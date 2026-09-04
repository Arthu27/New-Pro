# -*- coding: utf-8 -*-
"""Профиль пользователя панели (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

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



        # ── USER PROFILE API ────────────────────────────────────────────────────────
    @app .route ('/api/user-profile',methods =['POST'])
    @login_required 
    def api_user_profile ():
        """Получить профиль пользователя"""
        import json 
        import os 

        data =request .get_json ()
        query =data .get ('query','').strip ()

        if not query :
            return jsonify ({'success':False ,'error':'Запрос не может быть пустым'}),400 

            # Найти пользователя в тикетах
        data_dir ='data'
        user_tickets =[]
        user_info =None 

        if os .path .exists (data_dir ):
            for filename in os .listdir (data_dir ):
                if filename .startswith ('ai_tickets_')and filename .endswith ('.json'):
                    filepath =os .path .join (data_dir ,filename )
                    try :
                        with open (filepath ,'r',encoding ='utf-8')as f :
                            tickets =json .load (f )
                            for ticket_id ,ticket in tickets .items ():
                                user_name =ticket .get ('user_name','')
                                user_id =ticket .get ('user_id','')

                                # Поиск по ID, имени или тегу
                                if (query in str (user_id )or 
                                query .lower ()in user_name .lower ()or 
                                query .lower ()in ticket .get ('user_tag','').lower ()):

                                    if not user_info :
                                        user_info ={
                                        'id':user_id ,
                                        'name':user_name ,
                                        'tag':ticket .get ('user_tag',''),
                                        'avatar_url':ticket .get ('avatar_url',''),
                                        'joined_at':ticket .get ('joined_at',''),
                                        'last_activity':ticket .get ('last_activity','')
                                        }

                                    user_tickets .append ({
                                    'id':ticket_id ,
                                    'status':ticket .get ('status','open'),
                                    'category':ticket .get ('category',''),
                                    'created_at':ticket .get ('created_at',''),
                                    'description':ticket .get ('description','')
                                    })
                    except Exception as _ex:
                        _log.debug("api_user_profile(): подавлено: %s", _ex)

        if not user_info :
            return jsonify ({'success':False ,'error':'Пользователь не найден'}),404 

            # Статистика
        total_tickets =len (user_tickets )
        open_tickets =sum (1 for t in user_tickets if t ['status']=='open')
        closed_tickets =total_tickets -open_tickets 

        # Загрузить предупреждения
        warnings =[]
        warnings_file ='data/warnings.json'
        if os .path .exists (warnings_file ):
            try :
                with open (warnings_file ,'r',encoding ='utf-8')as f :
                    all_warnings =json .load (f )
                    user_warnings =all_warnings .get (str (user_info ['id']),[])
                    warnings =user_warnings 
            except Exception as _ex:
                _log.debug("api_user_profile(): подавлено: %s", _ex)

        return jsonify ({
        'success':True ,
        'user':{
        **user_info ,
        'total_tickets':total_tickets ,
        'open_tickets':open_tickets ,
        'closed_tickets':closed_tickets ,
        'warnings_count':len (warnings ),
        'tickets':user_tickets [:20 ],# Последние 20 тикетов
        'warnings':warnings [:10 ]# Последние 10 предупреждений
        }
        })


    @app .route ('/user-profile')
    @login_required 
    def user_profile_page ():
        """Страница профиля пользователя"""
        return render_template ('user_profile.html',role =session .get ('role'),username =session .get ('username'))
