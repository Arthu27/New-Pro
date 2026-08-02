"""
Time Tracking
Система отслеживания времени
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional


class TimeEntry:
    """Zaman записейi"""
    
    def __init__(self, entry_id: str, ticket_id: str, user_id: str,
                 start_time: datetime, end_time: Optional[datetime] = None,
                 description: str = '', billable: bool = True):
        self.entry_id = entry_id
        self.ticket_id = ticket_id
        self.user_id = user_id
        self.start_time = start_time
        self.end_time = end_time
        self.description = description
        self.billable = billable
        self.tags = []
    
    def get_duration(self) -> timedelta:
        """Длительностьyi al"""
        if self.end_time:
            return self.end_time - self.start_time
        return datetime.now() - self.start_time
    
    def get_duration_hours(self) -> float:
        """Saat cinsinden длительностьyi al"""
        return self.get_duration().total_seconds() / 3600
    
    def to_dict(self) -> Dict[str, Any]:
        """Dict'e чevir"""
        return {
            'entry_id': self.entry_id,
            'ticket_id': self.ticket_id,
            'user_id': self.user_id,
            'start_time': self.start_time.isoformat(),
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'description': self.description,
            'billable': self.billable,
            'tags': self.tags
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TimeEntry':
        """Создать из словаря"""
        entry = cls(
            entry_id=data['entry_id'],
            ticket_id=data['ticket_id'],
            user_id=data['user_id'],
            start_time=datetime.fromisoformat(data['start_time']),
            end_time=datetime.fromisoformat(data['end_time']) if data.get('end_time') else None,
            description=data.get('description', ''),
            billable=data.get('billable', True)
        )
        entry.tags = data.get('tags', [])
        return entry


class TimeTracker:
    """Zaman takipчisi"""
    
    def __init__(self):
        self.entries_file = 'data/time_entries.json'
        self.entries = self._load_entries()
        self.active_timers = {}  # user_id -> entry_id
    
    def _load_entries(self) -> Dict[str, TimeEntry]:
        """Загрузить записи"""
        if os.path.exists(self.entries_file):
            try:
                with open(self.entries_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return {
                        entry_id: TimeEntry.from_dict(entry_data)
                        for entry_id, entry_data in data.items()
                    }
            except Exception:
                pass
        
        return {}
    
    def _save_entries(self):
        """Сохранить записи"""
        os.makedirs('data', exist_ok=True)
        
        data = {
            entry_id: entry.to_dict()
            for entry_id, entry in self.entries.items()
        }
        
        with open(self.entries_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def start_timer(self, ticket_id: str, user_id: str,
                    description: str = '') -> TimeEntry:
        """Zamanlayыcыyы запустить"""
        # Ёnceki zamanlayыcыyы остановить
        if user_id in self.active_timers:
            self.stop_timer(user_id)
        
        entry_id = f"time_{len(self.entries) + 1}"
        
        entry = TimeEntry(
            entry_id=entry_id,
            ticket_id=ticket_id,
            user_id=user_id,
            start_time=datetime.now(),
            description=description
        )
        
        self.entries[entry_id] = entry
        self.active_timers[user_id] = entry_id
        self._save_entries()
        
        return entry
    
    def stop_timer(self, user_id: str) -> Optional[TimeEntry]:
        """Zamanlayыcыyы остановить"""
        if user_id not in self.active_timers:
            return None
        
        entry_id = self.active_timers[user_id]
        entry = self.entries.get(entry_id)
        
        if entry:
            entry.end_time = datetime.now()
            del self.active_timers[user_id]
            self._save_entries()
        
        return entry
    
    def add_manual_entry(self, ticket_id: str, user_id: str,
                         start_time: datetime, end_time: datetime,
                         description: str = '', billable: bool = True) -> TimeEntry:
        """Manuel записей добавить"""
        entry_id = f"time_{len(self.entries) + 1}"
        
        entry = TimeEntry(
            entry_id=entry_id,
            ticket_id=ticket_id,
            user_id=user_id,
            start_time=start_time,
            end_time=end_time,
            description=description,
            billable=billable
        )
        
        self.entries[entry_id] = entry
        self._save_entries()
        
        return entry
    
    def get_active_timer(self, user_id: str) -> Optional[TimeEntry]:
        """Aktif zamanlayыcыyы al"""
        if user_id not in self.active_timers:
            return None
        
        entry_id = self.active_timers[user_id]
        return self.entries.get(entry_id)
    
    def get_user_entries(self, user_id: str, start_date: Optional[datetime] = None,
                         end_date: Optional[datetime] = None) -> List[TimeEntry]:
        """Пользователь записейlerini al"""
        entries = [e for e in self.entries.values() if e.user_id == user_id]
        
        if start_date:
            entries = [e for e in entries if e.start_time >= start_date]
        
        if end_date:
            entries = [e for e in entries if e.start_time <= end_date]
        
        entries.sort(key=lambda e: e.start_time, reverse=True)
        
        return entries
    
    def get_ticket_entries(self, ticket_id: str) -> List[TimeEntry]:
        """Ticket записейlerini al"""
        entries = [e for e in self.entries.values() if e.ticket_id == ticket_id]
        entries.sort(key=lambda e: e.start_time)
        return entries
    
    def get_total_time(self, user_id: Optional[str] = None,
                       ticket_id: Optional[str] = None,
                       start_date: Optional[datetime] = None,
                       end_date: Optional[datetime] = None,
                       billable_only: bool = False) -> float:
        """Всего длительностьyi al (saat)"""
        entries = list(self.entries.values())
        
        if user_id:
            entries = [e for e in entries if e.user_id == user_id]
        
        if ticket_id:
            entries = [e for e in entries if e.ticket_id == ticket_id]
        
        if start_date:
            entries = [e for e in entries if e.start_time >= start_date]
        
        if end_date:
            entries = [e for e in entries if e.start_time <= end_date]
        
        if billable_only:
            entries = [e for e in entries if e.billable]
        
        total_hours = sum(e.get_duration_hours() for e in entries if e.end_time)
        
        return round(total_hours, 2)
    
    def delete_entry(self, entry_id: str) -> bool:
        """Входi удалить"""
        if entry_id in self.entries:
            del self.entries[entry_id]
            self._save_entries()
            return True
        
        return False


class PomodoroTimer:
    """Pomodoro zamanlayыcы"""
    
    def __init__(self):
        self.sessions_file = 'data/pomodoro_sessions.json'
        self.sessions = self._load_sessions()
        self.active_sessions = {}  # user_id -> session
    
    def _load_sessions(self) -> Dict[str, Any]:
        """Oturumlarы загрузить"""
        if os.path.exists(self.sessions_file):
            try:
                with open(self.sessions_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        
        return {}
    
    def _save_sessions(self):
        """Oturumlarы сохранить"""
        os.makedirs('data', exist_ok=True)
        with open(self.sessions_file, 'w', encoding='utf-8') as f:
            json.dump(self.sessions, f, ensure_ascii=False, indent=2)
    
    def start_session(self, user_id: str, work_minutes: int = 25,
                      break_minutes: int = 5) -> Dict[str, Any]:
        """Oturumu запустить"""
        session = {
            'user_id': user_id,
            'work_minutes': work_minutes,
            'break_minutes': break_minutes,
            'start_time': datetime.now().isoformat(),
            'status': 'working',
            'completed_pomodoros': 0
        }
        
        self.active_sessions[user_id] = session
        return session
    
    def complete_pomodoro(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Pomodoro'yu tamamla"""
        if user_id not in self.active_sessions:
            return None
        
        session = self.active_sessions[user_id]
        session['completed_pomodoros'] += 1
        session['status'] = 'break'
        
        # Kaydet
        if user_id not in self.sessions:
            self.sessions[user_id] = []
        
        self.sessions[user_id].append({
            'timestamp': datetime.now().isoformat(),
            'work_minutes': session['work_minutes']
        })
        
        self._save_sessions()
        
        return session
    
    def end_session(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Oturumu sonlandыr"""
        if user_id not in self.active_sessions:
            return None
        
        session = self.active_sessions[user_id]
        del self.active_sessions[user_id]
        
        return session
    
    def get_active_session(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Aktif oturumu al"""
        return self.active_sessions.get(user_id)
    
    def get_user_stats(self, user_id: str, days: int = 7) -> Dict[str, Any]:
        """Пользователь статистикаini al"""
        if user_id not in self.sessions:
            return {
                'total_pomodoros': 0,
                'total_hours': 0,
                'avg_per_day': 0
            }
        
        cutoff_date = datetime.now() - timedelta(days=days)
        
        recent_sessions = [
            s for s in self.sessions[user_id]
            if datetime.fromisoformat(s['timestamp']) >= cutoff_date
        ]
        
        total_pomodoros = len(recent_sessions)
        total_minutes = sum(s.get('work_minutes', 25) for s in recent_sessions)
        total_hours = total_minutes / 60
        
        return {
            'total_pomodoros': total_pomodoros,
            'total_hours': round(total_hours, 2),
            'avg_per_day': round(total_pomodoros / days, 2)
        }


class TimeEstimator:
    """Zaman tahmincisi"""
    
    def __init__(self, time_tracker: TimeTracker):
        self.time_tracker = time_tracker
        self.estimates_file = 'data/time_estimates.json'
        self.estimates = self._load_estimates()
    
    def _load_estimates(self) -> Dict[str, Any]:
        """Tahminleri загрузить"""
        if os.path.exists(self.estimates_file):
            try:
                with open(self.estimates_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        
        return {}
    
    def _save_estimates(self):
        """Tahminleri сохранить"""
        os.makedirs('data', exist_ok=True)
        with open(self.estimates_file, 'w', encoding='utf-8') as f:
            json.dump(self.estimates, f, ensure_ascii=False, indent=2)
    
    def set_estimate(self, ticket_id: str, estimated_hours: float,
                     user_id: str) -> Dict[str, Any]:
        """Tahmin настроить"""
        estimate = {
            'ticket_id': ticket_id,
            'estimated_hours': estimated_hours,
            'set_by': user_id,
            'set_at': datetime.now().isoformat()
        }
        
        self.estimates[ticket_id] = estimate
        self._save_estimates()
        
        return estimate
    
    def get_estimate(self, ticket_id: str) -> Optional[Dict[str, Any]]:
        """Tahmini al"""
        return self.estimates.get(ticket_id)
    
    def get_actual_vs_estimate(self, ticket_id: str) -> Dict[str, Any]:
        """Gerчek vs tahmin karшыlaшtыrmasы"""
        estimate = self.estimates.get(ticket_id)
        
        if not estimate:
            return {
                'ticket_id': ticket_id,
                'estimated_hours': None,
                'actual_hours': None,
                'difference': None
            }
        
        actual_hours = self.time_tracker.get_total_time(ticket_id=ticket_id)
        estimated_hours = estimate['estimated_hours']
        difference = actual_hours - estimated_hours
        
        return {
            'ticket_id': ticket_id,
            'estimated_hours': estimated_hours,
            'actual_hours': actual_hours,
            'difference': round(difference, 2),
            'over_estimate': difference > 0
        }
    
    def get_average_by_category(self) -> Dict[str, float]:
        """Kategoriye по ortalama длительность"""
        # Basit implementasyon - gerчek uygulamada ticket kategorileri ile объединитьilecek
        category_times = {}
        
        for entry in self.time_tracker.entries.values():
            if not entry.end_time:
                continue
            
            # Placeholder - gerчek kategorхорошо al
            category = 'general'
            
            if category not in category_times:
                category_times[category] = []
            
            category_times[category].append(entry.get_duration_hours())
        
        averages = {
            category: round(sum(times) / len(times), 2)
            for category, times in category_times.items()
        }
        
        return averages


class TimeReport:
    """Zaman raporu"""
    
    def __init__(self, time_tracker: TimeTracker):
        self.time_tracker = time_tracker
    
    def generate_user_report(self, user_id: str, start_date: datetime,
                             end_date: datetime) -> Dict[str, Any]:
        """Пользователь raporu создать"""
        entries = self.time_tracker.get_user_entries(user_id, start_date, end_date)
        
        total_hours = sum(e.get_duration_hours() for e in entries if e.end_time)
        billable_hours = sum(e.get_duration_hours() for e in entries if e.end_time and e.billable)
        
        # Деньlere по grupla
        by_day = {}
        for entry in entries:
            if not entry.end_time:
                continue
            
            day = entry.start_time.strftime('%Y-%m-%d')
            
            if day not in by_day:
                by_day[day] = 0
            
            by_day[day] += entry.get_duration_hours()
        
        # Ticket'lara по grupla
        by_ticket = {}
        for entry in entries:
            if not entry.end_time:
                continue
            
            ticket_id = entry.ticket_id
            
            if ticket_id not in by_ticket:
                by_ticket[ticket_id] = 0
            
            by_ticket[ticket_id] += entry.get_duration_hours()
        
        return {
            'user_id': user_id,
            'period': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat()
            },
            'total_hours': round(total_hours, 2),
            'billable_hours': round(billable_hours, 2),
            'non_billable_hours': round(total_hours - billable_hours, 2),
            'total_entries': len(entries),
            'by_day': by_day,
            'by_ticket': by_ticket
        }
    
    def generate_project_report(self, ticket_ids: List[str],
                                start_date: datetime,
                                end_date: datetime) -> Dict[str, Any]:
        """Proje raporu создать"""
        all_entries = []
        
        for ticket_id in ticket_ids:
            entries = self.time_tracker.get_ticket_entries(ticket_id)
            entries = [e for e in entries if start_date <= e.start_time <= end_date]
            all_entries.extend(entries)
        
        total_hours = sum(e.get_duration_hours() for e in all_entries if e.end_time)
        
        # Пользовательlara по grupla
        by_user = {}
        for entry in all_entries:
            if not entry.end_time:
                continue
            
            user_id = entry.user_id
            
            if user_id not in by_user:
                by_user[user_id] = 0
            
            by_user[user_id] += entry.get_duration_hours()
        
        return {
            'ticket_ids': ticket_ids,
            'period': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat()
            },
            'total_hours': round(total_hours, 2),
            'total_entries': len(all_entries),
            'by_user': by_user,
            'by_ticket': {
                ticket_id: self.time_tracker.get_total_time(ticket_id=ticket_id,
                                                           start_date=start_date,
                                                           end_date=end_date)
                for ticket_id in ticket_ids
            }
        }


# Global instances
time_tracker = TimeTracker()
pomodoro_timer = PomodoroTimer()
time_estimator = TimeEstimator(time_tracker)
time_report = TimeReport(time_tracker)
