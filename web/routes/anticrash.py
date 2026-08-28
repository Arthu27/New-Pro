# -*- coding: utf-8 -*-
"""Анти-краш центр (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

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


    # ── ANTI-CRASH merkezi ──────────────────────────────────────────────
    def _anticrash_handler():
        import web.app as _app
        bot = _app.bot_instance
        return getattr(bot, 'error_handler', None) if bot else None


    @app.route('/anticrash')
    @login_required
    @role_required('admin')
    def anticrash_page():
        return render_template('anticrash.html', role=session.get('role'), username=session.get('username'))


    @app.route('/api/anticrash/overview')
    @login_required
    @role_required('admin')
    def api_anticrash_overview():
        eh = _anticrash_handler()
        if not eh:
            import web.app as _app
            if _app._demo_mode():
                # демо: здоровый обработчик — страница живая в превью
                now = time.time()
                days = []
                for i in range(6, -1, -1):
                    days.append({'day': time.strftime('%Y-%m-%d', time.localtime(now - i * 86400)), 'count': (i * 7) % 4})
                return jsonify({
                    'ok': True,
                    'master_enabled': True,
                    'uptime_sec': 45000,
                    'uptime_human': '12ч 30м 0с',
                    'total_errors': 318,
                    'errors_last_hour': 2,
                    'critical': 5,
                    'filtered': 96,
                    'repeats_hidden': 41,
                    'warnings_total': 17,
                    'warnings': {'HTTP 429': 6, 'Timeout': 4, 'Gateway': 3},
                    'disconnects': 11,
                    'disconnects_hour': 1,
                    'webhook_sent': 12,
                    'webhook_dropped': 0,
                    'webhook_on': False,
                    'alerts_sent': 9,
                    'alerts_dropped': 0,
                    'alerts_queued': 0,
                    'loop_lag_max': 0.84,
                    'loop_lag_recent': 0.12,
                    'top_types': [{'name': 'HTTPException', 'count': 74}, {'name': 'Timeout', 'count': 41}, {'name': 'AttributeError', 'count': 29}],
                    'top_cogs': [{'name': 'Moderation', 'count': 58}, {'name': 'Tickets', 'count': 33}, {'name': 'Leveling', 'count': 21}],
                    'breakers': [],
                    'daily7': days,
                    'last_errors': [
                        {'module': 'cogs.moderation', 'text': 'HTTPException: 429 Too Many Requests', 'count': 12, 'ts': now - 60},
                        {'module': 'cogs.tickets', 'text': 'Timeout waiting for response', 'count': 5, 'ts': now - 900},
                    ],
                    'guilds': 1,
                    'latency_ms': 14,
                    'channel_configured': False,
                })
            return jsonify({'ok': False, 'error': 'Обработчик офлайн (бот не запущен)'})
        return jsonify(eh.get_overview())


    @app.route('/api/anticrash/config', methods=['GET', 'POST'])
    @login_required
    @role_required('admin')
    def api_anticrash_config():
        from error_handler import CONFIG_META, DEFAULT_CONFIG
        eh = _anticrash_handler()
        if not eh:
            import web.app as _app
            if _app._demo_mode():
                return jsonify({
                    'ok': True,
                    'config': dict(DEFAULT_CONFIG),
                    'order': list(DEFAULT_CONFIG.keys()),
                    'meta': {k: {'label': v[0], 'desc': v[1], 'type': v[2]} for k, v in CONFIG_META.items()},
                })
            return jsonify({'ok': False, 'error': 'Обработчик офлайн'}), 503
        if request.method == 'GET':
            return jsonify({
                'ok': True,
                'config': eh.config,
                'order': list(DEFAULT_CONFIG.keys()),
                'meta': {k: {'label': v[0], 'desc': v[1], 'type': v[2]} for k, v in CONFIG_META.items()},
            })
        data = request.get_json(silent=True) or {}
        updated, errors = {}, {}
        for k, v in data.items():
            try:
                updated[k] = eh.update_config(k, v)
            except KeyError:
                errors[k] = 'неизвестный ключ'
            except (ValueError, TypeError) as e:
                errors[k] = str(e)
        if errors:
            return jsonify({'ok': False, 'updated': updated, 'errors': errors}), 400
        return jsonify({'ok': True, 'config': eh.config})


    @app.route('/api/anticrash/reset', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_anticrash_reset():
        eh = _anticrash_handler()
        if not eh:
            return jsonify({'ok': False, 'error': 'Обработчик офлайн'}), 503
        eh.reset_stats()
        return jsonify({'ok': True})
