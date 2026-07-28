from __future__ import annotations
from typing import Dict, Iterable, Optional
import discord
from server import db

DEFAULT_LOG_CHANNELS = {
    "mod": "mod-logs", "message": "message-logs", "member": "member-logs",
    "voice": "voice-logs", "ticket": "ticket-logs", "security": "security-logs",
    "bot": "bot-logs", "role": "role-logs", "channel": "channel-logs", "invite": "invite-logs",
}


async def create_log_channels(guild: discord.Guild, selected: Dict[str, bool], visible_roles: Iterable[discord.Role], category_name: str = "📁 Logs") -> Dict[str, int]:
    me = guild.me
    if me is None:
        raise RuntimeError("Bot member is not available")
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        me: discord.PermissionOverwrite(view_channel=True, send_messages=True, embed_links=True),
    }
    for role in visible_roles:
        overwrites[role] = discord.PermissionOverwrite(view_channel=True, read_message_history=True)
    category = await guild.create_category(category_name, overwrites=overwrites, reason="ProBotum log setup")
    created: Dict[str, int] = {"category": category.id}
    for key, channel_name in DEFAULT_LOG_CHANNELS.items():
        if not selected.get(key):
            continue
        channel = await guild.create_text_channel(name=channel_name, category=category, overwrites=overwrites, reason="ProBotum log setup")
        created[key] = channel.id
        await channel.send("✅ Log channel connected.")
    db.save_log_channels(str(guild.id), {"categoryId": category.id, "channels": created})
    db.add_audit_log(str(guild.id), "discord_log_channels_created", {"created": created})
    return created


async def send_log(guild: discord.Guild, log_type: str, embed: discord.Embed) -> None:
    config = db.get_log_channels(str(guild.id))
    channel_id = config.get("channels", {}).get(log_type)
    if not channel_id:
        return
    channel = guild.get_channel(int(channel_id))
    if isinstance(channel, discord.TextChannel):
        await channel.send(embed=embed)
