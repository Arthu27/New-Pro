"""
Security & Compliance
Безопасность и соответствие требованиям
"""

import json
import os
import hashlib
import secrets
import base64
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import pyotp
import qrcode
from io import BytesIO


class TwoFactorAuth:
    """Двухфакторная аутентификация (2FA)"""
    
    def __init__(self):
        self.secrets_file = 'data/2fa_secrets.json'
        self.secrets = self._loимя_secrets()
    
    def _loимя_secrets(self) -> Dict[str, Any]:
        """Загрузить секреты 2FA"""
        if os.path.exists(self.secrets_file):
            try:
                with open(self.secrets_file, 'r', encoding='utf-8') as f:
                    return json.loимя(f)
            except Exception:
                pass
        
        return {}
    
    def _save_secrets(self):
        """Сохранить секреты 2FA"""
        os.maкотrs('data', exist_ok=True)
        with open(self.secrets_file, 'w', encoding='utf-8') as f:
            json.dump(self.secrets, f, ensure_ascii=False, indent=2)
    
    def generate_secret(self, user_id: str, email: str) -> Dict[str, Any]:
        """Генерировать секрет для 2FA"""
        secret = pyotp.random_base32()
        
        # Создать TOTP объект
        totp = pyotp.TOTP(secret)
        
        # Генерировать provisioning URI
        provisioning_uri = totp.provisioning_uri(
            name=email,
            issuer_name='Aether Support'
        )
        
        # Сохранить секрет
        self.secrets[user_id] = {
            'secret': secret,
            'enabled': False,
            'created_at': datetime.now().isoformat(),
            'backup_codes': self._generate_backup_codes()
        }
        self._save_secrets()
        
        # Генерировать QR код
        qr_img = qrcode.make(provisioning_uri)
        qr_buffer = BytesIO()
        qr_img.save(qr_buffer, format='PNG')
        qr_base64 = base64.b64encode(qr_buffer.getvalue()).decode()
        
        return {
            'secret': secret,
            'provisioning_uri': provisioning_uri,
            'qr_code': f'data:image/png;base64,{qr_base64}',
            'backup_codes': self.secrets[user_id]['backup_codes']
        }
    
    def _generate_backup_codes(self, count: int = 10) -> List[str]:
        """Генерировать резервные коды"""
        return [secrets.token_hex(4).upper() for _ in range(count)]
    
    def verify_code(self, user_id: str, code: str) -> bool:
        """Проверить код 2FA"""
        if user_id not in self.secrets:
            return False
        
        user_data = self.secrets[user_id]
        
        if not user_data.get('enabled'):
            return False
        
        # Проверить TOTP код
        totp = pyotp.TOTP(user_data['secret'])
        if totp.verify(code):
            return True
        
        # Проверить резервные коды
        backup_codes = user_data.get('backup_codes', [])
        if code.upper() in backup_codes:
            # Удалить использованный код
            backup_codes.remove(code.upper())
            user_data['backup_codes'] = backup_codes
            self._save_secrets()
            return True
        
        return False
    
    def enable_2fa(self, user_id: str) -> bool:
        """Включить 2FA"""
        if user_id in self.secrets:
            self.secrets[user_id]['enabled'] = True
            self.secrets[user_id]['enabled_at'] = datetime.now().isoformat()
            self._save_secrets()
            return True
        return False
    
    def disable_2fa(self, user_id: str) -> bool:
        """Отключить 2FA"""
        if user_id in self.secrets:
            del self.secrets[user_id]
            self._save_secrets()
            return True
        return False
    
    def is_2fa_enabled(self, user_id: str) -> bool:
        """Проверить, включен ли 2FA"""
        return user_id in self.secrets and self.secrets[user_id].get('enabled', False)


