"""
RAG (Retrieval Augmented Generation) — поиск по базе знаний сервера
AI может искать в правилах, FAQ, логах тикетов, документации
"""
import os
import json
import re
from typing import List, Dict, Optional
from datetime import datetime


class KnowledgeBase:
    """База знаний сервера с поиском"""
    
    def __init__(self, guild_id: int):
        self.guild_id = guild_id
        self.documents = []
        self._load_documents()
    
    def _load_documents(self):
        """Загружает все документы в память"""
        # 1. Правила сервера
        rules_file = f"data/rules_{self.guild_id}.json"
        if os.path.exists(rules_file):
            try:
                with open(rules_file, 'r', encoding='utf-8') as f:
                    rules_data = json.load(f)
                    for rule in rules_data.get('rules', []):
                        self.documents.append({
                            'type': 'rule',
                            'content': rule.get('text', ''),
                            'metadata': {'id': rule.get('id', 0)}
                        })
            except:
                pass
        
        # 2. FAQ (выученные вопросы)
        faq_file = 'data/faq_learned.json'
        if os.path.exists(faq_file):
            try:
                with open(faq_file, 'r', encoding='utf-8') as f:
                    faq_data = json.load(f)
                    for faq in faq_data.get(str(self.guild_id), []):
                        self.documents.append({
                            'type': 'faq',
                            'content': f"В: {faq.get('question', '')}\nО: {faq.get('answer', '')}",
                            'metadata': {'timestamp': faq.get('timestamp', '')}
                        })
            except:
                pass
        
        # 3. Логи тикетов (последние 50)
        tickets_file = f"data/tickets_{self.guild_id}.json"
        if os.path.exists(tickets_file):
            try:
                with open(tickets_file, 'r', encoding='utf-8') as f:
                    tickets_data = json.load(f)
                    for ticket in tickets_data.get('tickets', [])[-50:]:
                        # Извлекаем ключевые моменты из тикета
                        summary = f"Тикет: {ticket.get('category', '?')} — {ticket.get('status', '?')}"
                        if ticket.get('summary'):
                            summary += f"\n{ticket.get('summary', '')}"
                        
                        self.documents.append({
                            'type': 'ticket',
                            'content': summary,
                            'metadata': {
                                'user_id': ticket.get('user_id', 0),
                                'created_at': ticket.get('created_at', '')
                            }
                        })
            except:
                pass
        
        # 4. Пользовательские заметки (из data/notes.json если есть)
        notes_file = 'data/notes.json'
        if os.path.exists(notes_file):
            try:
                with open(notes_file, 'r', encoding='utf-8') as f:
                    notes_data = json.load(f)
                    guild_notes = notes_data.get(str(self.guild_id), {})
                    for user_id, notes in guild_notes.items():
                        for note in notes:
                            self.documents.append({
                                'type': 'note',
                                'content': note.get('text', ''),
                                'metadata': {
                                    'user_id': int(user_id),
                                    'author': note.get('author', '?'),
                                    'timestamp': note.get('timestamp', '')
                                }
                            })
            except:
                pass
    
    def search(self, query: str, max_results: int = 5) -> List[Dict]:
        """Поиск по базе знаний (простой keyword-based)"""
        query_lower = query.lower()
        query_words = set(re.findall(r'\w+', query_lower))
        
        scored_docs = []
        for doc in self.documents:
            content_lower = doc['content'].lower()
            
            # Подсчёт совпадений
            matches = sum(1 for word in query_words if word in content_lower)
            
            if matches > 0:
                # Нормализованный скор
                score = matches / len(query_words) if query_words else 0
                scored_docs.append((score, doc))
        
        # Сортируем по скору
        scored_docs.sort(reverse=True, key=lambda x: x[0])
        
        # Возвращаем топ результаты
        return [doc for score, doc in scored_docs[:max_results]]
    
    def get_context_for_query(self, query: str) -> str:
        """Получает контекст из базы знаний для ответа на вопрос"""
        results = self.search(query, max_results=3)
        
        if not results:
            return ""
        
        context_parts = ["РЕЛЕВАНТНАЯ ИНФОРМАЦИЯ ИЗ БАЗЫ ЗНАНИЙ:"]
        
        for i, doc in enumerate(results, 1):
            doc_type = doc['type']
            content = doc['content'][:500]  # Ограничиваем длину
            
            if doc_type == 'rule':
                context_parts.append(f"\n{i}. ПРАВИЛО СЕРВЕРА:\n{content}")
            elif doc_type == 'faq':
                context_parts.append(f"\n{i}. ПОХОЖИЙ ВОПРОС-ОТВЕТ:\n{content}")
            elif doc_type == 'ticket':
                context_parts.append(f"\n{i}. ПОХОЖИЙ ТИКЕТ:\n{content}")
            elif doc_type == 'note':
                context_parts.append(f"\n{i}. ЗАМЕТКА:\n{content}")
        
        return "\n".join(context_parts)


class ConversationAnalyzer:
    """Анализатор разговоров — извлекает важные факты"""
    
    @staticmethod
    def extract_facts(messages: List[Dict]) -> List[str]:
        """Извлекает важные факты из разговора"""
        facts = []
        
        # Паттерны для извлечения фактов
        patterns = [
            (r'меня зовут (\w+)', 'Имя пользователя: {}'),
            (r'мне (\d+) (?:лет|год)', 'Возраст: {} лет'),
            (r'я из ([\w\s]+?)(?:\.|,|$)', 'Город: {}'),
            (r'мой (?:discord|дс|ник):? ([\w#]+)', 'Discord: {}'),
            (r'(?:люблю|нравится|интересуюсь) ([\w\s]+?)(?:\.|,|$)', 'Интересы: {}'),
            (r'работаю ([\w\s]+?)(?:\.|,|$)', 'Работа: {}'),
            (r'учусь ([\w\s]+?)(?:\.|,|$)', 'Учёба: {}'),
        ]
        
        for msg in messages:
            content = msg.get('content', '')
            if msg.get('role') != 'user':
                continue
            
            for pattern, template in patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    fact = template.format(match.group(1).strip())
                    if fact not in facts:
                        facts.append(fact)
        
        return facts
    
    @staticmethod
    def detect_sentiment(messages: List[Dict]) -> str:
        """Определяет настроение разговора"""
        positive_words = ['спасибо', 'отлично', 'круто', 'супер', 'класс', 'помог', 'решил']
        negative_words = ['бесит', 'злюсь', 'ненавижу', 'тупой', 'идиот', 'не работает', 'ошибка']
        
        all_text = ' '.join([msg.get('content', '') for msg in messages[-10:]]).lower()
        
        positive_count = sum(1 for word in positive_words if word in all_text)
        negative_count = sum(1 for word in negative_words if word in all_text)
        
        if positive_count > negative_count:
            return 'positive'
        elif negative_count > positive_count:
            return 'negative'
        else:
            return 'neutral'


# Глобальный кэш баз знаний (чтобы не загружать каждый раз)
_kb_cache: Dict[int, KnowledgeBase] = {}


def get_knowledge_base(guild_id: int) -> KnowledgeBase:
    """Получает базу знаний для сервера (с кэшированием)"""
    if guild_id not in _kb_cache:
        _kb_cache[guild_id] = KnowledgeBase(guild_id)
    return _kb_cache[guild_id]


def refresh_knowledge_base(guild_id: int):
    """Обновляет кэш базы знаний"""
    if guild_id in _kb_cache:
        del _kb_cache[guild_id]
