"""Agent experience: a lineage ledger, XP/level, failure attribution and a distilled playbook.

HP answers "is this agent alive and well right now". It cannot also answer "what has this agent learned", because it falls on a bad day
and is shaped so it saturates. This module is the second axis (owner decision 2026-09-26, treating each agent as a person):

  * LEDGER  -- every outcome an agent's lineage (district + name, so successors share it) has had: what was asked, whether it worked,
    whether the result was independently verified, and -- for failures -- whose fault it was. Append-only: nothing is ever erased on
    death, so a successor can know what its predecessors did and what went wrong.
  * XP / LEVEL -- earned from outcomes, weighted by difficulty and novelty (the Nth identical success is worth much less), and worth far
    more when the result was verified. XP never decreases. Deaths do not erase experience; they temper the lineage's *standing*
    (each death multiplies standing XP by DEATH_STANDING_FACTOR), so death is meaningful without deleting what was learned.
  * FAULT ATTRIBUTION -- a failure caused by the environment (no API key, provider down, module missing, timeout) is not the agent's
    fault. The first failure of a kind is cheap and produces a lesson; only repeating it costs full price.
  * PLAYBOOK -- deterministic (no LLM) DO / DON'T lines built from the ledger for one lineage, small enough to inject into a prompt.

Recording is always on (it only appends rows). Anything that changes behaviour is behind VECTOR_HP_FAIR (default off) or
VECTOR_PLAYBOOK (default off) -- see AgentBase and Governor.
"""
from __future__ import annotations

__all__ = [
    "lineage_key", "record", "classify_failure", "failure_signature", "is_first_of_kind", "lineage_stats",
    "level_for_xp", "skill_table", "playbook", "own_fault_failures", "hp_fair_enabled", "playbook_enabled", "OUTCOMES",
    "fair_cull_enabled", "level_council_enabled", "explore_enabled", "explore_share", "attempts",
]

import math
import os
import re
import threading
import time
from typing import Any

from loguru import logger

OUTCOMES = ("success", "partial", "fail_own", "fail_env")
DEATH_STANDING_FACTOR = 0.75        # each death multiplies the lineage's standing XP; the ledger itself is never trimmed
BASE_XP = 10.0
UNVERIFIED_FACTOR = 0.3             # a success nobody checked is worth less than one that was
LEARNING_XP = 2.0                   # the first failure of a kind teaches something
MAX_LEVEL = 10

_ENV_PATTERNS = re.compile(
    r"api[ _-]?key|not configured|not set\b|no module named|not installed|modulenotfound|connection (?:refused|error|reset)|"
    r"timed? ?out|timeout|unreachable|unavailable|rate[ _-]?limit|quota|\b50[234]\b|service unavailable|provider|offline|"
    r"not running|no such host|name resolution|credentials? (?:missing|not)|permission denied|no (?:api|network|internet)|"
    r"ollama|cuda|out of memory|model .* not found",
    re.IGNORECASE,
)

_LOCK = threading.Lock()
_READY_CONN: Any = None          # the connection the table was last ensured on (tests and restarts swap the DB under us)
_CACHE: dict[str, tuple[float, dict]] = {}
_CACHE_TTL = 30.0


def hp_fair_enabled() -> bool:
    return os.environ.get("VECTOR_HP_FAIR", "0").strip().lower() in ("1", "true", "yes", "on")


def fair_cull_enabled() -> bool:
    """ON by default (VECTOR_FAIR_CULL=0 restores the old rank-only cull). Replayed against the recorded history on 2026-09-26: of 573
    real-agent deaths, 560 (98%) were agents at 200+ HP killed by the 02:00 rank cull for sitting near the bottom of a district
    with more than five agents -- no failure required. Owner rule: idle agents are safe; death is rare and meaningful."""
    return os.environ.get("VECTOR_FAIR_CULL", "1").strip().lower() in ("1", "true", "yes", "on")


