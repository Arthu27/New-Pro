"""
Aether — Re-Join Roles (Sunucudan çıkıp giren üyeye otomatik rol geri verme)
----------------------------------------------------------------------------
Discord'da üye sunucudan ayrılınca tüm rolleri silinir. Bu cog, panelden
seçilen rolleri ayrılmadan ÖNCE kaydeder ve geri döndüğünde otomatik geri
verir. Sadece sahip izin verdiği (tracked) roller izlenir; diğerleri kayıt
dışıdır.

Yapı:
  data/rejoin_<guild_id>.json
    {
      "enabled": bool,
      "tracked_role_ids": [str, ...],
      "leave_log": [
        {"user_id": str, "roles": [str, ...], "left_at": iso, "restored": bool}
      ]
    }

Davranış:
  * `enabled: false` veya `tracked_role_ids: []` ise HİÇBİR ŞEY yapılmaz.
  * Üye ayrılınca: tracked roller `leave_log`'a yazılır.
  * Üye geri gelince: leave_log'da en yeni kaydı bul, tracked rolleri geri ver.
  * Geri veremediği rolleri (bot yetkisi yok / rol silinmiş) alert kanalına yazar.
"""

import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import time
from datetime import datetime, timezone


def _config_path(guild_id: int) -> str:
    return f"data/rejoin_{guild_id}.json"


def _load(guild_id: int) -> dict:
    p = _config_path(guild_id)
    if not os.path.exists(p):
        return {"enabled": False, "tracked_role_ids": [], "leave_log": []}
    try:
        with open(p, "r", encoding="utf-8") as f:
            d = json.load(f)
        if not isinstance(d, dict):
            return {"enabled": False, "tracked_role_ids": [], "leave_log": []}
        d.setdefault("enabled", False)
        d.setdefault("tracked_role_ids", [])
        d.setdefault("leave_log", [])
        if not isinstance(d["tracked_role_ids"], list):
            d["tracked_role_ids"] = []
        if not isinstance(d["leave_log"], list):
            d["leave_log"] = []
        return d
    except Exception:
        return {"enabled": False, "tracked_role_ids": [], "leave_log": []}


