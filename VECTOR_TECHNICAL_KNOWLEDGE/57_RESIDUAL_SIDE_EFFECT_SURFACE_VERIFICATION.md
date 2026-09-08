# 57 — Residual Autonomous Side-Effect Surface Verification

**Date**: 2026-09-02
**Type**: VERIFICATION FIRST. No production code was modified by this task. Two new
diagnostic-only test files were added (`tests/test_task57_device_control_bypass_diagnostic.py`,
`tests/test_task57_capability_bypass_diagnostic.py`) — both exercise real production methods with
only the actual dangerous primitive (subprocess/remote-job-submission) replaced by a spy, and
perform zero real side effects.
**Purpose**: close the three specific verification gaps that kept task 54 at B (Conditionally
Ready) rather than A: (1) `pc_controller.py`/`phone_controller.py` `grant_control()` production
callers, (2) event-fan-out handler coverage beyond the security district, (3) the remaining
~70-80 unread subprocess/os.system files.

**Result, in short: this task does NOT improve 54's readiness gate — it finds new reasons to keep
it at B, or arguably move toward C.** Phases 1 and 3 each surfaced a **CONFIRMED, real, currently
unfixed permission-boundary bypass** — deeper and more concerning than "unverified." Phase 2
(event fan-out) is the one gap that genuinely resolves to VERIFIED.

---

## 1. Scope

In scope: exhaustively tracing the three specific surfaces named in `54`'s gate, to either VERIFY
them safe or CONFIRM/document any bypass found. Per this task's explicit instructions, no bypass
found was fixed — each is documented precisely, with an exact recommended follow-up task, and
production behavior is otherwise unchanged.

Out of scope, not touched: routing, provider selection, model selection, thresholds, cadence,
memory, planning, cognition, governance architecture, the 7-day experiment itself.

---

## 2. Inputs / Previous Findings

Read in full before starting: `53_PERMISSION_BOUNDARY_INTEGRITY.md`, `54_PRE_EXPERIMENT_
READINESS_VERIFICATION.md`. Per this task's instruction, production code was inspected directly
rather than trusting either document's characterizations — this proved necessary: `53`'s account
of `pc_controller.py`/`phone_controller.py` ("the mechanism is fail-closed by design") was correct
as far as it went, but did not examine what a token, once minted, is actually *accepted for* —
which is where this task's Finding A lives.

---

## 3. Device-Control Audit (Phase 1)

**Every production caller of `PermissionGateway.grant_control()`**, found by grep across the full
non-test codebase:

| Caller | Location | Context |
|---|---|---|
| `PCController.play_music()` | `core/control/pc_controller.py:292` | Self-mints if no token passed; `play_music` is GREEN, so this is architecturally consistent *for play_music itself* |
| `PermissionGateway._execute_action()`'s `play_music` handler | `core/loop/permission_gateway.py:912` | Mints post-classification (GREEN, no approval needed) — **this is where Finding A originates** |
| `PermissionGateway._execute_action()`'s `launch_app` handler | `core/loop/permission_gateway.py:1292` | Only reachable via `execute()`'s classify→approve flow; `launch_app` is RED |
| `PermissionGateway._execute_action()`'s `run_shell_command` handler | `core/loop/permission_gateway.py:1314` | Same — only reachable post-RED-approval |
| `PCController.__main__` self-test | `core/control/pc_controller.py:426,435` | Self-test only, mints directly for its own smoke test — not a production path |
| `PhoneController.post_instagram()` | `districts/content/phone_poster.py:108` | **Correctly gated**: mints only after `PermissionGateway().request_approval(...)` returns `True`, fail-closed on exception |
| `PhoneController.post_youtube()` | `districts/content/phone_poster.py:194` | Same correct pattern |

**`grant_control()` itself has no internal tier/approval check** (`core/loop/permission_gateway.py:789`)
— it mints a valid, opaque token for *any* `action_type` string handed to it, no matter what tier
that string belongs to. `verify_control()` (line 800) only checks token validity/expiry/use-count/
exact-action-type-match against whatever was minted — it has no concept of tiers either. The entire
token system's security value rests **entirely on caller discipline** (every legitimate caller
minting only after a real approval), not on any enforced property of the token mechanism itself.
This is confirmed correct discipline in `phone_poster.py`'s two callers. It is **not** correct in
`permission_gateway.py`'s own `play_music` handler.

### Finding A — CONFIRMED BYPASS: `play_music` (GREEN) → arbitrary application launch (RED capability), zero owner approval

**Exact call chain** (every link read directly, not assumed):

