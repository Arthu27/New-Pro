# -*- coding: utf-8 -*-
"""Массовые операции и заметки по участникам (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

from web.routes._common import (
    _panel_limit_deny, _panel_limit_record,
    _safe_json_obj,
    _run_async, _fetch_channel_msgs_async, _fetch_channel_msgs_sync,
    _notify_discord_sender, _fire_panel_notification,
    _process_action, _log, viewer_member, acl_action_allowed,
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


    @app .route ('/api/member-notes')
    @login_required 
    @role_required ('mod')
    def api_all_member_notes ():
        f ='data/member_notes.json'
        if not os .path .exists (f ):return jsonify ([])
        try :
            with open (f ,encoding ='utf-8')as fp :data =json .load (fp )
        except (json .JSONDecodeError ,ValueError ):
            return jsonify ([])
        return jsonify ([{'id':k ,'name':v .get ('name',k ),'avatar':v .get ('avatar',''),'notes':v .get ('notes',[])}for k ,v in data .items ()if v .get ('notes')])


    @app .route ('/api/member-notes/<member_id>')
    @login_required 
    @role_required ('mod')
    def api_member_notes (member_id ):
        f ='data/member_notes.json'
        if not os .path .exists (f ):return jsonify ([])
        try :
            with open (f ,encoding ='utf-8')as fp :data =json .load (fp )
        except (json .JSONDecodeError ,ValueError ):
            return jsonify ([])
        return jsonify (data .get (member_id ,{}).get ('notes',[]))


    @app .route ('/api/member-notes/<member_id>/add',methods =['POST'])
    @login_required 
    @role_required ('mod')
    def api_add_member_note (member_id ):
        import web .app as _app ;bot =_app .bot_instance 
        f ='data/member_notes.json'
        data ={}
        if os .path .exists (f ):
            try :
                with open (f ,encoding ='utf-8')as fp :data =json .load (fp )
            except (json .JSONDecodeError ,ValueError ):
                data ={}
        if member_id not in data :
            name =member_id 
            avatar =''
            if bot :
                for g in bot .guilds :
                    m =g .get_member (int (member_id ))
                    if m :
                        name =m .display_name 
                        avatar =str (m .display_avatar .url )
                        break 
            data [member_id ]={'name':name ,'avatar':avatar ,'notes':[]}
        note ={'id':str (int (datetime.now(timezone.utc).timestamp ())),'text':_safe_json_obj().get ('text',''),
        'author':session .get ('username'),'created_at':datetime.now(timezone.utc).isoformat ()}
        data [member_id ]['notes'].append (note )
        with open (f ,'w',encoding ='utf-8')as fp :json .dump (data ,fp ,indent =2 ,ensure_ascii =False )
        return jsonify ({'success':True })


    @app .route ('/api/member-notes/<member_id>/<note_id>/delete',methods =['POST'])
    @login_required 
    @role_required ('mod')
    def api_delete_member_note (member_id ,note_id ):
        f ='data/member_notes.json'
        if not os .path .exists (f ):return jsonify ({'success':True })
        try :
            with open (f ,encoding ='utf-8')as fp :data =json .load (fp )
        except (json .JSONDecodeError ,ValueError ):
            return jsonify ({'success':True })
        if member_id in data :
            data [member_id ]['notes']=[n for n in data [member_id ]['notes']if n ['id']!=note_id ]
        with open (f ,'w',encoding ='utf-8')as fp :json .dump (data ,fp ,indent =2 ,ensure_ascii =False )
        return jsonify ({'success':True })


    @app .route ('/api/guild/<guild_id>/purge',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_purge (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio 
        if not bot :return jsonify ({'error':'Бот офлайн'})
        data =_safe_json_obj()
        result ={'count':0 }
        _acl_m = viewer_member(bot, int(guild_id))
        if not acl_action_allowed(int(guild_id), _acl_m, 'purge'):
            return jsonify({'error': 'Нет права: «Очистка сообщений» не разрешено вашей роли (настройка — «Права команд»)'}), 403
        # Лимит «чистка»: 1 хит за операцию, не за каждое сообщение.
        # Раньше в квоту писали count — первая чистка 25 сообщений при
        # лимите 10 сразу давала «Лимит исчерпан … использовано 0».
        try :
            _purge_amt =max (1 ,min (int ((data .get ('count')or 10 )),200 ))
        except (TypeError ,ValueError ):
            _purge_amt =10
        _lim_denied =_panel_limit_deny (bot ,int (guild_id ),_acl_m ,'clear',1)
        if _lim_denied :
            return jsonify ({'error':_lim_denied }),429

        _need =[k for k in ('channel_id',) if not str (data .get (k ,'')or '' ).strip ()]
        if _need :return jsonify ({'error':'Не указано: '+', '.join (_need )}),400 
        async def do ():
            ch =bot .get_channel (int (data ['channel_id']))
            if ch :
                deleted =await (ch .purge (limit =_purge_amt ))
                result ['count']=len (deleted )
        asyncio .run_coroutine_threadsafe (do (),bot .loop ).result (timeout =30 )
        try :
            if int (result .get ('count')or 0 )>0 :
                _panel_limit_record (int (guild_id ),_acl_m ,'clear',1)
        except Exception as _rex :
            _log .debug ('purge record: %s',_rex )
        return jsonify ({'success':True ,'count':result ['count']})


    @app .route ('/api/guild/<guild_id>/bulk-roles',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_bulk_role (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio ,discord 
        if not bot :return jsonify ({'error':'Бот офлайн'})
        data =_safe_json_obj()
        _need =[k for k in ('target_role', 'action_role', 'action') if not str (data .get (k ,'')or '' ).strip ()]
        if _need :return jsonify ({'error':'Не указано: '+', '.join (_need )}),400 
        result ={'count':0 }
        _acl_m = viewer_member(bot, int(guild_id))
        if not acl_action_allowed(int(guild_id), _acl_m, 'roles'):
            return jsonify({'error': 'Нет права: «Роли» не разрешено вашей роли (настройка — «Права команд»)'}), 403
        # mass-смена ролей не лимитируется: ключа «роли» в лимитах нет

        _need =[k for k in ('target_role', 'action_role', 'action') if not str (data .get (k ,'')or '' ).strip ()]
        if _need :return jsonify ({'error':'Не указано: '+', '.join (_need )}),400 
        async def do ():
            guild =bot .get_guild (int (guild_id ))
            target_role =guild .get_role (int (data ['target_role']))
            action_role =guild .get_role (int (data ['action_role']))
            if not target_role or not action_role :return 
            for member in target_role .members :
                try :
                    if data ['action']=='add':await (member .add_roles (action_role ))
                    else :await (member .remove_roles (action_role ))
                    result ['count']+=1 
                except Exception as _ex:
                    _log.debug("do(): подавлено: %s", _ex)
        asyncio .run_coroutine_threadsafe (do (),bot .loop ).result (timeout =60 )
        return jsonify ({'success':True ,'count':result ['count']})


    @app .route ('/api/guild/<guild_id>/bulk-dm',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_bulk_dm (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio ,discord 
        if not bot :return jsonify ({'error':'Бот офлайн'})
        data =_safe_json_obj()
        _need =[k for k in ('role_id', 'message') if not str (data .get (k ,'')or '' ).strip ()]
        if _need :return jsonify ({'error':'Не указано: '+', '.join (_need )}),400 
        result ={'count':0 }
        async def do ():
            guild =bot .get_guild (int (guild_id ))
            role =guild .get_role (int (data ['role_id']))
            if not role :return 
            embed =discord .Embed (title ="📢 Объявление",description =data ['message'],color =0xdc143c )
            embed .set_footer (text ="Hakumo Panel",icon_url =bot .user .display_avatar .url )
            for member in role .members :
                try :
                    await (member .send (embed =embed ))
                    result ['count']+=1 
                except Exception as _ex:
                    _log.debug("do(): подавлено: %s", _ex)
        asyncio .run_coroutine_threadsafe (do (),bot .loop ).result (timeout =120 )
        return jsonify ({'success':True ,'count':result ['count']})


    @app .route ('/api/guild/<guild_id>/bulk-mute',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_bulk_mute (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio ,discord 
        from datetime import timedelta 
        if not bot :return jsonify ({'error':'Бот офлайн'})
        data =_safe_json_obj()
        result ={'count':0 }
        _acl_m = viewer_member(bot, int(guild_id))
        if not acl_action_allowed(int(guild_id), _acl_m, 'mute'):
            return jsonify({'error': 'Нет права: «Мут» не разрешено вашей роли (настройка — «Права команд»)'}), 403
        _lim_denied =_panel_limit_deny (bot ,int (guild_id ),_acl_m ,'mute')
        if _lim_denied :
            return jsonify ({'error':_lim_denied }),429

        _need =[k for k in ('role_id',) if not str (data .get (k ,'')or '' ).strip ()]
        if _need :return jsonify ({'error':'Не указано: '+', '.join (_need )}),400 
        async def do ():
            guild =bot .get_guild (int (guild_id ))
            role =guild .get_role (int (data ['role_id']))
            if not role :return 
            duration =int (data .get ('duration',60 ))
            # ИЕРАРХИЯ: персонал не мутит персонал своего уровня и выше —
            # таких молча пропускаем (bulk по роли, а не по человеку)
            from services .staff_hierarchy import check as _hchk
            _sess_role =session .get ('role')
            for member in role .members :
                _hok ,_hdeny ,_ ,_ =_hchk (guild ,_acl_m ,member ,'mute',
                session_role =_sess_role )
                if not _hok :
                    continue
                try :
                    await (member .timeout (datetime.now(timezone.utc)+timedelta (minutes =duration ),reason ='Bulk mute'))
                    result ['count']+=1 
                except Exception as _ex:
                    _log.debug("do(): подавлено: %s", _ex)
        asyncio .run_coroutine_threadsafe (do (),bot .loop ).result (timeout =120 )
        return jsonify ({'success':True ,'count':result ['count']})


    @app .route ('/api/guild/<guild_id>/bulk-kick',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_bulk_kick (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio ,discord 
        if not bot :return jsonify ({'error':'Бот офлайн'})
        data =_safe_json_obj()
        result ={'count':0 }
        _acl_m = viewer_member(bot, int(guild_id))
        if not acl_action_allowed(int(guild_id), _acl_m, 'kick'):
            return jsonify({'error': 'Нет права: «Кик» не разрешено вашей роли (настройка — «Права команд»)'}), 403
        _lim_denied =_panel_limit_deny (bot ,int (guild_id ),_acl_m ,'kick')
        if _lim_denied :
            return jsonify ({'error':_lim_denied }),429

        _need =[k for k in ('role_id',) if not str (data .get (k ,'')or '' ).strip ()]
        if _need :return jsonify ({'error':'Не указано: '+', '.join (_need )}),400 
        async def do ():
            guild =bot .get_guild (int (guild_id ))
            role =guild .get_role (int (data ['role_id']))
            if not role :return 
            # ИЕРАРХИЯ: не кикаем персонал своего уровня и выше
            from services .staff_hierarchy import check as _hchk
            _sess_role =session .get ('role')
            for member in role .members :
                _hok ,_hdeny ,_ ,_ =_hchk (guild ,_acl_m ,member ,'kick',
                session_role =_sess_role )
                if not _hok :
                    continue
                try :
                    await (member .kick (reason ='Bulk kick'))
                    result ['count']+=1 
                except Exception as _ex:
                    _log.debug("do(): подавлено: %s", _ex)
        asyncio .run_coroutine_threadsafe (do (),bot .loop ).result (timeout =120 )
        return jsonify ({'success':True ,'count':result ['count']})


    @app .route ('/api/guild/<guild_id>/bulk-ban',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_bulk_ban (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio ,discord 
        if not bot :return jsonify ({'error':'Бот офлайн'})
        data =_safe_json_obj()
        result ={'count':0 }
        _acl_m = viewer_member(bot, int(guild_id))
        if not acl_action_allowed(int(guild_id), _acl_m, 'ban'):
            return jsonify({'error': 'Нет права: «Бан» не разрешено вашей роли (настройка — «Права команд»)'}), 403
        _lim_denied =_panel_limit_deny (bot ,int (guild_id ),_acl_m ,'ban')
        if _lim_denied :
            return jsonify ({'error':_lim_denied }),429

        _need =[k for k in ('role_id',) if not str (data .get (k ,'')or '' ).strip ()]
        if _need :return jsonify ({'error':'Не указано: '+', '.join (_need )}),400 
        async def do ():
            guild =bot .get_guild (int (guild_id ))
            role =guild .get_role (int (data ['role_id']))
            if not role :return 
            # ИЕРАРХИЯ: не банрим персонал своего уровня и выше
            from services .staff_hierarchy import check as _hchk
            _sess_role =session .get ('role')
            for member in role .members :
                _hok ,_hdeny ,_ ,_ =_hchk (guild ,_acl_m ,member ,'ban',
                session_role =_sess_role )
                if not _hok :
                    continue
                try :
                    await (guild .ban (member ,reason ='Bulk ban'))
                    result ['count']+=1 
                except Exception as _ex:
                    _log.debug("do(): подавлено: %s", _ex)
        asyncio .run_coroutine_threadsafe (do (),bot .loop ).result (timeout =180 )
        return jsonify ({'success':True ,'count':result ['count']})


        # ── WARN CONFIG API ───────────────────────────────────────────────────────

    @app .route ('/api/guild/<guild_id>/warn-config',methods =['GET','POST'])
    @login_required
    @role_required ('admin')
    def api_warn_config (guild_id ):
        # Канонический писатель ступеней — «Лестница наказаний» (ladder_panel,
        # ключ 'steps'). Сырую запись в файл здесь больше не делаем, чтобы
        # формат 'thresholds' не перетирал боевой 'steps'.
        from web .routes import ladder_panel as LP
        if request .method =='GET':
            cfg =LP .load_cfg (str (guild_id ))
            return jsonify ({'steps':LP .steps_of (cfg )})
        return jsonify ({'success':False ,
            'error':'Настройка ступеней переехала на страницу «Лестница наказаний» (/ladder)'}),409


        # ── WARN DM НАСТРОЙКА ─────────────────────────────────────────────────────────

    @app .route ('/api/guild/<guild_id>/warn-dm',methods =['GET','POST'])
    @login_required 
    @role_required ('admin')
    def api_warn_dm (guild_id ):
        f =f'data/warn_dm_{guild_id}.json'
        if request .method =='GET':
            if not os .path .exists (f ):
                return jsonify ({'message':''})
            with open (f ,'r',encoding ='utf-8')as fp :
                return jsonify (json .load (fp ))
        data =_safe_json_obj()
        os .makedirs ('data',exist_ok =True )
        with open (f ,'w',encoding ='utf-8')as fp :
            json .dump ({'message':data .get ('message','')},fp ,ensure_ascii =False )
        return jsonify ({'success':True })
