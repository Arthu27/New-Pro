# -*- coding: utf-8 -*-
"""Страницы-рендеры (простые шаблоны) (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

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
        main_guild_id =MAIN_GUILD_ID )


    @app .route ('/reaction-roles')
    @login_required 
    @role_required ('admin')
    def reaction_roles_page ():
        return render_template ('reaction_roles.html',role =session .get ('role'),username =session .get ('username'),main_guild_id =MAIN_GUILD_ID )


    @app .route ('/giveaway')
    @login_required 
    @role_required ('admin')
    def giveaway_page ():
        return render_template ('giveaway.html',role =session .get ('role'),username =session .get ('username'),guild_id =active_guild_id ())


    @app .route ('/polls')
    @login_required 
    @role_required ('mod')
    def polls_page ():
        return render_template ('polls.html',role =session .get ('role'),username =session .get ('username'))


    @app .route ('/autorole')
    @login_required 
    @role_required ('admin')
    def autorole_page ():
        return render_template ('autorole.html',role =session .get ('role'),username =session .get ('username'),main_guild_id =MAIN_GUILD_ID )


    @app .route ('/leveling')
    @login_required 
    @role_required ('owner')
    def leveling_page ():
        return render_template ('leveling.html',role =session .get ('role'),username =session .get ('username'),main_guild_id =MAIN_GUILD_ID )


    @app .route ('/ai-tickets')
    @login_required 
    @role_required ('mod')
    def ai_tickets_page ():
        """Показать диалоги AI-тикетов"""
        try :
            guild_id =int (session .get ('guild_id',MAIN_GUILD_ID )or 0 )
        except (TypeError ,ValueError ):
            guild_id =0 
        tickets_data =_load_ai_tickets (guild_id )if guild_id else {}

        # Bot instance'dan channel информация al
        import web .app as _app ;bot =_app .bot_instance 
        tickets_list =[]

        for channel_id ,ticket in tickets_data .items ():
            try :
                guild =bot .get_guild (int (guild_id ))
                channel =guild .get_channel (int (channel_id ))if guild else None 
                user =guild .get_member (ticket ['user_id'])if guild and ticket .get ('user_id')else None 

                tickets_list .append ({
                'channel_id':channel_id ,
                'channel_name':channel .name if channel else f"ticket-{channel_id}",
                'user_name':user .display_name if user else 'Неизвестно',
                'user_id':ticket .get ('user_id'),
                'status':ticket .get ('status','unknown'),
                'category':ticket .get ('category','общий'),
                'ai_message_count':ticket .get ('ai_message_count',0 ),
                'history':ticket .get ('history',[]),
                'escalated_at':ticket .get ('escalated_at'),
                'staff_notified':ticket .get ('staff_notified',False )
                })
            except Exception as _ex:
                _log.debug("ai_tickets_page(): подавлено: %s", _ex)

        return render_template (
        'ai_tickets.html',
        role =session .get ('role'),
        username =session .get ('username'),
        tickets =tickets_list 
        )


    @app .route ('/economy')
    @login_required 
    @role_required ('admin')
    def economy_page ():
        return render_template ('economy.html',role =session .get ('role'),username =session .get ('username'))


    @app .route ('/scheduled-messages')
    @login_required 
    @role_required ('owner')
    def scheduled_messages_page ():
        return render_template ('scheduled_messages.html',role =session .get ('role'),username =session .get ('username'),main_guild_id =MAIN_GUILD_ID )


    @app .route ('/custom-commands')
    @login_required 
    @role_required ('owner')
    def custom_commands_page ():
        return render_template ('custom_commands.html',role =session .get ('role'),username =session .get ('username'),
        main_guild_id =MAIN_GUILD_ID )


    @app .route ('/member-notes')
    @login_required 
    @role_required ('mod')
    def member_notes_page ():
        return render_template ('member_notes.html',role =session .get ('role'),username =session .get ('username'),main_guild_id =MAIN_GUILD_ID )


    @app .route ('/bulk-actions')
    @login_required 
    @role_required ('admin')
    def bulk_actions_page ():
        return render_template ('bulk_actions.html',role =session .get ('role'),username =session .get ('username'))


    @app .route ('/invite-tracker')
    @login_required 
    @role_required ('mod')
    def invite_tracker_page ():
        return render_template ('invite_tracker.html',role =session .get ('role'),username =session .get ('username'),main_guild_id =MAIN_GUILD_ID )


    @app .route ('/suggestions')
    @login_required 
    @role_required ('mod')
    def suggestions_page ():
        return render_template ('suggestions.html',role =session .get ('role'),username =session .get ('username'),main_guild_id =MAIN_GUILD_ID )


    @app .route ('/starboard')
    @login_required 
    @role_required ('mod')
    def starboard_page ():
        return render_template ('starboard.html',role =session .get ('role'),username =session .get ('username'),main_guild_id =MAIN_GUILD_ID )


    @app .route ('/yardim')
    @login_required 
    @role_required ('uye')
    def yardim_page ():
        return render_template ('yardim.html',role =session .get ('role'),username =session .get ('username'))


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


    @app .route ('/leveling-admin')
    @login_required 
    @role_required ('admin')
    def leveling_admin_page ():
        return render_template ('leveling_admin.html',role =session .get ('role'),username =session .get ('username'))


    @app .route ('/ai-moderation')
    @login_required 
    @role_required ('admin')
    def ai_moderation_page ():
        return render_template ('ai_moderation.html',role =session .get ('role'),username =session .get ('username'))


    @app .route ('/temp-moderation')
    @login_required 
    @role_required ('mod')
    def temp_moderation_page ():
        return render_template ('temp_moderation.html',role =session .get ('role'),username =session .get ('username'))


    @app .route ('/cog-manager')
    @login_required 
    @role_required ('owner')
    def cog_manager_page ():
        return render_template ('cog_manager.html',role =session .get ('role'),username =session .get ('username'))


    @app .route ('/warn-config')
    @login_required 
    @role_required ('admin')
    def warn_config_page ():
        return render_template ('warn_config.html',role =session .get ('role'),username =session .get ('username'),guild_id =active_guild_id ())


    @app .route ('/duty-panel-web')
    @login_required 
    @role_required ('admin')
    def duty_panel_web_page ():
        return render_template ('duty_panel.html',role =session .get ('role'),username =session .get ('username'),guild_id =active_guild_id ())


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
        return render_template ('change_password.html',role =session .get ('role'),username =session .get ('username'))


    # ── Липкие сообщения + Panic-локдаун (модуль cogs/mod_plus.py) ──────
    @app .route ('/mod-tools')
    @login_required 
    @role_required ('mod')
    def mod_tools_page ():
        return render_template ('mod_tools.html',role =session .get ('role'),username =session .get ('username'),guild_id =active_guild_id ())
