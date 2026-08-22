# -*- coding: utf-8 -*-
"""OPS-центр тикетов (идеи #21-25): SLA, массовое закрытие, реопен, заметки, назначение.

Работает поверх того же файла data/ai_tickets_<gid>.json, что пишет
cogs/ticket.py (статусы/поля не переизобретаются; «открыт» = любой статус,
кроме 'closed' — так же считает и про-аналитика). Запись — атомарная.

Заметки модератора (notes) и назначение (assigned_to) — новые необязательные
поля тикета: ког их не трогает и не ломается (JSON-словарь, лишний ключ
безвреден).

Чтение — mod+ (страница и снимки). Точечные операции (закрыть/реопен/
назначить/заметить) — mod+, как существующий /tickets/<id>/close.
Массовое закрытие — admin+: масштаб больше точечного действия.
"""
import csv
import io
import json
import os
import tempfile
from datetime import datetime, timezone

from web.routes._common import (
    _log,
    render_template, session, request, jsonify, Response,
)

DEFAULT_SLA_HOURS = 24
SLA_CHOICES = (4, 12, 24, 48, 72)
NOTE_MAX = 300


def _path(gid):
    return f'data/ai_tickets_{int(gid)}.json'


def load_tickets(gid):
    """Словарь тикетов сервера из файла кога; битый/нет -> {}."""
    path = _path(gid)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as _ex:
        _log.debug("tickets_ops: файл не прочитан: %s", _ex)
        return {}
    return data if isinstance(data, dict) else {}


def save_tickets(gid, tickets):
    """Атомарная запись (временный файл + замена), чтобы не поймать полуфайл."""
    path = _path(gid)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.ai_tickets_', dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            json.dump(tickets, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError as _ex:
            _log.debug("tickets_ops: временный файл не удалён: %s", _ex)
        raise


def _parse_ts(ts):
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace('Z', '+00:00'))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)  # легаси-метки без пояса считаем UTC
    else:
        dt = dt.astimezone(timezone.utc)
    return dt


def is_open(ticket):
    return (ticket or {}).get('status') != 'closed'


def sla_snapshot(tickets, now=None, sla_hours=DEFAULT_SLA_HOURS):
    """Снимок SLA: открытые с возрастом, просроченные, среднее время закрытия."""
    now = now or datetime.now(timezone.utc)
    try:
        sla = float(sla_hours)
    except (TypeError, ValueError):
        sla = float(DEFAULT_SLA_HOURS)
    if sla <= 0:
        sla = float(DEFAULT_SLA_HOURS)

    open_items = []
    close_hours = []
    for tid, t in (tickets or {}).items():
        if not isinstance(t, dict):
            continue
        if is_open(t):
            created = _parse_ts(t.get('created_at'))
            age = round((now - created).total_seconds() / 3600, 1) if created else None
            open_items.append({
                'id': str(tid),
                'user_id': str(t.get('user_id') or ''),
                'category': t.get('category') or 'Другое',
                'created_at': t.get('created_at') or '',
                'age_h': age,
                'overdue': bool(age is not None and age > sla),
                'assigned_to': t.get('assigned_to') or '',
                'notes_count': len(t.get('notes') or []),
            })
        else:
            created = _parse_ts(t.get('created_at'))
            closed = _parse_ts(t.get('closed_at'))
            if created and closed and closed >= created:
                close_hours.append((closed - created).total_seconds() / 3600)
    open_items.sort(key=lambda x: -(x['age_h'] or -1))
    avg_close = round(sum(close_hours) / len(close_hours), 1) if close_hours else None
    reopened = sum(1 for t in (tickets or {}).values()
                   if isinstance(t, dict) and t.get('reopened_at'))
    return {
        'sla_hours': sla,
        'open_count': len(open_items),
        'overdue_count': sum(1 for i in open_items if i['overdue']),
        'overdue_ids': [i['id'] for i in open_items if i['overdue']],
        'avg_close_hours': avg_close,
        'closed_total': len(close_hours),
        'reopened_total': reopened,
        'items': open_items,
    }


