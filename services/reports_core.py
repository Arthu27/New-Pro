# -*- coding: utf-8 -*-
"""Ядро системы репортов: конфиг, тикеты, рецидивы, zlib-архив.

Хранение — SQLite (data/reports.db) и JSON-конфиг (data/reports_<gid>.json):
отдельно от основной базы бота, ничего не трогаем. Переписка тикета
сжимается zlib и кладётся блобом — как в ТЗ, только без PostgreSQL
(на Windows-VDS его нет, а данных репортов мизер).

Модуль чистый (без discord) — покрыт tests/test_reports_core.py.
"""
import json
import os
import sqlite3
import zlib
from datetime import datetime, timezone
from logger import get_logger
_log = get_logger(__name__)

DB_PATH = 'data/reports.db'

# Лестница рецидивов по умолчанию (ТЗ 6.2): 1-е — варн, 2-е — мут/день,
# 3-е — мут/неделя, 4-е — бан. Настраивается per-guild.
DEFAULT_LADDER = [
    {'n': 1, 'kind': 'warn', 'hours': 0, 'label': 'Предупреждение'},
    {'n': 2, 'kind': 'mute', 'hours': 24, 'label': 'Мут на 1 день'},
    {'n': 3, 'kind': 'mute', 'hours': 24 * 7, 'label': 'Мут на 1 неделю'},
    {'n': 4, 'kind': 'ban', 'hours': 0, 'label': 'Бан'},
]

KIND_LABELS = {
    'warn': 'Предупреждение',
    'mute': 'Мут',
    'kick': 'Кик',
    'ban': 'Бан',
    'none': 'Без наказания',
}

DURATIONS = [
    ('10 минут', 10 / 60),
    ('1 час', 1.0),
    ('1 день', 24.0),
    ('1 неделя', 24 * 7),
    ('Постоянно', 0),
]


def _now() -> float:
    return datetime.now(timezone.utc).timestamp()


# ── конфиг ──────────────────────────────────────────────────────────
def cfg_path(guild_id) -> str:
    return f'data/reports_{guild_id}.json'


def load_cfg(guild_id) -> dict:
    """Настройки репортов сервера: канал, роль модератора, лестница
    рецидивов и срок давности. Без файла — дефолты (канал не привязан)."""
    cfg = {'channel_id': '', 'mod_role_id': '', 'expiry_days': 90,
           'ladder': [dict(x) for x in DEFAULT_LADDER]}
    try:
        with open(cfg_path(guild_id), encoding='utf-8') as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            for k in ('channel_id', 'mod_role_id'):
                cfg[k] = str(raw.get(k) or '')
            if isinstance(raw.get('expiry_days'), int):
                cfg['expiry_days'] = max(1, raw['expiry_days'])
            if isinstance(raw.get('ladder'), list) and raw['ladder']:
                lad = []
                for step in raw['ladder']:
                    if isinstance(step, dict) and step.get('kind') in KIND_LABELS:
                        lad.append({'n': int(step.get('n') or len(lad) + 1),
                                    'kind': step['kind'],
                                    'hours': float(step.get('hours') or 0),
                                    'label': str(step.get('label') or KIND_LABELS[step['kind']])})
                if lad:
                    cfg['ladder'] = sorted(lad, key=lambda x: x['n'])
    except Exception as _sx1:
        _log.debug('подавлено: %s', _sx1)
    return cfg


