# -*- coding: utf-8 -*-
"""Конфиг support-бота (/verify): JSON + env overrides."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from logger import get_logger

log = get_logger('support_bot_config')

ROOT = Path(__file__).resolve().parents[1]
CFG_PATH = ROOT / 'config' / 'support_bot.json'

_DEFAULT = {
    'guild_id': '793336829280780331',
    'support_role_id': '1553138713532563516',
    'support_lead_role_id': '1553139245735219390',
    'male_role_id': '804361264641474602',  # cat
    'female_role_id': '804361268017627156',  # kitty
    'unverify_role_id': '0',
    'nedopusk_role_id': '0',
    'reviews_channel_id': '0',
    'appeals_channel_id': '0',
    'staff_log_category_id': '1312411839182672015',
    'create_missing': True,
    'review_max_chars': 140,
    'review_window_seconds': 300,  # 5 минут на отзыв в ЛС
    'daily_norma': 10,
}

_ENV_MAP = {
    'SUPPORT_GUILD_ID': 'guild_id',
    'SUPPORT_ROLE_ID': 'support_role_id',
    'SUPPORT_LEAD_ROLE_ID': 'support_lead_role_id',
    'SUPPORT_MALE_ROLE_ID': 'male_role_id',
    'SUPPORT_FEMALE_ROLE_ID': 'female_role_id',
    'SUPPORT_UNVERIFY_ROLE_ID': 'unverify_role_id',
    'SUPPORT_NEDOPUSK_ROLE_ID': 'nedopusk_role_id',
    'SUPPORT_REVIEWS_CHANNEL_ID': 'reviews_channel_id',
    'SUPPORT_APPEALS_CHANNEL_ID': 'appeals_channel_id',
}


def _sid(v) -> str:
    return str(v or '').strip()


def _iid(v) -> int:
    try:
        return int(str(v or '0').strip() or 0)
    except (TypeError, ValueError):
        return 0


def load_config() -> dict[str, Any]:
    cfg = dict(_DEFAULT)
    try:
        if CFG_PATH.is_file():
            data = json.loads(CFG_PATH.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                cfg.update({k: data[k] for k in cfg if k in data})
    except Exception as ex:
        log.warning('support config load: %s', ex)
    for env_k, cfg_k in _ENV_MAP.items():
        raw = (os.environ.get(env_k) or '').strip()
        if raw:
            cfg[cfg_k] = raw
    cfg['create_missing'] = str(cfg.get('create_missing', True)).lower() not in (
        '0', 'false', 'no', '')
    try:
        cfg['review_max_chars'] = max(20, min(500, int(cfg.get('review_max_chars', 140))))
    except (TypeError, ValueError):
        cfg['review_max_chars'] = 140
    try:
        cfg['review_window_seconds'] = max(60, min(3600, int(cfg.get('review_window_seconds', 300))))
    except (TypeError, ValueError):
        cfg['review_window_seconds'] = 300
    try:
        cfg['daily_norma'] = max(1, min(100, int(cfg.get('daily_norma', 10))))
    except (TypeError, ValueError):
        cfg['daily_norma'] = 10
    return cfg


def save_config(cfg: dict) -> None:
    CFG_PATH.parent.mkdir(parents=True, exist_ok=True)
    out = {k: cfg.get(k, _DEFAULT.get(k)) for k in _DEFAULT}
    # keep note if present
    if 'note' in cfg:
        out['note'] = cfg.get('note')
    tmp = CFG_PATH.with_suffix('.tmp')
    tmp.write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    tmp.replace(CFG_PATH)


def gid(cfg: dict | None = None) -> int:
    return _iid((cfg or load_config()).get('guild_id'))


def role_id(cfg: dict, key: str) -> int:
    return _iid(cfg.get(key))
