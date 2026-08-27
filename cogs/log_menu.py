"""
Hakumo — Интерактивное графическое меню логов и аудит-хаб (Pillow + Discord UI).

Возможности:
  • Динамическая генерация графической карточки-дашборда для выбранной категории
  • Интерактивное переключение категорий (Модерация, Сообщения, Войс, Участники, Роли, Каналы, Тикеты)
  • Постраничная навигация (◀️ / ▶️) по истории аудита
  • Поиск по участнику или ключевому слову через Discord Modal
  • Отправка тестовых логов с проверкой доставки
"""

from logger import get_logger
from services.audit_labels import human_action

_log = get_logger("log_menu")

import io
import os
import re
import json
import random
import datetime
import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = os.path.join(ROOT, 'assets', 'fonts')
ICONS_DIR = os.path.join(ROOT, 'assets', 'icons', 'logcards')
FONT_B = os.path.join(FONTS, 'Bold.ttf')
FONT_R = os.path.join(FONTS, 'Regular.ttf')
AUDIT_FILE = 'data/audit_log.json'

# Палитра HAKUMO
C_BG_TOP       = (10, 16, 30)
C_BG_BOT       = (16, 26, 48)
C_GOLD         = (212, 175, 55)
C_GOLD_BRIGHT  = (245, 215, 110)
C_GOLD_SOFT    = (160, 130, 50)
C_TEXT_WHITE   = (242, 245, 252)
C_TEXT_DIM     = (140, 155, 185)
C_CELL_BG      = (18, 26, 46, 210)
C_CELL_BORDER  = (212, 175, 55, 65)

# Цветовые акценты категорий для плашек
CAT_META = {
    'all':     {'title': 'ВСЕ СОБЫТИЯ',     'color': (212, 175, 55),  'tag': '✦ HAKUMO · ОБЩИЙ АУДИТ'},
    'mod':     {'title': 'МОДЕРАЦИЯ',       'color': (235, 65, 85),   'tag': '🛡️ HAKUMO · МОДЕРАЦИЯ'},
    'message': {'title': 'СООБЩЕНИЯ',       'color': (0, 195, 255),   'tag': '💬 HAKUMO · СООБЩЕНИЯ'},
    'member':  {'title': 'УЧАСТНИКИ',       'color': (46, 213, 115),  'tag': '👤 HAKUMO · УЧАСТНИКИ'},
    'voice':   {'title': 'ГОЛОСОВЫЕ',       'color': (26, 188, 156),  'tag': '🎙️ HAKUMO · ГОЛОС'},
    'role':    {'title': 'РОЛИ',            'color': (165, 94, 234),  'tag': '🎭 HAKUMO · РОЛИ'},
    'channel': {'title': 'КАНАЛЫ',          'color': (243, 156, 18),  'tag': '📁 HAKUMO · КАНАЛЫ'},
    'guild':   {'title': 'СЕРВЕР',          'color': (212, 175, 55),  'tag': '👑 HAKUMO · СЕРВЕР'},
    'invite':  {'title': 'ПРИГЛАШЕНИЯ',     'color': (108, 92, 231),  'tag': '🔗 HAKUMO · ИНВАЙТЫ'},
    'ticket':  {'title': 'ТИКЕТЫ',          'color': (84, 160, 255),  'tag': '🎫 HAKUMO · ТИКЕТЫ'},
}

_fonts = {}


def _f(bold=False, sz=20):
    key = (bold, sz)
    f = _fonts.get(key)
    if f is None:
        try:
            f = ImageFont.truetype(FONT_B if bold else FONT_R, sz)
        except Exception:
            f = ImageFont.load_default()
        _fonts[key] = f
    return f


