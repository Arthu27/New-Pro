@echo off
chcp 65001 >nul 2>&1
title Aether Bot

echo ============================================================
echo   AETHER BOT - Запуск...
echo ============================================================
echo.

:: Проверка Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ОШИБКА] Python не найден!
    echo Установите Python с https://python.org
    echo При установке отметьте "Add Python to PATH"
    pause
    exit /b 1
)

:: Установка зависимостей
echo [1/3] Установка зависимостей...
pip install -r requirements.txt --quiet 2>nul
if errorlevel 1 (
    echo [ВНИМАНИЕ] Некоторые пакеты не установлены, пробуем с --pre...
    pip install -r requirements.txt --pre --quiet 2>nul
)
echo [OK] Зависимости установлены
echo.

:: Проверка .env
echo [2/3] Проверка конфигурации...
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo [ВНИМАНИЕ] Файл .env создан из .env.example
        echo Заполните TOKEN и другие настройки в файле .env
        echo.
        notepad ".env"
        echo После заполнения .env запустите start.bat снова
        pause
        exit /b 0
    ) else (
        echo [ОШИБКА] Файл .env не найден!
        pause
        exit /b 1
    )
)
echo [OK] Конфигурация найдена
echo.

:: Запуск бота
echo [3/3] Запуск бота...
echo ============================================================
echo.
python main.py

:: Если бот упал
echo.
echo ============================================================
echo [ОШИБКА] Бот остановлен!
echo ============================================================
pause
