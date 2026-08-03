# VECTOR — Known Issues Log

Only unresolved issues live here — everything already fixed (or accepted as a
non-bug/design limitation) has been removed. Full history, including every
root-cause trace and verification detail for the ~50 issues that have been
closed, is preserved verbatim in **`KNOWN_ISSUES_ARCHIVE.md`**.

Last cleaned up: 2026-08-04 — overnight session added #8 (git push blocker,
needs owner) and #9 (live re-verification of tonight's Phase 1-6 changes,
needs live backend); #3, #4, #5, #6 fixed and live-verified against a
freshly restarted backend on 2026-07-30; #1/#2 genuinely need the owner; #7
is a verification task, not a code fix, still open.

---

## Needs owner action (not code-fixable by the agent alone)

1. **Instagram "AI Creator" toggle** — reported once, root-caused (2026-07-28)
   as very likely a real Instagram *app* feature, unrelated to any VECTOR code
   path (exhaustive codebase search found zero matches for any related toggle
   name). Needs the owner to confirm: which surface was this on (real
   Instagram app vs. something VECTOR renders), what was tapped, ideally a
   screenshot. See archive issue #10 for the full investigation.

2. **WebAuthn/passkey login** — code complete, unit + integration tested
   (10/10 tests passing), but never exercised against a real browser + real
   authenticator + the live API. Needs the owner to: `pip install -r
   requirements.txt`, restart the API, open `http://localhost:8000` (must be
   `localhost` or `https://` — WebAuthn requires a secure context), then run
   `VECTORAuth.register()` then `VECTORAuth.login()` in the browser console
   (no UI button wired yet — optional follow-up). See archive issue #34.

8. **9 overnight commits (2026-08-03/04) are local only — `git push` failed.**
   Branch `production-hardening-complete`, commits `a16d2eb09` through
   `3f4c7f51f` (9 commits: Phase 1 routing, Phase 2 memory, Phase 3
   guardrails, Phase 5 idempotency, Phase 6 vendored-integration fix, in that
   dependency order — see the section below for what each contains). Pushing
   from the sandboxed dev environment failed: `fatal: could not read
   Username for 'https://github.com': No such device or address` — no
   GitHub credentials are available in that sandbox, and per this project's
   own safety rules the agent will not handle/enter credentials on your
   behalf. **You need to either run `git push origin
   production-hardening-complete` yourself from a machine with GitHub auth
   configured, or provide a way to authenticate.** Nothing has been force-
   pushed or rewritten — this is a plain fast-forward push once you're
   authenticated.

9. **Tonight's Phase 1-6/8 fixes are verified against a scratch copy of the
   real DB + real code paths, not the actual live API/websocket/voice
   surface.** Update: the "encrypted DB unreadable in the sandbox" limitation
   documented earlier turned out to be a missing `sqlcipher3-binary` pip
   package, not a fundamental sandbox limit — installing it let the sandbox
   open a **copy** of the real `vector_memory.db` (never the live file
   itself, to avoid any risk to production data) and actually run
   `ConsolidationBot.run()`, `PermissionGateway`'s owner-approval branching,
   the taint-check regex, and `MLOpsAgent.run()` against real code and real
   (copied) data. Confirmed working: `remember`/`recall` round-trip against
   real historical episodic rows; `push_github`/etc. correctly force
   `_council_verdict = "defer"` (skip auto-proceed, go to owner approval);
   the taint-check regex correctly fires on shell/fetch task_types and
   correctly leaves `execute_code` alone; `mlops_agent`'s namespace fix
   resolves the real vendored package end-to-end (see the new fixed-tonight
   entry below for what this surfaced). **Still not done — needs your real
   machine**: the actual HTTP/websocket API surface, real TTS/voice
   pipeline, real Ollama/Gemini calls (this sandbox's network policy blocks
   Ollama entirely and 403s Gemini/OpenRouter — confirmed while testing
   `ml_plan`, not a code bug), and a full DeepEval suite re-run.

