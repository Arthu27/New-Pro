"""
Rate Limiter Service для системы тикетов
Защита от спама и злоупотреблений
"""

import json
import os
import time
import asyncio
from datetime import datetime, timedelta
from typing import Tuple, Optional, Dict, List
import logging

logger = logging.getLogger('ticket.rate_limiter')


class RateLimitResult:
    """Результат проверки rate limit"""
    def __init__(self, allowed: bool, reason: str = None, wait_seconds: int = 0, 
                 remaining: int = 0, limit: int = 0):
        self.allowed = allowed
        self.reason = reason
        self.wait_seconds = wait_seconds
        self.remaining = remaining
        self.limit = limit
    
    def __bool__(self):
        return self.allowed


class RateLimiter:
    """
    Rate Limiter для тикетов
    
    Поддерживает:
    - Лимит тикетов за 24 часа (рольling window)
    - Кулдаун между созданием тикетов
    - Персистентное хранение (JSON)
    - Threимя-safe операции
    """
    
    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.data_file = os.path.join(data_dir, "ticket_rate_limits.json")
        self._lock = asyncio.Lock()
        self._data: Dict = {}
        self._loимя_data()
        
        # Дефолтные лимиты (могут быть переопределены через config)
        self.default_limits = {
            'max_tickets_per_24h': 3,
            'cooldown_seconds': 60,
            'max_tickets_per_week': 10,
            'max_tickets_per_month': 30,
        }
    
    def _loимя_data(self):
        """Загрузить данные из файла"""
        try:
            os.maкотrs(self.data_dir, exist_ok=True)
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    self._data = json.loимя(f)
                logger.info(f"[RateLimiter] Загружены данные: {len(self._data)} пользователей")
            else:
                self._data = {}
                logger.info("[RateLimiter] Создан новый файл rate limits")
        except Exception as e:
            logger.error(f"[RateLimiter] Ошибка загрузки данных: {e}")
            self._data = {}
    
    def _save_data(self):
        """Сохранить данные в файл (атомарная запись)"""
        try:
            os.maкотrs(self.data_dir, exist_ok=True)
            tmp_file = self.data_file + '.tmp'
            with open(tmp_file, 'w', encoding='utf-8') as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_file, self.data_file)
            logger.debug("[RateLimiter] Данные сохранены")
        except Exception as e:
            logger.error(f"[RateLimiter] Ошибка сохранения данных: {e}")
    
    def _get_user_key(self, guild_id: int, user_id: int) -> str:
        """Получить уникальный ключ для пользователя"""
        return f"{guild_id}:{user_id}"
    
    def _cleanup_old_entries(self, user_data: dict, cutoff_timestamp: float):
        """Удалить старые записи"""
        if 'tickets' in user_data:
            user_data['tickets'] = [
                ts for ts in user_data['tickets'] 
                if ts > cutoff_timestamp
            ]
    
    async def check_ticket_limit(
        self, 
        guild_id: int, 
        user_id: int,
        limits: Optional[dict] = None
    ) -> RateLimitResult:
        """
        Проверить, может ли пользователь создать новый тикет
        
        Args:
            guild_id: ID сервера
            user_id: ID пользователя
            limits: Опциональные кастомные лимиты
            
        Returns:
            RateLimitResult с информацией о результате
        """
        limits = limits or self.default_limits
        
        async with self._lock:
            key = self._get_user_key(guild_id, user_id)
            
            # Инициализировать данные пользователя если нужно
            if key not in self._data:
                self._data[key] = {
                    'tickets': [],
                    'last_ticket': 0,
                    'guild_id': guild_id,
                    'user_id': user_id,
                }
            
            user_data = self._data[key]
            now = time.time()
            
            # 1. Проверить кулдаун
            cooldown = limits.get('cooldown_seconds', 60)
            time_since_last = now - user_data.get('last_ticket', 0)
            
            if time_since_last < cooldown:
                wait_seconds = int(cooldown - time_since_last)
                logger.info(
                    f"[RateLimiter] Кулдаун активен: {user_id} должен подождать {wait_seconds}с"
                )
                return RateLimitResult(
                    allowed=False,
                    reason=f"Подождите {wait_seconds} секунд перед созданием нового тикета",
                    wait_seconds=wait_seconds,
                    remaining=0,
                    limit=limits.get('max_tickets_per_24h', 3)
                )
            
            # 2. Проверить лимит за 24 часа
            cutoff_24h = now - (24 * 3600)
            self._cleanup_old_entries(user_data, cutoff_24h)
            
            tickets_24h = len(user_data['tickets'])
            max_24h = limits.get('max_tickets_per_24h', 3)
            
            if tickets_24h >= max_24h:
                # Найти когда будет доступен следующий слот
                oldest_ticket = min(user_data['tickets']) if user_data['tickets'] else now
                wait_seconds = int((oldest_ticket + 24*3600) - now)
                
                logger.info(
                    f"[RateLimiter] Лимит 24ч превышен: {user_id} ({tickets_24h}/{max_24h})"
                )
                return RateLimitResult(
                    allowed=False,
                    reason=f"Превышен лимит тикетов за 24 часа ({max_24h}). Попробуйте позже.",
                    wait_seconds=wait_seconds,
                    remaining=0,
                    limit=max_24h
                )
            
            # 3. Проверить лимит за неделю
            cutoff_week = now - (7 * 24 * 3600)
            tickets_week = len([ts for ts in user_data['tickets'] if ts > cutoff_week])
            max_week = limits.get('max_tickets_per_week', 10)
            
            if tickets_week >= max_week:
                logger.info(
                    f"[RateLimiter] Лимит недели превышен: {user_id} ({tickets_week}/{max_week})"
                )
                return RateLimitResult(
                    allowed=False,
                    reason=f"Превышен недельный лимит тикетов ({max_week}).",
                    wait_seconds=int((cutoff_week + 7*24*3600) - now),
                    remaining=0,
                    limit=max_week
                )
            
            # Все проверки пройдены
            remaining = max_24h - tickets_24h - 1  # -1 потому что сейчас создаст
            logger.info(
                f"[RateLimiter] Проверка пройдена: {user_id} (осталось: {remaining}/{max_24h})"
            )
            
            return RateLimitResult(
                allowed=True,
                remaining=remaining,
                limit=max_24h
            )
    
    async def record_ticket_creation(self, guild_id: int, user_id: int):
        """
        Записать создание тикета
        
        Вызывать после успешного создания тикета
        """
        async with self._lock:
            key = self._get_user_key(guild_id, user_id)
            now = time.time()
            
            if key not in self._data:
                self._data[key] = {
                    'tickets': [],
                    'last_ticket': 0,
                    'guild_id': guild_id,
                    'user_id': user_id,
                }
            
            self._data[key]['tickets'].append(now)
            self._data[key]['last_ticket'] = now
            
            self._save_data()
            logger.info(f"[RateLimiter] Тикет записан: {user_id} в {guild_id}")
    
    async def get_user_stats(self, guild_id: int, user_id: int) -> dict:
        """Получить статистику пользователя"""
        async with self._lock:
            key = self._get_user_key(guild_id, user_id)
            
            if key not in self._data:
                return {
                    'tickets_24h': 0,
                    'tickets_week': 0,
                    'tickets_month': 0,
                    'last_ticket': None,
                    'cooldown_remaining': 0,
                }
            
            user_data = self._data[key]
            now = time.time()
            
            cutoff_24h = now - (24 * 3600)
            cutoff_week = now - (7 * 24 * 3600)
            cutoff_month = now - (30 * 24 * 3600)
            
            tickets_24h = len([ts for ts in user_data['tickets'] if ts > cutoff_24h])
            tickets_week = len([ts for ts in user_data['tickets'] if ts > cutoff_week])
            tickets_month = len([ts for ts in user_data['tickets'] if ts > cutoff_month])
            
            last_ticket_ts = user_data.get('last_ticket', 0)
            cooldown_remaining = max(
                0, 
                int(self.default_limits['cooldown_seconds'] - (now - last_ticket_ts))
            )
            
            return {
                'tickets_24h': tickets_24h,
                'tickets_week': tickets_week,
                'tickets_month': tickets_month,
                'last_ticket': datetime.fromtimestamp(last_ticket_ts) if last_ticket_ts else None,
                'cooldown_remaining': cooldown_remaining,
            }
    
    async def reset_user(self, guild_id: int, user_id: int):
        """Сбросить rate limit для пользователя (для админов)"""
        async with self._lock:
            key = self._get_user_key(guild_id, user_id)
            if key in self._data:
                del self._data[key]
                self._save_data()
                logger.info(f"[RateLimiter] Сброшен rate limit для {user_id} в {guild_id}")
    
    async def cleanup_old_data(self, days: int = 30):
        """Очистить старые данные (старше X дней)"""
        async with self._lock:
            cutoff = time.time() - (days * 24 * 3600)
            keys_to_delete = []
            
            for key, data in self._data.items():
                if not data.get('tickets'):
                    keys_to_delete.append(key)
                elif max(data['tickets']) < cutoff:
                    keys_to_delete.append(key)
            
            for key in keys_to_delete:
                del self._data[key]
            
            if keys_to_delete:
                self._save_data()
                logger.info(f"[RateLimiter] Очищено {len(keys_to_delete)} старых записей")


# Глобальный instance
_rate_limiter_instance: Optional[RateLimiter] = None

def get_rate_limiter() -> RateLimiter:
    """Получить глобальный instance rate limiter"""
    global _rate_limiter_instance
    if _rate_limiter_instance is None:
        _rate_limiter_instance = RateLimiter()
    return _rate_limiter_instance
