"""
Help Cog — Professional Dashboard/ID-Card Style via Pillow
Белый фон, тонкие чёрные линии, красные line-art иконки.
Все страницы (Главное меню + 11 категорий) рендерятся как карточки через Pillow.
Поддерживает Discord Select Menu для удобного переключения категорий.
"""

import os
import io
import math
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.join(os.path.dirname(__file__), '..')
FONTS = os.path.join(ROOT, 'assets', 'fonts')
BG_PATH = os.path.join(ROOT, 'assets', 'profile_bg_pro.jpg')
FONT_B = os.path.join(FONTS, 'Bold.ttf')
FONT_R = os.path.join(FONTS, 'Regular.ttf')

WHITE = (255, 255, 255)
BLACK = (20, 20, 25)
RED = (220, 38, 38)
MUTED = (110, 115, 125)
SS = 4


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


# ═══════════════════════════════════════════════════════════════════════
# Custom line-art vector icons — drawn in red, crisp thin strokes
# ═══════════════════════════════════════════════════════════════════════

def _icon_overview(d, cx, cy, s, w):
    gap = s * 0.1
    sz = s * 0.38
    for i in (-1, 1):
        for j in (-1, 1):
            x = cx + i * (sz/2 + gap/2)
            y = cy + j * (sz/2 + gap/2)
            d.rectangle((x - sz/2, y - sz/2, x + sz/2, y + sz/2), outline=RED, width=w)


def _icon_moderation(d, cx, cy, s, w):
    pts = [
        (cx - s*0.4, cy - s*0.4),
        (cx + s*0.4, cy - s*0.4),
        (cx + s*0.4, cy + s*0.05),
        (cx, cy + s*0.45),
        (cx - s*0.4, cy + s*0.05)
    ]
    d.line(pts + [pts[0]], fill=RED, width=w, joint='curve')
    chk = [(cx - s*0.18, cy + s*0.02), (cx - s*0.04, cy + s*0.16), (cx + s*0.2, cy - s*0.12)]
    d.line(chk, fill=RED, width=w, joint='curve')


def _icon_warnings(d, cx, cy, s, w):
    pts = [
        (cx, cy - s*0.42),
        (cx + s*0.42, cy + s*0.35),
        (cx - s*0.42, cy + s*0.35),
        (cx, cy - s*0.42)
    ]
    d.line(pts, fill=RED, width=w, joint='curve')
    d.line([(cx, cy - s*0.15), (cx, cy + s*0.1)], fill=RED, width=w)
    r = w * 0.8
    d.ellipse((cx - r, cy + s*0.2 - r, cx + r, cy + s*0.2 + r), fill=RED)


def _icon_tickets(d, cx, cy, s, w):
    w_t, h_t = s*0.44, s*0.30
    x0, y0 = cx - w_t, cy - h_t
    x1, y1 = cx + w_t, cy + h_t
    d.rounded_rectangle((x0, y0, x1, y1), radius=h_t*0.25, outline=RED, width=w)
    r = s*0.1
    d.arc((x0 - r, cy - r, x0 + r, cy + r), -90, 90, fill=WHITE, width=w*2)
    d.arc((x0 - r, cy - r, x0 + r, cy + r), -90, 90, fill=RED, width=w)
    d.arc((x1 - r, cy - r, x1 + r, cy + r), 90, 270, fill=WHITE, width=w*2)
    d.arc((x1 - r, cy - r, x1 + r, cy + r), 90, 270, fill=RED, width=w)


def _icon_economy(d, cx, cy, s, w):
    bw, bh = s * 0.64, s * 0.46
    x0, y0 = cx - bw / 2, cy - bh / 2
    x1, y1 = cx + bw / 2, cy + bh / 2
    d.rounded_rectangle((x0, y0, x1, y1), radius=bh * 0.22, outline=RED, width=w)
    d.line([(x0, y0 + bh * 0.32), (x1, y0 + bh * 0.32)], fill=RED, width=max(1, int(w * 0.7)))
    r = s * 0.085
    ccx = x1 - r * 1.5
    ccy = y0 + bh * 0.66
    d.ellipse((ccx - r, ccy - r, ccx + r, ccy + r), outline=RED, width=max(1, int(w * 0.8)))


