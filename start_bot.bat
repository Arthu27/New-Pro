@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title Hakumo Bot

echo ============================================================
echo   HAKUMO BOT — то же, что start.bat (main + Event)
echo ============================================================
echo.
echo Перенаправляю на start.bat (единая точка запуска всех ботов)...
echo.
call "%~dp0start.bat"
exit /b %ERRORLEVEL%
