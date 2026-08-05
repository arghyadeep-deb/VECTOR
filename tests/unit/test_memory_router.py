"""MemoryRouter (core.memory.router) — classify-then-dispatch front end for
UnifiedMemory. Verifies every deterministic write/read path calls the REAL
store methods with the REAL signatures (this file exists because the first
draft of router.py called four methods that don't exist:
CounterfactualMemory.store(), SemanticMemory.remember()/.recall(), and
KnowledgeGraph.query_graph() — all caught by reading the actual store source
before trusting the router, not by running it and hoping).

The LLM-fallback path (Ollama, allow_cloud=False) is monkeypatched out here
since this suite runs without a local Ollama server; MemoryRouter's contract
for that path — "any LLM failure defaults to episodic, never crashes, never
drops the write" — is what's actually under test, not Ollama itself.
"""
from __future__ import annotations

import pytest

from core.memory import router as router_mod
from core.memory.router import (
    CAT_COUNTERFACTUAL,
    CAT_ENTITY,
    CAT_EPISODIC,
    CAT_POLICY,
    CAT_REASONING,
    CAT_SEMANTIC,
    MemoryRouter,
)


@pytest.fixture()
def isolated_router(tmp_path, monkeypatch):
    """Fresh MemoryRouter over an isolated episodic/semantic/policy DB, and an
    isolated knowledge-graph / counterfactual DB (both live at fixed
    Path.home()-relative paths, so point HOME at a scratch dir instead)."""
    monkeypatch.setenv("VECTOR_DB_PATH", str(tmp_path / "router_test.db"))
    monkeypatch.setenv("VECTOR_DB_KEY", "test_key_router")
    monkeypatch.setenv("VECTOR_TEST_DATA_DIR", str(tmp_path / "data"))  # isolates counterfactual.db
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))  # Windows equivalent
    # knowledge_graph.py's _KG_DB is a module-level constant computed once at
    # first import (Path.home()/".vector_ca"/...), so it is NOT re-isolated
    # per test the way episodic/semantic/counterfactual are — every test in
    # this file shares one knowledge-graph DB. Assertions below use distinct
    # entity names so this doesn't cause cross-test false positives.

    import core.memory.episodic as ep
    import core.memory.unified as unified
    ep.close_db_connection()
    unified._INSTANCE = None
    router_mod._INSTANCE = None

    r = MemoryRouter()
    # Safety net: no Ollama server is reachable in this sandbox, and
    # _llm_classify() otherwise blocks for a long time on the failed
    # connection attempt rather than failing fast. Default it to "unavailable"
    # (None) for every test; tests that specifically exercise the
    # llm-classification-honored path monkeypatch _llm_classify_write /
    # _llm_classify_read directly, which takes precedence over this.
    monkeypatch.setattr(r, "_llm_classify", lambda text, instruction: None)
    yield r
    ep.close_db_connection()
    unified._INSTANCE = None
    router_mod._INSTANCE = None


# ── WRITE: deterministic classification ─────────────────────────────────────

def test_action_reward_routes_to_policy(isolated_router):
    r = isolated_router
    result = r.route_write(
        "Executed check_weather with reward",
        metadata={"action_type": "check_weather", "reward": 0.9},
    )
    assert result.category == CAT_POLICY
    assert result.method == "deterministic"


def test_rejection_language_routes_to_counterfactual(isolated_router):
    r = isolated_router
    result = r.route_write("Decided not to push the untested branch to prod")
    assert result.category == CAT_COUNTERFACTUAL
    assert isinstance(result.store_result, str) and result.store_result  # decision_id (uuid)


def test_explicit_rejected_metadata_routes_to_counterfactual(isolated_router):
    r = isolated_router
    result = r.route_write(
        "Skip the migration this week",
        metadata={"rejected": True, "reason": "too risky before the demo"},
    )
    assert result.category == CAT_COUNTERFACTUAL


def test_entity_shaped_statement_routes_to_entity(isolated_router):
    r = isolated_router
    result = r.route_write("Arghyadeep is the owner of VECTOR")
    assert result.category == CAT_ENTITY
    assert result.store_result == "Arghyadeep"


def test_fact_statement_routes_to_semantic(isolated_router):
    r = isolated_router
    result = r.route_write("Remember that I prefer dark mode in all apps")
    assert result.category == CAT_SEMANTIC
    assert isinstance(result.store_result, str)  # the derived key
    # actually persisted, not just classified
    assert r._mem.semantic.get(result.store_result) is not None


