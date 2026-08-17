# -*- coding: utf-8 -*-
"""Центр модерации — единая страница модерации нового поколения.

Заменил пары «Мод-контроль»/«Мод-анализ»: один экран, четыре вкладки
(Пульт / Контроль / Аналитика / Досье), меньше пояснений — больше
действий. Вся логика переиспользуется из проверенных модулей:
- web/routes/mod_control.py — причины, «на грани», амнистия, радар,
  варн из панели, CSV, последние действия, журнал панели;
- web/routes/mod_insights.py — субъекты, досье, эффективность,
  команда, тренд, рецидивисты, чек-лист готовности.

Своих хранилищ у модуля нет — только склейка. Чтение mod+,
мутации admin+ (как в предшественниках).
"""
from web.routes._common import (
    render_template, session, request, jsonify, Response,
)

from web.routes import mod_control as MC
from web.routes import mod_insights as MI


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required
    active_guild_id = ctx.active_guild_id

    def _json():
        return request.get_json(silent=True) or {}

    @app.route('/mod-center')
    @login_required
    @role_required('mod')
    def mod_center_page():
        return render_template('mod_center.html', role=session.get('role'),
                               username=session.get('username'),
                               guild_id=active_guild_id())

    @app.route('/api/guild/<gid>/mod-center/overview')
    @login_required
    @role_required('mod')
    def api_mod_center_overview(gid):
        days = MI._norm_days(request.args.get('days'), MI.EFFECT_DEFAULT_DAYS)
        events = MI.mod_events(gid)
        names = MC.names_from_audit(gid)
        steps = MC.load_warn_steps(gid)
        warns_map = MC.load_warns_map(gid)
        items = MC.at_risk_users(warns_map, steps, names=names)
        radar_rows = MC.load_temp_actions(gid)
        for r in radar_rows:
            r['name'] = names.get(r['user_id'], '')
        amnesty_log = MC.load_amnesty_log(gid)
        return jsonify({
            'success': True,
            'reason_kinds': [{'key': k, 'label': MC.REASON_KIND_LABELS[k]}
                             for k in MC.REASON_KINDS],
            'reasons': MC.load_reasons(gid),
            'risk': {
                'tuned': bool(steps),
                'steps': steps,
                'items': items,
                'edge': sum(1 for r in items if r['gap'] == 1),
            },
            'radar': MC.expiry_radar(radar_rows),
            'amnesty': [MC.public_amnesty(a) for a in reversed(amnesty_log)][:10],
            'amnesty_total': len(amnesty_log),
            'recent': MC.recent_actions(gid),
            'recent7': MC.recent_punish_count(gid),
            'panel_log': MC.panel_log(gid),
            'warns_total': sum(len(v) for v in warns_map.values()),
            'subjects': MI.subjects(gid),
            'effectiveness': MI.punishment_effectiveness(events, days=days),
            'team': MI.team_activity(gid, days=days),
            'trend': MI.punishment_trend(gid, days=days),
            'repeat': MI.repeat_offenders(gid, days=days),
            'checklist': MI.readiness_checklist(gid),
            'can_edit': session.get('role') in ('admin', 'owner'),
        })

    @app.route('/api/guild/<gid>/mod-center/warn', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_mod_center_warn(gid):
        data = _json()
        ok, err, res = MC.panel_warn(gid, data.get('user_id'), data.get('reason'),
                                     by=session.get('username'))
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        _ok, _err, uid = MC.validate_user_id(data.get('user_id'))
        MC.panel_log_add(gid, 'warn', uid, res['entry']['reason'],
                         by=session.get('username'))
        return jsonify({'success': True, 'total': res['total'], 'entry': res['entry']})

    @app.route('/api/guild/<gid>/mod-center/unwarn', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_mod_center_unwarn(gid):
        data = _json()
        ok, err, res = MC.panel_unwarn(gid, data.get('user_id'))
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        _ok, _err, uid = MC.validate_user_id(data.get('user_id'))
        MC.panel_log_add(gid, 'unwarn', uid,
                         str(res['removed'].get('reason') or ''),
                         by=session.get('username'))
        return jsonify({'success': True, 'removed': res['removed'], 'left': res['left']})

    @app.route('/api/guild/<gid>/mod-center/amnesty', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_mod_center_amnesty(gid):
        data = _json()
        ok, err, entry = MC.amnesty_user(gid, data.get('user_id'),
                                         by=session.get('username'))
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        MC.panel_log_add(gid, 'amnesty', entry['user_id'],
                         'списано варнов: %d' % entry['count'],
                         by=session.get('username'))
        return jsonify({'success': True, 'amnesty': MC.public_amnesty(entry)})

    @app.route('/api/guild/<gid>/mod-center/amnesty/<int:aid>/undo', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_mod_center_amnesty_undo(gid, aid):
        ok, err, restored = MC.undo_amnesty(gid, aid)
        if not ok:
            code = 404 if err == 'Запись амнистии не найдена' else 400
            return jsonify({'success': False, 'error': err}), code
        MC.panel_log_add(gid, 'amnesty_undo', '', 'возвращено варнов: %d' % restored,
                         by=session.get('username'))
        return jsonify({'success': True, 'restored': restored})

    @app.route('/api/guild/<gid>/mod-center/reasons', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_mod_center_reason_add(gid):
        data = _json()
        ok, err, item = MC.add_reason(gid, data.get('kind'), data.get('text'),
                                      by=session.get('username'))
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        MC.panel_log_add(gid, 'reason_add', '', item['text'],
                         by=session.get('username'))
        return jsonify({'success': True, 'item': item, 'reasons': MC.load_reasons(gid)})

    @app.route('/api/guild/<gid>/mod-center/reasons/<kind>/<int:rid>/delete',
               methods=['POST'])
    @login_required
    @role_required('admin')
    def api_mod_center_reason_delete(gid, kind, rid):
        ok, err, removed = MC.remove_reason(gid, kind, rid)
        if not ok:
            code = 404 if err == 'Причина не найдена' else 400
            return jsonify({'success': False, 'error': err}), code
        MC.panel_log_add(gid, 'reason_del', '', removed['text'],
                         by=session.get('username'))
        return jsonify({'success': True, 'removed': removed,
                        'reasons': MC.load_reasons(gid)})

    @app.route('/api/guild/<gid>/mod-center/warns.csv')
    @login_required
    @role_required('mod')
    def api_mod_center_warns_csv(gid):
        resp = Response(MC.csv_body(MC.WARN_CSV_HEADER, MC.warns_csv_rows(gid)),
                        mimetype='text/csv; charset=utf-8')
        resp.headers['Content-Disposition'] = (
            f'attachment; filename=modcenter_warns_{MC._gid_str(gid)}.csv')
        return resp

    @app.route('/api/guild/<gid>/mod-center/radar.csv')
    @login_required
    @role_required('mod')
    def api_mod_center_radar_csv(gid):
        resp = Response(MC.csv_body(MC.RADAR_CSV_HEADER, MC.radar_csv_rows(gid)),
                        mimetype='text/csv; charset=utf-8')
        resp.headers['Content-Disposition'] = (
            f'attachment; filename=modcenter_radar_{MC._gid_str(gid)}.csv')
        return resp

    @app.route('/api/guild/<gid>/mod-center/dossier')
    @login_required
    @role_required('mod')
    def api_mod_center_dossier(gid):
        ok, err, data = MI.dossier(gid, request.args.get('user_id'))
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        return jsonify({'success': True, 'dossier': data})
