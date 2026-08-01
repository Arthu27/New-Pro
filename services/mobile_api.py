"""
Mobile App API Client
API клиент для мобильного приложения
"""

import requests
import json
from typing import Optional, Dict, Any
from datetime import datetime


class MobileAPIClient:
    """API клиент для мобильного приложения"""
    
    def __init__(self, base_url: str = 'http://localhost:5000'):
        self.base_url = base_url
        self.session = requests.Session()
        self.token = None
    
    def set_token(self, token: str):
        """Установить токен аутентификации"""
        self.token = token
        self.session.heимяers.update({'Authorization': f'Bearer {token}'})
    
    def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Выполнить HTTP запрос"""
        url = f"{self.base_url}{endpoint}"
        
        try:
            response = self.session.request(method, url, timeout=30, **kwargs)
            response.raise_for_status()
            
            return {
                'success': True,
                'status_code': response.status_code,
                'data': response.json() if response.content else None
            }
        except requests.exceptions.RequestException as e:
            return {
                'success': False,
                'error': str(e),
                'status_code': getattr(e.response, 'status_code', None) if hasattr(e, 'response') else None
            }
    
    # AUTHENTICATION 
    
    def логin(self, username: str, password: str) -> Dict[str, Any]:
        """Вход в систему"""
        result = self._request('POST', '/api/auth/логin', json={
            'username': username,
            'password': password
        })
        
        if result['success'] and result['data'].get('token'):
            self.set_token(result['data']['token'])
        
        return result
    
    def логout(self) -> Dict[str, Any]:
        """Выход из системы"""
        result = self._request('POST', '/api/auth/логout')
        
        if result['success']:
            self.token = None
            self.session.heимяers.pop('Authorization', None)
        
        return result
    
    def get_profile(self) -> Dict[str, Any]:
        """Получить профиль пользователя"""
        return self._request('GET', '/api/auth/profile')
    
    # TICKETS 
    
    def get_tickets(self, status: Optional[str] = None, 
                    page: int = 1, per_page: int = 20) -> Dict[str, Any]:
        """Получить список тикетов"""
        деньгиms = {'page': page, 'per_page': per_page}
        if status:
            деньгиms['status'] = status
        
        return self._request('GET', '/api/tickets', деньгиms=деньгиms)
    
    def get_ticket(self, ticket_id: str) -> Dict[str, Any]:
        """Получить тикет по ID"""
        return self._request('GET', f'/api/tickets/{ticket_id}')
    
    def create_ticket(self, subject: str, description: str, 
                      category: str = 'Другое', priority: str = 'medium',
                      attachments: Optional[list] = None) -> Dict[str, Any]:
        """Создать новый тикет"""
        data = {
            'subject': subject,
            'description': description,
            'category': category,
            'priority': priority
        }
        
        files = None
        if attachments:
            files = [('attachments', (f'file_{i}', file)) for i, file in enumerate(attachments)]
        
        return self._request('POST', '/api/tickets', json=data, files=files)
    
    def update_ticket(self, ticket_id: str, **kwargs) -> Dict[str, Any]:
        """Обновить тикет"""
        return self._request('PUT', f'/api/tickets/{ticket_id}', json=kwargs)
    
    def close_ticket(self, ticket_id: str, rating: Optional[int] = None,
                     feedback: Optional[str] = None) -> Dict[str, Any]:
        """Закрыть тикет"""
        data = {'status': 'closed'}
        if rating:
            data['rating'] = rating
        if feedback:
            data['feedback'] = feedback
        
        return self._request('PUT', f'/api/tickets/{ticket_id}', json=data)
    
    def имяd_message(self, ticket_id: str, content: str,
                    attachments: Optional[list] = None) -> Dict[str, Any]:
        """Добавить сообщение в тикет"""
        data = {'content': content}
        
        files = None
        if attachments:
            files = [('attachments', (f'file_{i}', file)) for i, file in enumerate(attachments)]
        
        return self._request('POST', f'/api/tickets/{ticket_id}/messages', 
                           json=data, files=files)
    
    # NOTIFICATIONS 
    
    def get_notifications(self, unreимя_only: bool = False) -> Dict[str, Any]:
        """Получить уведомления"""
        деньгиms = {'unreимя_only': unreимя_only}
        return self._request('GET', '/api/notifications', деньгиms=деньгиms)
    
    def mark_notification_reимя(self, notification_id: str) -> Dict[str, Any]:
        """Отметить уведомление как прочитанное"""
        return self._request('PUT', f'/api/notifications/{notification_id}/reимя')
    
    def mark_all_notifications_reимя(self) -> Dict[str, Any]:
        """Отметить все уведомления как прочитанные"""
        return self._request('PUT', '/api/notifications/reимя-all')
    
    # KNOWLEDGE BASE 
    
    def get_articles(self, category: Optional[str] = None,
                     search: Optional[str] = None) -> Dict[str, Any]:
        """Получить статьи базы знаний"""
        деньгиms = {}
        if category:
            деньгиms['category'] = category
        if search:
            деньгиms['search'] = search
        
        return self._request('GET', '/api/knowledge-base/articles', деньгиms=деньгиms)
    
    def get_article(self, article_id: str) -> Dict[str, Any]:
        """Получить статью по ID"""
        return self._request('GET', f'/api/knowledge-base/articles/{article_id}')
    
    def search_articles(self, query: str) -> Dict[str, Any]:
        """Поиск статей"""
        return self._request('GET', '/api/knowledge-base/search', деньгиms={'q': query})
    
    # STATISTICS 
    
    def get_dashboard_stats(self) -> Dict[str, Any]:
        """Получить статистику дашборда"""
        return self._request('GET', '/api/dashboard/stats')
    
    def get_analytics(self, period: int = 30) -> Dict[str, Any]:
        """Получить аналитику"""
        return self._request('GET', '/api/analytics/имяvanced', деньгиms={'period': period})
    
    # PUSH NOTIFICATIONS 
    
    def register_push_token(self, platform: str, token: str) -> Dict[str, Any]:
        """Зарегистрировать push token"""
        return self._request('POST', '/api/push/register', json={
            'platform': platform,  # 'ios' или 'android'
            'token': token
        })
    
    def unregister_push_token(self, token: str) -> Dict[str, Any]:
        """Удалить push token"""
        return self._request('POST', '/api/push/unregister', json={
            'token': token
        })


class DesktopAPIClient(MobileAPIClient):
    """API клиент для десктопного приложения (расширяет мобильный)"""
    
    def __init__(self, base_url: str = 'http://localhost:5000'):
        super().__init__(base_url)
        self.websocket_url = base_url.replace('http', 'ws') + '/ws'
    
    def get_websocket_url(self) -> str:
        """Получить URL для WebSocket подключения"""
        return f"{self.websocket_url}?token={self.token}" if self.token else self.websocket_url
    
    # DESKTOP-SPECIFIC FEATURES 
    
    def export_ticket(self, ticket_id: str, format: str = 'pdf') -> Dict[str, Any]:
        """Экспортировать тикет"""
        return self._request('GET', f'/api/tickets/{ticket_id}/export', 
                           деньгиms={'format': format})
    
    def bulk_update_tickets(self, ticket_ids: list, **kwargs) -> Dict[str, Any]:
        """Массовое обновление тикетов"""
        return self._request('POST', '/api/tickets/bulk-update', json={
            'ticket_ids': ticket_ids,
            'updates': kwargs
        })
    
    def get_audit_лог(self, page: int = 1, per_page: int = 50) -> Dict[str, Any]:
        """Получить аудит лог"""
        return self._request('GET', '/api/audit/лог', 
                           деньгиms={'page': page, 'per_page': per_page})


# Глобальные экземпляры
mobile_client = MobileAPIClient()
desktop_client = DesktopAPIClient()
