# -*- coding: utf-8 -*-
"""Карма-панель (идеи #51-55): зал благодарностей, лента, тёплые пары,
накрутка-детектор, корректировка очков.

Хранилище одно на двоих с ботом: GuildData('karma'), ключ 'state'
({'scores': {uid: pts}, 'thanks': [{giver, target, at, reason}]}),
пишет cogs/karma.py. Арифметика — его чистые функции (top_rows,
apply_rep, get_score) без переписываний.

Чтение и экспорт — mod+, корректировка очков — admin+.
"""
from collections import Counter
from datetime import datetime, timedelta

from web.routes._common import (
    _log,
    render_template, session, request, jsonify, Response,
)

from web.routes.analytics_plus import _parse_ts
from web.routes.mod_control import validate_user_id, names_from_audit

from cogs import karma as KC

FEED_DAYS = 7
FEED_LIMIT = 30
PAIRS_DAYS = 7
PAIRS_MIN = 2
FARM_MIN = 3          # взаимные веер-благодарности за окно — «фермерская пара»
ADJUST_LIMIT = 500    # разовая корректировка, ±


def _db():
    from db import GuildData
    return GuildData('karma')


def _state(gid):
    return _db().get(gid, 'state', KC.empty_state()) or KC.empty_state()


def _thanks_in(state, now=None, days=FEED_DAYS):
    """Журналные записи окна: [(dt, raw)], свежие первыми."""
    now = now or datetime.now()
    cutoff = now - timedelta(days=days)
    out = []
    for th in (state or {}).get('thanks', []):
        if not isinstance(th, dict):
            continue
        dt = _parse_ts(th.get('at'))
        if dt is None or dt < cutoff:
            continue
        giver = str(th.get('giver') or '')
        target = str(th.get('target') or '')
        if not giver or not target:
            continue
        out.append((dt, giver, target, str(th.get('reason') or '').strip()))
    out.sort(key=lambda r: r[0], reverse=True)
    return out


def karma_snapshot(state, names=None, now=None, days=FEED_DAYS):
    """Сводка зала: топ по очкам (top_rows кога), итоги, активность окна."""
    names = names or {}
    top = [{'user_id': str(uid), 'name': str(names.get(str(uid)) or ''), 'score': score}
           for uid, score in KC.top_rows(state, limit=10)]
    scores = (state or {}).get('scores', {})
    points = sum(int(v) for v in scores.values()
                 if isinstance(v, int) or str(v).lstrip('-').isdigit())
    window = _thanks_in(state, now=now, days=days)
    return {
        'top': top,
        'people': len(scores),
        'points_total': points,
        'thanks_total': len((state or {}).get('thanks', [])),
        'thanks_window': len(window),
        'days': days,
        'leader': top[0] if top else None,
    }


def thanks_feed(state, names=None, now=None, days=FEED_DAYS,
                limit=FEED_LIMIT, user_id=None):
    """Лента благодарностей окна, опционально по участнику (любая сторона)."""
    names = names or {}
    rows = []
    for dt, giver, target, reason in _thanks_in(state, now=now, days=days):
        if user_id and user_id not in (giver, target):
            continue
        rows.append({
            'giver': giver, 'giver_name': str(names.get(giver) or ''),
            'target': target, 'target_name': str(names.get(target) or ''),
            'reason': reason,
            'at': dt.isoformat(timespec='minutes'),
        })
        if len(rows) >= max(1, int(limit)):
            break
    return rows


def warm_pairs(state, now=None, days=PAIRS_DAYS, min_count=PAIRS_MIN):
    """Тёплые связки окна + «фермерские пары» (взаимный фарм >= FARM_MIN)."""
    direct = Counter()
    for _dt, giver, target, _reason in _thanks_in(state, now=now, days=days):
        direct[(giver, target)] += 1
    pairs = []
    seen = set()
    for (giver, target), cnt in sorted(direct.items(), key=lambda kv: (-kv[1], kv[0])):
        if cnt < min_count:
            continue
        back = direct.get((target, giver), 0)
        key = (target, giver)
        mutual = back > 0
        if mutual and key in seen:
            continue
        seen.add((giver, target))
        pairs.append({
            'giver': giver, 'target': target, 'count': cnt,
            'back': back,
            'farming': mutual and cnt >= FARM_MIN and back >= FARM_MIN,
        })
    pairs.sort(key=lambda p: (-(p['farming']), -(p['count'] + p['back']), p['giver']))
    return pairs


