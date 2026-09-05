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


def _read_audit(guild_id):
    """Сырые события сервера из audit_log.json; битый/отсутствующий файл -> []."""
    gid = str(guild_id)
    if not os.path.exists(_AUDIT_FILE):
        return []
    try:
        with open(_AUDIT_FILE, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as _ex:
        _log.debug("analytics_plus: audit прочитать не удалось: %s", _ex)
        return []
    return [ev for ev in (data.get(gid, []) or []) if isinstance(ev, dict)]


def load_message_events(guild_id):
    """События сообщений сервера: [(автор, канал, datetime|None, uid|None)].

    Объединяем ОБА источника, а не выбираем один:
      • data/message_logs_<gid>.json — основной полный поток (его ведёт ког
        activity_stats на КАЖДОЕ сообщение, не ботов/вебхуков/ЛС);
      • audit_log.json (category=message, 'message написано') — редкое
        историческое дополнение.
    Раньше был фолбэк «audit, а если он не пуст — message_logs не читаем»:
    одного старого audit-сообщения хватало, чтобы весь message_logs
    (тысячи реальных сообщений) проигнорировался, и heatmap/недельная
    сводка/рекорды/детализация каналов выходили пустыми.
    """
    gid = str(guild_id)
    events = []

    # 1) Основной источник — message_logs (полные реальные данные).
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
            author = m.get('author') or m.get('user_name') or m.get('user_id')
            if not author:
                continue
            # uid — личность автора: топы и «уникальные» клеятся по нему,
            # смена ника не дробит человека (владелец 2026-09-05).
            uid = str(m.get('uid') or '') or None
            events.append((
                str(author),
                str(m.get('channel') or m.get('channel_name') or '?'),
                _parse_ts(m.get('timestamp')),
                uid,
            ))

    # 2) Дополнение из audit_log (message-события). Дедуплицируем по ключу
    #    (автор, канал, дата-время до секунды), чтобы не задвоить совпадения.
    seen = {(str(a), str(c), d.isoformat() if d else None) for a, c, d, _u in events}
    for ev in _read_audit(gid):
        if (ev.get('category') or '').lower() != 'message':
            continue
        if (ev.get('action') or '').lower() != 'message написано':
            continue
        author = ev.get('user_name') or ev.get('user_id')
        if not author:
            continue
        dt = _parse_ts(ev.get('timestamp'))
        key = (str(author), str(ev.get('channel') or ev.get('channel_name') or '?'),
               dt.isoformat() if dt else None)
        if key in seen:
            continue
        seen.add(key)
        events.append((str(author), key[1], dt,
                       str(ev.get('user_id') or '') or None))

    return events


def heatmap_matrix(events):
    """7×24 (день недели × час): [[cnt]*24]*7 плюс максимум для шкалы."""
    matrix = [[0] * 24 for _ in range(7)]
    total = 0
    for _author, _channel, dt, _uid in events:
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
    for _author, _channel, dt, _uid in events:
        if dt is not None:
            counts[dt.date().isoformat()] += 1
    today = date.today()
    return [((today - timedelta(days=i)).isoformat(),
             counts[(today - timedelta(days=i)).isoformat()])
            for i in range(days - 1, -1, -1)]


def top_counter(events, idx, limit=20):
    cnt = Counter(str(ev[idx]) for ev in events)
    return cnt.most_common(limit)


def _identity_key(author, uid):
    """Личность автора: uid, а без него — само имя (старые записи)."""
    return ('u:' + str(uid)) if uid else ('n:' + str(author))


def top_members_counter(events, limit=20):
    """Топ авторов ПО ЛИЧНОСТИ (uid); подпись — из самой свежей записи.

    Смена ника не дробит человека в CSV и «детализации канала»
    (владелец 2026-09-05: «один и тот же человек, имя поменял»).
    Список хронологический, поэтому последний ник просто побеждает.
    """
    counts, labels = {}, {}
    for author, _ch, _dt, uid in events:
        key = _identity_key(author, uid)
        counts[key] = counts.get(key, 0) + 1
        labels[key] = str(author)
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]
    return [(labels[k], c) for k, c in ranked]


def unique_members(events):
    """Сколько РАЗНЫХ людей в событиях (по uid, не по никам)."""
    return len({_identity_key(a, u) for a, _c, _dt, u in events})


def load_member_events(guild_id):
    """Приходы/уходы участников из audit_log: [(действие, datetime|None)]."""
    out = []
    for ev in _read_audit(guild_id):
        action = ev.get('action')
        if ev.get('category') != 'member':
            continue
        if action not in ('Участник вошёл', 'Участник вышел'):
            continue
        out.append((action, _parse_ts(ev.get('timestamp'))))
    return out


