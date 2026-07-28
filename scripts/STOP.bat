@echo off
setlocal EnableDelayedExpansion
title ProBotum - Servisleri Durdur
color 0C

echo.
echo  ============================================
echo     ProBotum - Servisleri Durdur
echo  ============================================
echo.
echo  Kapatilacak:
echo    Port 5173  - Dashboard
echo    Port 3000  - API
echo    ProBotum Bot penceresi
echo.
pause
echo.

set "KILLED=0"

call :kill_port 5173 Dashboard
call :kill_port 3000 API

:: Bot penceresini basligindan bul ve kapat
taskkill /FI "WINDOWTITLE eq ProBotum Bot*" /T /F >nul 2>nul
if not errorlevel 1 (
    echo  [OK] ProBotum Bot kapatildi.
    set "KILLED=1"
)

echo.
if "%KILLED%"=="0" (
    echo  [i] Calisan ProBotum servisi bulunamadi.
) else (
    echo  [OK] Servisler durduruldu.
)
echo.
pause
exit /b 0


:: ------------------------------------------------------------
:: %1 = port numarasi, %2 = gorunen ad
:kill_port
set "PORT=%~1"
set "NAME=%~2"
:: ":5173 " kaliba tam eslesme - :51730 gibi portlari yanlislikla kapatmamak icin
:: LISTENING satirlarindaki 5. sutun = PID
for /f "tokens=5" %%a in ('netstat -ano -p TCP 2^>nul ^| findstr /r /c:":%PORT% .*LISTENING"') do (
    if not "%%a"=="0" (
        echo  Port %PORT% ^(%NAME%^) - PID %%a kapatiliyor...
        taskkill /PID %%a /T /F >nul 2>nul
        if not errorlevel 1 set "KILLED=1"
    )
)
exit /b 0
