"""Модератор Отчёт Sistemi — haftalık toplantı отчётu"""
import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import os
import datetime
from collections import defaultdict

DATA_DIR = 'data'
MOD_DATA_FILE = f'{DATA_DIR}/mod_data.json'


def _cfg_file(guild_id: int) -> str:
    return f'{DATA_DIR}/mod_report_config_{guild_id}.json'


def _load_cfg(guild_id: int) -> dict:
    path = _cfg_file(guild_id)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {
        'enabled': False,
        'channel_id': None,
        'day': 0,
        'hour': 9,
        'staff_roles': [],
        'last_meeting': None  # Последний toplantı датаi (ISO format)
    }


def _save_cfg(guild_id: int, cfg: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(_cfg_file(guild_id), 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def _load_mod_data() -> dict:
    if os.path.exists(MOD_DATA_FILE):
        try:
            with open(MOD_DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {'caголос': {}}


def _load_lb(guild_id: int) -> dict:
    """Leaderboard verisini загрузить — voice_stats ve leaderboard dosyalarını birleştir"""
    result = {'messages': {}, 'voice_minutes': {}}

    # Сообщение verisi
    lb_path = f'{DATA_DIR}/leaderboard_{guild_id}.json'
    if os.path.exists(lb_path):
        try:
            with open(lb_path, 'r', encoding='utf-8') as f:
                lb = json.load(f)
            result['messages'] = lb.get('messages', {})
            # leaderboard'da voice_minutes varsa al
            for uid, mins in lb.get('voice_minutes', {}).items():
                result['voice_minutes'][uid] = result['voice_minutes'].get(uid, 0) + mins
        except:
            pass

    # Голос verisi — voice_stats_GUILDID.json (saniye cinsinden)
    vs_path = f'{DATA_DIR}/voice_stats_{guild_id}.json'
    if os.path.exists(vs_path):
        try:
            with open(vs_path, 'r', encoding='utf-8') as f:
                vs = json.load(f)
            for uid, udata in vs.get('users', {}).items():
                seconds = udata.get('total_seconds', 0) if isinstance(udata, dict) else int(udata)
                minutes = seconds // 60
                result['voice_minutes'][uid] = result['voice_minutes'].get(uid, 0) + minutes
        except:
            pass

    return result


def _load_invites(guild_id: int) -> dict:
    path = f'{DATA_DIR}/invite_counts_{guild_id}.json'
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            result = {}
            for uid, val in data.items():
                if isinstance(val, dict):
                    # {'name': '...', 'total': 25} veya {'count': 5}
                    result[uid] = val.get('total', val.get('count', val.get('uголос', 0)))
                elif isinstance(val, (int, float)):
                    result[uid] = int(val)
            return result
        except:
            pass
    return {}


def _action_emoji(action: str) -> str:
    return {
        'ban': '🔨', 'kick': '👢', 'timeout': '⏱️',
        'warn': '⚠️', 'unban': '✅', 'mute': '🔇',
    }.get(action.lower(), '🔹')


def _fmt_time(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    if h:
        return f'{h}s {m}dk'
    return f'{m}dk'


def _bar(value: int, max_val: int, length: int = 12) -> str:
    if max_val == 0:
        return '░' * length
    filled = int((value / max_val) * length)
    return '█' * filled + '░' * (length - filled)


async def _build_weekly_report(guild: discord.Guild, days: int = 7, force_cutoff: datetime.datetime = None) -> list[discord.Embed]:
    """Haftalık toplantı отчётu — tüm embed'ler"""
    now = datetime.datetime.now(datetime.timezone.utc)
    cfg = _load_cfg(guild.id)

    if force_cutoff:
        cutoff = force_cutoff
        period = f'Последний {days} Gün'
    elif cfg.get('last_meeting'):
        try:
            cutoff = datetime.datetime.fromisoformat(cfg['last_meeting'])
            if cutoff.tzinfo is None:
                cutoff = cutoff.replace(tzinfo=datetime.timezone.utc)
            days_since = (now - cutoff).days
            period = f'Последний Toplantıdan Bu Yana ({days_since} день)'
        except:
            cutoff = now - datetime.timedelta(days=days)
            period = f'Последний {days} Gün'
    else:
        cutoff = now - datetime.timedelta(days=days)
        period = f'Последний {days} Gün'

    ts_cutoff = int(cutoff.timestamp())
    ts_now = int(now.timestamp())

    lb = _load_lb(guild.id)
    invites = _load_invites(guild.id)
    mod_data = _load_mod_data()
    cfg = _load_cfg(guild.id)

    gid = str(guild.id)
    all_caголос = mod_data.get('caголос', {}).get(gid, [])

    # Bu dönemdeki mod case'leri
    period_caголос = []
    for c in all_caголос:
        try:
            ts = datetime.datetime.fromisoformat(c['timestamp'])
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=datetime.timezone.utc)
            if ts >= cutoff:
                period_caголос.append(c)
        except:
            pass

    embeds = []

    # ══════════════════════════════════════════════════════════════════════════
    # 1. KAPAK EMBED
    # ══════════════════════════════════════════════════════════════════════════
    cover = discord.Embed(
        color=0x2B2D31,
        timestamp=now
    )
    cover.set_author(
        name=f'{guild.name}  ·  Haftalık Toplantı Отчётu',
        icon_url=guild.icon.url if guild.icon else None
    )
    cover.description = (
        f'```ansi\n'
        f'\u001b[1;34m╔══════════════════════════════════╗\u001b[0m\n'
        f'\u001b[1;34m║   HAFTALIK PERFORMANS RAPORU     ║\u001b[0m\n'
        f'\u001b[1;34m╚══════════════════════════════════╝\u001b[0m\n'
        f'```\n'
        f'> 📅 Dönem: **{period}**\n'
        f'> 🗓️ <t:{ts_cutoff}:D> → <t:{ts_now}:D>\n'
        f'> 👥 Всего Участник: **{guild.member_count}**\n'
        f'> 📊 Mod Действиеi: **{len(period_caголос)}**'
    )
    cover.set_image(url='https://media.tenor.com/ZBDpMFBMFpkAAAAC/celebration-party.gif')
    embeds.append(cover)

    # ══════════════════════════════════════════════════════════════════════════
    # 2. GENEL SUNUCU SIRALAMASI (Top 5 — message + голос + davet)
    # ══════════════════════════════════════════════════════════════════════════
    scores = defaultdict(lambda: {'msg': 0, 'voice': 0, 'inv': 0, 'score': 0})
    for uid, cnt in lb.get('messages', {}).items():
        scores[uid]['msg'] = cnt
        scores[uid]['score'] += cnt
    for uid, mins in lb.get('voice_minutes', {}).items():
        scores[uid]['voice'] = mins
        scores[uid]['score'] += mins * 2
    for uid, cnt in invites.items():
        scores[uid]['inv'] = cnt
        scores[uid]['score'] += cnt * 5

    top_overall = sorted(scores.items(), key=lambda x: x[1]['score'], reverse=True)[:5]
    max_score = top_overall[0][1]['score'] if top_overall else 1

    overall_embed = discord.Embed(
        title='🏆  Genel Сортировкаma — Top 5',
        color=0xF1C40F,
        timestamp=now
    )
    medals = ['🥇', '🥈', '🥉', '4️⃣', '5️⃣']
    lines = []
    for i, (uid, s) in enumerate(top_overall):
        m = guild.get_member(int(uid))
        name = m.display_name if m else f'<@{uid}>'
        bar = _bar(s['score'], max_score)
        h, mn = divmod(s['voice'], 60)
        lines.append(
            f'{medals[i]} **{name}**\n'
            f'╰ {bar} `{s["score"]:,} puan`\n'
            f'╰ 💬 {s["msg"]:,} message  🎙️ {h}s{mn}dk  📨 {s["inv"]} davet'
        )
    overall_embed.description = '\n\n'.join(lines) or 'Veri yok.'
    overall_embed.set_footer(text=f'Puan: Сообщение×1 + Голос dk×2 + Davet×5')
    embeds.append(overall_embed)

    # ══════════════════════════════════════════════════════════════════════════
    # 3. ROL BAZLI TOP 4 (Правоli roleler için)
    # ══════════════════════════════════════════════════════════════════════════
    staff_role_ids = cfg.get('staff_roles', [])

    # Eğer role настроитьnmamışsa, serverdaki tüm roleleri tara (admin/mod içerenler)
    if not staff_role_ids:
        staff_role_ids = [
            r.id for r in guild.roles
            if r.permissions.manage_messages or r.permissions.kick_members
            and not r.is_default()
        ]

    for role_id in staff_role_ids[:8]:  # Max 8 role
        role = guild.get_role(role_id)
        if not role or role.is_default():
            continue

        # Bu roledeki участникlerin skorları
        role_members = [m for m in role.members if not m.bot]
        if not role_members:
            continue

        role_scores = []
        for member in role_members:
            uid = str(member.id)
            msg = lb.get('messages', {}).get(uid, 0)
            voice = lb.get('voice_minutes', {}).get(uid, 0)
            inv = invites.get(uid, 0)
            score = msg + voice * 2 + inv * 5
            role_scores.append((member, msg, voice, inv, score))

        role_scores.sort(key=lambda x: x[4], reverse=True)
        top4 = role_scores[:4]

        if not top4:
            continue

        max_s = top4[0][4] if top4[0][4] > 0 else 1

        role_embed = discord.Embed(
            title=f'{role.name}  —  Top {min(4, len(top4))}',
            color=role.color.value if role.color.value else 0x5865F2,
            timestamp=now
        )

        lines = []
        rank_emojis = ['🥇', '🥈', '🥉', '4️⃣']
        for i, (member, msg, voice, inv, score) in enumerate(top4):
            bar = _bar(score, max_s)
            h, mn = divmod(voice, 60)
            lines.append(
                f'{rank_emojis[i]} **{member.display_name}**\n'
                f'╰ {bar} `{score:,} puan`\n'
                f'╰ 💬 {msg:,}  🎙️ {h}s{mn}dk  📨 {inv}'
            )

        role_embed.description = '\n\n'.join(lines)
        role_embed.set_footer(text=f'{role.name} • {len(role_members)} участник')
        embeds.append(role_embed)

    # ══════════════════════════════════════════════════════════════════════════
    # 4. MOD İSTATİSTİKLERİ
    # ══════════════════════════════════════════════════════════════════════════
    if period_caголос:
        action_counts = defaultdict(int)
        mod_counts = defaultdict(int)
        for c in period_caголос:
            action_counts[c['action'].lower()] += 1
            mod_counts[c['mod_id']] += 1

        mod_embed = discord.Embed(
            title='⚔️  Moderasyon Özeti',
            color=0xED4245,
            timestamp=now
        )

        # Aksiyon dağılımı
        action_lines = []
        for action, count in sorted(action_counts.items(), key=lambda x: x[1], reverse=True):
            bar = _bar(count, max(action_counts.values()))
            action_lines.append(f'{_action_emoji(action)} `{action.upper():<8}` {bar} **{count}**')

        mod_embed.add_field(
            name=f'📋 Действие Dağılımı ({len(period_caголос)} всего)',
            value='\n'.join(action_lines) or 'Нет',
            inline=False
        )

        # Top модераторler
        top_mods = sorted(mod_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        mod_lines = []
        for i, (mid, cnt) in enumerate(top_mods):
            m = guild.get_member(int(mid))
            name = m.display_name if m else f'<@{mid}>'
            mod_lines.append(f'`#{i+1}` **{name}** — {cnt} действие')
        mod_embed.add_field(
            name='🏅 En Активен Модераторler',
            value='\n'.join(mod_lines) or 'Нет',
            inline=False
        )
        mod_embed.set_footer(text=f'Aether Mod Отчётu • {period}')
        embeds.append(mod_embed)

    # ══════════════════════════════════════════════════════════════════════════
    # 5. KAPANIŞ
    # ══════════════════════════════════════════════════════════════════════════
    close = discord.Embed(
        color=0x57F287,
        timestamp=now
    )
    close.description = (
        f'```ansi\n\u001b[1;32m✦ Отчёт Последнийu ✦\u001b[0m\n```\n'
        f'> Bu отчёт **{period}** verilerini kapsamaktadır.\n'
        f'> Bir следующий отчёт: <t:{ts_now + (7 - datetime.datetime.utcnow().weekday()) * 86400}:D>\n\n'
        f'-# Aether Бот • Otomatik Haftalık Отчёт'
    )
    embeds.append(close)

    return embeds


class ModReportView(discord.ui.View):
    """Mod отчёт paneli butonları"""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label='📊  Haftalık Отчёт', style=discord.ButtonStyle.primary, custom_id='modreport_weekly', row=0)
    async def weekly(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message('❌ Правоn yok.', ephemeral=True)
            return
        await interaction.response.defer()
        embeds = await _build_weekly_report(interaction.guild, days=7)
        for i in range(0, len(embeds), 10):
            await interaction.followup.send(embeds=embeds[i:i+10])

    @discord.ui.button(label='📅  Последний 30 Gün', style=discord.ButtonStyle.secondary, custom_id='modreport_30', row=0)
    async def monthly(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message('❌ Правоn yok.', ephemeral=True)
            return
        await interaction.response.defer()
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)
        embeds = await _build_weekly_report(interaction.guild, days=30, force_cutoff=cutoff)
        for i in range(0, len(embeds), 10):
            await interaction.followup.send(embeds=embeds[i:i+10])

    @discord.ui.button(label='👤  Mod İstatistik', style=discord.ButtonStyle.secondary, custom_id='modreport_modstats', row=0)
    async def modstats(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message('❌ Правоn yok.', ephemeral=True)
            return
        # Kendi istatistiklerini göster
        data = _load_mod_data()
        gid = str(interaction.guild.id)
        caголос = data.get('caголос', {}).get(gid, [])
        mod_caголос = [c for c in caголос if c['mod_id'] == str(interaction.user.id)]
        action_counts = defaultdict(int)
        for c in mod_caголос:
            action_counts[c['action'].lower()] += 1
        lb = _load_lb(interaction.guild.id)
        inv = _load_invites(interaction.guild.id)
        uid = str(interaction.user.id)
        msg = lb.get('messages', {}).get(uid, 0)
        voice = lb.get('voice_minutes', {}).get(uid, 0)
        h, mn = divmod(voice, 60)
        embed = discord.Embed(
            title=f'📊 {interaction.user.display_name}',
            color=interaction.user.accent_color or 0x5865F2,
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        if interaction.guild.icon:
            embed.set_footer(text=interaction.guild.name, icon_url=interaction.guild.icon.url)
        embed.add_field(
            name='📈 Aktivite',
            value=f'```yaml\nСообщение  : {msg:,}\nГолос    : {h}s {mn}dk\nDavet  : {inv.get(uid, 0)}\n```',
            inline=True
        )
        embed.add_field(
            name='⚔️ Moderasyon',
            value=(
                f'```yaml\n'
                f'Всего : {len(mod_caголос)}\n'
                f'Бан    : {action_counts.get("ban", 0)}\n'
                f'Кик   : {action_counts.get("kick", 0)}\n'
                f'Мут: {action_counts.get("timeout", 0)}\n'
                f'Warning  : {action_counts.get("warn", 0)}\n'
                f'```'
            ),
            inline=True
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label='🏆  Сортировкаma', style=discord.ButtonStyle.success, custom_id='modreport_lb', row=1)
    async def leaderboard(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        lb = _load_lb(interaction.guild.id)
        inv = _load_invites(interaction.guild.id)
        from collections import defaultdict as dd
        scores = dd(int)
        for uid, cnt in lb.get('messages', {}).items():
            scores[uid] += cnt
        for uid, mins in lb.get('voice_minutes', {}).items():
            scores[uid] += mins * 2
        top = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:10]
        medals = ['🥇', '🥈', '🥉']
        lines = []
        for i, (uid, score) in enumerate(top):
            m = interaction.guild.get_member(int(uid))
            name = m.display_name if m else f'<@{uid}>'
            medal = medals[i] if i < 3 else f'`#{i+1}`'
            lines.append(f'{medal} **{name}** — {score:,} puan')
        embed = discord.Embed(title='🏆 Genel Сортировкаma', description='\n'.join(lines) or 'Veri yok.', color=0xF1C40F)
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
        await interaction.followup.send(embed=embed)

    @discord.ui.button(label='⚙️  Настройки', style=discord.ButtonStyle.grey, custom_id='modreport_settings', row=1)
    async def settings(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message('❌ Правоn yok.', ephemeral=True)
            return
        cfg = _load_cfg(interaction.guild.id)
        gun_names = ['Pazartesi', 'Salı', 'Çarşamba', 'Perşembe', 'Cuma', 'Cumartesi', 'Pazar']
        ch = interaction.guild.get_channel(cfg.get('channel_id', 0))
        embed = discord.Embed(title='⚙️ Отчёт Настройкиı', color=0x5865F2)
        embed.add_field(name='Статус', value='✅ Активен' if cfg.get('enabled') else '❌ Закрыт', inline=True)
        embed.add_field(name='Канал', value=ch.mention if ch else 'Настроитьnmamış', inline=True)
        embed.add_field(name='Gün/Время', value=f'{gun_names[cfg.get("day", 0)]} {cfg.get("hour", 9):02d}:00', inline=True)
        embed.description = (
            '**Командаlar:**\n'
            '`!отчёт-настроить #channel [день] [час]`\n'
            '`!отчёт-role-add @Роль`\n'
            '`!отчёт-role-cikar @Роль`'
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class ModReport(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.weekly_report_loop.start()

    def cog_unload(self):
        self.weekly_report_loop.cancel()

    @tasks.loop(minutes=30)
    async def weekly_report_loop(self):
        now = datetime.datetime.utcnow()
        for guild in self.bot.guilds:
            cfg = _load_cfg(guild.id)
            if not cfg.get('enabled') or not cfg.get('channel_id'):
                continue
            if now.weekday() == cfg.get('day', 0) and now.hour == cfg.get('hour', 9) and now.minute < 30:
                week_str = now.strftime('%Y-W%W')
                if cfg.get('last_sent') == week_str:
                    continue
                channel = guild.get_channel(cfg['channel_id'])
                if channel:
                    try:
                        embeds = await _build_weekly_report(guild, days=7)
                        # Discord max 10 embed/message — ikiye böl
                        for i in range(0, len(embeds), 10):
                            await channel.send(embeds=embeds[i:i+10])
                        cfg['last_sent'] = week_str
                        _save_cfg(guild.id, cfg)
                        print(f'[ModReport] Отчёт отправитьildi: {guild.name}')
                    except Exception as e:
                        print(f'[ModReport] Ошибка: {e}')

    @weekly_report_loop.before_loop
    async def before_loop(self):
        await self.bot.wait_until_ready()

    @commands.command(name='mod-panel')
    @commands.has_permissions(manage_messages=True)
    async def mod_panel(self, ctx):
        """Mod отчёт panelini отправить: !mod-panel"""
        embed = discord.Embed(
            title='📊  Moderasyon & Отчёт Панельi',
            color=0x5865F2
        )
        if ctx.guild.icon:
            embed.set_thumbnail(url=ctx.guild.icon.url)
        if ctx.guild.banner:
            embed.set_image(url=ctx.guild.banner.url)
        embed.description = (
            '> Bu panel ile server отчётlarını ve istatistikleri görüntüleyebilirsin.\n\n'
            '**📊 Haftalık Отчёт** — Последний 7 деньün moderasyon ve aktivite özeti\n'
            '**📅 Последний 30 Gün** — Aylık отчёт\n'
            '**👤 Mod İstatistik** — Kendi moderasyon istatistiklerin\n'
            '**🏆 Сортировкаma** — Genel aktivite sıralaması\n'
            '**⚙️ Настройки** — Otomatik отчёт настройкиı'
        )
        embed.set_footer(
            text=f'{ctx.guild.name}  ·  Mod Панельi',
            icon_url=ctx.guild.icon.url if ctx.guild.icon else None
        )
        await ctx.send(embed=embed, view=ModReportView())

    @commands.command(name='haftalik-отчёт', aliaголос=['отчёт', 'report'])
    @commands.has_permissions(manage_messages=True)
    async def weekly_report(self, ctx, gun: int = 7):
        """Haftalık toplantı отчётunu göster: !haftalik-отчёт [день]"""
        async with ctx.typing():
            embeds = await _build_weekly_report(ctx.guild, days=gun)
            for i in range(0, len(embeds), 10):
                await ctx.send(embeds=embeds[i:i+10])

    @commands.command(name='отчёт-настроить')
    @commands.has_permissions(administrator=True)
    async def setup_report(self, ctx, channel: discord.TextChannel, gun: int = 0, час: int = 9):
        """Otomatik haftalık отчётu настроить: !отчёт-настроить #channel [день] [час]"""
        cfg = _load_cfg(ctx.guild.id)
        cfg.update({'enabled': True, 'channel_id': channel.id, 'day': gun, 'hour': час})
        _save_cfg(ctx.guild.id, cfg)
        gun_names = ['Pazartesi', 'Salı', 'Çarşamba', 'Perşembe', 'Cuma', 'Cumartesi', 'Pazar']
        embed = discord.Embed(
            title='✅ Haftalık Отчёт Настроитьndı',
            color=0x57F287,
            description=(
                f'Her **{gun_names[gun]}** час **{час:02d}:00**\'de\n'
                f'{channel.mention} channelına otomatik отправитьilecek.'
            )
        )
        await ctx.send(embed=embed)

    @commands.command(name='отчёт-role-add')
    @commands.has_permissions(administrator=True)
    async def add_staff_role(self, ctx, role: discord.Role):
        """Отчётa right_btn roleü add: !отчёт-role-add @Роль"""
        cfg = _load_cfg(ctx.guild.id)
        if role.id not in cfg.get('staff_roles', []):
            cfg.setdefault('staff_roles', []).append(role.id)
            _save_cfg(ctx.guild.id, cfg)
        await ctx.send(f'✅ **{role.name}** roleü отчётa addndi.')

    @commands.command(name='отчёт-role-cikar')
    @commands.has_permissions(administrator=True)
    async def remove_staff_role(self, ctx, role: discord.Role):
        """Рольü отчётdan çıkar: !отчёт-role-cikar @Роль"""
        cfg = _load_cfg(ctx.guild.id)
        if role.id in cfg.get('staff_roles', []):
            cfg['staff_roles'].remove(role.id)
            _save_cfg(ctx.guild.id, cfg)
        await ctx.send(f'✅ **{role.name}** roleü отчётdan çıkarıldı.')

    @commands.command(name='toplanti-baslat')
    @commands.has_permissions(administrator=True)
    async def start_meeting(self, ctx, дата: str = None):
        """Toplantı запустить: !toplanti-baslat [GG.AA.YYYY]"""
        cfg = _load_cfg(ctx.guild.id)

        # Дата parse et
        if дата:
            try:
                dt = datetime.datetime.strptime(дата, '%d.%m.%Y')
                meeting_time = dt.replace(tzinfo=datetime.timezone.utc)
            except ValueError:
                await ctx.send('❌ Дата formatı yanlış! Örn: `!toplanti-baslat 12.04.2026`')
                return
        else:
            meeting_time = datetime.datetime.now(datetime.timezone.utc)

        async with ctx.typing():
            if cfg.get('last_meeting'):
                try:
                    embeds = await _build_weekly_report(ctx.guild)
                    for i in range(0, len(embeds), 10):
                        await ctx.send(embeds=embeds[i:i+10])
                except Exception as e:
                    await ctx.send(f'⚠️ Отчёт создатьulurken Ошибка: {e}')

        cfg['last_meeting'] = meeting_time.isoformat()
        _save_cfg(ctx.guild.id, cfg)
        ts = int(meeting_time.timestamp())
        await ctx.send(f'✅ Toplantı датаi настроитьndı: <t:{ts}:F>\nBir следующий отчёт bu датаten itibaren sayacak.')

    @commands.command(name='toplanti-sayac')
    async def meeting_counter(self, ctx):
        """Последний toplantıdan kaç день geçti: !toplanti-sayac"""
        cfg = _load_cfg(ctx.guild.id)
        if not cfg.get('last_meeting'):
            await ctx.send('❌ Henüz toplantı запуститьılmadı. `!toplanti-baslat` kullan.')
            return
        try:
            last = datetime.datetime.fromisoformat(cfg['last_meeting'])
            if last.tzinfo is None:
                last = last.replace(tzinfo=datetime.timezone.utc)
            now = datetime.datetime.now(datetime.timezone.utc)
            days = (now - last).days
            ts = int(last.timestamp())
            embed = discord.Embed(
                title='📅 Toplantı Sayacı',
                color=0x5865F2,
                description=(
                    f'Последний toplantı: <t:{ts}:F>\n'
                    f'Geçen süre: **{days} день**'
                )
            )
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(f'❌ Ошибка: {e}')

    @commands.command(name='mod-istatistik', aliaголос=['modstats'])
    @commands.has_permissions(manage_messages=True)
    async def mod_stats(self, ctx, moderator: discord.Member = None):
        """Модератор istatistikleri: !mod-istatistik [@kişi]"""
        target = moderator or ctx.author
        data = _load_mod_data()
        gid = str(ctx.guild.id)
        caголос = data.get('caголос', {}).get(gid, [])
        mod_caголос = [c for c in caголос if c['mod_id'] == str(target.id)]
        action_counts = defaultdict(int)
        for c in mod_caголос:
            action_counts[c['action'].lower()] += 1
        lb = _load_lb(ctx.guild.id)
        inv = _load_invites(ctx.guild.id)
        uid = str(target.id)
        msg = lb.get('messages', {}).get(uid, 0)
        voice = lb.get('voice_minutes', {}).get(uid, 0)
        invites_cnt = inv.get(uid, 0)
        h, mn = divmod(voice, 60)
        embed = discord.Embed(
            title=f'📊 {target.display_name}',
            color=target.accent_color or 0x5865F2,
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(
            name='📈 Aktivite',
            value=f'```yaml\nСообщение  : {msg:,}\nГолос    : {h}s {mn}dk\nDavet  : {invites_cnt}\n```',
            inline=True
        )
        embed.add_field(
            name='⚔️ Moderasyon',
            value=(
                f'```yaml\n'
                f'Всего : {len(mod_caголос)}\n'
                f'Бан    : {action_counts.get("ban", 0)}\n'
                f'Кик   : {action_counts.get("kick", 0)}\n'
                f'Мут: {action_counts.get("timeout", 0)}\n'
                f'Warning  : {action_counts.get("warn", 0)}\n'
                f'```'
            ),
            inline=True
        )
        embed.set_footer(text=f'{ctx.guild.name} • Aether')
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(ModReport(bot))
    bot.add_view(ModReportView())
