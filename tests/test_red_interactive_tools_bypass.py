"""
Regression tests for the 2026-08-04 RED_INTERACTIVE_TOOLS hardening.

Context (audit finding): `run_shell_command`, `gui_task`, `pc_click`, etc.
used to sit in the YELLOW tier. With `VECTOR_YELLOW_AUTO_CONFIRM=1` (the
owner's live .env) those auto-executed after a ~10s window with NO owner
confirmation — a direct prompt-injection -> unattended-execution path, since
the action_type is invented by an LLM (`classify_chat_intent()`) from text
that can originate in an email/web page/message.

The hardening moved them to RED, with a deliberate owner-initiated bypass so
the owner's own typed/spoken commands stay frictionless.

The review of that hardening found a second, subtler hole: the bypass keys
off `Action.proposed_by`, and three routes populate that field straight from
a client-supplied request body (`executor.py`, `missions.py`, `tasks.py`).
So `POST /execute/run {"action_type":"run_shell_command",
"proposed_by":"api_command"}` would have inherited the owner bypass and run
arbitrary shell with no approval. Before the hardening RED had no bypass at
all, so spoofing that string bought nothing — the hardening is what made it
exploitable. `sanitize_proposed_by()` closes it at every client ingress.

These tests lock in BOTH halves so neither can silently regress.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.loop.permission_gateway import (  # noqa: E402
    OWNER_APPROVAL_ONLY,
    RED,
    RED_INTERACTIVE_TOOLS,
    YELLOW,
    sanitize_proposed_by,
)


# ---------------------------------------------------------------------------
# Half 1 — the dangerous capabilities really are RED, not YELLOW
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("action_type", sorted(RED_INTERACTIVE_TOOLS))
def test_interactive_tool_is_red_not_yellow(action_type):
    """Every RED_INTERACTIVE_TOOLS entry must be RED and must NOT be YELLOW.

    If any of these leaks back into YELLOW it becomes auto-confirmable again
    under VECTOR_YELLOW_AUTO_CONFIRM=1, silently reopening the original hole.
    """
    assert action_type in RED, f"{action_type} must be in the RED tier"
    assert action_type not in YELLOW, (
        f"{action_type} is back in YELLOW — it would auto-execute without "
        f"owner confirmation when VECTOR_YELLOW_AUTO_CONFIRM=1"
    )


def test_shell_execution_is_red():
    """The single highest-risk capability, called out explicitly."""
    assert "run_shell_command" in RED
    assert "run_shell_command" not in YELLOW


def test_interactive_tools_do_not_weaken_owner_approval_only():
    """Money / deploy / publish actions must never gain the owner bypass.

    OWNER_APPROVAL_ONLY requires a real phone tap EVEN for owner-typed
    commands. RED_INTERACTIVE_TOOLS grants a bypass. The two sets must stay
    disjoint or the bypass would silently extend to real-money actions.
    """
    assert RED_INTERACTIVE_TOOLS & OWNER_APPROVAL_ONLY == set()


# ---------------------------------------------------------------------------
# Half 2 — the owner-trust marker cannot be forged from client input
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("claimed", ["api_command", "voice", "API_COMMAND", " api_command "])
def test_client_cannot_claim_owner_trust_marker(claimed):
    """A client-supplied proposed_by must never survive as a trust marker.

    This is the exploit that review caught: without this, POST /execute/run
    with {"proposed_by": "api_command"} bypasses RED owner approval entirely.
    Case/whitespace variants must be neutralised too.
    """
    out = sanitize_proposed_by(claimed)
    assert out.strip().lower() not in {"api_command", "voice"}
    assert out.startswith("client_claimed_")


@pytest.mark.parametrize("legit", ["api.executor", "api.missions", "autonomous_loop", "skill"])
def test_legitimate_proposed_by_passes_through_unchanged(legit):
    """The guard must not disturb normal, non-reserved values."""
    assert sanitize_proposed_by(legit) == legit


def test_empty_proposed_by_falls_back_safely():
    assert sanitize_proposed_by("") == "untrusted_client"
    assert sanitize_proposed_by("", fallback="api.executor") == "api.executor"


def test_sanitized_marker_would_not_match_bypass_condition():
    """End-to-end intent: the sanitized value fails the gateway's bypass check.

    The RED branch bypasses approval only when
    `action.proposed_by in ("api_command", "voice")`. Assert the sanitized
    output cannot satisfy that, for the highest-risk action type.
    """
    forged = sanitize_proposed_by("api_command")
    assert "run_shell_command" in RED_INTERACTIVE_TOOLS
    assert forged not in ("api_command", "voice")
