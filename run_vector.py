"""VECTOR local launcher.

This is the single command entrypoint for the local VECTOR spine. It can run a
quick smoke check, start the autonomous loop, or launch the FastAPI server.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from loguru import logger


CORE_DISTRICTS = (
    ("governance-001", "GovernorCouncil", "governance"),
    ("coding-001", "CodeDistrict", "coding"),
    ("calendar-001", "CalendarDistrict", "time_calendar"),
    ("security-001", "SecurityDistrict", "security"),
    ("research-001", "ResearchDistrict", "research"),
    ("memory-001", "MemoryCuratorDistrict", "memory_curator"),
    ("health-001", "HealthDistrict", "health"),
    ("finance-001", "FinanceDistrict", "finance"),
    ("projects-001", "ProjectsDistrict", "projects"),
    ("reflection-001", "ReflectionDistrict", "reflection"),
)


def preflight_checks() -> None:
    """Verify critical runtime dependencies before starting the loop."""
    from pathlib import Path as _P
    from core.config import CONFIG as _cfg

    # 1. Ollama reachability
    try:
        import httpx as _httpx
        r = _httpx.get("http://127.0.0.1:11434/api/tags", timeout=3.0)
        if r.status_code == 200:
            models = [m["name"] for m in r.json().get("models", [])]
            logger.info(f"[VECTOR][preflight] Ollama OK — {len(models)} models")
            if not any("vector-focus" in m or "gemma4" in m for m in models):
                logger.warning(
                    "[VECTOR][preflight] vector-focus model missing — "
                    "run: ollama create vector-focus -f modelfiles/vector-focus.modelfile"
                )
        else:
            logger.warning("[VECTOR][preflight] Ollama returned non-200 — run: ollama serve")
    except Exception:
        logger.warning(
            "[VECTOR][preflight] Ollama unreachable at 127.0.0.1:11434 — "
            "run: ollama serve"
        )

    # 2. Hermes repo present
    hermes_repo = _P(_cfg.get("hermes", {}).get(
        "repo_path",
        "C:/Users/Arghyadeep/Desktop/V.E.C.T.O.R/GitHub/NousResearch_hermes-agent/repo",
    ))
    if hermes_repo.exists():
        logger.info(f"[VECTOR][preflight] Hermes repo found at {hermes_repo}")
    else:
        logger.warning(
            f"[VECTOR][preflight] Hermes repo missing at {hermes_repo} — "
            "District 6 comms will be unavailable"
        )

    # 3. Obsidian vault
    vault = _P(str(_cfg.get("vault_path", "")))
    if vault.exists():
        logger.info(f"[VECTOR][preflight] Obsidian vault OK at {vault}")
    else:
        logger.warning(
            f"[VECTOR][preflight] Obsidian vault not found at {vault} — "
            "Obsidian sync inactive"
        )

    # 4. SQLite DB dir writable
    db_path = _P(str(_cfg.get("db_path", "vector_memory.db")))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"[VECTOR][preflight] DB dir writable: {db_path.parent}")


def bootstrap_agents() -> int:
    """Register baseline district agents so the city is not empty at startup."""
    from core.city.agent_base import AgentBase
    from core.city.agent_registry import get_registry

    registry = get_registry()
    created = 0
    for agent_id, name, district in CORE_DISTRICTS:
        if registry.get(agent_id):
            continue
        registry.register(AgentBase(agent_id, name, district))
        created += 1
    return created


async def smoke_test() -> dict:
    """Verify the local spine can initialize and make one decision safely."""
    from core.brain.goal_system import GoalSystem
    from core.loop.context_engine import ContextEngine
    from core.loop.decision_engine import Candidate, DecisionEngine
    from core.memory.episodic import EpisodicMemory

    created = bootstrap_agents()
    memory = EpisodicMemory()
    memory.store(
        event_type="startup_smoke",
        content="VECTOR smoke test started from run_vector.py",
        tags=["startup", "smoke"],
        source="run_vector",
    )

    context_prompt = ContextEngine().session_hydration_prompt({"mode": "smoke"})
    actions = GoalSystem().generate_immediate_actions(limit=4)
    candidates = [
        Candidate(
            action_type=a["action"],
            params={"goal_id": a["goal_id"], "title": a["title"]},
            goal_ids=[a["goal_id"]],
            urgency={"high": 0.9, "medium": 0.5, "low": 0.2}.get(a.get("urgency"), 0.5),
            confidence=0.7,
            source="run_vector_smoke",
        )
        for a in actions
    ]
    decision = await DecisionEngine().evaluate(candidates)
    stats = memory.get_stats()

    return {
        "status": "ok",
        "agents_bootstrapped": created,
        "hydration_chars": len(context_prompt),
        "candidates_evaluated": decision.evaluated,
        "winner": decision.winner.action_type,
        "winner_score": decision.winner.total_score,
        "memory_stats": stats,
    }


async def run_loop() -> None:
    """Start the autonomous loop. This is intended to run until interrupted."""
    bootstrap_agents()
    from core.loop.autonomous_loop import AutonomousLoop

    await AutonomousLoop().run_forever()


def run_api(host: str, port: int) -> None:
    """Start the local FastAPI server using the modular API."""
    bootstrap_agents()
    import uvicorn
    from core.api import create_app
    app = create_app()
    uvicorn.run(app, host=host, port=port, reload=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="VECTOR local launcher")
    parser.add_argument(
        "mode",
        nargs="?",
        default="loop",
        choices=("loop", "api", "smoke"),
        help="Default is loop. Use smoke for a one-shot startup check.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logger.info(f"[VECTOR][launcher] mode={args.mode}")

    if args.mode == "api":
        run_api(args.host, args.port)
        return 0

    if args.mode == "smoke":
        result = asyncio.run(smoke_test())
        print(result)
        return 0 if result["status"] == "ok" else 1

    try:
        asyncio.run(run_loop())
        return 0
    except KeyboardInterrupt:
        logger.info("[VECTOR][launcher] stopped by owner")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
