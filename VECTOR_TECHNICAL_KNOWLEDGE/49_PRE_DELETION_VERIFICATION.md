# VECTOR Technical Knowledge #49 — Pre-Deletion Verification

**Date:** 2026-08-13
**Preceded by:** #46 Cognitive Integration Audit (identified 8 dead code candidates)
**Status:** VERIFICATION COMPLETE — awaiting owner decision
**Scope:** 12-point reachability verification for 12 modules (8 original + 4 smart_routing crypto)

---

## Executive Summary

12-point reachability verification performed on all 12 proposed deletion candidates.
Results confirm the prior audit with **2 corrections** and **3 reclassifications**.

| Classification | Count | Modules |
|---------------|-------|---------|
| **DEFINITELY DEAD** | 8 | self_evolve, external_mirror, vector_index_gate, workspace_audit, wallet, payment, proxy, balance |
| **DYNAMICALLY REACHABLE** | 3 | zk_steward, feedback_synthesizer, performance_optimizer |
| **ALIVE** | 1 | safe_eval |

**Recommendation:** Phase 1 deletion (8 DEFINITELY DEAD modules) is safe to proceed after cleanup. The 3 DYNAMICALLY REACHABLE modules and 1 ALIVE module must NOT be deleted.

---

## Verification Method — 12 Checks

| # | Check | What it catches |
|---|-------|----------------|
| 1 | Static imports | `import X` / `from X import Y` in any `.py` file |
| 2 | Dynamic imports | `importlib.import_module("X")` |
| 3 | `__init__.py` imports | Parent package `__init__.py` re-exporting the module |
| 4 | Manifest references | `config/agent_manifest.yaml` class entries |
| 5 | Registry references | `AgentRegistry.register()` or `get_registry()` calls |
| 6 | Configuration references | `core/config.py`, `.env`, YAML config files |
| 7 | CLI/API references | `scripts/`, `run_vector.py`, `core/api/routers/` |
| 8 | Plugin references | Plugin loading, hook configs, capability routing |
| 9 | Reflection/string-based | `eval()`, `__import__()`, string class paths in YAML/JSON |
| 10 | Test references | `tests/` files importing the module |
| 11 | Runtime bootstrap | `bootstrap_agents()`, `run_loop()`, `ManifestLoader` |
| 12 | Package init side effects | Does `__init__.py` execution import this module? |

---

## Module 1: `core/brain/self_evolve.py`

```
DELETION CONFIDENCE: 100/100
```

| Check | Result | Detail |
|-------|--------|--------|
| 1. Static imports | ❌ NONE | No `import self_evolve` or `from core.brain.self_evolve` in any file |
| 2. Dynamic imports | ❌ NONE | No `importlib.import_module("core.brain.self_evolve")` |
| 3. `__init__.py` imports | ❌ NONE | No `core/brain/__init__.py` exists (namespace package) |
| 4. Manifest references | ❌ NONE | Not in `agent_manifest.yaml` |
| 5. Registry references | ❌ NONE | Never registered in AgentRegistry |
| 6. Configuration refs | ❌ NONE | Not in config.py, .env, or any YAML |
| 7. CLI/API refs | ❌ NONE | Not referenced by any script or router |
| 8. Plugin refs | ❌ NONE | Not in any plugin/hook config |
| 9. Reflection loading | ❌ NONE | No string-based class path references |
| 10. Test references | ❌ NONE | No test file imports it |
| 11. Bootstrap refs | ❌ NONE | Not in bootstrap path |
| 12. Package init effects | ❌ NONE | No parent `__init__.py` to trigger |

**Known callers:** None
**Known imports:** None
**Dynamic references:** None
**Side effects:** None
**Required cleanup:** None
**Regression risk:** ZERO

**Documentation references only (non-blocking):**
- `VECTOR_TECHNICAL_KNOWLEDGE/45_JARVIS_GAP_ANALYSIS.md` — mentions SelfEvolver
- `VECTOR_TECHNICAL_KNOWLEDGE/46_COGNITIVE_INTEGRATION_AUDIT.md` — lists for deletion