def _save(guild_id: int, data: dict):
    os.makedirs("data", exist_ok=True)
    # leave_log'u 200 kayıtla sınırla
    if len(data.get("leave_log", [])) > 200:
        data["leave_log"] = data["leave_log"][-200:]
    with open(_config_path(guild_id), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


class ReJoinRoles(commands.Cog):
    """Sunucudan ayrılıp geri dönen üyeye rol geri verme (gözlemci + opt-in)."""

    def __init__(self, bot):
        self.bot = bot

    # ── Üye ayrıldı: rolleri kaydet ────────────────────────────────────────
    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if member.bot:
            return
        cfg = _load(member.guild.id)
        if not cfg.get("enabled") or not cfg.get("tracked_role_ids"):
            return

        tracked = {str(rid) for rid in cfg["tracked_role_ids"] if str(rid).isdigit()}
        # Üyenin şu anki tracked rollerini filtrele
        kept_roles = [
            r.id for r in member.roles
            if r.id != member.guild.id  # @everyone değil
            and str(r.id) in tracked
        ]
        if not kept_roles:
            return  # izlenen rolü yoktu, loglama

        cfg["leave_log"].append({
            "user_id": str(member.id),
            "user_tag": str(member),
            "roles": [str(rid) for rid in kept_roles],
            "left_at": datetime.now(timezone.utc).isoformat(),
            "restored": False,
        })
        _save(member.guild.id, cfg)

    # ── Üye geri geldi: rolleri geri ver ───────────────────────────────────
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        cfg = _load(member.guild.id)
        if not cfg.get("enabled") or not cfg.get("tracked_role_ids"):
            return

        # Bu kullanıcı için en yeni geri verilmemiş kaydı bul
        pending = None
        for entry in reversed(cfg["leave_log"]):
            if entry.get("user_id") == str(member.id) and not entry.get("restored"):
                pending = entry
                break
        if not pending:
            return

        tracked = {str(rid) for rid in cfg["tracked_role_ids"] if str(rid).isdigit()}
        to_restore_ids = [rid for rid in pending.get("roles", []) if str(rid) in tracked]
        if not to_restore_ids:
            return

        # Bot'un verebileceği rolleri filtrele
        guild = member.guild
        bot_member = guild.get_member(self.bot.user.id)
        bot_top = bot_member.top_role if bot_member else None

        restored = []
        skipped = []
        for rid in to_restore_ids:
            role = guild.get_role(int(rid))
            if not role:
                skipped.append((rid, "rol silinmiş"))
                continue
            if role >= bot_top:
                skipped.append((rid, "bot yetkisi yetersiz"))
                continue
            try:
                await member.add_roles(role, reason="Re-Join Roles: otomatik geri verildi")
                restored.append(rid)
            except (discord.Forbidden, discord.HTTPException) as e:
                skipped.append((rid, str(e)))

        # Log'u güncelle
        pending["restored"] = True
        pending["restored_at"] = datetime.now(timezone.utc).isoformat()
        pending["restored_ok"] = restored
        pending["restored_fail"] = [{"role": r, "reason": why} for r, why in skipped]
        _save(member.guild.id, cfg)

        # Kanal bildirimi (varsa)
        if skipped and cfg.get("alert_channel_id"):
            ch = guild.get_channel(int(cfg["alert_channel_id"]))
            if ch:
                lines = [f"• <@&{r}>: {why}" for r, why in skipped]
                e = discord.Embed(
                    title="♻️ Re-Join Roles — kısmi geri verim",
                    description=(
                        f"{member.mention} geri döndü ama bazı roller verilemedi:\n"
                        + "\n".join(lines)
                        + f"\n\nVerilen: **{len(restored)}** | Başarısız: **{len(skipped)}**"
                    ),
                    color=discord.Color.orange(),
                )
                try:
                    await ch.send(embed=e)
                except Exception:
                    pass

    # ── Slash komutları ───────────────────────────────────────────────────
    @app_commands.command(name="rejoin-toggle", description="Re-Join Roles sistemini aç/kapat")
    @app_commands.checks.has_permissions(administrator=True)
    async def rejoin_toggle(self, interaction: discord.Interaction, enabled: bool):
        cfg = _load(interaction.guild.id)
        cfg["enabled"] = enabled
        _save(interaction.guild.id, cfg)
        await interaction.response.send_message(
            f"♻️ Re-Join Roles **{'AÇIK' if enabled else 'KAPALI'}**.",
            ephemeral=True,
        )

    @app_commands.command(name="rejoin-status", description="Re-Join Roles sisteminin anlık durumu")
    async def rejoin_status(self, interaction: discord.Interaction):
        cfg = _load(interaction.guild.id)
        e = discord.Embed(
            title="♻️ Re-Join Roles — Durum",
            color=0x2ECC71 if cfg.get("enabled") else 0x95A5A6,
        )
        e.add_field(name="Sistem", value="✅ Açık" if cfg.get("enabled") else "❌ Kapalı", inline=True)
        tracked = cfg.get("tracked_role_ids", [])
        e.add_field(name="İzlenen rol sayısı", value=str(len(tracked)), inline=True)
        log = cfg.get("leave_log", [])
        pending = sum(1 for x in log if not x.get("restored"))
        e.add_field(name="Bekleyen", value=str(pending), inline=True)
        e.add_field(name="Toplam kayıt", value=str(len(log)), inline=True)
        await interaction.response.send_message(embed=e, ephemeral=True)


async def setup(bot):
    await bot.add_cog(
        ReJoinRoles(bot),
        guilds=[
            discord.Object(id=1421244140359909513),
            discord.Object(id=1107038411895881788),
        ],
    )