def level_council_enabled() -> bool:
    """Council eligibility by level instead of HP (VECTOR_LEVEL_COUNCIL, default off until agents have levels)."""
    return os.environ.get("VECTOR_LEVEL_COUNCIL", "0").strip().lower() in ("1", "true", "yes", "on")


def explore_enabled() -> bool:
    """A share of GREEN dispatches go to a less-tried capable agent instead of the top-HP one (VECTOR_EXPLORE, default off)."""
    return os.environ.get("VECTOR_EXPLORE", "0").strip().lower() in ("1", "true", "yes", "on")


def explore_share() -> float:
    try:
        return max(0.0, min(0.5, float(os.environ.get("VECTOR_EXPLORE_SHARE", "0.15"))))
    except ValueError:
        return 0.15


def attempts(agent_or_key: Any) -> int:
    return int(sum(lineage_stats(agent_or_key).get("outcomes", {}).values()))


def playbook_enabled() -> bool:
    return os.environ.get("VECTOR_PLAYBOOK", "0").strip().lower() in ("1", "true", "yes", "on")


def lineage_key(agent: Any) -> str:
    return f"{getattr(agent, 'district', '') or 'unknown'}:{getattr(agent, 'name', '') or 'unknown'}"


def _conn():
    from core.memory.episodic import get_db_connection
    return get_db_connection()


def _ensure() -> None:
    global _READY_CONN
    conn = _conn()
    if conn is _READY_CONN:
        return
    with _LOCK:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS agent_experience (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   ts REAL NOT NULL,
                   lineage TEXT NOT NULL,
                   agent_id TEXT,
                   generation INTEGER,
                   kind TEXT NOT NULL,              -- outcome | death | note
                   task_type TEXT,
                   outcome TEXT,                    -- success | partial | fail_own | fail_env
                   verified INTEGER DEFAULT 0,
                   difficulty REAL DEFAULT 0.5,
                   signature TEXT,
                   note TEXT,
                   xp REAL DEFAULT 0,
                   hp_delta REAL DEFAULT 0
               )"""
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_exp_lineage ON agent_experience(lineage, task_type)")
        conn.commit()
        _READY_CONN = conn
        _CACHE.clear()


def _reset_for_tests() -> None:
    global _READY_CONN
    _READY_CONN = None
    _CACHE.clear()


def failure_signature(text: Any) -> str:
    """A stable identity for 'the same mistake': lowercase, digits/hex/paths collapsed, first 80 characters."""
    s = re.sub(r"[0-9a-f]{8,}|\d+", "#", str(text or "").lower())
    s = re.sub(r"[a-z]:[\\/][^\s]+|/[^\s]+/[^\s]+", "<path>", s)
    return re.sub(r"\s+", " ", s).strip()[:80]


def classify_failure(result: Any) -> str:
    """'env' when the failure text names something outside the agent's control, else 'own'. Conservative in one direction only:
    anything not clearly environmental is the agent's own."""
    if isinstance(result, dict):
        text = " ".join(str(result.get(k, "")) for k in ("error", "reason", "message", "note", "detail")) + " " + str(result.get("status", ""))
    else:
        text = str(result or "")
    return "env" if _ENV_PATTERNS.search(text) else "own"


def is_first_of_kind(lineage: str, task_type: str, signature: str) -> bool:
    _ensure()
    row = _conn().execute(
        "SELECT COUNT(*) FROM agent_experience WHERE lineage=? AND task_type=? AND signature=? AND outcome='fail_own'",
        (lineage, task_type, signature),
    ).fetchone()
    return (row[0] if row else 0) == 0


def own_fault_failures(lineage: str, since_seconds: float | None = None) -> int:
    _ensure()
    q, args = "SELECT COUNT(*) FROM agent_experience WHERE lineage=? AND outcome='fail_own'", [lineage]
    if since_seconds:
        q += " AND ts>=?"
        args.append(time.time() - since_seconds)
    row = _conn().execute(q, args).fetchone()
    return int(row[0] if row else 0)


