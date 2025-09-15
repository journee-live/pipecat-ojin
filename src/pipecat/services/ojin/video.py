"""Ojin Persona implementation for Pipecat."""

import asyncio
import math
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Awaitable, Callable, Optional, Tuple

# Will use numpy when implementing persona-specific processing
from loguru import logger
from ojin.entities.interaction_messages import ErrorResponseMessage
from ojin.ojin_persona_client import OjinPersonaClient
from ojin.ojin_persona_messages import (
    IOjinPersonaClient,
    OjinPersonaCancelInteractionMessage,
    OjinPersonaInteractionInputMessage,
    OjinPersonaInteractionReadyMessage,
    OjinPersonaInteractionResponseMessage,
    OjinPersonaSessionReadyMessage,
)
from ojin.profiling_utils import FPSTracker
from pydantic import BaseModel

from pipecat.audio.utils import create_default_resampler
from pipecat.frames.frames import (
    BotStoppedSpeakingFrame,
    CancelFrame,
    EndFrame,
    Frame,
    OutputAudioRawFrame,
    OutputImageRawFrame,
    StartFrame,
    StartInterruptionFrame,
    TTSAudioRawFrame,
    TTSStoppedFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


def debug_frame(message: str, frame_idx: int, every_n_frames: int = 1):
    if frame_idx % every_n_frames == 0:
        logger.debug(message)


class OjinPersonaInitializedFrame(Frame):
    """Frame indicating that the persona has been initialized and can now output frames."""

    pass


class InteractionState(Enum):
    """Enum representing the possible states of an persona interaction.

    These states track the lifecycle of an interaction from creation to completion.
    """

    INACTIVE = "inactive"
    STARTING = "starting"
    WAITING_READY = "waiting_ready"
    ACTIVE = "active"
    ALL_AUDIO_PROCESSED = "all_audio_processed"


@dataclass
class OjinPersonaSettings:
    """Settings for Ojin Persona service.

    This class encapsulates all configuration parameters for the OjinPersonaService.
    """

    api_key: str = field(default="")  # api key for Ojin platform
    ws_url: str = field(default="wss://models.ojin.ai/realtime")  # websocket url for Ojin platform
    client_connect_max_retries: int = field(
        default=3
    )  # amount of times it will try to reconnect to the server
    client_reconnect_delay: float = field(default=3.0)  # time between connecting retries
    persona_config_id: str = field(default="")  # config id of the persona to use from Ojin platform
    image_size: Tuple[int, int] = field(default=(1920, 1080))
    cache_idle_sequence: bool = field(
        default=False
    )  # whether to cache the idle sequence loop to avoid doing inference while persona is not speaking
    idle_sequence_duration: int = field(default=30)  # length of the idle sequence loop in seconds.
    idle_to_speech_seconds: float = field(
        default=0.75
    )  # seconds to wait before starting speech, recommended not less than 0.75 to avoid missing frames. This ensures smooth transition between idle frames and speech frames
    tts_audio_passthrough: bool = field(
        default=False
    )  # whether to pass through TTS audio to the output
    push_bot_stopped_speaking_frames: bool = field(
        default=True
    )  # whether to push bot stopped speaking frames to the output


class ConversationSignal(Enum):
    """Possible states of the conversation."""

    START_INTERACTION_MESSAGE_SENT = "start_interaction_message_sent"
    SPEECH_AUDIO_STARTED_PROCESSING = "speech_audio_started_processing"
    USER_INTERRUPTED_AI = "user_interrupted_ai"
    NO_MORE_IMAGE_FRAMES_EXPECTED = "no_more_image_frames_expected"


class PersonaState(Enum):
    """Enum representing the possible states of the persona conversation FSM."""

    INVALID = "invalid"
    INITIALIZING = "initializing"
    IDLE = "idle"
    WAITING_INTERACTION_READY = "waiting_interaction_ready"
    IDLE_TO_SPEECH = "idle_to_speech"
    SPEECH = "speech"


class OjinPersonaFSM:
    """Finite State Machine for managing persona conversational states.

    This class manages the different states of an persona during a conversation,
    including initialization, idle animations, speech, and transitions between states.
    It also handles the caching of idle frames for efficient playback.

    Attributes:
        idle_loop (PersonaIdleLoop): The idle animation loop for the persona
        current_state (PersonaState): The current state of the persona
        fps (int): Frames per second for animations

    """

    def __init__(
        self,
        frame_processor: FrameProcessor,
        settings: OjinPersonaSettings,
        on_state_changed_callback: Callable[[PersonaState, PersonaState], Awaitable[None]],
    ):
        self._settings = settings
        self._frame_processor = frame_processor
        self._state = PersonaState.INVALID
        self._num_frames_missed = 0
        self._playback_loop = PersonaPlaybackLoop(settings.idle_sequence_duration, 25)
        self._speech_frames: asyncio.Queue[OutputImageRawFrame] = asyncio.Queue()
        self._transition_time: float = -1
        self._current_frame_idx: int = -1
        self._playback_task: Optional[asyncio.Task] = None
        self._waiting_for_image_frames = False
        self._previous_speech_frame: Optional[OutputImageRawFrame] = None
        self.on_state_changed_callback = on_state_changed_callback
        self.last_update_time: float = -1.0
        self.fps_tracker = FPSTracker("OjinPersonaFSM")
        self._transition_timestamp: float = -1.0

    async def start(self):
        await self.set_state(PersonaState.INITIALIZING)

    async def close(self):
        await self._stop_playback()

    async def set_state(self, new_state: PersonaState):
        if self._state == new_state:
            return

        old_state = self._state
        self._state = new_state
        logger.debug(f"set_state from {old_state} to {new_state}")
        self.on_state_changed(old_state, new_state)
        await self.on_state_changed_callback(old_state, new_state)

    def get_transition_frame_idx(self) -> int:
        return math.ceil(self._transition_time * 25)

    def get_state(self) -> PersonaState:
        """Get the current state of the persona FSM.

        Returns:
            The current persona state from the PersonaState enum

        """
        return self._state

    def receive_image_frame(self, image_frame: OutputImageRawFrame):
        """Process incoming image frames based on the current persona state.

        During initialization, frames are added to the idle animation loop.
        In other states, frames are queued as speech animation frames.

        Args:
            image_frame: The raw image frame to process

        """
        # While initializing we consider frames as idle frames
        if self._state == PersonaState.INITIALIZING:
            self._playback_loop.add_frame(image_frame.image)

        # On any other state these would be speech frames
        else:
            self._speech_frames.put_nowait(image_frame)

    async def on_conversation_signal(self, signal: ConversationSignal):
        """Handle conversation signals to update the persona state.

        Processes signals such as user interruptions, speech starting,
        and frame completion to trigger appropriate state transitions.

        Args:
            signal: The conversation signal to process

        """
        logger.debug(f"{signal}")
        match signal:
            case ConversationSignal.START_INTERACTION_MESSAGE_SENT:
                await self.set_state(PersonaState.WAITING_INTERACTION_READY)

            case ConversationSignal.USER_INTERRUPTED_AI:
                await self.interrupt()

            case ConversationSignal.SPEECH_AUDIO_STARTED_PROCESSING:
                await self.set_state(PersonaState.IDLE_TO_SPEECH)

            case ConversationSignal.NO_MORE_IMAGE_FRAMES_EXPECTED:
                self._waiting_for_image_frames = False
                if self._state == PersonaState.INITIALIZING:
                    await self.set_state(PersonaState.IDLE)

    async def interrupt(self):
        """Interrupt the current speech animation.

        Clears any queued speech frames and transitions the persona back to
        the IDLE state if it was in a speaking state.

        """
        if self._state in (
            PersonaState.SPEECH,
            PersonaState.IDLE_TO_SPEECH,
        ):
            await self.set_state(PersonaState.IDLE)  # Corrected from DittoState

            while not self._speech_frames.empty():
                self._speech_frames.get_nowait()

    def _start_playback(self):
        """Start the animation playback loop.

        Creates an asynchronous task to run the animation loop if one doesn't
        already exist. Initializes the timing for frame rate control.

        """
        logger.debug("Starting playback loop")

        if self._playback_task is not None:
            return
        self.last_update_time = time.perf_counter()
        self._playback_task = asyncio.create_task(self._run())

    async def _stop_playback(self):
        """Stop the animation playback loop.

        Cancels the running playback task if one exists and waits for it to
        complete before cleaning up references.

        """
        logger.debug("Stopping playback loop")
        if self._playback_task is None:
            return

        self._playback_task.cancel()
        with suppress(asyncio.CancelledError):
            await self._playback_task
        self._playback_task = None

    async def _run(self):
        """Run the main animation loop continuously while playback is active.

        Handle frame timing, state transitions, and frame processing based on
        the current persona state. Manage transitions between idle and speech states,
        detect when speech has ended, and push frames to the output pipeline.

        """
        try:
            self.last_update_time = time.perf_counter()
            while True:
                delta_time = time.perf_counter() - self.last_update_time
                self._playback_loop.step(delta_time)
                self.last_update_time = time.perf_counter()

                if (
                    not self._waiting_for_image_frames
                    and self._speech_frames.empty()
                    and (
                        self._state == PersonaState.SPEECH
                        or self._state == PersonaState.IDLE_TO_SPEECH
                    )
                ):
                    logger.debug("Speech ended!!!")
                    await self.set_state(PersonaState.IDLE)

                # Process output image frames
                if self.should_process_output():
                    frame = await self.get_next_persona_frame()
                    if frame is not None:
                        await self._frame_processor.push_frame(frame)

                await asyncio.sleep(0.005)
        except Exception as e:
            logger.exception(f"Playback loop stopped with error: {e}")

        logger.debug("Playback loop stopped")

    def should_process_output(self) -> bool:
        """Determine if the persona should process and output frames.

        Returns:
            True if the persona is in a state where it should output frames,
            False otherwise

        """
        return self._state in (
            PersonaState.IDLE,
            PersonaState.SPEECH,
            PersonaState.IDLE_TO_SPEECH,
            PersonaState.WAITING_INTERACTION_READY,
        )

    def on_state_changed(self, old_state: PersonaState, new_state: PersonaState):
        """Handle state transitions in the persona FSM.

        This method is called whenever the persona's state changes, allowing for
        state-specific behavior to be implemented.

        Args:
            new_state: The new state that the persona has transitioned to

        """
        match new_state:
            case PersonaState.INITIALIZING:
                self.fps_tracker.start()
                self._waiting_for_image_frames = True

            case PersonaState.IDLE | PersonaState.WAITING_INTERACTION_READY:
                # abort transition
                # self.fps_tracker.stop()
                self._transition_time = -1
                # If we have a previous speech frame we seek to it to syncrhonize perfectly the following idle frame
                if self._previous_speech_frame is not None:
                    self._playback_loop.seek_frame(self._previous_speech_frame.pts + 1)
                    self._previous_speech_frame = None

                if old_state == PersonaState.INITIALIZING:
                    self._start_playback()

            case PersonaState.SPEECH:
                self.fps_tracker.start()
                self._transition_time = -1
                pass

            case PersonaState.IDLE_TO_SPEECH:
                self._waiting_for_image_frames = True
                self._transition_timestamp = time.perf_counter()
                self._transition_time = (
                    self._playback_loop.get_playback_time() + self._settings.idle_to_speech_seconds
                )

            case _:
                logger.debug(f"State: {self._state} - Unknown state")

    async def get_next_persona_frame(self) -> OutputImageRawFrame | None:
        """Get the next frame to display based on the current persona state.

        Retrieves either an idle animation frame or a speech animation frame
        depending on the current state. If a speech frame is expected but not
        available, falls back to an idle frame and tracks missed frames.

        Returns:
            The next image frame to display, or None if no new frame is available

        """
        # Wait until current frame idx is different than the last one (frame steps of 25 fps)
        if self._current_frame_idx == self._playback_loop.get_current_frame_idx():
            return None

        self._current_frame_idx = self._playback_loop.get_current_frame_idx()

        # Transition to speech as soon as we reach the transition frame
        if self._current_frame_idx == self.get_transition_frame_idx():
            await self.set_state(PersonaState.SPEECH)

        match self._state:
            case (
                PersonaState.IDLE
                | PersonaState.IDLE_TO_SPEECH
                | PersonaState.WAITING_INTERACTION_READY
            ):
                debug_frame(
                    f"Pushing idle frame: {self._current_frame_idx}",
                    self._current_frame_idx,
                    50,
                )

                idle_frame = self._playback_loop.get_current_idle_frame()
                assert idle_frame is not None
                image_frame = OutputImageRawFrame(
                    image=idle_frame.image,
                    size=self._settings.image_size,
                    format="RGB",
                )
                image_frame.pts = self._playback_loop.get_current_frame_idx()
                return image_frame
            case PersonaState.SPEECH:
                try:
                    frame = self._speech_frames.get_nowait()
                except asyncio.QueueEmpty:
                    frame = None

                if frame is None:
                    self._num_frames_missed += 1
                    if self._num_frames_missed % 100 == 0:
                        logger.debug(f"Frames missed {self._num_frames_missed}")

                    if self._previous_speech_frame is not None:
                        return self._previous_speech_frame

                    # If we don't have a previous speech frame we push an idle frame instead
                    idle_frame = self._playback_loop.get_current_idle_frame()
                    assert idle_frame is not None
                    image_frame = OutputImageRawFrame(
                        image=idle_frame.image,
                        size=self._settings.image_size,
                        format="RGB",
                    )
                    image_frame.pts = self._playback_loop.get_current_frame_idx()

                    return image_frame

                else:
                    self._previous_speech_frame = frame
                    self.fps_tracker.update(1)
                    if frame.pts % 1 == 0:
                        logger.debug(
                            f"Pushing speech frame: {frame.pts} ==? {self._current_frame_idx}"
                        )
                    self._num_frames_missed = 0

                return frame
            case _:
                return None


OJIN_PERSONA_SAMPLE_RATE = 16000
SPEECH_FILTER_AMOUNT = 1000.0
IDLE_FILTER_AMOUNT = 1000.0
IDLE_MOUTH_OPENING_SCALE = 0.0
SPEECH_MOUTH_OPENING_SCALE = 1.0

IDLE_ANIMATION_KEYFRAMES_SLOT = 0

@dataclass
class OjinPersonaInteraction:
    """Represents an interaction session between a user and the Ojin persona.

    This class maintains the state of an ongoing interaction, including audio queues,
    frame tracking for animations, and interaction lifecycle state. It handles the
    buffering of audio inputs and manages the interaction's state transitions.
    """

    interaction_id: str = ""
    persona_id: str = ""
    audio_input_queue: asyncio.Queue[OjinPersonaInteractionInputMessage] | None = None
    audio_output_queue: asyncio.Queue[OutputAudioRawFrame] | None = None
    pending_first_input: bool = True
    start_frame_idx: int | None = None
    frame_idx: int = 0
    filter_amount: float = 0.0
    num_loop_frames: int = 0
    state: InteractionState = InteractionState.INACTIVE
    ending_extra_time: float = 1.0
    ending_timestamp: float = 0.0
    mouth_opening_scale: float = 0.0
    received_all_interaction_inputs: bool = False
    active_keyframes_slot: int = IDLE_ANIMATION_KEYFRAMES_SLOT
    keyframe_slot_to_update: int = -1

    def __post_init__(self):
        """Initialize queues after instance creation."""
        if self.audio_input_queue is None:
            self.audio_input_queue = asyncio.Queue()
        if self.audio_output_queue is None:
            self.audio_output_queue = asyncio.Queue()

    def next_frame(self):
        """Advance to the next frame in the animation sequence.

        Updates the frame index and applies mirroring for smooth looping animations.
        """
        self.frame_idx += 1

    def close(self):
        """Close the interaction."""
        if self.audio_input_queue is not None:
            while not self.audio_input_queue.empty():
                self.audio_input_queue.get_nowait()
                self.audio_input_queue.task_done()

        if self.audio_output_queue is not None:
            while not self.audio_output_queue.empty():
                self.audio_output_queue.get_nowait()
                self.audio_output_queue.task_done()

        self.state = InteractionState.INACTIVE
        self.received_all_interaction_inputs = False

    def set_state(self, new_state: InteractionState):
        """Update the interaction state.

        Changes the interaction's state and logs the transition if the state
        actually changes.

        Args:
            new_state: The new state to transition to

        """
        if self.state == new_state:
            return

        logger.debug(f"Old Interaction state: {self.state}, New Interaction state: {new_state}")
        old_state = self.state
        self.state = new_state


class OjinPersonaService(FrameProcessor):
    """Ojin Persona integration for Pipecat.

    This class provides integration between Ojin personas and the Pipecat framework.
    """

    def __init__(
        self,
        settings: OjinPersonaSettings,
        client: IOjinPersonaClient | None = None,
    ) -> None:
        super().__init__()
        logger.debug(f"OjinPersonaService initialized with settings {settings}")
        # Use provided settings or create default settings
        self._settings = settings
        if client is None:
            self._client = OjinPersonaClient(
                ws_url=settings.ws_url,
                api_key=settings.api_key,
                config_id=settings.persona_config_id,
            )
        else:
            self._client = client

        self._fsm = OjinPersonaFSM(
            self,
            settings,
            on_state_changed_callback=self._on_state_changed,
        )

        # Generate a UUID if avatar_id is not provided
        assert self._settings.persona_config_id is not None

        self._audio_input_task: Optional[asyncio.Task] = None
        self._audio_output_task: Optional[asyncio.Task] = None

        self._interaction: Optional[OjinPersonaInteraction] = None
        self._pending_interaction: Optional[OjinPersonaInteraction] = None

        self._resampler = create_default_resampler()
        self._server_fps_tracker = FPSTracker("OjinPersonaService")
        self.should_generate_silence: bool = False
        self._last_frame_timestamp: float | None = None
        self._stopping = False

    async def _generate_and_send_silence(self, duration: float, is_last_input: bool):
        num_samples = int(duration * OJIN_PERSONA_SAMPLE_RATE)
        silence_audio = b"\x00\x00" * num_samples
        logger.debug(f"Sending {duration}s of silence to initialize persona")
        assert self._interaction is not None and self._interaction.audio_input_queue is not None

        await self.push_ojin_message(
            OjinPersonaInteractionInputMessage(
                audio_int16_bytes=silence_audio,
                interaction_id=self._interaction.interaction_id,
                is_last_input=is_last_input,
                params={
                    "start_frame_idx": self._interaction.start_frame_idx,
                    "filter_amount": self._interaction.filter_amount,
                    "mouth_opening_scale": self._interaction.mouth_opening_scale,
                    "active_keyframe_slot_index": self._interaction.active_keyframes_slot,
                    "to_update_keyframe_slot_index": self._interaction.keyframe_slot_to_update,
                }
            )
        )

    async def _on_state_changed(self, old_state: PersonaState, new_state: PersonaState) -> None:
        """Handle state transitions in the persona FSM.

        This method is called when the persona's state changes and performs
        state-specific initialization actions.

        Args:
            old_state: The previous state of the persona
            new_state: The new state that the persona has transitioned to

        """
        if new_state == PersonaState.INITIALIZING:
            self._server_fps_tracker.start()
            # Send silence to persona with idle_sequence_duration
            await self._start_interaction(
                is_speech=False,
                active_keyframes_slot=IDLE_ANIMATION_KEYFRAMES_SLOT,
                keyframe_slot_to_update=IDLE_ANIMATION_KEYFRAMES_SLOT
            )
            assert self._interaction is not None
            self._interaction.set_state(InteractionState.ALL_AUDIO_PROCESSED)
            await self._generate_and_send_silence(self._settings.idle_sequence_duration, True)

        if new_state == PersonaState.IDLE_TO_SPEECH:
            self._server_fps_tracker.start()

        if old_state == PersonaState.INITIALIZING and new_state == PersonaState.IDLE:
            await self.push_frame(
                OjinPersonaInitializedFrame(), direction=FrameDirection.DOWNSTREAM
            )
            await self.push_frame(OjinPersonaInitializedFrame(), direction=FrameDirection.UPSTREAM)

        if new_state == PersonaState.SPEECH and self._audio_output_task is None:
            self._start_pushing_audio_output()

        if new_state == PersonaState.IDLE:
            logger.debug("PersonaState.IDLE reached - closing interaction")
            self._close_interaction()
            # self._server_fps_tracker.stop()
            if self._audio_output_task is not None:
                logger.debug("Stopping audio output")
                await self._stop_pushing_audio_output()
                if self._settings.push_bot_stopped_speaking_frames:
                    await self.push_frame(BotStoppedSpeakingFrame(), FrameDirection.UPSTREAM)
        if new_state == PersonaState.WAITING_INTERACTION_READY:
            # NOTE(mouad): nothing to do
            pass

    async def _start(self):
        """Initialize the persona service and start processing.

        Authenticates with the proxy and creates tasks for processing
        audio and receiving messages.
        """
        is_connected = await self.connect_with_retry()

        if not is_connected:
            return

        # Create tasks to process audio and video
        self._audio_input_task = self.create_task(self._process_queued_audio())
        self._receive_task = self.create_task(self._receive_messages())
        # TODO Jorge / Edgar : To handle edge cases with new messages for ending interation not cancelling, since the server still has audio to be processed and it's lost after cancelling
        # self._handle_incomming_frame_task = self.create_task(self._incomming_frame_task())

    async def connect_with_retry(self) -> bool:
        """Attempt to connect with configurable retry mechanism."""
        last_error: Optional[Exception] = None
        assert self._client is not None

        for attempt in range(self._settings.client_connect_max_retries):
            try:
                logger.info(
                    f"Connection attempt {attempt + 1}/{self._settings.client_connect_max_retries}"
                )
                await self._client.connect()
                logger.info("Successfully connected!")
                return True

            except ConnectionError as e:
                last_error = e
                logger.warning(f"Connection attempt {attempt + 1} failed: {e}")

                # If this was the last attempt, don't wait
                if attempt < self._settings.client_connect_max_retries - 1:
                    logger.info(f"Retrying in {self._settings.client_reconnect_delay} seconds...")
                    await asyncio.sleep(self._settings.client_reconnect_delay)

        # All retry attempts failed
        logger.error(
            f"Failed to connect after {self._settings.client_connect_max_retries} attempts. Last error: {last_error}"
        )
        await self.push_frame(EndFrame(), FrameDirection.UPSTREAM)
        await self.push_frame(EndFrame(), FrameDirection.DOWNSTREAM)
        return False

    # Disabled for now since it was causing issues with the server not processing all audio
    async def _incomming_frame_task(self):
        while True:
            if self._fsm is not None:
                time_since_transition = time.perf_counter() - self._fsm._transition_timestamp

                if (
                    self._fsm._state == PersonaState.SPEECH
                    and self._fsm._waiting_for_image_frames
                    and self._last_frame_timestamp is not None
                ):
                    last_received_frame_time = time.perf_counter() - self._last_frame_timestamp

                    if last_received_frame_time > 1.5:
                        logger.info("Ending interaction")
                        # We send the Cancel interaction message because we don't send the "last_audio" flag
                        # to the server, therefore the server won't be able to send the last frame and reset the model
                        # Cancelation message resets the model instead.
                        await self.push_ojin_message(
                            OjinPersonaCancelInteractionMessage(
                                interaction_id=self._interaction.interaction_id,
                            )
                        )
                        await self._fsm.on_conversation_signal(
                            ConversationSignal.NO_MORE_IMAGE_FRAMES_EXPECTED
                        )
                        self._last_frame_timestamp = None
                elif (
                    self._fsm._state == PersonaState.SPEECH
                    and self._fsm._waiting_for_image_frames
                    and time_since_transition > 2.5
                ):
                    logger.warning(
                        "No Frames received from the server, stopping interaction by timeout"
                    )
                    # We send the cancel Interaction message to reset the state even when we didn't receive any frame
                    await self.push_ojin_message(
                        OjinPersonaCancelInteractionMessage(
                            interaction_id=self._interaction.interaction_id,
                        )
                    )
                    await self._fsm.on_conversation_signal(
                        ConversationSignal.NO_MORE_IMAGE_FRAMES_EXPECTED
                    )

            await asyncio.sleep(0.01)

    async def _stop(self):
        """Stop the persona service and clean up resources.

        Cancels all running tasks, closes connections, and resets the state.
        """
        # Cancel queued audio processing task
        if self._audio_input_task:
            await self.cancel_task(self._audio_input_task)
            self._audio_input_task = None

        if self._receive_task:
            await self.cancel_task(self._receive_task)
            self._receive_task = None

        if self._client:
            await self._client.close()
            self._client = None

        # Clear all buffers
        await self._interrupt()

        if self._fsm:
            await self._fsm.close()
            self._fsm = None

        logger.debug(f"OjinPersonaService {self._settings.persona_config_id} stopped")

    @property
    def fsm_fps_tracker(self):
        return self._fsm.fps_tracker

    @property
    def server_fps_tracker(self):
        return self._server_fps_tracker

    def _start_pushing_audio_output(self):
        logger.warning("Start pushing audio output")
        self._audio_output_task = self.create_task(self._push_audio_output())

    async def _stop_pushing_audio_output(self):
        logger.warning("Stop pushing audio output")
        if self._audio_output_task:
            await self.cancel_task(self._audio_output_task)
            self._audio_output_task = None

    async def _push_audio_output(self):
        """Continuously push audio output to the proxy."""
        while True:
            assert (
                self._interaction is not None and self._interaction.audio_output_queue is not None
            )
            try:
                audio_frame = await self._interaction.audio_output_queue.get()
                await self.push_frame(audio_frame, direction=FrameDirection.DOWNSTREAM)
            except asyncio.QueueEmpty:
                await asyncio.sleep(0.05)

    async def _receive_messages(self):
        """Continuously receive and process messages from the proxy.

        This method runs as a background task and handles all incoming messages
        from the proxy.
        """
        while True:
            assert self._client is not None
            message = await self._client.receive_message()
            if message is not None:
                await self._handle_ojin_message(message)
            await asyncio.sleep(0.001)

    async def push_ojin_message(self, message: BaseModel):
        """Send a message to the proxy.

        Args:
            message: The message to send to the proxy

        """
        assert self._client is not None
        if hasattr(message, "interaction_id"):
            logger.info(
                f"Sending message type {type(message)} with interaction {message.interaction_id}"
            )

        await self._client.send_message(message)

    async def _handle_ojin_message(self, message: BaseModel):
        """Process incoming messages from the proxy.

        Handles different message types including authentication responses,
        interaction ready notifications, and interaction responses containing
        video frames.

        Args:
            message: The message received from the proxy

        """
        if isinstance(message, OjinPersonaInteractionResponseMessage):
            if self._interaction is None:
                logger.warning("No interaction in progress when receiving video frame")
                return

            self._server_fps_tracker.update(1)
            debug_frame(
                f"Received video frame fame_idx: {self._interaction.frame_idx}, interactionId: {message.interaction_id}, currentInteractionId: {self._interaction.interaction_id}",
                self._interaction.frame_idx,
                5,
            )
            # logger.info(f"Video frame received: {self._interaction.frame_idx} isFinal: {message.is_final_response}")
            # Create and push the image frame
            image_frame = OutputImageRawFrame(
                image=message.video_frame_bytes,
                size=self._settings.image_size,
                format="RGB",
            )
            image_frame.pts = self._interaction.frame_idx
            # Push the image frame to the FSM if it exists for advanced processing or directly to the output to outsource the processing to the client
            if self._fsm is not None:
                self._fsm.receive_image_frame(image_frame)
            else:
                debug_frame(
                    f"Video frame pushed (no fsm): {self._interaction.frame_idx}",
                    self._interaction.frame_idx,
                    5,
                )
                if self._audio_output_task is None:
                    self._start_pushing_audio_output()

                await self.push_frame(image_frame)

            self._interaction.next_frame()
            self._last_frame_timestamp = time.perf_counter()
            if message.is_final_response:
                logger.debug("No more video frames expected")
                if self._fsm is not None:
                    await self._fsm.on_conversation_signal(
                        ConversationSignal.NO_MORE_IMAGE_FRAMES_EXPECTED
                    )
                if self._pending_interaction is not None:
                    await self._start_interaction(self._pending_interaction, is_speech=True)
                    self._pending_interaction = None

        elif isinstance(message, OjinPersonaSessionReadyMessage):
            if self._fsm is not None:
                await self._fsm.start()

        elif isinstance(message, OjinPersonaInteractionReadyMessage):
            logger.debug("Received interaction ready message")
            assert self._fsm is not None
            if (
                self._interaction is not None
                and self._interaction.state == InteractionState.WAITING_READY
            ):
                self._interaction.set_state(InteractionState.ACTIVE)
                await self._fsm.on_conversation_signal(
                    ConversationSignal.SPEECH_AUDIO_STARTED_PROCESSING
                )
                self._interaction.start_frame_idx = self._fsm.get_transition_frame_idx()
                self._interaction.frame_idx = self._fsm.get_transition_frame_idx()

        elif isinstance(message, ErrorResponseMessage):
            is_fatal = False
            if message.payload.code == "NO_BACKEND_SERVER_AVAILABLE":
                logger.error("No OJIN servers available. Please try again later.")
                is_fatal = True
            elif message.payload.code == "FRAME_SIZE_TOO_BIG":
                logger.error(
                    "Frame Size sent to Ojin server was higher than the allowed max limit."
                )
            elif message.payload.code == "INVALID_INTERACTION_ID":
                logger.error("Invalid interaction ID sent to Ojin server")
            elif message.payload.code == "FAILED_CREATE_MODEL":
                is_fatal = True
                logger.error("Ojin couldn't create a model from supplied persona ID.")
            elif message.payload.code == "INVALID_PERSONA_ID_CONFIGURATION":
                is_fatal = True
                logger.error("Ojin couldn't load the configuration from the supplied persona ID.")

            if is_fatal:
                await self.push_frame(EndFrame(), FrameDirection.UPSTREAM)
                await self.push_frame(EndFrame(), FrameDirection.DOWNSTREAM)

    def get_fsm_state(self) -> PersonaState:
        """Get the current state of the persona's finite state machine.

        Returns:
            The current state of the persona FSM or INVALID if no FSM exists

        """
        if self._fsm is not None:
            return self._fsm.get_state()
        return PersonaState.INVALID

    def is_pending_initialization(self) -> bool:
        """Check if the persona is ready to receive TTS input.

        Returns:
            True if the persona is in a state that can accept TTS input, False otherwise

        """
        return self.get_fsm_state() not in [
            PersonaState.INITIALIZING,
            PersonaState.INVALID,
        ]

    def is_tts_input_allowed(self) -> bool:
        """Check if the persona is ready to receive TTS input.

        Returns:
            True if the persona is in a state that can accept TTS input, False otherwise

        """
        return self._interaction is None or self._interaction.state in [
            InteractionState.ACTIVE,
            InteractionState.WAITING_READY,
        ]

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process incoming frames from the pipeline.

        This method handles different frame types and routes them to the appropriate
        handler methods. It manages service lifecycle events (Start/End/Cancel),
        audio processing, and interaction state transitions.

        Args:
            frame: The frame to process
            direction: The direction of the frame (input or output)

        """
        await super().process_frame(frame, direction)

        # logger.debug(f"Processing frame: {type(frame)}")
        if isinstance(frame, StartFrame):
            logger.debug("StartFrame")
            await self.push_frame(frame, direction)
            await self._start()

        elif isinstance(frame, TTSStoppedFrame):
            logger.debug("TTSStoppedFrame")
            # TODO(@JM): Avoid ending interaction here since some TTS services continue to send audio frames
            if self._pending_interaction:
                self._pending_interaction = None
            else:
                await self._end_interaction()
            await self.push_frame(frame, direction)

        elif isinstance(frame, TTSAudioRawFrame):
            logger.debug("TTSAudioRawFrame")
            # TODO(@JM): Check if speech interaction is already possible
            await self._handle_input_audio(frame)
            if self._settings.tts_audio_passthrough:
                await self.push_frame(frame, direction)

        elif isinstance(frame, (EndFrame, CancelFrame)):
            await self._stop()
            await self.push_frame(frame, direction)

        elif isinstance(frame, StartInterruptionFrame):
            logger.debug("StartInterruptionFrame")
            # only interrupt if we are allowed to send TTS input
            if not self.is_pending_initialization() and self.is_tts_input_allowed():
                await self._interrupt()

            await self.push_frame(frame, direction)

        else:
            # Pass through any other frames
            await self.push_frame(frame, direction)

    async def _interrupt(self):
        """Interrupt the current interaction.

        Sends a cancel message to the backend, updates the FSM state, and
        cleans up the current interaction.
        """
        if self._interaction is None or self._interaction.interaction_id is None:
            logger.debug("Trying to interrupt an interaction but none is active")
            return

        logger.debug(f"Try interrupt interaction in state {self._interaction.state}")
        if self._interaction.state != InteractionState.INACTIVE:
            logger.warning("Sending CancelInteractionMessage")
            await self.push_ojin_message(
                OjinPersonaCancelInteractionMessage(
                    interaction_id=self._interaction.interaction_id,
                )
            )
            if self._fsm is not None:
                await self._fsm.interrupt()
                await self._fsm.on_conversation_signal(ConversationSignal.USER_INTERRUPTED_AI)

            self._close_interaction()

    async def _start_interaction(
        self,
        new_interaction: Optional[OjinPersonaInteraction] = None,
        is_speech: bool = False,
        active_keyframes_slot: int = IDLE_ANIMATION_KEYFRAMES_SLOT,
        keyframe_slot_to_update: int = -1
    ):
        """Start a new interaction with the persona.

        Creates a new interaction or uses the provided one, initializes it with
        the appropriate state and parameters, and sends a start message to the backend.

        Args:
            new_interaction: Optional existing interaction to use instead of creating a new one
            is_speech: Whether this interaction is speech-based (True) or idle (False)

        """
        self._interaction = new_interaction or OjinPersonaInteraction(
            persona_id=self._settings.persona_config_id,
        )
        self._interaction.num_loop_frames = self._settings.idle_sequence_duration * 25  # 25 fps
        self._interaction.set_state(InteractionState.STARTING)
        if is_speech:
            self._interaction.filter_amount = SPEECH_FILTER_AMOUNT
            self._interaction.mouth_opening_scale = SPEECH_MOUTH_OPENING_SCALE
            self._interaction.pending_first_input = True
            await self._fsm.on_conversation_signal(
                ConversationSignal.START_INTERACTION_MESSAGE_SENT
            )
        else:
            self._interaction.filter_amount = IDLE_FILTER_AMOUNT
            self._interaction.mouth_opening_scale = IDLE_MOUTH_OPENING_SCALE
            self._interaction.start_frame_idx = 0
            self._interaction.frame_idx = 0

        assert self._client is not None
        assert self._fsm is not None
        interaction_id = await self._client.start_interaction()
        logger.debug(f"Started interaction with id: {interaction_id}")
        self._interaction.interaction_id = interaction_id
        self._interaction.set_state(InteractionState.WAITING_READY)
        self._interaction.active_keyframes_slot   = active_keyframes_slot
        self._interaction.keyframe_slot_to_update = keyframe_slot_to_update

    async def _end_interaction(self):
        """End the current interaction.

        Sets received_all_interaction_inputs flag to True, which will trigger cleanup
        once all queued audio has been processed.
        """
        # TODO Handle possible race conditions i.e. when _interaction.state == STARTING
        if self._interaction is None:
            logger.error("_end_interaction but no interaction is set")
            return

        self._interaction.ending_timestamp = time.perf_counter()
        self._interaction.received_all_interaction_inputs = True

    async def _handle_input_audio(self, frame: TTSAudioRawFrame):
        """Process incoming audio frames from the TTS service.

        Handles audio frames based on the current persona state. If the persona is not
        ready to receive input, the audio is queued for later processing. Otherwise,
        it starts or continues an active interaction.

        Resamples the audio to the target sample rate and either sends it directly
        to the backend if an interaction is running, or queues it for later processing.

        Args:
            frame: The audio frame to process

        """
        resampled_audio = await self._resampler.resample(
            frame.audio, frame.sample_rate, OJIN_PERSONA_SAMPLE_RATE
        )

        if not self.is_pending_initialization():
            if self._interaction is None or self._interaction.interaction_id is None:
                logger.debug("No interaction is set")
                return

            if self._pending_interaction is None:
                self._pending_interaction = OjinPersonaInteraction(
                    persona_id=self._settings.persona_config_id,
                )
                self._pending_interaction.set_state(InteractionState.INACTIVE)

            assert self._pending_interaction.audio_input_queue is not None
            self._pending_interaction.audio_input_queue.put_nowait(
                OjinPersonaInteractionInputMessage(
                    interaction_id=self._interaction.interaction_id,
                    audio_int16_bytes=resampled_audio,
                )
            )
            self._pending_interaction.pending_first_input = False
            logger.debug(
                f"Audio input is still not allowed (initializing), queing to pending interaction. Queue size: {self._pending_interaction.audio_input_queue.qsize()}"
            )
        elif self.is_tts_input_allowed():
            if self._interaction is None:
                await self._start_interaction(is_speech=True)

            assert self._interaction is not None and self._interaction.audio_input_queue is not None

            await self._interaction.audio_input_queue.put(
                OjinPersonaInteractionInputMessage(
                    interaction_id=self._interaction.interaction_id,
                    audio_int16_bytes=resampled_audio,
                )
            )
            self._interaction.pending_first_input = False
            logger.debug(
                f"Queued audio for later processing. Queue size: {self._interaction.audio_input_queue.qsize()}"
            )

    def _close_interaction(self):
        """Close and clean up the current interaction.

        Clears the interaction queue and resets the interaction state.
        """
        logger.debug("Closing interaction")
        # Clear the interaction queue if it exists
        if self._interaction is not None:
            self._interaction.close()
            self._interaction = None

    async def _process_queued_audio(self):
        """Process audio that was queued before an interaction was ready.

        Continuously monitors the audio queue of the current interaction and
        sends audio messages to the backend when available. Handles the final
        audio chunk specially to signal the end of input.
        """
        audio_buffer = b""

        while True:
            # Wait until we have a running interaction (starts with first audio input)
            if (
                not self._interaction
                or self._interaction.audio_input_queue is None
                or self._interaction.interaction_id is None
                or self._interaction.state == InteractionState.WAITING_READY
                or self._interaction.state == InteractionState.ALL_AUDIO_PROCESSED
            ):
                await asyncio.sleep(0.001)
                continue

            is_final_message = False
            if self._interaction.received_all_interaction_inputs:
                if (
                    time.perf_counter()
                    > self._interaction.ending_timestamp + self._interaction.ending_extra_time
                ):
                    is_final_message = self._interaction.audio_input_queue.qsize() <= 1
                else:
                    is_final_message = False

            # while there is more audio coming we wait for it if we don't have any to process atm
            if self._interaction.audio_input_queue.empty() and not is_final_message:
                await asyncio.sleep(0.005)
                continue

            # Get audio from the queue
            should_finish_task = False
            try:
                message: OjinPersonaInteractionInputMessage = (
                    self._interaction.audio_input_queue.get_nowait()
                )
                message.interaction_id = self._interaction.interaction_id
                should_finish_task = True
            except asyncio.QueueEmpty:
                should_finish_task = False
                if is_final_message:
                    # TODO Tell server to end interaction by finish processing pending data. No more audio frames expected.
                    logger.warning("Pushing final message with empty audio")
                    silence_duration = 0.01
                    num_samples = int(silence_duration * OJIN_PERSONA_SAMPLE_RATE)
                    silence_audio = b"\x00\x00" * num_samples
                    message = OjinPersonaInteractionInputMessage(
                        interaction_id=self._interaction.interaction_id,
                        audio_int16_bytes=silence_audio,
                    )
                else:
                    logger.error(
                        f"Audio queue empty! state = {self._interaction.state} is_final_message = {is_final_message}"
                    )
                    continue


            if is_final_message:
                logger.debug("sending last audio input")
                self._interaction.set_state(InteractionState.ALL_AUDIO_PROCESSED)
                message.is_last_input = True

            message.params ={
                "start_frame_idx": self._interaction.start_frame_idx,
                "filter_amount": self._interaction.filter_amount,
                "mouth_opening_scale": self._interaction.mouth_opening_scale,
                "active_keyframe_slot_index": self._interaction.active_keyframes_slot,
                "to_update_keyframe_slot_index": self._interaction.keyframe_slot_to_update,
            }
            logger.debug(
                f"Sending audio int16: {len(message.audio_int16_bytes)} is_final: {message.is_last_input}"
            )

            await self.push_ojin_message(message)
            await self.enqueue_audio_output(message.audio_int16_bytes)

            if should_finish_task:
                self._interaction.audio_input_queue.task_done()

    async def enqueue_audio_output(self, audio: bytes):
        """Enqueue audio data to be sent as output frames.

        This method creates an OutputAudioRawFrame from the raw audio bytes
        and adds it to the current interaction's audio output queue.

        Args:
            audio: Raw audio bytes to be sent as output

        """
        assert self._interaction and self._interaction.audio_output_queue is not None
        await self._interaction.audio_output_queue.put(
            OutputAudioRawFrame(
                audio=audio,
                sample_rate=OJIN_PERSONA_SAMPLE_RATE,
                num_channels=1,
            )
        )


@dataclass
class AnimationKeyframe:
    """Represents a single frame in an animation sequence.

    This class stores information about a specific keyframe in an animation,
    including its position in the sequence and the image data.

    Attributes:
        mirror_frame_idx (int): Index used for mirrored animation playback
        frame_idx (int): The sequential index of this frame in the animation
        image (bytes): The binary image data for this keyframe

    """

    mirror_frame_idx: int
    frame_idx: int
    image: bytes


class PersonaPlaybackLoop:
    """Manages a complete idle animation loop with synchronized audio and video."""

    id: int = 0
    duration: int = 0  # seconds
    frames: list[AnimationKeyframe] = []  # Keyframes of the idle animation
    playback_time: float = 0  # Total elapsed playback time in seconds

    def __init__(
        self,
        duration: int,
        fps: int = 25,
    ):
        """Initialize the persona idle loop animation.

        Args:
            duration (int): The total duration of the animation in seconds
            fps (int, optional): Frames per second for the animation. Defaults to 25.

        """
        self.duration = duration
        self.fps = fps

    def num_frames(self) -> int:
        return len(self.frames)

    def add_frame(self, image: bytes) -> AnimationKeyframe:
        """Get an existing keyframe or create a new one at the specified frame index.

        Args:
            image (bytes): The image data for the frame

        Returns:
            AnimationKeyframe: The existing or newly created keyframe

        """
        frame_idx = len(self.frames)
        expected_frames = self.duration * self.fps
        keyframe = AnimationKeyframe(
            mirror_frame_idx=mirror_index(frame_idx, expected_frames),
            frame_idx=frame_idx,
            image=image,
        )
        self.frames.append(keyframe)
        return keyframe

    def get_frame(self, frame_idx: int) -> AnimationKeyframe | None:
        """Get an existing keyframe or create a new one at the specified frame index.

        Args:
            frame_idx (int): The frame index to retrieve or create

        Returns:
            AnimationKeyframe: The existing or newly created keyframe

        """
        for keyframe in self.frames:
            if keyframe.frame_idx == frame_idx:
                return keyframe

        logger.error(f"Couldn't find idle frame frame_idx: {frame_idx}")
        return None

    def get_frame_at_time(self, playback_time: float) -> AnimationKeyframe:
        """Retrieve the animation keyframe at a specific playback time.

        Args:
            playback_time (float): The time in seconds to get the frame for

        Returns:
            AnimationKeyframe: The keyframe corresponding to the given playback time

        """
        # Get total frames passed
        current_frame_idx = math.floor(playback_time * self.fps)

        mirror_frame_idx = mirror_index(current_frame_idx, len(self.frames))

        return self.frames[mirror_frame_idx]

    def get_current_idle_frame(self) -> AnimationKeyframe | None:
        """Get the keyframe at the current playback time.

        Returns:
            AnimationKeyframe | None: The current keyframe or None if no keyframes exist

        """
        return self.get_frame_at_time(self.playback_time)

    def get_current_frame_idx(self) -> int:
        """Get the absolute key frame idx at the current playback time

        Returns:
            int: The current keyframe idx

        """
        current_frame_idx = math.floor(self.playback_time * self.fps)
        return current_frame_idx

    def get_playback_time(self) -> float:
        return self.playback_time

    def seek(self, playback_time: float):
        """Set the playback time to a specific position.

        Args:
            playback_time (float): The time in seconds to set as the current playback position

        """
        self.playback_time = playback_time

    def seek_frame(self, frame_idx: int):
        """Set the playback position to a specific frame.

        Args:
            frame_idx (int): The frame index to seek to

        """
        self.playback_time = frame_idx / self.fps

    def step(self, delta_time: float):
        """Advance the animation by the specified time delta.

        Args:
            delta_time (float): The time in seconds to advance the animation

        """
        self.playback_time += delta_time


def mirror_index(index: int, size: int) -> int:
    """Calculate a mirrored index for creating a ping-pong animation effect.

    This method maps a continuously increasing index to a back-and-forth pattern
    within the given size, creating a ping-pong effect for smooth looping animations.

    Args:
        index (int): The original frame index
        size (int): The number of available frames

    Returns:
        int: The mirrored index that creates the ping-pong effect

    """

    # Calculate period length (going up and down)
    period = (size - 1) * 2

    # Get position within one period
    normalized_idx = index % period

    # If in first half, return the index directly
    if normalized_idx < size:
        return normalized_idx
    else:
        # If in second half, return the mirrored index
        return period - normalized_idx - 1
