# -*- coding: utf-8 -*-
"""Application emoji для support-бота (assets/stickers/s_*.png)."""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from logger import get_logger

log = get_logger('support_emojis')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STICKERS = os.path.join(ROOT, 'assets', 'stickers')

STICKER_KEYS = (
    's_verify', 's_deny', 's_undeny', 's_male', 's_female',
    's_gender', 's_review', 's_support', 'appeal',
)

_UNICODE = {
    's_verify': '✅',
    's_deny': '🚫',
    's_undeny': '🔓',
    's_male': '♂️',
    's_female': '♀️',
    's_gender': '🔄',
    's_review': '⭐',
    's_support': '🎧',
    'appeal': '📝',
}

_cache: Dict[str, Any] = {}
_synced = False


def sticker_path(key: str) -> Optional[str]:
    path = os.path.join(STICKERS, f'{key}.png')
    return path if os.path.isfile(path) else None


def emoji_for(key: str):
    return _cache.get(key) or _UNICODE.get(key, '🤍')


async def ensure_support_emojis(bot) -> Dict[str, Any]:
    global _synced
    if _synced and len(_cache) >= 4:
        return dict(_cache)
    try:
        existing = {e.name: e for e in await bot.fetch_application_emojis()}
    except Exception as ex:
        log.warning('support_emojis fetch: %s', ex)
        existing = {}
    for key in STICKER_KEYS:
        name = f'hakumo_{key}'
        if name in existing:
            _cache[key] = existing[name]
            continue
        path = sticker_path(key)
        if not path:
            continue
        try:
            with open(path, 'rb') as f:
                image = f.read()
            em = await bot.create_application_emoji(name=name, image=image)
            _cache[key] = em
            existing[name] = em
            log.info('support_emojis: %s id=%s', name, em.id)
        except Exception as ex:
            log.warning('support_emojis create %s: %s', name, ex)
            if name in existing:
                _cache[key] = existing[name]
    _synced = True
    return dict(_cache)