def level_for_xp(standing_xp: float) -> int:
    return max(0, min(MAX_LEVEL, int(math.sqrt(max(0.0, standing_xp) / 25.0))))


def record(
    agent: Any,
    task_type: str,
    outcome: str,
    *,
    difficulty: float = 0.5,
    verified: bool = False,
    note: str = "",
    hp_delta: float = 0.0,
    weight: float = 1.0,
) -> float:
    """Append one outcome to the agent's lineage ledger and return the XP it earned. Never raises."""
    try:
        if outcome not in OUTCOMES:
            return 0.0
        _ensure()
        lineage = lineage_key(agent)
        task_type = str(task_type or "unknown")[:80]
        signature = failure_signature(note) if outcome.startswith("fail") else ""
        difficulty = max(0.2, min(1.0, float(difficulty)))
        xp = 0.0
        if outcome == "success":
            seen = _conn().execute(
                "SELECT COUNT(*) FROM agent_experience WHERE lineage=? AND task_type=? AND outcome='success'", (lineage, task_type)
            ).fetchone()[0]
            novelty = 1.0 / math.sqrt(1.0 + seen)               # the Nth identical success is worth 1/sqrt(1+N) of the first
            xp = BASE_XP * difficulty * novelty * (1.0 if verified else UNVERIFIED_FACTOR)
        elif outcome == "partial":
            xp = 2.0 * difficulty
        elif outcome == "fail_own" and is_first_of_kind(lineage, task_type, signature):
            xp = LEARNING_XP                                     # a new mistake is how a person learns; a repeated one teaches nothing
        xp = round(xp * max(0.0, min(1.0, float(weight))), 4)      # practice and help count for less than the real thing
        with _LOCK:
            conn = _conn()
            conn.execute(
                "INSERT INTO agent_experience (ts, lineage, agent_id, generation, kind, task_type, outcome, verified, difficulty,"
                " signature, note, xp, hp_delta) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (time.time(), lineage, getattr(agent, "id", ""), getattr(agent, "generation", None), "outcome", task_type, outcome,
                 1 if verified else 0, difficulty, signature, str(note or "")[:300], round(xp, 4), float(hp_delta)),
            )
            conn.commit()
        _CACHE.pop(lineage, None)
        return xp
    except Exception as e:
        logger.debug("[VECTOR][experience] record skipped: {}", e)
        return 0.0


def record_death(agent: Any, cause: str = "") -> None:
    try:
        _ensure()
        with _LOCK:
            conn = _conn()
            conn.execute(
                "INSERT INTO agent_experience (ts, lineage, agent_id, generation, kind, note) VALUES (?,?,?,?,?,?)",
                (time.time(), lineage_key(agent), getattr(agent, "id", ""), getattr(agent, "generation", None), "death", str(cause)[:300]),
            )
            conn.commit()
        _CACHE.pop(lineage_key(agent), None)
    except Exception as e:
        logger.debug("[VECTOR][experience] death not recorded: {}", e)


def lineage_stats(agent_or_key: Any) -> dict:
    """{'xp': total ever earned, 'deaths': n, 'standing_xp': xp after death tempering, 'level': from standing, 'outcomes': counts}."""
    key = agent_or_key if isinstance(agent_or_key, str) else lineage_key(agent_or_key)
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < _CACHE_TTL:
        return hit[1]
    try:
        _ensure()
        conn = _conn()
        xp = conn.execute("SELECT COALESCE(SUM(xp),0) FROM agent_experience WHERE lineage=?", (key,)).fetchone()[0]
        deaths = conn.execute("SELECT COUNT(*) FROM agent_experience WHERE lineage=? AND kind='death'", (key,)).fetchone()[0]
        counts = {o: n for o, n in conn.execute(
            "SELECT outcome, COUNT(*) FROM agent_experience WHERE lineage=? AND outcome IS NOT NULL GROUP BY outcome", (key,))}
        standing = float(xp) * (DEATH_STANDING_FACTOR ** int(deaths))
        stats = {"lineage": key, "xp": round(float(xp), 2), "deaths": int(deaths), "standing_xp": round(standing, 2),
                 "level": level_for_xp(standing), "outcomes": counts}
    except Exception as e:
        logger.debug("[VECTOR][experience] stats unavailable: {}", e)
        stats = {"lineage": key, "xp": 0.0, "deaths": 0, "standing_xp": 0.0, "level": 0, "outcomes": {}}
    _CACHE[key] = (time.time(), stats)
    return stats


