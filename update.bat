@echo off
rem ═══════════════════════════════════════════════════════════════════
rem  Hakumo Updater — обновление бота в один двойной клик.
rem
rem  Откуда качает: ПОСТОЯННАЯ ссылка «последний релиз» на GitHub —
rem  она не меняется от чата к чату. Если релизов нет — запасной путь:
rem  ветка, прописанная ниже (BRANCH).
rem
rem  Что делает:
rem    1. Скачивает свежую сборку ветки arena/019fee4a-new-pro с GitHub
rem    2. Распаковывает во временную папку
rem    3. Аккуратно докладывает код поверх текущей папки.
rem       НЕ ТРОГАЕТ: .env, data\ (база, настройки, логи), .venv, .git —
rem       твои данные в безопасности, чистится только код.
rem    4. Ставит зависимости из requirements.txt (если изменились).
rem    5. Перезапускает бота (старую копию main.py гасит точечно).
rem
rem  Запуск: двойной клик по update.bat
rem  Без перезапуска: update.bat /norestart
rem ═══════════════════════════════════════════════════════════════════
chcp 65001 >nul
setlocal EnableDelayedExpansion
title Hakumo Updater
cd /d "%~dp0"

set "REPO=Arthu27/New-Pro"
set "BRANCH=arena/01a03640-new-pro"
set "URL=https://codeload.github.com/%REPO%/zip/refs/heads/%BRANCH%"
set "TMPZ=%TEMP%\hakumo_update.zip"
set "TMPSRC=%TEMP%\hakumo_update_src"
set "SRC="
set "TMPURL=%TEMP%\hakumo_update_url.txt"

rem Постоянный источник: последний релиз (ссылка не зависит от ветки)
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol=[Enum]::ToObject([Net.SecurityProtocolType],3072); try { $r=Invoke-RestMethod 'https://api.github.com/repos/%REPO%/releases/latest'; if ($r.zipball_url) { $r.zipball_url | Out-File -Encoding ascii '%TMPURL%' } else { exit 1 } } catch { exit 1 }" >nul 2>nul
if exist "%TMPURL%" (
    for /f "usebackq delims=" %%U in ("%TMPURL%") do if not "%%U"=="" set "URL=%%U"
    del "%TMPURL%" >nul 2>nul
)
if "%URL%"=="https://codeload.github.com/%REPO%/zip/refs/heads/%BRANCH%" (
    echo   Источник: ветка %BRANCH% ^(релизов пока нет^)
) else (
    echo   Источник: последний релиз ^(постоянная ссылка^)
)

echo ════════════════════════════════════════════════════════════
echo   Hakumo Updater
echo   Ветка: %BRANCH%
echo   Папка бота: %CD%
echo ════════════════════════════════════════════════════════════
echo.

if not exist main.py (
    echo [ОШИБКА] main.py не найден — запусти update.bat из папки бота.
    goto :end
)

echo [1/5] Скачиваю свежую сборку с GitHub...
rem Старый PowerShell не договаривается с GitHub по TLS 1.2 («SSL/TLS channel»):
rem сначала пробуем curl.exe (есть в Windows 10 / Server 2019+), иначе PowerShell
rem с принудительным TLS 1.2 (3072).
where curl.exe >nul 2>nul
if not errorlevel 1 (
    curl.exe -L --fail --silent --show-error -o "%TMPZ%" "%URL%"
    if errorlevel 1 goto :fail_download
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol=[Enum]::ToObject([Net.SecurityProtocolType],3072); $ProgressPreference='SilentlyContinue'; try { Invoke-WebRequest -Uri '%URL%' -OutFile '%TMPZ%' -UseBasicParsing; exit 0 } catch { Write-Host $_.Exception.Message; exit 1 }"
    if errorlevel 1 goto :fail_download
)

echo [2/5] Распаковываю...
if exist "%TMPSRC%" rmdir /s /q "%TMPSRC%"
mkdir "%TMPSRC%" >nul 2>nul
where tar.exe >nul 2>nul
if not errorlevel 1 (
    tar.exe -xf "%TMPZ%" -C "%TMPSRC%"
    if errorlevel 1 goto :fail_download
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Expand-Archive -Path '%TMPZ%' -DestinationPath '%TMPSRC%' -Force; exit 0 } catch { Write-Host $_.Exception.Message; exit 1 }"
    if errorlevel 1 goto :fail_download
)
for /d %%D in ("%TMPSRC%\*") do if not defined SRC set "SRC=%%D"
if not defined SRC (
    echo [ОШИБКА] В архиве нет ожидаемой папки — отмена.
    goto :fail_download
)

echo [3/5] Обновляю код (данные, .env и логи не трогаю)...
robocopy "%SRC%" "." /E /XD data .git .venv __pycache__ logs /XF .env update.bat /NFL /NDL /NJH /R:2 /W:2 >nul
if errorlevel 8 goto :fail_copy

echo [4/5] Проверяю зависимости...
if exist requirements.txt (
    python -m pip install -r requirements.txt --quiet --disable-pip-version-check
    if errorlevel 1 echo [ПРЕДУПРЕЖДЕНИЕ] pip завершился с ошибкой — смотри вывод выше.
)

if /i "%~1"=="/norestart" (
    echo [5/5] Готово. Перезапуск пропущен (передан /norestart).
    goto :ok
)

echo [5/5] Перезапускаю бота...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe' or Name='pythonw.exe'\" | Where-Object { $_.CommandLine -match 'main\.py' } | ForEach-Object { Write-Host ('  Останавливаю PID ' + $_.ProcessId); Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
timeout /t 2 /nobreak >nul
start "Hakumo Bot" cmd /k python main.py

:ok
echo.
echo ════════════════════════════════════════════════════════════
echo   Обновление завершено. Маркер свежего кода при старте:
echo   «Слеш-меню: NN команд (лимит Discord — 100...)»
echo ════════════════════════════════════════════════════════════
goto :end

:fail_download
echo.
echo [ОШИБКА] Не удалось скачать/распаковать сборку.
echo Проверь интернет и что GitHub доступен. Локальные файлы не тронуты.
echo Если снова про SSL/TLS — скачай файл вручную в браузере и положи рядом:
echo   https://github.com/Arthu27/New-Pro/raw/latest/update.bat
goto :end

:fail_copy
echo.
echo [ОШИБКА] Robocopy вернул ошибку при копировании файлов.
echo Твои .env и data\ не пострадали. Повтори запуск от имени пользователя с правами на эту папку.

:end
echo.
pause
endlocal
