# -*- coding: utf-8 -*-
"""Ночной режим (Night Mode Cog)
===============================
Ночью сервер уязвимее: модераторы спят, а рейдеры активнее. Ночной режим
по расписанию поднимает слоумод и (опционально) закрывает каналы на запись,
а утром возвращает всё как было — прежние значения сохраняются.

- /ночь вкл|выкл           — включить/выключить
- /ночь окно <нач> <кон>   — часы, напр. /ночь окно 23 7 (с 23:00 до 7:00 UTC)
- /ночь слоумод <сек>      — слоумод ночью (0 — не трогать)
- /ночь лок вкл|выкл       — закрывать ли @everyone запись в каналы
- /ночь исключить [#канал] — канал не трогаем ни слоумодом, ни локом
- /ночь статус             — настройки и текущее состояние

Настройки и состояние — SQLite (GuildData 'night_mode'). Метки — aware UTC.
"""
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks

from db import GuildData
from logger import get_logger
from services import text_format as tf

log = get_logger("night_mode")

UTC = timezone.utc
COLOR_NIGHT = 0x2C2F7A
COLOR_DAY = 0x57F287

DEFAULT_SETTINGS = {
    'enabled': False,
    'start_hour': 23,
    'end_hour': 7,
    'slowmode_seconds': 0,      # 0 — слоумод не применяем
    'lock_channels': False,     # True — deny send_messages у @everyone
    'exempt_channels': [],      # id каналов-исключений
    'report_channel_id': 0,     # куда писать «режим вкл/выкл»
}


# ─── чистые функции (покрыты тестом) ────────────────────────────────────────

def merge_settings(raw):
    out = dict(DEFAULT_SETTINGS)
    if not isinstance(raw, dict):
        return out
    for key in out:
        if key in raw:
            out[key] = raw[key]
    for key in ('start_hour', 'end_hour'):
        try:
            out[key] = int(out[key]) % 24
        except (TypeError, ValueError):
            out[key] = DEFAULT_SETTINGS[key]
    try:
        out['slowmode_seconds'] = max(0, min(21600, int(out['slowmode_seconds'])))
    except (TypeError, ValueError):
        out['slowmode_seconds'] = 0
    if not isinstance(out['exempt_channels'], list):
        out['exempt_channels'] = []
    return out


def is_night(moment=None, start=23, end=7):
    """Внутри ли ночного окна [start, end) по ЧАСАМ (UTC).

    Окно может переходить через полночь: 23..7 означает «23:00–06:59».
    start == end — окно пустое (False). naive момент трактуется как UTC.
    """
    moment = moment or datetime.now(UTC)
    if isinstance(moment, str):
        moment = datetime.fromisoformat(moment)
    hour = moment.hour
    if start == end:
        return False
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def empty_state():
    """Активное состояние (чтобы утром всё вернуть)."""
    return {'active': False, 'slow_before': {}, 'lock_before': {},
            'since': None}


def window_text(settings):
    s = merge_settings(settings)
    return f"{s['start_hour']:02d}:00–{s['end_hour']:02d}:00 UTC"


def plan_settings_lines(settings):
    s = merge_settings(settings)
    slow = (tf.spell(s['slowmode_seconds'], 'секунда', 'секунды', 'секунд')
            if s['slowmode_seconds'] else 'не трогаем')
    return [
        f"Режим: {'включён' if s['enabled'] else 'выключен'}",
        f"Окно: {window_text(s)}",
        f"Слоумод ночью: {slow}",
        f"Лок каналов: {'да' if s['lock_channels'] else 'нет'}",
        f"Исключения: {tf.spell(len(s['exempt_channels']), 'канал', 'канала', 'каналов')}",
    ]


def channels_for_action(guild, settings):
    """Текстовые каналы, которые режиму обрабатывать (без исключений)."""
    s = merge_settings(settings)
    exempt = set(s['exempt_channels'])
    return [c for c in getattr(guild, 'text_channels', []) if c.id not in exempt]


# ─── ког ────────────────────────────────────────────────────────────────────

