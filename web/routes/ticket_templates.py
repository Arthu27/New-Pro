# -*- coding: utf-8 -*-
"""Шаблоны тикетов (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

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



        # ── TICKET TEMPLATES API ────────────────────────────────────────────────────
    @app .route ('/api/ticket-templates',methods =['GET'])
    @login_required 
    def api_ticket_templates_get ():
        """Получить все шаблоны тикетов"""
        import json 
        import os 

        templates_file ='data/ticket_templates.json'
        templates =[]

        if os .path .exists (templates_file ):
            try :
                with open (templates_file ,'r',encoding ='utf-8')as f :
                    templates =json .load (f )
            except Exception :
                templates =[]

        return jsonify ({'success':True ,'templates':templates })


    @app .route ('/api/ticket-templates',methods =['POST'])
    @login_required 
    def api_ticket_templates_create ():
        """Создать новый шаблон тикета"""
        import json 
        import os 
        import uuid 

        data =request .get_json ()
        name =data .get ('name','').strip ()
        category =data .get ('category','Другое')
        description =data .get ('description','').strip ()
        message =data .get ('message','').strip ()

        if not name or not message :
            return jsonify ({'success':False ,'error':'Название и сообщение обязательны'}),400 

        templates_file ='data/ticket_templates.json'
        templates =[]

        if os .path .exists (templates_file ):
            try :
                with open (templates_file ,'r',encoding ='utf-8')as f :
                    templates =json .load (f )
            except Exception :
                templates =[]

                # Создать новый шаблон
        new_template ={
        'id':str (uuid .uuid4 ())[:8 ],
        'name':name ,
        'category':category ,
        'description':description ,
        'message':message ,
        'created_at':datetime .now ().isoformat (),
        'usage_count':0 
        }

        templates .append (new_template )

        # Сохранить
        os .makedirs ('data',exist_ok =True )
        with open (templates_file ,'w',encoding ='utf-8')as f :
            json .dump (templates ,f ,ensure_ascii =False ,indent =2 )

        return jsonify ({'success':True ,'template':new_template })


    @app .route ('/api/ticket-templates/<template_id>',methods =['GET'])
    @login_required 
    def api_ticket_template_get (template_id ):
        """Получить шаблон по ID"""
        import json 
        import os 

        templates_file ='data/ticket_templates.json'

        if os .path .exists (templates_file ):
            try :
                with open (templates_file ,'r',encoding ='utf-8')as f :
                    templates =json .load (f )
            except Exception :
                templates =[]
        else :
            templates =[]

            # Найти шаблон
        template =None 
        for t in templates :
            if t .get ('id')==template_id :
                template =t 
                break 

        if not template :
            return jsonify ({'success':False ,'error':'Шаблон не найден'}),404 

        return jsonify ({'success':True ,'template':template })


    @app .route ('/api/ticket-templates/<template_id>',methods =['DELETE'])
    @login_required 
    def api_ticket_template_delete (template_id ):
        """Удалить шаблон"""
        import json 
        import os 

        templates_file ='data/ticket_templates.json'

        if not os .path .exists (templates_file ):
            return jsonify ({'success':False ,'error':'Шаблоны не найдены'}),404 

        try :
            with open (templates_file ,'r',encoding ='utf-8')as f :
                templates =json .load (f )
        except Exception :
            return jsonify ({'success':False ,'error':'Ошибка чтения шаблонов'}),500 

            # Удалить шаблон
        templates =[t for t in templates if t .get ('id')!=template_id ]

        # Сохранить
        with open (templates_file ,'w',encoding ='utf-8')as f :
            json .dump (templates ,f ,ensure_ascii =False ,indent =2 )

        return jsonify ({'success':True })


    @app .route ('/ticket-templates')
    @login_required 
    def ticket_templates_page ():
        """Страница шаблонов тикетов"""
        return render_template ('ticket_templates.html',role =session .get ('role'),username =session .get ('username'))
