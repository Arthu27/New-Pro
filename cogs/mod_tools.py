"""
Инструменты модераторов (Pro-панель в один клик):

- ПКМ по пользователю → «Предупредить», «Изолировать», «Войс-мут»,
  «Войс-размут», «Кик из войса» (модалка с причиной + доказательством)
- ПКМ по сообщению → «Варн за сообщение» (автору)
- /войс — голосовой контроль: select-меню канала → участник → действие
- /userinfo — карточка участника (+ досье warns/cases для модераторов)
- /cases — полная история нарушений (дела модерации + предупреждения + temp-история)
"""

from logger import get_logger

_log = get_logger("mod_tools")

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
    """Модалка 'Причина' (+ ссылка-доказательство) для контекстных действий."""

    def __init__(self, title: str, handler, require_proof=False):
        super().__init__(title=title[:45])
        self._handler = handler
        self._require_proof = require_proof
        self.reason = discord.ui.TextInput(
            label="Причина",
            placeholder="За что наказание? (необязательно)",
            required=False, max_length=300, style=discord.TextStyle.paragraph)
        self.add_item(self.reason)
        if require_proof:
            self.proof = discord.ui.TextInput(
                label="Доказательство (ссылка)",
                placeholder="https://… — скрин или видео нарушения (обязательно)",
                required=True, max_length=500)
            self.add_item(self.proof)

    async def on_submit(self, interaction: discord.Interaction):
        # Быстрый ack: DM + наказание может занять больше 3 секунд
        try:
            await interaction.response.defer(ephemeral=True)
        except Exception as _ex:
            _log.debug("on_submit(): подавлено: %s", _ex)
        proof = None
        if self._require_proof:
            proof = str(self.proof.value).strip() or None
            if not proof:
                await _respond(interaction,
                    content="🚫 Без доказательства (ссылка на скрин/видео) наказание не выдаётся.",
                    ephemeral=True)
                return
        await self._handler(interaction, str(self.reason.value).strip() or None, proof)


async def _respond(interaction, **kwargs):
    """Ответ без «Приложение не отвечает»: response → followup по обстоятельствам.

    Отправка не роняет контекстное действие: наказание уже могло быть
    применено — модератор обязан получить подтверждение.
    """
    try:
        if interaction.response.is_done():
            await interaction.followup.send(**kwargs)
        else:
            await interaction.response.send_message(**kwargs)
    except Exception:
        try:
            await interaction.followup.send(**kwargs)
        except Exception as _ex:
            _log.debug("_respond(): подавлено: %s", _ex)


def _fmt_ts(ts: int, style: str = 'R') -> str:
    return f"<t:{ts}:{style}>"


# ─── Голосовой контроль (/войс): select канал → участник → действие ────────

