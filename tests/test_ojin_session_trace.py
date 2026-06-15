"""Tests for the per-turn latency surfaces in OjinSessionTrace.

Each turn is anchored at its first TTS audio frame, and two measurements close
against that anchor — ``recv`` (first speech video frame arriving from the
server) and ``played`` (that frame reaching the transport downstream). With the
v3 refactor the *caller* of these anchors moved into ``ojin.stv.OjinSTVClient``
(the avatar client), but the recording/summary surface they rely on still lives
on ``OjinSessionTrace`` and is exercised here with a controllable clock so the
durations are deterministic. The bot's ``LatencyTracker`` likewise folds each
completed turn's end-to-end breakdown into the shared trace via
``record_latency_report``.
"""

import unittest

from pipecat.services.ojin.session_trace import LANES, OjinSessionTrace


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
        recv_ms = trace.record_response_latency("recv", anchor, args={"frame_type": 3})
        # …and played downstream 50 ms after that (250 ms from the anchor).
        clock.t = 1.25
        played_ms = trace.record_response_latency("played", anchor, args={"frame_type": 3})

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


class TestLatencyReportRecording(unittest.TestCase):
    """The bot's LatencyTracker folds each completed turn's end-to-end latency
    breakdown into the shared trace via ``record_latency_report``; the raw
    per-turn list and a per-field summary surface in ``otherData``, and each
    turn is drawn on the ``latency`` lane.
    """

    def test_has_dedicated_latency_lane(self) -> None:
        self.assertIn("latency", LANES)

    def test_records_turns_and_summarises_per_field(self) -> None:
        trace, _ = _make_trace()
        trace.record_latency_report(
            {
                "stt_ttfb_ms": 50.0,
                "llm_ttfb_ms": 120.0,
                "tts_ttfb_ms": 80.0,
                "ojin_ttfb_ms": 90.0,
                "e2e_ms": 400.0,
                "perceived_e2e_ms": 300.0,
                "gap_ms": 60.0,
                "ojin_total_ms": 200.0,
                "filler_used": True,
            }
        )
        # An STS-style turn without a separate LLM measurement.
        trace.record_latency_report(
            {"tts_ttfb_ms": 70.0, "e2e_ms": 200.0, "llm_ttfb_ms": None, "filler_used": False}
        )

        other = trace.build()["otherData"]
        turns = other["latency_turns"]
        self.assertEqual(len(turns), 2)
        self.assertTrue(turns[0]["filler_used"])
        # None / missing fields are dropped, not stored as null.
        self.assertNotIn("llm_ttfb_ms", turns[1])

        summary = other["latency_ms"]
        self.assertEqual(summary["e2e_ms"]["count"], 2)
        self.assertAlmostEqual(summary["e2e_ms"]["min_ms"], 200.0, places=1)
        self.assertAlmostEqual(summary["e2e_ms"]["max_ms"], 400.0, places=1)
        # Only the first turn carried an LLM TTFB.
        self.assertEqual(summary["llm_ttfb_ms"]["count"], 1)

    def test_empty_report_is_skipped(self) -> None:
        trace, _ = _make_trace()
        trace.record_latency_report({"filler_used": True})  # no numeric fields
        other = trace.build()["otherData"]
        self.assertEqual(other["latency_turns"], [])
        self.assertEqual(other["latency_ms"], {})

    def test_draws_instant_and_counter_events(self) -> None:
        trace, _ = _make_trace()
        trace.record_latency_report({"e2e_ms": 300.0, "perceived_e2e_ms": 250.0})

        doc = trace.build()
        markers = [
            e
            for e in doc["traceEvents"]
            if e.get("ph") == "i" and e.get("name") == "latency_report"
        ]
        self.assertEqual(len(markers), 1)
        self.assertEqual(markers[0]["tid"], LANES["latency"])

        counters = {
            e["name"]
            for e in doc["traceEvents"]
            if e.get("ph") == "C" and e["name"] in ("e2e_ms", "perceived_e2e_ms")
        }
        self.assertEqual(counters, {"e2e_ms", "perceived_e2e_ms"})

    def test_summary_empty_by_default(self) -> None:
        trace, _ = _make_trace()
        other = trace.build()["otherData"]
        self.assertEqual(other["latency_ms"], {})
        self.assertEqual(other["latency_turns"], [])

    def test_records_are_frozen_after_write(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            trace = OjinSessionTrace(session_id="w", config_id="c", root_dir=tmp)
            trace.record_latency_report({"e2e_ms": 100.0})
            trace.write()
            # A turn completing during teardown (producer still holds a ref)
            # must not mutate the already-flushed doc.
            trace.record_latency_report({"e2e_ms": 999.0})

        summary = trace.build()["otherData"]["latency_ms"]
        self.assertEqual(summary["e2e_ms"]["count"], 1)
        self.assertAlmostEqual(summary["e2e_ms"]["max_ms"], 100.0, places=1)


if __name__ == "__main__":
    unittest.main()
