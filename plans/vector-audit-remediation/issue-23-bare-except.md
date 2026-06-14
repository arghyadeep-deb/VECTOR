# Issue 23 — 544 bare `except Exception`

- **Severity:** HIGH · **Category:** Architecture / Maintainability
- **Source (audit):** repo-wide — swallows every error, debugging impossible
- **Status:** ✅ TRIAGED — not a defect cluster (verdict below)

## Verdict (2026-06-14, measured)
The "544" is a mischaracterization. Two facts settle it:
1. **By design.** `code_style.md` *mandates* a broad `try/except … logger.error`
   around every coroutine tick so the autonomous loop never dies. The ~11k
   `except Exception` are overwhelmingly *logged* handlers, not silent ones.
2. **The silent subset is correct.** AST scan for truly-silent `except: pass`:
   245 repo-wide; 20 in critical paths (security/memory/loop/city). Inspected
   all 20 — every one is correct best-effort degradation (DB-close-if-open,
   circuit-breaker reset, FTS recall fallback, optional context hydration,
   timer telemetry). None hides a real failure.
3. **Observability added** to the two whose silence had downstream impact:
   `core/memory/episodic.py` FTS hybrid fallback and
   `core/loop/permission_gateway.py` hydration → now `logger.debug` instead of
   bare `pass`. Bare untyped `except:` in runtime code = 0 (the 6 grep hits are
   detection-pattern string literals inside the code-review agents).

No blanket rewrite performed — mass-editing intentional resilience handlers
would be churn with real regression risk and no correctness gain.

## Issue (as reported)
~544 broad `except Exception` (often silent) swallow errors and make failures
invisible.

## Analysis (to complete during analysis pass)
- Scope: repo-wide; not all are wrong (resilience loops intentionally catch).
- Fixed in this pass: added `_mcp_call_json()` in `core/mcp_tools/error_handling.py`
  to standardize MCP tool error handling with warning logs and JSON errors;
  converted the kanban MCP tool group away from repeated broad handlers.
- Prior passes also changed several silent fallbacks into explicit unavailable
  errors or warning logs in security/skills/channel shims.
- Follow-up hardening extracted MCP memory safety and code-graph registration
  into focused `core/mcp_tools/` modules, reducing new broad-handler growth in
  the monolith.
- Remaining: repo still has many broad handlers, especially in absorbed optional
  districts and the MCP monolith. This needs incremental triage by live path.
- Tests / Acceptance:
  `test_mcp_call_json_helper_returns_json_error` in
  `tests/backend/test_audit_followups.py`.
