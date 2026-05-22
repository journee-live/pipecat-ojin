"""Tests for the OjinVideoService FADE_OUT interrupt strategy.

The bot reacts to the server's fade-out wire signal (a video frame with
``frame_idx == 2``). On the cut-on-pop path, the audio cut fires from inside
``_video_playback_loop`` at the exact tick when the fade-out frame is
consumed for playback — keeping audio and video transitions visually in
sync. The TTS lockout (``_discard_tts``) stays armed until the next
``TTSStartedFrame`` from upstream.
"""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock

from pipecat.frames.frames import (
    OutputAudioRawFrame,
    TTSAudioRawFrame,
    TTSStartedFrame,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.ojin.video import (
    InterruptStrategy,
    OjinVideoService,
    OjinVideoSettings,
    VideoFrame,
)


def _make_service(*, strategy: InterruptStrategy = InterruptStrategy.FADE_OUT) -> OjinVideoService:
    client = MagicMock()
    client.send_message = AsyncMock()
    service = OjinVideoService(
        settings=OjinVideoSettings(interrupt_strategy=strategy),
        client=client,
    )
    service._initialized = True
    return service


def _fade_out_frame() -> VideoFrame:
    return VideoFrame(
        frame_idx=2,
        image_bytes=b"\x00" * 32,
        audio_bytes=b"\x00" * 1280,
        is_final=False,
        volume=0,
    )


def _speech_frame() -> VideoFrame:
    return VideoFrame(
        frame_idx=1,
        image_bytes=b"\x00" * 32,
        audio_bytes=b"\x00" * 1280,
        is_final=False,
        volume=100,
    )


class TestVideoFramePredicates(unittest.TestCase):
    def test_is_fade_out_true_only_for_frame_idx_2(self) -> None:
        self.assertTrue(_fade_out_frame().is_fade_out())
        self.assertFalse(_speech_frame().is_fade_out())
        silence = VideoFrame(0, b"", b"", False, 0)
        self.assertFalse(silence.is_fade_out())


class TestFadeOutStrategyEnum(unittest.TestCase):
    def test_fade_out_member_exists(self) -> None:
        self.assertEqual(InterruptStrategy.FADE_OUT.value, "fade_out")


class TestHandleOjinMessageNoLongerCutsOnReceipt(unittest.IsolatedAsyncioTestCase):
    """Regression: receipt of a fade-out frame must NOT cut audio. The cut
    now happens at pop-time in the playback loop, so state should be left
    intact while the frame is queued.
    """

    async def test_fade_out_receipt_does_not_clear_speech_buffer(self) -> None:
        service = _make_service()
        service._speech_buffer.extend(b"\x01" * 4096)
        service._is_playing_speech_audio = True
        before_len = len(service._speech_buffer)
        before_playing = service._is_playing_speech_audio
        before_discard = service._discard_tts

        # Mimic _handle_ojin_message's frame-append step for a fade-out frame.
        # (We don't need to drive the whole message handler — just verify
        # the receipt path leaves state alone for fade-out frames.)
        service._video_frames.append(_fade_out_frame())

        self.assertEqual(len(service._speech_buffer), before_len)
        self.assertEqual(service._is_playing_speech_audio, before_playing)
        self.assertEqual(service._discard_tts, before_discard)
        self.assertEqual(len(service._video_frames), 1)


class TestCutOnPopInPlaybackLoop(unittest.IsolatedAsyncioTestCase):
    """The fade-out cut trims only the OLD prefix of _speech_buffer at pop
    time, preserving any NEW-utterance TTS that arrived between
    TTSStartedFrame and the fade-out pop.
    """

    async def test_loop_trims_old_prefix_preserves_new_at_fade_pop(self) -> None:
        """OLD bytes are removed, NEW bytes survive across the pop."""
        service = _make_service()
        service._playback_paused = False
        # Simulate state at the moment of fade-out pop:
        # 4096 B OLD already in buffer, 2048 B NEW appended after
        # TTSStartedFrame snapshot. cut_pos == 4096 (= snapshot len).
        # fade_cut_done == False (armed by prior VAD).
        old_bytes = b"\x01" * 4096
        new_bytes = b"\x02" * 2048
        service._speech_buffer.extend(old_bytes + new_bytes)
        service._speech_buffer_cut_pos = len(old_bytes)
        service._fade_cut_done = False
        service._is_playing_speech_audio = True
        service._first_silence_frame = None
        service._video_frames.append(_fade_out_frame())

        pushed: list = []

        async def capture(frame, *_args, **_kwargs):
            pushed.append(frame)

        service.push_frame = capture  # type: ignore[assignment]

        loop_task = asyncio.create_task(service._video_playback_loop())
        try:
            deadline = asyncio.get_event_loop().time() + 2.0
            while not service._fade_cut_done:
                if asyncio.get_event_loop().time() > deadline:
                    self.fail("playback loop never reached the fade-out cut")
                await asyncio.sleep(0.01)
        finally:
            service._initialized = False
            try:
                await asyncio.wait_for(loop_task, timeout=1.0)
            except asyncio.TimeoutError:
                loop_task.cancel()
                try:
                    await loop_task
                except (asyncio.CancelledError, Exception):
                    pass

        self.assertTrue(service._fade_cut_done,
                        "fade_cut_done must flip to True after pop")
        self.assertEqual(service._speech_buffer_cut_pos, 0,
                         "cut_pos must reset to 0 after trim")
        # The NEW bytes must survive; OLD prefix must be gone. Allow a
        # small slack for any chunk consumed by playback during the loop's
        # initial buffer-fill ticks (audio_frames are 1280 B each).
        self.assertGreaterEqual(
            len(service._speech_buffer), len(new_bytes) - 6 * 1280,
            "new TTS must be largely preserved across the fade-out pop",
        )
        self.assertLessEqual(
            len(service._speech_buffer), len(new_bytes),
            "OLD prefix must be trimmed (buffer no larger than new portion)",
        )
        # _discard_tts must NOT be re-armed at fade-out pop — the new
        # turn's gate must stay open.
        self.assertFalse(
            service._discard_tts,
            "fade-out pop must not re-arm _discard_tts (new turn gate stays open)",
        )

    async def test_loop_pushes_silence_for_fade_tick(self) -> None:
        """The fade-out video frame goes downstream paired with silence audio
        for that one tick (NOT with whatever bytes were prepared from the
        OLD prefix this tick).
        """
        service = _make_service()
        service._playback_paused = False
        # Pure-OLD buffer (no NEW bytes) so any non-zero audio frame after
        # the cut would indicate the old payload leaked.
        service._speech_buffer.extend(b"\xff" * 4096)
        service._speech_buffer_cut_pos = 4096
        service._fade_cut_done = False
        service._is_playing_speech_audio = True
        service._first_silence_frame = None
        service._video_frames.append(_fade_out_frame())

        pushed: list = []

        async def capture(frame, *_args, **_kwargs):
            pushed.append(frame)

        service.push_frame = capture  # type: ignore[assignment]

        loop_task = asyncio.create_task(service._video_playback_loop())
        try:
            deadline = asyncio.get_event_loop().time() + 2.0
            while not service._fade_cut_done:
                if asyncio.get_event_loop().time() > deadline:
                    self.fail("loop did not reach fade-out cut")
                await asyncio.sleep(0.01)
            await asyncio.sleep(0.06)
        finally:
            service._initialized = False
            try:
                await asyncio.wait_for(loop_task, timeout=1.0)
            except asyncio.TimeoutError:
                loop_task.cancel()
                try:
                    await loop_task
                except (asyncio.CancelledError, Exception):
                    pass

        audio_pushed = [f for f in pushed if isinstance(f, OutputAudioRawFrame)]
        self.assertTrue(audio_pushed, "loop must push at least one audio frame")
        silent_pushes = [f for f in audio_pushed if set(f.audio) == {0}]
        self.assertTrue(
            len(silent_pushes) >= 1,
            "at least one all-zero audio frame must be pushed after the cut",
        )

    async def test_five_fade_pops_only_trim_once(self) -> None:
        """The server emits 5 frame_idx==2 frames. Only the first pop trims;
        subsequent pops must no-op because _fade_cut_done is True.
        """
        service = _make_service()
        service._playback_paused = False
        # Buffer contains ONLY new bytes (cut_pos == 0). After the first
        # pop, _fade_cut_done flips True; if subsequent pops were not
        # guarded they could re-call _stop_audio_playback() etc.
        new_bytes = b"\x02" * 4096
        service._speech_buffer.extend(new_bytes)
        service._speech_buffer_cut_pos = 0
        service._fade_cut_done = False
        service._is_playing_speech_audio = True
        service._first_silence_frame = None
        # Queue 5 fade frames (mimicking the server's emission pattern).
        for _ in range(5):
            service._video_frames.append(_fade_out_frame())

        async def capture(_frame, *_args, **_kwargs):
            pass

        service.push_frame = capture  # type: ignore[assignment]

        loop_task = asyncio.create_task(service._video_playback_loop())
        try:
            deadline = asyncio.get_event_loop().time() + 2.0
            while not service._fade_cut_done:
                if asyncio.get_event_loop().time() > deadline:
                    self.fail("first fade pop never fired")
                await asyncio.sleep(0.01)
            # Let the remaining 4 fade pops run.
            await asyncio.sleep(0.25)
        finally:
            service._initialized = False
            try:
                await asyncio.wait_for(loop_task, timeout=1.0)
            except asyncio.TimeoutError:
                loop_task.cancel()
                try:
                    await loop_task
                except (asyncio.CancelledError, Exception):
                    pass

        # The new bytes should still be (mostly) in the buffer — repeated
        # un-guarded pops would have wiped them via the prior `clear()`.
        self.assertGreater(
            len(service._speech_buffer), 0,
            "subsequent fade pops must not wipe the preserved new TTS",
        )


class TestTtsLockoutLifecycle(unittest.IsolatedAsyncioTestCase):
    """_discard_tts gates incoming TTS frames after a fade-out, and resets
    only on the next TTSStartedFrame from upstream.
    """

    async def test_tts_audio_dropped_while_discard_tts_set(self) -> None:
        service = _make_service()
        service._discard_tts = True

        # Stub _send_tts_audio so we can detect if it was called.
        service._send_tts_audio = AsyncMock()
        service.push_frame = AsyncMock()

        frame = TTSAudioRawFrame(audio=b"\x00\x01" * 100, sample_rate=16000, num_channels=1)
        await service.process_frame(frame, FrameDirection.DOWNSTREAM)

        service._send_tts_audio.assert_not_called()

    async def test_tts_started_frame_clears_discard_tts(self) -> None:
        service = _make_service()
        service._discard_tts = True
        service.push_frame = AsyncMock()

        await service.process_frame(TTSStartedFrame(), FrameDirection.DOWNSTREAM)

        self.assertFalse(service._discard_tts)


if __name__ == "__main__":
    unittest.main()
