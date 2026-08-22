# -*- coding: utf-8 -*-
"""Данные участников: варны, дежурства, AFK, профили, дни рождения (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

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


    @app .route ('/api/warn-config/<guild_id>',methods =['GET'])
    @login_required 
    @role_required ('admin')
    def api_warn_config_get (guild_id ):
        f =f'data/warn_config_{guild_id}.json'
        if not os .path .exists (f ):
            return jsonify ({'thresholds':[{'count':3 ,'action':'timeout','duration':10 },{'count':5 ,'action':'ban','duration':0 }]})
        with open (f ,encoding ='utf-8')as fp :
            return jsonify (json .load (fp ))


    @app .route ('/api/warn-config/<guild_id>',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_warn_config_save (guild_id ):
        d =request .get_json (silent =True )or {}
        os .makedirs ('data',exist_ok =True )
        with open (f'data/warn_config_{guild_id}.json','w',encoding ='utf-8')as fp :
            json .dump (d ,fp ,indent =2 ,ensure_ascii =False )
        return jsonify ({'ok':True })


    @app .route ('/api/duty/<guild_id>',methods =['GET'])
    @login_required 
    @role_required ('admin')
    def api_duty_data (guild_id ):
        duty_f ='data/duty_log.json'
        pts_f ='data/duty_points.json'
        duty ={}
        pts ={}
        if os .path .exists (duty_f ):
            with open (duty_f ,encoding ='utf-8')as f :duty =json .load (f ).get (guild_id ,{})
        if os .path .exists (pts_f ):
            with open (pts_f ,encoding ='utf-8')as f :pts =json .load (f ).get (guild_id ,{})
        return jsonify ({'duty':duty ,'points':pts })


    @app .route ('/api/afk/<guild_id>',methods =['GET'])
    @login_required 
    @role_required ('mod')
    def api_afk_list (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        if not bot :return jsonify ([])
        afk_cog =bot .get_cog ('AFK')
        if not afk_cog :return jsonify ([])
        guild_afk =afk_cog ._afk .get (str (guild_id ),{})
        result =[]
        guild =bot .get_guild (int (guild_id ))
        for uid ,data in guild_afk .items ():
            member =guild .get_member (int (uid ))if guild else None 
            result .append ({
            'id':uid ,
            'name':member .display_name if member else uid ,
            'avatar':str (member .display_avatar .url )if member else None ,
            'reason':data .get ('reason','AFK'),
            'since':data .get ('since','')
            })
        return jsonify (result )


    @app .route ('/api/watchlist/<guild_id>',methods =['GET'])
    @login_required 
    @role_required ('mod')
    def api_watchlist (guild_id ):
        f ='data/mod_data.json'
        if not os .path .exists (f ):return jsonify ([])
        with open (f ,encoding ='utf-8')as fp :
            data =json .load (fp )
        wl =data .get ('watchlist',{}).get (guild_id ,{})
        result =[]
        try :
            from web .routes ._common import name_map_for
            _nm =name_map_for (guild_id )
        except Exception as _ex :
            _nm ={}
        for uid ,info in wl .items ():
            result .append ({'id':uid ,'name':_nm .get (uid )or info .get ('name')or uid ,
            'reason':info .get ('reason',''),'added_by':info .get ('added_by',''),
            'timestamp':info .get ('timestamp','')})
        return jsonify (result )


    @app .route ('/api/member-search/<guild_id>',methods =['GET'])
    @login_required 
    @role_required ('admin')
    def api_member_search (guild_id ):
        # Поиск участников: по имени, нику, упоминанию или (части) ID,
        # с релевантной сортировкой и понятными ошибками вместо молчаливых [].
        import web .app as _app ;bot =_app .bot_instance 
        if not bot :
            from web .routes ._common import demo_members_search ,demo_member_payload
            q =ms_normalize_query (request .args .get ('q',''))
            if not q :
                return jsonify ({'error':'Введите имя, никнейм или ID участника.'}),400 
            return jsonify ([demo_member_payload (m )for m in demo_members_search (q )])
        guild =bot .get_guild (int (guild_id )if str (guild_id ).isdigit ()else 0 )
        if not guild :
            return jsonify ({'error':'Сервер не найден: проверьте выбор сервера на панели.'}),404 
        q =ms_normalize_query (request .args .get ('q',''))
        if not q :
            return jsonify ({'error':'Введите имя, никнейм или ID участника.'}),400 
        matches =ms_search_members (guild .members ,q ,limit =25 )
        return jsonify ([ms_member_payload (m )for m in matches ])


    @app .route ('/api/member-profile/<guild_id>/<user_id>',methods =['GET'])
    @login_required 
    @role_required ('admin')
    def api_member_profile (guild_id ,user_id ):
        # Профиль участника: данные Discord + предупреждения + история модерации.
        if not str (user_id ).isdigit ():
            return jsonify ({'error':'Некорректный ID участника.'}),400 
        import web .app as _app ;bot =_app .bot_instance 
        result ={'id':user_id ,'warnings':[],'warn_count':0 ,'case':[],'cases':[],'case_count':0 }
        if bot :
            guild =bot .get_guild (int (guild_id )if str (guild_id ).isdigit ()else 0 )
            if guild :
                m =guild .get_member (int (user_id ))
                if m :
                    result .update (ms_member_payload (m ))
                    result ['joined_at']=m .joined_at .isoformat ()if m .joined_at else None 
                    result ['created_at']=m .created_at .isoformat ()if m .created_at else None 
                    result ['role']=[r .name for r in m .roles [1 :]]
                    result ['roles']=[{'name':r .name ,'color':str (r .color )}for r in m .roles [1 :]]
                    result ['member_found']=True 
                else :
                    result ['member_found']=False 
        # Предупреждения (работают и когда бот не в сети — читаются с диска)
        warns =[]
        wf ='data/warnings.json'
        if os .path .exists (wf ):
            try :
                with open (wf ,encoding ='utf-8')as f :wdata =json .load (f )
                warns =wdata .get (str (guild_id ),{}).get (str (user_id ),[])
            except Exception :
                warns =[]
        warns =[ms_normalize_warn (w ,i +1 )for i ,w in enumerate (warns )]
        result ['warnings']=warns 
        result ['warn_count']=len (warns )
        # История модерации
        case =[]
        mf ='data/mod_data.json'
        if os .path .exists (mf ):
            try :
                with open (mf ,encoding ='utf-8')as f :mdata =json .load (f )
                case =[c for c in mdata .get ('case',{}).get (str (guild_id ),[])if str (c .get ('user_id'))==str (user_id )]
            except Exception :
                case =[]
        case =[ms_normalize_case (c ,i +1 )for i ,c in enumerate (case )]
        result ['case']=case 
        result ['cases']=case 
        result ['case_count']=len (case )
        return jsonify (result )


    @app .route ('/api/my-profile',methods =['GET'])
    @login_required 
    def api_my_profile ():
        import web .app as _app ;bot =_app .bot_instance 
        username =session .get ('username')
        result ={'username':username ,'display_name':username }
        # Данные участника
        mf ='data/members.json'
        if os .path .exists (mf ):
            with open (mf ,encoding ='utf-8')as f :members =json .load (f )
            for uid ,m in members .items ():
                if m .get ('username')==username :
                    result ['discord_id']=uid 
                    result ['avatar']=m .get ('avatar')
                    result ['display_name']=m .get ('display_name',username )
                    break 
                    # Предупреждения (все серверы)
        wf ='data/warnings.json'
        all_warns =[]
        if os .path .exists (wf )and result .get ('discord_id'):
            with open (wf ,encoding ='utf-8')as f :wdata =json .load (f )
            for gid ,users in wdata .items ():
                all_warns .extend (users .get (result ['discord_id'],[]))
        result ['warnings']=all_warns 
        # Баланс (первый сервер)
        if bot and result .get ('discord_id'):
            for guild in bot .guilds :
                bf =f'data/balance_{guild.id}.json'
                if os .path .exists (bf ):
                    with open (bf ,encoding ='utf-8')as f :bdata =json .load (f )
                    result ['balance']=bdata .get (result ['discord_id'],{}).get ('balance',0 )
                    break 
                    # Время в голосовых каналах
        if bot and result .get ('discord_id'):
            from cogs .voice_tracker import voice_seconds as _vs_secs
            for guild in bot .guilds :
                secs =_vs_secs (guild .id ,result ['discord_id'])
                if secs :
                    result ['voice_seconds']=secs
                    break
                    # Количество приглашений
        if bot and result .get ('discord_id'):
            for guild in bot .guilds :
                inf =f'data/invite_counts_{guild.id}.json'
                if os .path .exists (inf ):
                    with open (inf ,encoding ='utf-8')as f :idata =json .load (f )
                    result ['invites']=idata .get (result ['discord_id'],{}).get ('total',0 )
                    break 
        return jsonify (result )


    @app .route ('/api/my-birthday/<guild_id>',methods =['GET'])
    @login_required 
    def api_my_birthday_get (guild_id ):
        username =session .get ('username')
        mf ='data/members.json'
        discord_id =None 
        if os .path .exists (mf ):
            with open (mf ,encoding ='utf-8')as f :members =json .load (f )
            for uid ,m in members .items ():
                if m .get ('username')==username :
                    discord_id =uid ;break 
        if not discord_id :return jsonify ({})
        bf =f'data/birthdays_{guild_id}.json'
        if not os .path .exists (bf ):return jsonify ({})
        with open (bf ,encoding ='utf-8')as f :bdata =json .load (f )
        return jsonify (bdata .get (discord_id ,{}))


    @app .route ('/api/my-birthday/<guild_id>',methods =['POST'])
    @login_required 
    def api_my_birthday_save (guild_id ):
        username =session .get ('username')
        mf ='data/members.json'
        discord_id =None 
        if os .path .exists (mf ):
            with open (mf ,encoding ='utf-8')as f :members =json .load (f )
            for uid ,m in members .items ():
                if m .get ('username')==username :
                    discord_id =uid ;break 
        if not discord_id :return jsonify ({'error':'Пользователь не найден'}),404 
        d =request .get_json (silent =True )or {}
        day ,month ,year =d .get ('day'),d .get ('month'),d .get ('year')
        if not day or not month :return jsonify ({'error':'День и месяц обязательны'}),400 
        os .makedirs ('data',exist_ok =True )
        bf =f'data/birthdays_{guild_id}.json'
        bdata ={}
        if os .path .exists (bf ):
            with open (bf ,encoding ='utf-8')as f :bdata =json .load (f )
        entry ={'date':f'{int(month):02d}-{int(day):02d}','name':username }
        if year :entry ['year']=int (year )
        bdata [discord_id ]=entry 
        with open (bf ,'w',encoding ='utf-8')as f :json .dump (bdata ,f ,indent =2 ,ensure_ascii =False )
        return jsonify ({'ok':True })


    @app .route ('/api/birthdays/<guild_id>',methods =['GET'])
    @login_required 
    def api_birthdays_list (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        bf =f'data/birthdays_{guild_id}.json'
        if not os .path .exists (bf ):return jsonify ([])
        with open (bf ,encoding ='utf-8')as f :bdata =json .load (f )
        from datetime import datetime as _dt 
        now =_dt .utcnow ()
        today_num =now .month *100 +now .day 
        result =[]
        for uid ,info in bdata .items ():
            try :
                m ,d =map (int ,info ['date'].split ('-'))
                num =m *100 +d 
                diff =num -today_num 
                if diff <0 :diff +=1200 
                name =info .get ('name',uid )
                if bot :
                    guild =bot .get_guild (int (guild_id ))
                    if guild :
                        member =guild .get_member (int (uid ))
                        if member :name =member .display_name 
                result .append ({'name':name ,'date':info ['date'],'diff':diff })
            except Exception as _ex:
                _log.debug("api_birthdays_list(): подавлено: %s", _ex)
        result .sort (key =lambda x :x ['diff'])
        return jsonify (result )
