# SELF_DEV P2 — Coding Personas

Date: 2026-09-29

District: `coding`

Disposition: 41 selected personas = 19 existing matches + 14 newly implemented + 8 not built

## Guardrail result

No unverifiable persona was represented by an LLM-only stub. The fourteen new agents perform only in-memory work over caller-supplied evidence. Their checks use Python AST parsing, unified diffing, contract comparison, numeric metric recomputation, or explicit structural validation. They make no LLM, network, subprocess, filesystem-write, hardware, or third-party-service calls.

Most requested source persona files were not present in this worktree. Only the existing code-reviewer persona material was found under `.claude/agents/`; other scopes were inferred conservatively from the supplied names and the Coding district, as the task directed.

## Existing VECTOR-native matches — not duplicated (19)

| Selected persona | Existing real match | Evidence of real behavior |
|---|---|---|
| `code-modernization/architecture-critic` | `districts.coding.architect_bot.ArchitectBot` | Registered architecture/design agent with dependency and design analysis. |
| `code-simplifier/code-simplifier` | `districts.coding.refactor_cleaner.RefactorCleaner` | Registered dead-code/refactor specialist. |
| `engineering-codebase-onboarding-engineer` | `districts.coding.codebase_onboarding_engineer.CodebaseOnboardingEngineer` via `CodingSwarm` | Real repository scanning, tracing, and onboarding implementation. |
| `engineering-data-engineer` | `districts.data_analytics.data_engineer.DataEngineer` | Real SQLite/SQLCipher pipeline health, profiling, contracts, and Bronze-to-Silver operations. |
| `engineering-database-optimizer` | `districts.coding.database_optimizer.DatabaseOptimizer` via `CodingSwarm` | Real schema/benchmark/audit paths. |
| `engineering-email-intelligence-engineer` | `districts.communications.email_intelligence.EmailIntelligence` | Exact native role; parses actual thread structures and has a Gmail integration when credentials exist. |
| `engineering-frontend-developer` | `districts.coding.frontend_developer.FrontendDeveloper` via `CodingSwarm` | Real audit, scaffold, dashboard-plan, and API-check paths. |
| `engineering-git-workflow-master` | `districts.coding.git_bot.GitBot` | Registered real Git status/diff/commit workflow agent. |
| `engineering-minimal-change-engineer` | `districts.coding.minimal_change_engineer.MinimalChangeEngineer` via `CodingSwarm` | Exact native role with scope and diff checks. |
| `engineering-rapid-prototyper` | `districts.coding.rapid_prototyper.RapidPrototyper` via `CodingSwarm` | Exact native role with stack selection, analysis, and prototype planning. |
| `engineering-software-architect` | `districts.coding.architect_bot.ArchitectBot` | Same real architecture capability; a second persona wrapper would duplicate it. |
| `engineering-sre` | `districts.ops.sre_monitor.SREMonitor` via `OpsSwarm` | Real health probes, SLO calculation, and incident signals. |
| `engineering-technical-writer` | `districts.qa.technical_writer.TechnicalWriter`, registered under `documentation` | Real AST-backed module/API documentation generation. |
| `engineering-threat-detection-engineer` | `districts.security.threat_detection_engineer.ThreatDetectionEngineer` | Exact native role with Sigma, ATT&CK, coverage, and log analysis. |
| `feature-dev/code-reviewer` | `districts.coding.code_reviewer.CodeReviewer` | Registered AST-based review and circular-import/security checks. |
| `pr-review-toolkit/code-reviewer` | `districts.coding.addy_code_reviewer.AddyCodeReviewer` / `ObraCodeReviewer` | Two registered independent review perspectives already cover this scope. |
| `pr-review-toolkit/code-simplifier` | `districts.coding.refactor_cleaner.RefactorCleaner` | Existing refactor/dead-code implementation covers simplification without duplication. |
| `pr-review-toolkit/pr-test-analyzer` | `districts.qa.test_results_analyzer.TestResultsAnalyzer` via `QASwarm` | Real test execution/output parsing, history, and regression comparison. |
| `specialized-document-generator` | `districts.qa.doc_generator.DocGenerator`, registered under `documentation` | Exact native document-generation role with changelog, summary, and district-report paths. |

