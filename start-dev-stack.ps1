#Requires -Version 5.1
# 一键启动开发验收环境：Java 后端(8080) + Agent(8000/auto) + Vue(5173)
# 双击「一键启动Vue.bat」运行；本窗口关闭后，后台服务继续运行。
#
# 已修复的问题：
#  1) 本文件必须存为 UTF-8 with BOM。否则 Windows PowerShell 5.1 会按 GBK 解码中文，
#     导致语法错误（Missing closing '}' 等），双击直接报错。
#  2) foreach 的循环变量名不能叫 $pid —— $PID 是只读自动变量，赋值会抛异常。
#  3) 就绪接口必须返回 2xx，避免把错误路径或鉴权失败当成启动成功。
#  4) 启动后端前先确认 MySQL 3306 可达，避免白等 150 秒。

param(
    [ValidateSet("auto", "live", "demo")]
    [string]$Mode = "auto",
    [switch]$PublicDemo,
    [switch]$NoBrowser,
    [switch]$NoPause,
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"

[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
try { chcp 65001 > $null } catch {}

$root = $PSScriptRoot
if (-not $root) { $root = Split-Path -Parent $MyInvocation.MyCommand.Path }
$agentDir = Join-Path $root "agent-service"
$frontendDir = Join-Path $root "frontend"

function Import-DotEnv {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return }
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#") -or -not $trimmed.Contains("=")) { continue }
        $name, $value = $trimmed.Split("=", 2)
        $name = $name.Trim()
        $value = $value.Trim().Trim('"').Trim("'")
        $commentIndex = $value.IndexOf(" #")
        if ($commentIndex -ge 0) {
            $value = $value.Substring(0, $commentIndex).Trim()
        }
        if ($name) { [Environment]::SetEnvironmentVariable($name, $value, "Process") }
    }
}

$environmentFile = Join-Path $root ".env"
if (-not (Test-Path -LiteralPath $environmentFile)) { $environmentFile = Join-Path $agentDir ".env" }
Import-DotEnv $environmentFile
if ($PublicDemo) {
    $Mode = "live"
    $env:PUBLIC_DEMO = "true"
    $env:PUBLIC_READONLY = "false"
    $env:SERVER_ADDRESS = "127.0.0.1"
    if (-not $env:DEMO_ALLOWED_USERS) { $env:DEMO_ALLOWED_USERS = "interview_demo" }
} else {
    # 本地启动不继承上一次公网模式的登录限制。
    $env:PUBLIC_DEMO = "false"
}
$env:AGENT_MODE = $Mode

function Set-DefaultProcessEnvironment {
    param([string]$Name, [string]$Value)
    if (-not [Environment]::GetEnvironmentVariable($Name, "Process")) {
        [Environment]::SetEnvironmentVariable($Name, $Value, "Process")
    }
}

# 子进程继承环境变量：支持 .env 覆盖，同时避免把密码拼到命令行参数里。
Set-DefaultProcessEnvironment "MYSQL_HOST" "127.0.0.1"
Set-DefaultProcessEnvironment "MYSQL_PORT" "3306"
Set-DefaultProcessEnvironment "MYSQL_USER" "root"
Set-DefaultProcessEnvironment "MYSQL_PASSWORD" "123456"
Set-DefaultProcessEnvironment "MYSQL_DATABASE" "ecommerce_db"
Set-DefaultProcessEnvironment "ECOMMERCE_BACKEND" "api"
Set-DefaultProcessEnvironment "ECOMMERCE_API_BASE_URL" "http://localhost:8080/api"
Set-DefaultProcessEnvironment "DB_TYPE" "mysql"

$env:SPRING_DATASOURCE_URL = "jdbc:mysql://$($env:MYSQL_HOST):$($env:MYSQL_PORT)/$($env:MYSQL_DATABASE)?useSSL=false&serverTimezone=UTC&allowPublicKeyRetrieval=true"
$env:SPRING_DATASOURCE_USERNAME = $env:MYSQL_USER
$env:SPRING_DATASOURCE_PASSWORD = $env:MYSQL_PASSWORD

