# -*- coding: utf-8 -*-
"""Шаблоны профилей — стабильное хранилище вне git.

Проблема: `git reset --hard` / смена ветки сносит `web/static/profiles/`,
если в новой ветке этих файлов нет.

Решение: канон лежит в `data/profile_templates/` (gitignore `data/`).
Раздаём оттуда. При первом старте один раз копируем из static, если persist
пустой. Уже лежащие файлы НИКОГДА не перезаписываем — «не менялись».
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


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def persist_dir() -> Path:
    """Каталог, который git не трогает."""
    env = (os.environ.get('PROFILES_DIR') or '').strip()
    if env:
        return Path(env)
    return _repo_root() / 'data' / 'profile_templates'


def static_seed_dir() -> Path:
    return _repo_root() / 'web' / 'static' / 'profiles'


def ensure_profile_templates(*, overwrite: bool = False) -> Path:
    """Гарантировать persist-папку. Не затирает существующие файлы.

    overwrite=True — только для явного админ-восстановления (не в проде).
    """
    dest = persist_dir()
    dest.mkdir(parents=True, exist_ok=True)
    seed = static_seed_dir()
    copied = 0
    skipped = 0
    for name in REQUIRED:
        dst = dest / name
        if dst.is_file() and not overwrite:
            skipped += 1
            continue
        src = seed / name
        if src.is_file():
            shutil.copy2(src, dst)
            copied += 1
        elif not dst.is_file():
            log.warning('profile template missing in seed and persist: %s', name)
    if copied:
        log.info('profile_templates: seeded %s file(s) → %s (kept %s)',
                 copied, dest, skipped)
    return dest


def profiles_dir() -> Path:
    """Папка для send_from_directory — всегда persist после ensure."""
    return ensure_profile_templates(overwrite=False)
