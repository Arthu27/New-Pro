@echo off
title Moebius Bot - Baslatiliyor...
color 0A

echo.
echo  ╔═══════════════════════════════════════╗
echo  ║       MOEBIUS BOT BASLATILIYOR        ║
echo  ╚═══════════════════════════════════════╝
echo.

REM Python kontrolu
python --version >nul 2>&1
if errorlevel 1 (
    echo  [HATA] Python bulunamadi!
    echo  Lutfen Python 3.8+ yukleyin: https://python.org
    echo.
    pause
    exit /b 1
)

echo  [OK] Python bulundu
echo.

REM .env dosyasi kontrolu
if not exist .env (
    echo  [UYARI] .env dosyasi bulunamadi!
    echo.
    echo  Lutfen .env dosyasini olusturun ve asagidaki bilgileri ekleyin:
    echo.
    echo  TOKEN=your_discord_bot_token
    echo  MAIN_GUILD_ID=your_server_id
    echo  OWNER_ID=your_discord_id
    echo  MISTRAL_API_KEY=your_mistral_api_key
    echo  OPENROUTER_API_KEY=your_openrouter_api_key
    echo  GITHUB_TOKEN=your_github_token
    echo  VOICE_SECRET=Aether-voice-2024
    echo.
    echo  .env ornegi olusturuluyor...
    (
        echo # Discord Bot Token
        echo TOKEN=YOUR_BOT_TOKEN_HERE
        echo.
        echo # Ana Sunucu ID
        echo MAIN_GUILD_ID=YOUR_SERVER_ID
        echo.
        echo # Bot Sahibi Discord ID
        echo OWNER_ID=YOUR_DISCORD_ID
        echo.
        echo # AI API Keys
        echo MISTRAL_API_KEY=YOUR_MISTRAL_KEY
        echo.
        echo # OpenRouter API Keys
        echo OPENROUTER_API_KEY=YOUR_OPENROUTER_KEY
        echo.
        echo # GitHub Token
        echo GITHUB_TOKEN=YOUR_GITHUB_TOKEN
        echo.
        echo # Sesli Komut
        echo VOICE_SECRET=Aether-voice-2024
    ) > .env
    echo.
    echo  [OK] .env ornegi olusturuldu!
    echo  Lutfen .env dosyasini acip kendi bilgilerini yaz.
    echo.
    pause
    exit /b 0
)

echo  [OK] .env dosyasi bulundu
echo.
echo  [INFO] Bot baslatiliyor...
echo.
python main.py

if errorlevel 1 (
    echo.
    echo  [HATA] Bot beklenmedik sekilde kapandi!
    pause
)
