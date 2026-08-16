# -*- coding: utf-8 -*-
"""Про-аналитика сообщений (идеи #11, #12): теплокарта и CSV-экспорт.

Читает ТЕ ЖЕ источники, что /api/guild/<gid>/analytics в community.py:
data/audit_log.json (category=message) с фолбэком в
data/message_logs_<gid>.json, если аудит пуст. Вся агрегация — чистыми
функциями модуля, эндпоинты их только сериализуют.

Чтение — mod+ (как сам раздел «Аналитика» в меню).
"""
import csv
import io
import json
import os
from collections import Counter
from datetime import date, datetime, timedelta

from web.routes._common import (
    _log,
    jsonify, Response,
)

_AUDIT_FILE = 'data/audit_log.json'
_WEEKDAYS = ('Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс')


def _parse_ts(ts):
    """ISO-метка -> naive local datetime (aware приводим к локали), мусор -> None."""
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace('Z', '+00:00'))
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt


def load_message_events(guild_id):
    """События сообщений сервера: [(автор, канал, datetime|None)].

    Порядок источников 1:1 с базовой аналитикой: audit_log, а если там
    сообщений нет — message_logs_<gid>.json.
    """
    gid = str(guild_id)
    events = []
    if os.path.exists(_AUDIT_FILE):
        try:
            with open(_AUDIT_FILE, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError) as _ex:
            _log.debug("analytics_plus: audit прочитать не удалось: %s", _ex)
            data = {}
        for ev in data.get(gid, []) or []:
            if not isinstance(ev, dict):
                continue
            if (ev.get('category') or '').lower() != 'message':
                continue
            if (ev.get('action') or '').lower() != 'message написано':
                continue
            events.append((
                ev.get('user_name') or ev.get('user_id', '?'),
                ev.get('channel') or ev.get('channel_name', '?'),
                _parse_ts(ev.get('timestamp')),
            ))
    if not events:
        log_file = f'data/message_logs_{gid}.json'
        if os.path.exists(log_file):
            try:
                with open(log_file, 'r', encoding='utf-8') as fh:
                    msgs = json.load(fh)
            except (OSError, json.JSONDecodeError) as _ex:
                _log.debug("analytics_plus: message_logs не прочитан: %s", _ex)
                msgs = []
            for m in msgs or []:
                if not isinstance(m, dict):
                    continue
                events.append((
                    m.get('author') or m.get('user_name', '?'),
                    m.get('channel', '?'),
                    _parse_ts(m.get('timestamp')),
                ))
    return events


def heatmap_matrix(events):
    """7×24 (день недели × час): [[cnt]*24]*7 плюс максимум для шкалы."""
    matrix = [[0] * 24 for _ in range(7)]
    total = 0
    for _author, _channel, dt in events:
        if dt is None:
            continue
        matrix[dt.weekday()][dt.hour] += 1
        total += 1
    peak = None
    max_val = 0
    for wd in range(7):
        for h in range(24):
            if matrix[wd][h] > max_val:
                max_val = matrix[wd][h]
                peak = (wd, h)
    return {
        'matrix': matrix,
        'max': max_val,
        'total': total,
        'weekdays': list(_WEEKDAYS),
        'peak': {'weekday': _WEEKDAYS[peak[0]], 'hour': peak[1], 'count': max_val} if peak else None,
    }


def daily_series(events, days=30):
    """[(iso-дата, сообщений)] за последние N дней, включая нулевые."""
    counts = Counter()
    for _author, _channel, dt in events:
        if dt is not None:
            counts[dt.date().isoformat()] += 1
    today = date.today()
    return [((today - timedelta(days=i)).isoformat(),
             counts[(today - timedelta(days=i)).isoformat()])
            for i in range(days - 1, -1, -1)]


def top_counter(events, idx, limit=20):
    cnt = Counter(str(ev[idx]) for ev in events)
    return cnt.most_common(limit)


