# -*- coding: utf-8 -*-
"""Конфиг Staff Manager — единственный источник ID ролей.

Файл: data/staff_manager.json (см. config/staff_manager.example.json).
В Python-коде НЕТ боевых Discord ID — только структура и валидация.

Hakumo: лестница Master/Assistant/Curator/Admin — ОБЩИЕ Discord-роли.
Ветка определяется через entry_role_id (Moderator/Helper/…).
"""
from __future__ import annotations

import json
import os
import threading
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

from logger import get_logger

_log = get_logger('staff_manager.config')

CONFIG_PATH = os.environ.get(
    'STAFF_MANAGER_CONFIG',
    os.path.join('data', 'staff_manager.json'),
)

DEFAULT_LADDER = [
    {'key': 'master', 'name': 'Master', 'rank': 1, 'emoji': '🟢', 'protected': False},
    {'key': 'curator', 'name': 'Curator', 'rank': 2, 'emoji': '🟣', 'protected': False},
    {'key': 'assistant', 'name': 'Assistent', 'rank': 3, 'emoji': '🔵', 'protected': False},
    {'key': 'admin', 'name': 'Admin', 'rank': 4, 'emoji': '🔴', 'protected': True},
]

_LOCK = threading.RLock()
_CFG: Optional[dict] = None
_INDEX: Optional[dict] = None
_ENABLED = False
_LAST_ERROR = ''


class ConfigError(Exception):
    """Конфиг Staff Manager невалиден — систему не поднимаем."""


def _as_int(v, default=0) -> int:
    try:
        return int(v or 0)
    except Exception:
        return default


def _normalize_ladder(raw) -> List[dict]:
    items = raw if isinstance(raw, list) and raw else deepcopy(DEFAULT_LADDER)
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        key = str(it.get('key') or '').strip().lower()
        if not key:
            continue
        if key == 'assistent':
            key = 'assistant'
        out.append({
            'key': key,
            'name': str(it.get('name') or key.title()),
            'rank': int(it.get('rank') or 0),
            'emoji': str(it.get('emoji') or ''),
            'protected': bool(it.get('protected')),
        })
    if not out:
        out = deepcopy(DEFAULT_LADDER)
    out.sort(key=lambda x: x['rank'])
    return out


def _normalize_branches(raw, ladder_keys: List[str]) -> Dict[str, dict]:
    if not isinstance(raw, dict):
        return {}
    out = {}
    for bkey, b in raw.items():
        if not isinstance(b, dict):
            continue
        roles_in = b.get('roles') or {}
        roles = {}
        for lk in ladder_keys:
            rid = roles_in.get(lk)
            if rid is None and lk == 'assistant':
                rid = roles_in.get('assistent')
            roles[lk] = _as_int(rid)
        out[str(bkey)] = {
            'key': str(bkey),
            'label': str(b.get('label') or bkey),
            'color': _as_int(b.get('color'), 0x5865F2),
            'responsible_role_id': _as_int(b.get('responsible_role_id')),
            'entry_role_id': _as_int(b.get('entry_role_id')),
            'roles': roles,
        }
    return out


def load_raw(path: str | None = None) -> dict:
    path = path or CONFIG_PATH
    if not os.path.isfile(path):
        raise ConfigError(
            f'Нет файла {path}. Скопируй config/staff_manager.example.json '
            f'→ data/staff_manager.json и заполни role ID.')
    with open(path, 'r', encoding='utf-8') as f:
        raw = json.load(f)
    if not isinstance(raw, dict):
        raise ConfigError('staff_manager.json должен быть объектом')
    return raw


