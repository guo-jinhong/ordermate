param(
    [string]$MySqlRootPassword = "123456"
)

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
    Write-Host "Docker was not found. Start Docker Desktop first." -ForegroundColor Red
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

$mysqlContainer = Invoke-Compose ps -q mysql
if (-not $mysqlContainer) {
    Write-Host "The demo MySQL container is not running. Run .\start-demo.ps1 first." -ForegroundColor Red
    exit 1
}

$sql = @"
START TRANSACTION;
UPDATE products p
JOIN order_items oi ON oi.product_id = p.id
JOIN orders o ON o.id = oi.order_id
SET p.stock = p.stock - oi.quantity,
    p.sold_count = p.sold_count + oi.quantity
WHERE o.id = 1 AND o.status = 4;
UPDATE orders
SET status = 0,
    payment_status = 0,
    paid_at = NULL,
    shipped_at = NULL,
    delivered_at = NULL
WHERE id = 1;
COMMIT;
"@

& $dockerExe exec $mysqlContainer mysql "-uroot" "-p$MySqlRootPassword" `
    -D ecommerce_db -e $sql
if ($LASTEXITCODE -ne 0) {
    throw "Failed to reset the demo order."
}

Invoke-Compose restart agent | Out-Null
Write-Host "Demo order 1 and its confirmation state were reset." -ForegroundColor Green
Write-Host "Login: testuser / password"
