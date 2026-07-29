import discord
from discord.ext import commands
from discord import app_commands
import io
from datetime import datetime

class Archive(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="archive", description="Архивировать сообщения канала (HTML)")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def archive(self, interaction: discord.Interaction, limit: int = 100):
        await interaction.response.defer(ephemeral=True)
        
        messages = []
        async for msg in interaction.channel.history(limit=limit, oldest_first=True):
            messages.append(msg)
        
        html = self.generate_html(messages, interaction.channel)
        
        file = discord.File(
            fp=io.BytesIO(html.encode('utf-8')),
            filename=f"archive_{interaction.channel.name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.html"
        )
        
        await interaction.followup.send(f"✅ {len(messages)} сообщений заархивировано.", file=file, ephemeral=True)

    def generate_html(self, messages, channel):
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>#{channel.name} Arşivi</title>
    <style>
        body {{ font-family: Arial; background: #36393f; color: #dcddde; padding: 20px; }}
        .message {{ margin: 10px 0; padding: 10px; background: #40444b; border-radius: 5px; }}
        .author {{ color: #7289da; font-weight: bold; }}
        .timestamp {{ color: #72767d; font-size: 12px; }}
        .content {{ margin-top: 5px; }}
        img {{ max-width: 400px; border-radius: 5px; margin-top: 5px; }}
    </style>
</head>
<body>
    <h1>#{channel.name} Arşivi</h1>
    <p>Всего Сообщение: {len(messages)}</p>
    <hr>
"""
        for msg in messages:
            timestamp = msg.created_at.strftime('%Y-%m-%d %H:%M:%S')
            content = msg.content.replace('<', '&lt;').replace('>', '&gt;')
            
            html += f"""
    <div class="message">
        <div>
            <span class="author">{msg.author.name}</span>
            <span class="timestamp">{timestamp}</span>
        </div>
        <div class="content">{content}</div>
"""
            for attachment in msg.attachments:
                if attachment.content_type and attachment.content_type.startswith('image'):
                    html += f'        <img src="{attachment.url}" alt="image"><br>\n'
                else:
                    html += f'        <a href="{attachment.url}">{attachment.filename}</a><br>\n'
            
            html += "    </div>\n"
        
        html += """
</body>
</html>
"""
        return html

    @app_commands.command(name="backup-channel", description="Резервное копирование сообщений канала (TXT)")
    @app_commands.checks.has_permissions(administrator=True)
    async def backup_channel(self, interaction: discord.Interaction, limit: int = 500):
        await interaction.response.defer(ephemeral=True)
        
        messages = []
        async for msg in interaction.channel.history(limit=limit, oldest_first=True):
            timestamp = msg.created_at.strftime('%Y-%m-%d %H:%M:%S')
            messages.append(f"[{timestamp}] {msg.author}: {msg.content}")
        
        content = "\n".join(messages)
        file = discord.File(
            fp=io.BytesIO(content.encode('utf-8')),
            filename=f"backup_{interaction.channel.name}_{datetime.utcnow().strftime('%Y%m%d')}.txt"
        )
        
        await interaction.followup.send(f"✅ {len(messages)} message yedaddndi.", file=file, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Archive(bot), guilds=[discord.Object(id=1421244140359909513), discord.Object(id=1107038411895881788)])
