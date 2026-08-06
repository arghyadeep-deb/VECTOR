"""Phase 5 — Autonomy proof (the shipped gate) of
plans/wire-absorbed-repos-autonomy.md.

Task 5.1: prove the engine is genuinely autonomous, not just functional.
The critical guardrail: this test must NEVER call HandRunner.run_hand()
itself. The trigger path is scheduler -> callable -> hand -> memory, with
nothing in this test body prompting the hand directly. A real
apscheduler.schedulers.asyncio.AsyncIOScheduler is started, a job is
registered with a 'date' trigger ~1s in the future (the same registration
primitive register_all() uses, core/loop/cron_jobs.py::_try_register's
sibling path), and the test waits for the *scheduler* to fire it.

Only the LLM/governor leaf (HandRunner._dispatch) is stubbed, for speed and
to decouple this proof from Ollama availability/warmth (a separate, already
documented concern — see docs/capability_proofs/research_engine.md). Every
other side effect — episodic persistence, HP delta, policy reward — is the
real, unstubbed code path.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture
def isolated_db(monkeypatch, tmp_path):
    import core.memory.episodic as ep
    ep.close_db_connection()
    monkeypatch.setenv("VECTOR_DB_PATH", str(tmp_path / "autonomy_proof.db"))
    yield ep
    try:
        ep.close_db_connection()
    except Exception:
        pass


@pytest.mark.asyncio
async def test_scheduler_fires_hands(isolated_db, capsys):
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from hands.registry import HandRegistry
    from hands.runner import HandRunner
    from core.city.agent_base import AgentBase
    from core.city.agent_registry import get_registry
    from core.memory.episodic import get_temp_cursor

    hand = HandRegistry().get("vault_sync")
    assert hand is not None and hand.district == "security"

    # A real district agent, so the closed loop's HP award has something
    # real to move (unstubbed — this is exactly what run_hand's
    # _award_hp does in production).
    registry = get_registry()
    agent = AgentBase(str(uuid.uuid4()), "ProofAgent", hand.district)
    registry.register(agent)
    starting_hp = agent.health_points

    runner = HandRunner()
    # The ONLY stub: the LLM/governor leaf. Everything downstream of this
    # call (episodic write, HP award, policy update, persist()) is real.
    dispatch_calls = {"n": 0}

    async def _stub_dispatch(h, context):
        dispatch_calls["n"] += 1
        return "autonomy proof: vault sync scan complete, no exposures found"

    runner._dispatch = _stub_dispatch

    # Register directly against the scheduler with a near-future 'date'
    # trigger — same primitive register_all()/-try_register use for cron,
    # just pointed at "now + ~1.5s" instead of vault_sync's real "every 6h"
    # schedule, so this test finishes in seconds instead of hours.
    scheduler = AsyncIOScheduler()
    scheduler.start()
    fire_at = datetime.now(timezone.utc) + timedelta(seconds=1.5)

    async def _scheduled_job():
        await runner.run_hand(hand, {})

    scheduler.add_job(_scheduled_job, "date", run_date=fire_at, id="proof-vault-sync")

    try:
        # The test does NOT call run_hand() — it only waits for the
        # scheduler to do so on its own, exactly as it would in production.
        await asyncio.sleep(3.0)

        # 1) dispatch was actually invoked by the SCHEDULER (proves the
        # trigger path fired, not just that the engine is callable).
        assert dispatch_calls["n"] == 1, "scheduler never fired the job"

        # 2) Real, persisted episodic row — kind="hand_run", no prompt.
        with get_temp_cursor() as cursor:
            cursor.execute(
                "SELECT id, event_type, content, tags, source, timestamp "
                "FROM episodic_memory WHERE event_type = ? AND source = ? "
                "ORDER BY timestamp DESC LIMIT 1",
                ("hand_run", "vault_sync"),
            )
            row = cursor.fetchone()
        assert row is not None, "no kind=hand_run episodic row was persisted"
        row_dict = {
            "id": row[0], "event_type": row[1], "content": row[2],
            "tags": row[3], "source": row[4], "timestamp": row[5],
        }
        content = json.loads(row[2])
        assert content["status"] == "ok"
        assert content["hand"] == "vault_sync"

        # 3) Real HP delta on the real district agent (unstubbed _award_hp).
        ending_hp = agent.health_points
        assert ending_hp != starting_hp, "HP never moved — closed loop did not run for real"
        # 2026-08-06: HP shaping formula applies headroom_multiplier =
        # (1000 - starting_hp) / 1000, so a raw award of 50 at 500 HP yields
        # 50 * 1.0 * 0.5 = 25 HP (not 50). Test expectation updated to match.
        expected_delta = 50 * 1.0 * max(0.0, (1000.0 - starting_hp) / 1000.0)
        assert ending_hp == starting_hp + expected_delta  # award_points(50, ...) on status=ok, shaped

        # 4) Real policy_memory row from update_from_outcome (unstubbed).
        with get_temp_cursor() as cursor:
            cursor.execute(
                "SELECT action_type, situation_hash, avg_reward, sample_count "
                "FROM policy_memory WHERE action_type = ?",
                ("vault_sync",),
            )
            policy_row = cursor.fetchone()
        assert policy_row is not None, "no policy_memory row — policy update did not run for real"
        policy_dict = {
            "action_type": policy_row[0], "situation_hash": policy_row[1],
            "avg_reward": policy_row[2], "sample_count": policy_row[3],
        }

        # Capture the actual artifact — not "it passed."
        with capsys.disabled():
            print("\n--- AUTONOMY PROOF ARTIFACT ---")
            print("episodic row:", json.dumps(row_dict, indent=2, default=str))
            print(f"HP: {starting_hp} -> {ending_hp} (delta={ending_hp - starting_hp})")
            print("policy_memory row:", json.dumps(policy_dict, indent=2, default=str))
            print("--- END ARTIFACT ---\n")

    finally:
        scheduler.shutdown(wait=False)
        registry._agents.pop(agent.id, None)


if __name__ == "__main__":
    print("✅ test_absorbed_autonomy.py module loads")