**Verdict:** DEFINITELY DEAD. Safe to delete. No cleanup required.

---

## Module 2: `core/memory/external_mirror.py`

```
DELETION CONFIDENCE: 100/100
```

| Check | Result | Detail |
|-------|--------|--------|
| 1. Static imports | ❌ NONE in production | Only imported in test file |
| 2. Dynamic imports | ❌ NONE | |
| 3. `__init__.py` imports | ❌ NONE | No `core/memory/__init__.py` exists |
| 4. Manifest references | ❌ NONE | Not in `agent_manifest.yaml` |
| 5. Registry references | ❌ NONE | |
| 6. Configuration refs | ❌ NONE | |
| 7. CLI/API refs | ❌ NONE | |
| 8. Plugin refs | ❌ NONE | |
| 9. Reflection loading | ❌ NONE | |
| 10. Test references | ⚠️ 1 TEST | `tests/backend/test_repo_analysis_optional_boundaries.py:6,35-40` |
| 11. Bootstrap refs | ❌ NONE | |
| 12. Package init effects | ❌ NONE | |

**Known callers:** None (production)
**Known imports:**
- `tests/backend/test_repo_analysis_optional_boundaries.py:6` — `from core.memory.external_mirror import ExternalMemoryMirror`

**Dynamic references:** None
**Side effects:** None
**Required cleanup:**
- Delete `tests/backend/test_repo_analysis_optional_boundaries.py` lines 6 and 35-40 (import + test function `test_external_memory_mirror_disabled_returns_disabled`)

**Regression risk:** ZERO

**Security note:** `VECTOR_TECHNICAL_KNOWLEDGE/44_UNRESOLVED_SYSTEM_QUESTIONS.md` flagged "external_mirror" as a potential data exfiltration vector — module name suggests mirroring memory to external store. Deleting removes this risk surface.

**Verdict:** DEFINITELY DEAD. Safe to delete after test cleanup.

---

## Module 3: `core/memory/vector_index_gate.py`

```
DELETION CONFIDENCE: 100/100
```

| Check | Result | Detail |
|-------|--------|--------|
| 1. Static imports | ❌ NONE in production | Only imported in test file |
| 2. Dynamic imports | ❌ NONE | |
| 3. `__init__.py` imports | ❌ NONE | No `core/memory/__init__.py` exists |
| 4. Manifest references | ❌ NONE | |
| 5. Registry references | ❌ NONE | |
| 6. Configuration refs | ❌ NONE | |
| 7. CLI/API refs | ❌ NONE | |
| 8. Plugin refs | ❌ NONE | |
| 9. Reflection loading | ❌ NONE | |
| 10. Test references | ⚠️ 1 TEST | `tests/backend/test_repo_analysis_optional_boundaries.py:7,43-50` |
| 11. Bootstrap refs | ❌ NONE | |
| 12. Package init effects | ❌ NONE | |

**Known callers:** None (production)
**Known imports:**
- `tests/backend/test_repo_analysis_optional_boundaries.py:7` — `from core.memory.vector_index_gate import decide_vector_index_backend`

**Dynamic references:** None
**Side effects:** None
**Required cleanup:**
- Delete `tests/backend/test_repo_analysis_optional_boundaries.py` lines 7 and 43-50 (import + test function `test_vector_index_gate_defers_turbovec_below_threshold`)

**Regression risk:** ZERO

**Verdict:** DEFINITELY DEAD. Safe to delete after test cleanup.

---

## Module 4: `core/security/workspace_audit.py`

```
DELETION CONFIDENCE: 100/100
```

| Check | Result | Detail |
|-------|--------|--------|
| 1. Static imports | ❌ NONE in production | Only imported in test file |
| 2. Dynamic imports | ❌ NONE | |
| 3. `__init__.py` imports | ❌ NONE | No `core/security/__init__.py` exists |
| 4. Manifest references | ❌ NONE | |
| 5. Registry references | ❌ NONE | |
| 6. Configuration refs | ❌ NONE | |
| 7. CLI/API refs | ❌ NONE | |
| 8. Plugin refs | ❌ NONE | |
| 9. Reflection loading | ❌ NONE | |
| 10. Test references | ⚠️ 1 TEST | `tests/backend/test_repo_analysis_optional_boundaries.py:8,91-103` |
| 11. Bootstrap refs | ❌ NONE | |
| 12. Package init effects | ❌ NONE | |

