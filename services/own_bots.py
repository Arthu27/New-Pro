# -*- coding: utf-8 -*-
"""ID «своих» ботов Hakumo — их нельзя кикать антирейдом/щитом.

Основной / Events / Support / Love-room. Список из env + известные
боевые id (fallback), плюс текущий bot.user.
"""
from __future__ import annotations

import os

# Боевые боты сервера (fallback, если env не задан)
_FALLBACK = frozenset({
    1421418700451348520,  # Moderation (main)
    1552093253807902770,  # Events
    1553179415821680640,  # Support
    1553044662267289802,  # Love / Broadcaster
})


def _env_ids() -> set[int]:
    out: set[int] = set()
    for key in (
        'BOT_ID', 'CLIENT_ID', 'DISCORD_CLIENT_ID',
        'EVENT_BOT_ID', 'SUPPORT_BOT_ID', 'LOVE_ROOM_BOT_ID',
        'OWN_BOT_IDS',
    ):
        raw = (os.getenv(key) or '').strip()
        if not raw:
            continue
        for part in raw.replace(';', ',').split(','):
            part = part.strip()
            if part.isdigit():
                out.add(int(part))
    return out


def own_bot_ids(bot=None) -> set[int]:
    ids = set(_FALLBACK) | _env_ids()
    try:
        uid = getattr(getattr(bot, 'user', None), 'id', None)
        if uid:
            ids.add(int(uid))
    except Exception:
        pass
    return ids


def is_own_bot(user_id, bot=None) -> bool:
    try:
        return int(user_id) in own_bot_ids(bot)
    except (TypeError, ValueError):
        return False
