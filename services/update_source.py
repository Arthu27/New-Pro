# -*- coding: utf-8 -*-
"""Источник обновлений: ОТКУДА бот качает свежие версии.

Заказ 30.08 «дай, я поставлю, откуда он будет скачивать»: владелец хочет
сам указывать репозиторий и ветку — из панели, без правки .env на
машине. Приоритет: тумблер панели (data/update_source.json) → .env
(UPDATE_REPO / UPDATE_BRANCH) → значения по умолчанию.

Один и тот же источник читают ВСЕ пути обновления: команда /update
(services/self_update) и демон auto_update.py — расхождение источников
когда-то стоило владельцу «демон откатил ветку».
"""
import json
import logging
import os
import re
import threading

_PATH = 'data/update_source.json'
_lock = threading.Lock()
_log = None

DEFAULT_REPO = 'Arthu27/New-Pro'
DEFAULT_BRANCH = 'main'

# репозиторий — «владелец/имя» (каждая часть начинается с буквы/цифры,
# без '..'); ветка — обычное имя ветки (слэши ок: arena/01a04e42-new-pro).
# Всё прочее (пробелы, '..', ведущие точки/дефисы) — мимо: это URL.
_REPO_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*$')
_BRANCH_RE = re.compile(r'^[A-Za-z0-9._/-]{1,120}$')


def _logger():
    global _log
    if _log is None:
        _log = logging.getLogger('update_source')
        _log.addHandler(logging.NullHandler())
    return _log


def _read():
    if not os.path.exists(_PATH):
        return None
    try:
        with open(_PATH, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data
        _logger().warning('update_source: %s непонятного вида — беру .env', _PATH)
    except (OSError, json.JSONDecodeError) as ex:
        _logger().warning('update_source: прочитать %s не вышло (%s) — беру .env',
                          _PATH, ex)
    return None


def _env(name, default):
    return (os.environ.get(name, '') or '').strip() or default


def get_repo():
    """Репозиторий обновлений: панель → .env → Arthu27/New-Pro."""
    data = _read()
    if data:
        repo = str(data.get('repo') or '').strip()
        if _REPO_RE.match(repo):
            return repo
    return _env('UPDATE_REPO', DEFAULT_REPO)


def get_branch():
    """Ветка обновлений: панель → .env → main."""
    data = _read()
    if data:
        branch = str(data.get('branch') or '').strip()
        if _BRANCH_RE.match(branch):
            return branch
    return _env('UPDATE_BRANCH', DEFAULT_BRANCH)


def validate(repo, branch):
    """(ok, error) — можно ли такое сохранить."""
    repo = str(repo or '').strip()
    branch = str(branch or '').strip()
    if (not _REPO_RE.match(repo) or '..' in repo
            or '..' in branch or branch.startswith('-')
            or not _BRANCH_RE.match(branch)):
        return False, ('Репозиторий — в виде «владелец/имя» (например '
                       'Arthu27/New-Pro), ветка — обычное имя ветки '
                       '(например main или arena/01a04e42-new-pro); '
                       f'получилось «{repo}» / «{branch}»)')
    return True, ''


def set_source(repo, branch):
    """Сохранить источник тумблером панели. (ok, error, значения)."""
    ok, error = validate(repo, branch)
    if not ok:
        return False, error, (get_repo(), get_branch())
    with _lock:
        try:
            os.makedirs(os.path.dirname(_PATH) or '.', exist_ok=True)
            tmp = _PATH + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as fh:
                json.dump({'repo': str(repo).strip(), 'branch': str(branch).strip()},
                          fh, ensure_ascii=False)
            os.replace(tmp, _PATH)
        except OSError as ex:
            _logger().warning('update_source: записать %s не вышло: %s', _PATH, ex)
            return False, f'Не удалось сохранить: {ex}', (get_repo(), get_branch())
    _logger().info('update_source: источник обновлений = %s@%s',
                   get_repo(), get_branch())
    return True, '', (get_repo(), get_branch())


def source_kind():
    """Откуда действует текущий источник: 'панель' | '.env/по умолчанию'."""
    return 'панель' if _read() else '.env / по умолчанию'
