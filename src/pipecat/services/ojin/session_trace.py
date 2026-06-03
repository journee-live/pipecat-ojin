"""Client/bot-side session trace for OjinVideoService.

Produces a Perfetto / Chrome Trace Event Format JSON per session — the bot-side
counterpart to the inference server's ``session_metrics.json``. Open the file in
https://ui.perfetto.dev to inspect every audio/video event on one timeline (and
diff it against the server's trace, which uses the same format).

Design mirrors the server's ``session_metrics`` module (recorder builds a doc,
atomic write on stop) but is deliberately lighter: every OjinVideoService
producer — ``process_frame``, the receive loop, and the playback loop — runs on
the SAME asyncio event loop, so there is no cross-thread access and no locking.
Each record is one cheap ``deque.append`` (bounded, evict-oldest), guarded by a
single ``None`` check at the call site, so it costs ~nothing when disabled.

On :meth:`write` (session stop) the trace builds the document once and fans it
out to every attached :class:`~pipecat.services.ojin.trace_sinks.TraceSink`,
isolating failures so one sink erroring never costs another. By default a single
:class:`~pipecat.services.ojin.trace_sinks.PerfettoFileSink` is attached, which
writes::

    /root/debug/sessions/bot/{YYYY-MM-DD}/{HH-MM-SS}_{session_id}/session.json

Callers attach more sinks — e.g. a Sentry latency forwarder — via the
constructor's ``sinks=`` or :meth:`add_sink`, the bot-side equivalent of the
inference server's single ``MetricsSink`` but fanned out to N sinks.

Lanes (Perfetto threads), grouped so the received stream and the played stream
are split by frame type (speech / new-turn / idle / fade), making a
post-interruption desync between "what arrived" and "what played" obvious:

    lifecycle      session + connect spans
    tts_input      TTS frames in from upstream
    to_server      audio + cancel sent to the inference server
    recv:*         frames received from the server, split by type
    play:*         frames emitted downstream, split by type
    play_audio     audio chunks emitted (real / silenced / underrun)
    buffers        audio-buffer queue + swaps
    interruption   barge-in + cancel→new-turn round-trip
    speaking       bot speaking spans
    lipsync        swap-time audio alignment corrections
    response       first TTS audio → first speech video frame (turn latency)
    latency        per-turn end-to-end latency reports from the bot pipeline

Per-turn video response latency is anchored at the first TTS audio frame of the
turn (when the bot's speech starts flowing into the avatar) and recorded at two
endpoints, each a span on the ``response`` lane: ``recv`` (first speech video
frame arriving from the server — the Ojin inference round-trip) and ``played``
(that frame reaching the transport downstream — adds bot-side buffering/playback
delay). Both are summarised under ``otherData.response_latency_ms`` (count / min
/ max / mean / p50 / last per endpoint), so the avatar's response time and where
it is spent are readable without opening Perfetto.

The bot pipeline's per-turn latency breakdown (STT / LLM / TTS / Ojin TTFB,
end-to-end and perceived end-to-end, pipeline gap) is fed in via
:meth:`OjinSessionTrace.record_latency_report`: each completed turn is drawn as
an instant marker on the ``latency`` lane (full breakdown in its args) with
counter events for the headline E2E figures, and the raw per-turn list plus a
per-field summary are written under ``otherData.latency_turns`` /
``otherData.latency_ms``.
"""

from __future__ import annotations

import os
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Callable, Dict, Optional, Sequence

from loguru import logger

from pipecat.services.ojin.trace_sinks import PerfettoFileSink, TraceSink

# Perfetto thread (lane) ids. Stable integers; names are attached via ``M``
# metadata events at build time.
LANES: Dict[str, int] = {
    "lifecycle": 1,
    "tts_input": 2,
    "to_server": 3,
    "recv:speech": 4,
    "recv:new_turn": 5,
    "recv:idle": 6,
    "recv:fade": 7,
    "play:speech": 8,
    "play:new_turn": 9,
    "play:idle": 10,
    "play:fade": 11,
    "play:repeat": 12,
    "play_audio": 13,
    "buffers": 14,
    "interruption": 15,
    "speaking": 16,
    "lipsync": 17,
    "response": 18,
    "latency": 19,
}

