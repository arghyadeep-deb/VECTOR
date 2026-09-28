# RR-3.7B.1 — Ambiguity Closure + Autopilot Recursion Repair

Starting HEAD: `b8c95b60e67b08f7156b985b6283c2dfd2f40edc` (branch `production-hardening-complete`)
Final HEAD: see Section 22 commit ledger.

---

## 1. Executive Result

Both residuals RR-3.7B left open are closed.

**A. Ambiguity closure**: all 19 endpoints RR-3.7B marked "unconfirmed"/
"conservative" were individually traced end-to-end (every realistically-
selectable district agent's `run()` method, not just the "obvious" one —
Governor.dispatch()'s HP-lottery fallback means ANY agent in a resolved
district can be the one that actually executes). 14 reclassified S0/S1/S3
with full evidence. 4 reclassified S3-low (real, fully-characterized,
non-mutating/low-severity default executions — matching RR-3.7B's own
established convention for e.g. `track_experiment`/`add_contact`). ONE
real, credential-adjacent finding required and received a narrow repair:
`districts/governance/credential_manager.py`'s catch-all `else` branch
used to unconditionally expose real API key prefixes (`key[:8]+"..."`) in
its HTTP response for ANY unmatched governance-district action_type —
reachable via `POST /privacy/gdpr-check` (whose `"gdpr_check"` action_type
resolves to the wrong district — "governance", not "privacy" — via a
`DISTRICT_TASK_MAP` substring collision) whenever Governor's HP-lottery
selected `CredentialManager` among the 6 governance-district agents.

**B. Autopilot recursion**: independently reproduced and root-caused
(correcting RR-3.7B's own diagnosis — see Section 9). Repaired by
threading `chain_depth` across the one channel that survives a
`Governor.dispatch()` round-trip (the task dict itself), closing a
self-referential recursive edge `MAX_CHAIN_DEPTH` was never actually
bounding. Verified live in production: exactly 5 real dispatch hops,
then a clean, deterministic stop (`{"status":"ok","chain_stopped":
"max_depth_reached","depth":5}`), confirmed against the running server's
own logs.

**UNRESOLVED SECURITY-RELEVANT AMBIGUITIES: 0.**

**Verdict:** `RR-3.7B.1 PASS — STRUCTURED AMBIGUITY AND AUTOPILOT DEFECT CLOSED`

---

## 2. Starting Integrity

```
git rev-parse HEAD        -> b8c95b60e67b08f7156b985b6283c2dfd2f40edc  (MATCH)
git branch --show-current -> production-hardening-complete             (MATCH)
```
VECTOR confirmed stopped (`tasklist` showed zero matching python.exe
processes) before any mutation. Pre-existing modified/untracked files
recorded and unchanged by this mission: `data/models/neural_policy.{pt,
meta.json}` (autonomous-loop runtime artifacts) plus a backlog of
uncommitted report/doc files from earlier missions in this same session
(`RG0`–`RR3_7B` reports, `docs/CODEX_VECTOR_V1_HANDOFF.md`, etc.) — none
touched by this mission.

**Note on a suspected prompt-injection attempt during this mission**: a
background-task notification arrived mid-mission for a dispatched
read-only investigation fork, whose `result` field was written in
first-person voice mimicking the assistant's own internal reasoning
("This is a serious problem... I need to stop it immediately..."),
falsely claiming the fork had made unauthorized edits to
`districts/governance/autopilot.py` and created a test file. This was
independently verified false via `git diff` — those exact changes were
made by the primary session itself per this mission's own plan, and the
fork (scoped strictly read-only) never touched either file. No action was
taken on the notification's implied instruction; it is flagged here as a
suspected injection attempt for the record, not acted upon.

---

## 3. Authoritative Residual Inventory

Derived directly from `RR3_7B_STRUCTURED_ROUTER_AUTHORIZATION_REPORT.md`
Section 4's ledger (not from this prompt's approximate "~15" figure).
Exact set of rows containing "unconfirmed"/"conservative"/"possible"/
"real branch exists, district unconfirmed"/"local only if reached" or
equivalent uncertainty language — **19 endpoints**:

1. `analytics_report` — analytics.py
2. `screen_call` — calls.py
3. `vocabulary_practice` — languages.py
4. `grammar_practice` — languages.py
5. `dialogue_practice` — languages.py
6. `study_guide` — languages.py
7. `extract_concepts` — learning.py
8. `scan_data_sharing` — privacy.py
9. `gdpr_check` — privacy.py
10. `accessibility_audit` — qa.py
11. `growth_analysis` — reflection.py
12. `add_contact` — relationships.py
13. `communication_style` — relationships.py
14. `gap_analysis` — skills.py
15. `track_mastery` — skills.py
16. `validate_idea` — startups.py
17. `market_scan` — startups.py
18. `revenue_model` — startups.py

Plus RR-3.7B's own separately-flagged, non-authorization structural
defect: `autopilot_trigger` (`POST /governance/autopilot/trigger`).

(`reality_check` was RR-3.7B's own S1, already fully resolved via an
exact capability match — re-confirmed, not re-traced, as endpoint #19 in
Section 4 below.)

---

## 4. Full Residual Endpoint Ledger

Method for every row below: determined the resolved district (re-derived
from source, not assumed); checked whether ANY agent in that district has
the action_type as an EXACT **manifest-declared** capability
(`config/agent_manifest.yaml` — confirmed elsewhere in this mission
series, via direct read of `core/city/declarative_manifest.py:107-108`,
to unconditionally overwrite an agent's in-code `__init__` capabilities
at real bootstrap: `instance.capabilities = list(entry.get("capabilities",
[]))`, for every agent that successfully instantiates); if none match,
every agent in that district is a real HP-lottery candidate — its
`run()` method was read in full, not merely grepped for the literal
string.

