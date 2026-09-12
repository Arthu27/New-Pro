# -*- coding: utf-8 -*-
"""Сид прав роли «Хелпер» (заказ владельца 2026-09-12).

Роль 948969471916249119:
  • может вызывать /modpanel;
  • в меню видит ТОЛЬКО «Мут» (чат) и «Очистка сообщений» — без бана,
    варна, войс-мута и таймаута;
  • лимит чисток как у модеров: 10/день.

Идемпотентно: маркер data/.helper_acl.v<N>. Не трогает чужие роли в ACL —
только ДОПИСЫВАЕТ helper к спискам mute/purge и к cmd_acl modpanel.
Лимиты роли ставит только если для helper ещё нет override.
"""
from __future__ import annotations

import json
import os

from logger import get_logger

_log = get_logger('helper_acl_seed')

HELPER_ROLE_ID = 948969471916249119
# action_acl ключи (permission_acl.ACTIONS): mute = чат-мут, purge = очистка
HELPER_ACTIONS = ('mute', 'purge')
HELPER_LIMITS = {'clear': 10, 'mute': 10, 'unmute': 10}
SEED_VERSION = 1
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
    """Выдать хелперу урезанные права /modpanel. Возвращает отчёт."""
    report = {
        'applied': False, 'reason': '', 'guild_id': 0,
        'actions_added': [], 'cmd_acl': False, 'limits': False,
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

        # 1) Action ACL: mute + purge
        from services.permission_acl import load_action_acl, save_action_acl
        acl = load_action_acl(gid)
        if not isinstance(acl, dict):
            acl = {}
        for action in HELPER_ACTIONS:
            cur = [str(r) for r in (acl.get(action) or [])]
            if helper not in cur:
                cur.append(helper)
                acl[action] = cur
                report['actions_added'].append(action)
        save_action_acl(gid, acl)

        # 2) Command ACL: /modpanel
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
                # правила нет — команда открыта; для явности добавим helper
                # вместе с ролями персонала из role_map (если есть)
                roles = [helper]
                try:
                    with open('data/role_map.json', encoding='utf-8') as fh:
                        rm = json.load(fh) or {}
                    for rid, tier in rm.items():
                        if tier in ('mod', 'curator', 'admin', 'owner'):
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

        # 3) Лимиты роли → role_scoped_actions сузит меню до clear/mute/unmute
        try:
            from services.staff_limits import get_role_overrides, set_role_limits
            ov = (get_role_overrides(gid) or {}).get(helper) or {}
            if not (ov.get('limits') or {}):
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
            'helper_acl_seed v%s: guild=%s actions=%s cmd_acl=%s limits=%s',
            SEED_VERSION, gid, report['actions_added'],
            report['cmd_acl'], report['limits'])
    except Exception as ex:
        report['reason'] = f'error: {ex}'
        _log.warning('apply_helper_acl_seed: %s', ex)
    return report
