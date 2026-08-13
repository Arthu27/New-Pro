# -*- coding: utf-8 -*-
"""Локдаун (Lockdown Cog)
========================
Экстренная красная кнопка при рейде: мгновенно закрывает каналы на запись
для @everyone, а после — возвращает оригинальные права, какими бы они ни
были (мы запоминаем исходное состояние, а не тупо выставляем None).

- /lockdown [#канал|все] [причина] — закрыть канал или весь сервер
- /unlockdown [#канал|все]         — вернуть права обратно
- /lockstatus                      — что сейчас под локдауном

Состояние — SQLite (GuildData 'lockdown'): переживает рестарт бота, права
не теряются, даже если бот упал посреди рейда. Метки — aware UTC.
"""
from datetime import datetime, timezone

import discord
from discord.ext import commands

from db import GuildData
from logger import get_logger
from services import text_format as tf

log = get_logger("lockdown")

UTC = timezone.utc
COLOR_LOCK = 0xED4245
COLOR_OPEN = 0x57F287

WATCHED_PERMS = ('send_messages', 'add_reactions', 'create_public_threads',
                 'connect')


# ─── чистые функции (покрыты тестом) ────────────────────────────────────────

def empty_state():
    """Что закрыто: {cid: {perm: исходное значение}} + метаданные."""
    return {'channels': {}, 'since': None, 'by': None, 'reason': None}


def snapshot_overwrite(ow):
    """PermissionOverwrite-like -> компактный dict исходных значений."""
    return {p: getattr(ow, p, None) for p in WATCHED_PERMS}


def apply_lock(ow):
    """Закрыть overwrite (mutate): deny всем наблюдаемым правам."""
    for p in WATCHED_PERMS:
        if hasattr(ow, p):
            setattr(ow, p, False)
    return ow


def apply_restore(ow, saved):
    """Вернуть overwrite из снимка (mutate). Неизвестные ключи пропускаем."""
    for p in WATCHED_PERMS:
        if p in saved and hasattr(ow, p):
            setattr(ow, p, saved[p])
    return ow


def state_locked_count(state):
    return len((state or {}).get('channels', {}))


def state_summary(state, now=None):
    """'3 канала · 2 ч назад · причина: рейд' — строка для статуса."""
    state = state or empty_state()
    n = state_locked_count(state)
    if n == 0:
        return 'локдауна нет'
    parts = [tf.spell(n, 'канал закрыт', 'канала закрыто', 'каналов закрыто')]
    if state.get('since'):
        try:
            since = datetime.fromisoformat(state['since'])
            parts.append(tf.rel_time(since, now or datetime.now(UTC)))
        except ValueError:
            parts.append('давно')
    if state.get('reason'):
        parts.append(f'причина: {state["reason"][:60]}')
    return ' · '.join(parts)


def is_locked(state, channel_id):
    return str(channel_id) in (state or {}).get('channels', {})


# ─── ког ────────────────────────────────────────────────────────────────────

