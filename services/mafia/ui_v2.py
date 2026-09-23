# -*- coding: utf-8 -*-
"""Components V2-раскладки для Мафии + стикеры Hakumo на всё."""
from __future__ import annotations

import discord

from logger import get_logger

_log = get_logger('mafia_v2')

try:
    from services.v2_layouts import (
        V2_AVAILABLE, SHOW_MENU_BANNER, black_container, _gallery,
    )
    from discord import ui as _ui
    from discord import SeparatorSpacing
except Exception as _ex:  # pragma: no cover
    V2_AVAILABLE = False
    _log.debug('mafia_v2 import: %s', _ex)


_BLACK = 0x000000
_GOLD = 0xD4AF37
_BANNER = 'hakumo_events_banner_v15.png'

# kind → assets/stickers/{key}.png (hakumo_w_*)
_STICKER_ALIAS = {
    # действия
    'join': 'signup',
    'leave': 'finish',
    'deal': 'announce',
    'refresh': 'elist',
    'kill': 'ban',
    'vote': 'warn',
    'exclude': 'clear',
    'cancel': 'finish',
    'pending': 'mute',
    'remind': 'heart',
    'play': 'start',
    'confirm': 'start',
    'menu': 'heart',
    'signup': 'signup',
    'elist': 'elist',
    # роли (путана / мафия / … — те же neon-стики)
    'mafia': 'ban',
    'don': 'moderator',
    'sheriff': 'helper',
    'doctor': 'appeal',
    'courtesan': 'heart',  # путана
    'putana': 'heart',
    'citizen': 'user',
}

_UNICODE = {
    'join': '✋', 'leave': '🚪', 'deal': '🎭', 'refresh': '🔄',
    'kill': '🔫', 'vote': '🗳️', 'exclude': '🚫', 'cancel': '🗑️',
    'pending': '⏳', 'remind': '🔔', 'play': '▶', 'confirm': '✅',
    'menu': '🎲', 'signup': '✋', 'elist': '📋',
    'mafia': '🔴', 'don': '👑', 'sheriff': '🕵️', 'doctor': '💉',
    'courtesan': '💋', 'putana': '💋', 'citizen': '👤',
}


def sticker(kind: str):
    """Application-emoji стикер Hakumo или unicode-фолбек."""
    try:
        from services.menu_emojis import emoji_for_event, get_cached
        key = _STICKER_ALIAS.get(kind, kind)
        em = get_cached(key)
        if em is None and key in (
            'signup', 'announce', 'start', 'finish', 'elist',
            'warn', 'mute', 'ban', 'clear', 'unban', 'appeal',
            'helper', 'moderator', 'heart', 'staff', 'user',
        ):
            em = emoji_for_event(key) if key in (
                'signup', 'announce', 'start', 'finish', 'elist', 'reg',
            ) else get_cached(key)
        if em is None:
            # общий путь через get_cached после sync
            from services.menu_emojis import get_cached as gc
            em = gc(key)
        if em is not None:
            return em
    except Exception:
        pass
    return _UNICODE.get(kind, '🎲')


def role_sticker(role_key: str):
    """Стикер роли (в т.ч. путана → heart)."""
    return sticker(role_key if role_key in _STICKER_ALIAS else 'citizen')


def role_mark(role_key: str) -> str:
    """Текст с mention стикера, если есть PartialEmoji."""
    em = role_sticker(role_key)
    try:
        if hasattr(em, 'id') and getattr(em, 'id', None):
            return str(em)
    except Exception:
        pass
    return _UNICODE.get(role_key, '🎲')


def mafia_banner_file():
    try:
        if not SHOW_MENU_BANNER:
            return None, None
        from services.menu_banners import menu_banner_file
        import io
        bio, name = menu_banner_file('events')
        raw = bio.getvalue() if hasattr(bio, 'getvalue') else bio.read()
        out = io.BytesIO(raw)
        out.seek(0)
        return discord.File(out, filename=name), name
    except Exception as ex:
        _log.debug('mafia banner: %s', ex)
        return None, None


def build_mafia_lobby_items(*, title: str, body: str, banner_filename: str = None,
                            action_row=None, accent: int = _BLACK):
    if not V2_AVAILABLE:
        return None
    head = [
        _ui.TextDisplay(f'# {title}\n-# HAKUMO · MAFIA'),
        _ui.Separator(spacing=SeparatorSpacing.large),
    ]
    if SHOW_MENU_BANNER and banner_filename:
        head.append(_gallery(banner_filename))
    head.append(_ui.TextDisplay(body[:3900]))
    items = [black_container(*head, accent=accent)]
    if action_row is not None:
        items.append(black_container(
            _ui.TextDisplay('**Участникам**\n-# только записаться / выйти'),
            action_row,
            accent=accent,
        ))
    return items


def build_mafia_menu_items(*, body: str, select_row, banner_filename: str = None,
                           accent: int = _BLACK):
    if not V2_AVAILABLE:
        return None
    head = [
        _ui.TextDisplay('# Мафия\n-# HAKUMO · MENU · ведущий'),
        _ui.Separator(spacing=SeparatorSpacing.large),
    ]
    if SHOW_MENU_BANNER and banner_filename:
        head.append(_gallery(banner_filename))
    head.append(_ui.TextDisplay(body[:3900]))
    items = [black_container(*head, accent=accent)]
    items.append(black_container(
        _ui.TextDisplay('**Действие**\n-# только ведущему / модеру'),
        select_row,
        accent=accent,
    ))
    return items


def build_mafia_status_items(*, title: str, body: str, accent: int = _GOLD):
    if not V2_AVAILABLE:
        return None
    return [black_container(
        _ui.TextDisplay(f'# {title}\n-# HAKUMO · MAFIA'),
        _ui.Separator(spacing=SeparatorSpacing.large),
        _ui.TextDisplay(body[:3900]),
        accent=accent,
    )]


def build_mafia_host_items(*, title: str, body: str,
                           row0=None, row1=None, row2=None, row3=None,
                           accent: int = _BLACK):
    if not V2_AVAILABLE:
        return None
    items = [black_container(
        _ui.TextDisplay(f'# {title}\n-# только ведущему'),
        _ui.Separator(spacing=SeparatorSpacing.large),
        _ui.TextDisplay(body[:3900]),
        accent=accent,
    )]
    for label, row in (
        ('Подтверждения', row0),
        ('Стол', row1),
        ('Ночь / день', row2),
        ('Сброс', row3),
    ):
        if row is None:
            continue
        items.append(black_container(
            _ui.TextDisplay(f'**{label}**'),
            row,
            accent=accent,
        ))
    return items
