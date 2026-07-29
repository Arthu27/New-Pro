import discord
from discord.ext import commands
from discord import app_commands
import json
import os
from datetime import datetime, timezone
from cogs.embed_utils import _divider, now_ts

APPLY_CHANNEL_ID = 1484308081302306846
APPS_FILE = "data/staff_apps.json"

# Роли при одобрении
STAFF_ROLE_IDS = [1384282749338386593, 1434986280399147069]

def load_apps():
    os.makedirs("data", exist_ok=True)
    if os.path.exists(APPS_FILE):
        with open(APPS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_apps(data):
    with open(APPS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


class StaffApplyModal(discord.ui.Modal, title="📋 Заявка в модераторы"):
    yas = discord.ui.TextInput(label="Ваш возраст", placeholder="Например: 18", max_length=3)
    tecrube = discord.ui.TextInput(
        label="Опыт модерации",
        placeholder="Укажите сервер и вашу должность",
        style=discord.TextStyle.paragraph, max_length=500
    )
    why = discord.ui.TextInput(
        label="Почему именно вы?",
        placeholder="Почему вы хотите стать модератором?",
        style=discord.TextStyle.paragraph, max_length=600
    )
    activity_input = discord.ui.TextInput(
        label="Онлайн в день (часы)",
        placeholder="Например: 4-5 часов",
        max_length=50
    )
    ekstra = discord.ui.TextInput(
        label="Дополнительно",
        placeholder="Что хотите добавить от себя...",
        style=discord.TextStyle.paragraph,
        required=False, max_length=400
    )

    async def on_submit(self, interaction: discord.Interaction):
        apps = load_apps()
        app_id = str(int(datetime.now(timezone.utc).timestamp()))
        uid = str(interaction.user.id)

        app_data = {
            "app_id": app_id,
            "user_id": uid,
            "user_name": str(interaction.user),
            "display_name": interaction.user.display_name,
            "avatar": str(interaction.user.display_avatar.url),
            "guild_id": str(interaction.guild.id),
            "guild_name": interaction.guild.name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "pending",
            "answers": {
                "yas": self.yas.value,
                "tecrube": self.tecrube.value,
                "why": self.why.value,
                "activity_input": self.activity_input.value,
                "ekstra": self.ekstra.value or "—"
            },
            "message_id": None,
            "reviewed_by": None,
            "review_note": None
        }

        apps[app_id] = app_data
        save_apps(apps)

        channel = interaction.guild.get_channel(APPLY_CHANNEL_ID)
        if not channel:
            await interaction.response.send_message("❌ Канал для заявок не найден.", ephemeral=True)
            return

        embed = discord.Embed(color=0x2B2D31, timestamp=datetime.now(timezone.utc))
        embed.description = (
            f"### 📋 Заявка в модераторы\n"
            f"**Кандидат:** {interaction.user.mention} (`{interaction.user.id}`)\n"
            f"**Возраст:** `{self.yas.value}`  •  **Онлайн:** `{self.activity_input.value}`\n\n"
            f"**Опыт модерации**\n> {self.tecrube.value}\n\n"
            f"**Мотивация**\n> {self.why.value}\n"
        )
        if self.ekstra.value and self.ekstra.value != "—":
            embed.description += f"\n**Дополнительно**\n> {self.ekstra.value}\n"
        
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        if interaction.guild.icon:
            embed.set_footer(text=f"ID заявки: {app_id} • {interaction.guild.name}", icon_url=interaction.guild.icon.url)
        else:
            embed.set_footer(text=f"ID заявки: {app_id} • {interaction.guild.name}")

        view = StaffReviewView(app_id)
        msg = await channel.send(embed=embed, view=view)

        apps[app_id]["message_id"] = str(msg.id)
        save_apps(apps)

        await interaction.response.send_message(
            "✅ Ваша заявка отправлена! Администрация рассмотрит ее, результат придет в ЛС.",
            ephemeral=True
        )


class StaffReviewView(discord.ui.View):
    def __init__(self, app_id: str = None):
        super().__init__(timeout=None)
        self.app_id = app_id

    def get_app_id_from_custom(self, custom_id):
        parts = custom_id.split("_", 1)
        return parts[1] if len(parts) == 2 else None

    @discord.ui.button(label="✅ Одобрить", style=discord.ButtonStyle.success, custom_id="staff_approve")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ У вас нет прав администратора.", ephemeral=True)
            return

        app_id = None
        if interaction.message and interaction.message.embeds:
            footer = interaction.message.embeds[0].footer.text or ""
            for part in footer.split("•"):
                part = part.strip()
                if part.startswith("ID заявки:"):
                    app_id = part.replace("ID заявки:", "").strip()

        if not app_id:
            await interaction.response.send_message("❌ ID заявки не найден.", ephemeral=True)
            return

        apps = load_apps()
        if app_id not in apps:
            await interaction.response.send_message("❌ Заявка не найдена в базе.", ephemeral=True)
            return

        apps[app_id]["status"] = "approved"
        apps[app_id]["reviewed_by"] = str(interaction.user)
        save_apps(apps)

        try:
            member = interaction.guild.get_member(int(apps[app_id]["user_id"]))
            if not member:
                member = await interaction.guild.fetch_member(int(apps[app_id]["user_id"]))
            if member:
                for role_id in STAFF_ROLE_IDS:
                    role = interaction.guild.get_role(role_id)
                    if role:
                        await member.add_roles(role, reason=f'Заявка одобрена — {interaction.user}')
        except Exception as e:
            print(f'[StaffApply] Ошибка выдачи роли: {e}')

        embed = interaction.message.embeds[0]
        embed.color = 0x2ECC71
        embed.description = embed.description.replace("### 📋 Заявка в модераторы", "### 🟢 Заявка одобрена")
        embed.description += f"\n\n**Одобрено:** {interaction.user.mention}"

        await interaction.message.edit(embed=embed, view=None)

        try:
            user = await interaction.client.fetch_user(int(apps[app_id]["user_id"]))
            ts = int(datetime.now(timezone.utc).timestamp())
            dm_embed = discord.Embed(color=0x2ECC71, timestamp=datetime.now(timezone.utc))
            dm_embed.description = (
                f"### 🟢 Заявка одобрена!\n\n"
                f"Ваша заявка на пост модератора на сервере **{interaction.guild.name}** была одобрена!\n\n"
                f"**Статус:** Одобрено\n"
                f"**Рассмотрел:** {interaction.user.display_name}\n"
                f"**Дата:** <t:{ts}:F>\n\n"
                f"Перейдите на сервер и свяжитесь с администрацией для получения роли модератора.\n"
                f"Добро пожаловать в команду и успехов!"
            )
            dm_embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
            await user.send(embed=dm_embed)
        except:
            pass

        await interaction.response.send_message("✅ Заявка одобрена, уведомление отправлено пользователю в ЛС.", ephemeral=True)

    @discord.ui.button(label="❌ Отклонить", style=discord.ButtonStyle.danger, custom_id="staff_reject")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ У вас нет прав администратора.", ephemeral=True)
            return

        await interaction.response.send_modal(RejectReasonModal(interaction.message))


class RejectReasonModal(discord.ui.Modal, title="Причина отклонения"):
    reason = discord.ui.TextInput(
        label="Причина отклонения",
        placeholder="Почему заявка отклонена?",
        style=discord.TextStyle.paragraph,
        max_length=500
    )

    def __init__(self, message: discord.Message):
        super().__init__()
        self.message = message

    async def on_submit(self, interaction: discord.Interaction):
        app_id = None
        if self.message.embeds:
            footer = self.message.embeds[0].footer.text or ""
            for part in footer.split("•"):
                part = part.strip()
                if part.startswith("ID заявки:"):
                    app_id = part.replace("ID заявки:", "").strip()

        apps = load_apps()
        if app_id and app_id in apps:
            apps[app_id]["status"] = "rejected"
            apps[app_id]["reviewed_by"] = str(interaction.user)
            apps[app_id]["review_note"] = self.reason.value
            save_apps(apps)

            try:
                user = await interaction.client.fetch_user(int(apps[app_id]["user_id"]))
                ts = int(datetime.now(timezone.utc).timestamp())
                dm_embed = discord.Embed(color=0xE74C3C, timestamp=datetime.now(timezone.utc))
                dm_embed.description = (
                    f"### 🔴 Заявка отклонена\n\n"
                    f"К сожалению, ваша заявка на пост модератора на сервере **{interaction.guild.name}** была отклонена.\n\n"
                    f"**Статус:** Отклонено\n"
                    f"**Рассмотрел:** {interaction.user.display_name}\n"
                    f"**Причина:** {self.reason.value}\n"
                    f"**Дата:** <t:{ts}:F>\n\n"
                    f"Вы можете подать заявку снова позже."
                )
                dm_embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
                await user.send(embed=dm_embed)
            except:
                pass

        embed = self.message.embeds[0]
        embed.color = 0xE74C3C
        embed.description = embed.description.replace("### 📋 Заявка в модераторы", "### 🔴 Заявка отклонена")
        embed.description += f"\n\n**Отклонено:** {interaction.user.mention}\n**Причина:** {self.reason.value}"

        await self.message.edit(embed=embed, view=None)
        await interaction.response.send_message("❌ Заявка отклонена.", ephemeral=True)


class StaffApply(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        bot.add_view(StaffReviewView())  # Persistent

    @app_commands.command(name="staff-basvuru", description="Открыть форму подачи заявки в модераторы")
    async def staff_apply_cmd(self, interaction: discord.Interaction):
        await interaction.response.send_modal(StaffApplyModal())

    @app_commands.command(name="staff-basvurular", description="Показать список всех заявок")
    @app_commands.checks.has_permissions(administrator=True)
    async def list_apps(self, interaction: discord.Interaction):
        apps = load_apps()
        if not apps:
            await interaction.response.send_message("❌ Нет поданных заявок.", ephemeral=True)
            return

        embed = discord.Embed(title="📋 Список заявок в модераторы", color=0x2B2D31, timestamp=datetime.now(timezone.utc))
        pending = [a for a in apps.values() if a["status"] == "pending"]
        approved = [a for a in apps.values() if a["status"] == "approved"]
        rejected = [a for a in apps.values() if a["status"] == "rejected"]

        embed.add_field(name="⏳ На рассмотрении", value=str(len(pending)), inline=True)
        embed.add_field(name="🟢 Одобрено", value=str(len(approved)), inline=True)
        embed.add_field(name="🔴 Отклонено", value=str(len(rejected)), inline=True)

        desc = ""
        for a in sorted(apps.values(), key=lambda x: x["timestamp"], reverse=True)[:10]:
            icon = "⏳" if a["status"] == "pending" else "🟢" if a["status"] == "approved" else "🔴"
            desc += f"{icon} **{a['display_name']}** (`{a['user_id']}`) — {a['status'].upper()}\n"

        if desc:
            embed.description = desc

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(StaffApply(bot))
