# -*- coding: utf-8 -*-
"""Массовые операции и заметки по участникам (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

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


    @app .route ('/api/member-notes')
    @login_required 
    @role_required ('mod')
    def api_all_member_notes ():
        f ='data/member_notes.json'
        if not os .path .exists (f ):return jsonify ([])
        try :
            with open (f ,encoding ='utf-8')as fp :data =json .load (fp )
        except (json .JSONDecodeError ,ValueError ):
            return jsonify ([])
        return jsonify ([{'id':k ,'name':v .get ('name',k ),'avatar':v .get ('avatar',''),'notes':v .get ('notes',[])}for k ,v in data .items ()if v .get ('notes')])


    @app .route ('/api/member-notes/<member_id>')
    @login_required 
    @role_required ('mod')
    def api_member_notes (member_id ):
        f ='data/member_notes.json'
        if not os .path .exists (f ):return jsonify ([])
        try :
            with open (f ,encoding ='utf-8')as fp :data =json .load (fp )
        except (json .JSONDecodeError ,ValueError ):
            return jsonify ([])
        return jsonify (data .get (member_id ,{}).get ('notes',[]))


    @app .route ('/api/member-notes/<member_id>/add',methods =['POST'])
    @login_required 
    @role_required ('mod')
    def api_add_member_note (member_id ):
        import web .app as _app ;bot =_app .bot_instance 
        f ='data/member_notes.json'
        data ={}
        if os .path .exists (f ):
            try :
                with open (f ,encoding ='utf-8')as fp :data =json .load (fp )
            except (json .JSONDecodeError ,ValueError ):
                data ={}
        if member_id not in data :
            name =member_id 
            avatar =''
            if bot :
                for g in bot .guilds :
                    m =g .get_member (int (member_id ))
                    if m :
                        name =m .display_name 
                        avatar =str (m .display_avatar .url )
                        break 
            data [member_id ]={'name':name ,'avatar':avatar ,'notes':[]}
        note ={'id':str (int (datetime.now(timezone.utc).timestamp ())),'text':request .get_json (silent =True ).get ('text',''),
        'author':session .get ('username'),'created_at':datetime.now(timezone.utc).isoformat ()}
        data [member_id ]['notes'].append (note )
        with open (f ,'w',encoding ='utf-8')as fp :json .dump (data ,fp ,indent =2 ,ensure_ascii =False )
        return jsonify ({'success':True })


    @app .route ('/api/member-notes/<member_id>/<note_id>/delete',methods =['POST'])
    @login_required 
    @role_required ('mod')
    def api_delete_member_note (member_id ,note_id ):
        f ='data/member_notes.json'
        if not os .path .exists (f ):return jsonify ({'success':True })
        try :
            with open (f ,encoding ='utf-8')as fp :data =json .load (fp )
        except (json .JSONDecodeError ,ValueError ):
            return jsonify ({'success':True })
        if member_id in data :
            data [member_id ]['notes']=[n for n in data [member_id ]['notes']if n ['id']!=note_id ]
        with open (f ,'w',encoding ='utf-8')as fp :json .dump (data ,fp ,indent =2 ,ensure_ascii =False )
        return jsonify ({'success':True })


    @app .route ('/api/guild/<guild_id>/purge',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_purge (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio 
        if not bot :return jsonify ({'error':'Бот офлайн'})
        data =request .get_json (silent =True )or {}
        result ={'count':0 }
        async def do ():
            ch =bot .get_channel (int (data ['channel_id']))
            if ch :
                deleted =await (ch .purge (limit =int (data .get ('count',10 ))))
                result ['count']=len (deleted )
        asyncio .run_coroutine_threadsafe (do (),bot .loop ).result (timeout =30 )
        return jsonify ({'success':True ,'count':result ['count']})


    @app .route ('/api/guild/<guild_id>/bulk-roles',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_bulk_role (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio ,discord 
        if not bot :return jsonify ({'error':'Бот офлайн'})
        data =request .get_json (silent =True )or {}
        result ={'count':0 }
        async def do ():
            guild =bot .get_guild (int (guild_id ))
            target_role =guild .get_role (int (data ['target_role']))
            action_role =guild .get_role (int (data ['action_role']))
            if not target_role or not action_role :return 
            for member in target_role .members :
                try :
                    if data ['action']=='add':await (member .add_roles (action_role ))
                    else :await (member .remove_roles (action_role ))
                    result ['count']+=1 
                except Exception as _ex:
                    _log.debug("do(): подавлено: %s", _ex)
        asyncio .run_coroutine_threadsafe (do (),bot .loop ).result (timeout =60 )
        return jsonify ({'success':True ,'count':result ['count']})


    @app .route ('/api/guild/<guild_id>/bulk-dm',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_bulk_dm (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio ,discord 
        if not bot :return jsonify ({'error':'Бот офлайн'})
        data =request .get_json (silent =True )or {}
        result ={'count':0 }
        async def do ():
            guild =bot .get_guild (int (guild_id ))
            role =guild .get_role (int (data ['role_id']))
            if not role :return 
            embed =discord .Embed (title ="📢 Объявление",description =data ['message'],color =0xdc143c )
            embed .set_footer (text ="Hakumo Panel",icon_url =bot .user .display_avatar .url )
            for member in role .members :
                try :
                    await (member .send (embed =embed ))
                    result ['count']+=1 
                except Exception as _ex:
                    _log.debug("do(): подавлено: %s", _ex)
        asyncio .run_coroutine_threadsafe (do (),bot .loop ).result (timeout =120 )
        return jsonify ({'success':True ,'count':result ['count']})


    @app .route ('/api/guild/<guild_id>/bulk-mute',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_bulk_mute (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio ,discord 
        from datetime import timedelta 
        if not bot :return jsonify ({'error':'Бот офлайн'})
        data =request .get_json (silent =True )or {}
        result ={'count':0 }
        async def do ():
            guild =bot .get_guild (int (guild_id ))
            role =guild .get_role (int (data ['role_id']))
            if not role :return 
            duration =int (data .get ('duration',60 ))
            for member in role .members :
                try :
                    await (member .timeout (datetime.now(timezone.utc)+timedelta (minutes =duration ),reason ='Bulk mute'))
                    result ['count']+=1 
                except Exception as _ex:
                    _log.debug("do(): подавлено: %s", _ex)
        asyncio .run_coroutine_threadsafe (do (),bot .loop ).result (timeout =120 )
        return jsonify ({'success':True ,'count':result ['count']})


    @app .route ('/api/guild/<guild_id>/bulk-kick',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_bulk_kick (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio ,discord 
        if not bot :return jsonify ({'error':'Бот офлайн'})
        data =request .get_json (silent =True )or {}
        result ={'count':0 }
        async def do ():
            guild =bot .get_guild (int (guild_id ))
            role =guild .get_role (int (data ['role_id']))
            if not role :return 
            for member in role .members :
                try :
                    await (member .kick (reason ='Bulk kick'))
                    result ['count']+=1 
                except Exception as _ex:
                    _log.debug("do(): подавлено: %s", _ex)
        asyncio .run_coroutine_threadsafe (do (),bot .loop ).result (timeout =120 )
        return jsonify ({'success':True ,'count':result ['count']})


    @app .route ('/api/guild/<guild_id>/bulk-ban',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_bulk_ban (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio ,discord 
        if not bot :return jsonify ({'error':'Бот офлайн'})
        data =request .get_json (silent =True )or {}
        result ={'count':0 }
        async def do ():
            guild =bot .get_guild (int (guild_id ))
            role =guild .get_role (int (data ['role_id']))
            if not role :return 
            for member in role .members :
                try :
                    await (guild .ban (member ,reason ='Bulk ban'))
                    result ['count']+=1 
                except Exception as _ex:
                    _log.debug("do(): подавлено: %s", _ex)
        asyncio .run_coroutine_threadsafe (do (),bot .loop ).result (timeout =180 )
        return jsonify ({'success':True ,'count':result ['count']})


        # ── WARN CONFIG API ───────────────────────────────────────────────────────

    @app .route ('/api/guild/<guild_id>/warn-config',methods =['GET','POST'])
    @login_required 
    @role_required ('admin')
    def api_warn_config (guild_id ):
        f =f'data/warn_config_{guild_id}.json'
        if request .method =='GET':
            if not os .path .exists (f ):
                return jsonify ({'steps':[]})
            with open (f ,'r',encoding ='utf-8')as fp :
                return jsonify (json .load (fp ))
        data =request .get_json (silent =True )or {}
        os .makedirs ('data',exist_ok =True )
        with open (f ,'w',encoding ='utf-8')as fp :
            json .dump (data ,fp ,indent =2 ,ensure_ascii =False )
        return jsonify ({'success':True })


        # ── WARN DM НАСТРОЙКА ─────────────────────────────────────────────────────────

    @app .route ('/api/guild/<guild_id>/warn-dm',methods =['GET','POST'])
    @login_required 
    @role_required ('admin')
    def api_warn_dm (guild_id ):
        f =f'data/warn_dm_{guild_id}.json'
        if request .method =='GET':
            if not os .path .exists (f ):
                return jsonify ({'message':''})
            with open (f ,'r',encoding ='utf-8')as fp :
                return jsonify (json .load (fp ))
        data =request .get_json (silent =True )or {}
        os .makedirs ('data',exist_ok =True )
        with open (f ,'w',encoding ='utf-8')as fp :
            json .dump ({'message':data .get ('message','')},fp ,ensure_ascii =False )
        return jsonify ({'success':True })
