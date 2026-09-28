# SELF_DEV_P10_SELF_DEV — isolated VECTOR tooling improvement checks

Date: 2026-09-29
District: `self_dev` (new)
Owner approval: explicitly recorded in the task on 2026-09-29
Review status: every new permission-tier entry is flagged for pending independent review.

## Findings and duplication check

The seven requested persona files were absent from `.claude/agents/` in this worktree:

- `plugin-dev/agent-creator.md`
- `plugin-dev/plugin-validator.md`
- `plugin-dev/skill-reviewer.md`
- `skill-creator/analyzer.md`
- `skill-creator/comparator.md`
- `skill-creator/grader.md`
- `hookify/conversation-analyzer.md`

Their scope was therefore inferred conservatively from the names, as the task permits. Searches of `config/agent_manifest.yaml`, existing districts, Governor routes, permission tiers, and tests found no real agent match for these seven roles and no existing `self_dev` district. Related coding agents validate product-code concerns, but none owns this package's isolated Claude Code/plugin/skill/hook tooling scope; reusing or registering them under `self_dev` would violate the required capability boundary.

All seven inferred jobs have a bounded deterministic evidence source and were built. There are no omitted personas and no `NEEDS_HUMAN` disclosures.

## Real agents and deterministic checks

All classes in `districts/self_dev/self_dev_specialists.py` subclass `AgentBase`, start with real HP, support ghost inheritance, and are registered only under `self_dev`.

| Agent | Brief capability | Check capability | Deterministic evidence checked |
|---|---|---|---|
| `AgentCreator` | `agent_creation_brief` | `agent_definition_check` | Required metadata, `self_dev` district, unique capabilities, parseable Python AST, one `AgentBase` subclass, async `run`, no direct coding/Governor import, and no filesystem-write primitive in supplied source. |
| `PluginValidator` | `plugin_validation_brief` | `plugin_manifest_check` | Supplied JSON/dict manifest fields, slug, semantic version, standard manifest file, declared entrypoint, and explicit unique permission names. |
| `SkillReviewer` | `skill_review_brief` | `skill_structure_check` | Frontmatter name/description, caller-required sections, and numbered actionable steps in supplied skill text. |
| `SkillAnalyzer` | `skill_analysis_brief` | `skill_analysis_check` | Metadata, instruction-section count, caller-expected resource references, and unresolved placeholders. |
| `SkillComparator` | `skill_comparison_brief` | `skill_comparison_check` | Real unified diff plus caller-supplied required additions and removals. |
| `SkillGrader` | `skill_grading_brief` | `skill_grade_check` | Explicit weighted criteria, required terms, bounded passing score, and recomputed weighted score. |
| `ConversationAnalyzer` | `hook_conversation_brief` | `hook_candidate_check` | Bounded structured transcript events, unique hook names, a restricted non-grouping regex subset, expected-event coverage, and actual rule matches. |

Briefs report `ready` only when every declared evidence field is supplied. Checks report `verified` only when a real analyzer produced checks. HP is awarded only for a ready brief or a verified passing check; missing evidence and deterministic failures earn no HP.

## Enforced architectural boundary

The package contains no import of `districts.coding` or `core.city.governor`, no direct reference to a coding agent class, and no file-writing API. It consumes caller-supplied artifacts and returns in-memory reports only. It does not read or write product code, `districts/`, `core/`, or owner data. Artifact sizes and collection counts are bounded; hook regexes reject grouping, alternation, counted repetition, and backreferences before matching to prevent untrusted-pattern backtracking attacks.

The regression test parses `self_dev_specialists.py` with Python AST and fails if it finds:

- any direct `districts.coding` import;
- any `core.city.governor` import; or
- any common filesystem write/move/delete primitive (`open`, `write_text`, `write_bytes`, `write`, `unlink`, `rename`, `replace`, `mkdir`, and related calls).

The manifest registrations and all fourteen `DISTRICT_TASK_MAP` routes are asserted to exist only under `self_dev`. No coding route or capability registration was added. These agents currently need no coding-district action. If that changes, the only permitted design is inherited `a2a_ask(..., to=<registered coding agent>, capability=...)` through the normal governed A2A bus; a direct in-process coding import remains forbidden.

## Permission-tier decisions — all NEW, all pending independent review

All fourteen actions are GREEN because they only parse, compare, or grade caller-supplied in-memory tooling data. They do not call an LLM, execute code, edit a tool, write a file, send data, or mutate external state. No existing tier was moved, changed, or loosened.

| New GREEN action | Reason |
|---|---|
| `agent_creation_brief` | Reports completeness of supplied tooling-agent evidence only. |
| `agent_definition_check` | Static AST/metadata validation only; rejects direct product-code access patterns. |
| `plugin_validation_brief` | Reports completeness of supplied plugin evidence only. |
| `plugin_manifest_check` | Parses supplied manifest/package-file names without installing or writing a plugin. |
| `skill_review_brief` | Reports completeness of supplied skill evidence only. |
| `skill_structure_check` | Static frontmatter/heading/step checks over supplied text. |
| `skill_analysis_brief` | Reports completeness of supplied skill-analysis evidence only. |
| `skill_analysis_check` | Static section/resource/placeholder checks over supplied text. |
| `skill_comparison_brief` | Reports completeness of supplied comparison evidence only. |
| `skill_comparison_check` | In-memory diff and explicit expectation matching only. |
| `skill_grading_brief` | Reports completeness of supplied grading evidence only. |
| `skill_grade_check` | Recomputes a score from explicit criteria; no subjective model verdict. |
| `hook_conversation_brief` | Reports completeness of supplied transcript/hook evidence only. |
| `hook_candidate_check` | Compiles supplied regexes and matches supplied events; installs no hook. |

