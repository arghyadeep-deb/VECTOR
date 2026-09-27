"""Work board: practice drills for agents that have had no work, so an idle agent still grows without ever being at risk.

Owner decisions 2026-09-26: idle agents are safe (they never lose HP for being idle); agents should still get to work; the practice
uses LOCAL resources only and never competes with the owner. This module is the framework for that, and it is deliberately honest
about what it is:

  * A DRILL is a small real task with an answer that can be checked independently of the agent (`verify`). Only drills whose answer is
    known count; there is no invented busywork and no self-graded success.
  * A drill moves NO HP and earns reduced XP (GYM_WEIGHT) -- practice is worth less than the real thing and can never farm HP. Novelty
    decay in the ledger and a per-agent daily cap stop XP farming too.
  * It runs only when the owner is not coding, the bus is not busy, and VECTOR_GYM is on (default OFF). Drills flagged `needs_llm` are
    off unless VECTOR_GYM_LLM is on too, because an LLM drill cannot be guaranteed local-only from here.
  * Coverage is reported plainly: which agents have a drill and which do not. Most of the 230 agents' 700-odd capabilities have no
    safe canned test yet; writing drills per district is content work, and `register_drill()` makes each one a few lines.

Real work still comes from goals, plans, the owner and other agents (core/city/a2a_bus.py). The board only fills gaps.
"""
from __future__ import annotations

__all__ = ["Drill", "WorkBoard", "register_drill", "get_board", "gym_enabled", "GYM_WEIGHT"]

import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from loguru import logger

GYM_WEIGHT = 0.3
MAX_DRILLS_PER_AGENT_PER_DAY = 3


def gym_enabled() -> bool:
    return os.environ.get("VECTOR_GYM", "0").strip().lower() in ("1", "true", "yes", "on")


def _gym_llm_enabled() -> bool:
    return os.environ.get("VECTOR_GYM_LLM", "0").strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Drill:
    name: str
    task_type: str                              # a real, GREEN task type the agent already handles
    matches: Callable[[Any], bool]              # which agents can be drilled with it
    verify: Callable[[dict], bool]              # independent check of the answer
    params: dict = field(default_factory=dict)
    difficulty: float = 0.3
    needs_llm: bool = False


_DRILLS: list[Drill] = []


def register_drill(drill: Drill) -> Drill:
    _DRILLS[:] = [d for d in _DRILLS if d.name != drill.name] + [drill]
    return drill


def _caps(agent: Any) -> set[str]:
    return {str(c).lower() for c in (getattr(agent, "capabilities", None) or [])}


def _git(*args: str) -> str:
    """Ask git directly (not through any agent) -- the ground truth a drill's answer is checked against."""
    import subprocess
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    return subprocess.run(["git", *args], cwd=str(root), capture_output=True, text=True, timeout=15, check=True).stdout.strip()


def _verify_git_status(r: dict) -> bool:
    return isinstance(r, dict) and r.get("branch") == _git("rev-parse", "--abbrev-ref", "HEAD") and isinstance(r.get("modified"), list)


def _verify_recent_commits(r: dict) -> bool:
    commits = r.get("commits") if isinstance(r, dict) else None
    if not isinstance(commits, list) or not commits or not all(isinstance(c, dict) and c.get("hash") and c.get("message") for c in commits):
        return False
    head = _git("rev-parse", "HEAD")
    return head.startswith(str(commits[0]["hash"])[:8])


def _install_starter_drills() -> None:
    # Deterministic, read-only, no LLM: the GitBot's own read handlers, each answer compared with what git itself says.
    register_drill(Drill(
        name="git_status_matches_git", task_type="git_status",
        matches=lambda a: "git_status" in _caps(a) or getattr(a, "name", "") == "GitBot",
        verify=_verify_git_status, difficulty=0.3,
    ))
    register_drill(Drill(
        name="recent_commits_match_git", task_type="recent_commits",
        matches=lambda a: "recent_commits" in _caps(a) or getattr(a, "name", "") == "GitBot",
        params={"limit": 3}, verify=_verify_recent_commits, difficulty=0.3,
    ))