def mod_load(guild_id, days=30):
    """Мод-нагрузка: действия по дням, по модераторам и по типам."""
    per_day = Counter()
    by_mod = Counter()
    by_action = Counter()
    for ev in _read_audit(guild_id):
        if ev.get('category') != 'mod':
            continue
        dt = _parse_ts(ev.get('timestamp'))
        if dt is not None:
            per_day[dt.date().isoformat()] += 1
        mod_name = str(ev.get('mod_name') or '?')
        if mod_name != '?':
            by_mod[mod_name] += 1
        by_action[str(ev.get('action') or '?')] += 1
    today = date.today()
    labels = [(today - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]
    return {
        'labels': labels,
        'counts': [per_day.get(lb, 0) for lb in labels],
        'mods': by_mod.most_common(6),
        'actions': by_action.most_common(8),
        'total': sum(by_action.values()),
    }


def voice_pulse(guild_id):
    """Пульс войса: входы по дням недели, топы каналов. Честно: события, не минуты."""
    per_wd = [0] * 7
    channels = Counter()
    users = set()
    total = 0
    for ev in _read_audit(guild_id):
        if ev.get('category') != 'voice' or ev.get('action') != 'Зашёл в голосовой':
            continue
        total += 1
        dt = _parse_ts(ev.get('timestamp'))
        if dt is not None:
            per_wd[dt.weekday()] += 1
        ch = str(ev.get('channel') or '?')
        if ch != '?':
            channels[ch] += 1
        user = str(ev.get('user_name') or '')
        if user:
            users.add(user)
    return {
        'weekdays': per_wd,
        'weekday_labels': list(_WEEKDAYS),
        'top_channels': channels.most_common(6),
        'total_joins': total,
        'unique_users': len(users),
    }


def invite_leaders(guild_id, limit=6):
    """Лидеры по созданным инвайтам (аудит-события 'Приглашение создано')."""
    leaders = Counter()
    total = 0
    for ev in _read_audit(guild_id):
        if ev.get('category') != 'invite' or ev.get('action') != 'Приглашение создано':
            continue
        total += 1
        name = str(ev.get('user_name') or '?')
        if name != '?':
            leaders[name] += 1
    return {'leaders': leaders.most_common(limit), 'total': total}


def analytics_full_csv(guild_id, days=30):
    """Полный отчёт одним файлом: сообщения, участники, каналы, поток, модерация."""
    events = load_message_events(guild_id)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=';')
    w.writerow(['Дата', 'Сообщений'])
    for day, cnt in daily_series(events, days=days):
        w.writerow([day, cnt])
    w.writerow([])
    w.writerow(['Участник', 'Сообщений'])
    for name, cnt in top_members_counter(events):
        w.writerow([name, cnt])
    w.writerow([])
    w.writerow(['Канал', 'Сообщений'])
    for name, cnt in top_counter(events, 1):
        w.writerow([name, cnt])
    w.writerow([])
    w.writerow(['Дата', 'Пришло', 'Ушло'])
    flow = member_flow(guild_id, days=days)
    today = date.today()
    iso_labels = [(today - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]
    for i, lb in enumerate(iso_labels):
        w.writerow([lb, flow['joins'][i], flow['leaves'][i]])
    w.writerow([])
    w.writerow(['Мод-действие', 'Кол-во'])
    for action, cnt in mod_load(guild_id, days=days)['actions']:
        w.writerow([action, cnt])
    w.writerow([])
    w.writerow(['Инвайтер', 'Создано ссылок'])
    for name, cnt in invite_leaders(guild_id)['leaders']:
        w.writerow([name, cnt])
    return buf.getvalue()


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


def member_count_series(current_count, flow, days=None):
    """Ряд «число участников на конец каждого дня» по реальным приходам/уходам.

    current_count — члены сервера СЕЙЧАС (после всех событий окна), это
    последняя точка (сегодня). Идём назад по дням: если в день i пришло
    joins[i] и ушло leaves[i], то на конец предыдущего дня было
    count[i-1] = count[i] - joins[i] + leaves[i].

    Раньше community.py считал одной формулой со срезом joins[i:]/leaves[i:],
    что давало сдвиг на день (событие дня i относилось к дню i-1) и рисовало
    линию роста неверно.
    """
    joins = flow.get('joins') or []
    leaves = flow.get('leaves') or []
    n = days or len(joins) or len(leaves) or 7
    if len(joins) < n:
        joins = joins + [0] * (n - len(joins))
    if len(leaves) < n:
        leaves = leaves + [0] * (n - len(leaves))
    counts = [0] * n
    counts[n - 1] = max(0, int(current_count or 0))
    for i in range(n - 1, 0, -1):
        counts[i - 1] = max(0, counts[i] - int(joins[i] or 0) + int(leaves[i] or 0))
    return counts


def channel_drill(events, name, days=30):
    """Детализация по каналу: ряд по дням, топ авторов, всего сообщений."""
    name = (name or '').strip()
    own = [ev for ev in events if str(ev[1]) == name]
    days_row = []
    counts = Counter(dt.date().isoformat() for _a, _c, dt, _u in own if dt is not None)
    today = date.today()
    for i in range(days - 1, -1, -1):
        day = (today - timedelta(days=i)).isoformat()
        days_row.append((day, counts.get(day, 0)))
    return {
        'name': name,
        'total': len(own),
        'days': days_row,
        'top_authors': top_members_counter(own, limit=5),
        'unique_authors': unique_members(own),
    }


def record_days(events, limit=3):
    """Рекордные дни сервера по сообщениям: [(дата, кол-во)] по убыванию."""
    counts = Counter(dt.date().isoformat() for _a, _c, dt, _u in events if dt is not None)
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]


