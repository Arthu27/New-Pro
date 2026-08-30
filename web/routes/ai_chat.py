# -*- coding: utf-8 -*-
"""AI-чат панели (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

from web.routes._common import (
    _run_async, _fetch_channel_msgs_async, _fetch_channel_msgs_sync,
    _load_ai_tickets, _notify_discord_sender, _fire_panel_notification,
    _process_action, _log,
    ms_normalize_query, ms_member_match, ms_search_members, ms_member_payload,
    ms_normalize_warn, ms_normalize_case, calculate_ai_ticket_stats, _REPO_ROOT,
    render_template, session, redirect, url_for, request, jsonify, Response,
    os, json, time, math, discord, datetime, timezone,
)

# Модель панельного AI — заказ владельца: в панели заведомо СЛАБАЯ (дешёвая)
# модель; боевой сильный ответчик живёт в Discord-чате (cogs/ai_chat).
# Переопределяется через AI_PANEL_MODEL в .env.
_AI_PANEL_MODEL = (os.getenv('AI_PANEL_MODEL', 'mistral-small-latest')
                   or 'mistral-small-latest')

def register(ctx):
    app = ctx.app
    ROLES = ctx.ROLES
    login_required = ctx.login_required
    role_required = ctx.role_required
    MAIN_GUILD_ID = ctx.MAIN_GUILD_ID
    active_guild_id = ctx.active_guild_id
    _resolve_member_async = ctx._resolve_member_async


    @app .route ('/birthday-register')
    @login_required 
    @role_required ('uye')
    def birthday_register_page ():
        return render_template ('birthday_register.html',role =session .get ('role'),username =session .get ('username'),guild_id =active_guild_id ())


    @app .route ('/ai-chat')
    @login_required 
    @role_required ('uye')
    def ai_chat_page ():
        return render_template ('ai_chat_panel.html',role =session .get ('role'),username =session .get ('username'),guild_id =active_guild_id ())


    @app .route ('/api/ai-chat',methods =['POST'])
    @login_required 
    @role_required ('uye')
    def api_ai_chat ():
        """Panel AI — tam сервер доступ + выполнение действий"""
        from web .ai_helper import _call 
        import web .app as _app ;bot =_app .bot_instance 
        import datetime as _dt ,asyncio as _asyncio ,discord as _discord 
        d =request .get_json (silent =True )or {}
        question =d .get ('message','').strip ()
        if not question :
            return jsonify ({'error':'Сообщение пусто'}),400 

        history_key =f'ai_history_{session.get("username", "anon")}'
        history =session .get (history_key ,[])
        user_role =session .get ('role','uye')
        now =_dt .datetime .now ()

        # ── СЕРВЕР VERИSИ собрать ──────────────────────────────────────────────
        guild_data =[]
        if bot :
            for g in bot .guilds :
                online =[m for m in g .members if not m .bot and m .status !=_discord .Status .offline ]
                in_voice =[]
                for vc in g .voice_channels :
                    mems =[m .display_name for m in vc .members if not m .bot ]
                    if mems :in_voice .append (f"{vc.name}: {', '.join(mems)}")
                channels =[f"#{c.name}(id={c.id})"for c in g .text_channels [:20 ]]
                role =[r .name for r in g .roles if not r .is_default ()][:15 ]
                # Список участников (для сопоставления имя→ID в действиях)
                members_list =[f"{m.display_name}(id={m.id})"for m in g .members if not m .bot ][:50 ]

                # Прочитать все data-файлы сервера
                server_configs =[]
                config_files ={
                f'data/automod_{g.id}.json':'Настройки Automod',
                f'data/antiraid_{g.id}.json':'Настройки Anti-raid',
                f'data/health_{g.id}.json':'Состояние сервера',
                f'data/badges_{g.id}.json':'Значки',
                f'data/warn_config_{g.id}.json':'Лимиты предупреждений',
                }
                for fpath ,flabel in config_files .items ():
                    if os .path .exists (fpath ):
                        try :
                            with open (fpath ,'r',encoding ='utf-8')as fp :
                                fdata =json .load (fp )
                                # Только сводка info отправить (token tasarrufu)
                            if flabel =='Состояние сервера':
                                score =fdata .get ('score',fdata .get ('health_score','?'))
                                label =fdata .get ('label',fdata .get ('status','?'))
                                server_configs .append (f"{flabel}: {score}/100 ({label})")
                            elif flabel =='Настройки Automod':
                                enabled =[k for k ,v in fdata .items ()if isinstance (v ,dict )and v .get ('enabled')]
                                server_configs .append (f"{flabel}: {', '.join(enabled) or 'Нет'}")
                            elif flabel =='Лимиты предупреждений':
                                thresholds =fdata .get ('thresholds',[])
                                server_configs .append (f"{flabel}: {thresholds}")
                            else :
                                server_configs .append (f"{flabel}: текущий")
                        except Exception as _ex:
                            _log.debug("api_ai_chat(): подавлено: %s", _ex)

                        # Warning число
                warn_summary =''
                warns_f ='data/warnings.json'
                if os .path .exists (warns_f ):
                    try :
                        with open (warns_f ,'r',encoding ='utf-8')as fp :
                            wd =json .load (fp )
                        gw =wd .get (str (g .id ),{})
                        total_warns =sum (len (v )for v in gw .values ())
                        top_warned =sorted (gw .items (),key =lambda x :len (x [1 ]),reverse =True )[:3 ]
                        top_names =[]
                        for uid ,ws in top_warned :
                            m =g .get_member (int (uid ))if uid .isdigit ()else None 
                            name =m .display_name if m else uid 
                            top_names .append (f"{name}({len(ws)})")
                        warn_summary =f"Всего предупреждение: {total_warns}, En очень: {', '.join(top_names)}"
                    except Exception as _ex:
                        _log.debug("api_ai_chat(): подавлено: %s", _ex)

                guild_data .append (
                f"Сервер: {g.name} (id={g.id})\n"
                f"  Всего участников: {g.member_count}, Онлайн: {len(online)}\n"
                f"  Голосовые каналы: {', '.join(in_voice) or 'Пусто'}\n"
                f"  Каналы: {', '.join(channels)}\n"
                f"  Роли: {', '.join(role)}\n"
                f"  Участники: {', '.join(members_list)}\n"
                +(f"  Предупреждения: {warn_summary}\n"if warn_summary else '')
                +('\n'.join (f'  {c}'for c in server_configs ))
                )

                # ── ПОЛЬЗОВАТЕЛЬ ID TESPИT ET VE ИНФОРМАЦИЯ ТЯНУТЬ ─────────────────────────────
        import re as _re2 
        user_info_block =''
        id_matches =_re2 .findall (r'\b(\d{17,20})\b',question )
        # Поиск имени — только в кавычках или явные имена
        name_matches =_re2 .findall (r'"([^"]+)"',question )# имена в кавычках
        if not id_matches and bot and name_matches :
            for name_q in name_matches [:2 ]:
                for g in bot .guilds :
                    m =discord .utils .find (
                    lambda mem :mem .display_name .lower ()==name_q .lower ()or mem .name .lower ()==name_q .lower (),
                    g .members 
                    )
                    if m :
                        id_matches .append (str (m .id ))
                        break 
        if id_matches and bot :
            for uid_str in id_matches [:3 ]:# max 3 ID
                uid =int (uid_str )
                for g in bot .guilds :
                    member =g .get_member (uid )
                    if not member :
                        continue 
                        # Роли
                    member_roles =[r .name for r in member .roles if r .name !='@everyone']
                    # Предупреждения
                    warn_count =0 
                    warns_file ='data/warnings.json'
                    warn_list =[]
                    if os .path .exists (warns_file ):
                        try :
                            with open (warns_file ,'r',encoding ='utf-8')as fp :
                                wd =json .load (fp )
                            warn_list =wd .get (str (g .id ),{}).get (uid_str ,[])
                            warn_count =len (warn_list )
                        except Exception as _ex:
                            _log.debug("api_ai_chat(): подавлено: %s", _ex)
                        # История модерации — из mod_data.json и кэша аудита Discord
                    mod_history =[]
                    mod_file ='data/mod_data.json'
                    if os .path .exists (mod_file ):
                        try :
                            with open (mod_file ,'r',encoding ='utf-8')as fp :
                                md =json .load (fp )
                            case =md .get ('case',{}).get (str (g .id ),[])
                            for c in case :
                                if str (c .get ('user_id',''))==uid_str :
                                    mod_history .append (
                                    f"{c.get('timestamp','')[:10]} {c.get('action','?').upper()} — "
                                    f"Mod: {c.get('mod_id','?')} — {c.get('reason','?')}"
                                    )
                        except Exception as _ex:
                            _log.debug("api_ai_chat(): подавлено: %s", _ex)
                        # Также подтягиваем из кэша аудита Discord
                    cache_f ='data/discord_audit_cache.json'
                    if os .path .exists (cache_f ):
                        try :
                            with open (cache_f ,'r',encoding ='utf-8')as fp :
                                cdata =json .load (fp )
                            for gid_c ,evs in cdata .items ():
                                for ev in evs :
                                    if str (ev .get ('target_id',''))==uid_str :
                                        ts =ev .get ('timestamp','')[:16 ].replace ('T',' ')
                                        mod_history .append (
                                        f"{ts} {ev.get('action','?')} — "
                                        f"Mod: {ev.get('mod_name','?')} — {ev.get('reason','') or 'Причины нет'}"
                                        )
                        except Exception as _ex:
                            _log.debug("api_ai_chat(): подавлено: %s", _ex)
                        # История ролей — из кэша аудита: кто выдал/снял ролей
                    role_gecmisi =[]
                    if os .path .exists (cache_f ):
                        try :
                            with open (cache_f ,'r',encoding ='utf-8')as fp :
                                cdata2 =json .load (fp )
                            for gid_c ,evs in cdata2 .items ():
                                for ev in evs :
                                    if str (ev .get ('target_id',''))==uid_str and ev .get ('action')=='Изменение ролей':
                                        ts =ev .get ('timestamp','')[:16 ].replace ('T',' ')
                                        role_gecmisi .append (
                                        f"{ts} Изменение ролей — Мод: {ev.get('mod_name','?')} — {ev.get('reason','') or ev.get('before','') or ''}"
                                        )
                        except Exception as _ex:
                            _log.debug("api_ai_chat(): подавлено: %s", _ex)
                    role_gecmisi .sort ()
                    # Кто пригласил
                    inviter ='?'
                    invite_file =f'data/invite_joins_{g.id}.json'
                    if os .path .exists (invite_file ):
                        try :
                            with open (invite_file ,'r',encoding ='utf-8')as fp :
                                inv =json .load (fp )
                            inviter =inv .get (uid_str ,{}).get ('inviter_name','?')
                        except Exception as _ex:
                            _log.debug("api_ai_chat(): подавлено: %s", _ex)
                        # Дата присоединения
                    joined =member .joined_at .strftime ('%d.%m.%Y %H:%M')if member .joined_at else '?'
                    created =member .created_at .strftime ('%d.%m.%Y')if member .created_at else '?'
                    # Статус мута
                    timed_out ='Да'if member .is_timed_out ()else 'Нет'

                    user_info_block +=(
                    f"\n=== ИНФОРМАЦИЯ О ПОЛЬЗОВАТЕЛЕ: {member.display_name} (ID: {uid_str}) ===\n"
                    f"  Сервер: {g.name}\n"
                    f"  Имя пользователя: {member.name}\n"
                    f"  Состояние: {str(member.status)}\n"
                    f"  Мут: {timed_out}\n"
                    f"  Вступил: {joined}\n"
                    f"  Аккаунт создан: {created}\n"
                    f"  Роли: {', '.join(member_roles) or 'Нет'}\n"
                    f"  Предупреждений: {warn_count}\n"
                    f"  Предупреждения: {'; '.join([w.get('reason','?') for w in warn_list[-5:]]) or 'Нет'}\n"
                    f"  История модерации ({len(mod_history)} записей):\n"
                    )
                    user_info_block +=('\n'.join (f'    {h}'for h in mod_history )if mod_history else '    чисто')+'\n'
                    user_info_block +=(f"  История ролей ({len(role_gecmisi)} записей):\n"+'\n'.join (f'    {r}'for r in role_gecmisi )+'\n')if role_gecmisi else '  История ролей: записей нет\n'
                    user_info_block +=f"  Пригласил: {inviter}\n"
                    break 

                    # ── ИСТОРИЯ СООБЩЕНИЙ КАНАЛА (если в вопросе упоминается канал) ──────
        channel_messages_block =''
        import re as _re3 
        channel_mentions =_re3 .findall (r'#([\w\-]+)',question )
        channel_keywords =['channel','текст','написано','messagelar','son message']
        if bot and (channel_mentions or any (k in question .lower ()for k in channel_keywords )):
            try :
                import asyncio as _asyncio3 
                ch_lines =_asyncio3 .run_coroutine_threadsafe (
                _fetch_channel_msgs_sync (bot ,channel_mentions ),bot .loop 
                ).result (timeout =8 )
                if ch_lines :
                    channel_messages_block ="\n=== КАНАЛ СООБЩЕНИЯ ===\n"+'\n'.join (ch_lines [:30 ])
            except Exception as _ex:
                _log.debug("api_ai_chat(): подавлено: %s", _ex)
        recent_logs =[]
        cache_file_logs ='data/discord_audit_cache.json'
        if os .path .exists (cache_file_logs ):
            try :
                with open (cache_file_logs ,'r',encoding ='utf-8')as fp :
                    ald =json .load (fp )
                for gid ,evs in ald .items ():
                    for ev in evs [-5 :]:
                        recent_logs .append (
                        f"[{ev.get('timestamp','')[:16]}] {ev.get('action','?')}: "
                        f"{ev.get('target_name', ev.get('user_name','?'))} — "
                        f"Mod: {ev.get('mod_name','?')} — {ev.get('reason','')}"
                        )
            except Exception as _ex:
                _log.debug("api_ai_chat(): подавлено: %s", _ex)

            # Статистика модерации — читаем из кэша (бот обновляет каждые 30 сек)
        mod_stats =''
        today =_dt .datetime.now(timezone.utc).replace(tzinfo=None).date ()
        yesterday =today -_dt .timedelta (days =1 )
        today_actions =[]
        yesterday_actions =[]

        cache_file_mod ='data/discord_audit_cache.json'
        if os .path .exists (cache_file_mod ):
            try :
                with open (cache_file_mod ,'r',encoding ='utf-8')as fp :
                    cache_data =json .load (fp )
                mod_action_types ={'Бан','Кик','Мут','Unban','Бан снят','Мут снят'}
                for gid ,evs in cache_data .items ():
                    for ev in evs :
                        ts =ev .get ('timestamp','')
                        if ev .get ('action')not in mod_action_types :
                            continue 
                        ev_date =ts [:10 ]
                        entry ={
                        'action':ev .get ('action','?'),
                        'target':ev .get ('target_name','?'),
                        'mod':ev .get ('mod_name','?'),
                        'reason':ev .get ('reason',''),
                        'time':ts [11 :16 ],
                        }
                        if ev_date ==str (today ):
                            today_actions .append (entry )
                        elif ev_date ==str (yesterday ):
                            yesterday_actions .append (entry )
            except Exception as _fe :
                print (f'[AI] Ошибка чтения кэша: {_fe}')

        def fmt_actions (actions ):
            if not actions :
                return '  Нет'
            return '\n'.join (
            f"  {a['time']} {a['action']} — Цель: {a['target']} — Мод: {a['mod']}"
            +(f" — Причина: {a['reason']}"if a ['reason']else '')
            for a in actions 
            )

        t_ban =sum (1 for c in today_actions if c ['action']=='Бан')
        t_kick =sum (1 for c in today_actions if c ['action']=='Кик')
        t_to =sum (1 for c in today_actions if c ['action']=='Мут')

        # Сегодняшние предупреждения — прочитать из warnings.json
        today_warns =[]
        warns_f2 ='data/warnings.json'
        if os .path .exists (warns_f2 ):
            try :
                with open (warns_f2 ,'r',encoding ='utf-8')as fp :
                    wd2 =json .load (fp )
                for gid2 ,guild_warns2 in wd2 .items ():
                    for uid2 ,warn_list2 in guild_warns2 .items ():
                        for w in warn_list2 :
                            ts2 =w .get ('timestamp','')
                            if ts2 [:10 ]==str (today ):
                                today_warns .append ({
                                'action':'Warning',
                                'target':uid2 ,
                                'mod':w .get ('moderator',w .get ('mod','?')),
                                'reason':w .get ('reason',''),
                                'time':ts2 [11 :16 ],
                                })
            except Exception as _ex:
                _log.debug("api_ai_chat(): подавлено: %s", _ex)

        mod_stats =(
        f"Сегодня ({today}) — Ban: {t_ban}, Kick: {t_kick}, Mute: {t_to}, Warning: {len(today_warns)}\n"
        f"Сегодня mod действия:\n{fmt_actions(today_actions)}\n"
        f"Сегодня предупреждения:\n{fmt_actions(today_warns) if today_warns else '  Yok'}\n\n"
        f"Вчера ({yesterday}) действия:\n{fmt_actions(yesterday_actions)}"
        )

        # состояние skoru — все guild'lerin health dosyalarыndan тянуть
        health_info =''
        health_lines =[]
        if bot :
            for g in bot .guilds :
                hf =f'data/health_{g.id}.json'
                if os .path .exists (hf ):
                    try :
                        with open (hf ,'r',encoding ='utf-8')as fp :
                            hd =json .load (fp )
                        score =hd .get ('score',hd .get ('health_score','?'))
                        label =hd .get ('label',hd .get ('status','?'))
                        health_lines .append (f"{g.name}: {score}/100 ({label})")
                    except Exception as _ex:
                        _log.debug("api_ai_chat(): подавлено: %s", _ex)
        if health_lines :
            health_info ='Оценки состояния сервера:\n'+'\n'.join (f'  {l}'for l in health_lines )
        else :
        # Fallback: API'den hesapla
            try :
                # Порт панели берём из того же источника, что и сам сервер
                # (PANEL_PORT -> PORT из config.py), а не «магическую»
                # константу: self-call дружит с любой настройкой портов.
                try :
                    from config import Config as _Cfg
                    _panel_port =int (os .environ .get ('PANEL_PORT','')or 0)or int (getattr (_Cfg ,'PORT',5001))
                except Exception :
                    _panel_port =5001 
                import requests as _req2 
                for g in (bot .guilds if bot else []):
                    r =_req2 .get (
                    f'http://127.0.0.1:{_panel_port}/api/guild/{g.id}/health',
                    cookies =request .cookies ,timeout =3 
                    )
                    if r .status_code ==200 :
                        hd =r .json ()
                        health_info =f"{g.name} состояние skoru: {hd.get('score','?')}/100 ({hd.get('label','?')})"
                        break 
            except Exception as _ex:
                _log.debug("api_ai_chat(): подавлено: %s", _ex)

            # ── СИСТЕМА PROMPT ────────────────────────────────────────────────────
        is_owner =user_role =='owner'

        if is_owner :
            eylem_prompt =(
            "=== РЕЖИМ J.A.R.V.I.S. (ВЛАДЕЛЕЦ) ===\n"
            "Ты — личный ассистент Arthur'а.\n\n"
            "ПРАВИЛО ДЕЙСТВИЙ — использовать тег [EYLEM:...] ТОЛЬКО при явном запросе:\n"
            "  'закрыть канал' / 'закрой канал' / 'заблокируй канал' → [EYLEM:KANAL_KILITLE:channel_id_or_name]\n"
            "  'открыть канал' / 'разблокируй' → [EYLEM:KANAL_AC:channel_id_or_name]\n"
            "  'бан' / 'забанить' → [EYLEM:BAN:user_id:причина]\n"
            "  'кик' / 'выгнать' → [EYLEM:KICK:user_id:причина]\n"
            "  'мут' / 'тайм-аут' / 'заткнуть' → [EYLEM:TIMEOUT:user_id:минуты:причина]\n"
            "  'напиши в канал' / 'отправь сообщение' + ad_канала + текст → [EYLEM:СООБЩЕНИЕ:channel_name:text]\n"
            "  'медленный режим' / 'slowmode' → [EYLEM:KANAL_YAVAШ:channel_id:секунды]\n"
            "  'выдай роль' / 'дай роль' → [EYLEM:ROL_VER:user_id:role_id]\n"
            "  'забери роль' / 'убери роль' → [EYLEM:ROL_AL:user_id:role_id]\n"
            "  'отправь ЛС' / 'напиши в ЛС' → [EYLEM:DM:user_id_or_name:text]\n"
            "  'выкинь из голоса' → [EYLEM:SESTEN_AT:user_id]\n"
            "  'перемести в канал' + user + channel → [EYLEM:SESE_TAS:user_id:channel_name]\n"
            "  'на голосовой выше' / 'подними на этаж' → [EYLEM:UST_SESE:user_id:шаги] (отмена: добавить :geri)\n"
            "  'на голосовой ниже' / 'опусти' → [EYLEM:ALT_SESE:user_id:шаги] (отмена: добавить :geri)\n"
            "  Пример: 'на 1 этаж выше и верни обратно' → [EYLEM:UST_SESE:user_id:1:geri]\n"
            "  ВАЖНО: для 'выше/ниже' ОБЯЗАТЕЛЬНО UST_SESE/ALT_SESE, не SESE_TAS!\n"
            "  'заглуши' (в голосе) → [EYLEM:SUSTUR:user_id]\n"
            "  'заглушение снять' → [EYLEM:SUSTUR_KALDIR:user_id]\n"
            "  'наушники закрыть' → [EYLEM:KULAKLIK_KAPAT:user_id]\n"
            "  'наушники открыть' → [EYLEM:KULAKLIK_AC:user_id]\n"
            "  'снять тайм-аут' → [EYLEM:TIMEOUT_KALDIR:user_id]\n"
            "  'разбанить' → [EYLEM:UNBAN:user_id]\n"
            "  'предупредить' / 'варн' → [EYLEM:ПРЕДУПРЕЖДЕНИЕ:user_id:причина]\n"
            "  'очистить предупреждения' → [EYLEM:UYARI_TEMIZLE:user_id]\n"
            "  'удалить сообщения' → [EYLEM:MESAJ_SIL:channel:число]\n"
            "  'создать канал' → [EYLEM:KANAL_OLUSTUR:имя-канала]\n"
            "  'создать голосовой канал' → [EYLEM:SES_KANAL_OLUSTUR:имя канала]\n"
            "  'создать роль' → [EYLEM:ROL_OLUSTUR:имя роли]\n"
            "  'объявление' / 'анонс' → [EYLEM:DUYURU:channel:text]\n"
            "  'сменить ник' / 'добавить к нику X' → [EYLEM:NICK:user_id:новый_ник]\n\n"
            "ЗАПРЕЩЕНО: 'удали', 'что', 'кто', 'сколько', 'покажи', 'есть ли', 'статус', 'состояние', 'список', 'прочитай', 'посмотри', 'собираюсь', 'ухожу', 'меня нет' — НИКОГДА не создавай действие!\n"
            "ВАЖНО: используй имя канала вместо ID — система сама найдёт. Пример: [EYLEM:СООБЩЕНИЕ:общий:привет]\n"
            "ОБЯЗАТЕЛЬНО: если пользователь просит 'покажи/найди/выведи сообщения <ник/id>' — НЕМЕДЛЕННО вызывай [FUNC:search_user_messages(user_id=<id>, limit=20)]. НЕ говори 'Discord API недоступен' — есть гибридный поиск (API + лог).\n"
            "Отвечай кратко и по делу.\n"
            )
        else :
            eylem_prompt =(
            "=== РЕЖИМ ИНФОРМАЦИИ ===\n"
            "Этот пользователь может только запрашивать информацию, не может выполнять действия.\n"
            "Если пользователь запрашивает действие, ответь: 'Это действие доступно только владельцу или администратору'.\n"
            )

        # Всё о панели и боте: роли (включая Куратора), разделы и страницы —
        # ИИ отвечает про панель точно и не выдумывает ссылок.
        panel_kb =''
        try :
            from web .ai_knowledge import build_panel_knowledge
            panel_kb =build_panel_knowledge (compact =True )
        except Exception as _ex:
            _log.debug("api_ai_chat(): подавлено: %s", _ex )

        system =(
        "Ты Hakumo — ИИ-ассистент Discord-сервера Hakumo и веб-панели.\n"
        f"Пользователь: {session.get('username')}, Роль: {user_role}\n"
        f"Время: {now.strftime('%H:%M')}, Дата: {now.strftime('%d %B %Y, %A')}\n\n"
        +(f"=== ВСЁ О ПАНЕЛИ И БОТЕ ===\n{panel_kb}\n\n"if panel_kb else '')+
        "=== СОСТОЯНИЕ СЕРВЕРА ===\n"
        f"{chr(10).join(guild_data) if guild_data else 'Бот не в сети'}\n\n"
        f"=== СТАТИСТИКА МОДЕРАЦИИ ===\n{mod_stats}\n\n"
        f"{f'=== СОСТОЯНИЕ ЗДОРОВЬЯ ==={chr(10)}{health_info}{chr(10)}{chr(10)}' if health_info else ''}"
        f"=== ПОСЛЕДНИЕ ЛОГИ (последние 10) ===\n{chr(10).join(recent_logs[-10:]) if recent_logs else 'Логов нет'}\n\n"
        f"{user_info_block}"
        f"{channel_messages_block}\n"
        f"{eylem_prompt}\n"
        "Говори ТОЛЬКО на русском языке. Никакого турецкого, никакого английского. "
        "Используй ТОЛЬКО реальные данные из контекста выше, никогда не выдумывай. "
        "Если в списке нет нужного имени или действия, скажи 'Такого пользователя/действия в записях нет'. "
        "При выполнении действия используй ID участника, а не имя — в списке участников у каждого есть ID.\n"
        "Не используй markdown кодовые блоки (```) в ответе — пиши обычным текстом."
        )

        messages =[{'role':'system','content':system }]
        messages .extend (history [-20 :])
        messages .append ({'role':'user','content':question })

        try :
            answer ,model_name ,_ =_call (messages ,max_tokens =1024 ,model =_AI_PANEL_MODEL )
        except Exception as e :
        # Fallback: локальный ответ
            print (f"[AI-CHAT] _call exception: {e}")
            from web .ai_helper import _local_moebius_fallback 
            try :
                answer ,model_name ,_ =_local_moebius_fallback (messages )
            except Exception as _fe :
                print (f"[AI-CHAT] fallback exception: {_fe}")
                return jsonify ({'error':'AI сервис сейчас недоступен. Попробуйте позже.'}),503 
        if not answer :
            from web .ai_helper import _local_moebius_fallback 
            try :
                answer ,model_name ,_ =_local_moebius_fallback (messages )
            except Exception :
                return jsonify ({'error':'AI вернул пустой ответ.'}),502 

                # ── FUNC ИШLE (function calling) — выполнение [FUNC:...] от AI ──────────
        import re as _re 
        func_calls_in_answer =_re .findall (r'\[FUNC:[^\]]+\]',answer )
        func_results_text =''

        # ── ВАЖНО: ПРИОРИТЕТ ID ─────────────────────────────────────────────
        # Сначала ищем ID в вопросе пользователя (это истина).
        # Только если в вопросе НЕТ ID — берём ID из ответа AI.
        # (AI может галлюцинировать ID из system prompt, например OWNER_ID)
        _question_id_m =_re .search (r'\b(\d{17,20})\b',question )
        _question_id =_question_id_m .group (1 )if _question_id_m else None 

        # Запоминаем, был ли запрос на search_user_messages (для анти-галлюцинации)
        asked_search_user_messages =any (
        'search_user_messages'in fc for fc in func_calls_in_answer 
        )
        # ID из [FUNC:...] маркера в ответе AI
        asked_user_id_m =_re .search (r'user_id=(\d+)',' '.join (func_calls_in_answer ))
        asked_user_id_from_ai =asked_user_id_m .group (1 )if asked_user_id_m else None 
        # ПРИОРИТЕТ: ID из вопроса > ID из ответа AI.
        # ДОПОЛНИТЕЛЬНО: если AI подставил OWNER_ID/BOT_ID/спец. ID —
        # это галлюцинация. Игнорируем если в вопросе НЕТ ID И есть имя
        # пользователя (mrxway, имя из @mention).
        _owner_id =str (os .getenv ('OWNER_ID',''))
        _bot_id_env =str (os .getenv ('BOT_ID',''))
        if asked_user_id_from_ai and asked_user_id_from_ai in (_owner_id ,_bot_id_env )and not _question_id :
        # AI подставил OWNER_ID — вероятно, галлюцинация.
        # Не используем этот ID; если есть @упоминание в вопросе — найдём ниже.
            asked_user_id_from_ai =None 
            # Если в вопросе есть @упоминание — попробуем найти его ID в guild
        if not _question_id and not asked_user_id_from_ai :
            _mention_m =_re .search (r'@([\w\.\-_]+)',question )
            if _mention_m and bot :
                _mention_name =_mention_m .group (1 ).lower ()
                try :
                    _gid_str3 =str (session .get ('selected_guild')or MAIN_GUILD_ID or '')
                    _guild3 =bot .get_guild (int (_gid_str3 ))if _gid_str3 .isdigit ()else None 
                    if _guild3 :
                        for _m in _guild3 .members :
                            if (_m .display_name .lower ()==_mention_name or 
                            _m .name .lower ()==_mention_name or 
                            _mention_name in _m .display_name .lower ()or 
                            _mention_name in _m .name .lower ()):
                                _question_id =str (_m .id )
                                break 
                except Exception as _ex:
                    _log.debug("api_ai_chat(): подавлено: %s", _ex)
        asked_user_id =_question_id or asked_user_id_from_ai 

        # ── ПРЕДИКТИВНЫЙ ВЫЗОВ: если AI НЕ вызвал [FUNC:search_user_messages] ──
        # но пользователь явно просит сообщения + в вопросе есть Discord ID
        # (17-20 цифр) — САМИ вызовем функцию ДО отдачи ответа AI.
        # Это ловит случай, когда LLM пропускает вызов функции и галлюцинирует.
        if not asked_search_user_messages and bot :
            try :
                _pred_id_m =_re .search (r'\b(\d{17,20})\b',question )
                _pred_keywords =['покажи сообщ','найди сообщ','выведи сообщ',
                'историю сообщ','последние сообщ','что писал',
                'где писал','искать сообщ','последние сообщения']
                if _pred_id_m and any (kw in question .lower ()for kw in _pred_keywords ):
                    asked_search_user_messages =True 
                    asked_user_id =_pred_id_m .group (1 )
                    # Сразу вызываем функцию синхронно
                    try :
                        from web .ai_functions import AIFunctions 
                        _gid_str2 =str (session .get ('selected_guild')or MAIN_GUILD_ID or '')
                        _guild2 =bot .get_guild (int (_gid_str2 ))if _gid_str2 .isdigit ()else None 
                        if _guild2 :
                            ai_fns2 =AIFunctions (bot )
                            _fc2 =f'[FUNC:search_user_messages(user_id={asked_user_id}, limit=20)]'
                            res2 =_run_async (ai_fns2 .execute_function (_fc2 ,_guild2 ),timeout =15 )
                            if res2 :
                                func_results_text =f"\n--- РЕЗУЛЬТАТ {_fc2} ---\n{res2}\n"
                                func_calls_in_answer .append (_fc2 )
                    except Exception as _pfe :
                        print (f"[AI-CHAT] predictive func exec error: {_pfe}")
            except Exception as _ex:
                _log.debug("api_ai_chat(): подавлено: %s", _ex)

        if func_calls_in_answer and bot :
            try :
                from web .ai_functions import AIFunctions 
                # Guild belli mi? MAIN_GUILD_ID veya session.selected_guild
                _gid_str =str (session .get ('selected_guild')or MAIN_GUILD_ID or '')
                _guild =bot .get_guild (int (_gid_str ))if _gid_str .isdigit ()else None 
                if _guild :
                    ai_fns =AIFunctions (bot )
                    for fc in func_calls_in_answer [:3 ]:# макс 3 функции
                        try :
                            res =_run_async (ai_fns .execute_function (fc ,_guild ),timeout =15 )
                            if res :
                                func_results_text +=f"\n--- РЕЗУЛЬТАТ {fc} ---\n{res}\n"
                        except Exception as _fce :
                        # Детальная диагностика — type + repr (на случай пустого str)
                            import traceback 
                            err_type =type (_fce ).__name__ 
                            err_repr =repr (_fce )
                            err_str =str (_fce )or "(пусто)"
                            tb_short ='\n'.join ([l for l in traceback .format_exc ().splitlines ()if l .strip ()][-3 :])
                            print (f"[AI-CHAT] func exec error ({fc}): {err_type}: {err_repr}")
                            print (f"[AI-CHAT] Traceback: {tb_short}")
                            # Сохраняем в func_results_text с type + repr
                            func_results_text +=(
                            f"\n--- РЕЗУЛЬТАТ {fc} ---\n"
                            "⚠️ Ошибка в функции поиска\n\n"
                            f"**Тип:** `{err_type}`\n"
                            f"**repr:** `{err_repr}`\n"
                            f"**str:** {err_str[:200]}\n\n"
                            f"Traceback (последние 3 строки):\n```\n{tb_short}\n```\n"
                            )
            except Exception as _fce_outer :
                print (f"[AI-CHAT] function calling setup error: {_fce_outer}")

                # Если были вызваны функции — решаем, переспрашивать ли LLM.
                # АНТИГАЛЛЮЦИНАЦИЯ: если результат содержит «не найдено» / «не найдены»
                # / «Нет» / «0 записей» — НЕ вызываем LLM повторно, иначе он начнёт
                # выдумывать детали. Просто отдаём реальный результат as-is.
        if asked_search_user_messages and not func_results_text :
        # Функция search_user_messages была запрошена, но НЕ выполнилась
        # (бот offline, guild не найден, или ошибка). НЕ даём AI галлюцинировать —
        # отдаём честный ответ с диагностикой.
            _tgt_str =f"<@{asked_user_id}>"if asked_user_id else "указанного пользователя"
            # Проверим наличие лог-файла (даже если функция не выполнилась)
            _log_status ="не найден (бот ещё не записал сообщений)"
            try :
                _gid_check =str (session .get ('selected_guild')or MAIN_GUILD_ID or '0')
                _log_path =f'data/message_log_{_gid_check}.json'
                if os .path .exists (_log_path ):
                    _log_status ="существует, но функция поиска сейчас недоступна (бот offline?)"
            except Exception as _ex:
                _log.debug("api_ai_chat(): подавлено: %s", _ex)
            answer =_re .sub (r'\[FUNC:[^\]]+\]','',answer ).strip ()
            answer =(
            f"🔍 Поиск сообщений {_tgt_str}:\n\n"
            "В данный момент функция поиска сообщений через Discord API недоступна "
            "(бот возможно offline или нет связи с Discord).\n\n"
            f"**Статус лога:** {_log_status}\n\n"
            "**Что можно сделать:**\n"
            "• Если бот только что перезапускался — подождите 1-2 минуты и попробуйте снова.\n"
            "• Проверьте что бот онлайн и имеет права на чтение истории каналов.\n"
            "• Используйте Discord-команду `/history @пользователь` для просмотра модерационной истории.\n\n"
            "Я не буду выдумывать содержимое сообщений — лучше честно сказать, что поиск "
            "сейчас недоступен."
            )
        elif func_results_text :
        # Вырежем [FUNC:...] маркеры из ответа
            answer =_re .sub (r'\[FUNC:[^\]]+\]','',answer ).strip ()
            results_lower =func_results_text .lower ()
            is_negative =any (neg in results_lower for neg in [
            'не найден','нет','недоступен','0 записей','0 сообщений',
            'нет результат','пусто','ошибка:','не могу','найдено 0',
            'не найдено','не найдены','нет сообщений'
            ])

            if is_negative or asked_search_user_messages :
            # Для search_user_messages ВСЕГДА отдаём as-is, без перевызова LLM.
            # LLM при перефразировке реальных данных склонен к галлюцинациям
            # (путает кто писал, выдумывает детали). Антигаллюцинация: данные
            # уже отформатированы в search_user_messages — пользователь
            # получит их как есть, без искажений.
                _tuid_m =_re .search (r'user_id=(\d+)',' '.join (func_calls_in_answer ))
                _tuid_str =f"<@{_tuid_m.group(1)}>"if _tuid_m else "пользователь"
                # Если результат начинается с "Найдено N сообщений" — это уже
                # готовый отформатированный вывод. Отдаём как есть.
                # Если начинается с "Ошибка:" / "Сообщения не найдены" — оборачиваем
                # в диагностическую обёртку.
                clean_result =func_results_text .strip ()
                # Удалим "--- РЕЗУЛЬТАТ [FUNC:...] ---" обёртку (в любом месте текста)
                clean_result =_re .sub (r'\n?---\s*РЕЗУЛЬТАТ\s*\[FUNC:[^\]]+\]\s*---\s*\n?','\n',clean_result ).strip ()

                # Проверяем, является ли результат РЕАЛЬНОЙ ошибкой (начинается с "Ошибка:")
                # или "⚠️ Ошибка" (мой новый формат). Если да — это диагностика,
                # а не "не найдено", и должна показываться ОТДЕЛЬНО.
                is_real_error =(
                clean_result .startswith ('Ошибка:')or 
                clean_result .startswith ('⚠️ Ошибка')or 
                '⚠️ Ошибка в функции поиска'in clean_result 
                )
                is_empty_error =clean_result =='Ошибка:'or clean_result =='Ошибка: '

                if is_empty_error :
                # Пустая ошибка (e без текста) — даём детальный диагноз
                    answer =(
                    f"🔍 Поиск сообщений {_tuid_str}:\n\n"
                    "⚠️ **Функция поиска упала без описания ошибки.**\n\n"
                    "Возможные причины:\n"
                    "• Бот offline или перезапускается\n"
                    "• Бот не имеет прав на чтение истории каналов\n"
                    "• Внутренняя ошибка в `search_user_messages`\n\n"
                    "Проверьте:\n"
                    "• Статус бота в Discord (Online?)\n"
                    "• Логи бота — ищите строки `[AI-FUNC] search_user_messages CRASH`\n"
                    "• Права бота: VIEW_CHANNEL + READ_MESSAGE_HISTORY\n\n"
                    "— Я не буду выдумывать содержимое сообщений."
                    )
                elif is_real_error :
                # Реальная ошибка с описанием — покажем как есть + предупреждение
                    answer =(
                    f"🔍 Поиск сообщений {_tuid_str}:\n\n"
                    f"{clean_result}\n\n"
                    "— Это **диагностическое сообщение** от функции поиска, не результат. "
                    "Поиск сейчас не работает. Подробности в логах бота (`[AI-FUNC]`)."
                    )
                elif is_negative :
                # Реальный «пустой» результат («не найдены», «0 записей»)
                    answer =(
                    f"🔍 Поиск сообщений {_tuid_str}:\n\n"
                    f"{clean_result}\n\n"
                    "— Это реальные данные. Я не буду перефразировать или дополнять их, "
                    "чтобы не исказить информацию."
                    )
                else :
                # Положительный результат (например, "Найдено 3 сообщения...")
                # всё равно отдаём as-is, но в более дружелюбной обёртке
                    answer =(
                    f"🔍 Результат поиска сообщений {_tuid_str}:\n\n"
                    f"{clean_result}\n\n"
                    "— Данные из Discord API / лога бота. Если нужно искать в конкретном "
                    "канале — уточни имя (например, «покажи сообщения mrxway в #teyit-chat»)."
                    )
            else :
            # Для ДРУГИХ функций (не search_user_messages) — попросим LLM
            # красиво оформить (галлюцинации менее опасны).
                messages .append ({'role':'assistant','content':answer })
                messages .append ({
                'role':'system',
                'content':(
                "Система выполнила функции по твоему запросу. Вот РЕАЛЬНЫЕ результаты:\n"
                f"{func_results_text}\n"
                "ВАЖНО: сформулируй финальный ответ на русском языке, используя ТОЛЬКО эти "
                "реальные данные. НЕ выдумывай сообщения, имена, каналы или даты. "
                "НЕ придумывай имена владельцев, администраторов, несуществующие Discord-команды "
                "(например, /search НЕ существует в Discord). Если в результатах нет владельца — "
                "так и напиши 'владелец сервера'. Не используй markdown кодовые блоки (```)."
                )
                })
                messages .append ({
                'role':'user',
                'content':"Сформулируй финальный ответ на основе данных выше."
                })
                try :
                    final_answer ,model_name2 ,_ =_call (messages ,max_tokens =1024 ,model =_AI_PANEL_MODEL )
                    if final_answer :
                        answer =final_answer 
                except Exception as _fe2 :
                    print (f"[AI-CHAT] re-call after FUNC error: {_fe2}")
                    answer =(answer +"\n\n"+func_results_text ).strip ()if answer else func_results_text .strip ()
                    # На всякий случай вырежем оставшиеся маркеры
            answer =_re .sub (r'\[FUNC:[^\]]+\]','',answer ).strip ()

            # ── EYLEM ИШLE (только owner) ─────────────────────────────────────────
        action_result =None 
        action_match =_re .search (r'\[EYLEM:([^\]]+)\]',answer )
        if action_match and bot and user_role =='owner':
            parts =action_match .group (1 ).split (':')
            tip =parts [0 ]if parts else ''
            # убираем префиксы вида "channel_id=123" или "user_id=123"
            import re as _re3 
            clean_parts =[parts [0 ]]
            for p in parts [1 :]:
                clean_parts .append (_re3 .sub (r'^[a-z_]+=','',p ))
            parts =clean_parts 
            try :
                def do_action ():
                    guild =bot .get_guild (int (MAIN_GUILD_ID ))
                    if not guild :return '❌ Сервер не найден'
                    from config import clean_number
                    _owner_id = clean_number(os.getenv('OWNER_ID')) or 987430047889637426

                    def resolve_channel (val ):
                        """Вернуть объект канала по имени или по ID"""
                        val =val .lstrip ('#').strip ()
                        if val .isdigit ():
                            return guild .get_channel (int (val ))
                            # Isimle ara
                        return discord .utils .find (
                        lambda c :c .name .lower ()==val .lower ()or val .lower ()in c .name .lower (),
                        guild .text_channels 
                        )

                    def resolve_member (val ):
                        """Вернуть участника по ID или имени — поддержка частичного совпадения"""
                        if val .isdigit ():
                            return guild .get_member (int (val ))
                        val_lower =val .lower ()
                        # До tam eшleшme
                        exact =discord .utils .find (
                        lambda m :m .display_name .lower ()==val_lower or m .name .lower ()==val_lower ,
                        guild .members 
                        )
                        if exact :return exact 
                        # В конецra kыsmi eшleшme
                        return discord .utils .find (
                        lambda m :val_lower in m .display_name .lower ()or val_lower in m .name .lower (),
                        guild .members 
                        )

                    def resolve_role (val ):
                        """Вернуть роль по ID или имени"""
                        if val .isdigit ():
                            return guild .get_role (int (val ))
                        return discord .utils .find (
                        lambda r :r .name .lower ()==val .lower (),
                        guild .roles 
                        )
                    if tip =='KANAL_KILITLE'and len (parts )>1 :
                        ch =resolve_channel (parts [1 ])
                        if ch :
                            _run_async (ch .set_permissions (guild .default_role ,send_messages =False ))
                            return f'✅ #{ch.name} kilitlendi'
                    elif tip =='KANAL_AC'and len (parts )>1 :
                        ch =resolve_channel (parts [1 ])
                        if ch :
                            _run_async (ch .set_permissions (guild .default_role ,send_messages =None ))
                            return f'✅ #{ch.name} открыт'
                    elif tip =='BAN'and len (parts )>1 :
                        m =resolve_member (parts [1 ])
                        if m :
                            reason =':'.join (parts [2 :])or 'Panel AI'
                            _run_async (m .ban (reason =reason ))
                            return f'✅ {m.display_name} забанен'
                    elif tip =='KICK'and len (parts )>1 :
                        m =resolve_member (parts [1 ])
                        if m :
                            reason =':'.join (parts [2 :])or 'Panel AI'
                            _run_async (m .kick (reason =reason ))
                            return f'✅ {m.display_name} кикнут'
                    elif tip =='TIMEOUT'and len (parts )>2 :
                        m =resolve_member (parts [1 ])
                        if m and m .id !=_owner_id :
                            mins =int (parts [2 ])if parts [2 ].isdigit ()else 10 
                            until =_dt.datetime.now(_dt.timezone.utc)+_dt .timedelta (minutes =mins )
                            _run_async (m .timeout (until ))
                            return f'✅ {m.display_name} — мут на {mins} мин'
                    elif tip =='СООБЩЕНИЕ'and len (parts )>2 :
                        ch =resolve_channel (parts [1 ])
                        if ch :
                            msg_text =':'.join (parts [2 :])
                            if msg_text :
                                _run_async (ch .send (msg_text ))
                                return f'✅ Сообщение отправлено в канал #{ch.name}'
                            return '❌ Сообщение содержимое пусто'
                    elif tip =='KANAL_YAVAШ'and len (parts )>2 :
                        ch =resolve_channel (parts [1 ])
                        if ch :
                            secs =int (parts [2 ])if parts [2 ].isdigit ()else 5 
                            _run_async (ch .edit (slowmode_delay =secs ))
                            return f'✅ #{ch.name} медленный режим: {secs}с'
                    elif tip =='DM'and len (parts )>2 :
                        m =resolve_member (parts [1 ])
                        if m :
                            msg_text =':'.join (parts [2 :])
                            if msg_text :
                                try :
                                    _run_async (m .send (msg_text ))
                                    return f'✅ DM отправлено пользователю {m.display_name}'
                                except discord .Forbidden :
                                    return f'❌ ЛС у {m.display_name} закрыты'
                        return '❌ Участник не найден'
                    elif tip =='SESTEN_AT'and len (parts )>1 :
                        m =resolve_member (parts [1 ])
                        if m and m .voice :
                            _run_async (m .move_to (None ))
                            return f'✅ {m.display_name} kicked из голоса'
                        return '❌ Участник не в голосе или не найден'
                    elif tip =='SESE_TAS'and len (parts )>2 :
                        m =resolve_member (parts [1 ])
                        ch =discord .utils .find (lambda c :parts [2 ].lower ()in c .name .lower (),guild .voice_channels )
                        if m and ch :
                            _run_async (m .move_to (ch ))
                            return f'✅ {m.display_name} → перемещён в {ch.name}'
                        return '❌ Участник или канал не найден'
                    elif tip =='UST_SESE'and len (parts )>1 :
                    # Юst ses в канал move
                        m =resolve_member (parts [1 ])
                        steps =int (parts [2 ])if len (parts )>2 and parts [2 ].isdigit ()else 1 
                        move_back =parts [3 ].lower ()=='geri'if len (parts )>3 else False 
                        if not m or not m .voice :
                            return '❌ Участник не в голосе'
                        vcs =sorted (guild .voice_channels ,key =lambda c :c .position )
                        idx =next ((i for i ,c in enumerate (vcs )if c .id ==m .voice .channel .id ),None )
                        if idx is None :return '❌ Канал не найден'
                        original_ch =m .voice .channel 
                        target_idx =max (0 ,idx -steps )
                        target_ch =vcs [target_idx ]
                        _run_async (m .move_to (target_ch ))
                        if move_back :
                            import asyncio as _as2 
                            _run_async (_as2 .sleep (3 ))
                            fresh =guild .get_member (m .id )
                            if fresh and fresh .voice :
                                _run_async (fresh .move_to (original_ch ))
                            return f'✅ {m.display_name} → перемещён в {target_ch.name}, через 3с возвращён в {original_ch.name}'
                        return f'✅ {m.display_name} → перемещён в {target_ch.name}'
                    elif tip =='ALT_SESE'and len (parts )>1 :
                        m =resolve_member (parts [1 ])
                        steps =int (parts [2 ])if len (parts )>2 and parts [2 ].isdigit ()else 1 
                        move_back =parts [3 ].lower ()=='geri'if len (parts )>3 else False 
                        if not m or not m .voice :
                            return '❌ Участник не в голосе'
                        vcs =sorted (guild .voice_channels ,key =lambda c :c .position )
                        idx =next ((i for i ,c in enumerate (vcs )if c .id ==m .voice .channel .id ),None )
                        if idx is None :return '❌ Канал не найден'
                        original_ch =m .voice .channel 
                        target_idx =min (len (vcs )-1 ,idx +steps )
                        target_ch =vcs [target_idx ]
                        _run_async (m .move_to (target_ch ))
                        if move_back :
                            import asyncio as _as2 
                            _run_async (_as2 .sleep (3 ))
                            fresh =guild .get_member (m .id )
                            if fresh and fresh .voice :
                                _run_async (fresh .move_to (original_ch ))
                            return f'✅ {m.display_name} → перемещён в {target_ch.name}, через 3с возвращён в {original_ch.name}'
                        return f'✅ {m.display_name} → перемещён в {target_ch.name}'
                    elif tip =='SUSTUR'and len (parts )>1 :
                        m =resolve_member (parts [1 ])
                        if m :
                            if not m .voice :
                                return f'❌ {m.display_name} сейчас не в голосовом канале, нельзя заглушить'
                            _run_async (m .edit (mute =True ))
                            return f'✅ {m.display_name} заглушен'
                        return '❌ Участник не найден'
                    elif tip =='SUSTUR_KALDIR'and len (parts )>1 :
                        m =resolve_member (parts [1 ])
                        if m :
                            if not m .voice :
                                return f'❌ {m.display_name} сейчас не в голосовом канале'
                            _run_async (m .edit (mute =False ))
                            return f'✅ с {m.display_name} снято заглушение'
                        return '❌ Участник не найден'
                    elif tip =='KULAKLIK_KAPAT'and len (parts )>1 :
                        m =resolve_member (parts [1 ])
                        if m :
                            _run_async (m .edit (deafen =True ))
                            return f'✅ {m.display_name} — звук отключён (deafen)'
                    elif tip =='KULAKLIK_AC'and len (parts )>1 :
                        m =resolve_member (parts [1 ])
                        if m :
                            _run_async (m .edit (deafen =False ))
                            return f'✅ {m.display_name} — звук включён'
                    elif tip =='TIMEOUT_KALDIR'and len (parts )>1 :
                        m =resolve_member (parts [1 ])
                        if m :
                            _run_async (m .timeout (None ))
                            return f'✅ {m.display_name} timeout удалено'
                    elif tip =='UNBAN'and len (parts )>1 :
                        try :
                            u =_run_async (bot .fetch_user (int (parts [1 ])))
                            _run_async (guild .unban (u ))
                            return f'✅ {u.name} unban edildi'
                        except Exception:return '❌ Пользователь не найден'
                    elif tip =='ПРЕДУПРЕЖДЕНИЕ'and len (parts )>1 :
                        m =resolve_member (parts [1 ])
                        if m :
                            import json as _j2 
                            wf ='data/warnings.json'
                            wd =_j2 .load (open (wf ,encoding ='utf-8'))if os .path .exists (wf )else {}
                            gid =str (guild .id )
                            uid =str (m .id )
                            wd .setdefault (gid ,{}).setdefault (uid ,[])
                            reason =':'.join (parts [2 :])or 'Panel AI'
                            import datetime as _dt2 
                            wd [gid ][uid ].append ({'reason':reason ,'mod':'Arthur','timestamp':_dt2 .datetime.now(timezone.utc).isoformat ()})
                            with open (wf ,'w',encoding ='utf-8')as fp :_j2 .dump (wd ,fp ,ensure_ascii =False ,indent =2 )
                            return f'✅ {m.display_name} предупреждение: {reason}'
                    elif tip =='UYARI_TEMIZLE'and len (parts )>1 :
                        m =resolve_member (parts [1 ])
                        if m :
                            import json as _j2 
                            wf ='data/warnings.json'
                            wd =_j2 .load (open (wf ,encoding ='utf-8'))if os .path .exists (wf )else {}
                            wd .setdefault (str (guild .id ),{})[str (m .id )]=[]
                            with open (wf ,'w',encoding ='utf-8')as fp :_j2 .dump (wd ,fp ,ensure_ascii =False ,indent =2 )
                            return f'✅ {m.display_name} предупреждения clearndi'
                    elif tip =='MESAJ_SIL'and len (parts )>1 :
                        ch =resolve_channel (parts [1 ])
                        number =int (parts [2 ])if len (parts )>2 and parts [2 ].isdigit ()else 10 
                        if ch :
                            deleted =_run_async (ch .purge (limit =number ))
                            return f'✅ #{ch.name} из канала {len(deleted)} message удалено'
                    elif tip =='KANAL_OLUSTUR'and len (parts )>1 :
                        channel_name ='-'.join (parts [1 :]).lower ().replace (' ','-')
                        ch =_run_async (guild .create_text_channel (channel_name ))
                        return f'✅ Канал #{ch.name} создан'
                    elif tip =='SES_KANAL_OLUSTUR'and len (parts )>1 :
                        channel_name =' '.join (parts [1 :])
                        ch =_run_async (guild .create_voice_channel (channel_name ))
                        return f'✅ 🔊 Голосовой канал {ch.name} создан'
                    elif tip =='ROL_OLUSTUR'and len (parts )>1 :
                        channel_name =' '.join (parts [1 :])
                        r =_run_async (guild .create_role (name =channel_name ))
                        return f'✅ Роль @{r.name} создана'
                    elif tip =='DUYURU'and len (parts )>2 :
                        ch =resolve_channel (parts [1 ])
                        msg_text =':'.join (parts [2 :])
                        if ch and msg_text :
                            _run_async (ch .send (f'📢 **ОБЪЯВЛЕНИЕ**\n\n{msg_text}'))
                            return f'✅ Объявление отправлено в канал #{ch.name}'
                    elif tip =='ROL_VER'and len (parts )>2 :
                        m =resolve_member (parts [1 ])
                        r =resolve_role (parts [2 ])
                        if m and r :
                            _run_async (m .add_roles (r ))
                            return f'✅ {m.display_name} → {r.name} роль verildi'
                    elif tip =='ROL_AL'and len (parts )>2 :
                        m =resolve_member (parts [1 ])
                        r =resolve_role (parts [2 ])
                        if m and r :
                            _run_async (m .remove_roles (r ))
                            return f'✅ у {m.display_name} снята роль {r.name}'
                    elif tip =='NICK'and len (parts )>2 :
                        m =resolve_member (parts [1 ])
                        if m :
                            new_nick =':'.join (parts [2 :])
                            _run_async (m .edit (nick =new_nick ))
                            return f'✅ Ник изменён: {m.name} → {new_nick}'
                    return '⚠️ Действие не завершено — канал/участник не найден'
                    # do_action() — синхронная функция, вызываем напрямую (не coroutine)
                action_result =do_action ()
            except Exception as ae :
                action_result =f'❌ Ошибка действия: {ae}'

                # Убрать тег действия из ответа
            answer =_re .sub (r'\[EYLEM:[^\]]+\]','',answer ).strip ()
            if action_result :
                answer =f"{answer}\n\n`{action_result}`"if answer else f"`{action_result}`"

        new_history =history +[
        {'role':'user','content':question [:500 ]},
        {'role':'assistant','content':answer [:500 ]}
        ]
        # Son 12 сообщение (6 user+assistant чifti) — cookie 4KB sыnыrы iчin
        session [history_key ]=new_history [-12 :]
        session .modified =True 
        return jsonify ({'answer':answer ,'model':model_name })


    @app .route ('/api/ai-chat/clear',methods =['POST'])
    @login_required 
    @role_required ('uye')
    def api_ai_chat_clear ():
        """AI sohbet историю clear"""
        history_key =f'ai_history_{session.get("username", "anon")}'
        session .pop (history_key ,None )
        session .modified =True 
        return jsonify ({'ok':True })
