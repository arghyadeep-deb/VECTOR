"""Ebbinghaus forgetting-curve decay (core.memory.decay) — replaces the
fixed-calendar-day forgetting cliff. Owner's framing (2026-07-29): "when
decay ≈ 0 we can evict that data — not based on a fixed N days."

    R(t) = e^(-t/S)   S grows on genuine reuse (reinforcement)

Covers: the pure formula, episodic_memory store/recall/prune end-to-end
(ephemeral vs bulk vs protected vs reinforced), and reasoning_chains
reinforcement via search_chains/inject_past_reasoning.
"""
from __future__ import annotations

import datetime

import pytest

from core.memory import decay


# ── Pure formula ─────────────────────────────────────────────────────────

def test_retention_at_zero_elapsed_is_full():
    assert decay.retention(0, 30.0) == 1.0
    assert decay.retention(-1, 30.0) == 1.0  # clock skew guard


def test_retention_decays_toward_zero():
    r1 = decay.retention(10, 30.0)
    r2 = decay.retention(60, 30.0)
    assert 0.0 < r2 < r1 < 1.0


def test_retention_invalid_stability_is_fully_decayed():
    assert decay.retention(5, 0) == 0.0
    assert decay.retention(5, -3) == 0.0


def test_should_evict_matches_threshold_crossing():
    # R(t=3S) ≈ 0.0498 < 0.05 threshold -> evict; just before, survives.
    S = 20.0
    assert decay.should_evict(3 * S, S) is True
    assert decay.should_evict(2 * S, S) is False


def test_reinforce_grows_stability_multiplicatively_and_caps():
    s = 5.0
    for _ in range(3):
        s = decay.reinforce(s)
    assert s == pytest.approx(5.0 * (decay.REINFORCE_FACTOR ** 3))
    assert decay.reinforce(10_000.0) == decay.MAX_STABILITY_DAYS


def test_reinforce_missing_stability_starts_from_default():
    assert decay.reinforce(None) == pytest.approx(decay.DEFAULT_STABILITY_DAYS * decay.REINFORCE_FACTOR)
    assert decay.reinforce(0) == pytest.approx(decay.DEFAULT_STABILITY_DAYS * decay.REINFORCE_FACTOR)


def test_reinforced_row_can_outlive_the_old_fixed_cutoff():
    """The whole point of switching off a fixed 90-day cliff: a row reinforced
    enough times can legitimately survive well past day 90, while an
    unreinforced one at the same age is long gone."""
    unreinforced_stability = 30.0  # never touched since creation
    assert decay.should_evict(150, unreinforced_stability) is True

    reinforced_stability = 30.0
    for _ in range(4):  # a handful of genuine recalls over its life
        reinforced_stability = decay.reinforce(reinforced_stability)
    assert decay.should_evict(150, reinforced_stability) is False


# ── Integration: episodic_memory store / recall / prune ────────────────────

@pytest.fixture()
def isolated_episodic(tmp_path, monkeypatch):
    """Fresh, isolated SQLite DB per test — never touches the real memory DB."""
    monkeypatch.setenv("VECTOR_DB_PATH", str(tmp_path / "decay_test.db"))
    monkeypatch.setenv("VECTOR_DB_KEY", "test_key_isolated")
    import core.memory.episodic as ep
    ep.close_db_connection()
    mem = ep.EpisodicMemory()
    yield mem, ep
    ep.close_db_connection()


def test_close_db_connection_resets_stale_db_key(monkeypatch):
    """Regression (root cause of the cross-test contamination this file used to
    trigger): _get_db_key() caches its result in module-global _DB_KEY and
    returns it early on every later call. close_db_connection() closed/cleared
    _db_connection and reset the circuit breaker, but did NOT reset _DB_KEY —
    so a test that monkeypatches VECTOR_DB_KEY for isolation, then closes the
    connection at teardown, left the STALE test key cached. The next
    get_db_connection() (e.g. from an unrelated, unisolated test running
    later in the same process) then opened the REAL production
    vector_memory.db keyed with the test's key and died with
    "hmac check failed" / "file is not a database".

    Asserts directly against episodic._DB_KEY (and via _get_db_key()) that
    close_db_connection() clears the cache, so a fresh get_db_connection()
    resolves the key from whatever VECTOR_DB_KEY is current at call time —
    not whatever it was the first time _get_db_key() ever ran in this
    process.
    """
    import core.memory.episodic as ep

    monkeypatch.setenv("VECTOR_DB_KEY", "first_test_key")
    ep._DB_KEY = None  # start from a clean slate regardless of prior test/import order
    assert ep._get_db_key() == "first_test_key"
    assert ep._DB_KEY == "first_test_key"

    ep.close_db_connection()
    assert ep._DB_KEY is None, "close_db_connection() must also clear the cached _DB_KEY"

    monkeypatch.setenv("VECTOR_DB_KEY", "second_test_key")
    assert ep._get_db_key() == "second_test_key", (
        "_get_db_key() returned a stale cached key instead of re-resolving "
        "from the current VECTOR_DB_KEY env var"
    )
    assert ep._DB_KEY == "second_test_key"

    # Leave the module in a clean state for whatever runs next in this process.
    ep.close_db_connection()


