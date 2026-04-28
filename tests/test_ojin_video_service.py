#
# Copyright (c) 2024-2026, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#
"""Regression tests for OjinVideoService._stop_audio_playback."""

import sys
from unittest.mock import MagicMock

# The 'ojin' package (provided by ojin-client) and cv2 (opencv-python,
# from --extra webrtc) are imported at module load by
# pipecat.services.ojin.video, but CI's tests workflow installs neither.
# Stub them so the test file can import OjinVideoService; the test only
# exercises _stop_audio_playback, which does not touch any stubbed
# attribute at runtime.
for _name in (
    "cv2",
    "ojin",
    "ojin.entities",
    "ojin.entities.interaction_messages",
    "ojin.ojin_client",
    "ojin.ojin_client_messages",
    "ojin.profiling_utils",
):
    sys.modules.setdefault(_name, MagicMock())

import unittest  # noqa: E402
from unittest.mock import AsyncMock  # noqa: E402

from pipecat.processors.frame_processor import FrameDirection  # noqa: E402
from pipecat.services.ojin.video import (  # noqa: E402
    OjinBotStoppedSpeakingFrame,
    OjinVideoService,
    OjinVideoSettings,
)


def _make_service() -> OjinVideoService:
    """Build an OjinVideoService with a mocked client and a stubbed push_frame."""
    settings = OjinVideoSettings()
    service = OjinVideoService(settings=settings, client=MagicMock())
    service.push_frame = AsyncMock()
    return service


class TestStopAudioPlayback(unittest.IsolatedAsyncioTestCase):
    async def test_emits_frame_when_flag_already_false(self):
        # Regression scenario: _video_playback_loop's natural-end branch
        # pre-sets the flag to False before calling _stop_audio_playback.
        # Before the fix, the method short-circuited and skipped the frame
        # push and buffer clear.
        service = _make_service()
        service._is_playing_speech_audio = False
        service._speech_buffer.extend(b"\x00\x01\x02\x03")

        await service._stop_audio_playback()

        self.assertEqual(len(service._speech_buffer), 0)
        service.push_frame.assert_awaited_once()
        pushed_frame = service.push_frame.call_args.args[0]
        self.assertIsInstance(pushed_frame, OjinBotStoppedSpeakingFrame)
        self.assertEqual(
            service.push_frame.call_args.kwargs.get("direction"),
            FrameDirection.DOWNSTREAM,
        )

    async def test_clears_buffer_when_flag_true(self):
        # Interruption-handler call sites (INSTANT_CUT, SMOOTH_VIDEO_HARD_AUDIO)
        # do not pre-set the flag. Behaviour must remain correct here.
        service = _make_service()
        service._is_playing_speech_audio = True
        service._speech_buffer.extend(b"\xff\xee\xdd")

        await service._stop_audio_playback()

        self.assertFalse(service._is_playing_speech_audio)
        self.assertEqual(len(service._speech_buffer), 0)
        service.push_frame.assert_awaited_once()
        self.assertIsInstance(service.push_frame.call_args.args[0], OjinBotStoppedSpeakingFrame)

    async def test_idempotent_across_repeated_calls(self):
        # Calling twice in a row should remain consistent: the flag stays
        # False and a frame is pushed each time. This guards against any
        # future re-introduction of an early-return that would silently
        # drop a stop signal.
        service = _make_service()
        service._is_playing_speech_audio = True
        service._speech_buffer.extend(b"\x10\x20")

        await service._stop_audio_playback()
        await service._stop_audio_playback()

        self.assertFalse(service._is_playing_speech_audio)
        self.assertEqual(len(service._speech_buffer), 0)
        self.assertEqual(service.push_frame.await_count, 2)
        for call in service.push_frame.await_args_list:
            self.assertIsInstance(call.args[0], OjinBotStoppedSpeakingFrame)


if __name__ == "__main__":
    unittest.main()