function Test-TcpPort {
    param([string]$TargetHost, [int]$Port)
    $client = $null
    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        $async = $client.BeginConnect($TargetHost, $Port, $null, $null)
        $ok = $async.AsyncWaitHandle.WaitOne(800)
        if ($ok) { $client.EndConnect($async) }
        return $ok
    } catch {
        return $false
    } finally {
        if ($client) { $client.Close() }
    }
}

function Get-PidsByPort {
    param([int]$Port)
    $found = @()
    $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($conn in $connections) {
        if ($conn.OwningProcess -and $conn.OwningProcess -ne 0) {
            $found += $conn.OwningProcess
        }
    }
    # 受限 Windows 环境可能无法访问网络 CIM，回退到监听端口列表。
    if ($found.Count -eq 0) {
        foreach ($line in (& netstat.exe -ano -p tcp)) {
            if ($line -match '^\s*TCP\s+\S+:(\d+)\s+\S+\s+LISTENING\s+(\d+)\s*$' -and [int]$matches[1] -eq $Port) {
                $found += [int]$matches[2]
            }
        }
    }
    return @($found | Sort-Object -Unique)
}

function Test-ProjectListener {
    param([int]$ProcessId, [int]$Port)
    $info = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
    if (-not $info) { return $false }
    $workspacePrefix = $root.TrimEnd('\') + '\'
    $commandLine = ([string]$info.CommandLine).Replace('/', '\')
    $executable = ([string]$info.ExecutablePath).Replace('/', '\')
    $belongsHere = $commandLine.IndexOf($workspacePrefix, [StringComparison]::OrdinalIgnoreCase) -ge 0 -or
        $executable.StartsWith($workspacePrefix, [StringComparison]::OrdinalIgnoreCase)
    # Windows venv python.exe forwards to global Python; confirm its direct venv parent.
    if (-not $belongsHere -and $Port -eq 8000 -and $info.Name -match '^python(?:w)?\.exe$') {
        $parent = Get-CimInstance Win32_Process -Filter "ProcessId=$($info.ParentProcessId)" -ErrorAction SilentlyContinue
        $expectedLauncher = Join-Path $agentDir '.venv\Scripts\python.exe'
        $belongsHere = $parent -and ([string]$parent.ExecutablePath).Equals($expectedLauncher, [StringComparison]::OrdinalIgnoreCase) -and
            ([string]$parent.CommandLine -match 'uvicorn\s+app\.main:app') -and $parent.CreationDate -le $info.CreationDate
    }
    if (-not $belongsHere) { return $false }
    if ($Port -eq 8080) { return $info.Name -eq 'java.exe' -and $commandLine -match 'com\.ecommerce\.EcommerceOrderSystemApplication' }
    if ($Port -eq 8000) { return $info.Name -match '^python(?:w)?\.exe$' -and $commandLine -match 'uvicorn\s+app\.main:app' }
    if ($Port -eq 5173) { return $info.Name -eq 'node.exe' -and $commandLine -match 'vite' }
    return $false
}

function Stop-Port {
    param([int]$Port, [switch]$ValidateOnly)
    $pids = @(Get-PidsByPort $Port)
    if ($pids.Count -eq 0) { return }
    foreach ($procId in $pids) {
        if (-not (Test-ProjectListener $procId $Port)) {
            throw "端口 $Port 的进程 $procId 无法确认属于当前项目，未停止。请手动处理端口占用后重试。"
        }
    }
    if ($ValidateOnly) { return }
    Write-Host "端口 $Port 被本项目占用，正在重新启动进程: $($pids -join ', ')" -ForegroundColor Yellow
    foreach ($procId in $pids) {
        try { Stop-Process -Id $procId -Force -ErrorAction Stop } catch {}
    }
    Start-Sleep -Seconds 1
}

function Wait-ForUrl {
    param([string]$Name, [string]$Url, [int]$Seconds = 120)
    Write-Host "等待 $Name 就绪: $Url"
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300) {
                Write-Host "$Name 已就绪。" -ForegroundColor Green
                return $true
            }
        } catch {
            # 就绪接口必须成功，不能把 404 或鉴权错误当成启动成功。
            $webResponse = $_.Exception.Response
            if ($webResponse -ne $null) {
                $code = [int]$webResponse.StatusCode
                if ($code -ge 200 -and $code -lt 300) {
                    Write-Host "$Name 已就绪（HTTP $code）。" -ForegroundColor Green
                    return $true
                }
            }
        }
        Start-Sleep -Seconds 2
    }
    Write-Host "$Name 在 $Seconds 秒内未就绪。" -ForegroundColor Red
    return $false
}

