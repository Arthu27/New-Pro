# -*- coding: utf-8 -*-
"""Персистентный реестр Love Room + naming / pair-lock / empty-delete."""
from __future__ import annotations

import json
import os
import time
from typing import Any, Optional

from logger import get_logger

_log = get_logger('love_room_store')

_CFG_REL = 'config/love_room.json'
DEFAULT_HEARTS = ['💕', '💖', '💗', '💓', '💞', '💝']
DEFAULT_PREFIX = 'love room'
DEFAULT_GUILD = 793336829280780331


def _repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _cfg_path() -> str:
    return os.path.join(_repo_root(), _CFG_REL)


def _store_path(guild_id: int) -> str:
    return os.path.join(_repo_root(), 'data', f'love_rooms_{int(guild_id)}.json')


def _read_json(path: str, default):
    try:
        if os.path.isfile(path):
            with open(path, encoding='utf-8') as fh:
                data = json.load(fh)
            return data if isinstance(data, type(default)) else default
    except (OSError, ValueError, TypeError) as ex:
        _log.debug('read %s: %s', path, ex)
    return default


def _write_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def load_love_room_cfg() -> dict:
    """JSON + env overrides. IDs default 0 until wire-up."""
    cfg = {
        'guild_id': str(DEFAULT_GUILD),
        'category_id': '0',
        'panel_channel_id': '0',
        'host_role_ids': [],
        'vedushiy_role_id': '0',
        'source_stage_channel_id': '0',
        'user_limit': 2,
        'pair_cooldown_sec': 10,
        'empty_delete_debounce_sec': 1.5,
        'name_prefix': DEFAULT_PREFIX,
        'heart_emojis': list(DEFAULT_HEARTS),
    }
    raw = _read_json(_cfg_path(), {})
    if isinstance(raw, dict):
        for k in cfg:
            if k in raw and raw[k] is not None:
                cfg[k] = raw[k]
    env_map = {
        'guild_id': 'LOVE_ROOM_GUILD_ID',
        'category_id': 'LOVE_ROOM_CATEGORY_ID',
        'panel_channel_id': 'LOVE_ROOM_PANEL_CHANNEL_ID',
        'vedushiy_role_id': 'VEDUSHIY_ROLE_ID',
        'source_stage_channel_id': 'LOVE_ROOM_SOURCE_STAGE_ID',
    }
    for key, envk in env_map.items():
        val = (os.environ.get(envk) or '').strip()
        if val and val not in ('none', 'None'):
            cfg[key] = val
    host_env = (os.environ.get('LOVE_ROOM_HOST_ROLE_IDS') or '').strip()
    if host_env:
        ids = []
        for part in host_env.replace(';', ',').split(','):
            part = part.strip()
            if not part:
                continue
            try:
                ids.append(str(int(part)))
            except ValueError:
                continue
        cfg['host_role_ids'] = ids
    try:
        cfg['user_limit'] = int(cfg.get('user_limit') or 2)
    except (TypeError, ValueError):
        cfg['user_limit'] = 2
    try:
        cfg['pair_cooldown_sec'] = float(cfg.get('pair_cooldown_sec') or 10)
    except (TypeError, ValueError):
        cfg['pair_cooldown_sec'] = 10.0
    try:
        cfg['empty_delete_debounce_sec'] = float(
            cfg.get('empty_delete_debounce_sec') or 1.5)
    except (TypeError, ValueError):
        cfg['empty_delete_debounce_sec'] = 1.5
    hearts = cfg.get('heart_emojis') or DEFAULT_HEARTS
    if not isinstance(hearts, list) or not hearts:
        hearts = list(DEFAULT_HEARTS)
    cfg['heart_emojis'] = [str(h) for h in hearts]
    cfg['name_prefix'] = str(cfg.get('name_prefix') or DEFAULT_PREFIX).strip() or DEFAULT_PREFIX
    return cfg


def cfg_int(cfg: dict, key: str, default: int = 0) -> int:
    try:
        return int(str(cfg.get(key) or default) or default)
    except (TypeError, ValueError):
        return default


def load_rooms(guild_id: int) -> dict:
    data = _read_json(_store_path(guild_id), {'rooms': {}, 'cooldowns': {}})
    if not isinstance(data.get('rooms'), dict):
        data['rooms'] = {}
    if not isinstance(data.get('cooldowns'), dict):
        data['cooldowns'] = {}
    return data


def save_rooms(guild_id: int, data: dict) -> None:
    _write_json(_store_path(guild_id), {
        'rooms': data.get('rooms') or {},
        'cooldowns': data.get('cooldowns') or {},
    })


def pair_key(u1: int, u2: int) -> str:
    a, b = sorted((int(u1), int(u2)))
    return f'{a}:{b}'


def room_name(prefix: str, heart: str) -> str:
    return f'{prefix} {heart}'.strip()


def is_love_room_name(name: str, prefix: str = DEFAULT_PREFIX) -> bool:
    n = (name or '').strip().lower()
    p = (prefix or DEFAULT_PREFIX).strip().lower()
    return n.startswith(p)


def pick_heart(used_hearts: set[str], hearts: list[str] | None = None) -> str:
    pool = list(hearts or DEFAULT_HEARTS)
    for h in pool:
        if h not in used_hearts:
            return h
    # all in use — cycle with index suffix via time
    return pool[int(time.time()) % len(pool)]


