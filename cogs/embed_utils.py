"""
Hakumo — модуль Embed'ов и GIF
Все коги импортируют этот модуль — единый красивый стиль для всего бота.
"""
import discord
import random
from datetime import datetime, timezone

DIVIDER = "✦ ───────────────────── ✦"

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


def Hakumo_footer(guild=None, extra=""):
    text = f"Hakumo{' · ' + extra if extra else ''}"
    icon = guild.icon.url if guild and guild.icon else None
    return {"text": text, "icon_url": icon}


def _divider() -> str:
    return DIVIDER


# ── DM Embed (отправляется пользователю при наказании) ─────────────────────

def mod_dm_embed(action, guild, moderator, reason=None, extra_fields=None, gif_key=None):
    """DM-сообщение пользователю — минималистичный стиль"""
    configs = {
        "ban": {
            "title": "🚫 Вам закрыты каналы",
            "color": 0xE74C3C,
            "text": f"На сервере **{guild.name}** вам **закрыты все каналы** — остался только канал апелляции.",
            "note": "В канале апелляции можно обжаловать наказание. Опишите ситуацию, и модерация рассмотрит.",
            "gif": None,
        },
        "kick": {
            "title": "👢 Вы кикнуты",
            "color": 0xE67E22,
            "text": f"Вы были **кикнуты** с сервера **{guild.name}**.",
            "note": "Вы можете вернуться по ссылке-приглашению. Соблюдайте правила сервера.",
            "gif": "https://media.tenor.com/OtNpHMFHMhsAAAAC/kick-out.gif",
        },
        "timeout": {
            "title": "🔇 Вы в муте",
            "color": 0xF39C12,
            "text": f"На сервере **{guild.name}** вам **временно ограничена** отправка сообщений.",
            "note": "Мут будет снят автоматически по истечении срока.",
            "gif": "https://media.tenor.com/zjaHBJMFMIsAAAAC/shh-quiet.gif",
        },
        "untimeout": {
            "title": "🔊 Мут снят",
            "color": 0x2ECC71,
            "text": f"С вас **сняли мут** на сервере **{guild.name}**.",
            "note": "Вы снова можете отправлять сообщения. Соблюдайте правила сервера.",
            "gif": None,
        },
        "warn": {
            "title": "⚠️ Предупреждение",
            "color": 0xFF6B6B,
            "text": f"На сервере **{guild.name}** вы получили **предупреждение** за нарушение правил.",
            "note": "При накоплении предупреждений могут быть применены более строгие меры.",
            "gif": "https://media.tenor.com/xTMoHBqFkFkAAAAC/warning-caution.gif",
        },
        "mute_chat": {
            "title": "🔇 Мут чата",
            "color": 0xF39C12,
            "text": f"На сервере **{guild.name}** вам **временно ограничена** отправка сообщений.",
            "note": "Мут будет снят автоматически по истечении срока.",
            "gif": "https://media.tenor.com/zjaHBJMFMIsAAAAC/shh-quiet.gif",
        },
        "vmute": {
            "title": "🎙️ Войс-мут",
            "color": 0xF39C12,
            "text": f"На сервере **{guild.name}** ваш **микрофон заглушён**.",
            "note": "Микрофон будет включён модератором, когда наказание закончится.",
            "gif": None,
        },
        "vunmute": {
            "title": "🎙️ Войс-мут снят",
            "color": 0x2ECC71,
            "text": f"На сервере **{guild.name}** ваш **микрофон снова включён**.",
            "note": "Добро пожаловать обратно в голосовое общение!",
            "gif": None,
        },
        "unban": {
            "title": "🕊️ Бан снят",
            "color": 0x2ECC71,
            "text": f"С вас **сняли бан** на сервере **{guild.name}**.",
            "note": "Вы можете вернуться на сервер. Цените этот шанс.",
            "gif": None,
        },
    }
    cfg = configs.get(action, configs["warn"])

    e = discord.Embed(color=cfg["color"], timestamp=datetime.now(timezone.utc))

    desc = f"## {cfg['title']}\n"
    desc += f"### {cfg['text']}\n"
    desc += f"{DIVIDER}\n"
    desc += f"🏰 **Сервер:** {guild.name}\n"
    desc += f"🛡️ **Модератор:** {moderator.display_name}\n"
    desc += f"📝 **Причина:** {reason or 'Не указана'}\n"

    if extra_fields:
        desc += "\n"
        for name, value, inline in extra_fields:
            desc += f"**{name}:** {value}\n"

    desc += f"\n{DIVIDER}\n"
    desc += f"> {cfg['note']}"

    e.description = desc
    e.set_thumbnail(url=guild.icon.url if guild.icon else None)

    # GIF для действия
    if cfg.get("gif"):
        e.set_image(url=cfg["gif"])

    # Footer с иконкой сервера
    if guild.icon:
        e.set_footer(text=f"{guild.name} · Модерация", icon_url=guild.icon.url)
    else:
        e.set_footer(text=f"{guild.name} · Модерация")

    return e


