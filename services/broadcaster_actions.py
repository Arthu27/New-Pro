# -*- coding: utf-8 -*-
"""Discord-действия трибуны: канал, событие, права, откат если событие не создалось."""
from __future__ import annotations

from datetime import timedelta
from typing import Optional

import discord

from logger import get_logger
from services.broadcaster_catalog import banner_png, tribune_by_key
from services.broadcaster_logic import channel_name, permission_plan
from services import broadcaster_store as store

log = get_logger('broadcaster.actions')


def _cfg_int(cfg: dict, key: str, default: int = 0) -> int:
    try:
        return int(cfg.get(key) or default)
    except Exception:
        return default


def gender_roles(guild: discord.Guild, cfg: dict) -> list:
    out = []
    for raw in cfg.get('gender_role_ids') or []:
        try:
            rid = int(raw)
        except Exception:
            continue
        role = guild.get_role(rid)
        if role is not None:
            out.append(role)
    return out


def build_overwrites(guild: discord.Guild, cfg: dict, *, opened: bool) -> dict:
    genders = gender_roles(guild, cfg)
    plan = permission_plan(opened=opened, has_gender=bool(genders))
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(**plan['everyone']),
    }
    host = guild.get_role(_cfg_int(cfg, 'broadcaster_role_id'))
    if host is not None:
        overwrites[host] = discord.PermissionOverwrite(**plan['broadcaster'])
    me = guild.me
    if me is not None:
        overwrites[me] = discord.PermissionOverwrite(**plan['bot'])
    if 'gender' in plan:
        for role in genders:
            overwrites[role] = discord.PermissionOverwrite(**plan['gender'])
    return overwrites


async def _category(
    guild: discord.Guild,
    *,
    configured_id: int,
    meta_key: str,
    name: str,
) -> Optional[discord.CategoryChannel]:
    cid = configured_id or int(store.meta_get(meta_key) or 0)
    if cid:
        found = guild.get_channel(cid)
        if isinstance(found, discord.CategoryChannel):
            return found
    for cat in list(getattr(guild, 'categories', []) or []):
        if (cat.name or '').strip().lower() == name.lower():
            store.meta_set(meta_key, str(cat.id))
            return cat
    created = await guild.create_category(name, reason='broadcaster')
    store.meta_set(meta_key, str(created.id))
    return created


async def tribune_category(guild: discord.Guild, cfg: dict):
    return await _category(
        guild,
        configured_id=_cfg_int(cfg, 'tribune_category_id'),
        meta_key=f'tribune_category:{guild.id}',
        name='Трибуны',
    )


async def love_category(guild: discord.Guild, cfg: dict):
    love = cfg.get('love') or {}
    try:
        configured = int(love.get('category_id') or 0)
    except Exception:
        configured = 0
    return await _category(
        guild,
        configured_id=configured,
        meta_key=f'love_category:{guild.id}',
        name='Лав румы',
    )


async def _create_channel(guild, *, name: str, category, overwrites):
    """Сначала сцена, если сервер не даёт — обычный голосовой."""
    try:
        return await guild.create_stage_channel(
            name=name,
            category=category,
            overwrites=overwrites,
            reason='broadcaster tribune',
        )
    except Exception as ex:
        log.info('stage channel unavailable, voice instead: %s', ex)
    return await guild.create_voice_channel(
        name=name,
        category=category,
        overwrites=overwrites,
        reason='broadcaster tribune',
    )


