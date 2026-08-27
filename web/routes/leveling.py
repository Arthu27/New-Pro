# -*- coding: utf-8 -*-
"""Левелинг API (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

from web.routes._common import (
    _run_async, _fetch_channel_msgs_async, _fetch_channel_msgs_sync,
    _load_ai_tickets, _notify_discord_sender, _fire_panel_notification,
    _process_action, _log,
    ms_normalize_query, ms_member_match, ms_search_members, ms_member_payload,
    ms_normalize_warn, ms_normalize_case, calculate_ai_ticket_stats, _REPO_ROOT,
    render_template, session, redirect, url_for, request, jsonify, Response,
    os, json, time, math, discord, datetime, timezone,
)

def _demo_leveling_file (guild_id ):
    return f'data/leveling_demo_{guild_id}.json'

def _demo_leveling_default ():
    return {
        'enabled':True ,
        'text_xp':{'enabled':True ,'min':15 ,'max':25 ,'cooldown_sec':60 },
        'voice_xp':{'enabled':True ,'per_minute':5 ,'min_online_sec':60 },
        'streak_bonus':{'enabled':True ,'7_days':2.0 ,'14_days':3.0 ,'30_days':5.0 },
        'level_rewards':{
            '5':{'role_id':None ,'message':' Вы достигли 5 уровня!'},
            '10':{'role_id':None ,'message':' 10 уровень — вы ветеран!'},
            '25':{'role_id':None ,'message':' 25 уровень — почетный участник!'},
        },
        'achievements_enabled':True ,
        'engagement_dm':{'enabled':True ,'after_inactive_hours':48 ,'message':' Скучаем по тебе на сервере!'},
    }

def _demo_leveling_config (guild_id ):
    f =_demo_leveling_file (guild_id )
    if os .path .exists (f ):
        try :
            with open (f ,'r',encoding ='utf-8')as fp :
                return json .load (fp )
        except Exception as _ex :
            _log.debug("_demo_leveling_config(): подавлено: %s", _ex)
    return _demo_leveling_default ()

def _demo_leveling_save (guild_id ,cfg ):
    try :
        with open (_demo_leveling_file (guild_id ),'w',encoding ='utf-8')as fp :
            json .dump (cfg ,fp ,ensure_ascii =False ,indent =2 )
    except Exception as _ex :
        _log.debug("_demo_leveling_save(): подавлено: %s", _ex)

def register(ctx):
    app = ctx.app
    ROLES = ctx.ROLES
    login_required = ctx.login_required
    role_required = ctx.role_required
    MAIN_GUILD_ID = ctx.MAIN_GUILD_ID
    active_guild_id = ctx.active_guild_id
    _resolve_member_async = ctx._resolve_member_async


        # ── LEVELING API ─────────────────────────────────────
    @app .route ('/api/leveling/config',methods =['GET','POST'])
    @login_required 
    @role_required ('admin')
    def api_leveling_config ():
        import web .app as _app ;bot =_app .bot_instance 
        guild_id =str (session .get ('selected_guild')or MAIN_GUILD_ID )
        if _app ._demo_mode ()or not bot :
            # демо: конфиг живёт локально, тумблеры в превью работают
            if request .method =='POST':
                cfg =_demo_leveling_config (guild_id )
                patch =request .get_json (silent =True )or {}
                for k ,v in patch .items ():
                    cfg [k ]=v 
                _demo_leveling_save (guild_id ,cfg )
                return jsonify ({'ok':True ,'config':cfg })
            return jsonify (_demo_leveling_config (guild_id ))
        from cogs .leveling_engagement import LevelingEngagement 
        cog =bot .get_cog ('LevelingEngagement')
        if request .method =='POST':
            cfg =cog .load_config (guild_id )
            patch =request .get_json (silent =True )or {}
            for k ,v in patch .items ():
                cfg [k ]=v 
            cog .save_config (guild_id ,cfg )
            return jsonify ({'ok':True ,'config':cfg })
        return jsonify (cog .load_config (guild_id ))


    @app .route ('/api/leveling/stats')
    @login_required 
    def api_leveling_stats ():
        import web .app as _app ;bot =_app .bot_instance 
        guild_id =str (session .get ('selected_guild')or MAIN_GUILD_ID )
        if _app ._demo_mode ()or not bot :
            # демо: статистика из демо-XP файла
            users ={}
            try :
                with open (f'data/xp_{guild_id}.json','r',encoding ='utf-8')as fp :
                    raw =json .load (fp )
                if isinstance (raw ,dict ):
                    users =raw 
            except Exception as _ex :
                _log.debug("api_leveling_stats() demo: подавлено: %s", _ex)
            top =sorted (users .values (),key =lambda x :x .get ('xp',0 ),reverse =True )[:10 ]
            top_list =[{'name':u .get ('name','Участник'),'level':u .get ('level',1 ),'xp':u .get ('xp',0 )}for u in top ]
            levels =[int (u .get ('level',0 ))for u in users .values ()]
            # Честный офлайн: без бота показываем ТО, что реально накоплено
            # в xp_<gid>.json. Подставлять выдуманных участников и тонны XP
            # можно только в режиме предпросмотра (DEMO_MODE=1) — в бою
            # владелец не должен видеть данные, которых не добавлял.
            _demo =bool (getattr (_app ,'_demo_mode ',lambda :False )())
            _has =bool (users )
            return jsonify ({
                'total_users':len (users )if _has else (8 if _demo else 0 ),
                'max_level':max (levels )if levels else (31 if _demo else 0 ),
                'total_xp':sum (u .get ('xp',0 )for u in users .values ())if _has else (184200 if _demo else 0 ),
                'total_achievements':12 if (_has or _demo )else 0 ,
                'total_ach_available':20 if (_has or _demo )else 0 ,
                'top':(top_list or ([
                    {'name':'sonya.staff','level':31 ,'xp':84200 },
                    {'name':'ecobar','level':24 ,'xp':49800 },
                    {'name':'dragon','level':19 ,'xp':27100 },
                ] if _demo else [] )),
            })
        from cogs .leveling_engagement import LevelingEngagement ,level_from_xp 
        cog =bot .get_cog ('LevelingEngagement')
        if not cog :
            return jsonify ({'error':'Модуль не загружен'}),404 
        guild_id =str (session .get ('selected_guild')or MAIN_GUILD_ID )
        data =cog .load_xp (guild_id )
        users =data .get ('users',{})
        top =sorted (users .items (),key =lambda x :x [1 ].get ('xp',0 ),reverse =True )[:10 ]
        top_list =[]
        for uid ,u in top :
            member =bot .get_guild (int (guild_id )).get_member (int (uid ))if bot .get_guild (int (guild_id ))else None 
            level ,_ ,_ =level_from_xp (u .get ('xp',0 ))
            top_list .append ({
            'name':member .display_name if member else f'User#{uid}',
            'level':level ,
            'xp':u .get ('xp',0 )
            })
        max_lvl =0 
        for u in users .values ():
            lvl ,_ ,_ =level_from_xp (u .get ('xp',0 ))
            if lvl >max_lvl :
                max_lvl =lvl 
        from cogs .leveling_engagement import ACHIEVEMENTS 
        return jsonify ({
        'total_users':len (users ),
        'max_level':max_lvl ,
        'total_xp':sum (u .get ('xp',0 )for u in users .values ()),
        'total_achievements':sum (len (v )for v in data .get ('achievements',{}).values ()),
        'total_ach_available':len (ACHIEVEMENTS ),
        'top':top_list 
        })


    @app .route ('/api/leveling/achievements')
    @login_required 
    def api_leveling_achievements ():
        import web .app as _app ;bot =_app .bot_instance 
        guild_id =str (session .get ('selected_guild')or MAIN_GUILD_ID )
        if _app ._demo_mode ()or not bot :
            from cogs .leveling_engagement import ACHIEVEMENTS 
            demo_unlocked =[k for k in list (ACHIEVEMENTS .keys ())[:6 ]]
            return jsonify ({'unlocked':demo_unlocked ,'catalog':ACHIEVEMENTS })
        from cogs .leveling_engagement import LevelingEngagement 
        cog =bot .get_cog ('LevelingEngagement')
        if not cog :
            return jsonify ({'error':'Модуль не загружен'}),404 
        guild_id =str (session .get ('selected_guild')or MAIN_GUILD_ID )
        data =cog .load_xp (guild_id )
        username =session .get ('username','')
        # Find user's unlocked achievements
        unlocked =[]
        for uid ,achs in data .get ('achievements',{}).items ():
            try :
                g =bot .get_guild (int (guild_id ))
                if g :
                    m =g .get_member (int (uid ))
                    if m and m .display_name ==username :
                        unlocked =achs 
                        break 
            except Exception as _ex:
                _log.debug("api_leveling_achievements(): подавлено: %s", _ex)
        from cogs .leveling_engagement import ACHIEVEMENTS 
        return jsonify ({'unlocked':unlocked ,'catalog':ACHIEVEMENTS })


    @app .route ('/api/leveling/rewards')
    @login_required 
    def api_leveling_rewards ():
        import web .app as _app ;bot =_app .bot_instance 
        guild_id =str (session .get ('selected_guild')or MAIN_GUILD_ID )
        if _app ._demo_mode ()or not bot :
            return jsonify ({'rewards':_demo_leveling_config (guild_id ).get ('level_rewards',{})})
        from cogs .leveling_engagement import LevelingEngagement 
        cog =bot .get_cog ('LevelingEngagement')
        if not cog :
            return jsonify ({'error':'Модуль не загружен'}),404 
        guild_id =str (session .get ('selected_guild')or MAIN_GUILD_ID )
        cfg =cog .load_config (guild_id )
        return jsonify ({'rewards':cfg .get ('level_rewards',{})})
