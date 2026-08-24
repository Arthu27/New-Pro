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
set REKEY=

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

if exist cloudflared.exe cloudflared.exe --version >nul 2>&1 && goto havebin
del cloudflared.exe >nul 2>&1
echo(
echo [1/6] Downloading cloudflared, please wait ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; $ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile 'cloudflared.exe'"
cloudflared.exe --version >nul 2>&1
if errorlevel 1 (
  del cloudflared.exe >nul 2>&1
  echo [ERROR] Download failed or the file is broken.
  echo         Plan B: open this link in your browser, then move
  echo         the downloaded file into this scripts folder
  echo         and rename it to cloudflared.exe :
  echo         https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe
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
call :resolvetid
if "%TID%"=="" (
  echo [ERROR] Tunnel ID not found. Run me again.
  pause
  exit /b 1
)

rem  The tunnel key (credentials json) lives only on the machine that
rem  created the tunnel. On a new PC/VDS it is missing -> we either
rem  restore it from the portable copies in this scripts folder, or
rem  rebuild the tunnel right here (step 2 login is enough for that).
call :ensurekey
if errorlevel 1 (
  pause
  exit /b 1
)

if "%REKEY%"=="1" (
  echo        Re-linking domains to the rebuilt tunnel ...
  cloudflared.exe tunnel route dns --overwrite-dns %TNAME% %HOST1%
  cloudflared.exe tunnel route dns --overwrite-dns %TNAME% %HOST2%
  cloudflared.exe tunnel route dns --overwrite-dns %TNAME% %HOST3%
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

rem Portable copies next to the bot: upload this folder to a VDS and the
rem tunnel will start itself from start.bat (binary auto-downloads too).
copy /y "%CFG%" "%~dp0config.yml" >nul 2>&1
copy /y "%USERPROFILE%\.cloudflared\%TID%.json" "%~dp0tunnel-creds.json" >nul 2>&1
echo        Portable copies saved into scripts - VDS upload ready.

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
cloudflared.exe service install >nul 2>&1
if errorlevel 1 (
  echo        Service already exists, restarting it ...
  net stop cloudflared >nul 2>&1
  net start cloudflared >nul 2>&1
) else (
  echo        Service installed.
)
sc start cloudflared >nul 2>&1
net start cloudflared >nul 2>&1
sc query cloudflared | findstr /C:"RUNNING" >nul 2>&1
if errorlevel 1 (
  echo(
  echo [NOTE] Service did not start, running tunnel in this window.
  echo        Do NOT close this window.
  cloudflared.exe tunnel run %TNAME%
) else (
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
goto :eof


:resolvetid
set TID=
for /f "tokens=1" %%i in ('cloudflared.exe tunnel list 2^>nul ^| findstr /C:"%TNAME%"') do set TID=%%i
goto :eof


:ensurekey
set CREDS=%USERPROFILE%\.cloudflared\%TID%.json
if exist "%CREDS%" goto :eof
if exist "%~dp0%TID%.json" copy /y "%~dp0%TID%.json" "%CREDS%" >nul 2>&1
if exist "%CREDS%" (
  echo        Key restored from the scripts folder copy, ok.
  goto :eof
)
if exist "%~dp0tunnel-creds.json" copy /y "%~dp0tunnel-creds.json" "%CREDS%" >nul 2>&1
if exist "%CREDS%" (
  echo        Key restored from the scripts folder copy, ok.
  goto :eof
)
echo(
echo [NOTE] Tunnel key file not found on this machine.
echo        The tunnel was created on another PC - rebuilding it here.
cloudflared.exe tunnel delete -f %TNAME% >nul 2>&1
cloudflared.exe tunnel create %TNAME%
if errorlevel 1 (
  echo [ERROR] Could not rebuild the tunnel.
  exit /b 1
)
call :resolvetid
if "%TID%"=="" (
  echo [ERROR] Tunnel ID not found after rebuild.
  exit /b 1
)
set CREDS=%USERPROFILE%\.cloudflared\%TID%.json
if not exist "%CREDS%" (
  echo [ERROR] Key file still missing after rebuild.
  exit /b 1
)
set REKEY=1
echo        Tunnel rebuilt and the key is saved on this machine.
goto :eof
