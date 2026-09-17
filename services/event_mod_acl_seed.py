# -*- coding: utf-8 -*-
"""Сид прав роли Event Mod (заказ владельца 2026-09-17).

Роль 852634463535759461:
  • может вызывать /event-panel (публикация панели событий в канал);
  • кнопки модерации на панели событий (анонс / закрыть запись).

Идемпотентно: маркер data/.event_mod_acl.v<N>. Только ДОПИСЫВАЕТ роль
в cmd_acl event-panel, чужие роли не трогает.
"""
from __future__ import annotations

import os

from logger import get_logger

_log = get_logger('event_mod_acl_seed')

EVENT_MOD_ROLE_ID = 852634463535759461
SEED_VERSION = 1
MARKER = f'data/.event_mod_acl.v{SEED_VERSION}'
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


def apply_event_mod_acl_seed(force=False, guild_id=None):
    """Выдать event-mod права на /event-panel. Возвращает отчёт."""
    report = {
        'applied': False, 'reason': '', 'guild_id': 0,
        'cmd_acl': False, 'role_id': EVENT_MOD_ROLE_ID,
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
        event_mod = str(EVENT_MOD_ROLE_ID)

        try:
            from services.permission_acl import load_acl, set_rule
            cmd = load_acl(gid)
            if not isinstance(cmd, dict):
                cmd = {}
            existing = [str(r) for r in (cmd.get('event-panel') or [])]
            if existing:
                if event_mod not in existing:
                    existing.append(event_mod)
                    set_rule(gid, 'event-panel', existing)
                    report['cmd_acl'] = True
            else:
                # правила нет — команда открыта manage_guild; для явности
                # добавляем event-mod + персонал из role_map
                roles = [event_mod]
                try:
                    import json
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
                set_rule(gid, 'event-panel', uniq)
                report['cmd_acl'] = True
        except Exception as ex:
            _log.warning('event_mod cmd_acl: %s', ex)

        try:
            os.makedirs('data', exist_ok=True)
            with open(MARKER, 'w', encoding='utf-8') as fh:
                fh.write('ok')
        except OSError as ex:
            _log.debug('event_mod marker: %s', ex)

        report['applied'] = True
        report['reason'] = 'ok'
        _log.info(
            'event_mod_acl_seed v%s: guild=%s cmd_acl=%s role=%s',
            SEED_VERSION, gid, report['cmd_acl'], event_mod)
    except Exception as ex:
        report['reason'] = f'error: {ex}'
        _log.warning('apply_event_mod_acl_seed: %s', ex)
    return report
