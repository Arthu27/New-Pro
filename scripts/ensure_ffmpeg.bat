@echo off
setlocal
rem -----------------------------------------------------------------------
rem  ensure_ffmpeg.bat - guarantee ffmpeg exists for music (/play).
rem  Linear, goto-based, NO nested parentheses (robust under any code page).
rem  Never aborts the caller: on any failure it just prints a hint and exits.
rem -----------------------------------------------------------------------
cd /d "%~dp0.."
set "BIN=%CD%\bin"
set "FF=%BIN%\ffmpeg.exe"
set "ZIP=%TEMP%\ffmpeg_essentials.zip"
set "URL=https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

rem 1) already on PATH?
where ffmpeg >nul 2>&1
if %errorlevel%==0 (
    echo [ffmpeg] already on PATH
    goto :done
)

rem 2) local copy next to the bot?
if exist "%FF%" (
    echo [ffmpeg] local copy: %FF%
    goto :done
)

echo [ffmpeg] not found - trying to install automatically...

rem 3) try winget (Windows 10/11 App Installer)
where winget >nul 2>&1
if %errorlevel%==0 goto :try_winget
goto :try_download

:try_winget
echo [ffmpeg] installing via winget (Gyan.FFmpeg)...
winget install --id Gyan.FFmpeg -e --silent --accept-source-agreements --accept-package-agreements >nul 2>&1
where ffmpeg >nul 2>&1
if %errorlevel%==0 (
    echo [ffmpeg] installed via winget
    goto :done
)
if exist "%LOCALAPPDATA%\Microsoft\WinGet\Links\ffmpeg.exe" (
    echo [ffmpeg] installed via winget (WinGet Links)
    goto :done
)

:try_download
rem 4) no winget / winget failed - download static build into .\bin
echo [ffmpeg] winget unavailable - downloading static build (gyan.dev)...
if not exist "%BIN%" mkdir "%BIN%"

powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; try { Invoke-WebRequest -Uri '%URL%' -OutFile '%ZIP%' -UseBasicParsing } catch { Write-Host $_.Exception.Message; exit 1 }"
if %errorlevel% neq 0 goto :fail
if not exist "%ZIP%" goto :fail

powershell -NoProfile -ExecutionPolicy Bypass -Command "Add-Type -AssemblyName System.IO.Compression.FileSystem; $z=[IO.Compression.ZipFile]::OpenRead('%ZIP%'); foreach($e in $z.Entries){ $n=$e.FullName -replace '/','\\'; if($n -like '*\bin\ffmpeg.exe' -or $n -like '*\bin\ffprobe.exe'){ $dst=Join-Path '%BIN%' ([IO.Path]::GetFileName($e.FullName)); [IO.Compression.ZipFileExtensions]::ExtractToFile($e,$dst,$true) } }; $z.Dispose()"
if %errorlevel% neq 0 goto :fail

del "%ZIP%" >nul 2>&1
if exist "%FF%" (
    echo [ffmpeg] ready: %FF%
    goto :done
)

:fail
echo [ffmpeg] WARNING: automatic install failed.
echo [ffmpeg] Music (/play) will not work until ffmpeg is present.
echo [ffmpeg] Install manually:  winget install Gyan.FFmpeg
echo [ffmpeg] or download from https://www.gyan.dev/ffmpeg and put ffmpeg.exe into .\bin\

:done
endlocal
exit /b 0
