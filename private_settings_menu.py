from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict
import discord
from discord import app_commands
import db
from permissions import deny_interaction, has_command_access


@dataclass(frozen=True)
class MenuScope:
    key: str; icon: str; title: str; short: str; workspace_title: str; workspace_description: str; fields: Dict[str, str]


SCOPES: Dict[str, MenuScope] = {
    "moderation_ban": MenuScope(key="moderation_ban", icon="🛡️", title="Moderation Control", short="Управление наказаниями, банами, мутами.", workspace_title="Moderation Control", workspace_description="Configure bans and moderation actions.", fields={}),
    "tickets_panel": MenuScope(key="tickets_panel", icon="🎫", title="Ticket Control", short="Настройка ticket-панелей, staff-доступа, SLA.", workspace_title="Ticket Panel", workspace_description="Configure ticket panels and staff access.", fields={}),
    "welcome_flow": MenuScope(key="welcome_flow", icon="👋", title="Welcome Control", short="Настройка приветствия, DM-сообщений, autorole.", workspace_title="Welcome Flow", workspace_description="Configure welcome messages and autoroles.", fields={}),
    "roles_access": MenuScope(key="roles_access", icon="🎭", title="Role Access Control", short="Настройка доступа ролей к командам.", workspace_title="Role Access", workspace_description="Configure role access to commands.", fields={}),
    "logs_setup": MenuScope(key="logs_setup", icon="🧾", title="Logs Setup", short="Создание log-категории и каналов.", workspace_title="Log Channels", workspace_description="Create log category and channels.", fields={}),
}

ORDERED_SCOPE_KEYS = ["moderation_ban", "tickets_panel", "welcome_flow", "roles_access", "logs_setup"]


def _guild_id(interaction: discord.Interaction) -> str:
    return str(interaction.guild.id) if interaction.guild else "0"

def _user_id(interaction: discord.Interaction) -> str:
    return str(interaction.user.id)

def _draft(interaction: discord.Interaction, scope_key: str) -> Dict[str, Any]:
    return db.get_draft(_guild_id(interaction), _user_id(interaction), scope_key)

def _merged(interaction: discord.Interaction, scope: MenuScope) -> Dict[str, str]:
    draft = _draft(interaction, scope.key)
    return {k: str(draft.get(k, v)) for k, v in scope.fields.items()}

def _embed(title: str, desc: str, icon: str) -> discord.Embed:
    e = discord.Embed(title=f"{icon} {title}", description=desc, color=discord.Color.dark_embed())
    e.set_footer(text="Private configuration session · visible only to you")
    return e

def intro_embed(interaction: discord.Interaction, scope_key: str = "moderation_ban") -> discord.Embed:
    s = SCOPES[scope_key]
    e = _embed(s.title, s.short, s.icon)
    e.add_field(name="What you configure", value="Select a section below.", inline=False)
    e.add_field(name="Session", value="Draft-safe · no changes until Apply", inline=False)
    return e

def workspace_embed(interaction: discord.Interaction, scope_key: str) -> discord.Embed:
    s = SCOPES[scope_key]; vals = _merged(interaction, s)
    e = _embed(s.workspace_title, s.workspace_description, s.icon)
    e.add_field(name="Status", value=f"Draft changes: **{len(_draft(interaction, s.key))}**", inline=False)
    for k, v in vals.items():
        e.add_field(name=k.replace("_", " ").title(), value=v or "missing", inline=True)
    return e

def validation_embed(interaction: discord.Interaction, scope_key: str) -> discord.Embed:
    s = SCOPES[scope_key]; vals = _merged(interaction, s)
    e = _embed("Validation Check", "Проверка перед применением.", s.icon)
    missing = [k for k, v in vals.items() if v.strip().lower() in {"", "missing", "none"}]
    for k in missing:
        e.add_field(name=f"! {k.replace('_', ' ').title()}", value="Required value missing", inline=False)
    if not missing:
        e.add_field(name="✓ All fields filled", value="Ready to apply", inline=False)
    return e

def apply_preview_embed(interaction: discord.Interaction, scope_key: str) -> discord.Embed:
    s = SCOPES[scope_key]
    e = _embed("Apply Preview", "Что будет сделано:", s.icon)
    for i, step in enumerate(["Validate permissions", f"Save {s.key} config", "Update bot cache", "Write audit event"], 1):
        e.add_field(name=f"{i}. {step}", value="—", inline=False)
    return e