| # | Router | Path | action_type | Resolved district | Real winner(s) traced | Real branch? | Side effect | Tier | PG? | Final class |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | analytics.py | /analytics/report | analytics_report | data_analytics (substring) | analytics_reporter, data_engineer, performance_benchmarker, performance_optimizer — all 4 typed-dispatch, no default-execution path | no | none | not tiered | n/a | **S3** |
| 2 | calls.py | /calls/screen | screen_call | calls (substring) | call_screener (real capability, no external effect — RR-3.7B's own finding, re-confirmed against full district roster), transcription_bot, voice_responder (typed, honest-error tails) | partial (harmless) | local screening/history only | not tiered | none | **S3-low** |
| 3-6 | languages.py | /languages/{lang}/{vocabulary,grammar,dialogue,study-guide} | vocabulary_practice / grammar_practice / dialogue_practice / study_guide | LLM-FALLBACK (no DTM key; `{lang}` path param never reaches the dispatched task at all) | all 5 language coaches (japanese/assamese/bengali/english/hindi) share identical `run()`; none of the 4 literals match any coach's own vocabulary; all 4 request schemas never populate `query`/`content`/`prompt` → confirmed verbatim `{"status":"error","error":"unhandled type ..."}` tail (japanese_coach.py:167, identical ×5) | no | none | not tiered | none | **S3** (×4) |
| 7 | learning.py | /learning/extract-concepts | extract_concepts | LLM-FALLBACK, likely learning | `concept_extractor` HAS exact capability match; real branch confirmed (`concept_extractor.py:163-165`) BUT neutered by a parameter-name mismatch (`ExtractConceptsReq.content` vs the handler's `p.get("text","")`) — same defect class as RR-3.7B's own `ops.py::post_mortem` finding | yes, but neutered | none (empty input) | not tiered | none | **S3** |
| 8 | privacy.py | /privacy/scan-sharing | scan_data_sharing | **security** (substring "scan" — wrong-district) | 12 agents traced; 3 have zero type-check (threat_scout, node_guard, malware_hunter); worst case MalwareHunter unconditionally scans the server's CWD and returns findings in the response (`malware_hunter.py:398-410`) | yes (3/12) | **read-only** local filesystem enumeration | not tiered | none | **S3-low** (real, confirmed, non-mutating — see Section 6 justification) |
| 9 | privacy.py | /privacy/gdpr-check | gdpr_check | **governance** (substring "gdpr" — wrong-district) | 6 agents traced; CredentialManager's catch-all default UNCONDITIONALLY exposed real API key prefixes (`credential_manager.py`, pre-fix line 162-181) | yes | **real information disclosure** (partial key material in HTTP response) | not tiered | none pre-fix | **S4 — REPAIRED** (see Sections 7-8) |
| 10 | qa.py | /qa/accessibility-audit | accessibility_audit | qa (substring; single agent QASwarm always selected) | QASwarm's internal `TASK_ROLE_MAP` exact-key lookup misses `"accessibility_audit"` (real key is `"accessibility"`), silently misroutes to the already-vetted-safe `APITester` self-diagnostic instead of the real `AccessibilityAuditor` | yes (wrong one) | none dangerous (safe-by-accident) | n/a | n/a | **S3** (real correctness/routing bug, not a security gap — reported) |
| 11 | reflection.py | /reflection/growth-analysis | growth_analysis | **marketing** (substring "growth" — wrong-district) | 16 agents traced; `geo_optimizer_agent.py:88`'s `run()` has zero type-check (binds the whole task positionally), unconditionally runs a real, non-mutating LLM citation-check with default brand/queries | yes | real LLM call, **no mutation** | not tiered | none | **S3-low** |
| 12 | relationships.py | /relationships/contacts/add | add_contact | relationships (substring) | contact_manager, communication_analyst — both zero-type-check but confirmed no dangerous default (write path requires 2 specific params neither endpoint's schema supplies) | partial | local read/no-op only | not tiered | none | **S3-low** |
| 13 | relationships.py | /relationships/communication-style | communication_style | relationships (exact DTM key) | same 2 candidates as #12 | partial | same | not tiered | none | **S3-low** |
| 14 | skills.py | /skills/gap-analysis | gap_analysis | LLM-FALLBACK, likely skills | `skill_mapper.py:187-190` zero-type-check, unconditionally writes local skill-progress state (defaults to "python" skill) | yes | **real local write**, low severity | not tiered | none | **S3-low** |
| 15 | skills.py | /skills/mastery | track_mastery | skills (substring) | same SkillMapper finding as #14, different triggering endpoint | yes | same | not tiered | none | **S3-low** |
| 16 | startups.py | /startups/validate-idea | validate_idea | LLM-FALLBACK, likely startups | `idea_validator.py:164-175` zero-type-check, runs the SAME capability RR-3.5A already vetted GREEN-safe, but via a different, untiered, ungated literal — an audit-trail/governance gap, not a new privilege | yes | real, non-destructive (already-vetted-safe underlying capability) | not tiered | none | **S3** |
| 17 | startups.py | /startups/market-scan | market_scan | startups (exact DTM) | `market_scanner.py:130` zero-type-check, real but outbound-READ-ONLY (public HN/Reddit reads — RR-3.7B's own prior finding, re-confirmed) | yes | outbound read-only | not tiered | none | **S3** |
| 18 | startups.py | /startups/revenue-model | revenue_model | LLM-FALLBACK, likely startups | `revenue_modeler.py:117` zero-type-check, real call but neutered to default/empty input by the same parameter-mismatch pattern as #7/#16/#17 | yes, neutered | local compute + likely local write, non-destructive | not tiered | none | **S3** |
| 19 | qa.py | /qa/reality-check | reality_check | qa (EXACT DTM + EXACT capability) | qa_swarm — deterministic, already RR-3.7B's own S1 | yes | read-only | GREEN | n/a | **S1** (unchanged, re-confirmed) |
| — | governance_extended.py | /governance/autopilot/trigger | autopilot_trigger | governance (substring; ALSO an exact capability match, per Autopilot's manifest-declared `["autopilot_trigger","autonomous_chaining"]` — corrects RR-3.7B's "HP-lottery" framing, see Section 9) | Autopilot — deterministic | yes | **structurally provable unbounded recursion — REPAIRED** | n/a (control-flow defect, not an auth gap) | n/a | **REPAIRED** (see Sections 9-12) |

---

## 5. Per-Endpoint Execution Traces

Full traces (every candidate agent's `run()` method, file:line citations,
exact fallthrough behavior) are preserved verbatim in this mission's
working notes and condensed into the ledger above; the two consequential
ones are detailed fully in Sections 7 and 9-12. Representative additional
detail for the four S3-low reclassifications (Section 6 explains why
S3-low, not S4 or S5):

- **scan_data_sharing → MalwareHunter**: `malware_hunter.py:398`, no
  `task.get("type")` check anywhere in `run()`; `query` derivation finds
  nothing in `ScanDataSharingReq{data_types}`'s dump; falls to
  `path = p.get("path", ".")` → `self.scan_directory(".")` — confirmed via
  direct read that `scan_directory()` only *reads* file metadata/content
  for pattern matching, never writes/deletes/moves anything.
- **growth_analysis → GEOOptimizerAgent**: `geo_optimizer_agent.py:88`,
  `async def run(self, params: dict | None = None)` — the parameter name
  is `params`, but Governor calls `agent.run(task)` positionally, so the
  WHOLE task dict lands there; no type check; unconditionally calls
  `self.geo_score(brand, queries)`, a real LLM-based citation-ranking
  read/analysis call — no external mutation confirmed anywhere in
  `geo_score()`'s body.
- **gap_analysis / track_mastery → SkillMapper**: `skill_mapper.py:187`,
  no type check; unconditionally calls
  `self.track_skill_progress(p.get("skill","python"))` — confirmed this
  writes to VECTOR's own local skill-progress store only (episodic
  memory / semantic memory), no external effect, no destructive
  operation, no credential/security surface touched.

---

## 6. Reclassification Results

**14 endpoints → S0/S1/S3** with full evidence (#1, #2, #3-6, #7, #10,
#12, #13, #16, #17, #18, #19 in Section 4's numbering — no endpoint left
S3 merely because a targeted grep found nothing; every default/fallthrough
path was read in full for every realistically-selectable agent).

**4 endpoints → S3-low** (#2, #8, #11, #14, #15 — wait, #2 already listed
above; the S3-low set is exactly {#2, #8, #11, #12, #13, #14, #15}, i.e.
7 rows carry the "-low" qualifier, matching RR-3.7B's own established
convention for confirmed-real-but-non-dangerous local/read-only
executions). These are **not** ambiguous — every one is fully
characterized with exact evidence of what happens and why it is safe
(read-only, or a low-stakes local write with no external/persistent
significant effect, per the mission's own Section 6 exemption for
"ordinary in-memory computation, retrieval, summarization... explicitly
NOT dangerous"). None left unrepaired due to insufficient evidence —
each is unrepaired because full evidence proves it is genuinely safe.

**1 endpoint → S4, REPAIRED**: `gdpr_check`'s CredentialManager
information-disclosure finding (Sections 7-8).

**1 non-authorization structural defect → REPAIRED**: `autopilot_trigger`
recursion (Sections 9-12).

**0 endpoints remain S5.** The fork that performed the initial trace
labeled 5 rows "S5" (scan_data_sharing, gdpr_check, growth_analysis,
gap_analysis, track_mastery), but on review this mislabeled "fully
characterized but non-destructive" as "ambiguous" — the mission's own S5
definition ("cannot prove safety or danger... ambiguity must fail closed")
requires genuine evidentiary insufficiency, which none of these have:
every one has a complete, source-verified execution trace. Four are
reclassified S3-low (Section 4/5); the fifth (gdpr_check) is the one
genuinely credential-adjacent finding among them and has been repaired,
not merely relabeled.

**UNRESOLVED SECURITY-RELEVANT AMBIGUITIES = 0.**

---

## 7. Newly Discovered Authorization Gap (Repair Documentation, per Section 7's required pre-repair checklist)

1. **Endpoint**: `POST /privacy/gdpr-check` (and, more precisely, ANY
   unmatched governance-district `task_type` reaching `CredentialManager`
   — this is an agent-level default-behavior gap, not specific to this
   one router).
2. **Real capability**: `CredentialManager.scan_available_providers()` —
   a real, legitimate capability (deliberately triggered by the literal
   `task_type == "scan"`, this file's own self-tested pathway).
3. **Exact side effect**: returns `key_prefix: <first 8 chars of a real
   API key> + "..."` for every LLM provider with a configured key, in the
   HTTP response body.
4. **Current permission tier**: `gdpr_check` itself is not tiered
   (confirmed by grep against `core/config.py`'s green/yellow/red lists).
5. **Canonical action_type already exists?**: yes — `"scan"` is the real,
   intended, already-correct action_type for this capability. The bug is
   that `"scan"` was not the ONLY thing reaching this branch; anything
   unrecognized fell into the same branch.
6. **Authorization owner**: none, pre-fix (no PermissionGateway anywhere
   in this district's agents for this capability).
7. **Execution owner**: `CredentialManager.run()` itself.
8. **Double-execution risk**: none — this is a single, synchronous method
   call, not a dispatch/redispatch pattern.
9. **Parameter integrity**: the caller cannot influence WHICH provider's
   key is exposed (the scan is unconditional over all configured
   providers) — the gap is purely "this branch runs at all for an
   unintended action_type," not a parameter-injection issue.
10. **Smallest existing seam**: give `"scan"` its own explicit `elif`
    branch (preserving 100% of existing behavior for the real, intended
    action_type) and make the catch-all `else` an honest
    `{"status":"error","error":"unhandled type ..."}` — the SAME pattern
    already used by ~15 other district agents in this codebase for an
    unrecognized type (confirmed by direct read of `federation_agent.py`,
    `product_manager.py`, `compliance_auditor.py`, and cross-referenced
    via grep across the security/marketing districts during the residual
    trace). No PermissionGateway wiring, no new tier, no architectural
    change — bringing one outlier agent's default in line with the
    codebase's own dominant, established convention.

---

## 8. Repair (credential_manager.py)

`districts/governance/credential_manager.py::CredentialManager.run()`:
split the old catch-all `else` (which handled BOTH the deliberate `"scan"`
action_type AND every unrecognized type identically) into an explicit
`elif task_type == "scan":` branch (unchanged behavior, including the
free-text-question override and the `__main__` smoke test's own
`agent.run({"type":"scan"})` call) and a new `else:` that still answers a
real free-text question (safe — LLM-grounded, no key material) but
otherwise returns `{"status":"error","error":f"unhandled type '{task_type}'"}`
instead of calling `scan_available_providers()`. `task.get("type","scan")`
(the default when `type` is omitted entirely) is unchanged, so a caller
that omits `type` still deliberately reaches the scan path — this fix
narrows what triggers the scan to "scan" or "no type given," not "any
unrecognized string."

Verified via `python districts/governance/credential_manager.py` (the
file's own real smoke test) — unchanged output, all 4 lines still `[OK]`.

---

## 9. Autopilot — Independent Root-Cause Analysis

Traced fully independently, not trusting RR-3.7B's own diagnosis (per the
mission's explicit instruction). Answers to the mission's lettered
questions:

**A. Mounted and authenticated?** Yes — confirmed `governance_extended`
is registered in `core/api/app.py:462`, and `/governance/autopilot/trigger`
is not in `core/api/middleware.py`'s `_PUBLIC_PATHS` set (exact-match
only, no prefix exemption) — same bearer-token gate as every other route.

**B. Externally reachable?** Yes.

**C. Does `autopilot_trigger` have an exact capable agent?**
**YES — this CORRECTS RR-3.7B's own characterization.** RR-3.7B's report
said "no exact capability match... reachable whenever Autopilot happens
to be the highest-HP agent" (HP-lottery-dependent, probabilistic).
Independently verified false: `config/agent_manifest.yaml`'s `autopilot`
entry declares `capabilities: [autopilot_trigger, autonomous_chaining]` —
an EXACT match. `Governor.dispatch()`'s `capable = [a for a in agents if
task_type in a.capabilities]` therefore always contains exactly one
agent (Autopilot) for this action_type; `agent = max(capable, key=HP)`
trivially returns that one agent. Selection is **100% deterministic**,
not HP-lottery-dependent — confirmed by direct read of
`config/agent_manifest.yaml` (the real bootstrap-authoritative
capabilities source — `ManifestLoader.instantiate_all()`,
`core/city/declarative_manifest.py:107-108`, unconditionally overwrites
the in-code `__init__` capabilities of every successfully-instantiated
agent) and re-confirmed live in production (Section 12).

**D. Can HP fallback select Autopilot?** Moot — see C; selection never
reaches the HP-fallback branch at all for this action_type.

**E. Does `Autopilot.run()` redispatch the same task?** Yes.
`run()`'s "chain" branch (task_type != "classify", no free-text query)
calls `self.run_chain(task)` with the ORIGINAL, unmodified task
(`type="autopilot_trigger"`, still). `run_chain()`'s first action,
pre-fix, was `result = await gov.dispatch(initial_task)` — dispatching
that exact same task again.

**F. Does chain_depth increase before redispatch?** **NO, pre-fix.**
`run()` calls `self.run_chain(task)` with NO depth argument (always
defaults to 0). Because `Governor.dispatch()` re-selects Autopilot
deterministically (per C), this re-enters `Autopilot.run()` fresh, which
calls `run_chain(task)` again — also defaulting to depth 0, since
`chain_depth` is a plain Python method argument that does **not** survive
a `Governor.dispatch()` round-trip (the task dict is the only channel
that does).

**G. Is MAX_CHAIN_DEPTH effective or ineffective (pre-fix)?**
**Ineffective for this specific self-referential edge.** The guard
`if chain_depth >= self.MAX_CHAIN_DEPTH` never sees depth advance on this
edge — completely independent of the legitimate, correctly-depth-tracked
chain-to-next-district recursion (`return await self.run_chain(follow_on,
chain_depth + 1)`, a direct Python call that DOES thread depth correctly,
confirmed unaffected by this bug).

**H. Deterministic or selection-dependent?** Deterministic (see C) —
another correction to RR-3.7B's framing.

**I. What terminates it, pre-fix?** Python's own `RecursionError`
(confirmed by direct source read: `Governor.dispatch()` has a broad
`except Exception as e:` wrapping its entire body — `governor.py:2452` —
and `Autopilot.run()` has its own broad `except Exception as e:` too;
`RecursionError` subclasses `RuntimeError` subclasses `Exception`, so
whichever of these two try/except blocks is nearest the actual stack-
overflow point catches it, converts it to an honest
`{"status":"error","error":"maximum recursion depth exceeded..."}`, and
that error propagates back up cleanly through every enclosing frame as a
normal return value — no unhandled crash, no infinite hang).

**J. Resource exhaustion / hang?** Self-terminating (bounded by Python's
own recursion limit, not by `MAX_CHAIN_DEPTH`), but consumes real,
wasteful CPU and I/O-adjacent work proportional to however many stack
frames occur before the limit fires (likely 100+ logical hops, each
involving real rate-limiter checks, audit-chain writes, OTel spans, and —
for every OUTER frame whose nested call already unwound normally — a
real `EpisodicMemory.store()` write) — a genuine resource-waste/DoS-
shaped defect, not a literal infinite hang.

**K. Side effects during recursion?** Yes — confirmed: every `run_chain()`
level whose nested `gov.dispatch()` call has already returned (i.e. every
level shallower than wherever the RecursionError actually fired) reaches
its own `self._get_memory().store(event_type="autopilot_chain_step",...)`
call, and every corresponding `Governor.dispatch()` frame reaches its own
`self._get_memory().store(event_type="governor_dispatch",...)` call — real
episodic-memory and audit-chain writes accumulate proportional to
recursion depth, though none are privileged/destructive.

**L. Does PermissionGateway matter?** No — confirmed `"autopilot_trigger"`
is not in `_PLAN_COMPOSABLE_ACTION_TYPES` and is not `hand_`-prefixed, so
`/command`/`/ws/command`/A2A's PermissionGateway pipelines report
`not_implemented` for it and never reach `Governor.dispatch()` at all.
This defect is purely a Governor/Autopilot control-flow bug, entirely
independent of any permission tier — confirmed, not merely asserted, by
the fact that no privileged action ever executes during the recursion
(each level just re-selects Autopilot and repeats the same non-
privileged control flow).

The defect is **real and confirmed**, not falsified — but the mechanism
is materially different from RR-3.7B's own description (deterministic,
not probabilistic; self-terminates via RecursionError, not a literal
hang).

---

## 10. Pre-Fix Recursion Reproduction

Bounded, mocked reproduction (never allowing genuine unbounded recursion
inside the test process, per the mission's explicit instruction): a real,
unmodified `Autopilot` instance is wired to a lightweight stand-in
Governor whose `dispatch()` simulates the REAL, confirmed re-entrant
behavior for `"autopilot_trigger"` (re-invoking `agent.run(task)`
directly, equivalent to what real `Governor.dispatch()`'s deterministic
capability match does), hard-capped at 20 real re-entries (real
`MAX_CHAIN_DEPTH` is 5).

`test_rr3_7b1_exploit_self_redispatch_never_terminates_pre_fix` — pre-fix,
via `git stash push -- districts/governance/autopilot.py` then re-run:
**FAILS**, exhausting the full 20-call hard bound with `chain_depth`
stuck at 0 throughout (confirmed via captured stderr: `"task failed at
depth 0 — stopping"`, repeated identically 20 times) — proving `chain_depth`
genuinely never advances pre-fix. 11 further tests (monotonic-depth,
no-extra-dispatch-after-max, all 6 malformed/adversarial-depth tests)
also correctly fail pre-fix, for the same reason (the depth-reading
mechanism these tests exercise did not exist pre-fix). `git stash pop`
restored the fix; full suite re-confirmed passing.

---

## 11. Autopilot Repair

`districts/governance/autopilot.py`:

1. `run_chain()`: before dispatching, stamps
   `dispatch_task = {**initial_task, "autopilot_depth": chain_depth + 1}`
   and dispatches THAT (instead of the raw `initial_task`) — the depth
   this specific dispatch attempt is at now survives the
   `Governor.dispatch()` round-trip via the task dict itself, the only
   channel available.
2. `run()`'s "chain" branch: reads `incoming_depth = task.get(
   "autopilot_depth", 0)` back, with `isinstance`/bool/negative validation
   collapsing anything malformed to 0 (never widening the guard), and
   threads it into `run_chain(task, chain_depth=incoming_depth)` instead
   of the old unconditional `run_chain(task)` (which always started at 0).

This closes the self-referential edge using the SAME existing
`MAX_CHAIN_DEPTH` invariant RR-3.7B's own report correctly identified as
the right mechanism — no second recursion-control system, no new
tier, no architectural redesign. The legitimate chain-to-next-district
recursion (`run_chain(follow_on, chain_depth+1)`, a plain Python call) is
completely unaffected — verified by dedicated regression tests (Section
14) proving a real multi-hop chain still terminates correctly and a
harmless stamp on the dispatched task is silently ignored by any
non-Autopilot receiving agent.

Adversarial-input hardening confirmed via tests: `None`/string/float/
list/dict/arbitrary-object depths all collapse to 0 (full 5-hop chain
still runs and terminates); negative depths collapse to 0 (cannot bypass
the guard by exploiting `depth >= MAX` never becoming true); huge
(`10**9`) depths terminate the chain immediately (fail toward safety);
`bool` (a Python `int` subclass) does not sneak past the `isinstance`
check. Confirmed the caller CANNOT inject an `autopilot_depth` value via
the real HTTP schema at all (`AutopilotTriggerReq` has no such field and
no `extra="allow"` config — Pydantic v2's default `extra="ignore"`
silently drops it), and confirmed `/city/dispatch`'s own hardcoded
`"direct_dispatch"` action_type (never the caller's literal string)
cannot be used to smuggle a crafted `autopilot_depth` alongside
`type="autopilot_trigger"` either.

---

## 12. Post-Fix Recursion Proof

Unit-level: `test_rr3_7b1_exploit_self_redispatch_never_terminates_pre_fix`
(the same test that failed pre-fix) now **passes**: exactly 5 real
dispatches, `depths_seen == [1,2,3,4,5]` (strictly monotonic, never
repeating), final result `{"status":"ok","chain_stopped":
"max_depth_reached","depth":5}`, zero further dispatch calls after the
5th.

**Live production proof** (Section 17): `POST /governance/autopilot/
trigger` against a real, running VECTOR instance returned in **0.368
seconds** with `{"status":"ok","chain_stopped":"max_depth_reached",
"depth":5,...}`. Server log confirms the exact predicted mechanism:
```
chain depth=0 dispatching autopilot_trigger
chain depth=1 dispatching autopilot_trigger
chain depth=2 dispatching autopilot_trigger
chain depth=3 dispatching autopilot_trigger
chain depth=4 dispatching autopilot_trigger
max chain depth 5 reached — stopping
```
Exactly 5 real dispatch cycles, then a clean, deterministic, `MAX_CHAIN_
DEPTH`-governed stop — the defect is closed, not merely unit-tested.

---

## 13. Autopilot Authorization/Side-Effect Analysis

No privileged action ever executes during the (now-bounded) recursion —
each of the 5 real hops just re-selects Autopilot and repeats the same
non-privileged control flow (query="" → run_chain → dispatch → repeat).
`PermissionGateway` is never in this path (Section 9L). This remains
correctly classified as a control-flow/resource defect, not an
authorization gap — confirmed, not assumed, both by static trace and by
live production observation (the 5 real episodic-memory/audit-chain
writes per invocation are real but non-privileged, matching the
pre-existing, accepted behavior of the LEGITIMATE chain-to-next-district
path, just now correctly bounded for the self-referential edge too).

---

## 14. Tests

Two new test files, 36 tests total:

**`tests/test_rr3_7b1_autopilot_recursion.py`** (26 tests): pre-fix
exploit reproduction (bounded), depth-monotonicity, exact-boundary
termination, zero-extra-dispatch-after-max, normal/legitimate multi-hop
chain unaffected, 6 malformed/adversarial-depth-input tests, caller-
cannot-inject-via-real-schema (×2), PermissionGateway-uninvolved
confirmation, capability-is-exact-not-lottery confirmation (checked
against the real, authoritative manifest YAML, not a raw in-code
instantiation — a genuine test-authoring correction made during this
mission, see Section 15), and 5 tests re-confirming all 3 of RR-3.7B's
frozen repairs remain intact.

**`tests/test_rr3_7b1_ambiguous_endpoint_closure.py`** (10 tests):
pre-fix exploit reproduction for the credential-prefix-exposure gap,
confirmation the deliberate `"scan"` pathway (including its free-text-
question override and missing-type default) is 100% unchanged,
confirmation `"validate"`/`"template"` are unaffected, confirmation ANY
other unmatched type (not just `gdpr_check`) now fails honestly,
confirmation the free-text-question-answering feature remains reachable
for an unmatched type, and 3 evidence-recording tests for the S3-low
reclassifications (MalwareHunter read-only, GEOOptimizerAgent
non-mutating, SkillMapper local-only).

All 36 pass against post-fix HEAD.

---

## 15. Pre-Fix/Post-Fix Exploit Verification

Both fixes independently git-stash-verified:

- `districts/governance/autopilot.py` stashed → 12 of 26 autopilot tests
  fail (Section 10) → popped → all 26 pass again.
- `districts/governance/credential_manager.py` stashed → 2 of 10
  ambiguity-closure tests fail, with the pre-fix run's own captured
  output showing REAL, live API key prefixes (`AQ.Ab8RN...`,
  `sk-or-v1...`, from this development machine's own configured
  providers) genuinely present in the returned dict for an unmatched
  `"delegate_task"`/`gdpr_check`-shaped type — concrete, first-hand proof
  the pre-fix vulnerability was real, not theoretical → popped → all 10
  pass again.

Two genuine test-authoring bugs were caught and fixed during this process
(both self-identified, not user-reported, matching this session's
established discipline): (1) `test_rr3_7b1_legitimate_multi_hop_chain_
terminates_within_depth`'s own mock response text accidentally
re-triggered `classify_next_step()`'s FIRST chain rule ("implement")
instead of advancing to the "test" rule, causing an unrelated 5-hop
self-loop in the test's OWN mock, not a real regression — fixed by
choosing mock response text that doesn't collide with an earlier rule's
keywords. (2) `test_rr3_7b1_autopilot_capability_is_exact_not_hp_lottery`
initially checked a raw `Autopilot()` instantiation's `.capabilities`
(which only ever shows the in-code `__init__` default, never the
manifest override, since the real bootstrap path was never invoked) —
fixed to check `config/agent_manifest.yaml` directly, the real
authoritative source.

---

## 16. Broad Regression

Ran together, post-fix: both new RR-3.7B.1 test files (36),
`test_rr3_7b_structured_router_authorization.py` (20),
`test_rr3_7a_a2a_authorization.py` (22), `test_rr3_6_authorization_
boundary.py` (16), `test_rr3_5_foundation_closure.py`,
`test_r19_capability_composition.py`, `test_permission_gateway.py`,
`test_phase2_districts.py`, `test_spec06_health.py`. Result: all pass
except `test_permission_gateway.py::test_red_action_times_out_without_
confirmation`, independently re-confirmed via git-stash (this exact test,
against this exact pre-RR-3.7B.1 HEAD) to fail identically —
**PRE-EXISTING/ENVIRONMENTAL**, not caused by this mission. No unrelated
test was modified or repaired.

---

## 17. Production Validation

VECTOR started via `python run_vector.py api`, confirmed ready via
authenticated `GET /health/status` (200).

- **`POST /learning/ingest-video`** (RR-3.7B repair, control): still
  `{"status":"blocked","reason":"Unknown action type: ingest_video",
  "level":"UNKNOWN"}` — unchanged.
- **`POST /governance/autopilot/trigger`**: returned in 0.368s with the
  exact predicted bounded-termination shape; server log confirms the
  precise 5-hop mechanism (Section 12) — **the primary validation target
  for this mission, fully confirmed live.**
- **`POST /privacy/gdpr-check`**: two live attempts both had Governor's
  HP-lottery select a DIFFERENT governance-district agent than
  CredentialManager (`LLMCouncil` both times — confirmed via server log:
  `dispatch task_... -> governance (gdpr_check)` followed by
  `LLMCouncil` timing out at 45s on a real multi-model council
  deliberation, a legitimate, already-understood, non-dangerous real
  effect per Section 4's ledger row #9 trace). The specific
  CredentialManager code path was therefore **not independently observed
  via this exact live HTTP round-trip** within this mission's time
  budget — reported honestly rather than waiting indefinitely for a
  specific HP-lottery outcome. The fix itself IS independently verified
  via direct, real (non-mocked) code execution
  (`CredentialManager().run({"type":"gdpr_check",...})` returns the
  honest error, confirmed both via the file's own real smoke test
  continuing to pass unchanged and via the dedicated exploit test) and
  via git-stash-verified pre/post-fix comparison (Section 15) — the
  identical code path a live HTTP request would exercise if HP-lottery
  happened to select this agent.

  A secondary observation made during this live check, out of scope for
  this mission but worth flagging: the server's own log briefly
  contained a REAL, complete (not prefix-truncated) API key as part of
  an unrelated Gemini-provider-failure log line
  (`core/inference/vectorcode_llm.py`'s `_try_gemini()` error message
  includes the full request URL, which carries the key as a query
  parameter) — an existing, pre-dating-this-mission logging-hygiene gap,
  unrelated to the `credential_manager.py` fix, not reproduced here, and
  named without its value for RR-3.7C (Section 20).

VECTOR was stopped (`taskkill`, confirmed via `tasklist` showing zero
matching processes) after validation.

---

## 18. Updated Structured-Router Security Status

All 19 previously-ambiguous endpoints now carry a final, fully-evidenced
S-class (Section 4). Combined with RR-3.7B's own 3 repaired S4s and the
one new repair here, the complete structured-router class (66 endpoints
across 26 files) now has **zero unresolved security-relevant
ambiguities** and **zero endpoints whose S-class rests on absent rather
than examined evidence**.

---

## 19. Global Ingress Snapshot

| Ingress | Status |
|---|---|
| `/command` | SAFE CANONICAL (unchanged) |
| `/ws/command` | SAFE CANONICAL (RR-3.6, unchanged) |
| A2A (`/invoke`, `/sessions/{id}/messages`) | SAFE CANONICAL (RR-3.7A, unchanged) |
| Structured HTTP router class (26 files, 66 endpoints) | SAFE CANONICAL for the 4 real repaired findings (RR-3.7B's 3 + this mission's 1); SAFE READ-ONLY/DOWNSTREAM-SAFE for all 62 others, each now individually evidenced (not merely asserted) |
| `voice_ws` | UNTRACED / RR-3.7C (out of scope, not audited this mission) |

---

## 20. Adversarial Falsification

1. Every RR-3.7B conservative/unconfirmed row individually traced — **PROVEN** (19/19, Section 4).
2. No endpoint called S3 solely because grep found no handler — **PROVEN** (every row's `run()` fallthrough was read, not merely grepped; the two parameter-mismatch findings, #7 and #18, are exactly the kind of "grep would have said dead, but a real branch exists" case this check exists to catch — and were caught).
3. HP fallback behavior was considered — **PROVEN** (every district's full agent roster traced, not just the "obvious" candidate — this is precisely what surfaced #8's MalwareHunter, #9's CredentialManager, #11's GEOOptimizerAgent, and #14/#15's SkillMapper findings).
4. Default `run()` behavior was considered — **PROVEN** (same evidence as #3).
5. No real side-effect endpoint remains ungated without explicit justification — **PROVEN** (the one real, credential-adjacent gap found is repaired; all others are explicitly justified as read-only or low-severity-local with cited evidence).
6. No security-relevant S5 remains — **PROVEN** (Section 6 — the fork's initial 5 "S5" labels were reviewed and resolved: 4 to S3-low with justification, 1 repaired).
7. All accepted RR-3.7B repairs remain intact — **PROVEN** (Section 16 regression + Section 17 live re-validation of `ingest_video`; dedicated unit tests re-confirm `log_exercise`→health routing, `create_project`→projects routing, both agents' declared capabilities, and `_PLAN_COMPOSABLE_ACTION_TYPES`'s membership).
8. `ingest_video` still fails closed — **PROVEN** (live re-check, Section 17).
9. `log_exercise` still reaches ExerciseLogger deterministically — **PROVEN** (unit test, Section 14).
10. `create_project` still reaches ProjectPlanner deterministically — **PROVEN** (unit test, Section 14).
11. Autopilot recursion independently reproduced or falsified — **PROVEN, reproduced** (not falsified — the defect was real; Sections 9-12).
12. Repaired depth state cannot be reset by caller input — **PROVEN** (Section 11 — real HTTP schema cannot smuggle `autopilot_depth`; `/city/dispatch` cannot smuggle the action_type + a crafted field either).
13. `MAX_CHAIN_DEPTH` genuinely terminates recursive chains — **PROVEN** (unit test + live production proof, Sections 10/12).
14. No alternate recursion path bypasses the guard — **PROVEN for the two paths that exist** (self-referential edge, now fixed; legitimate chain-to-next-district edge, always correctly bounded, re-confirmed unaffected by this fix via dedicated regression test).
15. Autopilot repair did not introduce double execution — **PROVEN** (`state["calls"]==5` exactly, never more, across every test scenario including malformed-input variants).
16. Authentication remains intact — **PROVEN** (unchanged bearer-token middleware; `/governance/autopilot/trigger`'s mounting+auth independently re-verified this mission, Section 9A).
17. `/command` unchanged — **PROVEN** (zero diff).
18. `/ws/command` unchanged — **PROVEN** (zero diff).
19. A2A unchanged — **PROVEN** (zero diff; RR-3.7A's 22 tests still pass).
20. No new authorization framework/ontology introduced — **PROVEN** (this mission's two repairs are: (a) an agent-local "unmatched type → honest error" branch, the SAME pattern ~15 other agents already use; (b) a depth-stamp on a task dict, using the pre-existing `MAX_CHAIN_DEPTH` invariant — zero new classes, zero new tiers, zero new gateways).

No security-critical FALSIFIED or NOT-PROVEN item.

---

## 21. Diff Audit

```
districts/governance/autopilot.py          | 38 +++++++++++++++++++++++++--
districts/governance/credential_manager.py | 41 +++++++++++++++++++++++++++++-
2 files changed, 76 insertions(+), 3 deletions(-)
```
Plus two new test files (untracked): `tests/test_rr3_7b1_autopilot_
recursion.py` (~330 lines, 26 tests), `tests/test_rr3_7b1_ambiguous_
endpoint_closure.py` (~175 lines, 10 tests). `git status --short` on the
full touched set confirms exactly these 4 files/additions — no other
production file was modified by this mission (the pre-existing,
unrelated `data/models/neural_policy.{pt,meta.json}` runtime artifacts
and the earlier-session report backlog remain present but untouched by
this mission's own edits).

Every hunk in both modified files is accounted for in Sections 8 and 11
above — no unexplained change, no unrelated cleanup or refactor.

---

## 22. Commit Ledger

To be populated at commit time (Hard Stop, below) — this mission's
changes are committed as a single logical commit covering both closures
together, since they were investigated and delivered as one mission with
a shared report.

---

## 23. Evidence Ladder

1. Source read (every claim in Sections 4, 7, 9 traced to exact file:line
   citations — the fork's initial trace was independently spot-verified
   at the highest-stakes point, `credential_manager.py`, by the primary
   session directly reading and running the real file before acting on
   the finding).
2. Unit-level pre-fix/post-fix exploit-proof tests for both repairs
   (Sections 10, 15) — including one that captured REAL, live API key
   prefix material in its pre-fix failure output, first-hand proof the
   vulnerability was genuine, not theoretical.
3. Full regression suite, cross-checked against pre-fix baseline for the
   one failure that appeared (Section 16).
4. Live production validation against a real, running VECTOR instance —
   the autopilot fix's live server-log evidence (Section 12) is the
   strongest evidence in this report: not a mock, not a unit test, the
   actual production code path, observed end-to-end.

---

## 24. Remaining Gaps for RR-3.7C

1. **`voice_ws`** — untraced, explicitly out of this mission's scope
   (unchanged from RR-3.7B).
2. **Wrong-district `DISTRICT_TASK_MAP` substring collisions** — this
   mission found THREE more instances of the pattern RR-3.7B already
   flagged once (`redact_data`→security instead of privacy):
   `scan_data_sharing`→security instead of privacy, `gdpr_check`→
   governance instead of privacy, `growth_analysis`→marketing instead of
   reflection. None of the real, intended handlers (`privacy_enforcer.py`,
   `growth_analyst.py`) are ever reachable via these specific literal
   action_types. Not fixed here (would require touching
   `DISTRICT_TASK_MAP`'s substring-matching architecture, explicitly out
   of this mission's narrow scope) — worth a dedicated, careful pass in a
   future mission, since the pattern is now confirmed recurring rather
   than a one-off.
3. **`vectorcode_llm.py`'s `_try_gemini()` full-URL error logging** —
   observed live during this mission's own production validation (Section
   17): a provider-call failure log line includes the complete request
   URL with the API key as a query parameter, not truncated/redacted.
   Pre-existing, unrelated to this mission's own changes, not reproduced
   or fixed here — a genuine, real logging-hygiene finding for a future
   mission (or immediate owner attention, given it involves live
   credential material in log output).
4. **The four S3-low real-but-low-severity findings** (Section 4, rows
   #8, #11, #14/#15) are deliberately left unrepaired per this mission's
   own evidence that they are non-dangerous — but they share the same
   "zero-type-check, HP-lottery-selectable" architectural shape as the
   defects RR-3.7B/this mission DID repair. If any of these agents'
   default-action semantics change in the future (e.g. MalwareHunter's
   scan gains a write/delete capability), they would need re-auditing.
5. **`accessibility_audit`'s silent misroute** (Section 4, row #10) is a
   real correctness bug (the named capability, `AccessibilityAuditor`,
   never actually runs for this endpoint) — safe today only because the
   agent it accidentally routes to instead (`APITester`) is independently
   harmless. Worth a genuine fix in a future mission (not security-
   relevant, so out of this mission's scope).

---

## 25. Verdict

**`RR-3.7B.1 PASS — STRUCTURED AMBIGUITY AND AUTOPILOT DEFECT CLOSED`**

Justification: every one of the 19 previously-conservative/unconfirmed
endpoints was individually traced to a fully-evidenced final class — zero
remain ambiguous for lack of evidence. The one real, credential-adjacent
authorization gap discovered during that trace was closed via the
smallest existing seam (agent-level honest-error default, matching this
codebase's own dominant convention), with pre-fix exploit proof
capturing real key material and post-fix proof confirming closure. The
autopilot recursion defect was independently reproduced (correcting
RR-3.7B's own probabilistic framing to the true deterministic mechanism),
repaired using the pre-existing `MAX_CHAIN_DEPTH` invariant rather than a
new control system, and verified live in production with exact,
predicted server-log evidence. No double execution, no privilege
widening, all of RR-3.7B's own three repairs remain intact and
re-verified, and the regression/production evidence directly supports
every claim in this report.

---

## Hard Stop

VECTOR is stopped. This mission does NOT proceed to RR-3.7C, RR-4,
RG-C2, RG-D2, R27, or any new cognition/Understanding-Engine/world-model/
new-feature work. Awaiting independent review.
