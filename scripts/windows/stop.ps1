# Stop what scripts\windows\start.ps1 started (whole process trees, by saved pid).
#   powershell -ExecutionPolicy Bypass -File scripts\windows\stop.ps1             (all)
#   powershell -ExecutionPolicy Bypass -File scripts\windows\stop.ps1 -Only api   (livekit|api|agent|web)
param([ValidateSet('all', 'livekit', 'api', 'agent', 'web')][string]$Only = 'all')
$T = Join-Path (Resolve-Path "$PSScriptRoot\..\..").Path '.cache\run'
$names = if ($Only -eq 'all') { 'web', 'agent', 'api', 'livekit' } else { @($Only) }
foreach ($n in $names) {
    $f = "$T\$n.pid"
    if (-not (Test-Path $f)) { "${n}: not started by start.ps1"; continue }
    $id = [int](Get-Content $f)
    if (Get-Process -Id $id -ErrorAction SilentlyContinue) {
        taskkill /PID $id /T /F | Out-Null
        "$n stopped (pid $id)"
    } else { "${n}: not running" }
    Remove-Item $f
}
