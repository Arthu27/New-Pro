# -*- coding: utf-8 -*-
"""Самообновление бота по команде /update (заказ, пункт 5.6).

Один вызов — и всё делает бот сам, без ручного скачивания.

Главное: обновление ИНКРЕМЕНТАЛЬНОЕ — целиком бот не перекачивается.
Если каталог — git-репозиторий, идём через git fetch/pull: по сети уходят
только изменения коммитов. Если git нет — качаем zip ветки (другого
способа у codeload нет), но раскатываем только файлы, у которых изменился
байтовый хэш: неизменённые не трогаем вообще. Если удалённый sha совпадает
с уже применённым — отвечаем «бот уже свежий» и ничего не делаем.

1. git_update()    — git-путь: fetch + diff + ff/reset; только дельты по сети.
   download_zip()  — запасной путь: zip ветки репозитория с GitHub (codeload).
2. verify_zip()    — целостность: это валидный zip, есть опорные файлы
                     (main.py, config.py, web/app.py), архив не битый,
                     каждый .py компилируется (py_compile).
3. stage_update()  — раскатывает СВЕЖЕЕ состояние ветки как ЕДИНСТВЕННОЕ:
                     из архива копируются ТОЛЬКО новые/изменённые файлы
                     (по хэшу содержимого), а любой файл, которого
                     НЕТ в архиве (старый, уже удалённый в репо), убирается —
                     «обновил и всё», старого и нового вперемешку не остаётся.
                     Бережно сохраняет данные и секреты (data/, logs/, .env,
                     .git, .venv — в исключениях) и пишет маркер
                     data/update_pending.json (sha/ветка/канал).
4. ког делает os.execv — процесс заменяется свежим кодом; на on_ready
                     main.py отчитывается в канал из маркера.

Функции синхронные — из кога зовутся через asyncio.to_thread.
"""

import hashlib
import json
import os
import py_compile
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path as _Path
from datetime import datetime, timezone

from logger import get_logger

log = get_logger('self_update')

# Опорные файлы: обновление без них — это «не наш» архив, не раскатываем
REQUIRED_FILES = ('main.py', 'config.py', 'web/app.py')

# Что НЕЛЬЗЯ трогать при раскатке: данные, секреты, git и колёса окружения
PRESERVE_DIRS = ('data', 'logs', '.git', '.venv', 'venv', 'env',
                 '__pycache__', 'node_modules', '.idea', '.vscode')
PRESERVE_FILES = ('.env', '.env.local', 'bot_output.log', 'last_commit.txt')

_MAX_ZIP_BYTES = 300 * 1024 * 1024  # 300 МБ — защита от бомбы/каприза сети


def _utcnow_iso():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def running_branch(bot_dir):
    """Ветка, на которой бот реально запущен (для самообновления).

    Раньше /update всегда тянул захардкоженный `main`, даже когда бот
    запущен с ветки-сессии (распакованный zip вида
    «New-Pro-arena-01a05336-new-pro») — и обновление ОТКАТЫВАЛО бота на
    старый main без фиксов. Теперь определяем ветку:
      1) git-репозиторий → текущая ветка (git rev-parse);
      2) не-репозиторий (распакованный zip) → маркер data/.update_branch,
         записанный при прошлой раскатке, или имя папки дистрибутива;
      3) неизвестно → None (вызывающий берёт main).
    """
    # 1) git
    if is_git_repo(bot_dir):
        r = _run_git(bot_dir, ['rev-parse', '--abbrev-ref', 'HEAD'], timeout=15)
        if r is not None and r.returncode == 0:
            name = (r.stdout or '').strip()
            if name and name != 'HEAD':
                return name
    # 2) маркер после раскатки zip
    try:
        with open(os.path.join(bot_dir, 'data', '.update_branch'),
                  encoding='utf-8') as f:
            name = f.read().strip()
            if name:
                return name
    except OSError as _ex:
        log.debug('self_update: маркер ветки не прочитан: %s', _ex)
    # 3) имя папки дистрибутива: «New-Pro-arena-01a05336-new-pro» → ветка
    try:
        base = os.path.basename(os.path.abspath(bot_dir))
        low = base.lower()
        if low.startswith('new-pro-') and len(low) > len('new-pro-'):
            cand = base[len('New-Pro-'):]
            # в zip-имени ветки слэши заменены дефисами у префикса arena/
            if cand.lower().startswith('arena-'):
                cand = 'arena/' + cand[len('arena-'):]
            if cand and cand != 'main':
                return cand
    except Exception as _ex:
        log.debug('self_update: определение ветки по папке: %s', _ex)
    return None