async def create_tribune(
    guild: discord.Guild,
    cfg: dict,
    *,
    owner_id: int,
    catalog_key: str,
    start,
) -> tuple[bool, str, Optional[dict]]:
    item = tribune_by_key(catalog_key)
    if not item:
        return False, 'Такой трибуны нет в базе', None
    title = item['title']
    name = channel_name(title)
    category = await tribune_category(guild, cfg)
    overwrites = build_overwrites(guild, cfg, opened=False)
    channel = await _create_channel(
        guild, name=name, category=category, overwrites=overwrites,
    )
    duration = max(30, _cfg_int(cfg, 'event_duration_minutes', 120))
    end = start + timedelta(minutes=duration)
    image = banner_png(item)
    kwargs = dict(
        name=title[:100],
        description=(item.get('blurb') or title)[:1000],
        start_time=start,
        channel=channel,
        privacy_level=discord.PrivacyLevel.guild_only,
        image=image,
        reason=f'broadcaster tribune by {owner_id}',
    )
    try:
        event = await guild.create_scheduled_event(**kwargs, end_time=end)
    except Exception as first:
        log.info('event with end_time failed (%s), retry without it', first)
        try:
            event = await guild.create_scheduled_event(**kwargs)
        except Exception as ex:
            log.warning('scheduled event failed, dropping channel: %s', ex)
            try:
                await channel.delete(reason='tribune event failed')
            except Exception as del_ex:
                log.warning('rollback channel delete: %s', del_ex)
            return False, f'Событие не создалось: {ex}', None
    row = store.insert_tribune(
        guild_id=guild.id,
        owner_id=owner_id,
        catalog_key=item['key'],
        title=title,
        starts_at=start.isoformat(),
        channel_id=int(channel.id),
        event_id=int(event.id),
    )
    link = getattr(event, 'url', '') or ''
    text = (
        f'Трибуна **{title}** записана на {start.strftime("%d.%m.%Y %H:%M")}.\n'
        f'Канал: {channel.mention}'
    )
    if link:
        text += f'\nСобытие: {link}'
    return True, text, row


async def delete_tribune(guild: discord.Guild, row: dict) -> tuple[bool, str]:
    event_id = int(row.get('event_id') or 0)
    channel_id = int(row.get('channel_id') or 0)
    if event_id:
        try:
            event = guild.get_scheduled_event(event_id)
            if event is None:
                event = await guild.fetch_scheduled_event(event_id)
            if event is not None:
                await event.delete()
        except discord.NotFound:
            pass
        except Exception as ex:
            return False, f'Событие не удалилось: {ex}'
    if channel_id:
        channel = guild.get_channel(channel_id)
        if channel is None:
            try:
                channel = await guild.fetch_channel(channel_id)
            except discord.NotFound:
                channel = None
            except Exception as ex:
                return False, f'Канал не найден: {ex}'
        if channel is not None:
            try:
                await channel.delete(reason='broadcaster delete tribune')
            except discord.NotFound:
                pass
            except Exception as ex:
                return False, f'Канал не удалился: {ex}'
    store.mark_deleted(row['id'])
    return True, f'Трибуна **{row.get("title") or "—"}** удалена.'


async def edit_tribune(
    guild: discord.Guild,
    cfg: dict,
    row: dict,
    *,
    catalog_key: str,
    start,
    change_time: bool,
) -> tuple[bool, str]:
    item = tribune_by_key(catalog_key)
    if not item:
        return False, 'Такой трибуны нет в базе'
    title = item['title']
    event_id = int(row.get('event_id') or 0)
    channel_id = int(row.get('channel_id') or 0)
    if event_id:
        try:
            event = guild.get_scheduled_event(event_id)
            if event is None:
                event = await guild.fetch_scheduled_event(event_id)
        except discord.NotFound:
            event = None
        except Exception as ex:
            return False, f'Событие не прочиталось: {ex}'
        if event is not None:
            kwargs = {
                'name': title[:100],
                'description': (item.get('blurb') or title)[:1000],
                'image': banner_png(item),
            }
            if change_time:
                duration = max(30, _cfg_int(cfg, 'event_duration_minutes', 120))
                kwargs['start_time'] = start
                kwargs['end_time'] = start + timedelta(minutes=duration)
            try:
                await event.edit(**kwargs)
            except Exception as ex:
                return False, f'Событие не изменилось: {ex}'
    if channel_id:
        channel = guild.get_channel(channel_id)
        if channel is not None and channel.name != channel_name(title):
            try:
                await channel.edit(name=channel_name(title), reason='broadcaster edit')
            except Exception as ex:
                return False, f'Канал не переименовался: {ex}'
    fields = {'catalog_key': item['key'], 'title': title}
    if change_time:
        fields['starts_at'] = start.isoformat()
    store.update_tribune(row['id'], **fields)
    when = start.strftime('%d.%m.%Y %H:%M') if change_time else 'время без изменений'
    return True, f'Трибуна теперь **{title}**. {when}.'


