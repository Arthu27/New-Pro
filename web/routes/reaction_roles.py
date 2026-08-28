# -*- coding: utf-8 -*-
"""Реакции-роли API (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

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


    @app .route ('/api/guild/<guild_id>/reaction-roles')
    @login_required 
    def api_reaction_roles (guild_id ):
        f =f'data/rr_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ([])
        with open (f )as fp :return jsonify (list (json .load (fp ).values ()))


    @app .route ('/api/guild/<guild_id>/reaction-roles/create',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_create_reaction_role (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio ,discord 
        data =request .get_json (silent =True )or {}
        title =str (data .get ('title')or '').strip ()[:200 ]
        ch_id =str (data .get ('channel_id')or '').strip ()
        ptype =data .get ('type','emoji')# 'emoji' or 'select'
        if ptype not in ('emoji','select'):
            ptype ='emoji'
        entries =data .get ('entries')if isinstance (data .get ('entries'),list )else []
        if not title :
            return jsonify ({'error':'Укажите заголовок панели'}),400 
        if not ch_id :
            return jsonify ({'error':'Выберите канал панели'}),400 
        entries_with_names =[]
        seen =set ()
        for e in entries :
            if not isinstance (e ,dict ):continue 
            role_id =str (e .get ('role_id')or '').strip ()
            if not role_id :continue 
            emoji =str (e .get ('emoji')or '').strip ()if ptype =='emoji'else ''
            role_name =role_id 
            try :
                import web .app as _appr
                from web .routes .guild_admin import _demo_roles_load
                if _appr ._demo_mode ():
                    for dr in _demo_roles_load (guild_id ):
                        if str (dr .get ('id'))==role_id :
                            role_name =str (dr .get ('name')or role_id )
                            break 
                elif bot :
                    g =bot .get_guild (int (guild_id ))
                    if g is not None :
                        r =g .get_role (int (role_id ))
                        if r is not None :
                            role_name =r .name 
            except Exception as _ex :
                _log.debug("role_name: подавлено: %s", _ex )
            if role_id in seen :continue 
            seen .add (role_id )
            entries_with_names .append ({'emoji':emoji ,'role_id':role_id ,'role_name':role_name })
        if not entries_with_names :
            return jsonify ({'error':'Добавьте хотя бы одну роль'}),400 
        if ptype =='emoji'and any (not e ['emoji']for e in entries_with_names ):
            return jsonify ({'error':'Для emoji-панели у каждой роли нужен эмодзи'}),400 
        import random as _rnd
        rr_id ='%d-%s' % (int (datetime.now(timezone.utc).timestamp ()*1000 ),
                          ''.join (_rnd .choices ('abcdef0123456789',k =4 )))
        f =f'data/rr_{guild_id}.json'
        rrs ={}
        if os .path .exists (f ):
            try :
                with open (f ,encoding ='utf-8')as fp :rrs =json .load (fp )
            except Exception :
                rrs ={}
        rrs [rr_id ]={'id':rr_id ,'title':title ,'channel_id':ch_id ,'type':ptype ,
        'entries':entries_with_names ,'guild_id':str (guild_id )}
        os .makedirs ('data',exist_ok =True )
        with open (f ,'w',encoding ='utf-8')as fp :json .dump (rrs ,fp ,indent =2 ,ensure_ascii =False )
        if not bot :
            if _app ._demo_mode ():
                _fire_panel_notification ('reaction_roles',f"Панель ролей создана: {title }",f"Канал {ch_id } · демо-режим")
                return jsonify ({'success':True ,'demo':True ,'id':rr_id ,
                    'message':f"Демо-режим: панель «{title }» сохранена — при живом боте она уйдёт в Discord"})
            return jsonify ({'error':'Бот офлайн — создание недоступно'})

        async def send ():
            ch =bot .get_channel (int (ch_id ))
            if not ch :
                raise RuntimeError ('Канал панели не найден — возможно, бот его не видит')
            desc ='\n'.join ([f"{e['emoji']+' ' if e['emoji'] else ''}**{e['role_name']}**"for e in entries_with_names ])
            embed =discord .Embed (title =title ,description =desc ,color =0xdc143c )
            if ptype =='select':
                msg =await ch .send (embed =embed )
                try :
                    cog =bot .get_cog ('ReactionRolesCog')
                    if cog and hasattr (cog ,'register_select_panel'):
                        await cog .register_select_panel (int (msg .id ),rrs [rr_id ])
                except Exception as _ex :
                    _log.debug("send(): select-панель: %s", _ex )
            else :
                msg =await ch .send (embed =embed )
                for e in entries_with_names :
                    try :
                        await msg .add_reaction (e ['emoji'])
                    except Exception as _ex :
                        _log.debug("send(): реакция %s: %s", e ['emoji'], _ex )
            rrs [rr_id ]['message_id']=str (msg .id )
            with open (f ,'w',encoding ='utf-8')as fp2 :json .dump (rrs ,fp2 ,indent =2 ,ensure_ascii =False )

        try :
            asyncio .run_coroutine_threadsafe (send (),bot .loop ).result (timeout =25 )
        except Exception as _ex :
            msg =str (_ex )
            if 'Forbidden' in msg or 'Missing Access' in msg :
                msg ='Discord запретил отправку: у бота нет прав на этот канал'
            return jsonify ({'error':f"Не удалось создать панель: {msg }"[:200 ]}),502 
        _fire_panel_notification ('reaction_roles',f"Панель ролей создана: {title }",f"Канал {ch_id }")
        return jsonify ({'success':True ,'id':rr_id })


    @app .route ('/api/guild/<guild_id>/reaction-roles/<rr_id>/delete',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_delete_reaction_role (guild_id ,rr_id ):
        f =f'data/rr_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ({'success':True })
        try :
            with open (f ,encoding ='utf-8')as fp :rrs =json .load (fp )
        except Exception :
            return jsonify ({'success':True })
        removed =rrs .pop (rr_id ,None )
        with open (f ,'w',encoding ='utf-8')as fp :json .dump (rrs ,fp ,indent =2 ,ensure_ascii =False )
        _fire_panel_notification ('reaction_roles','Панель ролей удалена',
            str (removed .get ('title')or rr_id )if isinstance (removed ,dict )else str (rr_id ))
        return jsonify ({'success':True })
