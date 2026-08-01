"""
Developer Tools
Инструменты для разработчиков
"""

import json
import os
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import requests


class APIKeyManager:
    """Менеджер API ключей"""
    
    def __init__(self):
        self.keys_file = 'data/api_keys.json'
        self.keys = self._load_keys()
    
    def _load_keys(self) -> Dict[str, Any]:
        """Загрузить API ключи"""
        if os.path.exists(self.keys_file):
            try:
                with open(self.keys_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        
        return {}
    
    def _save_keys(self):
        """Сохранить API ключи"""
        os.makedirs('data', exist_ok=True)
        with open(self.keys_file, 'w', encoding='utf-8') as f:
            json.dump(self.keys, f, ensure_ascii=False, indent=2)
    
    def create_api_key(self, name: str, permissions: List[str], 
                       expires_in_days: Optional[int] = None) -> Dict[str, Any]:
        """Создать API ключ"""
        api_key = secrets.token_urlsafe(32)
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        
        expires_at = None
        if expires_in_days:
            expires_at = (datetime.now() + timedelta(days=expires_in_days)).isoformat()
        
        key_data = {
            'name': name,
            'hash': key_hash,
            'permissions': permissions,
            'created_at': datetime.now().isoformat(),
            'expires_at': expires_at,
            'last_used': None,
            'usage_count': 0
        }
        
        self.keys[key_hash] = key_data
        self._save_keys()
        
        return {
            'api_key': api_key,
            'name': name,
            'permissions': permissions,
            'expires_at': expires_at
        }
    
    def validate_api_key(self, api_key: str, required_permission: Optional[str] = None) -> bool:
        """Валидировать API ключ"""
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        
        if key_hash not in self.keys:
            return False
        
        key_data = self.keys[key_hash]
        
        # Проверить срок действия
        if key_data.get('expires_at'):
            expires_at = datetime.fromisoformat(key_data['expires_at'])
            if datetime.now() > expires_at:
                return False
        
        # Проверить права доступа
        if required_permission and required_permission not in key_data.get('permissions', []):
            return False
        
        # Обновить статистику использования
        key_data['last_used'] = datetime.now().isoformat()
        key_data['usage_count'] += 1
        self._save_keys()
        
        return True
    
    def revoke_api_key(self, key_hash: str) -> bool:
        """Отозвать API ключ"""
        if key_hash in self.keys:
            del self.keys[key_hash]
            self._save_keys()
            return True
        return False
    
    def list_api_keys(self) -> List[Dict[str, Any]]:
        """Получить список API ключей"""
        return [
            {
                'hash': key_hash,
                'name': key_data['name'],
                'permissions': key_data['permissions'],
                'created_at': key_data['created_at'],
                'expires_at': key_data.get('expires_at'),
                'last_used': key_data.get('last_used'),
                'usage_count': key_data['usage_count']
            }
            for key_hash, key_data in self.keys.items()
        ]


class WebhookManager:
    """Менеджер вебхуков"""
    
    def __init__(self):
        self.webhooks_file = 'data/webhooks.json'
        self.webhooks = self._load_webhooks()
    
    def _load_webhooks(self) -> Dict[str, Any]:
        """Загрузить вебхуки"""
        if os.path.exists(self.webhooks_file):
            try:
                with open(self.webhooks_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        
        return {}
    
    def _save_webhooks(self):
        """Сохранить вебхуки"""
        os.makedirs('data', exist_ok=True)
        with open(self.webhooks_file, 'w', encoding='utf-8') as f:
            json.dump(self.webhooks, f, ensure_ascii=False, indent=2)
    
    def create_webhook(self, name: str, url: str, events: List[str],
                       secret: Optional[str] = None) -> Dict[str, Any]:
        """Создать вебхук"""
        webhook_id = secrets.token_urlsafe(16)
        
        if not secret:
            secret = secrets.token_urlsafe(32)
        
        webhook_data = {
            'name': name,
            'url': url,
            'events': events,
            'secret': secret,
            'created_at': datetime.now().isoformat(),
            'enabled': True,
            'last_triggered': None,
            'trigger_count': 0,
            'error_count': 0
        }
        
        self.webhooks[webhook_id] = webhook_data
        self._save_webhooks()
        
        return {
            'webhook_id': webhook_id,
            'name': name,
            'url': url,
            'events': events,
            'secret': secret
        }
    
    def trigger_webhook(self, webhook_id: str, event: str, payload: dict) -> bool:
        """Запустить вебхук"""
        if webhook_id not in self.webhooks:
            return False
        
        webhook = self.webhooks[webhook_id]
        
        if not webhook.get('enabled'):
            return False
        
        if event not in webhook.get('events', []):
            return False
        
        # Подготовить данные
        data = {
            'event': event,
            'timestamp': datetime.now().isoformat(),
            'payload': payload
        }
        
        # Подписать запрос
        signature = self._sign_payload(data, webhook['secret'])
        
        headers = {
            'Content-Type': 'application/json',
            'X-Webhook-Signature': signature
        }
        
        try:
            response = requests.post(
                webhook['url'],
                json=data,
                headers=headers,
                timeout=10
            )
            
            webhook['last_triggered'] = datetime.now().isoformat()
            webhook['trigger_count'] += 1
            
            if response.status_code >= 400:
                webhook['error_count'] += 1
            
            self._save_webhooks()
            
            return response.status_code < 400
        except Exception:
            webhook['error_count'] += 1
            self._save_webhooks()
            return False
    
    def _sign_payload(self, payload: dict, secret: str) -> str:
        """Подписать payload"""
        payload_str = json.dumps(payload, sort_keys=True)
        signature = hashlib.sha256(f"{payload_str}{secret}".encode()).hexdigest()
        return signature
    
    def delete_webhook(self, webhook_id: str) -> bool:
        """Удалить вебхук"""
        if webhook_id in self.webhooks:
            del self.webhooks[webhook_id]
            self._save_webhooks()
            return True
        return False
    
    def list_webhooks(self) -> List[Dict[str, Any]]:
        """Получить список вебхуков"""
        return [
            {
                'webhook_id': webhook_id,
                'name': webhook['name'],
                'url': webhook['url'],
                'events': webhook['events'],
                'enabled': webhook['enabled'],
                'created_at': webhook['created_at'],
                'last_triggered': webhook.get('last_triggered'),
                'trigger_count': webhook['trigger_count'],
                'error_count': webhook['error_count']
            }
            for webhook_id, webhook in self.webhooks.items()
        ]
    
    def enable_webhook(self, webhook_id: str) -> bool:
        """Включить вебхук"""
        if webhook_id in self.webhooks:
            self.webhooks[webhook_id]['enabled'] = True
            self._save_webhooks()
            return True
        return False
    
    def disable_webhook(self, webhook_id: str) -> bool:
        """Отключить вебхук"""
        if webhook_id in self.webhooks:
            self.webhooks[webhook_id]['enabled'] = False
            self._save_webhooks()
            return True
        return False


class APIDocumentation:
    """Генератор API документации"""
    
    def __init__(self):
        self.endpoints = []
    
    def add_endpoint(self, method: str, path: str, description: str,
                     parameters: List[Dict[str, Any]], response: Dict[str, Any]):
        """Добавить endpoint"""
        self.endpoints.append({
            'method': method,
            'path': path,
            'description': description,
            'parameters': parameters,
            'response': response
        })
    
    def generate_openapi(self, title: str = 'Aether API', version: str = '1.0.0') -> dict:
        """Генерировать OpenAPI спецификацию"""
        paths = {}
        
        for endpoint in self.endpoints:
            path = endpoint['path']
            
            if path not in paths:
                paths[path] = {}
            
            method = endpoint['method'].lower()
            
            paths[path][method] = {
                'summary': endpoint['description'],
                'parameters': endpoint['parameters'],
                'responses': {
                    '200': {
                        'description': 'Success',
                        'content': {
                            'application/json': {
                                'schema': endpoint['response']
                            }
                        }
                    }
                }
            }
        
        return {
            'openapi': '3.0.0',
            'info': {
                'title': title,
                'version': version
            },
            'paths': paths
        }
    
    def generate_markdown(self) -> str:
        """Генерировать Markdown документацию"""
        lines = ['# API Documentation\n']
        
        for endpoint in self.endpoints:
            lines.append(f"## {endpoint['method']} {endpoint['path']}\n")
            lines.append(f"{endpoint['description']}\n")
            
            if endpoint['parameters']:
                lines.append('### Parameters\n')
                for param in endpoint['parameters']:
                    lines.append(f"- **{param['name']}** ({param['type']}): {param['description']}")
                lines.append('')
            
            lines.append('### Response\n')
            lines.append('```json')
            lines.append(json.dumps(endpoint['response'], indent=2))
            lines.append('```\n')
        
        return '\n'.join(lines)


class SDKGenerator:
    """Генератор SDK"""
    
    def generate_python_sdk(self, api_base_url: str) -> str:
        """Генерировать Python SDK"""
        return f'''"""
Aether API Python SDK
"""

import requests
from typing import Dict, Any, Optional


class AetherAPI:
 """Aether API клиент"""
 
 def __init__(self, api_key: str, base_url: str = '{api_base_url}'):
 self.api_key = api_key
 self.base_url = base_url
 self.session = requests.Session()
 self.session.headers.update({{'Authorization': f'Bearer {{api_key}}'}})
 
 def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
 """Выполнить HTTP запрос"""
 url = f"{{self.base_url}}{{endpoint}}"
 response = self.session.request(method, url, **kwargs)
 response.raise_for_status()
 return response.json()
 
 def get_tickets(self, status: Optional[str] = None) -> Dict[str, Any]:
 """Получить список тикетов"""
 params = {{}}
 if status:
 params['status'] = status
 return self._request('GET', '/api/tickets', params=params)
 
 def get_ticket(self, ticket_id: str) -> Dict[str, Any]:
 """Получить тикет по ID"""
 return self._request('GET', f'/api/tickets/{{ticket_id}}')
 
 def create_ticket(self, subject: str, description: str, **kwargs) -> Dict[str, Any]:
 """Создать новый тикет"""
 data = {{
 'subject': subject,
 'description': description,
 **kwargs
 }}
 return self._request('POST', '/api/tickets', json=data)
 
 def update_ticket(self, ticket_id: str, **kwargs) -> Dict[str, Any]:
 """Обновить тикет"""
 return self._request('PUT', f'/api/tickets/{{ticket_id}}', json=kwargs)
 
 def close_ticket(self, ticket_id: str, rating: Optional[int] = None) -> Dict[str, Any]:
 """Закрыть тикет"""
 data = {{'status': 'closed'}}
 if rating:
 data['rating'] = rating
 return self._request('PUT', f'/api/tickets/{{ticket_id}}', json=data)
''' 
    def generate_javascript_sdk(self, api_base_url: str) -> str:
        """Генерировать JavaScript SDK"""
        return f'''/**
 * Aether API JavaScript SDK
 */

class AetherAPI {{
 constructor(apiKey, baseUrl = '{api_base_url}') {{
 this.apiKey = apiKey;
 this.baseUrl = baseUrl;
 }}
 
 async _request(method, endpoint, options = {{}}) {{
 const url = `${{this.baseUrl}}${{endpoint}}`;
 const response = await fetch(url, {{
 method,
 headers: {{
 'Authorization': `Bearer ${{this.apiKey}}`,
 'Content-Type': 'application/json',
 ...options.headers
 }},
 ...options
 }});
 
 if (!response.ok) {{
 throw new Error(`HTTP error! status: ${{response.status}}`);
 }}
 
 return response.json();
 }}
 
 async getTickets(status = null) {{
 const params = status ? `?status=${{status}}` : '';
 return this._request('GET', `/api/tickets${{params}}`);
 }}
 
 async getTicket(ticketId) {{
 return this._request('GET', `/api/tickets/${{ticketId}}`);
 }}
 
 async createTicket(subject, description, options = {{}}) {{
 return this._request('POST', '/api/tickets', {{
 body: JSON.stringify({{ subject, description, ...options }})
 }});
 }}
 
 async updateTicket(ticketId, data) {{
 return this._request('PUT', `/api/tickets/${{ticketId}}`, {{
 body: JSON.stringify(data)
 }});
 }}
 
 async closeTicket(ticketId, rating = null) {{
 const data = {{ status: 'closed' }};
 if (rating) data.rating = rating;
 return this._request('PUT', `/api/tickets/${{ticketId}}`, {{
 body: JSON.stringify(data)
 }});
 }}
}}

module.exports = AetherAPI;
'''

# Глобальные экземпляры
api_key_manager = APIKeyManager()
webhook_manager = WebhookManager()
api_documentation = APIDocumentation()
sdk_generator = SDKGenerator()
