# -*- coding: utf-8 -*-
"""Тикеты: настройки, уведомления, закрытие (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

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


        # ── API ROUTES ───────────────────────────────────────────────────────────

    @app .route ('/api/guild/<guild_id>/ticket-settings',methods =['GET','POST'])
    @login_required 
    @role_required ('admin')
    def api_ticket_settings (guild_id ):
        f =f'data/ticket_settings_{guild_id}.json'
        if request .method =='GET':
            if not os .path .exists (f ):return jsonify ({})
            with open (f )as fp :return jsonify (json .load (fp ))
        data =request .get_json (silent =True )or {}
        with open (f ,'w')as fp :json .dump (data ,fp ,indent =2 )
        # Panel сообщение отправить
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio ,discord 
        from cogs .ticket import TicketView 
        panel_sent =False 
        panel_error =None 
        if bot and data .get ('ticket_channel_id'):
            def send_panel ():
                ch =bot .get_channel (int (data ['ticket_channel_id']))
                if not ch :
                    raise ValueError (f"Канал не найден: {data['ticket_channel_id']}")
                embed =discord .Embed (
                title =data .get ('title','🎫  ПОДДЕРЖКА СИСТЕМА'),
                description =(
                data .get ('description',
                "Возникла проблема на сервере?\n"
                "Хочешь что-то спросить?\n\n"
                "**Нажми кнопку ниже** — будет создан твой личный канал поддержки.\n"
                "🤖 **AI-ассистент** сначала поможет тебе!\n"
                "При необходимости наша команда подключится. 💙\n\n"
                "```yaml\n🤖 AI Поддержка  •  ⚡ Быстрый ответ  •  🔒 Приватный канал\n```"
                )
                ),
                color =0x5865F2 
                )
                embed .set_footer (
                text =f"{ch.guild.name} • Поддержка Система",
                icon_url =ch .guild .icon .url if ch .guild .icon else None 
                )
                _run_async (ch .send (embed =embed ,view =TicketView ()))
            try :
                future =asyncio .run_coroutine_threadsafe (send_panel (),bot .loop )
                future .result (timeout =10 )# ждём 10 секунд, ловим ошибку
                panel_sent =True 
            except Exception as ex :
                panel_error =str (ex )
        return jsonify ({'success':True ,'panel_sent':panel_sent ,'error':panel_error })


        # ── КАНАЛ УВЕДОМЛЕНИЙ АДМИНОВ О ТИКЕТАХ ─────────────────────────────
    @app .route ('/api/guild/<guild_id>/ticket-notify-channel',methods =['GET','POST'])
    @login_required 
    @role_required ('admin')
    def api_ticket_notify_channel (guild_id ):
        f =f'data/ticket_notify_{guild_id}.json'
        if request .method =='GET':
            if not os .path .exists (f ):
                return jsonify ({
                'notify_channel_id':None ,
                'rules_channel_id':None ,
                'mod_role_id':None ,
                'admin_role_id':None ,
                'owner_role_id':None 
                })
            try :
                with open (f ,'r',encoding ='utf-8')as fp :
                    return jsonify (json .load (fp ))
            except Exception :
                return jsonify ({
                'notify_channel_id':None ,
                'rules_channel_id':None ,
                'mod_role_id':None ,
                'admin_role_id':None ,
                'owner_role_id':None 
                })
        data =request .get_json (silent =True )or {}
        cid =data .get ('notify_channel_id')
        rcid =data .get ('rules_channel_id')
        mrid =data .get ('mod_role_id')
        arid =data .get ('admin_role_id')
        orid =data .get ('owner_role_id')

        def val_id (x ):
            if x is not None and x !='':
                x =str (x ).strip ()
                if x .isdigit ()and 17 <=len (x )<=22 :
                    return x 
            return None 

        config_data ={
        'notify_channel_id':val_id (cid ),
        'rules_channel_id':val_id (rcid ),
        'mod_role_id':val_id (mrid ),
        'admin_role_id':val_id (arid ),
        'owner_role_id':val_id (orid )
        }
        os .makedirs ('data',exist_ok =True )
        with open (f ,'w',encoding ='utf-8')as fp :
            json .dump (config_data ,fp ,indent =2 ,ensure_ascii =False )
        return jsonify ({'success':True ,**config_data })


    @app .route ('/api/guild/<guild_id>/ticket-notify-diagnose',methods =['GET'])
    @login_required 
    @role_required ('admin')
    def api_ticket_notify_diagnose (guild_id ):
        """Диагностика: что происходит при вызове _notify_admins_penalty.
        Возвращает детальную информацию о текущей конфигурации, чтобы
        понять, почему уведомления не доходят.
        """
        import web .app as _app 
        bot =_app .bot_instance 
        result ={
        'guild_id':guild_id ,
        'bot_online':bool (bot ),
        'config_file_exists':False ,
        'config_notify_channel_id':None ,
        'config_target_channel':None ,
        'config_target_channel_name':None ,
        'fallback_channels_found':[],
        'admin_role_found':None ,
        'guild_owner_can_dm':None ,
        'all_text_channels':[],
        'recommendation':'',
        }

        # 1. Конфиг-файл
        f =f'data/ticket_notify_{guild_id}.json'
        if os .path .exists (f ):
            result ['config_file_exists']=True 
            try :
                with open (f ,'r',encoding ='utf-8')as fp :
                    cfg =json .load (fp )or {}
                result ['config_notify_channel_id']=cfg .get ('notify_channel_id')
            except Exception as e :
                result ['config_file_error']=str (e )

                # 2. Бот и guild
        if not bot :
            result ['recommendation']='❌ Бот offline. Перезапусти бота.'
            return jsonify (result )
        guild =None 
        for g in bot .guilds :
            if str (g .id )==str (guild_id ):
                guild =g 
                break 
        if not guild :
            result ['recommendation']=f'❌ Бот не на сервере {guild_id}. Бот на: {[str(g.id) for g in bot.guilds]}'
            return jsonify (result )
        result ['guild_name']=guild .name 

        # 3. Канал из конфига
        if result ['config_notify_channel_id']:
            try :
                ch =guild .get_channel (int (result ['config_notify_channel_id']))
                if not ch :
                    ch =None # fetch не делаем — sync endpoint
                if ch :
                    result ['config_target_channel']=str (ch .id )
                    result ['config_target_channel_name']=ch .name 
                else :
                    result ['config_target_channel_error']=f'Канал ID={result["config_notify_channel_id"]} не найден на сервере'
            except Exception as e :
                result ['config_target_channel_error']=str (e )

                # 4. Все текстовые каналы
        result ['all_text_channels']=[
        {'id':str (c .id ),'name':c .name ,'position':c .position }
        for c in guild .text_channels [:50 ]
        ]

        # 5. Fallback каналы по имени
        for name in ('admin-log','mod-log','логи-модерации','staff-log'):
            ch =discord .utils .get (guild .text_channels ,name =name )
            if ch :
                result ['fallback_channels_found'].append ({'name':name ,'id':str (ch .id )})

                # 6. Admin role
        try :
            admin_role =discord .utils .get (guild .roles ,permissions =discord .Permissions (administrator =True ))
            if admin_role :
                result ['admin_role_found']={'name':admin_role .name ,'id':str (admin_role .id )}
        except Exception as _ex:
            _log.debug("api_ticket_notify_diagnose(): подавлено: %s", _ex)

            # 7. Владелец для DM
        if guild .owner :
            result ['guild_owner_can_dm']={
            'name':str (guild .owner ),
            'id':str (guild .owner .id ),
            'bot':guild .owner .bot ,
            }

            # 8. Рекомендация
        if result ['config_target_channel']:
            result ['recommendation']=(
            '✅ Конфиг установлен. Уведомления должны идти в канал '
            f'#{result["config_target_channel_name"]} ({result["config_target_channel"]}). '
            'Если уведомлений нет — проверь логи бота (ищи "[TICKET-NOTIFY]").'
            )
        elif result ['fallback_channels_found']:
            ch =result ['fallback_channels_found'][0 ]
            result ['recommendation']=(
            f'⚠️ Конфиг пустой, но найден fallback-канал #{ch["name"]} ({ch["id"]}). '
            'Уведомления должны идти туда.'
            )
        elif result ['guild_owner_can_dm']and not result ['guild_owner_can_dm'].get ('bot'):
            result ['recommendation']=(
            '⚠️ Ни конфиг, ни fallback каналы не найдены. Уведомления пойдут в DM '
            f'владельцу {result["guild_owner_can_dm"]["name"]}. '
            'Но лучше создать канал "admin-log" или "mod-log" ИЛИ установить '
            'notify_channel_id в настройках выше.'
            )
        else :
            result ['recommendation']=(
            '❌ Ни конфиг, ни fallback каналы, ни владелец для DM — '
            'уведомления НИКУДА не доставляются! Создай канал или установи ID.'
            )

        return jsonify (result )


    @app .route ('/api/guild/<guild_id>/tickets')
    @login_required 
    @role_required ('mod')
    def api_tickets (guild_id ):
        f =f'data/tickets_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ([])
        with open (f )as fp :return jsonify (list (json .load (fp ).values ()))


    @app .route ('/api/guild/<guild_id>/tickets/<ticket_id>/close',methods =['POST'])
    @login_required 
    @role_required ('mod')
    def api_close_ticket (guild_id ,ticket_id ):
        f =f'data/tickets_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ({'success':True })
        with open (f )as fp :tickets =json .load (fp )
        if ticket_id in tickets :
            tickets [ticket_id ]['status']='closed'
            with open (f ,'w')as fp :json .dump (tickets ,fp ,indent =2 )
            _t =tickets [ticket_id ]
            # Уведомление персонала по настроенным каналам (веб/Discord/email)
            _fire_panel_notification (
            'ticket_close',
            f"Тикет закрыт: {_t .get ('name') or _t .get ('subject') or ticket_id}",
            f"{session .get ('username','Модератор')} закрыл тикет {ticket_id}")
        return jsonify ({'success':True })


    @app .route ('/api/guild/<guild_id>/automod',methods =['GET','POST'])
    @login_required 
    @role_required ('admin')
    def api_automod_settings (guild_id ):
        f =f'data/automod_{guild_id}.json'
        if request .method =='GET':
            if not os .path .exists (f ):return jsonify ({'banned_words':[]})
            with open (f )as fp :return jsonify (json .load (fp ))
        data =request .get_json (silent =True )or {}
        # Читаем текущий конфиг и объединяем (чтобы ни одно поле не потерялось)
        existing ={}
        if os .path .exists (f ):
            try :
                with open (f ,encoding ='utf-8')as fp :existing =json .load (fp )
            except Exception as _ex:
                _log.debug("api_automod_settings(): подавлено: %s", _ex)
        existing .update (data )
        with open (f ,'w',encoding ='utf-8')as fp :json .dump (existing ,fp ,indent =2 ,ensure_ascii =False )
        return jsonify ({'success':True })
