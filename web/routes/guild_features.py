# -*- coding: utf-8 -*-
"""Настройки фич сервера (welcome/autorole/leveling/economy/polls/etc) (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

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


    @app .route ('/api/guild/<guild_id>/welcome-settings',methods =['GET','POST'])
    @login_required 
    @role_required ('admin')
    def api_welcome_settings (guild_id ):
        f =f'data/welcome_{guild_id}.json'
        os .makedirs ('data',exist_ok =True )# Enдлительность data directory exists

        if request .method =='GET':
            if not os .path .exists (f ):
                return jsonify ({})
            try :
                with open (f ,'r',encoding ='utf-8')as fp :
                    return jsonify (json .load (fp ))
            except Exception as e :
                print (f'[WEB][ERR] welcome-settings GET error: {e}')
                return jsonify ({'error':str (e )})

                # POST request
        try :
            data =request .get_json (silent =True )or {}
            if not data :
                return jsonify ({'error':'Данные не переданы'})

            settings ={}
            if os .path .exists (f ):
                with open (f ,'r',encoding ='utf-8')as fp :
                    settings =json .load (fp )

            t =data .pop ('type',None )
            if not t :
                return jsonify ({'error':'Тип заметок не указан'})

            settings [t ]=data 
            with open (f ,'w',encoding ='utf-8')as fp :
                json .dump (settings ,fp ,indent =2 ,ensure_ascii =False )
            print (f'[WEB] welcome-settings saved for guild {guild_id}, type {t}')
            return jsonify ({'success':True })
        except Exception as e :
            print (f'[WEB][ERR] welcome-settings POST error: {e}')
            return jsonify ({'error':str (e )})


    @app .route ('/api/guild/<guild_id>/autorole',methods =['GET','POST'])
    @login_required 
    @role_required ('admin')
    def api_autorole (guild_id ):
        f =f'data/autorole_{guild_id}.json'
        if request .method =='GET':
            if not os .path .exists (f ):
                return jsonify ({'member_roles':[],'girl_roles':[],'boy_roles':[],'bot_roles':[]})
            with open (f )as fp :
                data =json .load (fp )
                # Старый format uyumluluгu
            data .setdefault ('girl_roles',[])
            data .setdefault ('boy_roles',[])
            return jsonify (data )
        data =request .get_json (silent =True )or {}
        settings ={}
        if os .path .exists (f ):
            with open (f ,encoding ='utf-8')as fp :settings =json .load (fp )
            # type -> key mapping
        key_map ={'member':'member_roles','girl':'girl_roles','boy':'boy_roles','bot':'bot_roles'}
        t =data .get ('type','member')
        key =key_map .get (t ,t +'_roles')
        # Frontend hem 'roles' (чoгul) hem 'role' (tekil) yollayabilir; ikisini de принять et
        new_value =data .get ('roles',data .get ('role',[]))
        if not isinstance (new_value ,list ):
            new_value =[]
            # Оставить только строковые id
        new_value =[str (x )for x in new_value if x ]
        settings [key ]=new_value 
        os .makedirs ('data',exist_ok =True )
        with open (f ,'w',encoding ='utf-8')as fp :json .dump (settings ,fp ,indent =2 ,ensure_ascii =False )
        return jsonify ({'success':True ,'key':key ,'value':new_value })


    @app .route ('/api/guild/<guild_id>/leveling',methods =['GET','POST'])
    @login_required 
    @role_required ('mod')
    def api_leveling (guild_id ):
        f =f'data/leveling_{guild_id}.json'
        if request .method =='GET':
            if not os .path .exists (f ):return jsonify ({'enabled':False ,'xp_min':15 ,'xp_max':25 })
            with open (f )as fp :return jsonify (json .load (fp ))
        data =request .get_json (silent =True )or {}
        with open (f ,'w')as fp :json .dump (data ,fp ,indent =2 )
        return jsonify ({'success':True })


    @app .route ('/api/guild/<guild_id>/leaderboard')
    @login_required 
    def api_leaderboard (guild_id ):
        f =f'data/xp_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ([])
        with open (f )as fp :data =json .load (fp )
        lb =sorted (data .values (),key =lambda x :x .get ('xp',0 ),reverse =True )
        return jsonify (lb [:20 ])


    @app .route ('/api/guild/<guild_id>/economy',methods =['GET','POST'])
    @login_required 
    @role_required ('admin')
    def api_economy (guild_id ):
        f =f'data/economy_{guild_id}.json'
        if request .method =='GET':
            if not os .path .exists (f ):return jsonify ({'currency_name':'Coin','currency_emoji':'💰','start_balance':100 ,'daily_reward':50 })
            with open (f )as fp :return jsonify (json .load (fp ))
        data =request .get_json (silent =True )or {}
        with open (f ,'w')as fp :json .dump (data ,fp ,indent =2 )
        return jsonify ({'success':True })


    @app .route ('/api/guild/<guild_id>/economy/shop')
    @login_required 
    def api_economy_shop (guild_id ):
        f =f'data/shop_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ([])
        with open (f )as fp :return jsonify (json .load (fp ))


    @app .route ('/api/guild/<guild_id>/economy/shop/add',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_economy_shop_add (guild_id ):
        f =f'data/shop_{guild_id}.json'
        items =[]
        if os .path .exists (f ):
            with open (f )as fp :items =json .load (fp )
        data =request .get_json (silent =True )or {}
        data ['id']=str (int (datetime.now(timezone.utc).replace(tzinfo=None).timestamp ()))
        items .append (data )
        with open (f ,'w')as fp :json .dump (items ,fp ,indent =2 )
        return jsonify ({'success':True })


    @app .route ('/api/guild/<guild_id>/economy/shop/<item_id>/remove',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_economy_shop_remove (guild_id ,item_id ):
        f =f'data/shop_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ({'success':True })
        with open (f )as fp :items =json .load (fp )
        items =[i for i in items if i .get ('id')!=item_id ]
        with open (f ,'w')as fp :json .dump (items ,fp ,indent =2 )
        return jsonify ({'success':True })


    @app .route ('/api/guild/<guild_id>/economy/rich')
    @login_required 
    def api_economy_rich (guild_id ):
        f =f'data/balance_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ([])
        with open (f )as fp :data =json .load (fp )
        return jsonify (sorted (data .values (),key =lambda x :x .get ('balance',0 ),reverse =True )[:10 ])


    @app .route ('/api/guild/<guild_id>/giveaways')
    @login_required 
    def api_giveaways (guild_id ):
        f =f'data/giveaways_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ([])
        with open (f )as fp :return jsonify (list (json .load (fp ).values ()))


    @app .route ('/api/guild/<guild_id>/giveaways/create',methods =['POST'])
    @login_required 
    @role_required ('mod')
    def api_create_giveaway (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio ,discord 
        if not bot :return jsonify ({'error':'Бот офлайн'})
        data =request .get_json (silent =True )or {}
        gw_id =str (int (datetime.now(timezone.utc).replace(tzinfo=None).timestamp ()))
        from datetime import timedelta 
        ends_at =(datetime.now(timezone.utc).replace(tzinfo=None)+timedelta (minutes =data ['duration'])).isoformat ()
        f =f'data/giveaways_{guild_id}.json'
        gws ={}
        if os .path .exists (f ):
            with open (f )as fp :gws =json .load (fp )
        gws [gw_id ]={
        'id':gw_id ,
        'prize':data ['prize'],
        'winners':data ['winners'],
        'ends_at':ends_at ,
        'status':'active',
        'channel_id':data ['channel_id'],
        'participants':[],
        'message_id':None 
        }
        with open (f ,'w',encoding ='utf-8')as fp :json .dump (gws ,fp ,indent =2 ,ensure_ascii =False )
        def send ():
            from cogs .giveaway import GiveawayView 
            ch =bot .get_channel (int (data ['channel_id']))
            if ch :
                end_ts =int (datetime.now(timezone.utc).replace(tzinfo=None).timestamp ())+int (data ['duration'])*60 
                embed =discord .Embed (
                title ='🎉 ✨ НАЧАЛСЯ ЗАМЕЧАТЕЛЬНЫЙ РОЗЫГРЫШ! ✨ 🎉',
                description =(
                f"\n🏆 **НАГРАДА:** `{data['prize']}`\n"
                "\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "🎟️ **Чтобы участвовать:** нажми кнопку 🎉 **«Участвовать»** ниже\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"\n⏳ **Время завершения:** <t:{end_ts}:R>\n"
                f"📅 **Точное время:** <t:{end_ts}:f>\n"
                "\n✅ Участие абсолютно **БЕСПЛАТНО** и **ОТКРЫТО**!\n"
                "🍀 Испытай удачу и **ВЫИГРАЙ**! 🍀\n"
                ),
                color =0xFFD700 
                )
                embed .add_field (name ='🏅 Количество победителей',value =f'**{data["winners"]} ЧЕЛОВЕК ВЫИГРАЕТ!** 👑',inline =False )
                embed .add_field (name ='👥 Текущие участники',value =f'**0/{data["winners"]}** 🔥',inline =True )
                embed .add_field (name ='📊 Статистика',value ='Открывается...',inline =True )
                embed .set_footer (text =f'🎯 Giveaway ID: {gw_id} | Система: Bot Giveaway v2')
                view =GiveawayView (gw_id ,guild_id )
                msg =_run_async (ch .send (embed =embed ,view =view ))
                gws [gw_id ]['message_id']=str (msg .id )
                with open (f ,'w',encoding ='utf-8')as fp :
                    json .dump (gws ,fp ,indent =2 ,ensure_ascii =False )
        asyncio .run_coroutine_threadsafe (send (),bot .loop )
        return jsonify ({'success':True })


    @app .route ('/api/guild/<guild_id>/giveaways/<gw_id>/end',methods =['POST'])
    @login_required 
    @role_required ('mod')
    def api_end_giveaway (guild_id ,gw_id ):
        f =f'data/giveaways_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ({'error':'Не найдено'})
        with open (f )as fp :gws =json .load (fp )
        if gw_id in gws :
            gws [gw_id ]['status']='ended'
            with open (f ,'w')as fp :json .dump (gws ,fp ,indent =2 )
        return jsonify ({'success':True })


    @app .route ('/api/guild/<guild_id>/giveaways/<gw_id>/join',methods =['POST'])
    @login_required 
    def api_join_giveaway (guild_id ,gw_id ):
        f =f'data/giveaways_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ({'error':'Розыгрыш не найден'})
        with open (f )as fp :gws =json .load (fp )
        if gw_id not in gws :return jsonify ({'error':'Розыгрыш не найден'})
        gw =gws [gw_id ]
        if gw .get ('status')!='active':return jsonify ({'error':'Розыгрыш не активен'})
        participants =gw .setdefault ('participants',[])
        username =session .get ('username','')
        if username in participants :return jsonify ({'error':'Ты уже присоединился!'})
        participants .append (username )
        with open (f ,'w')as fp :json .dump (gws ,fp ,indent =2 )
        return jsonify ({'success':True })


    @app .route ('/api/guild/<guild_id>/polls')
    @login_required 
    def api_polls (guild_id ):
        f =f'data/polls_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ([])
        with open (f )as fp :return jsonify (list (json .load (fp ).values ()))


    @app .route ('/api/guild/<guild_id>/polls/<poll_id>/vote',methods =['POST'])
    @login_required 
    @role_required ('mod')
    def api_vote_poll (guild_id ,poll_id ):
        f =f'data/polls_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ({'error':'Опрос не найден'})
        with open (f ,encoding ='utf-8')as fp :polls =json .load (fp )
        if poll_id not in polls :return jsonify ({'error':'Опрос не найден'})
        data =request .get_json (silent =True )or {}
        option_index =data .get ('option_index',0 )
        poll =polls [poll_id ]
        voters =poll .setdefault ('voters',[])
        username =session .get ('username','')
        if username in voters :return jsonify ({'error':'Ты уже голосовал!'})
        if 0 <=option_index <len (poll ['options']):
            poll ['options'][option_index ]['votes']=poll ['options'][option_index ].get ('votes',0 )+1 
            voters .append (username )
            with open (f ,'w',encoding ='utf-8')as fp :json .dump (polls ,fp ,indent =2 ,ensure_ascii =False )
            return jsonify ({'success':True })
        return jsonify ({'error':'Неверный выбрать'})


    @app .route ('/api/guild/<guild_id>/polls/create',methods =['POST'])
    @login_required 
    @role_required ('owner')
    def api_create_poll (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio ,discord 
        if not bot :return jsonify ({'error':'Бот офлайн'})
        data =request .get_json (silent =True )or {}
        poll_id =str (int (datetime.now(timezone.utc).replace(tzinfo=None).timestamp ()))
        f =f'data/polls_{guild_id}.json'
        polls ={}
        if os .path .exists (f ):
            with open (f )as fp :polls =json .load (fp )
        entry ={'id':poll_id ,'question':data ['question'],'created_at':datetime.now(timezone.utc).replace(tzinfo=None).isoformat (),
        'options':[{'emoji':o ['emoji'],'text':o ['text'],'votes':0 }for o in data ['options']]}
        polls [poll_id ]=entry 
        with open (f ,'w')as fp :json .dump (polls ,fp ,indent =2 )
        def send ():
            ch =bot .get_channel (int (data ['channel_id']))
            if ch :
                desc ='\n'.join ([f"{o['emoji']} **{o['text']}**"for o in data ['options']])
                embed =discord .Embed (title =f"📊 {data['question']}",description =desc ,color =0xdc143c )
                embed .set_footer (text =f"ID опроса: {poll_id}")
                msg =_run_async (ch .send (embed =embed ))
                for o in data ['options']:
                    try :_run_async (msg .add_reaction (o ['emoji']))
                    except Exception as _ex:
                        _log.debug("send(): подавлено: %s", _ex)
        asyncio .run_coroutine_threadsafe (send (),bot .loop )
        return jsonify ({'success':True })


    @app .route ('/api/guild/<guild_id>/custom-commands')
    @login_required 
    def api_custom_commands (guild_id ):
        f =f'data/custom_cmds_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ([])
        with open (f )as fp :return jsonify (list (json .load (fp ).values ()))


    @app .route ('/api/guild/<guild_id>/custom-commands/create',methods =['POST'])
    @login_required 
    @role_required ('owner')
    def api_create_custom_command (guild_id ):
        data =request .get_json (silent =True )or {}
        f =f'data/custom_cmds_{guild_id}.json'
        cmds ={}
        if os .path .exists (f ):
            with open (f )as fp :cmds =json .load (fp )
        cmd_id =str (int (datetime.now(timezone.utc).replace(tzinfo=None).timestamp ()))
        cmds [cmd_id ]={'id':cmd_id ,'trigger':data ['trigger'],'response':data ['response'],
        'type':data .get ('type','text'),'uses':0 ,'created_at':datetime.now(timezone.utc).replace(tzinfo=None).isoformat ()}
        with open (f ,'w')as fp :json .dump (cmds ,fp ,indent =2 )
        return jsonify ({'success':True })


    @app .route ('/api/guild/<guild_id>/custom-commands/<cmd_id>/delete',methods =['POST'])
    @login_required 
    @role_required ('owner')
    def api_delete_custom_command (guild_id ,cmd_id ):
        f =f'data/custom_cmds_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ({'success':True })
        with open (f )as fp :cmds =json .load (fp )
        cmds .pop (cmd_id ,None )
        with open (f ,'w')as fp :json .dump (cmds ,fp ,indent =2 )
        return jsonify ({'success':True })


    @app .route ('/api/guild/<guild_id>/scheduled-messages')
    @login_required 
    def api_scheduled_messages (guild_id ):
        f =f'data/scheduled_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ([])
        with open (f )as fp :return jsonify (list (json .load (fp ).values ()))


    @app .route ('/api/guild/<guild_id>/scheduled-messages/create',methods =['POST'])
    @login_required 
    @role_required ('mod')
    def api_create_scheduled_message (guild_id ):
        data =request .get_json (silent =True )or {}
        f =f'data/scheduled_{guild_id}.json'
        msgs ={}
        if os .path .exists (f ):
            with open (f )as fp :msgs =json .load (fp )
        msg_id =str (int (datetime.now(timezone.utc).replace(tzinfo=None).timestamp ()))
        msgs [msg_id ]={'id':msg_id ,'channel_id':data ['channel_id'],'channel_name':'',
        'content':data ['content'],'interval':data ['interval'],
        'next_run':data .get ('start_time',datetime.now(timezone.utc).replace(tzinfo=None).isoformat ()),
        'active':True ,'created_at':datetime.now(timezone.utc).replace(tzinfo=None).isoformat ()}
        with open (f ,'w')as fp :json .dump (msgs ,fp ,indent =2 )
        return jsonify ({'success':True })


    @app .route ('/api/guild/<guild_id>/scheduled-messages/<msg_id>/delete',methods =['POST'])
    @login_required 
    @role_required ('mod')
    def api_delete_scheduled_message (guild_id ,msg_id ):
        f =f'data/scheduled_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ({'success':True })
        with open (f )as fp :msgs =json .load (fp )
        msgs .pop (msg_id ,None )
        with open (f ,'w')as fp :json .dump (msgs ,fp ,indent =2 )
        return jsonify ({'success':True })


    @app .route ('/api/guild/<guild_id>/scheduled-messages/<msg_id>/toggle',methods =['POST'])
    @login_required 
    @role_required ('mod')
    def api_toggle_scheduled_message (guild_id ,msg_id ):
        f =f'data/scheduled_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ({'success':False ,'error':'Не найдено'}),404
        with open (f )as fp :msgs =json .load (fp )
        if msg_id not in msgs :
            return jsonify ({'success':False ,'error':'Не найдено'}),404
        msgs [msg_id ]['active']=not bool (msgs [msg_id ].get ('active',True ))
        with open (f ,'w')as fp :json .dump (msgs ,fp ,indent =2 )
        return jsonify ({'success':True ,'active':msgs [msg_id ]['active']})
