# -*- coding: utf-8 -*-
"""CRUD каналов (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

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


    @app .route ('/api/guild/<guild_id>/channels/create',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_create_channel (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio ,discord 
        if not bot :return jsonify ({'error':'Бот офлайн'})
        data =request .get_json (silent =True )or {}
        async def do ():
            guild =bot .get_guild (int (guild_id ))
            t =data .get ('type','text')
            name =str (data .get ('name','') or '').strip ()
            if not name :
                raise ValueError ('Название канала обязательно')
            kwargs ={}
            cat_name =data .get ('category','')
            if cat_name :
                cat =None 
                for c in guild .channels :
                    if c .type ==discord .ChannelType .category and c .name ==cat_name :
                        cat =c 
                        break 
                if cat is None :
                    cat =await (guild .create_category (cat_name ))
                kwargs ['category']=cat 
            topic =data .get ('topic','')
            if topic :
                kwargs ['topic']=str (topic )[:1024 ]
            slowmode =data .get ('slowmode',0 )
            if slowmode :
                kwargs ['slowmode_delay']=int (slowmode )
            nsfw =data .get ('nsfw',False )
            if nsfw :
                kwargs ['nsfw']=True 
            if t =='text':
                await (guild .create_text_channel (name ,**kwargs ))
            elif t =='voice':
                vkw =dict (kwargs )
                bitrate =data .get ('bitrate',0 )
                if bitrate :
                    vkw ['bitrate']=min (int (bitrate )* 1000 ,guild .bitrate_limit )
                ulimit =data .get ('user_limit',0 )
                if ulimit :
                    vkw ['user_limit']=int (ulimit )
                await (guild .create_voice_channel (name ,**vkw ))
            elif t =='category':
                await (guild .create_category (name ))
        try :
            asyncio .run_coroutine_threadsafe (do (),bot .loop ).result (timeout =10 )
            return jsonify ({'success':True })
        except Exception as e :
            return jsonify ({'success':False ,'error':str (e )})


    @app .route ('/api/guild/<guild_id>/channels/<channel_id>/update',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_update_channel (guild_id ,channel_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio ,discord 
        if not bot :return jsonify ({'error':'Бот офлайн'})
        data =request .get_json (silent =True )or {}
        async def do ():
            guild =bot .get_guild (int (guild_id ))
            ch =guild .get_channel (int (channel_id ))
            if not ch :
                raise ValueError ('Канал не найден')
            # Переименование
            if 'name' in data and data ['name']:
                await (ch .edit (name =str (data ['name'])[:100 ]))
            # Тема / topic (текстовые каналы)
            if 'topic' in data :
                await (ch .edit (topic =str (data ['topic'] or '')[:1024 ]))
            # NSFW
            if 'nsfw' in data :
                await (ch .edit (nsfw =bool (data ['nsfw'])))
            # Slowmode (текстовые каналы)
            if 'slowmode' in data :
                await (ch .edit (slowmode_delay =int (data ['slowmode'] or 0 )))
            # Битрейт (голосовые каналы)
            if 'bitrate' in data :
                br =min (int (data ['bitrate'] or 0 )* 1000 ,guild .bitrate_limit )
                await (ch .edit (bitrate =br ))
            # Лимит участников (голосовые каналы)
            if 'user_limit' in data :
                await (ch .edit (user_limit =int (data ['user_limit'] or 0 )))
            # Перенос в категорию
            if 'category' in data :
                cat_name =data ['category']
                if cat_name :
                    cat =None 
                    for c in guild .channels :
                        if c .type ==discord .ChannelType .category and c .name ==cat_name :
                            cat =c 
                            break 
                    if cat is None :
                        cat =await (guild .create_category (cat_name ))
                    await (ch .edit (category =cat ))
                else :
                    await (ch .edit (category =None ))
            # Позиция
            if 'position' in data :
                await (ch .edit (position =int (data ['position'])))
        try :
            asyncio .run_coroutine_threadsafe (do (),bot .loop ).result (timeout =10 )
            return jsonify ({'success':True })
        except Exception as e :
            return jsonify ({'success':False ,'error':str (e )})



    @app .route ('/api/guild/<guild_id>/channels/<channel_id>/delete',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_delete_channel (guild_id ,channel_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio 
        if not bot :return jsonify ({'error':'Бот офлайн'})
        async def do ():
            ch =bot .get_channel (int (channel_id ))
            if ch :await (ch .delete ())
        asyncio .run_coroutine_threadsafe (do (),bot .loop ).result (timeout =10 )
        return jsonify ({'success':True })
