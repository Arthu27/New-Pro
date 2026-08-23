# -*- coding: utf-8 -*-
"""Настройки модерации: лестница авто-наказаний + исключения временных мер.

Живые хранилища (те же, что читает бот — меняешь в панели, бот применяет):
- data/warn_config_<gid>.json, ключ 'steps' — лестница «N варнов → мера»
  (командный формат ladder-add: мут N мин/ч/дн, кик, бан); рендер подписи —
  cogs.ladder._fmt_step, так что в панели и в Discord текст одинаковый.
- data/temp_whitelist.json, ключ str(gid) — кого временные меры (tempmute/
  tempban/tempkick) не трогают вообще (администраторы всегда вне списка).

Доступ: страница и изменение — Админ+ (как остальные рискованные настройки).
"""
import json
import os

from web.routes._common import (
    _log, _fire_panel_notification,
    render_template, session, request, jsonify,
)

from cogs import ladder as LD
from cogs.warnings import load_warn_config

ACTIONS = ('mute', 'kick', 'ban')
ACTION_LABELS = {'mute': 'Мут', 'kick': 'Кик', 'ban': 'Бан'}
UNITS = (('minute', 'минут'), ('hour', 'часов'), ('day', 'дней'))
TEMP_WHITELIST_PATH = 'data/temp_whitelist.json'
MAX_STEPS = 20
_ID_MIN, _ID_MAX = 17, 22


def _gid(ctx):
    try:
        return int(ctx.active_guild_id() or 0)
    except (TypeError, ValueError):
        return 0


def steps_view(gid):
    """Ступени лестницы с русскими подписями (формат кога 1:1)."""
    cfg = load_warn_config(str(gid))
    raw = cfg.get('steps') or cfg.get('thresholds') or []
    out = []
    seen = set()
    for st in sorted(raw, key=lambda s: int(s.get('count', 0) or 0)):
        count = int(st.get('count', 0) or 0)
        if not count or count in seen:
            continue
        seen.add(count)
        out.append({'count': count,
                    'action': str(st.get('action', 'mute')),
                    'duration': int(st.get('duration', 0) or 0),
                    'unit': str(st.get('unit', 'minute')),
                    'label': LD._fmt_step(st)})
    return out


def normalize_steps(raw):
    """Принять лестницу целиком: уникальные числа, клампы, кик без длительности."""
    if not isinstance(raw, list):
        return []
    out = []
    seen = set()
    for st in raw:
        if not isinstance(st, dict):
            continue
        try:
            count = int(st.get('count', 0) or 0)
        except (TypeError, ValueError):
            count = 0
        if count < 1:                    # «0 варнов» — не ступень, выкидываем
            continue
        if count > 100:
            count = 100
        if count in seen:
            continue
        seen.add(count)
        action = str(st.get('action', 'mute'))
        if action not in ACTIONS:
            action = 'mute'
        try:
            duration = int(st.get('duration', 0) or 0)
        except (TypeError, ValueError):
            duration = 0
        duration = max(0, min(10000, duration))
        unit = str(st.get('unit', 'minute'))
        if unit not in dict(UNITS):
            unit = 'minute'
        if action == 'kick':
            duration = 0
        out.append({'count': count, 'action': action,
                    'duration': duration, 'unit': unit})
        if len(out) >= MAX_STEPS:
            break
    out.sort(key=lambda s: s['count'])
    return out


def save_steps(gid, steps):
    cfg = load_warn_config(str(gid))
    if not isinstance(cfg, dict):
        cfg = {}
    cfg['steps'] = normalize_steps(steps)
    LD._save_warn_config(int(gid), cfg)
    return cfg


def temp_whitelist(gid):
    try:
        with open(TEMP_WHITELIST_PATH, 'r', encoding='utf-8') as fp:
            data = json.load(fp)
        row = data.get(str(gid), [])
        return [str(x) for x in row] if isinstance(row, list) else []
    except (OSError, ValueError):
        return []


def save_temp_whitelist(gid, ids):
    clean = []
    for x in ids or ():
        s = str(x).strip()
        if not (s.isdigit() and _ID_MIN <= len(s) <= _ID_MAX):
            continue
        if s in clean:
            continue
        clean.append(s)
        if len(clean) >= 200:
            break
    try:
        with open(TEMP_WHITELIST_PATH, 'r', encoding='utf-8') as fp:
            data = json.load(fp)
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}
    data[str(gid)] = clean
    os.makedirs('data', exist_ok=True)
    tmp = TEMP_WHITELIST_PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)
    os.replace(tmp, TEMP_WHITELIST_PATH)
    return clean


def mod_view(gid):
    steps = steps_view(gid)
    return {
        'steps': steps,
        'actions': [{'key': k, 'label': v} for k, v in ACTION_LABELS.items()],
        'units': [{'key': k, 'label': v} for k, v in UNITS],
        'temp_whitelist': temp_whitelist(gid),
        'max_steps': MAX_STEPS,
    }


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required

    @app.route('/mod-settings')
    @login_required
    @role_required('admin')
    def mod_settings_page():
        return render_template('mod_settings.html',
                               role=session.get('role'),
                               username=session.get('username'),
                               guild_id=_gid(ctx))

    @app.route('/api/guild/<gid>/mod-settings', methods=['GET', 'POST'])
    @login_required
    @role_required('admin')
    def api_mod_settings(gid):
        gid = _gid(ctx)
        if not gid:
            try:
                gid = int(gid)
            except (TypeError, ValueError):
                gid = 0
        if request.method == 'GET':
            return jsonify({'success': True, 'cfg': mod_view(gid)})

        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({'success': False,
                            'error': 'Пустой или битый JSON'}), 400
        who = session.get('username', '?')
        if 'steps' in data:
            save_steps(gid, data.get('steps'))
            _fire_panel_notification(
                'mod_settings', 'Настройки модерации: лестница обновлена',
                f'{who}: ступеней — {len(steps_view(gid))}')
        if 'temp_whitelist' in data:
            save_temp_whitelist(gid, data.get('temp_whitelist'))
            _fire_panel_notification(
                'mod_settings', 'Исключения временных мер обновлены',
                f'{who}: в списке — {len(temp_whitelist(gid))}')
        return jsonify({'success': True, 'cfg': mod_view(gid)})
