# -*- coding: utf-8 -*-
"""SLA-контроль (идеи #161-165): /sla в браузере.

Сервисы общие с когом: services.sla_management (синглтоны sla_manager,
sla_calculator, sla_breach_detector, sla_reporter) — те самые объекты, что
у cogs/sla_cog: политики и нарушения лежат в data/sla_policies.json и
data/sla_breaches.json, картина одна на бота и панель.

- Политики 1:1 /sla-info: список и карточки с лимитами ответа и решения по
  приоритетам; ошибки словами команды без префикса-эмодзи.
- Создание — как /sla-create (admin); лимиты — через публичный
  update_policy (он же сохраняет): пустое поле «не трогай», 0 — «сними».
- Статус тикета — как /sla-status: тикет ищет ticket_manager, показатели
  считает sla_calculator.calculate_sla; обреченные даты (часовой пояс в
  created_at сервис не стерпит — сравнение aware/naive) честно ловятся и
  логируются, без молчания.
- Нарушения — как /sla-breaches: что детектор уже записал, плюс сводка
  reporter.get_breach_summary; «перепроверить» прогоняет детектор по всем
  тикетам (то же делает и отчёт).
- Отчёт — SLAReporter.generate_compliance_report за 7/30/90 дней; фильтр
  по периоду — обязанность вызывающего (такова сигнатура сервиса), тикеты
  с битыми датами отбраковываются сухим прогоном детектора. CSV политик и
  нарушений.

Чтение — mod+; политики и перепроверку меняет admin+ (создание в боте идёт
с administrator).
"""
from datetime import datetime, timedelta

from web.routes._common import (
    _log,
    render_template, session, request, jsonify, Response,
)

from services.sla_management import (
    sla_manager, sla_calculator, sla_breach_detector, sla_reporter,
)
from services.ticket_system import ticket_manager

ERR_POLICY = 'SLA политика не найдена!'   # слова /sla-info
ERR_TICKET = 'Тикет не найден!'           # слова /sla-status
ERR_BREACHES = 'Нарушение SLA не найдено!'  # слова /sla-breaches
ERR_NAME = 'Название политики пустое'
ERR_MINUTES = 'Время — целое число минут'
ERR_LIMITS = 'Укажите хотя бы один лимит'
ERR_CALC = 'Не удалось посчитать SLA-показатели'
TYPE_LABELS = {'response_time': 'время ответа',
               'resolution_time': 'время решения'}


def policy_card(pol):
    """Карточка в духе /sla-info <id>: лимиты и условия как есть."""
    return {
        'policy_id': pol.policy_id,
        'name': pol.name,
        'description': pol.description,
        'response_times': dict(pol.response_times),
        'resolution_times': dict(pol.resolution_times),
        'business_hours': pol.business_hours,
        'conditions': ['%s %s %s' % (c.get('field'), c.get('operator'),
                                     c.get('value'))
                       for c in pol.conditions],
    }


def policies_view():
    """Список словами /sla-info без аргумента: все политики по id."""
    return [policy_card(p) for p in sorted(sla_manager.get_all_policies(),
                                           key=lambda p: p.policy_id)]


def create_flow(name, description):
    """/sla-create 1:1: создать политику админом."""
    name = str(name or '').strip()
    if not name:
        return False, ERR_NAME, None
    pol = sla_manager.create_policy(name, str(description or '').strip())
    msg = f'Политика «{pol.name}» создана. ID: {pol.policy_id}.'
    return True, '', {'message': msg, 'policies': policies_view()}


def _minutes(raw):
    """Пусто — не трогаем; 0 и меньше — снять лимит; иначе минуты."""
    if raw is None or str(raw).strip() == '':
        return None, None
    try:
        return int(str(raw).strip()), None
    except (TypeError, ValueError):
        return None, ERR_MINUTES


