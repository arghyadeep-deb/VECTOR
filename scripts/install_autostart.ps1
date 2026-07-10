<#
  Installs VECTOR autostart via the user Startup folder — the no-admin, no-NSSM,
  no-Scheduled-Task method. A shortcut in Startup runs VECTOR's launcher at every
  logon (minimized). The launcher itself skips if VECTOR is already running.

  Run it yourself (persistence change — Claude Code can't self-install this):
    powershell -ExecutionPolicy Bypass -File "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\scripts\install_autostart.ps1"

  To remove later: delete the shortcut it reports below.
#>
$bat = "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\scripts\vector_autostart.bat"
if (-not (Test-Path $bat)) { Write-Error "launcher missing: $bat"; exit 1 }

$startup = [Environment]::GetFolderPath("Startup")
$lnkPath = Join-Path $startup "VECTOR Autostart.lnk"

$sh = New-Object -ComObject WScript.Shell
$lnk = $sh.CreateShortcut($lnkPath)
$lnk.TargetPath  = "cmd.exe"
$lnk.Arguments   = "/c `"$bat`""
$lnk.WindowStyle = 7            # 7 = minimized
$lnk.WorkingDirectory = Split-Path $bat
$lnk.Description  = "Starts VECTOR autonomous loop at logon"
$lnk.Save()

if (Test-Path $lnkPath) {
    Write-Host "Installed: $lnkPath"
    Write-Host "VECTOR will auto-start (minimized) at every logon. Current running instance untouched."
} else {
    Write-Error "Failed to create the Startup shortcut."
}
