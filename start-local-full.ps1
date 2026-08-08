param(
    [string]$MySqlHost = "127.0.0.1",
    [int]$MySqlPort = 3306,
    [string]$MySqlUser = "root",
    [string]$MySqlPassword = "123456",
    [string]$BackendDatabase = "ecommerce_db",
    [string]$AgentDatabase = "ecommerce_db",
    [string]$AgentMySqlUser = "agent_user",
    [string]$AgentMySqlPassword = "agent_readonly_123456",
    [int]$BackendPort = 8080,
    [int]$AgentPort = 18000,
    [switch]$NoDockerMySql,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
try {
    chcp 65001 *> $null
} catch {
    # chcp is only available on Windows consoles; ignore when unavailable.
}

$root = (Resolve-Path ".").Path
$agentDir = Join-Path $root "agent-service"
$runDir = Join-Path $root ".run"
$backendPidFile = Join-Path $runDir "backend.pid"
$agentPidFile = Join-Path $runDir "agent.pid"
$backendLog = Join-Path $runDir "backend.log"
$agentLog = Join-Path $runDir "agent.log"
$backendSchemaSql = Join-Path $root "src\main\resources\sql\schema.sql"
$backendDataSql = Join-Path $root "src\main\resources\sql\data.sql"
$agentKnowledgeSql = Join-Path $agentDir "sql\setup_single_database.sql"
$enhanceBusinessSql = Join-Path $agentDir "sql\enhance_business_demo_data.sql"
$envFile = Join-Path $root ".env"

New-Item -ItemType Directory -Force -Path $runDir | Out-Null

function Import-DotEnv {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }
    foreach ($line in Get-Content -Encoding UTF8 -Path $Path) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#") -or -not $trimmed.Contains("=")) {
            continue
        }
        $name, $value = $trimmed.Split("=", 2)
        $name = $name.Trim()
        $value = $value.Trim().Trim('"').Trim("'")
        if ($name) {
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
}

function Test-TcpPort {
    param([string]$HostName, [int]$Port)
    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        $async = $client.BeginConnect($HostName, $Port, $null, $null)
        $ok = $async.AsyncWaitHandle.WaitOne(1000)
        if ($ok) { $client.EndConnect($async) }
        $client.Close()
        return $ok
    } catch {
        return $false
    }
}

function Test-HttpOk {
    param([string]$Url)
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
        return ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500)
    } catch {
        return $false
    }
}

function Wait-ForUrl {
    param([string]$Name, [string]$Url, [int]$Seconds = 90)
    Write-Host "Waiting for ${Name}: $Url"
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-HttpOk $Url) {
            Write-Host "$Name is ready." -ForegroundColor Green
            return $true
        }
        Start-Sleep -Seconds 2
    }
    Write-Host "$Name did not become ready in $Seconds seconds." -ForegroundColor Yellow
    return $false
}

function Wait-ForTcpPort {
    param([string]$Name, [string]$HostName, [int]$Port, [int]$Seconds = 45)
    Write-Host "Waiting for ${Name}: ${HostName}:${Port}"
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-TcpPort $HostName $Port) {
            Write-Host "$Name is reachable." -ForegroundColor Green
            return $true
        }
        Start-Sleep -Seconds 2
    }
    Write-Host "$Name did not become reachable in $Seconds seconds." -ForegroundColor Yellow
    return $false
}

function Find-DockerExe {
    $dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
    if ($dockerCommand) {
        return $dockerCommand.Source
    }
    $knownPaths = @(
        "D:\Docker\resources\bin\docker.exe",
        "C:\Program Files\Docker\Docker\resources\bin\docker.exe"
    )
    foreach ($path in $knownPaths) {
        if (Test-Path -LiteralPath $path) {
            return $path
        }
    }
    return $null
}

function Invoke-Compose {
    param(
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$ComposeArgs
    )
    if (-not $script:dockerExe) {
        throw "docker.exe was not found."
    }
    & $script:dockerExe compose version *> $null
    if ($LASTEXITCODE -eq 0) {
        & $script:dockerExe compose @ComposeArgs
        return
    }
    $dockerComposeCommand = Get-Command docker-compose -ErrorAction SilentlyContinue
    if ($dockerComposeCommand) {
        & $dockerComposeCommand.Source @ComposeArgs
        return
    }
    throw "Docker Compose was not found."
}

