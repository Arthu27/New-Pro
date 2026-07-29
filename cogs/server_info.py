"""Сервер Информация Sistemi — Бот'a server hakkında her şeyi öğret"""
import discord
from discord.ext import commands
from discord import app_commands
import json
import os

DATA_DIR = 'data'


def _info_file(guild_id: int) -> str:
    return f'{DATA_DIR}/server_info_{guild_id}.json'


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


def get_server_context(guild_id: int) -> str:
    """AI için server info metnini создать"""
    info = _load_info(guild_id)
    if not info:
        return ''
    
    lines = ['=== SUNUCU BİLGİLERİ ===']
    
    if info.get('hakkinda'):
        lines.append(f'Сервер Hakkında: {info["hakkinda"]}')
    if info.get('kurallar'):
        lines.append(f'Kurallar: {info["kurallar"]}')
    if info.get('right_btn_olmak'):
        lines.append(f'Правоli Nasıl Olunur: {info["right_btn_olmak"]}')
    if info.get('ozel_infoler'):
        for k, v in info['ozel_infoler'].items():
            lines.append(f'{k}: {v}')
    
    return '\n'.join(lines)


class ServerInfoModal(discord.ui.Modal):
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

    @discord.ui.button(label='📖  Сервер Hakkında', style=discord.ButtonStyle.primary, row=0)
    async def hakkinda(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message('❌ Правоn yok.', ephemeral=True)
            return
        await interaction.response.send_modal(
            ServerInfoModal('hakkinda', 'Сервер Hakkında', self.guild_id)
        )

    @discord.ui.button(label='📋  Kurallar', style=discord.ButtonStyle.primary, row=0)
    async def kurallar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message('❌ Правоn yok.', ephemeral=True)
            return
        await interaction.response.send_modal(
            ServerInfoModal('kurallar', 'Сервер Kuralları', self.guild_id)
        )

    @discord.ui.button(label='👮  Правоli Olmak', style=discord.ButtonStyle.primary, row=0)
    async def right_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message('❌ Правоn yok.', ephemeral=True)
            return
        await interaction.response.send_modal(
            ServerInfoModal('right_btn_olmak', 'Правоli Nasıl Olunur', self.guild_id)
        )

    @discord.ui.button(label='➕  Özel Информация Добавить', style=discord.ButtonStyle.secondary, row=1)
    async def ozel_add(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message('❌ Правоn yok.', ephemeral=True)
            return
        await interaction.response.send_modal(OzelИнформацияModal(self.guild_id))

    @discord.ui.button(label='👁️  Mevcut Информацияler', style=discord.ButtonStyle.secondary, row=1)
    async def goster(self, interaction: discord.Interaction, button: discord.ui.Button):
        info = _load_info(interaction.guild.id)
        if not info:
            await interaction.response.send_message('Henüz info girilmemiş.', ephemeral=True)
            return
        
        embed = discord.Embed(title='📚 Сервер Информацияleri', color=0x5865F2)
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
        
        if info.get('hakkinda'):
            embed.add_field(name='📖 Hakkında', value=info['hakkinda'][:500], inline=False)
        if info.get('kurallar'):
            embed.add_field(name='📋 Kurallar', value=info['kurallar'][:500], inline=False)
        if info.get('right_btn_olmak'):
            embed.add_field(name='👮 Правоli Olmak', value=info['right_btn_olmak'][:500], inline=False)
        if info.get('ozel_infoler'):
            for k, v in list(info['ozel_infoler'].items())[:5]:
                embed.add_field(name=k, value=str(v)[:200], inline=True)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label='🗑️  Очистить', style=discord.ButtonStyle.danger, row=1)
    async def clear(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message('❌ Правоn yok.', ephemeral=True)
            return
        _save_info(interaction.guild.id, {})
        await interaction.response.send_message('✅ Tüm server bilgileri clearndi.', ephemeral=True)


class OzelИнформацияModal(discord.ui.Modal, title='Özel Информация Добавить'):
    def __init__(self, guild_id: int):
        super().__init__()
        self.guild_id = guild_id
        self.baslik = discord.ui.TextInput(
            label='Заголовок',
            placeholder='örn: Discord Linki, Etkinlik Günü...',
            max_length=50
        )
        self.icerik = discord.ui.TextInput(
            label='İçerik',
            style=discord.TextStyle.paragraph,
            placeholder='Информацияnin içeriği...',
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

    @commands.command(name='server-info')
    @commands.has_permissions(administrator=True)
    async def server_info_panel(self, ctx):
        """Сервер info control paneli: !server-info"""
        embed = discord.Embed(
            title='📚 Сервер Информация Управлениеi',
            color=0x5865F2,
            description=(
                '> Бот\'a server hakkında info öğret.\n'
                '> Bu infoler AI sohbetinde kullanılacak.\n\n'
                '**📖 Сервер Hakkında** — Серверnun amacı, teması\n'
                '**📋 Kurallar** — Сервер kuralları\n'
                '**👮 Правоli Olmak** — Nasıl right_btn olunur\n'
                '**➕ Özel Информация** — Başka herhangi bir info\n'
                '**👁️ Mevcut Информацияler** — Зарегистрированные bilgileri gör'
            )
        )
        if ctx.guild.icon:
            embed.set_thumbnail(url=ctx.guild.icon.url)
        if ctx.guild.banner:
            embed.set_image(url=ctx.guild.banner.url)
        embed.set_footer(
            text=f'{ctx.guild.name}  ·  Сервер Информация Sistemi',
            icon_url=ctx.guild.icon.url if ctx.guild.icon else None
        )
        await ctx.send(embed=embed, view=ServerInfoView(ctx.guild.id))


async def setup(bot):
    await bot.add_cog(ServerInfo(bot))
