# -*- coding: utf-8 -*-
"""Хранилище отзывов, апелляций, нормы и топов support-бота."""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from logger import get_logger

log = get_logger('support_store')

DATA = Path(os.environ.get('SUPPORT_DATA_DIR') or 'data')
REVIEWS = DATA / 'support_reviews.json'
APPEALS = DATA / 'support_appeals.json'
STATS = DATA / 'support_stats.json'
PENDING_REVIEWS = DATA / 'support_pending_reviews.json'


def _load(path: Path) -> dict:
    try:
        if path.is_file():
            data = json.loads(path.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                return data
    except Exception as ex:
        log.warning('support_store load %s: %s', path, ex)
    return {'items': []}


def _save(path: Path, data: dict) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)


def add_review(*, guild_id: int, user_id: int, support_id: int,
               text: str, message_id: int | None = None) -> dict:
    data = _load(REVIEWS)
    item = {
        'id': uuid.uuid4().hex[:12],
        'guild_id': str(guild_id),
        'user_id': str(user_id),
        'support_id': str(support_id),
        'text': str(text or '')[:500],
        'message_id': str(message_id or ''),
        'ts': time.time(),
    }
    data.setdefault('items', []).append(item)
    _save(REVIEWS, data)
    return item


def add_appeal(*, guild_id: int, user_id: int, support_id: int,
               reason: str, message_id: int | None = None) -> dict:
    data = _load(APPEALS)
    item = {
        'id': uuid.uuid4().hex[:12],
        'guild_id': str(guild_id),
        'user_id': str(user_id),
        'support_id': str(support_id),
        'reason': str(reason or '')[:1000],
        'status': 'pending',
        'message_id': str(message_id or ''),
        'ts': time.time(),
    }
    data.setdefault('items', []).append(item)
    _save(APPEALS, data)
    return item


def set_appeal_status(appeal_id: str, status: str,
                      reviewer_id: int | None = None) -> dict | None:
    data = _load(APPEALS)
    for it in data.get('items') or []:
        if it.get('id') == appeal_id:
            it['status'] = status
            it['reviewer_id'] = str(reviewer_id or '')
            it['resolved_ts'] = time.time()
            _save(APPEALS, data)
            return it
    return None


def get_appeal(appeal_id: str) -> dict | None:
    data = _load(APPEALS)
    for it in data.get('items') or []:
        if it.get('id') == appeal_id:
            return it
    return None


def list_appeals_for_user(guild_id: int, user_id: int) -> list[dict]:
    out = []
    for it in _load(APPEALS).get('items') or []:
        if int(it.get('guild_id') or 0) == int(guild_id) and int(it.get('user_id') or 0) == int(user_id):
            out.append(it)
    return out


def deny_count(guild_id: int, user_id: int) -> int:
    n = 0
    for it in list_appeals_for_user(guild_id, user_id):
        # count any deny-related appeal or we track denials separately
        n += 1
    # also from stats denials
    st = _stats_row(guild_id, user_id)
    return int(st.get('denials') or 0) or n


def _stats_root() -> dict:
    data = _load(STATS)
    if not isinstance(data.get('guilds'), dict):
        data = {'guilds': {}}
    return data


def _mut_row(data: dict, guild_id: int, user_id: int) -> dict:
    g = data.setdefault('guilds', {}).setdefault(str(int(guild_id)), {})
    users = g.setdefault('users', {})
    return users.setdefault(str(int(user_id)), {
        'verifies': 0,
        'denials': 0,
        'rejoins': 0,
        'last_deny_reason': '',
        'voice_seconds': 0.0,
        'daily': {},
    })


def _save_stats(data: dict) -> None:
    _save(STATS, data)


def bump_verify(guild_id: int, support_id: int) -> None:
    data = _stats_root()
    row = _mut_row(data, guild_id, support_id)
    row['verifies'] = int(row.get('verifies') or 0) + 1
    day = time.strftime('%Y-%m-%d', time.gmtime())
    daily = row.setdefault('daily', {})
    daily[day] = int(daily.get(day) or 0) + 1
    _save_stats(data)


def bump_denial(guild_id: int, target_id: int, reason: str = '') -> None:
    data = _stats_root()
    row = _mut_row(data, guild_id, target_id)
    row['denials'] = int(row.get('denials') or 0) + 1
    if reason:
        row['last_deny_reason'] = str(reason)[:200]
    _save_stats(data)


def bump_rejoin(guild_id: int, user_id: int) -> None:
    data = _stats_root()
    row = _mut_row(data, guild_id, user_id)
    row['rejoins'] = int(row.get('rejoins') or 0) + 1
    _save_stats(data)


def add_voice_seconds(guild_id: int, user_id: int, seconds: float) -> None:
    if seconds <= 0:
        return
    data = _stats_root()
    row = _mut_row(data, guild_id, user_id)
    row['voice_seconds'] = float(row.get('voice_seconds') or 0) + float(seconds)
    _save_stats(data)


def get_user_meta(guild_id: int, user_id: int) -> dict:
    data = _stats_root()
    row = _mut_row(data, guild_id, user_id)
    return {
        'denials': int(row.get('denials') or 0),
        'rejoins': int(row.get('rejoins') or 0),
        'last_deny_reason': str(row.get('last_deny_reason') or ''),
        'verifies': int(row.get('verifies') or 0),
        'voice_seconds': float(row.get('voice_seconds') or 0),
        'daily': dict(row.get('daily') or {}),
    }


def daily_verifies(guild_id: int, support_id: int, day: str | None = None) -> int:
    day = day or time.strftime('%Y-%m-%d', time.gmtime())
    data = _stats_root()
    row = _mut_row(data, guild_id, support_id)
    return int((row.get('daily') or {}).get(day) or 0)


def top_support(guild_id: int, limit: int = 15) -> list[dict]:
    data = _stats_root()
    users = (data.get('guilds') or {}).get(str(int(guild_id)), {}).get('users') or {}
    rows = []
    for uid, row in users.items():
        v = int(row.get('verifies') or 0)
        if v <= 0:
            continue
        rows.append({'user_id': int(uid), 'verifies': v})
    rows.sort(key=lambda r: r['verifies'], reverse=True)
    return rows[:limit]


def top_online(guild_id: int, limit: int = 15) -> list[dict]:
    data = _stats_root()
    users = (data.get('guilds') or {}).get(str(int(guild_id)), {}).get('users') or {}
    rows = []
    for uid, row in users.items():
        sec = float(row.get('voice_seconds') or 0)
        if sec <= 0:
            continue
        rows.append({'user_id': int(uid), 'seconds': sec})
    rows.sort(key=lambda r: r['seconds'], reverse=True)
    return rows[:limit]


def set_pending_review(*, user_id: int, support_id: int, guild_id: int,
                       expires_at: float) -> None:
    data = _load(PENDING_REVIEWS)
    items = [x for x in (data.get('items') or []) if str(x.get('user_id')) != str(user_id)]
    items.append({
        'user_id': str(user_id),
        'support_id': str(support_id),
        'guild_id': str(guild_id),
        'expires_at': float(expires_at),
    })
    data['items'] = items
    _save(PENDING_REVIEWS, data)


def pop_pending_review(user_id: int) -> Optional[dict]:
    data = _load(PENDING_REVIEWS)
    now = time.time()
    found = None
    keep = []
    for it in data.get('items') or []:
        if str(it.get('user_id')) == str(user_id) and float(it.get('expires_at') or 0) >= now:
            found = it
        elif float(it.get('expires_at') or 0) >= now:
            keep.append(it)
    data['items'] = keep
    _save(PENDING_REVIEWS, data)
    return found
