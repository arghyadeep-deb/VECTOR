"""Regression for vectorcode/src/connectors/scheduler.py:

SyncScheduler.stop() unconditionally set self._thread = None after its
join(timeout=5), regardless of whether the background thread actually
exited. If a sync cycle in progress outlasted the 5s join timeout, the
thread kept running but was no longer tracked -- a subsequent start() call
checks `self._thread is not None and self._thread.is_alive()` to refuse
spawning a duplicate, but with self._thread cleared to None that guard
always passed, letting two _loop() threads run concurrently.

Fixed: if the thread is still alive after the join timeout, stop() leaves
self._thread set (instead of clearing it) so start()'s existing guard
correctly detects it and refuses to start a second thread.
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from vectorcode.src.connectors.scheduler import SyncScheduler


def test_stop_does_not_clear_thread_reference_if_still_alive():
    scheduler = SyncScheduler(sync_engine=MagicMock(), interval_seconds=3600)

    # Simulate a thread that is still "running" (does not actually exit
    # within the join timeout) without waiting 5 real seconds in the test.
    still_running = threading.Event()

    def _never_ending():
        still_running.wait(timeout=10)

    thread = threading.Thread(target=_never_ending, daemon=True)
    thread.start()
    scheduler._thread = thread

    # Patch the join timeout down so the test doesn't actually block for 5s.
    original_join = thread.join

    def _fast_join(timeout=None):
        original_join(timeout=0.05)

    thread.join = _fast_join

    scheduler.stop()

    assert scheduler._thread is thread, (
        "stop() must not clear self._thread while the background thread "
        "is still alive -- doing so lets a later start() spawn a duplicate"
    )

    still_running.set()
    thread.join(timeout=2)


def test_start_refuses_duplicate_after_stop_leaves_thread_alive():
    scheduler = SyncScheduler(sync_engine=MagicMock(), interval_seconds=3600)

    still_running = threading.Event()
    thread = threading.Thread(target=lambda: still_running.wait(timeout=10), daemon=True)
    thread.start()
    scheduler._thread = thread
    thread.join = lambda timeout=None: time.sleep(0.05)

    scheduler.stop()
    first_thread = scheduler._thread

    scheduler.start()

    assert scheduler._thread is first_thread, (
        "start() must refuse to spawn a second background thread while "
        "the previous one (left tracked by stop()) is still alive"
    )

    still_running.set()
    thread.join(timeout=2)


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
