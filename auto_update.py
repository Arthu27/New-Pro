import time
import requests
import subprocess
import os
import zipfile
import sys

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
REPO_API = "https://api.github.com/repos/Arthu27/moebius-bot/commits/main"
ZIP_URL = "https://github.com/Arthu27/moebius-bot/archive/refs/heads/main.zip"

# Автоматически определить директорию скрипта (VSCode workspace)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BOT_DIR = SCRIPT_DIR  # использовать workspace VSCode
LAST_COMMIT_FILE = os.path.join(BOT_DIR, "last_commit.txt")
BOT_LOG = os.path.join(BOT_DIR, "bot_output.log")

# содержимое .env теперь читается из файла .env, здесь не задано жёстко
ENV_CONTENT = """TOKEN=YOUR_BOT_TOKEN_HERE
GROQ_API_KEY=YOUR_GROQ_API_KEY
MISTRAL_API_KEY=YOUR_MISTRAL_API_KEY
OWNER_ID=987430047889637426"""

MY_PID = os.getpid()


def лог(msg):
    print(msg, flush=True)


def get_remote_commit():
    """GitHub API'den son commit hash'ini al"""
    try:
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        r = requests.get(REPO_API, headers=headers, timeout=10)
        if r.status_code == 200:
            return r.json()["sha"]
    except Exception as e:
        лог(f"[AUTO-UPDATE] Ошибка получения коммита: {e}")
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


def _find_bot_pids():
    """PID процессов main.py (кроме этого скрипта) — кроссплатформенно.

    Раньше использовался wmic/taskkill — это Windows-only, причём wmic
    удалён из Windows 11. Теперь основной путь — psutil (есть в
    requirements.txt), wmic оставлен как запасной вариант для старой Windows.
    """
    pids = []
    try:
        import psutil
    except ImportError:
        psutil = None
    if psutil is not None:
        for proc in psutil.process_iter(['pid', 'cmdline']):
            try:
                cmdline = proc.info.get('cmdline') or []
                if proc.pid != MY_PID and any('main.py' in str(part) for part in cmdline):
                    pids.append(proc.pid)
            except Exception:
                continue
    elif os.name == 'nt':
        try:
            result = subprocess.run(
                'wmic process where "commandline like \'%main.py%\'" get processid',
                shell=True, capture_output=True, text=True
            )
            for line in result.stdout.strip().split('\n'):
                line = line.strip()
                if line.isdigit() and int(line) != MY_PID:
                    pids.append(int(line))
        except Exception:
            pass
    return pids


def is_bot_running():
    """Проверить, работает ли процесс main.py"""
    return bool(_find_bot_pids())


def kill_bot():
    """Завершить только процессы main.py"""
    try:
        for pid in _find_bot_pids():
            try:
                if os.name == 'nt':
                    subprocess.run(f'taskkill /f /pid {pid}', shell=True, capture_output=True)
                else:
                    os.kill(pid, 15)  # SIGTERM
                лог(f"[AUTO-UPDATE] Bot process закрыто (PID: {pid})")
            except Exception as e:
                лог(f"[AUTO-UPDATE] Kill ошибки (PID {pid}): {e}")
    except Exception as e:
        лог(f"[AUTO-UPDATE] Kill ошибки: {e}")

    if os.name == 'nt':
        subprocess.run('taskkill /f /im cloudflared.exe', shell=True, capture_output=True)
    else:
        # Linux: мягко попросить cloudflared завершиться (если запущен)
        try:
            import psutil
            for proc in psutil.process_iter(['name']):
                if proc.info.get('name') == 'cloudflared':
                    proc.terminate()
        except Exception:
            pass
    time.sleep(4)


