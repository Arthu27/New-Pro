"""
Проактивная модерация — AI сам замечает проблемы в чате
Токсичность, спам, подозрительные ссылки, повторяющиеся вопросы
"""
import discord
from discord.ext import commands, tasks
import re
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import asyncio


class ProactiveModeration(commands.Cog):
    """AI который сам следит за чатом"""
    
    def __init__(self, bot):
        self.bot = bot
        self.message_buffer: Dict[int, List[Dict]] = {}  # channel_id -> messages
        self.toxicity_patterns = [
            r'\b(тварь|ублюдок|мразь|сволочь|идиот|дебил|тупой|тупая)\b',
            r'\b(пошел|иди)\s*(на|в)\s*(хуй|хер|пизду|жопу)\b',
            r'\b(сука|блять|бля|нахуй|пиздец|ебать)\b',
        ]
        self.spam_threshold = 5  # Сообщений за 10 секунд
        self.spam_window = 10  # секунд
        self.link_patterns = [
            r'https?://[^\s]+',
            r'www\.[^\s]+',
            r'discord\.gg/[^\s]+',
        ]
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Анализирует каждое сообщение"""
        if message.author.bot or not message.guild:
            return
        
        channel_id = message.channel.id
        
        # Добавляем в буфер
        if channel_id not in self.message_buffer:
            self.message_buffer[channel_id] = []
        
        self.message_buffer[channel_id].append({
            'author_id': message.author.id,
            'author_name': str(message.author),
            'content': message.content,
            'timestamp': datetime.utcnow(),
            'message_id': message.id,
        })
        
        # Ограничиваем буфер 50 сообщениями
        if len(self.message_buffer[channel_id]) > 50:
            self.message_buffer[channel_id] = self.message_buffer[channel_id][-50:]
        
        # Проверяем на проблемы
        await self._check_toxicity(message)
        await self._check_spam(message)
        await self._check_suspicious_links(message)
    
    async def _check_toxicity(self, message: discord.Message):
        """Проверяет на токсичность"""
        content_lower = message.content.lower()
        
        for pattern in self.toxicity_patterns:
            if re.search(pattern, content_lower, re.IGNORECASE):
                # Нашли токсичность
                await self._alert_moderators(
                    message.guild,
                    'toxicity',
                    f"Обнаружена токсичность от {message.author.mention}",
                    message
                )
                break
    
    async def _check_spam(self, message: discord.Message):
        """Проверяет на спам"""
        channel_id = message.channel.id
        author_id = message.author.id
        
        # Считаем сообщения от этого автора за последние N секунд
        now = datetime.utcnow()
        recent_messages = [
            msg for msg in self.message_buffer.get(channel_id, [])
            if msg['author_id'] == author_id
            and (now - msg['timestamp']).total_seconds() <= self.spam_window
        ]
        
        if len(recent_messages) >= self.spam_threshold:
            # Спам обнаружен
            await self._alert_moderators(
                message.guild,
                'spam',
                f"Обнаружен спам от {message.author.mention} ({len(recent_messages)} сообщений за {self.spam_window}с)",
                message
            )
    
    async def _check_suspicious_links(self, message: discord.Message):
        """Проверяет подозрительные ссылки"""
        # Пропускаем модераторов
        if message.author.guild_permissions.kick_members:
            return
        
        for pattern in self.link_patterns:
            links = re.findall(pattern, message.content)
            if links:
                # Проверяем на подозрительные домены
                suspicious_domains = ['bit.ly', 'tinyurl.com', 'discord.gg']
                for link in links:
                    if any(domain in link.lower() for domain in suspicious_domains):
                        await self._alert_moderators(
                            message.guild,
                            'suspicious_link',
                            f"Подозрительная ссылка от {message.author.mention}: {link}",
                            message
                        )
                        break
    
    async def _alert_moderators(self, guild: discord.Guild, alert_type: str, description: str, message: discord.Message):
        """Отправляет уведомление модераторам"""
        try:
            # Ищем канал для уведомлений
            alert_channel = discord.utils.get(guild.text_channels, name="ai-alerts")
            if not alert_channel:
                # Создаём канал если нет
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(read_messages=False),
                    guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                }
                
                # Даём доступ модераторам
                for role in guild.roles:
                    if role.permissions.kick_members or role.permissions.ban_members:
                        overwrites[role] = discord.PermissionOverwrite(read_messages=True)
                
                alert_channel = await guild.create_text_channel(
                    'ai-alerts',
                    overwrites=overwrites,
                    reason="AI проактивная модерация"
                )
            
            # Создаём embed
            color_map = {
                'toxicity': 0xFF6B6B,
                'spam': 0xFFA500,
                'suspicious_link': 0xFFD700,
            }
            
            e = discord.Embed(
                color=color_map.get(alert_type, 0xFF0000),
                timestamp=datetime.utcnow()
            )
            
            e.description = (
                f"## AI Alert: {alert_type.upper()}\n"
                f"{description}\n\n"
                f"**Канал:** {message.channel.mention}\n"
                f"**Сообщение:** {message.content[:200]}\n"
                f"**Ссылка:** [Перейти]({message.jump_url})"
            )
            
            e.set_footer(text=f"{guild.name} · Проактивная модерация")
            
            await alert_channel.send(embed=e)
            
        except Exception as e:
            print(f"[PROACTIVE] Ошибка уведомления: {e}")
    
    @commands.command(name="proactive-stats")
    @commands.has_permissions(kick_members=True)
    async def proactive_stats(self, ctx):
        """Статистика проактивной модерации"""
        total_messages = sum(len(msgs) for msgs in self.message_buffer.values())
        channels_monitored = len(self.message_buffer)
        
        e = discord.Embed(
            title="Статистика проактивной модерации",
            color=0x5865F2
        )
        e.description = (
            f"**Каналов под наблюдением:** {channels_monitored}\n"
            f"**Сообщений в буфере:** {total_messages}\n"
            f"**Порог спама:** {self.spam_threshold} сообщений за {self.spam_window}с"
        )
        e.set_footer(text=f"{ctx.guild.name}")
        
        await ctx.send(embed=e)


async def setup(bot):
    await bot.add_cog(ProactiveModeration(bot))
