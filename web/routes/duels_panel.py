# -*- coding: utf-8 -*-
"""Дуэльная арена в панели (идея #4): статистика дуэлей сервера.

Читает то же хранилище GuildData('duels'), ключ 'state', что пишет ког,
и считает РОВНО чистыми функциями кога: top_duels / player_stats /
empty_state. Настройки у кога нет — страница честно read-only (mod+),
без выдуманных переключателей.
"""

from web.routes._common import (
    _log,
    render_template, session, jsonify,
)

from db import GuildData
from cogs.duels import empty_state, player_stats, top_duels


def _resolve_name(bot, gid, uid):
    """Имя из кэша бота; офлайн/не найден — честный фолбэк на ID."""
    if bot is not None:
        try:
            g = bot.get_guild(int(gid))
            m = g.get_member(int(uid)) if g else None
            if m is not None:
                return str(m.display_name)
        except Exception as _ex:
            _log.debug("duels _resolve_name(): кэш недоступен: %s", _ex)
    return f'ID {uid}'


def duels_payload(gid, bot=None):
    """Витрина арены: KPI, топ, горячие серии, свежие бои."""
    state = GuildData('duels').get(int(gid), 'state', empty_state()) or empty_state()
    players_raw = state.get('players') or {}

    top = []
    for uid, _wins, _losses in top_duels(state, limit=10):
        st = player_stats(state, uid)
        if not st:
            continue
        top.append({'user_id': uid, 'name': _resolve_name(bot, gid, uid), **st})

    hot = []
    recent = []
    for uid, rec in players_raw.items():
        if not str(uid).isdigit():
            continue
        st = player_stats(state, uid)
        if not st or not st['total']:
            continue
        if st['streak'] >= 2:
            hot.append({'user_id': int(uid), 'name': _resolve_name(bot, gid, uid),
                        'streak': st['streak']})
        if rec.get('last_at'):
            recent.append({'ts': rec['last_at'],
                           'user_id': int(uid),
                           'name': _resolve_name(bot, gid, uid),
                           'summary': f"{st['wins']}:{st['losses']}"})
    hot.sort(key=lambda r: -r['streak'])
    recent.sort(key=lambda r: r['ts'], reverse=True)

    best_ever = 0
    for rec in players_raw.values():
        try:
            best_ever = max(best_ever, int(rec.get('best_streak', 0) or 0))
        except (TypeError, ValueError) as _ex:
            _log.debug("duels best_streak: битое значение пропущено: %s", _ex)
            continue

    return {
        'success': True,
        'total_duels': int(state.get('total', 0) or 0),
        'players': sum(1 for rec in players_raw.values()
                       if (rec or {}).get('wins', 0) + (rec or {}).get('losses', 0) > 0),
        'best_streak_ever': best_ever,
        'hot_count': len(hot),
        'top': top,
        'hot': hot[:8],
        'recent': recent[:10],
    }


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required

    @app.route('/duels')
    @login_required
    @role_required('mod')
    def duels_page():
        return render_template('duels.html', role=session.get('role'),
                               username=session.get('username'))

    @app.route('/api/duels/state')
    @login_required
    @role_required('mod')
    def api_duels_state():
        import web.app as _app
        _gid = ctx.active_guild_id_int()
        if _gid is None:
            return jsonify({'success': False, 'error': 'Сервер не выбран (задайте MAIN_GUILD_ID в .env или дождитесь подключения бота)'}), 503
        return jsonify(duels_payload(_gid,
                                     bot=_app.bot_instance))
