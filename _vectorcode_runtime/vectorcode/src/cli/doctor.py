"""Doctor — diagnostics for VectorCode installation."""
# --- Windows console UTF-8 safety (VECTOR codemod) ---
import sys as _vsys  # noqa: E402
for _vstream in (_vsys.stdout, _vsys.stderr):
    try:
        if _vstream is not None and hasattr(_vstream, "reconfigure") and (getattr(_vstream, "encoding", "") or "").lower() not in ("utf-8", "utf8"):
            _vstream.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
# ---------------------------------------------------------------------------

from pathlib import Path
import sys
import subprocess
import shutil
from dataclasses import dataclass
from typing import Callable


from loguru import logger

@dataclass
class CheckResult:
    name: str
    status: str    # "ok" | "warning" | "error" | "missing"
    message: str
    fix: str = ""  # Suggested fix command

# ── ANSI colours (stripped in non-TTY) ──────────────────────────────────────

def _supports_color() -> bool:
    return sys.stdout.isatty()

def _icon(status: str) -> str:
    if not _supports_color():
        return {"ok": "[OK]", "warning": "[WARN]", "error": "[ERROR]", "missing": "[MISS]"}.get(status, "[?]")
    return {
        "ok":      "\x1b[92m✅\x1b[0m",
        "warning": "\x1b[93m⚠️ \x1b[0m",
        "error":   "\x1b[91m❌\x1b[0m",
        "missing": "\x1b[91m❌\x1b[0m",
    }.get(status, "  ")

