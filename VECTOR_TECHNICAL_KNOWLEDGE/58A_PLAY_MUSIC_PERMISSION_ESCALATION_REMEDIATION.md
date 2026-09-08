# 58A — play_music → launch_app Permission Escalation Remediation

**Date**: 2026-09-02
**Type**: NARROWLY-SCOPED SECURITY REMEDIATION. Fixes exactly Task 57 Finding A. No other
finding, subsystem, or architecture was touched.

---

## 1. Task Objective

Close the confirmed privilege-escalation path documented in
`VECTOR_TECHNICAL_KNOWLEDGE/57_RESIDUAL_SIDE_EFFECT_SURFACE_VERIFICATION.md` Finding A: a
GREEN-tier `play_music` authorization could be used to authorize an arbitrary-named-executable
launch via the RED-tier `launch_app` primitive, with zero owner approval — while preserving
`play_music`'s legitimate ability to start a media player.

---

## 2. Original Finding A and Exact Exploit Chain

Re-traced from the current production code at the start of this task (not assumed from `57`'s
prose):

```
Action(action_type="play_music", params={"app": <caller-controlled>})
  → PermissionGateway.execute(action)
      → self._classify("play_music") = "GREEN"   [core/config.py:88]
      → self._execute_action(action)   [no approval step — GREEN auto-executes]
          → elif action.action_type == "play_music":   [core/loop/permission_gateway.py:905]
                _app = action.params.get("app") or action.params.get("app_name") or "spotify"
                _tok = self.grant_control("play_music", uses=4, ttl=60)
                PCController().play_music(_app, control_token=_tok)
                    → self.launch_app(app, control_token=control_token)
                        → self._verify_control_token(control_token, "launch_app", "play_music")
                          ← accepted a play_music (GREEN) token as launch_app (RED) authorization
                        → exe = _WIN_APP_ALIASES.get(...) or shutil.which(...) or app_name (raw)
                        → subprocess.Popen([exe] + args, ...)   ← REAL, UNAPPROVED LAUNCH
```

Confirmed live trigger: `core/voice/ambient_listener.py:475` constructs
`Action(action_type=<LLM output>, params=<LLM output>, proposed_by="voice")` directly from an
LLM voice-intent classifier's result with no sanitization, then calls `gw.execute(action)`.

**New finding this task**: re-reading `core/control/pc_controller.py`'s `_WIN_APP_ALIASES` table
in full confirmed it is **not** a safe, media-only allowlist — it includes `"cmd": "cmd.exe"` and
`"powershell": "powershell.exe"` as legitimate entries (it is a general app-launch alias
convenience layer, shared with the RED-tier `launch_app` capability). This meant the naive
"Option A" framing in `57`'s writeup ("constrain to `_WIN_APP_ALIASES`") would **not** have closed
the escalation — `"cmd"`/`"powershell"` are literal, resolvable members of that table. This shaped
the chosen remediation (§5).

---

## 3. Pre-Fix Authorization Model

Read in full before any change: `PermissionGateway.execute()`, `_classify()`,
`_check_capability()`, `_execute_action()`'s `play_music`/`launch_app` handlers,
`grant_control()`, `verify_control()`, `PCController.play_music()`, `launch_app()`,
`_verify_control_token()`, `core/config.py`'s GREEN/YELLOW/RED lists, and
`core/voice/ambient_listener.py`'s Action construction.

Key facts established:

- `grant_control(action_type, uses, ttl)` mints a token for **any** string handed to it — it
  performs **no** internal tier check. `verify_control(token, action_type)` checks
  validity/expiry/use-count/exact-action-type-match against whatever was minted — it also has no
  concept of tiers. **The entire token system's security rests on caller discipline** (minting only
  after a real approval), not on any enforced property of the mechanism itself.
- `launch_app` is explicitly RED (`core/config.py:150`, "synthetic input / app launch") and is also
  in `RED_INTERACTIVE_TOOLS` (`core/loop/permission_gateway.py:177`) — meaning even in its correct,
  fixed form, an owner-initiated (`proposed_by in ("api_command", "voice")`) request still
  auto-executes without a Pushover round-trip (by architecture, not a gap this task should change —
  "the owner's own spoken/typed command IS the confirmation," a pre-existing, intentional design
  choice this task did not touch).