def _icon_music(d, cx, cy, s, w):
    r = s * 0.1
    x1, y1 = cx - s * 0.22, cy + s * 0.22
    x2, y2 = cx + s * 0.18, cy + s * 0.14
    d.ellipse((x1 - r*1.2, y1 - r, x1 + r*1.2, y1 + r), outline=RED, width=w)
    d.ellipse((x2 - r*1.2, y2 - r, x2 + r*1.2, y2 + r), outline=RED, width=w)
    d.line([(x1 + r*1.2, y1), (x1 + r*1.2, y1 - s*0.45)], fill=RED, width=w)
    d.line([(x2 + r*1.2, y2), (x2 + r*1.2, y2 - s*0.45)], fill=RED, width=w)
    d.line([(x1 + r*1.2, y1 - s*0.45), (x2 + r*1.2, y2 - s*0.45)], fill=RED, width=int(w*1.5))


def _icon_levels(d, cx, cy, s, w):
    bar_w = s * 0.14
    bars = [
        (cx - s*0.28, cy + s*0.35, cy + s*0.1),
        (cx - s*0.05, cy + s*0.35, cy - s*0.1),
        (cx + s*0.18, cy + s*0.35, cy - s*0.3)
    ]
    for bx, ybot, ytop in bars:
        d.rounded_rectangle((bx - bar_w/2, ytop, bx + bar_w/2, ybot), radius=bar_w*0.3, outline=RED, width=w)
    pts = [(cx + s*0.05, cy - s*0.32), (cx + s*0.32, cy - s*0.32), (cx + s*0.32, cy - s*0.05)]
    d.line(pts, fill=RED, width=w, joint='curve')
    d.line([(cx - s*0.1, cy - s*0.12), (cx + s*0.32, cy - s*0.32)], fill=RED, width=w)


def _icon_utility(d, cx, cy, s, w):
    r_out = s * 0.4
    r_in = s * 0.28
    for idx in range(8):
        a1 = math.radians(idx * 45 - 12)
        a2 = math.radians(idx * 45 + 12)
        p1 = (cx + r_in * math.cos(a1), cy + r_in * math.sin(a1))
        p2 = (cx + r_out * math.cos(a1), cy + r_out * math.sin(a1))
        p3 = (cx + r_out * math.cos(a2), cy + r_out * math.sin(a2))
        p4 = (cx + r_in * math.cos(a2), cy + r_in * math.sin(a2))
        d.line([p1, p2, p3, p4], fill=RED, width=w, joint='curve')
    r_mid = s * 0.28
    d.ellipse((cx - r_mid, cy - r_mid, cx + r_mid, cy + r_mid), outline=RED, width=w)
    r_center = s * 0.12
    d.ellipse((cx - r_center, cy - r_center, cx + r_center, cy + r_center), outline=RED, width=w)


def _icon_voice(d, cx, cy, s, w):
    bx = cx - s * 0.20
    hw, hh = s * 0.14, s * 0.20
    d.rounded_rectangle((bx - hw, cy - hh, bx + hw * 0.3, cy + hh), radius=hw * 0.5, outline=RED, width=w)
    tri = [(bx + hw * 0.15, cy - hh * 0.9), (bx + s * 0.20, cy - s * 0.28), (bx + s * 0.20, cy + s * 0.28), (bx + hw * 0.15, cy + hh * 0.9)]
    d.line(tri, fill=RED, width=w, joint='curve')
    for r in (s * 0.11, s * 0.20, s * 0.29):
        bbox = (cx + s * 0.05 - r, cy - r, cx + s * 0.05 + r, cy + r)
        d.arc(bbox, -42, 42, fill=RED, width=w)


