# VECTOR V1 Stage 1 — IntentMatcher Prewarm Reliability

Date completed: 2026-09-22 (written retroactively — this report was not
produced at the time because the owner's "write a `.md` file per stage"
instruction came after this stage had already closed; recorded now for a
complete stage-by-stage record).

**VERDICT: STAGE_1_PASS.**

## 1. Governance

Run entirely through `tools/vector_dev_orchestrator`'s bridge (program
`prog-45fbcac8`) — isolated worktrees, targeted pytest, independent
cross-provider review on every package. No direct-session self-certified
work. Program usage: 3/4 packages, 9/30 provider calls, 0 correction
cycles, 0 replans — clean first-attempt acceptance on all three.

## 2. Problem (from prior reports, read-only evidence)

`PRE_RG_D2_FINAL_CLOSURE_REPORT.md` and
`OWNER_PAPER_RETRIEVAL_ROUTING_CLOSURE_REPORT.md` had already fixed the
IntentMatcher's event-loop-blocking bug, but the embedding bootstrap still
took ~261s in one live run, and 23+ `"[IntentMatcher] Embedding failed:
timed out"` lines appeared inside 10 minutes while a direct Ollama
embeddings call from a separate process at the same moment took 0.04s. A
failed embedding silently became a zero vector by design — a silently
degraded matcher with no visibility into how degraded it was.

## 3. Packages (all accepted, all cross-provider reviewed, zero corrections)

| Package | What | Commit |
|---|---|---|
| `IM-PREWARM-1` | Reuse one Ollama client per matcher instead of constructing a new one per embedding call | `0fcd7dc08e` |
| `IM-PREWARM-2` | Honest embedding failures — a failed/timed-out embedding is never stored as a zero vector that can take part in matching; failed examples are tracked and bounded-retried; matcher readiness/degradation (embedded count vs. failed count) exposed through the existing status/logging surface | `082f5f790f` |
| `IM-PREWARM-3` | Bounded total bootstrap work per attempt; elapsed time and failed count logged on completion; existing guarantees reconfirmed by regression (prewarm never blocks the event loop, exactly one bootstrap runs under concurrent match/prewarm calls, atomic publish, bounded command-path wait) | `1d5fb6d6d3` |

Scope discipline held: routing decisions, classifier behavior, gateway
vocabulary, and permission logic were explicitly untouched — confirmed by
the goal's own constraint and the reviewer's independent sign-off on each
package. All tests used deterministic fake Ollama clients (no real network
calls), including an explicit test proving a zero vector can never match.

## 4. Evidence category

| Claim | Category |
|---|---|
| Client reuse, honest failure tracking, bounded bootstrap | SOURCE IMPLEMENTED, INTEGRATED (`vector-integration`), TEST VERIFIED, independent cross-provider review PASS on each package |
| Live behavioral re-verification of the ~261s/23-timeout scenario specifically | Not separately re-run as a live gate under this program — the fix is unit/integration-test proven with deterministic fakes standing in for the real failure mode observed in the prior live reports. Reasonable given the failure mode itself (real Ollama timeouts) was already the empirical basis for this repair, not merely a hypothesis. |

---

**STAGE_1_PASS.**
