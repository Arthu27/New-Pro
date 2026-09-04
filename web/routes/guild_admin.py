# -*- coding: utf-8 -*-
"""Админка гильдии: роли, каналы, инфо, мод-история (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

from web.routes._common import (
    _run_async, _fetch_channel_msgs_async, _fetch_channel_msgs_sync,
    _notify_discord_sender, _fire_panel_notification,
    _live_publish, _process_action, _log,
    ms_normalize_query, ms_member_match, ms_search_members, ms_member_payload,
    ms_normalize_warn, ms_normalize_case, _REPO_ROOT, role_member_counts,
    render_template, session, redirect, url_for, request, jsonify, Response,
    os, json, time, math, discord, datetime, timezone, timedelta)

class _NoGuild (Exception ):
    """Сервер не выбран (MAIN_GUILD_ID пуст и бот офлайн).

    Не ошибка, а штатное состояние «данных ещё неоткуда взять»: отличаем
    его от настоящих сбоев, чтобы не сорить трейсбеками в консоль
    (инцидент 30.08: лог был полон «invalid literal for int() with base 10»).
    """


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
        {'id':'9013','name':'Куратор','color':'#22d3ee','members':5},
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


def _dedupe_by_id (items ):
    """Один id — один пункт в любом списке/селекте панели.

    Всеми пикерами каналов (объявления, настройки, чат) и ролей (репорты,
    логи, доступы) правят списки из API. Если источник вернул запись
    дважды (повтор id в кэше/демо-данных), в селекте появляются
    «2 одинаковых выбора». Оставляем только первый экземпляр каждого id.
    """
    if not isinstance (items ,list ):
        return items or []
    seen =set ()
    out =[]
    for it in items :
        if not isinstance (it ,dict ):
            continue
        iid =it .get ('id')
        if iid is None or iid in seen :
            continue
        seen .add (iid )
        out .append (it )
    return out


def _dedupe_channels (channels ):
    """см. _dedupe_by_id — специализация для каналов (историческое имя)."""
    return _dedupe_by_id (channels )


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


def _demo_channels_seed ():
    """Встроенная демо-структура каналов (тот же состав, что data/demo_channels.json)."""
    return [
        {'id':'1001','name':'правила','type':'text','position':0,'category':'ИНФОРМАЦИЯ','category_id':'900','hidden':False},
        {'id':'1002','name':'новости','type':'text','position':1,'category':'ИНФОРМАЦИЯ','category_id':'900','hidden':False},
        {'id':'1003','name':'FAQ','type':'text','position':2,'category':'ИНФОРМАЦИЯ','category_id':'900','hidden':False},
        {'id':'1015','name':'журнал-модерации','type':'forum','position':0,'category':'ИНФОРМАЦИЯ','category_id':'900','hidden':False},
        {'id':'1004','name':'флудилка','type':'text','position':0,'category':'ОБЩЕНИЕ','category_id':'901','hidden':False},
        {'id':'1005','name':'мемы','type':'text','position':1,'category':'ОБЩЕНИЕ','category_id':'901','hidden':False},
        {'id':'1006','name':'музыка-чат','type':'text','position':2,'category':'ОБЩЕНИЕ','category_id':'901','hidden':False},
        {'id':'1007','name':'предложения','type':'text','position':0,'category':'РАЗНОЕ','category_id':'902','hidden':False},
        {'id':'1008','name':'розыгрыши','type':'text','position':1,'category':'РАЗНОЕ','category_id':'902','hidden':False},
        {'id':'1010','name':'варны','type':'text','position':2,'category':'РАЗНОЕ','category_id':'902','hidden':False},
        {'id':'1016','name':'анонс-бота','type':'text','position':3,'category':'РАЗНОЕ','category_id':'902','hidden':False},
        {'id':'1017','name':'рекруты','type':'text','position':4,'category':'РАЗНОЕ','category_id':'902','hidden':False},
        {'id':'1018','name':'стата-недель','type':'text','position':5,'category':'РАЗНОЕ','category_id':'902','hidden':False},
        {'id':'1009','name':'тикет-логи','type':'text','position':6,'category':'РАЗНОЕ','category_id':'902','hidden':False},
        {'id':'1011','name':'общий-голос-1','type':'voice','position':0,'category':'ГОЛОСОВЫЕ','category_id':'903','bitrate':64,'user_limit':0,'hidden':False},
        {'id':'1012','name':'общий-голос-2','type':'voice','position':1,'category':'ГОЛОСОВЫЕ','category_id':'903','bitrate':64,'user_limit':0,'hidden':False},
        {'id':'1013','name':'афк','type':'voice','position':2,'category':'ГОЛОСОВЫЕ','category_id':'903','bitrate':32,'user_limit':99,'hidden':False},
        {'id':'1014','name':'сцена','type':'stage','position':0,'category':'ГОЛОСОВЫЕ','category_id':'903','bitrate':128,'user_limit':0,'hidden':False},
        # Сами КАТЕГОРИИ — это тоже каналы (type category): без них на
        # странице «Каналы» пустуют селекты «Категория» (создание/правка).
        {'id':'900','name':'ИНФОРМАЦИЯ','type':'category','position':0,'category_id':None,'category_pos':-1,'hidden':False},
        {'id':'901','name':'ОБЩЕНИЕ','type':'category','position':1,'category_id':None,'category_pos':-1,'hidden':False},
        {'id':'902','name':'РАЗНОЕ','type':'category','position':2,'category_id':None,'category_pos':-1,'hidden':False},
        {'id':'903','name':'ГОЛОСОВЫЕ','type':'category','position':3,'category_id':None,'category_pos':-1,'hidden':False},
    ]


def _demo_channels_sort (demo ):
    """Порядок категорий/позиций — как в живом списке каналов."""
    return sorted (demo ,key =lambda x :((9999 if (x .get ('category_pos')is None or x .get ('category_pos')<0 )else x .get ('category_pos',0 )),x .get ('position',0 ),x .get ('name','')))


def _fill_category_names (rows ):
    """Проставить 'category' (ИМЯ категории) по category_id, где имени нет.

    Живой /api/channels всегда отдаёт имя категории; демо-структура и
    старые data/demo_channels.json содержали только category_id — из-за
    этого страница «Каналы» показывала «undefined» вместо категории,
    группы категорий пустовали («В этой категории пока нет каналов»),
    а все каналы сваливались в «Без категории».
    """
    if not isinstance (rows ,list ):
        return rows
    by_id ={}
    for r in rows :
        if isinstance (r ,dict )and r .get ('type')=='category'and r .get ('id'):
            by_id [str (r ['id'])]=r .get ('name')or ''
    for r in rows :
        if isinstance (r ,dict )and not r .get ('category')and r .get ('category_id'):
            r ['category']=by_id .get (str (r ['category_id']))or None
        # Демо-сид и старые data/demo_channels.json не содержали числовых
        # полей — страница «Каналы» показывала «undefined kbps» у голосовых.
        if isinstance (r ,dict ):
            for k in ('bitrate','connected','slowmode','user_limit','position'):
                if not isinstance (r .get (k),(int ,float )):
                    r [k]=0
            r .setdefault ('topic','')
            for k in ('nsfw','news','stage','forum','hidden'):
                r .setdefault (k ,False )
    return rows


def demo_channels_list (guild_id ):
    """Демо-каналы: data/demo_channels.json, а если не засеян — встроенный список."""
    demo_file =os .path .join (_REPO_ROOT ,'data','demo_channels.json')
    if os .path .exists (demo_file ):
        try :
            with open (demo_file ,'r',encoding ='utf-8')as fp :
                demo =json .load (fp )
            if isinstance (demo ,list )and demo :
                return _demo_channels_sort (_fill_category_names (demo ))
        except Exception as _ex :
            _log.debug ("demo_channels_list(): подавлено: %s", _ex)
    return _demo_channels_sort (_fill_category_names (_demo_channels_seed ()))


def resolve_guild (guild_id ):
    """Живая гильдия бота или None.

    Тот же порядок, что у /api/channels: get_guild(int), затем обход
    bot.guilds по str(id). Один только get_guild в бою регулярно промахивается
    (кэш гильдий ещё не наполнен) — отсюда «пустые» селекты на живом сервере.
    """
    import web .app as _app
    bot =getattr (_app ,'bot_instance',None )
    if not bot or not guild_id :
        return None
    guild =None
    try :
        guild =bot .get_guild (int (guild_id ))
    except (TypeError ,ValueError ):
        guild =None
    if guild is None :
        for g in getattr (bot ,'guilds',[])or []:
            if str (getattr (g ,'id',''))==str (guild_id ):
                guild =g
                break
    return guild


def guild_channels_roles (guild_id ):
    """(текстовые каналы, роли) гильдии для пикеров настроек.

    Порядок источников:
    1) живая гильдия бота в этом процессе;
    2) бот в ОТДЕЛЬНОМ процессе — реальные снимки из моста
       (data/bot_roles_<gid>.json + panel_channels_cache_<gid>.json);
    3) иначе — известный состав-плейсхолдер (тот же, что /api/channels и
       /api/roles): живой гильдии нет, а пикер обязан оставаться живым
       (историческое поведение — селект с одной строкой «— не задан —»
       выглядел сломанным при холодном кэше гильдий).
    """
    guild =resolve_guild (guild_id )
    if guild is not None :
        channels =[{'id':str (c .id ),'name':c .name }
                   for c in getattr (guild ,'text_channels',[])or []]
        roles =[{'id':str (r .id ),'name':r .name }
                for r in getattr (guild ,'roles',[])or []
                if r .id !=guild .id ]
        # Общий резолвер питает пикеры многих страниц (репорты, логи и т.д.):
        # дубли id в кэше гильдии = «2 одинаковых выбора» в селектах.
        return _dedupe_channels (channels ),_dedupe_channels (roles )
    # Панель отдельным процессом от бота: снимки, которые бот пишет в data/
    # (services.bot_bridge) — реальные роли и текстовые каналы сервера.
    from services import bot_bridge as _bb
    if _bb .bot_alive_for (guild_id ):
        channels =[{'id':str (c .get ('id','')),'name':c .get ('name','')}
                  for c in (_bb .read_channels (guild_id )or [])
                  if c .get ('type')=='text']
        roles =[{'id':r ['id'],'name':r ['name']}
                for r in (_bb .read_roles (guild_id )or [])
                if not r .get ('managed')and str (r .get ('id',''))!=str (guild_id )]
        return _dedupe_channels (channels ),_dedupe_channels (roles )
    channels =[{'id':str (c .get ('id','')),'name':c .get ('name','')}
              for c in demo_channels_list (guild_id )
              if c .get ('type')=='text']
    roles =[{'id':str (r .get ('id','')),'name':r .get ('name','')}
            for r in _demo_roles_load (guild_id )]
    return _dedupe_channels (channels ),_dedupe_channels (roles )


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
        # Та же изоляция, что у /api/logs: при заданном MAIN_GUILD_ID
        # хвост журнала — только главного сервера, склейки чужих не бывает.
        _mg =str (getattr (_app ,'MAIN_GUILD_ID','')or '')
        if _mg :guild_id =_mg 
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

        # Имена вместо ID: цель и модератор резолвятся из карты имён гильдии.
        # ВАЖНО: здесь нужен guild_id (сервер из запроса/MAIN_GUILD_ID), а НЕ
        # gid — тот был переменной ЦИКЛА выше. Если ни один цикл не отработал
        # (файлов mod_data.json/warnings.json ещё нет — чистая установка),
        # имя gid вообще не определено, и весь блок падал с
        # «cannot access local variable 'gid'» → имена не резолвились,
        # в истории модерации вместо ников торчали голые ID.
        _target_gid = str(guild_id or '')
        try :
            import web .app as _appm
            _nm =_appm ._guild_name_map (_target_gid )if _target_gid else {}
            for _ev in all_events :
                _gid =str (_ev .get ('guild_id')or '')
                if _gid and _target_gid and _gid !=_target_gid :
                    continue 
                _map =_nm
                _uid =str (_ev .get ('target_id')or _ev .get ('user_id')or '').strip ()
                if _uid and (not str (_ev .get ('target_name')or '').strip ()or str (_ev .get ('target_name'))==_uid ):
                    _ev ['target_name']=_map .get (_uid )or _uid
                _mid =str (_ev .get ('mod_id')or '').strip ()
                if _mid and not str (_ev .get ('mod_name')or '').strip ():
                    _ev ['mod_name']=_map .get (_mid )or _mid
        except Exception as _ex :
            print (f'[MOD-HISTORY] Имена: {_ex }')
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
        # Сервер может быть НЕ выбран (MAIN_GUILD_ID пуст + бот офлайн) —
        # тогда gid = '' и источники ниже падают на int(''). Это не ошибка
        # данных, а «сервера ещё нет»: считаем метрики пустыми и не сорим
        # трейсбеками в консоль (инцидент 30.08: лог полон
        # «invalid literal for int() with base 10: ''»).
        if gid :
            try :
                from services .mod_activity import message_counts as _mc
                msg_map =_mc (gid ,days =7 )
            except Exception as _ex :
                print (f'[MOD-STATS] Ошибка счётчика сообщений: {_ex }')
        try :
            if not gid :
                raise _NoGuild ('сервер не выбран')
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
        except _NoGuild as _ex :
            # сервер не выбран — голосовых метрик просто нет (не ошибка)
            _log .debug ('api_mod_stats(): голос пропущен: %s',_ex )
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


    def _roles_cache_drop (guild_id ):
        """Сбросить живой кэш списка ролей ТОЛЬКО этого сервера.

        Раньше после создания/удаления роли обнуляли весь кэш целиком — и
        следующий запрос по каждому остальному серверу шёл мимо кэша.
        """
        live =getattr (api_guild_roles ,'_live_cache',None )
        if not isinstance (live ,dict ):
            return
        for k in [k for k in live if str (k [0 ])==str (guild_id )]:
            live .pop (k ,None )

    @app .route ('/api/roles')
    @login_required 
    def api_roles_default ():
        import web .app as _app
        _gid =MAIN_GUILD_ID or ('777'if _app ._demo_mode ()else 0 )
        if not _gid :
            return jsonify ({'error':'Сервер не выбран (задайте MAIN_GUILD_ID в .env)'}),503 
        return api_guild_roles (str (_gid ))


    @app .route ('/api/channels')
    @login_required 
    def api_channels_default ():
        # Демо-витрина без MAIN_GUILD_ID показывает демо-сервер 777, а не 503:
        # пикеры каналов на страницах настроек не должны пустовать.
        import web .app as _app
        _gid =MAIN_GUILD_ID or ('777'if _app ._demo_mode ()else 0 )
        if not _gid :
            return jsonify ({'error':'Сервер не выбран (задайте MAIN_GUILD_ID в .env)'}),503 
        return api_guild_channels (str (_gid ))


    @app .route ('/api/members')
    @login_required 
    def api_members_default ():
        import web .app as _app
        _gid =MAIN_GUILD_ID or ('777'if _app ._demo_mode ()else 0 )
        if not _gid :
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
                return jsonify (_dedupe_by_id (sorted (_demo_roles_load (guild_id ),key =lambda x :-x ['members'])))
            # панель отдельным процессом, бот жив по пульсу: реальные роли из
            # снимка (id/имя/цвет) — пикеры «роль сервера» по всей панели живые.
            from services import bot_bridge as _bb
            if _bb .bot_alive_for (guild_id ):
                rows =[{'id':r .get ('id'),'name':r .get ('name'),
                        'color':r .get ('color')or '','members':0}
                       for r in (_bb .read_roles (guild_id )or [])
                       if r .get ('id')]
                return jsonify (_dedupe_by_id (rows))
            return jsonify ([])
        guild =bot .get_guild (int (guild_id ))
        if not guild :return jsonify ([])
        # Живой кэш + ETag/304 (как у каналов): состав ролей меняется редко,
        # а настройки/пикеры опрашивают список часто. len(roles) в сигнатуре
        # даёт мгновенный промах при создании/удалении роли.
        def _rl_respond (_payload ,_sig ):
            _etag ='"rl%d-%d"'%(len (_payload ),_sig )
            if _etag in request .headers .get ('If-None-Match',''):
                from flask import Response as _Resp
                return _Resp (status =304 ,headers ={'ETag':_etag ,'Cache-Control':'no-cache'})
            from flask import Response as _Resp
            return _Resp (json .dumps (_payload ,ensure_ascii =False ),
            mimetype ='application/json',
            headers ={'ETag':_etag ,'Cache-Control':'no-cache'})
        import time as _time
        _now =_time .time ()
        _live =getattr (api_guild_roles ,'_live_cache',{})
        _ckey =(str (guild_id ),len (getattr (guild ,'roles',[])or []))
        _hit =_live .get (_ckey )
        if _hit and (_now -_hit [0 ])<10.0 :
            return _rl_respond (_hit [1 ],_ckey [1 ])
        # Число участников в роли — одним проходом по составу сервера.
        # Было len(r.members) на каждую роль, а Role.members в discord.py
        # копирует и фильтрует ВЕСЬ список участников (discord/role.py:415) —
        # на 250 ролях и 20 000 участников это 5 млн итераций и [SLOW] 2.95 с
        # в логе, из-за чего туннель рвал соединение (context canceled).
        _counts =role_member_counts (guild )
        roles =[{'id':str (r .id ),'name':r .name ,'color':str (r .color ),
        'members':_counts .get (r .id ,0 )}
        for r in guild .roles if r .name !='@everyone']
        roles =_dedupe_by_id (sorted (roles ,key =lambda x :-x ['members']))
        try :
            api_guild_roles ._live_cache =getattr (api_guild_roles ,'_live_cache',{})
            api_guild_roles ._live_cache [_ckey ]=(_now ,roles )
            for _k in [k for k ,v in api_guild_roles ._live_cache .items ()if _now -v [0 ]>60.0 ]:
                api_guild_roles ._live_cache .pop (_k ,None )
        except Exception as _rce :
            _log .debug ('roles live-cache: %s',_rce )
        return _rl_respond (roles ,_ckey [1 ])


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
        if len (name )>100 :
            # Discord режет имена ролей на 100 символах и отвечает на это
            # невнятной 400 — говорим по-человечески сами
            return jsonify ({'error':'Название роли длиннее 100 символов — Discord такое не принимает'}),400 
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
            await (guild .create_role (name =name ,color =color ,reason ='Создано через панель Hakumo'))
        try :
            asyncio .run_coroutine_threadsafe (do (),bot .loop ).result (timeout =10 )
            _roles_cache_drop (guild_id )
            _live_publish (gid ,'roles')
            return jsonify ({'success':True })
        except discord .Forbidden :
            return jsonify ({'error':'У меня нет прав создавать роли на этом сервере'}),403 
        except discord .HTTPException as e :
            return jsonify ({'error':f'Ошибка Discord: {e}'}),500 
        except TimeoutError :
            return jsonify ({'error':'Discord не ответил за 10 секунд — попробуйте ещё раз'}),504 
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
            return jsonify ({'error':'Бот офлайн'}),503 
        try :
            gid =int (guild_id )
        except (TypeError ,ValueError ):
            return jsonify ({'error':'Неверный ID сервера'}),400 
        if not str (role_id ).isdigit ():
            # было int(role_id) без проверки → 500 с трейсбеком на «/delete»
            return jsonify ({'error':'Неверный ID роли'}),400 
        guild =resolve_guild (guild_id )
        if guild is None :
            return jsonify ({'error':f'Бот не состоит на этом сервере (id={guild_id})'}),404 
        role =guild .get_role (int (role_id ))
        if role is None :
            # раньше роль «не найдена» тоже считалась успехом: панель писала
            # «Роль удалена», а роль оставалась на сервере
            return jsonify ({'error':'Роль не найдена — возможно, её уже удалили'}),404 
        if int (role .id )==int (guild .id ):
            # то же самое, что role.is_default(), но не требует метода
            # (discord.Role.is_default — это ровно id == guild.id)
            return jsonify ({'error':'Роль @everyone удалить нельзя'}),400 
        if getattr (role ,'managed',False ):
            return jsonify ({'error':'Эту роль выдаёт интеграция (бот или подписка) — Discord не даёт её удалить'}),403 

        async def do ():
            await role .delete (reason ='Удалено через панель Hakumo')

        try :
            asyncio .run_coroutine_threadsafe (do (),bot .loop ).result (timeout =10 )
        except discord .Forbidden :
            return jsonify ({'error':'У меня нет прав удалить эту роль: она стоит выше моей в иерархии'}),403 
        except discord .HTTPException as e :
            return jsonify ({'error':f'Ошибка Discord: {e}'}),500 
        except TimeoutError :
            return jsonify ({'error':'Discord не ответил за 10 секунд — попробуйте ещё раз'}),504 
        except Exception as e :
            return jsonify ({'error':str (e )}),500 
        _roles_cache_drop (guild_id )
        _live_publish (gid ,'roles')
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
                        return jsonify (_annotate_hidden (guild_id ,_dedupe_channels (_fill_category_names (demo ))))
                    except Exception as e :
                        print (f'[WEB][WARN] /channels: demo_channels.json ошибка: {e}')
                # Демо-структура не засеяна — отдаём полный встроенный список
                # (тот же состав, что жил в data/demo_channels.json), чтобы
                # селекты каналов и чат не пустовали в превью.
                return jsonify (_annotate_hidden (guild_id ,_dedupe_channels (_fill_category_names (_demo_channels_seed ()))))
            cached =_channels_offline_cache (guild_id )
            if cached :
                print (f'[WEB] /channels bot offline — отдаём кэш ({len(cached)} кан.)')
                return jsonify (_dedupe_channels (cached ))
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

        # Короткий in-memory кэш живого списка: страницы настроек и опросы
        # дёргают /channels часто, а пересборка с обходом каналов и подсчётом
        # участников в голосовых — лишняя работа на каждый тик. 3 сек свежести
        # достаточно. В ключе — число каналов сервера: при создании/удалении
        # канала состав меняется и кэш промахивается мгновенно (без ожидания
        # TTL), при неизменном составе — попадает и экономит пересборку.
        import time as _time
        _now = _time.time()
        _live = getattr(api_guild_channels, '_live_cache', {})
        _ckey = (str(guild_id), len(getattr(guild, 'channels', []) or []))
        _hit = _live.get(_ckey)
        # TTL поднят с 3 до 10с: настройки и пикеры опрашивают список часто,
        # состав каналов меняется редко (а при создании/удалении сигнатура
        # с числом каналов меняется → промах мгновенно, без ожидания TTL).
        if _hit and (_now - _hit[0]) < 10.0:
            _payload = _hit[1]
            # ETag/304: повторный опрос с тем же составом отдаём без тела —
            # селекты на страницах настроек не пересобирают ответ вхолостую.
            _etag = '"ch%d-%d"' % (len(_payload), _ckey[1])
            if _etag in request.headers.get('If-None-Match', ''):
                from flask import Response as _Resp
                return _Resp(status=304, headers={'ETag': _etag,
                                                   'Cache-Control': 'no-cache'})
            from flask import Response as _Resp
            return _Resp(json.dumps(_payload, ensure_ascii=False),
                         mimetype='application/json',
                         headers={'ETag': _etag, 'Cache-Control': 'no-cache'})

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
                # «Подключено» имеет смысл только для голосового канала —
                # сколько людей сейчас в нём сидит. Раньше c.members звали у
                # КАЖДОГО канала, а в discord.py у текстового канала members —
                # это «все, кто канал видит»: [m for m in guild.members if
                # permissions_for(m).read_messages] (discord/channel.py:419).
                # На сервере в 20 000 участников это 20 000 проверок прав на
                # КАЖДЫЙ текстовый канал — десятки секунд на один /api/channels.
                # У голосового members берётся из guild._voice_states
                # (discord/channel.py:1132) и стоит копейки.
                if ch_type in ('voice', 'stage'):
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
        # Защита от дублей на источнике (см. _dedupe_channels): все пикеры
        # каналов берут список отсюда — дублей в селектах быть не должно.
        sorted_channels =_dedupe_channels (sorted_channels )
        _annotate_hidden (guild_id ,sorted_channels )
        # Кладём в короткий in-memory кэш (следующие 10 сек отдаём без пересборки).
        try :
            api_guild_channels ._live_cache =getattr (api_guild_channels ,'_live_cache',{})
            api_guild_channels ._live_cache [_ckey ] =(_now ,sorted_channels )
            # Лёгкая уборка протухших ключей (разные числа каналов со временем),
            # чтобы словарь не рос вечно.
            for _k in [k for k ,v in api_guild_channels ._live_cache .items ()if _now -v [0 ] >60.0 ]:
                api_guild_channels ._live_cache .pop (_k ,None )
        except Exception as _cce :
            _log .debug ('channels live-cache: %s',_cce )
        # Запоминаем живой список: при кратком офлайне/перезапуске бота
        # пикеры каналов не пустуют и имена не превращаются в голые ID.
        try :
            os .makedirs ('data',exist_ok =True )
            with open (f'data/panel_channels_cache_{guild_id}.json','w',encoding ='utf-8')as _cf :
                json .dump ({'channels':sorted_channels },_cf ,ensure_ascii =False )
        except Exception as _ce :
            _log .debug ('channels cache save: %s',_ce )
        _etag ='"ch%d-%d"' % (len (sorted_channels ),_ckey [1 ])
        if _etag in request .headers .get ('If-None-Match',''):
            from flask import Response as _Resp
            return _Resp (status =304 ,headers ={'ETag':_etag ,'Cache-Control':'no-cache'})
        from flask import Response as _Resp
        return _Resp (json .dumps (sorted_channels ,ensure_ascii =False ),
        mimetype ='application/json',
        headers ={'ETag':_etag ,'Cache-Control':'no-cache'})

    def _channels_offline_cache (guild_id ):
        """Последний известный список каналов (имена + id) при офлайн-боте."""
        try :
            p =f'data/panel_channels_cache_{guild_id}.json'
            if os .path .exists (p ):
                with open (p ,encoding ='utf-8')as fh :
                    data =json .load (fh )
                chans =data .get ('channels')if isinstance (data ,dict )else None
                good =[c for c in (chans or [])if c .get ('id')and c .get ('name')]
                if good :
                    return good
        except Exception as _ce :
            print (f'[WEB][WARN] channels cache load: {_ce}')
        return None

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
        try :
            from services .live_bus import publish as _lpub
            _lpub (str (guild_id ),'channels')
        except Exception as _live_ex :
            print (f'[WEB][WARN] hidden-channel live-push: {_live_ex}')
        return jsonify ({'success':True ,'hidden':hidden ,'id':target ,'kind':kind })
