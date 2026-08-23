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
        """Правило к каноничному виду {t, u, img, thumb, img_gen}.

        img_gen — тема авто-картинки ('' = не генерировать, берётся URL из img);
        легаси-строки — только текст, всё остальное пустое.
        """
        def _theme_of (raw ):
            from services import banner_gen as _bg
            raw = str (raw or '').strip ().lower ()
            return raw if raw in _bg .THEMES else ''
        if isinstance (r ,str ):
            return {'t':r .strip (),'u':'','img':'','thumb':'','img_gen':''}
        if isinstance (r ,dict ):
            return {
            't':str (r .get ('t')or r .get ('text')or r .get ('title')or '').strip (),
            'u':str (r .get ('u')or r .get ('url')or r .get ('link')or '').strip (),
            'img':str (r .get ('img')or r .get ('image')or r .get ('image_url')or '').strip (),
            'thumb':str (r .get ('thumb')or r .get ('thumbnail')or r .get ('thumbnail_url')or '').strip (),
            'img_gen':_theme_of (r .get ('img_gen')or r .get ('auto_img')or ''),
            }
        return {'t':'','u':'','img':'','thumb':'','img_gen':''}

    def _fix_url (v ):
        """Ссылка к рабочему виду: без протокола — доклеиваем https://.

        Пользователи часто вставляют «discord.gg/x» — жёсткий 400
        блокировал публикацию; теперь ссылка чинится автоматически.
        """
        v =str (v or '').strip ()
        if not v :
            return ''
        if v .lower ().startswith (('http://','https://')):
            return v
        if v .lower ().startswith ('javascript:')or v .lower ().startswith ('data:'):
            return ''   # опасные схемы отбрасываем полностью
        return 'https://' + v

    def _validate_rule_urls (rules ):
        """URL-ы только http(s). Возвращает (ok, ошибка)."""
        for i ,r in enumerate (rules ,1 ):
            for field ,label in (('u','ссылки'),('img','картинки'),('thumb','миниатюры')):
                v =r .get (field )or ''
                if v and not v .lower ().startswith (('http://','https://')):
                    return False ,f'Правило {i}: некорректный URL {label} — укажите полный адрес (https://…)'
        return True ,''

    def _normalize_rules_urls (rules ):
        """Прогнать _fix_url по всем ссылкам/картинкам правил (мутация копий)."""
        out =[]
        for r in rules :
            rr =dict (r )
            for f in ('u','img','thumb'):
                if rr .get (f ):
                    rr [f ]=_fix_url (rr [f ])
            out .append (rr )
        return out

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
        rules =_normalize_rules_urls ([_norm_rule (r )for r in raw ])
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


    def _rules_meta_path (guild_id ):
        return f'data/rules_meta_{guild_id}.json'

    def _load_rules_meta (guild_id ):
        """Настройки публикации: заголовок, вступление, цвет, канал,
        тема авто-картинок (последняя выбранная в редакторе)."""
        f =_rules_meta_path (guild_id )
        meta ={'title':'Правила сервера','intro':'Нарушение правил ведёт к наказанию.',
               'color':'4f46e5','channel_id':'','img_theme':'violet'}
        try :
            if os .path .exists (f ):
                with open (f ,encoding ='utf-8')as fp :
                    rawm =json .load (fp )
                if isinstance (rawm ,dict ):
                    meta .update ({k :v for k ,v in rawm .items ()if k in meta })
        except Exception as _ex :
            _log.debug("_load_rules_meta(): подавлено: %s", _ex)
        return meta

    def _save_rules_meta (guild_id ,meta ):
        f =_rules_meta_path (guild_id )
        os .makedirs ('data',exist_ok =True )
        with open (f ,'w',encoding ='utf-8')as fp :
            json .dump (meta ,fp ,indent =2 ,ensure_ascii =False )

    @app .route ('/api/guild/<guild_id>/rules/meta',methods =['GET','POST'])
    @login_required 
    @role_required ('admin')
    def api_rules_meta (guild_id ):
        meta =_load_rules_meta (guild_id )
        if request .method =='GET':
            return jsonify ({'success':True ,'meta':meta })
        data =request .get_json (silent =True )or {}
        if 'title'in data :
            meta ['title']=str (data ['title']or '').strip ()[:200 ]or 'Правила сервера'
        if 'intro'in data :
            meta ['intro']=str (data ['intro']or '').strip ()[:1800 ]
        if 'color'in data :
            c =str (data ['color']or '').strip ().lstrip ('#')
            import re as _re 
            if _re .match (r'^[0-9a-fA-F]{6}$',c ):
                meta ['color']=c .lower ()
        if 'channel_id'in data :
            meta ['channel_id']=str (data ['channel_id']or '').strip ()
        if 'img_theme'in data :
            from services import banner_gen as _bg
            th =str (data ['img_theme']or '').strip ().lower ()
            if th in _bg .THEMES :
                meta ['img_theme']=th
        _save_rules_meta (guild_id ,meta )
        return jsonify ({'success':True ,'meta':meta })

    @app .route ('/api/guild/<guild_id>/rules/banner')
    @login_required
    @role_required ('admin')
    def api_rules_banner (guild_id ):
        """Предпросмотр авто-картинки правила — то, что увидит Discord при публикации."""
        from services import banner_gen
        text =(request .args .get ('text')or '').strip ()[:500 ]
        try :
            n =max (1 ,int (request .args .get ('n',1 )))
        except (TypeError ,ValueError ):
            n =1
        try :
            total =max (n ,int (request .args .get ('total',n )))
        except (TypeError ,ValueError ):
            total =n
        theme =request .args .get ('theme')or banner_gen .DEFAULT_THEME
        title =(request .args .get ('title')or 'Правила сервера').strip ()[:80 ]
        color =(request .args .get ('color')or '4f46e5').strip ().lstrip ('#')
        try :
            png =banner_gen .render_rules_banner (title =title ,text =text ,index =n ,
                total =total ,accent =color ,theme =theme )
        except Exception as _ex :
            return jsonify ({'error':f'Не удалось отрисовать баннер: {_ex}'[:180 ]}),500
        resp =Response (png ,mimetype ='image/png')
        resp .headers ['Cache-Control']='no-store'
        return resp

    @app .route ('/api/guild/<guild_id>/rules/publish',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_publish_rules (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio ,discord 
        data =request .get_json (silent =True )or {}
        ch_id =str (data .get ('channel_id')or '').strip ()
        raw =data .get ('rules')
        if raw is None :
            # тело без списка правил — публикуем то, что сохранено в редакторе
            f_stored =f'data/rules_{guild_id}.json'
            try :
                with open (f_stored ,encoding ='utf-8')as fp :
                    raw =json .load (fp )
            except Exception :
                raw =[]
        rules =[_norm_rule (r )for r in raw ]if isinstance (raw ,list )else []
        rules =_normalize_rules_urls (rules )
        rules =[r for r in rules if r ['t']]
        meta =_load_rules_meta (guild_id )
        if data .get ('channel_id')is not None :
            meta ['channel_id']=ch_id 
        for k in ('title','intro','color'):
            if k in data :
                meta [k]=str (data [k ]or '').strip ()
        if not ch_id :
            ch_id =meta .get ('channel_id')or ''
        if not ch_id :
            return jsonify ({'error':'Выберите канал публикации'}),400 
        if not rules :
            return jsonify ({'error':'Сначала добавьте правила'}),400 
        ok ,err =_validate_rule_urls (rules )
        if not ok :
            return jsonify ({'error':err }),400
        # финальная нормализация меты
        title =str (meta .get ('title')or '').strip ()[:200 ]or 'Правила сервера'
        intro =str (meta .get ('intro')or '').strip ()[:1800 ]
        color_s =str (meta .get ('color')or '4f46e5').strip ().lstrip ('#')
        import re as _re
        if not _re .match (r'^[0-9a-fA-F]{6}$',color_s ):
            color_s ='4f46e5'
        from services import banner_gen as _bg
        img_theme =str (meta .get ('img_theme')or '').strip ().lower ()
        if img_theme not in _bg .THEMES :
            img_theme =_bg .DEFAULT_THEME
        meta ={'title':title ,'intro':intro ,'color':color_s .lower (),'channel_id':ch_id ,'img_theme':img_theme }
        _save_rules_meta (guild_id ,meta )

        # авто-картинки: у правил без URL включаем отрисовку баннера.
        # Рендерим ДО хождений в Discord — ошибка генерации видна сразу.
        gen ={}   # номер правила (1..N) -> PNG-байты баннера
        for i ,r in enumerate (rules ,1 ):
            if r .get ('img')or not r .get ('img_gen'):
                continue
            try :
                gen [i ]=_bg .render_rules_banner (title =title ,text =r ['t'],
                    index =i ,total =len (rules ),accent =color_s ,theme =r ['img_gen'])
            except Exception as _ex :
                _log .warning ("rules publish: баннер правила %s: %s", i ,_ex )
        gen_count =len (gen )
        # автосохранение — публикуем ровно то, что видим
        f =f'data/rules_{guild_id}.json'
        os .makedirs ('data',exist_ok =True )
        with open (f ,'w',encoding ='utf-8')as fp :json .dump (rules ,fp ,indent =2 ,ensure_ascii =False )
        try :
            from web import _store as _wstore
            _wstore .invalidate_path (f )
        except Exception as _ex :
            _log.debug("api_rules(): invalidate подавлено: %s", _ex )

        accent =int (color_s ,16 )

        def build_embeds ():
            embeds =[]
            head =discord .Embed (
            title =title ,
            description =(intro + (f'  ·  {len (rules )} пунктов' if intro else f'{len (rules )} пунктов')),
            color =accent )
            head .set_footer (text ="Обновлено: " + datetime.now(timezone.utc).strftime ('%d.%m.%Y %H:%M')+ " (UTC) · Aether")
            embeds .append (head )
            for i ,r in enumerate (rules ,1 ):
                e =discord .Embed (color =accent )
                e .title =f"{i}. {r ['t'][:250]}"
                desc =r ['t'][:1000 ]
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

        def channel_ok (ch ,guild ):
            """Канал существует и бот имеет право писать в него."""
            if ch is None :
                return False ,'Канал публикации не найден — возможно, бот его не видит'
            perms =ch .permissions_for (guild .me )
            if not perms .send_messages :
                return False ,'У бота нет права писать в этот канал (Send Messages)'
            return True ,''

        if not bot :
            if _app ._demo_mode ():
                # демо-предпросмотр без бота: публикация считается успешной,
                # отметка в лог панели — действие видно в ленте
                _fire_panel_notification ('rules',f"Правила опубликованы: {len (rules )} пунктов",f"Канал {ch_id } · демо-режим")
                try :
                    import time as _t
                    _pl ='data/panel_logs.json'
                    _logs =_store_json_list (_pl )
                    _logs .insert (0 ,{'username':'system','role':'owner','action':'Правила опубликованы',
                        'detail':f'Канал {ch_id } · {len (rules )} пунктов · демо-режим','ts':int (_t .time ()),'broadcast':True ,'link':'/rules-editor'})
                    json .dump (_logs ,open (_pl ,'w',encoding ='utf-8'),ensure_ascii =False ,indent =2 )
                except Exception as _ex :
                    _log.debug("api_publish_rules(): panel_logs: %s", _ex)
                _gen_note =f", из них {gen_count} с авто-картинкой" if gen_count else ''
                return jsonify ({'success':True ,'demo':True ,'title':title ,'color':color_s .lower (),
                    'images_generated':gen_count ,
                    'message':f"Демо-режим: {len (rules )} правил готовы{_gen_note} — при живом боте они уйдут в Discord с заголовком «{title}»"})
            return jsonify ({'error':'Бот офлайн — публикация недоступна. Запустите бота и повторите.'})
        guild =bot .get_guild (int (guild_id ))
        if guild is None :
            return jsonify ({'error':'Сервер не найден у бота'}),404 
        embeds =build_embeds ()

        async def send ():
            import io as _io
            ch =bot .get_channel (int (ch_id ))
            ok_ch ,err_ch =channel_ok (ch ,guild )
            if not ok_ch :
                raise RuntimeError (err_ch )
            batch =[]
            for i ,e in enumerate (embeds ):
                png =gen .get (i )          # embeds[0] — заголовок, embeds[i] — правило i
                if png is not None :
                    if batch :
                        await ch .send (embeds =batch );batch =[]
                    fn =_bg .banner_filename (i )
                    e .set_image (url ='attachment://' + fn )
                    await ch .send (embed =e ,file =discord .File (_io .BytesIO (png ),filename =fn ))
                else :
                    batch .append (e )
                    if len (batch )==10 :
                        await ch .send (embeds =batch );batch =[]
            if batch :
                await ch .send (embeds =batch )

        try :
            asyncio .run_coroutine_threadsafe (send (),bot .loop ).result (timeout =25 )
        except Exception as _ex :
            msg =str (_ex )
            if 'Forbidden' in msg or 'Missing Access' in msg :
                msg ='Discord запретил отправку: у бота нет прав на этот канал'
            elif 'HTTPException' in msg and '400' in msg :
                msg ='Discord отклонил сообщение (400): проверьте ссылки и картинки правил'
            _log.debug("api_publish_rules(): подавлено: %s", _ex)
            return jsonify ({'error':f"Не удалось опубликовать: {msg }"[:220 ]}),502 
        _fire_panel_notification ('rules',f"Правила опубликованы: {len (rules )} пунктов",f"Канал {ch_id }")
        _gen_note =f", картинок создано: {gen_count}" if gen_count else ''
        return jsonify ({'success':True ,'title':title ,'color':color_s .lower (),
            'images_generated':gen_count ,
            'message':f"Опубликовано правил: {len (rules )}{_gen_note}"})

    def _store_json_list (path ):
        """Список из JSON-файла (или пустой список)."""
        try :
            if os .path .exists (path ):
                with open (path ,encoding ='utf-8')as fp :
                    d =json .load (fp )
                if isinstance (d ,list ):
                    return d
        except Exception as _ex :
            _log.debug("_store_json_list(%s): %s", path ,_ex )
        return []

