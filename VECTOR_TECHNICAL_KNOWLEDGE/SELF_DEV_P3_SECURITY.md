# SELF-DEV P3 — Security District

Date: 2026-09-29

## Approval and safety boundary

The owner explicitly approved this security-sensitive package on 2026-09-29.
The implementation is defensive and analysis-only. It does not add a patch
executor, shell runner, arbitrary-code path, auto-merge path, deployment path,
or PermissionGateway bypass.

The selected `claude-security/*` persona files were absent from `.claude/agents/`
and from the rest of this worktree. Their scope was therefore inferred from the
names and VECTOR's existing Security district, as the task permits. The three
specialized persona sources exist under `core/prompts/shared/specialized/` and
were inspected.

## Existing real matches retained

The pre-build inventory found the following real, registered matches. They were
not duplicated:

| Selected role | Existing VECTOR evidence | Decision |
| --- | --- | --- |
| `claude-security/claude-security` | `ThreatScout`, `MalwareHunter`, `NodeGuard`, `ThreatDetectionEngineer`, `DetectionRules`, `SIEMPipeline`, `AlertManager`, and `IncidentPlaybookRunner` already form a scan/detect/alert/respond pipeline | Retained the cohesive existing pipeline |
| `claude-security/explore` | `SkillSpector` performs static pre-load artifact exploration through `core.security.skill_scanner`; `ThreatScout` inventories processes/startup entries | Retained existing scanners |
| `claude-security/scan-redactor` | `DataRedactor` performs deterministic PII/secret redaction and cloud-safety checks | Retained existing redactor |

Other relevant existing capabilities found during inventory include network
connection/port/blocklist checks in `NetworkMonitor`, MITRE/Sigma/log analysis
in `ThreatDetectionEngineer`, rule evaluation in `DetectionRules`, structured
event processing in `SIEMPipeline`, and permission-gated incident actions in
`IncidentPlaybookRunner`. The new file does not reproduce any of those checks.

## New real agents

`districts/security/security_specialists.py` adds eight concrete `AgentBase`
subclasses. Every agent has real HP, generation tracking, ghost inheritance,
manifest registration, exact Governor routes, and normal A2A reachability.
No bespoke scan-pipeline bus was added.

| Agent | Exact capabilities | Deterministic evidence check |
| --- | --- | --- |
| `PatchProposalGenerator` | `patch_proposal_brief`, `patch_proposal_check` | Builds an in-memory unified diff from explicit before/after text; validates relative target, changed content, and diff hunk |
| `PatchProposalVerifier` | `patch_verification_brief`, `patch_verification_check` | Parses diff headers/hunks and caller-supplied check evidence; never runs the reported commands/tests |
| `ScanInventoryAnalyst` | `scan_inventory_brief`, `scan_inventory_check` | Validates artifact paths, detects duplicates, and computes SHA-256/byte counts without returning content |
| `ScanLoaderAnalyst` | `scan_load_brief`, `scan_load_check` | Parses JSON only and validates scan IDs, severities, paths, line numbers, and finding evidence |
| `ScanResearcher` | `scan_research_brief`, `scan_research_check` | Checks advisory provenance, identifier consistency, and corroboration across independent domains |
| `ScanVerifier` | `scan_verification_brief`, `scan_verification_check` | Compares supplied inventory paths with scan coverage and reports missing/unexpected paths |
| `AgenticIdentityTrustAnalyst` | `identity_trust_brief`, `identity_trust_check` | Fails closed on registry-ID mismatch, missing scope, expiry, missing independent signature evidence, or invalid audit-chain evidence |
| `AutomationGovernanceAnalyst` | `automation_governance_brief`, `automation_governance_check` | Scores explicit reliability controls and returns APPROVE/PILOT/PARTIAL/DEFER/REJECT without activating automation |

All checks return `needs_human` when required evidence is missing or a
deterministic condition fails. No LLM call was added, so RULE 1 has no new call
site. Security conclusions never come from a model judging its own output.

## Patch proposal and verification guardrail

The patch roles are deliberately inert:

- no target file is read or written;
- no diff is applied;
- no validation command or test is run;
- no `subprocess`, `runpy`, `eval`, `exec`, `compile`, `os.system`, or write API
  is imported/called;
- no commit, push, merge, or deployment is attempted;
- every proposal/report states `applied=False`, `executed=False`, and
  `requires_human_or_permission_gateway=True`.

The focused test supplies Python code that would write an execution marker if
run. It verifies that the marker is absent and the target file is unchanged
after both roles process the payload. The same test performs an AST check for
execution and write primitives.

## Permission entries pending independent review

The following sixteen **new GREEN proposals** were added to `core/config.py`
and explicitly flagged there for pending independent review. Each handler is
local, in-memory analysis with zero target/system/business-data mutation and
zero external effect; successful work uses only standard `AgentBase` HP
accounting. No existing tier was changed or loosened:

