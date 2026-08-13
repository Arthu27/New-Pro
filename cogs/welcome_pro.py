# -*- coding: utf-8 -*-
"""Приветствия PRO (Welcome PRO Cog)
===================================
Расширенные приветствия новичков: несколько шаблонов с переменными,
ротация (каждый новичок получает следующий шаблон по кругу), аккуратная
карточка с аватаром и порядковым номером участника, опциональное ЛС.

Переменные в шаблоне: {mention} {user} {server} {count}.

- /приветствие вкл #канал    — включить и выбрать канал
- /приветствие выкл          — выключить
- /приветствие добавить <текст> — новый шаблон
- /приветствие список        — все шаблоны
- /приветствие убрать <№>    — удалить шаблон
- /приветствие лс вкл|выкл <текст> — личное сообщение новичку
- /приветствие тест          — превью карточки на себе

Настройки — SQLite (GuildData 'welcome_pro'). Метки — aware UTC.
"""
from datetime import datetime, timezone

import discord
from discord.ext import commands

from db import GuildData
from logger import get_logger

log = get_logger("welcome_pro")

UTC = timezone.utc
COLOR = 0x57F287

DEFAULT_SETTINGS = {
    'enabled': False,
    'channel_id': 0,
    'templates': [
        'Добро пожаловать, {mention}! Ты — {count}-й житель **{server}**.',
        '{mention} приземлился на **{server}**. Устраивайся поудобнее!',
        'Поприветствуем {mention}! Участник №{count}.',
    ],
    'rotate_index': 0,
    'dm_enabled': False,
    'dm_text': 'Привет, {user}! Рады видеть тебя на **{server}**. '
               'Загляни в правила — и вперёд, знакомиться.',
}


# ─── чистые функции (покрыты тестом) ────────────────────────────────────────

def merge_settings(raw):
    out = dict(DEFAULT_SETTINGS)
    out['templates'] = list(DEFAULT_SETTINGS['templates'])
    if isinstance(raw, dict):
        for key in out:
            if key in raw:
                out[key] = raw[key]
    if not isinstance(out['templates'], list) or not out['templates']:
        out['templates'] = list(DEFAULT_SETTINGS['templates'])
    out['templates'] = [str(t)[:500] for t in out['templates']][:15]
    try:
        out['rotate_index'] = int(out['rotate_index']) % len(out['templates'])
    except (TypeError, ValueError, ZeroDivisionError):
        out['rotate_index'] = 0
    return out


def render_welcome(template, user, mention, server, count):
    """Шаблон + переменные -> текст. Неизвестные переменные не роняют рендер."""
    safe = {
        'user': str(user),
        'mention': str(mention),
        'server': str(server),
        'count': int(count),
    }
    try:
        return str(template).format_map(_SafeDict(safe))
    except (ValueError, IndexError, KeyError) as _ex:
        log.debug('welcome_pro: битый шаблон %r: %s', str(template)[:60], _ex)
        return str(template)


class _SafeDict(dict):
    def __missing__(self, key):
        return '{' + str(key) + '}'


def pick_template(settings):
    """Шаблон по кругу: (текст, index_следующего)."""
    s = merge_settings(settings)
    idx = s['rotate_index'] % len(s['templates'])
    return s['templates'][idx], (idx + 1) % len(s['templates'])


def add_template(settings, text):
    """(settings, ok): добавить шаблон с валидацией."""
    s = merge_settings(settings)
    text = str(text or '').strip()
    if len(text) < 10:
        return s, 'шаблон короче 10 символов — такое не впечатлит'
    if '{mention}' not in text and '{user}' not in text:
        return s, 'добавьте {mention} или {user} — кого приветствуем?'
    if len(s['templates']) >= 15:
        return s, 'максимум 15 шаблонов'
    s['templates'].append(text[:500])
    return s, None


def remove_template(settings, index):
    """(settings, ok): убрать шаблон по номеру (1-based)."""
    s = merge_settings(settings)
    if len(s['templates']) <= 1:
        return s, 'последний шаблон не удаляем — с чем-то бот же должен зайти'
    if not 1 <= index <= len(s['templates']):
        return s, f'нет шаблона №{index} (всего {len(s["templates"])})'
    s['templates'].pop(index - 1)
    s['rotate_index'] = s['rotate_index'] % len(s['templates'])
    return s, None


# ─── ког ────────────────────────────────────────────────────────────────────

