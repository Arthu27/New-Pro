"""
Инструменты модераторов (Pro-панель в один клик):

- ПКМ по пользователю → «Предупредить», «Забанить» (модалка с причиной)
- ПКМ по сообщению → «Варн за сообщение» (автору)
- /userinfo — карточка участника (+ досье warns/cases для модераторов)
- /cases — полная история нарушений (дела модерации + предупреждения + temp-история)
"""
import json
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone

from logger import get_logger

log = get_logger("mod_tools")

GOLD = 0xD4AF37
DIVIDER = "✦ ───────────────────── ✦"

ACTION_META = {
    'ban': ('🔨', 'Бан'), 'kick': ('👢', 'Кик'), 'timeout': ('🔇', 'Таймаут'),
    'mute': ('🔇', 'Мьют'), 'warn': ('⚠️', 'Варн'), 'unban': ('♻️', 'Разбан'),
    'unmute': ('🔊', 'Размьют'), 'vmute': ('🎙', 'Войс-мьют'),
}


class ReasonModal(discord.ui.Modal):
    """Модалка одной строки 'Причина' для контекстных действий."""

    reason = discord.ui.TextInput(
        label="Причина",
        placeholder="За что наказание? (необязательно)",
        required=False,
        max_length=300,
        style=discord.TextStyle.paragraph,
    )

    def __init__(self, title: str, handler):
        super().__init__(title=title[:45])
        self._handler = handler

    async def on_submit(self, interaction: discord.Interaction):
        await self._handler(interaction, str(self.reason.value).strip() or None)


def _fmt_ts(ts: int, style: str = 'R') -> str:
    return f"<t:{ts}:{style}>"