async def open_tribune(guild: discord.Guild, cfg: dict, row: dict) -> tuple[bool, str]:
    channel_id = int(row.get('channel_id') or 0)
    channel = guild.get_channel(channel_id) if channel_id else None
    if channel is None and channel_id:
        try:
            channel = await guild.fetch_channel(channel_id)
        except Exception as ex:
            return False, f'Канал трибуны недоступен: {ex}'
    if channel is None:
        return False, 'Канал трибуны не найден'
    try:
        await channel.edit(
            overwrites=build_overwrites(guild, cfg, opened=True),
            reason='broadcaster open tribune',
        )
    except Exception as ex:
        return False, f'Права не открылись: {ex}'
    event_id = int(row.get('event_id') or 0)
    if event_id:
        try:
            event = guild.get_scheduled_event(event_id)
            if event is None:
                event = await guild.fetch_scheduled_event(event_id)
            if event is not None and getattr(event, 'status', None) == discord.EventStatus.scheduled:
                await event.start()
        except Exception as ex:
            log.warning('event start %s: %s', event_id, ex)
    await _ping_open(guild, cfg, row, channel)
    store.mark_opened(row['id'])
    return True, 'opened'


async def _ping_open(guild, cfg, row, channel) -> None:
    text = f'@everyone Трибуна **{row.get("title") or "трибуна"}** открыта — {channel.mention}'
    target = await announce_channel(guild, cfg)
    if target is None:
        log.warning('no announce channel for tribune %s', row.get('id'))
        return
    try:
        await target.send(
            text,
            allowed_mentions=discord.AllowedMentions(everyone=True),
        )
    except Exception as ex:
        log.warning('everyone ping failed: %s', ex)


async def announce_channel(guild: discord.Guild, cfg: dict):
    cid = _cfg_int(cfg, 'announce_channel_id')
    if cid:
        found = guild.get_channel(cid)
        if found is not None:
            return found
    system = getattr(guild, 'system_channel', None)
    if system is not None:
        return system
    needles = ('анонс', 'эфир', 'tribune', 'трибун')
    for ch in list(getattr(guild, 'text_channels', []) or []):
        low = (ch.name or '').lower()
        if any(n in low for n in needles):
            return ch
    channels = list(getattr(guild, 'text_channels', []) or [])
    return channels[0] if channels else None


async def ensure_love_lobby(guild: discord.Guild, cfg: dict):
    love = cfg.get('love') or {}
    lobby_name = (love.get('lobby_name') or 'войти в лав руму').strip() or 'войти в лав руму'
    category = await love_category(guild, cfg)
    for ch in list(getattr(category, 'voice_channels', []) or []):
        if ch.name == lobby_name:
            store.meta_set(f'love_lobby:{guild.id}', str(ch.id))
            return ch
    for ch in list(getattr(guild, 'voice_channels', []) or []):
        if ch.name == lobby_name:
            store.meta_set(f'love_lobby:{guild.id}', str(ch.id))
            return ch
    created = await guild.create_voice_channel(
        lobby_name,
        category=category,
        reason='broadcaster love lobby',
    )
    store.meta_set(f'love_lobby:{guild.id}', str(created.id))
    return created


async def spawn_love_room(guild: discord.Guild, cfg: dict, member, lobby) -> Optional[int]:
    love = cfg.get('love') or {}
    room_name = (love.get('room_name') or 'лав рума').strip() or 'лав рума'
    try:
        limit = int(love.get('user_limit') or 2)
    except Exception:
        limit = 2
    limit = max(2, min(99, limit))
    category = getattr(lobby, 'category', None) or await love_category(guild, cfg)
    channel = await guild.create_voice_channel(
        room_name[:100],
        category=category,
        user_limit=limit,
        reason=f'love room for {member.id}',
    )
    store.add_love(int(channel.id), int(guild.id), int(member.id))
    try:
        await member.move_to(channel, reason='love room')
    except Exception as ex:
        log.warning('love move failed: %s', ex)
        store.remove_love(int(channel.id))
        try:
            await channel.delete(reason='love move failed')
        except Exception:
            pass
        return None
    return int(channel.id)


async def delete_empty_love(channel) -> bool:
    if channel is None or not store.is_love(int(channel.id)):
        return False
    members = list(getattr(channel, 'members', []) or [])
    if members:
        return False
    store.remove_love(int(channel.id))
    try:
        await channel.delete(reason='love room empty')
    except discord.NotFound:
        pass
    except Exception as ex:
        log.warning('love delete %s: %s', channel.id, ex)
        return False
    return True
