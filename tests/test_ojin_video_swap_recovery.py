"""Tests for OjinVideoService v3 deferred-swap recovery after an interruption.

Repro of the silent-audio bug: the audio buffer swap is edge-triggered on the
server's ``frame_type == 3`` new-turn marker. After a barge-in, that marker can
arrive BEFORE the replacement TTS buffer is queued, so the edge-triggered swap is
skipped and never repeats — the late buffer is orphaned and playback is silent
for the rest of the session.

The fix makes recovery level-triggered: ``_swap_to_next_buffer`` records
``_swap_pending`` when the boundary passes with an empty queue, and the playback
loop promotes the buffer as soon as it lands and a new-turn SPEECH frame pops
(``_current_replaceable``), while still honouring the ``not interrupted`` fadeout
guard for the normal case.
"""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock

from pipecat.frames.frames import OutputAudioRawFrame
from pipecat.services.ojin.video import (
    AudioBuffer,
    OjinVideoService,
    OjinVideoSettings,
    VideoFrame,
)


def _make_service() -> OjinVideoService:
    client = MagicMock()
    client.send_message = AsyncMock()
    service = OjinVideoService(settings=OjinVideoSettings(), client=client)
    service._initialized = True
    return service


def _speech() -> VideoFrame:
    return VideoFrame(
        frame_type=1, image_bytes=b"\x00" * 8, audio_bytes=b"\x01" * 1280,
        is_final=False, volume=100,
    )


def _buffer(buffer_id: int, *, nbytes: int = 0, interrupted: bool = False) -> AudioBuffer:
    buf = AudioBuffer(buffer_id=buffer_id, interrupted=interrupted)
    if nbytes:
        buf.bytes_.extend(b"\x01" * nbytes)
    return buf


class TestCurrentReplaceable(unittest.TestCase):
    """The swap gate: when may a queued buffer replace the current one."""

    def test_no_current_is_replaceable(self) -> None:
        s = _make_service()
        s._current_buffer = None
        self.assertTrue(s._current_replaceable())

    def test_valid_buffer_with_bytes_is_not_replaceable(self) -> None:
        s = _make_service()
        s._current_buffer = _buffer(1, nbytes=4096)
        self.assertFalse(s._current_replaceable())

    def test_valid_drained_buffer_is_replaceable(self) -> None:
        s = _make_service()
        s._current_buffer = _buffer(1, nbytes=0)
        self.assertTrue(s._current_replaceable())

    def test_interrupted_with_bytes_not_replaceable_without_pending(self) -> None:
        # The fadeout guard: a stale old-turn SPEECH frame must not swap mid-fade.
        s = _make_service()
        s._current_buffer = _buffer(94, nbytes=4096, interrupted=True)
        s._swap_pending = False
        self.assertFalse(s._current_replaceable())

    def test_interrupted_with_bytes_replaceable_with_pending(self) -> None:
        # Orphan recovery: the new-turn boundary already passed, so the
        # interrupted buffer is the stale prior turn — replace it.
        s = _make_service()
        s._current_buffer = _buffer(94, nbytes=4096, interrupted=True)
        s._swap_pending = True
        self.assertTrue(s._current_replaceable())

    def test_interrupted_drained_replaceable_only_with_pending(self) -> None:
        s = _make_service()
        s._current_buffer = _buffer(94, nbytes=0, interrupted=True)
        s._swap_pending = False
        self.assertFalse(s._current_replaceable())
        s._swap_pending = True
        self.assertTrue(s._current_replaceable())


class TestSwapDeferral(unittest.IsolatedAsyncioTestCase):
    """_swap_to_next_buffer arms/clears the deferred-swap flag correctly."""

    async def test_empty_queue_defers_instead_of_dropping(self) -> None:
        s = _make_service()
        s._current_buffer = _buffer(94, nbytes=2048, interrupted=True)

        await s._swap_to_next_buffer(align_to_frame=_speech())

        self.assertTrue(s._swap_pending, "boundary with empty queue must defer the swap")
        # Current is left intact (not dropped): playback keeps draining it.
        self.assertIsNotNone(s._current_buffer)
        self.assertEqual(s._current_buffer.buffer_id, 94)

    async def test_pending_swap_completes_when_buffer_lands(self) -> None:
        s = _make_service()
        s._current_buffer = _buffer(94, nbytes=0, interrupted=True)
        s._swap_pending = True
        s._audio_buffers.append(_buffer(95, nbytes=4096))

        await s._swap_to_next_buffer(align_to_frame=_speech())

        self.assertFalse(s._swap_pending, "successful swap must clear the pending flag")
        self.assertEqual(s._current_buffer.buffer_id, 95)

    async def test_successful_swap_clears_any_prior_pending(self) -> None:
        s = _make_service()
        s._swap_pending = True
        s._current_buffer = None
        s._audio_buffers.append(_buffer(95, nbytes=4096))

        await s._swap_to_next_buffer(align_to_frame=_speech())

        self.assertFalse(s._swap_pending)
        self.assertEqual(s._current_buffer.buffer_id, 95)


class TestOrphanRecoveryThroughLoop(unittest.IsolatedAsyncioTestCase):
    """End-to-end: after a deferred swap, the playback loop promotes the late
    buffer and its audio actually plays (the bug left this silent forever)."""

    async def test_late_buffer_is_promoted_and_audio_plays(self) -> None:
        s = _make_service()
        s._playback_paused = False
        # Orphan state: a barge-in left buffer #94 interrupted+drained, and the
        # frame_type=3 boundary already passed with an empty queue (_swap_pending).
        s._current_buffer = _buffer(94, nbytes=0, interrupted=True)
        s._swap_pending = True
        # The replacement turn's TTS finally lands, and its new-turn SPEECH
        # video frames start arriving from the server.
        s._audio_buffers.append(_buffer(95, nbytes=40 * 1280))
        for _ in range(40):
            s._video_frames.append(_speech())

        pushed: list = []

        async def capture(frame, *_a, **_k):
            pushed.append(frame)

        s.push_frame = capture  # type: ignore[assignment]
        s._prepare_video_frame = AsyncMock(return_value=b"img")  # type: ignore[assignment]

        loop_task = asyncio.create_task(s._video_playback_loop())
        try:
            deadline = asyncio.get_event_loop().time() + 3.0
            while not (s._current_buffer is not None and s._current_buffer.buffer_id == 95):
                if asyncio.get_event_loop().time() > deadline:
                    self.fail("late buffer #95 was never promoted (orphaned-swap bug)")
                await asyncio.sleep(0.01)
            # Let a few ticks drain #95's audio after the swap.
            await asyncio.sleep(0.15)
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

        self.assertFalse(s._swap_pending, "pending flag must clear after recovery swap")
        audio = [f for f in pushed if isinstance(f, OutputAudioRawFrame)]
        self.assertTrue(audio, "loop must push audio frames")
        non_silent = [f for f in audio if set(bytes(f.audio)) != {0}]
        self.assertTrue(
            non_silent,
            "buffer #95's real audio must play after the recovery swap (was silent)",
        )


if __name__ == "__main__":
    unittest.main()
