# -*- coding: utf-8 -*-
"""Канальные охранники (заказ владельца 2026-09-12, усиление 2026-09-17).

1) Возраст < 18 — НЕЛЬЗЯ ВООБЩЕ (весь сервер).
   • Везде: «мне 16», «я 14 лет», «возраст=17», «четырнадцать»,
     обходы «ищу девушку меньше 18», «до 18», «под 18», «несовершеннолетн…».
   • В каналах знакомств дополнительно: голое «17» / «16+» / «+14».
   «мне 18» / «старше 18» / «от 18» / 18+ НЕ трогаем.
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
# Каналы знакомств: плюс голые цифры 10–17 (в остальных каналах — только
# явные заявления возраста / поиск «меньше 18»).
AGE_GUARD_CHANNELS = frozenset({
    1312430207067623456,
    1312552287360516207,
})
# Меньше 18 нельзя вообще — проверяем каждый текстовый канал гильдии.
AGE_GUARD_GUILD_WIDE = True

SELFIE_CHANNEL_ID = 1312434029278134294
SELFIE_ROLE_ID = 920462510769975306

# Удаляем заявленный возраст 1–17; 18+ оставляем.
AGE_MAX_BLOCK = 17
AGE_MIN_ALLOWED = AGE_MAX_BLOCK + 1  # 18

# Мусор вокруг/между цифрами: +17, 16_, 1 5, 1-4 …
_AGE_JUNK = r'[\s\+\=\~\*\-\.\:\;\#\|\/\\<>_]*'
# 10–17 с разделителями; одиночная 1–9 не берёт «1» из «1 8».
_UNDER = rf'1{_AGE_JUNK}[0-7]'
_NUM_ME = rf'(?P<a_me>{_UNDER}|[1-9](?!{_AGE_JUNK}\d))(?!\d)'
_NUM_YRS = rf'(?P<a_yrs>{_UNDER})(?!\d)'
_NUM_AGE = rf'(?P<a_age>{_UNDER}|[1-9](?!{_AGE_JUNK}\d))(?!\d)'
_AFTER = rf'{_AGE_JUNK}'

# Явные заявления возраста (безопасно для всего сервера).
_UNDERAGE_EXPLICIT_RE = re.compile(
    rf'(?ix)'
    rf'(?:'
    # «мне 16» / «я +17_» / «мне есть 1 5»
    rf'(?:^|[^\wа-яё])(?:мне|я)\s*(?:есть\s*)?{_AGE_JUNK}{_NUM_ME}'
    rf'{_AFTER}(?:(?:лет|года|год|л\.?){_AFTER})?'
    rf'|'
    # «15 лет» / «+16_ лет» (только 10–17, без «2 года на сервере»)
    rf'(?:^|[^\wа-яё]){_AGE_JUNK}{_NUM_YRS}'
    rf'{_AFTER}(?:лет|года|год)(?:[^\wа-яё]|$)'
    rf'|'
    # «возраст 14» / «возраст=+17_»
    rf'возраст(?:а|у)?\s*[:=]?{_AGE_JUNK}{_NUM_AGE}{_AFTER}'
    rf')'
)

# Голое «17» / «16+» / «+14» — только в каналах знакомств.
_UNDERAGE_BARE_RE = re.compile(
    rf'(?ix)(?:^|[^\wа-яё])(?P<a_bare>\+?{_UNDER}[_+\=\~\*]*)(?!\d)'
)

_WORD_AGES = {
    'десять': 10, 'одиннадцать': 11, 'двенадцать': 12, 'тринадцать': 13,
    'четырнадцать': 14, 'пятнадцать': 15, 'шестнадцать': 16, 'семнадцать': 17,
}
_WORD_AGE_RE = re.compile(
    r'(?ix)(?:^|[^\wа-яё])(?:мне|я)\s*(?:есть\s*)?'
    r'(десять|одиннадцать|двенадцать|тринадцать|'
    r'четырнадцать|пятнадцать|шестнадцать|семнадцать)'
    r'(?:\s*(?:лет|года|год))?'
)

# Обходы: «меньше 18», «ищу до 18», «под 18», «<18», «несовершеннолетн…»
# Не трогаем «не меньше 18» / «не младше 18» / «старше 18» / «от 18».
_BELOW_18_RE = re.compile(
    rf'(?ix)'
    rf'(?:'
    rf'(?:^|[^\wа-яё])(?:меньше|младше|до|под|ниже|<)\s*{_AGE_JUNK}'
    rf'1{_AGE_JUNK}8(?!\d)'
    rf'|'
    rf'(?:^|[^\wа-яё])(?:under|u)\s*{_AGE_JUNK}1{_AGE_JUNK}8(?!\d)'
    rf'|'
    rf'несовершеннолетн'
    rf')'
)
_NOT_BELOW_18_RE = re.compile(
    r'(?ix)(?:^|[^\wа-яё])не\s+(?:меньше|младше|ниже)\s+'
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


def _is_below_18_solicitation(norm: str) -> bool:
    """Ищут/упоминают возраст младше 18 (обход вместо «мне 16»)."""
    if not _BELOW_18_RE.search(norm):
        return False
    # «не меньше 18» / «не младше 18» — это 18+, пропускаем
    if _NOT_BELOW_18_RE.search(norm):
        for m in _BELOW_18_RE.finditer(norm):
            start = m.start()
            prefix = norm[max(0, start - 4):start].lower()
            if not re.search(r'не\s*$', prefix):
                return True
        return False
    return True


def claimed_underage(text: str, *, allow_bare: bool = True) -> Optional[int]:
    """Вернуть возраст 1–17 / маркер обхода, или None если <18 не заявлено.

    allow_bare=False — без голых «16»/«17+» (для всего сервера, меньше ложных).
    allow_bare=True — строже, для каналов знакомств.
    """
    if not text:
        return None
    norm = _normalize_age_text(text)
    if _is_below_18_solicitation(norm):
        return AGE_MAX_BLOCK  # обход «меньше/до/под 18»
    m = _UNDERAGE_EXPLICIT_RE.search(norm)
    if m:
        gd = m.groupdict()
        raw = gd.get('a_me') or gd.get('a_yrs') or gd.get('a_age')
        age = _digits_to_age(raw)
        if 1 <= age <= AGE_MAX_BLOCK:
            return age
    if allow_bare:
        mb = _UNDERAGE_BARE_RE.search(norm)
        if mb:
            age = _digits_to_age(mb.group('a_bare'))
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


def _should_scan_channel(ch_id: int) -> bool:
    """Где действует фильтр <18."""
    if AGE_GUARD_GUILD_WIDE:
        return True
    return ch_id in AGE_GUARD_CHANNELS


async def _warn_author_private(message: discord.Message) -> None:
    """Закрытое предупреждение только автору (ЛС). В канал не пишем."""
    ch = getattr(message.channel, 'mention', None) or 'этом канале'
    text = (
        f'Твоё сообщение в {ch} удалено: на сервере нельзя указывать или '
        f'искать возраст младше {AGE_MIN_ALLOWED}.'
    )
    try:
        await message.author.send(text)
    except (discord.Forbidden, discord.HTTPException) as ex:
        log.debug('age-guard: ЛС %s недоступны: %s', message.author.id, ex)


async def _enforce_age(message: discord.Message) -> bool:
    """Удалить сообщение с <18. True если сработало."""
    if message.guild is None or message.author.bot:
        return False
    if not isinstance(message.author, discord.Member):
        return False
    if _is_immune(message.author):
        return False

    ch_id = getattr(message.channel, 'id', 0) or 0
    if not _should_scan_channel(ch_id):
        return False

    # В каналах знакомств — строже (голые цифры); везде — явные заявления.
    allow_bare = ch_id in AGE_GUARD_CHANNELS
    age = claimed_underage(message.content or '', allow_bare=allow_bare)
    if age is None:
        return False

    try:
        await message.delete()
    except discord.Forbidden:
        log.warning('age-guard: нет права удалить в #%s', ch_id)
        return False
    except discord.HTTPException as ex:
        log.debug('age-guard delete: %s', ex)
        return False

    log.info(
        'age-guard: удалил msg %s от %s (заявлен возраст %s) в #%s bare=%s',
        message.id, message.author.id, age, ch_id, allow_bare,
    )
    await _warn_author_private(message)
    return True


class ChannelGuards(commands.Cog):
    """Возраст-фильтр (<18 везде) + роль за селфи."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if await _enforce_age(message):
            return

        if message.guild is None or message.author.bot:
            return
        if not isinstance(message.author, discord.Member):
            return

        ch_id = getattr(message.channel, 'id', 0) or 0

        # ── селфи → роль ───────────────────────────────────────────
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

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        """Редакт с «мне 14» тоже ловим — меньше 18 нельзя вообще."""
        if after is None:
            return
        if before and (before.content or '') == (after.content or ''):
            return
        await _enforce_age(after)


async def setup(bot: commands.Bot):
    await bot.add_cog(ChannelGuards(bot))
