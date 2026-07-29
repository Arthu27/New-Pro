import time
import requests
import subprocess
import os
import zipfile
import sys

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
REPO_API = "https://api.github.com/repos/Arthu27/moebius-bot/commits/main"
ZIP_URL = "https://github.com/Arthu27/moebius-bot/archive/refs/heads/main.zip"

# Script'in найден dizini автоматически определить (VSCode workspace)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BOT_DIR = SCRIPT_DIR  # VSCode workspace'ini использовать
LAST_COMMIT_FILE = os.path.join(BOT_DIR, "last_commit.txt")
BOT_LOG = os.path.join(BOT_DIR, "bot_output.log")

# .env содержимое теперь .env dosyasından okunur, здесь hardcoded değildir
ENV_CONTENT = """TOKEN=YOUR_BOT_TOKEN_HERE
GROQ_API_KEY=YOUR_GROQ_API_KEY
MISTRAL_API_KEY=YOUR_MISTRAL_API_KEY
OWNER_ID=987430047889637426"""

MY_PID = os.getpid()


def log(msg):
    print(msg, flush=True)


def get_remote_commit():
    """GitHub API'den son commit hash'ini al"""
    try:
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        r = requests.get(REPO_API, headers=headers, timeout=10)
        if r.status_code == 200:
            return r.json()["sha"]
    except Exception as e:
        log(f"[AUTO-UPDATE] Commit alma ошибки: {e}")
    return None


def get_local_commit():
    """Local git repo'dan HEAD commit hash'ini al"""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=BOT_DIR, capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def get_last_commit():
    """Для geri sovmestimosti"""
    return get_remote_commit()


def is_bot_running():
    """main.py process'i работает mu контроль et"""
    try:
        result = subprocess.run(
            'wmic process where "commandline like \'%main.py%\'" get processid',
            shell=True, capture_output=True, text=True
        )
        for line in result.stdout.strip().split('\n'):
            line = line.strip()
            if line.isdigit() and int(line) != MY_PID:
                return True
    except Exception:
        pass
    return False


def kill_bot():
    """Только main.py process'lerini oldur"""
    try:
        result = subprocess.run(
            'wmic process where "commandline like \'%main.py%\'" get processid',
            shell=True, capture_output=True, text=True
        )
        for line in result.stdout.strip().split('\n'):
            line = line.strip()
            if line.isdigit():
                pid = int(line)
                if pid != MY_PID:
                    subprocess.run(f'taskkill /f /pid {pid}', shell=True, capture_output=True)
                    log(f"[AUTO-UPDATE] Bot process закрыто (PID: {pid})")
    except Exception as e:
        log(f"[AUTO-UPDATE] Kill ошибки: {e}")

    subprocess.run('taskkill /f /im cloudflared.exe', shell=True, capture_output=True)
    time.sleep(4)


def start_bot():
    """Botu arka planda baslatir, log dosyasina yazar"""
    try:
        os.makedirs(BOT_DIR, exist_ok=True)
        
        # main.py'nin tam yolunu al
        main_py = os.path.join(BOT_DIR, "main.py")
        if not os.path.exists(main_py):
            log(f"[AUTO-UPDATE] ОШИБКА: main.py не найдено: {main_py}")
            return False
        
        # data/ klasörünü контроль et
        data_dir = os.path.join(BOT_DIR, "data")
        os.makedirs(data_dir, exist_ok=True)
        
        # .env dosyasını контроль et
        env_file = os.path.join(BOT_DIR, ".env")
        if not os.path.exists(env_file):
            log("[AUTO-UPDATE] .env не найдено, olusturuluyor...")
            with open(env_file, "w", encoding="utf-8") as f:
                f.write(ENV_CONTENT)
        
        log(f"[AUTO-UPDATE] Bot dizini: {BOT_DIR}")
        log(f"[AUTO-UPDATE] Python: {sys.executable}")
        log(f"[AUTO-UPDATE] main.py: {main_py}")
        
        log_file = open(BOT_LOG, 'w', encoding='utf-8', errors='replace')
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        proc = subprocess.Popen(
            [sys.executable, main_py],
            cwd=BOT_DIR,
            stdout=log_file,
            stderr=log_file,
            stdin=subprocess.DEVNULL,
            env=env,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP  # Signal izolasyonu
        )
        log(f"[AUTO-UPDATE] Bot çalıştırıldı! PID: {proc.pid} | Log: {BOT_LOG}")
        
        # 3 saniye badd ve process'in hala çalıştığını контроль et
        time.sleep(3)
        if proc.poll() is not None:
            log(f"[AUTO-UPDATE] ПРЕДУПРЕЖДЕНИЕ: Bot hemen kapandi! Exit code: {proc.returncode}")
            log(f"[AUTO-UPDATE] Log dosyasini контроль et: {BOT_LOG}")
            return False
        
        return True
    except Exception as e:
        log(f"[AUTO-UPDATE] Bot baslatma ОШИБКА: {e}")
        import traceback
        log(traceback.format_exc())
        return False


