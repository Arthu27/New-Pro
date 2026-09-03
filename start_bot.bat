@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title Hakumo Bot

echo ============================================================
echo   HAKUMO BOT
echo ============================================================
echo.

:: Проверка Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ОШИБКА] Python не найден!
    echo Установите Python 3.12 с https://python.org
    echo Обязательно отметьте галочку "Add Python to PATH".
    echo.
    pause
    exit /b 1
)

:: .env с токеном
if not exist ".env" (
    echo [ВНИМАНИЕ] Файл .env не найден — создаю из шаблона.
    if exist ".env.example" copy ".env.example" ".env" >nul
    echo Откройте .env блокнотом и впишите TOKEN=ваш_токен, затем запустите снова.
    notepad ".env"
    pause
    exit /b 0
)

echo [ОК] Конфигурация найдена (.env)
echo Лог запуска пишется в файл: logs\start_console.log

:: FFmpeg-блок убран вместе с системой музыки /play (2026-09-01).
echo.

:: Авто-перезапуск при падении процесса (как на Linux в start.sh).
:: Внутри main.py свой цикл переподключения к Discord; сюда попадаем,
:: только если упал сам процесс. Код выхода 7 = неверный токен (чинить .env).
if not exist "logs" mkdir "logs"
:runloop
rem Если прямо сейчас идёт обновление (бот поставил метку перед запуском
rem обновлятора) - старый процесс НЕ воскрешаем: иначе он поднимется
rem посреди замены файлов и обновление сорвётся. Метка старше 15 минут
rem считается протухшей (обновлятор мог упасть) - тогда перезапускаем.
python -c "import os,sys,time;p=os.path.join('data','.updating');sys.exit(0 if os.path.exists(p) and time.time()-os.path.getmtime(p)<900 else 1)" >nul 2>&1
if not errorlevel 1 (
    echo [ОБНОВЛЕНИЕ] Идёт обновление бота - старый процесс не перезапускается.
    echo Это окно можно закрыть.
    exit /b 0
)
echo [%date% %time%] === Запуск бота === >> "logs\start_console.log"
python -X utf8 main.py >> "logs\start_console.log" 2>&1
set EXITCODE=%ERRORLEVEL%
echo.
echo [%date% %time%] Бот остановился (код %EXITCODE%). >> "logs\start_console.log"
if "%EXITCODE%"=="7" (
    echo.
    echo [ОШИБКА] Неверный токен Discord (код 7).
    echo Откройте .env и исправьте строку TOKEN=... — перезапуск не поможет.
    echo Подробности: logs\start_console.log
    echo.
    pause
    exit /b 7
)
echo [ПЕРЕЗАПУСК] Процесс завершился (код %EXITCODE%) — перезапуск через 5 секунд...
echo Полный лог ошибок смотрите в logs\start_console.log и logs\bot_errors.log
timeout /t 5 /nobreak >nul
goto runloop
