"""Phase-3 audit: districts/growth fail-closed / honest-status fixes."""
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import pytest

from core.config import CONFIG


# ── content_arm: ungated publish when auto_publish is off ───────────────
@pytest.mark.parametrize("mode", ["phone", "graph_api"])
async def test_auto_publish_off_never_runs_real_publisher(monkeypatch, mode):
    from districts.growth.content_arm import ContentArm
    monkeypatch.setitem(CONFIG["growth"], "auto_publish", False)
    monkeypatch.setitem(CONFIG["growth"], "instagram_mode", mode)
    arm = ContentArm()
    called = {"phone": 0, "graph": 0, "notify": 0}

    async def phone(reel=None): called["phone"] += 1; return True
    async def graph(reel=None): called["graph"] += 1; return True
    async def notify(reel=None): called["notify"] += 1; return True
    monkeypatch.setattr(arm, "_phone_post", phone)
    monkeypatch.setattr(arm, "_graph_api_post", graph)
    monkeypatch.setattr(arm, "_notify_owner_to_post", notify)
    await arm._gated_publish("r.mp4", "work_done")
    assert called == {"phone": 0, "graph": 0, "notify": 1}


# ── content_arm: failure reported as success ────────────────────────────
async def test_youtube_phone_blocked_is_failure(monkeypatch):
    from districts.growth.content_arm import ContentArm
    monkeypatch.setitem(CONFIG["growth"], "youtube_mode", "phone")
    mod = types.ModuleType("districts.content.phone_poster")

    class PP:
        async def post_youtube(self, *a, **k):
            return {"status": "blocked", "reason": "owner did not approve"}
    mod.PhonePoster = PP
    monkeypatch.setitem(sys.modules, "districts.content.phone_poster", mod)
    assert await ContentArm()._publish_youtube("r.mp4", "work_done") is False


async def test_youtube_api_simulated_is_not_success(monkeypatch):
    from districts.growth.content_arm import ContentArm
    monkeypatch.setitem(CONFIG["growth"], "youtube_mode", "api")
    mod = types.ModuleType("districts.content.uploader")

    class U:
        async def upload_to_youtube(self, *a, **k):
            return {"status": "success", "simulated": True}
    mod.Uploader = U
    monkeypatch.setitem(sys.modules, "districts.content.uploader", mod)
    assert await ContentArm()._publish_youtube("r.mp4", "w") is False


async def test_instagram_swallowed_failure_not_ok(monkeypatch):
    from districts.growth.content_arm import ContentArm
    monkeypatch.setitem(CONFIG["growth"], "instagram_mode", "phone")
    mod = types.ModuleType("districts.content.phone_poster")

    class PP:
        async def post_instagram(self, *a, **k):
            return {"status": "error", "reason": "phone not connected"}
    mod.PhonePoster = PP
    monkeypatch.setitem(sys.modules, "districts.content.phone_poster", mod)
    assert await ContentArm()._instagram_publisher_safe("r.mp4") is False


async def test_graph_api_passes_required_hashtags(monkeypatch):
    from districts.growth.content_arm import ContentArm
    mod = types.ModuleType("districts.content.uploader")

    class U:
        async def upload_to_instagram(self, video_path, caption, hashtags, scheduled_time=None):
            return {"status": "success", "platform": "instagram"}
    mod.Uploader = U
    monkeypatch.setitem(sys.modules, "districts.content.uploader", mod)
    assert await ContentArm()._graph_api_post("r.mp4") is True


# ── software_arm ────────────────────────────────────────────────────────
def test_specs_not_validated_just_because_import_works():
    from districts.growth.software_arm import SoftwareArm
    assert SoftwareArm()._specs({"title": "x"})["validated"] is False
    assert SoftwareArm()._specs(None)["validated"] is False
    assert SoftwareArm()._specs({"validated": True})["validated"] is True


