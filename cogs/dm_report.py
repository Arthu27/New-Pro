"""
Zhaloba — линия жалоб на DM-рекламу / скаутинг.

Игроки, которым в личку пишут рекламщики и «скауты» чужих серверов,
жалуются одной командой:

  /report @нарушитель [детали]

3 жалобы от РАЗНЫХ людей за 7 дней → автоматический таймаут 60 минут.
Модераторы разбирают очередь: /reports, /report-ok №, /report-no №.
Одобренная жалоба автоматически превращается в варн нарушителю.

Хранилище: data/dm_reports.json
"""
import os
import json
import time
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone, timedelta

from logger import get_logger

log = get_logger("dm_report")

DATA_PATH = 'data/dm_reports.json'

GOLD = 0xD4AF37
RED = 0xE74C3C
GREEN = 0x2ECC71
ORANGE = 0xE67E22
DIVIDER = "✦ ───────────────────── ✦"

AUTO_THRESHOLD = 3          # сколько жалоб для автодействия
AUTO_WINDOW = 7 * 86400     # окно подсчёта (7 дней)
AUTO_TIMEOUT_MIN = 60       # авто-таймаут в минутах

STATUS_LABEL = {
    'open': '🟡 открыта',
    'ok': '🟢 подтверждена',
    'no': '🔴 отклонена',
    'auto': '🟠 авто-санкция',
}


def _load(path, default):
    try:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return default


def _save(path, data):
    try:
        os.makedirs('data', exist_ok=True)
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception as e:
        log.error(f"[ZHALOBA] ошибка записи: {e}")


