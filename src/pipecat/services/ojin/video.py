"""OjinVideoService — thin pipecat adapter over the framework-agnostic OjinSTVClient.

All avatar behavior (connect/retry, TTS-audio buffering + playback, the
audio-as-clock 40 ms playback loop, post-interruption re-sync, idle-backlog
drain, off-loop JPEG decode, and session tracing) lives in
``ojin.stv.OjinSTVClient`` and is unit-tested in ``services/tests/stv``. This
module is a small ``FrameProcessor`` that:

1. Translates inbound pipecat frames into ``OjinSTVClient`` calls.
2. Implements the client's ``STVOutput`` sink, pushing pipecat
   ``OutputAudioRawFrame`` / ``OutputImageRawFrame`` downstream — behind the
   playback-start gate (:meth:`OjinVideoService.set_can_start_playback`).
3. Maps client events to the pipecat frames the bot expects, plus TTFB metrics.

**The gate (default closed) is the adapter's job, not the client's.** The client
never pauses — it always produces synced frames into the sink. While the gate is
closed (the connect→participant-join window) the adapter *drops* whatever the
client emits, so no idle-frame backlog enters the transport ``output_buffer``.
At join the gate opens and the live edge is forwarded with no playback warm-up to
re-arm — strictly lower join latency than the old pause/resume approach.

See ``services/docs/ojin_video_service_refactor.md``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional, Tuple, Type

from ojin.ojin_client_messages import IOjinClient
from ojin.stv import (
    OjinSTVClient,
    STVAudioFrame,
    STVConfig,
    STVEvent,
    STVVideoFrame,
)

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
from pipecat.services.ojin.session_trace import OjinSessionTrace


@dataclass
class OjinVideoInitializedFrame(Frame):
    """Frame indicating that the service has been initialized."""

    session_data: Optional[dict] = None


class OjinBotStartedSpeakingFrame(Frame):
    """Emitted when the avatar starts speaking (a buffer is promoted to current)."""

    pass


class OjinBotStoppedSpeakingFrame(Frame):
    """Emitted when the avatar stops speaking (current buffer drains, none queued)."""

    pass


@dataclass
class OjinVideoSettings:
    """Settings for :class:`OjinVideoService`.

    Connection identity plus behavioral knobs. The behavioral fields are mapped
    onto :class:`ojin.stv.STVConfig` by :func:`_config_from`; the remaining
    fields are pipecat-adapter concerns. ``started_speaking_delay_s`` /
    ``stopped_speaking_delay_s`` / ``frame_debugging_enabled`` are retained for
    call-site compatibility but are not wired to any behavior (they were unused
    in the previous implementation too).
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
    max_buffered_video_frames: int = 700
    idle_buffer_target_frames: int = 6
    lipsync_trace_enabled: bool = False
    align_audio_on_swap: bool = True
    align_audio_max_frames: int = 50
    interrupt_audio_fade_s: float = 0.75


def _config_from(settings: OjinVideoSettings) -> STVConfig:
    """Map the behavioral fields of ``OjinVideoSettings`` onto an ``STVConfig``.

    The loop-stall watchdog thresholds additionally honour the operator env-var
    escape hatches the old ``video.py`` exposed (``OJIN_LOOP_STALL_WATCHDOG_MS`` /
    ``OJIN_TICK_WARN_MS`` / ``OJIN_STALL_PROBE_MS``); when unset they fall back to
    ``STVConfig``'s defaults.
    """
    config = STVConfig(
        client_connect_max_retries=settings.client_connect_max_retries,
        client_reconnect_delay=settings.client_reconnect_delay,
        image_size=settings.image_size,
        max_buffered_video_frames=settings.max_buffered_video_frames,
        idle_buffer_target_frames=settings.idle_buffer_target_frames,
        align_audio_on_swap=settings.align_audio_on_swap,
        align_audio_max_frames=settings.align_audio_max_frames,
        interrupt_audio_fade_s=settings.interrupt_audio_fade_s,
        lipsync_trace_enabled=settings.lipsync_trace_enabled,
    )
    for env_name, attr in (
        ("OJIN_LOOP_STALL_WATCHDOG_MS", "loop_stall_watchdog_ms"),
        ("OJIN_TICK_WARN_MS", "tick_warn_ms"),
        ("OJIN_STALL_PROBE_MS", "stall_probe_ms"),
    ):
        raw = os.environ.get(env_name)
        if raw is not None:
            setattr(config, attr, float(raw))
    return config


def _is_trailing_silence(pcm: bytes, sample_rate: int, num_channels: int) -> bool:
    """True for the ~0.5 s all-zero sentinel the client discards in ``send_tts_audio``.

    Mirrors ``OjinSTVClient.send_tts_audio``'s discard so the adapter neither arms
    TTFB nor forwards a frame that will never be buffered/played — matching the old
    ``video.py``, which dropped this frame before the metrics + passthrough.
    """
    if not pcm:
        return False
    duration = len(pcm) / (sample_rate * num_channels * 2)
    return abs(duration - 0.5) < 0.01 and pcm == b"\x00" * len(pcm)