function Start-WindowsMySqlService {
    $services = Get-Service -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -match '^mysql' -or
            $_.DisplayName -match 'MySQL'
        } |
        Sort-Object Status, Name
    foreach ($service in $services) {
        if ($service.Status -eq "Running") {
            continue
        }
        try {
            Write-Host "Trying to start Windows service '$($service.Name)'..."
            Start-Service -Name $service.Name -ErrorAction Stop
            if (Wait-ForTcpPort "MySQL service $($service.Name)" $MySqlHost $MySqlPort 30) {
                return $true
            }
        } catch {
            Write-Host "Could not start service '$($service.Name)': $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }
    return (Test-TcpPort $MySqlHost $MySqlPort)
}

function Find-MySqlExe {
    $command = Get-Command mysql -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }
    $knownPaths = @(
        "C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe",
        "C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe",
        "C:\Program Files (x86)\MySQL\MySQL Server 8.0\bin\mysql.exe"
    )
    foreach ($path in $knownPaths) {
        if (Test-Path -LiteralPath $path) {
            return $path
        }
    }
    return $null
}

function Invoke-MySql {
    param(
        [string]$Sql,
        [string]$Database = ""
    )
    if ($script:useDockerMySql) {
        $dockerArgs = @(
            "compose", "exec", "-T", "mysql",
            "mysql",
            "-h", "127.0.0.1",
            "-P", "3306",
            "-u", $MySqlUser,
            "-p$MySqlPassword",
            "--default-character-set=utf8mb4",
            "--batch",
            "--skip-column-names"
        )
        if ($Database) {
            $dockerArgs += @("-D", $Database)
        }
        $dockerArgs += @("-e", $Sql)
        & $script:dockerExe @dockerArgs
        if ($LASTEXITCODE -ne 0) {
            throw "docker mysql command failed: $Sql"
        }
        return
    }
    $args = @(
        "-h", $MySqlHost,
        "-P", "$MySqlPort",
        "-u", $MySqlUser,
        "-p$MySqlPassword",
        "--default-character-set=utf8mb4",
        "--batch",
        "--skip-column-names"
    )
    if ($Database) {
        $args += @("-D", $Database)
    }
    $args += @("-e", $Sql)
    & $script:mysqlExe @args
    if ($LASTEXITCODE -ne 0) {
        throw "mysql command failed: $Sql"
    }
}

