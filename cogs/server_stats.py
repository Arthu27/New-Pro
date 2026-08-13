# -*- coding: utf-8 -*-
"""Каналы-счётчики (Server Stats Cog)
====================================
Живая статистика сервера прямо в списке каналов: имена вида
«Участники: 128» сами обновляются по расписанию.

Переменные в шаблоне: {members} {bots} {people} {channels} {text}
{voice} {roles} {boosts} {online}.

- /счётчики добавить #канал <шаблон>  — напр. Участники: {members}
- /счётчики убрать <№>                — отвязать канал
- /счётчики список                    — все связки + текущий рендер
- /счётчики обновить                  — обновить сейчас (лимитовано)
- /счётчики вкл|выкл                  — общий выключатель

Discord даёт переименовывать канал не чаще 2 раз в 10 минут — поэтому
авто-обновление раз в 600 секунд и только каналов, чьё имя изменилось.

Хранилище — SQLite (GuildData 'server_stats'). Метки — aware UTC.
"""
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks

from db import GuildData
from logger import get_logger
from services import text_format as tf

log = get_logger("server_stats")

UTC = timezone.utc
COLOR = 0x1ABC9C
UPDATE_INTERVAL_SEC = 600        # авто-обновление
MIN_MANUAL_GAP_SEC = 330         # между ручными «обновить»

DEFAULT_SETTINGS = {
    'enabled': True,
    'channels': {},              # {channel_id(str): шаблон имени}
    'last_update': None,
    'last_manual': None,
}


class _SafeDict(dict):
    def __missing__(self, key):
        return '{' + str(key) + '}'


# ─── чистые функции (покрыты тестом) ────────────────────────────────────────

def merge_settings(raw):
    out = dict(DEFAULT_SETTINGS)
    out['channels'] = {}
    if isinstance(raw, dict):
        for key in ('enabled', 'last_update', 'last_manual'):
            if key in raw:
                out[key] = raw[key]
        if isinstance(raw.get('channels'), dict):
            out['channels'] = {str(k): str(v)[:80]
                               for k, v in raw['channels'].items()}
    return out


def gather_stats(guild):
    """Сервер -> счётчики. Всё защищено getattr: фейки/частичные объекты ок."""
    members_count = int(getattr(guild, 'member_count', 0) or 0)
    members = list(getattr(guild, 'members', []) or [])
    bots = sum(1 for m in members if getattr(m, 'bot', False))
    online = sum(1 for m in members
                 if str(getattr(getattr(m, 'status', 'offline'), 'value',
                                getattr(m, 'status', 'offline'))) != 'offline')
    text_ch = [c for c in getattr(guild, 'text_channels', []) or []]
    voice_ch = [c for c in getattr(guild, 'voice_channels', []) or []]
    return {
        'members': members_count,
        'bots': bots,
        'people': max(0, members_count - bots) if members else members_count,
        'online': online,
        'channels': len(getattr(guild, 'channels', []) or []),
        'text': len(text_ch),
        'voice': len(voice_ch),
        'roles': len(getattr(guild, 'roles', []) or []),
        'boosts': int(getattr(guild, 'premium_subscription_count', 0) or 0),
    }


def render_counter(template, stats):
    """Шаблон + счётчики -> имя канала. Неизвестные переменные не роняют."""
    try:
        return str(template).format_map(_SafeDict(stats))[:80]
    except (ValueError, IndexError) as _ex:
        log.debug('server_stats: битый шаблон %r: %s', str(template)[:60], _ex)
        return str(template)[:80]


def plan_updates(settings, current_names, stats):
    """[(channel_id, новое_имя)] — только то, что реально поменялось."""
    out = []
    for cid, template in merge_settings(settings)['channels'].items():
        new_name = render_counter(template, stats)
        if current_names.get(cid) != new_name:
            out.append((cid, new_name))
    return out


def should_auto_update(settings, now):
    """Пора ли авто-обновлять: включено + есть каналы + интервал вышел."""
    s = merge_settings(settings)
    if not s['enabled'] or not s['channels']:
        return False
    last = s.get('last_update')
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(last)
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=UTC)
    except ValueError:
        return True
    return (now - last_dt).total_seconds() >= UPDATE_INTERVAL_SEC


def manual_allowed(settings, now):
    """Ручное «обновить» не чаще MIN_MANUAL_GAP_SEC (щадим рейтлимит)."""
    s = merge_settings(settings)
    last = s.get('last_manual')
    if not last:
        return True, 0
    try:
        last_dt = datetime.fromisoformat(last)
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=UTC)
    except ValueError:
        return True, 0
    left = int(MIN_MANUAL_GAP_SEC - (now - last_dt).total_seconds())
    return (left <= 0), max(0, left)


# ─── ког ────────────────────────────────────────────────────────────────────

