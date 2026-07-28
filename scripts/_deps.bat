@echo off
:: ============================================================
::  ProBotum - ortak bagimlilik yukleyici
::
::  Kullanim:   call scripts\_deps.bat node
::              call scripts\_deps.bat node python
::
::  Cagirana geri dondurdugu degiskenler:
::    NODE_VER      Node.js surumu
::    PY_CMD        Calisan python komutu (python / py)
::    PY_VER        Python surumu
::    NEED_RESTART  1 ise PATH yenilenmesi icin yeniden baslatma gerekiyor
::
::  NOT: Burada bilerek "setlocal" YOK - degiskenler cagirana gecsin diye.
:: ============================================================

set "NEED_RESTART=0"
set "DEPS_FAILED=0"

:arg_loop
if "%~1"=="" goto :arg_done
if /i "%~1"=="node"   call :ensure_node
if /i "%~1"=="python" call :ensure_python
if "%DEPS_FAILED%"=="1" exit /b 1
shift
goto :arg_loop

:arg_done
exit /b 0


:: ------------------------------------------------------------
:ensure_node
set "NODE_VER="
where node >nul 2>nul
if not errorlevel 1 (
    for /f "tokens=*" %%v in ('node -v 2^>nul') do set "NODE_VER=%%v"
)
if defined NODE_VER (
    echo  [OK] Node.js zaten yuklu: %NODE_VER%
    exit /b 0
)
echo  [!] Node.js bulunamadi, yukleniyor...
call :install_pkg "OpenJS.NodeJS.LTS" "Node.js" "https://nodejs.org/dist/v22.11.0/node-v22.11.0-x64.msi" "node.msi"
if errorlevel 1 (
    set "DEPS_FAILED=1"
    exit /b 1
)
call :refresh_path
where node >nul 2>nul
if errorlevel 1 (
    set "NEED_RESTART=1"
    exit /b 0
)
for /f "tokens=*" %%v in ('node -v 2^>nul') do set "NODE_VER=%%v"
echo  [OK] Node.js yuklendi: %NODE_VER%
exit /b 0


:: ------------------------------------------------------------
:ensure_python
call :find_python
if defined PY_CMD (
    echo  [OK] Python zaten yuklu: %PY_VER%
    exit /b 0
)
echo  [!] Python bulunamadi, yukleniyor...
call :install_pkg "Python.Python.3.12" "Python" "https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe" "python.exe"
if errorlevel 1 (
    set "DEPS_FAILED=1"
    exit /b 1
)
call :refresh_path
call :find_python
if not defined PY_CMD (
    set "NEED_RESTART=1"
    exit /b 0
)
echo  [OK] Python yuklendi: %PY_VER%
exit /b 0


:: ------------------------------------------------------------
:: Gercek Python'u bulur. Microsoft Store'un sahte "python"
:: stub'ini eler (o stub surum bilgisi yerine reklam basar).
:find_python
set "PY_CMD="
set "PY_VER="
for %%c in (python python3 py) do (
    if not defined PY_CMD (
        for /f "tokens=*" %%v in ('%%c --version 2^>^&1') do (
            if not defined PY_CMD (
                echo %%v | findstr /r /i "^Python [23]\." >nul
                if not errorlevel 1 (
                    set "PY_CMD=%%c"
                    set "PY_VER=%%v"
                )
            )
        )
    )
)
exit /b 0


:: ------------------------------------------------------------
:: %~1 winget id | %~2 gorunen ad | %~3 yedek indirme linki | %~4 dosya adi
:install_pkg
where winget >nul 2>nul
if not errorlevel 1 (
    echo       winget ile yukleniyor: %~2
    winget install --id %~1 -e --source winget --accept-package-agreements --accept-source-agreements --silent
    if not errorlevel 1 exit /b 0
    echo       winget ile olmadi, dogrudan indirmeye geciliyor...
) else (
    echo       winget yok, dogrudan indiriliyor...
)

set "DL=%TEMP%\probotum_%~4"
if exist "%DL%" del "%DL%" >nul 2>nul

echo       Indiriliyor: %~2
where curl >nul 2>nul
if not errorlevel 1 (
    curl -L --fail --silent --show-error -o "%DL%" "%~3"
) else (
    powershell -NoProfile -Command "try{[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12;Invoke-WebRequest -Uri '%~3' -OutFile '%DL%' -UseBasicParsing}catch{exit 1}"
)

if not exist "%DL%" (
    echo.
    echo  [ERROR] %~2 indirilemedi. Internet baglantisini kontrol edin.
    echo          Elle yuklemek icin: %~3
    exit /b 1
)

echo       Kuruluyor: %~2   ^(Windows yonetici izni isteyebilir^)
if /i "%~4"=="node.msi" (
    msiexec /i "%DL%" /qn /norestart
) else (
    "%DL%" /quiet InstallAllUsers=1 PrependPath=1 Include_pip=1
)
set "RC=%ERRORLEVEL%"
del "%DL%" >nul 2>nul

:: 3010 = basarili ama yeniden baslatma gerekiyor
if "%RC%"=="0"    exit /b 0
if "%RC%"=="3010" exit /b 0
echo.
echo  [ERROR] %~2 kurulumu basarisiz oldu ^(hata kodu %RC%^).
echo          Elle yuklemek icin: %~3
exit /b 1


:: ------------------------------------------------------------
:: Kurulum sonrasi PATH'i registry'den tazeler ki ayni
:: pencerede yeni programi gorebilelim.
:refresh_path
set "SYSPATH="
set "USRPATH="
:: "tokens=2,*" ile REG_EXPAND_SZ/REG_SZ tipini atlayip degeri aliriz
for /f "skip=1 tokens=2,*" %%a in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do (
    if not "%%b"=="" set "SYSPATH=%%b"
)
for /f "skip=1 tokens=2,*" %%a in ('reg query "HKCU\Environment" /v Path 2^>nul') do (
    if not "%%b"=="" set "USRPATH=%%b"
)
if defined SYSPATH set "PATH=%SYSPATH%"
if defined USRPATH set "PATH=%PATH%;%USRPATH%"
:: Kurulumlar bu klasorlere yazar - registry okunamazsa yedek olarak ekle
if exist "%ProgramFiles%\nodejs\node.exe" set "PATH=%PATH%;%ProgramFiles%\nodejs"
exit /b 0
