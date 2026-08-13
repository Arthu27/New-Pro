# -*- coding: utf-8 -*-
"""Админка гильдии: роли, каналы, инфо, мод-история (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

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


    @app .route ('/api/guild/<guild_id>/info')
    @login_required 
    def api_guild_info (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        if not bot :
            return jsonify ({'error':'Бот офлайн'})
        guild =bot .get_guild (int (guild_id ))
        if not guild :
            return jsonify ({'error':'Сервер не найден'})
        return jsonify ({
        'id':str (guild .id ),
        'name':guild .name ,
        'description':guild .description or '',
        'icon':str (guild .icon .url )if guild .icon else None ,
        'icon_url':str (guild .icon .url )if guild .icon else None ,
        'banner':str (guild .banner .url )if guild .banner else None ,
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


    @app .route ('/api/bot-stats')
    @login_required 
    def api_bot_stats ():
        import time 
        import web .app as _app ;bot =_app .bot_instance 
        if not bot :
            return jsonify ({'error':'Бот офлайн'})
        try :
            try :
                import psutil 
                proc =psutil .Process ()
                cpu =psutil .cpu_percent (interval =0.1 )
                ram =round (proc .memory_info ().rss /1024 /1024 ,1 )
                uptime_sec =int (time .time ()-proc .create_time ())
            except Exception :
                cpu =0 
                ram =0 
                uptime_sec =0 
            h =uptime_sec //3600 
            m =(uptime_sec %3600 )//60 
            uptime =f"{h} ч {m} мин"
            history_file ='data/sys_history.json'
            os .makedirs ('data',exist_ok =True )
            history =[]
            if os .path .exists (history_file ):
                try :
                    with open (history_file )as f :
                        history =json .load (f )
                except Exception :
                    history =[]
            now =datetime.now(timezone.utc).replace(tzinfo=None).strftime ('%H:%M')
            history .append ({'time':now ,'cpu':cpu ,'ram':ram })
            history =history [-20 :]
            try :
                with open (history_file ,'w')as f :
                    json .dump (history ,f )
            except Exception as _ex:
                _log.debug("api_bot_stats(): подавлено: %s", _ex)
            lat_val = 0
            if bot and bot.latency is not None:
                try:
                    if math.isfinite(bot.latency):
                        lat_val = round(bot.latency * 1000)
                except Exception:
                    lat_val = 0
            return jsonify ({
            'guilds':len (bot .guilds ) if bot else 0,
            'users':sum (g .member_count for g in bot .guilds ) if bot else 0,
            'latency':lat_val ,
            'uptime':uptime ,
            'cpu':cpu ,
            'ram':ram ,
            'history':history ,
            'guild_list':[{'name':g .name ,'members':g .member_count }for g in bot .guilds ] if bot else []
            })
        except Exception as e :
            return jsonify ({'error':str (e ),'guilds':len (bot .guilds )if bot else 0 ,'history':[]}),200


    @app .route ('/api/mod-history')
    @login_required 
    @role_required ('mod')
    def api_mod_history ():
        import web .app as _app ;bot =_app .bot_instance 
        guild_id =request .args .get ('guild_id')
        all_events =[]

        # ── 1. mod_data.json — bot'un сохран case'ler ────────────────────
        mod_file ='data/mod_data.json'
        if os .path .exists (mod_file ):
            try :
                with open (mod_file ,'r',encoding ='utf-8')as fp :
                    md =json .load (fp )
                case =md .get ('case',{})
                for gid ,case_list in case .items ():
                    if guild_id and gid !=guild_id :
                        continue 
                    if not isinstance (case_list ,list ):
                        continue 
                    for case in case_list :
                        uid =str (case .get ('user_id',''))
                        mid =str (case .get ('mod_id',''))
                        all_events .append ({
                        'guild_id':gid ,
                        'category':'mod',
                        'action':case .get ('action','warn'),
                        'target_name':uid ,
                        'target_id':uid ,
                        'mod_name':mid ,
                        'reason':case .get ('reason','Belirtilmedi'),
                        'created_at':case .get ('timestamp',''),
                        'source':'bot',
                        })
            except Exception as _e :
                print (f'[MOD-HISTORY] Ошибка данных модерации: {_e}')

                # ── 2. Discord Audit Cache ────────────────────────────────────────────
        cache_file ='data/discord_audit_cache.json'
        if os .path .exists (cache_file ):
            try :
                with open (cache_file ,'r',encoding ='utf-8')as fp :
                    cache =json .load (fp )
                mod_cats ={'Бан','Бан снят','Кик','Мут','Мут снят',
                'ban','kick','timeout','unban','warn','mute'}
                for gid ,events in cache .items ():
                    if guild_id and gid !=guild_id :
                        continue 
                    for ev in events :
                        if ev .get ('action')in mod_cats :
                            ev ['guild_id']=gid 
                            ev ['created_at']=ev .get ('timestamp','')
                            all_events .append (ev )
            except Exception as _e :
                print (f'[MOD-HISTORY] Cache okuma Ошибки: {_e}')

                # ── 3. warnings.json ─────────────────────────────────────────────────
        warns_file ='data/warnings.json'
        if os .path .exists (warns_file ):
            try :
                with open (warns_file ,'r',encoding ='utf-8')as fp :
                    data =json .load (fp )
                for gid ,guild_warns in data .items ():
                    if guild_id and gid !=guild_id :
                        continue 
                    for uid ,warns in guild_warns .items ():
                        if not isinstance (warns ,list ):
                            continue 
                        name =uid 
                        if bot :
                            for g in bot .guilds :
                                m =g .get_member (int (uid ))if uid .isdigit ()else None 
                                if m :
                                    name =m .display_name 
                                    break 
                        for w in warns :
                            all_events .append ({
                            'guild_id':gid ,
                            'category':'mod',
                            'action':'warn',
                            'target_name':name ,
                            'target_id':uid ,
                            'mod_name':w .get ('mod',w .get ('moderator','?')),
                            'reason':w .get ('reason',''),
                            'created_at':w .get ('timestamp',''),
                            'source':'bot',
                            })
            except Exception as _e :
                print (f'[MOD-HISTORY] Ошибка чтения предупреждений: {_e}')

        all_events .sort (key =lambda x :x .get ('created_at',''),reverse =True )
        return jsonify (all_events [:500 ])


    @app .route ('/api/roles')
    @login_required 
    def api_roles_default ():
        if not MAIN_GUILD_ID :
            return jsonify ({'error':'Сервер не выбран (задайте MAIN_GUILD_ID в .env)'}),503 
        return api_guild_roles (str (MAIN_GUILD_ID ))


    @app .route ('/api/channels')
    @login_required 
    def api_channels_default ():
        if not MAIN_GUILD_ID :
            return jsonify ({'error':'Сервер не выбран (задайте MAIN_GUILD_ID в .env)'}),503 
        return api_guild_channels (str (MAIN_GUILD_ID ))


    @app .route ('/api/members')
    @login_required 
    def api_members_default ():
        if not MAIN_GUILD_ID :
            return jsonify ({'error':'Сервер не выбран (задайте MAIN_GUILD_ID в .env)'}),503 
        from web .app import api_guild_members 
        return api_guild_members (str (MAIN_GUILD_ID ))


    @app .route ('/api/guild/<guild_id>/roles')
    @login_required 
    def api_guild_roles (guild_id ):
        import web .app as _app 
        bot =_app .bot_instance 
        if not bot :return jsonify ([])
        guild =bot .get_guild (int (guild_id ))
        if not guild :return jsonify ([])
        roles =[{'id':str (r .id ),'name':r .name ,'color':str (r .color ),'members':len (r .members )}
        for r in guild .roles if r .name !='@everyone']
        return jsonify (sorted (roles ,key =lambda x :-x ['members']))


    @app .route ('/api/guild/<guild_id>/roles/create',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_create_role (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio ,discord 
        if not bot :return jsonify ({'error':'Бот офлайн'}),503 
        data =request .get_json (silent =True )or {}
        name =(data .get ('name')or '').strip ()
        if not name :
            return jsonify ({'error':'Требуется название роли'}),400 
            # Проверка: один из серверов, где состоит бот
        try :
            gid =int (guild_id )
        except (TypeError ,ValueError ):
            return jsonify ({'error':'Неверный ID сервера'}),400 
        guild =bot .get_guild (gid )if bot else None 
        if guild is None and bot is not None :
        # Запасной вариант: сравнение ID строкой
            for g in bot .guilds :
                if str (g .id )==str (guild_id ):
                    guild =g 
                    break 
        if guild is None :
            return jsonify ({'error':f'Бот не состоит на этом сервере (id={guild_id})'}),404 
        async def do ():
            color_hex =(data .get ('color')or '#dc143c').lstrip ('#')or 'dc143c'
            try :
                color =discord .Color (int (color_hex ,16 ))
            except ValueError :
                color =discord .Color .default ()
            await (guild .create_role (name =name ,color =color ,reason ='Создано через панель Aether'))
        try :
            asyncio .run_coroutine_threadsafe (do (),bot .loop ).result (timeout =10 )
            return jsonify ({'success':True })
        except discord .Forbidden :
            return jsonify ({'error':'У меня нет прав создавать роли на этом сервере'}),403 
        except discord .HTTPException as e :
            return jsonify ({'error':f'Ошибка Discord: {e}'}),500 
        except Exception as e :
            return jsonify ({'error':str (e )}),500 


    @app .route ('/api/guild/<guild_id>/roles/<role_id>/delete',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_delete_role (guild_id ,role_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio 
        if not bot :return jsonify ({'error':'Бот офлайн'})
        async def do ():
            guild =bot .get_guild (int (guild_id ))
            role =guild .get_role (int (role_id ))
            if role :await (role .delete ())
        asyncio .run_coroutine_threadsafe (do (),bot .loop ).result (timeout =10 )
        return jsonify ({'success':True })


    @app .route ('/api/guild/<guild_id>/channels')
    @login_required 
    def api_guild_channels (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import discord as _discord 
        if not bot :
            print ('[WEB][WARN] /channels: bot is None')
            return jsonify ({'error':'Бот офлайн','channels':[]})

        guild =bot .get_guild (int (guild_id ))
        if not guild :
            for g in bot .guilds :
                if str (g .id )==str (guild_id ):
                    guild =g 
                    break 
        if not guild :
            print (f'[WEB][WARN] /channels: guild {guild_id} заметок found. Bot guilds: {[str(g.id) for g in bot.guilds]}')
            return jsonify ({'error':f'Guild {guild_id} заметок found','channels':[]})

        type_map ={
        _discord .ChannelType .text :'text',
        _discord .ChannelType .voice :'voice',
        _discord .ChannelType .category :'category',
        _discord .ChannelType .news :'text',
        _discord .ChannelType .stage_voice :'voice',
        _discord .ChannelType .forum :'text',
        }

        channels_data =[]
        try :
            for c in guild .channels :
                ch_type =type_map .get (c .type ,str (c .type ).split ('.')[-1 ])
                # Подробная информация о канале — для детального отображения в панели
                topic =''
                nsfw =False
                slowmode =0
                bitrate =0
                user_limit =0
                news =False
                stage =False
                forum =False
                connected =0
                if hasattr (c ,'topic'):
                    topic =c .topic or ''
                if hasattr (c ,'nsfw'):
                    nsfw =bool (c .nsfw )
                if hasattr (c ,'slowmode_delay'):
                    slowmode =int (c .slowmode_delay or 0 )
                if hasattr (c ,'bitrate'):
                    bitrate =int ((c .bitrate or 0 )// 1000 )
                if hasattr (c ,'user_limit'):
                    user_limit =int (c .user_limit or 0 )
                if hasattr (c ,'type'):
                    if c .type ==discord .ChannelType .news :
                        news =True 
                    if c .type ==discord .ChannelType .stage_voice :
                        stage =True 
                    if c .type ==discord .ChannelType .forum :
                        forum =True 
                if hasattr (c ,'members'):
                    try :
                        connected =len ([m for m in c .members if not getattr (m ,'bot',False )])
                    except Exception :
                        connected =0 
                channels_data .append ({
                'id':str (c .id ),
                'name':c .name ,
                'type':ch_type ,
                'position':getattr (c ,'position',0 ),
                'category':c .category .name if hasattr (c ,'category')and c .category else None ,
                'category_id':str (c .category .id ) if hasattr (c ,'category')and c .category else None ,
                'category_pos':c .category .position if hasattr (c ,'category')and c .category else -1 ,
                'topic':topic ,
                'nsfw':nsfw ,
                'slowmode':slowmode ,
                'bitrate':bitrate ,
                'user_limit':user_limit ,
                'news':news ,
                'stage':stage ,
                'forum':forum ,
                'connected':connected ,
                'created_at':c .created_at .isoformat () if getattr (c ,'created_at',None )else None ,
                'mention':getattr (c ,'mention','')
                })
        except Exception as e :
            print (f'[WEB][ERR] channels error: {e}')
            return jsonify ({'error':str (e ),'channels':[]})

        sorted_channels =sorted (channels_data ,key =lambda x :(x ['category_pos'],x ['position']))
        print (f'[WEB] /channels guild={guild_id} returned {len(sorted_channels)} channels')
        return jsonify (sorted_channels )
