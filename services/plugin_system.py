"""
Система плагинов
Загрузка и управление плагинами
"""

import os
import json
import importlib.util
from typing import List, Dict, Optional
from datetime import datetime


class Plugin:
    """Класс плагина"""
    
    def __init__(self, name: str, version: str = '1.0.0', author: str = 'Unknown',
                 description: str = '', enabled: bool = True):
        self.name = name
        self.version = version
        self.author = author
        self.description = description
        self.enabled = enabled
        self.loaded_at = None
        self.module = None
    
    def to_dict(self) -> Dict:
        """Преобразовать в dict"""
        return {
            'name': self.name,
            'version': self.version,
            'author': self.author,
            'description': self.description,
            'enabled': self.enabled,
            'loaded_at': self.loaded_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Plugin':
        """Создать из словаря"""
        plugin = cls(
            name=data['name'],
            version=data.get('version', '1.0.0'),
            author=data.get('author', 'Unknown'),
            description=data.get('description', ''),
            enabled=data.get('enabled', True)
        )
        plugin.loaded_at = data.get('loaded_at')
        return plugin


class PluginManager:
    """Менеджер плагинов"""
    
    def __init__(self, plugins_dir: str = 'plugins'):
        self.plugins_dir = plugins_dir
        self.plugins: Dict[str, Plugin] = {}
        self.config_file = 'data/plugins_config.json'
        
        os.makedirs(plugins_dir, exist_ok=True)
        self.load_config()
    
    def load_config(self):
        """Config загрузить"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for plugin_data in data.get('plugins', []):
                        plugin = Plugin.from_dict(plugin_data)
                        self.plugins[plugin.name] = plugin
            except Exception as e:
                print(f" Не удалось загрузить конфиг плагина: {e}")
    
    def save_config(self):
        """Config сохранить"""
        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
        
        data = {
            'plugins': [plugin.to_dict() for plugin in self.plugins.values()]
        }
        
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def load_plugin(self, plugin_name: str) -> bool:
        """Plugin загрузить"""
        plugin_file = os.path.join(self.plugins_dir, f'{plugin_name}.py')
        
        if not os.path.exists(plugin_file):
            print(f" Plugin не найдено: {plugin_name}")
            return False
        
        try:
            spec = importlib.util.spec_from_file_location(plugin_name, plugin_file)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Plugin metadata al
            plugin = Plugin(
                name=plugin_name,
                version=getattr(module, '__version__', '1.0.0'),
                author=getattr(module, '__author__', 'Unknown'),
                description=getattr(module, '__description__', ''),
                enabled=True
            )
            plugin.loaded_at = datetime.now().isoformat()
            plugin.module = module
            
            self.plugins[plugin_name] = plugin
            self.save_config()
            
            # Вызываем setup плагина
            if hasattr(module, 'setup'):
                module.setup()
            
            print(f" Плагин загружен: {plugin_name}")
            return True
        except Exception as e:
            print(f" Не удалось загрузить плагин: {plugin_name} - {e}")
            return False
    
    def unload_plugin(self, plugin_name: str) -> bool:
        """Plugin удалить"""
        if plugin_name not in self.plugins:
            print(f" Plugin не найдено: {plugin_name}")
            return False
        
        plugin = self.plugins[plugin_name]
        
        # Вызываем teardown плагина
        if plugin.module and hasattr(plugin.module, 'teardown'):
            plugin.module.teardown()
        
        del self.plugins[plugin_name]
        self.save_config()
        
        print(f" Plugin удалено: {plugin_name}")
        return True
    
    def enable_plugin(self, plugin_name: str) -> bool:
        """Plugin включить"""
        if plugin_name not in self.plugins:
            return False
        
        self.plugins[plugin_name].enabled = True
        self.save_config()
        
        print(f" Плагин включён: {plugin_name}")
        return True
    
    def disable_plugin(self, plugin_name: str) -> bool:
        """Отключить плагин"""
        if plugin_name not in self.plugins:
            return False
        
        self.plugins[plugin_name].enabled = False
        self.save_config()
        
        print(f" Плагин отключен: {plugin_name}")
        return True
    
    def get_plugin(self, plugin_name: str) -> Optional[Plugin]:
        """Plugin al"""
        return self.plugins.get(plugin_name)
    
    def get_all_plugins(self) -> List[Plugin]:
        """Все pluginleri al"""
        return list(self.plugins.values())
    
    def get_enabled_plugins(self) -> List[Plugin]:
        """Etkin pluginleri al"""
        return [p for p in self.plugins.values() if p.enabled]
    
    def list_available_plugins(self) -> List[str]:
        """Список текущих плагинов"""
        plugins = []
        
        for file in os.listdir(self.plugins_dir):
            if file.endswith('.py') and not file.startswith('__'):
                plugins.append(file[:-3])
        
        return plugins
    
    def install_plugin(self, plugin_url: str) -> bool:
        """Установить плагин."""
        # В полноценном развертывании: git clone или скачивание архива
        print(f"📦 Установка плагина: {plugin_url}")
        return True
    
    def update_plugin(self, plugin_name: str) -> bool:
        """Обновить плагин."""
        # В полноценном развертывании: git pull
        print(f"⏰ Обновление плагина: {plugin_name}")
        return True
    
    def get_plugin_info(self, plugin_name: str) -> Optional[Dict]:
        """Получить информацию о плагине"""
        plugin = self.get_plugin(plugin_name)
        
        if not plugin:
            return None
        
        return {
            'name': plugin.name,
            'version': plugin.version,
            'author': plugin.author,
            'description': plugin.description,
            'enabled': plugin.enabled,
            'loaded_at': plugin.loaded_at
        }
    
    def get_stats(self) -> Dict:
        """Получить статистику плагинов"""
        total_plugins = len(self.plugins)
        enabled_plugins = len(self.get_enabled_plugins())
        
        return {
            'total_plugins': total_plugins,
            'enabled_plugins': enabled_plugins,
            'disabled_plugins': total_plugins - enabled_plugins
        }


def create_plugin_manager(plugins_dir: str = 'plugins') -> PluginManager:
    """Создать менеджер плагинов"""
    return PluginManager(plugins_dir)
