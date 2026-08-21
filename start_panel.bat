@echo off
chcp 65001 >nul 2>&1
title Aether Panel
cd /d "%~dp0"

echo ============================================================
echo   AETHER - ВЕБ-ПАНЕЛЬ (демо-режим, без токена бота)
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

echo [3/4] Готовлю демо-данные...
.venv\Scripts\python scripts\seed_demo_panel.py

echo.
echo [4/4] Запускаю панель...
echo     Адрес:  http://localhost:5001
echo     Логин:  owner
echo     Пароль: preview123
echo     Остановить: Ctrl+C или закрыть окно
echo.
start /b cmd /c "timeout /t 4 >nul & start http://localhost:5001"

set DEMO_MODE=1
set SECRET_KEY=local-preview-secret
set PANEL_USER=owner
set PANEL_PASSWORD=preview123
set MAIN_GUILD_ID=987654321098765432
.venv\Scripts\python -m flask --app web.wsgi run --host 0.0.0.0 --port 5001

echo.
echo ============================================================
echo [ОШИБКА] Панель остановилась!
echo ============================================================
pause
