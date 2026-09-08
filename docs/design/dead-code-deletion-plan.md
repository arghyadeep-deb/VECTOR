# Dead Code Reachability Verification & Deletion Plan

**Date:** 2026-08-13
**Source:** Cognitive Integration Audit (§6 — 8 dead code modules)
**Method:** 10-point reachability verification per module

---

## Verification Method

For each candidate, 10 checks were performed:

| # | Check | What it catches |
|---|-------|----------------|
| 1 | Static imports | `import X` / `from X import Y` |
| 2 | Dynamic imports | `importlib.import_module("X")` |
| 3 | Manifest references | `config/agent_manifest.yaml` class entries |
| 4 | Configuration references | `core/config.py`, `.env`, YAML configs |
| 5 | CLI references | `scripts/`, `run_vector.py` CLI commands |
| 6 | API/router references | `core/api/routers/` endpoints |
| 7 | Plugin/registry references | `AgentRegistry`, governor capability routing |
| 8 | Reflection/string-based loading | `eval()`, `__import__()`, string class paths |
| 9 | Test references | `tests/` files that import the module |
| 10 | Runtime execution trace | Evidence of actual invocation during runtime |

---

## Results

### 1. `core/brain/self_evolve.py` — ✅ DEFINITELY DEAD

| Check | Result |
|-------|--------|
| 1. Static imports | ❌ None. No `import self_evolve` anywhere in codebase |
| 2. Dynamic imports | ❌ None |
| 3. Manifest references | ❌ NOT in `agent_manifest.yaml` |
| 4. Configuration refs | ❌ None |
| 5. CLI references | ❌ None |
| 6. API/router refs | ❌ None |
| 7. Plugin/registry refs | ❌ None |
| 8. Reflection loading | ❌ None |
| 9. Test references | ❌ None |
| 10. Runtime trace | ❌ No evidence of runtime invocation |

**Only references:** Audit documentation files (45, 46) and its own `__main__` block.
**Replacement:** `self_improvement_cycle.py` covers this functionality.
**Risk of deletion:** Zero.

---

### 2. `core/memory/external_mirror.py` — ✅ DEFINITELY DEAD

| Check | Result |
|-------|--------|
| 1. Static imports | ❌ None in production code |
| 2. Dynamic imports | ❌ None |
| 3. Manifest references | ❌ NOT in `agent_manifest.yaml` |
| 4. Configuration refs | ❌ None |
| 5. CLI references | ❌ None |
| 6. API/router refs | ❌ None |
| 7. Plugin/registry refs | ❌ None |
| 8. Reflection loading | ❌ None |
| 9. Test references | ⚠️ ONE test: `tests/backend/test_repo_analysis_optional_boundaries.py:6` |
| 10. Runtime trace | ❌ Zero callers since creation |

**Only references:** One test file + audit docs (44, 46).
**Security note:** `44_UNRESOLVED_SYSTEM_QUESTIONS.md` flagged this as a potential data exfiltration risk — name "external_mirror" suggests mirroring to external store.
**Risk of deletion:** Zero. Test reference must also be removed.

---

### 3. `core/memory/vector_index_gate.py` — ✅ DEFINITELY DEAD

| Check | Result |
|-------|--------|
| 1. Static imports | ❌ None in production code |
| 2. Dynamic imports | ❌ None |
| 3. Manifest references | ❌ NOT in `agent_manifest.yaml` |
| 4. Configuration refs | ❌ None |
| 5. CLI references | ❌ None |
| 6. API/router refs | ❌ None |
| 7. Plugin/registry refs | ❌ None |
| 8. Reflection loading | ❌ None |
| 9. Test references | ⚠️ ONE test: `tests/backend/test_repo_analysis_optional_boundaries.py:7` |
| 10. Runtime trace | ❌ No production use |

**Only references:** Same single test file + audit doc.
**Risk of deletion:** Zero. Test reference must also be removed.

---

### 4. `districts/personal_growth/zk_steward.py` — 🟡 DYNAMICALLY REACHABLE — DO NOT DELETE

