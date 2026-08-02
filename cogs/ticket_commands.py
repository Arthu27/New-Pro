"""
Discord Bot Commands для системы тикетов
Slash-команды для управления тикетами прямо из Discord
"""

import discord
from discord.ext import commands
from discord import app_commands
import json
import os
from datetime import datetime
import uuid

from logger import get_logger
log = get_logger("ticket_commands")



class TicketCommands(commands.Cog):
    """Slash-команды для управления тикетами"""
    
    def __init__(self, bot):
        self.bot = bot
    
    # /ticket create 
    @app_commands.command(name="ticket", description="Создать новый тикет поддержки")
    @app_commands.describe(
        subject="Тема тикета",
        category="Категория тикета",
        priority="Приоритет тикета",
        description="Подробное описание проблемы"
    )
    @app_commands.choices(
        category=[
            app_commands.Choice(name="Вопрос", value="Вопрос"),
            app_commands.Choice(name="Техническая проблема", value="Техническая проблема"),
            app_commands.Choice(name="Жалоба", value="Жалоба"),
            app_commands.Choice(name="Предложение", value="Предложение"),
            app_commands.Choice(name="Другое", value="Другое")
        ],
        priority=[
            app_commands.Choice(name="Низкий", value="low"),
            app_commands.Choice(name="Средний", value="medium"),
            app_commands.Choice(name="Высокий", value="high")
        ]
    )
    async def ticket_create(
        self,
        interaction: discord.Interaction,
        subject: str,
        category: app_commands.Choice[str],
        priority: app_commands.Choice[str],
        description: str
    ):
        """Создать новый тикет"""
        await interaction.response.defer(ephemeral=True)
        
        # Создать тикет
        tickets_file = 'data/customer_tickets.json'
        
        if os.path.exists(tickets_file):
            try:
                with open(tickets_file, 'r', encoding='utf-8') as f:
                    tickets = json.load(f)
            except Exception:
                tickets = []
        else:
            tickets = []
        
        ticket_id = str(uuid.uuid4())[:8]
        
        new_ticket = {
            'id': ticket_id,
            'user_id': str(interaction.user.id),
            'user_name': str(interaction.user),
            'subject': subject,
            'category': category.value,
            'priority': priority.value,
            'description': description,
            'status': 'open',
            'message_count': 1,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        
        tickets.append(new_ticket)
        
        os.makedirs('data', exist_ok=True)
        with open(tickets_file, 'w', encoding='utf-8') as f:
            json.dump(tickets, f, ensure_ascii=False, indent=2)
        
        # Создать embed
        priority_colors = {
            'low': 0x2ecc71,
            'medium': 0xf1c40f,
            'high': 0xe74c3c
        }
        
        priority_names = {
            'low': 'Низкий',
            'medium': 'Средний',
            'high': 'Высокий'
        }
        
        embed = discord.Embed(
            title=f" Тикет #{ticket_id} создан!",
            description=f"Ваш тикет успешно создан и будет обработан в ближайшее время.",
            color=priority_colors.get(priority.value, 0x5865f2),
            timestamp=datetime.now()
        )
        
        embed.add_field(name="Тема", value=subject, inline=False)
        embed.add_field(name="Категория", value=category.value, inline=True)
        embed.add_field(name="Приоритет", value=priority_names.get(priority.value, 'Средний'), inline=True)
        embed.add_field(name="Описание", value=description[:1024], inline=False)
        embed.set_footer(text=f"ID: {ticket_id}")
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    # /ticket list 
    @app_commands.command(name="mytickets", description="Показать список ваших тикетов")
    @app_commands.describe(
        status="Фильтр по статусу"
    )
    @app_commands.choices(
        status=[
            app_commands.Choice(name="Все", value="all"),
            app_commands.Choice(name="Открытые", value="open"),
            app_commands.Choice(name="Закрытые", value="closed")
        ]
    )
    async def ticket_list(
        self,
        interaction: discord.Interaction,
        status: app_commands.Choice[str] = None
    ):
        """Показать список тикетов пользователя"""
        await interaction.response.defer(ephemeral=True)
        
        status_filter = status.value if status else 'all'
        
        # Загрузить тикеты
        tickets_file = 'data/customer_tickets.json'
        
        if os.path.exists(tickets_file):
            try:
                with open(tickets_file, 'r', encoding='utf-8') as f:
                    all_tickets = json.load(f)
            except Exception:
                all_tickets = []
        else:
            all_tickets = []
        
        # Фильтровать по пользователю
        user_tickets = [t for t in all_tickets if t.get('user_id') == str(interaction.user.id)]
        
        # Фильтровать по статусу
        if status_filter == 'open':
            user_tickets = [t for t in user_tickets if t.get('status') == 'open']
        elif status_filter == 'closed':
            user_tickets = [t for t in user_tickets if t.get('status') == 'closed']
        
        # Сортировка по дате (новые первые)
        user_tickets.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        if not user_tickets:
            embed = discord.Embed(
                title=" Ваши тикеты",
                description="У вас пока нет тикетов.",
                color=0x5865f2
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        # Создать embed
        embed = discord.Embed(
            title=f" Ваши тикеты ({len(user_tickets)})",
            color=0x5865f2,
            timestamp=datetime.now()
        )
        
        # Показать максимум 10 тикетов
        for ticket in user_tickets[:10]:
            status_emoji = "🟢" if ticket.get('status') == 'open' else ""
            status_text = "Открыт" if ticket.get('status') == 'open' else "Закрыт"
            
            created_date = datetime.fromisoformat(ticket.get('created_at', ''))
            created_str = created_date.strftime('%d.%m.%Y %H:%M')
            
            value = f"**{ticket.get('subject', 'Без темы')}**\n"
            value += f"{status_emoji} {status_text} • {ticket.get('category', 'Другое')}\n"
            value += f" {created_str} • {ticket.get('message_count', 0)} сообщений\n"
            value += f"ID: `{ticket.get('id')}`"
            
            embed.add_field(
                name=f"#{ticket.get('id')}",
                value=value,
                inline=False
            )
        
        if len(user_tickets) > 10:
            embed.set_footer(text=f"Показано 10 из {len(user_tickets)} тикетов")
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    # /ticket view 
    @app_commands.command(name="viewticket", description="Просмотреть details тикета")
    @app_commands.describe(
        ticket_id="ID тикета"
    )
    async def ticket_view(
        self,
        interaction: discord.Interaction,
        ticket_id: str
    ):
        """Просмотреть details тикета"""
        await interaction.response.defer(ephemeral=True)
        
        # Загрузить тикеты
        tickets_file = 'data/customer_tickets.json'
        
        if os.path.exists(tickets_file):
            try:
                with open(tickets_file, 'r', encoding='utf-8') as f:
                    all_tickets = json.load(f)
            except Exception:
                all_tickets = []
        else:
            all_tickets = []
        
        # Найти тикет
        ticket = None
        for t in all_tickets:
            if t.get('id') == ticket_id:
                ticket = t
                break
        
        if not ticket:
            embed = discord.Embed(
                title=" Тикет не найден",
                description=f"Тикет с ID `{ticket_id}` не найден.",
                color=0xe74c3c
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        # Проверить права доступа
        if ticket.get('user_id') != str(interaction.user.id):
            embed = discord.Embed(
                title=" Нет доступа",
                description="У вас нет доступа к этому тикету.",
                color=0xe74c3c
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        # Создать embed
        priority_colors = {
            'low': 0x2ecc71,
            'medium': 0xf1c40f,
            'high': 0xe74c3c
        }
        
        priority_names = {
            'low': 'Низкий',
            'medium': 'Средний',
            'high': 'Высокий'
        }
        
        status_emoji = "🟢" if ticket.get('status') == 'open' else ""
        status_text = "Открыт" if ticket.get('status') == 'open' else "Закрыт"
        
        embed = discord.Embed(
            title=f" Тикет #{ticket_id}",
            description=ticket.get('description', 'Без описания'),
            color=priority_colors.get(ticket.get('priority', 'medium'), 0x5865f2),
            timestamp=datetime.fromisoformat(ticket.get('created_at', ''))
        )
        
        embed.add_field(name="Тема", value=ticket.get('subject', 'Без темы'), inline=False)
        embed.add_field(name="Категория", value=ticket.get('category', 'Другое'), inline=True)
        embed.add_field(name="Приоритет", value=priority_names.get(ticket.get('priority', 'medium'), 'Средний'), inline=True)
        embed.add_field(name="Статус", value=f"{status_emoji} {status_text}", inline=True)
        embed.add_field(name="Сообщений", value=str(ticket.get('message_count', 0)), inline=True)
        
        if ticket.get('rating'):
            embed.add_field(name="Оценка", value=f" {ticket.get('rating')}/5", inline=True)
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    # /stats 
    @app_commands.command(name="stats", description="Показать статистику сервера")
    async def stats(self, interaction: discord.Interaction):
        """Показать статистику"""
        await interaction.response.defer(ephemeral=True)
        
        # Загрузить тикеты
        tickets_file = 'data/customer_tickets.json'
        
        if os.path.exists(tickets_file):
            try:
                with open(tickets_file, 'r', encoding='utf-8') as f:
                    all_tickets = json.load(f)
            except Exception:
                all_tickets = []
        else:
            all_tickets = []
        
        # Статистика
        total_tickets = len(all_tickets)
        open_tickets = sum(1 for t in all_tickets if t.get('status') == 'open')
        closed_tickets = total_tickets - open_tickets
        
        ratings = [t.get('rating', 0) for t in all_tickets if t.get('rating')]
        avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else 0
        
        # Создать embed
        embed = discord.Embed(
            title=" Статистика сервера",
            color=0x5865f2,
            timestamp=datetime.now()
        )
        
        embed.add_field(name=" Всего тикетов", value=str(total_tickets), inline=True)
        embed.add_field(name="🟢 Открытых", value=str(open_tickets), inline=True)
        embed.add_field(name=" Закрытых", value=str(closed_tickets), inline=True)
        embed.add_field(name=" Средняя оценка", value=f"{avg_rating}/5", inline=True)
        embed.add_field(name=" Участников", value=str(interaction.guild.member_count), inline=True)
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    # /help 
    @app_commands.command(name="ticket-help", description="Показать справку по тикетам")
    async def help(self, interaction: discord.Interaction):
        """Показать справку"""
        embed = discord.Embed(
            title=" Справка по командам",
            description="Доступные slash-команды для работы с тикетами:",
            color=0x5865f2,
            timestamp=datetime.now()
        )
        
        commands_list = [
            ("`/ticket`", "Создать новый тикет поддержки"),
            ("`/mytickets`", "Показать список ваших тикетов"),
            ("`/viewticket <id>`", "Просмотреть details тикета"),
            ("`/stats`", "Показать статистику сервера"),
            ("`/help`", "Показать эту справку")
        ]
        
        for cmd, desc in commands_list:
            embed.add_field(name=cmd, value=desc, inline=False)
        
        embed.set_footer(text="Используйте эти команды для быстрого доступа к системе тикетов")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    """Загрузка cog"""
    await bot.add_cog(TicketCommands(bot))
    log.info('[Ticket Commands] Команды загружены')
