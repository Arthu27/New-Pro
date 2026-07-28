@echo off
setlocal
cd /d "%~dp0"

title ProBotum Full System Launcher
color 0A

echo.
echo  ============================================
echo     ProBotum Full System Launcher
echo     Dashboard + API + Bot
echo  ============================================
echo.

:: ── Check Node.js ──
where node >nul 2>nul
if errorlevel 1 (
    echo  [ERROR] Node.js bulunamadi!
    echo  https://nodejs.org/
    pause
    exit /b 1
)

:: ── Check Python ──
where python >nul 2>nul
if errorlevel 1 (
    echo  [ERROR] Python bulunamadi!
    echo  https://python.org/
    pause
    exit /b 1
)

for /f "tokens=*" %%v in ('node -v') do echo  [OK] Node.js: %%v
for /f "tokens=*" %%v in ('python --version') do echo  [OK] %%v
echo.

:: ── Install Node packages ──
if not exist "node_modules" (
    echo  [1/5] Node paketleri yukleniyor...
    call npm install
    if errorlevel 1 (
        echo  [ERROR] npm install basarisiz!
        pause
        exit /b 1
    )
) else (
    echo  [1/5] Node paketleri zaten yuklu.
)

:: ── Install Python packages ──
echo  [2/5] Python paketleri kontrol ediliyor...
python -m pip install -r requirements.txt >nul 2>nul
echo  [OK] Python paketleri hazir.
echo.

:: ── Check .env ──
if not exist ".env" (
    if exist ".env.example" (
        echo  [!] .env dosyasi bulunamadi, .env.example kopyalaniyor...
        copy ".env.example" ".env" >nul
        echo  [!] .env dosyasini duzenle ve tekrar calistir.
        notepad ".env"
        pause
        exit /b 1
    ) else (
        echo  [WARN] .env ve .env.example bulunamadi.
        echo         API calisabilir ama Discord ozellikleri calismaz.
    )
)

echo.

:: ── Start API ──
echo  [3/5] API baslatiliyor (port 3000)...
start "ProBotum API :3000" cmd /k "cd /d "%~dp0" && python -m uvicorn server.api:app --host 0.0.0.0 --port 3000"
timeout /t 3 /nobreak >nul

:: ── Start Bot (optional) ──
echo  [4/5] Discord bot baslatiliyor...
start "ProBotum Bot" cmd /k "cd /d "%~dp0" && python -m bot.main"
timeout /t 2 /nobreak >nul

:: ── Start Dashboard ──
echo  [5/5] Dashboard baslatiliyor (port 5173)...
echo.
echo  ============================================
echo.
echo    Dashboard:  http://localhost:5173
echo    API:        http://localhost:3000/api
echo    API Health: http://localhost:3000/api/health
echo.
echo    Tum pencereleri kapatmak icin her birinde
echo    CTRL + C yapin veya pencereyi kapatin.
echo.
echo  ============================================
echo.

start "" "http://localhost:5173"
start "" "http://localhost:3000/api/health"
call npm run dev
