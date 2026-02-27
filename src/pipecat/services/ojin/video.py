"""Continuous audio streaming variant of OjinVideoService.

This service sends TTS audio to the inference server on-demand.
The server maintains a virtual timeline at 25fps and generates silence
when no client audio is available.
"""

import asyncio
import os
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple, Type

import cv2
import numpy as np
from loguru import logger
from ojin.entities.interaction_messages import ErrorResponseMessage
from ojin.ojin_client import OjinClient
from ojin.ojin_client_messages import (
    IOjinClient,
    OjinAudioInputMessage,
    OjinCancelInteractionMessage,
    OjinInteractionResponseMessage,
    OjinSessionReadyMessage,
)
from ojin.profiling_utils import FPSTracker
from pydantic import BaseModel

from pipecat.audio.utils import create_default_resampler, is_silence
from pipecat.frames.frames import (
    CancelFrame,
    EndFrame,
    Frame,
    OutputAudioRawFrame,
    OutputImageRawFrame,
    StartFrame,
    StartInterruptionFrame,
    TTSAudioRawFrame,
    TTSStartedFrame,
    UserStartedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


@dataclass
class OjinVideoInitializedFrame(Frame):
    """Frame indicating that the service has been initialized."""

    session_data: Optional[dict] = None


class OjinBotStartedSpeakingFrame(Frame):
    """Frame sent after X seconds of receiving TTS audio."""

    pass


class OjinBotStoppedSpeakingFrame(Frame):
    """Frame sent after Y seconds of running out of TTS audio."""

    pass


OJIN_PERSONA_SAMPLE_RATE = 16000
BYTES_PER_FRAME = int(OJIN_PERSONA_SAMPLE_RATE / 25 * 2)
MAX_FRAMES_BUFFER = 3
MIN_FRAMES_BUFFER = 0


@dataclass
class VideoFrame:
    """Represents a video frame with bundled audio from the server."""

    frame_idx: int
    image_bytes: bytes
    audio_bytes: bytes
    is_final: bool
    volume: int
    is_first_speech_frame: bool = False

    def is_silence(self) -> bool:
        return self.frame_idx == 0


@dataclass
class OjinVideoSettings:
    """Settings for Ojin Video Continuous Service."""

    api_key: str = field(default="")
    ws_url: str = field(default="wss://models.ojin.ai/realtime")
    client_connect_max_retries: int = field(default=3)
    client_reconnect_delay: float = field(default=3.0)
    config_id: str = field(default="")
    image_size: Tuple[int, int] = field(default=(1280, 720))
    tts_audio_passthrough: bool = field(default=False)
    # Speaking notification delays
    started_speaking_delay_s: float = field(default=0.5)  # Delay before sending StartedSpeaking
    stopped_speaking_delay_s: float = field(default=0.5)  # Delay before sending StoppedSpeaking
    frame_debugging_enabled: bool = field(default=False)
    start_frame_cls: Type[Frame] = field(default=StartFrame)


OJIN_VIDEO_SERVICE_VERSION = 3


class OjinVideoService(FrameProcessor):
    """Continuous audio streaming service.

    Sends TTS audio to the server on-demand:
    - Client sends TTS audio immediately when received
    - Server maintains virtual timeline at 25fps
    - Server generates silence when no client audio available
    """

    def __init__(
        self,
        settings: OjinVideoSettings,
        client: IOjinClient | None = None,
    ) -> None:
        super().__init__(name="ojin")
        logger.debug(
            f"OjinVideoService initialized with settings {settings} version: {OJIN_VIDEO_SERVICE_VERSION}"
        )

        self._settings = settings
        if client is None:
            self._client = OjinClient(
                ws_url=settings.ws_url,
                api_key=settings.api_key,
                config_id=settings.config_id,
                mode=os.getenv("OJIN_MODE", ""),
            )
        else:
            self._client = client

        self._session_data: Optional[dict] = None

        # Video frames queue from server
        self._video_frames: deque[VideoFrame] = deque()

        # Speech audio buffer - raw bytes ready to send (resampled to OJIN_PERSONA_SAMPLE_RATE)
        self._speech_buffer: bytearray = bytearray()

        # Playback state
        self.fps = 25
        self.fps_tracker = FPSTracker("Ojin")

        self._initialized = False
        self.last_frame_time = 0
        self._is_speaking = False
        self._waiting_for_first_tts = False
        self._current_frame_idx = -1
        self._played_frame_idx = -1
        self._last_played_image_bytes: Optional[bytes] = None

        # Audio input handling
        self._resampler = create_default_resampler()

        # Tasks
        self._receive_msg_task: Optional[asyncio.Task] = None
        self._video_playback_task: Optional[asyncio.Task] = None

        # Frame timing
        self._frame_duration = 0.04

        # Speaking state tracking
        self._turn = 0
        self._last_frame_idx = -1
        self._waiting_for_first_real_speech_frame = False
        self._waiting_to_play_silence_frame = False
        self._bot_speaking = False
        self._discarded_speech_frames = 0
        self._audio_playback_task: Optional[asyncio.Task] = None
        self._interrupting = False
        self._pending_latency_report: Optional[tuple[float, float]] = None

    def can_generate_metrics(self) -> bool:
        """Enable TTFB metrics reporting via the standard pipecat metrics system."""
        return True

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

                if attempt < self._settings.client_connect_max_retries - 1:
                    logger.info(f"Retrying in {self._settings.client_reconnect_delay} seconds...")
                    await asyncio.sleep(self._settings.client_reconnect_delay)

        await self.push_error(
            error_msg=f"Failed to connect after {self._settings.client_connect_max_retries} attempts. error: {last_error}",
            fatal=True,
        )
        await self._stop()
        return False

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process incoming frames from the pipeline."""
        await super().process_frame(frame, direction)

        if isinstance(frame, self._settings.start_frame_cls):
            logger.debug(f"{self._settings.start_frame_cls.__name__} received")
            await self.push_frame(frame, direction)
            await self._start()

        elif isinstance(frame, TTSStartedFrame):
            logger.warning("TTSStartedFrame received")
            self._interrupting = False
            self._waiting_for_first_tts = True
            await self.push_frame(frame, direction)

        elif isinstance(frame, TTSAudioRawFrame):
            if self._interrupting:
                logger.debug("Interrupting, dropping TTS audio")
                return
            await self._send_tts_audio(frame)

        elif isinstance(frame, (EndFrame, CancelFrame)):
            await self._stop()
            await self.push_frame(frame, direction)
        elif isinstance(frame, UserStartedSpeakingFrame):
            if not self._interrupting and self._client is not None:
                self._interrupting = True
                self._waiting_for_first_tts = False
                await self._stop_audio_playback()
                # OjinCancelInteractionMessage will clear any existing tts audio sent to the server. There might be still some frames coming
                await self._client.send_message(OjinCancelInteractionMessage())
            await self.push_frame(frame, direction)
        else:
            await self.push_frame(frame, direction)

    async def _send_tts_audio(self, frame: TTSAudioRawFrame):
        """Send TTS audio to the server immediately.

        The server maintains a virtual timeline and will generate silence
        when no client audio is available.
        """
        # Resample audio to target sample rate
        resampled_audio = await self._resampler.resample(
            frame.audio, frame.sample_rate, OJIN_PERSONA_SAMPLE_RATE
        )
        self._speech_buffer.extend(resampled_audio)

        if self._waiting_for_first_tts:
            self._waiting_for_first_tts = False
            await self.start_ttfb_metrics()
        # Send audio to server immediately
        # logger.debug(f"Sending TTS audio to server, size: {len(resampled_audio)} bytes")
        await self._client.send_message(
            OjinAudioInputMessage(
                audio_int16_bytes=resampled_audio,
            )
        )

        if self._settings.tts_audio_passthrough:
            await self.push_frame(frame, FrameDirection.DOWNSTREAM)

    async def _handle_ojin_message(self, message: BaseModel):
        """Process incoming messages from the server."""
        if isinstance(message, OjinSessionReadyMessage):
            if message.parameters is not None:
                self._session_data = message.parameters

            logger.info(f"Received Session Ready: {message}")
            if self._session_data and self._session_data.get("server_id"):
                logger.info(f"Connected to server: {self._session_data.get('server_id')}")

            # Start the playback loop
            if self._video_playback_task is None:
                self._video_playback_task = self.create_task(self._video_playback_loop())

            # Notify that we're ready
            self._initialized = True
            initialized_frame = OjinVideoInitializedFrame(session_data=self._session_data)
            await self.push_frame(initialized_frame, direction=FrameDirection.DOWNSTREAM)
            await self.push_frame(initialized_frame, direction=FrameDirection.UPSTREAM)

            await self._client.send_message(
                OjinAudioInputMessage(
                    audio_int16_bytes=b"\x00" * BYTES_PER_FRAME,
                )
            )

        elif isinstance(message, OjinInteractionResponseMessage):
            if not self.fps_tracker.is_running:
                self.fps_tracker.start()
            self.fps_tracker.update(1)

            if self.fps_tracker.total_frames % 25 == 0:
                self.fps_tracker.log()

            self.last_frame_time = time.monotonic()
            frame_idx = message.index
            samples = [
                int.from_bytes(message.audio_frame_bytes[i : i + 2], "little", signed=True)
                for i in range(0, len(message.audio_frame_bytes) - 1, 2)
            ]
            volume = 0 if len(samples) == 0 else (sum(s * s for s in samples) / len(samples)) ** 0.5

            if self._settings.frame_debugging_enabled:
                logger.debug(
                    f"Received video frame {message.index} [{volume}], delta: {time.monotonic() - self.last_frame_time} buffer: {len(self._video_frames)}"
                )
            # Queue video frame with bundled audio
            video_frame = VideoFrame(
                frame_idx=frame_idx,
                image_bytes=message.video_frame_bytes,
                audio_bytes=message.audio_frame_bytes,
                is_final=message.is_final_response,
                volume=volume,
            )

            if frame_idx != self._last_frame_idx:
                self._turn += 1
                self._last_frame_idx = frame_idx
                if not video_frame.is_silence():
                    self._waiting_for_first_real_speech_frame = True
                else:
                    self._waiting_to_play_silence_frame = True

            if self._waiting_for_first_real_speech_frame and not video_frame.is_silence():
                self._waiting_for_first_real_speech_frame = False
                video_frame.is_first_speech_frame = True

            self._video_frames.append(video_frame)
            if self._settings.frame_debugging_enabled:
                logger.debug(
                    f"Received video frame {frame_idx}, is_final={message.is_final_response}"
                )

        elif isinstance(message, ErrorResponseMessage):
            await self.push_error(
                error_msg=f"Ojin server error: {message.payload.code}", fatal=True
            )
            await self._stop()

    async def _receive_ojin_messages(self):
        """Continuously receive and process messages from the server."""
        while True:
            assert self._client is not None
            message = await self._client.receive_message()
            if message is not None:
                await self._handle_ojin_message(message)

    async def _video_playback_loop(self):
        """Main playback loop - outputs video frames and audio at fixed fps."""
        logger.info("Starting playback loop")

        start_ts = time.perf_counter()
        next_frame_time = start_ts + self._frame_duration
        is_silence = False
        frame_count = 0
        # Determine which frame to play
        image_bytes: Optional[bytes] = None
        skip_count = 0
        initial_buffer = 6

        while self._initialized:
            # Sleep for most of the wait time
            now = time.perf_counter()
            sleep_time = next_frame_time - now
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

            next_frame_time += self._frame_duration
            # Check if we have a ready video frame
            if len(self._video_frames) > 0:
                if initial_buffer > 0:
                    initial_buffer -= 1
                    continue

                video_frame = self._video_frames.popleft()
                frame_count += 1
                image_bytes = video_frame.image_bytes

                self._last_played_image_bytes = image_bytes
                is_silence = video_frame.is_silence()

                if self._waiting_to_play_silence_frame and is_silence:
                    await self._stop_audio_playback()
                    self._waiting_to_play_silence_frame = False

                if video_frame.is_first_speech_frame:
                    await self._start_audio_playback()

                if self._settings.frame_debugging_enabled:
                    if is_silence:
                        logger.debug(
                            f"[SILENCE] Playing frame {frame_count}, buffer left: {len(self._video_frames)} volume: {video_frame.volume}"
                        )
                    else:
                        logger.debug(
                            f"[SPEECH] Playing frame {frame_count}, buffer left: {len(self._video_frames)} volume: {video_frame.volume}"
                        )
                all_silence = (
                    all(f.is_silence() for f in self._video_frames) and len(self._video_frames) > 0
                )
                if all_silence and len(self._video_frames) > MAX_FRAMES_BUFFER:
                    skip_count += 1
                    if skip_count % 2 == 0:
                        self._video_frames.popleft()
                        logger.debug(
                            f"Skipping silence frame: {len(self._video_frames)}, target: {MAX_FRAMES_BUFFER}"
                        )
                elif all_silence and len(self._video_frames) < MIN_FRAMES_BUFFER:
                    next_frame_time += self._frame_duration
                    logger.debug(
                        f"Slowing down silence frames: {len(self._video_frames)}, target: {MIN_FRAMES_BUFFER}"
                    )

                await self.encode_and_send(image_bytes, video_frame.is_first_speech_frame)

            elif self._last_played_image_bytes:
                # Repeat last frame to avoid stutter
                logger.debug(f"frame miss, repeating frame {frame_count}")
                continue
            else:
                # No frame to show yet - just continue
                continue

    async def _start_audio_playback(self):
        logger.warning("Starting audio playback")
        self._is_speaking = True
        await self.push_frame(OjinBotStartedSpeakingFrame(), direction=FrameDirection.DOWNSTREAM)
        await self.stop_ttfb_metrics()
        if self._audio_playback_task is not None:
            self._stop_audio_playback()

        self._audio_playback_task = asyncio.create_task(self._playback_audio())

    async def _stop_audio_playback(self):
        if not self._is_speaking:
            return

        self._is_speaking = False
        await self.push_frame(OjinBotStoppedSpeakingFrame(), direction=FrameDirection.DOWNSTREAM)
        self._speech_buffer.clear()
        if self._audio_playback_task is not None:
            self._audio_playback_task.cancel()
            try:
                await self._audio_playback_task
            except asyncio.CancelledError:
                pass
            self._audio_playback_task = None

    async def _playback_audio(self):
        sample_rate = OJIN_PERSONA_SAMPLE_RATE
        num_channels = 1
        chunk_duration_s = 0.1  # 100ms
        bytes_per_sample = 2  # 16-bit PCM
        chunk_size = int(sample_rate * chunk_duration_s) * num_channels * bytes_per_sample

        next_push_time = time.perf_counter()
        is_first_audio_frame = True
        logger.info("Started audio playback")
        try:
            while True:
                if not self._speech_buffer:
                    await asyncio.sleep(0.005)
                    continue

                next_push_time = time.perf_counter()
                if len(self._speech_buffer) < chunk_size:
                    audio = bytes(self._speech_buffer)
                    self._speech_buffer.clear()
                else:
                    audio = bytes(self._speech_buffer[:chunk_size])
                    del self._speech_buffer[:chunk_size]

                audio_frame = OutputAudioRawFrame(
                    audio=audio,
                    sample_rate=sample_rate,
                    num_channels=num_channels,
                )
                audio_frame.pts = int(time.monotonic() * 1_000_000_000)
                if is_first_audio_frame:
                    logger.warning(f"First audio frame played! size: {len(audio_frame.audio)}")
                    is_first_audio_frame = False

                await self.push_frame(audio_frame)

                # logger.debug(
                #     f"Playing audio frame, duration: {len(audio_frame.audio) / sample_rate / num_channels / bytes_per_sample:.3f}s, buffer left: {len(self._speech_buffer)}"
                # )
                next_push_time += chunk_duration_s

                # Sleep for most of the wait time
                now = time.perf_counter()
                sleep_time = next_push_time - now - 0.005
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)

                # Spin lock for precise timing
                while time.perf_counter() < next_push_time:
                    pass
        finally:
            self._audio_playback_task = None

    async def _start(self):
        """Initialize the service and start processing."""
        is_connected = await self.connect_with_retry()
        if not is_connected:
            return

        # Start receiving messages
        self._receive_msg_task = self.create_task(self._receive_ojin_messages())

        # Start an interaction for continuous streaming
        await self._client.start_interaction()

    async def encode_and_send(self, video: bytes, is_first: bool = False):
        image_array = np.frombuffer(video, dtype=np.uint8)
        image_size = self._settings.image_size
        decoded_image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
        if decoded_image is not None:
            h, w = decoded_image.shape[:2]
            target_w, target_h = image_size

            scale = min(target_w / w, target_h / h)
            new_w = int(w * scale)
            new_h = int(h * scale)

            scaled_image = cv2.resize(decoded_image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
            rgb_image = cv2.cvtColor(scaled_image, cv2.COLOR_BGR2RGB)
            rgb_bytes = rgb_image.tobytes()

            rgb_frame = OutputImageRawFrame(image=rgb_bytes, size=(new_w, new_h), format="RGB")
            rgb_frame.pts = int(time.monotonic() * 1_000_000_000)
            if is_first:
                logger.warning(f"First image frame played!")
            await self.push_frame(rgb_frame, FrameDirection.DOWNSTREAM)
        pass

    async def _stop(self):
        self._initialized = False
        self._is_speaking = False
        if self._client:
            await self._client.close()
            self._client = None

        """Stop the service and clean up resources."""
        if self._receive_msg_task:
            await self.cancel_task(self._receive_msg_task)
            self._receive_msg_task = None

        if self._video_playback_task:
            await self.cancel_task(self._video_playback_task)
            self._video_playback_task = None

        logger.debug(f"OjinVideoService {self._settings.config_id} stopped")

    def can_generate_metrics(self) -> bool:
        """Check if this service can generate processing metrics.

        Returns:
            True, as OjinVideoService supports metrics generation.
        """
        return True
