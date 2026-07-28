# Register VECTOR as an ELEVATED, single-instance, auto-start task.
#
# Why a Scheduled Task and not a Windows Service (NSSM):
#   A service runs as SYSTEM in session 0 — no desktop. That would kill exactly
#   the things VECTOR needs: mouse/keyboard control (pyautogui), screenshots,
#   camera (face ID) and microphone (wake word). This task runs *as the owner,
#   in the owner's interactive session, with the elevated token* — full admin
#   AND full desktop access, with no UAC prompt on every launch.
#
# Owner rules honoured:
#   - ONE instance only: MultipleInstances=IgnoreNew + vector_autostart.bat's
#     own "already running" guard.
#   - ONE entry point: the desktop icon triggers this task (see vector_open.bat).
#
# Run ONCE, elevated. Re-run safely to update (uses -Force).

$ErrorActionPreference = 'Stop'

# The elevated window closes the instant this throws, so log everything to disk.
$Log = 'C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\vector_admin_install.log'
try { Start-Transcript -Path $Log -Force | Out-Null } catch {}

$CodeDir  = 'C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase'
$Bat      = Join-Path $CodeDir 'scripts\vector_autostart.bat'
$TaskName = 'VECTOR'
$Me       = "$env:USERDOMAIN\$env:USERNAME"

try {
    Write-Output "user      : $Me"
    Write-Output "code dir  : $CodeDir"
    if (-not (Test-Path $Bat)) { throw "autostart bat not found: $Bat" }
    $IsAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
               ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    Write-Output "elevated  : $IsAdmin"
    if (-not $IsAdmin) { throw 'Not elevated — right-click > Run as administrator.' }

    $Action    = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument "/c `"$Bat`"" -WorkingDirectory $CodeDir
    $Trigger   = New-ScheduledTaskTrigger -AtLogOn -User $Me
    # Interactive = keeps the desktop session (mouse/screen/camera/mic).
    # Highest     = elevated / admin token.
    $Principal = New-ScheduledTaskPrincipal -UserId $Me -LogonType Interactive -RunLevel Highest
    # NOTE: no -RestartCount/-RestartInterval — those are only valid together with
    # certain trigger types and make Register-ScheduledTask throw on AtLogOn.
    $Settings  = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit ([TimeSpan]::Zero) `
        -MultipleInstances IgnoreNew `
        -StartWhenAvailable

    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger `
        -Principal $Principal -Settings $Settings -Force `
        -Description 'VECTOR — elevated single-instance brain+API. Started at logon and by the desktop icon.' | Out-Null
    Write-Output "OK: registered scheduled task '$TaskName' (elevated, interactive, single-instance)"

    # The task now owns logon-start — drop the old Startup shortcut so we can never
    # get two VECTORs racing at login.
    $OldLnk = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Startup\VECTOR Autostart.lnk'
    if (Test-Path $OldLnk) {
        $Backup = 'C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\_disabled_startup_backup'
        New-Item -ItemType Directory -Force -Path $Backup | Out-Null
        Move-Item $OldLnk (Join-Path $Backup 'VECTOR Autostart.lnk') -Force
        Write-Output 'OK: moved old Startup shortcut to backup (task handles logon now)'
    } else {
        Write-Output 'OK: no old Startup shortcut to remove'
    }
    Write-Output 'DONE — VECTOR will start elevated at logon and via the desktop icon.'
}
catch {
    Write-Output "FAILED: $($_.Exception.Message)"
    Write-Output $_.ScriptStackTrace
}
finally {
    try { Stop-Transcript | Out-Null } catch {}
}
