#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Install VECTOR as a Windows service using NSSM so it restarts automatically on crash.

.DESCRIPTION
    Requires NSSM (Non-Sucking Service Manager): https://nssm.cc/download
    Download nssm.exe and place it in C:\Windows\System32\ or update $NSSMPath below.

.USAGE
    # Run once from an elevated PowerShell prompt:
    powershell -ExecutionPolicy Bypass -File scripts\install_service.ps1
#>

$ServiceName = "VECTOR"
$Root        = (Resolve-Path "$PSScriptRoot\..").Path
$Python      = (Get-Command python).Source
$Script      = Join-Path $Root "run_vector.py"
$LogDir      = Join-Path $Root "data\logs"
$NSSMPath    = "nssm"   # assumes nssm.exe is on PATH; set full path if not

# Ensure log directory exists
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

# Remove existing service if present
$existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Stopping and removing existing VECTOR service..."
    & $NSSMPath stop $ServiceName
    & $NSSMPath remove $ServiceName confirm
}

Write-Host "Installing VECTOR as Windows service..."
& $NSSMPath install $ServiceName $Python "$Script --mode autonomous"
& $NSSMPath set $ServiceName AppDirectory $Root
& $NSSMPath set $ServiceName AppStdout (Join-Path $LogDir "vector-stdout.log")
& $NSSMPath set $ServiceName AppStderr (Join-Path $LogDir "vector-stderr.log")
& $NSSMPath set $ServiceName AppRotateFiles 1
& $NSSMPath set $ServiceName AppRotateBytes 10485760   # 10 MB per log file
& $NSSMPath set $ServiceName AppRotateOnline 1
& $NSSMPath set $ServiceName Start SERVICE_AUTO_START
& $NSSMPath set $ServiceName AppRestartDelay 5000      # restart 5s after crash

# Graceful shutdown: send CTRL+C (Python handles as KeyboardInterrupt → asyncio drain)
# instead of TerminateProcess (which kills Python mid-loop without flushing memory/logs)
& $NSSMPath set $ServiceName AppStopMethodConsole 1    # CTRL+C first
& $NSSMPath set $ServiceName AppStopMethodWindow  0    # no WM_CLOSE
& $NSSMPath set $ServiceName AppStopMethodThreads 0    # no thread inject
& $NSSMPath set $ServiceName AppKillProcessTree   1    # kill child procs on stop

Write-Host "Starting VECTOR service..."
& $NSSMPath start $ServiceName

$svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($svc -and $svc.Status -eq "Running") {
    Write-Host "VECTOR service is RUNNING. Verify with: Get-Service VECTOR"
} else {
    Write-Warning "Service may not have started. Check: $LogDir\vector-stderr.log"
}