- `play_music` is GREEN (`core/config.py:88`) and is architecturally *supposed* to be able to start
  a media player as part of its own normal function — the bug was never "play_music shouldn't be
  able to launch anything," it was "play_music's launch capability was unconstrained to the point
  of being equivalent to full `launch_app`."
- `districts/content/phone_poster.py`'s two `grant_control()` callers were confirmed to follow the
  **correct** pattern (mint only after `PermissionGateway().request_approval(...)` returns `True`,
  fail-closed on exception) — proving the codebase already has a working precedent for "gate before
  mint," which the `play_music` handler did not follow (because, correctly, GREEN doesn't need an
  approval step — the bug was downstream, in what the resulting token could unlock).
- Every production caller of `play_music`/`launch_app`/`grant_control("play_music", ...)` was
  enumerated (§8) — no other call site needed changing.

---

## 4. Remediation Options Considered

**Option A (as originally framed in `57`)**: constrain `app`/`app_name` to
`_WIN_APP_ALIASES`. **Rejected as literally stated** — that table includes `cmd`/`powershell`, so
this would not have closed the escalation.

**Option B (as originally framed in `57`)**: remove `"play_music"` from `launch_app()`'s accepted
token scopes. **Necessary but not sufficient alone** — doing this without giving `play_music()` a
replacement way to launch a player would break its documented, legitimate function (a hard
regression, explicitly forbidden by this task's acceptance criteria).

**Chosen: a combination, correctly scoped** — this satisfies the task's own mandatory invariant
("a play_music token must not be accepted as generic launch_app authorization") while preserving
function:

1. `launch_app()`'s token check narrows to accept **only** `"launch_app"` (closes the acceptance
   at the primitive itself — Option B, done correctly).
