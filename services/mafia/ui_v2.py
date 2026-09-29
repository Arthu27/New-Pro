# -*- coding: utf-8 -*-
"""Components V2 для Мафии — как /modpanel: баннер + чёрные блоки + стикеры."""
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
    SHOW_MENU_BANNER = False
    _log.debug('mafia_v2 import: %s', _ex)


_BLACK = 0x000000
_GOLD = 0xD4AF37
_BANNER = 'hakumo_events_banner_v15.png'

_STICKER_ALIAS = {
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
    'mafia': 'ban',
    'don': 'moderator',
    'sheriff': 'helper',
    'doctor': 'appeal',
    'courtesan': 'heart',
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
    try:
        from services.menu_emojis import emoji_for_event, get_cached
        key = _STICKER_ALIAS.get(kind, kind)
        em = get_cached(key)
        if em is None and key in (
            'signup', 'announce', 'start', 'finish', 'elist',
        ):
            em = emoji_for_event(key)
        if em is not None:
            return em
    except Exception:
        pass
    return _UNICODE.get(kind, '🎲')


def role_sticker(role_key: str):
    return sticker(role_key if role_key in _STICKER_ALIAS else 'citizen')


def role_mark(role_key: str) -> str:
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


def lobby_status_md(game) -> str:
    """Короткий статус для публичной карточки — без воды."""
    from services.mafia import PHASE_LOBBY
    from services.mafia.roles import preset_summary

    n = len(game.players)
    need = max(0, 6 - n)
    players = list(game.players.values())
    if players:
        roster = '\n'.join(
            f'{i}. <@{p.user_id}>' for i, p in enumerate(players[:16], 1)
        )
        if len(players) > 16:
            roster += f'\n… +{len(players) - 16}'
    else:
        roster = '_пусто_'

    lines = [
        f'**Ведущий** <@{game.host_id}>',
        f'**Войс** <#{game.voice_channel_id}>',
        f'**Состав** {n}/6+',
    ]
    if n >= 6:
        try:
            lines.append(f'**Пресет** {preset_summary(n)}')
        except Exception:
            pass
    else:
        lines.append(f'-# ещё {need} до раздачи')
    lines.append('')
    lines.append(roster)
    if getattr(game, 'phase', None) == PHASE_LOBBY and n < 6:
        lines.append('')
        lines.append('-# войс → **Участвовать**')
    return '\n'.join(lines)


def menu_status_md(game, user_id: int) -> str:
    """Одна короткая плашка для меню ведущего."""
    if game is None:
        return (
            'Партии нет.\n'
            '-# Войс → **Начать игру** · игроки жмут Участвовать'
        )
    phase_map = {
        'lobby': 'Лобби',
        'confirm': 'Подтверждение',
        'ready': 'Готово',
        'playing': 'Игра',
        'ended': 'Конец',
    }
    phase = phase_map.get(game.phase, game.phase)
    host = ' · вы ведущий' if user_id == game.host_id else ''
    return (
        f'**#{game.game_id}** · {phase}{host}\n'
        f'<#{game.voice_channel_id}> · '
        f'{len(game.players)} игроков · '
        f'{game.confirmed_count()}/{len(game.players)} ✓'
    )


def build_mafia_lobby_items(*, body: str, banner_filename: str = None,
                            action_row=None, accent: int = _BLACK):
    if not V2_AVAILABLE:
        return None
    head = [
        _ui.TextDisplay('# Мафия\n-# HAKUMO'),
        _ui.Separator(spacing=SeparatorSpacing.large),
    ]
    if SHOW_MENU_BANNER and banner_filename:
        head.append(_gallery(banner_filename))
    head.append(_ui.TextDisplay(body[:3900]))
    items = [black_container(*head, accent=accent)]
    if action_row is not None:
        items.append(black_container(
            _ui.TextDisplay('**Участникам**\n-# запись в состав'),
            action_row,
            accent=accent,
        ))
    return items


def build_mafia_menu_items(*, body: str, select_row, banner_filename: str = None,
                           accent: int = _BLACK):
    if not V2_AVAILABLE:
        return None
    head = [
        _ui.TextDisplay('# Мафия\n-# HAKUMO · ведущий'),
        _ui.Separator(spacing=SeparatorSpacing.large),
    ]
    if SHOW_MENU_BANNER and banner_filename:
        head.append(_gallery(banner_filename))
    head.append(_ui.TextDisplay(body[:3900]))
    items = [black_container(*head, accent=accent)]
    items.append(black_container(
        _ui.TextDisplay('**Действие**'),
        select_row,
        accent=accent,
    ))
    return items


def build_mafia_host_tools_items(*, body: str, action_row, banner_filename: str = None,
                                 accent: int = _BLACK):
    if not V2_AVAILABLE:
        return None
    head = [
        _ui.TextDisplay('# Ведущий\n-# только вам'),
        _ui.Separator(spacing=SeparatorSpacing.large),
    ]
    if SHOW_MENU_BANNER and banner_filename:
        head.append(_gallery(banner_filename))
    head.append(_ui.TextDisplay(body[:3900]))
    return [
        black_container(*head, accent=accent),
        black_container(
            _ui.TextDisplay('**Управление**'),
            action_row,
            accent=accent,
        ),
    ]


def build_mafia_status_items(*, title: str, body: str, accent: int = _GOLD):
    if not V2_AVAILABLE:
        return None
    return [black_container(
        _ui.TextDisplay(f'# {title}\n-# HAKUMO'),
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