def _clean(text):
    t = str(text or '')
    t = re.sub(r'<@&(\d+)>', r'@роль·\1', t)
    t = re.sub(r'<@!?(\d+)>', r'@\1', t)
    t = re.sub(r'<#(\d+)>', r'#\1', t)
    t = re.sub(r'<a?:(\w+):\d+>', r'\1', t)
    t = re.sub(r'[\U00010000-\U0010ffff]', '', t)
    t = re.sub(r'[\u2600-\u27bf]', '', t)
    t = re.sub(r'[\ufe00-\ufe0f]', '', t)
    t = t.replace('**', '').replace('`', '').replace('__', '').strip()
    return re.sub(r'\s+', ' ', t)


def _ellipsize(draw, text, font_obj, max_w):
    text = str(text or '')
    if draw.textlength(text, font=font_obj) <= max_w:
        return text
    while text and draw.textlength(text + '…', font=font_obj) > max_w:
        text = text[:-1]
    return text + '…'


def _load_events_from_db(guild_id: int, category: str = 'all', query: str = '') -> list:
    """Загрузить и отфильтровать события аудита сервера."""
    if not os.path.exists(AUDIT_FILE):
        return []
    try:
        with open(AUDIT_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        events = data.get(str(guild_id), [])
        if not isinstance(events, list):
            return []
        
        filtered = []
        q = str(query or '').lower().strip()
        cat_filter = category.lower().strip()

        for ev in reversed(events):
            c = str(ev.get('category', 'guild')).lower()
            if cat_filter != 'all':
                if cat_filter == 'mod' and c not in ('mod', 'automod'):
                    continue
                elif cat_filter == 'member' and c not in ('member', 'welcome'):
                    continue
                elif cat_filter != c:
                    continue

            if q:
                blob = json.dumps(ev, ensure_ascii=False).lower()
                if q not in blob:
                    continue

            filtered.append(ev)
        return filtered
    except Exception:
        return []


def _format_event_detail(ev: dict) -> str:
    parts = []
    un = ev.get('user_name') or ev.get('name')
    if un:
        parts.append(str(un))
    chn = ev.get('channel_name') or ev.get('channel')
    if chn:
        parts.append('#' + str(chn).lstrip('#'))
    if ev.get('content'):
        parts.append('«' + str(ev['content'])[:45] + '»')
    mn = ev.get('mod_name')
    if mn and mn != '—':
        parts.append(f'Мод: {mn}')
    if ev.get('reason') and ev['reason'] != '—':
        parts.append('Причина: ' + str(ev['reason'])[:50])
    return ' · '.join(parts)[:110] or '—'


def _load_celestial_bg(w, h, cat_tint=None):
    """Загружает реальный звёздно-космический фон assets/help_bg.png с золотой аурой."""
    bg_path = os.path.join(ROOT, 'assets', 'help_bg.png')
    try:
        bg_im = Image.open(bg_path).convert('RGBA')
        bw, bh = bg_im.size
        target_ratio = w / h
        src_ratio = bw / bh
        if src_ratio > target_ratio:
            nw = int(bh * target_ratio)
            x0 = (bw - nw) // 2
            bg_im = bg_im.crop((x0, 0, x0 + nw, bh))
        else:
            nh = int(bw / target_ratio)
            y0 = (bh - nh) // 2
            bg_im = bg_im.crop((0, y0, bw, y0 + nh))
        base = bg_im.resize((w, h), Image.Resampling.LANCZOS)
    except Exception:
        grad = Image.new('RGB', (1, h))
        for y in range(h):
            t = y / max(1, h - 1)
            grad.putpixel((0, y), tuple(int(C_BG_TOP[i] + (C_BG_BOT[i] - C_BG_TOP[i]) * t) for i in range(3)))
        base = grad.resize((w, h)).convert('RGBA')

    if cat_tint:
        glow = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        gd.ellipse((-100, -120, 560, 300), fill=C_GOLD + (34,))
        gd.ellipse((w - 440, -140, w + 100, 280), fill=cat_tint + (25,))
        glow = glow.filter(ImageFilter.GaussianBlur(75))
        base = Image.alpha_composite(base, glow)

    return base


def generate_log_browser_card(guild_name: str, category: str, events: list, page: int, total_pages: int, search_q: str = '') -> Image.Image:
    """Генерирует графическую Pillow-таблицу для интерактивного меню логов."""
    W = 1180
    PAD = 44
    meta = CAT_META.get(category, CAT_META['all'])
    acc = meta['color']
    
    row_h = 74
    gap_y = 10
    header_h = 176
    footer_h = 72
    display_events = events[:6]
    H = header_h + max(1, len(display_events)) * (row_h + gap_y) + footer_h

    # 1. Полноценная звёздная иллюстрация с неоновым свечением
    img = _load_celestial_bg(W, H, cat_tint=acc)
    d = ImageDraw.Draw(img)

    # 4. Двойная золотая рамка
    d.rectangle((10, 10, W - 10, H - 10), outline=C_GOLD + (80,), width=2)
    d.rectangle((16, 16, W - 16, H - 16), outline=C_GOLD_SOFT + (40,), width=1)

    # 5. Шапка таблицы
    tag_txt = meta['tag']
    tag_w = d.textlength(tag_txt, font=_f(True, 18)) + 26
    d.rounded_rectangle((PAD, 32, PAD + tag_w, 32 + 34), radius=10,
                        fill=(20, 28, 48, 220), outline=C_GOLD + (120,), width=1)
    d.text((PAD + 13, 38), tag_txt, font=_f(True, 18), fill=C_GOLD_BRIGHT)

    # Индикатор страницы и поиска справа вверху
    page_txt = f"Стр. {page} / {max(1, total_pages)}"
    if search_q:
        page_txt += f" · Поиск: «{_clean(search_q)[:16]}»"
    pw = d.textlength(page_txt, font=_f(True, 18)) + 24
    d.rounded_rectangle((W - PAD - pw, 32, W - PAD, 32 + 34), radius=10,
                        fill=(20, 28, 48, 220), outline=acc + (120,), width=1)
    d.text((W - PAD - pw + 12, 38), page_txt, font=_f(True, 18), fill=C_TEXT_WHITE)

    # Заголовок раздела
    title_txt = meta['title']
    d.text((PAD, 78), title_txt, font=_f(True, 38), fill=C_TEXT_WHITE)
    sub_txt = f"Сервер: {_clean(guild_name)} · активных событий: {len(events)}"
    d.text((PAD, 126), sub_txt, font=_f(False, 18), fill=C_TEXT_DIM)

    # Золотой разделитель шапки
    d.line([(PAD, header_h - 14), (W - PAD, header_h - 14)], fill=C_GOLD + (80,), width=1)
    d.line([(PAD, header_h - 14), (PAD + 220, header_h - 14)], fill=C_GOLD_BRIGHT + (230,), width=2)

    # 6. Строки событий
    card_w = W - PAD * 2
    y = header_h

    if not display_events:
        d.rounded_rectangle((PAD, y, PAD + card_w, y + 84), radius=14,
                            fill=C_CELL_BG, outline=C_CELL_BORDER, width=1)
        d.text((PAD + 24, y + 28), "В этой категории пока нет записанных событий.",
               font=_f(False, 22), fill=C_TEXT_DIM)
    else:
        for ev in display_events:
            ev_cat = str(ev.get('category', 'guild')).lower()
            ev_acc = CAT_META.get(ev_cat, CAT_META['all'])['color']
            
            # Плашка строки
            d.rounded_rectangle((PAD, y, PAD + card_w, y + row_h), radius=14,
                                fill=C_CELL_BG, outline=C_CELL_BORDER, width=1)

            # Левый акцентный штрих
            d.rounded_rectangle((PAD + 3, y + 10, PAD + 8, y + row_h - 10), radius=3,
                                fill=ev_acc + (255,))

            # Время
            ts = str(ev.get('timestamp', ''))
            time_str = ts[11:16] if 'T' in ts else (ts[:5] if ts else '—')
            d.text((PAD + 20, y + 24), time_str, font=_f(True, 22), fill=C_GOLD_BRIGHT)

            # Название действия (сырые коды старых записей — по-русски)
            act_txt = _clean(human_action(ev.get('action', 'Событие')))
            act_max_w = 370
            d.text((PAD + 110, y + 23), _ellipsize(d, act_txt, _f(True, 24), act_max_w),
                   font=_f(True, 24), fill=C_TEXT_WHITE)

            # Разделитель
            d.text((PAD + 490, y + 21), '›', font=_f(True, 24), fill=C_GOLD + (180,))

            # Детали события
            det_txt = _clean(_format_event_detail(ev))
            det_max_w = card_w - 520 - 20
            d.text((PAD + 515, y + 25), _ellipsize(d, det_txt, _f(False, 20), det_max_w),
                   font=_f(False, 20), fill=C_TEXT_DIM)

            y += row_h + gap_y

    # 7. Футер таблицы
    fy = H - footer_h + 16
    d.line([(PAD, fy), (W - PAD, fy)], fill=C_GOLD + (80,), width=1)
    d.text((PAD, fy + 16), "HAKUMO LOG HUB · ИНТЕРАКТИВНЫЙ АУДИТ", font=_f(False, 20), fill=C_TEXT_DIM)

    brand = "✦ HAKUMO"
    bw = d.textlength(brand, font=_f(True, 22))
    d.text((W - PAD - bw, fy + 14), brand, font=_f(True, 22), fill=C_GOLD_BRIGHT)

    return img


def generate_log_browser_bytes(guild_name: str, category: str, events: list, page: int, total_pages: int, search_q: str = '') -> io.BytesIO:
    card = generate_log_browser_card(guild_name, category, events, page, total_pages, search_q).convert('RGB')
    buf = io.BytesIO()
    card.save(buf, format='PNG', optimize=True)
    buf.seek(0)
    return buf


class LogSearchModal(discord.ui.Modal, title="Поиск по истории логов"):
    search_query = discord.ui.TextInput(
        label="Ключевое слово, никнейм или ID",
        placeholder="Например: Ivan, 123456789, спам...",
        required=False,
        max_length=80,
    )

    def __init__(self, parent_view):
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.parent_view.query = str(self.search_query.value).strip()
        self.parent_view.page = 1
        await self.parent_view.update_message(interaction)


class LogCategorySelect(discord.ui.Select):
    def __init__(self, current_cat="all"):
        options = [
            discord.SelectOption(label="Все события", value="all", emoji="👑", description="Полная сводка всех логов сервера", default=(current_cat == "all")),
            discord.SelectOption(label="Модерация", value="mod", emoji="🛡️", description="Баны, кики, муты, таймауты, варны", default=(current_cat == "mod")),
            discord.SelectOption(label="Сообщения", value="message", emoji="💬", description="Удаления, правки сообщений", default=(current_cat == "message")),
            discord.SelectOption(label="Участники", value="member", emoji="👤", description="Входы, выходы, смена ников и аватаров", default=(current_cat == "member")),
            discord.SelectOption(label="Голосовые", value="voice", emoji="🎙️", description="Подключения, выходы, переходы в войсе", default=(current_cat == "voice")),
            discord.SelectOption(label="Роли", value="role", emoji="🎭", description="Создание, удаление, выдача и снятие ролей", default=(current_cat == "role")),
            discord.SelectOption(label="Каналы", value="channel", emoji="📁", description="Создание, удаление, права каналов", default=(current_cat == "channel")),
            discord.SelectOption(label="Приглашения", value="invite", emoji="🔗", description="Создание и использование инвайт-ссылок", default=(current_cat == "invite")),
            discord.SelectOption(label="Тикеты", value="ticket", emoji="🎫", description="Обращения в службу поддержки", default=(current_cat == "ticket")),
        ]
        super().__init__(placeholder="📂 Выберите категорию логов...", options=options, custom_id="log_menu:select")

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.view.category = self.values[0]
        self.view.page = 1
        await self.view.update_message(interaction)


class LogBrowserView(discord.ui.View):
    """Интерактивное меню-дашборд для просмотра логов сервера."""

    def __init__(self, guild: discord.Guild, user_id: int, category: str = "all", query: str = ""):
        super().__init__(timeout=600)
        self.guild = guild
        self.user_id = user_id
        self.category = category
        self.query = query
        self.page = 1
        self.page_size = 6
        self._refresh_components()

    def _refresh_components(self):
        self.clear_items()
        self.add_item(LogCategorySelect(current_cat=self.category))

        # Кнопки навигации и действий
        btn_prev = discord.ui.Button(label="Назад", style=discord.ButtonStyle.secondary, emoji="◀️", custom_id="log_menu:prev", disabled=(self.page <= 1))
        btn_prev.callback = self.on_prev

        btn_next = discord.ui.Button(label="Вперёд", style=discord.ButtonStyle.secondary, emoji="▶️", custom_id="log_menu:next")
        btn_next.callback = self.on_next

        btn_search = discord.ui.Button(label="Поиск" if not self.query else f"Поиск: {self.query[:10]}", style=discord.ButtonStyle.primary if self.query else discord.ButtonStyle.secondary, emoji="🔍", custom_id="log_menu:search")
        btn_search.callback = self.on_search

        btn_reset = discord.ui.Button(label="Сброс фильтра", style=discord.ButtonStyle.danger, emoji="✖️", custom_id="log_menu:reset", disabled=(not self.query and self.category == 'all'))
        btn_reset.callback = self.on_reset

        btn_refresh = discord.ui.Button(label="Обновить", style=discord.ButtonStyle.success, emoji="🔄", custom_id="log_menu:refresh")
        btn_refresh.callback = self.on_refresh

        self.add_item(btn_prev)
        self.add_item(btn_next)
        self.add_item(btn_search)
        self.add_item(btn_reset)
        self.add_item(btn_refresh)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not (interaction.user.guild_permissions.administrator or interaction.user.guild_permissions.moderate_members or interaction.user.guild_permissions.manage_messages):
            await interaction.response.send_message("🚫 Меню логов доступно только модераторам и администраторам.", ephemeral=True)
            return False
        return True

    def get_current_page_data(self):
        all_events = _load_events_from_db(self.guild.id, self.category, self.query)
        total = len(all_events)
        total_pages = max(1, math.ceil(total / self.page_size))
        self.page = max(1, min(self.page, total_pages))
        start_idx = (self.page - 1) * self.page_size
        page_events = all_events[start_idx:start_idx + self.page_size]
        return page_events, self.page, total_pages, total

    async def update_message(self, interaction: discord.Interaction):
        page_events, page, total_pages, total = self.get_current_page_data()
        self._refresh_components()
        # Обновляем кнопку Next
        for item in self.children:
            if getattr(item, 'custom_id', None) == 'log_menu:next':
                item.disabled = (self.page >= total_pages)

        img_buf = await interaction.client.loop.run_in_executor(
            None, generate_log_browser_bytes, self.guild.name, self.category, page_events, page, total_pages, self.query
        )
        file = discord.File(img_buf, filename="hakumo_log_menu.png")
        if interaction.response.is_done():
            await interaction.edit_original_response(attachments=[file], view=self)
        else:
            await interaction.response.edit_message(attachments=[file], view=self)

    async def on_prev(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if self.page > 1:
            self.page -= 1
        await self.update_message(interaction)

    async def on_next(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.page += 1
        await self.update_message(interaction)

    async def on_search(self, interaction: discord.Interaction):
        await interaction.response.send_modal(LogSearchModal(self))

    async def on_reset(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.category = 'all'
        self.query = ''
        self.page = 1
        await self.update_message(interaction)

    async def on_refresh(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self.update_message(interaction)


class LogMenu(commands.Cog):
    """Интерактивное меню логов для модераторов и администраторов."""

    def __init__(self, bot):
        self.bot = bot


async def setup(bot):
    await bot.add_cog(LogMenu(bot))
