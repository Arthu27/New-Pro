"""Custom Embed Builder - Allows сервер admins to create custom embeds"""
import discord
from discord.ext import commands
from discord import app_commands
import json
import os
from datetime import datetime, timezone
from config import Config 
from json_store import load_json as _js_load, save_json as _js_save

class CustomEmbeds(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _file(self, guild_id):
        return f'data/custom_embeds_{guild_id}.json'

    def _load(self, guild_id):
        return _js_load(self._file(guild_id), {})

    def _save(self, guild_id, data):
        _js_save(self._file(guild_id), data)

    @app_commands.command(name="embed_builder", description="Create a custom embed message")
    @app_commands.describe(
        title="Title of the embed",
        description="Description of the embed",
        color="Color of the embed in hex (e.g., #ff0000)",
        channel="Channel to send the embed to (defaults to current channel)",
        footer="Footer text for the embed",
        image_url="Image URL for the embed",
        thumbnail_url="Thumbnail URL for the embed"
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def create_embed(
        self,
        interaction: discord.Interaction,
        title: str = None,
        description: str = None,
        color: str = "#0000ff",
        channel: discord.TextChannel = None,
        footer: str = None,
        image_url: str = None,
        thumbnail_url: str = None
    ):
        """Create a custom embed via slash command"""
        try:
            # Convert hex color to integer
            color_int = int(color.replace("#", ""), 16)
            
            # Create embed
            embed = discord.Embed()
            if title:
                embed.title = title
            if description:
                embed.description = description
            embed.color = discord.Colour(color_int)
            
            if footer:
                embed.set_footer(text=footer)
            if image_url:
                embed.set_image(url=image_url)
            if thumbnail_url:
                embed.set_thumbnail(url=thumbnail_url)
            
            # Determine target channel
            target_channel = channel or interaction.channel
            
            # Try to send the embed
            sent_msg = await target_channel.send(embed=embed)
            
            # Save to history
            embed_data = {
                'id': str(sent_msg.id),
                'title': title or '',
                'description': description or '',
                'color': color,
                'footer': footer or '',
                'image_url': image_url or '',
                'thumbnail_url': thumbnail_url or '',
                'channel_id': str(target_channel.id),
                'author_id': str(interaction.user.id),
                'timestamp': datetime.now().isoformat()
            }
            
            embeds_data = self._load(interaction.guild_id)
            if 'history' not in embeds_data:
                embeds_data['history'] = []
            embeds_data['history'].insert(0, embed_data)
            
            # Keep only last 50 embeds
            embeds_data['history'] = embeds_data['history'][:50]
            self._save(interaction.guild_id, embeds_data)
            
            await interaction.response.send_message(
                f" Embed successfully created and sent to {target_channel.mention}",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f" Error creating embed: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="embed_history", description="View recently created embeds")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def embed_history(self, interaction: discord.Interaction):
        """Show history of recently created embeds"""
        embeds_data = self._load(interaction.guild_id)
        history = embeds_data.get('history', [])
        
        if not history:
            await interaction.response.send_message("No embeds have been created yet.", ephemeral=True)
            return
        
        # Show last 10 embeds
        recent = history[:10]
        embed = discord.Embed(
            title=" Recent Embeds",
            color=0x7289DA,
            timestamp=datetime.now(timezone.utc).replace(tzinfo=None)
        )
        
        for idx, item in enumerate(recent, 1):
            title = item.get('title', 'No Title')
            author_id = item.get('author_id', 'Unknown')
            author = interaction.guild.get_member(int(author_id))
            author_name = author.display_name if author else "Unknown User"
            
            embed.add_field(
                name=f"#{idx}: {title[:50]}...",
                value=f"By: {author_name}\nChannel: <#{item['channel_id']}>",
                inline=False
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(CustomEmbeds(bot), guilds=Config.guild_objects())