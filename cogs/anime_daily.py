"""Günlük Anime Предложениеsi — Jikan API + Türkçe çeviri butonu"""
import discord
from discord.ext import commands, tasks
from discord import app_commands
import random
import datetime
import json
import os
import aiohttp

DATA_FILE = 'data/anime_daily_config.json'

KATEGORILER = {
    "Aksiyon": 1, "Macera": 2, "Komedi": 4, "Dram": 8,
    "Fantastik": 10, "Korku": 14, "Romantizm": 22,
    "Bilim Kurgu": 24, "Gizem": 7, "Назадlim": 41
}


def _load() -> dict:
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {}


def _save(data: dict):
    os.makedirs('data', exist_ok=True)
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class CeviriButonu(discord.ui.View):
    def __init__(self, ozet: str):
        super().__init__(timeout=None)
        self.ozet = ozet

    @discord.ui.button(label='🇹🇷  Türkçeye Çevir', style=discord.ButtonStyle.primary)
    async def cevir(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        try:
            from deep_translator import GoogleTranslator
            if not self.ozet or self.ozet == 'Özet bulunamadı.':
                await interaction.followup.send('❌ Çevrilecek metin yok.', ephemeral=True)
                return
            ceviri = GoogleTranslator(source='en', target='tr').translate(self.ozet)
            if len(ceviri) > 1900:
                ceviri = ceviri[:1900] + '...'
            await interaction.followup.send(f'🎬 **Türkçe Özet:**\n\n{ceviri}', ephemeral=True)
        except Exception as e:
            await interaction.followup.send('❌ Çeviri yapılamadı.', ephemeral=True)


async def _anime_getir(tur_id: int = None) -> dict:
    """Jikan API'den rastgele anime al"""
    sayfa = random.randint(1, 4)
    if tur_id:
        url = f'https://api.jikan.moe/v4/anime?genres={tur_id}&sfw=true&type=tv&min_score=6.5&order_by=popularity&page={sayfa}'
    else:
        url = f'https://api.jikan.moe/v4/anime?sfw=true&type=tv&min_score=7.0&order_by=popularity&page={sayfa}'
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientМут(total=10)) as resp:
                if resp.status == 200:
                    veri = await resp.json()
                    animeler = veri.get('data', [])
                    if animeler:
                        return random.choice(animeler)
    except:
        pass
    return None


def _embed_olustur(guild: discord.Guild, anime: dict, kategori: str = 'Rastgele') -> tuple:
    """Anime embed'i создать, (embed, ozet) döndür"""
    baslik = anime.get('title_english') or anime.get('title', 'Bilinmiyor')
    puan = anime.get('score') or 'Puanlanmamış'
    resim = anime.get('images', {}).get('jpg', {}).get('large_image_url', '')
    link = anime.get('url', '')
    bolum = anime.get('episodes') or 'Bilinmiyor'
    ozet = anime.get('synopsis', 'Özet bulunamadı.')
    kisa_ozet = (ozet[:300] + '...') if len(ozet) > 300 else ozet

    embed = discord.Embed(
        title=f'🎬 Günün Anime Предложениеsi: {baslik}',
        url=link,
        description=kisa_ozet,
        color=0xED4245
    )
    if resim:
        embed.set_image(url=resim)
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.add_field(name='📂 Kategori', value=kategori, inline=True)
    embed.add_field(name='⭐ Puan', value=str(puan), inline=True)
    embed.add_field(name='📺 Bölüm', value=str(bolum), inline=True)
    embed.set_footer(
        text=f'{guild.name}  ·  Günlük Anime',
        icon_url=guild.icon.url if guild.icon else None
    )
    return embed, ozet


