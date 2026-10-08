# -*- coding: utf-8 -*-
"""Живая сводка варнов в Discord-канале warn.

Два постоянных сообщения (участники / стафф) — бот редактирует их,
а не создаёт новые. ID сообщений в GuildData(namespace=settings).
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import discord

from logger import get_logger

_log = get_logger('warn_board')

_NS = 'settings'
_KEY_MEMBER_MSG = 'warn_board_member_msg_id'
_KEY_STAFF_MSG = 'warn_board_staff_msg_id'
_KEY_CHANNEL = 'warn_board_channel_id'
_KEY_MEMBER_PAGE = 'warn_board_member_page'
_KEY_STAFF_PAGE = 'warn_board_staff_page'

ROWS_PER_PAGE = 12
_UPDATE_LOCK = asyncio.Lock()
_last_update: float = 0.0


def board_channel_id() -> int:
    """WARN_BOARD_CHANNEL_ID из .env / Config, иначе 0."""
    raw = (os.getenv('WARN_BOARD_CHANNEL_ID') or '').strip()
    if raw:
        try:
            return int(raw)
        except (TypeError, ValueError):
            _log.warning('WARN_BOARD_CHANNEL_ID=%r не число', raw)
    try:
        from config import Config
        return int(getattr(Config, 'WARN_BOARD_CHANNEL_ID', 0) or 0)
    except Exception:
        return 0


def panel_warns_url() -> str:
    base = (
        (os.getenv('PANEL_PUBLIC_URL') or '').strip()
        or (os.getenv('PANEL_URL') or '').strip()
        or 'https://hakumods.xyz'
    ).rstrip('/')
    return f'{base}/warns'


def _gd():
    from db import GuildData
    return GuildData(_NS)


def _get_msg_id(guild_id: int, key: str) -> Optional[int]:
    try:
        v = _gd().get(int(guild_id), key)
        if v is None:
            return None
        return int(v)
    except Exception:
        return None


def _set_msg_id(guild_id: int, key: str, mid: int) -> None:
    try:
        _gd().set(int(guild_id), key, int(mid))
    except Exception as ex:
        _log.debug('set msg id: %s', ex)


def _get_page(guild_id: int, kind: str) -> int:
    key = _KEY_MEMBER_PAGE if kind == 'member' else _KEY_STAFF_PAGE
    try:
        return max(0, int(_gd().get(int(guild_id), key, 0) or 0))
    except Exception:
        return 0


def _set_page(guild_id: int, kind: str, page: int) -> None:
    key = _KEY_MEMBER_PAGE if kind == 'member' else _KEY_STAFF_PAGE
    try:
        _gd().set(int(guild_id), key, max(0, int(page)))
    except Exception:
        pass


async def resolve_channel(guild) -> Optional[discord.TextChannel]:
    """Найти/создать канал warn. ID сохраняется в settings."""
    if guild is None:
        return None
    cid = board_channel_id()
    if not cid:
        try:
            saved = _gd().get(int(guild.id), _KEY_CHANNEL)
            if saved:
                cid = int(saved)
        except Exception:
            cid = 0

    ch = None
    if cid:
        ch = guild.get_channel(int(cid))
        if ch is None:
            try:
                ch = await guild.fetch_channel(int(cid))
            except Exception:
                ch = None

    if ch is None:
        # поиск по имени
        for c in getattr(guild, 'text_channels', []) or []:
            n = (getattr(c, 'name', '') or '').lower()
            if n in ('warn', 'варн') or n.endswith('-warn') or n.endswith('・warn'):
                ch = c
                break

    if ch is None:
        # создать под Staff log
        parent = None
        for c in getattr(guild, 'categories', []) or []:
            n = (getattr(c, 'name', '') or '')
            if 'Staff log' in n or 'staff log' in n.lower():
                parent = c
                break
        try:
            ch = await guild.create_text_channel(
                'warn',
                category=parent,
                topic='Сводка активных варнов · бот редактирует сообщения',
                reason='Warn board channel',
            )
            _log.info('warn_board: создан канал #%s (%s)', ch.name, ch.id)
        except Exception as ex:
            _log.warning('warn_board: не удалось создать канал: %s', ex)
            return None

    try:
        _gd().set(int(guild.id), _KEY_CHANNEL, int(ch.id))
    except Exception:
        pass
    return ch if isinstance(ch, discord.abc.Messageable) else None


def _fmt_date(ts: str | None) -> str:
    if not ts:
        return '—'
    s = str(ts)
    if 'T' in s:
        return s.replace('T', ' ')[:16]
    return s[:16]


def _short(text: str, n: int = 40) -> str:
    t = (text or '—').replace('\n', ' ').strip()
    return t if len(t) <= n else t[: n - 1] + '…'


def _name_of(guild, uid: int, book: dict | None = None) -> str:
    m = guild.get_member(int(uid)) if guild else None
    if m is not None:
        return getattr(m, 'display_name', None) or str(uid)
    if book:
        return str(book.get(str(uid)) or book.get(uid) or uid)
    return str(uid)


def build_member_embeds(
    guild, rows: List[Dict[str, Any]], *, page: int = 0,
) -> Tuple[List[discord.Embed], int, int]:
    """Embed(ы) сводки участников. Возвращает embeds, page, total_pages."""
    total_pages = max(1, (len(rows) + ROWS_PER_PAGE - 1) // ROWS_PER_PAGE)
    page = max(0, min(int(page), total_pages - 1))
    chunk = rows[page * ROWS_PER_PAGE:(page + 1) * ROWS_PER_PAGE]

    lines = []
    for r in chunk:
        uid = int(r.get('user_id') or 0)
        name = _short(_name_of(guild, uid), 18)
        cnt = int(r.get('active_count') or 0)
        reason = _short(r.get('reason') or '—', 36)
        mid = int(r.get('moderator_id') or 0)
        mod = f'<@{mid}>' if mid else '—'
        when = _fmt_date(r.get('created_at'))
        lines.append(
            f'`{cnt}` **{name}** `{uid}`\n'
            f'└ {reason} · {mod} · {when}')

    e = discord.Embed(
        title='⚠ Варны · Участники',
        description='\n'.join(lines) if lines else '_Активных варнов нет._',
        color=0xF1C40F,
        timestamp=datetime.now(timezone.utc),
    )
    e.set_footer(
        text=f'Стр. {page + 1}/{total_pages} · активных людей: {len(rows)}')
    return [e], page, total_pages


def build_staff_embeds(
    guild, rows: List[Dict[str, Any]], *, page: int = 0,
) -> Tuple[List[discord.Embed], int, int]:
    from services.warn_config import branch_labels
    labels = branch_labels()
    total_pages = max(1, (len(rows) + ROWS_PER_PAGE - 1) // ROWS_PER_PAGE)
    page = max(0, min(int(page), total_pages - 1))
    chunk = rows[page * ROWS_PER_PAGE:(page + 1) * ROWS_PER_PAGE]

    lines = []
    for r in chunk:
        uid = int(r.get('user_id') or 0)
        name = _short(_name_of(guild, uid), 16)
        cnt = int(r.get('active_count') or 0)
        br = labels.get(r.get('branch') or '', r.get('branch') or '—')
        reason = _short(r.get('reason') or '—', 32)
        mid = int(r.get('moderator_id') or 0)
        mod = f'<@{mid}>' if mid else '—'
        when = _fmt_date(r.get('created_at'))
        lines.append(
            f'`{cnt}` **{name}** · {br}\n'
            f'└ {reason} · {mod} · {when}')

    e = discord.Embed(
        title='🛡 Варны · Стафф',
        description='\n'.join(lines) if lines else '_Активных варнов стаффа нет._',
        color=0x8B0000,
        timestamp=datetime.now(timezone.utc),
    )
    e.set_footer(
        text=f'Стр. {page + 1}/{total_pages} · стаффа с варнами: {len(rows)}'
             f' · роль warn не выдаётся')
    return [e], page, total_pages


class WarnBoardView(discord.ui.View):
    """Пагинация + ссылка на панель. custom_id persistent."""

    def __init__(self, guild_id: int, kind: str, page: int = 0,
                 total_pages: int = 1):
        super().__init__(timeout=None)
        self.guild_id = int(guild_id)
        self.kind = 'staff' if kind == 'staff' else 'member'
        self.page = max(0, int(page))
        self.total_pages = max(1, int(total_pages))
        self._rebuild()

    def _rebuild(self):
        self.clear_items()
        prev = discord.ui.Button(
            label='◀ Назад', style=discord.ButtonStyle.secondary,
            custom_id=f'warnboard:{self.guild_id}:{self.kind}:'
                      f'{self.page - 1}',
            disabled=self.page <= 0)
        nxt = discord.ui.Button(
            label='Вперёд ▶', style=discord.ButtonStyle.secondary,
            custom_id=f'warnboard:{self.guild_id}:{self.kind}:'
                      f'{self.page + 1}',
            disabled=self.page >= self.total_pages - 1)
        self.add_item(prev)
        self.add_item(nxt)
        url = panel_warns_url()
        if url.startswith('http'):
            self.add_item(discord.ui.Button(
                label='Открыть панель варнов',
                style=discord.ButtonStyle.link, url=url))


async def _ensure_message(
    channel: discord.TextChannel,
    guild_id: int,
    key: str,
    embeds: List[discord.Embed],
    view: discord.ui.View,
) -> Optional[discord.Message]:
    mid = _get_msg_id(guild_id, key)
    msg = None
    if mid:
        try:
            msg = await channel.fetch_message(int(mid))
        except discord.NotFound:
            msg = None
        except Exception as ex:
            _log.debug('fetch board msg: %s', ex)
            msg = None
    if msg is not None:
        try:
            await msg.edit(embeds=embeds, view=view, content=None)
            return msg
        except Exception as ex:
            _log.warning('edit board msg: %s', ex)
    try:
        msg = await channel.send(embeds=embeds, view=view)
        _set_msg_id(guild_id, key, int(msg.id))
        return msg
    except Exception as ex:
        _log.warning('send board msg: %s', ex)
        return None


async def update_warn_board(
    guild, *, force: bool = False, member_page: int | None = None,
    staff_page: int | None = None,
) -> bool:
    """Обновить оба сообщения-сводки. Вызывать после issue/remove."""
    global _last_update
    if guild is None:
        return False
    async with _UPDATE_LOCK:
        import time
        now = time.monotonic()
        if not force and (now - _last_update) < 2.0:
            # антиспам при пачке действий
            await asyncio.sleep(0.05)
        try:
            from services import warn_store as WS
            member_rows = WS.list_board_rows(guild.id, reason_type='member')
            staff_rows = WS.list_board_rows(guild.id, reason_type='staff')
        except Exception as ex:
            _log.warning('board load rows: %s', ex)
            return False

        ch = await resolve_channel(guild)
        if ch is None:
            return False

        mp = (member_page if member_page is not None
              else _get_page(guild.id, 'member'))
        sp = (staff_page if staff_page is not None
              else _get_page(guild.id, 'staff'))

        m_embeds, mp, m_pages = build_member_embeds(
            guild, member_rows, page=mp)
        s_embeds, sp, s_pages = build_staff_embeds(
            guild, staff_rows, page=sp)
        _set_page(guild.id, 'member', mp)
        _set_page(guild.id, 'staff', sp)

        m_view = WarnBoardView(guild.id, 'member', mp, m_pages)
        s_view = WarnBoardView(guild.id, 'staff', sp, s_pages)

        ok1 = await _ensure_message(
            ch, guild.id, _KEY_MEMBER_MSG, m_embeds, m_view)
        ok2 = await _ensure_message(
            ch, guild.id, _KEY_STAFF_MSG, s_embeds, s_view)
        _last_update = time.monotonic()
        return bool(ok1 and ok2)


async def handle_board_button(interaction: discord.Interaction) -> bool:
    """warnboard:gid:kind:page"""
    data = getattr(interaction, 'data', None) or {}
    cid = str(data.get('custom_id') or '')
    if not cid.startswith('warnboard:'):
        return False
    parts = cid.split(':')
    if len(parts) < 4:
        return False
    try:
        gid = int(parts[1])
        kind = parts[2]
        page = int(parts[3])
    except (TypeError, ValueError):
        return False
    guild = interaction.guild
    if guild is None or int(guild.id) != gid:
        try:
            await interaction.response.send_message(
                'Не та гильдия.', ephemeral=True)
        except Exception:
            pass
        return True
    try:
        await interaction.response.defer()
    except Exception:
        pass
    if kind == 'staff':
        await update_warn_board(guild, force=True, staff_page=page)
    else:
        await update_warn_board(guild, force=True, member_page=page)
    return True


async def schedule_board_refresh(guild) -> None:
    """Неблокирующий вызов из warn_actions (create_task)."""
    try:
        await update_warn_board(guild, force=True)
    except Exception as ex:
        _log.debug('schedule_board_refresh: %s', ex)
