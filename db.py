"""
Центральный Database Helper
Простой API перехода JSON -> DB для когов
"""
import copy
import sqlite3
import os
import json
import threading
import time
from typing import Any, Optional, Dict, List
from datetime import datetime

from config import Config
from logger import get_logger

log = get_logger("db_helper")

# Короткий read-through кэш: /modpanel и ACL дергают GuildData.get десятки
# раз за клик. Без кэша каждый вызов = новый sqlite3.connect (на Windows
# Defender это доли-секунды → Discord «не ответило вовремя»).
_GD_CACHE: Dict[tuple, tuple] = {}  # (ns, gid, key) -> (value, mono_ts)
_GD_CACHE_LOCK = threading.Lock()
_GD_CACHE_TTL = 15.0
_GD_CACHE_MAX = 4096
_MISSING = object()


def _gd_cache_get(ns: str, guild_id: int, key: str):
    ck = (ns, int(guild_id), str(key))
    now = time.monotonic()
    with _GD_CACHE_LOCK:
        hit = _GD_CACHE.get(ck)
        if not hit:
            return _MISSING
        val, ts = hit
        if now - ts > _GD_CACHE_TTL:
            _GD_CACHE.pop(ck, None)
            return _MISSING
        return copy.deepcopy(val) if isinstance(val, (dict, list)) else val