def configure_flow(policy_id, priority, resp_raw, res_raw):
    """Лимиты приоритета через update_policy — сохраняется, как в сервисе."""
    pol = sla_manager.get_policy(str(policy_id or ''))
    if not pol:
        return False, ERR_POLICY, None
    priority = str(priority or '').strip() or 'medium'
    resp, err = _minutes(resp_raw)
    if err:
        return False, err, None
    res, err = _minutes(res_raw)
    if err:
        return False, err, None
    if resp is None and res is None:
        return False, ERR_LIMITS, None
    rt = dict(pol.response_times)
    rs = dict(pol.resolution_times)
    parts = []
    for limits, value, word in ((rt, resp, 'ответ'), (rs, res, 'решение')):
        if value is None:
            continue
        if value <= 0:
            limits.pop(priority, None)
            parts.append(f'{word} снят')
        else:
            limits[priority] = value
            parts.append(f'{word} {value} мин')
    sla_manager.update_policy(pol.policy_id, response_times=rt,
                              resolution_times=rs)
    msg = f'Политика «{pol.name}»: {priority} — ' + ', '.join(parts) + '.'
    return True, '', {'message': msg, 'policies': policies_view()}


def delete_flow(policy_id):
    pid = str(policy_id or '')
    pol = sla_manager.get_policy(pid)
    if not pol or not sla_manager.delete_policy(pid):
        return False, ERR_POLICY, None
    total = len(sla_manager.get_all_policies())
    return True, '', {'message': f'Политика «{pol.name}» удалена. '
                                 f'Всего политик: {total}.',
                      'policies': policies_view()}


def status_flow(tid_raw):
    """/sla-status 1:1: тикет из ticket_manager, расчёт — calculate_sla."""
    tid = str(tid_raw or '').strip()
    if not tid:
        return False, ERR_TICKET, None
    ticket = ticket_manager.get_ticket(tid)
    if not ticket:
        return False, ERR_TICKET, None
    try:
        info = sla_calculator.calculate_sla(ticket)
    except (TypeError, ValueError, KeyError) as exc:
        _log.debug('sla status %s: %s', tid, exc)
        return False, ERR_CALC, None
    payload = dict(info)
    payload['ticket_id'] = tid
    payload['ticket_status'] = str(ticket.get('status', ''))
    return True, '', payload


def breaches_view():
    """Лента словами /sla-breaches: записанные детектором нарушения."""
    rows = []
    for b in sla_breach_detector.get_all_breaches():
        pol = sla_manager.get_policy(str(b.get('policy_id', '')))
        rows.append({
            'ticket_id': str(b.get('ticket_id', '')),
            'type': str(b.get('type', '')),
            'type_label': TYPE_LABELS.get(b.get('type'), str(b.get('type', ''))),
            'deadline': str(b.get('deadline', ''))[:16].replace('T', ' '),
            'breached_at': str(b.get('breached_at', ''))[:16].replace('T', ' '),
            'policy_id': str(b.get('policy_id', '')),
            'policy_name': pol.name if pol else str(b.get('policy_id', '')),
        })
    rows.sort(key=lambda r: r['breached_at'], reverse=True)
    return {'rows': rows, 'summary': sla_reporter.get_breach_summary(),
            'empty_note': ERR_BREACHES}


def _computable(tickets):
    """Отбраковать тикеты, на которых детектор падает (битые даты)."""
    good = []
    for t in tickets:
        try:
            sla_breach_detector.check_ticket(t)
        except (TypeError, ValueError, KeyError) as exc:
            _log.debug('sla report skip %s: %s', t.get('id'), exc)
            continue
        good.append(t)
    return good


def scan_flow():
    """Перепроверка: детектор прогоняет все тикеты — как в отчёте."""
    tickets = ticket_manager.get_all_tickets()
    good = _computable(tickets)
    view = breaches_view()
    view['checked'] = len(tickets)
    view['found'] = len(view['rows'])
    view['skipped'] = len(tickets) - len(good)
    return view


def _created_dt(ticket):
    """created_at → naive datetime; битые и пустые — None."""
    raw = str(ticket.get('created_at') or '')[:19]
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def report_flow(days_raw):
    """Отчёт reporter'а за N дней; фильтр периода — здесь, по сигнатуре."""
    try:
        days = int(str(days_raw if days_raw is not None else '30').strip())
    except (TypeError, ValueError):
        days = 30
    days = max(1, min(days, 3650))
    end = datetime.now()
    start = end - timedelta(days=days)
    tickets = []
    for t in ticket_manager.get_all_tickets():
        dt = _created_dt(t)
        if dt is None or start <= dt <= end:
            tickets.append(t)
    scoped = _computable(tickets)
    try:
        rep = sla_reporter.generate_compliance_report(scoped, start, end)
    except (TypeError, ValueError, KeyError) as exc:
        _log.debug('sla report: %s', exc)
        return False, ERR_CALC, None
    rep['days'] = days
    rep.setdefault('breach_rate', 0)
    return True, '', rep


