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


    @app .route ('/api/guild/<guild_id>/rules',methods =['GET','POST'])
    @login_required 
    @role_required ('admin')
    def api_rules (guild_id ):
        f =f'data/rules_{guild_id}.json'
        os .makedirs ('data',exist_ok =True )
        if request .method =='GET':
            if not os .path .exists (f ):return jsonify ([])
            with open (f ,encoding ='utf-8')as fp :return jsonify (json .load (fp ))
        rules =request .get_json (force =True ,silent =True )
        if rules is None :rules =[]
        with open (f ,'w',encoding ='utf-8')as fp :json .dump (rules ,fp ,indent =2 ,ensure_ascii =False )
        return jsonify ({'success':True })


    @app .route ('/api/guild/<guild_id>/rules/publish',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_publish_rules (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio ,discord 
        if not bot :return jsonify ({'error':'Бот офлайн'})
        data =request .get_json (silent =True )or {}
        def send ():
            ch =bot .get_channel (int (data ['channel_id']))
            if ch :
                desc ='\n'.join ([f"**{i+1}.** {r}"for i ,r in enumerate (data ['rules'])])
                embed =discord .Embed (title ="Правила сервера",description =desc ,color =0x4f46e5 )
                embed .set_footer (text ="Нарушение правил ведёт к наказанию.")
                _run_async (ch .send (embed =embed ))
        asyncio .run_coroutine_threadsafe (send (),bot .loop ).result (timeout =10 )
        return jsonify ({'success':True })
