"""
Weekly Crown — еженедельная коронация.

Каждый понедельник в 00:00–00:30 (выбранный часовой пояс) бот подводит
итоги прошедшей недели: считает прирост сообщений и голосовых минут
(снимки-снапшоты из leaderboard_*/voice_stats_*), находит чемпиона и:

  • выдаёт ему роль короны (👑 Чемпион недели, золотая, отдельная)
  • снимает роль с прошлого чемпиона
  • публикует золотой анонс

Роль короны создаётся автоматически, если не задана вручную.
Команды: /crown ... (админ).
Хранилище: data/weekly_crown.json
"""

from logger import get_logger

_log = get_logger("weekly_crown")

import os
import json
import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timezone, timedelta

from logger import get_logger

log = get_logger("weekly_crown")

STATE_PATH = 'data/weekly_crown.json'

GOLD = 0xD4AF37
CROWN_ROLE_NAME = "👑 Чемпион недели"
DIVIDER = "✦ ───────────────────── ✦"


def _load():
    try:
        if os.path.exists(STATE_PATH):
            with open(STATE_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as _ex:
        _log.debug("_load(): подавлено: %s", _ex)
    return {}


def _save(data):
    try:
        os.makedirs('data', exist_ok=True)
        tmp = STATE_PATH + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, STATE_PATH)
    except Exception as e:
        log.error(f"[CROWN] ошибка записи: {e}")


def _read_activity(guild_id: int):
    """Текущие суммы: {uid: (сообщения, войс_минуты)}."""
    out = {}
    try:
        path = f'data/leaderboard_{guild_id}.json'
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                msgs = json.load(f).get('messages', {})
            for uid, cnt in msgs.items():
                out.setdefault(str(uid), [0, 0])[0] = int(cnt)
    except Exception as _ex:
        _log.debug("_read_activity(): подавлено: %s", _ex)
    try:
        from cogs.voice_tracker import voice_view
        for uid, d in voice_view(guild_id).get('users', {}).items():
            secs = d.get('total_seconds', 0) if isinstance(d, dict) else int(d or 0)
            out.setdefault(str(uid), [0, 0])[1] = int(secs) // 60
    except Exception as _ex:
        _log.debug("_read_activity(): подавлено: %s", _ex)
    return out


