"""
Performance Monitoring
Система мониторинга производительности
"""

import json
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import statistics
from collections import defaultdict


class PerformanceMetric:
    """Производительность metrik"""
    
    def __init__(self, metric_name: str, value: float, timestamp: datetime = None):
        self.metric_name = metric_name
        self.value = value
        self.timestamp = timestamp or datetime.now()
        self.tags = {}
        self.unit = None
    
    def add_tag(self, key: str, value: str):
        """Добавить метку"""
        self.tags[key] = value
    
    def set_unit(self, unit: str):
        """Настроить единицу"""
        self.unit = unit
    
    def to_dict(self) -> Dict[str, Any]:
        """Dict'e чevir"""
        return {
            'metric_name': self.metric_name,
            'value': self.value,
            'timestamp': self.timestamp.isoformat(),
            'tags': self.tags,
            'unit': self.unit
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PerformanceMetric':
        """Создать из словаря"""
        metric = cls(
            metric_name=data['metric_name'],
            value=data['value'],
            timestamp=datetime.fromisoformat(data['timestamp'])
        )
        metric.tags = data.get('tags', {})
        metric.unit = data.get('unit')
        return metric


class MetricsCollector:
    """Metrik toplayыcы"""
    
    def __init__(self):
        self.metrics_file = 'data/performance_metrics.json'
        self.metrics = self._load_metrics()
    
    def _load_metrics(self) -> Dict[str, List[PerformanceMetric]]:
        """Metrikleri загрузить"""
        if os.path.exists(self.metrics_file):
            try:
                with open(self.metrics_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return {
                        metric_name: [PerformanceMetric.from_dict(m) for m in metrics]
                        for metric_name, metrics in data.items()
                    }
            except Exception:
                pass
        
        return defaultdict(list)
    
    def _save_metrics(self):
        """Metrikleri сохранить"""
        os.makedirs('data', exist_ok=True)
        
        data = {
            metric_name: [m.to_dict() for m in metrics]
            for metric_name, metrics in self.metrics.items()
        }
        
        with open(self.metrics_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def record_metric(self, metric_name: str, value: float,
                      tags: Dict[str, str] = None, unit: str = None):
        """Metrik сохранить"""
        metric = PerformanceMetric(metric_name, value)
        
        if tags:
            for key, val in tags.items():
                metric.add_tag(key, val)
        
        if unit:
            metric.set_unit(unit)
        
        self.metrics[metric_name].append(metric)
        
        # Eski metrikleri очистить (son 7 день)
        cutoff = datetime.now() - timedelta(days=7)
        self.metrics[metric_name] = [
            m for m in self.metrics[metric_name]
            if m.timestamp > cutoff
        ]
        
        self._save_metrics()
    
    def get_metrics(self, metric_name: str, start_time: Optional[datetime] = None,
                    end_time: Optional[datetime] = None) -> List[PerformanceMetric]:
        """Metrikleri al"""
        metrics = self.metrics.get(metric_name, [])
        
        if start_time:
            metrics = [m for m in metrics if m.timestamp >= start_time]
        
        if end_time:
            metrics = [m for m in metrics if m.timestamp <= end_time]
        
        return metrics
    
    def get_latest_metric(self, metric_name: str) -> Optional[PerformanceMetric]:
        """Son metriгi al"""
        metrics = self.metrics.get(metric_name, [])
        
        if not metrics:
            return None
        
        return metrics[-1]
    
    def get_average(self, metric_name: str, hours: int = 1) -> Optional[float]:
        """Ortalama deгeri al"""
        start_time = datetime.now() - timedelta(hours=hours)
        metrics = self.get_metrics(metric_name, start_time=start_time)
        
        if not metrics:
            return None
        
        values = [m.value for m in metrics]
        return statistics.mean(values)
    
    def get_percentile(self, metric_name: str, percentile: float,
                       hours: int = 1) -> Optional[float]:
        """Yюzdelik deгeri al"""
        start_time = datetime.now() - timedelta(hours=hours)
        metrics = self.get_metrics(metric_name, start_time=start_time)
        
        if not metrics:
            return None
        
        values = sorted([m.value for m in metrics])
        index = int(len(values) * percentile / 100)
        
        return values[index]
    
    def get_all_metric_names(self) -> List[str]:
        """Все metrik adlerini al"""
        return list(self.metrics.keys())


class ResponseTimeTracker:
    """Yanыt длительность takipчisi"""
    
    def __init__(self, metrics_collector: MetricsCollector):
        self.metrics_collector = metrics_collector
    
    def track_response_time(self, endpoint: str, response_time_ms: float,
                            status_code: int = 200, method: str = 'GET'):
        """Yanыt длительностьni takip et"""
        tags = {
            'endpoint': endpoint,
            'status_code': str(status_code),
            'method': method
        }
        
        self.metrics_collector.record_metric(
            'response_time',
            response_time_ms,
            tags=tags,
            unit='ms'
        )
    
    def get_endpoint_stats(self, endpoint: str, hours: int = 1) -> Dict[str, Any]:
        """Endpoint статистикаini al"""
        start_time = datetime.now() - timedelta(hours=hours)
        metrics = self.metrics_collector.get_metrics('response_time', start_time=start_time)
        
        # Endpoint'e по filtrele
        endpoint_metrics = [
            m for m in metrics
            if m.tags.get('endpoint') == endpoint
        ]
        
        if not endpoint_metrics:
            return {
                'endpoint': endpoint,
                'count': 0,
                'avg_response_time': None,
                'p50': None,
                'p95': None,
                'p99': None
            }
        
        values = [m.value for m in endpoint_metrics]
        
        return {
            'endpoint': endpoint,
            'count': len(values),
            'avg_response_time': round(statistics.mean(values), 2),
            'p50': round(statistics.median(values), 2),
            'p95': round(self._percentile(values, 95), 2),
            'p99': round(self._percentile(values, 99), 2)
        }
    
    def _percentile(self, values: List[float], percentile: float) -> float:
        """Yюzdelik hesapla"""
        sorted_values = sorted(values)
        index = int(len(sorted_values) * percentile / 100)
        return sorted_values[index]
    
    def get_slow_endpoints(self, threshold_ms: float = 1000,
                           hours: int = 1) -> List[Dict[str, Any]]:
        """Медленный endpoint'leri al"""
        start_time = datetime.now() - timedelta(hours=hours)
        metrics = self.metrics_collector.get_metrics('response_time', start_time=start_time)
        
        # Endpoint'lere по grupla
        by_endpoint = defaultdict(list)
        for metric in metrics:
            endpoint = metric.tags.get('endpoint', 'unknown')
            by_endpoint[endpoint].append(metric.value)
        
        slow_endpoints = []
        for endpoint, values in by_endpoint.items():
            avg_time = statistics.mean(values)
            
            if avg_time >= threshold_ms:
                slow_endpoints.append({
                    'endpoint': endpoint,
                    'avg_response_time': round(avg_time, 2),
                    'count': len(values)
                })
        
        slow_endpoints.sort(key=lambda x: x['avg_response_time'], reverse=True)
        
        return slow_endpoints


class ErrorRateTracker:
    """Ошибка соотношение takipчisi"""
    
    def __init__(self, metrics_collector: MetricsCollector):
        self.metrics_collector = metrics_collector
    
    def track_error(self, error_type: str, error_message: str,
                    endpoint: str = None, severity: str = 'error'):
        """Hatayы takip et"""
        tags = {
            'error_type': error_type,
            'severity': severity
        }
        
        if endpoint:
            tags['endpoint'] = endpoint
        
        self.metrics_collector.record_metric(
            'error',
            1,
            tags=tags
        )
        
        # Ошибка сообщениеыnы da сохранить
        self.metrics_collector.record_metric(
            'error_message',
            1,
            tags={'message': error_message[:200]}
        )
    
    def get_error_rate(self, hours: int = 1) -> Dict[str, Any]:
        """Ошибка соотношениеnы al"""
        start_time = datetime.now() - timedelta(hours=hours)
        error_metrics = self.metrics_collector.get_metrics('error', start_time=start_time)
        response_metrics = self.metrics_collector.get_metrics('response_time', start_time=start_time)
        
        total_errors = len(error_metrics)
        total_requests = len(response_metrics)
        
        error_rate = (total_errors / total_requests * 100) if total_requests > 0 else 0
        
        # Ошибка tiplerine по grupla
        by_type = defaultdict(int)
        for metric in error_metrics:
            error_type = metric.tags.get('error_type', 'unknown')
            by_type[error_type] += 1
        
        return {
            'total_errors': total_errors,
            'total_requests': total_requests,
            'error_rate': round(error_rate, 2),
            'by_type': dict(by_type)
        }
    
    def get_top_errors(self, hours: int = 1, limit: int = 10) -> List[Dict[str, Any]]:
        """En sыk hatalarы al"""
        start_time = datetime.now() - timedelta(hours=hours)
        error_metrics = self.metrics_collector.get_metrics('error_message', start_time=start_time)
        
        # Сообщенияa по grupla
        by_message = defaultdict(int)
        for metric in error_metrics:
            message = metric.tags.get('message', 'Unknown error')
            by_message[message] += 1
        
        top_errors = [
            {'message': message, 'count': count}
            for message, count in by_message.items()
        ]
        
        top_errors.sort(key=lambda x: x['count'], reverse=True)
        
        return top_errors[:limit]


class UptimeMonitor:
    """Uptime izleyici"""
    
    def __init__(self, metrics_collector: MetricsCollector):
        self.metrics_collector = metrics_collector
        self.uptime_file = 'data/uptime_records.json'
        self.uptime_records = self._load_uptime_records()
    
    def _load_uptime_records(self) -> Dict[str, Any]:
        """Uptime kayыtlarыnы загрузить"""
        if os.path.exists(self.uptime_file):
            try:
                with open(self.uptime_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        
        return {
            'checks': [],
            'last_check': None,
            'uptime_percentage': 100.0
        }
    
    def _save_uptime_records(self):
        """Uptime kayыtlarыnы сохранить"""
        os.makedirs('data', exist_ok=True)
        with open(self.uptime_file, 'w', encoding='utf-8') as f:
            json.dump(self.uptime_records, f, ensure_ascii=False, indent=2)
    
    def record_check(self, endpoint: str, is_up: bool, response_time_ms: float = None,
                     status_code: int = None, error_message: str = None):
        """Kontrol сохранить"""
        check = {
            'endpoint': endpoint,
            'is_up': is_up,
            'timestamp': datetime.now().isoformat(),
            'response_time_ms': response_time_ms,
            'status_code': status_code,
            'error_message': error_message
        }
        
        self.uptime_records['checks'].append(check)
        self.uptime_records['last_check'] = datetime.now().isoformat()
        
        # Uptime yюzdesini hesapla
        self._calculate_uptime_percentage()
        
        # Eski kayыtlarы очистить (son 30 день)
        cutoff = datetime.now() - timedelta(days=30)
        self.uptime_records['checks'] = [
            c for c in self.uptime_records['checks']
            if datetime.fromisoformat(c['timestamp']) > cutoff
        ]
        
        self._save_uptime_records()
    
    def _calculate_uptime_percentage(self):
        """Uptime yюzdesini hesapla"""
        checks = self.uptime_records['checks']
        
        if not checks:
            self.uptime_records['uptime_percentage'] = 100.0
            return
        
        up_count = sum(1 for c in checks if c['is_up'])
        total_count = len(checks)
        
        self.uptime_records['uptime_percentage'] = (up_count / total_count * 100)
    
    def get_uptime_percentage(self, hours: int = 24) -> float:
        """Uptime yюzdesini al"""
        start_time = datetime.now() - timedelta(hours=hours)
        
        checks = [
            c for c in self.uptime_records['checks']
            if datetime.fromisoformat(c['timestamp']) > start_time
        ]
        
        if not checks:
            return 100.0
        
        up_count = sum(1 for c in checks if c['is_up'])
        return (up_count / len(checks) * 100)
    
    def get_downtime_periods(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Downtime dёnemlerini al"""
        start_time = datetime.now() - timedelta(hours=hours)
        
        checks = [
            c for c in self.uptime_records['checks']
            if datetime.fromisoformat(c['timestamp']) > start_time
        ]
        
        downtime_periods = []
        current_period = None
        
        for check in checks:
            if not check['is_up']:
                if current_period is None:
                    current_period = {
                        'start': check['timestamp'],
                        'end': check['timestamp'],
                        'endpoint': check['endpoint']
                    }
                else:
                    current_period['end'] = check['timestamp']
            else:
                if current_period is not None:
                    downtime_periods.append(current_period)
                    current_period = None
        
        if current_period is not None:
            downtime_periods.append(current_period)
        
        return downtime_periods


class DatabasePerformanceMonitor:
    """Veritabanы performans izleyici"""
    
    def __init__(self, metrics_collector: MetricsCollector):
        self.metrics_collector = metrics_collector
    
    def track_query_time(self, query_type: str, query_time_ms: float,
                         table: str = None, rows_affected: int = None):
        """Sorgu длительностьni takip et"""
        tags = {
            'query_type': query_type
        }
        
        if table:
            tags['table'] = table
        
        if rows_affected is not None:
            tags['rows_affected'] = str(rows_affected)
        
        self.metrics_collector.record_metric(
            'db_query_time',
            query_time_ms,
            tags=tags,
            unit='ms'
        )
    
    def get_query_stats(self, hours: int = 1) -> Dict[str, Any]:
        """Sorgu статистикаini al"""
        start_time = datetime.now() - timedelta(hours=hours)
        metrics = self.metrics_collector.get_metrics('db_query_time', start_time=start_time)
        
        if not metrics:
            return {
                'total_queries': 0,
                'avg_query_time': None,
                'slow_queries': 0
            }
        
        values = [m.value for m in metrics]
        slow_queries = sum(1 for v in values if v > 1000)  # 1 saniyeden медленный
        
        return {
            'total_queries': len(values),
            'avg_query_time': round(statistics.mean(values), 2),
            'slow_queries': slow_queries,
            'slow_query_rate': round(slow_queries / len(values) * 100, 2)
        }
    
    def get_slow_queries(self, threshold_ms: float = 1000,
                         hours: int = 1) -> List[Dict[str, Any]]:
        """Медленный sorgularы al"""
        start_time = datetime.now() - timedelta(hours=hours)
        metrics = self.metrics_collector.get_metrics('db_query_time', start_time=start_time)
        
        slow_queries = [
            {
                'query_type': m.tags.get('query_type', 'unknown'),
                'table': m.tags.get('table'),
                'query_time_ms': m.value,
                'timestamp': m.timestamp.isoformat()
            }
            for m in metrics
            if m.value > threshold_ms
        ]
        
        slow_queries.sort(key=lambda x: x['query_time_ms'], reverse=True)
        
        return slow_queries[:20]


class PerformanceAlert:
    """Производительность предупреждениеsы"""
    
    def __init__(self, metrics_collector: MetricsCollector):
        self.metrics_collector = metrics_collector
        self.alerts_file = 'data/performance_alerts.json'
        self.alerts = self._load_alerts()
        self.alert_rules = {}
    
    def _load_alerts(self) -> Dict[str, Any]:
        """Предупреждениеlarы загрузить"""
        if os.path.exists(self.alerts_file):
            try:
                with open(self.alerts_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        
        return {'alerts': [], 'rules': {}}
    
    def _save_alerts(self):
        """Предупреждениеlarы сохранить"""
        os.makedirs('data', exist_ok=True)
        with open(self.alerts_file, 'w', encoding='utf-8') as f:
            json.dump(self.alerts, f, ensure_ascii=False, indent=2)
    
    def add_alert_rule(self, metric_name: str, threshold: float,
                       operator: str = 'greater_than',
                       severity: str = 'warning'):
        """Предупреждение kuralы добавить"""
        if metric_name not in self.alerts['rules']:
            self.alerts['rules'][metric_name] = []
        
        self.alerts['rules'][metric_name].append({
            'threshold': threshold,
            'operator': operator,
            'severity': severity,
            'enabled': True
        })
        
        self._save_alerts()
    
    def check_alerts(self) -> List[Dict[str, Any]]:
        """Предупреждениеlarы проверить et"""
        triggered_alerts = []
        
        for metric_name, rules in self.alerts['rules'].items():
            latest_metric = self.metrics_collector.get_latest_metric(metric_name)
            
            if not latest_metric:
                continue
            
            for rule in rules:
                if not rule.get('enabled', True):
                    continue
                
                threshold = rule['threshold']
                operator = rule['operator']
                value = latest_metric.value
                
                triggered = False
                
                if operator == 'greater_than' and value > threshold:
                    triggered = True
                elif operator == 'less_than' and value < threshold:
                    triggered = True
                elif operator == 'equals' and value == threshold:
                    triggered = True
                
                if triggered:
                    alert = {
                        'metric_name': metric_name,
                        'value': value,
                        'threshold': threshold,
                        'operator': operator,
                        'severity': rule['severity'],
                        'timestamp': datetime.now().isoformat(),
                        'tags': latest_metric.tags
                    }
                    
                    triggered_alerts.append(alert)
                    self.alerts['alerts'].append(alert)
        
        if triggered_alerts:
            self._save_alerts()
        
        return triggered_alerts
    
    def get_recent_alerts(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Son предупреждениеlarы al"""
        start_time = datetime.now() - timedelta(hours=hours)
        
        return [
            a for a in self.alerts['alerts']
            if datetime.fromisoformat(a['timestamp']) > start_time
        ]
    
    def dismiss_alert(self, alert_index: int) -> bool:
        """Предупреждениеyы закрыть"""
        if alert_index < len(self.alerts['alerts']):
            self.alerts['alerts'][alert_index]['dismissed'] = True
            self._save_alerts()
            return True
        
        return False


# Global instances
metrics_collector = MetricsCollector()
response_time_tracker = ResponseTimeTracker(metrics_collector)
error_rate_tracker = ErrorRateTracker(metrics_collector)
uptime_monitor = UptimeMonitor(metrics_collector)
database_performance_monitor = DatabasePerformanceMonitor(metrics_collector)
performance_alert = PerformanceAlert(metrics_collector)
