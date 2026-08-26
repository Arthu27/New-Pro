"""
Tag Jail — система «запрещённый тег».

Участники, в нике/имени которых найден запрещённый тег (тег чужого сервера,
рекламная строка, приглашение), автоматически отправляются в джейл:
роли снимаются и сохраняются, выдаётся jail-роль, лог в канал, DM с причиной.

Когда участник убирает запрещённый тег из имени — автоматическое освобождение
(можно выключить и выпускать вручную через /unjail).

Команды: /tagjail ... (админ), /jail, /unjail, /jailed (модераторы).
"""

from logger import get_logger

_log = get_logger("tag_jail")

import os
import json
import time
import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone

from logger import get_logger

log = get_logger("tag_jail")

CFG_PATH = 'data/tag_jail.json'
JAIL_PATH = 'data/tag_jailed.json'

GOLD = 0xD4AF37
RED = 0xE74C3C
GREEN = 0x2ECC71
DIVIDER = "✦ ───────────────────── ✦"

DEFAULT_CFG = {
    "enabled": False,           # система выключена до настройки
    "banned_tags": [],          # запрещённые теги/строки, напр. ["✞", ".gg/", "discord.gg"]
    "jail_role_id": 0,          # роль джейла (права настраиваете сами)
    "log_channel_id": 0,        # канал логов (0 = не слать)
    "auto_release": True,       # освобождать, когда тег убран из имени
    "jail_style": "remove",     # remove = снять роли (настоящий джейл) | keep = только jail-роль
    "on_join": True,            # проверять при входе
    "on_name_change": True,     # проверять при смене ника/имени
    "exempt_admins": True,      # админы/модераторы не трогаются
    "exempt_roles": [],         # id ролей-исключений
    "exempt_users": [],         # id пользователей-исключений
    "dm_notify": True,          # DM пользователю о джейле/освобождении
    "scan_on_boot": False,      # полный обход участников при запуске бота
    "min_account_days": 0,      # возрастная граница аккаунта (0 = выкл)
    "age_action": "kick",       # kick | jail — что делать с новичками
}

ROLE_EDIT_ERR = (
    "Не могу изменить роли — поднимите роль бота ВЫШЕ jail-роли "
    "и ролей заключённых в списке ролей сервера."
)


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
        log.error(f"[TAGJAIL] ошибка записи {path}: {e}")


