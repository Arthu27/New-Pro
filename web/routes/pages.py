# -*- coding: utf-8 -*-
"""Страницы-рендеры (простые шаблоны) (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

from web.routes._common import (
    _run_async, _fetch_channel_msgs_async, _fetch_channel_msgs_sync,
    _notify_discord_sender, _fire_panel_notification,
    _process_action, _log,
    ms_normalize_query, ms_member_match, ms_search_members, ms_member_payload,
    ms_normalize_warn, ms_normalize_case, _REPO_ROOT,
    render_template, session, redirect, url_for, request, jsonify, Response,
    os, json, time, math, discord, datetime, timezone)

def register(ctx):
    app = ctx.app
    ROLES = ctx.ROLES
    login_required = ctx.login_required
    role_required = ctx.role_required
    MAIN_GUILD_ID = ctx.MAIN_GUILD_ID
    active_guild_id = ctx.active_guild_id
    _resolve_member_async = ctx._resolve_member_async


    @app .route ('/roles')
    @login_required 
    @role_required ('admin')
    def roles_page ():
        return render_template ('roles.html',role =session .get ('role'),username =session .get ('username'),
        main_guild_id =MAIN_GUILD_ID )


    @app .route ('/channels')
    @login_required 
    @role_required ('admin')
    def channels_page ():
        return render_template ('channels.html',role =session .get ('role'),username =session .get ('username'),main_guild_id =MAIN_GUILD_ID )


    @app .route ('/mod-history')
    @login_required 
    @role_required ('mod')
    def modhistory_page ():
        return render_template ('modhistory.html',role =session .get ('role'),username =session .get ('username'))


    @app .route ('/welcome-editor')
    @login_required 
    @role_required ('admin')
    def welcome_editor_page ():
        return render_template ('welcome_editor.html',role =session .get ('role'),username =session .get ('username'),
        main_guild_id =active_guild_id ())












    @app .route ('/member-notes')
    @login_required 
    @role_required ('mod')
    def member_notes_page ():
        return render_template ('member_notes.html',role =session .get ('role'),username =session .get ('username'),main_guild_id =MAIN_GUILD_ID )


    @app .route ('/bulk-actions')
    @login_required 
    @role_required ('admin')
    def bulk_actions_page ():
        return render_template ('bulk_actions.html',role =session .get ('role'),username =session .get ('username'),main_guild_id =session .get ('main_guild_id',''))


    @app .route ('/invite-tracker')
    @login_required 
    @role_required ('mod')
    def invite_tracker_page ():
        return render_template ('invite_tracker.html',role =session .get ('role'),username =session .get ('username'),main_guild_id =MAIN_GUILD_ID )






    @app .route ('/spravka')
    @login_required 
    @role_required ('uye')
    def spravka_page ():
        return render_template ('spravka.html',role =session .get ('role'),username =session .get ('username'))


        # ── НОВЫЙ SAYFALAR ────────────────────────────────────────────────────────

    @app .route ('/chat')
    @login_required 
    @role_required ('owner')
    def chat_page ():
        return render_template ('chat.html',role =session .get ('role'),username =session .get ('username'),guild_id =active_guild_id ())


    @app .route ('/bot-settings')
    @login_required 
    @role_required ('owner')
    def bot_settings_page ():
        return render_template ('bot_settings.html',role =session .get ('role'),username =session .get ('username'))


    @app .route ('/bot-diagnostics')
    @login_required 
    @role_required ('admin')
    def bot_diagnostics_page ():
        return render_template ('bot_diagnostics.html',role =session .get ('role'),username =session .get ('username'))




    @app .route ('/ai-moderation')
    @login_required 
    @role_required ('admin')
    def ai_moderation_page ():
        return render_template ('ai_moderation.html',role =session .get ('role'),username =session .get ('username'))


    @app .route ('/temp-moderation')
    @login_required 
    @role_required ('mod')
    def temp_moderation_page ():
        return render_template ('temp_moderation.html',role =session .get ('role'),username =session .get ('username'),guild_id =active_guild_id ())


    @app .route ('/cog-manager')
    @login_required 
    @role_required ('owner')
    def cog_manager_page ():
        return render_template ('cog_manager.html',role =session .get ('role'),username =session .get ('username'))


    @app .route ('/warn-config')
    @login_required
    @role_required ('admin')
    def warn_config_page ():
        # Настройка ступеней варнов живёт в одном месте — «Лестница наказаний».
        # Старая страница с конфликтующим форматом закрыта: редирект туда же.
        return redirect (url_for ('ladder_page'))




    @app .route ('/member-search')
    @login_required 
    @role_required ('admin')
    def member_search_page ():
        return render_template ('member_search.html',role =session .get ('role'),username =session .get ('username'),guild_id =active_guild_id ())


    @app .route ('/afk-list')
    @login_required 
    @role_required ('mod')
    def afk_list_page ():
        return render_template ('afk_list.html',role =session .get ('role'),username =session .get ('username'),guild_id =active_guild_id ())


    @app .route ('/watchlist-panel')
    @login_required 
    @role_required ('mod')
    def watchlist_panel_page ():
        return render_template ('watchlist.html',role =session .get ('role'),username =session .get ('username'),guild_id =active_guild_id ())


    @app .route ('/my-profile')
    @login_required 
    @role_required ('uye')
    def my_profile_page ():
        return render_template ('member_profile.html',role =session .get ('role'),username =session .get ('username'))


    @app .route ('/change-password')
    @login_required 
    @role_required ('uye')
    def change_password_page ():
        return render_template ('change_password.html',role =session .get ('role'),
                                username =session .get ('username'))


    # ── Липкие сообщения + Panic-локдаун (модуль cogs/mod_plus.py) ──────
    @app .route ('/mod-tools')
    @login_required 
    @role_required ('mod')
    def mod_tools_page ():
        return render_template ('mod_tools.html',role =session .get ('role'),username =session .get ('username'),guild_id =active_guild_id ())
