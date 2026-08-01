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
from datetime import datetime, timezone

from logger import get_logger
log = get_logger("staff_apply")


APPLY_CHANNEL_ID = Config.APPLY_CHANNEL_ID
APPS_FILE = "data/staff_apps.json"


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
            "username": str(interaction.user),
            "display_name": interaction.user.display_name,
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
            placeholder="Выберите роль",
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

    @app_commands.command(name="staff-panel", description="Создать панель набора в команду")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def staff_panel(self, interaction: discord.Interaction):
        """Создать embed-панель для набора"""
        embed = discord.Embed(
            title="Набор в команду сервера",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )
        embed.description = (
            "Мы ищем людей, готовых внести свой вклад и помочь нам "
            "сделать наше сообщество лучше.\n\n"
            "Независимо от вашего опыта, у нас найдётся место для вас.\n"
            "Отправляйте заявку, чтобы стать частью нашей дружной команды "
            "и весело провести время вместе!"
        )
        embed.add_field(
            name="НАБОРЫ НА СЕРВЕР",
            value=(
                "К кому хотите присоединиться?\n\n"
                "**Moderator** — Модерация сервера и участников\n"
                "**Chat Control** — Контроль чатов и порядка\n"
                "**Helper** — Помощь участникам сервера"
            ),
            inline=False
        )
        embed.set_footer(text="Подавайте заявку")

        view = StaffApplyView()
        await interaction.response.send_message(embed=embed, view=view)
        log.info(f"Staff panel создана в {interaction.channel}")

    @commands.Cog.listener()
    async def on_ready(self):
        # Регистрируем persistent view
        self.bot.add_view(StaffApplyView())


async def setup(bot):
    await bot.add_cog(StaffApply(bot))
    log.info("StaffApply загружен")