class NightMode(commands.Cog):
    """Ночной щит: слоумод и лок каналов по расписанию."""

    def __init__(self, bot):
        self.bot = bot
        self.db = GuildData('night_mode')
        self.watch_loop.start()

    def cog_unload(self):
        self.watch_loop.cancel()

    def _settings(self, guild_id):
        return merge_settings(self.db.get(guild_id, 'settings', {}))

    def _save_settings(self, guild_id, settings):
        self.db.set(guild_id, 'settings', settings)

    def _state(self, guild_id):
        return self.db.get(guild_id, 'state', empty_state()) or empty_state()

    def _save_state(self, guild_id, state):
        self.db.set(guild_id, 'state', state)

    # ---- петля ----
    @tasks.loop(seconds=60)
    async def watch_loop(self):
        now = datetime.now(UTC)
        for guild in list(self.bot.guilds):
            settings = self._settings(guild.id)
            if not settings['enabled']:
                continue
            state = self._state(guild.id)
            night = is_night(now, settings['start_hour'], settings['end_hour'])
            try:
                if night and not state['active']:
                    await self._activate(guild, settings, state)
                elif not night and state['active']:
                    await self._deactivate(guild, settings, state)
            except Exception as _ex:
                log.error('night_mode: ошибка петли на %s: %s', guild.id, _ex)

    @watch_loop.before_loop
    async def _wait_ready(self):
        await self.bot.wait_until_ready()

    # ---- вкатиться в ночь ----
    async def _activate(self, guild, settings, state):
        done_slow, done_lock = 0, 0
        for ch in channels_for_action(guild, settings):
            cid = str(ch.id)
            if settings['slowmode_seconds'] > 0:
                state['slow_before'][cid] = ch.slowmode_delay
                try:
                    await ch.edit(slowmode_delay=settings['slowmode_seconds'],
                                  reason='Ночной режим: слоумод')
                    done_slow += 1
                except (discord.Forbidden, discord.HTTPException) as _ex:
                    log.debug('night_mode: слоумод #%s не применился: %s', ch.id, _ex)
            if settings['lock_channels']:
                ow = ch.overwrites_for(guild.default_role)
                state['lock_before'][cid] = {'send_messages': ow.send_messages}
                ow.send_messages = False
                try:
                    await ch.set_permissions(guild.default_role, overwrite=ow,
                                             reason='Ночной режим: лок')
                    done_lock += 1
                except (discord.Forbidden, discord.HTTPException) as _ex:
                    log.debug('night_mode: лок #%s не применился: %s', ch.id, _ex)
        state['active'] = True
        state['since'] = datetime.now(UTC).isoformat()
        self._save_state(guild.id, state)
        log.info('night_mode: ночь на %s — слоумод %s, лок %s',
                 guild.id, done_slow, done_lock)
        await self._report(guild, settings, night=True,
                           detail=(f'Слоумод на {tf.spell(done_slow, "канале", "каналах", "каналах")}'
                                   + (f', лок на {done_lock}' if settings['lock_channels'] else '')))

    async def _deactivate(self, guild, settings, state):
        restored_s, restored_l = 0, 0
        for ch in channels_for_action(guild, settings):
            cid = str(ch.id)
            if cid in state['slow_before']:
                try:
                    await ch.edit(slowmode_delay=state['slow_before'][cid],
                                  reason='Ночной режим: утро, слоумод возвращён')
                    restored_s += 1
                except (discord.Forbidden, discord.HTTPException) as _ex:
                    log.debug('night_mode: слоумод #%s не вернулся: %s', ch.id, _ex)
            if cid in state['lock_before']:
                ow = ch.overwrites_for(guild.default_role)
                ow.send_messages = state['lock_before'][cid].get('send_messages')
                try:
                    await ch.set_permissions(guild.default_role, overwrite=ow,
                                             reason='Ночной режим: утро, лок снят')
                    restored_l += 1
                except (discord.Forbidden, discord.HTTPException) as _ex:
                    log.debug('night_mode: лок #%s не снялся: %s', ch.id, _ex)
        self._save_state(guild.id, empty_state())
        log.info('night_mode: утро на %s — всё возвращено (%s/%s)',
                 guild.id, restored_s, restored_l)
        await self._report(guild, settings, night=False,
                           detail=f'Каналы возвращены к дневным настройкам ({restored_s})')

    async def _report(self, guild, settings, night, detail):
        cid = settings.get('report_channel_id')
        channel = guild.get_channel(cid) if cid else guild.system_channel
        if channel is None:
            return
        embed = discord.Embed(
            title='Ночной режим: наступила ночь' if night else 'Ночной режим: наступило утро',
            description=detail,
            color=COLOR_NIGHT if night else COLOR_DAY,
            timestamp=datetime.now(UTC),
        )
        try:
            await channel.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException) as _ex:
            log.debug('night_mode: репорт на %s не ушёл: %s', guild.id, _ex)

    # ---- команды ----
    @commands.hybrid_group(name='ночь', aliases=['night', 'nightmode'],
                           description='Ночной режим сервера')
    @commands.has_permissions(manage_guild=True)
    async def grp(self, ctx):
        if ctx.invoked_subcommand is None:
            await self._show_status(ctx)

    @grp.command(name='вкл', description='Включить ночной режим')
    async def cmd_on(self, ctx):
        s = self._settings(ctx.guild.id)
        s['enabled'] = True
        self._save_settings(ctx.guild.id, s)
        await ctx.reply(f'Ночной режим **включён** — окно {window_text(s)}.',
                        mention_author=False)

    @grp.command(name='выкл', description='Выключить ночной режим')
    async def cmd_off(self, ctx):
        s = self._settings(ctx.guild.id)
        s['enabled'] = False
        self._save_settings(ctx.guild.id, s)
        # сразу же деактивируем, если посреди ночи всё выключили
        state = self._state(ctx.guild.id)
        if state['active']:
            await self._deactivate(ctx.guild, s, state)
        await ctx.reply('Ночной режим **выключен**.', mention_author=False)

    @grp.command(name='окно', description='Часы: /ночь окно 23 7')
    async def cmd_window(self, ctx, начало: int, конец: int):
        if not (0 <= начало < 24 and 0 <= конец < 24) or начало == конец:
            await ctx.reply('Часы: два разных числа 0–23, напр. `/ночь окно 23 7`.',
                            mention_author=False)
            return
        s = self._settings(ctx.guild.id)
        s['start_hour'], s['end_hour'] = начало, конец
        self._save_settings(ctx.guild.id, s)
        await ctx.reply(f'Окно ночи: **{window_text(s)}**.', mention_author=False)

    @grp.command(name='слоумод', description='Слоумод ночью (0 — не трогать)')
    async def cmd_slow(self, ctx, сек: int):
        if not 0 <= сек <= 21600:
            await ctx.reply('Слоумод: 0–21600 секунд.', mention_author=False)
            return
        s = self._settings(ctx.guild.id)
        s['slowmode_seconds'] = сек
        self._save_settings(ctx.guild.id, s)
        await ctx.reply(f'Ночной слоумод: **{сек} сек**.' if сек else
                        'Слоумод ночью не применяется.', mention_author=False)

    @grp.command(name='лок', description='Закрывать каналы ночью: вкл|выкл')
    async def cmd_lock(self, ctx, режим: str):
        режим = режим.strip().lower()
        if режим not in ('вкл', 'выкл'):
            await ctx.reply('Режим: `вкл` или `выкл`.', mention_author=False)
            return
        s = self._settings(ctx.guild.id)
        s['lock_channels'] = режим == 'вкл'
        self._save_settings(ctx.guild.id, s)
        await ctx.reply(f'Лок каналов ночью: **{"да" if s["lock_channels"] else "нет"}**.',
                        mention_author=False)

    @grp.command(name='исключить', description='Канал-исключение (повторно — вернуть)')
    async def cmd_exempt(self, ctx, канал: discord.TextChannel):
        s = self._settings(ctx.guild.id)
        if канал.id in s['exempt_channels']:
            s['exempt_channels'].remove(канал.id)
            what = 'убран из исключений'
        else:
            s['exempt_channels'].append(канал.id)
            what = 'добавлен в исключения'
        self._save_settings(ctx.guild.id, s)
        await ctx.reply(f'{канал.mention} {what}.', mention_author=False)

    @grp.command(name='канал', description='Куда писать «ночь/утро»')
    async def cmd_report(self, ctx, канал: discord.TextChannel = None):
        s = self._settings(ctx.guild.id)
        s['report_channel_id'] = канал.id if канал else 0
        self._save_settings(ctx.guild.id, s)
        await ctx.reply(f'Репорты ночного режима: {канал.mention if канал else "авто"}.',
                        mention_author=False)

    @grp.command(name='статус', description='Настройки и состояние')
    async def cmd_status(self, ctx):
        await self._show_status(ctx)

    async def _show_status(self, ctx):
        s = self._settings(ctx.guild.id)
        st = self._state(ctx.guild.id)
        night_now = is_night(datetime.now(UTC), s['start_hour'], s['end_hour'])
        lines = plan_settings_lines(s)
        lines.append(f"Сейчас: {'ночь, режим активен' if st['active'] else ('ночь (пауза — режим выключен)' if night_now else 'день')}")
        embed = discord.Embed(title='Ночной режим — статус',
                              description='\n'.join('• ' + x for x in lines),
                              color=COLOR_NIGHT if st['active'] else COLOR_DAY)
        await ctx.reply(embed=embed, mention_author=False)


async def setup(bot):
    await bot.add_cog(NightMode(bot))
