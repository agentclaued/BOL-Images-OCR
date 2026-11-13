# Console-window auto-start for BOL Images (66). Works from any folder: everything is found relative to this file.
#   -Mode Check    : list existing BOL tasks, startup shortcuts, servers on the port (with PID) - changes nothing
#   -Mode Install  : check, then create task Tools-BOL_Images (PC boot + any login + manual run, app .venv)
#                    and a live-log console window at login
#   -Mode Remove   : delete task Tools-BOL_Images
param([ValidateSet('Check','Install','Remove')][string]$Mode = 'Check')
$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
$base = @((Join-Path $here '..'), (Join-Path $here '..\..')) | Where-Object { Test-Path (Join-Path $_ 'app\main.py') } | Select-Object -First 1
if (-not $base) { Write-Host 'Could not find the app folder (app\main.py).' -ForegroundColor Red; exit 1 }
$base = (Resolve-Path $base).Path
$s = ((Get-Content (Join-Path $here 'settings.json') -Raw) -replace '(?m)^\s*//.*$','' | ConvertFrom-Json)
$task = 'Tools-BOL_Images'
$startup = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Startup'

# "This app" = mentions BOL, this app folder, or this app's port. Other apps (e.g. other dashboards) are ignored.
$mine = 'BOL|_console_server|' + [regex]::Escape($base) + '|--port\s+' + $s.port + '\b'

function Show-Existing {
    Write-Host ''
    Write-Host "=== App folder : $base"
    Write-Host "=== App port   : $($s.port)   URL: $($s.public_url)"
    Write-Host ''
    Write-Host '--- Scheduled tasks for BOL / uvicorn:' -ForegroundColor Cyan
    $tasks = Get-ScheduledTask | Where-Object {
        $_.TaskName -match 'BOL' -or (($_.Actions | ForEach-Object { "$($_.Execute) $($_.Arguments) $($_.WorkingDirectory)" }) -join ' ') -match $mine
    }
    if ($tasks) {
        foreach ($t in $tasks) {
            $info = $t | Get-ScheduledTaskInfo
            $act = ($t.Actions | ForEach-Object { "$($_.Execute) $($_.Arguments)" }) -join ' | '
            $port = if ($act -match '--port\s+(\d+)') { $Matches[1] } elseif ($act -match '_console_server') { "$($s.port) (from settings.json)" } else { '?' }
            Write-Host ("  {0}  [{1}]  user={2}  port={3}  last run={4}" -f $t.TaskName, $t.State, $t.Principal.UserId, $port, $info.LastRunTime) -ForegroundColor Yellow
            Write-Host "      runs: $act"
        }
    } else { Write-Host '  none' }

    Write-Host '--- Startup-folder shortcuts for BOL:' -ForegroundColor Cyan
    $sh = New-Object -ComObject WScript.Shell
    $lnks = Get-ChildItem $startup, "$env:ProgramData\Microsoft\Windows\Start Menu\Programs\StartUp" -Filter *.lnk -ErrorAction SilentlyContinue |
        Where-Object { $l = $sh.CreateShortcut($_.FullName); "$($_.Name) $($l.TargetPath) $($l.Arguments) $($l.WorkingDirectory)" -match $mine }
    if ($lnks) { $lnks | ForEach-Object { $l = $sh.CreateShortcut($_.FullName); Write-Host "  $($_.FullName)" -ForegroundColor Yellow; Write-Host "      runs: $($l.TargetPath) $($l.Arguments)" } }
    else { Write-Host '  none' }

    Write-Host '--- Running BOL / uvicorn Python processes:' -ForegroundColor Cyan
    $procs = Get-CimInstance Win32_Process -Filter "Name like 'python%'" | Where-Object { $_.CommandLine -match $mine -or (Get-NetTCPConnection -OwningProcess $_.ProcessId -LocalPort $s.port -State Listen -ErrorAction SilentlyContinue) }
    if ($procs) {
        foreach ($p in $procs) {
            $ports = (Get-NetTCPConnection -OwningProcess $p.ProcessId -State Listen -ErrorAction SilentlyContinue | Select-Object -Expand LocalPort -Unique) -join ','
            Write-Host ("  PID {0}  listening on port {1}" -f $p.ProcessId, $(if ($ports) { $ports } else { '-' })) -ForegroundColor Yellow
            Write-Host "      $($p.CommandLine)"
        }
    } else { Write-Host '  none' }

    Write-Host "--- Anything listening on port $($s.port):" -ForegroundColor Cyan
    $own = Get-NetTCPConnection -LocalPort $s.port -State Listen -ErrorAction SilentlyContinue
    if ($own) { $own | ForEach-Object { $pp = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue; Write-Host "  PID $($_.OwningProcess) ($($pp.ProcessName)) on $($_.LocalAddress):$($_.LocalPort)" -ForegroundColor Yellow } }
    else { Write-Host '  free' }
    Write-Host ''
    return [bool]($tasks -or $lnks -or $procs -or $own)
}