## Newly implemented real agents (14)

All classes live in `districts/coding/coding_specialists.py`, subclass `AgentBase`, start with real 500 HP, support ghost inheritance, and are registered individually in `config/agent_manifest.yaml`.

| Selected persona / class | Deterministic evidence check |
|---|---|
| `agent-sdk-dev/agent-sdk-verifier-ts` / `AgentSDKVerifierTS` | Parses submitted package/tsconfig mappings and TypeScript source text; verifies dependency, strict mode, construction, and export. |
| `code-modernization/business-rules-extractor` / `BusinessRulesExtractor` | Parses Python with `ast` and locates conditional/comparison rules and owning functions. |
| `code-modernization/legacy-analyst` / `LegacyAnalyst` | Parses Python and identifies bare exceptions and wildcard imports. |
| `code-modernization/scaffolder` / `Scaffolder` | Compares a submitted file tree to required scaffold files and checks non-empty content. |
| `code-modernization/uplift-migrator` / `UpliftMigrator` | Parses both versions, computes a real unified diff, and verifies public definitions remain. |
| `code-modernization/version-delta-analyst` / `VersionDeltaAnalyst` | Compares baseline/current contract mappings for additions, removals, and signature changes. |
| `engineering-ai-data-remediation-engineer` / `AIDataRemediationEngineer` | Recomputes required-field, non-null, and uniqueness constraints across supplied records. |
| `engineering-autonomous-optimization-architect` / `AutonomousOptimizationArchitect` | Compares measured baseline/candidate metrics against explicit direction and minimum improvement objectives. |
| `engineering-cms-developer` / `CMSDeveloper` | Validates content-field and route shape/uniqueness from supplied schemas. It does not claim a live CMS deployment. |
| `engineering-mobile-app-builder` / `MobileAppBuilder` | Checks submitted project files for application source and target-specific manifests. It does not claim a device build. |
| `pr-review-toolkit/comment-analyzer` / `CommentAnalyzer` | Validates review comments have real file/line locations, priorities, and actionable bodies. |
| `pr-review-toolkit/type-design-analyzer` / `TypeDesignAnalyzer` | Uses Python AST to verify requested public symbols exist and have parameter/return annotations. |
| `specialized-mcp-builder` / `MCPBuilder` | Validates MCP server/tool naming, descriptions, uniqueness, and object input schemas. It does not claim a server was launched. |
| `terminal-integration-specialist` / `TerminalIntegrationSpecialist` | Validates tokenized argv, bounded timeouts, explicit success codes, unique command names, and disabled shell execution. It never runs a command. |

Each class has a `<x>_brief` capability for evidence completeness and a `<x>_check` capability for deterministic verification. Missing evidence returns `needs_human` / `verified=false`; it never earns HP. A completed brief earns HP only when all declared evidence is present. An audit earns HP only when at least one deterministic check ran and every check passed.

## Deliberately not built (8)

| Selected persona | Reason |
|---|---|
| `engineering-embedded-firmware-engineer` | VECTOR has no target board, compiler/programmer evidence, hardware-in-loop result, or device telemetry in scope. Static prose would not verify firmware behavior. |
| `engineering-feishu-integration-developer` | No Feishu tenant, app credentials, API connector, or auditable service response is available. |
| `engineering-filament-optimization-specialist` | No printer, slicer telemetry, material measurements, or verified print-result source is available. |
| `engineering-solidity-smart-contract-engineer` | No Solidity compiler/analyzer or chain/testnet execution source is established for this package; an LLM opinion would not verify contract safety. |
| `engineering-voice-ai-integration-engineer` | No selected provider/service, credentials, audio fixture contract, or live latency/transcription evidence was supplied. |
| `specialized-salesforce-architect` | No Salesforce org, metadata API connection, schema export, or deployment/test result is available. |
| `blender-addon-engineer` | No Blender runtime/add-on registration context or headless Blender verification source is available. |
| `macos-spatial-metal-engineer` | This Windows VECTOR host has no macOS/Metal/spatial runtime or build/test evidence source. |

