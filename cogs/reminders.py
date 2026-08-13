# -*- coding: utf-8 -*-
"""Напоминания (Reminders Cog)
=============================
- /напомни <когда> <текст>   — «через 10м», «18:30», «2026-08-20 12:00»
- /напоминания               — ваши активные напоминания
- /напомотмена <id>          — отменить своё напоминание

Хранение — SQLite через GuildData('reminders') (никаких JSON-файлов).
Доставка — в канал, где создано; если канал недоступен — в личку.
Повторяющиеся напоминания: «каждые 24ч ...» — repeat_seconds в записи.

Все метки времени aware UTC. Разбор «когда» — services/text_format.
"""
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands, tasks

from db import GuildData
from logger import get_logger
from services import text_format as tf

log = get_logger("reminders")

UTC = timezone.utc
MAX_PER_USER = 25
MAX_TEXT = 300
COLOR = 0x5865F2


# ─── чистые функции над состоянием (покрыты тестом) ─────────────────────────

def empty_state():
    return {'next_id': 1, 'items': []}


def create_reminder(state, user_id, channel_id, text, when_text, now,
                    user_name=''):
    """Разобрать срок и добавить запись. Возвращает (item, ошибка)."""
    text = str(text or '').strip()
    if not text:
        return None, 'пустой текст напоминания'
    if len(text) > MAX_TEXT:
        return None, f'текст длиннее {MAX_TEXT} символов'
    active = [i for i in state['items']
              if i['user_id'] == user_id and not i.get('done')]
    if len(active) >= MAX_PER_USER:
        return None, f'лимит: не больше {MAX_PER_USER} активных напоминаний'
    due = tf.parse_deadline(when_text, now)
    if due is None:
        return None, ('не понял срок «' + str(when_text)[:30] +
                      '» — примеры: «10м», «через 2ч», «18:30», «2026-08-20 12:00»')
    item = {
        'id': state['next_id'],
        'user_id': user_id,
        'user_name': user_name,
        'channel_id': channel_id,
        'text': text,
        'due_at': due.isoformat(),
        'created_at': now.isoformat(),
        'repeat_seconds': None,
        'done': False,
    }
    state['next_id'] += 1
    state['items'].append(item)
    return item, None


_REPEAT_WORD_SECONDS = {
    'минуту': 60, 'час': 3600, 'день': 86400, 'неделю': 604800,
    'месяц': 2592000, 'год': 31536000,
}


def parse_repeat(text):
    """'каждые 24ч отчёт' / 'каждый день зарядка' / 'каждые 2 часа вода'
    -> (секунды повтора, остаток текста). Без маркера — (None, исходник)."""
    import re as _re
    text = str(text or '').strip()
    low = text.lower()
    for marker in ('каждые ', 'каждый ', 'каждую '):
        if not low.startswith(marker):
            continue
        rest = text[len(marker):].strip()
        # 1) число + единица словом: '2 часа вода' / '3 дня отчёт'
        m = _re.match(r'^(\d+)\s+([a-zа-яё]+)\b\s*(.*)$', rest, _re.IGNORECASE)
        if m:
            seconds = tf.parse_duration(f'{m.group(1)}{m.group(2)}')
            if seconds:
                return seconds, (m.group(3) or 'напоминание').strip()
        # 2) слитно: '24ч отчёт' / '30м'
        m = _re.match(r'^(\d+[a-zа-яё]+)\b\s*(.*)$', rest, _re.IGNORECASE)
        if m:
            seconds = tf.parse_duration(m.group(1))
            if seconds:
                return seconds, (m.group(2) or 'напоминание').strip()
        # 3) голое слово: 'день зарядка' / 'час пик'
        parts = rest.split(None, 1)
        if parts:
            seconds = _REPEAT_WORD_SECONDS.get(parts[0].lower())
            if seconds:
                body = parts[1] if len(parts) > 1 else 'напоминание'
                return seconds, body
    return None, text


def due_items(state, now):
    """Записи, которые пора доставить (due_at <= now, не done)."""
    out = []
    for item in state['items']:
        if item.get('done'):
            continue
        due = _parse_iso(item.get('due_at'))
        if due and due <= now:
            out.append(item)
    return out


def mark_delivered(state, item, now):
    """Пометить доставленным; повторяющееся — перенести вперёд."""
    repeat = item.get('repeat_seconds')
    if repeat:
        due = _parse_iso(item.get('due_at')) or now
        while due <= now:
            due = due + timedelta(seconds=int(repeat))
        item['due_at'] = due.isoformat()
    else:
        item['done'] = True


def cancel_item(state, item_id, user_id):
    """Отмена своей записи. True, если нашлась и была активной."""
    for item in state['items']:
        if item['id'] == item_id and item['user_id'] == user_id and not item.get('done'):
            item['done'] = True
            return True
    return False


def user_items(state, user_id):
    """Активные записи пользователя, ближайшие первыми."""
    rows = [i for i in state['items']
            if i['user_id'] == user_id and not i.get('done')]
    return sorted(rows, key=lambda i: i.get('due_at', ''))


def _parse_iso(text):
    try:
        dt = datetime.fromisoformat(str(text))
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def fmt_reminder_line(item, now):
    """'#3 · через 2 ч · каждые 1 д · текст' — строка для списка."""
    due = _parse_iso(item.get('due_at'))
    when = tf.rel_time(due, now) if due else '?'
    repeat = item.get('repeat_seconds')
    tail = f' · каждые {tf.fmt_seconds(repeat)}' if repeat else ''
    return f"**#{item['id']}** · {when}{tail} · {item['text'][:80]}"


