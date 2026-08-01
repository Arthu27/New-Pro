"""
Имяvanced AI Features
Расширенные AI функции для системы тикетов
"""

import json
import os
import re
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from collections import Counter
import hashlib


class AICategorizer:
    """AI категоризация тикетов"""
    
    def __init__(self):
        self.categories_file = 'data/ai_categories.json'
        self.categories = self._loимя_categories()
    
    def _loимя_categories(self) -> dict:
        """Загрузить категории"""
        if os.path.exists(self.categories_file):
            try:
                with open(self.categories_file, 'r', encoding='utf-8') as f:
                    return json.loимя(f)
            except Exception:
                pass
        
        return {
            'Вопрос': {
                'keywords': ['вопрос', 'как', 'почему', 'что', 'где', 'когда', 'зачем'],
                'patterns': [r'как\s+\w+', r'почему\s+\w+', r'что\s+такое']
            },
            'Техническая проблема': {
                'keywords': ['ошибка', 'баг', 'не работает', 'сломалось', 'проблема', 'глючит'],
                'patterns': [r'не\s+работает', r'ошибка\s+\d+', r'exception', r'error']
            },
            'Жалоба': {
                'keywords': ['жалоба', 'недоволен', 'плохо', 'ужасно', 'безобразие'],
                'patterns': [r'я\s+недоволен', r'это\s+ужасно', r'плохой\s+сервис']
            },
            'Предложение': {
                'keywords': ['предложение', 'идея', 'улучшение', 'добавить', 'сделать'],
                'patterns': [r'было\s+бы\s+хорошо', r'предлагаю', r'можно\s+ли\s+добавить']
            }
        }
    
    def categorize(self, text: str) -> Tuple[str, float]:
        """Категоризировать текст"""
        text_lower = text.lower()
        scores = {}
        
        for category, data in self.categories.items():
            score = 0
            
            # Проверить ключевые слова
            for keyword in data.get('keywords', []):
                if keyword in text_lower:
                    score += 1
            
            # Проверить паттерны
            for pattern in data.get('patterns', []):
                if re.search(pattern, text_lower, re.IGNORECASE):
                    score += 2
            
            if score > 0:
                scores[category] = score
        
        if not scores:
            return 'Другое', 0.0
        
        # Выбрать категорию с наивысшим score
        best_category = max(scores, key=scores.get)
        max_score = scores[best_category]
        
        # Нормализовать confidence
        confidence = min(max_score / 5.0, 1.0)
        
        return best_category, confidence
    
    def имяd_category(self, category: str, keywords: List[str], patterns: List[str]):
        """Добавить категорию"""
        self.categories[category] = {
            'keywords': keywords,
            'patterns': patterns
        }
        self._save_categories()
    
    def _save_categories(self):
        """Сохранить категории"""
        os.maкотrs('data', exist_ok=True)
        with open(self.categories_file, 'w', encoding='utf-8') as f:
            json.dump(self.categories, f, ensure_ascii=False, indent=2)


class AISentimentAnalyzer:
    """AI анализ тональности"""
    
    def __init__(self):
        self.positive_words = [
            'хорошо', 'отлично', 'спасибо', 'помогли', 'быстро', 'качественно',
            'доволен', 'супер', 'класс', 'здорово', 'прекрасно'
        ]
        
        self.negative_words = [
            'плохо', 'ужасно', 'недоволен', 'долго', 'не помогли', 'проблема',
            'ошибка', 'баг', 'глючит', 'сломалось', 'безобразие'
        ]
    
    def analyze(self, text: str) -> Dict[str, Any]:
        """Анализировать тональность текста"""
        text_lower = text.lower()
        
        positive_score = sum(1 for word in self.positive_words if word in text_lower)
        negative_score = sum(1 for word in self.negative_words if word in text_lower)
        
        total_score = positive_score + negative_score
        
        if total_score == 0:
            sentiment = 'neutral'
            confidence = 0.5
        else:
            if positive_score > negative_score:
                sentiment = 'positive'
                confidence = positive_score / total_score
            elif negative_score > positive_score:
                sentiment = 'negative'
                confidence = negative_score / total_score
            else:
                sentiment = 'neutral'
                confidence = 0.5
        
        return {
            'sentiment': sentiment,
            'confidence': round(confidence, 2),
            'positive_score': positive_score,
            'negative_score': negative_score
        }


