import discord 
from discord .ext import commands 
from discord import app_commands 
import json 
import os 
from datetime import datetime, timezone
from collections import defaultdict 
from config import Config 

class Stats (commands .Cog ):
    def __init__ (self ,bot ):
        self .bot =bot 

    @app_commands .command (name ="stats",description ="Показать статистику сервера")
    async def server_stats (self ,interaction :discord .Interaction ):
        """Показать статистику сервера — участники, каналы, роли, тикеты"""
        await interaction.response.defer(ephemeral=True)
        g = interaction.guild
        humans = sum(1 for m in g.members if not m.bot)
        bots = g.member_count - humans
        online = sum(1 for m in g.members if m.status == discord.Status.online)
        text_ch = sum(1 for c in g.text_channels)
        voice_ch = sum(1 for c in g.voice_channels)
        categories = len(g.categories)

        # Статистика тикетов
        tickets_file = 'data/customer_tickets.json'
        all_tickets = []
        if os.path.exists(tickets_file):
            try:
                with open(tickets_file, 'r', encoding='utf-8') as f:
                    all_tickets = json.load(f)
            except Exception:
                all_tickets = []
        total_tickets = len(all_tickets)
        open_tickets = sum(1 for t in all_tickets if t.get('status') == 'open')
        closed_tickets = total_tickets - open_tickets
        ratings = [t.get('rating', 0) for t in all_tickets if t.get('rating')]
        avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else 0

        e = discord.Embed(
            title=f"📊 {g.name} — Статистика сервера",
            color=0x5865F2,
            timestamp=datetime.now(timezone.utc).replace(tzinfo=None)
        )
        if g.icon:
            e.set_thumbnail(url=g.icon.url)
        e.add_field(name="👤 Участников", value=f"```{g.member_count}```", inline=True)
        e.add_field(name="🧑 Людей", value=f"```{humans}```", inline=True)
        e.add_field(name="🤖 Ботов", value=f"```{bots}```", inline=True)
        e.add_field(name="🟢 Онлайн", value=f"```{online}```", inline=True)
        e.add_field(name="💬 Текст. каналы", value=f"```{text_ch}```", inline=True)
        e.add_field(name="🔊 Голос. каналы", value=f"```{voice_ch}```", inline=True)
        e.add_field(name="🗂 Категории", value=f"```{categories}```", inline=True)
        e.add_field(name="🎭 Ролей", value=f"```{len(g.roles)}```", inline=True)
        e.add_field(name="🎫 Всего тикетов", value=f"```{total_tickets}```", inline=True)
        e.add_field(name="🟢 Открытых", value=f"```{open_tickets}```", inline=True)
        e.add_field(name="🔒 Закрытых", value=f"```{closed_tickets}```", inline=True)
        e.add_field(name="⭐ Средняя оценка", value=f"```{avg_rating}/5```", inline=True)
        e.set_footer(text=f"ID сервера: {g.id}", icon_url=interaction.user.display_avatar.url)

        await interaction.followup.send(embed=e, ephemeral=True)


async def setup (bot ):
    await bot .add_cog (Stats (bot ),guilds =Config .guild_objects ())
