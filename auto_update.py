import time
import requests
import subprocess
import os
import zipfile
import sys

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
REPO_API = "https://api.github.com/repos/Arthu27/moebius-бот/commits/main"
ZIP_URL = "https://github.com/Arthu27/moebius-бот/archive/refs/heads/main.zip"

# Script'in найденоğu dizini otomatik tespit et (VSCode workspace)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BOT_DIR = SCRIPT_DIR  # VSCode workspace'ini kullan
LAST_COMMIT_FILE = os.path.join(BOT_DIR, "last_commit.txt")
BOT_LOG = os.path.join(BOT_DIR, "бот_output.log")

# .env içeriği artık .env dosyasından okunur, burada hardcoded değildir
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
        log(f"[AUTO-UPDATE] Commit alma ошибкаsi: {e}")
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
    """Для обратной совместимости"""
    return get_remote_commit()


def is_бот_running():
    """main.py process'i работает mu контrole et"""
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


def kill_бот():
    """Sadece main.py process'lerini oldur"""
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
                    log(f"[AUTO-UPDATE] Бот process закрытьildi (PID: {pid})")
    except Exception as e:
        log(f"[AUTO-UPDATE] Kill ошибкаsi: {e}")

    subprocess.run('taskkill /f /im cloudflared.exe', shell=True, capture_output=True)
    time.sleep(4)


def start_бот():
    """Ботu arka planda baslatir, log dosyasina записатьar"""
    try:
        os.makedirs(BOT_DIR, exist_ok=True)
        
        # main.py'nin tam yolunu al
        main_py = os.path.join(BOT_DIR, "main.py")
        if not os.path.exists(main_py):
            log(f"[AUTO-UPDATE] HATA: main.py bulunamadi: {main_py}")
            return False
        
        # data/ klasörünü контrole et
        data_dir = os.path.join(BOT_DIR, "data")
        os.makedirs(data_dir, exist_ok=True)
        
        # .env dosyasını контrole et
        env_file = os.path.join(BOT_DIR, ".env")
        if not os.path.exists(env_file):
            log("[AUTO-UPDATE] .env bulunamadi, olusturuluyor...")
            with open(env_file, "w", encoding="utf-8") as f:
                f.write(ENV_CONTENT)
        
        log(f"[AUTO-UPDATE] Бот dizini: {BOT_DIR}")
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
        log(f"[AUTO-UPDATE] Бот запущено! PID: {proc.pid} | Лог: {BOT_LOG}")
        
        # 3 saniye badd ve process'in hala çalıştığını контrole et
        time.sleep(3)
        if proc.poll() is not None:
            log(f"[AUTO-UPDATE] UYARI: Бот hemen kapandi! Exit code: {proc.returncode}")
            log(f"[AUTO-UPDATE] Лог dosyasini контrole et: {BOT_LOG}")
            return False
        
        return True
    except Exception as e:
        log(f"[AUTO-UPDATE] Бот baslatma HATASI: {e}")
        import traceback
        log(traceback.format_exc())
        return False


def git_pull():
    """git pull ile repoyu guncelle"""
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
        raise Exception(f"git pull ошибкаsi: {e}")


def download_and_extract():
    """GitHub'dan ZIP indir ve BOT_DIR'e ac (fallback)"""
    log("[AUTO-UPDATE] Dosyalar indiriliyor...")
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    r = requests.get(ZIP_URL, headers=headers, timeout=60)
    if r.status_code != 200:
        raise Exception(f"Indirme ошибкаsi HTTP {r.status_code}")

    zip_path = os.path.join(BOT_DIR, "aether-update.zip")
    with open(zip_path, "wb") as f:
        f.write(r.content)
    log(f"[AUTO-UPDATE] ZIP indirildi ({len(r.content)//1024} KB)")

    with zipfile.ZipFile(zip_path, 'r') as zf:
        for member in zf.infolist():
            target = member.filename.replace("moebius-бот-main/", "", 1).replace("aether-бот-main/", "", 1)
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
                    log(f"[AUTO-UPDATE] Dosya записатьma ошибкаsi ({target}): {e}")

    os.remove(zip_path)
    log("[AUTO-UPDATE] Dosyalar обновлено (ZIP)")

    env_path = os.path.join(BOT_DIR, ".env")
    if not os.path.exists(env_path):
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(ENV_CONTENT)
        log("[AUTO-UPDATE] .env создано")


def update_бот():
    log("[AUTO-UPDATE] === GUNCELLEME BASLADI ===")
    try:
        kill_бот()
        # Önce git pull dene, git repo değilse ZIP fallback
        git_dir = os.path.join(BOT_DIR, ".git")
        if os.path.isdir(git_dir):
            git_pull()
        else:
            log("[AUTO-UPDATE] .git bulunamadi, ZIP ile guncelleniyor...")
            download_and_extract()
        time.sleep(2)
        start_бот()
        log("[AUTO-UPDATE] === GUNCELLEME TAMAMLANDI ===")
    except Exception as e:
        log(f"[AUTO-UPDATE] Guncelleme ошибкаsi: {e}")
        log("[AUTO-UPDATE] Ошибка oldu, bot yeniden baslatiliyor...")
        start_бот()


def main():
    log(f"[AUTO-UPDATE] Запущено (PID: {MY_PID})")
    log(f"[AUTO-UPDATE] Script dizini: {SCRIPT_DIR}")
    log(f"[AUTO-UPDATE] Бот dizini: {BOT_DIR}")
    log(f"[AUTO-UPDATE] Python: {sys.executable}")
    
    # Gerekli dosyaları контrole et
    main_py = os.path.join(BOT_DIR, "main.py")
    if not os.path.exists(main_py):
        log(f"[AUTO-UPDATE] KRITIK HATA: main.py bulunamadi: {main_py}")
        log("[AUTO-UPDATE] Lutfen script'i bot dizininde calistirin!")
        return
    
    log("[AUTO-UPDATE] GitHub polling запущено (5 saniye)...")

    # Ilk контrolede bot calismiyorsa hemen baslatir
    if not is_бот_running():
        log("[AUTO-UPDATE] Бот не работает, запускается...")
        if not start_бот():
            log("[AUTO-UPDATE] Бот baslatma неудачно! Лог dosyasini контrole edin:")
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
                    update_бот()

            # Бот calismiyor mu контrole et
            if not is_бот_running():
                log("[AUTO-UPDATE] Бот durdu! Новыйden baslatiliyor...")
                if not start_бот():
                    log("[AUTO-UPDATE] Бот yeniden baslatma неудачно!")
                time.sleep(10)

            time.sleep(30)

        except KeyboardInterrupt:
            log("[AUTO-UPDATE] Kullanici tarafindan остановлено")
            break
        except Exception as e:
            log(f"[AUTO-UPDATE] Ana dongu ошибкаsi: {e}")
            import traceback
            log(traceback.format_exc())
            time.sleep(10)


if __name__ == "__main__":
    main()
