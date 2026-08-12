"""
Scheduler — запланированные анонсы.

Разовые и повторяющиеся объявления (каждый день / каждую неделю
в заданное время). Если бот был выключен и пропустил время —
догоняет при запуске (просрочка до 6 часов).

Команды: /schedule add|list|remove|toggle|test (manage_guild).
Панель: /schedule (страница панели управления).
Хранилище: data/schedules.json
"""

from logger import get_logger

_log = get_logger("scheduler")

import os
import json
import time
import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timezone, timedelta

from logger import get_logger

log = get_logger("scheduler")

DATA_PATH = 'data/schedules.json'

GOLD = 0xD4AF37
GREEN = 0x2ECC71
GRAY = 0x95A5A6
DIVIDER = "✦ ───────────────────── ✦"

MAX_LATE_SEC = 6 * 3600          # просрочка, до которой догоняем анонс
WEEKDAYS_RU = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']

REPEAT_LABEL = {'once': 'Один раз', 'daily': 'Каждый день', 'weekly': 'Каждую неделю'}


def _load():
    try:
        if os.path.exists(DATA_PATH):
            with open(DATA_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as _ex:
        _log.debug("_load(): подавлено: %s", _ex)
    return {}


def _save(data):
    try:
        os.makedirs('data', exist_ok=True)
        tmp = DATA_PATH + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, DATA_PATH)
    except Exception as e:
        log.error(f"[SCHED] ошибка записи: {e}")


def parse_time_hhmm(text: str):
    """'20:30' → (20, 30) или None."""
    try:
        h, m = str(text).strip().split(':')
        h, m = int(h), int(m)
        if 0 <= h <= 23 and 0 <= m <= 59:
            return h, m
    except Exception as _ex:
        _log.debug("parse_time_hhmm(): подавлено: %s", _ex)
    return None


def compute_next(item: dict, now: float = None) -> int:
    """Ближайший момент срабатывания (unix UTC) вперёд от now."""
    now = now or time.time()
    tz = int(item.get('tz_offset', 3) or 0)
    h, m = parse_time_hhmm(item.get('time', '12:00')) or (12, 0)
    local_now = datetime.fromtimestamp(now, tz=timezone.utc) + timedelta(hours=tz)
    cand = local_now.replace(hour=h, minute=m, second=0, microsecond=0)
    repeat = item.get('repeat', 'once')
    if repeat == 'weekly':
        wd = int(item.get('weekday', 0) or 0)
        days = (wd - cand.weekday()) % 7
        cand += timedelta(days=days)
        if cand <= local_now:
            cand += timedelta(days=7)
    else:
        if cand <= local_now:
            cand += timedelta(days=1)
    return int((cand - timedelta(hours=tz)).replace(tzinfo=timezone.utc).timestamp())


def human_next(item: dict) -> str:
    ts = item.get('next_ts') or 0
    if not ts:
        return '—'
    tz = int(item.get('tz_offset', 3) or 0)
    dt = datetime.fromtimestamp(ts, tz=timezone.utc) + timedelta(hours=tz)
    return dt.strftime('%d.%m %H:%M')