class DMReport(commands.Cog):
    """Жалобы игроков на DM-рекламу и браконьерство."""

    def __init__(self, bot):
        self.bot = bot
        self._data = _load(DATA_PATH, {})

    # ────────────────────────────────────────────────────────────
    # Хранилище
    # ────────────────────────────────────────────────────────────
    def _g(self, guild_id: int) -> dict:
        g = self._data.setdefault(str(guild_id), {'next_id': 1, 'items': []})
        g.setdefault('next_id', 1)
        g.setdefault('items', [])
        return g

    def _add(self, guild_id: int, reporter_id: int, target_id: int, details: str) -> dict:
        g = self._g(guild_id)
        rec = {
            'id': g['next_id'],
            'reporter_id': reporter_id,
            'target_id': target_id,
            'details': (details or '')[:500],
            'ts': int(time.time()),
            'status': 'open',
            'mod_id': 0,
        }
        g['next_id'] += 1
        g['items'].append(rec)
        del g['items'][:-300]
        _save(DATA_PATH, self._data)
        return rec

    def _get(self, guild_id: int, num: int):
        for rec in self._g(guild_id)['items']:
            if rec['id'] == num:
                return rec
        return None

    def _set_status(self, guild_id: int, num: int, status: str, mod_id: int):
        rec = self._get(guild_id, num)
        if rec:
            rec['status'] = status
            rec['mod_id'] = mod_id
            _save(DATA_PATH, self._data)
        return rec

    def _target_report_count(self, guild_id: int, target_id: int) -> int:
        """Жалобы от разных людей за окно (open + ok + auto)."""
        now = time.time()
        reporters = set()
        for rec in self._g(guild_id)['items']:
            if rec['target_id'] == target_id and now - rec['ts'] < AUTO_WINDOW \
                    and rec['status'] in ('open', 'ok', 'auto'):
                reporters.add(rec['reporter_id'])
        return len(reporters)

    # ────────────────────────────────────────────────────────────
    # Лог / DM
    # ────────────────────────────────────────────────────────────
    async def _log_channel(self, guild: discord.Guild):
        logs_cog = self.bot.get_cog('Logs')
        if logs_cog:
            try:
                return await logs_cog.get_log_channel(guild, 'модерация')
            except Exception:
                pass
        return None

    async def _log(self, guild: discord.Guild, embed: discord.Embed):
        ch = await self._log_channel(guild)
        if ch:
            try:
                await ch.send(embed=embed)
            except Exception:
                pass

    # ────────────────────────────────────────────────────────────
    # /report — подать жалобу (все игроки)
    # ────────────────────────────────────────────────────────────
    @app_commands.command(name="report", description="Пожаловаться на DM-рекламу / скаутинг")
    @app_commands.describe(
        нарушитель="Кто прислал рекламу в личку",
        детали="Что именно прислал (текст, ссылка) — не обязательно")
    async def report(self, interaction: discord.Interaction,
                      нарушитель: discord.User, детали: str = None):
        guild = interaction.guild
        if нарушитель.id == interaction.user.id:
            await interaction.response.send_message("❌ Нельзя пожаловаться на самого себя.", ephemeral=True)
            return
        if нарушитель.bot:
            await interaction.response.send_message("❌ На ботов жалобы не принимаются.", ephemeral=True)
            return

        rec = self._add(guild.id, interaction.user.id, нарушитель.id, детали or '')
        total = self._target_report_count(guild.id, нарушитель.id)

        auto_txt = ""
        if total >= AUTO_THRESHOLD:
            member = guild.get_member(нарушитель.id)
            if member and guild.me.guild_permissions.moderate_members:
                try:
                    await member.timeout(
                        discord.utils.utcnow() + timedelta(minutes=AUTO_TIMEOUT_MIN),
                        reason=f"[DMREPORT] {total} жалоб на DM-рекламу")
                    self._set_status(guild.id, rec['id'], 'auto', self.bot.user.id if self.bot.user else 0)
                    auto_txt = f"\n🟠 **{total} жалобы от разных людей → автоматический таймаут {AUTO_TIMEOUT_MIN} мин**"
                except Exception as e:
                    log.warning(f"[ZHALOBA] {guild.name}: авто-таймаут {нарушитель}: {e}")

        await interaction.response.send_message(
            f"✅ Жалоба **#{rec['id']}** принята — модераторы разберут её.\n"
            f"На этого пользователя уже **{total}** жалоб(ы) за неделю.{auto_txt}",
            ephemeral=True)

        e = discord.Embed(color=ORANGE, timestamp=datetime.now(timezone.utc))
        e.description = (
            f"## 📨 Жалоба #{rec['id']} на DM-рекламу\n"
            f"Нарушитель: **{нарушитель.display_name}** · `{нарушитель.id}`\n"
            f"Автор жалобы: {interaction.user.mention}\n"
            + (f"\n> {детали[:300]}" if детали else "")
            + f"\n\nЖалоб на него за неделю: **{total}**{auto_txt}\n{DIVIDER}"
        )
        e.set_footer(text=f"{guild.name} · dm-report")
        await self._log(guild, e)

    # ────────────────────────────────────────────────────────────
    # /zhaloby — очередь (модераторы)
    # ────────────────────────────────────────────────────────────
    @app_commands.command(name="reports", description="Очередь жалоб (модераторы)")
    @app_commands.describe(фильтр="Какие показать")
    @app_commands.choices(фильтр=[
        app_commands.Choice(name="Открытые", value="open"),
        app_commands.Choice(name="Все", value="all"),
    ])
    @app_commands.checks.has_permissions(moderate_members=True)
    async def reports(self, interaction: discord.Interaction,
                      фильтр: app_commands.Choice[str] = None):
        mode = фильтр.value if фильтр else 'open'
        items = self._g(interaction.guild.id)['items']
        if mode == 'open':
            items = [r for r in items if r['status'] == 'open']
        items = list(reversed(items[-15:]))

        e = discord.Embed(color=GOLD, timestamp=datetime.now(timezone.utc))
        if not items:
            e.description = "## 📨 Жалобы\nОчередь пуста — чисто ✨"
        else:
            lines = [f"## 📨 Жалобы — {'открытые' if mode == 'open' else 'все (последние 15)'}\n"]
            for r in items:
                ts = datetime.fromtimestamp(r['ts'], tz=timezone.utc).strftime('%d.%m %H:%M')
                details = f" — {r['details'][:80]}" if r['details'] else ""
                lines.append(
                    f"**#{r['id']}** {STATUS_LABEL.get(r['status'], r['status'])} · {ts}\n"
                    f"Нарушитель: <@{r['target_id']}> `{r['target_id']}` · от: <@{r['reporter_id']}>{details}")
            lines.append(f"\nРазбор: `/report-ok №` / `/report-no №`\n{DIVIDER}")
            e.description = "\n\n".join(lines)
        e.set_footer(text=f"{interaction.guild.name} · dm-report")
        await interaction.response.send_message(embed=e, ephemeral=True)

    # ────────────────────────────────────────────────────────────
    # /report-ok — подтвердить → варн нарушителю
    # ────────────────────────────────────────────────────────────
    @app_commands.command(name="report-ok", description="Подтвердить жалобу (варн нарушителю)")
    @app_commands.describe(номер="Номер жалобы из /reports")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def report_ok(self, interaction: discord.Interaction, номер: int):
        guild = interaction.guild
        rec = self._get(guild.id, номер)
        if not rec:
            await interaction.response.send_message(f"❌ Жалоба #{номер} не найдена.", ephemeral=True)
            return
        if rec['status'] != 'open':
            await interaction.response.send_message(
                f"⚠️ Жалоба #{номер} уже закрыта ({STATUS_LABEL.get(rec['status'])}).", ephemeral=True)
            return

        self._set_status(guild.id, номер, 'ok', interaction.user.id)

        warn_txt = ""
        target = guild.get_member(rec['target_id'])
        wcog = self.bot.get_cog('warnings') or self.bot.get_cog('Warnings')
        if target and wcog and hasattr(wcog, 'add_warning'):
            try:
                wid, total_w = await wcog.add_warning(
                    target, interaction.user,
                    f"DM-реклама (жалоба #{номер})")
                warn_txt = f" → выдан варн **#{wid}** (всего {total_w})"
            except Exception as e:
                log.warning(f"[ZHALOBA] варн по жалобе #{номер}: {e}")
                warn_txt = " (варн не удался)"
        elif not target:
            warn_txt = " (нарушитель уже не на сервере — варн не выдан)"

        reporter = guild.get_member(rec['reporter_id'])
        if reporter:
            try:
                dm = discord.Embed(color=GREEN, timestamp=datetime.now(timezone.utc))
                dm.description = (
                    f"## ✅ Ваша жалоба #{номер} подтверждена\n"
                    f"Сервер: **{guild.name}**\n"
                    f"Нарушитель наказан{warn_txt}. Спасибо за бдительность!")
                dm.set_footer(text=guild.name)
                await reporter.send(embed=dm)
            except Exception:
                pass

        await interaction.response.send_message(
            f"🟢 Жалоба **#{номер}** подтверждена{warn_txt}.", ephemeral=True)

        e = discord.Embed(color=GREEN, timestamp=datetime.now(timezone.utc))
        e.description = (
            f"## 📨 Жалоба #{номер} — 🟢 подтверждена\n"
            f"Нарушитель: <@{rec['target_id']}> `{rec['target_id']}`{warn_txt}\n"
            f"Модератор: {interaction.user.mention}\n{DIVIDER}")
        e.set_footer(text=f"{guild.name} · dm-report")
        await self._log(guild, e)

    # ────────────────────────────────────────────────────────────
    # /report-no — отклонить
    # ────────────────────────────────────────────────────────────
    @app_commands.command(name="report-no", description="Отклонить жалобу")
    @app_commands.describe(номер="Номер жалобы из /reports",
                           причина="Почему отклонена — не обязательно")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def report_no(self, interaction: discord.Interaction, номер: int, причина: str = None):
        guild = interaction.guild
        rec = self._get(guild.id, номер)
        if not rec:
            await interaction.response.send_message(f"❌ Жалоба #{номер} не найдена.", ephemeral=True)
            return
        if rec['status'] != 'open':
            await interaction.response.send_message(
                f"⚠️ Жалоба #{номер} уже закрыта ({STATUS_LABEL.get(rec['status'])}).", ephemeral=True)
            return

        self._set_status(guild.id, номер, 'no', interaction.user.id)
        await interaction.response.send_message(f"🔴 Жалоба **#{номер}** отклонена.", ephemeral=True)

        e = discord.Embed(color=RED, timestamp=datetime.now(timezone.utc))
        e.description = (
            f"## 📨 Жалоба #{номер} — 🔴 отклонена\n"
            f"Нарушитель: <@{rec['target_id']}> `{rec['target_id']}`\n"
            f"Модератор: {interaction.user.mention}"
            + (f"\nПричина: {причина[:200]}" if причина else "")
            + f"\n{DIVIDER}")
        e.set_footer(text=f"{guild.name} · dm-report")
        await self._log(guild, e)


async def setup(bot):
    await bot.add_cog(DMReport(bot))
    log.info("[ZHALOBA] Ког загружен")
