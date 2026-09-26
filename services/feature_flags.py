"""
Feature Flags
Система флагов функций
"""

from logger import get_logger

_log = get_logger("feature_flags")

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from collections import defaultdict


class FeatureFlag:
    """Флаг функции"""
    
    def __init__(self, flag_key: str, name: str, description: str = ''):
        self.flag_key = flag_key
        self.name = name
        self.description = description
        self.enabled = False
        self.rollout_percentage = 0  # 0-100
        self.targeting_rules = []
        self.variants = {}  # variant_key -> enabled
        self.metadata = {}
        self.created_at = datetime.now()
        self.created_by = None
        self.tags = {}
        self.environment = 'production'
    
    def enable(self):
        """Включить флаг"""
        self.enabled = True
    
    def disable(self):
        """Отключить флаг"""
        self.enabled = False
    
    def set_rollout_percentage(self, percentage: int):
        """Настроить процент"""
        self.rollout_percentage = max(0, min(100, percentage))
    
    def add_targeting_rule(self, rule_type: str, value: Any):
        """Добавить правило таргетинга"""
        self.targeting_rules.append({
            'type': rule_type,  # user_id, user_group, country, etc.
            'value': value
        })
    
    def add_variant(self, variant_key: str, enabled: bool = True):
        """Varyant добавить"""
        self.variants[variant_key] = enabled
    
    def add_tag(self, key: str, value: str):
        """Добавить метку"""
        self.tags[key] = value
    
    def add_metadata(self, key: str, value: Any):
        """Metadata добавить"""
        self.metadata[key] = value
    
    def is_enabled_for_user(self, user_id: str, user_context: Dict[str, Any] = None) -> bool:
        """Проверить, активен ли для пользователя"""
        if not self.enabled:
            return False
        
        # Проверяем правила таргетинга
        if self.targeting_rules:
            if not self._matches_targeting_rules(user_id, user_context):
                return False
        
        # Проверка процента
        if self.rollout_percentage < 100:
            if not self._is_in_rollout_percentage(user_id):
                return False
        
        return True
    
    def _matches_targeting_rules(self, user_id: str, user_context: Dict[str, Any] = None) -> bool:
        """Проверить соответствие правилам таргетинга"""
        if not user_context:
            user_context = {}
        
        for rule in self.targeting_rules:
            rule_type = rule['type']
            rule_value = rule['value']
            
            if rule_type == 'user_id':
                if user_id not in rule_value:
                    return False
            
            elif rule_type == 'user_group':
                user_groups = user_context.get('groups', [])
                if not any(group in rule_value for group in user_groups):
                    return False
            
            elif rule_type == 'country':
                user_country = user_context.get('country')
                if user_country not in rule_value:
                    return False
            
            elif rule_type == 'custom':
                # Особый kural
                custom_field = rule.get('field')
                custom_value = user_context.get(custom_field)
                
                if custom_value not in rule_value:
                    return False
        
        return True
    
    def _is_in_rollout_percentage(self, user_id: str) -> bool:
        """Проверить, входит ли в процент"""
        if self.rollout_percentage >= 100:
            return True
        
        if self.rollout_percentage <= 0:
            return False
        
        # Детерминированный хеш: один пользователь всегда получает один результат
        import hashlib
        hash_input = f"{self.flag_key}:{user_id}"
        hash_value = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)
        
        user_percentage = (hash_value % 100) + 1
        
        return user_percentage <= self.rollout_percentage
    
    def get_variant_for_user(self, user_id: str) -> Optional[str]:
        """Пользователь для вариантов al"""
        if not self.is_enabled_for_user(user_id):
            return None
        
        enabled_variants = [k for k, v in self.variants.items() if v]
        
        if not enabled_variants:
            return None
        
        # Детерминированный выбор
        import hashlib
        hash_input = f"{self.flag_key}:variant:{user_id}"
        hash_value = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)
        
        variant_index = hash_value % len(enabled_variants)
        
        return enabled_variants[variant_index]
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразовать в dict"""
        return {
            'flag_key': self.flag_key,
            'name': self.name,
            'description': self.description,
            'enabled': self.enabled,
            'rollout_percentage': self.rollout_percentage,
            'targeting_rules': self.targeting_rules,
            'variants': self.variants,
            'metadata': self.metadata,
            'created_at': self.created_at.isoformat(),
            'created_by': self.created_by,
            'tags': self.tags,
            'environment': self.environment
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FeatureFlag':
        """Создать из словаря"""
        flag = cls(
            flag_key=data['flag_key'],
            name=data['name'],
            description=data.get('description', '')
        )
        flag.enabled = data.get('enabled', False)
        flag.rollout_percentage = data.get('rollout_percentage', 0)
        flag.targeting_rules = data.get('targeting_rules', [])
        flag.variants = data.get('variants', {})
        flag.metadata = data.get('metadata', {})
        flag.created_at = datetime.fromisoformat(data['created_at'])
        flag.created_by = data.get('created_by')
        flag.tags = data.get('tags', {})
        flag.environment = data.get('environment', 'production')
        return flag


class FeatureFlagManager:
    """Менеджер флагов функций"""
    
    def __init__(self):
        self.flags_file = 'data/feature_flags.json'
        self.flags = self._load_flags()
    
    def _load_flags(self) -> Dict[str, FeatureFlag]:
        """Загрузить флаги"""
        if os.path.exists(self.flags_file):
            try:
                with open(self.flags_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return {
                        flag_key: FeatureFlag.from_dict(flag_data)
                        for flag_key, flag_data in data.items()
                    }
            except Exception as _ex:
                _log.debug("_load_flags(): подавлено: %s", _ex)
        
        return {}
    
    def _save_flags(self):
        """Сохранить флаги"""
        os.makedirs('data', exist_ok=True)
        
        data = {
            flag_key: flag.to_dict()
            for flag_key, flag in self.flags.items()
        }
        
        with open(self.flags_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def save_flag(self, flag: 'FeatureFlag') -> bool:
        """Сохранить изменения флага (после set_rollout_percentage и т.п.)."""
        if not flag or not getattr(flag, 'flag_key', None):
            return False
        self.flags[flag.flag_key] = flag
        self._save_flags()
        return True

    def create_flag(self, flag_key: str, name: str, description: str = '',
                    created_by: str = None) -> FeatureFlag:
        """Создать флаг"""
        flag = FeatureFlag(
            flag_key=flag_key,
            name=name,
            description=description
        )
        flag.created_by = created_by
        
        self.flags[flag_key] = flag
        self._save_flags()
        
        return flag
    
    def get_flag(self, flag_key: str) -> Optional[FeatureFlag]:
        """Получить флаг"""
        return self.flags.get(flag_key)
    
    def get_all_flags(self, environment: str = None) -> List[FeatureFlag]:
        """Получить все флаги"""
        flags = list(self.flags.values())
        
        if environment:
            flags = [f for f in flags if f.environment == environment]
        
        flags.sort(key=lambda f: f.created_at, reverse=True)
        
        return flags
    
    def get_enabled_flags(self) -> List[FeatureFlag]:
        """Получить активные флаги"""
        return [f for f in self.flags.values() if f.enabled]
    
    def enable_flag(self, flag_key: str) -> bool:
        """Включить флаг"""
        flag = self.flags.get(flag_key)
        
        if flag:
            flag.enable()
            self._save_flags()
            return True
        
        return False
    
    def disable_flag(self, flag_key: str) -> bool:
        """Отключить флаг"""
        flag = self.flags.get(flag_key)
        
        if flag:
            flag.disable()
            self._save_flags()
            return True
        
        return False
    
    def delete_flag(self, flag_key: str) -> bool:
        """Удалить флаг"""
        if flag_key in self.flags:
            del self.flags[flag_key]
            self._save_flags()
            return True
        
        return False
    
    def is_feature_enabled(self, flag_key: str, user_id: str = None,
                            user_context: Dict[str, Any] = None) -> bool:
        """Проверить, активна ли функция"""
        flag = self.flags.get(flag_key)
        
        if not flag:
            return False
        
        if user_id:
            return flag.is_enabled_for_user(user_id, user_context)
        
        return flag.enabled
    
    def get_variant(self, flag_key: str, user_id: str) -> Optional[str]:
        """Получить вариант"""
        flag = self.flags.get(flag_key)
        
        if not flag:
            return None
        
        return flag.get_variant_for_user(user_id)


class FeatureFlagRollout:
    """Управление rollout флагов функций"""
    
    def __init__(self, feature_flag_manager: FeatureFlagManager):
        self.feature_flag_manager = feature_flag_manager
        self.rollout_plans_file = 'data/feature_flag_rollout_plans.json'
        self.rollout_plans = self._load_rollout_plans()
    
    def _load_rollout_plans(self) -> Dict[str, Any]:
        """Загрузить планы rollout"""
        if os.path.exists(self.rollout_plans_file):
            try:
                with open(self.rollout_plans_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as _ex:
                _log.debug("_load_rollout_plans(): подавлено: %s", _ex)
        
        return {}
    
    def _save_rollout_plans(self):
        """Сохранить планы rollout"""
        os.makedirs('data', exist_ok=True)
        with open(self.rollout_plans_file, 'w', encoding='utf-8') as f:
            json.dump(self.rollout_plans, f, ensure_ascii=False, indent=2)
    
    def create_rollout_plan(self, flag_key: str, stages: List[Dict[str, Any]]):
        """Создать план rollout"""
        self.rollout_plans[flag_key] = {
            'stages': stages,
            'current_stage': 0,
            'created_at': datetime.now().isoformat()
        }
        
        self._save_rollout_plans()
    
    def advance_rollout(self, flag_key: str) -> bool:
        """Rollout'u ilerlet"""
        if flag_key not in self.rollout_plans:
            return False
        
        plan = self.rollout_plans[flag_key]
        current_stage = plan['current_stage']
        stages = plan['stages']
        
        if current_stage >= len(stages):
            return False
        
        stage = stages[current_stage]
        percentage = stage.get('percentage', 0)
        
        flag = self.feature_flag_manager.get_flag(flag_key)
        
        if flag:
            flag.set_rollout_percentage(percentage)
            self.feature_flag_manager._save_flags()
        
        plan['current_stage'] += 1
        self._save_rollout_plans()
        
        return True
    
    def get_rollout_status(self, flag_key: str) -> Optional[Dict[str, Any]]:
        """Получить состояние rollout'а"""
        if flag_key not in self.rollout_plans:
            return None
        
        plan = self.rollout_plans[flag_key]
        current_stage = plan['current_stage']
        stages = plan['stages']
        
        flag = self.feature_flag_manager.get_flag(flag_key)
        
        return {
            'flag_key': flag_key,
            'current_stage': current_stage,
            'total_stages': len(stages),
            'current_percentage': flag.rollout_percentage if flag else 0,
            'next_stage': stages[current_stage] if current_stage < len(stages) else None,
            'completed': current_stage >= len(stages)
        }