def start_bot():
    """Запускает бота в фоне, пишет в лог-файл"""
    try:
        os.makedirs(BOT_DIR, exist_ok=True)
        
        # main.py'nin tam yolunu al
        main_py = os.path.join(BOT_DIR, "main.py")
        if not os.path.exists(main_py):
            лог(f"[AUTO-UPDATE] ОШИБКА: main.py не найдено: {main_py}")
            return False
        
        # проверить папку data/
        data_dir = os.path.join(BOT_DIR, "data")
        os.makedirs(data_dir, exist_ok=True)
        
        # проверить файл .env
        env_file = os.path.join(BOT_DIR, ".env")
        if not os.path.exists(env_file):
            лог("[AUTO-UPDATE] .env не найден, создаётся...")
            with open(env_file, "w", encoding="utf-8") as f:
                f.write(ENV_CONTENT)
        
        лог(f"[AUTO-UPDATE] Директория бота: {BOT_DIR}")
        лог(f"[AUTO-UPDATE] Python: {sys.executable}")
        лог(f"[AUTO-UPDATE] main.py: {main_py}")
        
        log_file = open(BOT_LOG, 'w', encoding='utf-8', errors='replace')
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        # Изоляция сигналов: на Windows — CREATE_NEW_PROCESS_GROUP,
        # на Linux/macOS — отдельная сессия. Раньше флаг Windows передавался
        # безусловно и auto_update падал с AttributeError на Linux.
        popen_kwargs = {
            'cwd': BOT_DIR,
            'stdout': log_file,
            'stderr': log_file,
            'stdin': subprocess.DEVNULL,
            'env': env,
        }
        if os.name == 'nt':
            popen_kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs['start_new_session'] = True
        proc = subprocess.Popen([sys.executable, main_py], **popen_kwargs)
        лог(f"[AUTO-UPDATE] Бот запущен! PID: {proc.pid} | Лог: {BOT_LOG}")
        
        # ждём 3 секунды и проверяем, что процесс всё ещё работает
        time.sleep(3)
        if proc.poll() is not None:
            лог(f"[AUTO-UPDATE] ПРЕДУПРЕЖДЕНИЕ: Бот сразу завершился! Код выхода: {proc.returncode}")
            лог(f"[AUTO-UPDATE] Проверьте лог-файл: {BOT_LOG}")
            return False
        
        return True
    except Exception as e:
        лог(f"[AUTO-UPDATE] ОШИБКА запуска бота: {e}")
        import traceback
        лог(traceback.format_exc())
        return False


def git_pull():
    """Обновить репозиторий через git pull"""
    лог("[AUTO-UPDATE] Выполняется git pull...")
    try:
        result = subprocess.run(
            ["git", "pull", "origin", "main"],
            cwd=BOT_DIR,
            capture_output=True,
            text=True,
            timeout=60
        )
        лог(f"[AUTO-UPDATE] git pull stdout: {result.stdout.strip()}")
        if result.returncode != 0:
            лог(f"[AUTO-UPDATE] git pull stderr: {result.stderr.strip()}")
            # Conflict varsa force reset yap
            лог("[AUTO-UPDATE] Обнаружен конфликт, выполняется force reset...")
            subprocess.run(["git", "fetch", "origin"], cwd=BOT_DIR, capture_output=True, timeout=30)
            subprocess.run(["git", "reset", "--hard", "origin/main"], cwd=BOT_DIR, capture_output=True, timeout=30)
            лог("[AUTO-UPDATE] Force reset завершено")
        else:
            лог("[AUTO-UPDATE] Файлы обновлены")

        # создать .env, если отсутствует
        env_path = os.path.join(BOT_DIR, ".env")
        if not os.path.exists(env_path):
            with open(env_path, "w", encoding="utf-8") as f:
                f.write(ENV_CONTENT)
            лог("[AUTO-UPDATE] .env создано")

    except Exception as e:
        raise Exception(f"git pull ошибки: {e}")


def _zip_target_ok(bot_dir, target_path):
    """Безопасен ли путь из ZIP-архива (защита от Zip Slip).

    Разрешены только пути внутри bot_dir. Функция вынесена отдельно,
    чтобы её покрывали тесты (tests/test_security.py).
    """
    bot_dir_abs = os.path.abspath(bot_dir)
    _abs = os.path.abspath(target_path)
    return _abs == bot_dir_abs or _abs.startswith(bot_dir_abs + os.sep)


