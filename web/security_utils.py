"""Утилиты безопасности и производительности"""
from functools import wraps
from flask import session, jsonify, request
import re
import time
from collections import defaultdict
import hashlib
import json
import os
from datetime import datetime


# ── PERMISSION VALIDATION ───────────────────────────────────────────────────
def require_permission(permission):
    """Декоратор для проверки прав доступа"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user_role = session.get('role')
            
            # Определение прав по ролям
            permissions_map = {
                'owner': ['*'],  # Все права
                'админ': [
                    'ticket.view', 'ticket.create', 'ticket.close', 'ticket.delete',
                    'ticket.assign', 'ticket.priority',
                    'user.view', 'user.ban', 'user.warn',
                    'settings.view', 'settings.edit',
                    'moderation.*',
                    'analytics.view'
                ],
                'moderator': [
                    'ticket.view', 'ticket.create', 'ticket.close',
                    'ticket.assign',
                    'user.view', 'user.warn',
                    'analytics.view'
                ],
                'support': [
                    'ticket.view', 'ticket.create', 'ticket.close',
                    'user.view'
                ]
            }
            
            user_permissions = permissions_map.get(user_role, [])
            
            # Проверка прав
            if '*' in user_permissions:
                return f(*args, **kwargs)
            
            # Проверка wildcard прав (например, 'moderation.*')
            for perm in user_permissions:
                if perm.endswith('.*'):
                    if permission.startswith(perm[:-1]):
                        return f(*args, **kwargs)
            
            if permission in user_permissions:
                return f(*args, **kwargs)
            
            return jsonify({'success': False, 'error': 'Недостаточно прав'}), 403
        
        return decorated_function
    return decorator


# ── INPUT SANITIZATION ──────────────────────────────────────────────────────
def sanitize_input(text, max_length=1000):
    """Очистка пользовательского ввода"""
    if not text:
        return ''
    
    # Ограничение длины
    text = str(text)[:max_length]
    
    # Удаление потенциально опасных символов
    text = re.sub(r'[<>"\']', '', text)
    
    # Удаление управляющих символов
    text = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', text)
    
    # Удаление лишних пробелов
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text


def sanitize_html(text):
    """Очистка HTML (базовая защита от XSS)"""
    if not text:
        return ''
    
    # Экранирование HTML символов
    html_escape_table = {
        "&": "&amp;",
        '"': "&quot;",
        "'": "&#39;",
        ">": "&gt;",
        "<": "&lt;",
    }
    
    return "".join(html_escape_table.get(c, c) for c in str(text))


def validate_email(email):
    """Валидация email адреса"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def validate_discord_id(discord_id):
    """Валидация Discord ID"""
    pattern = r'^\d{17,19}$'
    return re.match(pattern, str(discord_id)) is not None


# ── AUDIT LOGGING ───────────────────────────────────────────────────────────
class AuditLogger:
    """Система аудита действий"""
    
    def __init__(self):
        self.log_file = 'data/audit_log.json'
        os.makedirs('data', exist_ok=True)
    
    def лог(self, user_id, username, action, details=None, ip_address=None):
        """Записать действие в аудит лог"""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'user_id': user_id,
            'username': username,
            'action': action,
            'details': details or {},
            'ip_address': ip_address or request.remote_addr
        }
        
        # Загрузить существующие логи
        logs = []
        if os.path.exists(self.log_file):
            try:
                with open(self.log_file, 'r', encoding='utf-8') as f:
                    logs = json.load(f)
            except Exception:
                logs = []
        
        # Добавить новую запись
        logs.append(log_entry)
        
        # Ограничить количество записей (последние 10000)
        logs = logs[-10000:]
        
        # Сохранить
        try:
            with open(self.log_file, 'w', encoding='utf-8') as f:
                json.dump(logs, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f'Ошибка записи аудит лога: {e}')
    
    def get_logs(self, limit=100, user_id=None, action=None):
        """Получить логи"""
        if not os.path.exists(self.log_file):
            return []
        
        try:
            with open(self.log_file, 'r', encoding='utf-8') as f:
                logs = json.load(f)
        except Exception:
            return []
        
        # Фильтрация
        if user_id:
            logs = [лог for лог in logs if log.get('user_id') == user_id]
        
        if action:
            logs = [лог for лог in logs if log.get('action') == action]
        
        # Сортировка по времени (новые первые)
        logs.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        return logs[:limit]


