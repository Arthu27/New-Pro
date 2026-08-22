# -*- coding: utf-8 -*-
"""Права ролей и доступ к панели (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

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


    # ═══════════════════════════════════════════════════════════════════
    #  РОЛИ И ДОСТУП (Command ACL) — управление доступом к командам
    # ═══════════════════════════════════════════════════════════════════
    @app .route ('/role-permissions')
    @login_required
    @role_required ('owner')
    def role_permissions_page ():
        return render_template (
        'role_permissions.html',
        role =session .get ('role'),
        username =session .get ('username'),
        guild_id =active_guild_id ()
        )


    @app .route ('/api/panel/visibility',methods =['GET','POST'])
    @login_required
    @role_required ('owner')
    def api_panel_visibility ():
        """Кому видны уведомления и лента активности (min-роль)."""
        f ='data/panel_visibility.json'
        defaults ={'notifications_min_role':'mod','activity_min_role':'mod'}
        cur =dict (defaults )
        try :
            if os .path .exists (f ):
                with open (f ,encoding ='utf-8')as fp :
                    d =json .load (fp )
                if isinstance (d ,dict ):
                    cur .update ({k :v for k ,v in d .items ()if k in defaults })
        except Exception as _ex :
            _log.debug("api_panel_visibility(): подавлено: %s", _ex )
        if request .method =='GET':
            return jsonify ({'success':True ,'visibility':cur })
        data =request .get_json (silent =True )or {}
        for k in defaults :
            v =str (data .get (k ,cur [k ])or '').strip ()
            if v in ROLES :
                cur [k ]=v
        os .makedirs ('data',exist_ok =True )
        with open (f ,'w',encoding ='utf-8')as fp :
            json .dump (cur ,fp ,indent =2 ,ensure_ascii =False )
        return jsonify ({'success':True ,'visibility':cur })


    @app .route ('/panel-access')
    @login_required
    @role_required ('owner')
    def panel_access_page ():
        """Доступ к панелям: какие Discord-роли получают панель
        Владелец / Администратор / Модератор / Участник."""
        return render_template (
        'panel_access.html',
        role =session .get ('role'),
        username =session .get ('username'),
        guild_id =active_guild_id ()
        )


    @app .route ('/panel-menu')
    @login_required
    @role_required ('owner')
    def panel_menu_page ():
        """Доступ к меню: какие категории (группы) и страницы (комнаты)
        видны в панели Модератора и Администратора."""
        return render_template (
        'panel_menu.html',
        role =session .get ('role'),
        username =session .get ('username'),
        guild_id =active_guild_id ()
        )


    @app .route ('/api/role-permissions/<guild_id>')
    @login_required
    @role_required ('owner')
    def api_role_permissions_get (guild_id ):
        """Вернуть: все роли сервера, категории команд, текущие ACL."""
        from services .permission_acl import COMMAND_CATEGORIES ,load_acl
        import web .app as _app
        bot =_app .bot_instance
        guild =None
        if bot :
            guild =bot .get_guild (int (guild_id ))
            if guild is None :
                for g in bot .guilds :
                    if str (g .id )==str (guild_id ):
                        guild =g
                        break
        roles =[]
        if guild :
            roles =[
            {'id':str (r .id ),'name':r .name ,'color':str (r .color ),
             'position':r .position ,'hoist':r .hoist ,
             'permissions':r .permissions .value }
            for r in guild .roles
            ]
            roles .sort (key =lambda x :x ['position'],reverse =True )
        acl =load_acl (int (guild_id ))
        return jsonify ({
        'success':True ,
        'roles':roles ,
        'categories':COMMAND_CATEGORIES ,
        'acl':acl ,
        })


    @app .route ('/api/role-permissions/<guild_id>/set',methods =['POST'])
    @login_required
    @role_required ('owner')
    def api_role_permissions_set (guild_id ):
        """Установить роли для команды/категории."""
        from services .permission_acl import set_rule ,clear_rule
        data =request .get_json (silent =True )or {}
        command =data .get ('command','').strip ()
        role_ids =data .get ('role_ids',[]) or []
        if not command :
            return jsonify ({'success':False ,'error':'Нет команды'}),400
        if role_ids :
            set_rule (int (guild_id ),command ,[str (r )for r in role_ids ])
        else :
            clear_rule (int (guild_id ),command )
        return jsonify ({'success':True })


    @app .route ('/api/role-permissions/<guild_id>/clear',methods =['POST'])
    @login_required
    @role_required ('owner')
    def api_role_permissions_clear (guild_id ):
        """Сбросить все ограничения (всё доступно всем)."""
        from services .permission_acl import save_acl
        save_acl (int (guild_id ),{})
        return jsonify ({'success':True })


    @app .route ('/api/role-permissions/<guild_id>/preset',methods =['POST'])
    @login_required
    @role_required ('owner')
    def api_role_permissions_preset (guild_id ):
        """Применить пресет: moderator / admin / member / everyone."""
        from services .permission_acl import COMMAND_CATEGORIES ,save_acl
        data =request .get_json (silent =True )or {}
        preset =data .get ('preset','')
        role_ids =[str (r )for r in (data .get ('role_ids',[]) or [])]
        if not role_ids :
            return jsonify ({'success':False ,'error':'Выберите хотя бы одну роль'}),400
        acl ={}
        if preset =='mod':
            for cat ,cmds in COMMAND_CATEGORIES .items ():
                if cat =='Модерация':
                    acl [cat ]=role_ids
        elif preset =='staff':
            for cat ,cmds in COMMAND_CATEGORIES .items ():
                if cat in ('Модерация','Сервер','Приглашения/Участники'):
                    acl [cat ]=role_ids
        elif preset =='all':
            for cat ,cmds in COMMAND_CATEGORIES .items ():
                acl [cat ]=role_ids
        else :
            return jsonify ({'success':False ,'error':'Неизвестный пресет'}),400
        save_acl (int (guild_id ),acl )
        return jsonify ({'success':True ,'preset':preset })


    @app .route ('/api/role-permissions/<guild_id>/category/everyone',methods =['POST'])
    @login_required
    @role_required ('owner')
    def api_role_permissions_category_everyone (guild_id ):
        """Открыть категорию для всех: снять ограничения с категории и всех её команд."""
        from services .permission_acl import COMMAND_CATEGORIES ,load_acl ,save_acl
        data =request .get_json (silent =True )or {}
        category =data .get ('category','').strip ()
        if not category :
            return jsonify ({'success':False ,'error':'Не указана категория'}),400
        cmds =COMMAND_CATEGORIES .get (category ,[])
        acl =load_acl (int (guild_id ))
        acl .pop (category ,None )   # снять ограничение с категории
        for c in cmds :
            acl .pop (c ,None )      # снять ограничение с каждой команды
        save_acl (int (guild_id ),acl )
        return jsonify ({'success':True ,'category':category ,'commands_cleared':len (cmds )})


    @app .route ('/api/role-permissions/<guild_id>/category/assign',methods =['POST'])
    @login_required
    @role_required ('owner')
    def api_role_permissions_category_assign (guild_id ):
        """Топливо: назначить несколько ролей сразу на целую категорию (все её команды)."""
        from services .permission_acl import COMMAND_CATEGORIES ,load_acl ,save_acl
        data =request .get_json (silent =True )or {}
        category =data .get ('category','').strip ()
        role_ids =[str (r )for r in (data .get ('role_ids',[]) or [])]
        if not category :
            return jsonify ({'success':False ,'error':'Не указана категория'}),400
        cmds =COMMAND_CATEGORIES .get (category ,[])
        acl =load_acl (int (guild_id ))
        if role_ids :
            acl [category ]=role_ids
            for c in cmds :
                acl [c ]=role_ids
        else :
            acl .pop (category ,None )
            for c in cmds :
                acl .pop (c ,None )
        save_acl (int (guild_id ),acl )
        return jsonify ({'success':True ,'category':category ,'role_ids':role_ids ,'commands':len (cmds )})