`patch_proposal_brief`, `patch_proposal_check`,
`patch_verification_brief`, `patch_verification_check`,
`scan_inventory_brief`, `scan_inventory_check`, `scan_load_brief`,
`scan_load_check`, `scan_research_brief`, `scan_research_check`,
`scan_verification_brief`, `scan_verification_check`,
`identity_trust_brief`, `identity_trust_check`,
`automation_governance_brief`, and `automation_governance_check`.

No new action was classified YELLOW or RED. A RED-worthy executor was not
built; any real patch application or code execution remains outside these
agents and must use a separately authorized existing path.

## NEEDS_HUMAN disclosures

1. **Blockchain Security Auditor was not built.** Repository-wide extension and
   toolchain searches found no Solidity, Vyper, Move, Cairo, Foundry, Hardhat,
   Truffle, or Brownie audit subject. Creating an auditor here would be a fake
   persona with nothing VECTOR can verify. Add it only when real smart-contract
   code and an approved deterministic toolchain are in scope.
2. **Patch application remains human/PermissionGateway work.** The generator
   and verifier intentionally cannot apply, execute, commit, merge, or publish
   their output.
3. **Cryptographic identity verification is not performed by the new analyst.**
   It validates IDs, scopes, expiry, and the presence/result of independent
   signature evidence supplied by an existing verifier. Building key issuance,
   rotation, revocation, or a new crypto trust root would be a separate
   security architecture decision.
4. **Security research sources must be supplied.** `ScanResearcher` checks
   provenance and cross-domain corroboration but does not browse or treat a
   model response as evidence. An approved research path or a human must supply
   the advisories.
5. **The sixteen GREEN entries need the independent permission review required
   by `SELF_DEV_AGENT_SPEC.md`.** They are listed above and commented in code.
6. **Exact upstream `claude-security/*` persona text was unavailable.** Scope
   for those nine names was inferred conservatively; the existing scan and
   redaction matches were preferred over speculative aliases.
7. **The requested local commit is blocked by this session's filesystem
   policy.** `git add` failed because Git tried to create
   `V.E.C.T.O.R. Codebase/.git/worktrees/p3-security-manual/index.lock`, while
   that parent-repository metadata is read-only to this session. No staging,
   commit, push, merge, or branch change occurred. A human or a session with
   write access to the parent `.git` directory must stage these nine files and
   create the local commit.

## Risks and limitations

These agents prove properties of the supplied data, not the truth of an
untrusted caller's claims. In particular, a reported test result or signature
result remains caller evidence; the reports label whether execution or
cryptographic verification occurred locally (both false). The safe failure
mode is `needs_human`, not an inflated verified claim.

## Verification evidence

Verification performed in this worktree:

- Red test: `pytest tests/test_security_specialists.py -q` failed at collection
  before implementation because the module did not exist.
- Focused tests: `pytest tests/test_security_specialists.py -q` passed all 10
  tests, including eight parametrized agent cases, manifest/tier/route checks,
  and the patch non-execution proof.
- Relevant routing/permission/A2A regression set: `pytest tests/test_security_specialists.py
  tests/test_security_agents_are_agentbase.py
  tests/test_governor_unknown_task_gate.py
  tests/test_v1_trust_t3_permission_vocabulary.py
  tests/test_a2a_conformance_all_districts.py -q` passed after updating the
  stale exact Security-agent count from 12 to 20 and asserting the eight new
  names explicitly — **62 passed**.
- Security-district regression set: `pytest tests/test_security_specialists.py
  tests/test_security_agents_are_agentbase.py
  tests/test_security_district_run_wiring.py
  tests/test_security_status_nonblocking.py tests/districts/security
  tests/integration/test_spec04_siem.py tests/unit/test_security_modules.py -q`
  — **167 passed**.
- `python districts/security/security_specialists.py` passed its real
  missing-evidence smoke check for all eight agents and exited 0.
- `python tests/test_security_specialists.py` passed all 10 tests through the
  test file's own `__main__` block.
- `python tests/test_security_agents_are_agentbase.py` passed all 7 tests
  through that edited file's own `__main__` block.
- `ruff check districts/security/security_specialists.py
  tests/test_security_specialists.py tests/test_security_agents_are_agentbase.py`
  passed.
- `python -m compileall -q districts/security/security_specialists.py
  tests/test_security_specialists.py` exited 0.
- `git diff --check` completed without whitespace errors (Git emitted only its
  Windows LF-to-CRLF advisory).

No dependency, database-schema, credential, deployment, commit, push, merge,
or branch change was made. The working-tree changes remain unstaged because of
the read-only Git metadata boundary described above.

## Addendum, 2026-09-29 (later follow-up pass) — 9th agent added, then relocated + independent Codex review