# ── Mod Log Embed (отправляется в mod-log канал) ───────────────────────────

def mod_log_embed(action, title, color, user, moderator, guild, reason=None, case_id=None, extra_fields=None):
    """Embed для mod-log канала — минималистичный стиль"""
    e = discord.Embed(color=color, timestamp=datetime.now(timezone.utc))
    desc = (
        f"## {title}\n"
        f"**{user.display_name}** · `{user.id}`\n\n"
        f"🛡️ **Модератор:** {moderator.mention}\n"
        f"📝 **Причина:** {reason or 'Не указана'}\n"
    )
    if case_id:
        desc += f"📁 **Дело:** #{case_id}\n"
    if extra_fields:
        for name, value, inline in extra_fields:
            desc += f"**{name}:** {value}\n"
    desc += f"\n{DIVIDER}"
    e.description = desc
    e.set_thumbnail(url=user.display_avatar.url)
    e.set_footer(text=f"{guild.name} · Модерация")
    return e


# ── Общие Embed'ы ──────────────────────────────────────────────────────────

def success_embed(title, description, guild=None, gif_key=None, fields=None):
    """Успешное действие"""
    e = discord.Embed(color=0x2ECC71, timestamp=datetime.now(timezone.utc))
    desc = f"## ✅ {title}\n{description}"
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
    e.description = f"## ❌ {title}\n{description}"
    return e


def info_embed(title, description, guild=None):
    """Информация"""
    e = discord.Embed(color=0x3498DB, timestamp=datetime.now(timezone.utc))
    e.description = f"## ℹ️ {title}\n{description}"
    if guild:
        e.set_footer(text=f"{guild.name}")
    return e


def warning_embed(title, description):
    """Предупреждение"""
    e = discord.Embed(color=0xF39C12, timestamp=datetime.now(timezone.utc))
    e.description = f"## ⚠️ {title}\n{description}"
    return e


# ═══════════════════════════════════════════════════════════════════════
# УНИВЕРСАЛЬНЫЙ HAKUMO-КИТ — единый премиальный стиль для всех команд бота.
# Тёмно-золотой фирменный стиль: аккуратные акценты по типу системы,
# характерная кромка‑иконка, футер с именем сервера, живые метки времени.
# ═══════════════════════════════════════════════════════════════════════

GOLD = 0xD8A94E          # фирменное золото Hakumo
GOLD_DARK = 0x9A7A35     # приглушённое золото

KINDS = {
    #      (цвет,     эмодзи-кромка)
    'success': (0x2ECC71, ''),
    'error':   (0xED4245, ''),
    'info':    (GOLD, 'ℹ️'),
    'warn':    (0xF39C12, '⚠️'),
    'mod':     (0xE74C3C, '🛡️'),
    'jail':    (0xB03A2E, '🔒'),
    'ticket':  (0x5865F2, '🎫'),
    'music':   (GOLD, '🎵'),
    'voice':   (0x1ABC9C, '🎙️'),
    'ai':      (0x9B59B6, '🤖'),
    'logs':    (0x95A5A6, '📜'),
    'welcome': (GOLD, '👋'),
    'appeal':  (GOLD, '⚖️'),
    'system':  (0x607080, '⚙️'),
}


