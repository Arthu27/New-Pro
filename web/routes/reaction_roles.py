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
        if not bot :return jsonify ({'error':'Бот офлайн'})
        data =request .get_json (silent =True )or {}
        rr_id =str (int (datetime.now(timezone.utc).replace(tzinfo=None).timestamp ()))
        f =f'data/rr_{guild_id}.json'
        rrs ={}
        if os .path .exists (f ):
            with open (f )as fp :rrs =json .load (fp )
        guild =bot .get_guild (int (guild_id ))
        ptype =data .get ('type','emoji')# 'emoji' or 'select'
        entries_with_names =[]
        for e in data .get ('entries',[]):
            role =guild .get_role (int (e ['role_id']))if guild else None 
            entries_with_names .append ({'emoji':e .get ('emoji',''),'role_id':e ['role_id'],'role_name':role .name if role else e ['role_id']})
        rrs [rr_id ]={'id':rr_id ,'title':data ['title'],'channel_id':data ['channel_id'],'type':ptype ,'entries':entries_with_names ,'guild_id':str (guild_id )}
        with open (f ,'w')as fp :json .dump (rrs ,fp ,indent =2 )
        def send ():
            ch =bot .get_channel (int (data ['channel_id']))
            if ch :
                desc ='\n'.join ([f"**{e['role_name']}**"for e in entries_with_names ])
                embed =discord .Embed (title =data ['title'],description =desc ,color =0xdc143c )
                if ptype =='select':
                    # Select-menu panel: attach a persistent View via the cog
                    msg =_run_async (ch .send (embed =embed ))
                    try :
                        cog =bot .get_cog ('ReactionRolesCog')
                        if cog and hasattr (cog ,'register_select_panel'):
                            _run_async (cog .register_select_panel (int (msg .id ),rrs [rr_id ]))
                    except Exception as _ex:
                        _log.debug("send(): подавлено: %s", _ex)
                else :
                    msg =_run_async (ch .send (embed =embed ))
                    for e in entries_with_names :
                        if e ['emoji']:
                            try :_run_async (msg .add_reaction (e ['emoji']))
                            except Exception as _ex:
                                _log.debug("send(): подавлено: %s", _ex)
                rrs [rr_id ]['message_id']=str (msg .id )
                with open (f ,'w')as fp2 :json .dump (rrs ,fp2 ,indent =2 )
        asyncio .run_coroutine_threadsafe (send (),bot .loop )
        return jsonify ({'success':True })


    @app .route ('/api/guild/<guild_id>/reaction-roles/<rr_id>/delete',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_delete_reaction_role (guild_id ,rr_id ):
        f =f'data/rr_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ({'success':True })
        with open (f )as fp :rrs =json .load (fp )
        rrs .pop (rr_id ,None )
        with open (f ,'w')as fp :json .dump (rrs ,fp ,indent =2 )
        return jsonify ({'success':True })
