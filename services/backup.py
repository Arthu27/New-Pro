"""
Backup Servisi
Система резервного копирования

Современный модульный API (используется cogs/backup_cog.py и веб-панелью):
  create_backup()    — zip-архив data/ (атомарно, с manifest.json внутри)
  list_backups()     — список архивов (свежие первые)
  rotate_backups()   — оставить N самых свежих, остальные удалить
  resolve_backup()   — безопасный путь к архиву (анти path-traversal)
  format_size()      — человекочитаемый размер

Секреты (panel_credentials*, flask_secret.key, .env, flask-сессии) в архив
НЕ попадают: бэкап не должен становиться способом унести ключи панели.

Ниже класс BackupService оставлен для обратной совместимости.
"""

from logger import get_logger

_log = get_logger("backup")

import os
import re
import shutil
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from uuid import uuid4
import zipfile
import glob

# ── Настройки по умолчанию ────────────────────────────────────────────────
BACKUP_DIR_DEFAULT = 'backups'
DATA_DIR_DEFAULT = 'data'
BACKUP_KEEP_DEFAULT = 7

# Файлы-СЕКРЕТЫ: никогда не включаются в архив
EXCLUDED_FILES = frozenset({
    'panel_credentials.json',
    'panel_credentials.txt',
    'flask_secret.key',
    '.env',
})
# Префиксы служебных файлов (flask-сессии и т.п.) — в бэкапе не нужны
EXCLUDED_PREFIXES = ('web_session',)

# backup_20260811_050000_ab12.zip
BACKUP_NAME_RE = re.compile(r'^backup_\d{8}_\d{6}_[0-9a-f]{4}\.zip$')


def _is_excluded(rel_path: str) -> bool:
    base = os.path.basename(rel_path)
    if base in EXCLUDED_FILES:
        return True
    return any(base.startswith(p) for p in EXCLUDED_PREFIXES)


def format_size(num) -> str:
    """Человекочитаемый размер: 512 Б / 3.2 КБ / 1.5 МБ."""
    try:
        num = float(num)
    except (TypeError, ValueError):
        return '0 Б'
    for unit in ('Б', 'КБ', 'МБ', 'ГБ'):
        if num < 1024 or unit == 'ГБ':
            if unit == 'Б':
                return f'{int(num)} {unit}'
            return f'{num:.1f} {unit}'
        num /= 1024.0
    return f'{num:.1f} ГБ'


def valid_backup_name(name) -> bool:
    """Строгая проверка имени архива (защита от ../ и прочего)."""
    return isinstance(name, str) and bool(BACKUP_NAME_RE.match(name))


def resolve_backup(name, backup_dir: str = BACKUP_DIR_DEFAULT) -> Optional[str]:
    """Абсолютный путь к существующему архиву или None.

    Двойная защита: regex имени + realpath обязан остаться внутри backup_dir.
    """
    if not valid_backup_name(name):
        return None
    root = os.path.realpath(backup_dir)
    path = os.path.realpath(os.path.join(root, name))
    if not path.startswith(root + os.sep):
        return None
    if not os.path.isfile(path):
        return None
    return path


def create_backup(data_dir: str = DATA_DIR_DEFAULT,
                  backup_dir: str = BACKUP_DIR_DEFAULT,
                  reason: str = 'ручной', by: Optional[str] = None) -> Dict:
    """Создать zip-архив данных.

    Пишет в <name>.part и атомарно переименовывает — полу-записанных
    архивов не бывает даже при падении посреди упаковки.
    Внутрь кладёт manifest.json с метаданными. Возвращает info-dict.
    """
    if not os.path.isdir(data_dir):
        raise FileNotFoundError(f'Папка данных не найдена: {data_dir}')
    os.makedirs(backup_dir, exist_ok=True)

    ts = datetime.now()
    name = f'backup_{ts:%Y%m%d_%H%M%S}_{uuid4().hex[:4]}.zip'
    tmp_path = os.path.join(backup_dir, name + '.part')

    files = 0
    skipped = 0
    source_bytes = 0
    try:
        with zipfile.ZipFile(tmp_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            manifest = {
                'created_at': ts.isoformat(timespec='seconds'),
                'reason': reason,
                'by': by or '',
                'app': 'Aether (MOEBIUS)',
                'version': 2,
            }
            zf.writestr('manifest.json',
                        json.dumps(manifest, ensure_ascii=False, indent=2))
            for root, dirs, fnames in os.walk(data_dir):
                dirs.sort()
                for fn in sorted(fnames):
                    full = os.path.join(root, fn)
                    rel = os.path.relpath(full, data_dir)
                    if _is_excluded(rel):
                        skipped += 1
                        continue
                    try:
                        zf.write(full, os.path.join('data', rel))
                        files += 1
                        source_bytes += os.path.getsize(full)
                    except OSError:
                        # файл удалили/заблокировали прямо под нами — пропускаем
                        skipped += 1
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError as _ex:
            _log.debug("create_backup(): подавлено: %s", _ex)
        raise

    final_path = os.path.join(backup_dir, name)
    os.replace(tmp_path, final_path)
    return {
        'name': name,
        'size': os.path.getsize(final_path),
        'files': files,
        'skipped': skipped,
        'source_bytes': source_bytes,
        'created_at': ts.isoformat(timespec='seconds'),
        'reason': reason,
        'by': by or '',
    }


def list_backups(backup_dir: str = BACKUP_DIR_DEFAULT) -> List[Dict]:
    """Список архивов (свежие первые) с размером и датой."""
    items = []
    for path in glob.glob(os.path.join(backup_dir, 'backup_*.zip')):
        name = os.path.basename(path)
        if not valid_backup_name(name):
            continue  # чужеродные backup_*.zip не показываем и не трогаем
        try:
            st = os.stat(path)
        except OSError as _ex:
            _log.debug("list_backups(): подавлено: %s", _ex)
            continue
        items.append({
            'name': name,
            'size': st.st_size,
            'size_h': format_size(st.st_size),
            'created_at': datetime.fromtimestamp(st.st_mtime).isoformat(timespec='seconds'),
            'mtime': st.st_mtime,
        })
    items.sort(key=lambda x: x['mtime'], reverse=True)
    return items


def rotate_backups(backup_dir: str = BACKUP_DIR_DEFAULT,
                   keep: int = BACKUP_KEEP_DEFAULT) -> List[str]:
    """Оставить `keep` самых свежих архивов, остальные удалить.

    Возвращает список удалённых имён.
    """
    keep = max(1, int(keep))
    items = list_backups(backup_dir)
    removed = []
    for it in items[keep:]:
        path = resolve_backup(it['name'], backup_dir)
        if not path:
            continue
        try:
            os.remove(path)
            removed.append(it['name'])
        except OSError as _ex:
            _log.debug("rotate_backups(): подавлено: %s", _ex)
    return removed


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