def policies_csv_rows():
    """Строка на пару «политика × приоритет»; без лимитов — одна пустая."""
    rows = []
    for pol in sorted(sla_manager.get_all_policies(),
                      key=lambda p: p.policy_id):
        prios = sorted(set(pol.response_times) | set(pol.resolution_times))
        if not prios:
            rows.append((pol.policy_id, pol.name, pol.description, '', '', ''))
            continue
        for prio in prios:
            rows.append((pol.policy_id, pol.name, pol.description, prio,
                         pol.response_times.get(prio, ''),
                         pol.resolution_times.get(prio, '')))
    return rows


def breaches_csv_rows():
    return [(r['ticket_id'], r['type_label'], r['deadline'], r['breached_at'],
             r['policy_id'], r['policy_name'])
            for r in breaches_view()['rows']]


def _csv_cell(text):
    return str(text).replace(';', ',').replace('\r', ' ').replace('\n', ' ')


def _csv_response(gid, name, header, rows):
    body = '\ufeff' + header + '\n'
    body += '\n'.join(';'.join(_csv_cell(c) for c in row) for row in rows)
    resp = Response(body, mimetype='text/csv; charset=utf-8')
    resp.headers['Content-Disposition'] = (
        f'attachment; filename={name}_{gid}.csv')
    return resp


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required
    active_guild_id = ctx.active_guild_id

    @app.route('/sla')
    @login_required
    @role_required('mod')
    def sla_page():
        return render_template('sla.html', role=session.get('role'),
                               username=session.get('username'),
                               guild_id=active_guild_id(),
                               can_edit=session.get('role') in ('admin', 'owner'))

    @app.route('/api/guild/<gid>/sla/view')
    @login_required
    @role_required('mod')
    def api_sla_view(gid):
        breaches = breaches_view()
        return jsonify({'success': True,
                        'kpi': {'policies': len(sla_manager.get_all_policies()),
                                'tickets': len(ticket_manager.get_all_tickets()),
                                'breaches': breaches['summary']['total_breaches']},
                        'policies': policies_view(),
                        'breaches': breaches,
                        'can_edit': session.get('role') in ('admin', 'owner')})

    @app.route('/api/guild/<gid>/sla/ticket')
    @login_required
    @role_required('mod')
    def api_sla_ticket(gid):
        ok, err, payload = status_flow(request.args.get('tid'))
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        return jsonify({'success': True, **payload})

    @app.route('/api/guild/<gid>/sla/report')
    @login_required
    @role_required('mod')
    def api_sla_report(gid):
        ok, err, rep = report_flow(request.args.get('days'))
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        return jsonify({'success': True, **rep})

    @app.route('/api/guild/<gid>/sla/create', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_sla_create(gid):
        data = request.get_json(silent=True) or {}
        ok, err, payload = create_flow(data.get('name'), data.get('description'))
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        return jsonify({'success': True, **payload})

    @app.route('/api/guild/<gid>/sla/configure', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_sla_configure(gid):
        data = request.get_json(silent=True) or {}
        ok, err, payload = configure_flow(data.get('policy_id'),
                                          data.get('priority'),
                                          data.get('response_minutes'),
                                          data.get('resolution_minutes'))
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        return jsonify({'success': True, **payload})

    @app.route('/api/guild/<gid>/sla/delete', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_sla_delete(gid):
        ok, err, payload = delete_flow(
            (request.get_json(silent=True) or {}).get('policy_id'))
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        return jsonify({'success': True, **payload})

    @app.route('/api/guild/<gid>/sla/scan', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_sla_scan(gid):
        return jsonify({'success': True, **scan_flow()})

    @app.route('/api/guild/<gid>/sla/policies.csv')
    @login_required
    @role_required('mod')
    def api_sla_policies_csv(gid):
        return _csv_response(gid, 'sla_policies',
                             'policy_id;name;description;priority;'
                             'response_min;resolution_min',
                             policies_csv_rows())

    @app.route('/api/guild/<gid>/sla/breaches.csv')
    @login_required
    @role_required('mod')
    def api_sla_breaches_csv(gid):
        return _csv_response(gid, 'sla_breaches',
                             'ticket_id;type;deadline;breached_at;'
                             'policy_id;policy_name',
                             breaches_csv_rows())