def parse_config(raw: dict) -> dict:
    ladder = _normalize_ladder(raw.get('ladder') or raw.get('LADDER_TEMPLATE'))
    ladder_keys = [x['key'] for x in ladder]
    branches = _normalize_branches(
        raw.get('branches') or raw.get('BRANCHES') or {}, ladder_keys)
    owner_ids = []
    for x in (raw.get('owner_ids') or []):
        n = _as_int(x)
        if n:
            owner_ids.append(n)
    try:
        from config import Config
        owner_ids = sorted(set(owner_ids) | set(Config.all_owner_ids() or []))
    except Exception:
        owner_ids = sorted(set(owner_ids))

    role_emojis = {}
    for k, v in (raw.get('ROLE_EMOJIS') or raw.get('role_emojis') or {}).items():
        role_emojis[str(k).lower()] = str(v or '')
    branch_emojis = {}
    for k, v in (raw.get('BRANCH_EMOJIS') or raw.get('branch_emojis') or {}).items():
        branch_emojis[str(k)] = str(v or '')

    require_consent = []
    for x in (raw.get('REQUIRE_CONSENT_FOR') or raw.get('require_consent_for')
              or ['transfer']):
        require_consent.append(str(x).strip().lower())

    cfg = {
        'staff_admin_role_id': _as_int(raw.get('staff_admin_role_id')),
        'owner_ids': owner_ids,
        'common_staff_role_id': _as_int(raw.get('common_staff_role_id')),
        'vacation_role_id': _as_int(raw.get('vacation_role_id')),
        'hidden_admin_role_ids': [
            _as_int(x) for x in (
                raw.get('hidden_admin_role_ids')
                or raw.get('HIDDEN_ADMIN_ROLE_IDS') or [])
            if _as_int(x)
        ],
        'staff_power_role_ids': [
            _as_int(x) for x in (
                raw.get('staff_power_role_ids')
                or raw.get('STAFF_POWER_ROLE_IDS') or [])
            if _as_int(x)
        ],
        # 👑 🌺 и любые роли, которые НИКОГДА не снимает бот
        'never_strip_role_ids': [
            _as_int(x) for x in (
                raw.get('never_strip_role_ids')
                or raw.get('NEVER_STRIP_ROLE_IDS') or [])
            if _as_int(x)
        ],
        'log_channel_id': _as_int(raw.get('log_channel_id')),
        'actions_channel_id': _as_int(raw.get('actions_channel_id')),
        'consent_fallback_channel_id': _as_int(
            raw.get('CONSENT_FALLBACK_CHANNEL_ID')
            or raw.get('consent_fallback_channel_id')),
        'consent_expire_hours': max(
            1, _as_int(raw.get('CONSENT_EXPIRE_HOURS')
                       or raw.get('consent_expire_hours'), 48)),
        'require_consent_for': require_consent,
        'selftest_role_id': _as_int(
            raw.get('SELFTEST_ROLE_ID') or raw.get('selftest_role_id')),
        'selftest_user_id': _as_int(
            raw.get('SELFTEST_USER_ID') or raw.get('selftest_user_id')),
        'undo_window_minutes': max(
            1, _as_int(raw.get('UNDO_WINDOW_MINUTES')
                       or raw.get('undo_window_minutes'), 10)),
        'role_emojis': role_emojis,
        'branch_emojis': branch_emojis,
        'ladder': ladder,
        'branches': branches,
        'responsible_can_manage': [
            ('assistant' if str(x).lower() == 'assistent' else str(x).lower())
            for x in (raw.get('responsible_can_manage')
                      or ['master', 'curator', 'assistant'])
        ],
        'branch_admin_can_manage': [
            str(x).lower() for x in (raw.get('branch_admin_can_manage') or [])
        ],
        'curator_can_manage': [
            str(x).lower() for x in (raw.get('curator_can_manage') or [])
        ],
        'allow_promotion_requests': bool(
            raw.get('allow_promotion_requests', True)),
    }
    # подмешать emoji из ROLE_EMOJIS в ladder
    for it in cfg['ladder']:
        if not it.get('emoji') and role_emojis.get(it['key']):
            it['emoji'] = role_emojis[it['key']]
    return cfg


