"""
AntiFake — защита от подделок (impersonation guard).

Ловит участников, которые выдают себя за администрацию/модерацию:
  • ник/имя визуально совпадает с именем админа (кириллица↔латиница,
    греческие буквы, цифры-хамелеоны «0->o», «1->l» и т.п.)
  • полностью скопирован аватар администратора

Действия при обнаружении (настраивается): strip | jail | kick | alert.

Дополнительно — детектор «замаскированной рекламы»: сообщение с
конфузабельными (поддельными) буквами + ссылкой/инвайтом удаляется,
автор получает страйк; 3 страйка за 7 дней — автоматический таймаут.

Команды: /antifake ... (админ).
"""

from logger import get_logger

_log = get_logger("impersonation")

import os
import re
import json
import time
import difflib
import unicodedata
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone, timedelta

from logger import get_logger

log = get_logger("antifake")

CFG_PATH = 'data/antifake.json'
STRIKES_PATH = 'data/antifake_strikes.json'

GOLD = 0xD4AF37
RED = 0xE74C3C
ORANGE = 0xE67E22
GREEN = 0x2ECC71
DIVIDER = "✦ ───────────────────── ✦"

DEFAULT_CFG = {
    "enabled": False,          # opt-in: владелец включает сам — по умолчанию ВЫКЛ
    "action": "strip",         # strip | jail | kick | alert
    "log_channel_id": 0,       # 0 = tagjail-лог → канал мод-логов
    "check_join": True,        # проверять при входе
    "check_update": True,      # проверять при смене ника/имени
    "check_ads": True,         # ловить замаскированную рекламу в чате
    "threshold": 0.85,         # порог похожести имён (0.6–1.0)
    "protected_names": [],     # дополнительные защищаемые строки (бренды, роли)
    "exempt_staff": True,      # не трогать админов/модераторов
    "dm_notify": True,         # DM нарушителю
    "strike_timeout": True,    # 3 страйка рекламы за 7 дней → таймаут 60 мин
}

ACTIONS_META = {
    "strip": "Снять ник",
    "jail": "В джейл (Tag Jail)",
    "kick": "Кикнуть",
    "alert": "Только журнал",
}

# Варианты действий — те самые Choice из слеш-команды /antifake action;
# на них же опирается веб-панель (имена/значения не расходятся никогда).
ACTION_CHOICES = [
    app_commands.Choice(name="Снять ник (по умолч.)", value="strip"),
    app_commands.Choice(name="В джейл (Tag Jail)", value="jail"),
    app_commands.Choice(name="Кикнуть", value="kick"),
    app_commands.Choice(name="Только журнал", value="alert"),
]

# Кириллица/греческие/цифры, визуально похожие на латиницу
_CONFUSABLES = str.maketrans({
    'а': 'a', 'А': 'a', 'ɑ': 'a', 'α': 'a',
    'е': 'e', 'Е': 'e', 'ё': 'e', 'Ё': 'e', 'ε': 'e',
    'о': 'o', 'О': 'o', 'ο': 'o', '0': 'o',
    'р': 'p', 'Р': 'p', 'ρ': 'p',
    'с': 'c', 'С': 'c', 'ϲ': 'c',
    'х': 'x', 'Х': 'x', 'χ': 'x',
    'у': 'y', 'У': 'y', 'υ': 'u',
    'к': 'k', 'К': 'k', 'κ': 'k',
    'м': 'm', 'М': 'm', 'μ': 'm',
    'т': 't', 'Т': 't', 'τ': 't', '7': 't',
    'в': 'b', 'В': 'b', 'ν': 'v',
    'н': 'h', 'Н': 'h', 'η': 'n', 'һ': 'h',
    'ѕ': 's', 'Ѕ': 's', '5': 's',
    'і': 'i', 'І': 'i', 'í': 'i', 'ι': 'i', '1': 'l', '!': 'i', '|': 'l',
    'ј': 'j', 'Ј': 'j',
    'ԁ': 'd', 'ԍ': 'g', 'з': '3',
    'ω': 'w', 'λ': 'n', 'Γ': 'r', 'г': 'r',
})

