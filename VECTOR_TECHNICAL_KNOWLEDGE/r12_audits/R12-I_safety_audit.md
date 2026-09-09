# R12-I — Safety Audit

## Objective
Independently re-verify (not assume) that R11 (native goal strategy candidate generation,
commit `81b53b117`) introduced no safety regression in the goal → candidate → DecisionEngine
→ Governor → PermissionGateway → execution path.

## Method
Direct source read of `core/brain/goal_system.py`, `core/loop/autonomous_loop.py` (`_think_tick`,
`_act_on`), `core/config.py` (`PermissionConfig`), `core/loop/permission_gateway.py`
(`classify`/`_classify`/`execute`); `git diff ca682c79e 81b53b117 --stat` on the three files
that gate authority (`core/config.py`, `core/loop/permission_gateway.py`,
`core/city/governor.py`); targeted greps for code-execution primitives and
Governor/PermissionGateway references inside the R11-changed files.

## Findings

1. **`core/config.py`, `core/loop/permission_gateway.py`, `core/city/governor.py` are
   byte-identical across the R11 commit** — `git diff ca682c79e 81b53b117 --stat` on these
   three files returns empty. R11 did not touch classification, routing, or the gateway at all.

2. **`_TAG_TO_ACTION_TYPE` (`core/brain/goal_system.py:47-56`) — every one of its 21 mapping
   entries resolves to one of 11 distinct values**: `check_attendance, git_status, code_task,
   daily_digest, search_arxiv, monthly_report, check_fatigue, search_web, consolidate,
   daily_review, code_review_vc`. Cross-checked each against the live `PermissionConfig`
   (`core/config.py:87-269`):
   - GREEN: `check_attendance, git_status, daily_digest, search_arxiv, check_fatigue,
     search_web, consolidate, daily_review, code_review_vc` (9)
   - YELLOW: `monthly_report` (1)
   - RED: `code_task` (line 258, confirmed inside the `red` list block which closes at 269) (1)
   - FORBIDDEN (`permission_gateway.py:45`, `['format_drive', 'mass_delete',
     'share_private_data']`): **zero overlap**
   - UNKNOWN: **zero** — every value is classified.

3. **No code-execution primitive anywhere in the R11-changed logic.** Grep for
   `eval\(|exec\(|subprocess|os\.system|shell=True|Governor|PermissionGateway` inside
   `core/brain/goal_system.py` returns exactly one hit — a comment (line 43) referencing
   Governor, not a call. `_tag_derived_action_types()` and `generate_immediate_actions()`
   only ever perform dict `.get()` lookups against a fixed, hardcoded table; there is no path
   by which a tag's own string content can become the emitted `action_type` — only a
   pre-registered dict *value* can.

4. **`autonomous_loop.py::_think_tick()` (lines 816-991)** — confirmed the candidate-building
   loop (lines 913-926) is a direct 1:1 `a["action_type"] → Candidate` translation with zero
   subprocess/eval/Governor/gateway references. The dead `_TAG_TO_ACTION` remap this replaced
   is gone, replaced by an explanatory comment (898-912) — verified by reading the full
   function body, not just the diff.

5. **`_act_on()` (lines 1002+) — the RED/YELLOW gate before the VectorCode bridge is
   completely intact and unmodified by R11.** Lines 1050-1081: `_VC_ACTION_TYPES = {"code_task",
   "code_review_vc", "code_generate", "code_fix", "code_debug"}`; `gw.classify()` is called
   first; `FORBIDDEN` returns immediately; `RED`/`YELLOW` route through `gw.execute()` and check
   `.approved` before ever reaching `districts.coding.vectorcode_bridge.get_bridge()`
   (lines 1082+). This is the exact mechanism the R11 report claimed was untouched — now
   independently re-confirmed by direct read, not by trusting that report.

6. **No new cloud execution, financial action, or communications-send path** is reachable from
   anything R11 added — the 11 action_types R11's mapping can produce were all pre-existing,
   pre-classified, pre-routed action_types before R11 (R11 only changed *how many* of them one
   goal can propose as competing candidates, never *which* types exist or what tier they sit at).

## Explicit PASS/FAIL

| Safety property | Result |
|---|---|
| `PermissionConfig` green/yellow/red unchanged by R11 | PASS (0 diff) |
| `PermissionGateway.classify()`/`execute()` unchanged by R11 | PASS (0 diff) |
| `Governor` routing unchanged by R11 | PASS (0 diff) |
| No code-execution primitive in R11's new code | PASS (grep-verified) |
| No Governor/PermissionGateway reference in R11's new code | PASS (grep-verified; only a comment) |
| Malicious/crafted tag cannot produce an out-of-allowlist action_type | PASS (fixed dict-value output; verified all 11 possible outputs classified, 0 unclassified) |
| RED/YELLOW gate before VectorCode bridge intact | PASS (direct read of `_act_on()`) |
| No new FORBIDDEN-tier or UNKNOWN-tier action reachable | PASS (0 overlap with FORBIDDEN list) |
| No new cloud/financial/comms-send path reachable | PASS (all 11 action_types pre-existing) |

## Current capability level
Not applicable to this audit (safety-only; see R12-A for candidate-diversity capability
classification). This audit found the safety boundary at the same state it was in before R11:
byte-identical classification/routing/gateway code, R11 only changes how many pre-classified
options compete for one decision.

## What's broken vs working
Nothing broken. Everything examined is working as R11's own report claimed, and this audit
independently re-derived the same conclusion from source rather than trusting the prior report.

## Recommended next milestone
None from a safety perspective — this subsystem is stable. Future strategy-coverage expansion
(R13) must re-run this same classification cross-check for any NEW `_TAG_TO_ACTION_TYPE` entry
before it's added — the pattern here (verify against `PermissionConfig` before adding) is the
reusable safety gate for that work.

## Open questions
None outstanding for R11's own changes. One general observation for R13 scope (not a defect):
if a future tag mapping proposes an action_type genuinely not yet in `PermissionConfig`, per
the master mission's own Section 2/7 rules this must STOP and escalate for separate
architectural review, not be silently added.
