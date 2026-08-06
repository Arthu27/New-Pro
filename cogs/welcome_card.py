"""
Welcome Card — роскошная карточка приветствия (тёмно-синий + золото).

При входе участника бот рисует карту с его аватаром:
«ДОБРО ПОЖАЛОВАТЬ · Имя · ты N-й участник сервера».
Опционально — карта «ДО СВИДАНИЯ» при выходе.

Команды: /welcome ... (админ).
Хранилище: data/welcome_card.json
"""
import os
import io
import json
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone

from PIL import Image, ImageDraw, ImageFont

from logger import get_logger

log = get_logger("welcome_card")

CFG_PATH = 'data/welcome_card.json'

GOLD = 0xD4AF37
DIVIDER = "✦ ───────────────────── ✦"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = os.path.join(ROOT, 'assets', 'fonts')
FONT_B = os.path.join(FONTS, 'Bold.ttf')
FONT_R = os.path.join(FONTS, 'Regular.ttf')

C_BG_TOP = (10, 16, 30)
C_BG_BOT = (17, 28, 52)
C_GOLD = (212, 175, 55)
C_GOLD_SOFT = (150, 122, 44)
C_TEXT = (236, 238, 244)
C_DIM = (150, 158, 175)

DEFAULT_CFG = {
    "enabled": True,
    "channel_id": 0,          # 0 = system_channel
    "welcome": True,          # карта при входе
    "goodbye": False,         # карта при выходе
}

_font_cache = {}


def _font(bold: bool, size: int):
    key = (bold, size)
    f = _font_cache.get(key)
    if f is None:
        try:
            f = ImageFont.truetype(FONT_B if bold else FONT_R, size)
        except Exception:
            f = ImageFont.load_default()
        _font_cache[key] = f
    return f


def _load_cfg():
    try:
        if os.path.exists(CFG_PATH):
            with open(CFG_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_cfg(data):
    try:
        os.makedirs('data', exist_ok=True)
        tmp = CFG_PATH + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, CFG_PATH)
    except Exception as e:
        log.error(f"[WCARD] ошибка записи: {e}")


def _circle_avatar(img_bytes: bytes, size: int) -> Image.Image:
    av = Image.open(io.BytesIO(img_bytes)).convert('RGBA').resize((size, size), Image.LANCZOS)
    mask = Image.new('L', (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size, size], fill=255)
    out = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    out.paste(av, (0, 0), mask)
    return out


def _letter_avatar(letter: str, size: int) -> Image.Image:
    """Заглушка: золотая буква в тёмном круге."""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([0, 0, size, size], fill=(20, 30, 55, 255))
    f = _font(True, int(size * 0.44))
    d.text((size / 2, size / 2), letter.upper(), font=f, fill=C_GOLD, anchor='mm')
    return img