class TagJail(commands.Cog):
    """Авто-джейл за запрещённые теги в имени."""

    # ── фирменный Hakumo-эмбед ─────────────────────────────────
    def _ae(self, kind, title, desc=None):
        from cogs.embed_utils import hakumo_embed
        return hakumo_embed(kind, title, desc)

    def __init__(self, bot):
        self.bot = bot
        self._configs = _load_json(CFG_PATH, {})
        self._jailed = _load_json(JAIL_PATH, {})
        self._scan_started = False

    # ────────────────────────────────────────────────────────────
    # Конфиг / хранилище
    # ────────────────────────────────────────────────────────────
    def cfg(self, guild_id: int) -> dict:
        gid = str(guild_id)
        c = dict(DEFAULT_CFG)
        c.update(self._configs.get(gid, {}))
        return c

    def set_cfg(self, guild_id: int, key: str, value):
        gid = str(guild_id)
        self._configs.setdefault(gid, {})
        self._configs[gid][key] = value
        _save_json(CFG_PATH, self._configs)

    def _jail_rec(self, guild_id: int, user_id: int):
        return self._jailed.get(str(guild_id), {}).get(str(user_id))

    def _set_jail_rec(self, guild_id: int, user_id: int, rec):
        self._jailed.setdefault(str(guild_id), {})[str(user_id)] = rec
        _save_json(JAIL_PATH, self._jailed)

    def _del_jail_rec(self, guild_id: int, user_id: int):
        self._jailed.get(str(guild_id), {}).pop(str(user_id), None)
        _save_json(JAIL_PATH, self._jailed)

    # ────────────────────────────────────────────────────────────
    # Логика проверки
    # ────────────────────────────────────────────────────────────
    def find_banned_tag(self, member: discord.Member, tags: list):
        """Имя/ник содержит запрещённый тег? Вернёт найденный или None."""
        haystacks = [
            member.display_name or "",
            member.nick or "",
            getattr(member, 'global_name', None) or "",
            member.name or "",
        ]
        joined = " || ".join(haystacks).lower()
        for tag in tags:
            t = str(tag).strip()
            if t and t.lower() in joined:
                return t
        return None

    def is_exempt(self, member: discord.Member, cfg: dict) -> bool:
        if member.bot or member == member.guild.owner:
            return True
        if cfg.get('exempt_admins') and (
            member.guild_permissions.administrator
            or member.guild_permissions.moderate_members
        ):
            return True
        if member.id in [int(x) for x in cfg.get('exempt_users', []) if str(x).lstrip('-').isdigit()]:
            return True
        exempt_roles = {int(x) for x in cfg.get('exempt_roles', []) if str(x).lstrip('-').isdigit()}
        return any(r.id in exempt_roles for r in member.roles)

    # ────────────────────────────────────────────────────────────
    # Джейл / освобождение
    # ────────────────────────────────────────────────────────────
    async def _log(self, guild: discord.Guild, embed: discord.Embed):
        ch_id = int(self.cfg(guild.id).get('log_channel_id', 0) or 0)
        if not ch_id:
            return
        ch = guild.get_channel(ch_id)
        if ch:
            try:
                await ch.send(embed=embed)
            except Exception as _ex:
                _log.debug("_log(): подавлено: %s", _ex)

    async def _dm(self, member: discord.Member, embed: discord.Embed):
        try:
            await member.send(embed=embed)
        except Exception as _ex:
            _log.debug("_dm(): подавлено: %s", _ex)

    def _jail_role(self, guild: discord.Guild):
        rid = int(self.cfg(guild.id).get('jail_role_id', 0) or 0)
        return guild.get_role(rid) if rid else None

    def _err_embed(self, title, desc):
        e = discord.Embed(color=RED, timestamp=datetime.now(timezone.utc))
        e.description = f"## ⚠️ {title}\n{desc}"
        return e

    async def jail(self, member: discord.Member, reason: str, tag_found: str = None):
        """Отправить участника в джейл (роли сохраняются)."""
        guild = member.guild
        cfg = self.cfg(guild.id)
        role = self._jail_role(guild)
        if role is None:
            log.warning(f"[TAGJAIL] {guild.name}: jail-роль не настроена!")
            return False

        rec = self._jail_rec(guild.id, member.id)
        stored_roles = rec['roles'] if rec else []

        # Снимаем роли (настоящий джейл) — только если записи ещё нет
        if cfg.get('jail_style') == 'remove' and not rec:
            me = guild.me
            removable = [r for r in member.roles[1:]
                         if r < me.top_role and not r.managed]
            stored_roles = [r.id for r in removable]
            if removable:
                try:
                    await member.remove_roles(*removable, reason=f"[TagJail] {reason}")
                except Exception as e:
                    log.warning(f"[TAGJAIL] {guild.name}: remove_roles {member}: {e}")

        if role not in member.roles:
            try:
                await member.add_roles(role, reason=f"[TagJail] {reason}")
            except discord.Forbidden:
                await self._log(guild, self._err_embed("Нет прав!", f"{member.mention}\n{ROLE_EDIT_ERR}"))
                return False
            except Exception as e:
                log.error(f"[TAGJAIL] ошибка add_roles: {e}")
                return False

        if not rec:
            self._set_jail_rec(guild.id, member.id, {
                'roles': stored_roles,
                'since': int(time.time()),
                'reason': reason,
                'tag': tag_found or '',
            })

        if cfg.get('dm_notify'):
            dm = discord.Embed(color=RED, timestamp=datetime.now(timezone.utc))
            dm.description = (
                "## ⛔ Вы в джейле\n"
                f"Сервер: **{guild.name}**\n"
                f"Причина: {reason}\n"
            )
            if tag_found:
                dm.description += (
                    f"\nВ вашем имени найден запрещённый тег: `{tag_found}`\n"
                    "Уберите его из ника — и вы будете освобождены"
                    f"{' автоматически' if cfg.get('auto_release') else ' после проверки модератором'}."
                )
            dm.set_footer(text=guild.name)
            await self._dm(member, dm)

        e = discord.Embed(color=RED, timestamp=datetime.now(timezone.utc))
        e.description = (
            "## ⛔ Tag Jail\n"
            f"**{member.display_name}** · `{member.id}`\n\n"
            f"Причина: {reason}"
            + (f"\nНайденный тег: `{tag_found}`" if tag_found else "")
            + f"\nРолей сохранено: **{len(stored_roles)}**\n{DIVIDER}"
        )
        e.set_footer(text=f"{guild.name} · tag-jail")
        await self._log(guild, e)
        return True

    async def release(self, member: discord.Member, reason: str, manual_by=None):
        """Освободить из джейла и вернуть сохранённые роли."""
        guild = member.guild
        rec = self._jail_rec(guild.id, member.id)
        role = self._jail_role(guild)

        if role and role in member.roles:
            try:
                await member.remove_roles(role, reason=f"[TagJail] {reason}")
            except Exception as _ex:
                _log.debug("release(): подавлено: %s", _ex)

        restored = 0
        if rec:
            to_restore = []
            me = guild.me
            for rid in rec.get('roles', []):
                r = guild.get_role(int(rid))
                if r and r < me.top_role and not r.managed:
                    to_restore.append(r)
            if to_restore:
                try:
                    await member.add_roles(*to_restore, reason=f"[TagJail] {reason}")
                    restored = len(to_restore)
                except Exception as e:
                    log.error(f"[TAGJAIL] ошибка возврата ролей: {e}")
            self._del_jail_rec(guild.id, member.id)

        e = discord.Embed(color=GREEN, timestamp=datetime.now(timezone.utc))
        e.description = (
            "## ✅ Освобождён из джейла\n"
            f"**{member.display_name}** · `{member.id}`\n\n"
            f"Причина: {reason}\n"
            f"Ролей возвращено: **{restored}**"
            + (f"\nМодератор: {manual_by.mention}" if manual_by else "")
            + f"\n{DIVIDER}"
        )
        e.set_footer(text=f"{guild.name} · tag-jail")
        await self._log(guild, e)

        if self.cfg(guild.id).get('dm_notify'):
            dm = discord.Embed(color=GREEN, timestamp=datetime.now(timezone.utc))
            dm.description = (
                "## ✅ Вы освобождены\n"
                f"Сервер: **{guild.name}**\n"
                f"Причина: {reason}\n"
                f"Ваши роли возвращены ({restored}). Добро пожаловать обратно!"
            )
            dm.set_footer(text=guild.name)
            await self._dm(member, dm)
        return True

    async def evaluate(self, member: discord.Member, trigger: str):
        """Проверить участника: тег есть → джейл; тега нет и сидит → авто-выход."""
        if member.guild is None:
            return
        cfg = self.cfg(member.guild.id)
        if not cfg.get('enabled'):
            return
        if self.is_exempt(member, cfg):
            return

        tag = self.find_banned_tag(member, cfg.get('banned_tags', []))
        rec = self._jail_rec(member.guild.id, member.id)

        if tag and not rec:
            await self.jail(member, f"Запрещённый тег в имени ({trigger})", tag_found=tag)
        elif not tag and rec and cfg.get('auto_release'):
            await self.release(member, "Тег убран из имени")

    # ────────────────────────────────────────────────────────────
    # События
    # ────────────────────────────────────────────────────────────
    async def _check_account_age(self, member: discord.Member, cfg: dict):
        """Возрастная граница: слишком новые аккаунты — kick или jail."""
        limit = int(cfg.get('min_account_days', 0) or 0)
        if limit <= 0 or self.is_exempt(member, cfg):
            return
        try:
            age_days = (datetime.now(timezone.utc) - member.created_at).days
        except Exception:
            return
        if age_days >= limit:
            return
        reason = f"Аккаунт слишком новый ({age_days} дн. < {limit} дн.)"
        if cfg.get('age_action', 'kick') == 'jail':
            await self.jail(member, reason)
            return
        # Auto-kick
        if cfg.get('dm_notify'):
            dm = discord.Embed(color=RED, timestamp=datetime.now(timezone.utc))
            dm.description = (
                "## ⛔ Ваш аккаунт слишком новый\n"
                f"Сервер: **{member.guild.name}**\n"
                f"Возраст аккаунта: **{age_days} дн.** — требуется минимум **{limit} дн.**\n"
                f"Возвращайтесь, когда аккаунту исполнится {limit} дней. 🙂"
            )
            dm.set_footer(text=member.guild.name)
            await self._dm(member, dm)
        try:
            await member.guild.kick(member, reason=f"[TagJail] {reason}")
        except discord.Forbidden:
            await self._log(member.guild, self._err_embed(
                "Нет прав!", f"{member.mention} — не могу кикнуть новый аккаунт (нужно право Kick Members)."))
            return
        except Exception as e:
            log.error(f"[TAGJAIL] ошибка age-kick: {e}")
            return
        e = discord.Embed(color=RED, timestamp=datetime.now(timezone.utc))
        e.description = (
            "## 🚪 Авто-кик: новый аккаунт\n"
            f"**{member.display_name}** · `{member.id}`\n\n"
            f"Возраст аккаунта: **{age_days} дн.** (лимит **{limit}**)\n{DIVIDER}"
        )
        e.set_footer(text=f"{member.guild.name} · age-gate")
        await self._log(member.guild, e)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        cfg = self.cfg(member.guild.id)
        if not cfg.get('enabled') or not cfg.get('on_join'):
            return
        try:
            await self._check_account_age(member, cfg)
            await self.evaluate(member, "вход на сервер")
        except Exception as e:
            log.error(f"[TAGJAIL] ошибка on_member_join: {e}")

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.display_name == after.display_name and before.nick == after.nick:
            return
        cfg = self.cfg(after.guild.id)
        if not cfg.get('enabled') or not cfg.get('on_name_change'):
            return
        try:
            await self.evaluate(after, "смена ника")
        except Exception as e:
            log.error(f"[TAGJAIL] ошибка on_member_update: {e}")

    @commands.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User):
        """Смена глобального имени/username — проверяем на всех серверах."""
        for guild in self.bot.guilds:
            cfg = self.cfg(guild.id)
            if not cfg.get('enabled') or not cfg.get('on_name_change'):
                continue
            member = guild.get_member(after.id)
            if member:
                try:
                    await self.evaluate(member, "смена имени профиля")
                except Exception as e:
                    log.error(f"[TAGJAIL] ошибка on_user_update: {e}")

    @commands.Cog.listener()
    async def on_ready(self):
        if self._scan_started:
            return
        self._scan_started = True
        for guild in self.bot.guilds:
            if self.cfg(guild.id).get('enabled') and self.cfg(guild.id).get('scan_on_boot'):
                self.bot.loop.create_task(self._sweep_guild(guild))

    # ────────────────────────────────────────────────────────────
    # Команды управления (админ)
    # ────────────────────────────────────────────────────────────
    tagjail = app_commands.Group(
        name="tagjail",
        description="Tag Jail: авто-джейл за запрещённые теги в имени",
        default_permissions=discord.Permissions(administrator=True),
    )

    def _cfg_embed(self, guild: discord.Guild) -> discord.Embed:
        c = self.cfg(guild.id)
        tags = c.get('banned_tags', [])
        jail_role = f"<@&{c['jail_role_id']}>" if c['jail_role_id'] else "⚠ не задана"
        log_ch = f"<#{c['log_channel_id']}>" if c['log_channel_id'] else "⚪ не задан"
        age_txt = (f"**{c.get('min_account_days')} дн.** (действие: {c.get('age_action', 'kick')})"
                   if c.get('min_account_days') else "⚪ выкл")
        e = discord.Embed(color=GOLD, timestamp=datetime.now(timezone.utc))
        e.description = (
            "## ⛔ Tag Jail — Настройки\n"
            f"Статус: {'🟢 **ВКЛ**' if c['enabled'] else '🔴 **ВЫКЛ**'}\n"
            f"Запрещённых тегов: **{len(tags)}**"
            + (f"\nТеги: {' · '.join('`' + t + '`' for t in tags[:15])}" if tags
               else "\nТеги: — *(добавьте: /tagjail add-tag)*")
            + f"\n{DIVIDER}\n"
            f"Jail-роль: {jail_role}\n"
            f"Лог-канал: {log_ch}\n"
            f"Режим: **{'роли снимаются (настоящий джейл)' if c['jail_style'] == 'remove' else 'только jail-роль сверху'}**\n"
            f"Авто-освобождение: {'🟢 вкл' if c['auto_release'] else '🔴 выкл'}\n"
            f"Проверка входов: {'🟢' if c['on_join'] else '🔴'} · смен имён: {'🟢' if c['on_name_change'] else '🔴'}\n"
            f"Исключения: админы {'🟢' if c['exempt_admins'] else '🔴'} · "
            f"ролей: {len(c['exempt_roles'])} · юзеров: {len(c['exempt_users'])}\n"
            f"Возрастная граница: {age_txt}"
        )
        e.set_footer(text=f"{guild.name} · сейчас в джейле: {len(self._jailed.get(str(guild.id), {}))}")
        return e

    @tagjail.command(name="status", description="Текущие настройки tag jail")
    @app_commands.checks.has_permissions(administrator=True)
    async def tj_durum(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=self._cfg_embed(interaction.guild), ephemeral=True)

    @tagjail.command(name="on", description="Включить tag jail")
    @app_commands.checks.has_permissions(administrator=True)
    async def tj_ac(self, interaction: discord.Interaction):
        c = self.cfg(interaction.guild.id)
        if not c.get('jail_role_id'):
            return await interaction.response.send_message(
                embed=self._ae("warn", "Сначала задайте jail-роль",
                               "Укажите роль заключённых: `/tagjail jail-role`"), ephemeral=True)
        if not c.get('banned_tags'):
            return await interaction.response.send_message(
                embed=self._ae("warn", "Сначала добавьте запрещённые теги",
                               "Без списка тегов ловить некого: `/tagjail add-tag`"), ephemeral=True)
        self.set_cfg(interaction.guild.id, 'enabled', True)
        await interaction.response.send_message(
            embed=self._ae("jail", "Tag Jail включён",
                           "У кого запрещённый тег в имени — отправится в джейл автоматически.\n"
                           "Проверить всех сразу: `/tagjail scan`"), ephemeral=True)

    @tagjail.command(name="off", description="Выключить tag jail")
    @app_commands.checks.has_permissions(administrator=True)
    async def tj_off(self, interaction: discord.Interaction):
        self.set_cfg(interaction.guild.id, 'enabled', False)
        await interaction.response.send_message(
            embed=self._ae("jail", "Tag Jail выключен", "Текущие заключённые не тронуты."), ephemeral=True)

    @tagjail.command(name="add-tag", description="Запретить тег/строку в имени (тег чужого сервера, '.gg/', 'discord.gg'...)")
    @app_commands.describe(текст="Тег или строка, запрещённая в имени (без учёта регистра)")
    @app_commands.checks.has_permissions(administrator=True)
    async def tj_tag_ekle(self, interaction: discord.Interaction, текст: str):
        c = self.cfg(interaction.guild.id)
        tags = list(c.get('banned_tags', []))
        if текст in tags:
            return await interaction.response.send_message(
                embed=self._ae("warn", "Тег уже в списке", f"`{текст}` давно под запретом."), ephemeral=True)
        tags.append(текст)
        self.set_cfg(interaction.guild.id, 'banned_tags', tags)
        await interaction.response.send_message(
            embed=self._ae("jail", "Тег запрещён",
                           f"`{текст}` — теперь под запретом (всего {len(tags)}).\n"
                           "Все, у кого он в нике/имени, отправятся в джейл."), ephemeral=True)

    @tagjail.command(name="del-tag", description="Убрать тег из запрещённых")
    @app_commands.describe(текст="Тег для удаления из списка")
    @app_commands.checks.has_permissions(administrator=True)
    async def tj_tag_sil(self, interaction: discord.Interaction, текст: str):
        tags = list(self.cfg(interaction.guild.id).get('banned_tags', []))
        if текст not in tags:
            return await interaction.response.send_message(
                embed=self._ae("warn", "Тег не найден", f"`{текст}` и так не запрещён."), ephemeral=True)
        tags.remove(текст)
        self.set_cfg(interaction.guild.id, 'banned_tags', tags)
        await interaction.response.send_message(
            embed=self._ae("success", "Тег разрешён", f"`{текст}` убран из запрещённых (осталось {len(tags)})."), ephemeral=True)

    @tagjail.command(name="tags", description="Список запрещённых тегов")
    @app_commands.checks.has_permissions(administrator=True)
    async def tj_taglar(self, interaction: discord.Interaction):
        tags = self.cfg(interaction.guild.id).get('banned_tags', [])
        if not tags:
            return await interaction.response.send_message(
                embed=self._ae("jail", "Список пуст", "Добавьте первый тег: `/tagjail add-tag`"), ephemeral=True)
        e = discord.Embed(color=GOLD)
        e.description = "## ⛔ Запрещённые теги\n" + "\n".join(
            f"`{i}.` **{t}**" for i, t in enumerate(tags, 1))
        await interaction.response.send_message(embed=e, ephemeral=True)

    @tagjail.command(name="jail-role", description="Задать jail-роль (её права вы настраиваете: закрыть каналы и т.д.)")
    @app_commands.describe(роль="Роль заключённых")
    @app_commands.checks.has_permissions(administrator=True)
    async def tj_jail_rol(self, interaction: discord.Interaction, роль: discord.Role):
        if роль >= interaction.guild.me.top_role:
            return await interaction.response.send_message(
                "❌ Эта роль выше моей — я не смогу её выдавать. Поднимите мою роль выше jail-роли.", ephemeral=True)
        self.set_cfg(interaction.guild.id, 'jail_role_id', роль.id)
        await interaction.response.send_message(
            f"✅ Jail-роль: {роль.mention}\n"
            "💡 Совет: в настройках каналов закройте этой роли всё, кроме одного канала джейла.", ephemeral=True)

    @tagjail.command(name="log-channel", description="Канал для логов tag jail")
    @app_commands.describe(канал="Текстовый канал для логов")
    @app_commands.checks.has_permissions(administrator=True)
    async def tj_log_kanal(self, interaction: discord.Interaction, канал: discord.TextChannel):
        self.set_cfg(interaction.guild.id, 'log_channel_id', канал.id)
        await interaction.response.send_message(
            embed=self._ae("logs", "Логи подключены", f"Tag jail пишет в {канал.mention}"), ephemeral=True)

    @tagjail.command(name="auto-release", description="Авто-освобождение, когда тег убран из имени")
    @app_commands.describe(режим="вкл — выходит сам, выкл — выпускает только модератор")
    @app_commands.choices(режим=[
        app_commands.Choice(name="вкл (сам выходит, убрав тег)", value="on"),
        app_commands.Choice(name="выкл (только через /unjail)", value="off"),
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def tj_oto_serbest(self, interaction: discord.Interaction, режим: str):
        self.set_cfg(interaction.guild.id, 'auto_release', режим == 'on')
        txt = ("включено — убрал тег, вышел автоматически" if режим == 'on'
               else "выключено — выпускает только модератор (/unjail)")
        await interaction.response.send_message(f"✅ Авто-освобождение: **{txt}**", ephemeral=True)

    @tagjail.command(name="style", description="Режим джейла: снимать роли или оставлять")
    @app_commands.describe(стиль="remove — роли снимаются, keep — только jail-роль сверху")
    @app_commands.choices(стиль=[
        app_commands.Choice(name="снимать роли (настоящий джейл, роли вернутся при выходе)", value="remove"),
        app_commands.Choice(name="оставить роли (добавляется только jail-роль)", value="keep"),
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def tj_stil(self, interaction: discord.Interaction, стиль: str):
        self.set_cfg(interaction.guild.id, 'jail_style', стиль)
        txt = ("роли снимаются и сохраняются (при выходе вернутся)" if стиль == 'remove'
               else "роли остаются, сверху только jail-роль")
        await interaction.response.send_message(f"✅ Режим джейла: **{txt}**", ephemeral=True)

    @tagjail.command(name="exempt-role", description="Роль-исключение: tag jail её не трогает (добавить/убрать)")
    @app_commands.describe(роль="Роль-исключение")
    @app_commands.checks.has_permissions(administrator=True)
    async def tj_muaf_rol(self, interaction: discord.Interaction, роль: discord.Role):
        lst = list(self.cfg(interaction.guild.id).get('exempt_roles', []))
        if роль.id in lst:
            lst.remove(роль.id)
            msg = f"➖ {роль.mention} убрана из исключений"
        else:
            lst.append(роль.id)
            msg = f"✅ {роль.mention} — исключение (tag jail эту роль не трогает)"
        self.set_cfg(interaction.guild.id, 'exempt_roles', lst)
        await interaction.response.send_message(msg, ephemeral=True)

    @tagjail.command(name="exempt-user", description="Пользователь-исключение: tag jail его не трогает (добавить/убрать)")
    @app_commands.describe(пользователь="Участник-исключение")
    @app_commands.checks.has_permissions(administrator=True)
    async def tj_muaf_uye(self, interaction: discord.Interaction, пользователь: discord.Member):
        lst = list(self.cfg(interaction.guild.id).get('exempt_users', []))
        if пользователь.id in lst:
            lst.remove(пользователь.id)
            msg = f"➖ {пользователь.mention} убран из исключений"
        else:
            lst.append(пользователь.id)
            msg = f"✅ {пользователь.mention} — в исключениях"
        self.set_cfg(interaction.guild.id, 'exempt_users', lst)
        await interaction.response.send_message(msg, ephemeral=True)

    async def _sweep_guild(self, guild: discord.Guild):
        """Обход всех участников: тег есть → джейл."""
        c = self.cfg(guild.id)
        jailed_now, checked = 0, 0
        for member in guild.members:
            if not c.get('enabled'):
                break
            checked += 1
            try:
                if self.is_exempt(member, c):
                    continue
                tag = self.find_banned_tag(member, c.get('banned_tags', []))
                if tag and not self._jail_rec(guild.id, member.id):
                    ok = await self.jail(member, "Запрещённый тег (полный обход)", tag_found=tag)
                    if ok:
                        jailed_now += 1
                    await asyncio.sleep(0.8)  # щадим rate-limit
            except Exception as e:
                log.error(f"[TAGJAIL] ошибка обхода ({member}): {e}")
        return checked, jailed_now

    @tagjail.command(name="scan", description="Проверить ВСЕХ участников прямо сейчас (обход сервера)")
    @app_commands.checks.has_permissions(administrator=True)
    async def tj_tara(self, interaction: discord.Interaction):
        if not self.cfg(interaction.guild.id).get('enabled'):
            return await interaction.response.send_message(
                embed=self._ae("warn", "Система выключена", "Сначала включите: `/tagjail on`"), ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        checked, jailed_now = await self._sweep_guild(interaction.guild)
        from cogs.embed_utils import plural
        await interaction.followup.send(
            embed=self._ae("jail", "Обход завершён",
                           f"Проверено: **{checked}** {plural(checked, 'участник', 'участника', 'участников')} · "
                           f"в джейл отправлено: **{jailed_now}**."), ephemeral=True)

    @tagjail.command(name="age-limit", description="Возрастная граница: мин. возраст аккаунта в днях (0 = выкл)")
    @app_commands.describe(дней="Минимальный возраст аккаунта. 0 — выключить проверку")
    @app_commands.checks.has_permissions(administrator=True)
    async def tj_age_limit(self, interaction: discord.Interaction, дней: int):
        if дней < 0:
            return await interaction.response.send_message(
                embed=self._ae("error", "Число не может быть отрицательным"), ephemeral=True)
        self.set_cfg(interaction.guild.id, 'min_account_days', дней)
        if дней == 0:
            await interaction.response.send_message(
            embed=self._ae("success", "Возрастная граница выключена"), ephemeral=True)
        else:
            action = self.cfg(interaction.guild.id).get('age_action', 'kick')
            await interaction.response.send_message(
                embed=self._ae("success", "Возрастная граница обновлена",
                           f"Аккаунты моложе **{дней} дн.** → **{action}** при входе.\n"
                           "Изменить действие: `/tagjail age-action`"), ephemeral=True)

    @tagjail.command(name="age-action", description="Что делать со слишком новыми аккаунтами")
    @app_commands.describe(действие="kick — выгнать, jail — посадить в джейл")
    @app_commands.choices(действие=[
        app_commands.Choice(name="kick — выгнать с сервера", value="kick"),
        app_commands.Choice(name="jail — посадить в джейл", value="jail"),
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def tj_age_action(self, interaction: discord.Interaction, действие: str):
        self.set_cfg(interaction.guild.id, 'age_action', действие)
        txt = ("выгонять с сервера (с DM-предупреждением)" if действие == 'kick'
               else "сажать в джейл (выпускает модератор)")
        await interaction.response.send_message(
            embed=self._ae("success", "Действие для новичков обновлено", f"Новые аккаунты теперь: **{txt}**"), ephemeral=True)

    # ────────────────────────────────────────────────────────────
    # Ручные команды модераторов
    # ────────────────────────────────────────────────────────────
    @app_commands.command(name="jail", description="Отправить участника в джейл вручную")
    @app_commands.describe(пользователь="Кого посадить", причина="Причина")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def jail_cmd(self, interaction: discord.Interaction, пользователь: discord.Member, причина: str = None):
        if пользователь.bot:
            return await interaction.response.send_message(
                embed=self._ae("warn", "Ботов не сажаем", "Джейл — только для людей."), ephemeral=True)
        if self._jail_rec(interaction.guild.id, пользователь.id):
            return await interaction.response.send_message(
                embed=self._ae("warn", "Он уже в джейле"), ephemeral=True)
        ok = await self.jail(
            пользователь,
            f"Ручной джейл — {interaction.user.display_name}: {причина or 'причина не указана'}")
        if ok:
            await interaction.response.send_message(
            embed=self._ae("jail", f"{пользователь.display_name} — в джейле",
                           f"Заключён модератором {interaction.user.display_name}."), ephemeral=True)
        else:
            await interaction.response.send_message(
                embed=self._ae("error", "Не получилось",
                               "Проверьте jail-роль (`/tagjail jail-role`) и мои права."), ephemeral=True)

    @app_commands.command(name="unjail", description="Освободить участника из джейла (роли вернутся)")
    @app_commands.describe(пользователь="Кого освободить", причина="Причина")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def unjail_cmd(self, interaction: discord.Interaction, пользователь: discord.Member, причина: str = None):
        if not self._jail_rec(interaction.guild.id, пользователь.id):
            role = self._jail_role(interaction.guild)
            if role and role in пользователь.roles:
                try:
                    await пользователь.remove_roles(role, reason=f"[TagJail] unjail {interaction.user}")
                except Exception as _ex:
                    _log.debug("unjail_cmd(): подавлено: %s", _ex)
                return await interaction.response.send_message(
                    embed=self._ae("success", "Jail-роль снята",
                                   f"Снята с **{пользователь.display_name}** (записи в джейле не было)."), ephemeral=True)
            return await interaction.response.send_message(
                embed=self._ae("warn", "Он не в джейле"), ephemeral=True)
        await self.release(пользователь, f"Освобождён модератором: {причина or '—'}", manual_by=interaction.user)
        await interaction.response.send_message(
            embed=self._ae("success", f"{пользователь.display_name} — на свободе", "Роли возвращены."), ephemeral=True)

    @app_commands.command(name="jailed", description="Список текущих заключённых tag jail")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def jailed_cmd(self, interaction: discord.Interaction):
        recs = self._jailed.get(str(interaction.guild.id), {})
        if not recs:
            return await interaction.response.send_message(
                embed=self._ae("jail", "Джейл пуст", "Сейчас там никого нет."), ephemeral=True)
        lines = []
        for uid, rec in list(recs.items())[:20]:
            since = f"<t:{rec.get('since', 0)}:R>"
            tag = f" · тег `{rec['tag']}`" if rec.get('tag') else ""
            lines.append(f"<@{uid}> · {since}{tag}")
        e = discord.Embed(color=RED, timestamp=datetime.now(timezone.utc))
        e.description = f"## ⛔ В джейле сейчас: {len(recs)}\n" + "\n".join(lines)
        e.set_footer(text=interaction.guild.name)
        await interaction.response.send_message(embed=e, ephemeral=True)


async def setup(bot):
    await bot.add_cog(TagJail(bot))
