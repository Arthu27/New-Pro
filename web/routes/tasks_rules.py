# -*- coding: utf-8 -*-
"""Таск-трекер сервера + правила (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

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


    @app .route ('/api/tasks')
    @login_required 
    @role_required ('mod')
    def api_get_tasks ():
        f ='data/tasks.json'
        if not os .path .exists (f ):return jsonify ([])
        with open (f )as fp :return jsonify (list (json .load (fp ).values ()))


    @app .route ('/api/tasks',methods =['POST'])
    @login_required 
    @role_required ('mod')
    def api_create_task ():
        data =request .get_json (silent =True )or {}
        title =(data .get ('title')or '').strip ()
        if not title :return jsonify ({'error':'Укажите название задачи'}),400 
        f ='data/tasks.json'
        os .makedirs ('data',exist_ok =True )
        tasks ={}
        if os .path .exists (f ):
            with open (f )as fp :tasks =json .load (fp )
        task_id =str (int (datetime.now(timezone.utc).timestamp ()))
        tasks [task_id ]={'id':task_id ,'title':title ,'assigned_to':data .get ('assigned_to',''),
        'priority':data .get ('priority','medium'),'status':'pending',
        'created_by':session .get ('username'),'created_at':datetime.now(timezone.utc).isoformat ()}
        with open (f ,'w')as fp :json .dump (tasks ,fp ,indent =2 ,ensure_ascii =False )
        return jsonify ({'success':True })


    @app .route ('/api/tasks/<task_id>',methods =['PATCH'])
    @login_required 
    @role_required ('mod')
    def api_update_task (task_id ):
        f ='data/tasks.json'
        if not os .path .exists (f ):return jsonify ({'error':'Не найдено'})
        with open (f )as fp :tasks =json .load (fp )
        if task_id in tasks :
            tasks [task_id ].update (request .get_json (silent =True )or {})
            with open (f ,'w')as fp :json .dump (tasks ,fp ,indent =2 )
        return jsonify ({'success':True })


    @app .route ('/api/tasks/<task_id>/delete',methods =['POST'])
    @login_required 
    @role_required ('mod')
    def api_delete_task (task_id ):
        f ='data/tasks.json'
        if not os .path .exists (f ):return jsonify ({'success':True })
        with open (f )as fp :tasks =json .load (fp )
        tasks .pop (task_id ,None )
        with open (f ,'w')as fp :json .dump (tasks ,fp ,indent =2 )
        return jsonify ({'success':True })


    def _norm_rule (r ):
        """Правило к каноничному виду {t, u, img, thumb}. Легаси-строки — только текст."""
        if isinstance (r ,str ):
            return {'t':r .strip (),'u':'','img':'','thumb':''}
        if isinstance (r ,dict ):
            return {
            't':str (r .get ('t')or r .get ('text')or r .get ('title')or '').strip (),
            'u':str (r .get ('u')or r .get ('url')or r .get ('link')or '').strip (),
            'img':str (r .get ('img')or r .get ('image')or r .get ('image_url')or '').strip (),
            'thumb':str (r .get ('thumb')or r .get ('thumbnail')or r .get ('thumbnail_url')or '').strip (),
            }
        return {'t':'','u':'','img':'','thumb':''}

    def _validate_rule_urls (rules ):
        """URL-ы только http(s). Возвращает (ok, ошибка)."""
        for i ,r in enumerate (rules ,1 ):
            for field ,label in (('u','ссылки'),('img','картинки'),('thumb','миниатюры')):
                v =r .get (field )or ''
                if v and not v .lower ().startswith (('http://','https://')):
                    return False ,f'Правило {i}: некорректный URL {label}'
        return True ,''

    @app .route ('/api/guild/<guild_id>/rules',methods =['GET','POST'])
    @login_required 
    @role_required ('admin')
    def api_rules (guild_id ):
        f =f'data/rules_{guild_id}.json'
        os .makedirs ('data',exist_ok =True )
        if request .method =='GET':
            if not os .path .exists (f ):return jsonify ([])
            try :
                with open (f ,encoding ='utf-8')as fp :raw =json .load (fp )
            except Exception :
                raw =[]
            if not isinstance (raw ,list ):raw =[]
            return jsonify ([_norm_rule (r )for r in raw ])
        raw =request .get_json (force =True ,silent =True )
        if not isinstance (raw ,list ):raw =[]
        rules =[_norm_rule (r )for r in raw ]
        ok ,err =_validate_rule_urls (rules )
        if not ok :
            return jsonify ({'error':err }),400 
        rules =[r for r in rules if r ['t']]
        with open (f ,'w',encoding ='utf-8')as fp :json .dump (rules ,fp ,indent =2 ,ensure_ascii =False )
        try :
            from web import _store as _wstore
            _wstore .invalidate_path (f )
        except Exception as _ex :
            _log.debug("api_rules(): invalidate подавлено: %s", _ex )
        return jsonify ({'success':True ,'rules':rules })


    @app .route ('/api/guild/<guild_id>/rules/publish',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_publish_rules (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio ,discord 
        data =request .get_json (silent =True )or {}
        ch_id =str (data .get ('channel_id')or '').strip ()
        raw =data .get ('rules')or []
        rules =[_norm_rule (r )for r in raw ]if isinstance (raw ,list )else []
        rules =[r for r in rules if r ['t']]
        if not ch_id :
            return jsonify ({'error':'Выберите канал публикации'}),400 
        if not rules :
            return jsonify ({'error':'Сначала добавьте правила'}),400 
        ok ,err =_validate_rule_urls (rules )
        if not ok :
            return jsonify ({'error':err }),400 
        # автосохранение — публикуем ровно то, что видим
        f =f'data/rules_{guild_id}.json'
        os .makedirs ('data',exist_ok =True )
        with open (f ,'w',encoding ='utf-8')as fp :json .dump (rules ,fp ,indent =2 ,ensure_ascii =False )
        try :
            from web import _store as _wstore
            _wstore .invalidate_path (f )
        except Exception as _ex :
            _log.debug("api_rules(): invalidate подавлено: %s", _ex )

        def build_embeds ():
            embeds =[]
            head =discord .Embed (
            title ="Правила сервера",
            description =f"Обновлённые правила сообщества — {len (rules )} пунктов. Нарушение правил ведёт к наказанию.",
            color =0x4f46e5 )
            head .set_footer (text ="Обновлено: " + datetime.now(timezone.utc).strftime ('%d.%m.%Y %H:%M')+ " (UTC)")
            embeds .append (head )
            for i ,r in enumerate (rules ,1 ):
                e =discord .Embed (color =0x4f46e5 )
                e .title =f"{i}. {r ['t'][:200]}"
                desc =r ['t']
                if r ['u']:
                    desc +="\n\nСсылка: [открыть](" + r ['u']+ ")"
                e .description =desc [:3900 ]
                if r ['thumb']:
                    e .set_thumbnail (url =r ['thumb'])
                if r ['img']:
                    e .set_image (url =r ['img'])
                e .set_footer (text =f"Правило {i} из {len (rules )}")
                embeds .append (e )
            return embeds 

        if not bot :
            if _app ._demo_mode ():
                # демо-предпросмотр без бота: публикация считается успешной,
                # в лог панели уходит отметка — кнопка видимо работает
                _fire_panel_notification ('rules',f"Правила опубликованы: {len (rules )} пунктов",f"Канал {ch_id } · демо-режим")
                return jsonify ({'success':True ,'demo':True ,'message':f"Демо-режим: правила готовы к публикации ({len (rules )} пунктов)"})
            return jsonify ({'error':'Бот офлайн — публикация недоступна'})
        embeds =build_embeds ()

        async def send ():
            ch =bot .get_channel (int (ch_id ))
            if not ch :
                raise RuntimeError ('Канал публикации не найден')
            for k in range (0 ,len (embeds ),10 ):
                await ch .send (embeds =embeds [k :k +10 ])

        try :
            asyncio .run_coroutine_threadsafe (send (),bot .loop ).result (timeout =20 )
        except Exception as _ex :
            _log.debug("api_publish_rules(): подавлено: %s", _ex)
            return jsonify ({'error':f"Не удалось опубликовать: {_ex }"[:200 ]}),502 
        _fire_panel_notification ('rules',f"Правила опубликованы: {len (rules )} пунктов",f"Канал {ch_id }")
        return jsonify ({'success':True ,'message':f"Опубликовано правил: {len (rules )}"})
