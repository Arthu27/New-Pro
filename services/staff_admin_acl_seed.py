# -*- coding: utf-8 -*-
"""Сид роли «× Staff Administrator» — полные admin-права + лимиты +2.

Роль 1549118975110152263 (эскалация жалоб на админов):
  • тир admin в role_map;
  • все классические ACL-действия как у × Administrator;
  • лимиты на 2 выше дефолта admin (mute/unmute/ban/warn/clear).

Идемпотентно: маркер data/.staff_admin_acl.v<N>.
"""
from __future__ import annotations

import json
import os

from logger import get_logger

_log = get_logger('staff_admin_acl_seed')

SEED_VERSION = 1
MARKER = f'data/.staff_admin_acl.v{SEED_VERSION}'
_DEMO_GUILD = 987654321098765432

# admin defaults + 2
STAFF_ADMIN_LIMITS = {
    'warn': 4,      # admin 2 + 2
    'ban': 7,       # admin 5 + 2
    'mute': 12,     # admin 10 + 2
    'unmute': 12,   # admin 10 + 2
    'clear': 12,    # admin 10 + 2
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


def _staff_admin_id():
    from services.staff_roles import KNOWN_STAFF_ADMIN_ROLE_ID
    return str(int(KNOWN_STAFF_ADMIN_ROLE_ID))


def apply_staff_admin_acl_seed(force=False, guild_id=None) -> dict:
    report = {
        'applied': False, 'reason': '', 'guild_id': 0,
        'role_map': False, 'acl_added': [], 'limits': False,
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
        if (not force) and os.path.isfile(MARKER):
            report['reason'] = f'already applied (v{SEED_VERSION})'
            return report

        said = _staff_admin_id()

        # 1) role_map → admin
        path = 'data/role_map.json'
        try:
            data = {}
            if os.path.isfile(path):
                with open(path, encoding='utf-8') as f:
                    data = json.load(f) or {}
            if not isinstance(data, dict):
                data = {}
            if data.get(said) != 'admin':
                data[said] = 'admin'
                os.makedirs('data', exist_ok=True)
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                report['role_map'] = True
        except Exception as ex:
            report['reason'] = f'role_map: {ex}'
            return report

        # 2) все ACL-действия
        from services.permission_acl import ACTIONS, load_action_acl, save_action_acl
        acl = load_action_acl(gid)
        if not isinstance(acl, dict):
            acl = {}
        changed = False
        for action in ACTIONS:
            cur = [str(r) for r in (acl.get(action) or [])]
            if said not in cur:
                cur.append(said)
                acl[action] = cur
                report['acl_added'].append(action)
                changed = True
        if changed:
            save_action_acl(gid, acl)

        # 3) лимиты +2 к admin
        from services import staff_limits as SL
        SL.set_role_limits(
            gid, int(said), who='staff_admin_acl_seed',
            role_name='× Staff Administrator', **STAFF_ADMIN_LIMITS)
        report['limits'] = True

        os.makedirs('data', exist_ok=True)
        with open(MARKER, 'w', encoding='utf-8') as f:
            f.write(f'v{SEED_VERSION}\n')
        report['applied'] = True
        report['reason'] = 'ok'
        _log.info(
            'staff_admin_acl v%s: role_map=%s acl+%s limits=%s',
            SEED_VERSION, report['role_map'], report['acl_added'],
            STAFF_ADMIN_LIMITS)
    except Exception as ex:
        report['reason'] = f'error: {ex}'
        _log.warning('apply_staff_admin_acl_seed: %s', ex)
    return report
