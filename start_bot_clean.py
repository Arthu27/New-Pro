#!/usr/bin/env python3
"""
Temiz bot запуститьma scripti - Старый process'leri clearr ve yeni bot запуститьır
"""
import subprocess
import time
import os
import sys

def kill_existing_procesголос():
    """Mevcut bot process'lerini завершить"""
    print("[CLEANUP] Mevcut bot process'leri завершаются...")
    
    try:
        # Python main.py process'lerini завершить
        subprocess.run('taskkill /f /im python.exe', shell=True, capture_output=True)
        
        # Cloudflared process'lerini завершить  
        subprocess.run('taskkill /f /im cloudflared.exe', shell=True, capture_output=True)
        
        # WMIC ile spesifik команда satırı olan process'leri завершить
        subprocess.run('wmic process where "commandline like \'%main.py%\'" delete', shell=True, capture_output=True)
        
        print("[CLEANUP] Process'ler завершены")
        
    except Exception as e:
        print(f"[ERROR] Ошибка завершения процесса: {e}")

def wait_for_cleanup():
    """Process'lerin tamamen kapanmasını badd"""
    print("[WAIT] Process'lerin kapanması ожидается...")
    time.sleep(5)

def start_бот():
    """Бот'u запустить"""
    print("[START] Бот запуститьılıyor...")
    
    try:
        # Бот'u yeni console'da запустить
        subprocess.Popen(
            "python main.py",
            shell=True,
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )
        print("[OK] Бот запуститьıldı!")
        
    except Exception as e:
        print(f"[ERROR] Бот запуститьma ошибкаsı: {e}")

def main():
    print("=" * 50)
    print("Aether Бот - Temiz Запуститьma")
    print("=" * 50)
    
    # 1. Mevcut process'leri завершить
    kill_existing_procesголос()
    
    # 2. Temizlik için badd
    wait_for_cleanup()
    
    # 3. Бот'u запустить
    start_бот()
    
    print("[INFO] Действие завершено!")

if __name__ == "__main__":
    main()