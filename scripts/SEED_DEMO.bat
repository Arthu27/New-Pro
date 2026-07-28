@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0.."

title ProBotum - Demo Data Seed
color 0E

echo.
echo  ============================================
echo     ProBotum - Demo Data Yukle
echo  ============================================
echo.
echo  Bu islem, bot ve gercek Discord baglantisi
echo  olmadan paneli test edebilmen icin ornek
echo  veri olusturur.
echo.
echo  Olusturulacak:
echo    Guild     : ProBotum Test Server
echo    Uyeler    : artur, lega, admin ...
echo    Kanallar  : welcome, general, tickets ...
echo    Roller    : Owner, Admin, Moderator ...
echo.

:: ── Python (yoksa kurulur) ──
echo  [1/3] Python kontrol ediliyor...
echo.
call "%~dp0_deps.bat" python
if errorlevel 1 goto :fatal

if "%NEED_RESTART%"=="1" (
    echo.
    echo  ============================================
    echo   [!] Python yuklendi.
    echo.
    echo   Bu pencereyi KAPATIN ve SEED_DEMO.bat
    echo   dosyasini tekrar calistirin.
    echo  ============================================
    echo.
    pause
    exit /b 0
)

:: ── Sanal ortam + paketler ──
echo.
echo  [2/3] Python paketleri...
if not exist ".venv" (
    echo       Sanal ortam olusturuluyor...
    %PY_CMD% -m venv .venv
    if errorlevel 1 (
        echo  [ERROR] Sanal ortam olusturulamadi.
        goto :fatal
    )
)
set "VPY=.venv\Scripts\python.exe"
if not exist "%VPY%" (
    echo  [ERROR] Sanal ortam bozuk. .venv klasorunu silip tekrar deneyin.
    goto :fatal
)
"%VPY%" -m pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo  [ERROR] Python paketleri yuklenemedi.
    goto :fatal
)
echo  [OK] Hazir.

:: ── Seed ──
echo.
echo  [3/3] Demo veri yukleniyor...
echo.
"%VPY%" -m server.dev_seed
if errorlevel 1 (
    echo.
    echo  [ERROR] Demo veri yuklenemedi.
    goto :fatal
)

echo.
echo  ============================================
echo   [OK] Demo veri yuklendi.
echo.
echo   Simdi START_FULL.bat ile baslatabilirsin.
echo  ============================================
echo.
pause
exit /b 0


:fatal
echo.
echo  ============================================
echo   Islem tamamlanamadi.
echo  ============================================
echo.
pause
exit /b 1