| Check | Result |
|-------|--------|
| 1. Static imports | ❌ None (lazy-loaded via manifest, not direct import) |
| 2. Dynamic imports | ✅ `ManifestLoader.instantiate_all()` → `importlib.import_module("districts.personal_growth.zk_steward")` |
| 3. Manifest references | ✅ `agent_manifest.yaml:1130-1131` — `class: districts.personal_growth.zk_steward.ZKSteward` |
| 4. Configuration refs | ❌ None |
| 5. CLI references | ❌ None |
| 6. API/router refs | ❌ None |
| 7. Plugin/registry refs | ✅ Registered in `AgentRegistry` at runtime via `bootstrap_agents()` |
| 8. Reflection loading | ✅ String class path in manifest → `importlib.import_module` |
| 9. Test references | ❌ None |
| 10. Runtime trace | ⚠️ Agent IS instantiated and registered. Governor routes "zettelkasten"/"zk"/"knowledge_links" → `personal_growth` district. But no evidence governor dispatches actually reach THIS specific agent. |

**Additional references:**
- `core/prompt_library.py:89` — prompt mapping `"zk_steward": "zk-steward"`
- `docs/manifest_gap.md:263` — manifest gap analysis
- `phase_status.md:245` — marked ✅ built
- 5 documentation/inventory files

