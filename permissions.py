from __future__ import annotations
from typing import Iterable
import discord
import db


def _ids(values: Iterable[discord.abc.Snowflake]) -> set[str]:
    return {str(v.id) for v in values}


async def has_command_access(interaction: discord.Interaction, command_name: str) -> bool:
    if interaction.guild is None or not isinstance(interaction.user, discord.Member):
        return False
    member: discord.Member = interaction.user
    if member.guild_permissions.administrator:
        return True
    rules = db.get_permission_rules(str(interaction.guild.id), command_name)
    if not rules:
        return False
    user_id = str(member.id)
    role_ids = _ids(member.roles)
    denied = False
    allowed = False
    for rule in rules:
        matches_user = rule["target_type"] == "user" and rule["target_id"] == user_id
        matches_role = rule["target_type"] == "role" and rule["target_id"] in role_ids
        if not (matches_user or matches_role):
            continue
        if rule["effect"] == "deny":
            denied = True
        if rule["effect"] == "allow":
            allowed = True
    if denied:
        return False
    return allowed


async def deny_interaction(interaction: discord.Interaction) -> None:
    message = "У вас нет доступа к этой команде. Попросите администратора выдать права в Permissions Center."
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)
