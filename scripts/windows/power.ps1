# Keep Windows from throttling Pratyaksh's background processes.
# Windows 11 runs hidden, windowless processes in power-saving "efficiency mode" (EcoQoS), more so while
# the user is away. Measured on the RTX 3060 laptop: Parler took ~40 s a sentence instead of ~8 s, with
# the GPU idling at 877 MHz. Switching throttling off for our own processes needs no admin rights.
#   . scripts\windows\power.ps1; Set-Unthrottled <pid>        (that process and all its children)
#   powershell -File scripts\windows\power.ps1 -Match pratyaksh-voice-cache   (every matching process now)

param([string]$Match)

if (-not ('PratyakshThrottle' -as [type])) {
    Add-Type -TypeDefinition @'
using System; using System.Runtime.InteropServices;
public static class PratyakshThrottle {
  [StructLayout(LayoutKind.Sequential)] struct State { public uint Version; public uint ControlMask; public uint StateMask; }
  [DllImport("kernel32.dll", SetLastError=true)] static extern IntPtr OpenProcess(uint access, bool inherit, int pid);
  [DllImport("kernel32.dll", SetLastError=true)] static extern bool SetProcessInformation(IntPtr h, int cls, ref State s, int size);
  [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);
  // ProcessPowerThrottling (4): control execution speed and timer resolution, state 0 = never throttle.
  public static bool Off(int pid) {
    IntPtr h = OpenProcess(0x0200, false, pid);
    if (h == IntPtr.Zero) return false;
    State s = new State(); s.Version = 1; s.ControlMask = 0x1 | 0x4; s.StateMask = 0;
    bool ok = SetProcessInformation(h, 4, ref s, Marshal.SizeOf(typeof(State)));
    CloseHandle(h); return ok;
  }
}
'@
}

function Get-Tree([int]$Root) {
    $all = Get-CimInstance Win32_Process -Property ProcessId, ParentProcessId
    $ids = @($Root); $frontier = @($Root)
    while ($frontier) {
        $frontier = @($all | Where-Object { $frontier -contains $_.ParentProcessId } | ForEach-Object { [int]$_.ProcessId })
        $ids += $frontier
    }
    return $ids
}

function Set-Unthrottled([int]$Root) {
    foreach ($id in Get-Tree $Root) {
        $p = Get-Process -Id $id -ErrorAction SilentlyContinue
        if (-not $p) { continue }
        [void][PratyakshThrottle]::Off($id)
        try { if ($p.PriorityClass -eq 'Normal') { $p.PriorityClass = 'AboveNormal' } } catch {}
    }
}

if ($Match) {
    Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*$Match*" } |
        ForEach-Object { Set-Unthrottled ([int]$_.ProcessId); "unthrottled $($_.ProcessId) $($_.Name)" }
}
