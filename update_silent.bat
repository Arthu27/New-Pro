@echo off
chcp 65001 >nul 2>&1
title Hakumo Updater
cd /d "%~dp0"

rem ==================================================================
rem  Hakumo SILENT Updater - запускается командой /update из бота.
rem
rem  Порядок ВАЖЕН: сначала гасим старый процесс, потом обновляем код,
rem  и только в конце поднимаем бота заново. Бот перезапускается ВСЕГДА -
rem  даже если обновление не удалось, иначе владелец остаётся без бота.
rem
rem  Метку data\.updating ставит бот перед запуском этого файла: она не
rem  даёт старому start_bot.bat воскресить процесс посреди замены кода.
rem  Снимаем метку прямо перед стартом свежей версии.
rem
rem  data\, .env, .venv, .git не трогаются.
rem
rem  Аргументы:  update_silent.bat  <OLD_PID>  <branch>
rem ==================================================================

set "OLD_PID=%~1"
set "BRANCH=%~2"
if "%BRANCH%"=="" set "BRANCH=main"
set "FAILED="

echo ============================================================
echo   HAKUMO - ОБНОВЛЕНИЕ
echo   Каталог: %CD%
echo   Ветка:  %BRANCH%
echo ============================================================
echo.

rem --- 1. Гасим старый процесс бота ---------------------------------
rem БЕЗ /T. Обновлятор запущен из процесса бота и в первые секунды висит
rem в том же дереве: taskkill /T глушил это самое окно, обновление
rem обрывалось на первом шаге, а бот уже был мёртв.
if not "%OLD_PID%"=="" (
    echo [1/4] Останавливаю текущий процесс бота (PID %OLD_PID%)...
    taskkill /PID %OLD_PID% /F >nul 2>&1
)
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe' or Name='pythonw.exe'\" | Where-Object { $_.CommandLine -match 'main\.py' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1

rem Ждём, пока процесс действительно отпустит файлы (до 20 секунд):
rem замена кода по занятым файлам молча не получалась.
set /a WAITED=0
:waitdead
if "%OLD_PID%"=="" goto waitdone
tasklist /FI "PID eq %OLD_PID%" 2>nul | find /I "python" >nul
if errorlevel 1 goto waitdone
set /a WAITED+=1
if %WAITED% GEQ 20 goto waitdone
timeout /t 1 /nobreak >nul
goto waitdead
:waitdone
echo   Процесс остановлен, файлы свободны.

rem --- 2. Обновляем код ---------------------------------------------
rem Основной путь: бот УЖЕ скачал и проверил архив до выключения (заказ
rem владельца - не гаснуть, пока новая версия не скачана). Тогда просто
rem применяем готовое. Запасной - git, потом скачивание самим: он нужен
rem для ручного запуска update_silent.bat / update.bat, когда бот архив
rem не готовил.
if exist "data\.update_pending.zip" (
    echo [2/4] Применяю архив, который бот скачал до перезапуска...
    python "scripts\silent_zip_update.py" --pending %BRANCH%
    if errorlevel 1 set "FAILED=готовый архив не применился"
    goto deps
)
echo [2/4] Готового архива нет - обновляю код (git -> запасной архив)...
python -c "import sys,os;sys.path.insert(0,os.getcwd());from services import self_update as SU;b=os.getcwd();ok,err,info=SU.git_update(b,'%BRANCH%');print('  git:',('обновлено' if ok else 'не вышел'),err or '');sys.exit(0 if ok else 1)"
if errorlevel 1 (
    echo   git не сработал - качаю архив ветки и кладу только изменённое...
    python "scripts\silent_zip_update.py" %BRANCH%
    if errorlevel 1 set "FAILED=код не обновился - ни git, ни архив не сработали"
)
:deps

rem --- 3. Зависимости (тихо) ---------------------------------------
echo [3/4] Проверяю зависимости...
if exist requirements.txt python -m pip install -r requirements.txt --quiet --disable-pip-version-check

rem --- 4. Поднимаю бота заново - ВСЕГДА ----------------------------
rem Метку снимаем ДО старта: иначе start_bot.bat решит, что обновление
rem ещё идёт, и не поднимет процесс.
if exist "data\.updating" del /q "data\.updating" >nul 2>&1
echo [4/4] Запускаю свежую версию в новом окне...
if exist start_bot.bat (
    start "Hakumo Bot" cmd /k start_bot.bat
) else (
    start "Hakumo Bot" cmd /k python main.py
)

echo.
if not "%FAILED%"=="" (
    echo ВНИМАНИЕ: %FAILED%.
    echo Бот всё равно запущен на том коде, что есть сейчас.
    echo Это окно останется открытым - прочитайте ошибку выше.
    exit /b 1
)
echo Готово - бот поднимается в новом окне и отчитается в Discord.
echo Это окно закроется через 5 секунд.
timeout /t 5 /nobreak >nul
exit /b 0