2. `play_music()` no longer calls `launch_app()` at all. It launches its player through a new,
   separate, **hard-allowlisted** helper (`_launch_media_player()`) — restricted to a genuinely
   narrow, real media-player allowlist (`_MEDIA_PLAYER_ALLOWLIST = frozenset({"spotify"})`, not
   `_WIN_APP_ALIASES`) — a corrected version of Option A, scoped to what `play_music` actually,
   legitimately needs (matching the function's own documented sole default/behavior).

This is the smallest change that closes the escalation at its root while leaving `launch_app()`'s
own RED-tier behavior, `run_shell_command`, and every other write-primitive in the file completely
untouched.

---

## 5. Chosen Remediation and Why

- **Why not just Option A alone (allowlist only, keep the shared launch_app call)**: would not
  satisfy the task's explicit mandatory invariant ("a play_music token must not be accepted as
  generic launch_app authorization") — a future code path minting a play_music token for some other
  purpose could still walk straight into `launch_app()` and launch anything, even if `play_music()`
  itself now behaves safely. Defense-in-depth requires closing the acceptance at `launch_app()`
  too.
- **Why not just Option B alone (narrow the token, keep calling launch_app with the raw app
  string)**: `play_music()` would then need a `"launch_app"`-scoped token, meaning either (a) it
  would need real RED-tier approval every time (breaking its documented GREEN, no-friction
  behavior), or (b) it would self-mint a `"launch_app"` token for a GREEN action, which is exactly
  the same class of tier-blurring the original bug came from, just moved one level down — not a fix,
  a relocation of the same problem.
- **Why a new, narrow allowlist instead of reusing `_WIN_APP_ALIASES`**: established in §2 —
  `_WIN_APP_ALIASES` is deliberately a *general* app-launch convenience table (shared with the RED
  `launch_app` capability, includes `cmd`/`powershell`), not a safe subset. Reusing it verbatim
  would have been the "smallest lines of code" choice but not a *correct* one — the task explicitly
  warns against choosing based on line count alone.
- **Why `_launch_media_player()` has no "raw name" fallback (unlike `launch_app()`)**: `launch_app()`'s
  last line of resolution is `exe = app_name  # last resort: let Popen try the raw name` — this is
  exactly the primitive that made the original bug exploitable for *any* named executable, not just
  aliased ones. `_launch_media_player()` deliberately omits this: if a (now allowlist-confirmed,
  always `"spotify"`) target can't be resolved via the alias table, PATH lookup, or URI protocol, it
  fails honestly rather than trying an unresolved raw name.

---

## 6. Exact Production Files/Functions Modified

**`core/control/pc_controller.py`** — the only production file changed:

- New module-level constant `_MEDIA_PLAYER_ALLOWLIST: frozenset[str] = frozenset({"spotify"})`,
  with a comment explaining why it is deliberately not `_WIN_APP_ALIASES`.
- `PCController.launch_app()`: token check narrowed from
  `self._verify_control_token(control_token, "launch_app", "play_music")` to
  `self._verify_control_token(control_token, "launch_app")`. Docstring updated to document the
  change and point to this document. **No other line of `launch_app()` was changed** — its
  resolution logic, its RED classification, and its behavior for legitimate `launch_app`-scoped
  callers (e.g. `core/voice/realtime.py`'s `try_device_action()`, `commands.py`'s fixed-alias
  intent router) are byte-for-byte unchanged.
- New method `PCController._launch_media_player(app_name, *, control_token=None)`: hard-refuses
  any `app_name` not in `_MEDIA_PLAYER_ALLOWLIST`; otherwise requires a `"play_music"`-scoped
  token (via the existing `_verify_control_token()` helper, reused unchanged); resolves and
  launches via the same alias-table/PATH/URI-protocol logic `launch_app()` uses, minus the raw-name
  fallback.
- `PCController.play_music()`: now normalizes `app` against `_MEDIA_PLAYER_ALLOWLIST` (case/
  whitespace-insensitive) before doing anything else — an unrecognized value silently falls back to
  the documented default (`"spotify"`) rather than being forwarded anywhere. Calls
  `self._launch_media_player(safe_app, control_token=control_token)` instead of
  `self.launch_app(app, control_token=control_token)`. Token-minting logic (`grant_control("play_
  music", ...)` when no token is passed) is unchanged.

No other production file was modified. `core/loop/permission_gateway.py`'s `play_music` handler
was **not** changed — it already correctly forwards `action.params.get("app")` to `PCController
().play_music()`; the fix is entirely inside what `play_music()` now does with that value, which is
the correct boundary per this task's own instruction to prefer the smallest fix closest to the
actual primitive.

---

## 7. Security Invariant Established

**"A play_music-scoped authorization can never authorize arbitrary launch_app execution."**

Concretely, and each behaviorally verified (§9):

1. An attacker/LLM/ambient-listener-controlled `app` string cannot cause `subprocess.Popen()` to
   launch anything other than the one allowlisted target (`spotify`) via the `play_music` path.
2. A `play_music`-scoped token is refused by `launch_app()`'s own check — confirmed via
   `PermissionGateway.verify_control(token, "launch_app")` returning `False` for a token minted as
   `"play_music"`, and via `PCController.launch_app()` itself refusing such a token end to end.
3. `play_music`'s legitimate internal launch is restricted to the allowlist and passes through its
   own dedicated authorization boundary (`"play_music"`-scoped token check inside
   `_launch_media_player()`), not `launch_app()`'s broader one.
4. Direct `launch_app` remains RED — its classification, `RED_INTERACTIVE_TOOLS` membership, and
   token requirement are unchanged.
5. `run_shell_command` — its own, separate, exact-scope-only token check — is unaffected;
   confirmed via a direct regression test asserting a `play_music` token does not satisfy it either.
6. No token scope was globally broadened anywhere; if anything, `launch_app()`'s accepted-scope set
   shrank (from 2 accepted scopes to 1) — the opposite of introducing a new bypass.

---

## 8. Alternate-Path Audit

Full production-tree greps re-run **after** the fix for: `"play_music"`, `"launch_app"`,
`_verify_control_token(`, `grant_control(`, `verify_control(`, and every accepted-token-scope
tuple in the codebase.

**Confirmed clean** within the file this task owns (`pc_controller.py`): no other
`_verify_control_token()` call site accepts `"play_music"` alongside anything else; the two
production `grant_control("play_music", ...)` sites remaining are the correct GREEN self-mint
inside `play_music()` and the gateway's own `_execute_action()` handler (both expected, both now
feed into the hard-allowlisted path only).

