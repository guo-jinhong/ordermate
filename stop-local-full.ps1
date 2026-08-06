param(
    [int[]]$Ports = @(8080, 18000)
)

$ErrorActionPreference = "Continue"

$root = (Resolve-Path ".").Path
$runDir = Join-Path $root ".run"
$pidFiles = @(
    (Join-Path $runDir "agent.pid"),
    (Join-Path $runDir "backend.pid")
)

foreach ($pidFile in $pidFiles) {
    if (-not (Test-Path -LiteralPath $pidFile)) {
        continue
    }
    $pidValue = (Get-Content -Path $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    if (-not $pidValue) {
        Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
        continue
    }
    try {
        $process = Get-Process -Id ([int]$pidValue) -ErrorAction Stop
        Stop-Process -Id $process.Id -Force -ErrorAction Stop
        Write-Host "Stopped process $($process.Id) from $pidFile"
    } catch {
        Write-Host "Process from $pidFile is not running."
    }
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
}

foreach ($port in $Ports) {
    $listeners = netstat -ano | Select-String ":$port\s" | Where-Object { $_ -match "LISTENING" }
    foreach ($listener in $listeners) {
        $parts = $listener.ToString() -split "\s+" | Where-Object { $_ }
        if (-not $parts -or $parts.Count -lt 5) {
            continue
        }
        $pidValue = [int]$parts[-1]
        try {
            $process = Get-Process -Id $pidValue -ErrorAction Stop
            Stop-Process -Id $process.Id -Force -ErrorAction Stop
            Write-Host "Stopped process $($process.Id) listening on port $port"
        } catch {
            Write-Host "Process listening on port $port is not running."
        }
    }
}

Write-Host "Local full stack stop command completed." -ForegroundColor Green