_ZERO_WIDTH = dict.fromkeys(map(ord, '​‌‍‎‏‪‫‬‭‮⁠'), None)

_AD_TRIGGERS = ('discord.gg', '.gg/', 'http://', 'https://', 'nitro', 'steamcommunity', 'steampowered')

STRIKE_WINDOW = 7 * 86400
STRIKE_LIMIT = 3


def normalize(text: str) -> str:
    """Каноническая форма: конфузабельные буквы → латиница, только a-z0-9."""
    if not text:
        return ""
    t = unicodedata.normalize('NFKC', str(text)).translate(_ZERO_WIDTH)
    t = t.casefold().translate(_CONFUSABLES)
    return re.sub(r'[^a-z0-9]+', '', t)


def has_confusables(text: str) -> bool:
    """В тексте есть буквы-хамелеоны (не ASCII-буквы, но визуально латиница)."""
    if not text:
        return False
    for ch in text:
        if ord(ch) > 127 and _CONFUSABLES.get(ord(ch)):
            return True
    return False


def similarity(a: str, b: str) -> float:
    """0..1 насколько имена визуально совпадают (с бонусом за вложенность)."""
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    r = difflib.SequenceMatcher(None, a, b).ratio()
    if len(a) >= 4 and len(b) >= 4 and (a in b or b in a):
        r = max(r, 0.92)
    return r


def _load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as _ex:
        _log.debug("_load_json(): подавлено: %s", _ex)
    return default


def _save_json(path, data):
    try:
        os.makedirs('data', exist_ok=True)
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception as e:
        log.error(f"[ANTIFAKE] ошибка записи {path}: {e}")


