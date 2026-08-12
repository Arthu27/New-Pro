"""
Night Summary — автоматическая ежедневная сводка.

Каждую ночь в 00:00 (по выбранному часовому поясу) бот рисует
«золотую карту дня» и отправляет её в канал логов:

  • варны / баны / кики / мьюты за день
  • сколько человек попало в Tag Jail
  • сколько ghost-ping'ов поймано
  • ошибок бота за день (anti-crash)
  • модератор дня

Предпросмотр: /summary now (админ).
"""

from logger import get_logger

_log = get_logger("night_summary")

import os
import io
import json
import asyncio
import sqlite3
import time
import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timezone, timedelta

from PIL import Image, ImageDraw, ImageFont

from logger import get_logger

log = get_logger("night_summary")

STATE_PATH = 'data/night_summary.json'

GOLD = 0xD4AF37
DIVIDER = "✦ ───────────────────── ✦"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = os.path.join(ROOT, 'assets', 'fonts')
FONT_B = os.path.join(FONTS, 'Bold.ttf')
FONT_R = os.path.join(FONTS, 'Regular.ttf')

# Палитра карты (тёмно-синий + золото)
C_BG_TOP = (10, 16, 30)
C_BG_BOT = (16, 26, 48)
C_GOLD = (212, 175, 55)
C_GOLD_SOFT = (150, 122, 44)
C_TEXT = (236, 238, 244)
C_DIM = (140, 148, 165)
C_CELL = (255, 255, 255, 6)

_font_cache = {}


def _font(bold: bool, size: int):
    key = (bold, size)
    f = _font_cache.get(key)
    if f is None:
        try:
            f = ImageFont.truetype(FONT_B if bold else FONT_R, size)
        except Exception:
            f = ImageFont.load_default()
        _font_cache[key] = f
    return f


def _load_state():
    try:
        if os.path.exists(STATE_PATH):
            with open(STATE_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as _ex:
        _log.debug("_load_state(): подавлено: %s", _ex)
    return {}


def _save_state(data):
    try:
        os.makedirs('data', exist_ok=True)
        tmp = STATE_PATH + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, STATE_PATH)
    except Exception as e:
        log.error(f"[SVODKA] ошибка записи: {e}")


def _parse_ts(v) -> float:
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return datetime.fromisoformat(str(v).replace('Z', '+00:00')).timestamp()
    except Exception:
        return 0.0


