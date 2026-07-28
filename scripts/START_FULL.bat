@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0.."

title ProBotum Full System Launcher
color 0A

echo.
echo  ============================================
echo     ProBotum Full System Launcher
echo     Dashboard + API + Bot
echo  ============================================
echo.
echo  Eksik program varsa otomatik yuklenecek.
echo.

:: ── 1/6  Node.js + Python (yoksa kurulur) ──
echo  [1/6] Gerekli programlar kontrol ediliyor...
echo.
call "%~dp0_deps.bat" node python
if errorlevel 1 goto :fatal

if "%NEED_RESTART%"=="1" (
    echo.
    echo  ============================================
    echo   [!] Yeni program yuklendi.
    echo.
    echo   Windows'un yeni programi taniyabilmesi icin
    echo   bu pencereyi KAPATIN ve START_FULL.bat
    echo   dosyasini tekrar calistirin.
    echo  ============================================
    echo.
    pause
    exit /b 0
)

:: ── 2/6  .env ──
echo.
echo  [2/6] Konfigurasyon...
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo  [!] .env olusturuldu - Discord token girmen gerekiyor.
        echo.
        echo      Token almak icin:
        echo      https://discord.com/developers/applications
        echo.
        echo      Simdi Notepad acilacak. DISCORD_TOKEN satirini
        echo      doldur, KAYDET ^(Ctrl+S^) ve pencereyi kapat.
        echo.
        echo      Token girmeden de devam edebilirsin - bu durumda
        echo      dashboard demo veriyle calisir, bot baslamaz.
        echo.
        pause
        notepad ".env"
    ) else (
        echo  [WARN] .env.example bulunamadi, bu adim atlaniyor.
    )
) else (
    echo  [OK] .env mevcut.
)

:: ── 3/6  Node paketleri ──
echo.
echo  [3/6] Node paketleri...
if not exist "node_modules" (
    echo       Yukleniyor - ilk seferde 1-2 dakika surebilir...
    call npm install
    if errorlevel 1 (
        echo  [ERROR] npm install basarisiz oldu.
        goto :fatal
    )
    echo  [OK] Node paketleri yuklendi.
) else (
    echo  [OK] Zaten yuklu.
)

:: ── 4/6  Python sanal ortam + paketler ──
echo.
echo  [4/6] Python paketleri...
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
    echo  [ERROR] Sanal ortam bozuk gorunuyor.
    echo          .venv klasorunu silip tekrar calistirin.
    goto :fatal
)
"%VPY%" -m pip install --upgrade pip --quiet
"%VPY%" -m pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo  [ERROR] Python paketleri yuklenemedi.
    goto :fatal
)
echo  [OK] Python paketleri hazir.

:: ── 5/6  Veritabani ──
echo.
echo  [5/6] Veritabani...
if not exist "data\database.sqlite" (
    echo       Demo veri yukleniyor...
    "%VPY%" -m server.dev_seed
) else (
    echo  [OK] Veritabani mevcut.
)

:: ── 6/6  Servisler ──
echo.
echo  [6/6] Servisler baslatiliyor...

start "ProBotum API :3000" cmd /k "cd /d "%~dp0.." && .venv\Scripts\python.exe -m uvicorn server.api:app --host 0.0.0.0 --port 3000"
timeout /t 3 /nobreak >nul

:: Bot yalnizca gercek token varsa baslatilir
set "TOKEN_OK=0"
if exist ".env" (
    for /f "usebackq eol=# tokens=1,* delims==" %%a in (".env") do (
        if /i "%%a"=="DISCORD_TOKEN" (
            if not "%%b"=="" if /i not "%%b"=="put_your_bot_token_here" set "TOKEN_OK=1"
        )
    )
)

if "%TOKEN_OK%"=="1" (
    echo       Discord bot baslatiliyor...
    start "ProBotum Bot" cmd /k "cd /d "%~dp0.." && .venv\Scripts\python.exe -m bot.main"
    timeout /t 2 /nobreak >nul
) else (
    echo.
    echo  [!] DISCORD_TOKEN ayarlanmamis - bot baslatilmadi.
    echo      Dashboard ve API demo veriyle calisiyor.
    echo      Token eklemek icin .env dosyasini duzenleyin.
)

echo.
echo  ============================================
echo.
echo    Dashboard:  http://localhost:5173
echo    API:        http://localhost:3000/api
echo    API Health: http://localhost:3000/api/health
echo.
echo    Kapatmak icin: scripts\STOP.bat
echo.
echo  ============================================
echo.

start "" "http://localhost:5173"
call npm run dev

exit /b 0


:fatal
echo.
echo  ============================================
echo   Kurulum tamamlanamadi.
echo   Yukaridaki hata mesajina bakin.
echo  ============================================
echo.
pause
exit /b 1