These limitations are intentional applications of the self-development specification's “no fabricated capability” rule. A future package may build one only after a real compiler, runtime, authenticated sandbox, device, or reproducible external evidence source is added.

## Permission and routing changes

The following 28 actions are **new GREEN tier entries**, all flagged in `core/config.py` for the pending independent review. No existing permission entry was changed, moved, or loosened:

`agent_sdk_ts_brief`, `agent_sdk_ts_check`, `business_rules_brief`, `business_rules_check`, `legacy_analysis_brief`, `legacy_analysis_check`, `scaffold_brief`, `scaffold_structure_check`, `uplift_migration_brief`, `uplift_migration_check`, `version_delta_brief`, `version_delta_check`, `ai_data_remediation_brief`, `ai_data_remediation_check`, `autonomous_optimization_brief`, `autonomous_optimization_check`, `cms_implementation_brief`, `cms_structure_check`, `mobile_app_brief`, `mobile_project_check`, `review_comment_brief`, `review_comment_check`, `type_design_brief`, `type_design_check`, `mcp_server_brief`, `mcp_manifest_check`, `terminal_integration_brief`, `terminal_contract_check`.

Every one has an exact `DISTRICT_TASK_MAP` entry to `coding`; the tests compare class capabilities, manifest capabilities, GREEN membership, absence from YELLOW/RED, and exact routing.

## Evaluation and verification

Acceptance criteria were defined before implementation in `docs/superpowers/plans/2026-09-29-coding-self-dev-agents.md`:

- incomplete brief/check evidence makes no capability claim and awards no HP;
- complete evidence produces a ready brief;
- each check recomputes at least one concrete result without an LLM;
- a failing deterministic audit does not earn HP;
- manifest registration exactly matches class capabilities;
- every new capability has exactly one GREEN classification and exact Coding route.

Executed in this worktree:

```text
python -m pytest tests/test_coding_specialists.py -q
3 passed (one unrelated torch/pynvml deprecation warning)

python districts/coding/coding_specialists.py
exit 0; [VECTOR][coding_specialists] smoke check passed

python tests/test_coding_specialists.py
exit 0; coding specialist tests OK

python -m pytest tests/test_coding_specialists.py tests/test_governor_unknown_task_gate.py tests/test_manifest_swarm_orchestrators.py tests/test_rr1_5_permission_vocabulary.py tests/test_v1_trust_t3_permission_vocabulary.py -q
64 passed (one unrelated torch/pynvml deprecation warning)

python -m ruff check districts/coding/coding_specialists.py tests/test_coding_specialists.py
All checks passed
```

No LLM evaluation was needed because the new implementation contains no LLM call site. Therefore there is no model latency or token cost and no hydration path to verify in the new module.

## Commit status

The requested local commit could not be created from this session. `git add` failed before staging with:

```text
fatal: Unable to create 'C:/Users/Arghyadeep/Desktop/V.E.C.T.O.R/V.E.C.T.O.R. Codebase/.git/worktrees/p2-coding-manual/index.lock': Permission denied
```

The worktree files are writable, but the linked worktree's real Git metadata directory is outside the writable sandbox and is exposed read-only. No push, merge, checkout, or branch change was attempted. The intended commit subject is `[P2] coding: add evidence-gated specialists` once Git metadata is writable.

## Risks

- These checks establish structural and contract evidence, not semantic correctness beyond what can be recomputed from the submitted artifacts.
- TypeScript checks intentionally avoid claiming compilation; a future real TypeScript compiler integration could strengthen them.
- CMS, mobile, MCP, and terminal specialists verify submitted contracts only; they do not claim deployment or runtime execution.
- Existing native matches were reused rather than rewritten, so this package does not broaden or normalize their historical behavior.
