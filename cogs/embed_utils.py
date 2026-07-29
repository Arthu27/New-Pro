"""
Aether Бот — Центральный модуль Embed & GIF
Все cog'и импортируют из этого модуля.
"""
import discord
import random
from datetime import datetime, timezone

GIFS = {
    "ban": ["https://media.tenor.com/x8v1oNUOmg4AAAAC/ban-hammer.gif","https://media.tenor.com/deECPGRKlmYAAAAC/ban-banned.gif","https://media.tenor.com/NkEMgMUMR6EAAAAC/banned-hammer.gif","https://media.tenor.com/Ug1IQKM5LXUAAAAC/ban-hammer-ban.gif"],
    "kick": ["https://media.tenor.com/OtNpHMFHMhsAAAAC/kick-out.gif","https://media.tenor.com/jTGCHqHKOGkAAAAC/kicked-out.gif"],
    "mute": ["https://media.tenor.com/zjaHBJMFMIsAAAAC/shh-quiet.gif"],
    "unmute": ["https://media.tenor.com/3Ky6UNqMFpkAAAAC/talking-speak.gif"],
    "warn": ["https://media.tenor.com/xTMoHBqFkFkAAAAC/warning-caution.gif"],
    "timeout": ["https://media.tenor.com/zjaHBJMFMIsAAAAC/shh-quiet.gif","https://media.tenor.com/xTMoHBqFkFkAAAAC/warning-caution.gif"],
    "untimeout": ["https://media.tenor.com/3Ky6UNqMFpkAAAAC/talking-speak.gif"],
    "unban": ["https://media.tenor.com/3Ky6UNqMFpkAAAAC/talking-speak.gif"],
    "ticket_open": ["https://media.tenor.com/3Ky6UNqMFpkAAAAC/talking-speak.gif"],
    "ticket_close": ["https://media.tenor.com/x8v1oNUOmg4AAAAC/ban-hammer.gif"],
    "ticket_panel": ["https://media.tenor.com/3Ky6UNqMFpkAAAAC/talking-speak.gif"],
    "giveaway_win": ["https://media.tenor.com/ZBDpMFBMFpkAAAAC/celebration-party.gif"],
    "giveaway_start": ["https://media.tenor.com/ZBDpMFBMFpkAAAAC/celebration-party.gif"],
    "apply_approved": ["https://media.tenor.com/ZBDpMFBMFpkAAAAC/celebration-party.gif"],
    "apply_rejected": ["https://media.tenor.com/x8v1oNUOmg4AAAAC/ban-hammer.gif"],
    "verify": ["https://media.tenor.com/3Ky6UNqMFpkAAAAC/talking-speak.gif"],
    "economy_win": ["https://media.tenor.com/ZBDpMFBMFpkAAAAC/celebration-party.gif"],
    "economy_lose": ["https://media.tenor.com/x8v1oNUOmg4AAAAC/ban-hammer.gif"],
    "economy_daily": ["https://media.tenor.com/ZBDpMFBMFpkAAAAC/celebration-party.gif"],
    "badge": ["https://media.tenor.com/ZBDpMFBMFpkAAAAC/celebration-party.gif"],
    "welcome": ["https://media.tenor.com/ZBDpMFBMFpkAAAAC/celebration-party.gif"],
    "error": ["https://media.tenor.com/x8v1oNUOmg4AAAAC/ban-hammer.gif"],
    "success": ["https://media.tenor.com/ZBDpMFBMFpkAAAAC/celebration-party.gif"],
    "duty_start": ["https://media.tenor.com/3Ky6UNqMFpkAAAAC/talking-speak.gif"],
    "duty_end": ["https://media.tenor.com/ZBDpMFBMFpkAAAAC/celebration-party.gif"],
}

def gif(category: str) -> str:
    pool = GIFS.get(category, GIFS["success"])
    return random.choice(pool)

def now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())