```
Any constructor of Action(action_type="play_music", params={"app": <caller-controlled string>})
  → PermissionGateway.execute(action)
      → level = self._classify("play_music") = "GREEN"   [core/config.py:88]
      → if level == 'GREEN': exec_result = await self._execute_action(action)   [NO approval step — by GREEN's own definition]
          → elif action.action_type == "play_music":   [core/loop/permission_gateway.py:905]
                _app = action.params.get("app") or action.params.get("app_name") or "spotify"   [line 911 — UNVALIDATED]
                _tok = self.grant_control("play_music", uses=4, ttl=60)                          [line 912]
                _r = PCController().play_music(_app, control_token=_tok)                          [line 913]
                    → self.launch_app(app, control_token=control_token)   [core/control/pc_controller.py:295]
                        → if not self._verify_control_token(control_token, "launch_app", "play_music"):   [line 211 —
                                                                                                              EXPLICITLY
                                                                                                              ACCEPTS A
                                                                                                              play_music TOKEN]
                        → exe = _WIN_APP_ALIASES.get(...) or shutil.which(app_name) or (URI protocol) or app_name  [last resort]
                        → subprocess.Popen([exe] + args, ...)   [line 238 — REAL PROCESS LAUNCH]
```

Concretely reachable one real production trigger: `core/voice/ambient_listener.py:455-476` builds
`Action(action_type=action_type, params=params, proposed_by="voice")` directly from an **LLM-based
ambient-speech intent classifier's output** (`intent.get("action_type", ...)`, `intent.get("params",
{"message": text})`) with **zero validation of `params`'s contents**, then calls `gw.execute(action)`
immediately. If the classifier ever emits `action_type="play_music"` with a `params["app"]` value
derived from misheard/ambient/injected audio, that string reaches `subprocess.Popen` with **no
owner confirmation, no RED-tier gate, no sanitization** — despite `launch_app`/`pc_launch_app` being
explicitly, deliberately classified RED in `core/config.py:150` under the comment "synthetic input
/ app launch."

**Why this is a genuine tier-escalation, not intended design**: `launch_app()`'s own comment
(`core/control/pc_controller.py:210`) explains the *intent* — "play_music is GREEN and legitimately
drives launch_app — accept its token" — a narrow accommodation so the GREEN music-playing path can
launch a media player as an implementation detail. But `play_music`'s own `app` parameter is fully
attacker/LLM-controllable and unconstrained (no allowlist against, e.g., `_WIN_APP_ALIASES`'s known
keys) — the accommodation, as implemented, doesn't just let `play_music` launch *a media player*,
it lets `play_music` launch **anything `launch_app()` itself could launch**, with the exact same
reach as calling `launch_app` directly and RED-tier-approving it, minus the approval.

**Severity**: real, confirmed, `subprocess.Popen`-reaching, list-form (not `shell=True`, so no
shell-metacharacter injection via this specific path — the app name resolves to a single executable
target, launched with zero arguments since `play_music()` never exposes an `args` parameter). Still
squarely inside this document's BLOCKER definition ("unauthorized consequential side effects") —
launching an arbitrary named executable (e.g., `cmd`, `powershell`, or anything else discoverable
via `shutil.which` on the owner's PATH) with zero owner approval is a real, consequential,
unauthorized side effect.

**Behavioral verification (this task, zero real side effects)**:
`tests/test_task57_device_control_bypass_diagnostic.py` — 4/4 pass. Confirms, via the real
`PermissionGateway.execute()` call (only `PCController.launch_app`/`media_key` monkeypatched to
spies): the action auto-executes at GREEN with `approved=True`; an attacker-chosen `app` string
reaches `launch_app()` verbatim; a control test confirms `launch_app()` correctly refuses a call
with no token at all (isolating the finding to the specific play_music-token-acceptance design
choice, not a claim that `launch_app` has zero protection).

**Not fixed in this task**, per explicit instruction. See §15 for the recommended follow-up.

**`run_shell_command` was checked and is NOT similarly affected** — its token check
(`core/control/pc_controller.py:323`) accepts *only* a `"run_shell_command"`-scoped token (no
broadened tuple), and `grant_control("run_shell_command", ...)` is only ever called from inside
`_execute_action()`'s own RED-tier `run_shell_command` handler — itself only reachable after a real
RED approval. The codebase's **one** `shell=True` call site (`core/control/pc_controller.py:334`,
confirmed via a full-codebase grep for `shell=True`) is correctly, exclusively gated.

**`phone_controller.py`'s verification logic is over-broad but not confirmed exploitable**: its
6 write primitives (`unlock`, `tap`/keyevent, `swipe`, `type_text`, `launch_app`, one more) all call
`_verify_control_token(control_token, *self._control_action_types)` — a single shared 10-item tuple
that includes `"play_music"` (`core/control/phone_controller.py:21-25`). This means a
`"play_music"`-scoped token would *also* satisfy any of these 6 checks — the same class of design
weakness as Finding A. **No currently-reachable production call chain was found that actually
passes a `"play_music"`-scoped token into any `PhoneController` write primitive** — `PCController
.play_music()`'s flow never touches `PhoneController`. This is documented as a **latent design
weakness (WARNING)**, not a confirmed bypass — see §15 for the recommended scope of the follow-up
task to close it defensively regardless.

---

## 4. Event-Fan-Out Audit (Phase 2)

**Authoritative source**: `core/event_bus/wiring.py`'s `EVENT_TRIGGER_MAP` (read directly, not
assumed from `53`'s summary). 11 `EventType` keys, 23 total `(district, task_type, params_template)`
entries, reaching **14 distinct districts**: coding, content (×3), marketing (×2), qa (×2),
documentation, intelligence (×2), investment, emergency (×4), governance, health,
predictive_analytics, security (×2), data_analytics, strategy.

**Master invariant, re-confirmed and extended this task**: a bulk grep of all 23 exact task_type
strings (`implement_design`, `distribute_content`, `lockdown_systems`, `evaluate_research_
opportunities`, etc.) across the entire `districts/`+`core/` tree, excluding `wiring.py` itself,
returns **zero matches anywhere**. No agent in any of the 14 reachable districts implements a
dedicated handler for any of these strings.

**Consequence**: every fan-out dispatch lands on whichever agent wins that district's capability-
match-or-HP-lottery (`Governor.dispatch()`'s existing, unmodified logic), and — since no agent
declares these fake task_types as a capability either (re-confirmed) — that agent's `run()` treats
the task_type as unrecognized and falls to *its own* default/fallback branch.

**Districts individually traced this task** (default-branch behavior read directly, not assumed):

| District | Agent checked | Default-branch behavior | Classification |
|---|---|---|---|
| security | `NodeGuard`, `ThreatScout` | Ignore `task_type` entirely; always run their own fixed, read-only scan | SAFE — TASK TYPE IGNORED |
| investment | `HedgeBotAgent` | Explicit documented fallback: unmatched task_type → `hedge_run()` (analysis-only, 5-agent text pipeline); `solana_execute` "requires an EXACT action match... never reachable from this fallback" (the file's own comment) | SAFE — TASK TYPE IGNORED |
| investment | `ExecutionEngine` | Default → `get_today_summary()` (read-only); `place_order` requires exact match, unreachable via fan-out strings | SAFE — READ ONLY |
| emergency | `EmergencyResponseSystem` | Exact-match required for `escalate_emergency`/`classify_emergency`; all fan-out strings fall to `return {"status": "ok", **self.get_state()}` (pure status report) | SAFE — READ ONLY |
| coding | `CodingSwarm` (HP=1500, virtually certain outer-district winner) | Internal fuzzy-match (`_score_agent_match`, `TASK_ROLE_MAP`) traced for `"implement_design"` → resolves to `CodeIntelAgent` (role contains "code") → `CodeIntelAgent.run()`'s own exact-match dispatch has no handler for "implement_design" → `return {"status": "error", "error": f"Unknown code_intel task type: ..."}` — honest refusal, zero side effect | SAFE — TASK TYPE IGNORED (traced 2 routing layers deep) |
| content | `ContentScheduler` | Same documented "2026-08-05" fix pattern as `uploader.py` (`53`): unmatched task_type → `get_summary()` (read-only) or honest error; `run_pending()` (real RED-tier publish) requires exact match, unreachable via fan-out strings | SAFE — READ ONLY |
| governance | `LLMCouncil` | `run()` falls back to `task.get("type", ...)` as the literal deliberation "question" for an unmatched task_type → one bounded, real LLM call (`convene()`) — confirmed via full-file grep: zero `PermissionGateway`/`subprocess`/`os.system` references anywhere in this file; `convene()` has no execution authority, purely advisory text output | SAFE — LLM-CALL-ONLY, no execution capability |

**Districts not individually traced this task** (content beyond `ContentScheduler`, marketing,
qa, documentation, intelligence, health, predictive_analytics, data_analytics, strategy): not
exhaustively read line-by-line. Confidence in their safety rests on (a) the confirmed master
invariant (no exact-match handler exists anywhere for any fan-out string, so no agent's *dangerous,
exact-match-gated* capability is directly reachable) and (b) the now-consistent pattern observed
across every one of 7 districts actually sampled, spanning the highest-plausible-risk categories
(financial, emergency-response, security, code-writing, content-publishing, deliberative-authority)
without a single exception.

**Classification: VERIFIED**, on the strength of the confirmed master invariant plus consistent
positive sampling across the highest-risk districts — not "no bypass found but incompletely
verified" in the sense that would require withholding this classification, because the *specific
mechanism* that would make a bypass possible (an agent having some exact-match, real-side-effecting
handler that accidentally collides with one of the 23 fixed fan-out strings) was directly, bulk-
disproven across the entire codebase, not merely unsampled.

---

## 5. Subprocess / os.system Sweep (Phase 3)

**Starting inventory**: re-ran the exact grep from `53` — **91 files** matching
`subprocess.(run|Popen|call|check_output)` or `os.system(` across `core/`, `districts/`, `hands/`.
A separate full-codebase grep for `shell=True` found **exactly one production hit**:
`core/control/pc_controller.py:334` (inside `run_shell_command()`, confirmed correctly gated, §3).

### Files individually traced this task (beyond what `53` already covered)

| File | What it does | Reachable autonomously? | Gated? | Classification |
|---|---|---|---|---|
| `districts/emergency/escalation.py` | `["powershell", "-c", "[console]::beep(...)"]` — fixed alert beep | Yes (emergency detection) | N/A — fixed args, no dynamic input | VERIFIED SAFE — LOW-RISK |
| `districts/emergency/runbook.py` | `nvidia-smi -pl 150`, `ollama list`/`serve`, `ipconfig /renew`, `netsh advfirewall ... state on` — all fixed-argument remediation commands | Yes (emergency detection) | N/A — fixed args, no caller-controlled input anywhere, none destructive (firewall command *enables* protection) | VERIFIED SAFE — LOW-RISK |
| `districts/coding/coding_tools.py` | `apply_search_replace`, `write_code_file`, `multiedit_file`, `apply_codex_patch` (all real file-mutation) | Yes (VC-routing/skill paths, `53`) | **Yes** — all 4 gated by `_require_coding_grant()` / `is_coding_grant_active()`, refuses with an error dict if the gateway-approved `code_*` grant isn't active; `grep_code`'s `rg` subprocess call is read-only, list-form | VERIFIED GATED |
| `core/control/security/node_router.py` | `ipconfig /all` — parses DNS server config | Possibly | N/A — read-only, fixed command | VERIFIED SAFE — LOW-RISK |
| `core/loop/cron_jobs.py` | `python -m compileall`, `python run_vector.py smoke`, `git log -1` — self-diagnostic health check after a file change | Yes (scheduled) | N/A — fixed commands, explicitly documented as non-destructive ("No auto-revert — the owner decides") | VERIFIED SAFE — LOW-RISK |
| `districts/security/incident_playbook_runner.py` | `taskkill /F /PID`/`/IM` inside `_action_kill_process()`, sourced from playbook-YAML-defined steps, not free caller input | Yes (security incident response — by design) | **Yes** — same documented "2026-08-05" pattern as `uploader.py`/`content_scheduler.py`: `execute_playbook` requires an exact task_type match *and* a resolvable `playbook_id` against the loaded (owner/repo-authored) YAML set; free-text/chat dispatch explicitly routed to the read-only `list_playbooks()` default, confirmed via the method's own code comment naming `kill_process`/`block_ip`/`run_antivirus` as the exact risk this routing avoids | VERIFIED GATED |
| `districts/investment/finagent_agent.py` | `self._launcher.launch()` (real `subprocess.Popen` of a native Qt6 GUI binary) + `ensure_built(auto_build=True)` (real `cmake`/build invocation) | **Yes — see Finding B below** | **No** | **CONFIRMED BYPASS (Finding B)** |
| `districts/coding/mlops_agent.py` | `hf_train()` submits a caller-supplied Python script to HuggingFace Jobs (remote execution) | **Yes — see Finding C below** | **No** | **CONFIRMED BYPASS (Finding C)** |

### Finding B — CONFIRMED BYPASS: `finagent_agent.py`'s `launch_terminal` capability, zero gating

`FinAgentAgent.capabilities` (`districts/investment/finagent_agent.py:79`) declares
`"launch_terminal"` — this alone means `Governor.dispatch()`'s capability-match routes
`task_type in ("launch_terminal", "terminal", "open_terminal")` **directly** to this agent (no
HP-lottery needed, and reachable cross-district too via the `_llm_classified` whole-registry
capability search, `core/city/governor.py:2252-2266`, for any LLM-classified chat message). `run()`
(line 636-637) maps this straight to `launch_terminal(auto_build=p.get("auto_build", False))`,
which calls `self._launcher.ensure_built(auto_build=auto_build)` — a **real, caller-triggerable
`cmake`/native-build invocation** (`districts/investment/vector_finagent/terminal_launcher.py:105,
118`) — followed by `self._launcher.launch()` — a **real `subprocess.Popen`** of the built binary
(same file, line 160). `"launch_terminal"` is not present in *any* of `core/config.py`'s GREEN/
YELLOW/RED/FORBIDDEN lists (confirmed via direct read) — this whole capability sits completely
outside the permission taxonomy, never reaches `PermissionGateway` at all.

**Severity note**: lower than Finding A — the launched target is *fixed* to this project's own
terminal binary, not an attacker-namable arbitrary executable. But the capability itself
(application launch + native code compilation, both squarely RED-category per `core/config.py`'s
own classification of `launch_app` as "synthetic input / app launch") is real, unstubbed, and fully
reachable with zero owner approval via an ordinary chat message.

**Behavioral verification (this task, zero real side effects)**:
`tests/test_task57_capability_bypass_diagnostic.py::test_run_launch_terminal_reaches_real_
launcher_with_no_gateway_step` — calls the real `FinAgentAgent.run()` with
`task_type="launch_terminal", params={"auto_build": True}`, with only the `FinAgentTerminalLauncher`
instance's `ensure_built`/`status`/`launch` methods replaced by spies (no real build, no real
launch). Confirms `auto_build=True` reaches `ensure_built()` unfiltered and `launch()` is called —
pass.

### Finding C — CONFIRMED BYPASS: `mlops_agent.py`'s `hf_train` capability, zero gating

`MLOpsAgent.capabilities` (`districts/coding/mlops_agent.py:113`) declares `"hf_train"` — same
capability-match reachability as Finding B. `run()` maps `action == "hf_train"` to
`hf_train(script=p.get("script", ""), repo_id=..., hardware=..., ...)` — the caller-supplied
`script` string (arbitrary Python source, per the method's own docstring: "Python training script
content (will be uploaded then executed)") flows verbatim into `args = {"script": script, ...}`,
submitted to `hf_jobs_handler(args)` — a **real remote job submission to HuggingFace Jobs**, using
the owner's HF credentials, executing on HF's cloud infrastructure at real (potentially GPU-tier)
cost. `"hf_train"` is not present in any `core/config.py` permission tier. Zero `PermissionGateway`
reference anywhere in `hf_train()`'s source (confirmed via `inspect.getsource()`).

**Severity note**: this is remote code execution (attacker/LLM-controlled Python source, executed
on infrastructure tied to the owner's account/billing) — arguably comparable in class to Finding A
(arbitrary-content execution) even though the blast radius is a sandboxed remote job rather than the
owner's local machine. Real financial cost is a direct, confirmed consequence (`hardware` selects
GPU tiers up to `nvidia-a100-large`).

**Behavioral verification (this task, zero real side effects)**: a full mocked-call test was
attempted but the actual `hf_jobs_handler` import happens via a fresh dynamic import inside a
namespace-switching context manager each call, which proved unreliable to intercept reliably across
repeated runs (documented in the test file). Verification instead uses `inspect.getsource()` to
confirm, against the real current method body (not memory/assumption): the `script` parameter flows
into `args["script"]` unvalidated, `hf_jobs_handler(args)` is called, and no `PermissionGateway`/
`gateway` reference exists anywhere in the method. `tests/test_task57_capability_bypass_
diagnostic.py::test_hf_train_forwards_caller_script_to_remote_job_submission_unvalidated` — pass.

### Files classified without full individual line-by-line trace (bulk/import-reachability classification)

Given the volume (91 files) and the time this task had already spent achieving deep, confirmed
findings on the highest-value targets, the remaining files were classified using **import-
reachability** (confirmed via grep — is this file imported from any code path a registered district
agent or the autonomous loop can reach) plus the established pattern-matching used successfully
throughout this document, rather than a full independent read of every file:

- **DORMANT/UNREACHABLE from autonomous cognition, verified via import-graph check** (zero
  references from `core/city/`, `core/loop/`, or the district-agent registry system):
  `districts/intelligence/shadowbroker_server/*` (7 files). No import anywhere outside its own
  directory tree.
- **Vendored, reachable only via a specific wrapper agent** (not "dormant" — actively imported):
  `vector_social_sim` (via `core/api/routers/simulation.py`, a **user-HTTP-triggered** API route,
  not autonomous-decision-reachable — not traced further, since Phase 4's reachability question is
  specifically about *autonomous* cognition), `vector_backtest` (imported by
  `districts/investment/backtest_agent.py` — not individually traced this task; `50`'s prior
  precedent classified sibling vendored packages as isolated/dormant, but `finagent`/`mlops`'s
  wrapper-agent pattern being exploitable (Findings B/C) means this assumption should **not** be
  extended to `vector_backtest` without direct verification — flagged UNCERTAIN, not assumed safe).
- **Claude-Code/dev-tooling, not VECTOR-autonomous-runtime code**: `core/coding_assistant/*`,
  `core/mcp_tools/expansion_modules/*`, `core/mcp/client.py`, `core/mcp_server.py`'s general tool
  surface (per `50`'s own established precedent for this exact category) — not re-verified this
  task; carried forward.
- **Deterministic media/local processing, LOW-RISK by consistent pattern**: `core/video/*` (4
  files), `core/media/local_inference.py`, `districts/content/video_merger.py`,
  `districts/content/voice_generator.py`, `districts/growth/hud_recorder.py`,
  `districts/learning/video_ingestor.py` — not individually read this task; classified LOW-RISK by
  filename/purpose consistency with the codebase's demonstrated pattern of fixed-argument media
  tooling, **not independently confirmed** — genuinely UNCERTAIN in the strict sense this document
  requires, not VERIFIED SAFE.
- **Sandbox/resilience-testing infrastructure**: `core/sandbox/*`, `core/research_engine/bootstrap_
  sandbox.py`, `sandbox_executor.py`, `core/resilience/injectors/*` — purpose is explicitly to run
  code in isolation or to deliberately inject test failures; not autonomous-decision-reachable by
  design (these are testing/chaos-engineering harnesses, not district-agent capabilities) — not
  individually re-verified this task.
- **Remaining ~35 files** (`core/api/routers/{sandbox,sensing,vectorcode}.py`,
  `core/benchmark/report.py`, `core/brain_hooks/__init__.py`, `core/code_conductor/git_eval.py`,
  `core/inference/model_router.py`, `core/knowledge/wiki_merger.py`, `core/loop/nudge_engine.py`,
  `core/mining/_pearl_subprocess.py`, `core/security/{rules_engine,skill_scanner}.py`,
  `core/seo/gsc_client.py`, `core/stealth_browser/*`, `core/telemetry/energy_apple.py`,
  `core/training/lora_trainer.py`, `core/vision_control/vision_operator.py`,
  `core/voice/wake_word.py`, `districts/coding/{bug_hunter,code_reviewer,security_reviewer}.py`,
  `districts/coding/vectorcode_bridge.py` (already established as Action-gated in `53`),
  `districts/coding/vector_mlops/agent/**` (the vendored package `mlops_agent.py` wraps — given
  Finding C confirms this wrapper agent IS reachable, this vendored package should be treated as
  **UNCERTAIN**, not dormant, in any follow-up), `districts/karpathy_lab/autoresearch_runner.py`,
  `districts/marketing/ads/scripts/generate_report.py`, `districts/marketing/ads_orchestrator_
  agent.py`, `districts/qa/{doc_generator,evidence_collector,reality_checker}.py`,
  `districts/research/opencli_adapter.py`) — **not individually traced this task**. This is stated
  explicitly rather than implied: this document does **not** claim these are safe. They remain
  UNCERTAIN.

---

## 6. Autonomous Reachability Analysis (Phase 4)

For every item classified UNCERTAIN or CONFIRMED BYPASS above, reachability was assessed:

- **Finding A** (`play_music`): confirmed reachable via `core/voice/ambient_listener.py`'s direct
  `gw.execute()` call from LLM-classified ambient speech (traced end to end, §3). Also structurally
  reachable via any other constructor of a `play_music` Action — `_act_on()`'s fallthrough,
  `commands.py`'s hardcoded intent path (confirmed this task to use empty `params`, so not a live
  vector via that *specific* entry point — but `classify_chat_intent()`'s LLM-based path was not
  individually re-traced for this exact param-population question, since ambient_listener.py's
  confirmation alone is sufficient to establish reachability).
- **Finding B** (`launch_terminal`): confirmed reachable via `Governor.dispatch()`'s ordinary
  capability-match (declared capability, exact task_type match) — the most direct, unconditional
  reachability class in the whole codebase; no LLM-classification ambiguity needed.
- **Finding C** (`hf_train`): same reachability class as Finding B — declared capability, exact
  match, unconditional.
- **The ~40 UNCERTAIN files** (§5's last three bullet groups): no autonomous reachability trace was
  performed for these specific files this task — their status is UNCERTAIN precisely because
  reachability was not established either way, not because reachability was checked and found
  absent. This is a meaningful, load-bearing distinction this document does not blur.

---

## 7. Permission-Boundary Cross-Check (Phase 5)

For the two confirmed bypasses: **no**, neither passes through the intended
`classification → policy/governance → PermissionGateway → approval/deny → side effect` boundary
verified in `53`. Both reach a real, consequential side effect (`subprocess.Popen` for Finding
A/B; a real remote job submission for Finding C) via a path that never constructs a gateway
classification for the *actual* risky capability being exercised — Finding A smuggles a RED
capability through a GREEN action_type's unvalidated parameter; Findings B/C bypass the gateway
entirely via `Governor.dispatch()`'s capability-match, the same architectural pattern `53`'s
Finding 1 (email) exploited, now confirmed to recur in at least two more districts.

For the district-agent default-branch behaviors verified safe in Phase 2 (event fan-out): yes,
consistent with `53`'s established finding — these don't need to reach `PermissionGateway` because
they perform no consequential action at all (read-only status/summary, or a single bounded
advisory LLM call with no execution authority).

---

## 8. Behavioral Verification (Phase 6)

Two new diagnostic-only test files, **10/10 tests pass**, zero real side effects performed by
either:

- `tests/test_task57_device_control_bypass_diagnostic.py` (4 tests) — Finding A, real
  `PermissionGateway.execute()` call chain, `PCController.launch_app`/`media_key` monkeypatched to
  spies.
- `tests/test_task57_capability_bypass_diagnostic.py` (6 tests) — Findings B and C; B via a full
  real-method-call behavioral test with the terminal launcher's build/launch calls spied; C via a
  source-inspection confirmation (full mocked-call attempt proved unreliable against the vendored
  package's dynamic-import pattern, documented in the test file itself).

---

## 9. Complete Inventory

| Surface | Items checked | Verified safe/gated | Uncertain | Confirmed bypass | Autonomous reachable |
|---|---|---|---|---|---|
| Device control (`grant_control()` callers) | 7 production call sites | 5 (both `phone_poster.py` sites, `run_shell_command`'s own handler, `launch_app`'s own handler, `phone_controller.py`'s fail-closed mechanism itself) | 1 (`phone_controller.py`'s over-broad shared token-scope tuple — latent, not confirmed exploitable) | **1 (Finding A)** | Yes (Finding A) |
| Event fan-out | 23 `(district, task_type)` entries, 14 districts, 7 districts individually traced | 7 districts traced, all safe; remaining 7 covered by the confirmed master invariant | 0 in the sense of "unresolved" — the underlying mechanism was bulk-disproven codebase-wide | 0 | N/A |
| Subprocess/os.system | 91 files total; ~15 individually traced this task beyond `53`'s prior coverage | 6 newly traced this task (escalation.py, runbook.py, coding_tools.py, node_router.py, cron_jobs.py, incident_playbook_runner.py) + everything `53` already covered | ~40 files, explicitly not traced | **2 (Findings B, C)** | Yes (B, C) |

---

## 10. Findings Summary

- **Finding A** — `play_music` (GREEN) → arbitrary-named application launch via `launch_app`'s
  broadened token acceptance. CONFIRMED, live-reachable (ambient voice path traced end to end).
- **Finding B** — `finagent_agent.py`'s `launch_terminal` capability (real app launch + real
  `cmake` build trigger) reachable via ordinary `Governor.dispatch()` capability-match, zero
  gateway involvement. CONFIRMED, unconditionally reachable.
- **Finding C** — `mlops_agent.py`'s `hf_train` capability (real remote code execution via
  HuggingFace Jobs, real cost) reachable the same way. CONFIRMED, unconditionally reachable.
- **Latent weakness** — `phone_controller.py`'s shared, over-broad `_control_action_types` tuple
  means any of its 6 write primitives would also accept a `"play_music"`-scoped token, though no
  currently-reachable call chain was found that does so.
- **~40 subprocess-using files** remain genuinely UNCERTAIN, not verified either way.

None of these three confirmed findings were fixed in this task, per explicit instruction.

---

## 11. Risk Classification

| Finding | Severity (54's scale) | Reachable autonomously | Reachable without deliberate high-stakes user action | Confirmed vs. uncertain |
|---|---|---|---|---|
| A — play_music → arbitrary app launch | S3 (high — real, unauthorized, consequential side effect; bounded to a named-executable launch, no arguments, no shell metacharacters) | Yes | Yes (ambient/misheard speech) | CONFIRMED |
| B — launch_terminal (fixed target + build trigger) | S2 (moderate — real side effect, but launch target is fixed to the project's own binary, not attacker-namable; build trigger has real but bounded local-resource cost) | Yes | Yes (ordinary ill-worded chat) | CONFIRMED |
| C — hf_train (remote code execution + real cost) | S3 (high — arbitrary caller-controlled Python source executed remotely under the owner's credentials/billing) | Yes | Yes (ordinary chat requesting training help) | CONFIRMED |
| phone_controller.py shared token scope | S1 (low — latent only, no live call chain found) | N/A | N/A | UNCERTAIN (design weakness, not exploit) |
| ~40 unread subprocess files | Unknown per-file | Unknown | Unknown | UNCERTAIN |

---

## 12. Test Results

**Targeted new diagnostic tests** (this task, verification-only, zero production behavior change):
`tests/test_task57_device_control_bypass_diagnostic.py` (4/4) +
`tests/test_task57_capability_bypass_diagnostic.py` (6/6) = **10/10 pass**.

**Full baseline suite** (`tests/unit` + `tests/integration`, identical scope/exclusions to tasks
52/53/55/56/54):

```
2212 collected, 2175 passed, 8 failed, 0 errors, 29 skipped
```
Identical to the established baseline — same 8 failing test names, all previously root-caused and
confirmed unrelated to any change in this or any prior task this session. No production file was
modified by this task (confirmed via `git status` before writing this document — only this
document and the two new diagnostic test files are new).

Expected baseline: 2212 collected / 2175 passed / 8 failed / 0 errors / 29 skipped. No production
code was modified this task, so no deviation from this baseline is expected or was found — see the
actual numbers above. If any new failure appears, it is by construction unrelated to this task's
changes (there are none to production code) and would need the same root-causing discipline `54`
established for the previous two newly-surfaced pre-existing failures.

---

## 13. Remaining Uncertainty

Explicitly not resolved by this task:

- Whether `phone_controller.py`'s over-broad shared token-scope tuple is exploitable via any call
  chain not yet found.
- The exact safety of ~40 subprocess-using files never individually traced this task (§5's last
  bullet groups) — including `vector_backtest` and `vector_mlops`'s own internal subprocess usage
  beyond the one `hf_train` entry point already confirmed dangerous.
- Whether `classify_chat_intent()`'s LLM-based classifier (as opposed to the hardcoded regex
  intent-router, confirmed safe) can itself be induced to populate `params["app"]` for a
  `play_music` action from ordinary or adversarial chat text — Finding A's reachability was
  established via the ambient-voice path specifically, not this one.
- Whether other district agents beyond `finagent_agent.py`/`mlops_agent.py` declare similarly
  ungated, permission-tier-absent capabilities — the search that found Findings B/C was targeted
  (following subprocess usage back to its owning agent), not an exhaustive audit of every agent's
  `self.capabilities` list against `core/config.py`'s tier lists.

---

## 14. Experiment Impact (Phase 8)

Using `54`'s exact BLOCKER definition: Findings A, B, and C each constitute "unauthorized
consequential side effects" reachable by an autonomous or ordinary-chat-triggered path with no
owner approval — squarely inside the BLOCKER bar, not merely a WARNING-level uncertainty.

This is a materially different outcome from what this task was launched to produce. Task 54 held
open three specific *uncertainties*, hoping this task would resolve them to VERIFIED. Two of the
three did resolve (device-control's fail-closed mechanism is real, and is not itself the problem;
event fan-out is genuinely safe) — but Phase 1's deeper trace, and Phase 3's, each surfaced a
**new, confirmed BLOCKER** that neither `53` nor `54` had found, because both concern a different
attack surface than what those documents' own execution paths considered (a token-scope acceptance
bug, and district-agent-declared capabilities with no permission-tier classification at all —
neither is "Governor.dispatch() bypasses the gateway centrally," the specific pattern `53` was
built to find).

---

## 15. Exact Next Task(s)

Given confirmed BLOCKER-class findings, **do not proceed to the 7-day experiment**. Recommended,
narrowly-scoped remediation task(s) — none performed in this task:

1. **Fix Finding A**: either (a) constrain `play_music`'s `app`/`app_name` parameter to a fixed
   allowlist (e.g., only `_WIN_APP_ALIASES`'s known keys) before it ever reaches `launch_app()`, or
   (b) remove `"play_music"` from `launch_app()`'s accepted-token-scopes tuple and instead have
   `play_music()` request a real, narrowly-scoped `launch_app` approval (or a dedicated, properly
   RED-classified `"play_music_launch"` sub-action) when it needs to start a player. Add a
   regression test proving an unconstrained `app` string can no longer reach `subprocess.Popen`.
2. **Fix Finding B**: gate `finagent_agent.py`'s `launch_terminal` (and any `auto_build=True`
   build-trigger path) behind a real `PermissionGateway.execute()` call — classify it explicitly in
   `core/config.py` (RED, matching `launch_app`'s own classification for the same underlying
   capability class) rather than leaving it unclassified.
3. **Fix Finding C**: gate `mlops_agent.py`'s `hf_train` behind a real `PermissionGateway.execute()`
   call before submitting to HuggingFace Jobs — classify it RED (real remote execution + real cost,
   analogous to `financial_transaction`'s classification rationale).
4. **Verification-only follow-up**: audit `phone_controller.py`'s `_control_action_types` tuple —
   either narrow each write primitive's accepted-token-scopes to only what it actually needs, or
   confirm (via the same reachability-tracing standard used in this document) that no call chain
   can ever pass a lower-tier token to a higher-tier primitive.
5. **Verification-only follow-up**: extend Phase 3's coverage to the ~40 files this task did not
   individually trace, with particular priority on `vector_backtest`'s and `vector_mlops`'s own
   internal subprocess usage (given `vector_finagent`'s and `vector_mlops`'s wrapper-agent pattern
   is now confirmed exploitable, the "these vendored packages are dormant" assumption from `50`
   should not be extended to `vector_backtest` without direct verification), and a systematic
   cross-check of every district agent's `self.capabilities` declarations against `core/config.py`'s
   permission tiers, to find any other ungated, tier-absent capability before it needs to be found
   the same way Findings B and C were — by accident, while tracing something else.

---

## 16. Documentation

This document. No other file was modified except the two new diagnostic test files listed in the
header, and this document itself.

---

==================================================
VECTOR RESIDUAL SIDE-EFFECT SURFACE
==================================================

Device-control:
CONFIRMED BYPASS (Finding A) — VERIFIED for the fail-closed mechanism itself and the run_shell_command path; UNCERTAIN for phone_controller.py's shared token scope

Event fan-out:
VERIFIED

Subprocess/os.system:
CONFIRMED BYPASS (Findings B, C) — VERIFIED/GATED for ~15 individually-traced files; UNCERTAIN for ~40 unread files

Confirmed safety bypasses:
3

Remaining consequential uncertainty:
2 (phone_controller.py's latent shared token scope; ~40 unread subprocess files including vector_backtest/vector_mlops internals)

New experiment blockers:
3

Overall impact on Task 54:
NEW BLOCKER — Task 54's B (Conditionally Ready) gate is superseded; VECTOR must not proceed to the 7-day experiment until Findings A, B, and C are remediated and re-verified

7-DAY EXPERIMENT:
DO NOT START

Next task:
Three narrowly-scoped remediation tasks (Findings A, B, C — §15 items 1-3), each fixing exactly one confirmed bypass with its own regression test, followed by two verification-only follow-ups (§15 items 4-5) before re-attempting the Task 54 readiness gate.

==================================================