def test_reasoning_chain_shape_routes_to_reasoning(isolated_router):
    r = isolated_router
    result = r.route_write(
        "thought chain",
        metadata={
            "chain": True,
            "situation": "debugging a crash",
            "steps": ["a", "b"],
            "action": "restart",
            "outcome": "fixed",
            "reward": 0.8,
        },
    )
    assert result.category == CAT_REASONING
    assert isinstance(result.store_result, str)  # chain_id


def test_metadata_is_authoritative_over_text_shape(isolated_router):
    """A caller-supplied structural hint wins even if the free text alone
    would have matched a different deterministic rule."""
    r = isolated_router
    result = r.route_write(
        "Arghyadeep is happy with the results",  # looks entity-shaped
        metadata={"action_type": "ship_release", "reward": 1.0},  # but this is ground truth
    )
    assert result.category == CAT_POLICY


def test_ambiguous_text_with_llm_unavailable_falls_back_to_episodic(isolated_router, monkeypatch):
    """No deterministic rule fires, and the LLM classifier is unreachable
    (matches this suite's no-Ollama environment) -> must still store the
    write somewhere, never drop it silently."""
    r = isolated_router
    monkeypatch.setattr(r, "_llm_classify_write", lambda content: None)
    result = r.route_write("VECTOR API restarted cleanly at 3am", event_type="ops")
    assert result.category == CAT_EPISODIC
    assert result.store_result is not None


def test_llm_classification_result_is_honored(isolated_router, monkeypatch):
    """When the LLM fallback DOES return a confident category, the router
    dispatches to that category's writer, not episodic."""
    r = isolated_router
    monkeypatch.setattr(r, "_llm_classify_write", lambda content: CAT_SEMANTIC)
    result = r.route_write("some genuinely ambiguous free text with no shape")
    assert result.category == CAT_SEMANTIC
    assert result.method == "llm"


def test_empty_content_is_a_safe_noop(isolated_router):
    r = isolated_router
    result = r.route_write("   ")
    assert result.category == CAT_EPISODIC
    assert result.method == "fallback"


# ── READ: deterministic classification + real dispatch ─────────────────────

def test_entity_read_hits_knowledge_graph(isolated_router):
    r = isolated_router
    r.route_write("Arghyadeep is the owner of VECTOR")
    result = r.route_read("who is Arghyadeep")
    assert result.category == CAT_ENTITY
    assert result.store_result is not None
    assert result.store_result.total > 0


def test_reasoning_read_hits_reasoning_chains(isolated_router):
    r = isolated_router
    r.route_write(
        "thought chain",
        metadata={
            "chain": True,
            "situation": "debugging a crash",
            "steps": ["a", "b"],
            "action": "restart",
            "outcome": "fixed",
            "reward": 0.8,
        },
    )
    result = r.route_read("have i tried this before: debugging a crash")
    assert result.category == CAT_REASONING
    assert result.store_result  # non-empty list


def test_policy_read_extracts_snake_case_action_type(isolated_router):
    r = isolated_router
    r.route_write(
        "Executed check_weather with reward",
        metadata={"action_type": "check_weather", "reward": 0.9},
    )
    result = r.route_read("how good is check_weather usually")
    assert result.category == CAT_POLICY
    assert isinstance(result.store_result, float)


def test_semantic_read_finds_exact_key_match(isolated_router):
    r = isolated_router
    write_result = r.route_write("Remember that I prefer dark mode in all apps")
    key = write_result.store_result
    # A raw derived key ("fact_...") has no question-shaped wording, so the
    # text-based rules can't classify it -> forces the task_hint path instead
    # of the (real, unmocked-here) LLM fallback.
    result = r.route_read(key, task_hint="semantic")
    assert result.category == CAT_SEMANTIC
    assert result.store_result is not None


def test_read_falls_back_to_episodic_when_category_finds_nothing(isolated_router):
    r = isolated_router
    r._mem.episodic.store("note", "unique_router_fallback_needle plain episodic text")
    result = r.route_read("who is unique_router_fallback_needle")  # classifies as entity, KG has nothing
    assert result.category == CAT_EPISODIC
    assert result.method == "fallback"
    assert any("unique_router_fallback_needle" in row.get("content", "") for row in result.store_result)


def test_empty_query_is_a_safe_noop(isolated_router):
    r = isolated_router
    result = r.route_read("   ")
    assert result.store_result == []


def test_task_hint_overrides_text_based_classification(isolated_router):
    r = isolated_router
    result = r.route_read("this text has no obvious shape at all", task_hint="policy")
    assert result.category == CAT_POLICY


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