**Known callers:** None (production)
**Known imports:**
- `tests/backend/test_repo_analysis_optional_boundaries.py:8` — `from core.security.workspace_audit import audit_hook_configs, audit_skill_inventory`

**Dynamic references:** None
**Side effects:** None
**Required cleanup:**
- Delete `tests/backend/test_repo_analysis_optional_boundaries.py` lines 8 and 91-103 (import + test function `test_workspace_audit_skill_inventory_and_hook_review`)

**Regression risk:** ZERO

**Verdict:** DEFINITELY DEAD. Safe to delete after test cleanup.

---

## Module 5: `districts/personal_growth/zk_steward.py`

```
DELETION CONFIDENCE: 0/100 — DO NOT DELETE
```

| Check | Result | Detail |
|-------|--------|--------|
| 1. Static imports | ❌ None (lazy-loaded) | |
| 2. Dynamic imports | ✅ MANIFEST | `ManifestLoader.instantiate_all()` → `importlib.import_module("districts.personal_growth.zk_steward")` |
| 3. `__init__.py` imports | ❌ NONE | No `districts/personal_growth/__init__.py` re-exports it |
| 4. Manifest references | ✅ YES | `agent_manifest.yaml:1130-1131` — `class: districts.personal_growth.zk_steward.ZKSteward` |
| 5. Registry references | ✅ YES | Registered via `bootstrap_agents()` → `ManifestLoader.register_all()` |
| 6. Configuration refs | ❌ NONE | |
| 7. CLI/API refs | ❌ NONE | |
| 8. Plugin refs | ✅ PROMPT | `core/prompt_library.py:89` — `"zk_steward": "zk-steward"` |
| 9. Reflection loading | ✅ MANIFEST | String class path in YAML → `importlib.import_module()` |
| 10. Test references | ❌ NONE | |
| 11. Bootstrap refs | ✅ YES | `run_vector.py:155` → `bootstrap_agents()` → loads from manifest |
| 12. Package init effects | ❌ NONE | |

**Known callers:** Governor dispatches to `personal_growth` district on keywords: "zettelkasten", "zk", "knowledge_links"
**Known imports:** ManifestLoader (dynamic)
**Dynamic references:** agent_manifest.yaml, prompt_library.py, phase_status.md, 5 inventory docs
**Side effects:** Instantiated at every VECTOR startup. Removing would reduce agent count by 1 (manifest skips on import failure — no crash, but silently loses the agent).
**Required cleanup if removed:** Must remove manifest entry (line 1130-1134), prompt_library entry (line 89), and update all documentation.
**Regression risk:** HIGH if deleted without manifest cleanup. MEDIUM if manifest entry removed first.

**Verdict:** DYNAMICALLY REACHABLE. Do NOT delete.

---

## Module 6: `districts/personal_growth/feedback_synthesizer.py`

```
DELETION CONFIDENCE: 0/100 — DO NOT DELETE
```

| Check | Result | Detail |
|-------|--------|--------|
| 1. Static imports | ❌ None (lazy-loaded) | |
| 2. Dynamic imports | ✅ MANIFEST | `importlib.import_module("districts.personal_growth.feedback_synthesizer")` |
| 3. `__init__.py` imports | ❌ NONE | |
| 4. Manifest references | ✅ YES | `agent_manifest.yaml:1124-1125` — `class: districts.personal_growth.feedback_synthesizer.FeedbackSynthesizer` |
| 5. Registry references | ✅ YES | Registered via `bootstrap_agents()` |
| 6. Configuration refs | ❌ NONE | |
| 7. CLI/API refs | ❌ NONE | |
| 8. Plugin refs | ✅ PROMPT | `core/prompt_library.py:88` — `"feedback_synthesizer": "product-feedback-synthesizer"` |
| 9. Reflection loading | ✅ MANIFEST | String class path → `importlib.import_module()` |
| 10. Test references | ❌ NONE | |
| 11. Bootstrap refs | ✅ YES | `run_vector.py:155` → `bootstrap_agents()` |
| 12. Package init effects | ❌ NONE | |

