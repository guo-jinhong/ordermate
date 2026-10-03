#Requires -Version 5.1
# Run after start-dev-stack.ps1 -PublicDemo. The new tunnel stays in this window.
param([string]$Domain, [switch]$CheckOnly)

$ErrorActionPreference = "Stop"
$expectedUrl = "https://lesia-unfrightening-leone.ngrok-free.dev"
if (-not $Domain) { $Domain = $env:NGROK_DOMAIN }
if (-not $Domain) {
    $envFile = Join-Path $PSScriptRoot '.env'
    if (-not (Test-Path -LiteralPath $envFile)) { $envFile = Join-Path $PSScriptRoot 'agent-service/.env' }
    if (Test-Path -LiteralPath $envFile) {
        foreach ($line in Get-Content -LiteralPath $envFile -Encoding UTF8) {
            if ($line -match '^\s*NGROK_DOMAIN\s*=\s*(.*)$') { $Domain = $matches[1].Split('#')[0].Trim().Trim('"').Trim("'") }
        }
    }
}
if ($Domain) { $expectedUrl = if ($Domain.StartsWith('https://')) { $Domain.TrimEnd('/') } else { "https://$Domain" } }
if ($expectedUrl -notmatch '^https://[a-zA-Z0-9][a-zA-Z0-9.-]*\.[a-zA-Z]{2,}$') { throw 'NGROK_DOMAIN must be an HTTPS hostname without a path or port.' }
$localHealth = "http://127.0.0.1:8000/health"
$tunnelApi = "http://127.0.0.1:4040/api/tunnels"

$ngrok = Get-Command ngrok.exe -ErrorAction SilentlyContinue
if (-not $ngrok) { throw 'ngrok.exe was not found in PATH. Install/sign in to ngrok first.' }
if ($CheckOnly) {
    & $ngrok.Source version
    if ($LASTEXITCODE -ne 0) { throw 'ngrok.exe cannot run.' }
    Write-Host "ngrok preflight passed: $expectedUrl (no tunnel started)." -ForegroundColor Green
    exit 0
}

function Assert-PublicDemoHealth {
    param($Health)
    if ($Health.status -ne 'ok' -or $Health.public_demo -ne $true -or
        $Health.agent_mode -ne 'live' -or $Health.model_configured -ne $true) {
        throw 'Start/restart with start-dev-stack.ps1 -PublicDemo first; a healthy local development service cannot be exposed.'
    }
}

try {
    $health = Invoke-RestMethod -Uri $localHealth -TimeoutSec 5
    Assert-PublicDemoHealth $health
} catch {
    Write-Error "Public demo is not ready at $localHealth. ngrok was not started. $($_.Exception.Message)"
    exit 1
}

# An existing ngrok agent can continue forwarding while local services restart.
try {
    $existing = Invoke-RestMethod -Uri $tunnelApi -TimeoutSec 3
} catch {
    $existing = $null
}

if ($existing) {
    $tunnels = @($existing.tunnels)
    $matching = @($tunnels | Where-Object {
        $_.public_url -eq $expectedUrl -and
        $_.config.addr -in @("http://127.0.0.1:8000", "127.0.0.1:8000")
    })
    if ($matching.Count -gt 0) {
        if ($matching[0].config.inspect -ne $false) {
            Write-Error "The existing tunnel has request inspection enabled. Stop it and restart with --inspect=false."
            exit 1
        }
        Write-Host "Public demo tunnel is already running: $expectedUrl" -ForegroundColor Green
        Write-Host "Closing this launcher will not stop that existing ngrok process."
        exit 0
    }
    if ($tunnels.Count -gt 0) {
        Write-Error "A different ngrok tunnel is already running. Stop it or inspect $tunnelApi before starting this public demo."
        exit 1
    }
}

Write-Host "Starting public demo tunnel: $expectedUrl" -ForegroundColor Cyan
Write-Host "Keep this window open; Ctrl+C or closing it stops this new tunnel."
try {
    & $ngrok.Source http 127.0.0.1:8000 --url $expectedUrl --inspect=false
    exit $LASTEXITCODE
} catch {
    Write-Error "ngrok could not start: $($_.Exception.Message)"
    exit 1
}
