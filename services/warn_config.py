# -*- coding: utf-8 -*-
"""Конфиг единой роли warn и веток стаффа.

Ветка = должность набора (helper/moderator/event/…). Роли веток и
кураторов («× Отвечаю за …») берутся из services.staff_roles — единый
источник, без хардкода ID по коду варнов.
"""
from __future__ import annotations

import os

from logger import get_logger

_log = get_logger('warn_config')

# Единая роль warn (счётчик — только в БД, не уровнями warn_1/2/3).
# Переопределяется WARN_ROLE_ID в .env.
_DEFAULT_WARN_ROLE_ID = 1545468739221327942


def warn_role_id() -> int:
    """Snowflake роли warn. 0 = роль не настроена."""
    raw = (os.getenv('WARN_ROLE_ID') or '').strip()
    if raw:
        try:
            return int(raw)
        except (TypeError, ValueError):
            _log.warning('WARN_ROLE_ID=%r не число — дефолт', raw)
    try:
        from config import Config
        return int(getattr(Config, 'WARN_ROLE_ID', 0) or _DEFAULT_WARN_ROLE_ID)
    except Exception:
        return _DEFAULT_WARN_ROLE_ID


def branch_labels() -> dict:
    """kind → человекочитаемое имя ветки."""
    return {
        'helper': 'Helper',
        'moderator': 'Moderator',
        'event': 'Eventsmod',
        'support': 'Support',
        'closemod': 'Close mod',
        'creative': 'Creative',
        'broadcaster': 'Broadcaster',
    }


def branch_grant_roles() -> dict:
    """kind → role_id выдаваемой роли ветки."""
    out = {}
    try:
        from services.staff_roles import KNOWN_GRANT_BY_KIND
        for kind, rid in (KNOWN_GRANT_BY_KIND or {}).items():
            try:
                out[str(kind)] = int(rid)
            except (TypeError, ValueError):
                continue
    except Exception as _ex:
        _log.debug('branch_grant_roles: %s', _ex)
    return out


def branch_curator_roles() -> dict:
    """kind → role_id куратора ветки («× Отвечаю за …»)."""
    out = {}
    try:
        from services.staff_roles import KNOWN_CURATOR_BY_KIND
        for kind, rid in (KNOWN_CURATOR_BY_KIND or {}).items():
            try:
                out[str(kind)] = int(rid)
            except (TypeError, ValueError):
                continue
    except Exception as _ex:
        _log.debug('branch_curator_roles: %s', _ex)
    return out


def format_branches(kinds) -> str:
    labels = branch_labels()
    names = [labels.get(k, k) for k in sorted(kinds or [])]
    return ', '.join(names) if names else '—'
