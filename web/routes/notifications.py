# -*- coding: utf-8 -*-
"""Уведомления панели (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

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



        # ── NOTIFICATIONS API ───────────────────────────────────────────────────────
    @app .route ('/api/notifications/settings',methods =['GET'])
    @login_required 
    def api_notifications_settings_get ():
        """Получить настройки уведомлений"""
        import json 
        import os 

        settings_file ='data/notification_settings.json'
        default_settings ={
        'web_enabled':True ,
        'discord_enabled':True ,
        'email_enabled':False ,
        'event_ticket_open':True ,
        'event_ticket_message':True ,
        'event_ticket_close':True ,
        'event_priority_change':False ,
        'event_assignment':False ,
        'event_warn':True ,
        'event_mod_action':True ,
        'event_staff_apply':True ,
        'discord_channel':'',
        'webhook_url':'',
        'smtp_server':'',
        'smtp_port':587 ,
        'smtp_email':'',
        'smtp_password':''
        }

        if os .path .exists (settings_file ):
            try :
                with open (settings_file ,'r',encoding ='utf-8')as f :
                    settings =json .load (f )
                    # Merge with defaults
                    for key ,value in default_settings .items ():
                        if key not in settings :
                            settings [key ]=value 
            except Exception :
                settings =default_settings 
        else :
            settings =default_settings 

        return jsonify ({'success':True ,'settings':settings })


    @app .route ('/api/notifications/settings',methods =['POST'])
    @login_required 
    def api_notifications_settings_post ():
        """Сохранить настройки уведомлений"""
        import json 
        import os 

        data =request .get_json ()

        settings_file ='data/notification_settings.json'
        os .makedirs ('data',exist_ok =True )

        try :
            with open (settings_file ,'w',encoding ='utf-8')as f :
                json .dump (data ,f ,ensure_ascii =False ,indent =2 )
            return jsonify ({'success':True })
        except Exception as e :
            return jsonify ({'success':False ,'error':str (e )}),500 


    @app .route ('/api/notifications/test',methods =['POST'])
    @login_required 
    def api_notifications_test ():
        """Отправить тестовое уведомление по всем настроенным каналам"""
        try :
            from services .notification_dispatcher import send_test
            channels =send_test (discord_sender =_notify_discord_sender )
            return jsonify ({'success':True ,'channels':channels })
        except Exception as e :
            return jsonify ({'success':False ,'error':str (e )}),500 


    @app .route ('/api/notifications/history',methods =['GET'])
    @login_required 
    def api_notifications_history ():
        """Получить историю уведомлений"""
        import json 
        import os 

        history_file ='data/notification_history.json'

        if os .path .exists (history_file ):
            try :
                with open (history_file ,'r',encoding ='utf-8')as f :
                    history =json .load (f )
            except Exception :
                history =[]
        else :
            history =[]

            # Сортировка по дате (новые первые)
        history .sort (key =lambda x :x .get ('created_at',''),reverse =True )

        # Чистим markdown из видимых полей — панель разметку не рендерит
        try :
            import web .app as _app
            for _h in history :
                _app ._clean_md_fields (_h )
        except Exception as _ex:
            _log.debug("api_notifications_history(): подавлено: %s", _ex)

        return jsonify ({'success':True ,'notifications':history [:50 ]})# Максимум 50


    @app .route ('/notifications')
    @login_required 
    def notifications_page ():
        """Страница настроек уведомлений (только персонал)"""
        if ROLES .get (session .get ('role'),-1 )<ROLES .get ('mod',999 ):
            return redirect (url_for ('index'))
        return render_template ('notifications.html',role =session .get ('role'),username =session .get ('username'))
