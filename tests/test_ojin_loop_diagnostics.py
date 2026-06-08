"""Tests for OjinVideoService event-loop stall diagnostics.

Covers the instrumentation added after the audio_freeze investigation, where a
~0.66s synchronous block on the bot's asyncio loop froze both playback and the
websocket reader while the server kept pacing:

* ``_loop_stall_watchdog`` — a background thread that dumps all thread stacks
  when a playback tick fails to advance within the threshold (and is silent
  while playback is paused or ticks are advancing).
* ``_loop_exception_handler`` — names the connection (peer/host/fd) behind a
  socket error and delegates to the previous handler, never raising.
"""

import threading
import time
import unittest
from unittest.mock import MagicMock

import pipecat.services.ojin.video as video_mod
from pipecat.services.ojin.video import OjinVideoService, OjinVideoSettings


def _make_service() -> OjinVideoService:
    return OjinVideoService(settings=OjinVideoSettings(), client=MagicMock())


class TestLoopExceptionHandler(unittest.TestCase):
    """The handler extracts transport identity and always delegates."""

    def test_extracts_transport_info_and_delegates(self) -> None:
        s = _make_service()
        prev = MagicMock()
        s._prev_loop_exc_handler = prev
        loop = MagicMock()
        sock = MagicMock()
        sock.fileno.return_value = 63
        transport = MagicMock()
        transport.get_extra_info.side_effect = lambda k: {
            "peername": ("1.2.3.4", 443),
            "sockname": ("10.0.0.2", 51000),
            "server_hostname": "models.ojin.foo",
            "socket": sock,
        }.get(k)
        ctx = {
            "message": "Fatal error on SSL transport",
            "transport": transport,
            "exception": OSError(9, "Bad file descriptor"),
        }

        s._loop_exception_handler(loop, ctx)

        prev.assert_called_once_with(loop, ctx)
        transport.get_extra_info.assert_any_call("peername")
        transport.get_extra_info.assert_any_call("server_hostname")
        transport.get_extra_info.assert_any_call("socket")

    def test_no_prev_handler_delegates_to_default(self) -> None:
        s = _make_service()
        s._prev_loop_exc_handler = None
        loop = MagicMock()

        s._loop_exception_handler(loop, {"message": "boom"})

        loop.default_exception_handler.assert_called_once()

    def test_never_raises_on_bad_transport(self) -> None:
        s = _make_service()
        s._prev_loop_exc_handler = None
        loop = MagicMock()
        bad = MagicMock()
        bad.get_extra_info.side_effect = RuntimeError("transport is dead")

        # Must swallow the introspection failure and still delegate.
        s._loop_exception_handler(loop, {"transport": bad})
        loop.default_exception_handler.assert_called_once()


class TestStallWatchdog(unittest.TestCase):
    """The watchdog dumps only on a genuine stall."""

    def _run_watchdog(self, service, *, threshold_s=0.05, hold_s, pet=False):
        calls: list = []
        orig = video_mod.faulthandler.dump_traceback
        video_mod.faulthandler.dump_traceback = lambda **_k: calls.append(1)
        stop = threading.Event()
        th = threading.Thread(
            target=service._loop_stall_watchdog,
            args=(threshold_s, stop),
            daemon=True,
        )
        th.start()
        try:
            deadline = time.time() + hold_s
            while time.time() < deadline:
                if pet:
                    service._last_tick_perf = time.perf_counter()
                if calls and not pet:
                    break
                time.sleep(0.02)
        finally:
            stop.set()
            th.join(1.0)
            video_mod.faulthandler.dump_traceback = orig
        return calls

    def test_dumps_when_tick_is_stale(self) -> None:
        s = _make_service()
        s._playback_paused = False
        s._last_tick_perf = time.perf_counter() - 1.0  # 1s since last tick
        calls = self._run_watchdog(s, hold_s=2.0)
        self.assertTrue(calls, "watchdog must dump when the playback tick is stale")

    def test_no_dump_while_paused(self) -> None:
        s = _make_service()
        s._playback_paused = True
        s._last_tick_perf = time.perf_counter() - 1.0  # stale, but paused
        calls = self._run_watchdog(s, hold_s=0.4)
        self.assertFalse(calls, "watchdog must stay silent while playback is paused")

    def test_no_dump_while_ticks_advance(self) -> None:
        s = _make_service()
        s._playback_paused = False
        s._last_tick_perf = time.perf_counter()
        calls = self._run_watchdog(s, hold_s=0.4, pet=True)
        self.assertFalse(calls, "watchdog must stay silent while ticks keep advancing")


if __name__ == "__main__":
    unittest.main()
