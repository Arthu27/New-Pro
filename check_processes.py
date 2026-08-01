#!/usr/bin/env python3
"""
Контроль действия botun - Контроль mnojestvennih пример
"""
import subprocess
import sys

def check_bot_processes():
    """Работа действия botun'lerini контроль et"""
    try:
        # Python main.py process'lerini найти
        result = subprocess.run(
            'wmic process where "commandline like \'%main.py%\'" get processid,commandline',
            shell=True,
            capture_output=True,
            text=True
        )
        
        lines = result.stdout.strip().split('\n')
        processes = []
        
        for line in lines[1:]:  # Pervaya satыr - заголовок
            if line.strip() and 'main.py' in line:
                processes.append(line.strip())
        
        print(f"[INFO] Число найден действия botun: {len(processes)}")
        
        if len(processes) > 1:
            print("[WARNING] Работает neskolko действия botun!")
            for i, proc in enumerate(processes, 1):
                print(f" {i}. {proc}")
            return True
        elif len(processes) == 1:
            print("[OK] Работает bir process botun")
            print(f" {processes[0]}")
            return False
        else:
            print("[INFO] Действия botun не найден")
            return False
            
    except Exception as e:
        print(f"[ERROR] Ошибка контроль действия: {e}")
        return False

def kill_all_bot_processes():
    """Все заверш все действия botun"""
    try:
        print("[INFO] Все действия botun'leri заверш...")
        
        # Python process'lerini заверш
        subprocess.run('taskkill /f /im python.exe', shell=True, capture_output=True)
        
        # Cloudflared process'lerini заверш
        subprocess.run('taskkill /f /im cloudflared.exe', shell=True, capture_output=True)
        
        print("[OK] Process'ler завершено")
        
    except Exception as e:
        print(f"[ERROR] Ошибка заверш действие: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "kill":
        kill_all_bot_processes()
    else:
        check_bot_processes()