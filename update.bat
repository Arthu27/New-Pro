@echo off
rem ==================================================================
rem  Hakumo Updater -- obnovlenie bota v odin dvoynoy klik.
rem
rem  Istochnik: POSTOYANNAYA ssylka "posledniy reliz" na GitHub --
rem  ona ne menyayetsya ot chata k chatu. Esli relizov net -- zapasnoy
rem  put': vetka, propisannaya nizhe (BRANCH).
rem
rem  Chto delaet:
rem    1. Skachivayet svejuyu sborku s GitHub
rem    2. Raspakovyvayet vo vremennuyu papku
rem    3. Akkuratno dokladyvayet kod poverh tekushchey papki.
rem       NE TROGAYET: .env, data\ (baza, nastroyki, logi), .venv, .git
rem    4. Stavit zavisimosti iz requirements.txt (esli izmenilis)
rem    5. Perezapuskayet bota (staruyu kopiyu main.py gasit tochno)
rem
rem  Zapusk: dvoynoy klik po update.bat
rem  Bez perezapuska: update.bat /norestart
rem ==================================================================
setlocal EnableDelayedExpansion
title Hakumo Updater
cd /d "%~dp0"

set "REPO=Arthu27/New-Pro"
rem Vetka po umolchaniyu: main (tuda merzhatsya relizy). Ranshe tut byla
rem myortvaya arena-vetka staroy sessii - obnovlenie kachalo ustarevshiy kod.
rem Esli vladelec zadal UPDATE_REPO/UPDATE_BRANCH v .env - uvozhaem ih.
set "BRANCH=main"
rem Token dlya PRIVATNOGO repozitoriya (iz .env): bez nego GitHub dayot 404.
set "GH_TOKEN="
if exist ".env" (
    for /f "usebackq tokens=1,2 delims==" %%A in (`findstr /b /c:"UPDATE_REPO=" .env 2^>nul`) do set "REPO=%%B"
    for /f "usebackq tokens=1,2 delims==" %%A in (`findstr /b /c:"UPDATE_BRANCH=" .env 2^>nul`) do set "BRANCH=%%B"
    for /f "usebackq tokens=1,2 delims==" %%A in (`findstr /b /c:"GITHUB_TOKEN=" .env 2^>nul`) do set "GH_TOKEN=%%B"
    for /f "usebackq tokens=1,2 delims==" %%A in (`findstr /b /c:"UPDATE_TOKEN=" .env 2^>nul`) do if not defined GH_TOKEN set "GH_TOKEN=%%B"
)
rem Privatnyy repozitoriy: anonimnaya codeload-ssylka dayot 404. S tokenom
rem kachaem cherez api.github.com/zipball (GitHub otdayot 302 na podpisannyy codeload).
set "AUTH="
if defined GH_TOKEN set AUTH=-H "Authorization: token %GH_TOKEN%"
set "URL=https://codeload.github.com/%REPO%/zip/refs/heads/%BRANCH%"
if defined GH_TOKEN set "URL=https://api.github.com/repos/%REPO%/zipball/%BRANCH%"
set "TMPZ=%TEMP%\hakumo_update.zip"
set "TMPSRC=%TEMP%\hakumo_update_src"
set "SRC="
set "TMPURL=%TEMP%\hakumo_update_url.txt"

rem -- Postoyannyy istochnik: posledniy reliz (ssylka ne zavisit ot vetki)
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol=[Enum]::ToObject([Net.SecurityProtocolType],3072); $h=@{}; if ($env:GH_TOKEN) { $h['Authorization']='token '+$env:GH_TOKEN }; try { $r=Invoke-RestMethod -Headers $h 'https://api.github.com/repos/%REPO%/releases/latest'; if ($r.zipball_url) { $r.zipball_url | Out-File -Encoding ascii '%TMPURL%' } else { exit 1 } } catch { exit 1 }" >nul 2>nul
if exist "%TMPURL%" (
    for /f "usebackq delims=" %%U in ("%TMPURL%") do if not "%%U"=="" set "URL=%%U"
    del "%TMPURL%" >nul 2>nul
)
if "%URL%"=="https://codeload.github.com/%REPO%/zip/refs/heads/%BRANCH%" (
    echo   Istochnik: vetka %BRANCH% ^| relizov poka net
) else if "%URL%"=="https://api.github.com/repos/%REPO%/zipball/%BRANCH%" (
    echo   Istochnik: vetka %BRANCH% ^| relizov poka net
) else (
    echo   Istochnik: posledniy reliz ^| postoyannaya ssylka
)

