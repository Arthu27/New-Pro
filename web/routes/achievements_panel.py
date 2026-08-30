# -*- coding: utf-8 -*-
"""Ачивки в панели (идея #5): витрина достижений сервера.

Читает то же хранилище GuildData('achievements'), что пишет ког, и считает
всё РОВНО теми же чистыми функциями кога: ACHIEVEMENTS / total_points /
user_record. Выдуманных переключателей нет: ког настраивается нечем,
поэтому страница честно read-only (mod+), как /crown.
"""

from web.routes._common import (
    _log,
    render_template, session, jsonify,
)

from db import GuildData
from cogs.achievements import (ACHIEVEMENTS_ENABLED, ACHIEVEMENTS,
                               total_points, user_record)


def _resolve_name(bot, gid, uid):
    """Имя из кэша бота; офлайн/не найден — честный фолбэк на ID."""
    if bot is not None:
        try:
            g = bot.get_guild(int(gid))
            m = g.get_member(int(uid)) if g else None
            if m is not None:
                return str(m.display_name)
        except Exception as _ex:
            _log.debug("achievements _resolve_name(): кэш недоступен: %s", _ex)
    return f'ID {uid}'


def achievements_payload(gid, bot=None):
    """Единая витрина достижений: каталог с охватом, топ и свежие открытия."""
    db = GuildData('achievements')
    gid = int(gid)
    per_key = {key: 0 for key in ACHIEVEMENTS}
    players = 0
    sum_points = 0
    sum_grants = 0
    top = []
    recent = []
    for raw_key in db.get_all_keys(gid) or []:
        if not raw_key.startswith('user_'):
            continue
        rec = db.get(gid, raw_key, user_record()) or user_record()
        grants = [g for g in (rec.get('grants') or []) if g in ACHIEVEMENTS]
        if not grants:
            continue
        players += 1
        pts = total_points(grants)
        sum_points += pts
        sum_grants += len(grants)
        uid = raw_key[5:]
        top.append((uid, pts, len(grants)))
        for key in grants:
            per_key[key] += 1
            ts = (rec.get('granted_at') or {}).get(key)
            if ts:
                recent.append((ts, uid, key))
    top.sort(key=lambda r: (-r[1], -r[2]))
    recent.sort(reverse=True)

    catalog = []
    for key, (name, desc, pts, _c) in ACHIEVEMENTS.items():
        owners = per_key[key]
        catalog.append({
            'key': key, 'name': name, 'desc': desc, 'points': pts,
            'owners': owners,
            'coverage': round(owners * 100 / players, 1) if players else 0,
        })
    rarest = min((c for c in catalog if c['owners'] > 0),
                 key=lambda c: c['owners'], default=None)
    commonest = max(catalog, key=lambda c: c['owners'], default=None)

    return {
        'success': True,
        'players': players,
        'sum_points': sum_points,
        'sum_grants': sum_grants,
        'catalog': catalog,
        'catalog_size': len(ACHIEVEMENTS),
        'rarest': {'name': rarest['name'], 'owners': rarest['owners']} if rarest else None,
        'commonest': {'name': commonest['name'], 'owners': commonest['owners']} if players else None,
        'top': [{'user_id': uid, 'name': _resolve_name(bot, gid, uid),
                 'points': pts, 'count': cnt} for uid, pts, cnt in top[:10]],
        'recent': [{'ts': ts, 'user_id': uid,
                    'name': _resolve_name(bot, gid, uid),
                    'ach_name': ACHIEVEMENTS[key][0],
                    'points': ACHIEVEMENTS[key][2]}
                   for ts, uid, key in recent[:12]],
    }


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required

    @app.route('/achievements')
    @login_required
    @role_required('mod')
    def achievements_page():
        return render_template('achievements.html', role=session.get('role'),
                               username=session.get('username'),
                               ach_off=not ACHIEVEMENTS_ENABLED)

    @app.route('/api/achievements/state')
    @login_required
    @role_required('mod')
    def api_achievements_state():
        import web.app as _app
        _gid = ctx.active_guild_id_int()
        if _gid is None:
            return jsonify({'success': False, 'error': 'Сервер не выбран (задайте MAIN_GUILD_ID в .env или дождитесь подключения бота)'}), 503
        return jsonify(achievements_payload(_gid,
                                            bot=_app.bot_instance))
