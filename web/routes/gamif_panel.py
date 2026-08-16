# -*- coding: utf-8 -*-
"""Панель «Геймификация» (идеи #86-90): зал очков, серии дней, ежедневная
награда, досье игрока с уровнем и бейджами, корректировка очков.

Хранилище — файлы services/gamification.py (вне серверного namespace,
один инстанс на бота):
    data/user_points.json   {uid: {total_points, history [{points, reason,
                                    timestamp}], last_daily?}}
    data/user_streaks.json  {uid: {current_streak, longest_streak,
                                    last_activity iso}}
    data/user_badges.json   {uid: [{badge_id, name, ...}]}
Синглтоны сервиса кешируют файлы в памяти процесса бота, поэтому панель
читает файлы СВЕЖИМИ на каждый запрос, а вся арифметика (уровни, дейли,
серия-ноль при перерыве) повторяет методы сервиса 1:1, с константами
из него же (LEVELS, DAILY_REWARD/COOLDOWN_HOURS, BADGES).

Чтение и выгрузка — mod+, корректировка очков — admin+.
"""
import json
import os
from datetime import datetime, timedelta

from web.routes._common import (
    _log,
    render_template, session, request, jsonify, Response,
)

from web.routes.mod_control import validate_user_id, names_from_audit

import services.gamification as GM   # константы: LEVELS, BADGES, DAILY_*

PANEL_LIMIT = 25
ADJUST_LIMIT = 5000    # разовая панельная корректировка, ±

DAILY_REWARD = GM.PointsSystem.DAILY_REWARD
DAILY_COOLDOWN = timedelta(hours=GM.PointsSystem.DAILY_COOLDOWN_HOURS)

POINTS_FILE = 'data/user_points.json'
STREAKS_FILE = 'data/user_streaks.json'
BADGES_FILE = 'data/user_badges.json'