if ($Mode -eq 'Check') { if (Show-Existing) { Write-Host 'Items above are already set up/running for this app. Check them before installing.' -ForegroundColor Yellow } else { Write-Host 'Nothing found - safe to install.' -ForegroundColor Green }; exit 0 }

if ($Mode -eq 'Remove') {
    if (Get-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue) { Stop-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue; Unregister-ScheduledTask -TaskName $task -Confirm:$false; Write-Host "Task $task removed." }
    else { Write-Host "Task $task was not installed." }
    $lnk = Join-Path $startup "$($s.name) (live log).lnk"
    if (Test-Path $lnk) { Remove-Item $lnk -Force; Write-Host 'Live-log window at login removed.' }
    exit 0
}

# ---- Install ----
$found = Show-Existing
if ($found) {
    Write-Host 'WARNING: the items above already exist for this app (other tasks, shortcuts or a running server).' -ForegroundColor Yellow
    Write-Host 'Installing will stop the running app, and remove the older auto-starts (22 boot task BOLImages_Boot, 33 login shortcuts)' -ForegroundColor Yellow
    Write-Host 'so only ONE copy starts. Tasks from OTHER folders/ports listed above are NOT touched - remove them yourself if old.' -ForegroundColor Yellow
    $ans = Read-Host 'Continue? (Y/N)'
    if ($ans -notmatch '^[Yy]') { Write-Host 'Cancelled. Nothing changed.'; exit 2 }
}

& (Join-Path $here 'stop_background.ps1')
Unregister-ScheduledTask -TaskName 'BOLImages_Boot' -Confirm:$false -ErrorAction SilentlyContinue
foreach ($n in @($s.shortcut, "$($s.name) (tray).lnk")) { $p = Join-Path $startup $n; if (Test-Path $p) { Remove-Item $p -Force; Write-Host "Removed old login shortcut: $n" } }

# One task, three ways to start: PC boot, any user login, manual run. Runs hidden as SYSTEM so it works before login.
# The runner exits if the port is already in use, and the task ignores new starts while running: never two copies.
$runner = Join-Path $here '_console_server.bat'
$act = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument "/c `"`"$runner`"`"" -WorkingDirectory $base
$boot = New-ScheduledTaskTrigger -AtStartup; $boot.Delay = 'PT45S'
$logon = New-ScheduledTaskTrigger -AtLogOn; $logon.Delay = 'PT15S'
# Watchdog: every 5 minutes start it if it is not running (runner exits at once if already running or paused).
$watch = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 3650)
$set = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$pri = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask -TaskName $task -Action $act -Trigger @($boot, $logon, $watch) -Settings $set -Principal $pri -Force | Out-Null

# Live-log console window at every login (closing it does not stop the server).
$lnk = Join-Path $startup "$($s.name) (live log).lnk"
$sc = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
$sc.TargetPath = Join-Path $here '_show_log.bat'; $sc.WorkingDirectory = $base; $sc.WindowStyle = 1; $sc.Save()

Write-Host ''
Write-Host "Done. Task $task starts BOL Images ~45s after PC boot, at every login, every 5 min if it is off, and with 66 4 RUN." -ForegroundColor Green
Write-Host "A live-log console window opens when you log in.  Environment: $base\.venv"
Write-Host "Log: $base\logs\server.log   URL: $($s.public_url)"
exit 0
