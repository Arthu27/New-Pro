# -*- coding: utf-8 -*-
"""Студия модерации — светлая рабочая среда модерации.

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
import time

from web.routes._common import (
    _log,
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

    @app.route('/mod-studio')
    @login_required
    @role_required('mod')
    def mod_center_page():
        return render_template('mod_studio.html', role=session.get('role'),
                               username=session.get('username'),
                               guild_id=active_guild_id())

    @app.route('/api/guild/<gid>/mod-studio/overview')
    @login_required
    @role_required('mod')
    def api_mod_studio_overview(gid):
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

    @app.route('/api/guild/<gid>/mod-studio/warn', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_mod_studio_warn(gid):
        data = _json()
        ok, err, res = MC.panel_warn(gid, data.get('user_id'), data.get('reason'),
                                     by=session.get('username'))
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        _ok, _err, uid = MC.validate_user_id(data.get('user_id'))
        MC.panel_log_add(gid, 'warn', uid, res['entry']['reason'],
                         by=session.get('username'))
        return jsonify({'success': True, 'total': res['total'], 'entry': res['entry']})

    @app.route('/api/guild/<gid>/mod-studio/unwarn', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_mod_studio_unwarn(gid):
        data = _json()
        ok, err, res = MC.panel_unwarn(gid, data.get('user_id'))
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        _ok, _err, uid = MC.validate_user_id(data.get('user_id'))
        MC.panel_log_add(gid, 'unwarn', uid,
                         str(res['removed'].get('reason') or ''),
                         by=session.get('username'))
        return jsonify({'success': True, 'removed': res['removed'], 'left': res['left']})

    @app.route('/api/guild/<gid>/mod-studio/amnesty', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_mod_studio_amnesty(gid):
        data = _json()
        ok, err, entry = MC.amnesty_user(gid, data.get('user_id'),
                                         by=session.get('username'))
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        MC.panel_log_add(gid, 'amnesty', entry['user_id'],
                         'списано варнов: %d' % entry['count'],
                         by=session.get('username'))
        return jsonify({'success': True, 'amnesty': MC.public_amnesty(entry)})

    @app.route('/api/guild/<gid>/mod-studio/amnesty/<int:aid>/undo', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_mod_studio_amnesty_undo(gid, aid):
        ok, err, restored = MC.undo_amnesty(gid, aid)
        if not ok:
            code = 404 if err == 'Запись амнистии не найдена' else 400
            return jsonify({'success': False, 'error': err}), code
        MC.panel_log_add(gid, 'amnesty_undo', '', 'возвращено варнов: %d' % restored,
                         by=session.get('username'))
        return jsonify({'success': True, 'restored': restored})

    @app.route('/api/guild/<gid>/mod-studio/reasons', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_mod_studio_reason_add(gid):
        data = _json()
        ok, err, item = MC.add_reason(gid, data.get('kind'), data.get('text'),
                                      by=session.get('username'))
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        MC.panel_log_add(gid, 'reason_add', '', item['text'],
                         by=session.get('username'))
        return jsonify({'success': True, 'item': item, 'reasons': MC.load_reasons(gid)})

    @app.route('/api/guild/<gid>/mod-studio/reasons/<kind>/<int:rid>/delete',
               methods=['POST'])
    @login_required
    @role_required('admin')
    def api_mod_studio_reason_delete(gid, kind, rid):
        ok, err, removed = MC.remove_reason(gid, kind, rid)
        if not ok:
            code = 404 if err == 'Причина не найдена' else 400
            return jsonify({'success': False, 'error': err}), code
        MC.panel_log_add(gid, 'reason_del', '', removed['text'],
                         by=session.get('username'))
        return jsonify({'success': True, 'removed': removed,
                        'reasons': MC.load_reasons(gid)})

    @app.route('/api/guild/<gid>/mod-studio/warns.csv')
    @login_required
    @role_required('mod')
    def api_mod_studio_warns_csv(gid):
        resp = Response(MC.csv_body(MC.WARN_CSV_HEADER, MC.warns_csv_rows(gid)),
                        mimetype='text/csv; charset=utf-8')
        resp.headers['Content-Disposition'] = (
            f'attachment; filename=modcenter_warns_{MC._gid_str(gid)}.csv')
        return resp

    @app.route('/api/guild/<gid>/mod-studio/radar.csv')
    @login_required
    @role_required('mod')
    def api_mod_studio_radar_csv(gid):
        resp = Response(MC.csv_body(MC.RADAR_CSV_HEADER, MC.radar_csv_rows(gid)),
                        mimetype='text/csv; charset=utf-8')
        resp.headers['Content-Disposition'] = (
            f'attachment; filename=modcenter_radar_{MC._gid_str(gid)}.csv')
        return resp


    @app.route('/api/guild/<gid>/mod-studio/journal')
    @login_required
    @role_required('mod')
    def api_mod_studio_journal(gid):
        """Журнал гильдии: категории/поиск/модератор, новые сверху."""
        q = str(request.args.get('query') or '').strip().lower()
        cat = str(request.args.get('category') or '').strip().lower()
        mod = str(request.args.get('mod') or '').strip().lower()
        events = []
        cat_counts = {}
        for ev in MC._read_audit(gid):
            if not isinstance(ev, dict):
                continue
            cat_e = str(ev.get('category') or '').strip()
            dt = MC._parse_ts(ev.get('timestamp'))
            if dt is None:
                continue
            if cat and cat_e.lower() != cat:
                continue
            mod_name = str(ev.get('mod_name') or '').strip()
            if mod and mod not in mod_name.lower():
                continue
            hay = ' '.join(str(ev.get(k) or '') for k in
                           ('action', 'user_name', 'reason', 'detail', 'channel'))
            if q and q not in hay.lower():
                continue
            cat_counts[cat_e] = cat_counts.get(cat_e, 0) + 1
            events.append((dt, {
                'category': cat_e,
                'action': str(ev.get('action') or ''),
                'user_id': str(ev.get('user_id') or '').strip(),
                'name': str(ev.get('user_name') or '').strip(),
                'mod_name': mod_name,
                'reason': str(ev.get('reason') or ev.get('detail') or '').strip(),
                'at': dt.isoformat(timespec='minutes'),
            }))
        events.sort(key=lambda t: t[0], reverse=True)
        return jsonify({'success': True,
                        'rows': [r for _dt, r in events[:250]],
                        'total': len(events),
                        'categories': cat_counts})

    @app.route('/api/guild/<gid>/mod-studio/temp-full')
    @login_required
    @role_required('mod')
    def api_mod_studio_temp_full(gid):
        """Все активные временные наказания (не только срочные)."""
        names = MC.names_from_audit(gid)
        rows = []
        counts = {'overdue': 0, 'soon': 0, 'week': 0, 'later': 0}
        for r in sorted(MC.load_temp_actions(gid), key=lambda x: x['until']):
            row = dict(r)
            row['name'] = names.get(r['user_id'], '')
            left = row['until'] - time.time()
            row['remaining_s'] = int(left)
            if left <= 0:
                counts['overdue'] += 1
            elif left <= 86400:
                counts['soon'] += 1
            elif left <= 3 * 86400:
                counts['week'] += 1
            else:
                counts['later'] += 1
            rows.append(row)
        return jsonify({'success': True, 'rows': rows, 'counts': counts})

    @app.route('/api/guild/<gid>/mod-studio/warns-list')
    @login_required
    @role_required('mod')
    def api_mod_studio_warns_list(gid):
        """Варны по участникам: счёт, последние причины, пороги."""
        names = MC.names_from_audit(gid)
        rows = []
        for uid, warns in MC.load_warns_map(gid).items():
            items = [{'reason': str(w.get('reason') or '').strip() or 'Без причины',
                      'mod': str(w.get('mod') or ''),
                      'at': str(w.get('timestamp') or '')[:10]}
                     for w in warns[-5:][::-1]]
            rows.append({'user_id': uid, 'name': names.get(uid, ''),
                         'count': len(warns), 'items': items})
        rows.sort(key=lambda r: (-r['count'], r['user_id']))
        return jsonify({'success': True, 'rows': rows,
                        'total_warns': sum(r['count'] for r in rows),
                        'steps': MC.load_warn_steps(gid)})

    @app.route('/api/guild/<gid>/mod-studio/history')
    @login_required
    @role_required('mod')
    def api_mod_studio_history(gid):
        """Таймлайн кар и снятий, новые сверху."""
        names = MC.names_from_audit(gid)
        rows = []
        for dt, action, uid, ev in reversed(MI.mod_events(gid)):
            if action not in MI.PUNISH_ACTIONS + MI.LIFT_ACTIONS:
                continue
            rows.append({
                'action': action,
                'kind': 'punish' if action in MI.PUNISH_ACTIONS else 'lift',
                'user_id': uid,
                'name': names.get(uid, ''),
                'mod_name': str(ev.get('mod_name') or '').strip(),
                'reason': str(ev.get('reason') or '').strip(),
                'at': dt.isoformat(timespec='minutes'),
            })
            if len(rows) >= 250:
                break
        return jsonify({'success': True, 'rows': rows})

    @app.route('/api/guild/<gid>/mod-studio/shield')
    @login_required
    @role_required('mod')
    def api_mod_studio_shield(gid):
        """Щит сервера: сводный статус всех защит одним снимком."""
        autofilter = MI._autofilter_check(gid)
        antiraid = MI._antiraid_check(gid)
        lockdown = {'active': False, 'count': 0, 'summary': '',
                    'since': '', 'by': '', 'reason': ''}
        try:
            from web.routes import lockdown_panel as LP
            state = LP._state(MC._gid_str(gid))
            view = LP.status_view(None, state)
            lockdown = {'active': view.get('count', 0) > 0,
                        'count': view.get('count', 0),
                        'summary': str(view.get('summary') or ''),
                        'since': str(view.get('since') or ''),
                        'by': str(view.get('by') or ''),
                        'reason': str(view.get('reason') or '')}
        except Exception as _ex:
            _log.debug('mod_studio: lockdown-статус недоступен: %s', _ex)
        security = {'tuned': False, 'detail': 'Не настроена'}
        sec_raw = MC._load_json('data/security_%s.json' % MC._gid_str(gid), None)
        if isinstance(sec_raw, dict) and sec_raw:
            on = sum(1 for v in sec_raw.values() if v)
            security = {'tuned': on > 0,
                        'detail': ('включено: %d' % on) if on else 'всё выключено'}
        return jsonify({'success': True,
                        'autofilter': autofilter,
                        'antiraid': antiraid,
                        'lockdown': lockdown,
                        'security': security})

    @app.route('/api/guild/<gid>/mod-studio/proofs')
    @login_required
    @role_required('mod')
    def api_mod_studio_proofs(gid):
        """Галерея демок: кто, кого, за что и доказательство."""
        raw = MC._load_json('data/modproof_%s.json' % MC._gid_str(gid), {})
        items = raw.get('items') if isinstance(raw, dict) else None
        rows = []
        if isinstance(items, dict):
            for pid, it in items.items():
                if not isinstance(it, dict):
                    continue
                rows.append({
                    'id': pid,
                    'user_name': str(it.get('user_name') or ''),
                    'user_id': str(it.get('user_id') or ''),
                    'mod_name': str(it.get('mod_name') or ''),
                    'action': str(it.get('action') or ''),
                    'reason': str(it.get('reason') or ''),
                    'link': str(it.get('link') or it.get('url') or ''),
                    'at': str(it.get('set_at') or ''),
                })
        rows.sort(key=lambda r: r['at'], reverse=True)
        return jsonify({'success': True, 'rows': rows[:60], 'total': len(rows)})

    @app.route('/api/guild/<gid>/mod-studio/appeals')
    @login_required
    @role_required('mod')
    def api_mod_studio_appeals(gid):
        """Апелляции: счётчики очереди и последние заявки."""
        try:
            from web.routes import appeals_panel as AP
            state = AP._state(MC._gid_str(gid))
            stats = AP.overview_stats(state)
            items = state.get('items') if isinstance(state, dict) else []
            rows = []
            for it in (items or []):
                if not isinstance(it, dict):
                    continue
                rows.append({
                    'id': it.get('id'),
                    'status': str(it.get('status') or ''),
                    'user': str(it.get('user_name') or it.get('user_id') or ''),
                    'reason': str(it.get('reason') or it.get('punishment_reason') or ''),
                    'created_at': str(it.get('created_at') or ''),
                })
            rows.sort(key=lambda r: r['created_at'], reverse=True)
            return jsonify({'success': True, 'stats': stats,
                            'rows': rows[:20], 'total': len(rows)})
        except Exception as _ex:
            _log.debug('mod_studio: апелляции недоступны: %s', _ex)
            return jsonify({'success': True,
                            'stats': {'pending': 0, 'accepted': 0, 'rejected': 0,
                                      'last': None},
                            'rows': [], 'total': 0})

    @app.route('/api/guild/<gid>/mod-studio/dossier')
    @login_required
    @role_required('mod')
    def api_mod_studio_dossier(gid):
        ok, err, data = MI.dossier(gid, request.args.get('user_id'))
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        return jsonify({'success': True, 'dossier': data})