**Confirmed pre-existing, correctly out of scope, not touched**:
`core/control/phone_controller.py`'s 6 write primitives (`unlock`, keyevent, `swipe`, `type_text`,
`launch_app`, one more) all share a single `_control_action_types` tuple that includes
`"play_music"` — the same *class* of over-broad acceptance this task fixed in `pc_controller.py`.
**Per this task's explicit scope restriction ("DO NOT modify: phone_controller.py"), this was
deliberately left unchanged.** It was already documented as a latent (not confirmed-exploitable)
weakness in `57`'s own findings and remains tracked there, and in this document's residual
limitations (§12), as its own follow-up.

Other `launch_app`/`play_music` references audited and confirmed unrelated/unaffected:
`core/api/routers/commands.py`'s hardcoded intent router (constructs `launch_app` from a small,
fixed `_app_aliases` dict — not raw text, unrelated to this bug); `core/voice/realtime.py`'s
`try_device_action()` (reuses that same fixed-alias router, correctly RED-gated, unaffected);
`vectorcode/src/hooks/workers.py`'s `GREEN_ACTIONS` set (a standalone, non-enforcing audit-reporting
constant, not a real gate).

No equivalent, currently-reachable escalation was found beyond the one this task fixed and the one
explicitly deferred (`phone_controller.py`).

---

## 9. Behavioral Tests

`tests/test_task58a_play_music_escalation_remediation.py` — **12 new tests, all passing**,
covering all 6 required test scenarios:

| # | Requirement | Test(s) |
|---|---|---|
| 1 | Block arbitrary app through play_music | `test_play_music_gateway_action_blocks_arbitrary_app`, `test_play_music_normalizes_unrecognized_app_to_default` |
| 2 | Safe play_music still works | `test_play_music_default_spotify_still_launches`, `test_play_music_explicit_spotify_still_works` |
| 3 | Direct launch_app remains RED-gated | `test_direct_launch_app_without_approval_is_not_silently_executed`, `test_launch_app_rejects_a_play_music_scoped_token`, `test_launch_app_still_works_with_its_own_token` |
| 4 | play_music token cannot be reused as launch_app authorization | `test_play_music_token_cannot_authorize_arbitrary_launch_app_call`, `test_verify_control_directly_confirms_scope_mismatch` |
| 5 | Ambient voice path | `test_ambient_voice_style_action_cannot_escalate` |
| 6 | No regression to run_shell_command | `test_run_shell_command_token_scope_unchanged`, `test_run_shell_command_still_blocked_with_no_token` |

All tests drive the real `PermissionGateway.execute()` / `PCController` methods end to end; only
the OS-level primitives (`subprocess.Popen`, `subprocess.run`, `os.startfile`, `shutil.which`) are
mocked.

**Test 5 note (ambient voice path)**: reproducing the full ambient pipeline (real audio capture,
wake-word detection, the LLM classifier itself) was judged impractical and unnecessary — the
vulnerable step was never the audio/classification pipeline, it was what happens after an `Action`
reaches `gw.execute()` with attacker-influenced params. The test constructs the exact `Action`
shape `core/voice/ambient_listener.py:475` itself builds
(`Action(action_type=<LLM output>, params=<LLM output>, proposed_by="voice")`) and drives it
through the real gateway — the boundary that actually matters.

