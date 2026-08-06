"""
Calendar Integration
Takvim entegrasyonu (Google Calendar, Outlook)
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import hashlib


class CalendarEvent:
    """Событие календаря"""
    
    def __init__(self, event_id: str, title: str, start_time: datetime,
                 end_time: datetime, description: str = '',
                 location: str = '', attendees: List[str] = None):
        self.event_id = event_id
        self.title = title
        self.start_time = start_time
        self.end_time = end_time
        self.description = description
        self.location = location
        self.attendees = attendees or []
        self.reminders = []
        self.recurring = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразовать в dict"""
        return {
            'event_id': self.event_id,
            'title': self.title,
            'start_time': self.start_time.isoformat(),
            'end_time': self.end_time.isoformat(),
            'description': self.description,
            'location': self.location,
            'attendees': self.attendees,
            'reminders': self.reminders,
            'recurring': self.recurring
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CalendarEvent':
        """Создать из словаря"""
        event = cls(
            event_id=data['event_id'],
            title=data['title'],
            start_time=datetime.fromisoformat(data['start_time']),
            end_time=datetime.fromisoformat(data['end_time']),
            description=data.get('description', ''),
            location=data.get('location', ''),
            attendees=data.get('attendees', [])
        )
        event.reminders = data.get('reminders', [])
        event.recurring = data.get('recurring')
        return event


class CalendarManager:
    """Менеджер календаря"""
    
    def __init__(self):
        self.events_file = 'data/calendar_events.json'
        self.events = self._load_events()
    
    def _load_events(self) -> Dict[str, Any]:
        """Загрузить события"""
        if os.path.exists(self.events_file):
            try:
                with open(self.events_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return {
                        event_id: CalendarEvent.from_dict(event_data)
                        for event_id, event_data in data.items()
                    }
            except Exception:
                pass
        
        return {}
    
    def _save_events(self):
        """Сохранить события"""
        os.makedirs('data', exist_ok=True)
        
        data = {
            event_id: event.to_dict()
            for event_id, event in self.events.items()
        }
        
        with open(self.events_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def create_event(self, title: str, start_time: datetime,
                     end_time: datetime, description: str = '',
                     location: str = '', attendees: List[str] = None) -> CalendarEvent:
        """Событие создать"""
        event_id = hashlib.md5(f"{title}{start_time.isoformat()}".encode()).hexdigest()[:12]
        
        event = CalendarEvent(
            event_id=event_id,
            title=title,
            start_time=start_time,
            end_time=end_time,
            description=description,
            location=location,
            attendees=attendees
        )
        
        self.events[event_id] = event
        self._save_events()
        
        return event
    
    def update_event(self, event_id: str, **kwargs) -> Optional[CalendarEvent]:
        """Обновить событие"""
        if event_id not in self.events:
            return None
        
        event = self.events[event_id]
        
        for key, value in kwargs.items():
            if hasattr(event, key):
                setattr(event, key, value)
        
        self._save_events()
        
        return event
    
    def delete_event(self, event_id: str) -> bool:
        """Удалить событие"""
        if event_id in self.events:
            del self.events[event_id]
            self._save_events()
            return True
        
        return False
    
    def get_event(self, event_id: str) -> Optional[CalendarEvent]:
        """Получить событие"""
        return self.events.get(event_id)
    
    def get_events(self, start_date: Optional[datetime] = None,
                   end_date: Optional[datetime] = None) -> List[CalendarEvent]:
        """Получить события"""
        events = list(self.events.values())
        
        if start_date:
            events = [e for e in events if e.start_time >= start_date]
        
        if end_date:
            events = [e for e in events if e.start_time <= end_date]
        
        events.sort(key=lambda e: e.start_time)
        
        return events
    
    def get_upcoming_events(self, limit: int = 10) -> List[CalendarEvent]:
        """Получить предстоящие события"""
        now = datetime.now()
        events = [e for e in self.events.values() if e.start_time > now]
        events.sort(key=lambda e: e.start_time)
        return events[:limit]


class GoogleCalendarIntegration:
    """Google Calendar entegrasyonu"""
    
    def __init__(self):
        self.config_file = 'data/google_calendar_config.json'
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Загрузить конфигурацию"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        
        return {
            'client_id': None,
            'client_secret': None,
            'redirect_uri': None,
            'access_token': None,
            'refresh_token': None
        }
    
    def _save_config(self):
        """Сохранить конфигурацию"""
        os.makedirs('data', exist_ok=True)
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)
    
    def setup(self, client_id: str, client_secret: str, redirect_uri: str):
        """Kurulum"""
        self.config['client_id'] = client_id
        self.config['client_secret'] = client_secret
        self.config['redirect_uri'] = redirect_uri
        self._save_config()
    
    def get_auth_url(self) -> str:
        """Yetkilendirme URL'si"""
        # Placeholder - gerчek uygulamada OAuth2 akышы
        return f"https://accounts.google.com/o/oauth2/auth?client_id={self.config.get('client_id', '')}"
    
    def sync_event(self, event: CalendarEvent) -> Dict[str, Any]:
        """Синхронизировать событие"""
        # Placeholder - gerчek uygulamada Google Calendar API чaгrыsы
        return {
            'success': True,
            'google_event_id': f"gcal_{event.event_id}",
            'html_link': f"https://calendar.google.com/calendar/event?eid={event.event_id}"
        }
    
    def delete_event(self, google_event_id: str) -> bool:
        """Удалить событие"""
        # Placeholder
        return True


class OutlookCalendarIntegration:
    """Outlook Calendar entegrasyonu"""
    
    def __init__(self):
        self.config_file = 'data/outlook_calendar_config.json'
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Загрузить конфигурацию"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        
        return {
            'client_id': None,
            'client_secret': None,
            'tenant_id': None,
            'access_token': None
        }
    
    def _save_config(self):
        """Сохранить конфигурацию"""
        os.makedirs('data', exist_ok=True)
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)
    
    def setup(self, client_id: str, client_secret: str, tenant_id: str):
        """Kurulum"""
        self.config['client_id'] = client_id
        self.config['client_secret'] = client_secret
        self.config['tenant_id'] = tenant_id
        self._save_config()
    
    def sync_event(self, event: CalendarEvent) -> Dict[str, Any]:
        """Синхронизировать событие"""
        # Placeholder - gerчek uygulamada Microsoft Graph API чaгrыsы
        return {
            'success': True,
            'outlook_event_id': f"outlook_{event.event_id}",
            'web_link': f"https://outlook.office.com/calendar/event/{event.event_id}"
        }
    
    def delete_event(self, outlook_event_id: str) -> bool:
        """Удалить событие"""
        # Placeholder
        return True


class AppointmentScheduler:
    """Планировщик встреч"""
    
    def __init__(self, calendar_manager: CalendarManager):
        self.calendar_manager = calendar_manager
        self.availability_file = 'data/availability.json'
        self.availability = self._load_availability()
    
    def _load_availability(self) -> Dict[str, Any]:
        """Загрузить доступность"""
        if os.path.exists(self.availability_file):
            try:
                with open(self.availability_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        
        return {}
    
    def _save_availability(self):
        """Сохранить доступность"""
        os.makedirs('data', exist_ok=True)
        with open(self.availability_file, 'w', encoding='utf-8') as f:
            json.dump(self.availability, f, ensure_ascii=False, indent=2)
    
    def set_availability(self, user_id: str, day_of_week: int,
                         start_time: str, end_time: str):
        """Настроить доступность"""
        if user_id not in self.availability:
            self.availability[user_id] = {}
        
        self.availability[user_id][str(day_of_week)] = {
            'start_time': start_time,
            'end_time': end_time
        }
        
        self._save_availability()
    
    def get_available_slots(self, user_id: str, date: datetime,
                            duration_minutes: int = 60) -> List[Dict[str, str]]:
        """Получить доступные временные слоты"""
        day_of_week = date.weekday()
        
        if user_id not in self.availability:
            return []
        
        availability = self.availability[user_id].get(str(day_of_week))
        
        if not availability:
            return []
        
        # Basit implementasyon - gerчek uygulamada mevcut событиеleri проверить et
        slots = []
        start_hour = int(availability['start_time'].split(':')[0])
        end_hour = int(availability['end_time'].split(':')[0])
        
        for hour in range(start_hour, end_hour):
            slot_start = date.replace(hour=hour, minute=0, second=0, microsecond=0)
            slot_end = slot_start + timedelta(minutes=duration_minutes)
            
            slots.append({
                'start': slot_start.isoformat(),
                'end': slot_end.isoformat()
            })
        
        return slots
    
    def book_appointment(self, user_id: str, slot_start: datetime,
                         slot_end: datetime, title: str,
                         attendee_id: str) -> CalendarEvent:
        """Randevu создать"""
        event = self.calendar_manager.create_event(
            title=title,
            start_time=slot_start,
            end_time=slot_end,
            attendees=[user_id, attendee_id]
        )
        
        return event


class ReminderManager:
    """Менеджер напоминаний"""
    
    def __init__(self, calendar_manager: CalendarManager):
        self.calendar_manager = calendar_manager
        self.reminders_file = 'data/reminders.json'
        self.reminders = self._load_reminders()
    
    def _load_reminders(self) -> Dict[str, Any]:
        """Загрузить напоминания"""
        if os.path.exists(self.reminders_file):
            try:
                with open(self.reminders_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        
        return {}
    
    def _save_reminders(self):
        """Сохранить напоминания"""
        os.makedirs('data', exist_ok=True)
        with open(self.reminders_file, 'w', encoding='utf-8') as f:
            json.dump(self.reminders, f, ensure_ascii=False, indent=2)
    
    def add_reminder(self, event_id: str, reminder_minutes: int,
                     reminder_type: str = 'notification') -> Dict[str, Any]:
        """Напоминание добавить"""
        if event_id not in self.reminders:
            self.reminders[event_id] = []
        
        reminder = {
            'minutes_before': reminder_minutes,
            'type': reminder_type,
            'sent': False
        }
        
        self.reminders[event_id].append(reminder)
        self._save_reminders()
        
        return reminder
    
    def get_pending_reminders(self) -> List[Dict[str, Any]]:
        """Получить ожидающие напоминания"""
        now = datetime.now()
        pending = []
        
        for event_id, reminders in self.reminders.items():
            event = self.calendar_manager.get_event(event_id)
            
            if not event:
                continue
            
            for reminder in reminders:
                if reminder.get('sent'):
                    continue
                
                reminder_time = event.start_time - timedelta(minutes=reminder['minutes_before'])
                
                if reminder_time <= now:
                    pending.append({
                        'event_id': event_id,
                        'event': event,
                        'reminder': reminder
                    })
        
        return pending
    
    def mark_reminder_sent(self, event_id: str, reminder_index: int):
        """Отметить напоминание отправленным"""
        if event_id in self.reminders and reminder_index < len(self.reminders[event_id]):
            self.reminders[event_id][reminder_index]['sent'] = True
            self._save_reminders()


# Global instances
calendar_manager = CalendarManager()
google_calendar = GoogleCalendarIntegration()
outlook_calendar = OutlookCalendarIntegration()
appointment_scheduler = AppointmentScheduler(calendar_manager)
reminder_manager = ReminderManager(calendar_manager)
