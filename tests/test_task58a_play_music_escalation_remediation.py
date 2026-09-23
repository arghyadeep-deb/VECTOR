"""
Regression tests for VECTOR_TECHNICAL_KNOWLEDGE/58A_PLAY_MUSIC_PERMISSION_
ESCALATION_REMEDIATION.md — Task 57 Finding A remediation.

Original finding (57_RESIDUAL_SIDE_EFFECT_SURFACE_VERIFICATION.md):
PermissionGateway's GREEN "play_music" handler read action.params["app"]
unvalidated and forwarded it to PCController.play_music() ->
PCController.launch_app(), whose token check
(`_verify_control_token(control_token, "launch_app", "play_music")`)
explicitly accepted a play_music-scoped (GREEN) token as authorization for
launch_app (RED tier) — letting an arbitrary caller-controlled app name
reach subprocess.Popen() with zero owner approval. A live trigger was
traced through core/voice/ambient_listener.py, which constructs an Action
directly from LLM-classified voice-intent output with no sanitization of
params.

Fix (core/control/pc_controller.py):
  - launch_app()'s token check now accepts ONLY "launch_app" — a
    play_music-scoped token is no longer sufficient.
  - play_music() normalizes its `app` parameter against a new, narrow
    _MEDIA_PLAYER_ALLOWLIST (currently {"spotify"}) BEFORE anything is
    launched; anything not on the allowlist falls back to the documented
    default ("spotify") rather than being forwarded anywhere.
  - play_music() launches its player via a new _launch_media_player()
    helper — hard-restricted to the allowlist, with no "raw name" Popen
    fallback (unlike launch_app()) — instead of calling launch_app() at
    all.

These tests exercise the REAL PermissionGateway.execute() / PCController
methods end to end. Only the actual OS-level primitives
(subprocess.Popen, os.startfile, shutil.which) are mocked, so NO real
process is ever launched by this file.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def _fake_popen_factory(calls: list):
    """A drop-in subprocess.Popen replacement that records the command it
    would have run and returns a fake process object — never spawns
    anything real."""
    def _fake_popen(cmd, **kwargs):
        calls.append(cmd)
        proc = MagicMock()
        proc.pid = 424242
        return proc
    return _fake_popen


# ---------------------------------------------------------------------------
# TEST 1 — Block arbitrary app through play_music
# ---------------------------------------------------------------------------

async def test_play_music_gateway_action_blocks_arbitrary_app(monkeypatch):
    """The real PermissionGateway.execute() GREEN path for
    action_type="play_music" with an attacker-chosen `app` string must NOT
    let that string reach subprocess.Popen. subprocess.Popen is mocked to
    a spy (never spawns anything real); the assertion is that the command
    it would have run, if any, is the safe default (spotify), never the
    attacker string."""
    from core.loop.permission_gateway import PermissionGateway, Action
    from core.control import pc_controller as pcc_mod

    popen_calls: list = []
    monkeypatch.setattr(pcc_mod.subprocess, "Popen", _fake_popen_factory(popen_calls))
    monkeypatch.setattr(pcc_mod.shutil, "which", lambda name: None)
    monkeypatch.setattr(pcc_mod.os, "startfile", lambda proto: None, raising=False)
    monkeypatch.setattr(pcc_mod.PCController, "media_key", lambda self, key: {"ok": True, "key": key})

    gw = PermissionGateway()
    attacker_app = "powershell"  # present in _WIN_APP_ALIASES as a REAL executable alias

    action = Action(
        action_type="play_music",
        params={"app": attacker_app},
        proposed_by="autonomous_test",
    )
    result = await gw.execute(action)

    assert result.level == "GREEN"
    assert result.approved is True

    # The attacker-chosen executable must never appear in any Popen call —
    # if anything launched, it must have been the safe default (spotify).
    launched_names = [c[0] if isinstance(c, list) else c for c in popen_calls]
    assert not any("powershell" in str(n).lower() for n in launched_names), (
        f"attacker-controlled 'powershell' reached subprocess.Popen: {popen_calls}"
    )
    assert result.result.get("app") == "spotify", (
        f"expected play_music to fall back to the safe default; got: {result.result}"
    )


def test_play_music_normalizes_unrecognized_app_to_default(monkeypatch):
    """Direct-call proof (no gateway involved): PCController.play_music()
    itself refuses to forward an unrecognized app string."""
    from core.control import pc_controller as pcc_mod

    popen_calls: list = []
    startfile_calls: list = []
    monkeypatch.setattr(pcc_mod.subprocess, "Popen", _fake_popen_factory(popen_calls))
    monkeypatch.setattr(pcc_mod.shutil, "which", lambda name: None)
    monkeypatch.setattr(pcc_mod.os, "startfile", lambda proto: startfile_calls.append(proto), raising=False)
    monkeypatch.setattr(pcc_mod.PCController, "media_key", lambda self, key: {"ok": True})
    # Force grant_control to succeed with a real, correctly-scoped token so
    # the token check itself isn't what's being exercised in this test.
    from core.loop.permission_gateway import PermissionGateway
    real_gw = PermissionGateway()
    token = real_gw.grant_control("play_music", uses=4, ttl=60)

    ctrl = pcc_mod.PCController()
    result = ctrl.play_music("definitely_not_a_media_player_cmd", control_token=token)

    assert result["app"] == "spotify"
    launched_names = [c[0] if isinstance(c, list) else c for c in popen_calls]
    assert not any("definitely_not_a_media_player_cmd" in str(n) for n in launched_names)


# ---------------------------------------------------------------------------
# TEST 2 — Safe play_music still works
# ---------------------------------------------------------------------------

async def test_play_music_default_spotify_still_launches(monkeypatch):
    """The legitimate, documented default behavior (no app named -> Spotify)
    must be unaffected by the remediation."""
    from core.loop.permission_gateway import PermissionGateway, Action
    from core.control import pc_controller as pcc_mod

    popen_calls: list = []
    monkeypatch.setattr(pcc_mod.subprocess, "Popen", _fake_popen_factory(popen_calls))
    # Force the alias-table entry to resolve so Popen is actually reached
    # (the real Spotify path may not exist on the test machine).
    monkeypatch.setattr(pcc_mod, "_WIN_APP_ALIASES", {**pcc_mod._WIN_APP_ALIASES, "spotify": "spotify.exe"})
    monkeypatch.setattr(pcc_mod.os.path, "isabs", lambda p: False)
    monkeypatch.setattr(pcc_mod.PCController, "media_key", lambda self, key: {"ok": True, "key": key})

    gw = PermissionGateway()
    action = Action(action_type="play_music", params={}, proposed_by="autonomous_test")
    result = await gw.execute(action)

    assert result.approved is True
    assert result.result.get("app") == "spotify"
    assert result.result.get("launched") is True
    assert len(popen_calls) == 1
    assert popen_calls[0] == ["spotify.exe"]


async def test_play_music_explicit_spotify_still_works(monkeypatch):
    """Explicitly requesting the one allowlisted player by name still works
    (case/whitespace-insensitive, matching the pre-existing normalization
    style used elsewhere in this file)."""
    from core.loop.permission_gateway import PermissionGateway, Action
    from core.control import pc_controller as pcc_mod

    popen_calls: list = []
    monkeypatch.setattr(pcc_mod.subprocess, "Popen", _fake_popen_factory(popen_calls))
    monkeypatch.setattr(pcc_mod, "_WIN_APP_ALIASES", {**pcc_mod._WIN_APP_ALIASES, "spotify": "spotify.exe"})
    monkeypatch.setattr(pcc_mod.os.path, "isabs", lambda p: False)
    monkeypatch.setattr(pcc_mod.PCController, "media_key", lambda self, key: {"ok": True})

    gw = PermissionGateway()
    action = Action(action_type="play_music", params={"app": "  Spotify  "}, proposed_by="autonomous_test")
    result = await gw.execute(action)

    assert result.result.get("app") == "spotify"
    assert result.result.get("launched") is True


# ---------------------------------------------------------------------------
# TEST 3 — Direct launch_app remains RED-gated
# ---------------------------------------------------------------------------

async def test_direct_launch_app_without_approval_is_not_silently_executed(monkeypatch):
    """A direct launch_app Action with no owner-trust marker must go
    through the real RED-tier flow (council/Pushover), not auto-execute.
    We don't need a full Pushover round-trip here — confirming the
    classification is RED and that it is NOT the GREEN auto-execute path
    is the relevant regression: launch_app must never again be reachable
    without RED-tier machinery, which play_music used to shortcut around."""
    from core.loop.permission_gateway import PermissionGateway

    gw = PermissionGateway()
    assert gw._classify("launch_app") == "RED"


def test_launch_app_rejects_a_play_music_scoped_token():
    """Direct proof of the core invariant: a token minted for play_music
    must be REFUSED by launch_app()'s own check."""
    from core.control.pc_controller import PCController
    from core.loop.permission_gateway import PermissionGateway

    gw = PermissionGateway()
    play_music_token = gw.grant_control("play_music", uses=4, ttl=60)

    result = PCController().launch_app("notepad", control_token=play_music_token)

    assert result.get("launched") is False
    assert "control token" in result.get("error", "")


