"""
Staff Apply — recruitment menu (Helper / Moderator / Eventsmod / Broadcaster).
Components V2 LayoutView + webhook publish. English position labels.
"""

MENU_GIF = "https://media.tenor.com/x8v1oNUOmg4AAAAC/rain-dark.gif"

import discord
from discord.ext import commands
from discord import app_commands
from config import Config
import json
import os
import io
from datetime import datetime, timezone

import aiohttp
from PIL import Image, ImageDraw, ImageFont

from logger import get_logger
log = get_logger("staff_apply")


APPLY_CHANNEL_ID = Config.APPLY_CHANNEL_ID
STAFF_MENU_CHANNEL_ID = getattr(Config, 'STAFF_MENU_CHANNEL_ID', 0)
APPS_FILE = "data/staff_apps.json"
BLACKLIST_FILE = "data/staff_blacklist.json"


ROOT = os.path.join(os.path.dirname(__file__), '..')
FONTS = os.path.join(ROOT, 'assets', 'fonts')
BG_PATH = os.path.join(ROOT, 'assets', 'staff_bg.jpg')
# Резервный баннер пользователя, если локальный файл ещё не загружен.
STAFF_REMOTE_BANNER_URL = "https://files.catbox.moe/pe6gqw.jpeg"
FONT_B = os.path.join(FONTS, 'Bold.ttf')
FONT_R = os.path.join(FONTS, 'Regular.ttf')

WHITE = (255, 255, 255)
BLACK = (20, 20, 25)
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

def _icon_staff(d, cx, cy, s, w, color):
    r = s * 0.4
    points = [
        (cx, cy - r),
        (cx + r, cy - r * 0.6),
        (cx + r * 0.8, cy + r * 0.4),
        (cx, cy + r),
        (cx - r * 0.8, cy + r * 0.4),
        (cx - r, cy - r * 0.6)
    ]
    d.polygon(points, outline=color, width=w)

