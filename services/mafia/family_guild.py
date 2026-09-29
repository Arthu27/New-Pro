# -*- coding: utf-8 -*-
"""Сервер семьи мафии: одноразовый инвайт каждому, выгон после матча.

Только текущая мафия может быть на сервере — чужих кикаем сразу.
Event-бот: Create Instant Invite + Kick + Ban; желательно Members Intent.
"""
from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple

import discord

from logger import get_logger

if TYPE_CHECKING:
    from services.mafia.game import Game

log = get_logger('mafia.family')

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
        # fetch_guild — урезанный объект; для инвайтов хватает
        return await bot.fetch_guild(gid)
    except Exception as ex:
        log.warning('mafia family guild %s: %s', gid, ex)
        return None


def allowed_mafia_ids(bot) -> Set[int]:
    """Все uid семьи из активных партий (на сервере семьи только они)."""
    out: Set[int] = set()
    try:
        from services.mafia import STORE, PHASE_ENDED
        for g in list(STORE._by_guild.values()):
            if g.phase == PHASE_ENDED:
                continue
            ids = list(getattr(g, 'mafia_family_ids', None) or [])
            if not ids:
                try:
                    ids = [p.user_id for p in g.mafia_team()]
                except Exception:
                    ids = []
            for uid in ids:
                out.add(int(uid))
    except Exception as ex:
        log.debug('allowed_mafia_ids: %s', ex)
    return out


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
    if me is None:
        try:
            me = await guild.fetch_member(guild.me.id if guild.me else 0)  # type: ignore
        except Exception:
            me = None

    candidates: list = []
    try:
        candidates.extend(list(getattr(guild, 'text_channels', None) or []))
    except Exception:
        pass
    try:
        candidates.extend(list(getattr(guild, 'voice_channels', None) or []))
    except Exception:
        pass
    # fetch_guild иногда без channels — подтянуть
    if not candidates:
        try:
            channels = await guild.fetch_channels()
            candidates = [
                c for c in channels
                if isinstance(c, (discord.TextChannel, discord.VoiceChannel,
                                  discord.StageChannel))
            ]
        except Exception as ex:
            log.debug('family fetch_channels: %s', ex)

    for ch in candidates:
        try:
            if me is not None:
                perms = ch.permissions_for(me)
                if not getattr(perms, 'create_instant_invite', True):
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
        bot, user_id: int, *, game_id: str,
        guild: Optional[discord.Guild] = None,
        channel: Optional[discord.abc.GuildChannel] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """Инвайт max_uses=1, unique. Ретраи при rate-limit."""
    if guild is None:
        guild = await resolve_family_guild(bot)
    if guild is None:
        return None, None
    await unban_user(guild, user_id)
    ch = channel or await _invite_channel(guild)
    if ch is None:
        log.warning('mafia family: нет канала для инвайта на %s', guild.id)
        return None, None
    last_err = None
    for attempt in range(4):
        try:
            inv = await ch.create_invite(
                max_age=6 * 3600,
                max_uses=1,
                unique=True,
                reason=f'мафия семья · #{game_id} · {user_id}',
            )
            return str(inv.url), str(inv.code)
        except discord.HTTPException as ex:
            last_err = ex
            # 429 / temporary
            wait = min(2.0 * (attempt + 1), 6.0)
            log.warning(
                'mafia family invite %s attempt %s: %s — sleep %.1fs',
                user_id, attempt + 1, ex, wait,
            )
            await asyncio.sleep(wait)
        except Exception as ex:
            last_err = ex
            log.warning('mafia family invite %s: %s', user_id, ex)
            await asyncio.sleep(1.0)
    log.warning('mafia family invite FAIL %s: %s', user_id, last_err)
    return None, None


async def create_invites_for_team(
        bot, game: 'Game') -> Dict[int, Tuple[str, str]]:
    """Сделать отдельный одноразовый инвайт КАЖДОМУ из семьи."""
    team = list(game.mafia_team())
    game.mafia_family_ids = [int(t.user_id) for t in team]
    game.mafia_invite_codes = []
    out: Dict[int, Tuple[str, str]] = {}
    if not team:
        return out

    guild = await resolve_family_guild(bot)
    if guild is None:
        log.warning('mafia family: сервер %s недоступен боту', family_guild_id())
        return out
    ch = await _invite_channel(guild)
    if ch is None:
        log.warning('mafia family: нет канала инвайта')
        return out

    # старые инвайты бота на сервере — снести, чтобы чужие не зашли
    try:
        for inv in await guild.invites():
            try:
                await inv.delete(reason='мафия: новая раздача')
            except Exception:
                pass
    except Exception as ex:
        log.debug('family revoke-all before deal: %s', ex)

    for i, p in enumerate(team):
        if i:
            await asyncio.sleep(1.2)  # не упереться в rate-limit
        url, code = await create_one_shot_invite(
            bot, p.user_id, game_id=game.game_id, guild=guild, channel=ch)
        if url and code:
            out[int(p.user_id)] = (url, code)
            game.mafia_invite_codes.append(code)
            log.info('mafia family invite OK uid=%s code=%s', p.user_id, code)
        else:
            log.warning('mafia family invite MISSING uid=%s', p.user_id)
    return out


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


