"""
Advanced Notifications
Расширенная система уведомлений
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from enum import Enum


class NotificationChannel(Enum):
    """Каналы уведомлений"""
    IN_APP = 'in_app'
    EMAIL = 'email'
    SLACK = 'slack'
    DISCORD = 'discord'
    TELEGRAM = 'telegram'
    SMS = 'sms'
    WEBHOOK = 'webhook'


class NotificationPriority(Enum):
    """Приоритеты уведомлений"""
    LOW = 'low'
    MEDIUM = 'medium'
    HIGH = 'high'
    URGENT = 'urgent'


class Notification:
    """Уведомление"""
    
    def __init__(self, notification_id: str, recipient_id: str,
                 title: str, message: str, channel: NotificationChannel,
                 priority: NotificationPriority = NotificationPriority.MEDIUM):
        self.notification_id = notification_id
        self.recipient_id = recipient_id
        self.title = title
        self.message = message
        self.channel = channel
        self.priority = priority
        self.created_at = datetime.now().isoformat()
        self.sent_at = None
        self.read_at = None
        self.status = 'pending'  # pending, sent, read, failed
        self.metadata = {}
        self.retry_count = 0
    
    def mark_sent(self):
        """Отметить как отправленное"""
        self.status = 'sent'
        self.sent_at = datetime.now().isoformat()
    
    def mark_read(self):
        """Отметить как прочитанное"""
        self.status = 'read'
        self.read_at = datetime.now().isoformat()
    
    def mark_failed(self, error: str):
        """Пометить как неудачное"""
        self.status = 'failed'
        self.retry_count += 1
        self.metadata['last_error'] = error
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразовать в dict"""
        return {
            'notification_id': self.notification_id,
            'recipient_id': self.recipient_id,
            'title': self.title,
            'message': self.message,
            'channel': self.channel.value,
            'priority': self.priority.value,
            'created_at': self.created_at,
            'sent_at': self.sent_at,
            'read_at': self.read_at,
            'status': self.status,
            'metadata': self.metadata,
            'retry_count': self.retry_count
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Notification':
        """Создать из словаря"""
        notif = cls(
            notification_id=data['notification_id'],
            recipient_id=data['recipient_id'],
            title=data['title'],
            message=data['message'],
            channel=NotificationChannel(data['channel']),
            priority=NotificationPriority(data['priority'])
        )
        notif.created_at = data.get('created_at')
        notif.sent_at = data.get('sent_at')
        notif.read_at = data.get('read_at')
        notif.status = data.get('status', 'pending')
        notif.metadata = data.get('metadata', {})
        notif.retry_count = data.get('retry_count', 0)
        return notif


class NotificationRule:
    """Правило уведомлений"""
    
    def __init__(self, rule_id: str, name: str, event_type: str,
                 channels: List[NotificationChannel],
                 conditions: List[Dict[str, Any]] = None):
        self.rule_id = rule_id
        self.name = name
        self.event_type = event_type
        self.channels = channels
        self.conditions = conditions or []
        self.enabled = True
        self.priority = NotificationPriority.MEDIUM
        self.template_id = None
    
    def matches_event(self, event: Dict[str, Any]) -> bool:
        """Проверить, совпадает ли с событием"""
        if not self.enabled:
            return False
        
        if event.get('type') != self.event_type:
            return False
        
        # Koэтотllarы проверить et
        for condition in self.conditions:
            field = condition.get('field')
            operator = condition.get('operator')
            value = condition.get('value')
            
            event_value = event.get(field)
            
            if operator == 'equals' and event_value != value:
                return False
            elif operator == 'not_equals' and event_value == value:
                return False
            elif operator == 'contains' and value not in str(event_value):
                return False
            elif operator == 'greater_than' and event_value <= value:
                return False
            elif operator == 'less_than' and event_value >= value:
                return False
        
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразовать в dict"""
        return {
            'rule_id': self.rule_id,
            'name': self.name,
            'event_type': self.event_type,
            'channels': [ch.value for ch in self.channels],
            'conditions': self.conditions,
            'enabled': self.enabled,
            'priority': self.priority.value,
            'template_id': self.template_id
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'NotificationRule':
        """Создать из словаря"""
        rule = cls(
            rule_id=data['rule_id'],
            name=data['name'],
            event_type=data['event_type'],
            channels=[NotificationChannel(ch) for ch in data['channels']],
            conditions=data.get('conditions', [])
        )
        rule.enabled = data.get('enabled', True)
        rule.priority = NotificationPriority(data.get('priority', 'medium'))
        rule.template_id = data.get('template_id')
        return rule


class NotificationManager:
    """Менеджер уведомлений"""
    
    def __init__(self):
        self.notifications_file = 'data/notifications.json'
        self.notifications = self._load_notifications()
    
    def _load_notifications(self) -> Dict[str, Notification]:
        """Загрузить уведомления"""
        if os.path.exists(self.notifications_file):
            try:
                with open(self.notifications_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return {
                        notif_id: Notification.from_dict(notif_data)
                        for notif_id, notif_data in data.items()
                    }
            except Exception:
                pass
        
        return {}
    
    def _save_notifications(self):
        """Сохранить уведомления"""
        os.makedirs('data', exist_ok=True)
        
        data = {
            notif_id: notif.to_dict()
            for notif_id, notif in self.notifications.items()
        }
        
        with open(self.notifications_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def create_notification(self, recipient_id: str, title: str, message: str,
                            channel: NotificationChannel,
                            priority: NotificationPriority = NotificationPriority.MEDIUM,
                            metadata: Dict[str, Any] = None) -> Notification:
        """Уведомление создать"""
        notification_id = f"notif_{len(self.notifications) + 1}"
        
        notification = Notification(
            notification_id=notification_id,
            recipient_id=recipient_id,
            title=title,
            message=message,
            channel=channel,
            priority=priority
        )
        
        if metadata:
            notification.metadata = metadata
        
        self.notifications[notification_id] = notification
        self._save_notifications()
        
        return notification
    
    def get_notification(self, notification_id: str) -> Optional[Notification]:
        """Получить уведомление"""
        return self.notifications.get(notification_id)
    
    def get_user_notifications(self, user_id: str, unread_only: bool = False) -> List[Notification]:
        """Получить уведомления пользователя"""
        notifications = [
            n for n in self.notifications.values()
            if n.recipient_id == user_id
        ]
        
        if unread_only:
            notifications = [n for n in notifications if n.status != 'read']
        
        notifications.sort(key=lambda n: n.created_at, reverse=True)
        
        return notifications
    
    def mark_as_read(self, notification_id: str) -> bool:
        """Отметить как прочитанное"""
        notification = self.notifications.get(notification_id)
        
        if notification:
            notification.mark_read()
            self._save_notifications()
            return True
        
        return False
    
    def mark_all_as_read(self, user_id: str) -> int:
        """Пометить все как прочитанные"""
        count = 0
        
        for notification in self.notifications.values():
            if notification.recipient_id == user_id and notification.status != 'read':
                notification.mark_read()
                count += 1
        
        if count > 0:
            self._save_notifications()
        
        return count
    
    def get_unread_count(self, user_id: str) -> int:
        """Получить количество непрочитанных уведомлений"""
        return sum(
            1 for n in self.notifications.values()
            if n.recipient_id == user_id and n.status != 'read'
        )
    
    def delete_notification(self, notification_id: str) -> bool:
        """Удалить уведомление"""
        if notification_id in self.notifications:
            del self.notifications[notification_id]
            self._save_notifications()
            return True
        
        return False


class NotificationRuleManager:
    """Менеджер правил уведомлений"""
    
    def __init__(self):
        self.rules_file = 'data/notification_rules.json'
        self.rules = self._load_rules()
    
    def _load_rules(self) -> Dict[str, NotificationRule]:
        """Загрузить правила"""
        if os.path.exists(self.rules_file):
            try:
                with open(self.rules_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return {
                        rule_id: NotificationRule.from_dict(rule_data)
                        for rule_id, rule_data in data.items()
                    }
            except Exception:
                pass
        
        return {}
    
    def _save_rules(self):
        """Сохранить правила"""
        os.makedirs('data', exist_ok=True)
        
        data = {
            rule_id: rule.to_dict()
            for rule_id, rule in self.rules.items()
        }
        
        with open(self.rules_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def create_rule(self, name: str, event_type: str,
                    channels: List[NotificationChannel],
                    conditions: List[Dict[str, Any]] = None) -> NotificationRule:
        """Kural создать"""
        rule_id = f"rule_{len(self.rules) + 1}"
        
        rule = NotificationRule(
            rule_id=rule_id,
            name=name,
            event_type=event_type,
            channels=channels,
            conditions=conditions
        )
        
        self.rules[rule_id] = rule
        self._save_rules()
        
        return rule
    
    def update_rule(self, rule_id: str, **kwargs) -> Optional[NotificationRule]:
        """Обновить правило"""
        if rule_id not in self.rules:
            return None
        
        rule = self.rules[rule_id]
        
        for key, value in kwargs.items():
            if hasattr(rule, key):
                setattr(rule, key, value)
        
        self._save_rules()
        
        return rule
    
    def delete_rule(self, rule_id: str) -> bool:
        """Удалить правило"""
        if rule_id in self.rules:
            del self.rules[rule_id]
            self._save_rules()
            return True
        
        return False
    
    def get_rule(self, rule_id: str) -> Optional[NotificationRule]:
        """Получить правило"""
        return self.rules.get(rule_id)
    
    def get_all_rules(self) -> List[NotificationRule]:
        """Получить все правила"""
        return list(self.rules.values())
    
    def get_rules_for_event(self, event: Dict[str, Any]) -> List[NotificationRule]:
        """Получить правила для события"""
        return [
            rule for rule in self.rules.values()
            if rule.matches_event(event)
        ]
    
    def enable_rule(self, rule_id: str) -> bool:
        """Включить правило"""
        rule = self.rules.get(rule_id)
        
        if rule:
            rule.enabled = True
            self._save_rules()
            return True
        
        return False
    
    def disable_rule(self, rule_id: str) -> bool:
        """Отключить правило"""
        rule = self.rules.get(rule_id)
        
        if rule:
            rule.enabled = False
            self._save_rules()
            return True
        
        return False


class NotificationTemplate:
    """Шаблон уведомления"""
    
    def __init__(self):
        self.templates_file = 'data/notification_templates.json'
        self.templates = self._load_templates()
    
    def _load_templates(self) -> Dict[str, Any]:
        """Загрузить шаблоны"""
        if os.path.exists(self.templates_file):
            try:
                with open(self.templates_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        
        return {}
    
    def _save_templates(self):
        """Сохранить шаблоны"""
        os.makedirs('data', exist_ok=True)
        with open(self.templates_file, 'w', encoding='utf-8') as f:
            json.dump(self.templates, f, ensure_ascii=False, indent=2)
    
    def create_template(self, template_id: str, title_template: str,
                        message_template: str) -> Dict[str, Any]:
        """Создать шаблон"""
        template = {
            'template_id': template_id,
            'title_template': title_template,
            'message_template': message_template,
            'created_at': datetime.now().isoformat()
        }
        
        self.templates[template_id] = template
        self._save_templates()
        
        return template
    
    def get_template(self, template_id: str) -> Optional[Dict[str, Any]]:
        """Получить шаблон"""
        return self.templates.get(template_id)
    
    def render_template(self, template_id: str, context: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """Отрендерить шаблон"""
        template = self.templates.get(template_id)
        
        if not template:
            return None
        
        try:
            title = template['title_template'].format(**context)
            message = template['message_template'].format(**context)
            
            return {
                'title': title,
                'message': message
            }
        except (KeyError, ValueError):
            return None
    
    def delete_template(self, template_id: str) -> bool:
        """Удалить шаблон"""
        if template_id in self.templates:
            del self.templates[template_id]
            self._save_templates()
            return True
        
        return False


class NotificationScheduler:
    """Планировщик уведомлений"""
    
    def __init__(self, notification_manager: NotificationManager):
        self.notification_manager = notification_manager
        self.scheduled_file = 'data/scheduled_notifications.json'
        self.scheduled = self._load_scheduled()
    
    def _load_scheduled(self) -> Dict[str, Any]:
        """Загрузить запланированные уведомления"""
        if os.path.exists(self.scheduled_file):
            try:
                with open(self.scheduled_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        
        return {}
    
    def _save_scheduled(self):
        """Сохранить запланированные уведомления"""
        os.makedirs('data', exist_ok=True)
        with open(self.scheduled_file, 'w', encoding='utf-8') as f:
            json.dump(self.scheduled, f, ensure_ascii=False, indent=2)
    
    def schedule_notification(self, recipient_id: str, title: str, message: str,
                              channel: NotificationChannel, send_at: datetime,
                              priority: NotificationPriority = NotificationPriority.MEDIUM) -> str:
        """Уведомление zamanla"""
        schedule_id = f"sched_{len(self.scheduled) + 1}"
        
        self.scheduled[schedule_id] = {
            'schedule_id': schedule_id,
            'recipient_id': recipient_id,
            'title': title,
            'message': message,
            'channel': channel.value,
            'priority': priority.value,
            'send_at': send_at.isoformat(),
            'sent': False
        }
        
        self._save_scheduled()
        
        return schedule_id
    
    def get_pending_notifications(self) -> List[Dict[str, Any]]:
        """Получить ожидающие уведомления"""
        now = datetime.now()
        pending = []
        
        for schedule_id, sched in self.scheduled.items():
            if sched.get('sent'):
                continue
            
            send_at = datetime.fromisoformat(sched['send_at'])
            
            if send_at <= now:
                pending.append(sched)
        
        return pending
    
    def mark_as_sent(self, schedule_id: str):
        """Отметить как отправленное"""
        if schedule_id in self.scheduled:
            self.scheduled[schedule_id]['sent'] = True
            self._save_scheduled()
    
    def cancel_scheduled(self, schedule_id: str) -> bool:
        """Отменить запланированное уведомление"""
        if schedule_id in self.scheduled:
            del self.scheduled[schedule_id]
            self._save_scheduled()
            return True
        
        return False


class DigestNotification:
    """Сводное уведомление"""
    
    def __init__(self, notification_manager: NotificationManager):
        self.notification_manager = notification_manager
        self.digest_config_file = 'data/digest_config.json'
        self.digest_config = self._load_digest_config()
    
    def _load_digest_config(self) -> Dict[str, Any]:
        """Загрузить конфигурацию сводки"""
        if os.path.exists(self.digest_config_file):
            try:
                with open(self.digest_config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        
        return {}
    
    def _save_digest_config(self):
        """Сохранить конфигурацию сводки"""
        os.makedirs('data', exist_ok=True)
        with open(self.digest_config_file, 'w', encoding='utf-8') as f:
            json.dump(self.digest_config, f, ensure_ascii=False, indent=2)
    
    def configure_digest(self, user_id: str, frequency: str,
                         channel: NotificationChannel, quiet_hours: List[int] = None):
        """Конфигурация сводки"""
        self.digest_config[user_id] = {
            'frequency': frequency,  # daily, weekly
            'channel': channel.value,
            'quiet_hours': quiet_hours or [],
            'last_sent': None
        }
        
        self._save_digest_config()
    
    def get_digest_config(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Получить конфигурацию сводки"""
        return self.digest_config.get(user_id)
    
    def should_send_digest(self, user_id: str) -> bool:
        """Проверить, нужно ли отправить сводку"""
        config = self.digest_config.get(user_id)
        
        if not config:
            return False
        
        last_sent = config.get('last_sent')
        
        if not last_sent:
            return True
        
        last_sent_dt = datetime.fromisoformat(last_sent)
        now = datetime.now()
        
        frequency = config.get('frequency')
        
        if frequency == 'daily':
            return (now - last_sent_dt).days >= 1
        elif frequency == 'weekly':
            return (now - last_sent_dt).days >= 7
        
        return False
    
    def generate_digest(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Создать сводку"""
        config = self.digest_config.get(user_id)
        
        if not config:
            return None
        
        # Пользовательnыn okunmaлиш уведомлениеlerini al
        notifications = self.notification_manager.get_user_notifications(user_id, unread_only=True)
        
        if not notifications:
            return None
        
        # Ёnceliгe по grupla
        by_priority = {
            'urgent': [],
            'high': [],
            'medium': [],
            'low': []
        }
        
        for notif in notifications:
            by_priority[notif.priority.value].append(notif)
        
        return {
            'user_id': user_id,
            'total_count': len(notifications),
            'by_priority': {
                priority: len(notifs)
                for priority, notifs in by_priority.items()
            },
            'notifications': notifications[:20]  # Иlk 20 уведомление
        }
    
    def mark_digest_sent(self, user_id: str):
        """Пометить сводку как отправленную"""
        if user_id in self.digest_config:
            self.digest_config[user_id]['last_sent'] = datetime.now().isoformat()
            self._save_digest_config()


# Global instances
notification_manager = NotificationManager()
notification_rule_manager = NotificationRuleManager()
notification_template = NotificationTemplate()
notification_scheduler = NotificationScheduler(notification_manager)
digest_notification = DigestNotification(notification_manager)
