from __future__ import annotations
import discord
import db
from logging_setup import send_log


async def handle_message(message: discord.Message) -> None:
    if message.guild is None or message.author.bot:
        return
    config = db.get_module_config(str(message.guild.id), "automod")
    if not config.get("enabled") in (True, "true", "True", 1):
        return
    content = message.content.lower()
    if config.get("blockInvites", True) and ("discord.gg/" in content or "discord.com/invite/" in content):
        try:
            await message.delete()
        except discord.Forbidden:
            return
        embed = discord.Embed(title="Invite link blocked", color=discord.Color.red())
        embed.add_field(name="User", value=f"{message.author} (`{message.author.id}`)", inline=False)
        embed.add_field(name="Channel", value=message.channel.mention, inline=True)
        embed.add_field(name="Action", value="message deleted", inline=True)
        await send_log(message.guild, "mod", embed)