def tickets_csv(tickets):
    """Плоский список тикетов для выгрузки: строки по всем статусам."""
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=';')
    w.writerow(['ID', 'Категория', 'Автор ID', 'Статус', 'Создан', 'Закрыт',
                'Закрыл', 'Ответственный', 'Заметок'])
    for tid in sorted(tickets or {}):
        t = tickets[tid]
        if not isinstance(t, dict):
            continue
        w.writerow([tid, t.get('category') or '', t.get('user_id') or '',
                    t.get('status') or '', t.get('created_at') or '',
                    t.get('closed_at') or '', t.get('closed_by') or '',
                    t.get('assigned_to') or '', len(t.get('notes') or [])])
    return buf.getvalue()


def bulk_close(tickets, ids, by, now=None):
    """Массовое закрытие. Возвращает (закрытые, пропущенные)."""
    now = now or datetime.now(timezone.utc)
    closed, skipped = [], []
    wanted = {str(i) for i in ids or []}
    for tid in wanted:
        t = tickets.get(tid)
        if not isinstance(t, dict) or not is_open(t):
            skipped.append(tid)
            continue
        t['status'] = 'closed'
        t['closed_at'] = now.isoformat()
        t['closed_by'] = by
        closed.append(tid)
    return closed, skipped


def reopen_ticket(tickets, tid):
    """Вернуть тикет в работу: статус 'open', поля закрытия стираются."""
    t = (tickets or {}).get(str(tid))
    if not isinstance(t, dict) or is_open(t):
        return False
    t['status'] = 'open'
    t.pop('closed_at', None)
    t.pop('closed_by', None)
    t['reopened_at'] = datetime.now(timezone.utc).isoformat()
    return True


def add_note(tickets, tid, text, by, now=None):
    """Заметка модератора к тикету. Возвращает (ok, ошибка или заметка)."""
    t = (tickets or {}).get(str(tid))
    if not isinstance(t, dict):
        return False, 'Тикет не найден.'
    text = (text or '').strip()
    if not text:
        return False, 'Введите текст заметки.'
    if len(text) > NOTE_MAX:
        return False, f'Заметка слишком длинная (максимум {NOTE_MAX}).'
    note = {'text': text, 'by': by,
            'at': (now or datetime.now(timezone.utc)).isoformat()}
    t.setdefault('notes', []).append(note)
    return True, note


def assign_ticket(tickets, tid, name, by):
    """Назначить ответственного (пустое имя — снять). Возвращает (ok, ошибка)."""
    t = (tickets or {}).get(str(tid))
    if not isinstance(t, dict):
        return False, 'Тикет не найден.'
    name = (name or '').strip()
    if name:
        t['assigned_to'] = name
        t['assigned_by'] = by
        t['assigned_at'] = datetime.now(timezone.utc).isoformat()
    else:
        t.pop('assigned_to', None)
        t.pop('assigned_by', None)
        t.pop('assigned_at', None)
    return True, ''


def author_history(tickets, user_id, exclude=None, limit=5):
    """История автора: всего тикетов + последние по дате создания (без текущего)."""
    uid = str(user_id or '')
    own = []
    for tid, t in (tickets or {}).items():
        if not isinstance(t, dict) or str(t.get('user_id') or '') != uid:
            continue
        if exclude is not None and str(tid) == str(exclude):
            continue
        own.append((str(t.get('created_at') or ''), str(tid),
                    t.get('category') or 'Другое', t.get('status') or 'open'))
    own.sort(reverse=True)
    return {
        'total': len(own) + (1 if exclude is not None else 0),
        'last': [{'id': tid, 'category': cat, 'status': st, 'created_at': day}
                 for day, tid, cat, st in own[:limit]],
    }


