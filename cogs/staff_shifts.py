# -*- coding: utf-8 -*-
"""Стафф-смены (Staff Shifts)
============================
Недельное расписание дежурств модераторов с автонапоминаниями: когда у
смотрящего начинается смена — бот пингует его в стафф-канале, когда
кончается — благодарит и называет следующего дежурного.

Хранилище: GuildData('staff_shifts')
  'shifts'   — {id: {user_id, weekday, start 'ЧЧ:ММ', end 'ЧЧ:ММ'}} (вечное расписание)
  'settings' — {channel_id, tz_offset} (канал анонсов, часовой пояс, по умолч. +3)
  '_marks'   — {id: {start: iso, end: iso}} служебные метки «уже напомнили»

Команды (группа /дежурства, префикс !дежурства):
  (без подкоманды) — расписание недели
  кто                      — кто сейчас дежурит и кто следующий
  назначить @user <день> <ЧЧ:ММ-ЧЧ:ММ>  — добавить смену (мод)
  снять <id>               — убрать смену (мод)
  канал [#канал]           — куда слать напоминания (мод)
  пояс <±N>                — часовой пояс расписания (мод)
"""
import random
import re
import string
from datetime import datetime, time, timedelta, timezone

import discord
from discord.ext import commands, tasks

from db import GuildData
from logger import get_logger
from services.text_format import fmt_seconds, plural_ru

log = get_logger('staff_shifts')
UTC = timezone.utc

WEEKDAYS_RU = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс']
WEEKDAYS_FULL_RU = ['понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота', 'воскресенье']
_WEEKDAY_ALIAS = {}
for _i, _short in enumerate(WEEKDAYS_RU):
    _WEEKDAY_ALIAS[_short] = _i
for _i, _full in enumerate(WEEKDAYS_FULL_RU):
    _WEEKDAY_ALIAS[_full] = _i
for _i, _en in enumerate(['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']):
    _WEEKDAY_ALIAS[_en] = _i

DEFAULT_TZ = 3  # МСК — дефолт для русскоязычного сервера
_RANGE_RE = re.compile(r'^\s*(\d{1,2})[:.](\d{2})\s*[-—]\s*(\d{1,2})[:.](\d{2})\s*$')


def parse_weekday(text):
    """'пн' | 'понедельник' | 'mon' -> 0..6; мусор -> None."""
    return _WEEKDAY_ALIAS.get(str(text or '').strip().lower())


def parse_time_range(text):
    """'18:00-22:30' -> (минуты_от_полуночи_старт, ..._конец). Конец позже старта —
    смена с переносом через полночь (22:00-02:00). Валидность: обе метки в сутках,
    разница не нулевая."""
    m = _RANGE_RE.match(str(text or ''))
    if not m:
        return None
    h1, m1, h2, m2 = (int(x) for x in m.groups())
    if not (0 <= h1 <= 23 and 0 <= m1 <= 59 and 0 <= h2 <= 23 and 0 <= m2 <= 59):
        return None
    start, end = h1 * 60 + m1, h2 * 60 + m2
    if start == end:
        return None
    return start, end


def fmt_time(minutes):
    """минуты от полуночи -> 'ЧЧ:ММ'."""
    return f'{minutes // 60:02d}:{minutes % 60:02d}'


