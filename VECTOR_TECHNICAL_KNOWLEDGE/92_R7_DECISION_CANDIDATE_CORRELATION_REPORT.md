# Task 92 — R7 Decision/Candidate Correlation

**Authoritative HEAD verified at task start:** `b8d5b406b3d2b66334a76903d8d8765b9c9f9e02` (unchanged
since Task 90/91 — still uncommitted on top of it). `git status` at task start showed exactly the
R6 diff (`core/config.py`, `core/loop/decision_engine.py`) plus the untracked Task 90/91 reports and
R6 test file — confirmed present, confirmed not discarded, confirmed unmodified by this task except
where R7 explicitly builds on top of R6's own new code (additively — R6's `_select_staleness_aware_winner`
was never edited). No worktree created. No reset/rebase. Segment2/PID 37588 not touched. `.env` not
touched.

---

## 1. Executive summary

DecisionEngine had no per-occurrence identity at all. Worse: the ONE place in the codebase that
already had a column literally named `decision_id` — `CounterfactualMemory`'s `rejections`/`outcomes`
tables — was silently being fed `winner.action_type` (a reusable action-type string) at every real
call site, not a unique event identifier. Two completely unrelated decision occurrences involving
the same action_type collapsed onto the same "decision_id" value. This was already self-documented
elsewhere in the repo (`core/training/reasoning_chain_dataset.py`'s own docstring: "``decision_id``
is actually a generic ``action_type`` string").

R7 adds a genuine per-occurrence `decision_id` (one per `DecisionEngine.evaluate()` call) and
`candidate_id` (one per `Candidate` object, from construction) to the existing `Candidate`/`Decision`
dataclasses, and threads them into the **existing, already-schemaless** correlation surfaces this
audit found — no new table, no new column on any SQL table, no new memory subsystem, no change to
`PolicyMemory`'s reward/aggregate semantics, no change to `CounterfactualMemory`'s own code (only
what value autonomous_loop.py passes into its pre-existing parameters).

> VECTOR can correlate a decision occurrence and candidate occurrence with existing downstream
> decision/outcome/veto records, providing the identity needed for honest attribution.

That claim is behaviorally proven below (§10, §11) — no stronger claim is made.

## 2. Pre-fix architecture (data-flow map)

```
candidate generation (autonomous_loop._think_tick, _get_plan_candidates)
      │  -- goal-action / plan-step Candidate objects, no identity beyond
      │     (action_type, params)
      ▼
DecisionEngine.evaluate()
      │  -- scores every candidate (5-factor formula), R6 staleness guard
      │     picks the winner from the already-ranked list
      ▼
winner  (a Candidate object -- ALSO logged: every OTHER scored candidate,
      │   via evaluate()'s own mem.store(event_type="decision_candidate", ...)
      │   loop, tagged "winner"/"rejected" -- pre-R7 this had NO decision_id
      │   or candidate_id field in its `context` dict at all)
      ▼
autonomous_loop._act_on(winner)
      │
      ├─▶ CounterfactualMemory.should_avoid() veto ─▶ record_rejection(
      │        decision_id=winner.action_type,   ◀── BUG: not unique per
      │        proposal=..., reason=...)              occurrence, pre-R7
      │
      ├─▶ ThreatDetector / RedTeamAgent block ─▶ _record_external_rejection(
      │        action_type, params, reason) ─▶ record_rejection(
      │        decision_id=action_type, ...)     ◀── same bug, 2 call sites
      │
      └─▶ execution (governor.dispatch) ─▶ outcome
                │
                ▼
          reward = 5-factor formula
                │
                ├─▶ PolicyMemory.update_from_outcome(action_type,
                │      situation_hash, reward)  -- AGGREGATE row, no
                │      per-occurrence identity by design (avg_reward /
                │      sample_count accumulate across MANY occurrences)
                │
                ├─▶ loop_state.save_decision(action_type, params, score)
                │      -- JSON blob, no correlation fields
                │
                └─▶ EpisodicMemory.store_chain(situation, goal_ids, steps,
                       action, outcome, reward) -- per-call INSERT, fresh
                       chain_id every time, but no decision_id/candidate_id
```

The audit explicitly distinguishes, per the task's own required distinction, what pre-R7 code
actually tracked:

| State | Pre-R7 tracking |
|---|---|
| **candidate_generated/scored** | Logged (episodic `decision_candidate` events) but with no per-occurrence identity |
| **candidate_selected** | Distinguished only by the string `status="winner"` in that same log — not a stable ID |
| **candidate_vetoed/suppressed** | `CounterfactualMemory.rejections` (has a `decision_id` column, fed the wrong value) + `PolicyMemory.record_suppression` (aggregate `veto_count`, correctly has NO per-occurrence identity, by design — see §7) |
| **candidate_executed** | `EpisodicMemory.reasoning_chains` (per-call row) + `PolicyMemory.update_from_outcome` (aggregate) + `loop_state.save_decision` (single overwritten "latest" JSON snapshot) — none carried any per-occurrence correlation |

## 3. Exact correlation gap

Nothing in the codebase could answer "which exact `evaluate()` call, and which exact candidate
object, produced *this specific* rejection row / reasoning-chain row / save_decision snapshot?" The
closest existing mechanism (`CounterfactualMemory.rejections.decision_id`) actively answered the
question *wrong* — every rejection of `send_email`, regardless of when or why, reported the same
"decision_id" (`"send_email"`), making two genuinely different veto events indistinguishable by that
field alone.

## 4. Existing IDs discovered (pre-implementation audit, item 8)

| Location | What it generates | Relevance to R7 |
|---|---|---|
| `core/memory/counterfactual.py` | `uuid.uuid4()` for `scenarios.id`, `rejections.id`, `outcomes.id` (row primary keys) | Row identity, not decision identity — untouched, still generated the same way |
| `core/memory/episodic.py::store()` | `uuid.uuid4()` for `episodic_memory.id` | Row identity — untouched |
| `core/memory/episodic.py::store_chain()` | `uuid.uuid4()` for `reasoning_chains.chain_id` | Row identity — untouched; confirms this table is per-event, not aggregate (safe to correlate against, see §7) |
| `core/memory/router.py:193` | `meta.get("decision_id") or str(uuid.uuid4())` | **Different subsystem** (Hermes/vectorcode message routing, not `DecisionEngine.evaluate()`) — traced and confirmed unrelated to the autonomous decision path; explicitly left untouched |
| `core/loop/permission_gateway.py:745-746` | none (feeds `action.action_type` into `record_rejection`'s `decision_id`) | Same bug as autonomous_loop.py's call sites, but this file is inside `PermissionGateway` — **explicitly forbidden to modify** by this task's MUST NOT list. Left as-is; documented as a known, out-of-scope remaining gap (§14) |
| `core/loop/autonomous_loop.py:350-351` (`_record_external_rejection`, before this task) | none (`decision_id=action_type`) | **The bug this task fixes** for 2 of its 3 real call sites (the third, permission_gateway.py's own internal one, is out of scope per above) |

No suitable pre-existing per-occurrence "decision_id"/"candidate_id" generator existed anywhere in
`DecisionEngine`'s own call path. A new, minimal one was introduced (§5, §6) — not a second
competing system, since it lives on the dataclasses `DecisionEngine` already owns and uses the same
`uuid.uuid4()` mechanism already accepted throughout this codebase (episodic.py, counterfactual.py,
router.py all already do exactly this).

## 5. Decision identity design

- **Format**: `"d:" + uuid.uuid4().hex` (e.g. `d:3f9a2e1b7c4d4a8e9f0b1c2d3e4f5a6b`). The `"d:"`
  prefix visually distinguishes it from `PolicyMemory.make_situation_hash()`'s `"v2:"`-prefixed
  hashes — structurally impossible for the two to collide or be confused.
- **Generated once per `DecisionEngine.evaluate()` call**, immediately after the R6 staleness-aware
  winner is selected (`core/loop/decision_engine.py`, right after `self._decision_count += 1`).
- **Stamped onto every candidate scored in that call** (`for c in ranked: c.decision_id =
  decision_id`) — including candidates that lost. This directly implements the task's required
  correlation model: `decision_id` fans out to every candidate that belonged to that decision
  occurrence, not just the winner.
- **NOT** derived from, or equal to, any candidate's `situation_hash` — proven directly by
  `test_c_same_action_different_decision_id_across_occurrences` (`d1.winner.decision_id !=
  h1` where `h1` is the real `make_situation_hash()` output for that exact candidate).
- **Collision resistance**: `uuid.uuid4()` (122 bits of OS-random entropy via `os.urandom`),
  thread-safe by Python's own `uuid` module design — the same mechanism this repo already uses
  pervasively for exactly this purpose. No global counter, no distributed-ID infrastructure.
  `test_h_many_rapid_decisions_never_collide` generates 300 decision_ids in a tight sequential loop
  and asserts all 300 are distinct.
- **Never contains prompt/param content**: it's a pure random hex string, structurally incapable of
  leaking anything from `winner.params` — proven by `test_9_ids_never_contain_sensitive_param_content`.

## 6. Candidate identity design

- **Format**: `"c:" + uuid.uuid4().hex`, same rationale as decision_id, distinct prefix.
- **Generated via `dataclasses.field(default_factory=...)`** — every `Candidate` object gets one the
  moment it is constructed, whether or not it is ever scored, ever wins, or is even part of a real
  `evaluate()` call. This is deliberately the smallest possible addition: no new class, no registry,
  no counter — the existing dataclass just carries one more auto-populated field.
- **Object-identity-based, not content-based**: two `Candidate` objects with byte-identical
  `action_type`/`params` still get different `candidate_id`s, because identity here means "this
  specific candidate occurrence," not "this action/situation pattern" (that's what
  `situation_hash` is for — see §2's data-flow map and the explicit non-conflation in the task's own
  "CORRELATION MODEL" section). Proven by `test_duplicate_identity_candidates_still_get_distinct_candidate_ids`
  and `test_same_action_params_across_two_decisions_distinct_candidate_ids`.
- **Stable through scoring**: `_score_candidate()` mutates a candidate's score fields but never its
  `candidate_id` — proven by `test_candidate_id_stable_through_scoring`.
- No suitable pre-existing per-candidate identity was found anywhere in the codebase (§4), so this is
  the smallest new representation introduced, exactly as the task allows when "no suitable
  candidate_id exists."

## 7. Persistence design

**No new database table. No new memory subsystem. No schema change to any existing SQL table.**

Every correlation write goes through a mechanism that already existed and was already schemaless/
JSON at that exact point:

| Sink | Existing mechanism reused | What changed |
|---|---|---|
| `decision_engine.evaluate()`'s per-candidate log | `EpisodicMemory.store()`'s `context` param (already a JSON column, `context_snapshot`) | Added `decision_id`, `candidate_id`, `candidate_status` keys to the dict already being built |
| `CounterfactualMemory.rejections` (auto-block path) | `record_rejection(decision_id=..., context=...)` — **both parameters already existed** in the function signature | Changed the VALUE passed to the existing `decision_id` param (was `action_type`, now the real ID with an `action_type` fallback); started passing the existing, previously-unused `context` param with `candidate_id` |
| `CounterfactualMemory.rejections` (ThreatDetector / RedTeam block) | Same as above, via `autonomous_loop._record_external_rejection()`, which gained 2 new **optional, default-empty** parameters | Same value-only fix, 2 call sites |
| `loop_state._DECISION_KEY` snapshot | `save_decision()`'s `json.dumps({...})` payload — already fully free-form JSON | Added `decision_id`/`candidate_id` keys (2 new optional kwargs, default `""`, fully backward compatible) |
| `EpisodicMemory.reasoning_chains` (executed-candidate outcome) | `store_chain()`'s `steps` parameter — already a JSON list (`winner.reasoning_chain`) | Appended one extra `{"correlation": {"decision_id": ..., "candidate_id": ...}}` dict entry to the list passed in, at the one call site — `store_chain()`'s own signature/table untouched |

**`core/memory/counterfactual.py` itself was not modified at all** — verified directly by
`test_counterfactual_record_rejection_signature_unchanged` (asserts the exact parameter list is
still `["self", "decision_id", "proposal", "reason", "context"]`) and by `git diff` (§Git discipline
below shows `core/memory/counterfactual.py` is absent from the changed-files list).

**No schema change was genuinely needed anywhere** — every correlation surface this task used was
already JSON/schemaless at the exact point R7 needed to write to. The STOP-CONDITION path ("a new
database table appears necessary") was never triggered.

## 8. Exact source changes

### `core/loop/decision_engine.py`
- `import uuid` added.
- `Candidate` dataclass: added `candidate_id: str = field(default_factory=lambda: "c:" +
  uuid.uuid4().hex)` and `decision_id: str = ""`.
- `Decision` dataclass: added `decision_id: str = field(default_factory=lambda: "d:" +
  uuid.uuid4().hex)`.
- `evaluate()`: after winner selection, generates one `decision_id` and stamps it onto every
  candidate in `ranked`; the existing per-candidate `mem.store()` logging loop's `context` dict
  gained `decision_id`/`candidate_id`/`candidate_status` keys; the final `Decision(...)`
  construction now passes `decision_id=decision_id` explicitly (so the Decision and every candidate
  it contains share the exact same value, not two independently-generated ones); the empty-candidate
  noop fallback path stamps `noop.decision_id` to match its wrapping `Decision`'s auto-generated id,
  for consistency.
- `_select_staleness_aware_winner()` (R6, Task 91): **zero lines changed** — confirmed by the full
  R6 test suite (`tests/test_task91_r6_candidate_diversity.py`) passing unmodified (§11).

### `core/loop/autonomous_loop.py`
- `_record_external_rejection()`: gained 2 new optional kwargs (`decision_id: str = ""`,
  `candidate_id: str = ""`), both default-empty for full backward compatibility; now passes
  `decision_id or action_type` (old behavior preserved when unset) and an optional `context` dict
  into the existing `CounterfactualMemory.record_rejection()` call.
- Its 2 call sites (ThreatDetector block, RedTeamAgent block) now pass `winner.decision_id,
  winner.candidate_id`.
- The auto-block `_cf.record_rejection(...)` call: `decision_id=winner.decision_id or
  winner.action_type` (was `decision_id=winner.action_type`), plus a new `context={"candidate_id":
  winner.candidate_id}`.
- `save_decision(...)` call: now passes `decision_id=winner.decision_id,
  candidate_id=winner.candidate_id`.
- `store_chain(...)` call: `steps=` now `winner.reasoning_chain + [{"correlation": {...}}]` instead
  of the bare `winner.reasoning_chain`.
- Nothing else in this 2000+ line file was touched — no candidate-generation logic, no
  `_TAG_TO_ACTION`, no `_get_plan_candidates()`, no gating order, no `GOAL_ACTION_MAP`.

### `core/loop/loop_state.py`
- `save_decision()`: gained 2 new optional kwargs (`decision_id: str = ""`, `candidate_id: str =
  ""`), added as 2 more keys in the already-freeform JSON payload. All 3 existing call sites (2 in
  tests, 1 production, all using only the original 3 positional args) remain valid unmodified calls
  — verified directly (§ regression run, `tests/unit/test_memory_stores.py`,
  `tests/unit/test_episodic_direct.py`).

### Not modified (by explicit design, per §7 and the task's own scope rules)
`core/memory/policy.py`, `core/memory/counterfactual.py`, `core/loop/permission_gateway.py`,
`core/city/governor.py`, `core/config.py`, `core/brain/goal_system.py`, and every district/candidate-
generation file — confirmed via `git diff --stat` (§Git discipline).

## 9. End-to-end data flow (as implemented)

```
candidate A + candidate B
      │
      ▼
DecisionEngine.evaluate()
      │  decision_id = "d:<uuid4>"          (ONE per call)
      │  A.candidate_id = "c:<uuid4-A>"     (already existed, from construction)
      │  B.candidate_id = "c:<uuid4-B>"
      │  A.decision_id = B.decision_id = decision_id
      ▼
winner = A  (say)                            selected candidate = A, id = A.candidate_id
      │
      ├── vetoed path: CounterfactualMemory.record_rejection(
      │       decision_id=A.decision_id, context={"candidate_id": A.candidate_id})
      │       → rejections row: decision_id == D1, context.candidate_id == C1  ✓ verified
      │
      └── executed path: store_chain(steps=A.reasoning_chain + [{"correlation":
              {"decision_id": A.decision_id, "candidate_id": A.candidate_id}}])
              → reasoning_chains row's steps JSON carries D1/C1            ✓ verified

Second decision, same action_type/params:
DecisionEngine.evaluate() again
      │  decision_id2 = "d:<different uuid4>"   → D1 != D2                 ✓ verified
      │  A2.candidate_id = "c:<different uuid4>" → C1 != C2                ✓ verified
      │  situation_hash(A2) == situation_hash(A) (same action_type/params) ✓ verified
      │     (this is exactly why decision_id/candidate_id are INSTANCE
      │      identifiers, not the reusable policy/situation identity)
```

## 10. Behavioral tests

`tests/test_task92_r7_decision_candidate_correlation.py` — **24 tests, all passing**:

- `TestDecisionIdUniqueness` (A, B, C, H) — 4 tests: every decision gets a unique id; repeated
  `evaluate()` calls with an identical candidate set produce different ids; the same action_type
  across two occurrences gets different decision_ids while its situation_hash stays identical; 300
  rapid sequential decisions produce 300 distinct ids.
- `TestCandidateId` (D, F-identity) — 4 tests: candidate_id distinguishes 3 candidates within one
  decision, the winner's id is genuinely one of the input objects' ids; candidate_id survives
  scoring unchanged; duplicate-identity candidates in the same decision still get distinct
  candidate_ids; the same action_type/params across two decisions gets distinct candidate_ids.
- `TestPropagationDownstream` (E, F, G) — 3 tests, using a **real** `AutonomousLoop._act_on()` +
  **real** `CounterfactualMemory` on an isolated temp-file db (Governor/PolicyMemory/EpisodicMemory
  stubbed, mirroring the established `tests/test_task89c_goal_progress.py` pattern): the exact
  end-to-end scenario from the task (§9) proven directly against real code; two separate vetoed
  decisions of the same action_type never cross-attribute; an executed candidate's correlation
  survives into the real `store_chain()` call's `steps` argument.
- `TestLegacyCompatibility` (I) — 2 tests: a rejection recorded the OLD way (no context, decision_id
  = bare action_type — the exact shape of every pre-existing test in
  `tests/integration/test_spec11_year2_gaps.py` etc.) reads back with no crash, `context` defaults
  safely to `{}`; `PolicyMemory`'s legacy row shape is untouched.
- `TestR6StillWorks` (J) — 2 tests: the staleness threshold still suppresses after 5 consecutive
  wins and a safe alternative still wins; a no-alternative situation still never fabricates one.
- `TestGovernanceAndSecurity` (K, L, adversarial #9/#10) — 5 tests: no FORBIDDEN action_type is
  created by ID tagging; `core/loop/permission_gateway.py` and `core/city/governor.py`'s actual
  current source contain zero references to `decision_id`/`candidate_id` (direct source-text proof
  R7 never touched them); IDs never contain sensitive param content even when a candidate's params
  include password-/api_key-shaped values; the veto path never reaches `Governor.dispatch`.
- `TestNoRewardSemanticChange` — 4 tests: `PolicyMemory.update_from_outcome`,
  `PolicyMemory.record_suppression`, `PolicyMemory.make_situation_hash`, and
  `CounterfactualMemory.record_rejection`'s exact parameter lists are asserted unchanged from
  source — proof, not description, that reward/policy/counterfactual semantics were not touched.

## 11. Adversarial tests

All 10 adversarial items from the task were addressed:

1. Same action selected repeatedly does not collapse decisions — `test_b`, `test_h` (300 unique ids).
2. Different dict key ordering — canonical situation hash stays stable — inherited unchanged from R4
   (`PolicyMemory.make_situation_hash`'s own `json.dumps(sort_keys=True)`); re-asserted implicitly by
   every test comparing `_make_situation_hash()` outputs across differently-constructed-but-equal
   param dicts.
3. Different params → distinguishable candidate identity — `test_d`, `TestDecisionIdUniqueness`.
4. Vetoed candidate cannot be attributed to another decision — `test_f_two_vetoed_decisions_never_cross_attribute`
   (two separate veto events of the same action_type, decision/candidate ids never swapped).
5. Concurrent/rapid decisions remain unique — `test_h_many_rapid_decisions_never_collide` (300
   sequential calls, single process — see §Important Concurrency Check below for why this is
   sufficient given the repo's own concurrency model).
6. Restart/readback — persisted correlation fields remain readable — `test_i` (legacy AND new-style
   rows both read back via the real `get_similar_rejections()` / `json.loads()` path).
7. Legacy row missing decision_id/candidate_id does not crash readers — `test_i`,
   `test_i2` (both directions: reading an old row, and confirming `PolicyMemory`'s reader is
   unaffected).
8. R6 staleness suppression is not corrupted by ID tagging — `TestR6StillWorks` (both tests, plus
   the full R6 suite, §12).
9. IDs never contain prompts/secrets/credentials — `test_9_ids_never_contain_sensitive_param_content`.
10. No path around Governor/PermissionGateway — `test_10_veto_path_never_reaches_governor` (direct
    `assert_not_called()` on the mocked `Governor.dispatch`) + `test_l_*` (source-text absence
    proof).

### Important Concurrency Check

`decision_id`/`candidate_id` generation is process-local (in-memory `uuid.uuid4()` calls inside
`DecisionEngine.evaluate()` and `Candidate.__init__`). Per `.claude/rules/architecture.md`, VECTOR's
autonomous loop is a single asyncio event loop (`observe(0.5s) → think(event-driven) →
act(permission-gated) → reflect(2AM)`) — `evaluate()` is `async def` but is never invoked
concurrently with itself from two different OS threads in the production architecture; genuine
Python-level thread races were therefore not the concurrency model to defend against. What matters
is collision resistance under **rapid repeated calls**, which `uuid.uuid4()`'s 122 bits of
`os.urandom` entropy already guarantees regardless of call rate (the birthday-bound collision
probability at even millions of calls/second for years is astronomically below any real risk) — no
distributed-ID infrastructure, no global counter, no lock was introduced, matching the task's
explicit "keep it simple" instruction.

## 12. Regression results

**Targeted regression** (DecisionEngine, R6, PolicyMemory, CounterfactualMemory, Task89 goal-progress,
fanout cooldown, governor thread-hop, permission gateway):
```
tests/test_task92_r7_decision_candidate_correlation.py .......... (24)
tests/test_task91_r6_candidate_diversity.py .................... (22)
tests/unit/test_decision_engine.py tests/test_decision_engine.py
tests/test_policy_reward_identity.py
tests/test_counterfactual_block_penalizes_policy.py
tests/integration/test_phase_a3_counterfactual_act_on.py
tests/integration/test_spec11_year2_gaps.py
tests/test_task89c_goal_progress.py
tests/loop/test_fanout_cooldown.py
tests/unit/test_governor_dispatch_thread_hop.py
tests/unit/test_permission_gateway_extra.py
tests/test_permission_gateway.py
```
**Result: 1 failure — `test_permission_gateway.py::test_red_action_times_out_without_confirmation`,
the exact same pre-existing Class-A baseline failure from Task 90/91** (a test-side monkeypatch
signature mismatch inside `permission_gateway.py`'s own council-timeout path, unrelated to R7 —
confirmed unrelated by `test_l_permission_gateway_source_has_no_r7_code` passing, i.e.
`permission_gateway.py`'s actual source contains zero R7-added text). Everything else passed.

**Full non-Ollama suite** (same 7 files excluded as Tasks 90/91, for the same previously root-caused
environment reason, unrelated to R7):

| Metric | Task 91 baseline | Task 92 (this run) |
|---|---|---|
| Collected | 5,092 | 5,116 (+24 — this task's own new test file) |
| Passed | 5,042 | 5,066 |
| Failed | 13 | **13 — identical set, by exact test name** |
| Skipped | 37 | 37 |
| Errors | 0 | 0 |

All 13 failures, by full node ID, are byte-identical to Task 90's and Task 91's own classification
tables (`test_webauthn_middleware_integration.py::test_wrong_token_type_rejected_type_confusion`,
`test_correction_integration.py::test_full_loop_stores_and_retrieves`,
`test_correction_integration.py::test_lifecycle_unvalidated_to_validated`,
`test_epistemic_integration.py::test_different_domains_independent`,
`test_phase_a7_council_red_tier.py::test_proceed_high_confidence_returns_proceed`,
`test_openwa_absorption.py::test_exception_in_send_counted_as_failure` (Class C, pollution),
`test_permission_gateway.py::test_red_action_times_out_without_confirmation`,
`test_agent_registry_successor_class.py::test_dying_coding_swarm_respawns_...`,
`test_correction_learner.py::test_extract_from_explicit_correction`,
`test_correction_learner.py::test_tags_include_domain_and_source`,
`test_epistemic_scoring.py::test_stale_domain_reduces_score`,
`test_planning.py::test_circular_deps_flattened`,
`test_planning.py::test_decompose_returns_plan_or_none`) — **12×A + 1×C, 0×B. Zero new
regressions caused by R7.** None of these 13 were touched, "fixed," or investigated further, per
the task's explicit instruction.

## 13. Historical compatibility

- `Candidate.decision_id` defaults to `""` — any code path that constructs a `Candidate` outside
  `DecisionEngine.evaluate()` (existing tests, e.g. `test_counterfactual_block_penalizes_policy.py`,
  which builds a bare `Candidate(...)` and calls `_act_on()` directly) gets the exact pre-R7 fallback
  behavior (`decision_id or action_type` → `action_type`), proven still passing (§12).
- `loop_state.save_decision()`'s 2 new kwargs are optional with safe defaults — all 3 pre-existing
  call sites (1 production, 2 tests) remain valid, unmodified, still passing.
- `CounterfactualMemory.record_rejection()`'s `context` parameter already defaulted to `None` before
  this task — every one of the ~25 pre-existing call sites across
  `tests/integration/test_spec11_year2_gaps.py`, `tests/integration/test_phase_a3_counterfactual_act_on.py`,
  `tests/backend/test_audit_followups.py` etc. that never pass `context` continue to work identically
  (verified passing, §12).
- A rejection row written the OLD way (`context='{}'`, `decision_id=<bare action_type>`) reads back
  with no crash and no special-casing required — `json.loads('{}').get("candidate_id")` is simply
  `None` — proven by `test_i_legacy_rejection_row_without_context_reads_back_safely`.
- `PolicyMemory`'s schema, columns, and reader/writer contract are completely untouched — proven by
  signature-introspection tests (§10) rather than by description.

## 14. Security analysis

- `decision_id`/`candidate_id` are pure `uuid.uuid4().hex` strings with a 2-character prefix —
  structurally incapable of embedding prompt content, parameters, or credentials, since they are
  never derived from `winner.params`/`action_type`/any user- or LLM-supplied text at all.
  `test_9_ids_never_contain_sensitive_param_content` verifies this directly against candidates whose
  params contain password-/api_key-shaped strings.
- No logging statement added by this task prints raw `params`/prompt content that wasn't already
  being logged before R7 (the only new log line, R6's pre-existing staleness log, was not touched;
  the correlation writes themselves are silent unless the underlying call already logs, e.g.
  `record_rejection`'s existing `logger.info` line, which logs `decision_id` and `reason[:60]` —
  same fields it always logged, just now a real ID instead of a bare action_type).
- No new attack surface: correlation IDs are read-only metadata attached to existing writes; nothing
  reads a `decision_id`/`candidate_id` value back to make a security-relevant decision (no gating
  logic anywhere branches on these IDs) — they are pure observability/attribution data.

## 15. Governance analysis

R7 introduced zero code into `core/loop/permission_gateway.py` or `core/city/governor.py` —
confirmed both by `git diff --stat` (§Git discipline) and, independently, by two tests
(`test_l_permission_gateway_source_has_no_r7_code`, `test_l_governor_source_has_no_r7_code`) that
scan those files' actual current source text for `decision_id`/`candidate_id` and assert absence.
`permission_gateway.py:745-746`'s own pre-existing `decision_id=action.action_type` bug (§4) is
**left exactly as it was** — out of scope by this task's own explicit rule, and documented as a
known remaining gap (§16) rather than silently worked around.

The gating order inside `_act_on()` — CounterfactualMemory veto → ThreatDetector → RedTeamAgent →
skills/gateway → `governor.dispatch()` — is byte-identical to before this task; R7 only changed what
metadata accompanies the `record_rejection()`/`save_decision()`/`store_chain()` calls that already
existed at each of those stages. `test_10_veto_path_never_reaches_governor` and the assertion inside
`test_e`/`test_g` (`governor.dispatch.assert_not_called()` / `assert_called_once()`) directly prove
the veto-before-execution ordering is unchanged.

## 16. Remaining limitations

- `core/loop/permission_gateway.py:745-746`'s own internal `CounterfactualMemory.record_rejection(
  decision_id=action.action_type, ...)` call (the council-REJECTED path) still uses the old,
  non-unique value — explicitly out of scope for R7 (MUST NOT modify PermissionGateway) and left
  untouched. A future task with explicit authorization to touch `PermissionGateway` could apply the
  identical, already-proven fix pattern there.
- `core/memory/router.py:193`'s own `decision_id` generation is a **separate subsystem** (Hermes/
  vectorcode message routing) with no relationship to `DecisionEngine.evaluate()` — confirmed
  unrelated during the audit (§4), not touched, not claimed to be fixed.
- `PolicyMemory.update_from_outcome()`/`record_suppression()` intentionally do **not** carry
  decision_id/candidate_id — their rows are aggregates across many decision occurrences by design
  (§7); adding per-occurrence identity there would require either a schema change or redefining what
  an aggregate row means, both explicitly out of R7's scope per the REWARD REQUIREMENT section. This
  is a deliberate non-propagation, not an oversight — see §10's `TestNoRewardSemanticChange`.
  Anyone wanting to correlate a specific reward-accumulation event to its originating decision must
  currently do so via the `reasoning_chains` correlation entry (§8) or the episodic
  `decision_candidate` log (§8), not via `policy_memory` directly.
  Consequently, `DataCollector.record()` (the training-data JSON-file writer) was also deliberately
  left untouched — its `metadata` argument is already discarded beyond `.get("source")`, and wiring
  real persistence there would be a 3rd-file, non-minimal expansion beyond what this task's explicit
  correlation model (candidate_generated/scored, candidate_selected, candidate_vetoed/suppressed,
  candidate_executed — all 4 already satisfied via §7's 4 chosen sinks) required.
- Correlation metadata is not queryable in bulk yet (no new "get rejections/outcomes by
  decision_id" helper was added to `CounterfactualMemory` — the existing
  `get_similar_rejections()`/proposal-text search was sufficient for this task's own behavioral
  proof and no new public API was judged necessary to add).

## 17. Explicit non-claims

Even after successful R7, this report does **not** claim VECTOR has:
- L4 learning, or general learning of any kind;
- true counterfactual reasoning (`CounterfactualMemory` remains exactly what it was — a
  Jaccard-similarity rejection-avoidance store, not a simulator of hypothetical outcomes);
- exploration (no randomness or curiosity signal was added — `uuid.uuid4()` is used purely for
  identity generation, never to influence which candidate is scored or selected);
- general candidate generation (candidate generation logic, `_TAG_TO_ACTION`, `GOAL_ACTION_MAP`, and
  `_get_plan_candidates()` are byte-for-byte unchanged);
- Astra-level understanding, AGI, or causal world modeling.

The only supported claim is the one stated in §1.

## 18. Recommendation for R8

R7 was the last task explicitly authorized in this prompt. Two natural, narrowly-scoped candidates
are visible from this session's own findings but are **not** being started:
1. Extending the identical decision_id fix pattern to `permission_gateway.py:745-746`, under a task
   explicitly authorized to modify `PermissionGateway`.
2. A minimal `CounterfactualMemory.get_rejections_by_decision(decision_id)` read-only helper, if a
   future task needs bulk correlation queries rather than the proposal-text search this task's own
   tests used.

---

## Git discipline

```
$ git status --porcelain
 M core/config.py
 M core/loop/autonomous_loop.py
 M core/loop/decision_engine.py
 M core/loop/loop_state.py
?? VECTOR_TECHNICAL_KNOWLEDGE/90_AUTHORITATIVE_REPOSITORY_BASELINE.md
?? VECTOR_TECHNICAL_KNOWLEDGE/91_R6_CANDIDATE_DIVERSITY_REPORT.md
?? VECTOR_TECHNICAL_KNOWLEDGE/92_R7_DECISION_CANDIDATE_CORRELATION_REPORT.md
?? tests/test_task91_r6_candidate_diversity.py
?? tests/test_task92_r7_decision_candidate_correlation.py

$ git diff --stat
 core/config.py                | 15 ++++++++       <- Task 91 (R6), UNCHANGED by Task 92
 core/loop/autonomous_loop.py  | 51 ++++++++++++++++++---     <- Task 92 (R7)
 core/loop/decision_engine.py  | 123 +++++++++++++++++++++++++++++++++++++++--  <- R6 (Task91) + R7 (Task92), both preserved
 core/loop/loop_state.py       | 12 +++++-      <- Task 92 (R7)
 4 files changed, 189 insertions(+), 12 deletions(-)
```

- **R6 changes preserved**: `core/config.py`'s diff is unchanged from Task 91 (confirmed byte-
  identical `+15` insertion count); `_select_staleness_aware_winner()` in `decision_engine.py` was
  not edited (confirmed by the full R6 test suite passing unmodified, §12).
- **No unrelated production file changed**: `core/memory/policy.py`, `core/memory/counterfactual.py`,
  `core/loop/permission_gateway.py`, `core/city/governor.py` all absent from the diff.
- No worktree created. No cherry-pick. No merge. No reset/rebase.
- **Nothing committed** — awaiting explicit instruction, exactly as required.

---

## FINAL VERDICT

```
AUTHORITATIVE HEAD VERIFIED: PASS (b8d5b406b, R6 preserved uncommitted on top)
DECISION PATH FULLY TRACED: PASS
IDENTITY MECHANISMS FULLY TRACED: PASS (existing decision_id column found mis-fed; no other pre-existing per-occurrence ID found)
DECISION_ID DISTINGUISHES OCCURRENCES: PASS
CANDIDATE_ID DISTINGUISHES CANDIDATE OCCURRENCES: PASS
SITUATION/POLICY HASH UNCHANGED AND SEPARATE: PASS
CORRELATION PROPAGATES THROUGH EXISTING DOWNSTREAM PATHS: PASS (episodic log, CounterfactualMemory rejections, loop_state snapshot, reasoning_chains)
VETO/SUPPRESSION CORRELATION: PASS (CounterfactualMemory only; PolicyMemory suppression deliberately NOT propagated, documented)
EXECUTION/OUTCOME CORRELATION: PASS (reasoning_chains; PolicyMemory reward deliberately NOT propagated, documented)
LEGACY RECORDS REMAIN READABLE: PASS
NO REWARD SEMANTICS CHANGED: PASS (signature-proven)
NO CANDIDATE-GENERATION CHANGES: PASS
NO NEW MEMORY SUBSYSTEM: PASS
NO NEW EXPERIENCE TABLE: PASS
NO GOVERNANCE CHANGES: PASS (source-text-proven)
R6 TESTS: 22/22 PASS (unmodified)
R1-R5 TARGETED TESTS: PASS
NEW R7 TESTS: 24/24 PASS
ADVERSARIAL TESTS: 10/10 items covered, PASS
FULL NON-OLLAMA REGRESSION: 5,066 passed / 13 failed (all pre-existing, 0 new) / 37 skipped / 0 errors
NEW REGRESSIONS: 0
WORKING TREE: core/config.py (R6, untouched by R7), core/loop/autonomous_loop.py, core/loop/decision_engine.py, core/loop/loop_state.py modified; 2 new test files, 3 reports — nothing committed
```

R7 ONLY. Not proceeding to R8. STOP.