class _PushFrameOutput:
    """``STVOutput`` sink: forwards the client's frames downstream, behind the gate.

    While the gate is closed everything is dropped (no ``push_frame``), so the
    connect→join idle backlog never reaches the transport ``output_buffer``. Once
    open, the live edge is forwarded.
    """

    def __init__(self, service: "OjinVideoService") -> None:
        """Bind the sink to its owning :class:`OjinVideoService`."""
        self._svc = service

    async def write_audio(self, frame: STVAudioFrame) -> None:
        """Forward one tick of played audio downstream when the gate is open."""
        if self._svc._can_start_playback:
            await self._svc.push_frame(
                OutputAudioRawFrame(frame.pcm, frame.sample_rate, frame.num_channels)
            )

    async def write_video(self, frame: STVVideoFrame) -> None:
        """Forward one decoded avatar frame downstream when the gate is open."""
        if self._svc._can_start_playback and frame.rgb is not None:
            await self._svc.push_frame(
                OutputImageRawFrame(
                    image=frame.rgb,
                    size=(frame.width, frame.height),
                    format=frame.format,
                )
            )

    def on_event(self, event: STVEvent, **kwargs) -> None:
        """No-op: lifecycle events are handled via the client's emitter, not here."""


class OjinVideoService(FrameProcessor):
    """Thin pipecat adapter delegating all avatar behavior to :class:`OjinSTVClient`."""

    def __init__(
        self,
        settings: OjinVideoSettings,
        client: Optional[IOjinClient] = None,
        session_trace: Optional[OjinSessionTrace] = None,
        *,
        stv_client: Optional[OjinSTVClient] = None,
    ) -> None:
        """Build the adapter.

        Args:
            settings: pipecat-facing settings (identity + behavioral knobs).
            client: optional low-level ``IOjinClient`` transport, passed through
                to ``OjinSTVClient`` (defaults to a WebSocket client).
            session_trace: the bot's ``OjinSessionTrace``, injected as the
                client's tracer so the avatar and ``LatencyTracker`` share one
                trace. ``None`` → the client uses a ``NullTracer``.
            stv_client: optional pre-built client (dependency injection for tests
                or alternative transports). When provided, ``client`` and the
                settings-derived client configuration are ignored.
        """
        super().__init__(name="ojin")
        self._settings = settings
        self._start_frame_cls = settings.start_frame_cls
        self._can_start_playback = False  # gated until participant join
        self._waiting_for_first_tts = False
        self._output = _PushFrameOutput(self)
        self._stv = stv_client or OjinSTVClient(
            api_key=settings.api_key,
            config_id=settings.config_id,
            ws_url=settings.ws_url,
            output=self._output,
            resampler=create_default_resampler(),
            tracer=session_trace,
            client=client,
            config=_config_from(settings),
        )
        self._wire_events()

    def set_can_start_playback(self, value: bool) -> None:
        """Open (``True``) or close (``False``) the playback gate.

        Called ``True`` at participant-join, after the transport ``output_buffer``
        has been flushed and before the greeting is triggered. The avatar's A/V is
        dropped until this is called, keeping the connect→join idle backlog out of
        the transport.
        """
        self._can_start_playback = value

    def can_generate_metrics(self) -> bool:
        """Enable pipecat TTFB/processing metrics for this service."""
        return True

    async def connect_with_retry(self) -> bool:
        """Connect the underlying client with retry; ``True`` on success.

        Preserved from the old public surface (refactor doc §5). The client also
        connects lazily on ``StartFrame`` via ``start()``; this remains for callers
        that connect explicitly.
        """
        return await self._stv.connect_with_retry()

    def _wire_events(self) -> None:
        """Map ``OjinSTVClient`` events onto pipecat frames + TTFB metrics."""

        @self._stv.on(STVEvent.SESSION_READY)
        async def _on_ready(session_data=None, **_):
            frame = OjinVideoInitializedFrame(session_data=session_data)
            await self.push_frame(frame, FrameDirection.DOWNSTREAM)
            await self.push_frame(frame, FrameDirection.UPSTREAM)

        @self._stv.on(STVEvent.BOT_STARTED_SPEAKING)
        async def _on_started(**_):
            await self.push_frame(OjinBotStartedSpeakingFrame())
            await self.stop_ttfb_metrics()

        @self._stv.on(STVEvent.BOT_STOPPED_SPEAKING)
        async def _on_stopped(**_):
            await self.push_frame(OjinBotStoppedSpeakingFrame())

        @self._stv.on(STVEvent.ERROR)
        async def _on_error(message="", fatal=False, **_):
            await self.push_error(message, fatal=fatal)

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        """Route inbound pipecat frames to the client; stay transparent otherwise."""
        await super().process_frame(frame, direction)

        if isinstance(frame, self._start_frame_cls):
            await self.push_frame(frame, direction)
            await self._stv.start()
        elif isinstance(frame, TTSStartedFrame):
            self._waiting_for_first_tts = True
            await self._stv.start_turn()
            await self.push_frame(frame, direction)
        elif isinstance(frame, TTSAudioRawFrame):
            # The client discards the ~0.5 s trailing-silence sentinel; drop it here
            # too so TTFB anchors on audio that is actually buffered/played and the
            # sentinel is not passed through (parity with the old adapter).
            if _is_trailing_silence(frame.audio, frame.sample_rate, frame.num_channels):
                return
            if self._waiting_for_first_tts:
                self._waiting_for_first_tts = False
                await self.start_ttfb_metrics()
            await self._stv.send_tts_audio(frame.audio, frame.sample_rate, frame.num_channels)
            if self._settings.tts_audio_passthrough:
                await self.push_frame(frame, FrameDirection.DOWNSTREAM)
        elif isinstance(frame, UserStartedSpeakingFrame):
            await self._stv.interrupt()
            await self.push_frame(frame, direction)
        elif isinstance(frame, (EndFrame, CancelFrame)):
            await self._stv.close()
            await self.push_frame(frame, direction)
        else:
            await self.push_frame(frame, direction)
