"""
Сервис автоматического закрытия неактивных тикетов
"""

from logger import get_logger

_log = get_logger("auto_close_service")

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional
import logging
import discord

logger = logging.getLogger('ticket.auto_close')


class AutoCloseService:
    """Автоматическое закрытие неактивных тикетов"""
    
    def __init__(self, bot):
        self.bot = bot
        self.task: Optional[asyncio.Task] = None
        self.inactive_hours = 24  # По умолчанию 24 часа
        self.check_interval = 3600  # Проверка каждый час (в секундах)
    
    async def start(self):
        """Запустить фоновую задачу"""
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self._auto_close_loop())
            logger.info("[AutoClose] Фоновая задача запущена")
    
    async def stop(self):
        """Остановить фоновую задачу"""
        if self.task and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError as _ex:
                _log.debug("stop(): подавлено: %s", _ex)
            logger.info("[AutoClose] Фоновая задача остановлена")
    
    async def _auto_close_loop(self):
        """Основной цикл проверки неактивных тикетов"""
        await self.bot.wait_until_ready()
        logger.info(f"[AutoClose] Цикл запущен (проверка каждые {self.check_interval}с)")
        
        while not self.bot.is_closed():
            try:
                await self._check_inactive_tickets()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[AutoClose] Ошибка в цикле: {e}")
                await asyncio.sleep(60)  # Подождать минуту перед повтором
    
    async def _check_inactive_tickets(self):
        """Проверить все тикеты на неактивность"""
        cutoff_time = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=self.inactive_hours)
        closed_count = 0
        
        for guild in self.bot.guilds:
            # Найти категорию тикетов
            ticket_category = discord.utils.get(guild.categories, name="Тикеты")
            if not ticket_category:
                continue
            
            # Проверить все каналы в категории
            for channel in ticket_category.channels:
                if not isinstance(channel, discord.TextChannel):
                    continue
                if not channel.name.startswith("ticket-"):
                    continue
                
                # Получить последнее сообщение
                try:
                    last_message = None
                    async for msg in channel.history(limit=1):
                        last_message = msg
                        break
                    
                    if not last_message:
                        continue
                    
                    # Проверить время последнего сообщения
                    if last_message.created_at < cutoff_time:
                        # Тикет неактивен - закрыть
                        await self._close_inactive_ticket(channel, last_message)
                        closed_count += 1
                        
                        # Небольшая задержка чтобы не спамить Discord API
                        await asyncio.sleep(1)
                
                except Exception as e:
                    logger.error(f"[AutoClose] Ошибка проверки {channel.name}: {e}")
        
        if closed_count > 0:
            logger.info(f"[AutoClose] Закрыто {closed_count} неактивных тикетов")
    
    async def _close_inactive_ticket(self, channel: discord.TextChannel, last_message: discord.Message):
        """Закрыть неактивный тикет"""
        try:
            # Получить cog для вызова метода закрытия
            cog = self.bot.get_cog('Ticket')
            if not cog:
                logger.warning("[AutoClose] Ticket cog не найден")
                return
            
            # Отправить уведомление о закрытии
            embed = discord.Embed(
                title="⏰ Тикет закрыт автоматически",
                description=(
                    "Этот тикет был закрыт из-за неактивности.\n\n"
                    f"**Последнее сообщение:** {last_message.created_at.strftime('%d.%m.%Y %H:%M')}\n"
                    f"**Неактивен:** более {self.inactive_hours} часов\n\n"
                    "Если ваша проблема не решена, создайте новый тикет."
                ),
                color=0xF39C12,
                timestamp=datetime.now(timezone.utc).replace(tzinfo=None)
            )
            
            await channel.send(embed=embed)
            
            # Получить владельца тикета
            owner_id = None
            if channel.topic and "Ticket sahibi:" in channel.topic:
                try:
                    owner_id = int(channel.topic.split("Ticket sahibi:")[-1].strip())
                except Exception as _ex:
                    _log.debug("_close_inactive_ticket(): подавлено: %s", _ex)
            
            # Отправить DM владельцу
            if owner_id:
                try:
                    owner = await channel.guild.fetch_member(owner_id)
                    dm_embed = discord.Embed(
                        title="⏰ Ваш тикет закрыт",
                        description=(
                            f"Ваш тикет **{channel.name}** был автоматически закрыт "
                            f"из-за неактивности (более {self.inactive_hours} часов).\n\n"
                            "Если проблема не решена, создайте новый тикет."
                        ),
                        color=0xF39C12,
                        timestamp=datetime.now(timezone.utc).replace(tzinfo=None)
                    )
                    await owner.send(embed=dm_embed)
                except Exception as e:
                    logger.debug(f"[AutoClose] Не удалось отправить DM: {e}")
            
            # Сохранить транскрипт
            messages = []
            async for msg in channel.history(limit=200, oldest_first=True):
                if not msg.author.bot:
                    messages.append(
                        f"[{msg.created_at.strftime('%d.%m.%Y %H:%M:%S')}] "
                        f"{msg.author.display_name}: {msg.content}"
                    )
            
            # Отправить в лог-канал
            log_channel = discord.utils.get(channel.guild.text_channels, name="ticket-log")
            if log_channel:
                import io
                transcript = "\n".join(messages) if messages else "Сообщений не найдено."
                log_embed = discord.Embed(
                    title=" Тикет закрыт автоматически (неактивность)",
                    description=f"**Канал:** {channel.name}\n**Сообщений:** {len(messages)}",
                    color=0xF39C12,
                    timestamp=datetime.now(timezone.utc).replace(tzinfo=None)
                )
                file = discord.File(
                    fp=io.StringIO(transcript),
                    filename=f"{channel.name}_auto_closed.txt"
                )
                await log_channel.send(embed=log_embed, file=file)
            
            # Очистить состояние
            cog._delete_ticket_state(channel.guild.id, channel.id)
            
            # Удалить канал
            await asyncio.sleep(2)  # Дать время на отправку сообщений
            await channel.delete(reason=f"Автоматическое закрытие (неактивность {self.inactive_hours}ч)")
            
            logger.info(f"[AutoClose] Тикет {channel.name} закрыт (неактивность)")
            
        except Exception as e:
            logger.error(f"[AutoClose] Ошибка закрытия {channel.name}: {e}")
    
    def set_inactive_hours(self, hours: int):
        """Установить порог неактивности"""
        self.inactive_hours = max(1, min(168, hours))  # От 1 часа до 7 дней
        logger.info(f"[AutoClose] Порог неактивности: {self.inactive_hours} часов")


# Глобальный instance
_auto_close_service: Optional[AutoCloseService] = None


def get_auto_close_service(bot=None) -> AutoCloseService:
    """Получить глобальный instance сервиса"""
    global _auto_close_service
    if _auto_close_service is None and bot is not None:
        _auto_close_service = AutoCloseService(bot)
    return _auto_close_service
