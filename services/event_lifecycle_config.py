# -*- coding: utf-8 -*-
"""Config for event lifecycle (/eventstart)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from logger import get_logger

log = get_logger('event_lifecycle_config')
ROOT = Path(__file__).resolve().parents[1]
CFG_PATH = ROOT / 'config' / 'event_lifecycle.json'

_DEFAULT = {
    'guild_id': '793336829280780331',
    'event_mod_role_id': '852634463535759461',
    'event_admin_role_id': '1551527644326002748',
    'announce_role_id': '852634463535759461',
    'announce_channel_id': '0',
    'events_category_id': '0',
    'create_missing': True,
    'remind_hours': 1,
    'remind_minutes': 10,
    'min_attend_seconds': 600,
    'templates': {},
}

_ENV = {
    'EVENT_LIFECYCLE_GUILD_ID': 'guild_id',
    'EVENT_MOD_ROLE_ID': 'event_mod_role_id',
    'EVENT_ADMIN_ROLE_ID': 'event_admin_role_id',
    'EVENT_ANNOUNCE_ROLE_ID': 'announce_role_id',
    'EVENT_ANNOUNCE_CHANNEL_ID': 'announce_channel_id',
    'EVENT_CATEGORY_ID': 'events_category_id',
}


def load_config() -> dict[str, Any]:
    cfg = dict(_DEFAULT)
    try:
        if CFG_PATH.is_file():
            raw = json.loads(CFG_PATH.read_text(encoding='utf-8'))
            if isinstance(raw, dict):
                cfg.update({k: raw[k] for k in cfg if k in raw})
                if isinstance(raw.get('templates'), dict):
                    cfg['templates'] = dict(raw['templates'])
    except Exception as ex:
        log.warning('lifecycle cfg: %s', ex)
    for ek, ck in _ENV.items():
        v = (os.environ.get(ek) or '').strip()
        if v:
            cfg[ck] = v
    cfg['create_missing'] = str(cfg.get('create_missing', True)).lower() not in (
        '0', 'false', 'no', '')
    for k in ('remind_hours', 'remind_minutes', 'min_attend_seconds'):
        try:
            cfg[k] = int(cfg.get(k) or _DEFAULT[k])
        except (TypeError, ValueError):
            cfg[k] = _DEFAULT[k]
    return cfg


def save_config(cfg: dict) -> None:
    CFG_PATH.parent.mkdir(parents=True, exist_ok=True)
    out = {k: cfg.get(k, _DEFAULT.get(k)) for k in _DEFAULT}
    tmp = CFG_PATH.with_suffix('.tmp')
    tmp.write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    tmp.replace(CFG_PATH)


def iid(cfg: dict, key: str) -> int:
    try:
        return int(str(cfg.get(key) or '0').strip() or 0)
    except (TypeError, ValueError):
        return 0
