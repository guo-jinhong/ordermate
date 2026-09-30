#Requires -Version 5.1
# 一键启动开发验收环境：Java 后端(8080) + Agent(8000/auto) + Vue(5173)
# 双击「一键启动Vue.bat」运行；本窗口关闭后，三个服务窗口继续运行。
#
# 已修复的问题：
#  1) 本文件必须存为 UTF-8 with BOM。否则 Windows PowerShell 5.1 会按 GBK 解码中文，
#     导致语法错误（Missing closing '}' 等），双击直接报错。
#  2) foreach 的循环变量名不能叫 $pid —— $PID 是只读自动变量，赋值会抛异常。
#  3) 就绪探测不再把 4xx 当失败：服务已启动但接口要求鉴权时（401/403）也算就绪。
#  4) 启动后端前先确认 MySQL 3306 可达，避免白等 150 秒。

param(
    [ValidateSet("auto", "live", "demo")]
    [string]$Mode = "auto",
    [switch]$NoBrowser,
    [switch]$NoPause
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

Import-DotEnv (Join-Path $root ".env")
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
    $connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    foreach ($conn in $connections) {
        if ($conn.OwningProcess -and $conn.OwningProcess -ne 0) {
            $found += $conn.OwningProcess
        }
    }
    return @($found | Sort-Object -Unique)
}

