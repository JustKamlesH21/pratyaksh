# Start Pratyaksh on the Windows GPU laptop: LiveKit, the verifier API, the Voice Agent and the web app,
# each hidden in the background with a log in .cache\run (git-ignored).
#   powershell -ExecutionPolicy Bypass -File scripts\windows\start.ps1             (all)
#   powershell -ExecutionPolicy Bypass -File scripts\windows\start.ps1 -Only api   (livekit|api|agent|web)
# Stop with scripts\windows\stop.ps1. Secrets are read from .env and never printed.
# LiveKit: -LiveKit <path to livekit-server.exe>, or LIVEKIT_SERVER in the environment, or on PATH.
# Laptops: use the vendor's performance/Turbo power mode; quiet modes double every model time.
# Models load from the local Hugging Face cache only (venue internet is unreliable, ADR-0005; checking
# for updates on slow Wi-Fi took Whisper's load from 17 s to 2.5 min). Pass -Online the first time,
# when the models still have to be downloaded.
param(
    [ValidateSet('all', 'livekit', 'api', 'agent', 'web')][string]$Only = 'all',
    [string]$LiveKit = $env:LIVEKIT_SERVER,
    [switch]$Online
)
$ErrorActionPreference = 'Stop'
$R = (Resolve-Path "$PSScriptRoot\..\..").Path
$T = Join-Path $R '.cache\run'
New-Item -ItemType Directory -Force $T | Out-Null

$envs = @{}
foreach ($l in [IO.File]::ReadAllLines("$R\.env")) {
    if ($l -match '^\s*([A-Za-z_]\w*)\s*=\s*(.*?)\s*(\s#.*)?$') { $envs[$matches[1]] = $matches[2].Trim('"', "'") }
}
. "$PSScriptRoot\pidfile.ps1"
. "$PSScriptRoot\power.ps1"
function Running($name) { return [bool](Get-Started "$T\$name.pid") }
function Launch($name, $exe, $argList, $dir) {
    if (Running $name) { "$name already running (pid $(Get-Content "$T\$name.pid"))"; return }
    $opts = @{ FilePath = $exe; WorkingDirectory = $dir; WindowStyle = 'Hidden'; PassThru = $true
               RedirectStandardOutput = "$T\$name.out.log"; RedirectStandardError = "$T\$name.log" }
    if ($argList) { $opts.ArgumentList = $argList }  # Start-Process refuses an empty list
    $p = Start-Process @opts
    Save-Started "$T\$name.pid" $p
    Start-Sleep -Seconds 2  # the .exe launchers start the real python.exe as a child
    Set-Unthrottled $p.Id   # hidden processes are otherwise throttled by Windows (see power.ps1)
    "$name started (pid $($p.Id)); log $T\$name.log"
}

$env:PYTHONUTF8 = '1'; $env:PYTHONUNBUFFERED = '1'            # Kannada/Hindi in logs; logs as they happen
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = '1'
if ($Online) { Remove-Item Env:HF_HUB_OFFLINE -ErrorAction SilentlyContinue } else { $env:HF_HUB_OFFLINE = '1' }
Remove-Item Env:HTTP_PROXY, Env:HTTPS_PROXY, Env:ALL_PROXY -ErrorAction SilentlyContinue  # proxies break the agent's WebSocket
$env:NO_PROXY = '127.0.0.1,localhost'

if ($Only -in 'all', 'livekit') {
    if (-not $LiveKit) { $LiveKit = (Get-Command livekit-server -ErrorAction SilentlyContinue).Source }
    if (-not $LiveKit) { throw 'livekit-server not found: pass -LiveKit <path> or set LIVEKIT_SERVER.' }
    $env:LIVEKIT_KEYS = "$($envs.LIVEKIT_API_KEY): $($envs.LIVEKIT_API_SECRET)"  # not on the command line
    Launch 'livekit' $LiveKit @('--config', "$R\infra\livekit.yaml", '--node-ip', $envs.LAN_IP) $T
    Remove-Item Env:LIVEKIT_KEYS
}
if ($Only -in 'all', 'api') {
    Launch 'api' "$R\.venv\Scripts\pratyaksh-api.exe" @() $R
}
if ($Only -in 'all', 'agent') {
    # The LiveKit Agents CLI reads these from the environment, not from .env.
    foreach ($n in 'LIVEKIT_URL', 'LIVEKIT_API_KEY', 'LIVEKIT_API_SECRET') { Set-Item "env:$n" $envs[$n] }
    Launch 'agent' "$R\.venv\Scripts\pratyaksh-agent.exe" @('dev') $R
    foreach ($n in 'LIVEKIT_URL', 'LIVEKIT_API_KEY', 'LIVEKIT_API_SECRET') { Remove-Item "env:$n" }
}
if ($Only -in 'all', 'web') {
    Launch 'web' 'npm.cmd' @('run', 'dev') "$R\web"
}
"Console: http://localhost:5173/console   Caller: http://localhost:5173/call   Status: http://$($envs.LAN_IP):8000/v1/status"
