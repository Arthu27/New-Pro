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


def apply_target(role_name: str, guild):
    """Куда отправить новую заявку + тег куратора СВОЕЙ ветки.

    Порядок канала:
      1) своя ветка должности (helper/moderator/event/broadcaster)
      2) общий apply_channel / APPLY_CHANNEL_ID (канал заявок)
      3) комната апелляций (legacy-фолбек)
    """
    from services.staff_roles import normalize_position, setting
    if not guild:
        return None, ''
    kind = normalize_position(role_name) or 'moderator'
    tag = _curator_ping(guild, role_name)
    # 1) своя ветка
    ch = _channel_for_kind(guild, kind)
    if ch is not None:
        return ch, tag
    # 2) общий канал заявок
    common = setting(guild.id, 'apply_channel', APPLY_CHANNEL_ID)
    if common:
        getter = getattr(guild, 'get_channel', None)
        ch = getter(int(common)) if callable(getter) else None
        if ch is not None:
            return ch, tag
    # 3) legacy: комната апелляций
    room = _apply_room(guild)
    if room is not None:
        return room, tag
    return None, tag


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
    os.makedirs("data", exist_ok=True)
    if os.path.exists(BLACKLIST_FILE):
        try:
            with open(BLACKLIST_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError) as _ex:
            log.debug('staff blacklist load: %s', _ex)
    return {}


