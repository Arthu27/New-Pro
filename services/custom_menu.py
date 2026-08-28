"""
Система кастомных меню - Чистый и профессиональный дизайн
Меню без эмодзи, с select menu (dropdown)
"""

import discord
from typing import List, Dict, Optional, Union
from datetime import datetime, timezone


class CustomMenu:
    """
    Чистая и профессиональная система меню
    
    Особенности:
    - Без эмодзи
    - Select menu (dropdown) поддержка
    - Чистый текстовый формат
    - Профессиональный вид
    """
    
    # Renk paletleri
    COLORS = {
        'primary': 0x5865F2,      # Discord Blurple
        'success': 0x2ECC71,      # Yeшil
        'warning': 0xF39C12,      # Turuncu
        'danger': 0xE74C3C,       # Kыrлиzы
        'info': 0x00D9FF,         # Cyan
        'purple': 0x9B59B6,       # Mor
        'gold': 0xFFD700,         # Altыn
        'dark': 0x2C2F33,         # Koyu gri
    }
    
    # Декорации (без эмодзи, только линии)
    BORDERS = {
        'single': '' * 40,
        'double': '' * 40,
        'dotted': '·' * 40,
    }
    
    def __init__(
        self,
        title: str,
        description: Optional[str] = None,
        color: Union[int, str] = 'primary',
        border_style: str = 'single',
        show_timestamp: bool = True,
        footer_text: Optional[str] = None,
        footer_icon: Optional[str] = None,
        thumbnail: Optional[str] = None,
        image: Optional[str] = None
    ):
        self.title = title
        self.description = description
        self.color = self.COLORS.get(color, color) if isinstance(color, str) else color
        self.border = self.BORDERS.get(border_style, self.BORDERS['single'])
        self.show_timestamp = show_timestamp
        self.footer_text = footer_text
        self.footer_icon = footer_icon
        self.thumbnail = thumbnail
        self.image = image
        self.sections = []
    
    def add_section(
        self,
        title: str,
        content: str,
        inline: bool = False,
        emoji: str = None
    ):
        """Добавить раздел (emoji необязателен)"""
        if emoji:
            title = f"{emoji} {title}"
        self.sections.append({
            'title': title,
            'content': content,
            'inline': inline
        })
        return self
    
    def add_stats(
        self,
        stats: List[Dict[str, Union[str, int]]],
        layout: str = 'grid'
    ):
        """
        Добавить статистику (без эмодзи)
        
        Args:
            stats: [{'label': 'Всего', 'value': 150}, ...]
            layout: 'grid' (по 3) или 'list' (одна колонка)
        """
        if layout == 'grid':
            # grid по 3
            for i in range(0, len(stats), 3):
                row = stats[i:i+3]
                for stat in row:
                    self.add_section(
                        title=stat['label'],
                        content=f"```{stat['value']}```",
                        inline=True
                    )
        else:
            # Liste формат
            lines = []
            for stat in stats:
                lines.append(f"**{stat['label']}:** `{stat['value']}`")
            
            self.add_section(
                title="Статистика",
                content="\n".join(lines)
            )
        
        return self
    
    def add_progress_bar(
        self,
        label: str,
        current: int,
        maximum: int
    ):
        """Добавить полосу прогресса (без эмодзи)"""
        percentage = (current / maximum) * 100 if maximum > 0 else 0
        filled = int(percentage / 5)
        bar = "" * filled + "" * (20 - filled)
        
        content = f"```[{bar}] {percentage:.1f}%```\n{current}/{maximum}"
        self.add_section(title=label, content=content)
        
        return self
    
    def add_list(
        self,
        title: str,
        items: List[str],
        numbered: bool = True,
        emoji: str = None
    ):
        """Добавить список (emoji необязателен)"""
        if emoji:
            title = f"{emoji} {title}"
        if numbered:
            lines = [f"**{i+1}.** {item}" for i, item in enumerate(items)]
        else:
            lines = [f"• {item}" for item in items]
        
        self.add_section(
            title=title,
            content="\n".join(lines)
        )
        
        return self
    
    def add_code_block(
        self,
        title: str,
        code: str,
        language: str = ''
    ):
        """Добавить блок кода (без эмодзи)"""
        content = f"```{language}\n{code}\n```"
        self.add_section(title=title, content=content)
        return self
    
    def add_separator(self, style: str = 'single'):
        """Добавить разделитель"""
        separator = self.BORDERS.get(style, self.border)
        self.sections.append({
            'title': None,
            'content': separator,
            'inline': False
        })
        return self
    
    def build(self) -> discord.Embed:
        """Embed создать"""
        embed = discord.Embed(
            color=self.color,
            timestamp=datetime.now(timezone.utc) if self.show_timestamp else None
        )
        
        # Заголовок ve описание
        if self.description:
            embed.description = f"**{self.title}**\n\n{self.description}"
        else:
            embed.description = f"**{self.title}**"
        
        # Bёlюmler
        for section in self.sections:
            if section['title'] is None:
                # Separator
                embed.add_field(
                    name="\u200b",  # Zero-width space
                    value=section['content'],
                    inline=False
                )
            else:
                embed.add_field(
                    name=f"**{section['title']}**",
                    value=section['content'],
                    inline=section['inline']
                )
        
        # Thumbnail
        if self.thumbnail:
            embed.set_thumbnail(url=self.thumbnail)
        
        # Image
        if self.image:
            embed.set_image(url=self.image)
        
        # Footer
        if self.footer_text:
            embed.set_footer(
                text=self.footer_text,
                icon_url=self.footer_icon
            )
        
        return embed


