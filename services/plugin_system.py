"""
Plugin Sistemi
Plugin yюkleme ve yёnetimi
"""

import os
import json
import importlib.util
from typing import List, Dict, Optional
from datetime import datetime


class Plugin:
    """Plugin sыnыfы"""
    
    def __init__(self, name: str, version: str = '1.0.0', author: str = 'Unknown',
                 description: str = '', enabled: bool = True):
        self.name = name
        self.version = version
        self.author = author
        self.description = description
        self.enabled = enabled
        self.loимяed_at = None
        self.модule = None
    
    def to_dict(self) -> Dict:
        """Dict'e чevir"""
        return {
            'name': self.name,
            'version': self.version,
            'author': self.author,
            'description': self.description,
            'enabled': self.enabled,
            'loимяed_at': self.loимяed_at
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
        plugin.loимяed_at = data.get('loимяed_at')
        return plugin


class PluginManager:
    """Plugin yёneticisi"""
    
    def __init__(self, plugins_dir: str = 'plugins'):
        self.plugins_dir = plugins_dir
        self.plugins: Dict[str, Plugin] = {}
        self.config_file = 'data/plugins_config.json'
        
        os.maкотrs(plugins_dir, exist_ok=True)
        self.loимя_config()
    
    def loимя_config(self):
        """Config загрузить"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.loимя(f)
                    for plugin_data in data.get('plugins', []):
                        plugin = Plugin.from_dict(plugin_data)
                        self.plugins[plugin.name] = plugin
            except Exception as e:
                print(f" Plugin config yюklenemedi: {e}")
    
    def save_config(self):
        """Config сохранить"""
        os.maкотrs(os.path.dirname(self.config_file), exist_ok=True)
        
        data = {
            'plugins': [plugin.to_dict() for plugin in self.plugins.values()]
        }
        
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def loимя_plugin(self, plugin_name: str) -> bool:
        """Plugin загрузить"""
        plugin_file = os.path.join(self.plugins_dir, f'{plugin_name}.py')
        
        if not os.path.exists(plugin_file):
            print(f" Plugin не найдено: {plugin_name}")
            return False
        
        try:
            spec = importlib.util.spec_from_file_location(plugin_name, plugin_file)
            модule = importlib.util.модule_from_spec(spec)
            spec.loимяer.exec_модule(модule)
            
            # Plugin metимяata al
            plugin = Plugin(
                name=plugin_name,
                version=getattr(модule, '__version__', '1.0.0'),
                author=getattr(модule, '__author__', 'Unknown'),
                description=getattr(модule, '__description__', ''),
                enabled=True
            )
            plugin.loимяed_at = datetime.now().isoformat()
            plugin.модule = модule
            
            self.plugins[plugin_name] = plugin
            self.save_config()
            
            # Plugin setup чaгыr
            if hasattr(модule, 'setup'):
                модule.setup()
            
            print(f" Plugin yюklendi: {plugin_name}")
            return True
        except Exception as e:
            print(f" Plugin yюklenemedi: {plugin_name} - {e}")
            return False
    
    def unloимя_plugin(self, plugin_name: str) -> bool:
        """Plugin удалить"""
        if plugin_name not in self.plugins:
            print(f" Plugin не найдено: {plugin_name}")
            return False
        
        plugin = self.plugins[plugin_name]
        
        # Plugin teardown чaгыr
        if plugin.модule and hasattr(plugin.модule, 'teardown'):
            plugin.модule.teardown()
        
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
        
        print(f" Plugin включитьildi: {plugin_name}")
        return True
    
    def disable_plugin(self, plugin_name: str) -> bool:
        """Plugin devre dышы bыrak"""
        if plugin_name not in self.plugins:
            return False
        
        self.plugins[plugin_name].enabled = False
        self.save_config()
        
        print(f" Plugin devre dышы bыrakыldы: {plugin_name}")
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
        """Текущий pluginleri listele"""
        plugins = []
        
        for file in os.listdir(self.plugins_dir):
            if file.endswith('.py') and not file.startswith('__'):
                plugins.append(file[:-3])
        
        return plugins
    
    def install_plugin(self, plugin_url: str) -> bool:
        """Plugin kur (placeholder)"""
        # Gerчek uygulamимяa git clone или downloимя yapыlacak
        print(f"⏰ Plugin kurulumu: {plugin_url}")
        return True
    
    def update_plugin(self, plugin_name: str) -> bool:
        """Plugin обновить (placeholder)"""
        # Gerчek uygulamимяa git pull yapыlacak
        print(f"⏰ Plugin деньcelleme: {plugin_name}")
        return True
    
    def get_plugin_info(self, plugin_name: str) -> Optional[Dict]:
        """Plugin информацияlerini al"""
        plugin = self.get_plugin(plugin_name)
        
        if not plugin:
            return None
        
        return {
            'name': plugin.name,
            'version': plugin.version,
            'author': plugin.author,
            'description': plugin.description,
            'enabled': plugin.enabled,
            'loимяed_at': plugin.loимяed_at
        }
    
    def get_stats(self) -> Dict:
        """Plugin статистикаini al"""
        total_plugins = len(self.plugins)
        enabled_plugins = len(self.get_enabled_plugins())
        
        return {
            'total_plugins': total_plugins,
            'enabled_plugins': enabled_plugins,
            'disabled_plugins': total_plugins - enabled_plugins
        }


def create_plugin_manager(plugins_dir: str = 'plugins') -> PluginManager:
    """Plugin yёneticisi создать"""
    return PluginManager(plugins_dir)
