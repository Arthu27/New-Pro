# -*- coding: utf-8 -*-
"""Продвинутая аналитика (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

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



        # ── ADVANCED ANALYTICS API ──────────────────────────────────────────────────
    @app .route ('/api/analytics/advanced',methods =['POST'])
    @login_required 
    def api_analytics_advanced ():
        """Получить расширенную аналитику"""
        import json 
        import os 
        from datetime import datetime ,timedelta ,timezone 
        from collections import Counter ,defaultdict 

        def _aware (s ):
            # ISO-метка -> aware-UTC. Naive считаем UTC (так пишут тикеты).
            # Без этого сравнение с cutoff (aware) роняло эндпоинт с TypeError
            # либо молча отбрасывало все тикеты.
            try :
                dt =datetime .fromisoformat (str (s or '').replace ('Z','+00:00'))
            except Exception :
                return None 
            if dt .tzinfo is None :
                dt =dt .replace (tzinfo =timezone .utc )
            else :
                dt =dt .astimezone (timezone .utc )
            return dt 

        data =request .get_json ()
        period =int (data .get ('period',30 ))
        category_filter =data .get ('category','')
        moderator_filter =data .get ('moderator','')

        # Загрузить данные тикетов
        data_dir ='data'
        all_tickets =[]

        if os .path .exists (data_dir ):
            for filename in os .listdir (data_dir ):
                if filename .startswith ('ai_tickets_')and filename .endswith ('.json'):
                    filepath =os .path .join (data_dir ,filename )
                    try :
                        with open (filepath ,'r',encoding ='utf-8')as f :
                            tickets =json .load (f )
                            for ticket_id ,ticket in tickets .items ():
                                ticket ['id']=ticket_id 
                                all_tickets .append (ticket )
                    except Exception as _ex:
                        _log.debug("api_analytics_advanced(): подавлено: %s", _ex)

                        # Фильтрация по периоду
        cutoff_date =datetime .now (timezone .utc )-timedelta (days =period )
        filtered_tickets =[]

        for ticket in all_tickets :
            created_at =ticket .get ('created_at','')
            if created_at :
                try :
                    created_date =_aware (created_at )
                    if created_date is not None and created_date >=cutoff_date :
                    # Фильтрация по категории
                        if category_filter and ticket .get ('category','')!=category_filter :
                            continue 
                            # Фильтрация по модератору
                        if moderator_filter and ticket .get ('closed_by','')!=moderator_filter :
                            continue 
                        filtered_tickets .append (ticket )
                except Exception as _ex:
                    _log.debug("api_analytics_advanced(): подавлено: %s", _ex)

                    # Расчет статистики
        total_tickets =len (filtered_tickets )
        closed_tickets =sum (1 for t in filtered_tickets if t .get ('status')=='closed')
        resolution_rate =round ((closed_tickets /total_tickets *100 ),1 )if total_tickets >0 else 0 

        # Среднее время решения
        resolution_times =[]
        for ticket in filtered_tickets :
            if ticket .get ('status')=='closed'and ticket .get ('created_at')and ticket .get ('closed_at'):
                try :
                    created =_aware (ticket ['created_at'])
                    closed =_aware (ticket ['closed_at'])
                    if created is not None and closed is not None and closed >=created :
                        hours =(closed -created ).total_seconds ()/3600 
                        resolution_times .append (hours )
                except Exception as _ex:
                    _log.debug("api_analytics_advanced(): подавлено: %s", _ex)

        avg_resolution_time =round (sum (resolution_times )/len (resolution_times ),1 )if resolution_times else 0 

        # Оценка удовлетворенности (placeholder)
        satisfaction_score =4.5 

        # Тренды (сравнение с предыдущим периодом)
        prev_cutoff_date =cutoff_date -timedelta (days =period )
        prev_tickets =[]
        for t in all_tickets :
            _cd =_aware (t .get ('created_at',''))
            if _cd is not None and prev_cutoff_date <=_cd <cutoff_date :
                prev_tickets .append (t )
        prev_total =len (prev_tickets )

        total_tickets_trend =round (((total_tickets -prev_total )/prev_total *100 ),1 )if prev_total >0 else 0 

        # Тренд тикетов (по дням)
        tickets_by_day =defaultdict (int )
        for ticket in filtered_tickets :
            created_at =ticket .get ('created_at','')
            if created_at :
                try :
                    _d =_aware (created_at )
                    if _d is not None :
                        date =_d .date ()
                        tickets_by_day [date ]+=1 
                except Exception as _ex:
                    _log.debug("api_analytics_advanced(): подавлено: %s", _ex)

        trend_labels =[]
        trend_data =[]
        for i in range (period ,0 ,-1 ):
            date =(datetime .now (timezone .utc )-timedelta (days =i )).date ()
            trend_labels .append (date .strftime ('%d.%m'))
            trend_data .append (tickets_by_day .get (date ,0 ))

            # Распределение по категориям
        category_counter =Counter (t .get ('category','Другое')for t in filtered_tickets )
        category_labels =list (category_counter .keys ())
        category_data =list (category_counter .values ())

        # Производительность модераторов
        moderator_counter =Counter (t .get ('closed_by','Неизвестный')for t in filtered_tickets if t .get ('status')=='closed')
        moderator_labels =list (moderator_counter .keys ())[:10 ]# Топ 10
        moderator_data =[moderator_counter [m ]for m in moderator_labels ]

        # Время решения по категориям
        resolution_by_category =defaultdict (list )
        for ticket in filtered_tickets :
            if ticket .get ('status')=='closed'and ticket .get ('created_at')and ticket .get ('closed_at'):
                try :
                    created =_aware (ticket ['created_at'])
                    closed =_aware (ticket ['closed_at'])
                    hours =(closed -created ).total_seconds ()/3600 
                    category =ticket .get ('category','Другое')
                    resolution_by_category [category ].append (hours )
                except Exception as _ex:
                    _log.debug("api_analytics_advanced(): подавлено: %s", _ex)

        resolution_time_labels =list (resolution_by_category .keys ())
        resolution_time_data =[
        round (sum (times )/len (times ),1 )if times else 0 
        for times in resolution_by_category .values ()
        ]

        # AI-инсайты (placeholder)
        insights =[
        {
        'type':'positive'if total_tickets_trend >0 else 'negative',
        'title':'Тренд тикетов',
        'description':f'Количество тикетов {"увеличилось" if total_tickets_trend > 0 else "уменьшилось"} на {abs(total_tickets_trend)}% по сравнению с предыдущим периодом'
        },
        {
        'type':'positive'if resolution_rate >80 else 'neutral',
        'title':'Процент решения',
        'description':f'{resolution_rate}% тикетов успешно закрыты. {"Отличный результат!" if resolution_rate > 80 else "Есть потенциал для улучшения"}'
        },
        {
        'type':'positive'if avg_resolution_time <24 else 'negative',
        'title':'Скорость решения',
        'description':f'Среднее время решения: {avg_resolution_time} часов. {"Быстрее среднего" if avg_resolution_time < 24 else "Медленнее среднего"}'
        }
        ]

        return jsonify ({
        'success':True ,
        'stats':{
        'total_tickets':total_tickets ,
        'avg_resolution_time':avg_resolution_time ,
        'resolution_rate':resolution_rate ,
        'satisfaction_score':satisfaction_score ,
        'total_tickets_trend':total_tickets_trend ,
        'avg_resolution_time_trend':0 ,
        'resolution_rate_trend':0 ,
        'satisfaction_score_trend':0 
        },
        'charts':{
        'tickets_trend':{
        'labels':trend_labels ,
        'data':trend_data 
        },
        'category':{
        'labels':category_labels ,
        'data':category_data 
        },
        'moderator':{
        'labels':moderator_labels ,
        'data':moderator_data 
        },
        'resolution_time':{
        'labels':resolution_time_labels ,
        'data':resolution_time_data 
        }
        },
        'insights':insights 
        })


    @app .route ('/api/analytics/export',methods =['POST'])
    @login_required 
    def api_analytics_export ():
        """Экспорт отчёта аналитики — РЕАЛЬНЫЕ тикеты из data/ai_tickets_*.json
        (раньше тут отдавалась захардкоженная заглушка с фейковыми строками
        «01.01.2026,Вопрос…» — владелец получал выдуманный отчёт)."""
        from flask import Response
        import csv as _csv
        import io as _io
        from datetime import timedelta as _timedelta

        data =request .get_json (silent =True )or {}
        format_type =data .get ('format','csv')
        if format_type !='csv':
            return jsonify ({'success':False ,'error':'Формат временно недоступен'}),501

        # Та же логика отбора, что в api_analytics_advanced: тикеты за
        # период + фильтры по категории/модератору.
        try :
            period =int (data .get ('period',30 ))
        except (TypeError ,ValueError ):
            period =30
        category_filter =str (data .get ('category','')or '')
        moderator_filter =str (data .get ('moderator','')or '')

        def _aware (s ):
            try :
                dt =datetime .fromisoformat (str (s or '').replace ('Z','+00:00'))
            except Exception :
                return None
            if dt .tzinfo is None :
                dt =dt .replace (tzinfo =timezone .utc )
            else :
                dt =dt .astimezone (timezone .utc )
            return dt

        cutoff =datetime .now (timezone .utc )-_timedelta (days =period )
        rows =[]
        data_dir ='data'
        if os .path .isdir (data_dir ):
            for filename in os .listdir (data_dir ):
                if not (filename .startswith ('ai_tickets_')and filename .endswith ('.json')):
                    continue
                try :
                    with open (os .path .join (data_dir ,filename ),'r',encoding ='utf-8')as f :
                        tickets =json .load (f )
                except Exception as _ex:
                    _log.debug("api_analytics_export(): %s: %s", filename, _ex)
                    continue
                for ticket_id ,ticket in (tickets or {}).items ():
                    if not isinstance (ticket ,dict ):
                        continue
                    created =_aware (ticket .get ('created_at'))
                    if created is None or created <cutoff :
                        continue
                    cat =str (ticket .get ('category','')or '')
                    if category_filter and cat !=category_filter :
                        continue
                    closed_by =str (ticket .get ('closed_by','')or '')
                    if moderator_filter and closed_by !=moderator_filter :
                        continue
                    closed =_aware (ticket .get ('closed_at'))
                    hours =''
                    if closed is not None and closed >=created :
                        hours =round ((closed -created ).total_seconds ()/3600 ,1 )
                    rows .append ([
                        created .strftime ('%Y-%m-%d %H:%M'),
                        ticket_id ,
                        cat or '—',
                        str (ticket .get ('status','')or '—'),
                        closed_by or '—',
                        hours ,
                    ])

        buf =_io .StringIO ()
        buf .write ('\ufeff')  # utf-8-sig, чтобы Excel не ломал кириллицу
        writer =_csv .writer (buf ,delimiter =';')
        writer .writerow (['Дата создания','ID тикета','Категория','Статус','Модератор','Время решения, ч'])
        writer .writerows (rows )

        return Response (
            buf .getvalue (),
            mimetype ='text/csv; charset=utf-8',
            headers ={'Content-Disposition':'attachment; filename=analytics_report.csv'}
        )


    @app .route ('/advanced-analytics')
    @login_required 
    def advanced_analytics_page ():
        """Страница расширенной аналитики"""
        return render_template ('advanced_analytics.html',role =session .get ('role'),username =session .get ('username'))
