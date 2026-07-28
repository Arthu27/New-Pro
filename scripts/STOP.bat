@echo off
title ProBotum - Portlari Kapat
color 0C
echo.
echo  ============================================
echo     ProBotum - Portlari Temizle
echo  ============================================
echo.
echo  Port 5173 (Dashboard) ve 3000 (API) kapatilacak.
echo.
pause

for /f "tokens=5" %%a in ('netstat -ano ^| findstr :5173 ^| findstr LISTENING') do (
    echo  Port 5173 - PID %%a kapatiliyor...
    taskkill /PID %%a /F >nul 2>nul
)

for /f "tokens=5" %%a in ('netstat -ano ^| findstr :3000 ^| findstr LISTENING') do (
    echo  Port 3000 - PID %%a kapatiliyor...
    taskkill /PID %%a /F >nul 2>nul
)

echo.
echo  [OK] Portlar temizlendi.
echo.
pause
