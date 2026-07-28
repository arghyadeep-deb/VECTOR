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

# ── Launch fresh, detached, hidden, output captured to its own log ────────
$startLog = Join-Path $base "watchdog_restart_stdout.log"
Start-Process -FilePath "python" -ArgumentList "run_vector.py api --host 0.0.0.0" `
    -WorkingDirectory $base -WindowStyle Hidden `
    -RedirectStandardOutput $startLog -RedirectStandardError $startLog
Pop-Location

Get-Date -Format "yyyy-MM-dd HH:mm:ss" | Set-Content -Path $graceFile
Write-Log "Restart launched (detached, hidden, python run_vector.py api --host 0.0.0.0)."