class WeeklyCrown(commands.Cog):
    """Коронация чемпиона недели (сообщения + войс)."""

    def __init__(self, bot):
        self.bot = bot
        self._state = _load()

    def cfg(self, guild_id: int) -> dict:
        c = {
            'enabled': True, 'role_id': 0, 'channel_id': 0,
            'tz_offset': 3, 'last_week': '', 'holder_id': 0,
            'snapshot': {},
        }
        c.update(self._state.get(str(guild_id), {}))
        return c

    def set_cfg(self, guild_id: int, key: str, value):
        self._state.setdefault(str(guild_id), {})[key] = value
        _save(self._state)

    async def cog_load(self):
        if not self._loop.is_running():
            self._loop.start()

    async def cog_unload(self):
        self._loop.cancel()

    # ────────────────────────────────────────────────────────────
    # Чемпион недели
    # ────────────────────────────────────────────────────────────
    def weekly_scores(self, guild_id: int):
        """[(uid, score, msgs_delta, vmin_delta)] за неделю (по снапшоту)."""
        cur = _read_activity(guild_id)
        snap = self.cfg(guild_id).get('snapshot') or {}
        rows = []
        for uid, (msgs, vmin) in cur.items():
            old = snap.get(uid) or [0, 0]
            dm = max(0, msgs - int(old[0]))
            dv = max(0, vmin - int(old[1]))
            if dm + dv <= 0:
                continue
            rows.append((uid, dm + dv, dm, dv))
        rows.sort(key=lambda x: -x[1])
        return cur, rows

    async def _crown_role(self, guild: discord.Guild):
        role_id = int(self.cfg(guild.id).get('role_id', 0) or 0)
        role = guild.get_role(role_id) if role_id else None
        if role:
            return role
        # найти по имени (вдруг уже создана)
        role = discord.utils.get(guild.roles, name=CROWN_ROLE_NAME)
        if role is None:
            try:
                role = await guild.create_role(
                    name=CROWN_ROLE_NAME,
                    colour=discord.Colour(GOLD),
                    hoist=True,
                    mentionable=False,
                    reason="[Crown] автосоздание роли чемпиона недели")
                log.info(f"[CROWN] {guild.name}: создана роль короны")
            except Exception as e:
                log.warning(f"[CROWN] {guild.name}: не смог создать роль: {e}")
                return None
        self.set_cfg(guild.id, 'role_id', role.id)
        return role

    async def _announce_channel(self, guild: discord.Guild):
        ch_id = int(self.cfg(guild.id).get('channel_id', 0) or 0)
        ch = guild.get_channel(ch_id) if ch_id else None
        return ch or guild.system_channel

    async def crown_now(self, guild: discord.Guild, silent_if_empty: bool = True):
        """Подвести итоги недели прямо сейчас. Вернёт (member, score) или None."""
        cur, rows = self.weekly_scores(guild.id)
        # снапшот обновляем ВСЕГДА — следующая неделя считается от сейчас
        self.set_cfg(guild.id, 'snapshot', {u: [m, v] for u, (m, v) in cur.items()})

        if not rows:
            if not silent_if_empty:
                log.info(f"[CROWN] {guild.name}: активности за неделю нет")
            return None

        uid, score, dm, dv = rows[0]
        member = guild.get_member(int(uid)) if uid.isdigit() else None
        if member is None or member.bot:
            rows = [r for r in rows if (guild.get_member(int(r[0])) if r[0].isdigit() else None)
                    and not guild.get_member(int(r[0])).bot]
            if not rows:
                return None
            uid, score, dm, dv = rows[0]
            member = guild.get_member(int(uid))

        role = await self._crown_role(guild)
        old_holder = self.cfg(guild.id).get('holder_id', 0)
        if role:
            if old_holder and int(old_holder) != member.id:
                old_m = guild.get_member(int(old_holder))
                if old_m and role in old_m.roles:
                    try:
                        await old_m.remove_roles(role, reason="[Crown] конец недели чемпиона")
                    except Exception as e:
                        log.warning(f"[CROWN] снятие роли: {e}")
            if role not in member.roles:
                try:
                    await member.add_roles(role, reason="[Crown] чемпион недели")
                except Exception as e:
                    log.warning(f"[CROWN] выдача роли: {e}")
        self.set_cfg(guild.id, 'holder_id', member.id)

        ch = await self._announce_channel(guild)
        if ch:
            e = discord.Embed(color=GOLD, timestamp=datetime.now(timezone.utc))
            e.description = (
                "## 👑 КОРОНАЦИЯ НЕДЕЛИ\n"
                f"Самый активный участник недели — {member.mention}!\n\n"
                f"За неделю: **{dm}** сообщений · **{dv}** минут в войсе\n"
                f"Титул {role.mention if role else '👑 Чемпион недели'} теперь его — до следующего понедельника!\n{DIVIDER}")
            e.set_thumbnail(url=member.display_avatar.url)
            e.set_footer(text=f"{guild.name} · weekly crown")
            try:
                mentions = discord.AllowedMentions(users=[member], roles=False)
                await ch.send(content=f"🎉 Поздравляем, {member.mention}!",
                              embed=e, allowed_mentions=mentions)
            except Exception as ex:
                log.warning(f"[CROWN] {guild.name}: анонс не удался: {ex}")
        log.info(f"[CROWN] {guild.name}: чемпион недели — {member} (+{dm} сообщ, +{dv} мин войса)")
        return member, score

    # ────────────────────────────────────────────────────────────
    # Цикл
    # ────────────────────────────────────────────────────────────
    @tasks.loop(minutes=30)
    async def _loop(self):
        for guild in list(self.bot.guilds):
            try:
                cfg = self.cfg(guild.id)
                if not cfg.get('enabled'):
                    continue
                off = int(cfg.get('tz_offset', 3))
                now = datetime.now(timezone.utc) + timedelta(hours=off)
                iso = now.isocalendar()
                week_key = f"{iso[0]}-W{iso[1]:02d}"
                if cfg.get('last_week') == week_key:
                    continue
                # понедельник 00:00–00:29 локального времени
                if now.weekday() != 0 or now.hour != 0 or now.minute >= 30:
                    continue
                await self.crown_now(guild)
                self.set_cfg(guild.id, 'last_week', week_key)
            except Exception as e:
                log.error(f"[CROWN] ошибка цикла {guild}: {e}")

    @_loop.before_loop
    async def _before_loop(self):
        await self.bot.wait_until_ready()

    # ────────────────────────────────────────────────────────────
    # Slash: /crown
    # ────────────────────────────────────────────────────────────
    crown = app_commands.Group(name="crown", description="Чемпион недели (корона)")

    @crown.command(name="status", description="Кто сейчас носит корону + настройки")
    @app_commands.checks.has_permissions(administrator=True)
    async def cr_status(self, interaction: discord.Interaction):
        cfg = self.cfg(interaction.guild.id)
        role = interaction.guild.get_role(int(cfg.get('role_id', 0) or 0))
        holder = interaction.guild.get_member(int(cfg.get('holder_id', 0) or 0))
        ch = interaction.guild.get_channel(int(cfg.get('channel_id', 0) or 0))
        e = discord.Embed(color=GOLD if cfg.get('enabled') else 0x95A5A6,
                          timestamp=datetime.now(timezone.utc))
        e.description = (
            "## 👑 Weekly Crown\n"
            f"Система: **{'🟢 вкл' if cfg.get('enabled') else '🔴 выкл'}**\n"
            f"Текущий чемпион: {holder.mention if holder else '`никого`'}\n"
            f"Роль короны: {role.mention if role else '`создастся автоматически`'}\n"
            f"Канал анонсов: {ch.mention if ch else '`системный канал`'}\n"
            f"Последняя неделя: `{cfg.get('last_week') or '—'}`\n{DIVIDER}")
        e.set_footer(text=f"{interaction.guild.name} · weekly crown")
        await interaction.response.send_message(embed=e, ephemeral=True)

    @crown.command(name="now", description="Немедленно короновать лидера недели (тест)")
    @app_commands.checks.has_permissions(administrator=True)
    async def cr_now(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        res = await self.crown_now(interaction.guild, silent_if_empty=False)
        if res:
            await interaction.followup.send(
                f"👑 Чемпион недели: {res[0].mention} (очков активности: {res[1]})", ephemeral=True)
        else:
            await interaction.followup.send(
                "⚠️ Активности за неделю не найдено — снапшот обновлён, "
                "счёт пойдёт от текущего момента.", ephemeral=True)

    @crown.command(name="role", description="Своя роль короны (вместо автосозданной)")
    @app_commands.describe(роль="Роль чемпиона недели")
    @app_commands.checks.has_permissions(administrator=True)
    async def cr_role(self, interaction: discord.Interaction, роль: discord.Role):
        self.set_cfg(interaction.guild.id, 'role_id', роль.id)
        await interaction.response.send_message(f"✅ Роль короны: {роль.mention}", ephemeral=True)

    @crown.command(name="channel", description="Канал анонсов коронации")
    @app_commands.describe(канал="Текстовый канал")
    @app_commands.checks.has_permissions(administrator=True)
    async def cr_channel(self, interaction: discord.Interaction, канал: discord.TextChannel):
        self.set_cfg(interaction.guild.id, 'channel_id', канал.id)
        await interaction.response.send_message(f"✅ Анонсы коронации: {канал.mention}", ephemeral=True)

    @crown.command(name="toggle", description="Включить или выключить коронацию")
    @app_commands.describe(режим="вкл или выкл")
    @app_commands.choices(режим=[app_commands.Choice(name="вкл", value=1),
                                 app_commands.Choice(name="выкл", value=0)])
    @app_commands.checks.has_permissions(administrator=True)
    async def cr_toggle(self, interaction: discord.Interaction, режим: app_commands.Choice[int]):
        self.set_cfg(interaction.guild.id, 'enabled', bool(режим.value))
        await interaction.response.send_message(
            f"{'✅ Коронация **включена**' if режим.value else '🔴 Коронация **выключена**'}.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(WeeklyCrown(bot))
    log.info("[CROWN] Ког загружен")
