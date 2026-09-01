# -*- coding: utf-8 -*-
"""Панель: верификация участников с молодыми аккаунтами.

Источник правды — конфиг кога cogs/age_verification.py:
  data/verify_<guild_id>.json — настройки (включённость, порог, роли, каналы)
  data/verify_db.sqlite        — заявки на карантине / на рассмотрении

API:
  GET  /api/guild/<gid>/verify/config
  POST /api/guild/<gid>/verify/config   (сохранить настройки)
  GET  /api/guild/<gid>/verify/pending  (список заявок для модерации)
"""

from flask import request, session, jsonify, render_template

from logger import get_logger

_log = get_logger('verify_panel')


def load_cfg(gid):
    import json as _json
    import os
    p = os.path.join('data', f'verify_{gid}.json')
    base = {
        'enabled': False, 'min_age_days': 2, 'quarantine_role_id': '',
        'member_role_id': '', 'verify_channel_id': '', 'review_channel_id': '',
        'kick_after_days': 1,
    }
    try:
        with open(p, encoding='utf-8') as f:
            data = _json.load(f)
        if isinstance(data, dict):
            base.update({k: data[k] for k in base if k in data})
    except FileNotFoundError:
        _log.debug('verify panel: конфиг %s ещё не создан — дефолт', p)
    except Exception as ex:
        _log.debug('verify panel load_cfg(%s): %s', gid, ex)
    return base


def save_cfg(gid, cfg):
    import json as _json
    import os
    os.makedirs('data', exist_ok=True)
    p = os.path.join('data', f'verify_{gid}.json')
    with open(p + '.tmp', 'w', encoding='utf-8') as f:
        _json.dump(cfg, f, ensure_ascii=False, indent=2)
    os.replace(p + '.tmp', p)


def list_pending(gid):
    """Заявки из sqlite: карантин/анкета — для таблицы модерации в панели."""
    import sqlite3
    import os
    import json as _json
    p = os.path.join('data', 'verify_db.sqlite')
    if not os.path.exists(p):
        return []
    out = []
    try:
        conn = sqlite3.connect(p)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM pending WHERE guild_id=? ORDER BY quarantined_at DESC",
            (str(gid),)).fetchall()
        conn.close()
        for r in rows:
            d = dict(r)
            try:
                d['answers'] = _json.loads(d.get('answers') or 'null')
            except Exception:
                d['answers'] = None
            out.append(d)
    except Exception as ex:
        _log.debug('verify panel list_pending(%s): %s', gid, ex)
    return out


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required
    active_guild_id = ctx.active_guild_id

    @app.route('/verify')
    @login_required
    @role_required('mod')
    def verify_page():
        return render_template('verification.html', role=session.get('role'),
                               username=session.get('username'),
                               guild_id=active_guild_id())

    @app.route('/api/guild/<gid>/verify/config')
    @login_required
    @role_required('mod')
    def api_verify_config(gid):
        return jsonify({'success': True, 'config': load_cfg(gid),
                        'pending': list_pending(gid)})

    @app.route('/api/guild/<gid>/verify/config', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_verify_save(gid):
        body = request.get_json(silent=True) or {}
        cfg = load_cfg(gid)

        def _as_id(v):
            v = str(v or '').strip().replace('<#', '').replace('<@&', '').replace('>', '')
            return v if v.isdigit() else ''

        cfg['enabled'] = bool(body.get('enabled', cfg['enabled']))
        try:
            days = int(body.get('min_age_days', cfg['min_age_days']))
            cfg['min_age_days'] = max(0, min(365, days))
        except (TypeError, ValueError):
            _log.debug('verify panel: кривой min_age_days=%r — оставляю %s',
                       body.get('min_age_days'), cfg['min_age_days'])
        try:
            kick = int(body.get('kick_after_days', cfg['kick_after_days']))
            cfg['kick_after_days'] = max(0, min(30, kick))
        except (TypeError, ValueError):
            _log.debug('verify panel: кривой kick_after_days=%r — оставляю %s',
                       body.get('kick_after_days'), cfg['kick_after_days'])
        for key in ('quarantine_role_id', 'member_role_id',
                    'verify_channel_id', 'review_channel_id'):
            if key in body:
                cfg[key] = _as_id(body.get(key))
        save_cfg(gid, cfg)
        return jsonify({'success': True, 'config': cfg})
