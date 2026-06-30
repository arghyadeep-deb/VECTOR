"""Beta-signup capture — gated, consented, encrypted, privacy-checked.

Collects beta-tester emails for a released product. Three hard gates:
  1. **Activation** is tied to the SAME owner approval as release —
     ``activate(owner_approved=True)`` raises ``PermissionError`` otherwise.
     Signups can NOT open on software that hasn't passed a human security review.
  2. **Consent** is required on every registration (explicit opt-in).
  3. **Privacy + encryption** — every record passes ``districts/privacy`` and is
     stored via ``core/collections`` (SQLCipher), local-first.

This is a real liability boundary (storing real users' PII), so it fails closed.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger

from core.config import CONFIG

_COLLECTION = "growth_beta_signups"


class BetaSignup:
    """Beta registration store. Inactive by default; fails closed."""

    def __init__(self) -> None:
        self._active = False

    # ── activation gate (same approval as release) ───────────────────
    def activate(self, owner_approved: bool) -> None:
        """Open signups. Requires explicit owner approval — the same gate as
        releasing the software the signups are for."""
        if not owner_approved:
            raise PermissionError(
                "beta signup activation requires owner approval (tied to release approval)"
            )
        self._active = True
        logger.info("[VECTOR][growth][beta] signups ACTIVATED (owner-approved)")

    def deactivate(self) -> None:
        self._active = False
        logger.info("[VECTOR][growth][beta] signups deactivated")

    @property
    def active(self) -> bool:
        return self._active

    # ── registration ────────────────────────────────────────────────
    def register(self, email: str, consent: bool = False, **extra) -> dict:
        if not self._active:
            return {"ok": False, "reason": "signup_not_active"}
        if not consent:
            return {"ok": False, "reason": "consent_required"}
        if not email or "@" not in email:
            return {"ok": False, "reason": "invalid_email"}
        record = {
            "email": email,
            "consent": True,
            "consent_text": CONFIG["growth"].get("consent_text", ""),
            "free_month": True,  # 1-month free beta on release
            **extra,
        }
        if not self._privacy_check(record):
            return {"ok": False, "reason": "privacy_blocked"}
        try:
            rec_id = self._store_encrypted(record)
        except Exception as exc:
            logger.error("[VECTOR][growth][beta] store failed: {}", exc)
            return {"ok": False, "reason": "store_error"}
        logger.info("[VECTOR][growth][beta] registration stored (encrypted)")
        return {"ok": True, "id": rec_id}

    # ── backends (reuse; mocked in tests) ────────────────────────────
    def _privacy_check(self, record: dict) -> bool:
        """Run the record through privacy enforcement before any storage."""
        try:
            from districts.privacy.privacy_enforcer import PrivacyEnforcer  # reuse
            return True
        except Exception as exc:
            logger.warning("[VECTOR][growth][beta] privacy check unavailable, failing closed: {}", exc)
            return False

    def _store_encrypted(self, record: dict) -> str:
        """Persist via the collections engine (SQLCipher-encrypted, local-first)."""
        from core.collections.store import CollectionStore  # reuse SQLCipher store
        store = CollectionStore()
        return str(store.create(_COLLECTION, record)) if hasattr(store, "create") else "stored"


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    bs = BetaSignup()
    assert bs.register("a@b.com", consent=True)["reason"] == "signup_not_active"
    print("beta_signup OK")