def _backdate(ep_module, event_id: str, days_ago: float, last_touch_days_ago: float | None = None) -> None:
    now = datetime.datetime.now(datetime.timezone.utc)
    ts = (now - datetime.timedelta(days=days_ago)).isoformat()
    lt = ts if last_touch_days_ago is None else (now - datetime.timedelta(days=last_touch_days_ago)).isoformat()
    with ep_module.get_temp_cursor() as cur:
        cur.execute(
            "UPDATE episodic_memory SET timestamp=?, last_touch=? WHERE id=?",
            (ts, lt, event_id),
        )


def _exists(ep_module, event_id: str) -> bool:
    with ep_module.get_temp_cursor() as cur:
        cur.execute("SELECT 1 FROM episodic_memory WHERE id=?", (event_id,))
        return cur.fetchone() is not None


def test_unreinforced_ephemeral_row_decays_and_gets_pruned(isolated_episodic):
    mem, ep = isolated_episodic
    eid = mem.store("observation", "raw sensor tick, never revisited")
    _backdate(ep, eid, days_ago=200)

    mem.prune_old_episodes(retention_days=90)
    assert not _exists(ep, eid)


def test_recent_bulk_row_survives_even_past_old_ephemeral_cutoff(isolated_episodic):
    mem, ep = isolated_episodic
    eid = mem.store("task", "a normal task event")
    _backdate(ep, eid, days_ago=25)  # would have survived the old 90d cliff too

    mem.prune_old_episodes(retention_days=90)
    assert _exists(ep, eid)


def test_old_but_reinforced_row_outlives_original_creation_date(isolated_episodic):
    mem, ep = isolated_episodic
    eid = mem.store("task", "a fact VECTOR keeps finding useful")
    # Created 200 days ago, but recalled recently and built up stability —
    # exactly the scenario a fixed-day cliff can't represent.
    _backdate(ep, eid, days_ago=200, last_touch_days_ago=5)
    with ep.get_temp_cursor() as cur:
        cur.execute("UPDATE episodic_memory SET stability_days=? WHERE id=?", (60.0, eid))

    mem.prune_old_episodes(retention_days=90)
    assert _exists(ep, eid), "a reinforced memory must be able to outlive a fixed 90-day cutoff"


def test_protected_event_type_survives_regardless_of_decay(isolated_episodic):
    mem, ep = isolated_episodic
    eid = mem.store("council", "important verdict")
    _backdate(ep, eid, days_ago=400)  # decayed to ~0 under any stability

    mem.prune_old_episodes(retention_days=90)
    assert _exists(ep, eid), "protected event types must never be auto-evicted"


def test_recall_reinforces_stability_and_resets_last_touch(isolated_episodic):
    mem, ep = isolated_episodic
    eid = mem.store("task", "unique_needle_for_reinforcement_test findable text")

    with ep.get_temp_cursor() as cur:
        cur.execute("SELECT stability_days FROM episodic_memory WHERE id=?", (eid,))
        before = cur.fetchone()[0]

    results = mem.recall("unique_needle_for_reinforcement_test")
    assert any(r["id"] == eid for r in results)

    with ep.get_temp_cursor() as cur:
        cur.execute("SELECT stability_days FROM episodic_memory WHERE id=?", (eid,))
        after = cur.fetchone()[0]

    assert after > before


# ── Integration: reasoning_chains reinforcement ─────────────────────────────

def test_search_chains_reinforces_reused_chains(isolated_episodic, monkeypatch):
    _mem, ep = isolated_episodic
    from core.memory.reasoning_memory import ReasoningMemory
    rm = ReasoningMemory()

    chain_id = rm.store_chain(
        situation="unique_reasoning_needle situation",
        goal_ids=[],
        steps=["step1", "step2"],
        action="do_thing",
        outcome="worked",
        reward=0.8,
    )

    conn = rm._get_mem().conn
    before = conn.execute(
        "SELECT stability_days FROM reasoning_chains WHERE chain_id=?", (chain_id,)
    ).fetchone()[0]

    chains = rm.search_chains("unique_reasoning_needle")
    assert any(c["id"] == chain_id for c in chains)

    after = conn.execute(
        "SELECT stability_days FROM reasoning_chains WHERE chain_id=?", (chain_id,)
    ).fetchone()[0]

    assert after > before
