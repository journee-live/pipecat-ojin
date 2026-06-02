"""Tests for the OjinSessionTrace sink layer.

The trace builds its document once at :meth:`write` and fans it out to every
attached :class:`TraceSink`, isolating per-sink failures so one sink erroring
never costs another (the bot-side equivalent of the inference server's single
``MetricsSink``, fanned out to N). These tests exercise that fan-out, the
failure isolation, and the default :class:`PerfettoFileSink` file output.
"""

import json
import os
import tempfile
import unittest

from pipecat.services.ojin.session_trace import OjinSessionTrace
from pipecat.services.ojin.trace_sinks import NullSink, PerfettoFileSink, TraceSink


class _CaptureSink:
    """Records every document it is handed (and how many times)."""

    def __init__(self) -> None:
        self.docs: list[dict] = []

    def write(self, snapshot: dict) -> None:
        self.docs.append(snapshot)


class _BoomSink:
    """A sink that always raises — stand-in for a flaky forwarder."""

    def __init__(self) -> None:
        self.calls = 0

    def write(self, snapshot: dict) -> None:
        self.calls += 1
        raise RuntimeError("boom")


def _trace(**kwargs) -> OjinSessionTrace:
    return OjinSessionTrace(session_id="s", config_id="c", **kwargs)


class TestPerfettoFileSink(unittest.TestCase):
    def test_satisfies_trace_sink_protocol(self) -> None:
        self.assertIsInstance(PerfettoFileSink(), TraceSink)
        self.assertIsInstance(NullSink(), TraceSink)

    def test_writes_session_json_with_expected_layout_and_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tr = _trace(root_dir=tmp)
            tr.record_latency_report({"e2e_ms": 100.0, "llm_ttfb_ms": 40.0})
            path = tr.write()

            # <root>/<YYYY-MM-DD>/<HH-MM-SS>_<session_id>/session.json
            self.assertIsNotNone(path)
            self.assertTrue(os.path.exists(path))
            self.assertEqual(os.path.basename(path), "session.json")
            self.assertTrue(path.startswith(tmp))
            self.assertIn("_s", os.path.basename(os.path.dirname(path)))

            doc = json.load(open(path))
            self.assertEqual(doc["otherData"]["session_id"], "s")
            self.assertEqual(doc["otherData"]["latency_turns"][0]["e2e_ms"], 100.0)

    def test_session_dir_falls_back_on_missing_header(self) -> None:
        sink = PerfettoFileSink(root_dir="/tmp/x")
        d = sink.session_dir({"otherData": {}})
        self.assertEqual(d, os.path.join("/tmp/x", "unknown-date", "unknown-time_unknown"))

    def test_no_temp_file_left_behind(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tr = _trace(root_dir=tmp)
            path = tr.write()
            leftovers = [p for p in os.listdir(os.path.dirname(path)) if p.endswith(".tmp")]
            self.assertEqual(leftovers, [])


class TestTraceFanOut(unittest.TestCase):
    def test_default_sink_is_perfetto_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tr = _trace(root_dir=tmp)
            path = tr.write()
            self.assertTrue(os.path.exists(path))

    def test_every_sink_receives_the_same_built_doc(self) -> None:
        a, b = _CaptureSink(), _CaptureSink()
        tr = _trace(sinks=[a, b])
        tr.record_latency_report({"e2e_ms": 7.0})
        tr.write()
        self.assertEqual(len(a.docs), 1)
        self.assertEqual(len(b.docs), 1)
        self.assertIs(a.docs[0], b.docs[0])  # build() runs once; same object fanned out
        self.assertEqual(a.docs[0]["otherData"]["latency_turns"][0]["e2e_ms"], 7.0)

    def test_failing_sink_does_not_block_others_and_still_freezes(self) -> None:
        boom, cap = _BoomSink(), _CaptureSink()
        with tempfile.TemporaryDirectory() as tmp:
            file_sink = PerfettoFileSink(root_dir=tmp)
            tr = _trace(sinks=[boom, file_sink, cap])
            path = tr.write()

            self.assertEqual(boom.calls, 1)
            self.assertEqual(len(cap.docs), 1, "capture sink ran despite Boom raising")
            self.assertIsNotNone(path)
            self.assertTrue(os.path.exists(path), "file sink ran despite Boom raising")
            # write() returns the PerfettoFileSink path even when an earlier sink raised.
            self.assertEqual(path, file_sink.path)

    def test_write_returns_none_when_no_file_sink(self) -> None:
        tr = _trace(sinks=[_CaptureSink()])
        self.assertIsNone(tr.write())

    def test_second_write_is_a_noop(self) -> None:
        cap = _CaptureSink()
        tr = _trace(sinks=[cap])
        tr.write()
        tr.write()
        self.assertEqual(len(cap.docs), 1)

    def test_add_sink_attaches_before_write(self) -> None:
        cap = _CaptureSink()
        tr = _trace(sinks=[NullSink()])
        tr.add_sink(cap)
        tr.write()
        self.assertEqual(len(cap.docs), 1)

    def test_add_sink_after_write_is_a_noop(self) -> None:
        cap = _CaptureSink()
        tr = _trace(sinks=[NullSink()])
        tr.write()
        tr.add_sink(cap)
        self.assertEqual(len(cap.docs), 0)


if __name__ == "__main__":
    unittest.main()