def download_and_extract():
    """Скачать ZIP с GitHub и распаковать в BOT_DIR (fallback)"""
    лог("[AUTO-UPDATE] Файлы загружаются...")
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    r = requests.get(ZIP_URL, headers=headers, timeout=60)
    if r.status_code != 200:
        raise Exception(f"Ошибка загрузки HTTP {r.status_code}")

    zip_path = os.path.join(BOT_DIR, "hakumo-update.zip")
    with open(zip_path, "wb") as f:
        f.write(r.content)
    лог(f"[AUTO-UPDATE] ZIP загружен ({len(r.content)//1024} KB)")

    with zipfile.ZipFile(zip_path, 'r') as zf:
        for member in zf.infolist():
            target = member.filename.replace("moebius-bot-main/", "", 1).replace("hakumo-bot-main/", "", 1)
            if not target:
                continue
            # Защита от Zip Slip: путь в архиве не должен выводить за
            # пределы BOT_DIR (../../ и абсолютные пути запрещены).
            target_path = os.path.join(BOT_DIR, target)
            if not _zip_target_ok(BOT_DIR, target_path):
                лог(f"[AUTO-UPDATE] Пропущен небезопасный путь в архиве: {member.filename}")
                continue
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
                    лог(f"[AUTO-UPDATE] Ошибка записи файла ({target}): {e}")

    os.remove(zip_path)
    лог("[AUTO-UPDATE] Файлы обновлены (ZIP)")

    env_path = os.path.join(BOT_DIR, ".env")
    if not os.path.exists(env_path):
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(ENV_CONTENT)
        лог("[AUTO-UPDATE] .env создано")


def update_bot():
    лог("[AUTO-UPDATE] === ОБНОВЛЕНИЕ НАЧАТО ===")
    try:
        kill_bot()
        # Сначала пробуем git pull; если это не git-репозиторий — скачиваем ZIP
        git_dir = os.path.join(BOT_DIR, ".git")
        if os.path.isdir(git_dir):
            git_pull()
        else:
            лог("[AUTO-UPDATE] .git не найден — обновляемся из ZIP-архива...")
            download_and_extract()
        time.sleep(2)
        start_bot()
        лог("[AUTO-UPDATE] === ОБНОВЛЕНИЕ ЗАВЕРШЕНО ===")
    except Exception as e:
        лог(f"[AUTO-UPDATE] Ошибка обновления: {e}")
        лог("[AUTO-UPDATE] Произошла ошибка, бот перезапускается...")
        start_bot()


def main():
    лог(f"[AUTO-UPDATE] Запущен (PID: {MY_PID})")
    лог(f"[AUTO-UPDATE] Директория скрипта: {SCRIPT_DIR}")
    лог(f"[AUTO-UPDATE] Директория бота: {BOT_DIR}")
    лог(f"[AUTO-UPDATE] Python: {sys.executable}")
    
    # Проверка необходимых файлов
    main_py = os.path.join(BOT_DIR, "main.py")
    if not os.path.exists(main_py):
        лог(f"[AUTO-UPDATE] KRITIK ОШИБКА: main.py не найдено: {main_py}")
        лог("[AUTO-UPDATE] Запустите скрипт в директории бота!")
        return
    
    лог("[AUTO-UPDATE] GitHub-опрос запущен (5 сек)...")

    # Первая проверка: если бот не работает — запустить сразу
    if not is_bot_running():
        лог("[AUTO-UPDATE] Бот не работает, запускается...")
        if not start_bot():
            лог("[AUTO-UPDATE] Не удалось запустить бота! Проверьте лог-файл:")
            лог(f"[AUTO-UPDATE] {BOT_LOG}")
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
                    лог(f"[AUTO-UPDATE] Обнаружен новый коммит: {remote_hash[:8]} (local: {local_hash[:8]})")
                    update_bot()

            # Проверить, не остановился ли бот
            if not is_bot_running():
                лог("[AUTO-UPDATE] Бот остановлен! Перезапуск...")
                if not start_bot():
                    лог("[AUTO-UPDATE] Не удалось перезапустить бота!")
                time.sleep(10)

            time.sleep(30)

        except KeyboardInterrupt:
            лог("[AUTO-UPDATE] Остановлено пользователем")
            break
        except Exception as e:
            лог(f"[AUTO-UPDATE] Ошибка главного цикла: {e}")
            import traceback
            лог(traceback.format_exc())
            time.sleep(10)


if __name__ == "__main__":
    main()
