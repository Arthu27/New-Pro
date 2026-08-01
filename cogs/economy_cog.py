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
import io
import os
import math
from PIL import Image, ImageDraw, ImageFont

WHITE = (255, 255, 255)
BLACK = (20, 20, 25)
EMERALD = (16, 185, 129)
MUTED = (110, 115, 125)
SS = 4

ROOT = os.path.join(os.path.dirname(__file__), '..')
FONTS = os.path.join(ROOT, 'assets', 'fonts')
BG_PATH = os.path.join(ROOT, 'assets', 'profile_bg_pro.jpg')
FONT_B = os.path.join(FONTS, 'Bold.ttf')
FONT_R = os.path.join(FONTS, 'Regular.ttf')


def _f(bold=False, sz=20):
    try:
        return ImageFont.truetype(FONT_B if bold else FONT_R, sz)
    except Exception:
        return ImageFont.load_default()


def _ss_render(w, h, draw_fn, scale=SS):
    big = Image.new('RGBA', (w * scale, h * scale), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    draw_fn(d, scale)
    return big.resize((w, h), Image.Resampling.LANCZOS)


def _load_bg(w, h):
    try:
        bg = Image.open(BG_PATH).convert('RGBA')
        bw, bh = bg.size
        target_ratio = w / h
        src_ratio = bw / bh
        if src_ratio > target_ratio:
            new_w = int(bh * target_ratio)
            x0 = (bw - new_w) // 2
            bg = bg.crop((x0, 0, x0 + new_w, bh))
        else:
            new_h = int(bw / target_ratio)
            y0 = (bh - new_h) // 2
            bg = bg.crop((0, y0, bw, y0 + new_h))
        return bg.resize((w, h), Image.Resampling.LANCZOS)
    except Exception:
        return Image.new('RGBA', (w, h), (255, 255, 255, 255))


def _icon_wallet(d, cx, cy, s, w, color):
    bw, bh = s * 0.64, s * 0.46
    x0, y0 = cx - bw / 2, cy - bh / 2
    x1, y1 = cx + bw / 2, cy + bh / 2
    d.rounded_rectangle((x0, y0, x1, y1), radius=bh * 0.22, outline=color, width=w)
    d.line([(x0, y0 + bh * 0.32), (x1, y0 + bh * 0.32)], fill=color, width=max(1, int(w * 0.7)))
    r = s * 0.085
    ccx = x1 - r * 1.5
    ccy = y0 + bh * 0.66
    d.ellipse((ccx - r, ccy - r, ccx + r, ccy + r), outline=color, width=max(1, int(w * 0.8)))


def _icon_badge(diameter, glyph_fn, ring_color=BLACK, ring_w=None, icon_color=EMERALD):
    ring_w = ring_w if ring_w is not None else max(2, diameter // 22)

    def draw(d, scale):
        size = diameter * scale
        rw = ring_w * scale
        r = size * 0.22
        d.rounded_rectangle((rw / 2, rw / 2, size - rw / 2 - 1, size - rw / 2 - 1),
                             radius=r, fill=WHITE, outline=ring_color, width=rw)
        glyph_fn(d, size / 2, size / 2, size * 0.60, max(2, int(size * 0.032)), icon_color)

    return _ss_render(diameter, diameter, draw)


def _corner_bracket(size, thickness, length_ratio=0.35, color=EMERALD):
    def draw(d, scale):
        t = thickness * scale
        L = size * scale * length_ratio
        d.line([(0, t / 2), (L, t / 2)], fill=color, width=t)
        d.line([(t / 2, 0), (t / 2, L)], fill=color, width=t)
    return _ss_render(size, size, draw)


def _rounded_panel(w, h, radius, fill=WHITE, outline=BLACK, ow=3):
    def draw(d, scale):
        r = radius * scale
        o = ow * scale
        d.rounded_rectangle((o / 2, o / 2, w * scale - o / 2 - 1, h * scale - o / 2 - 1),
                             radius=r, fill=fill, outline=outline, width=o)
    return _ss_render(w, h, draw)


def generate_economy_card(cog, member: discord.Member, category: str = "shop") -> Image.Image:
    W = 920
    data = cog._get(member.id)
    items = list(cog.ITEMS.items()) if category == "shop" else []
    if category == "inventory":
        items = [(itm, 0) for itm in data['inventory']]

    H = max(520, 110 + max(3, len(items)) * 104 + 30)
    bg = _load_bg(W, H)
    d = ImageDraw.Draw(bg)

    # Header
    header_box = _rounded_panel(872, 72, radius=14, fill=WHITE, outline=BLACK, ow=2)
    bg.alpha_composite(header_box, (24, 20))

    badge = _icon_badge(52, _icon_wallet, ring_color=BLACK, ring_w=2, icon_color=EMERALD)
    bg.alpha_composite(badge, (36, 30))

    title_map = {
        "shop": "МАГАЗИН СЕРВЕРА",
        "inventory": f"ИНВЕНТАРЬ • {member.display_name.upper()}",
        "balance": f"БАЛАНС • {member.display_name.upper()}"
    }
    title_text = title_map.get(category, "ЭКОНОМИКА СЕРВЕРА")
    d.text((100, 26), title_text, fill=BLACK, font=_f(True, 24))
    d.text((100, 56), "ФИНАНСОВАЯ СИСТЕМА • ИНВЕНТАРЬ И ПРИВИЛЕГИИ", fill=MUTED, font=_f(False, 15))

    pill = _rounded_panel(156, 36, radius=10, fill=WHITE, outline=EMERALD, ow=2)
    bg.alpha_composite(pill, (724, 38))
    d.text((742, 46), "ECONOMY v4.0", fill=EMERALD, font=_f(True, 14))

    if category == "balance":
        box_w, box_h = 872, 130
        box1 = _rounded_panel(box_w, box_h, radius=14, fill=WHITE, outline=BLACK, ow=2)
        bg.alpha_composite(box1, (24, 110))
        d.text((60, 135), "НАЛИЧНЫЙ БАЛАНС", fill=MUTED, font=_f(False, 18))
        d.text((60, 170), f"{data['balance']:,} МОНЕТ".replace(",", " "), fill=BLACK, font=_f(True, 38))

        box2 = _rounded_panel(box_w, box_h, radius=14, fill=WHITE, outline=BLACK, ow=2)
        bg.alpha_composite(box2, (24, 260))
        d.text((60, 285), "БАНКОВСКИЙ СЧЁТ", fill=MUTED, font=_f(False, 18))
        d.text((60, 320), f"{data['bank']:,} МОНЕТ".replace(",", " "), fill=EMERALD, font=_f(True, 38))
    else:
        box_w, box_h = 872, 92
        gap_y = 12
        start_x, start_y = 24, 108
        display_items = items if items else [("Пусто", 0)]
        for idx, (name, price) in enumerate(display_items):
            bx = start_x
            by = start_y + idx * (box_h + gap_y)

            box = _rounded_panel(box_w, box_h, radius=14, fill=WHITE, outline=BLACK, ow=2)
            bg.alpha_composite(box, (bx, by))

            ibadge = _icon_badge(64, _icon_wallet, ring_color=BLACK, ring_w=2, icon_color=EMERALD)
            bg.alpha_composite(ibadge, (bx + 16, by + 14))

            d.text((bx + 94, by + 15), name.title(), fill=BLACK, font=_f(True, 30))
            d.text((bx + 94, by + 53), "Предмет магазина сервера" if price > 0 else "В инвентаре", fill=MUTED, font=_f(False, 22))

            if price > 0:
                p_txt = f"{price:,} МОНЕТ".replace(",", " ")
                pw = len(p_txt) * 14
                d.text((bx + box_w - 24 - pw, by + 32), p_txt, fill=EMERALD, font=_f(True, 22))
            else:
                d.text((bx + box_w - 180, by + 32), "В НАЛИЧИИ", fill=EMERALD, font=_f(True, 22))

    br = _corner_bracket(40, 4, color=EMERALD)
    bg.alpha_composite(br, (6, 6))
    bg.alpha_composite(br.rotate(270), (W - 46, 6))
    bg.alpha_composite(br.rotate(90), (6, H - 46))
    bg.alpha_composite(br.rotate(180), (W - 46, H - 46))

    return bg


def generate_economy_bytes(cog, member: discord.Member, category: str = "shop") -> io.BytesIO:
    card = generate_economy_card(cog, member, category).convert('RGB')
    buf = io.BytesIO()
    card.save(buf, format='PNG', optimize=True)
    buf.seek(0)
    return buf


class EconomySelect(discord.ui.Select):
    def __init__(self, cog, member, current_cat="shop"):
        self.cog = cog
        self.member = member
        options = [
            discord.SelectOption(
                label="Магазин сервера",
                value="shop",
                description="Просмотр и покупка ролей и предметов",
                emoji="🛍️",
                default=(current_cat == "shop")
            ),
            discord.SelectOption(
                label="Инвентарь пользователя",
                value="inventory",
                description="Список купленных предметов в инвентаре",
                emoji="🎒",
                default=(current_cat == "inventory")
            ),
            discord.SelectOption(
                label="Баланс и банковский счёт",
                value="balance",
                description="Текущее финансовое состояние",
                emoji="💰",
                default=(current_cat == "balance")
            )
        ]
        super().__init__(
            placeholder="📂 Выберите раздел экономики...",
            options=options,
            custom_id="economy_select_v4_pro"
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cat_id = self.values[0]
        img_buf = await interaction.client.loop.run_in_executor(
            None, generate_economy_bytes, self.cog, interaction.user, cat_id
        )
        file = discord.File(img_buf, filename="economy_card.png")
        view = EconomyView(self.cog, interaction.user, current_cat=cat_id)
        await interaction.edit_original_response(embed=None, attachments=[file], view=view)


class EconomyView(discord.ui.View):
    def __init__(self, cog, member, current_cat="shop"):
        super().__init__(timeout=300)
        self.add_item(EconomySelect(cog, member, current_cat=current_cat))


    ITEMS = {
        "игровая консоль": 500,
        "ноутбук": 2000,
        "машина": 10000,
        "дом": 50000,
        "самолёт": 100000,
    }

    @commands.command(name='shop', aliases=['mağaza', 'магазин'])
    async def shop(self, ctx):
        """Профессиональное меню магазина сервера"""
        img_buf = await self.bot.loop.run_in_executor(
            None, generate_economy_bytes, self, ctx.author, "shop"
        )
        file = discord.File(img_buf, filename="economy_card.png")
        view = EconomyView(self, ctx.author, current_cat="shop")
        await ctx.send(file=file, view=view)

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

    @commands.command(name='inventory', aliases=['envanter', 'инвентарь'])
    async def inventory(self, ctx, member: discord.Member = None):
        """Профессиональное меню инвентаря"""
        member = member or ctx.author
        img_buf = await self.bot.loop.run_in_executor(
            None, generate_economy_bytes, self, member, "inventory"
        )
        file = discord.File(img_buf, filename="economy_card.png")
        view = EconomyView(self, member, current_cat="inventory")
        await ctx.send(file=file, view=view)

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
