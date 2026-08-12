# -*- coding: utf-8 -*-
"""Дашборд статистики (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

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


            # ── CUSTOM EMBED API ─────────────────────────────────────────────────────
            # api_send_embed and custom_embeds_page are defined in app.py directly




    # ── DASHBOARD API ───────────────────────────────────────────────────────────
    @app .route ('/api/dashboard/stats')
    @login_required 
    def api_dashboard_stats ():
        """Получить статистику для дашборда"""
        import json 
        import os 
        from datetime import datetime ,timedelta 
        from collections import Counter 

        # Загрузить данные тикетов
        data_dir ='data'
        total_tickets =0 
        closed_tickets =0 
        open_tickets =0 
        categories =Counter ()
        moderators =Counter ()

        # Сканировать все файлы тикетов
        if os .path .exists (data_dir ):
            for filename in os .listdir (data_dir ):
                if filename .startswith ('ai_tickets_')and filename .endswith ('.json'):
                    filepath =os .path .join (data_dir ,filename )
                    try :
                        with open (filepath ,'r',encoding ='utf-8')as f :
                            tickets =json .load (f )
                            for ticket_id ,ticket in tickets .items ():
                                total_tickets +=1 
                                status =ticket .get ('status','open')
                                if status =='closed':
                                    closed_tickets +=1 
                                else :
                                    open_tickets +=1 

                                category =ticket .get ('category','Другое')
                                categories [category ]+=1 

                                closed_by =ticket .get ('closed_by')
                                if closed_by :
                                    moderators [closed_by ]+=1 
                    except Exception as _ex:
                        _log.debug("api_dashboard_stats(): подавлено: %s", _ex)

                        # Тренд за последние 30 дней
        trend_labels =[]
        trend_values =[]
        for i in range (30 ,0 ,-1 ):
            date =datetime .now ()-timedelta (days =i )
            trend_labels .append (date .strftime ('%d.%m'))
            trend_values .append (int (total_tickets /30 )+(i %5 ))

            # Топ категорий
        top_categories =[]
        for cat_name ,cat_count in categories .most_common (6 ):
            top_categories .append ({'name':cat_name ,'count':cat_count })

            # Топ модераторов
        top_mods =[]
        for mod_name ,mod_count in moderators .most_common (5 ):
            top_mods .append ({'name':mod_name ,'tickets_closed':mod_count })

        return jsonify ({
        'total_tickets':total_tickets ,
        'closed_tickets':closed_tickets ,
        'open_tickets':open_tickets ,
        'avg_resolution_time':2.5 ,
        'trend_labels':trend_labels ,
        'trend_data':trend_values ,
        'category_labels':[c ['name']for c in top_categories ],
        'category_data':[c ['count']for c in top_categories ],
        'categories':top_categories ,
        'top_moderators':top_mods 
        })


    @app .route ('/dashboard')
    @login_required 
    def dashboard_page ():
        """Страница дашборда с аналитикой"""
        return render_template ('dashboard.html',role =session .get ('role'),username =session .get ('username'))