def save_cfg(guild_id, cfg: dict) -> None:
    os.makedirs('data', exist_ok=True)
    with open(cfg_path(guild_id), 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


# ── база ────────────────────────────────────────────────────────────
def _db() -> sqlite3.Connection:
    os.makedirs('data', exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute("""CREATE TABLE IF NOT EXISTS tickets(
        guild TEXT, thread_id TEXT PRIMARY KEY, kind TEXT DEFAULT 'report',
        reporter_id TEXT, accused_id TEXT, witnesses TEXT DEFAULT '[]',
        mode TEXT DEFAULT 'wait', word_id TEXT DEFAULT '',
        verdict TEXT DEFAULT '', created REAL, closed REAL DEFAULT 0)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS violations(
        id INTEGER PRIMARY KEY AUTOINCREMENT, guild TEXT, user_id TEXT,
        kind TEXT, hours REAL, reason TEXT, thread_id TEXT, created REAL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS archive(
        guild TEXT, thread_id TEXT, blob BLOB, meta TEXT,
        created REAL, PRIMARY KEY(guild, thread_id))""")
    conn.commit()
    return conn


def db() -> sqlite3.Connection:
    return _db()


# ── тикеты ──────────────────────────────────────────────────────────
def ticket_create(guild_id, thread_id, reporter_id, accused_id,
                  kind: str = 'report') -> None:
    with db() as c:
        c.execute("""INSERT OR REPLACE INTO tickets
            (guild, thread_id, kind, reporter_id, accused_id, created)
            VALUES (?,?,?,?,?,?)""",
                  (str(guild_id), str(thread_id), kind,
                   str(reporter_id), str(accused_id), _now()))


def ticket_get(thread_id) -> dict | None:
    with db() as c:
        row = c.execute("""SELECT guild, thread_id, kind, reporter_id, accused_id,
            witnesses, mode, word_id, verdict, created, closed
            FROM tickets WHERE thread_id=?""", (str(thread_id),)).fetchone()
    if not row:
        return None
    keys = ('guild', 'thread_id', 'kind', 'reporter_id', 'accused_id',
            'witnesses', 'mode', 'word_id', 'verdict', 'created', 'closed')
    t = dict(zip(keys, row))
    try:
        t['witnesses'] = json.loads(t['witnesses'] or '[]')
    except Exception:
        t['witnesses'] = []
    return t


def ticket_list(guild_id, limit: int = 200) -> list:
    """Тикеты сервера, свежие сверху — для панели (очередь репортов)."""
    with db() as c:
        rows = c.execute("""SELECT thread_id, kind, reporter_id, accused_id,
            verdict, created, closed FROM tickets
            WHERE guild=? ORDER BY created DESC LIMIT ?""",
                         (str(guild_id), int(limit))).fetchall()
    out = []
    for r in rows:
        out.append({'thread_id': r[0], 'kind': r[1], 'reporter_id': r[2],
                    'accused_id': r[3], 'verdict': r[4] or '',
                    'created': float(r[5] or 0),
                    'closed': float(r[6] or 0) if r[6] else None})
    return out


def ticket_stats(guild_id) -> dict:
    """Сводка очереди: открыто / закрыто за 7 дней / всего."""
    now = _now()
    with db() as c:
        row = c.execute("""SELECT
            SUM(CASE WHEN closed IS NULL OR closed=0 THEN 1 ELSE 0 END),
            SUM(CASE WHEN closed IS NOT NULL AND closed>0 AND closed>=?
                 THEN 1 ELSE 0 END),
            COUNT(*) FROM tickets WHERE guild=?""",
                        (now - 7 * 86400, str(guild_id))).fetchone()
    return {'open': int(row[0] or 0), 'closed_week': int(row[1] or 0),
            'total': int(row[2] or 0)}


def ticket_set(thread_id, **kv) -> None:
    if not kv:
        return
    cols = ', '.join(f'{k}=?' for k in kv)
    with db() as c:
        c.execute(f'UPDATE tickets SET {cols} WHERE thread_id=?',
                  (*kv.values(), str(thread_id)))


def add_witness(thread_id, user_id) -> None:
    t = ticket_get(thread_id)
    if not t or str(user_id) in t['witnesses']:
        return
    t['witnesses'].append(str(user_id))
    ticket_set(thread_id, witnesses=json.dumps(t['witnesses']))


# ── нарушения и рецидивы ────────────────────────────────────────────
def add_violation(guild_id, user_id, kind: str, hours: float,
                  reason: str, thread_id='') -> int:
    with db() as c:
        cur = c.execute("""INSERT INTO violations
            (guild, user_id, kind, hours, reason, thread_id, created)
            VALUES (?,?,?,?,?,?,?)""",
                        (str(guild_id), str(user_id), kind, float(hours or 0),
                         str(reason or ''), str(thread_id), _now()))
        return int(cur.lastrowid)


def violations_of(guild_id, user_id, expiry_days: int = 90) -> list:
    """Нарушения пользователя в пределах срока давности (6.3)."""
    horizon = _now() - max(1, expiry_days) * 86400
    with db() as c:
        rows = c.execute("""SELECT id, kind, hours, reason, thread_id, created
            FROM violations WHERE guild=? AND user_id=? AND created>=?
            ORDER BY created""", (str(guild_id), str(user_id), horizon)).fetchall()
    return [dict(zip(('id', 'kind', 'hours', 'reason', 'thread_id', 'created'), r))
            for r in rows]


def compute_default(ladder, count: int) -> dict:
    """Дефолтное наказание по числу нарушений (ТЗ 4.3): последний шаг,
    чей порог n <= count; count выше максимального — самый строгий шаг."""
    lad = sorted((ladder or DEFAULT_LADDER), key=lambda x: x['n'])
    step = lad[0]
    for s in lad:
        if count >= s['n']:
            step = s
    return dict(step)


def remove_violation(violation_id: int) -> None:
    with db() as c:
        c.execute('DELETE FROM violations WHERE id=?', (int(violation_id),))


# ── архив переписки (zlib) ──────────────────────────────────────────
def pack_messages(messages: list) -> bytes:
    """Сжать переписку: [(author, author_id, ts, content), ...] -> zlib."""
    raw = json.dumps(messages, ensure_ascii=False).encode('utf-8')
    return zlib.compress(raw, 9)


def unpack_messages(blob: bytes) -> list:
    return json.loads(zlib.decompress(bytes(blob)).decode('utf-8'))


def archive_save(guild_id, thread_id, messages: list, meta: dict) -> int:
    blob = pack_messages(messages)
    with db() as c:
        c.execute("""INSERT OR REPLACE INTO archive
            (guild, thread_id, blob, meta, created) VALUES (?,?,?,?,?)""",
                  (str(guild_id), str(thread_id), blob,
                   json.dumps(meta, ensure_ascii=False), _now()))
    return len(blob)


def archive_load(guild_id, thread_id) -> list:
    with db() as c:
        row = c.execute('SELECT blob FROM archive WHERE guild=? AND thread_id=?',
                        (str(guild_id), str(thread_id))).fetchone()
    return unpack_messages(row[0]) if row else []
