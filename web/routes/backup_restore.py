# -*- coding: utf-8 -*-
"""Бэкапы: создание/скачивание/восстановление + логи сообщений (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

from web.routes._common import (
    _run_async, _fetch_channel_msgs_async, _fetch_channel_msgs_sync,
    _notify_discord_sender, _fire_panel_notification,
    _process_action, _log,
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


    @app .route ('/api/guild/<guild_id>/backup',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_create_backup (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        if not bot :return jsonify ({'error':'Бот офлайн'})
        guild =bot .get_guild (int (guild_id ))
        if not guild :return jsonify ({'error':'Сервер не найден'})
        data =request .get_json (silent =True )or {}
        backup ={'guild_name':guild .name ,'guild_id':str (guild .id ),
        'created_at':datetime.now(timezone.utc).replace(tzinfo=None).strftime ('%Y-%m-%d %H:%M'),'size':'0 KB'}
        if data .get ('role'):
            backup ['role']=[{'name':r .name ,'color':str (r .color ),'permissions':r .permissions .value ,
            'hoist':r .hoist ,'mentionable':r .mentionable }for r in guild .roles if r .name !='@everyone']
        if data .get ('channels'):
            backup ['channels']=[{'name':c .name ,'type':str (c .type ),'position':c .position ,
            'topic':getattr (c ,'topic',None )}for c in guild .channels ]
        if data .get ('settings'):
            backup ['settings']={'name':guild .name ,'description':guild .description ,
            'verification_level':str (guild .verification_level )}
        backup_id =str (int (datetime.now(timezone.utc).timestamp ()))
        backup ['id']=backup_id 
        import sys 
        backup ['size']=f"{round(sys.getsizeof(json.dumps(backup)) / 1024, 1)} KB"
        f ='data/backups.json'
        os .makedirs ('data',exist_ok =True )
        backups =[]
        if os .path .exists (f ):
            try :
                with open (f ,encoding ='utf-8')as fp :backups =json .load (fp )
            except (json .JSONDecodeError ,ValueError ):
                backups =[]
        backups .append (backup )
        with open (f ,'w',encoding ='utf-8')as fp :json .dump (backups ,fp ,indent =2 ,ensure_ascii =False )
        return jsonify ({'success':True ,'id':backup_id })


    @app .route ('/api/backups/<backup_id>/download')
    @login_required 
    @role_required ('admin')
    def api_download_backup (backup_id ):
        from flask import send_file 
        import io 
        f ='data/backups.json'
        if not os .path .exists (f ):return jsonify ({'error':'Не найдено'})
        try :
            with open (f ,encoding ='utf-8')as fp :backups =json .load (fp )
        except (json .JSONDecodeError ,ValueError ):
            return jsonify ({'error':'Файл бэкапа повреждён'})
        backup =next ((b for b in backups if b .get ('id')==backup_id ),None )
        if not backup :return jsonify ({'error':'Не найдено'})
        buf =io .BytesIO (json .dumps (backup ,indent =2 ,ensure_ascii =False ).encode ())
        buf .seek (0 )
        return send_file (buf ,as_attachment =True ,download_name =f"backup_{backup_id}.json",mimetype ='application/json')


    @app .route ('/api/backups/<backup_id>/delete',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_delete_backup (backup_id ):
        f ='data/backups.json'
        if not os .path .exists (f ):return jsonify ({'success':True })
        try :
            with open (f ,encoding ='utf-8')as fp :backups =json .load (fp )
        except (json .JSONDecodeError ,ValueError ):
            return jsonify ({'success':True })
        backups =[b for b in backups if b .get ('id')!=backup_id ]
        with open (f ,'w',encoding ='utf-8')as fp :json .dump (backups ,fp ,indent =2 ,ensure_ascii =False )
        return jsonify ({'success':True })


    @app .route ('/api/guild/<guild_id>/restore',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_restore_backup (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio ,discord 
        if not bot :return jsonify ({'error':'Бот офлайн'})
        guild =bot .get_guild (int (guild_id ))
        if not guild :return jsonify ({'error':'Целевой сервер не найден'})

        # Загрузка JSON-файла или backup_id?
        backup_data =None 
        if request .content_type and 'multipart'in request .content_type :
            f =request .files .get ('file')
            if not f :return jsonify ({'error':'Файл не найден'})
            try :
                backup_data =json .loads (f .read ().decode ('utf-8'))
            except Exception :
                return jsonify ({'error':'Неверный JSON-файл'})
        else :
            data =request .get_json (silent =True )or {}
            backup_id =data .get ('backup_id')
            bf ='data/backups.json'
            if not os .path .exists (bf ):return jsonify ({'error':'Резервная копия не найдена'})
            try :
                with open (bf ,encoding ='utf-8')as fp :backups =json .load (fp )
            except Exception :
                return jsonify ({'error':'Файл резервной копии повреждён'})
            backup_data =next ((b for b in backups if b .get ('id')==backup_id ),None )
            if not backup_data :return jsonify ({'error':'Резервная копия не найдена'})

        result ={'roles_created':0 ,'channels_created':0 ,'errors':[]}

        def do_restore ():
        # Роли примен
            if 'role'in backup_data :
                existing_role_names =[r .name .lower ()for r in guild .roles ]
                for role_data in backup_data ['role']:
                    if role_data ['name'].lower ()in existing_role_names :
                        continue 
                    try :
                        color_str =role_data .get ('color','#000000').lstrip ('#')
                        color =discord .Color (int (color_str ,16 ))if color_str and color_str !='000000'else discord .Color .default ()
                        _run_async (guild .create_role (
                        name =role_data ['name'],
                        color =color ,
                        hoist =role_data .get ('hoist',False ),
                        mentionable =role_data .get ('mentionable',False ),
                        permissions =discord .Permissions (role_data .get ('permissions',0 ))
                        ))
                        result ['roles_created']+=1 
                        _run_async (asyncio .sleep (0.5 ))# rate limit
                    except Exception as e :
                        result ['errors'].append (f"Роли '{role_data['name']}': {str(e)}")

                        # Каналы примен
            if 'channels'in backup_data :
                existing_ch_names =[c .name .lower ()for c in guild .channels ]
                for ch_data in backup_data ['channels']:
                    if ch_data ['name'].lower ()in existing_ch_names :
                        continue 
                    try :
                        ch_type =ch_data .get ('type','text')
                        if 'text'in ch_type :
                            _run_async (guild .create_text_channel (
                            name =ch_data ['name'],
                            topic =ch_data .get ('topic')
                            ))
                        elif 'voice'in ch_type :
                            _run_async (guild .create_voice_channel (name =ch_data ['name']))
                        elif 'category'in ch_type :
                            _run_async (guild .create_category (name =ch_data ['name']))
                        result ['channels_created']+=1 
                        _run_async (asyncio .sleep (0.5 ))
                    except Exception as e :
                        result ['errors'].append (f"Канал '{ch_data['name']}': {str(e)}")

        asyncio .run_coroutine_threadsafe (do_restore (),bot .loop ).result (timeout =120 )
        return jsonify ({'success':True ,'result':result })


    @app .route ('/api/guild/<guild_id>/message-logs')
    @login_required 
    @role_required ('mod')
    def api_message_logs (guild_id ):
        audit_file ='data/audit_log.json'
        if not os .path .exists (audit_file ):
            return jsonify ([])
        try :
            with open (audit_file ,'r',encoding ='utf-8')as fp :
                all_data =json .load (fp )
        except Exception :
            return jsonify ([])
        events =all_data .get (str (guild_id ),[])
        # Только message kategorisi
        msg_type =request .args .get ('type')# 'deleted' или 'edited'
        result =[]
        for ev in events :
            if ev .get ('category')!='message':
                continue 
            action =ev .get ('action','').lower ()
            if msg_type =='deleted'and 'удалить'not in action and 'delete'not in action :
                continue 
            if msg_type =='edited'and 'dюzenl'not in action and 'edit'not in action :
                continue 
            result .append (ev )
        result .sort (key =lambda x :x .get ('timestamp',''),reverse =True )
        return jsonify (result [:300 ])


        # ── ПОИСК СООБЩЕНИЙ ПОЛЬЗОВАТЕЛЯ (для AI) ──────────────────────────────
    @app .route ('/api/guild/<guild_id>/user-messages',methods =['GET'])
    @login_required 
    @role_required ('mod')
    def api_user_messages (guild_id ):
        """Поиск сообщений пользователя в файле message_log.

        Query params:
          user_id (обязательно) — Discord user ID
          channel_id (опционально) — конкретный канал
          limit (опционально, default 50, max 200) — число результатов
        """
        try :
            user_id =str (request .args .get ('user_id','')).strip ()
            if not user_id .isdigit ()or not (17 <=len (user_id )<=22 ):
                return jsonify ({'error':'Неверный user_id'}),400 
            channel_id =str (request .args .get ('channel_id','')).strip ()or None 
            try :
                limit =int (request .args .get ('limit',50 ))
                limit =max (1 ,min (limit ,200 ))
            except (TypeError ,ValueError ):
                limit =50 

            f =f'data/message_log_{guild_id}.json'
            if not os .path .exists (f ):
                return jsonify ({'messages':[],'total':0 ,'note':'log нет'})
            try :
                with open (f ,'r',encoding ='utf-8')as fp :
                    logs =json .load (fp )or []
            except (OSError ,json .JSONDecodeError ,ValueError ):
                return jsonify ({'messages':[],'total':0 ,'note':'log bozuk'})

                # Filtrele
            filtered =[m for m in logs 
            if str (m .get ('author_id',''))==user_id 
            and (channel_id is None or str (m .get ('channel_id',''))==channel_id )]
            # En новыйden старыйye
            filtered .sort (key =lambda x :x .get ('timestamp',''),reverse =True )
            filtered =filtered [:limit ]
            return jsonify ({
            'messages':filtered ,
            'total':len (filtered ),
            'note':None ,
            })
        except Exception as e :
            return jsonify ({'error':str (e )}),500 


    @app .route ('/api/restore-upload',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_restore_upload ():
        """Вернуть backup_data из загруженного JSON (для предпросмотра)"""
        f =request .files .get ('file')
        if not f :return jsonify ({'error':'Файл отсутствует'})
        try :
            data =json .loads (f .read ().decode ('utf-8'))
            return jsonify ({
            'guild_name':data .get ('guild_name','?'),
            'created_at':data .get ('created_at','?'),
            'roles_count':len (data .get ('role',[])),
            'channels_count':len (data .get ('channels',[])),
            'has_settings':'settings'in data ,
            'raw':data 
            })
        except Exception as e :
            return jsonify ({'error':f'Неверный файл: {str(e)}'})
