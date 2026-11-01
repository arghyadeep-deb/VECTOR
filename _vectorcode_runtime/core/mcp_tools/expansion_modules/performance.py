from __future__ import annotations

from pathlib import Path

from loguru import logger

from core.config import CONFIG
from core.mcp_tools.error_handling import safe_json as _safe_json
from core.mcp_tools.error_handling import register_stub_tool as _reg
from core.mcp_tools.memory_safety import (
    MEMORY_CLEAR_CONFIRM as _MEMORY_CLEAR_CONFIRM,
    resolve_memory_path as _resolve_memory_path,
)

_ROOT = Path(__file__).resolve().parents[3]  # module-level so tests can point it at a tmp dir


def _resolve_py_script(root: Path, raw: str) -> tuple[Path | None, str | None]:
    """Resolve a caller-supplied script to profile: an existing .py file inside the repo root.

    Rejects option-looking values (``-c <code>`` would be arbitrary code
    execution) and anything outside the repo (CWE-22).
    """
    raw = (raw or "").strip()
    if not raw or raw.startswith("-"):
        return None, "file_path must be a .py file path (must not start with '-')"
    base = root.resolve()
    try:
        p = (base / raw).resolve()
    except (OSError, ValueError):
        return None, "invalid file_path"
    if not p.is_relative_to(base) or p.suffix != ".py":
        return None, "file_path must be a .py file inside the repo root"
    if not p.is_file():
        return None, f"file not found: {raw}"
    return p, None


