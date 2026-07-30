"""
Временная Модерация Cog
=======================
- /mute @user <время> [причина] - Временный мьют
- /unmute @user - Снять мьют досрочно
- /tempban @user <время> [причина] - Временный бан
- /unban <id/username> - Снять бан досрочно
- /tempkick @user <время> [причина] - Кикнуть, через N мин можно вернуться
- /unwarn @user - Снять последнее предупреждение
- /schedule <действие> @user <время> [причина] - Запланировать
- /unschedule <id> - Отменить запланированное

Время: 30s, 5m, 2h, 1d, 7d, 30d + свободный формат
"""
import discord
from discord.ext import commands, tasks
import json
import os
import re
import time
import asyncio
from datetime import datetime, timedelta
from collections import defaultdict

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

PRESETS = [
    ("30с",   30),
    ("1м",    60),
    ("5м",    300),
    ("15м",   900),
    ("30м",   1800),
    ("1ч",    3600),
    ("3ч",    10800),
    ("6ч",    21600),
    ("12ч",   43200),
    ("1д",    86400),
    ("3д",    259200),
    ("7д",    604800),
    ("14д",   1209600),
    ("30д",   2592000),
]

# Парсинг времени: 1h, 30m, 1d, 1д, 30мин, 1час, 1день, etc.
TIME_REGEX = re.compile(r'(\d+)\s*(s|sec|secs|second|seconds|м|мин|min|mins|minute|minutes|ч|час|часа|часов|h|hr|hrs|hour|hours|д|день|дня|дней|d|day|days|w|week|weeks|нед|неделя|недели|недель|мес|месяц|месяца|месяцев|mo|month|months)\b', re.IGNORECASE)

TIME_ALIASES = {
    's': 1, 'sec': 1, 'secs': 1, 'second': 1, 'seconds': 1,
    'м': 60, 'мин': 60, 'min': 60, 'mins': 60, 'minute': 60, 'minutes': 60,
    'ч': 3600, 'час': 3600, 'часа': 3600, 'часов': 3600, 'h': 3600, 'hr': 3600, 'hrs': 3600, 'hour': 3600, 'hours': 3600,
    'д': 86400, 'день': 86400, 'дня': 86400, 'дней': 86400, 'd': 86400, 'day': 86400, 'days': 86400,
    'w': 604800, 'week': 604800, 'weeks': 604800, 'нед': 604800, 'неделя': 604800, 'недели': 604800, 'недель': 604800,
    'мес': 2592000, 'месяц': 2592000, 'месяца': 2592000, 'месяцев': 2592000, 'mo': 2592000, 'month': 2592000, 'months': 2592000,
}


def parse_duration(text):
    """Parse '1h 30m', '2д 5ч', '30мин' etc. → seconds"""
    if not text:
        return None
    text = str(text).strip().lower()
    # Try direct seconds
    if text.isdigit():
        return int(text)
    # Find all matches
    matches = TIME_REGEX.findall(text)
    if not matches:
        return None
    total = 0
    for num, unit in matches:
        unit = unit.lower()
        if unit in TIME_ALIASES:
            total += int(num) * TIME_ALIASES[unit]
        else:
            return None
    return total if total > 0 else None


