"""
Самообучение — AI учится на своих ошибках и успехах
Анализ обратной связи, корректировка поведения
"""
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from collections import defaultdict


class SelfLearning:
    """Система самообучения AI"""
    
    def __init__(self):
        self.feedback_log = []  # Логи обратной связи
        self.learned_patterns = {}  # Выученные паттерны
        self.mistakes = []  # Ошибки AI
        self.successes = []  # Успешные ответы
        
        # Загружаем данные
        self._load_data()
    
    def record_feedback(
        self,
        user_message: str,
        ai_response: str,
        feedback_type: str,
        feedback_details: Dict = None
    ):
        """Записывает обратную связь"""
        entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'user_message': user_message,
            'ai_response': ai_response,
            'feedback_type': feedback_type,  # 'positive', 'negative', 'correction'
            'details': feedback_details or {}
        }
        
        self.feedback_log.append(entry)
        
        # Ограничиваем лог
        if len(self.feedback_log) > 1000:
            self.feedback_log = self.feedback_log[-1000:]
        
        # Анализируем и обучаемся
        self._analyze_and_learn(entry)
        
        # Сохраняем
        self._save_data()
    
    def record_mistake(
        self,
        user_message: str,
        ai_response: str,
        correct_response: str,
        mistake_type: str
    ):
        """Записывает ошибку AI"""
        mistake = {
            'timestamp': datetime.utcnow().isoformat(),
            'user_message': user_message,
            'wrong_response': ai_response,
            'correct_response': correct_response,
            'mistake_type': mistake_type  # 'wrong_info', 'inappropriate', 'misunderstanding'
        }
        
        self.mistakes.append(mistake)
        
        # Ограничиваем
        if len(self.mistakes) > 500:
            self.mistakes = self.mistakes[-500:]
        
        # Учимся на ошибке
        self._learn_from_mistake(mistake)
        
        # Сохраняем
        self._save_data()
    
    def record_success(
        self,
        user_message: str,
        ai_response: str,
        success_type: str
    ):
        """Записывает успешный ответ"""
        success = {
            'timestamp': datetime.utcnow().isoformat(),
            'user_message': user_message,
            'ai_response': ai_response,
            'success_type': success_type  # 'helpful', 'accurate', 'empathetic'
        }
        
        self.successes.append(success)
        
        # Ограничиваем
        if len(self.successes) > 500:
            self.successes = self.successes[-500:]
        
        # Учимся на успехе
        self._learn_from_success(success)
        
        # Сохраняем
        self._save_data()
    
    def _analyze_and_learn(self, feedback: Dict):
        """Анализирует обратную связь и обучается"""
        feedback_type = feedback['feedback_type']
        
        if feedback_type == 'negative':
            # Негативная обратная связь — учимся избегать
            self._learn_from_mistake({
                'user_message': feedback['user_message'],
                'wrong_response': feedback['ai_response'],
                'correct_response': feedback.get('details', {}).get('suggested_response', ''),
                'mistake_type': 'negative_feedback'
            })
        
        elif feedback_type == 'positive':
            # Позитивная обратная связь — запоминаем что работает
            self._learn_from_success({
                'user_message': feedback['user_message'],
                'ai_response': feedback['ai_response'],
                'success_type': 'positive_feedback'
            })
        
        elif feedback_type == 'correction':
            # Корректировка — запоминаем правильный ответ
            correct_response = feedback.get('details', {}).get('correction', '')
            if correct_response:
                self._learn_from_mistake({
                    'user_message': feedback['user_message'],
                    'wrong_response': feedback['ai_response'],
                    'correct_response': correct_response,
                    'mistake_type': 'correction'
                })
    
    def _learn_from_mistake(self, mistake: Dict):
        """Учится на ошибке"""
        user_msg = mistake['user_message'].lower()
        wrong_resp = mistake['wrong_response']
        correct_resp = mistake.get('correct_response', '')
        mistake_type = mistake['mistake_type']
        
        # Извлекаем ключевые слова
        keywords = self._extract_keywords(user_msg)
        
        # Запоминаем паттерн
        pattern_key = f"avoid_{mistake_type}"
        if pattern_key not in self.learned_patterns:
            self.learned_patterns[pattern_key] = []
        
        self.learned_patterns[pattern_key].append({
            'keywords': keywords,
            'wrong_response': wrong_resp[:200],  # Ограничиваем длину
            'correct_response': correct_resp[:200] if correct_resp else '',
            'timestamp': mistake['timestamp']
        })
        
        # Ограничиваем паттерны
        if len(self.learned_patterns[pattern_key]) > 100:
            self.learned_patterns[pattern_key] = self.learned_patterns[pattern_key][-100:]
    
    def _learn_from_success(self, success: Dict):
        """Учится на успехе"""
        user_msg = success['user_message'].lower()
        ai_resp = success['ai_response']
        success_type = success['success_type']
        
        # Извлекаем ключевые слова
        keywords = self._extract_keywords(user_msg)
        
        # Запоминаем паттерн
        pattern_key = f"repeat_{success_type}"
        if pattern_key not in self.learned_patterns:
            self.learned_patterns[pattern_key] = []
        
        self.learned_patterns[pattern_key].append({
            'keywords': keywords,
            'response': ai_resp[:200],  # Ограничиваем длину
            'timestamp': success['timestamp']
        })
        
        # Ограничиваем паттерны
        if len(self.learned_patterns[pattern_key]) > 100:
            self.learned_patterns[pattern_key] = self.learned_patterns[pattern_key][-100:]
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Извлекает ключевые слова из текста"""
        import re
        
        # Убираем стоп-слова
        stop_words = {
            'и', 'в', 'на', 'с', 'по', 'для', 'от', 'до', 'из', 'к', 'у',
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for'
        }
        
        # Извлекаем слова
        words = re.findall(r'\b\w+\b', text.lower())
        
        # Фильтруем
        keywords = [w for w in words if len(w) > 2 and w not in stop_words]
        
        # Убираем дубликаты
        return list(set(keywords))
    
    def get_learning_context(self, user_message: str) -> str:
        """Получает контекст обучения для промпта"""
        user_msg_lower = user_message.lower()
        keywords = self._extract_keywords(user_msg_lower)
        
        if not keywords:
            return ""
        
        context_parts = []
        
        # Ищем похожие паттерны
        for pattern_type, patterns in self.learned_patterns.items():
            matching_patterns = []
            
            for pattern in patterns[-20:]:  # Последние 20
                # Проверяем пересечение ключевых слов
                pattern_keywords = set(pattern['keywords'])
                message_keywords = set(keywords)
                intersection = pattern_keywords & message_keywords
                
                if len(intersection) >= 2:  # Минимум 2 общих слова
                    matching_patterns.append(pattern)
            
            if matching_patterns:
                if pattern_type.startswith('avoid_'):
                    # Паттерны которых нужно избегать
                    context_parts.append(
                        f"\n⚠️ ИЗБЕГАЙ подобных ответов (были ошибки):\n"
                    )
                    for p in matching_patterns[:3]:  # Максимум 3
                        if p.get('wrong_response'):
                            context_parts.append(f"- {p['wrong_response']}\n")
                        if p.get('correct_response'):
                            context_parts.append(f"+ Вместо: {p['correct_response']}\n")
                
                elif pattern_type.startswith('repeat_'):
                    # Паттерны которые нужно повторять
                    context_parts.append(
                        f"\n✅ ИСПОЛЬЗУЙ подобные ответы (были успешны):\n"
                    )
                    for p in matching_patterns[:3]:  # Максимум 3
                        if p.get('response'):
                            context_parts.append(f"- {p['response']}\n")
        
        return ''.join(context_parts)
    
    def get_learning_stats(self) -> Dict:
        """Получает статистику обучения"""
        return {
            'total_feedback': len(self.feedback_log),
            'total_mistakes': len(self.mistakes),
            'total_successes': len(self.successes),
            'learned_patterns': sum(len(p) for p in self.learned_patterns.values()),
            'pattern_types': list(self.learned_patterns.keys()),
            'recent_mistakes': self.mistakes[-5:] if self.mistakes else [],
            'recent_successes': self.successes[-5:] if self.successes else [],
        }
    
    def _load_data(self):
        """Загружает данные из файла"""
        data_file = 'data/ai_learning.json'
        if os.path.exists(data_file):
            try:
                with open(data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.feedback_log = data.get('feedback_log', [])
                    self.learned_patterns = data.get('learned_patterns', {})
                    self.mistakes = data.get('mistakes', [])
                    self.successes = data.get('successes', [])
            except:
                pass
    
    def _save_data(self):
        """Сохраняет данные в файл"""
        try:
            os.makedirs('data', exist_ok=True)
            data_file = 'data/ai_learning.json'
            with open(data_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'feedback_log': self.feedback_log[-200:],  # Сохраняем только последние 200
                    'learned_patterns': self.learned_patterns,
                    'mistakes': self.mistakes[-100:],  # Последние 100
                    'successes': self.successes[-100:],  # Последние 100
                }, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[SELF LEARNING] Ошибка сохранения: {e}")


# Глобальный экземпляр
_self_learning = None

def get_self_learning() -> SelfLearning:
    """Получает глобальный экземпляр SelfLearning"""
    global _self_learning
    if _self_learning is None:
        _self_learning = SelfLearning()
    return _self_learning
