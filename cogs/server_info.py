"""Server Информация Система — Bot'a сервер о каждый что-тоi öğret"""
import discord
from discord.ext import commands
from discord import app_commands
import json
import os

DATA_DIR = 'data'


def _info_file(guild_id: int) -> str:
    return f'{DATA_DIR}/sunucu_info_{guild_id}.json'


def _load_info(guild_id: int) -> dict:
    path = _info_file(guild_id)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {}


def _save_info(guild_id: int, data: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(_info_file(guild_id), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_sunucu_context(guild_id: int) -> str:
    """AI для сервер info metnini создать"""
    info = _load_info(guild_id)
    if not info:
        return ''
    
    lines = ['=== СЕРВЕР ИНФОРМАЦИЯ ===']
    
    if info.get('о'):
        lines.append(f'Server О: {info["о"]}')
    if info.get('правила'):
        lines.append(f'Правила: {info["правила"]}')
    if info.get('yetkili_olmak'):
        lines.append(f'Как стать модератором: {info["yetkili_olmak"]}')
    if info.get('ozel_infoler'):
        for k, v in info['ozel_infoler'].items():
            lines.append(f'{k}: {v}')
    
    return '\n'.join(lines)


class ServerModal(discord.ui.Modal):
    def __init__(self, field: str, title: str, guild_id: int):
        super().__init__(title=title)
        self.field = field
        self.guild_id = guild_id
        self.metin = discord.ui.TextInput(
            label='Информация',
            style=discord.TextStyle.paragraph,
            placeholder='Buraya yaz...',
            max_length=1000,
            required=True
        )
        self.add_item(self.metin)

    async def on_submit(self, interaction: discord.Interaction):
        info = _load_info(self.guild_id)
        info[self.field] = self.metin.value.strip()
        _save_info(self.guild_id, info)
        await interaction.response.send_message(
            f'✅ **{self.title}** сохранено!', ephemeral=True
        )


class ServerInfoView(discord.ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    @discord.ui.button(label='📖  Server О', style=discord.ButtonStyle.primary, row=0)
    async def о(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message('❌ Администратор yok.', ephemeral=True)
            return
        await interaction.response.send_modal(
            ServerModal('о', 'Информация о сервере', self.guild_id)
        )

    @discord.ui.button(label='📋  Правила', style=discord.ButtonStyle.primary, row=0)
    async def правила(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message('❌ Администратор yok.', ephemeral=True)
            return
        await interaction.response.send_modal(
            ServerModal('правила', 'Правила сервера', self.guild_id)
        )

    @discord.ui.button(label='👮  Как стать модератором', style=discord.ButtonStyle.primary, row=0)
    async def администратор(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message('❌ Администратор yok.', ephemeral=True)
            return
        await interaction.response.send_modal(
            ServerModal('yetkili_olmak', 'Как стать модератором', self.guild_id)
        )

    @discord.ui.button(label='➕  Добавлено информацию', style=discord.ButtonStyle.secondary, row=1)
    async def ozel_add(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message('❌ Администратор yok.', ephemeral=True)
            return
        await interaction.response.send_modal(OzelBilgiModal(self.guild_id))

    @discord.ui.button(label='👁️  Текущая информация', style=discord.ButtonStyle.secondary, row=1)
    async def goster(self, interaction: discord.Interaction, button: discord.ui.Button):
        info = _load_info(interaction.guild.id)
        if not info:
            await interaction.response.send_message('Информация еще не введена.', ephemeral=True)
            return
        
        embed = discord.Embed(title='📚 Server Информация', color=0x5865F2)
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
        
        if info.get('о'):
            embed.add_field(name='📖 О', value=info['о'][:500], inline=False)
        if info.get('правила'):
            embed.add_field(name='📋 Правила', value=info['правила'][:500], inline=False)
        if info.get('yetkili_olmak'):
            embed.add_field(name='👮 Как стать модератором', value=info['yetkili_olmak'][:500], inline=False)
        if info.get('ozel_infoler'):
            for k, v in list(info['ozel_infoler'].items())[:5]:
                embed.add_field(name=k, value=str(v)[:200], inline=True)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label='🗑️  Temizle', style=discord.ButtonStyle.danger, row=1)
    async def clear(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message('❌ Администратор yok.', ephemeral=True)
            return
        _save_info(interaction.guild.id, {})
        await interaction.response.send_message('✅ Все сервер информация clearndi.', ephemeral=True)


class OzelBilgiModal(discord.ui.Modal, title='Добавлено информацию'):
    def __init__(self, guild_id: int):
        super().__init__()
        self.guild_id = guild_id
        self.baslik = discord.ui.TextInput(
            label='Заголовок',
            placeholder='напр.: Discord Linki, Etkinlik День...',
            max_length=50
        )
        self.icerik = discord.ui.TextInput(
            label='Содержимое',
            style=discord.TextStyle.paragraph,
            placeholder='Информация содержимое...',
            max_length=500
        )
        self.add_item(self.baslik)
        self.add_item(self.icerik)

    async def on_submit(self, interaction: discord.Interaction):
        info = _load_info(self.guild_id)
        if 'ozel_infoler' not in info:
            info['ozel_infoler'] = {}
        info['ozel_infoler'][self.baslik.value.strip()] = self.icerik.value.strip()
        _save_info(self.guild_id, info)
        await interaction.response.send_message(
            f'✅ **{self.baslik.value}** сохранено!', ephemeral=True
        )


class ServerInfo(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='сервер-info')
    @commands.has_permissions(administrator=True)
    async def sunucu_info_panel(self, ctx):
        """Server info control paneli: !сервер-info"""
        embed = discord.Embed(
            title='📚 Server Информация Управление',
            color=0x5865F2,
            description=(
                '> Bot\'a сервер о info öğret.\n'
                '> Bu infoler AI sohbetinde использовать.\n\n'
                '**📖 Server О** — Сервера amacı, teması\n'
                '**📋 Правила** — Правила сервера\n'
                '**👮 Как стать модератором** — Как администратор olunur\n'
                '**➕ Особый Информация** — Başka каждый bir info\n'
                '**👁️ Текущая информация** — Запись информация видеть'
            )
        )
        if ctx.guild.icon:
            embed.set_thumbnail(url=ctx.guild.icon.url)
        if ctx.guild.banner:
            embed.set_image(url=ctx.guild.banner.url)
        embed.set_footer(
            text=f'{ctx.guild.name}  ·  Server Информация Система',
            icon_url=ctx.guild.icon.url if ctx.guild.icon else None
        )
        await ctx.send(embed=embed, view=ServerInfoView(ctx.guild.id))


async def setup(bot):
    await bot.add_cog(ServerInfo(bot))
