"""
Staff Stats — таблица активности модераторов.

/staff-stats — топ модераторов за период (таблица)
/staff-stats @мод — личная карточка модератора

Источники действий:
- data/mod_data.json     — дела модерации (бан/кик/мут/варн/разбан)
- data/temp_history.json — временные наказания
- sqlite guild_data      — предупреждения (namespace 'warnings')
"""
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
    except Exception:
        pass
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
    except Exception:
        pass
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
            except Exception:
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
        await interaction.response.send_message(embed=e)

    @staff_stats.error
    async def staff_stats_error(self, interaction, error):
        try:
            await interaction.response.send_message("🚫 Нужны права модератора.", ephemeral=True)
        except Exception:
            pass


async def setup(bot):
    await bot.add_cog(StaffStats(bot))
