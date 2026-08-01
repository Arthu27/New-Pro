"""
Leveling & Engagement System
============================
- Text XP (her mesajda 15-25 random XP, 60s cooldown)
- Voice XP (her минут 5 XP online, MUTE/DEAF/AFK hariç)
- Streak bonus (7+ gün üst üste günlük сообщение = 2x XP, 14+ gün = 3x)
- 50+ Achievement badges
- Level-up role rewards (configurable per guild)
- Daily/weekly/monthly leaderboards
- Auto-engagement: 24 часов inactive kullanıcılara DM
"""
import discord
from discord.ext import commands, tasks
import json
import os
import random
import time
from datetime import datetime, timedelta
from collections import defaultdict

from logger import get_logger
log = get_logger("leveling_engagement")


DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

# ACHIEVEMENTS CATALOG (50+) 
ACHIEVEMENTS = {
    # Milestone achievements
    "first_message":   {"name": "Первые шаги",        "desc": "Отправить первое сообщение",        "icon": "", "rarity": "common"},
    "messages_100":    {"name": "Болтун",              "desc": "100 сообщений",                      "icon": "", "rarity": "common"},
    "messages_500":    {"name": "Активист",            "desc": "500 сообщений",                      "icon": "", "rarity": "common"},
    "messages_1000":   {"name": "Душа компании",       "desc": "1,000 сообщений",                    "icon": "", "rarity": "uncommon"},
    "messages_5000":   {"name": "Легенда чата",        "desc": "5,000 сообщений",                    "icon": "", "rarity": "rare"},
    "messages_10000":  {"name": "Миф сервера",         "desc": "10,000 сообщений",                   "icon": "", "rarity": "epic"},
    "messages_50000":  {"name": "Бог дискорда",        "desc": "50,000 сообщений",                   "icon": "", "rarity": "legendary"},

    # Voice achievements
    "first_voice":     {"name": "Голос",               "desc": "Зайти в голосовой канал",            "icon": "", "rarity": "common"},
    "voice_1h":        {"name": "Чат-компаньон",       "desc": "1 час в голосе",                     "icon": "", "rarity": "common"},
    "voice_10h":       {"name": "Завсегдатай",         "desc": "10 часов в голосе",                  "icon": "", "rarity": "uncommon"},
    "voice_50h":       {"name": "Радиоведущий",        "desc": "50 часов в голосе",                  "icon": "", "rarity": "rare"},
    "voice_100h":      {"name": "Голосовой мастер",    "desc": "100 часов в голосе",                 "icon": "", "rarity": "epic"},
    "voice_500h":      {"name": "DJ сервера",          "desc": "500 часов в голосе",                 "icon": "", "rarity": "legendary"},

    # Level achievements
    "level_5":         {"name": "Новичок+",            "desc": "Достичь 5 уровня",                   "icon": "", "rarity": "common"},
    "level_10":        {"name": "Участник",            "desc": "Достичь 10 уровня",                  "icon": "", "rarity": "common"},
    "level_25":        {"name": "Ветеран",             "desc": "Достичь 25 уровня",                  "icon": "", "rarity": "uncommon"},
    "level_50":        {"name": "Элита",               "desc": "Достичь 50 уровня",                  "icon": "", "rarity": "rare"},
    "level_75":        {"name": "Магистр",             "desc": "Достичь 75 уровня",                  "icon": "", "rarity": "epic"},
    "level_100":       {"name": "Легенда",             "desc": "Достичь 100 уровня",                 "icon": "", "rarity": "legendary"},

    # Streak achievements
    "streak_3":        {"name": "Регулярный",          "desc": "3 дня подряд активности",            "icon": "", "rarity": "common"},
    "streak_7":        {"name": "Постоянный",          "desc": "7 дней подряд",                      "icon": "", "rarity": "uncommon"},
    "streak_14":       {"name": "Зависимый",           "desc": "14 дней подряд",                     "icon": "", "rarity": "rare"},
    "streak_30":       {"name": "Фанат сервера",       "desc": "30 дней подряд",                     "icon": "", "rarity": "epic"},
    "streak_100":      {"name": "Житель сервера",      "desc": "100 дней подряд",                    "icon": "", "rarity": "legendary"},

    # Social achievements
    "first_invite":    {"name": "Амбассадор",          "desc": "Пригласить первого друга",           "icon": "", "rarity": "common"},
    "invites_5":       {"name": "Вербовщик",           "desc": "5 приглашений",                      "icon": "", "rarity": "common"},
    "invites_25":      {"name": "Маркетолог",          "desc": "25 приглашений",                     "icon": "", "rarity": "uncommon"},
    "invites_100":     {"name": "Магнит для людей",    "desc": "100 приглашений",                    "icon": "", "rarity": "rare"},
    "invites_500":     {"name": "Рекрутер",            "desc": "500 приглашений",                    "icon": "", "rarity": "legendary"},

    # Moderation achievements
    "first_warn":      {"name": "Под наблюдением",     "desc": "Получить первое предупреждение",     "icon": "", "rarity": "common"},
    "no_warn_year":    {"name": "Безупречный",         "desc": "Год без предупреждений",             "icon": "", "rarity": "epic"},

    # Fun achievements
    "first_reaction":  {"name": "Эмоциональный",       "desc": "Поставить первую реакцию",           "icon": "", "rarity": "common"},
    "night_owl":       {"name": "Сова",                "desc": "Написать сообщение после 3 ночи",    "icon": "", "rarity": "uncommon"},
    "early_bird":      {"name": "Жаворонок",           "desc": "Написать сообщение до 6 утра",       "icon": "", "rarity": "uncommon"},
    "birthday":        {"name": "Именинник",           "desc": "Отпраздновать день рождения",        "icon": "", "rarity": "uncommon"},

    # Special achievements
    "first_command":   {"name": "Командующий",         "desc": "Использовать первую команду",        "icon": "", "rarity": "common"},
    "help_seeker":     {"name": "Любопытный",          "desc": "Открыть /help",                      "icon": "", "rarity": "common"},
    "pollster":        {"name": "Демократ",            "desc": "Участвовать в опросе",               "icon": "", "rarity": "common"},
    "trivia_win":      {"name": "Эрудит",              "desc": "Выиграть в викторине",               "icon": "", "rarity": "uncommon"},
    "giveaway_winner": {"name": "Счастливчик",         "desc": "Выиграть розыгрыш",                  "icon": "", "rarity": "uncommon"},
    "economy_rich":    {"name": "Богач",               "desc": "Заработать 10,000 монет",            "icon": "", "rarity": "rare"},
    "ticket_creator":  {"name": "Инициатор",           "desc": "Открыть первый тикет",               "icon": "", "rarity": "common"},
    "afk_artist":      {"name": "Творец AFK",          "desc": "Побывать в AFK 10 раз",              "icon": "", "rarity": "common"},

    # Event achievements
    "event_attendee":  {"name": "Участник события",    "desc": "Принять участие в ивенте",           "icon": "", "rarity": "common"},
    "event_host":      {"name": "Организатор",         "desc": "Создать событие",                    "icon": "", "rarity": "uncommon"},
    "first_boost":     {"name": "Бустер",              "desc": "Забустить сервер",                   "icon": "", "rarity": "rare"},
    "boost_3":         {"name": "Мега-бустер",         "desc": "3 активных буста",                   "icon": "", "rarity": "epic"},

    # Time-based
    "member_30d":      {"name": "Адаптировался",       "desc": "30 дней на сервере",                 "icon": "", "rarity": "common"},
    "member_1y":       {"name": "Старожил",            "desc": "1 год на сервере",                   "icon": "", "rarity": "epic"},
    "member_3y":       {"name": "Памятник",            "desc": "3 года на сервере",                  "icon": "", "rarity": "legendary"},
}