def adjust_score(state, user_id, delta):
    """Корректировка очков 1:1 с арифметикой кога (apply_rep).

    -> (ok, err, new_total). delta — целое, не ноль, |delta| <= ADJUST_LIMIT.
    """
    ok, err, uid = validate_user_id(user_id)
    if not ok:
        return False, err, None
    try:
        delta = int(delta)
    except (TypeError, ValueError):
        return False, 'Корректировка — целое число', None
    if delta == 0:
        return False, 'Корректировка не бывает нулевой', None
    if abs(delta) > ADJUST_LIMIT:
        return False, 'Разом — не больше ±%d' % ADJUST_LIMIT, None
    total = KC.apply_rep(state, uid, delta)
    return True, '', total


# ─────────────────────────────────────────────────────────────────────
# Маршруты
# ─────────────────────────────────────────────────────────────────────
def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required
    active_guild_id = ctx.active_guild_id

    @app.route('/karma')
    @login_required
    @role_required('mod')
    def karma_page():
        return render_template('karma.html', role=session.get('role'),
                               username=session.get('username'),
                               guild_id=active_guild_id())

    @app.route('/api/guild/<gid>/karma/overview')
    @login_required
    @role_required('mod')
    def api_karma_overview(gid):
        state = _state(gid)
        names = names_from_audit(gid)
        uid_filter = request.args.get('user')
        if uid_filter:
            ok, _err, uid_filter = validate_user_id(uid_filter)
            if not ok:
                uid_filter = None
        pairs = warm_pairs(state)
        for p in pairs:
            p['giver_name'] = str(names.get(p['giver']) or '')
            p['target_name'] = str(names.get(p['target']) or '')
        return jsonify({
            'success': True,
            'snapshot': karma_snapshot(state, names=names),
            'feed': thanks_feed(state, names=names, user_id=uid_filter),
            'feed_filter': uid_filter,
            'pairs': pairs,
            'can_edit': session.get('role') in ('admin', 'owner'),
        })

    @app.route('/api/guild/<gid>/karma/adjust', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_karma_adjust(gid):
        from web.routes._common import _fire_panel_notification
        data = request.get_json(silent=True) or {}
        ok, err, uid = validate_user_id(data.get('user_id'))
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        state = _state(gid)
        ok, err, total = adjust_score(state, uid, data.get('delta'))
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        _db().set(gid, 'state', state)
        try:
            delta_int = int(data.get('delta'))
        except (TypeError, ValueError):
            delta_int = 0  # в adjust_score уже провалидировано — это для подписи
        try:
            _fire_panel_notification(
                'karma', f'Карма: {uid} скорректирована ({delta_int:+d})',
                f'Через панель ({session.get("username", "?")}), сервер {gid}')
        except Exception as _ex:
            _log.debug('karma: уведомление не ушло: %s', _ex)
        return jsonify({'success': True, 'user_id': uid, 'total': total,
                        'snapshot': karma_snapshot(state,
                                                   names=names_from_audit(gid))})

    @app.route('/api/guild/<gid>/karma/export.csv')
    @login_required
    @role_required('mod')
    def api_karma_export(gid):
        state = _state(gid)
        names = names_from_audit(gid)
        rows = KC.top_rows(state, limit=100000)
        lines = ['rank;user_id;name;score']
        for rank, (uid, score) in enumerate(rows, 1):
            name = str(names.get(str(uid)) or '').replace(';', ',')
            lines.append('%d;%d;%s;%d' % (rank, uid, name, score))
        body = '\ufeff' + '\n'.join(lines) + '\n'
        return Response(body, mimetype='text/csv; charset=utf-8',
                        headers={'Content-Disposition':
                                 'attachment; filename="karma_%s.csv"' % gid})
