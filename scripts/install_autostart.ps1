<#
  Installs the "VECTOR Autostart" scheduled task so VECTOR's autonomous loop starts
  automatically at every logon and restarts on crash. NO admin / NO NSSM needed —
  runs in your own user context.

  Run it yourself (persistence change — Claude Code can't self-install this):
    powershell -ExecutionPolicy Bypass -File "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\scripts\install_autostart.ps1"

  To remove later:
    Unregister-ScheduledTask -TaskName "VECTOR Autostart" -Confirm:$false
#>
$bat = "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\scripts\vector_autostart.bat"
if (-not (Test-Path $bat)) { Write-Error "launcher missing: $bat"; exit 1 }

$action   = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$bat`""
$trigger  = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
              -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 2) `
              -ExecutionTimeLimit ([TimeSpan]::Zero)   # no time limit — it runs forever

Register-ScheduledTask -TaskName "VECTOR Autostart" -Action $action -Trigger $trigger `
    -Settings $settings -Description "Starts VECTOR autonomous loop at logon" -Force | Out-Null

Write-Host "Installed. State:" (Get-ScheduledTask -TaskName "VECTOR Autostart").State
Write-Host "VECTOR will now auto-start at every logon. It also keeps running now (current process untouched)."
