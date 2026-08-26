# -*- coding: utf-8 -*-
"""Коги, события, вебхуки, права тикетов (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

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


        # ── COG УПРАВЛЕНИЕ API ─────────────────────────────────────────────────────

    @app .route ('/api/cogs')
    @login_required 
    @role_required ('owner')
    def api_cogs ():
        import web .app as _app ;bot =_app .bot_instance 
        import os 
        # Скрыть служебные файлы, чтобы не путать пользователя:
        #  - имена с '_' / __init__ — вспомогательные (не cog'и)
        #  - NON_COG — модули-помощники на диске, загружаемые через import, а не как cog
        NON_COG ={'embed_utils','leveling_engagement'}
        all_cogs =[]
        _cogs_dir =os .path .join (_REPO_ROOT ,'cogs')
        for f in os .listdir (_cogs_dir ):
            if not f .endswith ('.py'):continue 
            name =f [:-3 ]
            if name .startswith ('_')or name in NON_COG :
                continue 
            all_cogs .append (name )
        if bot is None :
            from services .demo_cogs import demo_mode ,is_loaded 
            if demo_mode ():
                # демо-витрина: живого бота нет, модули «загружены»,
                # выключенные из менеджера — честно показаны выключенными
                return jsonify ([{'name':c ,'loaded':is_loaded (c )}for c in sorted (all_cogs )])
        loaded =[ext .split ('.')[-1 ]for ext in (bot .extensions if bot else [])]
        return jsonify ([{
        'name':c ,
        'loaded':c in loaded 
        }for c in sorted (all_cogs )])


    @app .route ('/api/cogs/<cog_name>/reload',methods =['POST'])
    @login_required 
    @role_required ('owner')
    def api_reload_cog (cog_name ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio 
        if not bot :return jsonify ({'error':'Бот офлайн'})
        async def do ():
            if f'cogs.{cog_name}'in bot .extensions :
                await (bot .reload_extension (f'cogs.{cog_name}'))
            else :
                await (bot .load_extension (f'cogs.{cog_name}'))
        try :
            asyncio .run_coroutine_threadsafe (do (),bot .loop ).result (timeout =10 )
            return jsonify ({'success':True })
        except Exception as e :
            return jsonify ({'error':str (e )})


    @app .route ('/api/cogs/<cog_name>/unload',methods =['POST'])
    @login_required 
    @role_required ('owner')
    def api_unload_cog (cog_name ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio 
        if not bot :return jsonify ({'error':'Бот офлайн'})
        if cog_name =='cog_manager':
            return jsonify ({'error':'Модуль удалён!'})
        async def do ():
            await (bot .unload_extension (f'cogs.{cog_name}'))
        try :
            asyncio .run_coroutine_threadsafe (do (),bot .loop ).result (timeout =10 )
            return jsonify ({'success':True })
        except Exception as e :
            return jsonify ({'error':str (e )})


            # ── СЕРВЕР ИНФОРМАЦИЯ API ───────────────────────────────────────────────────

    @app .route ('/api/guild/<guild_id>/info2')
    @login_required 
    @role_required ('mod')
    def api_guild_info2 (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        if not bot :return jsonify ({'error':'Бот офлайн'})
        guild =bot .get_guild (int (guild_id ))
        if not guild :return jsonify ({'error':'Сервер не найден'})
        return jsonify ({
        'id':str (guild .id ),
        'name':guild .name ,
        'description':guild .description or '',
        'icon':str (guild .icon .url )if guild .icon else None ,
        'banner':str (guild .banner .url )if guild .banner else None ,
        'splash':str (guild .splash .url )if guild .splash else None ,
        'member_count':guild .member_count ,
        'online_count':sum (1 for m in guild .members if m .status !=discord .Status .offline ),
        'bot_count':sum (1 for m in guild .members if m .bot ),
        'channel_count':len (guild .channels ),
        'role_count':len (guild .roles ),
        'emoji_count':len (guild .emojis ),
        'boost_level':guild .premium_tier ,
        'boost_count':guild .premium_subscription_count ,
        'created_at':guild .created_at .isoformat (),
        'owner_id':str (guild .owner_id ),
        'verification_level':str (guild .verification_level ),
        'features':list (guild .features ),
        })


        # ── ETKИNLИKLER API ──────────────────────────────────────────────────────

    @app .route ('/api/guild/<guild_id>/events')
    @login_required 
    @role_required ('mod')
    def api_guild_events (guild_id ):
        f =f'data/events_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ([])
        with open (f ,'r',encoding ='utf-8')as fp :
            data =json .load (fp )
        events =list (data .values ())
        events .sort (key =lambda x :x .get ('time',''))
        return jsonify (events )


    @app .route ('/api/guild/<guild_id>/events/<event_id>/delete',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_delete_event (guild_id ,event_id ):
        f =f'data/events_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ({'success':True })
        with open (f ,'r',encoding ='utf-8')as fp :data =json .load (fp )
        data .pop (event_id ,None )
        with open (f ,'w',encoding ='utf-8')as fp :json .dump (data ,fp ,indent =2 ,ensure_ascii =False )
        return jsonify ({'success':True })


        # ── РОЖДЕНИЕ ДЕНЬ API ───────────────────────────────────────────────────────

    @app .route ('/api/guild/<guild_id>/birthdays')
    @login_required 
    @role_required ('mod')
    def api_birthdays (guild_id ):
        f =f'data/birthdays_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ([])
        with open (f ,'r',encoding ='utf-8')as fp :data =json .load (fp )
        return jsonify ([{'user_id':k ,**v }for k ,v in data .items ()])


        # ── WEBHOOK API ──────────────────────────────────────────────────────────

    @app .route ('/api/guild/<guild_id>/webhooks')
    @login_required 
    @role_required ('admin')
    def api_guild_webhooks (guild_id ):
        f =f'data/webhooks_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ([])
        with open (f ,'r',encoding ='utf-8')as fp :return jsonify (list (json .load (fp ).values ()))


    @app .route ('/api/guild/<guild_id>/webhooks/send',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_send_webhook_v2 (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio ,discord as _discord 
        if not bot :return jsonify ({'error':'Бот офлайн'})
        data =request .get_json (silent =True )or {}
        wh_id =data .get ('webhook_id')
        message =data .get ('message','')
        username =data .get ('username','Aether')
        style =data .get ('style','')
        f =f'data/webhooks_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ({'error':'Вебхук не найден'})
        with open (f ,encoding='utf-8')as fp :whs =json .load (fp )
        if wh_id not in whs :return jsonify ({'error':'Вебхук не найден'})
        wh_data =whs [wh_id ]
        async def do ():
            channel =bot .get_channel (int (wh_data ['channel_id']))
            if channel :
                webhooks =await (channel .webhooks ())
                wh =_discord .utils .get (webhooks ,id =int (wh_id ))
                if wh :
                    # Components V2: сообщение блоками (контейнер, заголовки,
                    # разделители) — библиотека сама ставит флаг v2
                    if style =='v2':
                        from services .v2_layouts import rules_layout ,rules_embed
                        title =data .get ('title','Сообщение')
                        lines =data .get ('lines')or ([message ]if message else ['—'])
                        layout =rules_layout (title ,lines ,footer =username )
                        if layout is not None :
                            await (wh .send (view =layout ,username =username ))
                            return 
                        await (wh .send (embed =rules_embed (title ,lines ),
                        username =username ))
                        return 
                    await (wh .send (content =message ,username =username ))
        try :
            asyncio .run_coroutine_threadsafe (do (),bot .loop ).result (timeout =10 )
            return jsonify ({'success':True })
        except Exception as e :
            return jsonify ({'error':str (e )})


            # ── TICKET PERMISSIONS API ─────────────────────────────────────────────────
    @app .route ('/api/guild/<int:guild_id>/ticket-permissions')
    @login_required 
    def api_ticket_permissions_get (guild_id ):
        """Получить настройки разрешений тикетов"""
        cfg_path =f'data/ticket_permissions_{guild_id}.json'
        default ={
        'systems':{
        'ai_enabled':True ,
        'rate_limiter':True ,
        'auto_close':True ,
        'feedback':True ,
        'progress_indicator':True ,
        'complaint_system':True ,
        },
        'roles':{
        'mod_roles':[],
        'owner_roles':[],
        }
        }
        try :
            if os .path .exists (cfg_path ):
                with open (cfg_path ,'r',encoding ='utf-8')as f :
                    data =json .load (f )
                return jsonify ({'success':True ,'config':data })
            return jsonify ({'success':True ,'config':default })
        except Exception as e :
            return jsonify ({'success':False ,'error':str (e )}),500 


    @app .route ('/api/guild/<int:guild_id>/ticket-permissions',methods =['POST'])
    @login_required 
    def api_ticket_permissions_set (guild_id ):
        """Сохранить настройки разрешений тикетов"""
        data =request .get_json ()
        if not data :
            return jsonify ({'success':False ,'error':'Нет данных'}),400 

        cfg_path =f'data/ticket_permissions_{guild_id}.json'
        try :
            os .makedirs ('data',exist_ok =True )
            tmp =cfg_path +'.tmp'
            with open (tmp ,'w',encoding ='utf-8')as f :
                json .dump (data ,f ,ensure_ascii =False ,indent =2 )
            os .replace (tmp ,cfg_path )
            return jsonify ({'success':True })
        except Exception as e :
            return jsonify ({'success':False ,'error':str (e )}),500 
