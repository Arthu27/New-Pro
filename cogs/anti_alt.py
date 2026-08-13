# -*- coding: utf-8 -*-
"""Анти-альт (Anti-Alt Cog)
==========================
Ловит свежесозданные аккаунты при входе на сервер — классический признак
твинков нарушителей, рейд-ботов и рекламных рассыльщиков.

- /антиальт вкл|выкл        — включить/выключить защиту
- /антиальт порог <дней>    — минимальный возраст аккаунта (по умолчанию 7)
- /антиальт действие alert|kick|ban — что делать с нарушителем
- /антиальт канал [#канал]  — куда слать карточки тревоги
- /антиальт статус          — текущие настройки

Настройки — per-guild в SQLite (GuildData 'anti_alt'), панель умеет их
редактировать (страница «Модули»). Все метки времени — aware UTC.
"""
from datetime import datetime, timezone

import discord
from discord.ext import commands

from db import GuildData
from logger import get_logger
from services import text_format as tf

log = get_logger("anti_alt")

UTC = timezone.utc
COLOR_ALERT = 0xED4245
COLOR_OK = 0x57F287

DEFAULT_SETTINGS = {
    'enabled': False,
    'min_age_days': 7,
    'action': 'alert',          # alert | kick | ban
    'log_channel_id': 0,
    'whitelist': [],            # user_id — доверенные, их не трогаем
}

ACTIONS = ('alert', 'kick', 'ban')
ACTION_NAMES = {'alert': 'только тревога', 'kick': 'кик', 'ban': 'бан'}


# ─── чистые функции (покрыты тестом) ────────────────────────────────────────

def merge_settings(raw):
    """Наложить сохранённое на дефолт: неизвестные ключи отбрасываются,
    сломанные типы возвращаются к дефолту."""
    out = dict(DEFAULT_SETTINGS)
    if not isinstance(raw, dict):
        return out
    for key in out:
        if key in raw:
            out[key] = raw[key]
    if out['action'] not in ACTIONS:
        out['action'] = DEFAULT_SETTINGS['action']
    try:
        out['min_age_days'] = max(0, int(out['min_age_days']))
    except (TypeError, ValueError):
        out['min_age_days'] = DEFAULT_SETTINGS['min_age_days']
    if not isinstance(out['whitelist'], list):
        out['whitelist'] = []
    return out


def account_age_days(created_at, now=None):
    """Возраст аккаунта в днях (float). naive метка трактуется как UTC."""
    now = now or datetime.now(UTC)
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return (now - created_at).total_seconds() / 86400.0


def decide(settings, user_id, created_at, now=None):
    """Решение по зашедшему: (сработало, действие, возраст_дней, причина)."""
    settings = merge_settings(settings)
    age = account_age_days(created_at, now)
    if not settings['enabled']:
        return False, None, age, 'выключено'
    if user_id in settings['whitelist']:
        return False, None, age, 'в белом списке'
    limit = settings['min_age_days']
    if age >= limit:
        return False, None, age, 'возраст в норме'
    return True, settings['action'], age, (
        f'аккаунту {tf.fmt_seconds(int(age * 86400))} при пороге '
        f'{tf.spell(limit, "день", "дня", "дней")}')


def settings_lines(settings):
    """Человеческие строки настроек для /антиальт статус и панели."""
    s = merge_settings(settings)
    return [
        f"Защита: {'включена' if s['enabled'] else 'выключена'}",
        f"Порог возраста: {tf.spell(s['min_age_days'], 'день', 'дня', 'дней')}",
        f"Действие: {ACTION_NAMES[s['action']]}",
        f"Канал тревог: #{s['log_channel_id'] or 'лог-канал сервера'}",
        f"Белый список: {tf.spell(len(s['whitelist']), 'аккаунт', 'аккаунта', 'аккаунтов')}",
    ]


# ─── ког ────────────────────────────────────────────────────────────────────

