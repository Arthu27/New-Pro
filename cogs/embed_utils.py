"""
Aether Bot — Embed & GIF модуль
Все cog'и импортируют из этого модуля.
"""
import discord
import random
from datetime import datetime, timezone

DIVIDER = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

GIFS = {
    "ban": ["https://media.tenor.com/x8v1oNUOmg4AAAAC/ban-hammer.gif", "https://media.tenor.com/deECPGRKlmYAAAAC/ban-banned.gif"],
    "kick": ["https://media.tenor.com/OtNpHMFHMhsAAAAC/kick-out.gif"],
    "mute": ["https://media.tenor.com/zjaHBJMFMIsAAAAC/shh-quiet.gif"],
    "warn": ["https://media.tenor.com/xTMoHBqFkFkAAAAC/warning-caution.gif"],
    "timeout": ["https://media.tenor.com/zjaHBJMFMIsAAAAC/shh-quiet.gif"],
    "unban": ["https://media.tenor.com/3Ky6UNqMFpkAAAAC/talking-speak.gif"],
    "untimeout": ["https://media.tenor.com/3Ky6UNqMFpkAAAAC/talking-speak.gif"],
    "success": ["https://media.tenor.com/ZBDpMFBMFpkAAAAC/celebration-party.gif"],
    "error": ["https://media.tenor.com/x8v1oNUOmg4AAAAC/ban-hammer.gif"],
}


def gif(category: str) -> str:
    pool = GIFS.get(category, GIFS["success"])
    return random.choice(pool)


def now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def Aether_footer(guild=None, extra=""):
    text = f"Aether{' · ' + extra if extra else ''}"
    icon = guild.icon.url if guild and guild.icon else None
    return {"text": text, "icon_url": icon}


def _divider() -> str:
    return DIVIDER


# ─── DM Embed (отправляется пользователю) ────────────────────────────────────

def mod_dm_embed(action, guild, moderator, reason=None, extra_fields=None, gif_key=None):
    """DM сообщение пользователю — минимализм стиль"""
    configs = {
        "ban": {
            "title": "Вы забанены",
            "color": 0xE74C3C,
            "text": f"Вы были **навсегда** удалены с сервера **{guild.name}**.",
            "note": "Если вы считаете это решение ошибочным — свяжитесь с администрацией.",
        },
        "kick": {
            "title": "Вы исключены",
            "color": 0xE67E22,
            "text": f"Вы были исключены с сервера **{guild.name}**.",
            "note": "Вы можете вернуться по ссылке-приглашению. Соблюдайте правила.",
        },
        "timeout": {
            "title": "Вы замьючены",
            "color": 0xF39C12,
            "text": f"На сервере **{guild.name}** вам временно ограничена отправка сообщений.",
            "note": "Мут будет снят автоматически по истечении срока.",
        },
        "untimeout": {
            "title": "Мут снят",
            "color": 0x2ECC71,
            "text": f"Ваш мут на сервере **{guild.name}** снят.",
            "note": "Вы снова можете отправлять сообщения. Соблюдайте правила.",
        },
        "warn": {
            "title": "Предупреждение",
            "color": 0xFF6B6B,
            "text": f"На сервере **{guild.name}** вы получили предупреждение за нарушение правил.",
            "note": "При накоплении предупреждений могут быть применены более строгие наказания.",
        },
        "unban": {
            "title": "Бан снят",
            "color": 0x2ECC71,
            "text": f"Ваш бан на сервере **{guild.name}** снят.",
            "note": "Вы можете вернуться на сервер. Цените этот шанс.",
        },
    }
    cfg = configs.get(action, configs["warn"])

    e = discord.Embed(color=cfg["color"], timestamp=datetime.now(timezone.utc))
    desc = (
        f"## {cfg['title']}\n"
        f"{cfg['text']}\n\n"
        f"Модератор: **{moderator.display_name}**\n"
        f"Причина: {reason or 'Не указана'}\n"
    )
    if extra_fields:
        for name, value, inline in extra_fields:
            desc += f"{name}: {value}\n"
    desc += f"\n> {cfg['note']}"
    e.description = desc
    e.set_thumbnail(url=guild.icon.url if guild.icon else None)
    e.set_footer(text=f"{guild.name}")
    return e


# ─── Mod Log Embed (отправляется в mod-log канал) ────────────────────────────

def mod_log_embed(action, title, color, user, moderator, guild, reason=None, case_id=None, extra_fields=None):
    """Embed для mod-log канала — минимализм стиль"""
    e = discord.Embed(color=color, timestamp=datetime.now(timezone.utc))
    desc = (
        f"## {title}\n"
        f"**{user.display_name}** · `{user.id}`\n\n"
        f"Модератор: {moderator.mention}\n"
        f"Причина: {reason or 'Не указана'}\n"
    )
    if case_id:
        desc += f"Дело: **#{case_id}**\n"
    if extra_fields:
        for name, value, inline in extra_fields:
            desc += f"{name}: {value}\n"
    desc += f"\n{DIVIDER}"
    e.description = desc
    e.set_thumbnail(url=user.display_avatar.url)
    e.set_footer(text=f"{guild.name}")
    return e


# ─── Общие Embed'ы ────────────────────────────────────────────────────────────

def success_embed(title, description, guild=None, gif_key=None, fields=None):
    """Успешное действие"""
    e = discord.Embed(color=0x2ECC71, timestamp=datetime.now(timezone.utc))
    desc = f"## {title}\n{description}"
    if fields:
        desc += "\n"
        for name, value, inline in fields:
            desc += f"\n**{name}**: {value}"
    desc += f"\n\n{DIVIDER}"
    e.description = desc
    if gif_key:
        e.set_image(url=gif(gif_key))
    if guild:
        e.set_footer(text=f"{guild.name}")
    return e


def error_embed(description, title="Ошибка"):
    """Ошибка"""
    e = discord.Embed(color=0xE74C3C, timestamp=datetime.now(timezone.utc))
    e.description = f"## {title}\n{description}"
    return e


def info_embed(title, description, guild=None):
    """Информация"""
    e = discord.Embed(color=0x3498DB, timestamp=datetime.now(timezone.utc))
    e.description = f"## {title}\n{description}"
    if guild:
        e.set_footer(text=f"{guild.name}")
    return e


def warning_embed(title, description):
    """Предупреждение"""
    e = discord.Embed(color=0xF39C12, timestamp=datetime.now(timezone.utc))
    e.description = f"## {title}\n{description}"
    return e
