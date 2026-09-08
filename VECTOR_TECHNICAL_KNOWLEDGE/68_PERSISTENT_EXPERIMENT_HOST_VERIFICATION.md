# Task 68 — Persistent Experiment Host Verification

Verification-only. **VECTOR was not started or restarted. Nothing was installed, configured, or
modified.** See §17 for the full disclosure.

---

## 1. Executive Summary

Three existing, already-built hosting mechanisms were found in the repository, none of them
currently active:

1. **NSSM Windows service** (`scripts/install_service.ps1`) — not installed. **Contains a real,
   unfixed bug**: it invokes `run_vector.py --mode loop`, but `run_vector.py`'s argparse defines
   `mode` as a positional argument (`nargs="?"`, default `"loop"`) with no `--mode` flag at all — as
   written, this would make argparse reject the service's own launch command. The project's own
   inline comment claims this exact class of bug was already fixed, but the fix did not make it into
   the actual command line. **This mechanism is not usable as-is.**
2. **Elevated Scheduled Task "VECTOR"** (`install_vector_admin.ps1`) — **already registered on this
   machine, currently `Disabled`.** Runs in the owner's own interactive desktop session (not SYSTEM),
   explicitly engineered this way — its own comments explain that a SYSTEM-session Windows service
   would break VECTOR's mouse/keyboard/screenshot/camera/microphone access, which is exactly why NSSM
   was rejected as the primary path for this specific project. This is the most carefully-engineered,
   most clearly-intended-as-primary mechanism found.
3. **Scheduled Task "VECTOR-Watchdog"** — **also registered, also `Disabled`.** Polls
   `http://127.0.0.1:8000/health` every 5 minutes and restarts a hung/dead process.

**Critical finding directly relevant to Task 68's purpose:** all three existing mechanisms are wired
to `python run_vector.py api --host 0.0.0.0 --port 8000` with `VECTOR_API_RUN_LOOP=1` (the combined
API+loop deployment target) — **none of them reproduce the exact configuration Task 62 actually
launched** (`python run_vector.py loop`, no host/port flags, implicitly `127.0.0.1`-only, no combined
API server). This is a genuine environment-parity gap, not a matter of convenience — different code
path (`VECTOR_API_RUN_LOOP` gate in `core/api/app.py`), different network exposure (`0.0.0.0` binds
to all interfaces vs. the audited `127.0.0.1`), and a runtime configuration Task 60's safety audit
did not specifically scope.

**A separate, unrelated, but directly useful finding:** VECTOR's own file-based logger
(`_configure_file_logging()`, `run_vector.py`) already wrote real, independent, on-disk log files
(`data/logs/vector_loop.log`, `vector_api.log`) throughout the Segment-1 run, and their
`LastWriteTime` (**2026-09-03 02:36:29**) independently corroborates the exact death timestamp
established in Tasks 66-67, entirely apart from the Claude-Code-tracked background task's own stdout
capture. This confirms VECTOR already has session-independent logging regardless of which hosting
mechanism is chosen.

**Recommendation: RESTART ONLY AFTER INFRASTRUCTURE CHANGE**, and specifically **REQUIRES
INFRASTRUCTURE CHANGE (C)** for any of the three existing mechanisms to be used safely — none is
"ready to use" as-is for reproducing the exact experiment configuration. Preferred path: enabling the
existing Scheduled Task "VECTOR" (§12), but only after the owner resolves the `VECTOR_API_RUN_LOOP`/
`0.0.0.0` parity gap against what Task 60 actually audited — a decision this task does not make.

## 2. Current Experiment State

**Segment 1: 2026-09-03 00:53:29 → 02:36:29 IST (~2h03m), externally terminated, NOT completed.**
Per Task 66/67's findings, re-confirmed as still current: PID 48840 does not exist, no VECTOR-related
process is running, no service or scheduled task is currently active for VECTOR, databases remain
intact (integrity not re-verified this task — no new information would result, and this task's scope
is hosting-mechanism verification, not repeated data-integrity checks already performed twice).

## 3. Existing NSSM / Windows Service Evidence

**A. Does the project have an intended NSSM path?** Yes — `scripts/install_service.ps1`, also
referenced in `DEPLOY.md` ("Always-on (Admin PowerShell): `powershell -File scripts/install_service.ps1`"),
`.claude/skills/vector-run-and-operate/SKILL.md`, and `.claude/skills/vector-campaign-ship-to-running/SKILL.md`.