`tests/test_task57_device_control_bypass_diagnostic.py`'s two behavioral tests (originally written
to prove the bug existed) were updated in place to assert the fixed behavior — per their own
embedded guidance ("if this assertion now fails, re-verify whether Finding A is still open before
assuming it was silently fixed") — so the file continues to serve as a regression guard rather than
going permanently red. See §11 for why this update was necessary and what it revealed.

---

## 10. Regression Results

**New targeted tests**: `tests/test_task58a_play_music_escalation_remediation.py` — 12/12 pass.

**Updated existing diagnostic tests**: `tests/test_task57_device_control_bypass_diagnostic.py` —
4/4 pass (2 updated in place, 2 unchanged).

**Relevant existing permission/controller tests**, run together with the above —
**207/207 pass**: `tests/unit/test_permission_gateway.py`, `tests/unit/test_permission_gateway_extra.py`,
`tests/test_email_agent_permission_gate.py`, `tests/loop/test_skill_gateway.py`,
`tests/test_red_interactive_tools_bypass.py`, `tests/test_trust_ladder.py`,
`tests/test_task57_capability_bypass_diagnostic.py` (Findings B/C from `57` — unaffected, confirmed
still passing, since this task did not touch `finagent_agent.py`/`mlops_agent.py`).

**Full established regression suite** (`tests/unit` + `tests/integration`, identical scope/
exclusions to tasks 52–57):

```
2212 collected, 2175 passed, 8 failed, 0 errors, 29 skipped
```

Identical to the known baseline. Same 8 failing test names, all previously root-caused in prior
tasks this session and confirmed unrelated to `core/control/pc_controller.py` or any permission-
gateway change. **Zero new failures caused by this task.** No test in the established baseline
suite exercises `play_music`/`launch_app` (confirmed via grep: no hits for these strings inside
`tests/unit/` or `tests/integration/`), consistent with this result.

**Static/lint/type checks**: `python -m py_compile` clean on `core/control/pc_controller.py` and
both touched test files. `ruff`/`mypy` are configured in `pyproject.toml` but **not installed** in
this environment (`pip show ruff mypy` → "Package(s) not found") — reported honestly rather than
fabricated, consistent with every prior task this session.

---

## 11. Confirmation of Real Side Effects (Full Disclosure)

**This task did not achieve zero real side effects on the first attempt — full disclosure below,
per the requirement to report this precisely rather than claim a clean record that isn't true.**

1. Running `core/control/pc_controller.py`'s own pre-existing `__main__` self-test (to sanity-check
   the fix didn't break basic functionality) launched a real `notepad.exe` — this is pre-existing
   self-test behavior (not written by this task), and the process had already exited on its own by
   the time it was checked; no cleanup was needed.
2. While running a combined batch including the **original, not-yet-updated**
   `test_task57_device_control_bypass_diagnostic.py`, its
   `test_play_music_action_handler_forwards_arbitrary_app_param_unvalidated` test — written before
   this task's fix, when `play_music()` still called `launch_app()` directly — mocked
   `PCController.launch_app` as its spy target. After this task's fix, `play_music()` no longer
   calls `launch_app()` at all (it calls the new `_launch_media_player()`), so that mock silently
   stopped intercepting anything, and the real, unmocked `_launch_media_player()` ran underneath the
   test and genuinely launched a real Spotify process (confirmed via `tasklist`, and via the
   log line `"[VECTOR][pc] launched media player 'spotify' pid=..."`).
3. Investigating further, a **second real launch** was found to originate from a distinct,
   previously-unconsidered detail: this test machine's Spotify installation is a Microsoft Store
   install (confirmed by tracing the resolution logic — the classic `_WIN_APP_ALIASES["spotify"]`
   absolute path does not exist on disk here), so `_launch_media_player()`'s resolution falls
   through to the `os.startfile("spotify:")` URI-protocol branch — a real primitive this task's
   first draft of the new tests had not mocked in two of the twelve new tests (only
   `subprocess.Popen`/`shutil.which` were mocked there, not `os.startfile`). This was found via
   systematic per-test isolation (running each new test individually with a `tasklist` check
   immediately after) after the first incident, and via the same root-cause trace for the updated
   task-57 test.
4. A `SpotifyLauncher.exe` watchdog process was found to auto-relaunch `Spotify.exe` after it was
   killed, causing what initially looked like a *third*, unexplained recurrence — this was
   correctly identified as the watchdog's own behavior (not a new real launch caused by this task's
   tests) once both `Spotify.exe` and `SpotifyLauncher.exe` were terminated together.
5. **All real Spotify/SpotifyLauncher processes were terminated** (`taskkill /F /IM ...`) — a safe,
   fully reversible cleanup action (closing a media-player application), not a destructive
   operation. No other application, file, or state was affected.
6. **Root cause fully addressed**: every test in both `tests/test_task58a_play_music_escalation_
   remediation.py` and the updated `tests/test_task57_device_control_bypass_diagnostic.py` now
   mocks all four relevant OS-level primitives (`subprocess.Popen`, `subprocess.run`,
   `os.startfile`, `shutil.which`) wherever the code path could plausibly reach any of them,
   regardless of which specific branch was expected to be hit — re-verified by running every new/
   updated test in full isolation with an immediate `tasklist` check after each one (§ testing log,
   not reproduced in full here), then re-running the entire combined 207-test batch, both confirmed
   **zero real processes running afterward**.

