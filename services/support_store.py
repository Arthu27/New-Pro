# -*- coding: utf-8 -*-
"""Хранилище отзывов и апелляций support-бота."""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from logger import get_logger

log = get_logger('support_store')

DATA = Path(os.environ.get('SUPPORT_DATA_DIR') or 'data')
REVIEWS = DATA / 'support_reviews.json'
APPEALS = DATA / 'support_appeals.json'


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
