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
        """Database yedekle"""
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"База данных не найдена: {db_path}")
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = os.path.join(self.backup_dir, f'database_{timestamp}.db')
        
        shutil.copy2(db_path, backup_file)
        
        print(f" Database yedeklendi: {backup_file}")
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
        
        print(f" Все data yedeklendi: {backup_file}")
        return backup_file
    
    def backup_config(self) -> str:
        """Config dosyalarыnы yedekle"""
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
        
        print(f" Config yedeklendi: {backup_file}")
        return backup_file
    
    def restore_database(self, backup_file: str, db_path: str = 'data/bot.db'):
        """Database geri загрузить"""
        if not os.path.exists(backup_file):
            raise FileNotFoundError(f"Резервная копия не найдена: {backup_file}")
        
        # Текущий database'i yedekle
        if os.path.exists(db_path):
            self.backup_database(db_path)
        
        shutil.copy2(backup_file, db_path)
        
        print(f" Database geri yюklendi: {backup_file}")
    
    def restore_all_data(self, backup_file: str):
        """Все data'yы geri загрузить"""
        if not os.path.exists(backup_file):
            raise FileNotFoundError(f"Резервная копия не найдена: {backup_file}")
        
        data_dir = 'data'
        
        # Текущий data'yы yedekle
        if os.path.exists(data_dir):
            self.backup_all_data()
        
        with zipfile.ZipFile(backup_file, 'r') as zipf:
            zipf.extractall(data_dir)
        
        print(f" Все data geri yюklendi: {backup_file}")
    
    def restore_config(self, backup_file: str):
        """Config geri загрузить"""
        if not os.path.exists(backup_file):
            raise FileNotFoundError(f"Резервная копия не найдена: {backup_file}")
        
        with zipfile.ZipFile(backup_file, 'r') as zipf:
            zipf.extractall('.')
        
        print(f" Config geri yюklendi: {backup_file}")
    
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
        
        # Tarihe по очередьla
        backups.sort(key=lambda x: x['created_at'], reverse=True)
        
        return backups
    
    def delete_backup(self, backup_file: str):
        """Yedek удалить"""
        if not os.path.exists(backup_file):
            raise FileNotFoundError(f"Резервная копия не найдена: {backup_file}")
        
        os.remove(backup_file)
        print(f" Yedek удалено: {backup_file}")
    
    def cleanup_old_backups(self, days: int = 30):
        """Eski yedekleri удалить"""
        cutoff = datetime.now() - timedelta(days=days)
        
        for backup_file in glob.glob(os.path.join(self.backup_dir, '*')):
            stat = os.stat(backup_file)
            file_time = datetime.fromtimestamp(stat.st_mtime)
            
            if file_time < cutoff:
                os.remove(backup_file)
                print(f" Eski yedek удалено: {backup_file}")
    
    def get_backup_info(self, backup_file: str) -> Dict:
        """Yedek информацияlerini al"""
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
        """Otomatik yedekleme planla (placeholder)"""
        # Gerчek uygulamada scheduler kullanыlacak
        print(f"⏰ Otomatik yedekleme planlandы: Her {interval_hours} saatte bir")
    
    def export_stats(self) -> Dict:
        """Резвное копирование статистикаini al"""
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
