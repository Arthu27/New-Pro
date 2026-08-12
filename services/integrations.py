"""
Интеграции с внешними сервисами
Jira, Slack, Telegram, Payment (Stripe/PayPal)
"""

from logger import get_logger

_log = get_logger("integrations")

import json
import os
import requests
from datetime import datetime
from typing import Optional, Dict, Any


class IntegrationManager:
    """Менеджер интеграций с внешними сервисами"""
    
    def __init__(self):
        self.config_file = 'data/integrations_config.json'
        self.config = self._load_config()
    
    def _load_config(self) -> dict:
        """Загрузить конфигурацию интеграций"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as _ex:
                _log.debug("_load_config(): подавлено: %s", _ex)
        
        return {
            'jira': {'enabled': False, 'url': '', 'username': '', 'api_token': ''},
            'slack': {'enabled': False, 'webhook_url': '', 'bot_token': ''},
            'telegram': {'enabled': False, 'bot_token': '', 'chat_id': ''},
            'stripe': {'enabled': False, 'api_key': '', 'webhook_secret': ''},
            'paypal': {'enabled': False, 'client_id': '', 'client_secret': '', 'sandbox': True}
        }
    
    def _save_config(self):
        """Сохранить конфигурацию интеграций"""
        os.makedirs('data', exist_ok=True)
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)
    
    # JIRA INTEGRATION 
    
    def jira_create_issue(self, summary: str, description: str, 
                          issue_type: str = 'Task', priority: str = 'Medium') -> Dict[str, Any]:
        """Создать issue в Jira"""
        if not self.config['jira']['enabled']:
            return {'success': False, 'error': 'Jira integration is disabled'}
        
        url = f"{self.config['jira']['url']}/rest/api/2/issue"
        auth = (self.config['jira']['username'], self.config['jira']['api_token'])
        
        payload = {
            "fields": {
                "summary": summary,
                "description": description,
                "issuetype": {"name": issue_type},
                "priority": {"name": priority}
            }
        }
        
        try:
            response = requests.post(url, json=payload, auth=auth, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            return {
                'success': True,
                'issue_key': data.get('key'),
                'issue_url': f"{self.config['jira']['url']}/browse/{data.get('key')}"
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def jira_add_comment(self, issue_key: str, comment: str) -> Dict[str, Any]:
        """Добавить комментарий к issue в Jira"""
        if not self.config['jira']['enabled']:
            return {'success': False, 'error': 'Jira integration is disabled'}
        
        url = f"{self.config['jira']['url']}/rest/api/2/issue/{issue_key}/comment"
        auth = (self.config['jira']['username'], self.config['jira']['api_token'])
        
        payload = {"body": comment}
        
        try:
            response = requests.post(url, json=payload, auth=auth, timeout=10)
            response.raise_for_status()
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # SLACK INTEGRATION 
    
    def slack_send_message(self, channel: str, text: str, 
                           attachments: Optional[list] = None) -> Dict[str, Any]:
        """Отправить сообщение в Slack"""
        if not self.config['slack']['enabled']:
            return {'success': False, 'error': 'Slack integration is disabled'}
        
        # Использовать webhook если доступен
        if self.config['slack']['webhook_url']:
            payload = {
                'channel': channel,
                'text': text,
                'attachments': attachments or []
            }
            
            try:
                response = requests.post(
                    self.config['slack']['webhook_url'],
                    json=payload,
                    timeout=10
                )
                response.raise_for_status()
                return {'success': True}
            except Exception as e:
                return {'success': False, 'error': str(e)}
        
        # Использовать Bot Token
        if self.config['slack']['bot_token']:
            url = 'https://slack.com/api/chat.postMessage'
            headers = {
                'Authorization': f"Bearer {self.config['slack']['bot_token']}",
                'Content-Type': 'application/json'
            }
            
            payload = {
                'channel': channel,
                'text': text,
                'attachments': attachments or []
            }
            
            try:
                response = requests.post(url, json=payload, headers=headers, timeout=10)
                response.raise_for_status()
                data = response.json()
                
                if data.get('ok'):
                    return {'success': True, 'message_ts': data.get('ts')}
                else:
                    return {'success': False, 'error': data.get('error')}
            except Exception as e:
                return {'success': False, 'error': str(e)}
        
        return {'success': False, 'error': 'No webhook URL or bot token configured'}
    
    def slack_create_ticket_notification(self, ticket: dict) -> Dict[str, Any]:
        """Создать уведомление о новом тикете в Slack"""
        priority_colors = {
            'low': '#2ecc71',
            'medium': '#f1c40f',
            'high': '#e74c3c'
        }
        
        priority_names = {
            'low': 'Низкий',
            'medium': 'Средний',
            'high': 'Высокий'
        }
        
        attachments = [{
            'color': priority_colors.get(ticket.get('priority', 'medium'), '#5865f2'),
            'title': f"Новый тикет #{ticket.get('id')}",
            'text': ticket.get('subject', 'Без темы'),
            'fields': [
                {'title': 'Категория', 'value': ticket.get('category', 'Другое'), 'short': True},
                {'title': 'Приоритет', 'value': priority_names.get(ticket.get('priority', 'medium'), 'Средний'), 'short': True},
                {'title': 'Пользователь', 'value': ticket.get('user_name', 'Неизвестный'), 'short': True}
            ],
            'footer': 'Aether Support System',
            'ts': int(datetime.now().timestamp())
        }]
        
        return self.slack_send_message(
            channel='#support',
            text=f" Новый тикет #{ticket.get('id')}",
            attachments=attachments
        )
    
    # TELEGRAM INTEGRATION 
    
    def telegram_send_message(self, text: str, parse_mode: str = 'HTML') -> Dict[str, Any]:
        """Отправить сообщение в Telegram"""
        if not self.config['telegram']['enabled']:
            return {'success': False, 'error': 'Telegram integration is disabled'}
        
        url = f"https://api.telegram.org/bot{self.config['telegram']['bot_token']}/sendMessage"
        
        payload = {
            'chat_id': self.config['telegram']['chat_id'],
            'text': text,
            'parse_mode': parse_mode
        }
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get('ok'):
                return {'success': True, 'message_id': data.get('result', {}).get('message_id')}
            else:
                return {'success': False, 'error': data.get('description')}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def telegram_create_ticket_notification(self, ticket: dict) -> Dict[str, Any]:
        """Создать уведомление о новом тикете в Telegram"""
        priority_emojis = {
            'low': '🟢',
            'medium': '🟡',
            'high': ''
        }
        
        priority_names = {
            'low': 'Низкий',
            'medium': 'Средний',
            'high': 'Высокий'
        }
        
        text = f"""
