import time
import requests
import subprocess
import os
import zipfile
import sys
import json
import datetime


def _load_dotenv():
    """Поднять .env рядом со скриптом (как это делает сам бот).

    Без этого UPDATE_BRANCH/UPDATE_REPO из .env сюда не доходят — демон
    жил жёстко на main и откатывал рабочую ветку (все правки пропадали).
    """
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    try:
        with open(env_path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except OSError:
        pass


_load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

# Автоматически определить директорию скрипта (VSCode workspace)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BOT_DIR = SCRIPT_DIR  # использовать workspace VSCode
LAST_COMMIT_FILE = os.path.join(BOT_DIR, "last_commit.txt")
BOT_LOG = os.path.join(BOT_DIR, "bot_output.log")
EVENTS_LOG = os.path.join(BOT_DIR, "data", "auto_update_events.json")


def _detect_branch():
    """Рабочая ветка git-репозитория (или '' — не git/не получилось)."""
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=BOT_DIR, capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            return (r.stdout or "").strip()
    except Exception:
        pass
    return ""


# ВЕТКА ОБНОВЛЕНИЯ — из .env (UPDATE_BRANCH); если не задана — ТЕКУЩАЯ ветка.
# Раньше по умолчанию был main: машина с рабочей веткой arena и без
# UPDATE_BRANCH НЕСООТВЕТСТВОВАЛА origin/main — демон сбрасывал checkout
# на main со СТАРЫМ кодом и перезапускал бота (свежие правки откатывались).
# Теперь: ветка = своя (из git), а не захардкоженная main.
UPDATE_BRANCH = (os.getenv("UPDATE_BRANCH", "").strip() or _detect_branch() or "main")
REPO_SLUG = os.getenv("UPDATE_REPO", "Arthu27/New-Pro").strip() or "Arthu27/New-Pro"
REPO_API = f"https://api.github.com/repos/{REPO_SLUG}/commits/{UPDATE_BRANCH}"
ZIP_URL = f"https://github.com/{REPO_SLUG}/archive/refs/heads/{UPDATE_BRANCH}.zip"

# АВТООБНОВЛЕНИЕ — только по явному флагу AUTO_UPDATE=1/true/yes.
# По умолчанию ВЫКЛЮЧЕНО: демон лишь присматривает за живым процессом
# (поднимет, если бот умер). Никаких kill/reset без разрешения владельца.
AUTO_UPDATE_ENABLED = (os.getenv("AUTO_UPDATE", "0") or "0").strip().lower() \
    in ("1", "true", "yes", "on")
AUTO_UPDATE_COOLDOWN = 600  # между перезапусками (сек), переопределяется в .env
try:
    AUTO_UPDATE_COOLDOWN = max(60, int(os.getenv("AUTO_UPDATE_COOLDOWN", "600")))
except ValueError:
    pass
_LAST_UPDATE_TS = 0.0

# содержимое .env теперь читается из файла .env, здесь не задано жёстко
ENV_CONTENT = """TOKEN=YOUR_BOT_TOKEN_HERE
GROQ_API_KEY=YOUR_GROQ_API_KEY
MISTRAL_API_KEY=YOUR_MISTRAL_API_KEY
OWNER_ID=987430047889637426"""

MY_PID = os.getpid()


def лог(msg):
    print(msg, flush=True)


def log_event(event, **extra):
    """Журнал событий демона: любое решение «обновлять/не обновлять» видно."""
    try:
        os.makedirs(os.path.dirname(EVENTS_LOG), exist_ok=True)
        rows = []
        if os.path.exists(EVENTS_LOG):
            try:
                with open(EVENTS_LOG, "r", encoding="utf-8") as f:
                    rows = json.load(f)
            except Exception:
                rows = []
        rows.append({
            "ts": datetime.datetime.now(datetime.timezone.utc)
                   .isoformat(timespec="seconds"),
            "event": event, "branch": UPDATE_BRANCH, **extra,
        })
        rows = rows[-200:]
        tmp = EVENTS_LOG + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
        os.replace(tmp, EVENTS_LOG)
    except Exception:
        return


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


# ZIP-режим (без .git): версию установки знает МАРКЕР data/.update_sha —
# его же пишет /update (services/self_update.note_applied_sha). Жалоба
# 30.08 «опять так же, команды не удалились»: демон в ZIP-режиме вообще
# не обновлял бота — git rev-parse без .git вечно возвращал None, и НИ
# ОДИН фикс до владельца не доезжал. Теперь: remote из GitHub API,
# local из маркера.
ZIP_API_POLL_SEC = 300   # опрос API не чаще 5 мин (анонимный лимит 60/час)


def get_local_zip_commit():
    """Версия ZIP-установки: маркер data/.update_sha (None — неизвестна)."""
    try:
        with open(os.path.join(BOT_DIR, "data", ".update_sha"),
                  encoding="utf-8") as f:
            val = f.read().strip()
            return val or None
    except OSError:
        return None


def note_zip_commit(sha):
    """Запомнить применённую версию (ZIP-режим) — иначе обновление по кругу."""
    if not (sha or "").strip():
        return
    try:
        os.makedirs(os.path.join(BOT_DIR, "data"), exist_ok=True)
        with open(os.path.join(BOT_DIR, "data", ".update_sha"), "w",
                  encoding="utf-8") as f:
            f.write(sha.strip())
    except OSError as e:
        лог(f"[AUTO-UPDATE] Не записать маркер версии: {e}")


def _archive_root(names):
    """Корневой каталог архива GitHub ('Репозиторий-ветка/') или ''.

    Префикс у архива СВОЙ для каждой ветки (New-Pro-arena-.../), раньше
    были захардкожены старые имена — архив свежей ветки распаковывался
    во вложенную папку, и бот продолжал работать на старых файлах.
    """
    if not names or "/" not in names[0]:
        return ""
    root = names[0].split("/")[0] + "/"
    if all(n.startswith(root) for n in names):
        return root
    return ""


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
            ["git", "pull", "origin", UPDATE_BRANCH],
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
            subprocess.run(["git", "reset", "--hard", f"origin/{UPDATE_BRANCH}"], cwd=BOT_DIR, capture_output=True, timeout=30)
            лог(f"[AUTO-UPDATE] Force reset на origin/{UPDATE_BRANCH} завершено")
        else:
            лог("[AUTO-UPDATE] Файлы обновлены")

        # ТОЛЬКО СВЕЖЕЕ: ничего лишнего помимо дерева origin/main —
        # убираем неотслеживаемые хвосты (бывшие модули, временные файлы).
        # Сохраняем: данные, логи, секреты, окружение, ручной контент.
        clean_res = subprocess.run(
            ["git", "clean", "-fd",
             "-e", "data/", "-e", "logs/", "-e", ".env", "-e", ".env.local",
             "-e", ".venv", "-e", "venv", "-e", "env", "-e", "node_modules",
             "-e", "bot_output.log", "-e", "last_commit.txt",
             "-e", "UPDATE.bat", "-e", "config-local.py"],
            cwd=BOT_DIR, capture_output=True, text=True, timeout=60)
        cleaned = [x.strip() for x in clean_res.stdout.splitlines()
                   if x.strip().startswith(('Removing', 'Удаляется', 'Удалён'))]
        if cleaned:
            лог(f"[AUTO-UPDATE] убрано устаревшего: {len(cleaned)} шт — только самое свежее")
        else:
            лог("[AUTO-UPDATE] каталог уже соответствует свежей ветке")

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
        # корень архива выводим из самого архива (имя = репозиторий-ветка)
        root = _archive_root(zf.namelist())
        for member in zf.infolist():
            target = member.filename[len(root):] if root and member.filename.startswith(root) else member.filename
            target = target.replace("moebius-bot-main/", "", 1).replace("hakumo-bot-main/", "", 1)
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


def update_bot(reason="new_commit", remote_sha=None, local_sha=None):
    """Обновление с полным журналом. ВОЗВРАЩАЕТ True, если обновление сделано
    (иначе False — причина уже в event-логе)."""
    global _LAST_UPDATE_TS
    now = time.time()
    if now - _LAST_UPDATE_TS < AUTO_UPDATE_COOLDOWN:
        log_event("skipped_update", reason="cooldown",
                  wait=int(AUTO_UPDATE_COOLDOWN - (now - _LAST_UPDATE_TS)))
        лог("[AUTO-UPDATE] Кулдаун: обновление реже раза в "
            f"{AUTO_UPDATE_COOLDOWN // 60} мин — пропускаю")
        return False
    _LAST_UPDATE_TS = now
    log_event("update_start", reason=reason,
              remote=remote_sha or "", local=local_sha or "")
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
            note_zip_commit(remote_sha)   # иначе на следующем круге снова «новое»
        time.sleep(2)
        start_bot()
        log_event("update_done", remote=remote_sha or "", local=local_sha or "")
        лог("[AUTO-UPDATE] === ОБНОВЛЕНИЕ ЗАВЕРШЕНО ===")
        return True
    except Exception as e:
        log_event("update_error", error=str(e)[:300])
        лог(f"[AUTO-UPDATE] Ошибка обновления: {e}")
        лог("[AUTO-UPDATE] Произошла ошибка, бот перезапускается...")
        start_bot()
        return False


def _tree_is_clean():
    """git status --porcelain пуст — только тогда обновлять (reset безопасен)."""
    try:
        r = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=BOT_DIR, capture_output=True, text=True, timeout=20)
        return r.returncode == 0 and not (r.stdout or "").strip()
    except Exception:
        return False


