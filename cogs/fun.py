"""Eğlence командаları"""
import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio
from datetime import datetime
from cogs.embed_utils import _divider, now_ts

class Fun(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.trivia_sessions = {}

    @app_commands.command(name="fun", description="Eğlenceli командаlar: zar, yazı-tura, 8top, выбрать, şans, uyumluluk")
    @app_commands.choices(islem=[
        app_commands.Choice(name="zar", value="zar"),
        app_commands.Choice(name="yazı-tura", value="yazi-tura"),
        app_commands.Choice(name="8top", value="8top"),
        app_commands.Choice(name="выбрать", value="sec"),
        app_commands.Choice(name="şans", value="sans"),
        app_commands.Choice(name="uyumluluk", value="uyumluluk"),
    ])
    async def eglen(self, interaction: discord.Interaction, islem: str,
                   yuz: int = 6, soru: str = None, secenaddr: str = None,
                   kullanici1: discord.Member = None, kullanici2: discord.Member = None):

        if islem == "zar":
            if yuz < 2 or yuz > 1000:
                await interaction.response.send_message("❌ Yüz 2-1000 arasında olmalı!", ephemeral=True)
                return
            sonuc = random.randint(1, yuz)
            pct = int((sonuc / yuz) * 10)
            bar = "█" * pct + "░" * (10 - pct)
            e = discord.Embed(title="🎲  Zar Atıldı!", color=0xDC143C, timestamp=datetime.utcnow())
            e.description = (
                f"```ansi\n\u001b[1;31m🎲 ZAR SONUCU\u001b[0m\n```\n{_divider()}"
            )
            e.add_field(name=f"🎲 d{yuz}", value=f"```fix\n{sonuc}\n```", inline=True)
            e.add_field(name="📊 Oran", value=f"`{bar}` {int(sonuc/yuz*100)}%", inline=True)
            e.set_footer(text=f"İsteyen: {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
            await interaction.response.send_message(embed=e)

        elif islem == "yazi-tura":
            sonuc = random.choice(["🪙 YAZI", "🪙 TURA"])
            e = discord.Embed(title="🪙  Текст Tura", color=0xF1C40F, timestamp=datetime.utcnow())
            e.description = (
                f"```ansi\n\u001b[1;33m🪙 PARA ATILDI\u001b[0m\n```\n{_divider()}\n\n"
                f"# {sonuc}\n\n{_divider()}"
            )
            e.set_footer(text=f"İsteyen: {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
            await interaction.response.send_message(embed=e)

        elif islem == "8top":
            if not soru:
                await interaction.response.send_message("❌ Soru belirtmelisin!", ephemeral=True)
                return
            cevaplar = [
                ("✅ Kesinlikle evet!", 0x2ECC71), ("✅ Да, öyle görünüyor.", 0x2ECC71),
                ("✅ Büyük ihtimalle.", 0x2ECC71), ("✅ Buna güvenebilirsin.", 0x2ECC71),
                ("🤔 Şu an belirsiz, tekrar sor.", 0xF39C12), ("🤔 Daha sonra tekrar sor.", 0xF39C12),
                ("🤔 Şu an tahmin edemiyorum.", 0xF39C12), ("❌ Pek iyi görünmüyor.", 0xE74C3C),
                ("❌ Cevabım hayır.", 0xE74C3C), ("❌ Kesinlikle hayır.", 0xE74C3C),
            ]
            cevap, color = random.choice(cevaplar)
            e = discord.Embed(title="🎱  Sihirli 8 Top", color=color, timestamp=datetime.utcnow())
            e.description = f"```ansi\n\u001b[1;35m🎱 CEVAP GELİYOR...\u001b[0m\n```\n{_divider()}"
            e.add_field(name="❓ Soru", value=f"*{soru}*", inline=False)
            e.add_field(name="🎱 Cevap", value=f"```{cevap}```", inline=False)
            e.set_footer(text=f"İsteyen: {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
            await interaction.response.send_message(embed=e)

        elif islem == "sec":
            if not secenaddr:
                await interaction.response.send_message("❌ Выбратьenek belirtmelisin! (virgülle ayır)", ephemeral=True)
                return
            liste = [s.strip() for s in secenaddr.split(",") if s.strip()]
            if len(liste) < 2:
                await interaction.response.send_message("❌ En az 2 выбратьenek gir!", ephemeral=True)
                return
            secilen = random.choice(liste)
            e = discord.Embed(title="🎯  Karar Verildi!", color=0xDC143C, timestamp=datetime.utcnow())
            e.description = (
                f"```ansi\n\u001b[1;31m🎯 KARAR VERİLDİ\u001b[0m\n```\n{_divider()}"
            )
            e.add_field(
                name=f"📋 Выбратьenaddr ({len(liste)})",
                value="\n".join(f"{'✅' if s == secilen else '▫️'} {s}" for s in liste),
                inline=False
            )
            e.add_field(name="🏆 Выбратьilen", value=f"```{secilen}```", inline=False)
            e.set_footer(text=f"İsteyen: {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
            await interaction.response.send_message(embed=e)

        elif islem == "sans":
            hedef = kullanici1 or interaction.user
            seed = int(str(hedef.id) + datetime.utcnow().strftime("%Y%m%d"))
            random.seed(seed)
            puan = random.randint(1, 100)
            random.seed()
            if puan >= 80:
                color, badge, yorum = 0x2ECC71, "🍀 SÜPER ŞANSLI", "Buдень her şey yolunda gidecek!"
            elif puan >= 60:
                color, badge, yorum = 0xF1C40F, "⭐ İYİ ŞANS", "Güzel bir день seni ожидание."
            elif puan >= 40:
                color, badge, yorum = 0xF39C12, "🌤️ ORTA ŞANS", "Dikkatli ol, ama umudu kesme."
            else:
                color, badge, yorum = 0xE74C3C, "🌧️ DÜŞÜK ŞANS", "Buдень temkinli ol!"
            bar = "█" * (puan // 10) + "░" * (10 - puan // 10)
            e = discord.Embed(title="🍀  Günlük Şans", color=color, timestamp=datetime.utcnow())
            e.description = (
                f"```ansi\n\u001b[1;{'32' if puan >= 60 else '33' if puan >= 40 else '31'}m{badge}\u001b[0m\n```\n{_divider()}"
            )
            e.set_thumbnail(url=hedef.display_avatar.url)
            e.add_field(name="👤 Пользователь", value=hedef.mention, inline=True)
            e.add_field(name="🍀 Şans Puanı", value=f"`{bar}` **{puan}/100**", inline=False)
            e.add_field(name="💬 Yorum", value=f"*{yorum}*", inline=False)
            e.set_footer(text=f"Aether • {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
            await interaction.response.send_message(embed=e)

        elif islem == "uyumluluk":
            if not kullanici1 or not kullanici2:
                await interaction.response.send_message("❌ İki user belirtmelisin!", ephemeral=True)
                return
            seed = min(kullanici1.id, kullanici2.id) * max(kullanici1.id, kullanici2.id)
            random.seed(seed % 999999)
            puan = random.randint(1, 100)
            random.seed()
            kalpler = "❤️" * (puan // 20) + "🖤" * (5 - puan // 20)
            if puan >= 80:
                yorum, color = "Mükemmel bir uyum! Ayrılmayın! 💑", 0xFF69B4
            elif puan >= 60:
                yorum, color = "İyi bir uyum var, devam edin! 💕", 0xE91E8C
            elif puan >= 40:
                yorum, color = "Orta düzey uyum, çaba gösterin! 💛", 0xF39C12
            else:
                yorum, color = "Zor bir ilişki olur... 💔", 0xE74C3C
            e = discord.Embed(title="💕  Uyumluluk Testi", color=color, timestamp=datetime.utcnow())
            e.description = (
                f"```ansi\n\u001b[1;35m💕 UYUMLULUK SONUCU\u001b[0m\n```\n{_divider()}"
            )
            e.add_field(name="👫 Çift", value=f"{kullanici1.mention} & {kullanici2.mention}", inline=False)
            e.add_field(name="💕 Uyumluluk", value=f"{kalpler} **%{puan}**", inline=False)
            e.add_field(name="💬 Yorum", value=f"*{yorum}*", inline=False)
            e.set_footer(text=f"Aether • {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
            await interaction.response.send_message(embed=e)

    @app_commands.command(name="опрос-hızlı", description="Hızlı evet/hayır опросi создатьur")
    async def poll_quick(self, interaction: discord.Interaction, soru: str):
        e = discord.Embed(title="📊  Hızlı Опрос", color=0xDC143C, timestamp=datetime.utcnow())
        e.description = (
            f"```ansi\n\u001b[1;31m📊 ANKET BAŞLADI\u001b[0m\n```\n{_divider()}\n\n"
            f"**{soru}**\n\n{_divider()}"
        )
        e.add_field(name="✅ Да", value="Внизya oy ver!", inline=True)
        e.add_field(name="❌ Нет", value="Внизya oy ver!", inline=True)
        e.set_footer(text=f"Soran: {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
        msg = await interaction.channel.send(embed=e)
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")
        await interaction.response.send_message("✅ Опрос создано!", ephemeral=True)

    @app_commands.command(name="profil-kartı", description="Detaylı profil kartı gösterir")
    async def profil_karti(self, interaction: discord.Interaction, kullanici: discord.Member = None):
        u = kullanici or interaction.user
        rozet = "👑" if u == interaction.guild.owner else "🛡️" if u.guild_permissions.administrator else "⚔️" if u.guild_permissions.moderate_members else "👤"
        e = discord.Embed(
            title=f"{rozet}  {u.display_name} — Profil",
            color=u.color if u.color.value else 0xDC143C,
            timestamp=datetime.utcnow()
        )
        e.description = f"```ansi\n\u001b[1;31m👤 KULLANICI PROFİLİ\u001b[0m\n```\n{_divider()}"
        e.set_thumbnail(url=u.display_avatar.url)
        e.add_field(name="🆔 ID", value=f"```{u.id}```", inline=True)
        e.add_field(name="📅 Katılım", value=f"<t:{int(u.joined_at.timestamp())}:R>", inline=True)
        e.add_field(name="🎂 Hesap", value=f"<t:{int(u.created_at.timestamp())}:R>", inline=True)
        e.add_field(name="🎭 Роли", value=f"```{len(u.roles)-1} role```", inline=True)
        e.add_field(name="📊 Статус", value=f"```{str(u.status).title()}```", inline=True)
        e.add_field(name="🖥️ Platform", value=f"```{'Mobil' if u.is_on_mobile() else 'Masaüstü'}```", inline=True)
        roles = [r.mention for r in u.roles[1:6]]
        if roles:
            e.add_field(name="🎭 Верхние роли", value=" ".join(roles), inline=False)
        e.set_footer(text=f"Aether • {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
        await interaction.response.send_message(embed=e)

    @app_commands.command(name="geri-sayım", description="Назад sayım запуститьır (maks 60 saniye)")
    async def geri_sayim(self, interaction: discord.Interaction, saniye: int, message: str = ""):
        if saniye < 1 or saniye > 60:
            await interaction.response.send_message("❌ 1-60 saniye arası!", ephemeral=True)
            return
        e = discord.Embed(title="⏱️  Назад Sayım", color=0xDC143C, timestamp=datetime.utcnow())
        e.description = (
            f"```ansi\n\u001b[1;31m⏱️ GERİ SAYIM BAŞLADI\u001b[0m\n```\n{_divider()}\n\n"
            f"{message}\n\n**{saniye}** saniye kaldı...\n\n{_divider()}"
        )
        await interaction.response.send_message(embed=e)
        msg = await interaction.original_response()
        for i in range(saniye - 1, 0, -1):
            await asyncio.sleep(1)
            e.description = (
                f"```ansi\n\u001b[1;31m⏱️ GERİ SAYIM\u001b[0m\n```\n{_divider()}\n\n"
                f"{message}\n\n**{i}** saniye kaldı...\n\n{_divider()}"
            )
            await msg.edit(embed=e)
        await asyncio.sleep(1)
        e.title = "🔔  Süre Doldu!"
        e.description = (
            f"```ansi\n\u001b[1;32m🔔 SÜRE DOLDU!\u001b[0m\n```\n{_divider()}\n\n"
            f"{message}\n\n**⏰ ZAMAN!**\n\n{_divider()}"
        )
        e.color = 0x2ECC71
        await msg.edit(embed=e)

    @app_commands.command(name="rastgele-участник", description="Серверdan rastgele участник выбратьer")
    async def rastgele_uye(self, interaction: discord.Interaction, role: discord.Role = None):
        havuz = [m for m in interaction.guild.members if not m.bot]
        if role:
            havuz = [m for m in havuz if role in m.roles]
        if not havuz:
            await interaction.response.send_message("❌ Uygun участник bulunamadı!", ephemeral=True)
            return
        secilen = random.choice(havuz)
        e = discord.Embed(title="🎰  Rastgele Участник Выбратьildi!", color=0xDC143C, timestamp=datetime.utcnow())
        e.description = (
            f"```ansi\n\u001b[1;31m🎲 KURA ÇEKİLDİ\u001b[0m\n```\n{_divider()}\n\n"
            f"Kura çekildi ve kazanan belli oldu! 🎊\n\n{_divider()}"
        )
        e.set_thumbnail(url=secilen.display_avatar.url)
        e.add_field(name="🏆 Выбратьilen", value=secilen.mention, inline=True)
        e.add_field(name="👥 Havuz", value=f"```{len(havuz)} kişi```", inline=True)
        if role:
            e.add_field(name="🎭 Role Filtresi", value=role.mention, inline=True)
        e.set_footer(text=f"Aether • {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
        await interaction.response.send_message(embed=e)

    @app_commands.command(name="hatırlatıcı", description="Belirli süre sonra seni hatırlatır (maks 60 dk)")
    async def hatirlatici(self, interaction: discord.Interaction, minutes: int, message: str):
        if minutes < 1 or minutes > 60:
            await interaction.response.send_message("❌ 1-60 minutes arası!", ephemeral=True)
            return
        e = discord.Embed(title="⏰  Hatırlatıcı Kuruldu!", color=0x3498DB, timestamp=datetime.utcnow())
        e.description = (
            f"```ansi\n\u001b[1;34m✔ HATIRLATICI AKTİF\u001b[0m\n```\n{_divider()}\n\n"
            f"**{minutes} minutes** sonra seni hatırlatacağım!\n\n{_divider()}"
        )
        e.add_field(name="⏱️ Süre", value=f"```{minutes} minutes```", inline=True)
        e.add_field(name="📝 Сообщение", value=f"```{message}```", inline=False)
        e.add_field(name="🔔 Hatırlatma", value=f"<t:{now_ts() + minutes * 60}:R>", inline=True)
        e.set_footer(text=f"Aether • {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
        await interaction.response.send_message(embed=e, ephemeral=True)
        await asyncio.sleep(minutes * 60)
        try:
            remind_e = discord.Embed(title="🔔  Hatırlatıcı!", color=0xDC143C, timestamp=datetime.utcnow())
            remind_e.description = (
                f"```ansi\n\u001b[1;31m🔔 HATIRLATMA!\u001b[0m\n```\n{_divider()}\n\n"
                f"{interaction.user.mention}, bunu hatırlatmamı istedin!\n\n{_divider()}"
            )
            remind_e.add_field(name="📝 Сообщение", value=f"```{message}```", inline=False)
            remind_e.set_footer(text=f"Aether • {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
            await interaction.channel.send(content=interaction.user.mention, embed=remind_e)
        except Exception:
            pass


async def setup(bot):
    await bot.add_cog(Fun(bot), guilds=[discord.Object(id=1421244140359909513), discord.Object(id=1107038411895881788)])
