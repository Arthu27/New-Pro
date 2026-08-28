# -*- coding: utf-8 -*-
"""База знаний (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

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



        # ── KNOWLEDGE BASE API ──────────────────────────────────────────────────────
    @app .route ('/api/knowledge-base',methods =['GET'])
    @login_required 
    def api_knowledge_base_get ():
        """Получить базу знаний"""
        import json 
        import os 

        kb_file ='data/knowledge_base.json'

        if os .path .exists (kb_file ):
            try :
                with open (kb_file ,'r',encoding ='utf-8')as f :
                    kb_data =json .load (f )
            except Exception :
                kb_data ={'categories':[],'articles':[]}
        else :
            kb_data ={'categories':[],'articles':[]}

        categories =kb_data .get ('categories',[])
        articles =kb_data .get ('articles',[])

        # Демо-режим: база не пустая — страница живая в превью
        import web .app as _app
        if _app ._demo_mode ()and not categories and not articles :
            categories =[
                {'id':'kb-c1','name':'Общие вопросы','description':'Вход, роли и навигация по панели.','icon':'fa-circle-question'},
                {'id':'kb-c2','name':'Модерация','description':'Варны, баны и правила для команды.','icon':'fa-shield-halved'},
                {'id':'kb-c3','name':'Бот и команды','description':'Основные команды и реакции бота.','icon':'fa-robot'},
            ]
            articles =[
                {'id':'kb-a1','category_id':'kb-c1','title':'Как войти в панель','summary':'Логин, Discord PIN и первый вход.',
                 'content':'Открой страницу входа и выбери способ: пароль или Discord PIN. После входа попадёшь на дашборд со своим профилем, заявками и событиями.','tags':['вход','pin','логин'],
                 'views':412,'helpful_yes':31,'helpful_no':2,'created_at':'2026-07-01T10:00:00','updated_at':'2026-08-10T12:00:00'},
                {'id':'kb-a2','category_id':'kb-c1','title':'Что умеет @-поиск','summary':'Мгновенный поиск по всей панели.',
                 'content':'Нажми @ в любом месте панели и начни печатать: найдутся страницы, участники, каналы и команды. Стрелки выбирают, Enter открывает.','tags':['поиск','@','горячие клавиши'],
                 'views':298,'helpful_yes':24,'helpful_no':1,'created_at':'2026-07-05T10:00:00','updated_at':'2026-08-02T09:00:00'},
                {'id':'kb-a3','category_id':'kb-c2','title':'Как выдать варн','summary':'Шаги предупреждения участника.',
                 'content':'Открой «Предупреждения», найди участника по ID или имени, укажи причину и отправь. Все варны попадают в журнал модерации.','tags':['варн','модерация'],
                 'views':356,'helpful_yes':29,'helpful_no':3,'created_at':'2026-07-08T10:00:00','updated_at':'2026-08-05T18:00:00'},
                {'id':'kb-a4','category_id':'kb-c2','title':'Локдаун за минуту','summary':'Экстренное закрытие каналов с откатом.',
                 'content':'Выбери каналы вручную или «все», сделай предпросмотр, укажи причину и закрой. Снимки прав вернутся при снятии режима.','tags':['локдаун','безопасность'],
                 'views':189,'helpful_yes':17,'helpful_no':0,'created_at':'2026-07-12T10:00:00','updated_at':'2026-07-30T14:00:00'},
                {'id':'kb-a5','category_id':'kb-c3','title':'Команды уровня','summary':'/rank, /top и награды за активность.',
                 'content':'Пиши сообщения — опыт капает сам. /rank покажет твой уровень, /top — таблицу лидеров. Награды за уровни выдаются автоматически.','tags':['уровни','xp','rank'],
                 'views':267,'helpful_yes':22,'helpful_no':2,'created_at':'2026-07-15T10:00:00','updated_at':'2026-08-08T11:00:00'},
                {'id':'kb-a6','category_id':'kb-c3','title':'Дни рождения и ивенты','summary':'Календарь событий сервера.',
                 'content':'Зарегистрируй дату рождения в панели — бот поздравит в канале. Ивенты команды видны в разделе «События».','tags':['др','ивенты'],
                 'views':143,'helpful_yes':11,'helpful_no':1,'created_at':'2026-07-18T10:00:00','updated_at':'2026-07-28T16:00:00'},
            ]
            try :
                with open (kb_file ,'w',encoding ='utf-8')as f :
                    json .dump ({'categories':categories,'articles':articles},f ,ensure_ascii =False ,indent =2 )
            except Exception as _ex :
                _log.debug("api_knowledge_base_get() demo: подавлено: %s", _ex)

        # Подсчитать количество статей в каждой категории
        for category in categories :
            category ['article_count']=sum (1 for a in articles if a .get ('category_id')==category ['id'])

            # Статистика
        total_views =sum (a .get ('views',0 )for a in articles )
        helpful_votes =sum (a .get ('helpful_yes',0 )for a in articles )
        total_votes =helpful_votes +sum (a .get ('helpful_no',0 )for a in articles )
        helpful_rate =round ((helpful_votes /total_votes *100 ),1 )if total_votes >0 else 0 

        # Популярные статьи (по просмотрам)
        popular_articles =sorted (articles ,key =lambda x :x .get ('views',0 ),reverse =True )[:6 ]

        # Недавно обновленные
        recent_articles =sorted (articles ,key =lambda x :x .get ('updated_at',''),reverse =True )[:6 ]

        return jsonify ({
        'success':True ,
        'stats':{
        'total_articles':len (articles ),
        'total_categories':len (categories ),
        'total_views':total_views ,
        'helpful_rate':helpful_rate 
        },
        'categories':categories ,
        'articles':articles ,   # полный список — модалка категории показывает все её статьи
        'popular_articles':popular_articles ,
        'recent_articles':recent_articles 
        })


    @app .route ('/api/knowledge-base/categories',methods =['GET'])
    @login_required 
    def api_knowledge_base_categories_get ():
        """Получить категории"""
        import json 
        import os 

        kb_file ='data/knowledge_base.json'

        if os .path .exists (kb_file ):
            try :
                with open (kb_file ,'r',encoding ='utf-8')as f :
                    kb_data =json .load (f )
            except Exception :
                kb_data ={'categories':[],'articles':[]}
        else :
            kb_data ={'categories':[],'articles':[]}

        return jsonify ({'success':True ,'categories':kb_data .get ('categories',[])})


    @app .route ('/api/knowledge-base/categories',methods =['POST'])
    @login_required 
    def api_knowledge_base_categories_create ():
        """Создать категорию"""
        import json 
        import os 
        import uuid 

        data =request .get_json ()
        name =data .get ('name','').strip ()
        description =data .get ('description','').strip ()
        icon =data .get ('icon','fa-folder').strip ()

        if not name :
            return jsonify ({'success':False ,'error':'Название обязательно'}),400 

        kb_file ='data/knowledge_base.json'

        if os .path .exists (kb_file ):
            try :
                with open (kb_file ,'r',encoding ='utf-8')as f :
                    kb_data =json .load (f )
            except Exception :
                kb_data ={'categories':[],'articles':[]}
        else :
            kb_data ={'categories':[],'articles':[]}

        new_category ={
        'id':str (uuid .uuid4 ())[:8 ],
        'name':name ,
        'description':description ,
        'icon':icon ,
        'created_at':datetime .now (timezone.utc).isoformat ()
        }

        kb_data ['categories'].append (new_category )

        os .makedirs ('data',exist_ok =True )
        with open (kb_file ,'w',encoding ='utf-8')as f :
            json .dump (kb_data ,f ,ensure_ascii =False ,indent =2 )

        return jsonify ({'success':True ,'category':new_category })


    @app .route ('/api/knowledge-base/articles',methods =['POST'])
    @login_required 
    def api_knowledge_base_articles_create ():
        """Создать статью"""
        import json 
        import os 
        import uuid 

        data =request .get_json ()
        title =data .get ('title','').strip ()
        category_id =data .get ('category_id','').strip ()
        summary =data .get ('summary','').strip ()
        content =data .get ('content','').strip ()
        tags =data .get ('tags',[])

        if not title or not content :
            return jsonify ({'success':False ,'error':'Заголовок и содержание обязательны'}),400 

        kb_file ='data/knowledge_base.json'

        if os .path .exists (kb_file ):
            try :
                with open (kb_file ,'r',encoding ='utf-8')as f :
                    kb_data =json .load (f )
            except Exception :
                kb_data ={'categories':[],'articles':[]}
        else :
            kb_data ={'categories':[],'articles':[]}

        new_article ={
        'id':str (uuid .uuid4 ())[:8 ],
        'title':title ,
        'category_id':category_id ,
        'summary':summary ,
        'content':content ,
        'tags':tags ,
        'views':0 ,
        'helpful_yes':0 ,
        'helpful_no':0 ,
        'created_at':datetime .now (timezone.utc).isoformat (),
        'updated_at':datetime .now (timezone.utc).isoformat ()
        }

        kb_data ['articles'].append (new_article )

        os .makedirs ('data',exist_ok =True )
        with open (kb_file ,'w',encoding ='utf-8')as f :
            json .dump (kb_data ,f ,ensure_ascii =False ,indent =2 )

        return jsonify ({'success':True ,'article':new_article })


    @app .route ('/api/knowledge-base/search',methods =['POST'])
    @login_required 
    def api_knowledge_base_search ():
        """Поиск по базе знаний"""
        import json 
        import os 

        data =request .get_json ()
        query =data .get ('query','').lower ().strip ()

        if not query :
            return jsonify ({'success':True ,'results':[]})

        kb_file ='data/knowledge_base.json'

        if os .path .exists (kb_file ):
            try :
                with open (kb_file ,'r',encoding ='utf-8')as f :
                    kb_data =json .load (f )
            except Exception :
                kb_data ={'categories':[],'articles':[]}
        else :
            kb_data ={'categories':[],'articles':[]}

        articles =kb_data .get ('articles',[])
        categories ={c ['id']:c ['name']for c in kb_data .get ('categories',[])}

        # Поиск
        results =[]
        for article in articles :
            searchable_text =f"{article.get('title', '')} {article.get('summary', '')} {article.get('content', '')} {' '.join(article.get('tags', []))}".lower ()
            if query in searchable_text :
                article ['category_name']=categories .get (article .get ('category_id'),'Без категории')
                results .append (article )

                # Сортировка по релевантности (простая: по количеству совпадений)
        results .sort (key =lambda x :x .get ('views',0 ),reverse =True )

        return jsonify ({'success':True ,'results':results [:20 ]})


    @app .route ('/knowledge-base')
    @login_required 
    def knowledge_base_page ():
        """Страница базы знаний"""
        return render_template ('knowledge_base.html',role =session .get ('role'),username =session .get ('username'))