def main():
    лог(f"[AUTO-UPDATE] Запущен (PID: {MY_PID})")
    лог(f"[AUTO-UPDATE] Директория скрипта: {SCRIPT_DIR}")
    лог(f"[AUTO-UPDATE] Директория бота: {BOT_DIR}")
    лог(f"[AUTO-UPDATE] Python: {sys.executable}")
    лог(f"[AUTO-UPDATE] Ветка: {UPDATE_BRANCH} | "
        f"автообновление: {'ВКЛ' if AUTO_UPDATE_ENABLED else 'ВЫКЛ'}")
    log_event("daemon_start", auto_update=AUTO_UPDATE_ENABLED, branch=UPDATE_BRANCH)
    
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

    _is_git = os.path.isdir(os.path.join(BOT_DIR, ".git"))
    if not _is_git:
        лог("[AUTO-UPDATE] .git нет — ZIP-режим: версию смотрю в GitHub API "
            f"и маркере data/.update_sha (опрос раз в {ZIP_API_POLL_SEC // 60} мин)")
        log_event("zip_mode", poll_sec=ZIP_API_POLL_SEC)
    _last_api_check = 0.0

    while True:
        try:
            remote_hash = None
            if _is_git:
                subprocess.run(["git", "fetch", "origin"], cwd=BOT_DIR,
                               capture_output=True, timeout=30)
                result = subprocess.run(
                    ["git", "rev-parse", f"origin/{UPDATE_BRANCH}"],
                    cwd=BOT_DIR, capture_output=True, text=True, timeout=10
                )
                remote_hash = result.stdout.strip() if result.returncode == 0 else None
            else:
                # ZIP-режим: git не работает — спрашиваем GitHub API.
                # Реже, чем git-режим: анонимный лимит API — 60 запросов/час.
                _now = time.time()
                if _now - _last_api_check >= ZIP_API_POLL_SEC:
                    _last_api_check = _now
                    remote_hash = get_remote_commit()
                    if remote_hash is None:
                        лог("[AUTO-UPDATE] GitHub API не ответил — попробую "
                            "через 5 минут (бот работает)")

            if remote_hash:
                local_hash = (get_local_commit() if _is_git
                              else get_local_zip_commit()) or ""
                if remote_hash != local_hash:
                    лог(f"[AUTO-UPDATE] Удалённый коммит отличается: {remote_hash[:8]} (local: {local_hash[:8] if local_hash else 'неизвестен'})")
                    # БЕЗОПАСНОСТЬ: обновление только по явному флагу владельца.
                    if not AUTO_UPDATE_ENABLED:
                        log_event("skipped_update", reason="auto_update_disabled",
                                  remote=remote_hash, local=local_hash)
                        лог("[AUTO-UPDATE] AUTO_UPDATE=0 — НЕ перезапускаю бота "
                            "(обновляйтесь командой /update или включите "
                            "AUTO_UPDATE=1 в .env)")
                    elif _is_git and _detect_branch() != UPDATE_BRANCH:
                        log_event("skipped_update", reason="branch_mismatch",
                                  remote=remote_hash, local=local_hash)
                        лог("[AUTO-UPDATE] Рабочая ветка ≠ UPDATE_BRANCH — "
                            "обновление пропущено (reset на чужую ветку запрещён)")
                    elif _is_git and not _tree_is_clean():
                        log_event("skipped_update", reason="dirty_tree",
                                  remote=remote_hash, local=local_hash)
                        лог("[AUTO-UPDATE] В рабочем дереве есть изменения — "
                            "reset --hard не делаю, бот работает дальше")
                    else:
                        update_bot("new_commit", remote_hash, local_hash)

            # Проверить, не остановился ли бот
            if not is_bot_running():
                лог("[AUTO-UPDATE] Бот остановлен! Перезапуск...")
                log_event("bot_restart", reason="bot_stopped")
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
