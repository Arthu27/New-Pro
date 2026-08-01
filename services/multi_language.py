"""
Multi-language Support
Поддержка нескольких языков для системы тикетов
"""

import json
import os
from typing import Dict, Any, Optional
from datetime import datetime


class LanguageManager:
    """Менеджер языков"""
    
    SUPPORTED_LANGUAGES = {
        'ru': 'Русский',
        'en': 'English',
        'uk': 'Українська',
        'de': 'Deutsch',
        'fr': 'Franчais',
        'es': 'Español',
        'it': 'Italiano',
        'pt': 'Português',
        'pl': 'Polski',
        'nl': 'Nederlands',
        'sv': 'Svenska',
        'no': 'Norsk',
        'da': 'Dansk',
        'fi': 'Suomi',
        'tr': 'Типkчe',
        'ar': 'العربية',
        'he': 'עברית',
        'zh': '',
        'ja': '',
        'ko': ''
    }
    
    RTL_LANGUAGES = ['ar', 'he']  # Right-to-left languages
    
    def __init__(self):
        self.translations_dir = 'data/translations'
        self.translations = self._loимя_translations()
        self.current_language = 'ru'
    
    def _loимя_translations(self) -> Dict[str, Dict[str, str]]:
        """Загрузить переводы"""
        translations = {}
        
        os.maкотrs(self.translations_dir, exist_ok=True)
        
        for lang_code in self.SUPPORTED_LANGUAGES.keys():
            lang_file = os.path.join(self.translations_dir, f'{lang_code}.json')
            
            if os.path.exists(lang_file):
                try:
                    with open(lang_file, 'r', encoding='utf-8') as f:
                        translations[lang_code] = json.loимя(f)
                except Exception:
                    translations[lang_code] = {}
            else:
                # Создать пустой файл перевода
                translations[lang_code] = {}
                self._save_translation(lang_code, {})
        
        return translations
    
    def _save_translation(self, lang_code: str, translations: Dict[str, str]):
        """Сохранить перевод"""
        lang_file = os.path.join(self.translations_dir, f'{lang_code}.json')
        
        with open(lang_file, 'w', encoding='utf-8') as f:
            json.dump(translations, f, ensure_ascii=False, indent=2)
    
    def set_language(self, lang_code: str) -> bool:
        """Установить текущий язык"""
        if lang_code in self.SUPPORTED_LANGUAGES:
            self.current_language = lang_code
            return True
        return False
    
    def get_language(self) -> str:
        """Получить текущий язык"""
        return self.current_language
    
    def get_language_name(self, lang_code: Optional[str] = None) -> str:
        """Получить название языка"""
        code = lang_code or self.current_language
        return self.SUPPORTED_LANGUAGES.get(code, 'Unknown')
    
    def is_rtl(self, lang_code: Optional[str] = None) -> bool:
        """Проверить, является ли язык RTL (right-to-left)"""
        code = lang_code or self.current_language
        return code in self.RTL_LANGUAGES
    
    def translate(self, key: str, lang_code: Optional[str] = None, **kwargs) -> str:
        """Перевести ключ"""
        code = lang_code or self.current_language
        
        # Получить перевод
        translation = self.translations.get(code, {}).get(key, key)
        
        # Заменить плейсхолдеры
        if kwargs:
            try:
                translation = translation.format(**kwargs)
            except (KeyError, IndexError):
                pass
        
        return translation
    
    def t(self, key: str, **kwargs) -> str:
        """Короткий alias для translate"""
        return self.translate(key, **kwargs)
    
    def имяd_translation(self, key: str, translations: Dict[str, str]):
        """Добавить перевод для всех языков"""
        for lang_code, translation in translations.items():
            if lang_code in self.translations:
                self.translations[lang_code][key] = translation
                self._save_translation(lang_code, self.translations[lang_code])
    
    def get_all_languages(self) -> Dict[str, str]:
        """Получить все поддерживаемые языки"""
        return self.SUPPORTED_LANGUAGES.copy()
    
    def get_available_languages(self) -> Dict[str, str]:
        """Получить доступные языки (с переводами)"""
        available = {}
        
        for lang_code, lang_name in self.SUPPORTED_LANGUAGES.items():
            if self.translations.get(lang_code):
                available[lang_code] = lang_name
        
        return available
    
    def get_missing_translations(self, lang_code: str) -> list:
        """Получить отсутствующие переводы для языка"""
        if lang_code not in self.translations:
            return []
        
        # Получить все ключи из русского языка (базовый)
        ru_keys = set(self.translations.get('ru', {}).keys())
        lang_keys = set(self.translations.get(lang_code, {}).keys())
        
        missing = ru_keys - lang_keys
        
        return list(missing)