def _icon_fun(d, cx, cy, s, w):
    cw, ch = s * 0.44, s * 0.28
    d.rounded_rectangle((cx - cw, cy - ch, cx + cw, cy + ch), radius=ch*0.4, outline=RED, width=w)
    dx, dy = cx - cw*0.45, cy
    l_d = s * 0.09
    d.line([(dx - l_d, dy), (dx + l_d, dy)], fill=RED, width=w)
    d.line([(dx, dy - l_d), (dx, dy + l_d)], fill=RED, width=w)
    bx, by = cx + cw*0.45, cy
    r_b = s * 0.05
    d.ellipse((bx - l_d - r_b, by - r_b, bx - l_d + r_b, by + r_b), fill=RED)
    d.ellipse((bx + l_d - r_b, by - r_b, bx + l_d + r_b, by + r_b), fill=RED)


def _icon_giveaway(d, cx, cy, s, w):
    bw, bh = s * 0.36, s * 0.36
    d.rounded_rectangle((cx - bw, cy - bh*0.7, cx + bw, cy + bh), radius=s*0.06, outline=RED, width=w)
    d.rounded_rectangle((cx - bw*1.1, cy - bh*0.7, cx + bw*1.1, cy - bh*0.35), radius=s*0.05, outline=RED, width=w)
    d.line([(cx, cy - bh*0.7), (cx, cy + bh)], fill=RED, width=int(w*1.2))
    r_bow = s * 0.12
    d.ellipse((cx - r_bow*1.4, cy - bh*0.9 - r_bow*0.5, cx, cy - bh*0.6), outline=RED, width=w)
    d.ellipse((cx, cy - bh*0.9 - r_bow*0.5, cx + r_bow*1.4, cy - bh*0.6), outline=RED, width=w)


def _icon_profile(d, cx, cy, s, w):
    cw, ch = s * 0.40, s * 0.28
    d.rounded_rectangle((cx - cw, cy - ch, cx + cw, cy + ch), radius=ch*0.3, outline=RED, width=w)
    r_h = s * 0.08
    d.ellipse((cx - r_h, cy - s*0.12 - r_h, cx + r_h, cy - s*0.12 + r_h), outline=RED, width=w)
    d.arc((cx - s*0.16, cy - s*0.04, cx + s*0.16, cy + s*0.18), 180, 0, fill=RED, width=w)


def _icon_cmd_bullet(d, cx, cy, s, w):
    r = s * 0.40
    pts = [(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy), (cx, cy - r)]
    d.line(pts, fill=RED, width=w)
    c_r = s * 0.14
    chev = [(cx - c_r*0.6, cy - c_r), (cx + c_r*0.6, cy), (cx - c_r*0.6, cy + c_r)]
    d.line(chev, fill=RED, width=w, joint='curve')


ICON_FUNCS = {
    'overview': _icon_overview,
    'moderation': _icon_moderation,
    'warnings': _icon_warnings,
    'tickets': _icon_tickets,
    'economy': _icon_economy,
    'music': _icon_music,
    'levels': _icon_levels,
    'utility': _icon_utility,
    'voice': _icon_voice,
    'fun': _icon_fun,
    'giveaway': _icon_giveaway,
    'profile': _icon_profile,
    'cmd_bullet': _icon_cmd_bullet
}


