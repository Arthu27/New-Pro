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


def apply_target(role_name: str, guild):
    """Куда отправить новую заявку: своя ветка на должность + кого позвать.

    Хелперам и модераторам — отдельные каналы (STAFF_HELPER_CHANNEL_ID /
    STAFF_MODERATOR_CHANNEL_ID), каждому своему куратору; кураторов бот
    пингует ролью (STAFF_*_CURATOR_ROLE_ID). Запасной канал — общий
    APPLY_CHANNEL_ID. Возвращает (channel, content) или (None, '')."""
    from services.staff_roles import normalize_position, setting
    if not guild:
        return None, ''
    kind = normalize_position(role_name) or 'moderator'
    if kind == 'helper':
        cid = setting(guild.id, 'helper_channel', Config.STAFF_HELPER_CHANNEL_ID)
        cur = setting(guild.id, 'helper_curator_role',
                      Config.STAFF_HELPER_CURATOR_ROLE_ID)
    else:
        cid = setting(guild.id, 'moderator_channel',
                      Config.STAFF_MODERATOR_CHANNEL_ID)
        cur = setting(guild.id, 'moderator_curator_role',
                      Config.STAFF_MODERATOR_CURATOR_ROLE_ID)
    ch = guild.get_channel(cid) if cid else None
    if ch is None:
        # общий канал: настройка панели главнее .env
        common = setting(guild.id, 'apply_channel', APPLY_CHANNEL_ID)
        ch = guild.get_channel(common) if common else None
    content = f'<@&{cur}>' if cur else ''
    return ch, content


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

        # Подтверждение пользователю
        embed = discord.Embed(
            title="Заявка отправлена",
            description=(
                f"Ваша заявка на роль **{self.role_name}** успешно отправлена.\n"
                "Ожидайте рассмотрения администрацией.\n"
                "Статус можно проверить командой `/my-application`."
            ),
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )
        embed.add_field(name="Возраст", value=str(self.age), inline=True)
        embed.add_field(name="Активность", value=str(self.activity), inline=True)
        embed.add_field(name="Опыт", value=str(self.experience)[:200], inline=False)
        embed.add_field(name="Причина", value=str(self.reason)[:200], inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

        # Уведомление в ветку заявки: хелперы — кураторам хелперов,
        # модераторы — кураторам модераторов (свой канал + пинг роли)
        if interaction.guild:
            ch, ping = apply_target(self.role_name, interaction.guild)
            if ch:
                notify = discord.Embed(
                    title="Новая заявка",
                    description=(
                        f"**Пользователь:** {interaction.user.mention}\n"
                        f"**Роль:** {self.role_name}\n"
                        f"**Возраст:** {self.age}\n"
                        f"**Активность:** {self.activity}"
                    ),
                    color=discord.Color.dark_grey(),
                    timestamp=datetime.now()
                )
                notify.add_field(name="Опыт", value=str(self.experience)[:500], inline=False)
                notify.add_field(name="Причина", value=str(self.reason)[:500], inline=False)
                notify.set_footer(text=f"ID заявителя: {user_id}")
                msg = await ch.send(content=ping or None, embed=notify, view=StaffReviewView())
                apps[user_id]["message_id"] = str(msg.id)
                save_apps(apps)

        save_apps(apps)
        log.info(f"Заявка от {interaction.user} на роль {self.role_name}")


# ═══════════════════════════════════════════════════════════════════
# Select menu — выбор роли
# ═══════════════════════════════════════════════════════════════════

class RoleSelect(discord.ui.Select):
    def __init__(self):
        # Должности: Хелпер и Модератор (чат-контроль упразднён 2026-08-27)
        options = [
            discord.SelectOption(
                label="Хелпер",
                value="Helper",
                description="Помощь участникам сервера"
            ),
            discord.SelectOption(
                label="Модератор",
                value="Moderator",
                description="Модерация сервера и участников"
            ),
        ]
        super().__init__(
            placeholder="Выберите желаемую должность",
            options=options,
            custom_id="staff_role_select_v2"
        )

    async def callback(self, interaction: discord.Interaction):
        role_name = self.values[0]
        modal = StaffApplyModal(role_name=role_name)
        await interaction.response.send_modal(modal)


# ═══════════════════════════════════════════════════════════════════
# Кнопки рассмотрения заявки (persistent) — Одобрить / Отклонить
# ═══════════════════════════════════════════════════════════════════

class StaffReviewView(discord.ui.View):
    """Кнопки под сообщением заявки: решение модератора + DM заявителю."""

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
        if not (interaction.user.guild_permissions.manage_guild
                or interaction.user.guild_permissions.administrator):
            return await interaction.response.send_message(
                "Рассматривать заявки может только администрация.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)

        key, app, apps = self._find_app_by_message(interaction.message.id)
        if not app:
            return await interaction.followup.send(
                "Заявка не найдена (возможно, данные удалены).", ephemeral=True)
        if app.get("status") != "pending":
            label = {"approved": "одобрена", "rejected": "отклонена"}.get(
                app.get("status"), app.get("status", "?"))
            return await interaction.followup.send(
                f"Эта заявка уже {label}.", ephemeral=True)

        app["status"] = "approved" if action == "approve" else "rejected"
        app["reviewed_by"] = str(interaction.user)
        if not app.get("timestamp"):
            app["timestamp"] = app.get("submitted_at")

        # Одобрена → сразу выдать роль по должности (Хелпер или Модератор)
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

        # DM заявителю — именно этого уведомления не хватало
        dm_ok = False
        try:
            user = await interaction.client.fetch_user(int(app["user_id"]))
            if action == "approve":
                emb = discord.Embed(
                    title=" Заявка одобрена!",
                    description=("Поздравляем! Ваша заявка в команду сервера **одобрена**.\n"
                                 "Администрация свяжется с вами в ближайшее время."),
                    color=0x2ECC71)
            else:
                emb = discord.Embed(
                    title=" Заявка отклонена",
                    description=("К сожалению, ваша заявка в команду сервера на этот раз "
                                 "**отклонена**.\nВы можете подать её снова позже."),
                    color=0xE74C3C)
            emb.add_field(name=" Должность", value=app.get("role", "—"), inline=True)
            emb.add_field(name=" Рассмотрел", value=interaction.user.display_name, inline=True)
            if granted:
                emb.add_field(name=" Выдана роль", value=granted, inline=True)
            emb.set_footer(text="Статус всегда можно проверить: /my-application")
            emb.timestamp = datetime.now(timezone.utc)
            await user.send(embed=emb)
            dm_ok = True
        except Exception as e:
            log.info(f"[STAFF] DM заявителю не доставлен: {e}")

        # Снять кнопки и отметить решение на исходном сообщении
        try:
            src = interaction.message
            if src and src.embeds:
                e0 = discord.Embed.from_dict(src.embeds[0].to_dict())
                e0.color = 0x2ECC71 if action == "approve" else 0xE74C3C
                verdict_line = f"Модератор: {interaction.user.display_name}"
                if action == "approve" and granted:
                    verdict_line += f" · Роль: {granted}"
                e0.add_field(
                    name=" Решение: одобрена" if action == "approve" else " Решение: отклонена",
                    value=verdict_line,
                    inline=False)
                await src.edit(embed=e0, view=None)
        except Exception as _ex:
            log.debug("_review(): подавлено: %s", _ex)

        verdict = "одобрена" if action == "approve" else "отклонена"
        role_line = ""
        if action == "approve":
            role_line = (f" Роль выдана: **{granted}**."
                         if granted else f" Роль НЕ выдана: {grant_note}.")
        await interaction.followup.send(
            f"Заявка **{verdict}**.{role_line} Уведомление пользователю: "
            f"{'отправлено в ЛС' if dm_ok else 'НЕ доставлено (у пользователя закрыты ЛС)'}",
            ephemeral=True)

    @discord.ui.button(label="Одобрить", style=discord.ButtonStyle.success,
                       custom_id="staff_review_approve_v1")
    async def approve_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._review(interaction, "approve")

    @discord.ui.button(label="Отклонить", style=discord.ButtonStyle.danger,
                       custom_id="staff_review_reject_v1")
    async def reject_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._review(interaction, "reject")


class StaffApplyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(RoleSelect())


# ═══════════════════════════════════════════════════════════════════
# Cog
# ═══════════════════════════════════════════════════════════════════

class StaffApply(commands.Cog):
    """Набор в команду сервера"""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="staff-panel", description="Создать панель заявок в персонал с баннером")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def staff_panel(self, interaction: discord.Interaction):
        """Отправляет баннер заявок в персонал с меню выбора роли"""
        # Сразу подтверждаем interaction: загрузка удалённого баннера может занять больше 3 секунд.
        await interaction.response.defer(ephemeral=True)

        # Пути к кастомным баннерам - приоритет у пользовательской фотки
        custom_paths = [
            # Пользовательская фотография имеет высший приоритет.
            os.path.join(ROOT, 'assets', 'staff.jpg'),
            os.path.join(ROOT, 'assets', 'diting_result_8b5912208df711f1ab51e63795c09448_1.jpeg'),
            os.path.join(ROOT, 'assets', 'staff_custom.png'),
            os.path.join(ROOT, 'assets', 'staff_custom.jpg'),
            os.path.join(ROOT, 'assets', 'staff_custom.jpeg'),
            os.path.join(ROOT, 'assets', 'staff_banner_custom.png'),
            os.path.join(ROOT, 'assets', 'staff_hakumo_banner.png'),
        ]
        
        file = None

        # Сначала используем оригинальную фотографию по URL.
        # Это намеренно имеет приоритет над старым локальным баннером.
        try:
            if any(os.path.exists(p) for p in custom_paths):
                raise aiohttp.ClientError("локальный баннер уже доступен")
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(STAFF_REMOTE_BANNER_URL) as response:
                    if response.status == 200:
                        remote_banner = await response.read()
                        if remote_banner:
                            file = discord.File(
                                io.BytesIO(remote_banner),
                                filename="staff_banner.png"
                            )
        except (aiohttp.ClientError, OSError) as exc:
            log.warning("Не удалось загрузить удалённый баннер STAFF: %s", exc)

        # Если URL недоступен — использовать локальные файлы баннеров.
        if not file:
            for p in custom_paths:
                if os.path.exists(p):
                    file = discord.File(p, filename="staff_banner.png")
                    break

        # Если удалённый и локальный баннеры недоступны - старый fallback.
        if not file:
            img_buf = await interaction.client.loop.run_in_executor(
                None, generate_staff_panel_bytes
            )
            file = discord.File(img_buf, filename="staff_panel.png")
        
        view = StaffApplyView()
        
        # Отправляем сам файл напрямую: без embed-контейнера и лишнего текста.
        # Так Discord показывает фотографию в полном размере, а меню остаётся снизу.
        await interaction.channel.send(file=file, view=view)
        await interaction.followup.send("✅ Панель заявок в персонал успешно создана!", ephemeral=True)

    @app_commands.command(name="my-application", description="Проверить статус моей заявки в персонал")
    async def my_application(self, interaction: discord.Interaction):
        """Пользователь видит, где его заявка: на рассмотрении / одобрена / отклонена."""
        apps = load_apps()
        uid = str(interaction.user.id)
        mine = [a for a in apps.values() if str(a.get("user_id")) == uid]
        if not mine:
            return await interaction.response.send_message(
                "У вас пока нет заявок. Подать можно через панель набора в команду сервера.",
                ephemeral=True)
        mine.sort(key=lambda a: a.get("timestamp") or a.get("submitted_at") or "", reverse=True)
        a = mine[0]
        status_map = {"pending": " На рассмотрении",
                      "approved": " Одобрена",
                      "rejected": " Отклонена"}
        st = status_map.get(a.get("status"), a.get("status", "?"))
        color = {"pending": 0xC8922A, "approved": 0x2ECC71, "rejected": 0xE74C3C}.get(
            a.get("status"), 0xC8922A)
        e = discord.Embed(title=" Моя заявка в команду", color=color,
                          timestamp=datetime.now(timezone.utc))
        total = len(mine)
        desc = (f"Статус: **{st}**\n"
                f"Должность: **{a.get('role', '—')}**\n"
                f"Подана: {(a.get('timestamp') or a.get('submitted_at') or '?')[:10]}\n")
        if total > 1:
            desc += f"Всего заявок: {total} (показана последняя)\n"
        if a.get("reviewed_by"):
            desc += f"Рассмотрел: **{a['reviewed_by']}**\n"
        if a.get("review_note"):
            desc += f"Комментарий: {a['review_note']}\n"
        e.description = desc
        e.set_footer(text="Решение также приходит в личные сообщения")
        await interaction.response.send_message(embed=e, ephemeral=True)

    @commands.Cog.listener()
    async def on_ready(self):
        # Регистрируем persistent views
        self.bot.add_view(StaffApplyView())
        self.bot.add_view(StaffReviewView())


async def setup(bot):
    await bot.add_cog(StaffApply(bot))
    log.info("StaffApply загружен")