def _gd_cache_put(ns: str, guild_id: int, key: str, value: Any) -> None:
    ck = (ns, int(guild_id), str(key))
    stored = copy.deepcopy(value) if isinstance(value, (dict, list)) else value
    now = time.monotonic()
    with _GD_CACHE_LOCK:
        if len(_GD_CACHE) >= _GD_CACHE_MAX and ck not in _GD_CACHE:
            # вытесняем ~10% самых старых
            doomed = sorted(_GD_CACHE.items(), key=lambda kv: kv[1][1])[: max(1, _GD_CACHE_MAX // 10)]
            for k, _ in doomed:
                _GD_CACHE.pop(k, None)
        _GD_CACHE[ck] = (stored, now)


def _gd_cache_invalidate(ns: str, guild_id: int, key: Optional[str] = None) -> None:
    gid = int(guild_id)
    with _GD_CACHE_LOCK:
        if key is None:
            drop = [ck for ck in _GD_CACHE if ck[0] == ns and ck[1] == gid]
            for ck in drop:
                _GD_CACHE.pop(ck, None)
        else:
            _GD_CACHE.pop((ns, gid, str(key)), None)


def clear_guild_data_cache() -> None:
    """Сброс всего кэша (тесты / смена DB_PATH)."""
    with _GD_CACHE_LOCK:
        _GD_CACHE.clear()
    _reset_shared_conns()


# Персистентное соединение на поток. Раньше _conn() открывал НОВЫЙ
# sqlite3.connect + гонял PRAGMA на КАЖДЫЙ get/set — а /modpanel и ACL
# дёргают get десятки раз за клик, плюс каждый voice/join-ивент. Это
# забивало event loop → Discord «не ответило вовремя». Теперь коннект
# создаётся один раз на поток (WAL безопасен для параллельных писателей).
_TLOCAL = threading.local()


def _shared_conn(db_path: str) -> sqlite3.Connection:
    conns = getattr(_TLOCAL, 'conns', None)
    if conns is None:
        conns = {}
        _TLOCAL.conns = conns
    conn = conns.get(db_path)
    if conn is not None:
        return conn
    d = os.path.dirname(db_path)
    if d:
        os.makedirs(d, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=5.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA synchronous=NORMAL')
        conn.execute('PRAGMA temp_store=MEMORY')
        conn.execute('PRAGMA busy_timeout=5000')
    except Exception:
        pass
    conns[db_path] = conn
    return conn


def _reset_shared_conns() -> None:
    """Закрыть кэшированные коннекты этого потока (смена DB_PATH в тестах)."""
    conns = getattr(_TLOCAL, 'conns', None)
    if not conns:
        return
    for c in list(conns.values()):
        try:
            c.close()
        except Exception:
            pass
    _TLOCAL.conns = {}


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
        # Персистентный коннект на поток — без reconnect+PRAGMA на каждый вызов.
        return _shared_conn(self.db_path)
    
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
    
    def get(self, guild_id: int, key: str, default: Any = None) -> Any:
        """Чтение значения (с коротким TTL-кэшем)."""
        cached = _gd_cache_get(self.namespace, guild_id, key)
        if cached is not _MISSING:
            return default if cached is None else cached
        conn = self._conn()
        row = conn.execute(
            'SELECT value FROM guild_data WHERE namespace = ? AND guild_id = ? AND key = ?',
            (self.namespace, guild_id, str(key))
        ).fetchone()
        if row:
            try:
                value = json.loads(row['value'])
            except Exception:
                value = row['value']
            _gd_cache_put(self.namespace, guild_id, key, value)
            return value
        _gd_cache_put(self.namespace, guild_id, key, None)
        return default
    
    def set(self, guild_id: int, key: str, value: Any) -> bool:
        """Запись значения"""
        conn = self._conn()
        try:
            conn.execute(
                '''INSERT OR REPLACE INTO guild_data (namespace, guild_id, key, value, updated_at)
                   VALUES (?, ?, ?, ?, ?)''',
                (self.namespace, guild_id, str(key), json.dumps(value, ensure_ascii=False), datetime.now().isoformat())
            )
            conn.commit()
            _gd_cache_put(self.namespace, guild_id, key, value)
            return True
        except Exception as e:
            log.error(f"DB write error: {e}")
            _gd_cache_invalidate(self.namespace, guild_id, key)
            return False
    
    def delete(self, guild_id: int, key: str) -> bool:
        """Удаление значения"""
        conn = self._conn()
        try:
            conn.execute(
                'DELETE FROM guild_data WHERE namespace = ? AND guild_id = ? AND key = ?',
                (self.namespace, guild_id, str(key))
            )
            conn.commit()
            _gd_cache_invalidate(self.namespace, guild_id, key)
            return True
        except Exception as e:
            log.error(f"DB delete error: {e}")
            return False
    
    def get_all(self, guild_id: int) -> Dict[str, Any]:
        """Все данные гильдии"""
        conn = self._conn()
        rows = conn.execute(
            'SELECT key, value FROM guild_data WHERE namespace = ? AND guild_id = ?',
            (self.namespace, guild_id)
        ).fetchall()
        result = {}
        for row in rows:
            try:
                result[row['key']] = json.loads(row['value'])
            except Exception:
                result[row['key']] = row['value']
        return result
    
    def get_all_keys(self, guild_id: int) -> List[str]:
        """Все ключи гильдии"""
        conn = self._conn()
        rows = conn.execute(
            'SELECT key FROM guild_data WHERE namespace = ? AND guild_id = ?',
            (self.namespace, guild_id)
        ).fetchall()
        return [row['key'] for row in rows]
    
    def count(self, guild_id: int) -> int:
        """Количество записей"""
        conn = self._conn()
        row = conn.execute(
            'SELECT COUNT(*) as cnt FROM guild_data WHERE namespace = ? AND guild_id = ?',
            (self.namespace, guild_id)
        ).fetchone()
        return row['cnt'] if row else 0
    
    def exists(self, guild_id: int, key: str) -> bool:
        """Есть ли запись"""

        return self.get(guild_id, key) is not None
    
    def clear(self, guild_id: int) -> bool:
        """Удалить все данные гильдии"""
        conn = self._conn()
        try:
            conn.execute(
                'DELETE FROM guild_data WHERE namespace = ? AND guild_id = ?',
                (self.namespace, guild_id)
            )
            conn.commit()
            _gd_cache_invalidate(self.namespace, guild_id, None)
            return True
        except Exception as e:
            log.error(f"DB clear error: {e}")
            return False
    
    def migrate_from_json(self, json_path: str, guild_id: int):
        """Перенести данные из JSON-файла в БД"""
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
    Хранение данных по пользователям.
    
    Использование:
        db = UserData("economy")
        db.set(user_id, {"balance": 1000, "level": 5})
        data = db.get(user_id)
    """
    
    def __init__(self, namespace: str):
        self.namespace = namespace
        self.db_path = Config.DB_PATH
        self._ensure_table()
    
    def _conn(self):
        return _shared_conn(self.db_path)
    
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
    
    def get(self, user_id: int, default: Any = None) -> Any:
        conn = self._conn()
        row = conn.execute(
            'SELECT value FROM user_data WHERE namespace = ? AND user_id = ?',
            (self.namespace, user_id)
        ).fetchone()
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
    
    def get_all(self) -> Dict[int, Any]:
        """Все пользователи"""
        conn = self._conn()
        rows = conn.execute(
            'SELECT user_id, value FROM user_data WHERE namespace = ?',
            (self.namespace,)
        ).fetchall()
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
