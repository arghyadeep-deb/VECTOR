# Issue 06 — Hardcoded secrets

- **Severity:** CRITICAL · **Category:** Security
- **Source (audit):** `terminal_tool.py` (SUDO_PASSWORD), `webhook.py` (HMAC secret), `districts/` (SECRET_KEY, Flask DEBUG=True, CORS *)
- **Status:** ✅ RESOLVED

## Issue (as reported)
Secrets hardcoded in source: a SUDO_PASSWORD in terminal_tool, an HMAC secret in
webhook, and Flask SECRET_KEY / DEBUG=True / CORS `*` in districts.

## Status notes
- ✅ `districts/intelligence/vector_social_sim` SECRET_KEY/DEBUG/CORS — fixed in
  production-hardening Task 05 (no hardcoded prod secret, DEBUG default false,
  configurable CORS).
- ✅ `vectorcode/src/tools/terminal_tool.py` — no static sudo password fallback.
- ✅ `vectorcode/src/gateway/platforms/webhook.py` and
  `vectorcode/src/vector_cli/webhook.py` — placeholder HMAC secrets rejected,
  production `INSECURE_NO_AUTH` rejected, docs no longer suggest placeholder
  secrets.
- ✅ Additional fixed defaults: `VECTOR_FEDERATION_SECRET`,
  `VECTOR_OFP_SECRET`, and `OPENMYTHOS_WEBHOOK_SECRET` now fail closed in
  production instead of falling back to hardcoded literals.

## Analysis (to complete during analysis pass)
- Affected files: `vectorcode/src/.../terminal_tool.py`, `.../webhook.py`
- Fix approach: env/config-only secrets, production fail-closed checks, random
  local-only development fallback where a dev fallback is still acceptable.
- Tests / Acceptance: `python -m pytest -q tests/backend/test_audit_followups.py`
  covers hardcoded marker removal and webhook placeholder/prod rejection.
