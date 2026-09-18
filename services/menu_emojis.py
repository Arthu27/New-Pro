# -*- coding: utf-8 -*-
"""Кастомные эмодзи меню из assets/stickers (Application Emoji).

Белые neon-стикеры заливаются как эмодзи приложения бота
(create_application_emoji) — тогда их видно в селектах /modpanel
без ручной заливки на сервер. Имена: hakumo_w_warn, hakumo_w_mute, …
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

import discord

from logger import get_logger

_log = get_logger('menu_emojis')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STICKERS = os.path.join(ROOT, 'assets', 'stickers')

# ключ файла → имя эмодзи приложения
STICKER_KEYS = (
    'warn', 'mute', 'ban', 'clear', 'unban',
    'appeal', 'helper', 'moderator', 'heart',
)

# действие /modpanel → ключ стикера
ACTION_STICKER = {
    'warn': 'warn',
    'unwarn': 'helper',
    'mute': 'mute',
    'unmute': 'unban',
    'timeout': 'mute',
    'mute_chat': 'mute',
    'vmute': 'mute',
    'untimeout': 'unban',
    'unmute_chat': 'unban',
    'vunmute': 'unban',
    'ban': 'ban',
    'unban': 'unban',
    'clear': 'clear',
}

# фолбек, пока эмодзи ещё не залиты
_UNICODE = {
    'warn': '⚠️',
    'unwarn': '✖️',
    'mute': '🔇',
    'unmute': '🔊',
    'timeout': '🔇',
    'mute_chat': '💬',
    'vmute': '🎙️',
    'untimeout': '🔊',
    'unmute_chat': '💬',
    'vunmute': '🔊',
    'ban': '⛔',
    'unban': '🔓',
    'clear': '🧹',
}

_cache: Dict[str, Any] = {}
_synced = False


def _emoji_name(key: str) -> str:
    # w_ = белый неон-пак (v2); старые hakumo_* не трогаем
    return f'hakumo_w_{key}'


def sticker_path(key: str) -> Optional[str]:
    path = os.path.join(STICKERS, f'{key}.png')
    return path if os.path.isfile(path) else None


def get_cached(key: str):
    return _cache.get(key)


def emoji_for_action(action: str):
    """PartialEmoji/Emoji для пункта селекта или unicode-фолбек."""
    key = ACTION_STICKER.get(action, 'heart')
    em = _cache.get(key)
    if em is not None:
        return em
    return _UNICODE.get(action, '🤍')


def emoji_heart():
    """Белое neon-сердечко или 🤍."""
    return _cache.get('heart') or '🤍'


async def ensure_menu_emojis(bot) -> Dict[str, Any]:
    """Залить белые стикеры как application emoji, заполнить кэш."""
    global _synced
    if _synced and len(_cache) >= len(STICKER_KEYS):
        return dict(_cache)
    try:
        existing = {e.name: e for e in await bot.fetch_application_emojis()}
    except Exception as ex:
        _log.warning('menu_emojis: fetch_application_emojis: %s', ex)
        existing = {}

    for key in STICKER_KEYS:
        name = _emoji_name(key)
        if name in existing:
            _cache[key] = existing[name]
            continue
        # фолбек на старое имя, если белое ещё не создано, но золотое есть
        legacy = f'hakumo_{key}'
        path = sticker_path(key)
        if not path:
            _log.warning('menu_emojis: нет файла %s', key)
            if legacy in existing:
                _cache[key] = existing[legacy]
            continue
        try:
            with open(path, 'rb') as f:
                image = f.read()
            em = await bot.create_application_emoji(name=name, image=image)
            _cache[key] = em
            existing[name] = em
            _log.info('menu_emojis: создан %s id=%s', name, em.id)
        except Exception as ex:
            _log.warning('menu_emojis: create %s: %s', name, ex)
            if name in existing:
                _cache[key] = existing[name]
            elif legacy in existing:
                _cache[key] = existing[legacy]

    _synced = True
    return dict(_cache)
