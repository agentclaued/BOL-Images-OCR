# Stops this app's tray (no restart) and whatever is listening on this app's port. Used by all OFF files.
$here = $PSScriptRoot
$port = ((Get-Content (Join-Path $here 'settings.json') -Raw) -replace '(?m)^\s*//.*$','' | ConvertFrom-Json).port
Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -like ('*' + $here + '\background_tray.pyw*') } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