def hakumo_embed(kind, title, description=None, fields=None, guild=None,
                 footer_extra='', thumbnail=None):
    """Фирменный эмбед Hakumo: кромка-эмодзи в заголовке, цвет по типу системы,
    футер «Hakumo · <сервер>», живая метка времени.

    fields — список кортежей (имя, значение, inline) или (имя, значение).
    thumbnail override: None → не ставить; 'guild' → иконка сервера.
    """
    color, edge = KINDS.get(kind, KINDS['info'])
    e = discord.Embed(
        title=f'{edge} {title}'.strip() if edge and edge not in title else title,
        description=description or None,
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    for f in fields or ():
        if len(f) == 3:
            e.add_field(name=f[0], value=f[1], inline=f[2])
        else:
            e.add_field(name=f[0], value=f[1])
    foot = Hakumo_footer(guild, footer_extra) if guild else Hakumo_footer(None, footer_extra)
    e.set_footer(text=foot['text'], icon_url=foot['icon_url'])
    if thumbnail == 'guild' and guild and guild.icon:
        e.set_thumbnail(url=guild.icon.url)
    elif isinstance(thumbnail, str) and thumbnail:
        e.set_thumbnail(url=thumbnail)
    return e


class InterCtx:
    """Адаптер interaction → ctx-подобный объект.

    Позволяет старым телам команд (написанным под ctx.send/reply) работать
    из слеш-команд: reply()/send_with_icon() принимают его как ctx.
    """

    def __init__(self, interaction):
        self.interaction = interaction
        self.bot = getattr(interaction, 'client', None)
        self.author = interaction.user
        self.guild = interaction.guild
        self.channel = interaction.channel
        self.voice_client = None
        if self.bot is not None and interaction.guild is not None:
            try:
                self.voice_client = discord.utils.get(
                    self.bot.voice_clients, guild=interaction.guild)
            except Exception:
                self.voice_client = None

    async def send(self, content=None, embed=None, **kw):
        kw.pop('mention_author', None)
        if content is not None:
            kw['content'] = content
        if embed is not None:
            kw['embed'] = embed
        if not self.interaction.response.is_done():
            return await self.interaction.response.send_message(**kw)
        return await self.interaction.followup.send(**kw)

    async def reply(self, content=None, **kw):
        return await self.send(content, **kw)


async def reply(ctx, kind, title, description=None, **kw):
    """Быстрый красивый ответ: один вызов вместо сборки эмбеда руками.

    Кварги для send (ephemeral, view, file, files, delete_after,
    mention_author) пробрасываются в ctx.send, остальные — в hakumo_embed.
    """
    send_kw = {}
    for k in ('ephemeral', 'view', 'file', 'files', 'delete_after', 'mention_author'):
        if k in kw:
            send_kw[k] = kw.pop(k)
    if 'guild' not in kw and getattr(ctx, 'guild', None):
        kw['guild'] = ctx.guild
    return await ctx.send(embed=hakumo_embed(kind, title, description, **kw), **send_kw)


def bar(frac, width=12, filled='█', empty='░'):
    """Прогресс-бар: bar(0.4) → '████░░░░░░░░'."""
    frac = max(0.0, min(1.0, float(frac or 0)))
    n = round(frac * width)
    return filled * n + empty * (width - n)


def plural(n, one, few, many):
    """Русская плюрализация: plural(n, 'трек', 'трека', 'треков')."""
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not (12 <= n % 100 <= 14):
        return few
    return many


def fmt_duration(seconds):
    """Секунды → '1 ч 23 мин', '45 мин', '2 дн 3 ч'."""
    seconds = int(seconds or 0)
    if seconds <= 0:
        return '0 мин'
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes = seconds // 60
    if days:
        return f'{days} дн {hours} ч'
    if hours:
        return f'{hours} ч {minutes} мин'
    return f'{minutes} мин'


async def setup(bot):
    pass
