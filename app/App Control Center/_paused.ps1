# Pause flag so only ONE way of running the app wins at a time (helper, not for double-click).
#   -Action Set          : terminal start. Auto-start/watchdog stand down while THIS terminal window is alive.
#   -Action Set -Manual  : "66 6 STOP". Auto-start stands down until the next PC reboot or "66 4 RUN".
#   -Action Clear        : remove the flag (auto-start/recovery resumes).
#   -Action Test         : exit code 1 = paused (do not start the server), 0 = free. Removes stale flags itself.
param([Parameter(Mandatory)][ValidateSet('Set','Clear','Test')][string]$Action, [switch]$Manual)
$here = $PSScriptRoot
$base = @((Join-Path $here '..'), (Join-Path $here '..\..')) | Where-Object { Test-Path (Join-Path $_ 'app\main.py') } | Select-Object -First 1
$base = (Resolve-Path $base).Path
$dir = Join-Path $base 'logs'
$flag = Join-Path $dir 'paused.flag'
function Get-Boot { (Get-CimInstance Win32_OperatingSystem).LastBootUpTime.Ticks }
switch ($Action) {
    'Clear' { Remove-Item $flag -Force -ErrorAction SilentlyContinue; exit 0 }
    'Set' {
        New-Item -ItemType Directory -Force $dir | Out-Null
        if ($Manual) { "manual|$(Get-Boot)" | Set-Content $flag }
        else { $owner = (Get-CimInstance Win32_Process -Filter "ProcessId=$PID").ParentProcessId; "pid|$owner" | Set-Content $flag }
        exit 0
    }
    'Test' {
        if (-not (Test-Path $flag)) { exit 0 }
        $kind, $val = (Get-Content $flag -TotalCount 1) -split '\|', 2
        $alive = if ($kind -eq 'pid') { [bool](Get-Process -Id ([int]$val) -ErrorAction SilentlyContinue) }
                 elseif ($kind -eq 'manual') { "$val" -eq "$(Get-Boot)" } else { $false }
        if ($alive) { exit 1 }
        Remove-Item $flag -Force -ErrorAction SilentlyContinue; exit 0
    }
}