def _icon_badge(diameter, glyph_key, ring_color=BLACK, ring_w=None):
    ring_w = ring_w if ring_w is not None else max(2, diameter // 22)

    def draw(d, scale):
        size = diameter * scale
        rw = ring_w * scale
        r = size * 0.22
        d.rounded_rectangle((rw / 2, rw / 2, size - rw / 2 - 1, size - rw / 2 - 1),
                             radius=r, fill=WHITE, outline=ring_color, width=rw)
        fn = ICON_FUNCS.get(glyph_key, _icon_overview)
        fn(d, size / 2, size / 2, size * 0.60, max(2, int(size * 0.032)))

    return _ss_render(diameter, diameter, draw)


def _corner_bracket(size, thickness, length_ratio=0.35, color=RED):
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

CAT_EMOJIS = {
    "moderation": "🛡️",
    "warnings": "⚠️",
    "tickets": "🎫",
    "economy": "💳",
    "music": "🎵",
    "levels": "⭐",
    "utility": "⚙️",
    "voice": "🎙️",
    "fun": "🎲",
    "giveaway": "🎁",
    "profile": "👤",
}


def generate_help_card(category_id: str = None) -> Image.Image:
    """Генерация карточки помощи 1000x640 в профессиональном стиле профиля"""
    W, H = 1000, 640
    if os.path.exists(BG_PATH):
        bg = Image.open(BG_PATH).convert('RGBA')
        if bg.size != (W, H):
            bg = bg.resize((W, H), Image.Resampling.LANCZOS)
    else:
        bg = Image.new('RGBA', (W, H), WHITE)

    d = ImageDraw.Draw(bg)

    # Top Header Panel
    header_box = _rounded_panel(952, 58, radius=12, fill=WHITE, outline=BLACK, ow=2)
    bg.alpha_composite(header_box, (24, 18))

    if category_id is None or category_id == "overview":
        title_text = "AETHER BOT • СПРАВКА И КОМАНДЫ"
        badge_icon = "overview"
    else:
        cat = next((c for c in CATEGORIES if c["id"] == category_id), None)
        title_text = f"КАТЕГОРИЯ: {cat['title'].upper()}" if cat else "СПРАВКА"
        badge_icon = category_id

    badge = _icon_badge(42, badge_icon, ring_color=BLACK, ring_w=2)
    bg.alpha_composite(badge, (34, 26))

    d.text((88, 27), title_text, fill=BLACK, font=_f(True, 22))
    d.text((88, 52), f"ПРОФЕССИОНАЛЬНАЯ СИСТЕМА • ВСЕГО КОМАНД: {TOTAL_CMDS} • ПРЕФИКС: !", fill=MUTED, font=_f(False, 12))

    # Right header pill
    pill = _rounded_panel(140, 32, radius=8, fill=WHITE, outline=RED, ow=2)
    bg.alpha_composite(pill, (822, 31))
    d.text((840, 38), "HELP v4.0 PRO", fill=RED, font=_f(True, 12))

    if category_id is None or category_id == "overview":
        # 3x4 Grid of Categories + Info navigation box
        cols = 3
        box_w, box_h = 306, 114
        gap_x, gap_y = 17, 15
        start_x, start_y = 24, 92

        for idx, cat in enumerate(CATEGORIES):
            c = idx % cols
            r = idx // cols
            bx = start_x + c * (box_w + gap_x)
            by = start_y + r * (box_h + gap_y)

            box = _rounded_panel(box_w, box_h, radius=14, fill=WHITE, outline=BLACK, ow=2)
            bg.alpha_composite(box, (bx, by))

            cat_badge = _icon_badge(52, cat["id"], ring_color=BLACK, ring_w=2)
            bg.alpha_composite(cat_badge, (bx + 16, by + 31))

            d.text((bx + 80, by + 20), cat["title"].upper(), fill=BLACK, font=_f(True, 17))
            d.text((bx + 80, by + 46), f"{len(cat['commands'])} КОМАНД", fill=RED, font=_f(True, 13))

            cmds_sample = " • ".join([cmd[0].split()[0] for cmd in cat["commands"][:3]])
            if len(cmds_sample) > 26:
                cmds_sample = cmds_sample[:25] + "…"
            d.text((bx + 80, by + 74), cmds_sample, fill=MUTED, font=_f(False, 11))

        # 12th Box - Interactive Menu nav info
        bx = start_x + 2 * (box_w + gap_x)
        by = start_y + 3 * (box_h + gap_y)
        box = _rounded_panel(box_w, box_h, radius=14, fill=WHITE, outline=RED, ow=2)
        bg.alpha_composite(box, (bx, by))

        nav_badge = _icon_badge(52, "overview", ring_color=RED, ring_w=2)
        bg.alpha_composite(nav_badge, (bx + 16, by + 31))

        d.text((bx + 80, by + 20), "НАВИГАЦИЯ МЕНЮ", fill=BLACK, font=_f(True, 17))
        d.text((bx + 80, by + 46), "ВЫБЕРИТЕ РАЗДЕЛ", fill=RED, font=_f(True, 13))
        d.text((bx + 80, by + 74), "через меню ниже", fill=MUTED, font=_f(False, 12))

    else:
        # Category commands view (2 columns)
        cat = next((c for c in CATEGORIES if c["id"] == category_id), None)
        cmds = cat["commands"] if cat else []
        cols = 2
        box_w = 467
        n_rows = (len(cmds) + 1) // 2
        box_h = min(74, 480 // max(1, n_rows) - 10)
        gap_x, gap_y = 18, 10
        start_x, start_y = 24, 95

        for idx, (cmd_str, desc, perm) in enumerate(cmds):
            c = idx % cols
            r = idx // cols
            bx = start_x + c * (box_w + gap_x)
            by = start_y + r * (box_h + gap_y)

            box = _rounded_panel(box_w, box_h, radius=12, fill=WHITE, outline=BLACK, ow=2)
            bg.alpha_composite(box, (bx, by))

            cmd_badge = _icon_badge(40, "cmd_bullet", ring_color=BLACK, ring_w=2)
            bg.alpha_composite(cmd_badge, (bx + 14, by + (box_h - 40)//2))

            cmd_name = cmd_str
            if len(cmd_name) > 34:
                cmd_name = cmd_name[:33] + "…"

            d.text((bx + 66, by + box_h // 2 - 19), cmd_name, fill=BLACK, font=_f(True, 15))
            d.text((bx + 66, by + box_h // 2 + 3), desc, fill=MUTED, font=_f(False, 12))

            perm_w = len(f"[{perm}]") * 7
            d.text((bx + box_w - 18 - perm_w, by + box_h // 2 - 19), f"[{perm}]", fill=RED, font=_f(True, 12))

    # 4 Corner brackets (red line-art accents)
    br = _corner_bracket(38, 4, color=RED)
    bg.alpha_composite(br, (6, 6))
    bg.alpha_composite(br.rotate(270), (956, 6))
    bg.alpha_composite(br.rotate(90), (6, 596))
    bg.alpha_composite(br.rotate(180), (956, 596))

    return bg


def generate_help_card_bytes(category_id: str = None) -> io.BytesIO:
    card = generate_help_card(category_id)
    buf = io.BytesIO()
    card.save(buf, format='PNG')
    buf.seek(0)
    return buf


def build_help_embed(category_id: str = None) -> discord.Embed:
    embed = discord.Embed(
        color=discord.Color.from_rgb(220, 38, 38),
        timestamp=datetime.now()
    )
    filename = "help_card.png"
    embed.set_image(url=f"attachment://{filename}")
    if category_id is None or category_id == "overview":
        embed.set_footer(text="Aether Help System • Главное меню • Выберите раздел в меню ниже")
    else:
        cat = next((c for c in CATEGORIES if c["id"] == category_id), None)
        title = cat["title"] if cat else "Справка"
        embed.set_footer(text=f"Aether Help System • Раздел: {title} • Выберите раздел в меню ниже")
    return embed


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
                    emoji=CAT_EMOJIS.get(c["id"], "▪️"),
                    default=(c["id"] == current_cat)
                )
            )
        super().__init__(
            placeholder="Выберите категорию команд...",
            options=options,
            custom_id="help_select_v4_pro"
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
        embed = build_help_embed(cat_id)
        view = HelpView(current_cat=cat_id)
        await interaction.edit_original_response(embed=embed, attachments=[file], view=view)


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
        embed = build_help_embed(cat_id)
        view = HelpView(current_cat=cat_id)
        await ctx.send(embed=embed, file=file, view=view)

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
        embed = build_help_embed(cat_id)
        view = HelpView(current_cat=cat_id)
        await interaction.followup.send(embed=embed, file=file, view=view, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Help(bot))