class ServerStats(commands.Cog):
    """Самообновляющиеся каналы-табло со статистикой сервера."""

    def __init__(self, bot):
        self.bot = bot
        self.db = GuildData('server_stats')
        self.update_loop.start()

    def cog_unload(self):
        self.update_loop.cancel()

    def _settings(self, guild_id):
        return merge_settings(self.db.get(guild_id, 'settings', {}))

    def _save(self, guild_id, settings):
        self.db.set(guild_id, 'settings', settings)

    # ---- авто-обновление ----
    @tasks.loop(seconds=UPDATE_INTERVAL_SEC)
    async def update_loop(self):
        now = datetime.now(UTC)
        for guild in list(self.bot.guilds):
            s = self._settings(guild.id)
            if not should_auto_update(s, now):
                continue
            done = await self._apply_updates(guild, s)
            s['last_update'] = now.isoformat()
            self._save(guild.id, s)
            if done:
                log.info('server_stats: %s — обновлено %s табло', guild.id, done)

    @update_loop.before_loop
    async def _wait_ready(self):
        await self.bot.wait_until_ready()

    async def _apply_updates(self, guild, settings):
        current = {str(c.id): c.name for c in guild.channels}
        stats = gather_stats(guild)
        done = 0
        for cid, new_name in plan_updates(settings, current, stats):
            channel = guild.get_channel(int(cid))
            if channel is None:
                continue
            try:
                await channel.edit(name=new_name, reason='Каналы-счётчики')
                done += 1
            except (discord.Forbidden, discord.HTTPException) as _ex:
                log.warning('server_stats: канал %s на %s не переименовался: %s',
                            cid, guild.id, _ex)
        return done

    # ---- команды ----
    @commands.hybrid_group(name='счётчики', aliases=['serverstats', 'counters'],
                           description='Каналы с живой статистикой сервера')
    @commands.has_permissions(manage_guild=True)
    async def grp(self, ctx):
        if ctx.invoked_subcommand is None:
            await self._list(ctx)

    @grp.command(name='добавить', description='#канал + шаблон с {members} и ко')
    async def cmd_add(self, ctx, канал: discord.VoiceChannel, *, шаблон: str):
        шаблон = шаблон.strip()
        if not шаблон or '{' not in шаблон:
            await ctx.reply('Шаблон должен содержать переменную, напр. '
                            '`Участники: {members}`.', mention_author=False)
            return
        s = self._settings(ctx.guild.id)
        if str(канал.id) in s['channels']:
            await ctx.reply(f'{канал.mention} уже счётчик — сначала `/счётчики убрать`.',
                            mention_author=False)
            return
        s['channels'][str(канал.id)] = шаблон[:80]
        self._save(ctx.guild.id, s)
        preview = render_counter(шаблон, gather_stats(ctx.guild))
        await ctx.reply(f'Привязано: {канал.mention} → `{preview}` '
                        '(обновится на ближайшем тике).', mention_author=False)

    @grp.command(name='убрать', description='Отвязать канал по номеру из списка')
    async def cmd_remove(self, ctx, номер: int):
        s = self._settings(ctx.guild.id)
        items = list(s['channels'].items())
        if not 1 <= номер <= len(items):
            await ctx.reply(f'Нет счётчика №{номер} (всего {len(items)}).',
                            mention_author=False)
            return
        cid, _tpl = items[номер - 1]
        del s['channels'][cid]
        self._save(ctx.guild.id, s)
        await ctx.reply(f'Счётчик №{номер} отвязан (имя канала осталось как есть).',
                        mention_author=False)

    @grp.command(name='список', description='Все счётчики и текущий рендер')
    async def cmd_list(self, ctx):
        await self._list(ctx)

    @grp.command(name='обновить', description='Обновить табло сейчас')
    async def cmd_now(self, ctx):
        s = self._settings(ctx.guild.id)
        ok, left = manual_allowed(s, datetime.now(UTC))
        if not ok:
            await ctx.reply(f'Рейтлимит Discord: подождите ещё {tf.fmt_seconds(left)}.',
                            mention_author=False)
            return
        s['last_manual'] = datetime.now(UTC).isoformat()
        done = await self._apply_updates(ctx.guild, s)
        self._save(ctx.guild.id, s)
        await ctx.reply(f'Обновлено табло: **{done}**.', mention_author=False)

    @grp.command(name='вкл', description='Разрешить авто-обновление')
    async def cmd_on(self, ctx):
        s = self._settings(ctx.guild.id)
        s['enabled'] = True
        self._save(ctx.guild.id, s)
        await ctx.reply('Авто-обновление счётчиков **включено**.', mention_author=False)

    @grp.command(name='выкл', description='Пауза авто-обновления')
    async def cmd_off(self, ctx):
        s = self._settings(ctx.guild.id)
        s['enabled'] = False
        self._save(ctx.guild.id, s)
        await ctx.reply('Авто-обновление счётчиков **выключено**.', mention_author=False)

    async def _list(self, ctx):
        s = self._settings(ctx.guild.id)
        if not s['channels']:
            await ctx.reply('Счётчиков нет. Пример: '
                            '`/счётчики добавить #голос Участники: {members}`.',
                            mention_author=False)
            return
        stats = gather_stats(ctx.guild)
        current = {str(c.id): c.name for c in ctx.guild.channels}
        lines = []
        for i, (cid, tpl) in enumerate(s['channels'].items(), 1):
            rendered = render_counter(tpl, stats)
            alive = 'есть' if cid in current else 'канал удалён!'
            lines.append(f'**{i}.** <#{cid}> ({alive})\n`{rendered}`')
        embed = discord.Embed(
            title=f'Счётчики ({len(s["channels"])}) — '
                  + ('обновляются' if s['enabled'] else 'на паузе'),
            description='\n'.join(lines), color=COLOR)
        await ctx.reply(embed=embed, mention_author=False)


async def setup(bot):
    await bot.add_cog(ServerStats(bot))
