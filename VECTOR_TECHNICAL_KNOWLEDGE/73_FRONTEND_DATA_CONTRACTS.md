# Task 73 — Frontend Data Contracts

Typed-interface reference for the three panels added in Task 73, and for the backend work each one's
dark/unknown state is waiting on. No backend endpoint listed as "required" here was created,
stubbed, or faked — this is a contract, not an implementation.

Format follows the task's own convention:
```ts
interface XDataProvider { ... }
```

---

## 1. Memory Explorer

### 1.1 Currently real (already existed before this task, reused as-is)

```ts
// GET /memory/recent?limit=N   — confirmed real, already polled by backend.js
interface EpisodicMemoryResponse {
  memories?: EpisodicEvent[];
  events?: EpisodicEvent[];        // alternate key some callers check
  items?: EpisodicEvent[];         // alternate key some callers check
}
interface EpisodicEvent {
  event_type: string;
  content: string;
  timestamp: string;               // ISO 8601
}

// GET /brain/reasoning/chains?limit=N   — confirmed real, already polled by backend.js
interface ReasoningChainsResponse {
  chains?: DecisionRecord[];
  decisions?: DecisionRecord[];
}
interface DecisionRecord {
  action?: string; action_type?: string; summary?: string;
  score?: number;
}

// GET /brain/epistemic/summary   — confirmed real (referenced in widgets.js's
// existing brainpanel endpoint list, line ~991) — response shape NOT
// independently verified against a live payload this task (§17 of the
// evolution doc). Memory Explorer's countPath function defensively checks
// three possible shapes and degrades to "—" if none match, rather than
// throwing or fabricating a number.
interface EpistemicSummaryResponse {
  beliefs?: unknown[];
  count?: number;
}
```

### 1.2 Required future backend work (does NOT exist today — do not fake)

```ts
// NOT IMPLEMENTED. Proposed shape only.
interface SemanticMemoryStatusProvider {
  getStatus(): Promise<{
    row_count: number;
    checkpoint_keys: string[];        // e.g. loop:current_goal, loop:last_decision, loop:agent_hp
    last_write_per_key: Record<string, string /* ISO timestamp */>;
    // Explicitly does NOT need to expose "learning" — Task 71/72 already
    // established this table is a checkpoint store, not a learning store.
  }>;
}

interface PolicyMemoryStatusProvider {
  getStatus(): Promise<{
    entry_count: number;
    top_entries: Array<{ action_type: string; situation_hash: string; avg_reward: number; sample_count: number; last_updated: string }>;
    // A future, honest UI would show sample_count prominently NEXT TO
    // avg_reward specifically so a viewer can see when an average has
    // become effectively frozen (Task 72 §2.1) — not just the number alone.
  }>;
}

interface CounterfactualMemoryStatusProvider {
  getStatus(): Promise<{
    rejection_count: number;
    scenario_count: number;
    top_rejected: Array<{ action_type: string; occurrence_count: number; first_seen: string; last_seen: string }>;
    // occurrence_count / first_seen / last_seen do not exist in the current
    // schema (Task 72 §6.F proposes adding them) — this endpoint cannot be
    // built honestly until that schema change happens, which is explicitly
    // gated on the experiment concluding.
  }>;
}

interface SkillMemoryStatusProvider {
  getStatus(): Promise<{ row_count: number } | null>;
  // Returns null / "not found" if no writer exists — Task 72 §J states this
  // is genuinely unknown, not merely unexposed. The frontend must be able
  // to represent "unknown whether this even exists" as distinct from "known
  // to be empty."
}
```

## 2. Cognition Panel

### 2.1 Currently real (reused)
`/brain/goals` (GOALS stage), `/brain/reasoning/chains` (DECISION stage), `/gateway/pending`
(PERMISSION stage) — all pre-existing, all already polled elsewhere in the app.

### 2.2 Required future backend work, per stage

```ts
// NOT IMPLEMENTED for any of the 7 stages below. Proposed shape only —
// deliberately uniform across stages so the panel can render them generically.
interface CognitionStageSignal {
  stage: 'OBSERVATION'|'CONTEXT'|'MEMORY'|'CANDIDATES'|'SCORING'|'ACTION'|'OUTCOME'|'LEARNING';
  state: 'idle'|'active'|'complete'|'blocked'|'failed'|'degraded'|'unknown';
  last_event_at: string | null;      // ISO timestamp, null if never observed
  detail?: string;                    // short, human-readable, e.g. "3 candidates scored"
  evidence_ref?: string;              // e.g. an experience_id (Task 72 §7) once that exists
}
interface CognitionPipelineProvider {
  getStageSignals(): Promise<CognitionStageSignal[]>;
}
```

