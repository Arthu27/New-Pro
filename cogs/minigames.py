"""Mini oyunlar"""
import discord
from discord.ext import commands
from discord import app_commands
import random
from cogs.embed_utils import _divider, now_ts

class MiniGames(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_guesголос = {}

    @app_commands.command(name='coinflip', description='Текст tura at')
    async def coin_flip(self, interaction: discord.Interaction, tahmin: str = None):
        result = random.choice(['Текст', 'Tura'])
        e = discord.Embed(title="🪙  Текст Tura", color=0xF1C40F, timestamp=discord.utils.utcnow())
        e.description = f"```ansi\n\u001b[1;33m🪙 PARA ATILDI\u001b[0m\n```\n{_divider()}"
        e.add_field(name="🎯 sonuç", value=f"```{result}```", inline=True)
        if tahmin:
            tahmin_norm = tahmin.lower().strip()
            correct = (tahmin_norm in ['yazı', 'yazi'] and result == 'Текст') or \
                      (tahmin_norm == 'tura' and result == 'Tura')
            e.add_field(name="💭 Tahminin", value=f"```{tahmin.capitalize()}```", inline=True)
            e.add_field(name="📊 Статус", value=f"```{'✅ Doğru!' if correct else '❌ Yanlış!'}```", inline=True)
            e.color = 0x2ECC71 if correct else 0xE74C3C
        e.set_footer(text=f"İsteyen: {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
        await interaction.response.send_message(embed=e)

    @app_commands.command(name='roll', description='Zar at')
    @app_commands.describe(adet='Kaç zar atılsın (1-5)')
    async def rolel_dice(self, interaction: discord.Interaction, adet: int = 1):
        adet = max(1, min(5, adet))
        results = [random.randint(1, 6) for _ in range(adet)]
        dice_emojis = {1: '⚀', 2: '⚁', 3: '⚂', 4: '⚃', 5: '⚄', 6: '⚅'}
        e = discord.Embed(title="🎲  Zar Atıldı!", color=0x9B59B6, timestamp=discord.utils.utcnow())
        e.description = (
            f"```ansi\n\u001b[1;35m🎲 ZAR SONUCU\u001b[0m\n```\n{_divider()}\n\n"
            f"# {' '.join(dice_emojis[r] for r in results)}\n\n{_divider()}"
        )
        e.add_field(name="🎯 sonuçlar", value=f"```{' | '.join(str(r) for r in results)}```", inline=True)
        if adet > 1:
            e.add_field(name="➕ Всего", value=f"```{sum(results)}```", inline=True)
        e.set_footer(text=f"İsteyen: {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
        await interaction.response.send_message(embed=e)

    @app_commands.command(name='rps', description='Taş kağıt makas oyna')
    @app_commands.choices(secim=[
        app_commands.Choice(name='Taş', value='taş'),
        app_commands.Choice(name='Kağıt', value='kağıt'),
        app_commands.Choice(name='Makas', value='makas'),
    ])
    async def rps(self, interaction: discord.Interaction, secim: str):
        choices = ['taş', 'kağıt', 'makas']
        emojis = {'taş': '🪨', 'kağıt': '📄', 'makas': '✂️'}
        бот_choice = random.choice(choices)
        wins = {'taş': 'makas', 'kağıt': 'taş', 'makas': 'kağıt'}
        if secim == bot_choice:
            result, color, badge = '🤝 Berabere!', 0xF39C12, "🤝 BERABERE"
        elif wins[secim] == bot_choice:
            result, color, badge = '✅ Kazandın!', 0x2ECC71, "✅ KAZANDIN"
        else:
            result, color, badge = '❌ Kaybettin!', 0xE74C3C, "❌ KAYBETTİN"
        e = discord.Embed(title="🎮  Taş Kağıt Makas", color=color, timestamp=discord.utils.utcnow())
        e.description = (
            f"```ansi\n\u001b[1;{'32' if '✅' in badge else '31' if '❌' in badge else '33'}m{badge}\u001b[0m\n```\n{_divider()}"
        )
        e.add_field(name="👤 Senin Выбратьimin", value=f"# {emojis[secim]} {secim.capitalize()}", inline=True)
        e.add_field(name="🤖 Ботun Выбратьimi", value=f"# {emojis[бот_choice]} {бот_choice.capitalize()}", inline=True)
        e.add_field(name="🏆 sonuç", value=f"```{result}```", inline=False)
        e.set_footer(text=f"İsteyen: {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
        await interaction.response.send_message(embed=e)

    @app_commands.command(name='guess-start', description='Sayı tahmin oyunu запустить (1-100)')
    async def start_guess(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        if gid in self.active_guesголос:
            await interaction.response.send_message('❌ Zaten активна bir oyun var! `/oyun-tahmin` ile devam et.', ephemeral=True)
            return
        number = random.randint(1, 100)
        self.active_guesголос[gid] = {'number': number, 'attempts': 0, 'started_by': interaction.user.id}
        e = discord.Embed(title="🎯  Sayı Tahmin Oyunu Başladı!", color=0x3498DB, timestamp=discord.utils.utcnow())
        e.description = (
            f"```ansi\n\u001b[1;34m🎮 OYUN BAŞLADI\u001b[0m\n```\n{_divider()}\n\n"
            f"1 ile 100 arasında bir sayı tuttum!\n"
            f"`/oyun-tahmin [sayı]` командаuyla tahmin et.\n\n{_divider()}"
        )
        e.set_thumbnail(url=interaction.user.display_avatar.url)
        e.add_field(name="🎯 Поискlık", value="```1 — 100```", inline=True)
        e.add_field(name="👤 Запуститьan", value=interaction.user.mention, inline=True)
        e.add_field(name="💡 İpucu", value="*Daha büyük / daha küçük ipuçlarını takip et!*", inline=False)
        e.set_footer(text=f"Aether • {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
        await interaction.response.send_message(embed=e)

    @app_commands.command(name='guess', description='Sayı tahmin et')
    @app_commands.describe(sayi='Tahminin (1-100)')
    async def guess(self, interaction: discord.Interaction, sayi: int):
        gid = interaction.guild_id
        if gid not in self.active_guesголос:
            await interaction.response.send_message('❌ Активен oyun yok! `/oyun-baslat` ile запустить.', ephemeral=True)
            return
        game = self.active_guesголос[gid]
        game['attempts'] += 1
        number = game['number']
        if sayi == number:
            del self.active_guesголос[gid]
            e = discord.Embed(title="🎉  DOĞRU TAHMİN!", color=0x2ECC71, timestamp=discord.utils.utcnow())
            e.description = (
                f"```ansi\n\u001b[1;32m🏆 KAZANDIN!\u001b[0m\n```\n{_divider()}\n\n"
                f"{interaction.user.mention} sayıyı buldu! 🎊\n\n{_divider()}"
            )
            e.add_field(name="🎯 Sayı", value=f"```{number}```", inline=True)
            e.add_field(name="🔢 Deneme", value=f"```{game['attempts']} deneme```", inline=True)
        elif sayi < number:
            e = discord.Embed(title="📈  Daha Büyük!", color=0xF39C12, timestamp=discord.utils.utcnow())
            e.description = f"```ansi\n\u001b[1;33m📈 DAHA BÜYÜK\u001b[0m\n```\n{_divider()}"
            e.add_field(name="💭 Tahminin", value=f"```{sayi}```", inline=True)
            e.add_field(name="🔢 Deneme", value=f"```{game['attempts']}. deneme```", inline=True)
            e.add_field(name="💡 İpucu", value="*Sayı daha büyük, yukarı çık!*", inline=False)
        else:
            e = discord.Embed(title="📉  Daha Küçük!", color=0xF39C12, timestamp=discord.utils.utcnow())
            e.description = f"```ansi\n\u001b[1;33m📉 DAHA KÜÇÜK\u001b[0m\n```\n{_divider()}"
            e.add_field(name="💭 Tahminin", value=f"```{sayi}```", inline=True)
            e.add_field(name="🔢 Deneme", value=f"```{game['attempts']}. deneme```", inline=True)
            e.add_field(name="💡 İpucu", value="*Sayı daha küçük, aşağı in!*", inline=False)
        e.set_footer(text=f"Aether • {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
        await interaction.response.send_message(embed=e)

    @app_commands.command(name='8ball', description='Sihirli 8 top - soruyu sor!')
    @app_commands.describe(soru='Sorunuz')
    async def magic_8ball(self, interaction: discord.Interaction, soru: str):
        responголос = [
            ('✅ Kesinlikle evet!', 0x2ECC71), ('✅ Да, öyle görünüyor.', 0x2ECC71),
            ('✅ Büyük ihtimalle evet.', 0x2ECC71), ('✅ Buna güvenebilirsin.', 0x2ECC71),
            ('🤔 Şu an söylemek zor.', 0xF39C12), ('🤔 Tekrar sor.', 0xF39C12),
            ('🤔 Şimdi cevap veremem.', 0xF39C12), ('🤔 Konsantre ol ve tekrar sor.', 0xF39C12),
            ('❌ Sanmıyorum.', 0xE74C3C), ('❌ Нет.', 0xE74C3C),
            ('❌ Kesinlikle hayır.', 0xE74C3C), ('❌ Görünüşe göre hayır.', 0xE74C3C),
        ]
        cevap, color = random.choice(responголос)
        e = discord.Embed(title="🎱  Sihirli 8 Top", color=color, timestamp=discord.utils.utcnow())
        e.description = (
            f"```ansi\n\u001b[1;35m🎱 CEVAP GELİYOR...\u001b[0m\n```\n{_divider()}"
        )
        e.add_field(name="❓ Soru", value=f"*{soru}*", inline=False)
        e.add_field(name="🎱 Cevap", value=f"```{cevap}```", inline=False)
        e.set_footer(text=f"İsteyen: {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
        await interaction.response.send_message(embed=e)

    @app_commands.command(name='oyun-rastgele-uye', description='Серверdan rastgele bir участник выбрать')
    async def random_member(self, interaction: discord.Interaction, role: discord.Role = None):
        members = [m for m in interaction.guild.members if not m.bot]
        if role:
            members = [m for m in members if role in m.roles]
        if not members:
            await interaction.response.send_message('❌ Uygun участник bulunamadı!', ephemeral=True)
            return
        secilen = random.choice(members)
        e = discord.Embed(title="🎰  Rastgele Участник Выбратьildi!", color=0xDC143C, timestamp=discord.utils.utcnow())
        e.description = (
            f"```ansi\n\u001b[1;31m🎲 SEÇIM YAPILDI\u001b[0m\n```\n{_divider()}\n\n"
            f"Kura çekildi ve kazanan belli oldu! 🎊\n\n{_divider()}"
        )
        e.set_thumbnail(url=secilen.display_avatar.url)
        e.add_field(name="🏆 Выбратьilen", value=secilen.mention, inline=True)
        if role:
            e.add_field(name="🎭 Role Filtresi", value=role.mention, inline=True)
        e.add_field(name="👥 Havuz", value=f"```{len(members)} kişi```", inline=True)
        e.set_footer(text=f"Aether • {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
        await interaction.response.send_message(embed=e)


async def setup(bot):
    await bot.add_cog(MiniGames(bot), guilds=[discord.Object(id=1421244140359909513), discord.Object(id=1107038411895881788)])
