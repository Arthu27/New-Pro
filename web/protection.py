# -*- coding: utf-8 -*-
"""Загрузки/сохранения защит сервера для панели Антикраш (opt-in)."""
from __future__ import annotations

import json
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / 'data'


def gid_int(raw) -> int:
    try:
        return int(raw) if raw else 0
    except Exception:
        return 0


def read_json(path, default=None):
    p = Path(path)
    if not p.exists():
        return {} if default is None else default
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return {} if default is None else default


def load_antiraid(gid: int) -> dict:
    from cogs.antiraid import GuildAntiraidConfig
    if not gid:
        return dict(GuildAntiraidConfig.DEFAULTS)
    return dict(GuildAntiraidConfig(gid).data)


def save_antiraid(gid: int, data: dict) -> dict:
    from cogs.antiraid import GuildAntiraidConfig
    DATA.mkdir(parents=True, exist_ok=True)
    base = dict(GuildAntiraidConfig.DEFAULTS)
    base.update(data or {})
    base['recent_events'] = list((data or {}).get('recent_events') or [])[:20]
    path = DATA / f'antiraid_{gid}.json'
    path.write_text(json.dumps(base, ensure_ascii=False, indent=2), encoding='utf-8')
    return base


def load_security(gid: int) -> dict:
    from cogs import security as SEC
    if not gid:
        return dict(SEC._CFG_DEFAULT)
    return SEC._load_cfg(str(gid))


def save_security(gid: int, data: dict) -> dict:
    from cogs import security as SEC
    SEC._save_cfg(str(gid), data)
    return data


def load_guardian(gid: int) -> dict:
    from cogs import guardian as G
    if not gid:
        return G.guardian_default()
    return G.load_cfg(gid)


def save_guardian(gid: int, data: dict) -> dict:
    from cogs import guardian as G
    clean = G.guardian_normalize(data)
    G.save_cfg(gid, clean)
    return clean


def kill_all_protections(gid: int, bot_instance=None) -> None:
    """Выключить ВСЕ защиты сервера и watchdog бота."""
    gu = load_guardian(gid)
    gu['enabled'] = False
    gu['kick_unauthorized_bots'] = False
    for ev in (gu.get('events') or {}).values():
        if isinstance(ev, dict):
            ev['enabled'] = False
    if gid:
        save_guardian(gid, gu)

    ar = load_antiraid(gid)
    for k, v in list(ar.items()):
        if isinstance(v, bool):
            ar[k] = False
    if gid:
        save_antiraid(gid, ar)

    sec = load_security(gid)
    for k in ('ai_spam', 'fake_account', 'link_scanner'):
        sec[k] = False
    if gid:
        save_security(gid, sec)

    eh = getattr(bot_instance, 'error_handler', None) if bot_instance else None
    if eh:
        eh.update_config('master_enabled', False)
    else:
        cfg = read_json(DATA / 'anticrash_config.json', {})
        if not isinstance(cfg, dict):
            cfg = {}
        cfg['master_enabled'] = False
        DATA.mkdir(parents=True, exist_ok=True)
        (DATA / 'anticrash_config.json').write_text(
            json.dumps(cfg, ensure_ascii=False, indent=2), encoding='utf-8')


def snapshot(gid: int, bot_instance=None) -> dict:
    from cogs import guardian as G
    from cogs.antiraid import GuildAntiraidConfig

    ar = load_antiraid(gid)
    sec = load_security(gid)
    gu = load_guardian(gid)

    try:
        from error_handler import DEFAULT_CONFIG, CONFIG_META
        bot_cfg = dict(DEFAULT_CONFIG)
        bot_meta = CONFIG_META
    except Exception:
        bot_cfg, bot_meta = {}, {}

    eh = getattr(bot_instance, 'error_handler', None) if bot_instance else None
    bot_ov = {}
    if eh:
        try:
            bot_ov = eh.get_overview() or {}
        except Exception:
            bot_ov = {'ok': False}
        bot_cfg = dict(getattr(eh, 'config', None) or bot_cfg)
    else:
        disk = read_json(DATA / 'anticrash_config.json', {})
        if isinstance(disk, dict):
            bot_cfg.update(disk)
        bot_ov = {'ok': False, 'master_enabled': bool(bot_cfg.get('master_enabled'))}

    ar_on = any(
        bool(ar.get(k))
        for k, v in GuildAntiraidConfig.DEFAULTS.items()
        if isinstance(v, bool)
    )
    sec_on = any(bool(sec.get(k)) for k in ('ai_spam', 'fake_account', 'link_scanner'))
    gu_on = bool(gu.get('enabled'))
    bot_on = bool(bot_cfg.get('master_enabled'))

    return {
        'antiraid': ar,
        'security': sec,
        'guardian': gu,
        'guardian_specs': list(G.EVENT_SPECS),
        'bot_overview': bot_ov,
        'bot_config': bot_cfg,
        'bot_meta': bot_meta,
        'flags': {
            'antiraid': ar_on,
            'security': sec_on,
            'guardian': gu_on,
            'bot': bot_on,
            'any': ar_on or sec_on or gu_on or bot_on,
        },
    }
