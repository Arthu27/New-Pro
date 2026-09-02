# -*- coding: utf-8 -*-
"""Данные участников: варны, дежурства, AFK, профили, дни рождения (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

from web.routes._common import (
    _run_async, _fetch_channel_msgs_async, _fetch_channel_msgs_sync,
    _load_ai_tickets, _notify_discord_sender, _fire_panel_notification,
    _process_action, _log, viewer_member, acl_action_allowed,
    ms_normalize_query, ms_member_match, ms_search_members, ms_member_payload,
    ms_normalize_warn, ms_normalize_case, calculate_ai_ticket_stats, _REPO_ROOT,
    demo_members_search, demo_member_payload,
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
        # Канонический источник ступеней — «Лестница наказаний» (ladder_panel /
        # cogs.warnings, ключ 'steps'). Старый формат 'thresholds' больше не пишем.
        from web .routes import ladder_panel as LP
        cfg =LP .load_cfg (str (guild_id ))
        return jsonify ({'steps':LP .steps_of (cfg )})


    @app .route ('/api/warn-config/<guild_id>',methods =['POST'])
    @login_required
    @role_required ('admin')
    def api_warn_config_save (guild_id ):
        # Ступени настраиваются только на /ladder. Запись через старый эндпоинт
        # запрещена, чтобы конфликтующий формат не перетирал 'steps'.
        return jsonify ({'ok':False ,
            'error':'Настройка ступеней переехала на страницу «Лестница наказаний» (/ladder)'}),409


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
        # int() на нечисловом id давал 500; остальные роуты панели так не делают.
        guild =bot .get_guild (int (guild_id ))if str (guild_id ).isdigit ()else None 
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
        # Канонический файл — data/mod_advanced_data.json: туда пишет бот
        # (cogs/moderation.py, _maybe_watchlist_after_mute при 2+ мьютах).
        # Раньше панель читала data/mod_data.json, где ключ watchlist не
        # создаёт никто, — страница «Наблюдение» была пуста ВСЕГДА, даже когда
        # фигуранты реально есть. mod_data.json оставлен запасным, чтобы
        # старые записи не потерялись.
        wl ={}
        for f in ('data/mod_advanced_data.json','data/mod_data.json'):
            if not os .path .exists (f ):continue 
            try :
                with open (f ,encoding ='utf-8')as fp :
                    data =json .load (fp )
            except Exception as _ex :
                _log .debug ('watchlist: не читается %s: %s',f ,_ex )
                continue 
            node =(data .get ('watchlist')or {}).get (str (guild_id ))or {}
            if node :
                wl =node 
                break 
        result =[]
        try :
            from web .routes ._common import name_map_for
            _nm =name_map_for (guild_id )
        except Exception as _ex :
            _nm ={}
        for uid ,info in wl .items ():
            if not isinstance (info ,dict ):continue 
            result .append ({'id':uid ,'name':_nm .get (uid )or info .get ('name')or uid ,
            'reason':info .get ('reason',''),'added_by':info .get ('added_by',''),
            'timestamp':info .get ('timestamp',''),'until':info .get ('until')})
        return jsonify (result )


    def _pick_member_item (m ):
        """Элемент для member-picker'а панели: {user_id, name, bot, avatar}."""
        p =ms_member_payload (m )
        return {
            'user_id':p .get ('id')or str (getattr (m ,'id','')),
            'name':p .get ('display_name')or p .get ('name')or str (getattr (m ,'id','')),
            'bot':bool (p .get ('is_bot')or getattr (m ,'bot',False )),
            'avatar':p .get ('avatar')or '',
        }

    def _pick_demo_item (m ):
        """Тот же формат для демо-участника (dict из DEMO_MEMBERS)."""
        return {
            'user_id':str (m .get ('id','')),
            'name':m .get ('display_name')or m .get ('name',''),
            'bot':bool (m .get ('bot',False )),
            'avatar':m .get ('avatar',''),
        }

    def _local_suggest (gid ,q ,offset ,limit ):
        """Локальный fallback для пикера: карта имён data/member_names_<gid>.json
        (+ демо в демо-режиме). Используется, когда бот подключён, но сервера или
        участников в его кэше нет (обрыв гейтвея, рестарт, нет intent) — чтобы
        страницы панели НЕ ломались 404 и показывали известные имена."""
        from web .routes ._common import name_map_for ,demo_members_search as _dms
        try :
            nm =name_map_for (str (gid ))
        except Exception :
            nm ={}
        pool =[{'user_id':str (u ),'name':n ,'bot':False ,'avatar':''}
               for u ,n in sorted (nm .items (),key =lambda kv :str (kv [1 ]).lower ())]
        if _app_demo ():
            pool +=[_pick_demo_item (m )for m in _dms ('',limit =500 )]
        qq =str (q or '').strip ().lower ()
        if qq :
            pool =[p for p in pool
                   if qq in p ['name'].lower ()or qq in p ['user_id']]
        # дедуп по user_id (имя-карта и демо могут пересечься)
        seen =set ();uniq =[]
        for p in pool :
            if p ['user_id']in seen :
                continue
            seen .add (p ['user_id']);uniq .append (p )
        return {'items':uniq [offset :offset +limit ],
                'has_more':len (uniq )>=offset +limit }

    def _app_demo ():
        try :
            import web .app as _am
            return _am ._demo_mode ()
        except Exception :
            return False

    @app .route ('/api/guild/<guild_id>/member-card/suggest',methods =['GET'])
    @login_required
    @role_required ('uye')
    def api_member_card_suggest (guild_id ):
        """Подсказки участника для пикеров панели (antifake, ladder, proofs,
        temp_moderation и т.д.). q — имя/ник/часть ID; offset — для «показать
        ещё». Без q отдаём первых участников кэша. Формат: {items:[...],has_more}.

        Никогда не отдаёт 404 для «своего» сервера: без бота — демо/имена,
        с ботом, но без сервера/участников в кэше — локальная карта имён.
        Точный ID, которого нет в кэше, догружается с Discord (fetch_member)."""
        try :
            limit =max (1 ,min (50 ,int (request .args .get ('limit',25 )or 25 )))
        except (TypeError ,ValueError ):
            limit =25
        try :
            offset =max (0 ,int (request .args .get ('offset',0 )or 0 ))
        except (TypeError ,ValueError ):
            offset =0
        q =ms_normalize_query (request .args .get ('q',''))

        import web .app as _app ;bot =_app .bot_instance
        # Нет бота (демо/превью) — отдаём демо-участников, чтобы пикер не 404.
        if not bot :
            demo =demo_members_search (q ,limit =limit +offset )
            items =[_pick_demo_item (m )for m in demo [offset :offset +limit ]]
            return jsonify ({'items':items ,'has_more':len (demo )>=offset +limit })

        gid =int (guild_id )if str (guild_id ).isdigit ()else 0
        guild =bot .get_guild (gid )if gid else None

        # Сначала — ПОЛНЫЙ состав из файла (services/member_store.py), а не
        # живой кэш discord.py. На большом сервере кэш наполняется постепенно,
        # и участник, которого там ещё нет, просто не находился; а при офлайн
        # боте пикер скатывался к карте имён. Файл бот правит событийно, так
        # что это самый полный и всегда доступный источник.
        window =limit +offset
        rows =[]
        stored_total =0
        if gid :
            try :
                from services import member_store as MS
                stored_total =MS .count (gid )
                if stored_total :
                    rows =(MS .find (gid ,q ,limit =window )if q
                           else MS .snapshot (gid ,offset ,limit ))
            except Exception as _ex :
                _log .debug ('member-card suggest: хранилище состава: %s',_ex )
        if rows :
            if q :
                total =len (rows )
                items =[_pick_demo_item (r )for r in rows [offset :offset +limit ]]
            else :
                total =stored_total
                items =[_pick_demo_item (r )for r in rows ]
            return jsonify ({'items':items ,'has_more':total >=offset +limit })

        # Бот подключён, но сервера в кэше нет — не 404, а локальные имена.
        if guild is None or not guild .members :
            return jsonify (_local_suggest (gid ,q ,offset ,limit ))

        if q :
            window =limit +offset
            matches =ms_search_members (guild .members ,q ,limit =window )
            # Точный/частичный ID, но в кэше участника нет — догружаем с Discord.
            if not matches and q .isdigit ()and offset ==0 :
                try :
                    fetched =_resolve_member_async (guild ,int (q ))
                    if fetched is not None :
                        matches =[fetched ]
                except Exception as _ex :
                    _log .debug ('member-card suggest fetch %s: %s',q ,_ex )
            total =len (matches )
            items =[_pick_member_item (m )for m in matches [offset :offset +limit ]]
        else :
            # Без запроса — стартовый список из кэша (по порядку).
            all_members =list (guild .members )
            total =len (all_members )
            items =[_pick_member_item (m )for m in all_members [offset :offset +limit ]]

        return jsonify ({'items':items ,'has_more':total >=offset +limit })


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


    @app .route ('/api/member-profile/<guild_id>/<user_id>/warn',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_member_profile_warn (guild_id ,user_id ):
        # Варн из профиля участника: идём через живой ког warnings, чтобы сработали
        # и хранение, и DM, и лог-канал, и авто-наказание по порогам.
        if not str (user_id ).isdigit ():
            return jsonify ({'error':'Некорректный ID участника.'}),400 
        import web .app as _app ;bot =_app .bot_instance 
        d =request .get_json (silent =True )or {}
        reason =(d .get ('reason')or '').strip ()or 'Не указана'
        proof =(d .get ('proof')or '').strip ()[:800]
        if proof and not proof .startswith (('http://','https://')):
            proof =''
        if _app ._demo_mode ():
            return jsonify ({'ok':True ,'demo':True ,'warn_id':1 ,'total':1 })
        if not bot :
            return jsonify ({'error':'Бот офлайн'}),503 
        guild =bot .get_guild (int (guild_id )if str (guild_id ).isdigit ()else 0 )
        if not guild :
            return jsonify ({'error':'Сервер не найден'}),404 
        _acl_m = viewer_member(bot, guild.id)
        if not acl_action_allowed(guild.id, _acl_m, 'warn'):
            return jsonify({'error': 'Нет права: «Варн» не разрешено вашей роли (настройка — «Права команд»)'}), 403

        try :
            member =_run_async (_resolve_member_async (guild ,int (user_id )))
        except Exception :
            member =None 
        if not member :
            return jsonify ({'error':'Участник не найден на сервере'}),404 
        # Модератор — владелец панели (Discord ID из сессии), иначе сам бот.
        moderator =guild .me 
        _did =str (session .get ('discord_id')or '')
        if _did .isdigit ():
            _md =guild .get_member (int (_did ))
            if _md :
                moderator =_md 
        cog =bot .get_cog ('warnings')or bot .get_cog ('Warnings')
        if cog :
            import asyncio as _asyncio 
            try :
                _fut =_asyncio .run_coroutine_threadsafe (cog .add_warning (member ,moderator ,reason ),bot .loop )
                warn_id ,total =_fut .result (timeout =15 )
            except Exception as _e :
                return jsonify ({'error':f'Не удалось выдать предупреждение: { _e }'}),500 
        else :
            # Ког не загружен — пишем зеркало data/warnings.json напрямую (та же схема).
            wf ='data/warnings.json'
            os .makedirs ('data',exist_ok =True )
            try :
                with open (wf ,encoding ='utf-8')as f :data =json .load (f )
                if not isinstance (data ,dict ):data ={}
            except Exception :
                data ={}
            _g =data .setdefault (str (guild_id ),{})
            _w =_g .get (str (user_id ),[])
            warn_id =len (_w )+1 
            _w .append ({'id':warn_id ,'reason':reason ,'mod':str (moderator ),
            'mod_id':str (moderator .id ),'timestamp':datetime .now (timezone .utc ).isoformat ()})
            _g [str (user_id )]=_w [-25 :]
            _tmp =wf +'.tmp'
            with open (_tmp ,'w',encoding ='utf-8')as f :json .dump (data ,f ,ensure_ascii =False ,indent =2 )
            os .replace (_tmp ,wf )
            total =len (_w )
        # Заказ владельца: доказательство к наказанию — прикрепляем ссылкой
        # к свежему варну (обе ветки выше пишут в data/warnings.json).
        if proof :
            try :
                wf2 ='data/warnings.json'
                if os .path .exists (wf2 ):
                    with open (wf2 ,encoding ='utf-8')as f2 :_wd =json .load (f2 )
                    _lst =_wd .get (str (guild_id ),{}).get (str (user_id ),[])
                    for _en in _lst :
                        if _en .get ('id')==warn_id :
                            _en ['proof']=proof ;break
                    _tmp2 =wf2 +'.tmp'
                    with open (_tmp2 ,'w',encoding ='utf-8')as f2 :json .dump (_wd ,f2 ,ensure_ascii =False ,indent =2 )
                    os .replace (_tmp2 ,wf2 )
            except Exception as _ex:
                _log .debug ("api_member_profile_warn(): proof-attach подавлен: %s",_ex )
        return jsonify ({'ok':True ,'warn_id':warn_id ,'total':total })


    @app .route ('/api/member-profile/<guild_id>/<user_id>/ban',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_member_profile_ban (guild_id ,user_id ):
        # Бан из профиля участника (кик из панели убран по решению владельца).
        if not str (user_id ).isdigit ():
            return jsonify ({'error':'Некорректный ID участника.'}),400 
        import web .app as _app ;bot =_app .bot_instance 
        d =request .get_json (silent =True )or {}
        reason =(d .get ('reason')or '').strip ()or 'Не указана'
        proof =(d .get ('proof')or '').strip ()[:800]
        if proof and not proof .startswith (('http://','https://')):
            proof =''
        if _app ._demo_mode ():
            return jsonify ({'ok':True ,'demo':True ,'proof':proof })
        if not bot :
            return jsonify ({'error':'Бот офлайн'}),503 
        guild =bot .get_guild (int (guild_id )if str (guild_id ).isdigit ()else 0 )
        if not guild :
            return jsonify ({'error':'Сервер не найден'}),404 
        _acl_m = viewer_member(bot, guild.id)
        if not acl_action_allowed(guild.id, _acl_m, 'ban'):
            return jsonify({'error': 'Нет права: «Бан» не разрешено вашей роли (настройка — «Права команд»)'}), 403

        try :
            member =_run_async (_resolve_member_async (guild ,int (user_id )))
        except Exception :
            member =None 
        if not member :
            return jsonify ({'error':'Участник не найден на сервере'}),404 
        if guild .owner_id ==member .id :
            return jsonify ({'error':'Нельзя забанить владельца сервера.'}),400 
        _uname =session .get ('username')or 'панель'
        # DM до бана — best effort: после бана написать уже не выйдет.
        try :
            import asyncio as _asyncio 
            async def _dm ():
                try :
                    await member .send (f'Вы забанены на сервере **{guild .name }**. Причина: {reason }'+(f'\nДоказательство: {proof }'if proof else ''))
                except Exception :
                    return 
            _asyncio .run_coroutine_threadsafe (_dm (),bot .loop ).result (timeout =5 )
        except Exception as _ex:
            _log .debug ("api_member_profile_ban(): DM не доставлено: %s",_ex )
        try :
            _run_async (guild .ban (member ,reason =f"[Панель] { _uname }: { reason }"))
        except Exception as _e :
            return jsonify ({'error':str (_e )}),400 
        _modcog =bot .get_cog ('Moderation')
        if _modcog :
            try :
                _modcog .save_case (guild .id ,'ban',str (user_id ),
                str (session .get ('discord_id')or _uname ),reason )
            except Exception as _ex:
                _log .debug ("api_member_profile_ban(): save_case подавлен: %s",_ex )
        # Доказательство к бану — в карточку дела (data/mod_data.json).
        if proof :
            try :
                mf3 ='data/mod_data.json'
                if os .path .exists (mf3 ):
                    with open (mf3 ,encoding ='utf-8')as f3 :_md =json .load (f3 )
                    _cs =_md .get ('case')or _md .get ('cases')or {}
                    for _en in reversed (_cs .get (str (guild_id ),[])):
                        if str (_en .get ('user_id'))==str (user_id ):
                            _en ['proof']=proof ;break
                    _tmp3 =mf3 +'.tmp'
                    with open (_tmp3 ,'w',encoding ='utf-8')as f3 :json .dump (_md ,f3 ,ensure_ascii =False ,indent =2 )
                    os .replace (_tmp3 ,mf3 )
            except Exception as _ex:
                _log .debug ("api_member_profile_ban(): proof-attach подавлен: %s",_ex )
        return jsonify ({'ok':True })


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
