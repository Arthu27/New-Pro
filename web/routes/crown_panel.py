# -*- coding: utf-8 -*-
"""Зал корон в панели (идея #7): история чемпионов недели и серии побед.

История пишется самим когом weekly_crown в его же data/weekly_crown.json
(запись добавлена в crown_now). Панель только читает: править конфиг из
панели нельзя НАМЕРЕННО — ког держит in-memory копию стейта, и внешняя
запись файла была бы потеряна при следующем set_cfg. Настройки — /crown
в Discord (так честно написано и на странице).

Чтение — mod+.
"""

from web.routes._common import (
    _log,
    render_template, session, jsonify,
)

from cogs import weekly_crown as W


def _resolve_name(bot, gid, uid):
    if bot is not None and uid:
        try:
            g = bot.get_guild(int(gid))
            m = g.get_member(int(uid)) if g else None
            if m is not None:
                return str(m.display_name)
        except Exception as _ex:
            _log.debug("_resolve_name(): кэш недоступен: %s", _ex)
    return f'ID {uid}'


def crown_payload(gid, bot=None):
    """Картина корон: держатель, настройки, история с именами, серии."""
    data = W._load()
    cfg = data.get(str(gid), {}) if isinstance(data, dict) else {}
    history = [h for h in (cfg.get('history') or []) if isinstance(h, dict)]
    streaks = W.crown_streaks(history)
    rows = []
    for h in reversed(history):  # свежие сверху
        uid = h.get('uid')
        rows.append({
            'week': str(h.get('week', '?')),
            'uid': str(uid or ''),
            'name': _resolve_name(bot, gid, uid),
            'dm': int(h.get('dm') or 0),
            'dv': int(h.get('dv') or 0),
            'score': int(h.get('score') or 0),
            'ts': str(h.get('ts', '')),
        })
    holder = int(cfg.get('holder_id') or 0)
    return {
        'success': True,
        'enabled': bool(cfg.get('enabled', True)),
        'tz_offset': int(cfg.get('tz_offset', 3) or 3),
        'last_week': str(cfg.get('last_week', '')),
        'holder_id': str(holder or ''),
        'holder_name': _resolve_name(bot, gid, holder) if holder else '',
        'history': rows,
        'total': len(rows),
        'current_streak': {'uid': str(streaks['current_uid'] or ''),
                           'name': _resolve_name(bot, gid, streaks['current_uid'])
                           if streaks['current_uid'] else '',
                           'n': streaks['current']},
        'best_streak': {'uid': str(streaks['best_uid'] or ''),
                        'name': _resolve_name(bot, gid, streaks['best_uid'])
                        if streaks['best_uid'] else '',
                        'n': streaks['best']},
    }


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required

    @app.route('/crown')
    @login_required
    @role_required('mod')
    def crown_page():
        return render_template('crown.html', role=session.get('role'),
                               username=session.get('username'))

    @app.route('/api/crown/state')
    @login_required
    @role_required('mod')
    def api_crown_state():
        import web.app as _app
        return jsonify(crown_payload(ctx.active_guild_id(), bot=_app.bot_instance))