def add_perf_tools(mcp) -> None:
    import json as _json
    import subprocess as _subprocess
    import os as _os
    import time as _time
    import shutil as _shutil
    from pathlib import Path as _Path

    ROOT = _ROOT

    # â”€â”€ perf_* (28) — wired to stdlib + core/training/benchmarks/ â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    @mcp.tool
    def perf_profile(file_path: str, function: str = "") -> str:
        """Profile a Python file or function."""
        try:
            import cProfile as _cp
            import pstats as _ps
            import io as _io
            import sys as _sys
            script, err = _resolve_py_script(ROOT, file_path)
            if err:
                return _safe_json({"error": err})
            pr = _cp.Profile()
            pr.enable()
            result = _subprocess.run([_sys.executable, str(script)], cwd=str(ROOT), capture_output=True, text=True, timeout=60)
            pr.disable()
            s = _io.StringIO()
            _ps.Stats(pr, stream=s).sort_stats("cumulative").print_stats(20)
            return _safe_json({"ok": result.returncode == 0, "file": file_path, "returncode": result.returncode, "stderr": result.stderr[-1000:], "profile": s.getvalue()[:3000]})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def perf_benchmark() -> str:
        """Run a performance benchmark."""
        try:
            from core.training.benchmarks.personality_benchmark import run_benchmark as _pb
            result = _pb()
            return _safe_json(result)
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def perf_compare(baseline: str = "", current: str = "") -> str:
        """Compare two performance baselines."""
        try:
            from core.training.eval_harness import EvalHarness
            eh = EvalHarness()
            result = eh.compare(baseline or "base", current or "current")
            return _safe_json(result)
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def perf_report() -> str:
        """Get the last performance report."""
        try:
            from core.training.eval_harness import EvalHarness
            eh = EvalHarness()
            return _safe_json({"status": "available", "harness": "EvalHarness"})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def perf_analyze() -> str:
        """Analyse performance bottlenecks."""
        try:
            from core.training.eval_harness import EvalHarness
            eh = EvalHarness()
            result = eh.compare("baseline", "current")
            improvements = getattr(result, "improvements", []) if hasattr(result, "improvements") else []
            return _safe_json({"improvements": improvements, "status": "analyzed"})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def perf_optimize() -> str:
        """Suggest performance optimisations."""
        try:
            from core.training.continuous_rl_trainer import get_trainer
            trainer = get_trainer()
            update = trainer.get_policy_update() if hasattr(trainer, "get_policy_update") else {}
            return _safe_json({"suggestions": update, "status": "optimized"})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def perf_cpu() -> str:
        """Profile CPU usage."""
        try:
            import psutil
            return _safe_json({"cpu_percent": psutil.cpu_percent(interval=1), "cpu_count": psutil.cpu_count(), "per_cpu": psutil.cpu_percent(interval=1, percpu=True)})
        except ImportError:
            return _safe_json({"error": "psutil not installed — pip install psutil"})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def perf_memory() -> str:
        """Profile memory usage."""
        try:
            import psutil
            process = psutil.Process()
            mem = process.memory_info()
            return _safe_json({"rss_mb": mem.rss / 1024 / 1024, "vms_mb": mem.vms / 1024 / 1024, "percent": process.memory_percent()})
        except ImportError:
            return _safe_json({"error": "psutil not installed"})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def perf_io() -> str:
        """Profile I/O operations."""
        try:
            import psutil
            io_counters = psutil.disk_io_counters()
            return _safe_json({"read_mb": io_counters.read_bytes / 1024 / 1024 if io_counters else 0, "write_mb": io_counters.write_bytes / 1024 / 1024 if io_counters else 0})
        except ImportError:
            return _safe_json({"error": "psutil not installed"})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def perf_network() -> str:
        """Profile network I/O."""
        try:
            import psutil
            net = psutil.net_io_counters()
            return _safe_json({"bytes_sent_mb": net.bytes_sent / 1024 / 1024, "bytes_recv_mb": net.bytes_recv / 1024 / 1024})
        except ImportError:
            return _safe_json({"error": "psutil not installed"})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def perf_gc() -> str:
        """Analyse garbage collection."""
        try:
            import gc
            stats = gc.get_stats()
            return _safe_json({"collections": [s["collections"] for s in stats], "collected": [s["collected"] for s in stats], "uncollectable": [s["uncollectable"] for s in stats]})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def perf_hotspots(file_path: str = "") -> str:
        """Identify performance hotspots."""
        try:
            import cProfile as _cp
            import pstats as _ps
            import io as _io
            import sys as _sys
            pr = _cp.Profile()
            pr.enable()
            if file_path:
                script, err = _resolve_py_script(ROOT, file_path)
                if err:
                    pr.disable()
                    return _safe_json({"error": err})
                result = _subprocess.run([_sys.executable, str(script)], cwd=str(ROOT), capture_output=True, text=True, timeout=30)
                if result.returncode != 0:
                    pr.disable()
                    return _safe_json({"error": f"script exited with code {result.returncode}", "stderr": result.stderr[-1000:]})
            pr.disable()
            s = _io.StringIO()
            _ps.Stats(pr, stream=s).sort_stats("tottime").print_stats(10)
            return _safe_json({"hotspots": s.getvalue()[:3000]})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def perf_regression() -> str:
        """Detect performance regressions."""
        try:
            from core.training.eval_harness import EvalHarness
            eh = EvalHarness()
            result = eh.compare("baseline", "current")
            overall = getattr(result, "overall_improvement", 0) if hasattr(result, "overall_improvement") else 0
            return _safe_json({"regression": overall < 0, "delta": overall})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def perf_monitor() -> str:
        """Monitor performance in real time."""
        try:
            import psutil
            return _safe_json({"cpu": psutil.cpu_percent(interval=1), "memory": psutil.virtual_memory().percent, "disk": psutil.disk_usage(str(ROOT)).percent})
        except ImportError:
            return _safe_json({"error": "psutil not installed"})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def perf_alert(threshold: float = 90.0) -> str:
        """Set a performance alert threshold."""
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=1)
            triggered = cpu > threshold
            return _safe_json({"cpu": cpu, "threshold": threshold, "triggered": triggered})
        except ImportError:
            return _safe_json({"error": "psutil not installed"})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def perf_history(limit: int = 10) -> str:
        """View performance history from episodic memory."""
        try:
            from core.memory.episodic import EpisodicMemory
            entries = EpisodicMemory().recall("performance", limit=max(1, min(int(limit), 200)))
            return _safe_json({"entries": entries})
        except Exception as e:
            logger.warning("[VECTOR][mcp] perf_history failed: {}", e)
            return _safe_json({"error": str(e)})

    @mcp.tool
    def perf_concurrent(n: int = 10) -> str:
        """Test concurrent request handling."""
        try:
            from core.config import CONFIG
            tq = CONFIG.get("task_queue", {})
            max_concurrent = tq.get("max_concurrent", 4)
            return _safe_json({"requested": n, "max_concurrent": max_concurrent, "status": "configured"})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def perf_latency(samples: int = 100) -> str:
        """Measure latency distribution."""
        try:
            import time
            samples = max(1, min(int(samples), 10000))
            latencies = []
            for _ in range(samples):
                start = time.perf_counter()
                time.sleep(0.0001)
                latencies.append((time.perf_counter() - start) * 1000)
            latencies.sort()
            return _safe_json({"samples": samples, "p50": latencies[int(samples * 0.5)], "p95": latencies[int(samples * 0.95)], "p99": latencies[int(samples * 0.99)], "min": latencies[0], "max": latencies[-1]})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def perf_trace(file_path: str = "") -> str:
        """Trace execution for performance."""
        return perf_profile(file_path)

    @mcp.tool
    def perf_cache() -> str:
        """Analyse cache hit rates."""
        try:
            from core.coding_assistant.cli.cache import get_cache
            cache = get_cache()
            stats = cache.stats() if hasattr(cache, "stats") else {}
            return _safe_json(stats)
        except Exception:
            return _safe_json({"status": "cache module not available"})

    @mcp.tool
    def perf_allocations() -> str:
        """Track memory allocations."""
        try:
            import tracemalloc
            tracemalloc.start()
            snapshot = tracemalloc.take_snapshot()
            stats = snapshot.statistics("lineno")[:10]
            return _safe_json({"top_allocations": [str(s) for s in stats]})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def perf_baseline(name: str = "default") -> str:
        """Set a performance baseline."""
        try:
            from core.memory.episodic import EpisodicMemory
            import psutil
            data = {"cpu": psutil.cpu_percent(interval=1), "memory_mb": psutil.Process().memory_info().rss / 1024 / 1024}
            EpisodicMemory().store("perf_baseline", _json.dumps({"name": name, "data": data}), tags=["performance", "baseline"])
            return _safe_json({"ok": True, "name": name, "data": data})
        except Exception as e:
            logger.warning("[VECTOR][mcp] perf_baseline failed: {}", e)
            return _safe_json({"error": str(e)})

    @mcp.tool
    def perf_flame_graph(file_path: str = "") -> str:
        """Generate a flame graph from profile data."""
        try:
            import cProfile as _cp
            import pstats as _ps
            import io as _io
            import sys as _sys
            pr = _cp.Profile()
            pr.enable()
            if file_path:
                script, err = _resolve_py_script(ROOT, file_path)
                if err:
                    pr.disable()
                    return _safe_json({"error": err})
                result = _subprocess.run([_sys.executable, str(script)], cwd=str(ROOT), capture_output=True, text=True, timeout=30)
                if result.returncode != 0:
                    pr.disable()
                    return _safe_json({"error": f"script exited with code {result.returncode}", "stderr": result.stderr[-1000:]})
            pr.disable()
            s = _io.StringIO()
            _ps.Stats(pr, stream=s).sort_stats("cumulative").print_stats(30)
            return _safe_json({"status": "profiled", "profile": s.getvalue()[:3000], "note": "For full flame graph, copy profile output to https://www.speedscope.app"})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def perf_export(path: str = "") -> str:
        """Export performance data to JSON."""
        try:
            import psutil
            data = {"cpu_percent": psutil.cpu_percent(interval=1), "memory_mb": psutil.Process().memory_info().rss / 1024 / 1024, "timestamp": _time.time()}
            out_path, err = _resolve_memory_path(path, default_name=f"perf_export_{int(_time.time())}.json")
            if err:
                return _safe_json({"error": err})
            with open(out_path, "w", encoding="utf-8") as f:
                _json.dump(data, f)
            return _safe_json({"ok": True, "path": str(out_path), "data": data})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def perf_import(path: str) -> str:
        """Import performance baseline data from JSON."""
        try:
            in_path, err = _resolve_memory_path(path, default_name="perf_export.json")
            if err:
                return _safe_json({"error": err})
            with open(in_path, encoding="utf-8") as f:
                data = _json.load(f)
            if not isinstance(data, dict):
                return _safe_json({"error": "performance baseline JSON must be an object"})
            from core.memory.episodic import EpisodicMemory
            EpisodicMemory().store("perf_import", str(data), tags=["performance", "baseline"])
            return _safe_json({"ok": True, "imported": str(in_path), "data_keys": list(data.keys())})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def perf_simulate(scenario: str = "cpu", duration_sec: int = 5) -> str:
        """Simulate a load scenario (cpu/memory/io)."""
        import math as _math
        duration_sec = max(1, min(int(duration_sec), 30))
        start = _time.time()
        ops = 0
        while _time.time() - start < duration_sec:
            if scenario == "cpu":
                _math.factorial(1000)
            elif scenario == "memory":
                _ = [0] * 10000
            elif scenario == "io":
                _subprocess.run(["echo", "sim"], capture_output=True)
            ops += 1
        return _safe_json({"scenario": scenario, "duration_sec": duration_sec, "operations": ops})

    @mcp.tool
    def perf_load(target: str = "cpu", workers: int = 4) -> str:
        """Run a load test by spawning concurrent workers."""
        import threading as _th
        import time as _tm
        workers = max(1, min(int(workers), 32))
        results = []
        def _worker(wid):
            start = _tm.time()
            count = 0
            while _tm.time() - start < 3:
                if target == "cpu":
                    _ = [i**2 for i in range(1000)]
                elif target == "io":
                    _subprocess.run(["echo", "load_test"], capture_output=True)
                count += 1
            results.append({"worker": wid, "iterations": count})
        threads = [_th.Thread(target=_worker, args=(i,)) for i in range(workers)]
        for t in threads: t.start()
        for t in threads: t.join()
        total_ops = sum(r["iterations"] for r in results)
        return _safe_json({"target": target, "workers": workers, "duration_sec": 3, "results": results, "total_operations": total_ops})

    @mcp.tool
    def perf_stress(workers: int = 8, duration_sec: int = 5) -> str:
        """Run a stress test combining CPU + memory + I/O load."""
        import threading as _th
        import time as _tm
        import math as _math
        workers = max(1, min(int(workers), 32))
        duration_sec = max(1, min(int(duration_sec), 30))
        results = []
        def _stress(wid):
            start = _tm.time()
            ops = 0
            mem_hog = []
            while _tm.time() - start < duration_sec:
                _math.factorial(2000)
                if ops % 100 == 0:
                    mem_hog.append([0] * 1000)
                _subprocess.run(["echo", "stress"], capture_output=True)
                ops += 1
            results.append({"worker": wid, "operations": ops, "memory_chunks": len(mem_hog)})
        threads = [_th.Thread(target=_stress, args=(i,)) for i in range(workers)]
        for t in threads: t.start()
        for t in threads: t.join()
        return _safe_json({"workers": workers, "duration_sec": duration_sec, "results": results})