**Why these 7 specifically have no live source today (traced, not assumed):**
- OBSERVATION / CONTEXT: `world_state`/`ContextEngine.track_beliefs()` runs every think_tick but has
  no dedicated read endpoint exposing "did a fresh observation happen this cycle."
- MEMORY (as a pipeline *stage*, distinct from the Memory Explorer's per-subsystem view): no endpoint
  distinguishes "a retrieval occurred this cycle" from "a retrieval occurred at some point."
- CANDIDATES / SCORING: `decision_engine`'s own `candidate.reasoning_chain` (Task 72 §3/§7) already
  contains exactly this information in-process, but nothing persists or exposes it per-cycle today.
- ACTION / OUTCOME: partially inferable from `gateway_audit` (via `/gateway/pending`'s sibling,
  a not-yet-existing `/gateway/recent`), but no such endpoint exists yet.
- LEARNING: would need the Task 72 §7 state-change log, which does not exist.

## 3. Experiment Observatory

### 3.1 Currently real (reused)
`/status` (uptime), `/loop/status` (tick count), `/inference/stats` (best-effort call count),
`/security/status` (best-effort `audit_log` length as a proxy for "gateway events in the current
in-memory window" — explicitly NOT the same as a true segment-lifetime count, since `audit_log` here
is whatever the security subsystem currently holds in memory, not a filtered "since Segment 2 started"
query).

### 3.2 Required future backend work (the actual Experiment Observatory this panel is named for)

```ts
// NOT IMPLEMENTED. This is the single most valuable piece of backend work
// this task identified as deferred — it would let the Experiment Observatory
// panel become what its name promises, rather than a proxy view assembled
// from unrelated general-purpose endpoints.
interface ExperimentSegmentProvider {
  getCurrentSegment(): Promise<{
    experiment_id: string;              // e.g. "exp61-segment2-20260903"
    segment_label: string;              // e.g. "Segment 2"
    started_at: string;                 // ISO timestamp
    day0_watermarks: {
      gateway_audit_seq: number;
      inference_calls_count: number;
      episodic_count: number; semantic_count: number; policy_count: number;
      reasoning_chains_count: number; skill_count: number; agent_history_count: number;
    };
  } | null>;                            // null if no segment is formally declared

  getDeltasSinceDay0(): Promise<{
    gateway_events: number;
    green: number; yellow: number; red: number; forbidden: number; unknown: number;
    inference_calls: number;
    unique_action_types: string[];      // "candidate/action-repertoire diversity"
    episodic_delta: number; semantic_delta: number; policy_delta: number;
    reasoning_chains_delta: number;
    // Deliberately does NOT include a single "learning score" — per Task 72,
    // no such honest scalar exists; any future UI here must keep the
    // Level 0-7 distinction (Task 72 §5) rather than collapsing it.
  }>;

  getAutonomyLabeling(): Promise<{
    telemetry_labeled_autonomous_calls: number;   // is_autonomous=1 in inference_calls
    behaviorally_inferred_unattended_calls: number; // caller_id pattern match, per Task 66's own method
    // These two numbers are EXPECTED to differ (Task 65-66 already showed
    // this for Segment 1). A future UI must render them as two separate
    // numbers, never averaged or reconciled into one.
  }>;
}
```

## 4. Cross-Cutting Contract Rules (apply to all future work in this area)

1. **Never return a fabricated value for a field with no real source.** Return `null`/omit the field
   and let the frontend render its own "NO LIVE SOURCE" state — the pattern already used by all three
   panels shipped this task.
2. **Never let a "count" field imply causation or influence.** Per Task 72 §5's Level ladder, a count
   is Level-0/1 evidence at most. Any future endpoint that wants to expose Level-2+ evidence (a
   retrieval that demonstrably influenced a decision) must say so explicitly in its own field name
   (e.g. `confirmed_influenced_decision: boolean`), never imply it via a bare count being nonzero.
3. **Autonomous vs. user-triggered must always be two fields, never one.** Per §3.2's
   `getAutonomyLabeling()` — this is not a style preference, it is a direct response to a confirmed
   measurement gap (Task 65 §4, Task 71).
4. **All of §1.2, §2.2, and §3.2 are explicitly deferred until after the 7-day experiment concludes**,
   per this task's own absolute rule against backend runtime changes during Segment 2.
