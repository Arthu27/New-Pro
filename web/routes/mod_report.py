# -*- coding: utf-8 -*-
"""Отчёт модерации (идеи #31-33): нагрузка команды, рецидивисты, выгрузка.

Источник — тот же data/audit_log.json (категория 'mod'), что пишет
cogs/logs.py: mod_name / user_name / action / timestamp. Никаких своих
журналов: считаем ровно то, что положил бот.

Чтение и выгрузка — mod+ (как раздел «Модерация» в меню).
"""
import csv
import io
from collections import Counter
from datetime import date, datetime, timedelta

from web.routes._common import (
    _log,
    render_template, session, request, jsonify, Response,
)

from web.routes.analytics_plus import _parse_ts, _read_audit

RECIDIVIST_MIN = 3


def mod_report(guild_id, days=7, now=None):
    """Сводка по мод-действиям за окно: по модераторам, типам, дням, целям."""
    try:
        days = int(days)
    except (TypeError, ValueError):
        days = 7
    days = min(90, max(1, days))
    now = now or datetime.now()
    cutoff = now - timedelta(days=days)

    per_mod = Counter()
    by_action = Counter()
    per_day = Counter()
    targets = Counter()
    for ev in _read_audit(guild_id):
        if ev.get('category') != 'mod':
            continue
        dt = _parse_ts(ev.get('timestamp'))
        if dt is None or dt < cutoff:
            continue
        per_day[dt.date().isoformat()] += 1
        by_action[str(ev.get('action') or '?')] += 1
        mod_name = str(ev.get('mod_name') or '').strip()
        if mod_name:
            per_mod[mod_name] += 1
        target = str(ev.get('user_name') or '').strip()
        if target:
            targets[target] += 1

    labels = [((now - timedelta(days=i)).date().isoformat()) for i in range(days - 1, -1, -1)]
    recidivists = [
        {'name': name, 'count': cnt}
        for name, cnt in targets.most_common()
        if cnt >= RECIDIVIST_MIN
    ]
    return {
        'days': days,
        'total': sum(by_action.values()),
        'mods_total': len(per_mod),
        'per_mod': per_mod.most_common(10),
        'by_action': by_action.most_common(),
        'per_day': {'labels': labels, 'counts': [per_day.get(lb, 0) for lb in labels]},
        'recidivists': recidivists[:10],
        'recidivists_total': len(recidivists),
    }


def mod_report_csv(guild_id, days=7, now=None):
    rep = mod_report(guild_id, days=days, now=now)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=';')
    w.writerow(['Период, дней', rep['days']])
    w.writerow(['Всего действий', rep['total']])
    w.writerow([])
    w.writerow(['Модератор', 'Действий'])
    for name, cnt in rep['per_mod']:
        w.writerow([name, cnt])
    w.writerow([])
    w.writerow(['Действие', 'Кол-во'])
    for action, cnt in rep['by_action']:
        w.writerow([action, cnt])
    w.writerow([])
    w.writerow(['Рецидивист (3+)', 'Нарушений'])
    for r in rep['recidivists']:
        w.writerow([r['name'], r['count']])
    return buf.getvalue()


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required

    @app.route('/mod-report')
    @login_required
    @role_required('mod')
    def mod_report_page():
        return render_template('mod_report.html', role=session.get('role'),
                               username=session.get('username'))

    @app.route('/api/mod-report')
    @login_required
    @role_required('mod')
    def api_mod_report():
        days = request.args.get('days', 7)
        body = mod_report(int(ctx.active_guild_id()), days=days)
        body['success'] = True
        return jsonify(body)

    @app.route('/api/mod-report.csv')
    @login_required
    @role_required('mod')
    def api_mod_report_csv():
        days = request.args.get('days', 7)
        filename = 'mod_report_%s_%s.csv' % (
            ctx.active_guild_id(), date.today().isoformat())
        return Response(
            '\ufeff' + mod_report_csv(int(ctx.active_guild_id()), days=days),
            mimetype='text/csv; charset=utf-8',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'},
        )