The additions are grouped in `core/config.py` under an explicit pending-independent-review comment as required.

## LLM, execution, and security posture

There are no LLM call sites in this package, so RULE 1 hydration is neither invoked nor bypassed. No model opinion is presented as verification. The implementation does not import prohibited libraries (`requests`, `flask`, `threading`, or `pickle`), uses `loguru`, and has no shell execution, dynamic evaluation, deserialization, network call, secret handling, or external action.

## Evaluation and testing

Evaluation criteria were established before implementation:

1. Every agent is a real `AgentBase` citizen registered only under `self_dev`.
2. Complete evidence yields a ready brief and a deterministic passing verification.
3. Missing evidence yields `needs_human`, an unverified result, and no HP.
4. A verified failing artifact earns no HP.
5. All fourteen tiers and routes are exact and isolated to `self_dev`.
6. The source-level boundary rejects direct coding/Governor imports and filesystem writes.

Commands actually run in this shell:

- TDD red run: `python -m pytest tests/test_self_dev_specialists.py -v` — collection failed with the expected `ModuleNotFoundError: No module named 'districts.self_dev'` before implementation.
- First implementation run: the focused test collected 19 tests; 18 passed and one syntax-specific source-string assertion failed. The underlying AST boundary assertions passed. The brittle assertion was removed and the proposed-agent analyzer was strengthened to enforce the same import/write boundary on supplied source.
- Security-review finding and fix: caller-supplied hook regexes were initially executable without complexity bounds. The final implementation caps text/collection sizes, restricts hook patterns to a non-grouping subset, and includes a nested-quantifier rejection regression.
- Focused green run after that fix: `python -m pytest tests/test_self_dev_specialists.py -q` — **20 passed**.
- Module smoke check: `python districts/self_dev/self_dev_specialists.py` — exit 0; all seven specialists exercised both missing evidence/no HP and complete evidence/real HP paths.
- Real manifest load and instantiation — loaded **260 agents across 41 districts**; asserted exactly **7 self_dev agents**, all successfully instantiated in `self_dev`.
- `python -m py_compile districts/self_dev/__init__.py districts/self_dev/self_dev_specialists.py tests/test_self_dev_specialists.py` — exit 0.
- Test file's own `__main__`: `python tests/test_self_dev_specialists.py` — exit 0; **20 passed**.
- Final routing/permission/A2A regression batch: `python -m pytest tests/test_self_dev_specialists.py tests/test_governor_unknown_task_gate.py tests/test_regression_governor_capability_routing.py tests/test_v1_trust_t3_permission_vocabulary.py tests/test_a2a_conformance_all_districts.py -v` — **76 passed**.
- Final module smoke and `py_compile` run in the same fresh verification chain — both exited 0.
- Source review/scans found no prohibited runtime dependency, LLM call, shell execution, direct coding/Governor import, or filesystem-write primitive in the district implementation. The only textual matches for forbidden module names are the analyzer's deny-list strings and the regression assertions themselves.

The observed pytest warning was the environment's existing `pynvml` deprecation warning from `torch`; it is unrelated to this package. The direct module smoke also logged that the managed shell could not open the external HP-validator database. The real in-process HP transitions still occurred and were asserted (500 to 510); the focused pytest run's configured test environment did not fail. No code was changed to bypass or mock the HP system.

## Commit status

The required scoped `git add` and `git commit` were attempted on `vector-dev/p10-self-dev-manual`. Git failed before staging because this managed session can read but cannot write the shared parent repository metadata:

`Unable to create .../.git/worktrees/p10-self-dev-manual/index.lock: Permission denied`

No file was staged, no commit was created, and no push, merge, checkout, branch change, or partial index update occurred. The intended commit message explicitly named all fourteen new GREEN entries for pending independent review. A write-enabled supervisor session must run the same scoped add and local commit; the implementation remains intact in this worktree.

## Risks and independent-review focus

- Structural checks cannot establish the semantic quality or safety of arbitrary tooling; they deliberately report only what was recomputed.
- The lightweight skill frontmatter parser supports the simple `key: value` fields required here, not the full YAML language. Complex frontmatter should be supplied in a normalized form or handled in a future separately reviewed extension.
- Regex hook matching can have false positives or false negatives. It validates declared rules against evidence but does not install hooks or prove runtime behavior.
- Weighted grading is only as sound as the caller-supplied criteria. The result is reproducible, not an expert certification.
- Independent review should confirm GREEN remains appropriate while these capabilities stay strictly in-memory. Any future file mutation must be a new separately classified action and remain confined to explicitly approved tooling paths.
