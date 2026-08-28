# -*- coding: utf-8 -*-
"""Панель «Оценки персонала» (идеи #101-105): таблица рейтинга, зачётка
модератора с гистограммой и голосующими, снятие голоса, выгрузка.

Хранилище одно на двоих с ботом: GuildData('staff_rating'), ключ 'state'
({'staff': {uid: {'votes': {voter: score}, 'comments': [...}]}}),
пишет cogs/staff_rating.py. Арифметика — его чистые функции
(rating_rows, staff_summary, score_stars, _avg) без переписываний;
звёзды приезжают данными (в шаблоне их нет — политика).

Чтение и выгрузка — mod+, снятие голосов — admin+.
"""
from web.routes._common import (
    _log,
    render_template, session, request, jsonify, Response,
)

from web.routes.mod_control import validate_user_id, names_from_audit

from cogs import staff_rating as SR

CARD_COMMENTS = 30   # столько последних комментариев хранит ког — все покажем


def _db():
    from db import GuildData
    return GuildData('staff_rating')


def _state(gid):
    return _db().get(gid, 'state', SR.empty_state()) or SR.empty_state()


def rating_table(state, names=None, limit=1000):
    """Таблица 1:1 с rating_rows кога + имена и звёзды (данные, не шаблон)."""
    names = names or {}
    rows = []
    for rank, (uid, avg, n) in enumerate(SR.rating_rows(state, limit=limit), 1):
        rows.append({'rank': rank, 'staff_id': str(uid), 'avg': avg,
                     'votes': n, 'stars': SR.score_stars(avg),
                     'name': str(names.get(str(uid)) or '')})
    return rows


def overview_stats(state, names=None):
    """Сводка команды: общий балл по всем голосам, голосов, с оценками, лидер."""
    combined = {}
    for sid, staff in (state or {}).get('staff', {}).items():
        if not str(sid).isdigit():
            continue  # мусорные ключи ког не показывает — сводка тоже без них
        for vid, score in (staff.get('votes') or {}).items():
            combined[f'{sid}:{vid}'] = score
    lead = rating_table(state, names=names, limit=1)
    return {
        'team_avg': round(SR._avg(combined), 2),
        'votes_total': len(combined),
        'staff_rated': len([1 for sid, s in (state or {}).get('staff', {}).items()
                            if str(sid).isdigit() and s.get('votes')]),
        'leader': lead[0] if lead else None,
    }


def score_distribution(votes):
    """Гистограмма оценок 1..5 (кривые значения ког игнорирует — и у нас)."""
    dist = {str(i): 0 for i in range(1, 6)}
    for score in (votes or {}).values():
        if isinstance(score, int) and not isinstance(score, bool) \
                and 1 <= score <= 5:
            dist[str(score)] += 1
    return dist


def staff_card(state, staff_id, names=None):
    """Зачётка: summary кога + свежие комментарии, гистограмма, голосующие.
    None, если голосов нет (как staff_summary кога)."""
    summary = SR.staff_summary(state, staff_id)
    if summary is None:
        return None
    names = names or {}
    staff = state['staff'][str(staff_id)]
    votes = staff.get('votes', {})
    comments = []
    for c in reversed((summary.get('comments') or [])[-CARD_COMMENTS:]):
        comments.append({'voter': str(c.get('voter') or ''),
                         'voter_name': str(names.get(str(c.get('voter'))) or ''),
                         'score': c.get('score'),
                         'text': str(c.get('text') or ''),
                         'at': str(c.get('at') or '')[:16].replace('T', ' ')})
    voters = sorted(({'voter': vid, 'score': score,
                      'name': str(names.get(vid) or '')}
                     for vid, score in votes.items()),
                    key=lambda v: (-(v['score'] if isinstance(v['score'], int)
                                     else 0), v['voter']))
    return {
        'staff_id': str(staff_id),
        'name': str(names.get(str(staff_id)) or ''),
        'avg': summary['avg'],
        'votes': summary['votes'],
        'stars': SR.score_stars(summary['avg']),
        'distribution': score_distribution(votes),
        'comments': comments,
        'voters': voters,
    }


