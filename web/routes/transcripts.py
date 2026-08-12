# -*- coding: utf-8 -*-
"""Транскрипты тикетов (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

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



        # ── TRANSCRIPTS API ─────────────────────────────────────────────────────────
    @app .route ('/api/transcripts/search',methods =['POST'])
    @login_required 
    def api_transcripts_search ():
        """Поиск транскриптов"""
        import json 
        import os 
        from datetime import datetime ,timedelta 

        data =request .get_json ()
        search =data .get ('search','').lower ()
        days =data .get ('days','')
        category =data .get ('category','')

        transcripts_file ='data/transcripts.json'
        transcripts =[]

        if os .path .exists (transcripts_file ):
            try :
                with open (transcripts_file ,'r',encoding ='utf-8')as f :
                    all_transcripts =json .load (f )
            except Exception :
                all_transcripts =[]
        else :
            all_transcripts =[]

            # Фильтрация
        for transcript in all_transcripts :
        # Фильтр по категории
            if category and transcript .get ('category','')!=category :
                continue 

                # Фильтр по дате
            if days :
                closed_at =transcript .get ('closed_at','')
                if closed_at :
                    closed_date =datetime .fromisoformat (closed_at .replace ('Z','+00:00'))
                    cutoff_date =datetime .now (closed_date .tzinfo )-timedelta (days =int (days ))
                    if closed_date <cutoff_date :
                        continue 

                        # Фильтр по поиску
            if search :
                search_fields =[
                str (transcript .get ('id','')),
                transcript .get ('user_name',''),
                transcript .get ('category','')
                ]
                if not any (search in field .lower ()for field in search_fields ):
                    continue 

            transcripts .append ({
            'id':transcript .get ('id'),
            'user_name':transcript .get ('user_name','Неизвестный'),
            'category':transcript .get ('category','Без категории'),
            'closed_at':transcript .get ('closed_at',''),
            'closed_by':transcript .get ('closed_by',''),
            'message_count':len (transcript .get ('messages',[])),
            'duration':transcript .get ('duration','0ч')
            })

            # Сортировка по дате (новые первые)
        transcripts .sort (key =lambda x :x .get ('closed_at',''),reverse =True )

        return jsonify ({
        'success':True ,
        'transcripts':transcripts [:100 ]# Максимум 100 результатов
        })


    @app .route ('/api/transcripts/<transcript_id>',methods =['GET'])
    @login_required 
    def api_transcript_get (transcript_id ):
        """Получить транскрипт по ID"""
        import json 
        import os 

        transcripts_file ='data/transcripts.json'

        if os .path .exists (transcripts_file ):
            try :
                with open (transcripts_file ,'r',encoding ='utf-8')as f :
                    all_transcripts =json .load (f )
            except Exception :
                all_transcripts =[]
        else :
            all_transcripts =[]

            # Найти транскрипт
        transcript =None 
        for t in all_transcripts :
            if str (t .get ('id'))==str (transcript_id ):
                transcript =t 
                break 

        if not transcript :
            return jsonify ({'success':False ,'error':'Транскрипт не найден'}),404 

        return jsonify ({'success':True ,'transcript':transcript })


    @app .route ('/api/transcripts/<transcript_id>/export',methods =['GET'])
    @login_required 
    def api_transcript_export (transcript_id ):
        """Экспорт транскрипта"""
        import json 
        import os 
        from io import BytesIO 

        format_type =request .args .get ('format','txt')

        transcripts_file ='data/transcripts.json'

        if os .path .exists (transcripts_file ):
            try :
                with open (transcripts_file ,'r',encoding ='utf-8')as f :
                    all_transcripts =json .load (f )
            except Exception :
                all_transcripts =[]
        else :
            all_transcripts =[]

            # Найти транскрипт
        transcript =None 
        for t in all_transcripts :
            if str (t .get ('id'))==str (transcript_id ):
                transcript =t 
                break 

        if not transcript :
            return jsonify ({'success':False ,'error':'Транскрипт не найден'}),404 

            # Генерация контента
        if format_type =='txt':
            content =f"Транскрипт тикета #{transcript.get('id')}\n"
            content +=f"Пользователь: {transcript.get('user_name', 'Неизвестный')}\n"
            content +=f"Категория: {transcript.get('category', 'Без категории')}\n"
            content +=f"Закрыт: {transcript.get('closed_at', '')}\n"
            content +=f"Закрыл: {transcript.get('closed_by', 'Неизвестный')}\n"
            content +="="*80 +"\n\n"

            for msg in transcript .get ('messages',[]):
                content +=f"[{msg.get('timestamp', '')}] {msg.get('author', 'Неизвестный')}:\n"
                content +=f"{msg.get('content', '')}\n\n"

            return Response (
            content ,
            mimetype ='text/plain',
            headers ={'Content-Disposition':f'attachment; filename=transcript_{transcript_id}.txt'}
            )

        elif format_type =='html':
            html =f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Транскрипт #{transcript.get('id')}</title>
    <style>
        body {{ font-family: Arial, sans-serif; padding: 20px; }}
        .header {{ background: #f5f5f5; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
        .message {{ background: #f9f9f9; padding: 12px; border-radius: 8px; margin-bottom: 12px; }}
        .bot {{ background: #e8f4f8; }}
        .author {{ font-weight: bold; margin-bottom: 4px; }}
        .timestamp {{ font-size: 11px; color: #666; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Транскрипт тикета #{transcript.get('id')}</h1>
        <p><strong>Пользователь:</strong> {transcript.get('user_name', 'Неизвестный')}</p>
        <p><strong>Категория:</strong> {transcript.get('category', 'Без категории')}</p>
        <p><strong>Закрыт:</strong> {transcript.get('closed_at', '')}</p>
        <p><strong>Закрыл:</strong> {transcript.get('closed_by', 'Неизвестный')}</p>
    </div>
"""

            for msg in transcript .get ('messages',[]):
                is_bot =msg .get ('is_bot',False )
                html +=f"""
    <div class="message {'bot' if is_bot else ''}">
        <div class="author">{msg.get('author', 'Неизвестный')}</div>
        <div class="timestamp">{msg.get('timestamp', '')}</div>
        <div>{msg.get('content', '')}</div>
    </div>
"""

            html +="""
</body>
</html>"""

            return Response (
            html ,
            mimetype ='text/html',
            headers ={'Content-Disposition':f'attachment; filename=transcript_{transcript_id}.html'}
            )

        else :# PDF (placeholder - нужна библиотека)
            return jsonify ({'success':False ,'error':'PDF экспорт временно недоступен'}),501 


    @app .route ('/transcripts')
    @login_required 
    def transcripts_page ():
        """Страница транскриптов тикетов"""
        return render_template ('transcripts.html',role =session .get ('role'),username =session .get ('username'))