def git_pull():
    """git pull с repoyu guncelle"""
    log("[AUTO-UPDATE] git pull yapiliyor...")
    try:
        result = subprocess.run(
            ["git", "pull", "origin", "main"],
            cwd=BOT_DIR,
            capture_output=True,
            text=True,
            timeout=60
        )
        log(f"[AUTO-UPDATE] git pull stdout: {result.stdout.strip()}")
        if result.returncode != 0:
            log(f"[AUTO-UPDATE] git pull stderr: {result.stderr.strip()}")
            # Conflict varsa force reset yap
            log("[AUTO-UPDATE] Conflict algilandi, force reset yapiliyor...")
            subprocess.run(["git", "fetch", "origin"], cwd=BOT_DIR, capture_output=True, timeout=30)
            subprocess.run(["git", "reset", "--hard", "origin/main"], cwd=BOT_DIR, capture_output=True, timeout=30)
            log("[AUTO-UPDATE] Force reset завершено")
        else:
            log("[AUTO-UPDATE] Dosyalar обновлено")

        # .env yoksa olustur
        env_path = os.path.join(BOT_DIR, ".env")
        if not os.path.exists(env_path):
            with open(env_path, "w", encoding="utf-8") as f:
                f.write(ENV_CONTENT)
            log("[AUTO-UPDATE] .env создано")

    except Exception as e:
        raise Exception(f"git pull ошибки: {e}")


def download_and_extract():
    """GitHub'dan ZIP indir ve BOT_DIR'e ac (fallback)"""
    log("[AUTO-UPDATE] Dosyalar indiriliyor...")
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    r = requests.get(ZIP_URL, headers=headers, timeout=60)
    if r.status_code != 200:
        raise Exception(f"Indirme ошибки HTTP {r.status_code}")

    zip_path = os.path.join(BOT_DIR, "aether-update.zip")
    with open(zip_path, "wb") as f:
        f.write(r.content)
    log(f"[AUTO-UPDATE] ZIP indirildi ({len(r.content)//1024} KB)")

    with zipfile.ZipFile(zip_path, 'r') as zf:
        for member in zf.infolist():
            target = member.filename.replace("moebius-bot-main/", "", 1).replace("aether-bot-main/", "", 1)
            if not target:
                continue
            target_path = os.path.join(BOT_DIR, target)
            if target.startswith("data/"):
                continue
            if member.is_dir():
                os.makedirs(target_path, exist_ok=True)
            else:
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                try:
                    with zf.open(member) as src, open(target_path, 'wb') as dst:
                        dst.write(src.read())
                except Exception as e:
                    log(f"[AUTO-UPDATE] Dosya yazma ошибки ({target}): {e}")

    os.remove(zip_path)
    log("[AUTO-UPDATE] Dosyalar обновлено (ZIP)")

    env_path = os.path.join(BOT_DIR, ".env")
    if not os.path.exists(env_path):
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(ENV_CONTENT)
        log("[AUTO-UPDATE] .env создано")


def update_bot():
    log("[AUTO-UPDATE] === GUNCELLEME BASLADI ===")
    try:
        kill_bot()
        # До git pull dene, git repo değilse ZIP fallback
        git_dir = os.path.join(BOT_DIR, ".git")
        if os.path.isdir(git_dir):
            git_pull()
        else:
            log("[AUTO-UPDATE] .git не найдено, ZIP с guncelleniyor...")
            download_and_extract()
        time.sleep(2)
        start_bot()
        log("[AUTO-UPDATE] === GUNCELLEME ЗАВЕРШЕНО ===")
    except Exception as e:
        log(f"[AUTO-UPDATE] Guncelleme ошибки: {e}")
        log("[AUTO-UPDATE] Ошибка oldu, bot yeniden baslatiliyor...")
        start_bot()


def main():
    log(f"[AUTO-UPDATE] Çalıştırıldı (PID: {MY_PID})")
    log(f"[AUTO-UPDATE] Script dizini: {SCRIPT_DIR}")
    log(f"[AUTO-UPDATE] Bot dizini: {BOT_DIR}")
    log(f"[AUTO-UPDATE] Python: {sys.executable}")
    
    # Проверка необходимых файлов
    main_py = os.path.join(BOT_DIR, "main.py")
    if not os.path.exists(main_py):
        log(f"[AUTO-UPDATE] KRITIK ОШИБКА: main.py не найдено: {main_py}")
        log("[AUTO-UPDATE] Lutfen script'i bot dizininde calistirin!")
        return
    
    log("[AUTO-UPDATE] GitHub polling çalıştırıldı (5 saniye)...")

    # Ilk контроль bot calismiyorsa hemen baslatir
    if not is_bot_running():
        log("[AUTO-UPDATE] Bot не работает, zapuskaetsya...")
        if not start_bot():
            log("[AUTO-UPDATE] Bot baslatma неудачно! Log dosyasini контроль edin:")
            log(f"[AUTO-UPDATE] {BOT_LOG}")
            return
        time.sleep(5)

    while True:
        try:
            # git fetch yap, remote'daki son hash'i al
            subprocess.run(["git", "fetch", "origin"], cwd=BOT_DIR, capture_output=True, timeout=30)
            
            # Remote HEAD hash'ini al
            result = subprocess.run(
                ["git", "rev-parse", "origin/main"],
                cwd=BOT_DIR, capture_output=True, text=True, timeout=10
            )
            remote_hash = result.stdout.strip() if result.returncode == 0 else None

            if remote_hash:
                local_hash = get_local_commit() or ""
                if remote_hash != local_hash:
                    log(f"[AUTO-UPDATE] Новый commit algilandi: {remote_hash[:8]} (local: {local_hash[:8]})")
                    update_bot()

            # Bot calismiyor mu контроль et
            if not is_bot_running():
                log("[AUTO-UPDATE] Bot durdu! Yeniden baslatiliyor...")
                if not start_bot():
                    log("[AUTO-UPDATE] Bot yeniden baslatma неудачно!")
                time.sleep(10)

            time.sleep(30)

        except KeyboardInterrupt:
            log("[AUTO-UPDATE] Пользователь сканироватьfindan durduruldu")
            break
        except Exception as e:
            log(f"[AUTO-UPDATE] Ana dongu ошибки: {e}")
            import traceback
            log(traceback.format_exc())
            time.sleep(10)


if __name__ == "__main__":
    main()