def _shift_window(shift, civil_day, tz_offset):
    """Границы смены в aware-UTC для конкретной гражданской даты."""
    tz = timezone(timedelta(hours=tz_offset))
    s_min, e_min = shift['_minutes']
    start = datetime.combine(civil_day, time(s_min // 60, s_min % 60), tzinfo=tz).astimezone(UTC)
    end_day = civil_day if e_min > s_min else civil_day + timedelta(days=1)  # через полночь
    end = datetime.combine(end_day, time(e_min // 60, e_min % 60), tzinfo=tz).astimezone(UTC)
    return start, end


def attach_minutes(shift):
    """Копия смены с рассчитанными минутами (_minutes) — готовится к окнам."""
    rng = parse_time_range(f"{shift['start']}-{shift['end']}")
    enriched = dict(shift)
    enriched['_minutes'] = rng
    return enriched


def iter_windows(shifts, civil_day, tz_offset):
    """(shift, start, end) для всех смен, чьё начало попадает на civil_day."""
    for shift in shifts:
        if shift.get('weekday') != civil_day.weekday():
            continue
        enriched = attach_minutes(shift)
        if enriched['_minutes'] is None:
            continue
        start, end = _shift_window(enriched, civil_day, tz_offset)
        yield enriched, start, end


def active_shift(shifts, now, tz_offset):
    """(shift, start, end) текущей смены или None. Учитывает перенос через полночь
    (смотрим окна вчера и сегодня)."""
    local_now = now.astimezone(timezone(timedelta(hours=tz_offset)))
    for day in (local_now.date() - timedelta(days=1), local_now.date()):
        for shift, start, end in iter_windows(shifts, day, tz_offset):
            if start <= now < end:
                return shift, start, end
    return None


def next_shift(shifts, now, tz_offset):
    """(shift, start) ближайшей будущей смены (горизонт — 8 суток)."""
    local_now = now.astimezone(timezone(timedelta(hours=tz_offset)))
    best = None
    for back in range(9):
        day = local_now.date() + timedelta(days=back)
        for shift, start, _end in iter_windows(shifts, day, tz_offset):
            if start > now and (best is None or start < best[1]):
                best = (shift, start)
    return best


def week_table(shifts):
    """Неделя текстом: 'пн: <@id> 18:00–22:00 · …' (None-слоты — '—')."""
    by_day = {i: [] for i in range(7)}
    for s in shifts:
        wd = s.get('weekday')
        if isinstance(wd, int) and 0 <= wd <= 6:
            by_day[wd].append(s)
    lines = []
    for i in range(7):
        if not by_day[i]:
            lines.append(f'**{WEEKDAYS_RU[i]}** —')
            continue
        chunks = sorted(by_day[i], key=lambda s: (s['start'], s['end']))
        parts = [f'<@{s["user_id"]}> `{s["start"]}–{s["end"]}`' for s in chunks]
        lines.append(f'**{WEEKDAYS_RU[i]}** ' + ' · '.join(parts))
    return '\n'.join(lines)


def new_shift_id(existing):
    for _ in range(50):
        sid = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
        if sid not in existing:
            return sid
    return ''.join(random.choices(string.ascii_lowercase, k=8))


class StaffShifts(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = GuildData('staff_shifts')
        self._watcher.start()

    def cog_unload(self):
        self._watcher.cancel()

    # ── хранилище ──────────────────────────────────────────────────────

    def _shifts(self, guild_id):
        return self.db.get(guild_id, 'shifts', {}) or {}

    def _save_shifts(self, guild_id, shifts):
        self.db.set(guild_id, 'shifts', shifts)

    def _settings(self, guild_id):
        raw = self.db.get(guild_id, 'settings', {}) or {}
        return {'channel_id': raw.get('channel_id'), 'tz_offset': int(raw.get('tz_offset', DEFAULT_TZ))}

    def _marks(self, guild_id):
        return self.db.get(guild_id, '_marks', {}) or {}

    def _save_marks(self, guild_id, marks):
        self.db.set(guild_id, '_marks', marks)

    # ── цикл напоминаний (вся логика в check_cycle — тестируемо без сна) ──

    async def check_cycle(self, guild_id, now):
        """Одна итерация напоминаний для гильдии. Возвращает список событий
        [('start'|'end', shift, when), ...] — для отладки и тестов."""
        settings = self._settings(guild_id)
        raw = self._shifts(guild_id)
        if not raw:
            return []
        shifts = {}
        for sid, s in raw.items():
            enriched = dict(s)
            enriched['_id'] = sid
            shifts[sid] = enriched
        marks = self._marks(guild_id)
        channel = self.bot.get_channel(settings['channel_id']) if settings.get('channel_id') else None
        events = []
        dirty = False
        local_now = now.astimezone(timezone(timedelta(hours=settings['tz_offset'])))

        shift_list = list(shifts.values())
        for day in (local_now.date() - timedelta(days=1), local_now.date()):
            for shift, start, end in iter_windows(shift_list, day, settings['tz_offset']):
                mark = marks.setdefault(shift['_id'], {})
                if start <= now < end and mark.get('start') != start.isoformat():
                    mark['start'] = start.isoformat()
                    dirty = True
                    events.append(('start', shift, start))
                    if channel:
                        await channel.send(
                            f'Смена началась: <@{shift["user_id"]}> — дежурь до '
                            f'**{shift["end"]}** (пояс UTC{settings["tz_offset"]:+d}). '
                            f'Вопросы сервера — на тебе.'
                        )
                if now >= end and mark.get('start') == start.isoformat() and mark.get('end') != end.isoformat():
                    mark['end'] = end.isoformat()
                    dirty = True
                    events.append(('end', shift, end))
                    if channel:
                        nxt = next_shift(shift_list, now, settings['tz_offset'])
                        nxt_txt = ''
                        if nxt:
                            nshift, nstart = nxt
                            wait_s = int((nstart - now).total_seconds())
                            nxt_txt = (f' Следующая смена: <@{nshift["user_id"]}> '
                                       f'({WEEKDAYS_RU[nshift["weekday"]]} {nshift["start"]}, '
                                       f'через {fmt_seconds(wait_s)}).')
                        await channel.send(
                            f'Смена <@{shift["user_id"]}> завершена — спасибо за дежурство!{nxt_txt}'
                        )
        if dirty:
            self._save_marks(guild_id, marks)
        return events

    @tasks.loop(seconds=60)
    async def _watcher(self):
        now = datetime.now(UTC)
        for guild in list(self.bot.guilds):
            try:
                await self.check_cycle(guild.id, now)
            except Exception as e:
                log.debug(f'watcher: пропуск гильдии {guild.id}: {e}')

    @_watcher.before_loop
    async def _before_watcher(self):
        await self.bot.wait_until_ready()

    # ── команды ────────────────────────────────────────────────────────

    @commands.hybrid_group(name='дежурства', aliases=['shifts'], description='Расписание дежурств модераторов', fallback='расписание')
    async def grp(self, ctx):
        settings = self._settings(ctx.guild.id)
        shifts = list(self._shifts(ctx.guild.id).values())
        if not shifts:
            return await ctx.send(
                'Расписание пусто. Модератор добавляет смены так:\n'
                '`/дежурства назначить @user пт 18:00-22:00` — а бот сам пинганёт дежурного '
                'в начале смены и поблагодарит в конце.'
            )
        emb = discord.Embed(title='Дежурства — неделя', description=week_table(shifts), color=0x5B8CFF)
        chan_txt = f'<#{settings["channel_id"]}>' if settings.get('channel_id') else 'не задан (`/дежурства канал`)'
        emb.set_footer(text=f'Напоминания: {chan_txt} · пояс UTC{settings["tz_offset"]:+d}')
        await ctx.send(embed=emb)

    @grp.command(name='кто', aliases=['who'], description='Кто сейчас дежурит и кто следующий')
    async def who(self, ctx):
        now = datetime.now(UTC)
        settings = self._settings(ctx.guild.id)
        shifts = list(self._shifts(ctx.guild.id).values())
        cur = active_shift(shifts, now, settings['tz_offset'])
        nxt = next_shift(shifts, now, settings['tz_offset'])
        parts = []
        if cur:
            shift, _start, end = cur
            left_s = int((end - now).total_seconds())
            parts.append(f'Сейчас дежурит <@{shift["user_id"]}> — до конца смены {fmt_seconds(left_s)}.')
        else:
            parts.append('Сейчас никто не дежурит.')
        if nxt:
            nshift, nstart = nxt
            wait_s = int((nstart - now).total_seconds())
            parts.append(f'Следующая смена: <@{nshift["user_id"]}> — {WEEKDAYS_RU[nshift["weekday"]]} '
                         f'`{nshift["start"]}–{nshift["end"]}`, через {fmt_seconds(wait_s)}.')
        await ctx.send('\n'.join(parts))

    @grp.command(name='назначить', aliases=['add'], description='Смена: @user <день> <ЧЧ:ММ-ЧЧ:ММ>')
    @commands.has_permissions(manage_guild=True)
    async def assign(self, ctx, user: discord.Member, weekday: str, time_range: str):
        wd = parse_weekday(weekday)
        if wd is None:
            days = ', '.join(WEEKDAYS_RU)
            return await ctx.send(f'Не понял день «{weekday}». Пиши: {days} (или полностью).')
        rng = parse_time_range(time_range)
        if rng is None:
            return await ctx.send('Формат времени: `ЧЧ:ММ-ЧЧ:ММ` (например `18:00-22:00`; можно через полночь).')
        shifts = self._shifts(ctx.guild.id)
        # защита от дублей: тот же мод, тот же день и время — и так есть
        for s in shifts.values():
            if s['user_id'] == user.id and s['weekday'] == wd and s['start'] == fmt_time(rng[0]):
                return await ctx.send('Такая смена уже назначена (смотри `/дежурства`).')
        sid = new_shift_id(shifts)
        shifts[sid] = {
            'user_id': user.id,
            'weekday': wd,
            'start': fmt_time(rng[0]),
            'end': fmt_time(rng[1]),
            'added_by': str(ctx.author.id),
            'added_at': datetime.now(UTC).isoformat(),
        }
        self._save_shifts(ctx.guild.id, shifts)
        await ctx.send(
            f'Смена добавлена: <@{user.id}> — **{WEEKDAYS_RU[wd]}** `{fmt_time(rng[0])}–{fmt_time(rng[1])}` (id `{sid}`).'
        )

    @grp.command(name='снять', aliases=['del'], description='Убрать смену по id')
    @commands.has_permissions(manage_guild=True)
    async def revoke(self, ctx, shift_id: str):
        shifts = self._shifts(ctx.guild.id)
        shift = shifts.pop(shift_id.strip(), None)
        if not shift:
            return await ctx.send(f'Смена `{shift_id}` не найдена. Список id — в `/дежурства` (таблица недели).')
        self._save_shifts(ctx.guild.id, shifts)
        marks = self._marks(ctx.guild.id)
        marks.pop(shift_id, None)
        self._save_marks(ctx.guild.id, marks)
        await ctx.send(f'Смена снята: <@{shift["user_id"]}> — {WEEKDAYS_RU[shift["weekday"]]} `{shift["start"]}–{shift["end"]}`.')

    @grp.command(name='канал', aliases=['channel'], description='Куда слать напоминания о сменах')
    @commands.has_permissions(manage_guild=True)
    async def set_channel(self, ctx, channel: discord.TextChannel = None):
        st = self.db.get(ctx.guild.id, 'settings', {}) or {}
        st['channel_id'] = channel.id if channel else None
        self.db.set(ctx.guild.id, 'settings', st)
        if channel:
            await ctx.send(f'Напоминания о сменах — в {channel.mention}. Если канал убрать: `/дежурства канал` без аргумента.')
        else:
            await ctx.send('Канал напоминаний сброшен — расписание работает молча (только `/дежурства кто`).')

    @grp.command(name='пояс', aliases=['tz'], description='Часовой пояс расписания: ±N (МСК = 3)')
    @commands.has_permissions(manage_guild=True)
    async def set_tz(self, ctx, offset: int):
        if not (-12 <= offset <= 14):
            return await ctx.send('Пояс: от -12 до +14 (МСК = 3).')
        st = self.db.get(ctx.guild.id, 'settings', {}) or {}
        st['tz_offset'] = offset
        self.db.set(ctx.guild.id, 'settings', st)
        await ctx.send(f'Часовой пояс расписания: **UTC{offset:+d}**.')


async def setup(bot):
    await bot.add_cog(StaffShifts(bot))
