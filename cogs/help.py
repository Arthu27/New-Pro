"""
Help Cog — Luxury Dark-Gold Dashboard (Pillow)
Тёмно-синий фон с золотыми звёздами, золотые панели, фирменные иконки категорий.
"""

import os
import io
import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.join(os.path.dirname(__file__), '..')
FONTS = os.path.join(ROOT, 'assets', 'fonts')
BG_PATH = os.path.join(ROOT, 'assets', 'help_bg.png')
ICONS_DIR = os.path.join(ROOT, 'assets', 'icons')
FONT_B = os.path.join(FONTS, 'Bold.ttf')
FONT_R = os.path.join(FONTS, 'Regular.ttf')

# Палитра — тёмный люкс
BG_DEEP = (13, 16, 38)
PANEL = (24, 29, 60, 215)
PANEL_BR = (212, 175, 55, 150)
GOLD = (212, 175, 55)
GOLD_SOFT = (240, 215, 130)
TXT = (235, 238, 250)
MUTED = (148, 156, 190)
SS = 2


def _f(bold=False, sz=20):
    try:
        return ImageFont.truetype(FONT_B if bold else FONT_R, sz)
    except Exception:
        return ImageFont.load_default()


def _load_bg(w, h):
    """Фон-картинка по пропорциям; если нет — градиент со звёздами"""
    try:
        bg = Image.open(BG_PATH).convert('RGB')
        bw, bh = bg.size
        target = w / h
        src = bw / bh
        if src > target:
            nw = int(bh * target)
            x0 = (bw - nw) // 2
            bg = bg.crop((x0, 0, x0 + nw, bh))
        else:
            nh = int(bw / target)
            y0 = (bh - nh) // 2
            bg = bg.crop((0, y0, bw, y0 + nh))
        return bg.resize((w, h), Image.Resampling.LANCZOS)
    except Exception:
        import random
        bg = Image.new('RGB', (w, h), BG_DEEP)
        d = ImageDraw.Draw(bg)
        rnd = random.Random(42)
        for _ in range(140):
            x, y = rnd.randrange(w), rnd.randrange(h)
            r = rnd.choice((1, 1, 2))
            d.ellipse((x - r, y - r, x + r, y + r), fill=(212, 175, 55))
        return bg


