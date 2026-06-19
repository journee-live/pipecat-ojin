#
# Copyright (c) 2024-2026, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Tests for LiveKit transport video stream handling.

Regression tests for issue #3116 (memory leak when video_in_enabled=False but
video tracks are subscribed) plus coverage for the video-output path that
publishes the avatar feed through ``LiveKitOutputTransport.write_video_frame``
and routes frames through ``rtc.AVSynchronizer``.
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

try:
    from livekit import rtc

    from pipecat.frames.frames import OutputImageRawFrame
    from pipecat.transports.livekit.transport import (
        LiveKitCallbacks,
        LiveKitOutputTransport,
        LiveKitParams,
        LiveKitTransport,
        LiveKitTransportClient,
    )

    LIVEKIT_AVAILABLE = True
except ImportError:
    LIVEKIT_AVAILABLE = False


@unittest.skipUnless(LIVEKIT_AVAILABLE, "livekit package not installed")
class TestLiveKitVideoStreamMemoryLeak(unittest.IsolatedAsyncioTestCase):
    """Regression tests for video queue memory leak (#3116).

    The bug: When video_in_enabled=False, subscribing to a video track would
    start a producer that fills _video_queue, but no consumer would drain it,
    causing unbounded memory growth (~3GB/min).

    The fix: Only start video stream processing when video_in_enabled=True.
    """

    def _create_client(self, video_in_enabled: bool) -> LiveKitTransportClient:
        """Create a client with the specified video input setting."""
        params = LiveKitParams(video_in_enabled=video_in_enabled)
        callbacks = LiveKitCallbacks(
            on_connected=AsyncMock(),
            on_disconnected=AsyncMock(),
            on_before_disconnect=AsyncMock(),
            on_participant_connected=AsyncMock(),
            on_participant_disconnected=AsyncMock(),
            on_audio_track_subscribed=AsyncMock(),
            on_audio_track_unsubscribed=AsyncMock(),
            on_video_track_subscribed=AsyncMock(),
            on_video_track_unsubscribed=AsyncMock(),
            on_data_received=AsyncMock(),
            on_first_participant_joined=AsyncMock(),
        )
        client = LiveKitTransportClient(
            url="wss://test.livekit.cloud",
            token="test-token",
            room_name="test-room",
            params=params,
            callbacks=callbacks,
            transport_name="test-transport",
        )
        client._task_manager = MagicMock()
        return client

    def _create_mock_video_track(self):
        """Create a mock video track subscription event."""
        track = MagicMock()
        track.kind = rtc.TrackKind.KIND_VIDEO
        track.sid = "video-track-123"
        publication = MagicMock()
        participant = MagicMock()
        participant.sid = "participant-456"
        return track, publication, participant

    async def test_disabled_video_input_does_not_start_queue_producer(self):
        """When video input is disabled, no producer should fill the queue.

        This prevents the memory leak where frames accumulate with no consumer.
        """
        client = self._create_client(video_in_enabled=False)
        track, publication, participant = self._create_mock_video_track()

        await client._async_on_track_subscribed(track, publication, participant)

        # Verify no video processing task was started
        task_names = [call[0][1] for call in client._task_manager.create_task.call_args_list]
        video_tasks = [name for name in task_names if "video" in name.lower()]
        self.assertEqual(video_tasks, [], "No video processing task should be started")

        # Queue should remain empty
        self.assertEqual(client._video_queue.qsize(), 0)

        # Track metadata should still be recorded
        self.assertIn(participant.sid, client._video_tracks)

        # Callback should still fire for user code
        client._callbacks.on_video_track_subscribed.assert_called_once()

    async def test_enabled_video_input_starts_queue_producer(self):
        """When video input is enabled, the producer should start."""
        client = self._create_client(video_in_enabled=True)
        track, publication, participant = self._create_mock_video_track()

        with patch.object(rtc, "VideoStream"):
            await client._async_on_track_subscribed(track, publication, participant)

        # Verify video processing task was started
        task_names = [call[0][1] for call in client._task_manager.create_task.call_args_list]
        video_tasks = [name for name in task_names if "video" in name.lower()]
        self.assertEqual(len(video_tasks), 1, "Video processing task should be started")

        # Track metadata should be recorded
        self.assertIn(participant.sid, client._video_tracks)

        # Callback should fire
        client._callbacks.on_video_track_subscribed.assert_called_once()


