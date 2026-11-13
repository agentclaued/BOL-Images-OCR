
w
param(
    [string]$HealthUrl = "http://127.0.0.1:8766/health",
    [int]$CheckIntervalSeconds = 60
)

$ErrorActionPreference = "Stop"
$projectDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$launcher = Join-Path $projectDirectory "start_bol_images_app.bat"

if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
    throw "BOL Images launcher was not found: $launcher"
}

function Test-BolImagesHealth {
    try {
        $response = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 5
        return $response.StatusCode -eq 200 -and $response.Content -match '"status"\s*:\s*"ok"'
    }
    catch {
        return $false
    }
}

while ($true) {
    if (-not (Test-BolImagesHealth)) {
        # The launcher stays running while Uvicorn is healthy; only start it after
        # a failed health check, avoiding duplicate servers.
        Start-Process -FilePath $launcher -WorkingDirectory $projectDirectory -WindowStyle Hidden
        Start-Sleep -Seconds 8
    }
    Start-Sleep -Seconds $CheckIntervalSeconds
}
