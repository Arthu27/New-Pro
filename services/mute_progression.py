# -*- coding: utf-8 -*-
"""Потолок срока мута (без прогрессии «+2»).

Раньше: первый мут 1 ч, каждый следующий +2 ч до варна.
Заказ владельца 2026-09-25: систему «+2» отменяем — срок выбирает
персонал в UI (мин. 30 мин, потолок FIXED_CAP_SEC), без авто-эскалации.

Модуль оставлен для совместимости импортов (bump/reset — no-op).
"""
from __future__ import annotations

from logger import get_logger

_log = get_logger('mute_progression')

# Фиксированный потолок без прогрессии (совпадает с подсказкой UI «… 2 ч»)
FIRST_CAP_SEC = 2 * 3600
STEP_SEC = 0                  # +2 отключён
FIXED_CAP_SEC = 2 * 3600
MAX_CAP_SEC = 28 * 86400
ENABLED = False               # прогрессия выключена


def _path(gid):
    return f'data/mute_progression_{int(gid)}.json'


def step_for(guild_id, target_id) -> int:
    """Всегда 0 — прогрессия отключена."""
    return 0


def cap_seconds(guild_id, target_id) -> int:
    """Фиксированный потолок (2 ч), без +2 по участнику."""
    return min(MAX_CAP_SEC, FIXED_CAP_SEC)


def bump_after_mute(guild_id, target_id) -> int:
    """No-op: систему +2 отменили."""
    return 0


def reset_on_warn(guild_id, target_id) -> None:
    """No-op: прогрессии больше нет."""
    return None
