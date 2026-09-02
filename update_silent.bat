@echo off
chcp 65001 >nul 2>&1
title Hakumo Updater
cd /d "%~dp0"

rem ==================================================================
rem  Hakumo SILENT Updater - запускается командой /update из бота.
rem
rem  Отличие от update.bat: БЕЗ пауз (бот не может нажать клавишу),
rem  окно поднимается отдельной НОВОЙ консолью, старый процесс бота
rem  гасится (его консоль закрывается), затем код обновляется через
rem  git (с запасным путём - zip) и бот стартует в новой консоли.
rem  data\, .env, .venv, .git не трогаются.
rem
rem  Аргументы:  update_silent.bat  <OLD_PID>  <branch>
rem ==================================================================

set "OLD_PID=%~1"
set "BRANCH=%~2"
if "%BRANCH%"=="" set "BRANCH=main"

echo ============================================================
echo   HAKUMO - ОБНОВЛЕНИЕ
echo   Каталог: %CD%
echo   Ветка:  %BRANCH%
echo ============================================================
echo.

rem --- 1. Гасим старый процесс бота (его консоль закроется) ---------
if not "%OLD_PID%"=="" (
    echo [1/4] Останавливаю текущий процесс бота (PID %OLD_PID%)...
    taskkill /PID %OLD_PID% /T /F >nul 2>&1
)
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe' or Name='pythonw.exe'\" | Where-Object { $_.CommandLine -match 'main\.py' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1
timeout /t 2 /nobreak >nul

rem --- 2. Обновляем код: git (дельты), при неудаче - zip -----------
echo [2/4] Обновляю код (git -> запасной архив)...
python -c "import sys,os;sys.path.insert(0,os.getcwd());from services import self_update as SU;b=os.getcwd();ok,err,info=SU.git_update(b,'%BRANCH%');print('  git:',('обновлено' if ok else 'не вышел'),err or '');sys.exit(0 if ok else 1)"
if errorlevel 1 (
    echo   git не сработал - качаю архив ветки...
    call update.bat /norestart
)

rem --- 3. Зависимости (тихо) ---------------------------------------
echo [3/4] Проверяю зависимости...
if exist requirements.txt python -m pip install -r requirements.txt --quiet --disable-pip-version-check

rem --- 4. Запускаю бота в НОВОЙ консоли ----------------------------
echo [4/4] Запускаю свежую версию в новом окне...
if exist start_bot.bat (
    start "Hakumo Bot" cmd /k start_bot.bat
) else (
    start "Hakumo Bot" cmd /k python main.py
)

timeout /t 3 /nobreak >nul
echo.
echo Готово - бот поднимается в новом окне. Это окно закроется.
timeout /t 2 /nobreak >nul
exit /b 0