def format_duration(sec, lang="ru"):
    """Format seconds → '1д 5ч 30м' or '2 hours 30 minutes'"""
    if sec < 60:
        return f"{sec}с" if lang == "ru" else f"{sec}s"
    days, rem = divmod(sec, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    parts = []
    if days > 0:
        days_label = "дн" if lang == "ru" else "d"
        parts.append(f"{days}{days_label}")
    if hours > 0:
        hours_label = "ч" if lang == "ru" else "h"
        parts.append(f"{hours}{hours_label}")
    if minutes > 0:
        min_label = "м" if lang == "ru" else "m"
        parts.append(f"{minutes}{min_label}")
    if not parts and seconds > 0:
        sec_label = "с" if lang == "ru" else "s"
        parts.append(f"{seconds}{sec_label}")
    return " ".join(parts) if lang == "ru" else " ".join(parts)


def fmt_countdown(end_ts):
    """Live countdown like '23м 14с осталось'"""
    now = time.time()
    rem = int(end_ts - now)
    if rem <= 0:
        return "истекло"
    return format_duration(rem) + " осталось" if True else "expired"


class TempModeration(commands.Cog):
    """Временная модерация: мьют, бан, кик с таймером"""

    def __init__(self, bot):
        self.bot = bot
        # Загрузить при старте
        self._mutes = {}     # guild_id -> {user_id: {until, reason, mod_id}}
        self._bans = {}      # guild_id -> {user_id: {until, reason, mod_id}}
        self._kicks = {}     # guild_id -> {user_id: {until (rejoin_time), reason, mod_id}}
        self._scheduled = [] # [{id, action, guild_id, user_id, mod_id, run_at, duration, reason}]
        self._cooldowns = {} # (user_id, action) -> last_time (anti-spam)
        self._load_state()
        # Запустить фоновые задачи
        self.check_expirations.start()
        self.run_scheduler.start()

    def cog_unload(self):
        self.check_expirations.cancel()
        self.run_scheduler.cancel()

    # ─── PERSISTENCE ───────────────────────────────────────
    def _mutes_file(self): return f"{DATA_DIR}/temp_mutes.json"
    def _bans_file(self): return f"{DATA_DIR}/temp_bans.json"
    def _kicks_file(self): return f"{DATA_DIR}/temp_kicks.json"
    def _scheduled_file(self): return f"{DATA_DIR}/temp_scheduled.json"
    def _history_file(self): return f"{DATA_DIR}/temp_history.json"
    def _whitelist_file(self): return f"{DATA_DIR}/temp_whitelist.json"

    def _load_state(self):
        """Load all data on startup"""
        for path, target in [
            (self._mutes_file(), "_mutes"),
            (self._bans_file(), "_bans"),
            (self._kicks_file(), "_kicks"),
        ]:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    setattr(self, target, json.load(f))
            except Exception:
                setattr(self, target, {})
        try:
            with open(self._scheduled_file(), "r", encoding="utf-8") as f:
                self._scheduled = json.load(f)
        except Exception:
            self._scheduled = []

    def _save(self, target, path):
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(getattr(self, target), f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[temp_mod] save {target}: {e}")

    def add_history(self, action, guild_id, user_id, mod_id, duration, reason, expires_at=None):
        try:
            history = []
            if os.path.exists(self._history_file()):
                with open(self._history_file(), "r", encoding="utf-8") as f:
                    history = json.load(f)
            history.append({
                "ts": time.time(),
                "action": action,
                "guild_id": str(guild_id),
                "user_id": str(user_id),
                "mod_id": str(mod_id),
                "duration": duration,
                "reason": reason,
                "expires_at": expires_at,
                "status": "active",
            })
            history = history[-2000:]
            with open(self._history_file(), "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[temp_mod] history: {e}")

    def get_whitelist(self, guild_id):
        try:
            with open(self._whitelist_file(), "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get(str(guild_id), [])
        except Exception:
            return []

    def is_whitelisted(self, guild, member):
        if member.guild_permissions.administrator:
            return True
        if str(member.id) in self.get_whitelist(guild.id):
            return True
        return False

    def _cooldown_ok(self, user_id, action):
        """Anti-spam: same user can't be muted/banned by same mod more than once per 10s"""
        key = (str(user_id), action)
        now = time.time()
        last = self._cooldowns.get(key, 0)
        if now - last < 10:
            return False, int(10 - (now - last))
        self._cooldowns[key] = now
        return True, 0

    # ─── COMMANDS ─────────────────────────────────────────
    @commands.command(name="mute", aliases=["tempmute", "времьют"])
    @commands.has_permissions(moderate_members=True)
    async def mute_cmd(self, ctx, member: discord.Member, duration: str = "1h", *, reason: str = "Без причины"):
        """Временный мьют: !mute @user 1h причина"""
        sec = parse_duration(duration)
        if not sec:
            presets = ", ".join(f"`{label}`" for label, _ in PRESETS[:10])
            await ctx.send(f"❌ Неверный формат времени. Примеры: `1h`, `30m`, `1д`, `2ч 30м`\nПресеты: {presets}")
            return
        if sec > 2592000 * 6:  # max 6 months
            await ctx.send("❌ Максимум 6 месяцев")
            return
        if sec < 30:
            await ctx.send("❌ Минимум 30 секунд")
            return
        if self.is_whitelisted(ctx.guild, member):
            await ctx.send("❌ Этот пользователь в белом списке")
            return
        ok, cd = self._cooldown_ok(member.id, "mute")
        if not ok:
            await ctx.send(f"⏳ Подождите {cd}с перед повторным мьютом этого пользователя")
            return
        until_ts = time.time() + sec
        until_dt = datetime.utcnow() + timedelta(seconds=sec)
        try:
            await member.timeout(until_dt, reason=f"[TempMod] {ctx.author}: {reason}")
        except discord.Forbidden:
            await ctx.send("❌ Нет прав на мьют этого пользователя (роль выше)")
            return
        except discord.HTTPException as e:
            await ctx.send(f"❌ Ошибка Discord: {e}")
            return
        # Record
        self._mutes.setdefault(str(ctx.guild.id), {})[str(member.id)] = {
            "until": until_ts,
            "reason": reason,
            "mod_id": str(ctx.author.id),
            "created_at": time.time(),
            "duration": sec,
        }
        self._save("_mutes", self._mutes_file())
        self.add_history("mute", ctx.guild.id, member.id, ctx.author.id, sec, reason, until_ts)
        # DM
        try:
            embed = discord.Embed(
                title="🔇 Временный мьют",
                description=f"Вы были замучены на сервере **{ctx.guild.name}** на **{format_duration(sec)}**",
                color=0xFBBF24
            )
            embed.add_field(name="Причина", value=reason, inline=False)
            embed.add_field(name="Модератор", value=ctx.author.display_name, inline=True)
            embed.add_field(name="Истекает", value=f"<t:{int(until_ts)}:R>", inline=True)
            await member.send(embed=embed)
        except discord.Forbidden:
            pass
        # Confirmation
        embed = discord.Embed(
            title="🔇 Временный мьют",
            description=f"{member.mention} замучен на **{format_duration(sec)}**",
            color=0xFBBF24
        )
        embed.add_field(name="Причина", value=reason, inline=False)
        embed.add_field(name="Истекает", value=f"<t:{int(until_ts)}:F> (<t:{int(until_ts)}:R>)", inline=False)
        embed.add_field(name="Модератор", value=ctx.author.mention, inline=True)
        await ctx.send(embed=embed)

    @commands.command(name="unmute")
    @commands.has_permissions(moderate_members=True)
    async def unmute_cmd(self, ctx, member: discord.Member):
        """Снять мьют досрочно"""
        guild_mutes = self._mutes.get(str(ctx.guild.id), {})
        if str(member.id) not in guild_mutes:
            await ctx.send(f"❌ {member.mention} не имеет активного временного мьюта")
            return
        try:
            await member.timeout(None, reason=f"[TempMod] Снято досрочно {ctx.author}")
        except discord.Forbidden:
            await ctx.send("❌ Нет прав")
            return
        del guild_mutes[str(member.id)]
        self._save("_mutes", self._mutes_file())
        embed = discord.Embed(
            title="🔊 Мьют снят",
            description=f"Мьют с {member.mention} снят досрочно",
            color=0x4ADE80
        )
        embed.add_field(name="Модератор", value=ctx.author.mention, inline=True)
        await ctx.send(embed=embed)

    @commands.command(name="tempban", aliases=["врембан", "tban"])
    @commands.has_permissions(ban_members=True)
    async def tempban_cmd(self, ctx, member: discord.Member, duration: str = "1d", *, reason: str = "Без причины"):
        """Временный бан: !tempban @user 7d причина"""
        sec = parse_duration(duration)
        if not sec:
            await ctx.send("❌ Неверный формат времени. Примеры: `1d`, `7д`, `12h`")
            return
        if sec < 300:
            await ctx.send("❌ Минимум 5 минут (для бана)")
            return
        if sec > 31536000:  # max 1 year
            await ctx.send("❌ Максимум 1 год")
            return
        if self.is_whitelisted(ctx.guild, member):
            await ctx.send("❌ Этот пользователь в белом списке")
            return
        ok, cd = self._cooldown_ok(member.id, "ban")
        if not ok:
            await ctx.send(f"⏳ Подождите {cd}с")
            return
        until_ts = time.time() + sec
        # DM before ban
        try:
            embed = discord.Embed(
                title="🔨 Временный бан",
                description=f"Вы были временно забанены на сервере **{ctx.guild.name}** на **{format_duration(sec)}**",
                color=0xEF4444
            )
            embed.add_field(name="Причина", value=reason, inline=False)
            embed.add_field(name="Модератор", value=ctx.author.display_name, inline=True)
            embed.add_field(name="Истекает", value=f"<t:{int(until_ts)}:R>", inline=True)
            await member.send(embed=embed)
        except discord.Forbidden:
            pass
        # Ban
        try:
            await ctx.guild.ban(member, reason=f"[TempMod] {ctx.author}: {reason} ({format_duration(sec)})")
        except discord.Forbidden:
            await ctx.send("❌ Нет прав на бан")
            return
        self._bans.setdefault(str(ctx.guild.id), {})[str(member.id)] = {
            "until": until_ts,
            "reason": reason,
            "mod_id": str(ctx.author.id),
            "created_at": time.time(),
            "duration": sec,
            "user_name": str(member),
        }
        self._save("_bans", self._bans_file())
        self.add_history("tempban", ctx.guild.id, member.id, ctx.author.id, sec, reason, until_ts)
        embed = discord.Embed(
            title="🔨 Временный бан",
            description=f"{member.mention} забанен на **{format_duration(sec)}**",
            color=0xEF4444
        )
        embed.add_field(name="Причина", value=reason, inline=False)
        embed.add_field(name="Истекает", value=f"<t:{int(until_ts)}:F>", inline=False)
        embed.add_field(name="Модератор", value=ctx.author.mention, inline=True)
        await ctx.send(embed=embed)

    @commands.command(name="unban")
    @commands.has_permissions(ban_members=True)
    async def unban_cmd(self, ctx, user_id: str):
        """Снять временный бан досрочно: !unban 123456789"""
        guild_bans = self._bans.get(str(ctx.guild.id), {})
        if user_id not in guild_bans:
            await ctx.send("❌ Этот пользователь не имеет активного временного бана")
            return
        try:
            user = await self.bot.fetch_user(int(user_id))
            await ctx.guild.unban(user, reason=f"[TempMod] Снято досрочно {ctx.author}")
        except Exception as e:
            await ctx.send(f"❌ Ошибка: {e}")
            return
        del guild_bans[user_id]
        self._save("_bans", self._bans_file())
        embed = discord.Embed(title="🔓 Бан снят", description=f"Временный бан снят досрочно", color=0x4ADE80)
        embed.add_field(name="Модератор", value=ctx.author.mention, inline=True)
        await ctx.send(embed=embed)

    @commands.command(name="tempkick", aliases=["softkick", "мягкий_кик"])
    @commands.has_permissions(kick_members=True)
    async def tempkick_cmd(self, ctx, member: discord.Member, duration: str = "5m", *, reason: str = "Без причины"):
        """Временный кик: !tempkick @user 5m причина (пользователь сможет вернуться через N минут)"""
        sec = parse_duration(duration)
        if not sec:
            await ctx.send("❌ Неверный формат")
            return
        if sec < 60:
            await ctx.send("❌ Минимум 1 минута")
            return
        if sec > 86400:
            await ctx.send("❌ Максимум 24 часа")
            return
        if self.is_whitelisted(ctx.guild, member):
            await ctx.send("❌ В белом списке")
            return
        ok, cd = self._cooldown_ok(member.id, "kick")
        if not ok:
            await ctx.send(f"⏳ Подождите {cd}с")
            return
        until_ts = time.time() + sec
        # DM
        try:
            embed = discord.Embed(
                title="👢 Временный кик",
                description=f"Вы были кикнуты с **{ctx.guild.name}** на **{format_duration(sec)}**.\nВы сможете вернуться после истечения срока.",
                color=0xF97316
            )
            embed.add_field(name="Причина", value=reason, inline=False)
            await member.send(embed=embed)
        except discord.Forbidden:
            pass
        try:
            await member.kick(reason=f"[TempMod] {ctx.author}: {reason} ({format_duration(sec)})")
        except discord.Forbidden:
            await ctx.send("❌ Нет прав")
            return
        self._kicks.setdefault(str(ctx.guild.id), {})[str(member.id)] = {
            "until": until_ts,
            "reason": reason,
            "mod_id": str(ctx.author.id),
            "created_at": time.time(),
            "duration": sec,
            "user_name": str(member),
        }
        self._save("_kicks", self._kicks_file())
        self.add_history("tempkick", ctx.guild.id, member.id, ctx.author.id, sec, reason, until_ts)
        embed = discord.Embed(
            title="👢 Временный кик",
            description=f"{member.mention} кикнут на **{format_duration(sec)}**\nСможет вернуться: <t:{int(until_ts)}:R>",
            color=0xF97316
        )
        embed.add_field(name="Причина", value=reason, inline=False)
        embed.add_field(name="Модератор", value=ctx.author.mention, inline=True)
        await ctx.send(embed=embed)

    # ─── EXPIRATION CHECKER ─────────────────────────────────
    @tasks.loop(seconds=30)
    async def check_expirations(self):
        """Check for expired mutes/bans every 30s"""
        now = time.time()
        # Mutes
        for guild_id, mutes in list(self._mutes.items()):
            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                continue
            for user_id, info in list(mutes.items()):
                if info["until"] <= now:
                    member = guild.get_member(int(user_id))
                    if member and member.is_timed_out():
                        try:
                            await member.timeout(None, reason="[TempMod] Срок мьюта истёк")
                        except (discord.Forbidden, discord.HTTPException):
                            pass
                    del mutes[user_id]
                    # History update
                    self._update_history_status(guild_id, user_id, "mute", "expired")
        # Bans
        for guild_id, bans in list(self._bans.items()):
            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                continue
            for user_id, info in list(bans.items()):
                if info["until"] <= now:
                    try:
                        user = await self.bot.fetch_user(int(user_id))
                        await guild.unban(user, reason="[TempMod] Срок бана истёк")
                    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                        pass
                    del bans[user_id]
                    self._update_history_status(guild_id, user_id, "tempban", "expired")
        # Save
        self._save("_mutes", self._mutes_file())
        self._save("_bans", self._bans_file())

    @check_expirations.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    def _update_history_status(self, guild_id, user_id, action, status):
        try:
            history = []
            if os.path.exists(self._history_file()):
                with open(self._history_file(), "r", encoding="utf-8") as f:
                    history = json.load(f)
            for h in reversed(history):
                if h["guild_id"] == str(guild_id) and h["user_id"] == str(user_id) and h["action"] == action and h["status"] == "active":
                    h["status"] = status
                    h["resolved_at"] = time.time()
                    break
            with open(self._history_file(), "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ─── SCHEDULER ────────────────────────────────────────
    @commands.command(name="schedule", aliases=["запланировать"])
    @commands.has_permissions(moderate_members=True)
    async def schedule_cmd(self, ctx, action: str, member: discord.Member, when: str, *, reason: str = "Запланировано"):
        """Запланировать мьют/бан: !schedule mute @user 2h через 1h причина"""
        # Parse '2h через 1h' or '2h 1h'
        parts = when.split()
        if len(parts) < 2:
            await ctx.send("❌ Формат: `!schedule mute @user 2h 1h` (действие через время)")
            return
        duration = parse_duration(parts[0])
        delay = parse_duration(parts[1])
        if not duration or not delay:
            await ctx.send("❌ Неверный формат времени")
            return
        if action not in ("mute", "ban", "kick"):
            await ctx.send("❌ Действие: mute / ban / kick")
            return
        run_at = time.time() + delay
        entry_id = f"sch_{int(run_at)}_{member.id}"
        entry = {
            "id": entry_id,
            "action": action,
            "guild_id": str(ctx.guild.id),
            "user_id": str(member.id),
            "user_name": str(member),
            "mod_id": str(ctx.author.id),
            "run_at": run_at,
            "duration": duration,
            "reason": reason,
            "status": "pending",
        }
        self._scheduled.append(entry)
        self._save("_scheduled", self._scheduled_file())
        embed = discord.Embed(
            title="⏰ Запланировано",
            description=f"**{action}** для {member.mention} на **{format_duration(duration)}**",
            color=0x60A5FA
        )
        embed.add_field(name="Сработает", value=f"<t:{int(run_at)}:F> (<t:{int(run_at)}:R>)", inline=False)
        embed.add_field(name="ID", value=f"`{entry_id}`", inline=True)
        embed.add_field(name="Причина", value=reason, inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="unschedule")
    @commands.has_permissions(moderate_members=True)
    async def unschedule_cmd(self, ctx, entry_id: str):
        """Отменить запланированное: !unschedule sch_xxx"""
        for i, e in enumerate(self._scheduled):
            if e["id"] == entry_id:
                self._scheduled.pop(i)
                self._save("_scheduled", self._scheduled_file())
                await ctx.send(f"✅ Запланированное `{entry_id}` отменено")
                return
        await ctx.send("❌ Не найдено")

    @tasks.loop(seconds=30)
    async def run_scheduler(self):
        """Run scheduled actions when their time comes"""
        now = time.time()
        for entry in list(self._scheduled):
            if entry["run_at"] <= now and entry["status"] == "pending":
                guild = self.bot.get_guild(int(entry["guild_id"]))
                if not guild:
                    entry["status"] = "failed"
                    continue
                # Find member if still on server
                member = guild.get_member(int(entry["user_id"]))
                action = entry["action"]
                duration = entry["duration"]
                reason = f"[Запланировано] {entry['reason']}"
                try:
                    if action == "mute":
                        if member:
                            until = datetime.utcnow() + timedelta(seconds=duration)
                            await member.timeout(until, reason=reason)
                            self._mutes.setdefault(entry["guild_id"], {})[entry["user_id"]] = {
                                "until": now + duration, "reason": reason,
                                "mod_id": entry["mod_id"], "created_at": now, "duration": duration,
                            }
                    elif action == "ban":
                        if member:
                            await guild.ban(member, reason=reason)
                        self._bans.setdefault(entry["guild_id"], {})[entry["user_id"]] = {
                            "until": now + duration, "reason": reason,
                            "mod_id": entry["mod_id"], "created_at": now, "duration": duration,
                            "user_name": entry.get("user_name", ""),
                        }
                    elif action == "kick":
                        if member:
                            await member.kick(reason=reason)
                        self._kicks.setdefault(entry["guild_id"], {})[entry["user_id"]] = {
                            "until": now + duration, "reason": reason,
                            "mod_id": entry["mod_id"], "created_at": now, "duration": duration,
                            "user_name": entry.get("user_name", ""),
                        }
                    entry["status"] = "executed"
                    self.add_history(f"scheduled_{action}", guild.id, entry["user_id"], entry["mod_id"], duration, reason)
                except Exception as e:
                    entry["status"] = f"failed: {e}"
        self._save("_scheduled", self._scheduled_file())

    @run_scheduler.before_loop
    async def before_scheduler(self):
        await self.bot.wait_until_ready()

    # ─── WHITELIST ─────────────────────────────────────────
    @commands.command(name="modwhitelist")
    @commands.has_permissions(administrator=True)
    async def whitelist_cmd(self, ctx, action: str = "list", user: discord.Member = None):
        """!modwhitelist list|add|remove @user"""
        data = {}
        try:
            with open(self._whitelist_file(), "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass
        guild_list = data.setdefault(str(ctx.guild.id), [])
        if action == "list":
            if not guild_list:
                await ctx.send("📋 Белый список пуст")
            else:
                lines = [f"• <@{uid}>" for uid in guild_list]
                await ctx.send("📋 **Белый список:**\n" + "\n".join(lines))
        elif action == "add" and user:
            if str(user.id) not in guild_list:
                guild_list.append(str(user.id))
                with open(self._whitelist_file(), "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                await ctx.send(f"✅ {user.mention} добавлен в белый список")
            else:
                await ctx.send("Уже в списке")
        elif action == "remove" and user:
            if str(user.id) in guild_list:
                guild_list.remove(str(user.id))
                with open(self._whitelist_file(), "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                await ctx.send(f"✅ {user.mention} удалён из белого списка")
            else:
                await ctx.send("Не в списке")
        else:
            await ctx.send("❌ Использование: `!modwhitelist list|add|remove @user`")

    # ─── LIST / STATS ─────────────────────────────────────
    @commands.command(name="tempmod", aliases=["tm"])
    @commands.has_permissions(moderate_members=True)
    async def tempmod_cmd(self, ctx):
        """Показать активные временные наказания"""
        guild_id = str(ctx.guild.id)
        mutes = self._mutes.get(guild_id, {})
        bans = self._bans.get(guild_id, {})
        kicks = self._kicks.get(guild_id, {})
        if not (mutes or bans or kicks):
            await ctx.send("📋 Нет активных временных наказаний")
            return
        embed = discord.Embed(title="⏱️ Активные временные наказания", color=0xFFD700)
        if mutes:
            text = ""
            for uid, info in mutes.items():
                rem = fmt_countdown(info["until"])
                text += f"🔇 <@{uid}> — {rem}\n   └ {info['reason'][:60]}\n"
            embed.add_field(name="Мьют", value=text[:1024] or "—", inline=False)
        if bans:
            text = ""
            for uid, info in bans.items():
                rem = fmt_countdown(info["until"])
                text += f"🔨 <@{uid}> — {rem}\n   └ {info['reason'][:60]}\n"
            embed.add_field(name="Баны", value=text[:1024] or "—", inline=False)
        if kicks:
            text = ""
            for uid, info in kicks.items():
                rem = fmt_countdown(info["until"])
                text += f"👢 {info.get('user_name', uid)} — {rem}\n   └ {info['reason'][:60]}\n"
            embed.add_field(name="Кики", value=text[:1024] or "—", inline=False)
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(TempModeration(bot))
