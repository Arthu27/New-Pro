"""
UI/UX Improvements
Улучшения пользовательского интерфейса
"""

from logger import get_logger

_log = get_logger("ui_ux")

import json
import os
from datetime import datetime
from typing import Dict, List, Any, Optional


class ThemeManager:
    """Менеджер тем"""
    
    BUILT_IN_THEMES = {
        'dark': {
            'name': 'Тёмная тема',
            'colors': {
                'primary': '#5865F2',
                'secondary': '#9b59b6',
                'success': '#2ecc71',
                'warning': '#f1c40f',
                'danger': '#e74c3c',
                'background': '#1a1a1a',
                'surface': '#2d2d2d',
                'text': '#ffffff',
                'text-muted': '#888888'
            }
        },
        'light': {
            'name': 'Светлая тема',
            'colors': {
                'primary': '#5865F2',
                'secondary': '#9b59b6',
                'success': '#27ae60',
                'warning': '#f39c12',
                'danger': '#c0392b',
                'background': '#ffffff',
                'surface': '#f5f5f5',
                'text': '#000000',
                'text-muted': '#666666'
            }
        },
        'blue': {
            'name': 'Синяя тема',
            'colors': {
                'primary': '#3498db',
                'secondary': '#2980b9',
                'success': '#27ae60',
                'warning': '#f39c12',
                'danger': '#e74c3c',
                'background': '#1a2332',
                'surface': '#2c3e50',
                'text': '#ecf0f1',
                'text-muted': '#95a5a6'
            }
        },
        'green': {
            'name': 'Зелёная тема',
            'colors': {
                'primary': '#27ae60',
                'secondary': '#229954',
                'success': '#27ae60',
                'warning': '#f39c12',
                'danger': '#e74c3c',
                'background': '#1a2e1a',
                'surface': '#2d4a2d',
                'text': '#ecf0f1',
                'text-muted': '#95a5a6'
            }
        }
    }
    
    def __init__(self):
        self.custom_themes_file = 'data/custom_themes.json'
        self.custom_themes = self._load_custom_themes()
        self.user_preferences_file = 'data/user_theme_preferences.json'
        self.user_preferences = self._load_user_preferences()
    
    def _load_custom_themes(self) -> Dict[str, Any]:
        """Загрузить пользовательские темы"""
        if os.path.exists(self.custom_themes_file):
            try:
                with open(self.custom_themes_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as _ex:
                _log.debug("_load_custom_themes(): подавлено: %s", _ex)
        
        return {}
    
    def _save_custom_themes(self):
        """Сохранить пользовательские темы"""
        os.makedirs('data', exist_ok=True)
        with open(self.custom_themes_file, 'w', encoding='utf-8') as f:
            json.dump(self.custom_themes, f, ensure_ascii=False, indent=2)
    
    def _load_user_preferences(self) -> Dict[str, Any]:
        """Загрузить предпочтения пользователей"""
        if os.path.exists(self.user_preferences_file):
            try:
                with open(self.user_preferences_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as _ex:
                _log.debug("_load_user_preferences(): подавлено: %s", _ex)
        
        return {}
    
    def _save_user_preferences(self):
        """Сохранить предпочтения пользователей"""
        os.makedirs('data', exist_ok=True)
        with open(self.user_preferences_file, 'w', encoding='utf-8') as f:
            json.dump(self.user_preferences, f, ensure_ascii=False, indent=2)
    
    def get_theme(self, theme_id: str) -> Optional[Dict[str, Any]]:
        """Получить тему"""
        if theme_id in self.BUILT_IN_THEMES:
            return self.BUILT_IN_THEMES[theme_id]
        
        if theme_id in self.custom_themes:
            return self.custom_themes[theme_id]
        
        return None
    
    def create_custom_theme(self, theme_id: str, name: str, colors: Dict[str, str]) -> bool:
        """Создать пользовательскую тему"""
        self.custom_themes[theme_id] = {
            'name': name,
            'colors': colors,
            'created_at': datetime.now().isoformat()
        }
        
        self._save_custom_themes()
        
        return True
    
    def delete_custom_theme(self, theme_id: str) -> bool:
        """Удалить пользовательскую тему"""
        if theme_id in self.custom_themes:
            del self.custom_themes[theme_id]
            self._save_custom_themes()
            return True
        return False
    
    def set_user_theme(self, user_id: str, theme_id: str) -> bool:
        """Установить тему пользователя"""
        theme = self.get_theme(theme_id)
        
        if not theme:
            return False
        
        self.user_preferences[user_id] = {
            'theme_id': theme_id,
            'updated_at': datetime.now().isoformat()
        }
        
        self._save_user_preferences()
        
        return True
    
    def get_user_theme(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Получить тему пользователя"""
        if user_id not in self.user_preferences:
            return self.BUILT_IN_THEMES['dark']  # Тема по умолчанию
        
        theme_id = self.user_preferences[user_id].get('theme_id', 'dark')
        return self.get_theme(theme_id)
    
    def get_all_themes(self) -> Dict[str, Any]:
        """Получить все темы"""
        all_themes = self.BUILT_IN_THEMES.copy()
        all_themes.update(self.custom_themes)
        return all_themes


class AnimationManager:
    """Менеджер анимаций"""
    
    ANIMATIONS = {
        'fade-in': {
            'name': 'Появление',
            'css': '''
                @keyframes fadeIn {
                    from { opacity: 0; }
                    to { opacity: 1; }
                }
                .animate-fade-in {
                    animation: fadeIn 0.3s ease-in;
                }
            '''
        },
        'slide-up': {
            'name': 'Слайд вверх',
            'css': '''
                @keyframes slideUp {
                    from { transform: translateY(20px); opacity: 0; }
                    to { transform: translateY(0); opacity: 1; }
                }
                .animate-slide-up {
                    animation: slideUp 0.3s ease-out;
                }
            '''
        },
        'slide-down': {
            'name': 'Слайд вниз',
            'css': '''
                @keyframes slideDown {
                    from { transform: translateY(-20px); opacity: 0; }
                    to { transform: translateY(0); opacity: 1; }
                }
                .animate-slide-down {
                    animation: slideDown 0.3s ease-out;
                }
            '''
        },
        'scale-in': {
            'name': 'Масштабирование',
            'css': '''
                @keyframes scaleIn {
                    from { transform: scale(0.9); opacity: 0; }
                    to { transform: scale(1); opacity: 1; }
                }
                .animate-scale-in {
                    animation: scaleIn 0.2s ease-out;
                }
            '''
        },
        'pulse': {
            'name': 'Пульсация',
            'css': '''
                @keyframes pulse {
                    0%, 100% { opacity: 1; }
                    50% { opacity: 0.5; }
                }
                .animate-pulse {
                    animation: pulse 2s ease-in-out infinite;
                }
            '''
        }
    }
    
    def get_animation(self, animation_id: str) -> Optional[Dict[str, Any]]:
        """Получить анимацию"""
        return self.ANIMATIONS.get(animation_id)
    
    def get_all_animations(self) -> Dict[str, Any]:
        """Получить все анимации"""
        return self.ANIMATIONS.copy()
    
    def generate_css(self) -> str:
        """Генерировать CSS для всех анимаций"""
        css_parts = []
        
        for animation_id, animation in self.ANIMATIONS.items():
            css_parts.append(animation['css'])
        
        return '\n\n'.join(css_parts)


class WidgetManager:
    """Менеджер виджетов"""
    
    def __init__(self):
        self.widgets_file = 'data/widgets.json'
        self.widgets = self._load_widgets()
        self.user_layouts_file = 'data/user_widget_layouts.json'
        self.user_layouts = self._load_user_layouts()
    
    def _load_widgets(self) -> Dict[str, Any]:
        """Загрузить виджеты"""
        if os.path.exists(self.widgets_file):
            try:
                with open(self.widgets_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as _ex:
                _log.debug("_load_widgets(): подавлено: %s", _ex)
        
        return self._get_default_widgets()
    
    def _get_default_widgets(self) -> Dict[str, Any]:
        """Получить виджеты по умолчанию"""
        return {
            'stats': {
                'name': 'Статистика',
                'description': 'Общая статистика системы',
                'icon': 'chart-bar',
                'size': 'medium',
                'refresh_interval': 60
            },
            'recent_tickets': {
                'name': 'Последние тикеты',
                'description': 'Список последних тикетов',
                'icon': 'ticket-alt',
                'size': 'large',
                'refresh_interval': 30
            },
            'notifications': {
                'name': 'Уведомления',
                'description': 'Последние уведомления',
                'icon': 'bell',
                'size': 'small',
                'refresh_interval': 15
            },
            'activity_feed': {
                'name': 'Лента активности',
                'description': 'Последние действия',
                'icon': 'stream',
                'size': 'large',
                'refresh_interval': 10
            }
        }
    
    def _save_widgets(self):
        """Сохранить виджеты"""
        os.makedirs('data', exist_ok=True)
        with open(self.widgets_file, 'w', encoding='utf-8') as f:
            json.dump(self.widgets, f, ensure_ascii=False, indent=2)
    
    def _load_user_layouts(self) -> Dict[str, Any]:
        """Загрузить макеты пользователей"""
        if os.path.exists(self.user_layouts_file):
            try:
                with open(self.user_layouts_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as _ex:
                _log.debug("_load_user_layouts(): подавлено: %s", _ex)
        
        return {}
    
    def _save_user_layouts(self):
        """Сохранить макеты пользователей"""
        os.makedirs('data', exist_ok=True)
        with open(self.user_layouts_file, 'w', encoding='utf-8') as f:
            json.dump(self.user_layouts, f, ensure_ascii=False, indent=2)
    
    def get_widget(self, widget_id: str) -> Optional[Dict[str, Any]]:
        """Получить виджет"""
        return self.widgets.get(widget_id)
    
    def get_all_widgets(self) -> Dict[str, Any]:
        """Получить все виджеты"""
        return self.widgets.copy()
    
    def set_user_layout(self, user_id: str, layout: List[Dict[str, Any]]) -> bool:
        """Установить макет пользователя"""
        self.user_layouts[user_id] = {
            'layout': layout,
            'updated_at': datetime.now().isoformat()
        }
        
        self._save_user_layouts()
        
        return True
    
    def get_user_layout(self, user_id: str) -> Optional[List[Dict[str, Any]]]:
        """Получить макет пользователя"""
        if user_id not in self.user_layouts:
            return None
        
        return self.user_layouts[user_id].get('layout')


class AccessibilityManager:
    """Менеджер доступности (WCAG 2.1)"""
    
    def __init__(self):
        self.preferences_file = 'data/accessibility_preferences.json'
        self.preferences = self._load_preferences()
    
    def _load_preferences(self) -> Dict[str, Any]:
        """Загрузить предпочтения доступности"""
        if os.path.exists(self.preferences_file):
            try:
                with open(self.preferences_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as _ex:
                _log.debug("_load_preferences(): подавлено: %s", _ex)
        
        return {}
    
    def _save_preferences(self):
        """Сохранить предпочтения доступности"""
        os.makedirs('data', exist_ok=True)
        with open(self.preferences_file, 'w', encoding='utf-8') as f:
            json.dump(self.preferences, f, ensure_ascii=False, indent=2)
    
    def set_user_preferences(self, user_id: str, preferences: Dict[str, Any]) -> bool:
        """Установить предпочтения доступности"""
        self.preferences[user_id] = {
            'preferences': preferences,
            'updated_at': datetime.now().isoformat()
        }
        
        self._save_preferences()
        
        return True
    
    def get_user_preferences(self, user_id: str) -> Dict[str, Any]:
        """Получить предпочтения доступности"""
        if user_id not in self.preferences:
            return {
                'high_contrast': False,
                'large_text': False,
                'reduce_motion': False,
                'screen_reader': False,
                'keyboard_navigation': True
            }
        
        return self.preferences[user_id].get('preferences', {})
    
    def generate_css(self, user_id: str) -> str:
        """Генерировать CSS для доступности"""
        prefs = self.get_user_preferences(user_id)
        css_parts = []
        
        if prefs.get('high_contrast'):
            css_parts.append('''
                body {
                    filter: contrast(1.5);
                }
            ''')
        
        if prefs.get('large_text'):
            css_parts.append('''
                body {
                    font-size: 1.2em;
                }
            ''')
        
        if prefs.get('reduce_motion'):
            css_parts.append('''
                *, *::before, *::after {
                    animation-duration: 0.01ms !important;
                    animation-iteration-count: 1 !important;
                    transition-duration: 0.01ms !important;
                }
            ''')
        
        return '\n\n'.join(css_parts)


# Глобальные экземпляры
theme_manager = ThemeManager()
animation_manager = AnimationManager()
widget_manager = WidgetManager()
accessibility_manager = AccessibilityManager()