# frame_type wire marker (0/1/2/3) → received-stream lane.
_RECV_LANE_FOR_FRAME_TYPE = {
    0: "recv:idle",
    1: "recv:speech",
    2: "recv:fade",
    3: "recv:new_turn",
}
# frame_type wire marker → played-stream lane.
_PLAY_LANE_FOR_FRAME_TYPE = {
    0: "play:idle",
    1: "play:speech",
    2: "play:fade",
    3: "play:new_turn",
}


def recv_lane_for_frame_type(frame_type: int) -> str:
    """Return the received-stream lane name for a wire ``frame_type`` marker."""
    return _RECV_LANE_FOR_FRAME_TYPE.get(frame_type, "recv:speech")


def play_lane_for_frame_type(frame_type: int) -> str:
    """Return the played-stream lane name for a wire ``frame_type`` marker."""
    return _PLAY_LANE_FOR_FRAME_TYPE.get(frame_type, "play:speech")


def new_session_id() -> str:
    """Return a short random session id (12 hex chars)."""
    return uuid.uuid4().hex[:12]


def session_trace_enabled(default: bool = True) -> bool:
    """Whether to write the per-session Perfetto trace.

    On for every session by default; ``OJIN_BOT_SESSION_TRACE=0`` (or
    ``false``/``no``/``off``) is a kill-switch, read at session start so it can
    be toggled without a code change. ``default=False`` forces it off regardless
    of the env var.
    """
    if not default:
        return False
    env = os.getenv("OJIN_BOT_SESSION_TRACE")
    if env is not None and env.strip().lower() in {"0", "false", "no", "off"}:
        return False
    return True