def week_summary(events, now=None):
    """Эта неделя vs прошлая: сообщения и активные авторы (7 суток × 2 окна)."""
    now = now or datetime.now()
    week_start = now - timedelta(days=7)
    prev_start = now - timedelta(days=14)
    cur_msgs = 0
    prev_msgs = 0
    cur_users = set()
    prev_users = set()
    for author, _channel, dt, uid in events:
        if dt is None:
            continue
        _key = _identity_key(author, uid)
        if dt >= week_start:
            cur_msgs += 1
            cur_users.add(_key)
        elif dt >= prev_start:
            prev_msgs += 1
            prev_users.add(_key)

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
    for name, cnt in top_members_counter(events):
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
            '\ufeff' + analytics_csv(guild_id),
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

    @app.route('/api/guild/<guild_id>/analytics/channel-drill')
    @login_required
    @role_required('mod')
    def api_guild_channel_drill(guild_id):
        from flask import request as _req
        name = _req.args.get('name', '')
        body = channel_drill(load_message_events(guild_id), name)
        # Демо-фабрикация детализации удалена (заказ владельца 2026-08):
        # никаких выдуманных авторов и чисел — только реальные события.
        body['success'] = True
        return jsonify(body)

    @app.route('/api/guild/<guild_id>/analytics/records')
    @login_required
    @role_required('mod')
    def api_guild_records(guild_id):
        events = load_message_events(guild_id)
        recs = record_days(events)
        today_iso = date.today().isoformat()
        counts_ser = Counter(
            dt.date().isoformat() for _a, _c, dt, _u in events if dt is not None
        )
        rank = None
        if counts_ser.get(today_iso):
            ordered = sorted(counts_ser.items(), key=lambda kv: (-kv[1], kv[0]))
            rank = next((i for i, (day, _c) in enumerate(ordered, 1)
                         if day == today_iso), None)
        return jsonify({
            'success': True,
            'records': [{'date': d, 'count': c} for d, c in recs],
            'today_count': counts_ser.get(today_iso, 0),
            'today_rank': rank,
        })

    @app.route('/api/guild/<guild_id>/analytics/mod-load')
    @login_required
    @role_required('mod')
    def api_guild_mod_load(guild_id):
        body = mod_load(guild_id)
        body['success'] = True
        return jsonify(body)

    @app.route('/api/guild/<guild_id>/analytics/voice-pulse')
    @login_required
    @role_required('mod')
    def api_guild_voice_pulse(guild_id):
        body = voice_pulse(guild_id)
        body['success'] = True
        return jsonify(body)

    @app.route('/api/guild/<guild_id>/analytics/invite-leaders')
    @login_required
    @role_required('mod')
    def api_guild_invite_leaders(guild_id):
        body = invite_leaders(guild_id)
        body['success'] = True
        return jsonify(body)

    @app.route('/api/guild/<guild_id>/analytics_full.csv')
    @login_required
    @role_required('mod')
    def api_guild_analytics_full_csv(guild_id):
        filename = f'analytics_full_{guild_id}_{date.today().isoformat()}.csv'
        return Response(
            '\ufeff' + analytics_full_csv(guild_id),
            mimetype='text/csv; charset=utf-8',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'},
        )
