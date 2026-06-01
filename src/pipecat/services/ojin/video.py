"""OjinVideoService v3 — server-signalled turn boundary.

Spec: ``demo-modal-agents/docs/ojin_video_service_v3_redesign.md``.

Key differences from v2:

* No bot-side first-speech-frame inference. The server emits
  ``frame_idx == 3`` for the first SPEECH frame of a new turn (either
  cancel-armed or silence-streak-armed). The bot swaps its audio buffer
  on that signal alone.
* No 4-state machine. The bot's effective state is derived from
  ``_current_buffer`` (existence + interrupted flag): if a buffer
  exists and is not interrupted, we're speaking; otherwise we're idle.
* No receive-side trim of the video deque. Mid-speech ``frame_idx == 0``
  frames (audio-feeder starvation glitches at the server) flow through
  the current buffer's video as-is.
* No IDLE silence-buffer trim. The audio buffer queue + ``frame_idx == 3``
  swap already bounds head silence.

Audio remains the playback clock — audio drains every tick when the
current buffer has bytes available. Within-turn lipsync drift on video
underrun is an accepted trade-off (audio crackle would be worse).

Fadeout audio-cut: when a user barges in, the current buffer is marked
``interrupted = True``. The buffer keeps draining (bytes consumed) but
audio is silenced. Visual playback continues from the server's fade
frames until the next ``frame_idx == 3`` triggers the swap.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections import deque
from dataclasses import dataclass, field
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
from pipecat.services.ojin.session_trace import (
    OjinSessionTrace,
    new_session_id,
    play_lane_for_idx,
    recv_lane_for_idx,
)


@dataclass
class OjinVideoInitializedFrame(Frame):
    """Frame indicating that the service has been initialized."""

    session_data: Optional[dict] = None


class OjinBotStartedSpeakingFrame(Frame):
    """Emitted when a new audio buffer is promoted to current (speaking)."""

    pass


class OjinBotStoppedSpeakingFrame(Frame):
    """Emitted when the current buffer drains/finishes and no next buffer."""

    pass


OJIN_PERSONA_SAMPLE_RATE = 16_000
BYTES_PER_FRAME = int(OJIN_PERSONA_SAMPLE_RATE / 25 * 2)  # 40 ms @ 16 kHz int16
OJIN_VIDEO_SERVICE_VERSION = 29  # bump for v3

# Swap-time audio alignment (see _align_current_buffer_to_frame).
_ALIGN_ANCHOR_FRAMES = 6  # how many leading new-turn frames to match on
_ALIGN_MIN_RMS = 1.0  # below this the anchor is silence — skip aligning
_ALIGN_REL_TOL = 0.05  # match tolerance as a fraction of the anchor RMS


def _rms_int16(audio: bytes) -> Optional[float]:
    """RMS amplitude of int16 PCM bytes, or None if empty/odd-length."""
    if not audio or len(audio) < 2:
        return None
    samples = np.frombuffer(audio[: len(audio) - (len(audio) % 2)], dtype="<i2")
    if samples.size == 0:
        return None
    return float(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))


def _session_trace_enabled(settings_flag: bool) -> bool:
    """Whether to write the per-session Perfetto trace.

    On for every session by default; ``OJIN_BOT_SESSION_TRACE=0`` (or
    ``false``/``no``/``off``) is a kill-switch, read at session start so it can
    be toggled without a code change.
    """
    if not settings_flag:
        return False
    env = os.getenv("OJIN_BOT_SESSION_TRACE")
    if env is not None and env.strip().lower() in {"0", "false", "no", "off"}:
        return False
    return True


@dataclass
class VideoFrame:
    """One video frame from the inference server, with bundled audio."""

    frame_idx: int
    image_bytes: bytes
    audio_bytes: bytes
    is_final: bool
    volume: int

    def is_silence(self) -> bool:
        return self.frame_idx == 0

    def is_fade_out(self) -> bool:
        return self.frame_idx == 2

    def is_new_turn_start(self) -> bool:
        """First speech frame of a new turn (v3 marker)."""
        return self.frame_idx == 3


_AUDIO_BUFFER_COUNTER = 0


def _next_audio_buffer_id() -> int:
    global _AUDIO_BUFFER_COUNTER
    _AUDIO_BUFFER_COUNTER += 1
    return _AUDIO_BUFFER_COUNTER


@dataclass
class AudioBuffer:
    """Holds the resampled TTS audio for one logical utterance.

    Opened by ``TTSStartedFrame``, extended by subsequent ``TTSAudioRawFrame``s
    for the same turn. The ``interrupted`` flag is set when the user barges
    in: the buffer keeps being drained (so its in-flight video frames can
    pop in time with the audio clock) but the audio chunks are silenced
    on output, producing the visible fadeout effect.
    """

    sample_rate: int = OJIN_PERSONA_SAMPLE_RATE
    num_channels: int = 1
    bytes_: bytearray = field(default_factory=bytearray)
    started_at: float = field(default_factory=time.monotonic)
    buffer_id: int = field(default_factory=_next_audio_buffer_id)
    interrupted: bool = False


@dataclass
class LipsyncTraceEntry:
    """Correlates a displayed video frame with the audio played that tick.

    Captured only when ``OjinVideoSettings.lipsync_trace_enabled`` is set, so
    it costs nothing in production. The point of the record is to make the
    post-swap lip-sync invariant *measurable*: ``frame_audio_bytes`` is the
    audio slice the server generated this video frame from (it travels bundled
    in the ``OjinInteractionResponseMessage``), and ``output_audio_bytes`` is
    the audio chunk drained from ``_current_buffer`` and pushed downstream the
    same tick. If the two correspond to the same underlying speech, lip-sync is
    correct; a persistent divergence after a swap is a desync whose size is the
    lag between them.
    """

    tick: int
    frame_idx: int  # wire marker: 0 silence / 1 speech / 2 fade / 3 new-turn
    swapped: bool  # a buffer-swap trigger fired this tick
    current_buffer_id: Optional[int]
    interrupted: bool  # current buffer was interrupted (audio silenced)
    frame_audio_bytes: bytes  # popped frame's bundled audio (server input slice)
    output_audio_bytes: Optional[bytes]  # audio drained from the current buffer (None on underrun)


@dataclass
class OjinVideoSettings:
    """Settings for OjinVideoService v3."""

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
    # Maximum buffered server video frames before we start dropping oldest.
    max_buffered_video_frames: int = 700
    # When set, the playback loop records a LipsyncTraceEntry per tick (into
    # ``_lipsync_trace``) pairing each displayed frame's bundled audio with the
    # audio chunk played that tick. Off in production; on for verification.
    lipsync_trace_enabled: bool = False
    # On a buffer swap, align the new buffer's read head to the audio the
    # server's first new-turn frame was generated from. The server can drop
    # leading new-turn speech (e.g. the post-fade SPEECH-drop window), which
    # would otherwise leave the new turn's audio lagging the video by the
    # dropped amount for the whole turn. On by default — it's a no-op when the
    # head already matches (the steady-state case).
    align_audio_on_swap: bool = True
    # Max leading frames to search/trim when aligning at swap (bounds cost and
    # blast radius). 50 frames = 2 s, well above any realistic drop window.
    align_audio_max_frames: int = 50
    # Write a per-session Perfetto trace (audio/video events) under
    # session_trace_dir. On for every session by default; env
    # OJIN_BOT_SESSION_TRACE=0 disables. See session_trace.py.
    session_trace_enabled: bool = True
    session_trace_dir: str = "/root/debug/sessions/bot"


class OjinVideoService(FrameProcessor):
    """v3 service — server-signalled turn boundary, no state machine."""

    def __init__(
        self,
        settings: OjinVideoSettings,
        client: IOjinClient | None = None,
    ) -> None:
        super().__init__(name="ojin")
        logger.debug(
            f"OjinVideoService v3 initialised, version={OJIN_VIDEO_SERVICE_VERSION}, "
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

        # Bot-side counters for logging.
        self._audio_chunks_emitted: int = 0
        self._video_frames_emitted: int = 0

        # TTFB metrics.
        self._waiting_for_first_tts = False

        # Tasks.
        self._receive_msg_task: Optional[asyncio.Task] = None
        self._video_playback_task: Optional[asyncio.Task] = None

        # Derived speaking state — fires the downstream "started/stopped
        # speaking" signals at edges of this predicate. Tracked here so
        # we emit each frame exactly once per transition.
        self._was_speaking_emitted: bool = False

        # Lip-sync verification trace (opt-in via settings). Bounded ring of
        # per-tick frame/audio correlations; empty + untouched in production.
        self._lipsync_trace: deque[LipsyncTraceEntry] = deque(maxlen=4000)

        # Per-session Perfetto trace (created in _start, written in _stop).
        # All event recording is guarded by ``self._trace is not None``.
        self._trace: Optional[OjinSessionTrace] = None
        self._tr_session_start: float = 0.0  # session span anchor (µs)
        self._tr_connect_start: float = 0.0  # connect span anchor (µs)
        self._tr_speaking_start: Optional[float] = None  # bot_speaking anchor
        self._tr_interrupt_start: Optional[float] = None  # cancel→new_turn anchor
        self._tr_emit_times: deque[float] = deque()  # recent video emits for fps
        self._tr_underruns: int = 0
        # Response-latency anchor: µs mark of the first TTS audio frame of the
        # current turn (when the bot's speech starts flowing into the avatar).
        # Closed twice per turn — once when the first speech video frame arrives
        # from the server (recv: the Ojin inference round-trip) and once when it
        # is played downstream (played: adds bot-side buffering) — each gated by
        # its own flag so the measurement fires exactly once. Armed only while
        # the session trace is active.
        self._tr_first_tts_audio_at: Optional[float] = None
        self._awaiting_first_recv_video: bool = False
        self._awaiting_first_played_video: bool = False

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
                f"TTSStartedFrame: opened buffer #{buf.buffer_id} "
                f"(queue={len(self._audio_buffers)})"
            )
            if self._trace is not None:
                self._trace.instant(
                    "tts_input",
                    "tts_started",
                    args={"buffer_id": buf.buffer_id, "queue_len": len(self._audio_buffers)},
                )
            await self.push_frame(frame, direction)

        elif isinstance(frame, TTSAudioRawFrame):
            # Check if duration is 0.5s
            duration = len(frame.audio) / (frame.sample_rate * frame.num_channels * 2)
            is_silence = frame.audio == b"\x00" * len(frame.audio)  # Check if audio is silence
            if duration - 0.5 < 0.01 and is_silence:  # Discard trailing silence
                logger.debug(
                    f"Received TTSAudioRawFrame with duration 0.5s — "
                    f"treating as first TTS frame of a turn for TTFB metrics"
                )
                if self._trace is not None:
                    self._trace.instant(
                        "tts_input",
                        "tts_silence_discarded",
                        args={"dur_ms": round(duration * 1000, 1)},
                    )
                return
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
        #   - If the queue has any buffers, the tail buffer is the latest
        #     turn upstream opened (with TTSStartedFrame). Audio extends
        #     the tail.
        #   - Else if a non-interrupted current buffer is draining, this
        #     is in-turn streaming TTS: extend the current buffer.
        #   - Else drop. The current buffer is interrupted (we're in
        #     fadeout) and no new TTSStartedFrame has opened a fresh
        #     buffer yet — the audio is straggler bytes from a cancelled
        #     turn.
        target: Optional[AudioBuffer]
        if self._audio_buffers:
            target = self._audio_buffers[-1]
        elif self._current_buffer is not None and not self._current_buffer.interrupted:
            target = self._current_buffer
        else:
            target = None

        if target is None:
            logger.warning(
                f"TTSAudioRawFrame received with no target buffer "
                f"(current={'interrupted' if self._current_buffer is not None else 'none'}) "
                f"— dropping {len(frame.audio)} bytes"
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
            # Anchor the per-turn video response latency at the first TTS audio
            # of the turn, and arm both the recv and played measurements.
            if self._trace is not None:
                self._tr_first_tts_audio_at = self._trace.mark()
                self._awaiting_first_recv_video = True
                self._awaiting_first_played_video = True

        await self._client.send_message(OjinAudioInputMessage(audio_int16_bytes=resampled))

        if self._trace is not None:
            dur_ms = round(
                len(frame.audio) / (frame.sample_rate * frame.num_channels * 2) * 1000, 1
            )
            self._trace.instant(
                "tts_input",
                "tts_audio",
                args={
                    "bytes": len(frame.audio),
                    "dur_ms": dur_ms,
                    "buffer_id": target.buffer_id,
                    "sample_rate": frame.sample_rate,
                },
            )
            self._trace.instant("to_server", "audio_sent", args={"bytes": len(resampled)})

        if self._settings.tts_audio_passthrough:
            await self.push_frame(frame, FrameDirection.DOWNSTREAM)

    # ------------------------------------------------------------------
    # Interruption entry point
    # ------------------------------------------------------------------

    async def _on_user_started_speaking(
        self, frame: UserStartedSpeakingFrame, direction: FrameDirection
    ) -> None:
        can = self._can_interrupt()
        if self._trace is not None:
            self._trace.instant(
                "interruption",
                "user_started_speaking",
                args={
                    "can_interrupt": can,
                    "buffer_id": (
                        self._current_buffer.buffer_id if self._current_buffer is not None else None
                    ),
                },
            )
        if can:
            logger.info(
                f"User started speaking while playing buffer "
                f"#{self._current_buffer.buffer_id} — marking interrupted and "
                f"sending cancel"
            )
            self._current_buffer.interrupted = True
            # Discard the queued buffers of the cancelled turn. A long agent
            # response is split into several TTS groups → several buffers; the
            # bot forwards every TTS frame to the inference server eagerly
            # (ahead of playback), so the whole response is already in the
            # server's input buffer. On cancel the server drains ALL of that
            # pre-sent audio and renders the genuinely-new turn from audio that
            # arrives after the drain. If we kept these stale queued buffers,
            # the next frame_idx==3 would swap playback to one of them and the
            # avatar would lip-sync the new turn over the cancelled turn's
            # audio. Dropping them here keeps client and server symmetric:
            # both discard everything pre-interrupt, so the next frame_idx==3
            # lands on the new turn's fresh buffer.
            discarded_buffers = len(self._audio_buffers)
            self._audio_buffers.clear()
            await self._client.send_message(OjinCancelInteractionMessage())
            if discarded_buffers:
                logger.info(
                    f"Barge-in discarded {discarded_buffers} queued buffer(s) "
                    f"from the cancelled turn"
                )
            if self._trace is not None:
                self._trace.instant("to_server", "cancel_sent")
                self._trace.instant(
                    "interruption",
                    "buffer_interrupted",
                    args={
                        "buffer_id": self._current_buffer.buffer_id,
                        "discarded_queued": discarded_buffers,
                    },
                )
                # Anchor the cancel→new-turn round-trip span (closed when the
                # next frame_idx==3 arrives).
                self._tr_interrupt_start = self._trace.mark()
        else:
            logger.debug(
                f"User started speaking while idle/already-interrupted — ignoring (no cancel sent)"
            )
        await self.push_frame(frame, direction)

    def _can_interrupt(self) -> bool:
        return (
            self._current_buffer is not None
            and not self._current_buffer.interrupted
            and len(self._current_buffer.bytes_) > 0
        )

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
            if self._trace is not None:
                self._trace.span("lifecycle", "connect", self._tr_connect_start)
            init_frame = OjinVideoInitializedFrame(session_data=self._session_data)
            await self.push_frame(init_frame, direction=FrameDirection.DOWNSTREAM)
            await self.push_frame(init_frame, direction=FrameDirection.UPSTREAM)

            # Seed the server's audio timeline with one silent chunk so it
            # starts emitting silence frames.
            await self._client.send_message(
                OjinAudioInputMessage(audio_int16_bytes=b"\x00" * BYTES_PER_FRAME)
            )
            if self._trace is not None:
                self._trace.instant("to_server", "seed_sent", args={"bytes": BYTES_PER_FRAME})

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
            # logger.debug(f"Received frame_idx={frame_idx} (volume={volume})")
            self._video_frames.append(video_frame)

            if self._trace is not None:
                self._trace.instant(
                    recv_lane_for_idx(frame_idx),
                    "frame_recv",
                    cat=str(frame_idx),
                    args={
                        "frame_idx": frame_idx,
                        "volume": volume,
                        "audio_len": len(message.audio_frame_bytes),
                        "recv_buf": len(self._video_frames),
                    },
                )
                # Close the cancel→new-turn round-trip span on the first
                # new-turn frame after a barge-in (the client-observed fade
                # latency — the lip-sync KPI).
                if frame_idx == 3 and self._tr_interrupt_start is not None:
                    self._trace.span("interruption", "interrupt→new_turn", self._tr_interrupt_start)
                    self._tr_interrupt_start = None

                # First speech video frame of the turn arriving from the server
                # — the Ojin inference round-trip (first TTS audio → video out).
                if (
                    self._awaiting_first_recv_video
                    and self._tr_first_tts_audio_at is not None
                    and not video_frame.is_silence()
                    and not video_frame.is_fade_out()
                ):
                    self._awaiting_first_recv_video = False
                    latency_ms = self._trace.record_response_latency(
                        "recv",
                        self._tr_first_tts_audio_at,
                        args={"frame_idx": frame_idx},
                    )
                    logger.info(
                        f"📹 First speech video frame received {latency_ms}ms "
                        f"after first TTS audio (frame_idx={frame_idx})"
                    )

            # Backstop: never let the receive buffer grow unbounded.
            cap = self._settings.max_buffered_video_frames
            if len(self._video_frames) > cap:
                drop = len(self._video_frames) - cap
                for _ in range(drop):
                    self._video_frames.popleft()
                logger.warning(f"Receive buffer overflow: dropped {drop} oldest frames")
                if self._trace is not None:
                    self._trace.instant("recv:idle", "recv_overflow_drop", args={"dropped": drop})

        elif isinstance(message, ErrorResponseMessage):
            if self._trace is not None:
                self._trace.instant(
                    "lifecycle", "server_error", args={"code": str(message.payload.code)}
                )
            await self.push_error(
                error_msg=f"Ojin server error: {message.payload.code}", fatal=True
            )
            await self._stop()

    async def _receive_ojin_messages(self) -> None:
        """Pull messages off the websocket and dispatch to the handler.

        Wraps each receive + handle in try/except so a malformed message
        or transient handler exception doesn't silently kill the loop.
        """
        while True:
            assert self._client is not None
            try:
                message = await self._client.receive_message()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Error receiving server message — continuing")
                continue
            if message is None:
                continue
            try:
                await self._handle_ojin_message(message)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    f"Error handling server message {type(message).__name__} — continuing"
                )

    # ------------------------------------------------------------------
    # Buffer swap on frame_idx == 3
    # ------------------------------------------------------------------

    async def _swap_to_next_buffer(self, align_to_frame: Optional["VideoFrame"] = None) -> None:
        """Promote the head of the audio buffer queue to current.

        Discards whatever bytes remain in ``_current_buffer`` (in-flight
        audio of a cancelled turn, or audio buffered ahead of playback
        for a natural-turn-end case). Server's ``frame_idx == 3`` marker
        is authoritative — bytes before this point belonged to the prior
        turn, bytes from now on belong to the new turn.

        ``align_to_frame`` is the video frame that triggered this swap (the
        first frame of the new turn). When ``align_audio_on_swap`` is set, we
        line the new buffer's read head up with the audio that frame was
        generated from — the server can drop leading new-turn speech, which
        would otherwise leave audio lagging video for the whole turn.

        If the queue is empty when we get a swap signal, log a warning
        and skip — server-bot desync, but harmless (next swap will
        come on the next ``frame_idx == 3``).
        """
        if not self._audio_buffers:
            logger.warning(
                f"frame_idx=3 received but audio buffer queue is empty "
                f"(current={'present' if self._current_buffer else 'none'}) "
                f"— skipping swap"
            )
            return

        prev_remnant = len(self._current_buffer.bytes_) if self._current_buffer is not None else 0
        prev_id = self._current_buffer.buffer_id if self._current_buffer is not None else None

        # Skip empty buffers at the head — TTSStartedFrame followed by no
        # audio (e.g. upstream cancelled before any bytes landed).
        new_buffer: Optional[AudioBuffer] = None
        while self._audio_buffers:
            candidate = self._audio_buffers.popleft()
            if len(candidate.bytes_) == 0:
                logger.debug(f"Skipping empty audio buffer #{candidate.buffer_id} on swap")
                continue
            new_buffer = candidate
            break

        if new_buffer is None:
            logger.warning(
                f"frame_idx=3 received but all queued buffers were empty — skipping swap"
            )
            self._current_buffer = None
            await self._maybe_emit_stopped_speaking()
            return

        self._current_buffer = new_buffer
        logger.info(
            f"frame_idx=3 swap: prev buffer #{prev_id} discarded "
            f"({prev_remnant}B remnant) → new buffer #{new_buffer.buffer_id} "
            f"({len(new_buffer.bytes_)}B; queue={len(self._audio_buffers)}); "
            f"prev-turn emitted audio_chunks={self._audio_chunks_emitted} "
            f"video_frames={self._video_frames_emitted}"
        )

        if self._trace is not None:
            trigger = (
                "new_turn"
                if (align_to_frame is not None and align_to_frame.is_new_turn_start())
                else "natural"
            )
            self._trace.instant(
                "buffers",
                "swap",
                args={
                    "prev_id": prev_id,
                    "new_id": new_buffer.buffer_id,
                    "prev_remnant_b": prev_remnant,
                    "new_b": len(new_buffer.bytes_),
                    "queue_len": len(self._audio_buffers),
                    "trigger": trigger,
                },
            )

        # Line the new buffer's read head up with the audio the server's first
        # new-turn frame was generated from. No-op when they already match.
        if self._settings.align_audio_on_swap and align_to_frame is not None:
            self._align_current_buffer_to_frame(align_to_frame)

        self._audio_chunks_emitted = 0
        self._video_frames_emitted = 0
        await self._maybe_emit_started_speaking()

    def _align_current_buffer_to_frame(self, align_to_frame: "VideoFrame") -> None:
        """Align the current buffer's head to the new turn's first server frame.

        Drops leading 40 ms frames from the current buffer so its head lines up
        with the audio that frame represents. The server can drop leading speech
        of the new turn (e.g. the post-fade SPEECH-drop window), so the first
        video frame we receive can correspond to audio further into the buffer
        than byte 0. We recover that offset by
        matching the bundled audio of the first server frame(s) against
        successive 40 ms windows of the buffer using an amplitude-envelope
        signature (RMS per frame) — robust to the server (16 kHz) vs buffer
        (TTS rate) sample-rate + resample differences, since RMS is amplitude-
        domain and rate-independent. Conservative: trims only on a confident,
        non-zero match, so the steady-state (offset 0) case is untouched.
        """
        buf = self._current_buffer
        if buf is None or not align_to_frame.audio_bytes:
            return
        if align_to_frame.is_silence() or align_to_frame.is_fade_out():
            return

        # Anchor sequence: the swap-triggering frame + the leading new-turn
        # speech frames already buffered. More anchors → a unique match.
        anchors_src = [align_to_frame] + [f for f in list(self._video_frames) if not f.is_silence()]
        anchor_rms: list[float] = []
        for f in anchors_src[:_ALIGN_ANCHOR_FRAMES]:
            r = _rms_int16(f.audio_bytes)
            if r is None:
                break
            anchor_rms.append(r)
        if not anchor_rms or max(anchor_rms) < _ALIGN_MIN_RMS:
            return  # nothing to anchor on (silence / empty)

        # Buffer is int16 at its own sample rate; one 40 ms frame == one tick.
        buf_frame_bytes = int(buf.sample_rate * self._frame_duration) * buf.num_channels * 2
        if buf_frame_bytes <= 0:
            return
        max_d = min(
            self._settings.align_audio_max_frames,
            len(buf.bytes_) // buf_frame_bytes - len(anchor_rms),
        )
        if max_d <= 0:
            return

        def window_err(d: int) -> Optional[float]:
            err = 0.0
            for j, a in enumerate(anchor_rms):
                start = (d + j) * buf_frame_bytes
                r = _rms_int16(bytes(buf.bytes_[start : start + buf_frame_bytes]))
                if r is None:
                    return None
                err += (r - a) * (r - a)
            return err / len(anchor_rms)

        base_err = window_err(0)
        if base_err is None:
            return
        best_d, best_err = 0, base_err
        for d in range(1, max_d + 1):
            e = window_err(d)
            if e is None:
                break
            if e < best_err:
                best_d, best_err = d, e

        # Trim only on a confident, better-than-head match. Tolerance scales
        # with the anchor energy so it works at any volume.
        tol = (_ALIGN_REL_TOL * (sum(anchor_rms) / len(anchor_rms))) ** 2
        if best_d > 0 and best_err <= tol and best_err < base_err:
            trim = best_d * buf_frame_bytes
            del buf.bytes_[:trim]
            logger.info(
                f"swap audio-align: trimmed {best_d} leading frame(s) "
                f"({trim}B) from buffer #{buf.buffer_id} to match the server's "
                f"first new-turn frame (head_err={base_err:.0f} → {best_err:.0f})"
            )
            if self._trace is not None:
                self._trace.instant(
                    "lipsync",
                    "swap_align_trim",
                    args={
                        "trim_frames": best_d,
                        "trim_ms": round(best_d * self._frame_duration * 1000, 1),
                        "buffer_id": buf.buffer_id,
                        "head_err": round(base_err, 1),
                        "best_err": round(best_err, 1),
                    },
                )

    # ------------------------------------------------------------------
    # Playback loop — audio-as-clock, no state machine
    # ------------------------------------------------------------------

    async def _video_playback_loop(self) -> None:
        """Audio-as-clock playback loop.

        Each 40 ms tick:
          1. If paused, wait for resume.
          2. Sleep + spin-lock until the next tick boundary.
          3. Pop one video frame (if any). On ``frame_idx == 3``, swap to
             the next audio buffer BEFORE draining audio this tick.
          4. Drain one chunk from the current buffer (regardless of
             video pop — audio is the clock).
          5. Emit OutputAudioRawFrame (real audio if buffer present and
             not interrupted, silence otherwise) + OutputImageRawFrame.
        """
        logger.info("Starting v3 playback loop")

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

        tick_count = 0
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
            tick_count += 1

            # Pop a video frame (if any).
            # Two swap triggers, both fire BEFORE we drain audio this tick
            # so the popped frame pairs with the new buffer's first chunk:
            #
            #   (1) frame_idx == 3 — cancel-armed boundary from the server.
            #       Deterministic. The ONLY swap trigger when the current
            #       buffer is interrupted (post-cancel fadeout in progress).
            #
            #   (2) Natural turn end — local detection. When the current
            #       buffer has drained AND a new buffer is queued AND the
            #       popped frame is a SPEECH frame (idx=1), the new turn
            #       has started arriving from the server. Swap.
            #
            # (2) is gated on `not interrupted`. During a cancel-driven
            # fadeout the current buffer's bytes drain ahead of the server's
            # fade/silence frames; without the guard, a stale in-flight
            # SPEECH frame from the OLD turn could pop while current is
            # empty, triggering a premature swap. For cancel boundaries
            # we rely exclusively on (1) — frame_idx=3 from the server.
            video_frame: Optional[VideoFrame] = None
            swapped = False
            if self._video_frames:
                video_frame = self._video_frames.popleft()
                if video_frame.is_new_turn_start():
                    await self._swap_to_next_buffer(align_to_frame=video_frame)
                    swapped = True
                elif (
                    not video_frame.is_silence()
                    and not video_frame.is_fade_out()
                    and self._audio_buffers
                    and (
                        self._current_buffer is None
                        or (
                            not self._current_buffer.interrupted
                            and len(self._current_buffer.bytes_) == 0
                        )
                    )
                ):
                    logger.info(
                        f"Natural turn end detected: current buffer "
                        f"#{self._current_buffer.buffer_id if self._current_buffer else 'None'} "
                        f"drained, popped SPEECH frame, "
                        f"queue has {len(self._audio_buffers)} buffer(s) — swapping"
                    )
                    await self._swap_to_next_buffer(align_to_frame=video_frame)
                    swapped = True

            # Audio drain: gated on _current_buffer existence only.
            # Audio is emitted as silence if the buffer is interrupted
            # (fadeout audio-cut). The bytes are still consumed so the
            # buffer drains in time with the audio clock.
            audio_frame: Optional[OutputAudioRawFrame] = None
            drained_chunk: Optional[bytes] = None
            if self._current_buffer is not None:
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
                chunk: Optional[bytes]
                if len(buf) >= chunk_size:
                    chunk = bytes(buf[:chunk_size])
                    del buf[:chunk_size]
                elif len(buf) > 0:
                    chunk = bytes(buf)
                    buf.clear()
                else:
                    # Underrun on a non-interrupted buffer mid-turn —
                    # upstream TTS hasn't caught up. Emit silence; the
                    # buffer will be extended by the next TTSAudioRawFrame.
                    # logger.warning(
                    #     f"[UNDERRUN] current buffer #{self._current_buffer.buffer_id} "
                    #     f"empty (interrupted={self._current_buffer.interrupted}) — emitting silence"
                    # )
                    chunk = None

                drained_chunk = chunk

                if chunk is not None and not self._current_buffer.interrupted:
                    audio_frame = OutputAudioRawFrame(
                        audio=chunk,
                        sample_rate=self._current_buffer.sample_rate,
                        num_channels=self._current_buffer.num_channels,
                    )
                    audio_frame.pts = pts

            # Lip-sync verification trace (opt-in). Record the pairing of the
            # displayed frame with the audio drained this tick, so a post-swap
            # desync between "what we show" and "what we play" is measurable.
            if self._settings.lipsync_trace_enabled and video_frame is not None:
                self._lipsync_trace.append(
                    LipsyncTraceEntry(
                        tick=tick_count,
                        frame_idx=video_frame.frame_idx,
                        swapped=swapped,
                        current_buffer_id=(
                            self._current_buffer.buffer_id
                            if self._current_buffer is not None
                            else None
                        ),
                        interrupted=(
                            self._current_buffer.interrupted
                            if self._current_buffer is not None
                            else False
                        ),
                        frame_audio_bytes=video_frame.audio_bytes,
                        output_audio_bytes=drained_chunk,
                    )
                )

            # Perfetto session trace: per-tick audio/video events + counters.
            tr = self._trace
            if tr is not None:
                if video_frame is not None:
                    tr.instant(
                        play_lane_for_idx(video_frame.frame_idx),
                        "video_emit",
                        cat=str(video_frame.frame_idx),
                        args={"frame_idx": video_frame.frame_idx, "swapped": swapped},
                    )
                    now_us = tr.now_us()
                    self._tr_emit_times.append(now_us)
                    while self._tr_emit_times and now_us - self._tr_emit_times[0] > 1_000_000:
                        self._tr_emit_times.popleft()

                    # First speech video frame of the turn played downstream —
                    # the recv latency plus bot-side buffering/playback delay.
                    if (
                        self._awaiting_first_played_video
                        and self._tr_first_tts_audio_at is not None
                        and not video_frame.is_silence()
                        and not video_frame.is_fade_out()
                    ):
                        self._awaiting_first_played_video = False
                        latency_ms = tr.record_response_latency(
                            "played",
                            self._tr_first_tts_audio_at,
                            args={"frame_idx": video_frame.frame_idx},
                        )
                        logger.info(
                            f"📹 First speech video frame played {latency_ms}ms "
                            f"after first TTS audio (frame_idx={video_frame.frame_idx})"
                        )
                elif self._last_played_image_bytes is not None:
                    tr.instant("play:repeat", "video_repeat")

                interrupted = (
                    self._current_buffer.interrupted if self._current_buffer is not None else False
                )
                if audio_frame is not None:
                    audio_kind = "real"
                elif drained_chunk is not None and interrupted:
                    audio_kind = "silenced"
                elif self._current_buffer is not None and drained_chunk is None:
                    audio_kind = "underrun"
                    self._tr_underruns += 1
                else:
                    audio_kind = "silence"
                tr.instant(
                    "play_audio",
                    "audio_emit",
                    cat=audio_kind,
                    args={"kind": audio_kind, "bytes": len(drained_chunk or b"")},
                )

                cur_ms = 0.0
                cb = self._current_buffer
                if cb is not None and cb.sample_rate:
                    cur_ms = len(cb.bytes_) / (cb.sample_rate * cb.num_channels * 2) * 1000.0
                tr.counter("current_buffer_ms", round(cur_ms, 1))
                tr.counter("queued_buffers", len(self._audio_buffers))
                tr.counter("pending_video_frames", len(self._video_frames))
                tr.counter("playback_fps", len(self._tr_emit_times))
                tr.counter("audio_underruns_total", self._tr_underruns)
                # Lip-sync envelope — the closest thing to a live offset without
                # tagged audio: the played-audio RMS should track the shown
                # frame's bundled-audio RMS. Divergence = drift.
                if video_frame is not None and drained_chunk:
                    fa = _rms_int16(video_frame.audio_bytes)
                    oa = _rms_int16(drained_chunk)
                    if fa is not None:
                        tr.counter("frame_audio_rms", round(fa, 1))
                    if oa is not None:
                        tr.counter("output_audio_rms", round(oa, 1))

            # Push frames downstream.
            if video_frame is not None:
                self._last_played_image_bytes = video_frame.image_bytes
                out_image = await self._prepare_video_frame(video_frame.image_bytes, pts)
                if out_image is not None:
                    await self.push_frame(out_image)
                    self._video_frames_emitted += 1

            elif self._last_played_image_bytes is not None:
                # No new frame — repeat the last one to keep the video flowing.
                out_image = await self._prepare_video_frame(self._last_played_image_bytes, pts)
                if out_image is not None:
                    await self.push_frame(out_image)
                    self._video_frames_emitted += 1

            await self.push_frame(audio_frame or silence_audio)
            self._audio_chunks_emitted += 1

            # Edge detection for the started/stopped-speaking signals.
            await self._maybe_emit_started_speaking()
            await self._maybe_emit_stopped_speaking()

    # ------------------------------------------------------------------
    # Started/Stopped speaking signalling — derived from buffer state
    # ------------------------------------------------------------------

    def _is_currently_speaking(self) -> bool:
        return (
            self._current_buffer is not None
            and not self._current_buffer.interrupted
            and len(self._current_buffer.bytes_) > 0
        )

    async def _maybe_emit_started_speaking(self) -> None:
        if self._is_currently_speaking() and not self._was_speaking_emitted:
            self._was_speaking_emitted = True
            if self._trace is not None:
                self._tr_speaking_start = self._trace.mark()
            await self.push_frame(OjinBotStartedSpeakingFrame())
            await self.stop_ttfb_metrics()

    async def _maybe_emit_stopped_speaking(self) -> None:
        if not self._is_currently_speaking() and self._was_speaking_emitted:
            self._was_speaking_emitted = False
            if self._trace is not None and self._tr_speaking_start is not None:
                self._trace.span(
                    "speaking",
                    "bot_speaking",
                    self._tr_speaking_start,
                    args={
                        "buffer_id": (
                            self._current_buffer.buffer_id
                            if self._current_buffer is not None
                            else None
                        )
                    },
                )
                self._tr_speaking_start = None
            await self.push_frame(OjinBotStoppedSpeakingFrame())

    # ------------------------------------------------------------------
    # Service lifecycle
    # ------------------------------------------------------------------

    async def _start(self) -> None:
        # Open the per-session Perfetto trace before connecting so the connect
        # latency itself is captured.
        if _session_trace_enabled(self._settings.session_trace_enabled):
            try:
                self._trace = OjinSessionTrace(
                    session_id=new_session_id(),
                    config_id=self._settings.config_id,
                    root_dir=self._settings.session_trace_dir,
                )
                self._tr_session_start = self._trace.mark()
                self._tr_connect_start = self._tr_session_start
            except Exception as e:  # never let tracing break the session
                logger.warning(f"session trace init failed: {e}")
                self._trace = None
        if not await self.connect_with_retry():
            return
        assert self._client is not None
        self._receive_msg_task = self.create_task(self._receive_ojin_messages())
        await self._client.start_interaction()

    def _write_session_trace(self) -> None:
        """Close open spans and flush the Perfetto trace to disk (once)."""
        tr = self._trace
        if tr is None:
            return
        self._trace = None
        try:
            if self._tr_speaking_start is not None:
                tr.span("speaking", "bot_speaking", self._tr_speaking_start)
                self._tr_speaking_start = None
            tr.span(
                "lifecycle", "session", self._tr_session_start, args={"session_id": tr.session_id}
            )
            path = tr.write()
            logger.info(f"OjinVideoService session trace written: {path}")
        except Exception as e:
            logger.warning(f"session trace write failed: {e}")

    async def _stop(self) -> None:
        self._initialized = False
        self._write_session_trace()
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
