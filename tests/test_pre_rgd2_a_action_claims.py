"""PRE-RG-D2 FINAL CLOSURE — Target A (conversational false action claims).

Background (V1_TRUST_ACTION_IDENTITY_PERMISSION_CLOSURE_REPORT.md §14 #1,
frozen live matrix): with no action routed or executed, the conversational
reply nevertheless told the owner that VECTOR would act or had acted —
RY5: "I'll ping you in **60 seconds** to remind you to stretch" (no timer
exists on that path); UA2: an invented "**Action Taken:** Revenue check…"
block. `defabricate_llm_answer()` only strips a narrow set of past-tense
completion verbs (and only when the owner's text hints at an action), so
future commitments, progressive claims and "Action Taken" narration passed.

Invariant proven here: VECTOR must not tell the owner it did / is doing /
will do something unless authoritative execution/scheduling evidence exists.
The LLM's own statement is not evidence. The check is
`remove_unsupported_action_claims(response, action_evidence)`: the evidence
list is the authoritative command trace (empty on a pure-text reply path,
where nothing can have run). Advice/hypothetical/ordinary language is
preserved.

Real production code throughout; the LLM is the only mocked boundary.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.city.governor import Governor


def _strip(text, evidence=None):
    from core.security.anti_fabrication import remove_unsupported_action_claims
    return remove_unsupported_action_claims(text, evidence)


# ── 1. Future reminder promise with no scheduled action ────────────────────

def test_reminder_promise_without_scheduled_action_is_removed():
    out = _strip("Understood. I'll ping you in 60 seconds to remind you to stretch.")
    assert "ping you" not in out and "60 seconds" not in out, out
    assert "haven't scheduled" in out or "didn't schedule" in out or "not scheduled" in out.lower(), out


# ── 2. "Action Taken" narration with no action ─────────────────────────────

def test_action_taken_block_is_rejected():
    fabricated = (
        "**Action Taken:** - **Revenue check:** Confirmed the graduate product launch "
        "is Wave 1 focus. - **No new product starts** pending the graduation gate. "
        "**Next Steps:** - If you'd like, I can go deeper."
    )
    out = _strip(fabricated)
    assert "Action Taken" not in out and "Confirmed the graduate product" not in out, out
    assert "didn't take any action" in out or "haven't taken any action" in out, out


# ── 3. Past completion claim, no execution ─────────────────────────────────

def test_sent_email_claim_without_execution_is_blocked():
    out = _strip("Sure. I've sent the email to the team.")
    assert "sent the email" not in out, out


# ── 4. Future send commitment, no scheduled/execution state ────────────────

def test_future_send_commitment_without_state_is_blocked():
    out = _strip("I'll send it shortly.")
    assert "send it shortly" not in out, out


# ── 5. Progressive claim ───────────────────────────────────────────────────

def test_progressive_deployment_claim_without_state_is_blocked():
    out = _strip("The deployment is running and should finish in a few minutes.")
    assert "deployment is running" not in out, out


# ── 6. Real successful execution: truthful completion preserved ───────────

def test_completion_claim_backed_by_real_execution_is_preserved():
    evidence = [{"action_type": "send_email", "status": "ok"}]
    text = "I've sent the email to the team."
    assert _strip(text, evidence) == text


def test_completion_claim_is_not_backed_by_an_unrelated_execution():
    evidence = [{"action_type": "set_reminder", "status": "ok", "scheduled": True}]
    out = _strip("I've sent the email to the team.", evidence)
    assert "sent the email" not in out, "evidence for a different action must not license the claim"


def test_failed_or_not_run_execution_does_not_license_a_completion_claim():
    for status in ("not_implemented", "rejected", "error"):
        out = _strip("I've sent the email to the team.", [{"action_type": "send_email", "status": status}])
        assert "sent the email" not in out, status


# ── 7. Real scheduled action: truthful future commitment preserved ─────────

def test_future_commitment_backed_by_real_schedule_is_preserved():
    evidence = [{"action_type": "set_reminder", "status": "ok", "scheduled": True}]
    text = "I'll ping you in 60 seconds to remind you to stretch."
    assert _strip(text, evidence) == text


def test_future_commitment_needs_scheduling_state_not_just_execution():
    evidence = [{"action_type": "send_email", "status": "ok"}]  # executed, not scheduled
    out = _strip("I'll send the follow-up email tomorrow morning.", evidence)
    assert "tomorrow morning" not in out


# ── 8. Hypothetical / advice language preserved ────────────────────────────

@pytest.mark.parametrize("text", [
    "You could set a reminder for that.",
    "One option would be to schedule it for tomorrow.",
    "If you want, VECTOR can set a reminder for you.",
    "I can set a reminder if you'd like.",
    "I can't send emails from this reply, but here is a draft you could send.",
    "I didn't schedule anything — this is only a text reply.",
])
def test_advice_and_hypothetical_language_is_preserved(text):
    assert _strip(text) == text


# ── 9. Ordinary conversation preserved ─────────────────────────────────────

@pytest.mark.parametrize("text", [
    "A process is an independent program in execution, while a thread is a lightweight unit within it.",
    "I'll explain the difference in two steps.",
    "Let me set the scene: threads share memory, processes do not.",
    "Plants convert light into chemical energy through photosynthesis.",
    "The email is sent over SMTP, then routed between servers.",
    "Kubernetes schedules pods onto nodes using a scoring algorithm.",
])
def test_ordinary_conversation_is_preserved(text):
    assert _strip(text) == text


# ── Wiring: both real conversational paths apply the check ────────────────

class _R:
    def __init__(self, content):
        self.content = content


@pytest.mark.asyncio
async def test_command_conversational_path_removes_false_promise():
    from core.api.routers import commands as commands_router
    fake = AsyncMock()
    fake.chat = AsyncMock(return_value=_R("Understood. I'll ping you in 60 seconds to remind you to stretch."))

    class _PC:
        async def chat(self, *a, **k):
            return await fake.chat(*a, **k)

    with patch("core.inference.provider_client.ProviderClient", _PC):
        out = await commands_router._llm_answer("Ping me in a minute so I remember to stretch.", "CTX")
    assert "ping you" not in out and "60 seconds" not in out, out


@pytest.mark.asyncio
async def test_ws_conversational_path_removes_false_promise():
    chat = AsyncMock(return_value=_R("Done — I've scheduled that for tomorrow at 9am."))
    fake_client = AsyncMock()
    fake_client.chat = chat
    with patch("core.inference.provider_client.get_client", return_value=fake_client):
        result = await Governor()._answer_conversationally(
            {"type": "answer_question", "params": {"query": "put the standup on my calendar for tomorrow"}}
        )
    assert "scheduled that" not in (result.get("response") or ""), result
