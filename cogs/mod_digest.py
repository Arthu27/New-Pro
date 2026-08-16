# -*- coding: utf-8 -*-
"""Мод-дайджест (Mod Digest Cog)
===============================
Еженедельная сводка активности модерации для админов сервера: сколько
мутов/банов/варнов за период, кто из модераторов активнее, как меняется
нагрузка. Источник — data/audit_log.json (тот же, что кормит панель).

- /дайджест [дней]             — мгновенная сводка за N дней (по умолч. 7)
- /дайджест вкл #канал [час]   — автоматическая сводка раз в неделю
- /дайджест выкл               — выключить автоматическую

Настройки — SQLite (GuildData 'mod_digest'). Метки — aware UTC.
"""
import json
import os
from collections import Counter
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands, tasks

from db import GuildData
from logger import get_logger
from services import text_format as tf

log = get_logger("mod_digest")

UTC = timezone.utc
COLOR = 0x5865F2
AUDIT_PATH = 'data/audit_log.json'

DEFAULT_SETTINGS = {
    'enabled': False,
    'channel_id': 0,
    'hour_utc': 18,          # в какой час UTC слать сводку
    'last_sent': None,       # ISO даты последней отправки
}

# разговорные названия категорий для сводки
CATEGORY_NAMES = {
    'mod': 'Мод-действия',
    'warn': 'Предупреждения',
    'proof': 'Демки',
    'ticket': 'Тикеты',
    'join': 'Заходы/уходы',
    'msg': 'Сообщения',
    'voice': 'Голосовая активность',
}


# ─── чистые функции (покрыты тестом) ────────────────────────────────────────

_BAR_FULL, _BAR_EMPTY, _BAR_W = '▓', '░', 10
_SPARKS = '▁▂▃▄▅▆▇█'
RHYTHM_DAYS = 14  # шире — эмбед поплывёт


def mini_bar(share, width=_BAR_W):
    """Доля 0..1 -> '▓▓▓░░░░░░░' (фикс-ширина; все поля эмбеда остаются monospace-ровными)."""
    try:
        share = max(0.0, min(1.0, float(share)))
    except (TypeError, ValueError):
        share = 0.0
    full = int(round(share * width))
    return _BAR_FULL * full + _BAR_EMPTY * (width - full)


def sparkline(counts):
    """Список чисел -> '▁▃█▂…' относительно максимума; пусто/одни нули -> ''."""
    vals = [int(c or 0) for c in counts or []]
    if not vals or max(vals) <= 0:
        return ''
    top = max(vals)
    return ''.join(_SPARKS[min(len(_SPARKS) - 1, int(c * (len(_SPARKS) - 1) / top))] for c in vals)


def rhythm_series(per_day, days, now=None):
    """Ряд событий по дням за последние min(days, RHYTHM_DAYS) суток (слева старое)."""
    now = now or datetime.now(UTC)
    window = max(1, min(int(days or 7), RHYTHM_DAYS))
    counts = []
    for back in range(window - 1, -1, -1):
        key = (now - timedelta(days=back)).date().isoformat()
        counts.append(int((per_day or {}).get(key, 0)))
    return counts


def merge_settings(raw):
    out = dict(DEFAULT_SETTINGS)
    if isinstance(raw, dict):
        for key in out:
            if key in raw:
                out[key] = raw[key]
    try:
        out['hour_utc'] = int(out['hour_utc']) % 24
    except (TypeError, ValueError):
        out['hour_utc'] = DEFAULT_SETTINGS['hour_utc']
    return out


def parse_ts(text):
    """ISO метка из audit_log -> aware datetime или None (мусор пропускаем)."""
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(str(text))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def aggregate_digest(events, days=7, now=None):
    """Сводка по событиям за days дней. Чистая функция — сердце дайджеста.

    Возвращает {'total', 'per_category', 'top_actions', 'top_mods',
                'per_day', 'busiest_day'}.
    """
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    try:
        days = max(1, int(days or 7))
    except (TypeError, ValueError):
        days = 7
    since = now - timedelta(days=days)

    per_category = Counter()
    per_action = Counter()
    per_mod = Counter()
    per_day = Counter()
    total = 0

    for ev in events or []:
        ts = parse_ts(ev.get('timestamp'))
        if ts is None or ts < since:
            continue
        total += 1
        category = str(ev.get('category') or 'прочее')
        per_category[category] += 1
        per_action[str(ev.get('action') or '?')] += 1
        mod = str(ev.get('mod_name') or '').strip()
        if mod:
            per_mod[mod] += 1
        per_day[ts.date().isoformat()] += 1

    busiest_day = per_day.most_common(1)[0] if per_day else (None, 0)
    return {
        'total': total,
        'per_category': per_category.most_common(8),
        'top_actions': per_action.most_common(8),
        'top_mods': per_mod.most_common(5),
        'per_day': dict(per_day),
        'busiest_day': busiest_day,
    }


