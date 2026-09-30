"""
SRE Monitor — District: ops
Tracks VECTOR's own system health, computes SLO, runs chaos probes,
and writes Obsidian SLO reports. RULE 11: no Claude API at runtime.
"""

import sys
import asyncio
import datetime
import time
import uuid

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync

_FOCUS = CONFIG.get("models", {}).get("focus", "vector-focus")

# Cloudflare Worker (cloud brain) health endpoint — configurable via CONFIG or env
_CF_HEALTH_URL: str = CONFIG.get("cf_worker_url", "https://vector-api.arghyadeepdeb020703.workers.dev/health")
# Ollama availability check
_OLLAMA_HOST: str = CONFIG.get("ollama_host", "http://127.0.0.1:11434")
# SLO target
_SLO_TARGET: float = 0.995  # 99.5%

class SREMonitor(AgentBase):
    """
    Site Reliability agent. Monitors VECTOR's own infrastructure:
      - Cloudflare Worker (cloud brain) /health ping
      - SQLite write-latency check
      - Ollama availability check
      - Autonomous-loop error rate → SLO calculation
      - Chaos probe via decision_engine
    Reports to Obsidian and episodic_memory.
    """

    def __init__(self, generation: int = 1, ghost: dict | None = None):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="SREMonitor",
            district="ops",
            generation=generation,
        )
        self.capabilities = ["chaos", "health", "high_cpu", "monitor", "ops", "slo", "sre"]
        if ghost:
            self.inherit_ghost(ghost)
        self._memory: EpisodicMemory | None = None
        self._obsidian: ObsidianSync | None = None
        logger.info(f"[VECTOR][sre_monitor] ready gen={generation}")

    # ── Lazy accessors ─────────────────────────────────────────────────────────

    def _get_memory(self) -> EpisodicMemory:
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    def _get_obsidian(self) -> ObsidianSync:
        if self._obsidian is None:
            self._obsidian = ObsidianSync()
        return self._obsidian

    @staticmethod
    def _emit_system_signal(results: dict) -> None:
        try:
            from districts.emergency.main import _emit
            import asyncio
            for signal_name in ("high_cpu", "high_ram", "disk_full"):
                val = results.get(signal_name.replace("_", ""), None)
                if val is not None and val > 90:
                    asyncio.create_task(_emit("system", signal_name, val, "sre_monitor"))
            if not results.get("ollama_ok", True):
                asyncio.create_task(_emit("system", "process_crash", True, "sre_monitor"))
        except Exception:
            logger.exception("[VECTOR] silent swallow")
            pass

    # ── Core checks ────────────────────────────────────────────────────────────

    async def check_system_health(self) -> dict:
        """
        Ping the Cloudflare Worker /health, check SQLite write latency, check
        Ollama availability, count errors in last 100 episodic events.
        Returns dict with keys: cf_ok, sqlite_latency_ms, ollama_ok, error_rate.
        """
        results: dict = {}

        # 1. Cloudflare Worker (cloud brain) ping
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                t0 = time.monotonic()
                resp = await client.get(_CF_HEALTH_URL)
                latency_ms = (time.monotonic() - t0) * 1000
                results["cf_ok"] = resp.status_code == 200
                results["cf_latency_ms"] = round(latency_ms, 1)
                results["cf_status_code"] = resp.status_code
        except Exception as e:
            logger.warning(f"[VECTOR][sre_monitor] Cloudflare ping failed: {e}")
            results["cf_ok"] = False
            results["cf_latency_ms"] = -1
            results["cf_status_code"] = -1

        # 2. SQLite write latency
        try:
            mem = self._get_memory()
            t0 = time.monotonic()
            mem.store(
                event_type="sre_latency_probe",
                content="SRE write-latency probe",
                tags=["sre_monitoring", "probe"],
                source="sre_monitor",
            )
            latency_ms = (time.monotonic() - t0) * 1000
            results["sqlite_latency_ms"] = round(latency_ms, 1)
            results["sqlite_ok"] = latency_ms < 500
        except Exception as e:
            logger.warning(f"[VECTOR][sre_monitor] SQLite probe failed: {e}")
            results["sqlite_latency_ms"] = -1
            results["sqlite_ok"] = False

        # 3. Ollama availability
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{_OLLAMA_HOST}/api/tags")
                results["ollama_ok"] = resp.status_code == 200
        except Exception as e:
            logger.warning(f"[VECTOR][sre_monitor] Ollama check failed: {e}")
            results["ollama_ok"] = False

        # 4. Error rate in last 100 episodic events
        try:
            mem = self._get_memory()
            cur = mem.conn.cursor()
            cur.execute(
                "SELECT event_type FROM episodic_memory ORDER BY timestamp DESC LIMIT 100"
            )
            rows = cur.fetchall()
            total = len(rows)
            errors = sum(
                1 for r in rows
                if r[0] and "error" in r[0].lower()
            )
            results["last_100_events"] = total
            results["last_100_errors"] = errors
            results["error_rate"] = round(errors / total, 4) if total > 0 else 0.0
        except Exception as e:
            logger.warning(f"[VECTOR][sre_monitor] error rate query failed: {e}")
            results["last_100_events"] = 0
            results["last_100_errors"] = 0
            results["error_rate"] = 1.0  # fail-closed: unknown state → assume worst case

        is_healthy = (
            results.get("sqlite_ok", False)
            and results.get("ollama_ok", False)
            and results.get("error_rate", 1.0) < 0.05
        )
        results["overall_healthy"] = is_healthy

        if not is_healthy:
            self._emit_system_signal(results)

        logger.info(f"[VECTOR][sre_monitor] health check: {results}")
        return results

    def compute_slo(self) -> dict:
        """
        Calculate % of autonomous loop ticks that completed without error.
        Uses episodic_memory events tagged 'loop_tick'. Target: 99.5%.
        Returns: {slo_pct, total_ticks, error_ticks, meets_target}.
        """
        try:
            mem = self._get_memory()
            cur = mem.conn.cursor()
            # Total loop ticks in last 24h
            cutoff = (
                datetime.datetime.now(datetime.timezone.utc)
                - datetime.timedelta(hours=24)
            ).isoformat()
            cur.execute(
                "SELECT COUNT(*) FROM episodic_memory WHERE timestamp > ? AND event_type LIKE '%loop%'",
                (cutoff,),
            )
            total_ticks = cur.fetchone()[0] or 0

            cur.execute(
                "SELECT COUNT(*) FROM episodic_memory WHERE timestamp > ? AND event_type LIKE '%loop%' AND content LIKE '%error%'",
                (cutoff,),
            )
            error_ticks = cur.fetchone()[0] or 0

            if total_ticks == 0:
                slo_pct = 1.0  # no data → assume healthy
            else:
                slo_pct = round((total_ticks - error_ticks) / total_ticks, 5)

            result = {
                "slo_pct": slo_pct,
                "slo_pct_display": f"{slo_pct * 100:.3f}%",
                "total_ticks_24h": total_ticks,
                "error_ticks_24h": error_ticks,
                "target_pct": _SLO_TARGET,
                "meets_target": slo_pct >= _SLO_TARGET,
            }
            logger.info(f"[VECTOR][sre_monitor] SLO={slo_pct * 100:.3f}% (target={_SLO_TARGET * 100}%)")
            return result
        except Exception as e:
            logger.error(f"[VECTOR][sre_monitor] compute_slo failed: {e}")
            return {
                "slo_pct": 0.0,
                "slo_pct_display": "0.000%",
                "total_ticks_24h": 0,
                "error_ticks_24h": 0,
                "target_pct": _SLO_TARGET,
                "meets_target": False,
                "error": str(e),
            }

    async def run_chaos_probe(self) -> dict:
        """
        Submit a sample task through decision_engine and measure end-to-end latency.
        Returns: {latency_ms, decision_made, error}.
        """
        try:
            from core.loop.decision_engine import DecisionEngine, Candidate
            engine = DecisionEngine()
            candidate = Candidate(
                action_type="check_weather",
                params={"location": "Bhubaneswar"},
                confidence=0.8,
                urgency=0.2,
                source="sre_chaos_probe",
            )
            t0 = time.monotonic()
            decision = await engine.evaluate([candidate])
            latency_ms = round((time.monotonic() - t0) * 1000, 2)
            result = {
                "latency_ms": latency_ms,
                "decision_made": decision is not None,
                "winner": decision.winner.action_type if decision else None,
                "error": None,
            }
            logger.info(f"[VECTOR][sre_monitor] chaos probe: {latency_ms}ms decision={decision is not None}")
            return result
        except Exception as e:
            logger.warning(f"[VECTOR][sre_monitor] chaos probe failed: {e}")
            return {"latency_ms": -1, "decision_made": False, "winner": None, "error": str(e)}

    def generate_slo_report(
        self,
        health: dict,
        slo: dict,
        chaos: dict,
    ) -> bool:
        """
        Write an Obsidian SLO report. Returns True on success.
        """
        date_str = datetime.date.today().isoformat()
        title = f"SLO Report — {date_str}"

        cf_icon = "✅" if health.get("cf_ok") else "❌"
        sqlite_icon = "✅" if health.get("sqlite_ok") else "❌"
        ollama_icon = "✅" if health.get("ollama_ok") else "❌"
        slo_icon = "✅" if slo.get("meets_target") else "⚠️"

        content = (
            f"# SLO Report — {date_str}\n\n"
            f"## System Health\n"
            f"| Component | Status | Latency |\n"
            f"|-----------|--------|--------|\n"
            f"| Cloudflare | {cf_icon} {health.get('cf_status_code', '?')} | {health.get('cf_latency_ms', '?')}ms |\n"
            f"| SQLite | {sqlite_icon} | {health.get('sqlite_latency_ms', '?')}ms |\n"
            f"| Ollama | {ollama_icon} | — |\n\n"
            f"## Error Rate (last 100 events)\n"
            f"- Total: {health.get('last_100_events', 0)}\n"
            f"- Errors: {health.get('last_100_errors', 0)}\n"
            f"- Rate: {health.get('error_rate', 0.0) * 100:.1f}%\n\n"
            f"## SLO (24h Autonomous Loop)\n"
            f"| Metric | Value |\n"
            f"|--------|-------|\n"
            f"| SLO | {slo_icon} {slo.get('slo_pct_display', '?')} |\n"
            f"| Target | {slo.get('target_pct', 0.995) * 100:.1f}% |\n"
            f"| Total ticks | {slo.get('total_ticks_24h', 0)} |\n"
            f"| Error ticks | {slo.get('error_ticks_24h', 0)} |\n\n"
            f"## Chaos Probe\n"
            f"- Latency: {chaos.get('latency_ms', -1)}ms\n"
            f"- Decision made: {chaos.get('decision_made', False)}\n"
            f"- Winner: `{chaos.get('winner', 'none')}`\n"
        )
        if chaos.get("error"):
            content += f"- Probe error: `{chaos['error']}`\n"

        content += f"\n---\n*auto-generated by SREMonitor · {datetime.datetime.now().isoformat()[:16]}*"

        try:
            self._get_obsidian().write_note(
                title=title,
                content=content,
                folder="Research",
                tags=["sre", "ops", "slo", "vector"],
            )
            logger.info(f"[VECTOR][sre_monitor] SLO report written: {title}")
            return True
        except Exception as e:
            logger.error(f"[VECTOR][sre_monitor] Obsidian write failed: {e}")
            return False

    # ── AgentBase.run entry-point ──────────────────────────────────────────────

    async def run(self, task: dict) -> dict:
        task_type = task.get("type", "full_check")
        try:
            if task_type == "health":
                result = await self.check_system_health()
                degraded = not result.get("overall_healthy", True)
                if degraded:
                    self.deduct_points(30, "system degradation detected")
                else:
                    self.award_points(20, "system healthy")
                self._get_memory().store(
                    event_type="sre_monitoring",
                    content=f"health check: healthy={result.get('overall_healthy')}",
                    tags=["sre_monitoring"],
                    source="sre_monitor",
                )
                return {"status": "ok", **result}

            elif task_type == "slo":
                result = self.compute_slo()
                if result.get("meets_target"):
                    self.award_points(30, "SLO target met")
                else:
                    self.deduct_points(20, f"SLO miss: {result.get('slo_pct_display')}")
                self._get_memory().store(
                    event_type="sre_monitoring",
                    content=f"SLO={result.get('slo_pct_display')} meets={result.get('meets_target')}",
                    tags=["sre_monitoring", "slo"],
                    source="sre_monitor",
                )
                return {"status": "ok", **result}

            elif task_type == "chaos":
                result = await self.run_chaos_probe()
                latency = result.get("latency_ms", -1)
                if latency > 0 and result.get("decision_made"):
                    self.award_points(10, f"chaos probe ok {latency}ms")
                else:
                    self.deduct_points(15, "chaos probe failed")
                self._get_memory().store(
                    event_type="sre_monitoring",
                    content=f"chaos probe latency={latency}ms ok={result.get('decision_made')}",
                    tags=["sre_monitoring", "chaos"],
                    source="sre_monitor",
                )
                return {"status": "ok", **result}

            else:
                # Full check: health + SLO + chaos + report
                health = await self.check_system_health()
                slo = self.compute_slo()
                chaos = await self.run_chaos_probe()
                report_ok = self.generate_slo_report(health, slo, chaos)

                overall_healthy = (
                    health.get("overall_healthy", False)
                    and slo.get("meets_target", False)
                )
                if overall_healthy:
                    self.award_points(50, "full SRE pass — all systems nominal")
                else:
                    self.deduct_points(30, "degradation detected in full SRE check")

                self._get_memory().store(
                    event_type="sre_monitoring",
                    content=(
                        f"full_check: healthy={health.get('overall_healthy')} "
                        f"slo={slo.get('slo_pct_display')} report={report_ok}"
                    ),
                    tags=["sre_monitoring", "full_check"],
                    source="sre_monitor",
                )
                return {
                    "status": "ok",
                    "health": health,
                    "slo": slo,
                    "chaos": chaos,
                    "report_written": report_ok,
                }

        except Exception as e:
            logger.error(f"[VECTOR][sre_monitor] run failed: {e}")
            self.deduct_points(30, "task_failed")
            return {"status": "error", "error": str(e)}

# ── Smoke test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = SREMonitor()
        assert agent.health_points == 500

        # Check SQLite and Ollama (Cloudflare check may fail offline — that's expected)
        health = await agent.check_system_health()
        print(f"sqlite_ok={health.get('sqlite_ok')} ollama_ok={health.get('ollama_ok')} "
              f"error_rate={health.get('error_rate')}")

        slo = agent.compute_slo()
        print(f"SLO={slo.get('slo_pct_display')} meets_target={slo.get('meets_target')}")

        chaos = await agent.run_chaos_probe()
        print(f"chaos latency={chaos.get('latency_ms')}ms decision={chaos.get('decision_made')}")

        ok = health.get("sqlite_ok", False)
        print(f"{'✅' if ok else '❌'} sre_monitor.py HP={agent.health_points}")

    asyncio.run(_smoke())