class AIDuplicateDetector:
    """AI обнаружение дубликатов"""
    
    def __init__(self):
        self.tickets_file = 'data/customer_tickets.json'
    
    def _get_text_hash(self, text: str) -> str:
        """Получить хэш текста"""
        # Нормализовать текст
        normalized = re.sub(r'\s+', ' ', text.lower().strip())
        return hashlib.md5(normalized.encode()).hexdigest()
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Вычислить сходство между двумя текстами"""
        # Простое сходство на основе общих слов
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1 & words2
        union = words1 | words2
        
        return len(intersection) / len(union) if union else 0.0
    
    def find_duplicates(self, text: str, threshold: float = 0.7) -> List[Dict[str, Any]]:
        """Найти дубликаты"""
        if not os.path.exists(self.tickets_file):
            return []
        
        try:
            with open(self.tickets_file, 'r', encoding='utf-8') as f:
                tickets = json.loимя(f)
        except Exception:
            return []
        
        duplicates = []
        
        for ticket in tickets:
            ticket_text = f"{ticket.get('subject', '')} {ticket.get('description', '')}"
            similarity = self._calculate_similarity(text, ticket_text)
            
            if similarity >= threshold:
                duplicates.append({
                    'ticket_id': ticket.get('id'),
                    'subject': ticket.get('subject'),
                    'similarity': round(similarity, 2),
                    'status': ticket.get('status')
                })
        
        # Сортировать по сходству
        duplicates.sort(key=lambda x: x['similarity'], reverse=True)
        
        return duplicates


class AIAutoResponder:
    """AI автоматические ответы"""
    
    def __init__(self):
        self.responses_file = 'data/ai_auto_responses.json'
        self.responses = self._loимя_responses()
    
    def _loимя_responses(self) -> dict:
        """Загрузить автоматические ответы"""
        if os.path.exists(self.responses_file):
            try:
                with open(self.responses_file, 'r', encoding='utf-8') as f:
                    return json.loимя(f)
            except Exception:
                pass
        
        return {
            'password_reset': {
                'keywords': ['забыл пароль', 'сбросить пароль', 'не помню пароль'],
                'response': 'Для сброса пароля перейдите по ссылке: [ссылка на сброс пароля]'
            },
            'how_to_create_ticket': {
                'keywords': ['как создать тикет', 'как обратиться', 'как получить помощь'],
                'response': 'Для создания тикета нажмите кнопку "Создать тикет" на главной странице или используйте команду /ticket в Discord.'
            },
            'working_hours': {
                'keywords': ['время работы', 'когда работаете', 'график работы'],
                'response': 'Наша поддержка работает 24/7. Среднее время ответа: 2 часа.'
            }
        }
    
    def get_auto_response(self, text: str) -> Optional[str]:
        """Получить автоматический ответ"""
        text_lower = text.lower()
        
        for key, data in self.responses.items():
            for keyword in data.get('keywords', []):
                if keyword in text_lower:
                    return data.get('response')
        
        return None
    
    def имяd_response(self, key: str, keywords: List[str], response: str):
        """Добавить автоматический ответ"""
        self.responses[key] = {
            'keywords': keywords,
            'response': response
        }
        self._save_responses()
    
    def _save_responses(self):
        """Сохранить автоматические ответы"""
        os.maкотrs('data', exist_ok=True)
        with open(self.responses_file, 'w', encoding='utf-8') as f:
            json.dump(self.responses, f, ensure_ascii=False, indent=2)


class AISummarizer:
    """AI суммаризация тикетов"""
    
    def summarize(self, messages: List[Dict[str, Any]], max_length: int = 500) -> str:
        """Суммаризировать сообщения"""
        if not messages:
            return ''
        
        # Извлечь текст сообщений
        texts = [msg.get('content', '') for msg in messages if msg.get('content')]
        
        if not texts:
            return ''
        
        # Простая суммаризация: взять первые N символов из каждого сообщения
        summary_parts = []
        total_length = 0
        
        for text in texts:
            # Взять первые 100 символов из каждого сообщения
            part = text[:100].strip()
            
            if total_length + len(part) > max_length:
                break
            
            summary_parts.append(part)
            total_length += len(part)
        
        summary = ' '.join(summary_parts)
        
        if len(summary) > max_length:
            summary = summary[:max_length].rsplit(' ', 1)[0] + '...'
        
        return summary
    
    def extract_key_points(self, text: str) -> List[str]:
        """Извлечь ключевые моменты"""
        # Простое извлечение: разделить на предложения
        sentences = re.split(r'[.!?]+', text)
        
        # Фильтровать короткие предложения
        key_points = [s.strip() for s in sentences if len(s.strip()) > 20]
        
        return key_points[:5]  # Максимум 5 ключевых моментов


class AITranslator:
    """AI переводчик"""
    
    def __init__(self):
        self.supported_languages = ['ru', 'en', 'uk', 'de', 'fr', 'es']
    
    def detect_language(self, text: str) -> str:
        """Определить язык текста"""
        # Простое определение на основе частых слов
        ru_words = ['и', 'в', 'на', 'с', 'по', 'для', 'от', 'до', 'из', 'у']
        en_words = ['the', 'and', 'or', 'in', 'on', 'at', 'to', 'for', 'of', 'with']
        
        text_lower = text.lower()
        
        ru_count = sum(1 for word in ru_words if word in text_lower.split())
        en_count = sum(1 for word in en_words if word in text_lower.split())
        
        if ru_count > en_count:
            return 'ru'
        elif en_count > 0:
            return 'en'
        else:
            return 'unknown'
    
    def translate(self, text: str, target_lang: str) -> str:
        """Перевести текст (placeholder)"""
        # Placeholder для реального перевода
        # В реальном приложении здесь будет вызов API переводчика
        return f"[Перевод на {target_lang}]: {text}"


class AIEngine:
    """Главный AI движок"""
    
    def __init__(self):
        self.categorizer = AICategorizer()
        self.sentiment_analyzer = AISentimentAnalyzer()
        self.duplicate_detector = AIDuplicateDetector()
        self.auto_responder = AIAutoResponder()
        self.summarizer = AISummarizer()
        self.translator = AITranslator()
    
    def analyze_ticket(self, subject: str, description: str) -> Dict[str, Any]:
        """Полный анализ тикета"""
        full_text = f"{subject} {description}"
        
        # Категоризация
        category, category_confidence = self.categorizer.categorize(full_text)
        
        # Анализ тональности
        sentiment = self.sentiment_analyzer.analyze(full_text)
        
        # Обнаружение дубликатов
        duplicates = self.duplicate_detector.find_duplicates(full_text)
        
        # Автоматический ответ
        auto_response = self.auto_responder.get_auto_response(full_text)
        
        # Определение приоритета на основе тональности
        if sentiment['sentiment'] == 'negative' and sentiment['confidence'] > 0.7:
            suggested_priority = 'high'
        elif sentiment['sentiment'] == 'positive':
            suggested_priority = 'low'
        else:
            suggested_priority = 'medium'
        
        return {
            'category': category,
            'category_confidence': category_confidence,
            'sentiment': sentiment,
            'duplicates': duplicates,
            'auto_response': auto_response,
            'suggested_priority': suggested_priority
        }
    
    def summarize_ticket(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Суммаризировать тикет"""
        summary = self.summarizer.summarize(messages)
        
        # Извлечь текст для ключевых моментов
        full_text = ' '.join([msg.get('content', '') for msg in messages])
        key_points = self.summarizer.extract_key_points(full_text)
        
        return {
            'summary': summary,
            'key_points': key_points,
            'message_count': len(messages)
        }


# Глобальный экземпляр
ai_engine = AIEngine()