function Get-JavaMajorVersion {
    $java = $null
    if ($env:JAVA_HOME) {
        $candidate = Join-Path $env:JAVA_HOME "bin\java.exe"
        if (Test-Path $candidate) { $java = $candidate }
    }
    if (-not $java) {
        $command = Get-Command java -ErrorAction SilentlyContinue
        if ($command) { $java = $command.Source }
    }
    # 返回 0 = 没找到 java，-1 = 找到了但探测失败，>0 = 主版本号
    if (-not $java) { return 0 }

    try {
        $info = [System.Diagnostics.ProcessStartInfo]::new()
        $info.FileName = $java
        $info.Arguments = "-version"
        $info.RedirectStandardOutput = $true
        $info.RedirectStandardError = $true
        $info.UseShellExecute = $false
        $info.CreateNoWindow = $true
        $process = [System.Diagnostics.Process]::Start($info)
        $text = $process.StandardOutput.ReadToEnd() + $process.StandardError.ReadToEnd()
        $process.WaitForExit()
        if ($text -match 'version "1\.(\d+)') { return [int]$matches[1] }
        if ($text -match 'version "(\d+)') { return [int]$matches[1] }
        return -1
    } catch {
        # 某些受限环境不允许带重定向地启动进程。这里不阻断，交给 mvnw 自行报错。
        return -1
    }
}

# ===== 前提检查 =====
Write-Host "=== 检查环境前提 ===" -ForegroundColor Cyan

if (-not (Test-Path (Join-Path $root "mvnw.cmd"))) {
    Write-Host "找不到 mvnw.cmd，请在项目根目录运行此脚本。" -ForegroundColor Red
    if (-not $NoPause) { Read-Host "按回车退出" }; exit 1
}
if (-not (Test-Path (Join-Path $agentDir ".venv\Scripts\python.exe"))) {
    Write-Host "找不到 agent-service\.venv\Scripts\python.exe，请先创建 Python 虚拟环境。" -ForegroundColor Red
    if (-not $NoPause) { Read-Host "按回车退出" }; exit 1
}
if (-not (Test-Path (Join-Path $frontendDir "package.json"))) {
    Write-Host "找不到 frontend\package.json。" -ForegroundColor Red
    if (-not $NoPause) { Read-Host "按回车退出" }; exit 1
}
if (-not (Test-Path (Join-Path $frontendDir "node_modules"))) {
    Write-Host "frontend\node_modules 不存在，请先在 frontend 目录执行 npm install。" -ForegroundColor Red
    if (-not $NoPause) { Read-Host "按回车退出" }; exit 1
}

$javaMajor = Get-JavaMajorVersion
if ($javaMajor -eq 0) {
    Write-Host "未找到 java，请安装 JDK 17 并设置 JAVA_HOME。" -ForegroundColor Red
    if (-not $NoPause) { Read-Host "按回车退出" }; exit 1
} elseif ($javaMajor -eq -1) {
    Write-Host "无法检测 Java 版本（已跳过检查）；若版本过低，后端窗口会直接报错。" -ForegroundColor Yellow
} elseif ($javaMajor -lt 17) {
    Write-Host "需要 Java 17+，当前 Java $javaMajor。请安装 JDK 17 并设置 JAVA_HOME。" -ForegroundColor Red
    if (-not $NoPause) { Read-Host "按回车退出" }; exit 1
} else {
    Write-Host "Java $javaMajor  OK" -ForegroundColor Green
}

