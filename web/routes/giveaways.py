# -*- coding: utf-8 -*-
"""Розыгрыши (короткие пути) (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

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


    @app .route ('/api/giveaway/<guild_id>',methods =['GET'])
    @login_required 
    @role_required ('admin')
    def api_giveaway_list (guild_id ):
        f =f'data/giveaways_{guild_id}.json'
        if not os .path .exists (f ):
            import web .app as _app
            if _app ._demo_mode ():
                # демо: пара примеров, чтобы страница не висела «Розыгрышей нет»
                import datetime as _dt
                now =_dt .datetime .now ()
                return jsonify ([
                {'id':'gw-demo-1','prize':'Discord Nitro · 1 месяц','winners':1 ,'status':'live',
                 'ends_at':(now +_dt .timedelta (hours =5 )).isoformat (),'participants':184 ,'channel_id':'1004'},
                {'id':'gw-demo-2','prize':'Роль «Бустер» на 30 дней','winners':3 ,'status':'live',
                 'ends_at':(now +_dt .timedelta (days =2 )).isoformat (),'participants':96 ,'channel_id':'2002'},
                {'id':'gw-demo-3','prize':'1 000 монет экономики','winners':5 ,'status':'ended',
                 'ends_at':(now -_dt .timedelta (days =1 )).isoformat (),'participants':310 ,'channel_id':'2002'},
                ])
            return jsonify ([])
        with open (f ,encoding ='utf-8')as fp :
            data =json .load (fp )
        result =[]
        for gw_id ,gw in data .items ():
            result .append ({
            'id':gw_id ,
            'prize':gw .get ('prize','?'),
            'winners':gw .get ('winners',1 ),
            'status':gw .get ('status','unknown'),
            'ends_at':gw .get ('ends_at',''),
            'participants':len (gw .get ('participants',[])),
            'channel_id':gw .get ('channel_id',''),
            })
        result .sort (key =lambda x :x ['ends_at'],reverse =True )
        return jsonify (result )


    @app .route ('/api/giveaway/<guild_id>/create',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_giveaway_create (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio ,random 
        from datetime import timedelta 
        data_req =request .get_json (silent =True )or {}
        prize =data_req .get ('prize','').strip ()
        winners =int (data_req .get ('winners',1 ))
        minutes =int (data_req .get ('minutes',60 ))
        channel_id =data_req .get ('channel_id','')
        if not prize or not channel_id :
            return jsonify ({'error':'Не заполнено поле'}),400 

        if not bot :
            return jsonify ({'error':'Бот офлайн'}),503 

        guild =bot .get_guild (int (guild_id ))
        if not guild :
            return jsonify ({'error':'Сервер не найден'}),404 

        channel =guild .get_channel (int (channel_id ))
        if not channel :
            return jsonify ({'error':'Канал не найден'}),404 

        ends_at =datetime.now(timezone.utc).replace(tzinfo=None)+timedelta (minutes =minutes )
        gw_id =str (int (ends_at .timestamp ()))

        def _send ():
            embed =discord .Embed (
            title ="🎉  РОЗЫГРЫШ НАЧАЛСЯ!",
            color =0x2ECC71 ,
            timestamp =ends_at 
            )
            embed .description =(
            f"**🏆 Награда:** `{prize}`\n\n"
            "Чтобы участвовать, нажми кнопку **🎉 Участвовать**!\n"
            f"Giveaway <t:{int(ends_at.timestamp())}:R> sona eriyor."
            )
            embed .add_field (name ="👥 Участники",value =f"0/{winners}",inline =True )
            embed .add_field (name ="🏆 Победителей",value =str (winners ),inline =True )
            embed .add_field (name ="⏰ Завершение",value =f"<t:{int(ends_at.timestamp())}:F>",inline =True )
            embed .set_footer (text =f"{guild.name} • Giveaway Система")

            from cogs .giveaway import GiveawayView 
            view =GiveawayView (gw_id ,guild_id )
            msg =_run_async (channel .send (embed =embed ,view =view ))

            os .makedirs ('data',exist_ok =True )
            f =f'data/giveaways_{guild_id}.json'
            gws ={}
            if os .path .exists (f ):
                with open (f ,encoding ='utf-8')as fp :
                    gws =json .load (fp )
            gws [gw_id ]={
            'prize':prize ,'winners':winners ,
            'ends_at':ends_at .isoformat (),
            'channel_id':str (channel .id ),
            'message_id':str (msg .id ),
            'status':'active',
            'participants':[],
            'user_info':{},
            }
            with open (f ,'w',encoding ='utf-8')as fp :
                json .dump (gws ,fp ,indent =2 ,ensure_ascii =False )

        asyncio .run_coroutine_threadsafe (_send (),bot .loop ).result (timeout =10 )
        return jsonify ({'ok':True ,'id':gw_id })


    @app .route ('/api/giveaway/<guild_id>/<gw_id>/end',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_giveaway_end (guild_id ,gw_id ):
        f =f'data/giveaways_{guild_id}.json'
        if not os .path .exists (f ):
            return jsonify ({'error':'Не найдено'}),404 
        with open (f ,encoding ='utf-8')as fp :
            gws =json .load (fp )
        if gw_id not in gws :
            return jsonify ({'error':'Розыгрыш не найден'}),404 
        gws [gw_id ]['status']='ended'
        with open (f ,'w',encoding ='utf-8')as fp :
            json .dump (gws ,fp ,indent =2 ,ensure_ascii =False )
        return jsonify ({'ok':True })


    @app .route ('/api/giveaway/<guild_id>/<gw_id>/delete',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_giveaway_delete (guild_id ,gw_id ):
        f =f'data/giveaways_{guild_id}.json'
        if not os .path .exists (f ):
            return jsonify ({'ok':True })
        with open (f ,encoding ='utf-8')as fp :
            gws =json .load (fp )
        gws .pop (gw_id ,None )
        with open (f ,'w',encoding ='utf-8')as fp :
            json .dump (gws ,fp ,indent =2 ,ensure_ascii =False )
        return jsonify ({'ok':True })
