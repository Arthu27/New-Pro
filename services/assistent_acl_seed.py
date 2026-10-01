# -*- coding: utf-8 -*-
"""Сид «× Assistent» / «× Staff Assistent» — выше куратора (обе ветки).

Discord pos: Assistent (95) > Curator (94) > Master (93).
Staff Assistent (100) — старший ассистент.

  • тир assistent в role_map (между curator и admin);
  • полный ACL наказаний (как куратор/мастер, не урезанный хелперский);
  • лимиты выше куратора: мут/размут 9, бан 3; Staff Assistent — ещё выше.

Идемпотентно: маркер data/.assistent_acl.v<N>.
"""
from __future__ import annotations

import json
import os

from logger import get_logger

_log = get_logger('assistent_acl_seed')

SEED_VERSION = 2
MARKER = f'data/.assistent_acl.v{SEED_VERSION}'
_DEMO_GUILD = 987654321098765432

# Полный набор действий стаффа (выше куратора — без урезания до mute/purge).
ASSISTENT_LIMITS = {
    'warn': 2, 'ban': 3, 'mute': 9, 'unmute': 9, 'clear': 10,
}
STAFF_ASSISTENT_LIMITS = {
    'warn': 3, 'ban': 4, 'mute': 10, 'unmute': 10, 'clear': 12,
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


def _assistent_ids():
    from services.staff_roles import (
        KNOWN_ASSISTENT_ROLE_ID, KNOWN_STAFF_ASSISTENT_ROLE_ID)
    out = []
    for rid in (KNOWN_ASSISTENT_ROLE_ID, KNOWN_STAFF_ASSISTENT_ROLE_ID):
        if int(rid or 0):
            out.append(str(int(rid)))
    return out


def _ensure_role_map(report):
    """Assistent / Staff Assistent → assistent; снять ошибочный master."""
    path = 'data/role_map.json'
    ids = _assistent_ids()
    try:
        data = {}
        if os.path.isfile(path):
            with open(path, encoding='utf-8') as fh:
                data = json.load(fh) or {}
        if not isinstance(data, dict):
            data = {}
        changed = False
        for rid in ids:
            if data.get(rid) != 'assistent':
                data[rid] = 'assistent'
                changed = True
                report['role_map_added'].append(f'{rid}=assistent')
        if changed:
            os.makedirs('data', exist_ok=True)
            with open(path, 'w', encoding='utf-8') as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
            report['role_map'] = True
    except Exception as ex:
        _log.warning('assistent role_map: %s', ex)


def _sync_assistent_action_acl(gid, report):
    """Полный ACL: добавить во все ACTIONS."""
    from services.permission_acl import (
        ACTIONS, load_action_acl, save_action_acl)
    acl = load_action_acl(gid)
    if not isinstance(acl, dict):
        acl = {}
    ids = _assistent_ids()
    for rid in ids:
        for action in ACTIONS:
            cur = [str(r) for r in (acl.get(action) or [])]
            if rid not in cur:
                cur.append(rid)
                acl[action] = cur
                report['actions_added'].append(f'{action}:{rid}')
    if report['actions_added']:
        save_action_acl(gid, acl)
    return acl


def ensure_assistent_acl(guild_id=None):
    """Подтянуть тир/ACL ассистента без маркера (каждый on_ready)."""
    report = {
        'applied': False, 'reason': '', 'guild_id': 0,
        'actions_added': [], 'actions_removed': [],
        'role_map': False, 'role_map_added': [], 'limits': False,
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
        _sync_assistent_action_acl(gid, report)
        if (report['actions_added'] or report['actions_removed']
                or report['role_map']):
            report['applied'] = True
            report['reason'] = 'acl repaired'
            _log.info(
                'assistent_acl ensure: guild=%s +%s map=%s',
                gid, report['actions_added'], report['role_map_added'])
        else:
            report['reason'] = 'acl ok'
    except Exception as ex:
        report['reason'] = f'error: {ex}'
        _log.warning('ensure_assistent_acl: %s', ex)
    return report


def apply_assistent_acl_seed(force=False, guild_id=None):
    """Выдать ассистенту права выше куратора. Возвращает отчёт."""
    report = {
        'applied': False, 'reason': '', 'guild_id': 0,
        'actions_added': [], 'actions_removed': [],
        'role_map': False, 'role_map_added': [],
        'cmd_acl': False, 'limits': False,
    }
    try:
        if str(os.environ.get('DEMO_MODE', '')).strip().lower() in (
                '1', 'true', 'yes', 'on'):
            report['reason'] = 'demo mode'
            return report
        # v1 маркер (старый mid/master) — всегда пересидить на v2
        old_marker = 'data/.assistent_acl.v1'
        if (not force) and os.path.exists(MARKER):
            return ensure_assistent_acl(guild_id)
        if (not force) and os.path.exists(old_marker) and not os.path.exists(
                MARKER):
            force = True  # апгрейд v1→v2

        gid = _main_guild_id(guild_id)
        if not gid:
            report['reason'] = 'no MAIN_GUILD_ID'
            return report
        report['guild_id'] = gid
        ids = _assistent_ids()
        if not ids:
            report['reason'] = 'no assistent role ids'
            return report

        _ensure_role_map(report)
        _sync_assistent_action_acl(gid, report)

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
            _log.warning('assistent cmd_acl: %s', ex)

        try:
            from services.staff_limits import set_role_limits
            from services.staff_roles import (
                KNOWN_ASSISTENT_ROLE_ID, KNOWN_STAFF_ASSISTENT_ROLE_ID)
            set_role_limits(
                gid, int(KNOWN_ASSISTENT_ROLE_ID),
                who='assistent_acl_seed', role_name='× Assistent',
                **ASSISTENT_LIMITS)
            set_role_limits(
                gid, int(KNOWN_STAFF_ASSISTENT_ROLE_ID),
                who='assistent_acl_seed', role_name='× Staff Assistent',
                **STAFF_ASSISTENT_LIMITS)
            report['limits'] = True
        except Exception as ex:
            _log.warning('assistent limits: %s', ex)

        try:
            os.makedirs('data', exist_ok=True)
            with open(MARKER, 'w', encoding='utf-8') as fh:
                fh.write('ok')
            if os.path.exists(old_marker):
                try:
                    os.remove(old_marker)
                except OSError:
                    pass
        except OSError as ex:
            _log.debug('assistent marker: %s', ex)

        report['applied'] = True
        report['reason'] = 'ok'
        _log.info(
            'assistent_acl_seed v%s: guild=%s +%s limits=%s/%s',
            SEED_VERSION, gid, report['actions_added'],
            ASSISTENT_LIMITS, STAFF_ASSISTENT_LIMITS)
    except Exception as ex:
        report['reason'] = f'error: {ex}'
        _log.warning('apply_assistent_acl_seed: %s', ex)
    return report