def used_hearts_from_rooms(rooms: dict, prefix: str = DEFAULT_PREFIX) -> set[str]:
    out: set[str] = set()
    for meta in (rooms or {}).values():
        if not isinstance(meta, dict):
            continue
        name = str(meta.get('name') or '')
        if not is_love_room_name(name, prefix):
            continue
        # last token is heart emoji
        parts = name.split()
        if parts:
            out.add(parts[-1])
    return out


def register_room(guild_id: int, *, channel_id: int, name: str,
                  users: list[int], created_by: int) -> dict:
    data = load_rooms(guild_id)
    meta = {
        'channel_id': str(int(channel_id)),
        'name': name,
        'users': [int(u) for u in users],
        'created_by': int(created_by),
        'created_at': time.time(),
    }
    data['rooms'][str(int(channel_id))] = meta
    save_rooms(guild_id, data)
    return meta


def unregister_room(guild_id: int, channel_id: int) -> bool:
    data = load_rooms(guild_id)
    key = str(int(channel_id))
    if key in data['rooms']:
        del data['rooms'][key]
        save_rooms(guild_id, data)
        return True
    return False


def find_room_for_user(guild_id: int, user_id: int) -> Optional[dict]:
    data = load_rooms(guild_id)
    uid = int(user_id)
    for meta in data['rooms'].values():
        if not isinstance(meta, dict):
            continue
        if uid in [int(x) for x in (meta.get('users') or [])]:
            return meta
    return None


def find_room_by_channel(guild_id: int, channel_id: int) -> Optional[dict]:
    data = load_rooms(guild_id)
    return data['rooms'].get(str(int(channel_id)))


def set_cooldown(guild_id: int, host_id: int, sec: float | None = None) -> None:
    cfg = load_love_room_cfg()
    delay = float(sec if sec is not None else cfg.get('pair_cooldown_sec') or 10)
    data = load_rooms(guild_id)
    data['cooldowns'][str(int(host_id))] = time.time() + delay
    save_rooms(guild_id, data)


def cooldown_remaining(guild_id: int, host_id: int) -> float:
    data = load_rooms(guild_id)
    until = float((data.get('cooldowns') or {}).get(str(int(host_id))) or 0)
    left = until - time.time()
    return max(0.0, left)


def should_delete_empty(human_count: int) -> bool:
    """True when no humans left (bots ignored by caller)."""
    return int(human_count or 0) <= 0


def host_role_id_set(cfg: dict | None = None) -> set[int]:
    cfg = cfg or load_love_room_cfg()
    out: set[int] = set()
    for rid in cfg.get('host_role_ids') or []:
        try:
            out.add(int(rid))
        except (TypeError, ValueError):
            continue
    for key in ('vedushiy_role_id',):
        try:
            v = int(str(cfg.get(key) or 0) or 0)
            if v:
                out.add(v)
        except (TypeError, ValueError):
            pass
    env_v = (os.environ.get('VEDUSHIY_ROLE_ID') or '').strip()
    if env_v and env_v not in ('0', 'none'):
        try:
            out.add(int(env_v))
        except ValueError:
            pass
    return out


def member_has_host_acl(member, cfg: dict | None = None) -> bool:
    """Ведущий / host roles / admin / manage_guild / administrator."""
    if member is None:
        return False
    try:
        perms = getattr(member, 'guild_permissions', None)
        if perms is not None and (
                getattr(perms, 'administrator', False)
                or getattr(perms, 'manage_guild', False)):
            return True
    except Exception:
        pass
    allowed = host_role_id_set(cfg)
    try:
        from services.vedushiy_role_seed import (
            resolve_vedushiy_role_id, NAME_ALIASES, ROLE_NAME)
        rid = resolve_vedushiy_role_id(guild=getattr(member, 'guild', None))
        if rid:
            allowed.add(int(rid))
        aliases = {_norm(a) for a in NAME_ALIASES}
        aliases.add(_norm(ROLE_NAME))
    except Exception:
        aliases = {'ведущий', 'vedushiy', 'broadcaster'}

    for role in list(getattr(member, 'roles', None) or []):
        try:
            if int(getattr(role, 'id', 0) or 0) in allowed:
                return True
        except (TypeError, ValueError):
            pass
        try:
            if _norm(getattr(role, 'name', '')) in aliases:
                return True
        except Exception:
            pass
    return False


def _norm(name: str) -> str:
    return (name or '').strip().lower().replace('ё', 'е')


# In-memory pair create locks (process-local)
_pair_locks: dict[str, float] = {}
_PAIR_LOCK_TTL = 15.0


def try_acquire_pair_lock(u1: int, u2: int) -> bool:
    key = pair_key(u1, u2)
    now = time.time()
    # purge stale
    stale = [k for k, t in _pair_locks.items() if now - t > _PAIR_LOCK_TTL]
    for k in stale:
        _pair_locks.pop(k, None)
    if key in _pair_locks:
        return False
    _pair_locks[key] = now
    return True


def release_pair_lock(u1: int, u2: int) -> None:
    _pair_locks.pop(pair_key(u1, u2), None)


def snapshot(guild_id: int) -> dict[str, Any]:
    data = load_rooms(guild_id)
    return {
        'guild_id': int(guild_id),
        'room_count': len(data.get('rooms') or {}),
        'rooms': dict(data.get('rooms') or {}),
    }