class TicketMenu:
    """Кастомное меню для системы тикетов (без эмодзи)"""
    
    @classmethod
    def welcome(cls, user, guild, channel):
        """Приветственное меню тикета"""
        menu = CustomMenu(
            title="Тикет открыт",
            description=f"Добро пожаловать, {user.mention}!\n\nОпишите вашу проблему, и мы поможем вам как можно скорее.",
            color='primary'
        )
        
        menu.add_section("Пользователь", user.mention, inline=True)
        menu.add_section("Канал", channel.mention, inline=True)
        menu.add_section("Создан", discord.utils.format_dt(datetime.now(timezone.utc), style='R'), inline=True)
        
        menu.add_separator()
        
        menu.add_section(
            "Что дальше?",
            "1. Опишите вашу проблему подробно\n"
            "2. Прикрепите скриншоты если нужно\n"
            "3. Дождитесь ответа модератора"
        )
        
        return menu.build()
    
    @classmethod
    def closed(cls, user, closed_by):
        """Меню закрытия тикета"""
        menu = CustomMenu(
            title="Тикет закрыт",
            description="Ваш тикет был успешно закрыт.",
            color='success'
        )
        
        menu.add_section("Пользователь", user.mention, inline=True)
        menu.add_section("Закрыл", closed_by.mention, inline=True)
        menu.add_section("Время", discord.utils.format_dt(datetime.now(timezone.utc), style='R'), inline=True)
        
        menu.add_separator()
        
        menu.add_section(
            "Спасибо!",
            "Спасибо за обращение. Если у вас есть еще вопросы, создайте новый тикет."
        )
        
        return menu.build()


class StatsMenu:
    """Меню статистики (без эмодзи)"""
    
    @classmethod
    def ticket_stats(cls, total, ai_handled, escalated):
        """Статистика тикетов"""
        menu = CustomMenu(
            title="Статистика тикетов",
            description="Общая статистика системы тикетов",
            color='info'
        )
        
        menu.add_stats([
            {'label': 'Всего', 'value': total},
            {'label': 'AI обработал', 'value': ai_handled},
            {'label': 'Передано', 'value': escalated},
        ], layout='grid')
        
        menu.add_separator()
        
        # AI успех соотношение
        if total > 0:
            ai_rate = (ai_handled / total) * 100
            menu.add_progress_bar("Эффективность AI", ai_handled, total)
            menu.add_section("AI обработал", f"{ai_rate:.1f}% всех тикетов")
        
        return menu.build()
    
    @classmethod
    def feedback_stats(cls, total, positive, negative, avg_rating, recent_comments):
        """Статистика отзывов"""
        menu = CustomMenu(
            title="Статистика отзывов",
            description="Отзывы пользователей о качестве поддержки",
            color='success'
        )
        
        menu.add_stats([
            {'label': 'Всего', 'value': total},
            {'label': 'Положительных', 'value': positive},
            {'label': 'Отрицательных', 'value': negative},
        ], layout='grid')
        
        menu.add_separator()
        
        # Ortalama очки
        menu.add_section("Средняя оценка", f"```{avg_rating:.2f}/5.00```", inline=True)
        
        # Pozitif соотношение
        if total > 0:
            pos_rate = (positive / total) * 100
            menu.add_section("Положительных", f"{pos_rate:.1f}%", inline=True)
        
        # Son yorumlar
        if recent_comments:
            menu.add_separator()
            menu.add_list("Последние отзывы", recent_comments[-5:], numbered=False)
        
        return menu.build()


class HelpMenu:
    """Меню помощи (без эмодзи)"""
    
    @classmethod
    def ticket_help(cls):
        """Меню помощи тикетов"""
        menu = CustomMenu(
            title="Справка по тикетам",
            description="Как использовать систему тикетов",
            color='info'
        )
        
        menu.add_section(
            "Как создать тикет?",
            "1. Нажмите кнопку 'Создать тикет'\n"
            "2. Выберите категорию из меню\n"
            "3. Опишите вашу проблему\n"
            "4. Дождитесь ответа"
        )
        
        menu.add_separator()
        
        menu.add_section(
            "Команды",
            "• `/ticket-panel` - Создать панель тикетов\n"
            "• `/ticket-add` - Добавить пользователя\n"
            "• `/ticket-remove` - Удалить пользователя\n"
            "• `/ticket-ai-stats` - Статистика AI\n"
            "• `/ticket-feedback-stats` - Статистика отзывов"
        )
        
        return menu.build()


# Пример использования
async def example_usage(interaction, channel):
    """Пример использования (без эмодзи)"""
    
    # Приветственное меню тикета
    welcome_embed = TicketMenu.welcome(
        user=interaction.user,
        guild=interaction.guild,
        channel=channel
    )
    
    # Меню статистики
    stats_embed = StatsMenu.ticket_stats(
        total=150,
        ai_handled=120,
        escalated=18
    )
    
    # Меню отзывов
    feedback_embed = StatsMenu.feedback_stats(
        total=89,
        positive=76,
        negative=13,
        avg_rating=4.25,
        recent_comments=["Отлично!", "Быстро помогли", "Спасибо!"]
    )
    
    # Меню помощи
    help_embed = HelpMenu.ticket_help()
    
    # Создать своё меню
    custom_menu = CustomMenu(
        title="Моё меню",
        description="Это моё кастомное меню без эмодзи",
        color='purple'
    )
    
    custom_menu.add_section(
        title="Привет",
        content="Это моё кастомное меню!"
    )
    
    custom_menu.add_stats([
        {'label': 'Очки', 'value': 1500},
        {'label': 'Уровень', 'value': 25},
        {'label': 'Ранг', 'value': 'Золото'},
    ])
    
    custom_menu.add_progress_bar(
        label="Прогресс",
        current=750,
        maximum=1000
    )
    
    embed = custom_menu.build()
