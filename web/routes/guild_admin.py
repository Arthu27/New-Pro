# -*- coding: utf-8 -*-
"""Админка гильдии: роли, каналы, инфо, мод-история (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

from web.routes._common import (
    _run_async, _fetch_channel_msgs_async, _fetch_channel_msgs_sync,
    _load_ai_tickets, _notify_discord_sender, _fire_panel_notification,
    _process_action, _log,
    ms_normalize_query, ms_member_match, ms_search_members, ms_member_payload,
    ms_normalize_warn, ms_normalize_case, calculate_ai_ticket_stats, _REPO_ROOT,
    render_template, session, redirect, url_for, request, jsonify, Response,
    os, json, time, math, discord, datetime, timezone, timedelta,
)

def _hidden_store ():
    path =os .path .join (_REPO_ROOT ,'data','hidden_channels.json')
    try :
        with open (path ,'r',encoding ='utf-8')as fp :
            return json .load (fp )
    except Exception :
        return {}


def _demo_roles_file (guild_id ):
    return f'data/demo_roles_{guild_id}.json'

def _demo_roles_seed ():
    """Типичный набор ролей сервера — страница ролей в превью живая."""
    return [
        {'id':'9001','name':'Владелец','color':'#e11d48','members':3},
        {'id':'9002','name':'Администратор','color':'#f43f5e','members':9},
        {'id':'9003','name':'Модератор','color':'#4f46e5','members':14},
        {'id':'9004','name':'Хелпер','color':'#22d3ee','members':11},
        {'id':'9005','name':'Чат-контроль','color':'#7c3aed','members':7},
        {'id':'9006','name':'Ивент-мастер','color':'#a78bfa','members':6},
        {'id':'9007','name':'Дизайнер','color':'#f59e0b','members':5},
        {'id':'9008','name':'Бустер','color':'#ec4899','members':38},
        {'id':'9009','name':'Ветеран','color':'#16a34a','members':64},
        {'id':'9010','name':'Актив','color':'#0ea5e9','members':97},
        {'id':'9011','name':'Музыкант','color':'#fb7185','members':12},
        {'id':'9012','name':'Новичок','color':'#64748b','members':214},
    ]

def _demo_roles_load (guild_id ):
    f =_demo_roles_file (guild_id )
    if os .path .exists (f ):
        try :
            with open (f ,'r',encoding ='utf-8')as fp :
                roles =json .load (fp )
            if isinstance (roles ,list ):
                return roles
        except Exception as _ex :
            _log.debug("_demo_roles_load(): подавлено: %s", _ex)
    roles =_demo_roles_seed ()
    _demo_roles_store (guild_id ,roles )
    return roles

def _demo_roles_store (guild_id ,roles ):
    try :
        with open (_demo_roles_file (guild_id ),'w',encoding ='utf-8')as fp :
            json .dump (roles ,fp ,ensure_ascii =False ,indent =2 )
    except Exception as _ex :
        _log.debug("_demo_roles_store(): подавлено: %s", _ex)


def _hidden_save (store ):
    path =os .path .join (_REPO_ROOT ,'data','hidden_channels.json')
    with open (path ,'w',encoding ='utf-8')as fp :
        json .dump (store ,fp ,ensure_ascii =False ,indent =2 )


def _annotate_hidden (guild_id ,channels ):
    """Пометить каналы/категории флагом hidden (сам канал или его категория скрыты владельцем)."""
    store =_hidden_store ().get (str (guild_id ),{})
    hch =set (str (x )for x in store .get ('channels',[]))
    hcat =set (str (x )for x in store .get ('categories',[]))
    for ch in channels :
        ch ['hidden']=(str (ch .get ('id',''))in hch )or (str (ch .get ('category_id')or '')in hcat )
    return channels


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
            # демо: типичные показатели процесса (страница живая в превью)
            if _app ._demo_mode ():
                h_ =int (time .time ())// 3600
                return jsonify ({
                'guilds':1 ,
                'users':1247 ,
                'latency':round (10 + (int (time .time ()*10 )% 30 ),1 ),
                'uptime':f"{h_ % 48 } ч {int (time .time ()*7 )% 60 } мин",
                'cpu':round (6 + (int (time .time ()*5 )% 24 ),1 ),
                'ram':round (240 + (int (time .time ()*3 )% 90 ),1 ),
                'ram_percent':round (38 + (int (time .time ()*9 )% 18 ),1 ),
                'history':[{'time':f"{ (12 + i )% 24 }:00" if False else f"{ (12 + (i *7 )% 12 )% 24 }:{ (i *13 )% 60 :02d}",'cpu':round (8 + ((i *5 )% 20 ),1 ),'ram':round (250 + ((i *7 )% 80 ),1 )}for i in range (12 )],
                'guild_list':[{'name':'Главный сервер','members':1247 }]
                })
            return jsonify ({'error':'Бот офлайн'})
        try :
            try :
                import psutil 
                proc =psutil .Process ()
                cpu =psutil .cpu_percent (interval =0.1 )
                ram =round (proc .memory_info ().rss /1024 /1024 ,1 )
                try :
                    ram_percent =round (psutil .virtual_memory ().percent ,1 )
                except Exception :
                    ram_percent =0 
                uptime_sec =int (time .time ()-proc .create_time ())
            except Exception :
                cpu =0 
                ram =0 
                ram_percent =0 
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
            'ram_percent':ram_percent ,
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


    @app .route ('/api/mod-stats')
    @login_required 
    @role_required ('mod')
    def api_mod_stats ():
        """Профи-статистика модераторов: действия (неделя/всего), сроки наказаний,
        сообщения и голосовые часы за неделю. Источники те же, что у /api/mod-history,
        плюс счётчик сообщений и голосовой трекер."""
        gid =request .args .get ('guild_id')or str (active_guild_id ()or MAIN_GUILD_ID or '')
        now =datetime .now (timezone .utc )
        week_start =now -timedelta (days =6 )

        def _ts (v ):
            try :
                dt =datetime .fromisoformat (str (v or '').replace ('Z','+00:00'))
            except Exception :
                return None 
            if dt .tzinfo is None :
                dt =dt .replace (tzinfo =timezone .utc )
            return dt .astimezone (timezone .utc )

        def _dur_min (v ):
            """Длительность наказания → минуты: int-минуты, '2h', '1d', '1d6h', '45m', '60'."""
            import re as _re 
            if v is None :return 0 
            if isinstance (v ,bool ):return 0 
            if isinstance (v ,(int ,float )):return max (0 ,int (v ))
            sv =str (v ).strip ()
            if sv .isdigit ():return max (0 ,int (sv ))
            mm =_re .match (r'^(?:(\d+)\s*d)?\s*(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?$',sv ,_re .I )
            if not mm or not any (mm .groups ()):return 0 
            d ,h ,mi =(int (x or 0 )for x in mm .groups ())
            return d *1440 +h *60 +mi 

        rows ={}
        def bump (mod_ref ,action ,ts ,dur =0 ):
            key =str (mod_ref or '').strip ()
            if not key :return 
            row =rows .setdefault (key ,{
            'mod':key ,'warns':0 ,'mutes':0 ,'kicks':0 ,'bans':0 ,'other':0 ,
            'total':0 ,'week':0 ,'duration_min':0 ,'duration_week_min':0 })
            act =str (action or '').lower ()
            dt =_ts (ts )
            in_week =dt is not None and dt >=week_start 
            row ['total']+=1 
            if in_week :row ['week']+=1 
            if act in ('warn','warning','предупреждение','варн'):row ['warns']+=1 
            elif act in ('mute','timeout','мут','таймаут'):row ['mutes']+=1 ;row ['duration_min']+=dur ;row ['duration_week_min']+=dur if in_week else 0 
            elif act in ('kick','кик'):row ['kicks']+=1 
            elif act in ('ban','бан'):row ['bans']+=1 
            else :row ['other']+=1 

        # 1. mod_data.json (кейсы бота, могут нести длительность)
        mod_file ='data/mod_data.json'
        if os .path .exists (mod_file ):
            try :
                with open (mod_file ,'r',encoding ='utf-8')as fp :md =json .load (fp )
                cases =md .get ('case',{})if isinstance (md ,dict )else {}
                for cgid ,case_list in cases .items ():
                    if gid and str (cgid )!=str (gid ):continue 
                    if not isinstance (case_list ,list ):continue 
                    for c in case_list :
                        if not isinstance (c ,dict ):continue 
                        bump (c .get ('mod_id')or c .get ('moderator'),c .get ('action','warn'),
                        c .get ('timestamp',''),_dur_min (c .get ('duration_minutes')if 'duration_minutes'in c else c .get ('duration')))
            except Exception as _ex :
                print (f'[MOD-STATS] Ошибка mod_data: {_ex }')
        # 2. audit_log.json
        af ='data/audit_log.json'
        if os .path .exists (af ):
            try :
                with open (af ,'r',encoding ='utf-8')as fp :audit =json .load (fp )
                for agid ,events in (audit .items ()if isinstance (audit ,dict )else []):
                    if gid and str (agid )!=str (gid ):continue 
                    if not isinstance (events ,list ):continue 
                    for ev in events :
                        if not isinstance (ev ,dict ):continue 
                        bump (ev .get ('mod_name')or ev .get ('moderator')or ev .get ('mod'),
                        ev .get ('action','warn'),ev .get ('timestamp',''))
            except Exception as _ex :
                print (f'[MOD-STATS] Ошибка audit_log: {_ex }')
        # 3. warnings.json
        wf ='data/warnings.json'
        if os .path .exists (wf ):
            try :
                with open (wf ,'r',encoding ='utf-8')as fp :warns =json .load (fp )
                for wgid ,users in (warns .items ()if isinstance (warns ,dict )else []):
                    if gid and str (wgid )!=str (gid ):continue 
                    if not isinstance (users ,dict ):continue 
                    for _uid ,wlist in users .items ():
                        if not isinstance (wlist ,list ):continue 
                        for w in wlist :
                            if not isinstance (w ,dict ):continue 
                            bump (w .get ('mod')or w .get ('moderator'),'warn',w .get ('timestamp',''))
            except Exception as _ex :
                print (f'[MOD-STATS] Ошибка warnings: {_ex }')

        # 4. Сообщения и голос за неделю
        msg_map ={}
        voice_map ={}
        try :
            from services .mod_activity import message_counts as _mc
            msg_map =_mc (gid ,days =7 )
        except Exception as _ex :
            print (f'[MOD-STATS] Ошибка счётчика сообщений: {_ex }')
        try :
            from cogs .voice_tracker import voice_view as _vv
            vv =_vv (gid )
            users =vv .get ('users',{})if isinstance (vv ,dict )else {}
            for uid ,rec in users .items ():
                if not isinstance (rec ,dict ):continue 
                daily =rec .get ('daily')or {}
                secs =0 
                for d in range (7 ):
                    dkey =(now -timedelta (days =d )).strftime ('%Y-%m-%d')
                    try :secs +=max (0 ,int (daily .get (dkey ,0 )or 0 ))
                    except Exception as _ex :_log.debug("api_mod_stats(): голосовой день %s: %s", dkey, _ex )
                voice_map [str (uid )]={'name':rec .get ('name')or str (uid ),'seconds':secs ,'avatar':rec .get ('avatar')or ''}
        except Exception as _ex :
            print (f'[MOD-STATS] Ошибка голосового трекера: {_ex }')

        # 5. Демо-имена и аватары: mod-имена 'sonya.staff' → Sonya + аватар
        try :
            import web .app as _app2 
            if _app2 ._demo_mode ():
                from web .routes ._common import DEMO_MEMBERS
                demo_by_name ={str (m .get ('name','')).lower ():m for m in DEMO_MEMBERS }
                demo_by_id ={str (m .get ('id')):m for m in DEMO_MEMBERS }
                for row in rows .values ():
                    key =str (row ['mod'])
                    dm =demo_by_name .get (key .lower ())or demo_by_id .get (key )
                    if dm :
                        row ['name']=str (dm .get ('display_name')or dm .get ('name')or key )
                        row ['avatar']=str (dm .get ('avatar')or '')
                for uid ,rec in voice_map .items ():
                    dm =demo_by_id .get (uid )
                    if dm and not rec .get ('name'):
                        rec ['name']=str (dm .get ('display_name')or dm .get ('name')or uid )
                        rec ['avatar']=str (dm .get ('avatar')or '')
                for uid ,rec in msg_map .items ():
                    dm =demo_by_id .get (uid )
                    if dm :
                        rec ['name']=str (dm .get ('display_name')or dm .get ('name')or rec .get ('name')or uid )
        except Exception as _ex :
            print (f'[MOD-STATS] Ошибка демо-имён: {_ex }')

        # 6. Собрать строки: действия по mod-ключу, сообщения/голос по uid-ключу
        final =[]
        seen_mods =set ()
        for key ,row in rows .items ():
            name =row .get ('name')or key 
            avatar =row .get ('avatar')or ''
            msgs =0 
            vo_secs =0 
            # сообщения: ищем по ключу И по имени среди записей счётчика
            for uid ,rec in msg_map .items ():
                if str (uid )==key or (rec .get ('name')and str (rec ['name']).lower ()==str (name ).lower ()):
                    msgs =max (msgs ,rec .get ('messages',0 ))
                    seen_mods .add (str (uid ).lower ())
            for uid ,rec in voice_map .items ():
                if str (uid )==key or (rec .get ('name')and str (rec ['name']).lower ()==str (name ).lower ()):
                    vo_secs =max (vo_secs ,rec .get ('seconds',0 ))
                    seen_mods .add (str (uid ).lower ())
                    if not avatar :avatar =rec .get ('avatar')or ''
                    if name ==key and rec .get ('name'):name =rec ['name']
            row ['name']=name 
            row ['avatar']=avatar 
            row ['messages_week']=msgs 
            row ['voice_seconds_week']=vo_secs 
            row ['voice_hours_week']=round (vo_secs /3600.0 ,1 )
            final .append (row )
            seen_mods .add (key .lower ())
        # модеры только с сообщениями/голосом (без действий в логах)
        for uid ,rec in msg_map .items ():
            if str (uid ).lower ()in seen_mods :continue 
            vrec =voice_map .get (uid ,{})
            vs =vrec .get ('seconds',0 )
            final .append ({'mod':str (uid ),'name':rec .get ('name')or str (uid ),'avatar':vrec .get ('avatar')or '',
            'warns':0 ,'mutes':0 ,'kicks':0 ,'bans':0 ,'other':0 ,'total':0 ,'week':0 ,
            'duration_min':0 ,'duration_week_min':0 ,'messages_week':rec .get ('messages',0 ),
            'voice_seconds_week':vs ,'voice_hours_week':round (vs /3600.0 ,1 )})
            seen_mods .add (str (uid ).lower ())
        for uid ,rec in voice_map .items ():
            if str (uid ).lower ()in seen_mods :continue 
            mrec =msg_map .get (uid ,{})
            final .append ({'mod':str (uid ),'name':rec .get ('name')or str (uid ),'avatar':rec .get ('avatar')or '',
            'warns':0 ,'mutes':0 ,'kicks':0 ,'bans':0 ,'other':0 ,'total':0 ,'week':0 ,
            'duration_min':0 ,'duration_week_min':0 ,'messages_week':mrec .get ('messages',0 ),
            'voice_seconds_week':rec .get ('seconds',0 ),'voice_hours_week':round (rec .get ('seconds',0 )/3600.0 ,1 )})
            seen_mods .add (str (uid ).lower ())
        final .sort (key =lambda r :(-(r .get ('week')or 0 ),-(r .get ('total')or 0 ),str (r .get ('name','')).lower ()))
        kpis ={
        'active_mods':sum (1 for r in final if (r .get ('week')or 0 )>0 or (r .get ('messages_week')or 0 )>0 or (r .get ('voice_seconds_week')or 0 )>0 ),
        'actions_week':sum (r .get ('week')or 0 for r in final ),
        'actions_total':sum (r .get ('total')or 0 for r in final ),
        'messages_week':sum (r .get ('messages_week')or 0 for r in final ),
        'voice_hours_week':round (sum (r .get ('voice_seconds_week')or 0 for r in final )/3600.0 ,1 ),
        }
        return jsonify ({'success':True ,'guild_id':str (gid ),'generated_at':now .isoformat (),'kpis':kpis ,'rows':final })


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
        if not bot :
            # демо: типичный набор ролей (пустой список = страница «не листается»)
            if _app ._demo_mode ():
                return jsonify (sorted (_demo_roles_load (guild_id ),key =lambda x :-x ['members']))
            return jsonify ([])
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
        data =request .get_json (silent =True )or {}
        name =(data .get ('name')or '').strip ()
        if not name :
            return jsonify ({'error':'Требуется название роли'}),400 
        if not bot :
            # демо: роль создаётся в локальном хранилище превью
            if _app ._demo_mode ():
                roles =_demo_roles_load (guild_id )
                new_id =str (max ([int (r .get ('id','0'))for r in roles ]+[9000 ])+1 )
                roles .append ({'id':new_id ,'name':name ,'color':str (data .get ('color')or '#4f46e5'),'members':0 })
                _demo_roles_store (guild_id ,roles )
                return jsonify ({'success':True })
            return jsonify ({'error':'Бот офлайн'}),503 
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
        if not bot :
            # демо: удаление из локального хранилища превью
            if _app ._demo_mode ():
                roles =_demo_roles_load (guild_id )
                kept =[r for r in roles if str (r .get ('id'))!=str (role_id )]
                if len (kept )==len (roles ):
                    return jsonify ({'error':'Роль не найдена'}),404 
                _demo_roles_store (guild_id ,kept )
                return jsonify ({'success':True })
            return jsonify ({'error':'Бот офлайн'})
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
            if _app ._demo_mode ():
                print ('[WEB][WARN] /channels: bot is None — отдаём демо-структуру каналов')
                demo_file =os .path .join (os .path .dirname (os .path .dirname (os .path .dirname (os .path .abspath (__file__ )))),'data','demo_channels.json')
                if os .path .exists (demo_file ):
                    try :
                        with open (demo_file ,'r',encoding ='utf-8')as fp :
                            demo =json .load (fp )
                        demo =sorted (demo ,key =lambda x :((9999 if (x .get ('category_pos')is None or x .get ('category_pos')<0 )else x .get ('category_pos',0 )),x .get ('position',0 ),x .get ('name','')))
                        return jsonify (_annotate_hidden (guild_id ,demo ))
                    except Exception as e :
                        print (f'[WEB][WARN] /channels: demo_channels.json ошибка: {e}')
            print ('[WEB][WARN] /channels: bot is None')
            return jsonify ({'error':'Бот офлайн','channels':[]})

        guild =bot .get_guild (int (guild_id ))
        if not guild :
            for g in bot .guilds :
                if str (g .id )==str (guild_id ):
                    guild =g 
                    break 
        if not guild :
            print (f'[WEB][WARN] /channels: guild {guild_id} не найден. Bot guilds: {[str(g.id) for g in bot.guilds]}')
            return jsonify ({'error':f'Сервер {guild_id} не найден — бот не состоит на нём','channels':[]})

        type_map ={
        _discord .ChannelType .text :'text',
        _discord .ChannelType .voice :'voice',
        _discord .ChannelType .category :'category',
        _discord .ChannelType .news :'text',
        _discord .ChannelType .stage_voice :'voice',
        _discord .ChannelType .forum :'text',
        }

        channels_data =[]
        for c in guild .channels :
            try :
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
                # один проблемный канал не должен ронять весь список панели
                print (f'[WEB][WARN] channels: канал {getattr(c, "id", "?")} пропущен: {e}')

        sorted_channels =sorted (channels_data ,key =lambda x :(x ['category_pos'],x ['position']))
        _annotate_hidden (guild_id ,sorted_channels )
        print (f'[WEB] /channels guild={guild_id} returned {len(sorted_channels)} channels')
        return jsonify (sorted_channels )

    # ── Владелец: скрыть канал/категорию из панели ─────────────────────────
    @app .route ('/api/guild/<guild_id>/channels-visibility',methods =['POST'])
    @login_required
    @role_required ('owner')
    def api_channels_visibility (guild_id ):
        data =request .get_json (silent =True )or {}
        target =str (data .get ('id')or '').strip ()
        kind =str (data .get ('kind')or 'channel')
        hidden =bool (data .get ('hidden'))
        if not target :
            return jsonify ({'success':False ,'error':'Не указан id канала/категории'}),400
        if kind not in ('channel','category'):
            return jsonify ({'success':False ,'error':'kind должен быть channel или category'}),400
        store =_hidden_store ()
        g =store .setdefault (str (guild_id ),{'channels':[],'categories':[]})
        key ='categories'if kind =='category'else 'channels'
        lst =[str (x )for x in g .get (key ,[])]
        if hidden and target not in lst :
            lst .append (target )
        if not hidden and target in lst :
            lst .remove (target )
        g [key ]=lst
        _hidden_save (store )
        return jsonify ({'success':True ,'hidden':hidden ,'id':target ,'kind':kind })
