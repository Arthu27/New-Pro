# -*- coding: utf-8 -*-
"""Аналитика, логи панели, инвайты, предложки, старборд (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

from web.routes._common import (
    _run_async, _fetch_channel_msgs_async, _fetch_channel_msgs_sync,
    _load_ai_tickets, _notify_discord_sender, _fire_panel_notification,
    _process_action, _log,
    ms_normalize_query, ms_member_match, ms_search_members, ms_member_payload,
    ms_normalize_warn, ms_normalize_case, calculate_ai_ticket_stats, _REPO_ROOT,
    render_template, session, redirect, url_for, request, jsonify, Response,
    os, json, time, math, discord, datetime, timezone,
)

def _norm_join (rec ):
    """Привести запись о вступлении к полям, которые рисует страница.

    Файл data/invite_joins_<gid>.json исторически писался в виде
    {user, inviter, timestamp}, а шаблон /invite-tracker ждёт
    {name, avatar, invite_code, joined_at} — из-за этого карточки
    «Недавние вступления» выходили без имени и без времени.
    Принимаем оба формата, чтобы старые записи тоже показывались.
    """
    if not isinstance (rec ,dict ):
        return {}
    return {
        'name':rec .get ('name')or rec .get ('display_name')or rec .get ('user')or '',
        'avatar':rec .get ('avatar')or '',
        'inviter':rec .get ('inviter')or '',
        'invite_code':rec .get ('invite_code')or rec .get ('code')or '',
        'joined_at':rec .get ('joined_at')or rec .get ('timestamp')or '',
        'user_id':str (rec .get ('user_id')or rec .get ('id')or ''),
    }


def register(ctx):
    app = ctx.app
    ROLES = ctx.ROLES
    login_required = ctx.login_required
    role_required = ctx.role_required
    MAIN_GUILD_ID = ctx.MAIN_GUILD_ID
    active_guild_id = ctx.active_guild_id
    _resolve_member_async = ctx._resolve_member_async


        # ── ANALYTICS API ─────────────────────────────────────────────────────────
    @app.route('/api/guild/<guild_id>/analytics')
    @login_required
    def api_guild_analytics(guild_id):
        import web.app as _app
        bot = _app.bot_instance
        import collections
        import datetime as _dt

        result = {
            'top_members': [], 'top_channels': [],
            'daily_labels': [], 'daily_messages': [],
            'member_labels': [], 'member_counts': [],
        }

        member_msg_counts = collections.Counter()
        channel_msg_counts = collections.Counter()
        daily_counts = collections.Counter()

        def _day_key(ts):
            """ISO-таймстамп (чаще UTC, '...Z' или '+00:00') -> дата В ЛОКАЛЬНОМ
            поясе сервера (ГГГГ-ММ-ДД). Раньше брали ts[:10] — это дата UTC, и
            вечерние/ночные сообщения падали «не в тот день» относительно меток,
            которые строятся по date.today() (локально)."""
            if not ts:
                return None
            s = str(ts).strip().replace('Z', '+00:00')
            try:
                parsed = _dt.datetime.fromisoformat(s)
            except (ValueError, TypeError):
                return s[:10] if len(s) >= 10 else None
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone()  # в локальный пояс сервера
            return parsed.date().isoformat()

        # Основной источник: message_logs_<gid>.json — его наполняет ког
        # activity_stats -> services.message_stats (КАЖДОЕ сообщение, кроме
        # ботов/вебхуков/ЛС). Полные и достоверные данные.
        msg_log_file = f'data/message_logs_{guild_id}.json'
        if os.path.exists(msg_log_file):
            try:
                with open(msg_log_file, 'r', encoding='utf-8') as fp:
                    msgs = json.load(fp)
            except Exception as ex:
                msgs = []
                _log.debug('analytics: не прочитать %s: %s', msg_log_file, ex)
            for m in msgs:
                if not isinstance(m, dict):
                    continue
                member_msg_counts[str(m.get('author') or m.get('user_name') or '?')] += 1
                channel_msg_counts[str(m.get('channel') or '?')] += 1
                day = _day_key(m.get('timestamp'))
                if day:
                    daily_counts[day] += 1

        # Дополнение из audit_log.json: событие «message написано» исторически
        # почти не пишется (лог фиксирует удаления/правки). Если основного файла
        # нет, а в старом аудите событие есть — учтём его (без двойного счёта).
        if not member_msg_counts:
            audit_file = 'data/audit_log.json'
            if os.path.exists(audit_file):
                try:
                    with open(audit_file, 'r', encoding='utf-8') as fp:
                        audit = json.load(fp)
                except Exception as ex:
                    audit = {}
                    _log.debug('analytics: audit_log: %s', ex)
                for ev in audit.get(str(guild_id), []):
                    if not isinstance(ev, dict):
                        continue
                    action = (ev.get('action') or '').lower()
                    category = (ev.get('category') or '').lower()
                    if category == 'message' and action == 'message написано':
                        member_msg_counts[str(ev.get('user_name') or ev.get('user_id') or '?')] += 1
                        channel_msg_counts[str(ev.get('channel') or ev.get('channel_name') or '?')] += 1
                        day = _day_key(ev.get('timestamp'))
                        if day:
                            daily_counts[day] += 1

        # Метки последних 7 дней (локальный пояс — тот же, что в _day_key)
        today = _dt.date.today()
        labels = [(today - _dt.timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
        result['daily_labels'] = [l[5:] for l in labels]  # формат ММ-ДД
        result['daily_messages'] = [daily_counts.get(l, 0) for l in labels]

        result['top_members'] = [
            {'name': name, 'messages': count}
            for name, count in member_msg_counts.most_common(10)
        ]
        result['top_channels'] = [
            {'name': ch, 'messages': count}
            for ch, count in channel_msg_counts.most_common(10)
        ]

        # Демо-подстановка удалена (заказ владельца): только реальные данные.

        # Рост участников: реконструкция по реальным приходам/уходам.
        result['member_labels'] = result['daily_labels']
        guild = None
        if bot:
            guild = bot.get_guild(int(guild_id))
        mc = guild.member_count if guild else 0
        counts = []
        try:
            from web.routes.analytics_plus import member_flow, member_count_series
            flow = member_flow(guild_id, days=7)
            if mc:
                # Бот на сервере — точка «сейчас» известна, восстанавливаем ряд.
                counts = member_count_series(mc, flow, days=7)
            else:
                # Бот не в сети/нет гильдии: абсолютный состав неизвестен.
                # Рисуем ЧЕСТНУЮ относительную динамику (0 = сегодня), а не
                # выдуманные абсолютные числа — иначе линия «участников» врёт.
                if any(flow.get('joins')) or any(flow.get('leaves')):
                    rel = member_count_series(0, flow, days=7)
                    base = rel[-1]
                    counts = [v - base for v in rel]
        except Exception as ex:
            _log.debug('api_guild_analytics(): member_flow подавлено: %s', ex)
        result['member_counts'] = counts

        return jsonify(result)


        # ── HEALTH API ────────────────────────────────────────────────────────────

    @app .route ('/api/guild/<guild_id>/health')
    @login_required 
    def api_guild_health (guild_id ):
        ban_count =0 
        kick_count =0 
        warn_count =0 
        spam_count =0 

        # mod_data.json
        mod_file ='data/mod_data.json'
        if os .path .exists (mod_file ):
            with open (mod_file ,'r',encoding ='utf-8')as fp :
                data =json .load (fp )
            case =data .get ('case',{}).get (guild_id ,[])
            for c in case :
                a =(c .get ('action')or '').lower ()
                if 'ban'in a :ban_count +=1 
                elif 'kick'in a :kick_count +=1 
                elif 'warn'in a :warn_count +=1 

                # warnings.json
        warns_file ='data/warnings.json'
        if os .path .exists (warns_file ):
            with open (warns_file ,'r',encoding ='utf-8')as fp :
                data =json .load (fp )
            guild_warns =data .get (guild_id ,{})
            for uid ,ws in guild_warns .items ():
                warn_count +=len (ws )

                # audit_log'dan spam tespiti
        audit_file ='data/audit_log.json'
        if os .path .exists (audit_file ):
            try :
                with open (audit_file ,'r',encoding ='utf-8')as fp :
                    data =json .load (fp )
            except Exception :
                data ={}
            for ev in data .get (guild_id ,[]):
                a =(ev .get ('action')or '').lower ()
                if 'spam'in a or 'automod'in a :
                    spam_count +=1 

                    # Расчёт оценки (вычитать из 100)
        score =100 
        score -=min (ban_count *3 ,30 )
        score -=min (kick_count *2 ,20 )
        score -=min (warn_count ,20 )
        score -=min (spam_count ,15 )
        score =max (0 ,score )

        if score >=80 :
            label ='Отлично'
        elif score >=60 :
            label ='Хорошо'
        elif score >=40 :
            label ='Средне'
        else :
            label ='Плохо'

        return jsonify ({
        'score':score ,
        'label':label ,
        'ban_count':ban_count ,
        'kick_count':kick_count ,
        'warn_count':warn_count ,
        'spam_count':spam_count 
        })


        # ── VOICE STATS API ───────────────────────────────────────────────────────

    @app .route ('/api/guild/<guild_id>/voice-stats')
    @login_required 
    def api_voice_stats (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 

        leaderboard =[]
        total_seconds =0

        from cogs .voice_tracker import voice_view ,voice_today_users ,fmt_duration
        # Данные — из SQLite через единый модуль (cogs/voice_tracker.py).
        # Легаси-JSON (data/voice_stats_*.json) мёртв: читателей не было
        # ни одного писателя; файл автомигрирует в базу при первом чтении.
        users_dict =voice_view (guild_id ).get ('users',{})

        for uid ,entry in users_dict .items ():
            if not isinstance (entry ,dict ):
                continue 
            raw_seconds =entry .get ('total_seconds',entry .get ('seconds',0 ))
            if not raw_seconds :
            # Legacy files store minutes instead of seconds.
                raw_seconds =entry .get ('minutes',0 )
                try :
                    raw_seconds =float (raw_seconds )*60 
                except (TypeError ,ValueError ):
                    raw_seconds =0 
            try :
                secs =max (0 ,int (float (raw_seconds )))
            except (TypeError ,ValueError ):
                secs =0 
            total_seconds +=secs 

            # Resolve the currently cached Discord profile where possible.
            name =entry .get ('name',uid )
            avatar =entry .get ('avatar','https://cdn.discordapp.com/embed/avatars/0.png')
            # Guild avatar URLs expire when a member changes their guild profile.
            # The canonical Discord CDN path is stable for a given avatar hash.
            if isinstance (avatar ,str )and '/guilds/'in avatar and '/users/'in avatar :
                import re 
                match =re .search (r'/users/(\d+)/avatars/([^/?]+)',avatar )
                if match :
                    avatar =f'https://cdn.discordapp.com/avatars/{match.group(1)}/{match.group(2)}?size=1024'
            if bot :
                for g in bot .guilds :
                    try :
                        m =g .get_member (int (uid ))
                        if m :
                            name =m .display_name 
                            avatar =str (m .display_avatar .url )
                            break 
                    except Exception as _ex:
                        _log.debug("api_voice_stats(): подавлено: %s", _ex)

            time_str =fmt_duration (secs )

            leaderboard .append ({
            'name':name ,
            'avatar':avatar ,
            'seconds':secs ,
            'time':time_str 
            })
        leaderboard .sort (key =lambda x :x ['seconds'],reverse =True )

        total_str =fmt_duration (total_seconds )

        # «Сегодня в голосе» — люди с ненулевым временем за текущую дату
        today_users =voice_today_users (guild_id )

        avg_secs =(total_seconds //len (leaderboard ))if leaderboard else 0
        avg_str =fmt_duration (avg_secs )

        return jsonify ({
        'leaderboard':leaderboard [:20 ],
        'total_time':total_str ,
        'today_users':today_users ,
        'avg_time':avg_str 
        })


        # ── PANEL LOGS API ────────────────────────────────────────────────────────

    @app .route ('/api/panel-logs')
    @login_required 
    @role_required ('admin')
    def api_panel_logs ():
        f ='data/panel_logs.json'
        if not os .path .exists (f ):
            return jsonify ([])
        try :
            with open (f ,'r',encoding ='utf-8')as fp :
                logs =json .load (fp )
                # En новый до
            logs =list (reversed (logs ))
            # человеческие ярлыки: «POST /api/.../appeals/resolve» → «Решение по апелляции»
            try :
                from web .app import _human_panel_action
                for e in logs :
                    if e .get ('broadcast')or not e .get ('action'):
                        continue
                    label ,icon ,link =_human_panel_action (e ['action'])
                    e ['label']=label ;e ['icon']=icon ;e ['link']=link
            except Exception as _ex:
                _log .debug ("api_panel_logs(): ярлыки: %s", _ex )
            return jsonify (logs )
        except (json .JSONDecodeError ,ValueError ):
            return jsonify ([])


    @app .route ('/api/panel-logs/clear',methods =['POST'])
    @login_required 
    @role_required ('owner')
    def api_clear_panel_logs ():
        f ='data/panel_logs.json'
        with open (f ,'w',encoding ='utf-8')as fp :
            json .dump ([],fp )
        return jsonify ({'success':True })


    @app .route ('/api/guild/<guild_id>/invite-tracker-full')
    @login_required 
    @role_required ('mod')
    def api_invite_tracker_full (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        result ={
        'total_invites':0 ,'total_joins':0 ,'total_leaves':0 ,
        'active_invites':0 ,'leaderboard':[],'recent_joins':[],'invite_list':[]
        }
        # Подтягиваем живые данные приглашений от бота
        if bot :
            import asyncio 
            guild =bot .get_guild (int (guild_id ))if str (guild_id ).isdigit ()else None 
            if guild :
                try :
                    invites_future =asyncio .run_coroutine_threadsafe (guild .invites (),bot .loop )
                    invites =invites_future .result (timeout =5 )
                    result ['active_invites']=len (invites )
                    result ['total_invites']=sum (inv .uses or 0 for inv in invites )
                    # Davet список
                    result ['invite_list']=[{
                    'code':inv .code ,
                    'inviter':inv .inviter .display_name if inv .inviter else '?',
                    'uses':inv .uses or 0 ,
                    'channel':inv .channel .name if inv .channel else '?'
                    }for inv in sorted (invites ,key =lambda x :x .uses or 0 ,reverse =True )]
                    # Liderboard - кто сколько человек davet etti
                    lb_map ={}
                    for inv in invites :
                        if inv .inviter :
                            uid =str (inv .inviter .id )
                            if uid not in lb_map :
                                lb_map [uid ]={
                                'name':inv .inviter .display_name ,
                                'avatar':str (inv .inviter .display_avatar .url ),
                                'total':0 ,'joins':0 ,'leaves':0 ,'fake':0 
                                }
                            lb_map [uid ]['total']+=inv .uses or 0 
                            lb_map [uid ]['joins']+=inv .uses or 0 
                    result ['leaderboard']=sorted (lb_map .values (),key =lambda x :x ['total'],reverse =True )[:20 ]
                except Exception as _ex:
                    _log.debug("api_invite_tracker_full(): подавлено: %s", _ex)
                    # JSON dosyasыndan Вход история oku
        joins_file =f'data/invite_joins_{guild_id}.json'
        if os .path .exists (joins_file ):
            try :
                with open (joins_file ,'r',encoding ='utf-8')as fp :
                    joins_data =json .load (fp )
            except Exception as _ex :
                _log .debug ('invite-tracker: битый %s: %s',joins_file ,_ex )
                joins_data =[]
            if not isinstance (joins_data ,list ):joins_data =[]
            result ['total_joins']=len (joins_data )
            result ['recent_joins']=list (reversed ([_norm_join (j )for j in joins_data [-50 :]]))
            # Ayrыlmalarы da say
            leaves_file =f'data/invite_leaves_{guild_id}.json'
            if os .path .exists (leaves_file ):
                try :
                    with open (leaves_file ,'r',encoding ='utf-8')as fp :
                        leaves_data =json .load (fp )
                except Exception as _ex :
                    _log .debug ('invite-tracker: битый %s: %s',leaves_file ,_ex )
                    leaves_data =[]
                if not isinstance (leaves_data ,list ):leaves_data =[]
                result ['total_leaves']=len (leaves_data )
                # Liderboard'a ayrыlmalarы add
                for leave in leaves_data :
                    inviter =leave .get ('inviter','')
                    for lb in result ['leaderboard']:
                        if lb ['name']==inviter :
                            lb ['leaves']+=1 
                            break 
                            # Старый format uyumluluгu
        old_file =f'data/invites_{guild_id}.json'
        if os .path .exists (old_file )and not result ['leaderboard']:
            with open (old_file )as fp :
                old =json .load (fp )
            result ['leaderboard']=old .get ('leaderboard',[])
            result ['total_joins']=result ['total_joins']or old .get ('total_joins',0 )
            result ['total_leaves']=result ['total_leaves']or old .get ('total_leaves',0 )
        return jsonify (result )


    @app .route ('/api/guild/<guild_id>/invite-tracker')
    @login_required 
    @role_required ('mod')
    def api_invite_tracker (guild_id ):
        f =f'data/invites_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ({'total_invites':0 ,'total_joins':0 ,'total_leaves':0 ,'fake_invites':0 ,'leaderboard':[]})
        with open (f )as fp :return jsonify (json .load (fp ))











        # ── STAFF SHIFTS (виджет и редактор дежурств) ─────────────────────────────
    def _staff_shifts_payload (gid ):
        """Текущая картина дежурств для панели (виджет + ответы мутаций редактора)."""
        from datetime import timedelta
        from db import GuildData
        from cogs .staff_shifts import active_shift ,next_shift ,iter_windows ,WEEKDAYS_RU
        import web .app as _app

        db =GuildData ('staff_shifts')
        shifts_map =db .get (gid ,'shifts',{})or {}
        raw_settings =db .get (gid ,'settings',{})or {}
        try :
            tz_offset =int (raw_settings .get ('tz_offset',3))
        except (TypeError ,ValueError ):
            tz_offset =3
        tz =timezone (timedelta (hours =tz_offset ))
        shifts =list (shifts_map .values ())

        # Имена из кэша бота; бот офлайн — честный фолбэк на ID.
        def _name (uid ):
            bot =_app .bot_instance
            if bot is not None :
                try :
                    g =bot .get_guild (gid )
                    m =g .get_member (int (uid ))if g else None
                    if m is not None :
                        return m .display_name
                except Exception as _ex :
                    _log .debug ("staff_shifts: имя не резолвится: %s",_ex )
            return f'ID {uid}'

        now =datetime .now (timezone .utc )

        current =None
        found =active_shift (shifts ,now ,tz_offset )
        if found :
            sh ,w_start ,w_end =found
            current ={'user_id':sh .get ('user_id'),'name':_name (sh .get ('user_id')),
            'start':sh .get ('start'),'end':sh .get ('end'),'ends_at':w_end .isoformat ()}

        nxt =None
        found_next =next_shift (shifts ,now ,tz_offset )
        if found_next :
            sh ,w_start =found_next
            nxt ={'user_id':sh .get ('user_id'),'name':_name (sh .get ('user_id')),
            'start':sh .get ('start'),'end':sh .get ('end'),
            'weekday':WEEKDAYS_RU [w_start .astimezone (tz ).weekday ()],
            'starts_at':w_start .isoformat ()}

        today =[]
        for sh ,w_start ,w_end in sorted (iter_windows (shifts ,now .astimezone (tz ).date (),tz_offset ),
        key =lambda t :t [1 ]):
            today .append ({'user_id':sh .get ('user_id'),'name':_name (sh .get ('user_id')),
            'start':sh .get ('start'),'end':sh .get ('end'),'active':w_start <=now <w_end })
        # активная смена, перенесённая с вчера через полночь, — первой строкой
        if current and not any (t ['active']for t in today ):
            today .insert (0 ,{'user_id':current ['user_id'],'name':current ['name'],
            'start':current ['start'],'end':current ['end'],'active':True })

        all_rows =sorted (
        ({'id':sid ,'user_id':s .get ('user_id'),'name':_name (s .get ('user_id')),
        'weekday':s .get ('weekday'),'weekday_ru':WEEKDAYS_RU [s .get ('weekday')]if isinstance (s .get ('weekday'),int )and 0 <=s .get ('weekday')<=6 else '?',
        'start':s .get ('start'),'end':s .get ('end')}for sid ,s in shifts_map .items ()),
        key =lambda r :(r ['weekday']if isinstance (r ['weekday'],int )else 99 ,r ['start']or ''))

        return {'success':True ,'tz_offset':tz_offset ,
        'current':current ,'next':nxt ,'today':today ,'all':all_rows ,
        'weekday':WEEKDAYS_RU [now .astimezone (tz ).weekday ()]}




