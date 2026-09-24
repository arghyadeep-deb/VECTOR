# Codex VECTOR V1 engineering handoff

Updated 2026-09-13. Owner: Arghyadeep Deb. Read this before continuing V1 work.

## Authority and evidence

Source of truth: **current code/tests > current Git/config/runtime > owner constraints > historical reports/plans**. Code establishes existing behavior, not permission to preserve a bug that violates owner intent; report the discrepancy before architectural changes.

This summarizes Codex's repository onboarding, static V1 gap trace, and historical-context reconciliation. No runtime, browser, provider, or test execution was performed. Findings below are source-traced, not fresh behavioral proof. Historical test counts are deliberately omitted.

Inspected baseline: branch `production-hardening-complete`, HEAD `830eb27b5a8c1e8056774bda77230405394c5ff9` (R24); working tree clean before this document. Git warned that its global ignore file was unreadable. Recheck HEAD, dirty state and worktrees next session; do not assume this baseline remains current.

## V1 definition and owner constraints

**Plan → execute → verify → remember → learn → recover.** V1 means reliable, bounded, observable completion of representative objectives with evidence, permissions, persistent progress and failure recovery. Dispatch, a response, tool return, positive reward and objective completion are distinct.

API-powered reliability comes first; increasingly local operation and native Arch/VECTOR OS are later directions. Preserve districts and provider flexibility. Do not expand agent counts, rewrite the system, consolidate memory, delete overlapping browser engines, build a Codex–Claude bridge, or launch unattended experiments merely because historical plans suggest them.

**Provider decision:** local models + free APIs + paid APIs are architecturally allowed. Paid usage requires explicit configuration/authorization and respected budgets/quotas. Do not silently spend. Sensitive-local routing remains binding. Exact model identities are configurable roles, not sacred architecture.

**Details checkpoints — OWNER INTENT; IMPLEMENTATION LOCATION NOT ESTABLISHED:** tasks must eventually support dynamically adding required details/checkpoints discovered during execution, rather than being restricted to a static predefined `checkpoint_key` scheme. Do not invent an implementation or assume that old scheme currently exists. Before changing extraction/planning/details collection, inspect code, Git history, plans and documentation; ask the owner if the intended implementation remains unresolved.

## Representative acceptance workflows and traced paths

These three workflows test the architecture vertically; they do not define the entire product scope. Routing is conditional, not one guaranteed pipeline.

### A. Research

`/command → intent classification → Governor.dispatch → ResearchSwarm/specialist → DeepResearcher → districts/research/research_api.py → research engine settings/LLM/search → iterative findings/sources/synthesis → agent/Governor/API memory and outcome handling`.

Separate `/research/search` directly constructs WebScout. Governor's special complex-research decomposition creates search/summarize/store subtasks but passes the topic, not prior findings.

Source-traced gaps:
- `DeepResearcher` advertises `deep_research` but `run()` accepts `quick/report/papers/news/documents`; ResearchSwarm forwards task types unchanged.
- `research_api._make_settings()` forces `llm.provider="ollama"`; general API routing does not automatically reach it.
- API-wrapper exceptions become summary/content text; `DeepResearcher.run()` can wrap those results in `status="ok"`.
- Nonempty synthesis, including an unable-to-summarize message, is not verified research. The wrapper does not enforce credible multi-source coverage or claim-to-citation support.
- Programmatic mode disables research-engine DB/metrics operations; other memory/report writes have separate success paths.

Preserve iterative research, source-bearing results, research IDs, report generation and resource cleanup.

### B. Software/coding

`/command or explicit task → Governor → CodingSwarm/CodeConductorAgent → explicit params.action + instruction → CodingOrchestrator → file selection/AST map → read → LLM plan → parsed edits → str_replace → edit summary → memory/HP`.

Source-traced gaps:
- A query can receive advice instead of execution; task-type selection does not supply the agent's required `params.action`.
- CodingSwarm's text fallback returns `ok`. CodingOrchestrator reports `ok` for zero edits (`0 == len(edits)`).
- Actual `run()` summarizes edits; it does not execute the advertised review phase or relevant tests. Partial edits receive positive HP in CodeConductorAgent.
- Inspected code-conductor writes call file helpers directly without Gateway enforcement or workspace containment in those helpers. Governor council review is advisory. Resolve this path before live coding acceptance; do not infer authorization from dispatch.
- No integrated persistent per-edit recovery/test-driven retry transaction was established.

