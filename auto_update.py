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


def _git_bin():
    """Путь к исполняемому git или '' — если git не установлен/нет в PATH.

    Раньше наличие git-режима определялось только папкой .git: скачанная с
    GitHub ZIP-папка с распакованным .git (или машина без git в PATH) вела к
    вызовам `git ...`, которые на Windows падали с [WinError 2]. Теперь
    сперва проверяем сам бинарь — нет git, честно уходим в ZIP-режим.
    """
    import shutil
    exe = shutil.which("git")
    if exe:
        return exe
    # Типичные места установки git на Windows, если его нет в PATH
    if os.name == "nt":
        for cand in (
            r"C:\Program Files\Git\cmd\git.exe",
            r"C:\Program Files (x86)\Git\cmd\git.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Git\cmd\git.exe"),
        ):
            if cand and os.path.exists(cand):
                return cand
    return ""


def _run_git(args, timeout=30):
    """Запустить git, только если он реально есть. Иначе — None (без падения)."""
    gbin = _git_bin()
    if not gbin:
        return None
    try:
        return subprocess.run([gbin] + list(args), cwd=BOT_DIR,
                              capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return None
    except Exception:
        return None


def _detect_branch():
    """Рабочая ветка git-репозитория (или '' — не git/не получилось)."""
    r = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], timeout=10)
    if r is not None and r.returncode == 0:
        return (r.stdout or "").strip()
    return ""


# ВЕТКА ОБНОВЛЕНИЯ — из .env (UPDATE_BRANCH); если не задана — ТЕКУЩАЯ ветка.
# Раньше по умолчанию был main: машина с рабочей веткой arena и без
# UPDATE_BRANCH НЕСООТВЕТСТВОВАЛА origin/main — демон сбрасывал checkout
# на main со СТАРЫМ кодом и перезапускал бота (свежие правки откатывались).
# Теперь: ветка = своя (из git), а не захардкоженная main.
UPDATE_BRANCH = (os.getenv("UPDATE_BRANCH", "").strip() or _detect_branch() or "main")
REPO_SLUG = os.getenv("UPDATE_REPO", "Arthu27/New-Pro").strip() or "Arthu27/New-Pro"


def _source():
    """Источник обновлений: панель (data/update_source.json) → .env.

    Заказ 30.08 «дай, я поставлю, откуда качать»: владелец меняет
    репозиторий/ветку кнопкой в панели — и /update, и этот демон
    качают оттуда же (раньше демон был прибит гвоздями к .env на старте).
    """
    try:
        sys.path.insert(0, BOT_DIR)
        from services.update_source import get_repo, get_branch
        return get_repo(), get_branch()
    except Exception:
        return REPO_SLUG, UPDATE_BRANCH


def _repo_api():
    repo, branch = _source()
    return f"https://api.github.com/repos/{repo}/commits/{branch}"


def _zip_url():
    repo, branch = _source()
    return f"https://github.com/{repo}/archive/refs/heads/{branch}.zip"

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
        r = requests.get(_repo_api(), headers=headers, timeout=10)
        if r.status_code == 200:
            return r.json()["sha"]
    except Exception as e:
        лог(f"[AUTO-UPDATE] Ошибка получения коммита: {e}")
    return None


def get_local_commit():
    """Local git repo'dan HEAD commit hash'ini al (None — git недоступен)."""
    result = _run_git(["rev-parse", "HEAD"], timeout=10)
    if result is not None and result.returncode == 0:
        return result.stdout.strip()
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


def note_zip_branch(branch):
    """Запомнить ветку, с которой распакован ZIP (data/.update_branch).

    Критично для установок «скачал ZIP ветки без .git»: иначе демон и /update
    не знают, откуда обновляться, и сваливаются на main (старый код без
    фиксов). Та же логика, что в services/self_update.running_branch.
    """
    branch = (branch or "").strip()
    if not branch:
        return
    try:
        os.makedirs(os.path.join(BOT_DIR, "data"), exist_ok=True)
        with open(os.path.join(BOT_DIR, "data", ".update_branch"), "w",
                  encoding="utf-8") as f:
            f.write(branch)
    except OSError as e:
        лог(f"[AUTO-UPDATE] Не записать маркер ветки: {e}")


