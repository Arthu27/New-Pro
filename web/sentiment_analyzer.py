"""
Анализ настроений сервера в реальном времени
Отслеживание эмоций, тона, конфликтов
"""
import discord
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
import re


class SentimentAnalyzer:
    """Анализатор настроений сервера"""
    
    # Паттерны для определения эмоций
    EMOTION_PATTERNS = {
        'positive': [
            r'\b(спасибо|благодарю|отлично|круто|супер|класс|здорово|прекрасно|замечательно)\b',
            r'\b(хорошо|нормально|ок|окй|ладно|понял|принял)\b',
            r'\b(люблю|нравится|обожаю|кайф|восторг)\b',
            r'\b(рад|рада|счастлив|счастлива|доволен|довольна)\b',
            r'[:\)]+|[:D]+|[❤️💖😊😄🎉👍]+',
        ],
        'negative': [
            r'\b(бесит|злюсь|ненавижу|раздражает|достало|задолбало)\b',
            r'\b(плохо|ужасно|отвратительно|кошмар|жесть)\b',
            r'\b(грустно|печально|тоскливо|одиноко|депрессия)\b',
            r'\b(устал|устала|вымотался|вымоталась|без сил)\b',
            r'\b(тупой|тупая|идиот|дебил|дурак)\b',
            r'[:\(]+|[:\[]+|[😢😭😡🤬💔👎]+',
        ],
        'neutral': [
            r'\b(вопрос|подскажите|объясните|расскажите)\b',
            r'\b(интересно|любопытно|хм|хмм)\b',
        ],
    }
    
    # Весовые коэффициенты для эмоций
    EMOTION_WEIGHTS = {
        'positive': 1.0,
        'negative': -1.0,
        'neutral': 0.0,
    }
    
    def __init__(self):
        self.message_buffer = defaultdict(list)  # channel_id -> messages
        self.sentiment_cache = {}  # channel_id -> sentiment_data
        self.alerts_sent = set()  # Предотвращение спама алертов
        
        # Загружаем историю
        self._load_history()
    
    def analyze_message(self, message: discord.Message) -> Dict:
        """Анализирует одно сообщение"""
        content = message.content.lower()
        
        # Определяем эмоции
        emotions = self._detect_emotions(content)
        
        # Определяем доминирующую эмоцию
        dominant = max(emotions, key=emotions.get) if emotions else 'neutral'
        
        # Вычисляем скор
        score = sum(
            emotions[emotion] * self.EMOTION_WEIGHTS[emotion]
            for emotion in emotions
        )
        
        result = {
            'message_id': message.id,
            'author_id': message.author.id,
            'author_name': str(message.author),
            'channel_id': message.channel.id,
            'channel_name': message.channel.name,
            'content': message.content[:200],  # Ограничиваем длину
            'emotions': emotions,
            'dominant_emotion': dominant,
            'sentiment_score': score,
            'timestamp': datetime.utcnow().isoformat(),
        }
        
        # Добавляем в буфер
        self.message_buffer[message.channel.id].append(result)
        
        # Ограничиваем буфер
        if len(self.message_buffer[message.channel.id]) > 100:
            self.message_buffer[message.channel.id] = self.message_buffer[message.channel.id][-100:]
        
        return result
    
    def _detect_emotions(self, content: str) -> Dict[str, float]:
        """Определяет эмоции в тексте"""
        emotions = {'positive': 0.0, 'negative': 0.0, 'neutral': 0.0}
        
        for emotion, patterns in self.EMOTION_PATTERNS.items():
            for pattern in patterns:
                matches = len(re.findall(pattern, content, re.IGNORECASE))
                emotions[emotion] += matches
        
        # Нормализуем
        total = sum(emotions.values())
        if total > 0:
            emotions = {k: v / total for k, v in emotions.items()}
        
        return emotions
    
    def get_channel_sentiment(self, channel_id: int, window_minutes: int = 60) -> Dict:
        """Получает настроение канала за последние N минут"""
        messages = self.message_buffer.get(channel_id, [])
        
        # Фильтруем по времени
        cutoff = datetime.utcnow() - timedelta(minutes=window_minutes)
        recent = [
            msg for msg in messages
            if datetime.fromisoformat(msg['timestamp']) > cutoff
        ]
        
        if not recent:
            return {
                'channel_id': channel_id,
                'message_count': 0,
                'avg_sentiment': 0.0,
                'dominant_emotion': 'neutral',
                'emotion_breakdown': {'positive': 0, 'negative': 0, 'neutral': 0},
                'trend': 'stable'
            }
        
        # Вычисляем среднее настроение
        avg_sentiment = sum(msg['sentiment_score'] for msg in recent) / len(recent)
        
        # Подсчитываем эмоции
        emotion_counts = {'positive': 0, 'negative': 0, 'neutral': 0}
        for msg in recent:
            emotion_counts[msg['dominant_emotion']] += 1
        
        # Определяем тренд (сравниваем первую и вторую половину)
        mid = len(recent) // 2
        if mid > 0:
            first_half_avg = sum(msg['sentiment_score'] for msg in recent[:mid]) / mid
            second_half_avg = sum(msg['sentiment_score'] for msg in recent[mid:]) / (len(recent) - mid)
            
            if second_half_avg > first_half_avg + 0.1:
                trend = 'improving'
            elif second_half_avg < first_half_avg - 0.1:
                trend = 'declining'
            else:
                trend = 'stable'
        else:
            trend = 'stable'
        
        result = {
            'channel_id': channel_id,
            'message_count': len(recent),
            'avg_sentiment': round(avg_sentiment, 2),
            'dominant_emotion': max(emotion_counts, key=emotion_counts.get),
            'emotion_breakdown': emotion_counts,
            'trend': trend
        }
        
        # Кэшируем
        self.sentiment_cache[channel_id] = result
        
        return result
    
    def get_server_sentiment(self, guild: discord.Guild, window_minutes: int = 60) -> Dict:
        """Получает общее настроение сервера"""
        channel_sentiments = []
        
        for channel in guild.text_channels:
            sentiment = self.get_channel_sentiment(channel.id, window_minutes)
            if sentiment['message_count'] > 0:
                channel_sentiments.append(sentiment)
        
        if not channel_sentiments:
            return {
                'guild_id': guild.id,
                'guild_name': guild.name,
                'total_messages': 0,
                'avg_sentiment': 0.0,
                'dominant_emotion': 'neutral',
                'mood': 'neutral',
                'channels': {}
            }
        
        # Вычисляем среднее по серверу
        total_messages = sum(s['message_count'] for s in channel_sentiments)
        avg_sentiment = sum(
            s['avg_sentiment'] * s['message_count'] for s in channel_sentiments
        ) / total_messages
        
        # Определяем общее настроение
        if avg_sentiment > 0.3:
            mood = 'very_positive'
        elif avg_sentiment > 0.1:
            mood = 'positive'
        elif avg_sentiment < -0.3:
            mood = 'very_negative'
        elif avg_sentiment < -0.1:
            mood = 'negative'
        else:
            mood = 'neutral'
        
        # Собираем эмоции
        total_emotions = {'positive': 0, 'negative': 0, 'neutral': 0}
        for s in channel_sentiments:
            for emotion, count in s['emotion_breakdown'].items():
                total_emotions[emotion] += count
        
        return {
            'guild_id': guild.id,
            'guild_name': guild.name,
            'total_messages': total_messages,
            'avg_sentiment': round(avg_sentiment, 2),
            'dominant_emotion': max(total_emotions, key=total_emotions.get),
            'mood': mood,
            'channels': {s['channel_id']: s for s in channel_sentiments}
        }
    
    async def check_for_alerts(self, guild: discord.Guild) -> List[Dict]:
        """Проверяет нужны ли алерты о настроении"""
        alerts = []
        
        for channel in guild.text_channels:
            sentiment = self.get_channel_sentiment(channel.id, window_minutes=30)
            
            # Алерт если очень негативное настроение
            if sentiment['avg_sentiment'] < -0.5 and sentiment['message_count'] >= 5:
                alert_key = f"{channel.id}_negative"
                if alert_key not in self.alerts_sent:
                    alerts.append({
                        'type': 'negative_sentiment',
                        'channel_id': channel.id,
                        'channel_name': channel.name,
                        'sentiment': sentiment['avg_sentiment'],
                        'message_count': sentiment['message_count'],
                        'message': f"⚠️ Негативное настроение в #{channel.name} ({sentiment['avg_sentiment']})"
                    })
                    self.alerts_sent.add(alert_key)
                    
                    # Сбрасываем алерт через 10 минут
                    import asyncio
                    asyncio.create_task(self._reset_alert(alert_key, delay=600))
            
            # Алерт если конфликт (много негатива за короткое время)
            recent_10min = self.get_channel_sentiment(channel.id, window_minutes=10)
            if recent_10min['emotion_breakdown']['negative'] >= 5:
                alert_key = f"{channel.id}_conflict"
                if alert_key not in self.alerts_sent:
                    alerts.append({
                        'type': 'potential_conflict',
                        'channel_id': channel.id,
                        'channel_name': channel.name,
                        'negative_messages': recent_10min['emotion_breakdown']['negative'],
                        'message': f"🔥 Возможный конфликт в #{channel.name} ({recent_10min['emotion_breakdown']['negative']} негативных сообщений)"
                    })
                    self.alerts_sent.add(alert_key)
                    asyncio.create_task(self._reset_alert(alert_key, delay=300))
        
        return alerts
    
    async def _reset_alert(self, alert_key: str, delay: int):
        """Сбрасывает алерт через N секунд"""
        import asyncio
        await asyncio.sleep(delay)
        self.alerts_sent.discard(alert_key)
    
    def _load_history(self):
        """Загружает историю из файла"""
        history_file = 'data/sentiment_history.json'
        if os.path.exists(history_file):
            try:
                with open(history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for channel_id, messages in data.items():
                        self.message_buffer[int(channel_id)] = messages
            except:
                pass
    
    def _save_history(self):
        """Сохраняет историю в файл"""
        try:
            os.makedirs('data', exist_ok=True)
            history_file = 'data/sentiment_history.json'
            
            # Сохраняем только последние 50 сообщений на канал
            data = {
                str(channel_id): messages[-50:]
                for channel_id, messages in self.message_buffer.items()
            }
            
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except:
            pass


# Глобальный экземпляр
_sentiment_analyzer = None

def get_sentiment_analyzer() -> SentimentAnalyzer:
    """Получает глобальный экземпляр SentimentAnalyzer"""
    global _sentiment_analyzer
    if _sentiment_analyzer is None:
        _sentiment_analyzer = SentimentAnalyzer()
    return _sentiment_analyzer
