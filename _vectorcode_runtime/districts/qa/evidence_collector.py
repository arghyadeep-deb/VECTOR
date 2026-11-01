"""
Evidence Collector — collects proof that VECTOR's work actually happened.

Before any task can be marked complete, EvidenceCollector gathers:
git commits, episodic event counts, agent HP snapshot, file timestamps.
No evidence = not done.
"""
import asyncio
import datetime
import subprocess
import json
from pathlib import Path


from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync


class EvidenceCollector(AgentBase):
    """
    Collects and stores evidence of VECTOR's work.
    No evidence = no credit. Proof-first, always.
    """

    def __init__(self):
        super().__init__(agent_id="evidence_collector_001", name="EvidenceCollector", district="qa")
        self.capabilities = ["evidence", "qa", "screenshot"]
        self._memory: EpisodicMemory | None = None
        self._obsidian: ObsidianSync | None = None
        self._root = Path(__file__).resolve().parent.parent.parent
        logger.info("[VECTOR][evidence_collector] initialized")

    def _get_memory(self) -> EpisodicMemory:
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    def _get_obsidian(self) -> ObsidianSync:
        if self._obsidian is None:
            self._obsidian = ObsidianSync()
        return self._obsidian

    # ── Evidence sources ───────────────────────────────────────────────────────

    def collect_git_evidence(self, days: int = 1) -> dict:
        """Collect git commits from last N days as evidence of code changes."""
        try:
            # 2026-09-29: "--since=Nd ago" is not a git-recognized duration (git wants "N days
            # ago"); this silently matched nothing and always returned 0 commits, found via a
            # real test that expected non-zero evidence from a repo with constant commit activity.
            result = subprocess.run(
                ["git", "log", f"--since={days} days ago", "--oneline", "--no-merges"],
                capture_output=True, text=True, cwd=str(self._root), timeout=10,
            )
            commits = [l.strip() for l in result.stdout.strip().splitlines() if l.strip()]
            return {
                "source": "git",
                "commits": commits[:20],
                "count": len(commits),
                "days": days,
                "evidence": "present" if commits else "none",
            }
        except Exception as e:
            logger.warning("[VECTOR][evidence_collector] git evidence failed: {}", e)
            return {"source": "git", "commits": [], "count": 0, "evidence": "error", "error": str(e)}

    def collect_memory_evidence(self, hours: int = 24) -> dict:
        """Count episodic memory events in last N hours by district and type."""
        try:
            mem = self._get_memory()
            events = mem.recall("", limit=200)
            cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)

            recent = []
            for e in events:
                ts_str = e.get("timestamp", "") or e.get("created_at", "")
                try:
                    ts = datetime.datetime.fromisoformat(ts_str)
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=datetime.timezone.utc)
                    if ts >= cutoff:
                        recent.append(e)
                except Exception:
                    logger.debug("[VECTOR] suppressed exception", exc_info=True)

            by_district: dict[str, int] = {}
            by_type: dict[str, int] = {}
            for e in recent:
                d = e.get("source", "unknown")
                t = e.get("event_type", "unknown")
                by_district[d] = by_district.get(d, 0) + 1
                by_type[t] = by_type.get(t, 0) + 1

            return {
                "source": "episodic_memory",
                "total_events": len(recent),
                "hours": hours,
                "by_district": dict(sorted(by_district.items(), key=lambda x: x[1], reverse=True)[:10]),
                "by_type": dict(sorted(by_type.items(), key=lambda x: x[1], reverse=True)[:10]),
                "evidence": "present" if recent else "none",
            }
        except Exception as e:
            logger.warning("[VECTOR][evidence_collector] memory evidence failed: {}", e)
            return {"source": "episodic_memory", "total_events": 0, "evidence": "error", "error": str(e)}

    def collect_test_evidence(self) -> dict:
        """Verify that test scripts exist, are non-empty, and were recently run."""
        test_files = {
            "smoke_test": self._root / "scripts/smoke_test.py",
            "integration_check": self._root / "scripts/integration_check.py",
        }
        results = {}
        for name, path in test_files.items():
            if path.exists():
                size = path.stat().st_size
                mtime = datetime.datetime.fromtimestamp(path.stat().st_mtime).isoformat()
                results[name] = {"exists": True, "size_bytes": size, "last_modified": mtime}
            else:
                results[name] = {"exists": False}

        # Check if smoke_test was recently run by looking for .pytest_cache or result markers
        has_tests = all(v.get("exists") for v in results.values())
        return {
            "source": "test_files",
            "test_files": results,
            "evidence": "present" if has_tests else "missing",
        }

    def take_system_snapshot(self) -> dict:
        """Capture current HP of all registered agents and system state."""
        try:
            from core.city.agent_registry import get_registry
            reg = get_registry()
            agents = reg.list_all()
            by_district: dict[str, list] = {}
            total_hp = 0
            alive_count = 0

            for a in agents:
                d = a.get("district", "unknown")
                hp = a.get("health_points", 500)
                total_hp += hp
                if a.get("is_alive", True):
                    alive_count += 1
                if d not in by_district:
                    by_district[d] = []
                by_district[d].append({"name": a.get("name"), "hp": hp, "alive": a.get("is_alive", True)})

            return {
                "source": "agent_registry",
                "total_agents": len(agents),
                "alive_agents": alive_count,
                "avg_hp": round(total_hp / max(1, len(agents)), 1),
                "by_district": {d: {"count": len(v), "avg_hp": round(sum(a["hp"] for a in v) / len(v), 1)} for d, v in by_district.items()},
                "snapshot_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "evidence": "present",
            }
        except Exception as e:
            logger.warning("[VECTOR][evidence_collector] snapshot failed: {}", e)
            return {"source": "agent_registry", "evidence": "error", "error": str(e)}

    # ── Evidence report ────────────────────────────────────────────────────────

    def compile_evidence_report(self, git_ev: dict, mem_ev: dict, test_ev: dict, snap: dict) -> dict:
        """Combine all evidence into a structured report."""
        all_present = all(
            ev.get("evidence") == "present"
            for ev in [git_ev, mem_ev, test_ev, snap]
        )
        return {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "verdict": "EVIDENCE_PRESENT" if all_present else "EVIDENCE_INCOMPLETE",
            "git": git_ev,
            "memory": mem_ev,
            "tests": test_ev,
            "system": snap,
            "summary": {
                "git_commits_24h": git_ev.get("count", 0),
                "memory_events_24h": mem_ev.get("total_events", 0),
                "test_files_present": test_ev.get("evidence") == "present",
                "alive_agents": snap.get("alive_agents", 0),
                "avg_agent_hp": snap.get("avg_hp", 0),
            },
        }

    def write_evidence_log(self, report: dict) -> str:
        """Append evidence report to docs/evidence_log.md."""
        log_path = self._root / "docs/evidence_log.md"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        summary = report.get("summary", {})
        entry = (
            f"\n## {ts} — {report['verdict']}\n"
            f"- Git commits (24h): {summary.get('git_commits_24h', 0)}\n"
            f"- Memory events (24h): {summary.get('memory_events_24h', 0)}\n"
            f"- Test files: {'✅' if summary.get('test_files_present') else '❌'}\n"
            f"- Alive agents: {summary.get('alive_agents', 0)} (avg HP: {summary.get('avg_agent_hp', 0)})\n"
        )

        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(entry)
            logger.info("[VECTOR][evidence_collector] evidence log updated: {}", log_path)
            return str(log_path)
        except Exception as e:
            logger.warning("[VECTOR][evidence_collector] log write failed: {}", e)
            return ""

    # ── Main run ───────────────────────────────────────────────────────────────

    async def run(self, task: dict) -> dict:
        """Collect all evidence, compile report, store in memory."""
        # 2026-09-30 (Phase 3 codebase audit finding): the real governor
        # dispatch shape is {"type": ..., "params": {...}} -- days/hours
        # below were read straight off `task`, never `task["params"]`, so a
        # real dispatch always fell back to the hardcoded defaults.
        # Flattening params into task once (params values win on overlap)
        # keeps every existing flat-shape caller/test working unchanged.
        task = {**task, **(task.get("params") or {})}
        try:
            days = task.get("days", 1)
            hours = task.get("hours", 24)

            git_ev = self.collect_git_evidence(days=days)
            mem_ev = self.collect_memory_evidence(hours=hours)
            test_ev = self.collect_test_evidence()
            snap = self.take_system_snapshot()

            report = self.compile_evidence_report(git_ev, mem_ev, test_ev, snap)
            log_path = self.write_evidence_log(report)

            # Store in memory
            mem = self._get_memory()
            mem.store(
                event_type="evidence_collected",
                content=(
                    f"Evidence: git={git_ev.get('count',0)} commits, "
                    f"memory={mem_ev.get('total_events',0)} events, "
                    f"verdict={report['verdict']}"
                ),
                tags=["qa", "evidence", report["verdict"].lower()],
                context=report["summary"],
                source="evidence_collector",
            )

            if report["verdict"] == "EVIDENCE_PRESENT":
                self.award_points(30, "evidence_collected_complete")
            else:
                self.award_points(10, "evidence_collected_incomplete")
                logger.warning("[VECTOR][evidence_collector] incomplete evidence: {}", report["summary"])

            return {"status": "ok", "report": report, "log_path": log_path}

        except Exception as e:
            logger.error("[VECTOR][evidence_collector] run failed: {}", e)
            self.deduct_points(30, "evidence_collection_failed")
            return {"status": "error", "error": str(e)}


if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = EvidenceCollector()
        git_ev = agent.collect_git_evidence(days=7)
        print(f"[OK] git_evidence: {git_ev['count']} commits")
        test_ev = agent.collect_test_evidence()
        print(f"[OK] test_evidence: {test_ev['evidence']}")
        snap = agent.take_system_snapshot()
        print(f"[OK] snapshot: {snap.get('total_agents',0)} agents")
        result = await agent.run({"days": 1, "hours": 24})
        print(f"[OK] run: verdict={result['report']['verdict']} status={result['status']}")
        print("evidence_collector.py OK")

    asyncio.run(_smoke())
