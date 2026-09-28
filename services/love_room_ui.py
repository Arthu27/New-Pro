# -*- coding: utf-8 -*-
"""Components V2-раскладки для Love Room (как /modpanel + mafia)."""
from __future__ import annotations

import discord

from logger import get_logger

_log = get_logger('love_room_ui')

try:
    from services.v2_layouts import (
        V2_AVAILABLE, SHOW_MENU_BANNER, black_container, _gallery,
    )
    from discord import ui as _ui
    from discord import SeparatorSpacing
except Exception as _ex:  # pragma: no cover
    V2_AVAILABLE = False
    SHOW_MENU_BANNER = False
    _log.debug('love_room_ui import: %s', _ex)

_BLACK = 0x000000
_PINK = 0xFF6B9A
_BANNER_KIND = 'loveroom'


def love_banner_file():
    try:
        if not SHOW_MENU_BANNER:
            return None, None
        from services.menu_banners import menu_banner_file
        import io
        bio, name = menu_banner_file(_BANNER_KIND)
        raw = bio.getvalue() if hasattr(bio, 'getvalue') else bio.read()
        out = io.BytesIO(raw)
        out.seek(0)
        return discord.File(out, filename=name), name
    except Exception as ex:
        _log.debug('love banner: %s', ex)
        try:
            from services.menu_banners import menu_banner_file
            import io
            bio, name = menu_banner_file('events')
            raw = bio.getvalue() if hasattr(bio, 'getvalue') else bio.read()
            out = io.BytesIO(raw)
            out.seek(0)
            return discord.File(out, filename=name), name
        except Exception:
            return None, None


def sticker(kind: str):
    """Application emoji for love_* keys or unicode fallback."""
    try:
        from services.menu_emojis import get_cached, emoji_for_love
        em = get_cached(kind) or emoji_for_love(kind)
        return em
    except Exception:
        return {
            'love_enter': '🚪',
            'love_pair': '💞',
            'love_room': '🏠',
            'love_raise': '⬆️',
            'love_lower': '⬇️',
            'love_close': '✖️',
            'love_heart': '🤍',
            'enter': '🚪',
            'pair': '💞',
            'room': '🏠',
            'raise': '⬆️',
            'lower': '⬇️',
            'close': '✖️',
            'heart': '🤍',
        }.get(kind, '🤍')


def build_love_panel_items(*, body: str, banner_filename: str = None,
                           action_row=None, pair_row=None,
                           stage_row=None, accent: int = _BLACK):
    if not V2_AVAILABLE:
        return None
    head = [
        _ui.TextDisplay('# Love Room\n-# HAKUMO · войти в love room'),
        _ui.Separator(spacing=SeparatorSpacing.large),
    ]
    if SHOW_MENU_BANNER and banner_filename:
        head.append(_gallery(banner_filename))
    head.append(_ui.TextDisplay(body[:3900]))
    items = [black_container(*head, accent=accent)]
    if pair_row is not None:
        items.append(black_container(
            _ui.TextDisplay('**Пара**\n-# выбери партнёра или себя + второго'),
            pair_row,
            accent=accent,
        ))
    if action_row is not None:
        items.append(black_container(
            _ui.TextDisplay('**Действия**\n-# создать · закрыть'),
            action_row,
            accent=accent,
        ))
    if stage_row is not None:
        items.append(black_container(
            _ui.TextDisplay('**Трибуна**\n-# поднять / опустить (Stage suppress)'),
            stage_row,
            accent=accent,
        ))
    return items


def build_love_status_items(*, title: str, body: str, accent: int = _PINK):
    if not V2_AVAILABLE:
        return None
    return [black_container(
        _ui.TextDisplay(f'# {title}\n-# HAKUMO · LOVE ROOM'),
        _ui.Separator(spacing=SeparatorSpacing.large),
        _ui.TextDisplay(body[:3900]),
        accent=accent,
    )]


def panel_embed(*, body: str, room_count: int = 0) -> discord.Embed:
    e = discord.Embed(
        title='Love Room',
        description=body[:4000],
        color=_BLACK,
    )
    e.add_field(name='Активных комнат', value=str(room_count), inline=True)
    e.set_footer(text='Hakumo · войти в love room · V2')
    return e


def panel_body_md(*, room_count: int = 0, category_ok: bool = False) -> str:
    cat = 'категория задана' if category_ok else 'категория ещё не настроена (ID=0)'
    return (
        f'**Назначение:** войти в love room — временный войс на двоих.\n'
        f'**Активных комнат:** {room_count}\n'
        f'**Категория:** {cat}\n\n'
        '① Выбери пару (User Select)\n'
        '② «Создать love room» — перенос пары, лимит 2\n'
        '③ Оба вышли — комната удалится сама\n\n'
        '-# Ведущий · Stage: Поднять / Опустить = suppress'
    )