**B. Exact executable/command expected:** `nssm install VECTOR <python.exe> "run_vector.py --mode loop"`
— **this command line is broken** (§1). `run_vector.py` has no `--mode` flag; the correct invocation
per its actual argparse definition would be either no arguments at all (defaults to `loop`) or the
bare positional `loop`.

**C. Working directory:** `AppDirectory` set to the repo root (`$Root`, resolved via
`$PSScriptRoot\..`) — correct and consistent with every other launch method checked.

**D. Environment variables expected:** none explicitly set by this script — it relies on `.env`
being loaded by `run_vector.py` itself (consistent with the project's documented `.env`-loading
convention) and does not set `VECTOR_API_RUN_LOOP` or `VECTOR_ENV` (irrelevant here since this script
targets `loop` mode, not `api` mode, so `VECTOR_API_RUN_LOOP` doesn't apply).

**E. User/account expected:** not explicitly configured (script has no `nssm set ... ObjectName`
call) — NSSM services default to running as `LocalSystem` when no account is specified. **This is a
real concern** — see §9.

**F. stdout/stderr/log paths:** `data\logs\vector-stdout.log` / `vector-stderr.log`, 10MB rotation,
online rotation enabled — sensible and consistent with the project's general logging conventions,
though these paths are distinct from `run_vector.py`'s own internal `_configure_file_logging()`
output (`vector_loop.log`) — running under NSSM would produce **two parallel log streams** for the
same process (NSSM's captured stdout/stderr, and VECTOR's own loguru file sink), not a conflict, but
worth knowing.

**G. Restart/recovery behavior:** `AppRestartDelay 5000` (auto-restart 5s after any exit, no
distinction between crash and graceful stop — see §10), graceful-stop-first design
(`AppStopMethodConsole 1`, i.e. CTRL+C, matching VECTOR's own confirmed-working `KeyboardInterrupt`
handler from Task 62's SIGINT test), `AppKillProcessTree 1`.

**H. Is NSSM currently installed?** Not on PATH (`Get-Command nssm` returns nothing), not in
`C:\Windows\System32\`. **However, `nssm.exe` (331,264 bytes, dated 2026-07-03) already exists at
`data\tools\nssm.exe`** — left over from a prior session's auto-download (the script's own
auto-download logic writes exactly there). It is present and usable without re-downloading, but is
not registered anywhere as a system-wide command.

**I/J. Is a VECTOR-related Windows service currently installed/running?** No — `Get-Service` filtered
for `VECTOR|nssm` by name or display name returns **no results**. No NSSM-based service exists on
this machine.

**K. N/A** — nothing is installed to have a configuration to report.

## 4. Existing Process-Supervision Mechanisms

Beyond NSSM, two further, already-built mechanisms were found:

- **`scripts/install_autostart.ps1`** — a no-admin Startup-folder shortcut (`VECTOR Autostart.lnk` →
  `cmd.exe /c vector_autostart.bat`, minimized). **Not currently installed** (`Get-ChildItem` on the
  Startup folder shows only a pre-existing `Ollama.lnk`; no VECTOR shortcut present). Superseded by
  the Scheduled Task approach below, per `install_vector_admin.ps1`'s own logic (it explicitly moves
  the old Startup shortcut to a backup folder if found, to prevent double-launch — though since the
  shortcut isn't currently present, this cleanup step is currently moot).
- **`scripts/install_vector_admin.ps1`** — registers an **elevated Windows Scheduled Task** named
  `VECTOR`. **Already registered on this machine** (confirmed via `Get-ScheduledTask`), current
  `State = Disabled`. Full XML definition (read-only export) confirms:
  - Trigger: `LogonTrigger` for user `LAPTOP-LHC4B8JG\Arghyadeep`.
  - Principal: `LogonType=InteractiveToken`, `RunLevel=HighestAvailable` — runs as the owner, in the
    owner's interactive desktop session, with an elevated (admin) token — **not** SYSTEM, **not**
    Session 0.
  - `ExecutionTimeLimit=PT0S` (zero = no time limit — critically relevant, since a
    default/unspecified Scheduled Task time limit is commonly 72 hours, which would itself have
    silently ended a 7-day experiment; this was already correctly set to unlimited).
  - `MultipleInstancesPolicy=IgnoreNew` (single-instance enforced at the OS level, not just via the
    batch file's own port-check guard).
  - Action: `cmd.exe /c "scripts\vector_autostart.bat"`, working directory = repo root.
- **`scripts/install_watchdog_task.ps1`** → registers **Scheduled Task "VECTOR-Watchdog"`.**
  **Already registered, `State = Disabled`.** Full XML confirms: `TimeTrigger` repeating every 5
  minutes indefinitely (`Duration=P3650D`, i.e. ~10 years) since 2026-07-23, `LogonType=InteractiveToken`
  (no elevated RunLevel specified), action = hidden `wscript.exe watchdog_check_hidden.vbs` →
  `WATCHDOG_CHECK.bat` → `scripts/vector_watchdog.ps1`.

**`vector_watchdog.ps1`'s actual logic (read in full, read-only):**
- Health check is **specifically HTTP-based**: `GET http://127.0.0.1:8000/health`, plus a
  loop-heartbeat staleness check read from that same response body.
- **This watchdog can only ever detect and act on the `api`-mode process** (the one that binds port
  8000). It has no mechanism to observe a bare `loop`-mode process like the one actually used for
  Segment 1 (PID 48840 never bound any port). **This means: even if this watchdog had been enabled,
  it would not have detected Segment 1's termination and would not have restarted anything relevant
  to it.** This is a load-bearing finding for §10.
- On detected failure, it force-kills whatever holds port 8000 (`Stop-Process -Force` — an
  *ungraceful* kill, unlike NSSM's CTRL+C-first design) and relaunches
  `python run_vector.py api --host 0.0.0.0` with `VECTOR_API_RUN_LOOP=1`/`VECTOR_ENV=production` set
  on the child environment.
- The script's own extensive inline history documents at least two real prior incidents this
  infrastructure was built to address: an ~11-day, ~470-restart-attempt silent crash loop, and a
  4-day-17-hour run where the autonomous loop silently never started due to a missing env var while
  the API itself looked healthy — both are directly relevant cautionary precedent for how easily a
  "looks fine" persistent-host setup can silently diverge from the intended experiment configuration.

## 5. Environment Parity

| Aspect | Task 62's actual launch (`run_vector.py loop`) | NSSM service (as scripted) | Scheduled Task "VECTOR" / Watchdog (`vector_autostart.bat`) |
|---|---|---|---|
| Working directory | Repo root | Repo root — **matches** | Repo root — **matches** |
| Python interpreter | Resolved from the coordinating session's own PATH at launch time | Resolved via `(Get-Command python).Source` at *install* time (baked in, not re-resolved per start) | Resolved at *run* time inside `vector_autostart.bat`/watchdog (bare `python` on PATH, or a fallback search) — **UNKNOWN whether this resolves to the identical interpreter/venv** without directly comparing paths, not verified this task since doing so would require invoking commands whose live side effects were judged not worth it for a verification-only pass — marked **UNKNOWN**, not assumed equal |
| Virtual environment | Whatever the coordinating session's shell had active (not independently re-verified this task) | Same caveat | Same caveat |
| `.env` handling | Loaded by `run_vector.py` itself via `load_dotenv`, unaffected by launch mechanism | **Same** — `.env` loading is internal to the script, mechanism-independent | **Same** |
| Host/port | Not applicable (`loop` mode does not bind a port) | Not applicable (also `loop` mode as scripted) | **DIFFERS** — `api --host 0.0.0.0 --port 8000`, a fundamentally different mode with network exposure Task 62 never used |
| `VECTOR_API_RUN_LOOP` | Not applicable | Not applicable | **Set to `1`** — routes through a different code gate (`core/api/app.py`) than the bare `loop` mode Task 60 audited |
| `VECTOR_ENV` | Not observed to be explicitly set for Segment 1 | Not set | Set to `production` — serves a different HUD build; not evaluated for safety-relevant differences this task (out of scope: this is a UI/deployment distinction, not a permission/action-scope one, based on prior sessions' characterization of `VECTOR_ENV`) |
| User identity | The coordinating session's own Windows user context (Arghyadeep, interactive) | **UNKNOWN — no `ObjectName` set, defaults to `LocalSystem`** (§9) | Owner's own interactive session, elevated — **matches** the human-launch identity, unlike NSSM's default |
| GPU/Ollama/local-model visibility | Available (interactive session) | **At risk** — `LocalSystem`/Session-0 services commonly cannot see a per-user CUDA context or a user-scoped Ollama instance the same way an interactive session can; not independently tested this task, flagged as a real risk given NSSM's own default | Preserved — interactive desktop session, same reasoning `install_vector_admin.ps1`'s own comments give for camera/mic/mouse access applies equally here |
| Camera/mic/screen/mouse-keyboard control | Available and actively used (Task 66 observed real ambient voice + screen_observer activity) | **Would very likely break** — Session 0 has no desktop; this is exactly the failure mode the project's own `install_vector_admin.ps1` comments describe and were written specifically to avoid | Preserved by design |
| Network exposure | `127.0.0.1`-only (implicit, `loop` mode binds nothing) | Same (as scripted, still `loop` mode) | **`0.0.0.0`** — LAN-reachable, a materially larger attack surface than what Task 60 red-teamed |

**Overall parity assessment: NSSM (as currently scripted) preserves *closer* runtime-mode parity
(still `loop` mode) but has an unresolved account-identity risk and a broken command line. The
Scheduled Task path has excellent identity/session parity (the single best-solved aspect of any
candidate) but a real, unresolved *mode* parity gap (`api`+`VECTOR_API_RUN_LOOP=1`+`0.0.0.0` is not
the same audited configuration).** Neither candidate is a clean drop-in replacement for exactly
reproducing Segment 1's configuration without the owner making an explicit choice and, likely, a
small script edit (marked here as a finding, not implemented).

## 6. Candidate Hosting Mechanisms

### 6.1 NSSM / Windows Service
- **Independence from Claude session:** Yes — a true, separate Windows service, no dependency on any
  terminal/session at all.
- **Persistence:** Yes, survives logoff (services run independent of any logged-on session).
- **Logging:** Yes, dedicated stdout/stderr files (§3F) plus VECTOR's own internal file logger.
- **Stop control:** `nssm stop VECTOR` / `Stop-Service VECTOR` — clear, owner-controllable.
- **Restart behavior:** Auto-restart on ANY exit after 5s, with no distinction between a graceful
  stop and a crash unless the stop was specifically issued via the service-stop path (§10).
- **Environment parity:** Mode-parity good (`loop`), but account-identity risk (§9) and GPU/desktop
  access risk are real concerns; command line is currently broken (§1/§3B).
- **Safety implications:** See §9 — potential `LocalSystem` execution is the single most important
  concern of any candidate.
- **Experiment validity:** Good, once the command-line bug is fixed and the account question is
  resolved — closest to a "just run the same thing forever" model.
- **Setup complexity:** Requires an elevated PowerShell session, `nssm.exe` already present locally
  (no download needed), and fixing the one-line command bug.
- **Known unknowns:** whether the account/GPU/desktop-access risk is real on this specific machine
  (untested), whether fixing the `--mode` bug is the only change needed or whether further testing
  would surface more.

### 6.2 Persistent Interactive Terminal
- **Independence from Claude session:** Yes, provided it is a terminal the owner opens and keeps
  open themselves, entirely separate from any Claude Code-tracked shell or background task.
- **Persistence:** Only as long as the owner keeps that terminal open and the machine doesn't
  sleep/log off — genuinely fragile to the same class of event (session/terminal lifecycle) that
  ended Segment 1, though the *specific* mechanism (Claude Code's background-task tracking) would no
  longer be in the loop at all.
- **Logging:** Yes — same internal file logger, plus whatever the terminal itself captures/scrolls.
- **Stop control:** A literal Ctrl+C in that terminal — confirmed working cleanly in Task 62.
- **Restart behavior:** None automatic — a crash or accidental close simply ends the process, with no
  auto-recovery (arguably a feature for experiment-integrity purposes: no silent new segment).
- **Environment parity:** **Excellent** — this is exactly the same launch method already used and
  validated for Segment 1 (a real terminal, real interactive session, `python run_vector.py loop`,
  no flags) — the only difference from Segment 1 is *which* terminal/session hosts it.
- **Safety implications:** None beyond what's already audited — identical runtime configuration.
- **Experiment validity:** Cleanest of all candidates specifically because it changes nothing about
  the audited configuration — only removes this coordinating session as the host.
- **Setup complexity:** Trivial — open a terminal, run the command, leave it open.
- **Known unknowns:** whether the owner's own terminal/session is itself immune to the kind of
  event that killed Segment 1 (a plain interactive terminal is a different failure domain than a
  Claude-Code-tracked background task, but "the machine sleeps/locks" is a separate risk this task
  did not investigate for this specific candidate — the project's own commit history mentions
  standby/lock-sound handling, implying sleep/lock events do occur on this machine periodically).

### 6.3 Other Existing Mechanisms
- **Startup-folder shortcut (§4):** Simple, no-admin, but only fires at logon — not useful for
  resuming an interrupted run without a logon event, and not currently installed.
- **Scheduled Task "VECTOR" (elevated, interactive):** covered in depth above (§4-5) — the
  best-engineered existing mechanism, but with the unresolved `api`/`0.0.0.0`/`VECTOR_API_RUN_LOOP`
  mode-parity gap against what was actually audited and launched.
- **Scheduled Task "VECTOR-Watchdog":** not a primary hosting mechanism by itself (it supervises the
  `api`-mode process specifically) — relevant to §9-10, not a standalone candidate for hosting a
  `loop`-mode experiment.

## 7. Process-Lifecycle Independence

Of the candidates evaluated, **NSSM service** and **Scheduled Task "VECTOR"** both achieve full
independence from Claude Code's shell/background-task/tool-execution-timeout lifecycle — the desired
architecture (Claude Code observes/controls only; an independent supervisor hosts VECTOR) is achieved
by either. **Persistent interactive terminal** achieves independence specifically from the
*background-task* mechanism that failed, but remains coupled to *some* terminal/session surviving —
a narrower, but real, improvement over Tasks 62-66's actual setup, at lower engineering cost and with
zero mode-parity risk.

## 8. Logging and Observability

Independently of hosting mechanism, VECTOR already logs to disk via its own file sink
(`_configure_file_logging()`, confirmed this task: `data/logs/vector_loop.log`, 10MB rotation, 5
files retained) — this persists regardless of which hosting mechanism is chosen and already proved
its value this task (independently corroborating the Segment-1 death timestamp, §1). `gateway_audit`
and `inference_calls` (SQLite) are similarly mechanism-independent. NSSM adds a second, redundant
stdout/stderr capture; the Scheduled Task path relies on `vector_autostart.bat`'s own log file
(`%USERPROFILE%\.vector_ca\logs\...` per its own script content) — **a different log location than
`loop` mode's `data\logs\vector_loop.log`**, another manifestation of the mode-parity gap, since that
script targets `api` mode specifically. **None of the three candidates would, by itself, distinguish
a future "VECTOR crashed" from "supervisor restarted it" from "OS killed it" any better than manual
log inspection already does** — NSSM's and the Watchdog's own action logs (`watchdog.log`,
`vector-stderr.log`) would add one more independent data point each, which is a genuine, if modest,
improvement over Segment 1's sole reliance on the Claude-Code-tracked capture (which itself proved to
be the thing that failed).

## 9. Security / Permission Implications

- **PermissionGateway, permission tiers, credentials, MCP availability, autonomous side-effect
  scope:** none of the three candidate mechanisms touch any of this — they are pure process-launch
  wrappers around the identical `run_vector.py` entry point; nothing about `core/loop/permission_gateway.py`
  or `core/config.py`'s tier classification changes based on how the process was started. **Confirmed
  by inspection this task; no code path in any of the three launch scripts references permission
  configuration at all.**
- **Elevated privileges — real, flagged concern:** the Scheduled Task "VECTOR" runs with
  `RunLevel=HighestAvailable` (admin token) in the owner's own session — this is *more* privileged
  than Segment 1's actual launch (an ordinary, non-elevated interactive terminal, so far as this
  investigation can determine — not independently re-verified this task, but nothing in Tasks 60-66
  indicates an elevated launch was used or required). **Running VECTOR with an admin token when it
  did not need one for Segment 1 is a real, if modest, privilege-escalation concern worth the owner's
  explicit attention before enabling this task** — VECTOR's own permission model
  (GREEN/YELLOW/RED tiers) still applies identically regardless of OS-level privilege, but an admin
  token widens what a bug or a future RED-tier-adjacent bypass *could* reach at the OS level, which is
  exactly the kind of blast-radius consideration Task 60's whole audit was concerned with.
- **NSSM's default account is a real, unresolved risk:** as scripted, the service would run as
  `LocalSystem` unless the owner adds an explicit `ObjectName` — `LocalSystem` is *more* privileged
  than a normal user account and, per the project's own `install_vector_admin.ps1` reasoning, would
  also very likely break camera/mic/screen/mouse access entirely (Session-0 has no desktop). This is
  flagged as the single most important unresolved item for the NSSM path specifically.
- **Network exposure:** the Scheduled Task/autostart path's `0.0.0.0` binding is a materially larger
  attack surface than the `127.0.0.1`-only configuration Task 60 red-teamed — not modified or
  disproven safe by this task; flagged as requiring the owner's explicit decision, not assumed
  acceptable.

## 10. Automatic Restart / Experiment Integrity

- **NSSM (as scripted):** `AppRestartDelay 5000` restarts on *any* process exit, including a clean,
  intentional stop that wasn't issued through `nssm stop` — **this could silently start a new
  segment** if the owner or a future task ever stops the process by any means other than the
  service's own stop command (e.g., a direct `taskkill`, or exactly the kind of external termination
  that ended Segment 1, if that mechanism is still capable of reaching a service-hosted process — not
  established either way this task). This is a genuine experiment-integrity risk requiring explicit
  owner awareness, not merely a robustness feature.
- **Scheduled Task "VECTOR-Watchdog":** currently `Disabled`; even if enabled, it is **structurally
  incapable of observing or restarting a bare `loop`-mode process** (§4) — so it poses **no** risk of
  silently creating a second experiment segment for a `loop`-mode run specifically, only for an
  `api`-mode one. If the owner ever switches the experiment to `api`+`VECTOR_API_RUN_LOOP=1` mode
  *and* enables this watchdog, then yes, an unattended restart could create an undeclared new segment
  — flagged for that specific combination only.
- **Persistent interactive terminal:** no automatic restart at all — the safest option specifically
  from an experiment-segment-integrity perspective, at the cost of no automatic recovery from any
  failure.

## 11. Comparison Matrix

| | NSSM Service | Scheduled Task "VECTOR" | Persistent Terminal |
|---|---|---|---|
| Independent of Claude session | Yes | Yes | Yes (of the specific failed mechanism) |
| Currently installed | No | Yes (Disabled) | N/A |
| Command line correct as-is | **No — broken** | Yes | Yes (owner types it) |
| Runtime-mode parity with Segment 1 | Good (`loop`) | **Poor** (`api`+`VECTOR_API_RUN_LOOP=1`+`0.0.0.0`) | **Exact** |
| Account/privilege parity | **Unresolved (LocalSystem risk)** | Elevated (more than Segment 1 had) | Exact |
| Auto-restart | Yes (any exit) | N/A directly (Watchdog is separate, doesn't apply to `loop` mode) | No |
| Experiment-integrity risk from auto-restart | Real, moderate | None for `loop` mode specifically | None |
| Logging | Own file logger + NSSM capture | Own file logger + `vector_autostart.log` (different path/mode) | Own file logger only |
| Setup effort remaining | Fix one-line bug, decide account, install | Just enable (already registered) | Zero — just open a terminal |
| Owner manual stop | `nssm stop` / Services.msc | `Stop-ScheduledTask` / Task Scheduler UI | Ctrl+C |

## 12. Preferred Mechanism

**Persistent interactive terminal, owned and kept open by the owner, running the exact command
already validated in Task 62 (`python run_vector.py loop`).**

Reasoning: of every candidate, this is the *only* one requiring **zero configuration changes and
zero unresolved parity questions** — it is not a new mechanism at all, but simply "the same thing
Segment 1 did, hosted by a terminal the owner controls directly instead of one tracked by this
coordinating session's background-task system." It carries no elevated-privilege risk, no
account-identity risk, no mode-parity gap, and no silent-auto-restart risk. Its only weakness —
fragility if the owner's terminal/session itself is closed, or the machine sleeps/locks — is a
different, and arguably smaller and more owner-visible, failure domain than the one that actually
caused Segment 1's termination, and it is a failure mode the owner can directly observe and control
(the terminal is right there, versus a coordinating AI session's internal lifecycle, which is
opaque to everyone including this task, per Task 67's own findings).

The Scheduled Task path is the better *long-term* answer once the owner deliberately resolves the
`api`/`0.0.0.0`/`VECTOR_API_RUN_LOOP` parity question and the elevated-privilege question — but doing
so is a real decision with real trade-offs (network exposure, admin token) that this task is
explicitly not positioned to make on the owner's behalf.

## 13. Known Unknowns

- Whether NSSM/service-hosted VECTOR would actually lose camera/mic/GPU/Ollama access on this
  specific machine (reasoned from the project's own documented rationale, not independently tested).
- Whether the coordinating-session termination mechanism that ended Segment 1 (Task 67) is even
  capable of affecting an NSSM-service-hosted or Scheduled-Task-hosted process at all, or whether it
  is specific to Claude-Code-tracked background bash tasks — **not established**, and directly
  relevant to how much confidence to place in any of these alternatives actually solving the problem.
- Whether the Python interpreter/virtualenv resolved by `vector_autostart.bat`/the watchdog at run
  time is identical to the one used in Segment 1's actual launch — not directly compared.
- The full safety implications of `VECTOR_ENV=production`'s HUD-build difference, beyond the network
  and loop-mode distinctions already covered.

## 14. Required Steps Before Restart

- Owner explicitly selects a hosting mechanism (this task provides evidence and a recommendation,
  not a decision).
- If NSSM is chosen: fix the `--mode loop` → `loop` command-line bug, and explicitly decide/set the
  service account (avoid the `LocalSystem` default).
- If the Scheduled Task is chosen: resolve the mode-parity gap (decide whether `api`+
  `VECTOR_API_RUN_LOOP=1`+`0.0.0.0` is an acceptable, deliberately-chosen configuration for the
  experiment, or adjust the task/script to launch bare `loop` mode instead — a decision and possible
  script change this task does not make).
- Whichever mechanism is chosen, capture a fresh Day-0 watermark exactly as Task 62 did, and treat
  the next run as an explicitly new, separately-declared experiment segment (§16), not a silent
  continuation.
- Verify the chosen mechanism's manual-stop path actually works before relying on it for a
  multi-hour/day run (an analogous verification to Task 62's own SIGINT test).

## 15. Restart Gate

**VECTOR was not restarted by this task.** No process was started, no service installed, no
scheduled task enabled, no script executed with side effects.

## 16. Experiment Segment Semantics

Per the task's explicit instruction, Segment 1 is recorded here formally, not silently treated as a
completed run:

> **Experiment Segment 1 — 2026-09-03 00:53:29 → 02:36:29 IST (~2h03m). Externally terminated
> (Task 66/67). Not a completion of the 7-day protocol.**

Any future restart, under any hosting mechanism, should be declared as **Segment 2** (or a formally
amended protocol), with its own fresh Day-0 watermark, rather than assumed to continue Segment 1's
clock or conclusions.

## 17. Experiment Integrity Statement

- **VECTOR started by this task?** No.
- **VECTOR restarted by this task?** No.
- **API/HUD started/restarted?** No.
- **Any process killed?** No.
- **Production source modified?** No.
- **Configuration modified?** No.
- **Database modified?** No.
- **Experiment state modified?** No.
- **Environment variables modified?** No.
- **Services modified?** No — both existing Scheduled Tasks were inspected via `Get-ScheduledTask`/
  `Export-ScheduledTask` only (read-only serialization), never enabled, disabled, or altered.
- **NSSM installed?** No — the pre-existing `data\tools\nssm.exe` binary was found and its file
  metadata inspected (`Get-Item`); it was never executed.
- **Synthetic stimulus introduced?** No.
- **VECTOR behavior steered?** No — VECTOR is not running.
- **Git HEAD before:** `5964a331678ac648c8289f4c38fd0e5430e1ee9d`. **Git HEAD after:** unchanged (no
  write operation of any kind occurred capable of altering it).
- **Working-tree state before:** 124 modified/untracked paths (unchanged from every prior task in
  this series). **Working-tree state after:** unchanged, plus this one new report file.
- **File created:** exactly one —
  `VECTOR_TECHNICAL_KNOWLEDGE/68_PERSISTENT_EXPERIMENT_HOST_VERIFICATION.md` (this document).
