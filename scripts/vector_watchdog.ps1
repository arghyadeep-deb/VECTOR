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
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -TimeoutSec 10 -UseBasicParsing
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