async def test_escalation_actually_notifies_owner(monkeypatch):
    from districts.growth.software_arm import SoftwareArm
    arm = SoftwareArm()
    monkeypatch.setattr(arm, "_review", lambda code: False)
    monkeypatch.setattr(arm, "_fix", lambda code, review: code)
    sent = []

    async def fake_push(msg, priority=0): sent.append(msg)
    import core.notify as notify
    monkeypatch.setattr(notify, "pushover", fake_push)
    res = await arm._review_fix_loop("x")
    assert res["escalated"] is True and len(sent) == 1


async def test_failed_build_aborts_pipeline(monkeypatch):
    from districts.growth.software_arm import SoftwareArm
    arm = SoftwareArm()
    monkeypatch.setattr(arm, "_build", lambda specs: {"specs": specs, "code": ""})
    reviewed = []
    monkeypatch.setattr(arm, "_review", lambda c: reviewed.append(c) or True)
    res = await arm.run_once({"title": "x"})
    assert res["status"] == "error" and res["release_ready"] is False and not reviewed


# ── beta_signup ─────────────────────────────────────────────────────────
def test_activate_requires_strict_true():
    from districts.growth.beta_signup import BetaSignup
    for bad in ("no", 1, "false", None, [1]):
        with pytest.raises(PermissionError):
            BetaSignup().activate(owner_approved=bad)


def test_consent_must_be_strict_true(monkeypatch):
    from districts.growth.beta_signup import BetaSignup
    bs = BetaSignup(); bs.activate(owner_approved=True)
    assert bs.register("a@b.com", consent="false")["reason"] == "consent_required"


def test_extra_cannot_overwrite_validated_fields(monkeypatch):
    from districts.growth.beta_signup import BetaSignup
    bs = BetaSignup(); bs.activate(owner_approved=True)
    stored = {}
    monkeypatch.setattr(bs, "_privacy_check", lambda r: True)
    monkeypatch.setattr(bs, "_store_encrypted", lambda r: stored.update(r) or "id")
    bs.register("a@b.com", consent=True, consent_text="x", free_month=False)
    assert stored["free_month"] is True and stored["consent_text"] != "x"


def test_privacy_check_blocks_pii_in_extras(monkeypatch):
    from districts.growth.beta_signup import BetaSignup
    mod = types.ModuleType("districts.privacy.privacy_enforcer")

    class PE:
        pii_patterns = {"phone": r"\b[6-9]\d{9}\b"}
    mod.PrivacyEnforcer = PE
    monkeypatch.setitem(sys.modules, "districts.privacy.privacy_enforcer", mod)
    bs = BetaSignup()
    assert bs._privacy_check({"email": "a@b.com", "extra": {"note": "call 9876543210"}}) is False
    assert bs._privacy_check({"email": "a@b.com", "extra": {"note": "hi"}}) is True


def test_privacy_check_fails_closed_when_enforcer_cannot_init(monkeypatch):
    from districts.growth.beta_signup import BetaSignup
    mod = types.ModuleType("districts.privacy.privacy_enforcer")

    class PE:
        def __init__(self): raise RuntimeError("boom")
    mod.PrivacyEnforcer = PE
    monkeypatch.setitem(sys.modules, "districts.privacy.privacy_enforcer", mod)
    assert BetaSignup()._privacy_check({"email": "a@b.com", "extra": {}}) is False


def test_store_encrypted_really_stores_via_engine(monkeypatch):
    import sqlite3
    from core.collections import CollectionEngine
    import core.collections as cc
    from districts.growth.beta_signup import BetaSignup, _COLLECTION
    conn = sqlite3.connect(":memory:")
    eng = CollectionEngine(conn=conn)
    monkeypatch.setattr(cc, "CollectionEngine", lambda *a, **k: eng)
    rid = BetaSignup()._store_encrypted(
        {"email": "a@b.com", "consent": True, "consent_text": "t", "free_month": True, "extra": {}})
    assert rid and eng.get_record(_COLLECTION, rid)["email"] == "a@b.com"
