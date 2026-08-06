$ErrorActionPreference = "Stop"

$dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
$dockerExe = if ($dockerCommand) {
    $dockerCommand.Source
} elseif (Test-Path -LiteralPath "D:\Docker\resources\bin\docker.exe") {
    "D:\Docker\resources\bin\docker.exe"
} else {
    $null
}

if (-not $dockerExe) {
    Write-Host "Docker was not found. Install and start Docker Desktop first." -ForegroundColor Red
    exit 1
}

function Invoke-Compose {
    param(
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$ComposeArgs
    )

    & $dockerExe compose version *> $null
    if ($LASTEXITCODE -eq 0) {
        & $dockerExe compose @ComposeArgs
        return
    }

    $dockerComposeCommand = Get-Command docker-compose -ErrorAction SilentlyContinue
    if ($dockerComposeCommand) {
        & $dockerComposeCommand.Source @ComposeArgs
        return
    }

    throw "Docker Compose was not found. Install Docker Compose v2 or docker-compose.exe."
}

Write-Host "Building and starting MySQL, backend, and Agent..." -ForegroundColor Cyan
Invoke-Compose up --build -d

Write-Host ""
Invoke-Compose ps
Write-Host ""
Write-Host "Open http://localhost:18000 after the services become ready." -ForegroundColor Green
Write-Host "Demo account: testuser / password"
Write-Host "The first build may take several minutes to download images and dependencies."
