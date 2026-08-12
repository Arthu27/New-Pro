# -*- coding: utf-8 -*-
"""Портал клиента (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

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



        # ── CUSTOMER PORTAL API ─────────────────────────────────────────────────────
    @app .route ('/api/customer-portal',methods =['GET'])
    @login_required 
    def api_customer_portal_get ():
        """Получить данные клиентского портала"""
        import json 
        import os 

        user_id =session .get ('user_id')

        # Загрузить тикеты пользователя
        tickets_file ='data/customer_tickets.json'

        if os .path .exists (tickets_file ):
            try :
                with open (tickets_file ,'r',encoding ='utf-8')as f :
                    all_tickets =json .load (f )
            except Exception :
                all_tickets =[]
        else :
            all_tickets =[]

            # Фильтровать по пользователю
        user_tickets =[t for t in all_tickets if t .get ('user_id')==user_id ]

        # Статистика
        total_tickets =len (user_tickets )
        open_tickets =sum (1 for t in user_tickets if t .get ('status')=='open')
        closed_tickets =total_tickets -open_tickets 

        ratings =[t .get ('rating',0 )for t in user_tickets if t .get ('rating')]
        avg_rating =round (sum (ratings )/len (ratings ),1 )if ratings else 0 

        # Загрузить статьи из базы знаний
        kb_file ='data/knowledge_base.json'

        if os .path .exists (kb_file ):
            try :
                with open (kb_file ,'r',encoding ='utf-8')as f :
                    kb_data =json .load (f )
            except Exception :
                kb_data ={'categories':[],'articles':[]}
        else :
            kb_data ={'categories':[],'articles':[]}

            # Популярные статьи
        articles =kb_data .get ('articles',[])
        popular_articles =sorted (articles ,key =lambda x :x .get ('views',0 ),reverse =True )[:6 ]

        # Информация о пользователе (placeholder)
        user_info ={
        'name':session .get ('username','Пользователь'),
        'email':'user@example.com',
        'member_since':'01.01.2026'
        }

        return jsonify ({
        'success':True ,
        'user':user_info ,
        'stats':{
        'total_tickets':total_tickets ,
        'open_tickets':open_tickets ,
        'closed_tickets':closed_tickets ,
        'avg_rating':avg_rating 
        },
        'tickets':user_tickets [:20 ],# Последние 20 тикетов
        'articles':popular_articles 
        })


    @app .route ('/api/customer-portal/tickets',methods =['POST'])
    @login_required 
    def api_customer_portal_create_ticket ():
        """Создать тикет"""
        import json 
        import os 
        import uuid 

        subject =request .form .get ('subject','').strip ()
        category =request .form .get ('category','Другое')
        priority =request .form .get ('priority','medium')
        description =request .form .get ('description','').strip ()

        if not subject or not description :
            return jsonify ({'success':False ,'error':'Тема и описание обязательны'}),400 

        tickets_file ='data/customer_tickets.json'

        if os .path .exists (tickets_file ):
            try :
                with open (tickets_file ,'r',encoding ='utf-8')as f :
                    tickets =json .load (f )
            except Exception :
                tickets =[]
        else :
            tickets =[]

        new_ticket ={
        'id':str (uuid .uuid4 ())[:8 ],
        'user_id':session .get ('user_id'),
        'subject':subject ,
        'category':category ,
        'priority':priority ,
        'description':description ,
        'status':'open',
        'message_count':1 ,
        'created_at':datetime .now ().isoformat (),
        'updated_at':datetime .now ().isoformat ()
        }

        tickets .append (new_ticket )

        os .makedirs ('data',exist_ok =True )
        with open (tickets_file ,'w',encoding ='utf-8')as f :
            json .dump (tickets ,f ,ensure_ascii =False ,indent =2 )

        # Уведомление персонала по настроенным каналам (веб/Discord/email)
        _fire_panel_notification (
        'ticket_open',
        f"Новый тикет #{new_ticket['id']}: {subject}",
        f"{session .get ('username','Пользователь')} · категория: {category} · приоритет: {priority}")

        return jsonify ({'success':True ,'ticket':new_ticket })


    @app .route ('/api/customer-portal/tickets',methods =['GET'])
    @login_required 
    def api_customer_portal_get_tickets ():
        """Получить тикеты пользователя"""
        import json 
        import os 

        user_id =session .get ('user_id')
        filter_type =request .args .get ('filter','all')

        tickets_file ='data/customer_tickets.json'

        if os .path .exists (tickets_file ):
            try :
                with open (tickets_file ,'r',encoding ='utf-8')as f :
                    all_tickets =json .load (f )
            except Exception :
                all_tickets =[]
        else :
            all_tickets =[]

            # Фильтровать по пользователю
        user_tickets =[t for t in all_tickets if t .get ('user_id')==user_id ]

        # Фильтровать по статусу
        if filter_type =='open':
            user_tickets =[t for t in user_tickets if t .get ('status')=='open']
        elif filter_type =='closed':
            user_tickets =[t for t in user_tickets if t .get ('status')=='closed']

            # Сортировка по дате (новые первые)
        user_tickets .sort (key =lambda x :x .get ('created_at',''),reverse =True )

        return jsonify ({'success':True ,'tickets':user_tickets })


    @app .route ('/api/customer-portal/profile',methods =['PUT'])
    @login_required 
    def api_customer_portal_update_profile ():
        """Обновить профиль пользователя"""
        data =request .get_json ()

        # Placeholder для обновления профиля
        # В реальном приложении здесь будет обновление в базе данных

        return jsonify ({'success':True })


    @app .route ('/customer-portal')
    @login_required 
    def customer_portal_page ():
        """Страница клиентского портала"""
        return render_template ('customer_portal.html',role =session .get ('role'),username =session .get ('username'))
