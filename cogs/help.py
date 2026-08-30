"""
Help Cog — Luxury Dark-Gold Dashboard (Pillow)
Тёмно-синий фон с золотыми звёздами, золотые панели, фирменные иконки категорий.
"""

from logger import get_logger

_log = get_logger("help")

# Владелец 2026-08-25: справка ВРЕМЕННО выключена (!help + алиасы и /help).
# Команды отвечают «выключена владельцем». Вернуть: HELP_ENABLED = True.
HELP_ENABLED = False
def _help_disabled_embed(guild=None):
    from cogs.embed_utils import hakumo_embed
    return hakumo_embed(
        'system', 'Справка выключена',
        'Команда временно выключена владельцем сервера.',
        guild=guild)

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

# Текстовый формат справки: без картинок, с фильтром по правам.
# Команды, к которым у участника нет доступа (в т.ч. классические
# разрешения на действия), скрываются из справки.
from services.permission_acl import COMMAND_CATEGORIES, has_access as _acl_has_access

_HELP_TITLE = 'Команды бота'
_HELP_COLOR = 0x4F46E5

# Фирменные маркеры разделов справки: эмодзи в select-меню и в заголовках полей.
_HELP_EMOJI = {
    'Модерация': '🛡️',
    'Тикеты': '🎫',
    'Логи': '🧾',
    'AI-система': '🤖',
    'Музыка': '🎵',
    'Голосовые': '🎧',
    'Экономика': '💰',
    'Уровни и карма': '📈',
    'Игры и развлечения': '🎲',
    'Профили и соц.': '👤',
    'Инфо и поиск': 'ℹ️',
    'Автоматизация': '⚙️',
    'События и команда': '📅',
    'Приветствие и вход': '👋',
    'Система': '🖥️',
    'Прочее': '🧩',
}
_HELP_BLURB = {
    'Модерация': 'варны, муты, баны, доказательства и дежурства',
    'Тикеты': 'приём обращений и сопровождение до закрытия',
    'Логи': 'журналы событий, аудит и отчёты команды',
    'AI-система': 'автопомощник в тикетах и авто-модерация',
    'Музыка': 'плеер, очередь и голосовые вечеринки',
    'Голосовые': 'войс-команды, личные комнаты и статистика голоса',
    'Экономика': 'баланс, магазин и переводы между участниками',
    'Уровни и карма': 'опыт, ранги и репутация на сервере',
    'Игры и развлечения': 'дуэли, квизы, аниме и мини-игры',
    'Профили и соц.': 'карточки профилей, дни рождения и карма-борды',
    'Инфо и поиск': 'информация о сервере, участниках и поиск',
    'Автоматизация': 'триггеры, расписания и свои команды',
    'События и команда': 'розыгрыши, собрания и события сервера',
    'Приветствие и вход': 'карточки входа, инвайты и автороли',
    'Система': 'состояние бота, модули и техническая диагностика',
    'Прочее': 'полезные мелочи',
}


def _registry_extra_categories():
    """Разделы из полного каталога команд, НЕ покрытые ACL-четвёркой."""
    try:
        from services.command_registry import CATEGORIES, catalog_by_category
        acl_labels = set(COMMAND_CATEGORIES)          # Модерация/Тикеты/Логи/AI-система
        overlapped_ids = {'mod', 'tickets', 'logs', 'ai'}  # дубли ACL-разделов
        out = {}
        for cid, meta in CATEGORIES.items():
            if cid in overlapped_ids or meta['label'] in acl_labels:
                continue
            names = catalog_by_category().get(meta['label'])
            if names:
                out[meta['label']] = names
        return out
    except Exception as _ex:
        _log.debug('_registry_extra_categories(): %s', _ex)
        return {}


def _all_category_labels():
    """Порядок разделов справки: ACL-ядро + дополнительные из каталога."""
    return list(COMMAND_CATEGORIES) + list(_registry_extra_categories())


