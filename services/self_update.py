# -*- coding: utf-8 -*-
"""Самообновление бота по команде /update (заказ, пункт 5.6).

Один вызов — и всё делает бот сам, без ручного скачивания:

1. download_zip()  — качает zip ветки репозитория с GitHub (codeload).
2. verify_zip()    — целостность: это валидный zip, есть опорные файлы
                     (main.py, config.py, web/app.py), архив не битый,
                     каждый .py компилируется (py_compile).
3. stage_update()  — раскатывает файлы ПОВЕРХ рабочей копии, бережно сохраняя
                     данные и секреты (data/, logs/, .env, .git, .venv —
                     в исключениях), и пишет маркер data/update_pending.json
                     (sha/ветка/канал подтверждения после рестарта).
4. ког делает os.execv — процесс заменяется свежим кодом; на on_ready
                     main.py отчитывается в канал из маркера.

Функции синхронные — из кога зовутся через asyncio.to_thread.
"""

import json
import os
import py_compile
import shutil
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


def marker_path(bot_dir):
    return os.path.join(bot_dir, 'data', 'update_pending.json')


def remote_sha():
    """HEAD ветки на GitHub (для отчёта). None — если API не ответил."""
    try:
        import requests
        from config import Config
        url = 'https://api.github.com/repos/{}/commits/{}'.format(
            Config.UPDATE_REPO, Config.UPDATE_BRANCH)
        r = requests.get(url, timeout=10, headers={'Accept': 'application/vnd.github+json'})
        if r.status_code == 200:
            return str(r.json().get('sha') or '') or None
        log.debug('self_update: remote_sha http %s', r.status_code)
    except Exception as _ex:
        log.debug('self_update: remote_sha: %s', _ex)
    return None


def zip_url():
    from config import Config
    return 'https://codeload.github.com/{}/zip/refs/heads/{}'.format(
        Config.UPDATE_REPO, Config.UPDATE_BRANCH)


def download_zip(dest_dir):
    """Скачать zip ветки в dest_dir/update.zip. Возвращает (ok, err, path)."""
    try:
        import requests
    except ImportError:
        return False, 'нет библиотеки requests — обновление недоступно', None
    url = zip_url()
    path = os.path.join(dest_dir, 'update.zip')
    total = 0
    try:
        with requests.get(url, stream=True, timeout=(10, 120)) as r:
            if r.status_code != 200:
                return False, f'GitHub ответил {r.status_code} — репозиторий или ветка недоступны', None
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


def stage_update(zip_path, bot_dir, root, rel_names, channel_id=0, sha='', branch=''):
    """Раскатать архив поверх bot_dir. Возвращает (ok, err, статистика).

    Копируем файлами (не хирургия каталогов): на Windows занятые ботом
    каталоги переименовать нельзя, а замена файлов внутри — можно.
    """
    tmp = tempfile.mkdtemp(prefix='hakumo_upd_')
    copied = 0
    skipped = 0
    try:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(tmp)
        src_root = os.path.join(tmp, root.rstrip('/'))
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
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
                copied += 1
        # маркер для приветствия после рестарта
        os.makedirs(os.path.join(bot_dir, 'data'), exist_ok=True)
        marker = {
            'sha': str(sha or ''),
            'branch': str(branch or ''),
            'channel_id': int(channel_id or 0),
            'at': _utcnow_iso(),
            'files_copied': copied,
        }
        with open(marker_path(bot_dir), 'w', encoding='utf-8') as f:
            json.dump(marker, f, ensure_ascii=False)
        log.info('self_update: раскатано %s файлов (пропущено %s)', copied, skipped)
        return True, None, {'copied': copied, 'skipped': skipped}
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
    text = ('Обновление завершено: версия **{}** ({}) — {} файлов. '
            'Все системы запущены заново и живы.').format(
                sha or 'из архива', branch or 'ветка', int(data.get('files_copied') or 0))
    if channel is not None:
        try:
            await channel.send(text)
        except Exception as _ex:
            log.debug('self_update: announce send: %s', _ex)
            return False
    log.info('self_update: %s', text)
    return True
