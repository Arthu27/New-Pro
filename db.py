"""
Центральный Database Helper
Простой API перехода JSON -> DB для когов
"""
import sqlite3
import os
import json
from typing import Any, Optional, Dict, List
from datetime import datetime

from config import Config
from logger import get_logger

log = get_logger("db_helper")


class GuildData:
    """
    Простое key-value хранилище для каждого кога.
    Заменяет JSON-файлы.

    Использование:
        db = GuildData("economy")
        db.set(guild_id, user_id, {"balance": 1000})
        data = db.get(guild_id, user_id)
    """
    
    def __init__(self, namespace: str):
        self.namespace = namespace
        self.db_path = Config.DB_PATH
        self._ensure_table()
    
    def _conn(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _ensure_table(self):
        conn = self._conn()
        conn.execute('''
            CREATE TABLE IF NOT EXISTS guild_data (
                namespace TEXT NOT NULL,
                guild_id INTEGER NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (namespace, guild_id, key)
            )
        ''')
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_guild_data_ns_guild 
            ON guild_data(namespace, guild_id)
        ''')
        conn.commit()
        conn.close()
    
    def get(self, guild_id: int, key: str, default: Any = None) -> Any:
        """Veri oku"""
        conn = self._conn()
        row = conn.execute(
            'SELECT value FROM guild_data WHERE namespace = ? AND guild_id = ? AND key = ?',
            (self.namespace, guild_id, str(key))
        ).fetchone()
        conn.close()
        if row:
            try:
                return json.loads(row['value'])
            except Exception:
                return row['value']
        return default
    
    def set(self, guild_id: int, key: str, value: Any) -> bool:
        """Veri yaz"""
        conn = self._conn()
        try:
            conn.execute(
                '''INSERT OR REPLACE INTO guild_data (namespace, guild_id, key, value, updated_at)
                   VALUES (?, ?, ?, ?, ?)''',
                (self.namespace, guild_id, str(key), json.dumps(value, ensure_ascii=False), datetime.now().isoformat())
            )
            conn.commit()
            return True
        except Exception as e:
            log.error(f"DB write error: {e}")
            return False
        finally:
            conn.close()
    
    def delete(self, guild_id: int, key: str) -> bool:
        """Veri sil"""
        conn = self._conn()
        try:
            conn.execute(
                'DELETE FROM guild_data WHERE namespace = ? AND guild_id = ? AND key = ?',
                (self.namespace, guild_id, str(key))
            )
            conn.commit()
            return True
        except Exception as e:
            log.error(f"DB delete error: {e}")
            return False
        finally:
            conn.close()
    
    def get_all(self, guild_id: int) -> Dict[str, Any]:
        """Guild'in tum verilerini al"""
        conn = self._conn()
        rows = conn.execute(
            'SELECT key, value FROM guild_data WHERE namespace = ? AND guild_id = ?',
            (self.namespace, guild_id)
        ).fetchall()
        conn.close()
        result = {}
        for row in rows:
            try:
                result[row['key']] = json.loads(row['value'])
            except Exception:
                result[row['key']] = row['value']
        return result
    
    def get_all_keys(self, guild_id: int) -> List[str]:
        """Guild'in tum key'lerini al"""
        conn = self._conn()
        rows = conn.execute(
            'SELECT key FROM guild_data WHERE namespace = ? AND guild_id = ?',
            (self.namespace, guild_id)
        ).fetchall()
        conn.close()
        return [row['key'] for row in rows]
    
    def count(self, guild_id: int) -> int:
        """Kayit sayisi"""
        conn = self._conn()
        row = conn.execute(
            'SELECT COUNT(*) as cnt FROM guild_data WHERE namespace = ? AND guild_id = ?',
            (self.namespace, guild_id)
        ).fetchone()
        conn.close()
        return row['cnt'] if row else 0
    
    def exists(self, guild_id: int, key: str) -> bool:
        """Kayit var mi?"""
        return self.get(guild_id, key) is not None
    
    def clear(self, guild_id: int) -> bool:
        """Guild'in tum verilerini sil"""
        conn = self._conn()
        try:
            conn.execute(
                'DELETE FROM guild_data WHERE namespace = ? AND guild_id = ?',
                (self.namespace, guild_id)
            )
            conn.commit()
            return True
        except Exception as e:
            log.error(f"DB clear error: {e}")
            return False
        finally:
            conn.close()
    
    def migrate_from_json(self, json_path: str, guild_id: int):
        """JSON dosyasindan DB'ye tasi"""
        if not os.path.exists(json_path):
            return
        
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if isinstance(data, dict):
                for key, value in data.items():
                    self.set(guild_id, key, value)
                log.info(f"Migrated {len(data)} records from {json_path} to DB")
            else:
                self.set(guild_id, "data", data)
                log.info(f"Migrated data from {json_path} to DB")
        except Exception as e:
            log.error(f"Migration error: {e}")


class UserData:
    """
    Kullanici bazli veri saklama.
    
    Kullanim:
        db = UserData("economy")
        db.set(user_id, {"balance": 1000, "level": 5})
        data = db.get(user_id)
    """
    
    def __init__(self, namespace: str):
        self.namespace = namespace
        self.db_path = Config.DB_PATH
        self._ensure_table()
    
    def _conn(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _ensure_table(self):
        conn = self._conn()
        conn.execute('''
            CREATE TABLE IF NOT EXISTS user_data (
                namespace TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                value TEXT NOT NULL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (namespace, user_id)
            )
        ''')
        conn.commit()
        conn.close()
    
    def get(self, user_id: int, default: Any = None) -> Any:
        conn = self._conn()
        row = conn.execute(
            'SELECT value FROM user_data WHERE namespace = ? AND user_id = ?',
            (self.namespace, user_id)
        ).fetchone()
        conn.close()
        if row:
            try:
                return json.loads(row['value'])
            except Exception:
                return row['value']
        return default
    
    def set(self, user_id: int, value: Any) -> bool:
        conn = self._conn()
        try:
            conn.execute(
                '''INSERT OR REPLACE INTO user_data (namespace, user_id, value, updated_at)
                   VALUES (?, ?, ?, ?)''',
                (self.namespace, user_id, json.dumps(value, ensure_ascii=False), datetime.now().isoformat())
            )
            conn.commit()
            return True
        except Exception as e:
            log.error(f"DB write error: {e}")
            return False
        finally:
            conn.close()
    
    def delete(self, user_id: int) -> bool:
        conn = self._conn()
        try:
            conn.execute(
                'DELETE FROM user_data WHERE namespace = ? AND user_id = ?',
                (self.namespace, user_id)
            )
            conn.commit()
            return True
        except Exception as e:
            log.error(f"DB delete error: {e}")
            return False
        finally:
            conn.close()
    
    def get_all(self) -> Dict[int, Any]:
        """Tum kullanicilari al"""
        conn = self._conn()
        rows = conn.execute(
            'SELECT user_id, value FROM user_data WHERE namespace = ?',
            (self.namespace,)
        ).fetchall()
        conn.close()
        result = {}
        for row in rows:
            try:
                result[row['user_id']] = json.loads(row['value'])
            except Exception:
                result[row['user_id']] = row['value']
        return result
    
    def get_top(self, field: str, limit: int = 10) -> List[Dict]:
        """Leaderboard - belirtilen field'a gore sirala"""
        all_data = self.get_all()
        sorted_data = sorted(
            [(uid, data) for uid, data in all_data.items() if isinstance(data, dict) and field in data],
            key=lambda x: x[1].get(field, 0),
            reverse=True
        )
        return [{"user_id": uid, **data} for uid, data in sorted_data[:limit]]
