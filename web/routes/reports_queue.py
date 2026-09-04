# -*- coding: utf-8 -*-
"""Очередь репортов участников (панель-зеркало cogs/reports.py).

Тикеты (/report → приватная ветка) живут в SQLite data/reports.db —
читаем через общие функции services/reports_core. Решение выносится
модераторами в самой ветке Discord — панель честно показывает очередь
и сводку, а не дублирует механику.

Чтение — mod+.
"""

from web.routes._common import (
    _safe_json_obj,
    _log,
    render_template, session, request, jsonify,
)

KIND_META = {'card': ('Жалоба', 'fa-flag', 'danger'),
             'report': ('Репорт', 'fa-flag', 'danger'),
             'appeal': ('Апелляция', 'fa-scale-balanced', 'info')}


def _guild_channels_roles(gid):
    """Списки текстовых каналов и ролей гильдии (для пикеров настройки).

    Делегируем общему резолверу: раньше здесь был только bot.get_guild(),
    который в бою регулярно промахивается (кэш гильдий ещё не наполнен),
    и пикеры «Канал для жалоб»/«Роль модераторов» оставались с одной
    строкой «— не задан —», хотя /api/channels те же данные отдавал.
    """
    from web.routes.guild_admin import guild_channels_roles
    return guild_channels_roles(gid)


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

    @app.route('/api/guild/<gid>/report-settings', methods=['GET', 'POST'])
    @login_required
    @role_required('admin')
    def api_report_settings(gid):
        """Канал репортов и роль модераторов — владелец выбирает в панели.

        Хранится в data/reports_<gid>.json (тот же конфиг, что /report-setup).
        """
        from services import reports_core as RC

        def _valid_id(x):
            try:
                return str(int(str(x).strip()))
            except (TypeError, ValueError):
                return ''

        gid = active_guild_id()
        if request.method == 'GET':
            cfg = RC.load_cfg(gid)
            # Показываем ЕДИНЫЙ источник роли модераторов (если в конфиге
            # репортов пусто, подтянется значение из старых страниц).
            try:
                from services.mod_role import get_mod_role_id
                unified_rid = get_mod_role_id(gid)
            except Exception:
                unified_rid = ''
            channels, roles = _guild_channels_roles(gid)
            return jsonify({'success': True,
                            'channel_id': cfg.get('channel_id', ''),
                            'mod_role_id': cfg.get('mod_role_id') or unified_rid,
                            'expiry_days': cfg.get('expiry_days', 90),
                            'channels': channels, 'roles': roles})

        data = _safe_json_obj()
        cfg = RC.load_cfg(gid)
        cid = _valid_id(data.get('channel_id'))
        rid = _valid_id(data.get('mod_role_id'))
        # пустая строка = «не задано»; валидируем, что канал/роль существуют
        channels, roles = _guild_channels_roles(gid)
        ch_ids = {c['id'] for c in channels}
        role_ids = {r['id'] for r in roles}
        if cid and ch_ids and cid not in ch_ids:
            return jsonify({'success': False,
                            'error': f'Канал {cid} не найден на сервере'}), 400
        if rid and role_ids and rid not in role_ids:
            return jsonify({'success': False,
                            'error': f'Роль {rid} не найдена на сервере'}), 400
        cfg['channel_id'] = cid
        cfg['mod_role_id'] = rid
        RC.save_cfg(gid, cfg)
        # Единый источник роли модераторов: зеркалим выбор во все системы,
        # которые исторически хранили свою роль (призыв модеров, заявки),
        # чтобы «настроил тут — работает везде».
        try:
            from services.mod_role import set_mod_role_id
            set_mod_role_id(gid, rid)
        except Exception as _ex:
            _log.debug('reports: зеркалирование роли модераторов: %s', _ex)
        return jsonify({'success': True,
                        'channel_id': cid, 'mod_role_id': rid,
                        'channels': channels, 'roles': roles})
