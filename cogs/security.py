"""
Aether Security Cog
- AI destekli spam tespiti (pattern + hız + benzerlik analizi)
- Fake hesap tespiti (yeni hesap, avatar yok, şüpheli имя)
- Link güvenlik tarayıcısı (zararlı domain listesi + URL shortener)
- Otomatik backup sistemi (server настройкиı yedeği)
"""
import discord
from discord.ext import commands, tasks
from discord import app_commands
import json, os, re, time, math
from collections import defaultdict
from datetime import datetime, timezone, timedelta

# ── Zararlı domain listesi ────────────────────────────────────────────────────
MALICIOUS_DOMAINS = {
    # Phishing / scam
    'grabify.link', 'iplogger.org', 'blasze.tk', 'ps3cfw.com',
    'bit.ly', 'tinyurl.com', 'shorturl.at', 'cutt.ly', 'rb.gy',
    'discord-nitro.gift', 'discordapp.gift', 'steamcommunity.ru',
    'free-nitro.ru', 'nitro-discord.ru', 'discord-gift.ru',
    'freestuff.gg', 'discord.gift', 'dlscord.com', 'discorcl.com',
    # Malware
    'mediafire.com', 'anonfiles.com', 'gofile.io',
}

# Şüpheli имя pattern'leri
SUSPICIOUS_NAME_PATTERNS = [
    r'discord.*nitro', r'free.*nitro', r'steam.*gift',
    r'admin.*\d{4}', r'mod.*\d{4}', r'support.*\d{4}',
    r'giveaway', r'free.*gift', r'claim.*reward',
]

DATA_FILE = 'data/security_{guild_id}.json'
BACKUP_DIR = 'data/backups'

def _load_cfg(guild_id):
    f = DATA_FILE.format(guild_id=guild_id)
    if os.path.exists(f):
        with open(f, 'r', encoding='utf-8') as fp:
            return json.load(fp)
    return {
        'ai_spam': True,
        'fake_account': True,
        'link_scanner': True,
        'new_account_days': 7,
        'new_account_action': 'warn',  # warn | kick | ban
        'log_channel': None,
    }

def _save_cfg(guild_id, data):
    os.makedirs('data', exist_ok=True)
    with open(DATA_FILE.format(guild_id=guild_id), 'w', encoding='utf-8') as fp:
        json.dump(data, fp, indent=2, ensure_ascii=False)

def _similarity(a: str, b: str) -> float:
    """İki string arasındaki benzerlik oranı (0-1). Levenshtein taзабаненные."""
    if not a or not b:
        return 0.0
    a, b = a.lower(), b.lower()
    if a == b:
        return 1.0
    la, lb = len(a), len(b)
    if abs(la - lb) / max(la, lb) > 0.5:
        return 0.0
    # Basit karakter örtüşme oranı
    common = sum(1 for c in a if c in b)
    return common / max(la, lb)

def _extract_domains(text: str) -> list:
    """Metinden domain'leri çıkar."""
    pattern = re.compile(
        r'(?:https?://|www\.)([a-zA-Z0-9\-\.]+\.[a-zA-Z]{2,})',
        re.IGNORECASE
    )
    return [m.group(1).lower() for m in pattern.finditer(text)]

def _is_suspicious_name(name: str) -> bool:
    name_lower = name.lower()
    for pattern in SUSPICIOUS_NAME_PATTERNS:
        if re.search(pattern, name_lower):
            return True
    return False


