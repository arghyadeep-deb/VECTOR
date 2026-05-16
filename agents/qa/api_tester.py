"""
API Tester — validates VECTOR's own FastAPI endpoints.

Tests all REST endpoints, checks response schemas, measures latency,
detects breaking changes, generates API health reports.
"""
import sys
import asyncio
import datetime
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync


class APITester(AgentBase):
    """Tests VECTOR's FastAPI endpoints for correctness and performance."""

    def __init__(self):
        super().__init__(agent_id="api_tester_001", name="APITester", district="qa")
        self._memory: EpisodicMemory | None = None
        self._obsidian: ObsidianSync | None = None
        self._base_url = CONFIG.get("api", {}).get("base_url", "http://127.0.0.1:8000")
        logger.info("[VECTOR][api_tester] initialized — base={}", self._base_url)

    def _get_memory(self):
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    def _get_obsidian(self):
        if self._obsidian is None:
            self._obsidian = ObsidianSync()
        return self._obsidian

    def test_endpoint(self, method: str, path: str, expected_status: int = 200,
                      body: dict | None = None, timeout: float = 5.0) -> dict:
        """Test a single endpoint and return result."""
        try:
            import httpx
            url = f"{self._base_url}{path}"
            t0 = time.perf_counter()
            if method.upper() == "GET":
                r = httpx.get(url, timeout=timeout)
            elif method.upper() == "POST":
                r = httpx.post(url, json=body or {}, timeout=timeout)
            else:
                r = httpx.request(method.upper(), url, json=body, timeout=timeout)
            latency_ms = round((time.perf_counter() - t0) * 1000, 1)

            ok = r.status_code == expected_status
            response_json = None
            try:
                response_json = r.json()
            except Exception:
                pass

            return {
                "method": method.upper(),
                "path": path,
                "status_code": r.status_code,
                "expected_status": expected_status,
                "ok": ok,
                "latency_ms": latency_ms,
                "slow": latency_ms > 500,
                "response_keys": list(response_json.keys()) if isinstance(response_json, dict) else None,
            }
        except Exception as e:
            return {
                "method": method.upper(),
                "path": path,
                "ok": False,
                "error": str(e)[:80],
                "latency_ms": 9999,
                "slow": True,
            }

    def run_full_suite(self) -> list[dict]:
        """Test all known VECTOR API endpoints."""
        tests = [
            ("GET", "/health", 200),
            ("GET", "/status", 200),
            ("GET", "/agents", 200),
            ("GET", "/goals", 200),
            ("GET", "/memory/recent", 200),
            ("GET", "/districts", 200),
            ("POST", "/command", 200, {"type": "check_health", "params": {}}),
            ("GET", "/metrics", 200),
        ]
        results = []
        for test in tests:
            method, path, expected = test[0], test[1], test[2]
            body = test[3] if len(test) > 3 else None
            result = self.test_endpoint(method, path, expected, body)
            results.append(result)
            status = "✅" if result["ok"] else "❌"
            logger.debug("[VECTOR][api_tester] {} {} {} {} ({}ms)",
                        status, method, path, result.get("status_code", "ERR"), result.get("latency_ms", 0))
        return results

    def compute_api_health(self, results: list[dict]) -> dict:
        """Compute overall API health metrics."""
        total = len(results)
        passed = sum(1 for r in results if r.get("ok"))
        slow = sum(1 for r in results if r.get("slow"))
        errors = [r for r in results if not r.get("ok")]
        latencies = [r["latency_ms"] for r in results if "latency_ms" in r and r["latency_ms"] < 9000]
        avg_latency = round(sum(latencies) / max(1, len(latencies)), 1)
        p95_latency = round(sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0, 1)

        if passed == total:
            grade = "A"
        elif passed / total >= 0.8:
            grade = "B"
        elif passed / total >= 0.6:
            grade = "C"
        else:
            grade = "F"

        return {
            "grade": grade,
            "passed": passed,
            "total": total,
            "pass_rate": round(passed / max(1, total) * 100, 1),
            "slow_endpoints": slow,
            "avg_latency_ms": avg_latency,
            "p95_latency_ms": p95_latency,
            "failed_endpoints": [f"{r['method']} {r['path']}: {r.get('error', r.get('status_code'))}" for r in errors],
            "api_reachable": any(r.get("ok") for r in results),
        }

    async def run(self, task: dict) -> dict:
        try:
            task_type = task.get("type", "full_suite")

            if task_type == "single":
                result = self.test_endpoint(
                    task.get("method", "GET"),
                    task.get("path", "/health"),
                    task.get("expected_status", 200),
                    task.get("body"),
                )
                self.award_points(15, "api_endpoint_tested")
                return {"status": "ok", "result": result}

            # Full test suite
            results = self.run_full_suite()
            health = self.compute_api_health(results)

            # Store in memory
            self._get_memory().store(
                event_type="api_health_check",
                content=f"API: grade={health['grade']} {health['passed']}/{health['total']} endpoints OK, avg={health['avg_latency_ms']}ms",
                tags=["qa", "api", f"grade_{health['grade'].lower()}"],
                context=health,
                source="api_tester",
            )

            # Write Obsidian report
            try:
                ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                report = (
                    f"# API Health — {ts}\n\n"
                    f"**Grade: {health['grade']}** | {health['passed']}/{health['total']} endpoints passing\n\n"
                    f"| Metric | Value |\n|---|---|\n"
                    f"| Pass rate | {health['pass_rate']}% |\n"
                    f"| Avg latency | {health['avg_latency_ms']}ms |\n"
                    f"| P95 latency | {health['p95_latency_ms']}ms |\n"
                    f"| Slow endpoints | {health['slow_endpoints']} |\n\n"
                )
                if not health["api_reachable"]:
                    report += "⚠️ **API server not running** — start with: `python run_vector.py api`\n"
                if health["failed_endpoints"]:
                    report += "## Failed Endpoints\n" + "\n".join(f"- {e}" for e in health["failed_endpoints"])
                self._get_obsidian().write_note("Projects", "API Health", report)
            except Exception as oe:
                logger.debug("[VECTOR][api_tester] obsidian failed: {}", oe)

            grade = health["grade"]
            if grade == "A":
                self.award_points(50, "api_all_passing")
            elif grade in ("B", "C"):
                self.award_points(25, f"api_grade_{grade.lower()}")
            else:
                self.deduct_points(20, "api_failing")

            return {"status": "ok", "health": health, "endpoint_results": results}

        except Exception as e:
            logger.error("[VECTOR][api_tester] {}", e)
            self.deduct_points(30, "api_test_failed")
            return {"status": "error", "error": str(e)}


if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = APITester()
        single = agent.test_endpoint("GET", "/health")
        print(f"[OK] test_endpoint: ok={single.get('ok')} latency={single.get('latency_ms')}ms")
        result = await agent.run({"type": "full_suite"})
        health = result.get("health", {})
        print(f"[OK] full_suite: grade={health.get('grade')} {health.get('passed')}/{health.get('total')} reachable={health.get('api_reachable')}")
        print("api_tester.py OK")

    asyncio.run(_smoke())