# XP curve: level n requires n² * 100 XP
def xp_for_level(level):
    return level * level * 100

def level_from_xp(xp):
    """Return (level, xp_into_level, xp_for_next_level)"""
    level = 0
    while xp >= xp_for_level(level + 1):
        level += 1
    cur = xp_for_level(level)
    nxt = xp_for_level(level + 1)
    return level, xp - cur, nxt - cur

# COG 
class LevelingEngagement(commands.Cog):
    """Level/engagement system with achievements, streaks, leaderboards"""

    def __init__(self, bot):
        self.bot = bot
        # In-memory caches
        self.text_cooldowns = {}   # (guild_id, user_id) -> last_xp_time
        self.voice_sessions = {}  # guild_id -> {user_id: joined_at}
        self.streaks = {}         # (guild_id, user_id) -> {last_day, count, multiplier}
        self.recent_levels = {}   # (guild_id, user_id) -> level (anti-spam)
        self.engagement_dm_sent = {}  # user_id -> last_dm_time
        self.bulk_save_pending = False

    # DATA PERSISTENCE 
    def _xp_file(self, guild_id):
        return f"{DATA_DIR}/xp_{guild_id}.json"

    def _config_file(self, guild_id):
        return f"{DATA_DIR}/leveling_config_{guild_id}.json"

    def _achievements_file(self, guild_id):
        return f"{DATA_DIR}/achievements_{guild_id}.json"

    def _streaks_file(self):
        return f"{DATA_DIR}/streaks.json"

    def load_xp(self, guild_id):
        f = self._xp_file(guild_id)
        if not os.path.exists(f):
            return {"users": {}, "achievements": {}, "level_rewards": {}}
        try:
            with open(f, "r", encoding="utf-8") as fp:
                return json.load(fp)
        except Exception:
            return {"users": {}, "achievements": {}, "level_rewards": {}}

    def save_xp(self, guild_id, data):
        try:
            with open(self._xp_file(guild_id), "w", encoding="utf-8") as fp:
                json.dump(data, fp, ensure_ascii=False, indent=2)
        except Exception as e:
            log.info(f"[leveling] save error: {e}")

    def load_config(self, guild_id):
        f = self._config_file(guild_id)
        if not os.path.exists(f):
            return self._default_config()
        try:
            with open(f, "r", encoding="utf-8") as fp:
                return json.load(fp)
        except Exception:
            return self._default_config()

    def save_config(self, guild_id, config):
        with open(self._config_file(guild_id), "w", encoding="utf-8") as fp:
            json.dump(config, fp, ensure_ascii=False, indent=2)

    def _default_config(self):
        return {
            "enabled": True,
            "text_xp": {"enabled": True, "min": 15, "max": 25, "cooldown_sec": 60},
            "voice_xp": {"enabled": True, "per_minute": 5, "min_online_sec": 60},
            "streak_bonus": {"enabled": True, "7_days": 2.0, "14_days": 3.0, "30_days": 5.0},
            "level_rewards": {
                "5":  {"role_id": None, "message": " Вы достигли 5 уровня!"},
                "10": {"role_id": None, "message": " 10 уровень — вы ветеран!"},
                "25": {"role_id": None, "message": " 25 уровень — почетный участник!"},
                "50": {"role_id": None, "message": " 50 уровень — элита сервера!"},
                "100":{"role_id": None, "message": " 100 уровень — ЛЕГЕНДА!"},
            },
            "achievements_enabled": True,
            "engagement_dm": {"enabled": True, "after_inactive_hours": 48, "message": " Скучаем по тебе на сервере! Заходи пообщаться."},
        }

    def load_streaks(self):
        f = self._streaks_file()
        if not os.path.exists(f):
            return {}
        try:
            with open(f, "r", encoding="utf-8") as fp:
                return json.load(fp)
        except Exception:
            return {}

    def save_streaks(self, data):
        try:
            with open(self._streaks_file(), "w", encoding="utf-8") as fp:
                json.dump(data, fp, ensure_ascii=False, indent=2)
        except Exception as e:
            log.info(f"[leveling] streaks save error: {e}")

    # STREAK TRACKING 
    def update_streak(self, guild_id, user_id):
        """Update daily streak for a user. Returns current streak count and multiplier."""
        data = self.load_streaks()
        key = f"{guild_id}_{user_id}"
        today = datetime.utcnow().date().isoformat()
        info = data.get(key, {"last_day": "", "count": 0})

        if info["last_day"] == today:
            return info["count"], 1.0  # already counted today

        yesterday = (datetime.utcnow().date() - timedelta(days=1)).isoformat()
        if info["last_day"] == yesterday:
            info["count"] += 1
        else:
            info["count"] = 1  # reset

        info["last_day"] = today
        data[key] = info
        self.save_streaks(data)

        # Multiplier
        cfg = self.load_config(guild_id)
        sb = cfg.get("streak_bonus", {})
        mult = 1.0
        if sb.get("enabled", True):
            if info["count"] >= 30: mult = sb.get("30_days", 5.0)
            elif info["count"] >= 14: mult = sb.get("14_days", 3.0)
            elif info["count"] >= 7: mult = sb.get("7_days", 2.0)
        return info["count"], mult

    # XP GIVING 
    async def add_xp(self, guild_id, user_id, amount, source="text"):
        """Add XP, check level up, return event info"""
        data = self.load_xp(guild_id)
        users = data.setdefault("users", {})
        u = users.setdefault(str(user_id), {
            "xp": 0, "level": 0, "messages": 0, "voice_minutes": 0,
            "last_message": 0, "last_voice": 0, "streak": 0, "joined_at": int(time.time())
        })
        u["xp"] += amount
        if source == "text":
            u["messages"] = u.get("messages", 0) + 1
        elif source == "voice":
            u["voice_minutes"] = u.get("voice_minutes", 0) + 1

        new_level, _, _ = level_from_xp(u["xp"])
        old_level = u.get("level", 0)
        leveled_up = new_level > old_level
        if leveled_up:
            u["level"] = new_level
            self.save_xp(guild_id, data)
            await self._handle_level_up(guild_id, user_id, new_level, old_level)
        else:
            self.save_xp(guild_id, data)
        return {"xp": u["xp"], "level": new_level, "leveled_up": leveled_up}

    async def _handle_level_up(self, guild_id, user_id, new_level, old_level):
        """Handle level-up: role reward, congratulations message, achievements"""
        cfg = self.load_config(guild_id)
        rewards = cfg.get("level_rewards", {})
        reward = rewards.get(str(new_level))
        guild = self.bot.get_guild(int(guild_id))
        if not guild:
            return
        member = guild.get_member(int(user_id))
        if not member:
            return

        # Role reward
        if reward and reward.get("role_id"):
            role = guild.get_role(int(reward["role_id"]))
            if role and role not in member.roles:
                try:
                    await member.add_roles(role, reason=f"Level {new_level} reward")
                except discord.Forbidden:
                    pass

        # Level-up message
        try:
            if reward and reward.get("message"):
                embed = discord.Embed(
                    title=f" Уровень {new_level}!",
                    description=reward["message"],
                    color=0xFFD700
                )
                embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
                await member.send(embed=embed)
        except discord.Forbidden:
            # DM closed — try system channel
            pass

        # Check level achievements
        achievement_map = {5: "level_5", 10: "level_10", 25: "level_25", 50: "level_50", 75: "level_75", 100: "level_100"}
        if new_level in achievement_map:
            await self.grant_achievement(guild_id, user_id, achievement_map[new_level])

    # ACHIEVEMENTS 
    async def grant_achievement(self, guild_id, user_id, achievement_id):
        cfg = self.load_config(guild_id)
        if not cfg.get("achievements_enabled", True):
            return False
        if achievement_id not in ACHIEVEMENTS:
            return False
        data = self.load_xp(guild_id)
        achs = data.setdefault("achievements", {})
        user_achs = achs.setdefault(str(user_id), [])
        if achievement_id in user_achs:
            return False  # already has it
        user_achs.append(achievement_id)
        self.save_xp(guild_id, data)

        # Notify
        ach = ACHIEVEMENTS[achievement_id]
        guild = self.bot.get_guild(int(guild_id))
        if not guild:
            return True
        member = guild.get_member(int(user_id))
        if not member:
            return True
        try:
            embed = discord.Embed(
                title=f" Достижение: {ach['name']}",
                description=f"{ach['icon']} {ach['desc']}",
                color=0xFFD700
            )
            await member.send(embed=embed)
        except discord.Forbidden:
            pass
        return True

    # TEXT XP 
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return
        guild_id = str(message.guild.id)
        user_id = str(message.author.id)

        cfg = self.load_config(guild_id)
        if not cfg.get("enabled", True) or not cfg["text_xp"].get("enabled", True):
            return

        # Cooldown
        now = time.time()
        key = (guild_id, user_id)
        last = self.text_cooldowns.get(key, 0)
        if now - last < cfg["text_xp"].get("cooldown_sec", 60):
            return
        self.text_cooldowns[key] = now

        # XP calculation
        xp = random.randint(cfg["text_xp"].get("min", 15), cfg["text_xp"].get("max", 25))
        streak_count, multiplier = self.update_streak(guild_id, user_id)
        xp = int(xp * multiplier)
        await self.add_xp(guild_id, user_id, xp, source="text")

        # Check milestones
        data = self.load_xp(guild_id)
        u = data.get("users", {}).get(user_id, {})
        msgs = u.get("messages", 0)
        if msgs == 1:    await self.grant_achievement(guild_id, user_id, "first_message")
        if msgs == 100:  await self.grant_achievement(guild_id, user_id, "messages_100")
        if msgs == 500:  await self.grant_achievement(guild_id, user_id, "messages_500")
        if msgs == 1000: await self.grant_achievement(guild_id, user_id, "messages_1000")
        if msgs == 5000: await self.grant_achievement(guild_id, user_id, "messages_5000")
        if msgs == 10000:await self.grant_achievement(guild_id, user_id, "messages_10000")
        if msgs == 50000:await self.grant_achievement(guild_id, user_id, "messages_50000")

        if streak_count == 3:   await self.grant_achievement(guild_id, user_id, "streak_3")
        if streak_count == 7:   await self.grant_achievement(guild_id, user_id, "streak_7")
        if streak_count == 14:  await self.grant_achievement(guild_id, user_id, "streak_14")
        if streak_count == 30:  await self.grant_achievement(guild_id, user_id, "streak_30")
        if streak_count == 100: await self.grant_achievement(guild_id, user_id, "streak_100")

        # Time-based
        hour = datetime.utcnow().hour
        if 3 <= hour < 6:  await self.grant_achievement(guild_id, user_id, "night_owl")
        if hour < 6:        await self.grant_achievement(guild_id, user_id, "early_bird")

    # VOICE XP 
    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot or not member.guild:
            return
        guild_id = str(member.guild.id)
        user_id = str(member.id)
        cfg = self.load_config(guild_id)
        if not cfg.get("enabled", True) or not cfg.get("voice_xp", {}).get("enabled", True):
            return

        # Joined voice
        if not before.channel and after.channel:
            self.voice_sessions.setdefault(guild_id, {})[user_id] = time.time()
            await self.grant_achievement(guild_id, user_id, "first_voice")
        # Left voice
        elif before.channel and not after.channel:
            sess = self.voice_sessions.get(guild_id, {}).pop(user_id, None)
            if sess:
                minutes = (time.time() - sess) / 60
                xp = int(minutes * cfg["voice_xp"].get("per_minute", 5))
                if xp > 0:
                    await self.add_xp(guild_id, user_id, xp, source="voice")
        # Mute/deafen/AFK — pause session
        elif after.channel:
            if after.self_mute or after.self_deaf or (after.afk if hasattr(after, 'afk') else False):
                sess = self.voice_sessions.get(guild_id, {}).pop(user_id, None)
                if sess:
                    minutes = (time.time() - sess) / 60
                    if minutes >= cfg["voice_xp"].get("min_online_sec", 60) / 60:
                        xp = int(minutes * cfg["voice_xp"].get("per_minute", 5))
                        await self.add_xp(guild_id, user_id, xp, source="voice")

    @tasks.loop(minutes=1)
    async def voice_xp_loop(self):
        """Award XP to users in voice channels every minute"""
        for guild_id, sessions in list(self.voice_sessions.items()):
            cfg = self.load_config(guild_id)
            if not cfg.get("voice_xp", {}).get("enabled", True):
                continue
            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                continue
            for user_id, joined_at in list(sessions.items()):
                member = guild.get_member(int(user_id))
                if not member or not member.voice or member.voice.self_mute or member.voice.self_deaf:
                    continue
                xp = cfg["voice_xp"].get("per_minute", 5)
                await self.add_xp(guild_id, user_id, xp, source="voice")
                # Voice time achievements
                data = self.load_xp(guild_id)
                u = data.get("users", {}).get(user_id, {})
                vmins = u.get("voice_minutes", 0)
                if vmins == 60:   await self.grant_achievement(guild_id, user_id, "voice_1h")
                if vmins == 600:  await self.grant_achievement(guild_id, user_id, "voice_10h")
                if vmins == 3000: await self.grant_achievement(guild_id, user_id, "voice_50h")
                if vmins == 6000: await self.grant_achievement(guild_id, user_id, "voice_100h")
                if vmins == 30000:await self.grant_achievement(guild_id, user_id, "voice_500h")

    @voice_xp_loop.before_loop
    async def before_voice_loop(self):
        await self.bot.wait_until_ready()

    # COMMANDS 
    @commands.command(name="xp-rank", aliases=["level-info"])
    async def rank(self, ctx, member: discord.Member = None):
        """Show your or someone else's rank card"""
        target = member or ctx.author
        guild_id = str(ctx.guild.id)
        data = self.load_xp(guild_id)
        u = data.get("users", {}).get(str(target.id))
        if not u:
            await ctx.send(f" {target.mention} ещё не набрал XP.")
            return
        level, xp_into, xp_needed = level_from_xp(u["xp"])
        # Leaderboard position
        sorted_users = sorted(data.get("users", {}).items(), key=lambda x: x[1].get("xp", 0), reverse=True)
        pos = next((i for i, (uid, _) in enumerate(sorted_users) if uid == str(target.id)), -1) + 1
        # Progress bar (20 chars)
        pct = xp_into / xp_needed if xp_needed else 1
        filled = int(pct * 20)
        bar = "" * filled + "" * (20 - filled)
        embed = discord.Embed(title=f" Ранг {target.display_name}", color=0xFFD700)
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Уровень", value=f"**{level}**", inline=True)
        embed.add_field(name="Всего XP", value=f"**{u['xp']:,}**", inline=True)
        embed.add_field(name="Позиция", value=f"#{pos}", inline=True)
        embed.add_field(name="Прогресс", value=f"`{bar}` {int(pct*100)}%\n{xp_into}/{xp_needed} XP до уровня {level+1}", inline=False)
        embed.add_field(name=" Сообщений", value=u.get("messages", 0), inline=True)
        embed.add_field(name=" Минут в войсе", value=u.get("voice_minutes", 0), inline=True)
        embed.add_field(name=" Streak", value=f"{u.get('streak', 0)} дн.", inline=True)
        # Achievements
        achs = data.get("achievements", {}).get(str(target.id), [])
        if achs:
            ach_text = " ".join(ACHIEVEMENTS[a]["icon"] for a in achs[-12:])
            embed.add_field(name=f" Достижения ({len(achs)})", value=ach_text or "—", inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="xp-leaderboard", aliases=["xp-top", "xp-lb"])
    async def leaderboard(self, ctx, scope: str = "all"):
        """Show top 10 users by XP"""
        guild_id = str(ctx.guild.id)
        data = self.load_xp(guild_id)
        users = data.get("users", {})
        sorted_users = sorted(users.items(), key=lambda x: x[1].get("xp", 0), reverse=True)[:10]
        if not sorted_users:
            await ctx.send(" Лидерборд пуст.")
            return
        lines = []
        medals = ["", "", ""] + [""] * 7
        for i, (uid, u) in enumerate(sorted_users):
            member = ctx.guild.get_member(int(uid))
            name = member.display_name if member else f"User#{uid}"
            level, _, _ = level_from_xp(u.get("xp", 0))
            lines.append(f"{medals[i]} **{name}** — Ур.{level} · {u.get('xp', 0):,} XP")
        embed = discord.Embed(title=" Топ-10 сервера", description="\n".join(lines), color=0xFFD700)
        await ctx.send(embed=embed)

    @commands.command(name="achievements", aliases=["ach", "badges"])
    async def achievements_cmd(self, ctx, member: discord.Member = None):
        """Show all achievements progress"""
        target = member or ctx.author
        guild_id = str(ctx.guild.id)
        data = self.load_xp(guild_id)
        achs = data.get("achievements", {}).get(str(target.id), [])
        # Group by rarity
        by_rarity = {"common": [], "uncommon": [], "rare": [], "epic": [], "legendary": []}
        for aid, info in ACHIEVEMENTS.items():
            unlocked = aid in achs
            by_rarity[info["rarity"]].append((aid, info, unlocked))
        embed = discord.Embed(title=f" Достижения {target.display_name}", color=0xFFD700)
        rarity_emoji = {"common": "", "uncommon": "🟢", "rare": "", "epic": "🟣", "legendary": "🟡"}
        for rarity in ["legendary", "epic", "rare", "uncommon", "common"]:
            items = by_rarity[rarity]
            unlocked_count = sum(1 for _, _, u in items if u)
            text = "\n".join(
                f"{'' if u else ''} {info['icon']} **{info['name']}** — {info['desc']}"
                for aid, info, u in items[:6]
            ) or "—"
            embed.add_field(
                name=f"{rarity_emoji[rarity]} {rarity.title()} ({unlocked_count}/{len(items)})",
                value=text[:1024], inline=False
            )
        embed.set_footer(text=f"Разблокировано: {len(achs)} / {len(ACHIEVEMENTS)}")
        await ctx.send(embed=embed)

    @commands.command(name="streak")
    async def streak_cmd(self, ctx, member: discord.Member = None):
        """Show streak info"""
        target = member or ctx.author
        data = self.load_streaks()
        key = f"{ctx.guild.id}_{target.id}"
        info = data.get(key, {"count": 0, "last_day": ""})
        days = info["count"]
        mult = 1.0
        cfg = self.load_config(str(ctx.guild.id))
        sb = cfg.get("streak_bonus", {})
        if sb.get("enabled"):
            if days >= 30: mult = sb.get("30_days", 5.0)
            elif days >= 14: mult = sb.get("14_days", 3.0)
            elif days >= 7:  mult = sb.get("7_days", 2.0)
        embed = discord.Embed(title=f" Streak {target.display_name}", color=0xFF6B35)
        embed.add_field(name="Дней подряд", value=f"**{days}**", inline=True)
        embed.add_field(name="XP множитель", value=f"**x{mult}**", inline=True)
        embed.add_field(name="Последний день", value=info.get("last_day", "—"), inline=True)
        # Progress to next milestone
        next_milestone = None
        if days < 7:    next_milestone = (7, "x2")
        elif days < 14: next_milestone = (14, "x3")
        elif days < 30: next_milestone = (30, "x5")
        if next_milestone:
            embed.add_field(name=" Следующий бонус", value=f"x{next_milestone[1]} через {next_milestone[0]-days} дн.", inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="toggle-leveling")
    @commands.has_permissions(administrator=True)
    async def toggle_leveling(self, ctx):
        """Toggle the entire leveling system on/off"""
        cfg = self.load_config(str(ctx.guild.id))
        cfg["enabled"] = not cfg.get("enabled", True)
        self.save_config(str(ctx.guild.id), cfg)
        status = " ВКЛЮЧЕН" if cfg["enabled"] else " ВЫКЛЮЧЕН"
        await ctx.send(f" Система уровней: **{status}**")

    @commands.group(name="levelset", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def levelset(self, ctx):
        """Configure leveling system"""
        cfg = self.load_config(str(ctx.guild.id))
        text = (
            f" **Настройки уровней**\n\n"
            f" Система: {'' if cfg.get('enabled') else ''}\n"
            f" Text XP: {cfg['text_xp']['min']}-{cfg['text_xp']['max']} (cooldown {cfg['text_xp']['cooldown_sec']}s)\n"
            f" Voice XP: {cfg['voice_xp']['per_minute']}/мин\n"
            f" Streak bonus: {'' if cfg['streak_bonus'].get('enabled') else ''} "
            f"(7д=x{cfg['streak_bonus'].get('7_days',2)}, 14д=x{cfg['streak_bonus'].get('14_days',3)}, 30д=x{cfg['streak_bonus'].get('30_days',5)})\n"
            f" Достижения: {'' if cfg.get('achievements_enabled') else ''}\n"
            f" Auto-DM: {'' if cfg['engagement_dm'].get('enabled') else ''} "
            f"({cfg['engagement_dm'].get('after_inactive_hours',48)}ч inactive)\n\n"
            f"**Команды:**\n"
            f"`!levelset text <min> <max> <cooldown>`\n"
            f"`!levelset voice <per_minute>`\n"
            f"`!levelset streak <7d> <14d> <30d>`\n"
            f"`!levelset achievement <on|off>`\n"
            f"`!levelset reward <level> <@role>` — задать роль за уровень\n"
        )
        await ctx.send(text)

    @levelset.command(name="text")
    async def levelset_text(self, ctx, min_xp: int, max_xp: int, cooldown: int):
        cfg = self.load_config(str(ctx.guild.id))
        cfg["text_xp"] = {"enabled": True, "min": min_xp, "max": max_xp, "cooldown_sec": cooldown}
        self.save_config(str(ctx.guild.id), cfg)
        await ctx.send(f" Text XP: {min_xp}-{max_xp} каждые {cooldown}s")

    @levelset.command(name="voice")
    async def levelset_voice(self, ctx, per_minute: int):
        cfg = self.load_config(str(ctx.guild.id))
        cfg["voice_xp"]["enabled"] = True
        cfg["voice_xp"]["per_minute"] = per_minute
        self.save_config(str(ctx.guild.id), cfg)
        await ctx.send(f" Voice XP: {per_minute} в минуту")

    @levelset.command(name="streak")
    async def levelset_streak(self, ctx, d7: float, d14: float, d30: float):
        cfg = self.load_config(str(ctx.guild.id))
        cfg["streak_bonus"] = {"enabled": True, "7_days": d7, "14_days": d14, "30_days": d30}
        self.save_config(str(ctx.guild.id), cfg)
        await ctx.send(f" Streak bonus: 7д=x{d7}, 14д=x{d14}, 30д=x{d30}")

    @levelset.command(name="achievement")
    async def levelset_ach(self, ctx, toggle: str):
        cfg = self.load_config(str(ctx.guild.id))
        enabled = toggle.lower() in ("on", "true", "1", "yes", "вкл")
        cfg["achievements_enabled"] = enabled
        self.save_config(str(ctx.guild.id), cfg)
        await ctx.send(f" Достижения: {' ВКЛ' if enabled else ' ВЫКЛ'}")

    @levelset.command(name="reward")
    async def levelset_reward(self, ctx, level: int, role: discord.Role):
        cfg = self.load_config(str(ctx.guild.id))
        cfg.setdefault("level_rewards", {})[str(level)] = {"role_id": str(role.id), "message": f" Достигнут уровень {level}! Роль: {role.name}"}
        self.save_config(str(ctx.guild.id), cfg)
        await ctx.send(f" За уровень {level} будет выдаваться роль {role.mention}")


async def setup(bot):
    await bot.add_cog(LevelingEngagement(bot))
