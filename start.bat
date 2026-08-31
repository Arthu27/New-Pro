@echo off
chcp 65001 >nul 2>&1
title Hakumo Bot
cd /d "%~dp0"

echo ============================================================
echo   HAKUMO BOT - Starting...
echo ============================================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found!
    echo Install Python from https://python.org
    echo Make sure to check "Add Python to PATH"
    pause
    exit /b 1
)

:: Install dependencies
echo [1/3] Installing dependencies...
pip install -r requirements.txt --quiet 2>nul
if errorlevel 1 (
    echo [WARN] Some packages failed, trying with --pre...
    pip install -r requirements.txt --pre --quiet 2>nul
)
echo [OK] Dependencies installed
echo.

:: Check .env
echo [2/3] Checking configuration...
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo [WARN] .env created from .env.example
        echo Please fill in TOKEN and other settings in .env
        echo.
        notepad ".env"
        echo After filling .env, run start.bat again
        pause
        exit /b 0
    ) else (
        echo [ERROR] .env not found!
        pause
        exit /b 1
    )
)
echo [OK] Configuration found
echo.

:: FFmpeg (нужен музыке /play): если нет — скачается/установится сам
echo [FFmpeg] Checking ffmpeg...
if exist "scripts\ensure_ffmpeg.bat" (
    call "scripts\ensure_ffmpeg.bat"
) else (
    where ffmpeg >nul 2>&1 || echo [FFmpeg] WARN: ffmpeg not found and installer script missing - music (/play) will not work
)
echo.

:: Start bot
echo [3/3] Starting bot...
echo ============================================================
echo.
python -X utf8 main.py

:: If bot crashed
echo.
echo ============================================================
echo [ERROR] Bot stopped!
echo ============================================================
pause