def running_branch_local():
    """Ветка текущей установки БЕЗ git (ZIP), как self_update.running_branch:
    1) маркер data/.update_branch (записан прошлой раскаткой);
    2) имя папки дистрибутива «New-Pro-arena-01a05c7b-new-pro» →
       ветка arena/01a05c7b-new-pro (в zip-имени слэши → дефисы);
    3) '' — неизвестно.
    """
    try:
        with open(os.path.join(BOT_DIR, "data", ".update_branch"),
                  encoding="utf-8") as f:
            name = f.read().strip()
            if name:
                return name
    except OSError:
        pass
    try:
        base = os.path.basename(os.path.abspath(BOT_DIR))
        if base.lower().startswith("new-pro-") and len(base) > len("new-pro-"):
            cand = base[len("New-Pro-"):]
            if cand.lower().startswith("arena-"):
                cand = "arena/" + cand[len("arena-"):]
            if cand and cand != "main":
                return cand
    except Exception:
        pass
    return ""


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
    """Обновить репозиторий через git pull (если git реально доступен)."""
    _branch = _source()[1]
    if not _git_bin():
        лог("[AUTO-UPDATE] git недоступен в PATH — обновляюсь через ZIP-архив")
        download_and_extract()
        return
    лог(f"[AUTO-UPDATE] Выполняется git pull ({_branch})...")
    try:
        result = _run_git(["pull", "origin", _branch], timeout=60)
        if result is None:
            лог("[AUTO-UPDATE] git pull не запустился — обновляюсь через ZIP")
            download_and_extract()
            return
        лог(f"[AUTO-UPDATE] git pull stdout: {result.stdout.strip()}")
        if result.returncode != 0:
            лог(f"[AUTO-UPDATE] git pull stderr: {result.stderr.strip()}")
            # Conflict varsa force reset yap
            лог("[AUTO-UPDATE] Обнаружен конфликт, выполняется force reset...")
            _run_git(["fetch", "origin"], timeout=30)
            _run_git(["reset", "--hard", f"origin/{_branch}"], timeout=30)
            лог(f"[AUTO-UPDATE] Force reset на origin/{_branch} завершено")
        else:
            лог("[AUTO-UPDATE] Файлы обновлены")

        # ТОЛЬКО СВЕЖЕЕ: ничего лишнего помимо дерева origin/main —
        # убираем неотслеживаемые хвосты (бывшие модули, временные файлы).
        # Сохраняем: данные, логи, секреты, окружение, ручной контент.
        clean_res = _run_git(
            ["clean", "-fd",
             "-e", "data/", "-e", "logs/", "-e", ".env", "-e", ".env.local",
             "-e", ".venv", "-e", "venv", "-e", "env", "-e", "node_modules",
             "-e", "bot_output.log", "-e", "last_commit.txt",
             "-e", "UPDATE.bat", "-e", "config-local.py"], timeout=60)
        cleaned = [x.strip() for x in (clean_res.stdout.splitlines() if clean_res else [])
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
    """Скачать ZIP с GitHub и распаковать в BOT_DIR (fallback)."""
    _dl_branch = _source()[1]
    лог("[AUTO-UPDATE] Файлы загружаются...")
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    r = requests.get(_zip_url(), headers=headers, timeout=60)
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

    # Запоминаем ветку, с которой распаковались: установка без .git должна и
    # дальше обновляться с ТОЙ ЖЕ ветки (иначе демон свалится на main со
    # старым кодом). Источник — запрошенная ветка, иначе — имя папки архива.
    try:
        _mark_branch = _dl_branch or running_branch_local()
        if _mark_branch and _mark_branch != "main":
            note_zip_branch(_mark_branch)
            лог(f"[AUTO-UPDATE] ветка установки зафиксирована: {_mark_branch}")
    except Exception as _be:
        лог(f"[AUTO-UPDATE] не удалось зафиксировать ветку: {_be}")

    # git-режим убирает неотслеживаемые хвосты через `git clean -fd`; в
    # ZIP-режиме этого шага нет — старые файлы вырезанных фич оставались бы
    # на диске. Сносим только заведомо мёртвый КОД (коги вырезанных систем):
    # его не грузит ни один профиль cogs_policy, так что команды/дублям взяться
    # неоткуда, а удаление гарантирует, что их не подхватит даже вручную.
    # Данные (data/), .env, логи, venv — не трогаем.
    _prune_dead_code()

    env_path = os.path.join(BOT_DIR, ".env")
    if not os.path.exists(env_path):
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(ENV_CONTENT)
        лог("[AUTO-UPDATE] .env создано")


# Код модулей, удалённых из боевого состава (вырезанные/снятые с эксплуатации
# системы). Распространяется только на файлы когов в ZIP-режиме — чтобы старые
# копии не оставались на машине после обновления архивом.
_DEAD_COG_FILES = (
    "cogs/ticket.py",          # тикет-система снята (RETired)
    "cogs/counting.py",        # считалка
    "cogs/starboard.py",       # доска славы
    "cogs/tag_jail.py",        # tag jail
    "cogs/staff_shifts.py",    # смены персонала
    "cogs/night_report.py",    # ночные сводки
    "cogs/mod_digest.py",      # дайджест модерации
    "cogs/music.py",           # музыка /play снесена
)


def _prune_dead_code():
    """Удалить файлы вырезанных модулей (ZIP-режим). Безопасно: их не грузят."""
    removed = 0
    for rel in _DEAD_COG_FILES:
        fp = os.path.join(BOT_DIR, rel)
        # не даём пути выйти за пределы BOT_DIR (тот же принцип, что Zip Slip)
        if not _zip_target_ok(BOT_DIR, fp):
            continue
        try:
            if os.path.isfile(fp):
                os.remove(fp)
                removed += 1
        except OSError as e:
            лог(f"[AUTO-UPDATE] не удалось убрать устаревший {rel}: {e}")
    if removed:
        лог(f"[AUTO-UPDATE] убрано устаревших модулей: {removed} шт (ZIP)")


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
        # git pull — только если есть и репозиторий .git, и сам бинарь git.
        # Иначе (нет .git или git не установлен/нет в PATH) — ZIP-архив, это
        # убирает [WinError 2] на машинах без git.
        git_dir = os.path.join(BOT_DIR, ".git")
        if os.path.isdir(git_dir) and _git_bin():
            git_pull()
        else:
            лог("[AUTO-UPDATE] git недоступен (.git нет или git не в PATH) — "
                "обновляемся из ZIP-архива...")
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
    """git status --porcelain пуст — только тогда обновлять (reset безопасен).

    Если git недоступен (нет бинаря) — возвращаем True, т.к. в ZIP-режиме
    reset --hard не используется вовсе (обновление идёт распаковкой архива).
    """
    r = _run_git(["status", "--porcelain"], timeout=20)
    if r is None:
        return True
    return r.returncode == 0 and not (r.stdout or "").strip()


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

    # git-режим — только если есть И папка .git, И сам бинарь git в PATH.
    # Скачанная ZIP-папка с распакованным .git на машине без git больше не
    # роняет цикл с [WinError 2] — честно уходим в ZIP-режим.
    _has_git_dir = os.path.isdir(os.path.join(BOT_DIR, ".git"))
    _has_git_bin = bool(_git_bin())
    _is_git = _has_git_dir and _has_git_bin
    if _has_git_dir and not _has_git_bin:
        лог("[AUTO-UPDATE] .git есть, но git не установлен/нет в PATH — "
            "перехожу на ZIP-режим (обновление распаковкой архива, без git)")
        log_event("zip_mode_fallback", reason="git_binary_missing")
    if not _is_git:
        # ZIP-установка без .git: ветку берём не из «main по умолчанию», а из
        # самой установки — маркер data/.update_branch (после первой раскатки)
        # или имя папки «New-Pro-arena-01a05c7b-new-pro». Так скачанный ZIP
        # ветки продолжает обновляться с ЭТОЙ ЖЕ ветки, а не откатывается.
        _auto_branch = running_branch_local()
        if _auto_branch:
            try:
                sys.path.insert(0, BOT_DIR)
                from services.update_source import set_source, get_repo
                set_source(get_repo(), _auto_branch)
                лог(f"[AUTO-UPDATE] ZIP-режим: ветка установки определена как {_auto_branch}")
            except Exception as _ab:
                os.environ["UPDATE_BRANCH"] = _auto_branch
                лог(f"[AUTO-UPDATE] ZIP-режим: ветка из папки/маркера: {_auto_branch} ({_ab})")
        лог("[AUTO-UPDATE] ZIP-режим: версию смотрю в GitHub API "
            f"и маркере data/.update_sha (опрос раз в {ZIP_API_POLL_SEC // 60} мин)")
        log_event("zip_mode", poll_sec=ZIP_API_POLL_SEC)
    _last_api_check = 0.0

    while True:
        try:
            _dyn_branch = _source()[1]
            # ZIP-режим без явной настройки панели: ветка установки важнее main.
            # Выставляем и UPDATE_BRANCH — это fallback _source(), если файл
            # update_source.json недоступен (например, services/ не прочитались).
            if not _is_git and (not _dyn_branch or _dyn_branch == "main"):
                _auto = running_branch_local()
                if _auto and _auto != "main":
                    _dyn_branch = _auto
                    os.environ["UPDATE_BRANCH"] = _auto
            remote_hash = None
            if _is_git:
                _run_git(["fetch", "origin"], timeout=30)
                result = _run_git(["rev-parse", f"origin/{_dyn_branch}"], timeout=10)
                remote_hash = result.stdout.strip() if (result is not None and result.returncode == 0) else None
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
                    elif _is_git and _detect_branch() != _dyn_branch:
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
