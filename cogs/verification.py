import discord
from discord.ext import commands
from discord import app_commands
import random
import string
from cogs.embed_utils import _divider, now_ts

class VerificationView(discord.ui.View):
    def __init__(self, code):
        super().__init__(timeout=300)
        self.code = code
        self.verified = False

    @discord.ui.button(label="✅ Проверка", style=discord.ButtonStyle.green, custom_id="verify_btn")
    async def verify_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = VerificationModal(self.code)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.verified:
            self.verified = True
            self.stop()

class VerificationModal(discord.ui.Modal, title="Проверка"):
    def __init__(self, correct_code):
        super().__init__()
        self.correct_code = correct_code
        self.verified = False

    code_input = discord.ui.TextInput(
        label="Проверка Kodu",
        placeholder="Vverhdaki kodu buraya yaz",
        required=True,
        max_length=6
    )

    async def on_submit(self, interaction: discord.Interaction):
        if self.code_input.value.upper() == self.correct_code:
            verified_role = discord.utils.get(interaction.guild.roles, name="Проверка")
            if verified_role:
                await interaction.user.add_roles(verified_role)
            
            unverified_role = discord.utils.get(interaction.guild.roles, name="Проверка")
            if unverified_role and unverified_role in interaction.user.roles:
                await interaction.user.remove_roles(unverified_role)
            
            await interaction.response.send_message("✅ Успешно проверка!", ephemeral=True)
            self.verified = True
        else:
            await interaction.response.send_message("❌ Неверно kod! Tekrar dene.", ephemeral=True)

class Verification(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member):
        verify_channel = discord.utils.get(member.guild.text_channels, name="проверка")
        if not verify_channel:
            return

        unverified_role = discord.utils.get(member.guild.roles, name="Проверка")
        if unverified_role:
            await member.add_roles(unverified_role)

        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

        e = discord.Embed(
            title="🔐  КТО ПРОВЕРКА",
            color=0x5865F2,
            timestamp=discord.utils.utcnow()
        )
        e.description = (
            f"```ansi\n\u001b[1;34m🔐 ПРОВЕРКА GEREKLİ\u001b[0m\n```\n"
            f"{_divider()}\n\n"
            f"Добро пожаловать geldin {member.mention}! 👋\n\n"
            f"**{member.guild.name}** сервер erişmek для кто проверка gerekiyor.\n\n"
            "aşağıdaki kodu kopyalayıp **✅ Проверка** butonuna bas:\n\n"
            f"```fix\n{code}\n```\n\n"
            f"{_divider()}"
        )
        e.set_thumbnail(url=member.display_avatar.url)
        e.set_image(url="https://media.tenor.com/3Ky6UNqMFpkAAAAC/talking-speak.gif")
        e.add_field(name="⏱️ Длительность", value="```5 minutes```", inline=True)
        e.add_field(name="⚠️ Предупреждение", value="```Длительность dolarsa atılırsın```", inline=True)
        e.add_field(name="💡 Подсказка", value="*Kodu kopyalayıp butona клик, после yapıştır.*", inline=False)
        e.set_footer(
            text=f"{member.guild.name} • Проверка Система",
            icon_url=member.guild.icon.url if member.guild.icon else None
        )

        view = VerificationView(code)
        msg = await verify_channel.send(f"{member.mention}", embed=e, view=view)
        
        await view.wait()
        if not view.verified:
            try:
                await member.kick(reason="Проверка длительность doldu")
                await msg.edit(content=f"~~{member.mention}~~ проверка ve atıldı.", embed=None, view=None)
            except:
                pass
        else:
            await msg.delete()

    @app_commands.command(name="verify-setup", description="Установить систему верификации")
    @app_commands.checks.has_permissions(administrator=True)
    async def verify_setup(self, interaction: discord.Interaction):
        guild = interaction.guild
        
        # Роли создать
        verified_role = discord.utils.get(guild.roles, name="Проверка")
        if not verified_role:
            verified_role = await guild.create_role(name="Проверка", color=discord.Color.green())
        
        unverified_role = discord.utils.get(guild.roles, name="Проверка")
        if not unverified_role:
            unverified_role = await guild.create_role(name="Проверка", color=discord.Color.red())
        
        # Проверка канал
        verify_channel = discord.utils.get(guild.text_channels, name="проверка")
        if not verify_channel:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                unverified_role: discord.PermissionOverwrite(read_messages=True, send_messages=False),
                verified_role: discord.PermissionOverwrite(read_messages=False)
            }
            verify_channel = await guild.create_text_channel("проверка", overwrites=overwrites)
        
        await interaction.response.send_message(
            f"✅ Проверка система kuruldu!\n"
            f"Роли: {verified_role.mention}, {unverified_role.mention}\n"
            f"Канал: {verify_channel.mention}",
            ephemeral=True
        )

async def setup(bot):
    await bot.add_cog(Verification(bot), guilds=[discord.Object(id=1421244140359909513), discord.Object(id=1107038411895881788)])
