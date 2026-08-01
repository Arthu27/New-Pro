import discord
from discord.ext import commands, tasks
from discord import app_commands
import datetime
from datetime import timedelta
import io
import json
import os
import logging
import asyncio
from cogs.embed_utils import gif, now_ts, _divider
from services.rate_limiter import get_rate_limiter
from services.feedback_service import get_feedback_service
from services.custom_menu import CustomMenu, TicketMenu, StatsMenu, HelpMenu

from logger import get_logger
log = get_logger("ticket")


logger = logging.getLogger('ticket')

TICKET_CATEGORY_NAME = "Тикеты"
SUPPORT_ROLE_NAME = "Поддержка"

GIF_TICKET_OPEN  = "https://media.tenor.com/3Ky6UNqMFpkAAAAC/talking-speak.gif"
GIF_TICKET_CLOSE = "https://media.tenor.com/x8v1oNUOmg4AAAAC/ban-hammer.gif"
GIF_PANEL        = "https://media.tenor.com/ZBDpMFBMFpkAAAAC/celebration-party.gif"

# AI Ticket Settings
AI_ENABLED = True  # AI-система поддержки активна
MAX_AI_MESSAGES = 10

# На этом сервере система тикетов отключена
TICKET_DISABLED_GUILDS: set = set()


class TicketCategorySelect(discord.ui.Select):
    """Select menu для выбора категории тикета"""
    def __init__(self, channel_id: int, guild_id: int):
        self.channel_id = channel_id
        self.guild_id = guild_id
        
        options = [
            discord.SelectOption(
                label="Жалоба",
                description="Нарушение правил, оскорбления, угрозы",
                value="sikayet"
            ),
            discord.SelectOption(
                label="Вопрос / Помощь",
                description="Общие вопросы, помощь с ботом",
                value="soru"
            ),
            discord.SelectOption(
                label="Техническая проблема",
                description="Баги, ошибки, технические вопросы",
                value="teknik"
            ),
        ]
        
        super().__init__(
            placeholder="Выберите категорию...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="ticket_category_select"
        )
    
    async def callback(self, interaction: discord.Interaction):
        category = self.values[0]
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
                '**Выбрана категория: Жалоба.**\n\n'
                'Кратко опишите, что произошло:'
            ),
            'soru': (
                '**Выбрана категория: Вопрос/Помощь.**\n\n'
                'Чем я могу помочь? Какую информацию вы хотите получить?\n'
                '> Панель, регистрация, команды, роли, экономика, уровни...'
            ),
            'teknik': (
                '**Выбрана категория: Техническая проблема.**\n\n'
                'Чем я могу помочь? С какой проблемой вы столкнулись?\n'
                '> Бот, музыка, команда не работает, текст ошибки...'
            ),
        }

        hint = category_hints.get(category, 'Чем я могу помочь?')
        e = discord.Embed(description=hint, color=0x00D9FF)
        await interaction.response.send_message(embed=e)
        
        # Отключить select menu после выбора
        self.disabled = True
        await interaction.message.edit(view=self.view)


class TicketCategoryView(discord.ui.View):
    """View с select menu для выбора категории"""
    def __init__(self, channel_id: int, guild_id: int):
        super().__init__(timeout=300)
        self.add_item(TicketCategorySelect(channel_id, guild_id))