class FeatureFlagAnalytics:
    """Аналитика флагов функций"""
    
    def __init__(self, feature_flag_manager: FeatureFlagManager):
        self.feature_flag_manager = feature_flag_manager
        self.analytics_file = 'data/feature_flag_analytics.json'
        self.analytics = self._load_analytics()
    
    def _load_analytics(self) -> Dict[str, Any]:
        """Загрузить аналитику"""
        if os.path.exists(self.analytics_file):
            try:
                with open(self.analytics_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as _ex:
                _log.debug("_load_analytics(): подавлено: %s", _ex)
        
        return {}
    
    def _save_analytics(self):
        """Сохранить аналитику"""
        os.makedirs('data', exist_ok=True)
        with open(self.analytics_file, 'w', encoding='utf-8') as f:
            json.dump(self.analytics, f, ensure_ascii=False, indent=2)
    
    def track_flag_check(self, flag_key: str, user_id: str, result: bool):
        """Отслеживать проверку флага"""
        if flag_key not in self.analytics:
            self.analytics[flag_key] = {
                'checks': 0,
                'enabled_checks': 0,
                'unique_users': set(),
                'last_check': None
            }
        
        flag_analytics = self.analytics[flag_key]
        flag_analytics['checks'] += 1
        
        if result:
            flag_analytics['enabled_checks'] += 1
        
        flag_analytics['unique_users'].add(user_id)
        flag_analytics['last_check'] = datetime.now().isoformat()
        
        # Преобразуем set в list (для JSON-сериализации)
        flag_analytics['unique_users'] = list(flag_analytics['unique_users'])
        
        self._save_analytics()
    
    def get_flag_analytics(self, flag_key: str) -> Optional[Dict[str, Any]]:
        """Получить аналитику флага"""
        if flag_key not in self.analytics:
            return None
        
        flag_analytics = self.analytics[flag_key]
        
        return {
            'flag_key': flag_key,
            'total_checks': flag_analytics['checks'],
            'enabled_checks': flag_analytics['enabled_checks'],
            'unique_users': len(flag_analytics['unique_users']),
            'last_check': flag_analytics['last_check'],
            'enabled_percentage': (flag_analytics['enabled_checks'] / flag_analytics['checks'] * 100) if flag_analytics['checks'] > 0 else 0
        }
    
    def get_all_analytics(self) -> Dict[str, Dict[str, Any]]:
        """Получить всю аналитику"""
        result = {}
        
        for flag_key in self.analytics:
            result[flag_key] = self.get_flag_analytics(flag_key)
        
        return result


# Global instances
feature_flag_manager = FeatureFlagManager()
feature_flag_rollout = FeatureFlagRollout(feature_flag_manager)
feature_flag_analytics = FeatureFlagAnalytics(feature_flag_manager)
