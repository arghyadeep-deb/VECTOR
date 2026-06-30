"""Task 5 — beta signup: activation gated to owner approval, consent required,
stored encrypted + privacy-checked."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import pytest


def test_signup_blocked_until_release_approved():
    from districts.growth.beta_signup import BetaSignup
    bs = BetaSignup(); bs.deactivate()
    r = bs.register(email="a@b.com", consent=True)
    assert r["ok"] is False and r["reason"] == "signup_not_active"


def test_signup_requires_consent_and_stores_encrypted(monkeypatch):
    from districts.growth.beta_signup import BetaSignup
    bs = BetaSignup(); bs.activate(owner_approved=True)
    assert bs.register("a@b.com", consent=False)["ok"] is False  # consent required
    stored = {}
    monkeypatch.setattr(bs, "_store_encrypted", lambda rec: stored.update(rec) or "id1")
    monkeypatch.setattr(bs, "_privacy_check", lambda rec: True)
    r = bs.register("a@b.com", consent=True)
    assert r["ok"] is True and stored["email"] == "a@b.com"


def test_activation_requires_owner_approval():
    from districts.growth.beta_signup import BetaSignup
    bs = BetaSignup()
    with pytest.raises(PermissionError):
        bs.activate(owner_approved=False)


if __name__ == "__main__":
    print("run via pytest")