_SSML_TEXT = "Hello world. VECTOR narrates itself. Ask & answer <fast>"   # no trailing period: the agent appends one per sentence
_REVIEW_CODE = "async def go():" + chr(10) + "    value = eval(input())" + chr(10) + "    time.sleep(1)" + chr(10)


def _verify_ssml(r: dict) -> bool:
    """The SSML must be well-formed XML whose <s> elements carry exactly the input sentences (checked with an XML parser)."""
    import xml.etree.ElementTree as ET
    if not isinstance(r, dict) or not isinstance(r.get("ssml"), str):
        return False
    try:
        root = ET.fromstring(r["ssml"])
    except ET.ParseError:
        return False
    got = ["".join(s.itertext()).strip() for s in root.findall("s")]
    return root.tag == "speak" and got == [part.strip() + "." for part in _SSML_TEXT.split(". ") if part.strip()]


def _verify_review(r: dict) -> bool:
    """The static scan must flag exactly the lines Python's own ast finds calling eval() and time.sleep(), eval as HIGH."""
    import ast
    if not isinstance(r, dict) or not isinstance(r.get("issues"), list):
        return False
    want_eval, want_sleep = set(), set()
    for node in ast.walk(ast.parse(_REVIEW_CODE)):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "eval":
                want_eval.add(node.lineno)
            if isinstance(node.func, ast.Attribute) and node.func.attr == "sleep":
                want_sleep.add(node.lineno)
    flagged = {i["line"]: i.get("severity") for i in r["issues"] if isinstance(i, dict) and i.get("line")}
    return set(flagged) == want_eval | want_sleep and all(flagged[n] == "HIGH" for n in want_eval)


def _install_district_drills() -> None:
    # Pure, deterministic handlers with no side effects and no LLM; each answer is checked by something other than the agent.
    register_drill(Drill(
        name="ssml_is_well_formed_xml", task_type="text_to_ssml",
        matches=lambda a: "text_to_ssml" in _caps(a) or getattr(a, "name", "") == "VoiceGenerator",
        params={"text": _SSML_TEXT}, verify=_verify_ssml, difficulty=0.3,
    ))
    register_drill(Drill(
        name="static_review_flags_the_lines_ast_finds", task_type="check_pep8",
        # only while the reviewer is in its deterministic static mode; with VECTOR_PYTHON_REVIEW_LLM=1 the same task calls an LLM
        matches=lambda a: ("check_pep8" in _caps(a) or getattr(a, "name", "") == "PythonReviewer")
        and os.environ.get("VECTOR_PYTHON_REVIEW_LLM") != "1",
        params={"code": _REVIEW_CODE, "filename": "drill.py"}, verify=_verify_review, difficulty=0.4,
    ))


_install_starter_drills()
_install_district_drills()


