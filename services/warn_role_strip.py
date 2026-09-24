# -*- coding: utf-8 -*-
"""Одноразово снять роль warn со ВСЕХ участников (заказ 2026-09-24).

Роль warn теперь только для стаффа при ≥3 варнах (на неделю). Старые
выдачи обычным участникам (и стаффу с 1 варном) снимаем при старте бота.
Маркер data/.warn_strip.v1 — повторно не трогаем.
"""
from __future__ import annotations

import os

from logger import get_logger

_log = get_logger('warn_role_strip')

MARKER = 'data/.warn_strip.v1'


async def strip_warn_roles_once(bot, guild_id=None) -> dict:
    """Снять все выбранные warn-роли с участников гильдии (один раз)."""
    report = {'stripped': 0, 'roles': [], 'reason': '', 'applied': False}
    if os.path.exists(MARKER):
        report['reason'] = 'already applied'
        return report
    try:
        from services import punish_roles as PR
        from config import Config
    except Exception as _ex:
        report['reason'] = f'import: {_ex}'
        return report

    gid = int(guild_id or getattr(Config, 'MAIN_GUILD_ID', 0) or 0)
    if not gid:
        report['reason'] = 'no guild'
        return report
    guild = bot.get_guild(gid) if bot is not None else None
    if guild is None:
        report['reason'] = 'guild offline'
        return report

    levels = PR.warn_levels(PR.get(gid))
    role_ids = list(dict.fromkeys(int(v) for v in levels.values() if v))
    if not role_ids:
        # сид мог ещё не применить warn_3 — возьмём из config
        try:
            import json
            with open('config/role_seed.json', 'r', encoding='utf-8') as fh:
                seed = json.load(fh)
            rid = int(((seed.get('punish_roles') or {}).get('warn_3') or 0))
            if rid:
                role_ids = [rid]
        except Exception as _ex:
            _log.debug('seed fallback: %s', _ex)
    if not role_ids:
        report['reason'] = 'no warn roles configured'
        return report

    roles = [guild.get_role(rid) for rid in role_ids]
    roles = [r for r in roles if r is not None]
    report['roles'] = [r.id for r in roles]
    if not roles:
        report['reason'] = 'roles missing on guild'
        return report

    n = 0
    for member in list(getattr(guild, 'members', []) or []):
        have = [r for r in roles if r in (getattr(member, 'roles', None) or [])]
        if not have:
            continue
        try:
            await member.remove_roles(
                *have, reason='Warn-роль только для стаффа (≥3, 7 дней)')
            n += len(have)
            for r in have:
                try:
                    PR.clear(gid, member.id, r.id)
                except Exception:
                    pass
        except Exception as _ex:
            _log.debug('strip %s: %s', getattr(member, 'id', '?'), _ex)
    report['stripped'] = n
    report['applied'] = True
    report['reason'] = 'ok'
    try:
        os.makedirs('data', exist_ok=True)
        with open(MARKER, 'w', encoding='utf-8') as fh:
            fh.write('ok')
    except OSError as _ex:
        _log.debug('marker: %s', _ex)
    _log.info('warn strip: снято %s выдач ролей %s на гильдии %s',
              n, report['roles'], gid)
    return report
