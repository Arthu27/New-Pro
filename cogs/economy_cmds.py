"""Экономика командаları"""
import discord
from discord.ext import commands
from discord import app_commands
import random
import json
import os
from datetime import datetime, timedelta
from cogs.embed_utils import _divider, now_ts, gif

DATA_DIR = 'data'

def get_balance(guild_id: str, user_id: str) -> int:
    f = f'{DATA_DIR}/balance_{guild_id}.json'
    if not os.path.exists(f):
        return 0
    with open(f) as fp:
        data = json.load(fp)
    return data.get(user_id, {}).get('balance', 0)

def set_balance(guild_id: str, user_id: str, amount: int, name: str = ''):
    os.makedirs(DATA_DIR, exist_ok=True)
    f = f'{DATA_DIR}/balance_{guild_id}.json'
    data = {}
    if os.path.exists(f):
        with open(f) as fp:
            data = json.load(fp)
    if user_id not in data:
        data[user_id] = {'name': name, 'balance': 0}
    data[user_id]['balance'] = max(0, amount)
    if name:
        data[user_id]['name'] = name
    with open(f, 'w') as fp:
        json.dump(data, fp, indent=2)

def get_currency(guild_id: str) -> tuple:
    f = f'{DATA_DIR}/economy_{guild_id}.json'
    if not os.path.exists(f):
        return 'Coin', '💰'
    with open(f) as fp:
        d = json.load(fp)
    return d.get('currency_name', 'Coin'), d.get('currency_emoji', '💰')

def _eco_embed(title: str, badge: str, color: int, gif_key: str = None) -> discord.Embed:
    e = discord.Embed(title=title, color=color, timestamp=datetime.utcnow())
    e.description = f"```ansi\n\u001b[1;33m{badge}\u001b[0m\n```\n{_divider()}"
    if gif_key:
        e.set_image(url=gif(gif_key))
    return e

