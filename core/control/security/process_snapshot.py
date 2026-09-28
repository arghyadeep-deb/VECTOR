"""Per-process CPU / memory table for the HUD, produced by a CHILD process (run as a script, not imported by the API).

Why out of process: on Windows psutil answers every per-process cpu / memory / status query with a whole-system
NtQuerySystemInformation call that HOLDS THE GIL. Measured 2026-09-27 on this machine (363 processes, py-spy on the running
API): status() 7.3 s, cpu_percent 3.3 s, memory_percent 3.2 s per full sweep, 67% of all GIL time in the API process, and every
request -- the autonomous loop, the HUD websockets, /agents -- froze for 15-27 s roughly every 30 s. A worker thread does not
help (the GIL is the shared resource); a child process does.

`table` mode is standalone on purpose (stdlib + psutil only); `anomalies` mode imports the detector from `core`.
Usage:  python process_snapshot.py table [limit]  -> JSON list of {name, cpu, mem, status}
        python process_snapshot.py anomalies      -> JSON list of {pid, name, exe, suspicious, reason}
                                                     (core.control.security.threat_detector.scan_processes_inprocess)
"""
from __future__ import annotations

import json
import sys
import time

import psutil

_SAMPLE_GAP_S = 0.5


def collect(limit: int = 20) -> list[dict]:
    """Top `limit` processes by CPU share of the whole machine. Never raises."""
    ncpu = psutil.cpu_count(logical=True) or 1
    procs = []
    for p in psutil.process_iter():
        try:
            if p.pid == 0:
                continue  # the idle pseudo-process reports (idle x cores) percent -- it is not load
            p.cpu_percent(None)  # first call only primes the counter
            procs.append(p)
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            continue
    time.sleep(_SAMPLE_GAP_S)
    ranked = []
    for p in procs:
        try:
            ranked.append((p.cpu_percent(None), p))
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            continue
    ranked.sort(key=lambda t: t[0], reverse=True)
    rows = []
    for cpu, p in ranked[: max(1, limit)]:
        try:
            name = p.name() or "unknown"
            if name == "System Idle Process":
                continue
            rows.append({
                "name": name[:50],
                # psutil's per-process cpu_percent is summed over cores; report the share of the whole machine
                "cpu": round(min(100.0, cpu / ncpu), 1),
                "mem": round(p.memory_percent() or 0.0, 1),
                "status": p.status() or "unknown",
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            continue
    return rows


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "table"
    if mode == "anomalies":
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # repo root, so `core` imports
        from core.control.security.threat_detector import scan_processes_inprocess

        sys.stdout.write(json.dumps(scan_processes_inprocess()))
    else:
        lim = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 20
        sys.stdout.write(json.dumps(collect(lim)))
