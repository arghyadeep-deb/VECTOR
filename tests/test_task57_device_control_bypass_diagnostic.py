"""
Originally a DIAGNOSTIC-ONLY test proving VECTOR_TECHNICAL_KNOWLEDGE/57_
RESIDUAL_SIDE_EFFECT_SURFACE_VERIFICATION.md's Finding A (device-control
token-scope bypass) was real. **Finding A has since been remediated** — see
VECTOR_TECHNICAL_KNOWLEDGE/58A_PLAY_MUSIC_PERMISSION_ESCALATION_REMEDIATION.md.
This file's two behavioral tests were updated in place (per the guidance
their own original assertions carried: "if this assertion now fails,
re-verify whether Finding A is still open before assuming it was silently
fixed" — it was, deliberately, in Task 58A) to assert the FIXED behavior
instead of the vulnerable one, so this file continues to serve as a
regression guard rather than going permanently red.

Original finding (kept for history): PermissionGateway._execute_action()'s
"play_music" handler (GREEN tier, zero owner approval) read
action.params["app"] with NO validation and passed it to
PCController.play_music(app) -> PCController.launch_app(app), and
launch_app()'s own token check explicitly accepted a token minted for the
GREEN "play_music" action as authorization for launch_app — a RED-tier
capability. The fix: launch_app()'s token check now accepts ONLY
"launch_app"; play_music() normalizes `app` against a narrow
_MEDIA_PLAYER_ALLOWLIST and launches via a new, hard-restricted
_launch_media_player() helper instead of calling launch_app() at all.

CAUTION FOR FUTURE EDITS: an earlier revision of this file's second test
mocked PCController.launch_app() as its spy target. After the Task 58A fix,
play_music() no longer calls launch_app() at all, so that mock silently
stopped intercepting anything — the test still passed its assertions
trivially, but the real (unmocked) _launch_media_player() ran underneath
it and briefly launched a real Spotify process during a regression run
before this file was corrected. The tests below mock subprocess.Popen
itself (the actual OS-level primitive), not a named method, specifically
to survive future internal refactors without silently losing coverage.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_launch_app_is_red_tier_but_play_music_is_green():
    """Confirms the tier mismatch this finding depends on: play_music is
    GREEN (auto-executes, zero approval) while launch_app is RED (should
    require owner approval) — read directly from the real, current
    permission configuration, not hardcoded assumptions."""
    from core.config import CONFIG

    green = CONFIG["permission"]["green"]
    red = CONFIG["permission"]["red"]
    assert "play_music" in green, "play_music must be GREEN for this finding to apply"
    assert "launch_app" in red, "launch_app must be RED for the tier-skip to be a real escalation"


def test_launch_app_token_check_no_longer_accepts_play_music_token():
    """UPDATED for Task 58A: launch_app()'s token check must NOT accept a
    play_music-scoped token — read from the real source, not asserted from
    memory. Before Task 58A this asserted the opposite (that it DID accept
    it, proving the bypass); that assertion is now inverted because the
    bypass is fixed."""
    import inspect
    from core.control.pc_controller import PCController

    src = inspect.getsource(PCController.launch_app)
    assert '"launch_app", "play_music"' not in src and "'launch_app', 'play_music'" not in src, (
        "launch_app()'s token check accepts a play_music-scoped token again "
        "— Task 58A's fix (58A_PLAY_MUSIC_PERMISSION_ESCALATION_"
        "REMEDIATION.md) has regressed"
    )


async def test_play_music_action_handler_no_longer_forwards_arbitrary_app_unvalidated(monkeypatch):
    """UPDATED for Task 58A: drive the REAL PermissionGateway.execute()
    GREEN path for action_type="play_music" with an attacker-chosen `app`
    string end to end, and confirm it can NO LONGER reach subprocess.Popen
    with that string — the only OS-level primitive is mocked (not a named
    method), so this survives future internal refactors of exactly the
    kind that made the pre-58A version of this test start running real
    code underneath its own stale mock."""
    from core.loop.permission_gateway import PermissionGateway, Action
    from core.control import pc_controller as pcc_mod

    popen_calls: list = []

    def _fake_popen(cmd, **kwargs):
        popen_calls.append(cmd)
        from unittest.mock import MagicMock
        proc = MagicMock()
        proc.pid = 424242
        return proc

    monkeypatch.setattr(pcc_mod.subprocess, "Popen", _fake_popen)
    monkeypatch.setattr(pcc_mod.shutil, "which", lambda name: None)
    monkeypatch.setattr(pcc_mod.os, "startfile", lambda proto: None, raising=False)
    monkeypatch.setattr(pcc_mod.PCController, "media_key", lambda self, key: {"ok": True})

    gw = PermissionGateway()

    malicious_app = "cmd_would_go_here_if_real"
    action = Action(
        action_type="play_music",
        params={"app": malicious_app},
        proposed_by="autonomous_test",
    )

    result = await gw.execute(action)

    # Still auto-executes at GREEN, as designed — that part is unchanged.
    assert result.level == "GREEN"
    assert result.approved is True

    # The attacker string must never reach subprocess.Popen.
    launched_names = [c[0] if isinstance(c, list) else c for c in popen_calls]
    assert not any(malicious_app in str(n) for n in launched_names), (
        f"attacker-controlled app string reached subprocess.Popen: {popen_calls}"
    )
    assert result.result.get("app") == "spotify"


async def test_direct_launch_app_call_without_any_token_is_refused():
    """Sanity/control test: confirms launch_app() is NOT simply ungated —
    calling it with no token at all is correctly refused. This isolates
    the finding to the specific play_music-token-acceptance design choice,
    not a claim that launch_app has no protection whatsoever."""
    from core.control.pc_controller import PCController

    result = PCController().launch_app("some_app", control_token=None)
    assert result.get("launched") is False
    assert "control token" in result.get("error", "")
