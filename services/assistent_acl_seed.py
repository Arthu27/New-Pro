# -*- coding: utf-8 -*-
"""Сид «× Assistent» / «× Staff Assistent» — мастер ветки Helper.

Между хелпером и куратором (заказ владельца 2026-10-01):
  • тир master в role_map;
  • /modpanel: мут чата, размут, очистка (как хелпер — без ban/vmute/warn);
  • лимиты mid: мут/размут 5, чистка 10 /день (хелпер 3 → ассистент 5 → куратор 7).

Идемпотентно: маркер data/.assistent_acl.v<N>.
"""
from __future__ import annotations

import json
import os

from logger import get_logger

_log = get_logger('assistent_acl_seed')

SEED_VERSION = 1
MARKER = f'data/.assistent_acl.v{SEED_VERSION}'
_DEMO_GUILD = 987654321098765432

# Как у хелпера — только чат. Бан / войс / таймаут / варн — нет.
ASSISTENT_ACTIONS = ('mute', 'purge')
# Среднее между helper (3) и curator (7).
ASSISTENT_LIMITS = {'clear': 10, 'mute': 5, 'unmute': 5}


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
    from services.staff_roles import KNOWN_HELPER_MASTER_ROLE_IDS
    return [str(int(r)) for r in KNOWN_HELPER_MASTER_ROLE_IDS if int(r or 0)]


def _sync_assistent_action_acl(gid, report):
    """Выдать mute/purge, снять тяжёлые. Пишет в report."""
    from services.permission_acl import (
        ACTIONS, load_action_acl, save_action_acl)
    acl = load_action_acl(gid)
    if not isinstance(acl, dict):
        acl = {}
    ids = _assistent_ids()
    for rid in ids:
        for action in ASSISTENT_ACTIONS:
            cur = [str(r) for r in (acl.get(action) or [])]
            if rid not in cur:
                cur.append(rid)
                acl[action] = cur
                report['actions_added'].append(f'{action}:{rid}')
        for action in ACTIONS:
            if action in ASSISTENT_ACTIONS:
                continue
            cur = [str(r) for r in (acl.get(action) or [])]
            if rid in cur:
                acl[action] = [r for r in cur if r != rid]
                report['actions_removed'].append(f'{action}:{rid}')
    if report['actions_added'] or report['actions_removed']:
        save_action_acl(gid, acl)
    return acl


def _ensure_role_map(report):
    """Assistent / Staff Assistent → master."""
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
            if data.get(rid) != 'master':
                data[rid] = 'master'
                changed = True
                report['role_map_added'].append(f'{rid}=master')
        if changed:
            os.makedirs('data', exist_ok=True)
            with open(path, 'w', encoding='utf-8') as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
            report['role_map'] = True
    except Exception as ex:
        _log.warning('assistent role_map: %s', ex)


def ensure_assistent_acl(guild_id=None):
    """Подтянуть ACL ассистента без маркера (каждый on_ready)."""
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
                'assistent_acl ensure: guild=%s +%s -%s map=%s',
                gid, report['actions_added'], report['actions_removed'],
                report['role_map_added'])
        else:
            report['reason'] = 'acl ok'
    except Exception as ex:
        report['reason'] = f'error: {ex}'
        _log.warning('ensure_assistent_acl: %s', ex)
    return report


def apply_assistent_acl_seed(force=False, guild_id=None):
    """Выдать ассистенту mid-права ветки хелперов. Возвращает отчёт."""
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
        if not force and os.path.exists(MARKER):
            return ensure_assistent_acl(guild_id)

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
            for rid in ids:
                set_role_limits(
                    gid, int(rid), who='assistent_acl_seed',
                    role_name='× Assistent', **ASSISTENT_LIMITS)
            report['limits'] = True
        except Exception as ex:
            _log.warning('assistent limits: %s', ex)

        try:
            os.makedirs('data', exist_ok=True)
            with open(MARKER, 'w', encoding='utf-8') as fh:
                fh.write('ok')
        except OSError as ex:
            _log.debug('assistent marker: %s', ex)

        report['applied'] = True
        report['reason'] = 'ok'
        _log.info(
            'assistent_acl_seed v%s: guild=%s +%s -%s limits=%s',
            SEED_VERSION, gid, report['actions_added'],
            report['actions_removed'], ASSISTENT_LIMITS)
    except Exception as ex:
        report['reason'] = f'error: {ex}'
        _log.warning('apply_assistent_acl_seed: %s', ex)
    return report
