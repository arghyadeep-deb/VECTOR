import sys
import ast
import subprocess
import uuid
import asyncio
import datetime
from pathlib import Path

from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from core.loop.context_engine import ContextEngine
from loguru import logger

_BASE_DIR = Path(__file__).resolve().parent.parent.parent
_SCRIPTS_DIR = _BASE_DIR / "scripts"

# 10 critical VECTOR modules that must always import cleanly
_CRITICAL_MODULES = [
    "core.config",
    "core.memory.episodic",
    "core.city.agent_base",
    "core.loop.context_engine",
    "core.loop.decision_engine",
    "core.loop.permission_gateway",
    "core.brain.goal_system",
    "core.memory.reasoning_memory",
    "core.memory.policy",
    "core.city.agent_registry",
]


class RealityChecker(AgentBase):
    """
    Stops fantasy approvals — requires evidence before marking anything done.
    Runs smoke tests, integration checks, import verifications, and syntax audits.
    Only awards HP if ALL checks pass.
    """

    def __init__(self, generation: int = 1, ghost: dict | None = None):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="RealityChecker",
            district="qa",
            generation=generation,
        )
        self.capabilities = ["qa", "reality_check", "verify"]
        if ghost:
            self.inherit_ghost(ghost)
        self._memory = EpisodicMemory()
        self._obsidian = ObsidianSync()
        self._context = ContextEngine()
        logger.info(f"[VECTOR][reality_checker] ready gen={generation}")

    # ── Check methods ──────────────────────────────────────────────────────────

    def check_smoke_tests(self) -> dict:
        """
        Run `python -X utf8 scripts/smoke_test.py` via subprocess.
        Returns {passed: int, failed: int, output: str, ok: bool}.
        """
        script = _SCRIPTS_DIR / "smoke_test.py"
        if not script.exists():
            logger.warning(f"[VECTOR][reality_checker] smoke_test.py not found at {script}")
            return {"passed": 0, "failed": 0, "output": "smoke_test.py not found", "ok": False, "skipped": True}

        try:
            result = subprocess.run(
                [sys.executable, "-X", "utf8", str(script)],
                capture_output=True, text=True, timeout=120,
                cwd=str(_BASE_DIR),
            )
            stdout = result.stdout + result.stderr
            passed = stdout.count("PASS") + stdout.count("✅") + stdout.count("ok")
            failed = stdout.count("FAIL") + stdout.count("❌") + stdout.count("ERROR")
            ok = result.returncode == 0 and failed == 0
            logger.info(f"[VECTOR][reality_checker] smoke tests: passed={passed} failed={failed} rc={result.returncode}")
            return {"passed": passed, "failed": failed, "output": stdout[:2000], "ok": ok}
        except subprocess.TimeoutExpired:
            logger.warning("[VECTOR][reality_checker] smoke_test.py timed out")
            return {"passed": 0, "failed": 1, "output": "timeout", "ok": False}
        except Exception as e:
            logger.error(f"[VECTOR][reality_checker] smoke test error: {e}")
            return {"passed": 0, "failed": 1, "output": str(e), "ok": False}

    def check_integration(self) -> dict:
        """
        Run `scripts/integration_check.py` via subprocess.
        Returns {passed: int, failed: int, output: str, ok: bool}.
        """
        script = _SCRIPTS_DIR / "integration_check.py"
        if not script.exists():
            logger.warning(f"[VECTOR][reality_checker] integration_check.py not found at {script}")
            return {"passed": 0, "failed": 0, "output": "integration_check.py not found", "ok": False, "skipped": True}

        try:
            result = subprocess.run(
                [sys.executable, "-X", "utf8", str(script)],
                capture_output=True, text=True, timeout=180,
                cwd=str(_BASE_DIR),
            )
            stdout = result.stdout + result.stderr
            passed = stdout.count("PASS") + stdout.count("✅") + stdout.count("ok")
            failed = stdout.count("FAIL") + stdout.count("❌") + stdout.count("ERROR")
            ok = result.returncode == 0 and failed == 0
            logger.info(f"[VECTOR][reality_checker] integration: passed={passed} failed={failed} rc={result.returncode}")
            return {"passed": passed, "failed": failed, "output": stdout[:2000], "ok": ok}
        except subprocess.TimeoutExpired:
            logger.warning("[VECTOR][reality_checker] integration_check.py timed out")
            return {"passed": 0, "failed": 1, "output": "timeout", "ok": False}
        except Exception as e:
            logger.error(f"[VECTOR][reality_checker] integration error: {e}")
            return {"passed": 0, "failed": 1, "output": str(e), "ok": False}

    def verify_imports(self) -> dict:
        """
        Try-import each of the 10 critical VECTOR modules in a subprocess.
        Returns {ok: bool, failures: list[str], successes: list[str]}.
        """
        failures: list[str] = []
        successes: list[str] = []

        for mod in _CRITICAL_MODULES:
            try:
                result = subprocess.run(
                    [sys.executable, "-c", f"import sys; sys.path.insert(0, r'{_BASE_DIR}'); import {mod}; print('OK')"],
                    capture_output=True, text=True, timeout=15,
                    cwd=str(_BASE_DIR),
                )
                if result.returncode == 0 and "OK" in result.stdout:
                    successes.append(mod)
                else:
                    err = (result.stderr or result.stdout)[:200]
                    logger.warning(f"[VECTOR][reality_checker] import failed: {mod} — {err}")
                    failures.append(f"{mod}: {err}")
            except Exception as e:
                failures.append(f"{mod}: {e}")

        ok = len(failures) == 0
        logger.info(f"[VECTOR][reality_checker] imports: {len(successes)}/{len(_CRITICAL_MODULES)} ok")
        return {"ok": ok, "successes": successes, "failures": failures}

    def check_syntax_clean(self) -> dict:
        """
        Run ast.parse on all core/*.py files and report syntax errors.
        Returns {ok: bool, errors: list[dict], clean_files: int}.
        """
        core_dir = _BASE_DIR / "core"
        if not core_dir.exists():
            return {"ok": False, "errors": [{"file": "core/", "error": "directory not found"}], "clean_files": 0}

        errors: list[dict] = []
        clean = 0
        py_files = list(core_dir.rglob("*.py"))

        for py in py_files:
            if "__pycache__" in py.parts:
                continue
            try:
                source = py.read_text(encoding="utf-8", errors="replace")
                ast.parse(source)
                clean += 1
            except SyntaxError as e:
                rel = str(py.relative_to(_BASE_DIR))
                errors.append({"file": rel, "line": e.lineno, "error": str(e.msg)})
                logger.warning(f"[VECTOR][reality_checker] syntax error: {rel}:{e.lineno} — {e.msg}")

        ok = len(errors) == 0
        logger.info(f"[VECTOR][reality_checker] syntax: {clean} clean, {len(errors)} errors")
        return {"ok": ok, "errors": errors, "clean_files": clean}

    def generate_reality_report(self) -> dict:
        """
        Run all four checks and combine into a structured report dict.
        """
        smoke = self.check_smoke_tests()
        integration = self.check_integration()
        imports = self.verify_imports()
        syntax = self.check_syntax_clean()

        all_ok = (
            smoke.get("ok", False)
            and integration.get("ok", False)
            and imports.get("ok", False)
            and syntax.get("ok", False)
        )

        report = {
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "all_clear": all_ok,
            "smoke_tests": {
                "passed": smoke.get("passed", 0),
                "failed": smoke.get("failed", 0),
                "ok": smoke.get("ok", False),
                "skipped": smoke.get("skipped", False),
            },
            "integration": {
                "passed": integration.get("passed", 0),
                "failed": integration.get("failed", 0),
                "ok": integration.get("ok", False),
                "skipped": integration.get("skipped", False),
            },
            "import_errors": imports.get("failures", []),
            "imports_ok": imports.get("ok", False),
            "syntax_errors": syntax.get("errors", []),
            "syntax_ok": syntax.get("ok", False),
            "clean_files": syntax.get("clean_files", 0),
        }
        return report

    # ── run ───────────────────────────────────────────────────────────────────

    async def run(self, task: dict) -> dict:
        """
        Run full reality check, write Obsidian note, return report.
        """
        logger.info("[VECTOR][reality_checker] running full reality check")
        report = self.generate_reality_report()

        # Build Obsidian note
        date_str = datetime.date.today().isoformat()
        status_emoji = "PASS" if report["all_clear"] else "FAIL"
        note_lines = [
            f"# QA Reality Check — {date_str} [{status_emoji}]\n",
            f"**All clear:** {report['all_clear']}\n",
            f"**Generated:** {report['generated_at']}\n\n",
            "## Smoke Tests\n",
            f"- Passed: {report['smoke_tests']['passed']}\n",
            f"- Failed: {report['smoke_tests']['failed']}\n",
            f"- Skipped: {report['smoke_tests']['skipped']}\n\n",
            "## Integration\n",
            f"- Passed: {report['integration']['passed']}\n",
            f"- Failed: {report['integration']['failed']}\n",
            f"- Skipped: {report['integration']['skipped']}\n\n",
            "## Import Health\n",
        ]
        if report["import_errors"]:
            note_lines.append("**FAILURES:**\n")
            for err in report["import_errors"]:
                note_lines.append(f"- {err}\n")
        else:
            note_lines.append("All critical imports: OK\n")

        note_lines.append("\n## Syntax Check\n")
        note_lines.append(f"- Clean files: {report['clean_files']}\n")
        if report["syntax_errors"]:
            note_lines.append("**SYNTAX ERRORS:**\n")
            for se in report["syntax_errors"]:
                # Not every entry here has a "line" -- check_syntax_clean() also reports
                # structural failures (e.g. "directory not found") with no line number.
                loc = f" line {se['line']}" if "line" in se else ""
                note_lines.append(f"- `{se['file']}`{loc}: {se['error']}\n")
        else:
            note_lines.append("- No syntax errors found\n")

        note_content = "".join(note_lines)

        try:
            self._obsidian.write_note(
                title=f"QA Reality Check — {date_str}",
                content=note_content,
                folder="Research",
                tags=["qa", "reality-check", "vector", status_emoji.lower()],
            )
        except Exception as e:
            logger.warning(f"[VECTOR][reality_checker] obsidian write failed: {e}")

        # Store in episodic memory
        self._memory.store(
            event_type="qa_reality_check",
            content=f"Reality check {'PASSED' if report['all_clear'] else 'FAILED'} — {date_str}",
            tags=["qa", "reality_check"],
            context=report,
            source="reality_checker",
        )
        self._memory.store_chain(
            situation="qa_reality_check",
            goal_ids=["quality_assurance"],
            steps=["smoke_tests", "integration", "verify_imports", "syntax_check"],
            action="generate_reality_report",
            outcome="pass" if report["all_clear"] else "fail",
            reward=0.9 if report["all_clear"] else 0.2,
        )

        # HP: only award if ALL checks pass; deduct if any fail
        if report["all_clear"]:
            self.award_points(50, "all QA checks passed")
        else:
            self.deduct_points(30, "QA checks failed")

        return {"status": "ok", "report": report}

    async def run_forever(self) -> None:
        logger.info("[VECTOR][reality_checker] run_forever — event-driven")
        while self.is_alive:
            try:
                await asyncio.sleep(60)
            except Exception as e:
                logger.error(f"[VECTOR][reality_checker] tick: {e}")
        logger.warning("[VECTOR][reality_checker] died — HP=0")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    agent = RealityChecker()
    assert agent.health_points == 500, f"expected 500 HP, got {agent.health_points}"

    # Smoke test: syntax check on core/ (always safe)
    syntax = agent.check_syntax_clean()
    assert isinstance(syntax, dict)
    assert "ok" in syntax and "clean_files" in syntax
    print(f"  syntax check: {syntax['clean_files']} clean files, {len(syntax['errors'])} errors")

    # Smoke test: import check (runs subprocess per module)
    imports = agent.verify_imports()
    assert isinstance(imports, dict) and "ok" in imports
    total = len(_CRITICAL_MODULES)
    ok_count = len(imports["successes"])
    print(f"  imports: {ok_count}/{total} clean")

    # Smoke test: report structure
    report = agent.generate_reality_report()
    assert "all_clear" in report and "smoke_tests" in report

    print(f"✅ reality_checker.py OK HP={agent.health_points}")
