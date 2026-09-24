# -*- coding: utf-8 -*-
"""Прогрессия срока мута по участнику (заказ владельца 2026-09-24).

Первый мут — максимум 2 часа. Каждый следующий — +2 часа
(2 → 4 → 6 → 8 …). Когда участник получает варн — прогрессия
сбрасывается, снова с 2 часов.

Хранится per-target: data/mute_progression_<gid>.json
  { "<uid>": {"step": 0} }   # step 0 = первый мут (2ч)
"""
from __future__ import annotations

import json
import os

from logger import get_logger

_log = get_logger('mute_progression')

FIRST_CAP_SEC = 2 * 3600      # 2 часа
STEP_SEC = 2 * 3600           # +2 часа за шаг
MAX_CAP_SEC = 28 * 86400      # потолок Discord


def _path(gid):
    return f'data/mute_progression_{int(gid)}.json'


def _load(gid):
    path = _path(gid)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError) as ex:
        _log.debug('mute_progression load: %s', ex)
        return {}


def _save(gid, data):
    os.makedirs('data', exist_ok=True)
    path = _path(gid)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False)
    os.replace(tmp, path)


def step_for(guild_id, target_id) -> int:
    """0-based шаг прогрессии цели."""
    try:
        row = _load(guild_id).get(str(int(target_id))) or {}
        return max(0, int(row.get('step') or 0))
    except (TypeError, ValueError):
        return 0


def cap_seconds(guild_id, target_id) -> int:
    """Потолок мута в секундах: 2ч + step×2ч (клэмп 28 дн.)."""
    step = step_for(guild_id, target_id)
    return min(MAX_CAP_SEC, FIRST_CAP_SEC + step * STEP_SEC)


def bump_after_mute(guild_id, target_id) -> int:
    """После успешного мута: step += 1. Возвращает новый step."""
    try:
        uid = str(int(target_id))
        data = _load(guild_id)
        row = data.get(uid) if isinstance(data.get(uid), dict) else {}
        step = max(0, int(row.get('step') or 0)) + 1
        data[uid] = {'step': step}
        _save(guild_id, data)
        return step
    except Exception as ex:
        _log.debug('bump_after_mute: %s', ex)
        return 0


def reset_on_warn(guild_id, target_id) -> None:
    """Варн → прогрессия с нуля (снова 2 часа)."""
    try:
        uid = str(int(target_id))
        data = _load(guild_id)
        data[uid] = {'step': 0}
        _save(guild_id, data)
    except Exception as ex:
        _log.debug('reset_on_warn: %s', ex)
