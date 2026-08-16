# -*- coding: utf-8 -*-
"""Лента инцидентов (идеи #136-140): /replay в браузере.

Источник единый с ботом: data/audit_log.json (его читает cogs/replay.py
через _load_events). Правила выборки 1:1 с командой:
- окно клампится max(5, min(minutes, 1440)), дефолт 30;
- метки без TZ считаем UTC; битые пропускаем;
- фильтр по участнику — его же грубый приём: uid ищется подстрокой
  в JSON-блобе события (ловит user_id/mod_id/цели разом);
- сортировка по времени, в ленту — хвост из 14.

Детали строк — его _detail_text. Чтение и CSV — mod+.
"""
import json
from collections import Counter
from datetime import datetime, timedelta, timezone

from web.routes._common import (
    render_template, session, request, jsonify, Response,
)
from web.routes.mod_control import validate_user_id

from cogs import replay as RP
from cogs.logs import CATEGORIES

UTC = timezone.utc

FEED_TAIL = 14          # сколько событий рисует карточка бота
MIN_MINUTES = 5
MAX_MINUTES = 1440
DEFAULT_MINUTES = 30


def load_rows(gid, minutes=DEFAULT_MINUTES, uid=None, now=None):
    """(rows, minutes) — выборка окна, как в команде: кламп и фильтры те же."""
    try:
        minutes = int(minutes or DEFAULT_MINUTES)
    except (TypeError, ValueError):
        minutes = DEFAULT_MINUTES
    minutes = max(MIN_MINUTES, min(minutes, MAX_MINUTES))
    now = now or datetime.now(UTC)
    threshold = now - timedelta(minutes=minutes)
    rows = []
    for ev in RP._load_events(gid):
        ts = RP._parse_ts(ev)
        if ts is None:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        if ts < threshold:
            continue
        if uid:
            blob = json.dumps(ev, ensure_ascii=False)
            if f'"{uid}"' not in blob and uid not in blob:
                continue
        rows.append((ts, ev))
    rows.sort(key=lambda x: x[0])
    return rows, minutes


def cat_label(cat):
    """Человекочитаемое имя категории — словарь из cogs/logs.py как есть."""
    meta = CATEGORIES.get(str(cat))
    return meta['label'] if meta else str(cat).capitalize()


def feed_view(rows, limit=FEED_TAIL):
    """Хвост ленты в том виде, в каком карточка бота отдаёт события."""
    out = []
    for ts, ev in rows[-limit:]:
        cat = str(ev.get('category', 'guild'))
        out.append({
            'time': ts.strftime('%H:%M'),
            'ts': ts.isoformat(),
            'cat': cat,
            'cat_label': cat_label(cat),
            'label': str(ev.get('action', 'Событие')),
            'detail': RP._detail_text(ev),
        })
    return out


def pulse(rows, minutes):
    """Пульс окна: счётчики по категориям и действиям за весь период."""
    cats = Counter(str(ev.get('category', 'guild')) for _ts, ev in rows)
    acts = Counter(str(ev.get('action', 'Событие')) for _ts, ev in rows)
    return {
        'total': len(rows),
        'per_hour': round(len(rows) * 60 / max(1, minutes), 1),
        'by_category': [{'cat': c, 'label': cat_label(c), 'count': n}
                        for c, n in cats.most_common(8)],
        'top_actions': [{'action': a, 'count': n} for a, n in acts.most_common(5)],
    }


def csv_rows(rows):
    return [(ts.isoformat(), str(ev.get('category', 'guild')),
             str(ev.get('action', 'Событие')), RP._detail_text(ev))
            for ts, ev in rows]


def _csv_cell(text):
    return str(text).replace(';', ',').replace('\r', ' ').replace('\n', ' ')


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required
    active_guild_id = ctx.active_guild_id

    def _params():
        uid_raw = (request.args.get('user') or '').strip()
        uid = None
        if uid_raw:
            ok, _err, uid = validate_user_id(uid_raw)
            if not ok:
                uid = None
        return uid

    @app.route('/replay')
    @login_required
    @role_required('mod')
    def replay_page():
        return render_template('replay.html', role=session.get('role'),
                               username=session.get('username'),
                               guild_id=active_guild_id())

    @app.route('/api/guild/<gid>/replay/feed')
    @login_required
    @role_required('mod')
    def api_replay_feed(gid):
        rows, minutes = load_rows(gid, request.args.get('minutes'), uid=_params())
        return jsonify({
            'success': True,
            'minutes': minutes,
            'quiet': not rows,
            'quiet_text': (f'За последние {minutes} мин событий нет. Бот ведёт '
                           'летопись, пока он в сети — старые окна могут быть пустыми.'),
            'feed': feed_view(rows),
            'pulse': pulse(rows, minutes),
        })

    @app.route('/api/guild/<gid>/replay/export.csv')
    @login_required
    @role_required('mod')
    def api_replay_export(gid):
        rows, minutes = load_rows(gid, request.args.get('minutes'), uid=_params())
        body = '\ufeff' + 'timestamp;category;action;detail\n'
        body += '\n'.join(';'.join(_csv_cell(c) for c in row) for row in csv_rows(rows))
        resp = Response(body, mimetype='text/csv; charset=utf-8')
        resp.headers['Content-Disposition'] = (
            f'attachment; filename=replay_{minutes}m_{gid}.csv')
        return resp
