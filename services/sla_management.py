"""
SLA Management
Управление Service Level Agreement
"""

from logger import get_logger

_log = get_logger("sla_management")

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional


class SLAPolicy:
    """Политика SLA"""
    
    def __init__(self, policy_id: str, name: str, description: str = ''):
        self.policy_id = policy_id
        self.name = name
        self.description = description
        self.response_times = {}  # priority -> minutes
        self.resolution_times = {}  # priority -> minutes
        self.business_hours = None
        self.conditions = []
    
    def set_response_time(self, priority: str, minutes: int):
        """Настроить время ответа"""
        self.response_times[priority] = minutes
    
    def set_resolution_time(self, priority: str, minutes: int):
        """Настроить время решения"""
        self.resolution_times[priority] = minutes
    
    def set_business_hours(self, start_hour: int, end_hour: int,
                           days: List[int] = None):
        """Настроить рабочие часы"""
        self.business_hours = {
            'start_hour': start_hour,
            'end_hour': end_hour,
            'days': days or [0, 1, 2, 3, 4]  # Понедельник-Пятница
        }
    
    def add_condition(self, field: str, operator: str, value: Any):
        """Добавить условие"""
        self.conditions.append({
            'field': field,
            'operator': operator,
            'value': value
        })
    
    def matches_ticket(self, ticket: Dict[str, Any]) -> bool:
        """Проверить, подходит ли тикету"""
        if not self.conditions:
            return True
        
        for condition in self.conditions:
            field = condition['field']
            operator = condition['operator']
            value = condition['value']
            
            ticket_value = ticket.get(field)
            
            if operator == 'equals' and ticket_value != value:
                return False
            elif operator == 'not_equals' and ticket_value == value:
                return False
            elif operator == 'in' and ticket_value not in value:
                return False
            elif operator == 'contains' and value not in str(ticket_value):
                return False
        
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразовать в dict"""
        return {
            'policy_id': self.policy_id,
            'name': self.name,
            'description': self.description,
            'response_times': self.response_times,
            'resolution_times': self.resolution_times,
            'business_hours': self.business_hours,
            'conditions': self.conditions
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SLAPolicy':
        """Создать из словаря"""
        policy = cls(
            policy_id=data['policy_id'],
            name=data['name'],
            description=data.get('description', '')
        )
        policy.response_times = data.get('response_times', {})
        policy.resolution_times = data.get('resolution_times', {})
        policy.business_hours = data.get('business_hours')
        policy.conditions = data.get('conditions', [])
        return policy


class SLAManager:
    """Менеджер SLA"""
    
    def __init__(self):
        self.policies_file = 'data/sla_policies.json'
        self.policies = self._load_policies()
    
    def _load_policies(self) -> Dict[str, SLAPolicy]:
        """Загрузить политики"""
        if os.path.exists(self.policies_file):
            try:
                with open(self.policies_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return {
                        policy_id: SLAPolicy.from_dict(policy_data)
                        for policy_id, policy_data in data.items()
                    }
            except Exception as _ex:
                _log.debug("_load_policies(): подавлено: %s", _ex)
        
        return {}
    
    def _save_policies(self):
        """Сохранить политики"""
        os.makedirs('data', exist_ok=True)
        
        data = {
            policy_id: policy.to_dict()
            for policy_id, policy in self.policies.items()
        }
        
        with open(self.policies_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def create_policy(self, name: str, description: str = '') -> SLAPolicy:
        """Politika создать"""
        policy_id = f"sla_{len(self.policies) + 1}"
        
        policy = SLAPolicy(
            policy_id=policy_id,
            name=name,
            description=description
        )
        
        self.policies[policy_id] = policy
        self._save_policies()
        
        return policy
    
    def update_policy(self, policy_id: str, **kwargs) -> Optional[SLAPolicy]:
        """Обновить политику"""
        if policy_id not in self.policies:
            return None
        
        policy = self.policies[policy_id]
        
        for key, value in kwargs.items():
            if hasattr(policy, key):
                setattr(policy, key, value)
        
        self._save_policies()
        
        return policy
    
    def delete_policy(self, policy_id: str) -> bool:
        """Удалить политику"""
        if policy_id in self.policies:
            del self.policies[policy_id]
            self._save_policies()
            return True
        
        return False
    
    def get_policy(self, policy_id: str) -> Optional[SLAPolicy]:
        """Получить политику"""
        return self.policies.get(policy_id)
    
    def get_all_policies(self) -> List[SLAPolicy]:
        """Получить все политики"""
        return list(self.policies.values())
    
    def get_applicable_policy(self, ticket: Dict[str, Any]) -> Optional[SLAPolicy]:
        """Получить применимую политику"""
        for policy in self.policies.values():
            if policy.matches_ticket(ticket):
                return policy
        
        return None


class SLACalculator:
    """Калькулятор SLA"""
    
    def __init__(self, sla_manager: SLAManager):
        self.sla_manager = sla_manager
    
    def calculate_response_deadline(self, ticket: Dict[str, Any],
                                    policy: Optional[SLAPolicy] = None) -> Optional[datetime]:
        """Вычислить срок ответа"""
        if not policy:
            policy = self.sla_manager.get_applicable_policy(ticket)
        
        if not policy:
            return None
        
        priority = ticket.get('priority', 'medium')
        response_minutes = policy.response_times.get(priority)
        
        if not response_minutes:
            return None
        
        created_at = ticket.get('created_at')
        if not created_at:
            return None
        
        created_dt = datetime.fromisoformat(created_at)
        
        # Работа saatlerini hesaba kat
        if policy.business_hours:
            deadline = self._add_business_hours(created_dt, response_minutes, policy.business_hours)
        else:
            deadline = created_dt + timedelta(minutes=response_minutes)
        
        return deadline
    
    def calculate_resolution_deadline(self, ticket: Dict[str, Any],
                                      policy: Optional[SLAPolicy] = None) -> Optional[datetime]:
        """Вычислить срок решения"""
        if not policy:
            policy = self.sla_manager.get_applicable_policy(ticket)
        
        if not policy:
            return None
        
        priority = ticket.get('priority', 'medium')
        resolution_minutes = policy.resolution_times.get(priority)
        
        if not resolution_minutes:
            return None
        
        created_at = ticket.get('created_at')
        if not created_at:
            return None
        
        created_dt = datetime.fromisoformat(created_at)
        
        # Работа saatlerini hesaba kat
        if policy.business_hours:
            deadline = self._add_business_hours(created_dt, resolution_minutes, policy.business_hours)
        else:
            deadline = created_dt + timedelta(minutes=resolution_minutes)
        
        return deadline
    
    def _add_business_hours(self, start: datetime, minutes: int,
                            business_hours: Dict[str, Any]) -> datetime:
        """Работа saatleri ekleyerek zaman hesapla"""
        current = start
        remaining_minutes = minutes
        
        start_hour = business_hours['start_hour']
        end_hour = business_hours['end_hour']
        work_days = business_hours['days']
        
        while remaining_minutes > 0:
            # Работа день mю?
            if current.weekday() not in work_days:
                current += timedelta(days=1)
                current = current.replace(hour=start_hour, minute=0, second=0, microsecond=0)
                continue
            
            # Работа saati в mi?
            if current.hour < start_hour:
                current = current.replace(hour=start_hour, minute=0, second=0, microsecond=0)
            elif current.hour >= end_hour:
                current += timedelta(days=1)
                current = current.replace(hour=start_hour, minute=0, second=0, microsecond=0)
                continue
            
            # Buдень kalan работа dakikalarы
            end_of_day = current.replace(hour=end_hour, minute=0, second=0, microsecond=0)
            available_minutes = int((end_of_day - current).total_seconds() / 60)
            
            if remaining_minutes <= available_minutes:
                current += timedelta(minutes=remaining_minutes)
                remaining_minutes = 0
            else:
                remaining_minutes -= available_minutes
                current += timedelta(days=1)
                current = current.replace(hour=start_hour, minute=0, second=0, microsecond=0)
        
        return current
    
    def get_time_remaining(self, deadline: datetime) -> timedelta:
        """Получить оставшееся время"""
        now = datetime.now()
        return deadline - now
    
    def is_breached(self, deadline: datetime) -> bool:
        """Проверить, нарушено ли"""
        return datetime.now() > deadline


class SLABreachDetector:
    """SLA ihlal tespit edici"""
    
    def __init__(self, sla_calculator: SLACalculator):
        self.sla_calculator = sla_calculator
        self.breaches_file = 'data/sla_breaches.json'
        self.breaches = self._load_breaches()
    
    def _load_breaches(self) -> Dict[str, Any]:
        """Загрузить нарушения"""
        if os.path.exists(self.breaches_file):
            try:
                with open(self.breaches_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as _ex:
                _log.debug("_load_breaches(): подавлено: %s", _ex)
        
        return {}
    
    def _save_breaches(self):
        """Сохранить нарушения"""
        os.makedirs('data', exist_ok=True)
        with open(self.breaches_file, 'w', encoding='utf-8') as f:
            json.dump(self.breaches, f, ensure_ascii=False, indent=2)
    
    def check_ticket(self, ticket: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Ticket'ы проверить et"""
        breaches = []
        ticket_id = ticket.get('id')
        
        if not ticket_id:
            return breaches
        
        policy = self.sla_calculator.sla_manager.get_applicable_policy(ticket)
        
        if not policy:
            return breaches
        
        # Yanыt длительность проверка
        first_response_at = ticket.get('first_response_at')
        if not first_response_at:
            response_deadline = self.sla_calculator.calculate_response_deadline(ticket, policy)
            
            if response_deadline and self.sla_calculator.is_breached(response_deadline):
                breaches.append({
                    'ticket_id': ticket_id,
                    'type': 'response_time',
                    'deadline': response_deadline.isoformat(),
                    'breached_at': datetime.now().isoformat(),
                    'policy_id': policy.policy_id
                })
        
        # Чёzюm длительность проверка
        if ticket.get('status') != 'closed':
            resolution_deadline = self.sla_calculator.calculate_resolution_deadline(ticket, policy)
            
            if resolution_deadline and self.sla_calculator.is_breached(resolution_deadline):
                breaches.append({
                    'ticket_id': ticket_id,
                    'type': 'resolution_time',
                    'deadline': resolution_deadline.isoformat(),
                    'breached_at': datetime.now().isoformat(),
                    'policy_id': policy.policy_id
                })
        
        # Иhlalleri сохранить
        if breaches:
            self.breaches[ticket_id] = breaches
            self._save_breaches()
        
        return breaches
    
    def get_ticket_breaches(self, ticket_id: str) -> List[Dict[str, Any]]:
        """Ticket ihlallerini al"""
        return self.breaches.get(ticket_id, [])
    
    def get_all_breaches(self) -> List[Dict[str, Any]]:
        """Все ihlalleri al"""
        all_breaches = []
        
        for ticket_id, breaches in self.breaches.items():
            for breach in breaches:
                breach['ticket_id'] = ticket_id
                all_breaches.append(breach)
        
        return all_breaches


