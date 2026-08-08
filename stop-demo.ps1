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
    Write-Host "Docker was not found." -ForegroundColor Red
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

Invoke-Compose down
Write-Host "Demo services stopped. Database data remains in the Docker volume." -ForegroundColor Green
