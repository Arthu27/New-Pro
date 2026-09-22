# -*- coding: utf-8 -*-
"""Сид лестницы варнов: 3 варна → бан на 30 дней с авто-снятием.

Заказ владельца 2026-09-22. Не перетирает уже настроенную лестницу —
только если data/warn_config_<gid>.json пуст / без steps.
"""
from __future__ import annotations

import os

from logger import get_logger

_log = get_logger('warn_ladder_seed')

SEED_VERSION = 1
MARKER = f'data/.warn_ladder_seed.v{SEED_VERSION}'
_DEMO_GUILD = 987654321098765432

# 3 варна → бан 30 дней (авто-снятие роли / tempban)
DEFAULT_STEPS = [
    {'count': 3, 'action': 'ban', 'duration': 30, 'unit': 'day'},
]


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


def apply_warn_ladder_seed(force=False, guild_id=None):
    """Поставить дефолтную ступень 3→бан 30д, если лестница пуста."""
    report = {
        'applied': False, 'reason': '', 'guild_id': 0, 'seeded': False,
        'steps': list(DEFAULT_STEPS),
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

        from cogs.warnings import load_warn_config
        from cogs.ladder import _save_warn_config

        cfg = load_warn_config(str(gid))
        steps = list(cfg.get('steps') or cfg.get('thresholds') or [])
        if steps:
            report['reason'] = 'ladder already configured'
            report['applied'] = True
            try:
                os.makedirs('data', exist_ok=True)
                with open(MARKER, 'w', encoding='utf-8') as fh:
                    fh.write('ok')
            except OSError:
                pass
            return report

        cfg = {'steps': [dict(s) for s in DEFAULT_STEPS]}
        _save_warn_config(gid, cfg)
        report['seeded'] = True
        report['applied'] = True
        report['reason'] = 'ok'
        try:
            os.makedirs('data', exist_ok=True)
            with open(MARKER, 'w', encoding='utf-8') as fh:
                fh.write('ok')
        except OSError as ex:
            _log.debug('warn_ladder marker: %s', ex)
        _log.info('warn_ladder_seed v%s: guild=%s steps=%s',
                  SEED_VERSION, gid, DEFAULT_STEPS)
    except Exception as ex:
        report['reason'] = f'error: {ex}'
        _log.warning('apply_warn_ladder_seed: %s', ex)
    return report