class Lockdown(commands.Cog):
    """Аварийное закрытие сервера на запись с точным откатом."""

    def __init__(self, bot):
        self.bot = bot
        self.db = GuildData('lockdown')

    def _state(self, guild_id):
        return self.db.get(guild_id, 'state', empty_state()) or empty_state()

    def _save(self, guild_id, state):
        self.db.set(guild_id, 'state', state)

    # ---- команды ----
    @commands.hybrid_command(name='lockdown', aliases=['локдаун'],
                             description='Закрыть канал или весь сервер на запись')
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_channels=True, manage_roles=True)
    async def cmd_lock(self, ctx, канал: str = 'all', *, причина: str = 'локдаун'):
        guild = ctx.guild
        state = self._state(guild.id)
        targets = self._resolve_targets(guild, канал, ctx.channel)
        if not targets:
            await ctx.reply('Не нашёл такой канал. `/lockdown #канал` или `/lockdown all`.',
                            mention_author=False)
            return

        locked, skipped = [], []
        for ch in targets:
            cid = str(ch.id)
            if cid in state['channels']:
                skipped.append(ch)
                continue
            try:
                ow = ch.overwrites_for(guild.default_role)
                state['channels'][cid] = snapshot_overwrite(ow)
                await ch.set_permissions(guild.default_role,
                                         overwrite=apply_lock(ow),
                                         reason=f'Локдаун: {причина[:120]}')
                locked.append(ch)
            except (discord.Forbidden, discord.HTTPException) as _ex:
                log.warning('lockdown: #%s на %s не закрылся: %s', ch.id, guild.id, _ex)
                state['channels'].pop(cid, None)
                skipped.append(ch)

        if locked:
            state['since'] = state['since'] or datetime.now(UTC).isoformat()
            state['by'] = str(ctx.author)
            state['reason'] = причина[:200]
            self._save(guild.id, state)

        embed = discord.Embed(
            title='Локдаун включён' if locked else 'Локдаун: ничего не закрылось',
            description=(
                f'Закрыто: {tf.spell(len(locked), "канал", "канала", "каналов")}'
                + (f' · уже было/не вышло: {len(skipped)}' if skipped else '')
                + f'\nПричина: {причина[:200]}\nОткат: `/unlockdown {"#" + канал if канал not in ("all", "все") else "all"}`'
            ),
            color=COLOR_LOCK if locked else COLOR_OPEN,
            timestamp=datetime.now(UTC),
        )
        await ctx.reply(embed=embed, mention_author=False)

    @commands.hybrid_command(name='unlockdown', aliases=['анлокдаун', 'разлок'],
                             description='Вернуть права каналу или всему серверу')
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_channels=True, manage_roles=True)
    async def cmd_unlock(self, ctx, канал: str = 'all'):
        guild = ctx.guild
        state = self._state(guild.id)
        targets = self._resolve_targets(guild, канал, ctx.channel)
        if not targets:
            await ctx.reply('Не нашёл такой канал.', mention_author=False)
            return

        restored, missing = [], []
        for ch in targets:
            cid = str(ch.id)
            saved = state['channels'].pop(cid, None)
            if saved is None:
                missing.append(ch)
                continue
            try:
                ow = ch.overwrites_for(guild.default_role)
                await ch.set_permissions(guild.default_role,
                                         overwrite=apply_restore(ow, saved),
                                         reason='Локдаун: откат прав')
                restored.append(ch)
            except (discord.Forbidden, discord.HTTPException) as _ex:
                log.warning('lockdown: #%s на %s не открылся: %s', ch.id, guild.id, _ex)
                state['channels'][cid] = saved  # оставляем под локом, попробуем позже
                missing.append(ch)

        if not state['channels']:
            state.update({'since': None, 'by': None, 'reason': None})
        self._save(guild.id, state)

        embed = discord.Embed(
            title='Локдаун снят' if restored else 'Локдаун: нечего открывать',
            description=(
                f'Открыто: {tf.spell(len(restored), "канал", "канала", "каналов")}'
                + (f' · пропущено/не вышло: {len(missing)}' if missing else '')
                + f'\n{state_summary(state)}'
            ),
            color=COLOR_OPEN,
            timestamp=datetime.now(UTC),
        )
        await ctx.reply(embed=embed, mention_author=False)

    @commands.hybrid_command(name='lockstatus', aliases=['локстатус'],
                             description='Что сейчас под локдауном')
    async def cmd_status(self, ctx):
        state = self._state(ctx.guild.id)
        lines = []
        for cid in list(state['channels'].keys())[:20]:
            ch = ctx.guild.get_channel(int(cid))
            lines.append(f'• {ch.mention if ch else "#" + cid}')
        embed = discord.Embed(
            title='Статус локдауна',
            description=(state_summary(state) + ('\n' + '\n'.join(lines) if lines else '')),
            color=COLOR_LOCK if state['channels'] else COLOR_OPEN,
        )
        await ctx.reply(embed=embed, mention_author=False)

    # ---- утилиты ----
    def _resolve_targets(self, guild, spec, fallback):
        """'all'/'все'/'#' — все текстовые; '123' / '#name' — один канал;
        без аргумента — текущий (fallback)."""
        spec = (spec or '').strip().lower()
        if spec in ('all', 'все', 'сервер', '#все'):
            return [c for c in guild.text_channels]
        if spec in ('', 'here', 'здесь', 'текущий'):
            return [fallback] if fallback is not None else []
        digits = ''.join(ch for ch in spec if ch.isdigit())
        if digits:
            ch = guild.get_channel(int(digits))
            return [ch] if ch is not None else []
        name = spec.lstrip('#')
        for ch in guild.text_channels:
            if ch.name == name:
                return [ch]
        return []


async def setup(bot):
    await bot.add_cog(Lockdown(bot))