**Known callers:** Governor dispatches to `personal_growth` on keywords: "feedback", "synthesize_feedback"
**Known imports:** ManifestLoader (dynamic)
**Dynamic references:** agent_manifest.yaml, prompt_library.py, 5 inventory docs
**Side effects:** Instantiated at every startup. Same risk profile as zk_steward.
**Required cleanup if removed:** Manifest entry (line 1124-1128), prompt_library entry (line 88), documentation.
**Regression risk:** HIGH if deleted without manifest cleanup.

**Verdict:** DYNAMICALLY REACHABLE. Do NOT delete.

---

## Module 7: `districts/data_analytics/performance_optimizer.py`

```
DELETION CONFIDENCE: 0/100 — DO NOT DELETE
```

| Check | Result | Detail |
|-------|--------|--------|
| 1. Static imports | ❌ None (lazy-loaded) | |
| 2. Dynamic imports | ✅ MANIFEST | `importlib.import_module("districts.data_analytics.performance_optimizer")` |
| 3. `__init__.py` imports | ❌ NONE | |
| 4. Manifest references | ✅ YES | `agent_manifest.yaml:596-597` — `class: districts.data_analytics.performance_optimizer.PerformanceOptimizer` |
| 5. Registry references | ✅ YES | Registered via `bootstrap_agents()` |
| 6. Configuration refs | ❌ NONE | |
| 7. CLI/API refs | ❌ NONE | |
| 8. Plugin refs | ❌ NONE | No prompt_library entry |
| 9. Reflection loading | ✅ MANIFEST | String class path → `importlib.import_module()` |
| 10. Test references | ❌ NONE | |
| 11. Bootstrap refs | ✅ YES | `run_vector.py:155` → `bootstrap_agents()` |
| 12. Package init effects | ❌ NONE | |

**Known callers:** Governor dispatches to `data_analytics` on keywords: "optimize", "profile", "bottleneck", "performance_report"
**Known imports:** ManifestLoader (dynamic)
**Dynamic references:** agent_manifest.yaml, docs/manifest_gap.md
**Side effects:** Instantiated at every startup.
**Required cleanup if removed:** Manifest entry (line 596-600), documentation.
**Regression risk:** HIGH if deleted without manifest cleanup.

**AUDIT CORRECTION:** The #46 audit classified this as "not in governor routing." This was INCORRECT. Governor explicitly maps:
```python
"optimize": "data_analytics",      # line 1104
"profile": "data_analytics",       # line 1105
"bottleneck": "data_analytics",    # line 1106
```

**Verdict:** DYNAMICALLY REACHABLE. Do NOT delete.

---

## Module 8: `core/security/safe_eval.py`

```
DELETION CONFIDENCE: 0/100 — DO NOT DELETE (ALIVE)
```

| Check | Result | Detail |
|-------|--------|--------|
| 1. Static imports | ✅ 3 PRODUCTION CALLERS | See below |
| 2. Dynamic imports | ❌ NONE | |
| 3. `__init__.py` imports | ❌ NONE | No `core/security/__init__.py` exists |
| 4. Manifest references | ❌ N/A | Core module, not district agent |
| 5. Registry references | ❌ N/A | |
| 6. Configuration refs | ❌ NONE | |
| 7. CLI/API refs | ❌ NONE | |
| 8. Plugin refs | ❌ NONE | |
| 9. Reflection loading | ❌ NONE | |
| 10. Test references | ✅ 2 TEST FILES | `test_security_modules.py`, `test_production_honesty.py` |
| 11. Bootstrap refs | ❌ N/A | |
| 12. Package init effects | ❌ NONE | |

**Known callers (3 production):**
```python
# 1. districts/investment/vector_finagent/ai_quant_lab/qlib_feature_engineering.py:393
from core.security.safe_eval import safe_eval_expression

# 2. districts/investment/vector_finagent/agents/rdagents/mcp_server.py:387
from core.security.safe_eval import safe_eval_expression

# 3. districts/investment/vector_finagent/agents/finagent_core/execution_planner.py:421
from core.security.safe_eval import safe_eval_expression
```

