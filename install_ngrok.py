#!/usr/bin/env python3
"""ngrok'u indirir ve token'ы настройки"""
import urllib.request
import zipfile
import os
import subprocess

TOKEN = "3BB4QVP47XqrznuOoAadg0DbzLb_4Bww5UbRdSsaUZvRKCrns"
URL = "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-windows-amd64.zip"

print("ngrok indiriliyor...")
try:
    urllib.request.urlretrieve(URL, "ngrok.zip")
    with zipfile.ZipFile("ngrok.zip", "r") as z:
        z.extractall(".")
    os.remove("ngrok.zip")
    print("✅ ngrok indirildi")
except Exception as e:
    print(f"❌ Indirme ошибки: {e}")
    exit(1)

# Token настройк
result = subprocess.run(["ngrok.exe", "config", "add-authtoken", TOKEN], capture_output=True, text=True)
print(result.stdout or result.stderr)
print("✅ Token настройк")
