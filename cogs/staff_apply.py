"""
Staff Apply — Набор в команду сервера
Select menu для выбора роли + модальное окно заявки
Тёмная тема, без эмодзи, русский язык
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
APPS_FILE = "data/staff_apps.json"


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
    """Комната, куда идёт ВСЁ: апелляции и заявки в команду.

    Маршрут «Комната апелляции» (1544483947705008188) — единая точка
    «всё сюда, кроме логов» (владелец 2026-09-06). Синхронная: каналы
    берём из кэша, без fetch — не нашли, значит комнаты нет на сервере.
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
      2) единая комната заявок/апелляций (если своей нет)
      3) общий apply_channel / APPLY_CHANNEL_ID
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
    # 2) общая комната
    room = _apply_room(guild)
    if room is not None:
        return room, tag
    # 3) общий канал заявок
    common = setting(guild.id, 'apply_channel', APPLY_CHANNEL_ID)
    ch = guild.get_channel(common) if common else None
    return ch, tag


def load_apps():
    os.makedirs("data", exist_ok=True)
    if os.path.exists(APPS_FILE):
        with open(APPS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_apps(data):
    with open(APPS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════════
# Модальное окно заявки
# ═══════════════════════════════════════════════════════════════════

class StaffApplyModal(discord.ui.Modal, title="Заявка в команду"):
    age = discord.ui.TextInput(
        label="Ваш возраст",
        placeholder="Например: 18",
        max_length=3
    )
    experience = discord.ui.TextInput(
        label="Опыт модерации",
        placeholder="Укажите сервер и вашу должность",
        style=discord.TextStyle.paragraph,
        max_length=500
    )
    reason = discord.ui.TextInput(
        label="Почему вы выбираете нас?",
        placeholder="Расскажите, что вас привлекает в нашем сервере",
        style=discord.TextStyle.paragraph,
        max_length=500
    )
    activity = discord.ui.TextInput(
        label="Ваша активность",
        placeholder="Сколько часов в день вы онлайн?",
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
        # Сохраняем заявку
        apps = load_apps()
        user_id = str(interaction.user.id)
        submitted_ts = datetime.now(timezone.utc).isoformat()
        apps[user_id] = {
            "user_id": user_id,
            "username": str(interaction.user),
            "display_name": interaction.user.display_name,
            "avatar": str(interaction.user.display_avatar.url) if interaction.user.display_avatar else None,
            "role": self.role_name,
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

        # Уведомление в ветку заявки: хелперы — кураторам хелперов,
        # модераторы — кураторам модераторов (свой канал + тег в карточке)
        delivered = False
        if interaction.guild:
            ch, tag = apply_target(self.role_name, interaction.guild)
            if ch:
                # Карточка заявки — Components V2 (без footer-стикера / мусора)
                role_label = self.role_name
                body = (
                    f"**Пользователь:** {interaction.user.mention}\n"
                    f"**ID:** `{user_id}`\n"
                    f"**Должность:** **{role_label}**\n\n"
                    f"**Возраст**\n{str(self.age)[:200] or '—'}\n\n"
                    f"**Активность**\n{str(self.activity)[:200] or '—'}\n\n"
                    f"**Опыт**\n{str(self.experience)[:1000] or '—'}\n\n"
                    f"**Почему к нам**\n{str(self.reason)[:1000] or '—'}"
                )
                try:
                    card = StaffAppCardView(
                        title=f'Заявка — {role_label}',
                        body=body,
                        footer='Hakumo · решение — только куратор этой ветки',
                    )
                    msg = await ch.send(
                        content=tag or None,
                        view=card,
                        allowed_mentions=discord.AllowedMentions(roles=True))
                    apps[user_id]["message_id"] = str(msg.id)
                    apps[user_id]["curator_tag"] = tag or None
                    delivered = True
                except (discord.Forbidden, discord.HTTPException) as _ex:
                    log.warning("STAFF: карточка заявки %s не ушла в %s: %s",
                                user_id, getattr(ch, 'name', '?'), _ex)
                    apps[user_id]["delivery"] = "failed"
            else:
                # ТИХАЯ ПОТЕРЯ ЗАЯВКИ — запрещена (жалоба владельца 2026-09-05
                # «таблица опять не отправляется»): раньше канал не находился
                # и карточка просто не отправлялась, заявитель ничего не знал.
                apps[user_id]["delivery"] = "no_channel"
                log.warning("STAFF: заявка %s сохранена, но канал заявок не "
                            "настроен (панель → Каналы и маршруты)", user_id)

        save_apps(apps)
        # Подтверждение пользователю — Components V2 (после доставки, чтобы
        # честно сказать, если персонал не уведомлён).
        body = (
            f"Ваша заявка на роль **{self.role_name}** успешно отправлена.\n"
            "Ожидайте рассмотрения администрацией.\n"
            "Статус можно проверить командой `/my-application`.\n\n"
            f"**Возраст:** {self.age}\n"
            f"**Активность:** {self.activity}\n"
            f"**Опыт:** {str(self.experience)[:200]}\n"
            f"**Причина:** {str(self.reason)[:200]}"
        )
        if not delivered:
            body += (
                "\n\n⚠️ Заявка сохранена и видна администрации в панели "
                "«Заявки в команду», но уведомление персоналу не доставлено "
                "(не настроен канал заявок). Сообщи о себе администрации лично."
            )
        try:
            from services.v2_layouts import respond_v2
            await respond_v2(
                interaction, kind='ok', title='Заявка отправлена', body=body,
                ephemeral=True)
        except Exception as _vx:
            log.debug('staff apply confirm v2: %s', _vx)
            try:
                await interaction.followup.send(body, ephemeral=True)
            except Exception as _fx:
                log.debug('staff apply confirm text: %s', _fx)
        log.info(f"Заявка от {interaction.user} на роль {self.role_name}"
                 + ("" if delivered else " (без уведомления персонала)"))


# ═══════════════════════════════════════════════════════════════════
# Select menu — выбор роли
# ═══════════════════════════════════════════════════════════════════

class RoleSelect(discord.ui.Select):
    def __init__(self):
        # 4 ветки: Хелпер / Модератор / Event / Broadcaster.
        # Чат-контроль убран. Свои стикеры Hakumo.
        from services.menu_banners import select_label
        try:
            from services.menu_emojis import get_cached
            em_help = get_cached('helper')
            em_mod = get_cached('moderator')
            em_event = get_cached('elist') or get_cached('announce')
            em_bc = get_cached('announce') or get_cached('start')
        except Exception:
            em_help = em_mod = em_event = em_bc = None
        options = [
            discord.SelectOption(
                label=select_label('Хелпер'),
                value="Helper",
                description="Помощь участникам сервера",
                emoji=em_help or '⭐',
            ),
            discord.SelectOption(
                label=select_label('Модератор'),
                value="Moderator",
                description="Модерация сервера и участников",
                emoji=em_mod or '🛡️',
            ),
            discord.SelectOption(
                label=select_label('Event'),
                value="Event",
                description="Ивенты и Events-команда",
                emoji=em_event or '📅',
            ),
            discord.SelectOption(
                label=select_label('Broadcaster'),
                value="Broadcaster",
                description="Эфиры и трансляции",
                emoji=em_bc or '📡',
            ),
        ]
        super().__init__(
            placeholder="К кому хотите присоединиться?",
            options=options,
            custom_id="staff_role_select_v2"
        )

    async def callback(self, interaction: discord.Interaction):
        role_name = self.values[0]
        modal = StaffApplyModal(role_name=role_name)
        await interaction.response.send_modal(modal)


# ═══════════════════════════════════════════════════════════════════
# Рассмотрение заявки (persistent) — Select «Принять / Отклонить»
# ═══════════════════════════════════════════════════════════════════

class StaffReviewSelect(discord.ui.Select):
    """Select решения — внутри V2-карточки заявки."""

    def __init__(self):
        super().__init__(
            placeholder="Действие с заявкой",
            options=[
                discord.SelectOption(
                    label="Принять", value="approve",
                    description="Одобрить заявку и выдать роль"),
                discord.SelectOption(
                    label="Отклонить", value="reject",
                    description="Отклонить заявку"),
            ],
            custom_id="staff_review_select_v2",
            min_values=1, max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        await StaffReviewView()._review(interaction, self.values[0])


class StaffAppCardView(discord.ui.LayoutView):
    """Карточка заявки куратору — V2, без стикера/мусора в футере."""

    def __init__(self, *, title: str, body: str, footer: str = ''):
        super().__init__(timeout=None)
        from services.v2_layouts import V2_AVAILABLE, black_container
        from discord import SeparatorSpacing
        sel = StaffReviewSelect()
        if V2_AVAILABLE:
            from discord import ui as dui
            head = f'# {title}\n-# HAKUMO'
            children = [
                dui.TextDisplay(head[:500]),
                dui.Separator(spacing=SeparatorSpacing.large),
                dui.TextDisplay(str(body)[:3500]),
            ]
            if footer:
                children.append(dui.TextDisplay(f'-# {footer}'[:400]))
            row = dui.ActionRow()
            row.add_item(sel)
            children.append(row)
            self.add_item(black_container(*children, accent=0xC8922A))
            return
        row = discord.ui.ActionRow()
        row.add_item(sel)
        self.add_item(row)


class StaffReviewView(discord.ui.View):
    """Select под сообщением заявки: решение модератора + DM заявителю.

    Классический View — для старых карточек (embed) до перехода на V2.
    """

    def __init__(self):
        super().__init__(timeout=None)  # select добавлен декоратором ниже

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
                interaction,
                "Заявка не найдена (возможно, данные удалены).",
                kind='err')
        # Права: только куратор СВОЕЙ ветки (или администратор)
        position = app.get('role') or ''
        ok, deny = can_review_position(interaction.user, position)
        if not ok:
            return await reply_text_v2(
                interaction,
                deny or "Рассматривать эту заявку может только куратор своей ветки.",
                kind='err', title='Чужая ветка')
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        if app.get("status") != "pending":
            label = {"approved": "одобрена", "rejected": "отклонена"}.get(
                app.get("status"), app.get("status", "?"))
            return await reply_text_v2(
                interaction, f"Эта заявка уже {label}.", kind='warn')

        app["status"] = "approved" if action == "approve" else "rejected"
        app["reviewed_by"] = str(interaction.user)
        if not app.get("timestamp"):
            app["timestamp"] = app.get("submitted_at")

        # Одобрена → выдать роль по должности (Helper/Mod/Event/Broadcaster)
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
        save_apps(apps)

        # DM заявителю — V2 notice
        dm_ok = False
        try:
            user = await interaction.client.fetch_user(int(app["user_id"]))
            pos = position_label(app.get("role"))
            if action == "approve":
                emb = discord.Embed(
                    title="Заявка одобрена!",
                    description=(
                        f"Поздравляем! Ваша заявка на **{pos}** **одобрена**.\n"
                        "Администрация свяжется с вами в ближайшее время."),
                    color=0x2ECC71)
            else:
                emb = discord.Embed(
                    title="Заявка отклонена",
                    description=(
                        f"К сожалению, заявка на **{pos}** на этот раз "
                        "**отклонена**.\nВы можете подать её снова позже."),
                    color=0xE74C3C)
            emb.add_field(name="Должность", value=app.get("role", "—"), inline=True)
            emb.add_field(name="Рассмотрел", value=interaction.user.display_name, inline=True)
            if granted:
                emb.add_field(name="Выдана роль", value=granted, inline=True)
            emb.set_footer(text="Статус всегда можно проверить: /my-application")
            emb.timestamp = datetime.now(timezone.utc)
            await send_dm_v2(user, emb)
            dm_ok = True
        except Exception as e:
            log.info(f"[STAFF] DM заявителю не доставлен: {e}")

        # Отметить решение на исходном сообщении (V2 или legacy embed)
        try:
            src = interaction.message
            verdict = "одобрена" if action == "approve" else "отклонена"
            who = interaction.user.display_name
            when = datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M')
            note = f"Принял: {who} · {when}" if action == "approve" else f"Отклонил: {who} · {when}"
            if granted:
                note += f" · роль {granted}"
            if V2_AVAILABLE:
                done = notice_layout_view(
                    title=f'Заявка {verdict}',
                    body=(f"**Должность:** {app.get('role', '—')}\n"
                          f"**Заявитель:** <@{app.get('user_id')}>\n\n"
                          f"{note}"),
                    footer='Hakumo · набор',
                    accent=0x2ECC71 if action == 'approve' else 0xE74C3C,
                    brand='HAKUMO',
                    timeout=None)
                if done is not None:
                    await src.edit(view=done, embed=None, content=src.content)
                else:
                    await src.edit(view=None)
            elif src and src.embeds:
                e0 = discord.Embed.from_dict(src.embeds[0].to_dict())
                e0.color = 0x2ECC71 if action == "approve" else 0xE74C3C
                e0.add_field(
                    name="Решение: одобрена" if action == "approve" else "Решение: отклонена",
                    value=note,
                    inline=False)
                await src.edit(embed=e0, view=None)
            else:
                await src.edit(view=None)
        except Exception as _ex:
            log.debug("_review(): подавлено: %s", _ex)

        verdict = "одобрена" if action == "approve" else "отклонена"
        role_line = ""
        if action == "approve":
            role_line = (f" Роль выдана: **{granted}**."
                         if granted else f" Роль НЕ выдана: {grant_note}.")
        await respond_v2(
            interaction, kind='ok' if action == 'approve' else 'warn',
            title=f'Заявка {verdict}',
            body=(
                f"Заявка на **{position_label(app.get('role'))}** **{verdict}**."
                f"{role_line}\n"
                f"Уведомление пользователю: "
                f"{'отправлено в ЛС' if dm_ok else 'НЕ доставлено (у пользователя закрыты ЛС)'}"
            ),
            ephemeral=True)

    @discord.ui.select(
        placeholder="Действие с заявкой",
        options=[
            discord.SelectOption(label="Принять", value="approve",
                                 description="Одобрить заявку и выдать роль"),
            discord.SelectOption(label="Отклонить", value="reject",
                                 description="Отклонить заявку"),
        ],
        custom_id="staff_review_select_v1", min_values=1, max_values=1)
    async def review_select(self, interaction: discord.Interaction,
                            select: discord.ui.Select):
        await self._review(interaction, select.values[0])


class StaffReviewButtonsView(discord.ui.View):
    """Старые кнопки: остаются живыми на заявках, отправленных до
    перехода на select (persistent custom_id совпадает)."""

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


class StaffApplyView(discord.ui.LayoutView):
    """Панель набора — Components V2 (чистый баннер + select роли)."""

    def __init__(self, *, banner_filename: str = 'hakumo_staff_banner_v16.png'):
        super().__init__(timeout=None)
        from services.v2_layouts import (
            V2_AVAILABLE, build_staff_menu_items, SHOW_MENU_BANNER)
        sel = RoleSelect()
        body = (
            'Мы ищем людей, **готовых внести свой вклад** и помочь сделать '
            'сообщество лучше. Независимо от опыта — отправьте заявку и '
            'станьте частью команды.\n'
            'Статус: `/my-application`.')
        show = bool(SHOW_MENU_BANNER and banner_filename)
        if V2_AVAILABLE:
            items = build_staff_menu_items(
                banner_filename=banner_filename or '',
                body=body,
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


# ═══════════════════════════════════════════════════════════════════
# Cog
# ═══════════════════════════════════════════════════════════════════

class StaffApply(commands.Cog):
    """Набор в команду сервера"""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="staff-panel",
                          description="Опубликовать меню набора в этот канал")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def staff_panel(self, interaction: discord.Interaction):
        """Просто скинуть V2-меню набора (баннер + select) в текущий канал."""
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

        # Чистый фирменный баннер (без AI-мусора staff.jpg) + V2 LayoutView
        from services.menu_banners import menu_banner_file
        bio, fname = await interaction.client.loop.run_in_executor(
            None, lambda: menu_banner_file('staff'))
        file = discord.File(bio, filename=fname)
        view = StaffApplyView(banner_filename=fname)
        await interaction.channel.send(file=file, view=view)
        try:
            from services.v2_layouts import respond_v2
            await respond_v2(
                interaction, kind='ok', title='Готово',
                body='Меню набора опубликовано в этом канале.',
                ephemeral=True)
        except Exception:
            await interaction.followup.send(
                'Меню набора опубликовано.', ephemeral=True)

    @app_commands.command(name="my-application", description="Проверить статус моей заявки в персонал")
    async def my_application(self, interaction: discord.Interaction):
        """Пользователь видит, где его заявка: на рассмотрении / одобрена / отклонена."""
        apps = load_apps()
        uid = str(interaction.user.id)
        mine = [a for a in apps.values() if str(a.get("user_id")) == uid]
        if not mine:
            from services.v2_layouts import reply_text_v2
            return await reply_text_v2(
                interaction,
                "У вас пока нет заявок. Подать можно через панель набора в команду сервера.",
                kind='info', title='Заявки')
        mine.sort(key=lambda a: a.get("timestamp") or a.get("submitted_at") or "", reverse=True)
        a = mine[0]
        status_map = {"pending": "На рассмотрении",
                      "approved": "Одобрена",
                      "rejected": "Отклонена"}
        st = status_map.get(a.get("status"), a.get("status", "?"))
        kind = {"pending": "warn", "approved": "ok", "rejected": "err"}.get(
            a.get("status"), "info")
        total = len(mine)
        body = (f"Статус: **{st}**\n"
                f"Должность: **{a.get('role', '—')}**\n"
                f"Подана: {(a.get('timestamp') or a.get('submitted_at') or '?')[:10]}\n")
        if total > 1:
            body += f"Всего заявок: {total} (показана последняя)\n"
        if a.get("reviewed_by"):
            body += f"Рассмотрел: **{a['reviewed_by']}**\n"
        if a.get("review_note"):
            body += f"Комментарий: {a['review_note']}\n"
        body += "\nРешение также приходит в личные сообщения."
        from services.v2_layouts import respond_v2
        await respond_v2(
            interaction, kind=kind, title='Моя заявка в команду', body=body,
            ephemeral=True)

    @commands.Cog.listener()
    async def on_ready(self):
        # Регистрируем persistent views
        self.bot.add_view(StaffApplyView())
        self.bot.add_view(StaffReviewView())
        self.bot.add_view(StaffReviewButtonsView())  # старые заявки с кнопками
        # V2-карточки заявок (select staff_review_select_v2)
        self.bot.add_view(StaffAppCardView(
            title='Заявка', body='…', footer=''))


async def setup(bot):
    await bot.add_cog(StaffApply(bot))
    log.info("StaffApply загружен")
