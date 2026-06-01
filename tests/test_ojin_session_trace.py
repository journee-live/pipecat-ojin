"""Tests for the per-turn video response-latency metric in OjinSessionTrace.

The OjinVideoService anchors each turn at its first TTS audio frame and closes
two measurements against it — ``recv`` (first speech video frame arriving from
the server) and ``played`` (that frame reaching the transport downstream). This
module exercises the recording/summary surface those call sites rely on, using a
controllable clock so the durations are deterministic.
"""

import unittest
from unittest.mock import AsyncMock, MagicMock

from ojin.ojin_client_messages import OjinInteractionResponseMessage
from pipecat.services.ojin.session_trace import LANES, OjinSessionTrace
from pipecat.services.ojin.video import OjinVideoService, OjinVideoSettings


class _FakeClock:
    """Monotonic clock whose value is advanced explicitly by the test."""

    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def _make_trace() -> tuple[OjinSessionTrace, _FakeClock]:
    clock = _FakeClock()
    trace = OjinSessionTrace(session_id="testsession", config_id="cfg", clock=clock)
    return trace, clock


class TestResponseLatencyRecording(unittest.TestCase):
    def test_has_dedicated_response_lane(self) -> None:
        self.assertIn("response", LANES)

    def test_records_recv_and_played_against_first_tts_anchor(self) -> None:
        trace, clock = _make_trace()

        # First TTS audio of the turn lands at t=1.0s — the anchor.
        clock.t = 1.0
        anchor = trace.mark()

        # First speech video frame received from the server 200 ms later.
        clock.t = 1.2
        recv_ms = trace.record_response_latency("recv", anchor, args={"frame_idx": 3})
        # …and played downstream 50 ms after that (250 ms from the anchor).
        clock.t = 1.25
        played_ms = trace.record_response_latency("played", anchor, args={"frame_idx": 3})

        self.assertAlmostEqual(recv_ms, 200.0, places=1)
        self.assertAlmostEqual(played_ms, 250.0, places=1)

        doc = trace.build()
        spans = [
            e
            for e in doc["traceEvents"]
            if e.get("ph") == "X" and e["name"].startswith("first_tts→first_video_")
        ]
        names = {e["name"] for e in spans}
        self.assertEqual(
            names,
            {"first_tts→first_video_recv", "first_tts→first_video_played"},
        )
        # Both spans live on the response lane.
        self.assertTrue(all(e["tid"] == LANES["response"] for e in spans))

    def test_summary_aggregates_multiple_turns(self) -> None:
        trace, clock = _make_trace()
        # Three turns with recv latencies 100/300/200 ms.
        for offset, recv_ms in ((0.0, 0.1), (2.0, 0.3), (4.0, 0.2)):
            clock.t = 1.0 + offset
            anchor = trace.mark()
            clock.t = 1.0 + offset + recv_ms
            trace.record_response_latency("recv", anchor)

        summary = trace.build()["otherData"]["response_latency_ms"]
        recv = summary["recv"]
        self.assertEqual(recv["count"], 3)
        self.assertAlmostEqual(recv["min_ms"], 100.0, places=1)
        self.assertAlmostEqual(recv["max_ms"], 300.0, places=1)
        self.assertAlmostEqual(recv["mean_ms"], 200.0, places=1)
        self.assertAlmostEqual(recv["p50_ms"], 200.0, places=1)
        self.assertAlmostEqual(recv["last_ms"], 200.0, places=1)
        # No played samples were recorded.
        self.assertEqual(summary["played"], {"count": 0})

    def test_summary_present_and_empty_by_default(self) -> None:
        trace, _ = _make_trace()
        summary = trace.build()["otherData"]["response_latency_ms"]
        self.assertEqual(summary, {"recv": {"count": 0}, "played": {"count": 0}})

    def test_schema_version_bumped_to_2(self) -> None:
        trace, _ = _make_trace()
        self.assertEqual(trace.build()["otherData"]["schema_version"], 2)


def _make_video_service() -> OjinVideoService:
    client = MagicMock()
    client.send_message = AsyncMock()
    service = OjinVideoService(settings=OjinVideoSettings(), client=client)
    service._initialized = True
    return service


def _response_msg(index: int) -> OjinInteractionResponseMessage:
    """A server response frame whose ``index`` is the wire marker
    (0 idle/silence, 1 speech, 2 fade, 3 new-turn)."""
    return OjinInteractionResponseMessage(
        interaction_id="t",
        video_frame_bytes=b"\x00" * 16,
        audio_frame_bytes=b"\x00" * 16,
        index=index,
    )


class TestVideoServiceRecvLatencyWiring(unittest.IsolatedAsyncioTestCase):
    """The recv-side measurement is driven from ``_handle_ojin_message`` when
    the first speech video frame of a turn arrives from the server.
    """

    def _armed_service(self, clock: _FakeClock) -> OjinVideoService:
        service = _make_video_service()
        service._trace = OjinSessionTrace(session_id="s", clock=clock)
        clock.t = 1.0
        service._tr_first_tts_audio_at = service._trace.mark()
        service._awaiting_first_recv_video = True
        return service

    async def test_recv_fires_once_on_first_speech_frame(self) -> None:
        clock = _FakeClock()
        service = self._armed_service(clock)

        clock.t = 1.15  # first new-turn speech frame arrives 150 ms later
        await service._handle_ojin_message(_response_msg(index=3))

        self.assertFalse(service._awaiting_first_recv_video)
        recv = service._trace.build()["otherData"]["response_latency_ms"]["recv"]
        self.assertEqual(recv["count"], 1)
        self.assertAlmostEqual(recv["last_ms"], 150.0, places=1)

        # A second speech frame in the same turn must not re-record.
        clock.t = 1.30
        await service._handle_ojin_message(_response_msg(index=1))
        recv = service._trace.build()["otherData"]["response_latency_ms"]["recv"]
        self.assertEqual(recv["count"], 1)

    async def test_idle_frame_does_not_record_and_stays_armed(self) -> None:
        clock = _FakeClock()
        service = self._armed_service(clock)

        clock.t = 1.15
        await service._handle_ojin_message(_response_msg(index=0))  # idle/silence

        self.assertTrue(service._awaiting_first_recv_video)
        recv = service._trace.build()["otherData"]["response_latency_ms"]["recv"]
        self.assertEqual(recv["count"], 0)


if __name__ == "__main__":
    unittest.main()
