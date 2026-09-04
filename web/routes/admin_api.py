# -*- coding: utf-8 -*-
"""Управление ботом: health, temp-mod, коги (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

from web.routes._common import (
    _run_async, _fetch_channel_msgs_async, _fetch_channel_msgs_sync,
    _notify_discord_sender, _fire_panel_notification,
    _process_action, _log, _live_publish, viewer_member, acl_action_allowed,
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


        # ── BOT DIAGNOSTICS API ────────────────────────────────────
    @app .route ('/api/bot/health')
    @login_required 
    def api_bot_health ():
        import web .app as _app ;bot =_app .bot_instance 
        if not bot :
            if _app ._demo_mode ():
                # демо: типичный здоровый бот (страница диагностики живая в превью)
                now =time .time ()
                hist =[]
                for i in range (30 ,0 ,-1 ):
                    hist .append ({
                        'timestamp':now -i *60 ,
                        'uptime_sec':45000 -i *60 ,
                        'guilds':1 ,'users':1247 ,'cogs_loaded':23 ,'commands':118 ,
                        'latency_ms':round (10 +((i *7 )% 28 ),1 ),
                        'errors_last_min':(1 if i %17 ==0 else 0 ),
                        'is_ws_connected':True ,
                        'memory_mb':round (298 +((i *3 )% 90 ),1 ),
                        'cpu_percent':round (9 +((i *5 )% 26 ),1 ),
                        'threads':44 + (i %5 ),
                    })
                return jsonify ({
                    'current':hist [-1 ],
                    'history':hist ,
                    'error_log':[{'ts':now -3600 ,'msg':'demo: пример ошибки из лога'}],
                    'cog_perf':{'AIModeration':0.004 ,'Logs':0.002 },
                    'repair_count':{'watchdog_restarts':1 },
                })
            return jsonify ({'error':'Бот офлайн'}),503 
        from cogs .diagnostics import Diagnostics 
        cog =bot .get_cog ('Diagnostics')
        if not cog :
            return jsonify ({'error':'Модуль не загружен'}),404 
        health =cog .get_health_snapshot ()
        # Try to load from file
        import json as _json 
        try :
            with open ('data/bot_health.json','r',encoding ='utf-8')as f :
                persisted =_json .load (f )
                return jsonify (persisted )
        except Exception :
            return jsonify ({'current':health ,'history':[],'error_log':[],'cog_perf':{},'repair_count':{}})


    @app .route ('/api/bot/errors')
    @login_required 
    @role_required ('admin')
    def api_bot_errors ():
        import json as _json 
        try :
            with open ('data/error_log.json','r',encoding ='utf-8')as f :
                log =_json .load (f )
                return jsonify (log [-20 :])
        except Exception :
            return jsonify ([])


    @app .route ('/api/bot/hot-reload',methods =['POST'])
    @login_required 
    @role_required ('owner')
    def api_bot_hot_reload ():
        import web .app as _app ;bot =_app .bot_instance 
        if not bot :
            return jsonify ({'error':'Бот офлайн'}),503 
            # Trigger via discord bot
        from cogs .diagnostics import Diagnostics 
        cog =bot .get_cog ('Diagnostics')
        if not cog :
            return jsonify ({'error':'Модуль не загружен'}),404 
            # Re-check files
        import asyncio 
        reloaded =[]
        import hashlib ,os 
        for filename in os .listdir ('cogs'):
            if filename .endswith ('.py')and filename !='__init__.py':
                cog_name =filename [:-3 ]
                if cog_name in ('embed_utils'):continue 
                filepath =f'cogs/{filename}'
                with open (filepath ,'rb')as f :
                    h =hashlib .md5 (f .read ()).hexdigest ()
                if cog .cog_hash_cache .get (cog_name )!=h :
                    try :
                        ext =f'cogs.{cog_name}'
                        if ext in (getattr (bot ,'extensions',None )or {}): 
                            asyncio .run_coroutine_threadsafe (bot .reload_extension (ext ),bot .loop ).result (timeout =10 )
                        else :
                            asyncio .run_coroutine_threadsafe (bot .load_extension (ext ),bot .loop ).result (timeout =10 )
                        reloaded .append (cog_name )
                    except Exception as _ex:
                        _log.debug("api_bot_hot_reload(): подавлено: %s", _ex)
                cog .cog_hash_cache [cog_name ]=h 
        if reloaded :
            try :
                from slash_budget import apply_slash_budget
                apply_slash_budget (bot .tree )
            except Exception as _ex :
                _log .debug ('api_bot_hot_reload(): apply_slash_budget: %s',_ex )
        return jsonify ({'reloaded':reloaded })


        # NOTE: api_bot_gc / api_bot_diagnose / api_bot_restart are defined in web/app.py.
        # Defining them here again would clash with Flask's endpoint registry
        # ("View function mapping is overwriting an existing endpoint function").

        # ── TEMP MODERATION API ─────────────────────────────────
    @app .route ('/api/temp-mod/active')
    @login_required 
    @role_required ('mod')
    def api_temp_mod_active ():
        import web .app as _app ;bot =_app .bot_instance 
        from cogs .temp_moderation import TempModeration 
        if not bot :
            # демо: активных временных наказаний нет — страница честно пустая
            if _app ._demo_mode ():
                return jsonify ({'mutes':[],'bans':[],'kicks':[],'scheduled':[]})
            return jsonify ({'error':'Бот офлайн'}),503 
        cog =bot .get_cog ('TempModeration')
        if not cog :
            return jsonify ({'error':'Модуль не загружен'}),404 
        guild_id =str (session .get ('selected_guild')or MAIN_GUILD_ID )
        # Defensive: mutes/bans/kicks dict-of-dicts may be missing or shaped differently.
        mutes =(getattr (cog ,'_mutes',{})or {}).get (guild_id ,{})or {}
        bans =(getattr (cog ,'_bans',{})or {}).get (guild_id ,{})or {}
        kicks =(getattr (cog ,'_kicks',{})or {}).get (guild_id ,{})or {}
        scheduled =getattr (cog ,'_scheduled',[])or []
        scheduled =[s for s in scheduled 
        if isinstance (s ,dict )
        and s .get ('guild_id')==guild_id 
        and s .get ('status')=='pending']
        return jsonify ({
        'mutes':list (mutes .values ())if isinstance (mutes ,dict )else [],
        'bans':list (bans .values ())if isinstance (bans ,dict )else [],
        'kicks':list (kicks .values ())if isinstance (kicks ,dict )else [],
        'scheduled':scheduled ,
        })


    @app .route ('/api/temp-mod/mute',methods =['POST'])
    @login_required 
    @role_required ('mod')
    def api_temp_mod_mute ():
        import web .app as _app ;bot =_app .bot_instance 
        from cogs .temp_moderation import TempModeration ,parse_duration 
        if not bot :
            return jsonify ({'error':'Бот офлайн'}),503 
        cog =bot .get_cog ('TempModeration')
        if not cog :
            return jsonify ({'error':'Модуль не загружен'}),404 
        d =request .get_json (silent =True )or {}
        sec =parse_duration (d .get ('duration','1h'))
        if not sec :
            return jsonify ({'error':'Неверный формат времени'}),400 
        guild =bot .get_guild (int (session .get ('selected_guild')or MAIN_GUILD_ID ))
        _acl_m = viewer_member(bot, guild.id if guild else None)
        if not acl_action_allowed(guild.id if guild else 0, _acl_m, 'mute'):
            return jsonify({'error': 'Нет права: «Мут» не разрешено вашей роли (настройка — «Права команд»)'}), 403
        if not guild :
            return jsonify ({'error':'Сервер не найден'}),404 
            # Resolve user
        user_id =d .get ('user_id','').strip ('<@!>')
        try :
            member =_run_async (_resolve_member_async (guild ,int (user_id )))
        except Exception :
            return jsonify ({'error':'Пользователь не найден'}),404 
        if not member :
            return jsonify ({'error':'Пользователь не найден'}),404 
        from datetime import datetime ,timedelta 
        until =datetime.now(timezone.utc).replace(tzinfo=None)+timedelta (seconds =sec )
        try :
            _run_async (member .timeout (until ,reason =f"[Panel] {session.get('username')}: {d.get('reason', '')}"))
        except Exception as e :
            return jsonify ({'error':str (e )}),400 
        cog ._mutes .setdefault (str (guild .id ),{})[str (member .id )]={
        'until':time .time ()+sec ,'reason':d .get ('reason',''),
        'mod_id':session .get ('username',''),'created_at':time .time (),'duration':sec ,
        }
        cog ._save ('_mutes',cog ._mutes_file ())
        _live_publish (str (session .get ('selected_guild')or MAIN_GUILD_ID ),'moderation')
        return jsonify ({'ok':True })


    @app .route ('/api/temp-mod/ban',methods =['POST'])
    @login_required 
    @role_required ('mod')
    def api_temp_mod_ban ():
        import web .app as _app ;bot =_app .bot_instance 
        from cogs .temp_moderation import TempModeration ,parse_duration 
        if not bot :
            return jsonify ({'error':'Бот офлайн'}),503 
        cog =bot .get_cog ('TempModeration')
        if not cog :
            return jsonify ({'error':'Модуль не загружен'}),404 
        d =request .get_json (silent =True )or {}
        sec =parse_duration (d .get ('duration','1d'))
        if not sec :
            return jsonify ({'error':'Неверный формат'}),400 
        guild =bot .get_guild (int (session .get ('selected_guild')or MAIN_GUILD_ID ))
        _acl_m = viewer_member(bot, guild.id if guild else None)
        if not acl_action_allowed(guild.id if guild else 0, _acl_m, 'ban'):
            return jsonify({'error': 'Нет права: «Бан» не разрешено вашей роли (настройка — «Права команд»)'}), 403
        user_id =d .get ('user_id','').strip ('<@!>')
        try :
            member =_run_async (_resolve_member_async (guild ,int (user_id )))
        except Exception :
            return jsonify ({'error':'Пользователь не найден'}),404 
        if not member :
            return jsonify ({'error':'Пользователь не найден'}),404 
        try :
            _run_async (guild .ban (member ,reason =f"[Panel] {session.get('username')}: {d.get('reason', '')}"))
        except Exception as e :
            return jsonify ({'error':str (e )}),400 
        cog ._bans .setdefault (str (guild .id ),{})[str (member .id )]={
        'until':time .time ()+sec ,'reason':d .get ('reason',''),
        'mod_id':session .get ('username',''),'created_at':time .time (),'duration':sec ,
        'user_name':str (member ),
        }
        cog ._save ('_bans',cog ._bans_file ())
        _live_publish (str (session .get ('selected_guild')or MAIN_GUILD_ID ),'moderation')
        return jsonify ({'ok':True })


    @app .route ('/api/temp-mod/kick',methods =['POST'])
    @login_required 
    @role_required ('mod')
    def api_temp_mod_kick ():
        import web .app as _app ;bot =_app .bot_instance 
        from cogs .temp_moderation import TempModeration ,parse_duration 
        if not bot :
            return jsonify ({'error':'Бот офлайн'}),503 
        cog =bot .get_cog ('TempModeration')
        if not cog :
            return jsonify ({'error':'Модуль не загружен'}),404 
        d =request .get_json (silent =True )or {}
        sec =parse_duration (d .get ('duration','5m'))
        if not sec :
            return jsonify ({'error':'Неверный формат'}),400 
        guild =bot .get_guild (int (session .get ('selected_guild')or MAIN_GUILD_ID ))
        _acl_m = viewer_member(bot, guild.id if guild else None)
        if not acl_action_allowed(guild.id if guild else 0, _acl_m, 'kick'):
            return jsonify({'error': 'Нет права: «Кик» не разрешено вашей роли (настройка — «Права команд»)'}), 403
        user_id =d .get ('user_id','').strip ('<@!>')
        try :
            member =_run_async (_resolve_member_async (guild ,int (user_id )))
        except Exception :
            return jsonify ({'error':'Пользователь не найден'}),404 
        if not member :
            return jsonify ({'error':'Пользователь не найден'}),404 
        try :
            _run_async (member .kick (reason =f"[Panel] {session.get('username')}: {d.get('reason', '')}"))
        except Exception as e :
            return jsonify ({'error':str (e )}),400 
        cog ._kicks .setdefault (str (guild .id ),{})[str (member .id )]={
        'until':time .time ()+sec ,'reason':d .get ('reason',''),
        'mod_id':session .get ('username',''),'created_at':time .time (),'duration':sec ,
        'user_name':str (member ),
        }
        cog ._save ('_kicks',cog ._kicks_file ())
        _live_publish (str (session .get ('selected_guild')or MAIN_GUILD_ID ),'moderation')
        return jsonify ({'ok':True })


    @app .route ('/api/temp-mod/unmute',methods =['POST'])
    @login_required 
    @role_required ('mod')
    def api_temp_mod_unmute ():
        import web .app as _app ;bot =_app .bot_instance 
        if not bot :
            return jsonify ({'error':'Бот офлайн'}),503 
        from cogs .temp_moderation import TempModeration 
        cog =bot .get_cog ('TempModeration')
        if not cog :
            return jsonify ({'error':'Модуль не загружен'}),404 
        d =request .get_json (silent =True )or {}
        user_id =d .get ('user_id','').strip ('<@!>')
        guild =bot .get_guild (int (session .get ('selected_guild')or MAIN_GUILD_ID ))
        _acl_m = viewer_member(bot, guild.id if guild else None)
        if not acl_action_allowed(guild.id if guild else 0, _acl_m, 'mute'):
            return jsonify({'error': 'Нет права: «Мут» не разрешено вашей роли (настройка — «Права команд»)'}), 403
        member =guild .get_member (int (user_id ))
        if member and member .is_timed_out ():
            try :
                _run_async (member .timeout (None ))
            except Exception as _ex:
                _log.debug("api_temp_mod_unmute(): подавлено: %s", _ex)
        cog ._mutes .get (str (guild .id ),{}).pop (user_id ,None )
        cog ._save ('_mutes',cog ._mutes_file ())
        _live_publish (str (guild .id ),'moderation')
        return jsonify ({'ok':True })


    @app .route ('/api/temp-mod/unban',methods =['POST'])
    @login_required 
    @role_required ('mod')
    def api_temp_mod_unban ():
        import web .app as _app ;bot =_app .bot_instance 
        if not bot :
            return jsonify ({'error':'Бот офлайн'}),503 
        from cogs .temp_moderation import TempModeration 
        cog =bot .get_cog ('TempModeration')
        if not cog :
            return jsonify ({'error':'Модуль не загружен'}),404 
        d =request .get_json (silent =True )or {}
        user_id =d .get ('user_id','').strip ('<@!>')
        guild =bot .get_guild (int (session .get ('selected_guild')or MAIN_GUILD_ID ))
        _acl_m = viewer_member(bot, guild.id if guild else None)
        if not acl_action_allowed(guild.id if guild else 0, _acl_m, 'ban'):
            return jsonify({'error': 'Нет права: «Бан» не разрешено вашей роли (настройка — «Права команд»)'}), 403
        try :
            user =_run_async (bot .fetch_user (int (user_id )))
            _run_async (guild .unban (user ))
        except Exception as e :
            return jsonify ({'error':str (e )}),400 
        cog ._bans .get (str (guild .id ),{}).pop (user_id ,None )
        cog ._save ('_bans',cog ._bans_file ())
        _live_publish (str (session .get ('selected_guild')or MAIN_GUILD_ID ),'moderation')
        return jsonify ({'ok':True })


    @app .route ('/api/temp-mod/unschedule',methods =['POST'])
    @login_required 
    @role_required ('mod')
    def api_temp_mod_unschedule ():
        import web .app as _app ;bot =_app .bot_instance 
        if not bot :
            return jsonify ({'error':'Бот офлайн'}),503 
        from cogs .temp_moderation import TempModeration 
        cog =bot .get_cog ('TempModeration')
        if not cog :
            return jsonify ({'error':'Модуль не загружен'}),404 
        d =request .get_json (silent =True )or {}
        eid =d .get ('id','')
        cog ._scheduled =[s for s in cog ._scheduled if s ['id']!=eid ]
        cog ._save ('_scheduled',cog ._scheduled_file ())
        _live_publish (str (session .get ('selected_guild')or MAIN_GUILD_ID ),'moderation')
        return jsonify ({'ok':True })


        # ── API ROUTES ────────────────────────────────────────────────────────────

        # ── НОВЫЕ API ENDPOINT'Ы ────────────────────────────────────────────────

    @app .route ('/api/bot/status',methods =['POST'])
    @login_required 
    @role_required ('owner')
    def api_bot_status ():
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio 
        if not bot :return jsonify ({'error':'Бот офлайн'}),503 
        d =request .get_json (silent =True )or {}
        status_map ={'online':discord .Status .online ,'idle':discord .Status .idle ,'dnd':discord .Status .dnd ,'invisible':discord .Status .invisible }
        type_map ={'listening':discord .ActivityType .listening ,'playing':discord .ActivityType .playing ,'watching':discord .ActivityType .watching ,'competing':discord .ActivityType .competing }
        status =status_map .get (d .get ('status','online'),discord .Status .online )
        atype =type_map .get (d .get ('activity_type','watching'),discord .ActivityType .watching )
        atext =str (d .get ('activity_text','Hakumo')or '').strip ()[:80]or 'Hakumo'
        def _set ():
            _run_async (bot .change_presence (status =status ,activity =discord .Activity (type =atype ,name =atext )))
        asyncio .run_coroutine_threadsafe (_set (),bot .loop ).result (timeout =5 )
        # Сохраняем в конфиг — бот вспомнит это и после перезапуска
        os .makedirs ('data',exist_ok =True )
        cfg ={}
        cfg_file ='data/bot_config.json'
        if os .path .exists (cfg_file ):
            try :
                with open (cfg_file ,encoding ='utf-8')as f :cfg =json .load (f )
            except Exception as _ex:
                _log.debug("api_bot_status(): подавлено: %s", _ex)
        cfg ['status']=d .get ('status','online')
        cfg ['activity_type']=d .get ('activity_type','listening')
        cfg ['activity_text']=atext 
        with open (cfg_file ,'w',encoding ='utf-8')as f :
            json .dump (cfg ,f ,indent =2 ,ensure_ascii =False )
        return jsonify ({'ok':True })


    @app .route ('/api/bot/prefix',methods =['POST'])
    @login_required 
    @role_required ('owner')
    def api_bot_prefix ():
        d =request .get_json (silent =True )or {}
        prefix =d .get ('prefix','!').strip ()
        if not prefix :return jsonify ({'error':'Пустой префикс'}),400 
        if len (prefix )>10 :return jsonify ({'error':'префикс слишком длинный'}),400 
        os .makedirs ('data',exist_ok =True )
        cfg_file ='data/bot_config.json'
        cfg ={}
        if os .path .exists (cfg_file ):
            try :
                with open (cfg_file ,'r',encoding ='utf-8')as f :
                    cfg =json .load (f )or {}
            except Exception as _ex:
                _log.debug("api_bot_prefix(): подавлено: %s", _ex)
        if not isinstance (cfg ,dict ):
            cfg ={}
            # Сохраняем текущие поля status/activity
        cfg ['prefix']=prefix 
        with open (cfg_file ,'w',encoding ='utf-8')as f :
            json .dump (cfg ,f ,indent =2 ,ensure_ascii =False )
        return jsonify ({'ok':True })


    @app .route ('/api/cogs/load',methods =['POST'])
    @login_required 
    @role_required ('owner')
    def api_cog_load ():
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio 
        d =request .get_json (silent =True )or {}
        name =(d .get ('name')or d .get ('cog')or '').strip ()
        if not bot :
            if _app ._demo_mode ()and name :
                from services .demo_cogs import set_loaded 
                set_loaded (name .replace ('cogs.','',1 ),True )
                return jsonify ({'ok':True ,'demo':True ,'name':name })
            return jsonify ({'error':'Бот офлайн'}),503 
        if not name :
            return jsonify ({'error':'Не указано имя расширения (name/cog)'}),400 
            # Accept both "cogs.foo" and "foo" forms
        if not name .startswith ('cogs.'):
            name ='cogs.'+name 
            # Idempotent: already loaded?
        if name in (getattr (bot ,'extensions',None )or {}): 
            return jsonify ({'ok':True ,'already_loaded':True ,'name':name })
        try :
            future =asyncio .run_coroutine_threadsafe (bot .load_extension (name ),bot .loop )
            future .result (timeout =10 )
            try :
                from slash_budget import apply_slash_budget
                apply_slash_budget (bot .tree )
            except Exception as _ex :
                _log .debug ('api_bot_load(): apply_slash_budget: %s',_ex )
            return jsonify ({'ok':True ,'name':name })
        except ModuleNotFoundError as e :
            return jsonify ({'error':f'Файл не найден: {e}'}),404 
        except Exception as e :
            err =str (e )or type (e ).__name__ 
            # Friendly translation for common cases
            if 'already loaded'in err .lower ():
                return jsonify ({'ok':True ,'already_loaded':True ,'name':name })
            return jsonify ({'error':f'Не удалось загрузить {name}: {err}'}),400 


    @app .route ('/api/cogs/unload',methods =['POST'])
    @login_required 
    @role_required ('owner')
    def api_cog_unload ():
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio 
        d =request .get_json (silent =True )or {}
        name =(d .get ('name')or d .get ('cog')or '').strip ()
        if not bot :
            if _app ._demo_mode ()and name :
                from services .demo_cogs import set_loaded 
                set_loaded (name .replace ('cogs.','',1 ),False )
                return jsonify ({'ok':True ,'demo':True ,'name':name })
            return jsonify ({'error':'Бот офлайн'}),503 
        if not name :
            return jsonify ({'error':'Не указано имя расширения'}),400 
        if not name .startswith ('cogs.'):
            name ='cogs.'+name 
        if name not in (getattr (bot ,'extensions',None )or {}): 
            return jsonify ({'ok':True ,'not_loaded':True ,'name':name })
        try :
            future =asyncio .run_coroutine_threadsafe (bot .unload_extension (name ),bot .loop )
            future .result (timeout =10 )
            return jsonify ({'ok':True ,'name':name })
        except Exception as e :
            return jsonify ({'error':f'Не удалось выгрузить {name}: {e}'}),400 


    @app .route ('/api/cogs/reload',methods =['POST'])
    @login_required 
    @role_required ('owner')
    def api_cog_reload ():
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio 
        d =request .get_json (silent =True )or {}
        name =(d .get ('name')or d .get ('cog')or '').strip ()
        if not bot :
            if _app ._demo_mode ()and name :
                from services .demo_cogs import set_loaded 
                set_loaded (name .replace ('cogs.','',1 ),True )
                return jsonify ({'ok':True ,'demo':True ,'name':name })
            return jsonify ({'error':'Бот офлайн'}),503 
        if not name :
            return jsonify ({'error':'Не указано имя расширения'}),400 
        if not name .startswith ('cogs.'):
            name ='cogs.'+name 
        try :
            future =asyncio .run_coroutine_threadsafe (bot .reload_extension (name ),bot .loop )
            future .result (timeout =10 )
            try :
                from slash_budget import apply_slash_budget
                apply_slash_budget (bot .tree )
            except Exception as _ex :
                _log .debug ('api_bot_reload(): apply_slash_budget: %s',_ex )
            return jsonify ({'ok':True ,'name':name })
        except Exception as e :
            return jsonify ({'error':f'Не удалось перезагрузить {name}: {e}'}),400 


    @app .route ('/api/cogs/reload-all',methods =['POST'])
    @login_required 
    @role_required ('owner')
    def api_cog_reload_all ():
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio 
        if not bot :
            if _app ._demo_mode ():
                from services .demo_cogs import save_states 
                save_states ({})           # «обновить всё» = вернуть всё во включённое
                return jsonify ({'ok':True ,'demo':True ,'results':[]})
            return jsonify ({'error':'Бот офлайн'}),503 
        results =[]
        for ext in list ((getattr (bot ,'extensions',None )or {}).keys ()):
            try :
                asyncio .run_coroutine_threadsafe (bot .reload_extension (ext ),bot .loop ).result (timeout =10 )
                results .append ({'name':ext ,'ok':True })
            except Exception as e :
                results .append ({'name':ext ,'ok':False ,'error':str (e )})
        try :
            from slash_budget import apply_slash_budget
            apply_slash_budget (bot .tree )
        except Exception as _ex :
            _log .debug ('api_bot_reload_all(): apply_slash_budget: %s',_ex )
        return jsonify ({'ok':True ,'results':results })
