#!/usr/bin/env python3
"""
GitHub Webhook Auto-Update Script
GitHub'a push edildiгinde VDS'deki botu автоматически обновл
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

# Konfigюrasyon
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
REPO_URL = "https://github.com/Arthu27/Aether-bot"
BOT_DIR = "C:/Users/Иsmininistrator/Aether-bot-main"
BACKUP_DIR = "C:/Users/Иsmininistrator/Aether-bot-backup"

def update_bot():
    """Botu обновить"""
    try:
        print("[UPDATE] Обновл baшlыyor...")
        
        # Текущий botu остановить (process kill)
        subprocess.run("taskkill /f /im python.exe", shell=True, capture_output=True)
        time.sleep(3)
        
        # Backup создать
        if os.path.exists(BOT_DIR):
            if os.path.exists(BACKUP_DIR):
                shutil.rmtree(BACKUP_DIR)
            shutil.copytree(BOT_DIR, BACKUP_DIR)
            print("[UPDATE] Backup создано")
        
        # Новый версийu indir
        zip_url = f"{REPO_URL}/archive/refs/heads/main.zip"
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        
        response = requests.get(zip_url, headers=headers)
        if response.status_code != 200:
            raise Exception(f"Indirme ошибки: {response.status_code}")
        
        # ZIP'i сохранить ve открыть
        zip_path = "C:/Users/Иsmininistrator/Aether-update.zip"
        with open(zip_path, "wb") as f:
            f.write(response.content)
        
        # Старый klasёrю удалить
        if os.path.exists(BOT_DIR):
            shutil.rmtree(BOT_DIR)
        
        # ZIP'i открыть
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall("C:/Users/Иsmininistrator/")
        
        # .env файл geri kopyala (backup'tan или template'ten)
        env_template = """TOKEN=YOUR_BOT_TOKEN_HERE
GROQ_API_KEY=YOUR_GROQ_API_KEY
MISTRAL_API_KEY=YOUR_MISTRAL_API_KEY
OWNER_ID=987430047889637426"""
        
        with open(f"{BOT_DIR}/.env", "w", encoding="utf-8") as f:
            f.write(env_template)
        
        # Cleanup
        os.remove(zip_path)
        
        print("[UPDATE] Dosyalar обновлено")
        
        # Botu yeniden запустить
        time.sleep(2)
        subprocess.Popen(["python", "main.py"], cwd=BOT_DIR, shell=True)
        print("[UPDATE] Bot yeniden запущено")
        
        return True
        
    except Exception as e:
        print(f"[UPDATE] Ошибка: {e}")
        # Backup'tan geri загрузить
        if os.path.exists(BACKUP_DIR):
            if os.path.exists(BOT_DIR):
                shutil.rmtree(BOT_DIR)
            shutil.copytree(BACKUP_DIR, BOT_DIR)
            subprocess.Popen(["python", "main.py"], cwd=BOT_DIR, shell=True)
            print("[UPDATE] Backup'tan geri загружено")
        return False

@app.route('/webhook', methods=['POST'])
def github_webhook():
    """GitHub webhook endpoint"""
    try:
        # GitHub signature проверка (basit)
        if request.headers.get('X-GitHub-Event') == 'push':
            payload = request.get_json()
            
            # main branch'e push контроль
            if payload.get('ref') == 'refs/heads/main':
                print("[WEBHOOK] Push algыlandы, обновл запуск...")
                
                # Обновл отдельно thread'de работатьtыr
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
    """Состояние контроль"""
    return jsonify({
        "status": "running",
        "bot_running": os.path.exists(f"{BOT_DIR}/main.py")
    })

@app.route('/manual-update', methods=['POST'])
def manual_update():
    """Manuel обновл"""
    threading.Thread(target=update_bot, daemon=True).start()
    return jsonify({"status": "success", "message": "Manual update started"})

if __name__ == '__main__':
    print("[WEBHOOK] GitHub Auto-Update servisi запуск...")
    print("[WEBHOOK] Webhook URL: http://localhost:5002/webhook")
    print("[WEBHOOK] Manuel обновл: http://localhost:5002/manual-update")
    app.run(host='0.0.0.0', port=5002, debug=False)