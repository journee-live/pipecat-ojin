"""Sinks for :class:`OjinSessionTrace` — the bot's multi-sink trace fan-out.

The bot-side counterpart to the inference server's ``session_metrics`` sinks.
A *sink* receives the built trace document (the dict returned by
:meth:`OjinSessionTrace.build`) once at session end and persists or forwards it
somewhere. :class:`OjinSessionTrace` fans the document out to every attached
sink, isolating failures so one sink erroring (e.g. a Sentry forwarder that hits
a network blip) never costs another (e.g. the Perfetto file on disk).

This mirrors modal-inference's ``MetricsSink`` protocol — a single
``write(snapshot)`` called once per session — but fans out to *N* sinks instead
of the server's one, which is exactly the "multiple sinks over the same trace"
shape the bot wants:

    trace = OjinSessionTrace(...)          # default: [PerfettoFileSink]
    trace.add_sink(SentryLatencySink())    # forward latency metrics too
    ...
    trace.write()                          # build() once, fan out to both

Sinks run synchronously on the asyncio event loop inside ``write()`` (called at
session stop), so they should be fast or fire-and-forget I/O.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Protocol, runtime_checkable

from loguru import logger


@runtime_checkable
class TraceSink(Protocol):
    """Anything that can persist/forward a built session-trace document.

    The document is the dict produced by :meth:`OjinSessionTrace.build`
    (``{"traceEvents": [...], "otherData": {...}}``). Implementations must not
    raise — :class:`OjinSessionTrace` guards each call, but a sink that swallows
    its own errors keeps the failure local and well-labelled.
    """

    def write(self, snapshot: dict) -> None:
        """Persist or forward the built session-trace document."""
        ...


class PerfettoFileSink:
    """Write the trace as one Chrome Trace Event Format ``session.json``.

    Path layout (unchanged from the trace's previous in-class writer)::

        <root_dir>/<YYYY-MM-DD>/<HH-MM-SS>_<session_id>/session.json

    derived from ``otherData.start_wall_iso`` + ``otherData.session_id`` so the
    sink needs nothing but the built document. Atomic write via tmp + replace.
    The written path is stashed on :attr:`path` so the trace can surface it for
    logging.
    """

    def __init__(self, root_dir: str = "/root/debug/sessions/bot") -> None:
        """Create a file sink writing under ``root_dir``."""
        self.root_dir = root_dir
        self.path: str | None = None

    def session_dir(self, snapshot: dict) -> str:
        """Return the session's output directory, derived from the doc header."""
        other = snapshot.get("otherData", {})
        session_id = other.get("session_id") or "unknown"
        start_iso = other.get("start_wall_iso")
        start = None
        if start_iso:
            try:
                start = datetime.fromisoformat(start_iso)
            except ValueError:
                start = None
        if start is None:
            # Never crash the flush on a malformed header; land it somewhere.
            day, stamp = "unknown-date", "unknown-time"
        else:
            day = start.strftime("%Y-%m-%d")
            stamp = start.strftime("%H-%M-%S")
        return os.path.join(self.root_dir, day, f"{stamp}_{session_id}")

    def write(self, snapshot: dict) -> None:
        """Atomically write the document to ``session.json`` (tmp + replace)."""
        out_dir = self.session_dir(snapshot)
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, "session.json")
        tmp = f"{path}.tmp"
        with open(tmp, "w") as f:
            json.dump(snapshot, f)
        os.replace(tmp, path)
        self.path = path


class NullSink:
    """Sink that drops everything — an explicit no-op for symmetry/tests."""

    def write(self, snapshot: dict) -> None:
        """Discard the document."""
        del snapshot
