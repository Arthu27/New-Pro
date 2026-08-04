"""
Warnings Cog
Система предупреждений — database (SQLite)
Тёмная тема, русский язык
"""
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone, timedelta
import os
import json
import io

from cogs.embed_utils import mod_dm_embed, DIVIDER
from logger import get_logger
from db import GuildData

log = get_logger("warnings")


# ═══════════════════════════════════════════════════════════════════
#  SELECT-МЕНЮ ДОСЬЕ (!pw) + карточка в стиле ticket-panel
# ═══════════════════════════════════════════════════════════════════
try:
    from cogs import _card_style as CS
    from cogs._menu_bg import load_menu_bg
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    _PIL_OK = True
except Exception:
    _PIL_OK = False


def _load_base_bg(w, h):
    try:
        from cogs._menu_bg import _load_base_bg as _lb
        return _lb(w, h)
    except Exception:
        img = Image.new("RGB", (w, h), (18, 18, 20))
        return img


def generate_pw_card(display_name, user_id, avatar_url, warns, cases, notes,
                     score, score_text, member=None):
    """Сгенерировать карточку-досье в стиле ticket-panel (profile_bg_pro)."""
    W, H = 1200, 600
    # Фон как у ticket-panel (teal на основе profile_bg_pro)
    try:
        bg = load_menu_bg(W, H, "teal")
        bg = bg.convert("RGB")
    except Exception:
        bg = _load_base_bg(W, H).convert("RGB")
    d = ImageDraw.Draw(bg, "RGBA")

    # Полупрозрачная тёмная панель для читаемости
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    do = ImageDraw.Draw(ov)
    do.rounded_rectangle((30, 30, W - 30, H - 30), radius=28, fill=(10, 10, 14, 190))
    bg = Image.alpha_composite(bg.convert("RGBA"), ov).convert("RGB")
    d = ImageDraw.Draw(bg, "RGBA")

    # Шапка
    try:
        f_title = CS.font(True, 52)
    except Exception:
        f_title = ImageFont.load_default() if _PIL_OK else None
    try:
        f_big = CS.font(True, 44)
        f_mid = CS.font(True, 28)
        f_txt = CS.font(False, 24)
        f_small = CS.font(False, 18)
    except Exception:
        f_big = f_mid = f_txt = f_small = f_title

    # Заголовок
    d.text((70, 55), "ДОСЬЕ ПОЛЬЗОВАТЕЛЯ", font=f_title, fill=(222, 28, 42, 255))
    d.line([(70, 120), (W - 70, 120)], fill=(222, 28, 42, 200), width=3)

    # Имя
    d.text((70, 145), display_name or "Неизвестно", font=f_big, fill=(255, 255, 255, 255))
    d.text((70, 200), f"ID: {user_id}", font=f_mid, fill=(205, 205, 208, 255))

    # Левая колонка: статистика
    x1 = 70
    y = 265
    d.text((x1, y), "ПРЕДУПРЕЖДЕНИЯ", font=f_txt, fill=(222, 28, 42, 255))
    d.text((x1 + 320, y), f"{warns}", font=f_big, fill=(255, 255, 255, 255))
    y += 55
    d.text((x1, y), "МЬЮТЫ / НАКАЗАНИЯ", font=f_txt, fill=(222, 28, 42, 255))
    d.text((x1 + 320, y), f"{cases}", font=f_big, fill=(255, 255, 255, 255))
    y += 55
    d.text((x1, y), "ЗАМЕТКИ", font=f_txt, fill=(222, 28, 42, 255))
    d.text((x1 + 320, y), f"{notes}", font=f_big, fill=(255, 255, 255, 255))

    # Правая колонка: оценка
    x2 = W // 2 + 60
    d.text((x2, 265), "ОЦЕНКА", font=f_txt, fill=(222, 28, 42, 255))
    score_color = (46, 204, 113, 255) if score >= 60 else (243, 156, 18, 255) if score >= 30 else (231, 76, 60, 255)
    d.text((x2, 305), f"{score}/100", font=CS.font(True, 72) if _PIL_OK else f_big, fill=score_color)

    # Прогресс-бар
    bar_w = 480
    bar_h = 22
    bx, by = x2, 400
    d.rounded_rectangle((bx, by, bx + bar_w, by + bar_h), radius=11, fill=(60, 60, 66, 255))
    fill_w = int(bar_w * max(0, min(100, score)) / 100)
    if fill_w > 0:
        d.rounded_rectangle((bx, by, bx + fill_w, by + bar_h), radius=11, fill=score_color)
    d.text((x2, 435), score_text, font=f_mid, fill=(255, 255, 255, 255))

    # Подпись
    d.text((70, H - 70), "Aether Модерация • Досье", font=f_small, fill=(150, 150, 155, 255))

    buf = io.BytesIO()
    bg.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf


