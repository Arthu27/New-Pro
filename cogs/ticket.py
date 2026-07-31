import discord
from discord.ext import commands
from discord import app_commands
import datetime
from datetime import timedelta
import io
import json
import os
from cogs.embed_utils import gif, now_ts, _divider

TICKET_CATEGORY_NAME = "Ticketlar"
SUPPORT_ROLE_NAME = "Поддержка"

GIF_TICKET_OPEN  = "https://media.tenor.com/3Ky6UNqMFpkAAAAC/talking-speak.gif"
GIF_TICKET_CLOSE = "https://media.tenor.com/x8v1oNUOmg4AAAAC/ban-hammer.gif"
GIF_PANEL        = "https://media.tenor.com/ZBDpMFBMFpkAAAAC/celebration-party.gif"

# AI Ticket Settings
AI_ENABLED = True  # AI поддержка система активен
MAX_AI_MESSAGES = 10

# Это сервер ticket система отключено
TICKET_DISABLED_GUILDS: set = set()


class TicketCategoryView(discord.ui.View):
    """Ticket при открытии kategori выбор кнопки"""
    def __init__(self, channel_id: int, guild_id: int):
        super().__init__(timeout=300)
        self.channel_id = channel_id
        self.guild_id = guild_id

    async def _set_category(self, interaction: discord.Interaction, category: str, label: str):
        cog = interaction.client.get_cog('Ticket')
        if cog:
            state = cog._get_ticket_state(self.guild_id, self.channel_id)
            state['category'] = category
            
            # В категории жалобы сразу запускать поток жалобы
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
                '🚨 **Выбрана категория: Жалоба.**\n\n'
                'Кратко опишите, что произошло:'
            ),
            'soru': (
                '❓ **Выбрана категория: Вопрос/Помощь.**\n\n'
                'Чем я могу помочь? Какую информацию вы хотите получить?\n'
                '> Панель, регистрация, команды, роли, экономика, уровни...'
            ),
            'teknik': (
                '🔧 **Выбрана категория: Техническая проблема.**\n\n'
                'Чем я могу помочь? С какой проблемой вы столкнулись?\n'
                '> Бот, музыка, команда не работает, текст ошибки...'
            ),
        }

        hint = category_hints.get(category, '💬 Чем я могу помочь?')
        e = discord.Embed(description=hint, color=0x00D9FF)
        await interaction.response.send_message(embed=e)
        # кнопки отключено bırak
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)

    @discord.ui.button(label='🚨  Жалоба', style=discord.ButtonStyle.danger, custom_id='ticket_cat_sikayet')
    async def btn_sikayet(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._set_category(interaction, 'sikayet', 'Жалоба')

    @discord.ui.button(label='❓  Вопрос / Помощь', style=discord.ButtonStyle.primary, custom_id='ticket_cat_soru')
    async def btn_soru(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._set_category(interaction, 'soru', 'Вопрос')

    @discord.ui.button(label='🔧  Teknik Вопросn', style=discord.ButtonStyle.secondary, custom_id='ticket_cat_teknik')
    async def btn_teknik(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._set_category(interaction, 'teknik', 'Teknik')


class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🎫  Создать тикет поддержки",
        style=discord.ButtonStyle.blurple,
        custom_id="ticket_open"
    )
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        
        # Это на сервере ticket отключено
        if guild.id in TICKET_DISABLED_GUILDS:
            await interaction.response.send_message(
                '❌ Это на сервере ticket система активен не.', ephemeral=True
            )
            return
        
        existing = discord.utils.get(guild.text_channels, name=f"ticket-{interaction.user.name.lower()}")
        if existing:
            await interaction.response.send_message(
                f"⚠️ У вас уже есть открытый тикет: {existing.mention}\nПожалуйста, сначала закройте его.",
                ephemeral=True
            )
            return
        
        # Пауза перед отправкой ответа (правило 3 секунды Discord)
        await interaction.response.send_message(
            "🎫 Канал тикета создан...",
            ephemeral=True
        )

        category = discord.utils.get(guild.categories, name=TICKET_CATEGORY_NAME)
        if not category:
            category = await guild.create_category(TICKET_CATEGORY_NAME)

        support_role = discord.utils.get(guild.roles, name=SUPPORT_ROLE_NAME)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(reимя_messages=False),
            interaction.user: discord.PermissionOverwrite(reимя_messages=True, send_messages=True),
        }
        if support_role:
            overwrites[support_role] = discord.PermissionOverwrite(reимя_messages=True, send_messages=True)

        channel = await guild.create_text_channel(
            f"ticket-{interaction.user.name.lower()}",
            category=category,
            overwrites=overwrites,
            topic=f"Ticket sahibi: {interaction.user.id}"
        )

        ts = int(datetime.datetime.utcnow().timestamp())

        # Канал içi добро пожаловать embed — kartocka stil
        e = discord.Embed(color=0x5865F2, timestamp=datetime.datetime.utcnow())
        e.description = (
            f"## Тикет открыт\n"
            f"### {channel.mention}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"**Категория:** Техническая проблема\n"
            f"**Пользователь:** {interaction.user.mention}\n"
            f"**Создан:** <t:{ts}:R>\n\n"
            f"Опишите вашу проблему ниже.\n"
            f"AI-ассистент поможет вам, при необходимости подключится модератор.\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        e.set_thumbnail(url=interaction.user.display_avatar.url)
        if guild.icon:
            e.set_footer(text=f"{guild.name} · Поддержка", icon_url=guild.icon.url)
        else:
            e.set_footer(text=f"{guild.name} · Поддержка")

        await channel.send(
            content=f"{interaction.user.mention}" + (f" | {support_role.mention}" if support_role else ""),
            embed=e,
            view=CloseTicketView()
        )
        
        # AI karalama сообщение gonder
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
                    name="Поддержка Aether AI",
                    icon_url=interaction.client.user.display_avatar.url
                )
                ai_embed.set_footer(text="Если я не смогу помочь — передам модератору.")
                await channel.send(
                    embed=ai_embed,
                    view=TicketCategoryView(channel.id, guild.id)
                )
            except Exception:
                pass

        # Пользователю DM
        try:
            dm_e = discord.Embed(color=0x5865F2, timestamp=datetime.datetime.utcnow())
            dm_e.description = (
                f"## Тикет создан\n"
                f"### Ваш запрос принят\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"**Сервер:** {guild.name}\n"
                f"**Канал:** {channel.mention}\n"
                f"**Создан:** <t:{ts}:R>\n\n"
                f"Опишите проблему как можно подробнее для быстрого решения.\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            dm_e.set_thumbnail(url=guild.icon.url if guild.icon else None)
            if guild.icon:
                dm_e.set_footer(text=f"{guild.name} · Поддержка", icon_url=guild.icon.url)
            else:
                dm_e.set_footer(text=f"{guild.name} · Поддержка")
            await interaction.user.send(embed=dm_e)
        except discord.Forbidden:
            pass

        # Followup сообщение gonder (response zaten gonderildi)
        await interaction.followup.send(
            f"✅ Канал тикета создан: {channel.mention}",
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
            await interaction.response.send_message("Это bir ticket канал не.", ephemeral=True)
            return

        # AI state'ini clear
        cog = interaction.client.get_cog('Ticket')
        if cog:
            cog._delete_ticket_state(interaction.guild.id, channel.id)

        messages = []
        async for msg in channel.history(limit=200, oldest_first=True):
            if not msg.author.bot:
                messages.append(f"[{msg.created_at.strftime('%d.%m.%Y %H:%M:%S')}] {msg.author.display_name}: {msg.content}")
        transcript = "\n".join(messages) if messages else "Сообщение не найдено."

        owner_id = None
        if channel.topic and "Ticket sahibi:" in channel.topic:
            try:
                owner_id = int(channel.topic.split("Ticket sahibi:")[-1].strip())
            except:
                pass

        ts = int(datetime.datetime.utcnow().timestamp())

        log_ch = discord.utils.get(interaction.guild.text_channels, name="ticket-log")
        if log_ch:
            log_e = discord.Embed(color=0xE74C3C, timestamp=datetime.datetime.utcnow())
            log_e.description = (
                f"## Ticket закрыт\n"
                f"### {channel.name}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"**Zakril:** {interaction.user.mention}\n"
                f"**Дата:** <t:{ts}:F>\n"
                f"**Сообщение:** {len(messages)}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            if interaction.guild.icon:
                log_e.set_footer(text=f"{interaction.guild.name} · Loglar", icon_url=interaction.guild.icon.url)
            else:
                log_e.set_footer(text=f"{interaction.guild.name} · Loglar")
            file = discord.File(fp=io.StringIO(transcript), filename=f"{channel.name}_transcript.txt")
            await log_ch.send(embed=log_e, file=file)

        if owner_id:
            try:
                owner = await interaction.guild.fetch_member(owner_id)
                dm_e = discord.Embed(color=0xE74C3C, timestamp=datetime.datetime.utcnow())
                dm_e.description = (
                    f"## Ticket закрыт\n"
                    f"### Sizin sorgu завершено\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"**Сервер:** {interaction.guild.name}\n"
                    f"**Zakril:** {interaction.user.display_name}\n"
                    f"**Закрыт:** <t:{ts}:R>\n"
                    f"**Сообщение:** {len(messages)}\n\n"
                    f"Если u vas vozniknet новый soru — sozdayte новый ticket.\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                )
                dm_e.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
                if interaction.guild.icon:
                    dm_e.set_footer(text=f"{interaction.guild.name} · Поддержка", icon_url=interaction.guild.icon.url)
                else:
                    dm_e.set_footer(text=f"{interaction.guild.name} · Поддержка")
                await owner.send(embed=dm_e)
            except:
                pass

        await interaction.response.send_message("🔒 Поддержка talebi закрыт, transcript сохранено...")
        await channel.delete()


class Ticket(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        bot.имяd_view(TicketView())
        bot.имяd_view(CloseTicketView())
    
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
                    _penalties = json.loимя(_f)
            
            # Новый формат: список как хранение (история наказаний)
            guild_str = str(guild_id)
            user_str = str(user_id)
            
            if guild_str not in _penalties:
                _penalties[guild_str] = {}
            if user_str not in _penalties[guild_str]:
                _penalties[guild_str][user_str] = []
            
            # Наказание kaydını имяd
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
            print(f'[TICKET] Наказание kaydı Ошибки: {_pe}')
    
    def _get_penalty_history(self, guild_id: int, user_id: int, days: int = 7) -> list:
        """В конец X день в наказание историю getir"""
        try:
            _penalty_file = 'data/ticket_penalties.json'
            if not os.path.exists(_penalty_file):
                return []
            
            with open(_penalty_file, 'r', encoding='utf-8') as _f:
                _penalties = json.loимя(_f)
            
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
            print(f'[TICKET] Penalty history Ошибки: {e}')
            return []
    
    def _calculate_penalty_duration(self, guild_id: int, user_id: int, base_duration: int) -> int:
        """История наказание по длительность hesapla (grимяation)"""
        history = self._get_penalty_history(guild_id, user_id, days=7)
        history_count = len(history)
        
        # Первое нарушение: base_duration
        # Второе: 2x
        # Третье: 4x
        # Четвёртое+: 8x (макс 24 часа)
        multiplier = 2 ** min(history_count, 3)
        calculated = base_duration * multiplier

        # Макс 1440 минут (24 часа)
        return min(calculated, 1440)

    def _get_ai_confidence(self, verdict: str) -> int:
        """Рассчитать уровень доверия к решению AI (0-100)"""
        confidence = 50  # Начальное значение

        verdict_lower = verdict.lower()

        # Признаки высокого доверия
        if 'открыт' in verdict_lower or 'явно' in verdict_lower or 'точно' in verdict_lower:
            confidence += 30
        if 'верно' in verdict_lower or 'прямо' in verdict_lower:
            confidence += 20
        if 'удалено' in verdict_lower or 'удален' in verdict_lower:
            confidence += 15

        # Признаки низкого доверия
        if 'неясно' in verdict_lower or 'контекст' in verdict_lower:
            confidence -= 30
        if 'недостаточно' in verdict_lower or 'отсутствует' in verdict_lower:
            confidence -= 20
        if 'возможно' in verdict_lower or 'вероятно' in verdict_lower:
            confidence -= 15

        return max(0, min(100, confidence))

    def _loимя_ai_data(self, guild_id: int) -> dict:
        """Загрузить данные AI-тикетов"""
        path = self._get_ai_data_path(guild_id)
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.loимя(f)
            except json.JSONDecodeError:
                # Повреждённый JSON — создать резервную копию и сбросить
                import shutil
                shutil.copy(path, path + '.bak')
                print(f'[TICKET] Резервная копия повреждённого JSON создана: {path}')
                return {}
            except Exception as e:
                print(f'[TICKET] Ошибка загрузки данных: {e}')
        return {}

    def _save_ai_data(self, guild_id: int, data: dict):
        """Сохранить данные AI-тикетов"""
        os.makedirs('data', exist_ok=True)
        path = self._get_ai_data_path(guild_id)
        try:
            # Сначала пишем во временный файл, затем переименовываем (атомарная запись)
            tmp = path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            import shutil
            shutil.move(tmp, path)
        except Exception as e:
            print(f'[TICKET] Ошибка сохранения данных: {e}')

    def _get_ticket_state(self, guild_id: int, channel_id: int) -> dict:
        """Получить состояние тикета"""
        data = self._loимя_ai_data(guild_id)
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
        data = self._loимя_ai_data(guild_id)
        data[str(channel_id)] = state
        self._save_ai_data(guild_id, data)
    
    def _delete_ticket_state(self, guild_id: int, channel_id: int):
        """Ticket state'ini удалить"""
        data = self._loимя_ai_data(guild_id)
        if str(channel_id) in data:
            del data[str(channel_id)]
            self._save_ai_data(guild_id, data)
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Ticket channellarindaki messagelari dinle ve AI ответить"""
        if message.author.bot:
            return
        if not message.channel.name.startswith("ticket-"):
            return
        if not AI_ENABLED:
            return

        guild_id = message.guild.id
        channel_id = message.channel.id
        state = self._get_ticket_state(guild_id, channel_id)

        # Staff message attiysa AI'yi durdur
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
        # Analiz devam ediyorsa новый сообщение действие
        if state.get('analyzing'):
            return

        # ── ЖАЛОБА STATE MACHINE ────────────────────────────────────────────
        complaint = state.get('complaint', {})
        if complaint.get('active'):
            await self._handle_complaint_flow(message, state, guild_id, channel_id, complaint)
            return

        # ── EK ДОКАЗАТЕЛЬСТВО СИСТЕМА ──────────────────────────────────────────────────
        if state.get('waiting_for_evidence'):
            content_lower = message.content.lower().strip()
            if content_lower in ('evet', 'e', 'yes', 'var'):
                state['waiting_for_evidence'] = False
                state['имяding_evidence'] = True
                self._save_ticket_state(guild_id, channel_id, state)
                await message.channel.send(
                    "📎 **Ek доказательство имяdme modu активен!**\n\n"
                    "Пожалуйста ek доказательство buraya отправить:\n"
                    "• Screenshot (resim как)\n"
                    "• Дополнительные сообщения (скопировать-вставить)\n"
                    "• DM ekran скриншот\n\n"
                    "Когда закончите, напишите **'готово'**."
                )
            elif content_lower in ('нет', 'н', 'no', 'hayır', 'h', 'yok'):
                state['waiting_for_evidence'] = False
                state['complaint'] = {}
                self._save_ticket_state(guild_id, channel_id, state)
                await message.channel.send("Понятно. Могу ли я помочь с чем-то еще?")
            # else: bимяd, tekrar sor
            return  # ← каждый statusda dur, normal AI akışına geçme
        
        # Ek доказательство собратьma modu
        if state.get('имяding_evidence'):
            content_lower = message.content.lower().strip()
            if content_lower in ('tamam', 'hazır', 'готово', 'готова', 'bitti', 'bitir'):
                state['имяding_evidence'] = False
                complaint = state.get('complaint', {})
                self._save_ticket_state(guild_id, channel_id, state)
                if not complaint:
                    await message.channel.send("❌ Жалоба infosi не найдено.")
                    return
                await message.channel.send("✅ Дополнительные доказательства получены. Повторный анализ...")
                await self._analyze_complaint(message.channel, state, guild_id, channel_id, complaint)
            else:
                if 'имяditional_evidence' not in state:
                    state['имяditional_evidence'] = []
                evidence_text = message.content
                if message.attachments:
                    evidence_text += f"\n[Ek: {len(message.attachments)} dosya]"
                state['имяditional_evidence'].append(evidence_text)
                complaint = state.get('complaint', {})
                if complaint and 'messages' in complaint:
                    complaint['messages'].append(f"[EK ДОКАЗАТЕЛЬСТВО]: {evidence_text[:300]}")
                    state['complaint'] = complaint
                self._save_ticket_state(guild_id, channel_id, state)
                await message.имяd_reaction("✅")
            return  # ← каждый statusda dur, normal AI akışına geçme

        # ── СИСТЕМА АПЕЛЛЯЦИИ ────────────────────────────────────────────────────
        itiraz_keywords = ['апелляция', 'подаю апелляцию', 'несправедливо', 'неверное решение',
                           'нечестно', 'не согласен', 'не согласна', 'не принимаю']
        if any(kw in message.content.lower() for kw in itiraz_keywords):
            # Проверяем последние наказания
            user_penalties = self._get_penalty_history(guild_id, message.author.id, days=1)
            if user_penalties:
                last_penalty = user_penalties[-1]

                # Есть ли право на апелляцию?
                if state.get('appeal_used'):
                    await message.channel.send(
                        "⚠️ Апелляция уже использована. Повторно подать апелляцию нельзя.\n"
                        "Передаю администрации."
                    )
                    await self._escalate_ticket(message.channel, state, 'appeal_rejected')
                    return
                
                state['appeal_used'] = True
                state['appeal_reason'] = message.content
                self._save_ticket_state(guild_id, channel_id, state)
                
                await message.channel.send(
                    f"📝 **Апелляция принята!**\n\n"
                    f"В конец наказание: **{last_penalty['reason']}** ({last_penalty['duration']} minutes)\n"
                    f"Апелляция причина: {message.content[:200]}\n\n"
                    "⏳ Апелляция AI сканироватьfından yeniden значение..."
                )
                
                # Апелляция AI'ya отправить
                await self._handle_appeal(message.channel, state, guild_id, channel_id, last_penalty)
                return

        # Жалоба tetikleyici kelimeler — только ticket açma amacıyla написано tetikle
        # ПРИМЕЧАНИЕ: кнопка жалобы уже сразу запускает поток, ключевое слово — только резервный триггер
        sikayet_keywords = ['sikayet', 'жалоба', 'kufur', 'мат', 'оскорбление',
                            'tehdit', 'taciz', 'bully', 'zorba', 'rahatsiz', 'rahatsız']
        # "как", "nedir", "ne" gibi soru kelimeleri varsa жалоба поток запуск
        soru_kelimeleri = ['как', 'как', 'ne takoe', 'ne', 'почему', 'как работает',
                           'как calisiyor', 'о', 'о', 'anlat', 'açıkla', 'acikla']
        icerik = message.content.lower()
        is_soru = any(kw in icerik for kw in soru_kelimeleri)
        # Kategori zaten выбрать keyword tetikleyiciyi atla
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
            await message.channel.send("Кратко опишите, что произошло:")
            return

        # ── АДМИНИСТРАТОР TALEBİ ───────────────────────────────────────────────────
        yetkili_keywords = ['поговорить с админом', 'позвать админа', 'позовите админа',
                            'администратор etiketle', 'администратору bağla', 'с администрацией iletişim',
                            'поговорить с админомmak', 'администратор хочу', 'имяmin çтяжелый',
                            'mod çтяжелый', 'модератор çтяжелый']
        if any(kw in message.content.lower() for kw in yetkili_keywords):
            support_role = discord.utils.get(message.guild.roles, name=SUPPORT_ROLE_NAME)
            mention = support_role.mention if support_role else '@Поддержка'
            await message.channel.send(
                f'{mention} — {message.author.mention} хочет связаться с вами.'
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
                        'запись': find_channel(message.guild, 'запись', 'запись', 'register', 'проверка', 'dogrulama', 'verification'),
                        'правила': find_channel(message.guild, 'правило', 'rules'),
                        'announcelar': find_channel(message.guild, 'announce', 'announce'),
                        'ticket': find_channel(message.guild, 'ticket', 'поддержка', 'support'),
                        'role': find_channel(message.guild, 'role', 'role'),
                        'общий': find_channel(message.guild, 'общий', 'general', 'sohbet'),
                        'panel': find_channel(message.guild, 'panel', 'link', 'web'),
                    },
                    'panel_url': os.getenv('PANEL_URL', ''),
                    'all_channels': [c.name for c in message.guild.text_channels],
                    'channel_mentions': {c.name: c.mention for c in message.guild.text_channels},
                }

                # Пользователь история ticket'larını имяd
                try:
                    all_tickets = self._loимя_ai_data(guild_id)
                    past_tickets = []
                    user_id_str = str(state.get('user_id', ''))
                    for ch_id, t in all_tickets.items():
                        if str(ch_id) == str(channel_id):
                            continue  # Текущий ticket'ı atla
                        if str(t.get('user_id', '')) == user_id_str and t.get('history'):
                            # В конец ticket'tan сводка al
                            last_msgs = [h['content'] for h in t['history'][-3:] if h.get('role') == 'user']
                            if last_msgs:
                                past_tickets.append(f"Назад ticket: {' | '.join(last_msgs[:2])}")
                    if past_tickets:
                        guild_context['past_tickets'] = past_tickets[-3:]  # В конец 3 ticket
                except:
                    pass

                full_message = message.content
                response, should_escalate, escalation_category, updated_history, detected_category = await ai_ticket_response(
                    full_message, state['history'], guild_context
                )
                actions = parse_ai_actions(response)

                # Işliyoruz действия
                if actions.get('jail'):
                    await self._apply_jail(message.channel, actions['jail']['user_id'],
                                           actions['jail']['duration'], actions['jail']['reason'],
                                           message.author)

                if actions.get('warn'):
                    await self._apply_warn(message.channel, actions['warn']['user_id'],
                                          actions['warn']['reason'], message.author)

                if actions.get('role_assign'):
                    await self._assign_role(message.guild, actions['role_assign']['user_id'],
                                           actions['role_assign']['role_id'])

                if actions.get('channel_redirect'):
                    channel = message.guild.get_channel(actions['channel_redirect']['channel_id'])
                    if channel:
                        await message.channel.send(f"Перенаправлено в {channel.mention}")

                if actions.get('delete_messages'):
                    await self._delete_messages(message.guild, actions['delete_messages']['channel_id'],
                                               actions['delete_messages']['count'])

                state['history'] = updated_history
                state['ai_message_count'] += 1
                state['category'] = detected_category

                if should_escalate or actions.get('escalate'):
                    await self._escalate_ticket(message.channel, state, escalation_category)
                    self._save_ticket_state(guild_id, channel_id, state)
                    return

                # 12. Generiruem bağlamnie podskazki для модератор
                suggested_actions = []
                
                # Если var предупреждения u пользователь
                if guild_context.get('user_id'):
                    try:
                        from cogs.warnings import loимя_warnings
                        warnings_data = loимя_warnings()
                        user_warnings = warnings_data.get(str(guild.id), {}).get(str(guild_context['user_id']), [])
                        
                        if len(user_warnings) >= 2:
                            suggested_actions.append({
                                'label': f'Ban ({len(user_warnings)} предупреждение)',
                                'action': 'ban',
                                'user_id': guild_context['user_id'],
                                'reason': f'{len(user_warnings)} предупреждение'
                            })
                        elif len(user_warnings) >= 1:
                            suggested_actions.append({
                                'label': 'Мут на 1 час',
                                'action': 'mute',
                                'user_id': guild_context['user_id'],
                                'duration': 60,
                                'reason': 'Повторное нарушение'
                            })
                    except:
                        pass

                # Отправляем очищенный ответ
                clean_response = actions.get('cleaned_response', response)
                if clean_response:
                    # Если есть предложенные действия — добавляем кнопки
                    if suggested_actions and message.channel.permissions_for(message.guild.me).send_messages:
                        view = discord.ui.View()

                        for action_data in suggested_actions[:3]:  # Максимум 3 кнопки
                            async def action_callback(interaction, data=action_data):
                                await interaction.response.defer(ephemeral=True)

                                target_user = guild.get_member(data['user_id'])
                                if not target_user:
                                    await interaction.followup.send("Пользователь не найден", ephemeral=True)
                                    return

                                if data['action'] == 'ban':
                                    await target_user.ban(reason=f"AI рекомендация: {data['reason']}")
                                    await interaction.followup.send(f"✅ {target_user.mention} забанен", ephemeral=True)
                                elif data['action'] == 'mute':
                                    until = discord.utils.utcnow() + timedelta(minutes=data['duration'])
                                    await target_user.timeout(until, reason=f"AI рекомендация: {data['reason']}")
                                    await interaction.followup.send(f"✅ {target_user.mention} заглушён на {data['duration']} мин", ephemeral=True)
                            
                            button = discord.ui.Button(
                                label=action_data['label'],
                                style=discord.ButtonStyle.danger if action_data['action'] == 'ban' else discord.ButtonStyle.primary
                            )
                            button.callback = action_callback
                            view.имяd_item(button)
                        
                        await message.channel.send(clean_response, view=view)
                    else:
                        await message.channel.send(clean_response)
                
                self._save_ticket_state(guild_id, channel_id, state)

            except Exception as e:
                print(f"AI Moderator error: {e}")
                import traceback
                traceback.print_exc()
                await self._escalate_ticket(message.channel, state, 'ai_error')
                self._save_ticket_state(guild_id, channel_id, state)

    async def _handle_appeal(self, channel, state, guild_id, channel_id, penalty):
        """Апелляция AI с значение"""
        from web.ai_helper import _call_text
        
        appeal_reason = state.get('appeal_reason', '')
        
        prompt = f"""Bir user AI moderasyon kararına апелляция ediyor.

=== НАКАЗАНИЕ ИНФОРМАЦИЯ ===
Наказание: {penalty['reason']}
Длительность: {penalty['duration']} minutes
Дата: {penalty['date']}

=== АПЕЛЛЯЦИЯ ===
{appeal_reason}

=== ЗАДАЧА ===
Апелляция значение. Пользователь haklı ?

КОНТРОЛЬ ET:
1. Содержит ли апелляция обоснованную причину?
2. Было ли наказание несправедливым?
3. Было ли неверное понимание?

ФОРМАТ ОТВЕТА:
[Значение]: (обоснованность апелляции — 2-3 предложения)
[Karar]: KABUL или RED или BELIRSIZ"""

        async with channel.typing():
            verdict = _call_text([
                {'role': 'system', 'content': 'Ты эксперт по модерации. Оцени апелляцию справедливо.'},
                {'role': 'user', 'content': prompt}
            ], max_tokens=300)

        print(f"[APPEAL] verdict: {verdict!r}")

        verdict_upper = verdict.strip().upper()

        if 'KABUL' in verdict_upper:
            await channel.send(
                "✅ **Апелляция принята!**\n\n"
                "Решение AI пересмотрено, и выявлена несправедливость.\n"
                "Наказание будет снято, передаю администрации."
            )
            await self._escalate_ticket(channel, state, 'appeal_accepted')
        elif 'RED' in verdict_upper:
            await channel.send(
                "❌ **Апелляция отклонена.**\n\n"
                "Решение AI пересмотрено и подтверждено как верное.\n"
                "Наказание остаётся в силе."
            )
        else:  # BELIRSIZ
            await channel.send(
                "🤔 **Апелляция неясна.**\n\n"
                "Этот статус не имеет чёткого значения, передаю администрации."
            )
            await self._escalate_ticket(channel, state, 'appeal_unclear')

        self._save_ticket_state(guild_id, channel_id, state)

    async def _handle_complaint_flow(self, message, state, guild_id, channel_id, complaint):
        """Управление потоком жалобы шаг за шагом"""
        content = message.content.strip()
        step = complaint.get('step')

        if step == 'ask_description':
            complaint['description'] = content
            complaint['step'] = 'ask_type'
            state['ai_message_count'] += 1
            self._save_ticket_state(guild_id, channel_id, state)
            await message.channel.send(
                "Жалоба принята. Какого рода проблема у вас возникла?\n"
                "**1** - Мат/Оскорбление\n**2** - Угроза\n**3** - Травля/Насмешка\n**4** - Другое"
            )
            return

        if step == 'ask_type':
            type_map = {'1': 'kufur', '2': 'tehdit', '3': 'zorbalik', '4': 'diger'}
            complaint['type'] = type_map.get(content, 'diger')
            complaint['step'] = 'ask_accused'
            state['ai_message_count'] += 1

            # При выборе "Другое" сразу передаём администрации
            if complaint['type'] == 'diger':
                state['complaint'] = {}
                self._save_ticket_state(guild_id, channel_id, state)
                await message.channel.send("Передаю администрации, в кратчайшие сроки займутся вашим обращением.")
                await self._escalate_ticket(message.channel, state, 'diger')
                return

            self._save_ticket_state(guild_id, channel_id, state)
            await message.channel.send("Введите Discord ID пользователя, на которого жалуетесь:")
            return

        if step == 'ask_accused':
            accused_id = content.strip()
            # Проверка ID — принимаем mention, числовой ID или имя
            import re as _re
            mention_match = _re.search(r'<@!?(\d+)>', accused_id)
            if mention_match:
                accused_id = mention_match.group(1)
            elif not accused_id.isdigit():
                # Поиск по имени
                found = discord.utils.find(
                    lambda m: m.display_name.lower() == accused_id.lower() or m.name.lower() == accused_id.lower(),
                    message.guild.members
                )
                if found:
                    accused_id = str(found.id)
                else:
                    await message.channel.send(
                        "❌ Пользователь не найден. Пожалуйста, введите Discord ID (17-19-значное число) или @упоминание:"
                    )
                    return
            complaint['accused_id'] = accused_id
            complaint['step'] = 'ask_channel'
            state['ai_message_count'] += 1
            self._save_ticket_state(guild_id, channel_id, state)
            await message.channel.send(
                "В каком канале произошёл инцидент? Введите ID канала.\n"
                "*(Чтобы узнать ID канала: правый клик на канал → Копировать ID)*"
            )
            return

        if step == 'ask_channel':
            complaint['channel_id'] = content.strip()
            complaint['step'] = 'ask_messages'
            state['ai_message_count'] += 1
            self._save_ticket_state(guild_id, channel_id, state)

            # Канал ID число messageları автоматически сканировать
            if content.strip().isdigit():
                await message.channel.send("⏳ Сообщения сканируются, пожалуйста, подождите...")
                try:
                    target_ch = message.guild.get_channel(int(content.strip()))
                    if target_ch:
                        accused_id_str = complaint.get('accused_id', '')
                        accused_id_int = int(accused_id_str) if accused_id_str.isdigit() else None
                        complainant_id_int = state.get('user_id')

                        # Жалоба edenin имяını bul
                        complainant_member = message.guild.get_member(complainant_id_int) if complainant_id_int else None
                        complainant_name = complainant_member.display_name if complainant_member else str(complainant_id_int)

                        # Жалоба edilenin имяını bul
                        accused_member = message.guild.get_member(accused_id_int) if accused_id_int else None
                        accused_name = accused_member.display_name if accused_member else str(accused_id_int)

                        msgs = []
                        all_msgs_raw = []
                        # В конец 1000 сообщение сканировать
                        async for msg in target_ch.history(limit=1000, oldest_first=False):
                            if msg.author.bot:
                                continue
                            all_msgs_raw.append(msg)

                        # En eskiden en yeniye очередь
                        all_msgs_raw.reverse()

                        # Каждый iki сканироватьfın messagelarını собрать
                        accused_msgs_set = set()
                        complainant_msgs_set = set()

                        for i, msg in enumerate(all_msgs_raw):
                            is_accused = accused_id_int and msg.author.id == accused_id_int
                            is_complainant = complainant_id_int and msg.author.id == complainant_id_int
                            if not (is_accused or is_complainant):
                                continue

                            # Yakın pencerede karşı сканироватьf var ?
                            window_start = max(0, i - 15)
                            window_end = min(len(all_msgs_raw), i + 16)
                            other_id = complainant_id_int if is_accused else accused_id_int
                            near_other = any(
                                all_msgs_raw[j].author.id == other_id
                                for j in range(window_start, window_end) if j != i
                            )

                            # Direkt mention/reply контроль
                            is_mention = other_id and any(m.id == other_id for m in msg.mentions)
                            is_reply = False
                            if msg.reference and msg.reference.reлевыйved:
                                ref = msg.reference.reлевыйved
                                if hasattr(ref, 'author') and other_id:
                                    is_reply = ref.author.id == other_id

                            if not (is_mention or is_reply or near_other):
                                continue

                            tag = '🎯 ВЕРНО' if (is_mention or is_reply) else '📍 BAĞLAMLI'
                            label = 'ЖАЛОБА EDİLEN' if is_accused else 'ЖАЛОБА EDEN'
                            line = (
                                f"[{msg.created_at.strftime('%d.%m %H:%M')}] "
                                f"[{label}: {msg.author.display_name}] {tag}: "
                                f"{msg.content[:300]}"
                            )
                            if is_accused:
                                accused_msgs_set.имяd(line)
                            else:
                                complainant_msgs_set.имяd(line)

                        # Каждый iki сканироватьfın messagelarını birleştir
                        msgs = sorted(accused_msgs_set | complainant_msgs_set)

                        print(f"[TICKET] Tarama: {len(accused_msgs_set)} жалоба edilen, "
                              f"{len(complainant_msgs_set)} жалоба eden сообщение найдено")

                        # Удален messageları cache'den тянуть — каждый iki сканироватьf для
                        deleted_msgs = []
                        try:
                            from cogs.logs import _msg_cache as _lc
                            for msg_id, cached_msg in list(_lc.items()):
                                if cached_msg.get('channel_id') != int(content.strip()):
                                    continue
                                author_id = cached_msg.get('author_id')
                                # Только iki сканироватьfın messagelarını al
                                if author_id not in (accused_id_int, complainant_id_int):
                                    continue
                                # Hâlâ channelda var ?
                                still_exists = any(m.id == msg_id for m in all_msgs_raw)
                                if still_exists:
                                    continue
                                ts = cached_msg.get('timestamp', '')[:16].replace('T', ' ')
                                label = 'ЖАЛОБА EDİLEN' if author_id == accused_id_int else 'ЖАЛОБА EDEN'
                                deleted_msgs.append(
                                    f"[{ts}] [{label}: {cached_msg.get('author_name','?')}] 🗑️ УДАЛЕН СООБЩЕНИЕ: "
                                    f"{cached_msg.get('content', '[Содержимое yok]')[:300]}"
                                )
                        except Exception as _de:
                            print(f'[TICKET] Cache deleted msgs Ошибки: {_de}')

                        if deleted_msgs:
                            msgs.extend(deleted_msgs)
                            await message.channel.send(
                                f"⚠️ **{len(deleted_msgs)} удален message** tespit edildi (содержимое скриншот)."
                            )

                        if msgs:
                            complaint['messages'] = msgs
                            complaint['messages_verified'] = True
                            complaint['step'] = 'analyze'
                            complaint['accused_name'] = accused_name
                            complaint['complainant_name'] = complainant_name
                            self._save_ticket_state(guild_id, channel_id, state)
                            await message.channel.send(
                                f"✅ **{len(msgs)} ilgili message найдено.** Analiz сделатьılıyor..."
                            )
                            await self._analyze_complaint(message.channel, state, guild_id, channel_id, complaint)
                            return
                        else:
                            await message.channel.send(
                                f"❌ **{target_ch.mention}** в канале **{accused_name}**'in "
                                f"**{complainant_name}**'e yönelik сообщение не найдено.\n\n"
                                "Скопируйте и вставьте сюда сообщения этого пользователя:"
                            )
                            complaint['messages_verified'] = False
                            complaint['step'] = 'ask_messages'
                            self._save_ticket_state(guild_id, channel_id, state)
                            return
                    else:
                        await message.channel.send(
                            "❌ Канал не найдено. Скопируйте и вставьте сюда сообщения этого пользователя:"
                        )
                        complaint['step'] = 'ask_messages'
                        self._save_ticket_state(guild_id, channel_id, state)
                        return
                except Exception as e:
                    print(f"[TICKET] Channel scan error: {e}")
                    await message.channel.send(
                        "⚠️ Канал сканироватьnırken Ошибка oluştu. Сообщения manuel как kopyalayıp сделатьıştır:"
                    )
                    complaint['step'] = 'ask_messages'
                    self._save_ticket_state(guild_id, channel_id, state)
                    return

            await message.channel.send(
                "Скопируйте и вставьте сюда сообщения этого пользователя:"
            )
            return

        if step == 'ask_messages':
            complaint['messages'] = [content]
            complaint['messages_verified'] = False
            complaint['step'] = 'analyze'
            # Isimler yoksa şimdi имяd
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
                await message.channel.send("Скопируйте и вставьте сюда сообщения этого пользователя:")
            return

    async def _analyze_complaint(self, channel, state, guild_id, channel_id, complaint):
        """Süper-umniy analiz жалобы с glubokoy proverkoy"""
        from web.complaint_analyzer import ComplaintAnalyzer
        
        # Создал analizör
        analyzer = ComplaintAnalyzer(self.bot)
        
        # Alıyoruz ID жалоба ve obvinyaemogo
        complainant_id = state.get('user_id')
        accused_id = complaint.get('accused_id')
        
        if not complainant_id or not accused_id:
            await channel.send("Не успешно oldu opredelit участников жалобы.")
            state['complaint'] = {}
            state['analyzing'] = False
            self._save_ticket_state(guild_id, channel_id, state)
            return
        
        # Preobrazuem в int если gerekli
        try:
            complainant_id = int(complainant_id)
            accused_id = int(accused_id) if str(accused_id).isdigit() else None
        except:
            await channel.send("Nekorrektniy ID пользователь.")
            state['complaint'] = {}
            state['analyzing'] = False
            self._save_ticket_state(guild_id, channel_id, state)
            return
        
        if not accused_id:
            await channel.send("Не успешно oldu opredelit ID obvinyaemogo.")
            state['complaint'] = {}
            state['analyzing'] = False
            self._save_ticket_state(guild_id, channel_id, state)
            return
        
        # Alıyoruz metin жалобы ve сообщения
        complaint_text = complaint.get('description', '')
        provided_messages = complaint.get('messages', [])
        
        # Zapuskaem süper-analiz
        async with channel.typing():
            try:
                result = await analyzer.analyze_complaint(
                    guild=channel.guild,
                    complainant_id=complainant_id,
                    accused_id=accused_id,
                    complaint_text=complaint_text,
                    provided_messages=provided_messages
                )
            except Exception as e:
                print(f"[COMPLAINT] Ошибка analiza: {e}")
                import traceback
                traceback.print_exc()
                await channel.send("Proizosla ошибка iken analize жалобы. На e модератор.")
                await self._escalate_ticket(channel, state, 'ai_error')
                return
        
        # Alıyoruz результат
        verdict = result['verdict']
        confidence = result['confidence']
        severity = result['severity']
        recommendation = result['recommendation']
        analysis_text = result['analysis']
        
        print(f"[COMPLAINT] verdict={verdict}, confidence={confidence}, severity={severity}")
        
        # Если доверие nizkaya — на e модератор
        if confidence < 50:
            await channel.send(
                f"{analysis_text}\n\n"
                f"**Доверие fazla nizkaya ({confidence}%)** — на e модератор для rucnoy контроль."
            )
            await self._escalate_ticket(channel, state, 'low_confidence')
            state['complaint'] = {}
            state['analyzing'] = False
            self._save_ticket_state(guild_id, channel_id, state)
            return
        
        # Отправл analiz
        await channel.send(analysis_text)
        
        # Primenyaem предложение
        action = recommendation['action']
        duration = recommendation['duration']
        reason = recommendation['reason']
        
        guild = channel.guild
        
        if action == 'BAN':
            target = guild.get_member(accused_id)
            if target:
                try:
                    await target.ban(reason=f"AI: {reason}")
                    await channel.send(f"✅ **{target.display_name}** забанен. Причина: {reason}")
                except Exception as e:
                    await channel.send(f"Не успешно oldu zabanit: {e}")
        
        elif action == 'MUTE':
            target = guild.get_member(accused_id)
            if target and duration:
                try:
                    until = discord.utils.utcnow() + timedelta(minutes=duration)
                    await target.timeout(until, reason=f"AI: {reason}")
                    hours = duration // 60
                    await channel.send(f"✅ **{target.display_name}** susturuldu на {hours} c. Причина: {reason}")
                except Exception as e:
                    await channel.send(f"Не успешно oldu zamyutit: {e}")
        
        elif action == 'WARN':
            target = guild.get_member(accused_id)
            if target:
                try:
                    from cogs.warnings import Предупреждениеs
                    warnings_cog = self.bot.get_cog('Предупреждениеs')
                    if warnings_cog:
                        await warnings_cog.имяd_warning(target, guild.me, reason)
                        await channel.send(f"✅ **{target.display_name}** polucil предупреждение. Причина: {reason}")
                except Exception as e:
                    await channel.send(f"Не успешно oldu ver предупреждение: {e}")
        
        elif action == 'MUTE_BOTH':
            # Zamyutit каждый ikisi
            compl = guild.get_member(complainant_id)
            accus = guild.get_member(accused_id)
            
            if compl and accus and duration:
                try:
                    until = discord.utils.utcnow() + timedelta(minutes=duration)
                    await compl.timeout(until, reason=f"AI: {reason}")
                    await accus.timeout(until, reason=f"AI: {reason}")
                    await channel.send(
                        f"✅ **{compl.display_name}** ve **{accus.display_name}** susturuldui на {duration} dk.\n"
                        f"Причина: {reason}"
                    )
                except Exception as e:
                    await channel.send(f"Не успешно oldu zamyutit каждый ikisi: {e}")
        
        elif action == 'WARN_COMPLAINANT':
            # Предупреждение жалоба для lojnuyu жалоба
            compl = guild.get_member(complainant_id)
            if compl:
                try:
                    from cogs.warnings import Предупреждениеs
                    warnings_cog = self.bot.get_cog('Предупреждениеs')
                    if warnings_cog:
                        await warnings_cog.имяd_warning(compl, guild.me, reason)
                        await channel.send(f"⚠️ **{compl.display_name}** polucil предупреждение для lojnuyu жалоба.")
                except Exception as e:
                    await channel.send(f"Не успешно oldu ver предупреждение: {e}")
        
        else:  # NO_ACTION
            await channel.send("Naruseniy не obnarujeno. Жалоба reddedildi.")
        
        # Ocisaem sostoyanie
        state['complaint'] = {}
        state['analyzing'] = False
        self._save_ticket_state(guild_id, channel_id, state)
    async def _escalate_ticket(self, channel: discord.TextChannel, state: dict, reason: str):
        """Ticket'i администрации yonlendir"""
        if state['staff_notified']:
            return  # уже yonlendirilmis
        
        state['status'] = 'escalated'
        state['escalated_at'] = datetime.datetime.utcnow().isoformat()
        state['staff_notified'] = True
        
        # Yonlendirme сообщение
        e = discord.Embed(color=0xF39C12, timestamp=datetime.datetime.utcnow())
        
        reason_text = {
            'sikayet': 'Жалоба должна быть рассмотрена модератором',
            'teknik': 'Техническая проблема требует контроля модератора',
            'администратор': 'Действие требует прав модератора',
            'agir_ihlal': 'Обнаружено серьёзное нарушение, требуется контроль',
            'апелляция': 'Пользователь оспаривает решение AI',
            'ban_talebi': 'Бан может быть завершён только модератором',
            'max_messages': 'Лимит сообщений превышен, модераторы получают управление',
            'ai_error': 'Системная ошибка, модераторы получают управление',
            'diger': 'Этот вопрос должен быть рассмотрен модератором'
        }
        
        e.description = (
            f"## На e модератор\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"**Причина:** {reason_text.get(reason, 'Модераторы получает управление')}\n\n"
            f"Nasa команда podderjki svyajetsya с vami в blijaysee время.\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        if channel.guild.icon:
            e.set_footer(text=f"{channel.guild.name} · Moderasyon", icon_url=channel.guild.icon.url)
        else:
            e.set_footer(text=f"{channel.guild.name} · Moderasyon")
        
        await channel.send(embed=e)
        
        # Поддержка роли ping at
        support_role = discord.utils.get(channel.guild.roles, name=SUPPORT_ROLE_NAME)
        if support_role:
            await channel.send(
                f"🔔 {support_role.mention} — Новый поддержка talebi направление!"
            )
        
        # State сохранить
        self._save_ticket_state(channel.guild.id, channel.id, state)
    
    async def _apply_jail(self, channel: discord.TextChannel, user_id: int, duration: int, reason: str, complainant: discord.Member):
        """AI moderator jail наказание примен"""
        try:
            guild = channel.guild
            target_user = guild.get_member(user_id)
            if not target_user:
                try:
                    target_user = await guild.fetch_member(user_id)
                except Exception:
                    target_user = None
            
            if not target_user:
                await channel.send("❌ Пользователь bu на сервере не найдено.")
                return
            
            # Jail роли bul или olustur
            jail_role = discord.utils.get(guild.roles, name="Jail")
            if not jail_role:
                # Jail роли olustur
                jail_role = await guild.create_role(
                    name="Jail",
                    color=discord.Color.dark_gray(),
                    reason="AI Moderator jail роли"
                )
            # Запрещаем jail-роль во всех каналах
            for channel_obj in guild.channels:
                try:
                    await channel_obj.set_permissions(jail_role, send_messages=False, speak=False)
                except:
                    pass

            # Выдаём jail-роль
            await target_user.имяd_roles(jail_role, reason=f"AI Moderator: {reason}")

            # Отправляем DM пользователю
            try:
                dm_embed = discord.Embed(color=0xE74C3C, timestamp=datetime.datetime.utcnow())
                dm_embed.description = (
                    f"## Наказание: Jail\n"
                    f"### Вы получили jail\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"**Сервер:** {guild.name}\n"
                    f"**Длительность:** {duration} минут\n"
                    f"**Причина:** {reason}\n\n"
                    f"По окончании срока jail-роль будет автоматически снята.\n"
                    f"Если хотите оспорить — напишите в тикет.\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                )
                if guild.icon:
                    dm_embed.set_footer(text=f"{guild.name} · Moderasyon", icon_url=guild.icon.url)
                else:
                    dm_embed.set_footer(text=f"{guild.name} · Moderasyon")
                await target_user.send(embed=dm_embed)
            except:
                pass
            
            # Канал bildir
            jail_embed = discord.Embed(color=0x2ECC71, timestamp=datetime.datetime.utcnow())
            jail_embed.description = (
                f"## Jail применён\n"
                f"### Наказание завершено\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"**Пользователь:** {target_user.mention}\n"
                f"**Длительность:** {duration} минут\n"
                f"**Причина:** {reason}\n\n"
                f"Наша команда модераторов поможет решить проблему.\n"
                f"Если хотите оспорить — оставьте этот тикет открытым.\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            if channel.guild.icon:
                jail_embed.set_footer(text=f"{channel.guild.name} · Moderasyon", icon_url=channel.guild.icon.url)
            else:
                jail_embed.set_footer(text=f"{channel.guild.name} · Moderasyon")
            await channel.send(embed=jail_embed)
            await channel.send(embed=jail_embed)
            
            # Jail'i автоматически удалить (duration minutes после)
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

            # Уведомить администраторов о применённом наказании
            await self._notify_имяmins_penalty(
                guild, penalty_type='jail',
                target=target_user, reason=reason,
                source_channel=channel, moderator=complainant,
            )

        except Exception as e:
            await channel.send(f"❌ Ошибка при выдаче наказания Jail: {str(e)}")
            print(f"Jail error: {e}")
    
    async def _schedule_unjail(self, guild: discord.Guild, user: discord.Member, jail_role: discord.Role, duration: int):
        """Снять jail-наказание после указанного времени"""
        import asyncio
        await asyncio.sleep(duration * 60)

        try:
            # Пользователь всё ещё на сервере?
            fresh_member = guild.get_member(user.id)
            if not fresh_member:
                try:
                    fresh_member = await guild.fetch_member(user.id)
                except discord.NotFound:
                    print(f'[TICKET] Unjail: {user} покинул сервер, роль не снята')
                    return
                except Exception as e:
                    print(f'[TICKET] Unjail fetch ошибка: {e}')
                    return

            # Jail роль hâlâ var ?
            fresh_role = guild.get_role(jail_role.id)
            if not fresh_role:
                print(f'[TICKET] Unjail: Jail роль удален')
                return

            if fresh_role in fresh_member.roles:
                await fresh_member.remove_roles(fresh_role, reason="Jail длительность doldu (AI Moderator)")
                try:
                    dm_embed = discord.Embed(color=0x2ECC71, timestamp=datetime.datetime.utcnow())
                    dm_embed.description = (
                        f"## Jail удалено\n"
                        f"### Наказание завершено\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"**Сервер:** {guild.name}\n\n"
                        f"Sizin jail srok желание. Teper siz edebilirsiniz polzovatsya сервер как obicno.\n"
                        f"Пожалуйста, prodoljayte soblyudat правила сервер.\n\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                    )
                    if guild.icon:
                        dm_embed.set_footer(text=f"{guild.name} · Moderasyon", icon_url=guild.icon.url)
                    else:
                        dm_embed.set_footer(text=f"{guild.name} · Moderasyon")
                    await fresh_member.send(embed=dm_embed)
                except:
                    pass
        except Exception as e:
            print(f'[TICKET] Unjail Ошибки: {e}')
    
    async def _apply_warn(self, channel: discord.TextChannel, user_id: int, reason: str, moderator: discord.Member):
        """AI ver предупреждение"""
        try:
            guild = channel.guild
            target_user = guild.get_member(user_id)
            if not target_user:
                try:
                    target_user = await guild.fetch_member(user_id)
                except:
                    target_user = None

            if not target_user:
                await channel.send("Пользователь не найдено на на сервере.")
                return

            # Выдать предупреждение пользователю с система warnings
            from cogs.warnings import Предупреждениеs
            warnings_cog = self.bot.get_cog('Предупреждениеs')
            if warnings_cog:
                # Создал feykovoe interaction для vizova /warn
                await warnings_cog.имяd_warning(target_user, moderator, reason)
                await channel.send(f"Предупреждение verildi {target_user.mention}: {reason}")
                # Уведомить администраторов
                await self._notify_имяmins_penalty(
                    guild, penalty_type='warn',
                    target=target_user, reason=reason,
                    source_channel=channel, moderator=moderator,
                )
            else:
                await channel.send("Система предупреждений недоступна.")

        except Exception as e:
            await channel.send(f"Ошибка iken vidace предупреждения: {str(e)}")
            print(f"Warn error: {e}")

    async def _notify_имяmins_penalty(self, guild, *, penalty_type: str, target,
                                     reason: str, source_channel, moderator):
        """Уведомить администраторов о применённом наказании.

        Канал для уведомлений: сначала `data/ticket_notify_<guild_id>.json` →
        `notify_channel_id`, иначе первый текстовый канал с именем
        'имяmin-log'/'mod-log'/'логи-модерации', иначе None (тогда DM
        владельцу сервера).
        """
        notify_ch_id = None
        cfg_path = f'data/ticket_notify_{guild.id}.json'
        try:
            if os.path.exists(cfg_path):
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    notify_ch_id = (json.loимя(f) or {}).get('notify_channel_id')
        except Exception:
            notify_ch_id = None

        target_ch = None
        if notify_ch_id:
            try:
                target_ch = guild.get_channel(int(notify_ch_id)) or await guild.fetch_channel(int(notify_ch_id))
            except Exception:
                target_ch = None
        if target_ch is None:
            for name in ('имяmin-log', 'mod-log', 'логи-модерации', 'staff-log'):
                target_ch = discord.utils.get(guild.text_channels, name=name)
                if target_ch:
                    break

        type_emoji = {
            'warn': '⚠️',
            'jail': '🔒',
            'ban': '🔨',
            'kick': '👢',
            'mute': '🔇',
        }.get(penalty_type, '📢')
        type_label = {
            'warn': 'Предупреждение',
            'jail': 'Jail (ограничение)',
            'ban': 'Бан',
            'kick': 'Кик',
            'mute': 'Мут',
        }.get(penalty_type, penalty_type.title())

        embed = discord.Embed(
            title=f"{type_emoji} AI Модератор: {type_label}",
            color=0xE74C3C if penalty_type in ('ban', 'jail') else 0xF1C40F,
            timestamp=datetime.datetime.utcnow(),
        )
        embed.имяd_field(name="Пользователь", value=f"{target.mention} (`{target.id}`)", inline=False)
        embed.имяd_field(name="Причина", value=reason[:500] if reason else "—", inline=False)
        embed.имяd_field(name="Канал тикета", value=source_channel.mention if source_channel else "—", inline=True)
        embed.имяd_field(name="Модератор", value=moderator.mention if moderator else "AI", inline=True)
        embed.set_footer(text=f"{guild.name} • AI Moderation", icon_url=guild.icon.url if guild.icon else None)

        # Пинг админов (роли с правами Имяministrator)
        имяmin_ping = ""
        try:
            имяmin_role = discord.utils.get(guild.roles, permissions=discord.Permissions(имяministrator=True))
            if имяmin_role:
                имяmin_ping = имяmin_role.mention + " "
        except Exception:
            pass

        sent = False
        if target_ch is not None:
            try:
                await target_ch.send(content=имяmin_ping or None, embed=embed)
                sent = True
            except Exception:
                sent = False
        if not sent:
            # Fallback: DM владельцу
            try:
                if guild.owner and not guild.owner.bot:
                    await guild.owner.send(content=имяmin_ping, embed=embed)
            except Exception:
                pass
    
    async def _assign_role(self, guild: discord.Guild, user_id: int, role_id: int):
        """AI ver роль"""
        try:
            target_user = guild.get_member(user_id)
            role = guild.get_role(role_id)
            
            if not target_user:
                print(f"[TICKET] Роли assign: пользователь {user_id} не найдено")
                return
            
            if not role:
                print(f"[TICKET] Назначение роли: роль {role_id} не найдена")
                return
            
            await target_user.имяd_roles(role, reason="AI Ticket Assistant")
            print(f"[TICKET] Роль {role.name} выдана {target_user}")
            
        except Exception as e:
            print(f"Роли assign error: {e}")
    
    async def _delete_messages(self, guild: discord.Guild, channel_id: int, count: int):
        """AI удалить сообщения"""
        try:
            channel = guild.get_channel(channel_id)
            if not channel:
                print(f"[TICKET] Delete messages: канал {channel_id} не найдено")
                return
            
            deleted = await channel.purge(limit=min(count, 100))
            print(f"[TICKET] Удалено {len(deleted)} сообщение в {channel.name}")
            
        except Exception as e:
            print(f"Delete messages error: {e}")
    
    async def _check_message_history(self, channel: discord.TextChannel, guild: discord.Guild, user_id: int = None, target_channel_id: int = None) -> str:
        """Сканировать сообщения указанного пользователя"""
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
                return f"Это channelda {'bu userya ait ' if user_id else ''}message не найдено."

            summary = f"#{target_channel.name} в канале найден messagelar ({len(messages)} имяet):\n"
            for msg in messages[:20]:
                edited_tag = ' [EDİTLENMİŞ]' if msg['edited'] else ''
                summary += f"[{msg['timestamp']}] {msg['author']}: {msg['content']}{edited_tag}\n"

            return summary

        except Exception as e:
            return f"Сообщение история контроль edilemedi: {str(e)}"

    @app_commands.command(name="ticket-panel", description="Отправить панель тикетов в канал")
    @app_commands.checks.has_permissions(имяministrator=True)
    async def ticket_panel(self, interaction: discord.Interaction):
        if interaction.guild.id in TICKET_DISABLED_GUILDS:
            await interaction.response.send_message(
                '❌ Это на сервере ticket система активен не.', ephemeral=True
            )
            return

        # Канал zaten bot сканироватьfından отправл bir ticket paneli var ?
        async for msg in interaction.channel.history(limit=20):
            if (msg.author == interaction.guild.me and
                    msg.embeds and
                    msg.components and
                    any('ticket_open' in str(c) for c in msg.components)):
                await interaction.response.send_message(
                    "⚠️ Это channelda zaten bir ticket paneli var. До eskisini удалить.",
                    ephemeral=True
                )
                return
        e = discord.Embed(
            title="🎫  ПОДДЕРЖКА СИСТЕМА",
            color=0x5865F2,
            timestamp=datetime.datetime.utcnow()
        )
        e.description = (
            f"```ansi\n\u001b[1;34m✦ Aether СИСТЕМА ПОДДЕРЖКИ ✦\u001b[0m\n```\n"
            f"{_divider()}\n\n"
            "Возникла ли проблема на сервере?\n"
            "Хотите что-то спросить?\n\n"
            "**Нажмите на кнопку ниже**, чтобы создать приватный канал поддержки.\n"
            "🤖 **AI-ассистент** сначала поможет вам!\n"
            "При необходимости подключится наша команда. 💙\n\n"
            f"{_divider()}\n\n"
            "```yaml\n"
            "🤖 AI Поддержка    •    ⚡ Быстрый ответ    •    🔒 Приватный канал\n"
            "```"
        )
        e.set_image(url=GIF_PANEL)
        e.set_footer(
            text=f"{interaction.guild.name} • AI Поддержка Система",
            icon_url=interaction.guild.icon.url if interaction.guild.icon else None
        )
        await interaction.channel.send(embed=e, view=TicketView())
        await interaction.response.send_message("✅ Ticket paneli отправлено.", ephemeral=True)

    @app_commands.command(name="ticket-имяd", description="Tickete user имяdr")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def ticket_имяd(self, interaction: discord.Interaction, user: discord.Member):
        await interaction.channel.set_permissions(user, reимя_messages=True, send_messages=True)
        e = discord.Embed(
            description=f"✅ {user.mention} bu поддержка в канал имяdndi.",
            color=0x2ECC71
        )
        await interaction.response.send_message(embed=e)

    @app_commands.command(name="ticket-cikar", description="Удалить пользователя из тикета")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def ticket_cikar(self, interaction: discord.Interaction, user: discord.Member):
        await interaction.channel.set_permissions(user, reимя_messages=False)
        e = discord.Embed(
            description=f"🚫 {user.mention} bu поддержка из канала удалить.",
            color=0xE74C3C
        )
        await interaction.response.send_message(embed=e)
    
    @app_commands.command(name="ticket-ai-stats", description="Показать статистику AI-поддержки")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_ai_stats(self, interaction: discord.Interaction):
        """AI ticket статистика goster"""
        data = self._loимя_ai_data(interaction.guild.id)
        
        if not data:
            await interaction.response.send_message("❌ Пока AI поддержка verisi yok.", ephemeral=True)
            return
        
        total_tickets = len(data)
        ai_handling = sum(1 for t in data.values() if t['status'] == 'ai_handling')
        escalated = sum(1 for t in data.values() if t['status'] == 'escalated')
        staff_handling = sum(1 for t in data.values() if t['status'] == 'staff_handling')
        
        total_ai_messages = sum(t['ai_message_count'] for t in data.values())
        avg_messages = total_ai_messages / total_tickets if total_tickets > 0 else 0
        
        e = discord.Embed(
            title="🤖  AI Поддержка Статистика",
            color=0x00D9FF,
            timestamp=datetime.datetime.utcnow()
        )
        e.description = (
            f"```ansi\n\u001b[1;36m📊 СТАТИСТИКА\u001b[0m\n```\n"
            f"{_divider()}"
        )
        e.имяd_field(name="📋 Всего тикетов", value=f"```{total_tickets}```", inline=True)
        e.имяd_field(name="🤖 Обрабатывает AI", value=f"```{ai_handling}```", inline=True)
        e.имяd_field(name="🔄 Перенаправлено", value=f"```{escalated}```", inline=True)
        e.имяd_field(name="👥 Обрабатывают модеры", value=f"```{staff_handling}```", inline=True)
        e.имяd_field(name="💬 Сообщений AI", value=f"```{total_ai_messages}```", inline=True)
        e.имяd_field(name="📊 Среднее число сообщений", value=f"```{avg_messages:.1f}```", inline=True)
        e.set_footer(text="Поддержка Aether AI")
        
        await interaction.response.send_message(embed=e)
    
    @app_commands.command(name="ticket-ai-toggle", description="Включить/отключить AI-поддержку тикетов")
    @app_commands.checks.has_permissions(имяministrator=True)
    async def ticket_ai_toggle(self, interaction: discord.Interaction):
        """Включить/отключить AI-поддержку тикетов"""
        global AI_ENABLED
        AI_ENABLED = not AI_ENABLED
        
        status = "✅ Активен" if AI_ENABLED else "❌ Değilaktif"
        e = discord.Embed(
            title="🤖  AI Поддержка Система",
            description=f"AI поддержка система şu an: **{status}**",
            color=0x2ECC71 if AI_ENABLED else 0xE74C3C
        )
        await interaction.response.send_message(embed=e)
    
    @app_commands.command(name="ticket-force-escalate", description="Перенаправить текущий тикет администрации")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def ticket_force_escalate(self, interaction: discord.Interaction):
        """Ticket'i manuel как yonlendir"""
        if not interaction.channel.name.startswith("ticket-"):
            await interaction.response.send_message("❌ Это bir ticket канал не.", ephemeral=True)
            return
        
        state = self._get_ticket_state(interaction.guild.id, interaction.channel.id)
        
        if state['status'] == 'escalated':
            await interaction.response.send_message("⚠️ Это ticket zaten направление.", ephemeral=True)
            return
        
        await interaction.response.send_message("🔄 Ticket администрации направление...", ephemeral=True)
        await self._escalate_ticket(interaction.channel, state, 'manual')


async def setup(bot):
    await bot.имяd_cog(Ticket(bot), guilds=[discord.Object(id=1421244140359909513), discord.Object(id=1107038411895881788), discord.Object(id=1498837105915330562)])
