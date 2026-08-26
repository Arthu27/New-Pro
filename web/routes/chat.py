# -*- coding: utf-8 -*-
"""Чат сервера + DM как бот (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

from web.routes._common import (
    _run_async, _fetch_channel_msgs_async, _fetch_channel_msgs_sync,
    _load_ai_tickets, _notify_discord_sender, _fire_panel_notification,
    _process_action, _log,
    ms_normalize_query, ms_member_match, ms_search_members, ms_member_payload,
    ms_normalize_warn, ms_normalize_case, calculate_ai_ticket_stats, _REPO_ROOT,
    render_template, session, redirect, url_for, request, jsonify, Response,
    os, json, time, math, discord, datetime, timezone,
)

def _chat_demo_store ():
    path =os .path .join (_REPO_ROOT ,'data','chat_demo.json')
    try :
        with open (path ,'r',encoding ='utf-8')as fp :
            return json .load (fp )
    except Exception :
        return {}


def _chat_demo_save (data ):
    os .makedirs (os .path .join (_REPO_ROOT ,'data'),exist_ok =True )
    with open (os .path .join (_REPO_ROOT ,'data','chat_demo.json'),'w',encoding ='utf-8')as fp :
        json .dump (data ,fp ,ensure_ascii =False ,indent =2 )


def _demo_members ():
    return [
        {'id':'1001','name':'sonya.staff','display_name':'Sonya','avatar':'https://cdn.discordapp.com/embed/avatars/1.png','status':'online','mention':'<@1001>'},
        {'id':'1002','name':'artem.mods','display_name':'Artem','avatar':'https://cdn.discordapp.com/embed/avatars/2.png','status':'idle','mention':'<@1002>'},
        {'id':'1003','name':'lina.mod','display_name':'Lina','avatar':'https://cdn.discordapp.com/embed/avatars/3.png','status':'dnd','mention':'<@1003>'},
        {'id':'1004','name':'max.gg','display_name':'Max','avatar':'https://cdn.discordapp.com/embed/avatars/4.png','status':'online','mention':'<@1004>'},
        {'id':'1005','name':'dasha.live','display_name':'Dasha','avatar':'https://cdn.discordapp.com/embed/avatars/5.png','status':'offline','mention':'<@1005>'},
        {'id':'1006','name':'hakumo.bot','display_name':'Hakumo','avatar':'','status':'online','bot':True,'mention':'<@1006>'},
    ]


def _chat_demo_seed (channel_id ):
    """Демо-сид канала: живая беседа, а не «режим превью».

    Показывает возможности чата: ответы, markdown, упоминания,
    редактирование, сообщения от участников и бота.
    """
    _demo_users ={
    '1001':('Sonya','https://cdn.discordapp.com/embed/avatars/1.png',False ),
    '1002':('Artem','https://cdn.discordapp.com/embed/avatars/2.png',False ),
    '1003':('Lina','https://cdn.discordapp.com/embed/avatars/3.png',False ),
    '1004':('Max','https://cdn.discordapp.com/embed/avatars/4.png',False ),
    '1006':('Hakumo','',True ),
    }
    from datetime import datetime as _dt ,timedelta as _td ,timezone as _tz 
    _base =_dt .now (_tz .utc )

    def _m (mid ,uid ,minutes_ago ,content ,**kw ):
        name ,av ,isbot =_demo_users [uid ]
        msg ={
        'id':mid ,'content':content ,
        'author':name ,'author_id':uid ,'avatar':av ,'bot':isbot ,
        'timestamp':(_base -_td (minutes =minutes_ago )).isoformat (),
        'edited':kw .get ('edited'),'attachments':kw .get ('attachments',[]),
        'embeds':kw .get ('embeds',False ),
        }
        if kw .get ('reply_to'):
            msg ['reply_to']=kw ['reply_to']
        return msg 

    return [
    _m ('d1','1001',240 ,'Всем привет! Сегодня в 20:00 запускаем новый розыгрыш — не пропустите'),
    _m ('d2','1004',236 ,'о, наконец-то) в этот раз что разыгрываем?'),
    _m ('d3','1001',233 ,'**Discord Nitro на месяц** — детали в канале #розыгрыши',
        reply_to ={'author':'Max','content':'о, наконец-то) в этот раз что разыгрываем?'}),
    _m ('d4','1006',230 ,'Напомнил про розыгрыш: подключайтесь заранее, чтобы не пропустить начало'),
    _m ('d5','1002',140 ,'Кто-нибудь проверял новые правила? Вроде теперь муты выдаёт только модератор, не автопилот'),
    _m ('d6','1001',138 ,'Да, ИИ теперь только консультирует — наказания всегда за человеком',
        reply_to ={'author':'Artem','content':'Кто-нибудь проверял новые правила?'}),
    _m ('d7','1003',45 ,'Я за! Стало спокойнее, никаких случайных мутов',
        edited =True ),
    _m ('d8','1004',12 ,'Тогда до вечера в голосовом'),
    ]


def register(ctx):
    app = ctx.app
    ROLES = ctx.ROLES
    login_required = ctx.login_required
    role_required = ctx.role_required
    MAIN_GUILD_ID = ctx.MAIN_GUILD_ID
    active_guild_id = ctx.active_guild_id
    _resolve_member_async = ctx._resolve_member_async


        # ── CHAT API ─────────────────────────────────────────────────────────────

    @app .route ('/api/chat/<guild_id>/<channel_id>/messages')
    @login_required 
    @role_required ('owner')
    def api_chat_messages (guild_id ,channel_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio 
        if not bot :
            store =_chat_demo_store ()
            key =f'{guild_id}:{channel_id}'
            fresh =False 
            if key not in store or not store [key ]:
                store [key ]=_chat_demo_seed (channel_id )
                fresh =True 
            else :
                # миграция: выкидываем старую системную заглушку «Демо-режим…»
                old_len =len (store [key ])
                store [key ]=[m for m in store [key ]
                if not str (m .get ('content','')).startswith ('Демо-режим')]
                if not store [key ]:
                    store [key ]=_chat_demo_seed (channel_id )
                elif len (store [key ])!=old_len :
                    fresh =True 
            if fresh :
                _chat_demo_save (store )
            return jsonify (store [key ][-50 :])
        channel =bot .get_channel (int (channel_id ))
        if not channel :return jsonify ({'error':'Канал не найден'}),404 
        async def _fetch ():
            msgs =[]
            async for m in channel .history (limit =50 ,oldest_first =False ):
                msgs .append ({
                'id':str (m .id ),
                'content':m .content ,
                'author':m .author .display_name ,
                'author_id':str (m .author .id ),
                'avatar':str (m .author .display_avatar .url ),
                'bot':m .author .bot ,
                'timestamp':m .created_at .isoformat (),
                'edited':m .edited_at .isoformat ()if m .edited_at else None ,
                'attachments':[a .url for a in m .attachments ],
                'embeds':len (m .embeds )>0 ,
                })
            return list (reversed (msgs ))
        try :
            msgs =asyncio .run_coroutine_threadsafe (_fetch (),bot .loop ).result (timeout =10 )
            return jsonify (msgs )
        except Exception as e :
            return jsonify ({'error':str (e )}),500 


    @app .route ('/api/chat/<guild_id>/<channel_id>/send',methods =['POST'])
    @login_required 
    @role_required ('owner')
    def api_chat_send (guild_id ,channel_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio 
        if not bot :
            d =request .get_json (silent =True )or {}
            content =str (d .get ('content','')).strip ()
            if not content :return jsonify ({'error':'Сообщение пусто'}),400
            store =_chat_demo_store ()
            key =f'{guild_id}:{channel_id}'
            msgs =store .get (key ,[])
            msgs .append ({
                'id':'d'+str (int (time .time ()*1000 )),
                'content':content ,
                'author':'Вы',
                'author_id':'0',
                'avatar':'https://cdn.discordapp.com/embed/avatars/0.png',
                'bot':False ,
                'timestamp':datetime .now (timezone .utc ).isoformat (),
                'edited':None ,'attachments':[] ,'embeds':False })
            store [key ]=msgs [-100 :]
            _chat_demo_save (store )
            return jsonify ({'ok':True })
        channel =bot .get_channel (int (channel_id ))
        if not channel :return jsonify ({'error':'Канал не найден'}),404 
        d =request .get_json (silent =True )or {}
        content =d .get ('content','').strip ()
        if not content :return jsonify ({'error':'Сообщение пусто'}),400 
        def _send ():
            _run_async (channel .send (content ))
        try :
            asyncio .run_coroutine_threadsafe (_send (),bot .loop ).result (timeout =10 )
            return jsonify ({'ok':True })
        except Exception as e :
            return jsonify ({'error':str (e )}),500 


    @app .route ('/api/chat/<guild_id>/<channel_id>/delete/<message_id>',methods =['POST'])
    @login_required 
    @role_required ('owner')
    def api_chat_delete (guild_id ,channel_id ,message_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio 
        if not bot :
            store =_chat_demo_store ()
            key =f'{guild_id}:{channel_id}'
            msgs =[m for m in store .get (key ,[])if str (m .get ('id'))!=str (message_id )]
            store [key ]=msgs 
            _chat_demo_save (store )
            return jsonify ({'ok':True })
        channel =bot .get_channel (int (channel_id ))
        if not channel :return jsonify ({'error':'Канал не найден'}),404 
        def _delete ():
            msg =_run_async (channel .fetch_message (int (message_id )))
            _run_async (msg .delete ())
        try :
            asyncio .run_coroutine_threadsafe (_delete (),bot .loop ).result (timeout =10 )
            return jsonify ({'ok':True })
        except Exception as e :
            return jsonify ({'error':str (e )}),500 


    @app .route ('/api/chat/<guild_id>/members')
    @login_required 
    @role_required ('owner')
    def api_chat_members (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        if not bot :return jsonify (_demo_members ())
        guild =bot .get_guild (int (guild_id ))
        if not guild :return jsonify ([])
        return jsonify ([{
        'id':str (m .id ),
        'name':m .display_name ,
        'display_name':m .display_name ,
        'avatar':str (m .display_avatar .url )if m .display_avatar else '',
        'mention':f'<@{m.id}>'
        }for m in guild .members if not m .bot ][:200 ])


        # ── DM API ───────────────────────────────────────────────────────────────
    DM_LOG_FILE ='data/dm_log.json'


    def _load_dm_log ():
        if os .path .exists (DM_LOG_FILE ):
            try :
                with open (DM_LOG_FILE ,'r',encoding ='utf-8')as f :
                    return json .load (f )
            except Exception as _ex:
                _log.debug("_load_dm_log(): подавлено: %s", _ex)
        return {}


    def _save_dm_log (data ):
        os .makedirs ('data',exist_ok =True )
        with open (DM_LOG_FILE ,'w',encoding ='utf-8')as f :
            json .dump (data ,f ,ensure_ascii =False ,indent =2 )


    @app .route ('/api/dm/<guild_id>/recent')
    @login_required 
    @role_required ('mod')
    def api_dm_recent (guild_id ):
        """Список последних DM-разговоров"""
        import web .app as _app ;bot =_app .bot_instance 
        log =_load_dm_log ()
        result =[]
        try :
            from web .routes ._common import name_map_for
            _nm =name_map_for (guild_id ,bot )
        except Exception as _ex :
            _nm ={}
        for uid ,msgs in log .items ():
            if not msgs :continue 
            last =msgs [-1 ]
            name =_nm .get (uid )or uid 
            avatar =''
            if bot :
                for g in bot .guilds :
                    try :
                        m =g .get_member (int (uid ))
                        if m :
                            name =m .display_name 
                            avatar =str (m .display_avatar .url )if m .display_avatar else ''
                            break 
                    except Exception as _ex:
                        _log.debug("api_dm_recent(): подавлено: %s", _ex)
            elif not avatar :
                try :
                    from web .routes ._common import DEMO_MEMBERS
                    for dm in DEMO_MEMBERS :
                        if str (dm .get ('id'))==uid :
                            name =str (dm .get ('display_name')or dm .get ('name')or uid )
                            avatar =str (dm .get ('avatar')or '')
                            break 
                except Exception as _ex :
                    _log.debug("api_dm_recent(): демо-аватар: %s", _ex )
            result .append ({
            'id':uid ,
            'name':name ,
            'avatar':avatar ,
            'last_msg':last .get ('content','')[:50 ],
            'timestamp':last .get ('timestamp',''),
            'unread':0 ,
            })
        result .sort (key =lambda x :x ['timestamp'],reverse =True )
        return jsonify (result [:20 ])


    @app .route ('/api/dm/<guild_id>/<user_id>/messages')
    @login_required 
    @role_required ('mod')
    def api_dm_messages (guild_id ,user_id ):
        log =_load_dm_log ()
        msgs =log .get (user_id ,[])
        return jsonify (msgs )


    @app .route ('/api/dm/<guild_id>/<user_id>/send',methods =['POST'])
    @login_required 
    @role_required ('mod')
    def api_dm_send (guild_id ,user_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio as _asyncio ,datetime as _dt2 
        if not bot :
            d =request .get_json (silent =True )or {}
            content =str (d .get ('content','')).strip ()
            if not content :return jsonify ({'error':'Сообщение пусто'}),400
            log =_load_dm_log ()
            msgs =log .get (user_id ,[])
            msgs .append ({'author':'demo','from_bot':True ,'content':content ,
                           'timestamp':datetime .now (timezone .utc ).isoformat ()})
            log [user_id ]=msgs 
            _save_dm_log (log )
            return jsonify ({'ok':True }) 
        data =request .get_json (silent =True )or {}
        content =data .get ('content','').strip ()
        if not content :return jsonify ({'error':'Сообщение пусто'}),400 

        async def do ():
            user =await (bot .fetch_user (int (user_id )))
            await (user .send (content ))
            return str (user )

        try :
            _asyncio .run_coroutine_threadsafe (do (),bot .loop ).result (timeout =10 )
            # Сохранить в лог
            log =_load_dm_log ()
            if user_id not in log :log [user_id ]=[]
            log [user_id ].append ({
            'author':session .get ('username','Panel'),
            'content':content ,
            'timestamp':_dt2 .datetime.now(timezone.utc).isoformat (),
            'from_bot':True ,
            })
            _save_dm_log (log )
            return jsonify ({'ok':True })
        except Exception as e :
            return jsonify ({'error':str (e )}),500 
