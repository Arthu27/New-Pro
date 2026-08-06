"""
Gamification
Система геймификации (значки, очки, уровни)
"""
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional


class BadgeSystem:
    """Система значков"""
    
    BADGES = {
        'first_ticket': {
            'name': 'Первый тикет',
            'description': 'Создал первый тикет',
            'icon': '',
            'points': 10
        },
        'ticket_master': {
            'name': 'Мастер тикетов',
            'description': 'Создал 10 тикетов',
            'icon': '',
            'points': 50
        },
        'helpful_user': {
            'name': 'Полезный пользователь',
            'description': 'Получил 5 положительных отзывов',
            'icon': '',
            'points': 100
        },
        'quick_responder': {
            'name': 'Быстрый ответ',
            'description': 'Тикет решен менее чем за 1 час',
            'icon': '',
            'points': 75
        },
        'streak_7': {
            'name': '7 дней подряд',
            'description': 'Активность 7 дней подряд',
            'icon': '',
            'points': 150
        },
        'streak_30': {
            'name': '30 дней подряд',
            'description': 'Активность 30 дней подряд',
            'icon': '',
            'points': 500
        },
        'top_rated': {
            'name': 'Лучший рейтинг',
            'description': 'Средний рейтинг 4.5+',
            'icon': '',
            'points': 200
        },
        'problem_solver': {
            'name': 'Решатель проблем',
            'description': 'Решил 50 тикетов',
            'icon': '',
            'points': 300
        }
    }
    
    def __init__(self):
        self.user_badges_file = 'data/user_badges.json'
        self.user_badges = self._load_user_badges()
    
    def _load_user_badges(self) -> Dict[str, Any]:
        """Загрузить значки пользователя"""
        if os.path.exists(self.user_badges_file):
            try:
                with open(self.user_badges_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        
        return {}
    
    def _save_user_badges(self):
        """Сохранить значки пользователя"""
        os.makedirs('data', exist_ok=True)
        with open(self.user_badges_file, 'w', encoding='utf-8') as f:
            json.dump(self.user_badges, f, ensure_ascii=False, indent=2)
    
    def award_badge(self, user_id: str, badge_id: str) -> Optional[Dict[str, Any]]:
        """Значок ver"""
        if badge_id not in self.BADGES:
            return None
        
        if user_id not in self.user_badges:
            self.user_badges[user_id] = []
        
        # Zaten varsa verme
        if any(b['badge_id'] == badge_id for b in self.user_badges[user_id]):
            return None
        
        badge = self.BADGES[badge_id]
        awarded_badge = {
            'badge_id': badge_id,
            'name': badge['name'],
            'description': badge['description'],
            'icon': badge['icon'],
            'points': badge['points'],
            'awarded_at': datetime.now().isoformat()
        }
        
        self.user_badges[user_id].append(awarded_badge)
        self._save_user_badges()
        
        return awarded_badge
    
    def get_user_badges(self, user_id: str) -> List[Dict[str, Any]]:
        """Пользователь rozetlerini al"""
        return self.user_badges.get(user_id, [])
    
    def get_total_points(self, user_id: str) -> int:
        """Получить общие очки"""
        badges = self.user_badges.get(user_id, [])
        return sum(badge.get('points', 0) for badge in badges)
    
    def check_and_award_badges(self, user_id: str, stats: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Проверить и выдать значки по статистике"""
        awarded = []
        
        # Иlk ticket
        if stats.get('total_tickets', 0) >= 1:
            badge = self.award_badge(user_id, 'first_ticket')
            if badge:
                awarded.append(badge)
        
        # Ticket master
        if stats.get('total_tickets', 0) >= 10:
            badge = self.award_badge(user_id, 'ticket_master')
            if badge:
                awarded.append(badge)
        
        # Helpful user
        if stats.get('positive_ratings', 0) >= 5:
            badge = self.award_badge(user_id, 'helpful_user')
            if badge:
                awarded.append(badge)
        
        # Quick responder
        if stats.get('quick_resolutions', 0) >= 1:
            badge = self.award_badge(user_id, 'quick_responder')
            if badge:
                awarded.append(badge)
        
        # Streak 7
        if stats.get('streak_days', 0) >= 7:
            badge = self.award_badge(user_id, 'streak_7')
            if badge:
                awarded.append(badge)
        
        # Streak 30
        if stats.get('streak_days', 0) >= 30:
            badge = self.award_badge(user_id, 'streak_30')
            if badge:
                awarded.append(badge)
        
        # Top rated
        if stats.get('avg_rating', 0) >= 4.5:
            badge = self.award_badge(user_id, 'top_rated')
            if badge:
                awarded.append(badge)
        
        # Problem solver
        if stats.get('resolved_tickets', 0) >= 50:
            badge = self.award_badge(user_id, 'problem_solver')
            if badge:
                awarded.append(badge)
        
        return awarded
    
    def get_all_badges(self) -> Dict[str, Any]:
        """Все rozetleri al"""
        return self.BADGES.copy()


class PointsSystem:
    """Система очков"""
    
    def __init__(self):
        self.user_points_file = 'data/user_points.json'
        self.user_points = self._load_user_points()
    
    def _load_user_points(self) -> Dict[str, Any]:
        """Загрузить очки пользователя"""
        if os.path.exists(self.user_points_file):
            try:
                with open(self.user_points_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        
        return {}
    
    def _save_user_points(self):
        """Сохранить очки пользователя"""
        os.makedirs('data', exist_ok=True)
        with open(self.user_points_file, 'w', encoding='utf-8') as f:
            json.dump(self.user_points, f, ensure_ascii=False, indent=2)
    
    def add_points(self, user_id: str, points: int, reason: str) -> Dict[str, Any]:
        """Очки добавить"""
        if user_id not in self.user_points:
            self.user_points[user_id] = {
                'total_points': 0,
                'history': []
            }
        
        self.user_points[user_id]['total_points'] += points
        self.user_points[user_id]['history'].append({
            'points': points,
            'reason': reason,
            'timestamp': datetime.now().isoformat()
        })
        
        self._save_user_points()
        
        return {
            'user_id': user_id,
            'points_added': points,
            'total_points': self.user_points[user_id]['total_points'],
            'reason': reason
        }
    
    def get_points(self, user_id: str) -> int:
        """Получить очки"""
        return self.user_points.get(user_id, {}).get('total_points', 0)
    
    def get_points_history(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Получить историю очков"""
        history = self.user_points.get(user_id, {}).get('history', [])
        return history[-limit:]
    
    def get_leaderboard(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Lider tablosunu al"""
        leaderboard = [
            {
                'user_id': user_id,
                'total_points': data['total_points']
            }
            for user_id, data in self.user_points.items()
        ]
        
        leaderboard.sort(key=lambda x: x['total_points'], reverse=True)
        
        return leaderboard[:limit]


class LevelSystem:
    """Система уровней"""
    
    LEVELS = {
        1: {'name': 'Новичок', 'min_points': 0, 'icon': ''},
        2: {'name': 'Ученик', 'min_points': 100, 'icon': ''},
        3: {'name': 'Опытный', 'min_points': 500, 'icon': ''},
        4: {'name': 'Эксперт', 'min_points': 1000, 'icon': ''},
        5: {'name': 'Мастер', 'min_points': 2500, 'icon': ''},
        6: {'name': 'Гуру', 'min_points': 5000, 'icon': ''},
        7: {'name': 'Легенда', 'min_points': 10000, 'icon': ''}
    }
    
    def __init__(self, points_system: PointsSystem):
        self.points_system = points_system
    
    def get_level(self, user_id: str) -> Dict[str, Any]:
        """Получить уровень"""
        points = self.points_system.get_points(user_id)
        
        current_level = 1
        for level, data in sorted(self.LEVELS.items(), reverse=True):
            if points >= data['min_points']:
                current_level = level
                break
        
        level_data = self.LEVELS[current_level]
        
        # Sonraki уровень
        next_level = current_level + 1
        next_level_data = self.LEVELS.get(next_level)
        
        if next_level_data:
            points_to_next = next_level_data['min_points'] - points
            progress = (points - level_data['min_points']) / (next_level_data['min_points'] - level_data['min_points']) * 100
        else:
            points_to_next = 0
            progress = 100
        
        return {
            'level': current_level,
            'name': level_data['name'],
            'icon': level_data['icon'],
            'points': points,
            'min_points': level_data['min_points'],
            'next_level': next_level if next_level_data else None,
            'next_level_name': next_level_data['name'] if next_level_data else None,
            'points_to_next': points_to_next,
            'progress': round(progress, 2)
        }
    
    def get_all_levels(self) -> Dict[int, Dict[str, Any]]:
        """Получить все уровни"""
        return self.LEVELS.copy()


class Leaderboard:
    """Lider tablosu"""
    
    def __init__(self, points_system: PointsSystem, badge_system: BadgeSystem):
        self.points_system = points_system
        self.badge_system = badge_system
        self.leaderboard_file = 'data/leaderboard_cache.json'
    
    def get_overall_leaderboard(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Genel lider tablosunu al"""
        points_leaderboard = self.points_system.get_leaderboard(limit)
        
        leaderboard = []
        for entry in points_leaderboard:
            user_id = entry['user_id']
            badges = self.badge_system.get_user_badges(user_id)
            
            leaderboard.append({
                'user_id': user_id,
                'total_points': entry['total_points'],
                'badge_count': len(badges),
                'badges': badges[:3]  # Иlk 3 rozet
            })
        
        return leaderboard
    
    def get_weekly_leaderboard(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Еженедельный lider tablosunu al"""
        # Basit implementasyon - gerчek uygulamada еженедельный очки hesaplanacak
        return self.get_overall_leaderboard(limit)
    
    def get_monthly_leaderboard(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Получить месячную таблицу лидеров"""
        # Basit implementasyon - gerчek uygulamada aylыk очки hesaplanacak
        return self.get_overall_leaderboard(limit)


class StreakTracker:
    """Трекер серий"""
    
    def __init__(self):
        self.streaks_file = 'data/user_streaks.json'
        self.streaks = self._load_streaks()
    
    def _load_streaks(self) -> Dict[str, Any]:
        """Serileri загрузить"""
        if os.path.exists(self.streaks_file):
            try:
                with open(self.streaks_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        
        return {}
    
    def _save_streaks(self):
        """Serileri сохранить"""
        os.makedirs('data', exist_ok=True)
        with open(self.streaks_file, 'w', encoding='utf-8') as f:
            json.dump(self.streaks, f, ensure_ascii=False, indent=2)
    
    def update_streak(self, user_id: str) -> Dict[str, Any]:
        """Обновить серию"""
        today = datetime.now().date()
        
        if user_id not in self.streaks:
            self.streaks[user_id] = {
                'current_streak': 0,
                'longest_streak': 0,
                'last_activity': None
            }
        
        streak_data = self.streaks[user_id]
        last_activity = streak_data.get('last_activity')
        
        if last_activity:
            last_date = datetime.fromisoformat(last_activity).date()
            days_diff = (today - last_date).days
            
            if days_diff == 0:
                # Aynы день, seri deгiшmez
                pass
            elif days_diff == 1:
                # Ertesi день, seri artar
                streak_data['current_streak'] += 1
            else:
                # 1 деньden fazla, seri сброситьnыr
                streak_data['current_streak'] = 1
        else:
            # Иlk aktivite
            streak_data['current_streak'] = 1
        
        # En uzun serхорошо обновить
        if streak_data['current_streak'] > streak_data['longest_streak']:
            streak_data['longest_streak'] = streak_data['current_streak']
        
        streak_data['last_activity'] = datetime.now().isoformat()
        
        self._save_streaks()
        
        return {
            'current_streak': streak_data['current_streak'],
            'longest_streak': streak_data['longest_streak']
        }
    
    def get_streak(self, user_id: str) -> Dict[str, Any]:
        """Получить серию"""
        if user_id not in self.streaks:
            return {
                'current_streak': 0,
                'longest_streak': 0
            }
        
        streak_data = self.streaks[user_id]
        
        # Serхорошо проверить et
        last_activity = streak_data.get('last_activity')
        if last_activity:
            last_date = datetime.fromisoformat(last_activity).date()
            today = datetime.now().date()
            days_diff = (today - last_date).days
            
            if days_diff > 1:
                # Seri bozulmuш
                return {
                    'current_streak': 0,
                    'longest_streak': streak_data['longest_streak']
                }
        
        return {
            'current_streak': streak_data['current_streak'],
            'longest_streak': streak_data['longest_streak']
        }


# Global instances
badge_system = BadgeSystem()
points_system = PointsSystem()
level_system = LevelSystem(points_system)
leaderboard_system = Leaderboard(points_system, badge_system)
streak_system = StreakTracker()