# ─── ког ────────────────────────────────────────────────────────────────────

class Reminders(commands.Cog):
    """Личные напоминания с доставкой в канал или личку."""

    def __init__(self, bot):
        self.bot = bot
        self.db = GuildData('reminders')
        self.deliver_loop.start()

    def cog_unload(self):
        self.deliver_loop.cancel()

    # ---- хранилище ----
    def _load(self, guild_id):
        return self.db.get(guild_id, 'state', empty_state()) or empty_state()

    def _save(self, guild_id, state):
        self.db.set(guild_id, 'state', state)

    # ---- команды ----
    @commands.hybrid_command(name='напомни', aliases=['remind', 'remindme'],
                             description='Напоминание: /напомни "через 10м" текст')
    async def cmd_remind(self, ctx, когда: str, *, текст: str):
        now = datetime.now(UTC)
        guild_id = ctx.guild.id if ctx.guild else 0
        state = self._load(guild_id)

        repeat, body = parse_repeat(текст)
        when_text = когда.lower().replace('через ', '', 1)
        item, err = create_reminder(state, ctx.author.id,
                                    ctx.channel.id if ctx.channel else 0,
                                    body, when_text, now,
                                    user_name=str(ctx.author))
        if err:
            await ctx.reply(f'Не получилось: {err}.', mention_author=False)
            return
        if repeat:
            item['repeat_seconds'] = repeat
        self._save(guild_id, state)

        embed = discord.Embed(
            title='Напоминание создано',
            description=(
                f'**#{item["id"]}** — {tf.rel_time(_parse_iso(item["due_at"]), now)}\n'
                f'{item["text"][:200]}'
                + (f'\nПовтор: каждые {tf.fmt_seconds(repeat)}' if repeat else '')
            ),
            color=COLOR,
        )
        await ctx.reply(embed=embed, mention_author=False)

    @commands.hybrid_command(name='напоминания', aliases=['reminders'],
                             description='Ваши активные напоминания')
    async def cmd_list(self, ctx):
        now = datetime.now(UTC)
        guild_id = ctx.guild.id if ctx.guild else 0
        rows = user_items(self._load(guild_id), ctx.author.id)
        if not rows:
            await ctx.reply('Активных напоминаний нет. Создайте: '
                            '`/напомни "через 10м" выпить воды`.',
                            mention_author=False)
            return
        embed = discord.Embed(title='Ваши напоминания', color=COLOR,
                              description='\n'.join(
                                  tf.clamp_text(fmt_reminder_line(i, now), 200)
                                  for i in rows[:15]))
        if len(rows) > 15:
            embed.set_footer(text=f'и ещё {len(rows) - 15}')
        await ctx.reply(embed=embed, mention_author=False)

    @commands.hybrid_command(name='напомотмена', aliases=['remindcancel'],
                             description='Отменить напоминание по номеру')
    async def cmd_cancel(self, ctx, номер: int):
        guild_id = ctx.guild.id if ctx.guild else 0
        state = self._load(guild_id)
        if cancel_item(state, номер, ctx.author.id):
            self._save(guild_id, state)
            await ctx.reply(f'Напоминание **#{номер}** отменено.',
                            mention_author=False)
        else:
            await ctx.reply(f'Напоминание **#{номер}** не найдено среди ваших.',
                            mention_author=False)

    # ---- доставка ----
    @tasks.loop(seconds=15)
    async def deliver_loop(self):
        now = datetime.now(UTC)
        guild_ids = [g.id for g in self.bot.guilds] or [0]
        for guild_id in guild_ids:
            state = self._load(guild_id)
            items = due_items(state, now)
            if not items:
                continue
            changed = False
            for item in items:
                ok = await self._deliver(guild_id, item)
                if ok:
                    mark_delivered(state, item, now)
                    changed = True
            if changed:
                self._save(guild_id, state)

    @deliver_loop.before_loop
    async def _wait_ready(self):
        await self.bot.wait_until_ready()

    async def _deliver(self, guild_id, item):
        """Отправить напоминание: канал -> личка. False = не доставлено."""
        embed = discord.Embed(
            title='Напоминание',
            description=item['text'][:1000],
            color=COLOR,
        )
        due = _parse_iso(item.get('due_at'))
        if due:
            embed.timestamp = due
        user = self.bot.get_user(item['user_id'])
        mention = user.mention if user else f"<@{item['user_id']}>"

        channel = self.bot.get_channel(item.get('channel_id') or 0)
        if channel is not None:
            try:
                await channel.send(f'{mention}', embed=embed)
                return True
            except discord.Forbidden as _ex:
                # прав на канал нет — ниже пробуем личку
                log.debug('reminders: нет прав на канал %s: %s',
                          item.get('channel_id'), _ex)
            except discord.HTTPException as _ex:
                log.debug('reminders: канал %s недоступен: %s',
                          item.get('channel_id'), _ex)
        if user is None:
            try:
                user = await self.bot.fetch_user(item['user_id'])
            except (discord.NotFound, discord.HTTPException) as _ex:
                log.warning('reminders: пользователь %s не найден: %s',
                            item['user_id'], _ex)
                return False
        try:
            await user.send(embed=embed)
            return True
        except (discord.Forbidden, discord.HTTPException) as _ex:
            log.warning('reminders: ЛС закрыты у %s: %s', item['user_id'], _ex)
            return False


async def setup(bot):
    await bot.add_cog(Reminders(bot))
