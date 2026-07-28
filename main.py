from __future__ import annotations
import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from automod import handle_message
from private_settings_menu import register_private_settings
import db

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
if hasattr(intents, "moderation"):
    intents.moderation = True

bot = commands.Bot(command_prefix="!", intents=intents)
_commands_registered = False


def build_guild_snapshot(guild: discord.Guild) -> dict:
    return {
        "id": str(guild.id), "name": guild.name, "member_count": guild.member_count,
        "channels": [{"id": str(ch.id), "name": ch.name, "type": getattr(ch, "type", None).value if getattr(ch, "type", None) is not None else None} for ch in guild.channels],
        "roles": [{"id": str(r.id), "name": r.name, "position": r.position} for r in guild.roles if r.name != "@everyone"],
    }

async def save_all_snapshots():
    for guild in bot.guilds:
        db.save_guild_snapshot(str(guild.id), build_guild_snapshot(guild))

@bot.event
async def on_ready():
    global _commands_registered
    db.init_db()
    await bot.change_presence(status=discord.Status.online, activity=discord.Activity(type=discord.ActivityType.watching, name="ProBotum Dashboard"))
    await save_all_snapshots()
    if not _commands_registered:
        await register_private_settings(bot.tree)
        _commands_registered = True
    if GUILD_ID:
        guild = discord.Object(id=int(GUILD_ID))
        bot.tree.copy_global_to(guild=guild)
        await bot.tree.sync(guild=guild)
    else:
        await bot.tree.sync()
    print(f"Logged in as {bot.user} ({bot.user.id if bot.user else 'unknown'})")

@bot.event
async def on_guild_join(guild): db.save_guild_snapshot(str(guild.id), build_guild_snapshot(guild))
@bot.event
async def on_guild_channel_create(channel):
    if channel.guild: db.save_guild_snapshot(str(channel.guild.id), build_guild_snapshot(channel.guild))
@bot.event
async def on_guild_channel_delete(channel):
    if channel.guild: db.save_guild_snapshot(str(channel.guild.id), build_guild_snapshot(channel.guild))
@bot.event
async def on_guild_role_create(role): db.save_guild_snapshot(str(role.guild.id), build_guild_snapshot(role.guild))
@bot.event
async def on_guild_role_delete(role): db.save_guild_snapshot(str(role.guild.id), build_guild_snapshot(role.guild))
@bot.event
async def on_member_join(member): db.save_guild_snapshot(str(member.guild.id), build_guild_snapshot(member.guild))
@bot.event
async def on_member_remove(member): db.save_guild_snapshot(str(member.guild.id), build_guild_snapshot(member.guild))
@bot.event
async def on_message(message):
    await handle_message(message)
    await bot.process_commands(message)

if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN is missing. Put it into .env")
    bot.run(TOKEN)
