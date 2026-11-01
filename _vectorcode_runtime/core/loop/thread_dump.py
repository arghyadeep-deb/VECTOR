"""Opt-in thread-stack dumper for diagnosing a stalled autonomous loop.

KNOWN_ISSUES.md issue 0 (2026-08-05): the loop thread has been observed to
silently stop ticking after ~5.5 hours while the API process stays alive and
`/health` keeps answering ok. Captured live: heartbeat frozen at
tick_count=1921 with an 894s-old mtime, process alive with 95 threads and
1.1GB working set, and 0 seconds of CPU consumed over a 20-second sample —
the loop thread is BLOCKED, not spinning and not crashed. No traceback was
logged anywhere, so the root cause is still unknown.

`faulthandler.dump_traceback_later(timeout, repeat=True, file=...)` writes
every thread's Python stack to a file on a timer — exactly the evidence
needed the next time this happens, since the process is alive but stuck
(a debugger attach or SIGABRT-style crash dump isn't available/appropriate
here; this is the standard-library tool built for precisely this case).

OFF by default — costs nothing in normal operation. To turn it on for the
next occurrence (PowerShell, before starting VECTOR):

    $env:VECTOR_THREAD_DUMP_SEC = "300"
    python run_vector.py api --host 0.0.0.0

or for the Task Scheduler / watchdog-launched process, set it as a machine/
user environment variable (`setx VECTOR_THREAD_DUMP_SEC 300`) so every
future launch picks it up. 300s (5 min) is a reasonable starting interval —
lower it (e.g. 60) if a faster catch is worth the extra log volume.

Dumps are written to `data/logs/thread_dumps.log` (under VECTOR_DATA_DIR if
set), never stdout — stdout is already ~12MB of uvicorn access logs and a
stack dump would be buried in it.
"""
import os
import threading
from typing import Optional

from loguru import logger

_lock = threading.Lock()
_enabled = False
_dump_file = None  # kept open for the process lifetime; faulthandler writes to it directly


def enable_if_requested() -> Optional[str]:
    """Enable the timed thread-stack dump if VECTOR_THREAD_DUMP_SEC is set.

    Idempotent and safe to call from multiple entry points (run_vector.py's
    `loop` mode and core/api/app.py's in-process brain thread both call this
    — whichever runs first wins; faulthandler state is process-global).

    Returns the dump file path (str) if enabled, else None. Never raises —
    this is diagnostics, it must not be able to break the loop it's meant to
    help debug.
    """
    global _enabled, _dump_file

    with _lock:
        if _enabled:
            return str(_dump_file.name) if _dump_file else None

        raw = os.environ.get("VECTOR_THREAD_DUMP_SEC", "").strip()
        if not raw:
            return None

        try:
            interval = float(raw)
            if interval <= 0:
                logger.warning(
                    "[VECTOR][thread_dump] VECTOR_THREAD_DUMP_SEC={} must be > 0, skipping", raw
                )
                return None
        except ValueError:
            logger.warning(
                "[VECTOR][thread_dump] VECTOR_THREAD_DUMP_SEC={!r} is not a number, skipping", raw
            )
            return None

        try:
            import faulthandler

            from core.runtime_paths import data_path

            logs_dir = data_path("logs")
            logs_dir.mkdir(parents=True, exist_ok=True)
            dump_path = logs_dir / "thread_dumps.log"

            # Roll before opening. Measured: ~850 KB/hour at a 60s interval, and
            # once the watchdog arms this on every restart (2026-08-06, active
            # P0 hunt) it runs continuously. Unbounded append is a mistake this
            # repo has already paid for — vector_autostart.log was found at
            # 671 MB with no rotation. Same one-generation policy as that fix
            # and vector_watchdog.ps1: past 25 MB the current file becomes
            # .log.1, replacing any previous .1.
            #
            # Rolling here (at arm time, before the handle is opened) rather
            # than mid-run is deliberate: faulthandler writes into the raw fd,
            # so renaming the file underneath a live dump would send stacks to
            # a file nobody is looking at.
            try:
                if dump_path.exists() and dump_path.stat().st_size > 25 * 1024 * 1024:
                    prev = dump_path.with_suffix(dump_path.suffix + ".1")
                    if prev.exists():
                        prev.unlink()
                    dump_path.rename(prev)
            except Exception as _roll_err:  # never let rotation break diagnostics
                logger.warning("[VECTOR][thread_dump] dump-log rotation skipped: {}", _roll_err)

            # Append mode + line-buffered-ish: faulthandler writes straight into
            # the raw file descriptor, bypassing loguru entirely, so the file
            # must stay open for the life of the process.
            f = open(dump_path, "a", encoding="utf-8")
            faulthandler.dump_traceback_later(interval, repeat=True, file=f)
            _dump_file = f
            _enabled = True
            logger.warning(
                "[VECTOR][thread_dump] ENABLED via VECTOR_THREAD_DUMP_SEC={} — "
                "dumping all thread stacks every {}s to {}",
                raw, interval, dump_path,
            )
            return str(dump_path)
        except Exception as e:
            logger.warning("[VECTOR][thread_dump] failed to enable: {}", e)
            return None


def disable() -> None:
    """Stop the timed dump (mainly for tests). Best-effort."""
    global _enabled, _dump_file
    with _lock:
        try:
            import faulthandler
            faulthandler.cancel_dump_traceback_later()
        except Exception:
            pass
        if _dump_file is not None:
            try:
                _dump_file.close()
            except Exception:
                pass
        _dump_file = None
        _enabled = False


if __name__ == "__main__":
    import tempfile
    import time as _time

    # Real, no-mock smoke test: enable a fast dump, let it fire, verify the
    # file actually contains thread stacks, then clean up.
    tmp_dir = tempfile.mkdtemp(prefix="vector_thread_dump_test_")
    os.environ["VECTOR_TEST_DATA_DIR"] = tmp_dir
    os.environ["VECTOR_THREAD_DUMP_SEC"] = "1"

    path = enable_if_requested()
    assert path, "enable_if_requested() should have returned a path"
    _time.sleep(2.5)
    disable()

    with open(path, encoding="utf-8") as f:
        content = f.read()
    assert "Thread" in content or "Current thread" in content, (
        f"dump file has no recognizable thread-stack content: {content[:300]!r}"
    )
    print(f"dump written to {path}, {len(content)} bytes")
    print("✅ thread_dump.py OK")
