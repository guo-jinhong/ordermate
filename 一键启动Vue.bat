@echo off
chcp 65001 >nul 2>&1
title OrderMate Vue 开发环境 - 一键启动
cd /d "%~dp0"

echo.
echo ========================================
echo    OrderMate Vue 开发环境 - 一键启动
echo ========================================
echo.
echo  将依次启动：
echo    1. Java 后端   http://localhost:8080/api
echo    2. Agent 服务  http://localhost:8000/health  (auto: 有 Key 使用 live，无 Key 使用 demo)
echo    3. Vue 前端    http://localhost:5173
echo.
echo  首次启动约需 1-2 分钟，请耐心等待。
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-dev-stack.ps1"
if errorlevel 1 goto failed
exit /b 0

:failed
pause >nul
exit /b 1