def save_blacklist(data):
    os.makedirs("data", exist_ok=True)
    with open(BLACKLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def is_blacklisted(user_id) -> bool:
    return str(user_id) in load_blacklist()


def add_to_blacklist(user_id, *, by: str = '', role: str = '',
                     guild_id=None, reason: str = '') -> dict:
    """Добавить в ЧС набора. Возвращает запись."""
    bl = load_blacklist()
    entry = {
        'user_id': str(user_id),
        'by': str(by or ''),
        'role': str(role or ''),
        'guild_id': int(guild_id) if guild_id else None,
        'reason': str(reason or ''),
        'at': datetime.now(timezone.utc).isoformat(),
    }
    bl[str(user_id)] = entry
    save_blacklist(bl)
    return entry


def remove_from_blacklist(user_id) -> bool:
    bl = load_blacklist()
    if str(user_id) not in bl:
        return False
    del bl[str(user_id)]
    save_blacklist(bl)
    return True


# ═══════════════════════════════════════════════════════════════════
# Модальное окно заявки
# ═══════════════════════════════════════════════════════════════════

class StaffApplyModal(discord.ui.Modal, title="Заявка в команду"):
    age = discord.ui.TextInput(
        label="Возраст",
        placeholder="например: 18",
        max_length=3
    )
    experience = discord.ui.TextInput(
        label="Опыт модерации",
        placeholder="Серверы и должности",
        style=discord.TextStyle.paragraph,
        max_length=500
    )
    reason = discord.ui.TextInput(
        label="Почему Hakumo?",
        placeholder="Что привлекает на сервере",
        style=discord.TextStyle.paragraph,
        max_length=500
    )
    activity = discord.ui.TextInput(
        label="Активность",
        placeholder="Часов в день онлайн",
        max_length=100
    )

    def __init__(self, role_name: str):
        super().__init__()
        self.role_name = role_name

    async def on_submit(self, interaction: discord.Interaction):
        # defer сразу: доставка карточки кураторам может занять >3с
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception as _dex:
            log.debug('staff apply defer: %s', _dex)
        from services.staff_roles import normalize_position, position_label
        user_id = str(interaction.user.id)
        if is_blacklisted(user_id):
            try:
                from services.v2_layouts import respond_v2
                await respond_v2(
                    interaction, kind='err', title='Чёрный список',
                    body='Вы в чёрном списке набора — подать заявку нельзя.',
                    ephemeral=True)
            except Exception:
                try:
                    await interaction.followup.send(
                        'Вы в чёрном списке набора — подать заявку нельзя.',
                        ephemeral=True)
                except Exception as _fx:
                    log.debug('staff apply bl deny: %s', _fx)
            return
        apps = load_apps()
        submitted_ts = datetime.now(timezone.utc).isoformat()
        kind = normalize_position(self.role_name) or 'moderator'
        role_label = position_label(kind)
        apps[user_id] = {
            "user_id": user_id,
            "username": str(interaction.user),
            "display_name": interaction.user.display_name,
            "avatar": str(interaction.user.display_avatar.url) if interaction.user.display_avatar else None,
            "role": role_label,
            "age": str(self.age),
            "experience": str(self.experience),
            "reason": str(self.reason),
            "activity": str(self.activity),
            "status": "pending",
            "submitted_at": submitted_ts,
            "timestamp": submitted_ts,
            "message_id": None,
            "guild_id": interaction.guild.id if interaction.guild else None,
        }

        delivered = False
        if interaction.guild:
            ch, tag = apply_target(role_label, interaction.guild)
            if ch:
                body = (
                    f"{interaction.user.mention} · `{user_id}`\n\n"
                    f"**Возраст** · {str(self.age)[:80] or '—'}\n"
                    f"**Активность** · {str(self.activity)[:120] or '—'}\n\n"
                    f"**Опыт**\n{str(self.experience)[:1000] or '—'}\n\n"
                    f"**Почему Hakumo**\n{str(self.reason)[:1000] or '—'}"
                )
                try:
                    card = StaffAppCardView(
                        title=role_label,
                        body=body,
                    )
                    msg = await _send_staff_card(
                        ch, content=tag or None, view=card)
                    apps[user_id]["message_id"] = str(msg.id)
                    apps[user_id]["curator_tag"] = tag or None
                    delivered = True
                except (discord.Forbidden, discord.HTTPException) as _ex:
                    log.warning("STAFF: карточка %s не ушла в %s: %s",
                                user_id, getattr(ch, 'name', '?'), _ex)
                    apps[user_id]["delivery"] = "failed"
            else:
                apps[user_id]["delivery"] = "no_channel"
                log.warning("STAFF: заявка %s сохранена, канал не настроен",
                            user_id)

        save_apps(apps)
        body = (
            f"Заявка на **{role_label}** отправлена.\n"
            f"Статус: `/my-application`"
        )
        if not delivered:
            body += (
                "\n\nСохранено, но персонал не уведомлён "
                "(не настроен канал заявок)."
            )
        try:
            from services.v2_layouts import respond_v2
            await respond_v2(
                interaction, kind='ok', title='Отправлено', body=body,
                ephemeral=True)
        except Exception as _vx:
            log.debug('staff apply confirm v2: %s', _vx)
            try:
                await interaction.followup.send(body, ephemeral=True)
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
            placeholder="",
            options=options,
            custom_id="staff_role_select_v2"
        )

    async def callback(self, interaction: discord.Interaction):
        if is_blacklisted(interaction.user.id):
            from services.v2_layouts import reply_text_v2
            return await reply_text_v2(
                interaction,
                'Вы в чёрном списке набора — подать заявку нельзя.',
                kind='err', title='Чёрный список')
        role_name = self.values[0]
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
    """Карточка заявки куратору — V2, чёрный блок, заголовок = должность (EN)."""

    def __init__(self, *, title: str, body: str, footer: str = ''):
        super().__init__(timeout=None)
        from services.v2_layouts import V2_AVAILABLE, black_container
        from discord import SeparatorSpacing
        sel = StaffReviewSelect()
        if V2_AVAILABLE:
            from discord import ui as dui
            children = [
                dui.TextDisplay(f'# {title}'[:500]),
                dui.Separator(spacing=SeparatorSpacing.large),
                dui.TextDisplay(str(body)[:3500]),
            ]
            if footer:
                children.append(dui.TextDisplay(f'-# {footer}'[:400]))
            row = dui.ActionRow()
            row.add_item(sel)
            children.append(row)
            self.add_item(black_container(*children))  # accent чёрный
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
                        "Вы добавлены в чёрный список набора — "
                        "повторно подать нельзя."
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
            role_line = " Повторные заявки заблокированы."
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
    """Карточка заявки через webhook V2, иначе от бота."""
    allowed = discord.AllowedMentions(roles=True)
    hook = await _channel_webhook(channel)
    if hook is not None:
        try:
            return await hook.send(
                content=content, view=view, wait=True,
                username=HOOK_USERNAME,
                avatar_url=_hook_avatar(getattr(channel, 'guild', None)),
                allowed_mentions=allowed)
        except Exception as _ex:
            log.debug('staff: card webhook failed: %s', _ex)
    return await channel.send(
        content=content, view=view, allowed_mentions=allowed)


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

    @app_commands.command(name="staff-panel",
                          description="Опубликовать меню набора в этот канал")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def staff_panel(self, interaction: discord.Interaction):
        """Webhook V2: баннер + select должности."""
        await interaction.response.defer(ephemeral=True)
        try:
            from services.system_readiness import readiness_block, staff_apply_missing
            block = readiness_block('Заявки в команду', staff_apply_missing(interaction.guild))
            if block:
                from services.v2_layouts import reply_text_v2
                await reply_text_v2(
                    interaction, block, kind='warn', title='Настройки')
                return
        except Exception as _ex:
            log.debug('staff-panel readiness: %s', _ex)

        from services.menu_banners import menu_banner_file
        bio, fname = await interaction.client.loop.run_in_executor(
            None, lambda: menu_banner_file('staff'))
        target = menu_channel(interaction.guild) or interaction.channel
        ok, detail = await publish_staff_menu(
            target, banner_bio=bio, banner_name=fname)
        try:
            from services.v2_layouts import respond_v2
            await respond_v2(
                interaction, kind='ok' if ok else 'err',
                title='Готово' if ok else 'Ошибка',
                body=detail, ephemeral=True)
        except Exception:
            await interaction.followup.send(detail, ephemeral=True)

    @app_commands.command(name="my-application",
                          description="Статус моей заявки в команду")
    async def my_application(self, interaction: discord.Interaction):
        apps = load_apps()
        uid = str(interaction.user.id)
        mine = [a for a in apps.values() if str(a.get("user_id")) == uid]
        if not mine:
            from services.v2_layouts import reply_text_v2
            return await reply_text_v2(
                interaction,
                "Заявок пока нет. Подать можно через меню набора.",
                kind='info', title='Заявки')
        from services.staff_roles import position_label
        mine.sort(key=lambda a: a.get("timestamp") or a.get("submitted_at") or "", reverse=True)
        a = mine[0]
        status_map = {"pending": "На рассмотрении",
                      "approved": "Одобрена",
                      "rejected": "Отклонена",
                      "blacklisted": "Чёрный список"}
        st = status_map.get(a.get("status"), a.get("status", "?"))
        kind = {
            "pending": "warn",
            "approved": "ok",
            "rejected": "err",
            "blacklisted": "err",
        }.get(a.get("status"), "info")
        pos = position_label(a.get('role'))
        body = (f"**{st}** · **{pos}**\n"
                f"Подана: {(a.get('timestamp') or a.get('submitted_at') or '?')[:10]}")
        if a.get("status") == "blacklisted" or is_blacklisted(uid):
            body += "\nПовторно подать заявку нельзя."
        if a.get("reviewed_by"):
            body += f"\nРассмотрел: **{a['reviewed_by']}**"
        if a.get("review_note"):
            body += f"\nКомментарий: {a['review_note']}"
        from services.v2_layouts import respond_v2
        await respond_v2(
            interaction, kind=kind, title='Моя заявка', body=body,
            ephemeral=True)

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


async def setup(bot):
    await bot.add_cog(StaffApply(bot))
    log.info("StaffApply загружен")
