# Остановить все процессы Python
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force

# 2 секунд bekle
Start-Sleep -Seconds 2

# Bot dizinine geç (verilerin doğru yerde tutulması için)
Set-Location -Path $PSScriptRoot

# Запустить бота заново
python main.py