def Aether_footer(guild: discord.Guild = None, extra: str = "") -> dict:
    text = f"Aether{' • ' + extra if extra else ''}"
    icon = guild.icon.url if guild and guild.icon else None
    return {"text": text, "icon_url": icon}

def _divider() -> str:
    return "╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌"

def _action_header(action: str) -> str:
    headers = {
        "ban":       "🔨  ПОЖИЗНЕННЫЙ БАН",
        "kick":      "👢  ИСКЛЮЧЁН С СЕРВЕРА",
        "timeout":   "🔇  ВРЕМЕННЫЙ МУТ",
        "untimeout": "🔊  МУТ СНЯТ",
        "warn":      "⚠️  ПРЕДУПРЕЖДЕНИЕ",
        "unban":     "🔓  БАН СНЯТ",
    }
    return headers.get(action, "📋  УВЕДОМЛЕНИЕ")

def mod_dm_embed(action: str, guild: discord.Guild, moderator: discord.Member, reason: str = None, extra_fields: list = None, gif_key: str = None) -> discord.Embed:
    configs = {
        "ban": {
            "title": "🔨  Вы забанены на serverе",
            "color": 0xE74C3C,
            "badge": "🚫 ПОЖИЗНЕННЫЙ БАН",
            "desc": "Вы были **навсегда** удалены с serverа **{guild.name}**.\n\n> Если вы считаете это решение ошибочным,\n> свяжитесь с администрацией serverа.",
            "tip": "💡 Вы не сможете вернуться без ссылки-приглашения.",
        },
        "kick": {
            "title": "👢  Вы исключены с serverа",
            "color": 0xE67E22,
            "badge": "⚡ ИСКЛЮЧЕНИЕ",
            "desc": "Вы были исключены с serverа **{guild.name}**.\n\n> Вы можете вернуться по ссылке-приглашению.\n> Пожалуйста, соблюдайте правила serverа.",
            "tip": "💡 Используйте действующую ссылку-приглашение для возврата.",
        },
        "timeout": {
            "title": "🔇  Вы временно замьючены",
            "color": 0xF39C12,
            "badge": "⏳ МУТ",
            "desc": "На serverе **{guild.name}** ваше право отправлять\nсообщения **временно ограничено**.\n\n> Мут будет снят автоматически по истечении срока.",
            "tip": "💡 Во vakit мута вы можете читать channelы, но не писать.",
        },
        "untimeout": {
            "title": "🔊  Мут снят",
            "color": 0x2ECC71,
            "badge": "✅ СВОБОДЕН",
            "desc": "Ваш мут на serverе **{guild.name}** **снят**.\n\n> Теперь вы снова можете отправлять сообщения.\n> Пожалуйста, продолжайте соблюдать правила. 👋",
            "tip": "💡 Старайтесь не нарушать правила.",
        },
        "warn": {
            "title": "⚠️  Вы получили предупреждение",
            "color": 0xFF6B6B,
            "badge": "⚠️ ПРЕДУПРЕЖДЕНИЕ",
            "desc": "На serverе **{guild.name}** вы получили официальное\n**предупреждение** за нарушение правил.\n\n> При накоплении предупреждений могут быть применены\n> более строгие наказания.",
            "tip": "💡 Посетите channel #правила для ознакомления.",
        },
        "unban": {
            "title": "🔓  Бан снят",
            "color": 0x2ECC71,
            "badge": "✅ БАН СНЯТ",
            "desc": "Ваш бан на serverе **{guild.name}** **снят**.\n\n> Теперь вы можете вернуться на server.\n> Пожалуйста, цените этот шанс. 🤝",
            "tip": "💡 Для возврата вам может понадобиться ссылка-приглашение.",
        },
    }
    cfg = configs.get(action, configs["warn"])
    e = discord.Embed(title=cfg["title"], color=cfg["color"], timestamp=datetime.now(timezone.utc))
    desc = cfg['desc'].format(guild=guild)
    e.description = f"```ansi\n\u001b[1;31m{cfg['badge']}\u001b[0m\n```\n{_divider()}\n\n{desc}\n\n{_divider()}"
    e.set_thumbnail(url=guild.icon.url if guild.icon else None)
    e.add_field(name="🏰 Сервер", value=f"```{guild.name}```", inline=True)
    e.add_field(name="👮 Модератор", value=f"```{moderator.display_name}```", inline=True)
    e.add_field(name="🕐 Дата и vakit", value=f"<t:{now_ts()}:F>", inline=False)
    e.add_field(name="📝 Причина", value=f"```{reason or 'Не указана'}```", inline=False)
    if extra_fields:
        for name, value, inline in extra_fields:
            e.add_field(name=name, value=value, inline=inline)
    e.add_field(name="ℹ️ Информация", value=f"*{cfg['tip']}*", inline=False)
    e.set_image(url=gif(gif_key or action))
    e.set_footer(text=f"Aether Модерация • {guild.name}", icon_url=guild.icon.url if guild.icon else None)
    return e

