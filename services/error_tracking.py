"""
Error Tracking
Система отслеживания ошибок
"""

from logger import get_logger

_log = get_logger("error_tracking")

import json
import os
import traceback
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from collections import defaultdict, Counter
import hashlib


class Error:
    """Ошибка"""
    
    def __init__(self, error_id: str, error_type: str, message: str,
                 stack_trace: str = None, endpoint: str = None,
                 user_id: str = None, severity: str = 'error'):
        self.error_id = error_id
        self.error_type = error_type
        self.message = message
        self.stack_trace = stack_trace
        self.endpoint = endpoint
        self.user_id = user_id
        self.severity = severity  # debug, info, warning, error, critical
        self.timestamp = datetime.now()
        self.occurrences = 1
        self.first_seen = datetime.now()
        self.last_seen = datetime.now()
        self.status = 'active'  # active, resolved, ignored
        self.tags = {}
        self.metadata = {}
        self.assigned_to = None
        self.resolution = None
    
    def add_occurrence(self):
        """Добавить новую запись"""
        self.occurrences += 1
        self.last_seen = datetime.now()
    
    def add_tag(self, key: str, value: str):
        """Добавить метку"""
        self.tags[key] = value
    
    def add_metadata(self, key: str, value: Any):
        """Добавить metadata"""
        self.metadata[key] = value
    
    def mark_resolved(self, resolution: str = None):
        """Отметить как решённую"""
        self.status = 'resolved'
        self.resolution = resolution
    
    def mark_ignored(self):
        """Отметить как проигнорированную"""
        self.status = 'ignored'
    
    def assign_to(self, user_id: str):
        """Ata"""
        self.assigned_to = user_id
    
    def get_fingerprint(self) -> str:
        """Создать отпечаток (для группировки похожих ошибок)"""
        fingerprint_data = f"{self.error_type}:{self.message}:{self.stack_trace}"
        return hashlib.md5(fingerprint_data.encode()).hexdigest()
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразовать в dict"""
        return {
            'error_id': self.error_id,
            'error_type': self.error_type,
            'message': self.message,
            'stack_trace': self.stack_trace,
            'endpoint': self.endpoint,
            'user_id': self.user_id,
            'severity': self.severity,
            'timestamp': self.timestamp.isoformat(),
            'occurrences': self.occurrences,
            'first_seen': self.first_seen.isoformat(),
            'last_seen': self.last_seen.isoformat(),
            'status': self.status,
            'tags': self.tags,
            'metadata': self.metadata,
            'assigned_to': self.assigned_to,
            'resolution': self.resolution,
            'fingerprint': self.get_fingerprint()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Error':
        """Создать из словаря"""
        error = cls(
            error_id=data['error_id'],
            error_type=data['error_type'],
            message=data['message'],
            stack_trace=data.get('stack_trace'),
            endpoint=data.get('endpoint'),
            user_id=data.get('user_id'),
            severity=data.get('severity', 'error')
        )
        error.timestamp = datetime.fromisoformat(data['timestamp'])
        error.occurrences = data.get('occurrences', 1)
        error.first_seen = datetime.fromisoformat(data['first_seen'])
        error.last_seen = datetime.fromisoformat(data['last_seen'])
        error.status = data.get('status', 'active')
        error.tags = data.get('tags', {})
        error.metadata = data.get('metadata', {})
        error.assigned_to = data.get('assigned_to')
        error.resolution = data.get('resolution')
        return error


class ErrorTracker:
    """Трекер ошибок"""
    
    def __init__(self):
        self.errors_file = 'data/tracked_errors.json'
        self.errors = self._load_errors()
    
    def _load_errors(self) -> Dict[str, Error]:
        """Загрузить ошибки"""
        if os.path.exists(self.errors_file):
            try:
                with open(self.errors_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return {
                        error_id: Error.from_dict(error_data)
                        for error_id, error_data in data.items()
                    }
            except Exception as _ex:
                _log.debug("_load_errors(): подавлено: %s", _ex)
        
        return {}
    
    def _save_errors(self):
        """Сохранить ошибки"""
        os.makedirs('data', exist_ok=True)
        
        data = {
            error_id: error.to_dict()
            for error_id, error in self.errors.items()
        }
        
        with open(self.errors_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def capture_exception(self, exception: Exception, endpoint: str = None,
                          user_id: str = None, severity: str = 'error',
                          tags: Dict[str, str] = None,
                          metadata: Dict[str, Any] = None) -> Error:
        """Exception yakala"""
        error_type = type(exception).__name__
        message = str(exception)
        stack_trace = traceback.format_exc()
        
        # Parmak izi создать
        fingerprint_data = f"{error_type}:{message}:{stack_trace}"
        fingerprint = hashlib.md5(fingerprint_data.encode()).hexdigest()
        
        # Текущий ошибка var ли проверить et
        existing_error = None
        for error in self.errors.values():
            if error.get_fingerprint() == fingerprint:
                existing_error = error
                break
        
        if existing_error:
            # Увеличиваем счётчик созданий текущей ошибки
            existing_error.add_occurrence()
            self._save_errors()
            return existing_error
        
        # Новый ошибка создать
        error_id = f"err_{len(self.errors) + 1}"
        
        error = Error(
            error_id=error_id,
            error_type=error_type,
            message=message,
            stack_trace=stack_trace,
            endpoint=endpoint,
            user_id=user_id,
            severity=severity
        )
        
        if tags:
            for key, value in tags.items():
                error.add_tag(key, value)
        
        if metadata:
            for key, value in metadata.items():
                error.add_metadata(key, value)
        
        self.errors[error_id] = error
        self._save_errors()
        
        return error
    
    def log_error(self, error_type: str, message: str,
                  stack_trace: str = None, endpoint: str = None,
                  user_id: str = None, severity: str = 'error',
                  tags: Dict[str, str] = None,
                  metadata: Dict[str, Any] = None) -> Error:
        """Записать ошибку в лог"""
        # Parmak izi создать
        fingerprint_data = f"{error_type}:{message}:{stack_trace}"
        fingerprint = hashlib.md5(fingerprint_data.encode()).hexdigest()
        
        # Текущий ошибка var ли проверить et
        existing_error = None
        for error in self.errors.values():
            if error.get_fingerprint() == fingerprint:
                existing_error = error
                break
        
        if existing_error:
            existing_error.add_occurrence()
            self._save_errors()
            return existing_error
        
        # Новый ошибка создать
        error_id = f"err_{len(self.errors) + 1}"
        
        error = Error(
            error_id=error_id,
            error_type=error_type,
            message=message,
            stack_trace=stack_trace,
            endpoint=endpoint,
            user_id=user_id,
            severity=severity
        )
        
        if tags:
            for key, value in tags.items():
                error.add_tag(key, value)
        
        if metadata:
            for key, value in metadata.items():
                error.add_metadata(key, value)
        
        self.errors[error_id] = error
        self._save_errors()
        
        return error
    
    def get_error(self, error_id: str) -> Optional[Error]:
        """Получить ошибку"""
        return self.errors.get(error_id)
    
    def get_all_errors(self, status: str = None, severity: str = None,
                       start_time: datetime = None, end_time: datetime = None) -> List[Error]:
        """Получить все ошибки"""
        errors = list(self.errors.values())
        
        if status:
            errors = [e for e in errors if e.status == status]
        
        if severity:
            errors = [e for e in errors if e.severity == severity]
        
        if start_time:
            errors = [e for e in errors if e.first_seen >= start_time]
        
        if end_time:
            errors = [e for e in errors if e.first_seen <= end_time]
        
        errors.sort(key=lambda e: e.last_seen, reverse=True)
        
        return errors
    
    def get_active_errors(self) -> List[Error]:
        """Получить активные ошибки"""
        return self.get_all_errors(status='active')
    
    def get_errors_by_endpoint(self, endpoint: str) -> List[Error]:
        """Получить ошибки по эндпоинту"""
        return [e for e in self.errors.values() if e.endpoint == endpoint]
    
    def get_errors_by_type(self, error_type: str) -> List[Error]:
        """Получить ошибки по типу"""
        return [e for e in self.errors.values() if e.error_type == error_type]
    
    def resolve_error(self, error_id: str, resolution: str = None) -> bool:
        """Решить ошибку"""
        error = self.errors.get(error_id)
        
        if error:
            error.mark_resolved(resolution)
            self._save_errors()
            return True
        
        return False
    
    def ignore_error(self, error_id: str) -> bool:
        """Игнорировать ошибку"""
        error = self.errors.get(error_id)
        
        if error:
            error.mark_ignored()
            self._save_errors()
            return True
        
        return False
    
    def assign_error(self, error_id: str, user_id: str) -> bool:
        """Назначить ошибку"""
        error = self.errors.get(error_id)
        
        if error:
            error.assign_to(user_id)
            self._save_errors()
            return True
        
        return False
    
    def delete_error(self, error_id: str) -> bool:
        """Удалить ошибку"""
        if error_id in self.errors:
            del self.errors[error_id]
            self._save_errors()
            return True
        
        return False


class ErrorGrouping:
    """Группировка ошибок"""
    
    def __init__(self, error_tracker: ErrorTracker):
        self.error_tracker = error_tracker
    
    def group_by_type(self, errors: List[Error] = None) -> Dict[str, List[Error]]:
        """Сгруппировать по типу"""
        if errors is None:
            errors = self.error_tracker.get_all_errors()
        
        groups = defaultdict(list)
        
        for error in errors:
            groups[error.error_type].append(error)
        
        return dict(groups)
    
    def group_by_endpoint(self, errors: List[Error] = None) -> Dict[str, List[Error]]:
        """Сгруппировать по эндпоинту"""
        if errors is None:
            errors = self.error_tracker.get_all_errors()
        
        groups = defaultdict(list)
        
        for error in errors:
            endpoint = error.endpoint or 'unknown'
            groups[endpoint].append(error)
        
        return dict(groups)
    
    def group_by_severity(self, errors: List[Error] = None) -> Dict[str, List[Error]]:
        """Сгруппировать по важности"""
        if errors is None:
            errors = self.error_tracker.get_all_errors()
        
        groups = defaultdict(list)
        
        for error in errors:
            groups[error.severity].append(error)
        
        return dict(groups)
    
    def get_top_errors(self, hours: int = 24, limit: int = 10) -> List[Error]:
        """Получить самые частые ошибки"""
        start_time = datetime.now() - timedelta(hours=hours)
        errors = self.error_tracker.get_all_errors(start_time=start_time)
        
        # Сортируем по количеству созданий
        errors.sort(key=lambda e: e.occurrences, reverse=True)
        
        return errors[:limit]
    
    def get_error_trends(self, hours: int = 24) -> Dict[str, int]:
        """Ошибка trendlerini al"""
        start_time = datetime.now() - timedelta(hours=hours)
        errors = self.error_tracker.get_all_errors(start_time=start_time)
        
        # Saate по grupla
        by_hour = defaultdict(int)
        
        for error in errors:
            hour = error.timestamp.strftime('%Y-%m-%d %H:00')
            by_hour[hour] += error.occurrences
        
        return dict(sorted(by_hour.items()))


class ErrorNotification:
    """Уведомление об ошибке"""
    
    def __init__(self, error_tracker: ErrorTracker):
        self.error_tracker = error_tracker
        self.notification_rules_file = 'data/error_notification_rules.json'
        self.notification_rules = self._load_notification_rules()
    
    def _load_notification_rules(self) -> Dict[str, Any]:
        """Загрузить правила уведомлений"""
        if os.path.exists(self.notification_rules_file):
            try:
                with open(self.notification_rules_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as _ex:
                _log.debug("_load_notification_rules(): подавлено: %s", _ex)
        
        return {}
    
    def _save_notification_rules(self):
        """Сохранить правила уведомлений"""
        os.makedirs('data', exist_ok=True)
        with open(self.notification_rules_file, 'w', encoding='utf-8') as f:
            json.dump(self.notification_rules, f, ensure_ascii=False, indent=2)
    
    def add_notification_rule(self, rule_id: str, severity: str,
                              channels: List[str], recipients: List[str]):
        """Добавить правило уведомления"""
        self.notification_rules[rule_id] = {
            'severity': severity,
            'channels': channels,
            'recipients': recipients,
            'enabled': True
        }
        
        self._save_notification_rules()
    
    def should_notify(self, error: Error) -> bool:
        """Проверить, нужно ли отправить уведомление"""
        for rule in self.notification_rules.values():
            if not rule.get('enabled', True):
                continue
            
            if rule['severity'] == error.severity:
                return True
        
        return False
    
    def get_notification_recipients(self, error: Error) -> List[str]:
        """Получить получателей уведомлений"""
        recipients = []
        
        for rule in self.notification_rules.values():
            if not rule.get('enabled', True):
                continue
            
            if rule['severity'] == error.severity:
                recipients.extend(rule['recipients'])
        
        return list(set(recipients))
    
    def enable_rule(self, rule_id: str) -> bool:
        """Включить правило"""
        if rule_id in self.notification_rules:
            self.notification_rules[rule_id]['enabled'] = True
            self._save_notification_rules()
            return True
        
        return False
    
    def disable_rule(self, rule_id: str) -> bool:
        """Отключить правило"""
        if rule_id in self.notification_rules:
            self.notification_rules[rule_id]['enabled'] = False
            self._save_notification_rules()
            return True
        
        return False


class ErrorAnalytics:
    """Аналитика ошибок"""
    
    def __init__(self, error_tracker: ErrorTracker):
        self.error_tracker = error_tracker
    
    def get_error_summary(self, hours: int = 24) -> Dict[str, Any]:
        """Получить сводку ошибок"""
        start_time = datetime.now() - timedelta(hours=hours)
        errors = self.error_tracker.get_all_errors(start_time=start_time)
        
        total_errors = len(errors)
        total_occurrences = sum(e.occurrences for e in errors)
        
        active_errors = sum(1 for e in errors if e.status == 'active')
        resolved_errors = sum(1 for e in errors if e.status == 'resolved')
        
        by_severity = Counter(e.severity for e in errors)
        by_type = Counter(e.error_type for e in errors)
        
        return {
            'period_hours': hours,
            'total_errors': total_errors,
            'total_occurrences': total_occurrences,
            'active_errors': active_errors,
            'resolved_errors': resolved_errors,
            'by_severity': dict(by_severity),
            'by_type': dict(by_type.most_common(10))
        }
    
    def get_error_rate(self, hours: int = 1) -> float:
        """Получить частоту ошибок (ошибок/мин)"""
        start_time = datetime.now() - timedelta(hours=hours)
        errors = self.error_tracker.get_all_errors(start_time=start_time)
        
        total_occurrences = sum(e.occurrences for e in errors)
        
        return total_occurrences / (hours * 60)  # ошибок/минута
    
    def get_mean_time_to_resolution(self, hours: int = 24) -> Optional[float]:
        """Получить среднее время решения (часы)"""
        start_time = datetime.now() - timedelta(hours=hours)
        errors = self.error_tracker.get_all_errors(start_time=start_time)
        
        resolved_errors = [e for e in errors if e.status == 'resolved']
        
        if not resolved_errors:
            return None
        
        resolution_times = []
        
        for error in resolved_errors:
            time_to_resolve = (error.last_seen - error.first_seen).total_seconds() / 3600
            resolution_times.append(time_to_resolve)
        
        return sum(resolution_times) / len(resolution_times)
    
    def get_impact_score(self, error: Error) -> float:
        """Оценка влияния ошибки."""
        # Скор на основе числа созданий, серьёзности и времени решения
        severity_weights = {
            'debug': 1,
            'info': 2,
            'warning': 3,
            'error': 5,
            'critical': 10
        }
        
        severity_weight = severity_weights.get(error.severity, 5)
        
        # Время решения (в часах)
        hours_unresolved = (datetime.now() - error.first_seen).total_seconds() / 3600
        
        impact_score = (error.occurrences * severity_weight) + (hours_unresolved * 0.1)
        
        return round(impact_score, 2)


# Global instances
error_tracker = ErrorTracker()
error_grouping = ErrorGrouping(error_tracker)
error_notification = ErrorNotification(error_tracker)
error_analytics = ErrorAnalytics(error_tracker)