**Why NOT dead:** The agent IS instantiated at runtime via the manifest loading path. It IS registered in the agent registry. Governor has keyword routes to its district. Deleting it would break `ManifestLoader.instantiate_all()` (which catches exceptions and skips — so it wouldn't crash, but the agent would disappear from the registry).

**Verdict:** DYNAMICALLY REACHABLE. Do not delete. If unused, wire it up or remove from manifest first.

---

### 5. `districts/personal_growth/feedback_synthesizer.py` — 🟡 DYNAMICALLY REACHABLE — DO NOT DELETE

| Check | Result |
|-------|--------|
| 1. Static imports | ❌ None (lazy-loaded via manifest) |
| 2. Dynamic imports | ✅ `ManifestLoader.instantiate_all()` → `importlib.import_module("districts.personal_growth.feedback_synthesizer")` |
| 3. Manifest references | ✅ `agent_manifest.yaml:1124-1125` — `class: districts.personal_growth.feedback_synthesizer.FeedbackSynthesizer` |
| 4. Configuration refs | ❌ None |
| 5. CLI references | ❌ None |
| 6. API/router refs | ❌ None |
| 7. Plugin/registry refs | ✅ Registered in `AgentRegistry` at runtime |
| 8. Reflection loading | ✅ String class path in manifest → `importlib.import_module` |
| 9. Test references | ❌ None |
| 10. Runtime trace | ⚠️ Agent IS instantiated. Governor routes "feedback"/"synthesize_feedback" → `personal_growth`. No evidence of actual dispatch to this specific agent. |

**Additional references:**
- `core/prompt_library.py:88` — `"feedback_synthesizer": "product-feedback-synthesizer"`
- `docs/manifest_gap.md:262` — manifest gap analysis
- `phase_status.md:245` — marked ✅ built
- 5 documentation/inventory files

**Why NOT dead:** Same as zk_steward — instantiated at runtime, registered, has governor keyword routes to its district.

**Verdict:** DYNAMICALLY REACHABLE. Do not delete.

---

### 6. `districts/data_analytics/performance_optimizer.py` — 🟡 DYNAMICALLY REACHABLE — DO NOT DELETE

| Check | Result |
|-------|--------|
| 1. Static imports | ❌ None |
| 2. Dynamic imports | ✅ `ManifestLoader.instantiate_all()` → `importlib.import_module("districts.data_analytics.performance_optimizer")` |
| 3. Manifest references | ✅ `agent_manifest.yaml:596-597` — `class: districts.data_analytics.performance_optimizer.PerformanceOptimizer` |
| 4. Configuration refs | ❌ None |
| 5. CLI references | ❌ None |
| 6. API/router refs | ❌ None |
| 7. Plugin/registry refs | ✅ Registered in `AgentRegistry` at runtime |
| 8. Reflection loading | ✅ String class path in manifest → `importlib.import_module` |
| 9. Test references | ❌ None |
| 10. Runtime trace | ⚠️ Agent IS instantiated. Governor routes "optimize"/"profile"/"bottleneck" → `data_analytics`. Note: audit said "not in governor routing" — that was WRONG. Governor explicitly maps these keywords to the `data_analytics` district. |

**Additional references:**
- `docs/manifest_gap.md:93` — manifest gap analysis
- `vectorcode/skills/vc-resource-allocator.md:382` — references (TypeScript, unrelated)

**Correction to audit:** The audit claimed this module was "not in governor routing." That's incorrect — governor.py maps "optimize", "profile", "bottleneck" → `data_analytics` district. The agent IS reachable via district dispatch.

**Verdict:** DYNAMICALLY REACHABLE. Do not delete.

---

### 7. `core/security/safe_eval.py` — ✅ ALIVE — DO NOT DELETE

| Check | Result |
|-------|--------|
| 1. Static imports | ✅ 3 production callers: |
| | • `districts/investment/vector_finagent/ai_quant_lab/qlib_feature_engineering.py:393` |
| | • `districts/investment/vector_finagent/agents/rdagents/mcp_server.py:387` |
| | • `districts/investment/vector_finagent/agents/finagent_core/execution_planner.py:421` |
| 2. Dynamic imports | ❌ None |
| 3. Manifest references | ❌ N/A (core module, not district agent) |
| 4. Configuration refs | ❌ None |
| 5. CLI references | ❌ None |
| 6. API/router refs | ❌ None (used indirectly through district agents) |
| 7. Plugin/registry refs | ❌ N/A |
| 8. Reflection loading | ❌ None |
| 9. Test references | ✅ `tests/unit/test_security_modules.py` (10+ tests) |
| | ✅ `tests/backend/test_production_honesty.py:114-119` |
| 10. Runtime trace | ✅ Actively used in investment district's quant pipeline |

**All imports are lazy** (`from core.security.safe_eval import safe_eval_expression` inside function bodies) — defensive pattern, not evidence of dead code.

**Correction to audit:** The audit claimed "tests exist, no production use." That was WRONG. Three production callers exist in the FinAgent/quant investment pipeline.

**Verdict:** ALIVE. Deleting would break the investment district's expression evaluation.

---

### 8. `core/security/workspace_audit.py` — ✅ DEFINITELY DEAD

| Check | Result |
|-------|--------|
| 1. Static imports | ❌ None in production code |
| 2. Dynamic imports | ❌ None |
| 3. Manifest references | ❌ NOT in `agent_manifest.yaml` |
| 4. Configuration refs | ❌ None |
| 5. CLI references | ❌ None |
| 6. API/router refs | ❌ None |
| 7. Plugin/registry refs | ❌ None |
| 8. Reflection loading | ❌ None |
| 9. Test references | ⚠️ ONE test: `tests/backend/test_repo_analysis_optional_boundaries.py:8` |
| 10. Runtime trace | ❌ No production use |

**Only references:** Same single test file + audit doc.
**Risk of deletion:** Zero. Test reference must also be removed.

---

## Bonus: Audit also flagged smart_routing/ crypto sub-modules

These were NOT in the original 8 but were flagged in §7 of the audit:

### `core/inference/smart_routing/wallet.py` — ✅ DEFINITELY DEAD
### `core/inference/smart_routing/payment.py` — ✅ DEFINITELY DEAD
### `core/inference/smart_routing/proxy.py` — ✅ DEFINITELY DEAD
### `core/inference/smart_routing/balance.py` — ✅ DEFINITELY DEAD

| Check | Result (all 4) |
|-------|--------|
| 1. Static imports | ❌ No direct production callers use wallet/payment/proxy/balance symbols |
| 2. Dynamic imports | ❌ None |
| 3-8. All other checks | ❌ None |
| 9. Test references | ❌ None |
| 10. Runtime trace | ❌ Never invoked |

**Important nuance:** These modules ARE imported by `core/inference/smart_routing/__init__.py` (lines 50-59), and the `__init__.py` IS imported by `core/inference/route_policy.py:76` (which imports the classifier). So `import core.inference.smart_routing` DOES trigger loading wallet.py, payment.py, proxy.py, and balance.py at module level. However, NONE of the crypto functions (`generate_mnemonic`, `derive_evm_key`, `BalanceMonitor`, `X402Client`, `SmartRoutingProxy`) are ever called.

**Risk of deletion:** Low but non-zero. Must remove from `__init__.py` imports simultaneously. Removing the crypto code from the package init means `from core.inference.smart_routing import *` no longer exposes them. The files themselves can be deleted after the init is cleaned.

---

## Summary Table

| Module | Classification | Delete? | Risk |
|--------|---------------|---------|------|
| `core/brain/self_evolve.py` | DEFINITELY DEAD | ✅ YES | Zero |
| `core/memory/external_mirror.py` | DEFINITELY DEAD | ✅ YES | Zero |
| `core/memory/vector_index_gate.py` | DEFINITELY DEAD | ✅ YES | Zero |
| `districts/personal_growth/zk_steward.py` | DYNAMICALLY REACHABLE | ❌ NO | Breaks manifest |
| `districts/personal_growth/feedback_synthesizer.py` | DYNAMICALLY REACHABLE | ❌ NO | Breaks manifest |
| `districts/data_analytics/performance_optimizer.py` | DYNAMICALLY REACHABLE | ❌ NO | Breaks manifest |
| `core/security/safe_eval.py` | ALIVE (3 production callers) | ❌ NO | Breaks investment district |
| `core/security/workspace_audit.py` | DEFINITELY DEAD | ✅ YES | Zero |
| `core/inference/smart_routing/wallet.py` | DEFINITELY DEAD | ✅ YES | Low (init cleanup needed) |
| `core/inference/smart_routing/payment.py` | DEFINITELY DEAD | ✅ YES | Low (init cleanup needed) |
| `core/inference/smart_routing/proxy.py` | DEFINITELY DEAD | ✅ YES | Low (init cleanup needed) |
| `core/inference/smart_routing/balance.py` | DEFINITELY DEAD | ✅ YES | Low (init cleanup needed) |

### Audit Corrections

The original audit had 2 factual errors:

1. **`safe_eval.py`** was classified "tests exist, no production use" — WRONG. 3 production callers in the FinAgent investment pipeline.
2. **`performance_optimizer.py`** was classified "not in governor routing" — WRONG. Governor maps "optimize"/"profile"/"bottleneck" → `data_analytics` district.

---

## Deletion Plan

### Phase 1: Delete DEFINITELY DEAD modules (zero risk)

**Files to delete:**
```
core/brain/self_evolve.py
core/memory/external_mirror.py
core/memory/vector_index_gate.py
core/security/workspace_audit.py
```

**Test cleanup required:**
```
tests/backend/test_repo_analysis_optional_boundaries.py
  → Remove lines 6-8 (imports of external_mirror, vector_index_gate, workspace_audit)
  → Remove test functions: test_external_mirror_*, test_vector_index_gate_*, test_workspace_audit_*
```

### Phase 2: Delete dead crypto sub-modules (low risk)

**Files to delete:**
```
core/inference/smart_routing/wallet.py
core/inference/smart_routing/payment.py
core/inference/smart_routing/proxy.py
core/inference/smart_routing/balance.py
```

**Init cleanup required:**
```
core/inference/smart_routing/__init__.py
  → Remove lines 50-59 (wallet, balance, payment, proxy imports)
  → Remove corresponding __all__ entries (lines 74-88)
```

### Phase 3: Documentation cleanup

```
docs/manifest_gap.md
  → Remove entries for deleted modules (lines 93, 262, 263)
  → Keep entries for zk_steward, feedback_synthesizer, performance_optimizer (still alive)
```

---

## Rollback Instructions

If any deletion causes issues, all files can be restored from git:

```bash
# Rollback Phase 1
git checkout HEAD~1 -- core/brain/self_evolve.py
git checkout HEAD~1 -- core/memory/external_mirror.py
git checkout HEAD~1 -- core/memory/vector_index_gate.py
git checkout HEAD~1 -- core/security/workspace_audit.py
git checkout HEAD~1 -- tests/backend/test_repo_analysis_optional_boundaries.py

# Rollback Phase 2
git checkout HEAD~1 -- core/inference/smart_routing/wallet.py
git checkout HEAD~1 -- core/inference/smart_routing/payment.py
git checkout HEAD~1 -- core/inference/smart_routing/proxy.py
git checkout HEAD~1 -- core/inference/smart_routing/balance.py
git checkout HEAD~1 -- core/inference/smart_routing/__init__.py
```

**Pre-deletion safety step:** Commit all current work before starting. Create a single commit per phase so rollback is clean.

---

## Modules NOT to Delete (with rationale)

| Module | Why it stays |
|--------|-------------|
| `zk_steward.py` | Manifest-registered, instantiated at runtime, governor routes to its district |
| `feedback_synthesizer.py` | Manifest-registered, instantiated at runtime, governor routes to its district |
| `performance_optimizer.py` | Manifest-registered, instantiated at runtime, governor routes to its district |
| `safe_eval.py` | 3 production callers in FinAgent investment pipeline |

For the 3 manifest-registered agents (zk_steward, feedback_synthesizer, performance_optimizer): if you determine they're never actually dispatched to, the correct action is to either (a) wire them up, or (b) remove them from `agent_manifest.yaml` first, THEN delete. Never delete a manifest-registered agent without removing the manifest entry.

---

## Verification After Deletion

After each phase, run:
```bash
python scripts/smoke_test.py          # 38/38 must pass
python scripts/integration_check.py   # 51/51 must pass
python -m pytest tests/ -x -q        # All tests must pass
python run_vector.py --smoke          # Bootstrap must succeed
```

If any test fails, check if it imports a deleted module. If yes, remove the import or the test.
