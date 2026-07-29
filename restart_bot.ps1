# Tüm Python process'lerini öldür
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force

# 2 saniye bekle
Start-Sleep -Seconds 2

# Yeni botu başlat
python main.py
