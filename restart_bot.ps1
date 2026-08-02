# Tюm Python process'lerini ёldюr
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force

# 2 секунд bekle
Start-Sleep -Seconds 2

# Yeni botu baшlat
python main.py
