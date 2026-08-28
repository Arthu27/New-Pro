# -*- coding: utf-8 -*-
"""Очередь репортов участников (панель-зеркало cogs/reports.py).

Тикеты (/report → приватная ветка) живут в SQLite data/reports.db —
читаем через общие функции services/reports_core. Решение выносится
модераторами в самой ветке Discord — панель честно показывает очередь
и сводку, а не дублирует механику.

Чтение — mod+.
"""

from web.routes._common import (
    _log,
    render_template, session, jsonify,
)

KIND_META = {'report': ('Репорт', 'fa-flag', 'danger'),
             'appeal': ('Апелляция', 'fa-scale-balanced', 'info')}


def queue_payload(gid, names=None):
    """Сводка + список тикетов (тестируется без Flask-запроса)."""
    from services import reports_core as RC
    if names is None:
        try:
            from web.routes.mod_control import names_from_audit
            names = names_from_audit(gid)
        except Exception as _ex:
            _log.debug('reports_queue: имена: %s', _ex)
            names = {}

    def nm(uid):
        return names.get(str(uid), '') or str(uid or '—')

    items = []
    for t in RC.ticket_list(gid):
        label, icon, tone = KIND_META.get(t['kind'], ('Тикет', 'fa-ticket', 'neutral'))
        age_min = 0
        try:
            import time as _t
            age_min = max(0, int((_t.time() - t['created']) // 60))
        except (TypeError, ValueError):
            age_min = 0
        verdict = str(t.get('verdict') or '').strip()
        items.append({
            'thread_id': t['thread_id'],
            'kind': t['kind'],
            'kind_label': label, 'icon': icon, 'tone': tone,
            'reporter': nm(t['reporter_id']),
            'accused': nm(t['accused_id']),
            'same': str(t['reporter_id']) == str(t['accused_id']),
            'age_min': age_min,
            'created_readable': _fmt(t['created']),
            'closed': bool(t.get('closed')),
            'closed_readable': _fmt(t.get('closed') or 0),
            'verdict': verdict[:300],
        })
    return {'stats': RC.ticket_stats(gid), 'items': items}


def _fmt(ts):
    try:
        if not ts:
            return ''
        from datetime import datetime
        return datetime.fromtimestamp(float(ts)).strftime('%d.%m %H:%M')
    except (TypeError, ValueError, OSError):
        return ''


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required
    active_guild_id = ctx.active_guild_id

    @app.route('/reports-queue')
    @login_required
    @role_required('mod')
    def reports_queue_page():
        return render_template('reports_queue.html', role=session.get('role'),
                               username=session.get('username'),
                               guild_id=active_guild_id())

    @app.route('/api/guild/<gid>/reports-queue')
    @login_required
    @role_required('mod')
    def api_reports_queue(gid):
        gid = active_guild_id()
        payload = queue_payload(gid)
        payload['success'] = True
        return jsonify(payload)