def marker_path(bot_dir):
    return os.path.join(bot_dir, 'data', 'update_pending.json')


def _git_env():
    """Чистое окружение для git: без GIT_DIR/GIT_WORK_TREE снаружи."""
    return {k: v for k, v in os.environ.items()
            if k not in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE')}


def is_git_repo(bot_dir):
    """Каталог — git-репозиторий (значит, можем качать только дельты)."""
    return os.path.isdir(os.path.join(bot_dir, '.git'))


def _run_git(bot_dir, args, timeout=90):
    try:
        return subprocess.run(
            ['git'] + list(args), cwd=bot_dir, capture_output=True,
            text=True, timeout=timeout, env=_git_env())
    except Exception as _ex:
        log.debug('self_update: git %s: %s', args, _ex)
        return None


def local_sha(bot_dir):
    """Применённая локально версия: git HEAD, иначе маркер data/.update_sha.

    None — неизвестно: тогда обновляться надо по полной схеме проверки.
    """
    if is_git_repo(bot_dir):
        r = _run_git(bot_dir, ['rev-parse', 'HEAD'], timeout=15)
        if r is not None and r.returncode == 0:
            return (r.stdout or '').strip() or None
    try:
        with open(os.path.join(bot_dir, 'data', '.update_sha'),
                  encoding='utf-8') as f:
            val = f.read().strip()
            return val or None
    except OSError:
        return None


def note_applied_sha(bot_dir, sha):
    """Запомнить применённый архивный sha (для не-репозиторного каталога)."""
    if not sha:
        return
    try:
        os.makedirs(os.path.join(bot_dir, 'data'), exist_ok=True)
        with open(os.path.join(bot_dir, 'data', '.update_sha'), 'w',
                  encoding='utf-8') as f:
            f.write(str(sha).strip())
    except OSError as _ex:
        log.debug('self_update: note_applied_sha: %s', _ex)


# ── Отложенный архив ──────────────────────────────────────────────────────
# Заказ владельца: «не выключайся, пока не скачается новая версия». Значит
# бот обязан скачать и проверить архив САМ, оставаясь живым, и только потом
# уходить на перезапуск. Скачанное кладём рядом с данными — обновлятор
# применит готовое, а если скачивание не удалось, бот просто продолжит
# работать на текущем коде.
PENDING_ZIP = os.path.join('data', '.update_pending.zip')
PENDING_META = os.path.join('data', '.update_pending.json')


def pending_paths(bot_dir):
    """Абсолютные пути отложенного архива и его описания."""
    return (os.path.join(bot_dir, PENDING_ZIP),
            os.path.join(bot_dir, PENDING_META))


def save_pending(bot_dir, zip_path, root, rel, sha, branch):
    """Отложить проверенный архив до перезапуска. Возвращает (ok, err).

    rel приходит из verify_zip МНОЖЕСТВОМ относительных путей — в JSON его
    писать нельзя («Object of type set is not JSON serializable»), поэтому
    кладём отсортированным списком и возвращаем обратно множеством.
    """
    dst, meta_path = pending_paths(bot_dir)
    try:
        rel_list = sorted(rel) if rel else []
    except TypeError:
        rel_list = []
    try:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(zip_path, dst)
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump({'root': root or '', 'rel': rel_list, 'sha': sha or '',
                       'branch': branch or '', 'size': os.path.getsize(dst),
                       'sha256': file_sha256(dst)}, f, ensure_ascii=False)
        return True, None
    except (OSError, TypeError, ValueError) as ex:
        log.warning('self_update: save_pending: %s', ex)
        return False, f'не удалось отложить архив: {ex}'


def load_pending(bot_dir):
    """Взять отложенный архив. Возвращает (zip_path, root, rel) или (None,)*3.

    Архив принимается только если совпала контрольная сумма из описания —
    иначе обновлятор раскатал бы недокачанный или подменённый файл.
    """
    src, meta_path = pending_paths(bot_dir)
    if not os.path.isfile(src) or not os.path.isfile(meta_path):
        return None, None, None
    try:
        with open(meta_path, encoding='utf-8') as f:
            meta = json.load(f)
    except (OSError, json.JSONDecodeError, ValueError) as ex:
        log.warning('self_update: load_pending: описание не читается: %s', ex)
        return None, None, None
    want = str(meta.get('sha256') or '')
    if not want or file_sha256(src) != want:
        log.warning('self_update: load_pending: контрольная сумма не сошлась')
        return None, None, None
    rel = meta.get('rel')
    # обратно — множеством: именно так его отдаёт verify_zip
    rel_set = set(rel) if isinstance(rel, (list, tuple, set)) else set()
    return src, meta.get('root'), rel_set


def clear_pending(bot_dir):
    """Убрать отложенный архив после применения (или после отказа)."""
    for p in pending_paths(bot_dir):
        try:
            if os.path.exists(p):
                os.remove(p)
        except OSError as ex:
            log.debug('self_update: clear_pending %s: %s', p, ex)


def file_sha256(path):
    """Контрольная сумма файла (для проверки отложенного архива)."""
    h = hashlib.sha256()
    try:
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(1024 * 256), b''):
                h.update(chunk)
    except OSError:
        return ''
    return h.hexdigest()


