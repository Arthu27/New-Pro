# -*- coding: utf-8 -*-
"""Шаблоны профилей — стабильное хранилище вне git.

Проблема: `git reset --hard` / смена ветки сносит `web/static/profiles/`,
если в новой ветке этих файлов нет → Discord/ссылки 404 («отлетели»).

Решение:
1. Канон (live) — `PROFILES_DIR` или `data/profile_templates/` (gitignore).
2. Жёсткий pin вне репо — `PROFILES_PIN_DIR` или `/var/lib/hakumo/profiles`
   (не трогается git clean / deploy).
3. Seed из `web/static/profiles` — только если в persist/pin файла ещё нет.

Уже лежащие файлы НИКОГДА не перезаписываем.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from logger import get_logger

log = get_logger('profile_templates')

# Имена, которые должны быть всегда (как у владельца).
REQUIRED = (
    'index.html',
    'profile-card.png',
    'most-active.png',
    'couple-card.png',
)

# Канонический pin вне дерева git (VDS).
DEFAULT_PIN_DIR = Path('/var/lib/hakumo/profiles')


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def persist_dir() -> Path:
    """Каталог, который отдаёт Flask (git его не трогает)."""
    env = (os.environ.get('PROFILES_DIR') or '').strip()
    if env:
        return Path(env)
    return _repo_root() / 'data' / 'profile_templates'


def pin_dir() -> Path:
    """Жёсткая копия вне /opt/hakumo — переживает любой deploy."""
    env = (os.environ.get('PROFILES_PIN_DIR') or '').strip()
    if env:
        return Path(env)
    return DEFAULT_PIN_DIR


def static_seed_dir() -> Path:
    return _repo_root() / 'web' / 'static' / 'profiles'


def _copy_if_needed(src: Path, dst: Path, *, overwrite: bool) -> bool:
    if not src.is_file():
        return False
    if dst.is_file() and not overwrite:
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def ensure_profile_templates(*, overwrite: bool = False) -> Path:
    """Гарантировать persist + pin. Не затирает существующие файлы.

    Порядок заполнения отсутствующих: pin → static seed → (уже в persist).
    После заполнения зеркалим недостающее из persist в pin.
    overwrite=True — только для явного админ-восстановления (не в проде).
    """
    dest = persist_dir()
    dest.mkdir(parents=True, exist_ok=True)
    pin = pin_dir()
    try:
        pin.mkdir(parents=True, exist_ok=True)
    except OSError as ex:
        log.warning('profile_templates: cannot create pin dir %s: %s', pin, ex)
        pin = None

    seed = static_seed_dir()
    copied = 0
    skipped = 0

    for name in REQUIRED:
        dst = dest / name
        if dst.is_file() and not overwrite:
            skipped += 1
        else:
            filled = False
            if pin is not None:
                filled = _copy_if_needed(pin / name, dst, overwrite=overwrite)
            if not filled:
                filled = _copy_if_needed(seed / name, dst, overwrite=overwrite)
            if filled:
                copied += 1
            elif not dst.is_file():
                log.warning('profile template missing in pin/seed/persist: %s', name)

        # Зеркало в pin: если в persist есть, а в pin нет — закрепить.
        if pin is not None and dst.is_file():
            pin_dst = pin / name
            if not pin_dst.is_file() or overwrite:
                try:
                    _copy_if_needed(dst, pin_dst, overwrite=overwrite or not pin_dst.is_file())
                except OSError as ex:
                    log.warning('profile_templates: pin copy %s failed: %s', name, ex)

    if copied:
        log.info('profile_templates: seeded %s file(s) → %s (kept %s, pin=%s)',
                 copied, dest, skipped, pin)
    return dest


def profiles_dir() -> Path:
    """Папка для send_from_directory — всегда persist после ensure."""
    return ensure_profile_templates(overwrite=False)


def status() -> dict:
    """Краткий статус для диагностики (без содержимого файлов)."""
    dest = persist_dir()
    pin = pin_dir()
    out = {
        'persist': str(dest),
        'pin': str(pin),
        'files': {},
    }
    for name in REQUIRED:
        p = dest / name
        out['files'][name] = {
            'persist': p.is_file(),
            'persist_bytes': p.stat().st_size if p.is_file() else 0,
            'pin': (pin / name).is_file() if pin else False,
        }
    return out
