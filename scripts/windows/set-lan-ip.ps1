# Switch Pratyaksh to a new LAN IP (another Wi-Fi, the venue hotspot...).
#   powershell -ExecutionPolicy Bypass -File scripts\windows\set-lan-ip.ps1             (detects the Wi-Fi IP)
#   powershell -ExecutionPolicy Bypass -File scripts\windows\set-lan-ip.ps1 -Ip 10.0.0.5
# Rewrites LAN_IP, LIVEKIT_PUBLIC_URL and CORS_ORIGINS in .env and VITE_API_URL in web\.env (UTF-8, no BOM).
# Then restart LiveKit, the API and the web app (stop.ps1, start.ps1) and reopen the Bank App pairing link.
param([string]$Ip)
$ErrorActionPreference = 'Stop'
$R = (Resolve-Path "$PSScriptRoot\..\..").Path
if (-not $Ip) {
    $Ip = (Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias 'Wi-Fi' |
           Where-Object { $_.IPAddress -notlike '169.254.*' } | Select-Object -First 1).IPAddress
    if (-not $Ip) { throw 'No Wi-Fi IPv4 address found; pass -Ip.' }
}
$utf8 = New-Object System.Text.UTF8Encoding $false
$envPath = Join-Path $R '.env'
$text = [IO.File]::ReadAllText($envPath)
$old = [regex]::Match($text, '(?m)^LAN_IP=([^\r\n]*)').Groups[1].Value.Trim()
if (-not $old) { throw "LAN_IP not found in $envPath" }
if ($old -eq $Ip) { "LAN_IP is already $Ip"; exit 0 }
[IO.File]::WriteAllText($envPath, $text.Replace($old, $Ip), $utf8)
[IO.File]::WriteAllText((Join-Path $R 'web\.env'), "VITE_API_URL=http://${Ip}:8000`n", $utf8)
"LAN IP changed: $old -> $Ip. Now restart: stop.ps1, then start.ps1; reopen the pairing link on the phone."
