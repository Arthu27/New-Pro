"""
Staff Stats — таблица активности модераторов.

/staff-stats — топ модераторов за период (таблица)
/staff-stats @мод — личная карточка модератора

Источники действий:
- data/mod_data.json     — дела модерации (бан/кик/мут/варн/разбан)
- data/temp_history.json — временные наказания
- sqlite guild_data      — предупреждения (namespace 'warnings')
"""

from logger import get_logger

_log = get_logger("staff_stats")

import json
import time
import sqlite3
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone

from logger import get_logger

log = get_logger("staff_stats")

GOLD = 0xD4AF37
DIVIDER = "✦ ───────────────────── ✦"

ACTION_LABEL = {
    'ban': '🔨 бан', 'kick': '👢 кик', 'timeout': '🔇 таймаут', 'mute': '🔇 мьют',
    'vmute': '🎙 войс-мьют', 'warn': '⚠️ варн', 'unban': '♻️ разбан', 'unmute': '🔊 размьют',
}
MEDALS = ['🥇', '🥈', '🥉']


def _parse_ts(v) -> float:
    """unix float | isoformat str → unix float (0 при неудаче)."""
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return datetime.fromisoformat(str(v).replace('Z', '+00:00')).timestamp()
    except Exception:
        return 0.0


def collect_actions(guild_id: int) -> list:
    """Все мод-действия сервера: список (mod_id, action, ts)."""
    acts = []
    # 1) Дела модерации
    try:
        with open('data/mod_data.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        for c in data.get('cases', {}).get(str(guild_id), []):
            ts = _parse_ts(c.get('timestamp'))
            if ts and c.get('mod_id'):
                acts.append((str(c['mod_id']), str(c.get('action', 'mod')), ts))
    except Exception as _ex:
        _log.debug("collect_actions(): подавлено: %s", _ex)
    # 2) Временные наказания
    try:
        with open('data/temp_history.json', 'r', encoding='utf-8') as f:
            hist = json.load(f)
        if isinstance(hist, list):
            for h in hist:
                if str(h.get('guild_id')) == str(guild_id) and h.get('mod_id'):
                    ts = float(h.get('ts', 0) or 0)
                    if ts:
                        acts.append((str(h['mod_id']), str(h.get('action', 'temp')), ts))
    except Exception as _ex:
        _log.debug("collect_actions(): подавлено: %s", _ex)
    # 3) Варны из sqlite
    try:
        from config import Config
        conn = sqlite3.connect(Config.DB_PATH)
        rows = conn.execute(
            "SELECT value FROM guild_data WHERE namespace = 'warnings' AND guild_id = ?",
            (int(guild_id),)
        ).fetchall()
        conn.close()
        for (val,) in rows:
            try:
                warns = json.loads(val)
            except Exception as _ex:
                _log.debug("collect_actions(): подавлено: %s", _ex)
                continue
            if isinstance(warns, list):
                for w in warns:
                    ts = _parse_ts(w.get('timestamp'))
                    mod_id = w.get('mod_id')
                    if ts and mod_id:
                        acts.append((str(mod_id), 'warn', ts))
    except Exception as e:
        log.info(f"[STAFF] не удалось прочитать sqlite: {e}")
    return acts


def summarize(actions: list, days: int = 30):
    """mod_id -> {'total': n, 'by': {action: n}} за days дней."""
    cutoff = time.time() - days * 86400
    per = {}
    for mod_id, action, ts in actions:
        if ts < cutoff:
            continue
        ent = per.setdefault(mod_id, {'total': 0, 'by': {}, 'last_ts': 0})
        ent['total'] += 1
        ent['by'][action] = ent['by'].get(action, 0) + 1
        ent['last_ts'] = max(ent['last_ts'], ts)
    return per


def _breakdown(by: dict) -> str:
    parts = []
    for act, n in sorted(by.items(), key=lambda x: -x[1]):
        lbl = ACTION_LABEL.get(act, f'▪ {act}')
        parts.append(f"{lbl} ×{n}")
    return " · ".join(parts) if parts else "—"


def _warns_in_window(guild_id: int, user_id: int, days: int) -> int:
    """Варны пользователя за последние days дней (источник — ког warnings)."""
    try:
        from cogs.warnings import warnings as _W
        import services  # noqa: F401  (страховка импорта)
        # лёгкое чтение без инстанса когов: GuildData('warnings')
        from db import GuildData
        raw = GuildData('warnings').get(int(guild_id), str(user_id), [])
        warns = raw if isinstance(raw, list) else []
        cutoff = time.time() - days * 86400
        n = 0
        for w in warns:
            if _parse_ts(w.get('timestamp')) >= cutoff:
                n += 1
        return n
    except Exception as _ex:
        _log.debug("_warns_in_window(): подавлено: %s", _ex)
        return 0


def _voice_seconds_window(guild_id: int, user_id: int, days: int) -> int:
    """Секунды в войсе за последние days дней (по daily-карте voice_tracker)."""
    try:
        from cogs import voice_tracker as vt
        rec = vt.voice_all(guild_id).get(str(user_id)) or {}
        daily = rec.get('daily') or {}
        from datetime import date, timedelta as _td
        total = 0
        for i in range(days):
            d = str(date.today() - _td(days=i))
            total += int(daily.get(d, 0) or 0)
        return total
    except Exception as _ex:
        _log.debug("_voice_seconds_window(): подавлено: %s", _ex)
        return 0


class StaffProfileSelect(discord.ui.UserSelect):
    """Select-меню: выбрать участника — увидеть его полный профиль активности
    (варны за неделю, сообщения, войс, все наказания). Доступ — только стафф."""

    def __init__(self, guild: discord.Guild, days: int = 7):
        super().__init__(placeholder='Выбрать участника — профиль активности',
                         min_values=1, max_values=1)
        self._guild = guild
        self._days = days

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        u = interaction.user
        ok = (u.guild_permissions.moderate_members
              or u.guild_permissions.ban_members
              or u.guild_permissions.administrator
              or u.id == interaction.guild.owner_id)
        if not ok:
            await interaction.response.send_message(
                '🚫 Профиль активности доступен только модерации/администрации.',
                ephemeral=True)
        return ok

    async def callback(self, interaction: discord.Interaction):
        member = self.values[0]
        days = self._days
        # сообщения за период
        msgs = 0
        try:
            from services import mod_activity as ma
            msgs = int(ma.message_counts(self._guild.id, days=days)
                       .get(str(member.id), {}).get('messages', 0) or 0)
        except Exception as _ex:
            _log.debug("profile messages: %s", _ex)
        # войс за период
        voice_s = _voice_seconds_window(self._guild.id, member.id, days)
        vh = voice_s // 3600
        vm = (voice_s % 3600) // 60
        voice_txt = f"{vh} ч {vm} мин" if vh else f"{vm} мин"
        # наказания (которые участник ПОЛУЧИЛ) за период — из дел модерации
        cutoff = time.time() - days * 86400
        received = {}
        try:
            with open('data/mod_data.json', 'r', encoding='utf-8') as f:
                md = json.load(f)
            for c in md.get('cases', {}).get(str(self._guild.id), []):
                if (str(c.get('user_id')) == str(member.id)
                        and _parse_ts(c.get('timestamp')) >= cutoff):
                    a = str(c.get('action', 'mod'))
                    received[a] = received.get(a, 0) + 1
        except Exception as _ex:
            _log.debug("profile received: %s", _ex)
        warns_week = _warns_in_window(self._guild.id, member.id, days)
        total_punish = sum(received.values()) + warns_week

        e = discord.Embed(color=GOLD, timestamp=datetime.now(timezone.utc))
        e.set_author(name=f"Профиль активности: {member.display_name}",
                     icon_url=member.display_avatar.url)
        e.set_thumbnail(url=member.display_avatar.url)
        e.description = (
            f"**{member.mention}** · период **{days} дн.**\n{DIVIDER}\n"
            f"💬 Сообщений: **{msgs}**\n"
            f"🎙 В голосовых: **{voice_txt}**\n"
            f"⚠️ Варнов за период: **{warns_week}**\n"
            f"🚨 Всего наказаний за период: **{total_punish}**"
        )
        # ВСЕ виды наказаний одним блоком (варны + муты/баны из дел).
        all_by = dict(received)
        if warns_week:
            all_by['warn'] = all_by.get('warn', 0) + warns_week
        e.add_field(name="Наказания (все виды)",
                    value=_breakdown(all_by) if all_by else "—",
                    inline=False)
        # Действия, которые участник сам совершил как модератор (если он стафф).
        actions = collect_actions(self._guild.id)
        mine = summarize(actions, days).get(str(member.id), {})
        if mine.get('total'):
            e.add_field(name=f"Его действия как модератора ({mine['total']})",
                        value=_breakdown(mine.get('by', {})), inline=False)
        e.set_footer(text=f"{self._guild.name}")
        await interaction.response.send_message(embed=e, ephemeral=True)


class StaffProfileView(discord.ui.View):
    def __init__(self, guild: discord.Guild, days: int = 7):
        super().__init__(timeout=None)
        self.add_item(StaffProfileSelect(guild, days))


class StaffStats(commands.Cog):
    """Активность команды модераторов."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="staff-stats", description="Активность модераторов: таблица или карточка")
    @app_commands.describe(
        модератор="Конкретный модератор (по умолчанию — вся команда)",
        дней="Период в днях (по умолчанию 30)",
    )
    @app_commands.checks.has_permissions(moderate_members=True)
    async def staff_stats(self, interaction: discord.Interaction, модератор: discord.Member = None, дней: int = 30):
        guild = interaction.guild
        дней = max(1, min(дней, 365))
        actions = collect_actions(guild.id)

        e = discord.Embed(color=GOLD, timestamp=datetime.now(timezone.utc))

        if модератор:
            per = summarize(actions, дней).get(str(модератор.id), {'total': 0, 'by': {}, 'last_ts': 0})
            e.set_author(name=f"Активность: {модератор.display_name}", icon_url=модератор.display_avatar.url)
            e.set_thumbnail(url=модератор.display_avatar.url)
            last = f"<t:{int(per['last_ts'])}:R>" if per['last_ts'] else "—"
            e.description = (
                f"**{модератор.mention}** · период **{дней} дн.**\n{DIVIDER}\n"
                f"Всего действий: **{per['total']}**\n"
                f"Последнее действие: {last}\n\n"
                f"Разбивка:\n{_breakdown(per['by'])}"
            )
            # Недавние действия этого мода
            mine = [a for a in actions if a[0] == str(модератор.id)]
            mine.sort(key=lambda a: -a[2])
            if mine:
                lines = []
                for _, act, ts in mine[:5]:
                    lbl = ACTION_LABEL.get(act, f'▪ {act}')
                    lines.append(f"{lbl} — <t:{int(ts)}:R>")
                e.add_field(name="Последние 5 действий", value="\n".join(lines), inline=False)
        else:
            per = summarize(actions, дней)
            if not per:
                e.description = (
                    "## 📊 Staff Stats\n"
                    f"За последние **{дней} дн.** действий не найдено.\n"
                    "(Читаются: mod_data.json, temp_history.json, варны из базы)"
                )
            else:
                top = sorted(per.items(), key=lambda x: -x[1]['total'])[:10]
                lines = []
                for i, (mod_id, ent) in enumerate(top):
                    medal = MEDALS[i] if i < 3 else f"`{i+1}.`"
                    member = guild.get_member(int(mod_id)) if mod_id.isdigit() else None
                    name = member.display_name if member else f"ID {mod_id}"
                    lines.append(
                        f"{medal} **{name}** — **{ent['total']}**\n"
                        f"⠀{_breakdown(ent['by'])[:90]}"
                    )
                e.description = (
                    "## 📊 Staff Stats — Топ модераторов\n"
                    f"Период: **{дней} дн.** · действий всего: **{sum(e2['total'] for e2 in per.values())}**\n"
                    f"{DIVIDER}\n\n" + "\n\n".join(lines)
                )
        e.set_footer(text=f"{guild.name}")
        if модератор is None:
            # Таблица команды + select-меню: выбрать любого участника и
            # открыть его полный профиль (варны/сообщения/войс/наказания).
            view = StaffProfileView(guild, дней)
            await interaction.response.send_message(embed=e, view=view)
        else:
            await interaction.response.send_message(embed=e)

    @staff_stats.error
    async def staff_stats_error(self, interaction, error):
        try:
            await interaction.response.send_message("🚫 Нужны права модератора.", ephemeral=True)
        except Exception as _ex:
            _log.debug("staff_stats_error(): подавлено: %s", _ex)


async def setup(bot):
    await bot.add_cog(StaffStats(bot))