# 前端构建/启动要求与 package.json 保持一致。
if (-not (Get-Command node.exe -ErrorAction SilentlyContinue) -or -not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    throw "未找到 Node.js/npm，请按 frontend/package.json 的 engines 安装。"
}
$nodeVersionText = (& node.exe --version).Trim().TrimStart('v')
$package = Get-Content (Join-Path $frontendDir 'package.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ($package.engines.node -match '>=([0-9.]+)\s+<([0-9]+)') {
    $nodeVersion = [Version]$nodeVersionText
    if ($nodeVersion -lt [Version]$matches[1] -or $nodeVersion.Major -ge [int]$matches[2]) {
        throw "Node.js $nodeVersionText 不满足项目要求 $($package.engines.node)。"
    }
}
if ($package.engines.npm -match '>=([0-9.]+)') {
    $minimumNpm = [Version]$matches[1]
    $npmVersion = [Version]((& npm.cmd --version).Trim())
    if ($npmVersion -lt $minimumNpm) { throw "npm $npmVersion 不满足项目要求 $($package.engines.npm)。" }
}
& (Join-Path $agentDir '.venv\Scripts\python.exe') -c "import sys, uvicorn, fastapi, openai, redis, langgraph, slowapi; assert sys.version_info >= (3, 11)"
if ($LASTEXITCODE -ne 0) { throw "Python 版本或 Agent 依赖不完整，请按 requirements.txt 安装。" }
if ($Mode -eq 'live' -and [string]::IsNullOrWhiteSpace($env:OPENAI_API_KEY)) {
    throw "live/公网演示模式需要 OPENAI_API_KEY，请在本地 .env 配置后重试。"
}

# ===== MySQL 检查 =====
Write-Host "`n=== 检查 MySQL (3306) ===" -ForegroundColor Cyan
if (-not (Test-TcpPort $env:MYSQL_HOST ([int]$env:MYSQL_PORT))) {
    if ($CheckOnly) { throw "配置的 MySQL 不可达；预检不会启动数据库服务。" }
    Write-Host "MySQL 3306 不可达，尝试启动 MySQL80 服务…" -ForegroundColor Yellow
    try {
        if ($env:MYSQL_HOST -notin @("127.0.0.1", "localhost") -or $env:MYSQL_PORT -ne "3306") { throw "Configured MySQL is unavailable." }
        Start-Service MySQL80 -ErrorAction Stop
    } catch {
        Write-Host "自动启动失败（可能需要管理员权限）。" -ForegroundColor Yellow
    }
    Start-Sleep -Seconds 5
}
if (-not (Test-TcpPort $env:MYSQL_HOST ([int]$env:MYSQL_PORT))) {
    Write-Host "MySQL 3306 仍不可达。后端依赖数据库，无法继续。" -ForegroundColor Red
    Write-Host "请以管理员身份执行: net start MySQL80" -ForegroundColor Yellow
    if (-not $NoPause) { Read-Host "按回车退出" }; exit 1
}
Write-Host "MySQL 3306 可达  OK" -ForegroundColor Green

if ($CheckOnly) {
    Write-Host "环境预检通过（$Mode 模式）；未启动或停止任何服务。" -ForegroundColor Green
    exit 0
}

if ($PublicDemo) {
    Write-Host "`n=== 构建公网演示 Vue 页面 ===" -ForegroundColor Cyan
    Push-Location $frontendDir
    try {
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw "Vue build failed." }
    } finally {
        Pop-Location
    }
}

# ===== 端口清理 =====
Write-Host "`n=== 端口检查 ===" -ForegroundColor Cyan
$portsToCheck = if ($PublicDemo) { @(8080, 8000) } else { @(8080, 8000, 5173) }
# 先确认全部占用者归属，再重启，避免只检查到一半便误停服务。
foreach ($port in $portsToCheck) {
    if (Test-TcpPort "127.0.0.1" $port) { Stop-Port $port -ValidateOnly }
}
foreach ($port in $portsToCheck) {
    if (-not (Test-TcpPort "127.0.0.1" $port)) {
        Write-Host "端口 $port 空闲" -ForegroundColor Green
        continue
    }
    Stop-Port $port
    Start-Sleep -Seconds 1
    if (Test-TcpPort "127.0.0.1" $port) {
        # 无法释放时停止，避免把旧服务误当成新服务。
        Write-Host "端口 $port 仍被占用，停止启动以避免误用旧服务。" -ForegroundColor Red
        Write-Host "请关闭占用端口的服务后重试。" -ForegroundColor Yellow
        exit 1
    } else {
        Write-Host "端口 $port 已释放" -ForegroundColor Green
    }
}

