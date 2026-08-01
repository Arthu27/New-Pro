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
from PIL import Image, ImageDraw, ImageFont
from cogs._menu_bg import load_menu_bg

from logger import get_logger
log = get_logger("staff_apply")


APPLY_CHANNEL_ID = Config.APPLY_CHANNEL_ID
APPS_FILE = "data/staff_apps.json"


ROOT = os.path.join(os.path.dirname(__file__), '..')
FONTS = os.path.join(ROOT, 'assets', 'fonts')
BG_PATH = os.path.join(ROOT, 'assets', 'staff_bg.jpg')
FONT_B = os.path.join(FONTS, 'Bold.ttf')
FONT_R = os.path.join(FONTS, 'Regular.ttf')

WHITE = (255, 255, 255)
BLACK = (20, 20, 25)
TEAL = (13, 148, 136)
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

def _icon_badge(diameter, glyph_fn, ring_color=BLACK, ring_w=None, icon_color=TEAL):
    ring_w = ring_w if ring_w is not None else max(2, diameter // 22)
    def draw(d, scale):
        size = diameter * scale
        rw = ring_w * scale
        r = size * 0.22
        d.rounded_rectangle((rw / 2, rw / 2, size - rw / 2 - 1, size - rw / 2 - 1),
                             radius=r, fill=WHITE, outline=ring_color, width=rw)
        glyph_fn(d, size / 2, size / 2, size * 0.60, max(2, int(size * 0.032)), icon_color)
    return _ss_render(diameter, diameter, draw)

def _corner_bracket(size, thickness, length_ratio=0.35, color=TEAL):
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

def generate_staff_panel_card() -> Image.Image:
    W, H = 920, 520
    bg = load_menu_bg(W, H, "teal")
    d = ImageDraw.Draw(bg)

    # Header
    header_box = _rounded_panel(872, 72, radius=14, fill=WHITE, outline=BLACK, ow=2)
    bg.alpha_composite(header_box, (24, 20))

    badge = _icon_badge(52, _icon_staff, ring_color=BLACK, ring_w=2, icon_color=TEAL)
    bg.alpha_composite(badge, (36, 30))

    d.text((100, 26), "НАБОР В КОМАНДУ СЕРВЕРА", fill=BLACK, font=_f(True, 24))
    d.text((100, 56), "ВЫБЕРИТЕ ЖЕЛАЕМУЮ ДОЛЖНОСТЬ В МЕНЮ НИЖЕ", fill=MUTED, font=_f(False, 15))

    pill = _rounded_panel(160, 36, radius=10, fill=WHITE, outline=TEAL, ow=2)
    bg.alpha_composite(pill, (720, 38))
    d.text((748, 46), "RECRUIT v4.0", fill=TEAL, font=_f(True, 14))

    # 3 Staff cards
    items = [
        ("MODERATOR", "Администрирование и порядок на сервере", "Возраст: 16+"),
        ("CHAT CONTROL", "Контроль текстовых каналов и чатов", "Возраст: 14+"),
        ("HELPER", "Помощь новичкам и ответы на вопросы", "Возраст: 14+")
    ]
    box_w, box_h = 872, 110
    gap_y = 16
    start_x, start_y = 24, 108

    for idx, (title, sub, note) in enumerate(items):
        by = start_y + idx * (box_h + gap_y)

        box = _rounded_panel(box_w, box_h, radius=14, fill=WHITE, outline=BLACK, ow=2)
        bg.alpha_composite(box, (start_x, by))

        ibadge = _icon_badge(64, _icon_staff, ring_color=BLACK, ring_w=2, icon_color=TEAL)
        bg.alpha_composite(ibadge, (start_x + 16, by + 23))

        d.text((start_x + 94, by + 18), title, fill=BLACK, font=_f(True, 23))
        d.text((start_x + 94, by + 50), sub, fill=TEAL, font=_f(True, 17))
        d.text((start_x + 94, by + 78), note, fill=MUTED, font=_f(False, 15))

    br = _corner_bracket(40, 4, color=TEAL)
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
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            "guild_id": interaction.guild.id if interaction.guild else None,
        }
        save_apps(apps)

        # Подтверждение пользователю
        embed = discord.Embed(
            title="Заявка отправлена",
            description=(
                f"Ваша заявка на роль **{self.role_name}** успешно отправлена.\n"
                f"Ожидайте рассмотрения администрацией."
            ),
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )
        embed.add_field(name="Возраст", value=str(self.age), inline=True)
        embed.add_field(name="Активность", value=str(self.activity), inline=True)
        embed.add_field(name="Опыт", value=str(self.experience)[:200], inline=False)
        embed.add_field(name="Причина", value=str(self.reason)[:200], inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

        # Уведомление в канал заявок
        if APPLY_CHANNEL_ID and interaction.guild:
            ch = interaction.guild.get_channel(APPLY_CHANNEL_ID)
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
                await ch.send(embed=notify)

        log.info(f"Заявка от {interaction.user} на роль {self.role_name}")


# ═══════════════════════════════════════════════════════════════════
# Select menu — выбор роли
# ═══════════════════════════════════════════════════════════════════

class RoleSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label="Moderator",
                value="Moderator",
                description="Модерация сервера и участников"
            ),
            discord.SelectOption(
                label="Chat Control",
                value="Chat Control",
                description="Контроль чатов и порядка"
            ),
            discord.SelectOption(
                label="Helper",
                value="Helper",
                description="Помощь участникам сервера"
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

    @app_commands.command(name="staff-panel", description="Создать красивую панель набора в команду")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def staff_panel(self, interaction: discord.Interaction):
        """Создать профессиональную карточку-панель для набора"""
        # Генерируем красивую кастомную Pillow карточку набора
        img_buf = await interaction.client.loop.run_in_executor(
            None, generate_staff_panel_bytes
        )
        file = discord.File(img_buf, filename="staff_panel.png")
        view = StaffApplyView()
        await interaction.channel.send(file=file, view=view)
        await interaction.response.send_message("Панель набора в команду успешно создана.", ephemeral=True)

    @commands.Cog.listener()
    async def on_ready(self):
        # Регистрируем persistent view
        self.bot.add_view(StaffApplyView())


async def setup(bot):
    await bot.add_cog(StaffApply(bot))
    log.info("StaffApply загружен")
