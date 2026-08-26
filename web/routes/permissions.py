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
        """Панели и роли: какие Discord-роли получают панель
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
        """Меню панели: какие категории (группы) и страницы (комнаты)
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
        """Вернуть: все роли сервера, категории команд, текущие ACL, действия."""
        from services .permission_acl import command_categories ,all_categories ,load_acl ,ACTIONS ,load_action_acl
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
             'permissions':r .permissions .value ,
             'members':len (getattr (r ,'members',[])or [])}
            for r in guild .roles
            ]
            roles .sort (key =lambda x :x ['position'],reverse =True )
        elif _app ._demo_mode ():
            # демо-превью без бота: роли из демо-набора (тот же источник,
            # что /api/role-map) — страница «Права команд» живая в превью.
            try :
                from web .routes .guild_admin import _demo_roles_seed
                roles =[
                {'id':str (r ['id']),'name':r ['name'],'color':r ['color'],
                 'position':int (r ['id'])if str (r ['id']).isdigit ()else 0,
                 'hoist':False ,'permissions':0 ,
                 'members':int (r .get ('members')or 0)}
                for r in _demo_roles_seed ()
                ]
                roles .sort (key =lambda x :x ['position'])
            except Exception as _ex:
                _log.debug("api_role_permissions_get(): демо-роли: %s", _ex )
        from services .permission_acl import effective_acl
        acl =effective_acl (int (guild_id ))
        action_acl =load_action_acl (int (guild_id ))
        return jsonify ({
        'success':True ,
        'roles':roles ,
        'categories':command_categories (),
        'acl':acl ,
        'actions':ACTIONS ,
        'action_acl':action_acl ,
        })


    @app .route ('/api/role-permissions/<guild_id>/action/set',methods =['POST'])
    @login_required
    @role_required ('owner')
    def api_role_permissions_action_set (guild_id ):
        """Классические разрешения: установить роли для действия (бан/мут/…).
        Пустой role_ids — снять правило (действие снова доступно всем)."""
        from services .permission_acl import ACTIONS ,set_action_rule
        data =request .get_json (silent =True )or {}
        action =data .get ('action','').strip ()
        role_ids =data .get ('role_ids',[]) or []
        if action not in ACTIONS :
            return jsonify ({'success':False ,'error':'Неизвестное действие'}),400
        set_action_rule (int (guild_id ),action ,[str (r )for r in role_ids ])
        return jsonify ({'success':True ,'action':action ,'role_ids':role_ids })


    @app .route ('/api/role-permissions/<guild_id>/actions/clear',methods =['POST'])
    @login_required
    @role_required ('owner')
    def api_role_permissions_actions_clear (guild_id ):
        """Снять все классические ограничения (все действия доступны всем)."""
        from services .permission_acl import clear_action_rules
        clear_action_rules (int (guild_id ))
        return jsonify ({'success':True })


    @app .route ('/api/role-permissions/<guild_id>/set',methods =['POST'])
    @login_required
    @role_required ('owner')
    def api_role_permissions_set (guild_id ):
        """Установить роли для команды/категории."""
        from services .permission_acl import (set_rule ,clear_rule ,load_acl ,
        save_acl ,materialize_category ,command_categories )
        data =request .get_json (silent =True )or {}
        command =data .get ('command','').strip ()
        role_ids =data .get ('role_ids',[]) or []
        if not command :
            return jsonify ({'success':False ,'error':'Нет команды'}),400
        # у команды может быть правило на КАТЕГОРИЮ — разворачиваем его в
        # явные правила на команды категории, чтобы правка одной команды не
        # пересекалась с категорийным ограничением (иначе «выдал — а не дал»)
        for cat ,cmds in command_categories ().items ():
            if command in cmds :
                acl =load_acl (int (guild_id ))
                if cat in acl :
                    materialize_category (acl ,cat )
                    save_acl (int (guild_id ),acl )
                break
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
        from services .permission_acl import all_categories ,save_acl
        data =request .get_json (silent =True )or {}
        preset =data .get ('preset','')
        role_ids =[str (r )for r in (data .get ('role_ids',[]) or [])]
        if not role_ids :
            return jsonify ({'success':False ,'error':'Выберите хотя бы одну роль'}),400
        from services .permission_acl import materialize_category
        cats_by_preset ={
            'mod':{'Модерация'},
            'staff':{'Модерация','Тикеты','Логи'},
            'all':set (all_categories ().keys ()),
        }.get (preset )
        if cats_by_preset is None :
            return jsonify ({'success':False ,'error':'Неизвестный пресет'}),400
        acl ={}
        for cat ,cmds in all_categories ().items ():
            if cat in cats_by_preset :
                acl [cat ]=role_ids
                materialize_category (acl ,cat )  # правило на КАЖДУЮ команду
        save_acl (int (guild_id ),acl )
        return jsonify ({'success':True ,'preset':preset })


    @app .route ('/api/role-permissions/<guild_id>/category/everyone',methods =['POST'])
    @login_required
    @role_required ('owner')
    def api_role_permissions_category_everyone (guild_id ):
        """Открыть категорию для всех: снять ограничения с категории и всех её команд."""
        from services .permission_acl import all_categories ,load_acl ,save_acl
        data =request .get_json (silent =True )or {}
        category =data .get ('category','').strip ()
        if not category :
            return jsonify ({'success':False ,'error':'Не указана категория'}),400
        cmds =all_categories ().get (category ,[])
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
        from services .permission_acl import (load_acl ,save_acl ,
        materialize_category ,all_categories )
        data =request .get_json (silent =True )or {}
        category =data .get ('category','').strip ()
        role_ids =[str (r )for r in (data .get ('role_ids',[]) or [])]
        if not category :
            return jsonify ({'success':False ,'error':'Не указана категория'}),400
        # ЖИВОЙ каталог (как на странице) + legacy: раньше искали только в
        # статическом списке, названия не совпадали — «Дать ролям» писал пусто
        cmds =all_categories ().get (category ,[])
        acl =load_acl (int (guild_id ))
        materialize_category (acl ,category )
        if role_ids :
            for c in cmds :
                acl [c ]=role_ids
        else :
            for c in cmds :
                acl .pop (c ,None )
        save_acl (int (guild_id ),acl )
        return jsonify ({'success':True ,'category':category ,'role_ids':role_ids ,'commands':len (cmds )})
