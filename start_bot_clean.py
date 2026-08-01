#!/usr/bin/env python3
"""
Temiz bot запуск scripti - Старый process'leri clearr ve новый bot запуск
"""
import subprocess
import time
import os
import sys

def kill_existing_processes():
    """Текущий bot process'lerini заверш"""
    print("[CLEANUP] Текущий bot process'leri заверш...")
    
    try:
        # Python main.py process'lerini заверш
        subprocess.run('taskkill /f /im python.exe', shell=True, capture_output=True)
        
        # Cloudflared process'lerini заверш 
        subprocess.run('taskkill /f /im cloudflared.exe', shell=True, capture_output=True)
        
        # WMIC с spesifik команда satыrы olan process'leri заверш
        subprocess.run('wmic process where "commandline like \'%main.py%\'" delete', shell=True, capture_output=True)
        
        print("[CLEANUP] Process'ler завершено")
        
    except Exception as e:
        print(f"[ERROR] Ошибка заверш действие: {e}")

def wait_for_cleanup():
    """Process'lerin tamamen kapanmasыnы bимяd"""
    print("[WAIT] Process'lerin kapanmasы ojidaetsya...")
    time.sleep(5)

def start_bot():
    """Bot'u запустить"""
    print("[START] Bot запуск...")
    
    try:
        # Bot'u новый console'da запустить
        subprocess.Popen(
            "python main.py",
            shell=True,
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )
        print("[OK] Bot запущено!")
        
    except Exception as e:
        print(f"[ERROR] Bot запуск ошибки: {e}")

def main():
    print("=" * 50)
    print("Aether Bot - Temiz Запуск")
    print("=" * 50)
    
    # 1. Текущий process'leri заверш
    kill_existing_processes()
    
    # 2. Temizlik для bимяd
    wait_for_cleanup()
    
    # 3. Bot'u запустить
    start_bot()
    
    print("[INFO] Действие завершено!")

if __name__ == "__main__":
    main()