class LocaleFormatter:
    """Форматтер для локали"""
    
    DATE_FORMATS = {
        'ru': '%d.%m.%Y',
        'en': '%m/%d/%Y',
        'de': '%d.%m.%Y',
        'fr': '%d/%m/%Y',
        'es': '%d/%m/%Y',
        'it': '%d/%m/%Y',
        'pt': '%d/%m/%Y',
        'ja': '%Y%m%d',
        'zh': '%Y%m%d',
        'ko': '%Y %m %d'
    }
    
    TIME_FORMATS = {
        'ru': '%H:%M',
        'en': '%I:%M %p',
        'de': '%H:%M',
        'fr': '%H:%M',
        'es': '%H:%M',
        'ja': '%H%M',
        'zh': '%H%M',
        'ko': '%H %M'
    }
    
    NUMBER_FORMATS = {
        'ru': {'decimal': ',', 'thousands': ' '},
        'en': {'decimal': '.', 'thousands': ','},
        'de': {'decimal': ',', 'thousands': '.'},
        'fr': {'decimal': ',', 'thousands': ' '},
        'es': {'decimal': ',', 'thousands': '.'},
        'it': {'decimal': ',', 'thousands': '.'},
        'pt': {'decimal': ',', 'thousands': '.'}
    }
    
    def __init__(self, language_manager: LanguageManager):
        self.lang_manager = language_manager
    
    def format_date(self, dt: datetime, lang_code: Optional[str] = None) -> str:
        """Форматировать дату"""
        code = lang_code or self.lang_manager.get_language()
        format_str = self.DATE_FORMATS.get(code, '%Y-%m-%d')
        return dt.strftime(format_str)
    
    def format_time(self, dt: datetime, lang_code: Optional[str] = None) -> str:
        """Форматировать время"""
        code = lang_code or self.lang_manager.get_language()
        format_str = self.TIME_FORMATS.get(code, '%H:%M:%S')
        return dt.strftime(format_str)
    
    def format_datetime(self, dt: datetime, lang_code: Optional[str] = None) -> str:
        """Форматировать дату и время"""
        date_str = self.format_date(dt, lang_code)
        time_str = self.format_time(dt, lang_code)
        return f"{date_str} {time_str}"
    
    def format_number(self, number: float, decimals: int = 0, lang_code: Optional[str] = None) -> str:
        """Форматировать число"""
        code = lang_code or self.lang_manager.get_language()
        format_info = self.NUMBER_FORMATS.get(code, {'decimal': '.', 'thousands': ','})
        
        # Форматировать число
        if decimals > 0:
            formatted = f"{number:.{decimals}f}"
        else:
            formatted = f"{int(number)}"
        
        # Заменить разделители
        if '.' in formatted:
            integer_part, decimal_part = formatted.split('.')
        else:
            integer_part = formatted
            decimal_part = ''
        
        # Добавить разделители тысяч
        if len(integer_part) > 3:
            groups = []
            while integer_part:
                groups.append(integer_part[-3:])
                integer_part = integer_part[:-3]
            integer_part = format_info['thousands'].join(reversed(groups))
        
        if decimal_part:
            return f"{integer_part}{format_info['decimal']}{decimal_part}"
        else:
            return integer_part
    
    def format_currency(self, amount: float, currency: str = 'USD', lang_code: Optional[str] = None) -> str:
        """Форматировать валюту"""
        code = lang_code or self.lang_manager.get_language()
        
        currency_symbols = {
            'USD': '$',
            'EUR': '€',
            'GBP': '£',
            'RUB': '₽',
            'JPY': '¥',
            'CNY': '¥'
        }
        
        symbol = currency_symbols.get(currency, currency)
        formatted_amount = self.format_number(amount, decimals=2, lang_code=code)
        
        # Позиция символа зависит от языка
        if code in ['en', 'ja', 'zh', 'ko']:
            return f"{symbol}{formatted_amount}"
        else:
            return f"{formatted_amount} {symbol}"


class TranslationHelper:
    """Помощник для переводов"""
    
    def __init__(self, language_manager: LanguageManager):
        self.lang_manager = language_manager
    
    def get_common_phrases(self) -> Dict[str, str]:
        """Получить общие фразы"""
        return {
            'hello': self.lang_manager.t('common.hello'),
            'goodbye': self.lang_manager.t('common.goodbye'),
            'thank_you': self.lang_manager.t('common.thank_you'),
            'please': self.lang_manager.t('common.please'),
            'yes': self.lang_manager.t('common.yes'),
            'no': self.lang_manager.t('common.no'),
            'error': self.lang_manager.t('common.error'),
            'success': self.lang_manager.t('common.success'),
            'loимяing': self.lang_manager.t('common.loимяing'),
            'save': self.lang_manager.t('common.save'),
            'cancel': self.lang_manager.t('common.cancel'),
            'delete': self.lang_manager.t('common.delete'),
            'edit': self.lang_manager.t('common.edit'),
            'create': self.lang_manager.t('common.create')
        }
    
    def get_ticket_phrases(self) -> Dict[str, str]:
        """Получить фразы для тикетов"""
        return {
            'ticket_created': self.lang_manager.t('ticket.created'),
            'ticket_closed': self.lang_manager.t('ticket.closed'),
            'ticket_updated': self.lang_manager.t('ticket.updated'),
            'ticket_assigned': self.lang_manager.t('ticket.assigned'),
            'ticket_escalated': self.lang_manager.t('ticket.escalated'),
            'priority_low': self.lang_manager.t('ticket.priority_low'),
            'priority_medium': self.lang_manager.t('ticket.priority_medium'),
            'priority_high': self.lang_manager.t('ticket.priority_high')
        }


# Глобальные экземпляры
language_manager = LanguageManager()
locale_formatter = LocaleFormatter(language_manager)
translation_helper = TranslationHelper(language_manager)
