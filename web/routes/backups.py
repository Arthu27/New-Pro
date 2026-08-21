# -*- coding: utf-8 -*-
"""Бэкапы + смена пароля (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

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


    # ── Резервные копии данных (services/backup.py + cogs/backup_cog.py) ──
    @app .route ('/backups')
    @login_required
    @role_required ('admin')
    def backups_page ():
        return render_template ('backups.html',role =session .get ('role'),username =session .get ('username'))


    def _backup_settings ():
        try :
            from cogs .backup_cog import backup_enabled ,backup_hour ,backup_keep ,backup_dir ,backup_attach
            return {'enabled':backup_enabled (),'hour':backup_hour (),'keep':backup_keep (),
            'dir':backup_dir (),'attach':backup_attach ()}
        except Exception :
            from services import backup as _bk2
            return {'enabled':False ,'hour':5 ,'keep':_bk2 .BACKUP_KEEP_DEFAULT ,
            'dir':_bk2 .BACKUP_DIR_DEFAULT ,'attach':False }


    @app .route ('/api/backups',methods =['GET'])
    @login_required
    @role_required ('admin')
    def api_backups_list ():
        from services import backup as _bk
        cfg =_backup_settings ()
        items =_bk .list_backups (cfg ['dir'])
        total =sum (i ['size']for i in items )
        for i in items :
            i .pop ('mtime',None )
        return jsonify ({'success':True ,'items':items ,
        'stats':{'total':len (items ),'total_size':total ,
        'total_size_h':_bk .format_size (total )},
        'settings':{k :v for k ,v in cfg .items ()if k !='dir'}})


    @app .route ('/api/backups',methods =['POST'])
    @login_required
    @role_required ('admin')
    def api_backups_create ():
        from services import backup as _bk
        cfg =_backup_settings ()
        try :
            info =_bk .create_backup (backup_dir =cfg ['dir'],reason ='ручной (панель)',
            by =f"панель:{session.get('username','?')}")
            removed =_bk .rotate_backups (cfg ['dir'],cfg ['keep'])
        except Exception as e :
            return jsonify ({'success':False ,'error':str (e )[:200 ]}),500
        # Лучшая попытка отчитаться в мод-лог Discord через ког (если бот жив)
        try :
            import web .app as _app
            bot =getattr (_app ,'bot_instance',None )
            cog =bot .get_cog ('Backup')if bot else None
            if cog :
                _run_async (cog ._notify (info ,removed ),timeout =20 )
        except Exception as _ex:
            _log.debug("api_backups_create(): подавлено: %s", _ex)
        info ['size_h']=_bk .format_size (info ['size'])
        _fire_panel_notification ('backup','Бэкап создан',
        f"{session.get('username')}: {info['name']} ({info['size_h']})")
        return jsonify ({'success':True ,'item':info ,'removed':len (removed )})


    @app .route ('/api/backups/download/<name>')
    @login_required
    @role_required ('admin')
    def api_backups_download (name ):
        from services import backup as _bk
        from flask import send_file
        cfg =_backup_settings ()
        path =_bk .resolve_backup (name ,cfg ['dir'])
        if not path :
            return jsonify ({'success':False ,'error':'Архив не найден'}),404
        return send_file (path ,as_attachment =True ,download_name =name ,mimetype ='application/zip')


    @app .route ('/api/backups/<name>',methods =['DELETE'])
    @login_required
    @role_required ('admin')
    def api_backups_delete (name ):
        from services import backup as _bk
        cfg =_backup_settings ()
        path =_bk .resolve_backup (name ,cfg ['dir'])
        if not path :
            if _bk .valid_backup_name (name ):
                return jsonify ({'success':False ,'error':'Архив не найден'}),404
            return jsonify ({'success':False ,'error':'Некорректное имя архива'}),400
        try :
            os .remove (path )
        except OSError as e :
            return jsonify ({'success':False ,'error':str (e )[:150 ]}),500
        _fire_panel_notification ('backup','🗑️ Бэкап удалён',f"{session.get('username')}: {name}")
        return jsonify ({'success':True })


    @app .route ('/api/user/change-password',methods =['POST'])
    @login_required
    @role_required ('uye')
    def api_user_change_password ():
        from web .app import USERS 
        import json as _json 
        data =request .get_json (silent =True )or {}
        old_pass =data .get ('old_password','').strip ()
        new_pass =data .get ('new_password','').strip ()

        if not old_pass or not new_pass or len (new_pass )<6 :
            return jsonify ({'error':'Неверные данные'})

            # Owner контроль (USERS dict'inden) — по солёному хэшу,
            # запись уходит в panel_credentials.json (переживает рестарт)
        username =session .get ('username')
        if username in USERS :
            from web .app import _pw_matches ,complete_owner_password_change 
            if not _pw_matches (USERS [username ].get ('password_hash'),old_pass ):
                return jsonify ({'error':'Текущий пароль неверен'})
            complete_owner_password_change (new_pass )
            return jsonify ({'success':True })

            # Normal участник — По Discord ID ara
        discord_id =session .get ('discord_id')or username 
        members_file ='data/members.json'
        if not os .path .exists (members_file ):
            return jsonify ({'error':'Пользователь не найден'})

        with open (members_file ,'r',encoding ='utf-8')as f :
            members =_json .load (f )

            # ищем по discord_id, если нет — пробуем по display_name
        member_key =None 
        if discord_id and discord_id in members :
            member_key =discord_id 
        else :
            for k ,v in members .items ():
                if v .get ('display_name')==username or v .get ('name')==username :
                    member_key =k 
                    break 

        if not member_key :
            return jsonify ({'error':'Пользователь не найден'})
        from web .app import _pw_matches ,_hash_pw 
        if not _pw_matches (members [member_key ].get ('password'),old_pass ):
            return jsonify ({'error':'Текущий пароль неверен'})

        members [member_key ]['password']=_hash_pw (new_pass )
        with open (members_file ,'w',encoding ='utf-8')as f :
            _json .dump (members ,f ,indent =2 ,ensure_ascii =False )
        return jsonify ({'success':True })
