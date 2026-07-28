# Registers/re-registers the VECTOR-Watchdog scheduled task with explicit
# battery-safe settings (AllowStartIfOnBatteries, DontStopIfGoingOnBatteries)
# — schtasks.exe's CLI defaults stop the task on battery, which would
# silently defeat it on a laptop. Run once via INSTALL_WATCHDOG2.bat.

$base = "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase"

Unregister-ScheduledTask -TaskName "VECTOR-Watchdog" -Confirm:$false -ErrorAction SilentlyContinue

$action = New-ScheduledTaskAction -Execute (Join-Path $base "WATCHDOG_CHECK.bat")
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 3)

Register-ScheduledTask -TaskName "VECTOR-Watchdog" -Action $action -Trigger $trigger -Settings $settings `
    -Description "Restarts VECTOR API if hung or dead. Added 2026-07-23 (JARVIS-parity robustness pass)." | Out-Null

Write-Output "Registered. Details:"
Get-ScheduledTask -TaskName "VECTOR-Watchdog" | Get-ScheduledTaskInfo | Format-List
Get-ScheduledTask -TaskName "VECTOR-Watchdog" | Select-Object TaskName, State | Format-List
