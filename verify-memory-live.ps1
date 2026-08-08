$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot
$Docker = "D:\Docker\resources\bin\docker.exe"

function Write-Step([string]$Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Invoke-AgentChat([string]$Message, [string]$SessionId, [string]$AccessToken = "") {
    $body = @{
        message = $Message
        session_id = $SessionId
        access_token = if ($AccessToken) { $AccessToken } else { $null }
    } | ConvertTo-Json
    return Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/chat" -ContentType "application/json" -Body $body
}

if (-not (Test-Path $Docker)) {
    throw "未找到 Docker CLI：$Docker"
}

Write-Step "检查 Docker 与容器"
& $Docker version --format "Docker Server {{.Server.Version}}"
& $Docker compose ps

Write-Step "检查 Agent 健康状态"
$health = Invoke-RestMethod "http://127.0.0.1:8000/health"
$health | Format-List
if ($health.status -ne "ok") { throw "Agent health 状态异常" }
if ($health.agent_mode -ne "live") { throw "当前不是 live 模式：$($health.agent_mode)" }
if (-not $health.model_configured) { throw "真实模型未配置" }

$sessionId = [guid]::NewGuid().ToString()
Write-Host "测试会话：$sessionId"

Write-Step "验证匿名商品多轮上下文"
$productTurns = @(
    "推荐几款手机，按价格从低到高介绍",
    "便宜一点的",
    "第二个怎么样",
    "它还有库存吗"
)
foreach ($turn in $productTurns) {
    Write-Host "`n用户：$turn" -ForegroundColor Yellow
    $response = Invoke-AgentChat $turn $sessionId
    Write-Host "Agent：$($response.answer)"
    if ([string]::IsNullOrWhiteSpace($response.answer)) { throw "模型返回了空回复" }
    if ($response.tool_calls) {
        Write-Host "工具：$((@($response.tool_calls) | ForEach-Object { $_.name }) -join ', ')" -ForegroundColor DarkGray
    }
}

Write-Step "登录并验证订单多轮上下文"
$loginBody = @{ username = "testuser"; password = "password" } | ConvertTo-Json
$login = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/auth/login" -ContentType "application/json" -Body $loginBody
$token = $login.access_token
if ([string]::IsNullOrWhiteSpace($token)) { throw "登录成功但没有返回 access token" }
Write-Host "登录成功（令牌已隐藏）" -ForegroundColor Green

$orderTurns = @("查看我的订单", "刚才那个待支付订单是什么时候创建的")
foreach ($turn in $orderTurns) {
    Write-Host "`n用户：$turn" -ForegroundColor Yellow
    $response = Invoke-AgentChat $turn $sessionId $token
    Write-Host "Agent：$($response.answer)"
    if ([string]::IsNullOrWhiteSpace($response.answer)) { throw "模型返回了空回复" }
}

Write-Step "清空服务端会话记忆"
$clearBody = @{ session_id = $sessionId; access_token = $token } | ConvertTo-Json
$clear = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/conversation/clear" -ContentType "application/json" -Body $clearBody
$clear | Format-List

Write-Step "验证清空后不应继续依赖旧指代"
$response = Invoke-AgentChat "第二个怎么样" $sessionId
Write-Host "Agent：$($response.answer)"

Write-Host "`n真实模型多轮联调脚本执行完成。请人工确认最后一条回复没有凭空复用清空前的商品列表。" -ForegroundColor Green