---

## Needs engineering work

10. **Live-reproduced: "remember X" from the real HUD chat misroutes to
   `chief_of_staff`, not `memory_curator` — the exact Governor capability-
   match/HP-lottery failure mode already flagged as deliberately deferred,
   caught live for the first time tonight.** With the real backend running
   (started via START_VECTOR.bat) and the real HUD open in a browser:
   typing "Remember that Claude ran a live verification test..." got the
   documented, correct, honest `_llm_answer()` caveat ("I don't have
   tool-calling in this reply path") — the classifier didn't treat it as an
   action at all, so it never left the safe conversational path. A second,
   near-identical message ("Remember that my favorite color is teal.") DID
   get classified as an action, but landed in `chief_of_staff`, which has no
   capability for it — its highest-HP agent just returned its own unrelated
   default output (a daily accomplishments/decisions-needed brief) instead
   of an error, exactly the HP-lottery pattern described all session as the
   most load-bearing, deliberately-unredesigned mechanism. Root cause:
   `classify_chat_intent()` (`core/city/governor.py`) only auto-corrects
   district via `DISTRICT_TASK_MAP` when the LLM-invented `task_type`
   string is an *exact* key match (e.g. literally `"remember"`); tonight's
   Phase 2 fix added `remember`/`recall`/`memory_store`/`memory_query` to
   `consolidation_bot`'s *capabilities* (a separate list, consulted only
   after Governor has already picked a district) — it never touched
   `classify_chat_intent()`'s own district-guessing, so a real memory
   request is still one LLM-classifier guess away from working correctly.
   **This is a pre-existing gap, not a regression from tonight's changes**
   (confirmed: `remember`/`recall` were already present in `DISTRICT_TASK_
   MAP` before tonight). Concrete evidence for the Governor capability-
   match/HP-lottery redesign conversation already flagged as needing the
   owner awake — this is the live instance of exactly that risk, not a new
   category of bug. Not fixed tonight: touching `classify_chat_intent()`'s
   prompt/matching logic without the owner reviewing risks regressing the
   100+ other routes this function already gets right.

11. **FIXED same session, live-caught by the owner reading #10's own output:**
   the misrouted `chief_of_staff` reply above contained raw markdown syntax
   (`#`, `**`, leading `-` bullets) — correct for chief_of_staff's own
   executive-brief document view, but never stripped before reaching the
   owner as a conversational reply. Traced to `AvatarVoice.format()`
   (`core/avatar/avatar_voice.py`) — the one shared formatter every district
   response passes through — which sanitises internal codenames, adds
   empathy, enforces personality tone, and guarantees first person, but had
   no markdown-stripping step at all. 2026-07-30's #105 fix only covered the
   streaming voice paths' own LLM-generated text, not this shared formatter,
   so raw syntax markers reached chat visibly broken and would be read aloud
   literally ("hash", "asterisk", "hyphen") over voice. Fixed: added
   `_strip_markdown()` (headers, bold/italic both delimiter styles, inline
   code, leading bullets — deliberately leaves numbered-list prefixes alone,
   not the same unpronounceable-symbol problem), wired in as the first
   content transform in `format()`. Verified: 6/6 isolated cases + one full
   end-to-end `format()` test using the exact live-observed chief_of_staff
   brief shape from #10 (commit `a361a60b9`).

