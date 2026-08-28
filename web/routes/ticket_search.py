# -*- coding: utf-8 -*-
"""Поиск по тикетам (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

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



        # ── TICKET SEARCH API ───────────────────────────────────────────────────────
    @app .route ('/api/tickets/search',methods =['POST'])
    @login_required 
    def api_ticket_search ():
        """Поиск тикетов по фильтрам"""
        import json 
        import os 
        from datetime import datetime ,timedelta 

        data =request .get_json ()
        search =data .get ('search','').lower ()
        status =data .get ('status','')
        category =data .get ('category','')
        days =data .get ('days','')

        # Загрузить данные тикетов
        data_dir ='data'
        tickets =[]

        if os .path .exists (data_dir ):
            for filename in os .listdir (data_dir ):
                if filename .startswith ('ai_tickets_')and filename .endswith ('.json'):
                    guild_id =filename .replace ('ai_tickets_','').replace ('.json','')
                    filepath =os .path .join (data_dir ,filename )
                    try :
                        with open (filepath ,'r',encoding ='utf-8')as f :
                            ticket_data =json .load (f )
                            for ticket_id ,ticket in ticket_data .items ():
                            # Фильтр по статусу
                                if status and ticket .get ('status','open')!=status :
                                    continue 

                                    # Фильтр по категории
                                if category and ticket .get ('category','')!=category :
                                    continue 

                                    # Фильтр по дате
                                if days :
                                    created_at =ticket .get ('created_at','')
                                    if created_at :
                                        created_date =datetime .fromisoformat (created_at .replace ('Z','+00:00'))
                                        cutoff_date =datetime .now (created_date .tzinfo )-timedelta (days =int (days ))
                                        if created_date <cutoff_date :
                                            continue 

                                            # Фильтр по поиску
                                if search :
                                    search_fields =[
                                    str (ticket_id ),
                                    ticket .get ('user_name',''),
                                    ticket .get ('description',''),
                                    ticket .get ('category','')
                                    ]
                                    if not any (search in field .lower ()for field in search_fields ):
                                        continue 

                                tickets .append ({
                                'id':ticket_id ,
                                'guild_id':guild_id ,
                                'user_name':ticket .get ('user_name','Неизвестный'),
                                'status':ticket .get ('status','open'),
                                'category':ticket .get ('category','Без категории'),
                                'description':ticket .get ('description',''),
                                'channel_name':ticket .get ('channel_name',''),
                                'created_at':ticket .get ('created_at',''),
                                'closed_by':ticket .get ('closed_by','')
                                })
                    except Exception as _ex:
                        _log.debug("api_ticket_search(): подавлено: %s", _ex)

                        # Сортировка по дате (новые первые)
        tickets .sort (key =lambda x :x .get ('created_at',''),reverse =True )

        return jsonify ({
        'success':True ,
        'tickets':tickets [:100 ]# Максимум 100 результатов
        })


    @app .route ('/ticket-search')
    @login_required 
    def ticket_search_page ():
        """Страница поиска тикетов"""
        return render_template ('ticket_search.html',role =session .get ('role'),username =session .get ('username'))