def build_indexes(cfg: dict) -> dict:
    """Индексы ролей.

    entry_role_id — уникальный якорь ветки (Moderator/Helper/…).
    Ladder-роли могут быть общими (shared=True) для всех веток.
    """
    by_role: Dict[int, dict] = {}
    by_branch_key: Dict[Tuple[str, str], int] = {}
    by_entry: Dict[int, str] = {}
    responsible_of: Dict[int, str] = {}

    for bkey, b in (cfg.get('branches') or {}).items():
        rid_resp = int(b.get('responsible_role_id') or 0)
        if rid_resp:
            if rid_resp in responsible_of and responsible_of[rid_resp] != bkey:
                raise ConfigError(
                    f'responsible_role_id {rid_resp} дублируется в ветках '
                    f'{responsible_of[rid_resp]} и {bkey}')
            responsible_of[rid_resp] = bkey

        entry_rid = int(b.get('entry_role_id') or 0)
        if entry_rid:
            if entry_rid in by_entry and by_entry[entry_rid] != bkey:
                raise ConfigError(
                    f'entry_role_id {entry_rid} дублируется в '
                    f'{by_entry[entry_rid]} и {bkey}')
            by_entry[entry_rid] = bkey

        for lk, rid in (b.get('roles') or {}).items():
            rid = int(rid or 0)
            if not rid:
                continue
            ladder_item = next(
                (x for x in cfg['ladder'] if x['key'] == lk), None)
            if not ladder_item:
                raise ConfigError(f'ветка {bkey}: неизвестный ключ роли {lk}')
            by_branch_key[(bkey, lk)] = rid
            entry = {
                'branch': bkey,
                'key': lk,
                'rank': int(ladder_item['rank']),
                'name': ladder_item['name'],
                'protected': bool(ladder_item.get('protected')),
                'label': b.get('label') or bkey,
                'color': int(b.get('color') or 0),
                'shared': False,
                'branches': [bkey],
                'is_entry': False,
            }
            if rid in by_role:
                prev = by_role[rid]
                if prev.get('key') != lk or prev.get('rank') != entry['rank']:
                    raise ConfigError(
                        f'role_id {rid} уже {prev.get("key")} — нельзя '
                        f'как {lk} в {bkey}')
                prev['shared'] = True
                if bkey not in prev['branches']:
                    prev['branches'].append(bkey)
            else:
                by_role[rid] = entry

    return {
        'by_role': by_role,
        'by_branch_key': by_branch_key,
        'by_entry': by_entry,
        'responsible_of': responsible_of,
    }


def validate_config(cfg: dict, *, guild_role_ids: set | None = None) -> List[str]:
    errs: List[str] = []
    if not cfg.get('staff_admin_role_id'):
        errs.append('staff_admin_role_id не задан')
    if not cfg.get('owner_ids'):
        errs.append('owner_ids пуст (нужен хотя бы OWNER_ID в .env)')
    ladder = cfg.get('ladder') or []
    if len(ladder) < 2:
        errs.append('ladder слишком короткий')
    keys = [x['key'] for x in ladder]
    if len(keys) != len(set(keys)):
        errs.append('в ladder дублируются key')
    ranks = [x['rank'] for x in ladder]
    if len(ranks) != len(set(ranks)):
        errs.append('в ladder дублируются rank')
    protected = [x for x in ladder if x.get('protected')]
    if not protected:
        errs.append('нет protected-роли (Admin) в ladder')
    branches = cfg.get('branches') or {}
    if not branches:
        errs.append('branches пуст')
    for bkey, b in branches.items():
        if not b.get('responsible_role_id'):
            errs.append(f'ветка {bkey}: нет responsible_role_id')
        if not b.get('entry_role_id'):
            errs.append(f'ветка {bkey}: нет entry_role_id')
        roles = b.get('roles') or {}
        for lk in keys:
            if not int(roles.get(lk) or 0):
                errs.append(f'ветка {bkey}: нет role_id для {lk}')
    try:
        build_indexes(cfg)
    except ConfigError as ex:
        errs.append(str(ex))

    if guild_role_ids is not None:
        need = set()
        need.add(int(cfg.get('staff_admin_role_id') or 0))
        for x in (
            cfg.get('common_staff_role_id'),
            cfg.get('vacation_role_id'),
            cfg.get('selftest_role_id'),
        ):
            if int(x or 0):
                need.add(int(x))
        for b in branches.values():
            need.add(int(b.get('responsible_role_id') or 0))
            need.add(int(b.get('entry_role_id') or 0))
            for rid in (b.get('roles') or {}).values():
                need.add(int(rid or 0))
        for rid in need:
            if rid and rid not in guild_role_ids:
                errs.append(f'роль {rid} не найдена на сервере')
    return errs