function Invoke-MySqlFile {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "SQL file was not found: $Path"
    }
    if ($script:useDockerMySql) {
        Get-Content -Raw -Encoding UTF8 -Path $Path | & $script:dockerExe compose exec -T mysql mysql `
            -h 127.0.0.1 `
            -P 3306 `
            -u $MySqlUser `
            "-p$MySqlPassword" `
            --default-character-set=utf8mb4
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to run SQL file in Docker MySQL: $Path"
        }
        return
    }
    $args = @(
        "-h", $MySqlHost,
        "-P", "$MySqlPort",
        "-u", $MySqlUser,
        "-p$MySqlPassword",
        "--default-character-set=utf8mb4"
    )
    Get-Content -Raw -Encoding UTF8 -Path $Path | & $script:mysqlExe @args
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to run SQL file: $Path"
    }
}

function Ensure-BackendDatabase {
    if (-not $script:useDockerMySql) {
        $script:mysqlExe = Find-MySqlExe
    }
    if (-not $script:useDockerMySql -and -not $script:mysqlExe) {
        Write-Host "mysql.exe was not found. Create database '$BackendDatabase' manually or add MySQL bin to PATH." -ForegroundColor Red
        exit 1
    }

    Write-Host "Ensuring backend database '$BackendDatabase' exists..."
    Invoke-MySqlFile $backendSchemaSql

    $countOutput = Invoke-MySql "SELECT COUNT(*) FROM users;" $BackendDatabase
    $userCount = 0
    if ($countOutput) {
        $userCount = [int]($countOutput | Select-Object -Last 1)
    }
    if ($userCount -eq 0) {
        Write-Host "Seeding backend demo data..."
        Invoke-MySqlFile $backendDataSql
    } else {
        Write-Host "Backend demo data already exists ($userCount users)." -ForegroundColor Green
    }

    Write-Host "Ensuring Agent knowledge table and demo knowledge data..."
    Invoke-MySqlFile $agentKnowledgeSql

    Write-Host "Ensuring Function Calling business demo data..."
    Invoke-MySqlFile $enhanceBusinessSql

    Invoke-MySql "CREATE USER IF NOT EXISTS '$AgentMySqlUser'@'localhost' IDENTIFIED BY '$AgentMySqlPassword';"
    Invoke-MySql "CREATE USER IF NOT EXISTS '$AgentMySqlUser'@'%' IDENTIFIED BY '$AgentMySqlPassword';"
    Invoke-MySql "GRANT SELECT ON $AgentDatabase.knowledge TO '$AgentMySqlUser'@'localhost';"
    Invoke-MySql "GRANT SELECT ON $AgentDatabase.knowledge TO '$AgentMySqlUser'@'%';"
    Invoke-MySql "FLUSH PRIVILEGES;"

    try {
        $knowledgeCountOutput = Invoke-MySql "SELECT COUNT(*) FROM knowledge;" $AgentDatabase
        $knowledgeCount = 0
        if ($knowledgeCountOutput) {
            $knowledgeCount = [int]($knowledgeCountOutput | Select-Object -Last 1)
        }
        Write-Host "Knowledge rows in $AgentDatabase.knowledge: $knowledgeCount" -ForegroundColor Green
        if ($knowledgeCount -eq 0) {
            Write-Host "Run agent-service\sql\setup_single_database.sql once to seed knowledge data." -ForegroundColor Yellow
        }
    } catch {
        Write-Host "Knowledge table is missing. Run agent-service\sql\setup_single_database.sql once before starting Agent." -ForegroundColor Yellow
    }
}

function Get-JavaMajorVersion {
    $javaExe = $null
    if ($env:JAVA_HOME) {
        $candidate = Join-Path $env:JAVA_HOME "bin\java.exe"
        if (Test-Path -LiteralPath $candidate) {
            $javaExe = $candidate
        }
    }
    if (-not $javaExe) {
        $javaCommand = Get-Command java -ErrorAction SilentlyContinue
        if ($javaCommand) {
            $javaExe = $javaCommand.Source
        }
    }
    if (-not $javaExe) {
        return 0
    }
    $processInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $processInfo.FileName = $javaExe
    $processInfo.Arguments = "-version"
    $processInfo.RedirectStandardOutput = $true
    $processInfo.RedirectStandardError = $true
    $processInfo.UseShellExecute = $false
    $processInfo.CreateNoWindow = $true
    $process = [System.Diagnostics.Process]::Start($processInfo)
    $versionText = $process.StandardOutput.ReadToEnd() + $process.StandardError.ReadToEnd()
    $process.WaitForExit()
    if ($versionText -match 'version "1\.(\d+)') {
        return [int]$matches[1]
    }
    if ($versionText -match 'version "(\d+)') {
        return [int]$matches[1]
    }
    return 0
}

function Find-Jdk17Home {
    if ($env:JAVA_HOME) {
        $candidate = Join-Path $env:JAVA_HOME "bin\java.exe"
        if (Test-Path -LiteralPath $candidate) {
            $major = Get-JavaMajorVersion
            if ($major -ge 17) {
                return $env:JAVA_HOME
            }
        }
    }
    $roots = @(
        "C:\Program Files\Java",
        "C:\Program Files\Eclipse Adoptium",
        "C:\Program Files\Microsoft",
        "C:\Program Files\OpenJDK"
    )
    foreach ($rootPath in $roots) {
        if (-not (Test-Path -LiteralPath $rootPath)) {
            continue
        }
        $candidates = Get-ChildItem -LiteralPath $rootPath -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match '17|18|19|20|21|jdk' } |
            Sort-Object Name -Descending
        foreach ($candidateDir in $candidates) {
            $javaPath = Join-Path $candidateDir.FullName "bin\java.exe"
            if (-not (Test-Path -LiteralPath $javaPath)) {
                continue
            }
            $processInfo = [System.Diagnostics.ProcessStartInfo]::new()
            $processInfo.FileName = $javaPath
            $processInfo.Arguments = "-version"
            $processInfo.RedirectStandardOutput = $true
            $processInfo.RedirectStandardError = $true
            $processInfo.UseShellExecute = $false
            $processInfo.CreateNoWindow = $true
            $process = [System.Diagnostics.Process]::Start($processInfo)
            $versionText = $process.StandardOutput.ReadToEnd() + $process.StandardError.ReadToEnd()
            $process.WaitForExit()
            if ($versionText -match 'version "1\.(\d+)' -and [int]$matches[1] -ge 17) {
                return $candidateDir.FullName
            }
            if ($versionText -match 'version "(\d+)' -and [int]$matches[1] -ge 17) {
                return $candidateDir.FullName
            }
        }
    }
    return $null
}

if (-not (Test-Path -LiteralPath (Join-Path $root "mvnw.cmd"))) {
    throw "mvnw.cmd was not found. Run this script from the project root."
}
if (-not (Test-Path -LiteralPath (Join-Path $agentDir ".venv\Scripts\python.exe"))) {
    throw "Agent virtualenv was not found: agent-service\.venv\Scripts\python.exe"
}

$jdkHome = Find-Jdk17Home
if ($jdkHome) {
    $env:JAVA_HOME = $jdkHome
    $env:PATH = (Join-Path $jdkHome "bin") + ";" + $env:PATH
}

$javaMajor = Get-JavaMajorVersion
if ($javaMajor -lt 17) {
    Write-Host "Java 17+ is required to run the Spring Boot backend, but this machine is using Java $javaMajor or Java is not on PATH." -ForegroundColor Red
    Write-Host "Install JDK 17, set JAVA_HOME to the JDK 17 directory, reopen PowerShell, then run this script again." -ForegroundColor Red
    exit 1
}
Write-Host "Using JAVA_HOME=$env:JAVA_HOME"

if (-not (Test-TcpPort $MySqlHost $MySqlPort)) {
    Write-Host "MySQL is not reachable at ${MySqlHost}:${MySqlPort}. Trying to start a local MySQL service..." -ForegroundColor Yellow
    Start-WindowsMySqlService | Out-Null
}

$script:useDockerMySql = $false
$script:dockerExe = $null
if (-not (Test-TcpPort $MySqlHost $MySqlPort)) {
    if ($NoDockerMySql) {
        Write-Host "MySQL is not reachable at ${MySqlHost}:${MySqlPort}, and Docker fallback is disabled." -ForegroundColor Red
        exit 1
    }
    $script:dockerExe = Find-DockerExe
    if (-not $script:dockerExe) {
        Write-Host "MySQL is not reachable and Docker was not found." -ForegroundColor Red
        Write-Host "Start local MySQL first, or install/start Docker Desktop, then run this script again." -ForegroundColor Red
        exit 1
    }
    Write-Host "Starting Docker Compose MySQL fallback..."
    Invoke-Compose up -d mysql
    if ($MySqlPort -eq 3306) {
        $MySqlPort = 3307
    }
    $script:useDockerMySql = $true
    if (-not (Wait-ForTcpPort "Docker MySQL" $MySqlHost $MySqlPort 90)) {
        Write-Host "Docker MySQL did not become reachable on host port $MySqlPort." -ForegroundColor Red
        exit 1
    }
}

Import-DotEnv $envFile
Ensure-BackendDatabase

$backendUrl = "http://localhost:$BackendPort/api/products/search?keyword=phone"
$agentHealthUrl = "http://localhost:$AgentPort/health"
$agentHomeUrl = "http://localhost:$AgentPort"

if (Test-HttpOk $backendUrl) {
    Write-Host "Backend already appears to be running on port $BackendPort." -ForegroundColor Green
} else {
    Write-Host "Starting Spring Boot backend on port $BackendPort..."
    $backendCommand = @"
`$env:SPRING_PROFILES_ACTIVE='dev'
`$env:DB_URL='jdbc:mysql://$MySqlHost`:$MySqlPort/$BackendDatabase?useSSL=false&serverTimezone=UTC&allowPublicKeyRetrieval=true'
`$env:DB_USERNAME='$MySqlUser'
`$env:DB_PASSWORD='$MySqlPassword'
.\mvnw.cmd spring-boot:run *> '$backendLog'
"@
    $backendProcess = Start-Process -FilePath "powershell.exe" `
        -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $backendCommand) `
        -WorkingDirectory $root `
        -WindowStyle Hidden `
        -PassThru
    Set-Content -Path $backendPidFile -Value $backendProcess.Id
}