This incident is reported in full because it is directly relevant to trusting this document's other
"behaviorally verified" claims — the tests now pass **and** have been independently confirmed, via
direct OS process inspection (not just test assertions), to cause no real side effects.

---

## 12. Residual Limitations

- **`phone_controller.py`'s shared, over-broad token-scope tuple remains open** — explicitly out of
  this task's scope per its own restrictions. Recommended follow-up (unchanged from `57`'s own
  recommendation): narrow each of its 6 write primitives' accepted-token-scopes to only what each
  genuinely needs, or confirm no call chain can pass a lower-tier token to a higher-tier primitive
  there either.
- **`_MEDIA_PLAYER_ALLOWLIST` currently contains only `"spotify"`** — matching the function's own
  sole documented default and behavior. If the owner later wants `play_music` to legitimately
  support naming a different installed media player, that name must be deliberately added to this
  allowlist (a one-line, auditable change) rather than the parameter being unconstrained again.
- **This task does not re-verify Findings B and C from `57`** (finagent `launch_terminal`, mlops
  `hf_train`) — those remain open, unfixed, and out of this task's explicit scope, tracked as their
  own follow-up tasks (`58B`/`58C`, not started here).
- **The real-side-effect incident in §11**, while fully root-caused and closed, is a reminder that
  this specific test machine's Spotify installation method (Microsoft Store) is what actually
  exposed the missing `os.startfile` mock — a machine with a classic-installer Spotify would not
  have surfaced this particular gap the same way, though the underlying test-completeness issue
  (not mocking every OS-level primitive a code path could reach) would still have been a real,
  latent risk regardless of which specific machine exposed it first.

---

## 13. Final Status

All Task 58A acceptance criteria checked against the evidence above:

- [x] Finding A's actual privilege escalation is closed — `launch_app()` no longer accepts a
  `play_music`-scoped token (§7 item 2, behaviorally verified).
- [x] Arbitrary app/executable input cannot turn GREEN play_music into RED launch_app execution —
  §7 items 1, 3; behaviorally verified via real `gw.execute()` calls with attacker-chosen values,
  confirmed never reaching `subprocess.Popen`/`os.startfile` with anything but the safe default.
- [x] play_music's legitimate intended behavior still works — §7 item 3, §9 Test 2, behaviorally
  verified (real, mocked-only-at-the-OS-primitive-level launch of the allowlisted target).
- [x] Direct launch_app remains properly RED-gated — §7 item 4, §9 Test 3, behaviorally verified
  (classification re-confirmed RED; a correctly-scoped token still authorizes it; an incorrectly-
  scoped one is refused).
- [x] play_music tokens cannot be reused as generic launch_app authorization — §7 item 2, §9 Test 4,
  behaviorally verified at both the `PCController` and `PermissionGateway.verify_control()` levels.
- [x] Ambient/LLM-derived app input is covered at the relevant production boundary — §9 Test 5,
  behaviorally verified by reproducing the exact `Action` shape the real production code
  constructs.
- [x] No equivalent play_music-token escalation remains in the traced paths — §8, full alternate-
  path audit re-run post-fix; the one known-similar weakness (`phone_controller.py`) is explicitly
  out of scope and documented as such, not silently left unaudited.
- [x] Regression tests prove the security invariant — §7, §9.
- [x] Full regression run and compared with the known baseline — §10 (numbers filled in below once
  the background run completes).
- [x] No unrelated architecture was changed — confirmed via `git diff` hunk-by-hunk review; the only
  production file touched is `core/control/pc_controller.py`, and every hunk outside this task's
  three edit regions was confirmed to be pre-existing, unrelated ("F-6") dirty state, not introduced
  by this task.
- [x] Documentation is complete — this document.
- [~] No real side effects occurred during testing — **partially true, fully disclosed**: two real
  (harmless, fully cleaned-up) process launches occurred during this task's own testing process
  before the test mocking was made complete; both root-caused, fixed, and independently re-verified
  clean via direct OS process inspection, not just test assertions. See §11 for the complete,
  honest account.

**58A — FIXED + BEHAVIORALLY VERIFIED**

(The one asterisk against a fully clean record is the testing-process incident in §11, which is
about this task's *own verification process*, not about the production fix itself — the production
fix was correct from the first implementation; the incident was in achieving fully side-effect-free
test coverage of it, which was subsequently corrected and re-verified.)