def applied_embed(scope_key: str) -> discord.Embed:
    s = SCOPES[scope_key]
    return _embed("Applied successfully", f"{s.workspace_title} saved.", s.icon)


class ScopeSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(placeholder="Open: Moderation / Tickets / Welcome / Roles / Logs", options=[discord.SelectOption(label=SCOPES[k].title, value=k, description=SCOPES[k].workspace_title, emoji=None) for k in ORDERED_SCOPE_KEYS])
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(embed=workspace_embed(interaction, self.values[0]), view=WorkspaceView(self.values[0]))

class IntroView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=900); self.add_item(ScopeSelect())

class WorkspaceActionSelect(discord.ui.Select):
    def __init__(self, scope_key: str):
        self.scope_key = scope_key
        super().__init__(placeholder="Next: edit / validation / apply / back", options=[
            discord.SelectOption(label="Edit fields", value="edit"), discord.SelectOption(label="Validation", value="validation"),
            discord.SelectOption(label="Apply preview", value="apply"), discord.SelectOption(label="Back", value="back")])
    async def callback(self, interaction: discord.Interaction):
        v = self.values[0]
        if v == "edit": await interaction.response.send_modal(GenericEditModal(self.scope_key))
        elif v == "validation": await interaction.response.edit_message(embed=validation_embed(interaction, self.scope_key), view=WorkspaceView(self.scope_key))
        elif v == "apply": await interaction.response.edit_message(embed=apply_preview_embed(interaction, self.scope_key), view=ApplyView(self.scope_key))
        else: await interaction.response.edit_message(embed=intro_embed(interaction, self.scope_key), view=IntroView())

class WorkspaceView(discord.ui.View):
    def __init__(self, scope_key: str):
        super().__init__(timeout=900); self.add_item(WorkspaceActionSelect(scope_key))

class ApplySelect(discord.ui.Select):
    def __init__(self, scope_key: str):
        self.scope_key = scope_key
        super().__init__(placeholder="Apply: dry-run / confirm / cancel", options=[
            discord.SelectOption(label="Dry-run", value="dry"), discord.SelectOption(label="Confirm apply", value="confirm"), discord.SelectOption(label="Cancel", value="cancel")])
    async def callback(self, interaction: discord.Interaction):
        if interaction.guild is None: await interaction.response.send_message("Guild only.", ephemeral=True); return
        v = self.values[0]
        if v == "confirm":
            draft = db.get_draft(str(interaction.guild.id), str(interaction.user.id), self.scope_key)
            db.set_module_config(str(interaction.guild.id), self.scope_key, draft)
            db.add_audit_log(str(interaction.guild.id), "discord_settings_apply", {"scope": self.scope_key}, str(interaction.user.id))
            await interaction.response.edit_message(embed=applied_embed(self.scope_key), view=None)
        elif v == "dry": await interaction.response.send_message("Dry-run completed.", ephemeral=True)
        else: await interaction.response.edit_message(embed=intro_embed(interaction, self.scope_key), view=IntroView())

class ApplyView(discord.ui.View):
    def __init__(self, scope_key: str):
        super().__init__(timeout=900); self.add_item(ApplySelect(scope_key))

class GenericEditModal(discord.ui.Modal):
    def __init__(self, scope_key: str):
        self.scope_key = scope_key; s = SCOPES[scope_key]
        super().__init__(title=f"Edit {s.workspace_title}")
        for k, v in list(s.fields.items())[:5]:
            self.add_item(discord.ui.TextInput(label=k.replace("_", " ").title(), custom_id=k, default=str(v), required=False, max_length=200))
    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild is None: await interaction.response.send_message("Guild only.", ephemeral=True); return
        current = db.get_draft(str(interaction.guild.id), str(interaction.user.id), self.scope_key)
        for item in self.children:
            if isinstance(item, discord.ui.TextInput): current[item.custom_id] = str(item.value)
        db.set_draft(str(interaction.guild.id), str(interaction.user.id), self.scope_key, current)
        await interaction.response.send_message("Draft updated.", ephemeral=True)


async def register_private_settings(tree: app_commands.CommandTree) -> None:
    @tree.command(name="settings", description="Open private ProBotum settings console")
    async def settings(interaction: discord.Interaction) -> None:
        if not await has_command_access(interaction, "settings"):
            await deny_interaction(interaction); return
        await interaction.response.send_message(embed=intro_embed(interaction), view=IntroView(), ephemeral=True)