class OjinSessionTrace:
    """Accumulates Chrome-Trace events for one OjinVideoService session."""

    SCHEMA_VERSION = 2

    # Numeric latency fields recorded per turn (display order). Mirrors the
    # bot's LatencyReportFrame; a turn may not have every stage measured (e.g.
    # STS pipelines without a separate LLM), so each is optional.
    _LATENCY_FIELDS = (
        "e2e_ms",
        "perceived_e2e_ms",
        "stt_ttfb_ms",
        "llm_ttfb_ms",
        "tts_ttfb_ms",
        "ojin_ttfb_ms",
        "gap_ms",
        "ojin_total_ms",
    )

    def __init__(
        self,
        *,
        session_id: Optional[str] = None,
        config_id: str = "",
        pid: int = 1,
        clock: Callable[[], float] = time.perf_counter,
        max_events: int = 500_000,
        root_dir: str = "/root/debug/sessions/bot",
        sinks: Optional[Sequence[TraceSink]] = None,
    ) -> None:
        """Create a session trace; defaults to a single Perfetto file sink."""
        self.session_id = session_id or new_session_id()
        self.config_id = config_id
        self._pid = pid
        self._clock = clock
        self._t0 = clock()
        self._start_wall = datetime.now(timezone.utc)
        self._events: deque[dict] = deque(maxlen=max_events)
        self._root_dir = root_dir
        # Sinks the built document is fanned out to on :meth:`write`. Defaults
        # to the Perfetto file writer (the trace's original behaviour); callers
        # attach more (e.g. a Sentry latency forwarder) via the constructor or
        # :meth:`add_sink`. Mirrors the inference server's single ``MetricsSink``
        # but fans out to N sinks over the one trace.
        self._sinks: list[TraceSink] = (
            [PerfettoFileSink(root_dir=root_dir)] if sinks is None else list(sinks)
        )
        self._evicted = 0
        # Lightweight running summary for otherData.
        self._counts: Dict[str, int] = {}
        # Per-turn video response latencies in ms, anchored at the first TTS
        # audio frame of the turn. Two series: "recv" = first speech video frame
        # arriving from the server (Ojin inference round-trip), "played" = that
        # frame reaching the transport downstream (adds bot-side buffering/
        # playback delay). Bounded; summarised into otherData at build time.
        self._response_latencies: Dict[str, deque[float]] = {
            "recv": deque(maxlen=10_000),
            "played": deque(maxlen=10_000),
        }
        # Per-turn end-to-end latency breakdowns fed from the bot pipeline's
        # LatencyTracker (same event loop, so plain append — no locking). The
        # raw list and a per-field summary are written to otherData; each turn
        # is also drawn on the ``latency`` lane at record time.
        self._latency_turns: deque[dict] = deque(maxlen=10_000)
        # Frozen once :meth:`write` has flushed to disk. Producers may keep a
        # reference (e.g. the bot's LatencyTracker holds its own), so further
        # records after the flush are dropped rather than appended to a doc that
        # will never be written again.
        self._written = False

    # -- time -----------------------------------------------------------

    def now_us(self) -> float:
        """Microseconds since session start (Perfetto ts domain)."""
        return (self._clock() - self._t0) * 1e6

    def mark(self) -> float:
        """Capture a start timestamp (µs) for a later :meth:`span`."""
        return self.now_us()

    # -- recording (all O(1); single event loop, no locking) ------------

    def _append(self, ev: dict) -> None:
        if self._written:
            return
        if len(self._events) == self._events.maxlen:
            self._evicted += 1
        self._events.append(ev)

    def _bump(self, name: str) -> None:
        self._counts[name] = self._counts.get(name, 0) + 1

    def instant(self, lane: str, name: str, *, cat: str = "", args: Optional[dict] = None) -> None:
        """Record an instant marker event (``ph='i'``) on ``lane``."""
        self._append(
            {
                "name": name,
                "cat": cat or lane,
                "ph": "i",
                "ts": self.now_us(),
                "pid": self._pid,
                "tid": LANES[lane],
                "s": "t",
                "args": args or {},
            }
        )
        self._bump(name)

    def span(
        self,
        lane: str,
        name: str,
        start_us: float,
        *,
        cat: str = "",
        args: Optional[dict] = None,
    ) -> None:
        """Record a completed duration event (``ph='X'``) from ``start_us`` to now."""
        dur = self.now_us() - start_us
        self._append(
            {
                "name": name,
                "cat": cat or lane,
                "ph": "X",
                "ts": start_us,
                "dur": max(dur, 1.0),
                "pid": self._pid,
                "tid": LANES[lane],
                "args": args or {},
            }
        )
        self._bump(name)

    def counter(self, name: str, value: float, *, extra: Optional[dict] = None) -> None:
        """Record a counter (line-plot) event (``ph='C'``) for ``name``."""
        series = {name: value}
        if extra:
            series.update(extra)
        self._append(
            {
                "name": name,
                "ph": "C",
                "ts": self.now_us(),
                "pid": self._pid,
                "args": series,
            }
        )

    def record_response_latency(
        self, kind: str, start_us: float, *, args: Optional[dict] = None
    ) -> float:
        """Record a first-TTS → first-speech-video span; return its ms value.

        ``start_us`` is the :meth:`mark` captured at the first TTS audio frame
        of the turn. ``kind`` selects the endpoint being measured: ``"recv"``
        (the first speech video frame arriving from the server) or ``"played"``
        (that frame reaching the transport downstream). The duration is drawn as
        a span on the ``response`` lane and fed into the matching
        ``response_latency_ms`` summary in :meth:`build`'s ``otherData``.
        """
        latency_ms = (self.now_us() - start_us) / 1000.0
        if not self._written:
            self.span("response", f"first_tts→first_video_{kind}", start_us, args=args)
            self._response_latencies[kind].append(latency_ms)
        return round(latency_ms, 1)

    @staticmethod
    def _summarise_latencies(vals: list) -> Dict[str, float]:
        if not vals:
            return {"count": 0}
        ordered = sorted(vals)
        return {
            "count": len(vals),
            "min_ms": round(ordered[0], 1),
            "max_ms": round(ordered[-1], 1),
            "mean_ms": round(sum(vals) / len(vals), 1),
            "p50_ms": round(ordered[len(ordered) // 2], 1),
            "last_ms": round(vals[-1], 1),
        }

    def _response_latency_summary(self) -> Dict[str, dict]:
        """Aggregate per-turn response latencies (recv + played) for ``otherData``."""
        return {
            kind: self._summarise_latencies(list(series))
            for kind, series in self._response_latencies.items()
        }

    def record_latency_report(self, metrics: dict) -> None:
        """Record one completed turn's end-to-end latency breakdown.

        ``metrics`` is the per-turn report produced by the bot pipeline's
        ``LatencyTracker`` (STT / LLM / TTS / Ojin TTFB, E2E, perceived E2E,
        pipeline gap). Known numeric fields are kept for the
        ``otherData.latency_ms`` summary and the raw per-turn list, and the turn
        is drawn as an instant marker on the ``latency`` lane (full breakdown in
        its args) plus a counter per headline E2E figure — so the bot-side
        latency is visible on the Perfetto timeline next to the avatar's video
        response latency. Missing/non-numeric fields are tolerated (a turn need
        not measure every stage). No-op once the trace has been written.
        """
        if self._written:
            return
        record: dict = {}
        for field in self._LATENCY_FIELDS:
            val = metrics.get(field)
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                record[field] = val
        if "filler_used" in metrics:
            record["filler_used"] = bool(metrics["filler_used"])
        # Nothing measurable this turn — skip rather than store an empty row.
        if not any(k in record for k in self._LATENCY_FIELDS):
            return
        self._latency_turns.append(record)
        self.instant("latency", "latency_report", args=record)
        for key in ("e2e_ms", "perceived_e2e_ms"):
            if key in record:
                self.counter(key, record[key])

    def _latency_report_summary(self) -> Dict[str, dict]:
        """Aggregate per-turn bot latency reports (per field) for ``otherData``."""
        summary: Dict[str, dict] = {}
        for field in self._LATENCY_FIELDS:
            vals = [
                t[field]
                for t in self._latency_turns
                if isinstance(t.get(field), (int, float)) and not isinstance(t.get(field), bool)
            ]
            if vals:
                summary[field] = self._summarise_latencies(vals)
        return summary

    # -- build + write --------------------------------------------------

    def build(self) -> dict:
        """Return the Chrome Trace document (events + ``otherData`` summary)."""
        meta = [{"name": "process_name", "ph": "M", "pid": self._pid, "args": {"name": "ojin_bot"}}]
        for lane, tid in LANES.items():
            meta.append(
                {
                    "name": "thread_name",
                    "ph": "M",
                    "pid": self._pid,
                    "tid": tid,
                    "args": {"name": lane},
                }
            )
        return {
            "traceEvents": meta + list(self._events),
            "otherData": {
                "schema_version": self.SCHEMA_VERSION,
                "producer": "ojin_video_service",
                "session_id": self.session_id,
                "config_id": self.config_id,
                "start_wall_iso": self._start_wall.isoformat(),
                "duration_s": round(self._clock() - self._t0, 3),
                "event_count": len(self._events),
                "events_evicted_overflow": self._evicted,
                "event_counts": dict(self._counts),
                "response_latency_ms": self._response_latency_summary(),
                "latency_ms": self._latency_report_summary(),
                "latency_turns": list(self._latency_turns),
            },
        }

    def session_dir(self) -> str:
        """Return this session's default output directory (under ``root_dir``)."""
        day = self._start_wall.strftime("%Y-%m-%d")
        stamp = self._start_wall.strftime("%H-%M-%S")
        return os.path.join(self._root_dir, day, f"{stamp}_{self.session_id}")

    def add_sink(self, sink: TraceSink) -> None:
        """Attach another sink to receive the built document at :meth:`write`.

        No-op once the trace has been written (the doc is already flushed).
        """
        if self._written:
            return
        self._sinks.append(sink)

    def write(self) -> Optional[str]:
        """Build the trace document once and hand it to every attached sink.

        Each sink is isolated: one failing (e.g. a Sentry forwarder hitting a
        network blip) neither raises nor stops the others (e.g. the Perfetto
        file on disk). Freezes the trace afterwards — any further records (e.g.
        a turn that completes during teardown, via a producer that still holds a
        reference) are dropped rather than mutating an already-flushed doc.

        Returns the path written by the first :class:`PerfettoFileSink`, if any,
        for back-compat logging at the call site.
        """
        if self._written:
            return None
        doc = self.build()
        first_path: Optional[str] = None
        for sink in self._sinks:
            try:
                sink.write(doc)
            except Exception as e:
                logger.warning(f"trace sink {type(sink).__name__} write failed: {e}")
                continue
            path = getattr(sink, "path", None)
            if isinstance(path, str) and first_path is None:
                first_path = path
        self._written = True
        return first_path
