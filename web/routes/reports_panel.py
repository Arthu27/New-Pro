# -*- coding: utf-8 -*-
"""Отчёты поддержки (идеи #166-170): /reports в браузере.

Сервисы общие с когом: services.advanced_reporting (синглтоны report_builder
и analytics_engine) — те же объекты, что у cogs/report_cog: тикеты читаются
из data/customer_tickets.json, пользовательские отчёты лежат в
data/custom_reports.json — файл общий.

- «Сегодня» 1:1 /report-daily: report_builder.generate_daily_report, те же
  шесть метрик с подписями эмбеда (без эмодзи) и тем же форматом чисел.
- «Неделя» 1:1 /report-weekly: с разбивкой по дням (daily_breakdown).
- Спец-отчёт 1:1 /report-custom: days + тип tickets/sla/performance,
  неверный тип — текстом команды без префикса-эмодзи. Дата aware в
  customer_tickets.json уронит и команду, и нас — панель ловит честно,
  логирует и отвечает одной строкой вместо тихого 500.
- «Аналитика» 1:1 /report-analytics: analytics_engine.get_dashboard_analytics
  (обзор + топ-5 категорий + лучшие сотрудники).
- Библиотека пользовательских отчётов — публичный CRUD ReportBuilder
  (create_report/list_reports/generate_report/delete_report); id выдаёт
  панель по максимальному номеру, чтобы удаление не давало дубликатов.
- CSV: разбивка недели и статы спец-отчёта (BOM, ;).

Чтение — mod+; библиотеку и её генерацию меняет admin+ (команды отчётов в
боте требуют manage_guild, а generate_report пишет last_generated в общий
файл).
"""
from datetime import datetime, timedelta

from web.routes._common import (
    _log,
    render_template, session, request, jsonify, Response,
)

from services.advanced_reporting import report_builder, analytics_engine

ERR_TYPE = 'Неверный тип отчёта! (tickets/sla/performance)'  # слова /report-custom
ERR_REPORT = 'Отчёт не найден'
ERR_NAME = 'Название отчёта пустое'
ERR_METRICS = 'Выберите хотя бы одну метрику'
ERR_CALC = 'Не удалось собрать отчёт'
REPORT_TYPES = ('tickets', 'sla', 'performance')
METRICS = ('total_tickets', 'tickets_by_status', 'tickets_by_category',
           'tickets_by_priority', 'avg_resolution_time', 'tickets_by_day',
           'tickets_by_hour', 'top_categories')
FILTER_KEYS = ('status', 'category', 'priority')


def _safe(fn, *args, **kwargs):
    """Один вызов сервиса без тихого 500: (True, data) / (False, ERR_CALC)."""
    try:
        return True, fn(*args, **kwargs)
    except (TypeError, ValueError, KeyError) as exc:
        _log.debug('reports: %s: %s', getattr(fn, '__name__', fn), exc)
        return False, ERR_CALC


def daily_view():
    """Метрики /report-daily один в один (словари уже округлены сервисом)."""
    return _safe(report_builder.generate_daily_report)


def weekly_view():
    """Метрики /report-weekly: те же поля + daily_breakdown."""
    return _safe(report_builder.generate_weekly_report)


def custom_flow(days_raw, report_type):
    """/report-custom 1:1: days как int с дефолтом 30, тип строго из трёх."""
    report_type = str(report_type or 'tickets')
    if report_type not in REPORT_TYPES:
        return False, ERR_TYPE, None
    try:
        days = int(str(days_raw if days_raw is not None else '30').strip())
    except (TypeError, ValueError):
        days = 30
    ok, rep = _safe(report_builder.generate_custom_report,
                    days=days, report_type=report_type)
    if not ok:
        return False, rep, None
    return True, '', rep


def analytics_view():
    """/report-analytics 1:1: сводка движка за 30 дней."""
    return _safe(analytics_engine.get_dashboard_analytics)


def _next_report_id():
    """rep_N за максимальным номером: удаление не даёт дубликатов."""
    top = 0
    for rep in report_builder.list_reports():
        tail = str(rep['report_id']).rsplit('_', 1)[-1]
        if tail.isdigit():
            top = max(top, int(tail))
    return f'rep_{top + 1}'


def library_view():
    """list_reports сервиса, добитый фильтрами из того же хранилища."""
    out = []
    for rep in report_builder.list_reports():
        full = report_builder.reports.get(rep['report_id'], {})
        rep['filters'] = full.get('filters', {})
        out.append(rep)
    return out


