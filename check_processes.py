#!/usr/bin/env python3
"""
Контrole процессов бота - Контrole множественных экземпляров
"""
import subprocess
import sys

def check_бот_procesголос():
    """Работающие процессы бота'lerini контrole et"""
    try:
        # Python main.py process'lerini bul
        result = subprocess.run(
            'wmic process where "commandline like \'%main.py%\'" get processid,commandline',
            shell=True,
            capture_output=True,
            text=True
        )
        
        lines = result.stdout.strip().split('\n')
        procesголос = []
        
        for line in lines[1:]:  # Первая строка - заголовок
            if line.strip() and 'main.py' in line:
                procesголос.append(line.strip())
        
        print(f"[INFO] Количество найденных процессов бота: {len(procesголос)}")
        
        if len(procesголос) > 1:
            print("[WARNING] Работает несколько процессов бота!")
            for i, proc in enumerate(procesголос, 1):
                print(f"  {i}. {proc}")
            return True
        elif len(procesголос) == 1:
            print("[OK] Работает один процесс бота")
            print(f"  {procesголос[0]}")
            return False
        else:
            print("[INFO] Процессы бота не найдены")
            return False
            
    except Exception as e:
        print(f"[ERROR] Ошибка контроля процессов: {e}")
        return False

def kill_all_бот_procesголос():
    """Все завершить все процессы бота"""
    try:
        print("[INFO] Все процессы бота'leri завершаются...")
        
        # Python process'lerini завершить
        subprocess.run('taskkill /f /im python.exe', shell=True, capture_output=True)
        
        # Cloudflared process'lerini завершить
        subprocess.run('taskkill /f /im cloudflared.exe', shell=True, capture_output=True)
        
        print("[OK] Process'ler завершены")
        
    except Exception as e:
        print(f"[ERROR] Ошибка завершения процесса: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "kill":
        kill_all_бот_procesголос()
    else:
        check_бот_procesголос()