if (-not (Wait-ForUrl "Backend" $backendUrl 120)) {
    Write-Host "Backend log: $backendLog" -ForegroundColor Yellow
    exit 1
}

if (Test-HttpOk $agentHealthUrl) {
    Write-Host "Agent already appears to be running on port $AgentPort." -ForegroundColor Green
} else {
    Write-Host "Starting Agent on port $AgentPort..."
    $agentCommand = @"
`$env:ECOMMERCE_BACKEND='api'
`$env:ECOMMERCE_API_BASE_URL='http://localhost:$BackendPort/api'
`$env:DB_TYPE='mysql'
`$env:MYSQL_HOST='$MySqlHost'
`$env:MYSQL_PORT='$MySqlPort'
`$env:MYSQL_USER='$AgentMySqlUser'
`$env:MYSQL_PASSWORD='$AgentMySqlPassword'
`$env:MYSQL_DATABASE='$AgentDatabase'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port $AgentPort *> '$agentLog'
"@
    $agentProcess = Start-Process -FilePath "powershell.exe" `
        -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $agentCommand) `
        -WorkingDirectory $agentDir `
        -WindowStyle Hidden `
        -PassThru
    Set-Content -Path $agentPidFile -Value $agentProcess.Id
}

if (-not (Wait-ForUrl "Agent" $agentHealthUrl 60)) {
    Write-Host "Agent log: $agentLog" -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "Full local stack is ready." -ForegroundColor Green
Write-Host "Open: $agentHomeUrl"
Write-Host "Demo account: testuser / password"
Write-Host "Backend log: $backendLog"
Write-Host "Agent log: $agentLog"
Write-Host "Stop with: .\stop-local-full.ps1"

if (-not $NoBrowser) {
    Start-Process $agentHomeUrl
}