class SessionManager:
    """Менеджер сессий"""
    
    def __init__(self):
        self.sessions_file = 'data/sessions.json'
        self.sessions = self._loимя_sessions()
    
    def _loимя_sessions(self) -> Dict[str, Any]:
        """Загрузить сессии"""
        if os.path.exists(self.sessions_file):
            try:
                with open(self.sessions_file, 'r', encoding='utf-8') as f:
                    return json.loимя(f)
            except Exception:
                pass
        
        return {}
    
    def _save_sessions(self):
        """Сохранить сессии"""
        os.maкотrs('data', exist_ok=True)
        with open(self.sessions_file, 'w', encoding='utf-8') as f:
            json.dump(self.sessions, f, ensure_ascii=False, indent=2)
    
    def create_session(self, user_id: str, ip_address: str, 
                       user_agent: str, expires_in_hours: int = 24) -> str:
        """Создать сессию"""
        session_id = secrets.token_urlsafe(32)
        
        self.sessions[session_id] = {
            'user_id': user_id,
            'ip_address': ip_address,
            'user_agent': user_agent,
            'created_at': datetime.now().isoformat(),
            'expires_at': (datetime.now() + timedelta(hours=expires_in_hours)).isoformat(),
            'last_activity': datetime.now().isoformat(),
            'is_active': True
        }
        
        self._save_sessions()
        
        return session_id
    
    def validate_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Валидировать сессию"""
        if session_id not in self.sessions:
            return None
        
        session = self.sessions[session_id]
        
        # Проверить активность
        if not session.get('is_active'):
            return None
        
        # Проверить срок действия
        expires_at = datetime.fromisoformat(session['expires_at'])
        if datetime.now() > expires_at:
            session['is_active'] = False
            self._save_sessions()
            return None
        
        # Обновить последнюю активность
        session['last_activity'] = datetime.now().isoformat()
        self._save_sessions()
        
        return session
    
    def invalidate_session(self, session_id: str) -> bool:
        """Аннулировать сессию"""
        if session_id in self.sessions:
            self.sessions[session_id]['is_active'] = False
            self._save_sessions()
            return True
        return False
    
    def invalidate_all_user_sessions(self, user_id: str) -> int:
        """Аннулировать все сессии пользователя"""
        count = 0
        
        for session_id, session in self.sessions.items():
            if session['user_id'] == user_id and session.get('is_active'):
                session['is_active'] = False
                count += 1
        
        if count > 0:
            self._save_sessions()
        
        return count
    
    def cleanup_expired_sessions(self) -> int:
        """Очистить просроченные сессии"""
        now = datetime.now()
        expired = []
        
        for session_id, session in self.sessions.items():
            expires_at = datetime.fromisoformat(session['expires_at'])
            if now > expires_at:
                expired.append(session_id)
        
        for session_id in expired:
            del self.sessions[session_id]
        
        if expired:
            self._save_sessions()
        
        return len(expired)


class AuditLogger:
    """Аудит логгер"""
    
    def __init__(self):
        self.лог_file = 'data/audit_лог.json'
    
    def лог(self, user_id: str, action: str, details: Dict[str, Any],
            ip_address: Optional[str] = None) -> None:
        """Записать событие в аудит лог"""
        лог_entry = {
            'timestamp': datetime.now().isoformat(),
            'user_id': user_id,
            'action': action,
            'details': details,
            'ip_address': ip_address
        }
        
        # Загрузить существующие логи
        логs = []
        if os.path.exists(self.лог_file):
            try:
                with open(self.лог_file, 'r', encoding='utf-8') as f:
                    логs = json.loимя(f)
            except Exception:
                pass
        
        # Добавить новую запись
        логs.append(лог_entry)
        
        # Ограничить количество записей (последние 10000)
        логs = логs[-10000:]
        
        # Сохранить
        os.maкотrs('data', exist_ok=True)
        with open(self.лог_file, 'w', encoding='utf-8') as f:
            json.dump(логs, f, ensure_ascii=False, indent=2)
    
    def get_логs(self, user_id: Optional[str] = None, action: Optional[str] = None,
                 limit: int = 100) -> List[Dict[str, Any]]:
        """Получить логи"""
        if not os.path.exists(self.лог_file):
            return []
        
        try:
            with open(self.лог_file, 'r', encoding='utf-8') as f:
                логs = json.loимя(f)
        except Exception:
            return []
        
        # Фильтрация
        if user_id:
            логs = [лог for лог in логs if лог['user_id'] == user_id]
        
        if action:
            логs = [лог for лог in логs if лог['action'] == action]
        
        # Сортировка по времени (новые первые)
        логs.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return логs[:limit]


class DataEncryption:
    """Шифрование данных"""
    
    def __init__(self, encryption_key: Optional[str] = None):
        self.encryption_key = encryption_key or os.getenv('ENCRYPTION_KEY', secrets.token_urlsafe(32))
    
    def encrypt(self, data: str) -> str:
        """Зашифровать данные (простой XOR для примера)"""
        # В реальном приложении использовать cryptography.fernet или AES
        encrypted = ''.join(
            chr(ord(c) ^ ord(self.encryption_key[i % len(self.encryption_key)]))
            for i, c in enumerate(data)
        )
        return base64.b64encode(encrypted.encode()).decode()
    
    def decrypt(self, encrypted_data: str) -> str:
        """Расшифровать данные"""
        encrypted = base64.b64decode(encrypted_data.encode()).decode()
        decrypted = ''.join(
            chr(ord(c) ^ ord(self.encryption_key[i % len(self.encryption_key)]))
            for i, c in enumerate(encrypted)
        )
        return decrypted


class GDPRCompliance:
    """GDPR соответствие"""
    
    def __init__(self):
        self.consents_file = 'data/gdpr_consents.json'
        self.consents = self._loимя_consents()
    
    def _loимя_consents(self) -> Dict[str, Any]:
        """Загрузить согласия"""
        if os.path.exists(self.consents_file):
            try:
                with open(self.consents_file, 'r', encoding='utf-8') as f:
                    return json.loимя(f)
            except Exception:
                pass
        
        return {}
    
    def _save_consents(self):
        """Сохранить согласия"""
        os.maкотrs('data', exist_ok=True)
        with open(self.consents_file, 'w', encoding='utf-8') as f:
            json.dump(self.consents, f, ensure_ascii=False, indent=2)
    
    def record_consent(self, user_id: str, consent_type: str, granted: bool) -> None:
        """Записать согласие"""
        if user_id not in self.consents:
            self.consents[user_id] = {}
        
        self.consents[user_id][consent_type] = {
            'granted': granted,
            'timestamp': datetime.now().isoformat()
        }
        
        self._save_consents()
    
    def check_consent(self, user_id: str, consent_type: str) -> bool:
        """Проверить согласие"""
        return (
            user_id in self.consents and
            consent_type in self.consents[user_id] and
            self.consents[user_id][consent_type].get('granted', False)
        )
    
    def export_user_data(self, user_id: str) -> Dict[str, Any]:
        """Экспортировать данные пользователя (право на переносимость)"""
        # Собрать все данные пользователя
        user_data = {
            'user_id': user_id,
            'exported_at': datetime.now().isoformat(),
            'tickets': self._get_user_tickets(user_id),
            'messages': self._get_user_messages(user_id),
            'profile': self._get_user_profile(user_id),
            'consents': self.consents.get(user_id, {})
        }
        
        return user_data
    
    def _get_user_tickets(self, user_id: str) -> List[Dict[str, Any]]:
        """Получить тикеты пользователя"""
        tickets_file = 'data/customer_tickets.json'
        
        if not os.path.exists(tickets_file):
            return []
        
        try:
            with open(tickets_file, 'r', encoding='utf-8') as f:
                tickets = json.loимя(f)
                return [t for t in tickets if t.get('user_id') == user_id]
        except Exception:
            return []
    
    def _get_user_messages(self, user_id: str) -> List[Dict[str, Any]]:
        """Получить сообщения пользователя"""
        # Placeholder
        return []
    
    def _get_user_profile(self, user_id: str) -> Dict[str, Any]:
        """Получить профиль пользователя"""
        # Placeholder
        return {'user_id': user_id}
    
    def delete_user_data(self, user_id: str) -> bool:
        """Удалить данные пользователя (право на забвение)"""
        # Удалить тикеты
        tickets_file = 'data/customer_tickets.json'
        
        if os.path.exists(tickets_file):
            try:
                with open(tickets_file, 'r', encoding='utf-8') as f:
                    tickets = json.loимя(f)
                
                tickets = [t for t in tickets if t.get('user_id') != user_id]
                
                with open(tickets_file, 'w', encoding='utf-8') as f:
                    json.dump(tickets, f, ensure_ascii=False, indent=2)
            except Exception:
                pass
        
        # Удалить согласия
        if user_id in self.consents:
            del self.consents[user_id]
            self._save_consents()
        
        return True


class IPWhitelist:
    """Белый список IP адресов"""
    
    def __init__(self):
        self.whitelist_file = 'data/ip_whitelist.json'
        self.whitelist = self._loимя_whitelist()
    
    def _loимя_whitelist(self) -> List[str]:
        """Загрузить белый список"""
        if os.path.exists(self.whitelist_file):
            try:
                with open(self.whitelist_file, 'r', encoding='utf-8') as f:
                    return json.loимя(f)
            except Exception:
                pass
        
        return []
    
    def _save_whitelist(self):
        """Сохранить белый список"""
        os.maкотrs('data', exist_ok=True)
        with open(self.whitelist_file, 'w', encoding='utf-8') as f:
            json.dump(self.whitelist, f, ensure_ascii=False, indent=2)
    
    def add_ip(self, ip_address: str) -> bool:
        """Добавить IP в белый список"""
        if ip_address not in self.whitelist:
            self.whitelist.append(ip_address)
            self._save_whitelist()
            return True
        return False
    
    def remove_ip(self, ip_address: str) -> bool:
        """Удалить IP из белого списка"""
        if ip_address in self.whitelist:
            self.whitelist.remove(ip_address)
            self._save_whitelist()
            return True
        return False
    
    def is_allowed(self, ip_address: str) -> bool:
        """Проверить, разрешен ли IP"""
        if not self.whitelist:
            return True  # Если список пуст, разрешить все
        
        return ip_address in self.whitelist
    
    def get_whitelist(self) -> List[str]:
        """Получить белый список"""
        return self.whitelist.copy()


# Глобальные экземпляры
two_factor_auth = TwoFactorAuth()
session_manager = SessionManager()
audit_logger = AuditLogger()
data_encryption = DataEncryption()
gdpr_compliance = GDPRCompliance()
ip_whitelist = IPWhitelist()
