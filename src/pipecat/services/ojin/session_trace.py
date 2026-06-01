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

Layout written to::

    /root/debug/sessions/bot/{YYYY-MM-DD}/{HH-MM-SS}_{session_id}/session.json

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

Per-turn video response latency is anchored at the first TTS audio frame of the
turn (when the bot's speech starts flowing into the avatar) and recorded at two
endpoints, each a span on the ``response`` lane: ``recv`` (first speech video
frame arriving from the server — the Ojin inference round-trip) and ``played``
(that frame reaching the transport downstream — adds bot-side buffering/playback
delay). Both are summarised under ``otherData.response_latency_ms`` (count / min
/ max / mean / p50 / last per endpoint), so the avatar's response time and where
it is spent are readable without opening Perfetto.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Callable, Dict, Optional

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
}

# frame_idx wire marker (0/1/2/3) → received-stream lane.
_RECV_LANE_FOR_IDX = {
    0: "recv:idle",
    1: "recv:speech",
    2: "recv:fade",
    3: "recv:new_turn",
}
# frame_idx wire marker → played-stream lane.
_PLAY_LANE_FOR_IDX = {
    0: "play:idle",
    1: "play:speech",
    2: "play:fade",
    3: "play:new_turn",
}


def recv_lane_for_idx(frame_idx: int) -> str:
    return _RECV_LANE_FOR_IDX.get(frame_idx, "recv:speech")


def play_lane_for_idx(frame_idx: int) -> str:
    return _PLAY_LANE_FOR_IDX.get(frame_idx, "play:speech")


def new_session_id() -> str:
    return uuid.uuid4().hex[:12]


class OjinSessionTrace:
    """Accumulates Chrome-Trace events for one OjinVideoService session."""

    SCHEMA_VERSION = 2

    def __init__(
        self,
        *,
        session_id: Optional[str] = None,
        config_id: str = "",
        pid: int = 1,
        clock: Callable[[], float] = time.perf_counter,
        max_events: int = 500_000,
        root_dir: str = "/root/debug/sessions/bot",
    ) -> None:
        self.session_id = session_id or new_session_id()
        self.config_id = config_id
        self._pid = pid
        self._clock = clock
        self._t0 = clock()
        self._start_wall = datetime.now(timezone.utc)
        self._events: deque[dict] = deque(maxlen=max_events)
        self._root_dir = root_dir
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

    # -- time -----------------------------------------------------------

    def now_us(self) -> float:
        """Microseconds since session start (Perfetto ts domain)."""
        return (self._clock() - self._t0) * 1e6

    def mark(self) -> float:
        """Capture a start timestamp (µs) for a later :meth:`span`."""
        return self.now_us()

    # -- recording (all O(1); single event loop, no locking) ------------

    def _append(self, ev: dict) -> None:
        if len(self._events) == self._events.maxlen:
            self._evicted += 1
        self._events.append(ev)

    def _bump(self, name: str) -> None:
        self._counts[name] = self._counts.get(name, 0) + 1

    def instant(self, lane: str, name: str, *, cat: str = "", args: Optional[dict] = None) -> None:
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

    # -- build + write --------------------------------------------------

    def build(self) -> dict:
        meta = [
            {"name": "process_name", "ph": "M", "pid": self._pid, "args": {"name": "ojin_bot"}}
        ]
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
            },
        }

    def session_dir(self) -> str:
        day = self._start_wall.strftime("%Y-%m-%d")
        stamp = self._start_wall.strftime("%H-%M-%S")
        return os.path.join(self._root_dir, day, f"{stamp}_{self.session_id}")

    def write(self) -> str:
        """Atomically write the trace; returns the path."""
        out_dir = self.session_dir()
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, "session.json")
        tmp = f"{path}.tmp"
        with open(tmp, "w") as f:
            json.dump(self.build(), f)
        os.replace(tmp, path)
        return path