class Security(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # AI spam tracking: uid -> [(timestamp, content), ...]
        self.msg_history: dict[int, list] = defaultdict(list)
        # Burst tracking: uid -> [timestamps]
        self.burst_tracker: dict[int, list] = defaultdict(list)
        self.backup_loop.start()

    def cog_unload(self):
        self.backup_loop.cancel()

    # ── Лог helper ────────────────────────────────────────────────────────────
    async def _log(self, guild: discord.Guild, embed: discord.Embed, cfg: dict):
        ch_id = cfg.get('log_channel')
        ch = guild.get_channel(int(ch_id)) if ch_id else None
        if not ch:
            ch = discord.utils.get(guild.text_channels, name='mod-log')
        if ch:
            try:
                await ch.send(embed=embed)
            except Exception:
                pass

    # ── AI Spam Analizi ───────────────────────────────────────────────────────
    def _ai_spam_score(self, uid: int, content: str) -> tuple[float, str]:
        """
        Сообщениеı analiz et, spam skoru döndür (0.0 - 1.0) ve причина.
        Çoklu sinyal: hız + benzerlik + tekrar + uzunluk anomalisi
        """
        now = time.time()
        window = 8  # saniye
        history = self.msg_history[uid]

        # Старый регистрацияları clear
        history = [(t, c) for t, c in history if now - t < 30]
        self.msg_history[uid] = history

        signals = []

        # 1. Hız sinyali: 8 saniyede kaç message?
        recent = [t for t, _ in history if now - t < window]
        speed_score = min(len(recent) / 6, 1.0)  # 6+ message = 1.0
        if speed_score > 0.5:
            signals.append(f"hız ({len(recent)} message/{window}s)")

        # 2. Benzerlik sinyali: son messagelara ne kadar benziyor?
        if history:
            sims = [_similarity(content, c) for _, c in history[-5:]]
            avg_sim = sum(sims) / len(sims)
            sim_score = avg_sim
            if sim_score > 0.7:
                signals.append(f"benzerlik ({avg_sim:.0%})")
        else:
            sim_score = 0.0

        # 3. Tekrar sinyali: aynı içerik kaç kez?
        repeat_count = sum(1 for _, c in history if c.lower() == content.lower())
        repeat_score = min(repeat_count / 3, 1.0)
        if repeat_score > 0.5:
            signals.append(f"tekrar ({repeat_count}x)")

        # 4. Uzunluk anomalisi: çok kısa + çok hızlı
        length_score = 0.3 if len(content) < 5 and speed_score > 0.4 else 0.0

        # Ağırlıklı skor
        final_score = (
            speed_score * 0.35 +
            sim_score * 0.35 +
            repeat_score * 0.20 +
            length_score * 0.10
        )

        # Geçmişe add
        self.msg_history[uid].append((now, content))

        reason = " + ".join(signals) if signals else "normal"
        return final_score, reason

    # ── Fake Hesap Tespiti ────────────────────────────────────────────────────
    def _fake_account_score(self, member: discord.Member, cfg: dict) -> tuple[float, list]:
        """Fake hesap risk skoru (0-1) ve предупреждений listesi döndür."""
        warnings = []
        score = 0.0

        # Hesap yaşı
        age_days = (discord.utils.utcnow() - member.created_at).days
        threshold = cfg.get('new_account_days', 7)
        if age_days < 1:
            score += 0.5
            warnings.append(f"⚠️ Hesap **{age_days} деньlük** (çok yeni!)")
        elif age_days < threshold:
            score += 0.3
            warnings.append(f"⚠️ Hesap **{age_days} деньlük** ({threshold} деньden az)")

        # Default avatar
        if member.display_avatar.is_animated() is False and 'embed' in str(member.display_avatar.url):
            score += 0.2
            warnings.append("⚠️ Естьsayılan avatar kullanıyor")

        # Şüpheli имя
        if _is_suspicious_name(member.name) or _is_suspicious_name(member.display_name):
            score += 0.4
            warnings.append(f"⚠️ Şüpheli user adı: `{member.name}`")

        # Discriminator 0000 (eski sistem bot pattern'i)
        if hasattr(member, 'discriminator') and member.discriminator == '0000':
            score += 0.1
            warnings.append("ℹ️ Новый user adı sistemi")

        return min(score, 1.0), warnings

    # ── Link Tarayıcı ─────────────────────────────────────────────────────────
    def _scan_links(self, content: str) -> tuple[bool, list]:
        """Zararlı link var mı? (bool, bulunan domainler)"""
        domains = _extract_domains(content)
        found = []
        for domain in domains:
            # Tam eşleşme
            if domain in MALICIOUS_DOMAINS:
                found.append(domain)
                continue
            # Alt domain kontroleü (örn: evil.grabify.link)
            for bad in MALICIOUS_DOMAINS:
                if domain.endswith('.' + bad) or domain == bad:
                    found.append(domain)
                    break
        return bool(found), found

    # ── Event Listeners ───────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if (message.author.guild_permissions.moderate_members or
                message.author.guild_permissions.administrator):
            return

        cfg = _load_cfg(str(message.guild.id))
        guild = message.guild
        member = message.author

        # ── Link Tarayıcı ──────────────────────────────────────────────────
        if cfg.get('link_scanner', True):
            has_bad, bad_domains = self._scan_links(message.content)
            if has_bad:
                try:
                    await message.delete()
                except Exception:
                    pass
                e = discord.Embed(
                    title="🔗 Zararlı Link Engellendi",
                    color=0xe74c3c,
                    timestamp=datetime.now(timezone.utc)
                )
                e.description = (
                    f"{member.mention} zararlı/şüpheli link paylaştı!\n\n"
                    f"**🚨 Tespit edilen domain(ler):**\n"
                    + "\n".join(f"• `{d}`" for d in bad_domains)
                )
                e.set_thumbnail(url=member.display_avatar.url)
                e.set_footer(text="🛡️ Aether Link Tarayıcı")
                await self._log(guild, e, cfg)
                try:
                    await message.channel.send(
                        f"🚫 {member.mention} zararlı link engellendi!",
                        delete_after=5
                    )
                except Exception:
                    pass
                return

        # ── AI Spam Tespiti ────────────────────────────────────────────────
        if cfg.get('ai_spam', True):
            score, reason = self._ai_spam_score(member.id, message.content)

            if score >= 0.85:
                # Yüksek güven → удалить + timeout
                try:
                    await message.delete()
                except Exception:
                    pass
                try:
                    await member.timeout(
                        discord.utils.utcnow() + timedelta(minutes=5),
                        reason=f"AI Spam Tespiti: {reason}"
                    )
                except Exception:
                    pass
                e = discord.Embed(
                    title="🤖 AI Spam Tespiti — Yüksek Risk",
                    color=0xe74c3c,
                    timestamp=datetime.now(timezone.utc)
                )
                e.description = f"**Оценка:** `{score:.0%}` | **Причина:** {reason}\n**⏳ Наказание:** 5 minutes мут"
                e.set_thumbnail(url=member.display_avatar.url)
                e.add_field(name="👤 Пользователь", value=f"{member.mention} `{member.id}`", inline=True)
                e.add_field(name="📺 Канал", value=message.channel.mention, inline=True)
                e.set_footer(text="🤖 Aether AI Security")
                await self._log(guild, e, cfg)

            elif score >= 0.65:
                # Orta güven → sadece удалить + uyar
                try:
                    await message.delete()
                except Exception:
                    pass
                try:
                    await message.channel.send(
                        f"⚠️ {member.mention} spam yapma!",
                        delete_after=5
                    )
                except Exception:
                    pass
                e = discord.Embed(
                    title="🤖 AI Spam Tespiti — Orta Risk",
                    color=0xf39c12,
                    timestamp=datetime.now(timezone.utc)
                )
                e.description = f"**Оценка:** `{score:.0%}` | **Причина:** {reason}"
                e.set_thumbnail(url=member.display_avatar.url)
                e.add_field(name="👤 Пользователь", value=f"{member.mention} `{member.id}`", inline=True)
                e.set_footer(text="🤖 Aether AI Security")
                await self._log(guild, e, cfg)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        cfg = _load_cfg(str(member.guild.id))
        if not cfg.get('fake_account', True):
            return

        score, warnings = self._fake_account_score(member, cfg)
        if score < 0.3:
            return

        guild = member.guild
        action = cfg.get('new_account_action', 'warn')

        e = discord.Embed(
            title="🕵️ Şüpheli Hesap Tespit Edildi",
            color=0xe74c3c if score >= 0.6 else 0xf39c12,
            timestamp=datetime.now(timezone.utc)
        )
        e.set_thumbnail(url=member.display_avatar.url)
        e.description = "\n".join(warnings)
        e.add_field(name="👤 Пользователь", value=f"{member.mention}\n`{member.id}`", inline=True)
        e.add_field(name="📅 Hesap Yaşı", value=f"`{(discord.utils.utcnow() - member.created_at).days} день`", inline=True)
        e.add_field(name="🎯 Risk Оценкаu", value=f"`{score:.0%}`", inline=True)

        if score >= 0.6 and action == 'kick':
            try:
                await member.kick(reason="Fake hesap tespiti")
                e.add_field(name="⚡ Aksiyon", value="```Кик uygulandı```", inline=False)
            except Exception:
                pass
        elif score >= 0.8 and action == 'ban':
            try:
                await member.ban(reason="Fake hesap tespiti")
                e.add_field(name="⚡ Aksiyon", value="```Бан uygulandı```", inline=False)
            except Exception:
                pass
        else:
            e.add_field(name="⚡ Aksiyon", value="```Модератор уведомлениеi отправитьildi```", inline=False)

        e.set_footer(text="🛡️ Aether Güvenlik Sistemi")
        await self._log(guild, e, cfg)

    # ── Slash Командаlar ────────────────────────────────────────────────────────
    @app_commands.command(name="security", description="Güvenlik настройкиını görüntüle")
    @app_commands.checks.has_permissions(administrator=True)
    async def security_status(self, interaction: discord.Interaction):
        cfg = _load_cfg(str(interaction.guild.id))
        e = discord.Embed(
            title="🛡️ Güvenlik Sistemi Статусu",
            color=0x2ecc71,
            timestamp=datetime.now(timezone.utc)
        )
        e.add_field(name="🤖 AI Spam", value="✅ Активен" if cfg.get('ai_spam') else "❌ Закрыт", inline=True)
        e.add_field(name="🕵️ Fake Hesap", value="✅ Активен" if cfg.get('fake_account') else "❌ Закрыт", inline=True)
        e.add_field(name="🔗 Link Tarayıcı", value="✅ Активен" if cfg.get('link_scanner') else "❌ Закрыт", inline=True)
        e.add_field(name="📅 Новый Hesap Eşiği", value=f"`{cfg.get('new_account_days', 7)} день`", inline=True)
        e.add_field(name="⚡ Новый Hesap Aksiyonu", value=f"`{cfg.get('new_account_action', 'warn')}`", inline=True)
        e.set_footer(text="🛡️ Aether Security")
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name="security-toggle", description="Güvenlik özelliğini aç/закрыть")
    @app_commands.describe(feature="Özellik", enabled="Открыть/Закрыть")
    @app_commands.choices(feature=[
        app_commands.Choice(name="AI Spam Tespiti", value="ai_spam"),
        app_commands.Choice(name="Fake Hesap Tespiti", value="fake_account"),
        app_commands.Choice(name="Link Tarayıcı", value="link_scanner"),
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def security_toggle(self, interaction: discord.Interaction, feature: str, enabled: bool):
        cfg = _load_cfg(str(interaction.guild.id))
        cfg[feature] = enabled
        _save_cfg(str(interaction.guild.id), cfg)
        status = "✅ Активен" if enabled else "❌ Закрыт"
        await interaction.response.send_message(
            f"🛡️ **{feature}** → {status}", ephemeral=True
        )

    @app_commands.command(name="security-newaccount", description="Новый hesap aksiyonunu настроить")
    @app_commands.describe(days="Kaç деньden yeni hesap şüpheli sayılsın", action="Aksiyon")
    @app_commands.choices(action=[
        app_commands.Choice(name="Sadece Bildir", value="warn"),
        app_commands.Choice(name="Кик", value="kick"),
        app_commands.Choice(name="Бан", value="ban"),
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def security_newaccount(self, interaction: discord.Interaction, days: int, action: str):
        cfg = _load_cfg(str(interaction.guild.id))
        cfg['new_account_days'] = days
        cfg['new_account_action'] = action
        _save_cfg(str(interaction.guild.id), cfg)
        await interaction.response.send_message(
            f"✅ Новый hesap eşiği: **{days} день** | Aksiyon: **{action}**", ephemeral=True
        )

    @app_commands.command(name="scan-link", description="Bir linki güvenlik taramasından geçir")
    @app_commands.describe(url="Taranacak URL")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def scan_link(self, interaction: discord.Interaction, url: str):
        has_bad, bad_domains = self._scan_links(url)
        if has_bad:
            e = discord.Embed(title="🚨 Zararlı Link!", color=0xe74c3c)
            e.description = "Bu link zararlı/şüpheli domain içeriyor:\n" + "\n".join(f"• `{d}`" for d in bad_domains)
        else:
            e = discord.Embed(title="✅ Link Temiz", color=0x2ecc71)
            e.description = "Bu link bilinen zararlı domain listesinde bulunamadı."
        e.add_field(name="🔗 URL", value=f"`{url[:100]}`", inline=False)
        e.set_footer(text="🛡️ Aether Link Tarayıcı")
        await interaction.response.send_message(embed=e, ephemeral=True)

    # ── Otomatik Backup ───────────────────────────────────────────────────────
    @tasks.loop(hours=24)
    async def backup_loop(self):
        """Her 24 часte tüm serverların настройкиını yedadd."""
        for guild in self.bot.guilds:
            await self._backup_guild(guild)

    @backup_loop.before_loop
    async def before_backup(self):
        await self.bot.wait_until_ready()

    async def _backup_guild(self, guild: discord.Guild):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M')
        backup = {
            'guild_id': str(guild.id),
            'guild_name': guild.name,
            'timestamp': timestamp,
            'member_count': guild.member_count,
            'roles': [
                {
                    'id': str(r.id), 'name': r.name,
                    'color': str(r.color), 'hoist': r.hoist,
                    'mentionable': r.mentionable, 'position': r.position,
                    'permissions': r.permissions.value
                }
                for r in guild.roles if not r.managed
            ],
            'channels': [
                {
                    'id': str(c.id), 'name': c.name,
                    'type': str(c.type), 'position': c.position,
                    'category': c.category.name if hasattr(c, 'category') and c.category else None
                }
                for c in guild.channels
            ],
            'categories': [
                {'id': str(c.id), 'name': c.name, 'position': c.position}
                for c in guild.categories
            ],
        }
        path = os.path.join(BACKUP_DIR, f'backup_{guild.id}_{timestamp}.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(backup, f, indent=2, ensure_ascii=False)

        # Старый yedaddri clear (son 7 tane tut)
        all_backups = sorted([
            x for x in os.listdir(BACKUP_DIR)
            if x.startswith(f'backup_{guild.id}_')
        ])
        for old in all_backups[:-7]:
            try:
                os.remove(os.path.join(BACKUP_DIR, old))
            except Exception:
                pass

    @app_commands.command(name="backup", description="Сервер настройкиını şimdi yedadd")
    @app_commands.checks.has_permissions(administrator=True)
    async def backup_now(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self._backup_guild(interaction.guild)
        # Mevcut yedaddri listele
        backups = sorted([
            x for x in os.listdir(BACKUP_DIR)
            if x.startswith(f'backup_{interaction.guild.id}_')
        ], reverse=True)
        e = discord.Embed(title="💾 Резервная копияme ОКlandı", color=0x2ecc71, timestamp=datetime.now(timezone.utc))
        e.description = f"**{interaction.guild.name}** serversu yedaddndi."
        e.add_field(
            name=f"📁 Mevcut Резервная копияr ({len(backups)})",
            value="\n".join(f"• `{b}`" for b in backups[:5]) or "Нет",
            inline=False
        )
        e.set_footer(text="💾 Aether Backup Sistemi • Günlük otomatik yedek активна")
        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="backup-list", description="Mevcut yedaddri listele")
    @app_commands.checks.has_permissions(administrator=True)
    async def backup_list(self, interaction: discord.Interaction):
        if not os.path.exists(BACKUP_DIR):
            await interaction.response.send_message("❌ Henüz yedek yok.", ephemeral=True)
            return
        backups = sorted([
            x for x in os.listdir(BACKUP_DIR)
            if x.startswith(f'backup_{interaction.guild.id}_')
        ], reverse=True)
        e = discord.Embed(title="📁 Сервер Резервная копияri", color=0x3498db, timestamp=datetime.now(timezone.utc))
        if not backups:
            e.description = "Henüz yedek bulunamadı. `/backup` ile yedek создать."
        else:
            e.description = "\n".join(f"• `{b}`" for b in backups)
        e.set_footer(text="💾 Последний 7 yedek saklanır")
        await interaction.response.send_message(embed=e, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Security(bot), guilds=[discord.Object(id=1421244140359909513), discord.Object(id=1107038411895881788)])
