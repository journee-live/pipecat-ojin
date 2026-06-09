"""Tests for the barge-in audio fade ramp (``_fade_chunk``).

On interruption the v3 ``OjinVideoService`` no longer hard-cuts audio to
silence; it ramps the current turn's audio to zero over
``interrupt_audio_fade_s`` via a per-sample linear gain keyed to the number of
samples emitted since the interrupt. These cover the pure ramp helper: gain
shape, length preservation, completion to silence, and — the property that
makes it click-free — continuity across chunk boundaries.
"""

import unittest

import numpy as np

from pipecat.services.ojin.video import _fade_chunk


def _const_chunk(n_samples: int, value: int = 10000) -> bytes:
    """``n_samples`` int16 samples all equal to ``value`` (constant amplitude)."""
    return np.full(n_samples, value, dtype="<i2").tobytes()


def _to_samples(audio: bytes) -> np.ndarray:
    return np.frombuffer(audio, dtype="<i2").astype(np.float64)


class FadeChunkTests(unittest.TestCase):
    def test_length_and_sample_count_preserved(self) -> None:
        chunk = _const_chunk(800)
        out = _fade_chunk(chunk, 0, 12000)
        self.assertEqual(len(out), len(chunk))
        self.assertEqual(_to_samples(out).size, 800)

    def test_first_sample_full_volume_at_start(self) -> None:
        value = 10000
        out = _to_samples(_fade_chunk(_const_chunk(800, value), 0, 12000))
        # samples_emitted=0 → gain[0] == 1.0 → sample passes through unattenuated.
        self.assertEqual(int(out[0]), value)

    def test_gain_monotonically_non_increasing(self) -> None:
        # Constant input → output magnitude tracks gain, which must never rise.
        out = _to_samples(_fade_chunk(_const_chunk(2000), 0, 1500))
        self.assertTrue(np.all(np.diff(out) <= 0))

    def test_midpoint_gain_is_about_half(self) -> None:
        value = 10000
        total = 12000
        # The sample at index total/2 should carry ~0.5 gain.
        out = _to_samples(_fade_chunk(_const_chunk(total, value), 0, total))
        mid = out[total // 2]
        self.assertAlmostEqual(mid / value, 0.5, delta=0.01)

    def test_fully_faded_chunk_is_silence(self) -> None:
        # Once samples_emitted has reached the window, every sample is zero.
        out = _to_samples(_fade_chunk(_const_chunk(800), 12000, 12000))
        self.assertTrue(np.all(out == 0))

    def test_gain_near_zero_at_window_end_and_silent_just_past_it(self) -> None:
        # The ramp hits exactly 0 at sample index == fade_total_samples. So the
        # last in-window sample (index total-1) is near-zero but not yet zero,
        # and the very next sample is fully silent.
        total = 1600
        value = 10000
        out = _to_samples(_fade_chunk(_const_chunk(total + 1, value), 0, total))
        self.assertGreaterEqual(out[total - 1], 0)
        self.assertLess(out[total - 1], value / total + 1)  # gain ~= 1/total
        self.assertEqual(int(out[total]), 0)  # gain clipped to 0

    def test_continuous_across_chunk_boundaries(self) -> None:
        # Threading samples_emitted forward must equal ramping one big chunk:
        # this is the click-free property (no discontinuity at the seam).
        total = 4000
        whole = _const_chunk(1000)
        one_shot = _fade_chunk(whole, 0, total)
        first = _fade_chunk(_const_chunk(500), 0, total)
        second = _fade_chunk(_const_chunk(500), 500, total)
        np.testing.assert_array_equal(_to_samples(one_shot), _to_samples(first + second))

    def test_stereo_is_channel_agnostic(self) -> None:
        # Flat-sample ramp: interleaved L/R at the same index step down together.
        total = 2000
        stereo = np.full(800, 10000, dtype="<i2").tobytes()  # treat as 400 L/R frames
        out = _to_samples(_fade_chunk(stereo, 0, total))
        # Adjacent interleaved samples (same frame) differ by at most one ramp step.
        self.assertLessEqual(abs(out[0] - out[1]), 10000 / total + 1)

    def test_empty_chunk_returns_empty(self) -> None:
        self.assertEqual(_fade_chunk(b"", 0, 12000), b"")


if __name__ == "__main__":
    unittest.main()
