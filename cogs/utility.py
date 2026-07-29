import discord
from discord.ext import commands
from discord import app_commands

class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="avatar", description="Пользователя avatarını gösterir")
    async def avatar(self, interaction: discord.Interaction, user: discord.Member = None):
        user = user or interaction.user
        e = discord.Embed(title=f"🖼️ {user.display_name} — Avatar", color=0xdc143c, timestamp=discord.utils.utcnow())
        e.set_image(url=user.display_avatar.url)
        e.set_footer(text=f"İsteyen: {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
        await interaction.response.send_message(embed=e)

    @app_commands.command(name="join", description="Ботu голос channelına çağırır")
    async def join(self, interaction: discord.Interaction, channel: discord.VoiceChannel = None):
        if channel is None:
            if interaction.user.voice:
                channel = interaction.user.voice.channel
            else:
                await interaction.response.send_message("❌ Bir голос channelında değilsin!", ephemeral=True)
                return
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.move_to(channel)
        else:
            await channel.connect()
        e = discord.Embed(title="🔊 SES KANALI", color=0x2ecc71, timestamp=discord.utils.utcnow())
        e.add_field(name="📢 Канал", value=f"**{channel.name}**", inline=True)
        e.set_footer(text=f"İsteyen: {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name="leave", description="Ботu голос channelından çıkarır")
    async def leave(self, interaction: discord.Interaction):
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.disconnect()
            e = discord.Embed(title="🔇 SES KANALINDEN AYRILDI", color=0xe74c3c, timestamp=discord.utils.utcnow())
            e.set_footer(text=f"İsteyen: {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
            await interaction.response.send_message(embed=e, ephemeral=True)
        else:
            await interaction.response.send_message("❌ Бот zaten голос channelında değil!", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Utility(bot), guilds=[discord.Object(id=1421244140359909513), discord.Object(id=1107038411895881788)])