echo ==================================================================
echo   Hakumo Updater
echo   Papka bota: %CD%
echo ==================================================================
echo.

if not exist main.py (
    echo [OSHIBKA] main.py ne nayden -- zapusti update.bat iz papki bota.
    goto :end
)

echo [1/5] Skachivayu svejuyu sborku s GitHub...
rem Staryy PowerShell ne dogovarivayetsya s GitHub po TLS 1.2:
rem snachala curl.exe (Windows 10 / Server 2019+), inache PowerShell s TLS 1.2.
where curl.exe >nul 2>nul
if not errorlevel 1 (
    curl.exe -L --fail --silent --show-error %AUTH% -o "%TMPZ%" "%URL%"
    if errorlevel 1 goto :fail_download
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol=[Enum]::ToObject([Net.SecurityProtocolType],3072); $ProgressPreference='SilentlyContinue'; $h=@{}; if ($env:GH_TOKEN) { $h['Authorization']='token '+$env:GH_TOKEN }; try { Invoke-WebRequest -Uri '%URL%' -Headers $h -OutFile '%TMPZ%' -UseBasicParsing; exit 0 } catch { Write-Host $_.Exception.Message; exit 1 }"
    if errorlevel 1 goto :fail_download
)

echo [2/5] Raspakovyvayu...
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
    echo [OSHIBKA] V arhive net ozhidaemoy papki -- otmena.
    goto :fail_download
)

echo [3/5] Obnovlyayu kod (dannye, .env i logi ne trogayu)...
robocopy "%SRC%" "." /E /XD data .git .venv __pycache__ logs /XF .env update.bat /NFL /NDL /NJH /R:2 /W:2 >nul
if errorlevel 8 goto :fail_copy

echo [4/5] Proveryayu zavisimosti...
if exist requirements.txt (
    python -m pip install -r requirements.txt --quiet --disable-pip-version-check
    if errorlevel 1 echo [PREDUPREZHDENIE] pip zavershilsya s oshibkoy -- smotri vyvod vyshe.
)

rem Snimaem metku obnovleniya (ee stavit bot pered zapuskom update_silent.bat).
rem Bez etogo start_bot.bat reshil by, chto obnovlenie eshchyo idyot, i ne podnyal by bota.
if exist "data\.updating" del /q "data\.updating" >nul 2>&1
rem Zaodno ubiraem otkladnoy arkhiv: etot skript kachaet sam, a staryy
rem fayl ot proshlogo zapuska obnovlyator primenil by vmesto svezhego.
if exist "data\.update_pending.zip" del /q "data\.update_pending.zip" >nul 2>&1
if exist "data\.update_pending.json" del /q "data\.update_pending.json" >nul 2>&1

if /i "%~1"=="/norestart" (
    echo [5/5] Gotovo. Perezapuska propushchen ^(/norestart^).
    goto :ok
)

echo [5/5] Perezapuskayu bota...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe' or Name='pythonw.exe'\" | Where-Object { $_.CommandLine -match 'main\.py' } | ForEach-Object { Write-Host ('  Ostanavlivayu PID ' + $_.ProcessId); Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
timeout /t 2 /nobreak >nul
start "Hakumo Bot" cmd /k python main.py

:ok
echo.
echo ==================================================================
echo   Obnovlenie zaversheno. Dannye i .env ne potrosheny.
echo   Marker svezhego koda pri starte: "Slesh-menyu: NN komand..."
echo ==================================================================
goto :end

:fail_download
echo.
echo [OSHIBKA] Ne udalos skachat/raspakovat sborku.
echo Proveryay internet i chto GitHub dostupen. Lokalnye faily ne tronuty.
echo Esli snova pro SSL/TLS -- skachay update.bat v brauzere i polozhi ryadom:
echo   https://github.com/Arthu27/New-Pro/raw/latest/update.bat
goto :end

:fail_copy
echo.
echo [OSHIBKA] Robocopy vernul oshibku pri kopirovanii.
echo Tvoi .env i data\ ne postradali. Povtori zapusk.

:end
echo.
pause
endlocal