def digest_embed_dict(summary, days, guild_name='сервер', now=None):
    """Готовый payload для эмбеда (строки собраны — удобно тестировать)."""
    total = summary['total'] or 0
    cat_lines = []
    for cat, n in summary['per_category']:
        name = CATEGORY_NAMES.get(cat, cat)
        share = (n / total) if total else 0.0
        cat_lines.append(f'• {name}: **{n}** `{mini_bar(share)}` {round(share * 100)}%')
    mod_lines = [f'• {name} — {tf.spell(n, "действие", "действия", "действий")}'
                 for name, n in summary['top_mods']]
    busiest = summary['busiest_day']
    busiest_txt = f"{busiest[0]} ({busiest[1]})" if busiest[0] else '—'
    spark = sparkline(rhythm_series(summary.get('per_day'), days, now))
    return {
        'title': f'Мод-дайджест · {guild_name} · {tf.spell(days, "день", "дня", "дней")}',
        'fields': [
            ('Всего событий', str(total)),
            ('По категориям', '\n'.join(cat_lines) or '—'),
            ('Активные модераторы', '\n'.join(mod_lines) or '—'),
            ('Самый горячий день', busiest_txt),
            ('Ритм по дням', spark or '—'),
        ],
    }


def load_events(guild_id, path=AUDIT_PATH):
    """События гильдии из audit_log.json; битый файл/нет файла -> []."""
    if not os.path.exists(path):
        return []
    try:
        with open(path, 'r', encoding='utf-8') as fp:
            data = json.load(fp)
    except (json.JSONDecodeError, OSError) as _ex:
        log.warning('mod_digest: не прочитал %s: %s', path, _ex)
        return []
    rows = data.get(str(guild_id), [])
    return rows if isinstance(rows, list) else []


def should_send(settings, now=None):
    """Пора ли слать автодайджест: включён + нужный час + неделя прошла."""
    s = merge_settings(settings)
    if not s['enabled'] or not s['channel_id']:
        return False
    now = now or datetime.now(UTC)
    if now.hour != s['hour_utc']:
        return False
    last = parse_ts(s.get('last_sent'))
    if last is None:
        return True
    return (now - last) >= timedelta(days=6, hours=20)


# ─── ког ────────────────────────────────────────────────────────────────────

class ModDigest(commands.Cog):
    """Еженедельная сводка модерации для админов."""

    def __init__(self, bot):
        self.bot = bot
        self.db = GuildData('mod_digest')
        self.digest_loop.start()

    def cog_unload(self):
        self.digest_loop.cancel()

    def _settings(self, guild_id):
        return merge_settings(self.db.get(guild_id, 'settings', {}))

    def _save(self, guild_id, settings):
        self.db.set(guild_id, 'settings', settings)

    # ---- команды ----
    @commands.hybrid_group(name='дайджест', aliases=['digest'],
                           description='Сводка модерации за период')
    async def grp(self, ctx):
        if ctx.invoked_subcommand is None:
            await self._send_digest(ctx, ctx.guild, 7, reply=True)

    @grp.command(name='период', description='Сводка за N дней: /дайджест период 14')
    async def cmd_period(self, ctx, дней: int = 7):
        await self._send_digest(ctx, ctx.guild, дней, reply=True)

    @grp.command(name='вкл', description='Автодайджест раз в неделю')
    @commands.has_permissions(manage_guild=True)
    async def cmd_on(self, ctx, канал: discord.TextChannel, час: int = 18):
        if not 0 <= час < 24:
            await ctx.reply('Час — число 0–23 (UTC).', mention_author=False)
            return
        s = self._settings(ctx.guild.id)
        s.update({'enabled': True, 'channel_id': канал.id, 'hour_utc': час})
        self._save(ctx.guild.id, s)
        await ctx.reply(f'Автодайджест включён: {канал.mention}, еженедельно '
                        f'в {час:02d}:00 UTC.', mention_author=False)

    @grp.command(name='выкл', description='Выключить автодайджест')
    @commands.has_permissions(manage_guild=True)
    async def cmd_off(self, ctx):
        s = self._settings(ctx.guild.id)
        s['enabled'] = False
        self._save(ctx.guild.id, s)
        await ctx.reply('Автодайджест выключен.', mention_author=False)

    # ---- отправка ----
    async def _send_digest(self, ctx_or_channel, guild, days, reply=False):
        days = max(1, min(90, int(days or 7)))
        events = load_events(guild.id)
        summary = aggregate_digest(events, days=days)
        payload = digest_embed_dict(summary, days, guild.name)
        embed = discord.Embed(title=payload['title'], color=COLOR,
                              timestamp=datetime.now(UTC))
        for name, value in payload['fields']:
            embed.add_field(name=name, value=value[:1024],
                            inline=name in ('Всего событий', 'Самый горячий день'))
        if summary['total'] == 0:
            embed.description = ('Событий за период нет. Дайджест читает '
                                 'audit_log (панель логов) — возможно, лог '
                                 'просто пуст.')
        if reply and hasattr(ctx_or_channel, 'reply'):
            await ctx_or_channel.reply(embed=embed, mention_author=False)
        else:
            await ctx_or_channel.send(embed=embed)

    # ---- автоматическая рассылка ----
    @tasks.loop(minutes=30)
    async def digest_loop(self):
        now = datetime.now(UTC)
        for guild in list(self.bot.guilds):
            s = self._settings(guild.id)
            if not should_send(s, now):
                continue
            channel = guild.get_channel(s['channel_id'])
            if channel is None:
                continue
            try:
                await self._send_digest(channel, guild, 7)
            except (discord.Forbidden, discord.HTTPException) as _ex:
                log.error('mod_digest: отправка на %s не удалась: %s', guild.id, _ex)
                continue
            s['last_sent'] = now.isoformat()
            self._save(guild.id, s)

    @digest_loop.before_loop
    async def _wait_ready(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(ModDigest(bot))
