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
_FIELDS = [
    {"name": "email", "type": "text", "required": True},
    {"name": "consent", "type": "bool"},
    {"name": "consent_text", "type": "text"},
    {"name": "free_month", "type": "bool"},
    {"name": "extra", "type": "json"},
]


class BetaSignup:
    """Beta registration store. Inactive by default; fails closed."""

    def __init__(self) -> None:
        self._active = False

    # ── activation gate (same approval as release) ───────────────────
    def activate(self, owner_approved: bool) -> None:
        """Open signups. Requires explicit owner approval — the same gate as
        releasing the software the signups are for."""
        if owner_approved is not True:  # strict: a truthy string/obj is not approval
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
        if consent is not True:  # strict: "false"/1/"no" must not count as opt-in
            return {"ok": False, "reason": "consent_required"}
        if not email or "@" not in email:
            return {"ok": False, "reason": "invalid_email"}
        # Caller extras are nested so they can never overwrite the validated
        # email / consent / free_month fields (they used to be spread last).
        record = {
            "email": email,
            "consent": True,
            "consent_text": CONFIG["growth"].get("consent_text", ""),
            "free_month": True,  # 1-month free beta on release
            "extra": dict(extra),
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
        """Run the record through privacy enforcement before any storage.

        Fails closed: the enforcer must actually load AND the caller-supplied
        extra fields must carry no PII beyond the (consented) email. Previously
        this returned True as soon as the import succeeded -- nothing was checked.
        """
        try:
            import re
            from districts.privacy.privacy_enforcer import PrivacyEnforcer  # reuse
            patterns = PrivacyEnforcer().pii_patterns
            blob = " ".join(str(v) for v in (record.get("extra") or {}).values())
            for ptype, pattern in patterns.items():
                if re.search(pattern, blob):
                    logger.warning("[VECTOR][growth][beta] extra fields contain {} -- blocked", ptype)
                    return False
            return True
        except Exception as exc:
            logger.warning("[VECTOR][growth][beta] privacy check unavailable, failing closed: {}", exc)
            return False

    def _store_encrypted(self, record: dict) -> str:
        """Persist via the collections engine (SQLCipher-encrypted, local-first).
        Raises on any failure -- never reports "stored" for a record that was not."""
        from core.collections import Collection, CollectionEngine  # reuse SQLCipher store
        engine = CollectionEngine()
        if engine.get_collection(_COLLECTION) is None:
            engine.create_collection(Collection(name=_COLLECTION, fields=_FIELDS))
        return str(engine.create_record(_COLLECTION, record)["id"])


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    bs = BetaSignup()
    assert bs.register("a@b.com", consent=True)["reason"] == "signup_not_active"
    print("beta_signup OK")
