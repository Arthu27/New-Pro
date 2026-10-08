# -*- coding: utf-8 -*-
"""Автоистечение варнов через БД + DM + sync роли + board."""
from __future__ import annotations

from typing import List

from logger import get_logger

_log = get_logger('warn_expire')


async def process_expired_warns(bot, guild_id: int | None = None) -> int:
    """Найти просроченные, пометить, sync роли, DM, board.

    Возвращает число истёкших записей.
    """
    from services import warn_store as WS
    from services.warn_role import sync_warn_role
    from services.warn_dm import (
        build_member_expire_dm, build_staff_expire_dm, send_warn_dm)
    from services.warn_acl import get_staff_info

    expired = WS.expire_due_warns(guild_id)
    if not expired:
        return 0

    # группируем по (guild, user)
    by_user: dict[tuple, list] = {}
    for w in expired:
        key = (int(w['guild_id']), int(w['user_id']))
        by_user.setdefault(key, []).append(w)

    touched_guilds = set()
    for (gid, uid), rows in by_user.items():
        touched_guilds.add(gid)
        guild = None
        member = None
        try:
            if bot is not None:
                guild = bot.get_guild(gid)
                if guild is not None:
                    member = guild.get_member(uid)
        except Exception:
            pass

        if member is not None:
            try:
                await sync_warn_role(member)
            except Exception as ex:
                _log.debug('expire sync_warn_role %s: %s', uid, ex)

            is_staff, branch, _rank = get_staff_info(member)
            active_left = WS.count_active(gid, uid)
            last = rows[-1]
            try:
                if is_staff:
                    emb = build_staff_expire_dm(
                        guild, reason=last.get('reason') or '',
                        warn_id=int(last['id']),
                        active_count=active_left, branch=branch)
                else:
                    emb = build_member_expire_dm(
                        guild, reason=last.get('reason') or '',
                        warn_id=int(last['id']),
                        active_count=active_left)
                await send_warn_dm(
                    member, emb, guild=guild,
                    log_channel_hint=f'warn expire #{last["id"]}')
            except Exception as ex:
                _log.debug('expire DM %s: %s', uid, ex)

    for gid in touched_guilds:
        try:
            import asyncio
            from services.warn_board import schedule_board_refresh
            guild = bot.get_guild(gid) if bot else None
            if guild is not None:
                asyncio.create_task(schedule_board_refresh(guild))
        except Exception as ex:
            _log.debug('expire board: %s', ex)

    try:
        from services import panel_cache as PC
        PC.invalidate('warns')
    except Exception:
        pass

    return len(expired)
