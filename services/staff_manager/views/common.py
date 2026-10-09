# -*- coding: utf-8 -*-
"""Общие примитивы стиля (цвета/чёрный контейнер/кнопки-зеркало).

НЕ билдер экранов — каждый экран собирает LayoutView сам.
"""
from __future__ import annotations

import discord

from services.staff_manager.styles import MIRROR_BLACK, BLACK
from services.staff_manager.emojis import emoji_str, partial_emoji
from services.staff_manager.config import role_emoji, branch_emoji
from services.staff_manager.bundles import format_actor_label, format_role_label


def mirror_container(*children, accent: int = MIRROR_BLACK):
    """Чёрный «зеркальный» контейнер — не классический зелёный confirm."""
    return discord.ui.Container(
        *children, accent_colour=discord.Colour(int(accent or BLACK)))


def black_container(*children, accent: int = BLACK):
    return discord.ui.Container(
        *children, accent_colour=discord.Colour(int(accent or BLACK)))


def mirror_confirm_row(
    *,
    ok_id: str,
    cancel_id: str,
    ok_label: str = 'Подтвердить',
    cancel_label: str = 'Отмена',
    ok_callback=None,
    cancel_callback=None,
) -> discord.ui.ActionRow:
    """Кнопки подтверждения: secondary (тёмные), без невалидных эмодзи."""
    row = discord.ui.ActionRow()
    # без emoji: Discord отклоняет ✦/✧ (не emoji) → 50035 Invalid Form Body
    btn_ok = discord.ui.Button(
        label=ok_label,
        style=discord.ButtonStyle.secondary,
        custom_id=ok_id,
    )
    btn_no = discord.ui.Button(
        label=cancel_label,
        style=discord.ButtonStyle.secondary,
        custom_id=cancel_id,
    )
    if ok_callback:
        btn_ok.callback = ok_callback  # type: ignore
    if cancel_callback:
        btn_no.callback = cancel_callback  # type: ignore
    row.add_item(btn_ok)
    row.add_item(btn_no)
    return row


def role_em(key: str, branch: str | None = None) -> str:
    return emoji_str('role', key or '', role_emoji(key or '', branch=branch) or '•')


def branch_em(key: str) -> str:
    return emoji_str('branch', key or '', branch_emoji(key or '') or '•')


def opt_emoji(kind: str, key: str, fallback=None):
    return partial_emoji(kind, key, fallback)


def actor_line(name: str, role_key: str | None = None,
               branch: str | None = None,
               snap_key: str | None = None) -> str:
    return format_actor_label(
        name, snap_key or role_key, branch=branch)


def avatar_url(member) -> str:
    try:
        return str(member.display_avatar.url)
    except Exception:
        return ''
