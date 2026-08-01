"""
Система кастомных меню - Чистый и профессиональный дизайн
Меню без эмодзи, с select menu (dropdown)
"""

import discord
from typing import List, Dict, Optional, Union
from datetime import datetime


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
        'success': 0x2ECC71,      # Yeşil
        'warning': 0xF39C12,      # Turuncu
        'danger': 0xE74C3C,       # Kırmızı
        'info': 0x00D9FF,         # Cyan
        'purple': 0x9B59B6,       # Mor
        'gold': 0xFFD700,         # Altın
        'dark': 0x2C2F33,         # Koyu gri
    }
    
    # Dekorasyonlar (emoji yok, sadece çizgiler)
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
        inline: bool = False
    ):
        """Bölüm ekle (emoji yok)"""
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
        İstatistik ekle (emoji yok)
        
        Args:
            stats: [{'label': 'Toplam', 'value': 150}, ...]
            layout: 'grid' (3'lü) veya 'list' (tek sütun)
        """
        if layout == 'grid':
            # 3'lü grid
            for i in range(0, len(stats), 3):
                row = stats[i:i+3]
                for stat in row:
                    self.add_section(
                        title=stat['label'],
                        content=f"```{stat['value']}```",
                        inline=True
                    )
        else:
            # Liste formatı
            lines = []
            for stat in stats:
                lines.append(f"**{stat['label']}:** `{stat['value']}`")
            
            self.add_section(
                title="Иstatistikler",
                content="\n".join(lines)
            )
        
        return self
    
    def add_progress_bar(
        self,
        label: str,
        current: int,
        maximum: int
    ):
        """İlerleme çubuğu ekle (emoji yok)"""
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
        numbered: bool = True
    ):
        """Liste ekle (emoji yok)"""
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
        """Kod bloğu ekle (emoji yok)"""
        content = f"```{language}\n{code}\n```"
        self.add_section(title=title, content=content)
        return self
    
    def add_separator(self, style: str = 'single'):
        """Ayırıcı ekle"""
        separator = self.BORDERS.get(style, self.border)
        self.sections.append({
            'title': None,
            'content': separator,
            'inline': False
        })
        return self
    
    def build(self) -> discord.Embed:
        """Embed oluştur"""
        embed = discord.Embed(
            color=self.color,
            timestamp=datetime.utcnow() if self.show_timestamp else None
        )
        
        # Başlık ve açıklama
        if self.description:
            embed.description = f"**{self.title}**\n\n{self.description}"
        else:
            embed.description = f"**{self.title}**"
        
        # Bölümler
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
    """Ticket sistemi için özel menü (emoji yok)"""
    
    @classmethod
    def welcome(cls, user, guild, channel):
        """Ticket hoş geldin menüsü"""
        menu = CustomMenu(
            title="Тикет открыт",
            description=f"Добро пожаловать, {user.mention}!\n\nОпишите вашу проблему, и мы поможем вам как можно скорее.",
            color='primary'
        )
        
        menu.add_section("Пользователь", user.mention, inline=True)
        menu.add_section("Канал", channel.mention, inline=True)
        menu.add_section("Создан", discord.utils.format_dt(discord.utils.utcnow(), style='R'), inline=True)
        
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
        """Ticket kapatma menüsü"""
        menu = CustomMenu(
            title="Тикет закрыт",
            description="Ваш тикет был успешно закрыт.",
            color='success'
        )
        
        menu.add_section("Пользователь", user.mention, inline=True)
        menu.add_section("Закрыл", closed_by.mention, inline=True)
        menu.add_section("Время", discord.utils.format_dt(discord.utils.utcnow(), style='R'), inline=True)
        
        menu.add_separator()
        
        menu.add_section(
            "Спасибо!",
            "Спасибо за обращение. Если у вас есть еще вопросы, создайте новый тикет."
        )
        
        return menu.build()


class StatsMenu:
    """İstatistik menüsü (emoji yok)"""
    
    @classmethod
    def ticket_stats(cls, total, ai_handled, escalated):
        """Ticket istatistikleri"""
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
        
        # AI başarı oranı
        if total > 0:
            ai_rate = (ai_handled / total) * 100
            menu.add_progress_bar("Эффективность AI", ai_handled, total)
            menu.add_section("AI обработал", f"{ai_rate:.1f}% всех тикетов")
        
        return menu.build()
    
    @classmethod
    def feedback_stats(cls, total, positive, negative, avg_rating, recent_comments):
        """Feedback istatistikleri"""
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
        
        # Ortalama puan
        menu.add_section("Средняя оценка", f"```{avg_rating:.2f}/5.00```", inline=True)
        
        # Pozitif oranı
        if total > 0:
            pos_rate = (positive / total) * 100
            menu.add_section("Положительных", f"{pos_rate:.1f}%", inline=True)
        
        # Son yorumlar
        if recent_comments:
            menu.add_separator()
            menu.add_list("Последние отзывы", recent_comments[-5:], numbered=False)
        
        return menu.build()


class HelpMenu:
    """Yardım menüsü (emoji yok)"""
    
    @classmethod
    def ticket_help(cls):
        """Ticket yardım menüsü"""
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
async def example_usage():
    """Örnek kullanım (emoji yok)"""
    
    # Ticket hoş geldin menüsü
    welcome_embed = TicketMenu.welcome(
        user=interaction.user,
        guild=interaction.guild,
        channel=channel
    )
    
    # İstatistik menüsü
    stats_embed = StatsMenu.ticket_stats(
        total=150,
        ai_handled=120,
        escalated=18
    )
    
    # Feedback menüsü
    feedback_embed = StatsMenu.feedback_stats(
        total=89,
        positive=76,
        negative=13,
        avg_rating=4.25,
        recent_comments=["Отлично!", "Быстро помогли", "Спасибо!"]
    )
    
    # Yardım menüsü
    help_embed = HelpMenu.ticket_help()
    
    # Özel menü oluşturma
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