class AntiAlt(commands.Cog):
    """Щит от свежих твинков и рейд-ботов."""

    def __init__(self, bot):
        self.bot = bot
        self.db = GuildData('anti_alt')

    # ---- настройки ----
    def _settings(self, guild_id):
        return merge_settings(self.db.get(guild_id, 'settings', {}))

    def _save(self, guild_id, settings):
        self.db.set(guild_id, 'settings', settings)

    # ---- слушатель ----
    @commands.Cog.listener()
    async def on_member_join(self, member):
        triggered, action, age, reason = decide(
            self._settings(member.guild.id), member.id, member.created_at)
        if not triggered:
            return
        log.info('anti_alt: %s (%s) на %s — %s, действие %s',
                 member, member.id, member.guild.id, reason, action)
        await self._alert(member, age, reason, action)
        await self._punish(member, action, reason)

    async def _alert(self, member, age, reason, action):
        settings = self._settings(member.guild.id)
        channel = None
        cid = settings.get('log_channel_id')
        if cid:
            channel = member.guild.get_channel(cid)
        if channel is None:
            channel = member.guild.system_channel
        if channel is None:
            return
        embed = discord.Embed(
            title='Анти-альт: свежий аккаунт',
            description=(
                f'{member.mention} ({member}) зашёл на сервер.\n'
                f'Возраст аккаунта: **{tf.fmt_seconds(int(age * 86400))}**.\n'
                f'Причина: {reason}.\nДействие: **{ACTION_NAMES[action]}**.'
            ),
            color=COLOR_ALERT,
            timestamp=datetime.now(UTC),
        )
        embed.set_footer(text=f'ID: {member.id}')
        try:
            await channel.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException) as _ex:
            log.warning('anti_alt: карточка не ушла на %s: %s', member.guild.id, _ex)

    async def _punish(self, member, action, reason):
        try:
            if action == 'kick':
                await member.kick(reason=f'Анти-альт: {reason}')
            elif action == 'ban':
                await member.ban(reason=f'Анти-альт: {reason}', delete_message_days=0)
        except discord.Forbidden:
            log.warning('anti_alt: не хватило прав на %s (%s)', action, member.id)
        except discord.HTTPException as _ex:
            log.error('anti_alt: действие %s не удалось для %s: %s',
                      action, member.id, _ex)

    # ---- команды ----
    @commands.hybrid_group(name='антиальт', aliases=['antialt'],
                           description='Анти-альт защита сервера')
    @commands.has_permissions(manage_guild=True)
    async def grp(self, ctx):
        if ctx.invoked_subcommand is None:
            await self._show_status(ctx)

    @grp.command(name='вкл', description='Включить анти-альт')
    async def cmd_on(self, ctx):
        s = self._settings(ctx.guild.id)
        s['enabled'] = True
        self._save(ctx.guild.id, s)
        await ctx.reply('Анти-альт **включён**. ' +
                        settings_lines(s)[1] + ', ' + settings_lines(s)[2] + '.',
                        mention_author=False)

    @grp.command(name='выкл', description='Выключить анти-альт')
    async def cmd_off(self, ctx):
        s = self._settings(ctx.guild.id)
        s['enabled'] = False
        self._save(ctx.guild.id, s)
        await ctx.reply('Анти-альт **выключен**.', mention_author=False)

    @grp.command(name='порог', description='Минимальный возраст аккаунта в днях')
    async def cmd_limit(self, ctx, дней: int):
        if not 0 <= дней <= 3650:
            await ctx.reply('Порог — от 0 до 3650 дней.', mention_author=False)
            return
        s = self._settings(ctx.guild.id)
        s['min_age_days'] = дней
        self._save(ctx.guild.id, s)
        await ctx.reply(f'Порог: **{tf.spell(дней, "день", "дня", "дней")}**.',
                        mention_author=False)

    @grp.command(name='действие', description='alert | kick | ban')
    async def cmd_action(self, ctx, действие: str):
        действие = действие.strip().lower()
        if действие not in ACTIONS:
            await ctx.reply('Действие должно быть: `alert`, `kick` или `ban`.',
                            mention_author=False)
            return
        s = self._settings(ctx.guild.id)
        s['action'] = действие
        self._save(ctx.guild.id, s)
        await ctx.reply(f'Действие: **{ACTION_NAMES[действие]}**.',
                        mention_author=False)

    @grp.command(name='канал', description='Куда слать карточки тревоги')
    async def cmd_channel(self, ctx, канал: discord.TextChannel = None):
        s = self._settings(ctx.guild.id)
        s['log_channel_id'] = канал.id if канал else 0
        self._save(ctx.guild.id, s)
        where = канал.mention if канал else 'лог-канал сервера (авто)'
        await ctx.reply(f'Карточки анти-альта идут в {where}.', mention_author=False)

    @grp.command(name='статус', description='Текущие настройки')
    async def cmd_status(self, ctx):
        await self._show_status(ctx)

    async def _show_status(self, ctx):
        s = self._settings(ctx.guild.id)
        embed = discord.Embed(
            title='Анти-альт — настройки',
            description='\n'.join('• ' + line for line in settings_lines(s)),
            color=COLOR_OK if s['enabled'] else COLOR_ALERT,
        )
        await ctx.reply(embed=embed, mention_author=False)


async def setup(bot):
    await bot.add_cog(AntiAlt(bot))
