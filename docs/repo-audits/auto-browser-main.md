# auto-browser-main Audit

**Repo:** auto-browser — Python/FastAPI browser automation with AI agents (MIT)
**Audited:** 2026-06-02
**Note:** Absorbed before the audit protocol started (2026-05-27 session).

---

## 1. Repo Reality

Python browser automation framework with AI agent loop. Features:
- DOM pruner (relevance-scored interactive element pruning, ~18k→500 tokens)
- PII scrubber (17 regex patterns + Pillow pixel-redaction of screenshots)
- Named browser auth profiles (Playwright `storage_state()` save/load/export/import)
- Mesh/delegation patterns (multi-browser agent distributed fleet)

---

## 2. VECTOR Parity

| Feature | VECTOR file | Verified | Status |
|---------|-------------|----------|--------|
| DOM pruner | `core/browser/dom_pruner.py` | DOMPruner OK | ✅ |
| PII scrubber | `core/browser/pii_scrub.py` | ✅ | ✅ |
| Named auth profiles | `core/browser/auth_profiles.py` | BrowserAuthStore OK | ✅ |
| MCP tools (3) | `core/mcp_server.py` | browser_prune_dom, browser_list_auth_profiles, browser_save_auth_profile | ✅ |

**Test coverage:** 59 tests passing (`tests/test_browser_absorption.py`).

---

## 3. Frontend: N/A

---

## 4. Verdict

**SAFE TO DELETE** — All 3 Python components absorbed and verified with 59 tests. Mesh/delegation (multi-browser distributed fleet) was skipped as out of scope for single-owner VECTOR.

**Delete-readiness:** ✅ DELETE-NOW

---

## 5. Gaps: None (absorption complete)
