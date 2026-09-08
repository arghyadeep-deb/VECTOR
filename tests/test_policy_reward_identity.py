"""
Task 89 (Agent D — R4/R5, Policy/Reward Identity).

Covers the round-trip correctness of PolicyMemory.make_situation_hash() as
the single canonical identity function shared by decision_engine.py's
reader (DecisionEngine._make_situation_hash) and the connected writers in
autonomous_loop.py (VectorCode reward, 5-factor reward). The
suppression/reward channel separation (record_suppression() not polluting
avg_reward) is covered in tests/test_counterfactual_block_penalizes_policy.py
-- this file focuses on identity (same situation -> same key; different
situation -> different key) and the writer -> storage -> reader round trip.

No live process, no network, no provider calls. Uses the real, shared
episodic-memory connection (PolicyMemory has no db_path override -- see
tests/test_counterfactual_block_penalizes_policy.py's own comment on this),
with uuid-unique action_types per test so nothing here can collide with real
production rows (including the ~29,000-sample historical analyze_progress
bucket, which this file never reads or writes).
"""
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_same_situation_same_key_two_independent_call_sites():
    """Test 1: same action_type + same meaningful params -> same canonical
    identity, computed via two independent call sites (mirrors a writer call
    and the reader's own call), byte-identical."""
    from core.memory.policy import PolicyMemory
    from core.loop.decision_engine import DecisionEngine, Candidate

    action_type = f"test_identity_{uuid.uuid4().hex[:8]}"
    goal_id = f"g_{uuid.uuid4().hex[:8]}"
    params = {"goal_id": goal_id, "title": "Start: some goal"}

    # Call site 1: a writer-shaped direct call (mirrors autonomous_loop.py's
    # writers, e.g. `pm.make_situation_hash(winner.action_type, winner.params)`).
    pm = PolicyMemory()
    writer_hash = pm.make_situation_hash(action_type, dict(params))

    # Call site 2: the reader's own path -- DecisionEngine._make_situation_hash()
    # via a real Candidate, exactly as _score_candidate() invokes it.
    engine = DecisionEngine()
    candidate = Candidate(action_type=action_type, params=dict(params), goal_ids=[goal_id])
    reader_hash = engine._make_situation_hash(candidate)

    assert writer_hash == reader_hash, (
        f"writer and reader must compute byte-identical canonical hashes for "
        f"the same (action_type, params): writer={writer_hash!r} reader={reader_hash!r}"
    )
    assert writer_hash.startswith("v2:"), "new canonical hashes must carry the v2: prefix"


def test_different_goal_id_different_key():
    """Test 2a: meaningfully different params (different goal_id) -> different
    canonical identity."""
    from core.memory.policy import PolicyMemory

    pm = PolicyMemory()
    action_type = f"test_identity_{uuid.uuid4().hex[:8]}"
    h1 = pm.make_situation_hash(action_type, {"goal_id": "g_alpha"})
    h2 = pm.make_situation_hash(action_type, {"goal_id": "g_beta"})
    assert h1 != h2, "different goal_id must produce a different canonical identity"


def test_different_action_type_different_key():
    """Test 2b: meaningfully different action_type -> different canonical
    identity, even with identical params."""
    from core.memory.policy import PolicyMemory

    pm = PolicyMemory()
    suffix = uuid.uuid4().hex[:8]
    params = {"goal_id": f"g_{suffix}"}
    h1 = pm.make_situation_hash(f"analyze_progress_{suffix}", params)
    h2 = pm.make_situation_hash(f"research_topic_{suffix}", params)
    assert h1 != h2, "different action_type must produce a different canonical identity"


def test_real_outcome_persisted_and_round_trips_through_reader(monkeypatch):
    """Tests 3 + 4: a real outcome reward, written via the (now-corrected)
    5-factor writer path in autonomous_loop.py's _act_on(), is persisted
    under the canonical identity, AND the same decision's canonical identity,
    looked up via the reader's own get_score() path (DecisionEngine._get_policy()
    -> get_score()), retrieves that exact persisted reward. A genuine
    writer -> storage -> reader round trip, not two independent assertions.

    Mocks the governor/gateway dispatch (no real execution, no network) so
    only the reward-computation-and-write path under test actually runs.
    """
    import asyncio
    from core.loop.autonomous_loop import AutonomousLoop
    from core.loop.decision_engine import DecisionEngine, Candidate

    action_type = f"test_5factor_{uuid.uuid4().hex[:8]}"
    goal_id = f"g_{uuid.uuid4().hex[:8]}"
    params = {"goal_id": goal_id, "title": "Start: round trip test goal"}

    loop = AutonomousLoop()

    # Skill matching and the VectorCode/swarm/red-team/threat-scan branches
    # must all no-op so _act_on() falls through to the plain governor-dispatch
    # + 5-factor-reward path this test targets.
    class _FakeSkillManager:
        def match(self, action_type, params):
            return []

    monkeypatch.setattr(
        "vectorcode.src.skills.manager.SkillManager", lambda: _FakeSkillManager()
    )

    class _FakeGovernor:
        async def dispatch(self, task):
            # A clean "ok" outcome, no override/correction -> completed=1.0,
            # not_overridden=1.0, not_corrected=1.0. goal_progress defaults to
            # 0.5 (result.get("goal_progress", 0.5)). No user_feedback in
            # episodic memory for this fresh, uuid-unique action_type -> uf=0.7.
            # reward = 0.7*0.40 + 0.5*0.25 + 1.0*0.15 + 1.0*0.15 + 1.0*0.05
            #        = 0.28 + 0.125 + 0.15 + 0.15 + 0.05 = 0.755
            return {"status": "ok"}

    monkeypatch.setattr(loop, "_get_governor", lambda: _FakeGovernor())
    monkeypatch.setattr(loop, "_get_recent_feedback", lambda action_type: None)

    candidate = Candidate(action_type=action_type, params=dict(params), goal_ids=[goal_id])

    asyncio.run(loop._act_on(candidate))

    expected_reward = 0.7 * 0.40 + 0.5 * 0.25 + 1.0 * 0.15 + 1.0 * 0.15 + 1.0 * 0.05

    # Round trip: the SAME decision's canonical identity, computed fresh via
    # the reader's own path (DecisionEngine._make_situation_hash ->
    # PolicyMemory.get_score()), must retrieve the reward the writer just
    # persisted -- not a second, independently-recomputed hash asserted
    # separately, but the actual reader call chain.
    engine = DecisionEngine()
    reader_candidate = Candidate(action_type=action_type, params=dict(params), goal_ids=[goal_id])
    situation_hash = engine._make_situation_hash(reader_candidate)
    retrieved_score = engine._get_policy().get_score(action_type, situation_hash)

    assert abs(retrieved_score - expected_reward) < 1e-9, (
        f"reader must retrieve the exact reward the 5-factor writer persisted: "
        f"expected {expected_reward}, got {retrieved_score}"
    )