Preserve AST mapping, unique-match replacements, diffs and the safeguard requiring explicit action/instruction before editing.

### C. Safe persistent multi-step browser task (proposed acceptance fixture)

Use controlled read-only pages: open index → discover detail URL → persist URL/progress → interrupt/restart → follow URL → extract fields → return page evidence → independently verify against fixture contents → record outcome. No accounts, purchases, publication or destructive external actions.

Candidate path: `PlanStore → ready PlanStep candidate → DecisionEngine → _act_on_plan_step → PlanRunner → AutonomousExecutor → PermissionGateway → [missing generic browser dispatch bridge] → Governor → GUIAutomationAgent → BrowserController → Playwright/VLM`.

Source-traced gaps:
- `browser_task` lacks the needed Gateway plan handler; generic composition dispatch is narrowly allowlisted to `script` and `schedule_post`.
- BrowserController returns status/conversations, not structured extracted fields for bindings; action results are not retained in the returned conversation trace.
- Its outer loop handles terminal actions but does not act on ordinary blocked/error action results. Model `finished` becomes `GUIStatus.END`; the agent rewards END without independent page verification.
- Browser/page lifecycle is not integrated with plan resumption. Unresolved plan bindings are silently skipped; general decomposition does not preserve supplied bindings/verification rules when constructing steps.

Direct Playwright is a structurally clearer first candidate than the sidecar bridge, not live-proven superior. Preserve browser governance and existing engines pending measured comparison. Persisting a discovered URL need not redesign Details checkpoints.

## Shared blockers

- Inconsistent `ok/executed/completed/end`, fallback and missing-status semantics.
- Executor verification is largely a four-status failure exclusion; missing status defaults to executed. Timeout, unavailable, rate-limited and partial outcomes need explicit interpretation.
- Capability registration does not prove readiness or compatible invocation parameters; baseline AgentBase can merely acknowledge work.
- Evidence is not consistently propagated to completion, memory and learning. Shared assessment cannot itself prove citation quality or code correctness.
- Direct Governor/API, native loop, Hands and plans differ; an executor-only fix misses important paths.
- HP/reward consumers differ and can double-account. Native reward defaults include goal progress and absence of correction/override; setting completion false alone does not remove favorable reward.
- Permissions are distributed across actual primitives. Supervision/process health does not establish useful progress or safe resumption.

## Preserve architecture and established invariants

Reuse Governor/registry/manifest/districts; ExecutionReport/AutonomousExecutor; Plan/PlanStep DAG, bindings, PlanStore and bounded replanning; existing memory stores and canonical policy identity; inference catalog/routing/quotas; Gateway/browser governance/control grants; existing tests and evidence.

Historical fixes must be checked against current code/tests before being called open or closed:
- Hypothesis generation must be awaited; preserve result text/confidence/observation contract fixes. A later hang is not recurrence of the original missing-await defect.
- Interrupted-plan recovery: first fresh-store load resets GREEN work for ordinary execution; non-GREEN/unknown interrupted work fails, takes declared authorized fallback or requires review. Preserve idempotency and no silent risky replay; revisit assumptions before concurrent plan writers.
- PermissionGateway remains the consequential-action boundary; Council, confidence, learning, recovery and composition cannot self-authorize.
- **Suppression/veto != executed outcome. Reward != goal completion.** Do not restore automatic reward-driven goal progress or manufacture reward history.
- Preserve behavioral policy identity separately from decision/candidate/plan correlation and provenance. Do not strip identifiers just to make learning tests pass.
- Preserve session hydration before LLM calls and sensitive-local routing across fallbacks.
- Preserve historical databases/metrics; isolate main and auxiliary stores, PlanStore/PostJob paths, frozen import-time paths and singletons before tests. Do not launch default `run_vector.py` as an inspection command.

## Shared outcome-assessment slice

**PROPOSED — NOT YET APPROVED OR IMPLEMENTED.**

Extend the existing execution-report semantics with one conservative assessment reused at completion boundaries. Preserve raw payload/status; distinguish explicit failure/blocking, incomplete work, execution claims and verification evidence. Separate authorization/execution checks from objective verification. Propagate assessment through Governor, native loop, API commands, plans and Hands; record observations without unsupported completion-derived credit.

