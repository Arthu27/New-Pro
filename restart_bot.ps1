# Tюm Python process'lerini ёldюr
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force

# 2 секунд bekle
Start-Sleep -Seconds 2

# Bot dizinine geç (verilerin doğru yerde tutulması için)
Set-Location -Path $PSScriptRoot

# Yeni botu baшlat
python main.py