def ticket_card(tickets, tid):
    """Карточка тикета для модалки: заметки, назначение, статус, история автора."""
    t = (tickets or {}).get(str(tid))
    if not isinstance(t, dict):
        return None
    return {
        'id': str(tid),
        'user_id': str(t.get('user_id') or ''),
        'category': t.get('category') or 'Другое',
        'status': t.get('status') or 'open',
        'created_at': t.get('created_at') or '',
        'closed_at': t.get('closed_at') or '',
        'closed_by': t.get('closed_by') or '',
        'assigned_to': t.get('assigned_to') or '',
        'reopened_at': t.get('reopened_at') or '',
        'history': author_history(tickets, t.get('user_id'), exclude=tid),
        'notes': [{'text': n.get('text', ''), 'by': n.get('by', ''), 'at': n.get('at', '')}
                  for n in (t.get('notes') or []) if isinstance(n, dict)],
    }


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required

    @app.route('/tickets-ops')
    @login_required
    @role_required('mod')
    def tickets_ops_page():
        return render_template('tickets_ops.html', role=session.get('role'),
                               username=session.get('username'))

    @app.route('/api/tickets-ops/sla')
    @login_required
    @role_required('mod')
    def api_ops_sla():
        hours = request.args.get('h', DEFAULT_SLA_HOURS)
        gid = int(ctx.active_guild_id())
        body = sla_snapshot(load_tickets(gid), sla_hours=hours)
        body['success'] = True
        body['sla_choices'] = list(SLA_CHOICES)
        body['can_edit'] = session.get('role') in ('admin', 'owner')
        return jsonify(body)

    @app.route('/api/tickets-ops/<ticket_id>')
    @login_required
    @role_required('mod')
    def api_ops_card(ticket_id):
        card = ticket_card(load_tickets(int(ctx.active_guild_id())), ticket_id)
        if card is None:
            return jsonify({'success': False, 'error': 'Тикет не найден.'}), 404
        card['success'] = True
        return jsonify(card)

    @app.route('/api/tickets-ops/bulk-close', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_ops_bulk_close():
        data = request.get_json(silent=True) or {}
        ids = data.get('ids')
        if not isinstance(ids, list) or not ids:
            return jsonify({'success': False, 'error': 'Не выбраны тикеты.'}), 400
        gid = int(ctx.active_guild_id())
        tickets = load_tickets(gid)
        closed, skipped = bulk_close(tickets, ids,
                                     by='panel:%s' % session.get('username'))
        if not closed:
            return jsonify({'success': False,
                            'error': 'Нечего закрывать: все выбранные уже закрыты или не найдены.'}), 400
        save_tickets(gid, tickets)
        return jsonify({'success': True, 'closed': closed, 'skipped': skipped})

    @app.route('/api/tickets-ops/<ticket_id>/reopen', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_ops_reopen(ticket_id):
        gid = int(ctx.active_guild_id())
        tickets = load_tickets(gid)
        if not reopen_ticket(tickets, ticket_id):
            return jsonify({'success': False,
                            'error': 'Тикет не найден или уже открыт.'}), 404
        save_tickets(gid, tickets)
        return jsonify({'success': True})

    @app.route('/api/tickets-ops/<ticket_id>/note', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_ops_note(ticket_id):
        data = request.get_json(silent=True) or {}
        gid = int(ctx.active_guild_id())
        tickets = load_tickets(gid)
        ok, res = add_note(tickets, ticket_id, data.get('text'),
                           by='panel:%s' % session.get('username'))
        if not ok:
            code = 404 if 'не найден' in res else 400
            return jsonify({'success': False, 'error': res}), code
        save_tickets(gid, tickets)
        return jsonify({'success': True, 'note': res})

    @app.route('/api/tickets-ops/<ticket_id>/assign', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_ops_assign(ticket_id):
        data = request.get_json(silent=True) or {}
        gid = int(ctx.active_guild_id())
        tickets = load_tickets(gid)
        ok, err = assign_ticket(tickets, ticket_id, data.get('name'),
                                by='panel:%s' % session.get('username'))
        if not ok:
            return jsonify({'success': False, 'error': err}), 404
        save_tickets(gid, tickets)
        return jsonify({'success': True})

    @app.route('/api/tickets-ops/export.csv')
    @login_required
    @role_required('mod')
    def api_ops_export():
        """Плоская выгрузка всех тикетов сервера (идея #29)."""
        gid = int(ctx.active_guild_id())
        filename = 'tickets_%s_%s.csv' % (gid, datetime.now(timezone.utc).date().isoformat())
        return Response(
            '\ufeff' + tickets_csv(load_tickets(gid)),
            mimetype='text/csv; charset=utf-8',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'},
        )