class WorkBoard:
    def __init__(self, bus: Any | None = None, registry: Any | None = None) -> None:
        self._bus = bus
        self._registry = registry
        self._last_cycle = 0.0

    def _agents(self) -> list:
        if self._registry is not None:
            return [a for a in self._registry.get_all_agents() if getattr(a, "is_alive", True)]
        from core.city.a2a_bus import get_bus
        return (self._bus or get_bus()).agents()

    def drills_for(self, agent: Any) -> list[Drill]:
        out = []
        for d in _DRILLS:
            if d.needs_llm and not _gym_llm_enabled():
                continue
            try:
                if d.matches(agent):
                    out.append(d)
            except Exception:
                continue
        return out

    # ── who is idle, who can be drilled ─────────────────────────────────────────────────────────────────────────────────
    @staticmethod
    def _last_outcome_ts(agent: Any) -> float:
        try:
            from core.city import experience
            experience._ensure()
            row = experience._conn().execute(
                "SELECT COALESCE(MAX(ts),0) FROM agent_experience WHERE lineage=? AND outcome IS NOT NULL",
                (experience.lineage_key(agent),)).fetchone()
            return float(row[0] if row else 0.0)
        except Exception:
            return 0.0

    def idle_agents(self, hours: float = 24.0) -> list:
        cutoff = time.time() - hours * 3600
        return sorted((a for a in self._agents() if self._last_outcome_ts(a) < cutoff), key=self._last_outcome_ts)

    def coverage(self) -> dict:
        agents = self._agents()
        with_drill = [a for a in agents if self.drills_for(a)]
        per_district: dict[str, dict] = {}
        for a in agents:
            slot = per_district.setdefault(getattr(a, "district", "unknown"), {"agents": 0, "with_drill": 0})
            slot["agents"] += 1
            slot["with_drill"] += 1 if a in with_drill else 0
        return {
            "agents": len(agents), "with_drill": len(with_drill),
            "without_drill": len(agents) - len(with_drill),
            "drills": [{"name": d.name, "task_type": d.task_type, "needs_llm": d.needs_llm} for d in _DRILLS],
            "districts_without_any_drill": sorted(d for d, v in per_district.items() if v["with_drill"] == 0),
            "per_district": per_district, "gym_enabled": gym_enabled(),
        }

    @staticmethod
    def _drilled_today(agent: Any) -> int:
        try:
            from core.city import experience
            experience._ensure()
            start = time.mktime(time.strptime(time.strftime("%Y-%m-%d"), "%Y-%m-%d"))
            row = experience._conn().execute(
                "SELECT COUNT(*) FROM agent_experience WHERE lineage=? AND task_type LIKE 'gym:%' AND ts>=?",
                (experience.lineage_key(agent), start)).fetchone()
            return int(row[0] if row else 0)
        except Exception:
            return 0

    @staticmethod
    def _owner_busy() -> bool:
        try:
            from core.sensing.stuck_detector import get_active_session
            return get_active_session() is not None
        except Exception:
            return False

    # ── one gym cycle ───────────────────────────────────────────────────────────────────────────────────────────────────
    async def run_cycle(self, max_agents: int = 2, *, force: bool = False, idle_hours: float = 24.0) -> dict:
        """Drill up to `max_agents` idle agents. Returns what happened; never raises."""
        report: dict = {"ran": [], "skipped": ""}
        if not (force or gym_enabled()):
            report["skipped"] = "VECTOR_GYM is off"
            return report
        if not force and self._owner_busy():
            report["skipped"] = "owner is coding; practice waits"
            return report
        from core.city import experience
        from core.city.a2a_bus import get_bus
        bus = self._bus or get_bus()
        done = 0
        for agent in self.idle_agents(idle_hours):
            if done >= max_agents:
                break
            drills = self.drills_for(agent)
            if not drills or self._drilled_today(agent) >= MAX_DRILLS_PER_AGENT_PER_DAY:
                continue
            drill = drills[int(time.time() // 3600) % len(drills)]
            reply = await bus.ask("work_board", drill.task_type, dict(drill.params), to=getattr(agent, "id", None),
                                  timeout=30, origin="loop", no_reward=True)
            passed = bool(reply.ok and drill.verify(reply.result))
            experience.record(agent, f"gym:{drill.name}", "success" if passed else ("fail_env" if not reply.delivered else "fail_own"),
                              difficulty=drill.difficulty, verified=passed, weight=GYM_WEIGHT,
                              note="" if passed else (reply.refused or reply.error or "drill answer did not verify")[:200])
            report["ran"].append({"agent": getattr(agent, "name", ""), "drill": drill.name, "passed": passed,
                                  "delivered": reply.delivered, "why": reply.refused or reply.error})
            done += 1
        if not report["ran"]:
            report["skipped"] = "no idle agent has a drill (or all reached today's cap)"
        return report


_BOARD: WorkBoard | None = None


def get_board() -> WorkBoard:
    global _BOARD
    if _BOARD is None:
        _BOARD = WorkBoard()
    return _BOARD


if __name__ == "__main__":
    print("work_board OK" if len(_DRILLS) >= 2 else "FAILED")