def _plural_cmds(n):
    m10, m100 = n % 10, n % 100
    if m10 == 1 and m100 != 11:
        return 'команда'
    if 2 <= m10 <= 4 and not (12 <= m100 <= 14):
        return 'команды'
    return 'команд'


def _visible_categories(guild_id, member):
    """Категории команд, которые видит участник.

    Сначала ACL-ядро (Модерация/Тикеты/Логи/AI) с фильтром прав, затем
    дополнительные разделы из полного каталога бота (музыка, экономика
    и т.д.) — без дублей уже показанных команд.
    """
    groups = {}
    covered = set()
    for cat, cmds in COMMAND_CATEGORIES.items():
        visible = []
        for cmd in cmds:
            covered.add(cmd)
            try:
                if _acl_has_access(guild_id, cmd, member):
                    visible.append(cmd)
            except Exception:
                visible.append(cmd)
        if visible:
            groups[cat] = visible
    for label, names in _registry_extra_categories().items():
        visible = []
        for cmd in names:
            if cmd in covered:
                continue
            try:
                if member is None or _acl_has_access(guild_id, cmd, member):
                    visible.append(cmd)
            except Exception:
                visible.append(cmd)
        if visible:
            groups[label] = visible
    return groups


def _help_chunks(items, cap=900):
    """Разбить команды на фрагменты по длине поля эмбеда."""
    out, cur, ln = [], [], 0
    for it in items:
        token = '`' + it + '`'
        if cur and ln + len(token) + 2 > cap:
            out.append(cur)
            cur, ln = [], 0
        cur.append(token)
        ln += len(token) + 2
    if cur:
        out.append(cur)
    return out


def build_help_embed(category_id=None, member=None, guild_id=0):
    """Текстовый эмбед справки (без картинок).

    Обзор: по разделу на категорию с фирменным маркером и счётчиком
    (команды рубятся на «продолжения», если не влезают в поле эмбеда).
    Раздел: отдельная страница с описанием и всеми его командами.
    Команды, к которым у участника нет доступа, скрыты — как и раньше.
    """
    groups = _visible_categories(guild_id, member)
    if category_id and category_id != 'overview':
        groups = {category_id: groups.get(category_id, [])}
    total = sum(len(v) for v in groups.values())

    if category_id and category_id != 'overview':
        cat = category_id
        emo = _HELP_EMOJI.get(cat, '▫️')
        cmds = groups.get(cat, []) or []
        e = discord.Embed(title=f'{emo} {cat}', color=_HELP_COLOR)
        blurb = _HELP_BLURB.get(cat, '')
        e.description = ((blurb + ' — ') if blurb else '') + \
            f'**{len(cmds)}** {_plural_cmds(len(cmds))} в разделе.'
        if not cmds:
            e.add_field(name=f'{emo} {cat}',
                        value='*Нет команд, доступных вашей роли, в этом разделе.*',
                        inline=False)
        for i, chunk in enumerate(_help_chunks(cmds)):
            e.add_field(name=(f'{emo} {cat}' if i == 0 else f'{cat} · продолжение'),
                        value=', '.join(chunk), inline=False)
        e.set_footer(text='Hakumo · назад ко всем разделам — «Главное меню» в списке ниже')
        return e

    e = discord.Embed(title='🧭 Справка Hakumo — команды', color=_HELP_COLOR)
    e.description = (
        'Пульт бота: выберите раздел в меню под сообщением — '
        'покажем команды именно этого раздела.\n'
        f'Сейчас вам доступно **{total}** {_plural_cmds(total)}; '
            'то, к чему нет доступа, мы не показываем.')
    for cat, cmds in groups.items():
        emo = _HELP_EMOJI.get(cat, '▫️')
        cap = f'{emo} {cat} · {len(cmds)} {_plural_cmds(len(cmds))}'
        if not cmds:
            e.add_field(name=cap, value='*Нет доступных команд*', inline=False)
            continue
        blurb = _HELP_BLURB.get(cat)
        for i, chunk in enumerate(_help_chunks(cmds)):
            name = cap if i == 0 else cap + ' · продолжение'
            val = ', '.join(chunk)
            if i == 0 and blurb:
                val = f'*{blurb}*\n' + val
            e.add_field(name=name, value=val, inline=False)
    e.set_footer(text='Hakumo · /help <раздел> — сразу открыть нужный, напр. /help Тикеты')
    return e

