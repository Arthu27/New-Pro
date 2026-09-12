# -*- coding: utf-8 -*-
"""Канальные охранники (заказ владельца 2026-09-12).

1) Возраст < 18 в указанных каналах → удалить сообщение.
   Каналы: 1312430207067623456, 1312552287360516207
   Ловим формулировки вроде «мне 16», «15 лет», «возраст 14».
   «мне 18» / «18 лет» НЕ трогаем.

2) Селфи-канал 1312434029278134294 → выдать роль 920462510769975306
   при посте с картинкой/видео (вложение или embed-image).

Иммунитет: боты, manage_messages / administrator, владелец бота.
"""
from __future__ import annotations

import re
from typing import Optional

import discord
from discord.ext import commands

from logger import get_logger

log = get_logger('channel_guards')

# ── боевые ID (владелец 2026-09-12) ─────────────────────────────────────
AGE_GUARD_CHANNELS = frozenset({
    1312430207067623456,
    1312552287360516207,
})
SELFIE_CHANNEL_ID = 1312434029278134294
SELFIE_ROLE_ID = 920462510769975306

# Возраст < 18:
#  • «мне 16» / «я 14» / «возраст 15» — любые 1–17
#  • «15 лет» — только 10–17 (чтобы «2 года на сервере» не триггерило)
# (?!\d) не даёт схватить «1» из «18» / «19».
_UNDERAGE_RE = re.compile(
    r'(?ix)'
    r'(?:'
    r'(?:^|[^\wа-яё])(?:мне|я)\s*(?:есть\s*)?(?P<a1>1[0-7]|[1-9])(?!\d)'
    r'(?:\s*(?:лет|года|год|л\.?))?'
    r'|'
    r'(?:^|[^\wа-яё])(?P<a2>1[0-7])(?!\d)\s*(?:лет|года|год)(?:[^\wа-яё]|$)'
    r'|'
    r'возраст(?:а|у)?\s*[:=]?\s*(?P<a3>1[0-7]|[1-9])(?!\d)'
    r')'
)

# Словесные числа 10–17 (на всякий случай)
_WORD_AGES = {
    'десять': 10, 'одиннадцать': 11, 'двенадцать': 12, 'тринадцать': 13,
    'четырнадцать': 14, 'пятнадцать': 15, 'шестнадцать': 16, 'семнадцать': 17,
}
_WORD_AGE_RE = re.compile(
    r'(?ix)(?:^|[^\wа-яё])(?:мне|я)\s*(?:есть\s*)?'
    r'(десять|одиннадцать|двенадцать|тринадцать|четырнадцать|'
    r'пятнадцать|шестнадцать|семнадцать)'
    r'(?:\s*(?:лет|года|год))?'
)


def claimed_underage(text: str) -> Optional[int]:
    """Вернуть заявленный возраст 1–17 или None, если <18 не заявлено."""
    if not text:
        return None
    m = _UNDERAGE_RE.search(text)
    if m:
        raw = m.group('a1') or m.group('a2') or m.group('a3')
        try:
            age = int(raw)
        except (TypeError, ValueError):
            age = 0
        if 1 <= age <= 17:
            return age
    mw = _WORD_AGE_RE.search(text)
    if mw:
        return _WORD_AGES.get(mw.group(1).lower())
    return None


def message_has_media(message: discord.Message) -> bool:
    """Есть ли в сообщении картинка/видео (вложение или embed)."""
    for att in message.attachments or ():
        ctype = (att.content_type or '').lower()
        name = (att.filename or '').lower()
        if ctype.startswith(('image/', 'video/')):
            return True
        if name.endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp',
                          '.mp4', '.mov', '.webm', '.mkv')):
            return True
    for emb in message.embeds or ():
        if emb.image or emb.thumbnail or emb.video:
            return True
    return False


def _is_immune(member: discord.Member) -> bool:
    if member is None or getattr(member, 'bot', False):
        return True
    try:
        from config import Config
        if int(member.id) in Config.all_owner_ids():
            return True
    except Exception:
        pass
    perms = getattr(member, 'guild_permissions', None)
    if perms and (perms.administrator or perms.manage_messages):
        return True
    return False


class ChannelGuards(commands.Cog):
    """Возраст-фильтр + роль за селфи."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None or message.author.bot:
            return
        if not isinstance(message.author, discord.Member):
            return

        ch_id = getattr(message.channel, 'id', 0) or 0

        # ── 1) возраст < 18 ────────────────────────────────────────────
        if ch_id in AGE_GUARD_CHANNELS and not _is_immune(message.author):
            age = claimed_underage(message.content or '')
            if age is not None:
                try:
                    await message.delete()
                except discord.Forbidden:
                    log.warning('age-guard: нет права удалить в #%s', ch_id)
                except discord.HTTPException as ex:
                    log.debug('age-guard delete: %s', ex)
                else:
                    log.info('age-guard: удалил msg %s от %s (заявлен возраст %s) в #%s',
                             message.id, message.author.id, age, ch_id)
                    try:
                        await message.channel.send(
                            f'{message.author.mention} в этом канале нельзя '
                            f'указывать возраст младше 18.',
                            delete_after=8,
                        )
                    except Exception:
                        pass
                return  # дальше селфи не обрабатываем (сообщения уже нет)

        # ── 2) селфи → роль ───────────────────────────────────────────
        if ch_id == SELFIE_CHANNEL_ID and message_has_media(message):
            role = message.guild.get_role(SELFIE_ROLE_ID)
            if role is None:
                log.warning('selfie-role: роль %s не найдена на сервере', SELFIE_ROLE_ID)
                return
            if role in message.author.roles:
                return
            try:
                await message.author.add_roles(
                    role, reason='Селфи в канале селфи (автороль)')
                log.info('selfie-role: выдал %s → %s', role.id, message.author.id)
            except discord.Forbidden:
                log.warning('selfie-role: нет права выдать роль %s', SELFIE_ROLE_ID)
            except discord.HTTPException as ex:
                log.debug('selfie-role add: %s', ex)


async def setup(bot: commands.Bot):
    await bot.add_cog(ChannelGuards(bot))