def _load_map(path):
    """Свежее чтение файла сервиса; битый/не-словарь — пусто (как у него)."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as fp:
            data = json.load(fp)
    except Exception as ex:
        _log.debug('gamif: %s: %s', path, ex)
        return {}
    return data if isinstance(data, dict) else {}


def _save_map(path, data):
    os.makedirs('data', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)


def level_view(points):
    """Уровень по очкам 1:1 с LevelSystem.get_level (перебор LEVELS
    сверху, прогресс до следующего, round 2)."""
    points = int(points or 0)
    current = 1
    for level, data in sorted(GM.LevelSystem.LEVELS.items(), reverse=True):
        if points >= data['min_points']:
            current = level
            break
    level_data = GM.LevelSystem.LEVELS[current]
    nxt = current + 1
    next_data = GM.LevelSystem.LEVELS.get(nxt)
    if next_data:
        points_to_next = next_data['min_points'] - points
        span = next_data['min_points'] - level_data['min_points']
        progress = (points - level_data['min_points']) / span * 100
    else:
        points_to_next = 0
        progress = 100
    return {
        'level': current,
        'name': level_data['name'],
        'points': points,
        'min_points': level_data['min_points'],
        'next_level': nxt if next_data else None,
        'next_level_name': next_data['name'] if next_data else None,
        'points_to_next': points_to_next,
        'progress': round(progress, 2),
    }


def daily_state(rec, now=None):
    """(can_claim, seconds_left) — логика can_claim_daily сервиса.
    None в seconds_left, если ждать нечего. Битая дата — можно (у него же)."""
    now = now or datetime.now()
    last = (rec or {}).get('last_daily') if isinstance(rec, dict) else None
    if not last:
        return True, None
    try:
        last_dt = datetime.fromisoformat(str(last))
    except ValueError:
        return True, None
    left = (last_dt + DAILY_COOLDOWN) - now
    if left.total_seconds() <= 0:
        return True, None
    return False, int(left.total_seconds())


def points_rows(points_map, names=None, limit=PANEL_LIMIT, now=None):
    """Зал очков: порядок как get_leaderboard сервиса (total desc)."""
    names = names or {}
    rows = []
    for uid, rec in (points_map or {}).items():
        if not isinstance(rec, dict):
            continue
        can, left = daily_state(rec, now=now)
        rows.append({
            'user_id': str(uid),
            'name': str(names.get(str(uid)) or f'ID {str(uid)[:6]}'),
            'points': int(rec.get('total_points', 0) or 0),
            'history': len(rec.get('history') or []),
            'daily_can': can,
            'daily_left_s': left,
        })
    rows.sort(key=lambda r: (-r['points'], r['user_id']))
    for rank, row in enumerate(rows[:max(1, int(limit))], 1):
        row['rank'] = rank
    return rows[:max(1, int(limit))]


def points_summary(points_map, now=None):
    """Чипы: людей, сумма очков, могут забрать дейли, на перезарядке."""
    people = points = 0
    claimable = on_cooldown = 0
    for rec in (points_map or {}).values():
        if not isinstance(rec, dict):
            continue
        people += 1
        try:
            points += int(rec.get('total_points', 0) or 0)
        except (TypeError, ValueError) as ex:
            _log.debug('gamif total_points: %s', ex)
            continue
        can, _left = daily_state(rec, now=now)
        if can:
            claimable += 1
        else:
            on_cooldown += 1
    return {'people': people, 'points_total': points,
            'daily_claimable': claimable, 'daily_cooldown': on_cooldown,
            'daily_reward': DAILY_REWARD}


def streak_rows(streaks_map, names=None, now=None, limit=PANEL_LIMIT):
    """Серии: текущая с обнулением при перерыве >1 дня (get_streak сервиса),
    активность сегодня, рекорд. Порядок: текущая, рекорд, uid."""
    names = names or {}
    today = (now or datetime.now()).date()
    rows = []
    for uid, rec in (streaks_map or {}).items():
        if not isinstance(rec, dict):
            continue
        current = int(rec.get('current_streak', 0) or 0)
        longest = int(rec.get('longest_streak', 0) or 0)
        last_iso = rec.get('last_activity')
        active_today = False
        last_date = None
        if last_iso:
            try:
                last_date = datetime.fromisoformat(str(last_iso)).date()
                if (today - last_date).days > 1:
                    current = 0        # серия прервана — как get_streak
                active_today = last_date == today
            except ValueError as ex:
                _log.debug('gamif streak %s: %s', uid, ex)
        rows.append({
            'user_id': str(uid),
            'name': str(names.get(str(uid)) or f'ID {str(uid)[:6]}'),
            'current': current,
            'longest': longest,
            'last_date': str(last_date) if last_date else '',
            'active_today': active_today,
        })
    rows.sort(key=lambda r: (-r['current'], -r['longest'], r['user_id']))
    return rows[:max(1, int(limit))]


def streak_summary(streaks_map, now=None):
    """Чипы: следим, активны сегодня, горят серией, рекорд длин."""
    rows = streak_rows(streaks_map, now=now, limit=100000)
    return {
        'tracked': len(rows),
        'active_today': sum(1 for r in rows if r['active_today']),
        'running': sum(1 for r in rows if r['current'] > 0),
        'best': max((r['longest'] for r in rows), default=0),
    }


def player_dossier(points_map, streaks_map, badges_map, uid,
                   names=None, now=None):
    """Досье игрока: очки + уровень (level_view), дейли, серия (с обнулением
    перерыва), бейджи из файла. Возвращает None, если игрока нет нигде."""
    uid = str(uid)
    prec = points_map.get(uid) if isinstance(points_map.get(uid), dict) else None
    srec = (streaks_map.get(uid)
            if isinstance(streaks_map.get(uid), dict) else None)
    brec = badges_map.get(uid) if isinstance(badges_map.get(uid), list) else None
    if prec is None and srec is None and not brec:
        return None
    points = int((prec or {}).get('total_points', 0) or 0)
    can, left = daily_state(prec or {}, now=now)
    streaks = streak_rows({uid: srec or {}}, now=now, limit=1)
    streak = streaks[0] if streaks else {'current': 0, 'longest': 0,
                                         'last_date': '', 'active_today': False}
    names = names or {}
    badges = []
    for badge in (brec or []):
        if isinstance(badge, dict):
            badges.append(str(badge.get('name') or badge.get('badge_id') or '?'))
        else:
            badges.append(str(badge))
    return {
        'user_id': uid,
        'name': str(names.get(uid) or f'ID {uid[:6]}'),
        'points': points,
        'level': level_view(points),
        'daily_can': can,
        'daily_left_s': left,
        'streak': streak,
        'badges': badges,
        'history': list((prec or {}).get('history') or [])[-50:],
    }


def adjust_points(points_map, user_id, delta, by_name, now=None):
    """Корректировка формой add_points сервиса: total_points += delta,
    запись в history {points, reason, timestamp} (timestamp — naive iso!).
    -> (total | None, err, uid | None)
    """
    ok, err, uid = validate_user_id(user_id)
    if not ok:
        return None, err, None
    try:
        delta = int(delta)
    except (TypeError, ValueError):
        return None, 'Корректировка — целое число', None
    if delta == 0:
        return None, 'Корректировка не бывает нулевой', None
    if abs(delta) > ADJUST_LIMIT:
        return None, 'Разом — не больше ±%d' % ADJUST_LIMIT, None
    rec = points_map.setdefault(uid, {'total_points': 0, 'history': []})
    if not isinstance(rec.get('history'), list):
        rec['history'] = []
    rec['total_points'] = int(rec.get('total_points', 0) or 0) + delta
    rec['history'].append({
        'points': delta,
        'reason': 'panel',
        'timestamp': (now or datetime.now()).isoformat(),
    })
    return rec['total_points'], '', uid


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
                'gamification', title,
                f'Через панель ({session.get("username", "?")})')
        except Exception as _ex:
            _log.debug('gamif: уведомление не ушло: %s', _ex)

    @app.route('/gamification')
    @login_required
    @role_required('mod')
    def gamification_page():
        return render_template('gamification.html', role=session.get('role'),
                               username=session.get('username'),
                               guild_id=active_guild_id())

    @app.route('/api/guild/<gid>/gamification/overview')
    @login_required
    @role_required('mod')
    def api_gamif_overview(gid):
        points_map = _load_map(POINTS_FILE)
        streaks_map = _load_map(STREAKS_FILE)
        names = names_from_audit(gid)
        return jsonify({
            'success': True,
            'points': points_rows(points_map, names=names),
            'points_summary': points_summary(points_map),
            'streaks': streak_rows(streaks_map, names=names),
            'streaks_summary': streak_summary(streaks_map),
            'can_edit': session.get('role') in ('admin', 'owner'),
        })

    @app.route('/api/guild/<gid>/gamification/player/<uid>')
    @login_required
    @role_required('mod')
    def api_gamif_player(gid, uid):
        ok, err, clean = validate_user_id(uid)
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        dossier = player_dossier(_load_map(POINTS_FILE),
                                 _load_map(STREAKS_FILE),
                                 _load_map(BADGES_FILE), clean,
                                 names=names_from_audit(gid))
        if dossier is None:
            return jsonify({'success': False,
                            'error': 'Игрок не найден.'}), 404
        return jsonify({'success': True, 'player': dossier})

    @app.route('/api/guild/<gid>/gamification/adjust', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_gamif_adjust(gid):
        data = request.get_json(silent=True) or {}
        points_map = _load_map(POINTS_FILE)
        total, err, uid = adjust_points(points_map, data.get('user_id'),
                                        data.get('delta'),
                                        session.get('username', '?'))
        if total is None:
            return jsonify({'success': False, 'error': err}), 400
        _save_map(POINTS_FILE, points_map)
        try:
            delta_int = int(data.get('delta'))
        except (TypeError, ValueError):
            delta_int = 0  # в adjust_points провалидировано — для подписи
        _notify(f'Очки геймификации: {uid} скорректированы ({delta_int:+d})')
        return jsonify({'success': True, 'user_id': uid, 'total': total,
                        'level': level_view(total)})

    @app.route('/api/guild/<gid>/gamification/export.csv')
    @login_required
    @role_required('mod')
    def api_gamif_csv(gid):
        kind = (request.args.get('kind') or 'points').strip()
        names = names_from_audit(gid)
        if kind == 'streaks':
            rows = streak_rows(_load_map(STREAKS_FILE), names=names,
                               limit=100000)
            lines = ['rank;user_id;name;current;longest;last_date']
            for rank, r in enumerate(rows, 1):
                lines.append('{};{};{};{};{};{}'.format(
                    rank, r['user_id'], str(r['name']).replace(';', ','),
                    r['current'], r['longest'], r['last_date']))
        else:
            rows = points_rows(_load_map(POINTS_FILE), names=names,
                               limit=100000)
            lines = ['rank;user_id;name;points']
            for r in rows:
                lines.append('{};{};{};{}'.format(
                    r['rank'], r['user_id'],
                    str(r['name']).replace(';', ','), r['points']))
        body = '\ufeff' + '\n'.join(lines) + '\n'
        return Response(
            body, mimetype='text/csv; charset=utf-8',
            headers={'Content-Disposition':
                     'attachment; filename="gamif_%s.csv"' % kind})