def load_member_events(guild_id):
    """Приходы/уходы участников из audit_log: [(действие, datetime|None)]."""
    gid = str(guild_id)
    out = []
    if not os.path.exists(_AUDIT_FILE):
        return out
    try:
        with open(_AUDIT_FILE, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as _ex:
        _log.debug("analytics_plus: audit для member-flow не прочитан: %s", _ex)
        return out
    for ev in data.get(gid, []) or []:
        if not isinstance(ev, dict) or ev.get('category') != 'member':
            continue
        action = ev.get('action')
        if action not in ('Участник вошёл', 'Участник вышел'):
            continue
        out.append((action, _parse_ts(ev.get('timestamp'))))
    return out


def member_flow(guild_id, days=14):
    """Приходы/уходы по дням + итоги: {labels, joins, leaves, joined, left, net}."""
    joins = Counter()
    leaves = Counter()
    for action, dt in load_member_events(guild_id):
        if dt is None:
            continue
        key = dt.date().isoformat()
        if action == 'Участник вошёл':
            joins[key] += 1
        else:
            leaves[key] += 1
    today = date.today()
    labels = [(today - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]
    joined_total = sum(joins.values())
    left_total = sum(leaves.values())
    return {
        'labels': [lb[5:] for lb in labels],
        'joins': [joins.get(lb, 0) for lb in labels],
        'leaves': [leaves.get(lb, 0) for lb in labels],
        'joined_total': joined_total,
        'left_total': left_total,
        'net': joined_total - left_total,
    }


def week_summary(events, now=None):
    """Эта неделя vs прошлая: сообщения и активные авторы (7 суток × 2 окна)."""
    now = now or datetime.now()
    week_start = now - timedelta(days=7)
    prev_start = now - timedelta(days=14)
    cur_msgs = 0
    prev_msgs = 0
    cur_users = set()
    prev_users = set()
    for author, _channel, dt in events:
        if dt is None:
            continue
        if dt >= week_start:
            cur_msgs += 1
            cur_users.add(str(author))
        elif dt >= prev_start:
            prev_msgs += 1
            prev_users.add(str(author))

    def _delta(cur, prev):
        if prev == 0:
            return None  # честно: сравнивать не с чем
        return round(100 * (cur - prev) / prev)

    return {
        'week_msgs': cur_msgs,
        'prev_week_msgs': prev_msgs,
        'msgs_delta': _delta(cur_msgs, prev_msgs),
        'week_users': len(cur_users),
        'prev_week_users': len(prev_users),
        'users_delta': _delta(len(cur_users), len(prev_users)),
    }


def analytics_csv(guild_id, days=30):
    """CSV одним файлом: дни, топ участников, топ каналов (utf-8-sig для Excel)."""
    events = load_message_events(guild_id)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=';')
    w.writerow(['Дата', 'Сообщений'])
    for day, cnt in daily_series(events, days=days):
        w.writerow([day, cnt])
    w.writerow([])
    w.writerow(['Участник', 'Сообщений'])
    for name, cnt in top_counter(events, 0):
        w.writerow([name, cnt])
    w.writerow([])
    w.writerow(['Канал', 'Сообщений'])
    for name, cnt in top_counter(events, 1):
        w.writerow([name, cnt])
    return buf.getvalue()


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required

    @app.route('/api/guild/<guild_id>/analytics/heatmap')
    @login_required
    @role_required('mod')
    def api_guild_heatmap(guild_id):
        body = heatmap_matrix(load_message_events(guild_id))
        body['success'] = True
        return jsonify(body)

    @app.route('/api/guild/<guild_id>/analytics.csv')
    @login_required
    @role_required('mod')
    def api_guild_analytics_csv(guild_id):
        filename = f'analytics_{guild_id}_{date.today().isoformat()}.csv'
        return Response(
            '﻿' + analytics_csv(guild_id),
            mimetype='text/csv; charset=utf-8',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'},
        )

    @app.route('/api/guild/<guild_id>/analytics/member-flow')
    @login_required
    @role_required('mod')
    def api_guild_member_flow(guild_id):
        body = member_flow(guild_id)
        body['success'] = True
        return jsonify(body)

    @app.route('/api/guild/<guild_id>/analytics/week-summary')
    @login_required
    @role_required('mod')
    def api_guild_week_summary(guild_id):
        body = week_summary(load_message_events(guild_id))
        body['success'] = True
        return jsonify(body)
