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
        import web .app as _app ;bot =_app .bot_instance 

        def _member_name (uid ,user_info ,fallback =''):
            """Имя участника: user_info → кэш бота → демо-состав → ID."""
            info =user_info .get (str (uid ))or user_info .get (uid )or {}
            name =(info .get ('name')or info .get ('username')
                   or info .get ('display_name')or '')
            if name :
                return str (name )
            if bot :
                try :
                    g =bot .get_guild (int (guild_id ))
                    mem =g .get_member (int (uid ))if g else None 
                    if mem :
                        return mem .display_name 
                except Exception as _ex:
                    _log.debug("api_giveaway_list(): подавлено: %s", _ex)
            return fallback or f'ID {uid}'

        f =f'data/giveaways_{guild_id}.json'
        if not os .path .exists (f ):
            if _app ._demo_mode ():
                # демо: живые карточки с именами участников — как в Discord,
                # а не одна цифра. Побеждёт красивая двойка :)
                import datetime as _dt 
                import random as _rnd 
                _rnd .seed (42 )
                _names =['GhostBlade','Sonya','Artem','Lina','Max','Dasha',
                'Kira','Vortex','NyanCat','Ryzen','Asuna','Kirito']
                _now =_dt .datetime .now ()
                def _demo_participants (n ):
                    pick =_rnd .sample (_names ,min (n ,len (_names )))
                    return [{'id':str (9000 +i ),'name':nm }
                    for i ,nm in enumerate (pick )]
                def _demo_gw (gid ,prize ,winners ,status ,c_h ,e_dt ,nparts ,widx ):
                    parts =_demo_participants (nparts )
                    wlist =[parts [i ]for i in widx if i <len (parts )]
                    return {'id':gid ,'prize':prize ,'winners':winners ,'status':status ,
                    'created_at':(_now -_dt .timedelta (hours =c_h )).isoformat (),
                    'ends_at':(_now +_dt .timedelta (**e_dt )).isoformat (),
                    'channel_id':'1004'if gid =='gw-demo-1'else '2002' ,
                    'participants':parts ,
                    'winner_ids':[p ['id']for p in wlist ],
                    'winners_list':wlist }
                return jsonify ([
                _demo_gw ('gw-demo-1','Discord Nitro · 1 месяц',1 ,'active',1 ,{'hours':5 },12 ,[]),
                _demo_gw ('gw-demo-2','Роль «Бустер» на 30 дней',3 ,'active',10 ,{'days':2 },9 ,[]),
                _demo_gw ('gw-demo-3','1 000 монет экономики',2 ,'ended',72 ,{'days':-1 },10 ,[1 ,4 ]),
                ])
            return jsonify ([])
        with open (f ,encoding ='utf-8')as fp :
            data =json .load (fp )
        result =[]
        for gw_id ,gw in data .items ():
            user_info =gw .get ('user_info',{})or {}
            parts =gw .get ('participants',[])or []
            part_list =[
            {'id':str (uid ),'name':_member_name (uid ,user_info )}
            for uid in parts [:100 ]
            ]
            winner_ids =set (str (w )for w in gw .get ('winner_ids',[])or [])
            winners =[
            {'id':str (uid ),'name':_member_name (uid ,user_info )}
            for uid in gw .get ('winner_ids',[])or []
            ]
            result .append ({
            'id':gw_id ,
            'prize':gw .get ('prize','?'),
            'winners':gw .get ('winners',1 ),
            'status':gw .get ('status','unknown'),
            'created_at':gw .get ('created_at',''),
            'ends_at':gw .get ('ends_at',''),
            'participants':part_list ,
            'participant_count':len (parts ),
            'winner_ids':sorted (winner_ids ),
            'winners_list':winners ,
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

        ends_at =datetime.now(timezone.utc)+timedelta (minutes =minutes )
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
            'created_at':datetime .now(timezone.utc).isoformat (),
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
        import random 
        f =f'data/giveaways_{guild_id}.json'
        if not os .path .exists (f ):
            return jsonify ({'error':'Не найдено'}),404 
        with open (f ,encoding ='utf-8')as fp :
            gws =json .load (fp )
        if gw_id not in gws :
            return jsonify ({'error':'Розыгрыш не найден'}),404 
        gw =gws [gw_id ]
        gw ['status']='ended'
        # Определяем победителей прямо сейчас (как это делает ког по расписанию)
        parts =gw .get ('participants',[])or []
        n =min (int (gw .get ('winners',1 )or 1 ),len (parts ))
        gw ['winner_ids']=[str (w )for w in random .sample (parts ,n )]if parts else []
        with open (f ,'w',encoding ='utf-8')as fp :
            json .dump (gws ,fp ,indent =2 ,ensure_ascii =False )
        return jsonify ({'ok':True ,'winners':gw ['winner_ids']})


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
