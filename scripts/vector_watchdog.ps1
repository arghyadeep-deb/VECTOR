# VECTOR watchdog — 2026-07-23 (JARVIS-parity robustness pass, task #95)
#
# Detects a hung or dead backend and restarts it automatically. This closes
# the exact gap found earlier this session: the API process was silently
# hung for ~24 hours (port 8000 still bound, /health timing out, log
# stalled since 2026-07-22 03:58) with nobody noticing until the next work
# session. Designed to run unattended on a schedule via Windows Task
# Scheduler (see INSTALL_WATCHDOG.bat) — not meant to be run interactively,
# though it's safe to.
#
# Logic: check port 8000 has a listener AND /health responds 200 within
# 10s. If either fails, kill whatever's on port 8000 and start fresh,
# detached and hidden (no visible console window popping up every 5
# minutes). A syntax check runs before every restart — if the codebase is
# mid-edit/broken, this will NOT loop-crash it every 5 minutes; it logs and
# bails so a human sees why, same principle as RESTART_API_ONLY.bat's own
# syntax-check-first step. A grace-period marker file prevents the watchdog
# from killing a restart it just triggered before that restart has finished
# booting (observed boot time ~20-40s; 3 minutes of headroom).

$ErrorActionPreference = "SilentlyContinue"
$base = "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase"
$log = Join-Path $base "watchdog.log"
$graceFile = Join-Path $base "watchdog_last_restart.marker"

function Write-Log($msg) {
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $log -Value "$stamp | $msg"
}

# ── Health check ────────────────────────────────────────────────────────
$listener = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue

$healthy = $false
if ($listener) {
    try {
        # 2026-08-04: bumped 10s -> 45s. Discovered live: with the redirect-
        # bug restart loop fixed (see commit e517f1f34), a genuinely healthy
        # process running a real eval (65 sequential LLM-backed /command
        # calls) got its /health check starved past 10s and was killed
        # mid-run as a false positive ("UNHEALTHY... Killed PID 14320" at
        # 03:16:26, ~5 min into a real eval). Whether that's expected event-
        # loop contention under load or a blocking-call bug elsewhere in the
        # request path is a separate, not-yet-investigated question -- this
        # change only stops the watchdog from being the thing that kills a
        # busy-but-fine process. If /health still doesn't answer within 45s,
        # it's a genuine hang, not just load, and killing it is still right.
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -TimeoutSec 45 -UseBasicParsing
        if ($resp.StatusCode -eq 200) { $healthy = $true }
    } catch {
        $healthy = $false
    }
}

if ($healthy) {
    # Quiet on success — don't spam the log every 5 minutes when things are fine.
    exit 0
}

# ── Grace period: don't kill a restart that's still booting ───────────────
if (Test-Path $graceFile) {
    $lastRestart = Get-Content $graceFile -Raw | ForEach-Object { [datetime]::Parse($_.Trim()) }
    $elapsed = (Get-Date) - $lastRestart
    if ($elapsed.TotalMinutes -lt 3) {
        Write-Log "UNHEALTHY but restarted $([math]::Round($elapsed.TotalSeconds))s ago -- still within 3min boot grace period, not restarting again yet."
        exit 0
    }
}

if ($listener) {
    Write-Log "UNHEALTHY: port 8000 bound (pid(s): $($listener.OwningProcess -join ',')) but /health did not return 200 within 10s -- likely hung. Restarting."
} else {
    Write-Log "DOWN: nothing listening on port 8000. Starting."
}

# ── Kill whatever's on port 8000 ───────────────────────────────────────────
foreach ($conn in $listener) {
    try {
        Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
        Write-Log "Killed PID $($conn.OwningProcess)"
    } catch {}
}
Start-Sleep -Seconds 3

# ── Syntax check before restarting (same file set as RESTART_API_ONLY.bat) ─
Push-Location $base
$syntaxOut = & python -m py_compile core\avatar\avatar_voice.py core\city\governor.py core\api\routers\commands.py core\api_manager.py core\city\prompt_agent.py 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Log "SYNTAX CHECK FAILED -- NOT restarting. Needs a human. $syntaxOut"
    Pop-Location
    exit 1
}

# ── Resolve a real python.exe path so PATH resolution can't silently fail
#    when this script runs under Task Scheduler's process-creation context
#    (which does not always match an interactively-launched shell's PATH,
#    e.g. App Execution Aliases / per-session PATH caching). Falls back to
#    bare "python" only if nothing better can be found.
$pythonExe = $null
$pyCmd = Get-Command python -ErrorAction SilentlyContinue
if ($pyCmd) { $pythonExe = $pyCmd.Source }
if (-not $pythonExe) {
    $candidates = Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe" -ErrorAction SilentlyContinue
    if ($candidates) { $pythonExe = ($candidates | Sort-Object FullName -Descending | Select-Object -First 1).FullName }
}
if (-not $pythonExe) { $pythonExe = "python" }

# ── Launch fresh, detached, hidden, output captured to its own log ────────
# Use -PassThru + -ErrorAction Stop + try/catch so a launch failure is LOUD
# in watchdog.log instead of being silently swallowed by the script-wide
# $ErrorActionPreference = SilentlyContinue above (this exact silent-failure
# shape is what let an 11-day, ~470-restart-attempt crash loop go unnoticed:
# every attempt logged "Restart launched" whether or not a process actually
# started, and watchdog_restart_stdout.log never once got created).
$startOutLog = Join-Path $base "watchdog_restart_stdout.log"
$startErrLog = Join-Path $base "watchdog_restart_stderr.log"
try {
    # 2026-08-04 (audit): the watchdog relaunched VECTOR WITHOUT the two env
    # vars scripts/vector_autostart.bat sets, so every watchdog-driven restart
    # silently produced an API-only process with NO autonomous brain:
    #   VECTOR_API_RUN_LOOP=1 -> core/api/app.py:192 gates the entire
    #     autonomous loop (observe/think/act/reflect) on this. Unset = the
    #     loop never starts and /health/system reports
    #     loop: {"status": "not_started"} while everything else looks healthy.
    #   VECTOR_ENV=production -> serves the lean prod HUD instead of the dev one.
    # Measured impact before this fix: over a 4d17h run the loop's last log
    # entry was 2h in (the boot that came from autostart.bat), the permission
    # gateway logged exactly ONE line in the whole window (its own init — zero
    # actions ever executed), and there were zero proactive owner
    # notifications. VECTOR looked fine (42k HTTP requests served, 2.5k
    # governor dispatches) while the JARVIS half was simply absent.
    # Start-Process inherits the parent environment, so setting them here is
    # sufficient and keeps parity with autostart.bat.
    $env:VECTOR_API_RUN_LOOP = "1"
    $env:VECTOR_ENV = "production"
    $proc = Start-Process -FilePath $pythonExe -ArgumentList "run_vector.py api --host 0.0.0.0" `
        -WorkingDirectory $base -WindowStyle Hidden `
        -RedirectStandardOutput $startOutLog -RedirectStandardError $startErrLog `
        -PassThru -ErrorAction Stop
    Get-Date -Format "yyyy-MM-dd HH:mm:ss" | Set-Content -Path $graceFile
    Write-Log "Restart launched using '$pythonExe' (PID $($proc.Id), detached, hidden, python run_vector.py api --host 0.0.0.0)."
} catch {
    Write-Log "RESTART LAUNCH FAILED using '$pythonExe': $($_.Exception.Message) -- NOT updating grace marker, will retry next cycle."
}
Pop-Location
