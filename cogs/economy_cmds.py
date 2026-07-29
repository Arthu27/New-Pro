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

def _eco_embed(title: str, subtitle: str, color: int, gif_key: str = None) -> discord.Embed:
    """Минимализм embed для экономики"""
    e = discord.Embed(color=color, timestamp=datetime.utcnow())
    e.description = (
        f"## {title}\n"
        f"### {subtitle}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    )
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
            e = _eco_embed("Баланс", "Состояние счёта", 0xF1C40F)
            e.description += (
                f"**Пользователь:** {hedef.mention}\n"
                f"**Баланс:** {bal:,} {name}\n"
                f"**Запрос:** <t:{now_ts()}:R>\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            e.set_thumbnail(url=hedef.display_avatar.url)
            if interaction.guild.icon:
                e.set_footer(text=f"{interaction.guild.name} · Экономика", icon_url=interaction.guild.icon.url)
            else:
                e.set_footer(text=f"{interaction.guild.name} · Экономика")
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
                    e = discord.Embed(color=0xE74C3C, timestamp=datetime.utcnow())
                    e.description = (
                        f"## Ежедневная награда\n"
                        f"### Подождите\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"Вы уже получили ежедневную награду!\n"
                        f"Нужно подождать ещё немного.\n\n"
                        f"**Осталось:** {h} ч {m} мин\n"
                        f"**Обновление:** <t:{int((last_dt + timedelta(hours=24)).timestamp())}:R>\n\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                    )
                    if interaction.guild.icon:
                        e.set_footer(text=f"{interaction.guild.name} · Экономика", icon_url=interaction.guild.icon.url)
                    else:
                        e.set_footer(text=f"{interaction.guild.name} · Экономика")
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
            e = _eco_embed("Ежедневная награда", "Награда получена!", 0x2ECC71, "economy_daily")
            e.description += (
                f"**Получено:** +{reward:,} {name}\n"
                f"**Новый баланс:** {bal+reward:,} {name}\n"
                f"**Следующая награда:** <t:{int((now + timedelta(hours=24)).timestamp())}:R>\n\n"
                f"*Не забывайте заходить каждый день чтобы получить награду!*\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            e.set_thumbnail(url=interaction.user.display_avatar.url)
            if interaction.guild.icon:
                e.set_footer(text=f"{interaction.guild.name} · Экономика", icon_url=interaction.guild.icon.url)
            else:
                e.set_footer(text=f"{interaction.guild.name} · Экономика")
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
            e = _eco_embed("Перевод", "Перевод выполнен", 0x3498DB)
            e.description += (
                f"**Отправитель:** {interaction.user.mention}\n"
                f"**Новый баланс:** {bal-miktar:,} {name}\n\n"
                f"**Получатель:** {kullanici.mention}\n"
                f"**Новый баланс:** {get_balance(gid, tid):,} {name}\n\n"
                f"**Сумма:** {miktar:,} {name}\n"
                f"**Дата:** <t:{now_ts()}:F>\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            if interaction.guild.icon:
                e.set_footer(text=f"{interaction.guild.name} · Экономика", icon_url=interaction.guild.icon.url)
            else:
                e.set_footer(text=f"{interaction.guild.name} · Экономика")
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
            e = discord.Embed(color=0xF1C40F, timestamp=datetime.utcnow())
            e.description = (
                f"## Рейтинг богатства\n"
                f"### Самые богатые участники\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n" +
                "\n".join([
                    f"{medals[i] if i < 3 else f'**{i+1}.**'} {v.get('name', k)} — {v.get('balance', 0):,} {emoji}"
                    for i, (k, v) in enumerate(lb)
                ]) +
                f"\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            if interaction.guild.icon:
                e.set_footer(text=f"{interaction.guild.name} · Экономика", icon_url=interaction.guild.icon.url)
            else:
                e.set_footer(text=f"{interaction.guild.name} · Экономика")
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
            e = discord.Embed(color=0x2ECC71, timestamp=datetime.utcnow())
            e.description = (
                f"## Работа завершена!\n"
                f"### Зарплата получена\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"{interaction.user.mention} сегодня работал как **{job_name}**!\n\n"
                f"**Профессия:** {job_name}\n"
                f"**Заработано:** +{earned:,} {name}\n"
                f"**Общий баланс:** {bal+earned:,} {name}\n"
                f"**Следующая работа:** <t:{int((now + timedelta(hours=1)).timestamp())}:R>\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            e.set_thumbnail(url=interaction.user.display_avatar.url)
            if interaction.guild.icon:
                e.set_footer(text=f"{interaction.guild.name} · Экономика", icon_url=interaction.guild.icon.url)
            else:
                e.set_footer(text=f"{interaction.guild.name} · Экономика")
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
                e = discord.Embed(color=0x2ECC71, timestamp=datetime.utcnow())
                e.description = (
                    f"## Казино\n"
                    f"### Вы выиграли!\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"Удача на вашей стороне! Вы выиграли удвоенную ставку.\n\n"
                    f"**Выиграно:** +{miktar:,} {name}\n"
                    f"**Новый баланс:** {bal+miktar:,} {name}\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                )
                e.set_image(url=gif("economy_win"))
            else:
                set_balance(gid, uid, bal - miktar, interaction.user.display_name)
                e = discord.Embed(color=0xE74C3C, timestamp=datetime.utcnow())
                e.description = (
                    f"## Казино\n"
                    f"### Вы проиграли\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"Удача отвернулась от вас. Повезёт в следующий раз!\n\n"
                    f"**Проиграно:** -{miktar:,} {name}\n"
                    f"**Новый баланс:** {bal-miktar:,} {name}\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                )
                e.set_image(url=gif("economy_lose"))
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
            e = discord.Embed(color=color, timestamp=datetime.utcnow())
            e.description = (
                f"## Слот-машина\n"
                f"### Результат\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"# {' '.join(s)}\n\n"
                f"**Результат:** {msg}\n"
                f"**Новый баланс:** {bal+kazanc:,} {name}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            e.set_image(url=gif(gif_key))
            if interaction.guild.icon:
                e.set_footer(text=f"{interaction.guild.name} · Экономика", icon_url=interaction.guild.icon.url)
            else:
                e.set_footer(text=f"{interaction.guild.name} · Экономика")
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
                e = discord.Embed(color=0x2ECC71, timestamp=datetime.utcnow())
                e.description = (
                    f"## Ограбление\n"
                    f"### Успешно!\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"{interaction.user.mention} ограбил {hedef.mention} в темноте ночи!\n\n"
                    f"**Украдено:** {miktar_c:,} {name}\n"
                    f"**Новый баланс:** {kendi_bal+miktar_c:,} {name}\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                )
                e.set_image(url=gif("economy_win"))
            else:
                ceza = random.randint(10, 50)
                set_balance(gid, uid, max(0, kendi_bal - ceza), interaction.user.display_name)
                e = discord.Embed(color=0xE74C3C, timestamp=datetime.utcnow())
                e.description = (
                    f"## Ограбление\n"
                    f"### Неудачно!\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"{interaction.user.mention} пойман на месте преступления и заплатил штраф!\n\n"
                    f"**Штраф:** -{ceza:,} {name}\n"
                    f"**Новый баланс:** {max(0, kendi_bal-ceza):,} {name}\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                )
                e.set_image(url=gif("economy_lose"))
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
        e = discord.Embed(color=0xF1C40F, timestamp=datetime.utcnow())
        e.description = (
            f"## Магазин сервера\n"
            f"### Доступные товары\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        )
        for item in items[:10]:
            e.description += f"**{item.get('name','?')}** — {item.get('price',0):,} {emoji}\n*{item.get('description', '-')}*\n\n"
        e.description += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        if interaction.guild.icon:
            e.set_footer(text=f"{interaction.guild.name} · Экономика", icon_url=interaction.guild.icon.url)
        else:
            e.set_footer(text=f"{interaction.guild.name} · Экономика")
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
        e = discord.Embed(color=0x2ECC71, timestamp=datetime.utcnow())
        e.description = (
            f"## Покупка\n"
            f"### Успешно!\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"**{item['name']}** успешно куплен!\n\n"
            f"**Товар:** {item['name']}\n"
            f"**Оплачено:** -{price:,} {name}\n"
            f"**Остаток:** {bal-price:,} {name}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        if interaction.guild.icon:
            e.set_footer(text=f"{interaction.guild.name} · Экономика", icon_url=interaction.guild.icon.url)
        else:
            e.set_footer(text=f"{interaction.guild.name} · Экономика")
        await interaction.response.send_message(embed=e)


async def setup(bot):
    await bot.add_cog(Economy(bot), guilds=[discord.Object(id=1421244140359909513), discord.Object(id=1107038411895881788)])
