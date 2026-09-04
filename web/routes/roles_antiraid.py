# -*- coding: utf-8 -*-
"""Цветные роли, антирейд, rejoin, бейджи (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

from web.routes._common import (
    _run_async, _fetch_channel_msgs_async, _fetch_channel_msgs_sync,
    _notify_discord_sender, _fire_panel_notification,
    _process_action, _log, _live_publish,
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


    @app .route ('/api/guild/<guild_id>/color-roles',methods =['GET','POST'])
    @login_required 
    def api_color_roles (guild_id ):
        """Цветные роли: GET — список из файла; POST — сохранить (admin+)."""
        f =f'data/color_roles_{guild_id}.json'
        if request .method =='GET':
            if not os .path .exists (f ):return jsonify ([])
            try :
                with open (f ,encoding ='utf-8')as fp :return jsonify (json .load (fp ))
            except Exception :
                return jsonify ([])
        # POST: сохранение списка цветов (без публикации)
        import web .app as _appm
        if _appm .ROLES .get (session .get ('role'),-1 )<_appm .ROLES .get ('admin',2 ):
            return jsonify ({'error':'Нет доступа'}),403 
        data =request .get_json (silent =True )or {}
        colors =data .get ('colors')if isinstance (data .get ('colors'),list )else []
        clean =[]
        for c in colors :
            if not isinstance (c ,dict ):continue 
            name =str (c .get ('name')or '').strip ()[:40 ]
            hexv =str (c .get ('hex')or '').strip ()
            import re as _re 
            if not name or not _re .match (r'^#[0-9a-fA-F]{6}$',hexv ):
                continue 
            clean .append ({'name':name ,'hex':hexv .lower (),'emoji':str (c .get ('emoji')or '').strip ()[:16 ]})
        os .makedirs ('data',exist_ok =True )
        with open (f ,'w',encoding ='utf-8')as fp :json .dump (clean ,fp ,indent =2 ,ensure_ascii =False )
        return jsonify ({'success':True ,'colors':clean })


    @app .route ('/api/guild/<guild_id>/color-roles/publish',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_publish_color_roles (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio ,discord 
        data =request .get_json (silent =True )or {}
        ch_id =str (data .get ('channel_id')or '').strip ()
        colors =data .get ('colors')if isinstance (data .get ('colors'),list )else []
        import re as _re 
        clean =[]
        for c in colors :
            if not isinstance (c ,dict ):continue 
            name =str (c .get ('name')or '').strip ()[:40 ]
            hexv =str (c .get ('hex')or '').strip ()
            if not name or not _re .match (r'^#[0-9a-fA-F]{6}$',hexv ):
                continue 
            clean .append ({'name':name ,'hex':hexv .lower (),'emoji':str (c .get ('emoji')or '').strip ()[:16 ]})
        if not ch_id :
            return jsonify ({'error':'Выберите канал панели'}),400 
        if not clean :
            return jsonify ({'error':'Сначала добавьте хотя бы один цвет'}),400 
        if not ch_id .isdigit ():
            # int(ch_id) внутри корутины давал «invalid literal for int()»
            return jsonify ({'error':'Неверный ID канала'}),400 
        if not str (guild_id ).isdigit ():
            return jsonify ({'error':'Неверный ID сервера'}),400 
        f =f'data/color_roles_{guild_id}.json'
        os .makedirs ('data',exist_ok =True )
        with open (f ,'w',encoding ='utf-8')as fp :json .dump (clean ,fp ,indent =2 ,ensure_ascii =False )
        if not bot :
            if _app ._demo_mode ():
                _fire_panel_notification ('color_roles',f"Цветные роли опубликованы: {len (clean )} цветов",f"Канал {ch_id } · демо-режим")
                return jsonify ({'success':True ,'demo':True ,'message':f"Демо-режим: {len (clean )} цветов готовы — при живом боте роли создадутся в Discord"})
            return jsonify ({'error':'Бот офлайн — публикация недоступна'}),503 

        failed =[]

        async def send ():
            guild =bot .get_guild (int (guild_id ))
            ch =bot .get_channel (int (ch_id ))
            if not guild :
                raise RuntimeError ('Сервер не найден у бота')
            if not ch :
                raise RuntimeError ('Канал панели не найден — возможно, бот его не видит')
            perms =ch .permissions_for (guild .me )
            if not perms .send_messages :
                raise RuntimeError ('У бота нет права писать в этот канал')
            for c in clean :
                role =discord .utils .get (guild .roles ,name =f"Цвет · {c['name']}")
                if not role :
                    color_hex =c ['hex'].lstrip ('#')
                    try :
                        await guild .create_role (name =f"Цвет · {c['name']}",color =discord .Color (int (color_hex ,16 )))
                    except Exception as _ex :
                        # раньше проглатывали молча и всё равно рапортовали
                        # «Опубликовано цветов: N», хотя роли не создались
                        _log.debug("send(): роль %s: %s", c['name'], _ex )
                        failed .append (c ['name'])
            desc ='\n'.join ([f"{c.get('emoji')or '🎨'} **{c['name']}** — `{c['hex']}`"for c in clean ])
            embed =discord .Embed (title ="Цветные роли",description =desc +"\n\nЧтобы получить нужный цвет, используйте команду `/color`!",color =0xdc143c )
            await ch .send (embed =embed )

        try :
            asyncio .run_coroutine_threadsafe (send (),bot .loop ).result (timeout =25 )
        except Exception as _ex :
            msg =str (_ex )
            if 'Forbidden' in msg or 'Missing Access' in msg :
                msg ='Discord запретил отправку: у бота нет прав на этот канал'
            return jsonify ({'error':f"Не удалось опубликовать: {msg }"[:200 ]}),502 
        _fire_panel_notification ('color_roles',f"Цветные роли опубликованы: {len (clean )} цветов",f"Канал {ch_id }")
        _live_publish (guild_id ,'roles')
        if failed :
            return jsonify ({'success':True ,'partial':True ,'message':
                f"Панель отправлена, но не удалось создать роли: {', '.join (failed )}. "
                'Проверьте право «Управлять ролями» и место моей роли в иерархии'})
        return jsonify ({'success':True ,'message':f"Опубликовано цветов: {len (clean )}"})


    @app .route ('/api/guild/<guild_id>/antiraid',methods =['GET','POST'])
    @login_required 
    @role_required ('admin')
    def api_antiraid_settings (guild_id ):
        f =f'data/antiraid_{guild_id}.json'
        if request .method =='GET':
            if not os .path .exists (f ):return jsonify ({'whitelist':[],'recent_events':[]})
            with open (f )as fp :return jsonify (json .load (fp ))
        data =request .get_json (silent =True )or {}
        existing ={}
        if os .path .exists (f ):
            with open (f )as fp :existing =json .load (fp )
            # recent_events: если есть в payload — использовать, иначе сохранить с диска
        if 'recent_events'not in data :
            data ['recent_events']=existing .get ('recent_events',[])
            # whitelist: принимать только валидные числовые user_id из 17-22 цифр
        wl =data .get ('whitelist')
        if not isinstance (wl ,list ):
            wl =existing .get ('whitelist',[])
        else :
            wl =[str (x )for x in wl if isinstance (x ,(str ,int ))
            and str (x ).isdigit ()and 17 <=len (str (x ))<=22 ]
            # Убрать повторы, сохранить порядок
        seen =set ()
        wl_clean =[]
        for x in wl :
            if x not in seen :
                seen .add (x )
                wl_clean .append (x )
                # Maks 500 user limit
        data ['whitelist']=wl_clean [:500 ]
        # raid_action her zaman 'alert' — diгer deгerleri отклонить
        data ['raid_action']='alert'
        # Канал тревоги настраивается в «Каналах и маршрутах» (тот же файл,
        # ключ alert_channel_id): здесь его не принимаем, чтобы пустой POST
        # со страницы анти-рейда не затёр выбранный канал.
        data ['alert_channel_id']=existing .get ('alert_channel_id')
        # Numeric alanlarыn tipini koru
        try :
            data ['join_threshold']=max (2 ,min (50 ,int (data .get ('join_threshold',5 ))))
            data ['join_window']=max (5 ,min (120 ,int (data .get ('join_window',10 ))))
            data ['min_age']=max (0 ,min (365 ,int (data .get ('min_age',5 ))))
        except (TypeError ,ValueError ):
            data ['join_threshold']=5 
            data ['join_window']=10 
            data ['min_age']=5 
            # Boolean alanlar
        for bkey in ('join_raid','bot_protection','webhook_protection',
        'delete_protection','age_filter'):
            data [bkey ]=bool (data .get (bkey ,False ))
        with open (f ,'w')as fp :json .dump (data ,fp ,indent =2 ,ensure_ascii =False )
        # Живой пуш: ког antiraid в боте слушает шину и перечитает конфиг сразу,
        # без ожидания 20-секундного watcher-тика.
        _live_publish (guild_id ,'guardian')
        _live_publish (guild_id ,'security')
        return jsonify ({'success':True })


        # ── RE-JOIN ROLES API ────────────────────────────────────────────────────

    @app .route ('/api/guild/<guild_id>/rejoin-roles',methods =['GET','POST'])
    @login_required 
    @role_required ('admin')
    def api_rejoin_roles (guild_id ):
        f =f'data/rejoin_{guild_id}.json'
        if request .method =='GET':
            if not os .path .exists (f ):
                return jsonify ({'enabled':False ,'tracked_role_ids':[],'leave_log':[]})
            try :
                with open (f ,'r',encoding ='utf-8')as fp :
                    d =json .load (fp )
            except Exception :
                d ={'enabled':False ,'tracked_role_ids':[],'leave_log':[]}
            d .setdefault ('enabled',False )
            d .setdefault ('tracked_role_ids',[])
            d .setdefault ('leave_log',[])
            return jsonify (d )

        data =request .get_json (silent =True )or {}
        enabled =bool (data .get ('enabled',False ))
        # tracked_role_ids: принимать только числовые строки, макс 50
        raw_ids =data .get ('tracked_role_ids',[])
        if not isinstance (raw_ids ,list ):
            raw_ids =[]
        seen =set ()
        clean_ids =[]
        for x in raw_ids :
            s =str (x )
            if s .isdigit ()and 17 <=len (s )<=22 and s not in seen :
                seen .add (s )
                clean_ids .append (s )
            if len (clean_ids )>=50 :
                break 
                # Кросс-проверка со списком ролей бота — отсутствующие роли могли быть удалены на сервереr
        import web .app as _app 
        bot =_app .bot_instance 
        guild =None 
        if bot :
            guild =bot .get_guild (int (guild_id ))
            if guild is None :
                for g in bot .guilds :
                    if str (g .id )==str (guild_id ):
                        guild =g 
                        break 

        if guild is not None :
            valid_ids =[rid for rid in clean_ids if guild .get_role (int (rid ))is not None ]
        else :
        # Bot offline veya guild bulunamadы — tюm ID'leri принять et
            valid_ids =clean_ids 

            # leave_log korunuyor (cog tarafыndan yazыlыr)
        existing ={}
        if os .path .exists (f ):
            try :
                with open (f ,'r',encoding ='utf-8')as fp :
                    existing =json .load (fp )
            except Exception :
                existing ={}
        leave_log =data .get ('leave_log')
        if not isinstance (leave_log ,list ):
            leave_log =existing .get ('leave_log',[])
            # leave_log'u 200 ile sыnыrla
        leave_log =leave_log [-200 :]
        result ={
        'enabled':enabled ,
        'tracked_role_ids':valid_ids ,
        'leave_log':leave_log ,
        }
        os .makedirs ('data',exist_ok =True )
        with open (f ,'w',encoding ='utf-8')as fp :
            json .dump (result ,fp ,indent =2 ,ensure_ascii =False )
        return jsonify ({'success':True ,'tracked_count':len (valid_ids )})


        # ── API ЗНАЧКОВ ────────────────────────────────────────────────────────────

    @app .route ('/api/guild/<guild_id>/badges')
    @login_required 
    @role_required ('mod')
    def api_guild_badges (guild_id ):
        f =f'data/badges_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ([])
        with open (f ,'r',encoding ='utf-8')as fp :
            data =json .load (fp )
        result =[]
        for uid ,u in data .items ():
            if u .get ('badges'):
                result .append ({'user_id':uid ,'name':u .get ('name',uid ),'badges':u ['badges'],'messages':u .get ('messages',0 )})
        result .sort (key =lambda x :len (x ['badges']),reverse =True )
        return jsonify (result [:50 ])
