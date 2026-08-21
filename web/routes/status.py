# -*- coding: utf-8 -*-
"""Публичный статус и консоль/логи (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

from web.routes._common import (
    _run_async, _fetch_channel_msgs_async, _fetch_channel_msgs_sync,
    _load_ai_tickets, _notify_discord_sender, _fire_panel_notification,
    _process_action, _log,
    ms_normalize_query, ms_member_match, ms_search_members, ms_member_payload,
    ms_normalize_warn, ms_normalize_case, calculate_ai_ticket_stats, _REPO_ROOT,
    render_template, session, redirect, url_for, request, jsonify, Response,
    os, json, time, math, discord, datetime, timezone,
)

def register(ctx):
    app = ctx.app
    ROLES = ctx.ROLES
    login_required = ctx.login_required
    role_required = ctx.role_required
    MAIN_GUILD_ID = ctx.MAIN_GUILD_ID
    active_guild_id = ctx.active_guild_id
    _resolve_member_async = ctx._resolve_member_async


    # ── Публичная статус-страница (без логина) ───────────────────────────
    @app.route('/status')
    def status_public_page():
        return render_template('status_public.html')


    @app.route('/api/status-public')
    def api_status_public():
        import web.app as _app
        # Демо-режим: бот «живой» (панель показывает типичную картину)
        if _app._demo_mode():
            up = 11 * 3600 + int(time.time() % 7200)
            h2, m2, s2 = up // 3600, (up % 3600) // 60, up % 60
            return jsonify({
                'ok': True,
                'online': True,
                'latency_ms': 12 + (int(time.time() * 10) % 19),
                'guilds': 1,
                'users_cached': 1247,
                'uptime_sec': up,
                'uptime_human': f'{h2}ч {m2}м {s2}с',
                'version': '2.0',
                'updated': datetime.now(timezone.utc).isoformat(),
            })
        bot = _app.bot_instance
        online = False
        latency_ms = 0
        guilds = 0
        users_cached = 0
        uptime_sec = 0
        if bot is not None:
            try:
                online = not bot.is_closed()
            except Exception:
                online = False
            try:
                lat = getattr(bot, 'latency', None)
                if lat is not None and math.isfinite(lat):
                    latency_ms = max(0, round(lat * 1000))
            except Exception:
                latency_ms = 0
            try:
                guilds = len(getattr(bot, 'guilds', []) or [])
            except Exception:
                guilds = 0
            try:
                users_cached = len(getattr(bot, 'users', []) or [])
            except Exception:
                users_cached = 0
            eh = getattr(bot, 'error_handler', None)
            if eh is not None:
                try:
                    uptime_sec = max(0, int(time.time() - eh.stats.get('started_at', time.time())))
                except Exception:
                    uptime_sec = 0
        h, m, s_ = uptime_sec // 3600, (uptime_sec % 3600) // 60, uptime_sec % 60
        days = uptime_sec // 86400
        if days:
            uptime_human = f'{days}д {h % 24}ч {m}м'
        else:
            uptime_human = f'{h}ч {m}м {s_}с'
        return jsonify({
            'ok': True,
            'online': online,
            'latency_ms': latency_ms,
            'guilds': guilds,
            'users_cached': users_cached,
            'uptime_sec': uptime_sec,
            'uptime_human': uptime_human,
            'version': '2.0',
            'updated': datetime.now(timezone.utc).isoformat(),
        })


    # ── Оперативный центр ───────────────────────────────────────────────
    @app.route('/ops-center')
    @login_required
    @role_required('admin')
    def ops_center_page():
        return render_template('ops_center.html', role=session.get('role'), username=session.get('username'))


    # ── Канбан-доска команды ─────────────────────────────────────────────
    @app.route('/team-board')
    @login_required
    @role_required('mod')
    def team_board_page():
        return render_template('team_board.html', role=session.get('role'),
                               username=session.get('username'))


    @app.route('/api/team-board')
    @login_required
    @role_required('mod')
    def api_team_board():
        from services.team_board import board_view
        return jsonify({'ok': True, **board_view()})


    @app.route('/api/team-board', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_team_board_add():
        from services.team_board import add_task
        payload = request.get_json(silent=True) or {}
        task, err = add_task(
            title=payload.get('title', ''),
            status=payload.get('status', 'todo'),
            priority=payload.get('priority', 'mid'),
            assignee=payload.get('assignee', ''),
            due=payload.get('due', ''),
            note=payload.get('note', ''),
            author=session.get('username', ''),
        )
        if err:
            return jsonify({'ok': False, 'error': err}), 400
        return jsonify({'ok': True, 'task': task})


    @app.route('/api/team-board/<int:task_id>', methods=['PATCH'])
    @login_required
    @role_required('mod')
    def api_team_board_patch(task_id):
        from services.team_board import update_task
        patch = request.get_json(silent=True) or {}
        task, err = update_task(task_id, patch)
        if err:
            return jsonify({'ok': False, 'error': err}), 400
        return jsonify({'ok': True, 'task': task})


    @app.route('/api/team-board/<int:task_id>', methods=['DELETE'])
    @login_required
    @role_required('mod')
    def api_team_board_delete(task_id):
        from services.team_board import delete_task
        ok, err = delete_task(task_id)
        if err:
            return jsonify({'ok': False, 'error': err}), 404
        return jsonify({'ok': True})


    @app.route('/api/team-board/reorder', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_team_board_reorder():
        from services.team_board import reorder
        payload = request.get_json(silent=True) or {}
        ok, err = reorder(payload.get('columns', {}))
        if err:
            return jsonify({'ok': False, 'error': err}), 400
        return jsonify({'ok': ok})


    # ── Центр модерации (сводный штаб раздела) ───────────────────────────
    @app.route('/mod-center')
    @login_required
    @role_required('mod')
    def mod_center_page():
        return render_template('mod_center.html', role=session.get('role'),
                               username=session.get('username'))

    # ── Экран дежурного (полноэкранная живая стена модерации) ────────────
    @app.route('/mod-kiosk')
    @login_required
    @role_required('mod')
    def mod_kiosk_page():
        return render_template('mod_kiosk.html', role=session.get('role'),
                               username=session.get('username'),
                               main_guild_id=session.get('main_guild_id', ''))


    # ── Студия темы ──────────────────────────────────────────────────────
    @app.route('/theme-studio')
    @login_required
    def theme_studio_page():
        return render_template('theme_studio.html', role=session.get('role'),
                               username=session.get('username'))


    # ── Живая консоль логов ──────────────────────────────────────────────
    @app.route('/konsol')
    @login_required
    @role_required('admin')
    def konsol_page():
        return render_template('konsol.html', role=session.get('role'), username=session.get('username'))


    @app.route('/api/live-logs')
    @login_required
    @role_required('admin')
    def api_live_logs():
        try:
            from logger import get_live_logs
            import web.app as _app
            after = request.args.get('after', 0, type=int) or 0
            items = get_live_logs(after_id=after, limit=250)
            last_id = items[-1]['id'] if items else after
            # демо: живая консоль с реалистичными строками (включая HEALTH-лог бота)
            if _app._demo_mode():
                import time as _t
                _now = int(_t.time())
                _demo_lines = [
                    (_now - 58, 'INFO', 'errors',
                     'HEALTH | uptime 2ч 40м 4с | guilds 1 | ping 159ms | errors 0 (hour 0, crit 0, filtered 0, repeats 0) | warn 0 | dc 2 | webhook 0/0 | lag max 0.0s | alerts 0'),
                    (_now - 50, 'INFO', 'aether',
                     'Команды синхронизированы · слэш-команд: 84'),
                    (_now - 41, 'WARNING', 'music',
                     'Трек пропущен: источник вернул пустой аудиопоток'),
                    (_now - 25, 'INFO', 'moderation',
                     'Варн выдан участнику toxicguy (причина: спам)'),
                    (_now - 11, 'ERROR', 'api',
                     'Discord API 429 (rate limit): повтор через 3.2s'),
                ]
                demo_items = [
                    {'id': _now - _i, 'ts': _now - _i, 'level': _lvl, 'name': _nm, 'msg': _msg}
                    for _i, (_ts, _lvl, _nm, _msg) in enumerate(_demo_lines)
                ]
                items = demo_items + items
                items.sort(key=lambda x: x.get('id', 0))
                last_id = items[-1]['id'] if items else after
            items = [i for i in items if i.get('id', 0) > after]
            return jsonify({'ok': True, 'items': items, 'last_id': last_id})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500