def _icon_badge(diameter, glyph_fn, ring_color=BLACK, ring_w=None, icon_color=BLACK):
    ring_w = ring_w if ring_w is not None else max(2, diameter // 22)
    def draw(d, scale):
        size = diameter * scale
        rw = ring_w * scale
        r = size * 0.22
        d.rounded_rectangle((rw / 2, rw / 2, size - rw / 2 - 1, size - rw / 2 - 1),
                             radius=r, fill=WHITE, outline=ring_color, width=rw)
        glyph_fn(d, size / 2, size / 2, size * 0.60, max(2, int(size * 0.032)), icon_color)
    return _ss_render(diameter, diameter, draw)

def _corner_bracket(size, thickness, length_ratio=0.35, color=BLACK):
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

def _load_bg(w, h):
    """Корректная обрезка фона по пропорциям без растягивания и размытия"""
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

def generate_staff_panel_card() -> Image.Image:
    W, H = 920, 360
    bg = _load_bg(W, H)
    d = ImageDraw.Draw(bg)

    # Тематический акцент: Теплый золотисто-бронзовый (как у волос персонажа и книг!)
    accent = (197, 137, 47)

    # Наружная полупрозрачная рамка (эффект теплого матового стекла поверх красивого фона)
    outer_border = _rounded_panel(896, 336, radius=16, fill=(255, 253, 245, 160), outline=accent, ow=2)
    bg.alpha_composite(outer_border, (12, 12))

    # Внутренняя панель заголовка
    header_box = _rounded_panel(848, 260, radius=14, fill=(255, 253, 245, 190), outline=BLACK, ow=2)
    bg.alpha_composite(header_box, (36, 30))

    # Векторная иконка щита в бронзовом цвете
    badge = _icon_badge(80, _icon_staff, ring_color=BLACK, ring_w=2, icon_color=accent)
    bg.alpha_composite(badge, (56, 120))

    # Текстовые заголовки СТРОГО на русском языке в темном цвете
    d.text((160, 110), "STAFF TEAM • НАБОР В КОМАНДУ", fill=BLACK, font=_f(True, 30))
    d.text((160, 160), "ВЫБЕРИТЕ ЖЕЛАЕМУЮ ДОЛЖНОСТЬ В МЕНЮ НИЖЕ", fill=MUTED, font=_f(False, 20))

    # Боковая плашка в стиле светлого стекла
    pill = _rounded_panel(150, 40, radius=10, fill=WHITE, outline=accent, ow=2)
    bg.alpha_composite(pill, (710, 140))
    d.text((746, 150), "STAFF RECRUIT", fill=accent, font=_f(True, 14))

    # Угловые скобки в бронзовом цвете
    br = _corner_bracket(40, 4, color=accent)
    bg.alpha_composite(br, (6, 6))
    bg.alpha_composite(br.rotate(270), (W - 46, 6))
    bg.alpha_composite(br.rotate(90), (6, H - 46))
    bg.alpha_composite(br.rotate(180), (W - 46, H - 46))

    return bg

def generate_staff_panel_bytes() -> io.BytesIO:
    card = generate_staff_panel_card().convert('RGB')
    buf = io.BytesIO()
    card.save(buf, format='PNG', optimize=True)
    buf.seek(0)
    return buf


def _apply_room(guild):
    """Legacy-фолбек: комната апелляций, если канал заявок недоступен.

    Заявки в команду идут в APPLY_CHANNEL_ID / staff_apply_channel.
    Эта комната — только запасной путь.
    """
    try:
        from services.channel_routes import (
            get_route as _get_route, KNOWN_CHANNELS as _KNOWN,
            channel_on_guild as _on_g)
        cid = int(_get_route(guild.id, 'ban_appeal_channel') or 0)
        if not cid:
            cid = int(_KNOWN.get('ban_appeal_channel') or 0)
    except Exception as _ex:
        log.debug('staff_apply: маршрут комнаты заявок: %s', _ex)
        cid = 0
    if not cid:
        return None
    try:
        ch = _on_g(guild, cid)
        if ch is not None:
            return ch
    except Exception as _e:
        log.debug('staff_apply: канал #%s: %s', cid, _e)
    getter = getattr(guild, 'get_channel', None)
    return getter(cid) if callable(getter) else None


def menu_channel(guild):
    """Куда публиковать меню набора: панель → KNOWN → Config → None."""
    if not guild:
        return None
    try:
        from services.channel_routes import (
            get_route, KNOWN_CHANNELS, channel_on_guild, STAFF_MENU_CHANNEL_ID as _KNOWN_MENU)
        cid = int(get_route(guild.id, 'staff_menu_channel') or 0)
        if not cid:
            cid = int(KNOWN_CHANNELS.get('staff_menu_channel') or _KNOWN_MENU or 0)
        if not cid:
            cid = int(STAFF_MENU_CHANNEL_ID or 0)
        if cid:
            ch = channel_on_guild(guild, cid)
            if ch is not None:
                return ch
            getter = getattr(guild, 'get_channel', None)
            return getter(cid) if callable(getter) else None
    except Exception as _ex:
        log.debug('staff_apply: menu_channel: %s', _ex)
    cid = int(STAFF_MENU_CHANNEL_ID or 0)
    if not cid:
        return None
    getter = getattr(guild, 'get_channel', None)
    return getter(cid) if callable(getter) else None


def _curator_ping(guild, role_name: str = ''):
    """Тег куратора СВОЕЙ ветки для карточки заявки.

    Helper → × Отвечаю за Helper, Event → × Отвечаю за Eventsmod и т.д.
    Тег только если роль реально есть на сервере.
    """
    from services.staff_roles import (
        curator_role_id_for, normalize_position, KNOWN_CURATOR_BY_KIND,
        KNOWN_CURATOR_ROLE_ID)
    if not guild:
        return ''
    kind = normalize_position(role_name) or 'moderator'
    cur = curator_role_id_for(guild.id, kind)
    get_role = getattr(guild, 'get_role', None)
    if not callable(get_role):
        return ''
    fallbacks = [
        cur,
        int(KNOWN_CURATOR_BY_KIND.get(kind) or 0),
        int(KNOWN_CURATOR_ROLE_ID or 0),
    ]
    for rid in fallbacks:
        try:
            rid = int(rid or 0)
        except (TypeError, ValueError) as _e:
            log.debug('staff_apply: id роли %r: %s', rid, _e)
            continue
        if rid and get_role(rid) is not None:
            return f'<@&{rid}>'
    return ''


def _channel_for_kind(guild, kind: str):
    """Канал ветки по должности (панель/.env)."""
    from services.staff_roles import setting
    key_env = {
        'helper': ('helper_channel', Config.STAFF_HELPER_CHANNEL_ID),
        'moderator': ('moderator_channel', Config.STAFF_MODERATOR_CHANNEL_ID),
        'event': ('event_channel', getattr(Config, 'STAFF_EVENT_CHANNEL_ID', 0)),
        'broadcaster': ('broadcaster_channel',
                        getattr(Config, 'STAFF_BROADCASTER_CHANNEL_ID', 0)),
    }.get(kind or 'moderator', ('moderator_channel', 0))
    key, env_cid = key_env
    cid = setting(guild.id, key, env_cid)
    if not cid:
        return None
    getter = getattr(guild, 'get_channel', None)
    return getter(int(cid)) if callable(getter) else None


def _bot_can_send(channel) -> bool:
    """Бот реально может писать в канал (не только «канал есть в кэше»)."""
    if channel is None:
        return False
    try:
        guild = getattr(channel, 'guild', None)
        me = getattr(guild, 'me', None) if guild is not None else None
        if me is None:
            return True  # нет me — пусть попробует отправить
        perms = channel.permissions_for(me)
        return bool(getattr(perms, 'view_channel', False)
                    and getattr(perms, 'send_messages', False))
    except Exception:
        return False


def apply_target(role_name: str, guild):
    """Куда отправить новую заявку + тег куратора СВОЕЙ ветки.

    Порядок канала:
      1) своя ветка должности (helper/moderator/event/broadcaster)
      2) общий apply_channel / APPLY_CHANNEL_ID / staff_apply_channel (анкеты)
      3) комната апелляций (legacy-фолбек)
    Канал без права send у бота пропускаем — иначе «сохранено, персонал
    не уведомлён» при живом #・анкеты.
    """
    from services.staff_roles import normalize_position, setting
    if not guild:
        return None, ''
    kind = normalize_position(role_name) or 'moderator'
    tag = _curator_ping(guild, role_name)
    candidates = []
    # 1) своя ветка
    ch = _channel_for_kind(guild, kind)
    if ch is not None:
        candidates.append(ch)
    # 2) общий канал заявок (анкеты)
    common = setting(guild.id, 'apply_channel', APPLY_CHANNEL_ID)
    if not common:
        try:
            from services.channel_routes import (
                get_route, KNOWN_CHANNELS, STAFF_APPLY_CHANNEL_ID)
            common = (get_route(guild.id, 'staff_apply_channel')
                      or KNOWN_CHANNELS.get('staff_apply_channel')
                      or STAFF_APPLY_CHANNEL_ID)
        except Exception:
            common = APPLY_CHANNEL_ID
    if common:
        getter = getattr(guild, 'get_channel', None)
        ch = getter(int(common)) if callable(getter) else None
        if ch is not None:
            candidates.append(ch)
    # 3) legacy: комната апелляций
    room = _apply_room(guild)
    if room is not None:
        candidates.append(room)
    seen = set()
    for ch in candidates:
        cid = getattr(ch, 'id', None)
        if cid in seen:
            continue
        seen.add(cid)
        if _bot_can_send(ch):
            return ch, tag
        log.warning('STAFF: канал #%s (%s) без права send — пропуск',
                    cid, getattr(ch, 'name', '?'))
    return None, tag


def _format_join(member) -> str:
    """Когда человек зашёл на сервер — для карточки куратору."""
    joined = getattr(member, 'joined_at', None)
    if joined is None:
        return '—'
    try:
        if joined.tzinfo is None:
            joined = joined.replace(tzinfo=timezone.utc)
        ts = int(joined.timestamp())
        return f'<t:{ts}:f> · <t:{ts}:R>'
    except Exception:
        return '—'


# Вопросы модалки по веткам (как на скринах Helper/Moderator).
# Discord TextInput.label ≤ 45 символов.
POSITION_QUESTIONS = {
    'helper': [
        {'label': 'Ваше имя и возраст', 'ph': 'например: Аня 21', 'style': 'short', 'max': 80},
        {'label': 'Умеете ли вы предлагать идеи', 'ph': 'Умею / нет', 'style': 'short', 'max': 200},
        {'label': 'Сможете ли вы приветствовать участников', 'ph': 'Смогу / нет', 'style': 'short', 'max': 200},
        {'label': 'Умеете ли вы прописывать бамп команды', 'ph': 'Да / нет', 'style': 'short', 'max': 100},
    ],
    'moderator': [
        {'label': 'Ваше имя и возраст', 'ph': 'например: 19', 'style': 'short', 'max': 80},
        {'label': 'С чего вы сидите и пик активности в сутках',
         'ph': 'например: пк, 2 часа', 'style': 'short', 'max': 200},
        {'label': 'Расскажите о себе и о своем опыте',
         'ph': 'кратко о себе и опыте', 'style': 'paragraph', 'max': 500},
        {'label': 'Оцените свои знания правил сервера/платформы',
         'ph': 'например: 10/10', 'style': 'short', 'max': 100},
    ],
    'event': [
        {'label': 'Ваше имя и возраст', 'ph': 'например: Саша 20', 'style': 'short', 'max': 80},
        {'label': 'Какие ивенты умеете проводить',
         'ph': 'мафия, квиз, киноночь…', 'style': 'paragraph', 'max': 500},
        {'label': 'Сколько часов в день готовы на ивенты',
         'ph': 'например: 2–3 часа, вечер', 'style': 'short', 'max': 200},
        {'label': 'Идеи ивентов для сервера',
         'ph': '1–2 идеи коротко', 'style': 'paragraph', 'max': 500},
    ],
    'broadcaster': [
        {'label': 'Ваше имя и возраст', 'ph': 'например: Лёша 22', 'style': 'short', 'max': 80},
        {'label': 'Где стримите и с какого устройства',
         'ph': 'Twitch/YouTube, ПК…', 'style': 'short', 'max': 200},
        {'label': 'Опыт эфиров и тематика контента',
         'ph': 'опыт и что стримите', 'style': 'paragraph', 'max': 500},
        {'label': 'Сколько часов в неделю готовы стримить',
         'ph': 'например: 6–8 часов', 'style': 'short', 'max': 200},
    ],
}


def questions_for(kind: str) -> list:
    """4 вопроса ветки; fallback — moderator."""
    from services.staff_roles import normalize_position
    k = normalize_position(kind) or str(kind or '').lower()
    return list(POSITION_QUESTIONS.get(k) or POSITION_QUESTIONS['moderator'])


def build_application_body(*, user, user_id: str, age: str = '', activity: str = '',
                           experience: str = '', reason: str = '', member=None,
                           kind: str = None, answers: list = None) -> str:
    """Текст карточки заявки V2 — тег юзера, id, вход, ответы с лейблами ветки."""
    mention = getattr(user, 'mention', None) or f'<@{user_id}>'
    lines = [
        f'**Пользователь** · {mention}',
        f'**ID** · `{user_id}`',
        f'**Присоединился** · {_format_join(member)}',
        '',
    ]
    pairs = []
    if answers and isinstance(answers, list):
        for row in answers:
            if not isinstance(row, dict):
                continue
            lab = str(row.get('label') or '').strip() or 'Ответ'
            val = str(row.get('value') or '').strip() or '—'
            pairs.append((lab, val))
    if not pairs:
        qs = questions_for(kind or 'moderator')
        vals = [age, activity, experience, reason]
        for i, q in enumerate(qs[:4]):
            pairs.append((q['label'], str(vals[i] if i < len(vals) else '') or '—'))
    for lab, val in pairs:
        lines.append(f'**{lab}**')
        lines.append(f'> {val[:1000]}')
        lines.append('')
    return '\n'.join(lines).rstrip()[:3500]


def load_apps():
    os.makedirs("data", exist_ok=True)
    if os.path.exists(APPS_FILE):
        with open(APPS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_apps(data):
    with open(APPS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_blacklist():
    """ЧС по веткам: {user_id: {kind: {by, at, guild_id, reason}}}."""
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(BLACKLIST_FILE):
        return {}
    try:
        with open(BLACKLIST_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
    except (OSError, ValueError) as _ex:
        log.debug('staff blacklist load: %s', _ex)
        return {}
    # миграция старого формата {uid: {user_id, role, by, at, ...}}
    from services.staff_roles import normalize_position
    migrated = False
    out = {}
    for uid, entry in data.items():
        if not isinstance(entry, dict):
            continue
        # уже по веткам: ключи — kind (helper/moderator/…)
        kinds = {}
        legacy_role = entry.get('role') if 'by' in entry or 'at' in entry else None
        if legacy_role is not None and not any(
                k in entry for k in ('helper', 'moderator', 'event', 'broadcaster')):
            kind = normalize_position(legacy_role) or 'moderator'
            kinds[kind] = {
                'by': str(entry.get('by') or ''),
                'at': str(entry.get('at') or ''),
                'guild_id': entry.get('guild_id'),
                'reason': str(entry.get('reason') or ''),
            }
            migrated = True
        else:
            for kind, row in entry.items():
                if kind in ('user_id', 'role', 'by', 'at', 'guild_id', 'reason'):
                    continue
                nk = normalize_position(kind) or str(kind or '').lower()
                if not nk or not isinstance(row, dict):
                    continue
                kinds[nk] = {
                    'by': str(row.get('by') or ''),
                    'at': str(row.get('at') or ''),
                    'guild_id': row.get('guild_id'),
                    'reason': str(row.get('reason') or ''),
                }
        if kinds:
            out[str(uid)] = kinds
    if migrated:
        try:
            save_blacklist(out)
        except Exception as _ex:
            log.debug('staff blacklist migrate save: %s', _ex)
    return out


def save_blacklist(data):
    os.makedirs("data", exist_ok=True)
    with open(BLACKLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def is_blacklisted(user_id, position=None) -> bool:
    """ЧС только своей ветки. Без position — есть ли хоть одна ветка в ЧС."""
    row = load_blacklist().get(str(user_id)) or {}
    if not row:
        return False
    if position is None:
        return True
    from services.staff_roles import normalize_position
    kind = normalize_position(position)
    return bool(kind and kind in row)


def blacklisted_kinds(user_id) -> list:
    row = load_blacklist().get(str(user_id)) or {}
    return sorted(row.keys())


def add_to_blacklist(user_id, *, by: str = '', role: str = '',
                     guild_id=None, reason: str = '') -> dict:
    """Добавить в ЧС только ветки должности заявки."""
    from services.staff_roles import normalize_position
    kind = normalize_position(role) or 'moderator'
    bl = load_blacklist()
    row = bl.setdefault(str(user_id), {})
    entry = {
        'by': str(by or ''),
        'role': kind,
        'guild_id': int(guild_id) if guild_id else None,
        'reason': str(reason or ''),
        'at': datetime.now(timezone.utc).isoformat(),
    }
    row[kind] = entry
    save_blacklist(bl)
    return entry


def remove_from_blacklist(user_id, position=None) -> bool:
    """Снять ЧС: одну ветку или все."""
    from services.staff_roles import normalize_position
    bl = load_blacklist()
    uid = str(user_id)
    if uid not in bl:
        return False
    if position is None:
        del bl[uid]
        save_blacklist(bl)
        return True
    kind = normalize_position(position)
    if not kind or kind not in bl[uid]:
        return False
    del bl[uid][kind]
    if not bl[uid]:
        del bl[uid]
    save_blacklist(bl)
    return True


MENU_STATE_FILE = "data/staff_menu_state.json"
# bump → при следующем on_ready меню перепубликуется в канал наборов
# v3: 4 ветки (Helper/Mod/Event/Broadcaster) + V2 баннер НАБОРЫ (не Gojo STAFF)
MENU_POST_VERSION = 3


def _load_menu_state():
    if os.path.exists(MENU_STATE_FILE):
        try:
            with open(MENU_STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            pass
    return {}


def _save_menu_state(data):
    os.makedirs("data", exist_ok=True)
    with open(MENU_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════════
# Модальное окно заявки — вопросы зависят от ветки
# ═══════════════════════════════════════════════════════════════════

class StaffApplyModal(discord.ui.Modal):
    """4 поля TextInput с лейблами конкретной должности."""

    def __init__(self, role_name: str):
        from services.staff_roles import normalize_position, position_label
        kind = normalize_position(role_name) or 'moderator'
        label = position_label(kind)
        qs = questions_for(kind)
        super().__init__(title=f'Заявка · {label}'[:45])
        self.role_name = role_name
        self.kind = kind
        self.q_meta = qs
        self._inputs = []
        for q in qs[:4]:
            style = (discord.TextStyle.paragraph
                     if q.get('style') == 'paragraph'
                     else discord.TextStyle.short)
            ti = discord.ui.TextInput(
                label=str(q['label'])[:45],
                placeholder=str(q.get('ph') or '')[:100],
                style=style,
                max_length=int(q.get('max') or 200),
                required=True,
            )
            self._inputs.append(ti)
            self.add_item(ti)
        # legacy aliases для тестов / старых путей
        self.age = self._inputs[0]
        self.activity = self._inputs[1]
        self.experience = self._inputs[2]
        self.reason = self._inputs[3]

    def _answer_values(self):
        vals = [str(ti.value or '').strip() for ti in self._inputs]
        while len(vals) < 4:
            vals.append('')
        return vals[:4]

    async def on_submit(self, interaction: discord.Interaction):
        # defer сразу: доставка карточки кураторам может занять >3с
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception as _dex:
            log.debug('staff apply defer: %s', _dex)
        from services.staff_roles import normalize_position, position_label
        user_id = str(interaction.user.id)
        kind = normalize_position(self.role_name) or self.kind or 'moderator'
        role_label = position_label(kind)
        if is_blacklisted(user_id, kind):
            try:
                from services.v2_layouts import respond_v2
                await respond_v2(
                    interaction, kind='err', title='Чёрный список',
                    body=(
                        f'Вы в чёрном списке ветки **{role_label}**.\n'
                        'Другие должности по-прежнему открыты.'
                    ),
                    ephemeral=True)
            except Exception:
                try:
                    await interaction.followup.send(
                        f'Вы в чёрном списке ветки **{role_label}**. '
                        'Другие должности открыты.',
                        ephemeral=True)
                except Exception as _fx:
                    log.debug('staff apply bl deny: %s', _fx)
            return
        v1, v2, v3, v4 = self._answer_values()
        answers = [
            {'label': self.q_meta[i]['label'], 'value': val}
            for i, val in enumerate((v1, v2, v3, v4))
            if i < len(self.q_meta)
        ]
        apps = load_apps()
        submitted_ts = datetime.now(timezone.utc).isoformat()
        apps[user_id] = {
            "user_id": user_id,
            "username": str(interaction.user),
            "display_name": interaction.user.display_name,
            "avatar": str(interaction.user.display_avatar.url) if interaction.user.display_avatar else None,
            "role": role_label,
            "kind": kind,
            "age": v1,
            "activity": v2,
            "experience": v3,
            "reason": v4,
            "answers": answers,
            "status": "pending",
            "submitted_at": submitted_ts,
            "timestamp": submitted_ts,
            "message_id": None,
            "guild_id": interaction.guild.id if interaction.guild else None,
        }

        delivered = False
        delivery_ch = None
        delivery_err = None
        if interaction.guild:
            ch, tag = apply_target(role_label, interaction.guild)
            if ch:
                member = None
                try:
                    member = interaction.guild.get_member(interaction.user.id)
                except Exception:
                    member = None
                body = build_application_body(
                    user=interaction.user, user_id=user_id,
                    age=v1, activity=v2, experience=v3, reason=v4,
                    member=member, kind=kind, answers=answers)
                # content: пинг куратора + тег заявителя (чтобы кликнуть профиль)
                ping_bits = []
                if tag:
                    ping_bits.append(tag)
                ping_bits.append(interaction.user.mention)
                content = ' · '.join(ping_bits)
                try:
                    card = StaffAppCardView(title=role_label, body=body)
                    msg = await _send_staff_card(
                        ch, content=content, view=card)
                    apps[user_id]["message_id"] = str(msg.id)
                    apps[user_id]["curator_tag"] = tag or None
                    apps[user_id]["channel_id"] = str(getattr(ch, 'id', '') or '')
                    delivered = True
                    delivery_ch = ch
                except (discord.Forbidden, discord.HTTPException) as _ex:
                    delivery_err = str(_ex)
                    log.warning("STAFF: карточка %s не ушла в %s: %s",
                                user_id, getattr(ch, 'name', '?'), _ex)
                    apps[user_id]["delivery"] = "failed"
            else:
                apps[user_id]["delivery"] = "no_channel"
                log.warning("STAFF: заявка %s сохранена, канал не настроен",
                            user_id)

        save_apps(apps)
        if delivered and delivery_ch is not None:
            ch_ref = f"#{getattr(delivery_ch, 'name', None) or 'анкеты'}"
            try:
                _m = getattr(delivery_ch, 'mention', None)
                if _m:
                    ch_ref = _m
            except Exception:
                pass
            confirm = (
                f"Заявка на **{role_label}** ушла в "
                f"{ch_ref}.\n"
                f"Кураторы ветки и админы уже видят карточку.\n"
                f"Статус: `/my-application`"
            )
            confirm_kind = 'ok'
            confirm_title = 'Заявка отправлена'
        else:
            confirm = (
                f"Заявка на **{role_label}** сохранена, но в канал анкет "
                f"не дошла"
                + (f" ({delivery_err})" if delivery_err else
                   " (нет канала или прав у бота).")
                + "\nНапиши администрации."
            )
            confirm_kind = 'warn'
            confirm_title = 'Не доставлено'
        try:
            from services.v2_layouts import respond_v2
            await respond_v2(
                interaction, kind=confirm_kind, title=confirm_title,
                body=confirm, ephemeral=True)
        except Exception as _vx:
            log.debug('staff apply confirm v2: %s', _vx)
            try:
                await interaction.followup.send(confirm, ephemeral=True)
            except Exception as _fx:
                log.debug('staff apply confirm text: %s', _fx)
        log.info(f"Заявка от {interaction.user} на роль {role_label}"
                 + ("" if delivered else " (без уведомления персонала)"))


# ═══════════════════════════════════════════════════════════════════
# Select menu — выбор роли
# ═══════════════════════════════════════════════════════════════════

class RoleSelect(discord.ui.Select):
    def __init__(self):
        from services.menu_banners import select_label
        from services.staff_roles import POSITIONS, position_select_value
        from services.menu_emojis import emoji_for_role
        options = []
        for kind in POSITIONS:
            label = position_select_value(kind)
            options.append(discord.SelectOption(
                label=select_label(label),
                value=label,
                emoji=emoji_for_role(kind),
            ))
        super().__init__(
            placeholder="Выберите должность",
            options=options,
            custom_id="staff_role_select_v2"
        )

    async def callback(self, interaction: discord.Interaction):
        role_name = self.values[0]
        if is_blacklisted(interaction.user.id, role_name):
            from services.v2_layouts import reply_text_v2
            from services.staff_roles import position_label
            return await reply_text_v2(
                interaction,
                (f'Вы в чёрном списке ветки **{position_label(role_name)}**.\n'
                 'Другие должности по-прежнему открыты.'),
                kind='err', title='Чёрный список')
        modal = StaffApplyModal(role_name=role_name)
        await interaction.response.send_modal(modal)


# ═══════════════════════════════════════════════════════════════════
# Рассмотрение заявки (persistent) — Select «Принять / Отклонить»
# ═══════════════════════════════════════════════════════════════════

class StaffReviewSelect(discord.ui.Select):
    """Select решения — внутри V2-карточки заявки, со стикерами."""

    def __init__(self):
        from services.menu_banners import select_label
        from services.menu_emojis import emoji_for_review
        super().__init__(
            placeholder="",
            options=[
                discord.SelectOption(
                    label=select_label("Принять"), value="approve",
                    emoji=emoji_for_review('approve')),
                discord.SelectOption(
                    label=select_label("Отклонить"), value="reject",
                    emoji=emoji_for_review('reject')),
                discord.SelectOption(
                    label=select_label("Чёрный список"), value="blacklist",
                    emoji=emoji_for_review('blacklist')),
            ],
            custom_id="staff_review_select_v2",
            min_values=1, max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        await StaffReviewView()._review(interaction, self.values[0])


class StaffAppCardView(discord.ui.LayoutView):
    """Карточка заявки куратору — V2 webhook: должность, тег, ответы, select."""

    def __init__(self, *, title: str, body: str, footer: str = ''):
        super().__init__(timeout=None)
        from services.v2_layouts import V2_AVAILABLE, black_container
        from discord import SeparatorSpacing
        from services.menu_emojis import emoji_for_role
        from services.staff_roles import normalize_position
        sel = StaffReviewSelect()
        kind = normalize_position(title) or 'moderator'
        try:
            em = emoji_for_role(kind)
            em_s = str(em) if em else ''
        except Exception:
            em_s = ''
        head = f'# {em_s} {title}'.strip() if em_s else f'# {title}'
        foot = footer or 'HAKUMO · решение — меню ниже · куратор этой ветки или админ'
        if V2_AVAILABLE:
            from discord import ui as dui
            children = [
                dui.TextDisplay(head[:500]),
                dui.TextDisplay('-# HAKUMO · заявка в команду'),
                dui.Separator(spacing=SeparatorSpacing.large),
                dui.TextDisplay(str(body)[:3500]),
                dui.Separator(),
                dui.TextDisplay(f'-# {foot}'[:400]),
            ]
            row = dui.ActionRow()
            row.add_item(sel)
            children.append(row)
            self.add_item(black_container(*children))
            return
        row = discord.ui.ActionRow()
        row.add_item(sel)
        self.add_item(row)


class StaffReviewView(discord.ui.View):
    """Select под сообщением заявки: решение + DM заявителю.

    Классический View — для старых карточек (embed) до перехода на V2.
    """

    def __init__(self):
        super().__init__(timeout=None)

    @staticmethod
    def _find_app_by_message(message_id):
        apps = load_apps()
        for key, app in apps.items():
            if str(app.get("message_id") or "") == str(message_id):
                return key, app, apps
        return None, None, apps

    async def _review(self, interaction: discord.Interaction, action: str):
        from services.v2_layouts import (
            reply_text_v2, respond_v2, send_dm_v2, notice_layout_view,
            V2_AVAILABLE)
        from services.staff_roles import can_review_position, position_label

        key, app, apps = self._find_app_by_message(interaction.message.id)
        if not app:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
            return await reply_text_v2(
                interaction, "Заявка не найдена.", kind='err')
        position = app.get('role') or ''
        ok, deny = can_review_position(interaction.user, position)
        if not ok:
            return await reply_text_v2(
                interaction, deny or "Чужая ветка.",
                kind='err', title='Нет доступа')
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        if app.get("status") != "pending":
            label = {
                "approved": "одобрена",
                "rejected": "отклонена",
                "blacklisted": "в чёрном списке",
            }.get(app.get("status"), app.get("status", "?"))
            return await reply_text_v2(
                interaction, f"Уже **{label}**.", kind='warn')

        status_map = {
            "approve": "approved",
            "reject": "rejected",
            "blacklist": "blacklisted",
        }
        if action not in status_map:
            return await reply_text_v2(
                interaction, "Неизвестное действие.", kind='err')

        app["status"] = status_map[action]
        app["reviewed_by"] = str(interaction.user)
        if not app.get("timestamp"):
            app["timestamp"] = app.get("submitted_at")

        granted = None
        grant_note = ""
        if action == "approve":
            from services.staff_roles import grant_staff_role, role_hint
            try:
                gid = int(app.get("guild_id") or 0)
            except (TypeError, ValueError):
                gid = 0
            guild = (interaction.client.get_guild(gid) if gid else None) or interaction.guild
            res = await grant_staff_role(guild, app.get("user_id"), app.get("role"))
            granted = res.get("role_name")
            if granted:
                app["granted_role"] = granted
            else:
                grant_note = role_hint(res)
        elif action == "blacklist":
            try:
                gid = int(app.get("guild_id") or 0)
            except (TypeError, ValueError):
                gid = 0
            add_to_blacklist(
                app.get("user_id"),
                by=str(interaction.user),
                role=app.get("role") or '',
                guild_id=gid or (interaction.guild.id if interaction.guild else None),
            )
            app["blacklisted"] = True
        save_apps(apps)

        pos = position_label(app.get("role"))
        dm_ok = False
        try:
            user = await interaction.client.fetch_user(int(app["user_id"]))
            if action == "approve":
                emb = discord.Embed(
                    title="Заявка одобрена",
                    description=f"Заявка на **{pos}** одобрена.",
                    color=0x2ECC71)
            elif action == "blacklist":
                emb = discord.Embed(
                    title="Чёрный список набора",
                    description=(
                        f"Заявка на **{pos}** отклонена.\n"
                        f"Вы в чёрном списке ветки **{pos}** — "
                        "повторно на эту должность нельзя.\n"
                        "Другие должности по-прежнему открыты."
                    ),
                    color=0x2C2F33)
            else:
                emb = discord.Embed(
                    title="Заявка отклонена",
                    description=f"Заявка на **{pos}** отклонена.",
                    color=0xE74C3C)
            if granted:
                emb.add_field(name="Роль", value=granted, inline=True)
            emb.set_footer(text="/my-application")
            emb.timestamp = datetime.now(timezone.utc)
            await send_dm_v2(user, emb)
            dm_ok = True
        except Exception as e:
            log.info(f"[STAFF] DM заявителю не доставлен: {e}")

        try:
            src = interaction.message
            verdict = {
                "approve": "одобрена",
                "reject": "отклонена",
                "blacklist": "чёрный список",
            }[action]
            accent = {
                "approve": 0x2ECC71,
                "reject": 0xE74C3C,
                "blacklist": 0x2C2F33,
            }[action]
            who = interaction.user.display_name
            when = datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M')
            note = f"{who} · {when}"
            if granted:
                note += f" · {granted}"
            if V2_AVAILABLE:
                done = notice_layout_view(
                    title=f'{pos} — {verdict}',
                    body=(f"<@{app.get('user_id')}>\n{note}"),
                    footer='',
                    accent=accent,
                    brand='HAKUMO',
                    timeout=None)
                if done is not None:
                    await src.edit(view=done, embed=None, content=src.content)
                else:
                    await src.edit(view=None)
            elif src and src.embeds:
                e0 = discord.Embed.from_dict(src.embeds[0].to_dict())
                e0.color = accent
                field_name = {
                    "approve": "Одобрена",
                    "reject": "Отклонена",
                    "blacklist": "Чёрный список",
                }[action]
                e0.add_field(name=field_name, value=note, inline=False)
                await src.edit(embed=e0, view=None)
            else:
                await src.edit(view=None)
        except Exception as _ex:
            log.debug("_review(): подавлено: %s", _ex)

        verdict = {
            "approve": "одобрена",
            "reject": "отклонена",
            "blacklist": "в чёрном списке",
        }[action]
        role_line = ""
        if action == "approve":
            role_line = (f" Роль: **{granted}**."
                         if granted else f" Роль не выдана: {grant_note}.")
        elif action == "blacklist":
            role_line = f" Только ветка **{pos}**. Остальные открыты."
        kind = {
            "approve": "ok",
            "reject": "warn",
            "blacklist": "err",
        }[action]
        await respond_v2(
            interaction, kind=kind,
            title=verdict.capitalize(),
            body=(
                f"**{pos}** — **{verdict}**.{role_line}\n"
                f"ЛС: {'отправлено' if dm_ok else 'не доставлено'}"
            ),
            ephemeral=True)

    @discord.ui.select(
        placeholder="",
        options=[
            discord.SelectOption(label="› Принять", value="approve"),
            discord.SelectOption(label="› Отклонить", value="reject"),
            discord.SelectOption(label="› Чёрный список", value="blacklist"),
        ],
        custom_id="staff_review_select_v1", min_values=1, max_values=1)
    async def review_select(self, interaction: discord.Interaction,
                            select: discord.ui.Select):
        await self._review(interaction, select.values[0])


class StaffReviewButtonsView(discord.ui.View):
    """Старые кнопки — живут на заявках до перехода на select."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Одобрить", style=discord.ButtonStyle.success,
                       custom_id="staff_review_approve_v1")
    async def approve_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await StaffReviewView()._review(interaction, "approve")

    @discord.ui.button(label="Отклонить", style=discord.ButtonStyle.danger,
                       custom_id="staff_review_reject_v1")
    async def reject_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await StaffReviewView()._review(interaction, "reject")

    @discord.ui.button(label="Чёрный список", style=discord.ButtonStyle.secondary,
                       custom_id="staff_review_blacklist_v1")
    async def blacklist_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await StaffReviewView()._review(interaction, "blacklist")


class StaffApplyView(discord.ui.LayoutView):
    """Меню набора — баннер + select (без дубля заголовка)."""

    def __init__(self, *, banner_filename: str = 'hakumo_staff_banner_v16.png'):
        super().__init__(timeout=None)
        from services.v2_layouts import (
            V2_AVAILABLE, build_staff_menu_items, SHOW_MENU_BANNER)
        sel = RoleSelect()
        show = bool(SHOW_MENU_BANNER and banner_filename)
        if V2_AVAILABLE:
            items = build_staff_menu_items(
                banner_filename=banner_filename or '',
                body=None,
                role_select=sel,
                show_banner=show,
            )
            if items:
                for it in items:
                    self.add_item(it)
                return
        row = discord.ui.ActionRow()
        row.add_item(sel)
        self.add_item(row)


WEBHOOK_NAME = 'Наборы Hakumo'
HOOK_USERNAME = 'Наборы'


async def _channel_webhook(channel):
    """Найти/создать вебхук бота для V2-публикации."""
    fetch = getattr(channel, 'webhooks', None)
    if fetch is None:
        return None
    try:
        hooks = await fetch()
    except Exception as _ex:
        log.debug('staff: webhooks(%s): %s', channel, _ex)
        return None
    me_id = None
    try:
        me_id = channel.guild.me.id
    except Exception as _ex:
        log.debug('staff: guild.me: %s', _ex)
    for h in hooks or ():
        try:
            if me_id is None or h.user is None or h.user.id == me_id:
                return h
        except Exception as _ex:
            log.debug('staff: skip webhook: %s', _ex)
    create = getattr(channel, 'create_webhook', None)
    if create is None:
        return None
    try:
        return await create(name=WEBHOOK_NAME)
    except Exception as _ex:
        log.debug('staff: create_webhook: %s', _ex)
        return None


def _hook_avatar(guild):
    try:
        return guild.icon.url if guild.icon else None
    except Exception:
        return None


async def _send_staff_card(channel, *, content=None, view=None):
    """Карточка заявки V2 (webhook или бот).

    Components V2 запрещает поле content вместе с LayoutView — пинги
    куратора/юзера либо в теле карточки, либо отдельным сообщением.
    """
    allowed = discord.AllowedMentions(roles=True, users=True)
    # отдельный пинг (чтобы Discord реально уведомил роль/юзера)
    if content:
        try:
            await channel.send(content, allowed_mentions=allowed)
        except Exception as _ex:
            log.debug('staff: ping before card: %s', _ex)
    hook = await _channel_webhook(channel)
    if hook is not None:
        try:
            return await hook.send(
                view=view, wait=True,
                username=HOOK_USERNAME,
                avatar_url=_hook_avatar(getattr(channel, 'guild', None)))
        except Exception as _ex:
            log.debug('staff: card webhook failed: %s', _ex)
    return await channel.send(view=view)


async def publish_staff_menu(channel, *, banner_bio=None, banner_name=None):
    """Опубликовать меню набора через webhook V2 (баннер + select)."""
    if channel is None:
        return False, 'Канал не найден'
    fname = banner_name or 'hakumo_staff_banner_v16.png'
    view = StaffApplyView(banner_filename=fname)
    file = None
    if banner_bio is not None:
        try:
            banner_bio.seek(0)
        except Exception:
            pass
        file = discord.File(banner_bio, filename=fname)
    avatar = _hook_avatar(getattr(channel, 'guild', None))
    hook = await _channel_webhook(channel)
    msg = None
    used_hook = None
    if hook is not None:
        used_hook = hook
        try:
            kwargs = dict(
                view=view, wait=True,
                username=HOOK_USERNAME, avatar_url=avatar)
            if file is not None:
                kwargs['file'] = file
            msg = await hook.send(**kwargs)
        except Exception as _ex:
            log.debug('staff: menu webhook failed: %s', _ex)
            msg = None
            used_hook = None
            if banner_bio is not None:
                try:
                    banner_bio.seek(0)
                    file = discord.File(banner_bio, filename=fname)
                except Exception:
                    file = None
    if msg is None:
        try:
            if file is not None:
                msg = await channel.send(file=file, view=view)
            else:
                msg = await channel.send(view=view)
        except (discord.Forbidden, discord.HTTPException) as _ex:
            return False, f'Не могу писать в канал: {_ex}'
    how = 'вебхуком' if used_hook is not None else 'от бота'
    return True, f'Опубликовано в {channel.mention} ({how})'


# ═══════════════════════════════════════════════════════════════════
# Cog
# ═══════════════════════════════════════════════════════════════════

class StaffApply(commands.Cog):
    """Набор в команду"""

    def __init__(self, bot):
        self.bot = bot
        self._menu_task_started = False

    @app_commands.command(name="my-application",
                          description="Статус моей заявки в команду")
    async def my_application(self, interaction: discord.Interaction):
        apps = load_apps()
        uid = str(interaction.user.id)
        mine = [a for a in apps.values() if str(a.get("user_id")) == uid]
        bl_kinds = blacklisted_kinds(uid)
        if not mine and not bl_kinds:
            from services.v2_layouts import reply_text_v2
            return await reply_text_v2(
                interaction,
                "Заявок пока нет. Подать можно через меню набора.",
                kind='info', title='Заявки')
        from services.staff_roles import position_label
        body_parts = []
        if mine:
            mine.sort(
                key=lambda a: a.get("timestamp") or a.get("submitted_at") or "",
                reverse=True)
            a = mine[0]
            status_map = {"pending": "На рассмотрении",
                          "approved": "Одобрена",
                          "rejected": "Отклонена",
                          "blacklisted": "Чёрный список"}
            st = status_map.get(a.get("status"), a.get("status", "?"))
            pos = position_label(a.get('role'))
            body_parts.append(
                f"**{st}** · **{pos}**\n"
                f"Подана: {(a.get('timestamp') or a.get('submitted_at') or '?')[:10]}")
            if a.get("reviewed_by"):
                body_parts.append(f"Рассмотрел: **{a['reviewed_by']}**")
            if a.get("review_note"):
                body_parts.append(f"Комментарий: {a['review_note']}")
            kind = {
                "pending": "warn",
                "approved": "ok",
                "rejected": "err",
                "blacklisted": "err",
            }.get(a.get("status"), "info")
        else:
            kind = "err"
        if bl_kinds:
            labels = ", ".join(f"**{position_label(k)}**" for k in bl_kinds)
            body_parts.append(
                f"Чёрный список веток: {labels}.\n"
                "Другие должности открыты.")
        from services.v2_layouts import respond_v2
        await respond_v2(
            interaction, kind=kind, title='Моя заявка',
            body='\n'.join(body_parts), ephemeral=True)

    async def _ensure_staff_menu(self):
        """Один раз: меню набора в канал наборов (без slash-команды)."""
        try:
            await self.bot.wait_until_ready()
        except Exception:
            return
        try:
            from services.menu_emojis import ensure_menu_emojis
            await ensure_menu_emojis(self.bot)
        except Exception as _ex:
            log.debug('staff ensure emojis: %s', _ex)
        from services.menu_banners import menu_banner_file
        state = _load_menu_state()
        for guild in list(self.bot.guilds):
            ch = menu_channel(guild)
            if ch is None:
                continue
            key = f'{guild.id}:{ch.id}'
            prev = state.get(key) or {}
            # уже актуальная версия — не спамим при каждом рестарте
            if int(prev.get('version') or 0) >= MENU_POST_VERSION:
                continue
            try:
                bio, fname = await self.bot.loop.run_in_executor(
                    None, lambda: menu_banner_file('staff'))
                ok, detail = await publish_staff_menu(
                    ch, banner_bio=bio, banner_name=fname)
                if ok:
                    state[key] = {
                        'channel_id': ch.id,
                        'guild_id': guild.id,
                        'version': MENU_POST_VERSION,
                        'at': datetime.now(timezone.utc).isoformat(),
                    }
                    _save_menu_state(state)
                    log.info('STAFF: меню набора → #%s (%s)', ch.id, detail)
                else:
                    log.warning('STAFF: меню не ушло в #%s: %s', ch.id, detail)
            except Exception as _ex:
                log.warning('STAFF: ensure menu guild=%s: %s', guild.id, _ex)

    @commands.Cog.listener()
    async def on_ready(self):
        try:
            from services.menu_emojis import schedule_ensure_menu_emojis
            schedule_ensure_menu_emojis(self.bot)
        except Exception as _ex:
            log.debug('staff emojis: %s', _ex)
        self.bot.add_view(StaffApplyView())
        self.bot.add_view(StaffReviewView())
        self.bot.add_view(StaffReviewButtonsView())
        self.bot.add_view(StaffAppCardView(title='Заявка', body='…'))
        if not self._menu_task_started:
            self._menu_task_started = True
            try:
                import asyncio
                asyncio.get_running_loop().create_task(self._ensure_staff_menu())
            except Exception as _ex:
                log.debug('staff menu task: %s', _ex)


async def setup(bot):
    await bot.add_cog(StaffApply(bot))
    log.info("StaffApply загружен")
