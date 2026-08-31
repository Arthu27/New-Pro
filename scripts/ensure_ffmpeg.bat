@echo off
:: ─────────────────────────────────────────────────────────────────────
::  ensure_ffmpeg.bat — гарантирует наличие ffmpeg для музыки (/play).
::
::  Порядок поиска/установки:
::    1) ffmpeg уже в PATH  -> выходим;
::    2) локальная копия .\bin\ffmpeg.exe (рядом с ботом) -> выходим,
::       прокидываем FFMPEG_BINARY в текущую сессию;
::    3) winget install Gyan.FFmpeg (тихая установка);
::    4) если winget нет/не сработал — качаем статическую сборку с
::       gyan.dev и распаковываем ffmpeg.exe/ffprobe.exe в .\bin\.
::
::  Вызывается из start.bat через `call`; при ошибке не роняем запуск
::  бота (музыка просто предупредит в /play).
:: ─────────────────────────────────────────────────────────────────────
setlocal
cd /d "%~dp0.."
set "BIN=%CD%\bin"
set "FF=%BIN%\ffmpeg.exe"

:: 1) уже в PATH?
where ffmpeg >nul 2>&1 && (
    echo [ffmpeg] найден в PATH
    exit /b 0
)

:: 2) локальная копия рядом с ботом?
if exist "%FF%" (
    echo [ffmpeg] локальная копия: %FF%
    endlocal & set "FFMPEG_BINARY=%FF%"
    exit /b 0
)

echo [ffmpeg] не найден — пробую установить автоматически...

:: 3) пробуем winget (Windows 10/11, App Installer)
where winget >nul 2>&1 && (
    echo [ffmpeg] установка через winget (Gyan.FFmpeg)...
    winget install --id Gyan.FFmpeg -e --silent --accept-source-agreements --accept-package-agreements >nul 2>&1
    where ffmpeg >nul 2>&1 && (
        echo [ffmpeg] установлен через winget
        exit /b 0
    )
    :: winget ставит в WinGet\Links — проверим явно (PATH текущей сессии мог не обновиться)
    if exist "%LOCALAPPDATA%\Microsoft\WinGet\Links\ffmpeg.exe" (
        echo [ffmpeg] установлен через winget (WinGet Links)
        endlocal & set "FFMPEG_BINARY=%LOCALAPPDATA%\Microsoft\WinGet\Links\ffmpeg.exe"
        exit /b 0
    )
)

:: 4) прямая загрузка статической сборки в .\bin\
echo [ffmpeg] winget недоступен — качаю статическую сборку (gyan.dev)...
if not exist "%BIN%" mkdir "%BIN%"
set "ZIP=%TEMP%\ffmpeg_essentials.zip"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip' -OutFile '%ZIP%' -UseBasicParsing } catch { Write-Host $_.Exception.Message; exit 1 }"
if errorlevel 1 goto :ff_fail
if not exist "%ZIP%" goto :ff_fail

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Add-Type -AssemblyName System.IO.Compression.FileSystem; $z=[IO.Compression.ZipFile]::OpenRead('%ZIP%'); foreach($e in $z.Entries){ if($e.FullName -match 'bin[\\/](ffmpeg|ffprobe)\.exe$'){ $dst=Join-Path '%BIN%' ([IO.Path]::GetFileName($e.FullName)); [IO.Compression.ZipFileExtensions]::ExtractToFile($e,$dst,$true) } }; $z.Dispose()"

del "%ZIP%" >nul 2>&1
if exist "%FF%" (
    echo [ffmpeg] готово: %FF%
    endlocal & set "FFMPEG_BINARY=%FF%"
    exit /b 0
)

:ff_fail
echo [ffmpeg] ВНИМАНИЕ: автоматическая установка не удалась.
echo [ffmpeg] Музыка (/play) работать не будет. Поставь вручную:
echo           winget install Gyan.FFmpeg
echo           или скачай с https://www.gyan.dev/ffmpeg и положи ffmpeg.exe в .\bin\
exit /b 0