**Known imports (2 test files):**
```python
# tests/unit/test_security_modules.py:7
from core.security.safe_eval import safe_eval_expression

# tests/backend/test_production_honesty.py:114
from core.security.safe_eval import UnsafeExpressionError, safe_eval_expression
```

**Dynamic references:** None
**Side effects:** All 3 production imports are LAZY (inside function bodies) — defensive pattern, not evidence of dead code.
**Required cleanup if removed:** Would break 3 production files + 2 test files. Entire FinAgent expression evaluation pipeline would fail.
**Regression risk:** CRITICAL. Deleting would break the investment district.

**AUDIT CORRECTION:** The #46 audit classified this as "tests exist, no production use." This was INCORRECT. Three active production callers exist in the FinAgent quantitative finance pipeline.

**Verdict:** ALIVE. Must NOT be deleted.

---

## SPECIAL CASE: Smart Routing Crypto Sub-Modules

### Import Chain Trace

```
core/inference/route_policy.py:76
    │
    │  from core.inference.smart_routing.classifier import classify
    │
    ▼
Python imports package: core.inference.smart_routing
    │
    ▼
Executes: core/inference/smart_routing/__init__.py
    │
    ├──▶ line 38-41:  from .classifier import ...        ✅ ACTIVE (used by route_policy)
    ├──▶ line 42-46:  from .model_catalog import ...      ✅ ACTIVE (used by proxy, stats)
    ├──▶ line 47:     from .compressor import ...         ✅ ACTIVE
    ├──▶ line 48:     from .request_cache import ...      ✅ ACTIVE
    ├──▶ line 49:     from .fallback_chain import ...     ✅ ACTIVE
    ├──▶ line 50-53:  from .wallet import ...             ❌ DEAD (crypto, never called)
    ├──▶ line 54:     from .balance import ...            ❌ DEAD (crypto, never called)
    ├──▶ line 55:     from .payment import ...            ❌ DEAD (crypto, never called)
    ├──▶ line 56:     from .stats import ...              ✅ ACTIVE
    ├──▶ line 57:     from .response_store import ...     ✅ ACTIVE
    ├──▶ line 58:     from .partners import ...           ✅ ACTIVE
    └──▶ line 59:     from .proxy import ...              ❌ DEAD (never called)
```

### Critical Finding: Package Initialization Side Effect

**ANY import from `core.inference.smart_routing` triggers `__init__.py` execution.**

Python's import system ALWAYS executes `__init__.py` when any submodule is imported. This means:

```python
# route_policy.py does this:
from core.inference.smart_routing.classifier import classify

# Python resolves this by:
# 1. Loading core.inference package
# 2. Loading core.inference.smart_routing package → EXECUTES __init__.py
# 3. Loading core.inference.smart_routing.classifier module
# 4. Importing 'classify' from it
```

**Step 2 loads ALL imports in `__init__.py`**, including wallet.py, balance.py, payment.py, and proxy.py.

**External callers of `from core.inference.smart_routing import ...`:**

| Caller | What it imports | File |
|--------|----------------|------|
| `core/inference/route_policy.py:76` | `classify` (from `.classifier` submodule) | Triggers `__init__.py` |
| `core/inference/smart_routing/stats.py:106` | `get_model` (from `.model_catalog` submodule) | Internal, already inside package |

**No external code imports wallet/payment/proxy/balance symbols.** The only callers of the package are `route_policy.py` (classifier only) and internal cross-references.

---

### Module 9: `core/inference/smart_routing/wallet.py`

```
DELETION CONFIDENCE: 95/100
```

