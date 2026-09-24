@echo off
chcp 65001 >nul 2>&1
title Hakumo — все боты (start.bat)
cd /d "%~dp0"

echo ============================================================
echo   HAKUMO — запуск ВСЕХ ботов через start.bat
echo   Основной (модерация/панель) + Event (войсе-stay)
echo ============================================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found!
    echo Install Python 3.12 from https://python.org
    echo Make sure to check "Add Python to PATH"
    pause
    exit /b 1
)

:: Install dependencies (PyNaCl + davey нужны для войса Event-бота)
echo [1/4] Installing dependencies...
pip install -r requirements.txt --quiet 2>nul
if errorlevel 1 (
    echo [WARN] Some packages failed, trying with --pre...
    pip install -r requirements.txt --pre --quiet 2>nul
)
echo [OK] Dependencies installed
echo.

:: Check .env
echo [2/4] Checking configuration...
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo [WARN] .env created from .env.example
        echo Please fill in TOKEN= and optionally EVENT_BOT_TOKEN=
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

:: Detect which bots will start (TOKEN / EVENT_BOT_TOKEN)
set "HAS_MAIN=0"
set "HAS_EVENT=0"
findstr /B /C:"TOKEN=" ".env" >nul 2>&1 && set "HAS_MAIN=1"
findstr /B /C:"EVENT_BOT_TOKEN=" ".env" >nul 2>&1 && set "HAS_EVENT=1"
:: empty TOKEN= still counts as "line exists" — fine, main.py will fail clearly
echo.
echo [3/4] Bots to start:
if "%HAS_MAIN%"=="1" (
    echo   - MAIN   : TOKEN найден → основной бот
) else (
    echo   - MAIN   : TOKEN не найден в .env — добавь TOKEN=...
)
if "%HAS_EVENT%"=="1" (
    echo   - EVENT  : EVENT_BOT_TOKEN найден → войсе-stay
) else (
    echo   - EVENT  : EVENT_BOT_TOKEN пуст — Event-бот пропустится
    echo             (настрой в панели: Бот → Совместные боты)
)
echo.

if not exist "logs" mkdir "logs"

:: Авто-перезапуск: оба клиента живут в одном main.py
echo [4/4] Starting main.py (main + event in one process)...
echo ============================================================
echo Лог: logs\start_console.log
echo Остановка: Ctrl+C в этом окне
echo.

:runloop
python -c "import os,sys,time;p=os.path.join('data','.updating');sys.exit(0 if os.path.exists(p) and time.time()-os.path.getmtime(p)<900 else 1)" >nul 2>&1
if not errorlevel 1 (
    echo [UPDATE] Идёт обновление — не перезапускаем.
    exit /b 0
)
echo [%date% %time%] === start.bat: main + event === >> "logs\start_console.log"
python -X utf8 main.py >> "logs\start_console.log" 2>&1
set EXITCODE=%ERRORLEVEL%
echo [%date% %time%] stopped code %EXITCODE% >> "logs\start_console.log"
if "%EXITCODE%"=="7" (
    echo.
    echo [ERROR] Неверный TOKEN (код 7). Исправь .env — перезапуск не поможет.
    pause
    exit /b 7
)
echo.
echo [RESTART] Процесс упал (код %EXITCODE%) — через 5 сек снова...
timeout /t 5 /nobreak >nul
goto runloop
