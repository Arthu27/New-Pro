# -*- coding: utf-8 -*-
"""Страницы-рендеры (кластер 2) (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

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


        # ── НОВЫЙ SAYFALAR ─────────────────────────────────────────────────────────

    @app .route ('/ticket-settings')
    @login_required
    @role_required ('admin')
    def ticket_settings_page ():
        # Система тикетов снята владельцем (жалобы идут через /report).
        # Роль модераторов и каналы настраиваются в «Жалобах» — туда и ведём.
        return redirect ('/reports')


    @app .route ('/automod-settings')
    @login_required 
    @role_required ('admin')
    def automod_settings_page ():
        return render_template ('automod_settings.html',role =session .get ('role'),username =session .get ('username'))


    @app .route ('/antiraid')
    @login_required 
    @role_required ('admin')
    def antiraid_page ():
        return render_template ('antiraid.html',role =session .get ('role'),username =session .get ('username'))


    @app .route ('/rejoin-roles')
    @login_required 
    @role_required ('admin')
    def rejoin_roles_page ():
        return render_template ('rejoin_roles.html',role =session .get ('role'),username =session .get ('username'))


    @app .route ('/backup')
    @login_required
    @role_required ('owner')
    def backup_page ():
        # Старый пункт «Бэкапы» в «Логах» дублировал рабочий раздел.
        # Ведём на единственный живой раздел бэкапов в группе «Бот».
        return redirect ('/backups')


    @app .route ('/panel-logs')
    @login_required 
    @role_required ('admin')
    def panel_logs_page ():
        return render_template ('panel_logs.html',role =session .get ('role'),username =session .get ('username'))


    @app .route ('/message-logs')
    @login_required 
    @role_required ('mod')
    def message_logs_page ():
        return render_template ('message_logs.html',role =session .get ('role'),username =session .get ('username'),main_guild_id =MAIN_GUILD_ID ,can_edit =session .get ('role')in ('admin','owner'))


    @app .route ('/voice-stats')
    @login_required 
    @role_required ('mod')
    def voice_stats_page ():
        return render_template ('voice_stats.html',role =session .get ('role'),username =session .get ('username'),main_guild_id =MAIN_GUILD_ID )


    @app .route ('/todo')
    @login_required 
    @role_required ('owner')
    def todo_page ():
        return render_template ('todo.html',role =session .get ('role'),username =session .get ('username'))


    @app .route ('/color-roles')
    @login_required 
    @role_required ('owner')
    def color_roles_page ():
        return render_template ('color_roles.html',role =session .get ('role'),username =session .get ('username'),main_guild_id =MAIN_GUILD_ID )


    @app .route ('/rules-editor')
    @login_required 
    @role_required ('admin')
    def rules_editor_page ():
        return render_template ('rules_editor.html',role =session .get ('role'),username =session .get ('username'),main_guild_id =MAIN_GUILD_ID )