# 后台启动日志用于定位失败，不依赖可见终端。
$logDir = Join-Path $root ".runtime"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
function Start-ServiceProcess {
    param([string]$Name, [string]$Command, [string]$Directory)
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($Command))
    Start-Process powershell.exe -WindowStyle Hidden -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", $encoded) -WorkingDirectory $Directory -RedirectStandardOutput (Join-Path $logDir "$Name.out.log") -RedirectStandardError (Join-Path $logDir "$Name.err.log")
}

# ===== 启动 Java 后端 =====
Write-Host "`n=== 启动 Java 后端 (8080) ===" -ForegroundColor Cyan
$backendCmd = @'
$env:SPRING_PROFILES_ACTIVE='dev'
$Host.UI.RawUI.WindowTitle='OrderMate - Java 后端'
.\mvnw.cmd spring-boot:run
'@
Start-ServiceProcess "backend" $backendCmd $root

if (-not (Wait-ForUrl "Java 后端" "http://localhost:8080/api/products/search?keyword=phone" 180)) {
    Write-Host "Java 后端启动失败，请查看 .runtime/backend.err.log 和 backend.out.log。" -ForegroundColor Red
    if (-not $NoPause) { Read-Host "按回车退出" }; exit 1
}

# ===== 启动 Agent（auto 有 Key 时 live，无 Key 时 demo；不重放业务） =====
Write-Host "`n=== 启动 Agent (8000 / $Mode 模式) ===" -ForegroundColor Cyan
$agentHost = if ($PublicDemo) { "127.0.0.1" } else { "0.0.0.0" }
$agentCmd = @"
`$Host.UI.RawUI.WindowTitle='OrderMate - Agent'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host $agentHost --port 8000
"@
Start-ServiceProcess "agent" $agentCmd $agentDir

if (-not (Wait-ForUrl "Agent" "http://localhost:8000/health" 90)) {
    Write-Host "Agent 启动失败，请查看 .runtime/agent.err.log 和 agent.out.log。" -ForegroundColor Red
    if (-not $NoPause) { Read-Host "按回车退出" }; exit 1
}

# ===== 启动 Vue 前端 =====
if (-not $PublicDemo) {
    Write-Host "`n=== 启动 Vue 前端 (5173) ===" -ForegroundColor Cyan
    $vueCmd = '$Host.UI.RawUI.WindowTitle=''OrderMate - Vue''; npm.cmd run dev'
    Start-ServiceProcess "vue" $vueCmd $frontendDir

    if (-not (Wait-ForUrl "Vue 前端" "http://localhost:5173" 60)) {
        Write-Host "Vue 前端启动失败，请查看服务日志。" -ForegroundColor Red
        exit 1
    }
}

# ===== 完成 =====
Write-Host "`n=== 全部服务已启动 ===" -ForegroundColor Green
if ($PublicDemo) {
    Write-Host "Vue 演示入口: http://127.0.0.1:8000"
    Write-Host "仅本机访问；确认本地验收通过后再单独启动 ngrok。"
} else {
    Write-Host "Vue 前端:  http://localhost:5173"
}
Write-Host "Agent:     http://localhost:8000/health"
Write-Host "运行模式:  $Mode（auto=有模型 Key 使用 live，无 Key 使用 demo；业务异常不重放）"
Write-Host "后端:      http://localhost:8080/api"
if ($PublicDemo) {
    Write-Host "允许的演示账号: $env:DEMO_ALLOWED_USERS；正常用户权限；取消订单、清空购物车等操作需要二次确认。"
} else {
    Write-Host "演示账号:  testuser / password"
}
Write-Host "`n服务在后台运行，日志位于 .runtime；停止服务时请只结束属于本项目的后台进程。公网模式还需关闭 ngrok 窗口。"
if (-not $NoBrowser) {
    Write-Host "正在打开浏览器…" -ForegroundColor Cyan
    $openUrl = if ($PublicDemo) { "http://127.0.0.1:8000" } else { "http://localhost:5173" }
    try { Start-Process $openUrl } catch {}
}
if (-not $NoPause) {
    Write-Host ""
    Read-Host "按回车关闭本窗口（后台服务继续运行）"
}
