# -*- coding: utf-8 -*-
"""Канальные охранники (заказ владельца 2026-09-12).

1) Возраст 1–13 в указанных каналах → удалить сообщение.
   Каналы: 1312430207067623456, 1312552287360516207
   Ловим «мне 13», «13+», «13_», «+12», «1 3», «возраст=11».
   14+ НЕ трогаем.
   Предупреждение — только в ЛС нарушителю (в канал не пишем).

2) Селфи-канал 1312434029278134294 → выдать роль 920462510769975306
   при посте с картинкой/видео (вложение или embed-image).

Иммунитет: боты, manage_messages / administrator, владелец бота.
"""
from __future__ import annotations

import re
import unicodedata
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

# Удаляем заявленный возраст 1–13 включительно (заказ: «на 13 цифру»).
AGE_MAX_BLOCK = 13
AGE_MIN_ALLOWED = AGE_MAX_BLOCK + 1  # 14

# Мусор вокруг/между цифрами: +13, 13_, 1 3, 1-3 …
_AGE_JUNK = r'[\s\+\=\~\*\-\.\:\;\#\|\/\\<>_]*'
# 10–13 с разделителями; одиночная 1–9 не берёт «1» из «1 4».
_TEEN = rf'1{_AGE_JUNK}[0-3]'
_NUM_ME = rf'(?P<a_me>{_TEEN}|[1-9](?!{_AGE_JUNK}\d))(?!\d)'
_NUM_YRS = rf'(?P<a_yrs>{_TEEN})(?!\d)'
_NUM_AGE = rf'(?P<a_age>{_TEEN}|[1-9](?!{_AGE_JUNK}\d))(?!\d)'
# хвост после числа: 13+, 13_, 13+++ …
_AFTER = rf'{_AGE_JUNK}'

_UNDERAGE_RE = re.compile(
    rf'(?ix)'
    rf'(?:'
    # «мне 13» / «я +13_» / «мне есть 1 3»
    rf'(?:^|[^\wа-яё])(?:мне|я)\s*(?:есть\s*)?{_AGE_JUNK}{_NUM_ME}'
    rf'{_AFTER}(?:(?:лет|года|год|л\.?){_AFTER})?'
    rf'|'
    # «13 лет» / «+13_ лет» / «13+ лет» (только 10–13)
    rf'(?:^|[^\wа-яё]){_AGE_JUNK}{_NUM_YRS}'
    rf'{_AFTER}(?:лет|года|год)(?:[^\wа-яё]|$)'
    rf'|'
    # «возраст 13» / «возраст=+13_»
    rf'возраст(?:а|у)?\s*[:=]?{_AGE_JUNK}{_NUM_AGE}{_AFTER}'
    rf'|'
    # голое «13» / «13+» / «13_» / «+13» (в возрастном канале)
    rf'(?:^|[^\wа-яё])(?P<a_bare>\+?{_TEEN}[_+\=\~\*]*)(?!\d)'
    rf')'
)

_WORD_AGES = {
    'десять': 10, 'одиннадцать': 11, 'двенадцать': 12, 'тринадцать': 13,
}
_WORD_AGE_RE = re.compile(
    r'(?ix)(?:^|[^\wа-яё])(?:мне|я)\s*(?:есть\s*)?'
    r'(десять|одиннадцать|двенадцать|тринадцать)'
    r'(?:\s*(?:лет|года|год))?'
)

_ZW_RE = re.compile(
    r'[\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff\u00ad\u180e]'
)


def _normalize_age_text(text: str) -> str:
    """Убрать zero-width / спойлеры и привести похожие цифры к ASCII."""
    if not text:
        return ''
    t = unicodedata.normalize('NFKC', text)
    t = _ZW_RE.sub('', t)
    t = t.replace('||', '')
    return t


def _digits_to_age(raw: Optional[str]) -> int:
    if not raw:
        return 0
    try:
        return int(re.sub(r'\D', '', raw))
    except (TypeError, ValueError):
        return 0


def claimed_underage(text: str) -> Optional[int]:
    """Вернуть заявленный возраст 1–13 или None, если ≤13 не заявлено."""
    if not text:
        return None
    norm = _normalize_age_text(text)
    m = _UNDERAGE_RE.search(norm)
    if m:
        gd = m.groupdict()
        raw = (
            gd.get('a_me') or gd.get('a_yrs') or gd.get('a_age')
            or gd.get('a_bare')
        )
        age = _digits_to_age(raw)
        if 1 <= age <= AGE_MAX_BLOCK:
            return age
    mw = _WORD_AGE_RE.search(norm)
    if mw:
        age = _WORD_AGES.get(mw.group(1).lower())
        if age is not None and age <= AGE_MAX_BLOCK:
            return age
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


async def _warn_author_private(message: discord.Message) -> None:
    """Закрытое предупреждение только автору (ЛС). В канал не пишем."""
    ch = getattr(message.channel, 'mention', None) or 'этом канале'
    text = (
        f'Твоё сообщение в {ch} удалено: нельзя указывать '
        f'возраст {AGE_MAX_BLOCK} и младше (нужно от {AGE_MIN_ALLOWED}).'
    )
    try:
        await message.author.send(text)
    except (discord.Forbidden, discord.HTTPException) as ex:
        log.debug('age-guard: ЛС %s недоступны: %s', message.author.id, ex)


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

        # ── 1) возраст 1–13 (ответ только в ЛС) ────────────────────────
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
                    log.info(
                        'age-guard: удалил msg %s от %s (заявлен возраст %s) в #%s',
                        message.id, message.author.id, age, ch_id,
                    )
                    await _warn_author_private(message)
                return

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
