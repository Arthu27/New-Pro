"""
Economy Cog
Экономическая система — database (SQLite)
Тёмная тема, без эмодзи, русский язык
"""

import discord
from discord.ext import commands
from datetime import datetime, timedelta
import random

from logger import get_logger
from db import UserData

log = get_logger("economy_cog")

DEFAULT_DATA = {
    'balance': 100,
    'bank': 0,
    'daily_last': None,
    'work_last': None,
    'beg_last': None,
    'inventory': []
}


class EconomyCog(commands.Cog):
    """Экономическая система"""

    def __init__(self, bot):
        self.bot = bot
        self.db = UserData("economy")

    def _get(self, user_id: int) -> dict:
        data = self.db.get(user_id)
        if data is None:
            data = dict(DEFAULT_DATA)
            self.db.set(user_id, data)
        return data

    def _save(self, user_id: int, data: dict):
        self.db.set(user_id, data)

    # ── balance ──────────────────────────────────────────────────────────
    @commands.command(name='balance', aliases=['bakiye', 'cüzdan', 'para'])
    async def balance(self, ctx, member: discord.Member = None):
        """Показать баланс"""
        member = member or ctx.author
        data = self._get(member.id)

        embed = discord.Embed(
            title=f"Баланс — {member.display_name}",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )
        embed.add_field(name="Кошелёк", value=f"${data['balance']:,}", inline=True)
        embed.add_field(name="Банк", value=f"${data['bank']:,}", inline=True)
        embed.add_field(name="Итого", value=f"${data['balance'] + data['bank']:,}", inline=True)
        await ctx.send(embed=embed)

    # ── daily ────────────────────────────────────────────────────────────
    @commands.command(name='daily', aliases=['günlük'])
    async def daily(self, ctx):
        """Ежедневная награда"""
        data = self._get(ctx.author.id)

        if data['daily_last']:
            last = datetime.fromisoformat(data['daily_last'])
            diff = datetime.now() - last
            if diff < timedelta(hours=24):
                remaining = timedelta(hours=24) - diff
                h = int(remaining.total_seconds() / 3600)
                m = int((remaining.total_seconds() % 3600) / 60)
                embed = discord.Embed(
                    title="Ежедневная награда",
                    description=f"Вы уже получили награду. Попробуйте через {h}ч {m}мин.",
                    color=discord.Color.dark_grey()
                )
                await ctx.send(embed=embed)
                return

        amount = random.randint(100, 500)
        data['balance'] += amount
        data['daily_last'] = datetime.now().isoformat()
        self._save(ctx.author.id, data)

        embed = discord.Embed(
            title="Ежедневная награда",
            description=f"Получено: ${amount:,}",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )
        await ctx.send(embed=embed)

    # ── work ─────────────────────────────────────────────────────────────
    @commands.command(name='work', aliases=['çalış'])
    async def work(self, ctx):
        """Работать"""
        data = self._get(ctx.author.id)

        if data['work_last']:
            last = datetime.fromisoformat(data['work_last'])
            diff = datetime.now() - last
            if diff < timedelta(minutes=30):
                m = int((timedelta(minutes=30) - diff).total_seconds() / 60)
                embed = discord.Embed(
                    title="Работа",
                    description=f"Отдохните. Попробуйте через {m} мин.",
                    color=discord.Color.dark_grey()
                )
                await ctx.send(embed=embed)
                return

        jobs = [
            ("Вы работали программистом", 200, 500),
            ("Вы работали поваром", 150, 400),
            ("Вы работали врачом", 300, 600),
            ("Вы работали учителем", 180, 450),
            ("Вы работали полицейским", 250, 550),
        ]
        job, lo, hi = random.choice(jobs)
        amount = random.randint(lo, hi)
        data['balance'] += amount
        data['work_last'] = datetime.now().isoformat()
        self._save(ctx.author.id, data)

        embed = discord.Embed(
            title="Работа",
            description=f"{job}\nЗаработано: ${amount:,}",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )
        await ctx.send(embed=embed)

    # ── beg ──────────────────────────────────────────────────────────────
    @commands.command(name='beg', aliases=['dilenci'])
    async def beg(self, ctx):
        """Попросить деньги"""
        data = self._get(ctx.author.id)

        if data['beg_last']:
            last = datetime.fromisoformat(data['beg_last'])
            diff = datetime.now() - last
            if diff < timedelta(minutes=15):
                m = int((timedelta(minutes=15) - diff).total_seconds() / 60)
                embed = discord.Embed(
                    title="Попрошайничество",
                    description=f"Попробуйте через {m} мин.",
                    color=discord.Color.dark_grey()
                )
                await ctx.send(embed=embed)
                return

        data['beg_last'] = datetime.now().isoformat()

        if random.random() < 0.3:
            self._save(ctx.author.id, data)
            embed = discord.Embed(
                title="Попрошайничество",
                description="Никто не дал вам денег.",
                color=discord.Color.dark_grey()
            )
            await ctx.send(embed=embed)
            return

        amount = random.randint(10, 100)
        data['balance'] += amount
        self._save(ctx.author.id, data)

        embed = discord.Embed(
            title="Попрошайничество",
            description=f"Получено: ${amount:,}",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )
        await ctx.send(embed=embed)

    # ── rob ──────────────────────────────────────────────────────────────
    @commands.command(name='rob', aliases=['soy'])
    async def rob(self, ctx, member: discord.Member):
        """Ограбить пользователя"""
        if member == ctx.author:
            await ctx.send("Нельзя грабить себя.")
            return
        if member.bot:
            await ctx.send("Нельзя грабить ботов.")
            return

        data = self._get(ctx.author.id)
        target = self._get(member.id)

        if target['balance'] < 50:
            await ctx.send(f"У {member.display_name} недостаточно денег.")
            return

        if random.random() < 0.5:
            penalty = min(data['balance'], 100)
            data['balance'] -= penalty
            self._save(ctx.author.id, data)
            embed = discord.Embed(
                title="Ограбление",
                description=f"Вас поймали! Потеряно: ${penalty:,}",
                color=discord.Color.dark_grey()
            )
            await ctx.send(embed=embed)
            return

        amount = min(target['balance'], random.randint(50, 200))
        data['balance'] += amount
        target['balance'] -= amount
        self._save(ctx.author.id, data)
        self._save(member.id, target)

        embed = discord.Embed(
            title="Ограбление",
            description=f"Украдено у {member.display_name}: ${amount:,}",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )
        await ctx.send(embed=embed)

    # ── deposit / withdraw ───────────────────────────────────────────────
    @commands.command(name='deposit', aliases=['yatır'])
    async def deposit(self, ctx, amount: int):
        """Положить деньги в банк"""
        data = self._get(ctx.author.id)
        if amount <= 0:
            await ctx.send("Неверная сумма.")
            return
        if amount > data['balance']:
            await ctx.send("Недостаточно денег в кошельке.")
            return

        data['balance'] -= amount
        data['bank'] += amount
        self._save(ctx.author.id, data)

        embed = discord.Embed(
            title="Депозит",
            description=f"Положено в банк: ${amount:,}",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )
        await ctx.send(embed=embed)

    @commands.command(name='withdraw', aliases=['çek'])
    async def withdraw(self, ctx, amount: int):
        """Снять деньги из банка"""
        data = self._get(ctx.author.id)
        if amount <= 0:
            await ctx.send("Неверная сумма.")
            return
        if amount > data['bank']:
            await ctx.send("Недостаточно денег в банке.")
            return

        data['bank'] -= amount
        data['balance'] += amount
        self._save(ctx.author.id, data)

        embed = discord.Embed(
            title="Снятие",
            description=f"Снято из банка: ${amount:,}",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )
        await ctx.send(embed=embed)

    # ── shop / buy / inventory ───────────────────────────────────────────
    ITEMS = {
        "игровая консоль": 500,
        "ноутбук": 2000,
        "машина": 10000,
        "дом": 50000,
        "самолёт": 100000,
    }

    @commands.command(name='shop', aliases=['mağaza'])
    async def shop(self, ctx):
        """Магазин"""
        embed = discord.Embed(
            title="Магазин",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )
        for name, price in self.ITEMS.items():
            embed.add_field(name=name.title(), value=f"${price:,}", inline=True)
        await ctx.send(embed=embed)

    @commands.command(name='buy', aliases=['satınal'])
    async def buy(self, ctx, *, item: str):
        """Купить предмет"""
        key = item.lower()
        if key not in self.ITEMS:
            await ctx.send("Предмет не найден.")
            return

        price = self.ITEMS[key]
        data = self._get(ctx.author.id)

        if data['balance'] < price:
            await ctx.send("Недостаточно денег.")
            return

        data['balance'] -= price
        data['inventory'].append(key)
        self._save(ctx.author.id, data)

        embed = discord.Embed(
            title="Покупка",
            description=f"Предмет: {item}\nЦена: ${price:,}",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )
        await ctx.send(embed=embed)

    @commands.command(name='inventory', aliases=['envanter'])
    async def inventory(self, ctx, member: discord.Member = None):
        """Инвентарь"""
        member = member or ctx.author
        data = self._get(member.id)

        if not data['inventory']:
            embed = discord.Embed(
                title="Инвентарь",
                description="Пусто.",
                color=discord.Color.dark_grey()
            )
            await ctx.send(embed=embed)
            return

        embed = discord.Embed(
            title=f"Инвентарь — {member.display_name}",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )
        for item in data['inventory']:
            embed.add_field(name=item.title(), value="—", inline=True)
        await ctx.send(embed=embed)

    # ── transfer ─────────────────────────────────────────────────────────
    @commands.command(name='transfer', aliases=['отправить'])
    async def transfer(self, ctx, member: discord.Member, amount: int):
        """Перевести деньги"""
        if member == ctx.author or member.bot:
            await ctx.send("Неверный получатель.")
            return
        if amount <= 0:
            await ctx.send("Неверная сумма.")
            return

        data = self._get(ctx.author.id)
        if data['balance'] < amount:
            await ctx.send("Недостаточно денег.")
            return

        target = self._get(member.id)
        data['balance'] -= amount
        target['balance'] += amount
        self._save(ctx.author.id, data)
        self._save(member.id, target)

        embed = discord.Embed(
            title="Перевод",
            description=f"Отправлено {member.mention}: ${amount:,}",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(EconomyCog(bot))
    log.info("EconomyCog загружен (database)")