class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Создать тикет поддержки",
        style=discord.ButtonStyle.blurple,
        custom_id="ticket_open"
    )
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        
        # На этом сервере система тикетов отключена
        if guild.id in TICKET_DISABLED_GUILDS:
            await interaction.response.send_message(
                'На этом сервере система тикетов отключена.', ephemeral=True
            )
            return
        
        existing = discord.utils.get(guild.text_channels, name=f"ticket-{interaction.user.name.lower()}")
        if existing:
            await interaction.response.send_message(
                f"У вас уже есть открытый тикет: {existing.mention}\nПожалуйста, сначала закройте его.",
                ephemeral=True
            )
            return
        
        #  RATE LIMIT CHECK 
        rate_limiter = get_rate_limiter()
        rate_check = await rate_limiter.check_ticket_limit(guild.id, interaction.user.id)
        if not rate_check.allowed:
            logger.warning(
                f"[RateLimit] Отказано в создании тикета: user={interaction.user} "
                f"({interaction.user.id}) reason={rate_check.reason}"
            )
            # Красивый embed с информацией о rate limit
            rl_embed = discord.Embed(
                color=0xE74C3C,
                timestamp=datetime.datetime.utcnow()
            )
            rl_embed.description = (
                f"## Ограничение на создание тикетов\n"
                f"\n\n"
                f"**Причина:** {rate_check.reason}\n\n"
            )
            if rate_check.wait_seconds > 0:
                # Конвертировать секунды в читаемый формат
                if rate_check.wait_seconds >= 3600:
                    wait_str = f"{rate_check.wait_seconds // 3600} ч. {(rate_check.wait_seconds % 3600) // 60} мин."
                elif rate_check.wait_seconds >= 60:
                    wait_str = f"{rate_check.wait_seconds // 60} мин. {rate_check.wait_seconds % 60} сек."
                else:
                    wait_str = f"{rate_check.wait_seconds} сек."
                rl_embed.description += f"**Подождите:** {wait_str}\n"
            
            rl_embed.description += (
                f"**Осталось тикетов:** {rate_check.remaining}/{rate_check.limit} (за 24 часа)\n\n"
                f""
            )
            rl_embed.set_footer(text="Защита от спама")
            await interaction.response.send_message(embed=rl_embed, ephemeral=True)
            return
        #  END RATE LIMIT CHECK 
        
        # Пауза перед отправкой ответа (правило 3 секунды Discord)
        await interaction.response.send_message(
            "Канал тикета создаётся...",
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

        # Встроенное приветствие в канале — стиль карточки (Custom Menu)
        e = TicketMenu.welcome(
            user=interaction.user,
            guild=guild,
            channel=channel
        )

        await channel.send(
            content=f"{interaction.user.mention}" + (f" | {support_role.mention}" if support_role else ""),
            embed=e,
            view=CloseTicketView()
        )
        
        # Отправить приветственное сообщение от AI
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

        # Отправить DM пользователю
        try:
            dm_e = discord.Embed(color=0x5865F2, timestamp=datetime.datetime.utcnow())
            dm_e.description = (
                f"## Тикет создан\n"
                f"### Ваш запрос принят\n"
                f"\n\n"
                f"**Сервер:** {guild.name}\n"
                f"**Канал:** {channel.mention}\n"
                f"**Создан:** <t:{ts}:R>\n\n"
                f"Опишите проблему как можно подробнее для быстрого решения.\n\n"
                f""
            )
            dm_e.set_thumbnail(url=guild.icon.url if guild.icon else None)
            if guild.icon:
                dm_e.set_footer(text=f"{guild.name} · Поддержка", icon_url=guild.icon.url)
            else:
                dm_e.set_footer(text=f"{guild.name} · Поддержка")
            await interaction.user.send(embed=dm_e)
        except discord.Forbidden:
            pass

        #  RATE LIMIT: Записать создание тикета 
        try:
            await rate_limiter.record_ticket_creation(guild.id, interaction.user.id)
            logger.info(
                f"[RateLimit] Тикет создан: user={interaction.user} ({interaction.user.id}) "
                f"remaining={rate_check.remaining}/{rate_check.limit}"
            )
        except Exception as _rl_err:
            logger.error(f"[RateLimit] Ошибка записи: {_rl_err}")
        #  END RATE LIMIT RECORD 

        # Отправить followup сообщение (response уже отправлен)
        await interaction.followup.send(
            f"Канал тикета создан: {channel.mention}",
            ephemeral=True
        )


class FeedbackModal(discord.ui.Modal, title="Обратная связь"):
    """Модальное окно для ввода отзыва"""
    feedback_text = discord.ui.TextInput(
        label="Ваш отзыв (необязательно)",
        style=discord.TextStyle.paragraph,
        placeholder="Расскажите, что можно улучшить...",
        required=False,
        max_length=500
    )
    
    def __init__(self, ticket_channel: str, rating: str):
        super().__init__()
        self.ticket_channel = ticket_channel
        self.rating = rating
    
    async def on_submit(self, interaction: discord.Interaction):
        """Обработка отправки формы"""
        feedback_service = get_feedback_service()
        feedback_service.add_feedback(
            guild_id=interaction.guild.id,
            user_id=interaction.user.id,
            ticket_channel=self.ticket_channel,
            rating=self.rating,
            comment=self.feedback_text.value if self.feedback_text.value else None
        )
        
        embed = discord.Embed(
            title="Спасибо за отзыв!",
            description="Ваше мнение очень важно для нас и поможет улучшить качество поддержки.",
            color=0x2ECC71
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class FeedbackView(discord.ui.View):
    """Представление для сбора обратной связи"""
    def __init__(self, ticket_channel: str):
        super().__init__(timeout=300)  # 5 минут
        self.ticket_channel = ticket_channel
    
    @discord.ui.button(label=" Хорошо", style=discord.ButtonStyle.success, custom_id="feedback_positive")
    async def positive_feedback(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Положительный отзыв"""
        feedback_service = get_feedback_service()
        feedback_service.add_feedback(
            guild_id=interaction.guild.id,
            user_id=interaction.user.id,
            ticket_channel=self.ticket_channel,
            rating='positive'
        )
        
        embed = discord.Embed(
            title="Спасибо за отзыв!",
            description="Рады, что вам понравилось! Если есть предложения — нажмите кнопку ниже.",
            color=0x2ECC71
        )
        
        # Предлагаем оставить комментарий
        comment_view = discord.ui.View(timeout=60)
        comment_button = discord.ui.Button(
            label=" Оставить комментарий",
            style=discord.ButtonStyle.primary,
            custom_id="add_comment"
        )
        
        async def comment_callback(btn_interaction: discord.Interaction):
            modal = FeedbackModal(self.ticket_channel, 'positive')
            await btn_interaction.response.send_modal(modal)
        
        comment_button.callback = comment_callback
        comment_view.add_item(comment_button)
        
        await interaction.response.send_message(embed=embed, view=comment_view, ephemeral=True)
        
        # Отключить кнопки
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)
    
    @discord.ui.button(label=" Плохо", style=discord.ButtonStyle.danger, custom_id="feedback_negative")
    async def negative_feedback(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Отрицательный отзыв"""
        # Сразу показать модальное окно для комментария
        modal = FeedbackModal(self.ticket_channel, 'negative')
        await interaction.response.send_modal(modal)
        
        # Отключить кнопки
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)


class AILearnModal(discord.ui.Modal, title="🧠 Обучение ИИ Аэйтера"):
    err_input = discord.ui.TextInput(
        label="В чем ошибся ИИ?",
        placeholder="Например: ИИ не заметил провокацию со стороны заявителя...",
        style=discord.TextStyle.paragraph,
        required=True
    )
    corr_input = discord.ui.TextInput(
        label="Каким должно быть правильное решение?",
        placeholder="Например: выдать обоюдный мут или отклонить жалобу...",
        style=discord.TextStyle.paragraph,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            import cogs.ai_chat as ai_mod
            guild_key = str(interaction.guild_id)
            if guild_key not in ai_mod._knowledge_base:
                ai_mod._knowledge_base[guild_key] = []
            ai_mod._knowledge_base[guild_key].append({
                'type': 'admin_correction',
                'question': f"Ошибка модерации: {self.err_input.value}",
                'info': f"Правильное правило от админа: {self.corr_input.value}",
                'confidence': 'high',
                'source': 'admin_correction'
            })
            ai_mod._save_knowledge_base(ai_mod._knowledge_base)
            from cogs._ai_card import generate_ai_dialogue_bytes
            img_buf = await interaction.client.loop.run_in_executor(
                None,
                generate_ai_dialogue_bytes,
                "Спасибо, Администратор! Я сохранил ваше исправление в базу знаний. Мои алгоритмы прокачаны и больше не допустят эту ошибку!",
                self.err_input.value,
                "solution"
            )
            file = discord.File(img_buf, filename="gojo_dialogue.png")
            await interaction.channel.send(file=file)
        except Exception as e:
            await interaction.followup.send(f"Ошибка сохранения обучения ИИ: {e}", ephemeral=True)


class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Закрыть тикет",
        style=discord.ButtonStyle.red,
        custom_id="ticket_close"
    )
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        if not channel.name.startswith("ticket-"):
            await interaction.response.send_message("Это не канал тикета.", ephemeral=True)
            return

        cog = interaction.client.get_cog('Ticket')
        if cog:
            state = cog._get_ticket_state(interaction.guild.id, channel.id)
            if state.get('admin_only_close'):
                is_admin = interaction.user.guild_permissions.administrator or interaction.user.guild_permissions.manage_guild
                if not is_admin:
                    await interaction.response.send_message(
                        "❌ Этот тикет находится под контролем администрации. Только администратор может закрыть его!",
                        ephemeral=True
                    )
                    return
            cog._delete_ticket_state(interaction.guild.id, channel.id)

    @discord.ui.button(
        label="🧠 Обучить ИИ / Указать ошибку",
        style=discord.ButtonStyle.blurple,
        custom_id="ticket_ai_feedback_btn"
    )
    async def ai_feedback_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        is_admin = interaction.user.guild_permissions.administrator or interaction.user.guild_permissions.manage_guild
        if not is_admin:
            await interaction.response.send_message("❌ Только администратор может обучать ИИ и указывать на ошибки!", ephemeral=True)
            return
        await interaction.response.send_modal(AILearnModal())

        # Очистить состояние AI
        cog = interaction.client.get_cog('Ticket')
        if cog:
            cog._delete_ticket_state(interaction.guild.id, channel.id)

        messages = []
        async for msg in channel.history(limit=200, oldest_first=True):
            if not msg.author.bot:
                messages.append(f"[{msg.created_at.strftime('%d.%m.%Y %H:%M:%S')}] {msg.author.display_name}: {msg.content}")
        transcript = "\n".join(messages) if messages else "Сообщения не найдены."

        owner_id = None
        if channel.topic and "Ticket sahibi:" in channel.topic:
            try:
                owner_id = int(channel.topic.split("Ticket sahibi:")[-1].strip())
            except Exception:
                pass

        ts = int(datetime.datetime.utcnow().timestamp())

        log_ch = discord.utils.get(interaction.guild.text_channels, name="ticket-log")
        if log_ch:
            log_e = discord.Embed(color=0xE74C3C, timestamp=datetime.datetime.utcnow())
            log_e.description = (
                f"## Тикет закрыт\n"
                f"### {channel.name}\n"
                f"\n\n"
                f"**Закрыл:** {interaction.user.mention}\n"
                f"**Дата:** <t:{ts}:F>\n"
                f"**Сообщений:** {len(messages)}\n\n"
                f""
            )
            if interaction.guild.icon:
                log_e.set_footer(text=f"{interaction.guild.name} · Логи", icon_url=interaction.guild.icon.url)
            else:
                log_e.set_footer(text=f"{interaction.guild.name} · Логи")
            file = discord.File(fp=io.StringIO(transcript), filename=f"{channel.name}_transcript.txt")
            await log_ch.send(embed=log_e, file=file)

        if owner_id:
            try:
                owner = await interaction.guild.fetch_member(owner_id)
                dm_e = discord.Embed(color=0xE74C3C, timestamp=datetime.datetime.utcnow())
                dm_e.description = (
                    f"## Тикет закрыт\n"
                    f"### Ваш запрос завершён\n"
                    f"\n\n"
                    f"**Сервер:** {interaction.guild.name}\n"
                    f"**Закрыл:** {interaction.user.display_name}\n"
                    f"**Закрыт:** <t:{ts}:R>\n"
                    f"**Сообщений:** {len(messages)}\n\n"
                    f"Если у вас возникнут новые вопросы — создайте новый тикет.\n\n"
                    f""
                )
                dm_e.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
                if interaction.guild.icon:
                    dm_e.set_footer(text=f"{interaction.guild.name} · Поддержка", icon_url=interaction.guild.icon.url)
                else:
                    dm_e.set_footer(text=f"{interaction.guild.name} · Поддержка")
                await owner.send(embed=dm_e)
            except Exception:
                pass

        #  FEEDBACK СИСТЕМА 
        # Показать форму обратной связи перед удалением канала
        feedback_embed = discord.Embed(
            title="Оцените качество поддержки",
            description=(
                "Пожалуйста, оцените работу нашей службы поддержки.\n"
                "Ваше мнение поможет нам стать лучше!"
            ),
            color=0xF39C12,
            timestamp=datetime.datetime.utcnow()
        )
        feedback_embed.set_footer(text="Тикет будет удалён через 30 секунд")
        
        await interaction.response.send_message(
            embed=feedback_embed,
            view=FeedbackView(channel.name)
        )
        
        # Подождать 30 секунд для сбора обратной связи
        await asyncio.sleep(30)
        #  END FEEDBACK СИСТЕМА 
        
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
        """Записать наказание в глобальный файл штрафов"""
        try:
            _penalty_file = 'data/ticket_penalties.json'
            _penalties = {}
            if os.path.exists(_penalty_file):
                with open(_penalty_file, 'r', encoding='utf-8') as _f:
                    _penalties = json.load(_f)
            
            # Новый формат: список как хранение (история наказаний)
            guild_str = str(guild_id)
            user_str = str(user_id)
            
            if guild_str not in _penalties:
                _penalties[guild_str] = {}
            if user_str not in _penalties[guild_str]:
                _penalties[guild_str][user_str] = []
            
            # Добавить запись о наказании
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
            log.info(f'[TICKET] Ошибка записи наказания: {_pe}')
    
    def _get_penalty_history(self, guild_id: int, user_id: int, days: int = 7) -> list:
        """В конец X день в наказание историю getir"""
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
                except Exception:
                    pass
            
            return recent
        except Exception as e:
            log.info(f'[TICKET] Penalty history Ошибки: {e}')
            return []
    
    def _calculate_penalty_duration(self, guild_id: int, user_id: int, base_duration: int) -> int:
        """История наказание по длительность hesapla (graduation)"""
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
        """Рассчитать уровень доверия к решению AI (0–100)"""
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

    def _load_ai_data(self, guild_id: int) -> dict:
        """Загрузить данные AI-тикетов"""
        path = self._get_ai_data_path(guild_id)
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                # Повреждённый JSON — создать резервную копию и сбросить
                import shutil
                shutil.copy(path, path + '.bak')
                log.info(f'[TICKET] Резервная копия повреждённого JSON создана: {path}')
                return {}
            except Exception as e:
                log.info(f'[TICKET] Ошибка загрузки данных: {e}')
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
            log.info(f'[TICKET] Ошибка сохранения данных: {e}')

    def _get_ticket_state(self, guild_id: int, channel_id: int) -> dict:
        """Получить состояние тикета"""
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
        """Слушать сообщения в каналах тикетов и отвечать с помощью AI"""
        if message.author.bot:
            return
        if not message.channel.name.startswith("ticket-"):
            return
        if not AI_ENABLED:
            return

        guild_id = message.guild.id
        channel_id = message.channel.id
        state = self._get_ticket_state(guild_id, channel_id)

        # Staff отправил сообщение — остановить AI
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
                    log.info(f"FAQ learn error: {e}")
            return

        if state['status'] == 'staff_handling':
            return
        if state['status'] == 'escalated':
            return
        if state['ai_message_count'] >= MAX_AI_MESSAGES:
            await self._escalate_ticket(message.channel, state, 'max_messages')
            return
        # Если анализ продолжается — не предпринимать действий с новым сообщением
        if state.get('analyzing'):
            return

        #  ЖАЛОБА STATE MACHINE 
        complaint = state.get('complaint', {})
        if complaint.get('active'):
            await self._handle_complaint_flow(message, state, guild_id, channel_id, complaint)
            return

        #  СИСТЕМА ДОПОЛНИТЕЛЬНЫХ ДОКАЗАТЕЛЬСТВ 
        if state.get('waiting_for_evidence'):
            content_lower = message.content.lower().strip()
            if content_lower in ('да', 'д', 'yes', 'ага', 'есть'):
                state['waiting_for_evidence'] = False
                state['adding_evidence'] = True
                self._save_ticket_state(guild_id, channel_id, state)
                await message.channel.send(
                    " **Режим добавления доказательств активирован!**\n\n"
                    "Пожалуйста, отправьте дополнительные доказательства сюда:\n"
                    "• Скриншоты (изображения)\n"
                    "• Дополнительные сообщения (скопировать-вставить)\n"
                    "• Скриншоты из ЛС\n\n"
                    "Когда закончите, напишите **'готово'**."
                )
            elif content_lower in ('нет', 'н', 'no', 'неа', 'не'):
                state['waiting_for_evidence'] = False
                state['complaint'] = {}
                self._save_ticket_state(guild_id, channel_id, state)
                await message.channel.send("Понятно. Могу ли я помочь чем-то ещё?")
            # else: Ждать, повторить вопрос
            return  # ← Остановиться здесь, не переходить к обычному потоку AI
        
        # Режим сбора дополнительных доказательств
        if state.get('adding_evidence'):
            content_lower = message.content.lower().strip()
            if content_lower in ('готово', 'готова', 'готово!', 'готова!', 'хватит', 'всё', 'все'):
                state['adding_evidence'] = False
                complaint = state.get('complaint', {})
                self._save_ticket_state(guild_id, channel_id, state)
                if not complaint:
                    await message.channel.send("Информация о жалобе не найдена.")
                    return
                await message.channel.send("Дополнительные доказательства получены. Повторный анализ...")
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
                    complaint['messages'].append(f"[ДОП. ДОКАЗАТЕЛЬСТВО]: {evidence_text[:300]}")
                    state['complaint'] = complaint
                self._save_ticket_state(guild_id, channel_id, state)
                await message.add_reaction("")
            return  # ← Остановиться здесь, не переходить к обычному потоку AI

        #  СИСТЕМА АПЕЛЛЯЦИИ 
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
                        "Апелляция уже использована. Повторно подать апелляцию нельзя.\n"
                        "Передаю администрации."
                    )
                    await self._escalate_ticket(message.channel, state, 'appeal_rejected')
                    return
                
                state['appeal_used'] = True
                state['appeal_reason'] = message.content
                self._save_ticket_state(guild_id, channel_id, state)
                
                await message.channel.send(
                    f"**Апелляция принята!**\n\n"
                    f"Последнее наказание: **{last_penalty['reason']}** ({last_penalty['duration']} мин.)\n"
                    f"Причина апелляции: {message.content[:200]}\n\n"
                    "Апелляция повторно рассматривается AI..."
                )
                
                # Апелляция AI'ya отправить
                await self._handle_appeal(message.channel, state, guild_id, channel_id, last_penalty)
                return

        # Ключевые слова жалобы — срабатывают только при открытии тикета
        # ПРИМЕЧАНИЕ: кнопка жалобы уже сразу запускает поток, ключевое слово — только резервный триггер
        sikayet_keywords = ['sikayet', 'жалоба', 'kufur', 'мат', 'оскорбление',
                            'tehdit', 'taciz', 'bully', 'zorba', 'rahatsiz', 'rahatsız']
        # Если есть вопросительные слова — не запускать поток жалобы
        question_keywords = ['как', 'что', 'что такое', 'почему', 'как работает',
                           'о', 'расскажи', 'объясни', 'опиши']
        content = message.content.lower()
        is_question = any(kw in content for kw in question_keywords)
        # Если категория уже выбрана — пропустить триггер по ключевым словам
        category_selected = state.get('category') is not None
        if any(kw in content for kw in sikayet_keywords) and not is_question and not category_selected:
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
            await message.channel.send(" Кратко опишите, что произошло:")
            return

        #  ЗАПРОС АДМИНИСТРАТОРА 
        admin_keywords = ['поговорить с админом', 'позвать админа', 'позовите админа',
                         'позвать модератора', 'связаться с администрацией',
                         'хочу администратора', 'вызовите модератора',
                         'нужен модератор', 'нужен админ']
        if any(kw in message.content.lower() for kw in admin_keywords):
            support_role = discord.utils.get(message.guild.roles, name=SUPPORT_ROLE_NAME)
            mention = support_role.mention if support_role else '@Поддержка'
            await message.channel.send(
                f'{mention} — {message.author.mention} хочет связаться с вами.'
            )
            state['status'] = 'staff_handling'
            self._save_ticket_state(guild_id, channel_id, state)
            return

        #  NORMAL AI AKIŞI 
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

                # Добавить историю прошлых тикетов пользователя
                try:
                    all_tickets = self._load_ai_data(guild_id)
                    past_tickets = []
                    user_id_str = str(state.get('user_id', ''))
                    for ch_id, t in all_tickets.items():
                        if str(ch_id) == str(channel_id):
                            continue  # Пропустить текущий тикет
                        if str(t.get('user_id', '')) == user_id_str and t.get('history'):
                            # Взять сводку из последнего тикета
                            last_msgs = [h['content'] for h in t['history'][-3:] if h.get('role') == 'user']
                            if last_msgs:
                                past_tickets.append(f"Назад ticket: {' | '.join(last_msgs[:2])}")
                    if past_tickets:
                        guild_context['past_tickets'] = past_tickets[-3:]  # Последние 3 тикета
                except Exception:
                    pass

                full_message = message.content
                response, should_escalate, escalation_category, updated_history, detected_category = await ai_ticket_response(
                    full_message, state['history'], guild_context
                )
                actions = parse_ai_actions(response)

                # Обрабатываем действия
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
                
                # Если у пользователя есть предупреждения
                if guild_context.get('user_id'):
                    try:
                        from cogs.warnings import load_warnings
                        warnings_data = load_warnings()
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
                    except Exception:
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
                                    await interaction.followup.send(f"{target_user.mention} забанен", ephemeral=True)
                                elif data['action'] == 'mute':
                                    until = discord.utils.utcnow() + timedelta(minutes=data['duration'])
                                    await target_user.timeout(until, reason=f"AI рекомендация: {data['reason']}")
                                    await interaction.followup.send(f"{target_user.mention} заглушён на {data['duration']} мин", ephemeral=True)
                            
                            button = discord.ui.Button(
                                label=action_data['label'],
                                style=discord.ButtonStyle.danger if action_data['action'] == 'ban' else discord.ButtonStyle.primary
                            )
                            button.callback = action_callback
                            view.add_item(button)
                        
                        await message.channel.send(clean_response, view=view)
                    else:
                        await message.channel.send(clean_response)
                
                self._save_ticket_state(guild_id, channel_id, state)

            except Exception as e:
                log.info(f"Ошибка AI-модератора: {e}")
                import traceback
                traceback.print_exc()
                await self._escalate_ticket(message.channel, state, 'ai_error')
                self._save_ticket_state(guild_id, channel_id, state)

    async def _handle_appeal(self, channel, state, guild_id, channel_id, penalty):
        """Апелляция AI с значение"""
        from web.ai_helper import _call_text
        
        appeal_reason = state.get('appeal_reason', '')
        
        prompt = f"""Пользователь подаёт апелляцию на решение AI-модератора.

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

        log.info(f"[APPEAL] verdict: {verdict!r}")

        verdict_upper = verdict.strip().upper()

        if 'KABUL' in verdict_upper:
            await channel.send(
                "**Апелляция принята!**\n\n"
                "Решение AI пересмотрено, выявлена несправедливость.\n"
                "Наказание будет снято. Передаю администрации."
            )
            await self._escalate_ticket(channel, state, 'appeal_accepted')
        elif 'RED' in verdict_upper:
            await channel.send(
                "**Апелляция отклонена.**\n\n"
                "Решение AI пересмотрено и подтверждено как верное.\n"
                "Наказание остаётся в силе."
            )
        else:  # НЕОПРЕДЕЛЁННО
            await channel.send(
                " **Апелляция неясна.**\n\n"
                "Ситуация не имеет однозначного решения, передаю администрации."
            )
            await self._escalate_ticket(channel, state, 'appeal_unclear')

        self._save_ticket_state(guild_id, channel_id, state)

    async def _handle_complaint_flow(self, message, state, guild_id, channel_id, complaint):
        """Управление потоком жалобы — пошагово"""
        content = message.content.strip()
        step = complaint.get('step')

        if step == 'ask_description':
            complaint['description'] = content
            complaint['step'] = 'ask_type'
            state['ai_message_count'] += 1
            self._save_ticket_state(guild_id, channel_id, state)
            await message.channel.send(
                "Жалоба принята. Какого рода проблема возникла?\n"
                "**1** — Мат / Оскорбление\n**2** — Угроза\n**3** — Травля / Насмешка\n**4** — Другое"
            )
            return

        if step == 'ask_type':
            type_map = {'1': 'kufur', '2': 'tehdit', '3': 'zorbalik', '4': 'diger'}
            complaint['type'] = type_map.get(content, 'diger')
            complaint['step'] = 'ask_accused'
            state['ai_message_count'] += 1

            # При выборе "Другое" — сразу передать модераторам
            if complaint['type'] == 'diger':
                state['complaint'] = {}
                self._save_ticket_state(guild_id, channel_id, state)
                await message.channel.send(" Передаю администрации. Ваше обращение будет рассмотрено в кратчайшие сроки.")
                await self._escalate_ticket(message.channel, state, 'diger')
                return

            self._save_ticket_state(guild_id, channel_id, state)
            await message.channel.send(" Введите Discord ID пользователя, на которого жалуетесь:")
            return

        if step == 'ask_accused':
            accused_id = content.strip()
            # Проверка ID — принимаем упоминание, числовой ID или имя
            import re as _re
            mention_match = _re.search(r'<@!?(\d+)>', accused_id)
            if mention_match:
                accused_id = mention_match.group(1)
            elif not accused_id.isdigit():
                # Поиск пользователя по имени
                found = discord.utils.find(
                    lambda m: m.display_name.lower() == accused_id.lower() or m.name.lower() == accused_id.lower(),
                    message.guild.members
                )
                if found:
                    accused_id = str(found.id)
                else:
                    await message.channel.send(
                        "Пользователь не найден. Пожалуйста, введите Discord ID (17–19 цифр) или @упоминание:"
                    )
                    return
            complaint['accused_id'] = accused_id
            complaint['step'] = 'ask_channel'
            state['ai_message_count'] += 1
            self._save_ticket_state(guild_id, channel_id, state)
            await message.channel.send(
                " В каком канале произошёл инцидент? Введите ID канала.\n"
                "*(Чтобы узнать ID канала: правый клик на канал → Копировать ID)*"
            )
            return

        if step == 'ask_channel':
            complaint['channel_id'] = content.strip()
            complaint['step'] = 'ask_messages'
            state['ai_message_count'] += 1
            self._save_ticket_state(guild_id, channel_id, state)

            # Если ID канала — число, автоматически сканировать сообщения
            if content.strip().isdigit():
                #  PROGRESS INDICATOR 
                progress_msg = await message.channel.send(
                    "**Сканирование сообщений...**\n\n"
                    "```[] 0%```\n"
                    "Пожалуйста, подождите..."
                )
                #  END PROGRESS INDICATOR 
                
                try:
                    target_ch = message.guild.get_channel(int(content.strip()))
                    if target_ch:
                        accused_id_str = complaint.get('accused_id', '')
                        accused_id_int = int(accused_id_str) if accused_id_str.isdigit() else None
                        complainant_id_int = state.get('user_id')

                        # Найти имя подавшего жалобу
                        complainant_member = message.guild.get_member(complainant_id_int) if complainant_id_int else None
                        complainant_name = complainant_member.display_name if complainant_member else str(complainant_id_int)

                        # Найти имя обвиняемого
                        accused_member = message.guild.get_member(accused_id_int) if accused_id_int else None
                        accused_name = accused_member.display_name if accused_member else str(accused_id_int)

                        msgs = []
                        all_msgs_raw = []
                        # В конец 1000 сообщение сканировать
                        total_scanned = 0
                        async for msg in target_ch.history(limit=1000, oldest_first=False):
                            if msg.author.bot:
                                continue
                            all_msgs_raw.append(msg)
                            total_scanned += 1
                            
                            #  PROGRESS UPDATE 
                            if total_scanned % 100 == 0:
                                percent = min(100, int((total_scanned / 1000) * 100))
                                filled = int(percent / 5)
                                bar = "" * filled + "" * (20 - filled)
                                try:
                                    await progress_msg.edit(
                                        content=(
                                            f"**Сканирование сообщений...**\n\n"
                                            f"```[{bar}] {percent}%```\n"
                                            f"Обработано: {total_scanned} сообщений"
                                        )
                                    )
                                except Exception:
                                    pass
                            #  END PROGRESS UPDATE 

                        # От старых к новым
                        all_msgs_raw.reverse()

                        # Собрать сообщения обеих сторон
                        accused_msgs_set = set()
                        complainant_msgs_set = set()

                        for i, msg in enumerate(all_msgs_raw):
                            is_accused = accused_id_int and msg.author.id == accused_id_int
                            is_complainant = complainant_id_int and msg.author.id == complainant_id_int
                            if not (is_accused or is_complainant):
                                continue

                            # Есть ли собеседник в ближайшем окне сообщений?
                            window_start = max(0, i - 15)
                            window_end = min(len(all_msgs_raw), i + 16)
                            other_id = complainant_id_int if is_accused else accused_id_int
                            near_other = any(
                                all_msgs_raw[j].author.id == other_id
                                for j in range(window_start, window_end) if j != i
                            )

                            # Прямое упоминание / ответ
                            is_mention = other_id and any(m.id == other_id for m in msg.mentions)
                            is_reply = False
                            if msg.reference and msg.reference.resolved:
                                ref = msg.reference.resolved
                                if hasattr(ref, 'author') and other_id:
                                    is_reply = ref.author.id == other_id

                            if not (is_mention or is_reply or near_other):
                                continue

                            tag = ' ПРЯМОЕ' if (is_mention or is_reply) else ' КОНТЕКСТ'
                            label = 'ОБВИНЯЕМЫЙ' if is_accused else 'ЗАЯВИТЕЛЬ'
                            line = (
                                f"[{msg.created_at.strftime('%d.%m %H:%M')}] "
                                f"[{label}: {msg.author.display_name}] {tag}: "
                                f"{msg.content[:300]}"
                            )
                            if is_accused:
                                accused_msgs_set.add(line)
                            else:
                                complainant_msgs_set.add(line)

                        # Объединить сообщения обеих сторон
                        msgs = sorted(accused_msgs_set | complainant_msgs_set)
                        
                        #  PROGRESS COMPLETE 
                        try:
                            await progress_msg.edit(
                                content=(
                                    f"**Сканирование завершено!**\n\n"
                                    f"```[] 100%```\n"
                                    f"Найдено: {len(msgs)} релевантных сообщений"
                                )
                            )
                            await asyncio.sleep(1)  # Показать результат
                            await progress_msg.delete()
                        except Exception:
                            pass
                        #  END PROGRESS COMPLETE 

                        log.info(f"[TICKET] Сканирование: {len(accused_msgs_set)} сообщений обвиняемого, "
                              f"{len(complainant_msgs_set)} сообщений заявителя")

                        # Извлечь удалённые сообщения из кэша — для обеих сторон
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
                                # Всё ещё в канале?
                                still_exists = any(m.id == msg_id for m in all_msgs_raw)
                                if still_exists:
                                    continue
                                ts = cached_msg.get('timestamp', '')[:16].replace('T', ' ')
                                label = 'ОБВИНЯЕМЫЙ' if author_id == accused_id_int else 'ЗАЯВИТЕЛЬ'
                                deleted_msgs.append(
                                    f"[{ts}] [{label}: {cached_msg.get('author_name','?')}]  УДАЛЁННОЕ СООБЩЕНИЕ: "
                                    f"{cached_msg.get('content', '[Содержимое отсутствует]')[:300]}"
                                )
                        except Exception as _de:
                            log.info(f'[TICKET] Ошибка кэша удалённых сообщений: {_de}')

                        if deleted_msgs:
                            msgs.extend(deleted_msgs)
                            await message.channel.send(
                                f"**Обнаружено {len(deleted_msgs)} удалённых сообщений** (содержимое сохранено)."
                            )

                        if msgs:
                            complaint['messages'] = msgs
                            complaint['messages_verified'] = True
                            complaint['step'] = 'analyze'
                            complaint['accused_name'] = accused_name
                            complaint['complainant_name'] = complainant_name
                            self._save_ticket_state(guild_id, channel_id, state)
                            await message.channel.send(
                                f"**Найдено {len(msgs)} сообщений.** Начинаю анализ..."
                            )
                            await self._analyze_complaint(message.channel, state, guild_id, channel_id, complaint)
                            return
                        else:
                            await message.channel.send(
                                f"В канале **{target_ch.mention}** сообщения между **{accused_name}** и **{complainant_name}** не найдены.\n\n"
                                "Скопируйте и вставьте сюда сообщения этого пользователя:"
                            )
                            complaint['messages_verified'] = False
                            complaint['step'] = 'ask_messages'
                            self._save_ticket_state(guild_id, channel_id, state)
                            return
                    else:
                        await message.channel.send(
                            "Канал не найден. Скопируйте и вставьте сюда сообщения этого пользователя:"
                        )
                        complaint['step'] = 'ask_messages'
                        self._save_ticket_state(guild_id, channel_id, state)
                        return
                except Exception as e:
                    log.info(f"[TICKET] Channel scan error: {e}")
                    await message.channel.send(
                        "Ошибка при сканировании канала. Скопируйте и вставьте сообщения вручную:"
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
            # Если имён нет — добавить сейчас
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
            if content.lower() in ('да', 'д', 'yes', 'ага'):
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
        """Глубокий анализ жалобы с проверкой"""
        from web.complaint_analyzer import ComplaintAnalyzer
        
        # Создал analizör
        analyzer = ComplaintAnalyzer(self.bot)
        
        # Получаем ID заявителя и обвиняемого
        complainant_id = state.get('user_id')
        accused_id = complaint.get('accused_id')
        
        if not complainant_id or not accused_id:
            await channel.send("Не удалось определить участников жалобы.")
            state['complaint'] = {}
            state['analyzing'] = False
            self._save_ticket_state(guild_id, channel_id, state)
            return
        
        # Преобразуем в int, если необходимо
        try:
            complainant_id = int(complainant_id)
            accused_id = int(accused_id) if str(accused_id).isdigit() else None
        except Exception:
            await channel.send("Некорректный ID пользователя.")
            state['complaint'] = {}
            state['analyzing'] = False
            self._save_ticket_state(guild_id, channel_id, state)
            return
        
        if not accused_id:
            await channel.send("Не удалось определить ID обвиняемого.")
            state['complaint'] = {}
            state['analyzing'] = False
            self._save_ticket_state(guild_id, channel_id, state)
            return
        
        # Получаем текст жалобы и сообщения
        complaint_text = complaint.get('description', '')
        provided_messages = complaint.get('messages', [])
        
        # Запускаем анализ
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
                log.info(f"[COMPLAINT] Ошибка analiza: {e}")
                import traceback
                traceback.print_exc()
                await channel.send("Произошла ошибка при анализе жалобы. Передаю модератору.")
                await self._escalate_ticket(channel, state, 'ai_error')
                return
        
        # Получаем результат анализа
        verdict = result['verdict']
        confidence = result['confidence']
        severity = result['severity']
        recommendation = result['recommendation']
        analysis_text = result['analysis']
        evidence = result['evidence']

        log.info(f"[COMPLAINT] verdict={verdict}, confidence={confidence}, severity={severity}")

        # Получаем профили для embed (analyzer уже импортирован на строке 1146)
        complainant_info = await analyzer._get_user_profile(channel.guild, complainant_id)
        accused_info = await analyzer._get_user_profile(channel.guild, accused_id)

        # Формируем embed-сообщение
        try:
            embed = analyzer._form_embed(
                verdict=verdict,
                confidence=confidence,
                severity=severity,
                evidence=evidence,
                recommendation=recommendation,
                complainant_info=complainant_info,
                accused_info=accused_info,
            )
        except Exception as _ee:
            log.info(f"[COMPLAINT] embed build error: {_ee}")
            embed = None

        # Если уверенность низкая — передать модератору (без наказания)
        if confidence < 50:
            from cogs._ai_card import generate_ai_dialogue_bytes
            low_text = f"Уверенность анализа слишком низкая ({confidence}%). Автоматическое наказание отменено, тикет передан модератору для проверки."
            img_buf = await self.bot.loop.run_in_executor(
                None, generate_ai_dialogue_bytes, low_text, "", "investigate"
            )
            file = discord.File(img_buf, filename="gojo_dialogue.png")
            await channel.send(file=file)
            await self._escalate_ticket(channel, state, 'low_confidence')
            state['complaint'] = {}
            state['analyzing'] = False
            self._save_ticket_state(guild_id, channel_id, state)
            return

        # Отправляем карточку визуальной новеллы Годжо с анализом (БЕЗ текста снизу)
        from cogs._ai_card import generate_ai_dialogue_bytes
        dialogue_text = f"ВЕРДИКТ ИИ ({confidence}%): {verdict}\n\n{analysis_text[:300]}"
        img_buf = await self.bot.loop.run_in_executor(
            None, generate_ai_dialogue_bytes, dialogue_text, "", "verdict"
        )
        file = discord.File(img_buf, filename="gojo_dialogue.png")
        await channel.send(file=file)
        
        # Применяем рекомендацию на основе вердикта
        action = recommendation['action']
        duration = recommendation['duration']
        reason = recommendation['reason']
        
        guild = channel.guild
        
        # Получаем участников
        complainant = guild.get_member(complainant_id)
        accused = guild.get_member(accused_id)
        
        # Определяем, кто виноват на основе вердикта
        verdict_upper = verdict.upper()
        
        # Функция для применения наказания к пользователю
        async def apply_punishment(target, target_name, action_type, dur, punishment_reason):
            if not target:
                return
            
            try:
                if action_type in ('BAN', 'KICK'):
                    # Для бана и кика — не наказываем сразу, а отправляем админам и блокируем тикет для обычного закрытия
                    state['admin_only_close'] = True
                    state['status'] = 'escalated'
                    self._save_ticket_state(guild_id, channel_id, state)
                    alert_text = f"РЕКОМЕНДАЦИЯ ИИ: {action_type} для {target.display_name}. Причина: {punishment_reason}. Решение передано администрации для проверки. Тикет заблокирован для обычного закрытия."
                    img_buf = await self.bot.loop.run_in_executor(
                        None, generate_ai_dialogue_bytes, alert_text, "", "verdict"
                    )
                    file = discord.File(img_buf, filename="gojo_dialogue.png")
                    await channel.send(file=file)
                    return
                
                elif action_type == 'MUTE' or action_type == 'TIMEOUT':
                    if dur:
                        until = discord.utils.utcnow() + timedelta(minutes=dur)
                        await target.timeout(until, reason=f"AI: {punishment_reason}")
                        hours = max(1, dur // 60)
                        success_text = f"Судебное решение выполнено. Участник {target.display_name} заглушен на {hours}ч. Причина: {punishment_reason}."
                        img_buf = await self.bot.loop.run_in_executor(
                            None, generate_ai_dialogue_bytes, success_text, "", "verdict"
                        )
                        file = discord.File(img_buf, filename="gojo_dialogue.png")
                        await channel.send(file=file)
                
                elif action_type == 'WARN':
                    from cogs.warnings import warnings
                    warnings_cog = self.bot.get_cog('warnings')
                    if warnings_cog:
                        await warnings_cog.add_warning(target, guild.me, punishment_reason)
                        success_text = f"Судебное решение выполнено. Участник {target.display_name} получил предупреждение. Причина: {punishment_reason}."
                        img_buf = await self.bot.loop.run_in_executor(
                            None, generate_ai_dialogue_bytes, success_text, "", "verdict"
                        )
                        file = discord.File(img_buf, filename="gojo_dialogue.png")
                        await channel.send(file=file)
            except Exception as e:
                log.error(f"[AI Punishment Error]: {e}")
        
        # Применяем наказание на основе вердикта
        if 'GUILTY' in verdict_upper and 'NOT' not in verdict_upper:
            await apply_punishment(accused, "обвиняемого", action, duration, reason)
        elif 'INNOCENT' in verdict_upper or 'NOT GUILTY' in verdict_upper or 'FALSE' in verdict_upper:
            false_reason = f"Ложная жалоба. {reason}"
            await apply_punishment(complainant, "заявителя", action, duration, false_reason)
        elif 'BOTH' in verdict_upper or 'MUTUAL' in verdict_upper:
            both_reason = f"Обоюдное нарушение. {reason}"
            await apply_punishment(accused, "обвиняемого", action, duration, both_reason)
            await apply_punishment(complainant, "заявителя", action, duration, both_reason)
        elif 'NO_VIOLATION' in verdict_upper or 'NO ACTION' in verdict_upper:
            img_buf = await self.bot.loop.run_in_executor(
                None, generate_ai_dialogue_bytes, "Нарушений не обнаружено. Жалоба отклонена по результатам проверки логов.", "", "solution"
            )
            file = discord.File(img_buf, filename="gojo_dialogue.png")
            await channel.send(file=file)
        else:
            await apply_punishment(accused, "обвиняемого", action, duration, reason)
        
        # Очищаем состояние
        state['complaint'] = {}
        state['analyzing'] = False
        self._save_ticket_state(guild_id, channel_id, state)
    async def _escalate_ticket(self, channel: discord.TextChannel, state: dict, reason: str):
        """Передать тикет модераторам"""
        if state['staff_notified']:
            return  # уже передан
        
        state['status'] = 'escalated'
        state['escalated_at'] = datetime.datetime.utcnow().isoformat()
        state['staff_notified'] = True
        
        # Сообщение о передаче модераторам
        e = discord.Embed(color=0xF39C12, timestamp=datetime.datetime.utcnow())
        
        reason_text = {
            'sikayet': 'Жалоба должна быть рассмотрена модератором',
            'teknik': 'Техническая проблема требует контроля модератора',
            'администратор': 'Действие требует прав модератора',
            'agir_ihlal': 'Обнаружено серьёзное нарушение, требуется контроль',
            'апелляция': 'Пользователь оспаривает решение AI',
            'ban_talebi': 'Бан может быть выдан только модератором',
            'max_messages': 'Лимит сообщений превышен, модераторы получают управление',
            'ai_error': 'Системная ошибка, модераторы получают управление',
            'diger': 'Этот вопрос должен быть рассмотрен модератором'
        }
        
        e.description = (
            f"## Передано модератору\n"
            f"\n\n"
            f"**Причина:** {reason_text.get(reason, 'Модераторы получают управление')}\n\n"
            f"Наша команда поддержки свяжется с вами в ближайшее время.\n\n"
            f""
        )
        if channel.guild.icon:
            e.set_footer(text=f"{channel.guild.name} · Модерация", icon_url=channel.guild.icon.url)
        else:
            e.set_footer(text=f"{channel.guild.name} · Модерация")
        
        await channel.send(embed=e)
        
        # Пинг роли поддержки
        support_role = discord.utils.get(channel.guild.roles, name=SUPPORT_ROLE_NAME)
        if support_role:
            await channel.send(
                f" {support_role.mention} — Новый тикет передан на рассмотрение!"
            )
        
        # Сохранить состояние
        self._save_ticket_state(channel.guild.id, channel.id, state)
    
    async def _apply_jail(self, channel: discord.TextChannel, user_id: int, duration: int, reason: str, complainant: discord.Member):
        """Применить наказание Jail от AI-модератора"""
        try:
            guild = channel.guild
            target_user = guild.get_member(user_id)
            if not target_user:
                try:
                    target_user = await guild.fetch_member(user_id)
                except Exception:
                    target_user = None
            
            if not target_user:
                await channel.send("Пользователь не найден на этом сервере.")
                return
            
            # Найти или создать роль Jail
            jail_role = discord.utils.get(guild.roles, name="Jail")
            if not jail_role:
                # Создать роль Jail
                jail_role = await guild.create_role(
                    name="Jail",
                    color=discord.Color.dark_gray(),
                    reason="AI Moderator — роль заключения"
                )
            # Запрещаем роль Jail во всех каналах
            for channel_obj in guild.channels:
                try:
                    await channel_obj.set_permissions(jail_role, send_messages=False, speak=False)
                except Exception:
                    pass

            # Выдаём роль Jail
            await target_user.add_roles(jail_role, reason=f"AI Moderator: {reason}")

            # Отправляем DM пользователю
            try:
                dm_embed = discord.Embed(color=0xE74C3C, timestamp=datetime.datetime.utcnow())
                dm_embed.description = (
                    f"## Наказание: Заключение\n"
                    f"### Вы получили заключение\n"
                    f"\n\n"
                    f"**Сервер:** {guild.name}\n"
                    f"**Длительность:** {duration} минут\n"
                    f"**Причина:** {reason}\n\n"
                    f"По окончании срока роль заключения будет автоматически снята.\n"
                    f"Если хотите оспорить — напишите в тикет.\n\n"
                    f""
                )
                if guild.icon:
                    dm_embed.set_footer(text=f"{guild.name} · Модерация", icon_url=guild.icon.url)
                else:
                    dm_embed.set_footer(text=f"{guild.name} · Модерация")
                await target_user.send(embed=dm_embed)
            except Exception:
                pass
            
            # Канал bildir
            jail_embed = discord.Embed(color=0x2ECC71, timestamp=datetime.datetime.utcnow())
            jail_embed.description = (
                f"## Заключение применено\n"
                f"### Наказание назначено\n"
                f"\n\n"
                f"**Пользователь:** {target_user.mention}\n"
                f"**Длительность:** {duration} минут\n"
                f"**Причина:** {reason}\n\n"
                f"Наша команда модераторов поможет решить проблему.\n"
                f"Если хотите оспорить — оставьте этот тикет открытым.\n\n"
                f""
            )
            if channel.guild.icon:
                jail_embed.set_footer(text=f"{channel.guild.name} · Модерация", icon_url=channel.guild.icon.url)
            else:
                jail_embed.set_footer(text=f"{channel.guild.name} · Модерация")
            await channel.send(embed=jail_embed)
            
            # Автоматически снять Jail по истечении срока (в минутах)
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
            log.info(f'[TICKET-NOTIFY] === JAIL ВЫЗОВ === target={target_user} ({target_user.id}) reason={reason[:80]}')
            try:
                await self._notify_admins_penalty(
                    guild, penalty_type='jail',
                    target=target_user, reason=reason,
                    source_channel=channel, moderator=complainant,
                )
            except Exception as _ne:
                log.info(f'[TICKET-NOTIFY] _notify_admins_penalty выбросил: {_ne}')
                import traceback as _tb
                log.info(f'[TICKET-NOTIFY] Traceback: {_tb.format_exc()[:300]}')

        except Exception as e:
            await channel.send(f"Ошибка при выдаче наказания Jail: {str(e)}")
            log.info(f"Ошибка Jail: {e}")
    
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
                    log.info(f'[TICKET] Unjail: {user} покинул сервер, роль не снята')
                    return
                except Exception as e:
                    log.info(f'[TICKET] Unjail — ошибка получения: {e}')
                    return

            # Роль Jail всё ещё существует?
            fresh_role = guild.get_role(jail_role.id)
            if not fresh_role:
                log.info(f'[TICKET] Unjail: Роль Jail удалена')
                return

            if fresh_role in fresh_member.roles:
                await fresh_member.remove_roles(fresh_role, reason="Срок заключения истёк (AI Moderator)")
                try:
                    dm_embed = discord.Embed(color=0x2ECC71, timestamp=datetime.datetime.utcnow())
                    dm_embed.description = (
                    f"## Заключение снято\n"
                    f"### Наказание завершено\n"
                        f"\n\n"
                        f"**Сервер:** {guild.name}\n\n"
                    f"Ваш срок заключения истёк. Теперь вы можете пользоваться сервером как обычно.\n"
                    f"Пожалуйста, продолжайте соблюдать правила сервера.\n\n"
                        f""
                    )
                    if guild.icon:
                        dm_embed.set_footer(text=f"{guild.name} · Модерация", icon_url=guild.icon.url)
                    else:
                        dm_embed.set_footer(text=f"{guild.name} · Модерация")
                    await fresh_member.send(embed=dm_embed)
                except Exception:
                    pass
        except Exception as e:
            log.info(f'[TICKET] Unjail — ошибка: {e}')
    
    async def _apply_warn(self, channel: discord.TextChannel, user_id: int, reason: str, moderator: discord.Member):
        """Выдать предупреждение от AI"""
        try:
            guild = channel.guild
            target_user = guild.get_member(user_id)
            if not target_user:
                try:
                    target_user = await guild.fetch_member(user_id)
                except Exception:
                    target_user = None

            if not target_user:
                await channel.send("Пользователь не найдено на на сервере.")
                return

            # Выдать предупреждение пользователю с система warnings
            from cogs.warnings import warnings
            warnings_cog = self.bot.get_cog('warnings')
            if warnings_cog:
                # Вызвать метод add_warning напрямую (без interaction)
                await warnings_cog.add_warning(target_user, moderator, reason)
                await channel.send(f"Предупреждение verildi {target_user.mention}: {reason}")
                # Уведомить администраторов
                log.info(f'[TICKET-NOTIFY] === WARN ВЫЗОВ === target={target_user} ({target_user.id}) reason={reason[:80]}')
                try:
                    await self._notify_admins_penalty(
                        guild, penalty_type='warn',
                        target=target_user, reason=reason,
                        source_channel=channel, moderator=moderator,
                    )
                except Exception as _ne:
                    log.info(f'[TICKET-NOTIFY] _notify_admins_penalty выбросил: {_ne}')
                    import traceback as _tb
                    log.info(f'[TICKET-NOTIFY] Traceback: {_tb.format_exc()[:300]}')
            else:
                await channel.send("Система предупреждений недоступна.")

        except Exception as e:
            await channel.send(f"Ошибка при выдаче предупреждения: {str(e)}")
            log.info(f"Ошибка предупреждения: {e}")

    async def _notify_admins_penalty(self, guild, *, penalty_type: str, target,
                                     reason: str, source_channel, moderator):
        """Уведомить администраторов о применённом наказании.

        Канал для уведомлений: сначала `data/ticket_notify_<guild_id>.json` →
        `notify_channel_id`, иначе первый текстовый канал с именем
        'admin-log'/'mod-log'/'логи-модерации', иначе None (тогда DM
        владельцу сервера).
        """
        import traceback
        #  ДИАГНОСТИКА: детальный print на каждом шаге 
        log.info(f'[TICKET-NOTIFY] === ВЫЗОВ УВЕДОМЛЕНИЯ ===')
        log.info(f'[TICKET-NOTIFY] guild={guild.id} ({guild.name}) type={penalty_type}')
        log.info(f'[TICKET-NOTIFY] target={target} ({getattr(target, "id", "?")}) reason={reason[:80] if reason else "(пусто)"}')
        log.info(f'[TICKET-NOTIFY] source_channel={getattr(source_channel, "id", "?")} moderator={getattr(moderator, "id", "?")}')

        notify_ch_id = None
        cfg_path = f'data/ticket_notify_{guild.id}.json'
        try:
            if os.path.exists(cfg_path):
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    notify_ch_id = (json.load(f) or {}).get('notify_channel_id')
                log.info(f'[TICKET-NOTIFY] Конфиг найден: notify_ch_id={notify_ch_id}')
            else:
                log.info(f'[TICKET-NOTIFY] Конфиг НЕ найден: {cfg_path}')
        except Exception as e:
            log.info(f'[TICKET-NOTIFY] Ошибка чтения конфига: {e}')
            notify_ch_id = None

        target_ch = None
        if notify_ch_id:
            try:
                target_ch = guild.get_channel(int(notify_ch_id))
                if not target_ch:
                    target_ch = await guild.fetch_channel(int(notify_ch_id))
                log.info(f'[TICKET-NOTIFY] Канал из конфига: {target_ch} ({getattr(target_ch, "id", "?")})')
            except Exception as e:
                log.info(f'[TICKET-NOTIFY] Ошибка получения канала по ID: {e}')
                target_ch = None
        if target_ch is None:
            # Fallback: ищем канал по имени
            tried = []
            for name in ('admin-log', 'mod-log', 'логи-модерации', 'staff-log'):
                target_ch = discord.utils.get(guild.text_channels, name=name)
                tried.append(name)
                if target_ch:
                    log.info(f'[TICKET-NOTIFY] Найден канал по имени: {name} → {target_ch.id}')
                    break
            if target_ch is None:
                log.info(f'[TICKET-NOTIFY] Ни один из каналов {tried} не найден на сервере. Доступные: {[c.name for c in guild.text_channels[:10]]}...')

        type_emoji = {
            'warn': '',
            'jail': '',
            'ban': '',
            'kick': '',
            'mute': '',
        }.get(penalty_type, '')
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
        embed.add_field(name="Пользователь", value=f"{target.mention} (`{target.id}`)", inline=False)
        embed.add_field(name="Причина", value=reason[:500] if reason else "—", inline=False)
        embed.add_field(name="Канал тикета", value=source_channel.mention if source_channel else "—", inline=True)
        embed.add_field(name="Модератор", value=moderator.mention if moderator else "AI", inline=True)
        embed.set_footer(text=f"{guild.name} • AI Moderation", icon_url=guild.icon.url if guild.icon else None)

        # Пинг админов (роли с правами administrator)
        admin_ping = ""
        try:
            admin_role = discord.utils.get(guild.roles, permissions=discord.Permissions(administrator=True))
            if admin_role:
                admin_ping = admin_role.mention + " "
                log.info(f'[TICKET-NOTIFY] Admin role для пинга: {admin_role.name} ({admin_role.id})')
            else:
                log.info(f'[TICKET-NOTIFY] Admin role не найдена (нет роли с правами admin)')
        except Exception as e:
            log.info(f'[TICKET-NOTIFY] Ошибка поиска admin role: {e}')

        sent = False
        if target_ch is not None:
            try:
                log.info(f'[TICKET-NOTIFY] Отправляю embed в #{getattr(target_ch, "name", "?")} ({target_ch.id})...')
                await target_ch.send(content=admin_ping or None, embed=embed)
                sent = True
                log.info(f'[TICKET-NOTIFY] Уведомление отправлено в канал #{target_ch.name}')
            except Exception as e:
                log.info(f'[TICKET-NOTIFY] Ошибка отправки в канал: {e}')
                log.info(f'[TICKET-NOTIFY] Traceback: {traceback.format_exc()[:300]}')
                sent = False
        if not sent:
            # Fallback: DM владельцу
            try:
                if guild.owner and not guild.owner.bot:
                    log.info(f'[TICKET-NOTIFY] Fallback: отправляю DM владельцу {guild.owner} ({guild.owner.id})...')
                    await guild.owner.send(content=admin_ping, embed=embed)
                    log.info(f'[TICKET-NOTIFY] DM отправлено владельцу')
                else:
                    log.info(f'[TICKET-NOTIFY] Нет владельца сервера — уведомление НИКУДА не доставлено!')
            except Exception as e:
                log.info(f'[TICKET-NOTIFY] Ошибка отправки DM владельцу: {e}')
                log.info(f'[TICKET-NOTIFY] УВЕДОМЛЕНИЕ ПОТЕРЯНО!')
        log.info(f'[TICKET-NOTIFY] === КОНЕЦ ===\n')
    
    async def _assign_role(self, guild: discord.Guild, user_id: int, role_id: int):
        """Назначить роль от AI"""
        try:
            target_user = guild.get_member(user_id)
            role = guild.get_role(role_id)
            
            if not target_user:
                log.info(f"[TICKET] Назначение роли: пользователь {user_id} не найден")
                return
            
            if not role:
                log.info(f"[TICKET] Назначение роли: роль {role_id} не найдена")
                return
            
            await target_user.add_roles(role, reason="AI Ticket Assistant")
            log.info(f"[TICKET] Роль {role.name} выдана {target_user}")
            
        except Exception as e:
            log.info(f"Ошибка назначения роли: {e}")
    
    async def _delete_messages(self, guild: discord.Guild, channel_id: int, count: int):
        """Удалить сообщения от AI"""
        try:
            channel = guild.get_channel(channel_id)
            if not channel:
                log.info(f"[TICKET] Удаление сообщений: канал {channel_id} не найден")
                return
            
            deleted = await channel.purge(limit=min(count, 100))
            log.info(f"[TICKET] Удалено {len(deleted)} сообщений в {channel.name}")
            
        except Exception as e:
            log.info(f"Ошибка удаления сообщений: {e}")
    
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
                return f"В этом канале сообщения {'этого пользователя ' if user_id else ''}не найдены."

            summary = f"В канале #{target_channel.name} найдено сообщений ({len(messages)}):\n"
            for msg in messages[:20]:
                edited_tag = ' [EDİTLENMİŞ]' if msg['edited'] else ''
                summary += f"[{msg['timestamp']}] {msg['author']}: {msg['content']}{edited_tag}\n"

            return summary

        except Exception as e:
            return f"Сообщение история контроль edilemedi: {str(e)}"

    @app_commands.command(name="ai-ticket-panel", description="Отправить AI панель тикетов в канал")
    @app_commands.checks.has_permissions(administrator=True)
    async def ticket_panel(self, interaction: discord.Interaction):
        if interaction.guild.id in TICKET_DISABLED_GUILDS:
            await interaction.response.send_message(
                'На этом сервере система тикетов отключена.', ephemeral=True
            )
            return

        # Канал уже содержит панель тикетов от бота?
        async for msg in interaction.channel.history(limit=20):
            if (msg.author == interaction.guild.me and
                    msg.embeds and
                    msg.components and
                    any('ticket_open' in str(c) for c in msg.components)):
                await interaction.response.send_message(
                    "В этом канале уже есть панель тикетов. Сначала удалите старую.",
                    ephemeral=True
                )
                return
        e = discord.Embed(
            title=" ПОДДЕРЖКА СИСТЕМА",
            color=0x5865F2,
            timestamp=datetime.datetime.utcnow()
        )
        e.description = (
            f"```ansi\n\u001b[1;34m Aether СИСТЕМА ПОДДЕРЖКИ \u001b[0m\n```\n"
            f"{_divider()}\n\n"
            "Возникла ли проблема на сервере?\n"
            "Хотите что-то спросить?\n\n"
            "**Нажмите на кнопку ниже**, чтобы создать приватный канал поддержки.\n"
            "**AI-ассистент** сначала поможет вам!\n"
            "При необходимости подключится наша команда. \n\n"
            f"{_divider()}\n\n"
            "```yaml\n"
            "AI Поддержка    •     Быстрый ответ    •    Приватный канал\n"
            "```"
        )
        e.set_image(url=GIF_PANEL)
        e.set_footer(
            text=f"{interaction.guild.name} • AI Поддержка Система",
            icon_url=interaction.guild.icon.url if interaction.guild.icon else None
        )
        await interaction.channel.send(embed=e, view=TicketView())
        await interaction.response.send_message("Ticket paneli отправлено.", ephemeral=True)

    @app_commands.command(name="ticket-add", description="Добавить пользователя в тикет")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def ticket_add(self, interaction: discord.Interaction, user: discord.Member):
        await interaction.channel.set_permissions(user, read_messages=True, send_messages=True)
        e = discord.Embed(
            description=f"{user.mention} добавлен в канал поддержки.",
            color=0x2ECC71
        )
        await interaction.response.send_message(embed=e)

    @app_commands.command(name="ticket-cikar", description="Удалить пользователя из тикета")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def ticket_cikar(self, interaction: discord.Interaction, user: discord.Member):
        await interaction.channel.set_permissions(user, read_messages=False)
        e = discord.Embed(
            description=f" {user.mention} удалён из канала поддержки.",
            color=0xE74C3C
        )
        await interaction.response.send_message(embed=e)
    
    @app_commands.command(name="ticket-ai-stats", description="Показать статистику AI-поддержки")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_ai_stats(self, interaction: discord.Interaction):
        """Показать статистику AI-поддержки"""
        data = self._load_ai_data(interaction.guild.id)
        
        if not data:
            await interaction.response.send_message("Данных AI-поддержки пока нет.", ephemeral=True)
            return
        
        total_tickets = len(data)
        ai_handling = sum(1 for t in data.values() if t['status'] == 'ai_handling')
        escalated = sum(1 for t in data.values() if t['status'] == 'escalated')
        staff_handling = sum(1 for t in data.values() if t['status'] == 'staff_handling')
        closed_tickets = total_tickets - ai_handling - escalated - staff_handling
        
        # Custom Menu kullan
        e = StatsMenu.ticket_stats(
            total=total_tickets,
            open_tickets=ai_handling + escalated + staff_handling,
            closed_tickets=closed_tickets,
            ai_handled=ai_handling,
            escalated=escalated
        )
        
        await interaction.response.send_message(embed=e)
    
    @app_commands.command(name="ticket-ai-toggle", description="Включить/отключить AI-поддержку тикетов")
    @app_commands.checks.has_permissions(administrator=True)
    async def ticket_ai_toggle(self, interaction: discord.Interaction):
        """Включить/отключить AI-поддержку тикетов"""
        global AI_ENABLED
        AI_ENABLED = not AI_ENABLED
        
        status = "Активна" if AI_ENABLED else "Отключена"
        e = discord.Embed(
            title=" AI Поддержка Система",
            description=f"AI-система поддержки сейчас: **{status}**",
            color=0x2ECC71 if AI_ENABLED else 0xE74C3C
        )
        await interaction.response.send_message(embed=e)
    
    @app_commands.command(name="ticket-force-escalate", description="Перенаправить текущий тикет администрации")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def ticket_force_escalate(self, interaction: discord.Interaction):
        """Передать тикет модераторам вручную"""
        if not interaction.channel.name.startswith("ticket-"):
            await interaction.response.send_message("Это не канал тикета.", ephemeral=True)
            return
        
        state = self._get_ticket_state(interaction.guild.id, interaction.channel.id)
        
        if state['status'] == 'escalated':
            await interaction.response.send_message("Этот тикет уже передан модераторам.", ephemeral=True)
            return
        
        await interaction.response.send_message(" Передаю тикет модераторам...", ephemeral=True)
        await self._escalate_ticket(interaction.channel, state, 'manual')

    @app_commands.command(name="ticket-reset-rate-limit", description="Сбросить rate limit для пользователя")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_reset_rate_limit(self, interaction: discord.Interaction, user: discord.Member):
        """Сбросить rate limit для указанного пользователя"""
        rate_limiter = get_rate_limiter()
        await rate_limiter.reset_user(interaction.guild.id, user.id)
        
        e = discord.Embed(
            color=0x2ECC71,
            description=f"Rate limit для {user.mention} сброшен.\nТеперь пользователь может создавать тикеты без ограничений."
        )
        await interaction.response.send_message(embed=e, ephemeral=True)
        logger.info(
            f"[RateLimit] Сброшен rate limit: admin={interaction.user} ({interaction.user.id}) "
            f"target={user} ({user.id})"
        )

    @app_commands.command(name="ticket-rate-limit-info", description="Показать rate limit информацию для пользователя")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_rate_limit_info(self, interaction: discord.Interaction, user: discord.Member = None):
        """Показать статистику rate limit для пользователя"""
        target = user or interaction.user
        rate_limiter = get_rate_limiter()
        stats = await rate_limiter.get_user_stats(interaction.guild.id, target.id)
        
        # Custom Menu kullan
        menu = CustomMenu(
            title=f"Rate Limit — {target.display_name}",
            color='info',
            border_style='single',
            thumbnail=target.display_avatar.url,
            footer_text=f"{interaction.guild.name} • Rate Limit Info",
            footer_icon=interaction.guild.icon.url if interaction.guild.icon else None
        )
        
        # İstatistikler (3'lü grid)
        menu.add_stats([
            {'label': 'За 24ч', 'value': stats['tickets_24h'], 'emoji': ''},
            {'label': 'За неделю', 'value': stats['tickets_week'], 'emoji': ''},
            {'label': 'За месяц', 'value': stats['tickets_month'], 'emoji': ''},
        ], layout='grid')
        
        menu.add_separator()
        
        # Son ticket ve cooldown
        if stats['last_ticket']:
            ts = int(stats['last_ticket'].timestamp())
            last_ticket_text = f"<t:{ts}:R>"
        else:
            last_ticket_text = "Нет данных"
        
        cooldown_text = f"{stats['cooldown_remaining']} сек." if stats['cooldown_remaining'] > 0 else "Готов"
        
        menu.add_section(
            title="Последний тикет",
            content=last_ticket_text,
            emoji="⏰",
            inline=True
        )
        
        menu.add_section(
            title="Кулдаун",
            content=f"```{cooldown_text}```",
            emoji="⏳",
            inline=True
        )
        
        e = menu.build()
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name="ticket-feedback-stats", description="Показать статистику обратной связи")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_feedback_stats(self, interaction: discord.Interaction):
        """Показать статистику отзывов пользователей"""
        feedback_service = get_feedback_service()
        stats = feedback_service.get_guild_stats(interaction.guild.id)
        
        if stats['total'] == 0:
            await interaction.response.send_message(
                "Отзывов пока нет.",
                ephemeral=True
            )
            return
        
        # Custom Menu kullan
        e = StatsMenu.feedback_stats(
            total=stats['total'],
            positive=stats['positive'],
            negative=stats['negative'],
            avg_rating=stats['avg_rating'],
            recent_comments=stats['comments']
        )
        
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name="ticket-auto-close", description="Настроить автоматическое закрытие неактивных тикетов")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(hours="Через сколько часов неактивности закрывать тикет (1-168)")
    async def ticket_auto_close(self, interaction: discord.Interaction, hours: int = 24):
        """Настроить время автоматического закрытия тикетов"""
        if hours < 1 or hours > 168:
            await interaction.response.send_message(
                "Значение должно быть от 1 до 168 часов (7 дней).",
                ephemeral=True
            )
            return
        
        from services.auto_close_service import get_auto_close_service
        auto_close = get_auto_close_service(self.bot)
        auto_close.set_inactive_hours(hours)
        
        # Custom Menu kullan
        menu = CustomMenu(
            title="Автозакрытие тикетов",
            color='success',
            border_style='wave'
        )
        
        menu.add_section(
            title="Настройка",
            content=f"Неактивные тикеты будут автоматически закрываться через **{hours}** часов.",
            emoji=""
        )
        
        menu.add_separator()
        
        menu.add_section(
            title="Что считается неактивностью?",
            content="Если в тикете не было сообщений указанное время, он будет закрыт автоматически.",
            emoji="ℹ"
        )
        
        e = menu.build()
        
        await interaction.response.send_message(embed=e, ephemeral=True)
        logger.info(f"[Ticket] Auto-close настроен на {hours} часов администратором {interaction.user}")

    @app_commands.command(name="ticket-config", description="Настройки системы тикетов")
    @app_commands.checks.has_permissions(administrator=True)
    async def ticket_config(self, interaction: discord.Interaction):
        """Показать текущие настройки системы тикетов"""
        from services.auto_close_service import get_auto_close_service
        auto_close = get_auto_close_service(self.bot)
        rate_limiter = get_rate_limiter()
        limits = rate_limiter.default_limits
        
        # Custom Menu kullan
        menu = CustomMenu(
            title="Настройки системы тикетов",
            color='primary',
            border_style='diamond',
            footer_text=f"{interaction.guild.name} • Конфигурация",
            footer_icon=interaction.guild.icon.url if interaction.guild.icon else None
        )
        
        # Ana ayarlar (3'lü grid)
        ai_status = "Активна" if AI_ENABLED else "Отключена"
        menu.add_stats([
            {'label': 'AI-поддержка', 'value': ai_status, 'emoji': ''},
            {'label': 'Автозакрытие', 'value': f"{auto_close.inactive_hours}ч", 'emoji': '⏰'},
            {'label': 'Rate Limit', 'value': f"{limits['max_tickets_per_24h']}/24ч", 'emoji': ''},
        ], layout='grid')
        
        menu.add_separator()
        
        # Rate limit detayları
        menu.add_stats([
            {'label': 'Кулдаун', 'value': f"{limits['cooldown_seconds']}с", 'emoji': '⏳'},
            {'label': 'Недельный лимит', 'value': str(limits['max_tickets_per_week']), 'emoji': ''},
            {'label': 'Месячный лимит', 'value': str(limits['max_tickets_per_month']), 'emoji': ''},
        ], layout='grid')
        
        menu.add_separator()
        
        # Komutlar listesi
        menu.add_list(
            title="Команды управления",
            items=[
                "`/ticket-ai-toggle` — Вкл/выкл AI",
                "`/ticket-auto-close <часы>` — Настроить автозакрытие",
                "`/ticket-reset-rate-limit <@user>` — Сбросить лимит",
                "`/ticket-feedback-stats` — Статистика отзывов",
            ],
            emoji="",
            numbered=False
        )
        
        e = menu.build()
        await interaction.response.send_message(embed=e, ephemeral=True)


async def setup(bot):
    """Загрузка cog и инициализация сервисов"""
    # Загружаем Ticket cog
    await bot.add_cog(
        Ticket(bot), 
        guilds=[
            discord.Object(id=1421244140359909513), 
            discord.Object(id=1107038411895881788), 
            discord.Object(id=1498837105915330562)
        ]
    )
    
    #  AUTO-CLOSE СЕРВИС 
    # Запускаем фоновую задачу автоматического закрытия неактивных тикетов
    from services.auto_close_service import get_auto_close_service
    auto_close = get_auto_close_service(bot)
    auto_close.set_inactive_hours(24)  # Закрывать через 24 часа неактивности
    await auto_close.start()
    logger.info("[Ticket] Auto-close сервис запущен (24 часа)")
    #  END AUTO-CLOSE СЕРВИС 
