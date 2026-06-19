"""Tests for off-loop JPEG→RGB frame decoding.

The playback loop must never run cv2 inline (it would block the audio clock),
so pixel decode is extracted into a pure function and run on a worker thread.
These cover the pure decoder's output shape/fallbacks and the worker's
in-order, attach-and-handoff behaviour (with a stop sentinel).
"""

import unittest
from unittest.mock import MagicMock

import cv2
import numpy as np

from pipecat.services.ojin.video import (
    OjinVideoService,
    OjinVideoSettings,
    VideoFrame,
    _decode_to_rgb,
)


def _jpeg(w: int, h: int) -> bytes:
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:, :, 1] = 200  # green-ish so BGR→RGB is observable
    ok, buf = cv2.imencode(".jpg", img)
    assert ok
    return buf.tobytes()


class TestDecodeToRgb(unittest.TestCase):
    def test_outputs_target_sized_rgb(self) -> None:
        rgb = _decode_to_rgb(_jpeg(640, 480), 256, 256)
        self.assertIsNotNone(rgb)
        self.assertEqual(len(rgb), 256 * 256 * 3)  # type: ignore[arg-type]

    def test_empty_input_returns_none(self) -> None:
        self.assertIsNone(_decode_to_rgb(b"", 256, 256))

    def test_undecodable_input_returns_none(self) -> None:
        self.assertIsNone(_decode_to_rgb(b"not-a-jpeg", 256, 256))


class TestDecodeWorker(unittest.TestCase):
    def _service(self, size=(128, 128)) -> OjinVideoService:
        return OjinVideoService(settings=OjinVideoSettings(image_size=size), client=MagicMock())

    def _frame(self, jpeg: bytes) -> VideoFrame:
        return VideoFrame(
            frame_type=1, image_bytes=jpeg, audio_bytes=b"", is_final=False, volume=0
        )

    def test_worker_decodes_and_hands_back_in_order(self) -> None:
        s = self._service(size=(128, 128))
        s._start_decode_worker()
        try:
            frames = [self._frame(_jpeg(200, 200)) for _ in range(3)]
            for f in frames:
                s._decode_in.put(f)
            out = [s._decode_out.get(timeout=2.0) for _ in range(3)]
        finally:
            s._stop_decode_worker()
        self.assertEqual([id(f) for f in out], [id(f) for f in frames])  # order preserved
        for f in out:
            self.assertIsNotNone(f.out_rgb)
            self.assertEqual(len(f.out_rgb), 128 * 128 * 3)  # type: ignore[arg-type]

    def test_worker_sets_none_on_bad_frame_without_dying(self) -> None:
        s = self._service()
        s._start_decode_worker()
        try:
            bad = self._frame(b"garbage")
            good = self._frame(_jpeg(160, 160))
            s._decode_in.put(bad)
            s._decode_in.put(good)
            o1 = s._decode_out.get(timeout=2.0)
            o2 = s._decode_out.get(timeout=2.0)
        finally:
            s._stop_decode_worker()
        self.assertIsNone(o1.out_rgb)  # bad frame -> None, worker survives
        self.assertIsNotNone(o2.out_rgb)  # next frame still decodes

    def test_stop_is_idempotent_and_joins(self) -> None:
        s = self._service()
        s._start_decode_worker()
        s._stop_decode_worker()
        s._stop_decode_worker()  # must not raise
        self.assertIsNone(s._decode_thread)


class TestPipelineThroughLoop(unittest.IsolatedAsyncioTestCase):
    """End-to-end: a JPEG fed to the decode pipeline reaches the playback loop
    already decoded, and the loop emits it as a real RGB frame while audio
    keeps flowing — i.e. no cv2 runs inline on the loop."""

    async def test_decoded_frame_is_emitted_and_audio_flows(self) -> None:
        import asyncio

        from pipecat.frames.frames import OutputAudioRawFrame, OutputImageRawFrame
        from pipecat.services.ojin.video import AudioBuffer

        size = (128, 128)
        s = OjinVideoService(settings=OjinVideoSettings(image_size=size), client=MagicMock())
        s._initialized = True
        s._playback_paused = False
        s._current_buffer = AudioBuffer(buffer_id=1)
        s._current_buffer.bytes_.extend(b"\x01" * (40 * 1280))  # real audio to drain

        pushed: list = []

        async def capture(frame, *_a, **_k):
            pushed.append(frame)

        s.push_frame = capture  # type: ignore[assignment]

        s._start_decode_worker()
        for _ in range(10):
            s._decode_in.put(
                VideoFrame(
                    frame_type=1, image_bytes=_jpeg(200, 200),
                    audio_bytes=b"\x01" * 1280, is_final=False, volume=100,
                )
            )
        loop_task = asyncio.create_task(s._video_playback_loop())
        try:
            deadline = asyncio.get_event_loop().time() + 3.0
            while asyncio.get_event_loop().time() < deadline:
                imgs = [f for f in pushed if isinstance(f, OutputImageRawFrame)]
                audio = [f for f in pushed if isinstance(f, OutputAudioRawFrame)]
                if imgs and audio:
                    break
                await asyncio.sleep(0.02)
        finally:
            s._initialized = False
            try:
                await asyncio.wait_for(loop_task, timeout=1.0)
            except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
                loop_task.cancel()
                try:
                    await loop_task
                except (asyncio.CancelledError, Exception):
                    pass
            s._stop_decode_worker()

        imgs = [f for f in pushed if isinstance(f, OutputImageRawFrame)]
        audio = [f for f in pushed if isinstance(f, OutputAudioRawFrame)]
        self.assertTrue(imgs, "loop must emit a decoded image frame")
        self.assertEqual(len(imgs[0].image), 128 * 128 * 3)  # real RGB, target-sized
        self.assertEqual(imgs[0].size, size)
        self.assertTrue(audio, "audio must keep flowing alongside video")


if __name__ == "__main__":
    unittest.main()