def test_launch_app_still_works_with_its_own_token(monkeypatch):
    """Control test: launch_app() is not broken — a genuinely
    launch_app-scoped token still authorizes it."""
    from core.control import pc_controller as pcc_mod
    from core.loop.permission_gateway import PermissionGateway

    popen_calls: list = []
    monkeypatch.setattr(pcc_mod.subprocess, "Popen", _fake_popen_factory(popen_calls))

    gw = PermissionGateway()
    # RED tier -- grant_control() now requires a real, gateway-issued
    # approval receipt (2026-09-23 round 2 fix, replacing a forgeable
    # approved=True bool from round 1); this test is verifying
    # token-consumption mechanics, so it issues one directly, standing in
    # for the real owner approval that would precede this call in
    # production.
    gw._issue_approval_receipt("launch_app")
    token = gw.grant_control("launch_app", uses=1, ttl=60)
    result = pcc_mod.PCController().launch_app("notepad", control_token=token)

    assert result.get("launched") is True
    assert len(popen_calls) == 1


# ---------------------------------------------------------------------------
# TEST 4 — play_music token cannot be reused as launch_app authorization
# ---------------------------------------------------------------------------

def test_play_music_token_cannot_authorize_arbitrary_launch_app_call():
    """Explicit end-to-end proof of the mandatory invariant: mint a REAL
    play_music-scoped token via the real gateway, then attempt to use it
    to authorize a completely unrelated launch_app() call for an arbitrary
    executable. Must be refused."""
    from core.control.pc_controller import PCController
    from core.loop.permission_gateway import PermissionGateway

    gw = PermissionGateway()
    token = gw.grant_control("play_music", uses=4, ttl=60)

    result = PCController().launch_app("powershell", control_token=token)

    assert result.get("launched") is False, (
        "a play_music-scoped token authorized launch_app — the invariant is broken"
    )


