# -*- coding: utf-8 -*-
"""Сид прав роли «Хелпер» — ветка чата (заказ владельца 2026-09-24).

Роль 948969471916249119:
  • /modpanel: мут чата, размут, очистка, варн;
  • бана / войс-мута / таймаута — нет;
  • лимиты: варн 1, мут/размут 3, чистка 10 /день.

v4: +warn; бан по-прежнему снят. Снимает хелпера с тяжёлых ACL.

Идемпотентно: маркер data/.helper_acl.v<N>.
"""
from __future__ import annotations

import json
import os

from logger import get_logger

_log = get_logger('helper_acl_seed')

HELPER_ROLE_ID = 948969471916249119
# Чат + варн. Бан / войс / таймаут — нет.
HELPER_ACTIONS = ('mute', 'purge', 'warn')
HELPER_LIMITS = {'clear': 10, 'mute': 3, 'unmute': 3, 'warn': 1}
SEED_VERSION = 4
MARKER = f'data/.helper_acl.v{SEED_VERSION}'
_DEMO_GUILD = 987654321098765432


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


def apply_helper_acl_seed(force=False, guild_id=None):
    """Выдать хелперу права ветки чата. Возвращает отчёт."""
    report = {
        'applied': False, 'reason': '', 'guild_id': 0,
        'actions_added': [], 'actions_removed': [],
        'cmd_acl': False, 'limits': False,
    }
    try:
        if str(os.environ.get('DEMO_MODE', '')).strip().lower() in (
                '1', 'true', 'yes', 'on'):
            report['reason'] = 'demo mode'
            return report
        if not force and os.path.exists(MARKER):
            report['reason'] = f'already applied (v{SEED_VERSION})'
            return report

        gid = _main_guild_id(guild_id)
        if not gid:
            report['reason'] = 'no MAIN_GUILD_ID'
            return report
        report['guild_id'] = gid
        helper = str(HELPER_ROLE_ID)

        from services.permission_acl import (
            ACTIONS, load_action_acl, save_action_acl)
        acl = load_action_acl(gid)
        if not isinstance(acl, dict):
            acl = {}
        for action in HELPER_ACTIONS:
            cur = [str(r) for r in (acl.get(action) or [])]
            if helper not in cur:
                cur.append(helper)
                acl[action] = cur
                report['actions_added'].append(action)
        for action in ACTIONS:
            if action in HELPER_ACTIONS:
                continue
            cur = [str(r) for r in (acl.get(action) or [])]
            if helper in cur:
                acl[action] = [r for r in cur if r != helper]
                report['actions_removed'].append(action)
        save_action_acl(gid, acl)

        try:
            from services.permission_acl import load_acl, set_rule
            cmd = load_acl(gid)
            if not isinstance(cmd, dict):
                cmd = {}
            existing = [str(r) for r in (cmd.get('modpanel') or [])]
            if existing:
                if helper not in existing:
                    existing.append(helper)
                    set_rule(gid, 'modpanel', existing)
                    report['cmd_acl'] = True
            else:
                roles = [helper]
                try:
                    with open('data/role_map.json', encoding='utf-8') as fh:
                        rm = json.load(fh) or {}
                    for rid, tier in rm.items():
                        if tier in ('helper', 'mod', 'master', 'curator',
                                    'admin', 'owner'):
                            roles.append(str(rid))
                except Exception:
                    pass
                seen, uniq = set(), []
                for r in roles:
                    if r not in seen:
                        seen.add(r)
                        uniq.append(r)
                set_rule(gid, 'modpanel', uniq)
                report['cmd_acl'] = True
        except Exception as ex:
            _log.warning('helper cmd_acl: %s', ex)

        try:
            from services.staff_limits import set_role_limits
            set_role_limits(
                gid, HELPER_ROLE_ID, who='helper_acl_seed',
                **HELPER_LIMITS)
            report['limits'] = True
        except Exception as ex:
            _log.warning('helper limits: %s', ex)

        try:
            os.makedirs('data', exist_ok=True)
            with open(MARKER, 'w', encoding='utf-8') as fh:
                fh.write('ok')
        except OSError as ex:
            _log.debug('helper marker: %s', ex)

        report['applied'] = True
        report['reason'] = 'ok'
        _log.info(
            'helper_acl_seed v%s: guild=%s +%s -%s cmd_acl=%s limits=%s',
            SEED_VERSION, gid, report['actions_added'],
            report['actions_removed'], report['cmd_acl'], report['limits'])
    except Exception as ex:
        report['reason'] = f'error: {ex}'
        _log.warning('apply_helper_acl_seed: %s', ex)
    return report