class WelcomePro(commands.Cog):
    """Красивые ротируемые приветствия новичков."""

    def __init__(self, bot):
        self.bot = bot
        self.db = GuildData('welcome_pro')

    def _settings(self, guild_id):
        return merge_settings(self.db.get(guild_id, 'settings', {}))

    def _save(self, guild_id, settings):
        self.db.set(guild_id, 'settings', settings)

    # ---- слушатель ----
    @commands.Cog.listener()
    async def on_member_join(self, member):
        settings = self._settings(member.guild.id)
        if not settings['enabled']:
            return
        count = member.guild.member_count or 0
        template, next_idx = pick_template(settings)
        settings['rotate_index'] = next_idx
        self._save(member.guild.id, settings)
        text = render_welcome(template, member.display_name, member.mention,
                              member.guild.name, count)

        channel = (member.guild.get_channel(settings['channel_id'])
                   or member.guild.system_channel)
        if channel is not None:
            embed = discord.Embed(description=text, color=COLOR,
                                  timestamp=datetime.now(UTC))
            embed.set_author(name=f'Добро пожаловать, {member.display_name}!',
                             icon_url=member.display_avatar.url
                             if member.display_avatar else None)
            embed.set_footer(text=f'Участник №{count}')
            try:
                await channel.send(embed=embed)
            except (discord.Forbidden, discord.HTTPException) as _ex:
                log.warning('welcome_pro: приветствие на %s не ушло: %s',
                            member.guild.id, _ex)

        if settings['dm_enabled']:
            try:
                dm_text = render_welcome(settings['dm_text'], member.display_name,
                                         member.mention, member.guild.name, count)
                await member.send(dm_text)
            except (discord.Forbidden, discord.HTTPException) as _ex:
                log.debug('welcome_pro: ЛС %s закрыты: %s', member.id, _ex)

    # ---- команды ----
    @commands.hybrid_group(name='приветствие', aliases=['welcomepro'],
                           description='Приветствия PRO')
    @commands.has_permissions(manage_guild=True)
    async def grp(self, ctx):
        if ctx.invoked_subcommand is None:
            await self._show_settings(ctx)

    @grp.command(name='вкл', description='Включить приветствия в канале')
    async def cmd_on(self, ctx, канал: discord.TextChannel):
        s = self._settings(ctx.guild.id)
        s['enabled'] = True
        s['channel_id'] = канал.id
        self._save(ctx.guild.id, s)
        await ctx.reply(f'Приветствия включены в {канал.mention}.', mention_author=False)

    @grp.command(name='выкл', description='Выключить приветствия')
    async def cmd_off(self, ctx):
        s = self._settings(ctx.guild.id)
        s['enabled'] = False
        self._save(ctx.guild.id, s)
        await ctx.reply('Приветствия выключены.', mention_author=False)

    @grp.command(name='добавить', description='Добавить шаблон приветствия')
    async def cmd_add(self, ctx, *, текст: str):
        s, err = add_template(self._settings(ctx.guild.id), текст)
        if err:
            await ctx.reply(f'Не добавлено: {err}.', mention_author=False)
            return
        self._save(ctx.guild.id, s)
        await ctx.reply(f'Шаблон **№{len(s["templates"])}** добавлен.', mention_author=False)

    @grp.command(name='список', description='Все шаблоны')
    async def cmd_list(self, ctx):
        s = self._settings(ctx.guild.id)
        lines = [f'**{i}.** {t[:150]}' for i, t in enumerate(s['templates'], 1)]
        embed = discord.Embed(title=f'Шаблоны приветствий ({len(s["templates"])})',
                              description='\n'.join(lines), color=COLOR)
        embed.set_footer(text=f'Следующий по кругу: №{s["rotate_index"] + 1}')
        await ctx.reply(embed=embed, mention_author=False)

    @grp.command(name='убрать', description='Удалить шаблон по номеру')
    async def cmd_remove(self, ctx, номер: int):
        s, err = remove_template(self._settings(ctx.guild.id), номер)
        if err:
            await ctx.reply(f'Не убрано: {err}.', mention_author=False)
            return
        self._save(ctx.guild.id, s)
        await ctx.reply(f'Шаблон №{номер} удалён. Осталось: {len(s["templates"])}.',
                        mention_author=False)

    @grp.command(name='лс', description='ЛС новичку: вкл|выкл [текст]')
    async def cmd_dm(self, ctx, режим: str, *, текст: str = ''):
        режим = режим.strip().lower()
        s = self._settings(ctx.guild.id)
        if режим == 'вкл':
            s['dm_enabled'] = True
            if текст.strip():
                s['dm_text'] = текст.strip()[:500]
        elif режим == 'выкл':
            s['dm_enabled'] = False
        else:
            await ctx.reply('Режим: `вкл` или `выкл`.', mention_author=False)
            return
        self._save(ctx.guild.id, s)
        await ctx.reply(f'ЛС новичкам: **{"включены" if s["dm_enabled"] else "выключены"}**.',
                        mention_author=False)

    @grp.command(name='тест', description='Превью карточки на вас')
    async def cmd_test(self, ctx):
        s = self._settings(ctx.guild.id)
        count = ctx.guild.member_count or 0
        template, _ = pick_template(s)
        text = render_welcome(template, ctx.author.display_name, ctx.author.mention,
                              ctx.guild.name, count)
        embed = discord.Embed(description=text, color=COLOR,
                              timestamp=datetime.now(UTC))
        embed.set_author(name=f'Добро пожаловать, {ctx.author.display_name}! (превью)',
                         icon_url=ctx.author.display_avatar.url
                         if ctx.author.display_avatar else None)
        embed.set_footer(text=f'Участник №{count} · ротация при превью не двигается')
        await ctx.reply(embed=embed, mention_author=False)

    async def _show_settings(self, ctx):
        s = self._settings(ctx.guild.id)
        embed = discord.Embed(
            title='Приветствия PRO — настройки',
            description=(
                f"• Статус: {'включены' if s['enabled'] else 'выключены'}\n"
                f"• Шаблонов: {len(s['templates'])} (ротация по кругу)\n"
                f"• ЛС новичкам: {'да' if s['dm_enabled'] else 'нет'}\n"
                f"• Переменные: {{mention}} {{user}} {{server}} {{count}}"
            ),
            color=COLOR,
        )
        await ctx.reply(embed=embed, mention_author=False)


async def setup(bot):
    await bot.add_cog(WelcomePro(bot))
