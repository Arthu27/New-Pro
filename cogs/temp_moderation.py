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
from datetime import datetime, timedelta, timezone
from collections import defaultdict

from logger import get_logger
log = get_logger("temp_moderation")


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
        self._vmutes = {}    # guild_id -> {user_id: {until, reason, mod_id}} (VOICE mute)
        self._scheduled = [] # [{id, action, guild_id, user_id, mod_id, run_at, duration, reason}]
        self._cooldowns = {} # (user_id, action) -> last_time (anti-spam)
        self._load_state()
        # Запустить фоновые задачи
        self.check_expirations.start()
        self.run_scheduler.start()

    def cog_unload(self):
        self.check_expirations.cancel()
        self.run_scheduler.cancel()

    #  PERSISTENCE 
    def _mutes_file(self): return f"{DATA_DIR}/temp_mutes.json"
    def _bans_file(self): return f"{DATA_DIR}/temp_bans.json"
    def _kicks_file(self): return f"{DATA_DIR}/temp_kicks.json"
    def _scheduled_file(self): return f"{DATA_DIR}/temp_scheduled.json"
    def _vmutes_file(self): return f"{DATA_DIR}/temp_vmutes.json"
    def _history_file(self): return f"{DATA_DIR}/temp_history.json"
    def _whitelist_file(self): return f"{DATA_DIR}/temp_whitelist.json"

    def _load_state(self):
        """Load all data on startup"""
        for path, target in [
            (self._mutes_file(), "_mutes"),
            (self._bans_file(), "_bans"),
            (self._kicks_file(), "_kicks"),
            (self._vmutes_file(), "_vmutes"),
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
            log.info(f"[temp_mod] save {target}: {e}")

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
            log.info(f"[temp_mod] history: {e}")

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

    #  COMMANDS 

    #  VOICE MUTE (отдельно от chat mute/timeout) 


    #  EXPIRATION CHECKER 
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
                        except (discord.Forbidden, discord.HTTPException) as _ex:
                            log.debug("check_expirations(): подавлено: %s", _ex)
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
                    except (discord.NotFound, discord.Forbidden, discord.HTTPException) as _ex:
                        log.debug("check_expirations(): подавлено: %s", _ex)
                    del bans[user_id]
                    self._update_history_status(guild_id, user_id, "tempban", "expired")
        # Voice mutes
        for guild_id, vmutes in list(self._vmutes.items()):
            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                continue
            for user_id, info in list(vmutes.items()):
                if info["until"] <= now:
                    member = guild.get_member(int(user_id))
                    if member and member.voice and member.voice.mute:
                        try:
                            await member.edit(mute=False)
                        except (discord.Forbidden, discord.HTTPException) as _ex:
                            log.debug("check_expirations(): подавлено: %s", _ex)
                    del vmutes[user_id]
                    self._update_history_status(guild_id, user_id, "vmute", "expired")
        # Save
        self._save("_mutes", self._mutes_file())
        self._save("_bans", self._bans_file())
        self._save("_vmutes", self._vmutes_file())

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
        except Exception as _ex:
            log.debug("_update_history_status(): подавлено: %s", _ex)

    #  SCHEDULER 


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
                            until = datetime.now(timezone.utc) + timedelta(seconds=duration)
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

    #  WHITELIST 

    #  LIST / STATS 


async def setup(bot):
    await bot.add_cog(TempModeration(bot))
