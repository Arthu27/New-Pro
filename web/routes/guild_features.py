# -*- coding: utf-8 -*-
"""Настройки фич сервера (welcome/autorole/leveling/economy/polls/etc) (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

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


    @app .route ('/api/guild/<guild_id>/welcome-settings',methods =['GET','POST'])
    @login_required 
    @role_required ('admin')
    def api_welcome_settings (guild_id ):
        f =f'data/welcome_{guild_id}.json'
        os .makedirs ('data',exist_ok =True )  # убеждаемся, что каталог data существует

        if request .method =='GET':
            if not os .path .exists (f ):
                return jsonify ({})
            try :
                with open (f ,'r',encoding ='utf-8')as fp :
                    return jsonify (json .load (fp ))
            except Exception as e :
                print (f'[WEB][ERR] welcome-settings GET error: {e}')
                return jsonify ({'error':str (e )})

                # POST request
        try :
            data =request .get_json (silent =True )or {}
            if not data :
                return jsonify ({'error':'Данные не переданы'})

            settings ={}
            if os .path .exists (f ):
                with open (f ,'r',encoding ='utf-8')as fp :
                    settings =json .load (fp )

            t =data .pop ('type',None )
            if not t :
                return jsonify ({'error':'Тип заметок не указан'})

            settings [t ]=data 
            with open (f ,'w',encoding ='utf-8')as fp :
                json .dump (settings ,fp ,indent =2 ,ensure_ascii =False )
            print (f'[WEB] welcome-settings saved for guild {guild_id}, type {t}')
            return jsonify ({'success':True })
        except Exception as e :
            print (f'[WEB][ERR] welcome-settings POST error: {e}')
            return jsonify ({'error':str (e )})












