def _panel(w, h, radius=16, fill=PANEL, border=PANEL_BR, bw=2):
    """Скруглённая полупрозрачная панель (2x supersample)"""
    img = Image.new('RGBA', (w * SS, h * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(
        (bw * SS / 2, bw * SS / 2, w * SS - bw * SS / 2 - 1, h * SS - bw * SS / 2 - 1),
        radius=radius * SS, fill=fill, outline=border, width=bw * SS)
    return img.resize((w, h), Image.Resampling.LANCZOS)


def _panel_shadowed(w, h, radius=16, border=PANEL_BR):
    """Gölgeli panel — derinlik hissi verir"""
    img = Image.new('RGBA', (w + 12, h + 12), (0, 0, 0, 0))
    sh = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, fill=(0, 0, 0, 130))
    img.alpha_composite(sh.filter(__import__('PIL.ImageFilter', fromlist=['GaussianBlur']).GaussianBlur(5)), (5, 7))
    img.alpha_composite(_panel(w, h, radius=radius, border=border), (0, 0))
    return img


_icon_cache = {}


def _cat_icon(key, size):
    """Фирменная иконка категории из assets/icons"""
    ckey = (key, size)
    if ckey in _icon_cache:
        return _icon_cache[ckey]
    img = None
    for cand in (f'{key}_256.png', f'{key}.png'):
        p = os.path.join(ICONS_DIR, cand)
        if os.path.exists(p):
            img = Image.open(p).convert('RGBA')
            break
    if img is None and key == 'afk_icon':
        p = os.path.join(ROOT, 'assets', 'afk_icon.png')
        if os.path.exists(p):
            img = Image.open(p).convert('RGBA')
    if img is None:
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    else:
        img = img.resize((size, size), Image.Resampling.LANCZOS)
        # Kenar beyaz cizgileri/artiklari yumusak sekilde kirp: %5 inset + yuvarlak kose mask
        inset = max(2, size // 20)
        img = img.crop((inset, inset, size - inset, size - inset)).resize((size, size), Image.Resampling.LANCZOS)
        mask = Image.new('L', (size, size), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius=max(6, size // 5), fill=255)
        img.putalpha(mask)
    _icon_cache[ckey] = img
    return img


CATEGORIES = [
    {
        "id": "moderation",
        "title": "Модерация",
        "commands": [
            ("!ban @user [причина]", "Бан пользователя", "Админ"),
            ("!kick @user [причина]", "Кик пользователя", "Админ"),
            ("!mute @user [время]", "Мьют пользователя", "Мод"),
            ("!unmute @user", "Размьют пользователя", "Мод"),
            ("!timeout @user [время]", "Таймаут пользователя", "Мод"),
            ("!clear [кол-во]", "Очистить сообщения", "Мод"),
            ("!lock [#канал]", "Заблокировать канал", "Мод"),
            ("!unlock [#канал]", "Разблокировать канал", "Мод"),
            ("!slowmode [сек]", "Медленный режим", "Мод"),
        ]
    },
    {
        "id": "warnings",
        "title": "Предупреждения",
        "commands": [
            ("/warn @user [причина]", "Выдать предупреждение", "Мод"),
            ("/warnings @user", "Список предупреждений", "Мод"),
            ("/clearwarns @user", "Очистить предупреждения", "Админ"),
        ]
    },
    {
        "id": "tickets",
        "title": "Тикеты",
        "commands": [
            ("/ticket-panel", "Создать панель тикетов", "Админ"),
            ("/tickets [статус]", "Список тикетов", "Все"),
            ("/ticket-info [ID]", "Информация о тикете", "Все"),
            ("/ticket-close [ID]", "Закрыть тикет", "Все"),
            ("/ticket-assign [ID] @user", "Назначить тикет", "Мод"),
        ]
    },
    {
        "id": "economy",
        "title": "Экономика",
        "commands": [
            ("!balance [@user]", "Баланс пользователя", "Все"),
            ("!daily", "Ежедневная награда", "Все"),
            ("!work", "Работать и получать монеты", "Все"),
            ("!beg", "Попросить деньги", "Все"),
            ("!rob @user", "Ограбить пользователя", "Все"),
            ("!deposit [сумма]", "Положить в банк", "Все"),
            ("!withdraw [сумма]", "Снять из банка", "Все"),
            ("!transfer @user [сумма]", "Перевести монеты", "Все"),
            ("!shop", "Магазин ролей и предметов", "Все"),
            ("!buy [предмет]", "Купить предмет", "Все"),
            ("!inventory [@user]", "Инвентарь пользователя", "Все"),
        ]
    },
    {
        "id": "music",
        "title": "Музыка",
        "commands": [
            ("!play [запрос]", "Воспроизвести трек", "Все"),
            ("!pause", "Пауза воспроизведения", "Все"),
            ("!resume", "Продолжить воспроизведение", "Все"),
            ("!skip", "Пропустить текущий трек", "Все"),
            ("!queue", "Очередь воспроизведения", "Все"),
            ("!stop", "Остановить и очистить", "Все"),
            ("!volume [0-100]", "Громкость музыки", "Все"),
            ("!loop", "Зациклить трек/очередь", "Все"),
            ("!shuffle", "Перемешать очередь", "Все"),
            ("!leave", "Покинуть голосовой канал", "Все"),
        ]
    },
    {
        "id": "levels",
        "title": "Уровни",
        "commands": [
            ("!rank [@user]", "Ранг и уровень", "Все"),
            ("!leaderboard", "Таблица лидеров", "Все"),
            ("!rewards", "Награды за уровни", "Все"),
            ("!setlevel @user [уровень]", "Установить уровень", "Админ"),
        ]
    },
    {
        "id": "utility",
        "title": "Утилиты",
        "commands": [
            ("!ping", "Задержка бота", "Все"),
            ("!botinfo", "Информация о боте", "Все"),
            ("!serverinfo", "Информация о сервере", "Все"),
            ("!userinfo [@user]", "О пользователе", "Все"),
            ("!avatar [@user]", "Аватар пользователя", "Все"),
            ("!color [hex]", "Показать цвет по hex", "Все"),
            ("!base64 [en/de] [текст]", "Кодирование Base64", "Все"),
            ("!hesap [выражение]", "Калькулятор", "Все"),
        ]
    },
    {
        "id": "voice",
        "title": "Голосовые",
        "commands": [
            ("!voicetime [@user]", "Время в голосовых", "Все"),
            ("!voiceleaderboard", "Топ по голосовым", "Все"),
            ("!voiceonline", "Кто в голосовых каналах", "Все"),
        ]
    },
    {
        "id": "fun",
        "title": "Развлечения",
        "commands": [
            ("!8ball [вопрос]", "Магический шар 8ball", "Все"),
            ("!coinflip", "Подбросить монетку", "Все"),
            ("!dice [грани]", "Бросить кубик", "Все"),
            ("!meme", "Случайный мем", "Все"),
            ("!joke", "Случайная шутка", "Все"),
            ("!cat", "Случайный кот", "Все"),
            ("!dog", "Случайная собака", "Все"),
        ]
    },
    {
        "id": "giveaway",
        "title": "Розыгрыши",
        "commands": [
            ("!giveaway [время] [побед] [приз]", "Создать розыгрыш", "Админ"),
            ("!reroll [ID]", "Перевыбрать победителя", "Админ"),
        ]
    },
    {
        "id": "profile",
        "title": "Профиль",
        "commands": [
            ("!profile [@user]", "Карточка профиля", "Все"),
            ("/profile [@user]", "Карточка профиля (slash)", "Все"),
        ]
    },
]

TOTAL_CMDS = sum(len(c["commands"]) for c in CATEGORIES)

# Категория -> фирменная иконка (assets/icons/<name>_256.png)
CAT_ICONS = {
    "moderation": "shield",
    "warnings": "warn",
    "tickets": "ticket",
    "economy": "coin",
    "music": "music",
    "levels": "levelup",
    "utility": "utility",
    "voice": "voice",
    "fun": "fun",
    "giveaway": "gift",
    "profile": "afk_icon",
    "navigation": "navigation",
}
# Эмодзи-заглушки для select-меню, если на сервере нет кастомных aether_*
CAT_EMOJIS_FALLBACK = {
    "moderation": "🛡", "warnings": "⚠", "tickets": "🎫", "economy": "🪙",
    "music": "🎵", "levels": "⭐", "utility": "⚙", "voice": "🎙",
    "fun": "🎲", "giveaway": "🎁", "profile": "👤",
}


def _header(bg, title_text, sub_text, icon_key):
    """Шапка карточки: фирменная иконка + заголовок + правый pill"""
    W = bg.size[0]
    panel = _panel(872, 76, radius=16)
    bg.alpha_composite(panel, (24, 20))
    badge = _cat_icon(icon_key, 56)
    bg.alpha_composite(badge, (40, 30))
    bg.alpha_composite(_panel(168, 40, radius=12, fill=(24, 29, 60, 215), border=(212, 175, 55, 200), bw=2), (712, 38))
    d = ImageDraw.Draw(bg)
    d.text((112, 28), title_text, fill=GOLD_SOFT, font=_f(True, 33))
    d.text((112, 66), sub_text, fill=MUTED, font=_f(False, 18))
    d.text((736, 48), "✦ HELP", fill=GOLD, font=_f(True, 16))


def generate_help_card(category_id: str = None) -> Image.Image:
    W = 920
    is_overview = category_id in (None, "overview")
    if is_overview:
        H = 112 + 4 * 128 + 3 * 14 + 90
    else:
        cat = next((c for c in CATEGORIES if c["id"] == category_id), None)
        cmds = cat["commands"] if cat else []
        H = max(520, 112 + len(cmds) * 91 + 90)

    bg = _load_bg(W, H).convert('RGBA')

    if is_overview:
        _header(bg, "AETHER  ·  СПРАВКА",
                f"{TOTAL_CMDS} КОМАНД  ·  ПРЕФИКС: !  ·  ВЫБЕРИТЕ КАТЕГОРИЮ В МЕНЮ", "aether_logo")

        # Сетка категорий 3x4 — крупные иконки, большие шрифты, тени
        box_w, box_h, gap = 284, 128, 14
        start_x, start_y = 24, 112
        for idx, cat in enumerate(CATEGORIES):
            c, r = idx % 3, idx // 3
            bx = start_x + c * (box_w + gap)
            by = start_y + r * (box_h + gap)
            bg.alpha_composite(_panel_shadowed(box_w, box_h, radius=16), (bx - 6, by - 6))
            icon = _cat_icon(CAT_ICONS.get(cat["id"], "aether_logo"), 84)
            bg.alpha_composite(icon, (bx + 12, by + 22))
            d = ImageDraw.Draw(bg)
            title_f = _f(True, 23)
            while d.textlength(cat["title"].upper(), font=title_f) > box_w - 116 and title_f.size > 15:
                title_f = _f(True, title_f.size - 1)
            d.text((bx + 108, by + 24), cat["title"].upper(), fill=TXT, font=title_f)
            d.text((bx + 108, by + 56), f"{len(cat['commands'])} команд", fill=GOLD, font=_f(True, 18))
            sample = " · ".join(cmd[0].split()[0] for cmd in cat["commands"][:3])
            if len(sample) > 24:
                sample = sample[:23] + "…"
            d.text((bx + 108, by + 82), sample, fill=MUTED, font=_f(False, 15))

        # Навигационная полоса внизу
        bg.alpha_composite(_panel_shadowed(872, 62, radius=16, border=(212, 175, 55, 230)), (18, H - 84))
        icon = _cat_icon("navigation", 46)
        bg.alpha_composite(icon, (32, H - 76))
        d = ImageDraw.Draw(bg)
        d.text((92, H - 78), "НАВИГАЦИЯ · МЕНЮ НИЖЕ", fill=TXT, font=_f(True, 22))
        d.text((92, H - 48), "выберите раздел — карточка обновится", fill=MUTED, font=_f(False, 16))
        d.text((W - 190, H - 66), "HELP v5.1", fill=GOLD, font=_f(True, 16))

    else:
        cat = next((c for c in CATEGORIES if c["id"] == category_id), None)
        cmds = cat["commands"] if cat else []
        icon_key = CAT_ICONS.get(category_id, "aether_logo")
        _header(bg, f"КАТЕГОРИЯ · {cat['title'].upper() if cat else 'СПРАВКА'}",
                f"{len(cmds)} КОМАНД  ·  [РОЛЬ] — КТО МОЖЕТ ИСПОЛЬЗОВАТЬ", icon_key)

        box_w, box_h, gap_y = 872, 80, 11
        start_x, start_y = 24, 112
        for idx, (cmd_str, desc, perm) in enumerate(cmds):
            by = start_y + idx * (box_h + gap_y)
            bg.alpha_composite(_panel_shadowed(box_w, box_h, radius=14), (start_x - 6, by - 6))
            d = ImageDraw.Draw(bg)
            # золотой ромб-буллет
            cx, cy = start_x + 30, by + box_h // 2
            s = 8
            d.polygon([(cx, cy - s), (cx + s, cy), (cx, cy + s), (cx - s, cy)], fill=GOLD)
            d.text((start_x + 54, by + 10), cmd_str, fill=TXT, font=_f(True, 28))
            d.text((start_x + 54, by + 47), desc, fill=MUTED, font=_f(False, 21))
            perm_txt = f" {perm} "
            pf = _f(True, 17)
            pw = d.textlength(perm_txt, font=pf) + 16
            ph = 30
            bg.alpha_composite(_panel(int(pw), ph, radius=10, fill=(24, 29, 60, 215), border=(212, 175, 55, 190), bw=2),
                               (start_x + box_w - int(pw) - 16, by + (box_h - ph) // 2))
            d = ImageDraw.Draw(bg)
            d.text((start_x + box_w - 16 - pw + 8, by + (box_h - ph) // 2 + 6), perm_txt, fill=GOLD, font=pf)

        # Alt navigasyon şeridi
        bg.alpha_composite(_panel(872, 54, radius=14, border=(212, 175, 55, 210)), (24, H - 76))
        icon = _cat_icon("navigation", 40)
        bg.alpha_composite(icon, (36, H - 69))
        d = ImageDraw.Draw(bg)
        d.text((90, H - 62), "МЕНЮ НИЖЕ · выберите другую категорию", fill=TXT, font=_f(True, 19))
        d.text((W - 170, H - 60), "HELP v5.1", fill=GOLD, font=_f(True, 15))

    # Золотые уголки
    d = ImageDraw.Draw(bg)
    L, T = 26, 3
    for (x, y, dx, dy) in ((8, 8, 1, 1), (W - 8, 8, -1, 1), (8, H - 8, 1, -1), (W - 8, H - 8, -1, -1)):
        d.line([(x, y), (x + dx * L, y)], fill=GOLD, width=T)
        d.line([(x, y), (x, y + dy * L)], fill=GOLD, width=T)
    return bg


def generate_help_card_bytes(category_id: str = None) -> io.BytesIO:
    """Discord önizlemesi ~400px; net görünmesi için 2x render + hafif keskinleştirme"""
    from PIL import ImageFilter
    card = generate_help_card(category_id).convert('RGB')
    w, h = card.size
    card = card.resize((w * 2, h * 2), Image.Resampling.LANCZOS)
    card = card.filter(ImageFilter.UnsharpMask(radius=2, percent=135, threshold=2))
    buf = io.BytesIO()
    card.save(buf, format='PNG', optimize=True)
    buf.seek(0)
    return buf


CUSTOM_EMOJIS: dict = {}


def load_custom_help_emojis(bot):
    """Sunucudaki ozel emojileri tara; isimleri aether_<ikon> olanlari help menusune bagla.

    Ikony yuklemek icin: !upload-emoji (assets/icons altindaki PNG'leri sunucuya ozel emoji olarak ekler).
    """
    CUSTOM_EMOJIS.clear()
    for g in bot.guilds:
        for e in g.emojis:
            if e.name.startswith('aether_') and e.available:
                key = e.name[len('aether_'):]
                CUSTOM_EMOJIS.setdefault(key, str(e))


class HelpSelect(discord.ui.Select):
    def __init__(self, current_cat=None):
        options = [
            discord.SelectOption(
                label="Главное меню",
                value="overview",
                description="Общий список всех 11 категорий команд",
                emoji="🔘",
                default=(current_cat == "overview" or current_cat is None)
            )
        ]
        for c in CATEGORIES:
            options.append(
                discord.SelectOption(
                    label=c["title"],
                    value=c["id"],
                    description=f"{len(c['commands'])} команд в категории",
                    emoji=CUSTOM_EMOJIS.get(c["id"]) or CAT_EMOJIS_FALLBACK.get(c["id"], "▪"),
                    default=(c["id"] == current_cat)
                )
            )
        super().__init__(
            placeholder="📂 Выберите категорию для просмотра команд...",
            options=options,
            custom_id="help_select_v5_lux"
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cat_id = self.values[0]
        if cat_id == "overview":
            cat_id = None
        img_buf = await interaction.client.loop.run_in_executor(
            None, generate_help_card_bytes, cat_id
        )
        file = discord.File(img_buf, filename="help_card.png")
        view = HelpView(current_cat=cat_id)
        await interaction.edit_original_response(embed=None, attachments=[file], view=view)


class HelpView(discord.ui.View):
    def __init__(self, current_cat=None):
        super().__init__(timeout=300)
        self.add_item(HelpSelect(current_cat=current_cat))


class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="help", aliases=["h", "команды", "menu", "yardim"])
    async def help_prefix(self, ctx, category: str = None):
        try:
            await ctx.message.delete()
        except Exception:
            pass

        cat_id = None
        if category:
            cat_l = category.lower()
            cat = next((c for c in CATEGORIES if c["id"] == cat_l or c["title"].lower() == cat_l), None)
            if cat:
                cat_id = cat["id"]

        img_buf = await self.bot.loop.run_in_executor(
            None, generate_help_card_bytes, cat_id
        )
        file = discord.File(img_buf, filename="help_card.png")
        view = HelpView(current_cat=cat_id)
        await ctx.send(file=file, view=view)

    @app_commands.command(name="help", description="Профессиональное руководство и справка по всем командам")
    async def help_slash(self, interaction: discord.Interaction, category: str = None):
        await interaction.response.defer(ephemeral=True)
        cat_id = None
        if category:
            cat_l = category.lower()
            cat = next((c for c in CATEGORIES if c["id"] == cat_l or c["title"].lower() == cat_l), None)
            if cat:
                cat_id = cat["id"]

        img_buf = await interaction.client.loop.run_in_executor(
            None, generate_help_card_bytes, cat_id
        )
        file = discord.File(img_buf, filename="help_card.png")
        view = HelpView(current_cat=cat_id)
        await interaction.followup.send(file=file, view=view, ephemeral=True)


class HelpEmojiUpload(commands.Cog):
    """Ozel help simgelerini sunucuya ozel emoji olarak yukleme yardimcisi (tek seferlik)."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='upload-emoji')
    @commands.has_permissions(administrator=True)
    async def upload_emoji(self, ctx, mode: str = None):
        """assets/icons altindaki simgeleri sunucuya 'aether_<isim>' ozel emojisi olarak yukler.

        'force' verilirse mevcut aether_* emojileri silinip yenileri yuklenir (ikon seti degistiginde).
        """
        import os as _os
        icons_dir = _os.path.join(ROOT, 'assets', 'icons')
        done, skipped, failed = [], [], []
        # force: eski aether_* emojilerini sil
        if mode and mode.lower() in ('force', 'yenile', 'refresh'):
            for e in list(ctx.guild.emojis):
                if e.name.startswith('aether_'):
                    try:
                        await e.delete()
                        await ctx.send(f'🗑 Старый эмодзи удалён: `{e.name}`')
                    except Exception:
                        pass
        existing = {e.name for e in ctx.guild.emojis}
        for fn in sorted(_os.listdir(icons_dir)):
            if not fn.endswith('_256.png'):
                continue
            name = 'aether_' + fn[:-len('_256.png')]
            if name in existing:
                skipped.append(fn)
                continue
            try:
                with open(_os.path.join(icons_dir, fn), 'rb') as fp:
                    data = fp.read()
                await ctx.guild.create_custom_emoji(name=name, image=data)
                done.append(fn)
            except Exception as exc:
                failed.append(f'{fn}: {exc}')
        # Afk ikonu (kök assets altinda)
        afk_p = _os.path.join(ROOT, 'assets', 'afk_icon.png')
        if _os.path.exists(afk_p) and 'aether_afk_icon' not in existing:
            try:
                with open(afk_p, 'rb') as fp:
                    await ctx.guild.create_custom_emoji(name='aether_afk_icon', image=fp.read())
                done.append('afk_icon.png')
            except Exception as exc:
                failed.append(f'afk_icon.png: {exc}')
        # Marka logosu (kart basligi icin)
        logo_p = _os.path.join(icons_dir, 'aether_logo.png')
        if _os.path.exists(logo_p) and 'aether_aether_logo' not in existing:
            try:
                im = Image.open(logo_p).convert('RGBA').resize((256, 256), Image.Resampling.LANCZOS)
                buf = io.BytesIO()
                im.save(buf, format='PNG')
                await ctx.guild.create_custom_emoji(name='aether_aether_logo', image=buf.getvalue())
                done.append('aether_logo.png')
            except Exception as exc:
                failed.append(f'aether_logo.png: {exc}')
        load_custom_help_emojis(self.bot)
        msg = [f'Загружено: **{len(done)}**, пропущено (уже есть): **{len(skipped)}**']
        if failed:
            msg.append('Ошибки: ' + '; '.join(failed[:5]))
        await ctx.send('\n'.join(msg))

    @commands.Cog.listener()
    async def on_ready(self):
        load_custom_help_emojis(self.bot)


async def setup(bot):
    await bot.add_cog(Help(bot))
    await bot.add_cog(HelpEmojiUpload(bot))
