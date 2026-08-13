# -*- coding: utf-8 -*-
"""Считалка (Counting Cog)
=========================
Канал, где участники считают по очереди: 1, 2, 3… Сбился номер, написал
тот же человек дважды или влез посторонний текст — счёт падает на ноль,
рекорд запоминается.

- /счёт канал #canal   — включить считалку в канале
- /счёт выкл           — выключить
- /счёт статус         — текущее число и рекорд сервера

Хранилище — SQLite (GuildData 'counting'). Метки — aware UTC.
"""
from datetime import datetime, timezone

import discord
from discord.ext import commands

from db import GuildData
from logger import get_logger
from services import text_format as tf

log = get_logger("counting")

UTC = timezone.utc
COLOR_HIT = 0x2ECC71
COLOR_FAIL = 0xED4245


# ─── чистые функции (покрыты тестом) ────────────────────────────────────────

def empty_state(channel_id=0):
    return {
        'channel_id': channel_id,   # 0 — считалка выключена
        'next': 1,                  # какое число ждём
        'best': 0,                  # рекорд сервера
        'last_user': 0,             # кто назвал последнее
        'last_user_name': '',
        'fails': 0,
        'updated_at': None,
    }


def parse_number(text):
    """Строго целое положительное число без мусора вокруг. Иначе None."""
    text = str(text or '').strip()
    if not text.isdigit():
        return None
    try:
        n = int(text)
    except ValueError:
        return None
    return n if n > 0 else None


def try_count(state, user_id, user_name, text, now):
    """Попытка назвать число. Возвращает (результат, state).

    Результат: 'ok' | 'wrong_number' | 'same_user' | 'not_number' |
    'inactive'. state мутируется в случаях ok/wrong/same_user.
    """
    state = state or empty_state()
    if not state.get('channel_id'):
        return 'inactive', state
    n = parse_number(text)
    if n is None:
        return 'not_number', state
    if user_id == state.get('last_user'):
        return _fail(state, 'same_user', now)
    if n != state.get('next'):
        return _fail(state, 'wrong_number', now, expected=state.get('next'), got=n)

    state['next'] = n + 1
    state['last_user'] = user_id
    state['last_user_name'] = str(user_name)
    state['best'] = max(state.get('best', 0), n)
    state['updated_at'] = now.isoformat()
    return 'ok', state


def _fail(state, kind, now, expected=None, got=None):
    state['fails'] = state.get('fails', 0) + 1
    state['fail_reason'] = kind
    state['fail_expected'] = expected
    state['fail_got'] = got
    state['next'] = 1
    state['last_user'] = 0
    state['updated_at'] = now.isoformat()
    return kind, state


def status_lines(state):
    """Строки статуса для /счёт статус."""
    s = state or empty_state()
    if not s.get('channel_id'):
        return ['Считалка выключена — включите: `/счёт канал #канал`']
    lines = [
        f"Ждём число: **{s.get('next', 1)}**",
        f"Рекорд сервера: **{s.get('best', 0)}**",
    ]
    if s.get('last_user_name'):
        lines.append(f"Последнее назвал: {s['last_user_name']}")
    if s.get('fails'):
        lines.append(f"Падений счёта: {tf.spell(s['fails'], 'раз', 'раза', 'раз')}")
    return lines


# ─── ког ────────────────────────────────────────────────────────────────────

class Counting(commands.Cog):
    """Серверная считалка с рекордами."""

    def __init__(self, bot):
        self.bot = bot
        self.db = GuildData('counting')

    def _state(self, guild_id):
        return self.db.get(guild_id, 'state', empty_state()) or empty_state()

    def _save(self, guild_id, state):
        self.db.set(guild_id, 'state', state)

    # ---- слушатель ----
    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.guild or message.author.bot:
            return
        state = self._state(message.guild.id)
        if state.get('channel_id') != message.channel.id:
            return
        result, state = try_count(state, message.author.id, str(message.author),
                                  message.content, datetime.now(UTC))
        self._save(message.guild.id, state)
        if result == 'inactive':
            return
        if result == 'ok':
            try:
                await message.add_reaction('✅')
            except (discord.Forbidden, discord.HTTPException) as _ex:
                log.debug('counting: реакция не встала: %s', _ex)
            return
        if result == 'not_number':
            try:
                await message.delete()
            except (discord.Forbidden, discord.NotFound, discord.HTTPException) as _ex:
                log.debug('counting: лишнее сообщение не удалилось: %s', _ex)
            return

        # падение счёта
        reason = ('нельзя два раза подряд одному' if result == 'same_user'
                  else f"ждали {state.get('fail_expected')}, а пришло {state.get('fail_got')}")
        embed = discord.Embed(
            title='Счёт упал!',
            description=(f'{message.author.mention}, {reason}.\n'
                         f'Рекорд остался: **{state.get("best", 0)}**. Начинаем с **1**.'),
            color=COLOR_FAIL,
            timestamp=datetime.now(UTC),
        )
        try:
            await message.delete()
        except (discord.Forbidden, discord.NotFound, discord.HTTPException) as _ex:
            log.debug('counting: неверное число не удалилось: %s', _ex)
        await message.channel.send(embed=embed)

    # ---- команды ----
    @commands.hybrid_group(name='счёт', aliases=['count', 'counting'],
                           description='Считалка сервера')
    async def grp(self, ctx):
        if ctx.invoked_subcommand is None:
            await self._show(ctx)

    @grp.command(name='канал', description='Включить считалку в канале')
    @commands.has_permissions(manage_guild=True)
    async def cmd_channel(self, ctx, канал: discord.TextChannel):
        state = empty_state(канал.id)
        state['updated_at'] = datetime.now(UTC).isoformat()
        self._save(ctx.guild.id, state)
        await ctx.reply(f'Считалка включена в {канал.mention} — начинаем с **1**.',
                        mention_author=False)

    @grp.command(name='выкл', description='Выключить считалку')
    @commands.has_permissions(manage_guild=True)
    async def cmd_off(self, ctx):
        state = self._state(ctx.guild.id)
        state['channel_id'] = 0
        self._save(ctx.guild.id, state)
        await ctx.reply('Считалка выключена (рекорд сохранён).', mention_author=False)

    @grp.command(name='статус', description='Текущее число и рекорд')
    async def cmd_status(self, ctx):
        await self._show(ctx)

    async def _show(self, ctx):
        embed = discord.Embed(title='Считалка — статус',
                              description='\n'.join(status_lines(self._state(ctx.guild.id))),
                              color=COLOR_HIT)
        await ctx.reply(embed=embed, mention_author=False)


async def setup(bot):
    await bot.add_cog(Counting(bot))
