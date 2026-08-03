"""
Reaction / Select Roles Cog

Supports both classic emoji-reaction role panels and modern Discord
select-menu role panels. Panels created from the web panel are persisted
to data/rr_<guild_id>.json and reloaded on startup, so they keep working
across bot restarts.
"""

import os
import json
import glob

import discord
from discord.ext import commands
from discord.ui import View, Select
from datetime import datetime

from logger import get_logger

log = get_logger("reaction_roles_cog")

DATA_DIR = "data"
PREFIX = "rr_"


def _load_panels():
    """Load all rr_*.json panel files -> list of (guild_id, panel_dict)."""
    panels = []
    for path in glob.glob(os.path.join(DATA_DIR, PREFIX + "*.json")):
        try:
            guild_id = os.path.basename(path)[len(PREFIX):-len(".json")]
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                for panel in data.values():
                    if isinstance(panel, dict):
                        panel.setdefault("guild_id", guild_id)
                        panels.append(panel)
        except Exception as e:
            log.warning("rr load error %s: %s", path, e)
    return panels


def _panel_entries(panel):
    """Normalize entries to [{'label','value','emoji','role_id','role_name'}]."""
    out = []
    for e in panel.get("entries", []) or []:
        role_id = str(e.get("role_id", ""))
        out.append({
            "label": e.get("role_name") or role_id or "?",
            "value": role_id,
            "emoji": e.get("emoji") or "",
            "role_id": role_id,
        })
    return out


class RoleSelect(Select):
    """A single select dropdown that toggles one role per selection."""

    def __init__(self, entries, placeholder, row=0):
        options = []
        for e in entries:
            kw = dict(label=e["label"][:80] or "?")
            if e.get("emoji"):
                kw["emoji"] = e["emoji"]
            try:
                options.append(discord.SelectOption(**kw))
            except Exception:
                options.append(discord.SelectOption(label=e["label"][:80] or "?"))
        super().__init__(
            placeholder=placeholder or "Выберите роль",
            min_values=1,
            max_values=1,
            options=options,
            row=row,
        )

    async def callback(self, interaction: discord.Interaction):
        role_id = int(self.values[0])
        role = interaction.guild.get_role(role_id)
        member = interaction.user
        if not role:
            await interaction.response.send_message("Роль не найдена.", ephemeral=True)
            return
        if role in member.roles:
            await member.remove_roles(role, reason="Выбор роли в меню")
            verb = "снята"
        else:
            await member.add_roles(role, reason="Выбор роли в меню")
            verb = "выдана"
        await interaction.response.send_message(
            f"Роль **{role.name}** {verb}.", ephemeral=True
        )


class RoleSelectView(View):
    """View holding one select per row of options (chunked to 25 each)."""

    def __init__(self, entries, title="Роли"):
        super().__init__(timeout=None)
        placeholder = title or "Выберите роль"
        # discord allows max 25 options per select and 5 rows
        for i in range(0, len(entries), 25):
            chunk = entries[i:i + 25]
            row = min(i // 25, 4)
            self.add_item(RoleSelect(chunk, placeholder, row=row))


class ReactionRolesCog(commands.Cog):
    """Reaction roles cog"""

    def __init__(self, bot):
        self.bot = bot
        self.reaction_roles = {}  # message_id -> {emoji -> role_id}
        self.select_panels = {}   # message_id -> panel dict

    # ── classic emoji commands ────────────────────────────────────────────
    @commands.command(name="reactionrole", aliases=["reactionrol"])
    @commands.has_permissions(administrator=True)
    async def reactionrole(self, ctx, message_id: int, emoji: str, role: discord.Role):
        """Привязать выдачу роли к реакции на сообщении"""
        if message_id not in self.reaction_roles:
            self.reaction_roles[message_id] = {}
        self.reaction_roles[message_id][emoji] = role.id

        try:
            message = await ctx.channel.fetch_message(message_id)
            await message.add_reaction(emoji)
            embed = discord.Embed(
                title="✅ Роль-реакция добавлена",
                description=f"**ID сообщения:** {message_id}\n**Эмодзи:** {emoji}\n**Роль:** {role.mention}",
                color=discord.Color.dark_grey(),
                timestamp=datetime.now(),
            )
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(f"Ошибка: {e}")

    @commands.command(name="removereactionrole", aliases=["удалитьреакцию"])
    @commands.has_permissions(administrator=True)
    async def removereactionrole(self, ctx, message_id: int):
        """Удалить привязку ролей-реакций с сообщения"""
        if message_id in self.reaction_roles:
            del self.reaction_roles[message_id]
            embed = discord.Embed(
                title="✅ Привязка ролей-реакций удалена",
                description=f"**ID сообщения:** {message_id}",
                color=discord.Color.dark_grey(),
                timestamp=datetime.now(),
            )
            await ctx.send(embed=embed)
        else:
            await ctx.send("❌ Привязка ролей-реакций не найдена!")

    # ── emoji reaction listeners ──────────────────────────────────────────
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.user_id == self.bot.user.id:
            return
        if payload.message_id not in self.reaction_roles:
            return
        emoji = str(payload.emoji)
        if emoji not in self.reaction_roles[payload.message_id]:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        member = guild.get_member(payload.user_id)
        role = guild.get_role(self.reaction_roles[payload.message_id][emoji])
        if member and role:
            await member.add_roles(role, reason="Роль по реакции")

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        if payload.user_id == self.bot.user.id:
            return
        if payload.message_id not in self.reaction_roles:
            return
        emoji = str(payload.emoji)
        if emoji not in self.reaction_roles[payload.message_id]:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        member = guild.get_member(payload.user_id)
        role = guild.get_role(self.reaction_roles[payload.message_id][emoji])
        if member and role:
            await member.remove_roles(role, reason="Снятие роли по реакции")

    # ── select-menu panels (created from web panel) ───────────────────────
    async def register_select_panel(self, message_id: int, panel: dict):
        """Attach the persisted select view to an existing message id."""
        try:
            guild = self.bot.get_guild(int(panel.get("guild_id", 0)))
            channel = guild.get_channel(int(panel.get("channel_id", 0))) if guild else None
            if not channel:
                return
            msg = await channel.fetch_message(message_id)
            entries = _panel_entries(panel)
            if not entries:
                return
            view = RoleSelectView(entries, panel.get("title", "Роли"))
            await msg.edit(view=view)
            self.select_panels[message_id] = panel
        except Exception as e:
            log.warning("register select panel error: %s", e)

    @commands.Cog.listener()
    async def on_ready(self):
        """Reload persisted panels so select menus work across restarts."""
        self.reaction_roles = {}
        self.select_panels = {}
        for panel in _load_panels():
            ptype = panel.get("type", "emoji")
            msg_id = panel.get("message_id")
            if not msg_id:
                continue
            if ptype == "select":
                await self.register_select_panel(int(msg_id), panel)
            else:
                entries = _panel_entries(panel)
                for e in entries:
                    if e.get("emoji"):
                        self.reaction_roles.setdefault(int(msg_id), {})[e["emoji"]] = int(e["role_id"])
        log.info("ReactionRolesCog loaded (%d select panels)", len(self.select_panels))


async def setup(bot):
    await bot.add_cog(ReactionRolesCog(bot))