class SLAReporter:
    """Отчёты SLA"""
    
    def __init__(self, sla_manager: SLAManager, breach_detector: SLABreachDetector):
        self.sla_manager = sla_manager
        self.breach_detector = breach_detector
    
    def generate_compliance_report(self, tickets: List[Dict[str, Any]],
                                   start_date: datetime,
                                   end_date: datetime) -> Dict[str, Any]:
        """Uyumluluk raporu создать"""
        total_tickets = len(tickets)
        
        if total_tickets == 0:
            return {
                'total_tickets': 0,
                'response_compliance': 100,
                'resolution_compliance': 100,
                'breached_tickets': 0
            }
        
        response_met = 0
        resolution_met = 0
        breached_tickets = set()
        
        for ticket in tickets:
            breaches = self.breach_detector.check_ticket(ticket)
            
            has_response_breach = any(b['type'] == 'response_time' for b in breaches)
            has_resolution_breach = any(b['type'] == 'resolution_time' for b in breaches)
            
            if not has_response_breach:
                response_met += 1
            
            if not has_resolution_breach:
                resolution_met += 1
            
            if breaches:
                breached_tickets.add(ticket.get('id'))
        
        response_compliance = (response_met / total_tickets) * 100
        resolution_compliance = (resolution_met / total_tickets) * 100
        
        return {
            'period': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat()
            },
            'total_tickets': total_tickets,
            'response_met': response_met,
            'resolution_met': resolution_met,
            'response_compliance': round(response_compliance, 2),
            'resolution_compliance': round(resolution_compliance, 2),
            'breached_tickets': len(breached_tickets),
            'breach_rate': round((len(breached_tickets) / total_tickets) * 100, 2)
        }
    
    def get_breach_summary(self) -> Dict[str, Any]:
        """Получить сводку нарушений"""
        all_breaches = self.breach_detector.get_all_breaches()
        
        response_breaches = [b for b in all_breaches if b['type'] == 'response_time']
        resolution_breaches = [b for b in all_breaches if b['type'] == 'resolution_time']
        
        # Politikaya по grupla
        by_policy = {}
        for breach in all_breaches:
            policy_id = breach.get('policy_id', 'unknown')
            
            if policy_id not in by_policy:
                by_policy[policy_id] = 0
            
            by_policy[policy_id] += 1
        
        return {
            'total_breaches': len(all_breaches),
            'response_breaches': len(response_breaches),
            'resolution_breaches': len(resolution_breaches),
            'by_policy': by_policy
        }


# Global instances
sla_manager = SLAManager()
sla_calculator = SLACalculator(sla_manager)
sla_breach_detector = SLABreachDetector(sla_calculator)
sla_reporter = SLAReporter(sla_manager, sla_breach_detector)
