# -*- coding: utf-8 -*-
"""Сид «× Master» — mid между Helper/Moderator и Curator (обе ветки).

Одна роль на обе ветки. Наказания — только вместе с Helper или Moderator
(см. master_punish_allowed). Лимиты mid: мут/размут 5, бан 1, варн 1.

Идемпотентно: маркер data/.master_acl.v<N>.
"""
from __future__ import annotations

import json
import os

from logger import get_logger

_log = get_logger('master_acl_seed')

SEED_VERSION = 1
MARKER = f'data/.master_acl.v{SEED_VERSION}'
_DEMO_GUILD = 987654321098765432

MASTER_LIMITS = {
    'warn': 1, 'ban': 1, 'mute': 5, 'unmute': 5, 'clear': 10,
}


def _main_guild_id(override=None):
    try:
        gid = int(override or 0)
    except (TypeError, ValueError):
        gid = 0
    if not gid:
        try:
            from config import Config
            gid = int(getattr(Config, 'MAIN_GUILD_ID', 0) or 0)
        except Exception:
            gid = 0
    if gid and gid != _DEMO_GUILD:
        return gid
    return None


def _master_id():
    from services.staff_roles import KNOWN_MASTER_ROLE_ID
    return str(int(KNOWN_MASTER_ROLE_ID))


def _ensure_role_map(report):
    path = 'data/role_map.json'
    mid = _master_id()
    try:
        data = {}
        if os.path.isfile(path):
            with open(path, encoding='utf-8') as fh:
                data = json.load(fh) or {}
        if not isinstance(data, dict):
            data = {}
        if data.get(mid) != 'master':
            data[mid] = 'master'
            os.makedirs('data', exist_ok=True)
            with open(path, 'w', encoding='utf-8') as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
            report['role_map'] = True
            report['role_map_added'].append(f'{mid}=master')
    except Exception as ex:
        _log.warning('master role_map: %s', ex)


def _sync_master_action_acl(gid, report):
    from services.permission_acl import (
        ACTIONS, load_action_acl, save_action_acl)
    acl = load_action_acl(gid)
    if not isinstance(acl, dict):
        acl = {}
    mid = _master_id()
    for action in ACTIONS:
        cur = [str(r) for r in (acl.get(action) or [])]
        if mid not in cur:
            cur.append(mid)
            acl[action] = cur
            report['actions_added'].append(action)
    if report['actions_added']:
        save_action_acl(gid, acl)


def ensure_master_acl(guild_id=None):
    report = {
        'applied': False, 'reason': '', 'guild_id': 0,
        'actions_added': [], 'role_map': False, 'role_map_added': [],
        'limits': False,
    }
    try:
        if str(os.environ.get('DEMO_MODE', '')).strip().lower() in (
                '1', 'true', 'yes', 'on'):
            report['reason'] = 'demo mode'
            return report
        gid = _main_guild_id(guild_id)
        if not gid:
            report['reason'] = 'no MAIN_GUILD_ID'
            return report
        report['guild_id'] = gid
        _ensure_role_map(report)
        _sync_master_action_acl(gid, report)
        if report['actions_added'] or report['role_map']:
            report['applied'] = True
            report['reason'] = 'acl repaired'
        else:
            report['reason'] = 'acl ok'
    except Exception as ex:
        report['reason'] = f'error: {ex}'
        _log.warning('ensure_master_acl: %s', ex)
    return report


def apply_master_acl_seed(force=False, guild_id=None):
    report = {
        'applied': False, 'reason': '', 'guild_id': 0,
        'actions_added': [], 'role_map': False, 'role_map_added': [],
        'cmd_acl': False, 'limits': False,
    }
    try:
        if str(os.environ.get('DEMO_MODE', '')).strip().lower() in (
                '1', 'true', 'yes', 'on'):
            report['reason'] = 'demo mode'
            return report
        if not force and os.path.exists(MARKER):
            return ensure_master_acl(guild_id)

        gid = _main_guild_id(guild_id)
        if not gid:
            report['reason'] = 'no MAIN_GUILD_ID'
            return report
        report['guild_id'] = gid
        mid = _master_id()

        _ensure_role_map(report)
        _sync_master_action_acl(gid, report)

        try:
            from services.permission_acl import load_acl, set_rule
            cmd = load_acl(gid)
            if not isinstance(cmd, dict):
                cmd = {}
            existing = [str(r) for r in (cmd.get('modpanel') or [])]
            if existing and mid not in existing:
                existing.append(mid)
                set_rule(gid, 'modpanel', existing)
                report['cmd_acl'] = True
        except Exception as ex:
            _log.warning('master cmd_acl: %s', ex)

        try:
            from services.staff_limits import set_role_limits
            set_role_limits(
                gid, int(mid), who='master_acl_seed',
                role_name='× Master', **MASTER_LIMITS)
            report['limits'] = True
        except Exception as ex:
            _log.warning('master limits: %s', ex)

        try:
            os.makedirs('data', exist_ok=True)
            with open(MARKER, 'w', encoding='utf-8') as fh:
                fh.write('ok')
        except OSError as ex:
            _log.debug('master marker: %s', ex)

        report['applied'] = True
        report['reason'] = 'ok'
        _log.info(
            'master_acl_seed v%s: guild=%s +%s limits=%s',
            SEED_VERSION, gid, report['actions_added'], MASTER_LIMITS)
    except Exception as ex:
        report['reason'] = f'error: {ex}'
        _log.warning('apply_master_acl_seed: %s', ex)
    return report