7. **DONE (2026-08-04): full 65-item DeepEval golden-dataset re-run against
   the live backend, first time this suite ever actually completed.**
   Raw result: **33/65 = 50.8%**. That number is misleading on its own —
   13 of the 32 failures are eval-infrastructure noise, not VECTOR quality
   problems: 8 are "empty response" from items that happened to fire during
   the ~90s window the watchdog was mid-restart (see #11/commit `e517f1f34`
   above — same run that live-verified the watchdog fix), and 5 more are
   local Ollama judge (`qwen3:14b`) `RetryError...TimeoutError` failures,
   not VECTOR failures at all — caused by the same resource contention (see
   below). **Adjusted: 33/52 = 63.5%** once those 13 non-VECTOR-fault items
   are excluded. Still not a great number, and the remaining ~18 failures
   are real and worth root-causing, in two clusters: (a) `correctness=0.00`
   on several single-topic tier1/tier6 items (`chief_of_staff`, `qa`,
   `learning`, `karpathy_lab`, `health+personal_growth`, `coding+qa`,
   `memory+self_awareness+privacy`) — reads like the same stub/off-topic
   default-output pattern flagged elsewhere this session, not yet confirmed
   against the raw response text; (b) a `hallucination=0.00` cluster
   (`chief_of_staff+communications`, `projects+coding`,
   `growth+content+safety`, `karpathy_lab`, `brain`, `design`,
   `predictive_analytics`) — worth checking whether these are genuine
   fabrication or the judge over-triggering on VECTOR's legitimate
   persistent-memory recall (the Hallucination metric's own criteria text
   tries to guard against that false-positive but may not be catching it
   consistently). Neither cluster has been read against the actual
   response text yet — `deepeval_report.json` has the full per-item
   input/output/score for follow-up. `tier1/safety_malware` also failed on
   "expected a refusal but none of the known refusal markers were found" —
   worth a manual read too, since that's a safety-relevant check and could
   be a real refusal that just used different wording than the pattern
   list expects, not necessarily VECTOR failing to refuse.

   **Separate finding, same run: real resource contention between VECTOR's
   full boot (170 agents/39 districts) and the local Ollama judge
   (`qwen3:14b`) used for scoring.** After the watchdog fix (#11) held
   VECTOR stable for ~85 minutes straight (03:16-04:42), it started getting
   killed and restarted every ~5 minutes again from 04:42 onward — but this
   time with a REAL cause, not the old redirect bug: `/health` was
   genuinely timing out past the already-loosened 45s limit, consistent
   with real CPU/RAM starvation while the judge model ran continuously in
   the background. Confirmed by timing: the cycling started right when
   Phase B (scoring) got going and stopped once Phase B's `DONE_MARKER`
   printed — VECTOR held steady again immediately after. Not fixed
   tonight (it's a capacity/scheduling question, not a bug — see the
   87%-RAM-at-clean-boot note above), but now documented with a clear
   before/during/after signature if it recurs. Practical implication: don't
   run the DeepEval judge phase and expect VECTOR itself to stay
   perfectly responsive at the same time on this machine.

   TIER5 (English-only policy) harness re-run is still separately not done
   — different suite, not started this session.

---

## Fixed overnight, compile/unit-verified only — see #9 above (2026-08-03/04)

Full audit trail (root causes, exact diffs, verification detail) is in
`KNOWN_ISSUES_ARCHIVE.md`. Summary, oldest-to-newest commit:

- **FIXED AND LIVE-VERIFIED (2026-08-04, this session): the VECTOR API had
  been crash-looping every ~5 minutes, continuously, for 11 straight days
  (2026-07-23 11:35 through tonight, ~470 failed restart attempts logged),
  and every attempt was silently logged as a false "Restart launched"
  success.** Discovered while diagnosing why the DeepEval suite scored 0/65
  (0.0%) with every response `[WinError 10061] connection refused` — checked
  the live HUD in a browser, found `/status` and `/command` both genuinely
  unreachable while `/hud/` still loaded (served from browser cache/service
  worker, not a real live signal), then found `watchdog.log`
  (`scripts/vector_watchdog.ps1`, the task-#95 self-healing watchdog)
  showing an unbroken `DOWN -> Restart launched` cycle every 5 minutes since
  2026-07-23, never once actually recovering. Root cause: the script's
  `Start-Process -RedirectStandardOutput $log -RedirectStandardError $log`
  pointed stdout and stderr at the *same* file path — PowerShell's
  `Start-Process` hard-rejects that combination
  (`"RedirectStandardOutput" and "RedirectStandardError" are same"`) — and
  the script-wide `$ErrorActionPreference = "SilentlyContinue"` swallowed
  the resulting exception on every single one of the ~470 attempts, so
  `Write-Log` unconditionally printed "Restart launched" whether or not a
  process actually started. (Confirmed independently: `watchdog_restart_
  stdout.log` had never once been created in 11 days, despite the log
  claiming hundreds of successful launches — a real launch would have
  created it immediately.) Fixed: split stdout/stderr into two separate log
  files; resolved a real `python.exe` path via `Get-Command`/`Get-ChildItem`
  instead of relying on bare `"python"` (removes a second, untested
  PATH-resolution risk under Task Scheduler's process-creation context);
  wrapped the launch in `try/catch` with `-ErrorAction Stop` and `-PassThru`
  so any future launch failure is logged loudly with the real exception
  message and a PID, instead of silently assumed to have succeeded.
  **Live-verified, not just compile-checked**: waited for the next real
  5-minute scheduled-task trigger, watched it fail once more with the
  now-surfaced real error message (confirming the diagnosis), then watched
  the following trigger actually launch VECTOR (PID logged), boot all 170
  agents across 39 districts, and serve real `200` responses on `/health`,
  `/status`, and `/command` — confirmed live via the browser HUD and a fresh
  DeepEval run. This means every "live-verified" claim earlier in this
  session that depended on the backend being up at that exact moment was
  genuinely testing a real (if short-lived) live window, not a fabrication —
  but it also means the backend has essentially never been stably available
  between sessions, which likely explains other intermittent oddities
  attributed to other causes over the past 11 days. Not yet done: a review
  of whether 39 districts / 170 agents booting on every restart is itself
  contributing to instability under this machine's RAM pressure (observed
  86.9% RAM used at a normal, healthy boot) — flagged for the owner, not
  fixed tonight, since it's a capacity/design question, not a bug.

- **Phase 1 — dispatch/routing** (`a16d2eb09`): governor-level routing fixes
  bundled with the taint-check fix below.
- **Phase 2 — memory subsystem** (`205f8110a`): wired the previously-dead
  scheduled-forgetting pass into the already-running 2AM reflect cron
  (`autonomous_loop.py`); gave `remember`/`recall`/`memory_store`/
  `memory_query` task_types real handlers in `consolidation_bot.py` instead
  of silently triggering full consolidation; connected the previously-
  orphaned `MemoryRouter` into a real call path; wired the knowledge graph
  into every LLM call's context (`context_engine.py`), not just the explicit
  `knowledge_query` path.
- **Phase 3 — guardrails** (`68de1a08c`, plus routing half in `a16d2eb09`):
  widened `OWNER_APPROVAL_ONLY` in `permission_gateway.py` from just
  `financial_transaction` to also cover `solana_swap_execute`,
  `push_github`, `deploy_production`, `delete_files`, `content_publish`,
  `hand_browser`, `hand_content`, `hand_clip` — closing a gap where real
  money and code pushes could be auto-authorized by an LLM council vote
  alone; fixed `avatar_voice.py`'s internal-name substitution so it
  reconjugates the verb instead of producing grammatically broken sentences
  ("CodingBot has reviewed" → "I have reviewed", not "I has reviewed"),
  7/7 regression cases verified; fixed the taint-check task_type matching in
  `governor.py` so the SHELL_EXEC/NET_FETCH security control actually fires;
  extended the English-only Devanagari backstop to the district-dispatch
  response path.
- **Phase 5 — idempotency** (`dddd78b17`): content-hash dedup for social
  posts (`social_safety.py`), duplicate-order suppression
  (`execution_engine.py`), non-terminal-job dedup (`post_job.py`).
- **Phase 6 — vendored integration reachability** (`3f4c7f51f`):
  `districts/coding/vector_mlops/agent/` was silently 100% non-functional
  (never on `sys.path`) — every `ml_research`/`hf_dataset`/`github_ml`/
  `hf_train`/`ml_plan` call in `mlops_agent.py` failed. A naive
  `sys.path.insert` fix would have collided with `vectorcode`'s own,
  unrelated `agent` package (both are bare top-level `agent`, and
  `vectorcode/src` is already on `sys.path` for nearly every module) —
  whichever imported first would silently break the other for the rest of
  the process. Fixed with a lock-guarded context manager that swaps
  `sys.modules['agent'*]` and `sys.path` only for the duration of each call,
  no vendored code touched. (`vector_backtest`'s `agent/` was checked too —
  confirmed not at risk, it imports as `src.agent.loop`.)

Phase 4 (district-level bugs) had no changes left to make this session —
everything found in that sweep was already covered by the fixes above or
previously-closed archive issues.

- **Phase 8 — deep live-DB verification, found + fixed 2 more real bugs**
  (`da40f4303`): installing `sqlcipher3-binary` unblocked real DB access in
  the sandbox (see #9 above), which let `mlops_agent.py`'s Phase 6 namespace
  fix actually reach vector_mlops's real code for the first time ever —
  exposing that `ml_research()` and `ml_plan()` called vendored functions
  that either never existed under those names, or (once the name was fixed)
  needed a live vector_mlops `AgentLoop` session object that isn't safely
  constructible standalone, or expected a completely different parameter
  shape than what was passed (`plan_tool.py`'s `PlanTool` is a todo-list
  state tracker, not a plan generator — there was no version of the old call
  that could have worked). Both were pre-existing bugs, invisible until
  Phase 6 fixed the `agent` namespace collision that made every import here
  fail first. Fixed by calling the reasoning LLM directly instead (same
  pattern as this agent's own `_answer_query`) — a real, working capability,
  trading away the vendored tool's live citation-graph lookups for a
  simpler but actually-functioning answer. Also fixed 3 more wrong names in
  the file's own self-test. `hf_dataset`/`github_ml`/`hf_train`/`hf_hub`
  were checked too and call real, correctly-shaped functions — no bug there.

- **Phase 8 continued — audited the other 3 vendored bridge agents, found +
  fixed 2 more** (`bbde3a30c`): `backtest_agent.py`'s `vt_backtest()`
  imported `BacktestConfigSchema` from the wrong module (it lives in
  `backtest.runner`, not `backtest.models`); `shadow_account()` called a
  function (`extract_rules`) that never existed and hand-built a
  `ShadowProfile` with a field name (`source_path`) that isn't one of its
  11 real fields on a frozen dataclass — rewrote it to call the real
  `extract_shadow_profile(journal_path)`, which does the whole pipeline
  itself. `vt_swarm`/`vt_skills`/`vt_export`/`vt_research` were checked too
  (every class/function signature cross-referenced against the real
  vendored files) — all correct. `finagent_agent.py` and `hedgebot_agent.py`
  were also fully checked — clean, no bugs: they use absolute dotted-path
  imports that were already validated against real names at write time,
  unlike the other two agents' bare-import + sys.path-trick pattern where
  naming drift could hide behind an import that failed before it mattered.

---

## Fixed and live-verified today (2026-07-30)

3. **`languages` district picked the wrong specific-language coach.** All 5
   language coaches share near-identical manifest capabilities (`[languages,
   <lang>, coaching]`), so a generic invented task_type gave capability-match
   nothing specific to grab and it fell to an HP tiebreak, always landing on
   the same coach regardless of which language was actually asked for. First
   fix attempt (fall back to matching the query text only when the invented
   type had zero word-overlap with any known key) still failed live: traced
   via `vector_api.log`, the LLM's invented type `"language_quiz"` was
   word-overlapping the generic `"language_coach"` key (shares the word
   "language") *before* the text fallback could ever run — and
   `"language_coach"` isn't a real capability on any agent, so it dead-ended
   at the same HP lottery anyway. Fixed by reordering `_snap_to_known_task_
   type()` to check the original query text for an unambiguous (exactly one)
   known-key match *first*, before the word-overlap pass — a literal word the
   user actually typed is strictly more trustworthy than an LLM's invented
   guess, and it's scoped to the already-decided district so it can't cause
   cross-district confusion. **Live-verified** after restart across all 3
   testable languages via 2 different LLM-invented phrasings each: "Quiz me
   on some Hindi vocabulary" -> `action_taken: "hindi"`, real Devanagari
   vocabulary (किताब/book, अध्ययन/study, सफलता/success); "Quiz me on some
   Japanese vocabulary" -> `action_taken: "japanese"`, real Japanese content;
   "Give me a Bengali vocabulary quiz" -> `action_taken: "bengali"`, real
   Bengali content (খাবার/food, অধ্যয়ন/study). (Assamese untested live —
   same code path, no reason to expect it differs.)

4. **Streaming voice paths had no deterministic English-only backstop.**
   `realtime.py::_stream_chat` already collects the FULL response before any
   TTS happens (the "streaming" there is just sentence-chunked playback) —
   added the same hard `_ensure_english_response()` guarantee text chat has,
   right before playback starts. `voice_ws.py::_stream_respond` is genuinely
   incremental (first sentence plays while the rest generates), so it now
   gates only the first sentence on a Devanagari check and falls back to the
   batch path on failure; the batch path (`_llm_respond_with_personality`)
   now carries the full translate-retry backstop. Compiles clean; Devanagari
   check verified against real Hindi/English strings. (Real synthesized
   audio still not listened to end-to-end — only the pre-TTS text logic is
   verified, same residual as before.)

5. **Vendored third-party subprojects** (`vector_mlops`, `vector_finagent`,
   `vector_backtest` — 1,700+ files combined; a full audit is genuinely out
   of scope) — confirmed the only registered bridge agents into these trees
   (`mlops_agent.py`, `finagent_agent.py`, `backtest_agent.py`,
   `hedgebot_agent.py`) were already swept in the #36 continuation, and
   grepped all three trees for the highest-risk patterns (subprocess,
   destructive file ops, real broker/trading clients, email/SMS senders).
   **Found and fixed a real bug in the process:** `backtest_agent.py`'s
   `sys.path` setup had one `.parent` too many and pointed at a directory
   that doesn't exist — every `from src...`/`from backtest...` import in
   that file had been silently failing (caught by a broad `except
   Exception`) since it was written, so all 6 of its governor routes
   (`vt_research`, `vt_backtest`, `shadow_account`, `vt_swarm`, `vt_skills`,
   `vt_export`) always failed closed instead of running. Fixed the path;
   confirmed the real imports now resolve. The other subprocess hit reachable
   from a registered agent (`vector_finagent/terminal_launcher.py`)
   builds/launches a local Qt desktop binary — not a safety concern.
   `vector_finagent/agents/rdagents/` isn't imported by `finagent_agent.py`
   at all — dead code as far as VECTOR's dispatch is concerned. A full
   file-by-file audit of all 1,700+ files remains out of scope.

6. **`memory_curator`'s `entity_add` task_type** — gave `ConsolidationBot`
   real handlers (`_kg_write`/`_kg_query`) for `entity_add`/`knowledge_add`/
   `relation_add`/`knowledge_relate`/`knowledge_query`, wired to the real
   `KnowledgeGraph` API, and added these as literal capabilities in
   `agent_manifest.yaml` so Governor's capability-match routes to it
   deterministically. **Live-verified**: "Remember that VECTOR runs on Ollama
   and add that as a knowledge graph entity" now returns `action_taken:
   "entity_add"`, `district: "memory_curator"`, response "Noted for the
   knowledge graph: that VECTOR runs on Ollama" — the real handler fired
   instead of the old unrelated consolidation default.