<b> Новый тикет #{ticket.get('id')}</b>

<b>Тема:</b> {ticket.get('subject', 'Без темы')}
<b>Категория:</b> {ticket.get('category', 'Другое')}
<b>Приоритет:</b> {priority_emojis.get(ticket.get('priority', 'medium'), '🟡')} {priority_names.get(ticket.get('priority', 'medium'), 'Средний')}
<b>Пользователь:</b> {ticket.get('user_name', 'Неизвестный')}

<b>Описание:</b>
{ticket.get('description', 'Без описания')[:500]}
 """
        return self.telegram_send_message(text)
    
    # STRIPE INTEGRATION 
    
    def stripe_create_customer(self, email: str, name: str) -> Dict[str, Any]:
        """Создать customer в Stripe"""
        if not self.config['stripe']['enabled']:
            return {'success': False, 'error': 'Stripe integration is disabled'}
        
        url = 'https://api.stripe.com/v1/customers'
        headers = {
            'Authorization': f"Bearer {self.config['stripe']['api_key']}"
        }
        
        payload = {
            'email': email,
            'name': name
        }
        
        try:
            response = requests.post(url, data=payload, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            return {'success': True, 'customer_id': data.get('id')}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def stripe_create_payment_intent(self, amount: int, currency: str = 'usd', 
                                      customer_id: Optional[str] = None) -> Dict[str, Any]:
        """Создать payment intent в Stripe"""
        if not self.config['stripe']['enabled']:
            return {'success': False, 'error': 'Stripe integration is disabled'}
        
        url = 'https://api.stripe.com/v1/payment_intents'
        headers = {
            'Authorization': f"Bearer {self.config['stripe']['api_key']}"
        }
        
        payload = {
            'amount': amount,
            'currency': currency
        }
        
        if customer_id:
            payload['customer'] = customer_id
        
        try:
            response = requests.post(url, data=payload, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            return {
                'success': True,
                'payment_intent_id': data.get('id'),
                'client_secret': data.get('client_secret')
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # PAYPAL INTEGRATION 
    
    def paypal_get_access_token(self) -> Optional[str]:
        """Получить access token от PayPal"""
        if not self.config['paypal']['enabled']:
            return None
        
        base_url = 'https://api-m.sandbox.paypal.com' if self.config['paypal']['sandbox'] else 'https://api-m.paypal.com'
        url = f"{base_url}/v1/oauth2/token"
        
        headers = {
            'Accept': 'application/json',
            'Accept-Language': 'en_US'
        }
        
        payload = 'grant_type=client_credentials'
        
        try:
            response = requests.post(
                url,
                data=payload,
                headers=headers,
                auth=(self.config['paypal']['client_id'], self.config['paypal']['client_secret']),
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            return data.get('access_token')
        except Exception:
            return None
    
    def paypal_create_order(self, amount: str, currency: str = 'USD', 
                            description: str = '') -> Dict[str, Any]:
        """Создать order в PayPal"""
        if not self.config['paypal']['enabled']:
            return {'success': False, 'error': 'PayPal integration is disabled'}
        
        access_token = self.paypal_get_access_token()
        if not access_token:
            return {'success': False, 'error': 'Failed to get access token'}
        
        base_url = 'https://api-m.sandbox.paypal.com' if self.config['paypal']['sandbox'] else 'https://api-m.paypal.com'
        url = f"{base_url}/v2/checkout/orders"
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f"Bearer {access_token}"
        }
        
        payload = {
            'intent': 'CAPTURE',
            'purchase_units': [{
                'amount': {
                    'currency_code': currency,
                    'value': amount
                },
                'description': description
            }]
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            # Получить approval URL
            approval_url = None
            for link in data.get('links', []):
                if link.get('rel') == 'approve':
                    approval_url = link.get('href')
                    break
            
            return {
                'success': True,
                'order_id': data.get('id'),
                'approval_url': approval_url
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # CONFIGURATION METHODS 
    
    def enable_integration(self, service: str, config: dict) -> Dict[str, Any]:
        """Включить интеграцию"""
        if service not in self.config:
            return {'success': False, 'error': f'Unknown service: {service}'}
        
        self.config[service]['enabled'] = True
        self.config[service].update(config)
        self._save_config()
        
        return {'success': True}
    
    def disable_integration(self, service: str) -> Dict[str, Any]:
        """Отключить интеграцию"""
        if service not in self.config:
            return {'success': False, 'error': f'Unknown service: {service}'}
        
        self.config[service]['enabled'] = False
        self._save_config()
        
        return {'success': True}
    
    def get_integration_status(self) -> dict:
        """Получить статус всех интеграций"""
        return {
            service: {
                'enabled': config.get('enabled', False),
                'configured': bool(config.get('url') or config.get('webhook_url') or 
                                   config.get('bot_token') or config.get('api_key'))
            }
            for service, config in self.config.items()
        }


# Глобальный экземпляр
integration_manager = IntegrationManager()
