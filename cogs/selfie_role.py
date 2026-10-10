# -*- coding: utf-8 -*-
"""Роль за фото/видео в канале селфи.

Канал и роль задаются в .env (SELFIE_CHANNEL_ID / SELFIE_ROLE_ID).
При вложении image/* или video/* участник получает роль (если её ещё нет).
При старте бот один раз проходит историю канала и докидывает роль тем,
кто уже кидал медиа без роли.
"""
from __future__ import annotations

import asyncio

import discord
from discord.ext import commands

from config import Config
from logger import get_logger

_log = get_logger('selfie_role')

IMAGE_EXTS = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp')
VIDEO_EXTS = ('.mp4', '.mov', '.webm', '.mkv', '.avi', '.m4v')

# Сколько сообщений смотреть при бэкапе (Discord history).
_BACKFILL_LIMIT = 2000
_BACKFILL_SLEEP = 0.35


def _channel_id() -> int:
    return int(getattr(Config, 'SELFIE_CHANNEL_ID', 0) or 0)


def _role_id() -> int:
    return int(getattr(Config, 'SELFIE_ROLE_ID', 0) or 0)


def is_media_attachment(attachment) -> bool:
    if attachment is None:
        return False
    ct = (getattr(attachment, 'content_type', '') or '').lower()
    if ct.startswith('image/') or ct.startswith('video/'):
        return True
    fn = (getattr(attachment, 'filename', '') or '').lower()
    return fn.endswith(IMAGE_EXTS) or fn.endswith(VIDEO_EXTS)


def message_has_media(message: discord.Message) -> bool:
    atts = getattr(message, 'attachments', None) or []
    if any(is_media_attachment(a) for a in atts):
        return True
    # stickers не считаем; embeds с картинкой от пользователя — редко
    return False


async def _grant(member: discord.Member, role: discord.Role, *, reason: str) -> bool:
    if member is None or role is None:
        return False
    if role in (getattr(member, 'roles', None) or []):
        return False
    try:
        await member.add_roles(role, reason=reason)
        return True
    except discord.Forbidden:
        _log.warning('selfie_role: нет прав выдать %s → %s', role.id, member.id)
    except Exception as ex:
        _log.warning('selfie_role: grant %s: %s', member.id, ex)
    return False


class SelfieRole(commands.Cog):
    """Авто-роль за медиа в канале селфи."""

    def __init__(self, bot):
        self.bot = bot
        self._backfill_done = set()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        try:
            if not message.guild or message.author.bot or message.webhook_id:
                return
            ch_id = _channel_id()
            role_id = _role_id()
            if not ch_id or not role_id:
                return
            if getattr(message.channel, 'id', 0) != ch_id:
                return
            if not message_has_media(message):
                return
            member = message.author
            if not isinstance(member, discord.Member):
                member = message.guild.get_member(message.author.id)
            if member is None:
                return
            role = message.guild.get_role(role_id)
            if role is None:
                _log.warning('selfie_role: роль %s не найдена', role_id)
                return
            if await _grant(member, role, reason='селфи-канал: фото/видео'):
                _log.info('selfie_role: +role %s → %s (%s)',
                          role_id, member.id, member.display_name)
        except Exception as ex:
            _log.debug('selfie_role: on_message: %s', ex)

    @commands.Cog.listener()
    async def on_ready(self):
        try:
            self.bot.loop.create_task(self._backfill_all())
        except Exception as ex:
            _log.debug('selfie_role: backfill task: %s', ex)

    async def _backfill_all(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(8)  # дать гильдиям и ролям подтянуться
        ch_id = _channel_id()
        role_id = _role_id()
        if not ch_id or not role_id:
            _log.info('selfie_role: выключено (нет SELFIE_CHANNEL_ID/ROLE_ID)')
            return
        for guild in list(getattr(self.bot, 'guilds', []) or []):
            gid = getattr(guild, 'id', None)
            if not gid or gid in self._backfill_done:
                continue
            self._backfill_done.add(gid)
            try:
                await self._backfill_guild(guild, ch_id, role_id)
            except Exception as ex:
                _log.warning('selfie_role: backfill %s: %s', gid, ex)

    async def _backfill_guild(self, guild: discord.Guild, ch_id: int, role_id: int):
        channel = guild.get_channel(ch_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(ch_id)
            except Exception:
                channel = None
        if channel is None or not hasattr(channel, 'history'):
            _log.info('selfie_role: канал %s нет на %s', ch_id, guild.id)
            return
        role = guild.get_role(role_id)
        if role is None:
            _log.warning('selfie_role: роль %s нет на %s', role_id, guild.id)
            return

        need: set[int] = set()
        scanned = 0
        try:
            async for msg in channel.history(limit=_BACKFILL_LIMIT):
                scanned += 1
                if getattr(msg.author, 'bot', False):
                    continue
                if not message_has_media(msg):
                    continue
                uid = getattr(msg.author, 'id', None)
                if uid:
                    need.add(int(uid))
                if scanned % 100 == 0:
                    await asyncio.sleep(_BACKFILL_SLEEP)
        except discord.Forbidden:
            _log.warning('selfie_role: нет доступа к истории %s', ch_id)
            return
        except Exception as ex:
            _log.warning('selfie_role: history %s: %s', ch_id, ex)
            return

        granted = 0
        skipped = 0
        for uid in need:
            member = guild.get_member(uid)
            if member is None:
                skipped += 1
                continue
            if role in member.roles:
                skipped += 1
                continue
            if await _grant(member, role, reason='селфи-канал: backfill медиа'):
                granted += 1
                await asyncio.sleep(0.4)

        _log.info(
            'selfie_role: backfill guild=%s scanned=%s media_authors=%s '
            'granted=%s already_or_left=%s',
            guild.id, scanned, len(need), granted, skipped,
        )


async def setup(bot):
    await bot.add_cog(SelfieRole(bot))
