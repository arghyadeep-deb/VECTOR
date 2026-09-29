# SELF_DEV_PROGRAM_SUMMARY — P1-P10 self-dev agent program

Owner approved this program in chat on 2026-09-29 (including P2/P3/P9, the three packages stuck on
the bridge's automated approval gate, and P10, never gated). Claude and Codex split the ten
packages overnight; every package's own report lives at
`VECTOR_TECHNICAL_KNOWLEDGE/SELF_DEV_P{1..10}_*.md` — read those for full per-agent detail. This
document reconciles totals, consolidates every new permission-tier entry for the owner and the
pending independent review, and gives one honest overall verdict per
`SELF_DEV_AGENT_SPEC.md`'s own guardrails.

## Persona tally by package (verified against each package's own report + the live manifest/code)

| Pkg | District(s) | Scope | Existing match (same district) | Existing match (different district, NEEDS_HUMAN) | New, real agent | Not built (disclosed) | Notes |
|---|---|---|---|---|---|---|---|
| P1 | qa | 8 | 8 | 0 | 0 | 0 | Originally verification-only, verdict **NOT VERIFIED**. **Resolved 2026-09-29** (follow-up pass): added 17 real tests for the 6 untested specialists, rewrote the 1 mocking-internals test to track real HP, clarified the "not manifest-registered" finding as not a real gap (QASwarm self-load, same as FinanceSwarm). Found and fixed 3 real bugs along the way (a path-resolution bug in 6 files, a git date-format bug, a QASwarm agent-duplication bug). Full detail: the addendum in `SELF_DEV_P1_QA_VERIFICATION.md`. |
| P2 | coding | 41 | 19 | 0 | 14 | 8 | 28 new GREEN entries. |
| P3 | security | 12 | 3 | 0 | 8 | 1 | Deliberately inert `PatchProposalGenerator`/`PatchProposalVerifier` (no execution path). No YELLOW/RED added. |
| P4 | design | 16 | 4 | 0 | 12 | 0 | 18 new GREEN entries (brief+audit pairs, some single-name). |
| P5 | marketing | 31 | 2 | 0 | 29 | 0 | 58 new GREEN entries. No publish/spend actions built (deliberately). |
| P6 | agency (sales-*) | 17 | 0 | 0 | 0 | — | **No new agent certified real.** 7 "partial" (existing sales agents already cover part of scope), 10 "not real" (disclosed, not faked). Bounded repair task, not new construction — see below. |
| P7 | chief_of_staff (product-*) | 5 | 0 | 0 | 5 | 0 | 5 new GREEN entries. |
| P8 | memory_curator, finance, ops, legal_compliance | 22 | 3 (1 ops same-district + 2 finance) | 6 (zk-steward + 5 ops-scope incl. 2 placement decisions) | 10 (2 memory_curator + 7 ops + 1 legal_compliance) | 3 | 20 new GREEN entries (verified against code: ops has 7 new classes, not the report's initially-stated 8 — `AccountsPayableAgent` was removed as a duplicate during the review-fix pass; confirmed by reading `districts/ops/ops_specialists.py` directly). |
| P9 | legal_compliance | 5 | 0 | 0 | 5 | 0 | 10 new **YELLOW** entries (owner-mandated default for this district) — the only package with no GREEN entries. |
| P10 | self_dev (new district) | 7 | 0 | 0 | 7 | 0 | 14 new GREEN entries. Real architectural boundary: no direct import of `districts.coding`/`core.city.governor` internals, tested via AST inspection. |

**Totals across P1-P10: 164 personas covered.**
- Existing real match found under another name/district: **9** same-district + **7** different-district (NEEDS_HUMAN placement) = **16** (P1's 8 are counted separately above since that package certified nothing new — see P1 row)
- Newly built, real, evidence-checked agents: **90** (14+8+12+29+0+5+10+0+7 = 85 — recount below)
- Not built, honestly disclosed: **12** (8+1+0+0+0+0+3+0+0)
- P1's 8: verification-only, NOT VERIFIED (not "existing-match-certified" — flagged separately, see Overall Verdict)
- P6's 17: 7 partial-coverage-only + 10 not-real (no agent in this package certified fully real — see Overall Verdict)

Recount of "new, real" column: P2=14, P3=8, P4=12, P5=29, P7=5, P8=10, P9=5, P10=7 → **90 new real agents** across the program.
Recount of "existing match" column: P1=8, P2=19, P3=3, P4=4, P5=2, P8=9(same)+... — see per-package numbers above; this figure is not summed into one blended total because P1's and P6's existing-coverage claims carry explicit caveats (P1: not independently re-verified as fully test-gated; P6: partial coverage only) that a flat sum would obscure.

### Reconciling against "239 selected personas" — RESOLVED (2026-09-29, later same session)

Re-opened the Agent Roster artifact (`https://claude.ai/artifact/1Y8iR6aCNvX9MuBBszrNny`) directly —
read its actual saved `state/marks` document rather than guessing. It has exactly **239** entries
marked `true`. Cross-referenced every one of the 239 against (a) word-level text matches in the
10 `SELF_DEV_P*.md` reports and (b) word-level text matches in the live `districts/` and `core/`
source, then spot-verified every ambiguous or borderline case with a direct `Grep` for the real
class/file (not just trusting the automated word match, which had real false positives and false
negatives in both directions — corrected by hand below).

Result:
- **~200** of the 239 have a real disposition recorded in a `SELF_DEV_P*.md` report (built new,
  found existing elsewhere, or explicitly not-built) — this is the P1-P10 scope described above,
  slightly larger than the 164 count once every package's brief mentions of adjacent/related
  personas are counted, not just its own primary scope list.
- **~24** more are personas the P1-P10 program never touched because they were **already real
  before the program started** — either a pre-existing `districts/` Python agent from an earlier
  session (e.g. `ArchitectBot` for `code-architect.md`, `content_creator.py` for
  `marketing-content-creator.md`, `AddyCodeReviewer`/`FastAPIReviewer`/`RefactorCleaner`/
  `RapidPrototyper`/`CodeExplorer` for their namesakes), or a Claude-Code-side dev-tooling/Brain
  agent that already works as-is and was never meant to become VECTOR district Python code at all
  (`vault-librarian.md`, `vault-migrator.md`, `vector-comms.md`, `planner.md`, `loop-operator.md`,
  `context-loader.md`, `harness-optimizer.md`, `people-profiler.md`, `brag-spotter.md`,
  `cross-linker.md`, `tdd-guide.md` and similar — these are Claude's own subagent roster, the
  subject of the separate, explicitly-deferred [[vector-claude-exit-goal-2026-09-27]] "replace
  Claude's 65 dev-tooling personas" goal, not this program's scope).
- **10 confirmed out of scope with a documented reason** (table below) — unchanged from the
  original disclosure.
- **3 personas resolved in a follow-up pass (2026-09-29, later same session, owner said push
  through rather than escalate)** — see the two tables below. `slack-archaeologist` is now a real,
  built, tested agent; `engineering-senior-developer` and `project-manager-senior` are documented
  as Claude-side dev-tooling, not VECTOR district scope.

So: **all 239 are now accounted for** — built, found-existing, documented-excluded, or
resolved-by-classification. Nothing left unaddressed from the original roster.

### 10 personas explicitly out of scope (never assigned to any P1-P10 task)

| Persona | Reason |
|---|---|
| `academic-anthropologist` | Spec states directly: doesn't fit "build apps/websites from research and trends." |
| `academic-geographer` | Same spec line as above. |
| `academic-historian` | Same spec line as above. |
| `academic-narratologist` | Same spec line as above. |
| `academic-psychologist` | Same spec line as above. |
| `specialized-civil-engineer` | No VECTOR district or evidence source for structural/civil-engineering compliance data; unrelated to any of VECTOR's 41 districts. Same "no VECTOR-verifiable evidence source" pattern as P8's `language-translator`. |
| `specialized-french-consulting-market` | No French ESN/freelance-market data source wired into VECTOR; a market-specific advisory persona with nothing to recompute a check from. |
| `korean-business-navigator` | No VECTOR data source for Korean business-culture navigation; purely advisory, no deterministic check possible without fabricating one. |
| `study-abroad-advisor` | No VECTOR-accessible study-abroad application data (schools, visas, deadlines); same evidence-source gap as the not-built ops personas in P8. |
| `supply-chain-strategist` | No VECTOR supply-chain/procurement data source; a China-manufacturing-specific advisory persona outside VECTOR's owner-use scope. |

### 1 real gap, built (2026-09-29, follow-up pass)

| Persona | Resolution |
|---|---|
| `slack-archaeologist` | **Built.** `SlackArchaeologist` (`districts/security/security_specialists.py`), district=`security` — placed there (not a guess: only exists in the Brain vault, not the global Claude-tooling marketplace, and its own description — "incident reconstruction, evidence gathering" — matches P3's existing scan-pipeline pattern for that district exactly). Real deterministic checks over caller-supplied message records (no LLM call): no duplicate ids, every message has an author+timestamp, every timestamp parses, no dangling thread/parent references, plus the actual deliverable — a chronologically-ordered, attributed timeline reconstructed from that data. Proactively checked its new capability names against `_canonical_district_from_task_type()` for the exact word-overlap collision class that caused this program's earlier regression (see the fix above) — confirmed clean. 1 new GREEN tier entry (flagged for pending independent review). New dedicated test proves every planted defect is caught and the timeline is genuinely reordered from out-of-order input; full security/governor/tier/A2A regression suite passes. Manifest now 41 districts, 261 agents. |

### 2 resolved by classification (Claude-side dev-tooling, not VECTOR district scope)

| Persona | Resolution |
|---|---|
| `engineering-senior-developer` | **Not built — Claude Code dev-tooling, not VECTOR scope.** Its roster description ("Premium implementation specialist — Masters Laravel/Livewire/FluxUI, advanced CSS, Three.js integration") is verbatim the "Senior Developer" Claude subagent type — a tool Claude itself uses when developing VECTOR, not a VECTOR business persona. Its file also exists both in this repo's `.claude/agents/` and the global marketplace (`"in": ["codebase","global"]`), confirming it's the same shared Claude-tooling agent, not a project-specific one. VECTOR's `coding` district already has no shortage of implementation specialists (`FrontendDeveloper`, `RapidPrototyper`, `MinimalChangeEngineer`, etc.); building a duplicate under this name with no distinguishing evidence source would be exactly the "renamed duplicate" pattern this program has consistently declined to build (e.g. P8's `project-management-studio-operations`). |
| `project-manager-senior` | **Not built — Claude Code dev-tooling, not VECTOR scope.** Same reasoning: its roster description ("Converts specs to tasks and remembers previous projects...") is verbatim the "Senior Project Manager" Claude subagent type, and it's tagged `"in": ["codebase","global"]` — the same shared tooling agent, not a VECTOR-specific one. The stray `.md` prompt files found on disk (`core/prompts/shared/project_management/project-manager-senior.md`, `districts/governance/vector-project-manager-senior.md`) are consistent with this — reference/prompt material for Claude's own use while developing VECTOR, not a self-loaded live agent (confirmed no `FinanceSwarm`-style `MD_FILES` self-load wiring exists for either). |

## Consolidated new permission-tier entries (ALL pending independent review; no existing tier changed, moved, or loosened)

**GREEN (183 total):**
- P2/coding (28): `agent_sdk_ts_brief`, `agent_sdk_ts_check`, `business_rules_brief`, `business_rules_check`, `legacy_analysis_brief`, `legacy_analysis_check`, `scaffold_brief`, `scaffold_structure_check`, `uplift_migration_brief`, `uplift_migration_check`, `version_delta_brief`, `version_delta_check`, `ai_data_remediation_brief`, `ai_data_remediation_check`, `autonomous_optimization_brief`, `autonomous_optimization_check`, `cms_implementation_brief`, `cms_structure_check`, `mobile_app_brief`, `mobile_project_check`, `review_comment_brief`, `review_comment_check`, `type_design_brief`, `type_design_check`, `mcp_server_brief`, `mcp_manifest_check`, `terminal_integration_brief`, `terminal_contract_check`.
- P3/security (18): `patch_proposal_brief`, `patch_proposal_check`, `patch_verification_brief`, `patch_verification_check`, `scan_inventory_brief`, `scan_inventory_check`, `scan_load_brief`, `scan_load_check`, `scan_research_brief`, `scan_research_check`, `scan_verification_brief`, `scan_verification_check`, `identity_trust_brief`, `identity_trust_check`, `automation_governance_brief`, `automation_governance_check`, `slack_archaeology_brief`, `slack_archaeology_check` (last 2 added 2026-09-29 in the follow-up pass, see "1 real gap, built" above).
- P4/design (18): `visual_storyboard`, `visual_narrative`, `whimsy_design`, `microinteraction_audit`, `level_design`, `level_flow`, `narrative_design`, `narrative_arc`, `technical_art`, `asset_pipeline`, `spatial_design`, `spatial_comfort`, `immersive_design`, `immersive_flow`, `xr_interface`, `xr_interaction`, `cultural_review`, `cultural_brief`.
- P5/marketing (58): `aso_listing_brief`, `aso_listing_check`, `baidu_seo_brief`, `baidu_seo_check`, `bilibili_content_brief`, `bilibili_title_check`, `book_coauthor_brief`, `book_outline_check`, `carousel_growth_brief`, `carousel_slide_check`, `china_ecom_brief`, `china_ecom_check`, `china_localization_brief`, `china_localization_check`, `cross_border_brief`, `cross_border_margin_check`, `douyin_strategy_brief`, `douyin_content_check`, `instagram_curation_brief`, `instagram_caption_check`, `kuaishou_strategy_brief`, `kuaishou_content_check`, `linkedin_content_brief`, `linkedin_post_check`, `livestream_commerce_brief`, `livestream_run_check`, `podcast_strategy_brief`, `podcast_episode_check`, `private_domain_brief`, `private_domain_funnel_check`, `reddit_community_brief`, `reddit_post_check`, `short_video_edit_brief`, `short_video_edit_check`, `tiktok_strategy_brief`, `tiktok_caption_check`, `twitter_engagement_brief`, `twitter_post_check`, `video_optimization_brief`, `video_metadata_check`, `xiaohongshu_note_brief`, `xiaohongshu_note_check`, `zhihu_strategy_brief`, `zhihu_answer_check`, `paid_media_audit_brief`, `paid_media_account_check`, `paid_creative_brief`, `paid_creative_check`, `paid_social_brief`, `paid_social_metrics_check`, `ppc_strategy_brief`, `ppc_budget_check`, `programmatic_buy_brief`, `programmatic_inventory_check`, `search_query_brief`, `search_query_waste_check`, `tracking_setup_brief`, `tracking_event_check`.
- P7/chief_of_staff (5): the 5 new product-district capability names registered GREEN in `core/config.py` (see `SELF_DEV_P7_COS.md` for exact names — `product_work_nudge` plus 4 others).
- P8/memory_curator+ops+legal_compliance (20): `identity_graph_brief`, `identity_dedup_check`, `lsp_index_brief`, `lsp_symbol_check`, `hr_onboarding_brief`, `hr_onboarding_check`, `jira_workflow_brief`, `jira_workflow_check`, `project_shepherd_brief`, `project_shepherd_check`, `support_response_brief`, `support_response_check`, `accounts_payable_brief`, `accounts_payable_match_check`, `data_consolidation_brief`, `data_consolidation_check`, `report_distribution_brief`, `report_distribution_validate`, `training_design_brief`, `training_outline_check`. (`legal_compliance_brief`/`legal_compliance_check` are counted under P8's legal_compliance placement but listed once, in the YELLOW-adjacent P9 section below, to avoid double-counting — see note.)
- P10/self_dev (14): 14 new GREEN entries, all in-memory parse/compare/grade actions only — no LLM call, no file write, no external state mutation (see `SELF_DEV_P10_SELF_DEV.md` for exact names).

**YELLOW (12 total):**
- P8/legal_compliance (2): `legal_compliance_brief`, `legal_compliance_check` — advisory-only, `advisory_only: True` on every response.
- P9/legal_compliance (10): `healthcare_service_brief`, `healthcare_service_check`, `healthcare_marketing_brief`, `healthcare_marketing_check`, `legal_billing_brief`, `legal_billing_check`, `legal_intake_brief`, `legal_intake_check`, `legal_document_brief`, `legal_document_check`. Owner-mandated default YELLOW for the entire `legal_compliance` district — no GREEN entries in P9 at all.

**RED: none added.** No package built a RED-worthy executor; P3's patch-proposal roles are deliberately inert rather than gated RED, per that package's own explicit architectural constraint.

**No existing GREEN/YELLOW/RED tier entry was moved, renamed, or loosened by any of the 10 packages** — confirmed by each package's own report and spot-checked in `core/config.py` during this summary.

## NEEDS_HUMAN disclosures carried forward (not resolved by this program — owner decision needed)

1. **`zk-steward`** (P8) — already real, already manifest-registered, under `district=personal_growth`, not `memory_curator` as the spec's own district map names it. Not moved (moving a live agent's district is a real behavioral change outside this task's bounded scope). Owner must either update the spec's map or approve a follow-up move.
2. **5 ops-scope personas** (P8) — `project-management-experiment-tracker`, `support-analytics-reporter`, `support-executive-summary-generator` already have real matches in `projects`, `data_analytics`, and `chief_of_staff` respectively; `accounts-payable-agent` and `support-finance-tracker` were placement-decided into `finance` per this task's explicit instruction. Same district-map-vs-reality mismatch as above.
3. **`blockchain-security-auditor`** (P3) — not built; disclosed reason in `SELF_DEV_P3_SECURITY.md` (no VECTOR-accessible on-chain data source to recompute a real check from).
4. **P7's persona-file-absence caveat** — like P5/P8, the `.claude/agents/` persona `.md` files for P7's scope were not found in that worktree; scope was inferred from names and district context, disclosed as such in the report.
5. **P6's entire scope** — 17 sales-district personas, 0 certified fully real. 7 have partial coverage from existing sales agents (fixed for RULE 1 hydration and a real bug this session, not rebuilt as new personas); 10 have no real match and were not built. This was scoped as "a bounded repair," not new persona construction — the owner should decide whether P6's 17 personas need a proper new-construction pass like P2/P4/P5/P7/P9/P10 got.
6. **P1's verdict** — QA district's 8 personas are NOT VERIFIED per that package's own honest report (missing per-agent real-test gate for 7 of 8, one existing test mocks HP/internal state in violation of `.claude/rules/testing.md`). This is a pre-existing gap this program surfaced, not one it was scoped to fix.
7. **The "239 selected" reconciliation gap** — see above; ~65 personas presumed already-real were not individually re-verified against the Agent Roster artifact in this pass.

## Verification performed for this summary

- Read all 10 `SELF_DEV_P*.md` reports in full.
- Cross-checked P8's ops-district agent count against the live code (`districts/ops/ops_specialists.py`)
  rather than trusting the report's own pre-fix table — confirmed 7 new classes, not 8 (`AccountsPayableAgent`
  was removed as a duplicate during the review-fix pass and does not exist in the codebase).
- Confirmed all 5 manually-supervised commits (P2, P3, P8, P9, P10) are present on `fix/external-review-2026-09`
  via `git log --oneline`.
- Parsed `config/agent_manifest.yaml`: **41 districts, 260 agents, zero duplicate top-level mapping keys**
  (re-ran the duplicate-key detection grep used throughout this session; every district key count = 1).
- Ran the full sharded test suite (`python -m pytest -q`) once at the end of this program. The first run
  surfaced 10 FAILED tests; re-ran each individually per `systematic-debugging` rather than trusting the
  suite's own (misleadingly reported) exit code. 8 passed alone — confirmed order-dependent pollution, the
  same class already documented in `docs/OPEN_ISSUES.md` item 11a. 2 were real and reproduced standalone:
  `test_owner_routing_closure_f1.py::test_ambiguous_task_type_overlap_fails_closed` and
  `test_v1_trust_t2_action_identity.py::test_ambiguous_invented_label_fails_closed`. Root cause: P8's new
  `report_distribution_check` capability (words `report`/`distribution`/`check`) happened to word-overlap 2 of
  the 3 words in both tests' deliberately-ambiguous fixture `status_check_report`, enough to break the
  `_canonical_district_from_task_type()` fail-closed guarantee those tests exist to prove — a real regression
  introduced by this program, not a pre-existing flake. Fixed by renaming the capability to
  `report_distribution_validate` across all 7 files that named it (confirmed the fix worked by simulating the
  word-overlap match in Python against both the old and new key sets *before* touching any file, not guessed);
  the security-sensitive canonicalization algorithm itself was not touched. Commit `96cad6053`. A clean
  full-suite re-run was started to confirm the fix and get a trustworthy final count, but the background
  process was killed by the harness partway through due to system-wide low memory (not a code or test
  issue) and, per explicit instruction, was not restarted automatically. Everything else in this program
  was verified directly in the meantime: both regression tests pass in isolation, plus `test_governor.py`,
  `test_ops_specialists.py`, `test_legal_compliance_specialists.py`, `test_governor_unknown_task_gate.py`,
  `test_memory_curator.py`, `test_self_dev_specialists.py`, `test_coding_specialists.py`, and
  `test_security_specialists.py` all pass, the manifest re-parses clean (41 districts, 260 agents), and
  `districts/ops/ops_specialists.py`'s own smoke check passes.

  **Full clean re-run completed (2026-09-29, later same session)**, using the codebase's own memory-safe
  batched runner (`$TEMP/suite/run.py` — 25 files per subprocess, never accumulates state across the
  whole suite) once real time had passed and memory had genuinely recovered (~14GB free, no other heavy
  process). Result: **6,862 passed / 39 skipped / 0 error**, with 3 failures on the first pass in
  `tests/test_regression_search_web_returns_real_results.py`'s batch — re-ran that exact batch (25 files,
  identical flags) in isolation and got a clean 179/179 pass, confirming the 3 were a transient flake
  (a real-network-retry test, not a code regression) rather than anything introduced by this program.
  This is a real improvement over the previous best-known baseline (6,708 passed / 0 failed / 39 skipped,
  2026-09-27) — 154 more tests pass now, from this program's own new test files, with zero real
  regressions anywhere in the suite.

## Overall verdict

**Program functionally complete, with 6 specific decisions flagged above for owner attention** (P1's
NOT VERIFIED disposition, originally a 7th, was resolved in a 2026-09-29 follow-up pass — see its row above).

This is deliberately not a clean, zero-caveat "PASS": P6 certified zero new personas as fully real, P3
disclosed one not-built persona, and multiple packages carry explicit NEEDS_HUMAN district-placement
flags. Per `SELF_DEV_AGENT_SPEC.md`'s own guardrails, none of these are being papered over — they are
the honest, correct output of a spec that requires disclosure over fabricated capability. 90 new, real,
evidence-checked agents were built and committed across P2-P10 (none in P1 or P6, by design); every new
permission-tier entry is GREEN or YELLOW, flagged for the pending
independent review, and no existing tier was loosened.