def load_config(path: str | None = None, *, guild_role_ids=None) -> dict:
    raw = load_raw(path)
    cfg = parse_config(raw)
    errs = validate_config(cfg, guild_role_ids=guild_role_ids)
    if errs:
        raise ConfigError('; '.join(errs))
    return cfg


def reload_config(path: str | None = None, *, guild_role_ids=None) -> Tuple[bool, str]:
    global _CFG, _INDEX, _ENABLED, _LAST_ERROR
    with _LOCK:
        try:
            cfg = load_config(path, guild_role_ids=guild_role_ids)
            idx = build_indexes(cfg)
            _CFG = cfg
            _INDEX = idx
            _ENABLED = True
            _LAST_ERROR = ''
            _log.info(
                'staff_manager: конфиг OK — ветки=%s ladder=%s entry=%s',
                list((cfg.get('branches') or {}).keys()),
                [x['key'] for x in cfg.get('ladder') or []],
                list((idx.get('by_entry') or {}).values()),
            )
            return True, ''
        except Exception as ex:
            _CFG = None
            _INDEX = None
            _ENABLED = False
            _LAST_ERROR = str(ex)
            _log.error('staff_manager: конфиг ОТКЛОНЁН — %s', ex)
            return False, str(ex)


def get_config() -> Optional[dict]:
    with _LOCK:
        return deepcopy(_CFG) if _CFG else None


def get_index() -> Optional[dict]:
    with _LOCK:
        return deepcopy(_INDEX) if _INDEX else None


def is_enabled() -> bool:
    return bool(_ENABLED)


def last_error() -> str:
    return _LAST_ERROR or ''


def ladder_by_key(key: str, cfg: dict | None = None) -> Optional[dict]:
    cfg = cfg or get_config() or {}
    key = 'assistant' if key == 'assistent' else key
    for it in cfg.get('ladder') or []:
        if it['key'] == key:
            return it
    return None


def branch_of_role(role_id: int) -> Optional[dict]:
    idx = get_index() or {}
    return (idx.get('by_role') or {}).get(int(role_id))


def entry_branch(role_id: int) -> Optional[str]:
    idx = get_index() or {}
    return (idx.get('by_entry') or {}).get(int(role_id))


def role_emoji(key: str, cfg: dict | None = None) -> str:
    cfg = cfg or get_config() or {}
    key = 'assistant' if key == 'assistent' else (key or '')
    em = (cfg.get('role_emojis') or {}).get(key) or ''
    if em:
        return em
    item = ladder_by_key(key, cfg)
    return (item or {}).get('emoji') or ''


def branch_emoji(branch: str, cfg: dict | None = None) -> str:
    cfg = cfg or get_config() or {}
    return (cfg.get('branch_emojis') or {}).get(branch or '') or ''


def requires_consent(action: str, cfg: dict | None = None) -> bool:
    cfg = cfg or get_config() or {}
    return str(action or '').lower() in set(cfg.get('require_consent_for') or [])
