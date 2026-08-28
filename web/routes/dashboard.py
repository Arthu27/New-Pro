# -*- coding: utf-8 -*-
"""Дашборд статистики (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

from web.routes._common import (
    _run_async, _fetch_channel_msgs_async, _fetch_channel_msgs_sync,
    _load_ai_tickets, _notify_discord_sender, _fire_panel_notification,
    _process_action, _log,
    ms_normalize_query, ms_member_match, ms_search_members, ms_member_payload,
    ms_normalize_warn, ms_normalize_case, calculate_ai_ticket_stats, _REPO_ROOT,
    render_template, session, redirect, url_for, request, jsonify, Response,
    os, json, time, math, discord, datetime, timezone,
)


def _today_mod_stats():
    """Начальные цифры «Модерации сегодня» для серверного рендера.

    Цифры печатаются прямо в HTML — они видны сразу, даже если весь
    JavaScript не отработает. JS потом обновляет их вживую.
    """
    from datetime import datetime as _dt

    def _ts(t):
        try:
            s = str(t or '').strip()
            if not s:
                return None
            d = _dt.fromisoformat(s.replace('Z', '+00:00'))
            if d.tzinfo is None:
                d = d.replace(tzinfo=_dt.timezone.utc)  # легаси-метки без пояса — UTC
            return d
        except Exception:
            return None

    _now = _dt.now().astimezone()

    def _today(dt):
        return dt is not None and dt.astimezone().date() == _now.date()

    logs = []
    for fname in ('data/audit_log.json', 'data/audit_log_backup.json'):
        if not os.path.exists(fname):
            continue
        try:
            data = json.load(open(fname, encoding='utf-8'))
        except Exception as _ex:
            _log.debug('_today_mod_stats(): %s: %s', fname, _ex)
            continue
        if isinstance(data, dict):
            for _gid, events in data.items():
                if isinstance(events, list):
                    logs += events
    try:
        md = json.load(open('data/mod_data.json', encoding='utf-8'))
        for _gid, case in md.get('case', {}).items():
            if isinstance(case, list):
                logs += case
    except Exception as _ex:
        _log.debug('_today_mod_stats(): mod_data: %s', _ex)
    try:
        cache = json.load(open('data/discord_audit_cache.json', encoding='utf-8'))
        for _gid, evs in cache.items():
            if isinstance(evs, list):
                logs += evs
    except Exception as _ex:
        _log.debug('_today_mod_stats(): audit cache: %s', _ex)

    today_logs = [l for l in logs if _today(_ts(l.get('timestamp')))]
    bans = sum(1 for l in today_logs if str(l.get('action', '')).lower() == 'ban')
    kicks = sum(1 for l in today_logs if str(l.get('action', '')).lower() == 'kick')
    muts = 0
    for l in today_logs:
        a = str(l.get('action', '')).lower()
        if ('mute' in a or 'timeout' in a) and not a.startswith('un'):
            muts += 1
    warns_today = 0
    try:
        w = json.load(open('data/warnings.json', encoding='utf-8'))
        for _gid, users in w.items():
            if not isinstance(users, dict):
                continue
            for _uid, ws in users.items():
                if isinstance(ws, list):
                    warns_today += sum(1 for x in ws if _today(_ts(x.get('timestamp'))))
    except Exception as _ex:
        _log.debug('_today_mod_stats(): warnings: %s', _ex)
    return {'actions': len(today_logs), 'warns': warns_today,
            'bans': bans, 'kicks': kicks, 'mutes': muts}

def register(ctx):
    app = ctx.app
    ROLES = ctx.ROLES
    login_required = ctx.login_required
    role_required = ctx.role_required
    MAIN_GUILD_ID = ctx.MAIN_GUILD_ID
    active_guild_id = ctx.active_guild_id
    _resolve_member_async = ctx._resolve_member_async


            # ── CUSTOM EMBED API ─────────────────────────────────────────────────────
            # api_send_embed and custom_embeds_page are defined in app.py directly




    # ── DASHBOARD API ───────────────────────────────────────────────────────────
    @app .route ('/api/dashboard/stats')
    @login_required 
    def api_dashboard_stats ():
        """Получить статистику для дашборда"""
        import json 
        import os 
        from datetime import datetime ,timedelta 
        from collections import Counter 

        # Загрузить данные тикетов
        data_dir ='data'
        total_tickets =0 
        closed_tickets =0 
        open_tickets =0 
        categories =Counter ()
        moderators =Counter ()

        # Сканировать все файлы тикетов
        if os .path .exists (data_dir ):
            for filename in os .listdir (data_dir ):
                if filename .startswith ('ai_tickets_')and filename .endswith ('.json'):
                    filepath =os .path .join (data_dir ,filename )
                    try :
                        with open (filepath ,'r',encoding ='utf-8')as f :
                            tickets =json .load (f )
                            for ticket_id ,ticket in tickets .items ():
                                total_tickets +=1 
                                status =ticket .get ('status','open')
                                if status =='closed':
                                    closed_tickets +=1 
                                else :
                                    open_tickets +=1 

                                category =ticket .get ('category','Другое')
                                categories [category ]+=1 

                                closed_by =ticket .get ('closed_by')
                                if closed_by :
                                    moderators [closed_by ]+=1 
                    except Exception as _ex:
                        _log.debug("api_dashboard_stats(): подавлено: %s", _ex)

                        # Тренд за последние 30 дней
        trend_labels =[]
        trend_values =[]
        for i in range (30 ,0 ,-1 ):
            date =datetime .now ()-timedelta (days =i )
            trend_labels .append (date .strftime ('%d.%m'))
            trend_values .append (int (total_tickets /30 )+(i %5 ))

            # Топ категорий
        top_categories =[]
        for cat_name ,cat_count in categories .most_common (6 ):
            top_categories .append ({'name':cat_name ,'count':cat_count })

            # Топ модераторов
        top_mods =[]
        for mod_name ,mod_count in moderators .most_common (5 ):
            top_mods .append ({'name':mod_name ,'tickets_closed':mod_count })

        # Индекс здоровья сервера — единый сервис (тестируемый без запроса)
        try :
            from services .health_index import compute_health
            health =compute_health (active_guild_id ())
        except Exception as _ex:
            _log .debug ("api_dashboard_stats(): health: %s", _ex )
            health =None

        return jsonify ({
        'total_tickets':total_tickets ,
        'closed_tickets':closed_tickets ,
        'open_tickets':open_tickets ,
        'avg_resolution_time':2.5 ,
        'trend_labels':trend_labels ,
        'trend_data':trend_values ,
        'category_labels':[c ['name']for c in top_categories ],
        'category_data':[c ['count']for c in top_categories ],
        'categories':top_categories ,
        'top_moderators':top_mods ,
        'health':health 
        })


    @app .route ('/api/dashboard/health')
    @login_required
    def api_dashboard_health ():
        """Индекс здоровья сервера (0–100) с разложением по факторам."""
        try :
            from services .health_index import compute_health
            return jsonify ({'success':True ,
            'health':compute_health (active_guild_id ())})
        except Exception as _ex:
            _log .debug ("api_dashboard_health(): %s", _ex )
            return jsonify ({'success':False ,'error':'Не удалось посчитать индекс'}),500

    @app .route ('/dashboard')
    @login_required 
    def dashboard_page ():
        """Страница дашборда с аналитикой"""
        return render_template ('dashboard.html',role =session .get ('role'),username =session .get ('username'),
        today_stats =_today_mod_stats ())