def test_historical_pre_fix_row_untouched_by_schema_or_key_changes():
    """Test 6: an existing historical row (pre-fix format: an un-prefixed,
    sorted()-repr-style situation_hash with no "v2:" prefix) remains present
    and byte-unchanged in the table after this task's changes ship. A
    read-only assertion against a fixture representing old data -- this test
    inserts its OWN uuid-unique fixture row shaped like a historical row (it
    never touches the real ~29,000-sample analyze_progress bucket), then
    proves no migration/backfill code path in this change set alters it.
    """
    import hashlib
    from core.memory.episodic import get_temp_cursor
    from core.memory.policy import PolicyMemory

    fixture_action_type = f"test_historical_fixture_{uuid.uuid4().hex[:8]}"
    # Old (pre-fix) reader formula: f"{action_type}:{sorted(params.items())}"
    old_style_hash = hashlib.sha256(
        f"{fixture_action_type}:{sorted({'goal_id': 'g_old'}.items())}".encode()
    ).hexdigest()[:12]
    fixture_avg_reward = 0.6321
    fixture_sample_count = 29164  # deliberately reminiscent of the real historical count

    with get_temp_cursor() as cursor:
        cursor.execute(
            "INSERT INTO policy_memory "
            "(action_type, situation_hash, avg_reward, sample_count, last_updated) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            (fixture_action_type, old_style_hash, fixture_avg_reward, fixture_sample_count),
        )

    def _read_fixture():
        with get_temp_cursor() as cursor:
            return cursor.execute(
                "SELECT action_type, situation_hash, avg_reward, sample_count, veto_count "
                "FROM policy_memory WHERE action_type=? AND situation_hash=?",
                (fixture_action_type, old_style_hash),
            ).fetchone()

    before = _read_fixture()
    assert before is not None, "fixture row must exist after insert"
    assert before[2] == fixture_avg_reward
    assert before[3] == fixture_sample_count

    # Exercise the code this task changed: schema init (adds veto_count via
    # guarded ALTER TABLE, idempotent, must not touch existing rows) and a
    # handful of make_situation_hash()/get_score() calls with unrelated keys,
    # simulating ordinary post-deploy activity.
    from core.memory.episodic import _create_tables, get_db_connection
    _create_tables(get_db_connection())
    pm = PolicyMemory()
    pm.get_score(f"unrelated_{uuid.uuid4().hex[:8]}", "deadbeef0000")
    pm.make_situation_hash(f"unrelated_{uuid.uuid4().hex[:8]}", {"x": 1})

    after = _read_fixture()
    assert after is not None, "fixture row must still exist -- no migration/deletion"
    assert after[0] == fixture_action_type
    assert after[1] == old_style_hash, "situation_hash must not be rewritten/re-keyed"
    assert after[2] == fixture_avg_reward, "avg_reward must be byte-unchanged"
    assert after[3] == fixture_sample_count, "sample_count must be byte-unchanged"
    # veto_count is a NEW column: an old row gets the column's DEFAULT (0) or
    # SQL NULL depending on how ALTER TABLE ... ADD COLUMN ... DEFAULT 0
    # backfills existing rows (SQLite backfills the declared default for
    # existing rows) -- either way this is the schema addition applying
    # uniformly, not a per-row migration touching this fixture's own data.
    assert after[4] in (0, None)

    # This old-format hash is a completely different string from the v2:
    # canonical hash for the "same" logical (action_type, params) -- proving
    # old rows are simply never looked up by new code, not migrated.
    v2_hash = PolicyMemory.make_situation_hash(fixture_action_type, {"goal_id": "g_old"})
    assert v2_hash != old_style_hash
    assert v2_hash.startswith("v2:")


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