class AnimeDaily(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.gunluk_anime.start()

    def cog_unload(self):
        self.gunluk_anime.cancel()

    @tasks.loop(hours=24)
    async def gunluk_anime(self):
        """Her день час 10:00'da anime предложениеsi отправить"""
        cfg = _load()
        for guild in self.bot.guilds:
            gid = str(guild.id)
            gcfg = cfg.get(gid, {})
            if not gcfg.get('enabled') or not gcfg.get('channel_id'):
                continue
            channel = guild.get_channel(gcfg['channel_id'])
            if not channel:
                continue
            try:
                tur_id = gcfg.get('tur_id')
                tur_adi = gcfg.get('tur_adi', 'Rastgele')
                anime = await _anime_getir(tur_id)
                if not anime:
                    continue
                embed, ozet = _embed_olustur(guild, anime, tur_adi)
                role_id = gcfg.get('role_id')
                content = f'<@&{role_id}>' if role_id else None
                await channel.send(content=content, embed=embed, view=CeviriButonu(ozet))
            except Exception as e:
                print(f'[AnimeDaily] {guild.name} Ошибка: {e}')

    @gunluk_anime.before_loop
    async def before_loop(self):
        await self.bot.wait_until_ready()
        # Время 10:00'a kadar badd
        now = datetime.datetime.now()
        target = now.replace(hour=10, minute=0, second=0, microsecond=0)
        if now >= target:
            target += datetime.timedelta(days=1)
        wait = (target - now).total_seconds()
        import asyncio
        await asyncio.sleep(wait)

    # ── Slash командаları ───────────────────────────────────────────────────────

    @app_commands.command(name='anime-настроить', description="Настроить ежедневную рекомендацию аниме")
    @app_commands.describe(
        channel='Anime предложениеlerinin отправитьileceği channel',
        kategori='Anime kategorisi (boş = rastgele)',
        role='Etiketlenecek role (opsiyonel)',
    )
    @app_commands.choices(kategori=[
        app_commands.Choice(name=k, value=str(v)) for k, v in KATEGORILER.items()
    ] + [app_commands.Choice(name='Rastgele', value='0')])
    @app_commands.checks.has_permissions(manage_channels=True)
    async def anime_настроить(self, interaction: discord.Interaction,
                           channel: discord.TextChannel,
                           kategori: str = '0',
                           role: discord.Role = None):
        cfg = _load()
        gid = str(interaction.guild.id)
        tur_id = int(kategori) if kategori != '0' else None
        tur_adi = next((k for k, v in KATEGORILER.items() if v == tur_id), 'Rastgele')

        cfg[gid] = {
            'enabled': True,
            'channel_id': channel.id,
            'tur_id': tur_id,
            'tur_adi': tur_adi,
            'role_id': role.id if role else None,
        }
        _save(cfg)

        embed = discord.Embed(title='✅ Günlük Anime Настроитьndı', color=0x57F287)
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
        embed.add_field(name='📺 Канал', value=channel.mention, inline=True)
        embed.add_field(name='📂 Kategori', value=tur_adi, inline=True)
        embed.add_field(name='🔔 Роль', value=role.mention if role else 'Нет', inline=True)
        embed.set_footer(text='Her день час 10:00\'da отправитьilecek.')
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='anime-закрыть', description="Отключить ежедневную рекомендацию аниме")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def anime_закрыть(self, interaction: discord.Interaction):
        cfg = _load()
        gid = str(interaction.guild.id)
        if gid in cfg:
            cfg[gid]['enabled'] = False
            _save(cfg)
        await interaction.response.send_message('✅ Günlük anime предложениеsi закрытьıldı.', ephemeral=True)

    @app_commands.command(name='anime', description='Получить случайную рекомендацию аниме')
    @app_commands.describe(kategori='Anime kategorisi')
    @app_commands.choices(kategori=[
        app_commands.Choice(name=k, value=str(v)) for k, v in KATEGORILER.items()
    ] + [app_commands.Choice(name='Rastgele', value='0')])
    async def anime_oner(self, interaction: discord.Interaction, kategori: str = '0'):
        await interaction.response.defer()
        tur_id = int(kategori) if kategori != '0' else None
        tur_adi = next((k for k, v in KATEGORILER.items() if v == tur_id), 'Rastgele')
        anime = await _anime_getir(tur_id)
        if not anime:
            await interaction.followup.send('❌ Anime bulunamadı, tekrar dene.')
            return
        embed, ozet = _embed_olustur(interaction.guild, anime, tur_adi)
        await interaction.followup.send(embed=embed, view=CeviriButonu(ozet))

    @app_commands.command(name='anime-oner', description="Получить случайную или категорийную рекомендацию аниме")
    @app_commands.describe(kategori='Anime kategorisi (boş = rastgele)')
    @app_commands.choices(kategori=[
        app_commands.Choice(name=k, value=str(v)) for k, v in KATEGORILER.items()
    ] + [app_commands.Choice(name='Rastgele', value='0')])
    async def anime_oner2(self, interaction: discord.Interaction, kategori: str = '0'):
        await interaction.response.defer()
        tur_id = int(kategori) if kategori != '0' else None
        tur_adi = next((k for k, v in KATEGORILER.items() if v == tur_id), 'Rastgele')
        anime = await _anime_getir(tur_id)
        if not anime:
            await interaction.followup.send('❌ Anime bulunamadı, tekrar dene.')
            return
        embed, ozet = _embed_olustur(interaction.guild, anime, tur_adi)
        await interaction.followup.send(embed=embed, view=CeviriButonu(ozet))


async def setup(bot):
    await bot.add_cog(AnimeDaily(bot), guilds=[discord.Object(id=1421244140359909513), discord.Object(id=1107038411895881788)])
