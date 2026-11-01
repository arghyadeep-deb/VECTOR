"""
API Tester — validates VECTOR's own FastAPI endpoints.

Tests all REST endpoints, checks response schemas, measures latency,
detects breaking changes, generates API health reports.
"""

import asyncio
import datetime
import time

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from core.security.secrets_manager import get_secret

class APITester(AgentBase):
    """Tests VECTOR's FastAPI endpoints for correctness and performance."""

    def __init__(self):
        super().__init__(agent_id="api_tester_001", name="APITester", district="qa")
        self.capabilities = [
            "api_test", "api_health", "full_suite", "single",
        ]
        self._memory: EpisodicMemory | None = None
        self._obsidian: ObsidianSync | None = None
        self._base_url = CONFIG.get("api", {}).get("base_url", "http://127.0.0.1:8000")
        # Authenticate against our OWN API. Without this, every endpoint behind
        # the auth middleware returned 401 and the QA agent permanently
        # self-reported "grade=F, 2/8 endpoints OK" for a perfectly healthy API
        # (2026-07-17 browser dogfood spotted the false alarm in VECTOR's own
        # memory feed). Read through the centralized manager so OS-keyring
        # deployments authenticate too, not only process-environment setups.
        self._api_key = get_secret("VECTOR_API_KEY")
        logger.info("[VECTOR][api_tester] initialized — base={} auth={}",
                    self._base_url, "on" if self._api_key else "off")

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}

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
            headers = self._auth_headers()
            t0 = time.perf_counter()
            if method.upper() == "GET":
                r = httpx.get(url, headers=headers, timeout=timeout)
            elif method.upper() == "POST":
                r = httpx.post(url, json=body or {}, headers=headers, timeout=timeout)
            else:
                r = httpx.request(method.upper(), url, json=body, headers=headers, timeout=timeout)
            latency_ms = round((time.perf_counter() - t0) * 1000, 1)

            ok = r.status_code == expected_status
            response_json = None
            try:
                response_json = r.json()
            except Exception:
                logger.debug("[VECTOR] suppressed exception", exc_info=True)

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
        # Paths corrected 2026-07-17: /goals and /districts are not real routes
        # (both 404'd even WITH auth) — the real ones are /brain/goals and
        # /city/districts. And /command requires a `text` field (CommandRequest),
        # so the old {"type":...} body 422'd. All three defects made the suite
        # under-report health even after the auth fix.
        tests = [
            ("GET", "/health", 200),
            ("GET", "/status", 200),
            ("GET", "/agents", 200),
            ("GET", "/brain/goals", 200),
            ("GET", "/memory/recent", 200),
            ("GET", "/city/districts", 200),
            # /command runs the full LLM pipeline (free-tier cloud, 3-8s typical)
            # — the 5s default timed it out and dropped an otherwise-healthy API
            # a full grade. 5th tuple element = per-test timeout seconds.
            ("POST", "/command", 200, {"text": "status"}, 20.0),
            ("GET", "/metrics", 200),
        ]
        results = []
        for test in tests:
            method, path, expected = test[0], test[1], test[2]
            body = test[3] if len(test) > 3 else None
            timeout = test[4] if len(test) > 4 else 5.0
            result = self.test_endpoint(method, path, expected, body, timeout=timeout)
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
        # 2026-09-30 (Phase 3 codebase audit finding): the real governor
        # dispatch shape is {"type": ..., "params": {...}} -- every branch
        # below read its arguments straight off `task`, never
        # `task["params"]`, so a real dispatch always fell back to the
        # hardcoded defaults. Flattening params into task once (params
        # values win on overlap) keeps every existing flat-shape
        # caller/test working unchanged while fixing all branches at once.
        # 2026-09-30 (Codex third independent review, same cycle): capture
        # task_type from the UNMERGED task first -- if a nested params dict
        # happens to carry its own "type" key, merging params over task
        # before reading task_type would let params["type"] silently
        # hijack routing. See districts/communications/email_agent.py's
        # identical fix for the full evidence.
        task_type = task.get("type", "full_suite")
        task = {**task, **(task.get("params") or {})}
        try:

            if task_type == "single":
                result = self.test_endpoint(
                    task.get("method", "GET"),
                    task.get("path", "/health"),
                    task.get("expected_status", 200),
                    task.get("body"),
                )
                self.award_points(15, "api_endpoint_tested")
                return {"status": "ok", "result": result}

            # 2026-09-24 (external review, Phase 3 -- KNOWN_ISSUES #81 death
            # loop): task types with NO declared capability match here
            # (e.g. "review_content" -- a real content-QA event dispatched
            # by core/event_bus/wiring.py's CONTENT_READY trigger, routed
            # to the "qa" district generically, then QASwarm's keyword-score
            # fallback landed on APITester specifically since no qa agent
            # declares that capability) used to silently fall through to the
            # full API-health suite below regardless of what was actually
            # asked. If the API server wasn't reachable in that moment, the
            # resulting "grade F" scored a real -20 HP penalty on EVERY such
            # dispatch -- confirmed live at ~858 deaths/day (one every ~63s),
            # 100% of review_content dispatches ending in agent death,
            # successor "gen 1" never advancing (VECTOR_TECHNICAL_KNOWLEDGE/
            # 81_LIVE_LOOP_HEALTH_CHECK.md). Only run+score the real,
            # consequential health suite for its own declared capabilities;
            # anything else is not this agent's job and must not cost HP.
            if task_type not in ("full_suite", "api_test", "api_health"):
                logger.debug(
                    "[VECTOR][api_tester] task_type '{}' is not an API-testing "
                    "capability -- skipping without penalty (likely a "
                    "misrouted qa-district dispatch)", task_type,
                )
                return {"status": "not_applicable", "task_type": task_type}

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