A 9th agent, `SlackArchaeologist` (`slack_archaeology_brief`/`slack_archaeology_check`), was added
to this district in a follow-up pass — real, deterministic Slack-history reconstruction (duplicate-id,
missing-author/timestamp, bad-timestamp, and dangling-thread-reference checks over caller-supplied
message records, no LLM call). This briefly brought the district to 9 agents / 18 GREEN permission
entries.

**Relocated to `chief_of_staff` later the same day**: re-reading `SELF_DEV_AGENT_SPEC.md`'s own district
map (not a new judgment call, the spec's own text) showed `slack-archaeologist` explicitly listed under
`chief_of_staff/`, not `security` — a placement error on the original build, corrected while the agent
was still brand-new (same day, no accumulated dependents, low risk to move). Now lives at
`districts/chief_of_staff/slack_archaeologist.py`; this district is back to its original **8 agents /
16 GREEN permission entries** — the "eight"/"sixteen" counts above are accurate again, not stale. Full
detail: `VECTOR_TECHNICAL_KNOWLEDGE/SELF_DEV_PROGRAM_SUMMARY.md`.

The independent Codex review this package's own report called for (section above) was completed
2026-09-29, while `SlackArchaeologist` still lived here: **no code-level security concern found** —
verified no dangerous primitives (subprocess/eval/exec/os.system/file-write) anywhere in
`security_specialists.py`, all specialists confirmed deterministic/evidence-gated with no
LLM-self-judging path, and all GREEN entries confirmed to match at the time. Codex's own read-only
sandbox had no writable temp directory, so it could not execute `pytest` itself (a sandbox limitation,
not a code issue — Claude already ran the full test file successfully, see the "Actually run" section
above); its overall verdict label was therefore `CANNOT_VERIFY` on the test-execution sub-point
specifically, while the code-level finding itself was
clean. Full writeup: `VECTOR_TECHNICAL_KNOWLEDGE/CODEX_REVIEW_2026-09-29_CORE.md`.

## Addendum — follow-up pass, 2026-09-30

Owner approval was given in chat the same day (asked why this disclosure couldn't be resolved by
Claude or Codex; the honest answer led to re-reading it more literally). The original disclosure
above ("no Solidity, Vyper, Move, Cairo, Foundry, Hardhat, Truffle, or Brownie audit subject" exists
in VECTOR) was correct and remains true — VECTOR still has no smart contracts of its own. But the gap
was never a missing *external* data source (a live chain RPC, an explorer API); it was that nothing
existed for VECTOR to check. Every other specialist in this district checks CALLER-SUPPLIED evidence,
not VECTOR's own state — the same model applies here: a real check over Solidity source a caller
supplies is buildable without any live blockchain dependency at all.

Built `BlockchainSecurityAuditor` (`contract_scan_brief`/`contract_pattern_check`) in
`districts/security/security_specialists.py`: a deterministic, bounded text-pattern scan aligned to
the SWC Registry (Smart Contract Weakness Classification) — the same reference industry static
analyzers like Slither cite. Six checks: SWC-103 floating pragma, SWC-104 unchecked `.call()` return
value, SWC-106 unprotected `selfdestruct`, SWC-107 reentrancy ordering (state write after an external
call, via a bounded brace-balance function splitter, not a real Solidity parser), SWC-115 `tx.origin`
used for authentication, and an unguarded-sensitive-function check (mint/pause/setOwner/... with no
visible access-control marker) restricted to names that are almost always meant to be owner/role-gated
— deliberately excluding ambiguous self-service names like `withdraw`/`burn` that are frequently and
legitimately public with only a caller-scoped balance check, to avoid a false-positive-prone guess.

Honestly scoped: this is a first-pass heuristic linter, not a compiler-based static analyzer or formal
verification, and the returned report says so explicitly (`analysis_scope` field). It flags patterns
for human review and never certifies a contract safe. Validated against real safe and vulnerable
Solidity samples before wiring: zero false positives on a checks-effects-interactions-ordered,
`nonReentrant`-guarded, `onlyOwner`-gated safe contract; all 6 planted defects caught, with correct
line and function attribution, on a deliberately vulnerable one.

Wiring: 1 new manifest entry under `security:`, 2 new `DISTRICT_TASK_MAP` routes, 2 new GREEN
permission-tier entries (flagged for the pending independent review; no existing tier touched).
Verified directly against `_canonical_district_from_task_type()` before finalizing the action names —
no word-overlap collision with the `status_check_report` fixture. Tests: 2 new (13 total in the file,
all pass) — the planted-defect proof plus a static check confirming the module never imports
web3/httpx-to-a-chain-explorer, matching the "no live dependency" claim. Manifest re-parses clean: 41
districts, 268 agents, zero duplicate keys.
