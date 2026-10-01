# -*- coding: utf-8 -*-
"""Сид «× Отвечаю за Helper/Moderator» — тир curator + полный ACL.

Роли кураторов веток должны мочь /modpanel наравне с × Curator.
Warn по стаффу — отдельно через warn_acl (своя ветка).

Идемпотентно: маркер data/.branch_curator_acl.v<N>.
"""
from __future__ import annotations

import json
import os

from logger import get_logger

_log = get_logger('branch_curator_acl_seed')

SEED_VERSION = 1
MARKER = f'data/.branch_curator_acl.v{SEED_VERSION}'
_DEMO_GUILD = 987654321098765432

CURATOR_LIMITS = {
    'warn': 2, 'ban': 2, 'mute': 7, 'unmute': 7, 'clear': 10,
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


def _branch_curator_ids():
    from services.staff_roles import KNOWN_CURATOR_BY_KIND, KNOWN_CURATOR_ROLE_ID
    ids = []
    for kind in ('helper', 'moderator'):
        rid = int((KNOWN_CURATOR_BY_KIND or {}).get(kind) or 0)
        if rid:
            ids.append(str(rid))
    try:
        cid = str(int(KNOWN_CURATOR_ROLE_ID or 0))
        if cid and cid != '0' and cid not in ids:
            ids.append(cid)
    except Exception:
        pass
    return ids


def _ensure_role_map(report):
    path = 'data/role_map.json'
    ids = _branch_curator_ids()
    try:
        data = {}
        if os.path.isfile(path):
            with open(path, encoding='utf-8') as fh:
                data = json.load(fh) or {}
        if not isinstance(data, dict):
            data = {}
        changed = False
        for rid in ids:
            if data.get(rid) != 'curator':
                data[rid] = 'curator'
                changed = True
                report['role_map_added'].append(f'{rid}=curator')
        if changed:
            os.makedirs('data', exist_ok=True)
            with open(path, 'w', encoding='utf-8') as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
            report['role_map'] = True
    except Exception as ex:
        _log.warning('branch_curator role_map: %s', ex)


def _sync_acl(gid, report):
    from services.permission_acl import (
        ACTIONS, load_action_acl, save_action_acl)
    acl = load_action_acl(gid)
    if not isinstance(acl, dict):
        acl = {}
    for rid in _branch_curator_ids():
        for action in ACTIONS:
            cur = [str(r) for r in (acl.get(action) or [])]
            if rid not in cur:
                cur.append(rid)
                acl[action] = cur
                report['actions_added'].append(f'{action}:{rid}')
    if report['actions_added']:
        save_action_acl(gid, acl)


def ensure_branch_curator_acl(guild_id=None):
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
        _sync_acl(gid, report)
        if report['actions_added'] or report['role_map']:
            report['applied'] = True
            report['reason'] = 'acl repaired'
        else:
            report['reason'] = 'acl ok'
    except Exception as ex:
        report['reason'] = f'error: {ex}'
        _log.warning('ensure_branch_curator_acl: %s', ex)
    return report


def apply_branch_curator_acl_seed(force=False, guild_id=None):
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
            return ensure_branch_curator_acl(guild_id)

        gid = _main_guild_id(guild_id)
        if not gid:
            report['reason'] = 'no MAIN_GUILD_ID'
            return report
        report['guild_id'] = gid
        ids = _branch_curator_ids()
        if not ids:
            report['reason'] = 'no curator ids'
            return report

        _ensure_role_map(report)
        _sync_acl(gid, report)

        try:
            from services.permission_acl import load_acl, set_rule
            cmd = load_acl(gid)
            if not isinstance(cmd, dict):
                cmd = {}
            existing = [str(r) for r in (cmd.get('modpanel') or [])]
            if existing:
                changed = False
                for rid in ids:
                    if rid not in existing:
                        existing.append(rid)
                        changed = True
                if changed:
                    set_rule(gid, 'modpanel', existing)
                    report['cmd_acl'] = True
        except Exception as ex:
            _log.warning('branch_curator cmd_acl: %s', ex)

        try:
            from services.staff_limits import set_role_limits
            for rid in ids:
                set_role_limits(
                    gid, int(rid), who='branch_curator_acl_seed',
                    role_name='× Curator/Отвечаю', **CURATOR_LIMITS)
            report['limits'] = True
        except Exception as ex:
            _log.warning('branch_curator limits: %s', ex)

        try:
            os.makedirs('data', exist_ok=True)
            with open(MARKER, 'w', encoding='utf-8') as fh:
                fh.write('ok')
        except OSError as ex:
            _log.debug('branch_curator marker: %s', ex)

        report['applied'] = True
        report['reason'] = 'ok'
        _log.info(
            'branch_curator_acl v%s: guild=%s +%s',
            SEED_VERSION, gid, report['actions_added'])
    except Exception as ex:
        report['reason'] = f'error: {ex}'
        _log.warning('apply_branch_curator_acl_seed: %s', ex)
    return report
