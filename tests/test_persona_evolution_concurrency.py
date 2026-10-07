"""Regression for core/persona/evolution.py PersonaEvolution:

__init__ created `self._lock = threading.RLock()` specifically to guard
concurrent access (sqlite3.connect(..., check_same_thread=False) explicitly
allows multi-thread use of the same connection), but record_signal() never
acquired it. _adjust_trait_from_signal()'s read-modify-write (SELECT the
current trait value, then UPDATE it +0.02) was therefore not atomic: two
threads calling record_signal() concurrently (PersonaManager.get() is a
process-wide singleton reachable from multiple districts/async tasks) could
both read the same old value and both write old+0.02, silently losing one
of the two increments.

Fixed by acquiring self._lock around record_signal()'s insert+adjust body.
"""
from __future__ import annotations

import tempfile
import threading
import time
from pathlib import Path

from core.persona.evolution import PersonaEvolution


class _SpyLock:
    """Wraps a real RLock, recording every acquire()/release() call."""

    def __init__(self, real_lock):
        self._real = real_lock
        self.calls: list[str] = []

    def acquire(self, *a, **kw):
        self.calls.append("acquire")
        return self._real.acquire(*a, **kw)

    def release(self, *a, **kw):
        self.calls.append("release")
        return self._real.release(*a, **kw)

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc):
        self.release()
        return False


class _SlowConnProxy:
    """Wraps a real sqlite3.Connection, sleeping after each SELECT on
    trait_values so concurrent threads reliably interleave the race window
    around the read-modify-write in _adjust_trait_from_signal()."""

    def __init__(self, real_conn, delay: float):
        self._real = real_conn
        self._delay = delay

    def execute(self, sql, params=()):
        result = self._real.execute(sql, params)
        if sql.strip().startswith("SELECT value FROM trait_values"):
            time.sleep(self._delay)
        return result

    def __getattr__(self, name):
        return getattr(self._real, name)


def test_record_signal_holds_lock_during_trait_update():
    with tempfile.TemporaryDirectory() as root:
        evo = PersonaEvolution(db_path=Path(root) / "evolution.db")
        try:
            spy = _SpyLock(evo._lock)
            evo._lock = spy
            evo.record_signal("task_completed")
            assert "acquire" in spy.calls, "record_signal() must hold self._lock while mutating trait_values"
        finally:
            evo.close()


def test_concurrent_record_signal_does_not_lose_trait_updates():
    with tempfile.TemporaryDirectory() as root:
        evo = PersonaEvolution(db_path=Path(root) / "evolution.db")
        try:
            # Seed the trait row so every subsequent call takes the UPDATE
            # (read-modify-write) path, not the INSERT path.
            evo.record_signal("task_completed")
            before = evo.get_evolved_traits()["reliability"]

            # Widen the race window around the SELECT so concurrent threads
            # reliably interleave without the lock.
            evo._conn = _SlowConnProxy(evo._conn, delay=0.03)

            n_threads = 6
            barrier = threading.Barrier(n_threads)

            def worker():
                barrier.wait()
                evo.record_signal("task_completed")

            threads = [threading.Thread(target=worker) for _ in range(n_threads)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            after = evo.get_evolved_traits()["reliability"]
            expected = round(min(1.0, before + 0.02 * n_threads), 3)
            assert round(after, 3) == expected, (
                f"expected reliability to accumulate all {n_threads} increments "
                f"({before} -> {expected}) but got {after} -- an update was lost to a race"
            )
        finally:
            evo.close()


if __name__ == "__main__":
    test_record_signal_holds_lock_during_trait_update()
    test_concurrent_record_signal_does_not_lose_trait_updates()
    print("OK - test_persona_evolution_concurrency.py")
