@echo off
rem ============================================================
rem  Aether Panel - tunnel to hakumods.xyz
rem  Right click this file - "Run as administrator"
rem  Guide: docs/PANEL-DOMAIN.md
rem ============================================================
setlocal EnableExtensions
cd /d "%~dp0"
title Aether Panel Tunnel

set TNAME=aether-panel
set PANEL_PORT=5001
set HOST1=hakumods.xyz
set HOST2=www.hakumods.xyz
set HOST3=panel.hakumods.xyz

echo(
echo  ==========================================================
echo   Aether Panel - your own domain setup
echo   %HOST1% and %HOST3% = http://localhost:%PANEL_PORT%
echo  ==========================================================
echo(
echo  Make sure first:
echo   1. hakumods.xyz is ACTIVE in Cloudflare
echo   2. the bot is running via start.bat
echo(
pause

echo [0/6] Checking panel on localhost:%PANEL_PORT% ...
powershell -NoProfile -Command "try { (Invoke-WebRequest -UseBasicParsing -TimeoutSec 4 -Uri 'http://localhost:%PANEL_PORT%/').StatusCode } catch { 'DOWN' }" > "%TEMP%\_aether_ping.txt" 2>nul
set /p PING=<"%TEMP%\_aether_ping.txt"
del "%TEMP%\_aether_ping.txt" >nul 2>&1
if /i "%PING%"=="DOWN" (
  echo [STOP] Panel is not answering on port %PANEL_PORT%.
  echo        Start the bot with start.bat, then run me again.
  pause
  exit /b 1
)
echo        Panel is alive, moving on.

if exist cloudflared.exe cloudflared.exe --version >nul 2>&1
if %errorlevel%==0 goto havebin
del cloudflared.exe >nul 2>&1
echo(
echo [1/6] Downloading cloudflared, please wait ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile 'cloudflared.exe'"
if not exist cloudflared.exe (
  echo [ERROR] Download failed. Check internet and try again.
  pause
  exit /b 1
)
goto binok
:havebin
echo [1/6] cloudflared.exe already here, ok.
:binok

echo(
echo [2/6] Cloudflare login. A browser will open.
echo        Pick site hakumods.xyz and press Authorize.
cloudflared.exe login
if errorlevel 1 (
  echo [ERROR] Login not finished. Run me again.
  pause
  exit /b 1
)

echo(
echo [3/6] Creating tunnel %TNAME% if needed ...
cloudflared.exe tunnel list | findstr /C:"%TNAME%" >nul
if errorlevel 1 (
  cloudflared.exe tunnel create %TNAME%
  if errorlevel 1 (
    echo [ERROR] Could not create the tunnel.
    pause
    exit /b 1
  )
)
echo        Tunnel ready.

echo(
echo [4/6] Linking domains to the tunnel ...
echo        Old empty-site record will be replaced by the panel.
cloudflared.exe tunnel route dns --overwrite-dns %TNAME% %HOST1%
if errorlevel 1 (
  echo [ERROR] Could not link %HOST1%.
  echo         Is the site ACTIVE in Cloudflare?
  pause
  exit /b 1
)
cloudflared.exe tunnel route dns --overwrite-dns %TNAME% %HOST2%
cloudflared.exe tunnel route dns --overwrite-dns %TNAME% %HOST3%

echo(
echo [5/6] Writing config ...
set TID=
for /f "tokens=1" %%i in ('cloudflared.exe tunnel list 2^>nul ^| findstr /C:"%TNAME%"') do set TID=%%i
if "%TID%"=="" (
  echo [ERROR] Tunnel ID not found. Run me again.
  pause
  exit /b 1
)
set CFG=%USERPROFILE%\.cloudflared\config.yml
if not exist "%USERPROFILE%\.cloudflared" mkdir "%USERPROFILE%\.cloudflared" >nul 2>&1
>  "%CFG%" echo tunnel: %TID%
>> "%CFG%" echo credentials-file: %USERPROFILE%\.cloudflared\%TID%.json
>> "%CFG%" echo(
>> "%CFG%" echo ingress:
>> "%CFG%" echo   - hostname: %HOST1%
>> "%CFG%" echo     service: http://localhost:%PANEL_PORT%
>> "%CFG%" echo   - hostname: %HOST2%
>> "%CFG%" echo     service: http://localhost:%PANEL_PORT%
>> "%CFG%" echo   - hostname: %HOST3%
>> "%CFG%" echo     service: http://localhost:%PANEL_PORT%
>> "%CFG%" echo   - service: http_status:404
echo        Config written: %CFG%

set SYSCFG=C:\Windows\System32\config\systemprofile\.cloudflared
if not exist "%SYSCFG%" mkdir "%SYSCFG%" >nul 2>&1
copy /y "%CFG%" "%SYSCFG%\config.yml" >nul 2>&1
copy /y "%USERPROFILE%\.cloudflared\%TID%.json" "%SYSCFG%\%TID%.json" >nul 2>&1

set ENVFILE=%~dp0..\.env
if exist "%ENVFILE%" (
  findstr /x /c:"WEB_BEHIND_PROXY=1" "%ENVFILE%" >nul 2>&1
  if errorlevel 1 (
    echo WEB_BEHIND_PROXY=1>> "%ENVFILE%"
    echo        Added WEB_BEHIND_PROXY=1 to .env
  ) else (
    echo        WEB_BEHIND_PROXY=1 already in .env, ok.
  )
) else (
  echo [NOTE] .env not found next to the bot.
  echo        Add this line by hand: WEB_BEHIND_PROXY=1
)

echo(
echo [6/6] Installing autostart service and starting it ...
cloudflared.exe service install
if errorlevel 1 (
  echo(
  echo [NOTE] Service install failed, starting tunnel in this window.
  echo        Do NOT close this window.
  cloudflared.exe tunnel run %TNAME%
) else (
  sc start cloudflared >nul 2>&1
  net start cloudflared >nul 2>&1
  echo(
  echo  ==========================================================
  echo   DONE! Panel now lives on your domain.
  echo(
  echo        https://%HOST1%
  echo(
  echo   FINAL STEP: restart the bot with start.bat,
  echo   then open https://%HOST1%
  echo  ==========================================================
)
echo(
pause
