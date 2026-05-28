"""OjinVideoService v2 — simplified fadeout-only interruption.

Spec: ``demo-modal-agents/docs/ojin_video_service_redesign.md``.

Key differences from the legacy module (``video_legacy.py``):

* Single interruption strategy (fadeout). No ``InterruptStrategy`` enum.
* Per-TTS audio buffer queue (each ``TTSStartedFrame`` opens a new buffer
  in a FIFO). The *current* buffer is the head being drained into the
  output; subsequent buffers wait their turn.
* Explicit four-state machine (``IDLE``, ``SPEAKING``, ``INTERRUPTING``,
  ``FADING_OUT``). Transitions are driven by the per-frame pop callback
  ``_on_video_frame_popped``.
* Interruption is allowed *only* when the bot is in ``SPEAKING``. User
  speech during ``IDLE`` does not cancel anything.
* Fadeout boundary: the server's ``frame_idx == 2`` video frame pops us
  into ``FADING_OUT``; the first ``frame_idx == 0`` (silence) popped in
  that state discards the current buffer and returns to ``IDLE``.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto
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

from pipecat.audio.utils import create_default_resampler
from pipecat.frames.frames import (
    CancelFrame,
    EndFrame,
    Frame,
    OutputAudioRawFrame,
    OutputImageRawFrame,
    StartFrame,
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
    """Emitted when the service transitions IDLE → SPEAKING."""

    pass


class OjinBotStoppedSpeakingFrame(Frame):
    """Emitted when the service transitions out of speaking states → IDLE."""

    pass


OJIN_PERSONA_SAMPLE_RATE = 16_000
BYTES_PER_FRAME = int(OJIN_PERSONA_SAMPLE_RATE / 25 * 2)  # 40 ms @ 16 kHz int16
OJIN_VIDEO_SERVICE_VERSION = 28  # bump for v2


@dataclass
class VideoFrame:
    """One video frame from the inference server, with bundled audio."""

    frame_idx: int
    image_bytes: bytes
    audio_bytes: bytes
    is_final: bool
    volume: int
    is_first_speech_frame: bool = False

    def is_silence(self) -> bool:
        return self.frame_idx == 0

    def is_fade_out(self) -> bool:
        return self.frame_idx == 2


class State(Enum):
    """Playback states for the v2 service.

    See ``demo-modal-agents/docs/ojin_video_service_redesign.md`` for the
    transition table.
    """

    IDLE = auto()
    SPEAKING = auto()
    INTERRUPTING = auto()
    FADING_OUT = auto()


_AUDIO_BUFFER_COUNTER = 0


def _next_audio_buffer_id() -> int:
    global _AUDIO_BUFFER_COUNTER
    _AUDIO_BUFFER_COUNTER += 1
    return _AUDIO_BUFFER_COUNTER


@dataclass
class AudioBuffer:
    """Holds the resampled TTS audio for one logical utterance.

    A buffer is opened by ``TTSStartedFrame`` and extended by subsequent
    ``TTSAudioRawFrame``s for the same turn. The next ``TTSStartedFrame``
    opens a new buffer; the previous one stays in the queue until its
    turn (or is discarded as part of a fadeout).

    ``buffer_id`` is a monotonic identifier across the process. It's
    used in logs to correlate audio events with the upstream TTS turn
    that produced them.
    """

    sample_rate: int = OJIN_PERSONA_SAMPLE_RATE
    num_channels: int = 1
    bytes_: bytearray = field(default_factory=bytearray)
    started_at: float = field(default_factory=time.monotonic)
    buffer_id: int = field(default_factory=_next_audio_buffer_id)


@dataclass
class OjinVideoSettings:
    """Settings for OjinVideoService v2.

    NOTE: the legacy ``interrupt_strategy`` field has been removed —
    v2 supports fadeout only.
    """

    api_key: str = ""
    ws_url: str = "wss://models.ojin.ai/realtime"
    client_connect_max_retries: int = 3
    client_reconnect_delay: float = 3.0
    config_id: str = ""
    image_size: Tuple[int, int] = (1280, 720)
    tts_audio_passthrough: bool = False
    started_speaking_delay_s: float = 0.5
    stopped_speaking_delay_s: float = 0.5
    frame_debugging_enabled: bool = False
    start_frame_cls: Type[Frame] = StartFrame
    # Hard cap on FADING_OUT state duration. Prevents stuck state if the
    # server never emits a post-fade silence frame for some reason.
    fading_out_timeout_s: float = 2.0
    # Maximum buffered server video frames before we start dropping oldest.
    max_buffered_video_frames: int = 700


class OjinVideoService(FrameProcessor):
    """v2 service — state-machine driven, fadeout-only interruption."""

    def __init__(
        self,
        settings: OjinVideoSettings,
        client: IOjinClient | None = None,
    ) -> None:
        super().__init__(name="ojin")
        logger.debug(
            f"OjinVideoService v2 initialised, version={OJIN_VIDEO_SERVICE_VERSION}, "
            f"settings={settings}"
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

        # State.
        self._state: State = State.IDLE
        self._session_data: Optional[dict] = None
        self._initialized = False

        # Server frames (incoming, popped by the playback loop).
        self._video_frames: deque[VideoFrame] = deque()

        # Audio buffer queue.
        self._audio_buffers: deque[AudioBuffer] = deque()
        self._current_buffer: Optional[AudioBuffer] = None

        # Resampler for TTS → server sample rate.
        self._resampler = create_default_resampler()

        # Playback timing.
        self.fps = 25
        self._frame_duration = 1.0 / self.fps  # 40 ms
        self.fps_tracker = FPSTracker("Ojin")
        self.last_frame_time = 0.0
        self._last_played_image_bytes: Optional[bytes] = None

        # Pause/resume. Paused on construction; consumer (widget) calls
        # ``resume_playback()`` once the room is ready.
        self._playback_paused = True
        self._playback_resume_event = asyncio.Event()

        # FADING_OUT safety timeout.
        self._fading_out_started_at: Optional[float] = None

        # Bot-side counters for logging — incremented every time we push
        # a frame downstream. The wire protocol does not carry a
        # sequential frame counter, so these are our best handle for
        # correlating audio/video position with timeline events. They
        # don't reset on interruption — they're cumulative for the
        # process lifetime.
        self._audio_chunks_emitted: int = 0
        self._video_frames_emitted: int = 0

        # TTFB metrics — set on TTSStartedFrame, cleared on first chunk.
        self._waiting_for_first_tts = False

        # Last server frame_idx (used for receive-side first-speech-frame
        # detection).
        self._last_received_frame_idx = -1

        # Tasks.
        self._receive_msg_task: Optional[asyncio.Task] = None
        self._video_playback_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def can_generate_metrics(self) -> bool:
        return True

    def pause_playback(self) -> None:
        if not self._playback_paused:
            self._playback_paused = True
            self._playback_resume_event.clear()
            logger.info("OjinVideoService: playback paused")

    def resume_playback(self) -> None:
        if self._playback_paused:
            self._playback_paused = False
            self._playback_resume_event.set()
            logger.info(
                f"OjinVideoService: playback resumed "
                f"(video_buf={len(self._video_frames)}, "
                f"audio_buffers={len(self._audio_buffers)})"
            )

    async def connect_with_retry(self) -> bool:
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
                    await asyncio.sleep(self._settings.client_reconnect_delay)
        await self.push_error(
            error_msg=(
                f"Failed to connect after "
                f"{self._settings.client_connect_max_retries} attempts: {last_error}"
            ),
            fatal=True,
        )
        await self._stop()
        return False

    # ------------------------------------------------------------------
    # Frame processing entry point
    # ------------------------------------------------------------------

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, self._settings.start_frame_cls):
            await self.push_frame(frame, direction)
            await self._start()

        elif isinstance(frame, TTSStartedFrame):
            # Open a new buffer at the tail of the queue.
            buf = AudioBuffer()
            self._audio_buffers.append(buf)
            self._waiting_for_first_tts = True
            logger.debug(
                f"TTSStartedFrame: opened buffer #{id(buf) & 0xFFFF} "
                f"(queue={len(self._audio_buffers)})"
            )
            await self.push_frame(frame, direction)

        elif isinstance(frame, TTSAudioRawFrame):
            await self._on_tts_audio_frame(frame)

        elif isinstance(frame, UserStartedSpeakingFrame):
            await self._on_user_started_speaking(frame, direction)

        elif isinstance(frame, (EndFrame, CancelFrame)):
            await self._stop()
            await self.push_frame(frame, direction)

        else:
            await self.push_frame(frame, direction)

    # ------------------------------------------------------------------
    # TTS audio path
    # ------------------------------------------------------------------

    async def _on_tts_audio_frame(self, frame: TTSAudioRawFrame) -> None:
        if self._client is None or not self._initialized:
            logger.warning("TTSAudioRawFrame received before client ready — dropping")
            return

        # Pick the buffer this audio belongs to:
        #   - If the queue has buffers, the tail buffer is the latest
        #     turn the upstream TTS opened (with TTSStartedFrame). Audio
        #     extends the tail.
        #   - Else if we're SPEAKING, the head was already promoted to
        #     _current_buffer and the upstream TTS is still streaming
        #     audio for the same turn. Audio extends _current_buffer.
        #   - During INTERRUPTING / FADING_OUT we drop incoming audio:
        #     it's straggler audio from the cancelled turn (upstream
        #     hasn't fully drained yet). Any new turn will start with
        #     a fresh TTSStartedFrame which opens a queue buffer.
        #   - In IDLE with no queued buffer, drop: no TTSStartedFrame
        #     has opened a buffer.
        target: Optional[AudioBuffer]
        if self._audio_buffers:
            target = self._audio_buffers[-1]
        elif self._state == State.SPEAKING and self._current_buffer is not None:
            target = self._current_buffer
        else:
            target = None

        if target is None:
            logger.warning(
                f"TTSAudioRawFrame received with no target buffer "
                f"(state={self._state.name}) — dropping {len(frame.audio)} bytes"
            )
            return

        resampled = await self._resampler.resample(
            frame.audio, frame.sample_rate, OJIN_PERSONA_SAMPLE_RATE
        )
        target.sample_rate = frame.sample_rate
        target.num_channels = frame.num_channels
        target.bytes_.extend(frame.audio)

        if self._waiting_for_first_tts:
            self._waiting_for_first_tts = False
            await self.start_ttfb_metrics()

        await self._client.send_message(OjinAudioInputMessage(audio_int16_bytes=resampled))

        if self._settings.tts_audio_passthrough:
            await self.push_frame(frame, FrameDirection.DOWNSTREAM)

    # ------------------------------------------------------------------
    # Interruption entry point
    # ------------------------------------------------------------------

    async def _on_user_started_speaking(
        self, frame: UserStartedSpeakingFrame, direction: FrameDirection
    ) -> None:
        if self._can_interrupt():
            logger.info("User started speaking while SPEAKING — sending cancel")
            self._state = State.INTERRUPTING
            await self._client.send_message(OjinCancelInteractionMessage())
        else:
            logger.debug(
                f"User started speaking while {self._state.name} — ignoring (no cancel sent)"
            )
        await self.push_frame(frame, direction)

    def _can_interrupt(self) -> bool:
        return self._state == State.SPEAKING and self._current_buffer is not None

    # ------------------------------------------------------------------
    # Server message handling
    # ------------------------------------------------------------------

    async def _handle_ojin_message(self, message: BaseModel) -> None:
        if isinstance(message, OjinSessionReadyMessage):
            if message.parameters is not None:
                self._session_data = message.parameters
            logger.info(f"Received Session Ready: {message}")

            if self._video_playback_task is None:
                self._video_playback_task = self.create_task(self._video_playback_loop())

            self._initialized = True
            init_frame = OjinVideoInitializedFrame(session_data=self._session_data)
            await self.push_frame(init_frame, direction=FrameDirection.DOWNSTREAM)
            await self.push_frame(init_frame, direction=FrameDirection.UPSTREAM)

            # Seed the server's audio timeline with one silent chunk so it
            # starts emitting silence frames.
            await self._client.send_message(
                OjinAudioInputMessage(audio_int16_bytes=b"\x00" * BYTES_PER_FRAME)
            )

        elif isinstance(message, OjinInteractionResponseMessage):
            if not self.fps_tracker.is_running:
                self.fps_tracker.start()
            self.fps_tracker.update(1)
            self.last_frame_time = time.monotonic()

            frame_idx = message.index
            samples = [
                int.from_bytes(message.audio_frame_bytes[i : i + 2], "little", signed=True)
                for i in range(0, len(message.audio_frame_bytes) - 1, 2)
            ]
            volume = (
                0 if len(samples) == 0 else int((sum(s * s for s in samples) / len(samples)) ** 0.5)
            )

            video_frame = VideoFrame(
                frame_idx=frame_idx,
                image_bytes=message.video_frame_bytes,
                audio_bytes=message.audio_frame_bytes,
                is_final=message.is_final_response,
                volume=volume,
            )

            # Mark first-speech-frame at the silence→speech boundary, server-side.
            if self._last_received_frame_idx != 1 and frame_idx == 1:
                video_frame.is_first_speech_frame = True
                logger.debug(
                    f"Received first speech frame after {time.time() - self._metrics._start_ttfb_time} seconds"
                )

            self._last_received_frame_idx = frame_idx

            self._video_frames.append(video_frame)

            # Backstop: never let the receive buffer grow unbounded.
            cap = self._settings.max_buffered_video_frames
            if len(self._video_frames) > cap:
                drop = len(self._video_frames) - cap
                for _ in range(drop):
                    self._video_frames.popleft()
                logger.warning(f"Receive buffer overflow: dropped {drop} oldest frames")

        elif isinstance(message, ErrorResponseMessage):
            await self.push_error(
                error_msg=f"Ojin server error: {message.payload.code}", fatal=True
            )
            await self._stop()

    async def _receive_ojin_messages(self) -> None:
        while True:
            assert self._client is not None
            message = await self._client.receive_message()
            if message is not None:
                await self._handle_ojin_message(message)

    # ------------------------------------------------------------------
    # State machine — runs once per video frame popped
    # ------------------------------------------------------------------

    async def _on_video_frame_popped(self, frame: VideoFrame) -> None:
        """Apply the state machine to one popped video frame.

        Transition table (matches the spec):

            IDLE         + speech (first)  + queue non-empty  → SPEAKING (pop head)
            SPEAKING     + silence + current buffer empty     → IDLE (drop current)
            SPEAKING     + UserStartedSpeakingFrame (proc_frame) → INTERRUPTING
            INTERRUPTING + fade_out                            → FADING_OUT
            FADING_OUT   + silence                             → IDLE (discard buffer)
        """
        if self._state == State.IDLE:
            if not frame.is_silence() and frame.is_first_speech_frame and self._audio_buffers:
                await self._promote_next_buffer(first_speech_frame=frame)

        elif self._state == State.SPEAKING:
            # Natural turn-end: server emits silence frame, our buffer
            # has nothing left to play. Drop current and return to IDLE.
            if (
                frame.is_silence()
                and self._current_buffer is not None
                and len(self._current_buffer.bytes_) == 0
            ):
                logger.info(f"SPEAKING → IDLE (turn end; queue={len(self._audio_buffers)})")
                self._current_buffer = None
                self._state = State.IDLE
                await self._emit_stopped_speaking()

        elif self._state == State.INTERRUPTING:
            if frame.is_fade_out():
                self._state = State.FADING_OUT
                self._fading_out_started_at = time.monotonic()
                logger.info("INTERRUPTING → FADING_OUT (current buffer keeps draining)")
            elif frame.is_silence():
                # Server skipped the fade_out frame and went straight to
                # silence. This happens when the server's audio input
                # queue was already starving at interrupt time — there
                # was nothing to fade out, so the server emits an
                # ``unpaired_request`` and transitions to silence. Treat
                # this silence frame the same way as the FADING_OUT →
                # IDLE boundary: discard current buffer, return to IDLE.
                # Without this branch the client gets stuck in
                # INTERRUPTING and the next ``UserStartedSpeakingFrame``
                # can't trigger a new cancel.
                discarded = len(self._current_buffer.bytes_) if self._current_buffer else 0
                logger.info(
                    f"INTERRUPTING → IDLE on silence (no fade frame "
                    f"emitted by server); discarding {discarded} bytes of "
                    f"current buffer (queue={len(self._audio_buffers)})"
                )
                self._current_buffer = None
                self._state = State.IDLE
                await self._emit_stopped_speaking()

        elif self._state == State.FADING_OUT:
            if frame.is_silence():
                discarded = len(self._current_buffer.bytes_) if self._current_buffer else 0
                logger.info(
                    f"FADING_OUT → IDLE on silence; discarding {discarded} bytes "
                    f"of current buffer (queue={len(self._audio_buffers)})"
                )
                self._current_buffer = None
                self._fading_out_started_at = None
                self._state = State.IDLE
                await self._emit_stopped_speaking()

        # Safety: if we've been FADING_OUT too long without a silence frame,
        # force the transition.
        if (
            self._state == State.FADING_OUT
            and self._fading_out_started_at is not None
            and (time.monotonic() - self._fading_out_started_at)
            > self._settings.fading_out_timeout_s
        ):
            logger.warning(
                f"FADING_OUT safety timeout "
                f"({self._settings.fading_out_timeout_s:.2f}s) — forcing → IDLE"
            )
            self._current_buffer = None
            self._fading_out_started_at = None
            self._state = State.IDLE
            await self._emit_stopped_speaking()

    async def _promote_next_buffer(self, first_speech_frame: Optional[VideoFrame] = None) -> None:
        """Pop the head of the audio-buffer queue to become current.

        Skips any empty buffers at the head — these arise when a
        ``TTSStartedFrame`` was followed by no audio (e.g. user barged in
        before any TTS audio landed). Empty buffers would otherwise block
        progress for the next non-empty buffer in the queue.

        If we end up with no non-empty buffer to promote, stay IDLE.

        Lipsync check: when the promoting first-speech video frame is
        provided, we compare the first chunk of audio we're about to
        play against the audio bundled with that video frame
        (``frame.audio_bytes``, which is what the server believes
        belongs to this video frame). Mismatch indicates a sync drift —
        we'd be playing audio that doesn't belong to this frame.
        """
        while self._audio_buffers:
            candidate = self._audio_buffers.popleft()
            if len(candidate.bytes_) == 0:
                logger.debug(f"Skipping empty audio buffer #{candidate.buffer_id} on promotion")
                continue
            self._current_buffer = candidate
            self._state = State.SPEAKING
            logger.info(
                f"IDLE → SPEAKING — buffer #{candidate.buffer_id} promoted "
                f"({len(candidate.bytes_)} bytes, queue={len(self._audio_buffers)}); "
                f"cumulative emitted audio_chunks={self._audio_chunks_emitted} "
                f"video_frames={self._video_frames_emitted}"
            )
            if first_speech_frame is not None:
                await self._check_lipsync_alignment(candidate, first_speech_frame)
            await self._emit_started_speaking()
            return
        # No non-empty buffer found.
        logger.debug("First-speech frame arrived but no non-empty buffer to promote")

    async def _check_lipsync_alignment(
        self, buffer: "AudioBuffer", first_speech_frame: VideoFrame
    ) -> None:
        """Compare buffer head against first speech frame's bundled audio.

        Log a warning when they disagree — the bot would be visibly out
        of sync (playing audio that doesn't belong to this video frame).

        The buffer holds audio at the TTS-native sample rate / channel
        count (whatever the upstream TTS emits). The server's
        ``audio_bytes`` is always at ``OJIN_PERSONA_SAMPLE_RATE`` mono
        (the format we sent to the server). To compare meaningfully we
        resample one 40 ms slice of the buffer head down to the server
        format, then byte-compare.

        Notes:
          * We use a *fresh* resampler instance, not ``self._resampler``,
            because the latter carries streaming state from the TTS path
            and would treat the fresh slice as a continuation, producing
            slightly different output bytes.
          * Stereo buffers can't be byte-compared against mono server
            audio without downmixing — we log a metadata-only line in
            that case and skip the compare.
        """
        server_audio = first_speech_frame.audio_bytes or b""
        # Bytes per 40 ms tick on the wire (server is always 16k mono int16).
        server_chunk_size = int(OJIN_PERSONA_SAMPLE_RATE * self._frame_duration) * 2
        # Bytes per 40 ms tick at the buffer's native format.
        buf_chunk_size = int(buffer.sample_rate * self._frame_duration) * buffer.num_channels * 2
        info_prefix = (
            f"[LIPSYNC] buffer #{buffer.buffer_id} "
            f"({buffer.sample_rate}Hz/{buffer.num_channels}ch, "
            f"buf_chunk={buf_chunk_size}B, head={len(buffer.bytes_)}B) "
            f"vs server frame ({len(server_audio)}B at "
            f"{OJIN_PERSONA_SAMPLE_RATE}Hz/1ch)"
        )

        if len(server_audio) == 0:
            logger.warning(f"{info_prefix} — first speech frame carried 0 bytes of audio")
            return

        if buffer.num_channels != 1:
            # Server audio is mono; comparing against a multi-channel
            # buffer head requires a downmix we'd rather not implement
            # for a diagnostic. Just log the alignment metadata.
            logger.info(f"{info_prefix} — byte-compare skipped (stereo buffer)")
            return

        if len(buffer.bytes_) < buf_chunk_size:
            logger.warning(
                f"{info_prefix} — buffer too short for a 40 ms slice "
                f"(have {len(buffer.bytes_)}B, need {buf_chunk_size}B)"
            )
            return

        buffer_head = bytes(buffer.bytes_[:buf_chunk_size])
        if buffer.sample_rate == OJIN_PERSONA_SAMPLE_RATE:
            # Same format as the server. Direct byte compare is meaningful
            # and avoids a resample.
            resampled_head = buffer_head
        else:
            # Fresh resampler — see docstring note about streaming state.
            fresh_resampler = create_default_resampler()
            resampled_head = await fresh_resampler.resample(
                buffer_head, buffer.sample_rate, OJIN_PERSONA_SAMPLE_RATE
            )

        cmp_len = min(len(resampled_head), len(server_audio), server_chunk_size)
        if cmp_len == 0:
            logger.warning(f"{info_prefix} — nothing to compare after resampling")
            return

        a = resampled_head[:cmp_len]
        b = server_audio[:cmp_len]
        if a == b:
            logger.info(f"{info_prefix} — byte-level match ({cmp_len}B)")
        else:
            diff_at = next(
                (i for i in range(cmp_len) if a[i] != b[i]),
                cmp_len,
            )
            logger.warning(
                f"{info_prefix} — MISMATCH at byte {diff_at}/{cmp_len}. Visual lipsync will drift."
            )

    # ------------------------------------------------------------------
    # Playback loop
    # ------------------------------------------------------------------

    async def _video_playback_loop(self) -> None:
        """Audio-as-clock playback loop.

        Each 40 ms tick:
          1. If paused, wait for resume.
          2. Sleep + spin-lock until the next tick boundary.
          3. Pop one video frame (if any). Run the state machine.
          4. Drain one chunk from the current buffer if in a speaking state.
          5. Emit OutputAudioRawFrame (audio or silence) + OutputImageRawFrame.
        """
        logger.info("Starting v2 playback loop")

        sample_rate = OJIN_PERSONA_SAMPLE_RATE
        audio_shape_initialized = False
        num_channels = 1
        chunk_size = int(sample_rate * self._frame_duration) * num_channels * 2
        silence_chunk = b"\x00" * chunk_size
        start_ts = time.perf_counter()
        next_tick = start_ts + self._frame_duration
        initial_buffer = 6
        silence_audio = OutputAudioRawFrame(
            audio=silence_chunk, sample_rate=OJIN_PERSONA_SAMPLE_RATE, num_channels=1
        )
        while self._initialized:
            if self._playback_paused:
                await self._playback_resume_event.wait()
                next_tick = time.perf_counter() + self._frame_duration
                initial_buffer = 6
                continue

            now = time.perf_counter()
            sleep_for = next_tick - now - 0.003
            if sleep_for > 0:
                await asyncio.sleep(sleep_for)
            while time.perf_counter() < next_tick:
                pass
            next_tick += self._frame_duration

            # Initial buffer warm-up.
            if self._video_frames and initial_buffer > 0:
                initial_buffer -= 1
                continue

            pts = int(time.monotonic() * 1_000_000_000)

            # Pop a video frame (if any). Note: we may emit silence audio
            # and a repeated image when the buffer is empty (server slow).
            video_frame: Optional[VideoFrame] = None
            if self._video_frames:
                video_frame = self._video_frames.popleft()
                await self._on_video_frame_popped(video_frame)

            # Audio: drain one chunk from current_buffer if speaking.
            audio_frame: Optional[OutputAudioRawFrame] = None
            speaking_audio = (
                self._state
                in (
                    State.SPEAKING,
                    State.INTERRUPTING,
                    State.FADING_OUT,
                )
                and self._current_buffer is not None
            )

            if speaking_audio and self._current_buffer:
                # Initialize audio shape and silence chunk if we haven't yet (e.g. if the first frame(s)
                if not audio_shape_initialized:
                    audio_shape_initialized = True
                    sample_rate = self._current_buffer.sample_rate
                    num_channels = self._current_buffer.num_channels
                    chunk_size = int(sample_rate * self._frame_duration) * num_channels * 2
                    silence_chunk = b"\x00" * chunk_size
                    silence_audio = OutputAudioRawFrame(
                        audio=silence_chunk, sample_rate=sample_rate, num_channels=num_channels
                    )
                buf = self._current_buffer.bytes_
                if len(buf) >= chunk_size:
                    chunk = bytes(buf[:chunk_size])
                    del buf[:chunk_size]
                elif len(buf) > 0:
                    chunk = bytes(buf)
                    buf.clear()
                else:
                    # Underrun.
                    logger.warning(
                        f"[UNDERRUN] current buffer empty while "
                        f"{self._state.name} — emitting silence"
                    )
                    chunk = None

                if chunk is not None:
                    audio_frame = OutputAudioRawFrame(
                        audio=chunk,
                        sample_rate=self._current_buffer.sample_rate,
                        num_channels=self._current_buffer.num_channels,
                    )
                    audio_frame.pts = pts

            # Push frames downstream.
            if video_frame is not None:
                self._last_played_image_bytes = video_frame.image_bytes
                out_image = await self._prepare_video_frame(video_frame.image_bytes, pts)
                if out_image is not None:
                    await self.push_frame(out_image)
                    self._video_frames_emitted += 1
                # audio_frame = OutputAudioRawFrame(
                #     audio=video_frame.audio_bytes,
                #     sample_rate=sample_rate,
                #     num_channels=num_channels,
                # )
            elif self._last_played_image_bytes is not None:
                # No new frame — repeat the last one to keep the video flowing.
                out_image = await self._prepare_video_frame(self._last_played_image_bytes, pts)
                if out_image is not None:
                    await self.push_frame(out_image)
                    self._video_frames_emitted += 1

            await self.push_frame(audio_frame or silence_audio)
            self._audio_chunks_emitted += 1

    # ------------------------------------------------------------------
    # Started/Stopped speaking signalling
    # ------------------------------------------------------------------

    async def _emit_started_speaking(self) -> None:
        await self.push_frame(OjinBotStartedSpeakingFrame())
        await self.stop_ttfb_metrics()

    async def _emit_stopped_speaking(self) -> None:
        await self.push_frame(OjinBotStoppedSpeakingFrame())

    # ------------------------------------------------------------------
    # Service lifecycle
    # ------------------------------------------------------------------

    async def _start(self) -> None:
        if not await self.connect_with_retry():
            return
        assert self._client is not None
        self._receive_msg_task = self.create_task(self._receive_ojin_messages())
        await self._client.start_interaction()

    async def _stop(self) -> None:
        self._initialized = False
        if self._client is not None:
            try:
                await self._client.close()
            except Exception as e:
                logger.warning(f"Error closing client: {e}")
        for t in (self._receive_msg_task, self._video_playback_task):
            if t is not None:
                t.cancel()
                try:
                    await t
                except (asyncio.CancelledError, Exception):
                    pass

    # ------------------------------------------------------------------
    # Frame preparation (JPEG decode + crop to target aspect)
    # ------------------------------------------------------------------

    async def _prepare_video_frame(
        self, video_bytes: bytes, pts: Optional[int] = None
    ) -> Optional[OutputImageRawFrame]:
        if not video_bytes:
            return None
        arr = np.frombuffer(video_bytes, dtype=np.uint8)
        bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if bgr is None:
            return None
        target_w, target_h = self._settings.image_size
        h, w = bgr.shape[:2]
        scale = max(target_w / w, target_h / h)
        new_w, new_h = int(w * scale), int(h * scale)
        bgr = cv2.resize(bgr, (new_w, new_h), interpolation=cv2.INTER_AREA)
        x = (new_w - target_w) // 2
        y = (new_h - target_h) // 2
        bgr = bgr[y : y + target_h, x : x + target_w]
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        out = OutputImageRawFrame(image=rgb.tobytes(), size=(target_w, target_h), format="RGB")
        if pts is not None:
            out.pts = pts
        return out
