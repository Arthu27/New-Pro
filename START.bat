@echo off
setlocal
cd /d "%~dp0"

title ProBotum Dashboard Launcher
color 0B

echo.
echo  ============================================
echo     ProBotum Dashboard - Full Start
echo  ============================================
echo.

:: ── Check Node.js ──
where node >nul 2>nul
if errorlevel 1 (
    echo  [ERROR] Node.js bulunamadi!
    echo.
    echo  Node.js indirmek icin:
    echo  https://nodejs.org/
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%v in ('node -v') do echo  [OK] Node.js: %%v

:: ── Check npm ──
where npm >nul 2>nul
if errorlevel 1 (
    echo  [ERROR] npm bulunamadi!
    pause
    exit /b 1
)

for /f "tokens=*" %%v in ('npm -v') do echo  [OK] npm: %%v
echo.

:: ── Install dependencies ──
if not exist "node_modules" (
    echo  [1/3] Paketler yukleniyor...
    echo       Bu ilk seferde 1-2 dakika surebilir.
    echo.
    call npm install
    if errorlevel 1 (
        echo.
        echo  [ERROR] npm install basarisiz!
        pause
        exit /b 1
    )
    echo.
    echo  [OK] Paketler yuklendi.
) else (
    echo  [1/3] Paketler zaten yuklu.
)

echo.

:: ── Build project ──
echo  [2/3] Proje derleniyor...
call npm run build
if errorlevel 1 (
    echo.
    echo  [ERROR] Build basarisiz!
    pause
    exit /b 1
)

echo.
echo  [OK] Build tamamlandi.
echo.

:: ── Start dev server ──
echo  [3/3] Dashboard baslatiliyor...
echo.
echo  ============================================
echo.
echo    Dashboard:  http://localhost:5173
echo    API:        http://localhost:3000/api
echo.
echo    Dashboard acilinca login ekrani gelir.
echo    API baglantisi yoksa simulation modunda
echo    calisir - sorun olmaz.
echo.
echo    Kapatmak icin: CTRL + C
echo.
echo  ============================================
echo.

start "" "http://localhost:5173"
call npm run dev
