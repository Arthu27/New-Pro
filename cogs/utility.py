import discord
from discord.ext import commands
from discord import app_commands

class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="avatar", description="Показать аватар пользователя")
    async def avatar(self, interaction: discord.Interaction, user: discord.Member = None):
        user = user or interaction.user
        e = discord.Embed(title=f"🖼️ {user.display_name} — Avatar", color=0xdc143c, timestamp=discord.utils.utcnow())
        e.set_image(url=user.display_avatar.url)
        e.set_footer(text=f"Желание: {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
        await interaction.response.send_message(embed=e)

    @app_commands.command(name="join", description="Подключить бота к голосовому каналу")
    async def join(self, interaction: discord.Interaction, channel: discord.VoiceChannel = None):
        if channel is None:
            if interaction.user.voice:
                channel = interaction.user.voice.channel
            else:
                await interaction.response.send_message("❌ Вы не находитесь в голосовом канале!", ephemeral=True)
                return
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.move_to(channel)
        else:
            await channel.connect()
        e = discord.Embed(title="🔊 SES КАНАЛ", color=0x2ecc71, timestamp=discord.utils.utcnow())
        e.add_field(name="📢 Канал", value=f"**{channel.name}**", inline=True)
        e.set_footer(text=f"Желание: {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name="vc_leave", description="Отключить бота от голосового канала")
    async def leave(self, interaction: discord.Interaction):
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.disconnect()
            e = discord.Embed(title="🔇 SES КАНАЛ ПОКИНУЛ", color=0xe74c3c, timestamp=discord.utils.utcnow())
            e.set_footer(text=f"Желание: {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
            await interaction.response.send_message(embed=e, ephemeral=True)
        else:
            await interaction.response.send_message("❌ Bot zaten ses в канале не!", ephemeral=True)

    @app_commands.command(name="faq-learn", description="Обучить AI новому вопросу и ответу (FAQ)")
    @app_commands.describe(question="Часто задаваемый вопрос", answer="Правильный ответ от администрации")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def faq_learn(self, interaction: discord.Interaction, question: str, answer: str):
        from web.faq_manager import learn_from_staff
        gid = interaction.guild.id if interaction.guild else 0
        learn_from_staff(question, answer, gid, staff_name=str(interaction.user))
        embed = discord.Embed(
            title="🧠 AI успешно обучен новому FAQ",
            color=0x2ECC71,
            description=f"**Вопрос:** {question}\n**Ответ:** {answer}"
        )
        embed.set_footer(text=f"Обучил: {interaction.user.display_name}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="faq-list", description="Показать список изученных вопросов AI (FAQ)")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def faq_list(self, interaction: discord.Interaction):
        from web.faq_manager import _load, FAQ_FILE
        faqs = _load(FAQ_FILE)
        gid = interaction.guild.id if interaction.guild else 0
        server_faqs = [f for f in faqs if str(f.get('guild_id', '')) == str(gid) or not f.get('guild_id')]
        if not server_faqs:
            await interaction.response.send_message("❌ В базе знаний пока нет изученных FAQ.", ephemeral=True)
            return
        embed = discord.Embed(title=f"📚 База знаний AI ({len(server_faqs)} FAQ)", color=0x2B2D31)
        desc = ""
        for idx, item in enumerate(server_faqs[:10], 1):
            desc += f"**{idx}. {item.get('question')}**\n> {item.get('answer', '')[:100]}\n\n"
        embed.description = desc
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Utility(bot), guilds=[discord.Object(id=1421244140359909513), discord.Object(id=1107038411895881788)])