def mod_log_embed(action: str, title: str, color: int, user: discord.Member, moderator: discord.Member, guild: discord.Guild, reason: str = None, case_id: int = None, extra_fields: list = None) -> discord.Embed:
    action_emojis = {"ban": "🔨", "kick": "👢", "timeout": "🔇", "untimeout": "🔊", "warn": "⚠️", "unban": "🔓"}
    emoji = action_emojis.get(action, "📋")
    e = discord.Embed(title=f"{emoji} {title}", color=color, timestamp=datetime.now(timezone.utc))
    e.set_thumbnail(url=user.display_avatar.url)
    e.set_author(name=f"{moderator.display_name} применил действие", icon_url=moderator.display_avatar.url)
    e.add_field(name="👤 Пользователь", value=f"{user.mention}\n`{user.name}` • `{user.id}`", inline=True)
    e.add_field(name="👮 Модератор", value=f"{moderator.mention}\n`{moderator.name}`", inline=True)
    if case_id:
        e.add_field(name="🆔 ID дела", value=f"```#{case_id}```", inline=True)
    e.add_field(name="📝 Причина", value=f"```{reason or 'Не указана'}```", inline=False)
    e.add_field(name="🕐 Время", value=f"<t:{now_ts()}:F> (<t:{now_ts()}:R>)", inline=False)
    if extra_fields:
        for name, value, inline in extra_fields:
            e.add_field(name=name, value=value, inline=inline)
    e.set_footer(text=f"Aether Модерация • {guild.name}", icon_url=guild.icon.url if guild.icon else None)
    return e

def success_embed(title: str, description: str, guild: discord.Guild = None, gif_key: str = None, fields: list = None) -> discord.Embed:
    e = discord.Embed(title=f"✅  {title}", description=description, color=0x2ECC71, timestamp=datetime.now(timezone.utc))
    if gif_key: e.set_image(url=gif(gif_key))
    if fields:
        for name, value, inline in fields:
            e.add_field(name=name, value=value, inline=inline)
    if guild:
        e.set_footer(text=f"Aether • {guild.name}", icon_url=guild.icon.url if guild.icon else None)
    return e

def error_embed(description: str, title: str = "Ошибка") -> discord.Embed:
    return discord.Embed(title=f"❌  {title}", description=f"```{description}```", color=0xE74C3C, timestamp=datetime.now(timezone.utc))

def info_embed(title: str, description: str, guild: discord.Guild = None) -> discord.Embed:
    e = discord.Embed(title=f"ℹ️  {title}", description=description, color=0x3498DB, timestamp=datetime.now(timezone.utc))
    if guild:
        e.set_footer(text=f"Aether • {guild.name}", icon_url=guild.icon.url if guild.icon else None)
    return e

def warning_embed(title: str, description: str) -> discord.Embed:
    return discord.Embed(title=f"⚠️  {title}", description=description, color=0xF39C12, timestamp=datetime.now(timezone.utc))
