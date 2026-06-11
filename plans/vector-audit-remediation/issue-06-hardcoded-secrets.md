# Issue 06 — Hardcoded secrets

- **Severity:** CRITICAL · **Category:** Security
- **Source (audit):** `terminal_tool.py` (SUDO_PASSWORD), `webhook.py` (HMAC secret), `districts/` (SECRET_KEY, Flask DEBUG=True, CORS *)
- **Status:** 🟨 PARTIAL

## Issue (as reported)
Secrets hardcoded in source: a SUDO_PASSWORD in terminal_tool, an HMAC secret in
webhook, and Flask SECRET_KEY / DEBUG=True / CORS `*` in districts.

## Status notes
- ✅ `districts/intelligence/vector_social_sim` SECRET_KEY/DEBUG/CORS — fixed in
  production-hardening Task 05 (no hardcoded prod secret, DEBUG default false,
  configurable CORS). Re-verify.
- ⬜ `terminal_tool.py` SUDO_PASSWORD — todo
- ⬜ `webhook.py` HMAC secret — todo (note: an HMAC signer exists at
  `core/engine/webhook/hmac_signer.py`; check this is the offending one or a
  different webhook)

## Analysis (to complete during analysis pass)
- Affected files: `vectorcode/src/.../terminal_tool.py`, `.../webhook.py`
- Fix approach: _pending_ (move to env/keyring via `core.config`; fail closed if missing in prod)
- Tests / Acceptance: _pending_