def skill_table(agent_or_key: Any) -> dict[str, dict]:
    """Per task type: attempts, successes, own-fault and environmental failures, success rate (env failures excluded), verified rate."""
    key = agent_or_key if isinstance(agent_or_key, str) else lineage_key(agent_or_key)
    _ensure()
    out: dict[str, dict] = {}
    for tt, outcome, verified, n in _conn().execute(
        "SELECT task_type, outcome, verified, COUNT(*) FROM agent_experience WHERE lineage=? AND outcome IS NOT NULL "
        "GROUP BY task_type, outcome, verified", (key,)):
        s = out.setdefault(tt, {"n": 0, "success": 0, "partial": 0, "fail_own": 0, "fail_env": 0, "verified": 0})
        s["n"] += n
        s[outcome] += n
        if outcome == "success" and verified:
            s["verified"] += n
    for s in out.values():
        judged = s["success"] + s["partial"] + s["fail_own"]           # the environment's failures do not count against the agent
        s["success_rate"] = round(s["success"] / judged, 3) if judged else None
        s["verified_rate"] = round(s["verified"] / s["success"], 3) if s["success"] else None
    return out


def playbook(agent_or_key: Any, task_type: str | None = None, k: int = 6) -> list[str]:
    """Short, deterministic DO / DON'T lines for one lineage. `task_type` puts that task's lines first."""
    key = agent_or_key if isinstance(agent_or_key, str) else lineage_key(agent_or_key)
    try:
        _ensure()
        conn = _conn()
        lines: list[tuple[int, str]] = []
        skills = skill_table(key)
        for tt, s in skills.items():
            prio = 0 if tt == task_type else 1
            judged = s["success"] + s["partial"] + s["fail_own"]
            if judged >= 3 and s["success_rate"] is not None:
                if s["success_rate"] >= 0.8:
                    lines.append((prio, f"DO: '{tt}' is a strength ({s['success']}/{judged} succeeded)."))
                elif s["success_rate"] <= 0.4:
                    lines.append((prio, f"CAREFUL: '{tt}' often fails for you ({s['fail_own']} of {judged} attempts); check your inputs first."))
        for tt, sig, n in conn.execute(
            "SELECT task_type, signature, COUNT(*) c FROM agent_experience WHERE lineage=? AND outcome='fail_own' AND signature<>'' "
            "GROUP BY task_type, signature HAVING c>=1 ORDER BY c DESC, MAX(ts) DESC LIMIT 12", (key,)):
            lines.append((0 if tt == task_type else 1, f"DON'T: repeat this mistake on '{tt}': {sig} (seen {n}x)."))
        env = conn.execute("SELECT COUNT(*) FROM agent_experience WHERE lineage=? AND outcome='fail_env'", (key,)).fetchone()[0]
        if env:
            lines.append((2, f"NOTE: {env} of your failures came from the environment (missing key/provider/timeouts), not from you."))
        lines.sort(key=lambda x: x[0])
        return [t for _, t in lines[:k]]
    except Exception as e:
        logger.debug("[VECTOR][experience] playbook unavailable: {}", e)
        return []


if __name__ == "__main__":
    print("experience OK" if level_for_xp(100) == 2 and classify_failure({"error": "no api key configured"}) == "env" else "FAILED")
