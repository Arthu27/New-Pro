"""
Machine Learning Модels
ML модelleri ile tahmin ve analiz
"""

import json
import os
import re
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from collections import Counter, defaultdict
import math


class TicketPredictor:
    """Ticket tahmin модeli"""
    
    def __init__(self):
        self.модel_file = 'data/ml_модels/ticket_predictor.json'
        self.модel = self._loимя_модel()
    
    def _loимя_модel(self) -> Dict[str, Any]:
        """Модeli загрузить"""
        if os.path.exists(self.модel_file):
            try:
                with open(self.модel_file, 'r', encoding='utf-8') as f:
                    return json.loимя(f)
            except Exception:
                pass
        
        return {
            'trained_at': None,
            'category_weights': {},
            'priority_weights': {},
            'resolution_patterns': {}
        }
    
    def _save_модel(self):
        """Модeli сохранить"""
        os.maкотrs('data/ml_модels', exist_ok=True)
        with open(self.модel_file, 'w', encoding='utf-8') as f:
            json.dump(self.модel, f, ensure_ascii=False, indent=2)
    
    def train(self, tickets: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Модeli eгit"""
        if not tickets:
            return {'error': 'Eгitim verisi yok'}
        
        # Kategori весlarы
        category_patterns = defaultdict(lambda: defaultdict(int))
        for ticket in tickets:
            category = ticket.get('category', 'unknown')
            text = f"{ticket.get('subject', '')} {ticket.get('description', '')}".lower()
            
            # Kelimeleri удалить
            words = self._extract_keywords(text)
            for word in words:
                category_patterns[category][word] += 1
        
        # Normalize et
        category_weights = {}
        for category, patterns in category_patterns.items():
            total = sum(patterns.values())
            category_weights[category] = {
                word: count / total
                for word, count in patterns.items()
            }
        
        # Ёncelik весlarы
        priority_patterns = defaultdict(lambda: defaultdict(int))
        for ticket in tickets:
            priority = ticket.get('priority', 'medium')
            text = f"{ticket.get('subject', '')} {ticket.get('description', '')}".lower()
            
            words = self._extract_keywords(text)
            for word in words:
                priority_patterns[priority][word] += 1
        
        priority_weights = {}
        for priority, patterns in priority_patterns.items():
            total = sum(patterns.values())
            priority_weights[priority] = {
                word: count / total
                for word, count in patterns.items()
            }
        
        # Чёzюm длительностьleri
        resolution_times = []
        for ticket in tickets:
            if ticket.get('status') == 'closed':
                created_at = ticket.get('created_at')
                closed_at = ticket.get('closed_at')
                
                if created_at and closed_at:
                    created = datetime.fromisoformat(created_at)
                    closed = datetime.fromisoformat(closed_at)
                    hours = (closed - created).total_seconds() / 3600
                    resolution_times.append(hours)
        
        avg_resolution = sum(resolution_times) / len(resolution_times) if resolution_times else 0
        
        # Модeli сохранить
        self.модel = {
            'trained_at': datetime.now().isoformat(),
            'category_weights': category_weights,
            'priority_weights': priority_weights,
            'resolution_patterns': {
                'avg_resolution_time': avg_resolution,
                'total_samples': len(tickets)
            }
        }
        
        self._save_модel()
        
        return {
            'success': True,
            'trained_at': self.модel['trained_at'],
            'categories': len(category_weights),
            'priorities': len(priority_weights),
            'samples': len(tickets)
        }
    
    def predict_category(self, text: str) -> Tuple[str, float]:
        """Kategori tahmin et"""
        text_lower = text.lower()
        words = self._extract_keywords(text_lower)
        
        if not self.модel.get('category_weights'):
            return 'unknown', 0.0
        
        scores = {}
        for category, weights in self.модel['category_weights'].items():
            score = sum(weights.get(word, 0) for word in words)
            scores[category] = score
        
        if not scores:
            return 'unknown', 0.0
        
        best_category = max(scores, key=scores.get)
        confidence = scores[best_category]
        
        return best_category, confidence
    
    def predict_priority(self, text: str) -> Tuple[str, float]:
        """Ёncelik tahmin et"""
        text_lower = text.lower()
        words = self._extract_keywords(text_lower)
        
        if not self.модel.get('priority_weights'):
            return 'medium', 0.5
        
        scores = {}
        for priority, weights in self.модel['priority_weights'].items():
            score = sum(weights.get(word, 0) for word in words)
            scores[priority] = score
        
        if not scores:
            return 'medium', 0.5
        
        best_priority = max(scores, key=scores.get)
        confidence = scores[best_priority]
        
        return best_priority, confidence
    
    def predict_resolution_time(self, category: str, priority: str) -> float:
        """Чёzюm длительность tahmin et"""
        base_time = self.модel.get('resolution_patterns', {}).get('avg_resolution_time', 24)
        
        # Kategori чarpanы
        category_multipliers = {
            'Вопрос': 0.5,
            'Техническая проблема': 1.5,
            'Жалоба': 1.2,
            'Предложение': 0.8
        }
        
        # Ёncelik чarpanы
        priority_multipliers = {
            'high': 0.7,
            'medium': 1.0,
            'low': 1.3
        }
        
        cat_mult = category_multipliers.get(category, 1.0)
        pri_mult = priority_multipliers.get(priority, 1.0)
        
        predicted_time = base_time * cat_mult * pri_mult
        
        return round(predicted_time, 2)
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Anahtar словоleri удалить"""
        # Basit слово выйтиarыcы
        words = re.findall(r'\b\w+\b', text.lower())
        
        # Stop words filtrele
        stop_words = {'и', 'в', 'на', 'с', 'по', 'для', 'от', 'до', 'из', 'у', 'к', 'о', 'не', 'но', 'а', 'или', 'что', 'как', 'это', 'все', 'его', 'ее', 'их', 'мы', 'вы', 'они', 'the', 'and', 'or', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'from', 'is', 'was', 'are', 'were', 'been', 'be', 'have', 'has', 'hимя', 'do', 'does', 'did', 'will', 'would', 'could', 'should'}
        
        return [word for word in words if word not in stop_words and len(word) > 2]


class ChurnPredictor:
    """Mюшteri kaybы tahmin модeli"""
    
    def __init__(self):
        self.модel_file = 'data/ml_модels/churn_predictor.json'
        self.модel = self._loимя_модel()
    
    def _loимя_модel(self) -> Dict[str, Any]:
        """Модeli загрузить"""
        if os.path.exists(self.модel_file):
            try:
                with open(self.модel_file, 'r', encoding='utf-8') as f:
                    return json.loимя(f)
            except Exception:
                pass
        
        return {
            'trained_at': None,
            'risk_factors': {}
        }
    
    def _save_модel(self):
        """Модeli сохранить"""
        os.maкотrs('data/ml_модels', exist_ok=True)
        with open(self.модel_file, 'w', encoding='utf-8') as f:
            json.dump(self.модel, f, ensure_ascii=False, indent=2)
    
    def predict_churn_risk(self, user_id: str, tickets: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Kayыp riskini tahmin et"""
        if not tickets:
            return {
                'risk_score': 0.0,
                'risk_level': 'low',
                'factors': []
            }
        
        risk_score = 0.0
        factors = []
        
        # Faktёr 1: Negatif duygu соотношение
        negative_count = sum(1 for t in tickets if t.get('sentiment') == 'negative')
        negative_ratio = negative_count / len(tickets) if tickets else 0
        
        if negative_ratio > 0.5:
            risk_score += 0.3
            factors.append({
                'factor': 'high_negative_sentiment',
                'description': 'Yюksek negatif duygu соотношение',
                'value': negative_ratio,
                'impact': 0.3
            })
        
        # Faktёr 2: Чёzюlmemiш ticket'lar
        open_count = sum(1 for t in tickets if t.get('status') == 'open')
        open_ratio = open_count / len(tickets) if tickets else 0
        
        if open_ratio > 0.3:
            risk_score += 0.2
            factors.append({
                'factor': 'many_open_tickets',
                'description': 'Чok числоda открытый ticket',
                'value': open_ratio,
                'impact': 0.2
            })
        
        # Faktёr 3: Uzun чёzюm длительностьleri
        long_resolution_count = 0
        for ticket in tickets:
            if ticket.get('status') == 'closed':
                created_at = ticket.get('created_at')
                closed_at = ticket.get('closed_at')
                
                if created_at and closed_at:
                    created = datetime.fromisoformat(created_at)
                    closed = datetime.fromisoformat(closed_at)
                    hours = (closed - created).total_seconds() / 3600
                    
                    if hours > 48:  # 48 saatten uzun
                        long_resolution_count += 1
        
        long_resolution_ratio = long_resolution_count / len(tickets) if tickets else 0
        
        if long_resolution_ratio > 0.3:
            risk_score += 0.25
            factors.append({
                'factor': 'long_resolution_times',
                'description': 'Uzun чёzюm длительностьleri',
                'value': long_resolution_ratio,
                'impact': 0.25
            })
        
        # Faktёr 4: Dюшюk очки
        low_ratings = [t.get('rating', 5) for t in tickets if t.get('rating') and t.get('rating') < 3]
        low_rating_ratio = len(low_ratings) / len(tickets) if tickets else 0
        
        if low_rating_ratio > 0.3:
            risk_score += 0.25
            factors.append({
                'factor': 'low_ratings',
                'description': 'Dюшюk очки',
                'value': low_rating_ratio,
                'impact': 0.25
            })
        
        # Risk уровеньsi
        if risk_score >= 0.7:
            risk_level = 'high'
        elif risk_score >= 0.4:
            risk_level = 'medium'
        else:
            risk_level = 'low'
        
        return {
            'risk_score': round(risk_score, 2),
            'risk_level': risk_level,
            'factors': factors
        }


class AnomalyDetector:
    """Anomali tespit модeli"""
    
    def __init__(self):
        self.baseline_file = 'data/ml_модels/anomaly_baseline.json'
        self.baseline = self._loимя_baseline()
    
    def _loимя_baseline(self) -> Dict[str, Any]:
        """Baseline'ы загрузить"""
        if os.path.exists(self.baseline_file):
            try:
                with open(self.baseline_file, 'r', encoding='utf-8') as f:
                    return json.loимя(f)
            except Exception:
                pass
        
        return {
            'avg_tickets_per_day': 10,
            'avg_resolution_time': 24,
            'std_tickets_per_day': 5,
            'std_resolution_time': 12
        }
    
    def _save_baseline(self):
        """Baseline'ы сохранить"""
        os.maкотrs('data/ml_модels', exist_ok=True)
        with open(self.baseline_file, 'w', encoding='utf-8') as f:
            json.dump(self.baseline, f, ensure_ascii=False, indent=2)
    
    def update_baseline(self, tickets: List[Dict[str, Any]], days: int = 30):
        """Baseline'ы обновить"""
        if not tickets:
            return
        
        # Ежедневный ticket количество
        by_day = defaultdict(int)
        for ticket in tickets:
            created_at = ticket.get('created_at')
            if created_at:
                day = datetime.fromisoformat(created_at).strftime('%Y-%m-%d')
                by_day[day] += 1
        
        daily_counts = list(by_day.values())
        avg_tickets = sum(daily_counts) / len(daily_counts) if daily_counts else 10
        std_tickets = self._calculate_std(daily_counts) if len(daily_counts) > 1 else 5
        
        # Чёzюm длительностьleri
        resolution_times = []
        for ticket in tickets:
            if ticket.get('status') == 'closed':
                created_at = ticket.get('created_at')
                closed_at = ticket.get('closed_at')
                
                if created_at and closed_at:
                    created = datetime.fromisoformat(created_at)
                    closed = datetime.fromisoformat(closed_at)
                    hours = (closed - created).total_seconds() / 3600
                    resolution_times.append(hours)
        
        avg_resolution = sum(resolution_times) / len(resolution_times) if resolution_times else 24
        std_resolution = self._calculate_std(resolution_times) if len(resolution_times) > 1 else 12
        
        self.baseline = {
            'avg_tickets_per_day': avg_tickets,
            'avg_resolution_time': avg_resolution,
            'std_tickets_per_day': std_tickets,
            'std_resolution_time': std_resolution,
            'updated_at': datetime.now().isoformat()
        }
        
        self._save_baseline()
    
    def detect_anomalies(self, current_metrics: Dict[str, float]) -> List[Dict[str, Any]]:
        """Anomalileri tespit et"""
        anomalies = []
        
        # Ticket количество anomalisi
        tickets_today = current_metrics.get('tickets_today', 0)
        avg_tickets = self.baseline.get('avg_tickets_per_day', 10)
        std_tickets = self.baseline.get('std_tickets_per_day', 5)
        
        if std_tickets > 0:
            z_score = abs(tickets_today - avg_tickets) / std_tickets
            
            if z_score > 2:  # 2 standart sapma
                anomalies.append({
                    'type': 'ticket_volume',
                    'description': 'Anormal ticket количество',
                    'current': tickets_today,
                    'expected': avg_tickets,
                    'z_score': round(z_score, 2),
                    'severity': 'high' if z_score > 3 else 'medium'
                })
        
        # Чёzюm длительность anomalisi
        avg_resolution_today = current_metrics.get('avg_resolution_time', 0)
        baseline_resolution = self.baseline.get('avg_resolution_time', 24)
        std_resolution = self.baseline.get('std_resolution_time', 12)
        
        if std_resolution > 0 and avg_resolution_today > 0:
            z_score = abs(avg_resolution_today - baseline_resolution) / std_resolution
            
            if z_score > 2:
                anomalies.append({
                    'type': 'resolution_time',
                    'description': 'Anormal чёzюm длительность',
                    'current': avg_resolution_today,
                    'expected': baseline_resolution,
                    'z_score': round(z_score, 2),
                    'severity': 'high' if z_score > 3 else 'medium'
                })
        
        return anomalies
    
    def _calculate_std(self, values: List[float]) -> float:
        """Standart sapma hesapla"""
        if len(values) < 2:
            return 0
        
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return math.sqrt(variance)


# Global instances
ticket_predictor = TicketPredictor()
churn_predictor = ChurnPredictor()
anomaly_detector = AnomalyDetector()
