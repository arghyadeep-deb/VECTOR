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

## Addendum, 2026-09-29 (later follow-up pass) — 9th agent added + independent Codex review

A 9th agent, `SlackArchaeologist` (`slack_archaeology_brief`/`slack_archaeology_check`), was added
to this district in a follow-up pass — real, deterministic Slack-history reconstruction (duplicate-id,
missing-author/timestamp, bad-timestamp, and dangling-thread-reference checks over caller-supplied
message records, no LLM call). Full details: `VECTOR_TECHNICAL_KNOWLEDGE/SELF_DEV_PROGRAM_SUMMARY.md`.
This brings the district to **9 agents / 18 GREEN permission entries** — the "eight"/"sixteen" counts
above describe this package's original scope and are historically accurate for that point in time, not
stale; they simply predate the addendum.

The independent Codex review this package's own report called for (section above) was completed
2026-09-29: **no code-level security concern found** — verified no dangerous primitives
(subprocess/eval/exec/os.system/file-write) anywhere in `security_specialists.py`, all 9 specialists
confirmed deterministic/evidence-gated with no LLM-self-judging path, and all 18 GREEN entries
confirmed to match. Codex's own read-only sandbox had no writable temp directory, so it could not
execute `pytest` itself (a sandbox limitation, not a code issue — Claude already ran the full test file
successfully, see the "Actually run" section above); its overall verdict label was therefore
`CANNOT_VERIFY` on the test-execution sub-point specifically, while the code-level finding itself was
clean. Full writeup: `VECTOR_TECHNICAL_KNOWLEDGE/CODEX_REVIEW_2026-09-29_CORE.md`.