class VoiceChannelSelect(discord.ui.Select):
    def __init__(self, cog, guild, channels):
        self.cog = cog
        self.guild = guild
        options = [discord.SelectOption(
            label=(f"🔊 {c.name}" if c.name else "Канал")[:100] or "Канал",
            value=str(c.id),
            description=f"{sum(1 for m in c.members if not m.bot)} участников"
        ) for c in channels[:25]]
        super().__init__(placeholder="Выберите голосовой канал…", options=options,
                         min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        ch = self.guild.get_channel(int(self.values[0]))
        members = [m for m in ch.members if not m.bot] if ch else []
        if not members:
            return await interaction.response.send_message(
                "В этом канале никого нет.", ephemeral=True)
        await interaction.response.send_message(
            f"Канал **{ch.name}** — выберите участника:",
            view=VoiceMemberView(self.cog, ch, members), ephemeral=True)


class VoiceChannelView(discord.ui.View):
    def __init__(self, cog, guild, channels):
        super().__init__(timeout=300)
        self.add_item(VoiceChannelSelect(cog, guild, channels))


class VoiceMemberSelect(discord.ui.Select):
    def __init__(self, cog, channel, members):
        self.cog = cog
        self.channel = channel
        options = [discord.SelectOption(
            label=(str(m.display_name) or str(m.name))[:100] or "Участник",
            value=str(m.id)) for m in members[:25]]
        super().__init__(placeholder="Выберите участника…", options=options,
                         min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        member = self.channel.guild.get_member(int(self.values[0]))
        if member is None:
            return await interaction.response.send_message("Участник не найден.", ephemeral=True)
        await interaction.response.send_message(
            f"Участник **{member.display_name}** — выберите действие:",
            view=VoiceActionView(self.cog, member), ephemeral=True)


class VoiceMemberView(discord.ui.View):
    def __init__(self, cog, channel, members):
        super().__init__(timeout=300)
        self.add_item(VoiceMemberSelect(cog, channel, members))


class VoiceActionView(discord.ui.View):
    def __init__(self, cog, member):
        super().__init__(timeout=300)
        self.cog = cog
        self.member = member

        def _btn(label, style, action, require_proof):
            b = discord.ui.Button(label=label, style=style)

            async def _cb(interaction: discord.Interaction):
                async def _do(inter, reason, proof):
                    await self.cog._voice_action(inter, self.member, action, reason, proof)
                title = {'vmute': 'Войс-мут', 'vkick': 'Кик из войса',
                         'vunmute': 'Войс-размут'}.get(action, action)
                await interaction.response.send_modal(
                    ReasonModal(f"{title}: {self.member.display_name}", _do,
                                require_proof=require_proof))
            b.callback = _cb
            return b

        self.add_item(_btn("Войс-мут", discord.ButtonStyle.danger, 'vmute', True))
        self.add_item(_btn("Кик из войса", discord.ButtonStyle.danger, 'vkick', True))
        self.add_item(_btn("Войс-размут", discord.ButtonStyle.secondary, 'vunmute', False))


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
            name="Изолировать",
            callback=self._ban_user_ctx,
        )
        self.ctx_ban_user.default_member_permissions = discord.Permissions(ban_members=True)

        self.ctx_warn_msg = app_commands.ContextMenu(
            name="Варн за сообщение",
            callback=self._warn_msg_ctx,
        )
        self.ctx_warn_msg.default_member_permissions = discord.Permissions(moderate_members=True)

        self.ctx_vmute_user = app_commands.ContextMenu(
            name="Войс-мут",
            callback=self._vmute_user_ctx,
        )
        self.ctx_vmute_user.default_member_permissions = discord.Permissions(mute_members=True)

        self.ctx_vunmute_user = app_commands.ContextMenu(
            name="Войс-размут",
            callback=self._vunmute_user_ctx,
        )
        self.ctx_vunmute_user.default_member_permissions = discord.Permissions(mute_members=True)

        self.ctx_vkick_user = app_commands.ContextMenu(
            name="Кик из войса",
            callback=self._vkick_user_ctx,
        )
        self.ctx_vkick_user.default_member_permissions = discord.Permissions(move_members=True)

        for cmd in (self.ctx_warn_user, self.ctx_ban_user, self.ctx_warn_msg,
                    self.ctx_vmute_user, self.ctx_vunmute_user, self.ctx_vkick_user):
            self.bot.tree.add_command(cmd)
            self.ctx_items.append(cmd)

    async def cog_unload(self):
        for cmd in self.ctx_items:
            try:
                self.bot.tree.remove_command(cmd.name, type=cmd.type)
            except Exception as _ex:
                _log.debug("cog_unload(): подавлено: %s", _ex)

    # ────────────────────────────────────────────────────────────
    # ПКМ → Предупредить (user)
    # ────────────────────────────────────────────────────────────
    async def _warn_user_ctx(self, interaction: discord.Interaction, member: discord.Member):
        if interaction.guild is None:
            return await _respond(interaction, content="Работает только на сервере.", ephemeral=True)
        if member.bot:
            return await _respond(interaction, content="Ботов предупреждать нельзя.", ephemeral=True)

        async def _do(inter: discord.Interaction, reason, proof_link):
            await self._apply_warn(inter, member, reason, origin="ПКМ", proof_link=proof_link)

        await interaction.response.send_modal(
            ReasonModal(f"Варн: {member.display_name}", _do, require_proof=True))

    # ────────────────────────────────────────────────────────────
    # ПКМ → Варн за сообщение (message)
    # ────────────────────────────────────────────────────────────
    async def _warn_msg_ctx(self, interaction: discord.Interaction, message: discord.Message):
        if interaction.guild is None:
            return await _respond(interaction, content="Работает только на сервере.", ephemeral=True)
        member = message.author
        if not isinstance(member, discord.Member) or member.bot:
            return await _respond(interaction, content="Нельзя: автор — бот или покинул сервер.", ephemeral=True)

        async def _do(inter: discord.Interaction, reason, _proof=None):
            preview = (message.content or "[вложение]")[:100]
            full_reason = f"{reason or 'Не указана'} | msg: {message.jump_url}"
            await self._apply_warn(inter, member, full_reason, origin="ПКМ-сообщение",
                                   extra=f"Сообщение: {preview}", proof_link=message.jump_url)

        await interaction.response.send_modal(ReasonModal("Варн за сообщение", _do))

    async def _apply_warn(self, inter: discord.Interaction, member: discord.Member, reason, origin="ПКМ", extra: str = None, proof_link=None):
        """Общий путь выдачи варна через ядро warnings-cog."""
        wcog = self.bot.get_cog("warnings")
        if wcog is None:
            return await _respond(inter, content="Модуль предупреждений не загружен.", ephemeral=True)
        try:
            warn_id, total, punishment = await wcog.add_warn(inter, member, reason)
        except Exception as e:
            log.error(f"[MOD_TOOLS] ошибка warn ctx: {e}")
            return await _respond(inter, content=f"Не удалось выдать варн: {e}", ephemeral=True)

        # В дела модерации тоже — для /cases
        mcog = self.bot.get_cog("Moderation")
        if mcog:
            try:
                mcog.save_case(inter.guild.id, 'warn', member.id, inter.user.id, reason)
            except Exception as _ex:
                _log.debug("_apply_warn(): подавлено: %s", _ex)

        # Доказательство — в канал доказательств (ссылка из ПКМ/сообщения).
        proof_note = None
        try:
            if proof_link:
                from cogs.proof_cog import try_deliver_proof
                proof_note = await try_deliver_proof(self.bot, inter.guild, inter.user,
                                                     member, 'варн', reason, link=proof_link)
        except Exception as _pe:
            log.debug(f"[MOD_TOOLS] демка: {_pe}")

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
        if proof_note:
            desc += f"\n{proof_note}"
        desc += f"\n\n{DIVIDER}"
        e.description = desc
        e.set_footer(text=inter.guild.name)
        await _respond(inter, embed=e, ephemeral=True)

    # ────────────────────────────────────────────────────────────
    # ПКМ → Изолировать (user)
    # ────────────────────────────────────────────────────────────
    async def _ban_user_ctx(self, interaction: discord.Interaction, member: discord.Member):
        if interaction.guild is None:
            return await _respond(interaction, content="Работает только на сервере.", ephemeral=True)
        if member.bot:
            return await _respond(interaction, content="Ботов изолировать нельзя.", ephemeral=True)
        if member == interaction.user:
            return await _respond(interaction, content="Себя изолировать не нужно.", ephemeral=True)

        async def _do(inter: discord.Interaction, reason, proof_link):
            reason_txt = reason or "Без причины"
            mcog = self.bot.get_cog("Moderation")
            # DM до изоляции
            try:
                dm = discord.Embed(color=discord.Color.dark_grey(), timestamp=datetime.now(timezone.utc))
                dm.description = (
                    "## Вам закрыты каналы\n"
                    f"Сервер: **{inter.guild.name}**\n"
                    f"Модератор: **{inter.user.display_name}**\n"
                    f"Причина: {reason_txt}\n\n"
                    "Открыт только канал апелляции — там можно обжаловать."
                )
                if mcog:
                    await mcog.send_dm(member, dm)
                else:
                    await member.send(embed=dm)
            except Exception as _ex:
                _log.debug("_do(): подавлено: %s", _ex)

            try:
                if mcog and hasattr(mcog, '_isolate_member'):
                    _iso, _closed = await mcog._isolate_member(inter.guild, member, reason_txt)
                else:
                    _iso, _closed = None, 0
            except Exception as _ex:
                _log.debug("_do(): изоляция: %s", _ex)
                _iso, _closed = None, 0

            case_id = 0
            if mcog:
                try:
                    case_id = mcog.save_case(inter.guild.id, 'ban', member.id, inter.user.id, reason_txt)
                except Exception as _ex:
                    _log.debug("_do(): подавлено: %s", _ex)

            proof_note = None
            try:
                if proof_link:
                    from cogs.proof_cog import try_deliver_proof
                    proof_note = await try_deliver_proof(self.bot, inter.guild, inter.user,
                                                        member, 'апелляция', reason_txt, link=proof_link)
            except Exception as _pe:
                log.debug(f"[MOD_TOOLS] демка: {_pe}")

            e = discord.Embed(color=0xE74C3C, timestamp=datetime.now(timezone.utc))
            e.description = (
                "## Изоляция (ПКМ)\n"
                f"**{member.display_name}** · `{member.id}`\n\n"
                f"Закрыто каналов: **{_closed}**\n"
                f"Открыт канал апелляции: {_iso.mention if _iso else '—'}\n"
                f"Причина: {reason_txt}\n"
                f"Модератор: {inter.user.mention}\n"
                f"Дело: **#{case_id}**\n\n{DIVIDER}"
            )
            if proof_note:
                e.description += f"\n{proof_note}"
            e.set_footer(text=inter.guild.name)
            await _respond(inter, embed=e, ephemeral=True)
            if mcog:
                try:
                    await mcog.send_log(inter.guild, e)
                except Exception as _ex:
                    _log.debug("_do(): подавлено: %s", _ex)

        await interaction.response.send_modal(
            ReasonModal(f"Изоляция: {member.display_name}", _do, require_proof=True))

    # ────────────────────────────────────────────────────────────
    # ПКМ → Войс-мут / Войс-размут / Кик из войса (user)
    # ────────────────────────────────────────────────────────────
    async def _vmute_user_ctx(self, interaction: discord.Interaction, member: discord.Member):
        if interaction.guild is None:
            return await _respond(interaction, content="Работает только на сервере.", ephemeral=True)
        if member.bot:
            return await _respond(interaction, content="Ботов мутить нельзя.", ephemeral=True)
        if member.voice is None or member.voice.channel is None:
            return await _respond(interaction, content="Участник не в голосовом канале.", ephemeral=True)

        async def _do(inter, reason, proof):
            await self._voice_action(inter, member, 'vmute', reason, proof)

        await interaction.response.send_modal(
            ReasonModal(f"Войс-мут: {member.display_name}", _do, require_proof=True))

    async def _vunmute_user_ctx(self, interaction: discord.Interaction, member: discord.Member):
        if interaction.guild is None:
            return await _respond(interaction, content="Работает только на сервере.", ephemeral=True)
        if member.bot:
            return await _respond(interaction, content="Ботов размучивать нельзя.", ephemeral=True)

        async def _do(inter, reason, _proof):
            await self._voice_action(inter, member, 'vunmute', reason, None)

        await interaction.response.send_modal(
            ReasonModal(f"Войс-размут: {member.display_name}", _do, require_proof=False))

    async def _vkick_user_ctx(self, interaction: discord.Interaction, member: discord.Member):
        if interaction.guild is None:
            return await _respond(interaction, content="Работает только на сервере.", ephemeral=True)
        if member.bot:
            return await _respond(interaction, content="Ботов выгонять из войса нельзя.", ephemeral=True)
        if member.voice is None or member.voice.channel is None:
            return await _respond(interaction, content="Участник не в голосовом канале.", ephemeral=True)

        async def _do(inter, reason, proof):
            await self._voice_action(inter, member, 'vkick', reason, proof)

        await interaction.response.send_modal(
            ReasonModal(f"Кик из войса: {member.display_name}", _do, require_proof=True))

    async def _voice_action(self, interaction, member, action, reason, proof):
        """Общий путь голосовых действий: мут / размут / кик из войса."""
        guild = interaction.guild
        try:
            if action == 'vmute':
                await member.edit(mute=True, reason=reason or "Войс-мут")
                title, color = "Войс-мут выдан", 0x9B59B6
                detail = f"**{member.display_name}** · `{member.id}`\nМикрофон заглушён."
            elif action == 'vunmute':
                await member.edit(mute=False, reason=reason or "Войс-размут")
                title, color = "Войс-мут снят", 0x2ECC71
                detail = f"**{member.display_name}** · `{member.id}`\nМикрофон включён."
            else:  # vkick
                await member.move_to(None, reason=reason or "Кик из войса")
                title, color = "Кик из войса", 0xE74C3C
                detail = f"**{member.display_name}** · `{member.id}`\nОтключён от голосового канала."
        except discord.Forbidden:
            return await _respond(interaction,
                content="🚫 Нет прав: роль бота ниже роли участника.", ephemeral=True)
        except Exception as e:
            return await _respond(interaction, content=f"🚫 Ошибка: {e}", ephemeral=True)

        mcog = self.bot.get_cog("Moderation")
        case_id = 0
        if mcog:
            try:
                case_id = mcog.save_case(guild.id, action, member.id, interaction.user.id, reason)
            except Exception as _ex:
                _log.debug("_voice_action(): save_case: %s", _ex)

        proof_note = None
        try:
            if proof:
                from cogs.proof_cog import try_deliver_proof
                _p_ru = {'vmute': 'войс-мут', 'vkick': 'кик из войса'}.get(action, action)
                proof_note = await try_deliver_proof(self.bot, guild, interaction.user,
                                                     member, _p_ru, reason, link=proof)
        except Exception as _pe:
            log.debug(f"[MOD_TOOLS] демка: {_pe}")

        e = discord.Embed(color=color, timestamp=datetime.now(timezone.utc))
        e.description = (
            f"## {title}\n{detail}\n"
            f"Причина: {reason or 'Не указана'}\n"
            f"Модератор: {interaction.user.mention}\n"
            f"Дело: **#{case_id}**"
        )
        if proof_note:
            e.description += f"\n{proof_note}"
        e.description += f"\n\n{DIVIDER}"
        e.set_footer(text=guild.name)
        await _respond(interaction, embed=e, ephemeral=True)
        if mcog:
            try:
                await mcog.send_log(guild, e)
            except Exception as _ex:
                _log.debug("_voice_action(): send_log: %s", _ex)

    # ────────────────────────────────────────────────────────────
    # /войс — голосовой контроль (select-меню)
    # ────────────────────────────────────────────────────────────
    @app_commands.command(name="войс", description="Голосовой контроль: войс-мут, кик из войса")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def voice_panel(self, interaction: discord.Interaction):
        chans = [c for c in interaction.guild.voice_channels]
        if not chans:
            return await interaction.response.send_message(
                "На сервере нет голосовых каналов.", ephemeral=True)
        await interaction.response.send_message(
            "Выберите голосовой канал:", view=VoiceChannelView(self, interaction.guild, chans),
            ephemeral=True)

    @voice_panel.error
    async def voice_panel_error(self, interaction, error):
        await _respond(interaction, content="🚫 Нужны права модератора.", ephemeral=True)

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
        except Exception as _ex:
            _log.debug("_load_temp_history(): подавлено: %s", _ex)
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
            except Exception as _ex:
                _log.debug("cases(): подавлено: %s", _ex)
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
        await _respond(interaction, embed=e, ephemeral=True)

    # ────────────────────────────────────────────────────────────
    # /userinfo — карточка участника
    # ────────────────────────────────────────────────────────────
    @app_commands.command(name="userinfo", description="Информация об участнике (модераторы видят досье)")
    @app_commands.describe(user="Участник (по умолчанию — вы)")
    async def userinfo(self, interaction: discord.Interaction, user: discord.Member = None):
        if interaction.guild is None:
            return await _respond(interaction, content="Работает только на сервере.", ephemeral=True)
        user = user or interaction.user
        if not isinstance(user, discord.Member):
            return await _respond(interaction, content="Этот пользователь не на сервере.", ephemeral=True)

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
                except Exception as _ex:
                    _log.debug("userinfo(): подавлено: %s", _ex)
            e.add_field(
                name="🛡 Досье (только модераторам)",
                value=(f"Дел: **{len(cases)}** · Предупреждений: **{len(warns)}**\n"
                       f"Подробная история: `/cases @{user.name}`"),
                inline=False)
            ephemeral = True

        e.set_footer(text=f"{interaction.guild.name}")
        await _respond(interaction, embed=e, ephemeral=ephemeral)

    @cases.error
    async def cases_error(self, interaction, error):
        await _respond(interaction, content="🚫 Нужны права модератора.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(ModTools(bot))
