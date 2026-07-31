"""
Aether — AntiRaid / Raid Koruması
----------------------------------
Sürüm: "Gözlemci modu" (read-only).

Davranış:
  * Panelden ayarlanan `data/antiraid_<guild_id>.json` dosyasını canlı olarak okur.
  * Dosya her değiştiğinde otomatik reload edilir (mtime polling).
  * `join_raid`, `bot_protection`, `age_filter` flag'lerine göre davranır.
  * `raid_action` her zaman "alert" kabul edilir: bot kimseyi kick/ban/lockdown YAPMAZ,
    sadece ayarlanan alert kanalına (yoksa `mod-log`) embed gönderir.
  * `whitelist` içindeki user_id'ler tüm kontrollerden muaftır.

Tüm aksiyon kararları paneldeki /antiraid sayfasından yapılır; bu cog yalnızca
"kural motoru"dur, icra yetkisi yoktur.
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
from collections import defaultdict
import json
import os
import time
import logging
import asyncio

log = logging.getLogger("aether.antiraid")

# ─────────────────────────────────────────────────────────────────────────────
# Yardımcı: per-guild config cache (disk + mtime)
# ─────────────────────────────────────────────────────────────────────────────

class GuildAntiraidConfig:
    """Tek bir guild için antiraid ayarlarını diskten okuyan in-memory cache."""

    DEFAULTS = {
        "join_raid": False,
        "bot_protection": False,
        "webhook_protection": False,
        "delete_protection": False,
        "age_filter": False,
        "min_age": 5,
        "join_threshold": 5,        # kaç kişi / kaç saniye = raid
        "join_window": 10,          # saniye
        "raid_action": "alert",     # Sadece "alert" — diğerleri YOK sayılır
        "alert_channel_id": None,   # panelde ayarlanabilir
        "whitelist": [],            # user_id listesi — muaf
        "recent_events": [],        # son 20 olay (panelde gösterilir)
    }

    def __init__(self, guild_id: int):
        self.guild_id = guild_id
        self.path = f"data/antiraid_{guild_id}.json"
        self.data: dict = dict(self.DEFAULTS)
        self._mtime: float = 0.0
        self.reload()

    def reload(self) -> bool:
        """Diskten oku. Değişiklik yoksa False, değiştiyse True döndürür."""
        try:
            if not os.path.exists(self.path):
                return False
            mtime = os.path.getmtime(self.path)
            if mtime == self._mtime and self.data:
                return False
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            # bilinmeyen anahtarları da kabul et, eksik olanları default'la doldur
            merged = dict(self.DEFAULTS)
            merged.update(raw or {})
            self.data = merged
            self._mtime = mtime
            log.info("antiraid config reloaded for guild=%s: %s", self.guild_id,
                     {k: v for k, v in self.data.items() if k != "recent_events"})
            return True
        except Exception as e:
            log.warning("antiraid config reload failed for guild=%s: %s", self.guild_id, e)
            return False

    def is_whitelisted(self, user_id: int) -> bool:
        try:
            return int(user_id) in {int(x) for x in self.data.get("whitelist", []) or []}
        except Exception:
            return False

    def add_event(self, event: dict, limit: int = 20):
        events = self.data.setdefault("recent_events", [])
        events.insert(0, event)
        del events[limit:]
        # recent_events'i diske yaz ki panel anında görsün
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            self._mtime = os.path.getmtime(self.path)
        except Exception as e:
            log.warning("antiraid event persist failed for guild=%s: %s", self.guild_id, e)


# ─────────────────────────────────────────────────────────────────────────────
# Ana cog
# ─────────────────────────────────────────────────────────────────────────────

class AntiRaid(commands.Cog):
    """Gözlemci modunda AntiRaid — otomatik aksiyon yok, sadece alert."""

    def __init__(self, bot):
        self.bot = bot
        self.configs: dict[int, GuildAntiraidConfig] = {}
        # join_tracker ayrı tutulur; whitelist kontrolü için
        self.join_tracker: dict[int, list[tuple[float, int]]] = defaultdict(list)
        # her 5 saniyede bir config dosyalarını kontrol et
        self.config_watcher.start()

    def cog_unload(self):
        try:
            self.config_watcher.cancel()
        except Exception:
            pass

    # ── Per-guild config helper ──────────────────────────────────────────────

    def get_config(self, guild_id: int) -> GuildAntiraidConfig:
        cfg = self.configs.get(guild_id)
        if cfg is None:
            cfg = GuildAntiraidConfig(guild_id)
            self.configs[guild_id] = cfg
        else:
            cfg.reload()
        return cfg

    # ── Background: mtime polling ────────────────────────────────────────────

    @tasks.loop(seconds=5.0)
    async def config_watcher(self):
        # tüm izlenen guild'lerin dosyası değişti mi?
        for guild_id in list(self.configs.keys()):
            try:
                self.configs[guild_id].reload()
            except Exception as e:
                log.debug("watcher reload error guild=%s: %s", guild_id, e)
        # data/ dizininde yeni oluşmuş antiraid dosyalarını da yakala
        try:
            for name in os.listdir("data"):
                if not (name.startswith("antiraid_") and name.endswith(".json")):
                    continue
                if name == "antiraid.json":  # eski tek-dosya formatı, atla
                    continue
                try:
                    gid = int(name[len("antiraid_"):-len(".json")])
                except ValueError:
                    continue
                if gid not in self.configs:
                    self.configs[gid] = GuildAntiraidConfig(gid)
        except Exception:
            pass

    @config_watcher.before_loop
    async def before_config_watcher(self):
        await self.bot.wait_until_ready()

    # ── Alert gönderme yardımcısı ───────────────────────────────────────────

    async def _send_alert(self, guild: discord.Guild, cfg: GuildAntiraidConfig,
                          title: str, description: str, fields: list[tuple[str, str]] | None = None,
                          color: discord.Color = discord.Color.orange()):
        """Alert kanalına (yoksa mod-log'a, yoksa owner DM) embed gönder."""
        target = None
        cid = cfg.data.get("alert_channel_id")
        if cid:
            try:
                target = guild.get_channel(int(cid)) or await guild.fetch_channel(int(cid))
            except Exception:
                target = None
        if target is None:
            target = discord.utils.get(guild.text_channels, name="mod-log")
        if target is None:
            # son çare: sunucu sahibine DM
            try:
                if guild.owner:
                    await guild.owner.send(f"⚠️ **Antiraid alert** (mod-log kanalı yok): {title}\n{description}")
            except Exception:
                pass
            return

        embed = discord.Embed(title=title, description=description, color=color,
                              timestamp=discord.utils.utcnow())
        embed.set_footer(text="Aether AntiRaid — Gözlemci modu (otomatik aksiyon YOK)")
        for name, value in (fields or []):
            embed.add_field(name=name, value=value, inline=False)
        try:
            await target.send(embed=embed)
        except Exception as e:
            log.warning("antiraid alert send failed: %s", e)

    # ── on_member_join ──────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        # bot hesapları ve whitelist muaf
        if member.bot:
            return
        if member.guild is None:
            return
        cfg = self.get_config(member.guild.id)
        if cfg.is_whitelisted(member.id):
            return

        guild_id = member.guild.id
        now = time.time()
        threshold = int(cfg.data.get("join_threshold", 5) or 5)
        window = int(cfg.data.get("join_window", 10) or 10)

        # Tracker temizle
        self.join_tracker[guild_id] = [
            (t, uid) for t, uid in self.join_tracker[guild_id]
            if now - t < window
        ]
        self.join_tracker[guild_id].append((now, member.id))

        # Hesap yaşı kontrolü
        account_age_days = (discord.utils.utcnow() - member.created_at).days
        min_age = int(cfg.data.get("min_age", 5) or 0)
        if cfg.data.get("age_filter") and min_age > 0 and account_age_days < min_age:
            await self._send_alert(
                member.guild, cfg,
                title="🕒 Yeni hesap katıldı (alert)",
                description=f"{member.mention} katıldı ama hesabı çok yeni.",
                fields=[
                    ("Kullanıcı", f"{member} (`{member.id}`)"),
                    ("Hesap yaşı", f"{account_age_days} gün (min: {min_age})"),
                    ("Oluşturulma", member.created_at.strftime("%Y-%m-%d %H:%M UTC")),
                ],
                color=discord.Color.yellow(),
            )
            cfg.add_event({
                "type": "young_account",
                "user_id": str(member.id),
                "user_tag": str(member),
                "account_age_days": account_age_days,
                "timestamp": discord.utils.utcnow().isoformat(),
            })

        # Raid kontrolü
        if cfg.data.get("join_raid"):
            count = len(self.join_tracker[guild_id])
            if count >= threshold:
                await self._send_alert(
                    member.guild, cfg,
                    title="🚨 Raid benzeri katılım dalgası (alert)",
                    description=(
                        f"Son {window} saniyede **{count}** kişi katıldı "
                        f"(eşik: {threshold}). **Otomatik aksiyon devre dışı** — "
                        f"paneldeki `/antiraid` sayfasından müdahale edebilirsiniz."
                    ),
                    fields=[
                        ("Eşik", f"{count}/{threshold} kişi / {window}sn"),
                        ("Son katılan", f"{member} (`{member.id}`)"),
                    ],
                    color=discord.Color.dark_red(),
                )
                cfg.add_event({
                    "type": "join_raid",
                    "count": count,
                    "window": window,
                    "threshold": threshold,
                    "last_user": str(member),
                    "timestamp": discord.utils.utcnow().isoformat(),
                })
                # sayaç resetlemesin ki kanal kirliliği olmasın; bir sonraki dalgayı da yakalasın
                # (tracker zaten window dolarsa eski kayıtları otomatik siler)

    # ── Bot join (bot_protection) ────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        # Bot eklenmesini burada yakalamak zor; on_member_join zaten yukarıda var.
        # bot_protection aktifse ve bir bot hesabı katıldıysa, alert ver.
        if not after.bot or before.bot:
            return
        if after.guild is None:
            return
        cfg = self.get_config(after.guild.id)
        if not cfg.data.get("bot_protection"):
            return
        if cfg.is_whitelisted(after.id):
            return
        await self._send_alert(
            after.guild, cfg,
            title="🤖 Sunucuya bot eklendi (alert)",
            description=f"{after.mention} sunucuya katıldı. **Otomatik kick devre dışı** — panelden kontrol edin.",
            fields=[
                ("Bot", f"{after} (`{after.id}`)"),
                ("Sahibi", "Bilinmiyor (eğer OAuth ise)"),
            ],
            color=discord.Color.purple(),
        )
        cfg.add_event({
            "type": "bot_join",
            "user_id": str(after.id),
            "user_tag": str(after),
            "timestamp": discord.utils.utcnow().isoformat(),
        })

    # ── Kanal toplu silme koruması (delete_protection) ──────────────────────

    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages: list[discord.Message]):
        if not messages:
            return
        guild = messages[0].guild
        if guild is None:
            return
        cfg = self.get_config(guild.id)
        if not cfg.data.get("delete_protection"):
            return
        if len(messages) < 5:
            return
        ch = messages[0].channel
        await self._send_alert(
            guild, cfg,
            title="🗑️ Toplu mesaj silme algılandı (alert)",
            description=f"#{ch.name} kanalında **{len(messages)}** mesaj toplu silindi.",
            fields=[
                ("Kanal", f"#{ch.name} (`{ch.id}`)"),
                ("Mesaj sayısı", str(len(messages))),
            ],
            color=discord.Color.dark_grey(),
        )
        cfg.add_event({
            "type": "bulk_delete",
            "channel_id": str(ch.id),
            "count": len(messages),
            "timestamp": discord.utils.utcnow().isoformat(),
        })

    # ── /antiraid slash komutu (Discord tarafı) — sadece durumu gösterir ─────

    @app_commands.command(name="antiraid", description="Antiraid sisteminin anlık durumunu gösterir")
    @app_commands.checks.has_permissions(administrator=True)
    async def antiraid_status(self, interaction: discord.Interaction):
        cfg = self.get_config(interaction.guild.id)
        d = cfg.data
        e = discord.Embed(
            title="🛡️ Antiraid — Durum",
            color=0x2ECC71 if (d.get("join_raid") or d.get("age_filter") or d.get("bot_protection")) else 0x95A5A6,
        )
        e.description = (
            "**Gözlemci modu**: bot otomatik kick/ban/lockdown yapmaz, "
            "sadece alert kanalına bildirir.\n"
            "Tüm ayarlar paneldeki `/antiraid` sayfasından yapılır."
        )
        e.add_field(name="Raid algılama", value="✅ Açık" if d.get("join_raid") else "❌ Kapalı", inline=True)
        e.add_field(name="Hesap yaşı filtresi", value="✅ Açık" if d.get("age_filter") else "❌ Kapalı", inline=True)
        e.add_field(name="Bot koruması", value="✅ Açık" if d.get("bot_protection") else "❌ Kapalı", inline=True)
        e.add_field(name="Toplu silme koruması", value="✅ Açık" if d.get("delete_protection") else "❌ Kapalı", inline=True)
        e.add_field(name="Eşik", value=f"{d.get('join_threshold', 5)} kişi / {d.get('join_window', 10)}sn", inline=True)
        e.add_field(name="Min hesap yaşı", value=f"{d.get('min_age', 5)} gün", inline=True)
        e.add_field(name="Whitelist", value=f"{len(d.get('whitelist', []))} kişi", inline=True)
        e.add_field(name="Alert kanalı", value=f"<#{d['alert_channel_id']}>" if d.get("alert_channel_id") else "`mod-log` (varsayılan)", inline=True)
        e.add_field(name="Son olaylar", value=str(len(d.get("recent_events", []))), inline=True)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name="antiraid-reload", description="Antiraid config dosyasını şimdi yeniden yükle")
    @app_commands.checks.has_permissions(administrator=True)
    async def antiraid_reload(self, interaction: discord.Interaction):
        cfg = self.get_config(interaction.guild.id)
        changed = cfg.reload()
        await interaction.response.send_message(
            f"🔄 Config {'değişti, yeniden yüklendi' if changed else 'zaten güncel'}.",
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(
        AntiRaid(bot),
        guilds=[
            discord.Object(id=1421244140359909513),
            discord.Object(id=1498837105915330562),
            discord.Object(id=1107038411895881788),
        ],
    )
