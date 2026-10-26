# Pid files for start.ps1 and stop.ps1. Each holds the pid and the process's start time, so a pid that
# Windows has since given to another process (after a reboot, say) is never mistaken for ours.

function Save-Started([string]$Path, $Process) {
    "$($Process.Id) $($Process.StartTime.ToUniversalTime().Ticks)" | Set-Content $Path
}

# The process a pid file names, if it is still the one we started; otherwise $null (and the stale file goes).
function Get-Started([string]$Path) {
    if (-not (Test-Path $Path)) { return $null }
    $id, $ticks = ((Get-Content $Path -Raw) -as [string]).Trim() -split '\s+'
    $p = if ($id -match '^\d+$' -and [int]$id -gt 0) { Get-Process -Id ([int]$id) -ErrorAction SilentlyContinue }
    if ($p -and $ticks -and "$($p.StartTime.ToUniversalTime().Ticks)" -eq $ticks) { return $p }
    Remove-Item $Path -ErrorAction SilentlyContinue
    return $null
}
