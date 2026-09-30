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

# 预检：docker.exe 存在不代表 Docker 守护进程已就绪。之前脚本直接进入
# compose，失败时只抛出一句 npipe:////./pipe/dockerDesktopLinuxEngine 的
# 底层错误，看不出到底缺什么。这里先探测引擎，并给出可执行的原因与出路。
function Test-DockerEngine {
    & $dockerExe version --format '{{.Server.Version}}' *> $null
    return ($LASTEXITCODE -eq 0)
}

if (-not (Test-DockerEngine)) {
    Write-Host "Docker CLI was found at: $dockerExe" -ForegroundColor Yellow
    Write-Host "But the Docker engine is not running, so 'docker compose' cannot connect." -ForegroundColor Red
    Write-Host ""
    Write-Host "Common causes on Windows:" -ForegroundColor Yellow
    Write-Host "  1. Docker Desktop is not started yet (wait for 'Engine running' in the tray)."
    Write-Host "  2. WSL2 / Virtual Machine Platform is not enabled. Docker Desktop log shows:"
    Write-Host "     'engine linux/wsl failed to start: Virtual Machine Platform not enabled'"
    Write-Host "     Enable it in an ADMIN PowerShell, then REBOOT:"
    Write-Host "       dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart"
    Write-Host "       dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart"
    Write-Host "       wsl --set-default-version 2"
    Write-Host "  3. Virtualization (VT-x/AMD-V) is disabled in BIOS."
    Write-Host ""
    Write-Host "No need to wait: this machine already has a working local stack that does not use Docker." -ForegroundColor Green
    Write-Host "Run instead:" -ForegroundColor Green
    Write-Host "  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start-local-full.ps1" -ForegroundColor Green
    Write-Host "  (local MySQL on 127.0.0.1:3306, Java on 8080, Agent on 18000)"
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
$agentPortLine = Invoke-Compose port agent 8000 | Select-Object -First 1
$agentPort = if ($agentPortLine -match ':(\d+)$') { $Matches[1] } else { "8000" }
Write-Host "Open http://localhost:$agentPort after the services become ready." -ForegroundColor Green
Write-Host "Demo account: testuser / password"
Write-Host "The first build may take several minutes to download images and dependencies."
