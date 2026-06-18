from __future__ import annotations

from pathlib import Path


from core.config import CONFIG
from core.mcp_tools.error_handling import safe_json as _safe_json
from core.mcp_tools.error_handling import register_stub_tool as _reg
from core.mcp_tools.memory_safety import (
    MEMORY_CLEAR_CONFIRM as _MEMORY_CLEAR_CONFIRM,
    resolve_memory_path as _resolve_memory_path,
)


def add_test_tools(mcp) -> None:
    import json as _json
    import subprocess as _subprocess
    import os as _os
    import time as _time
    import shutil as _shutil
    from pathlib import Path as _Path

    ROOT = _Path(__file__).resolve().parents[3]

    # â”€â”€ test_* (30) — wired to pytest subprocess + core/training/benchmarks/ â”€â”€â”€
    @mcp.tool
    def test_run(path: str = "") -> str:
        """Run the full test suite or a specific path."""
        try:
            cmd = ["pytest", path or "tests/", "-v", "--tb=short"]
            result = _subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=300)
            lines = result.stdout.strip().split("\n")
            return _safe_json({"passed": result.returncode == 0, "output": "\n".join(lines[-20:]), "full_output_length": len(result.stdout)})
        except FileNotFoundError:
            return _safe_json({"error": "pytest not installed"})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def test_filter(keyword: str) -> str:
        """Run tests matching a keyword filter."""
        try:
            result = _subprocess.run(["pytest", "-k", keyword, "-v", "--tb=short"], cwd=str(ROOT), capture_output=True, text=True, timeout=300)
            lines = result.stdout.strip().split("\n")
            return _safe_json({"keyword": keyword, "passed": result.returncode == 0, "output": "\n".join(lines[-20:])})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def test_parallel(n: int = 4) -> str:
        """Run tests in parallel with pytest-xdist."""
        try:
            result = _subprocess.run(["pytest", "-n", str(n), "-v", "--tb=short"], cwd=str(ROOT), capture_output=True, text=True, timeout=300)
            lines = result.stdout.strip().split("\n")
            return _safe_json({"workers": n, "passed": result.returncode == 0, "output": "\n".join(lines[-20:])})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def test_unit() -> str:
        """Run unit tests only."""
        return test_run("tests/unit/")

    @mcp.tool
    def test_integration() -> str:
        """Run integration tests only."""
        return test_run("tests/integration/")

    @mcp.tool
    def test_smoke() -> str:
        """Run smoke tests."""
        return test_run("tests/smoke/")

    @mcp.tool
    def test_regression() -> str:
        """Run regression test suite."""
        return test_run("tests/regression/")

    @mcp.tool
    def test_debug(path: str = "") -> str:
        """Run tests with verbose debug output."""
        try:
            cmd = ["pytest", path or "tests/", "-v", "-s", "--tb=long"]
            result = _subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=300)
            return _safe_json({"passed": result.returncode == 0, "output": result.stdout[-5000:], "stderr": result.stderr[-2000:]})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def test_discover() -> str:
        """Discover all test files in the repo."""
        try:
            result = _subprocess.run(["pytest", "--collect-only", "-q"], cwd=str(ROOT), capture_output=True, text=True, timeout=60)
            return _safe_json({"output": result.stdout[:5000]})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def test_fixtures() -> str:
        """List available pytest fixtures."""
        try:
            result = _subprocess.run(["pytest", "--fixtures", "-q"], cwd=str(ROOT), capture_output=True, text=True, timeout=60)
            return _safe_json({"output": result.stdout[:5000]})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def test_clean() -> str:
        """Remove test artefacts and caches."""
        try:
            for p in [ROOT / ".pytest_cache", ROOT / "__pycache__"]:
                if p.exists():
                    _shutil.rmtree(p, ignore_errors=True)
            return _safe_json({"ok": True, "message": "Test caches cleared"})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def test_profile(path: str = "") -> str:
        """Profile a test run with cProfile."""
        try:
            import cProfile as _cp
            import pstats as _ps
            import io as _io
            pr = _cp.Profile()
            pr.enable()
            result = _subprocess.run(["pytest", path or "tests/", "-q"], cwd=str(ROOT), capture_output=True, text=True, timeout=300)
            pr.disable()
            s = _io.StringIO()
            _ps.Stats(pr, stream=s).sort_stats("cumulative").print_stats(20)
            return _safe_json({"passed": result.returncode == 0, "profile": s.getvalue()[:3000]})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def test_benchmark() -> str:
        """Run performance benchmarks."""
        try:
            from core.training.benchmarks.personality_benchmark import run_benchmark as _pb
            result = _pb()
            return _safe_json(result)
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def test_compare(baseline: str = "", current: str = "") -> str:
        """Compare two test runs or model evaluations."""
        try:
            from core.training.eval_harness import EvalHarness
            eh = EvalHarness()
            result = eh.compare(baseline or "base", current or "current")
            return _safe_json(result)
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def test_perf() -> str:
        """Run performance regression tests."""
        return test_benchmark()

    @mcp.tool
    def test_report() -> str:
        """Get the last test run summary."""
        return _safe_json({"status": "requires_run", "message": "Run test_run first to generate a report"})

    @mcp.tool
    def test_status() -> str:
        """Show pass/fail status summary."""
        try:
            result = _subprocess.run(["pytest", "--tb=no", "-q"], cwd=str(ROOT), capture_output=True, text=True, timeout=120)
            return _safe_json({"summary": result.stdout.strip()[:500], "passed": result.returncode == 0})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def test_validate(path: str = "") -> str:
        """Validate test structure and configuration."""
        try:
            result = _subprocess.run(["pytest", "--co", "-q", path or "tests/"], cwd=str(ROOT), capture_output=True, text=True, timeout=60)
            return _safe_json({"valid": result.returncode == 0, "output": result.stdout[:2000]})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def test_e2e() -> str:
        """Run end-to-end tests."""
        return test_run("tests/e2e/")

    @mcp.tool
    def test_watch(path: str = ".", interval: int = 2) -> str:
        """Watch files and re-run tests on change (polls every N seconds, max 60s)."""
        import time as _time
        watched = _Path(path)
        mtimes = {p: p.stat().st_mtime for p in watched.rglob("*.py") if p.is_file()}
        start = _time.time()
        cycles = 0
        while _time.time() - start < 60:
            _time.sleep(interval)
            cycles += 1
            new_mtimes = {p: p.stat().st_mtime for p in watched.rglob("*.py") if p.is_file()}
            changed = [str(p) for p, m in new_mtimes.items() if m != mtimes.get(p)]
            if changed:
                result = _subprocess.run(["pytest", "-q", "--tb=short"], cwd=str(ROOT), capture_output=True, text=True, timeout=300)
                return _safe_json({"changed_files": changed, "test_output": result.stdout[-2000:], "passed": result.returncode == 0})
            mtimes = new_mtimes
        return _safe_json({"status": "timed_out", "cycles": cycles, "note": "Watched for 60s — no changes detected"})

    @mcp.tool
    def test_coverage(path: str = "tests/") -> str:
        """Generate test coverage report using pytest-cov."""
        try:
            result = _subprocess.run(["pytest", "--cov=core", "--cov-report=term", "--cov-report=html", "-q", path], cwd=str(ROOT), capture_output=True, text=True, timeout=300)
            html_report = str(ROOT / "htmlcov" / "index.html")
            return _safe_json({"passed": result.returncode == 0, "coverage_output": result.stdout[-3000:], "html_report": html_report if (ROOT / "htmlcov").exists() else None})
        except FileNotFoundError:
            return _safe_json({"error": "pytest-cov not installed — pip install pytest-cov"})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def test_create(name: str, target: str = "tests/") -> str:
        """Create a new test file from a template."""
        cls_name = "".join(w.capitalize() for w in name.replace(".", "_").replace("-", "_").split("_"))
        template = f'''"""
Tests for {name}
"""
import pytest


class Test{cls_name}:
    """Test suite for {name}."""

    def test_basic(self):
        assert True
'''
        test_path = _Path(target) / f"test_{name.lower().replace('.', '_').replace('-', '_')}.py"
        test_path.parent.mkdir(parents=True, exist_ok=True)
        test_path.write_text(template)
        return _safe_json({"ok": True, "path": str(test_path)})

    @mcp.tool
    def test_generate(module: str) -> str:
        """Generate tests for a module using vectorcode_llm."""
        try:
            from core.inference.vectorcode_llm import chat as _chat
            module_path = ROOT / module
            if not module_path.exists():
                return _safe_json({"error": f"Module not found: {module}"})
            source = module_path.read_text()
            result = _chat(f"Generate pytest test cases for this module:\n\n{source[:3000]}")
            return _safe_json({"module": module, "generated_tests": result[:5000]})
        except ImportError:
            return _safe_json({"status": "unavailable", "note": "Requires vectorcode_llm; run: pip install -e vectorcode"})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def test_fix(path: str = "") -> str:
        """Re-run failing tests and show diagnostics."""
        result = _subprocess.run(["pytest", path or "tests/", "-v", "--tb=long", "-x"], cwd=str(ROOT), capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            return _safe_json({"status": "all_passed", "output": result.stdout[-1000:]})
        failures = [line.strip() for line in result.stdout.split("\n") if "FAILED" in line]
        return _safe_json({"status": "failures_found", "count": len(failures), "failures": failures[:20], "output": result.stdout[-2000:], "stderr": result.stderr[-1000:]})

    @mcp.tool
    def test_snapshot(name: str = "", path: str = "") -> str:
        """Create/compare snapshot tests."""
        try:
            cmd = ["pytest", path or "tests/", "-v", "--tb=short"]
            result = _subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=300)
            return _safe_json({"snapshot": name or "default", "output": result.stdout[-2000:], "passed": result.returncode == 0, "note": "Install pytest-snapshot for snapshot update: pip install pytest-snapshot"})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def test_mock(module: str) -> str:
        """Analyse module and suggest mock targets."""
        try:
            import inspect as _inspect
            import importlib as _importlib
            mod_path = module.replace("/", ".").replace(".py", "")
            mod = _importlib.import_module(mod_path)
            classes = [n for n, o in _inspect.getmembers(mod, _inspect.isclass)]
            functions = [n for n, o in _inspect.getmembers(mod, _inspect.isfunction)]
            return _safe_json({"module": module, "classes": classes, "functions": functions[:30], "mock_targets": [f"{mod_path}.{c}" for c in classes[:5]]})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def test_assert() -> str:
        """List available assertion helpers."""
        return _safe_json({"helpers": ["assert x == y", "assert x != y", "assert x in y", "assert x is y", "assert x > y", "pytest.raises(Exc)", "pytest.warns(W)", "pytest.approx(x)", "pytest.fixture", "pytest.mark.parametrize"]})

    @mcp.tool
    def test_setup() -> str:
        """Configure test environment."""
        try:
            (ROOT / "tests" / "__init__.py").touch(exist_ok=True)
            (ROOT / "tests" / "conftest.py").touch(exist_ok=True)
            import tempfile as _tf
            tmp = _tf.mkdtemp(prefix="vector_test_")
            _os.environ["VECTOR_TEST_TMP"] = tmp
            return _safe_json({"ok": True, "tmp_dir": tmp})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def test_teardown() -> str:
        """Clean up test environment."""
        try:
            tmp = _os.environ.pop("VECTOR_TEST_TMP", "")
            if tmp:
                _shutil.rmtree(tmp, ignore_errors=True)
            return _safe_json({"ok": True, "cleaned": bool(tmp)})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def test_data(name: str = "default") -> str:
        """Load test data fixtures from tests/fixtures/."""
        fixtures_dir = ROOT / "tests" / "fixtures"
        fixtures_dir.mkdir(parents=True, exist_ok=True)
        if name == "default":
            available = sorted(f.name for f in fixtures_dir.iterdir() if f.is_file())
            return _safe_json({"fixtures_dir": str(fixtures_dir), "available": available or ["(none yet)"]})
        fixture_path = fixtures_dir / name
        if not fixture_path.exists():
            return _safe_json({"error": f"Fixture '{name}' not found in {fixtures_dir}"})
        return _safe_json({"fixture": name, "content": fixture_path.read_text()[:5000]})
