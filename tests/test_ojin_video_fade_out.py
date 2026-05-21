#
# Copyright (c) 2024-2026, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#
"""Unit tests for the FADE_OUT interrupt strategy on OjinVideoService.

The fade-out path replaces the buffer-clearing INSTANT_CUT with a graceful
200 ms audio decay aligned to the server's index=2 video frames. These tests
exercise the pure-logic surface (no WebSocket / no real client):

  - VideoFrame.is_fade_out() classifier
  - _apply_fade_ramp produces correctly-shaped audio
  - UserStartedSpeakingFrame handler under FADE_OUT does not clear buffers
"""

import unittest
from unittest.mock import AsyncMock, MagicMock

import numpy as np

from pipecat.frames.frames import (
    OutputAudioRawFrame,
    TTSStartedFrame,
    UserStartedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.ojin.video import (
    InterruptStrategy,
    OJIN_PERSONA_SAMPLE_RATE,
    OjinVideoService,
    OjinVideoSettings,
    VideoFrame,
    _FADE_GAIN,
    _FADE_SAMPLES_TOTAL,
)


def _make_service(strategy: InterruptStrategy) -> OjinVideoService:
    """Construct a service with a mocked client to avoid real WebSocket setup."""
    settings = OjinVideoSettings(interrupt_strategy=strategy, api_key="x", config_id="x")
    client = MagicMock()
    client.send_message = AsyncMock()
    svc = OjinVideoService(settings=settings, client=client)
    return svc


def _make_video_frame(frame_idx: int) -> VideoFrame:
    return VideoFrame(
        frame_idx=frame_idx,
        image_bytes=b"",
        audio_bytes=b"\x00" * 1280,
        is_final=False,
        volume=0,
    )


class TestVideoFrameFadeOutClassifier(unittest.TestCase):
    def test_fade_out_classifier_matches_index_2(self) -> None:
        self.assertTrue(_make_video_frame(2).is_fade_out())
        self.assertFalse(_make_video_frame(0).is_fade_out())
        self.assertFalse(_make_video_frame(1).is_fade_out())

    def test_silence_classifier_unchanged(self) -> None:
        self.assertTrue(_make_video_frame(0).is_silence())
        self.assertFalse(_make_video_frame(1).is_silence())
        self.assertFalse(_make_video_frame(2).is_silence())


class TestApplyFadeRamp(unittest.TestCase):
    """The fade ramp is applied to a single audio chunk per playback tick."""

    SAMPLE_RATE = OJIN_PERSONA_SAMPLE_RATE
    NUM_CHANNELS = 1
    CHUNK_SAMPLES = int(SAMPLE_RATE / 25)  # 640 samples per tick
    CHUNK_BYTES = CHUNK_SAMPLES * 2

    def setUp(self) -> None:
        self.svc = _make_service(InterruptStrategy.FADE_OUT)
        # Constant-amplitude audio so the ramp shape is the only thing that
        # changes the output.
        const = np.full(self.CHUNK_SAMPLES, 10000, dtype=np.int16)
        self.audio_frame = OutputAudioRawFrame(
            audio=const.tobytes(),
            sample_rate=self.SAMPLE_RATE,
            num_channels=self.NUM_CHANNELS,
        )

    def test_first_chunk_starts_near_full_amplitude_and_decays(self) -> None:
        out = self.svc._apply_fade_ramp(
            self.audio_frame, self.SAMPLE_RATE, self.NUM_CHANNELS, pts=0
        )
        samples = np.frombuffer(out.audio, dtype=np.int16)
        self.assertEqual(len(samples), self.CHUNK_SAMPLES)
        # First sample: full amplitude (ramp[0] = 1.0).
        self.assertGreater(samples[0], 9000)
        # Last sample of first chunk: decayed but not zero.
        self.assertLess(samples[-1], 9000)
        self.assertGreater(samples[-1], 0)
        # Counter advanced
        self.assertEqual(self.svc._fade_samples_done, self.CHUNK_SAMPLES)

    def test_consecutive_chunks_complete_full_ramp(self) -> None:
        ticks_in_fade = _FADE_SAMPLES_TOTAL // self.CHUNK_SAMPLES
        last = None
        for _ in range(ticks_in_fade):
            last = self.svc._apply_fade_ramp(
                OutputAudioRawFrame(
                    audio=np.full(self.CHUNK_SAMPLES, 10000, dtype=np.int16).tobytes(),
                    sample_rate=self.SAMPLE_RATE,
                    num_channels=self.NUM_CHANNELS,
                ),
                self.SAMPLE_RATE,
                self.NUM_CHANNELS,
                pts=0,
            )
        self.assertIsNotNone(last)
        # Last sample of final fade chunk should be at or very near zero.
        samples = np.frombuffer(last.audio, dtype=np.int16)
        self.assertLess(abs(int(samples[-1])), 100)
        self.assertEqual(self.svc._fade_samples_done, _FADE_SAMPLES_TOTAL)

    def test_chunk_past_fade_window_is_zero(self) -> None:
        # Pre-advance counter past the ramp window
        self.svc._fade_samples_done = _FADE_SAMPLES_TOTAL
        out = self.svc._apply_fade_ramp(
            self.audio_frame, self.SAMPLE_RATE, self.NUM_CHANNELS, pts=0
        )
        samples = np.frombuffer(out.audio, dtype=np.int16)
        self.assertTrue(np.all(samples == 0))


class TestUserStartedSpeakingFrameFadeOutBranch(unittest.IsolatedAsyncioTestCase):
    """FADE_OUT strategy preserves buffers and arms fade rather than cutting."""

    async def test_fade_out_strategy_does_not_clear_buffers(self) -> None:
        svc = _make_service(InterruptStrategy.FADE_OUT)
        svc.push_frame = AsyncMock()
        # Seed buffers to confirm they survive the interrupt
        svc._speech_buffer.extend(b"\x01" * 1280)
        svc._video_frames.append(_make_video_frame(1))

        await svc.process_frame(UserStartedSpeakingFrame(), FrameDirection.DOWNSTREAM)

        self.assertTrue(svc._fade_pending)
        self.assertFalse(svc._interrupting)
        self.assertFalse(svc._discard_speech_until_silence)
        self.assertEqual(len(svc._speech_buffer), 1280)
        self.assertEqual(len(svc._video_frames), 1)
        # Cancel message must still be sent so the server begins its fade.
        svc._client.send_message.assert_awaited_once()

    async def test_instant_cut_strategy_unchanged(self) -> None:
        """Regression: the existing INSTANT_CUT branch still clears state."""
        svc = _make_service(InterruptStrategy.INSTANT_CUT)
        svc.push_frame = AsyncMock()
        svc._speech_buffer.extend(b"\x01" * 1280)
        svc._video_frames.append(_make_video_frame(1))

        await svc.process_frame(UserStartedSpeakingFrame(), FrameDirection.DOWNSTREAM)

        self.assertTrue(svc._interrupting)
        self.assertTrue(svc._discard_speech_until_silence)
        self.assertEqual(len(svc._speech_buffer), 0)
        self.assertFalse(svc._fade_pending)

    async def test_double_interrupt_under_fade_out_is_idempotent(self) -> None:
        svc = _make_service(InterruptStrategy.FADE_OUT)
        svc.push_frame = AsyncMock()

        await svc.process_frame(UserStartedSpeakingFrame(), FrameDirection.DOWNSTREAM)
        self.assertTrue(svc._fade_pending)
        first_call_count = svc._client.send_message.await_count

        # Second VAD trigger while still pending: don't re-send cancel.
        await svc.process_frame(UserStartedSpeakingFrame(), FrameDirection.DOWNSTREAM)
        self.assertEqual(svc._client.send_message.await_count, first_call_count)


class TestTTSStartedFrameClearsFadeState(unittest.IsolatedAsyncioTestCase):
    """A new TTS turn must reset all fade flags and stale buffer."""

    async def test_post_fade_state_cleared_on_tts_started(self) -> None:
        svc = _make_service(InterruptStrategy.FADE_OUT)
        svc.push_frame = AsyncMock()
        svc._post_fade_mute = True
        svc._fade_samples_done = _FADE_SAMPLES_TOTAL
        svc._speech_buffer.extend(b"\xff" * 1280)

        await svc.process_frame(TTSStartedFrame(), FrameDirection.DOWNSTREAM)

        self.assertFalse(svc._post_fade_mute)
        self.assertFalse(svc._fade_active)
        self.assertFalse(svc._fade_pending)
        self.assertEqual(svc._fade_samples_done, 0)
        self.assertEqual(len(svc._speech_buffer), 0)


class TestPostFadeMuteDiscardsTtsAudio(unittest.IsolatedAsyncioTestCase):
    """During _post_fade_mute, incoming TTS audio is dropped on the floor."""

    async def test_tts_audio_dropped_when_post_fade_mute_is_set(self) -> None:
        svc = _make_service(InterruptStrategy.FADE_OUT)
        svc.push_frame = AsyncMock()
        svc._initialized = True
        svc._post_fade_mute = True

        from pipecat.frames.frames import TTSAudioRawFrame

        before_len = len(svc._speech_buffer)
        await svc.process_frame(
            TTSAudioRawFrame(audio=b"\x01" * 1280, sample_rate=16000, num_channels=1),
            FrameDirection.DOWNSTREAM,
        )
        # Buffer untouched + no message sent to server
        self.assertEqual(len(svc._speech_buffer), before_len)
        svc._client.send_message.assert_not_called()


class TestFadeGainShape(unittest.TestCase):
    """The precomputed fade-gain table is the canonical ramp shape."""

    def test_fade_gain_length_matches_5_frames_at_16khz(self) -> None:
        self.assertEqual(_FADE_SAMPLES_TOTAL, 5 * (16000 // 25))
        self.assertEqual(len(_FADE_GAIN), _FADE_SAMPLES_TOTAL)

    def test_fade_gain_monotonic_decreasing(self) -> None:
        diffs = np.diff(_FADE_GAIN)
        self.assertTrue(np.all(diffs <= 0))

    def test_fade_gain_endpoints(self) -> None:
        self.assertAlmostEqual(float(_FADE_GAIN[0]), 1.0, places=5)
        self.assertAlmostEqual(float(_FADE_GAIN[-1]), 0.0, places=5)


if __name__ == "__main__":
    unittest.main()
