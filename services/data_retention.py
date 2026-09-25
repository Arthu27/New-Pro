# -*- coding: utf-8 -*-
"""Хранение данных модерации: последние 14 дней.

Владелец 2026-09-25: апелляции / репорты / наказания — только за 2 недели.
Открытые (pending/active) записи НЕ удаляем, даже если старше 14 дней.

Что чистится
------------
1. GuildData('appeals') → state.items
   — удаляются accepted / rejected / closed старше RETENTION_DAYS;
   — pending остаются.
2. data/reports.db
   — tickets: закрытые (closed>0) старше cutoff;
   — violations: created старше cutoff;
   — archive: created старше cutoff.
3. GuildData('warnings') — записи с timestamp старше cutoff (per user list).
4. data/temp_history.json — записи с ts старше cutoff.
5. data/audit_log.json — события с timestamp старше cutoff (по гильдиям).

Не трогаем: активные temp_mutes/bans/vmutes, настройки, role_map, channel_routes.

Запуск: run_retention(dry_run=False) из appeals.on_ready и суточного цикла.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from logger import get_logger

_log = get_logger('data_retention')

UTC = timezone.utc
RETENTION_DAYS = 14
REPORTS_DB = 'data/reports.db'
TEMP_HISTORY = 'data/temp_history.json'
AUDIT_LOG = 'data/audit_log.json'


def retention_days() -> int:
    raw = (os.getenv('DATA_RETENTION_DAYS') or str(RETENTION_DAYS)).strip()
    try:
        return max(1, min(int(raw), 3650))
    except (TypeError, ValueError):
        return RETENTION_DAYS


def cutoff_dt(days: int | None = None) -> datetime:
    return datetime.now(UTC) - timedelta(days=int(days or retention_days()))


def cutoff_ts(days: int | None = None) -> float:
    return cutoff_dt(days).timestamp()


def _parse_iso(raw) -> datetime | None:
    if not raw:
        return None
    try:
        s = str(raw).strip().replace('Z', '+00:00')
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except (TypeError, ValueError):
        return None


def _guild_ids(namespace: str) -> list[int]:
    """Все guild_id в GuildData для namespace."""
    try:
        from config import Config
        from db import _shared_conn
        conn = _shared_conn(Config.DB_PATH)
        rows = conn.execute(
            'SELECT DISTINCT guild_id FROM guild_data WHERE namespace = ?',
            (namespace,),
        ).fetchall()
        out = []
        for r in rows:
            try:
                out.append(int(r['guild_id'] if hasattr(r, 'keys') else r[0]))
            except (TypeError, ValueError, KeyError):
                continue
        return out
    except Exception as _ex:
        _log.debug('guild_ids(%s): %s', namespace, _ex)
        return []


def purge_appeals(days: int | None = None, *, dry_run: bool = False) -> dict:
    """Удалить закрытые апелляции старше cutoff. Pending не трогаем."""
    from db import GuildData

    edge = cutoff_dt(days)
    db = GuildData('appeals')
    removed = 0
    kept_open = 0
    guilds = 0
    for gid in _guild_ids('appeals'):
        state = db.get(gid, 'state', None)
        if not isinstance(state, dict):
            continue
        items = list(state.get('items') or [])
        if not items:
            continue
        guilds += 1
        keep = []
        for item in items:
            if not isinstance(item, dict):
                continue
            status = str(item.get('status') or '')
            created = (_parse_iso(item.get('reviewed_at'))
                       or _parse_iso(item.get('created_at')))
            if status == 'pending':
                keep.append(item)
                kept_open += 1
                continue
            if status in ('accepted', 'rejected', 'closed') and created is not None:
                if created < edge:
                    removed += 1
                    continue
            keep.append(item)
        if len(keep) != len(items) and not dry_run:
            state['items'] = keep
            db.set(gid, 'state', state)
    return {
        'store': 'GuildData(appeals).state.items',
        'removed': removed,
        'kept_open': kept_open,
        'guilds': guilds,
        'dry_run': dry_run,
    }


def purge_reports_db(days: int | None = None, *, dry_run: bool = False) -> dict:
    """Закрытые тикеты / старые violations / archive в data/reports.db."""
    edge = cutoff_ts(days)
    path = REPORTS_DB
    stats = {
        'store': path,
        'tickets': 0,
        'violations': 0,
        'archive': 0,
        'dry_run': dry_run,
    }
    if not os.path.exists(path):
        return stats
    try:
        conn = sqlite3.connect(path, timeout=10)
        conn.execute('PRAGMA journal_mode=WAL')
        if dry_run:
            stats['tickets'] = int(conn.execute(
                """SELECT COUNT(*) FROM tickets
                   WHERE closed IS NOT NULL AND closed > 0 AND closed < ?""",
                (edge,)).fetchone()[0] or 0)
            stats['violations'] = int(conn.execute(
                'SELECT COUNT(*) FROM violations WHERE created < ?',
                (edge,)).fetchone()[0] or 0)
            stats['archive'] = int(conn.execute(
                'SELECT COUNT(*) FROM archive WHERE created < ?',
                (edge,)).fetchone()[0] or 0)
        else:
            cur = conn.execute(
                """DELETE FROM tickets
                   WHERE closed IS NOT NULL AND closed > 0 AND closed < ?""",
                (edge,))
            stats['tickets'] = int(cur.rowcount or 0)
            cur = conn.execute(
                'DELETE FROM violations WHERE created < ?', (edge,))
            stats['violations'] = int(cur.rowcount or 0)
            cur = conn.execute(
                'DELETE FROM archive WHERE created < ?', (edge,))
            stats['archive'] = int(cur.rowcount or 0)
            conn.commit()
        conn.close()
    except Exception as _ex:
        _log.warning('purge_reports_db: %s', _ex)
        stats['error'] = str(_ex)
    return stats


def purge_warnings(days: int | None = None, *, dry_run: bool = False) -> dict:
    """GuildData('warnings'): списки варнов по user_id, режем по timestamp."""
    from db import GuildData

    edge = cutoff_dt(days)
    db = GuildData('warnings')
    removed = 0
    users = 0
    for gid in _guild_ids('warnings'):
        all_keys = db.get_all(gid) or {}
        for key, warns in list(all_keys.items()):
            if not isinstance(warns, list):
                continue
            users += 1
            keep = []
            for w in warns:
                if not isinstance(w, dict):
                    continue
                ts = _parse_iso(w.get('timestamp') or w.get('created_at'))
                if ts is not None and ts < edge:
                    removed += 1
                    continue
                keep.append(w)
            if len(keep) != len(warns) and not dry_run:
                db.set(gid, key, keep)
    return {
        'store': 'GuildData(warnings)',
        'removed': removed,
        'users': users,
        'dry_run': dry_run,
    }


def purge_temp_history(days: int | None = None, *, dry_run: bool = False) -> dict:
    """data/temp_history.json — история мутов/банов (не активные сроки)."""
    path = TEMP_HISTORY
    stats = {'store': path, 'removed': 0, 'kept': 0, 'dry_run': dry_run}
    if not os.path.exists(path):
        return stats
    try:
        with open(path, 'r', encoding='utf-8') as f:
            history = json.load(f)
        if not isinstance(history, list):
            return stats
        edge = cutoff_ts(days)
        keep = []
        for h in history:
            if not isinstance(h, dict):
                continue
            ts = h.get('ts')
            try:
                ts_f = float(ts)
            except (TypeError, ValueError):
                keep.append(h)
                continue
            if ts_f < edge:
                stats['removed'] += 1
            else:
                keep.append(h)
        stats['kept'] = len(keep)
        if stats['removed'] and not dry_run:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(keep, f, ensure_ascii=False, indent=2)
    except Exception as _ex:
        _log.warning('purge_temp_history: %s', _ex)
        stats['error'] = str(_ex)
    return stats


def purge_audit_log(days: int | None = None, *, dry_run: bool = False) -> dict:
    """data/audit_log.json — события модерации по гильдиям."""
    path = AUDIT_LOG
    stats = {'store': path, 'removed': 0, 'kept': 0, 'dry_run': dry_run}
    if not os.path.exists(path):
        return stats
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return stats
        edge = cutoff_dt(days)
        changed = False
        for gid, events in list(data.items()):
            if not isinstance(events, list):
                continue
            keep = []
            for ev in events:
                if not isinstance(ev, dict):
                    continue
                ts = _parse_iso(ev.get('timestamp') or ev.get('created_at'))
                if ts is not None and ts < edge:
                    stats['removed'] += 1
                    changed = True
                    continue
                keep.append(ev)
                stats['kept'] += 1
            data[gid] = keep
        if changed and not dry_run:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as _ex:
        _log.warning('purge_audit_log: %s', _ex)
        stats['error'] = str(_ex)
    return stats


def run_retention(*, dry_run: bool = False, days: int | None = None) -> dict:
    """Полный прогон. Логирует сводку."""
    d = days if days is not None else retention_days()
    started = time.time()
    report: dict[str, Any] = {
        'days': d,
        'dry_run': dry_run,
        'cutoff': cutoff_dt(d).isoformat(),
        'parts': {},
    }
    for name, fn in (
        ('appeals', purge_appeals),
        ('reports_db', purge_reports_db),
        ('warnings', purge_warnings),
        ('temp_history', purge_temp_history),
        ('audit_log', purge_audit_log),
    ):
        try:
            report['parts'][name] = fn(d, dry_run=dry_run)
        except Exception as _ex:
            _log.warning('retention %s: %s', name, _ex)
            report['parts'][name] = {'error': str(_ex)}
    report['elapsed_sec'] = round(time.time() - started, 3)
    mode = 'DRY-RUN' if dry_run else 'APPLY'
    _log.info(
        'data_retention [%s] days=%s cutoff=%s → %s (%.2fs)',
        mode, d, report['cutoff'],
        {k: {kk: vv for kk, vv in (v or {}).items()
             if kk not in ('store',) or True}
         for k, v in report['parts'].items()},
        report['elapsed_sec'],
    )
    return report
