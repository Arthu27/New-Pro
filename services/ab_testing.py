"""
A/B Testing
Система A/B тестирования
"""

import json
import os
import random
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from collections import defaultdict
import hashlib


class ABTestVariant:
    """A/B test varyantı"""
    
    def __init__(self, variant_id: str, name: str, description: str = ''):
        self.variant_id = variant_id
        self.name = name
        self.description = description
        self.config = {}
        self.weight = 1.0  # Trafik ağırlığı
        self.enabled = True
    
    def set_config(self, config: Dict[str, Any]):
        """Настроить конфигурацию"""
        self.config = config
    
    def set_weight(self, weight: float):
        """Настроить вес"""
        self.weight = max(0.0, weight)
    
    def to_dict(self) -> Dict[str, Any]:
        """Dict'e çevir"""
        return {
            'variant_id': self.variant_id,
            'name': self.name,
            'description': self.description,
            'config': self.config,
            'weight': self.weight,
            'enabled': self.enabled
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ABTestVariant':
        """Создать из словаря"""
        variant = cls(
            variant_id=data['variant_id'],
            name=data['name'],
            description=data.get('description', '')
        )
        variant.config = data.get('config', {})
        variant.weight = data.get('weight', 1.0)
        variant.enabled = data.get('enabled', True)
        return variant


class ABTest:
    """A/B test"""
    
    def __init__(self, test_id: str, name: str, description: str = ''):
        self.test_id = test_id
        self.name = name
        self.description = description
        self.variants = {}  # variant_id -> ABTestVariant
        self.status = 'draft'  # draft, running, paused, completed
        self.start_time = None
        self.end_time = None
        self.target_sample_size = None
        self.metrics = []  # Ölçülecek metrikler
        self.created_at = datetime.now()
        self.created_by = None
        self.tags = {}
    
    def add_variant(self, variant: ABTestVariant):
        """Varyant добавить"""
        self.variants[variant.variant_id] = variant
    
    def remove_variant(self, variant_id: str) -> bool:
        """Varyant kaldır"""
        if variant_id in self.variants:
            del self.variants[variant_id]
            return True
        return False
    
    def get_variant(self, variant_id: str) -> Optional[ABTestVariant]:
        """Varyantı al"""
        return self.variants.get(variant_id)
    
    def get_all_variants(self) -> List[ABTestVariant]:
        """Tüm varyantları al"""
        return list(self.variants.values())
    
    def get_enabled_variants(self) -> List[ABTestVariant]:
        """Etkin varyantları al"""
        return [v for v in self.variants.values() if v.enabled]
    
    def start(self):
        """Testi запустить"""
        self.status = 'running'
        self.start_time = datetime.now()
    
    def pause(self):
        """Testi duraklat"""
        self.status = 'paused'
    
    def complete(self):
        """Testi tamamla"""
        self.status = 'completed'
        self.end_time = datetime.now()
    
    def add_metric(self, metric_name: str, metric_type: str = 'conversion'):
        """Metrik добавить"""
        self.metrics.append({
            'name': metric_name,
            'type': metric_type  # conversion, continuous, ratio
        })
    
    def add_tag(self, key: str, value: str):
        """Добавить метку"""
        self.tags[key] = value
    
    def select_variant_for_user(self, user_id: str) -> Optional[ABTestVariant]:
        """Пользователь для varyant seç"""
        if self.status != 'running':
            return None
        
        enabled_variants = self.get_enabled_variants()
        
        if not enabled_variants:
            return None
        
        # Deterministik seçim (aynı пользователь her zaman aynı varyantı alır)
        hash_input = f"{self.test_id}:{user_id}"
        hash_value = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)
        
        # Ağırlıklı seçim
        total_weight = sum(v.weight for v in enabled_variants)
        
        if total_weight == 0:
            return None
        
        random_value = (hash_value % 10000) / 10000.0 * total_weight
        
        cumulative_weight = 0
        for variant in enabled_variants:
            cumulative_weight += variant.weight
            
            if random_value <= cumulative_weight:
                return variant
        
        return enabled_variants[0]
    
    def to_dict(self) -> Dict[str, Any]:
        """Dict'e çevir"""
        return {
            'test_id': self.test_id,
            'name': self.name,
            'description': self.description,
            'variants': {
                variant_id: variant.to_dict()
                for variant_id, variant in self.variants.items()
            },
            'status': self.status,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'target_sample_size': self.target_sample_size,
            'metrics': self.metrics,
            'created_at': self.created_at.isoformat(),
            'created_by': self.created_by,
            'tags': self.tags
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ABTest':
        """Создать из словаря"""
        test = cls(
            test_id=data['test_id'],
            name=data['name'],
            description=data.get('description', '')
        )
        test.variants = {
            variant_id: ABTestVariant.from_dict(variant_data)
            for variant_id, variant_data in data.get('variants', {}).items()
        }
        test.status = data.get('status', 'draft')
        test.start_time = datetime.fromisoformat(data['start_time']) if data.get('start_time') else None
        test.end_time = datetime.fromisoformat(data['end_time']) if data.get('end_time') else None
        test.target_sample_size = data.get('target_sample_size')
        test.metrics = data.get('metrics', [])
        test.created_at = datetime.fromisoformat(data['created_at'])
        test.created_by = data.get('created_by')
        test.tags = data.get('tags', {})
        return test


class ABTestManager:
    """A/B test yöneticisi"""
    
    def __init__(self):
        self.tests_file = 'data/ab_tests.json'
        self.tests = self._load_tests()
    
    def _load_tests(self) -> Dict[str, ABTest]:
        """Testleri загрузить"""
        if os.path.exists(self.tests_file):
            try:
                with open(self.tests_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return {
                        test_id: ABTest.from_dict(test_data)
                        for test_id, test_data in data.items()
                    }
            except Exception:
                pass
        
        return {}
    
    def _save_tests(self):
        """Testleri сохранить"""
        os.makedirs('data', exist_ok=True)
        
        data = {
            test_id: test.to_dict()
            for test_id, test in self.tests.items()
        }
        
        with open(self.tests_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def create_test(self, name: str, description: str = '',
                    created_by: str = None) -> ABTest:
        """Test создать"""
        test_id = f"test_{len(self.tests) + 1}"
        
        test = ABTest(
            test_id=test_id,
            name=name,
            description=description
        )
        test.created_by = created_by
        
        self.tests[test_id] = test
        self._save_tests()
        
        return test
    
    def get_test(self, test_id: str) -> Optional[ABTest]:
        """Testi al"""
        return self.tests.get(test_id)
    
    def get_all_tests(self, status: str = None) -> List[ABTest]:
        """Tüm testleri al"""
        tests = list(self.tests.values())
        
        if status:
            tests = [t for t in tests if t.status == status]
        
        tests.sort(key=lambda t: t.created_at, reverse=True)
        
        return tests
    
    def get_running_tests(self) -> List[ABTest]:
        """Çalışan testleri al"""
        return self.get_all_tests(status='running')
    
    def start_test(self, test_id: str) -> bool:
        """Testi запустить"""
        test = self.tests.get(test_id)
        
        if test and test.status == 'draft':
            test.start()
            self._save_tests()
            return True
        
        return False
    
    def pause_test(self, test_id: str) -> bool:
        """Testi duraklat"""
        test = self.tests.get(test_id)
        
        if test and test.status == 'running':
            test.pause()
            self._save_tests()
            return True
        
        return False
    
    def complete_test(self, test_id: str) -> bool:
        """Testi tamamla"""
        test = self.tests.get(test_id)
        
        if test and test.status == 'running':
            test.complete()
            self._save_tests()
            return True
        
        return False
    
    def delete_test(self, test_id: str) -> bool:
        """Testi удалить"""
        if test_id in self.tests:
            del self.tests[test_id]
            self._save_tests()
            return True
        
        return False
    
    def get_user_variant(self, test_id: str, user_id: str) -> Optional[ABTestVariant]:
        """Пользователь varyantını al"""
        test = self.tests.get(test_id)
        
        if not test:
            return None
        
        return test.select_variant_for_user(user_id)


class ABTestTracking:
    """A/B test takibi"""
    
    def __init__(self, ab_test_manager: ABTestManager):
        self.ab_test_manager = ab_test_manager
        self.events_file = 'data/ab_test_events.json'
        self.events = self._load_events()
    
    def _load_events(self) -> Dict[str, Any]:
        """Olayları загрузить"""
        if os.path.exists(self.events_file):
            try:
                with open(self.events_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        
        return {}
    
    def _save_events(self):
        """Olayları сохранить"""
        os.makedirs('data', exist_ok=True)
        with open(self.events_file, 'w', encoding='utf-8') as f:
            json.dump(self.events, f, ensure_ascii=False, indent=2)
    
    def track_impression(self, test_id: str, variant_id: str, user_id: str):
        """Gösterim takip et"""
        if test_id not in self.events:
            self.events[test_id] = {'impressions': [], 'conversions': []}
        
        self.events[test_id]['impressions'].append({
            'variant_id': variant_id,
            'user_id': user_id,
            'timestamp': datetime.now().isoformat()
        })
        
        self._save_events()
    
    def track_conversion(self, test_id: str, variant_id: str, user_id: str,
                         metric_name: str, value: float = 1.0):
        """Dönüşüm takip et"""
        if test_id not in self.events:
            self.events[test_id] = {'impressions': [], 'conversions': []}
        
        self.events[test_id]['conversions'].append({
            'variant_id': variant_id,
            'user_id': user_id,
            'metric_name': metric_name,
            'value': value,
            'timestamp': datetime.now().isoformat()
        })
        
        self._save_events()
    
    def get_test_events(self, test_id: str) -> Dict[str, Any]:
        """Test olaylarını al"""
        return self.events.get(test_id, {'impressions': [], 'conversions': []})
    
    def get_variant_impressions(self, test_id: str, variant_id: str) -> int:
        """Varyant gösterim sayısını al"""
        events = self.events.get(test_id, {})
        impressions = events.get('impressions', [])
        
        return sum(1 for imp in impressions if imp['variant_id'] == variant_id)
    
    def get_variant_conversions(self, test_id: str, variant_id: str,
                                 metric_name: str = None) -> int:
        """Varyant dönüşüm sayısını al"""
        events = self.events.get(test_id, {})
        conversions = events.get('conversions', [])
        
        if metric_name:
            return sum(1 for conv in conversions
                      if conv['variant_id'] == variant_id and conv['metric_name'] == metric_name)
        
        return sum(1 for conv in conversions if conv['variant_id'] == variant_id)


class ABTestAnalytics:
    """A/B test analitiği"""
    
    def __init__(self, ab_test_manager: ABTestManager, tracking: ABTestTracking):
        self.ab_test_manager = ab_test_manager
        self.tracking = tracking
    
    def calculate_conversion_rate(self, test_id: str, variant_id: str,
                                   metric_name: str = None) -> float:
        """Dönüşüm oranını hesapla"""
        impressions = self.tracking.get_variant_impressions(test_id, variant_id)
        conversions = self.tracking.get_variant_conversions(test_id, variant_id, metric_name)
        
        if impressions == 0:
            return 0.0
        
        return (conversions / impressions) * 100
    
    def get_variant_stats(self, test_id: str) -> Dict[str, Dict[str, Any]]:
        """Varyant istatistiklerini al"""
        test = self.ab_test_manager.get_test(test_id)
        
        if not test:
            return {}
        
        stats = {}
        
        for variant_id, variant in test.variants.items():
            impressions = self.tracking.get_variant_impressions(test_id, variant_id)
            
            variant_stats = {
                'variant_id': variant_id,
                'variant_name': variant.name,
                'impressions': impressions,
                'metrics': {}
            }
            
            # Her metrik для dönüşüm oranı
            for metric in test.metrics:
                metric_name = metric['name']
                conversions = self.tracking.get_variant_conversions(test_id, variant_id, metric_name)
                conversion_rate = self.calculate_conversion_rate(test_id, variant_id, metric_name)
                
                variant_stats['metrics'][metric_name] = {
                    'conversions': conversions,
                    'conversion_rate': round(conversion_rate, 2)
                }
            
            stats[variant_id] = variant_stats
        
        return stats
    
    def get_winner(self, test_id: str, metric_name: str) -> Optional[str]:
        """Kazananı al"""
        test = self.ab_test_manager.get_test(test_id)
        
        if not test:
            return None
        
        best_variant_id = None
        best_conversion_rate = -1
        
        for variant_id in test.variants.keys():
            conversion_rate = self.calculate_conversion_rate(test_id, variant_id, metric_name)
            
            if conversion_rate > best_conversion_rate:
                best_conversion_rate = conversion_rate
                best_variant_id = variant_id
        
        return best_variant_id
    
    def calculate_statistical_significance(self, test_id: str, variant_a_id: str,
                                            variant_b_id: str, metric_name: str) -> Dict[str, Any]:
        """İstatistiksel anlamlılığı hesapla (basit z-test)"""
        impressions_a = self.tracking.get_variant_impressions(test_id, variant_a_id)
        conversions_a = self.tracking.get_variant_conversions(test_id, variant_a_id, metric_name)
        
        impressions_b = self.tracking.get_variant_impressions(test_id, variant_b_id)
        conversions_b = self.tracking.get_variant_conversions(test_id, variant_b_id, metric_name)
        
        if impressions_a == 0 or impressions_b == 0:
            return {'significant': False, 'p_value': 1.0, 'confidence': 0.0}
        
        rate_a = conversions_a / impressions_a
        rate_b = conversions_b / impressions_b
        
        # Basit z-test (gerçek uygulamada более sofistike test kullanılmalı)
        pooled_rate = (conversions_a + conversions_b) / (impressions_a + impressions_b)
        
        se = (pooled_rate * (1 - pooled_rate) * (1/impressions_a + 1/impressions_b)) ** 0.5
        
        if se == 0:
            return {'significant': False, 'p_value': 1.0, 'confidence': 0.0}
        
        z_score = (rate_a - rate_b) / se
        
        # Basit p-value hesaplama (gerçek uygulamada scipy.stats kullanılmalı)
        p_value = 2 * (1 - abs(z_score) / 3)  # Yaklaşık
        
        p_value = max(0, min(1, p_value))
        
        significant = p_value < 0.05
        confidence = (1 - p_value) * 100
        
        return {
            'significant': significant,
            'p_value': round(p_value, 4),
            'confidence': round(confidence, 2),
            'rate_a': round(rate_a * 100, 2),
            'rate_b': round(rate_b * 100, 2),
            'difference': round(abs(rate_a - rate_b) * 100, 2)
        }
    
    def generate_report(self, test_id: str) -> Dict[str, Any]:
        """Rapor создать"""
        test = self.ab_test_manager.get_test(test_id)
        
        if not test:
            return {}
        
        variant_stats = self.get_variant_stats(test_id)
        
        # Her metrik для kazanan
        winners = {}
        for metric in test.metrics:
            metric_name = metric['name']
            winner_id = self.get_winner(test_id, metric_name)
            winners[metric_name] = winner_id
        
        return {
            'test_id': test_id,
            'test_name': test.name,
            'status': test.status,
            'start_time': test.start_time.isoformat() if test.start_time else None,
            'end_time': test.end_time.isoformat() if test.end_time else None,
            'variant_stats': variant_stats,
            'winners': winners
        }


# Global instances
ab_test_manager = ABTestManager()
ab_test_tracking = ABTestTracking(ab_test_manager)
ab_test_analytics = ABTestAnalytics(ab_test_manager, ab_test_tracking)
