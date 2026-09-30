#Requires -Version 5.1
# 停止开发验收环境：按端口结束 Java(8080)、Agent(8000)、Vue(5173) 进程
# 双击「一键停止Vue.bat」运行。
#
# 已修复的问题：
#  1) 本文件必须存为 UTF-8 with BOM，否则 Windows PowerShell 5.1 按 GBK 解码中文会出错。
#  2) 循环变量不能叫 $pid —— $PID 是只读自动变量，赋值会抛异常，
#     而本脚本原先设了 SilentlyContinue，所以会「静默地一个进程都杀不掉」。

$ErrorActionPreference = "SilentlyContinue"

[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
try { chcp 65001 > $null } catch {}

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

$ports = @(8080, 8000, 5173)
foreach ($port in $ports) {
    $pids = Get-PidsByPort $port
    if ($pids.Count -eq 0) {
        Write-Host "端口 $port 无进程" -ForegroundColor Gray
        continue
    }
    Write-Host "停止端口 $port 进程: $($pids -join ', ')" -ForegroundColor Yellow
    foreach ($procId in $pids) {
        try {
            Stop-Process -Id $procId -Force -ErrorAction Stop
            Write-Host "  已停止 PID $procId" -ForegroundColor Green
        } catch {
            Write-Host "  停止 PID $procId 失败: $($_.Exception.Message)" -ForegroundColor Red
        }
    }
}

Write-Host "`n完成。" -ForegroundColor Green
Start-Sleep -Seconds 2
