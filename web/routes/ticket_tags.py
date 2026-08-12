# -*- coding: utf-8 -*-
"""Теги тикетов (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

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



        # ── TICKET TAGS API ─────────────────────────────────────────────────────────
    @app .route ('/api/ticket-tags',methods =['GET'])
    @login_required 
    def api_ticket_tags_get ():
        """Получить все теги"""
        import json 
        import os 
        from collections import Counter 

        tags_file ='data/ticket_tags.json'
        tags =[]

        if os .path .exists (tags_file ):
            try :
                with open (tags_file ,'r',encoding ='utf-8')as f :
                    tags =json .load (f )
            except Exception :
                tags =[]

                # Статистика
        tag_usage =Counter ()
        high_priority_count =0 

        data_dir ='data'
        if os .path .exists (data_dir ):
            for filename in os .listdir (data_dir ):
                if filename .startswith ('ai_tickets_')and filename .endswith ('.json'):
                    filepath =os .path .join (data_dir ,filename )
                    try :
                        with open (filepath ,'r',encoding ='utf-8')as f :
                            tickets =json .load (f )
                            for ticket in tickets .values ():
                                for tag in ticket .get ('tags',[]):
                                    tag_usage [tag ]+=1 
                                if ticket .get ('priority')=='high':
                                    high_priority_count +=1 
                    except Exception as _ex:
                        _log.debug("api_ticket_tags_get(): подавлено: %s", _ex)

        popular_tag =tag_usage .most_common (1 )[0 ][0 ]if tag_usage else '-'

        return jsonify ({
        'success':True ,
        'tags':tags ,
        'stats':{
        'popular_tag':popular_tag ,
        'high_priority_count':high_priority_count 
        }
        })


    @app .route ('/api/ticket-tags',methods =['POST'])
    @login_required 
    def api_ticket_tags_create ():
        """Создать новый тег"""
        import json 
        import os 
        import uuid 

        data =request .get_json ()
        name =data .get ('name','').strip ()
        color =data .get ('color','#9b59b6')

        if not name :
            return jsonify ({'success':False ,'error':'Название тега обязательно'}),400 

        tags_file ='data/ticket_tags.json'
        tags =[]

        if os .path .exists (tags_file ):
            try :
                with open (tags_file ,'r',encoding ='utf-8')as f :
                    tags =json .load (f )
            except Exception :
                tags =[]

                # Проверить дубликат
        if any (tag ['name'].lower ()==name .lower ()for tag in tags ):
            return jsonify ({'success':False ,'error':'Тег с таким названием уже существует'}),400 

            # Создать новый тег
        new_tag ={
        'id':str (uuid .uuid4 ())[:8 ],
        'name':name ,
        'color':color ,
        'created_at':datetime .now ().isoformat ()
        }

        tags .append (new_tag )

        # Сохранить
        os .makedirs ('data',exist_ok =True )
        with open (tags_file ,'w',encoding ='utf-8')as f :
            json .dump (tags ,f ,ensure_ascii =False ,indent =2 )

        return jsonify ({'success':True ,'tag':new_tag })


    @app .route ('/api/ticket-tags/<tag_id>',methods =['DELETE'])
    @login_required 
    def api_ticket_tags_delete (tag_id ):
        """Удалить тег"""
        import json 
        import os 

        tags_file ='data/ticket_tags.json'

        if not os .path .exists (tags_file ):
            return jsonify ({'success':False ,'error':'Теги не найдены'}),404 

        try :
            with open (tags_file ,'r',encoding ='utf-8')as f :
                tags =json .load (f )
        except Exception :
            return jsonify ({'success':False ,'error':'Ошибка чтения тегов'}),500 

            # Удалить тег
        tags =[tag for tag in tags if tag ['id']!=tag_id ]

        # Сохранить
        with open (tags_file ,'w',encoding ='utf-8')as f :
            json .dump (tags ,f ,ensure_ascii =False ,indent =2 )

        return jsonify ({'success':True })


    @app .route ('/ticket-tags')
    @login_required 
    def ticket_tags_page ():
        """Страница управления тегами и приоритетами"""
        return render_template ('ticket_tags.html',role =session .get ('role'),username =session .get ('username'))