def _compute_score(warns, cases):
    """Скоринг /100: старт 100, -12 за warn, -18 за mute/наказание, -25 за ban."""
    score = 100
    score -= warns * 12
    for c in cases:
        act = str(c.get("action", "")).lower()
        if act == "ban":
            score -= 25
        elif act in ("timeout", "mute_chat", "vmute", "kick"):
            score -= 18
        elif act == "warn":
            score -= 12
    return max(0, min(100, score))


def _score_text(score):
    if score >= 80:
        return "Хорошо"
    if score >= 50:
        return "Удовлетворительно"
    if score >= 25:
        return "Плохо"
    return "Очень плохо"


def load_warn_config(guild_id):
    """Загрузить конфигурацию наказаний (пока JSON, потом DB)"""
    import json, os
    f = f'data/warn_config_{guild_id}.json'
    if os.path.exists(f):
        with open(f, 'r', encoding='utf-8') as fp:
            return json.load(fp)
    return {'steps': []}


def duration_to_minutes(duration, unit):
    if unit == 'hour':
        return duration * 60
    if unit == 'day':
        return duration * 1440
    return duration


class warnings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = GuildData("warnings")

    def _get_warns(self, guild_id: int, user_id: int) -> list:
        return self.db.get(guild_id, str(user_id), [])

    def _save_warns(self, guild_id: int, user_id: int, warns: list):
        self.db.set(guild_id, str(user_id), warns)

    def _clear_warns(self, guild_id: int, user_id: int):
        self.db.set(guild_id, str(user_id), [])

    async def send_dm(self, user, embed):
        try:
            await user.send(embed=embed)
        except discord.Forbidden:
            pass

    async def apply_warn_punishment(self, guild, member, warn_count):
        """Автоматическое наказание по количеству предупреждений"""
        cfg = load_warn_config(str(guild.id))
        steps = cfg.get('steps', [])
        if not steps:
            return None

        matched = None
        for step in sorted(steps, key=lambda x: x['count']):
            if warn_count >= step['count']:
                matched = step

        if not matched:
            return None

        action = matched.get('action', 'mute')
        duration = matched.get('duration', 10)
        unit = matched.get('unit', 'minute')
        minutes = duration_to_minutes(duration, unit)

        try:
            if action in ('mute', 'timeout'):
                until = discord.utils.utcnow() + timedelta(minutes=minutes)
                await member.timeout(until, reason=f'Авто-наказание: {warn_count} предупреждений')
                return f'Мьют {duration} {unit}'
            elif action == 'kick':
                await member.kick(reason=f'Авто-наказание: {warn_count} предупреждений')
                return 'Кик'
            elif action == 'ban':
                await member.ban(reason=f'Авто-наказание: {warn_count} предупреждений')
                return 'Бан'
        except Exception as e:
            log.error(f'Ошибка авто-наказания: {e}')
        return None

    # ── /warn ────────────────────────────────────────────────────────────
    async def add_warn(self, interaction, user: discord.Member, reason: str = None):
        """Ortak warn çekirdeği: kayıt + DM + otomatik ceza.

        /warn komutu VE sağ-tık context menüleri (mod_tools) bunu kullanır.
        Yanıt GÖNDERMEZ — çağıran taraf yanıtlar.
        Döner: (warn_id, total, punishment_result)
        """
        guild = interaction.guild
        warns = self._get_warns(guild.id, user.id)
        warn_id = len(warns) + 1
        warns.append({
            "id": warn_id,
            "reason": reason or "Не указана",
            "mod": str(interaction.user),
            "mod_id": str(interaction.user.id),
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        self._save_warns(guild.id, user.id, warns)
        total = len(warns)

        # DM пользователю
        import json, os
        dm_file = f'data/warn_dm_{guild.id}.json'
        custom_dm = None
        if os.path.exists(dm_file):
            with open(dm_file, 'r', encoding='utf-8') as df:
                dm_cfg = json.load(df)
            custom_dm = dm_cfg.get('message')

        if custom_dm:
            msg = custom_dm.replace('{user}', user.display_name).replace('{reason}', reason or 'Не указана').replace('{mod}', interaction.user.display_name).replace('{сервер}', guild.name)
            dm_embed = discord.Embed(color=discord.Color.dark_grey(), timestamp=datetime.now(timezone.utc))
            dm_embed.description = (
                f"## Предупреждение #{warn_id}\n"
                f"{msg}\n\n"
                f"Сервер: **{guild.name}**\n"
                f"Модератор: **{interaction.user.display_name}**\n"
                f"Всего предупреждений: **{total}**\n"
                f"Причина: {reason or 'Не указана'}"
            )
            dm_embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
            dm_embed.set_footer(text=f"{guild.name}")
            await self.send_dm(user, dm_embed)
        else:
            await self.send_dm(user, mod_dm_embed("warn", guild, interaction.user, reason))

        # Авто-наказание
        punishment_result = await self.apply_warn_punishment(guild, user, total)
        return warn_id, total, punishment_result

    @app_commands.command(name="warn", description="Выдать предупреждение")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warn(self, interaction, user: discord.Member, reason: str = None):
        guild = interaction.guild
        warn_id, total, punishment_result = await self.add_warn(interaction, user, reason)

        # Ответ модератору
        e = discord.Embed(color=discord.Color.dark_grey(), timestamp=datetime.now(timezone.utc))
        desc = (
            f"## Предупреждение выдано\n"
            f"**{user.display_name}** · `{user.id}`\n\n"
            f"Предупреждение: **#{warn_id}**\n"
            f"Всего: **{total}**\n"
            f"Причина: {reason or 'Не указана'}\n"
            f"Модератор: {interaction.user.mention}"
        )
        if punishment_result:
            desc += f"\nАвто-наказание: **{punishment_result}**"
        desc += f"\n\n{DIVIDER}"
        e.description = desc
        e.set_footer(text=f"{guild.name}")
        await interaction.response.send_message(embed=e, ephemeral=True)

    # ── /warnings ────────────────────────────────────────────────────────
    @app_commands.command(name="warnings", description="Предупреждения пользователя")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warnings_list(self, interaction, user: discord.Member):
        warns = self._get_warns(interaction.guild.id, user.id)

        e = discord.Embed(color=discord.Color.dark_grey(), timestamp=datetime.now(timezone.utc))

        if not warns:
            e.description = (
                f"## Предупреждения\n"
                f"**{user.display_name}** · `{user.id}`\n\n"
                f"Предупреждений нет.\n\n"
                f"{DIVIDER}"
            )
        else:
            desc = (
                f"## Предупреждения\n"
                f"**{user.display_name}** · `{user.id}`\n"
                f"Всего: **{len(warns)}**\n\n"
            )
            for w in warns[-8:]:
                desc += f"**#{w['id']}** — {w['reason']}\n-# {w['timestamp'][:10]} · {w.get('mod', '?')}\n\n"
            desc += DIVIDER
            e.description = desc

        e.set_thumbnail(url=user.display_avatar.url)
        e.set_footer(text=f"{interaction.guild.name}")
        await interaction.response.send_message(embed=e, ephemeral=True)

    # ── /clearwarns ──────────────────────────────────────────────────────
    @app_commands.command(name="clearwarns", description="Очистить все предупреждения")
    @app_commands.checks.has_permissions(administrator=True)
    async def clearwarns(self, interaction, user: discord.Member):
        warns = self._get_warns(interaction.guild.id, user.id)
        count = len(warns)
        self._clear_warns(interaction.guild.id, user.id)

        e = discord.Embed(color=discord.Color.dark_grey(), timestamp=datetime.now(timezone.utc))
        e.description = (
            f"## Предупреждения очищены\n"
            f"**{user.display_name}** · `{user.id}`\n\n"
            f"Удалено: **{count}** предупреждений\n"
            f"Модератор: {interaction.user.mention}\n\n"
            f"{DIVIDER}"
        )
        e.set_footer(text=f"{interaction.guild.name}")
        await interaction.response.send_message(embed=e, ephemeral=True)

    # ── /unwarn ─────────────────────────────────────────────────────────
    @app_commands.command(name="unwarn", description="Снять последнее предупреждение у пользователя")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def unwarn(self, interaction, user: discord.Member):
        """Снять последнее предупреждение у пользователя"""
        warns = self._get_warns(interaction.guild.id, user.id)
        if not warns:
            e = discord.Embed(color=discord.Color.dark_grey(), timestamp=datetime.now(timezone.utc))
            e.description = (
                f"## Снятие предупреждения\n"
                f"**{user.display_name}** · `{user.id}`\n\n"
                f"У пользователя нет предупреждений.\n\n"
                f"{DIVIDER}"
            )
            e.set_footer(text=f"{interaction.guild.name}")
            await interaction.response.send_message(embed=e, ephemeral=True)
            return

        removed = warns.pop()
        self._save_warns(interaction.guild.id, user.id, warns)
        total = len(warns)

        e = discord.Embed(color=discord.Color.dark_grey(), timestamp=datetime.now(timezone.utc))
        e.description = (
            f"## Снятие предупреждения\n"
            f"**{user.display_name}** · `{user.id}`\n\n"
            f"Снято: **#{removed.get('id')}** — {removed.get('reason', 'Не указана')}\n"
            f"Осталось: **{total}**\n"
            f"Модератор: {interaction.user.mention}\n\n"
            f"{DIVIDER}"
        )
        e.set_thumbnail(url=user.display_avatar.url)
        e.set_footer(text=f"{interaction.guild.name}")
        await interaction.response.send_message(embed=e, ephemeral=True)

    # ── add_warning (для AI-modератора, без interaction) ─────────────────
    async def add_warning(self, user: discord.Member, moderator: discord.Member, reason: str = None):
        """Добавить предупреждение без interaction"""
        guild = user.guild
        warns = self._get_warns(guild.id, user.id)
        warn_id = len(warns) + 1
        warns.append({
            "id": warn_id,
            "reason": reason or "Не указана",
            "mod": str(moderator),
            "mod_id": str(moderator.id),
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        self._save_warns(guild.id, user.id, warns)
        total = len(warns)

        # DM
        try:
            dm_embed = discord.Embed(color=discord.Color.dark_grey(), timestamp=datetime.now(timezone.utc))
            dm_embed.description = (
                f"## Предупреждение #{warn_id}\n"
                f"**Сервер:** {guild.name}\n"
                f"**Причина:** {reason or 'Не указана'}\n"
                f"**Модератор:** {moderator.display_name}\n"
                f"**Всего предупреждений:** {total}"
            )
            if guild.icon:
                dm_embed.set_footer(text=f"{guild.name}", icon_url=guild.icon.url)
            await user.send(embed=dm_embed)
        except Exception:
            pass

        await self.apply_warn_punishment(guild, user, total)
        return warn_id, total

    # ── !pw — полное досье пользователя ────────────────────────────────
    def _collect_mod_data(self, guild_id, user_id):
        """Собрать все данные о пользователе: warns + случаи + заметки."""
        warns = self._get_warns(guild_id, user_id)
        cases = []
        notes = []
        # mod_data.json (ban/kick/timeout/mute от moderation)
        try:
            md = {}
            if os.path.exists("data/mod_data.json"):
                with open("data/mod_data.json", "r", encoding="utf-8") as f:
                    md = json.load(f)
            for c in md.get("cases", {}).get(str(guild_id), []):
                if str(c.get("user_id", "")) == str(user_id):
                    cases.append(c)
        except Exception:
            pass
        # mod_advanced_data.json (case + notes от advanced_mod)
        try:
            ad = {}
            if os.path.exists("data/mod_advanced_data.json"):
                with open("data/mod_advanced_data.json", "r", encoding="utf-8") as f:
                    ad = json.load(f)
            for c in ad.get("case", {}).get(str(guild_id), []):
                if str(c.get("user_id", "")) == str(user_id):
                    cases.append(c)
            for n in ad.get("notes", {}).get(str(guild_id), {}).get(str(user_id), []):
                notes.append(n)
        except Exception:
            pass
        return warns, cases, notes

    @commands.command(name="pw", aliases=["player", "dossier", "dosye"])
    @commands.has_permissions(moderate_members=True)
    async def pw(self, ctx, user: discord.Member = None):
        """Полное досье пользователя: предупреждения, наказания, заметки, оценка."""
        user = user or ctx.author
        warns, cases, notes = self._collect_mod_data(ctx.guild.id, user.id)
        score = _compute_score(len(warns), cases)
        score_text = _score_text(score)

        # Показываем карточку (если PIL доступен) + embed с деталями
        embed = discord.Embed(
            title=f"📋 Досье: {user.display_name}",
            description=(
                f"`{user.id}`\n\n"
                f"**⚠️ Предупреждения:** {len(warns)}\n"
                f"**🛠 Наказания:** {len(cases)}\n"
                f"**📝 Заметки:** {len(notes)}\n\n"
                f"**Оценка:** {score}/100 — **{score_text}**"
            ),
            color=0x3498DB,
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.set_footer(text=f"{ctx.guild.name} • Aether Модерация")

        files = []
        view = None
        if _PIL_OK:
            try:
                buf = generate_pw_card(
                    user.display_name, user.id, user.display_avatar.url,
                    len(warns), cases, len(notes), score, score_text, user
                )
                files = [discord.File(buf, filename="dossier.png")]
                embed.set_image(url="attachment://dossier.png")
            except Exception as e:
                log.warning(f"pw card gen error: {e}")

        view = PWView(self, user, warns, cases, notes)
        await ctx.send(embed=embed, files=files, view=view)


# ═══════════════════════════════════════════════════════════════════
#  SELECT-МЕНЮ для !pw (категории досье)
# ═══════════════════════════════════════════════════════════════════
class PWCategorySelect(discord.ui.Select):
    """Выбор категории досье."""

    def __init__(self, cog, user, warns, cases, notes):
        self.cog = cog
        self.user = user
        self.warns = warns
        self.cases = cases
        self.notes = notes
        options = [
            discord.SelectOption(label="Предупреждения", value="warns", description="Все предупреждения и причины"),
            discord.SelectOption(label="Наказания", value="cases", description="Мьюты, баны, кики и причины"),
            discord.SelectOption(label="Заметки", value="notes", description="Заметки модераторов"),
            discord.SelectOption(label="Оценка", value="score", description="Общая характеристика /100"),
        ]
        super().__init__(placeholder="Выберите раздел досье...", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        choice = self.values[0]
        e = discord.Embed(
            title=f"📋 Досье: {self.user.display_name}",
            color=0x3498DB,
            timestamp=datetime.now(timezone.utc)
        )
        e.set_thumbnail(url=self.user.display_avatar.url)
        e.set_footer(text=f"{interaction.guild.name} • Aether Модерация")

        if choice == "warns":
            if not self.warns:
                e.description = "У пользователя нет предупреждений."
            else:
                desc = f"**Всего: {len(self.warns)}**\n\n"
                for w in reversed(self.warns[-10:]):
                    desc += f"**#{w.get('id')}** — {w.get('reason','?')}\n-# {str(w.get('timestamp',''))[:10]} · {w.get('mod','?')}\n\n"
                e.description = desc
        elif choice == "cases":
            if not self.cases:
                e.description = "Нет записей о наказаниях."
            else:
                desc = f"**Всего: {len(self.cases)}**\n\n"
                for c in reversed(self.cases[-10:]):
                    act = str(c.get("action", "?")).upper()
                    desc += f"**{act}** — {c.get('reason','?')}\n-# {str(c.get('timestamp',''))[:10]}\n\n"
                e.description = desc
        elif choice == "notes":
            if not self.notes:
                e.description = "Заметок нет."
            else:
                desc = f"**Всего: {len(self.notes)}**\n\n"
                for n in reversed(self.notes[-10:]):
                    desc += f"**•** {n.get('note','?')}\n-# {str(n.get('timestamp',''))[:10]} · {n.get('mod','?')}\n\n"
                e.description = desc
        else:  # score
            score = _compute_score(len(self.warns), self.cases)
            st = _score_text(score)
            color = 0x2ECC71 if score >= 60 else 0xF39C12 if score >= 30 else 0xE74C3C
            e.color = color
            e.description = (
                f"**Оценка: {score}/100 — {st}**\n\n"
                f"• Предупреждения: **{len(self.warns)}** (каждое −12)\n"
                f"• Наказания: **{len(self.cases)}** (мут/кик −18, бан −25)\n\n"
                f"Шкала:\n• 80–100 — Хорошо\n• 50–79 — Удовлетворительно\n• 25–49 — Плохо\n• 0–24 — Очень плохо"
            )

        await interaction.response.edit_message(embed=e, view=PWView(self.cog, self.user, self.warns, self.cases, self.notes))


class PWView(discord.ui.View):
    """View для досье — select меню категорий."""

    def __init__(self, cog, user, warns, cases, notes):
        super().__init__(timeout=300)
        self.add_item(PWCategorySelect(cog, user, warns, cases, notes))


async def setup(bot):
    await bot.add_cog(warnings(bot))
    log.info("Warnings загружен (database)")