class NightSummary(commands.Cog):
    """Ежедневная автоматическая сводка сервера (00:00)."""

    def __init__(self, bot):
        self.bot = bot
        self._state = _load_state()
        self._fails = {}   # gid -> (попыток, monotonic-ts) — анти-спам ретраев

    def cfg(self, guild_id: int) -> dict:
        c = {'enabled': True, 'channel_id': 0, 'tz_offset': 3, 'last_date': ''}
        c.update(self._state.get(str(guild_id), {}))
        return c

    def set_cfg(self, guild_id: int, key: str, value):
        self._state.setdefault(str(guild_id), {})[key] = value
        _save_state(self._state)

    async def cog_load(self):
        if not self._loop.is_running():
            self._loop.start()

    async def cog_unload(self):
        self._loop.cancel()

    # ────────────────────────────────────────────────────────────
    # Сбор статистики за день
    # ────────────────────────────────────────────────────────────
    def collect_day(self, guild_id: int, day: datetime, tz_offset: int) -> dict:
        """Статистика сервера за календарный день (в локальной зоне)."""
        day_key = day.strftime('%Y-%m-%d')

        def in_day(ts: float) -> bool:
            if not ts:
                return False
            local = datetime.fromtimestamp(ts, tz=timezone.utc) + timedelta(hours=tz_offset)
            return local.strftime('%Y-%m-%d') == day_key

        stats = {
            'warns': 0, 'bans': 0, 'kicks': 0, 'mutes': 0,
            'tagjail': 0, 'ghost': 0, 'errors': 0,
            'top_mod_id': 0, 'top_mod_count': 0,
        }
        mod_counter = {}

        # 1) Дела модерации (mod_data.json)
        try:
            with open('data/mod_data.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
            for c in data.get('cases', {}).get(str(guild_id), []):
                ts = _parse_ts(c.get('timestamp'))
                if not in_day(ts):
                    continue
                act = str(c.get('action', '')).lower()
                if act == 'warn':
                    stats['warns'] += 1
                elif act == 'ban':
                    stats['bans'] += 1
                elif act == 'kick':
                    stats['kicks'] += 1
                elif act in ('timeout', 'mute', 'vmute'):
                    stats['mutes'] += 1
                mid = str(c.get('mod_id') or '')
                if mid and mid not in ('0', 'None'):
                    mod_counter[mid] = mod_counter.get(mid, 0) + 1
        except Exception as _ex:
            _log.debug("collect_day(): подавлено: %s", _ex)

        # 2) Варны из SQLite
        try:
            from config import Config
            conn = sqlite3.connect(Config.DB_PATH)
            cur = conn.execute(
                "SELECT value FROM guild_data WHERE namespace='warnings' AND guild_id=?",
                (str(guild_id),))
            for (val,) in cur.fetchall():
                try:
                    warns = json.loads(val)
                except Exception as _ex:
                    _log.debug("collect_day(): подавлено: %s", _ex)
                    continue
                for w in (warns if isinstance(warns, list) else []):
                    ts = _parse_ts(w.get('timestamp'))
                    if in_day(ts):
                        stats['warns'] += 1
                        mid = str(w.get('mod_id') or '')
                        if mid and mid not in ('0', 'None'):
                            mod_counter[mid] = mod_counter.get(mid, 0) + 1
            conn.close()
        except Exception as _ex:
            _log.debug("collect_day(): подавлено: %s", _ex)

        # 3) Временные наказания
        try:
            with open('data/temp_history.json', 'r', encoding='utf-8') as f:
                hist = json.load(f)
            for h in (hist if isinstance(hist, list) else []):
                if str(h.get('guild_id')) != str(guild_id):
                    continue
                ts = _parse_ts(h.get('timestamp') or h.get('ts'))
                if in_day(ts):
                    stats['mutes'] += 1
                    mid = str(h.get('mod_id') or '')
                    if mid and mid not in ('0', 'None'):
                        mod_counter[mid] = mod_counter.get(mid, 0) + 1
        except Exception as _ex:
            _log.debug("collect_day(): подавлено: %s", _ex)

        # 4) Tag Jail
        try:
            with open('data/tag_jailed.json', 'r', encoding='utf-8') as f:
                jailed = json.load(f)
            for rec in jailed.get(str(guild_id), {}).values():
                if in_day(_parse_ts(rec.get('since'))):
                    stats['tagjail'] += 1
        except Exception as _ex:
            _log.debug("collect_day(): подавлено: %s", _ex)

        # 5) Ghost-ping'и из аудит-лога
        try:
            with open('data/audit_log.json', 'r', encoding='utf-8') as f:
                audit = json.load(f)
            for ev in audit.get(str(guild_id), []):
                if ev.get('action') == 'Ghost Ping' and in_day(_parse_ts(ev.get('timestamp'))):
                    stats['ghost'] += 1
        except Exception as _ex:
            _log.debug("collect_day(): подавлено: %s", _ex)

        # 6) Ошибки бота за день (anti-crash, глобально)
        try:
            with open('data/anticrash_stats.json', 'r', encoding='utf-8') as f:
                ac = json.load(f)
            stats['errors'] = int((ac.get('daily') or {}).get(day_key, 0))
        except Exception:
            stats['errors'] = 0

        if mod_counter:
            top = max(mod_counter.items(), key=lambda x: x[1])
            stats['top_mod_id'] = int(top[0]) if top[0].isdigit() else 0
            stats['top_mod_count'] = top[1]
        return stats

    # ────────────────────────────────────────────────────────────
    # Отрисовка карты
    # ────────────────────────────────────────────────────────────
    def render_card(self, guild: discord.Guild, day: datetime, stats: dict) -> io.BytesIO:
        S = 2  # суперсэмплинг
        W, H = 980 * S, 560 * S
        img = Image.new('RGB', (W, H), C_BG_TOP)
        d = ImageDraw.Draw(img, 'RGBA')

        # Вертикальный градиент
        for y in range(H):
            t = y / max(1, H - 1)
            d.line([(0, y), (W, y)],
                   fill=tuple(int(C_BG_TOP[i] + (C_BG_BOT[i] - C_BG_TOP[i]) * t) for i in range(3)))

        # Двойная золотая рамка
        d.rectangle([14 * S, 14 * S, W - 14 * S, H - 14 * S], outline=C_GOLD, width=2 * S)
        d.rectangle([22 * S, 22 * S, W - 22 * S, H - 22 * S], outline=C_GOLD_SOFT + (110,), width=1 * S)

        # Заголовок
        d.text((52 * S, 44 * S), "ЕЖЕДНЕВНАЯ СВОДКА", font=_font(True, 36 * S), fill=C_GOLD)
        date_txt = day.strftime('%d.%m.%Y')
        d.text((W - 52 * S - d.textlength(date_txt, font=_font(True, 24 * S)), 52 * S),
               date_txt, font=_font(True, 24 * S), fill=C_TEXT)
        gname = (guild.name if guild else 'Сервер')[:44]
        d.text((52 * S, 96 * S), gname, font=_font(False, 18 * S), fill=C_DIM)
        d.line([52 * S, 132 * S, W - 52 * S, 132 * S], fill=C_GOLD + (170,), width=2 * S)

        # Сетка статистики 4×2
        cells = [
            ('ПРЕДУПРЕЖДЕНИЯ', stats['warns']),
            ('БАНЫ', stats['bans']),
            ('КИКИ', stats['kicks']),
            ('МЬЮТЫ', stats['mutes']),
            ('TAG JAIL', stats['tagjail']),
            ('GHOST-PING', stats['ghost']),
            ('ОШИБКИ БОТА', stats['errors']),
            ('МОДЕРАТОР ДНЯ', None),  # особая ячейка
        ]
        cols = 4  # 8 ячеек → 4×2
        gx0, gy0 = 52 * S, 158 * S
        cw = (W - 104 * S - (cols - 1) * 16 * S) // cols
        chh = 118 * S
        for i, (label, val) in enumerate(cells):
            r, c = divmod(i, cols)
            x0, y0 = gx0 + c * (cw + 16 * S), gy0 + r * (chh + 16 * S)
            d.rounded_rectangle([x0, y0, x0 + cw, y0 + chh], radius=14 * S,
                                fill=C_CELL, outline=C_GOLD + (70,), width=1 * S)
            if label == 'МОДЕРАТОР ДНЯ':
                name = '—'
                if stats['top_mod_id'] and guild:
                    m = guild.get_member(stats['top_mod_id'])
                    name = (m.display_name if m else f"ID {stats['top_mod_id']}")[:14]
                elif stats['top_mod_id']:
                    name = f"ID {stats['top_mod_id']}"
                sub = f"{stats['top_mod_count']} действий" if stats['top_mod_id'] else ''
                d.text((x0 + 16 * S, y0 + 14 * S), label, font=_font(False, 13 * S), fill=C_DIM)
                d.text((x0 + 16 * S, y0 + 40 * S), name, font=_font(True, 20 * S), fill=C_GOLD)
                if sub:
                    d.text((x0 + 16 * S, y0 + 74 * S), sub, font=_font(False, 14 * S), fill=C_TEXT)
            else:
                num = str(val)
                d.text((x0 + 16 * S, y0 + 14 * S), label, font=_font(False, 13 * S), fill=C_DIM)
                d.text((x0 + 16 * S, y0 + 38 * S), num, font=_font(True, 44 * S), fill=C_GOLD)

        # Футер
        d.line([52 * S, H - 66 * S, W - 52 * S, H - 66 * S], fill=C_GOLD + (110,), width=1 * S)
        ftxt = "AETHER · ночная сводка 00:00"
        d.text((52 * S, H - 50 * S), ftxt, font=_font(False, 15 * S), fill=C_DIM)
        total = stats['warns'] + stats['bans'] + stats['kicks'] + stats['mutes'] + stats['tagjail']
        rtxt = f"санкций за день: {total}"
        d.text((W - 52 * S - d.textlength(rtxt, font=_font(True, 15 * S)), H - 50 * S),
               rtxt, font=_font(True, 15 * S), fill=C_GOLD)

        img = img.resize((W // S, H // S), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format='PNG', optimize=True)
        buf.seek(0)
        return buf

    # ────────────────────────────────────────────────────────────
    # Отправка
    # ────────────────────────────────────────────────────────────
    async def _channel(self, guild: discord.Guild):
        ch_id = int(self.cfg(guild.id).get('channel_id', 0) or 0)
        ch = guild.get_channel(ch_id) if ch_id else None
        if ch is None:
            logs_cog = self.bot.get_cog('Logs')
            if logs_cog:
                try:
                    ch = await logs_cog.get_log_channel(guild, 'модерация')
                except Exception:
                    ch = None
        if ch is None:
            ch = guild.system_channel
        return ch

    async def send_summary(self, guild: discord.Guild, day: datetime, channel=None) -> bool:
        try:
            cfg = self.cfg(guild.id)
            stats = await asyncio.to_thread(self.collect_day, guild.id, day, int(cfg.get('tz_offset', 3)))
            ch = channel or await self._channel(guild)
            if ch is None:
                return False
            buf = await asyncio.to_thread(self.render_card, guild, day, stats)
            file = discord.File(buf, filename=f"svodka_{day.strftime('%Y-%m-%d')}.png")
            e = discord.Embed(color=GOLD, timestamp=datetime.now(timezone.utc))
            e.description = (
                f"## 🌙 Ночная сводка — {day.strftime('%d.%m.%Y')}\n"
                f"Варнов **{stats['warns']}** · банов **{stats['bans']}** · киков **{stats['kicks']}** · "
                f"мьютов **{stats['mutes']}**\n"
                f"Tag Jail: **{stats['tagjail']}** · ghost-ping: **{stats['ghost']}** · "
                f"ошибок бота: **{stats['errors']}**\n{DIVIDER}")
            e.set_image(url=f"attachment://svodka_{day.strftime('%Y-%m-%d')}.png")
            e.set_footer(text=f"{guild.name} · ежедневная сводка")
            await ch.send(embed=e, file=file)
            return True
        except Exception as ex:
            log.warning(f"[SVODKA] {guild.name}: не смог отправить сводку: {ex}")
            return False

    # ────────────────────────────────────────────────────────────
    # Ночной цикл
    # ────────────────────────────────────────────────────────────
    RETRY_EVERY_SEC = 300   # неудачную сводку повторяем не чаще раза в 5 минут
    MAX_ATTEMPTS = 5        # после 5 неудач за ночь сдаёмся до завтра

    async def _loop_once(self, guild, now_local=None):
        """Одна попытка сводки для гильдии (вынесено ради тестов).

        Антиспам: раньше при постоянной ошибке отправки last_date не
        обновлялся и цикл долбил повтор КАЖДУЮ минуту всю ночь — в логах
        сплошной warning каждые 60 секунд. Теперь ретрай редкий и его
        количество ограничено.
        """
        cfg = self.cfg(guild.id)
        if not cfg.get('enabled'):
            return
        off = int(cfg.get('tz_offset', 3))
        now_local = now_local or (datetime.now(timezone.utc) + timedelta(hours=off))
        today = now_local.strftime('%Y-%m-%d')
        if now_local.hour != 0 or cfg.get('last_date') == today:
            return
        fails, last_try = self._fails.get(guild.id, (0, 0.0))
        if fails >= self.MAX_ATTEMPTS:
            return
        if fails and time.monotonic() - last_try < self.RETRY_EVERY_SEC:
            return
        yesterday = (now_local - timedelta(days=1)).replace(tzinfo=None)
        if await self.send_summary(guild, yesterday):
            self.set_cfg(guild.id, 'last_date', today)
            self._fails.pop(guild.id, None)
            log.info(f"[SVODKA] {guild.name}: сводка за {yesterday.strftime('%d.%m.%Y')} отправлена")
        else:
            fails += 1
            self._fails[guild.id] = (fails, time.monotonic())
            if fails >= self.MAX_ATTEMPTS:
                log.warning(f"[SVODKA] {guild.name}: {self.MAX_ATTEMPTS} неудач за ночь — "
                            f"сдаюсь до завтра (проверьте канал/права и /summary now)")

    @tasks.loop(seconds=60)
    async def _loop(self):
        for guild in list(self.bot.guilds):
            try:
                await self._loop_once(guild)
            except Exception as e:
                log.error(f"[SVODKA] ошибка цикла {guild}: {e}")

    @_loop.before_loop
    async def _before_loop(self):
        await self.bot.wait_until_ready()

    # ────────────────────────────────────────────────────────────
    # Slash: /summary
    # ────────────────────────────────────────────────────────────
    svodka = app_commands.Group(name="summary", description="Ежедневная сводка сервера")

    @svodka.command(name="now", description="Сгенерировать сводку за сегодня (предпросмотр)")
    @app_commands.checks.has_permissions(administrator=True)
    async def sv_now(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cfg = self.cfg(interaction.guild.id)
        off = int(cfg.get('tz_offset', 3))
        today = (datetime.now(timezone.utc) + timedelta(hours=off)).replace(tzinfo=None)
        stats = await asyncio.to_thread(self.collect_day, interaction.guild.id, today, off)
        buf = await asyncio.to_thread(self.render_card, interaction.guild, today, stats)
        file = discord.File(buf, filename="svodka_preview.png")
        e = discord.Embed(color=GOLD, timestamp=datetime.now(timezone.utc))
        e.description = (
            "## 🌙 Сводка за сегодня (предпросмотр)\n"
            f"Варнов **{stats['warns']}** · банов **{stats['bans']}** · киков **{stats['kicks']}** · "
            f"мьютов **{stats['mutes']}**\n"
            f"Tag Jail: **{stats['tagjail']}** · ghost-ping: **{stats['ghost']}** · "
            f"ошибок бота: **{stats['errors']}**\n{DIVIDER}")
        e.set_image(url="attachment://svodka_preview.png")
        await interaction.followup.send(embed=e, file=file, ephemeral=True)

    @svodka.command(name="channel", description="Канал для ежедневной сводки")
    @app_commands.describe(канал="Текстовый канал")
    @app_commands.checks.has_permissions(administrator=True)
    async def sv_channel(self, interaction: discord.Interaction, канал: discord.TextChannel):
        self.set_cfg(interaction.guild.id, 'channel_id', канал.id)
        await interaction.response.send_message(f"✅ Канал сводки: {канал.mention}", ephemeral=True)

    @svodka.command(name="on", description="Включить автоматическую сводку в 00:00")
    @app_commands.checks.has_permissions(administrator=True)
    async def sv_on(self, interaction: discord.Interaction):
        self.set_cfg(interaction.guild.id, 'enabled', True)
        await interaction.response.send_message("✅ Ежедневная сводка **включена** (00:00).", ephemeral=True)

    @svodka.command(name="off", description="Выключить автоматическую сводку")
    @app_commands.checks.has_permissions(administrator=True)
    async def sv_off(self, interaction: discord.Interaction):
        self.set_cfg(interaction.guild.id, 'enabled', False)
        await interaction.response.send_message("🔴 Ежедневная сводка **выключена**.", ephemeral=True)

    @svodka.command(name="timezone", description="Часовой пояс сводки (UTC±часы, напр. 3 = МСК)")
    @app_commands.describe(смещение="Смещение от UTC в часах (от -12 до 14)")
    @app_commands.checks.has_permissions(administrator=True)
    async def sv_tz(self, interaction: discord.Interaction, смещение: app_commands.Range[int, -12, 14]):
        self.set_cfg(interaction.guild.id, 'tz_offset', смещение)
        await interaction.response.send_message(
            f"✅ Сводка будет приходить в 00:00 по UTC{'+' if смещение >= 0 else ''}{смещение}.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(NightSummary(bot))
    log.info("[SVODKA] Ког загружен")
