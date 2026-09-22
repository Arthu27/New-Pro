# -*- coding: utf-8 -*-
"""Аккуратная запись ключей в локальный .env (gitignored).

Панель «Совместные боты» пишет EVENT_BOT_TOKEN сюда — никогда в JSON
под git. Пустое value удаляет ключ.
"""
from __future__ import annotations

import os
import re
from typing import Iterable

from logger import get_logger

_log = get_logger('env_file')

_KEY_RE = re.compile(r'^[A-Z][A-Z0-9_]*$')


def env_path(repo_root: str | None = None) -> str:
    root = repo_root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, '.env')


def upsert_env_keys(updates: dict, repo_root: str | None = None) -> dict:
    """Обновить/добавить ключи в .env и os.environ.

    updates: {KEY: value}. value '' / None → удалить ключ.
    Возвращает {written: [...], removed: [...], path: ...}.
    """
    path = env_path(repo_root)
    report = {'path': path, 'written': [], 'removed': [], 'ok': True, 'error': ''}
    clean = {}
    for k, v in (updates or {}).items():
        key = str(k or '').strip()
        if not _KEY_RE.match(key):
            report['ok'] = False
            report['error'] = f'Некорректный ключ: {key}'
            return report
        if v is None:
            clean[key] = None
        else:
            clean[key] = str(v).strip()

    lines: list[str] = []
    if os.path.isfile(path):
        try:
            with open(path, encoding='utf-8') as fh:
                lines = fh.read().splitlines()
        except OSError as ex:
            report['ok'] = False
            report['error'] = str(ex)
            return report

    seen = set()
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith('#') or '=' not in stripped:
            out.append(line)
            continue
        key, _, _rest = stripped.partition('=')
        key = key.strip()
        if key in clean:
            seen.add(key)
            val = clean[key]
            if val is None or val == '':
                report['removed'].append(key)
                os.environ.pop(key, None)
                continue
            out.append(f'{key}={val}')
            os.environ[key] = val
            report['written'].append(key)
        else:
            out.append(line)

    for key, val in clean.items():
        if key in seen:
            continue
        if val is None or val == '':
            os.environ.pop(key, None)
            report['removed'].append(key)
            continue
        out.append(f'{key}={val}')
        os.environ[key] = val
        report['written'].append(key)

    try:
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write('\n'.join(out))
            if out:
                fh.write('\n')
        os.replace(tmp, path)
    except OSError as ex:
        report['ok'] = False
        report['error'] = str(ex)
        _log.warning('env upsert: %s', ex)
    return report


def mask_secret(value: str, keep: int = 4) -> str:
    v = (value or '').strip()
    if not v:
        return ''
    if len(v) <= keep:
        return '••••'
    return '••••' + v[-keep:]
