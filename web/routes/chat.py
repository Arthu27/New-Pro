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
        if not bot :return jsonify ({'error':'Бот офлайн'}),503 
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
        if not bot :return jsonify ({'error':'Бот офлайн'}),503 
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
        if not bot :return jsonify ({'error':'Бот офлайн'}),503 
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
        if not bot :return jsonify ([])
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
        for uid ,msgs in log .items ():
            if not msgs :continue 
            last =msgs [-1 ]
            name =uid 
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
        if not bot :return jsonify ({'error':'Бот офлайн'}),503 
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
