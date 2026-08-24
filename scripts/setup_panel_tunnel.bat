@echo off
rem ============================================================================
rem  Aether Panel — панель НА ГЛАВНОМ ДОМЕНЕ hakumods.xyz
rem  Открытие по: hakumods.xyz / www.hakumods.xyz / panel.hakumods.xyz
rem  Запуск: ПРАВЫЙ КЛИК -> "Запуск от имени администратора"
rem  Подробности: docs/PANEL-DOMAIN.md
rem ============================================================================
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title Aether Panel — домен hakumods.xyz

set TNAME=aether-panel
set PANEL_PORT=5001
set HOST1=hakumods.xyz
set HOST2=www.hakumods.xyz
set HOST3=panel.hakumods.xyz

echo.
echo  ==========================================================
echo   Aether Panel — панель на твоём домене
echo   %HOST1%  и  %HOST3%  =^>  http://localhost:%PANEL_PORT%
echo  ==========================================================
echo.
echo  Перед стартом убедись, что:
echo   1) hakumods.xyz добавлен в Cloudflare, статус "Active"
echo      (сайт-пустышка на хостинге больше не нужна — домен
echo       целиком показывает нашу панель)
echo   2) бот запущен (start.bat) и панель открывается на
echo      http://localhost:%PANEL_PORT%
echo.
pause

rem --- 1. cloudflared рядом со скриптом --------------------------------------
if not exist cloudflared.exe (
  echo.
  echo [1/6] Скачиваю cloudflared...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile 'cloudflared.exe'"
  if not exist cloudflared.exe (
    echo [ОШИБКА] Не удалось скачать cloudflared. Проверь интернет и повтори.
    pause & exit /b 1
  )
) else (
  echo [1/6] cloudflared.exe уже на месте
)

rem --- 2. вход в Cloudflare ---------------------------------------------------
echo.
echo [2/6] Вход в Cloudflare. Откроется браузер — выбери сайт hakumods.xyz
cloudflared.exe login
if errorlevel 1 (
  echo [ОШИБКА] Вход не завершён. Повтори скрипт ещё раз.
  pause & exit /b 1
)

rem --- 3. туннель -------------------------------------------------------------
echo.
echo [3/6] Создаю туннель %TNAME% (если уже есть — пропускаю)...
cloudflared.exe tunnel list | findstr /C:"%TNAME%" >nul
if errorlevel 1 (
  cloudflared.exe tunnel create %TNAME%
  if errorlevel 1 ( echo [ОШИБКА] Туннель не создан. & pause & exit /b 1 )
) else (
  echo       Туннель %TNAME% уже существует — ок.
)

rem --- 4. привязка доменов (перезаписываем старые записи --overwrite-dns) -----
echo.
echo [4/6] Привязываю домены к туннелю (старую запись сайта затираю)...
cloudflared.exe tunnel route dns --overwrite-dns %TNAME% %HOST1%
if errorlevel 1 goto dnsfail
cloudflared.exe tunnel route dns --overwrite-dns %TNAME% %HOST2%
cloudflared.exe tunnel route dns --overwrite-dns %TNAME% %HOST3%
goto dnsok
:dnsfail
echo [ОШИБКА] Не вышло привязать %HOST1%. Проверь: сайт в Cloudflare "Active"?
pause & exit /b 1
:dnsok

rem --- 5. конфиг --------------------------------------------------------------
echo.
echo [5/6] Пишу конфиг...
set TID=
for /f "tokens=1" %%i in ('cloudflared.exe tunnel list 2^>nul ^| findstr /C:"%TNAME%"') do set TID=%%i
if "%TID%"=="" (
  echo [ОШИБКА] Не нашёл ID туннеля. Повтори скрипт.
  pause & exit /b 1
)
set CFG=%USERPROFILE%\.cloudflared\config.yml
if not exist "%USERPROFILE%\.cloudflared" mkdir "%USERPROFILE%\.cloudflared" >nul 2>&1
>  "%CFG%" echo tunnel: %TID%
>> "%CFG%" echo credentials-file: %USERPROFILE%\.cloudflared\%TID%.json
>> "%CFG%" echo.
>> "%CFG%" echo ingress:
>> "%CFG%" echo   - hostname: %HOST1%
>> "%CFG%" echo     service: http://localhost:%PANEL_PORT%
>> "%CFG%" echo   - hostname: %HOST2%
>> "%CFG%" echo     service: http://localhost:%PANEL_PORT%
>> "%CFG%" echo   - hostname: %HOST3%
>> "%CFG%" echo     service: http://localhost:%PANEL_PORT%
>> "%CFG%" echo   - service: http_status:404
echo       Конфиг: %CFG%

rem конфиг и ключи также службе (у System32 свой профиль)
set SYSCFG=C:\Windows\System32\config\systemprofile\.cloudflared
if not exist "%SYSCFG%" mkdir "%SYSCFG%" >nul 2>&1
copy /y "%CFG%" "%SYSCFG%\config.yml" >nul 2>&1
copy /y "%USERPROFILE%\.cloudflared\%TID%.json" "%SYSCFG%\%TID%.json" >nul 2>&1

rem --- 6. автозапуск службой ---------------------------------------------------
echo.
echo [6/6] Ставлю автозапуск (служба Windows)...
cloudflared.exe service install
if errorlevel 1 (
  echo.
  echo [ВНИМАНИЕ] Служба не встала — запускаю туннель окном (НЕ закрывай его).
  echo Для автозапуска позже: запусти этот скрипт от имени администратора.
  cloudflared.exe tunnel run %TNAME%
) else (
  echo.
  echo  ==========================================================
  echo   ГОТОВО! Панель живёт на домене и будет сама подниматься
  echo   после каждой перезагрузки ПК. Адрес НЕ меняется никогда:
  echo.
  echo        https://%HOST1%
  echo.
  echo   Осталось: в .env бота допиши строку  WEB_BEHIND_PROXY=1
  echo   и перезапусти start.bat. Подробности: docs/PANEL-DOMAIN.md
  echo  ==========================================================
)
echo.
pause