def test_verify_control_directly_confirms_scope_mismatch():
    """Lowest-level proof: PermissionGateway.verify_control() itself
    correctly reports a scope mismatch between a play_music grant and a
    launch_app check — the fix does not depend on PCController's own
    bookkeeping."""
    from core.loop.permission_gateway import PermissionGateway

    gw = PermissionGateway()
    token = gw.grant_control("play_music", uses=1, ttl=60)

    assert gw.verify_control(token, "launch_app") is False


# ---------------------------------------------------------------------------
# TEST 5 — Ambient voice path
# ---------------------------------------------------------------------------

async def test_ambient_voice_style_action_cannot_escalate(monkeypatch):
    """Reproduces the exact production boundary core/voice/ambient_
    listener.py exercises (confirmed by reading the real source,
    core/voice/ambient_listener.py:475): it constructs
    `Action(action_type=<LLM output>, params=<LLM output>,
    proposed_by="voice")` directly from an LLM voice-intent classifier's
    result, with no sanitization, then calls `gw.execute(action)`.

    Reproducing the full ambient pipeline (real audio capture, wake-word
    detection, the LLM classifier itself) is impractical and unnecessary
    here — the vulnerable step was never the audio/classification pipeline,
    it was what happens AFTER an Action reaches gw.execute() with
    attacker-influenced params. This test constructs the exact Action
    shape ambient_listener.py's own code builds and drives it through the
    real gateway, proving the boundary that actually matters."""
    from core.loop.permission_gateway import PermissionGateway, Action
    from core.control import pc_controller as pcc_mod

    popen_calls: list = []
    startfile_calls: list = []
    monkeypatch.setattr(pcc_mod.subprocess, "Popen", _fake_popen_factory(popen_calls))
    monkeypatch.setattr(pcc_mod.shutil, "which", lambda name: None)
    monkeypatch.setattr(pcc_mod.os, "startfile", lambda proto: startfile_calls.append(proto), raising=False)
    monkeypatch.setattr(pcc_mod.PCController, "media_key", lambda self, key: {"ok": True})

    # Simulates an LLM voice-intent classifier having (mis)classified some
    # ambient audio as a play_music request naming an arbitrary program.
    simulated_llm_intent = {
        "action_type": "play_music",
        "params": {"app": "cmd"},  # a real _WIN_APP_ALIASES entry, not a media player
    }

    gw = PermissionGateway()
    action = Action(
        action_type=simulated_llm_intent["action_type"],
        params=simulated_llm_intent["params"],
        proposed_by="voice",
    )
    result = await gw.execute(action)

    assert result.approved is True  # GREEN still auto-executes, as intended
    launched_names = [c[0] if isinstance(c, list) else c for c in popen_calls]
    assert not any("cmd" in str(n).lower() for n in launched_names), (
        f"ambient-voice-style 'cmd' request reached subprocess.Popen: {popen_calls}"
    )
    assert result.result.get("app") == "spotify"