def git_update(bot_dir, branch):
    """Обновить через git: по сети идут только дельты объектов, а не весь бот.

    Возвращает (ok, err, info). info: {
        'up_to_date': bool, 'changed': N, 'from_sha': str, 'to_sha': str,
        'files': [относительные пути изменённых файлов] (до 50 шт.)}
    ok=False — git-путь недоступен/не вышел: вызывающий код пробует zip.
    """
    if not is_git_repo(bot_dir):
        return False, 'каталог бота не git-репозиторий', None
    branch = (branch or 'main').strip() or 'main'
    r = _run_git(bot_dir, ['fetch', 'origin', branch], timeout=120)
    if r is None or r.returncode != 0:
        return False, 'git fetch не удался (сеть или доступ к репо)', None
    remote_ref = 'origin/' + branch
    r = _run_git(bot_dir, ['rev-parse', remote_ref], timeout=15)
    if r is None or r.returncode != 0:
        return False, f'ветка {remote_ref} не найдена в репозитории', None
    to_sha = (r.stdout or '').strip()
    r = _run_git(bot_dir, ['rev-parse', 'HEAD'], timeout=15)
    from_sha = (r.stdout or '').strip() if r and r.returncode == 0 else ''
    if from_sha and from_sha == to_sha:
        return True, None, {'up_to_date': True, 'changed': 0,
                            'from_sha': from_sha, 'to_sha': to_sha, 'files': []}
    # какие именно файлы изменятся — для честного отчёта
    files = []
    if from_sha:
        r = _run_git(bot_dir, ['diff', '--name-only', from_sha, to_sha], timeout=30)
        if r is not None and r.returncode == 0:
            files = [ln.strip() for ln in (r.stdout or '').splitlines() if ln.strip()]
    # сначала аккуратный fast-forward; не вышло (локальные правки в коде) —
    # жёсткий сброс на свежую ветку: данные/логи/venv не отслеживаются гитом,
    # reset --hard их не трогает, как и незакоммиченные untracked-файлы.
    r = _run_git(bot_dir, ['merge', '--ff-only', remote_ref], timeout=60)
    if r is None or r.returncode != 0:
        log.info('self_update: ff-only не вышел, reset --hard на %s', remote_ref)
        r = _run_git(bot_dir, ['reset', '--hard', remote_ref], timeout=60)
        if r is None or r.returncode != 0:
            return False, 'git-обновление не применилось (конфликт с локальными файлами)', None
    log.info('self_update: git %s..%s, изменено файлов %s',
             (from_sha or '')[:7], to_sha[:7], len(files))
    return True, None, {'up_to_date': False, 'changed': len(files),
                        'from_sha': from_sha, 'to_sha': to_sha,
                        'files': files[:50]}


