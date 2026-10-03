@echo off
chcp 65001 >nul 2>&1
title OrderMate Public Demo
cd /d "%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-ngrok-tunnel.ps1" -CheckOnly
if errorlevel 1 goto failed

echo.
echo Starting OrderMate public demo locally...
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-dev-stack.ps1" -PublicDemo -NoBrowser -NoPause
if errorlevel 1 goto failed

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-ngrok-tunnel.ps1"
if errorlevel 1 goto failed

echo.
echo Local services remain running. Service logs are in .runtime. Close ngrok to stop public access.
pause
exit /b 0

:failed
echo.
echo Public demo startup failed. Check the messages above.
pause
exit /b 1
