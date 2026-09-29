# -*- coding: utf-8 -*-
"""Сервер семьи мафии: одноразовый инвайт на партию, выгон после матча.

Event-бот должен быть на этом сервере с правами:
Create Instant Invite, Kick Members, Ban Members.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING, List, Optional, Tuple

import discord

from logger import get_logger

if TYPE_CHECKING:
    from services.mafia.game import Game

log = get_logger('mafia.family')

# Сервер, куда мафия заходит общаться ночью (одноразово на партию).
DEFAULT_FAMILY_GUILD_ID = 1554581698946277538


def family_guild_id() -> int:
    raw = (os.environ.get('MAFIA_FAMILY_GUILD_ID') or '').strip()
    if raw.isdigit():
        return int(raw)
    return DEFAULT_FAMILY_GUILD_ID


def family_invite_channel_id() -> Optional[int]:
    raw = (os.environ.get('MAFIA_FAMILY_CHANNEL_ID') or '').strip()
    return int(raw) if raw.isdigit() else None


async def resolve_family_guild(bot) -> Optional[discord.Guild]:
    gid = family_guild_id()
    guild = bot.get_guild(gid)
    if guild is not None:
        return guild
    try:
        return await bot.fetch_guild(gid)
    except Exception as ex:
        log.warning('mafia family guild %s: %s', gid, ex)
        return None


async def _invite_channel(guild: discord.Guild) -> Optional[discord.abc.GuildChannel]:
    prefer = family_invite_channel_id()
    if prefer:
        ch = guild.get_channel(prefer)
        if ch is None:
            try:
                ch = await guild.fetch_channel(prefer)
            except Exception:
                ch = None
        if ch is not None:
            return ch  # type: ignore
    me = guild.me
    # текстовый / голосовой с правом Create Instant Invite
    candidates = list(getattr(guild, 'text_channels', None) or [])
    candidates += list(getattr(guild, 'voice_channels', None) or [])
    for ch in candidates:
        try:
            if me is not None:
                perms = ch.permissions_for(me)
                if not getattr(perms, 'create_instant_invite', False):
                    continue
            return ch
        except Exception:
            continue
    return guild.system_channel or (candidates[0] if candidates else None)


async def unban_user(guild: discord.Guild, user_id: int) -> None:
    try:
        await guild.unban(
            discord.Object(id=int(user_id)),
            reason='мафия: новая партия · вход для семьи',
        )
    except discord.NotFound:
        pass
    except Exception as ex:
        log.debug('family unban %s: %s', user_id, ex)


async def create_one_shot_invite(
        bot, user_id: int, *, game_id: str) -> Tuple[Optional[str], Optional[str]]:
    """Вернуть (url, code) — инвайт max_uses=1, unique. Перед этим снимает бан."""
    guild = await resolve_family_guild(bot)
    if guild is None:
        return None, None
    await unban_user(guild, user_id)
    ch = await _invite_channel(guild)
    if ch is None:
        log.warning('mafia family: нет канала для инвайта на %s', guild.id)
        return None, None
    try:
        inv = await ch.create_invite(
            max_age=6 * 3600,
            max_uses=1,
            unique=True,
            reason=f'мафия семья · партия #{game_id} · uid {user_id}',
        )
        return str(inv.url), str(inv.code)
    except Exception as ex:
        log.warning('mafia family invite %s: %s', user_id, ex)
        return None, None


async def revoke_invites(bot, codes: List[str]) -> int:
    guild = await resolve_family_guild(bot)
    if guild is None or not codes:
        return 0
    n = 0
    want = {str(c) for c in codes if c}
    try:
        invites = await guild.invites()
    except Exception as ex:
        log.debug('family invites list: %s', ex)
        return 0
    for inv in invites:
        if str(getattr(inv, 'code', '')) not in want:
            continue
        try:
            await inv.delete(reason='мафия: партия окончена')
            n += 1
        except Exception:
            pass
    return n


async def evict_family(bot, game: 'Game') -> int:
    """Выгнать семью с сервера и забанить, чтобы не зашли обратно по чужому инвайту."""
    guild = await resolve_family_guild(bot)
    if guild is None:
        return 0
    ids = list(getattr(game, 'mafia_family_ids', None) or [])
    if not ids:
        try:
            ids = [p.user_id for p in game.mafia_team()]
        except Exception:
            ids = []
    codes = list(getattr(game, 'mafia_invite_codes', None) or [])
    if codes:
        await revoke_invites(bot, codes)
    n = 0
    reason = f'мафия #{game.game_id}: матч окончен'
    for uid in ids:
        uid = int(uid)
        try:
            member = guild.get_member(uid)
            if member is None:
                try:
                    member = await guild.fetch_member(uid)
                except discord.NotFound:
                    member = None
            if member is not None:
                try:
                    await member.ban(reason=reason, delete_message_seconds=0)
                    n += 1
                    continue
                except Exception:
                    try:
                        await member.kick(reason=reason)
                        n += 1
                    except Exception as ex:
                        log.debug('family kick %s: %s', uid, ex)
            else:
                # уже вышел — всё равно бан, чтобы не зашёл снова
                try:
                    await guild.ban(
                        discord.Object(id=uid),
                        reason=reason,
                        delete_message_seconds=0,
                    )
                    n += 1
                except Exception:
                    pass
        except Exception as ex:
            log.debug('family evict %s: %s', uid, ex)
    if hasattr(game, 'mafia_invite_codes'):
        game.mafia_invite_codes = []
    log.info('mafia family: выгнано/забанено %s · #%s', n, game.game_id)
    return n