# Палитра — тёмный люкс
BG_DEEP = (13, 16, 38)
PANEL = (24, 29, 60, 215)
PANEL_BR = (212, 175, 55, 150)
GOLD = (212, 175, 55)
GOLD_SOFT = (240, 215, 130)
TXT = (235, 238, 250)
MUTED = (148, 156, 190)
SS = 2

# Кэш шрифтов — не открывает файл заново для каждого текста (рендер заметно быстрее)
_FONT_CACHE = {}


def _f(bold=False, sz=20):
    key = (bold, sz)
    f = _FONT_CACHE.get(key)
    if f is None:
        try:
            f = ImageFont.truetype(FONT_B if bold else FONT_R, sz)
        except Exception:
            f = ImageFont.load_default()
        _FONT_CACHE[key] = f
    return f


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
    """Shadow-panel — придаёт глубину"""
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
        # Мягко обрезать белые полосы/остатки по краям: inset 5% + маска со скруглёнными углами
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
            ("/modpanel", "Панель модератора: варн/мут/бан/кик/клир — модалка с демкой", "Мод"),
            ("/warnings @user", "Список предупреждений участника", "Мод"),
            ("/unwarn @user №", "Снять предупреждение по номеру", "Мод"),
            ("/proofs [@user]", "Все демки сервера или конкретного юзера", "Мод"),
            ("/proofdel №", "Удалить демку по номеру", "Админ"),
            ("панель «Доказательства»", "Загрузка демки файлом прямо из панели — фото/видео смотрятся там же", "Мод"),
        ]
    },
    {
        "id": "tickets",
        "title": "Тикеты и заявки",
        "commands": [
            ("/ticket-panel", "Разместить панель обращений в канале", "Админ"),
            ("кнопки ➕/➖ в тикете", "Добавить/убрать участника — меню под карточкой нового тикета", "Мод"),
            ("/staff-panel", "Панель набора в команду сервера", "Админ"),
            ("/my-application", "Статус моей заявки в команду", "Все"),
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
            ("!nowplaying", "Что сейчас играет", "Все"),
            ("!leave", "Покинуть голосовой канал", "Все"),
        ]
    },
    {
        "id": "utility",
        "title": "Утилиты",
        "commands": [
            ("/afk [причина]", "Уйти в AFK — бот ответит за тебя на упоминания", "Все"),
            ("/afk-remove", "Вернуться из AFK", "Все"),
            ("!help", "Это меню команд", "Все"),
            ("!апелляция", "Подать апелляцию на бан (в личке боту)", "Все"),
            ("/logs-setup", "Создать/починить категорию и каналы логов", "Админ"),
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
# Без эмоджи-заглушек (пожелание владельца): если кастомных hakumo_* нет,
# пункт меню выводится просто без иконки.
CAT_EMOJIS_FALLBACK = {}


R = 2  # рендер-масштаб: Discord-превью ~400px, рендерим вдвое больше — текст родной и чёткий


def generate_help_card(category_id: str = None) -> Image.Image:
    """Логический холст ~800px; физически рисуется в R раз больше (нет апскейла — нет мыла)."""
    def sc(v):
        return int(round(v * R))

    LW = 800
    is_overview = category_id in (None, "overview")

    if is_overview:
        LH = 830
    else:
        cat = next((c for c in CATEGORIES if c["id"] == category_id), None)
        cmds = cat["commands"] if cat else []
        n = len(cmds)
        col2 = n > 6
        rows = n if not col2 else (n + 1) // 2
        LH = 112 + rows * 99 + 88

    W, H = sc(LW), sc(LH)
    bg = _load_bg(W, H).convert('RGBA')

    # ── Шапка ──
    def header(title_text, sub_text, icon_key):
        hp = _panel(sc(LW - 48), sc(88), radius=sc(16))
        bg.alpha_composite(hp, (sc(24), sc(18)))
        badge = _cat_icon(icon_key, sc(58))
        bg.alpha_composite(badge, (sc(38), sc(33)))
        pill_w, pill_h = sc(150), sc(42)
        bg.alpha_composite(_panel(pill_w, pill_h, radius=sc(12), border=(212, 175, 55, 210)),
                           (sc(LW - 24 - 166), sc(41)))
        dd = ImageDraw.Draw(bg)
        dd.text((sc(112), sc(28)), title_text, fill=GOLD_SOFT, font=_f(True, sc(31)))
        dd.text((sc(112), sc(66)), sub_text, fill=(178, 186, 212), font=_f(False, sc(17)))
        pf2 = _f(True, sc(17))
        tw = dd.textlength("✦ HELP", font=pf2)
        dd.text((sc(LW - 24 - 166) + (pill_w - tw) / 2, sc(52)), "✦ HELP", fill=GOLD, font=pf2)

    if is_overview:
        header("HAKUMO  ·  СПРАВКА",
               f"{TOTAL_CMDS} КОМАНД  ·  ПРЕФИКС: !  ·  ВЫБОР КАТЕГОРИИ В МЕНЮ", "hakumo_logo")

        # ── Сетка категорий 2×6, крупно и без мелкого текста ──
        box_w, box_h, gap_x, gap_y = (LW - 48 - 14) // 2, 96, 14, 9
        start_x, start_y = 24, 122
        for idx, cat in enumerate(CATEGORIES):
            c, r = idx % 2, idx // 2
            bx = start_x + c * (box_w + gap_x)
            by = start_y + r * (box_h + gap_y)
            bg.alpha_composite(_panel_shadowed(sc(box_w), sc(box_h), radius=sc(16)), (sc(bx) - sc(6), sc(by) - sc(6)))
            icon = _cat_icon(CAT_ICONS.get(cat["id"], "hakumo_logo"), sc(64))
            bg.alpha_composite(icon, (sc(bx + 14), sc(by + 16)))
            dd = ImageDraw.Draw(bg)
            title_f = _f(True, sc(25))
            while dd.textlength(cat["title"].upper(), font=title_f) > sc(box_w - 104) and title_f.size > sc(14):
                title_f = _f(True, title_f.size - sc(1))
            dd.text((sc(bx + 90), sc(by + 20)), cat["title"].upper(), fill=TXT, font=title_f)
            dd.text((sc(bx + 90), sc(by + 55)), f"{len(cat['commands'])} команд", fill=GOLD, font=_f(True, sc(20)))

    else:
        cat = next((c for c in CATEGORIES if c["id"] == category_id), None)
        cmds = cat["commands"] if cat else []
        icon_key = CAT_ICONS.get(category_id, "hakumo_logo")
        header(f"{cat['title'].upper() if cat else 'СПРАВКА'}",
               f"{len(cmds)} КОМАНД  ·  СПРАВКА HAKUMO", icon_key)

        col2 = len(cmds) > 6
        box_w = (LW - 48 - 14) // 2 if col2 else LW - 48
        box_h, gap_y, gap_x = 88, 11, 14
        start_x, start_y = 24, 122
        for idx, (cmd_str, desc, perm) in enumerate(cmds):
            col_i, row_i = (idx % 2, idx // 2) if col2 else (0, idx)
            bx = start_x + col_i * (box_w + gap_x)
            by = start_y + row_i * (box_h + gap_y)
            bg.alpha_composite(_panel_shadowed(sc(box_w), sc(box_h), radius=sc(14)), (sc(bx) - sc(6), sc(by) - sc(6)))
            dd = ImageDraw.Draw(bg)
            cx, cy = sc(bx + 26), sc(by + box_h // 2)
            s8 = sc(8)
            dd.polygon([(cx, cy - s8), (cx + s8, cy), (cx, cy + s8), (cx - s8, cy)], fill=GOLD)
            cf = _f(True, sc(26))
            max_cw = box_w - 64 - 110 if not col2 else box_w - 64 - 96
            while dd.textlength(cmd_str, font=cf) > sc(max_cw) and cf.size > sc(13):
                cf = _f(True, cf.size - sc(1))
            dd.text((sc(bx + 46), sc(by + 12)), cmd_str, fill=TXT, font=cf)
            dd.text((sc(bx + 46), sc(by + 50)), desc, fill=(178, 186, 212), font=_f(False, sc(19)))
            pf = _f(True, sc(15))
            perm_txt = f" {perm} "
            pw = dd.textlength(perm_txt, font=pf) + sc(16)
            ph = sc(30)
            bg.alpha_composite(_panel(int(pw), int(ph), radius=sc(10), border=(212, 175, 55, 190)),
                               (sc(bx + box_w) - int(pw) - sc(12), sc(by) + (sc(box_h) - ph) // 2))
            dd = ImageDraw.Draw(bg)
            dd.text((sc(bx + box_w) - int(pw) - sc(12) + sc(8), sc(by) + (sc(box_h) - ph) // 2 + sc(5)),
                    perm_txt, fill=GOLD, font=pf)

    # ── Нижняя полоса навигации ──
    nav_h = 62
    bg.alpha_composite(_panel_shadowed(sc(LW - 48), sc(nav_h), radius=sc(16), border=(212, 175, 55, 230)),
                       (sc(24) - sc(6), H - sc(nav_h + 24) - sc(6)))
    icon = _cat_icon("navigation", sc(44))
    bg.alpha_composite(icon, (sc(36), H - sc(nav_h + 24) + sc(9)))
    dd = ImageDraw.Draw(bg)
    dd.text((sc(94), H - sc(nav_h + 24) + sc(10)), "НАВИГАЦИЯ · МЕНЮ НИЖЕ",
            fill=TXT, font=_f(True, sc(21)))
    dd.text((sc(94), H - sc(nav_h + 24) + sc(38)), "выберите раздел — карточка обновится",
            fill=(178, 186, 212), font=_f(False, sc(16)))
    vf = _f(True, sc(16))
    vt = "HELP v5.3"
    dd.text((W - sc(24) - dd.textlength(vt, font=vf) - sc(14), H - sc(nav_h + 24) + sc(24)), vt, fill=GOLD, font=vf)

    # ── Золотые уголки ──
    L, T = sc(30), sc(3)
    for (x, y, dx, dy) in ((8 * R, 8 * R, 1, 1), (W - 8 * R, 8 * R, -1, 1),
                           (8 * R, H - 8 * R, 1, -1), (W - 8 * R, H - 8 * R, -1, -1)):
        dd.line([(x, y), (x + dx * L, y)], fill=GOLD, width=T)
        dd.line([(x, y), (x, y + dy * L)], fill=GOLD, width=T)
    return bg


# Содержимое карточек полностью статично — PNG-байты кэшируются один раз,
# переключение страниц в select-меню становится мгновенным.
_CARD_BYTES_CACHE = {}


def generate_help_card_bytes(category_id: str = None) -> io.BytesIO:
    """Карта уже рисуется в 2x (R=2) — без размытия.
    Если PNG-байты есть в кэше — повторный рендер не выполняется (мгновенное переключение страниц)."""
    key = category_id or "overview"
    data = _CARD_BYTES_CACHE.get(key)
    if data is None:
        card = generate_help_card(category_id).convert('RGB')
        buf = io.BytesIO()
        card.save(buf, format='PNG', optimize=True)
        data = buf.getvalue()
        _CARD_BYTES_CACHE[key] = data
    return io.BytesIO(data)


def prewarm_help_cards():
    """Прогрев при старте: отрисовать все страницы в фоне — выбор мгновенный."""
    for cid in [None] + [c["id"] for c in CATEGORIES]:
        try:
            generate_help_card_bytes(cid)
        except Exception as _ex:
            _log.debug("prewarm_help_cards(): подавлено: %s", _ex)


CUSTOM_EMOJIS: dict = {}


def load_custom_help_emojis(bot):
    """Сканировать кастом-эмодзи сервера; hakumo_<icon> привязать к меню help.
    Загрузка иконок: !upload-emoji (PNG из assets/icons станут эмодзи сервера)."""
    CUSTOM_EMOJIS.clear()
    for g in bot.guilds:
        for e in g.emojis:
            if e.name.startswith('hakumo_') and e.available:
                key = e.name[len('hakumo_'):]
                CUSTOM_EMOJIS.setdefault(key, str(e))


class HelpSelect(discord.ui.Select):
    def __init__(self, current_cat=None):
        options = [
            discord.SelectOption(
                label="Главное меню",
                value="overview",
                emoji="🧭",
                description="Все разделы справки одним экраном",
                default=(current_cat == "overview" or current_cat is None)
            )
        ]
        for cat in _all_category_labels():
            cmds = COMMAND_CATEGORIES.get(cat) or _registry_extra_categories().get(cat) or []
            blurb = _HELP_BLURB.get(cat, f'Команды раздела «{cat}»')
            desc = f'{len(cmds)} {_plural_cmds(len(cmds))} · {blurb}'[:100]
            options.append(
                discord.SelectOption(
                    label=cat,
                    value=cat,
                    emoji=_HELP_EMOJI.get(cat, '▫️'),
                    description=desc,
                    default=(cat == current_cat)
                )
            )
        super().__init__(
            placeholder="Выберите раздел справки…",
            options=options,
            custom_id="help_select_text_v1"
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cat_id = self.values[0]
        if cat_id == "overview":
            cat_id = None
        e = build_help_embed(
            category_id=cat_id,
            member=interaction.user,
            guild_id=interaction.guild.id if interaction.guild else 0,
        )
        view = HelpView(current_cat=cat_id)
        await interaction.edit_original_response(embed=e, view=view)


class HelpView(discord.ui.View):
    def __init__(self, current_cat=None):
        super().__init__(timeout=300)
        self.add_item(HelpSelect(current_cat=current_cat))


class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        # Картинки в справке отключены — прогрев не нужен.
        pass

    def _resolve_help_cat(self, category):
        if not category:
            return None
        cat_l = str(category).lower().strip()
        for c in _all_category_labels():
            if c.lower() == cat_l or cat_l in c.lower():
                return c
        return None

    @app_commands.command(name="help", description="Справка по командам бота")
    async def help_slash(self, interaction: discord.Interaction, category: str = None):
        if not HELP_ENABLED:
            await interaction.response.send_message(
                embed=_help_disabled_embed(interaction.guild), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        cat_id = self._resolve_help_cat(category)
        e = build_help_embed(
            category_id=cat_id,
            member=interaction.user,
            guild_id=interaction.guild.id if interaction.guild else 0,
        )
        view = HelpView(current_cat=cat_id)
        await interaction.followup.send(embed=e, view=view, ephemeral=True)


class HelpEmojiUpload(commands.Cog):
    """Загрузить help-иконки на сервер как кастом-эмодзи (разово)."""

    def __init__(self, bot):
        self.bot = bot


    @commands.Cog.listener()
    async def on_ready(self):
        load_custom_help_emojis(self.bot)


async def setup(bot):
    await bot.add_cog(Help(bot))
    await bot.add_cog(HelpEmojiUpload(bot))