class AntiFake(commands.Cog):
    """Защита от подделок под администрацию + замаскированная реклама."""

    def __init__(self, bot):
        self.bot = bot
        self._configs = _load_json(CFG_PATH, {})
        self._strikes = _load_json(STRIKES_PATH, {})

    # ────────────────────────────────────────────────────────────
    # Конфиг / хранилище
    # ────────────────────────────────────────────────────────────
    def cfg(self, guild_id: int) -> dict:
        c = dict(DEFAULT_CFG)
        c.update(self._configs.get(str(guild_id), {}))
        return c

    def set_cfg(self, guild_id: int, key: str, value):
        self._configs.setdefault(str(guild_id), {})[key] = value
        _save_json(CFG_PATH, self._configs)

    # ────────────────────────────────────────────────────────────
    # Детекция
    # ────────────────────────────────────────────────────────────
    def _protected_members(self, guild: discord.Guild):
        """Администрация сервера: владелец + админы/модераторы."""
        out = []
        for m in guild.members:
            if m.bot:
                continue
            if m == guild.owner or m.guild_permissions.administrator \
                    or m.guild_permissions.manage_guild or m.guild_permissions.moderate_members:
                out.append(m)
        return out

    def protected_names(self, guild: discord.Guild):
        """[(user_id | None, display, norm)] защищаемые имена."""
        items = []
        for m in self._protected_members(guild):
            names = {m.display_name, m.nick, m.global_name, m.name} - {None, ""}
            for n in names:
                nn = normalize(n)
                if len(nn) >= 4:
                    items.append((m.id, n, nn, m))
        for s in self.cfg(guild.id).get('protected_names', []):
            nn = normalize(s)
            if len(nn) >= 4:
                items.append((None, str(s), nn, None))
        return items

    def is_exempt(self, member: discord.Member, cfg: dict) -> bool:
        if member.bot or member == member.guild.owner:
            return True
        if cfg.get('exempt_staff') and (
            member.guild_permissions.administrator
            or member.guild_permissions.manage_guild
            or member.guild_permissions.moderate_members
        ):
            return True
        return False

    def find_impersonation(self, member: discord.Member):
        """(target_name, target_member, score) лучшего совпадения или None."""
        cfg = self.cfg(member.guild.id)
        thr = float(cfg.get('threshold', 0.85))
        cand = {normalize(x) for x in (
            member.display_name, member.nick,
            getattr(member, 'global_name', None), member.name) if x}
        cand = {c for c in cand if len(c) >= 4}
        if not cand:
            return None
        best = None
        for tid, orig, norig, tmem in self.protected_names(member.guild):
            if tid == member.id:
                continue
            for cn in cand:
                sc = similarity(cn, norig)
                if sc >= thr and (best is None or sc > best[2]):
                    best = (orig, tmem, sc)
        return best

    def find_stolen_avatar(self, member: discord.Member):
        """Аватар полностью скопирован с администратора? → target member/None."""
        try:
            if not member.avatar:
                return None
            for m in self._protected_members(member.guild):
                if m.id == member.id or not m.avatar:
                    continue
                if m.avatar.key == member.avatar.key:
                    return m
        except Exception as _ex:
            _log.debug("find_stolen_avatar(): подавлено: %s", _ex)
        return None

    # ────────────────────────────────────────────────────────────
    # Лог / DM
    # ────────────────────────────────────────────────────────────
    async def _log_channel(self, guild: discord.Guild):
        ch_id = int(self.cfg(guild.id).get('log_channel_id', 0) or 0)
        ch = guild.get_channel(ch_id) if ch_id else None
        if ch is None:
            tj = self.bot.get_cog('TagJail')
            if tj:
                try:
                    tj_id = int(tj.cfg(guild.id).get('log_channel_id', 0) or 0)
                    ch = guild.get_channel(tj_id) if tj_id else None
                except Exception:
                    ch = None
        if ch is None:
            logs_cog = self.bot.get_cog('Logs')
            if logs_cog:
                try:
                    ch = await logs_cog.get_log_channel(guild, 'модерация')
                except Exception:
                    ch = None
        return ch

    async def _log(self, guild: discord.Guild, embed: discord.Embed):
        ch = await self._log_channel(guild)
        if ch:
            try:
                await ch.send(embed=embed)
            except Exception as _ex:
                _log.debug("_log(): подавлено: %s", _ex)

    async def _dm(self, member: discord.Member, embed: discord.Embed):
        if not self.cfg(member.guild.id).get('dm_notify'):
            return
        try:
            await member.send(embed=embed)
        except Exception as _ex:
            _log.debug("_dm(): подавлено: %s", _ex)

    # ────────────────────────────────────────────────────────────
    # Реакция на подделку
    # ────────────────────────────────────────────────────────────
    async def _punish(self, member: discord.Member, reason: str, target_name: str = None, score: float = 0.0):
        guild = member.guild
        cfg = self.cfg(guild.id)
        action = cfg.get('action', 'strip')
        done = action

        if action == 'jail':
            tj = self.bot.get_cog('TagJail')
            if tj and tj._jail_role(guild) is not None:
                ok = await tj.jail(member, reason, tag_found=f"антифейк: {target_name}" if target_name else None)
                if not ok:
                    action = 'strip'
            else:
                action = 'strip'

        if action == 'strip':
            if member.nick:
                try:
                    await member.edit(nick=None, reason=f"[AntiFake] {reason}")
                except Exception as e:
                    log.warning(f"[ANTIFAKE] {guild.name}: не смог снять ник {member}: {e}")
                    done = 'alert'
            else:
                # подделка в глобальном имени — ник снять нельзя
                done = 'alert'
        elif action == 'kick':
            try:
                await guild.kick(member, reason=f"[AntiFake] {reason}")
            except Exception as e:
                log.warning(f"[ANTIFAKE] {guild.name}: не смог кикнуть {member}: {e}")
                done = 'alert'

        dm = discord.Embed(color=RED, timestamp=datetime.now(timezone.utc))
        dm.description = (
            "## 🛡️ Защита сервера\n"
            f"Сервер: **{guild.name}**\n"
            "Ваше имя/аватар похожи на имя администрации сервера.\n"
            f"Действие: **{ACTIONS_META.get(done, done)}**\n"
            f"{'Похоже на: `' + str(target_name) + '`' if target_name else ''}\n"
            "Смените имя, если вы не администратор."
        )
        dm.set_footer(text=guild.name)
        await self._dm(member, dm)

        e = discord.Embed(color=RED, timestamp=datetime.now(timezone.utc))
        e.description = (
            "## 🎭 Подделка засечена\n"
            f"**{member.display_name}** · `{member.id}`\n\n"
            f"{reason}\n"
            f"Действие: **{ACTIONS_META.get(done, done)}**"
            + (f"\nПохоже на: **{target_name}** (совпадение {int(score * 100)}%)" if target_name else "")
            + f"\n{DIVIDER}"
        )
        e.set_footer(text=f"{guild.name} · anti-fake")
        await self._log(guild, e)
        return done

    async def evaluate(self, member: discord.Member, source: str):
        guild = member.guild
        cfg = self.cfg(guild.id)
        if not cfg.get('enabled') or self.is_exempt(member, cfg):
            return
        hit = self.find_impersonation(member)
        if hit:
            orig, _tmem, sc = hit
            await self._punish(member, f"Имя выдаёт себя за администрацию ({source}).", orig, sc)
            return
        stolen = self.find_stolen_avatar(member)
        if stolen:
            await self._punish(
                member,
                f"Аватар полностью скопирован с администратора **{stolen.display_name}** ({source}).",
                stolen.display_name, 1.0)

    # ────────────────────────────────────────────────────────────
    # Страйки рекламы
    # ────────────────────────────────────────────────────────────
    def _add_strike(self, guild_id: int, user_id: int) -> int:
        g = self._strikes.setdefault(str(guild_id), {})
        now = time.time()
        arr = [t for t in g.get(str(user_id), []) if now - t < STRIKE_WINDOW]
        arr.append(now)
        g[str(user_id)] = arr
        _save_json(STRIKES_PATH, self._strikes)
        return len(arr)

    def strike_view(self, guild_id: int) -> dict:
        """Страйки рекламы гильдии: {user_id: [метки времени]} (копия)."""
        return {u: list(a) for u, a
                in self._strikes.get(str(guild_id), {}).items()}

    def clear_strikes(self, guild_id: int, user_id: int) -> int:
        """Обнулить страйки пользователя. Возвращает, сколько снято."""
        g = self._strikes.setdefault(str(guild_id), {})
        arr = g.pop(str(user_id), [])
        _save_json(STRIKES_PATH, self._strikes)
        return len(arr)

    # ────────────────────────────────────────────────────────────
    # Слушатели
    # ────────────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if self.cfg(member.guild.id).get('check_join'):
            await self.evaluate(member, "вход на сервер")

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.display_name == after.display_name:
            return
        if self.cfg(after.guild.id).get('check_update'):
            await self.evaluate(after, "смена ника")

    @commands.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User):
        if (before.name, before.global_name) == (after.name, after.global_name):
            return
        for guild in self.bot.guilds:
            if not self.cfg(guild.id).get('check_update'):
                continue
            m = guild.get_member(after.id)
            if m:
                await self.evaluate(m, "смена имени")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        member = message.author
        if not isinstance(member, discord.Member):
            return
        cfg = self.cfg(message.guild.id)
        if not cfg.get('check_ads') or self.is_exempt(member, cfg):
            return
        content = message.content or ''
        if len(content) < 8 or not has_confusables(content):
            return
        norm = normalize(content)
        if not any(t in norm or t in content.lower() for t in _AD_TRIGGERS):
            return

        try:
            await message.delete()
        except Exception:
            return
        total = self._add_strike(message.guild.id, member.id)

        punished = ""
        if cfg.get('strike_timeout') and total >= STRIKE_LIMIT:
            try:
                try:
                    from services import mute_state
                    await mute_state.clear_voice_mute(message.guild, member)
                except Exception as _mse:
                    _log.debug('antifake timeout: очистка войс-мута: %s', _mse)
                await member.timeout(datetime.now(timezone.utc) + timedelta(minutes=60),
                                     reason="[AntiFake] замаскированная реклама (3 страйка)")
                punished = " · получен таймаут 60 мин"
            except Exception:
                punished = " · таймаут не удался (права)"

        dm = discord.Embed(color=ORANGE, timestamp=datetime.now(timezone.utc))
        dm.description = (
            "## ⚠️ Реклама замаскированными буквами\n"
            f"Сервер: **{message.guild.name}**\n"
            f"Ваше сообщение удалено (страйк **{total}/{STRIKE_LIMIT}**){punished}.\n"
            "Реклама без разрешения запрещена."
        )
        dm.set_footer(text=message.guild.name)
        await self._dm(member, dm)

        e = discord.Embed(color=ORANGE, timestamp=datetime.now(timezone.utc))
        e.description = (
            "## 🕵️ Замаскированная реклама\n"
            f"**{member.display_name}** · `{member.id}`\n"
            f"Канал: {message.channel.mention}\n\n"
            f"> {(content[:300] or '[вложение]')}\n\n"
            f"Страйк **{total}/{STRIKE_LIMIT}** за 7 дней{punished}\n{DIVIDER}"
        )
        e.set_footer(text=f"{message.guild.name} · anti-fake ads")
        await self._log(message.guild, e)

    # ────────────────────────────────────────────────────────────
    # Slash: /antifake
    # ────────────────────────────────────────────────────────────
    antifake = app_commands.Group(name="antifake", description="Защита от подделок администрации")

    def _cfg_embed(self, guild: discord.Guild) -> discord.Embed:
        cfg = self.cfg(guild.id)
        e = discord.Embed(color=GOLD if cfg.get('enabled') else 0x95A5A6,
                          timestamp=datetime.now(timezone.utc))
        ch = guild.get_channel(int(cfg.get('log_channel_id', 0) or 0))
        e.description = (
            "## 🎭 AntiFake\n"
            f"Система: **{'🟢 вкл' if cfg.get('enabled') else '🔴 выкл'}**\n"
            f"Действие: **{ACTIONS_META.get(cfg.get('action'), cfg.get('action'))}**\n"
            f"Порог похожести: **{int(float(cfg.get('threshold', 0.85)) * 100)}%**\n"
            f"Вход / смена имени: **{'вкл' if cfg.get('check_join') else 'выкл'}** / **{'вкл' if cfg.get('check_update') else 'выкл'}**\n"
            f"Анти-реклама: **{'вкл' if cfg.get('check_ads') else 'выкл'}**\n"
            f"Лог-канал: {ch.mention if ch else '`авто (мод-логи)`'}\n"
            f"Защищаемые строки: **{len(cfg.get('protected_names', []))}**\n{DIVIDER}"
        )
        e.set_footer(text=f"{guild.name} · anti-fake")
        return e

    @antifake.command(name="status", description="Показать настройки AntiFake")
    @app_commands.checks.has_permissions(administrator=True)
    async def af_status(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=self._cfg_embed(interaction.guild), ephemeral=True)

    @antifake.command(name="on", description="Включить AntiFake")
    @app_commands.checks.has_permissions(administrator=True)
    async def af_on(self, interaction: discord.Interaction):
        self.set_cfg(interaction.guild.id, 'enabled', True)
        await interaction.response.send_message(embed=self._cfg_embed(interaction.guild), ephemeral=True)

    @antifake.command(name="off", description="Выключить AntiFake")
    @app_commands.checks.has_permissions(administrator=True)
    async def af_off(self, interaction: discord.Interaction):
        self.set_cfg(interaction.guild.id, 'enabled', False)
        await interaction.response.send_message(embed=self._cfg_embed(interaction.guild), ephemeral=True)

    @antifake.command(name="action", description="Что делать с подделкой")
    @app_commands.describe(действие="Реакция на подделку")
    @app_commands.choices(действие=ACTION_CHOICES)
    @app_commands.checks.has_permissions(administrator=True)
    async def af_action(self, interaction: discord.Interaction, действие: app_commands.Choice[str]):
        self.set_cfg(interaction.guild.id, 'action', действие.value)
        await interaction.response.send_message(
            f"✅ Действие при подделке: **{действие.name}**", ephemeral=True)

    @antifake.command(name="threshold", description="Порог похожести имён (60–100%)")
    @app_commands.describe(процент="Число от 60 до 100")
    @app_commands.checks.has_permissions(administrator=True)
    async def af_threshold(self, interaction: discord.Interaction, процент: app_commands.Range[int, 60, 100]):
        self.set_cfg(interaction.guild.id, 'threshold', процент / 100.0)
        await interaction.response.send_message(f"✅ Порог похожести: **{процент}%**", ephemeral=True)

    @antifake.command(name="log-channel", description="Канал логов AntiFake")
    @app_commands.describe(канал="Текстовый канал")
    @app_commands.checks.has_permissions(administrator=True)
    async def af_log(self, interaction: discord.Interaction, канал: discord.TextChannel):
        self.set_cfg(interaction.guild.id, 'log_channel_id', канал.id)
        await interaction.response.send_message(f"✅ Лог-канал: {канал.mention}", ephemeral=True)

    @antifake.command(name="protect", description="Добавить защищаемое имя/строку (напр. бренд)")
    @app_commands.describe(текст="Строка, которую нельзя подделывать")
    @app_commands.checks.has_permissions(administrator=True)
    async def af_protect(self, interaction: discord.Interaction, текст: str):
        cfg = self.cfg(interaction.guild.id)
        arr = list(cfg.get('protected_names', []))
        if текст.strip() and текст not in arr:
            arr.append(текст)
            self.set_cfg(interaction.guild.id, 'protected_names', arr)
        await interaction.response.send_message(
            f"✅ Защищаемые строки ({len(arr)}): " + ", ".join(f"`{x}`" for x in arr), ephemeral=True)

    @antifake.command(name="unprotect", description="Убрать защищаемую строку")
    @app_commands.describe(текст="Строка для удаления")
    @app_commands.checks.has_permissions(administrator=True)
    async def af_unprotect(self, interaction: discord.Interaction, текст: str):
        cfg = self.cfg(interaction.guild.id)
        arr = [x for x in cfg.get('protected_names', []) if x != текст]
        self.set_cfg(interaction.guild.id, 'protected_names', arr)
        await interaction.response.send_message(
            f"✅ Осталось строк: **{len(arr)}**", ephemeral=True)

    @antifake.command(name="test", description="Проверить участника прямо сейчас (без наказания)")
    @app_commands.describe(пользователь="Кого проверить")
    @app_commands.checks.has_permissions(administrator=True)
    async def af_test(self, interaction: discord.Interaction, пользователь: discord.Member):
        await interaction.response.defer(ephemeral=True)
        hit = self.find_impersonation(пользователь)
        stolen = self.find_stolen_avatar(пользователь)
        e = discord.Embed(color=GREEN if not (hit or stolen) else RED,
                          timestamp=datetime.now(timezone.utc))
        lines = [f"## 🔍 Проверка {пользователь.mention}"]
        if hit:
            lines.append(f"🎭 Имя похоже на **{hit[0]}** (совпадение {int(hit[2] * 100)}%)")
        if stolen:
            lines.append(f"🖼 Аватар скопирован с **{stolen.display_name}**")
        if not hit and not stolen:
            lines.append("Чисто — подделки не найдено ✨")
        lines.append(DIVIDER)
        e.description = "\n".join(lines)
        await interaction.followup.send(embed=e, ephemeral=True)


async def setup(bot):
    await bot.add_cog(AntiFake(bot))
    log.info("[ANTIFAKE] Ког загружен")
