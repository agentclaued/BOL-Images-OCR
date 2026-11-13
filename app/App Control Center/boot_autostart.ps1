# Install/remove the PC-boot task (runs before login, hidden, once, no restart on crash).
param([ValidateSet('Install','Remove')][string]$Action)
$here = $PSScriptRoot
$base = @((Join-Path $here '..'), (Join-Path $here '..\..')) | Where-Object { Test-Path (Join-Path $_ 'app\main.py') } | Select-Object -First 1
$base = (Resolve-Path $base).Path
$s = ((Get-Content (Join-Path $here 'settings.json') -Raw) -replace '(?m)^\s*//.*$','' | ConvertFrom-Json)
$task = 'BOLImages_Boot'
if ($Action -eq 'Remove') {
    Unregister-ScheduledTask -TaskName $task -Confirm:$false -ErrorAction SilentlyContinue
    $tl = Join-Path $env:APPDATA ("Microsoft\Windows\Start Menu\Programs\Startup\" + $s.name + " (tray).lnk")
    if (Test-Path $tl) { Remove-Item $tl -Force }
    Write-Host 'PC boot auto-start removed.'; return
}
$py = Join-Path $base '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { $lp = Join-Path $env:ProgramData 'BOL_Images\venv\Scripts\python.exe'; if (Test-Path $lp) { $py = $lp } }
if (-not (Test-Path $py)) { Write-Host 'App environment missing. Run "11 1 ON" once first.'; return }
New-Item -ItemType Directory -Force (Join-Path $base 'logs') | Out-Null
$cmd = "/c `"`"$py`" -m uvicorn app.main:app --host $($s.host) --port $($s.port) --proxy-headers --forwarded-allow-ips=* >> logs\server.log 2>&1`""
$act = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument $cmd -WorkingDirectory $base
$trg = New-ScheduledTaskTrigger -AtStartup; $trg.Delay = 'PT45S'
$set = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 0 -StartWhenAvailable
Register-ScheduledTask -TaskName $task -Action $act -Trigger $trg -Settings $set -User 'SYSTEM' -RunLevel Highest -Force | Out-Null
# boot and login modes exclude each other
$lnk = Join-Path $env:APPDATA ("Microsoft\Windows\Start Menu\Programs\Startup\" + $s.shortcut)
if (Test-Path $lnk) { Remove-Item $lnk -Force }
# tray-only icon at login (attaches to the boot server; never starts or restarts it)
$pyw = Join-Path (Split-Path $py) 'pythonw.exe'
$tl = Join-Path $env:APPDATA ("Microsoft\Windows\Start Menu\Programs\Startup\" + $s.name + " (tray).lnk")
$sc = (New-Object -ComObject WScript.Shell).CreateShortcut($tl)
$sc.TargetPath = $pyw; $sc.Arguments = '"' + (Join-Path $here 'background_tray.pyw') + '" --attach'
$sc.WorkingDirectory = $base; $sc.WindowStyle = 7; $sc.Save()
Write-Host "Done. $($s.name) starts ~45s after the PC boots (task $task). Not restarted if it crashes."
