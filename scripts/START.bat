@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0.."

title ProBotum Dashboard Launcher
color 0B

echo.
echo  ============================================
echo     ProBotum Dashboard - Sadece Panel
echo  ============================================
echo.
echo  Not: Bu dosya yalnizca dashboard'u baslatir.
echo       API + bot da isteniyorsa START_FULL.bat
echo       kullanin.
echo.

:: ── 1/3  Node.js (yoksa kurulur) ──
echo  [1/3] Node.js kontrol ediliyor...
echo.
call "%~dp0_deps.bat" node
if errorlevel 1 goto :fatal

if "%NEED_RESTART%"=="1" (
    echo.
    echo  ============================================
    echo   [!] Node.js yuklendi.
    echo.
    echo   Windows'un taniyabilmesi icin bu pencereyi
    echo   KAPATIN ve START.bat dosyasini tekrar
    echo   calistirin.
    echo  ============================================
    echo.
    pause
    exit /b 0
)

:: ── 2/3  Paketler ──
echo.
echo  [2/3] Node paketleri...
if not exist "node_modules" (
    echo       Yukleniyor - ilk seferde 1-2 dakika surebilir...
    call npm install
    if errorlevel 1 (
        echo  [ERROR] npm install basarisiz oldu.
        goto :fatal
    )
    echo  [OK] Paketler yuklendi.
) else (
    echo  [OK] Zaten yuklu.
)

:: ── 3/3  Dev server ──
echo.
echo  [3/3] Dashboard baslatiliyor...
echo.
echo  ============================================
echo.
echo    Dashboard:  http://localhost:5173
echo.
echo    API calismadigi icin panel simulation
echo    modunda acilir - bu normaldir.
echo.
echo    Kapatmak icin: CTRL + C
echo.
echo  ============================================
echo.

start "" "http://localhost:5173"
call npm run dev

exit /b 0


:fatal
echo.
echo  ============================================
echo   Baslatilamadi. Yukaridaki hataya bakin.
echo  ============================================
echo.
pause
exit /b 1
