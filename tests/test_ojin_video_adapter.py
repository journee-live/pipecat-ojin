"""Tests for the thin ``OjinVideoService`` adapter over ``OjinSTVClient``.

The adapter only (a) translates pipecat frames into ``OjinSTVClient`` calls,
(b) implements the ``STVOutput`` sink (pushing ``Output*RawFrame`` downstream)
behind the playback-start gate, and (c) maps client events to the pipecat
frames + TTFB metrics the bot expects. All avatar behavior (sync engine,
JPEG decode, audio fade, idle drain, tracing) lives in ``ojin.stv`` and is
unit-tested in ``services/tests/stv``; those concerns are intentionally absent
here.
"""

import os
import unittest
from unittest.mock import AsyncMock, patch

from ojin.stv import STVAudioFrame, STVConfig, STVEvent, STVVideoFrame
from ojin.stv.events import EventEmitter

from pipecat.frames.frames import (
    CancelFrame,
    EndFrame,
    OutputAudioRawFrame,
    OutputImageRawFrame,
    TTSAudioRawFrame,
    TTSStartedFrame,
    UserStartedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.ojin.video import (
    OjinBotStartedSpeakingFrame,
    OjinBotStoppedSpeakingFrame,
    OjinVideoInitializedFrame,
    OjinVideoService,
    OjinVideoSettings,
    _config_from,
)
from pipecat.tests.utils import run_test


class FakeSTVClient:
    """Stand-in for ``OjinSTVClient``.

    Records adapter→client calls and uses the *real* ``EventEmitter`` so the
    adapter's event wiring is exercised against production dispatch logic
    (handlers registered via ``on``/``add_listener`` and fired via ``emit``).
    """

    def __init__(self) -> None:
        self._events = EventEmitter()
        self.calls: list = []
        self.connect_return = True

    # --- event registration the adapter uses in _wire_events ---
    def on(self, event):
        return self._events.on(event)

    def add_listener(self, event, cb) -> None:
        self._events.add_listener(event, cb)

    async def emit(self, event, **kwargs) -> None:
        await self._events.emit(event, **kwargs)

    # --- delegated calls the adapter makes from process_frame ---
    async def start(self) -> None:
        self.calls.append("start")

    async def start_turn(self) -> None:
        self.calls.append("start_turn")

    async def send_tts_audio(self, pcm, sample_rate, num_channels) -> None:
        self.calls.append(("send_tts_audio", pcm, sample_rate, num_channels))

    async def interrupt(self) -> None:
        self.calls.append("interrupt")

    async def close(self) -> None:
        self.calls.append("close")

    async def connect_with_retry(self) -> bool:
        self.calls.append("connect_with_retry")
        return self.connect_return


def _audio() -> TTSAudioRawFrame:
    return TTSAudioRawFrame(audio=b"\x01\x00" * 160, sample_rate=24000, num_channels=1)


def _silence() -> TTSAudioRawFrame:
    # 0.5 s of all-zero PCM @ 24 kHz mono int16 == the client's trailing-silence
    # sentinel (24000 samples * 2 bytes = 24000 bytes ⇒ 0.5 s). The client discards
    # it, so the adapter must not arm TTFB / send / pass it through.
    return TTSAudioRawFrame(audio=b"\x00" * 24000, sample_rate=24000, num_channels=1)


def _adapter(fake: FakeSTVClient, **settings_kw) -> OjinVideoService:
    return OjinVideoService(OjinVideoSettings(**settings_kw), stv_client=fake)


class TestConfigMapping(unittest.TestCase):
    """``_config_from`` maps the behavioral settings onto ``STVConfig``."""

    def test_behavioral_settings_map_to_stvconfig(self) -> None:
        settings = OjinVideoSettings(
            image_size=(640, 480),
            client_connect_max_retries=7,
            client_reconnect_delay=1.5,
            max_buffered_video_frames=123,
            idle_buffer_target_frames=9,
            align_audio_on_swap=False,
            align_audio_max_frames=11,
            interrupt_audio_fade_s=0.33,
            lipsync_trace_enabled=True,
        )
        cfg = _config_from(settings)
        self.assertIsInstance(cfg, STVConfig)
        self.assertEqual(cfg.image_size, (640, 480))
        self.assertEqual(cfg.client_connect_max_retries, 7)
        self.assertEqual(cfg.client_reconnect_delay, 1.5)
        self.assertEqual(cfg.max_buffered_video_frames, 123)
        self.assertEqual(cfg.idle_buffer_target_frames, 9)
        self.assertFalse(cfg.align_audio_on_swap)
        self.assertEqual(cfg.align_audio_max_frames, 11)
        self.assertEqual(cfg.interrupt_audio_fade_s, 0.33)
        self.assertTrue(cfg.lipsync_trace_enabled)

    def test_diagnostics_env_vars_override_stvconfig(self) -> None:
        # Preserve the old video.py operator escape hatches for watchdog tuning.
        with patch.dict(
            os.environ,
            {
                "OJIN_TICK_WARN_MS": "123",
                "OJIN_STALL_PROBE_MS": "45",
                "OJIN_LOOP_STALL_WATCHDOG_MS": "999",
            },
        ):
            cfg = _config_from(OjinVideoSettings())
        self.assertEqual(cfg.tick_warn_ms, 123.0)
        self.assertEqual(cfg.stall_probe_ms, 45.0)
        self.assertEqual(cfg.loop_stall_watchdog_ms, 999.0)

    def test_diagnostics_defaults_when_env_absent(self) -> None:
        for key in ("OJIN_LOOP_STALL_WATCHDOG_MS", "OJIN_TICK_WARN_MS", "OJIN_STALL_PROBE_MS"):
            self.assertNotIn(key, os.environ)  # guard: ambient env is clean
        cfg = _config_from(OjinVideoSettings())
        default = STVConfig()
        self.assertEqual(cfg.tick_warn_ms, default.tick_warn_ms)
        self.assertEqual(cfg.stall_probe_ms, default.stall_probe_ms)
        self.assertEqual(cfg.loop_stall_watchdog_ms, default.loop_stall_watchdog_ms)


class TestPlaybackGate(unittest.IsolatedAsyncioTestCase):
    """The gate lives in the adapter; the client always produces, the adapter drops."""

    async def test_gated_by_default_drops_audio_and_video(self) -> None:
        svc = _adapter(FakeSTVClient())
        svc.push_frame = AsyncMock()
        await svc._output.write_audio(
            STVAudioFrame(pcm=b"\x01\x00", sample_rate=24000, num_channels=1, pts=0)
        )
        await svc._output.write_video(
            STVVideoFrame(rgb=b"rgb", source_bytes=b"jpg", width=4, height=4, frame_type=1, pts=0)
        )
        svc.push_frame.assert_not_called()

    async def test_enabled_forwards_audio_and_video(self) -> None:
        svc = _adapter(FakeSTVClient())
        svc.push_frame = AsyncMock()
        svc.set_can_start_playback(True)
        await svc._output.write_audio(
            STVAudioFrame(pcm=b"\x02\x00", sample_rate=24000, num_channels=1, pts=0)
        )
        await svc._output.write_video(
            STVVideoFrame(
                rgb=b"rgbrgb", source_bytes=b"jpg", width=1, height=2, frame_type=1, pts=0
            )
        )
        pushed = [c.args[0] for c in svc.push_frame.call_args_list]
        audio = [f for f in pushed if isinstance(f, OutputAudioRawFrame)]
        image = [f for f in pushed if isinstance(f, OutputImageRawFrame)]
        self.assertEqual(len(audio), 1)
        self.assertEqual(audio[0].audio, b"\x02\x00")
        self.assertEqual(audio[0].sample_rate, 24000)
        self.assertEqual(audio[0].num_channels, 1)
        self.assertEqual(len(image), 1)
        self.assertEqual(image[0].image, b"rgbrgb")
        self.assertEqual(image[0].size, (1, 2))
        self.assertEqual(image[0].format, "RGB")

    async def test_enabled_but_no_rgb_drops_video(self) -> None:
        svc = _adapter(FakeSTVClient())
        svc.push_frame = AsyncMock()
        svc.set_can_start_playback(True)
        await svc._output.write_video(
            STVVideoFrame(rgb=None, source_bytes=b"jpg", width=1, height=1, frame_type=0, pts=0)
        )
        svc.push_frame.assert_not_called()


class TestEventToFrameMapping(unittest.IsolatedAsyncioTestCase):
    """Client lifecycle events map to the pipecat frames + TTFB the bot expects."""

    def _wired(self):
        fake = FakeSTVClient()
        svc = _adapter(fake)
        svc.push_frame = AsyncMock()
        svc.push_error = AsyncMock()
        svc.start_ttfb_metrics = AsyncMock()
        svc.stop_ttfb_metrics = AsyncMock()
        return fake, svc

    async def test_session_ready_pushes_initialized_frame_both_directions(self) -> None:
        fake, svc = self._wired()
        await fake.emit(STVEvent.SESSION_READY, session_data={"foo": 1})
        init = [
            c
            for c in svc.push_frame.call_args_list
            if isinstance(c.args[0], OjinVideoInitializedFrame)
        ]
        self.assertEqual(len(init), 2)
        self.assertEqual(init[0].args[0].session_data, {"foo": 1})
        dirs = {c.args[1] for c in init}
        self.assertEqual(dirs, {FrameDirection.DOWNSTREAM, FrameDirection.UPSTREAM})

    async def test_started_speaking_emits_frame_and_stops_ttfb(self) -> None:
        fake, svc = self._wired()
        await fake.emit(STVEvent.BOT_STARTED_SPEAKING)
        pushed = [type(c.args[0]) for c in svc.push_frame.call_args_list]
        self.assertIn(OjinBotStartedSpeakingFrame, pushed)
        svc.stop_ttfb_metrics.assert_awaited_once()

    async def test_stopped_speaking_emits_frame(self) -> None:
        fake, svc = self._wired()
        await fake.emit(STVEvent.BOT_STOPPED_SPEAKING)
        pushed = [type(c.args[0]) for c in svc.push_frame.call_args_list]
        self.assertIn(OjinBotStoppedSpeakingFrame, pushed)

    async def test_error_event_pushes_error_with_message_and_fatal(self) -> None:
        fake, svc = self._wired()
        # server-error path carries an extra ``code`` kwarg the adapter must tolerate
        await fake.emit(STVEvent.ERROR, message="boom", code="X", fatal=True)
        svc.push_error.assert_awaited_once()
        call = svc.push_error.call_args
        self.assertEqual(call.args[0], "boom")
        self.assertTrue(call.kwargs.get("fatal"))

    async def test_error_event_without_code_kwarg(self) -> None:
        # The connect-failure path emits ERROR with only message/fatal (no code).
        fake, svc = self._wired()
        await fake.emit(STVEvent.ERROR, message="connect failed", fatal=True)
        svc.push_error.assert_awaited_once()
        self.assertEqual(svc.push_error.call_args.args[0], "connect failed")


class TestFrameRouting(unittest.IsolatedAsyncioTestCase):
    """Inbound pipecat frames route to the right client calls (mid-stream frames)."""

    def _svc(self, **kw):
        fake = FakeSTVClient()
        svc = _adapter(fake, **kw)
        svc.push_frame = AsyncMock()
        svc.start_ttfb_metrics = AsyncMock()
        return fake, svc

    async def test_tts_started_opens_turn(self) -> None:
        fake, svc = self._svc()
        await svc.process_frame(TTSStartedFrame(), FrameDirection.DOWNSTREAM)
        self.assertIn("start_turn", fake.calls)

    async def test_tts_audio_sends_to_client_and_arms_ttfb_once(self) -> None:
        fake, svc = self._svc()
        await svc.process_frame(TTSStartedFrame(), FrameDirection.DOWNSTREAM)
        first = _audio()
        await svc.process_frame(first, FrameDirection.DOWNSTREAM)
        await svc.process_frame(_audio(), FrameDirection.DOWNSTREAM)
        sends = [c for c in fake.calls if isinstance(c, tuple) and c[0] == "send_tts_audio"]
        self.assertEqual(len(sends), 2)
        self.assertEqual(
            sends[0], ("send_tts_audio", first.audio, first.sample_rate, first.num_channels)
        )
        svc.start_ttfb_metrics.assert_awaited_once()

    async def test_tts_audio_passthrough_pushes_downstream_when_enabled(self) -> None:
        fake, svc = self._svc(tts_audio_passthrough=True)
        frame = _audio()
        await svc.process_frame(frame, FrameDirection.DOWNSTREAM)
        pushed = [c.args[0] for c in svc.push_frame.call_args_list]
        self.assertIn(frame, pushed)

    async def test_tts_audio_not_pushed_when_passthrough_disabled(self) -> None:
        fake, svc = self._svc(tts_audio_passthrough=False)
        frame = _audio()
        await svc.process_frame(frame, FrameDirection.DOWNSTREAM)
        pushed = [c.args[0] for c in svc.push_frame.call_args_list]
        self.assertNotIn(frame, pushed)

    async def test_user_started_speaking_interrupts(self) -> None:
        fake, svc = self._svc()
        await svc.process_frame(UserStartedSpeakingFrame(), FrameDirection.DOWNSTREAM)
        self.assertIn("interrupt", fake.calls)

    async def test_end_frame_closes_client(self) -> None:
        fake, svc = self._svc()
        await svc.process_frame(EndFrame(), FrameDirection.DOWNSTREAM)
        self.assertIn("close", fake.calls)

    async def test_can_generate_metrics_is_true(self) -> None:
        _, svc = self._svc()
        self.assertTrue(svc.can_generate_metrics())


class TestLifecycleThroughPipeline(unittest.IsolatedAsyncioTestCase):
    """End-to-end through a real pipeline: StartFrame→start, EndFrame→close."""

    async def test_start_starts_client_and_end_closes_it(self) -> None:
        fake = FakeSTVClient()
        svc = _adapter(fake)
        await run_test(
            svc,
            frames_to_send=[],
            expected_down_frames=None,
            send_end_frame=True,
        )
        self.assertIn("start", fake.calls)
        self.assertIn("close", fake.calls)


class TestTtfbAndSilence(unittest.IsolatedAsyncioTestCase):
    """TTFB arming honours the trailing-silence sentinel and re-arms per turn."""

    def _svc(self, **kw):
        fake = FakeSTVClient()
        svc = _adapter(fake, **kw)
        svc.push_frame = AsyncMock()
        svc.start_ttfb_metrics = AsyncMock()
        return fake, svc

    async def test_trailing_silence_first_frame_is_dropped_not_armed(self) -> None:
        # The client discards the 0.5s sentinel; the adapter must not arm TTFB,
        # send it, or pass it through — exactly as the old adapter did.
        fake, svc = self._svc(tts_audio_passthrough=True)
        await svc.process_frame(TTSStartedFrame(), FrameDirection.DOWNSTREAM)
        await svc.process_frame(_silence(), FrameDirection.DOWNSTREAM)
        svc.start_ttfb_metrics.assert_not_awaited()
        self.assertNotIn("send_tts_audio", [c[0] for c in fake.calls if isinstance(c, tuple)])
        self.assertEqual(
            [c for c in svc.push_frame.call_args_list if isinstance(c.args[0], TTSAudioRawFrame)],
            [],
        )
        # the real first frame that follows still arms TTFB once
        await svc.process_frame(_audio(), FrameDirection.DOWNSTREAM)
        svc.start_ttfb_metrics.assert_awaited_once()

    async def test_ttfb_not_armed_without_a_tts_started_frame(self) -> None:
        _, svc = self._svc()
        await svc.process_frame(_audio(), FrameDirection.DOWNSTREAM)
        svc.start_ttfb_metrics.assert_not_awaited()

    async def test_ttfb_rearmed_on_each_turn(self) -> None:
        _, svc = self._svc()
        for _turn in range(2):
            await svc.process_frame(TTSStartedFrame(), FrameDirection.DOWNSTREAM)
            await svc.process_frame(_audio(), FrameDirection.DOWNSTREAM)
        self.assertEqual(svc.start_ttfb_metrics.await_count, 2)


class TestClientDelegation(unittest.IsolatedAsyncioTestCase):
    """connect_with_retry delegates to the client (preserved public surface, §5)."""

    async def test_connect_with_retry_delegates_and_returns_true(self) -> None:
        fake = FakeSTVClient()
        fake.connect_return = True
        svc = _adapter(fake)
        self.assertTrue(await svc.connect_with_retry())
        self.assertIn("connect_with_retry", fake.calls)

    async def test_connect_with_retry_propagates_false(self) -> None:
        fake = FakeSTVClient()
        fake.connect_return = False
        svc = _adapter(fake)
        self.assertFalse(await svc.connect_with_retry())


class TestFrameTransparency(unittest.IsolatedAsyncioTestCase):
    """Handled frames are still forwarded downstream; unknown frames pass through."""

    def _svc(self, **kw):
        fake = FakeSTVClient()
        svc = _adapter(fake, **kw)
        svc.push_frame = AsyncMock()
        svc.start_ttfb_metrics = AsyncMock()
        return fake, svc

    def _pushed_args(self, svc):
        return [c.args for c in svc.push_frame.call_args_list]

    async def test_tts_started_forwarded_downstream(self) -> None:
        fake, svc = self._svc()
        frame = TTSStartedFrame()
        await svc.process_frame(frame, FrameDirection.DOWNSTREAM)
        self.assertIn((frame, FrameDirection.DOWNSTREAM), self._pushed_args(svc))

    async def test_user_started_speaking_forwarded_downstream(self) -> None:
        fake, svc = self._svc()
        frame = UserStartedSpeakingFrame()
        await svc.process_frame(frame, FrameDirection.DOWNSTREAM)
        self.assertIn((frame, FrameDirection.DOWNSTREAM), self._pushed_args(svc))

    async def test_end_frame_forwarded_downstream_and_closes(self) -> None:
        fake, svc = self._svc()
        frame = EndFrame()
        await svc.process_frame(frame, FrameDirection.DOWNSTREAM)
        self.assertIn("close", fake.calls)
        self.assertIn((frame, FrameDirection.DOWNSTREAM), self._pushed_args(svc))

    async def test_cancel_frame_closes_client(self) -> None:
        fake, svc = self._svc()
        await svc.process_frame(CancelFrame(), FrameDirection.DOWNSTREAM)
        self.assertIn("close", fake.calls)

    async def test_unknown_frame_passes_through(self) -> None:
        # A plain OutputAudioRawFrame is not special-cased by the adapter or base.
        fake, svc = self._svc()
        frame = OutputAudioRawFrame(b"\x00\x00", 24000, 1)
        await svc.process_frame(frame, FrameDirection.DOWNSTREAM)
        self.assertIn((frame, FrameDirection.DOWNSTREAM), self._pushed_args(svc))


if __name__ == "__main__":
    unittest.main()
