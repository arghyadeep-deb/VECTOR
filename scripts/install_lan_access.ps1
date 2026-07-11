<#
  Opens Windows Firewall for VECTOR's LAN API (TCP 8000) so the daily phone (and
  any device on the same Wi-Fi) can reach the VECTOR HUD + API.

  Needs Admin (firewall changes require elevation). Run:
    Right-click PowerShell -> Run as administrator, then:
    powershell -ExecutionPolicy Bypass -File "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\scripts\install_lan_access.ps1"

  To remove later:
    Remove-NetFirewallRule -DisplayName "VECTOR API 8000"
#>
$existing = Get-NetFirewallRule -DisplayName "VECTOR API 8000" -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Firewall rule already exists."
} else {
    New-NetFirewallRule -DisplayName "VECTOR API 8000" -Direction Inbound `
        -LocalPort 8000 -Protocol TCP -Action Allow -Profile Any | Out-Null
    Write-Host "Firewall opened for TCP 8000 (all profiles)."
}

$ip = (Get-NetIPAddress -AddressFamily IPv4 |
       Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.*' } |
       Select-Object -First 1).IPAddress

# Read the real API key from .env so we can print the complete, ready-to-use URL
# locally (it prints on YOUR screen only — do not paste it into any chat).
$envPath = "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\.env"
$key = ""
if (Test-Path $envPath) {
    $line = Get-Content $envPath | Where-Object { $_ -like "VECTOR_API_KEY=*" } | Select-Object -First 1
    if ($line) { $key = $line.Substring($line.IndexOf('=') + 1).Trim() }
}
Write-Host ""
Write-Host "==================================================================="
Write-Host "VECTOR is reachable from any device on your Wi-Fi at:"
if ($key) {
    Write-Host ("  http://{0}:8000/hud/?key={1}" -f $ip, $key)
} else {
    Write-Host ("  http://{0}:8000/hud/?key=YOUR_VECTOR_API_KEY" -f $ip)
}
Write-Host "Open that in your phone's browser (same Wi-Fi). Bookmark it."
Write-Host "Note: your IP ($ip) can change when you switch networks — re-run to see the new one."
Write-Host "==================================================================="
