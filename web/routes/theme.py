# -*- coding: utf-8 -*-
"""Тема панели (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

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



        # ── THEME SETTINGS API ──────────────────────────────────────────────────────
    @app .route ('/api/theme/settings',methods =['GET'])
    @login_required 
    def api_theme_settings_get ():
        """Получить настройки темы"""
        import json 
        import os 

        theme_file ='data/theme_settings.json'
        default_settings ={
        'theme':'dark',
        'accent_color':'#5865F2',
        'font_size':14 
        }

        if os .path .exists (theme_file ):
            try :
                with open (theme_file ,'r',encoding ='utf-8')as f :
                    settings =json .load (f )
            except Exception :
                settings =default_settings 
        else :
            settings =default_settings 

        return jsonify ({'success':True ,'settings':settings })


    @app .route ('/api/theme/settings',methods =['POST'])
    @login_required 
    def api_theme_settings_post ():
        """Сохранить настройки темы"""
        import json 
        import os 

        data =request .get_json ()

        theme_file ='data/theme_settings.json'
        os .makedirs ('data',exist_ok =True )

        try :
            with open (theme_file ,'w',encoding ='utf-8')as f :
                json .dump (data ,f ,ensure_ascii =False ,indent =2 )
            return jsonify ({'success':True })
        except Exception as e :
            return jsonify ({'success':False ,'error':str (e )}),500 


    @app .route ('/theme-settings')
    @login_required 
    def theme_settings_page ():
        """Страница настроек темы"""
        return render_template ('theme_settings.html',role =session .get ('role'),username =session .get ('username'))
