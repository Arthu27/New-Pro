@echo off
cd /d "%~dp0"
title ProBotum - Demo Data Seed
color 0E

echo.
echo  ============================================
echo     ProBotum - Demo Data Yukle
echo  ============================================
echo.
echo  Bu, API'nin test verisi olmadan da
echo  calismasi icin demo data olusturur.
echo.
echo  Guild ID: 1524635551804686486
echo  Test users: artur, lega, admin
echo  Test channels: welcome, general, tickets...
echo  Test roles: Owner, Admin, Moderator...
echo.

python -m server.dev_seed

echo.
echo  [OK] Demo data yuklendi!
echo  Simdi START_FULL.bat ile baslat.
echo.
pause
