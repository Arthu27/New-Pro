"""
Backup Servisi
Система резервного копирования
"""

import os
import shutil
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import zipfile
import glob


class BackupService:
    """Резвное копирование servisi"""
    
    def __init__(self, backup_dir: str = 'backups'):
        self.backup_dir = backup_dir
        os.makedirs(backup_dir, exist_ok=True)
    
    def backup_database(self, db_path: str = 'data/bot.db') -> str:
        """Создать резервную копию базы данных"""
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"База данных не найдена: {db_path}")
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = os.path.join(self.backup_dir, f'database_{timestamp}.db')
        
        shutil.copy2(db_path, backup_file)
        
        print(f" Резервная копия базы данных создана: {backup_file}")
        return backup_file
    
    def backup_all_data(self) -> str:
        """Резвное копирование всей папки данных"""
        data_dir = 'data'
        
        if not os.path.exists(data_dir):
            raise FileNotFoundError(f"Папка данных не найдена: {data_dir}")
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = os.path.join(self.backup_dir, f'data_{timestamp}.zip')
        
        with zipfile.ZipFile(backup_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(data_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, data_dir)
                    zipf.write(file_path, arcname)
        
        print(f" Резервная копия всех данных создана: {backup_file}")
        return backup_file
    
    def backup_config(self) -> str:
        """Резервное копирование файлов конфигурации"""
        config_files = [
            'config.json',
            'config/settings.json',
            '.env'
        ]
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = os.path.join(self.backup_dir, f'config_{timestamp}.zip')
        
        with zipfile.ZipFile(backup_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for config_file in config_files:
                if os.path.exists(config_file):
                    zipf.write(config_file, os.path.basename(config_file))
        
        print(f" Резервная копия конфига создана: {backup_file}")
        return backup_file
    
    def restore_database(self, backup_file: str, db_path: str = 'data/bot.db'):
        """Восстановить базу данных из копии"""
        if not os.path.exists(backup_file):
            raise FileNotFoundError(f"Резервная копия не найдена: {backup_file}")
        
        # Сохраняем текущую базу данных
        if os.path.exists(db_path):
            self.backup_database(db_path)
        
        shutil.copy2(backup_file, db_path)
        
        print(f" База данных восстановлена: {backup_file}")
    
    def restore_all_data(self, backup_file: str):
        """Восстановить все данные"""
        if not os.path.exists(backup_file):
            raise FileNotFoundError(f"Резервная копия не найдена: {backup_file}")
        
        data_dir = 'data'
        
        # Сохраняем все данные
        if os.path.exists(data_dir):
            self.backup_all_data()
        
        with zipfile.ZipFile(backup_file, 'r') as zipf:
            zipf.extractall(data_dir)
        
        print(f" Все данные восстановлены: {backup_file}")
    
    def restore_config(self, backup_file: str):
        """Восстановить конфиг из копии"""
        if not os.path.exists(backup_file):
            raise FileNotFoundError(f"Резервная копия не найдена: {backup_file}")
        
        with zipfile.ZipFile(backup_file, 'r') as zipf:
            zipf.extractall('.')
        
        print(f" Конфигурация восстановлена: {backup_file}")
    
    def list_backups(self, backup_type: str = None) -> List[Dict]:
        """Список резервных копий"""
        backups = []
        
        pattern = os.path.join(self.backup_dir, '*.db') if backup_type == 'database' else \
                  os.path.join(self.backup_dir, '*.zip') if backup_type in ['data', 'config'] else \
                  os.path.join(self.backup_dir, '*')
        
        for backup_file in glob.glob(pattern):
            stat = os.stat(backup_file)
            
            backups.append({
                'file': backup_file,
                'name': os.path.basename(backup_file),
                'size': stat.st_size,
                'created_at': datetime.fromtimestamp(stat.st_mtime),
                'type': 'database' if backup_file.endswith('.db') else 'zip'
            })
        
        # Сортируем по дате
        backups.sort(key=lambda x: x['created_at'], reverse=True)
        
        return backups
    
    def delete_backup(self, backup_file: str):
        """Удалить резервную копию"""
        if not os.path.exists(backup_file):
            raise FileNotFoundError(f"Резервная копия не найдена: {backup_file}")
        
        os.remove(backup_file)
        print(f" Резервная копия удалена: {backup_file}")
    
    def cleanup_old_backups(self, days: int = 30):
        """Удалить старые резервные копии"""
        cutoff = datetime.now() - timedelta(days=days)
        
        for backup_file in glob.glob(os.path.join(self.backup_dir, '*')):
            stat = os.stat(backup_file)
            file_time = datetime.fromtimestamp(stat.st_mtime)
            
            if file_time < cutoff:
                os.remove(backup_file)
                print(f" Старая копия удалена: {backup_file}")
    
    def get_backup_info(self, backup_file: str) -> Dict:
        """Получить информацию о резервных копиях"""
        if not os.path.exists(backup_file):
            raise FileNotFoundError(f"Резервная копия не найдена: {backup_file}")
        
        stat = os.stat(backup_file)
        
        return {
            'file': backup_file,
            'name': os.path.basename(backup_file),
            'size': stat.st_size,
            'created_at': datetime.fromtimestamp(stat.st_mtime),
            'type': 'database' if backup_file.endswith('.db') else 'zip'
        }
    
    def schedule_backup(self, interval_hours: int = 24):
        """Запланировать автоматическое резервное копирование (заглушка)"""
        # Gerчek uygulamada scheduler kullanыlacak
        print(f"⏰ Автоматическое резервное копирование запланировано: каждые {interval_hours} ч")
    
    def export_stats(self) -> Dict:
        """Получить статистику резервного копирования"""
        backups = self.list_backups()
        
        total_size = sum(b['size'] for b in backups)
        
        return {
            'total_backups': len(backups),
            'total_size': total_size,
            'oldest_backup': backups[-1]['created_at'] if backups else None,
            'newest_backup': backups[0]['created_at'] if backups else None
        }


def create_backup_service(backup_dir: str = 'backups') -> BackupService:
    """Backup servisi создать"""
    return BackupService(backup_dir)