# Глобальный экземпляр
audit_logger = AuditLogger()


# ── CACHING SYSTEM ──────────────────────────────────────────────────────────
class SimpleCache:
    """Простая система кэширования в памяти"""
    
    def __init__(self):
        self.cache = {}
        self.ttl = {}
    
    def get(self, key):
        """Получить значение из кэша"""
        if key not in self.cache:
            return None
        
        # Проверка TTL
        if key in self.ttl and self.ttl[key] < time.time():
            del self.cache[key]
            del self.ttl[key]
            return None
        
        return self.cache[key]
    
    def set(self, key, value, ttl=300):
        """Установить значение в кэш"""
        self.cache[key] = value
        self.ttl[key] = time.time() + ttl
    
    def delete(self, key):
        """Удалить значение из кэша"""
        if key in self.cache:
            del self.cache[key]
        if key in self.ttl:
            del self.ttl[key]
    
    def clear(self):
        """Очистить весь кэш"""
        self.cache.clear()
        self.ttl.clear()
    
    def cleanup(self):
        """Удалить просроченные записи"""
        current_time = time.time()
        expired_keys = [k for k, v in self.ttl.items() if v < current_time]
        for key in expired_keys:
            self.delete(key)


# Глобальный экземпляр
cache = SimpleCache()


# ── RATE LIMITING ───────────────────────────────────────────────────────────
class RateLimiter:
    """Ограничение частоты запросов"""
    
    def __init__(self):
        self.requests = defaultdict(list)
    
    def is_allowed(self, key, max_requests=100, window=60):
        """Проверить, разрешён ли запрос"""
        current_time = time.time()
        
        # Удалить старые записи
        self.requests[key] = [t for t in self.requests[key] if current_time - t < window]
        
        # Проверить лимит
        if len(self.requests[key]) >= max_requests:
            return False
        
        # Добавить текущий запрос
        self.requests[key].append(current_time)
        return True
    
    def get_remaining(self, key, max_requests=100, window=60):
        """Получить количество оставшихся запросов"""
        current_time = time.time()
        self.requests[key] = [t for t in self.requests[key] if current_time - t < window]
        return max(0, max_requests - len(self.requests[key]))


# Глобальный экземпляр
rate_limiter = RateLimiter()


def rate_limit(max_requests=100, window=60):
    """Декоратор для ограничения частоты запросов"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Ключ на основе IP и endpoint
            key = f"{request.remote_addr}:{request.endpoint}"
            
            if not rate_limiter.is_allowed(key, max_requests, window):
                return jsonify({
                    'success': False,
                    'error': 'Слишком много запросов. Попробуйте позже.'
                }), 429
            
            return f(*args, **kwargs)
        
        return decorated_function
    return decorator


# ── SECURITY HEADERS ────────────────────────────────────────────────────────
def add_security_headers(response):
    """Добавить заголовки безопасности"""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    return response


# ── UTILITY FUNCTIONS ───────────────────────────────────────────────────────
def generate_hash(data):
    """Генерация хэша"""
    return hashlib.sha256(str(data).encode()).hexdigest()


def format_datetime(dt_string):
    """Форматирование даты и времени"""
    try:
        dt = datetime.fromisoformat(dt_string.replace('Z', '+00:00'))
        return dt.strftime('%d.%m.%Y %H:%M:%S')
    except Exception:
        return dt_string


def paginate(items, page=1, per_page=20):
    """Пагинация"""
    start = (page - 1) * per_page
    end = start + per_page
    
    return {
        'items': items[start:end],
        'total': len(items),
        'page': page,
        'per_page': per_page,
        'pages': (len(items) + per_page - 1) // per_page
    }
