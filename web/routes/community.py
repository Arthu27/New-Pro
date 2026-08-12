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

def register(ctx):
    app = ctx.app
    ROLES = ctx.ROLES
    login_required = ctx.login_required
    role_required = ctx.role_required
    MAIN_GUILD_ID = ctx.MAIN_GUILD_ID
    active_guild_id = ctx.active_guild_id
    _resolve_member_async = ctx._resolve_member_async


        # ── ANALYTICS API ─────────────────────────────────────────────────────────

    @app .route ('/api/guild/<guild_id>/analytics')
    @login_required 
    def api_guild_analytics (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import collections ,datetime as dt 

        result ={
        'top_members':[],'top_channels':[],
        'daily_labels':[],'daily_messages':[],
        'member_labels':[],'member_counts':[]
        }

        # audit_log.json'dan message статистика тянуть
        audit_file ='data/audit_log.json'
        member_msg_counts =collections .Counter ()
        channel_msg_counts =collections .Counter ()
        daily_counts =collections .Counter ()

        if os .path .exists (audit_file ):
            try :
                with open (audit_file ,'r',encoding ='utf-8')as fp :
                    data =json .load (fp )
            except Exception :
                data ={}
            events =data .get (guild_id ,[])
            for ev in events :
                action =(ev .get ('action')or '').lower ()
                category =(ev .get ('category')or '').lower ()
                if category =='message'and action =='message написано':
                    name =ev .get ('user_name')or ev .get ('user_id','?')
                    member_msg_counts [name ]+=1 
                    ch =ev .get ('channel')or ev .get ('channel_name','?')
                    channel_msg_counts [ch ]+=1 
                    ts =ev .get ('timestamp','')
                    if ts :
                        try :
                            day =ts [:10 ]
                            daily_counts [day ]+=1 
                        except Exception as _ex:
                            _log.debug("api_guild_analytics(): подавлено: %s", _ex)

                            # Если в audit_log нет сообщений — смотреть файл message_logs
        msg_log_file =f'data/message_logs_{guild_id}.json'
        if not member_msg_counts and os .path .exists (msg_log_file ):
            with open (msg_log_file ,'r',encoding ='utf-8')as fp :
                msgs =json .load (fp )
            for m in msgs :
                name =m .get ('author')or m .get ('user_name','?')
                member_msg_counts [name ]+=1 
                ch =m .get ('channel','?')
                channel_msg_counts [ch ]+=1 
                ts =m .get ('timestamp','')
                if ts :
                    try :
                        daily_counts [ts [:10 ]]+=1 
                    except Exception as _ex:
                        _log.debug("api_guild_analytics(): подавлено: %s", _ex)

                        # Берём у бота свежие данные по участникам
        if bot :
            guild =bot .get_guild (int (guild_id ))
            if guild :
            # Если данных о сообщениях нет, показываем хотя бы активных участников
                if not member_msg_counts :
                # Участники сортируются по количеству ролей (приблизительный показатель активности)
                    for m in list (guild .members )[:10 ]:
                        if not m .bot :
                            member_msg_counts [m .display_name ]=len (m .roles )

                            # Метки последних 7 дней
        today =dt .date .today ()
        labels =[(today -dt .timedelta (days =i )).isoformat ()for i in range (6 ,-1 ,-1 )]
        result ['daily_labels']=[l [5 :]for l in labels ]# формат ММ-ДД
        result ['daily_messages']=[daily_counts .get (l ,0 )for l in labels ]

        # Топ участников
        result ['top_members']=[
        {'name':name ,'messages':count }
        for name ,count in member_msg_counts .most_common (10 )
        ]

        # Топ каналов
        result ['top_channels']=[
        {'name':ch ,'messages':count }
        for ch ,count in channel_msg_counts .most_common (10 )
        ]

        # Рост участников (последние 7 дней — приблизительные данные, не реального времени)
        result ['member_labels']=result ['daily_labels']
        if bot :
            guild =bot .get_guild (int (guild_id ))
            mc =guild .member_count if guild else 0 
        else :
            mc =0 
        result ['member_counts']=[max (0 ,mc -(6 -i )*2 )for i in range (7 )]

        return jsonify (result )


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

        # Defaults are defined before touching the optional statistics file.
        # This keeps the endpoint JSON-safe when no file exists yet.
        leaderboard =[]
        total_seconds =0 
        today_data ={}

        # Read persisted voice statistics.  This endpoint must always return JSON:
        # a malformed/old statistics file should заметок turn into an HTML 500 response.
        vs_file =f'data/voice_stats_{guild_id}.json'
        data ={}
        if os .path .exists (vs_file ):
            try :
                with open (vs_file ,'r',encoding ='utf-8')as fp :
                    data =json .load (fp )
            except (OSError ,json .JSONDecodeError ):
                data ={}

        users_dict =data .get ('users',data )if isinstance (data ,dict )else {}
        today_data =data .get ('today',{})if isinstance (data ,dict )else {}
        if not isinstance (users_dict ,dict ):
            users_dict ={}

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

            h ,rem =divmod (int (secs ),3600 )
            m_val ,s_val =divmod (rem ,60 )
            if h >0 :
                time_str =f'{h}s {m_val}dk'
            elif m_val >0 :
                time_str =f'{m_val}dk {s_val}sn'
            else :
                time_str =f'{s_val}sn'

            leaderboard .append ({
            'name':name ,
            'avatar':avatar ,
            'seconds':secs ,
            'time':time_str 
            })
        leaderboard .sort (key =lambda x :x ['seconds'],reverse =True )

        # Всего длительность formatla
        th ,trem =divmod (total_seconds ,3600 )
        tm ,_ =divmod (trem ,60 )
        total_str =f'{th}s {tm}dk'if th >0 else f'{tm}dk'

        # Сегодня VC использовать (basit tahmin)
        today_users =len (today_data )if isinstance (today_data ,dict )else sum (1 for u in leaderboard if u ['seconds']>0 )

        avg_secs =(total_seconds //len (leaderboard ))if leaderboard else 0 
        ah ,arem =divmod (avg_secs ,3600 )
        am ,_ =divmod (arem ,60 )
        avg_str =f'{ah}s {am}dk'if ah >0 else f'{am}dk'

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
            return jsonify (list (reversed (logs )))
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
            guild =bot .get_guild (int (guild_id ))
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
            with open (joins_file ,'r',encoding ='utf-8')as fp :
                joins_data =json .load (fp )
            result ['total_joins']=len (joins_data )
            result ['recent_joins']=list (reversed (joins_data [-50 :]))
            # Ayrыlmalarы da say
            leaves_file =f'data/invite_leaves_{guild_id}.json'
            if os .path .exists (leaves_file ):
                with open (leaves_file ,'r',encoding ='utf-8')as fp :
                    leaves_data =json .load (fp )
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


    @app .route ('/api/guild/<guild_id>/suggestions')
    @login_required 
    @role_required ('mod')
    def api_suggestions (guild_id ):
        f =f'data/suggestions_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ([])
        with open (f )as fp :return jsonify (list (json .load (fp ).values ()))


    @app .route ('/api/guild/<guild_id>/suggestions/<sug_id>/review',methods =['POST'])
    @login_required 
    @role_required ('mod')
    def api_review_suggestion (guild_id ,sug_id ):
        f =f'data/suggestions_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ({'error':'Не найдено'})
        with open (f )as fp :data =json .load (fp )
        if sug_id in data :
            data [sug_id ]['status']='approved'if request .get_json (silent =True ).get ('action')=='approve'else 'rejected'
            with open (f ,'w')as fp :json .dump (data ,fp ,indent =2 )
        return jsonify ({'success':True })


    @app .route ('/api/guild/<guild_id>/suggestions/channel',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_suggestions_channel (guild_id ):
        f =f'data/sug_settings_{guild_id}.json'
        with open (f ,'w')as fp :json .dump (request .get_json (silent =True ),fp )
        return jsonify ({'success':True })


    @app .route ('/api/guild/<guild_id>/starboard')
    @login_required 
    @role_required ('mod')
    def api_starboard (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        f =f'data/starboard_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ([])

        with open (f ,encoding ='utf-8')as fp :
            data =json .load (fp )

            # Подтягиваем детали сообщений от бота
        result =[]
        if bot :
            guild =bot .get_guild (int (guild_id ))
            if guild :
                import asyncio 
                for msg_id ,entry in data .items ():
                    try :
                    # Сообщение bul
                        for channel in guild .text_channels :
                            try :
                                msg_future =asyncio .run_coroutine_threadsafe (
                                channel .fetch_message (int (msg_id )),
                                bot .loop 
                                )
                                msg =msg_future .result (timeout =2 )
                                result .append ({
                                'id':msg_id ,
                                'count':entry .get ('stars',0 ),
                                'content':msg .content [:200 ]if msg .content else '',
                                'author':msg .author .display_name ,
                                'channel':channel .name ,
                                'jump_url':msg .jump_url ,
                                'created_at':entry .get ('created_at','')
                                })
                                break 
                            except Exception as _ex:
                                _log.debug("api_starboard(): подавлено: %s", _ex)
                                continue 
                    except Exception:
                    # Сообщение не найдено, только запись veriyi показать
                        result .append ({
                        'id':msg_id ,
                        'count':entry .get ('stars',0 ),
                        'content':'',
                        'author':'?',
                        'channel':'?',
                        'jump_url':'',
                        'created_at':entry .get ('created_at','')
                        })

                        # Yыldыz число по очередь
        result .sort (key =lambda x :x ['count'],reverse =True )
        return jsonify (result )


    @app .route ('/api/guild/<guild_id>/starboard/settings',methods =['GET','POST'])
    @login_required 
    @role_required ('admin')
    def api_starboard_settings (guild_id ):
        f =f'data/starboard_settings_{guild_id}.json'
        if request .method =='GET':
            if not os .path .exists (f ):return jsonify ({'min_stars':3 })
            with open (f )as fp :return jsonify (json .load (fp ))
        with open (f ,'w')as fp :json .dump (request .get_json (silent =True ),fp )
        return jsonify ({'success':True })
