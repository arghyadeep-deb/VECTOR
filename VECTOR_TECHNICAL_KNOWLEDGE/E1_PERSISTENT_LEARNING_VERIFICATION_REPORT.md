# E1 — Persistent Learning Verification

**Starting HEAD:** `f2703ff6673321fd816aca91e4078768ab92d8eb` (the R10 checkpoint). Clean tree, no
stale worktree, confirmed before starting.

## Question

Can VECTOR demonstrate: experience → persistent update → retrieval → changed future decision — using
the REAL existing `DecisionEngine`, `PolicyMemory`, and its real SQLite persistence, with no
architecture modification, no hidden state, and no candidate injection beyond what a real
`evaluate()` call already accepts?

## Method

No production code was modified for this stage — R1–R10 already established that
`PolicyMemory.get_score()`/`update_from_outcome()` is the real, correctly-identified (post-R4/R5)
reward-learning signal feeding `DecisionEngine._score_candidate()`'s `W_POLICY` (20%) term. E1's job
was to construct a genuine, controlled behavioral experiment proving this signal actually survives a
real restart and actually changes a real ranking — not to re-audit or re-wire anything.

`tests/test_e1_persistent_learning.py` (standalone, isolated `VECTOR_DB_PATH`, same convention as
`tests/test_task89c_goal_progress.py` and `tests/test_r10_decision_provenance.py`) runs the exact
8-step experiment specified:

1. **Baseline decision**: candidates `e1_action_a` (confidence 0.62) vs `e1_action_b` (confidence
   0.60), no policy history yet. `A` wins (sanity check on the real 5-factor formula).
2. **Real outcome for A, repeatedly bad**: `PolicyMemory.update_from_outcome("e1_action_a", hash,
   0.05)` × 8 — the same production write path `autonomous_loop._act_on()` uses after every real
   action, called directly here (no `_act_on()` needed since only the policy signal, not the whole
   action pipeline, is under test).
3. **Legitimate update, confirmed**: `get_score()` afterward is verified to be genuinely below
   `PolicyMemory.DEFAULT_SCORE` — the real reward moved the real learned value.
4. **Close persistence**: `core.memory.episodic.close_db_connection()` — a real connection close, not
   a mock.
5. **Reopen**: a brand-new `DecisionEngine` + `PolicyMemory` instance pair, same db file — this is a
   genuine simulated restart, not a re-used in-memory object.
6. **Same decision**: identical candidates (`e1_action_a` conf 0.62, `e1_action_b` conf 0.60),
   freshly constructed objects.
7. **Winner changed**: `e1_action_b` now wins.
8. **Update caused it**: `e1_action_a`'s `policy_score` after restart is asserted to equal (within
   0.01) the exact score recorded before closing the connection — not reset to `DEFAULT_SCORE`, not
   independently recomputed.

Three controls, each its own test:
- **Unrelated situation unaffected**: a distinct action_type/params pair, never touched by A's
  learning, still resolves to `DEFAULT_SCORE` and its own natural winner.
- **Duplicate updates don't amplify**: 20 identical `reward=0.3` updates converge to `0.3` (a correct
  online average), not something larger — proving the mechanism does not runaway under repetition.
- **An update recorded before a restart is neither lost nor double-counted**: two updates before a
  simulated restart + one after all average correctly to the same value across the boundary.

## Results

**All 4 tests pass.** The winner genuinely flips (`e1_action_a` → `e1_action_b`) as a direct,
provable consequence of a real, persisted, restart-surviving reward signal — using the real
production `DecisionEngine`/`PolicyMemory` code, the real SQLite write/read path, and the real
5-factor scoring formula. No candidate was injected outside `evaluate()`'s normal contract, no
scorer was altered for the experiment, and no winner was hardcoded — the winner in each run is
whatever the real formula computes.

## Classification

| Level | Achieved? | Evidence |
|---|---|---|
| L0 — storage | ✅ | `update_from_outcome()` persists to `policy_memory`, confirmed via direct `get_score()` read after write |
| L1 — retrieval | ✅ | `get_score()` returns the exact persisted value, confirmed across a real connection close/reopen |
| L2 — influence | ✅ | `policy_score` genuinely participates in `_score_candidate()`'s weighted total (pre-existing, R1-R7 work; re-confirmed here) |
| L3 — persistent learning | ✅ | The updated value survives a real restart and is read back unchanged, confirmed by exact-value assertion, not just "still exists" |
| L4 — adaptation (LAB) | ✅, **explicitly LAB-scoped** | The winner demonstrably changes (`A`→`B`) *because of* the prior persisted experience, in a controlled experiment with hand-constructed candidates. This is **not** a claim about VECTOR's real production candidate stream — see Explicit Non-Claims. |
| L5 — generalization | ❌ Not attempted, not claimed | E1 never tests whether learning about one situation transfers to a genuinely different one — that would require real candidate diversity in production (E6's own question), which this stage deliberately did not touch |

## Explicit non-claims

This result does **not** prove:
- that VECTOR's real, production candidate-generation pipeline ever naturally produces two
  meaningfully different action types for the same context (that is E6's explicit, separate
  question — this experiment hand-constructed both candidates);
- general learning, adaptation, or generalization in the strong sense forbidden by this pipeline's
  HONESTY RULE;
- that this specific magnitude of reward difference (`0.05` × 8 vs. a `0.02` raw-confidence gap) is
  representative of real production reward magnitudes — the experiment was deliberately tuned so the
  effect is unambiguous and reproducible, not to model realistic production dynamics.

The correct claim, and the only one made here: **VECTOR's policy-learning mechanism (`PolicyMemory` ↔
`DecisionEngine`) is a real, persistent, restart-surviving signal that can and does change which of
two hand-constructed candidates wins, when their prior outcomes genuinely differed** — an L3/L4(LAB)
result, not a production-behavior claim.

## Regression

No production code changed in this stage. The new test file was verified to collect cleanly as part
of the full suite (no collection errors) while, like its two predecessors in this session, requiring
standalone execution for its own assertions to be meaningful (shared `VECTOR_DB_PATH` singleton
constraint).

## Final verdict

```
STARTING HEAD: f2703ff6673321fd816aca91e4078768ab92d8eb
EXPERIMENT: PASS -- winner flips (A->B) after real, persisted, restart-surviving reward signal
CONTROLS: 3/3 PASS (unrelated unaffected, duplicate does not amplify, pre-restart update not lost)
IMPLEMENTATION: none (zero production code changes -- verification only)
CLASSIFICATION: L0-L3 PROVEN; L4 PROVEN AT LAB SCOPE ONLY (explicitly not a production claim);
                L5 not attempted
NEW REGRESSIONS: 0 (no production code changed)
VERDICT: E1 COMPLETE
```

**FINAL HEAD:** recorded after commit, below.