function Stop-Port {
    param([int]$Port)
    $pids = Get-PidsByPort $Port
    if ($pids.Count -eq 0) { return }
    Write-Host "端口 $Port 被占用，正在结束进程: $($pids -join ', ')" -ForegroundColor Yellow
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
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                Write-Host "$Name 已就绪。" -ForegroundColor Green
                return $true
            }
        } catch {
            # Invoke-WebRequest 在非 2xx 时会抛异常；服务其实已经起来了，
            # 只要能拿到 HTTP 状态码就说明端口在正常响应。
            $webResponse = $_.Exception.Response
            if ($webResponse -ne $null) {
                $code = [int]$webResponse.StatusCode
                if ($code -ge 200 -and $code -lt 500) {
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
    Read-Host "按回车退出"; exit 1
}
if (-not (Test-Path (Join-Path $agentDir ".venv\Scripts\python.exe"))) {
    Write-Host "找不到 agent-service\.venv\Scripts\python.exe，请先创建 Python 虚拟环境。" -ForegroundColor Red
    Read-Host "按回车退出"; exit 1
}
if (-not (Test-Path (Join-Path $frontendDir "package.json"))) {
    Write-Host "找不到 frontend\package.json。" -ForegroundColor Red
    Read-Host "按回车退出"; exit 1
}
if (-not (Test-Path (Join-Path $frontendDir "node_modules"))) {
    Write-Host "frontend\node_modules 不存在，请先在 frontend 目录执行 npm install。" -ForegroundColor Red
    Read-Host "按回车退出"; exit 1
}

$javaMajor = Get-JavaMajorVersion
if ($javaMajor -eq 0) {
    Write-Host "未找到 java，请安装 JDK 17 并设置 JAVA_HOME。" -ForegroundColor Red
    Read-Host "按回车退出"; exit 1
} elseif ($javaMajor -eq -1) {
    Write-Host "无法检测 Java 版本（已跳过检查）；若版本过低，后端窗口会直接报错。" -ForegroundColor Yellow
} elseif ($javaMajor -lt 17) {
    Write-Host "需要 Java 17+，当前 Java $javaMajor。请安装 JDK 17 并设置 JAVA_HOME。" -ForegroundColor Red
    Read-Host "按回车退出"; exit 1
} else {
    Write-Host "Java $javaMajor  OK" -ForegroundColor Green
}

# ===== MySQL 检查 =====
Write-Host "`n=== 检查 MySQL (3306) ===" -ForegroundColor Cyan
if (-not (Test-TcpPort "127.0.0.1" 3306)) {
    Write-Host "MySQL 3306 不可达，尝试启动 MySQL80 服务…" -ForegroundColor Yellow
    try { Start-Service MySQL80 -ErrorAction Stop } catch {
        Write-Host "自动启动失败（可能需要管理员权限）。" -ForegroundColor Yellow
    }
    Start-Sleep -Seconds 5
}
if (-not (Test-TcpPort "127.0.0.1" 3306)) {
    Write-Host "MySQL 3306 仍不可达。后端依赖数据库，无法继续。" -ForegroundColor Red
    Write-Host "请以管理员身份执行: net start MySQL80" -ForegroundColor Yellow
    Read-Host "按回车退出"; exit 1
}
Write-Host "MySQL 3306 可达  OK" -ForegroundColor Green

# ===== 端口清理 =====
Write-Host "`n=== 端口检查 ===" -ForegroundColor Cyan
foreach ($port in @(8080, 8000, 5173)) {
    if (-not (Test-TcpPort "127.0.0.1" $port)) {
        Write-Host "端口 $port 空闲" -ForegroundColor Green
        continue
    }
    Stop-Port $port
    Start-Sleep -Seconds 1
    if (Test-TcpPort "127.0.0.1" $port) {
        # 只警告不中断：个别环境下端口探测可能误报，中断会挡住本来能正常启动的流程。
        Write-Host "警告：端口 $port 似乎仍被占用，新服务可能绑定失败。" -ForegroundColor Yellow
        Write-Host "如后续步骤超时，请手动结束该端口对应进程，或双击「一键停止Vue.bat」。" -ForegroundColor Yellow
    } else {
        Write-Host "端口 $port 已释放" -ForegroundColor Green
    }
}

# ===== 启动 Java 后端 =====
Write-Host "`n=== 启动 Java 后端 (8080) ===" -ForegroundColor Cyan
$backendCmd = @'
$env:SPRING_PROFILES_ACTIVE='dev'
$Host.UI.RawUI.WindowTitle='OrderMate - Java 后端'
.\mvnw.cmd spring-boot:run
'@
Start-Process powershell.exe -ArgumentList @("-NoExit", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $backendCmd) -WorkingDirectory $root

if (-not (Wait-ForUrl "Java 后端" "http://localhost:8080/api/products/search?keyword=phone" 180)) {
    Write-Host "Java 后端启动失败，请查看「Java 后端」窗口的日志。" -ForegroundColor Red
    Read-Host "按回车退出"; exit 1
}

# ===== 启动 Agent（auto 默认优先 live，异常时请求级降级 demo） =====
Write-Host "`n=== 启动 Agent (8000 / $Mode 模式) ===" -ForegroundColor Cyan
$agentCmd = @'
$Host.UI.RawUI.WindowTitle='OrderMate - Agent'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
'@
Start-Process powershell.exe -ArgumentList @("-NoExit", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $agentCmd) -WorkingDirectory $agentDir

if (-not (Wait-ForUrl "Agent" "http://localhost:8000/health" 90)) {
    Write-Host "Agent 启动失败，请查看「Agent」窗口的日志。" -ForegroundColor Red
    Read-Host "按回车退出"; exit 1
}

# ===== 启动 Vue 前端 =====
Write-Host "`n=== 启动 Vue 前端 (5173) ===" -ForegroundColor Cyan
$vueCmd = '$Host.UI.RawUI.WindowTitle=''OrderMate - Vue''; npm.cmd run dev'
Start-Process powershell.exe -ArgumentList @("-NoExit", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $vueCmd) -WorkingDirectory $frontendDir

if (-not (Wait-ForUrl "Vue 前端" "http://localhost:5173" 60)) {
    Write-Host "Vue 前端可能仍在启动，请稍候手动访问 http://localhost:5173" -ForegroundColor Yellow
}

# ===== 完成 =====
Write-Host "`n=== 全部服务已启动 ===" -ForegroundColor Green
Write-Host "Vue 前端:  http://localhost:5173"
Write-Host "Agent:     http://localhost:8000/health"
Write-Host "运行模式:  $Mode（auto=优先 live，失败降级 demo）"
Write-Host "后端:      http://localhost:8080/api"
Write-Host "演示账号:  testuser / password"
Write-Host "`n停止服务：双击「一键停止Vue.bat」，或直接关掉三个服务窗口。"
if (-not $NoBrowser) {
    Write-Host "正在打开浏览器…" -ForegroundColor Cyan
    try { Start-Process "http://localhost:5173" } catch {}
}
if (-not $NoPause) {
    Write-Host ""
    Read-Host "按回车关闭本窗口（三个服务窗口继续运行）"
}