# ---------------------------------------------------------------------------
# TEST 6 — No regression to run_shell_command
# ---------------------------------------------------------------------------

def test_run_shell_command_token_scope_unchanged():
    """run_shell_command's token check must still accept ONLY its own
    scope — unaffected by this remediation (it was never broadened, but
    this locks in that the play_music fix didn't accidentally touch it)."""
    from core.control.pc_controller import PCController
    from core.loop.permission_gateway import PermissionGateway

    gw = PermissionGateway()

    # RED tier -- grant_control() now requires a real, gateway-issued
    # approval receipt (2026-09-23 round 2); standing in for the real
    # owner approval that would precede this call in production.
    gw._issue_approval_receipt("run_shell_command")
    shell_token = gw.grant_control("run_shell_command", uses=1, ttl=60)
    play_music_token = gw.grant_control("play_music", uses=1, ttl=60)

    ctrl = PCController()
    # Correct scope: refused only if actually broken.
    assert ctrl._verify_control_token(shell_token, "run_shell_command") is True

    # A play_music token must not authorize shell execution either —
    # confirms no new cross-scope acceptance was introduced anywhere.
    assert ctrl._verify_control_token(play_music_token, "run_shell_command") is False


def test_run_shell_command_still_blocked_with_no_token(monkeypatch):
    from core.control import pc_controller as pcc_mod

    run_calls: list = []

    def _fake_run(cmd, **kwargs):
        run_calls.append(cmd)
        raise AssertionError("subprocess.run must not be called when blocked")

    monkeypatch.setattr(pcc_mod.subprocess, "run", _fake_run)

    result = pcc_mod.PCController().run_shell_command("echo hi", control_token=None)

    assert result.get("blocked") is True
    assert run_calls == []
