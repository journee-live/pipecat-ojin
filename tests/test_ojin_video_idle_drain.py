"""Tests for the OjinVideoService v3 idle backlog drain.

The playback loop pops exactly one video frame per 40 ms tick — the same rate
the inference server produces them — so a backlog that accrues while playback is
paused (frames buffering during client connect) is otherwise carried for the
whole session, adding its depth as constant latency to every reply. The drain
(``_drain_idle_backlog``) shrinks the buffer back toward
``idle_buffer_target_frames`` by dropping leading *silence* frames while idle,
never touching speech/fade frames or the audio clock. See ``video.py``.
"""

import unittest
from unittest.mock import AsyncMock, MagicMock

from pipecat.services.ojin.video import (
    AudioBuffer,
    OjinVideoService,
    OjinVideoSettings,
    VideoFrame,
)


def _make_service(*, target: int = 10) -> OjinVideoService:
    client = MagicMock()
    client.send_message = AsyncMock()
    service = OjinVideoService(
        settings=OjinVideoSettings(idle_buffer_target_frames=target),
        client=client,
    )
    service._initialized = True
    return service


def _silence() -> VideoFrame:
    return VideoFrame(
        frame_type=0, image_bytes=b"\x00" * 8, audio_bytes=b"", is_final=False, volume=0
    )


def _speech() -> VideoFrame:
    return VideoFrame(
        frame_type=1, image_bytes=b"\x00" * 8, audio_bytes=b"\x01" * 1280, is_final=False, volume=100
    )


class TestIdleBacklogDrainGating(unittest.TestCase):
    def test_no_drain_when_buffer_at_or_below_target(self) -> None:
        service = _make_service(target=10)
        for _ in range(10):
            service._video_frames.append(_silence())
        self.assertEqual(service._drain_idle_backlog(_silence()), 0)
        self.assertEqual(len(service._video_frames), 10)

    def test_no_drain_when_popped_frame_is_speech(self) -> None:
        service = _make_service(target=10)
        for _ in range(50):
            service._video_frames.append(_silence())
        # We just emitted a speech frame — not idle, don't drain.
        self.assertEqual(service._drain_idle_backlog(_speech()), 0)
        self.assertEqual(len(service._video_frames), 50)

    def test_no_drain_when_popped_frame_is_none(self) -> None:
        service = _make_service(target=10)
        for _ in range(50):
            service._video_frames.append(_silence())
        self.assertEqual(service._drain_idle_backlog(None), 0)
        self.assertEqual(len(service._video_frames), 50)

    def test_no_drain_while_speech_audio_is_draining(self) -> None:
        service = _make_service(target=10)
        for _ in range(50):
            service._video_frames.append(_silence())
        # Current buffer still holds bytes → video must stay on the audio clock.
        buf = AudioBuffer()
        buf.bytes_.extend(b"\x01" * 4096)
        service._current_buffer = buf
        self.assertEqual(service._drain_idle_backlog(_silence()), 0)
        self.assertEqual(len(service._video_frames), 50)

    def test_drains_when_current_buffer_drained(self) -> None:
        service = _make_service(target=10)
        for _ in range(50):
            service._video_frames.append(_silence())
        # An empty (drained) current buffer is still idle — drain is allowed.
        service._current_buffer = AudioBuffer()  # zero bytes
        self.assertEqual(service._drain_idle_backlog(_silence()), 1)
        self.assertEqual(len(service._video_frames), 49)

    def test_target_zero_disables_drain(self) -> None:
        service = _make_service(target=0)
        for _ in range(50):
            service._video_frames.append(_silence())
        self.assertEqual(service._drain_idle_backlog(_silence()), 0)
        self.assertEqual(len(service._video_frames), 50)


class TestIdleBacklogDrainBehaviour(unittest.TestCase):
    def test_skips_one_silence_frame_when_over_target(self) -> None:
        service = _make_service(target=10)
        for _ in range(50):
            service._video_frames.append(_silence())
        self.assertEqual(service._drain_idle_backlog(_silence()), 1)
        self.assertEqual(len(service._video_frames), 49)

    def test_skips_two_when_speech_waits_behind_silence(self) -> None:
        service = _make_service(target=10)
        for _ in range(50):
            service._video_frames.append(_silence())
        service._video_frames.append(_speech())  # a reply queued behind the wall
        self.assertEqual(service._drain_idle_backlog(_silence()), 2)
        self.assertEqual(len(service._video_frames), 49)

    def test_never_drops_a_speech_frame(self) -> None:
        # Only one silence frame separates us from the queued speech; the drain
        # may take that silence but must stop at the speech frame.
        service = _make_service(target=2)
        service._video_frames.append(_silence())
        service._video_frames.append(_speech())
        service._video_frames.append(_speech())  # len 3 > target 2
        skipped = service._drain_idle_backlog(_silence())
        self.assertEqual(skipped, 1)  # the lone leading silence only
        self.assertEqual(len(service._video_frames), 2)
        self.assertTrue(all(not f.is_silence() for f in service._video_frames))

    def test_does_not_drain_below_target(self) -> None:
        service = _make_service(target=10)
        for _ in range(11):
            service._video_frames.append(_silence())
        # One frame over target → skip exactly one, landing on target.
        self.assertEqual(service._drain_idle_backlog(_silence()), 1)
        self.assertEqual(len(service._video_frames), 10)


class TestIdleBacklogDrainConvergence(unittest.TestCase):
    """A startup backlog converges to the target under steady-state idle."""

    def _run_idle(self, service: OjinVideoService, ticks: int) -> list[int]:
        """Simulate ``ticks`` idle frames: server appends one silence, the loop
        pops one, the drain runs. Returns the post-tick buffer depths."""
        depths = []
        for _ in range(ticks):
            service._video_frames.append(_silence())  # server produces a frame
            popped = service._video_frames.popleft()  # loop pops one to emit
            service._drain_idle_backlog(popped)
            depths.append(len(service._video_frames))
        return depths

    def test_backlog_converges_to_target(self) -> None:
        service = _make_service(target=10)
        for _ in range(128):  # pause-accrued backlog
            service._video_frames.append(_silence())
        depths = self._run_idle(service, 200)
        # Drains at ~1 frame/tick and then holds steady at the target.
        self.assertLessEqual(depths[-1], 10)
        self.assertEqual(depths[-1], 10)
        # ~118 ticks to drain 128→10; comfortably inside 130.
        self.assertTrue(
            any(d <= 10 for d in depths[:130]), f"did not reach target in 130 ticks: {depths[-1]}"
        )

    def test_steady_state_holds_at_target(self) -> None:
        service = _make_service(target=10)
        for _ in range(10):
            service._video_frames.append(_silence())
        depths = self._run_idle(service, 50)
        self.assertTrue(all(d == 10 for d in depths), f"buffer drifted off target: {set(depths)}")


if __name__ == "__main__":
    unittest.main()
