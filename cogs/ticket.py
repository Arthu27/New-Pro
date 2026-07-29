import discord
from discord.ext import commands
from discord import app_commands
import datetime
import io
import json
import os
from cogs.embed_utils import gif, now_ts, _divider

TICKET_CATEGORY_NAME = "Ticketlar"
SUPPORT_ROLE_NAME = "Destek"

GIF_TICKET_OPEN  = "https://media.tenor.com/3Ky6UNqMFpkAAAAC/talking-speak.gif"
GIF_TICKET_CLOSE = "https://media.tenor.com/x8v1oNUOmg4AAAAC/ban-hammer.gif"
GIF_PANEL        = "https://media.tenor.com/ZBDpMFBMFpkAAAAC/celebration-party.gif"

# AI Ticket Settings
AI_ENABLED = True  # AI destek sistemi активна
MAX_AI_MESSAGES = 10

# Bu serverlarda ticket sistemi devre dışı
TICKET_DISABLED_GUILDS: set = set()


class TicketCategoryView(discord.ui.View):
    """Ticket açıldığında kategori выбратьim butonları"""
    def __init__(self, channel_id: int, guild_id: int):
        super().__init__(timeout=300)
        self.channel_id = channel_id
        self.guild_id = guild_id

    async def _set_category(self, interaction: discord.Interaction, category: str, label: str):
        cog = interaction.client.get_cog('Ticket')
        if cog:
            state = cog._get_ticket_state(self.guild_id, self.channel_id)
            state['category'] = category
            
            # Şikayet kategorisinde direkt şikayet akışını запустить
            if category == 'sikayet':
                state['complaint'] = {
                    'active': True,
                    'step': 'ask_description',
                    'type': None,
                    'accused_id': None,
                    'channel_id': None,
                    'messages': [],
                    'description': None,
                }
            
            cog._save_ticket_state(self.guild_id, self.channel_id, state)

        category_hints = {
            'sikayet': (
                '🚨 **Şikayet kategorisi выбратьildi.**\n\n'
                'Ne yaşandığını kısaca anlat:'
            ),
            'soru': (
                '❓ **Soru/Yardım kategorisi выбратьildi.**\n\n'
                'Nasıl yardımcı olabilirim? Ne hakkında info almak istiyorsun?\n'
                '> Панель, регистрация, командаlar, roleler, economy, level...'
            ),
            'teknik': (
                '🔧 **Teknik sorun kategorisi выбратьildi.**\n\n'
                'Nasıl yardımcı olabilirim? Hangi sorunla karşılaştın?\n'
                '> Бот, müzik, команда çalışmıyor, Ошибка messageı...'
            ),
        }

        hint = category_hints.get(category, '💬 Nasıl yardımcı olabilirim?')
        e = discord.Embed(description=hint, color=0x00D9FF)
        await interaction.response.send_message(embed=e)
        # Butonları devre dışı bırak
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)

    @discord.ui.button(label='🚨  Şikayet', style=discord.ButtonStyle.danger, custom_id='ticket_cat_sikayet')
    async def btn_sikayet(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._set_category(interaction, 'sikayet', 'Şikayet')

    @discord.ui.button(label='❓  Soru / Yardım', style=discord.ButtonStyle.primary, custom_id='ticket_cat_soru')
    async def btn_soru(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._set_category(interaction, 'soru', 'Soru')

    @discord.ui.button(label='🔧  Teknik Sorun', style=discord.ButtonStyle.secondary, custom_id='ticket_cat_teknik')
    async def btn_teknik(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._set_category(interaction, 'teknik', 'Teknik')


class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🎫  Destek Talebi Создать",
        style=discord.ButtonStyle.blurple,
        custom_id="ticket_open"
    )
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        
        # Bu serverda ticket devre dışı
        if guild.id in TICKET_DISABLED_GUILDS:
            await interaction.response.send_message(
                '❌ Bu serverda ticket sistemi активна değil.', ephemeral=True
            )
            return
        
        existing = discord.utils.get(guild.text_channels, name=f"ticket-{interaction.user.name.lower()}")
        if existing:
            await interaction.response.send_message(
                f"⚠️ Zaten açık bir destek channelın var: {existing.mention}\nLütfen önce onu закрыть.",
                ephemeral=True
            )
            return
        
        # ÖNCE response отправить (3 saniye kuralı)
        await interaction.response.send_message(
            "🎫 Destek channelın создатьuluyor...",
            ephemeral=True
        )

        category = discord.utils.get(guild.categories, name=TICKET_CATEGORY_NAME)
        if not category:
            category = await guild.create_category(TICKET_CATEGORY_NAME)

        support_role = discord.utils.get(guild.roles, name=SUPPORT_ROLE_NAME)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }
        if support_role:
            overwrites[support_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        channel = await guild.create_text_channel(
            f"ticket-{interaction.user.name.lower()}",
            category=category,
            overwrites=overwrites,
            topic=f"Ticket sahibi: {interaction.user.id}"
        )

        ts = int(datetime.datetime.utcnow().timestamp())

        # Канал içi hoşgeldin embed
        e = discord.Embed(
            title="🎫  DESTEK TALEBİ OLUŞTURULDU",
            color=0x5865F2,
            timestamp=datetime.datetime.utcnow()
        )
        e.description = (
            f"```ansi\n\u001b[1;34m✔ TALEBİN ALINDI\u001b[0m\n```\n"
            f"{_divider()}\n\n"
            f"Merhaba {interaction.user.mention}, destek ekibimize hoş geldin! 👋\n\n"
            "**Lütfen aşağıdaki bilgileri paylaş:**\n"
            "```yaml\n"
            "• Yaşadığın sorunu kısaca açıkla\n"
            "• Естьsa ekran görüntüsü add\n"
            "• Sorunun ne vakit başladığını belirt\n"
            "```\n"
            f"{_divider()}"
        )
        e.set_thumbnail(url=interaction.user.display_avatar.url)
        e.set_image(url=GIF_TICKET_OPEN)
        e.add_field(name="⏱️ Ortalama Yanıt Süresi", value="```yaml\n5 — 15 minutes\n```", inline=True)
        e.add_field(name="📅 Создатьulma", value=f"<t:{ts}:R>", inline=True)
        e.add_field(name="🔒 Каналı Закрытьmak İçin", value="```Нажмите кнопку ниже```", inline=False)
        e.set_footer(
            text=f"Aether Destek • {guild.name}",
            icon_url=guild.icon.url if guild.icon else None
        )

        await channel.send(
            content=f"{interaction.user.mention}" + (f" | {support_role.mention}" if support_role else ""),
            embed=e,
            view=CloseTicketView()
        )
        
        # AI karудалитьama messagei gonder
        if AI_ENABLED:
            try:
                from web.ai_helper import ai_ticket_greeting

                state = {
                    'user_id': interaction.user.id,
                    'category': None,
                    'history': [],
                    'status': 'ai_handling',
                    'ai_message_count': 0,
                    'escalated_at': None,
                    'staff_notified': False
                }

                cog = interaction.client.get_cog('Ticket')
                if cog:
                    cog._save_ticket_state(guild.id, channel.id, state)

                greeting = ai_ticket_greeting()
                ai_embed = discord.Embed(
                    color=0x00D9FF,
                    timestamp=datetime.datetime.utcnow()
                )
                ai_embed.description = greeting
                ai_embed.set_author(
                    name="Aether AI Destek",
                    icon_url=interaction.client.user.display_avatar.url
                )
                ai_embed.set_footer(text="Çözemediğim statuslarda right_btnlere otomatik yönlendiririm.")
                await channel.send(
                    embed=ai_embed,
                    view=TicketCategoryView(channel.id, guild.id)
                )
            except Exception:
                pass

        # Пользователю DM
        try:
            dm_e = discord.Embed(
                title="🎫  Destek Talebiniz Создано",
                color=0x5865F2,
                timestamp=datetime.datetime.utcnow()
            )
            dm_e.description = (
                f"```ansi\n\u001b[1;34m✔ TALEBİN ALINDI\u001b[0m\n```\n"
                f"{_divider()}\n\n"
                f"**{guild.name}** serversunda bir destek talebi başarıyla açıldı.\n\n"
                "> Destek ekibimiz en kısa sürede seninle ilgilenecek.\n"
                "> Каналda sorununu detaylıca описаниеyı unutma!\n\n"
                f"{_divider()}"
            )
            dm_e.set_thumbnail(url=guild.icon.url if guild.icon else None)
            dm_e.add_field(name="📌 Канал", value=channel.mention, inline=True)
            dm_e.add_field(name="🕐 Создатьulma", value=f"<t:{ts}:R>", inline=True)
            dm_e.add_field(name="⏱️ Baddnen Yanıt", value="```5 — 15 minutes```", inline=False)
            dm_e.add_field(name="💡 İpucu", value="*Sorunu ne kadar detaylı anlatırsan, o kadar hızlı çözüm alırsın.*", inline=False)
            dm_e.set_image(url=GIF_TICKET_OPEN)
            dm_e.set_footer(text=f"Aether Destek • {guild.name}", icon_url=guild.icon.url if guild.icon else None)
            await interaction.user.send(embed=dm_e)
        except discord.Forbidden:
            pass

        # Followup messagei gonder (response zaten gonderildi)
        await interaction.followup.send(
            f"✅ Destek channelın создано: {channel.mention}",
            ephemeral=True
        )


class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🔒  Talebi Закрыть",
        style=discord.ButtonStyle.red,
        custom_id="ticket_close"
    )
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        if not channel.name.startswith("ticket-"):
            await interaction.response.send_message("Bu bir ticket channelı değil.", ephemeral=True)
            return

        # AI state'ini clear
        cog = interaction.client.get_cog('Ticket')
        if cog:
            cog._delete_ticket_state(interaction.guild.id, channel.id)

        messages = []
        async for msg in channel.history(limit=200, oldest_first=True):
            if not msg.author.bot:
                messages.append(f"[{msg.created_at.strftime('%d.%m.%Y %H:%M:%S')}] {msg.author.display_name}: {msg.content}")
        transcript = "\n".join(messages) if messages else "Сообщение bulunamadı."

        owner_id = None
        if channel.topic and "Ticket sahibi:" in channel.topic:
            try:
                owner_id = int(channel.topic.split("Ticket sahibi:")[-1].strip())
            except:
                pass

        ts = int(datetime.datetime.utcnow().timestamp())

        log_ch = discord.utils.get(interaction.guild.text_channels, name="ticket-log")
        if log_ch:
            log_e = discord.Embed(
                title="📋  Destek Talebi Закрытьıldı",
                color=0xE74C3C,
                timestamp=datetime.datetime.utcnow()
            )
            log_e.description = (
                f"```ansi\n\u001b[1;31m🔒 KAPATILDI\u001b[0m\n```\n"
                f"{_divider()}"
            )
            log_e.add_field(name="📁 Канал", value=f"`{channel.name}`", inline=True)
            log_e.add_field(name="👤 Закрытьan", value=interaction.user.mention, inline=True)
            log_e.add_field(name="📅 Дата", value=f"<t:{ts}:F>", inline=False)
            log_e.add_field(name="💬 Сообщение Sayısı", value=f"```{len(messages)} message```", inline=True)
            log_e.set_footer(text="Aether Destek")
            file = discord.File(fp=io.StringIO(transcript), filename=f"{channel.name}_transcript.txt")
            await log_ch.send(embed=log_e, file=file)

        if owner_id:
            try:
                owner = await interaction.guild.fetch_member(owner_id)
                dm_e = discord.Embed(
                    title="🔒  Destek Talebiniz Закрытьıldı",
                    color=0xE74C3C,
                    timestamp=datetime.datetime.utcnow()
                )
                dm_e.description = (
                    f"```ansi\n\u001b[1;31m🔒 TALEBİN KAPATILDI\u001b[0m\n```\n"
                    f"{_divider()}\n\n"
                    f"**{interaction.guild.name}** serversundaki destek talebiniz закрытьıldı.\n\n"
                    "> Новый bir sorunuz olursa tekrar destek talebi создатьabilirsiniz.\n"
                    "> Transcript dosyası server регистрацияlarına addndi.\n\n"
                    f"{_divider()}"
                )
                dm_e.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
                dm_e.add_field(name="👤 Закрытьan", value=f"```{interaction.user.display_name}```", inline=True)
                dm_e.add_field(name="🕐 Kapanma", value=f"<t:{ts}:R>", inline=True)
                dm_e.add_field(name="💬 Всего Сообщение", value=f"```{len(messages)} message```", inline=True)
                dm_e.add_field(name="💡 Информация", value="*Новый bir sorun için tekrar destek talebi açabilirsiniz.*", inline=False)
                dm_e.set_image(url=GIF_TICKET_CLOSE)
                dm_e.set_footer(
                    text=f"Aether Destek • {interaction.guild.name}",
                    icon_url=interaction.guild.icon.url if interaction.guild.icon else None
                )
                await owner.send(embed=dm_e)
            except:
                pass

        await interaction.response.send_message("🔒 Destek talebi закрытьılıyor, transcript сохранено...")
        await channel.delete()


class Ticket(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        bot.add_view(TicketView())
        bot.add_view(CloseTicketView())
    
    def _get_ai_data_path(self, guild_id: int) -> str:
        """AI ticket data dosya yolu"""
        return f"data/ai_tickets_{guild_id}.json"
    
    def _record_penalty(self, guild_id: int, user_id: int, user_name: str, reason: str, duration: int):
        """Наказание kaydını global penalty dosyasına yaz"""
        try:
            _penalty_file = 'data/ticket_penalties.json'
            _penalties = {}
            if os.path.exists(_penalty_file):
                with open(_penalty_file, 'r', encoding='utf-8') as _f:
                    _penalties = json.load(_f)
            
            # Новый format: liste olarak sakla (geçmiş cezalar için)
            guild_str = str(guild_id)
            user_str = str(user_id)
            
            if guild_str not in _penalties:
                _penalties[guild_str] = {}
            if user_str not in _penalties[guild_str]:
                _penalties[guild_str][user_str] = []
            
            # Наказание kaydını add
            _penalties[guild_str][user_str].append({
                'name': user_name,
                'reason': reason,
                'date': datetime.datetime.utcnow().isoformat(),
                'duration': duration,
            })
            
            os.makedirs('data', exist_ok=True)
            with open(_penalty_file, 'w', encoding='utf-8') as _f:
                json.dump(_penalties, _f, ensure_ascii=False, indent=2)
        except Exception as _pe:
            print(f'[TICKET] Наказание kaydı Ошибкаsı: {_pe}')
    
    def _get_penalty_history(self, guild_id: int, user_id: int, days: int = 7) -> list:
        """Последний X день içindeki ceza geçmişini getir"""
        try:
            _penalty_file = 'data/ticket_penalties.json'
            if not os.path.exists(_penalty_file):
                return []
            
            with open(_penalty_file, 'r', encoding='utf-8') as _f:
                _penalties = json.load(_f)
            
            guild_str = str(guild_id)
            user_str = str(user_id)
            
            if guild_str not in _penalties or user_str not in _penalties[guild_str]:
                return []
            
            user_penalties = _penalties[guild_str][user_str]
            cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=days)
            
            recent = []
            for p in user_penalties:
                try:
                    p_date = datetime.datetime.fromisoformat(p['date'])
                    if p_date > cutoff:
                        recent.append(p)
                except:
                    pass
            
            return recent
        except Exception as e:
            print(f'[TICKET] Penalty history Ошибкаsı: {e}')
            return []
    
    def _calculate_penalty_duration(self, guild_id: int, user_id: int, base_duration: int) -> int:
        """Geçmiş cezalara göre süreyi hesapla (gradation)"""
        history = self._get_penalty_history(guild_id, user_id, days=7)
        history_count = len(history)
        
        # Первый ihlal: base_duration
        # İkinci: 2x
        # Üçüncü: 4x
        # Dördüncü+: 8x (max 24 час)
        multiplier = 2 ** min(history_count, 3)
        calculated = base_duration * multiplier
        
        # Max 1440 minutes (24 час)
        return min(calculated, 1440)
    
    def _get_ai_confidence(self, verdict: str) -> int:
        """AI kararının güven skorunu hesapla (0-100)"""
        # Basit heuristic: belirli kelimelere göre güven skoru
        confidence = 50  # Естьsayılan
        
        verdict_lower = verdict.lower()
        
        # Yüksek güven göstergeleri
        if 'açık' in verdict_lower or 'kesin' in verdict_lower or 'net' in verdict_lower:
            confidence += 30
        if 'doğrudan' in verdict_lower or 'direkt' in verdict_lower:
            confidence += 20
        if 'удалено' in verdict_lower or 'удалитьinmiş' in verdict_lower:
            confidence += 15
        
        # Düşük güven göstergeleri
        if 'belirsiz' in verdict_lower or 'bağlam' in verdict_lower:
            confidence -= 30
        if 'yetersiz' in verdict_lower or 'eksik' in verdict_lower:
            confidence -= 20
        if 'olabilir' in verdict_lower or 'muhtemelen' in verdict_lower:
            confidence -= 15
        
        return max(0, min(100, confidence))
    
    def _load_ai_data(self, guild_id: int) -> dict:
        """AI ticket verilerini yukle"""
        path = self._get_ai_data_path(guild_id)
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                # Bozuk JSON — backup al ve sıfırla
                import shutil
                shutil.copy(path, path + '.bak')
                print(f'[TICKET] Bozuk JSON backup alındı: {path}')
                return {}
            except Exception as e:
                print(f'[TICKET] Veri загрузитьme Ошибкаsı: {e}')
        return {}
    
    def _save_ai_data(self, guild_id: int, data: dict):
        """AI ticket verilerini сохранить"""
        os.makedirs('data', exist_ok=True)
        path = self._get_ai_data_path(guild_id)
        try:
            # Önce temp dosyaya yaz, sonra rename (atomic write)
            tmp = path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            import shutil
            shutil.move(tmp, path)
        except Exception as e:
            print(f'[TICKET] Veri сохранитьme Ошибкаsı: {e}')
    
    def _get_ticket_state(self, guild_id: int, channel_id: int) -> dict:
        """Ticket state'ini al"""
        data = self._load_ai_data(guild_id)
        return data.get(str(channel_id), {
            'user_id': None,
            'category': None,
            'history': [],
            'status': 'ai_handling',
            'ai_message_count': 0,
            'escalated_at': None,
            'staff_notified': False
        })
    
    def _save_ticket_state(self, guild_id: int, channel_id: int, state: dict):
        """Ticket state'ini сохранить"""
        data = self._load_ai_data(guild_id)
        data[str(channel_id)] = state
        self._save_ai_data(guild_id, data)
    
    def _delete_ticket_state(self, guild_id: int, channel_id: int):
        """Ticket state'ini удалить"""
        data = self._load_ai_data(guild_id)
        if str(channel_id) in data:
            del data[str(channel_id)]
            self._save_ai_data(guild_id, data)
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Ticket channellarindaki messagelari dinle ve AI cevap ver"""
        if message.author.bot:
            return
        if not message.channel.name.startswith("ticket-"):
            return
        if not AI_ENABLED:
            return

        guild_id = message.guild.id
        channel_id = message.channel.id
        state = self._get_ticket_state(guild_id, channel_id)

        # Staff message attiysa AI'yi остановить
        support_role = discord.utils.get(message.guild.roles, name=SUPPORT_ROLE_NAME)
        if support_role and support_role in message.author.roles:
            if state['status'] == 'ai_handling':
                state['status'] = 'staff_handling'
                self._save_ticket_state(guild_id, channel_id, state)
            if state['status'] in ('staff_handling', 'escalated') and message.content.strip():
                try:
                    from web.faq_manager import learn_from_staff
                    last_user_q = None
                    for msg in reversed(state.get('history', [])):
                        if msg.get('role') == 'user':
                            last_user_q = msg.get('content', '')
                            break
                    if last_user_q and len(last_user_q) > 10:
                        learn_from_staff(question=last_user_q, answer=message.content,
                                         guild_id=guild_id, staff_name=message.author.display_name)
                except Exception as e:
                    print(f"FAQ learn error: {e}")
            return

        if state['status'] == 'staff_handling':
            return
        if state['status'] == 'escalated':
            return
        if state['ai_message_count'] >= MAX_AI_MESSAGES:
            await self._escalate_ticket(message.channel, state, 'max_messages')
            return
        # Analiz devam ediyorsa yeni messageı действиеe
        if state.get('analyzing'):
            return

        # ── ŞİKAYET STATE MACHINE ────────────────────────────────────────────
        complaint = state.get('complaint', {})
        if complaint.get('active'):
            await self._handle_complaint_flow(message, state, guild_id, channel_id, complaint)
            return

        # ── EK KANIT SİSTEMİ ──────────────────────────────────────────────────
        if state.get('waiting_for_evidence'):
            content_lower = message.content.lower().strip()
            if content_lower in ('evet', 'e', 'yes', 'var'):
                state['waiting_for_evidence'] = False
                state['adding_evidence'] = True
                self._save_ticket_state(guild_id, channel_id, state)
                await message.channel.send(
                    "📎 **Ek kanıt addme modu активна!**\n\n"
                    "Lütfen ek kanıtlarını buraya отправить:\n"
                    "• Screenshot (resim olarak)\n"
                    "• Ek messagelar (kopyala-yapıştır)\n"
                    "• DM ekran görüntüleri\n\n"
                    "Bitirdiğinde **'tamam'** yaz."
                )
            elif content_lower in ('hayır', 'h', 'no', 'yok'):
                state['waiting_for_evidence'] = False
                state['complaint'] = {}
                self._save_ticket_state(guild_id, channel_id, state)
                await message.channel.send("Anlaşıldı. Başka bir konuda yardımcı olabilirim.")
            # else: badd, tekrar sor
            return  # ← her statusda dur, normal AI akışına geçme
        
        # Ek kanıt всегоa modu
        if state.get('adding_evidence'):
            content_lower = message.content.lower().strip()
            if content_lower == 'tamam':
                state['adding_evidence'] = False
                complaint = state.get('complaint', {})
                self._save_ticket_state(guild_id, channel_id, state)
                if not complaint:
                    await message.channel.send("❌ Şikayet infosi bulunamadı.")
                    return
                await message.channel.send("✅ Ek kanıtlar alındı. Новыйden analiz yapılıyor...")
                await self._analyze_complaint(message.channel, state, guild_id, channel_id, complaint)
            else:
                if 'additional_evidence' not in state:
                    state['additional_evidence'] = []
                evidence_text = message.content
                if message.attachments:
                    evidence_text += f"\n[Ek: {len(message.attachments)} dosya]"
                state['additional_evidence'].append(evidence_text)
                complaint = state.get('complaint', {})
                if complaint and 'messages' in complaint:
                    complaint['messages'].append(f"[EK KANIT]: {evidence_text[:300]}")
                    state['complaint'] = complaint
                self._save_ticket_state(guild_id, channel_id, state)
                await message.add_reaction("✅")
            return  # ← her statusda dur, normal AI akışına geçme

        # ── İTİRAZ SİSTEMİ ────────────────────────────────────────────────────
        itiraz_keywords = ['itiraz', 'itiraz ediyorum', 'haksızlık', 'yanlış karar',
                           'adil değil', 'katılmıyorum', 'kabul etmiyorum']
        if any(kw in message.content.lower() for kw in itiraz_keywords):
            # Последний cezayı kontrole et
            user_penalties = self._get_penalty_history(guild_id, message.author.id, days=1)
            if user_penalties:
                last_penalty = user_penalties[-1]
                
                # İtiraz hakkı var mı?
                if state.get('appeal_used'):
                    await message.channel.send(
                        "⚠️ İtiraz hakkını zaten использовано. Daha fazla itiraz edemezsin.\n"
                        "Правоlilere iletiyorum."
                    )
                    await self._escalate_ticket(message.channel, state, 'appeal_rejected')
                    return
                
                state['appeal_used'] = True
                state['appeal_reason'] = message.content
                self._save_ticket_state(guild_id, channel_id, state)
                
                await message.channel.send(
                    f"📝 **İtirazın alındı!**\n\n"
                    f"Последний ceza: **{last_penalty['reason']}** ({last_penalty['duration']} minutes)\n"
                    f"İtiraz sebebin: {message.content[:200]}\n\n"
                    "⏳ İtirazın AI tarafından yeniden değerlendiriliyor..."
                )
                
                # İtirazı AI'ya отправить
                await self._handle_appeal(message.channel, state, guild_id, channel_id, last_penalty)
                return

        # Şikayet tetikleyici kelimeler — sadece ticket açma amacıyla yazılmışsa tetikle
        # NOT: Şikayet butonu zaten direkt akışı запуститьıyor, keyword tetikleyici sadece yedek
        sikayet_keywords = ['sikayet', 'şikayet', 'kufur', 'küfür', 'hakaret',
                            'tehdit', 'taciz', 'bully', 'zorba', 'rahatsiz', 'rahatsız']
        # "nasıl", "nedir", "ne" gibi soru kelimeleri varsa şikayet akışını запуститьma
        soru_kelimeleri = ['nasıl', 'naудалить', 'что такое', 'ne', 'neden', 'nasıl çalışıyor',
                           'naудалить calisiyor', 'hakkında', 'hakkinda', 'anlat', 'açıkla', 'acikla']
        icerik = message.content.lower()
        is_soru = any(kw in icerik for kw in soru_kelimeleri)
        # Kategori zaten выбратьildiyse keyword tetikleyiciyi atla
        kategori_secildi = state.get('category') is not None
        if any(kw in icerik for kw in sikayet_keywords) and not is_soru and not kategori_secildi:
            state['complaint'] = {
                'active': True,
                'step': 'ask_description',
                'type': None,
                'accused_id': None,
                'channel_id': None,
                'messages': [],
                'description': None,
            }
            state['ai_message_count'] += 1
            self._save_ticket_state(guild_id, channel_id, state)
            await message.channel.send("Ne yaşandığını kısaca anlat:")
            return

        # ── YETKİLİ TALEBİ ───────────────────────────────────────────────────
        right_btn_keywords = ['right_btnlerle konuş', 'right_btn çağır', 'right_btn gelsin',
                            'right_btn etiketle', 'right_btnye bağla', 'right_btnlerle iletişim',
                            'right_btnlerle konuşmak', 'right_btn istiyorum', 'admin çağır',
                            'mod çağır', 'модератор çağır']
        if any(kw in message.content.lower() for kw in right_btn_keywords):
            support_role = discord.utils.get(message.guild.roles, name=SUPPORT_ROLE_NAME)
            mention = support_role.mention if support_role else '@Destek'
            await message.channel.send(
                f'{mention} — {message.author.mention} seninle konuşmak istiyor.'
            )
            state['status'] = 'staff_handling'
            self._save_ticket_state(guild_id, channel_id, state)
            return

        # ── NORMAL AI AKIŞI ──────────────────────────────────────────────────
        async with message.channel.typing():
            try:
                from web.ai_helper import ai_ticket_response, parse_ai_actions

                def find_channel(guild, *keywords):
                    for kw in keywords:
                        ch = discord.utils.find(lambda c: kw in c.name.lower(), guild.text_channels)
                        if ch:
                            return ch.mention
                    return None

                guild_context = {
                    'guild_name': message.guild.name,
                    'member_count': message.guild.member_count,
                    'user_name': message.author.display_name,
                    'channel_name': message.channel.name,
                    'has_image': len(message.attachments) > 0,
                    'guild_id': message.guild.id,
                    'channel_id': message.channel.id,
                    'user_roles': [r.name for r in message.author.roles if r.name != '@everyone'],
                    'channels': {
                        'kayit': find_channel(message.guild, 'регистрация', 'kayit', 'register', 'doğrulama', 'dogrulama', 'verification'),
                        'kurallar': find_channel(message.guild, 'kural', 'rules'),
                        'announcelar': find_channel(message.guild, 'announce', 'announce'),
                        'ticket': find_channel(message.guild, 'ticket', 'destek', 'support'),
                        'roleler': find_channel(message.guild, 'role', 'role'),
                        'genel': find_channel(message.guild, 'genel', 'general', 'sohbet'),
                        'panel': find_channel(message.guild, 'panel', 'link', 'web'),
                    },
                    'panel_url': os.getenv('PANEL_URL', ''),
                    'all_channels': [c.name for c in message.guild.text_channels],
                    'channel_mentions': {c.name: c.mention for c in message.guild.text_channels},
                }

                # Пользователя geçmiş ticket'larını add
                try:
                    all_tickets = self._load_ai_data(guild_id)
                    past_tickets = []
                    user_id_str = str(state.get('user_id', ''))
                    for ch_id, t in all_tickets.items():
                        if str(ch_id) == str(channel_id):
                            continue  # Mevcut ticket'ı atla
                        if str(t.get('user_id', '')) == user_id_str and t.get('history'):
                            # Последний ticket'tan özet al
                            last_msgs = [h['content'] for h in t['history'][-3:] if h.get('role') == 'user']
                            if last_msgs:
                                past_tickets.append(f"Предыдущий ticket: {' | '.join(last_msgs[:2])}")
                    if past_tickets:
                        guild_context['past_tickets'] = past_tickets[-3:]  # Последний 3 ticket
                except:
                    pass

                full_message = message.content
                response, should_escalate, escalation_category, updated_history = ai_ticket_response(
                    full_message, state['history'], guild_context
                )
                actions = parse_ai_actions(response)

                if actions['jail']:
                    await self._apply_jail(message.channel, actions['jail']['user_id'],
                                           actions['jail']['duration'], actions['jail']['reason'],
                                           message.author)

                state['history'] = updated_history
                state['ai_message_count'] += 1

                if should_escalate or actions['escalate']:
                    state['category'] = escalation_category
                    await self._escalate_ticket(message.channel, state, escalation_category)
                    self._save_ticket_state(guild_id, channel_id, state)
                    return

                clean_response = response
                for tag in ['[JAIL]', '[CHECK_HISTORY]', '[ANALYZE_IMAGE]', '[ESCALATE]',
                            'ACTION:JAIL:', 'ACTION:CHECK:', 'ACTION:ESCALATE']:
                    if tag in clean_response:
                        clean_response = clean_response.split(tag)[0].strip()

                if clean_response:
                    await message.channel.send(clean_response)
                self._save_ticket_state(guild_id, channel_id, state)

            except Exception as e:
                print(f"AI Moderator error: {e}")
                import traceback
                traceback.print_exc()
                await self._escalate_ticket(message.channel, state, 'ai_error')
                self._save_ticket_state(guild_id, channel_id, state)

    async def _handle_appeal(self, channel, state, guild_id, channel_id, penalty):
        """İtirazı AI ile değerlendir"""
        from web.ai_helper import _call_text
        
        appeal_reason = state.get('appeal_reason', '')
        
        prompt = f"""Bir user AI moderasyon kararına itiraz ediyor.

=== CEZA BİLGİSİ ===
Наказание: {penalty['reason']}
Süre: {penalty['duration']} minutes
Дата: {penalty['date']}

=== İTİRAZ ===
{appeal_reason}

=== GÖREVİN ===
İtirazı değerlendir. Пользователь haklı mı?

KONTROL ET:
1. İtiraz geçerli bir причина içeriyor mu?
2. Наказание haksız mıydı?
3. Yanlış anlama var mıydı?

YANIT FORMATI:
[Değerlendirme]: (itirazın geçerliliği — 2-3 cümle)
[Karar]: KABUL veya RED veya BELIRSIZ"""

        async with channel.typing():
            verdict = _call_text([
                {'role': 'system', 'content': 'Sen bir moderasyon uzmanısın. İtirazları adil değerlendir.'},
                {'role': 'user', 'content': prompt}
            ], max_tokens=300)
        
        print(f"[APPEAL] verdict: {verdict!r}")
        
        verdict_upper = verdict.strip().upper()
        
        if 'KABUL' in verdict_upper:
            await channel.send(
                "✅ **İtirazın kabul edildi!**\n\n"
                "AI kararı yeniden değerlendirildi ve haksız olduğu tespit edildi.\n"
                "Наказаниеnı убратьmak için right_btnlere iletiyorum."
            )
            await self._escalate_ticket(channel, state, 'appeal_accepted')
        elif 'RED' in verdict_upper:
            await channel.send(
                "❌ **İtirazın reddedildi.**\n\n"
                "AI kararı yeniden incelendi ve doğru olduğu tespit edildi.\n"
                "Наказание geçerli kalıyor."
            )
        else:  # BELIRSIZ
            await channel.send(
                "🤔 **İtirazın belirsiz.**\n\n"
                "Bu statusu net değerlendiremiyorum, right_btnlere iletiyorum."
            )
            await self._escalate_ticket(channel, state, 'appeal_unclear')
        
        self._save_ticket_state(guild_id, channel_id, state)
    
    async def _handle_complaint_flow(self, message, state, guild_id, channel_id, complaint):
        """Şikayet akışını adım adım yönet"""
        content = message.content.strip()
        step = complaint.get('step')

        if step == 'ask_description':
            complaint['description'] = content
            complaint['step'] = 'ask_type'
            state['ai_message_count'] += 1
            self._save_ticket_state(guild_id, channel_id, state)
            await message.channel.send(
                "Şikayetini aldım. Ne tür bir sorun yaşadın?\n"
                "**1** - Küfür/Hakaret\n**2** - Tehdit\n**3** - Zorbalık/Dalga geçme\n**4** - Другое"
            )
            return

        if step == 'ask_type':
            type_map = {'1': 'kufur', '2': 'tehdit', '3': 'zorbalik', '4': 'diger'}
            complaint['type'] = type_map.get(content, 'diger')
            complaint['step'] = 'ask_accused'
            state['ai_message_count'] += 1

            # "Другое" выбратьilince direkt escalate et
            if complaint['type'] == 'diger':
                state['complaint'] = {}
                self._save_ticket_state(guild_id, channel_id, state)
                await message.channel.send("Статусu right_btnlere iletiyorum, en kısa sürede ilgilenecaddr.")
                await self._escalate_ticket(message.channel, state, 'diger')
                return

            self._save_ticket_state(guild_id, channel_id, state)
            await message.channel.send("Şikayet ettiğin kişinin Discord ID'sini yaz:")
            return

        if step == 'ask_accused':
            accused_id = content.strip()
            # ID doğrulama — mention, sayısal ID veya имя kabul et
            import re as _re
            mention_match = _re.search(r'<@!?(\d+)>', accused_id)
            if mention_match:
                accused_id = mention_match.group(1)
            elif not accused_id.isdigit():
                # Имяle ara
                found = discord.utils.find(
                    lambda m: m.display_name.lower() == accused_id.lower() or m.name.lower() == accused_id.lower(),
                    message.guild.members
                )
                if found:
                    accused_id = str(found.id)
                else:
                    await message.channel.send(
                        "❌ Пользователь bulunamadı. Lütfen Discord ID'si (17-19 haneli sayı) veya @mention gir:"
                    )
                    return
            complaint['accused_id'] = accused_id
            complaint['step'] = 'ask_channel'
            state['ai_message_count'] += 1
            self._save_ticket_state(guild_id, channel_id, state)
            await message.channel.send(
                "Bu olay hangi channelda gerçaddşti? Канал ID'sini yaz.\n"
                "*(Канал ID'sini bulmak için: channelı sağ tıkla → ID Kopyala)*"
            )
            return

        if step == 'ask_channel':
            complaint['channel_id'] = content.strip()
            complaint['step'] = 'ask_messages'
            state['ai_message_count'] += 1
            self._save_ticket_state(guild_id, channel_id, state)

            # Канал ID sayısalsa messageları otomatik tara
            if content.strip().isdigit():
                await message.channel.send("⏳ Сообщениеlar taranıyor, lütfen badd...")
                try:
                    target_ch = message.guild.get_channel(int(content.strip()))
                    if target_ch:
                        accused_id_str = complaint.get('accused_id', '')
                        accused_id_int = int(accused_id_str) if accused_id_str.isdigit() else None
                        complainant_id_int = state.get('user_id')

                        # Şikayet edenin adını найти
                        complainant_member = message.guild.get_member(complainant_id_int) if complainant_id_int else None
                        complainant_name = complainant_member.display_name if complainant_member else str(complainant_id_int)

                        # Şikayet edilenin adını найти
                        accused_member = message.guild.get_member(accused_id_int) if accused_id_int else None
                        accused_name = accused_member.display_name if accused_member else str(accused_id_int)

                        msgs = []
                        all_msgs_raw = []
                        # Последний 1000 messageı tara
                        async for msg in target_ch.history(limit=1000, oldest_first=False):
                            if msg.author.bot:
                                continue
                            all_msgs_raw.append(msg)

                        # En eskiden en yeniye sırala
                        all_msgs_raw.reverse()

                        # Her iki tarafın messagelarını topla
                        accused_msgs_set = set()
                        complainant_msgs_set = set()

                        for i, msg in enumerate(all_msgs_raw):
                            is_accused = accused_id_int and msg.author.id == accused_id_int
                            is_complainant = complainant_id_int and msg.author.id == complainant_id_int
                            if not (is_accused or is_complainant):
                                continue

                            # Yakın pencerede karşı taraf var mı?
                            window_start = max(0, i - 15)
                            window_end = min(len(all_msgs_raw), i + 16)
                            other_id = complainant_id_int if is_accused else accused_id_int
                            near_other = any(
                                all_msgs_raw[j].author.id == other_id
                                for j in range(window_start, window_end) if j != i
                            )

                            # Direkt mention/reply kontroleü
                            is_mention = other_id and any(m.id == other_id for m in msg.mentions)
                            is_reply = False
                            if msg.reference and msg.reference.resolved:
                                ref = msg.reference.resolved
                                if hasattr(ref, 'author') and other_id:
                                    is_reply = ref.author.id == other_id

                            if not (is_mention or is_reply or near_other):
                                continue

                            tag = '🎯 DOĞRUDAN' if (is_mention or is_reply) else '📍 BAĞLAMLI'
                            label = 'ŞİKAYET EDİLEN' if is_accused else 'ŞİKAYET EDEN'
                            line = (
                                f"[{msg.created_at.strftime('%d.%m %H:%M')}] "
                                f"[{label}: {msg.author.display_name}] {tag}: "
                                f"{msg.content[:300]}"
                            )
                            if is_accused:
                                accused_msgs_set.add(line)
                            else:
                                complainant_msgs_set.add(line)

                        # Her iki tarafın messagelarını birleştir
                        msgs = sorted(accused_msgs_set | complainant_msgs_set)

                        print(f"[TICKET] Tarama: {len(accused_msgs_set)} şikayet edilen, "
                              f"{len(complainant_msgs_set)} şikayet eden messageı bulundu")

                        # Удалитьinmiş messageları cache'den çek — her iki taraf için
                        deleted_msgs = []
                        try:
                            from cogs.logs import _msg_cache as _lc
                            for msg_id, cached_msg in list(_lc.items()):
                                if cached_msg.get('channel_id') != int(content.strip()):
                                    continue
                                author_id = cached_msg.get('author_id')
                                # Sadece iki tarafın messagelarını al
                                if author_id not in (accused_id_int, complainant_id_int):
                                    continue
                                # Hâlâ channelda var mı?
                                still_exists = any(m.id == msg_id for m in all_msgs_raw)
                                if still_exists:
                                    continue
                                ts = cached_msg.get('timestamp', '')[:16].replace('T', ' ')
                                label = 'ŞİKAYET EDİLEN' if author_id == accused_id_int else 'ŞİKAYET EDEN'
                                deleted_msgs.append(
                                    f"[{ts}] [{label}: {cached_msg.get('author_name','?')}] 🗑️ SİLİNMİŞ MESAJ: "
                                    f"{cached_msg.get('content', '[İçerik yok]')[:300]}"
                                )
                        except Exception as _de:
                            print(f'[TICKET] Cache deleted msgs Ошибкаsı: {_de}')

                        if deleted_msgs:
                            msgs.extend(deleted_msgs)
                            await message.channel.send(
                                f"⚠️ **{len(deleted_msgs)} удалитьinmiş message** tespit edildi (içerik görüntülenemiyor)."
                            )

                        if msgs:
                            complaint['messages'] = msgs
                            complaint['messages_verified'] = True
                            complaint['step'] = 'analyze'
                            complaint['accused_name'] = accused_name
                            complaint['complainant_name'] = complainant_name
                            self._save_ticket_state(guild_id, channel_id, state)
                            await message.channel.send(
                                f"✅ **{len(msgs)} ilgili message bulundu.** Analiz yapılıyor..."
                            )
                            await self._analyze_complaint(message.channel, state, guild_id, channel_id, complaint)
                            return
                        else:
                            await message.channel.send(
                                f"❌ **{target_ch.mention}** channelında **{accused_name}**'in "
                                f"**{complainant_name}**'e yönelik messageı bulunamadı.\n\n"
                                "O kişinin sana yazdığı messageları buraya kopyalayıp yapıştır:"
                            )
                            complaint['messages_verified'] = False
                            complaint['step'] = 'ask_messages'
                            self._save_ticket_state(guild_id, channel_id, state)
                            return
                    else:
                        await message.channel.send(
                            "❌ Канал bulunamadı. O kişinin sana yazdığı messageları buraya kopyalayıp yapıştır:"
                        )
                        complaint['step'] = 'ask_messages'
                        self._save_ticket_state(guild_id, channel_id, state)
                        return
                except Exception as e:
                    print(f"[TICKET] Channel scan error: {e}")
                    await message.channel.send(
                        "⚠️ Канал taranırken Ошибка oluştu. Сообщениеları manuel olarak kopyalayıp yapıştır:"
                    )
                    complaint['step'] = 'ask_messages'
                    self._save_ticket_state(guild_id, channel_id, state)
                    return

            await message.channel.send(
                "O kişinin sana yazdığı messageları buraya kopyalayıp yapıştır:"
            )
            return

        if step == 'ask_messages':
            complaint['messages'] = [content]
            complaint['messages_verified'] = False
            complaint['step'] = 'analyze'
            # Имяler yoksa şimdi add
            if 'complainant_name' not in complaint:
                cm = message.guild.get_member(state.get('user_id'))
                complaint['complainant_name'] = cm.display_name if cm else str(state.get('user_id', '?'))
            if 'accused_name' not in complaint:
                accused_id_str = complaint.get('accused_id', '')
                am = message.guild.get_member(int(accused_id_str)) if accused_id_str.isdigit() else None
                complaint['accused_name'] = am.display_name if am else accused_id_str
            self._save_ticket_state(guild_id, channel_id, state)
            await self._analyze_complaint(message.channel, state, guild_id, channel_id, complaint)
            return

        if step == 'confirm_messages':
            if content.lower() in ('evet', 'e', 'yes'):
                complaint['step'] = 'analyze'
                if 'complainant_name' not in complaint:
                    cm = message.guild.get_member(state.get('user_id'))
                    complaint['complainant_name'] = cm.display_name if cm else str(state.get('user_id', '?'))
                if 'accused_name' not in complaint:
                    accused_id_str = complaint.get('accused_id', '')
                    am = message.guild.get_member(int(accused_id_str)) if accused_id_str.isdigit() else None
                    complaint['accused_name'] = am.display_name if am else accused_id_str
                self._save_ticket_state(guild_id, channel_id, state)
                await self._analyze_complaint(message.channel, state, guild_id, channel_id, complaint)
            else:
                complaint['messages'] = []
                complaint['messages_verified'] = False
                complaint['step'] = 'ask_messages'
                self._save_ticket_state(guild_id, channel_id, state)
                await message.channel.send("O kişinin sana yazdığı messageları buraya kopyalayıp yapıştır:")
            return

    async def _analyze_complaint(self, channel, state, guild_id, channel_id, complaint):
        """Toplanan bilgileri AI'ya analiz ettir ve karar ver"""
        from web.ai_helper import _call_text

        # ── TEKRAR CEZA ÖNLEME (global — tüm ticket'larda) ──────────────────
        accused_id = complaint.get('accused_id', 'bilinmiyor')
        penalized_key = f"penalized_{accused_id}"

        # Global ceza kaydını kontrole et
        _penalty_file = 'data/ticket_penalties.json'
        _penalties = {}
        if os.path.exists(_penalty_file):
            try:
                with open(_penalty_file, 'r', encoding='utf-8') as _f:
                    _penalties = json.load(_f)
            except: pass

        guild_id_str = str(guild_id)
        user_penalties = _penalties.get(guild_id_str, {}).get(str(accused_id), [])
        # Новый format liste, eski format dict — her ikisini de destadd
        if isinstance(user_penalties, list) and len(user_penalties) > 0:
            prev = user_penalties[-1]
            prev_date = prev.get('date', '?')[:10]
            await channel.send(
                f"⚠️ **{prev.get('name', accused_id)}** bu serverda daha önce ticket sistemi üzerinden "
                f"ceza almış ({prev_date}, причина: {prev.get('reason', '?')}).\n"
                f"Tekrar ceza verilemez. Правоlilere iletiyorum."
            )
            state['complaint'] = {}
            state['analyzing'] = False
            await self._escalate_ticket(channel, state, 'itiraz')
            self._save_ticket_state(guild_id, channel_id, state)
            return

        # Analiz başladı — tekrar çağrılmasını önle
        if state.get('analyzing'):
            return
        state['analyzing'] = True
        self._save_ticket_state(guild_id, channel_id, state)
        complaint_type = complaint.get('type', 'diger')
        messages_raw = complaint.get('messages', [])
        messages_text = '\n'.join(messages_raw)

        type_labels = {
            'kufur': 'Küfür/Hakaret',
            'tehdit': 'Tehdit',
            'zorbalik': 'Zorbalık/Dalga geçme',
            'diger': 'Другое'
        }

        messages_verified = complaint.get('messages_verified', False)

        # Ticket sahibinin adını найти
        ticket_owner_member = channel.guild.get_member(state.get('user_id'))
        complainant_name = complaint.get('complainant_name') or (ticket_owner_member.display_name if ticket_owner_member else 'şikayet eden')
        complainant_id = state.get('user_id', '')

        # Şikayet edilen kişinin adını найти
        accused_name = complaint.get('accused_name') or accused_id
        if not complaint.get('accused_name') and str(accused_id).isdigit():
            accused_member = channel.guild.get_member(int(accused_id))
            if accused_member:
                accused_name = f"{accused_member.display_name} (ID: {accused_id})"

        prompt = f"""Bir Discord serversunda şikayet analizi yapıyorsun.

=== TARAFLAR ===
Şikayet EDEN: {complainant_name} (ID: {complainant_id})
Şikayet EDİLEN: {accused_name}
Şikayet türü: {type_labels.get(complaint_type, 'Другое')}
Пользователя anlattığı olay: {complaint.get('description', 'не указана')}
Сообщение kaynağı: {'✅ Каналdan otomatik tarandı (güvenilir)' if messages_verified else '⚠️ Пользователь kopyaladı (doğrulanamadı)'}

=== MESAJLAR (vakit sırasıyla, удалитьinen messagelar dahil) ===
NOT: [ŞİKAYET EDİLEN: X] = şikayet edilen kişinin messageı, [ŞİKAYET EDEN: X] = şikayetçinin messageı
NOT: 🗑️ SİLİNMİŞ MESAJ = Bu message sonradan удалено ama içeriği сохранено
{messages_text if messages_text else 'Сообщение bulunamadı'}

=== ANALİZ GÖREVİN ===
HER İKİ TARAFI DA İNCELE. Sadece şikayet edileni değil, şikayet edeni de analiz et.

KONTROL ET:
1. Сообщениеların ZAMAN DAMGALARINI incele — olayların sırası mantıklı mı?
2. SİLİNEN MESAJLARI DİKKATE AL — önemli kanıtlar удалитьinmiş olabilir
3. ŞİKAYET EDİLEN kişi kural ihlali yaptı mı? (küfür/hakaret/tehdit)
4. ŞİKAYET EDEN kişi de kural ihlali yaptı mı? (karşılıklı küfür)
5. Bağlamı incele — karşılıklı tartışma mı, tek taraflı saldırı mı?

KRİTİK KURALLAR:
- **HER İKİ TARAF DA küfür/hakaret ettiyse → KESİNLİKLE KARŞILIKLI_IHLAL** (ikisine de ceza)
- Sadece şikayet edilen küfür ettiyse → IHLAL_VAR (sadece ona ceza)
- Sadece şikayet eden küfür ettiyse → SAHTE_SIKAYET (şikayetçiye ceza)
- Genel sohbette geçen küfür (örn: "amk la") → İHLAL DEĞİL
- Сообщение yoksa veya bağlam yetersizse → BELIRSIZ
- Сообщениеlar doğrulanmamışsa (user kopyaladı) → BELIRSIZ

ÖNEMLİ: 
- Удалитьinmiş messagelar (🗑️ işaretli) özellikle önemli — genelde suçlu messageları удалитьer
- [ŞİKAYET EDEN] etiketli messagelarda da küfür varsa → KARŞILIKLI_IHLAL
- İki taraf da birbirine saldırdıysa → KARŞILIKLI_IHLAL (her ikisine de ceza)

YANIT FORMATI (kesinlikle bu formatta yaz):
[Analiz]: (her iki tarafın davranışını analiz et, удалитьinen messageları belirt — 3-4 cümle)
[Şikayet Edilen Статус]: (IHLAL_VAR / IHLAL_YOK)
[Şikayet Eden Статус]: (IHLAL_VAR / IHLAL_YOK)
[Karar]: IHLAL_VAR veya KARŞILIKLI_IHLAL veya SAHTE_SIKAYET veya IHLAL_YOK veya BELIRSIZ"""

        async with channel.typing():
            verdict = _call_text([
                {'role': 'system', 'content': (
                    'Sen bir Discord moderasyon uzmanısın. '
                    'Сообщениеları dikkatle analiz et, vakit damgalarına ve bağlama bak. '
                    'Türkçe yanıt ver. Kesinlikle verilen formatta yanıt ver.'
                )},
                {'role': 'user', 'content': prompt}
            ], max_tokens=500)

        print(f"[COMPLAINT] verified={messages_verified}, message_sayisi={len(messages_raw)}")
        print(f"[COMPLAINT] AI verdict: {verdict!r}")

        # AI güven skorunu hesapla
        confidence = self._get_ai_confidence(verdict)
        print(f"[COMPLAINT] AI confidence: {confidence}%")

        # Düşük güven → otomatik escalate (eşiği 40'a düşürdük, çok agresif escalate ediyordu)
        if confidence < 40:
            await channel.send(
                f"🤔 **AI Güven Оценкаu: %{confidence}** (Düşük)\n"
                "Bu statusu net bir şekilde değerlendiremiyorum, right_btnlere iletiyorum."
            )
            state['complaint'] = {}
            state['analyzing'] = False
            await self._escalate_ticket(channel, state, 'low_confidence')
            self._save_ticket_state(guild_id, channel_id, state)
            return

        # Analizi userya göster
        analiz_text = ''
        if '[Analiz]:' in verdict:
            analiz_text = verdict.split('[Analiz]:')[1].split('[Karar]:')[0].strip()
            if '[Şikayet Edilen Статус]:' in analiz_text:
                analiz_text = analiz_text.split('[Şikayet Edilen Статус]:')[0].strip()
            if analiz_text:
                await channel.send(
                    f"🔍 **AI Analizi** (Güven: %{confidence}):\n{analiz_text}"
                )

        verdict_upper = verdict.strip().upper()

        # KARŞILIKLI İHLAL — her iki tarafa da ceza
        if 'KARŞILIKLI_IHLAL' in verdict_upper or 'KARSILIKLI_IHLAL' in verdict_upper:
            await channel.send(
                "⚖️ **Karşılıklı kural ihlali tespit edildi!**\n"
                "Her iki taraf da küfür/hakaret kullandığı için **ikisine de ceza** uygulanacak."
            )
            
            type_labels2 = {'kufur': 'Küfür/Hakaret', 'tehdit': 'Tehdit', 'zorbalik': 'Zorbalık', 'diger': 'Другое'}
            accused_id_int = int(accused_id) if str(accused_id).isdigit() else None
            complainant_id_int = int(complainant_id) if str(complainant_id).isdigit() else None
            
            # Her iki tarafa da ceza uygula
            base_duration = 60 if complaint_type == 'tehdit' else 30
            reason = 'karşılıklı küfür/hakaret'
            
            # Şikayet edilene ceza (gradation ile)
            if accused_id_int:
                target = channel.guild.get_member(accused_id_int)
                if target and target.id != channel.guild.me.id:
                    duration = self._calculate_penalty_duration(guild_id, accused_id_int, base_duration)
                    history_count = len(self._get_penalty_history(guild_id, accused_id_int))
                    try:
                        await target.timeout(discord.utils.utcnow() + datetime.timedelta(minutes=duration), reason=f'[AI Ticket] {reason}')
                        suffix = f"\n📊 Geçmiş ceza: {history_count} (süre artırıldı)" if history_count > 0 else " (ilk ihlal)"
                        await channel.send(f"✅ {target.mention} **{duration} minutes** mute aldı{suffix}")
                        self._record_penalty(guild_id, accused_id_int, accused_name, reason, duration)
                    except Exception as e:
                        await channel.send(f"⚠️ {target.mention} mute atılamadı: {e}")
                else:
                    await channel.send(f"⚠️ Şikayet edilen user serverda bulunamadı.")

            # Şikayet edene de ceza (gradation ile)
            if complainant_id_int:
                complainant_member = channel.guild.get_member(complainant_id_int)
                if complainant_member and complainant_member.id != channel.guild.me.id:
                    duration = self._calculate_penalty_duration(guild_id, complainant_id_int, base_duration)
                    history_count = len(self._get_penalty_history(guild_id, complainant_id_int))
                    try:
                        await complainant_member.timeout(discord.utils.utcnow() + datetime.timedelta(minutes=duration), reason=f'[AI Ticket] {reason}')
                        suffix = f"\n📊 Geçmiş ceza: {history_count} (süre artırıldı)" if history_count > 0 else " (ilk ihlal)"
                        await channel.send(f"✅ {complainant_member.mention} **{duration} minutes** mute aldı{suffix}")
                        self._record_penalty(guild_id, complainant_id_int, complainant_name, reason, duration)
                    except Exception as e:
                        await channel.send(f"⚠️ {complainant_member.mention} mute atılamadı: {e}")
            
            state['complaint'] = {}
            state['analyzing'] = False
            self._save_ticket_state(guild_id, channel_id, state)
            return

        # SAHTE ŞİKAYET — sadece şikayetçi kural ihlali yapmış
        if 'SAHTE_SIKAYET' in verdict_upper or 'SAHTE_ŞIKAYET' in verdict_upper:
            await channel.send(
                "⚠️ **Sahte şikayet tespit edildi!**\n"
                "Şikayet edilen kişi kural ihlali yapmamış, ancak **sen küfür/hakaret kullanmışsın**.\n"
                "Bu statusda **sana ceza** uygulanacak."
            )
            
            complainant_id_int = int(complainant_id) if str(complainant_id).isdigit() else None
            if complainant_id_int:
                complainant_member = channel.guild.get_member(complainant_id_int)
                if complainant_member and complainant_member.id != channel.guild.me.id:
                    base_duration = 30
                    duration = self._calculate_penalty_duration(guild_id, complainant_id_int, base_duration)
                    history_count = len(self._get_penalty_history(guild_id, complainant_id_int))
                    reason = 'sahte şikayet + kural ihlali'
                    try:
                        await complainant_member.timeout(discord.utils.utcnow() + datetime.timedelta(minutes=duration), reason=f'[AI Ticket] {reason}')
                        suffix = f"\n📊 Geçmiş ceza: {history_count} (süre artırıldı)" if history_count > 0 else " (ilk ihlal)"
                        await channel.send(f"✅ {complainant_member.mention} **{duration} minutes** mute aldı{suffix}\nПричина: {reason}")
                        self._record_penalty(guild_id, complainant_id_int, complainant_name, reason, duration)
                    except Exception as e:
                        await channel.send(f"⚠️ Наказание uygulanamadı: {e}")
            
            state['complaint'] = {}
            state['analyzing'] = False
            self._save_ticket_state(guild_id, channel_id, state)
            return

        # Belirsiz → right_btnlere escalate et
        if 'BELIRSIZ' in verdict_upper or 'BELİRSİZ' in verdict_upper:
            await channel.send(
                "⚖️ **Статус belirsiz** — iki taraflı tartışma veya yetersiz kanıt.\n"
                "Bu statusu right_btnler değerlendirecek."
            )
            state['complaint'] = {}
            await self._escalate_ticket(channel, state, 'itiraz')
            self._save_ticket_state(guild_id, channel_id, state)
            return

        if 'IHLAL_VAR' in verdict_upper:
            type_labels2 = {'kufur': 'Küfür/Hakaret', 'tehdit': 'Tehdit', 'zorbalik': 'Zorbalık', 'diger': 'Другое'}

            accused_id_int = int(accused_id) if str(accused_id).isdigit() else None

            if not messages_verified:
                await channel.send(
                    "⚠️ Kural ihlali tespit edildi ancak messagelar doğrulanamadı.\n"
                    "Правоlilere iletiyorum, onlar karar verecek."
                )
                await self._escalate_ticket(channel, state, complaint_type)
            elif accused_id_int:
                if accused_id_int == channel.guild.me.id:
                    await channel.send("❌ Ботu jail atamam.")
                    state['complaint'] = {}
                    self._save_ticket_state(guild_id, channel_id, state)
                    return
                # Пользователь serverda var mı kontrole et
                target = channel.guild.get_member(accused_id_int)
                if not target:
                    try:
                        target = await channel.guild.fetch_member(accused_id_int)
                    except Exception:
                        target = None
                if not target:
                    await channel.send("⚠️ Kural ihlali tespit edildi ancak user bu serverda bulunamadı. Правоlilere iletiyorum.")
                    await self._escalate_ticket(channel, state, complaint_type)
                    state['complaint'] = {}
                    self._save_ticket_state(guild_id, channel_id, state)
                    return
                
                base_duration = 120 if complaint_type == 'tehdit' else 30
                duration = self._calculate_penalty_duration(guild_id, accused_id_int, base_duration)
                history_count = len(self._get_penalty_history(guild_id, accused_id_int))
                
                reason_map = {'kufur': 'hakaret', 'tehdit': 'tehdit', 'zorbalik': 'zorbalik', 'diger': 'kural ihlali'}
                reason = reason_map.get(complaint_type, 'kural ihlali')
                ticket_owner = channel.guild.get_member(state.get('user_id'))
                
                await self._apply_jail(channel, accused_id_int, duration, reason,
                                       ticket_owner or channel.guild.me)
                
                # Наказание infosi
                if history_count > 0:
                    await channel.send(
                        f"📊 **Geçmiş ceza:** {history_count} (ceza süresi {base_duration}dk → {duration}dk artırıldı)"
                    )
                else:
                    await channel.send(f"ℹ️ Первый ihlal, standart ceza uygulandı.")
                
                # Global ceza kaydı
                self._record_penalty(guild_id, accused_id_int, accused_name, reason, duration)
            else:
                await channel.send("⚠️ Пользователь ID'si geçersiz, right_btnler inceleyecek.")
                await self._escalate_ticket(channel, state, complaint_type)

        elif 'IHLAL_YOK' in verdict_upper:
            # Ek kanıt teklifi
            await channel.send(
                "🔍 İncelenen messagelarda açık bir kural ihlali tespit edemedim.\n\n"
                "**Ek kanıt addmek ister misin?** (evet/hayır)\n"
                "> Screenshot, ek messagelar veya başka kanıtlar varsa addyebilirsin."
            )
            # Ek kanıt baddme moduna geç
            state['waiting_for_evidence'] = True
            state['complaint'] = complaint  # Şikayeti sakla
            self._save_ticket_state(guild_id, channel_id, state)
            return

        else:  # BELIRSIZ
            await channel.send("🔄 Сообщениеlar yeterince net değil, right_btnlere iletiyorum.")
            await self._escalate_ticket(channel, state, complaint_type)

        # Şikayet akışını закрыть, analyzing flag'ini clear
        state['complaint'] = {}
        state['analyzing'] = False
        self._save_ticket_state(guild_id, channel_id, state)

    async def _escalate_ticket(self, channel: discord.TextChannel, state: dict, reason: str):
        """Ticket'i right_btnlere yonlendir"""
        if state['staff_notified']:
            return  # Zaten yonlendirilmis
        
        state['status'] = 'escalated'
        state['escalated_at'] = datetime.datetime.utcnow().isoformat()
        state['staff_notified'] = True
        
        # Yonlendirme messagei
        e = discord.Embed(
            title="🔄  Правоlilere Yönlendiriliyor",
            color=0xF39C12,
            timestamp=datetime.datetime.utcnow()
        )
        
        reason_text = {
            'sikayet': 'Şikayet konusu right_btnler tarafından değerlendirilmeli',
            'teknik': 'Teknik sorun right_btnler tarafından incelenmeli',
            'право': 'Право gerektiren действие',
            'agir_ihlal': 'Ağır ihlal tespit edildi, üst düzey inceleme gerekiyor',
            'itiraz': 'Пользователь AI kararına itiraz ediyor',
            'ban_talebi': 'Бан действиеi sadece right_btnler tarafından yapılabilir',
            'max_messages': 'Konuşma limiti aşıldı, right_btnler devralıyor',
            'ai_error': 'Система Ошибкаsı, right_btnler devralıyor',
            'diger': 'Bu konu right_btnler tarafından ele alınmalı'
        }
        
        e.description = (
            f"```ansi\n\u001b[1;33m🔄 YÖNLENDİRİLİYOR\u001b[0m\n```\n"
            f"{_divider()}\n\n"
            f"**Причина:** {reason_text.get(reason, 'Правоliler devralıyor')}\n\n"
            "Destek ekibimiz en kısa sürede seninle ilgilenecek. 💙\n"
            f"{_divider()}"
        )
        e.set_footer(text="Aether AI Moderator")
        
        await channel.send(embed=e)
        
        # Destek roleunu ping at
        support_role = discord.utils.get(channel.guild.roles, name=SUPPORT_ROLE_NAME)
        if support_role:
            await channel.send(
                f"🔔 {support_role.mention} — Новый destek talebi yönlendirildi!"
            )
        
        # State сохранить
        self._save_ticket_state(channel.guild.id, channel.id, state)
    
    async def _apply_jail(self, channel: discord.TextChannel, user_id: int, duration: int, reason: str, complainant: discord.Member):
        """AI moderator jail cezasi uygular"""
        try:
            guild = channel.guild
            target_user = guild.get_member(user_id)
            if not target_user:
                try:
                    target_user = await guild.fetch_member(user_id)
                except Exception:
                    target_user = None
            
            if not target_user:
                await channel.send("❌ Пользователь bu serverda bulunamadı.")
                return
            
            # Jail roleunu bul veya olustur
            jail_role = discord.utils.get(guild.roles, name="Jail")
            if not jail_role:
                # Jail roleu olustur
                jail_role = await guild.create_role(
                    name="Jail",
                    color=discord.Color.dark_gray(),
                    reason="AI Moderator jail role"
                )
                # Tum channellarda jail roleune izin verme
                for channel_obj in guild.channels:
                    try:
                        await channel_obj.set_permissions(jail_role, send_messages=False, speak=False)
                    except:
                        pass
            
            # Jail roleunu ver
            await target_user.add_roles(jail_role, reason=f"AI Moderator: {reason}")
            
            # Kullaniciya DM gonder
            try:
                dm_embed = discord.Embed(
                    title="⚠️  Jail Наказаниеsı Aldınız",
                    color=0xE74C3C,
                    timestamp=datetime.datetime.utcnow()
                )
                dm_embed.description = (
                    f"**Сервер:** {guild.name}\n"
                    f"**Süre:** {duration} minutes\n"
                    f"**Причина:** {reason}\n\n"
                    f"Наказание süresi sonunda jail roleünüz otomatik убратьılacaktır.\n"
                    f"İtiraz etmek isterseniz ticket channelında belirtiniz."
                )
                dm_embed.set_footer(text="Aether AI Moderator")
                await target_user.send(embed=dm_embed)
            except:
                pass
            
            # Каналa bildir
            jail_embed = discord.Embed(
                title="✅  Jail Наказаниеsı Uygulandı",
                color=0x2ECC71,
                timestamp=datetime.datetime.utcnow()
            )
            jail_embed.description = (
                f"```ansi\n\u001b[1;32m✅ CEZA UYGULAND\u001b[0m\n```\n"
                f"{_divider()}\n\n"
                f"**Пользователь:** {target_user.mention}\n"
                f"**Süre:** {duration} minutes\n"
                f"**Причина:** {reason}\n\n"
                f"Olayı çözmekte size right_btn ekibimiz yardımcı olacaktır.\n"
                f"İtiraz etmek isterseniz, bu channelı açık tutun.\n"
                f"{_divider()}"
            )
            jail_embed.set_footer(text="Aether AI Moderator")
            await channel.send(embed=jail_embed)
            
            # Jail'i otomatik kaldir (duration minutes sonra)
            await self._schedule_unjail(guild, target_user, jail_role, duration)
            
            # Mod log'a сохранить
            from cogs.logs import save_event
            save_event(
                guild.id,
                'moderation',
                'ai_jail',
                {
                    'target': str(target_user),
                    'target_id': target_user.id,
                    'duration': duration,
                    'reason': reason,
                    'complainant': str(complainant),
                    'complainant_id': complainant.id,
                    'timestamp': datetime.datetime.utcnow().isoformat()
                }
            )
            
        except Exception as e:
            await channel.send(f"❌ Jail cezası uygulanırken Ошибка oluştu: {str(e)}")
            print(f"Jail error: {e}")
    
    async def _schedule_unjail(self, guild: discord.Guild, user: discord.Member, jail_role: discord.Role, duration: int):
        """Jail cezasini belirli sure sonra kaldir"""
        import asyncio
        await asyncio.sleep(duration * 60)

        try:
            # Пользователь hâlâ serverda mı?
            fresh_member = guild.get_member(user.id)
            if not fresh_member:
                try:
                    fresh_member = await guild.fetch_member(user.id)
                except discord.NotFound:
                    print(f'[TICKET] Unjail: {user} serverdan ayrılmış, role убратьılamadı')
                    return
                except Exception as e:
                    print(f'[TICKET] Unjail fetch Ошибкаsı: {e}')
                    return

            # Jail roleü hâlâ var mı?
            fresh_role = guild.get_role(jail_role.id)
            if not fresh_role:
                print(f'[TICKET] Unjail: Jail roleü удалитьinmiş')
                return

            if fresh_role in fresh_member.roles:
                await fresh_member.remove_roles(fresh_role, reason="Jail süresi doldu (AI Moderator)")
                try:
                    dm_embed = discord.Embed(
                        title="✅  Jail Наказаниеnız Последнийa Erdi",
                        color=0x2ECC71,
                        timestamp=datetime.datetime.utcnow()
                    )
                    dm_embed.description = (
                        f"**Сервер:** {guild.name}\n\n"
                        f"Jail cezanız sona erdi. Artık normal şekilde serverya erişebilirsiniz.\n"
                        f"Lütfen server kurallarına uygun davranmaya devam edin."
                    )
                    dm_embed.set_footer(text="Aether AI Moderator")
                    await fresh_member.send(embed=dm_embed)
                except:
                    pass
        except Exception as e:
            print(f'[TICKET] Unjail Ошибкаsı: {e}')
    
    async def _check_message_history(self, channel: discord.TextChannel, guild: discord.Guild, user_id: int = None, target_channel_id: int = None) -> str:
        """Belirli kullanicinin messagelarini tara"""
        try:
            target_channel = channel
            if target_channel_id:
                tc = guild.get_channel(target_channel_id)
                if tc:
                    target_channel = tc

            messages = []
            async for msg in target_channel.history(limit=200, oldest_first=False):
                if msg.author.bot:
                    continue
                if user_id and msg.author.id != user_id:
                    continue
                messages.append({
                    'author': msg.author.display_name,
                    'author_id': msg.author.id,
                    'content': msg.content[:300],
                    'timestamp': msg.created_at.strftime('%H:%M'),
                    'edited': msg.edited_at is not None,
                })

            if not messages:
                return f"Bu channelda {'bu userya ait ' if user_id else ''}message bulunamadı."

            summary = f"#{target_channel.name} channelında bulunan messagelar ({len(messages)} adet):\n"
            for msg in messages[:20]:
                edited_tag = ' [EDİTLENMİŞ]' if msg['edited'] else ''
                summary += f"[{msg['timestamp']}] {msg['author']}: {msg['content']}{edited_tag}\n"

            return summary

        except Exception as e:
            return f"Сообщение geçmişi kontrole edilemedi: {str(e)}"

    @app_commands.command(name="ticket-panel", description="Ticket panelini отправитьir")
    @app_commands.checks.has_permissions(administrator=True)
    async def ticket_panel(self, interaction: discord.Interaction):
        if interaction.guild.id in TICKET_DISABLED_GUILDS:
            await interaction.response.send_message(
                '❌ Bu serverda ticket sistemi активна değil.', ephemeral=True
            )
            return

        # Каналda zaten bot tarafından отправитьilmiş bir ticket paneli var mı?
        async for msg in interaction.channel.history(limit=20):
            if (msg.author == interaction.guild.me and
                    msg.embeds and
                    msg.components and
                    any('ticket_open' in str(c) for c in msg.components)):
                await interaction.response.send_message(
                    "⚠️ Bu channelda zaten bir ticket paneli var. Önce eskisini удалить.",
                    ephemeral=True
                )
                return
        e = discord.Embed(
            title="🎫  DESTEK SİSTEMİ",
            color=0x5865F2,
            timestamp=datetime.datetime.utcnow()
        )
        e.description = (
            f"```ansi\n\u001b[1;34m✦ Aether DESTEK SİSTEMİ ✦\u001b[0m\n```\n"
            f"{_divider()}\n\n"
            "Серверmuzda bir sorunla mı karşılaştın?\n"
            "Bir şey mi sormak istiyorsun?\n\n"
            "**Нажмите кнопку нижеyarak** özel bir destek channelı создатьabilirsin.\n"
            "🤖 **AI Asistan** ilk olarak sana yardımcı olacak!\n"
            "Gerekirse ekibimiz devralacak. 💙\n\n"
            f"{_divider()}\n\n"
            "```yaml\n"
            "🤖 AI Destek    •    ⚡ Hızlı yanıt    •    🔒 Секретный channel\n"
            "```"
        )
        e.set_image(url=GIF_PANEL)
        e.set_footer(
            text=f"{interaction.guild.name} • AI Destek Sistemi",
            icon_url=interaction.guild.icon.url if interaction.guild.icon else None
        )
        await interaction.channel.send(embed=e, view=TicketView())
        await interaction.response.send_message("✅ Ticket paneli отправитьildi.", ephemeral=True)

    @app_commands.command(name="ticket-add", description="Tickete user addr")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def ticket_add(self, interaction: discord.Interaction, user: discord.Member):
        await interaction.channel.set_permissions(user, read_messages=True, send_messages=True)
        e = discord.Embed(
            description=f"✅ {user.mention} bu destek channelına addndi.",
            color=0x2ECC71
        )
        await interaction.response.send_message(embed=e)

    @app_commands.command(name="ticket-cikar", description="Ticketten user çıkarır")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def ticket_cikar(self, interaction: discord.Interaction, user: discord.Member):
        await interaction.channel.set_permissions(user, read_messages=False)
        e = discord.Embed(
            description=f"🚫 {user.mention} bu destek channelından çıkarıldı.",
            color=0xE74C3C
        )
        await interaction.response.send_message(embed=e)
    
    @app_commands.command(name="ticket-ai-stats", description="AI destek istatistiklerini gösterir")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_ai_stats(self, interaction: discord.Interaction):
        """AI ticket istatistiklerini goster"""
        data = self._load_ai_data(interaction.guild.id)
        
        if not data:
            await interaction.response.send_message("❌ Henüz AI destek verisi yok.", ephemeral=True)
            return
        
        total_tickets = len(data)
        ai_handling = sum(1 for t in data.values() if t['status'] == 'ai_handling')
        escalated = sum(1 for t in data.values() if t['status'] == 'escalated')
        staff_handling = sum(1 for t in data.values() if t['status'] == 'staff_handling')
        
        total_ai_messages = sum(t['ai_message_count'] for t in data.values())
        avg_messages = total_ai_messages / total_tickets if total_tickets > 0 else 0
        
        e = discord.Embed(
            title="🤖  AI Destek İstatistikleri",
            color=0x00D9FF,
            timestamp=datetime.datetime.utcnow()
        )
        e.description = (
            f"```ansi\n\u001b[1;36m📊 İSTATİSTİKLER\u001b[0m\n```\n"
            f"{_divider()}"
        )
        e.add_field(name="📋 Всего Ticket", value=f"```{total_tickets}```", inline=True)
        e.add_field(name="🤖 AI İşliyor", value=f"```{ai_handling}```", inline=True)
        e.add_field(name="🔄 Yönlendirildi", value=f"```{escalated}```", inline=True)
        e.add_field(name="👥 Staff İşliyor", value=f"```{staff_handling}```", inline=True)
        e.add_field(name="💬 Всего AI Сообщение", value=f"```{total_ai_messages}```", inline=True)
        e.add_field(name="📊 Ortalama Сообщение", value=f"```{avg_messages:.1f}```", inline=True)
        e.set_footer(text="Aether AI Destek")
        
        await interaction.response.send_message(embed=e)
    
    @app_commands.command(name="ticket-ai-toggle", description="AI destek sistemini aç/закрыть")
    @app_commands.checks.has_permissions(administrator=True)
    async def ticket_ai_toggle(self, interaction: discord.Interaction):
        """AI destek sistemini активна/неактивна yap"""
        global AI_ENABLED
        AI_ENABLED = not AI_ENABLED
        
        status = "✅ Активен" if AI_ENABLED else "❌ Неактивна"
        e = discord.Embed(
            title="🤖  AI Destek Sistemi",
            description=f"AI destek sistemi şu an: **{status}**",
            color=0x2ECC71 if AI_ENABLED else 0xE74C3C
        )
        await interaction.response.send_message(embed=e)
    
    @app_commands.command(name="ticket-force-escalate", description="Mevcut ticket'i hemen right_btnlere yönlendir")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def ticket_force_escalate(self, interaction: discord.Interaction):
        """Ticket'i manuel olarak yonlendir"""
        if not interaction.channel.name.startswith("ticket-"):
            await interaction.response.send_message("❌ Bu bir ticket channelı değil.", ephemeral=True)
            return
        
        state = self._get_ticket_state(interaction.guild.id, interaction.channel.id)
        
        if state['status'] == 'escalated':
            await interaction.response.send_message("⚠️ Bu ticket zaten yönlendirilmiş.", ephemeral=True)
            return
        
        await interaction.response.send_message("🔄 Ticket right_btnlere yönlendiriliyor...", ephemeral=True)
        await self._escalate_ticket(interaction.channel, state, 'manual')


async def setup(bot):
    await bot.add_cog(Ticket(bot), guilds=[discord.Object(id=1421244140359909513), discord.Object(id=1107038411895881788)])
