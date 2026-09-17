"""OWNER ROUTING CLOSURE — F1 (systematic district-name hallucination) tests.

Background (VECTOR_TECHNICAL_KNOWLEDGE/RGC2R_RGD2_COMBINED_REALITY_GATE_
REPORT.md Sections 9/10/12/14/36): 3 of 4 fresh owner probes produced a
high-confidence, semantically correct `task_type` but a `district` string
that does not exist in `DISTRICT_TASK_MAP` — `classify_chat_intent()`
rejects on `district not in districts` BEFORE ever reaching the existing
correction mechanisms (`_authoritative_district_from_text`, the
`DISTRICT_TASK_MAP[task_type] != district` exact-key correction), which
live further down the function and can never fire once the reject has
already returned. The fix reorders these existing, already-proven
mechanisms to run before the district-validity check (plus one new,
deliberately conservative generalization — see test 3/4/6 below), rather
than inventing hard-coded aliases for the three specific fabricated
strings observed (`knowledge_engineering`, `communication`,
`project_management` — whack-a-mole, explicitly forbidden by the mission).

Per .claude/rules/testing.md, only the LLM-call boundary
(`provider_client.get_client`) and `IntentMatcher.match` (Stage 2, not
under test here) are mocked — everything else (DISTRICT_TASK_MAP,
_authoritative_district_from_text, the new canonicalization helper) runs
as real production code.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.city import governor
from core.city.intent_matcher import IntentMatcher


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


async def _classify(text: str, llm_json: str) -> dict:
    with patch("core.inference.provider_client.get_client", return_value=_mock_client(llm_json)):
        return await governor.classify_chat_intent(text)


# ── 1. Valid/canonical task_type + wholly invented district ────────────────

@pytest.mark.asyncio
async def test_exact_task_type_survives_invented_district():
    """C1-shaped: task_type is an exact DISTRICT_TASK_MAP key ('search_web'
    -> research), but the LLM invented a district string that matches
    nothing. The exact-key mapping is authoritative and must win over the
    LLM's invented district, exactly as it already does for a merely-wrong
    (but syntactically valid) district."""
    text = "please look into recent developments in this subject area"
    llm_json = '{"is_action": true, "task_type": "search_web", "district": "knowledge_engineering", "confidence": 0.95}'
    result = await _classify(text, llm_json)
    assert result.get("type") == "search_web"
    assert result.get("district") == "research", (
        "an exact, unambiguous task_type->district mapping must be trusted "
        "over an invented district string, not rejected outright"
    )


# ── 2. Singular/plural near-miss district, resolved via exact task_type ────

@pytest.mark.asyncio
async def test_near_miss_district_corrected_via_exact_task_type():
    """C2-shaped: task_type 'message' is an exact key -> communications, but
    the LLM said district='communication' (singular, invalid)."""
    text = "could you put together a short note about this for me"
    llm_json = '{"is_action": true, "task_type": "message", "district": "communication", "confidence": 1.0}'
    result = await _classify(text, llm_json)
    assert result.get("type") == "message"
    assert result.get("district") == "communications"


# ── 3. Noncanonical task_type, resolved via literal query-text word ────────

@pytest.mark.asyncio
async def test_invented_task_type_resolved_via_query_text():
    """C4-shaped: task_type is LLM-invented (not an exact key), district is
    invented too, but the owner's own text contains a literal, unambiguous
    DISTRICT_TASK_MAP word ('project' -> projects) — the existing
    _authoritative_district_from_text() mechanism should resolve this
    without needing the new task_type-only fallback at all."""
    text = "has anything changed in the project lately worth flagging"
    llm_json = '{"is_action": true, "task_type": "project_status_scan", "district": "project_management", "confidence": 0.95}'
    result = await _classify(text, llm_json)
    assert result.get("district") == "projects"


# ── 4. Noncanonical task_type, resolved via new global word-overlap ────────

@pytest.mark.asyncio
async def test_invented_task_type_resolved_via_task_type_word_overlap():
    """No exact task_type key, no literal query-text word match either —
    only the invented task_type's own words give a signal. 'codebase' is a
    5+-char word appearing ONLY in coding-district keys (index_codebase,
    codebase_health) anywhere in DISTRICT_TASK_MAP, so this should resolve
    to district=coding via the new, deliberately narrow fallback."""
    text = "has anything shifted lately that's worth a look"
    llm_json = '{"is_action": true, "task_type": "codebase_change_scan", "district": "dev_ops_tracking", "confidence": 0.9}'
    result = await _classify(text, llm_json)
    assert result.get("district") == "coding"


# ── 5. Ambiguous cross-district overlap — must fail closed, not guess ──────

@pytest.mark.asyncio
async def test_ambiguous_task_type_overlap_fails_closed():
    """'status' overlaps BOTH git_status (coding) and system_status (ops) —
    a genuine tie across two unrelated districts. The repair must not guess
    between them; it must fail closed to answer_question, exactly like an
    unresolvable invalid district always has."""
    text = "wanted to check in on where things stand right now"
    llm_json = '{"is_action": true, "task_type": "status_check_report", "district": "reporting_hub", "confidence": 0.9}'
    result = await _classify(text, llm_json)
    assert result.get("type") == "answer_question", (
        "a genuinely ambiguous cross-district word overlap must fail closed, "
        "not force a guess between two unrelated districts"
    )


# ── 6. Wholly unrelated invented task_type — must remain UNKNOWN/blocked ───

@pytest.mark.asyncio
async def test_unrelated_invented_task_stays_blocked():
    """No exact key, no query-text word match, and the invented task_type's
    words are either too short/generic to count (<5 chars, filtered) or
    don't overlap anything real — must remain answer_question, not be
    routed anywhere. This is also the F1 security invariant: a
    dangerous-sounding invented task_type ('wipe_all_user_data_now') must
    NEVER fuzzy-snap into an unrelated benign capability merely because one
    short, generic word happens to overlap something real (e.g. 'data' in
    'data_viz')."""
    text = "not sure if there's anything to flag right now"
    llm_json = '{"is_action": true, "task_type": "wipe_all_user_data_now", "district": "chaos_zone", "confidence": 0.9}'
    result = await _classify(text, llm_json)
    assert result.get("type") == "answer_question", (
        "an invented task_type with no strong, unambiguous signal must fail "
        "closed rather than fuzzy-snap into an unrelated real capability"
    )


# ── 7. Security invariant: RED-tier task_type keeps its identity ───────────

@pytest.mark.asyncio
async def test_red_tier_task_type_preserved_through_district_correction():
    """'send_email' is a RED-tier task_type (_COUNCIL_TASK_TYPES) that is
    also an exact DISTRICT_TASK_MAP key -> communications. Canonicalizing
    an invented district must NOT alter task_type — PermissionGateway's
    downstream RED/YELLOW/GREEN classification depends on task_type staying
    exactly 'send_email', never silently substituted for a differently-
    tiered action.

    Deliberately avoids any literal DISTRICT_TASK_MAP word in the query
    text itself (e.g. 'message'), so this isolates the exact-task_type-key
    correction path (branch 2) from _authoritative_district_from_text()'s
    own, pre-existing, unmodified text-word mechanism (branch 1, which
    would otherwise fire first and rewrite task_type too — that is correct,
    already-established behavior, just not what this specific test targets)."""
    text = "could you get that out to them fairly soon please"
    llm_json = '{"is_action": true, "task_type": "send_email", "district": "email_ops", "confidence": 0.95}'
    result = await _classify(text, llm_json)
    assert result.get("type") == "send_email", (
        "district canonicalization must never change a RED-tier task_type's "
        "identity"
    )
    assert result.get("district") == "communications"


# ── 8. Regression: already-valid district still works exactly as before ───

@pytest.mark.asyncio
async def test_already_valid_district_unaffected():
    """Baseline regression: when the LLM already returns a syntactically
    valid district, behavior must be byte-for-byte identical to before this
    repair (task_type snapping still applies, nothing new interferes)."""
    text = "could you dig up some recent papers on this"
    llm_json = '{"is_action": true, "task_type": "search_arxiv", "district": "research", "confidence": 0.95}'
    result = await _classify(text, llm_json)
    assert result.get("type") == "search_arxiv"
    assert result.get("district") == "research"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