def create_flow(name, metrics, filters):
    """create_report сервиса: метрики и фильтры — только известные."""
    name = str(name or '').strip()
    if not name:
        return False, ERR_NAME, None
    metrics = [m for m in (metrics or []) if m in METRICS]
    if not metrics:
        return False, ERR_METRICS, None
    clean_filters = {k: str(v) for k, v in (filters or {}).items()
                     if k in FILTER_KEYS and str(v or '').strip()}
    rid = _next_report_id()
    report_builder.create_report(rid, name, metrics, clean_filters)
    msg = f'Отчёт «{name}» сохранён. ID: {rid}.'
    return True, '', {'message': msg, 'reports': library_view()}


def generate_flow(report_id, days_raw):
    """generate_report за N дней: обновляет last_generated в общем файле."""
    rid = str(report_id or '')
    if not report_builder.get_report(rid):
        return False, ERR_REPORT, None
    try:
        days = int(str(days_raw if days_raw is not None else '30').strip())
    except (TypeError, ValueError):
        days = 30
    days = max(1, min(days, 3650))
    end = datetime.now()
    start = end - timedelta(days=days)
    ok, rep = _safe(report_builder.generate_report, rid, start, end)
    if not ok:
        return False, rep, None
    if 'error' in rep:  # страховка словами сервиса
        return False, ERR_REPORT, None
    return True, '', {'report': rep, 'reports': library_view()}


def delete_flow(report_id):
    rid = str(report_id or '')
    rep = report_builder.get_report(rid)
    if not rep or not report_builder.delete_report(rid):
        return False, ERR_REPORT, None
    total = len(library_view())
    return True, '', {'message': f'Отчёт «{rep["name"]}» удалён. '
                                 f'Всего отчётов: {total}.',
                      'reports': library_view()}


def weekly_csv_rows():
    ok, rep = weekly_view()
    if not ok:
        return []
    return [(day, rep['daily_breakdown'].get(day, 0))
            for day in sorted(rep['daily_breakdown'])]


def custom_csv_rows(days_raw, report_type):
    ok, err, rep = custom_flow(days_raw, report_type)
    if not ok:
        return []
    return [('period_start', rep['period_start']),
            ('period_end', rep['period_end']),
            ('report_type', rep['report_type'])] + list(rep['stats'].items())


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

    @app.route('/reports')
    @login_required
    @role_required('mod')
    def reports_page():
        return render_template('reports.html', role=session.get('role'),
                               username=session.get('username'),
                               guild_id=active_guild_id(),
                               can_edit=session.get('role') in ('admin', 'owner'))

    @app.route('/api/guild/<gid>/reports/view')
    @login_required
    @role_required('mod')
    def api_reports_view(gid):
        ok_d, daily = daily_view()
        ok_w, weekly = weekly_view()
        ok_a, analytics = analytics_view()
        return jsonify({'success': True,
                        'daily': daily if ok_d else None,
                        'daily_error': None if ok_d else daily,
                        'weekly': weekly if ok_w else None,
                        'weekly_error': None if ok_w else weekly,
                        'analytics': analytics if ok_a else None,
                        'analytics_error': None if ok_a else analytics,
                        'reports': library_view(),
                        'can_edit': session.get('role') in ('admin', 'owner')})

    @app.route('/api/guild/<gid>/reports/custom')
    @login_required
    @role_required('mod')
    def api_reports_custom(gid):
        ok, err, rep = custom_flow(request.args.get('days'),
                                   request.args.get('type'))
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        return jsonify({'success': True, **rep})

    @app.route('/api/guild/<gid>/reports/create', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_reports_create(gid):
        data = request.get_json(silent=True) or {}
        ok, err, payload = create_flow(data.get('name'), data.get('metrics'),
                                       data.get('filters'))
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        return jsonify({'success': True, **payload})

    @app.route('/api/guild/<gid>/reports/generate', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_reports_generate(gid):
        data = request.get_json(silent=True) or {}
        ok, err, payload = generate_flow(data.get('report_id'),
                                         data.get('days'))
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        return jsonify({'success': True, **payload})

    @app.route('/api/guild/<gid>/reports/delete', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_reports_delete(gid):
        ok, err, payload = delete_flow(
            (request.get_json(silent=True) or {}).get('report_id'))
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        return jsonify({'success': True, **payload})

    @app.route('/api/guild/<gid>/reports/weekly.csv')
    @login_required
    @role_required('mod')
    def api_reports_weekly_csv(gid):
        return _csv_response(gid, 'reports_weekly', 'date;tickets',
                             weekly_csv_rows())

    @app.route('/api/guild/<gid>/reports/custom.csv')
    @login_required
    @role_required('mod')
    def api_reports_custom_csv(gid):
        return _csv_response(gid, 'reports_custom', 'metric;value',
                             custom_csv_rows(request.args.get('days'),
                                             request.args.get('type')))
