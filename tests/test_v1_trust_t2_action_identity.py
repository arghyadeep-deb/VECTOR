"""V1 TRUST CLOSURE — T2 (action/task identity preservation) tests.

Background (VECTOR_TECHNICAL_KNOWLEDGE/OWNER_ROUTING_CLOSURE_REPORT.md
Sections 17/26/28): in 4 of 5 live RED-shaped owner probes,
`classify_chat_intent()`'s correction mechanisms replaced the LLM's
correctly identified, exact, known task_type with a different task_type
purely because a word in the owner's sentence collided with another VECTOR
capability's name:

    push_github        -> code
    send_email         -> email
    deploy_production  -> deploy
    execute_code       -> script     (and the unrelated GREEN `script` ran)

`_authoritative_district_from_text()` (text-word -> DISTRICT_TASK_MAP key)
always returns a NEW task_type as well as a district, and
`_snap_to_known_task_type()` snaps within the district by word overlap;
neither had any notion that an exact known action identity must not be
rewritten. PermissionGateway then authorized the WRONG action identity.

Invariant proven here: routing may clarify district and may canonicalize a
genuinely unknown/invented label, but it must never rewrite an exact known
action identity (DISTRICT_TASK_MAP keys, the permission vocabulary, the
council/RED vocabulary), and must never substitute a lower-tier registered
action for an invented label that itself carries RED/FORBIDDEN-vocabulary
words.

Per .claude/rules/testing.md: only the LLM boundary
(`provider_client.get_client`), the embedding matcher (Stage 2, not under
test), and the RED tier's council-LLM / phone-notification / owner-wait
boundaries are mocked. DecisionEngine, PermissionGateway tier logic and
`command_endpoint` run as real production code.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.api.routers import commands as commands_router
from core.api.schemas import CommandRequest
from core.city import governor
from core.city.intent_matcher import IntentMatcher
from core.loop.decision_engine import DecisionEngine
from core.loop.permission_gateway import PermissionGateway


@pytest.fixture(autouse=True)
def _no_embedding_match():
    with patch.object(IntentMatcher, "match", new=AsyncMock(return_value=None)):
        yield


class _FakeCompletionResult:
    def __init__(self, content: str):
        self.content = content


def _mock_client(content: str):
    async def _chat(*args, **kwargs):
        return _FakeCompletionResult(content)
    fake = AsyncMock()
    fake.chat = _chat
    return fake


def _llm(task_type: str, district: str, confidence: float = 1.0) -> str:
    return (
        '{"is_action": true, "task_type": "%s", "district": "%s", "confidence": %s}'
        % (task_type, district, confidence)
    )


async def _classify(text: str, llm_json: str) -> dict:
    with patch("core.inference.provider_client.get_client", return_value=_mock_client(llm_json)):
        return await governor.classify_chat_intent(text)


# ── 1-3 (+push_github). Exact RED identity survives incidental homonym ─────

@pytest.mark.asyncio
async def test_execute_code_identity_survives_incidental_script_word():
    """Live R05: raw execute_code + the owner's word 'script' became the
    unrelated GREEN content `script` action, which then actually ran."""
    result = await _classify(
        "Execute that script and run it now.", _llm("execute_code", "development")
    )
    assert result.get("type") == "execute_code", (
        f"exact RED identity must not be rewritten by an incidental text "
        f"word, got {result!r}"
    )


@pytest.mark.asyncio
async def test_send_email_identity_survives_incidental_email_word():
    result = await _classify(
        "Go ahead and send that email out now.", _llm("send_email", "communication")
    )
    assert result.get("type") == "send_email", result
    assert result.get("district") == "communications"


@pytest.mark.asyncio
async def test_deploy_production_identity_survives_deploy_word():
    """Live R04: `deploy_production` was SNAPPED to plain `deploy` within the
    ops district (word overlap) before reaching PermissionGateway."""
    result = await _classify(
        "Could you deploy the latest version to production?",
        _llm("deploy_production", "ops"),
    )
    assert result.get("type") == "deploy_production", result


@pytest.mark.asyncio
async def test_push_github_identity_survives_code_word():
    """Live R01: raw push_github + the owner's word 'code' became the
    generic `code` action."""
    result = await _classify(
        "Please push the current code changes.", _llm("push_github", "development")
    )
    assert result.get("type") == "push_github", result


# ── 4. Exact known action + INVALID district: district corrected from the
#      authoritative mapping, task_type untouched ─────────────────────────────

@pytest.mark.asyncio
async def test_exact_known_action_with_invalid_district_gets_mapped_district():
    result = await _classify(
        "how does the working tree look at the moment",
        _llm("git_status", "development", 0.9),
    )
    assert result.get("type") == "git_status"
    assert result.get("district") == "coding"


# ── 5. Exact known GREEN unchanged ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_exact_known_green_action_identity_unchanged():
    result = await _classify(
        "dig up some recent papers for me", _llm("search_arxiv", "research", 0.95)
    )
    assert result.get("type") == "search_arxiv"
    assert result.get("district") == "research"


# ── 6. Noncanonical invented label + one unambiguous real signal ───────────

@pytest.mark.asyncio
async def test_invented_noncanonical_label_may_still_canonicalize():
    """Existing, documented (KNOWN_ISSUES #10) behavior for a genuinely
    unknown/invented label must be preserved: `save_preference` is not a
    known action identity, the owner's literal word 'remember' is an
    unambiguous authoritative signal."""
    result = await _classify(
        "Remember that my favorite color is teal.",
        _llm("save_preference", "chief_of_staff", 0.9),
    )
    assert result.get("type") == "remember"
    assert result.get("district") == "memory_curator"


# ── 7. Noncanonical + ambiguous -> fail closed ─────────────────────────────

@pytest.mark.asyncio
async def test_ambiguous_invented_label_fails_closed():
    result = await _classify(
        "wanted to check in on where things stand right now",
        _llm("status_check_report", "reporting_hub", 0.9),
    )
    assert result.get("type") == "answer_question"


# ── 8. Dangerous invented label must NOT be fuzzily downgraded to GREEN ────

@pytest.mark.asyncio
async def test_dangerous_invented_label_not_downgraded_into_green_action():
    """`delete_everything_now` is not a known action identity, but its words
    ('delete') come from the RED vocabulary. The owner's sentence also
    contains the unrelated literal word 'script' (a GREEN content-district
    key). Pre-fix, text-authoritative correction rewrote the label into
    `script`, an executable GREEN action. It must instead keep its own
    (unknown -> PermissionGateway UNKNOWN -> blocked) identity."""
    result = await _classify(
        "Delete everything and then run that script.",
        _llm("delete_everything_now", "ops", 0.9),
    )
    assert result.get("type") != "script", (
        "a dangerous-vocabulary invented label must not be fuzzily rewritten "
        f"into a benign GREEN action, got {result!r}"
    )
    assert result.get("type") == "delete_everything_now"
    assert PermissionGateway()._classify(result["type"]) == "UNKNOWN", (
        "the retained invented identity must remain fail-closed at the gateway"
    )


# ── 9/10. End-to-end through the REAL /command endpoint ────────────────────

class _FakeContextEngine:
    def session_hydration_prompt(self, extra_context=None):
        return "TEST_HYDRATION_CONTEXT"


@pytest.fixture()
def isolated_episodic(tmp_path, monkeypatch):
    monkeypatch.setenv("VECTOR_DB_PATH", str(tmp_path / "v1_trust_t2_test.db"))
    monkeypatch.setenv("VECTOR_DB_KEY", "test_key_v1_trust_t2")
    import core.memory.episodic as ep
    ep.close_db_connection()
    mem = ep.EpisodicMemory()
    yield mem
    ep.close_db_connection()


async def _run_endpoint(text, llm_json, isolated_episodic):
    """Real classify_chat_intent + real DecisionEngine + real
    PermissionGateway tier logic; only the external boundaries are patched."""
    seen: dict = {"executed": [], "candidates": [], "winner": None}

    orig_eval = DecisionEngine.evaluate

    async def _spy_eval(self, candidates):
        seen["candidates"] = [c.action_type for c in candidates]
        decision = await orig_eval(self, candidates)
        seen["winner"] = decision.winner.action_type
        return decision

    async def _record_exec(self, action):
        seen["executed"].append(action.action_type)
        return {"status": "ok", "action": action.action_type}

    with patch("core.inference.provider_client.get_client", return_value=_mock_client(llm_json)), \
         patch.object(DecisionEngine, "evaluate", _spy_eval), \
         patch.object(PermissionGateway, "_execute_action", _record_exec), \
         patch.object(PermissionGateway, "_notify", new=AsyncMock()), \
         patch.object(PermissionGateway, "_handle_red_tier", new=AsyncMock(return_value="defer")), \
         patch.object(PermissionGateway, "_wait_for_confirmation", new=AsyncMock(return_value=False)):
        response = await commands_router.command_endpoint(
            body=CommandRequest(text=text),
            ctx_engine=_FakeContextEngine(),
            decision_engine=DecisionEngine(),
            perm_gateway=PermissionGateway(),
            episodic_mem=isolated_episodic,
        )
    return response, seen


@pytest.mark.asyncio
async def test_identity_chain_candidate_gateway_dispatch_are_the_same_action(isolated_episodic):
    """A legitimate executable case: the classifier's canonical identity is
    the Candidate's action_type, the DecisionEngine winner, what
    PermissionGateway authorizes, and what is dispatched for execution."""
    response, seen = await _run_endpoint(
        "Draft a short video script about our new landing page.",
        _llm("script", "content", 0.95),
        isolated_episodic,
    )
    assert seen["candidates"] == ["script"]
    assert seen["winner"] == "script"
    assert seen["executed"] == ["script"], (
        f"dispatched identity must equal the authorized/candidate identity, got {seen!r}"
    )
    assert PermissionGateway()._classify("script") == "GREEN"


@pytest.mark.asyncio
async def test_red_action_not_executable_through_canonicalization(isolated_episodic):
    """Live R05, end to end: execute_code is RED. It must reach the RED
    confirmation path as `execute_code` and must NOT be executed (nor
    replaced by an executable GREEN action) when nobody confirms."""
    response, seen = await _run_endpoint(
        "Execute that script and run it now.",
        _llm("execute_code", "development"),
        isolated_episodic,
    )
    assert seen["candidates"] == ["execute_code"], seen
    assert seen["winner"] == "execute_code", seen
    assert seen["executed"] == [], (
        f"an unconfirmed RED action (or a GREEN substitute for it) must never "
        f"execute, got {seen!r}"
    )
    assert response.action_taken is None