class Doctor:
    """Runs diagnostic checks and prints a health report for VectorCode."""

    # ── Aggregator ───────────────────────────────────────────────

    def run_all(self) -> list[CheckResult]:
        """Run all checks and return the results list."""
        checks: list[Callable[[], CheckResult]] = [
            self.check_python_version,
            self.check_ollama,
            self.check_ollama_models,
            self.check_vector_home,
            self.check_core_deps,
            self.check_optional_deps,
            self.check_vectormd,
            self.check_git,
            self.check_session_db,
        ]
        results: list[CheckResult] = []
        for fn in checks:
            try:
                result = fn()
            except Exception as e:
                result = CheckResult(
                    name=fn.__name__.replace("check_", "").replace("_", " "),
                    status="error",
                    message=f"Check raised an exception: {e}",
                )
            results.append(result)
            logger.debug(f"[VECTOR][doctor] {result.name}: {result.status} — {result.message}")
        return results

    # ── Individual checks ────────────────────────────────────────

    def check_python_version(self) -> CheckResult:
        """Python >= 3.11 required."""
        v = sys.version_info
        version_str = f"Python {v.major}.{v.minor}.{v.micro}"
        if v >= (3, 11):
            return CheckResult("Python version", "ok", f"{version_str} — OK")
        return CheckResult(
            "Python version",
            "error",
            f"{version_str} — Python 3.11+ required",
            fix="Download from https://www.python.org/downloads/",
        )

    def check_ollama(self) -> CheckResult:
        """Check if Ollama is running on localhost:11434."""
        try:
            import httpx
            with httpx.Client(timeout=3.0) as client:
                resp = client.get("http://localhost:11434/api/tags")
            if resp.status_code == 200:
                return CheckResult("Ollama", "ok", "Running on localhost:11434")
            return CheckResult(
                "Ollama",
                "warning",
                f"Responded with HTTP {resp.status_code}",
                fix="ollama serve",
            )
        except ImportError:
            return CheckResult("Ollama", "warning", "httpx not installed — cannot probe Ollama",
                               fix="pip install httpx")
        except Exception:
            return CheckResult(
                "Ollama",
                "error",
                "Not reachable on localhost:11434",
                fix="ollama serve",
            )

    def check_ollama_models(self) -> CheckResult:
        """Check if the vector-focus model is available in Ollama."""
        try:
            import httpx
            with httpx.Client(timeout=5.0) as client:
                resp = client.get("http://localhost:11434/api/tags")
            if resp.status_code != 200:
                return CheckResult("vector-focus model", "warning",
                                   "Ollama not responding — cannot check models")
            data = resp.json()
            models = [m.get("name", "") for m in data.get("models", [])]
            # Accept both "vector-focus" and "vector-focus:latest"
            has_focus = any("vector-focus" in m for m in models)
            if has_focus:
                return CheckResult("vector-focus model", "ok",
                                   "vector-focus found in Ollama")
            return CheckResult(
                "vector-focus model",
                "warning",
                "Model not found — run: ollama create vector-focus -f modelfiles/vector-focus.modelfile",
                fix="ollama pull gemma4:e4b",
            )
        except ImportError:
            return CheckResult("vector-focus model", "warning",
                               "httpx not installed — cannot check models",
                               fix="pip install httpx")
        except Exception as e:
            return CheckResult("vector-focus model", "warning",
                               f"Could not check Ollama models: {e}")

    def check_vector_home(self) -> CheckResult:
        """~/.vector/ directory exists and is writable."""
        vector_home = Path.home() / ".vector"
        if not vector_home.exists():
            try:
                vector_home.mkdir(parents=True, exist_ok=True)
                return CheckResult("~/.vector dir", "ok",
                                   f"Created {vector_home}")
            except Exception as e:
                return CheckResult("~/.vector dir", "error",
                                   f"Could not create {vector_home}: {e}",
                                   fix=f"mkdir {vector_home}")
        # Exists — check writable
        test_file = vector_home / ".vectorcode_write_test"
        try:
            test_file.write_text("ok", encoding="utf-8")
            test_file.unlink()
            return CheckResult("~/.vector dir", "ok",
                               f"{vector_home} exists and is writable")
        except Exception:
            return CheckResult("~/.vector dir", "error",
                               f"{vector_home} is not writable",
                               fix=f"chmod u+w {vector_home}")

    def check_core_deps(self) -> CheckResult:
        """Check critical pip packages: loguru, httpx, pydantic, fastapi."""
        required = ["loguru", "httpx", "pydantic", "fastapi"]
        missing: list[str] = []
        for pkg in required:
            try:
                __import__(pkg)
            except ImportError:
                missing.append(pkg)
        if not missing:
            return CheckResult("Core dependencies", "ok",
                               f"All required packages installed ({', '.join(required)})")
        return CheckResult(
            "Core dependencies",
            "error",
            f"Missing: {', '.join(missing)}",
            fix=f"pip install {' '.join(missing)}",
        )

    def check_optional_deps(self) -> CheckResult:
        """Check optional packages: discord, apscheduler, faiss-cpu, keyring, etc."""
        optional: dict[str, str] = {
            "discord":      "Discord integration (District 5)",
            "apscheduler":  "Scheduled tasks (2AM reflect, daily scrape)",
            "faiss":        "FAISS vector index (District 7)",
            "keyring":      "Secure credential storage",
            "chromadb":     "ChromaDB vector store",
            "lightrag":     "LightRAG upgraded RAG",
            "playwright":   "Browser automation (KIIT scraper)",
            "face_recognition": "Face ID (District 4)",
            "mediapipe":    "Fatigue monitor (EAR scoring)",
        }
        # Try import for each — use the import name (may differ from pip name)
        import_names: dict[str, str] = {
            "faiss":        "faiss",
            "discord":      "discord",
            "apscheduler":  "apscheduler",
            "keyring":      "keyring",
            "chromadb":     "chromadb",
            "lightrag":     "lightrag",
            "playwright":   "playwright",
            "face_recognition": "face_recognition",
            "mediapipe":    "mediapipe",
        }
        missing: list[str] = []
        for key in optional:
            import_name = import_names[key]
            try:
                __import__(import_name)
            except ImportError:
                missing.append(key)

        if not missing:
            return CheckResult("Optional dependencies", "ok",
                               f"All {len(optional)} optional packages installed")
        present = len(optional) - len(missing)
        return CheckResult(
            "Optional dependencies",
            "warning",
            f"{present}/{len(optional)} installed. Missing: {', '.join(missing)}",
            fix=f"pip install {' '.join(missing)}",
        )

    def check_vectormd(self) -> CheckResult:
        """Check if VECTOR.md exists in the current working directory."""
        vmd = Path.cwd() / "VECTOR.md"
        if vmd.exists():
            size = vmd.stat().st_size
            return CheckResult("VECTOR.md", "ok", f"Found in {Path.cwd()} ({size} bytes)")
        return CheckResult(
            "VECTOR.md",
            "warning",
            f"Not found in {Path.cwd()}",
            fix="vector init  (creates VECTOR.md for this project)",
        )

    def check_git(self) -> CheckResult:
        """Git available on PATH."""
        git_path = shutil.which("git")
        if not git_path:
            return CheckResult(
                "Git",
                "error",
                "git not found on PATH",
                fix="Install Git: https://git-scm.com/downloads",
            )
        try:
            result = subprocess.run(
                ["git", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            version_str = result.stdout.strip()
            return CheckResult("Git", "ok", f"{version_str} ({git_path})")
        except Exception as e:
            return CheckResult("Git", "warning", f"git found but could not get version: {e}")

    def check_session_db(self) -> CheckResult:
        """Session DB accessible and not corrupted."""
        try:
            # Import path used by the rest of the codebase
            from vectorcode.session_db import get_session_db
            db = get_session_db()
            rows = db.list_sessions(limit=1)
            return CheckResult("Session DB", "ok",
                               f"Accessible — {type(rows).__name__} returned")
        except ImportError:
            # Try alternate import path
            try:
                from session_db import get_session_db
                db = get_session_db()
                db.list_sessions(limit=1)
                return CheckResult("Session DB", "ok", "Accessible")
            except Exception as e2:
                return CheckResult(
                    "Session DB",
                    "warning",
                    f"session_db module not importable: {e2}",
                )
        except Exception as e:
            return CheckResult(
                "Session DB",
                "error",
                f"Session DB error: {e}",
                fix="vector sessions list  (auto-creates DB if missing)",
            )

    # ── Report ───────────────────────────────────────────────────

    def print_report(self, results: list[CheckResult]) -> None:
        """
        Print formatted report to stdout.
        ✅ Python version    Python 3.13.0 — OK
        ⚠️  vector-focus     Model not found — run: ollama pull gemma4:e4b
        ❌ faiss-cpu         Not installed — run: pip install faiss-cpu
        """
        ok_count      = sum(1 for r in results if r.status == "ok")
        warning_count = sum(1 for r in results if r.status == "warning")
        error_count   = sum(1 for r in results if r.status in ("error", "missing"))

        print()
        print("  VectorCode Doctor — System Health Report")
        print("  " + "─" * 60)
        for r in results:
            icon = _icon(r.status)
            label = f"{r.name:<26}"
            line = f"  {icon}  {label}  {r.message}"
            print(line)
            if r.fix and r.status != "ok":
                print(f"  {'':>4}  {'':>26}  → {r.fix}")
        print("  " + "─" * 60)

        # Summary
        parts: list[str] = []
        if ok_count:
            parts.append(f"{ok_count} OK")
        if warning_count:
            parts.append(f"{warning_count} warning(s)")
        if error_count:
            parts.append(f"{error_count} error(s)")
        summary = ", ".join(parts) if parts else "no checks ran"

        if error_count:
            verdict = "⚠️  Errors found — address them before running VECTOR"
        elif warning_count:
            verdict = "⚠️  Warnings found — optional but recommended"
        else:
            verdict = "✅  All checks passed — VECTOR is ready"

        print(f"  {verdict}")
        print(f"  Summary: {summary}")
        print()

def run_doctor() -> None:
    """Run all checks and print the report."""
    doctor = Doctor()
    results = doctor.run_all()
    doctor.print_report(results)

# ── Smoke test ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    doctor = Doctor()
    results = doctor.run_all()

    assert isinstance(results, list), "run_all must return a list"
    assert len(results) > 0, "run_all must return at least one result"
    for r in results:
        assert isinstance(r, CheckResult), f"Expected CheckResult, got {type(r)}"
        assert r.status in ("ok", "warning", "error", "missing"), f"Bad status: {r.status}"

    # print_report must not raise
    doctor.print_report(results)

    print("✅ cli/doctor.py OK")