class ModTools(commands.Cog):
    """ПКМ-меню и быстрое досье участника."""

    def __init__(self, bot):
        self.bot = bot
        self.ctx_items = []

        self.ctx_warn_user = app_commands.ContextMenu(
            name="Предупредить",
            callback=self._warn_user_ctx,
        )
        self.ctx_warn_user.default_member_permissions = discord.Permissions(moderate_members=True)

        self.ctx_ban_user = app_commands.ContextMenu(
            name="Забанить",
            callback=self._ban_user_ctx,
        )
        self.ctx_ban_user.default_member_permissions = discord.Permissions(ban_members=True)

        self.ctx_warn_msg = app_commands.ContextMenu(
            name="Варн за сообщение",
            callback=self._warn_msg_ctx,
        )
        self.ctx_warn_msg.default_member_permissions = discord.Permissions(moderate_members=True)

        for cmd in (self.ctx_warn_user, self.ctx_ban_user, self.ctx_warn_msg):
            self.bot.tree.add_command(cmd)
            self.ctx_items.append(cmd)

    async def cog_unload(self):
        for cmd in self.ctx_items:
            try:
                self.bot.tree.remove_command(cmd.name, type=cmd.type)
            except Exception:
                pass

    # ────────────────────────────────────────────────────────────
    # ПКМ → Предупредить (user)
    # ────────────────────────────────────────────────────────────
    async def _warn_user_ctx(self, interaction: discord.Interaction, member: discord.Member):
        if interaction.guild is None:
            return await interaction.response.send_message("Работает только на сервере.", ephemeral=True)
        if member.bot:
            return await interaction.response.send_message("Ботов предупреждать нельзя.", ephemeral=True)

        async def _do(inter: discord.Interaction, reason):
            await self._apply_warn(inter, member, reason, origin="ПКМ")

        await interaction.response.send_modal(ReasonModal(f"Варн: {member.display_name}", _do))

    # ────────────────────────────────────────────────────────────
    # ПКМ → Варн за сообщение (message)
    # ────────────────────────────────────────────────────────────
    async def _warn_msg_ctx(self, interaction: discord.Interaction, message: discord.Message):
        if interaction.guild is None:
            return await interaction.response.send_message("Работает только на сервере.", ephemeral=True)
        member = message.author
        if not isinstance(member, discord.Member) or member.bot:
            return await interaction.response.send_message("Нельзя: автор — бот или покинул сервер.", ephemeral=True)

        async def _do(inter: discord.Interaction, reason):
            preview = (message.content or "[вложение]")[:100]
            full_reason = f"{reason or 'Не указана'} | msg: {message.jump_url}"
            await self._apply_warn(inter, member, full_reason, origin="ПКМ-сообщение", extra=f"Сообщение: {preview}")

        await interaction.response.send_modal(ReasonModal("Варн за сообщение", _do))

    async def _apply_warn(self, inter: discord.Interaction, member: discord.Member, reason, origin="ПКМ", extra: str = None):
        """Общий путь выдачи варна через ядро warnings-cog."""
        wcog = self.bot.get_cog("warnings")
        if wcog is None:
            return await inter.response.send_message("Модуль предупреждений не загружен.", ephemeral=True)
        try:
            warn_id, total, punishment = await wcog.add_warn(inter, member, reason)
        except Exception as e:
            log.error(f"[MOD_TOOLS] warn ctx hatası: {e}")
            return await inter.response.send_message(f"Не удалось выдать варн: {e}", ephemeral=True)

        # В дела модерации тоже — для /cases
        mcog = self.bot.get_cog("Moderation")
        if mcog:
            try:
                mcog.save_case(inter.guild.id, 'warn', member.id, inter.user.id, reason)
            except Exception:
                pass

        e = discord.Embed(color=discord.Color.dark_grey(), timestamp=datetime.now(timezone.utc))
        desc = (
            f"## Предупреждение выдано ({origin})\n"
            f"**{member.display_name}** · `{member.id}`\n\n"
            f"Предупреждение: **#{warn_id}**\n"
            f"Всего: **{total}**\n"
            f"Причина: {reason or 'Не указана'}"
        )
        if punishment:
            desc += f"\nАвто-наказание: **{punishment}**"
        if extra:
            desc += f"\n{extra}"
        desc += f"\n\n{DIVIDER}"
        e.description = desc
        e.set_footer(text=inter.guild.name)
        await inter.response.send_message(embed=e, ephemeral=True)

    # ────────────────────────────────────────────────────────────
    # ПКМ → Забанить (user)
    # ────────────────────────────────────────────────────────────
    async def _ban_user_ctx(self, interaction: discord.Interaction, member: discord.Member):
        if interaction.guild is None:
            return await interaction.response.send_message("Работает только на сервере.", ephemeral=True)
        if member.bot:
            return await interaction.response.send_message("Ботов банить через ПКМ нельзя.", ephemeral=True)
        if member == interaction.user:
            return await interaction.response.send_message("Себя банить не нужно.", ephemeral=True)

        async def _do(inter: discord.Interaction, reason):
            reason_txt = reason or "Без причины"
            # DM до бана — иначе пользователь недоступен
            mcog = self.bot.get_cog("Moderation")
            try:
                dm = discord.Embed(color=discord.Color.dark_grey(), timestamp=datetime.now(timezone.utc))
                dm.description = (
                    f"## Бан\n"
                    f"Сервер: **{inter.guild.name}**\n"
                    f"Модератор: **{inter.user.display_name}**\n"
                    f"Причина: {reason_txt}"
                )
                if mcog:
                    await mcog.send_dm(member, dm)
                else:
                    await member.send(embed=dm)
            except Exception:
                pass

            try:
                await inter.guild.ban(
                    member,
                    reason=f"[ПКМ] {reason_txt} — {inter.user}",
                    delete_message_seconds=0,
                )
            except discord.Forbidden:
                return await inter.response.send_message(
                    "❌ Не могу забанить: роль бота ниже роли пользователя или нет прав.", ephemeral=True)
            except Exception as e:
                return await inter.response.send_message(f"❌ Ошибка бана: {e}", ephemeral=True)

            case_id = 0
            if mcog:
                try:
                    case_id = mcog.save_case(inter.guild.id, 'ban', member.id, inter.user.id, reason_txt)
                except Exception:
                    pass

            e = discord.Embed(color=0xE74C3C, timestamp=datetime.now(timezone.utc))
            e.description = (
                f"## Бан выдан (ПКМ)\n"
                f"**{member.display_name}** · `{member.id}`\n\n"
                f"Причина: {reason_txt}\n"
                f"Модератор: {inter.user.mention}\n"
                f"Дело: **#{case_id}**\n\n{DIVIDER}"
            )
            e.set_footer(text=inter.guild.name)
            await inter.response.send_message(embed=e, ephemeral=True)
            if mcog:
                try:
                    await mcog.send_log(inter.guild, e)
                except Exception:
                    pass

        await interaction.response.send_modal(ReasonModal(f"Бан: {member.display_name}", _do))

    # ────────────────────────────────────────────────────────────
    # /cases — история нарушений
    # ────────────────────────────────────────────────────────────
    def _load_cases(self, guild_id: int, user_id: int) -> list:
        try:
            with open('data/mod_data.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
            return [c for c in data.get('cases', {}).get(str(guild_id), [])
                    if str(c.get('user_id')) == str(user_id)]
        except Exception:
            return []

    def _load_temp_history(self, guild_id: int, user_id: int) -> list:
        try:
            with open('data/temp_history.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list):
                return [h for h in data
                        if str(h.get('guild_id')) == str(guild_id) and str(h.get('user_id')) == str(user_id)]
            if isinstance(data, dict):
                return [h for h in data.get(str(guild_id), [])
                        if str(h.get('user_id')) == str(user_id)]
        except Exception:
            pass
        return []

    @app_commands.command(name="cases", description="Полная история нарушений пользователя (для модераторов)")
    @app_commands.describe(user="Участник сервера")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def cases(self, interaction: discord.Interaction, user: discord.Member):
        gid = interaction.guild.id
        cases = self._load_cases(gid, user.id)
        warns = []
        wcog = self.bot.get_cog("warnings")
        if wcog:
            try:
                warns = wcog._get_warns(gid, user.id)
            except Exception:
                pass
        temp_hist = self._load_temp_history(gid, user.id)
        total = len(cases) + len(warns) + len(temp_hist)

        e = discord.Embed(color=GOLD, timestamp=datetime.now(timezone.utc))
        e.set_author(name=f"Досье: {user.display_name}", icon_url=user.display_avatar.url)
        e.set_thumbnail(url=user.display_avatar.url)
        e.description = (
            f"**{user.mention}** · `{user.id}`\n"
            f"Дел: **{len(cases)}** · Предупреждений: **{len(warns)}** · Временных: **{len(temp_hist)}**\n"
            f"{DIVIDER}"
        )

        if cases:
            lines = []
            for c in cases[-6:][::-1]:
                ic, lbl = ACTION_META.get(c.get('action'), ('▪', c.get('action', '—')))
                date = str(c.get('timestamp', ''))[:10]
                lines.append(
                    f"`#{c.get('id')}` {ic} **{lbl}** — {str(c.get('reason', '—'))[:55]}\n"
                    f"   <@{c.get('mod_id')}> · `{date}`"
                )
            e.add_field(name="🗂 Дела модерации", value="\n".join(lines)[:1010], inline=False)

        if warns:
            wlines = [
                f"`#{w.get('id')}` {str(w.get('reason', '—'))[:70]} · `{str(w.get('timestamp', ''))[:10]}`"
                for w in warns[-4:][::-1]
            ]
            e.add_field(name="⚠️ Предупреждения", value="\n".join(wlines)[:1010], inline=False)

        if temp_hist:
            tlines = []
            for h in temp_hist[-3:][::-1]:
                act = h.get('action', '—')
                ic, lbl = ACTION_META.get(act, ('⏳', act))
                tlines.append(f"{ic} **{lbl}** {h.get('duration', '')} — {str(h.get('reason', '—'))[:45]}")
            e.add_field(name="⏳ Временные наказания", value="\n".join(tlines)[:1010], inline=False)

        if total == 0:
            e.description += "\nЧисто ✨ Нарушений не найдено."

        e.set_footer(text=f"{interaction.guild.name} · /userinfo для общей карточки")
        await interaction.response.send_message(embed=e, ephemeral=True)

    # ────────────────────────────────────────────────────────────
    # /userinfo — карточка участника
    # ────────────────────────────────────────────────────────────
    @app_commands.command(name="userinfo", description="Информация об участнике (модераторы видят досье)")
    @app_commands.describe(user="Участник (по умолчанию — вы)")
    async def userinfo(self, interaction: discord.Interaction, user: discord.Member = None):
        if interaction.guild is None:
            return await interaction.response.send_message("Работает только на сервере.", ephemeral=True)
        user = user or interaction.user
        if not isinstance(user, discord.Member):
            return await interaction.response.send_message("Этот пользователь не на сервере.", ephemeral=True)

        e = discord.Embed(color=GOLD, timestamp=datetime.now(timezone.utc))
        e.set_author(name=f"{user.display_name} (@{user.name})", icon_url=user.display_avatar.url)
        e.set_thumbnail(url=user.display_avatar.url)

        e.description = f"**{user.mention}** · `{user.id}`\n{DIVIDER}"
        e.add_field(
            name="📅 Аккаунт создан",
            value=f"{_fmt_ts(int(user.created_at.timestamp()), 'D')}\n({_fmt_ts(int(user.created_at.timestamp()))})",
            inline=True)
        if user.joined_at:
            e.add_field(
                name="📥 На сервере с",
                value=f"{_fmt_ts(int(user.joined_at.timestamp()), 'D')}\n({_fmt_ts(int(user.joined_at.timestamp()))})",
                inline=True)
        roles = [r.mention for r in reversed(user.roles[1:])][:8]
        more = len(user.roles) - 1 - len(roles)
        roles_txt = " ".join(roles) + (f" `+{more}`" if more > 0 else "") or "—"
        e.add_field(name=f"🎭 Роли ({len(user.roles) - 1})", value=roles_txt[:1000], inline=False)
        flags = []
        if user.guild_permissions.administrator:
            flags.append("👑 Администратор")
        elif user.guild_permissions.moderate_members:
            flags.append("🛡 Модератор")
        if user.premium_since:
            flags.append("💎 Бустер")
        if user.is_timed_out():
            flags.append("🔇 В таймауте")
        if flags:
            e.add_field(name="Статус", value=" · ".join(flags), inline=False)

        # Досье — только модераторам, ответ делаем ephemeral
        is_mod = (interaction.user.guild_permissions.moderate_members
                  or interaction.user.guild_permissions.administrator)
        ephemeral = False
        if is_mod:
            cases = self._load_cases(interaction.guild.id, user.id)
            warns = []
            wcog = self.bot.get_cog("warnings")
            if wcog:
                try:
                    warns = wcog._get_warns(interaction.guild.id, user.id)
                except Exception:
                    pass
            e.add_field(
                name="🛡 Досье (только модераторам)",
                value=(f"Дел: **{len(cases)}** · Предупреждений: **{len(warns)}**\n"
                       f"Подробная история: `/cases @{user.name}`"),
                inline=False)
            ephemeral = True

        e.set_footer(text=f"{interaction.guild.name}")
        await interaction.response.send_message(embed=e, ephemeral=ephemeral)

    @cases.error
    async def cases_error(self, interaction, error):
        await interaction.response.send_message("🚫 Нужны права модератора.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(ModTools(bot))