async def kick_if_not_mafia(bot, member: discord.Member) -> bool:
    """Чужой зашёл на сервер семьи → кик (+ бан, чтобы не вернулся)."""
    if member is None or member.bot:
        return False
    if int(member.guild.id) != family_guild_id():
        return False
    me = member.guild.me
    if me is not None and int(member.id) == int(me.id):
        return False
    # не трогаем тех, у кого роль выше бота / админы сервера семьи
    try:
        if member.guild_permissions.administrator:
            return False
    except Exception:
        pass
    allowed = allowed_mafia_ids(bot)
    if int(member.id) in allowed:
        return False
    reason = 'мафия: сервер только для текущей семьи'
    try:
        await member.ban(reason=reason, delete_message_seconds=0)
        log.info('mafia family: выгнан чужой %s (ban)', member.id)
        return True
    except Exception:
        try:
            await member.kick(reason=reason)
            log.info('mafia family: выгнан чужой %s (kick)', member.id)
            return True
        except Exception as ex:
            log.warning('mafia family kick stranger %s: %s', member.id, ex)
            return False


async def _list_family_member_ids(bot, guild: discord.Guild) -> List[int]:
    """Список uid на сервере семьи (HTTP — без Members Intent)."""
    ids: List[int] = []
    # кэш (если intent включён)
    for m in list(getattr(guild, 'members', None) or []):
        if m and not m.bot:
            ids.append(int(m.id))
    if ids:
        return ids
    # REST fallback
    try:
        after = 0
        while True:
            raw = await bot.http.get_members(guild.id, limit=100, after=after)
            if not raw:
                break
            for row in raw:
                try:
                    uid = int(row['user']['id'])
                    if not row['user'].get('bot'):
                        ids.append(uid)
                    after = max(after, uid)
                except Exception:
                    continue
            if len(raw) < 100:
                break
            await asyncio.sleep(0.3)
    except Exception as ex:
        log.debug('family list members http: %s', ex)
    return ids


async def purge_strangers(bot) -> int:
    """Пройти сервер семьи и выгнать всех не из текущей семьи."""
    guild = bot.get_guild(family_guild_id())
    if guild is None:
        try:
            guild = await bot.fetch_guild(family_guild_id())
        except Exception:
            return 0
    if guild is None:
        return 0
    allowed = allowed_mafia_ids(bot)
    # если нет активной семьи — никого не трогаем (не банить весь сервер)
    if not allowed:
        return 0
    me_id = int(bot.user.id) if bot.user else 0
    n = 0
    for uid in await _list_family_member_ids(bot, guild):
        if uid == me_id or uid in allowed:
            continue
        try:
            member = guild.get_member(uid)
            if member is None:
                try:
                    member = await guild.fetch_member(uid)
                except Exception:
                    member = None
            if member is None:
                try:
                    await guild.ban(
                        discord.Object(id=uid),
                        reason='мафия: не из текущей семьи',
                        delete_message_seconds=0,
                    )
                    n += 1
                except Exception:
                    pass
                continue
            if await kick_if_not_mafia(bot, member):
                n += 1
            await asyncio.sleep(0.4)
        except Exception as ex:
            log.debug('purge stranger %s: %s', uid, ex)
    return n


async def evict_family(bot, game: 'Game') -> int:
    """После матча: отозвать инвайты, выгнать/забанить семью."""
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
    # все инвайты на сервере — тоже
    try:
        for inv in await guild.invites():
            try:
                await inv.delete(reason=f'мафия #{game.game_id}: конец')
            except Exception:
                pass
    except Exception:
        pass
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
        await asyncio.sleep(0.35)
    if hasattr(game, 'mafia_invite_codes'):
        game.mafia_invite_codes = []
    log.info('mafia family: выгнано/забанено %s · #%s', n, game.game_id)
    return n