| Check | Result | Detail |
|-------|--------|--------|
| 1. Static imports | ❌ NONE externally | Only imported by `__init__.py` |
| 2. Dynamic imports | ❌ NONE | |
| 3. `__init__.py` imports | ⚠️ YES | `__init__.py:50-53` — `from .wallet import (generate_mnemonic, validate_mnemonic, derive_evm_key, derive_solana_key_bytes, derive_all_keys, ensure_wallet, DerivedKeys)` |
| 4. Manifest references | ❌ NONE | |
| 5. Registry references | ❌ NONE | |
| 6. Configuration refs | ❌ NONE | |
| 7. CLI/API refs | ❌ NONE | |
| 8. Plugin refs | ❌ NONE | |
| 9. Reflection loading | ❌ NONE | |
| 10. Test references | ❌ NONE | |
| 11. Bootstrap refs | ❌ NONE | |
| 12. Package init effects | ⚠️ YES | Loaded at package init via `__init__.py`. Removing file WITHOUT cleaning `__init__.py` will BREAK all smart_routing imports (including route_policy.py's classifier). |

**Known callers:** None (wallet functions never called by any production code)
**Known imports:** `__init__.py` only
**Dynamic references:** None
**Side effects:**
- If file deleted but `__init__.py` NOT cleaned → `ImportError` on ANY smart_routing import → route_policy.py classifier breaks → routing falls back to heuristic (line 83: `"COMPLEX" if len(prompt.split()) > 200 else "MEDIUM"`)
- If file deleted AND `__init__.py` cleaned → no impact on any production code

**Required cleanup:**
1. Remove lines 50-53 from `__init__.py` (wallet imports)
2. Remove `__all__` entries: lines 75-76 (`"generate_mnemonic"`, `"validate_mnemonic"`, `"derive_evm_key"`, `"derive_solana_key_bytes"`, `"derive_all_keys"`, `"ensure_wallet"`, `"DerivedKeys"`)
3. Then delete `wallet.py`

**Regression risk:** LOW if `__init__.py` cleaned first. HIGH if file deleted without cleaning init.

---

### Module 10: `core/inference/smart_routing/balance.py`

```
DELETION CONFIDENCE: 95/100
```

| Check | Result | Detail |
|-------|--------|--------|
| 1. Static imports | ❌ NONE externally | Only `__init__.py:54` |
| 2-11. All other checks | ❌ NONE | |
| 12. Package init effects | ⚠️ YES | `__init__.py:54` — `from .balance import BalanceMonitor, BalanceSufficiency` |

**Known callers:** None
**Required cleanup:**
1. Remove line 54 from `__init__.py`
2. Remove `__all__` entries: lines 78-79 (`"BalanceMonitor"`, `"BalanceSufficiency"`)
3. Then delete `balance.py`

**Regression risk:** LOW if cleaned first.

---

### Module 11: `core/inference/smart_routing/payment.py`

```
DELETION CONFIDENCE: 95/100
```

| Check | Result | Detail |
|-------|--------|--------|
| 1. Static imports | ❌ NONE externally | Only `__init__.py:55` |
| 2-11. All other checks | ❌ NONE | |
| 12. Package init effects | ⚠️ YES | `__init__.py:55` — `from .payment import X402Client, PaymentDetails` |

**Known callers:** None
**Required cleanup:**
1. Remove line 55 from `__init__.py`
2. Remove `__all__` entries: lines 80-81 (`"X402Client"`, `"PaymentDetails"`)
3. Then delete `payment.py`

**Regression risk:** LOW if cleaned first.

---

### Module 12: `core/inference/smart_routing/proxy.py`

```
DELETION CONFIDENCE: 95/100
```

| Check | Result | Detail |
|-------|--------|--------|
| 1. Static imports | ❌ NONE externally | Only `__init__.py:59` |
| 2-11. All other checks | ❌ NONE | |
| 12. Package init effects | ⚠️ YES | `__init__.py:59` — `from .proxy import SmartRoutingProxy` |

**Internal cross-references within proxy.py:**
```python
proxy.py:33-38 — imports from classifier, model_catalog, compressor, request_cache, fallback_chain, stats
proxy.py:124  — imports from model_catalog (estimate_cost, baseline_cost)
proxy.py:188  — imports from model_catalog (MODEL_CATALOG)
```

These are INTERNAL to the smart_routing package. proxy.py uses other smart_routing modules, but NO external code uses proxy.py.

**Known callers:** None
**Required cleanup:**
1. Remove line 59 from `__init__.py`
2. Remove `__all__` entry: line 89 (`"SmartRoutingProxy"`)
3. Then delete `proxy.py`

**Regression risk:** LOW if cleaned first.

---

## Cleanup Manifest

### Test File: `tests/backend/test_repo_analysis_optional_boundaries.py`

This file imports 3 of the 4 DEFINITELY DEAD core modules. It must be edited, NOT deleted (it also tests booking, whatsapp, order_lifecycle, evolution_audit, and supertonic which are alive).

**Lines to remove:**
```python
# Line 6:
from core.memory.external_mirror import ExternalMemoryMirror

# Line 7:
from core.memory.vector_index_gate import decide_vector_index_backend

# Line 8:
from core.security.workspace_audit import audit_hook_configs, audit_skill_inventory

# Lines 35-40 (test_external_memory_mirror_disabled_returns_disabled):
@pytest.mark.asyncio
async def test_external_memory_mirror_disabled_returns_disabled():
    mirror = ExternalMemoryMirror()
    result = await mirror.mirror_chunk("c1", "memory text")
    assert result["status"] == "disabled"
    assert result["provider"] == "helixdb"

# Lines 43-50 (test_vector_index_gate_defers_turbovec_below_threshold):
def test_vector_index_gate_defers_turbovec_below_threshold():
    small = decide_vector_index_backend(10_000, configured_backend="turbovec")
    large = decide_vector_index_backend(1_500_000, configured_backend="turbovec")
    assert small.should_enable is False
    assert small.backend == "nanovectordb"
    assert large.should_enable is True
    assert large.backend == "turbovec"

# Lines 91-103 (test_workspace_audit_skill_inventory_and_hook_review):
def test_workspace_audit_skill_inventory_and_hook_review(tmp_path):
    ...
```

**Lines to keep:** Lines 1-5, 9-12 (imports), 15-33, 53-89, 106-110 (other tests).

### Package Init: `core/inference/smart_routing/__init__.py`

**Lines to remove:**
```python
# Lines 50-53 (wallet):
from core.inference.smart_routing.wallet import (
    generate_mnemonic, validate_mnemonic, derive_evm_key,
    derive_solana_key_bytes, derive_all_keys, ensure_wallet, DerivedKeys,
)

# Line 54 (balance):
from core.inference.smart_routing.balance import BalanceMonitor, BalanceSufficiency

# Line 55 (payment):
from core.inference.smart_routing.payment import X402Client, PaymentDetails

# Line 59 (proxy):
from core.inference.smart_routing.proxy import SmartRoutingProxy
```

**`__all__` entries to remove (lines 74-89):**
```python
    # Wallet
    "generate_mnemonic", "validate_mnemonic", "derive_evm_key",
    "derive_solana_key_bytes", "derive_all_keys", "ensure_wallet", "DerivedKeys",
    # Balance
    "BalanceMonitor", "BalanceSufficiency",
    # Payment
    "X402Client", "PaymentDetails",
    # Proxy
    "SmartRoutingProxy",
```

**Lines to keep:** All other imports (classifier, model_catalog, compressor, request_cache, fallback_chain, stats, response_store, partners) and their `__all__` entries.

---

## Execution Order

### Phase 1: Core dead modules (zero risk)

```
Step 1: Edit tests/backend/test_repo_analysis_optional_boundaries.py
        → Remove 3 imports (lines 6-8) and 3 test functions
Step 2: Delete core/brain/self_evolve.py
Step 3: Delete core/memory/external_mirror.py
Step 4: Delete core/memory/vector_index_gate.py
Step 5: Delete core/security/workspace_audit.py
Step 6: Run verification (see below)
```

### Phase 2: Crypto dead modules (low risk — init cleanup required)

```
Step 1: Edit core/inference/smart_routing/__init__.py
        → Remove wallet/balance/payment/proxy imports (lines 50-55, 59)
        → Remove corresponding __all__ entries
Step 2: Delete core/inference/smart_routing/wallet.py
Step 3: Delete core/inference/smart_routing/balance.py
Step 4: Delete core/inference/smart_routing/payment.py
Step 5: Delete core/inference/smart_routing/proxy.py
Step 6: Run verification (see below)
```

### Post-Deletion Verification

```bash
# 1. Syntax check — all modified files parse
python -c "import py_compile; py_compile.compile('core/inference/smart_routing/__init__.py', doraise=True)"
python -c "import py_compile; py_compile.compile('tests/backend/test_repo_analysis_optional_boundaries.py', doraise=True)"

# 2. Import check — route_policy still works after smart_routing cleanup
python -c "from core.inference.route_policy import decide_route; print('route_policy OK')"

# 3. Smoke test
python scripts/smoke_test.py

# 4. Integration check
python scripts/integration_check.py

# 5. Full test suite
python -m pytest tests/ -x -q

# 6. Bootstrap verification
python run_vector.py --smoke
```

---

## Rollback

```bash
# Per-phase rollback (each phase should be a separate commit)

# Phase 1 rollback:
git checkout HEAD~1 -- core/brain/self_evolve.py
git checkout HEAD~1 -- core/memory/external_mirror.py
git checkout HEAD~1 -- core/memory/vector_index_gate.py
git checkout HEAD~1 -- core/security/workspace_audit.py
git checkout HEAD~1 -- tests/backend/test_repo_analysis_optional_boundaries.py

# Phase 2 rollback:
git checkout HEAD~1 -- core/inference/smart_routing/wallet.py
git checkout HEAD~1 -- core/inference/smart_routing/balance.py
git checkout HEAD~1 -- core/inference/smart_routing/payment.py
git checkout HEAD~1 -- core/inference/smart_routing/proxy.py
git checkout HEAD~1 -- core/inference/smart_routing/__init__.py
```

---

## Modules NOT to Delete (Summary)

| Module | Confidence | Reason |
|--------|-----------|--------|
| `zk_steward.py` | 0/100 | Manifest-registered, runtime-instantiated, governor routes to district |
| `feedback_synthesizer.py` | 0/100 | Manifest-registered, runtime-instantiated, governor routes to district |
| `performance_optimizer.py` | 0/100 | Manifest-registered, runtime-instantiated, governor routes to district |
| `safe_eval.py` | 0/100 | 3 active production callers in FinAgent investment pipeline |

---

## Audit Corrections (Permanent Record)

The #46 Cognitive Integration Audit contained 2 factual errors, corrected here:

1. **`safe_eval.py`** — Audit said "tests exist, no production use." CORRECTION: 3 production callers exist in the FinAgent investment pipeline (`qlib_feature_engineering.py:393`, `rdagents/mcp_server.py:387`, `finagent_core/execution_planner.py:421`). All are lazy imports inside function bodies.

2. **`performance_optimizer.py`** — Audit said "not in governor routing." CORRECTION: Governor explicitly maps "optimize" → data_analytics (line 1104), "profile" → data_analytics (line 1105), "bottleneck" → data_analytics (line 1106). The agent IS reachable via district dispatch.

---

## Final Recommendation

**Phase 1 (core dead modules): SAFE TO PROCEED.** All 4 modules have zero production callers, zero manifest entries, zero bootstrap references, zero `__init__.py` dependencies. Risk is zero. Only cleanup required is removing 3 imports + 3 test functions from one test file.

**Phase 2 (crypto modules): SAFE TO PROCEED WITH CAUTION.** All 4 modules have zero production callers. However, they are imported by `smart_routing/__init__.py`, which is executed on every smart_routing package import. The `__init__.py` MUST be cleaned BEFORE deleting the files, or route_policy.py's classifier import will break.

**Phases 3+ (manifest-registered agents): NOT RECOMMENDED.** These 3 agents are dynamically reachable via the manifest loading path. If determined to be unused, the correct approach is to first remove them from `agent_manifest.yaml`, run VECTOR to verify no regression, then delete the files in a subsequent commit.

**safe_eval.py: MUST NOT BE DELETED.** Active production module with 3 callers.

---

*Verification completed 2026-08-13. No files were modified or deleted during this verification.*
