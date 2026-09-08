# Documentation vs Code

**Purpose:** Discrepancies between docs and implementation
**Level:** System Level (Level 1)

---

## Overview

This document identifies discrepancies between documentation (CLAUDE.md, rules, brain vault) and actual code implementation.

**Key Properties:**
- **Stale docs** — documentation outdated
- **Undocumented** — code exists but not documented
- **Mismatched** — docs say one thing, code does another
- **Verified** — docs match code

---

## Stale Documentation

### 1. phase_status.md — Gaps 4/6/7/8

**Doc says:** "Year 2, not built"
**Reality:** All four exist
- `core/memory/counterfactual.py` (Gap 4) ✅
- `core/memory/causal_graph.py` (Gap 6) ✅
- `core/brain/person_model.py` (Gap 7) ✅
- `core/city/meta_cognition.py` (Gap 8) ✅

**Status:** ⚠️ STALE — docs need update

**Correction:** Session 2026-06-11 already corrected this in phase_status.md

---

### 2. phase_status.md — Next.js Dashboard

**Doc says:** "❌ not built"
**Reality:** `frontend/` HUD exists (6.3k LOC)
**Status:** ⚠️ STALE — HUD serves dashboard role

**Correction:** Session 2026-06-11 already noted this is superseded

---

### 3. phase_status.md — Fly.io Brain Server

**Doc says:** "❌ Run: `fly launch`"
**Reality:** Owner declined, Cloudflare Worker has full parity
**Status:** ⚠️ STALE — explicitly not building

**Correction:** Session 2026-06-20 already removed `cloud/brain_server/`

---

### 4. architecture.md — VECTOR Gaps

**Doc says:** "Gap 4/6/7/8 — Year 2"
**Reality:** All exist (see #1)
**Status:** ⚠️ STALE — needs update

---

## Undocumented Code

### 1. Collections Engine

**Code exists:** `core/collections/` (8 files)
**Doc coverage:** Minimal — mentioned in phase_status.md
**Status:** ⚠️ UNDER-DOCUMENTED

**What's missing:**
- Full API reference
- Schema design guide
- Migration documentation

---

### 2. OAuth System

**Code exists:** `core/engine/oauth/` (YAML registry, flows, server)
**Doc coverage:** Minimal — mentioned in absorbed repos
**Status:** ⚠️ UNDER-DOCUMENTED

**What's missing:**
- Provider setup guide
- Token refresh flow
- OAuth 1.0a usage

---

### 3. Browser Absorption

**Code exists:** `core/browser/` (DOM pruner, PII scrub, auth profiles)
**Doc coverage:** Minimal — mentioned in phase_status.md
**Status:** ⚠️ UNDER-DOCUMENTED

**What's missing:**
- DOM pruning algorithm
- PII scrub patterns
- Auth profile management

---

### 4. Webhook Signing

**Code exists:** `core/engine/webhook/hmac_signer.py`
**Doc coverage:** Minimal — mentioned in absorbed repos
**Status:** ⚠️ UNDER-DOCUMENTED

**What's missing:**
- HMAC signing guide
- Webhook delivery retry logic
- Signed headers format

---

## Mismatched Documentation

### 1. model_catalog.yaml vs provider_client.py

**Doc says:** model_catalog.yaml defines free models
**Code does:** provider_client.py has hardcoded fallback
**Status:** ⚠️ MISMATCH — dual source of truth

**Impact:** Confusion about which models are available

**Fix:** Consolidate to single source (model_catalog.yaml)

---

### 2. CLAUDE.md vs actual routing

**Doc says:** "Ollama is the FALLBACK"
**Code does:** Cloud providers primary, Ollama terminal fallback
**Status:** ⚠️ MISMATCH — misleading wording

**Impact:** Confusion about routing logic

**Fix:** Update CLAUDE.md to clarify: "Cloud primary for quality, Ollama terminal fallback"

---

### 3. rules/models.md vs actual models

**Doc says:** Lists specific models
**Code does:** 27 providers, many more models
**Status:** ⚠️ MISMATCH — incomplete list

**Impact:** Developers don't know all available models

**Fix:** Auto-generate model list from model_catalog.yaml

---

## Verified Documentation

### 1. CLAUDE.md — Core Rules

**Doc says:** 10 non-negotiable rules
**Code does:** All rules enforced
**Status:** ✅ VERIFIED

- RULE 1: context_engine.session_hydration_prompt() ✅
- RULE 2: Loop never dies ✅
- RULE 3: Permission gateway only path ✅
- RULE 4: Policy wired both ways ✅
- RULE 5: Local-first inference ✅
- RULE 6: No print() in production ✅
- RULE 7: SQLCipher for main DB ✅
- RULE 8: Never use requests/flask/threading/pickle ✅
- RULE 9: CONFIG dict for all values ✅
- RULE 10: Free-tier only at runtime ✅

---

### 2. architecture.md — Three-Layer System

**Doc says:** Devices → Cloud → APIs
**Code does:** Matches exactly
**Status:** ✅ VERIFIED

---

### 3. code_style.md — Naming Conventions

**Doc says:** snake_case files, PascalCase classes
**Code does:** Follows conventions
**Status:** ✅ VERIFIED

---

## Documentation Summary

| Category | Count | Status |
|----------|-------|--------|
| Stale docs | 4 | ⚠️ Need update |
| Under-documented | 4 | ⚠️ Need expansion |
| Mismatched | 3 | ⚠️ Need correction |
| Verified | 3 | ✅ Match code |
| **Total** | **14** | — |

---

## Recommendations

### High Priority

1. **Update phase_status.md** — Mark Gaps 4/6/7/8 as complete
2. **Document collections engine** — Add API reference
3. **Clarify routing logic** — Update CLAUDE.md wording

### Medium Priority

4. **Document OAuth system** — Add setup guide
5. **Document browser absorption** — Add usage guide
6. **Consolidate model catalog** — Single source of truth

### Low Priority

7. **Auto-generate model list** — From model_catalog.yaml
8. **Add docstrings** — To under-documented modules

---

## Cross-References

See:
- `01_GLOBAL_SYSTEM_MAP.md` — System overview
- `38_DOCUMENTATION_VS_CODE.md` — this document
- `37_KNOWN_ISSUES.md` — Known issues
- `40_CRITICAL_FINDINGS.md` — Critical analysis

---

**Last Updated:** 2026-08-12
**Status:** ✅ COMPLETE