def remove_vote(state, staff_id, voter_id=None):
    """Снять голос (или всю зачётку). -> (ok, err, removed_votes).
    Комментарии этого голосующего уходят вместе с голосом."""
    staff = (state or {}).get('staff', {}).get(str(staff_id))
    if not staff or not staff.get('votes'):
        return False, 'Модератор без оценок не найден', 0
    if voter_id is None:
        removed = len(staff['votes'])
        state['staff'].pop(str(staff_id))
        return True, '', removed
    voter_id = str(voter_id)
    if voter_id not in staff['votes']:
        return False, 'Голос не найден', 0
    staff['votes'].pop(voter_id)
    staff['comments'] = [c for c in staff.get('comments', [])
                         if str(c.get('voter')) != voter_id]
    if not staff['votes']:
        state['staff'].pop(str(staff_id))
    return True, '', 1


# ─────────────────────────────────────────────────────────────────────
# Маршруты
# ─────────────────────────────────────────────────────────────────────
def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required
    active_guild_id = ctx.active_guild_id

    def _notify(title):
        from web.routes._common import _fire_panel_notification
        try:
            _fire_panel_notification(
                'mod_action', title,
                f'Через панель ({session.get("username", "?")})')
        except Exception as _ex:
            _log.debug('staff_rating: уведомление не ушло: %s', _ex)

    @app.route('/staff-rating')
    @login_required
    @role_required('mod')
    def staff_rating_page():
        return render_template('staff_rating.html', role=session.get('role'),
                               username=session.get('username'),
                               guild_id=active_guild_id())

    @app.route('/api/guild/<gid>/staff-leaderboard')
    @login_required
    @role_required('mod')
    def api_staff_leaderboard(gid):
        """Композитная эффективность команды (активность+скорость+звёзды+справедливость)."""
        gid = active_guild_id()
        try:
            from services.mod_leaderboard import compute_leaderboard
            payload = compute_leaderboard(gid)
            payload['success'] = True
            return jsonify(payload)
        except Exception as _ex:
            _log.debug('staff-leaderboard: %s', _ex)
            return jsonify({'success': False,
                            'error': 'Не удалось собрать рейтинг'}), 500

    @app.route('/api/guild/<gid>/staff-rating/overview')
    @login_required
    @role_required('mod')
    def api_sr_overview(gid):
        state = _state(gid)
        names = names_from_audit(gid)
        return jsonify({
            'success': True,
            'table': rating_table(state, names=names),
            'stats': overview_stats(state, names=names),
            'can_edit': session.get('role') in ('admin', 'owner'),
        })

    @app.route('/api/guild/<gid>/staff-rating/card')
    @login_required
    @role_required('mod')
    def api_sr_card(gid):
        ok, err, staff_id = validate_user_id(request.args.get('staff'))
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        card = staff_card(_state(gid), staff_id,
                          names=names_from_audit(gid))
        if card is None:
            return jsonify({'success': False,
                            'error': 'Оценок у модератора нет.'}), 404
        card['can_edit'] = session.get('role') in ('admin', 'owner')
        return jsonify({'success': True, 'card': card})

    @app.route('/api/guild/<gid>/staff-rating/remove', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_sr_remove(gid):
        data = request.get_json(silent=True) or {}
        ok, err, staff_id = validate_user_id(data.get('staff_id'))
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        voter_id = data.get('voter_id')
        if voter_id in (None, '', '*'):
            voter_id = None
        else:
            ok, err, voter_id = validate_user_id(voter_id)
            if not ok:
                return jsonify({'success': False, 'error': err}), 400
        state = _state(gid)
        ok, err, removed = remove_vote(state, staff_id, voter_id)
        if not ok:
            return jsonify({'success': False, 'error': err}), 404
        _db().set(gid, 'state', state)
        _notify(f'Оценки персонала: у {staff_id} снято голосов — {removed}')
        return jsonify({'success': True, 'removed': removed,
                        'card': staff_card(state, staff_id,
                                           names=names_from_audit(gid)),
                        'stats': overview_stats(state)})

    @app.route('/api/guild/<gid>/staff-rating/export.csv')
    @login_required
    @role_required('mod')
    def api_sr_export(gid):
        rows = rating_table(_state(gid), names=names_from_audit(gid))
        lines = ['rank;staff_id;name;avg;stars;votes']
        for r in rows:
            name = r['name'].replace(';', ',')
            lines.append('%d;%s;%s;%s;%s;%d' % (
                r['rank'], r['staff_id'], name, r['avg'], r['stars'],
                r['votes']))
        body = '\ufeff' + '\n'.join(lines) + '\n'
        return Response(body, mimetype='text/csv; charset=utf-8',
                        headers={'Content-Disposition':
                                 'attachment; filename="staff_rating_%s.csv"'
                                 % gid})