def render_card(member_name: str, guild_name: str, count: int,
                avatar_bytes: bytes = None, kind: str = 'welcome') -> io.BytesIO:
    """kind: 'welcome' | 'goodbye' → PNG bytes."""
    S = 2
    W, H = 1000 * S, 320 * S
    img = Image.new('RGB', (W, H), C_BG_TOP)
    d = ImageDraw.Draw(img, 'RGBA')

    for y in range(H):
        t = y / max(1, H - 1)
        d.line([(0, y), (W, y)],
               fill=tuple(int(C_BG_TOP[i] + (C_BG_BOT[i] - C_BG_TOP[i]) * t) for i in range(3)))

    # Двойная золотая рамка
    d.rectangle([12 * S, 12 * S, W - 12 * S, H - 12 * S], outline=C_GOLD, width=2 * S)
    d.rectangle([20 * S, 20 * S, W - 20 * S, H - 20 * S], outline=C_GOLD_SOFT + (110,), width=1 * S)

    # Угловые акценты (тонкие золотые уголки)
    for cx, cy, sx, sy in ((12, 12, 1, 1), (W - 12, 12, -1, 1), (12, H - 12, 1, -1), (W - 12, H - 12, -1, -1)):
        d.line([cx * 1, cy * 1, cx * 1 + sx * 46 * S, cy * 1], fill=C_GOLD, width=2 * S)
        d.line([cx * 1, cy * 1, cx * 1, cy * 1 + sy * 46 * S], fill=C_GOLD, width=2 * S)

    # Аватар с золотым кольцом
    av_size = 208 * S
    ax, ay = 58 * S, (H - av_size) // 2
    if avatar_bytes:
        try:
            av = _circle_avatar(avatar_bytes, av_size)
        except Exception:
            av = _letter_avatar((member_name or '?')[0], av_size)
    else:
        av = _letter_avatar((member_name or '?')[0], av_size)
    img.paste(av, (ax, ay), av)
    d.ellipse([ax - 6 * S, ay - 6 * S, ax + av_size + 6 * S, ay + av_size + 6 * S],
              outline=C_GOLD, width=3 * S)
    d.ellipse([ax - 12 * S, ay - 12 * S, ax + av_size + 12 * S, ay + av_size + 12 * S],
              outline=C_GOLD_SOFT + (120,), width=1 * S)

    # Текст
    tx = ax + av_size + 56 * S
    if kind == 'welcome':
        title, title_color = "ДОБРО ПОЖАЛОВАТЬ", C_GOLD
        sub = f"ты {count}-й участник сервера"
    else:
        title, title_color = "ДО СВИДАНИЯ", (200, 205, 215)
        sub = f"нас стало {count} участников"

    d.text((tx, 64 * S), title, font=_font(True, 30 * S), fill=title_color)
    name = member_name[:26]
    d.text((tx, 108 * S), name, font=_font(True, 46 * S), fill=C_TEXT)
    d.line([tx, 172 * S, tx + 420 * S, 172 * S], fill=C_GOLD + (160,), width=2 * S)
    d.text((tx, 190 * S), sub, font=_font(False, 22 * S), fill=C_DIM)
    gname = guild_name[:44]
    d.text((tx, 226 * S), gname, font=_font(False, 19 * S), fill=C_DIM)
    dt = datetime.now().strftime('%d.%m.%Y')
    d.text((W - 48 * S - d.textlength(dt, font=_font(False, 16 * S)), H - 52 * S),
           dt, font=_font(False, 16 * S), fill=C_DIM)

    img = img.resize((W // S, H // S), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format='PNG', optimize=True)
    buf.seek(0)
    return buf


class WelcomeCard(commands.Cog):
    """Картинка-приветствие с аватаром (тёмно-синий + золото)."""

    def __init__(self, bot):
        self.bot = bot
        self._cfgs = _load_cfg()

    def cfg(self, guild_id: int) -> dict:
        c = dict(DEFAULT_CFG)
        c.update(self._cfgs.get(str(guild_id), {}))
        return c

    def set_cfg(self, guild_id: int, key: str, value):
        self._cfgs.setdefault(str(guild_id), {})[key] = value
        _save_cfg(self._cfgs)

    async def _avatar_bytes(self, member: discord.abc.User):
        try:
            return await member.display_avatar.replace(size=256, static_format='png').read()
        except Exception:
            return None

    async def _send_card(self, guild: discord.Guild, member: discord.abc.User, kind: str):
        cfg = self.cfg(guild.id)
        ch_id = int(cfg.get('channel_id', 0) or 0)
        ch = guild.get_channel(ch_id) if ch_id else None
        if ch is None:
            ch = guild.system_channel
        if ch is None:
            return
        av = await self._avatar_bytes(member)
        buf = render_card(member.display_name, guild.name, guild.member_count or 0, av, kind)
        file = discord.File(buf, filename=f"{kind}.png")
        try:
            if kind == 'welcome':
                await ch.send(content=f"Добро пожаловать, {member.mention} ✨", file=file)
            else:
                await ch.send(file=file)
        except Exception as e:
            log.warning(f"[WCARD] {guild.name}: не смог отправить карту: {e}")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        cfg = self.cfg(member.guild.id)
        if cfg.get('enabled') and cfg.get('welcome'):
            await self._send_card(member.guild, member, 'welcome')

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        cfg = self.cfg(member.guild.id)
        if cfg.get('enabled') and cfg.get('goodbye'):
            await self._send_card(member.guild, member, 'goodbye')

    # ────────────────────────────────────────────────────────────
    wcard = app_commands.Group(name="welcome", description="Карточки приветствия (картинка)")

    def _status_embed(self, guild: discord.Guild) -> discord.Embed:
        cfg = self.cfg(guild.id)
        ch = guild.get_channel(int(cfg.get('channel_id', 0) or 0))
        e = discord.Embed(color=GOLD if cfg.get('enabled') else 0x95A5A6,
                          timestamp=datetime.now(timezone.utc))
        e.description = (
            "## 🖼 Welcome Card\n"
            f"Система: **{'🟢 вкл' if cfg.get('enabled') else '🔴 выкл'}**\n"
            f"Карта входа: **{'вкл' if cfg.get('welcome') else 'выкл'}**\n"
            f"Карта прощания: **{'вкл' if cfg.get('goodbye') else 'выкл'}**\n"
            f"Канал: {ch.mention if ch else '`системный канал сервера`'}\n{DIVIDER}")
        e.set_footer(text=f"{guild.name} · welcome card")
        return e

    @wcard.command(name="status", description="Настройки приветственных карт")
    @app_commands.checks.has_permissions(administrator=True)
    async def wc_status(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=self._status_embed(interaction.guild), ephemeral=True)

    @wcard.command(name="test", description="Предпросмотр карты (на тебе)")
    @app_commands.describe(тип="Какую карту показать")
    @app_commands.choices(тип=[
        app_commands.Choice(name="Приветствие", value="welcome"),
        app_commands.Choice(name="Прощание", value="goodbye"),
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def wc_test(self, interaction: discord.Interaction, тип: app_commands.Choice[str] = None):
        await interaction.response.defer(ephemeral=True)
        kind = тип.value if тип else 'welcome'
        av = await self._avatar_bytes(interaction.user)
        buf = render_card(interaction.user.display_name, interaction.guild.name,
                          interaction.guild.member_count or 0, av, kind)
        await interaction.followup.send(file=discord.File(buf, filename=f"{kind}.png"), ephemeral=True)

    @wcard.command(name="channel", description="Канал для карт приветствия")
    @app_commands.describe(канал="Текстовый канал")
    @app_commands.checks.has_permissions(administrator=True)
    async def wc_channel(self, interaction: discord.Interaction, канал: discord.TextChannel):
        self.set_cfg(interaction.guild.id, 'channel_id', канал.id)
        await interaction.response.send_message(f"✅ Карты будут приходить в {канал.mention}", ephemeral=True)

    @wcard.command(name="toggle", description="Включить/выключить карты входа и прощания")
    @app_commands.describe(вход="Карта при входе", выход="Карта при выходе")
    @app_commands.choices(вход=[app_commands.Choice(name="вкл", value=1), app_commands.Choice(name="выкл", value=0)],
                          выход=[app_commands.Choice(name="вкл", value=1), app_commands.Choice(name="выкл", value=0)])
    @app_commands.checks.has_permissions(administrator=True)
    async def wc_toggle(self, interaction: discord.Interaction,
                        вход: app_commands.Choice[int] = None, выход: app_commands.Choice[int] = None):
        if вход is not None:
            self.set_cfg(interaction.guild.id, 'welcome', bool(вход.value))
            self.set_cfg(interaction.guild.id, 'enabled', True)
        if выход is not None:
            self.set_cfg(interaction.guild.id, 'goodbye', bool(выход.value))
            self.set_cfg(interaction.guild.id, 'enabled', True)
        await interaction.response.send_message(embed=self._status_embed(interaction.guild), ephemeral=True)


async def setup(bot):
    await bot.add_cog(WelcomeCard(bot))
    log.info("[WCARD] Ког загружен")
