# Stop what scripts\windows\start.ps1 started (whole process trees, by saved pid and start time).
#   powershell -ExecutionPolicy Bypass -File scripts\windows\stop.ps1             (all)
#   powershell -ExecutionPolicy Bypass -File scripts\windows\stop.ps1 -Only api   (livekit|api|agent|web)
param([ValidateSet('all', 'livekit', 'api', 'agent', 'web')][string]$Only = 'all')
$T = Join-Path (Resolve-Path "$PSScriptRoot\..\..").Path '.cache\run'
. "$PSScriptRoot\pidfile.ps1"
$names = if ($Only -eq 'all') { 'web', 'agent', 'api', 'livekit' } else { @($Only) }
foreach ($n in $names) {
    $p = Get-Started "$T\$n.pid"
    if (-not $p) { "${n}: not running"; continue }
    taskkill /PID $p.Id /T /F | Out-Null
    Remove-Item "$T\$n.pid" -ErrorAction SilentlyContinue
    "$n stopped (pid $($p.Id))"
}
