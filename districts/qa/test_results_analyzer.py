"""
Test Results Analyzer — transforms raw test output into actionable insights.

Parses smoke_test.py + integration_check.py output, tracks test trends,
identifies flaky tests, generates improvement recommendations.
"""

import sys
import asyncio
import datetime
import subprocess
import re
from pathlib import Path

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from core.inference.vectorcode_llm import chat

class TestResultsAnalyzer(AgentBase):
    """Analyzes test output and generates quality insights for VECTOR."""

    def __init__(self):
        super().__init__(agent_id="test_analyzer_001", name="TestResultsAnalyzer", district="qa")
        self.capabilities = [
            "test_results", "test_analyze", "smoke_test", "integration_test",
            "test_trend", "detect_regressions",
        ]
        self._memory: EpisodicMemory | None = None
        self._obsidian: ObsidianSync | None = None
        self._model = CONFIG.get("models", {}).get("focus", "vector-focus")
        self._root = Path(__file__).resolve().parent.parent.parent
        logger.info("[VECTOR][test_analyzer] initialized")

    def _get_memory(self):
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    def _get_obsidian(self):
        if self._obsidian is None:
            self._obsidian = ObsidianSync()
        return self._obsidian

    def run_and_capture(self, script: str) -> dict:
        """Run a test script and capture its output."""
        script_path = self._root / "scripts" / script
        if not script_path.exists():
            return {"error": f"{script} not found", "passed": 0, "failed": 0, "output": ""}
        try:
            result = subprocess.run(
                [sys.executable, "-X", "utf8", str(script_path)],
                capture_output=True, text=True, cwd=str(self._root), timeout=120,
            )
            output = result.stdout + result.stderr
            return {
                "output": output,
                "return_code": result.returncode,
                **self._parse_output(output),
            }
        except subprocess.TimeoutExpired:
            return {"error": "timeout", "passed": 0, "failed": 0, "output": ""}
        except Exception as e:
            return {"error": str(e), "passed": 0, "failed": 0, "output": ""}

    def _parse_output(self, output: str) -> dict:
        """Parse PASS/FAIL counts from test output."""
        pass_lines = [l for l in output.splitlines() if "PASS" in l and "FAIL" not in l]
        fail_lines = [l for l in output.splitlines() if "FAIL" in l]

        # Try to find summary line like "38/38 PASS"
        summary_m = re.search(r'(\d+)/(\d+)\s+PASS', output)
        if summary_m:
            passed = int(summary_m.group(1))
            total = int(summary_m.group(2))
            failed = total - passed
        else:
            passed = len(pass_lines)
            failed = len(fail_lines)

        failed_tests = [l.strip() for l in fail_lines if "FAIL" in l][:10]
        return {
            "passed": passed,
            "failed": failed,
            "total": passed + failed,
            "pass_rate": round(passed / max(1, passed + failed) * 100, 1),
            "failed_tests": failed_tests,
            "all_passed": failed == 0,
        }

    def get_historical_trend(self, limit: int = 10) -> list[dict]:
        """Fetch recent test run results from episodic memory."""
        try:
            mem = self._get_memory()
            events = mem.recall("test_results_analysis", limit=limit)
            return [e.get("context", {}) for e in events if e.get("context")]
        except Exception:
            return []

    def detect_regressions(self, current: dict, history: list[dict]) -> list[str]:
        """Compare current results to history and flag regressions."""
        regressions = []
        if not history:
            return regressions
        prev = history[-1] if history else {}
        prev_rate = prev.get("pass_rate", 100)
        curr_rate = current.get("pass_rate", 100)
        if curr_rate < prev_rate - 5:
            regressions.append(f"Pass rate dropped: {prev_rate}% → {curr_rate}% (-{prev_rate-curr_rate:.1f}%)")
        if current.get("failed", 0) > prev.get("failed", 0):
            regressions.append(f"New failures: {current['failed'] - prev.get('failed',0)} additional tests failing")
        return regressions

    async def generate_insights(self, smoke: dict, integration: dict, history: list) -> str:
        """LLM generates quality insights from test results."""
        prompt = (
            f"VECTOR AI test results analysis:\n\n"
            f"Smoke tests: {smoke.get('passed',0)}/{smoke.get('total',0)} passed ({smoke.get('pass_rate',0)}%)\n"
            f"Integration checks: {integration.get('passed',0)}/{integration.get('total',0)} passed ({integration.get('pass_rate',0)}%)\n"
            f"Failed tests: {smoke.get('failed_tests', []) + integration.get('failed_tests', [])}\n"
            f"Historical trend: {len(history)} previous runs\n\n"
            f"Provide:\n1. Quality verdict (EXCELLENT/GOOD/DEGRADED/CRITICAL)\n"
            f"2. Root cause analysis for any failures\n3. Top 2 recommended actions\n"
            f"Keep response under 200 words."
        )
        try:
            from core.prompt_library import get_library as _gl
            _sys = _gl().get_for_agent("test_results_analyzer") or ""
            _msgs = ([{"role": "system", "content": _sys}] if _sys else []) + [{"role": "user", "content": prompt}]
            return chat(model=self._model, messages=_msgs, timeout=20.0)
        except Exception as e:
            return f"Insight generation failed: {e}"

    async def run(self, task: dict) -> dict:
        try:
            # Run both test suites
            smoke = self.run_and_capture("smoke_test.py")
            integration = self.run_and_capture("integration_check.py")

            history = self.get_historical_trend(limit=5)
            combined_pass_rate = round(
                (smoke.get("passed", 0) + integration.get("passed", 0)) /
                max(1, smoke.get("total", 0) + integration.get("total", 0)) * 100, 1
            )
            regressions = self.detect_regressions(
                {"pass_rate": combined_pass_rate, "failed": smoke.get("failed", 0) + integration.get("failed", 0)},
                history,
            )
            insights = await self.generate_insights(smoke, integration, history)

            # Determine quality verdict
            total_failed = smoke.get("failed", 0) + integration.get("failed", 0)
            if total_failed == 0:
                verdict = "EXCELLENT"
            elif total_failed <= 2:
                verdict = "GOOD"
            elif total_failed <= 5:
                verdict = "DEGRADED"
            else:
                verdict = "CRITICAL"

            result = {
                "smoke": {"passed": smoke.get("passed"), "total": smoke.get("total"), "pass_rate": smoke.get("pass_rate")},
                "integration": {"passed": integration.get("passed"), "total": integration.get("total"), "pass_rate": integration.get("pass_rate")},
                "combined_pass_rate": combined_pass_rate,
                "verdict": verdict,
                "regressions": regressions,
                "failed_tests": smoke.get("failed_tests", []) + integration.get("failed_tests", []),
            }

            # Store in memory
            self._get_memory().store(
                event_type="test_results_analysis",
                content=f"Tests: {verdict} — smoke={smoke.get('passed')}/{smoke.get('total')} integration={integration.get('passed')}/{integration.get('total')}",
                tags=["qa", "testing", verdict.lower()],
                context=result,
                source="test_results_analyzer",
            )

            # Write Obsidian report
            try:
                ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                report = (
                    f"# Test Analysis — {ts}\n\n"
                    f"**Verdict: {verdict}** | Pass rate: {combined_pass_rate}%\n\n"
                    f"| Suite | Passed | Total | Rate |\n|---|---|---|---|\n"
                    f"| Smoke | {smoke.get('passed',0)} | {smoke.get('total',0)} | {smoke.get('pass_rate',0)}% |\n"
                    f"| Integration | {integration.get('passed',0)} | {integration.get('total',0)} | {integration.get('pass_rate',0)}% |\n\n"
                    f"## Insights\n{insights}\n"
                    + (f"\n## Regressions\n" + "\n".join(f"- {r}" for r in regressions) if regressions else "")
                )
                self._get_obsidian().write_note("Projects", "Test Analysis", report)
            except Exception as oe:
                logger.debug("[VECTOR][test_analyzer] obsidian write failed: {}", oe)

            if verdict in ("EXCELLENT", "GOOD"):
                self.award_points(50, "tests_passing")
            elif verdict == "DEGRADED":
                self.award_points(20, "tests_degraded")
            else:
                self.deduct_points(30, "tests_critical")

            result["insights"] = insights
            return {"status": "ok", **result}

        except Exception as e:
            logger.error("[VECTOR][test_analyzer] {}", e)
            self.deduct_points(30, "test_analysis_failed")
            return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = TestResultsAnalyzer()
        smoke = agent.run_and_capture("smoke_test.py")
        print(f"[OK] smoke: {smoke.get('passed')}/{smoke.get('total')} passed ({smoke.get('pass_rate')}%)")
        integration = agent.run_and_capture("integration_check.py")
        print(f"[OK] integration: {integration.get('passed')}/{integration.get('total')} passed")
        result = await agent.run({})
        print(f"[OK] run: verdict={result.get('verdict')} status={result['status']}")
        print("test_results_analyzer.py OK")

    asyncio.run(_smoke())
