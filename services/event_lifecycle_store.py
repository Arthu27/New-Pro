# -*- coding: utf-8 -*-
"""Persist events / signups / attendance / organizer stats for /eventstart."""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from logger import get_logger

log = get_logger('event_lifecycle_store')

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get('EVENT_LIFECYCLE_DATA') or (ROOT / 'data'))
EVENTS = DATA / 'event_lifecycle_events.json'
STATS = DATA / 'event_lifecycle_stats.json'


def _load(path: Path) -> dict:
    try:
        if path.is_file():
            data = json.loads(path.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                return data
    except Exception as ex:
        log.warning('load %s: %s', path, ex)
    return {'items': []}


def _save(path: Path, data: dict) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    tmp.replace(path)


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def create_event(**fields) -> dict:
    data = _load(EVENTS)
    item = {
        'id': new_id(),
        'created_at': time.time(),
        'status': 'scheduled',  # scheduled|cancelled|finished
        'signups': [],
        'voice_seconds': {},  # uid -> seconds in event voice
        'reminded_1h': False,
        'reminded_10m': False,
        **fields,
    }
    data.setdefault('items', []).append(item)
    _save(EVENTS, data)
    return item


def update_event(event_id: str, **fields) -> Optional[dict]:
    data = _load(EVENTS)
    for it in data.get('items') or []:
        if it.get('id') == event_id:
            it.update(fields)
            _save(EVENTS, data)
            return it
    return None


def get_event(event_id: str) -> Optional[dict]:
    for it in (_load(EVENTS).get('items') or []):
        if it.get('id') == event_id:
            return it
    return None


def list_events(guild_id: int | None = None, status: str | None = None) -> list[dict]:
    out = []
    for it in _load(EVENTS).get('items') or []:
        if guild_id is not None and int(it.get('guild_id') or 0) != int(guild_id):
            continue
        if status is not None and it.get('status') != status:
            continue
        out.append(it)
    return out


def add_signup(event_id: str, user_id: int) -> tuple[Optional[dict], str]:
    """Returns (event, reason) reason=ok|dup|closed|full|missing."""
    data = _load(EVENTS)
    for it in data.get('items') or []:
        if it.get('id') != event_id:
            continue
        if it.get('status') != 'scheduled':
            return it, 'closed'
        signups = list(it.get('signups') or [])
        uid = str(int(user_id))
        if uid in signups:
            return it, 'dup'
        limit = int(it.get('max_participants') or 0)
        if limit > 0 and len(signups) >= limit:
            return it, 'full'
        signups.append(uid)
        it['signups'] = signups
        _save(EVENTS, data)
        return it, 'ok'
    return None, 'missing'


def remove_signup(event_id: str, user_id: int) -> tuple[Optional[dict], str]:
    data = _load(EVENTS)
    for it in data.get('items') or []:
        if it.get('id') != event_id:
            continue
        uid = str(int(user_id))
        signups = list(it.get('signups') or [])
        if uid not in signups:
            return it, 'missing_user'
        signups = [x for x in signups if x != uid]
        it['signups'] = signups
        _save(EVENTS, data)
        return it, 'ok'
    return None, 'missing'


def add_voice_seconds(event_id: str, user_id: int, seconds: float) -> None:
    if seconds <= 0:
        return
    data = _load(EVENTS)
    for it in data.get('items') or []:
        if it.get('id') != event_id:
            continue
        vs = dict(it.get('voice_seconds') or {})
        uid = str(int(user_id))
        vs[uid] = float(vs.get(uid) or 0) + float(seconds)
        it['voice_seconds'] = vs
        _save(EVENTS, data)
        return


def record_organizer_finish(guild_id: int, organizer_id: int, event_id: str) -> None:
    data = _load(STATS)
    key = str(int(guild_id))
    g = data.setdefault(key, {'organizers': {}})
    org = g.setdefault('organizers', {})
    oid = str(int(organizer_id))
    row = org.setdefault(oid, {'events': []})
    row['events'].append({'id': event_id, 'ts': time.time()})
    # keep last 200
    row['events'] = row['events'][-200:]
    _save(STATS, data)


def organizer_counts(guild_id: int, *, week: bool = True, month: bool = True) -> list[dict]:
    data = _load(STATS)
    g = data.get(str(int(guild_id))) or {}
    org = g.get('organizers') or {}
    now = time.time()
    week_ago = now - 7 * 86400
    month_ago = now - 30 * 86400
    rows = []
    for oid, row in org.items():
        evs = row.get('events') or []
        w = sum(1 for e in evs if float(e.get('ts') or 0) >= week_ago)
        m = sum(1 for e in evs if float(e.get('ts') or 0) >= month_ago)
        rows.append({'organizer_id': int(oid), 'week': w, 'month': m, 'total': len(evs)})
    rows.sort(key=lambda r: (r['week'], r['month'], r['total']), reverse=True)
    return rows


def attendance_summary(event: dict, min_seconds: int = 600) -> dict[str, Any]:
    signups = [str(x) for x in (event.get('signups') or [])]
    vs = event.get('voice_seconds') or {}
    came, no_show = [], []
    for uid in signups:
        if float(vs.get(uid) or 0) >= float(min_seconds):
            came.append(uid)
        else:
            no_show.append(uid)
    return {
        'registered': len(signups),
        'came': len(came),
        'no_show': len(no_show),
        'came_ids': came,
        'no_show_ids': no_show,
    }