@unittest.skipUnless(LIVEKIT_AVAILABLE, "livekit package not installed")
class TestLiveKitVideoOutput(unittest.IsolatedAsyncioTestCase):
    """Coverage for the video-output / AVSynchronizer path.

    The avatar pipeline produces ``OutputImageRawFrame`` with a shared
    ``pts`` (nanoseconds) that already aligns audio + video at the source.
    These tests verify the transport (a) publishes a video track when
    ``video_out_enabled`` is set, (b) builds an ``AVSynchronizer`` when
    ``av_sync_enabled`` is True, (c) plumbs ``pts // 1000`` into
    ``VideoSource.capture_frame``'s ``timestamp_us`` on the no-sync path,
    and (d) tears state down on disconnect.
    """

    def _make_callbacks(self) -> LiveKitCallbacks:
        return LiveKitCallbacks(
            on_connected=AsyncMock(),
            on_disconnected=AsyncMock(),
            on_before_disconnect=AsyncMock(),
            on_participant_connected=AsyncMock(),
            on_participant_disconnected=AsyncMock(),
            on_audio_track_subscribed=AsyncMock(),
            on_audio_track_unsubscribed=AsyncMock(),
            on_video_track_subscribed=AsyncMock(),
            on_video_track_unsubscribed=AsyncMock(),
            on_data_received=AsyncMock(),
            on_first_participant_joined=AsyncMock(),
        )

    def _make_client(self, params: LiveKitParams) -> LiveKitTransportClient:
        client = LiveKitTransportClient(
            url="wss://test.livekit.cloud",
            token="test-token",
            room_name="test-room",
            params=params,
            callbacks=self._make_callbacks(),
            transport_name="test-transport",
        )
        client._task_manager = MagicMock()
        # Populate the audio path so the client thinks it can publish.
        client._connected = True
        client._audio_source = MagicMock(spec=rtc.AudioSource)
        client._audio_source.capture_frame = AsyncMock()
        return client

    def test_params_defaults_av_sync_enabled_true(self):
        """A bare ``LiveKitParams()`` defaults to ``av_sync_enabled=True``."""
        self.assertTrue(LiveKitParams().av_sync_enabled)

    async def test_connect_publishes_video_track_and_builds_synchronizer(self):
        """When ``video_out_enabled`` is on, connect() publishes a video track
        and constructs an ``AVSynchronizer`` (since ``av_sync_enabled`` is on by
        default)."""
        params = LiveKitParams(
            audio_out_enabled=True,
            audio_out_sample_rate=16000,
            video_out_enabled=True,
            video_out_width=640,
            video_out_height=360,
            video_out_framerate=25,
            video_out_bitrate=2_500_000,
        )
        client = LiveKitTransportClient(
            url="wss://test.livekit.cloud",
            token="t",
            room_name="r",
            params=params,
            callbacks=self._make_callbacks(),
            transport_name="test-transport",
        )
        client._task_manager = MagicMock()
        client._out_sample_rate = 16000

        room = MagicMock()
        room.connect = AsyncMock()
        room.local_participant = MagicMock()
        room.local_participant.publish_track = AsyncMock()
        room.local_participant.sid = "agent-sid"
        room.remote_participants = {}
        client._room = room

        with (
            patch.object(rtc, "AudioSource") as audio_source_cls,
            patch.object(rtc.LocalAudioTrack, "create_audio_track") as audio_track_factory,
            patch.object(rtc, "VideoSource") as video_source_cls,
            patch.object(rtc.LocalVideoTrack, "create_video_track") as video_track_factory,
            patch.object(rtc, "AVSynchronizer") as av_sync_cls,
        ):
            await client.connect()

        # Video source built with the requested resolution.
        video_source_cls.assert_called_once_with(640, 360)
        # Video track created and published.
        self.assertTrue(video_track_factory.called)
        publish_calls = room.local_participant.publish_track.call_args_list
        # 2 publish_track calls: audio + video
        self.assertEqual(len(publish_calls), 2)
        # AVSynchronizer constructed with the published audio + video sources.
        av_sync_cls.assert_called_once()
        kwargs = av_sync_cls.call_args.kwargs
        self.assertEqual(kwargs["video_fps"], 25.0)
        self.assertIs(kwargs["audio_source"], audio_source_cls.return_value)
        self.assertIs(kwargs["video_source"], video_source_cls.return_value)

    async def test_connect_without_video_out_skips_video_path(self):
        """Audio-only configuration must not touch video classes."""
        params = LiveKitParams(audio_out_enabled=True, audio_out_sample_rate=16000)
        client = LiveKitTransportClient(
            url="wss://test.livekit.cloud",
            token="t",
            room_name="r",
            params=params,
            callbacks=self._make_callbacks(),
            transport_name="test-transport",
        )
        client._task_manager = MagicMock()
        client._out_sample_rate = 16000

        room = MagicMock()
        room.connect = AsyncMock()
        room.local_participant = MagicMock()
        room.local_participant.publish_track = AsyncMock()
        room.local_participant.sid = "agent-sid"
        room.remote_participants = {}
        client._room = room

        with (
            patch.object(rtc, "AudioSource"),
            patch.object(rtc.LocalAudioTrack, "create_audio_track"),
            patch.object(rtc, "VideoSource") as video_source_cls,
            patch.object(rtc, "AVSynchronizer") as av_sync_cls,
        ):
            await client.connect()

        video_source_cls.assert_not_called()
        av_sync_cls.assert_not_called()
        self.assertIsNone(client._video_source)
        self.assertIsNone(client._av_synchronizer)

    async def test_av_sync_disabled_skips_synchronizer(self):
        """``av_sync_enabled=False`` publishes the video track but constructs
        no synchronizer — the caller is responsible for direct timestamp
        management via ``publish_video(... timestamp_us=...)``."""
        params = LiveKitParams(
            audio_out_enabled=True,
            audio_out_sample_rate=16000,
            video_out_enabled=True,
            av_sync_enabled=False,
        )
        client = LiveKitTransportClient(
            url="wss://test.livekit.cloud",
            token="t",
            room_name="r",
            params=params,
            callbacks=self._make_callbacks(),
            transport_name="test-transport",
        )
        client._task_manager = MagicMock()
        client._out_sample_rate = 16000

        room = MagicMock()
        room.connect = AsyncMock()
        room.local_participant = MagicMock()
        room.local_participant.publish_track = AsyncMock()
        room.local_participant.sid = "agent-sid"
        room.remote_participants = {}
        client._room = room

        with (
            patch.object(rtc, "AudioSource"),
            patch.object(rtc.LocalAudioTrack, "create_audio_track"),
            patch.object(rtc, "VideoSource"),
            patch.object(rtc.LocalVideoTrack, "create_video_track"),
            patch.object(rtc, "AVSynchronizer") as av_sync_cls,
        ):
            await client.connect()

        av_sync_cls.assert_not_called()
        self.assertIsNone(client._av_synchronizer)
        self.assertIsNotNone(client._video_source)

    async def test_publish_audio_routes_through_synchronizer_when_present(self):
        """With AVSynchronizer present, audio frames must go through ``push``
        not the raw ``audio_source.capture_frame`` — that's how the synchronizer
        keeps its internal clock."""
        client = self._make_client(LiveKitParams(video_out_enabled=True))
        synchronizer = MagicMock()
        synchronizer.push = AsyncMock()
        client._av_synchronizer = synchronizer

        audio_frame = MagicMock(spec=rtc.AudioFrame)
        ok = await client.publish_audio(audio_frame)

        self.assertTrue(ok)
        synchronizer.push.assert_awaited_once_with(audio_frame)
        client._audio_source.capture_frame.assert_not_called()

    async def test_publish_audio_falls_back_to_source_without_synchronizer(self):
        """Without a synchronizer, ``publish_audio`` keeps the original
        ``audio_source.capture_frame`` path."""
        client = self._make_client(LiveKitParams())
        audio_frame = MagicMock(spec=rtc.AudioFrame)

        ok = await client.publish_audio(audio_frame)

        self.assertTrue(ok)
        client._audio_source.capture_frame.assert_awaited_once_with(audio_frame)

    async def test_publish_video_forwards_timestamp_us_to_source(self):
        """The avatar's PTS arrives as ``timestamp_us`` on the no-sync path —
        this is the wire-level RTP timestamp basis used for lipsync."""
        client = self._make_client(LiveKitParams(video_out_enabled=True, av_sync_enabled=False))
        client._video_source = MagicMock(spec=rtc.VideoSource)
        video_frame = MagicMock(spec=rtc.VideoFrame)

        ok = await client.publish_video(video_frame, timestamp_us=123_456_789)

        self.assertTrue(ok)
        client._video_source.capture_frame.assert_called_once_with(
            video_frame, timestamp_us=123_456_789
        )

    async def test_publish_video_routes_through_synchronizer_when_present(self):
        """With AVSynchronizer present, video frames go through ``push``."""
        client = self._make_client(LiveKitParams(video_out_enabled=True))
        client._video_source = MagicMock(spec=rtc.VideoSource)
        synchronizer = MagicMock()
        synchronizer.push = AsyncMock()
        client._av_synchronizer = synchronizer
        video_frame = MagicMock(spec=rtc.VideoFrame)

        ok = await client.publish_video(video_frame, timestamp_us=1_000_000)

        self.assertTrue(ok)
        synchronizer.push.assert_awaited_once()
        # The synchronizer takes seconds, not microseconds.
        args, kwargs = synchronizer.push.call_args
        self.assertIs(args[0], video_frame)
        self.assertEqual(kwargs["timestamp"], 1.0)

    async def test_write_video_frame_passes_pts_as_timestamp_us(self):
        """``LiveKitOutputTransport.write_video_frame`` must convert the
        pipecat ``OutputImageRawFrame.pts`` (nanoseconds) into LiveKit
        ``timestamp_us``."""
        params = LiveKitParams(video_out_enabled=True)
        transport = MagicMock(spec=LiveKitTransport)
        client = MagicMock(spec=LiveKitTransportClient)
        client.publish_video = AsyncMock(return_value=True)
        output = LiveKitOutputTransport.__new__(LiveKitOutputTransport)
        output._client = client
        output._params = params
        output._transport = transport

        frame = OutputImageRawFrame(image=b"\x00" * (4 * 4 * 3), size=(4, 4), format="RGB")
        frame.pts = 5_000_000_000  # 5 seconds in nanoseconds

        ok = await output.write_video_frame(frame)

        self.assertTrue(ok)
        client.publish_video.assert_awaited_once()
        _args, kwargs = client.publish_video.call_args
        # 5s in ns → 5_000_000us
        self.assertEqual(kwargs["timestamp_us"], 5_000_000)

    async def test_write_video_frame_no_op_when_video_out_disabled(self):
        """Without ``video_out_enabled`` the output transport must short-circuit
        — avoids surprising publishes when the avatar pipeline isn't expected."""
        params = LiveKitParams(video_out_enabled=False)
        client = MagicMock(spec=LiveKitTransportClient)
        client.publish_video = AsyncMock(return_value=True)
        output = LiveKitOutputTransport.__new__(LiveKitOutputTransport)
        output._client = client
        output._params = params
        output._transport = MagicMock(spec=LiveKitTransport)

        frame = OutputImageRawFrame(image=b"\x00" * 12, size=(2, 2), format="RGB")
        frame.pts = 1

        ok = await output.write_video_frame(frame)

        self.assertFalse(ok)
        client.publish_video.assert_not_called()

    async def test_disconnect_tears_down_video_state(self):
        """Disconnect must release the synchronizer + video source so we don't
        leak the FFI handles."""
        client = self._make_client(LiveKitParams(video_out_enabled=True))
        synchronizer = MagicMock()
        synchronizer.aclose = AsyncMock()
        video_source = MagicMock(spec=rtc.VideoSource)
        video_source.aclose = AsyncMock()
        client._av_synchronizer = synchronizer
        client._video_source = video_source
        client._video_track = MagicMock()

        room = MagicMock()
        room.disconnect = AsyncMock()
        client._room = room
        client._disconnect_counter = 1

        await client.disconnect()

        synchronizer.aclose.assert_awaited_once()
        video_source.aclose.assert_awaited_once()
        self.assertIsNone(client._av_synchronizer)
        self.assertIsNone(client._video_source)
        self.assertIsNone(client._video_track)


if __name__ == "__main__":
    unittest.main()
