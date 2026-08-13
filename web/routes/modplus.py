# -*- coding: utf-8 -*-
"""Sticky/ghost/пруфы/паника (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

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


    def _modplus_cog ():
        import web .app as _app 
        bot =_app .bot_instance 
        return (bot .get_cog ('ModPlus')if bot else None ),bot 


    def _active_guild ():
        import web .app as _app 
        gid =active_guild_id ()
        _c ,bot =_modplus_cog ()
        return bot .get_guild (int (gid ))if bot and gid else None 


    @app .route ('/api/sticky',methods =['GET'])
    @login_required 
    @role_required ('mod')
    def api_sticky_list ():
        from cogs .mod_plus import _sticky_path ,_load_json 
        guild =_active_guild ()
        data =_load_json (_sticky_path (guild .id ),{})if guild else {}
        items =[]
        for cid ,entry in data .items ():
            ch =guild .get_channel (int (cid ))if guild else None 
            items .append ({
                'channel_id':str (cid ),
                'channel_name':getattr (ch ,'name',str (cid )),
                'text':(entry .get ('text')or '')[:400 ],
                'set_at':entry .get ('set_at',''),
            })
        return jsonify ({'success':True ,'items':items })


    @app .route ('/api/sticky',methods =['POST'])
    @login_required 
    @role_required ('mod')
    def api_sticky_create ():
        from cogs .mod_plus import _sticky_path ,_load_json ,_save_json 
        data =request .get_json (silent =True )or {}
        cid =str (data .get ('channel_id','')).strip ()
        text =(data .get ('text')or '').strip ()
        if not cid .isdigit ()or not text or len (text )>1900 :
            return jsonify ({'success':False ,'error':'Канал или текст неверные (текст до 1900 символов)'}),400 
        guild =_active_guild ()
        if not guild :
            return jsonify ({'success':False ,'error':'Бот офлайн'}),503 
        if not guild .get_channel (int (cid )):
            return jsonify ({'success':False ,'error':'Канал не найден на сервере'}),404 
        sdata =_load_json (_sticky_path (guild .id ),{})
        old =sdata .get (cid )
        sdata [cid ]={'text':text ,'msg_id':None ,'author_id':0,
        'set_at':datetime.now(timezone.utc).isoformat (),
        'by_panel':session .get ('username')}
        _save_json (_sticky_path (guild .id ),sdata )

        cog ,bot =_modplus_cog ()
        reposted =None 
        if cog :
            try :
                if old and old .get ('msg_id'):
                    _run_async (cog .delete_sticky_message_remote (guild ,cid ,old ['msg_id']))
                reposted =_run_async (cog .repost_remote (guild ,cid ))
            except Exception as e :
                reposted =False 
                print (f'[MOD+] sticky repost из панели: {e}')
        _fire_panel_notification ('sticky',f"📌 Липкое в #{cid}",f"{session.get('username')}: {text[:120]}")
        return jsonify ({'success':True ,'reposted':bool (reposted )})


    @app .route ('/api/sticky',methods =['DELETE'])
    @login_required 
    @role_required ('mod')
    def api_sticky_delete ():
        from cogs .mod_plus import _sticky_path ,_load_json ,_save_json 
        data =request .get_json (silent =True )or {}
        cid =str (data .get ('channel_id','')).strip ()
        if not cid .isdigit ():
            return jsonify ({'success':False ,'error':'Нужен channel_id'}),400 
        guild =_active_guild ()
        if not guild :
            return jsonify ({'success':False ,'error':'Бот офлайн'}),503 
        sdata =_load_json (_sticky_path (guild .id ),{})
        entry =sdata .pop (cid ,None )
        if not entry :
            return jsonify ({'success':False ,'error':'В этом канале липкого нет'}),404 
        _save_json (_sticky_path (guild .id ),sdata )
        cog ,bot =_modplus_cog ()
        if cog and entry .get ('msg_id'):
            try :
                _run_async (cog .delete_sticky_message_remote (guild ,cid ,entry ['msg_id']))
            except Exception as _ex:
                _log.debug("api_sticky_delete(): подавлено: %s", _ex)
        return jsonify ({'success':True })


    # ── Тихий мут (ghost mute) ────────────────────────────────────────────
    @app .route ('/api/ghost',methods =['GET'])
    @login_required
    @role_required ('mod')
    def api_ghost_list ():
        from cogs .mod_plus import ghost_entries
        guild =_active_guild ()
        data =ghost_entries (guild .id )if guild else {}
        items =[]
        for uid ,e in data .items ():
            m =guild .get_member (int (uid ))if guild else None
            items .append ({
                'user_id':str (uid ),
                'name':str (m )if m else f'ID {uid}',
                'reason':e .get ('reason',''),
                'by':e .get ('by',''),
                'until':e .get ('until'),
                'suppressed':e .get ('suppressed')or 0 ,
                'set_at':e .get ('set_at',''),
            })
        items .sort (key =lambda x :x ['set_at'],reverse =True )
        return jsonify ({'success':True ,'items':items })


    @app .route ('/api/ghost',methods =['POST'])
    @login_required
    @role_required ('mod')
    def api_ghost_add ():
        from cogs .mod_plus import ghost_add ,parse_ghost_duration
        data =request .get_json (silent =True )or {}
        uid =str (data .get ('user_id','')).strip ()
        reason =(data .get ('reason')or 'Через панель')[:300 ]
        if not uid .isdigit ():
            return jsonify ({'success':False ,'error':'Нужен числовой ID участника'}),400
        guild =_active_guild ()
        if not guild :
            return jsonify ({'success':False ,'error':'Бот офлайн'}),503
        member =guild .get_member (int (uid ))
        if not member :
            try :
                member =_run_async (guild .fetch_member (int (uid )))
            except Exception :
                member =None
        if not member :
            return jsonify ({'success':False ,'error':'Участник не найден на сервере'}),404
        if getattr (member ,'bot',False ):
            return jsonify ({'success':False ,'error':'Ботов призраками не делаем'}),400
        if getattr (guild ,'owner_id',None )and int (uid )==guild .owner_id :
            return jsonify ({'success':False ,'error':'Владельца мутить нельзя'}),400
        perms =getattr (member ,'guild_permissions',None )
        if perms is not None and perms .manage_messages :
            return jsonify ({'success':False ,'error':'У него права модератора — на состав не работает'}),400
        sec ,err =parse_ghost_duration (data .get ('duration'))
        if err :
            return jsonify ({'success':False ,'error':err }),400
        until =None
        if sec :
            from datetime import datetime as _dt ,timedelta as _td ,timezone as _tz
            until =(_dt .now (_tz .utc )+_td (seconds =sec )).isoformat ()
        ghost_add (guild .id ,int (uid ),reason ,
        by =f"панель:{session.get('username','?')}",until =until )
        _fire_panel_notification ('ghost',f"👻 Тихий мут: {member}",
        f"{session.get('username')}: {reason}")
        return jsonify ({'success':True })


    @app .route ('/api/ghost',methods =['DELETE'])
    @login_required
    @role_required ('mod')
    def api_ghost_remove ():
        from cogs .mod_plus import ghost_remove
        data =request .get_json (silent =True )or {}
        uid =str (data .get ('user_id','')).strip ()
        if not uid .isdigit ():
            return jsonify ({'success':False ,'error':'Нужен user_id'}),400
        guild =_active_guild ()
        if not guild :
            return jsonify ({'success':False ,'error':'Бот офлайн'}),503
        entry =ghost_remove (guild .id ,int (uid ))
        if not entry :
            return jsonify ({'success':False ,'error':'Он и не был призраком'}),404
        _fire_panel_notification ('ghost',f"👻 Тихий мут снят: {uid}",session .get ('username','?'))
        return jsonify ({'success':True ,'suppressed':entry .get ('suppressed')or 0 })


    # ── Демки к наказаниям (cogs/proof_cog.py) ────────────────────────────
    @app .route ('/proofs')
    @login_required
    @role_required ('mod')
    def proofs_page ():
        return render_template ('proofs.html',role =session .get ('role'),username =session .get ('username'))


    @app .route ('/api/proofs',methods =['GET'])
    @login_required
    @role_required ('mod')
    def api_proofs_list ():
        from cogs .proof_cog import proof_list
        guild =_active_guild ()
        gid =guild .id if guild else int (active_guild_id ()or 0 )
        uid =str (request .args .get ('user_id','')).strip ()
        action =str (request .args .get ('action','')).strip ()
        items =proof_list (gid ,user_id =int (uid ))if uid .isdigit ()else proof_list (gid )
        if action :
            items =[e for e in items if e .get ('action')==action ]
        from web .app import _ts_to_utc_iso 
        out =[]
        for e in items [:500 ]:
            ch_id =e .get ('channel_id')
            jump =None
            if ch_id and e .get ('msg_id'):
                jump =f"https://discord.com/channels/{gid}/{ch_id}/{e['msg_id']}"
            out .append ({'id':e .get ('id'),'user_id':str (e .get ('user_id')),
            'user_name':e .get ('user_name'),'mod_name':e .get ('mod_name'),
            'action':e .get ('action'),'reason':e .get ('reason'),
            'link':e .get ('link'),'url':e .get ('url'),
            'set_at':_ts_to_utc_iso (e .get ('set_at'))or e .get ('set_at')or '','jump':jump })
        return jsonify ({'success':True ,'items':out ,'total':len (items )})


    @app .route ('/api/proofs/<int:pid>',methods =['DELETE'])
    @login_required
    @role_required ('admin')
    def api_proofs_delete (pid ):
        # удаление демки — только admin+ (история наказаний = серьёзно)
        from cogs .proof_cog import proof_remove
        guild =_active_guild ()
        if not guild :
            return jsonify ({'success':False ,'error':'Бот офлайн'}),503
        entry =proof_remove (guild .id ,pid )
        if not entry :
            return jsonify ({'success':False ,'error':'Демка не найдена'}),404
        # заодно попробуем убрать сообщение из канала доказательств
        msg_deleted =False
        try :
            if entry .get ('channel_id')and entry .get ('msg_id'):
                ch =guild .get_channel (int (entry ['channel_id']))
                if ch :
                    msg =_run_async (ch .fetch_message (int (entry ['msg_id'])))
                    _run_async (msg .delete ())
                    msg_deleted =True
        except Exception as _ex:
            _log.debug("api_proofs_delete(): подавлено: %s", _ex)
        _fire_panel_notification ('proof',f'Демка #{pid} удалена',
        f"{session.get('username')}: {entry.get('user_name')}")
        return jsonify ({'success':True ,'msg_deleted':msg_deleted })


    @app .route ('/api/panic',methods =['GET'])
    @login_required 
    @role_required ('mod')
    def api_panic_status_panel ():
        from cogs .mod_plus import _panic_path ,_load_json 
        guild =_active_guild ()
        st =_load_json (_panic_path (guild .id ),None )if guild else None 
        return jsonify ({'success':True ,'active':bool (st ),'state':st or {}})


    @app .route ('/api/panic',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_panic_toggle ():
        # ВНИМАНИЕ: только admin+ — это локдаун всего сервера
        data =request .get_json (silent =True )or {}
        action =str (data .get ('action','')).lower ()
        reason =(data .get ('reason')or 'Через панель')[:300 ]
        boost =bool (data .get ('boost_verification'))
        guild =_active_guild ()
        cog ,bot =_modplus_cog ()
        if not cog or not guild :
            return jsonify ({'success':False ,'error':'Бот офлайн или модуль mod_plus не загружен'}),503 
        who =f'панель:{session.get("username","?")}'
        try :
            if action =='on':
                state ,done ,failed =_run_async (cog .panic_enable_core (guild ,reason ,boost_verification =boost ,by =who ),timeout =90 )
                if state is None :
                    return jsonify ({'success':False ,'error':'Локдаун уже активен'}),409 
            elif action =='off':
                state ,done ,failed =_run_async (cog .panic_disable_core (guild ,by =who ),timeout =90 )
                if state is None :
                    return jsonify ({'success':False ,'error':'Локдаун не активен'}),409 
            else :
                return jsonify ({'success':False ,'error':'action: on или off'}),400 
        except Exception as e :
            return jsonify ({'success':False ,'error':str (e )[:200 ]}),500 
        _fire_panel_notification ('panic',f"🚨 Локдаун: {action}",f'{who}: {reason}')
        return jsonify ({'success':True ,'action':action ,'done':done ,'failed':failed })
