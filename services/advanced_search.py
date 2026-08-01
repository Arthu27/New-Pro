"""
Advanced Search
Расширенная система поиска (Elasticsearch entegrasyonu)
"""

import json
import os
import re
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from collections import defaultdict


class SearchEngine:
    """Arama motoru"""
    
    def __init__(self):
        self.index_file = 'data/search_index.json'
        self.index = self._load_index()
    
    def _load_index(self) -> Dict[str, Any]:
        """Index'i загрузить"""
        if os.path.exists(self.index_file):
            try:
                with open(self.index_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        
        return {
            'tickets': {},
            'articles': {},
            'users': {},
            'updated_at': None
        }
    
    def _save_index(self):
        """Index'i сохранить"""
        os.makedirs('data', exist_ok=True)
        with open(self.index_file, 'w', encoding='utf-8') as f:
            json.dump(self.index, f, ensure_ascii=False, indent=2)
    
    def index_ticket(self, ticket_id: str, ticket_data: Dict[str, Any]):
        """Ticket'ı index'le"""
        self.index['tickets'][ticket_id] = {
            'subject': ticket_data.get('subject', ''),
            'description': ticket_data.get('description', ''),
            'category': ticket_data.get('category', ''),
            'priority': ticket_data.get('priority', ''),
            'status': ticket_data.get('status', ''),
            'user_id': ticket_data.get('user_id', ''),
            'created_at': ticket_data.get('created_at', ''),
            'tags': ticket_data.get('tags', [])
        }
        
        self.index['updated_at'] = datetime.now().isoformat()
        self._save_index()
    
    def index_article(self, article_id: str, article_data: Dict[str, Any]):
        """Makaleyi index'le"""
        self.index['articles'][article_id] = {
            'title': article_data.get('title', ''),
            'content': article_data.get('content', ''),
            'category': article_data.get('category', ''),
            'tags': article_data.get('tags', []),
            'created_at': article_data.get('created_at', '')
        }
        
        self.index['updated_at'] = datetime.now().isoformat()
        self._save_index()
    
    def index_user(self, user_id: str, user_data: Dict[str, Any]):
        """Kullanıcıyı index'le"""
        self.index['users'][user_id] = {
            'username': user_data.get('username', ''),
            'email': user_data.get('email', ''),
            'role': user_data.get('role', ''),
            'created_at': user_data.get('created_at', '')
        }
        
        self.index['updated_at'] = datetime.now().isoformat()
        self._save_index()
    
    def remove_from_index(self, item_type: str, item_id: str):
        """Index'ten kaldır"""
        if item_type in self.index and item_id in self.index[item_type]:
            del self.index[item_type][item_id]
            self.index['updated_at'] = datetime.now().isoformat()
            self._save_index()
    
    def search(self, query: str, item_type: Optional[str] = None,
               filters: Optional[Dict[str, Any]] = None,
               limit: int = 50) -> List[Dict[str, Any]]:
        """Ara"""
        query_lower = query.lower()
        results = []
        
        # Arama yapılacak türler
        types_to_search = [item_type] if item_type else ['tickets', 'articles', 'users']
        
        for search_type in types_to_search:
            items = self.index.get(search_type, {})
            
            for item_id, item_data in items.items():
                # Filtreleri uygula
                if filters and not self._apply_filters(item_data, filters):
                    continue
                
                # Arama yap
                score = self._calculate_score(item_data, query_lower)
                
                if score > 0:
                    results.append({
                        'type': search_type,
                        'id': item_id,
                        'data': item_data,
                        'score': score
                    })
        
        # Score'a по sırala
        results.sort(key=lambda x: x['score'], reverse=True)
        
        return results[:limit]
    
    def _apply_filters(self, item_data: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        """Filtreleri uygula"""
        for key, value in filters.items():
            if key not in item_data:
                return False
            
            if isinstance(value, list):
                if item_data[key] not in value:
                    return False
            elif item_data[key] != value:
                return False
        
        return True
    
    def _calculate_score(self, item_data: Dict[str, Any], query: str) -> float:
        """Skor hesapla"""
        score = 0.0
        
        # Tüm text alanlarını проверить et
        for field, value in item_data.items():
            if isinstance(value, str):
                value_lower = value.lower()
                
                # Tam eşleşme
                if query == value_lower:
                    score += 10.0
                # İçeriyor
                elif query in value_lower:
                    score += 5.0
                # Kelime kelime eşleşme
                else:
                    query_words = query.split()
                    for word in query_words:
                        if word in value_lower:
                            score += 1.0
            
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        item_lower = item.lower()
                        if query in item_lower:
                            score += 3.0
        
        return score
    
    def suggest(self, query: str, limit: int = 10) -> List[str]:
        """Öneriler"""
        suggestions = set()
        query_lower = query.lower()
        
        # Tüm text alanlarından öneriler topla
        for search_type in ['tickets', 'articles', 'users']:
            items = self.index.get(search_type, {})
            
            for item_data in items.values():
                for field, value in item_data.items():
                    if isinstance(value, str):
                        value_lower = value.lower()
                        
                        # Query ile başlayan kelimeleri найти
                        words = value_lower.split()
                        for word in words:
                            if word.startswith(query_lower) and len(word) > len(query):
                                suggestions.add(word)
        
        return list(suggestions)[:limit]
    
    def rebuild_index(self, tickets: List[Dict[str, Any]],
                      articles: List[Dict[str, Any]],
                      users: List[Dict[str, Any]]):
        """Index'i yeniden создать"""
        self.index = {
            'tickets': {},
            'articles': {},
            'users': {},
            'updated_at': datetime.now().isoformat()
        }
        
        for ticket in tickets:
            ticket_id = ticket.get('id')
            if ticket_id:
                self.index_ticket(ticket_id, ticket)
        
        for article in articles:
            article_id = article.get('id')
            if article_id:
                self.index_article(article_id, article)
        
        for user in users:
            user_id = user.get('id')
            if user_id:
                self.index_user(user_id, user)
        
        self._save_index()


class FuzzySearch:
    """Fuzzy arama"""
    
    def __init__(self, search_engine: SearchEngine):
        self.search_engine = search_engine
    
    def search(self, query: str, threshold: float = 0.6,
               limit: int = 50) -> List[Dict[str, Any]]:
        """Fuzzy ara"""
        # Basit fuzzy implementasyonu
        results = []
        
        for search_type in ['tickets', 'articles', 'users']:
            items = self.search_engine.index.get(search_type, {})
            
            for item_id, item_data in items.items():
                max_similarity = 0.0
                
                for field, value in item_data.items():
                    if isinstance(value, str):
                        similarity = self._calculate_similarity(query, value)
                        max_similarity = max(max_similarity, similarity)
                
                if max_similarity >= threshold:
                    results.append({
                        'type': search_type,
                        'id': item_id,
                        'data': item_data,
                        'similarity': max_similarity
                    })
        
        results.sort(key=lambda x: x['similarity'], reverse=True)
        
        return results[:limit]
    
    def _calculate_similarity(self, s1: str, s2: str) -> float:
        """Benzerlik hesapla (Levenshtein distance basitleştirilmiş)"""
        s1_lower = s1.lower()
        s2_lower = s2.lower()
        
        if s1_lower == s2_lower:
            return 1.0
        
        if s1_lower in s2_lower or s2_lower in s1_lower:
            return 0.8
        
        # Basit benzerlik
        words1 = set(s1_lower.split())
        words2 = set(s2_lower.split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        
        return intersection / union if union > 0 else 0.0


class SavedSearch:
    """Kaydedilmiş aramalar"""
    
    def __init__(self):
        self.saved_searches_file = 'data/saved_searches.json'
        self.saved_searches = self._load_saved_searches()
    
    def _load_saved_searches(self) -> Dict[str, Any]:
        """Kaydedilmiş aramaları загрузить"""
        if os.path.exists(self.saved_searches_file):
            try:
                with open(self.saved_searches_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        
        return {}
    
    def _save_saved_searches(self):
        """Kaydedilmiş aramaları сохранить"""
        os.makedirs('data', exist_ok=True)
        with open(self.saved_searches_file, 'w', encoding='utf-8') as f:
            json.dump(self.saved_searches, f, ensure_ascii=False, indent=2)
    
    def save_search(self, user_id: str, name: str, query: str,
                    filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Aramayı сохранить"""
        if user_id not in self.saved_searches:
            self.saved_searches[user_id] = []
        
        search_id = f"search_{len(self.saved_searches[user_id]) + 1}"
        
        saved_search = {
            'search_id': search_id,
            'name': name,
            'query': query,
            'filters': filters or {},
            'created_at': datetime.now().isoformat()
        }
        
        self.saved_searches[user_id].append(saved_search)
        self._save_saved_searches()
        
        return saved_search
    
    def get_saved_searches(self, user_id: str) -> List[Dict[str, Any]]:
        """Kaydedilmiş aramaları al"""
        return self.saved_searches.get(user_id, [])
    
    def delete_saved_search(self, user_id: str, search_id: str) -> bool:
        """Kaydedilmiş aramayı удалить"""
        if user_id not in self.saved_searches:
            return False
        
        searches = self.saved_searches[user_id]
        for i, search in enumerate(searches):
            if search['search_id'] == search_id:
                del searches[i]
                self._save_saved_searches()
                return True
        
        return False


class SearchAnalytics:
    """Arama analitiği"""
    
    def __init__(self):
        self.analytics_file = 'data/search_analytics.json'
        self.analytics = self._load_analytics()
    
    def _load_analytics(self) -> Dict[str, Any]:
        """Analitiği загрузить"""
        if os.path.exists(self.analytics_file):
            try:
                with open(self.analytics_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        
        return {
            'queries': defaultdict(int),
            'no_results': defaultdict(int),
            'updated_at': None
        }
    
    def _save_analytics(self):
        """Analitiği сохранить"""
        os.makedirs('data', exist_ok=True)
        
        # defaultdict'ları normal dict'lere çevir
        analytics_dict = {
            'queries': dict(self.analytics['queries']),
            'no_results': dict(self.analytics['no_results']),
            'updated_at': datetime.now().isoformat()
        }
        
        with open(self.analytics_file, 'w', encoding='utf-8') as f:
            json.dump(analytics_dict, f, ensure_ascii=False, indent=2)
    
    def record_search(self, query: str, result_count: int):
        """Aramayı сохранить"""
        self.analytics['queries'][query] += 1
        
        if result_count == 0:
            self.analytics['no_results'][query] += 1
        
        self._save_analytics()
    
    def get_popular_queries(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Popüler sorguları al"""
        queries = [
            {'query': query, 'count': count}
            for query, count in self.analytics['queries'].items()
        ]
        
        queries.sort(key=lambda x: x['count'], reverse=True)
        
        return queries[:limit]
    
    def get_no_results_queries(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Sonuçsuz sorguları al"""
        queries = [
            {'query': query, 'count': count}
            for query, count in self.analytics['no_results'].items()
        ]
        
        queries.sort(key=lambda x: x['count'], reverse=True)
        
        return queries[:limit]


# Global instances
search_engine = SearchEngine()
fuzzy_search = FuzzySearch(search_engine)
saved_search = SavedSearch()
search_analytics = SearchAnalytics()
