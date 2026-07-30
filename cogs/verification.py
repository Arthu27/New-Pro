"""
Aether — Doğrulama (Verification) — Gözlemci / opt-in modu
---------------------------------------------------------
Varsayılan: KAPALI. Yeni gelen kullanıcılara otomatik hiçbir şey YAPILMAZ:
  * Captcha kodu gösterilmez
  * "Проверка" / "Onaylandı" rolü VERILMEZ
  * Zaman aşımında KICK YAPILMAZ
  * Sunucu sahibi panelden açmadıkça sistem sessiz kalır

Açmak için: `/verify-toggle enabled:true` ya da panelden.
"""

import discord
from discord.ext import commands
from discord import app_commands
import json
import os


VERIFY_CONFIG_FILE = "data/verification_config.json"


def _load_global_state() -> dict:
    """Global olarak verification sistemi açık mı kapalı mı?"""
    if not os.path.exists(VERIFY_CONFIG_FILE):
        return {"enabled": False, "kick_timeout_minutes": 0}  # 0 = kick yok
    try:
        with open(VERIFY_CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"enabled": False, "kick_timeout_minutes": 0}
        return data
    except Exception:
        return {"enabled": False, "kick_timeout_minutes": 0}


def _save_global_state(state: dict):
    os.makedirs("data", exist_ok=True)
    with open(VERIFY_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


class Verification(commands.Cog):
    """İsteğe bağlı captcha/rol sistemi. Varsayılan KAPALI."""

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        state = _load_global_state()
        # KAPALI ise hiçbir şey yapma
        if not state.get("enabled", False):
            return
        if member.bot:
            return

        guild = member.guild
        unverified_role = discord.utils.get(guild.roles, name="Проверка")
        verified_role = discord.utils.get(guild.roles, name="Onaylandı")

        # Sadece bilgilendirme — otomatik rol/kick YOK
        try:
            await member.send(
                f"👋 {guild.name} sunucusuna hoş geldin!\n"
                f"Doğrulama gerekli ise lütfen sunucudaki talimatları takip et."
            )
        except Exception:
            pass
        # Not: kick/rol-atama/kanal-oluşturma gibi hiçbir otomatik aksiyon YOK.

    @app_commands.command(name="verify-toggle", description="Verification sistemini aç/kapat (gözlemci modunda)")
    @app_commands.checks.has_permissions(administrator=True)
    async def verify_toggle(self, interaction: discord.Interaction, enabled: bool):
        state = _load_global_state()
        state["enabled"] = enabled
        state["updated_by"] = str(interaction.user)
        _save_global_state(state)
        await interaction.response.send_message(
            f"🔐 Verification sistemi **{'AÇIK' if enabled else 'KAPALI'}**.\n"
            + ("⚠️ Bot otomatik captcha/rol/kick YAPMAYACAK — sadece bilgilendirme." if enabled else "✅ Artık yeni gelenler için hiçbir otomatik işlem yapılmayacak."),
            ephemeral=True,
        )

    @app_commands.command(name="verify-status", description="Verification sisteminin anlık durumunu gösterir")
    async def verify_status(self, interaction: discord.Interaction):
        state = _load_global_state()
        e = discord.Embed(
            title="🔐 Verification — Durum",
            color=0x2ECC71 if state.get("enabled") else 0x95A5A6,
        )
        e.add_field(name="Sistem", value="✅ Açık" if state.get("enabled") else "❌ Kapalı", inline=True)
        e.add_field(name="Otomatik aksiyon", value="❌ YOK (gözlemci modu)", inline=True)
        e.add_field(name="Son güncelleme", value=state.get("updated_by", "—"), inline=True)
        e.description = (
            "Bu cog gözlemci modunda: bot kimseye otomatik captcha/rol/kick UYGULAMAZ. "
            "Sadece sen `/verify-toggle enabled:true` dersen bilgilendirme DM'i atar."
        )
        await interaction.response.send_message(embed=e, ephemeral=True)


async def setup(bot):
    await bot.add_cog(
        Verification(bot),
        guilds=[
            discord.Object(id=1421244140359909513),
            discord.Object(id=1107038411895881788),
        ],
    )
