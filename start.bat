@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion
title Aether Bot
cd /d "%~dp0"

echo ============================================================
echo   AETHER BOT - Starting...
echo ============================================================
echo.

:: ------------------------------------------------------------
:: 1) Python check
:: ------------------------------------------------------------
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found!
    echo Install Python from https://python.org
    echo Make sure to check "Add Python to PATH"
    pause
    exit /b 1
)

:: ------------------------------------------------------------
:: 2) ffmpeg check + auto-download if missing
::    Needed for music bot and !video-analiz
:: ------------------------------------------------------------
set "FFMPEG_BIN=ffmpeg-8.1-essentials_build\bin\ffmpeg.exe"
if exist "%FFMPEG_BIN%" (
    echo [OK] ffmpeg found
) else (
    echo [INFO] ffmpeg not found. Downloading...
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
        "try { Invoke-WebRequest -Uri 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip' -OutFile 'ffmpeg_tmp.zip' -UseBasicParsing; " ^
        "Expand-Archive -Path 'ffmpeg_tmp.zip' -DestinationPath 'ffmpeg_tmp' -Force } catch { exit 1 }" >nul 2>&1
    if errorlevel 1 (
        echo [WARN] Automatic ffmpeg download failed.
        echo        Install ffmpeg manually from https://ffmpeg.org/download.html
        echo        or place ffmpeg.exe in PATH.
    ) else (
        :: Find the extracted folder (ffmpeg-X.Y-essentials_build)
        for /d %%D in ("ffmpeg_tmp\ffmpeg-*-essentials_build") do (
            if exist "%%D\bin\ffmpeg.exe" (
                move /y "%%D" "ffmpeg-8.1-essentials_build" >nul 2>&1
            )
        )
        if exist "%FFMPEG_BIN%" (
            echo [OK] ffmpeg installed
        ) else (
            echo [WARN] ffmpeg extracted but not in expected path. Will use PATH version.
        )
    )
    :: Cleanup temp files
    del /q "ffmpeg_tmp.zip" >nul 2>&1
    rd /s /q "ffmpeg_tmp" >nul 2>&1
)

:: ------------------------------------------------------------
:: 3) cloudflared check (tunnel). main.py auto-downloads, but
::    we warn early if missing so the user knows.
:: ------------------------------------------------------------
if not exist "cloudflared.exe" (
    if exist "cloudflared_new.exe" (
        echo [OK] cloudflared found
    ) else (
        echo [INFO] cloudflared not found - the bot will download it automatically.
    )
) else (
    echo [OK] cloudflared found
)

:: ------------------------------------------------------------
:: 4) Install Python dependencies
:: ------------------------------------------------------------
echo [1/4] Installing dependencies...
pip install -r requirements.txt --quiet 2>nul
if errorlevel 1 (
    echo [WARN] Some packages failed, trying with --pre...
    pip install -r requirements.txt --pre --quiet 2>nul
)
echo [OK] Dependencies installed
echo.

:: ------------------------------------------------------------
:: 5) Check .env
:: ------------------------------------------------------------
echo [2/4] Checking configuration...
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

:: ------------------------------------------------------------
:: 6) Start bot
:: ------------------------------------------------------------
echo [3/4] Starting bot...
echo ============================================================
echo.
python main.py

:: If bot crashed
echo.
echo ============================================================
echo [ERROR] Bot stopped!
echo ============================================================
pause
