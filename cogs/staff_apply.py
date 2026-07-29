import discord
from discord.ext import commands
from discord import app_commands
import json
import os
from datetime import datetime, timezone
from cogs.embed_utils import _divider, now_ts

APPLY_CHANNEL_ID = 1484308081302306846
APPS_FILE = "data/staff_apps.json"

# Подтвердитьnınca verilecek roleler (ID listesi)
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


class StaffApplyModal(discord.ui.Modal, title="⚔️ Правоli Заявка Formu"):
    yas = discord.ui.TextInput(label="Yaşınız", placeholder="Örn: 18", max_length=3)
    tecrube = discord.ui.TextInput(
        label="Moderasyon Tecrübeniz",
        placeholder="Daha önce hangi serverlarda right_btn oldunuz?",
        style=discord.TextStyle.paragraph, max_length=500
    )
    neden = discord.ui.TextInput(
        label="Neden Правоli Olmak İstiyorsunuz?",
        placeholder="Motivasyonunuzu açıklayın...",
        style=discord.TextStyle.paragraph, max_length=600
    )
    activity_input = discord.ui.TextInput(
        label="Günlük Активенlik (час)",
        placeholder="Örn: 3-4 час",
        max_length=50
    )
    ekstra = discord.ui.TextInput(
        label="Добавитьmek İstedikleriniz",
        placeholder="Kendiniz hakkında ekstra info...",
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
                "neden": self.neden.value,
                "activity_input": self.activity_input.value,
                "ekstra": self.ekstra.value or "—"
            },
            "message_id": None,
            "reviewed_by": None,
            "review_note": None
        }

        apps[app_id] = app_data
        save_apps(apps)

        # Заявка channelına отправить
        channel = interaction.guild.get_channel(APPLY_CHANNEL_ID)
        if not channel:
            await interaction.response.send_message("❌ Заявка channelı bulunamadı.", ephemeral=True)
            return

        embed = discord.Embed(
            title="📋 YENİ YETKİLİ BAŞVURUSU",
            color=0xDC143C,
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_author(
            name=f"{interaction.user.display_name} ({interaction.user})",
            icon_url=interaction.user.display_avatar.url
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)

        embed.add_field(name="👤 Пользователь", value=f"{interaction.user.mention}\n`{interaction.user.id}`", inline=True)
        embed.add_field(name="🎂 Yaş", value=self.yas.value, inline=True)
        embed.add_field(name="⏰ Günlük Активенlik", value=self.activity_input.value, inline=True)
        embed.add_field(name="🏆 Moderasyon Tecrübesi", value=f"```{self.tecrube.value}```", inline=False)
        embed.add_field(name="💬 Neden Правоli Olmak İstiyor?", value=f"```{self.neden.value}```", inline=False)
        if self.ekstra.value:
            embed.add_field(name="📝 Ekstra Информация", value=f"```{self.ekstra.value}```", inline=False)

        embed.set_footer(
            text=f"Заявка ID: {app_id} • {interaction.guild.name}",
            icon_url=interaction.guild.icon.url if interaction.guild.icon else None
        )

        view = StaffReviewView(app_id)
        msg = await channel.send(embed=embed, view=view)

        # Сообщение ID'sini сохранить
        apps[app_id]["message_id"] = str(msg.id)
        save_apps(apps)

        await interaction.response.send_message(
            "✅ Заявкаn alındı! Правоliler inceleyecek, sonucu DM ile bildirilecek.",
            ephemeral=True
        )


class StaffReviewView(discord.ui.View):
    def __init__(self, app_id: str = None):
        super().__init__(timeout=None)
        self.app_id = app_id

    def get_app_id_from_custom(self, custom_id):
        # custom_id: "approve_APPID" veya "reject_APPID"
        parts = custom_id.split("_", 1)
        return parts[1] if len(parts) == 2 else None

    @discord.ui.button(label="✅ Подтвердить", style=discord.ButtonStyle.success, custom_id="staff_approve")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Правоn yok.", ephemeral=True)
            return

        # Embed'den app_id найти
        app_id = None
        if interaction.message and interaction.message.embeds:
            footer = interaction.message.embeds[0].footer.text or ""
            for part in footer.split("•"):
                part = part.strip()
                if part.startswith("Заявка ID:"):
                    app_id = part.replace("Заявка ID:", "").strip()

        if not app_id:
            await interaction.response.send_message("❌ Заявка ID bulunamadı.", ephemeral=True)
            return

        apps = load_apps()
        if app_id not in apps:
            await interaction.response.send_message("❌ Заявка bulunamadı.", ephemeral=True)
            return

        apps[app_id]["status"] = "approved"
        apps[app_id]["reviewed_by"] = str(interaction.user)
        save_apps(apps)

        # Пользователю role ver
        try:
            member = interaction.guild.get_member(int(apps[app_id]["user_id"]))
            if not member:
                member = await interaction.guild.fetch_member(int(apps[app_id]["user_id"]))
            if member:
                for role_id in STAFF_ROLE_IDS:
                    role = interaction.guild.get_role(role_id)
                    if role:
                        await member.add_roles(role, reason=f'Правоli заявкаsu подтвердитьndı - {interaction.user}')
        except Exception as e:
            print(f'[StaffApply] Role verme Ошибкаsı: {e}')

        # Embed güncelle
        embed = interaction.message.embeds[0]
        embed.color = 0x2ECC71
        embed.title = "✅ BAŞVURU ONAYLANDI"
        embed.add_field(name="✅ Подтвердитьyan", value=f"{interaction.user.mention}", inline=True)

        await interaction.message.edit(embed=embed, view=None)

        # Пользователю DM
        try:
            user = await interaction.client.fetch_user(int(apps[app_id]["user_id"]))
            ts = int(datetime.now(timezone.utc).timestamp())
            dm_embed = discord.Embed(
                title="🎉  Правоli Заявка одобрена!",
                color=0x2ECC71,
                timestamp=datetime.now(timezone.utc)
            )
            dm_embed.description = (
                f"```ansi\n\u001b[1;32m✔ BAŞVURUN ONAYLANDI\u001b[0m\n```\n"
                f"{_divider()}\n\n"
                f"**{interaction.guild.name}** serversundaki right_btn заявка **подтвердитьndı**! 🎊\n\n"
                "> Серверya girerek right_btnlerle iletişime geçebilirsin.\n"
                "> Поискmıza hoş geldin, başarılar dileriz! 💪\n\n"
                f"{_divider()}"
            )
            dm_embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
            dm_embed.add_field(name="✅ Статус", value="```Подтвердитьndı```", inline=True)
            dm_embed.add_field(name="👮 İnceleyen", value=f"```{interaction.user.display_name}```", inline=True)
            dm_embed.add_field(name="🕐 Дата", value=f"<t:{ts}:F>", inline=False)
            dm_embed.add_field(name="💡 Последнийraki Имяım", value="*Серверya girerek right_btn roleünü almak için controlle iletişime geç.*", inline=False)
            dm_embed.set_image(url="https://media.tenor.com/ZBDpMFBMFpkAAAAC/celebration-party.gif")
            dm_embed.set_footer(
                text=f"Aether Правоli • {interaction.guild.name}",
                icon_url=interaction.guild.icon.url if interaction.guild.icon else None
            )
            await user.send(embed=dm_embed)
        except:
            pass

        await interaction.response.send_message("✅ Заявка подтвердитьndı, userya DM отправитьildi.", ephemeral=True)

    @discord.ui.button(label="❌ Отклонить", style=discord.ButtonStyle.danger, custom_id="staff_reject")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Правоn yok.", ephemeral=True)
            return

        await interaction.response.send_modal(RejectReasonModal(interaction.message))


class RejectReasonModal(discord.ui.Modal, title="❌ Red Sebebi"):
    reason = discord.ui.TextInput(
        label="Red Sebebi",
        placeholder="Заявкаyu neden reddediyorsunuz?",
        style=discord.TextStyle.paragraph,
        max_length=500
    )

    def __init__(self, message: discord.Message):
        super().__init__()
        self.message = message

    async def on_submit(self, interaction: discord.Interaction):
        # app_id найти
        app_id = None
        if self.message.embeds:
            footer = self.message.embeds[0].footer.text or ""
            for part in footer.split("•"):
                part = part.strip()
                if part.startswith("Заявка ID:"):
                    app_id = part.replace("Заявка ID:", "").strip()

        apps = load_apps()
        if app_id and app_id in apps:
            apps[app_id]["status"] = "rejected"
            apps[app_id]["reviewed_by"] = str(interaction.user)
            apps[app_id]["review_note"] = self.reason.value
            save_apps(apps)

            # Пользователю DM
            try:
                user = await interaction.client.fetch_user(int(apps[app_id]["user_id"]))
                ts = int(datetime.now(timezone.utc).timestamp())
                dm_embed = discord.Embed(
                    title="❌  Правоli Заявка отклонена",
                    color=0xE74C3C,
                    timestamp=datetime.now(timezone.utc)
                )
                dm_embed.description = (
                    f"```ansi\n\u001b[1;31m✘ BAŞVURUN REDDEDİLDİ\u001b[0m\n```\n"
                    f"{_divider()}\n\n"
                    f"**{interaction.guild.name}** serversundaki right_btn заявка **reddedildi**.\n\n"
                    "> Daha sonra tekrar başvurabilirsin.\n"
                    "> Kendini geliştirmeye devam et! 💪\n\n"
                    f"{_divider()}"
                )
                dm_embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
                dm_embed.add_field(name="❌ Статус", value="```Reddedildi```", inline=True)
                dm_embed.add_field(name="👮 İnceleyen", value=f"```{interaction.user.display_name}```", inline=True)
                dm_embed.add_field(name="📝 Red Sebebi", value=f"```{self.reason.value}```", inline=False)
                dm_embed.add_field(name="🕐 Дата", value=f"<t:{ts}:F>", inline=False)
                dm_embed.add_field(name="💡 Информация", value="*Belirli bir süre sonra tekrar başvurabilirsin.*", inline=False)
                dm_embed.set_image(url="https://media.tenor.com/x8v1oNUOmg4AAAAC/ban-hammer.gif")
                dm_embed.set_footer(
                    text=f"{interaction.guild.name} • Правоli Sistemi",
                    icon_url=interaction.guild.icon.url if interaction.guild.icon else None
                )
                await user.send(embed=dm_embed)
            except:
                pass

        # Embed güncelle
        embed = self.message.embeds[0]
        embed.color = 0xE74C3C
        embed.title = "❌ BAŞVURU REDDEDİLDİ"
        embed.add_field(name="❌ Reddeden", value=f"{interaction.user.mention}", inline=True)
        embed.add_field(name="📝 Причина", value=self.reason.value, inline=False)

        await self.message.edit(embed=embed, view=None)
        await interaction.response.send_message("❌ Заявка reddedildi.", ephemeral=True)


class StaffApply(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        bot.add_view(StaffReviewView())  # Persistent

    @app_commands.command(name="staff-basvuru", description="Правоli заявка formunu aç")
    async def staff_apply(self, interaction: discord.Interaction):
        # Zaten baddyen заявкаsu var mı?
        apps = load_apps()
        uid = str(interaction.user.id)
        for app in apps.values():
            if app["user_id"] == uid and app["status"] == "pending":
                await interaction.response.send_message(
                    "⚠️ Zaten baddyen bir заявка var! sonuçlanmasını badd.",
                    ephemeral=True
                )
                return

        await interaction.response.send_modal(StaffApplyModal())

    @app_commands.command(name="staff-basvurular", description="Tüm заявкаları listele")
    @app_commands.checks.has_permissions(administrator=True)
    async def staff_list(self, interaction: discord.Interaction, status: str = "pending"):
        apps = load_apps()
        filtered = [a for a in apps.values() if a.get("status") == status and a.get("guild_id") == str(interaction.guild.id)]

        if not filtered:
            await interaction.response.send_message(f"'{status}' statusunda заявка yok.", ephemeral=True)
            return

        embed = discord.Embed(title=f"📋 Заявкаlar — {status.upper()}", color=0xDC143C)
        for app in filtered[-10:]:
            embed.add_field(
                name=f"{app['display_name']} ({app['user_name']})",
                value=f"ID: `{app['app_id']}`\nДата: <t:{int(datetime.fromisoformat(app['timestamp']).timestamp())}:R>",
                inline=False
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(StaffApply(bot), guilds=[discord.Object(id=1421244140359909513), discord.Object(id=1107038411895881788)])