class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="economy", description="Экономика командаları: bakiye, деньlük, transfer, sıralama")
    @app_commands.choices(islem=[
        app_commands.Choice(name="balance", value="bakiye"),
        app_commands.Choice(name="деньlük", value="gunluk"),
        app_commands.Choice(name="transfer", value="transfer"),
        app_commands.Choice(name="ranking", value="siralama"),
    ])
    async def economy(self, interaction: discord.Interaction, islem: str,
                     kullanici: discord.Member = None, miktar: int = None):
        gid = str(interaction.guild_id)

        if islem == "bakiye":
            hedef = kullanici or interaction.user
            bal = get_balance(gid, str(hedef.id))
            name, emoji = get_currency(gid)
            e = _eco_embed(f"{emoji}  BAKİYE SORGULAMA", "💳 HESAP DURUMU", 0xF1C40F)
            e.set_thumbnail(url=hedef.display_avatar.url)
            e.add_field(name="👤 Пользователь", value=f"{hedef.mention}", inline=True)
            e.add_field(name=f"{emoji} Bakiye", value=f"```{bal:,} {name}```", inline=True)
            e.add_field(name="🕐 Sorgu", value=f"<t:{now_ts()}:R>", inline=False)
            e.set_footer(text=f"Aether Экономика • {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
            await interaction.response.send_message(embed=e)

        elif islem == "gunluk":
            uid = str(interaction.user.id)
            cooldown_f = f'{DATA_DIR}/daily_{gid}.json'
            os.makedirs(DATA_DIR, exist_ok=True)
            cooldowns = {}
            if os.path.exists(cooldown_f):
                with open(cooldown_f) as fp:
                    cooldowns = json.load(fp)
            last = cooldowns.get(uid)
            now = datetime.utcnow()
            if last:
                last_dt = datetime.fromisoformat(last)
                diff = now - last_dt
                if diff < timedelta(hours=24):
                    remaining = timedelta(hours=24) - diff
                    h, m = divmod(int(remaining.total_seconds()) // 60, 60)
                    e = discord.Embed(title="⏰  Günlük Ödül — Baddme", color=0xE74C3C, timestamp=datetime.utcnow())
                    e.description = (
                        f"```ansi\n\u001b[1;31m⏳ COOLDOWN AKTİF\u001b[0m\n```\n{_divider()}\n\n"
                        f"Günlük ödülünü zaten aldın! Biraz daha baddmen gerekiyor.\n\n{_divider()}"
                    )
                    e.add_field(name="⏱️ Kalan Süre", value=f"```{h} час {m} minutes```", inline=True)
                    e.add_field(name="🔄 Обновитьme", value=f"<t:{int((last_dt + timedelta(hours=24)).timestamp())}:R>", inline=True)
                    e.set_footer(text=f"Aether Экономика • {interaction.guild.name}")
                    await interaction.response.send_message(embed=e, ephemeral=True)
                    return
            f2 = f'{DATA_DIR}/economy_{gid}.json'
            reward = 50
            if os.path.exists(f2):
                with open(f2) as fp:
                    reward = json.load(fp).get('daily_reward', 50)
            bal = get_balance(gid, uid)
            set_balance(gid, uid, bal + reward, interaction.user.display_name)
            cooldowns[uid] = now.isoformat()
            with open(cooldown_f, 'w') as fp:
                json.dump(cooldowns, fp)
            name, emoji = get_currency(gid)
            e = _eco_embed(f"🎁  Günlük Ödül Alındı!", "🎁 GÜNLÜK ÖDÜL", 0x2ECC71, "economy_daily")
            e.set_thumbnail(url=interaction.user.display_avatar.url)
            e.add_field(name="💰 Kazanılan", value=f"```+{reward:,} {name}```", inline=True)
            e.add_field(name="🏦 Новый Bakiye", value=f"```{bal+reward:,} {name}```", inline=True)
            e.add_field(name="🔄 Последнийraki Ödül", value=f"<t:{int((now + timedelta(hours=24)).timestamp())}:R>", inline=False)
            e.add_field(name="💡 İpucu", value="*Her день вход yaparak ödülünü almayı unutma!*", inline=False)
            e.set_footer(text=f"Aether Экономика • {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
            await interaction.response.send_message(embed=e)

        elif islem == "transfer":
            if not kullanici or not miktar:
                await interaction.response.send_message("❌ Пользователь ve miktar belirtmelisin!", ephemeral=True)
                return
            if miktar <= 0 or kullanici.bot or kullanici == interaction.user:
                await interaction.response.send_message("❌ Geçersiz действие!", ephemeral=True)
                return
            uid, tid = str(interaction.user.id), str(kullanici.id)
            bal = get_balance(gid, uid)
            if bal < miktar:
                await interaction.response.send_message(f"❌ Yetersiz bakiye! Bakiyen: **{bal:,}**", ephemeral=True)
                return
            set_balance(gid, uid, bal - miktar, interaction.user.display_name)
            set_balance(gid, tid, get_balance(gid, tid) + miktar, kullanici.display_name)
            name, emoji = get_currency(gid)
            e = _eco_embed("💸  Transfer ОКlandı", "💸 PARA TRANSFERİ", 0x3498DB)
            e.add_field(name="📤 Отправитьen", value=f"{interaction.user.mention}\n`Новый: {bal-miktar:,} {name}`", inline=True)
            e.add_field(name="📥 Alan", value=f"{kullanici.mention}\n`Новый: {get_balance(gid, tid):,} {name}`", inline=True)
            e.add_field(name=f"{emoji} Miktar", value=f"```{miktar:,} {name}```", inline=False)
            e.add_field(name="🕐 Дата", value=f"<t:{now_ts()}:F>", inline=False)
            e.set_footer(text=f"Aether Экономика • {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
            await interaction.response.send_message(embed=e)

        elif islem == "siralama":
            f = f'{DATA_DIR}/balance_{gid}.json'
            if not os.path.exists(f):
                await interaction.response.send_message("❌ Henüz veri yok!", ephemeral=True)
                return
            with open(f) as fp:
                data = json.load(fp)
            name, emoji = get_currency(gid)
            lb = sorted(data.items(), key=lambda x: x[1].get('balance', 0), reverse=True)[:10]
            medals = ['🥇', '🥈', '🥉']
            e = discord.Embed(title=f"🏆  ZENGİNLİK SIRALAMASI", color=0xF1C40F, timestamp=datetime.utcnow())
            e.description = (
                f"```ansi\n\u001b[1;33m👑 EN ZENGİN ÜYELER\u001b[0m\n```\n{_divider()}\n\n" +
                "\n".join([
                    f"{medals[i] if i < 3 else f'`{i+1}.`'} **{v.get('name', k)}** — `{v.get('balance', 0):,} {emoji}`"
                    for i, (k, v) in enumerate(lb)
                ])
            )
            e.set_footer(text=f"Aether Экономика • {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
            await interaction.response.send_message(embed=e)

    @app_commands.command(name="games", description="Oyun командаları: çalış, kumar, slot, soygun")
    @app_commands.choices(oyun=[
        app_commands.Choice(name="çalış", value="calis"),
        app_commands.Choice(name="kumar", value="kumar"),
        app_commands.Choice(name="slot", value="slot"),
        app_commands.Choice(name="soygun", value="soygun"),
    ])
    async def oyunlar(self, interaction: discord.Interaction, oyun: str,
                     hedef: discord.Member = None, miktar: int = None):
        gid = str(interaction.guild_id)
        uid = str(interaction.user.id)
        name, emoji = get_currency(gid)

        if oyun == "calis":
            cooldown_f = f'{DATA_DIR}/work_{gid}.json'
            os.makedirs(DATA_DIR, exist_ok=True)
            cooldowns = {}
            if os.path.exists(cooldown_f):
                with open(cooldown_f) as fp:
                    cooldowns = json.load(fp)
            last = cooldowns.get(uid)
            now = datetime.utcnow()
            if last:
                diff = now - datetime.fromisoformat(last)
                if diff < timedelta(hours=1):
                    remaining = timedelta(hours=1) - diff
                    m = int(remaining.total_seconds()) // 60
                    await interaction.response.send_message(
                        f"⏰ **{m} minutes** sonra tekrar çalışabilirsin!", ephemeral=True)
                    return
            jobs = [
                ("👨‍💻 Текстlımcı", 60, 120), ("👨‍🍳 Aşçı", 30, 70),
                ("🎵 Müzisyen", 40, 90), ("🎨 Ressam", 35, 80),
                ("👨‍🏫 Öğretmen", 25, 60), ("👨‍⚕️ Doktor", 80, 150),
                ("⚙️ Mühendis", 70, 130), ("🚗 Sürücü", 20, 50),
            ]
            job_name, min_earn, max_earn = random.choice(jobs)
            earned = random.randint(min_earn, max_earn)
            bal = get_balance(gid, uid)
            set_balance(gid, uid, bal + earned, interaction.user.display_name)
            cooldowns[uid] = now.isoformat()
            with open(cooldown_f, 'w') as fp:
                json.dump(cooldowns, fp)
            e = discord.Embed(title="💼  Çalışma ОКlandı!", color=0x2ECC71, timestamp=datetime.utcnow())
            e.description = (
                f"```ansi\n\u001b[1;32m✔ MAAŞ ALINDI\u001b[0m\n```\n{_divider()}\n\n"
                f"{interaction.user.mention} buдень **{job_name}** olarak çalıştı!\n\n{_divider()}"
            )
            e.set_thumbnail(url=interaction.user.display_avatar.url)
            e.add_field(name="💼 Meslek", value=f"```{job_name}```", inline=True)
            e.add_field(name="💰 Kazanılan", value=f"```+{earned:,} {name}```", inline=True)
            e.add_field(name="🏦 Всего Bakiye", value=f"```{bal+earned:,} {name}```", inline=True)
            e.add_field(name="⏰ Последнийraki Çalışma", value=f"<t:{int((now + timedelta(hours=1)).timestamp())}:R>", inline=False)
            e.set_footer(text=f"Aether Экономика • {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
            await interaction.response.send_message(embed=e)

        elif oyun == "kumar":
            if not miktar or miktar <= 0:
                await interaction.response.send_message("❌ Geçerli bir miktar belirtmelisin!", ephemeral=True)
                return
            bal = get_balance(gid, uid)
            if bal < miktar:
                await interaction.response.send_message(f"❌ Yetersiz bakiye! Bakiyen: **{bal:,}**", ephemeral=True)
                return
            kazandi = random.random() < 0.45
            if kazandi:
                set_balance(gid, uid, bal + miktar, interaction.user.display_name)
                e = discord.Embed(title="🎰  Kumar — KAZANDIN!", color=0x2ECC71, timestamp=datetime.utcnow())
                e.description = (
                    f"```ansi\n\u001b[1;32m🎉 KAZANDIN!\u001b[0m\n```\n{_divider()}\n\n"
                    f"Şansın yaver gitti! Bahsin iki katını kazandın.\n\n{_divider()}"
                )
                e.set_image(url=gif("economy_win"))
                e.add_field(name="💰 Kazanılan", value=f"```+{miktar:,} {name}```", inline=True)
                e.add_field(name="🏦 Новый Bakiye", value=f"```{bal+miktar:,} {name}```", inline=True)
            else:
                set_balance(gid, uid, bal - miktar, interaction.user.display_name)
                e = discord.Embed(title="🎰  Kumar — KAYBETTİN!", color=0xE74C3C, timestamp=datetime.utcnow())
                e.description = (
                    f"```ansi\n\u001b[1;31m💸 KAYBETTİN!\u001b[0m\n```\n{_divider()}\n\n"
                    f"Şansın bu sefer yüz çevirmedi. Bir dahaki sefere!\n\n{_divider()}"
                )
                e.set_image(url=gif("economy_lose"))
                e.add_field(name="💸 Kaybedilen", value=f"```-{miktar:,} {name}```", inline=True)
                e.add_field(name="🏦 Новый Bakiye", value=f"```{bal-miktar:,} {name}```", inline=True)
            e.set_thumbnail(url=interaction.user.display_avatar.url)
            e.set_footer(text=f"Aether Экономика • {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
            await interaction.response.send_message(embed=e)

        elif oyun == "slot":
            if not miktar or miktar <= 0:
                await interaction.response.send_message("❌ Geçerli bir miktar belirtmelisin!", ephemeral=True)
                return
            bal = get_balance(gid, uid)
            if bal < miktar:
                await interaction.response.send_message("❌ Yetersiz bakiye!", ephemeral=True)
                return
            semboller = ['🍒', '🍋', '🍊', '🍇', '⭐', '💎']
            s = [random.choice(semboller) for _ in range(3)]
            if s[0] == s[1] == s[2]:
                if s[0] == '💎':
                    kazanc, msg, color = miktar * 10, "💎 JACKPOT! 10x kazandın!", 0xF1C40F
                elif s[0] == '⭐':
                    kazanc, msg, color = miktar * 5, "⭐ SÜPER! 5x kazandın!", 0xF39C12
                else:
                    kazanc, msg, color = miktar * 3, "🎉 3x kazandın!", 0x2ECC71
                set_balance(gid, uid, bal + kazanc, interaction.user.display_name)
                gif_key = "economy_win"
            elif s[0] == s[1] or s[1] == s[2]:
                kazanc, msg, color = miktar // 2, f"Yarım eşleşme! +{miktar//2} {name}", 0xF39C12
                set_balance(gid, uid, bal + kazanc, interaction.user.display_name)
                gif_key = "economy_win"
            else:
                kazanc, msg, color = -miktar, f"Kaybettin! -{miktar} {name}", 0xE74C3C
                set_balance(gid, uid, bal - miktar, interaction.user.display_name)
                gif_key = "economy_lose"
            e = discord.Embed(title="🎰  SLOT MAKİNESİ", color=color, timestamp=datetime.utcnow())
            e.description = (
                f"```ansi\n\u001b[1;33m🎰 SLOT SONUCU\u001b[0m\n```\n{_divider()}\n\n"
                f"# {' '.join(s)}\n\n{_divider()}"
            )
            e.set_image(url=gif(gif_key))
            e.add_field(name="🎯 sonuç", value=f"```{msg}```", inline=False)
            e.add_field(name="🏦 Новый Bakiye", value=f"```{bal+kazanc:,} {name}```", inline=True)
            e.set_footer(text=f"Aether Экономика • {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
            await interaction.response.send_message(embed=e)

        elif oyun == "soygun":
            if not hedef:
                await interaction.response.send_message("❌ Hedef belirtmelisin!", ephemeral=True)
                return
            if hedef.bot or hedef == interaction.user:
                await interaction.response.send_message("❌ Geçersiz hedef!", ephemeral=True)
                return
            tid = str(hedef.id)
            hedef_bal = get_balance(gid, tid)
            kendi_bal = get_balance(gid, uid)
            if hedef_bal < 10:
                await interaction.response.send_message(f"❌ {hedef.display_name} çok fakir, soyacak bir şey yok!", ephemeral=True)
                return
            basari = random.random() < 0.4
            if basari:
                miktar_c = random.randint(1, min(hedef_bal // 3, 200))
                set_balance(gid, uid, kendi_bal + miktar_c, interaction.user.display_name)
                set_balance(gid, tid, hedef_bal - miktar_c, hedef.display_name)
                e = discord.Embed(title="🦹  SOYGUN BAŞARILI!", color=0x2ECC71, timestamp=datetime.utcnow())
                e.description = (
                    f"```ansi\n\u001b[1;32m✔ SOYGUN BAŞARILI!\u001b[0m\n```\n{_divider()}\n\n"
                    f"{interaction.user.mention} gece karanlığında {hedef.mention}'ı soydu!\n\n{_divider()}"
                )
                e.set_image(url=gif("economy_win"))
                e.add_field(name="💰 Çalınan", value=f"```{miktar_c:,} {name}```", inline=True)
                e.add_field(name="🏦 Новый Bakiye", value=f"```{kendi_bal+miktar_c:,} {name}```", inline=True)
            else:
                ceza = random.randint(10, 50)
                set_balance(gid, uid, max(0, kendi_bal - ceza), interaction.user.display_name)
                e = discord.Embed(title="🚔  SOYGUN BAŞARISIZ!", color=0xE74C3C, timestamp=datetime.utcnow())
                e.description = (
                    f"```ansi\n\u001b[1;31m✘ YAKALANDIN!\u001b[0m\n```\n{_divider()}\n\n"
                    f"{interaction.user.mention} suçüstü yakalandı ve ceza ödedi!\n\n{_divider()}"
                )
                e.set_image(url=gif("economy_lose"))
                e.add_field(name="💸 Наказание", value=f"```-{ceza:,} {name}```", inline=True)
                e.add_field(name="🏦 Новый Bakiye", value=f"```{max(0, kendi_bal-ceza):,} {name}```", inline=True)
            e.set_thumbnail(url=interaction.user.display_avatar.url)
            e.set_footer(text=f"Aether Экономика • {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
            await interaction.response.send_message(embed=e)

    @app_commands.command(name="shop", description="Сервер mağazasını görüntüle")
    async def magaza(self, interaction: discord.Interaction):
        gid = str(interaction.guild_id)
        f = f'{DATA_DIR}/shop_{gid}.json'
        name, emoji = get_currency(gid)
        if not os.path.exists(f):
            await interaction.response.send_message("🏪 Mağaza henüz boş!", ephemeral=True)
            return
        with open(f) as fp:
            items = json.load(fp)
        if not items:
            await interaction.response.send_message("🏪 Mağaza henüz boş!", ephemeral=True)
            return
        e = discord.Embed(title="🏪  SUNUCU MAĞAZASI", color=0xF1C40F, timestamp=datetime.utcnow())
        e.description = f"```ansi\n\u001b[1;33m🛒 MEVCUT ÜRÜNLER\u001b[0m\n```\n{_divider()}"
        for item in items[:10]:
            e.add_field(
                name=f"🏷️ {item.get('name','?')} — `{item.get('price',0):,} {emoji}`",
                value=f"*{item.get('description', '-')}*",
                inline=False
            )
        e.set_footer(text=f"Aether Экономика • {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
        await interaction.response.send_message(embed=e)

    @app_commands.command(name="buy", description="Купить товар в магазине")
    async def satin_al(self, interaction: discord.Interaction, urun_adi: str):
        gid = str(interaction.guild_id)
        uid = str(interaction.user.id)
        f = f'{DATA_DIR}/shop_{gid}.json'
        if not os.path.exists(f):
            await interaction.response.send_message("❌ Mağaza boş!", ephemeral=True)
            return
        with open(f) as fp:
            items = json.load(fp)
        item = next((i for i in items if i.get('name', '').lower() == urun_adi.lower()), None)
        if not item:
            await interaction.response.send_message(f"❌ **{urun_adi}** bulunamadı!", ephemeral=True)
            return
        bal = get_balance(gid, uid)
        price = item.get('price', 0)
        name, emoji = get_currency(gid)
        if bal < price:
            await interaction.response.send_message(f"❌ Yetersiz bakiye! Gerekli: **{price:,} {name}**", ephemeral=True)
            return
        set_balance(gid, uid, bal - price, interaction.user.display_name)
        e = discord.Embed(title="✅  Satın Alma Успешно!", color=0x2ECC71, timestamp=datetime.utcnow())
        e.description = (
            f"```ansi\n\u001b[1;32m✔ SATIN ALINDI\u001b[0m\n```\n{_divider()}\n\n"
            f"**{item['name']}** başarıyla satın alındı!\n\n{_divider()}"
        )
        e.add_field(name="🏷️ Ürün", value=f"```{item['name']}```", inline=True)
        e.add_field(name="💸 Ödenen", value=f"```-{price:,} {name}```", inline=True)
        e.add_field(name="🏦 Kalan Bakiye", value=f"```{bal-price:,} {name}```", inline=True)
        e.set_footer(text=f"Aether Экономика • {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
        await interaction.response.send_message(embed=e)


async def setup(bot):
    await bot.add_cog(Economy(bot), guilds=[discord.Object(id=1421244140359909513), discord.Object(id=1107038411895881788)])