Do not trust an LLM-supplied verified flag. Do not pretend a shared assessor can detect every producer that incorrectly emits `ok`. Research error wrapping, zero-edit coding success, browser verification and routing bridges remain follow-up slices. Preserve PlanRunner's existing requirement that report status be executed AND verification pass; `always` alone must not complete blocked work.

**Required before implementation:** reconcile current execution semantics with existing R1–R24 outcome/reward/suppression/policy/provenance and plan-completion tests/reports. Inspect assertions, exclusions and isolation, not just report verdicts. Confirm whether the proposed assessment would disconnect established learning, duplicate accounting, change policy identity or regress suppression handling. Then recommend the exact minimal diff for approval.

## Highest-value files

Proposed shared-boundary candidates (not an approved edit list):
- `core/runtime/executor.py`
- `core/runtime/plans.py`
- `core/city/governor.py`
- `core/loop/autonomous_loop.py`
- `core/api/routers/commands.py`
- `hands/runner.py`

Workflow/permission trace anchors:
- `config/agent_manifest.yaml`, `core/city/agent_base.py`, `core/city/declarative_manifest.py`
- `core/loop/permission_gateway.py`, `core/memory/policy.py`, `core/memory/counterfactual.py`
- `districts/research/agent.py`, `deep_researcher.py`, `research_api.py` (same directory); `core/research_engine/api/research_functions.py`
- `districts/coding/agent.py`, `code_conductor_agent.py`, `gui_automation_agent.py` (same directory)
- `core/code_conductor/orchestrator.py`, `core/code_conductor/str_replace.py`
- `core/vision_control/browser_controller.py`, `core/browser/governance.py`
- `core/inference/provider_client.py`, `route_policy.py`, `vectorcode_llm.py` (same directory)

## Tests required for a future first slice

Extend `tests/backend/test_autonomous_executor.py`, `tests/unit/test_planning.py`, `tests/integration/test_planning_integration.py`, and relevant existing Governor/Hands/outcome-attribution suites after inspection.

Prove: missing/partial/fallback/timeout results cannot become verified completion; real Gateway denial prevents execution/credit; execution without proof stays distinct; an isolated real action with independently checked output can complete; unverified predecessors do not unlock dependencies; assessment/evidence survive reload; learning distinguishes incomplete work from verified success/failure; equivalent outcomes are interpreted consistently across surfaces; source/diff/error payloads survive; risky interrupted actions never silently replay.

Use real internal boundaries and isolated state; stub external services/models where necessary and label live versus simulated evidence. Existing executor tests use FakeGateway, so their current passing assertions would not alone prove real permission behavior. Guard against stalled legacy workflows, double rewards, lost results, unsafe retries and invented evidence on old records.

## Historical issues requiring current verification

Do not assume these remain open: external MCP Gateway/fail-open wrapper gap; plan/native ThreatDetector and Counterfactual parity; plan-strategy policy identity and R7 provenance; hypothesis liveness and bounded worker waits; disconnected memory/ghost/correction consumers; R16 test realism; WebAuthn token-type confusion. Consult relevant R8–R24 work before reopening old findings.

Navigation: `VECTOR_TECHNICAL_KNOWLEDGE/` reports 51, 52, 55, 60, 84, 88, 89; R19/R20 reports; R21–R23 reports; `R24_R26_ORCHESTRATOR_LEDGER.md`; M1c/M1d/M1E test-isolation reports. R24 is the last completion established in this inspection; R25/R26 and a fresh Reality Gate are not established or authorized. Historical scoped readiness does not authorize another seven-day run.

Other source-traced debt: DistrictLLM searches missing `agents/districts`; CI references missing `core/ui/dashboard`; `docs/phase_status.md` and `brain/` are absent in this checkout; CausalReasoner uses source/target against from/to graph keys. These are separate from the proposed slice. Do not import this handoff into runtime memory as verified operational truth.

## Next session

**FIRST perform a targeted read-only reconciliation of current execution, outcome, suppression, reward, policy identity and plan completion semantics against the relevant R1–R24 tests/reports.**

**THEN recommend the exact minimal implementation diff.**

**DO NOT begin a repository-wide refactor.**
