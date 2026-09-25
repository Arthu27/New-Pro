# -*- coding: utf-8 -*-
"""Сид ACL «warn»: только куратор/админ (заказ 2026-09-24).

Хелпер/модер/мастер снимаются с действия warn. Маркер data/.warn_acl.v1.
"""
from __future__ import annotations

import os

from logger import get_logger

_log = get_logger('warn_acl_seed')

SEED_VERSION = 1
MARKER = f'data/.warn_acl.v{SEED_VERSION}'
_DEMO_GUILD = 987654321098765432
WARN_TIERS = frozenset({'curator', 'admin', 'owner'})
REVOKE_TIERS = frozenset({'helper', 'mod', 'master'})


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


def apply_warn_acl_seed(force=False, guild_id=None) -> dict:
    report = {
        'applied': False, 'reason': '', 'guild_id': 0,
        'added': [], 'removed': [],
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

        from services.permission_acl import load_action_acl, save_action_acl
        from services.staff_limits import _role_tier_map
        tmap = _role_tier_map() or {}
        allow = [rid for rid, tier in tmap.items() if tier in WARN_TIERS]
        revoke = {rid for rid, tier in tmap.items() if tier in REVOKE_TIERS}
        # known helper/mod
        try:
            from services.staff_roles import (
                KNOWN_HELPER_ROLE_ID, KNOWN_MODERATOR_ROLE_ID,
                KNOWN_MASTER_ROLE_ID)
            revoke.add(str(int(KNOWN_HELPER_ROLE_ID)))
            revoke.add(str(int(KNOWN_MODERATOR_ROLE_ID)))
            if KNOWN_MASTER_ROLE_ID:
                revoke.add(str(int(KNOWN_MASTER_ROLE_ID)))
        except Exception:
            pass

        acl = load_action_acl(gid)
        if not isinstance(acl, dict):
            acl = {}
        cur = [str(r) for r in (acl.get('warn') or [])]
        new = []
        seen = set()
        # оставить уже разрешённых curator/admin + добавить из карты
        for rid in list(cur) + list(allow):
            s = str(rid)
            if s in revoke:
                if s in cur:
                    report['removed'].append(s)
                continue
            # если cur пуст — сеем allow; если cur был — чистим revoke, keep rest
            if not cur and s not in allow:
                continue
            if s not in seen:
                seen.add(s)
                new.append(s)
                if s not in cur:
                    report['added'].append(s)
        # если после чистки пусто — поставить curator/admin
        if not new and allow:
            new = list(dict.fromkeys(allow))
            report['added'] = list(new)
        if new != cur:
            acl['warn'] = new
            save_action_acl(gid, acl)
        report['applied'] = True
        report['reason'] = 'ok'
        try:
            os.makedirs('data', exist_ok=True)
            with open(MARKER, 'w', encoding='utf-8') as fh:
                fh.write('ok')
        except OSError as _ex:
            _log.debug('marker: %s', _ex)
        _log.info('warn_acl v%s: +%s -%s', SEED_VERSION,
                  report['added'], report['removed'])
    except Exception as ex:
        report['reason'] = f'error: {ex}'
        _log.warning('apply_warn_acl_seed: %s', ex)
    return report