class Scheduler(commands.Cog):
    """Отправка анонсов по расписанию."""

    def __init__(self, bot):
        self.bot = bot
        self._data = _load()

    async def cog_load(self):
        if not self._loop.is_running():
            self._loop.start()

    async def cog_unload(self):
        self._loop.cancel()

    # ────────────────────────────────────────────────────────────
    # Хранилище
    # ────────────────────────────────────────────────────────────
    def _g(self, guild_id: int) -> dict:
        g = self._data.setdefault(str(guild_id), {'next_id': 1, 'items': []})
        g.setdefault('next_id', 1)
        g.setdefault('items', [])
        return g

    def get_items(self, guild_id: int) -> list:
        return self._g(guild_id)['items']

    def add_item(self, guild_id: int, **fields) -> dict:
        g = self._g(guild_id)
        item = {
            'id': g['next_id'],
            'channel_id': int(fields.get('channel_id', 0)),
            'content': str(fields.get('content', '') or '')[:1900],
            'embed': fields.get('embed'),
            'repeat': fields.get('repeat', 'once'),
            'time': fields.get('time', '12:00'),
            'weekday': int(fields.get('weekday', 0) or 0),
            'tz_offset': int(fields.get('tz_offset', 3) or 0),
            'enabled': True,
            'created_by': int(fields.get('created_by', 0) or 0),
            'created_ts': int(time.time()),
            'last_sent_ts': 0,
        }
        item['next_ts'] = compute_next(item)
        g['next_id'] += 1
        g['items'].append(item)
        del g['items'][:-100]
        _save(self._data)
        return item

    def get_item(self, guild_id: int, num: int):
        for it in self._g(guild_id)['items']:
            if it['id'] == num:
                return it
        return None

    def remove_item(self, guild_id: int, num: int) -> bool:
        g = self._g(guild_id)
        before = len(g['items'])
        g['items'] = [it for it in g['items'] if it['id'] != num]
        if len(g['items']) != before:
            _save(self._data)
            return True
        return False

    def toggle_item(self, guild_id: int, num: int):
        it = self.get_item(guild_id, num)
        if it:
            it['enabled'] = not it.get('enabled', True)
            if it['enabled']:
                it['next_ts'] = compute_next(it)
            _save(self._data)
        return it

    # ────────────────────────────────────────────────────────────
    # Отправка
    # ────────────────────────────────────────────────────────────
    def build_payload(self, item: dict):
        """(content, embed) для отправки."""
        content = (item.get('content') or '').strip() or None
        emb = item.get('embed')
        embed = None
        if emb and (emb.get('title') or emb.get('description')):
            embed = discord.Embed(
                title=(emb.get('title') or '')[:240] or None,
                description=(emb.get('description') or '')[:1900] or None,
                color=int(emb.get('color', GOLD) or GOLD),
                timestamp=datetime.now(timezone.utc))
        if content is None and embed is None:
            content = '🔔'
        return content, embed

    async def send_item(self, guild: discord.Guild, item: dict) -> bool:
        ch = guild.get_channel(int(item.get('channel_id', 0) or 0))
        if ch is None:
            log.warning(f"[SCHED] {guild.name}: канал {item.get('channel_id')} не найден (анонс #{item.get('id')})")
            return False
        content, embed = self.build_payload(item)
        try:
            await ch.send(content=content, embed=embed)
            return True
        except Exception as e:
            log.warning(f"[SCHED] {guild.name}: отправка #{item.get('id')}: {e}")
            return False

    # ────────────────────────────────────────────────────────────
    # Цикл
    # ────────────────────────────────────────────────────────────
    @tasks.loop(seconds=30)
    async def _loop(self):
        now = time.time()
        for guild in list(self.bot.guilds):
            try:
                await self._legacy_tick(guild, now)
                g = self._g(guild.id)
                changed = False
                for item in list(g['items']):
                    if not item.get('enabled', True):
                        continue
                    nxt = int(item.get('next_ts', 0) or 0)
                    if now < nxt:
                        continue
                    late = now - nxt
                    sent = False
                    if late <= MAX_LATE_SEC:
                        sent = await self.send_item(guild, item)
                        if sent:
                            log.info(f"[SCHED] {guild.name}: анонс #{item['id']} отправлен"
                                     + (f" (задержка {int(late // 60)} мин)" if late > 90 else ""))
                    else:
                        log.info(f"[SCHED] {guild.name}: анонс #{item['id']} просрочен на {int(late // 3600)}ч — пропущен")
                    changed = True
                    if item.get('repeat') == 'once':
                        g['items'] = [x for x in g['items'] if x['id'] != item['id']]
                    else:
                        item['last_sent_ts'] = int(now)
                        item['next_ts'] = compute_next(item, now + 60)
                if changed:
                    _save(self._data)
            except Exception as e:
                log.error(f"[SCHED] ошибка цикла {guild}: {e}")

    @_loop.before_loop
    async def _before_loop(self):
        await self.bot.wait_until_ready()

    # ────────────────────────────────────────────────────────────
    # Устаревшая панель «Запланированные сообщения»
    # (data/scheduled_{gid}.json, интервал в минутах) — теперь
    # эти сообщения тоже реально отправляются.
    # ────────────────────────────────────────────────────────────
    async def _legacy_tick(self, guild: discord.Guild, now: float):
        path = f'data/scheduled_{guild.id}.json'
        if not os.path.exists(path):
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                msgs = json.load(f)
        except Exception:
            return
        if not isinstance(msgs, dict) or not msgs:
            return
        changed = False
        for msg_id, rec in msgs.items():
            try:
                if not rec.get('active', True):
                    continue
                nxt = rec.get('next_run') or ''
                try:
                    nxt_ts = datetime.fromisoformat(str(nxt).replace('Z', '+00:00')).timestamp()
                except Exception:
                    nxt_ts = 0
                if nxt_ts and now < nxt_ts:
                    continue
                ch = guild.get_channel(int(rec.get('channel_id', 0) or 0))
                content = (rec.get('content') or '').strip()
                if ch is not None and content:
                    try:
                        await ch.send(content)
                        log.info(f"[SCHED/legacy] {guild.name}: сообщение #{msg_id} отправлено")
                    except Exception as e:
                        log.warning(f"[SCHED/legacy] {guild.name}: отправка #{msg_id}: {e}")
                # следующий запуск: сейчас + интервал минут (догон без завала)
                try:
                    interval_min = max(1, int(rec.get('interval', 60) or 60))
                except Exception:
                    interval_min = 60
                rec['next_run'] = datetime.fromtimestamp(
                    now + interval_min * 60, tz=timezone.utc).isoformat()
                changed = True
            except Exception as e:
                log.error(f"[SCHED/legacy] ошибка записи #{msg_id}: {e}")
        if changed:
            try:
                tmp = path + '.tmp'
                with open(tmp, 'w', encoding='utf-8') as f:
                    json.dump(msgs, f, ensure_ascii=False, indent=2)
                os.replace(tmp, path)
            except Exception as e:
                log.error(f"[SCHED/legacy] ошибка записи файла: {e}")

    # ────────────────────────────────────────────────────────────
    # Slash: /schedule
    # ────────────────────────────────────────────────────────────
    schedule = app_commands.Group(name="schedule", description="Запланированные анонсы")

    @schedule.command(name="add", description="Добавить анонс по расписанию")
    @app_commands.describe(
        канал="Куда отправлять",
        время="Время ЧЧ:ММ (напр. 20:00)",
        текст="Текст анонса",
        повтор="Как часто повторять",
        день_недели="Для еженедельного — день",
        смещение="Часовой пояс UTC±часы (по умолч. 3 = МСК)")
    @app_commands.choices(повтор=[
        app_commands.Choice(name="Один раз", value="once"),
        app_commands.Choice(name="Каждый день", value="daily"),
        app_commands.Choice(name="Каждую неделю", value="weekly"),
    ], день_недели=[
        app_commands.Choice(name="Понедельник", value=0),
        app_commands.Choice(name="Вторник", value=1),
        app_commands.Choice(name="Среда", value=2),
        app_commands.Choice(name="Четверг", value=3),
        app_commands.Choice(name="Пятница", value=4),
        app_commands.Choice(name="Суббота", value=5),
        app_commands.Choice(name="Воскресенье", value=6),
    ])
    @app_commands.checks.has_permissions(manage_guild=True)
    async def sc_add(self, interaction: discord.Interaction,
                     канал: discord.TextChannel, время: str, текст: str,
                     повтор: app_commands.Choice[str],
                     день_недели: app_commands.Choice[int] = None,
                     смещение: app_commands.Range[int, -12, 14] = 3):
        if not parse_time_hhmm(время):
            await interaction.response.send_message(
                "❌ Неверное время. Формат: **ЧЧ:ММ** (например `20:00`).", ephemeral=True)
            return
        item = self.add_item(
            interaction.guild.id,
            channel_id=канал.id, content=текст, repeat=повтор.value,
            time=время, weekday=день_недели.value if день_недели else 0,
            tz_offset=смещение, created_by=interaction.user.id)
        e = discord.Embed(color=GREEN, timestamp=datetime.now(timezone.utc))
        wd = f" · {WEEKDAYS_RU[item['weekday']]}" if item['repeat'] == 'weekly' else ''
        e.description = (
            f"## 🗓 Анонс #{item['id']} запланирован\n"
            f"Канал: {канал.mention}\n"
            f"Режим: **{REPEAT_LABEL[item['repeat']]}** · {item['time']}{wd} (UTC+{item['tz_offset']})\n"
            f"Следующая отправка: **{human_next(item)}**\n{DIVIDER}")
        await interaction.response.send_message(embed=e, ephemeral=True)

    @schedule.command(name="list", description="Список запланированных анонсов")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def sc_list(self, interaction: discord.Interaction):
        items = self.get_items(interaction.guild.id)
        e = discord.Embed(color=GOLD, timestamp=datetime.now(timezone.utc))
        if not items:
            e.description = "## 🗓 Расписание\nПусто — добавь первый анонс: `/schedule add`"
        else:
            lines = ["## 🗓 Запланированные анонсы\n"]
            for it in items[-15:]:
                ch = interaction.guild.get_channel(int(it['channel_id']))
                state = '🟢' if it.get('enabled', True) else '⏸'
                wd = f" · {WEEKDAYS_RU[it['weekday']]}" if it['repeat'] == 'weekly' else ''
                preview = (it.get('content') or it.get('embed', {}).get('title') or '')[:60]
                lines.append(
                    f"{state} **#{it['id']}** {ch.mention if ch else '`канал удалён`'} · "
                    f"{REPEAT_LABEL.get(it['repeat'], it['repeat'])} · {it['time']}{wd}\n"
                    f"След.: **{human_next(it)}** · {preview}")
            lines.append(f"\n`/schedule toggle №` — пауза · `/schedule remove №` — удалить\n{DIVIDER}")
            e.description = "\n\n".join(lines)
        e.set_footer(text=f"{interaction.guild.name} · scheduler")
        await interaction.response.send_message(embed=e, ephemeral=True)

    @schedule.command(name="remove", description="Удалить анонс из расписания")
    @app_commands.describe(номер="Номер из /schedule list")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def sc_remove(self, interaction: discord.Interaction, номер: int):
        if self.remove_item(interaction.guild.id, номер):
            await interaction.response.send_message(f"🗑 Анонс **#{номер}** удалён.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Анонс **#{номер}** не найден.", ephemeral=True)

    @schedule.command(name="toggle", description="Пауза / возобновить анонс")
    @app_commands.describe(номер="Номер из /schedule list")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def sc_toggle(self, interaction: discord.Interaction, номер: int):
        it = self.toggle_item(interaction.guild.id, номер)
        if not it:
            await interaction.response.send_message(f"❌ Анонс **#{номер}** не найден.", ephemeral=True)
            return
        if it.get('enabled', True):
            await interaction.response.send_message(
                f"▶️ Анонс **#{номер}** возобновлён. След. отправка: **{human_next(it)}**", ephemeral=True)
        else:
            await interaction.response.send_message(f"⏸ Анонс **#{номер}** на паузе.", ephemeral=True)

    @schedule.command(name="test", description="Отправить анонс прямо сейчас (расписание сохранится)")
    @app_commands.describe(номер="Номер из /schedule list")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def sc_test(self, interaction: discord.Interaction, номер: int):
        it = self.get_item(interaction.guild.id, номер)
        if not it:
            await interaction.response.send_message(f"❌ Анонс **#{номер}** не найден.", ephemeral=True)
            return
        ok = await self.send_item(interaction.guild, it)
        if ok:
            await interaction.response.send_message(f"✅ Тестовая отправка анонса **#{номер}** выполнена.", ephemeral=True)
        else:
            await interaction.response.send_message(
                "❌ Не смог отправить — проверьте канал и права бота.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Scheduler(bot))
    log.info("[SCHED] Ког загружен")