def _bot_dir():
    """Каталог бота: корень репозитория (на уровень выше services/)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _source():
    """Источник обновлений (repo, branch).

    Приоритет ветки: панель (data/update_source.json) → .env
    (UPDATE_BRANCH) → АВТО ветка, на которой бот реально запущен
    (running_branch) → main. Авто-определение чинит баг, когда /update
    тянул захардкоженный main и откатывал фиксы с ветки-сессии.
    Репозиторий всегда из панели/.env (дефолт Arthu27/New-Pro).
    """
    repo = None
    branch = None
    try:
        from services import update_source
        repo = update_source.get_repo()
        branch = update_source.get_branch()
    except Exception as _ex:
        log.debug('self_update: update_source недоступен (%s)', _ex)

    # .env, если панель ничего не задала
    if not repo:
        repo = (os.environ.get('UPDATE_REPO') or '').strip() or 'Arthu27/New-Pro'
    env_branch = (os.environ.get('UPDATE_BRANCH') or '').strip()
    if not branch:
        branch = env_branch

    # авто: ветка запущенного кода (git или маркер/имя папки)
    if not branch or branch == 'main':
        auto = None
        try:
            auto = running_branch(_bot_dir())
        except Exception as _ex:
            log.debug('self_update: running_branch: %s', _ex)
        if auto and auto != 'main':
            # .env явно НЕ просил main — тогда уважаем авто; если в .env
            # жёстко вписан main, оставляем его (это сознательный выбор).
            if branch != 'main' or not env_branch:
                branch = auto

    if not branch:
        branch = 'main'
    return repo, branch


def _update_token():
    """Токен GitHub для обновлений ИЗ ПРИВАТНОГО репозитория.

    Приватный репозиторий анонимно отдаёт 404 (и на codeload, и на API) —
    чтобы качать обновления, нужен токен с доступом на чтение содержимого.
    Читаем из окружения/.env (бот грузит .env при старте): GITHUB_TOKEN
    (историческое имя, общее с AI через GitHub Models), UPDATE_TOKEN
    (отдельный, только для обновлений) или GH_TOKEN. Публичному
    репозиторию токен не нужен — запросы идут анонимно.
    """
    for _k in ('GITHUB_TOKEN', 'UPDATE_TOKEN', 'GH_TOKEN'):
        _v = (os.environ.get(_k) or '').strip()
        if _v:
            return _v
    return ''


def _api_headers(token=None):
    """Заголовки для запросов к api.github.com (Accept + токен, если есть)."""
    h = {'Accept': 'application/vnd.github+json'}
    token = _update_token() if token is None else (token or '')
    if token:
        h['Authorization'] = 'token ' + token
    return h


def remote_sha():
    """HEAD ветки на GitHub (для отчёта). None — если API не ответил."""
    try:
        import requests
        _repo, _branch = _source()
        url = 'https://api.github.com/repos/{}/commits/{}'.format(
            _repo, _branch)
        r = requests.get(url, timeout=10, headers=_api_headers())
        if r.status_code == 200:
            return str(r.json().get('sha') or '') or None
        log.debug('self_update: remote_sha http %s', r.status_code)
    except Exception as _ex:
        log.debug('self_update: remote_sha: %s', _ex)
    return None


def zip_url():
    """Публичная ссылка codeload на zip ветки (только для public-репозитория).

    У приватного репозитория эта ссылка без токена отдаёт 404 — качайте
    через download_zip(), он сам выберет авторизованный api.zipball.
    """
    _repo, _branch = _source()
    return 'https://codeload.github.com/{}/zip/refs/heads/{}'.format(
        _repo, _branch)


def zipball_url():
    """Авторизованная ссылка api.github.com на zip ветки (приватный репозиторий).

    GitHub отвечает 302 на подписанную codeload-ссылку; requests идёт за
    редиректом сам. Без токена у приватного репозитория — 404.
    """
    _repo, _branch = _source()
    return 'https://api.github.com/repos/{}/zipball/{}'.format(
        _repo, _branch)


def download_zip(dest_dir):
    """Скачать zip ветки в dest_dir/update.zip. Возвращает (ok, err, path).

    Публичный репозиторий — codeload анонимно. Приватный — api.zipball с
    токеном из .env (GITHUB_TOKEN / UPDATE_TOKEN / GH_TOKEN): без токена
    GitHub отвечает 404, и мы честно подсказываем, что нужно добавить.
    """
    try:
        import requests
    except ImportError:
        return False, 'нет библиотеки requests — обновление недоступно', None
    token = _update_token()
    if token:
        url = zipball_url()
        headers = _api_headers(token)
    else:
        url = zip_url()
        headers = None
    path = os.path.join(dest_dir, 'update.zip')
    total = 0
    try:
        with requests.get(url, stream=True, timeout=(10, 120),
                          headers=headers) as r:
            if r.status_code != 200:
                # 404 у приватного репозитория без токена GitHub отдаёт
                # нарочно (чтобы не светить существование репозитория) —
                # подсказываем владельцу, что делать.
                if not token and r.status_code == 404:
                    hint = (' Репозиторий приватный? Добавьте GITHUB_TOKEN '
                            '(или UPDATE_TOKEN) с доступом на чтение кода '
                            'в .env и повторите /update.')
                elif token and r.status_code in (401, 403):
                    hint = (' GITHUB_TOKEN не подходит: нужен токен с '
                            'доступом на чтение содержимого репозитория.')
                else:
                    hint = ''
                return False, (f'GitHub ответил {r.status_code} — репозиторий '
                               f'или ветка недоступны.{hint}'), None
            with open(path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=1024 * 256):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > _MAX_ZIP_BYTES:
                        return False, 'архив подозрительно большой — обновление отменено', None
                    f.write(chunk)
    except Exception as _ex:
        log.warning('self_update: download: %s', _ex)
        return False, 'не удалось скачать архив (сеть или GitHub)', None
    return True, None, path


def verify_zip(path):
    """Целостность архива. Возвращает (ok, err, names: set относительных путей)."""
    if not os.path.isfile(path) or os.path.getsize(path) < 100:
        return False, 'архив пуст или не скачался', None
    try:
        zf = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        return False, 'скачался битый архив (не zip)', None
    with zf:
        bad = zf.testzip()
        if bad is not None:
            return False, f'архив повреждён (файл {bad} не читается)', None
        names = zf.namelist()
    if not names:
        return False, 'архив пустой', None
    root = names[0].split('/')[0] + '/'
    rel = {n[len(root):] for n in names if n.startswith(root) and len(n) > len(root)}
    missing = [req for req in REQUIRED_FILES if req not in rel]
    if missing:
        return False, 'в архиве нет ' + ', '.join(missing) + ' — это не ветка бота', None
    return True, None, (zf and names, root, rel)


def verify_python(zip_path, root):
    """Каждый .py в архиве должен компилироваться. Возвращает (ok, err)."""
    tmp = tempfile.mkdtemp(prefix='hakumo_upd_check_')
    try:
        with zipfile.ZipFile(zip_path) as zf:
            py_files = [n for n in zf.namelist()
                        if n.startswith(root) and n.endswith('.py') and '__pycache__' not in n]
            if not py_files:
                return False, 'в архиве нет python-файлов'
            zf.extractall(tmp, members=py_files)
        base = os.path.join(tmp, root.rstrip('/'))
        for dirpath, _dirs, files in os.walk(base):
            for fn in files:
                if not fn.endswith('.py'):
                    continue
                fpath = os.path.join(dirpath, fn)
                try:
                    # quiet=0: иначе (2) py_compile молча проглатывает и ошибки
                    py_compile.compile(fpath, doraise=True, quiet=0)
                except py_compile.PyCompileError as _ex:
                    return False, f'файл {os.path.relpath(fpath, base)} не компилируется (синтаксис)'
        return True, None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _preserved(rel_parts, root_parts):
    """rel_parts — путь под корнем проекта (list). True — не трогать."""
    if not rel_parts:
        return True
    head = rel_parts[0]
    if head in PRESERVE_DIRS:
        return True
    if len(rel_parts) == 1 and rel_parts[0] in PRESERVE_FILES:
        return True
    if rel_parts[0] in PRESERVE_FILES:
        return True
    if '__pycache__' in rel_parts or rel_parts[-1].endswith(('.pyc', '.pyo')):
        return True
    return False


def _archive_rel_set(rel_names):
    """Множество относительных путей файлов из архива (нормализованные sep)."""
    out = set()
    for n in (rel_names or ()):  # str pathlib-ish унификация
        out.add(os.path.normpath(str(n)))
    return out


def _remove_stale_files(bot_dir, fresh_set, stats):
    """Удалить из bot_dir всё, чего НЕТ в свежем архиве.

    Только это и делает обновление «только свежим»: старые удалённые из репо
    файлы не остаются рядом с новыми. Пропуски — PRESERVE-список и всё,
    что вне репозиторного кода (логи, данные, виртуальные окружения).
    Любая ошибка удаления — не фатал: файл просто останется.
    """
    removed = 0
    if not fresh_set:
        return removed
    for dirpath, dirs, files in os.walk(bot_dir):
        dirs[:] = [d for d in dirs if d not in PRESERVE_DIRS]
        rel_dir = os.path.relpath(dirpath, bot_dir)
        rel_parts0 = [] if rel_dir == '.' else rel_dir.split(os.sep)
        for fn in files:
            parts = rel_parts0 + [fn]
            if _preserved(parts, None):
                continue
            rel = os.path.normpath(os.path.join(*parts)) if parts else fn
            if rel in fresh_set:
                continue
            fpath = os.path.join(dirpath, fn)
            try:
                os.unlink(fpath)
                removed += 1
            except OSError:
                log.debug('self_update: не удалось убрать устаревший %s', rel)
    # почти пустые каталоги после зачистки — тоже свежести не мешают
    for dirpath, dirs, files in os.walk(bot_dir, topdown=False):
        dirs[:] = [d for d in dirs if d not in PRESERVE_DIRS]
        rel_dir = os.path.relpath(dirpath, bot_dir)
        if rel_dir == '.':
            continue
        if any(p.startswith(os.path.normpath(rel_dir) + os.sep) for p in fresh_set):
            continue
        try:
            if not os.listdir(dirpath):
                os.rmdir(dirpath)
        except OSError as _ex:
            log.debug('self_update: не удалось убрать пустой каталог %s: %s', dirpath, _ex)
    return removed


def _file_sha256(path):
    """sha256 содержимого файла или None (файла нет/не читается)."""
    try:
        h = hashlib.sha256()
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(1024 * 256), b''):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _files_equal(src, dst):
    """Содержимое совпадает? Быстрый отсев по размеру, потом хэш."""
    try:
        if os.path.getsize(src) != os.path.getsize(dst):
            return False
    except OSError:
        return False
    a = _file_sha256(src)
    b = _file_sha256(dst)
    return a is not None and a == b


def stage_update(zip_path, bot_dir, root, rel_names, channel_id=0, sha='', branch=''):
    """Раскатать СВЕЖЕЕ состояние ветки поверх bot_dir — ИНКРЕМЕНТАЛЬНО.

    Перезаписываются только файлы, чьё содержимое реально изменилось
    (сравнение по sha256): неизменённые вообще не трогаются — развёртывание
    на долю секунды вместо перезаписи всего бота, диск и mtime не дёргаем.
    После копирования убираем файлы, отсутствующие в архиве — в итоге каталог
    содержит ровно свежайшую версию (плюс data/logs/.env/venv).
    """
    tmp = tempfile.mkdtemp(prefix='hakumo_upd_')
    copied = 0
    unchanged = 0
    skipped = 0
    removed = 0
    try:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(tmp)
        src_root = os.path.join(tmp, root.rstrip('/'))
        fresh_set = set()
        for dirpath, dirs, files in os.walk(src_root):
            dirs[:] = [d for d in dirs if d not in PRESERVE_DIRS]
            rel_dir = os.path.relpath(dirpath, src_root)
            rel_parts = [] if rel_dir == '.' else rel_dir.split(os.sep)
            for fn in files:
                parts = rel_parts + [fn]
                if _preserved(parts, None):
                    skipped += 1
                    continue
                src = os.path.join(dirpath, fn)
                dst = os.path.join(bot_dir, *parts)
                fresh_set.add(os.path.normpath(os.path.join(*parts)))
                if _files_equal(src, dst):
                    unchanged += 1
                    continue
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
                copied += 1
        removed = _remove_stale_files(bot_dir, fresh_set, None)
        # маркер для приветствия после рестарта
        os.makedirs(os.path.join(bot_dir, 'data'), exist_ok=True)
        marker = {
            'sha': str(sha or ''),
            'branch': str(branch or ''),
            'channel_id': int(channel_id or 0),
            'at': _utcnow_iso(),
            'files_copied': copied,
            'files_unchanged': unchanged,
            'files_removed': removed,
        }
        with open(marker_path(bot_dir), 'w', encoding='utf-8') as f:
            json.dump(marker, f, ensure_ascii=False)
        # запомнить ветку для не-git копии: следующий /update возьмёт её
        # же (а не захардкоженный main) — фикс «обновление откатывает фиксы».
        if branch:
            try:
                with open(os.path.join(bot_dir, 'data', '.update_branch'),
                          'w', encoding='utf-8') as f:
                    f.write(str(branch).strip())
            except OSError as _ex:
                log.debug('self_update: .update_branch: %s', _ex)
        log.info('self_update: изменено %s файлов (без изменений %s), '
                 'устаревших убрано %s (пропущено служебных %s)',
                 copied, unchanged, removed, skipped)
        return True, None, {'copied': copied, 'skipped': skipped,
                            'removed': removed, 'unchanged': unchanged}
    except Exception as _ex:
        log.warning('self_update: stage: %s', _ex)
        return False, 'не удалось раскатать файлы (права на каталог бота?)', None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def peek_pending(bot_dir):
    """Прочитать маркер ожидающего подтверждения обновления (dict или None)."""
    try:
        with open(marker_path(bot_dir), encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def pop_pending(bot_dir):
    """Забрать и снять маркер (после приветствия)."""
    data = peek_pending(bot_dir)
    _Path(marker_path(bot_dir)).unlink(missing_ok=True)
    return data


async def announce_pending(bot, bot_dir):
    """После рестарта: если обновление только что раскатано — отчитаться в канал."""
    data = pop_pending(bot_dir)
    if not data:
        return False
    sha = (data.get('sha') or '')[:7]
    branch = data.get('branch') or ''
    channel = None
    try:
        if data.get('channel_id'):
            channel = bot.get_channel(int(data['channel_id']))
            if channel is None:
                channel = await bot.fetch_channel(int(data['channel_id']))
    except Exception as _ex:
        log.debug('self_update: announce channel: %s', _ex)
        channel = None
    text = ('Обновление завершено: версия **{}** ({}) — изменено **{}** файлов '
            '(ещё {} были уже актуальны, их не трогали). '
            'Все системы запущены заново и живы.').format(
                sha or 'из архива', branch or 'ветка',
                int(data.get('files_copied') or 0),
                int(data.get('files_unchanged') or 0))
    if channel is not None:
        try:
            await channel.send(text)
        except Exception as _ex:
            log.debug('self_update: announce send: %s', _ex)
            return False
    log.info('self_update: %s', text)
    return True
