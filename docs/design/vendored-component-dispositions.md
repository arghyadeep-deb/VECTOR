# Vendored Component Dispositions — Input for an Owner Decision

**Gap 6 of the post-audit improvement plan. This is a RECOMMENDATION
document, not a decision — the owner still needs to choose a disposition
per component. No code has been changed, moved, or deleted as part of
producing this file. Closure type stays "accepted" in `docs/design/gap-register.md`
until the owner actually picks dispositions and they're executed.**

## The four dispositions (Codex's round-3 refinement, converged)

1. **Remove or replace** if unused — closes the risk outright, at the cost
   of losing whatever functionality it provided.
2. **Treat as a pinned external dependency** — provenance, license record,
   and an update/vulnerability-monitoring policy, with NO line-by-line
   reading required. Correct for large, stable, infrequently-touched trees.
3. **Reachability/privilege-boundary review + runtime tests** — the
   standing "wiring-check" tier this cycle already used: verify VECTOR's
   own real call sites into the component, not every internal line.
4. **Commission full-depth review** — only for exceptionally critical
   components where the blast radius of a hidden bug is severe enough to
   justify the cost (this is the most expensive option and should be rare).

## Components with an existing NOTICE.md (confirmed vendored, checked 2026-10-07)

| Component | Files | Upstream (per its own NOTICE.md) | License | VECTOR's real usage | Recommended disposition |
|---|---|---|---|---|---|
| `core/coding_assistant/` | 169 | Unconfirmed coding-CLI agent framework | Unstated | `core.tools.builtins`/`core.hooks.manager`/`core.skills.manager`/`core.paths` only | **(3) Reachability review** — already the standing policy; keep. Advertised `programmatic.py` entrypoint doesn't even import successfully and isn't called — candidate for **(1) remove** if truly dead, worth a quick confirm |
| `core/research_engine/` | 452 | Unconfirmed, possibly `local-deep-research` | Unstated | Selected research utilities via `districts/research/research_api.py` | **(3) Reachability review** — standing policy; keep |
| `districts/coding/vector_mlops/` | 73 | Unconfirmed async-agent-loop framework ("LiteLLM") | Unstated | Selected agent tools (dataset inspection, GitHub examples, HF jobs, planning) — already got a FULL audit this cycle (item 124, commit `63d7a6e44`), not just wiring-check | Already de-facto **(4) full-depth done** — the register should reflect this is NOT at the standard wiring-check tier anymore; it got full treatment and found real bugs (OAuth CSRF, keyring bypasses, CWE-22). **Recommend formally upgrading this component's tier to (4)/full-depth in policy, matching what already happened in practice** |
| `districts/intelligence/shadowbroker_server/` | 439 | `"backend"` v0.9.79, FastAPI | Unstated | VECTOR starts its `main.py` as a subprocess + proxies to it | **(3) Reachability review** — standing policy; keep. Given it's a standalone network-facing FastAPI service VECTOR runs as a subprocess, **(2) pinned-dependency-with-monitoring** may actually be more appropriate than (3) if it's never modified locally — worth asking whether this repo ever edits shadowbroker_server's own code or only consumes it as-is |
| `districts/intelligence/vector_social_sim/` | 37 | `mirofish-backend` | **AGPL-3.0** | `districts/intelligence/social_sim_agent.py` wrapper | **(3) Reachability review** — standing policy; keep. AGPL risk already explicitly accepted by the owner (personal use only), recorded separately — this file doesn't re-litigate that |
| `districts/investment/alpha_zoo/` | 465 | Unconfirmed Alpha101/Qlib-style factor library | Unstated | `AlphaZooLoader` utility only | **(2) Pinned external dependency** — 465 files of quant factor definitions that VECTOR only *loads*, never executes arbitrary logic from directly; a provenance+license record is more proportionate than ongoing review |
| `districts/investment/vector_backtest/` | 195 | Unconfirmed standalone backtesting framework | Unstated | `BacktestAgent` imports `AgentLoop`/`ChatLLM`/`build_registry`/`PersistentMemory` | **(3) Reachability review** — standing policy; keep |
| `districts/investment/vector_finagent/` | 1,458 | Fincept Terminal Python scripts | **MIT** | `FinAgentTerminalLauncher`/`CoreAgent`/financial-analysis classes | **(2) Pinned external dependency** — by far the largest vendored tree (1,458 files); MIT-licensed and well-attributed, (3)-tier reachability review of 1,458 files for marginal benefit over a dependency-pin record is likely not worth the cost |

## Components WITHOUT a NOTICE.md — a real gap this document found

| Component | Files | Status | Recommended disposition |
|---|---|---|---|
| `districts/investment/vector_hedgebot/` | 18 | Referenced as vendored in prior session memory, but has no `NOTICE.md` of its own | **Write the NOTICE.md first** (mechanical, same format as the 8 above), THEN pick a disposition — can't honestly recommend one without first establishing upstream/license the way the others did |
| `core/mining/` | 14 | **Inconsistent treatment found**: an earlier session memory note (2026-09-29) classified this as "an already-identified vectorcode port with unclear upstream license, owner accepted personal-use-only risk" (i.e., vendored). But THIS SAME AUDIT CYCLE gave it full-depth treatment (items 109, 120, 127 — real bugs found and fixed in `mining/_abc.py`'s `Sidecar.write()`, among others), the same as hand-written VECTOR code, with no NOTICE.md ever added. **Flagging this discrepancy rather than resolving it unilaterally**: either the 2026-09-29 vendored classification was wrong and this is actually hand-written/ported-with-full-rights code (in which case: write a brief note saying so, no NOTICE.md needed), or it genuinely is vendored with an unclear license (in which case: the full-depth audit work already done should probably not have happened under the stated policy, though reverting it now would be pointless — the fixes are real and good). **Owner call needed on which story is actually true**, not a code change |

## Summary

- **6 of 10 vendored components** (`research_engine`, `shadowbroker_server`,
  `vector_social_sim`, `vector_backtest`) are correctly at the standing
  wiring-check tier already — no change recommended.
- **2 components** (`alpha_zoo`, `vector_finagent`) are large enough and
  narrow-enough-usage that a pinned-dependency record (option 2) is
  probably more proportionate than ongoing reachability review — owner
  call.
- **1 component** (`vector_mlops`) already quietly got full-depth treatment
  this cycle in practice — the policy documentation should catch up to
  what actually happened, not the other way around.
- **2 gaps found** by writing this document: `vector_hedgebot` has no
  NOTICE.md at all (mechanical fix, not yet done); `core/mining/`'s
  vendored-vs-hand-written classification contradicts itself across two
  points in this project's own history — flagged, not resolved here.
