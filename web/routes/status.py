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
            after = request.args.get('after', 0, type=int) or 0
            items = get_live_logs(after_id=after, limit=250)
            last_id = items[-1]['id'] if items else after
            return jsonify({'ok': True, 'items': items, 'last_id': last_id})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500
