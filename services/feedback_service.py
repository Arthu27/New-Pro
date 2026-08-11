"""
Сервис обратной связи для системы тикетов
Сбор и анализ отзывов пользователей
"""

import json
import os
from datetime import datetime, timezone
from typing import Optional, Dict, List
import logging

logger = logging.getLogger('ticket.feedback')


class FeedbackService:
    """Сервис для управления отзывами пользователей"""
    
    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.data_file = os.path.join(data_dir, "ticket_feedback.json")
        self._data: Dict = {}
        self._load_data()
    
    def _load_data(self):
        """Загрузить данные из файла"""
        try:
            os.makedirs(self.data_dir, exist_ok=True)
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    self._data = json.load(f)
                logger.info(f"[Feedback] Загружено {len(self._data.get('feedbacks', []))} отзывов")
            else:
                self._data = {'feedbacks': []}
                logger.info("[Feedback] Создан новый файл отзывов")
        except Exception as e:
            logger.error(f"[Feedback] Ошибка загрузки: {e}")
            self._data = {'feedbacks': []}
    
    def _save_data(self):
        """Сохранить данные в файл"""
        try:
            tmp_file = self.data_file + '.tmp'
            with open(tmp_file, 'w', encoding='utf-8') as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_file, self.data_file)
            logger.debug("[Feedback] Данные сохранены")
        except Exception as e:
            logger.error(f"[Feedback] Ошибка сохранения: {e}")
    
    def add_feedback(
        self,
        guild_id: int,
        user_id: int,
        ticket_channel: str,
        rating: str,  # 'positive' или 'negative'
        comment: Optional[str] = None,
        closed_by: Optional[int] = None
    ):
        """Добавить отзыв"""
        feedback = {
            'guild_id': guild_id,
            'user_id': user_id,
            'ticket_channel': ticket_channel,
            'rating': rating,
            'comment': comment,
            'closed_by': closed_by,
            'timestamp': datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        }
        
        self._data['feedbacks'].append(feedback)
        self._save_data()
        
        logger.info(
            f"[Feedback] Добавлен отзыв: user={user_id} rating={rating} "
            f"ticket={ticket_channel}"
        )
        return feedback
    
    def get_guild_stats(self, guild_id: int) -> Dict:
        """Получить статистику по серверу"""
        feedbacks = [
            f for f in self._data['feedbacks']
            if f['guild_id'] == guild_id
        ]
        
        if not feedbacks:
            return {
                'total': 0,
                'positive': 0,
                'negative': 0,
                'positive_percent': 0,
                'negative_percent': 0,
                'avg_rating': 0,
                'comments': []
            }
        
        positive = sum(1 for f in feedbacks if f['rating'] == 'positive')
        negative = len(feedbacks) - positive
        total = len(feedbacks)
        
        return {
            'total': total,
            'positive': positive,
            'negative': negative,
            'positive_percent': round((positive / total) * 100, 1),
            'negative_percent': round((negative / total) * 100, 1),
            'avg_rating': round(positive / total, 2),
            'comments': [f['comment'] for f in feedbacks if f.get('comment')][-10:]  # Последние 10
        }
    
    def get_user_feedbacks(self, guild_id: int, user_id: int) -> List[Dict]:
        """Получить все отзывы пользователя"""
        return [
            f for f in self._data['feedbacks']
            if f['guild_id'] == guild_id and f['user_id'] == user_id
        ]
    
    def get_recent_feedbacks(self, guild_id: int, limit: int = 10) -> List[Dict]:
        """Получить последние отзывы"""
        feedbacks = [
            f for f in self._data['feedbacks']
            if f['guild_id'] == guild_id
        ]
        return feedbacks[-limit:]


# Глобальный instance
_feedback_service_instance: Optional[FeedbackService] = None


def get_feedback_service() -> FeedbackService:
    """Получить глобальный instance сервиса отзывов"""
    global _feedback_service_instance
    if _feedback_service_instance is None:
        _feedback_service_instance = FeedbackService()
    return _feedback_service_instance
