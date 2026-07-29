"""
Aether Social Cog
- Gelişmiş опрос sistemi (çoklu выбратьenek, vakitlı, anonim, grafik)
- Event planlayıcısı (etkinlik takvimi, katılımcı listesi, hatırlatmalar)
- Matchmaking sistemi (oyun arkadaşı bulma, takım создатьma)
"""
import discord
from discord.ext import commands, tasks
from discord import app_commands
import json, os
from datetime import datetime, timezone, timedelta
from typing import Optional

POLL_FILE   = 'data/polls_{guild_id}.json'
EVENT_FILE  = 'data/events_{guild_id}.json'
MATCH_FILE  = 'data/matchmaking_{guild_id}.json'

# Emoji bar için
BAR_FULL  = '█'
BAR_EMPTY = '░'

def _bar(ratio: float, length: int = 12) -> str:
    filled = round(ratio * length)
    return BAR_FULL * filled + BAR_EMPTY * (length - filled)

def _load(path): 
    return json.load(open(path, 'r', encoding='utf-8')) if os.path.exists(path) else {}

def _save(path, data):
    os.makedirs('data', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ══════════════════════════════════════════════════════════════════════════════
# POLL VIEW
# ══════════════════════════════════════════════════════════════════════════════
class PollView(discord.ui.View):
    def __init__(self, poll_id: str, options: list, anonymous: bool, guild_id: str):
        super().__init__(timeout=None)
        self.poll_id = poll_id
        self.guild_id = guild_id
        self.anonymous = anonymous
        emojis = ['1️⃣','2️⃣','3️⃣','4️⃣','5️⃣','6️⃣','7️⃣','8️⃣','9️⃣','🔟']
        for i, opt in enumerate(options[:10]):
            btn = discord.ui.Button(
                label=opt[:80],
                emoji=emojis[i],
                style=discord.ButtonStyle.secondary,
                custom_id=f"poll_{poll_id}_{i}"
            )
            btn.callback = self._make_callback(i)
            self.add_item(btn)

    def _make_callback(self, idx: int):
        async def callback(interaction: discord.Interaction):
            path = POLL_FILE.format(guild_id=self.guild_id)
            data = _load(path)
            poll = data.get(self.poll_id)
            if not poll:
                await interaction.response.send_message("❌ Опрос bulunamadı.", ephemeral=True)
                return
            if poll.get('ended'):
                await interaction.response.send_message("❌ Bu опрос sona erdi.", ephemeral=True)
                return

            uid = str(interaction.user.id)
            votes = poll.setdefault('votes', {})

            # Aynı выбратьeneğe tekrar tıklarsa oyu geri al
            if votes.get(uid) == idx:
                del votes[uid]
                await interaction.response.send_message("🗑️ Oyun geri alındı.", ephemeral=True)
            else:
                votes[uid] = idx
                opt_name = poll['options'][idx]
                await interaction.response.send_message(
                    f"✅ **{opt_name}** выбратьeneğine oy verdin!" + (" (anonim)" if self.anonymous else ""),
                    ephemeral=True
                )

            _save(path, data)
            # Embed'i güncelle
            await _update_poll_embed(interaction.message, poll)
        return callback


async def _update_poll_embed(message: discord.Message, poll: dict):
    votes = poll.get('votes', {})
    total = len(votes)
    options = poll['options']
    counts = [sum(1 for v in votes.values() if v == i) for i in range(len(options))]

    e = message.embeds[0] if message.embeds else discord.Embed()
    e.clear_fields()
    emojis = ['1️⃣','2️⃣','3️⃣','4️⃣','5️⃣','6️⃣','7️⃣','8️⃣','9️⃣','🔟']
    for i, (opt, cnt) in enumerate(zip(options, counts)):
        ratio = cnt / total if total > 0 else 0
        bar = _bar(ratio)
        pct = f"{ratio:.0%}"
        e.add_field(
            name=f"{emojis[i]} {opt}",
            value=f"`{bar}` **{pct}** ({cnt} oy)",
            inline=False
        )
    e.set_footer(text=f"📊 Всего {total} oy • Aynı butona tıklayarak oyunu geri alabilirsin")
    try:
        await message.edit(embed=e)
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
# EVENT VIEW
# ══════════════════════════════════════════════════════════════════════════════
class EventJoinView(discord.ui.View):
    def __init__(self, event_id: str, guild_id: str):
        super().__init__(timeout=None)
        self.event_id = event_id
        self.guild_id = guild_id

    @discord.ui.button(label="Katıl", emoji="✅", style=discord.ButtonStyle.success, custom_id="event_join")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        path = EVENT_FILE.format(guild_id=self.guild_id)
        data = _load(path)
        event = data.get(self.event_id)
        if not event:
            await interaction.response.send_message("❌ Etkinlik bulunamadı.", ephemeral=True)
            return
        uid = str(interaction.user.id)
        participants = event.setdefault('participants', [])
        if uid in participants:
            participants.remove(uid)
            msg = "❌ Etkinlikten ayrıldın."
        else:
            participants.append(uid)
            msg = f"✅ **{event['title']}** etkinliğine katıldın!"
        _save(path, data)
        await interaction.response.send_message(msg, ephemeral=True)
        # Embed güncelle
        await _update_event_embed(interaction.message, event)

    @discord.ui.button(label="Katılımcılar", emoji="👥", style=discord.ButtonStyle.secondary, custom_id="event_list")
    async def list_participants(self, interaction: discord.Interaction, button: discord.ui.Button):
        path = EVENT_FILE.format(guild_id=self.guild_id)
        data = _load(path)
        event = data.get(self.event_id, {})
        participants = event.get('participants', [])
        if not participants:
            await interaction.response.send_message("Henüz katılımcı yok.", ephemeral=True)
            return
        mentions = [f"<@{uid}>" for uid in participants[:20]]
        await interaction.response.send_message(
            f"**👥 Katılımcılar ({len(participants)}):**\n" + ", ".join(mentions),
            ephemeral=True
        )


async def _update_event_embed(message: discord.Message, event: dict):
    participants = event.get('participants', [])
    e = message.embeds[0] if message.embeds else discord.Embed()
    # Katılımcı sayısını güncelle
    for i, field in enumerate(e.fields):
        if '👥' in field.name:
            e.set_field_at(i, name=field.name, value=f"`{len(participants)} kişi`", inline=field.inline)
            break
    try:
        await message.edit(embed=e)
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
# MATCHMAKING VIEW
# ══════════════════════════════════════════════════════════════════════════════
class MatchView(discord.ui.View):
    def __init__(self, match_id: str, guild_id: str, max_players: int):
        super().__init__(timeout=None)
        self.match_id = match_id
        self.guild_id = guild_id
        self.max_players = max_players

    @discord.ui.button(label="Katıl", emoji="🎮", style=discord.ButtonStyle.success, custom_id="match_join")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        path = MATCH_FILE.format(guild_id=self.guild_id)
        data = _load(path)
        match = data.get(self.match_id)
        if not match:
            await interaction.response.send_message("❌ Eşleşme bulunamadı.", ephemeral=True)
            return
        uid = str(interaction.user.id)
        players = match.setdefault('players', [])
        if uid in players:
            players.remove(uid)
            await interaction.response.send_message("❌ Eşleşmeden ayrıldın.", ephemeral=True)
        elif len(players) >= self.max_players:
            await interaction.response.send_message("❌ Eşleşme dolu!", ephemeral=True)
            return
        else:
            players.append(uid)
            await interaction.response.send_message(f"✅ **{match['game']}** eşleşmesine katıldın!", ephemeral=True)
        _save(path, data)
        await _update_match_embed(interaction.message, match, self.max_players)

        # Takım doldu mu?
        if len(players) >= self.max_players:
            await interaction.channel.send(
                f"🎮 **{match['game']}** takımı doldu! "
                + " ".join(f"<@{p}>" for p in players)
                + "\nHaydi oynayın! 🚀"
            )


async def _update_match_embed(message: discord.Message, match: dict, max_players: int):
    players = match.get('players', [])
    e = message.embeds[0] if message.embeds else discord.Embed()
    for i, field in enumerate(e.fields):
        if '👥' in field.name:
            e.set_field_at(i, name=field.name, value=f"`{len(players)}/{max_players}`", inline=field.inline)
            break
    try:
        await message.edit(embed=e)
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
# MAIN COG
# ══════════════════════════════════════════════════════════════════════════════
class Social(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.poll_checker.start()
        self.event_reminder.start()

    def cog_unload(self):
        self.poll_checker.cancel()
        self.event_reminder.cancel()

    # ── ANKET ─────────────────────────────────────────────────────────────────
    @app_commands.command(name="опрос", description="Новый опрос создать")
    @app_commands.describe(
        soru="Опрос sorusu",
        secenaddr="Выбратьenaddr (virgülle ayır, max 10)",
        sure="Süre minutes cinsinden (0 = süresiz)",
        anonim="Anonim oylama?"
    )
    @app_commands.checks.has_permissions(moderate_members=True)
    async def poll_create(self, interaction: discord.Interaction,
                          soru: str, secenaddr: str,
                          sure: int = 0, anonim: bool = False):
        options = [o.strip() for o in secenaddr.split(',') if o.strip()][:10]
        if len(options) < 2:
            await interaction.response.send_message("❌ En az 2 выбратьenek gir!", ephemeral=True)
            return

        guild_id = str(interaction.guild.id)
        path = POLL_FILE.format(guild_id=guild_id)
        data = _load(path)

        poll_id = str(int(datetime.now().timestamp()))
        ends_at = (datetime.now(timezone.utc) + timedelta(minutes=sure)).isoformat() if sure > 0 else None

        poll = {
            'id': poll_id,
            'question': soru,
            'options': options,
            'votes': {},
            'anonymous': anonim,
            'created_by': str(interaction.user.id),
            'ends_at': ends_at,
            'ended': False,
            'channel_id': str(interaction.channel.id),
            'message_id': None,
        }
        data[poll_id] = poll
        _save(path, data)

        emojis = ['1️⃣','2️⃣','3️⃣','4️⃣','5️⃣','6️⃣','7️⃣','8️⃣','9️⃣','🔟']
        e = discord.Embed(
            title=f"📊 {soru}",
            color=0x3498db,
            timestamp=datetime.now(timezone.utc)
        )
        e.description = f"{'🔒 Anonim oylama' if anonim else '👁️ Открыт oylama'}"
        for i, opt in enumerate(options):
            e.add_field(name=f"{emojis[i]} {opt}", value=f"`{'░'*12}` **0%** (0 oy)", inline=False)
        if ends_at:
            e.add_field(name="⏰ Bitiş", value=f"<t:{int(datetime.fromisoformat(ends_at).timestamp())}:R>", inline=True)
        e.set_footer(text=f"📊 Всего 0 oy • Aynı butona tıklayarak oyunu geri alabilirsin")
        e.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)

        view = PollView(poll_id, options, anonim, guild_id)
        await interaction.response.send_message(embed=e, view=view)
        msg = await interaction.original_response()

        # Сообщение ID'sini сохранить
        data[poll_id]['message_id'] = str(msg.id)
        _save(path, data)

    @app_commands.command(name="опрос-bitir", description="Опросi завершить")
    @app_commands.describe(опрос_id="Опрос ID")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def poll_end(self, interaction: discord.Interaction, опрос_id: str):
        guild_id = str(interaction.guild.id)
        path = POLL_FILE.format(guild_id=guild_id)
        data = _load(path)
        poll = data.get(опрос_id)
        if not poll:
            await interaction.response.send_message("❌ Опрос bulunamadı.", ephemeral=True)
            return
        poll['ended'] = True
        _save(path, data)
        await interaction.response.send_message(f"✅ Опрос `{опрос_id}` завершитьıldı.", ephemeral=True)

    @tasks.loop(minutes=1)
    async def poll_checker(self):
        """Süresi dolan опросleri otomatik закрыть."""
        now = datetime.now(timezone.utc)
        for guild in self.bot.guilds:
            path = POLL_FILE.format(guild_id=str(guild.id))
            data = _load(path)
            changed = False
            for poll in data.values():
                if poll.get('ended') or not poll.get('ends_at'):
                    continue
                ends_at = datetime.fromisoformat(poll['ends_at'])
                if now >= ends_at:
                    poll['ended'] = True
                    changed = True
                    # sonuç messageı отправить
                    try:
                        ch = guild.get_channel(int(poll['channel_id']))
                        if ch:
                            votes = poll.get('votes', {})
                            total = len(votes)
                            options = poll['options']
                            counts = [sum(1 for v in votes.values() if v == i) for i in range(len(options))]
                            winner_idx = counts.index(max(counts)) if counts else 0
                            e = discord.Embed(
                                title=f"📊 Опрос sonuçlandı: {poll['question']}",
                                color=0x2ecc71
                            )
                            emojis = ['1️⃣','2️⃣','3️⃣','4️⃣','5️⃣','6️⃣','7️⃣','8️⃣','9️⃣','🔟']
                            for i, (opt, cnt) in enumerate(zip(options, counts)):
                                ratio = cnt / total if total > 0 else 0
                                winner_mark = " 🏆" if i == winner_idx else ""
                                e.add_field(
                                    name=f"{emojis[i]} {opt}{winner_mark}",
                                    value=f"`{_bar(ratio)}` **{ratio:.0%}** ({cnt} oy)",
                                    inline=False
                                )
                            e.set_footer(text=f"Всего {total} oy")
                            await ch.send(embed=e)
                    except Exception:
                        pass
            if changed:
                _save(path, data)

    @poll_checker.before_loop
    async def before_poll_checker(self):
        await self.bot.wait_until_ready()

    # ── ETKİNLİK ─────────────────────────────────────────────────────────────
    @app_commands.command(name="etkinlik", description="Новый etkinlik создать")
    @app_commands.describe(
        baslik="Etkinlik başlığı",
        aciklama="Etkinlik описаниеsı",
        дата="Дата (GG.AA.YYYY SS:DD formatında)",
        max_katilimci="Maksimum katılımcı sayısı (0 = sınırsız)"
    )
    @app_commands.checks.has_permissions(moderate_members=True)
    async def event_create(self, interaction: discord.Interaction,
                           baslik: str, aciklama: str,
                           дата: str, max_katilimci: int = 0):
        try:
            event_dt = datetime.strptime(дата, '%d.%m.%Y %H:%M').replace(tzinfo=timezone.utc)
        except ValueError:
            await interaction.response.send_message(
                "❌ Дата formatı yanlış! Örnek: `25.12.2025 20:00`", ephemeral=True
            )
            return

        guild_id = str(interaction.guild.id)
        path = EVENT_FILE.format(guild_id=guild_id)
        data = _load(path)

        event_id = str(int(datetime.now().timestamp()))
        event = {
            'id': event_id,
            'title': baslik,
            'description': aciklama,
            'date': event_dt.isoformat(),
            'max_participants': max_katilimci,
            'participants': [],
            'created_by': str(interaction.user.id),
            'channel_id': str(interaction.channel.id),
            'message_id': None,
            'reminded': False,
        }
        data[event_id] = event
        _save(path, data)

        e = discord.Embed(
            title=f"🎉 {baslik}",
            description=aciklama,
            color=0x9b59b6,
            timestamp=datetime.now(timezone.utc)
        )
        e.add_field(name="📅 Дата", value=f"<t:{int(event_dt.timestamp())}:F>", inline=True)
        e.add_field(name="⏰ Ne Время", value=f"<t:{int(event_dt.timestamp())}:R>", inline=True)
        e.add_field(name="👥 Katılımcılar", value="`0 kişi`" + (f" / {max_katilimci}" if max_katilimci else ""), inline=True)
        e.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        e.set_footer(text=f"🎉 Aether Event Sistemi • ID: {event_id}")

        view = EventJoinView(event_id, guild_id)
        await interaction.response.send_message(embed=e, view=view)
        msg = await interaction.original_response()
        data[event_id]['message_id'] = str(msg.id)
        _save(path, data)

    @app_commands.command(name="etkinlik-listesi", description="Yaklaşan etkinlikleri listele")
    async def event_list(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)
        path = EVENT_FILE.format(guild_id=guild_id)
        data = _load(path)
        now = datetime.now(timezone.utc)

        upcoming = sorted(
            [e for e in data.values() if datetime.fromisoformat(e['date']) > now],
            key=lambda x: x['date']
        )

        e = discord.Embed(title="📅 Yaklaşan Etkinlikler", color=0x9b59b6, timestamp=now)
        if not upcoming:
            e.description = "Yaklaşan etkinlik yok."
        else:
            for ev in upcoming[:8]:
                dt = datetime.fromisoformat(ev['date'])
                e.add_field(
                    name=f"🎉 {ev['title']}",
                    value=f"<t:{int(dt.timestamp())}:F> • {len(ev.get('participants', []))} katılımcı",
                    inline=False
                )
        await interaction.response.send_message(embed=e, ephemeral=True)

    @tasks.loop(minutes=10)
    async def event_reminder(self):
        """Etkinlikten 30 minutes önce hatırlatma отправить."""
        now = datetime.now(timezone.utc)
        for guild in self.bot.guilds:
            path = EVENT_FILE.format(guild_id=str(guild.id))
            data = _load(path)
            changed = False
            for event in data.values():
                if event.get('reminded'):
                    continue
                dt = datetime.fromisoformat(event['date'])
                diff = (dt - now).total_seconds()
                if 0 < diff <= 1800:  # 30 minutes
                    event['reminded'] = True
                    changed = True
                    try:
                        ch = guild.get_channel(int(event['channel_id']))
                        if ch:
                            participants = event.get('participants', [])
                            mentions = " ".join(f"<@{uid}>" for uid in participants) if participants else "@here"
                            await ch.send(
                                f"⏰ **{event['title']}** etkinliği **30 minutes** sonra başlıyor!\n{mentions}"
                            )
                    except Exception:
                        pass
            if changed:
                _save(path, data)

    @event_reminder.before_loop
    async def before_event_reminder(self):
        await self.bot.wait_until_ready()

    # ── MATCHMAKING ───────────────────────────────────────────────────────────
    @app_commands.command(name="oyun-ara", description="Oyun arkadaşı ara")
    @app_commands.describe(
        oyun="Oyun adı",
        max_oyuncu="Kaç kişilik takım?",
        not_="Ek not (rank, mod, vb.)"
    )
    async def matchmaking_create(self, interaction: discord.Interaction,
                                  oyun: str, max_oyuncu: int = 5,
                                  not_: Optional[str] = None):
        if max_oyuncu < 2 or max_oyuncu > 20:
            await interaction.response.send_message("❌ Oyuncu sayısı 2-20 arasında olmalı!", ephemeral=True)
            return

        guild_id = str(interaction.guild.id)
        path = MATCH_FILE.format(guild_id=guild_id)
        data = _load(path)

        match_id = str(int(datetime.now().timestamp()))
        match = {
            'id': match_id,
            'game': oyun,
            'max_players': max_oyuncu,
            'players': [str(interaction.user.id)],
            'note': not_,
            'created_by': str(interaction.user.id),
            'created_at': datetime.now(timezone.utc).isoformat(),
        }
        data[match_id] = match
        _save(path, data)

        e = discord.Embed(
            title=f"🎮 {oyun} — Oyuncu Поискnıyor",
            color=0x1abc9c,
            timestamp=datetime.now(timezone.utc)
        )
        e.add_field(name="👥 Oyuncular", value=f"`1/{max_oyuncu}`", inline=True)
        e.add_field(name="🎯 Oyun", value=f"`{oyun}`", inline=True)
        if not_:
            e.add_field(name="📝 Not", value=f"`{not_}`", inline=True)
        e.add_field(name="👤 Создатьan", value=interaction.user.mention, inline=True)
        e.set_footer(text=f"🎮 Aether Matchmaking • Takım dolunca уведомление gelir")
        e.set_thumbnail(url=interaction.user.display_avatar.url)

        view = MatchView(match_id, guild_id, max_oyuncu)
        await interaction.response.send_message(embed=e, view=view)

    @app_commands.command(name="oyun-listesi", description="Активен oyun aramalarını listele")
    async def matchmaking_list(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)
        path = MATCH_FILE.format(guild_id=guild_id)
        data = _load(path)

        # Последний 2 часteki активна aramalar
        now = datetime.now(timezone.utc)
        active = [
            m for m in data.values()
            if (now - datetime.fromisoformat(m['created_at'])).total_seconds() < 7200
            and len(m.get('players', [])) < m['max_players']
        ]

        e = discord.Embed(title="🎮 Активен Oyun Поискmaları", color=0x1abc9c, timestamp=now)
        if not active:
            e.description = "Şu an активна oyun araması yok.\n`/oyun-ara` ile yeni arama запустить!"
        else:
            for m in active[:8]:
                players = m.get('players', [])
                e.add_field(
                    name=f"🎮 {m['game']}",
                    value=f"👥 `{len(players)}/{m['max_players']}` • {m.get('note', '')} • <@{m['created_by']}>",
                    inline=False
                )
        await interaction.response.send_message(embed=e, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Social(bot), guilds=[discord.Object(id=1421244140359909513), discord.Object(id=1107038411895881788)])
