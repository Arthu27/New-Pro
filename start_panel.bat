@echo off
chcp 65001 >nul 2>&1
title Hakumo Panel
cd /d "%~dp0"

REM Запуск веб-панели Hakumo.
REM   start_panel.bat        — БОЕВОЙ режим: токен, сервер и пароль из .env
REM   start_panel.bat demo   — демо-превью без бота (все данные выдуманные,
REM                            настройки из config\panel_preview.env)

set DEMO=0
if /i "%~1"=="demo" set DEMO=1
if /i "%~1"=="--demo" set DEMO=1

echo ============================================================
if "%DEMO%"=="1" (
    echo   HAKUMO - ВЕБ-ПАНЕЛЬ (ДЕМО-превью: данные выдуманные!)
) else (
    echo   HAKUMO - ВЕБ-ПАНЕЛЬ (боевой режим, настройки из .env)
)
echo ============================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ОШИБКА] Python не найден!
    echo Скачай с https://python.org и при установке отметь
    echo галочку "Add python.exe to PATH"
    pause
    exit /b 1
)

if not exist .venv (
    echo [1/4] Создаю виртуальное окружение...
    python -m venv .venv
)
if not exist .venv\Scripts\python.exe (
    echo [ОШИБКА] Не удалось создать .venv
    pause
    exit /b 1
)

echo [2/4] Устанавливаю зависимости (только для панели)...
.venv\Scripts\python -m pip install --upgrade pip --quiet
.venv\Scripts\python -m pip install -r requirements-panel.txt --quiet

if "%DEMO%"=="1" (
    echo [3/4] Готовлю демо-данные (выдуманный сервер, участники, логи)...
    set DEMO_MODE=1
    .venv\Scripts\python scripts\seed_demo_panel.py
    REM Панель читает пресет превью вместо боевого .env (config.py: DOTENV_PATH)
    set DOTENV_PATH=config\panel_preview.env
) else (
    echo [3/4] Демо-посев пропущен (боевой режим — только реальные данные).
    REM Панель работает за Cloudflare Tunnel: включает редирект http->https
    REM и заголовок HSTS в web/app.py. Без этого internet.nl показывает
    REM «HTTPS redirect: no» и «HSTS: None». Для локалки не нужно — там
    REM редирект и так отключён проверкой хоста на localhost/127.0.0.1.
    set WEB_BEHIND_PROXY=1
    if not exist .env (
        echo.
        echo [ВНИМАНИЕ] .env не найден — панель не знает ни токена, ни твоего сервера.
        echo            1) Скопируй шаблон:  copy .env.example .env
        echo            2) Заполни TOKEN и MAIN_GUILD_ID (ID твоего сервера).
        echo            Просто посмотреть витрину:  start_panel.bat demo
        echo.
    )
)

if "%PANEL_PORT%"=="" set PANEL_PORT=5001
echo [4/4] Запускаю панель...
echo     Адрес:  http://localhost:%PANEL_PORT%
if "%DEMO%"=="1" (
    echo     Логин:  owner
    echo     Пароль: preview123
) else (
    echo     Логин/пароль: из .env (PANEL_USER / PANEL_PASSWORD)
)
echo     Остановить: Ctrl+C или закрыть окно
echo.
start /b cmd /c "timeout /t 4 >nul & start http://localhost:%PANEL_PORT%"

.venv\Scripts\python -m flask --app web.wsgi run --host 0.0.0.0 --port %PANEL_PORT%

echo.
echo ============================================================
echo [ОШИБКА] Панель остановилась!
echo ============================================================
pause
