# -*- coding: utf-8 -*-
"""Ключевые страницы статистики (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

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


            # ── PAGE ROUTES ──────────────────────────────────────────────────────────

    @app .route ('/ai_ticket_stats')
    @login_required 
    @role_required ('mod')
    def ai_ticket_stats ():
        """AI ticket статистика страница"""
        guild_id =session .get ('selected_guild')
        if not guild_id :
            return redirect (url_for ('guilds_page'))

        stats =calculate_ai_ticket_stats (int (guild_id ))

        return render_template (
        'ai_ticket_stats.html',
        role =session .get ('role'),
        username =session .get ('username'),
        stats =stats 
        )


    @app .route ('/bot-stats')
    @login_required 
    @role_required ('mod')
    def bot_stats_page ():
        return render_template ('bot_stats.html',role =session .get ('role'),username =session .get ('username'))


    @app .route ('/analytics')
    @login_required 
    @role_required ('mod')
    def analytics_page ():
        return render_template ('analytics.html',role =session .get ('role'),username =session .get ('username'),main_guild_id =MAIN_GUILD_ID )


    @app .route ('/server-health')
    @login_required 
    @role_required ('mod')
    def sunucu_health_page ():
        return render_template ('server_health.html',role =session .get ('role'),username =session .get ('username'))
