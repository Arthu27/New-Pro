#!/usr/bin/env python3
"""
GitHub Webhook Auto-Update Script
GitHub'a push edildiğinde VDS'deki ботu otomatik обновитьr
"""
import os
import subprocess
import shutil
import zipfile
import requests
from flask import Flask, request, jsonify
import threading
import time

app = Flask(__name__)

# Konfigürasyon
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
REPO_URL = "https://github.com/Arthu27/Aether-бот"
BOT_DIR = "C:/Users/Имяministrator/Aether-бот-main"
BACKUP_DIR = "C:/Users/Имяministrator/Aether-бот-backup"

def update_бот():
    """Ботu обновить"""
    try:
        print("[UPDATE] Обновитьme başlıyor...")
        
        # Mevcut ботu остановить (process kill)
        subprocess.run("taskkill /f /im python.exe", shell=True, capture_output=True)
        time.sleep(3)
        
        # Backup создать
        if os.path.exists(BOT_DIR):
            if os.path.exists(BACKUP_DIR):
                shutil.rmtree(BACKUP_DIR)
            shutil.copytree(BOT_DIR, BACKUP_DIR)
            print("[UPDATE] Backup создатьuldu")
        
        # Новый versiyonu indir
        zip_url = f"{REPO_URL}/archive/refs/heads/main.zip"
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        
        response = requests.get(zip_url, headers=headers)
        if response.status_code != 200:
            raise Exception(f"Скачатьme ошибкаsı: {response.status_code}")
        
        # ZIP'i сохранить ve aç
        zip_path = "C:/Users/Имяministrator/Aether-update.zip"
        with open(zip_path, "wb") as f:
            f.write(response.content)
        
        # Старый klasörü sil
        if os.path.exists(BOT_DIR):
            shutil.rmtree(BOT_DIR)
        
        # ZIP'i aç
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall("C:/Users/Имяministrator/")
        
        # .env dosyasını geri kopyala (backup'tan veya template'ten)
        env_template = """TOKEN=YOUR_BOT_TOKEN_HERE
GROQ_API_KEY=YOUR_GROQ_API_KEY
MISTRAL_API_KEY=YOUR_MISTRAL_API_KEY
OWNER_ID=987430047889637426"""
        
        with open(f"{BOT_DIR}/.env", "w", encoding="utf-8") as f:
            f.write(env_template)
        
        # Cleanup
        os.remove(zip_path)
        
        print("[UPDATE] Dosyalar обновитьndi")
        
        # Ботu yeniden запустить
        time.sleep(2)
        subprocess.Popen(["python", "main.py"], cwd=BOT_DIR, shell=True)
        print("[UPDATE] Бот yeniden запуститьıldı")
        
        return True
        
    except Exception as e:
        print(f"[UPDATE] Ошибка: {e}")
        # Backup'tan geri yükle
        if os.path.exists(BACKUP_DIR):
            if os.path.exists(BOT_DIR):
                shutil.rmtree(BOT_DIR)
            shutil.copytree(BACKUP_DIR, BOT_DIR)
            subprocess.Popen(["python", "main.py"], cwd=BOT_DIR, shell=True)
            print("[UPDATE] Backup'tan geri yüklendi")
        return False

@app.route('/webhook', methods=['POST'])
def github_webhook():
    """GitHub webhook endpoint"""
    try:
        # GitHub signature doğrulama (basit)
        if request.headers.get('X-GitHub-Event') == 'push':
            payload = request.get_json()
            
            # main branch'e push контroleü
            if payload.get('ref') == 'refs/heads/main':
                print("[WEBHOOK] Push algılandı, обновитьme запуститьılıyor...")
                
                # Обновитьmeyi ayrı thread'de çalıştır
                threading.Thread(target=update_bot, daemon=True).start()
                
                return jsonify({"status": "success", "message": "Update started"}), 200
            else:
                return jsonify({"status": "ignored", "message": "Not main branch"}), 200
        else:
            return jsonify({"status": "ignored", "message": "Not a push event"}), 200
            
    except Exception as e:
        print(f"[WEBHOOK] Ошибка: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/status')
def status():
    """Статус контroleü"""
    return jsonify({
        "status": "running",
        "бот_running": os.path.exists(f"{BOT_DIR}/main.py")
    })

@app.route('/manual-update', methods=['POST'])
def manual_update():
    """Manuel обновитьme"""
    threading.Thread(target=update_bot, daemon=True).start()
    return jsonify({"status": "success", "message": "Manual update started"})

if __name__ == '__main__':
    print("[WEBHOOK] GitHub Auto-Update servisi запуститьılıyor...")
    print("[WEBHOOK] Webhook URL: http://localhost:5002/webhook")
    print("[WEBHOOK] Manuel обновитьme: http://localhost:5002/manual-update")
    app.run(host='0.0.0.0', port=5002, debug=False)