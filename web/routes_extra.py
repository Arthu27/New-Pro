"""Extra panel routes - pages"""
from flask import render_template ,session ,redirect ,url_for ,request ,jsonify ,Response 
import os ,json 
import time 
import math 
import discord 
from datetime import datetime, timezone


def _load_ai_tickets (guild_id :int )->dict :
    """Загрузить данные AI-тикетов"""
    path =f"data/ai_tickets_{guild_id}.json"
    if os .path .exists (path ):
        try :
            with open (path ,'r',encoding ='utf-8')as f :
                return json .load (f )
        except Exception:
            pass 
    return {}


async def _fetch_channel_msgs_async (bot ,channel_mentions ):
    """Async helper to fetch recent messages from a channel, given a bot instance and optional mentions filter."""
    lines =[]
    for g in bot .guilds :
        for ch in g .text_channels :
        # Канал имя soruda geчiyor mu?
            if channel_mentions and not any (m .lower ()in ch .name .lower ()for m in channel_mentions ):
                continue 
            if not channel_mentions :
                break # Общий soru — только ilk канал al
            try :
                msgs =[m async for m in ch .history (limit =10 )]
                for m in reversed (msgs ):
                    lines .append (f"  [{ch.name}] {m.author.display_name}: {m.content[:100]}")
            except Exception :
                pass 
    return lines 


def _fetch_channel_msgs_sync (bot ,channel_mentions ):
    """Sync wrapper around the async channel-history helper. Use this from sync Flask handlers."""
    import asyncio as _asyncio3 
    return _asyncio3 .run (_fetch_channel_msgs_async (bot ,channel_mentions ))


def _run_async (coro ,timeout =10 ):
    """Run an async coroutine from sync code, return result or raise."""
    import asyncio as _aio
    import web .app as _app
    bot =_app .bot_instance
    if not bot or not getattr (bot ,'loop',None ):
        raise RuntimeError ('Бот не работает')
    future =_aio .run_coroutine_threadsafe (coro ,bot .loop )
    return future .result (timeout =timeout )


def _notify_discord_sender (channel_id ,title ,body ):
    """Отправить уведомление в Discord-канал через бота (для диспетчера уведомлений)."""
    try :
        import asyncio as _aio
        import web .app as _app
        bot =_app .bot_instance
        if not bot or not getattr (bot ,'loop',None ):
            return False
        channel =bot .get_channel (int (channel_id ))
        if not channel :
            return False
        import discord as _discord
        embed =_discord .Embed (title =title ,description =(body or '')[:4000 ],color =0xC8922A )
        _aio .run_coroutine_threadsafe (channel .send (embed =embed ),bot .loop ).result (timeout =10 )
        return True
    except Exception :
        return False


def _fire_panel_notification (event ,title ,body ):
    """Вызвать диспетчер уведомлений, не прерывая основной обработчик."""
    try :
        from services .notification_dispatcher import notify_event
        return notify_event (event ,title ,body ,discord_sender =_notify_discord_sender )
    except Exception :
        return {}


def _process_action (answer :str ,bot ,guild_id :str ,session_obj )->str :
    """Обрабатывает блок <action> из ответа AI и возвращает текст результата."""
    import re as _re ,asyncio as _asyncio ,os as _os 
    from datetime import datetime as _dt ,timedelta as _td 

    action_match =_re .search (r'<action>(.*?)</action>',answer ,_re .DOTALL )
    if not action_match :
        return ''
    try :
        raw =action_match .group (1 ).strip ()
        # Bozuk JSON'u clear
        raw =_re .sub (r'[\x00-\x1f]',' ',raw )# контроль karakterleri
        action_data =json .loads (raw )
    except Exception :
    # JSON parse неудачно — action'ы игнорировать
        return ''

    action_type =action_data .get ('action','').lower ()
    _aliases ={
    'dm_message':'dm','send_dm':'dm','direct_message':'dm',
    'chat_message':'send_message','channel_message':'send_message',
    'send_channel_message':'send_message','warning':'warn','mute':'timeout',
    }
    action_type =_aliases .get (action_type ,action_type )
    uid =str (action_data .get ('user_id',''))
    guild =bot .get_guild (int (guild_id ))if bot else None 

    try :
        if action_type =='warn':
            reason =action_data .get ('reason','AI asistan warn')
            if not uid :
                return '❌ Пользователь ID не найден'
                # AI asistan никогда автоматически warn не может отправить — только predlojenie предлагает
            return f'⚠️ AI предлагает warn: выдать {uid} предупреждение за «{reason}». Подтвердите командой /moderate.'

        elif action_type =='ban':
            reason =action_data .get ('reason','AI ban')
            if not (guild and uid ):
                return '❌ Отсутствует параметр'
            member =guild .get_member (int (uid ))
            if not member :
                return '❌ Участник на сервере не найден'
                # AI ban предложение — автоматически примен
            return f'⚠️ AI ban предложение: {member.display_name} ({uid}) — Причина: "{reason}". Подтвердите командой /moderate ban.'
            return f'✅ Ban применено (user_id: {uid})'

        elif action_type =='kick':
            reason =action_data .get ('reason','AI kick')
            if not (guild and uid ):
                return '❌ Отсутствует параметр'
            member =guild .get_member (int (uid ))
            if not member :
                return '❌ Участник на сервере не найден'
                # AI kick предложение — автоматически примен
            return f'⚠️ AI kick предложение: {member.display_name} ({uid}) — Причина: "{action_data.get("reason", "AI kick")}". Подтвердите командой /moderate kick.'

        elif action_type =='dm':
            message =action_data .get ('message','')
            if not (bot and uid and message ):
                return '❌ Пользователь ID или сообщение отсутствует'
            def _send_dm ():
                user =_run_async (bot .fetch_user (int (uid )))
                _run_async (user .send (message ))
            _asyncio .run_coroutine_threadsafe (_send_dm (),bot .loop ).result (timeout =10 )
            return f'✅ DM отправлено (user_id: {uid})'

        elif action_type =='timeout':
            minutes =int (action_data .get ('minutes',10 ))
            reason =action_data .get ('reason','AI timeout')
            if not (guild and uid ):
                return '❌ Отсутствует параметр'
            member =guild .get_member (int (uid ))
            if not member :
                return '❌ Участник на сервере не найден'
                # AI timeout предложение — автоматически примен
            return f'⚠️ AI timeout предложение: {member.display_name} ({uid}) — {minutes} мин, причина: "{reason}". Подтвердите командой /moderate timeout.'

        elif action_type =='add_role':
            role_id =str (action_data .get ('role_id',''))
            if not (guild and uid and role_id ):
                return '❌ Отсутствует параметр'
            member =guild .get_member (int (uid ))
            role =guild .get_role (int (role_id ))
            if not (member and role ):
                return '❌ Участник или роль не найдены'
            _asyncio .run_coroutine_threadsafe (member .add_roles (role ),bot .loop ).result (timeout =10 )
            return f'✅ Роль выдана: {role.name}'

        elif action_type =='remove_role':
            role_id =str (action_data .get ('role_id',''))
            if not (guild and uid and role_id ):
                return '❌ Отсутствует параметр'
            member =guild .get_member (int (uid ))
            role =guild .get_role (int (role_id ))
            if not (member and role ):
                return '❌ Участник или роль не найдены'
            _asyncio .run_coroutine_threadsafe (member .remove_roles (role ),bot .loop ).result (timeout =10 )
            return f'✅ Роль снята: {role.name}'

        elif action_type =='send_message':
            channel_id =str (action_data .get ('channel_id',''))
            message =action_data .get ('message','')
            if not (bot and channel_id and message ):
                return '❌ ID канала или сообщение отсутствует'
            channel =bot .get_channel (int (channel_id ))
            if not channel :
                return '❌ Канал не найден'
            _asyncio .run_coroutine_threadsafe (channel .send (message ),bot .loop ).result (timeout =10 )
            return f'✅ Сообщение отправлено → #{channel.name}'

        elif action_type =='delete_message':
            channel_id =str (action_data .get ('channel_id',''))
            message_id =str (action_data .get ('message_id',''))
            if not (bot and channel_id and message_id ):
                return '❌ ID канала или ID сообщения отсутствует'
            def _del_msg ():
                ch =bot .get_channel (int (channel_id ))
                if not ch :
                    return '❌ Канал не найден'
                msg =_run_async (ch .fetch_message (int (message_id )))
                _run_async (msg .delete ())
                return '✅ Сообщение удалено'
            return _asyncio .run_coroutine_threadsafe (_del_msg (),bot .loop ).result (timeout =10 )

        elif action_type =='send_embed':
            channel_id =str (action_data .get ('channel_id',''))
            title =action_data .get ('title','')
            description =action_data .get ('description','')
            color =int (action_data .get ('color',0xc8922a ))
            if not (bot and channel_id ):
                return '❌ Не указан ID канала'
            channel =bot .get_channel (int (channel_id ))
            if not channel :
                return '❌ Канал не найден'
            import discord as _discord 
            embed =_discord .Embed (title =title ,description =description ,color =color )
            _asyncio .run_coroutine_threadsafe (channel .send (embed =embed ),bot .loop ).result (timeout =10 )
            return f'✅ Embed отправлено → #{channel.name}'

        elif action_type =='bulk_dm':
            message =action_data .get ('message','')
            role_id =str (action_data .get ('role_id',''))
            if not (bot and guild and message ):
                return '❌ Отсутствует параметр'
            members =guild .members if not role_id else [
            m for m in guild .members if any (str (r .id )==role_id for r in m .roles )
            ]
            def _bulk ():
                count =0 
                for m in members :
                    if not m .bot :
                        try :
                            _run_async (m .send (message ))
                            count +=1 
                        except Exception :
                            pass 
                return count 
            count =_asyncio .run_coroutine_threadsafe (_bulk (),bot .loop ).result (timeout =60 )
            return f'✅ {count} пользователям DM отправлено'

        elif action_type =='create_channel':
            name =action_data .get ('name','новый-channel')
            category_id =action_data .get ('category_id')
            if not (bot and guild ):
                return '❌ Сервер не найден'
            def _create_ch ():
                cat =guild .get_channel (int (category_id ))if category_id else None 
                return _run_async (guild .create_text_channel (name ,category =cat ))
            ch =_asyncio .run_coroutine_threadsafe (_create_ch (),bot .loop ).result (timeout =10 )
            return f'✅ Канал создан: #{ch.name} (ID: {ch.id})'

        elif action_type =='delete_channel':
            channel_id =str (action_data .get ('channel_id',''))
            if not (bot and channel_id ):
                return '❌ Не указан ID канала'
            channel =bot .get_channel (int (channel_id ))
            if not channel :
                return '❌ Канал не найден'
            _asyncio .run_coroutine_threadsafe (channel .delete (),bot .loop ).result (timeout =10 )
            return f'✅ Канал удалено: #{channel.name}'

        elif action_type =='create_role':
            name =action_data .get ('name','новый-роли')
            color_hex =action_data .get ('color','000000').lstrip ('#')
            import discord as _discord 
            color_obj =_discord .Color (int (color_hex ,16 ))if color_hex else _discord .Color .default ()
            if not (bot and guild ):
                return '❌ Сервер не найден'
            role =_asyncio .run_coroutine_threadsafe (
            guild .create_role (name =name ,color =color_obj ),bot .loop 
            ).result (timeout =10 )
            return f'✅ Роль создана: {role.name} (ID: {role.id})'

        elif action_type =='delete_role':
            role_id =str (action_data .get ('role_id',''))
            if not (guild and role_id ):
                return '❌ Роли ID eksik'
            role =guild .get_role (int (role_id ))
            if not role :
                return '❌ Роль не найдена'
            _asyncio .run_coroutine_threadsafe (role .delete (),bot .loop ).result (timeout =10 )
            return f'✅ Роли удалено: {role.name}'

        elif action_type =='nick':
            nick =action_data .get ('nick','')
            if not (guild and uid ):
                return '❌ Отсутствует параметр'
            member =guild .get_member (int (uid ))
            if not member :
                return '❌ Участник не найден'
            _asyncio .run_coroutine_threadsafe (member .edit (nick =nick or None ),bot .loop ).result (timeout =10 )
            return f'✅ Nickname изменено → {nick or "(сброшен)"}'

        elif action_type =='unban':
            if not (guild and uid ):
                return '❌ Отсутствует параметр'
            def _unban ():
                user =_run_async (bot .fetch_user (int (uid )))
                _run_async (guild .unban (user ))
            _asyncio .run_coroutine_threadsafe (_unban (),bot .loop ).result (timeout =10 )
            return f'✅ Ban удалено (user_id: {uid})'

        elif action_type =='user_info':
            if not (guild and uid ):
                return '❌ Пользователь ID отсутствует'
            member =guild .get_member (int (uid ))
            if not member :
                return f'❌ Участник на сервере не найден (ID: {uid})'
            roles =[r .name for r in member .roles if r .name !='@everyone']
            warns_file ='data/warnings.json'
            warn_count =0 
            if os .path .exists (warns_file ):
                try :
                    w =json .load (open (warns_file ,encoding ='utf-8'))
                    warn_count =len (w .get (str (guild_id ),{}).get (uid ,[]))
                except Exception :
                    pass 
            return (f'👤 {member.display_name} ({member.name})\n'
            f'📅 Вход: {member.joined_at.strftime("%d.%m.%Y") if member.joined_at else "?"}\n'
            f'⚠️ Warning: {warn_count}\n'
            f'🎭 Роли: {", ".join(roles) or "нет"}')

        return f'⚠️ Неизвестное действие: {action_type}'
    except Exception as e :
        return f'⚠️ Ошибка действия: {e}'


import re as _ms_re


# ═══════════════════════════════════════════════════════════════════════════
# Поиск участников: нормализация запроса, релевантный скоринг, безопасные
# нормализаторы записей. Чистые функции — покрыты тестами (tests/test_member_search).
# ═══════════════════════════════════════════════════════════════════════════

def ms_normalize_query(raw) -> str:
    """Почистить поисковый запрос: пробелы, регистр, '@', упоминание <@123>."""
    q = (raw or '')
    if not isinstance(q, str):
        q = str(q)
    q = q.strip().lower()
    if len(q) > 64:
        q = q[:64]
    m = _ms_re.fullmatch(r'<@!?(\d+)>', q)
    if m:
        return m.group(1)
    if q.startswith('@'):
        q = q[1:]
    return q.strip()


def ms_member_match(q: str, member) -> int:
    """Очки совпадения запроса с участником (0 = не подходит).

    Точный ID/имя — высший балл, начало имени — средний, вхождение — базовый.
    Чисто цифровой запрос ищет и по началу ID (можно ввести часть ID).
    """
    if not q:
        return 0
    try:
        uid = str(member.id)
    except Exception:
        return 0
    if q == uid:
        return 500
    if q.isdigit() and uid.startswith(q):
        return 200
    best = 0
    for n in (
        getattr(member, 'display_name', None),
        getattr(member, 'name', None),
        getattr(member, 'global_name', None),
        getattr(member, 'nick', None),
    ):
        if not n:
            continue
        n = str(n).strip().lower()
        if not n:
            continue
        if n == q:
            best = max(best, 400)
        elif n.startswith(q):
            best = max(best, 150)
        elif q in n:
            best = max(best, 100)
    return best


def ms_search_members(members, query, limit=25):
    """Найти участников по запросу; результат отсортирован по релевантности."""
    q = ms_normalize_query(query)
    if not q:
        return []
    try:
        limit = max(1, min(50, int(limit)))
    except (TypeError, ValueError):
        limit = 25
    scored = []
    for m in members or []:
        s = ms_member_match(q, m)
        if s > 0:
            scored.append((s, str(getattr(m, 'display_name', '') or '').lower(), m))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [m for _, _, m in scored[:limit]]


def ms_member_payload(m) -> dict:
    """Карточка участника для API: безопасно вытаскивает поля."""
    try:
        avatar = str(m.display_avatar.url) if getattr(m, 'display_avatar', None) else None
    except Exception:
        avatar = None
    return {
        'id': str(m.id),
        'name': str(getattr(m, 'name', '') or ''),
        'display_name': str(getattr(m, 'display_name', '') or getattr(m, 'name', '') or str(m.id)),
        'nickname': getattr(m, 'nick', None),
        'avatar': avatar,
        'status': str(getattr(m, 'status', 'offline') or 'offline'),
        'is_bot': bool(getattr(m, 'bot', False)),
    }


def ms_normalize_warn(w, idx: int) -> dict:
    """Привести запись предупреждения к единому виду для панели."""
    if not isinstance(w, dict):
        return {'id': idx, 'reason': str(w) or '—', 'mod': '', 'timestamp': ''}
    return {
        'id': w.get('id', idx),
        'reason': str(w.get('reason') or '—'),
        'mod': str(w.get('mod') or w.get('moderator') or w.get('mod_id') or ''),
        'timestamp': str(w.get('timestamp') or w.get('date') or ''),
    }


def ms_normalize_case(c, idx: int) -> dict:
    """Привести запись модерационной истории к единому виду для панели."""
    if not isinstance(c, dict):
        return {'id': idx, 'action': '?', 'reason': str(c) or '—', 'mod': '', 'timestamp': ''}
    return {
        'id': c.get('id', idx),
        'action': str(c.get('action') or c.get('type') or '?'),
        'reason': str(c.get('reason') or '—'),
        'mod': str(c.get('mod_name') or c.get('mod') or c.get('mod_id') or ''),
        'timestamp': str(c.get('timestamp') or ''),
    }


def register_extra_routes (app ,ROLES ,login_required ,role_required ,MAIN_GUILD_ID ='1384282749317152878'):

    def active_guild_id ():
        """Return a live guild ID, never a stale value left in .env."""
        import web .app as _app 
        bot =_app .bot_instance 
        guilds =getattr (bot ,'guilds',None )if bot else None 
        configured =str (MAIN_GUILD_ID or '')
        if guilds :
            if any (str (g .id )==configured for g in guilds ):
                return configured 
            return str (guilds [0 ].id )
        return configured 

    def _resolve_member_async (guild ,user_id ):
        """Async helper: get cached member or fetch from API."""
        member =guild .get_member (int (user_id ))
        if member :
            return member 
        try :
            return _run_async (guild .fetch_member (int (user_id )))
        except Exception :
            return None 

            # ── PAGE ROUTES ──────────────────────────────────────────────────────────

    @app .route ('/ai_ticket_stats')
    @login_required 
    @role_required ('mod')
    def ai_ticket_stats ():
        """AI ticket статистика страница"""
        guild_id =session .get ('selected_guild')
        if not guild_id :
            return redirect (url_for ('guilds_page'))

        stats =calculate_ai_ticket_stats (int (guild_id ))

        return render_template (
        'ai_ticket_stats.html',
        role =session .get ('role'),
        username =session .get ('username'),
        stats =stats 
        )

    @app .route ('/bot-stats')
    @login_required 
    @role_required ('mod')
    def bot_stats_page ():
        return render_template ('bot_stats.html',role =session .get ('role'),username =session .get ('username'))

    @app .route ('/analytics')
    @login_required 
    @role_required ('mod')
    def analytics_page ():
        return render_template ('analytics.html',role =session .get ('role'),username =session .get ('username'),main_guild_id =MAIN_GUILD_ID )

    @app .route ('/server-health')
    @login_required 
    @role_required ('mod')
    def sunucu_health_page ():
        return render_template ('server_health.html',role =session .get ('role'),username =session .get ('username'))

    # ── ANTI-CRASH merkezi ──────────────────────────────────────────────
    def _anticrash_handler():
        import web.app as _app
        bot = _app.bot_instance
        return getattr(bot, 'error_handler', None) if bot else None

    @app.route('/anticrash')
    @login_required
    @role_required('admin')
    def anticrash_page():
        return render_template('anticrash.html', role=session.get('role'), username=session.get('username'))

    @app.route('/api/anticrash/overview')
    @login_required
    @role_required('admin')
    def api_anticrash_overview():
        eh = _anticrash_handler()
        if not eh:
            return jsonify({'ok': False, 'error': 'Обработчик офлайн (бот не запущен)'})
        return jsonify(eh.get_overview())

    @app.route('/api/anticrash/config', methods=['GET', 'POST'])
    @login_required
    @role_required('admin')
    def api_anticrash_config():
        from error_handler import CONFIG_META, DEFAULT_CONFIG
        eh = _anticrash_handler()
        if not eh:
            return jsonify({'ok': False, 'error': 'Обработчик офлайн'}), 503
        if request.method == 'GET':
            return jsonify({
                'ok': True,
                'config': eh.config,
                'order': list(DEFAULT_CONFIG.keys()),
                'meta': {k: {'label': v[0], 'desc': v[1], 'type': v[2]} for k, v in CONFIG_META.items()},
            })
        data = request.get_json(silent=True) or {}
        updated, errors = {}, {}
        for k, v in data.items():
            try:
                updated[k] = eh.update_config(k, v)
            except KeyError:
                errors[k] = 'неизвестный ключ'
            except (ValueError, TypeError) as e:
                errors[k] = str(e)
        if errors:
            return jsonify({'ok': False, 'updated': updated, 'errors': errors}), 400
        return jsonify({'ok': True, 'config': eh.config})

    @app.route('/api/anticrash/reset', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_anticrash_reset():
        eh = _anticrash_handler()
        if not eh:
            return jsonify({'ok': False, 'error': 'Обработчик офлайн'}), 503
        eh.reset_stats()
        return jsonify({'ok': True})

    # ── АВТОФИЛЬТР чата ───────────────────────────────────────────
    def _autofilter_gid() -> str:
        """MAIN_GUILD_ID, иначе первый сервер бота (как в остальных API)."""
        if MAIN_GUILD_ID:
            return str(MAIN_GUILD_ID)
        import web.app as _app
        bot = _app.bot_instance
        try:
            guilds = getattr(bot, 'guilds', None) or []
            return str(guilds[0].id) if guilds else ''
        except Exception:
            return ''

    @app.route('/autofilter')
    @login_required
    @role_required('mod')
    def autofilter_page():
        return render_template('autofilter.html', role=session.get('role'),
                               username=session.get('username'))

    @app.route('/api/autofilter')
    @login_required
    @role_required('mod')
    def api_autofilter_get():
        from cogs.auto_filter import load_config
        gid = _autofilter_gid()
        if not gid:
            return jsonify({'ok': False, 'error': 'Сервер не выбран (MAIN_GUILD_ID / бот офлайн)'}), 503
        return jsonify({'ok': True, 'guild_id': gid, 'config': load_config(gid)})

    @app.route('/api/autofilter/save', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_autofilter_save():
        from cogs.auto_filter import validate_config, save_config
        gid = _autofilter_gid()
        if not gid:
            return jsonify({'ok': False, 'error': 'Сервер не выбран'}), 503
        data = request.get_json(silent=True) or {}
        cfg, errors = validate_config(data)
        if errors:
            return jsonify({'ok': False, 'errors': errors}), 400
        save_config(gid, cfg)
        return jsonify({'ok': True, 'config': cfg})

    @app.route('/api/autofilter/test', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_autofilter_test():
        from cogs.auto_filter import load_config, classify_message
        gid = _autofilter_gid()
        if not gid:
            return jsonify({'ok': False, 'error': 'Сервер не выбран'}), 503
        data = request.get_json(silent=True) or {}
        text = str(data.get('text') or '')[:500]
        return jsonify({'ok': True,
                        'violations': classify_message(load_config(gid), text)})

    # ── Публичная статус-страница (без логина) ───────────────────────────
    @app.route('/status')
    def status_public_page():
        return render_template('status_public.html')

    @app.route('/api/status-public')
    def api_status_public():
        import web.app as _app
        bot = _app.bot_instance
        online = False
        latency_ms = 0
        guilds = 0
        users_cached = 0
        uptime_sec = 0
        if bot is not None:
            try:
                online = not bot.is_closed()
            except Exception:
                online = False
            try:
                lat = getattr(bot, 'latency', None)
                if lat is not None and math.isfinite(lat):
                    latency_ms = max(0, round(lat * 1000))
            except Exception:
                latency_ms = 0
            try:
                guilds = len(getattr(bot, 'guilds', []) or [])
            except Exception:
                guilds = 0
            try:
                users_cached = len(getattr(bot, 'users', []) or [])
            except Exception:
                users_cached = 0
            eh = getattr(bot, 'error_handler', None)
            if eh is not None:
                try:
                    uptime_sec = max(0, int(time.time() - eh.stats.get('started_at', time.time())))
                except Exception:
                    uptime_sec = 0
        h, m, s_ = uptime_sec // 3600, (uptime_sec % 3600) // 60, uptime_sec % 60
        days = uptime_sec // 86400
        if days:
            uptime_human = f'{days}д {h % 24}ч {m}м'
        else:
            uptime_human = f'{h}ч {m}м {s_}с'
        return jsonify({
            'ok': True,
            'online': online,
            'latency_ms': latency_ms,
            'guilds': guilds,
            'users_cached': users_cached,
            'uptime_sec': uptime_sec,
            'uptime_human': uptime_human,
            'version': '2.0',
            'updated': datetime.now(timezone.utc).isoformat(),
        })

    # ── Живая консоль логов ──────────────────────────────────────────────
    @app.route('/konsol')
    @login_required
    @role_required('admin')
    def konsol_page():
        return render_template('konsol.html', role=session.get('role'), username=session.get('username'))

    @app.route('/api/live-logs')
    @login_required
    @role_required('admin')
    def api_live_logs():
        try:
            from logger import get_live_logs
            after = request.args.get('after', 0, type=int) or 0
            items = get_live_logs(after_id=after, limit=250)
            last_id = items[-1]['id'] if items else after
            return jsonify({'ok': True, 'items': items, 'last_id': last_id})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500

    # ── TAG JAIL paneli ──────────────────────────────────────────────
    def _tagjail_ctx():
        import web.app as _app
        bot = _app.bot_instance
        cog = bot.get_cog('TagJail') if bot else None
        guild = None
        if bot and getattr(bot, 'guilds', None):
            gid = active_guild_id()
            guild = next((g for g in bot.guilds if str(g.id) == str(gid)), None)
            if guild is None:
                guild = bot.guilds[0]
        return bot, cog, guild

    @app.route('/tagjail')
    @login_required
    @role_required('admin')
    def tagjail_page():
        return render_template('tagjail.html', role=session.get('role'), username=session.get('username'))

    @app.route('/api/tagjail/state')
    @login_required
    @role_required('admin')
    def api_tagjail_state():
        bot, cog, guild = _tagjail_ctx()
        if not cog or not guild:
            return jsonify({'ok': False, 'error': 'Модуль офлайн (бот не запущен)'})
        c = cog.cfg(guild.id)
        jailed = []
        for uid, rec in list(cog._jailed.get(str(guild.id), {}).items())[:100]:
            try:
                m = guild.get_member(int(uid))
            except Exception:
                m = None
            jailed.append({
                'user_id': uid,
                'name': m.display_name if m else f'ID {uid}',
                'in_guild': bool(m),
                'since': rec.get('since', 0),
                'tag': rec.get('tag', ''),
                'reason': str(rec.get('reason', ''))[:90],
                'roles_saved': len(rec.get('roles', [])),
            })
        return jsonify({'ok': True, 'config': c, 'jailed': jailed, 'guild': guild.name})

    @app.route('/api/tagjail/config', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_tagjail_config():
        bot, cog, guild = _tagjail_ctx()
        if not cog or not guild:
            return jsonify({'ok': False, 'error': 'Модуль офлайн'}), 503
        data = request.get_json(silent=True) or {}
        updated, errors = {}, {}
        BOOL_KEYS = ('enabled', 'auto_release', 'on_join', 'on_name_change', 'dm_notify', 'scan_on_boot')
        INT_KEYS = ('min_account_days', 'jail_role_id', 'log_channel_id')
        for k, v in data.items():
            try:
                if k in BOOL_KEYS:
                    cog.set_cfg(guild.id, k, bool(v))
                    updated[k] = bool(v)
                elif k in INT_KEYS:
                    iv = int(v)
                    if iv < 0:
                        raise ValueError('>= 0')
                    cog.set_cfg(guild.id, k, iv)
                    updated[k] = iv
                elif k == 'jail_style':
                    if v not in ('remove', 'keep'):
                        raise ValueError('remove|keep')
                    cog.set_cfg(guild.id, k, v)
                    updated[k] = v
                elif k == 'age_action':
                    if v not in ('jail', 'kick'):
                        raise ValueError('jail|kick')
                    cog.set_cfg(guild.id, k, v)
                    updated[k] = v
                else:
                    errors[k] = 'недоступно для правки'
            except (ValueError, TypeError) as e:
                errors[k] = str(e)
        if errors and not updated:
            return jsonify({'ok': False, 'errors': errors}), 400
        return jsonify({'ok': True, 'updated': updated, 'errors': errors})

    @app.route('/api/tagjail/tag', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_tagjail_tag():
        bot, cog, guild = _tagjail_ctx()
        if not cog or not guild:
            return jsonify({'ok': False, 'error': 'Модуль офлайн'}), 503
        data = request.get_json(silent=True) or {}
        tag = str(data.get('tag', '')).strip()
        action = data.get('action')
        if not tag:
            return jsonify({'ok': False, 'error': 'Пустой тег'}), 400
        tags = list(cog.cfg(guild.id).get('banned_tags', []))
        if action == 'add':
            if tag not in tags:
                tags.append(tag)
        elif action == 'del':
            if tag in tags:
                tags.remove(tag)
        else:
            return jsonify({'ok': False, 'error': 'action: add|del'}), 400
        cog.set_cfg(guild.id, 'banned_tags', tags)
        return jsonify({'ok': True, 'tags': tags})

    @app.route('/api/tagjail/unjail', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_tagjail_unjail():
        bot, cog, guild = _tagjail_ctx()
        if not cog or not guild:
            return jsonify({'ok': False, 'error': 'Модуль офлайн'}), 503
        data = request.get_json(silent=True) or {}
        uid = str(data.get('user_id', '')).strip()
        if not uid.isdigit():
            return jsonify({'ok': False, 'error': 'user_id?'}), 400
        member = guild.get_member(int(uid))
        try:
            if member:
                _run_async(cog.release(member, 'Освобождён через веб-панель'))
            else:
                # покинул сервер — просто чистим запись
                cog._del_jail_rec(guild.id, int(uid))
            return jsonify({'ok': True})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500

    @app.route('/api/tagjail/scan', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_tagjail_scan():
        bot, cog, guild = _tagjail_ctx()
        if not cog or not guild:
            return jsonify({'ok': False, 'error': 'Модуль офлайн'}), 503
        if not cog.cfg(guild.id).get('enabled'):
            return jsonify({'ok': False, 'error': 'Система выключена'}), 400
        try:
            import asyncio as _aio
            _aio.run_coroutine_threadsafe(cog._sweep_guild(guild), bot.loop)
            return jsonify({'ok': True, 'started': True})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500

    # ── SCHEDULER (расписание анонсов) ──────────────────────────
    def _sched_ctx():
        import web.app as _app
        bot = _app.bot_instance
        cog = bot.get_cog('Scheduler') if bot else None
        guild = None
        if bot and getattr(bot, 'guilds', None):
            gid = active_guild_id()
            guild = next((g for g in bot.guilds if str(g.id) == str(gid)), None)
            if guild is None:
                guild = bot.guilds[0]
        return bot, cog, guild

    @app.route('/schedule')
    @login_required
    @role_required('admin')
    def schedule_page():
        return render_template('schedule.html', role=session.get('role'), username=session.get('username'))

    @app.route('/api/schedule/state')
    @login_required
    @role_required('admin')
    def api_schedule_state():
        bot, cog, guild = _sched_ctx()
        if not cog or not guild:
            return jsonify({'ok': False, 'error': 'Модуль офлайн (бот не запущен)'})
        from cogs.scheduler import REPEAT_LABEL, WEEKDAYS_RU, human_next
        channels = [{'id': str(c.id), 'name': c.name} for c in
                    sorted(guild.text_channels, key=lambda x: x.position)[:80]]
        items = []
        for it in cog.get_items(guild.id):
            items.append({
                'id': it['id'],
                'channel_id': str(it['channel_id']),
                'content': (it.get('content') or '')[:400],
                'embed_title': (it.get('embed') or {}).get('title', ''),
                'repeat': it.get('repeat', 'once'),
                'repeat_label': REPEAT_LABEL.get(it.get('repeat'), it.get('repeat')),
                'time': it.get('time', '12:00'),
                'weekday': it.get('weekday', 0),
                'weekday_label': WEEKDAYS_RU[it.get('weekday', 0)] if it.get('repeat') == 'weekly' else '',
                'tz_offset': it.get('tz_offset', 3),
                'enabled': bool(it.get('enabled', True)),
                'next': human_next(it),
                'last_sent_ts': it.get('last_sent_ts', 0),
            })
        return jsonify({'ok': True, 'items': list(reversed(items)), 'channels': channels,
                        'guild': guild.name})

    @app.route('/api/schedule/save', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_schedule_save():
        bot, cog, guild = _sched_ctx()
        if not cog or not guild:
            return jsonify({'ok': False, 'error': 'Модуль офлайн'}), 503
        from cogs.scheduler import parse_time_hhmm
        data = request.get_json(silent=True) or {}
        try:
            channel_id = int(data.get('channel_id', 0))
        except Exception:
            channel_id = 0
        if not guild.get_channel(channel_id):
            return jsonify({'ok': False, 'error': 'Канал не найден'}), 400
        if not parse_time_hhmm(data.get('time', '')):
            return jsonify({'ok': False, 'error': 'Время в формате ЧЧ:ММ'}), 400
        repeat = data.get('repeat', 'once')
        if repeat not in ('once', 'daily', 'weekly'):
            return jsonify({'ok': False, 'error': 'repeat: once|daily|weekly'}), 400
        content = str(data.get('content', '') or '')
        embed = None
        etitle = str(data.get('embed_title', '') or '').strip()
        edesc = str(data.get('embed_desc', '') or '').strip()
        if etitle or edesc:
            try:
                ecolor = int(str(data.get('embed_color', '0xD4AF37')).replace('#', '0x'), 16)
            except Exception:
                ecolor = 0xD4AF37
            embed = {'title': etitle[:240], 'description': edesc[:1800], 'color': ecolor}
        if not content.strip() and embed is None:
            return jsonify({'ok': False, 'error': 'Пустой анонс — текст или embed обязателен'}), 400
        try:
            tz = max(-12, min(14, int(data.get('tz_offset', 3))))
        except Exception:
            tz = 3
        try:
            wd = max(0, min(6, int(data.get('weekday', 0))))
        except Exception:
            wd = 0
        item = cog.add_item(
            guild.id, channel_id=channel_id, content=content, embed=embed,
            repeat=repeat, time=str(data.get('time')), weekday=wd, tz_offset=tz,
            created_by=session.get('user_id', 0) or 0)
        return jsonify({'ok': True, 'id': item['id']})

    @app.route('/api/schedule/toggle', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_schedule_toggle():
        bot, cog, guild = _sched_ctx()
        if not cog or not guild:
            return jsonify({'ok': False, 'error': 'Модуль офлайн'}), 503
        data = request.get_json(silent=True) or {}
        it = cog.toggle_item(guild.id, int(data.get('id', 0) or 0))
        if not it:
            return jsonify({'ok': False, 'error': 'Анонс не найден'}), 404
        return jsonify({'ok': True, 'enabled': bool(it.get('enabled', True))})

    @app.route('/api/schedule/delete', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_schedule_delete():
        bot, cog, guild = _sched_ctx()
        if not cog or not guild:
            return jsonify({'ok': False, 'error': 'Модуль офлайн'}), 503
        data = request.get_json(silent=True) or {}
        if cog.remove_item(guild.id, int(data.get('id', 0) or 0)):
            return jsonify({'ok': True})
        return jsonify({'ok': False, 'error': 'Анонс не найден'}), 404

    @app.route('/api/schedule/test', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_schedule_test():
        bot, cog, guild = _sched_ctx()
        if not cog or not guild:
            return jsonify({'ok': False, 'error': 'Модуль офлайн'}), 503
        data = request.get_json(silent=True) or {}
        it = cog.get_item(guild.id, int(data.get('id', 0) or 0))
        if not it:
            return jsonify({'ok': False, 'error': 'Анонс не найден'}), 404
        try:
            import asyncio as _aio
            _aio.run_coroutine_threadsafe(cog.send_item(guild, it), bot.loop)
            return jsonify({'ok': True})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500

    @app .route ('/roles')
    @login_required 
    @role_required ('admin')
    def roles_page ():
        return render_template ('roles.html',role =session .get ('role'),username =session .get ('username'),
        main_guild_id =MAIN_GUILD_ID )

    @app .route ('/channels')
    @login_required 
    @role_required ('admin')
    def channels_page ():
        return render_template ('channels.html',role =session .get ('role'),username =session .get ('username'),main_guild_id =MAIN_GUILD_ID )

    @app .route ('/mod-history')
    @login_required 
    @role_required ('mod')
    def modhistory_page ():
        return render_template ('modhistory.html',role =session .get ('role'),username =session .get ('username'))

    @app .route ('/welcome-editor')
    @login_required 
    @role_required ('admin')
    def welcome_editor_page ():
        return render_template ('welcome_editor.html',role =session .get ('role'),username =session .get ('username'),
        main_guild_id =MAIN_GUILD_ID )

    @app .route ('/reaction-roles')
    @login_required 
    @role_required ('admin')
    def reaction_roles_page ():
        return render_template ('reaction_roles.html',role =session .get ('role'),username =session .get ('username'),main_guild_id =MAIN_GUILD_ID )

    @app .route ('/giveaway')
    @login_required 
    @role_required ('admin')
    def giveaway_page ():
        return render_template ('giveaway.html',role =session .get ('role'),username =session .get ('username'),guild_id =active_guild_id ())

    @app .route ('/polls')
    @login_required 
    @role_required ('mod')
    def polls_page ():
        return render_template ('polls.html',role =session .get ('role'),username =session .get ('username'))

    @app .route ('/autorole')
    @login_required 
    @role_required ('admin')
    def autorole_page ():
        return render_template ('autorole.html',role =session .get ('role'),username =session .get ('username'),main_guild_id =MAIN_GUILD_ID )

    @app .route ('/leveling')
    @login_required 
    @role_required ('owner')
    def leveling_page ():
        return render_template ('leveling.html',role =session .get ('role'),username =session .get ('username'),main_guild_id =MAIN_GUILD_ID )

    @app .route ('/ai-tickets')
    @login_required 
    @role_required ('mod')
    def ai_tickets_page ():
        """Показать диалоги AI-тикетов"""
        try :
            guild_id =int (session .get ('guild_id',MAIN_GUILD_ID )or 0 )
        except (TypeError ,ValueError ):
            guild_id =0 
        tickets_data =_load_ai_tickets (guild_id )if guild_id else {}

        # Bot instance'dan channel информация al
        import web .app as _app ;bot =_app .bot_instance 
        tickets_list =[]

        for channel_id ,ticket in tickets_data .items ():
            try :
                guild =bot .get_guild (int (guild_id ))
                channel =guild .get_channel (int (channel_id ))if guild else None 
                user =guild .get_member (ticket ['user_id'])if guild and ticket .get ('user_id')else None 

                tickets_list .append ({
                'channel_id':channel_id ,
                'channel_name':channel .name if channel else f"ticket-{channel_id}",
                'user_name':user .display_name if user else 'Неизвестно',
                'user_id':ticket .get ('user_id'),
                'status':ticket .get ('status','unknown'),
                'category':ticket .get ('category','общий'),
                'ai_message_count':ticket .get ('ai_message_count',0 ),
                'history':ticket .get ('history',[]),
                'escalated_at':ticket .get ('escalated_at'),
                'staff_notified':ticket .get ('staff_notified',False )
                })
            except Exception:
                pass 

        return render_template (
        'ai_tickets.html',
        role =session .get ('role'),
        username =session .get ('username'),
        tickets =tickets_list 
        )

    @app .route ('/economy')
    @login_required 
    @role_required ('admin')
    def economy_page ():
        return render_template ('economy.html',role =session .get ('role'),username =session .get ('username'))

    @app .route ('/scheduled-messages')
    @login_required 
    @role_required ('owner')
    def scheduled_messages_page ():
        return render_template ('scheduled_messages.html',role =session .get ('role'),username =session .get ('username'),main_guild_id =MAIN_GUILD_ID )

    @app .route ('/custom-commands')
    @login_required 
    @role_required ('owner')
    def custom_commands_page ():
        return render_template ('custom_commands.html',role =session .get ('role'),username =session .get ('username'),
        main_guild_id =MAIN_GUILD_ID )

    @app .route ('/member-notes')
    @login_required 
    @role_required ('mod')
    def member_notes_page ():
        return render_template ('member_notes.html',role =session .get ('role'),username =session .get ('username'),main_guild_id =MAIN_GUILD_ID )

    @app .route ('/bulk-actions')
    @login_required 
    @role_required ('admin')
    def bulk_actions_page ():
        return render_template ('bulk_actions.html',role =session .get ('role'),username =session .get ('username'))

    @app .route ('/invite-tracker')
    @login_required 
    @role_required ('mod')
    def invite_tracker_page ():
        return render_template ('invite_tracker.html',role =session .get ('role'),username =session .get ('username'),main_guild_id =MAIN_GUILD_ID )

    @app .route ('/suggestions')
    @login_required 
    @role_required ('mod')
    def suggestions_page ():
        return render_template ('suggestions.html',role =session .get ('role'),username =session .get ('username'),main_guild_id =MAIN_GUILD_ID )

    @app .route ('/starboard')
    @login_required 
    @role_required ('mod')
    def starboard_page ():
        return render_template ('starboard.html',role =session .get ('role'),username =session .get ('username'),main_guild_id =MAIN_GUILD_ID )

    @app .route ('/yardim')
    @login_required 
    @role_required ('uye')
    def yardim_page ():
        return render_template ('yardim.html',role =session .get ('role'),username =session .get ('username'))

        # ── НОВЫЙ SAYFALAR ────────────────────────────────────────────────────────

    @app .route ('/chat')
    @login_required 
    @role_required ('owner')
    def chat_page ():
        return render_template ('chat.html',role =session .get ('role'),username =session .get ('username'),guild_id =active_guild_id ())

    @app .route ('/bot-settings')
    @login_required 
    @role_required ('owner')
    def bot_settings_page ():
        return render_template ('bot_settings.html',role =session .get ('role'),username =session .get ('username'))

    @app .route ('/bot-diagnostics')
    @login_required 
    @role_required ('admin')
    def bot_diagnostics_page ():
        return render_template ('bot_diagnostics.html',role =session .get ('role'),username =session .get ('username'))

    @app .route ('/leveling-admin')
    @login_required 
    @role_required ('admin')
    def leveling_admin_page ():
        return render_template ('leveling_admin.html',role =session .get ('role'),username =session .get ('username'))

    @app .route ('/ai-moderation')
    @login_required 
    @role_required ('admin')
    def ai_moderation_page ():
        return render_template ('ai_moderation.html',role =session .get ('role'),username =session .get ('username'))

    @app .route ('/temp-moderation')
    @login_required 
    @role_required ('mod')
    def temp_moderation_page ():
        return render_template ('temp_moderation.html',role =session .get ('role'),username =session .get ('username'))

    @app .route ('/cog-manager')
    @login_required 
    @role_required ('owner')
    def cog_manager_page ():
        return render_template ('cog_manager.html',role =session .get ('role'),username =session .get ('username'))

    @app .route ('/warn-config')
    @login_required 
    @role_required ('admin')
    def warn_config_page ():
        return render_template ('warn_config.html',role =session .get ('role'),username =session .get ('username'),guild_id =active_guild_id ())

    @app .route ('/duty-panel-web')
    @login_required 
    @role_required ('admin')
    def duty_panel_web_page ():
        return render_template ('duty_panel.html',role =session .get ('role'),username =session .get ('username'),guild_id =active_guild_id ())

    @app .route ('/member-search')
    @login_required 
    @role_required ('admin')
    def member_search_page ():
        return render_template ('member_search.html',role =session .get ('role'),username =session .get ('username'),guild_id =active_guild_id ())

    @app .route ('/afk-list')
    @login_required 
    @role_required ('mod')
    def afk_list_page ():
        return render_template ('afk_list.html',role =session .get ('role'),username =session .get ('username'),guild_id =active_guild_id ())

    @app .route ('/watchlist-panel')
    @login_required 
    @role_required ('mod')
    def watchlist_panel_page ():
        return render_template ('watchlist.html',role =session .get ('role'),username =session .get ('username'),guild_id =active_guild_id ())

    @app .route ('/my-profile')
    @login_required 
    @role_required ('uye')
    def my_profile_page ():
        return render_template ('member_profile.html',role =session .get ('role'),username =session .get ('username'))

    @app .route ('/change-password')
    @login_required 
    @role_required ('uye')
    def change_password_page ():
        return render_template ('change_password.html',role =session .get ('role'),username =session .get ('username'))

    # ── Липкие сообщения + Panic-локдаун (модуль cogs/mod_plus.py) ──────
    @app .route ('/mod-tools')
    @login_required 
    @role_required ('mod')
    def mod_tools_page ():
        return render_template ('mod_tools.html',role =session .get ('role'),username =session .get ('username'),guild_id =active_guild_id ())

    def _modplus_cog ():
        import web .app as _app 
        bot =_app .bot_instance 
        return (bot .get_cog ('ModPlus')if bot else None ),bot 

    def _active_guild ():
        import web .app as _app 
        gid =active_guild_id ()
        _c ,bot =_modplus_cog ()
        return bot .get_guild (int (gid ))if bot and gid else None 

    @app .route ('/api/sticky',methods =['GET'])
    @login_required 
    @role_required ('mod')
    def api_sticky_list ():
        from cogs .mod_plus import _sticky_path ,_load_json 
        guild =_active_guild ()
        data =_load_json (_sticky_path (guild .id ),{})if guild else {}
        items =[]
        for cid ,entry in data .items ():
            ch =guild .get_channel (int (cid ))if guild else None 
            items .append ({
                'channel_id':str (cid ),
                'channel_name':getattr (ch ,'name',str (cid )),
                'text':(entry .get ('text')or '')[:400 ],
                'set_at':entry .get ('set_at',''),
            })
        return jsonify ({'success':True ,'items':items })

    @app .route ('/api/sticky',methods =['POST'])
    @login_required 
    @role_required ('mod')
    def api_sticky_create ():
        from cogs .mod_plus import _sticky_path ,_load_json ,_save_json 
        data =request .get_json (silent =True )or {}
        cid =str (data .get ('channel_id','')).strip ()
        text =(data .get ('text')or '').strip ()
        if not cid .isdigit ()or not text or len (text )>1900 :
            return jsonify ({'success':False ,'error':'Канал или текст неверные (текст до 1900 символов)'}),400 
        guild =_active_guild ()
        if not guild :
            return jsonify ({'success':False ,'error':'Бот офлайн'}),503 
        if not guild .get_channel (int (cid )):
            return jsonify ({'success':False ,'error':'Канал не найден на сервере'}),404 
        sdata =_load_json (_sticky_path (guild .id ),{})
        old =sdata .get (cid )
        sdata [cid ]={'text':text ,'msg_id':None ,'author_id':0,
        'set_at':datetime.now(timezone.utc).replace(tzinfo=None).isoformat (),
        'by_panel':session .get ('username')}
        _save_json (_sticky_path (guild .id ),sdata )

        cog ,bot =_modplus_cog ()
        reposted =None 
        if cog :
            try :
                if old and old .get ('msg_id'):
                    _run_async (cog .delete_sticky_message_remote (guild ,cid ,old ['msg_id']))
                reposted =_run_async (cog .repost_remote (guild ,cid ))
            except Exception as e :
                reposted =False 
                print (f'[MOD+] sticky repost из панели: {e}')
        _fire_panel_notification ('sticky',f"📌 Липкое в #{cid}",f"{session.get('username')}: {text[:120]}")
        return jsonify ({'success':True ,'reposted':bool (reposted )})

    @app .route ('/api/sticky',methods =['DELETE'])
    @login_required 
    @role_required ('mod')
    def api_sticky_delete ():
        from cogs .mod_plus import _sticky_path ,_load_json ,_save_json 
        data =request .get_json (silent =True )or {}
        cid =str (data .get ('channel_id','')).strip ()
        if not cid .isdigit ():
            return jsonify ({'success':False ,'error':'Нужен channel_id'}),400 
        guild =_active_guild ()
        if not guild :
            return jsonify ({'success':False ,'error':'Бот офлайн'}),503 
        sdata =_load_json (_sticky_path (guild .id ),{})
        entry =sdata .pop (cid ,None )
        if not entry :
            return jsonify ({'success':False ,'error':'В этом канале липкого нет'}),404 
        _save_json (_sticky_path (guild .id ),sdata )
        cog ,bot =_modplus_cog ()
        if cog and entry .get ('msg_id'):
            try :
                _run_async (cog .delete_sticky_message_remote (guild ,cid ,entry ['msg_id']))
            except Exception :
                pass
        return jsonify ({'success':True })

    # ── Тихий мут (ghost mute) ────────────────────────────────────────────
    @app .route ('/api/ghost',methods =['GET'])
    @login_required
    @role_required ('mod')
    def api_ghost_list ():
        from cogs .mod_plus import ghost_entries
        guild =_active_guild ()
        data =ghost_entries (guild .id )if guild else {}
        items =[]
        for uid ,e in data .items ():
            m =guild .get_member (int (uid ))if guild else None
            items .append ({
                'user_id':str (uid ),
                'name':str (m )if m else f'ID {uid}',
                'reason':e .get ('reason',''),
                'by':e .get ('by',''),
                'until':e .get ('until'),
                'suppressed':e .get ('suppressed')or 0 ,
                'set_at':e .get ('set_at',''),
            })
        items .sort (key =lambda x :x ['set_at'],reverse =True )
        return jsonify ({'success':True ,'items':items })

    @app .route ('/api/ghost',methods =['POST'])
    @login_required
    @role_required ('mod')
    def api_ghost_add ():
        from cogs .mod_plus import ghost_add ,parse_ghost_duration
        data =request .get_json (silent =True )or {}
        uid =str (data .get ('user_id','')).strip ()
        reason =(data .get ('reason')or 'Через панель')[:300 ]
        if not uid .isdigit ():
            return jsonify ({'success':False ,'error':'Нужен числовой ID участника'}),400
        guild =_active_guild ()
        if not guild :
            return jsonify ({'success':False ,'error':'Бот офлайн'}),503
        member =guild .get_member (int (uid ))
        if not member :
            try :
                member =_run_async (guild .fetch_member (int (uid )))
            except Exception :
                member =None
        if not member :
            return jsonify ({'success':False ,'error':'Участник не найден на сервере'}),404
        if getattr (member ,'bot',False ):
            return jsonify ({'success':False ,'error':'Ботов призраками не делаем'}),400
        if getattr (guild ,'owner_id',None )and int (uid )==guild .owner_id :
            return jsonify ({'success':False ,'error':'Владельца мутить нельзя'}),400
        perms =getattr (member ,'guild_permissions',None )
        if perms is not None and perms .manage_messages :
            return jsonify ({'success':False ,'error':'У него права модератора — на состав не работает'}),400
        sec ,err =parse_ghost_duration (data .get ('duration'))
        if err :
            return jsonify ({'success':False ,'error':err }),400
        until =None
        if sec :
            from datetime import datetime as _dt ,timedelta as _td ,timezone as _tz
            until =(_dt .now (_tz .utc )+_td (seconds =sec )).isoformat ()
        ghost_add (guild .id ,int (uid ),reason ,
        by =f"панель:{session.get('username','?')}",until =until )
        _fire_panel_notification ('ghost',f"👻 Тихий мут: {member}",
        f"{session.get('username')}: {reason}")
        return jsonify ({'success':True })

    @app .route ('/api/ghost',methods =['DELETE'])
    @login_required
    @role_required ('mod')
    def api_ghost_remove ():
        from cogs .mod_plus import ghost_remove
        data =request .get_json (silent =True )or {}
        uid =str (data .get ('user_id','')).strip ()
        if not uid .isdigit ():
            return jsonify ({'success':False ,'error':'Нужен user_id'}),400
        guild =_active_guild ()
        if not guild :
            return jsonify ({'success':False ,'error':'Бот офлайн'}),503
        entry =ghost_remove (guild .id ,int (uid ))
        if not entry :
            return jsonify ({'success':False ,'error':'Он и не был призраком'}),404
        _fire_panel_notification ('ghost',f"👻 Тихий мут снят: {uid}",session .get ('username','?'))
        return jsonify ({'success':True ,'suppressed':entry .get ('suppressed')or 0 })

    # ── Демки к наказаниям (cogs/proof_cog.py) ────────────────────────────
    @app .route ('/proofs')
    @login_required
    @role_required ('mod')
    def proofs_page ():
        return render_template ('proofs.html',role =session .get ('role'),username =session .get ('username'))

    @app .route ('/api/proofs',methods =['GET'])
    @login_required
    @role_required ('mod')
    def api_proofs_list ():
        from cogs .proof_cog import proof_list
        guild =_active_guild ()
        gid =guild .id if guild else int (active_guild_id ()or 0 )
        uid =str (request .args .get ('user_id','')).strip ()
        action =str (request .args .get ('action','')).strip ()
        items =proof_list (gid ,user_id =int (uid ))if uid .isdigit ()else proof_list (gid )
        if action :
            items =[e for e in items if e .get ('action')==action ]
        out =[]
        for e in items [:50 ]:
            ch_id =e .get ('channel_id')
            jump =None
            if ch_id and e .get ('msg_id'):
                jump =f"https://discord.com/channels/{gid}/{ch_id}/{e['msg_id']}"
            out .append ({'id':e .get ('id'),'user_id':str (e .get ('user_id')),
            'user_name':e .get ('user_name'),'mod_name':e .get ('mod_name'),
            'action':e .get ('action'),'reason':e .get ('reason'),
            'link':e .get ('link'),'url':e .get ('url'),
            'set_at':e .get ('set_at'),'jump':jump })
        return jsonify ({'success':True ,'items':out ,'total':len (items )})

    @app .route ('/api/proofs/<int:pid>',methods =['DELETE'])
    @login_required
    @role_required ('admin')
    def api_proofs_delete (pid ):
        # удаление демки — только admin+ (история наказаний = серьёзно)
        from cogs .proof_cog import proof_remove
        guild =_active_guild ()
        if not guild :
            return jsonify ({'success':False ,'error':'Бот офлайн'}),503
        entry =proof_remove (guild .id ,pid )
        if not entry :
            return jsonify ({'success':False ,'error':'Демка не найдена'}),404
        # заодно попробуем убрать сообщение из канала доказательств
        msg_deleted =False
        try :
            if entry .get ('channel_id')and entry .get ('msg_id'):
                ch =guild .get_channel (int (entry ['channel_id']))
                if ch :
                    msg =_run_async (ch .fetch_message (int (entry ['msg_id'])))
                    _run_async (msg .delete ())
                    msg_deleted =True
        except Exception :
            pass
        _fire_panel_notification ('proof',f'🗑️ Демка #{pid} удалена',
        f"{session.get('username')}: {entry.get('user_name')}")
        return jsonify ({'success':True ,'msg_deleted':msg_deleted })

    @app .route ('/api/panic',methods =['GET'])
    @login_required 
    @role_required ('mod')
    def api_panic_status_panel ():
        from cogs .mod_plus import _panic_path ,_load_json 
        guild =_active_guild ()
        st =_load_json (_panic_path (guild .id ),None )if guild else None 
        return jsonify ({'success':True ,'active':bool (st ),'state':st or {}})

    @app .route ('/api/panic',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_panic_toggle ():
        # ВНИМАНИЕ: только admin+ — это локдаун всего сервера
        data =request .get_json (silent =True )or {}
        action =str (data .get ('action','')).lower ()
        reason =(data .get ('reason')or 'Через панель')[:300 ]
        boost =bool (data .get ('boost_verification'))
        guild =_active_guild ()
        cog ,bot =_modplus_cog ()
        if not cog or not guild :
            return jsonify ({'success':False ,'error':'Бот офлайн или модуль mod_plus не загружен'}),503 
        who =f'панель:{session.get("username","?")}'
        try :
            if action =='on':
                state ,done ,failed =_run_async (cog .panic_enable_core (guild ,reason ,boost_verification =boost ,by =who ),timeout =90 )
                if state is None :
                    return jsonify ({'success':False ,'error':'Локдаун уже активен'}),409 
            elif action =='off':
                state ,done ,failed =_run_async (cog .panic_disable_core (guild ,by =who ),timeout =90 )
                if state is None :
                    return jsonify ({'success':False ,'error':'Локдаун не активен'}),409 
            else :
                return jsonify ({'success':False ,'error':'action: on или off'}),400 
        except Exception as e :
            return jsonify ({'success':False ,'error':str (e )[:200 ]}),500 
        _fire_panel_notification ('panic',f"🚨 Локдаун: {action}",f'{who}: {reason}')
        return jsonify ({'success':True ,'action':action ,'done':done ,'failed':failed })

    # ── Резервные копии данных (services/backup.py + cogs/backup_cog.py) ──
    @app .route ('/backups')
    @login_required
    @role_required ('admin')
    def backups_page ():
        return render_template ('backups.html',role =session .get ('role'),username =session .get ('username'))

    def _backup_settings ():
        try :
            from cogs .backup_cog import backup_enabled ,backup_hour ,backup_keep ,backup_dir ,backup_attach
            return {'enabled':backup_enabled (),'hour':backup_hour (),'keep':backup_keep (),
            'dir':backup_dir (),'attach':backup_attach ()}
        except Exception :
            from services import backup as _bk2
            return {'enabled':False ,'hour':5 ,'keep':_bk2 .BACKUP_KEEP_DEFAULT ,
            'dir':_bk2 .BACKUP_DIR_DEFAULT ,'attach':False }

    @app .route ('/api/backups',methods =['GET'])
    @login_required
    @role_required ('admin')
    def api_backups_list ():
        from services import backup as _bk
        cfg =_backup_settings ()
        items =_bk .list_backups (cfg ['dir'])
        total =sum (i ['size']for i in items )
        for i in items :
            i .pop ('mtime',None )
        return jsonify ({'success':True ,'items':items ,
        'stats':{'total':len (items ),'total_size':total ,
        'total_size_h':_bk .format_size (total )},
        'settings':{k :v for k ,v in cfg .items ()if k !='dir'}})

    @app .route ('/api/backups',methods =['POST'])
    @login_required
    @role_required ('admin')
    def api_backups_create ():
        from services import backup as _bk
        cfg =_backup_settings ()
        try :
            info =_bk .create_backup (backup_dir =cfg ['dir'],reason ='ручной (панель)',
            by =f"панель:{session.get('username','?')}")
            removed =_bk .rotate_backups (cfg ['dir'],cfg ['keep'])
        except Exception as e :
            return jsonify ({'success':False ,'error':str (e )[:200 ]}),500
        # Лучшая попытка отчитаться в мод-лог Discord через ког (если бот жив)
        try :
            import web .app as _app
            bot =getattr (_app ,'bot_instance',None )
            cog =bot .get_cog ('Backup')if bot else None
            if cog :
                _run_async (cog ._notify (info ,removed ),timeout =20 )
        except Exception :
            pass
        info ['size_h']=_bk .format_size (info ['size'])
        _fire_panel_notification ('backup','💾 Бэкап создан',
        f"{session.get('username')}: {info['name']} ({info['size_h']})")
        return jsonify ({'success':True ,'item':info ,'removed':len (removed )})

    @app .route ('/api/backups/download/<name>')
    @login_required
    @role_required ('admin')
    def api_backups_download (name ):
        from services import backup as _bk
        from flask import send_file
        cfg =_backup_settings ()
        path =_bk .resolve_backup (name ,cfg ['dir'])
        if not path :
            return jsonify ({'success':False ,'error':'Архив не найден'}),404
        return send_file (path ,as_attachment =True ,download_name =name ,mimetype ='application/zip')

    @app .route ('/api/backups/<name>',methods =['DELETE'])
    @login_required
    @role_required ('admin')
    def api_backups_delete (name ):
        from services import backup as _bk
        cfg =_backup_settings ()
        path =_bk .resolve_backup (name ,cfg ['dir'])
        if not path :
            if _bk .valid_backup_name (name ):
                return jsonify ({'success':False ,'error':'Архив не найден'}),404
            return jsonify ({'success':False ,'error':'Некорректное имя архива'}),400
        try :
            os .remove (path )
        except OSError as e :
            return jsonify ({'success':False ,'error':str (e )[:150 ]}),500
        _fire_panel_notification ('backup','🗑️ Бэкап удалён',f"{session.get('username')}: {name}")
        return jsonify ({'success':True })

    @app .route ('/api/user/change-password',methods =['POST'])
    @login_required
    @role_required ('uye')
    def api_user_change_password ():
        from web .app import USERS 
        import json as _json 
        data =request .get_json (silent =True )or {}
        old_pass =data .get ('old_password','').strip ()
        new_pass =data .get ('new_password','').strip ()

        if not old_pass or not new_pass or len (new_pass )<6 :
            return jsonify ({'error':'Неверные данные'})

            # Owner контроль (USERS dict'inden)
        username =session .get ('username')
        if username in USERS :
            if USERS [username ]['password']!=old_pass :
                return jsonify ({'error':'Текущий пароль неверен'})
            USERS [username ]['password']=new_pass 
            return jsonify ({'success':True })

            # Normal участник — По Discord ID ara
        discord_id =session .get ('discord_id')or username 
        members_file ='data/members.json'
        if not os .path .exists (members_file ):
            return jsonify ({'error':'Пользователь не найден'})

        with open (members_file ,'r',encoding ='utf-8')as f :
            members =_json .load (f )

            # ищем по discord_id, если нет — пробуем по display_name
        member_key =None 
        if discord_id and discord_id in members :
            member_key =discord_id 
        else :
            for k ,v in members .items ():
                if v .get ('display_name')==username or v .get ('name')==username :
                    member_key =k 
                    break 

        if not member_key :
            return jsonify ({'error':'Пользователь не найден'})
        if members [member_key ].get ('password')!=old_pass :
            return jsonify ({'error':'Текущий пароль неверен'})

        members [member_key ]['password']=new_pass 
        with open (members_file ,'w',encoding ='utf-8')as f :
            _json .dump (members ,f ,indent =2 ,ensure_ascii =False )
        return jsonify ({'success':True })

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
                        except Exception:pass 

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
                    except Exception:pass 

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
                        except Exception:pass 
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
                        except Exception:pass 
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
                        except Exception:pass 
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
                        except Exception:pass 
                    role_gecmisi .sort ()
                    # Кто пригласил
                    inviter ='?'
                    invite_file =f'data/invite_joins_{g.id}.json'
                    if os .path .exists (invite_file ):
                        try :
                            with open (invite_file ,'r',encoding ='utf-8')as fp :
                                inv =json .load (fp )
                            inviter =inv .get (uid_str ,{}).get ('inviter_name','?')
                        except Exception:pass 
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
            except Exception:pass 
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
            except Exception:pass 

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
            except Exception:pass 

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
                    except Exception:pass 
        if health_lines :
            health_info ='Оценки состояния сервера:\n'+'\n'.join (f'  {l}'for l in health_lines )
        else :
        # Fallback: API'den hesapla
            try :
                import requests as _req2 
                for g in (bot .guilds if bot else []):
                    r =_req2 .get (
                    f'http://localhost:5001/api/guild/{g.id}/health',
                    cookies =request .cookies ,timeout =3 
                    )
                    if r .status_code ==200 :
                        hd =r .json ()
                        health_info =f"{g.name} состояние skoru: {hd.get('score','?')}/100 ({hd.get('label','?')})"
                        break 
            except Exception:pass 

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

        system =(
        "Ты Aether — ИИ-ассистент Discord-сервера Aether и веб-панели.\n"
        f"Пользователь: {session.get('username')}, Роль: {user_role}\n"
        f"Время: {now.strftime('%H:%M')}, Дата: {now.strftime('%d %B %Y, %A')}\n\n"
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
            answer ,model_name ,_ =_call (messages ,max_tokens =1024 )
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
                except Exception :
                    pass 
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
            except Exception :
                pass 

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
            except Exception :
                pass 
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
                    final_answer ,model_name2 ,_ =_call (messages ,max_tokens =1024 )
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
                            until =_discord .utils .utcnow ()+_dt .timedelta (minutes =mins )
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
                            wd [gid ][uid ].append ({'reason':reason ,'mod':'Arthur','timestamp':_dt2 .datetime.now(timezone.utc).replace(tzinfo=None).isoformat ()})
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

        # ── LEVELING API ─────────────────────────────────────
    @app .route ('/api/leveling/config',methods =['GET','POST'])
    @login_required 
    @role_required ('admin')
    def api_leveling_config ():
        import web .app as _app ;bot =_app .bot_instance 
        from cogs .leveling_engagement import LevelingEngagement 
        if not bot :
            return jsonify ({'error':'Бот офлайн'}),503 
        cog =bot .get_cog ('LevelingEngagement')
        if not cog :
            return jsonify ({'error':'Модуль не загружен'}),404 
        guild_id =str (session .get ('selected_guild')or MAIN_GUILD_ID )
        if request .method =='POST':
            cfg =cog .load_config (guild_id )
            patch =request .get_json (silent =True )or {}
            for k ,v in patch .items ():
                cfg [k ]=v 
            cog .save_config (guild_id ,cfg )
            return jsonify ({'ok':True ,'config':cfg })
        return jsonify (cog .load_config (guild_id ))

    @app .route ('/api/leveling/stats')
    @login_required 
    def api_leveling_stats ():
        import web .app as _app ;bot =_app .bot_instance 
        from cogs .leveling_engagement import LevelingEngagement ,level_from_xp 
        if not bot :
            return jsonify ({'error':'Бот офлайн'}),503 
        cog =bot .get_cog ('LevelingEngagement')
        if not cog :
            return jsonify ({'error':'Модуль не загружен'}),404 
        guild_id =str (session .get ('selected_guild')or MAIN_GUILD_ID )
        data =cog .load_xp (guild_id )
        users =data .get ('users',{})
        top =sorted (users .items (),key =lambda x :x [1 ].get ('xp',0 ),reverse =True )[:10 ]
        top_list =[]
        for uid ,u in top :
            member =bot .get_guild (int (guild_id )).get_member (int (uid ))if bot .get_guild (int (guild_id ))else None 
            level ,_ ,_ =level_from_xp (u .get ('xp',0 ))
            top_list .append ({
            'name':member .display_name if member else f'User#{uid}',
            'level':level ,
            'xp':u .get ('xp',0 )
            })
        max_lvl =0 
        for u in users .values ():
            lvl ,_ ,_ =level_from_xp (u .get ('xp',0 ))
            if lvl >max_lvl :
                max_lvl =lvl 
        from cogs .leveling_engagement import ACHIEVEMENTS 
        return jsonify ({
        'total_users':len (users ),
        'max_level':max_lvl ,
        'total_xp':sum (u .get ('xp',0 )for u in users .values ()),
        'total_achievements':sum (len (v )for v in data .get ('achievements',{}).values ()),
        'total_ach_available':len (ACHIEVEMENTS ),
        'top':top_list 
        })

    @app .route ('/api/leveling/achievements')
    @login_required 
    def api_leveling_achievements ():
        import web .app as _app ;bot =_app .bot_instance 
        from cogs .leveling_engagement import LevelingEngagement 
        if not bot :
            return jsonify ({'error':'Бот офлайн'}),503 
        cog =bot .get_cog ('LevelingEngagement')
        if not cog :
            return jsonify ({'error':'Модуль не загружен'}),404 
        guild_id =str (session .get ('selected_guild')or MAIN_GUILD_ID )
        data =cog .load_xp (guild_id )
        username =session .get ('username','')
        # Find user's unlocked achievements
        unlocked =[]
        for uid ,achs in data .get ('achievements',{}).items ():
            try :
                g =bot .get_guild (int (guild_id ))
                if g :
                    m =g .get_member (int (uid ))
                    if m and m .display_name ==username :
                        unlocked =achs 
                        break 
            except Exception:pass 
        from cogs .leveling_engagement import ACHIEVEMENTS 
        return jsonify ({'unlocked':unlocked ,'catalog':ACHIEVEMENTS })

    @app .route ('/api/leveling/rewards')
    @login_required 
    def api_leveling_rewards ():
        import web .app as _app ;bot =_app .bot_instance 
        from cogs .leveling_engagement import LevelingEngagement 
        if not bot :
            return jsonify ({'error':'Бот офлайн'}),503 
        cog =bot .get_cog ('LevelingEngagement')
        if not cog :
            return jsonify ({'error':'Модуль не загружен'}),404 
        guild_id =str (session .get ('selected_guild')or MAIN_GUILD_ID )
        cfg =cog .load_config (guild_id )
        return jsonify ({'rewards':cfg .get ('level_rewards',{})})

        # ── AI MODERATION API ─────────────────────────────────────
    @app .route ('/api/ai-mod/config',methods =['GET','POST'])
    @login_required 
    @role_required ('admin')
    def api_ai_mod_config ():
        import web .app as _app ;bot =_app .bot_instance 
        from cogs .ai_moderation import AIModeration 
        if not bot :
            return jsonify ({'error':'Бот офлайн'}),503 
        cog =bot .get_cog ('AIModeration')
        if not cog :
            return jsonify ({'error':'Модуль не загружен'}),404 
        guild_id =str (session .get ('selected_guild')or MAIN_GUILD_ID )
        if request .method =='POST':
            cfg =cog .load_config (guild_id )
            patch =request .get_json (silent =True )or {}
            for k ,v in patch .items ():
                if isinstance (v ,dict )and k in cfg :
                    cfg [k ].update (v )
                else :
                    cfg [k ]=v 
            cog .save_config (guild_id ,cfg )
            return jsonify ({'ok':True })
        return jsonify (cog .load_config (guild_id ))

    @app .route ('/api/ai-mod/stats')
    @login_required 
    def api_ai_mod_stats ():
        import web .app as _app ;bot =_app .bot_instance 
        from cogs .ai_moderation import AIModeration 
        if not bot :
            return jsonify ({'error':'Бот офлайн'}),503 
        cog =bot .get_cog ('AIModeration')
        if not cog :
            return jsonify ({'error':'Модуль не загружен'}),404 
        guild_id =str (session .get ('selected_guild')or MAIN_GUILD_ID )
        history =cog .load_history (guild_id )
        from collections import Counter 
        import time as _t 
        action_counter =Counter (h .get ('action')for h in history )
        last_24h =sum (1 for h in history if _t .time ()-h .get ('ts',0 )<86400 )
        return jsonify ({
        'total':len (history ),
        'last_24h':last_24h ,
        'bans':action_counter .get ('ban',0 ),
        'mutes':action_counter .get ('mute',0 ),
        'kicks':action_counter .get ('kick',0 ),
        'warns':action_counter .get ('warn',0 ),
        })

    @app .route ('/api/ai-mod/test',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_ai_mod_test ():
        import web .app as _app ;bot =_app .bot_instance 
        from cogs .ai_moderation import AIModeration 
        if not bot :
            return jsonify ({'error':'Бот офлайн'}),503 
        cog =bot .get_cog ('AIModeration')
        if not cog :
            return jsonify ({'error':'Модуль не загружен'}),404 
        guild_id =str (session .get ('selected_guild')or MAIN_GUILD_ID )
        cfg =cog .load_config (guild_id )
        d =request .get_json (silent =True )or {}
        text =d .get ('text','')
        matches =cog .detect_toxic (text ,cfg .get ('languages',['ru','tr','en']),cfg .get ('sensitivity',0.7 ))
        if not matches :
            return jsonify ({'clean':True })
        severity_order =['mild','spam','moderate','discrimination','severe']
        top =max (matches ,key =lambda m :severity_order .index (m [0 ]))
        return jsonify ({
        'clean':False ,
        'severity':top [0 ],
        'matches':len (matches ),
        'patterns':[p [1 ]for p in matches ]
        })

        # ── BOT DIAGNOSTICS API ────────────────────────────────────
    @app .route ('/api/bot/health')
    @login_required 
    def api_bot_health ():
        import web .app as _app ;bot =_app .bot_instance 
        from cogs .diagnostics import Diagnostics 
        if not bot :
            return jsonify ({'error':'Бот офлайн'}),503 
        cog =bot .get_cog ('Diagnostics')
        if not cog :
            return jsonify ({'error':'Модуль не загружен'}),404 
        health =cog .get_health_snapshot ()
        # Try to load from file
        import json as _json 
        try :
            with open ('data/bot_health.json','r',encoding ='utf-8')as f :
                persisted =_json .load (f )
                return jsonify (persisted )
        except Exception :
            return jsonify ({'current':health ,'history':[],'error_log':[],'cog_perf':{},'repair_count':{}})

    @app .route ('/api/bot/errors')
    @login_required 
    @role_required ('admin')
    def api_bot_errors ():
        import json as _json 
        try :
            with open ('data/error_log.json','r',encoding ='utf-8')as f :
                log =_json .load (f )
                return jsonify (log [-20 :])
        except Exception :
            return jsonify ([])

    @app .route ('/api/bot/hot-reload',methods =['POST'])
    @login_required 
    @role_required ('owner')
    def api_bot_hot_reload ():
        import web .app as _app ;bot =_app .bot_instance 
        if not bot :
            return jsonify ({'error':'Бот офлайн'}),503 
            # Trigger via discord bot
        from cogs .diagnostics import Diagnostics 
        cog =bot .get_cog ('Diagnostics')
        if not cog :
            return jsonify ({'error':'Модуль не загружен'}),404 
            # Re-check files
        import asyncio 
        reloaded =[]
        import hashlib ,os 
        for filename in os .listdir ('cogs'):
            if filename .endswith ('.py')and filename !='__init__.py':
                cog_name =filename [:-3 ]
                if cog_name in ('embed_utils',):continue 
                filepath =f'cogs/{filename}'
                with open (filepath ,'rb')as f :
                    h =hashlib .md5 (f .read ()).hexdigest ()
                if cog .cog_hash_cache .get (cog_name )!=h :
                    try :
                        ext =f'cogs.{cog_name}'
                        if ext in bot .extensions :
                            asyncio .run_coroutine_threadsafe (bot .reload_extension (ext ),bot .loop ).result (timeout =10 )
                        else :
                            asyncio .run_coroutine_threadsafe (bot .load_extension (ext ),bot .loop ).result (timeout =10 )
                        reloaded .append (cog_name )
                    except Exception :
                        pass 
                cog .cog_hash_cache [cog_name ]=h 
        return jsonify ({'reloaded':reloaded })

        # NOTE: api_bot_gc / api_bot_diagnose / api_bot_restart are defined in web/app.py.
        # Defining them here again would clash with Flask's endpoint registry
        # ("View function mapping is overwriting an existing endpoint function").

        # ── TEMP MODERATION API ─────────────────────────────────
    @app .route ('/api/temp-mod/active')
    @login_required 
    @role_required ('mod')
    def api_temp_mod_active ():
        import web .app as _app ;bot =_app .bot_instance 
        from cogs .temp_moderation import TempModeration 
        if not bot :
            return jsonify ({'error':'Бот офлайн'}),503 
        cog =bot .get_cog ('TempModeration')
        if not cog :
            return jsonify ({'error':'Модуль не загружен'}),404 
        guild_id =str (session .get ('selected_guild')or MAIN_GUILD_ID )
        # Defensive: mutes/bans/kicks dict-of-dicts may be missing or shaped differently.
        mutes =(getattr (cog ,'_mutes',{})or {}).get (guild_id ,{})or {}
        bans =(getattr (cog ,'_bans',{})or {}).get (guild_id ,{})or {}
        kicks =(getattr (cog ,'_kicks',{})or {}).get (guild_id ,{})or {}
        scheduled =getattr (cog ,'_scheduled',[])or []
        scheduled =[s for s in scheduled 
        if isinstance (s ,dict )
        and s .get ('guild_id')==guild_id 
        and s .get ('status')=='pending']
        return jsonify ({
        'mutes':list (mutes .values ())if isinstance (mutes ,dict )else [],
        'bans':list (bans .values ())if isinstance (bans ,dict )else [],
        'kicks':list (kicks .values ())if isinstance (kicks ,dict )else [],
        'scheduled':scheduled ,
        })

    @app .route ('/api/temp-mod/mute',methods =['POST'])
    @login_required 
    @role_required ('mod')
    def api_temp_mod_mute ():
        import web .app as _app ;bot =_app .bot_instance 
        from cogs .temp_moderation import TempModeration ,parse_duration 
        if not bot :
            return jsonify ({'error':'Бот офлайн'}),503 
        cog =bot .get_cog ('TempModeration')
        if not cog :
            return jsonify ({'error':'Модуль не загружен'}),404 
        d =request .get_json (silent =True )or {}
        sec =parse_duration (d .get ('duration','1h'))
        if not sec :
            return jsonify ({'error':'Неверный формат времени'}),400 
        guild =bot .get_guild (int (session .get ('selected_guild')or MAIN_GUILD_ID ))
        if not guild :
            return jsonify ({'error':'Сервер не найден'}),404 
            # Resolve user
        user_id =d .get ('user_id','').strip ('<@!>')
        try :
            member =_run_async (_resolve_member_async (guild ,int (user_id )))
        except Exception :
            return jsonify ({'error':'Пользователь не найден'}),404 
        if not member :
            return jsonify ({'error':'Пользователь не найден'}),404 
        from datetime import datetime ,timedelta 
        until =datetime.now(timezone.utc).replace(tzinfo=None)+timedelta (seconds =sec )
        try :
            _run_async (member .timeout (until ,reason =f"[Panel] {session.get('username')}: {d.get('reason', '')}"))
        except Exception as e :
            return jsonify ({'error':str (e )}),400 
        cog ._mutes .setdefault (str (guild .id ),{})[str (member .id )]={
        'until':time .time ()+sec ,'reason':d .get ('reason',''),
        'mod_id':session .get ('username',''),'created_at':time .time (),'duration':sec ,
        }
        cog ._save ('_mutes',cog ._mutes_file ())
        return jsonify ({'ok':True })

    @app .route ('/api/temp-mod/ban',methods =['POST'])
    @login_required 
    @role_required ('mod')
    def api_temp_mod_ban ():
        import web .app as _app ;bot =_app .bot_instance 
        from cogs .temp_moderation import TempModeration ,parse_duration 
        if not bot :
            return jsonify ({'error':'Бот офлайн'}),503 
        cog =bot .get_cog ('TempModeration')
        if not cog :
            return jsonify ({'error':'Модуль не загружен'}),404 
        d =request .get_json (silent =True )or {}
        sec =parse_duration (d .get ('duration','1d'))
        if not sec :
            return jsonify ({'error':'Неверный формат'}),400 
        guild =bot .get_guild (int (session .get ('selected_guild')or MAIN_GUILD_ID ))
        user_id =d .get ('user_id','').strip ('<@!>')
        try :
            member =_run_async (_resolve_member_async (guild ,int (user_id )))
        except Exception :
            return jsonify ({'error':'Пользователь не найден'}),404 
        if not member :
            return jsonify ({'error':'Пользователь не найден'}),404 
        try :
            _run_async (guild .ban (member ,reason =f"[Panel] {session.get('username')}: {d.get('reason', '')}"))
        except Exception as e :
            return jsonify ({'error':str (e )}),400 
        cog ._bans .setdefault (str (guild .id ),{})[str (member .id )]={
        'until':time .time ()+sec ,'reason':d .get ('reason',''),
        'mod_id':session .get ('username',''),'created_at':time .time (),'duration':sec ,
        'user_name':str (member ),
        }
        cog ._save ('_bans',cog ._bans_file ())
        return jsonify ({'ok':True })

    @app .route ('/api/temp-mod/kick',methods =['POST'])
    @login_required 
    @role_required ('mod')
    def api_temp_mod_kick ():
        import web .app as _app ;bot =_app .bot_instance 
        from cogs .temp_moderation import TempModeration ,parse_duration 
        if not bot :
            return jsonify ({'error':'Бот офлайн'}),503 
        cog =bot .get_cog ('TempModeration')
        if not cog :
            return jsonify ({'error':'Модуль не загружен'}),404 
        d =request .get_json (silent =True )or {}
        sec =parse_duration (d .get ('duration','5m'))
        if not sec :
            return jsonify ({'error':'Неверный формат'}),400 
        guild =bot .get_guild (int (session .get ('selected_guild')or MAIN_GUILD_ID ))
        user_id =d .get ('user_id','').strip ('<@!>')
        try :
            member =_run_async (_resolve_member_async (guild ,int (user_id )))
        except Exception :
            return jsonify ({'error':'Пользователь не найден'}),404 
        if not member :
            return jsonify ({'error':'Пользователь не найден'}),404 
        try :
            _run_async (member .kick (reason =f"[Panel] {session.get('username')}: {d.get('reason', '')}"))
        except Exception as e :
            return jsonify ({'error':str (e )}),400 
        cog ._kicks .setdefault (str (guild .id ),{})[str (member .id )]={
        'until':time .time ()+sec ,'reason':d .get ('reason',''),
        'mod_id':session .get ('username',''),'created_at':time .time (),'duration':sec ,
        'user_name':str (member ),
        }
        cog ._save ('_kicks',cog ._kicks_file ())
        return jsonify ({'ok':True })

    @app .route ('/api/temp-mod/unmute',methods =['POST'])
    @login_required 
    @role_required ('mod')
    def api_temp_mod_unmute ():
        import web .app as _app ;bot =_app .bot_instance 
        if not bot :
            return jsonify ({'error':'Бот офлайн'}),503 
        from cogs .temp_moderation import TempModeration 
        cog =bot .get_cog ('TempModeration')
        if not cog :
            return jsonify ({'error':'Модуль не загружен'}),404 
        d =request .get_json (silent =True )or {}
        user_id =d .get ('user_id','').strip ('<@!>')
        guild =bot .get_guild (int (session .get ('selected_guild')or MAIN_GUILD_ID ))
        member =guild .get_member (int (user_id ))
        if member and member .is_timed_out ():
            try :
                _run_async (member .timeout (None ))
            except Exception :
                pass 
        cog ._mutes .get (str (guild .id ),{}).pop (user_id ,None )
        cog ._save ('_mutes',cog ._mutes_file ())
        return jsonify ({'ok':True })

    @app .route ('/api/temp-mod/unban',methods =['POST'])
    @login_required 
    @role_required ('mod')
    def api_temp_mod_unban ():
        import web .app as _app ;bot =_app .bot_instance 
        if not bot :
            return jsonify ({'error':'Бот офлайн'}),503 
        from cogs .temp_moderation import TempModeration 
        cog =bot .get_cog ('TempModeration')
        if not cog :
            return jsonify ({'error':'Модуль не загружен'}),404 
        d =request .get_json (silent =True )or {}
        user_id =d .get ('user_id','').strip ('<@!>')
        guild =bot .get_guild (int (session .get ('selected_guild')or MAIN_GUILD_ID ))
        try :
            user =_run_async (bot .fetch_user (int (user_id )))
            _run_async (guild .unban (user ))
        except Exception as e :
            return jsonify ({'error':str (e )}),400 
        cog ._bans .get (str (guild .id ),{}).pop (user_id ,None )
        cog ._save ('_bans',cog ._bans_file ())
        return jsonify ({'ok':True })

    @app .route ('/api/temp-mod/unschedule',methods =['POST'])
    @login_required 
    @role_required ('mod')
    def api_temp_mod_unschedule ():
        import web .app as _app ;bot =_app .bot_instance 
        if not bot :
            return jsonify ({'error':'Бот офлайн'}),503 
        from cogs .temp_moderation import TempModeration 
        cog =bot .get_cog ('TempModeration')
        if not cog :
            return jsonify ({'error':'Модуль не загружен'}),404 
        d =request .get_json (silent =True )or {}
        eid =d .get ('id','')
        cog ._scheduled =[s for s in cog ._scheduled if s ['id']!=eid ]
        cog ._save ('_scheduled',cog ._scheduled_file ())
        return jsonify ({'ok':True })

        # ── API ROUTES ────────────────────────────────────────────────────────────

        # ── НОВЫЙ API ENDPOINT'LERИ ────────────────────────────────────────────────

    @app .route ('/api/bot/status',methods =['POST'])
    @login_required 
    @role_required ('owner')
    def api_bot_status ():
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio 
        if not bot :return jsonify ({'error':'Бот офлайн'}),503 
        d =request .get_json (silent =True )or {}
        status_map ={'online':discord .Status .online ,'idle':discord .Status .idle ,'dnd':discord .Status .dnd ,'invisible':discord .Status .invisible }
        type_map ={'listening':discord .ActivityType .listening ,'playing':discord .ActivityType .playing ,'watching':discord .ActivityType .watching ,'competing':discord .ActivityType .competing }
        status =status_map .get (d .get ('status','online'),discord .Status .online )
        atype =type_map .get (d .get ('activity_type','listening'),discord .ActivityType .listening )
        atext =d .get ('activity_text','.gg/Aether')
        def _set ():
            _run_async (bot .change_presence (status =status ,activity =discord .Activity (type =atype ,name =atext )))
        asyncio .run_coroutine_threadsafe (_set (),bot .loop ).result (timeout =5 )
        # Config'e сохранить — bot новыйden baшlayыnca da hatыrlasыn
        os .makedirs ('data',exist_ok =True )
        cfg ={}
        cfg_file ='data/bot_config.json'
        if os .path .exists (cfg_file ):
            try :
                with open (cfg_file ,encoding ='utf-8')as f :cfg =json .load (f )
            except Exception :pass 
        cfg ['status']=d .get ('status','online')
        cfg ['activity_type']=d .get ('activity_type','listening')
        cfg ['activity_text']=atext 
        with open (cfg_file ,'w',encoding ='utf-8')as f :
            json .dump (cfg ,f ,indent =2 ,ensure_ascii =False )
        return jsonify ({'ok':True })

    @app .route ('/api/bot/prefix',methods =['POST'])
    @login_required 
    @role_required ('owner')
    def api_bot_prefix ():
        d =request .get_json (silent =True )or {}
        prefix =d .get ('prefix','!').strip ()
        if not prefix :return jsonify ({'error':'Пустой префикс'}),400 
        if len (prefix )>10 :return jsonify ({'error':'префикс слишком длинный'}),400 
        os .makedirs ('data',exist_ok =True )
        cfg_file ='data/bot_config.json'
        cfg ={}
        if os .path .exists (cfg_file ):
            try :
                with open (cfg_file ,'r',encoding ='utf-8')as f :
                    cfg =json .load (f )or {}
            except Exception :
                pass 
        if not isinstance (cfg ,dict ):
            cfg ={}
            # Mevcut status/activity alanlarыnы KORU
        cfg ['prefix']=prefix 
        with open (cfg_file ,'w',encoding ='utf-8')as f :
            json .dump (cfg ,f ,indent =2 ,ensure_ascii =False )
        return jsonify ({'ok':True })

    @app .route ('/api/cogs/load',methods =['POST'])
    @login_required 
    @role_required ('owner')
    def api_cog_load ():
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio 
        if not bot :return jsonify ({'error':'Бот офлайн'}),503 
        d =request .get_json (silent =True )or {}
        name =(d .get ('name')or d .get ('cog')or '').strip ()
        if not name :
            return jsonify ({'error':'Не указано имя расширения (name/cog)'}),400 
            # Accept both "cogs.foo" and "foo" forms
        if not name .startswith ('cogs.'):
            name ='cogs.'+name 
            # Idempotent: already loaded?
        if name in bot .extensions :
            return jsonify ({'ok':True ,'already_loaded':True ,'name':name })
        try :
            future =asyncio .run_coroutine_threadsafe (bot .load_extension (name ),bot .loop )
            future .result (timeout =10 )
            return jsonify ({'ok':True ,'name':name })
        except ModuleNotFoundError as e :
            return jsonify ({'error':f'Файл не найден: {e}'}),404 
        except Exception as e :
            err =str (e )or type (e ).__name__ 
            # Friendly translation for common cases
            if 'already loaded'in err .lower ():
                return jsonify ({'ok':True ,'already_loaded':True ,'name':name })
            return jsonify ({'error':f'Не удалось загрузить {name}: {err}'}),400 

    @app .route ('/api/cogs/unload',methods =['POST'])
    @login_required 
    @role_required ('owner')
    def api_cog_unload ():
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio 
        if not bot :return jsonify ({'error':'Бот офлайн'}),503 
        d =request .get_json (silent =True )or {}
        name =(d .get ('name')or d .get ('cog')or '').strip ()
        if not name :
            return jsonify ({'error':'Не указано имя расширения'}),400 
        if not name .startswith ('cogs.'):
            name ='cogs.'+name 
        if name not in bot .extensions :
            return jsonify ({'ok':True ,'not_loaded':True ,'name':name })
        try :
            future =asyncio .run_coroutine_threadsafe (bot .unload_extension (name ),bot .loop )
            future .result (timeout =10 )
            return jsonify ({'ok':True ,'name':name })
        except Exception as e :
            return jsonify ({'error':f'Не удалось выгрузить {name}: {e}'}),400 

    @app .route ('/api/cogs/reload',methods =['POST'])
    @login_required 
    @role_required ('owner')
    def api_cog_reload ():
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio 
        if not bot :return jsonify ({'error':'Бот офлайн'}),503 
        d =request .get_json (silent =True )or {}
        name =(d .get ('name')or d .get ('cog')or '').strip ()
        if not name :
            return jsonify ({'error':'Не указано имя расширения'}),400 
        if not name .startswith ('cogs.'):
            name ='cogs.'+name 
        try :
            future =asyncio .run_coroutine_threadsafe (bot .reload_extension (name ),bot .loop )
            future .result (timeout =10 )
            return jsonify ({'ok':True ,'name':name })
        except Exception as e :
            return jsonify ({'error':f'Не удалось перезагрузить {name}: {e}'}),400 

    @app .route ('/api/cogs/reload-all',methods =['POST'])
    @login_required 
    @role_required ('owner')
    def api_cog_reload_all ():
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio 
        if not bot :return jsonify ({'error':'Бот офлайн'}),503 
        results =[]
        for ext in list (bot .extensions .keys ()):
            try :
                asyncio .run_coroutine_threadsafe (bot .reload_extension (ext ),bot .loop ).result (timeout =10 )
                results .append ({'name':ext ,'ok':True })
            except Exception as e :
                results .append ({'name':ext ,'ok':False ,'error':str (e )})
        return jsonify ({'ok':True ,'results':results })

    @app .route ('/api/warn-config/<guild_id>',methods =['GET'])
    @login_required 
    @role_required ('admin')
    def api_warn_config_get (guild_id ):
        f =f'data/warn_config_{guild_id}.json'
        if not os .path .exists (f ):
            return jsonify ({'thresholds':[{'count':3 ,'action':'timeout','duration':10 },{'count':5 ,'action':'ban','duration':0 }]})
        with open (f ,encoding ='utf-8')as fp :
            return jsonify (json .load (fp ))

    @app .route ('/api/warn-config/<guild_id>',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_warn_config_save (guild_id ):
        d =request .get_json (silent =True )or {}
        os .makedirs ('data',exist_ok =True )
        with open (f'data/warn_config_{guild_id}.json','w',encoding ='utf-8')as fp :
            json .dump (d ,fp ,indent =2 ,ensure_ascii =False )
        return jsonify ({'ok':True })

    @app .route ('/api/duty/<guild_id>',methods =['GET'])
    @login_required 
    @role_required ('admin')
    def api_duty_data (guild_id ):
        duty_f ='data/duty_log.json'
        pts_f ='data/duty_points.json'
        duty ={}
        pts ={}
        if os .path .exists (duty_f ):
            with open (duty_f ,encoding ='utf-8')as f :duty =json .load (f ).get (guild_id ,{})
        if os .path .exists (pts_f ):
            with open (pts_f ,encoding ='utf-8')as f :pts =json .load (f ).get (guild_id ,{})
        return jsonify ({'duty':duty ,'points':pts })

    @app .route ('/api/afk/<guild_id>',methods =['GET'])
    @login_required 
    @role_required ('mod')
    def api_afk_list (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        if not bot :return jsonify ([])
        afk_cog =bot .get_cog ('AFK')
        if not afk_cog :return jsonify ([])
        guild_afk =afk_cog ._afk .get (str (guild_id ),{})
        result =[]
        guild =bot .get_guild (int (guild_id ))
        for uid ,data in guild_afk .items ():
            member =guild .get_member (int (uid ))if guild else None 
            result .append ({
            'id':uid ,
            'name':member .display_name if member else uid ,
            'avatar':str (member .display_avatar .url )if member else None ,
            'reason':data .get ('reason','AFK'),
            'since':data .get ('since','')
            })
        return jsonify (result )

    @app .route ('/api/watchlist/<guild_id>',methods =['GET'])
    @login_required 
    @role_required ('mod')
    def api_watchlist (guild_id ):
        f ='data/mod_data.json'
        if not os .path .exists (f ):return jsonify ([])
        with open (f ,encoding ='utf-8')as fp :
            data =json .load (fp )
        wl =data .get ('watchlist',{}).get (guild_id ,{})
        result =[]
        for uid ,info in wl .items ():
            result .append ({'id':uid ,'name':info .get ('added_by',uid ),'reason':info .get ('reason',''),'added_by':info .get ('added_by',''),'timestamp':info .get ('timestamp','')})
        return jsonify (result )

    @app .route ('/api/member-search/<guild_id>',methods =['GET'])
    @login_required 
    @role_required ('admin')
    def api_member_search (guild_id ):
        # Поиск участников: по имени, нику, упоминанию или (части) ID,
        # с релевантной сортировкой и понятными ошибками вместо молчаливых [].
        import web .app as _app ;bot =_app .bot_instance 
        if not bot :
            return jsonify ({'error':'Бот сейчас не в сети — поиск участников недоступен.'}),503 
        guild =bot .get_guild (int (guild_id )if str (guild_id ).isdigit ()else 0 )
        if not guild :
            return jsonify ({'error':'Сервер не найден: проверьте выбор сервера на панели.'}),404 
        q =ms_normalize_query (request .args .get ('q',''))
        if not q :
            return jsonify ({'error':'Введите имя, никнейм или ID участника.'}),400 
        matches =ms_search_members (guild .members ,q ,limit =25 )
        return jsonify ([ms_member_payload (m )for m in matches ])

    @app .route ('/api/member-profile/<guild_id>/<user_id>',methods =['GET'])
    @login_required 
    @role_required ('admin')
    def api_member_profile (guild_id ,user_id ):
        # Профиль участника: данные Discord + предупреждения + история модерации.
        if not str (user_id ).isdigit ():
            return jsonify ({'error':'Некорректный ID участника.'}),400 
        import web .app as _app ;bot =_app .bot_instance 
        result ={'id':user_id ,'warnings':[],'warn_count':0 ,'case':[],'cases':[],'case_count':0 }
        if bot :
            guild =bot .get_guild (int (guild_id )if str (guild_id ).isdigit ()else 0 )
            if guild :
                m =guild .get_member (int (user_id ))
                if m :
                    result .update (ms_member_payload (m ))
                    result ['joined_at']=m .joined_at .isoformat ()if m .joined_at else None 
                    result ['created_at']=m .created_at .isoformat ()if m .created_at else None 
                    result ['role']=[r .name for r in m .roles [1 :]]
                    result ['roles']=[{'name':r .name ,'color':str (r .color )}for r in m .roles [1 :]]
                    result ['member_found']=True 
                else :
                    result ['member_found']=False 
        # Предупреждения (работают и когда бот не в сети — читаются с диска)
        warns =[]
        wf ='data/warnings.json'
        if os .path .exists (wf ):
            try :
                with open (wf ,encoding ='utf-8')as f :wdata =json .load (f )
                warns =wdata .get (str (guild_id ),{}).get (str (user_id ),[])
            except Exception :
                warns =[]
        warns =[ms_normalize_warn (w ,i +1 )for i ,w in enumerate (warns )]
        result ['warnings']=warns 
        result ['warn_count']=len (warns )
        # История модерации
        case =[]
        mf ='data/mod_data.json'
        if os .path .exists (mf ):
            try :
                with open (mf ,encoding ='utf-8')as f :mdata =json .load (f )
                case =[c for c in mdata .get ('case',{}).get (str (guild_id ),[])if str (c .get ('user_id'))==str (user_id )]
            except Exception :
                case =[]
        case =[ms_normalize_case (c ,i +1 )for i ,c in enumerate (case )]
        result ['case']=case 
        result ['cases']=case 
        result ['case_count']=len (case )
        return jsonify (result )

    @app .route ('/api/my-profile',methods =['GET'])
    @login_required 
    def api_my_profile ():
        import web .app as _app ;bot =_app .bot_instance 
        username =session .get ('username')
        result ={'username':username ,'display_name':username }
        # Данные участника
        mf ='data/members.json'
        if os .path .exists (mf ):
            with open (mf ,encoding ='utf-8')as f :members =json .load (f )
            for uid ,m in members .items ():
                if m .get ('username')==username :
                    result ['discord_id']=uid 
                    result ['avatar']=m .get ('avatar')
                    result ['display_name']=m .get ('display_name',username )
                    break 
                    # Предупреждения (все серверы)
        wf ='data/warnings.json'
        all_warns =[]
        if os .path .exists (wf )and result .get ('discord_id'):
            with open (wf ,encoding ='utf-8')as f :wdata =json .load (f )
            for gid ,users in wdata .items ():
                all_warns .extend (users .get (result ['discord_id'],[]))
        result ['warnings']=all_warns 
        # Баланс (первый сервер)
        if bot and result .get ('discord_id'):
            for guild in bot .guilds :
                bf =f'data/balance_{guild.id}.json'
                if os .path .exists (bf ):
                    with open (bf ,encoding ='utf-8')as f :bdata =json .load (f )
                    result ['balance']=bdata .get (result ['discord_id'],{}).get ('balance',0 )
                    break 
                    # Время в голосовых каналах
        if bot and result .get ('discord_id'):
            for guild in bot .guilds :
                vf =f'data/voice_stats_{guild.id}.json'
                if os .path .exists (vf ):
                    with open (vf ,encoding ='utf-8')as f :vdata =json .load (f )
                    result ['voice_seconds']=vdata .get ('users',{}).get (result ['discord_id'],{}).get ('total_seconds',0 )
                    break 
                    # Количество приглашений
        if bot and result .get ('discord_id'):
            for guild in bot .guilds :
                inf =f'data/invite_counts_{guild.id}.json'
                if os .path .exists (inf ):
                    with open (inf ,encoding ='utf-8')as f :idata =json .load (f )
                    result ['invites']=idata .get (result ['discord_id'],{}).get ('total',0 )
                    break 
        return jsonify (result )

    @app .route ('/api/my-birthday/<guild_id>',methods =['GET'])
    @login_required 
    def api_my_birthday_get (guild_id ):
        username =session .get ('username')
        mf ='data/members.json'
        discord_id =None 
        if os .path .exists (mf ):
            with open (mf ,encoding ='utf-8')as f :members =json .load (f )
            for uid ,m in members .items ():
                if m .get ('username')==username :
                    discord_id =uid ;break 
        if not discord_id :return jsonify ({})
        bf =f'data/birthdays_{guild_id}.json'
        if not os .path .exists (bf ):return jsonify ({})
        with open (bf ,encoding ='utf-8')as f :bdata =json .load (f )
        return jsonify (bdata .get (discord_id ,{}))

    @app .route ('/api/my-birthday/<guild_id>',methods =['POST'])
    @login_required 
    def api_my_birthday_save (guild_id ):
        username =session .get ('username')
        mf ='data/members.json'
        discord_id =None 
        if os .path .exists (mf ):
            with open (mf ,encoding ='utf-8')as f :members =json .load (f )
            for uid ,m in members .items ():
                if m .get ('username')==username :
                    discord_id =uid ;break 
        if not discord_id :return jsonify ({'error':'Пользователь не найден'}),404 
        d =request .get_json (silent =True )or {}
        day ,month ,year =d .get ('day'),d .get ('month'),d .get ('year')
        if not day or not month :return jsonify ({'error':'День и месяц обязательны'}),400 
        os .makedirs ('data',exist_ok =True )
        bf =f'data/birthdays_{guild_id}.json'
        bdata ={}
        if os .path .exists (bf ):
            with open (bf ,encoding ='utf-8')as f :bdata =json .load (f )
        entry ={'date':f'{int(month):02d}-{int(day):02d}','name':username }
        if year :entry ['year']=int (year )
        bdata [discord_id ]=entry 
        with open (bf ,'w',encoding ='utf-8')as f :json .dump (bdata ,f ,indent =2 ,ensure_ascii =False )
        return jsonify ({'ok':True })

    @app .route ('/api/birthdays/<guild_id>',methods =['GET'])
    @login_required 
    def api_birthdays_list (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        bf =f'data/birthdays_{guild_id}.json'
        if not os .path .exists (bf ):return jsonify ([])
        with open (bf ,encoding ='utf-8')as f :bdata =json .load (f )
        from datetime import datetime as _dt 
        now =_dt .utcnow ()
        today_num =now .month *100 +now .day 
        result =[]
        for uid ,info in bdata .items ():
            try :
                m ,d =map (int ,info ['date'].split ('-'))
                num =m *100 +d 
                diff =num -today_num 
                if diff <0 :diff +=1200 
                name =info .get ('name',uid )
                if bot :
                    guild =bot .get_guild (int (guild_id ))
                    if guild :
                        member =guild .get_member (int (uid ))
                        if member :name =member .display_name 
                result .append ({'name':name ,'date':info ['date'],'diff':diff })
            except Exception:pass 
        result .sort (key =lambda x :x ['diff'])
        return jsonify (result )

    @app .route ('/api/giveaway/<guild_id>',methods =['GET'])
    @login_required 
    @role_required ('admin')
    def api_giveaway_list (guild_id ):
        f =f'data/giveaways_{guild_id}.json'
        if not os .path .exists (f ):
            return jsonify ([])
        with open (f ,encoding ='utf-8')as fp :
            data =json .load (fp )
        result =[]
        for gw_id ,gw in data .items ():
            result .append ({
            'id':gw_id ,
            'prize':gw .get ('prize','?'),
            'winners':gw .get ('winners',1 ),
            'status':gw .get ('status','unknown'),
            'ends_at':gw .get ('ends_at',''),
            'participants':len (gw .get ('participants',[])),
            'channel_id':gw .get ('channel_id',''),
            })
        result .sort (key =lambda x :x ['ends_at'],reverse =True )
        return jsonify (result )

    @app .route ('/api/giveaway/<guild_id>/create',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_giveaway_create (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio ,random 
        from datetime import timedelta 
        data_req =request .get_json (silent =True )or {}
        prize =data_req .get ('prize','').strip ()
        winners =int (data_req .get ('winners',1 ))
        minutes =int (data_req .get ('minutes',60 ))
        channel_id =data_req .get ('channel_id','')
        if not prize or not channel_id :
            return jsonify ({'error':'Не заполнено поле'}),400 

        if not bot :
            return jsonify ({'error':'Бот офлайн'}),503 

        guild =bot .get_guild (int (guild_id ))
        if not guild :
            return jsonify ({'error':'Сервер не найден'}),404 

        channel =guild .get_channel (int (channel_id ))
        if not channel :
            return jsonify ({'error':'Канал не найден'}),404 

        ends_at =datetime.now(timezone.utc).replace(tzinfo=None)+timedelta (minutes =minutes )
        gw_id =str (int (ends_at .timestamp ()))

        def _send ():
            embed =discord .Embed (
            title ="🎉  РОЗЫГРЫШ НАЧАЛСЯ!",
            color =0x2ECC71 ,
            timestamp =ends_at 
            )
            embed .description =(
            f"**🏆 Награда:** `{prize}`\n\n"
            "Чтобы участвовать, нажми кнопку **🎉 Участвовать**!\n"
            f"Giveaway <t:{int(ends_at.timestamp())}:R> sona eriyor."
            )
            embed .add_field (name ="👥 Участники",value =f"0/{winners}",inline =True )
            embed .add_field (name ="🏆 Победителей",value =str (winners ),inline =True )
            embed .add_field (name ="⏰ Завершение",value =f"<t:{int(ends_at.timestamp())}:F>",inline =True )
            embed .set_footer (text =f"{guild.name} • Giveaway Система")

            from cogs .giveaway import GiveawayView 
            view =GiveawayView (gw_id ,guild_id )
            msg =_run_async (channel .send (embed =embed ,view =view ))

            os .makedirs ('data',exist_ok =True )
            f =f'data/giveaways_{guild_id}.json'
            gws ={}
            if os .path .exists (f ):
                with open (f ,encoding ='utf-8')as fp :
                    gws =json .load (fp )
            gws [gw_id ]={
            'prize':prize ,'winners':winners ,
            'ends_at':ends_at .isoformat (),
            'channel_id':str (channel .id ),
            'message_id':str (msg .id ),
            'status':'active',
            'participants':[],
            'user_info':{},
            }
            with open (f ,'w',encoding ='utf-8')as fp :
                json .dump (gws ,fp ,indent =2 ,ensure_ascii =False )

        asyncio .run_coroutine_threadsafe (_send (),bot .loop ).result (timeout =10 )
        return jsonify ({'ok':True ,'id':gw_id })

    @app .route ('/api/giveaway/<guild_id>/<gw_id>/end',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_giveaway_end (guild_id ,gw_id ):
        f =f'data/giveaways_{guild_id}.json'
        if not os .path .exists (f ):
            return jsonify ({'error':'Не найдено'}),404 
        with open (f ,encoding ='utf-8')as fp :
            gws =json .load (fp )
        if gw_id not in gws :
            return jsonify ({'error':'Розыгрыш не найден'}),404 
        gws [gw_id ]['status']='ended'
        with open (f ,'w',encoding ='utf-8')as fp :
            json .dump (gws ,fp ,indent =2 ,ensure_ascii =False )
        return jsonify ({'ok':True })

    @app .route ('/api/giveaway/<guild_id>/<gw_id>/delete',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_giveaway_delete (guild_id ,gw_id ):
        f =f'data/giveaways_{guild_id}.json'
        if not os .path .exists (f ):
            return jsonify ({'ok':True })
        with open (f ,encoding ='utf-8')as fp :
            gws =json .load (fp )
        gws .pop (gw_id ,None )
        with open (f ,'w',encoding ='utf-8')as fp :
            json .dump (gws ,fp ,indent =2 ,ensure_ascii =False )
        return jsonify ({'ok':True })

    @app .route ('/api/guild/<guild_id>/info')
    @login_required 
    def api_guild_info (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        if not bot :
            return jsonify ({'error':'Бот офлайн'})
        guild =bot .get_guild (int (guild_id ))
        if not guild :
            return jsonify ({'error':'Сервер не найден'})
        return jsonify ({
        'id':str (guild .id ),
        'name':guild .name ,
        'description':guild .description or '',
        'icon':str (guild .icon .url )if guild .icon else None ,
        'icon_url':str (guild .icon .url )if guild .icon else None ,
        'banner':str (guild .banner .url )if guild .banner else None ,
        'member_count':guild .member_count ,
        'online_count':sum (1 for m in guild .members if m .status !=discord .Status .offline ),
        'bot_count':sum (1 for m in guild .members if m .bot ),
        'channel_count':len (guild .channels ),
        'role_count':len (guild .roles ),
        'emoji_count':len (guild .emojis ),
        'boost_level':guild .premium_tier ,
        'boost_count':guild .premium_subscription_count ,
        'created_at':guild .created_at .isoformat (),
        'owner_id':str (guild .owner_id ),
        'verification_level':str (guild .verification_level ),
        'features':list (guild .features ),
        })

    @app .route ('/api/bot-stats')
    @login_required 
    def api_bot_stats ():
        import time 
        import web .app as _app ;bot =_app .bot_instance 
        if not bot :
            return jsonify ({'error':'Бот офлайн'})
        try :
            try :
                import psutil 
                proc =psutil .Process ()
                cpu =psutil .cpu_percent (interval =0.1 )
                ram =round (proc .memory_info ().rss /1024 /1024 ,1 )
                uptime_sec =int (time .time ()-proc .create_time ())
            except Exception :
                cpu =0 
                ram =0 
                uptime_sec =0 
            h =uptime_sec //3600 
            m =(uptime_sec %3600 )//60 
            uptime =f"{h}sa {m}dk"
            history_file ='data/sys_history.json'
            os .makedirs ('data',exist_ok =True )
            history =[]
            if os .path .exists (history_file ):
                try :
                    with open (history_file )as f :
                        history =json .load (f )
                except Exception :
                    history =[]
            now =datetime.now(timezone.utc).replace(tzinfo=None).strftime ('%H:%M')
            history .append ({'time':now ,'cpu':cpu ,'ram':ram })
            history =history [-20 :]
            try :
                with open (history_file ,'w')as f :
                    json .dump (history ,f )
            except Exception :
                pass 
            lat_val = 0
            if bot and bot.latency is not None:
                try:
                    if math.isfinite(bot.latency):
                        lat_val = round(bot.latency * 1000)
                except Exception:
                    lat_val = 0
            return jsonify ({
            'guilds':len (bot .guilds ) if bot else 0,
            'users':sum (g .member_count for g in bot .guilds ) if bot else 0,
            'latency':lat_val ,
            'uptime':uptime ,
            'cpu':cpu ,
            'ram':ram ,
            'history':history ,
            'guild_list':[{'name':g .name ,'members':g .member_count }for g in bot .guilds ] if bot else []
            })
        except Exception as e :
            return jsonify ({'error':str (e ),'guilds':len (bot .guilds )if bot else 0 ,'history':[]}),200

    @app .route ('/api/mod-history')
    @login_required 
    @role_required ('mod')
    def api_mod_history ():
        import web .app as _app ;bot =_app .bot_instance 
        guild_id =request .args .get ('guild_id')
        all_events =[]

        # ── 1. mod_data.json — bot'un сохран case'ler ────────────────────
        mod_file ='data/mod_data.json'
        if os .path .exists (mod_file ):
            try :
                with open (mod_file ,'r',encoding ='utf-8')as fp :
                    md =json .load (fp )
                case =md .get ('case',{})
                for gid ,case_list in case .items ():
                    if guild_id and gid !=guild_id :
                        continue 
                    if not isinstance (case_list ,list ):
                        continue 
                    for case in case_list :
                        uid =str (case .get ('user_id',''))
                        mid =str (case .get ('mod_id',''))
                        all_events .append ({
                        'guild_id':gid ,
                        'category':'mod',
                        'action':case .get ('action','warn'),
                        'target_name':uid ,
                        'target_id':uid ,
                        'mod_name':mid ,
                        'reason':case .get ('reason','Belirtilmedi'),
                        'created_at':case .get ('timestamp',''),
                        'source':'bot',
                        })
            except Exception as _e :
                print (f'[MOD-HISTORY] Ошибка данных модерации: {_e}')

                # ── 2. Discord Audit Cache ────────────────────────────────────────────
        cache_file ='data/discord_audit_cache.json'
        if os .path .exists (cache_file ):
            try :
                with open (cache_file ,'r',encoding ='utf-8')as fp :
                    cache =json .load (fp )
                mod_cats ={'Бан','Бан снят','Кик','Мут','Мут снят',
                'ban','kick','timeout','unban','warn','mute'}
                for gid ,events in cache .items ():
                    if guild_id and gid !=guild_id :
                        continue 
                    for ev in events :
                        if ev .get ('action')in mod_cats :
                            ev ['guild_id']=gid 
                            ev ['created_at']=ev .get ('timestamp','')
                            all_events .append (ev )
            except Exception as _e :
                print (f'[MOD-HISTORY] Cache okuma Ошибки: {_e}')

                # ── 3. warnings.json ─────────────────────────────────────────────────
        warns_file ='data/warnings.json'
        if os .path .exists (warns_file ):
            try :
                with open (warns_file ,'r',encoding ='utf-8')as fp :
                    data =json .load (fp )
                for gid ,guild_warns in data .items ():
                    if guild_id and gid !=guild_id :
                        continue 
                    for uid ,warns in guild_warns .items ():
                        if not isinstance (warns ,list ):
                            continue 
                        name =uid 
                        if bot :
                            for g in bot .guilds :
                                m =g .get_member (int (uid ))if uid .isdigit ()else None 
                                if m :
                                    name =m .display_name 
                                    break 
                        for w in warns :
                            all_events .append ({
                            'guild_id':gid ,
                            'category':'mod',
                            'action':'warn',
                            'target_name':name ,
                            'target_id':uid ,
                            'mod_name':w .get ('mod',w .get ('moderator','?')),
                            'reason':w .get ('reason',''),
                            'created_at':w .get ('timestamp',''),
                            'source':'bot',
                            })
            except Exception as _e :
                print (f'[MOD-HISTORY] Ошибка чтения предупреждений: {_e}')

        all_events .sort (key =lambda x :x .get ('created_at',''),reverse =True )
        return jsonify (all_events [:500 ])

    @app .route ('/api/roles')
    @login_required 
    def api_roles_default ():
        if not MAIN_GUILD_ID :
            return jsonify ({'error':'Сервер не выбран (задайте MAIN_GUILD_ID в .env)'}),503 
        return api_guild_roles (str (MAIN_GUILD_ID ))

    @app .route ('/api/channels')
    @login_required 
    def api_channels_default ():
        if not MAIN_GUILD_ID :
            return jsonify ({'error':'Сервер не выбран (задайте MAIN_GUILD_ID в .env)'}),503 
        return api_guild_channels (str (MAIN_GUILD_ID ))

    @app .route ('/api/members')
    @login_required 
    def api_members_default ():
        if not MAIN_GUILD_ID :
            return jsonify ({'error':'Сервер не выбран (задайте MAIN_GUILD_ID в .env)'}),503 
        from web .app import api_guild_members 
        return api_guild_members (str (MAIN_GUILD_ID ))

    @app .route ('/api/guild/<guild_id>/roles')
    @login_required 
    def api_guild_roles (guild_id ):
        import web .app as _app 
        bot =_app .bot_instance 
        if not bot :return jsonify ([])
        guild =bot .get_guild (int (guild_id ))
        if not guild :return jsonify ([])
        roles =[{'id':str (r .id ),'name':r .name ,'color':str (r .color ),'members':len (r .members )}
        for r in guild .roles if r .name !='@everyone']
        return jsonify (sorted (roles ,key =lambda x :-x ['members']))

    @app .route ('/api/guild/<guild_id>/roles/create',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_create_role (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio ,discord 
        if not bot :return jsonify ({'error':'Бот офлайн'}),503 
        data =request .get_json (silent =True )or {}
        name =(data .get ('name')or '').strip ()
        if not name :
            return jsonify ({'error':'Требуется название роли'}),400 
            # Проверка: один из серверов, где состоит бот
        try :
            gid =int (guild_id )
        except (TypeError ,ValueError ):
            return jsonify ({'error':'Неверный ID сервера'}),400 
        guild =bot .get_guild (gid )if bot else None 
        if guild is None and bot is not None :
        # Запасной вариант: сравнение ID строкой
            for g in bot .guilds :
                if str (g .id )==str (guild_id ):
                    guild =g 
                    break 
        if guild is None :
            return jsonify ({'error':f'Бот не состоит на этом сервере (id={guild_id})'}),404 
        async def do ():
            color_hex =(data .get ('color')or '#dc143c').lstrip ('#')or 'dc143c'
            try :
                color =discord .Color (int (color_hex ,16 ))
            except ValueError :
                color =discord .Color .default ()
            await (guild .create_role (name =name ,color =color ,reason ='Создано через панель Aether'))
        try :
            asyncio .run_coroutine_threadsafe (do (),bot .loop ).result (timeout =10 )
            return jsonify ({'success':True })
        except discord .Forbidden :
            return jsonify ({'error':'У меня нет прав создавать роли на этом сервере'}),403 
        except discord .HTTPException as e :
            return jsonify ({'error':f'Ошибка Discord: {e}'}),500 
        except Exception as e :
            return jsonify ({'error':str (e )}),500 

    @app .route ('/api/guild/<guild_id>/roles/<role_id>/delete',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_delete_role (guild_id ,role_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio 
        if not bot :return jsonify ({'error':'Бот офлайн'})
        async def do ():
            guild =bot .get_guild (int (guild_id ))
            role =guild .get_role (int (role_id ))
            if role :await (role .delete ())
        asyncio .run_coroutine_threadsafe (do (),bot .loop ).result (timeout =10 )
        return jsonify ({'success':True })

    @app .route ('/api/guild/<guild_id>/channels')
    @login_required 
    def api_guild_channels (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import discord as _discord 
        if not bot :
            print ('[WEB][WARN] /channels: bot is None')
            return jsonify ({'error':'Бот офлайн','channels':[]})

        guild =bot .get_guild (int (guild_id ))
        if not guild :
            for g in bot .guilds :
                if str (g .id )==str (guild_id ):
                    guild =g 
                    break 
        if not guild :
            print (f'[WEB][WARN] /channels: guild {guild_id} заметок found. Bot guilds: {[str(g.id) for g in bot.guilds]}')
            return jsonify ({'error':f'Guild {guild_id} заметок found','channels':[]})

        type_map ={
        _discord .ChannelType .text :'text',
        _discord .ChannelType .voice :'voice',
        _discord .ChannelType .category :'category',
        _discord .ChannelType .news :'text',
        _discord .ChannelType .stage_voice :'voice',
        _discord .ChannelType .forum :'text',
        }

        channels_data =[]
        try :
            for c in guild .channels :
                ch_type =type_map .get (c .type ,str (c .type ).split ('.')[-1 ])
                # Подробная информация о канале — для детального отображения в панели
                topic =''
                nsfw =False
                slowmode =0
                bitrate =0
                user_limit =0
                news =False
                stage =False
                forum =False
                connected =0
                if hasattr (c ,'topic'):
                    topic =c .topic or ''
                if hasattr (c ,'nsfw'):
                    nsfw =bool (c .nsfw )
                if hasattr (c ,'slowmode_delay'):
                    slowmode =int (c .slowmode_delay or 0 )
                if hasattr (c ,'bitrate'):
                    bitrate =int ((c .bitrate or 0 )// 1000 )
                if hasattr (c ,'user_limit'):
                    user_limit =int (c .user_limit or 0 )
                if hasattr (c ,'type'):
                    if c .type ==discord .ChannelType .news :
                        news =True 
                    if c .type ==discord .ChannelType .stage_voice :
                        stage =True 
                    if c .type ==discord .ChannelType .forum :
                        forum =True 
                if hasattr (c ,'members'):
                    try :
                        connected =len ([m for m in c .members if not getattr (m ,'bot',False )])
                    except Exception :
                        connected =0 
                channels_data .append ({
                'id':str (c .id ),
                'name':c .name ,
                'type':ch_type ,
                'position':getattr (c ,'position',0 ),
                'category':c .category .name if hasattr (c ,'category')and c .category else None ,
                'category_id':str (c .category .id ) if hasattr (c ,'category')and c .category else None ,
                'category_pos':c .category .position if hasattr (c ,'category')and c .category else -1 ,
                'topic':topic ,
                'nsfw':nsfw ,
                'slowmode':slowmode ,
                'bitrate':bitrate ,
                'user_limit':user_limit ,
                'news':news ,
                'stage':stage ,
                'forum':forum ,
                'connected':connected ,
                'created_at':c .created_at .isoformat () if getattr (c ,'created_at',None )else None ,
                'mention':getattr (c ,'mention','')
                })
        except Exception as e :
            print (f'[WEB][ERR] channels error: {e}')
            return jsonify ({'error':str (e ),'channels':[]})

        sorted_channels =sorted (channels_data ,key =lambda x :(x ['category_pos'],x ['position']))
        print (f'[WEB] /channels guild={guild_id} returned {len(sorted_channels)} channels')
        return jsonify (sorted_channels )

        # ── SECURITY THREAT DASHBOARD & LOCKDOWN API ─────────────────────────────

    @app .route ('/api/security/threat-index',methods =['GET'])
    @login_required 
    def api_threat_index ():
        import datetime as _dt ,json as _json 
        guild_id =request .args .get ('guild_id',str (MAIN_GUILD_ID ))

        # 1. Check warnings in last 24 hours
        warn_count =0 
        if os .path .exists ('data/warnings.json'):
            try :
                with open ('data/warnings.json','r',encoding ='utf-8')as _fp :
                    _wd =_json .load (_fp )
                for _uid ,_ws in _wd .get (str (guild_id ),{}).items ():
                    warn_count +=len (_ws )
            except Exception:
                pass 

                # 2. Check mod cases
        mod_count =0 
        if os .path .exists ('data/mod_data.json'):
            try :
                with open ('data/mod_data.json','r',encoding ='utf-8')as _fp :
                    _md =_json .load (_fp )
                mod_count =len (_md .get ('case',{}).get (str (guild_id ),[]))
            except Exception:
                pass 

                # 3. Check lockdown status
        lockdown_active =False 
        lockdown_file =f'data/lockdown_{guild_id}.json'
        if os .path .exists (lockdown_file ):
            try :
                with open (lockdown_file ,'r',encoding ='utf-8')as _fp :
                    _ld =_json .load (_fp )
                lockdown_active =bool (_ld .get ('active',False ))
            except Exception:
                pass 

                # Calculate score (0-100)
        base_score =5 +min (warn_count *4 ,45 )+min (mod_count *5 ,40 )
        if lockdown_active :
            base_score =max (base_score ,75 )
        threat_score =min (base_score ,100 )

        if threat_score <=25 :
            level ="Низкая угроза (Спокойно)"
            color ="#2ECC71"
        elif threat_score <=60 :
            level ="Повышенная угроза (Внимание)"
            color ="#F1C40F"
        else :
            level ="Критическая угроза (Атака / Рейд)"
            color ="#E74C3C"

        history =[
        {"time":"-4ч","score":max (5 ,threat_score -10 )},
        {"time":"-3ч","score":max (5 ,threat_score -5 )},
        {"time":"-2ч","score":max (5 ,threat_score -8 )},
        {"time":"-1ч","score":max (5 ,threat_score -2 )},
        {"time":"Сейчас","score":threat_score },
        ]

        return jsonify ({
        "success":True ,
        "threat_score":threat_score ,
        "threat_level":level ,
        "threat_color":color ,
        "breakdown":{
        "warnings_recent":warn_count ,
        "mod_cases":mod_count ,
        "lockdown_active":lockdown_active 
        },
        "history":history ,
        "lockdown_active":lockdown_active 
        })

    @app .route ('/api/security/toggle-lockdown',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_toggle_lockdown ():
        import json as _json 
        data =request .get_json (silent =True )or {}
        guild_id =str (data .get ('guild_id',MAIN_GUILD_ID ))
        lockdown_file =f'data/lockdown_{guild_id}.json'
        os .makedirs ('data',exist_ok =True )

        current =False 
        if os .path .exists (lockdown_file ):
            try :
                with open (lockdown_file ,'r',encoding ='utf-8')as _fp :
                    current =bool (_json .load (_fp ).get ('active',False ))
            except Exception:
                pass 

        new_status =not current 
        with open (lockdown_file ,'w',encoding ='utf-8')as _fp :
            _json .dump ({"active":new_status ,"updated_by":session .get ('username')},_fp ,indent =2 )

        status_str ="включён (карантин активен)"if new_status else "отключён (нормальный режим)"
        return jsonify ({
        "success":True ,
        "lockdown_active":new_status ,
        "message":f"🔒 Режим карантина сервера {status_str}!"
        })

        # ── AI API ───────────────────────────────────────────────────────────────

    @app .route ('/api/ai/stream',methods =['POST'])
    @login_required 
    @role_required ('mod')
    def api_ai_stream ():
        from web .ai_helper import ai_assistant 
        d =request .get_json (silent =True )or {}
        message =d .get ('message','').strip ()
        if not message :
            return jsonify ({'error':'Сообщение пусто'}),400 
        username =session .get ('username','anon')
        history_key =f'ai_history_{username}'
        history =session .get (history_key ,[])
        context ={'user_name':username ,'guild_name':'Aether Сервер'}
        answer ,new_history ,model_name ,_ =ai_assistant (message ,context ,history )
        # Храним только последние 6 пар сообщений (user + assistant),
        # чтобы session-cookie не превысил 4KB
        compact =[]
        for m in new_history [-12 :]:
            if m .get ('role')in ('user','assistant'):
                compact .append ({
                'role':m ['role'],
                'content':(m .get ('content')or '')[:500 ],
                })
        session [history_key ]=compact 
        return jsonify ({'ok':True ,'response':answer ,'history':new_history ,'model':model_name })

    @app .route ('/api/ai/assistant',methods =['POST'])
    @login_required 
    @role_required ('mod')
    def api_ai_assistant ():
        from web .ai_helper import ai_assistant 
        d =request .get_json (silent =True )or {}
        message =d .get ('message','').strip ()
        if not message :
            return jsonify ({'error':'Сообщение пусто'}),400 
        username =session .get ('username','anon')
        history_key =f'ai_history_{username}'
        history =session .get (history_key ,[])
        context ={'user_name':username ,'guild_name':'Aether Сервер'}
        answer ,new_history ,model_name ,_ =ai_assistant (message ,context ,history )
        compact =[]
        for m in new_history [-12 :]:
            if m .get ('role')in ('user','assistant'):
                compact .append ({
                'role':m ['role'],
                'content':(m .get ('content')or '')[:500 ],
                })
        session [history_key ]=compact 
        return jsonify ({'ok':True ,'response':answer ,'history':new_history ,'model':model_name })

    @app .route ('/api/ai/clear',methods =['POST'])
    @login_required 
    def api_ai_clear ():
    # Очищаем историю только текущего пользователя
        username =session .get ('username','anon')
        session .pop (f'ai_history_{username}',None )
        return jsonify ({'ok':True })

    @app .route ('/api/ai/announcement',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_ai_announcement ():
        from web .ai_helper import _call_text 
        d =request .get_json (silent =True )or {}
        topic =d .get ('topic','Общее объявление')
        tone =d .get ('tone','официальный')
        prompt = (
            f"Напиши профессиональное объявление для Discord-сервера на тему '{topic}', "
            f"тон: {tone}. Добавь заголовок и эмодзи. До 200 слов."
        )
        messages =[
        {"role":"system","content":"Ты — ассистент, пишущий эффектные объявления для Discord-сервера Aether. Пиши только текст объявления, без пояснений."},
        {"role":"user","content":prompt }
        ]
        announcement =_call_text (messages ,max_tokens =600 )
        return jsonify ({'ok':True ,'text':announcement ,'announcement':announcement ,'result':announcement })

    @app .route ('/api/ai/mod-report',methods =['POST'])
    @login_required 
    @role_required ('mod')
    def api_ai_mod_report ():
        from web .ai_helper import _call_text 
        import os ,json 
        warn_count =0 
        if os .path .exists ('data/warnings.json'):
            try :
                with open ('data/warnings.json','r',encoding ='utf-8')as fp :
                    wd =json .load (fp )
                warn_count =sum (len (v )for gw in wd .values ()for v in gw .values ())
            except Exception:
                pass 
        mod_count =0 
        if os .path .exists ('data/mod_data.json'):
            try :
                with open ('data/mod_data.json','r',encoding ='utf-8')as fp :
                    md =json .load (fp )
                mod_count =sum (len (v )for v in md .get ('case',{}).values ())
            except Exception:
                pass 
        prompt =(
        f"Сводная информация о модерации сервера:\n"
        f"- Всего записанных предупреждений: {warn_count}\n"
        f"- Всего случаев модерации (ban/kick/mute и т.д.): {mod_count}\n"
        f"Напиши краткую, профессиональную недельную оценку модерации с рекомендациями для администраторов."
        )
        messages =[
        {"role":"system","content":"Ты — профессиональный аналитик модерации. Составляешь краткие информативные отчёты."},
        {"role":"user","content":prompt }
        ]
        report =_call_text (messages ,max_tokens =700 )
        return jsonify ({'ok':True ,'report':report ,'text':report ,'result':report })

    @app .route ('/api/ai/embed',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_ai_embed ():
        from web .ai_helper import _call_text 
        d =request .get_json (silent =True )or {}
        prompt =d .get ('prompt','Правила сервера embedi')
        messages =[
        {"role":"system","content":"Ты ассистент-дизайнер Discord-эмбедов. Придумай подходящие теме заголовок и описание эмбеда."},
        {"role":"user","content":prompt }
        ]
        res =_call_text (messages ,max_tokens =400 )
        embed_data ={
        "title":f"📌 {prompt.title()}",
        "description":res ,
        "color":"#dc143c"
        }
        return jsonify ({'ok':True ,'embed':embed_data })

        # ── CHAT API ─────────────────────────────────────────────────────────────

    @app .route ('/api/chat/<guild_id>/<channel_id>/messages')
    @login_required 
    @role_required ('owner')
    def api_chat_messages (guild_id ,channel_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio 
        if not bot :return jsonify ({'error':'Бот офлайн'}),503 
        channel =bot .get_channel (int (channel_id ))
        if not channel :return jsonify ({'error':'Канал не найден'}),404 
        async def _fetch ():
            msgs =[]
            async for m in channel .history (limit =50 ,oldest_first =False ):
                msgs .append ({
                'id':str (m .id ),
                'content':m .content ,
                'author':m .author .display_name ,
                'author_id':str (m .author .id ),
                'avatar':str (m .author .display_avatar .url ),
                'bot':m .author .bot ,
                'timestamp':m .created_at .isoformat (),
                'edited':m .edited_at .isoformat ()if m .edited_at else None ,
                'attachments':[a .url for a in m .attachments ],
                'embeds':len (m .embeds )>0 ,
                })
            return list (reversed (msgs ))
        try :
            msgs =asyncio .run_coroutine_threadsafe (_fetch (),bot .loop ).result (timeout =10 )
            return jsonify (msgs )
        except Exception as e :
            return jsonify ({'error':str (e )}),500 

    @app .route ('/api/chat/<guild_id>/<channel_id>/send',methods =['POST'])
    @login_required 
    @role_required ('owner')
    def api_chat_send (guild_id ,channel_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio 
        if not bot :return jsonify ({'error':'Бот офлайн'}),503 
        channel =bot .get_channel (int (channel_id ))
        if not channel :return jsonify ({'error':'Канал не найден'}),404 
        d =request .get_json (silent =True )or {}
        content =d .get ('content','').strip ()
        if not content :return jsonify ({'error':'Сообщение пусто'}),400 
        def _send ():
            _run_async (channel .send (content ))
        try :
            asyncio .run_coroutine_threadsafe (_send (),bot .loop ).result (timeout =10 )
            return jsonify ({'ok':True })
        except Exception as e :
            return jsonify ({'error':str (e )}),500 

    @app .route ('/api/chat/<guild_id>/<channel_id>/delete/<message_id>',methods =['POST'])
    @login_required 
    @role_required ('owner')
    def api_chat_delete (guild_id ,channel_id ,message_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio 
        if not bot :return jsonify ({'error':'Бот офлайн'}),503 
        channel =bot .get_channel (int (channel_id ))
        if not channel :return jsonify ({'error':'Канал не найден'}),404 
        def _delete ():
            msg =_run_async (channel .fetch_message (int (message_id )))
            _run_async (msg .delete ())
        try :
            asyncio .run_coroutine_threadsafe (_delete (),bot .loop ).result (timeout =10 )
            return jsonify ({'ok':True })
        except Exception as e :
            return jsonify ({'error':str (e )}),500 

    @app .route ('/api/chat/<guild_id>/members')
    @login_required 
    @role_required ('owner')
    def api_chat_members (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        if not bot :return jsonify ([])
        guild =bot .get_guild (int (guild_id ))
        if not guild :return jsonify ([])
        return jsonify ([{
        'id':str (m .id ),
        'name':m .display_name ,
        'display_name':m .display_name ,
        'avatar':str (m .display_avatar .url )if m .display_avatar else '',
        'mention':f'<@{m.id}>'
        }for m in guild .members if not m .bot ][:200 ])

        # ── DM API ───────────────────────────────────────────────────────────────
    DM_LOG_FILE ='data/dm_log.json'

    def _load_dm_log ():
        if os .path .exists (DM_LOG_FILE ):
            try :
                with open (DM_LOG_FILE ,'r',encoding ='utf-8')as f :
                    return json .load (f )
            except Exception:pass 
        return {}

    def _save_dm_log (data ):
        os .makedirs ('data',exist_ok =True )
        with open (DM_LOG_FILE ,'w',encoding ='utf-8')as f :
            json .dump (data ,f ,ensure_ascii =False ,indent =2 )

    @app .route ('/api/dm/<guild_id>/recent')
    @login_required 
    @role_required ('mod')
    def api_dm_recent (guild_id ):
        """Список последних DM-разговоров"""
        import web .app as _app ;bot =_app .bot_instance 
        log =_load_dm_log ()
        result =[]
        for uid ,msgs in log .items ():
            if not msgs :continue 
            last =msgs [-1 ]
            name =uid 
            avatar =''
            if bot :
                for g in bot .guilds :
                    try :
                        m =g .get_member (int (uid ))
                        if m :
                            name =m .display_name 
                            avatar =str (m .display_avatar .url )if m .display_avatar else ''
                            break 
                    except Exception:pass 
            result .append ({
            'id':uid ,
            'name':name ,
            'avatar':avatar ,
            'last_msg':last .get ('content','')[:50 ],
            'timestamp':last .get ('timestamp',''),
            'unread':0 ,
            })
        result .sort (key =lambda x :x ['timestamp'],reverse =True )
        return jsonify (result [:20 ])

    @app .route ('/api/dm/<guild_id>/<user_id>/messages')
    @login_required 
    @role_required ('mod')
    def api_dm_messages (guild_id ,user_id ):
        log =_load_dm_log ()
        msgs =log .get (user_id ,[])
        return jsonify (msgs )

    @app .route ('/api/dm/<guild_id>/<user_id>/send',methods =['POST'])
    @login_required 
    @role_required ('mod')
    def api_dm_send (guild_id ,user_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio as _asyncio ,datetime as _dt2 
        if not bot :return jsonify ({'error':'Бот офлайн'}),503 
        data =request .get_json (silent =True )or {}
        content =data .get ('content','').strip ()
        if not content :return jsonify ({'error':'Сообщение пусто'}),400 

        async def do ():
            user =await (bot .fetch_user (int (user_id )))
            await (user .send (content ))
            return str (user )

        try :
            _asyncio .run_coroutine_threadsafe (do (),bot .loop ).result (timeout =10 )
            # Сохранить в лог
            log =_load_dm_log ()
            if user_id not in log :log [user_id ]=[]
            log [user_id ].append ({
            'author':session .get ('username','Panel'),
            'content':content ,
            'timestamp':_dt2 .datetime.now(timezone.utc).replace(tzinfo=None).isoformat (),
            'from_bot':True ,
            })
            _save_dm_log (log )
            return jsonify ({'ok':True })
        except Exception as e :
            return jsonify ({'error':str (e )}),500 

    @app .route ('/api/guild/<guild_id>/channels/create',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_create_channel (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio ,discord 
        if not bot :return jsonify ({'error':'Бот офлайн'})
        data =request .get_json (silent =True )or {}
        async def do ():
            guild =bot .get_guild (int (guild_id ))
            t =data .get ('type','text')
            name =str (data .get ('name','') or '').strip ()
            if not name :
                raise ValueError ('Название канала обязательно')
            kwargs ={}
            cat_name =data .get ('category','')
            if cat_name :
                cat =None 
                for c in guild .channels :
                    if c .type ==discord .ChannelType .category and c .name ==cat_name :
                        cat =c 
                        break 
                if cat is None :
                    cat =await (guild .create_category (cat_name ))
                kwargs ['category']=cat 
            topic =data .get ('topic','')
            if topic :
                kwargs ['topic']=str (topic )[:1024 ]
            slowmode =data .get ('slowmode',0 )
            if slowmode :
                kwargs ['slowmode_delay']=int (slowmode )
            nsfw =data .get ('nsfw',False )
            if nsfw :
                kwargs ['nsfw']=True 
            if t =='text':
                await (guild .create_text_channel (name ,**kwargs ))
            elif t =='voice':
                vkw =dict (kwargs )
                bitrate =data .get ('bitrate',0 )
                if bitrate :
                    vkw ['bitrate']=min (int (bitrate )* 1000 ,guild .bitrate_limit )
                ulimit =data .get ('user_limit',0 )
                if ulimit :
                    vkw ['user_limit']=int (ulimit )
                await (guild .create_voice_channel (name ,**vkw ))
            elif t =='category':
                await (guild .create_category (name ))
        try :
            asyncio .run_coroutine_threadsafe (do (),bot .loop ).result (timeout =10 )
            return jsonify ({'success':True })
        except Exception as e :
            return jsonify ({'success':False ,'error':str (e )})

    @app .route ('/api/guild/<guild_id>/channels/<channel_id>/update',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_update_channel (guild_id ,channel_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio ,discord 
        if not bot :return jsonify ({'error':'Бот офлайн'})
        data =request .get_json (silent =True )or {}
        async def do ():
            guild =bot .get_guild (int (guild_id ))
            ch =guild .get_channel (int (channel_id ))
            if not ch :
                raise ValueError ('Канал не найден')
            # Переименование
            if 'name' in data and data ['name']:
                await (ch .edit (name =str (data ['name'])[:100 ]))
            # Тема / topic (текстовые каналы)
            if 'topic' in data :
                await (ch .edit (topic =str (data ['topic'] or '')[:1024 ]))
            # NSFW
            if 'nsfw' in data :
                await (ch .edit (nsfw =bool (data ['nsfw'])))
            # Slowmode (текстовые каналы)
            if 'slowmode' in data :
                await (ch .edit (slowmode_delay =int (data ['slowmode'] or 0 )))
            # Битрейт (голосовые каналы)
            if 'bitrate' in data :
                br =min (int (data ['bitrate'] or 0 )* 1000 ,guild .bitrate_limit )
                await (ch .edit (bitrate =br ))
            # Лимит участников (голосовые каналы)
            if 'user_limit' in data :
                await (ch .edit (user_limit =int (data ['user_limit'] or 0 )))
            # Перенос в категорию
            if 'category' in data :
                cat_name =data ['category']
                if cat_name :
                    cat =None 
                    for c in guild .channels :
                        if c .type ==discord .ChannelType .category and c .name ==cat_name :
                            cat =c 
                            break 
                    if cat is None :
                        cat =await (guild .create_category (cat_name ))
                    await (ch .edit (category =cat ))
                else :
                    await (ch .edit (category =None ))
            # Позиция
            if 'position' in data :
                await (ch .edit (position =int (data ['position'])))
        try :
            asyncio .run_coroutine_threadsafe (do (),bot .loop ).result (timeout =10 )
            return jsonify ({'success':True })
        except Exception as e :
            return jsonify ({'success':False ,'error':str (e )})


    @app .route ('/api/guild/<guild_id>/channels/<channel_id>/delete',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_delete_channel (guild_id ,channel_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio 
        if not bot :return jsonify ({'error':'Бот офлайн'})
        async def do ():
            ch =bot .get_channel (int (channel_id ))
            if ch :await (ch .delete ())
        asyncio .run_coroutine_threadsafe (do (),bot .loop ).result (timeout =10 )
        return jsonify ({'success':True })

    @app .route ('/api/guild/<guild_id>/welcome-settings',methods =['GET','POST'])
    @login_required 
    @role_required ('admin')
    def api_welcome_settings (guild_id ):
        f =f'data/welcome_{guild_id}.json'
        os .makedirs ('data',exist_ok =True )# Enдлительность data directory exists

        if request .method =='GET':
            if not os .path .exists (f ):
                return jsonify ({})
            try :
                with open (f ,'r',encoding ='utf-8')as fp :
                    return jsonify (json .load (fp ))
            except Exception as e :
                print (f'[WEB][ERR] welcome-settings GET error: {e}')
                return jsonify ({'error':str (e )})

                # POST request
        try :
            data =request .get_json (silent =True )or {}
            if not data :
                return jsonify ({'error':'Данные не переданы'})

            settings ={}
            if os .path .exists (f ):
                with open (f ,'r',encoding ='utf-8')as fp :
                    settings =json .load (fp )

            t =data .pop ('type',None )
            if not t :
                return jsonify ({'error':'Тип заметок не указан'})

            settings [t ]=data 
            with open (f ,'w',encoding ='utf-8')as fp :
                json .dump (settings ,fp ,indent =2 ,ensure_ascii =False )
            print (f'[WEB] welcome-settings saved for guild {guild_id}, type {t}')
            return jsonify ({'success':True })
        except Exception as e :
            print (f'[WEB][ERR] welcome-settings POST error: {e}')
            return jsonify ({'error':str (e )})

    @app .route ('/api/guild/<guild_id>/autorole',methods =['GET','POST'])
    @login_required 
    @role_required ('admin')
    def api_autorole (guild_id ):
        f =f'data/autorole_{guild_id}.json'
        if request .method =='GET':
            if not os .path .exists (f ):
                return jsonify ({'member_roles':[],'girl_roles':[],'boy_roles':[],'bot_roles':[]})
            with open (f )as fp :
                data =json .load (fp )
                # Старый format uyumluluгu
            data .setdefault ('girl_roles',[])
            data .setdefault ('boy_roles',[])
            return jsonify (data )
        data =request .get_json (silent =True )or {}
        settings ={}
        if os .path .exists (f ):
            with open (f ,encoding ='utf-8')as fp :settings =json .load (fp )
            # type -> key mapping
        key_map ={'member':'member_roles','girl':'girl_roles','boy':'boy_roles','bot':'bot_roles'}
        t =data .get ('type','member')
        key =key_map .get (t ,t +'_roles')
        # Frontend hem 'roles' (чoгul) hem 'role' (tekil) yollayabilir; ikisini de принять et
        new_value =data .get ('roles',data .get ('role',[]))
        if not isinstance (new_value ,list ):
            new_value =[]
            # Оставить только строковые id
        new_value =[str (x )for x in new_value if x ]
        settings [key ]=new_value 
        os .makedirs ('data',exist_ok =True )
        with open (f ,'w',encoding ='utf-8')as fp :json .dump (settings ,fp ,indent =2 ,ensure_ascii =False )
        return jsonify ({'success':True ,'key':key ,'value':new_value })

    @app .route ('/api/guild/<guild_id>/leveling',methods =['GET','POST'])
    @login_required 
    @role_required ('mod')
    def api_leveling (guild_id ):
        f =f'data/leveling_{guild_id}.json'
        if request .method =='GET':
            if not os .path .exists (f ):return jsonify ({'enabled':False ,'xp_min':15 ,'xp_max':25 })
            with open (f )as fp :return jsonify (json .load (fp ))
        data =request .get_json (silent =True )or {}
        with open (f ,'w')as fp :json .dump (data ,fp ,indent =2 )
        return jsonify ({'success':True })

    @app .route ('/api/guild/<guild_id>/leaderboard')
    @login_required 
    def api_leaderboard (guild_id ):
        f =f'data/xp_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ([])
        with open (f )as fp :data =json .load (fp )
        lb =sorted (data .values (),key =lambda x :x .get ('xp',0 ),reverse =True )
        return jsonify (lb [:20 ])

    @app .route ('/api/guild/<guild_id>/economy',methods =['GET','POST'])
    @login_required 
    @role_required ('admin')
    def api_economy (guild_id ):
        f =f'data/economy_{guild_id}.json'
        if request .method =='GET':
            if not os .path .exists (f ):return jsonify ({'currency_name':'Coin','currency_emoji':'💰','start_balance':100 ,'daily_reward':50 })
            with open (f )as fp :return jsonify (json .load (fp ))
        data =request .get_json (silent =True )or {}
        with open (f ,'w')as fp :json .dump (data ,fp ,indent =2 )
        return jsonify ({'success':True })

    @app .route ('/api/guild/<guild_id>/economy/shop')
    @login_required 
    def api_economy_shop (guild_id ):
        f =f'data/shop_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ([])
        with open (f )as fp :return jsonify (json .load (fp ))

    @app .route ('/api/guild/<guild_id>/economy/shop/add',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_economy_shop_add (guild_id ):
        f =f'data/shop_{guild_id}.json'
        items =[]
        if os .path .exists (f ):
            with open (f )as fp :items =json .load (fp )
        data =request .get_json (silent =True )or {}
        data ['id']=str (int (datetime.now(timezone.utc).replace(tzinfo=None).timestamp ()))
        items .append (data )
        with open (f ,'w')as fp :json .dump (items ,fp ,indent =2 )
        return jsonify ({'success':True })

    @app .route ('/api/guild/<guild_id>/economy/shop/<item_id>/remove',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_economy_shop_remove (guild_id ,item_id ):
        f =f'data/shop_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ({'success':True })
        with open (f )as fp :items =json .load (fp )
        items =[i for i in items if i .get ('id')!=item_id ]
        with open (f ,'w')as fp :json .dump (items ,fp ,indent =2 )
        return jsonify ({'success':True })

    @app .route ('/api/guild/<guild_id>/economy/rich')
    @login_required 
    def api_economy_rich (guild_id ):
        f =f'data/balance_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ([])
        with open (f )as fp :data =json .load (fp )
        return jsonify (sorted (data .values (),key =lambda x :x .get ('balance',0 ),reverse =True )[:10 ])

    @app .route ('/api/guild/<guild_id>/giveaways')
    @login_required 
    def api_giveaways (guild_id ):
        f =f'data/giveaways_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ([])
        with open (f )as fp :return jsonify (list (json .load (fp ).values ()))

    @app .route ('/api/guild/<guild_id>/giveaways/create',methods =['POST'])
    @login_required 
    @role_required ('mod')
    def api_create_giveaway (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio ,discord 
        if not bot :return jsonify ({'error':'Бот офлайн'})
        data =request .get_json (silent =True )or {}
        gw_id =str (int (datetime.now(timezone.utc).replace(tzinfo=None).timestamp ()))
        from datetime import timedelta 
        ends_at =(datetime.now(timezone.utc).replace(tzinfo=None)+timedelta (minutes =data ['duration'])).isoformat ()
        f =f'data/giveaways_{guild_id}.json'
        gws ={}
        if os .path .exists (f ):
            with open (f )as fp :gws =json .load (fp )
        gws [gw_id ]={
        'id':gw_id ,
        'prize':data ['prize'],
        'winners':data ['winners'],
        'ends_at':ends_at ,
        'status':'active',
        'channel_id':data ['channel_id'],
        'participants':[],
        'message_id':None 
        }
        with open (f ,'w',encoding ='utf-8')as fp :json .dump (gws ,fp ,indent =2 ,ensure_ascii =False )
        def send ():
            from cogs .giveaway import GiveawayView 
            ch =bot .get_channel (int (data ['channel_id']))
            if ch :
                end_ts =int (datetime.now(timezone.utc).replace(tzinfo=None).timestamp ())+int (data ['duration'])*60 
                embed =discord .Embed (
                title ='🎉 ✨ НАЧАЛСЯ ЗАМЕЧАТЕЛЬНЫЙ РОЗЫГРЫШ! ✨ 🎉',
                description =(
                f"\n🏆 **НАГРАДА:** `{data['prize']}`\n"
                "\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "🎟️ **Чтобы участвовать:** нажми кнопку 🎉 **«Участвовать»** ниже\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"\n⏳ **Время завершения:** <t:{end_ts}:R>\n"
                f"📅 **Точное время:** <t:{end_ts}:f>\n"
                "\n✅ Участие абсолютно **БЕСПЛАТНО** и **ОТКРЫТО**!\n"
                "🍀 Испытай удачу и **ВЫИГРАЙ**! 🍀\n"
                ),
                color =0xFFD700 
                )
                embed .add_field (name ='🏅 Количество победителей',value =f'**{data["winners"]} ЧЕЛОВЕК ВЫИГРАЕТ!** 👑',inline =False )
                embed .add_field (name ='👥 Текущие участники',value =f'**0/{data["winners"]}** 🔥',inline =True )
                embed .add_field (name ='📊 Статистика',value ='Открывается...',inline =True )
                embed .set_footer (text =f'🎯 Giveaway ID: {gw_id} | Система: Bot Giveaway v2')
                view =GiveawayView (gw_id ,guild_id )
                msg =_run_async (ch .send (embed =embed ,view =view ))
                gws [gw_id ]['message_id']=str (msg .id )
                with open (f ,'w',encoding ='utf-8')as fp :
                    json .dump (gws ,fp ,indent =2 ,ensure_ascii =False )
        asyncio .run_coroutine_threadsafe (send (),bot .loop )
        return jsonify ({'success':True })

    @app .route ('/api/guild/<guild_id>/giveaways/<gw_id>/end',methods =['POST'])
    @login_required 
    @role_required ('mod')
    def api_end_giveaway (guild_id ,gw_id ):
        f =f'data/giveaways_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ({'error':'Не найдено'})
        with open (f )as fp :gws =json .load (fp )
        if gw_id in gws :
            gws [gw_id ]['status']='ended'
            with open (f ,'w')as fp :json .dump (gws ,fp ,indent =2 )
        return jsonify ({'success':True })

    @app .route ('/api/guild/<guild_id>/giveaways/<gw_id>/join',methods =['POST'])
    @login_required 
    def api_join_giveaway (guild_id ,gw_id ):
        f =f'data/giveaways_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ({'error':'Розыгрыш не найден'})
        with open (f )as fp :gws =json .load (fp )
        if gw_id not in gws :return jsonify ({'error':'Розыгрыш не найден'})
        gw =gws [gw_id ]
        if gw .get ('status')!='active':return jsonify ({'error':'Розыгрыш не активен'})
        participants =gw .setdefault ('participants',[])
        username =session .get ('username','')
        if username in participants :return jsonify ({'error':'Ты уже присоединился!'})
        participants .append (username )
        with open (f ,'w')as fp :json .dump (gws ,fp ,indent =2 )
        return jsonify ({'success':True })

    @app .route ('/api/guild/<guild_id>/polls')
    @login_required 
    def api_polls (guild_id ):
        f =f'data/polls_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ([])
        with open (f )as fp :return jsonify (list (json .load (fp ).values ()))

    @app .route ('/api/guild/<guild_id>/polls/<poll_id>/vote',methods =['POST'])
    @login_required 
    @role_required ('mod')
    def api_vote_poll (guild_id ,poll_id ):
        f =f'data/polls_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ({'error':'Опрос не найден'})
        with open (f ,encoding ='utf-8')as fp :polls =json .load (fp )
        if poll_id not in polls :return jsonify ({'error':'Опрос не найден'})
        data =request .get_json (silent =True )or {}
        option_index =data .get ('option_index',0 )
        poll =polls [poll_id ]
        voters =poll .setdefault ('voters',[])
        username =session .get ('username','')
        if username in voters :return jsonify ({'error':'Ты уже голосовал!'})
        if 0 <=option_index <len (poll ['options']):
            poll ['options'][option_index ]['votes']=poll ['options'][option_index ].get ('votes',0 )+1 
            voters .append (username )
            with open (f ,'w',encoding ='utf-8')as fp :json .dump (polls ,fp ,indent =2 ,ensure_ascii =False )
            return jsonify ({'success':True })
        return jsonify ({'error':'Неверный выбрать'})

    @app .route ('/api/guild/<guild_id>/polls/create',methods =['POST'])
    @login_required 
    @role_required ('owner')
    def api_create_poll (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio ,discord 
        if not bot :return jsonify ({'error':'Бот офлайн'})
        data =request .get_json (silent =True )or {}
        poll_id =str (int (datetime.now(timezone.utc).replace(tzinfo=None).timestamp ()))
        f =f'data/polls_{guild_id}.json'
        polls ={}
        if os .path .exists (f ):
            with open (f )as fp :polls =json .load (fp )
        entry ={'id':poll_id ,'question':data ['question'],'created_at':datetime.now(timezone.utc).replace(tzinfo=None).isoformat (),
        'options':[{'emoji':o ['emoji'],'text':o ['text'],'votes':0 }for o in data ['options']]}
        polls [poll_id ]=entry 
        with open (f ,'w')as fp :json .dump (polls ,fp ,indent =2 )
        def send ():
            ch =bot .get_channel (int (data ['channel_id']))
            if ch :
                desc ='\n'.join ([f"{o['emoji']} **{o['text']}**"for o in data ['options']])
                embed =discord .Embed (title =f"📊 {data['question']}",description =desc ,color =0xdc143c )
                embed .set_footer (text =f"ID опроса: {poll_id}")
                msg =_run_async (ch .send (embed =embed ))
                for o in data ['options']:
                    try :_run_async (msg .add_reaction (o ['emoji']))
                    except Exception:pass 
        asyncio .run_coroutine_threadsafe (send (),bot .loop )
        return jsonify ({'success':True })

    @app .route ('/api/guild/<guild_id>/custom-commands')
    @login_required 
    def api_custom_commands (guild_id ):
        f =f'data/custom_cmds_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ([])
        with open (f )as fp :return jsonify (list (json .load (fp ).values ()))

    @app .route ('/api/guild/<guild_id>/custom-commands/create',methods =['POST'])
    @login_required 
    @role_required ('owner')
    def api_create_custom_command (guild_id ):
        data =request .get_json (silent =True )or {}
        f =f'data/custom_cmds_{guild_id}.json'
        cmds ={}
        if os .path .exists (f ):
            with open (f )as fp :cmds =json .load (fp )
        cmd_id =str (int (datetime.now(timezone.utc).replace(tzinfo=None).timestamp ()))
        cmds [cmd_id ]={'id':cmd_id ,'trigger':data ['trigger'],'response':data ['response'],
        'type':data .get ('type','text'),'uses':0 ,'created_at':datetime.now(timezone.utc).replace(tzinfo=None).isoformat ()}
        with open (f ,'w')as fp :json .dump (cmds ,fp ,indent =2 )
        return jsonify ({'success':True })

    @app .route ('/api/guild/<guild_id>/custom-commands/<cmd_id>/delete',methods =['POST'])
    @login_required 
    @role_required ('owner')
    def api_delete_custom_command (guild_id ,cmd_id ):
        f =f'data/custom_cmds_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ({'success':True })
        with open (f )as fp :cmds =json .load (fp )
        cmds .pop (cmd_id ,None )
        with open (f ,'w')as fp :json .dump (cmds ,fp ,indent =2 )
        return jsonify ({'success':True })

    @app .route ('/api/guild/<guild_id>/scheduled-messages')
    @login_required 
    def api_scheduled_messages (guild_id ):
        f =f'data/scheduled_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ([])
        with open (f )as fp :return jsonify (list (json .load (fp ).values ()))

    @app .route ('/api/guild/<guild_id>/scheduled-messages/create',methods =['POST'])
    @login_required 
    @role_required ('mod')
    def api_create_scheduled_message (guild_id ):
        data =request .get_json (silent =True )or {}
        f =f'data/scheduled_{guild_id}.json'
        msgs ={}
        if os .path .exists (f ):
            with open (f )as fp :msgs =json .load (fp )
        msg_id =str (int (datetime.now(timezone.utc).replace(tzinfo=None).timestamp ()))
        msgs [msg_id ]={'id':msg_id ,'channel_id':data ['channel_id'],'channel_name':'',
        'content':data ['content'],'interval':data ['interval'],
        'next_run':data .get ('start_time',datetime.now(timezone.utc).replace(tzinfo=None).isoformat ()),
        'active':True ,'created_at':datetime.now(timezone.utc).replace(tzinfo=None).isoformat ()}
        with open (f ,'w')as fp :json .dump (msgs ,fp ,indent =2 )
        return jsonify ({'success':True })

    @app .route ('/api/guild/<guild_id>/scheduled-messages/<msg_id>/delete',methods =['POST'])
    @login_required 
    @role_required ('mod')
    def api_delete_scheduled_message (guild_id ,msg_id ):
        f =f'data/scheduled_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ({'success':True })
        with open (f )as fp :msgs =json .load (fp )
        msgs .pop (msg_id ,None )
        with open (f ,'w')as fp :json .dump (msgs ,fp ,indent =2 )
        return jsonify ({'success':True })

    @app .route ('/api/guild/<guild_id>/scheduled-messages/<msg_id>/toggle',methods =['POST'])
    @login_required 
    @role_required ('mod')
    def api_toggle_scheduled_message (guild_id ,msg_id ):
        f =f'data/scheduled_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ({'success':False ,'error':'Не найдено'}),404
        with open (f )as fp :msgs =json .load (fp )
        if msg_id not in msgs :
            return jsonify ({'success':False ,'error':'Не найдено'}),404
        msgs [msg_id ]['active']=not bool (msgs [msg_id ].get ('active',True ))
        with open (f ,'w')as fp :json .dump (msgs ,fp ,indent =2 )
        return jsonify ({'success':True ,'active':msgs [msg_id ]['active']})

    @app .route ('/api/member-notes')
    @login_required 
    @role_required ('mod')
    def api_all_member_notes ():
        f ='data/member_notes.json'
        if not os .path .exists (f ):return jsonify ([])
        try :
            with open (f ,encoding ='utf-8')as fp :data =json .load (fp )
        except (json .JSONDecodeError ,ValueError ):
            return jsonify ([])
        return jsonify ([{'id':k ,'name':v .get ('name',k ),'avatar':v .get ('avatar',''),'notes':v .get ('notes',[])}for k ,v in data .items ()if v .get ('notes')])

    @app .route ('/api/member-notes/<member_id>')
    @login_required 
    @role_required ('mod')
    def api_member_notes (member_id ):
        f ='data/member_notes.json'
        if not os .path .exists (f ):return jsonify ([])
        try :
            with open (f ,encoding ='utf-8')as fp :data =json .load (fp )
        except (json .JSONDecodeError ,ValueError ):
            return jsonify ([])
        return jsonify (data .get (member_id ,{}).get ('notes',[]))

    @app .route ('/api/member-notes/<member_id>/add',methods =['POST'])
    @login_required 
    @role_required ('mod')
    def api_add_member_note (member_id ):
        import web .app as _app ;bot =_app .bot_instance 
        f ='data/member_notes.json'
        data ={}
        if os .path .exists (f ):
            try :
                with open (f ,encoding ='utf-8')as fp :data =json .load (fp )
            except (json .JSONDecodeError ,ValueError ):
                data ={}
        if member_id not in data :
            name =member_id 
            avatar =''
            if bot :
                for g in bot .guilds :
                    m =g .get_member (int (member_id ))
                    if m :
                        name =m .display_name 
                        avatar =str (m .display_avatar .url )
                        break 
            data [member_id ]={'name':name ,'avatar':avatar ,'notes':[]}
        note ={'id':str (int (datetime.now(timezone.utc).replace(tzinfo=None).timestamp ())),'text':request .get_json (silent =True ).get ('text',''),
        'author':session .get ('username'),'created_at':datetime.now(timezone.utc).replace(tzinfo=None).isoformat ()}
        data [member_id ]['notes'].append (note )
        with open (f ,'w',encoding ='utf-8')as fp :json .dump (data ,fp ,indent =2 ,ensure_ascii =False )
        return jsonify ({'success':True })

    @app .route ('/api/member-notes/<member_id>/<note_id>/delete',methods =['POST'])
    @login_required 
    @role_required ('mod')
    def api_delete_member_note (member_id ,note_id ):
        f ='data/member_notes.json'
        if not os .path .exists (f ):return jsonify ({'success':True })
        try :
            with open (f ,encoding ='utf-8')as fp :data =json .load (fp )
        except (json .JSONDecodeError ,ValueError ):
            return jsonify ({'success':True })
        if member_id in data :
            data [member_id ]['notes']=[n for n in data [member_id ]['notes']if n ['id']!=note_id ]
        with open (f ,'w',encoding ='utf-8')as fp :json .dump (data ,fp ,indent =2 ,ensure_ascii =False )
        return jsonify ({'success':True })

    @app .route ('/api/guild/<guild_id>/purge',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_purge (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio 
        if not bot :return jsonify ({'error':'Бот офлайн'})
        data =request .get_json (silent =True )or {}
        result ={'count':0 }
        async def do ():
            ch =bot .get_channel (int (data ['channel_id']))
            if ch :
                deleted =await (ch .purge (limit =int (data .get ('count',10 ))))
                result ['count']=len (deleted )
        asyncio .run_coroutine_threadsafe (do (),bot .loop ).result (timeout =30 )
        return jsonify ({'success':True ,'count':result ['count']})

    @app .route ('/api/guild/<guild_id>/bulk-roles',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_bulk_role (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio ,discord 
        if not bot :return jsonify ({'error':'Бот офлайн'})
        data =request .get_json (silent =True )or {}
        result ={'count':0 }
        async def do ():
            guild =bot .get_guild (int (guild_id ))
            target_role =guild .get_role (int (data ['target_role']))
            action_role =guild .get_role (int (data ['action_role']))
            if not target_role or not action_role :return 
            for member in target_role .members :
                try :
                    if data ['action']=='add':await (member .add_roles (action_role ))
                    else :await (member .remove_roles (action_role ))
                    result ['count']+=1 
                except Exception:pass 
        asyncio .run_coroutine_threadsafe (do (),bot .loop ).result (timeout =60 )
        return jsonify ({'success':True ,'count':result ['count']})

    @app .route ('/api/guild/<guild_id>/bulk-dm',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_bulk_dm (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio ,discord 
        if not bot :return jsonify ({'error':'Бот офлайн'})
        data =request .get_json (silent =True )or {}
        result ={'count':0 }
        async def do ():
            guild =bot .get_guild (int (guild_id ))
            role =guild .get_role (int (data ['role_id']))
            if not role :return 
            embed =discord .Embed (title ="📢 Объявление",description =data ['message'],color =0xdc143c )
            embed .set_footer (text ="Aether Panel",icon_url =bot .user .display_avatar .url )
            for member in role .members :
                try :
                    await (member .send (embed =embed ))
                    result ['count']+=1 
                except Exception:pass 
        asyncio .run_coroutine_threadsafe (do (),bot .loop ).result (timeout =120 )
        return jsonify ({'success':True ,'count':result ['count']})

    @app .route ('/api/guild/<guild_id>/bulk-mute',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_bulk_mute (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio ,discord 
        from datetime import timedelta 
        if not bot :return jsonify ({'error':'Бот офлайн'})
        data =request .get_json (silent =True )or {}
        result ={'count':0 }
        async def do ():
            guild =bot .get_guild (int (guild_id ))
            role =guild .get_role (int (data ['role_id']))
            if not role :return 
            duration =int (data .get ('duration',60 ))
            for member in role .members :
                try :
                    await (member .timeout (discord .utils .utcnow ()+timedelta (minutes =duration ),reason ='Bulk mute'))
                    result ['count']+=1 
                except Exception:pass 
        asyncio .run_coroutine_threadsafe (do (),bot .loop ).result (timeout =120 )
        return jsonify ({'success':True ,'count':result ['count']})

    @app .route ('/api/guild/<guild_id>/bulk-kick',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_bulk_kick (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio ,discord 
        if not bot :return jsonify ({'error':'Бот офлайн'})
        data =request .get_json (silent =True )or {}
        result ={'count':0 }
        async def do ():
            guild =bot .get_guild (int (guild_id ))
            role =guild .get_role (int (data ['role_id']))
            if not role :return 
            for member in role .members :
                try :
                    await (member .kick (reason ='Bulk kick'))
                    result ['count']+=1 
                except Exception:pass 
        asyncio .run_coroutine_threadsafe (do (),bot .loop ).result (timeout =120 )
        return jsonify ({'success':True ,'count':result ['count']})

    @app .route ('/api/guild/<guild_id>/bulk-ban',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_bulk_ban (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio ,discord 
        if not bot :return jsonify ({'error':'Бот офлайн'})
        data =request .get_json (silent =True )or {}
        result ={'count':0 }
        async def do ():
            guild =bot .get_guild (int (guild_id ))
            role =guild .get_role (int (data ['role_id']))
            if not role :return 
            for member in role .members :
                try :
                    await (guild .ban (member ,reason ='Bulk ban'))
                    result ['count']+=1 
                except Exception:pass 
        asyncio .run_coroutine_threadsafe (do (),bot .loop ).result (timeout =180 )
        return jsonify ({'success':True ,'count':result ['count']})

        # ── WARN CONFIG API ───────────────────────────────────────────────────────

    @app .route ('/api/guild/<guild_id>/warn-config',methods =['GET','POST'])
    @login_required 
    @role_required ('admin')
    def api_warn_config (guild_id ):
        f =f'data/warn_config_{guild_id}.json'
        if request .method =='GET':
            if not os .path .exists (f ):
                return jsonify ({'steps':[]})
            with open (f ,'r',encoding ='utf-8')as fp :
                return jsonify (json .load (fp ))
        data =request .get_json (silent =True )or {}
        os .makedirs ('data',exist_ok =True )
        with open (f ,'w',encoding ='utf-8')as fp :
            json .dump (data ,fp ,indent =2 ,ensure_ascii =False )
        return jsonify ({'success':True })

        # ── WARN DM НАСТРОЙКА ─────────────────────────────────────────────────────────

    @app .route ('/api/guild/<guild_id>/warn-dm',methods =['GET','POST'])
    @login_required 
    @role_required ('admin')
    def api_warn_dm (guild_id ):
        f =f'data/warn_dm_{guild_id}.json'
        if request .method =='GET':
            if not os .path .exists (f ):
                return jsonify ({'message':''})
            with open (f ,'r',encoding ='utf-8')as fp :
                return jsonify (json .load (fp ))
        data =request .get_json (silent =True )or {}
        os .makedirs ('data',exist_ok =True )
        with open (f ,'w',encoding ='utf-8')as fp :
            json .dump ({'message':data .get ('message','')},fp ,ensure_ascii =False )
        return jsonify ({'success':True })

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
                        except Exception :
                            pass 

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
                    except Exception :
                        pass 

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
                    except Exception :
                        pass 

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
                except Exception :
                    pass 
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
                            except Exception:
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

    @app .route ('/api/guild/<guild_id>/reaction-roles')
    @login_required 
    def api_reaction_roles (guild_id ):
        f =f'data/rr_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ([])
        with open (f )as fp :return jsonify (list (json .load (fp ).values ()))

    @app .route ('/api/guild/<guild_id>/reaction-roles/create',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_create_reaction_role (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio ,discord 
        if not bot :return jsonify ({'error':'Бот офлайн'})
        data =request .get_json (silent =True )or {}
        rr_id =str (int (datetime.now(timezone.utc).replace(tzinfo=None).timestamp ()))
        f =f'data/rr_{guild_id}.json'
        rrs ={}
        if os .path .exists (f ):
            with open (f )as fp :rrs =json .load (fp )
        guild =bot .get_guild (int (guild_id ))
        ptype =data .get ('type','emoji')# 'emoji' or 'select'
        entries_with_names =[]
        for e in data .get ('entries',[]):
            role =guild .get_role (int (e ['role_id']))if guild else None 
            entries_with_names .append ({'emoji':e .get ('emoji',''),'role_id':e ['role_id'],'role_name':role .name if role else e ['role_id']})
        rrs [rr_id ]={'id':rr_id ,'title':data ['title'],'channel_id':data ['channel_id'],'type':ptype ,'entries':entries_with_names ,'guild_id':str (guild_id )}
        with open (f ,'w')as fp :json .dump (rrs ,fp ,indent =2 )
        def send ():
            ch =bot .get_channel (int (data ['channel_id']))
            if ch :
                desc ='\n'.join ([f"**{e['role_name']}**"for e in entries_with_names ])
                embed =discord .Embed (title =data ['title'],description =desc ,color =0xdc143c )
                if ptype =='select':
                    # Select-menu panel: attach a persistent View via the cog
                    msg =_run_async (ch .send (embed =embed ))
                    try :
                        cog =bot .get_cog ('ReactionRolesCog')
                        if cog and hasattr (cog ,'register_select_panel'):
                            _run_async (cog .register_select_panel (int (msg .id ),rrs [rr_id ]))
                    except Exception :
                        pass 
                else :
                    msg =_run_async (ch .send (embed =embed ))
                    for e in entries_with_names :
                        if e ['emoji']:
                            try :_run_async (msg .add_reaction (e ['emoji']))
                            except Exception:pass 
                rrs [rr_id ]['message_id']=str (msg .id )
                with open (f ,'w')as fp2 :json .dump (rrs ,fp2 ,indent =2 )
        asyncio .run_coroutine_threadsafe (send (),bot .loop )
        return jsonify ({'success':True })

    @app .route ('/api/guild/<guild_id>/reaction-roles/<rr_id>/delete',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_delete_reaction_role (guild_id ,rr_id ):
        f =f'data/rr_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ({'success':True })
        with open (f )as fp :rrs =json .load (fp )
        rrs .pop (rr_id ,None )
        with open (f ,'w')as fp :json .dump (rrs ,fp ,indent =2 )
        return jsonify ({'success':True })

        # ── НОВЫЙ SAYFALAR ─────────────────────────────────────────────────────────

    @app .route ('/ticket-settings')
    @login_required 
    @role_required ('admin')
    def ticket_settings_page ():
        return render_template ('ticket_settings.html',role =session .get ('role'),username =session .get ('username'))

    @app .route ('/automod-settings')
    @login_required 
    @role_required ('admin')
    def automod_settings_page ():
        return render_template ('automod_settings.html',role =session .get ('role'),username =session .get ('username'))

    @app .route ('/antiraid')
    @login_required 
    @role_required ('admin')
    def antiraid_page ():
        return render_template ('antiraid.html',role =session .get ('role'),username =session .get ('username'))

    @app .route ('/rejoin-roles')
    @login_required 
    @role_required ('admin')
    def rejoin_roles_page ():
        return render_template ('rejoin_roles.html',role =session .get ('role'),username =session .get ('username'))

    @app .route ('/backup')
    @login_required 
    @role_required ('owner')
    def backup_page ():
        return render_template ('backup.html',role =session .get ('role'),username =session .get ('username'))

    @app .route ('/panel-logs')
    @login_required 
    @role_required ('admin')
    def panel_logs_page ():
        return render_template ('panel_logs.html',role =session .get ('role'),username =session .get ('username'))

    @app .route ('/message-logs')
    @login_required 
    @role_required ('mod')
    def message_logs_page ():
        return render_template ('message_logs.html',role =session .get ('role'),username =session .get ('username'),main_guild_id =MAIN_GUILD_ID )

    @app .route ('/voice-stats')
    @login_required 
    @role_required ('mod')
    def voice_stats_page ():
        return render_template ('voice_stats.html',role =session .get ('role'),username =session .get ('username'),main_guild_id =MAIN_GUILD_ID )

    @app .route ('/todo')
    @login_required 
    @role_required ('owner')
    def todo_page ():
        return render_template ('todo.html',role =session .get ('role'),username =session .get ('username'))

    @app .route ('/color-roles')
    @login_required 
    @role_required ('owner')
    def color_roles_page ():
        return render_template ('color_roles.html',role =session .get ('role'),username =session .get ('username'),main_guild_id =MAIN_GUILD_ID )

    @app .route ('/rules-editor')
    @login_required 
    @role_required ('admin')
    def rules_editor_page ():
        return render_template ('rules_editor.html',role =session .get ('role'),username =session .get ('username'),main_guild_id =MAIN_GUILD_ID )

        # ── API ROUTES ───────────────────────────────────────────────────────────

    @app .route ('/api/guild/<guild_id>/ticket-settings',methods =['GET','POST'])
    @login_required 
    @role_required ('admin')
    def api_ticket_settings (guild_id ):
        f =f'data/ticket_settings_{guild_id}.json'
        if request .method =='GET':
            if not os .path .exists (f ):return jsonify ({})
            with open (f )as fp :return jsonify (json .load (fp ))
        data =request .get_json (silent =True )or {}
        with open (f ,'w')as fp :json .dump (data ,fp ,indent =2 )
        # Panel сообщение отправить
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio ,discord 
        from cogs .ticket import TicketView 
        panel_sent =False 
        panel_error =None 
        if bot and data .get ('ticket_channel_id'):
            def send_panel ():
                ch =bot .get_channel (int (data ['ticket_channel_id']))
                if not ch :
                    raise ValueError (f"Канал не найден: {data['ticket_channel_id']}")
                embed =discord .Embed (
                title =data .get ('title','🎫  ПОДДЕРЖКА СИСТЕМА'),
                description =(
                data .get ('description',
                "Возникла проблема на сервере?\n"
                "Хочешь что-то спросить?\n\n"
                "**Нажми кнопку ниже** — будет создан твой личный канал поддержки.\n"
                "🤖 **AI-ассистент** сначала поможет тебе!\n"
                "При необходимости наша команда подключится. 💙\n\n"
                "```yaml\n🤖 AI Поддержка  •  ⚡ Быстрый ответ  •  🔒 Приватный канал\n```"
                )
                ),
                color =0x5865F2 
                )
                embed .set_footer (
                text =f"{ch.guild.name} • Поддержка Система",
                icon_url =ch .guild .icon .url if ch .guild .icon else None 
                )
                _run_async (ch .send (embed =embed ,view =TicketView ()))
            try :
                future =asyncio .run_coroutine_threadsafe (send_panel (),bot .loop )
                future .result (timeout =10 )# ждём 10 секунд, ловим ошибку
                panel_sent =True 
            except Exception as ex :
                panel_error =str (ex )
        return jsonify ({'success':True ,'panel_sent':panel_sent ,'error':panel_error })

        # ── КАНАЛ УВЕДОМЛЕНИЙ АДМИНОВ О ТИКЕТАХ ─────────────────────────────
    @app .route ('/api/guild/<guild_id>/ticket-notify-channel',methods =['GET','POST'])
    @login_required 
    @role_required ('admin')
    def api_ticket_notify_channel (guild_id ):
        f =f'data/ticket_notify_{guild_id}.json'
        if request .method =='GET':
            if not os .path .exists (f ):
                return jsonify ({
                'notify_channel_id':None ,
                'rules_channel_id':None ,
                'mod_role_id':None ,
                'admin_role_id':None ,
                'owner_role_id':None 
                })
            try :
                with open (f ,'r',encoding ='utf-8')as fp :
                    return jsonify (json .load (fp ))
            except Exception :
                return jsonify ({
                'notify_channel_id':None ,
                'rules_channel_id':None ,
                'mod_role_id':None ,
                'admin_role_id':None ,
                'owner_role_id':None 
                })
        data =request .get_json (silent =True )or {}
        cid =data .get ('notify_channel_id')
        rcid =data .get ('rules_channel_id')
        mrid =data .get ('mod_role_id')
        arid =data .get ('admin_role_id')
        orid =data .get ('owner_role_id')

        def val_id (x ):
            if x is not None and x !='':
                x =str (x ).strip ()
                if x .isdigit ()and 17 <=len (x )<=22 :
                    return x 
            return None 

        config_data ={
        'notify_channel_id':val_id (cid ),
        'rules_channel_id':val_id (rcid ),
        'mod_role_id':val_id (mrid ),
        'admin_role_id':val_id (arid ),
        'owner_role_id':val_id (orid )
        }
        os .makedirs ('data',exist_ok =True )
        with open (f ,'w',encoding ='utf-8')as fp :
            json .dump (config_data ,fp ,indent =2 ,ensure_ascii =False )
        return jsonify ({'success':True ,**config_data })

    @app .route ('/api/guild/<guild_id>/ticket-notify-diagnose',methods =['GET'])
    @login_required 
    @role_required ('admin')
    def api_ticket_notify_diagnose (guild_id ):
        """Диагностика: что происходит при вызове _notify_admins_penalty.
        Возвращает детальную информацию о текущей конфигурации, чтобы
        понять, почему уведомления не доходят.
        """
        import web .app as _app 
        bot =_app .bot_instance 
        result ={
        'guild_id':guild_id ,
        'bot_online':bool (bot ),
        'config_file_exists':False ,
        'config_notify_channel_id':None ,
        'config_target_channel':None ,
        'config_target_channel_name':None ,
        'fallback_channels_found':[],
        'admin_role_found':None ,
        'guild_owner_can_dm':None ,
        'all_text_channels':[],
        'recommendation':'',
        }

        # 1. Конфиг-файл
        f =f'data/ticket_notify_{guild_id}.json'
        if os .path .exists (f ):
            result ['config_file_exists']=True 
            try :
                with open (f ,'r',encoding ='utf-8')as fp :
                    cfg =json .load (fp )or {}
                result ['config_notify_channel_id']=cfg .get ('notify_channel_id')
            except Exception as e :
                result ['config_file_error']=str (e )

                # 2. Бот и guild
        if not bot :
            result ['recommendation']='❌ Бот offline. Перезапусти бота.'
            return jsonify (result )
        guild =None 
        for g in bot .guilds :
            if str (g .id )==str (guild_id ):
                guild =g 
                break 
        if not guild :
            result ['recommendation']=f'❌ Бот не на сервере {guild_id}. Бот на: {[str(g.id) for g in bot.guilds]}'
            return jsonify (result )
        result ['guild_name']=guild .name 

        # 3. Канал из конфига
        if result ['config_notify_channel_id']:
            try :
                ch =guild .get_channel (int (result ['config_notify_channel_id']))
                if not ch :
                    ch =None # fetch не делаем — sync endpoint
                if ch :
                    result ['config_target_channel']=str (ch .id )
                    result ['config_target_channel_name']=ch .name 
                else :
                    result ['config_target_channel_error']=f'Канал ID={result["config_notify_channel_id"]} не найден на сервере'
            except Exception as e :
                result ['config_target_channel_error']=str (e )

                # 4. Все текстовые каналы
        result ['all_text_channels']=[
        {'id':str (c .id ),'name':c .name ,'position':c .position }
        for c in guild .text_channels [:50 ]
        ]

        # 5. Fallback каналы по имени
        for name in ('admin-log','mod-log','логи-модерации','staff-log'):
            ch =discord .utils .get (guild .text_channels ,name =name )
            if ch :
                result ['fallback_channels_found'].append ({'name':name ,'id':str (ch .id )})

                # 6. Admin role
        try :
            admin_role =discord .utils .get (guild .roles ,permissions =discord .Permissions (administrator =True ))
            if admin_role :
                result ['admin_role_found']={'name':admin_role .name ,'id':str (admin_role .id )}
        except Exception :
            pass 

            # 7. Владелец для DM
        if guild .owner :
            result ['guild_owner_can_dm']={
            'name':str (guild .owner ),
            'id':str (guild .owner .id ),
            'bot':guild .owner .bot ,
            }

            # 8. Рекомендация
        if result ['config_target_channel']:
            result ['recommendation']=(
            '✅ Конфиг установлен. Уведомления должны идти в канал '
            f'#{result["config_target_channel_name"]} ({result["config_target_channel"]}). '
            'Если уведомлений нет — проверь логи бота (ищи "[TICKET-NOTIFY]").'
            )
        elif result ['fallback_channels_found']:
            ch =result ['fallback_channels_found'][0 ]
            result ['recommendation']=(
            f'⚠️ Конфиг пустой, но найден fallback-канал #{ch["name"]} ({ch["id"]}). '
            'Уведомления должны идти туда.'
            )
        elif result ['guild_owner_can_dm']and not result ['guild_owner_can_dm'].get ('bot'):
            result ['recommendation']=(
            '⚠️ Ни конфиг, ни fallback каналы не найдены. Уведомления пойдут в DM '
            f'владельцу {result["guild_owner_can_dm"]["name"]}. '
            'Но лучше создать канал "admin-log" или "mod-log" ИЛИ установить '
            'notify_channel_id в настройках выше.'
            )
        else :
            result ['recommendation']=(
            '❌ Ни конфиг, ни fallback каналы, ни владелец для DM — '
            'уведомления НИКУДА не доставляются! Создай канал или установи ID.'
            )

        return jsonify (result )

    @app .route ('/api/guild/<guild_id>/tickets')
    @login_required 
    @role_required ('mod')
    def api_tickets (guild_id ):
        f =f'data/tickets_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ([])
        with open (f )as fp :return jsonify (list (json .load (fp ).values ()))

    @app .route ('/api/guild/<guild_id>/tickets/<ticket_id>/close',methods =['POST'])
    @login_required 
    @role_required ('mod')
    def api_close_ticket (guild_id ,ticket_id ):
        f =f'data/tickets_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ({'success':True })
        with open (f )as fp :tickets =json .load (fp )
        if ticket_id in tickets :
            tickets [ticket_id ]['status']='closed'
            with open (f ,'w')as fp :json .dump (tickets ,fp ,indent =2 )
            _t =tickets [ticket_id ]
            # Уведомление персонала по настроенным каналам (веб/Discord/email)
            _fire_panel_notification (
            'ticket_close',
            f"Тикет закрыт: {_t .get ('name') or _t .get ('subject') or ticket_id}",
            f"{session .get ('username','Модератор')} закрыл тикет {ticket_id}")
        return jsonify ({'success':True })

    @app .route ('/api/guild/<guild_id>/automod',methods =['GET','POST'])
    @login_required 
    @role_required ('admin')
    def api_automod_settings (guild_id ):
        f =f'data/automod_{guild_id}.json'
        if request .method =='GET':
            if not os .path .exists (f ):return jsonify ({'banned_words':[]})
            with open (f )as fp :return jsonify (json .load (fp ))
        data =request .get_json (silent =True )or {}
        # Читаем текущий конфиг и объединяем (чтобы ни одно поле не потерялось)
        existing ={}
        if os .path .exists (f ):
            try :
                with open (f ,encoding ='utf-8')as fp :existing =json .load (fp )
            except Exception :pass 
        existing .update (data )
        with open (f ,'w',encoding ='utf-8')as fp :json .dump (existing ,fp ,indent =2 ,ensure_ascii =False )
        return jsonify ({'success':True })

    @app .route ('/api/guild/<guild_id>/backup',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_create_backup (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        if not bot :return jsonify ({'error':'Бот офлайн'})
        guild =bot .get_guild (int (guild_id ))
        if not guild :return jsonify ({'error':'Сервер не найден'})
        data =request .get_json (silent =True )or {}
        backup ={'guild_name':guild .name ,'guild_id':str (guild .id ),
        'created_at':datetime.now(timezone.utc).replace(tzinfo=None).strftime ('%Y-%m-%d %H:%M'),'size':'0 KB'}
        if data .get ('role'):
            backup ['role']=[{'name':r .name ,'color':str (r .color ),'permissions':r .permissions .value ,
            'hoist':r .hoist ,'mentionable':r .mentionable }for r in guild .roles if r .name !='@everyone']
        if data .get ('channels'):
            backup ['channels']=[{'name':c .name ,'type':str (c .type ),'position':c .position ,
            'topic':getattr (c ,'topic',None )}for c in guild .channels ]
        if data .get ('settings'):
            backup ['settings']={'name':guild .name ,'description':guild .description ,
            'verification_level':str (guild .verification_level )}
        backup_id =str (int (datetime.now(timezone.utc).replace(tzinfo=None).timestamp ()))
        backup ['id']=backup_id 
        import sys 
        backup ['size']=f"{round(sys.getsizeof(json.dumps(backup)) / 1024, 1)} KB"
        f ='data/backups.json'
        os .makedirs ('data',exist_ok =True )
        backups =[]
        if os .path .exists (f ):
            try :
                with open (f ,encoding ='utf-8')as fp :backups =json .load (fp )
            except (json .JSONDecodeError ,ValueError ):
                backups =[]
        backups .append (backup )
        with open (f ,'w',encoding ='utf-8')as fp :json .dump (backups ,fp ,indent =2 ,ensure_ascii =False )
        return jsonify ({'success':True ,'id':backup_id })

    @app .route ('/api/backups')
    @login_required 
    @role_required ('admin')
    def api_list_backups ():
        f ='data/backups.json'
        if not os .path .exists (f ):return jsonify ([])
        try :
            with open (f ,encoding ='utf-8')as fp :return jsonify (json .load (fp ))
        except (json .JSONDecodeError ,ValueError ):
            return jsonify ([])

    @app .route ('/api/backups/<backup_id>/download')
    @login_required 
    @role_required ('admin')
    def api_download_backup (backup_id ):
        from flask import send_file 
        import io 
        f ='data/backups.json'
        if not os .path .exists (f ):return jsonify ({'error':'Не найдено'})
        try :
            with open (f ,encoding ='utf-8')as fp :backups =json .load (fp )
        except (json .JSONDecodeError ,ValueError ):
            return jsonify ({'error':'Файл бэкапа повреждён'})
        backup =next ((b for b in backups if b .get ('id')==backup_id ),None )
        if not backup :return jsonify ({'error':'Не найдено'})
        buf =io .BytesIO (json .dumps (backup ,indent =2 ,ensure_ascii =False ).encode ())
        buf .seek (0 )
        return send_file (buf ,as_attachment =True ,download_name =f"backup_{backup_id}.json",mimetype ='application/json')

    @app .route ('/api/backups/<backup_id>/delete',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_delete_backup (backup_id ):
        f ='data/backups.json'
        if not os .path .exists (f ):return jsonify ({'success':True })
        try :
            with open (f ,encoding ='utf-8')as fp :backups =json .load (fp )
        except (json .JSONDecodeError ,ValueError ):
            return jsonify ({'success':True })
        backups =[b for b in backups if b .get ('id')!=backup_id ]
        with open (f ,'w',encoding ='utf-8')as fp :json .dump (backups ,fp ,indent =2 ,ensure_ascii =False )
        return jsonify ({'success':True })

    @app .route ('/api/guild/<guild_id>/restore',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_restore_backup (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio ,discord 
        if not bot :return jsonify ({'error':'Бот офлайн'})
        guild =bot .get_guild (int (guild_id ))
        if not guild :return jsonify ({'error':'Целевой сервер не найден'})

        # Загрузка JSON-файла или backup_id?
        backup_data =None 
        if request .content_type and 'multipart'in request .content_type :
            f =request .files .get ('file')
            if not f :return jsonify ({'error':'Файл не найден'})
            try :
                backup_data =json .loads (f .read ().decode ('utf-8'))
            except Exception :
                return jsonify ({'error':'Неверный JSON-файл'})
        else :
            data =request .get_json (silent =True )or {}
            backup_id =data .get ('backup_id')
            bf ='data/backups.json'
            if not os .path .exists (bf ):return jsonify ({'error':'Резервная копия не найдена'})
            try :
                with open (bf ,encoding ='utf-8')as fp :backups =json .load (fp )
            except Exception :
                return jsonify ({'error':'Файл резервной копии повреждён'})
            backup_data =next ((b for b in backups if b .get ('id')==backup_id ),None )
            if not backup_data :return jsonify ({'error':'Резервная копия не найдена'})

        result ={'roles_created':0 ,'channels_created':0 ,'errors':[]}

        def do_restore ():
        # Роли примен
            if 'role'in backup_data :
                existing_role_names =[r .name .lower ()for r in guild .roles ]
                for role_data in backup_data ['role']:
                    if role_data ['name'].lower ()in existing_role_names :
                        continue 
                    try :
                        color_str =role_data .get ('color','#000000').lstrip ('#')
                        color =discord .Color (int (color_str ,16 ))if color_str and color_str !='000000'else discord .Color .default ()
                        _run_async (guild .create_role (
                        name =role_data ['name'],
                        color =color ,
                        hoist =role_data .get ('hoist',False ),
                        mentionable =role_data .get ('mentionable',False ),
                        permissions =discord .Permissions (role_data .get ('permissions',0 ))
                        ))
                        result ['roles_created']+=1 
                        _run_async (asyncio .sleep (0.5 ))# rate limit
                    except Exception as e :
                        result ['errors'].append (f"Роли '{role_data['name']}': {str(e)}")

                        # Каналы примен
            if 'channels'in backup_data :
                existing_ch_names =[c .name .lower ()for c in guild .channels ]
                for ch_data in backup_data ['channels']:
                    if ch_data ['name'].lower ()in existing_ch_names :
                        continue 
                    try :
                        ch_type =ch_data .get ('type','text')
                        if 'text'in ch_type :
                            _run_async (guild .create_text_channel (
                            name =ch_data ['name'],
                            topic =ch_data .get ('topic')
                            ))
                        elif 'voice'in ch_type :
                            _run_async (guild .create_voice_channel (name =ch_data ['name']))
                        elif 'category'in ch_type :
                            _run_async (guild .create_category (name =ch_data ['name']))
                        result ['channels_created']+=1 
                        _run_async (asyncio .sleep (0.5 ))
                    except Exception as e :
                        result ['errors'].append (f"Канал '{ch_data['name']}': {str(e)}")

        asyncio .run_coroutine_threadsafe (do_restore (),bot .loop ).result (timeout =120 )
        return jsonify ({'success':True ,'result':result })

    @app .route ('/api/guild/<guild_id>/message-logs')
    @login_required 
    @role_required ('mod')
    def api_message_logs (guild_id ):
        audit_file ='data/audit_log.json'
        if not os .path .exists (audit_file ):
            return jsonify ([])
        try :
            with open (audit_file ,'r',encoding ='utf-8')as fp :
                all_data =json .load (fp )
        except Exception :
            return jsonify ([])
        events =all_data .get (str (guild_id ),[])
        # Только message kategorisi
        msg_type =request .args .get ('type')# 'deleted' или 'edited'
        result =[]
        for ev in events :
            if ev .get ('category')!='message':
                continue 
            action =ev .get ('action','').lower ()
            if msg_type =='deleted'and 'удалить'not in action and 'delete'not in action :
                continue 
            if msg_type =='edited'and 'dюzenl'not in action and 'edit'not in action :
                continue 
            result .append (ev )
        result .sort (key =lambda x :x .get ('timestamp',''),reverse =True )
        return jsonify (result [:300 ])

        # ── ПОИСК СООБЩЕНИЙ ПОЛЬЗОВАТЕЛЯ (для AI) ──────────────────────────────
    @app .route ('/api/guild/<guild_id>/user-messages',methods =['GET'])
    @login_required 
    @role_required ('mod')
    def api_user_messages (guild_id ):
        """Поиск сообщений пользователя в файле message_log.

        Query params:
          user_id (обязательно) — Discord user ID
          channel_id (опционально) — конкретный канал
          limit (опционально, default 50, max 200) — число результатов
        """
        try :
            user_id =str (request .args .get ('user_id','')).strip ()
            if not user_id .isdigit ()or not (17 <=len (user_id )<=22 ):
                return jsonify ({'error':'Неверный user_id'}),400 
            channel_id =str (request .args .get ('channel_id','')).strip ()or None 
            try :
                limit =int (request .args .get ('limit',50 ))
                limit =max (1 ,min (limit ,200 ))
            except (TypeError ,ValueError ):
                limit =50 

            f =f'data/message_log_{guild_id}.json'
            if not os .path .exists (f ):
                return jsonify ({'messages':[],'total':0 ,'note':'log нет'})
            try :
                with open (f ,'r',encoding ='utf-8')as fp :
                    logs =json .load (fp )or []
            except (OSError ,json .JSONDecodeError ,ValueError ):
                return jsonify ({'messages':[],'total':0 ,'note':'log bozuk'})

                # Filtrele
            filtered =[m for m in logs 
            if str (m .get ('author_id',''))==user_id 
            and (channel_id is None or str (m .get ('channel_id',''))==channel_id )]
            # En новыйden старыйye
            filtered .sort (key =lambda x :x .get ('timestamp',''),reverse =True )
            filtered =filtered [:limit ]
            return jsonify ({
            'messages':filtered ,
            'total':len (filtered ),
            'note':None ,
            })
        except Exception as e :
            return jsonify ({'error':str (e )}),500 

    @app .route ('/api/restore-upload',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_restore_upload ():
        """Вернуть backup_data из загруженного JSON (для предпросмотра)"""
        f =request .files .get ('file')
        if not f :return jsonify ({'error':'Файл отсутствует'})
        try :
            data =json .loads (f .read ().decode ('utf-8'))
            return jsonify ({
            'guild_name':data .get ('guild_name','?'),
            'created_at':data .get ('created_at','?'),
            'roles_count':len (data .get ('role',[])),
            'channels_count':len (data .get ('channels',[])),
            'has_settings':'settings'in data ,
            'raw':data 
            })
        except Exception as e :
            return jsonify ({'error':f'Неверный dosya: {str(e)}'})

    @app .route ('/api/tasks')
    @login_required 
    @role_required ('mod')
    def api_get_tasks ():
        f ='data/tasks.json'
        if not os .path .exists (f ):return jsonify ([])
        with open (f )as fp :return jsonify (list (json .load (fp ).values ()))

    @app .route ('/api/tasks',methods =['POST'])
    @login_required 
    @role_required ('mod')
    def api_create_task ():
        data =request .get_json (silent =True )or {}
        title =(data .get ('title')or '').strip ()
        if not title :return jsonify ({'error':'Укажите название задачи'}),400 
        f ='data/tasks.json'
        os .makedirs ('data',exist_ok =True )
        tasks ={}
        if os .path .exists (f ):
            with open (f )as fp :tasks =json .load (fp )
        task_id =str (int (datetime.now(timezone.utc).replace(tzinfo=None).timestamp ()))
        tasks [task_id ]={'id':task_id ,'title':title ,'assigned_to':data .get ('assigned_to',''),
        'priority':data .get ('priority','medium'),'status':'pending',
        'created_by':session .get ('username'),'created_at':datetime.now(timezone.utc).replace(tzinfo=None).isoformat ()}
        with open (f ,'w')as fp :json .dump (tasks ,fp ,indent =2 ,ensure_ascii =False )
        return jsonify ({'success':True })

    @app .route ('/api/tasks/<task_id>',methods =['PATCH'])
    @login_required 
    @role_required ('mod')
    def api_update_task (task_id ):
        f ='data/tasks.json'
        if not os .path .exists (f ):return jsonify ({'error':'Не найдено'})
        with open (f )as fp :tasks =json .load (fp )
        if task_id in tasks :
            tasks [task_id ].update (request .get_json (silent =True )or {})
            with open (f ,'w')as fp :json .dump (tasks ,fp ,indent =2 )
        return jsonify ({'success':True })

    @app .route ('/api/tasks/<task_id>/delete',methods =['POST'])
    @login_required 
    @role_required ('mod')
    def api_delete_task (task_id ):
        f ='data/tasks.json'
        if not os .path .exists (f ):return jsonify ({'success':True })
        with open (f )as fp :tasks =json .load (fp )
        tasks .pop (task_id ,None )
        with open (f ,'w')as fp :json .dump (tasks ,fp ,indent =2 )
        return jsonify ({'success':True })

    @app .route ('/api/guild/<guild_id>/rules',methods =['GET','POST'])
    @login_required 
    @role_required ('admin')
    def api_rules (guild_id ):
        f =f'data/rules_{guild_id}.json'
        os .makedirs ('data',exist_ok =True )
        if request .method =='GET':
            if not os .path .exists (f ):return jsonify ([])
            with open (f ,encoding ='utf-8')as fp :return jsonify (json .load (fp ))
        rules =request .get_json (force =True ,silent =True )
        if rules is None :rules =[]
        with open (f ,'w',encoding ='utf-8')as fp :json .dump (rules ,fp ,indent =2 ,ensure_ascii =False )
        return jsonify ({'success':True })

    @app .route ('/api/guild/<guild_id>/rules/publish',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_publish_rules (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio ,discord 
        if not bot :return jsonify ({'error':'Бот офлайн'})
        data =request .get_json (silent =True )or {}
        def send ():
            ch =bot .get_channel (int (data ['channel_id']))
            if ch :
                desc ='\n'.join ([f"**{i+1}.** {r}"for i ,r in enumerate (data ['rules'])])
                embed =discord .Embed (title ="📜 Правила сервера",description =desc ,color =0xdc143c )
                embed .set_footer (text ="Правил нарушение edenler наказание.")
                _run_async (ch .send (embed =embed ))
        asyncio .run_coroutine_threadsafe (send (),bot .loop ).result (timeout =10 )
        return jsonify ({'success':True })

    @app .route ('/api/guild/<guild_id>/color-roles',methods =['GET'])
    @login_required 
    def api_color_roles (guild_id ):
        f =f'data/color_roles_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ([])
        with open (f )as fp :return jsonify (json .load (fp ))

    @app .route ('/api/guild/<guild_id>/color-roles/publish',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_publish_color_roles (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio ,discord 
        if not bot :return jsonify ({'error':'Бот офлайн'})
        data =request .get_json (silent =True )or {}
        f =f'data/color_roles_{guild_id}.json'
        with open (f ,'w')as fp :json .dump (data .get ('colors',[]),fp ,indent =2 )
        def send ():
            guild =bot .get_guild (int (guild_id ))
            ch =bot .get_channel (int (data ['channel_id']))
            if not guild or not ch :return 
            for c in data .get ('colors',[]):
                role =discord .utils .get (guild .roles ,name =f"🎨 {c['name']}")
                if not role :
                    color_hex =c ['hex'].lstrip ('#')
                    role =_run_async (guild .create_role (name =f"🎨 {c['name']}",color =discord .Color (int (color_hex ,16 ))))
            desc ='\n'.join ([f"{c.get('emoji','🎨')} **{c['name']}** — `{c['hex']}`"for c in data .get ('colors',[])])
            embed =discord .Embed (title ="🎨 Цветовые роли",description =desc +"\n\nЧтобы получить нужный цвет, используйте команду `/color`!",color =0xdc143c )
            _run_async (ch .send (embed =embed ))
        asyncio .run_coroutine_threadsafe (send (),bot .loop )
        return jsonify ({'success':True })

    @app .route ('/api/guild/<guild_id>/antiraid',methods =['GET','POST'])
    @login_required 
    @role_required ('admin')
    def api_antiraid_settings (guild_id ):
        f =f'data/antiraid_{guild_id}.json'
        if request .method =='GET':
            if not os .path .exists (f ):return jsonify ({'whitelist':[],'recent_events':[]})
            with open (f )as fp :return jsonify (json .load (fp ))
        data =request .get_json (silent =True )or {}
        existing ={}
        if os .path .exists (f ):
            with open (f )as fp :existing =json .load (fp )
            # recent_events: если есть в payload — использовать, иначе сохранить с диска
        if 'recent_events'not in data :
            data ['recent_events']=existing .get ('recent_events',[])
            # whitelist: принимать только валидные числовые user_id из 17-22 цифр
        wl =data .get ('whitelist')
        if not isinstance (wl ,list ):
            wl =existing .get ('whitelist',[])
        else :
            wl =[str (x )for x in wl if isinstance (x ,(str ,int ))
            and str (x ).isdigit ()and 17 <=len (str (x ))<=22 ]
            # Убрать повторы, сохранить порядок
        seen =set ()
        wl_clean =[]
        for x in wl :
            if x not in seen :
                seen .add (x )
                wl_clean .append (x )
                # Maks 500 user limit
        data ['whitelist']=wl_clean [:500 ]
        # raid_action her zaman 'alert' — diгer deгerleri отклонить
        data ['raid_action']='alert'
        # Numeric alanlarыn tipini koru
        try :
            data ['join_threshold']=max (2 ,min (50 ,int (data .get ('join_threshold',5 ))))
            data ['join_window']=max (5 ,min (120 ,int (data .get ('join_window',10 ))))
            data ['min_age']=max (0 ,min (365 ,int (data .get ('min_age',5 ))))
        except (TypeError ,ValueError ):
            data ['join_threshold']=5 
            data ['join_window']=10 
            data ['min_age']=5 
            # Boolean alanlar
        for bkey in ('join_raid','bot_protection','webhook_protection',
        'delete_protection','age_filter'):
            data [bkey ]=bool (data .get (bkey ,False ))
        with open (f ,'w')as fp :json .dump (data ,fp ,indent =2 ,ensure_ascii =False )
        return jsonify ({'success':True })

        # ── RE-JOIN ROLES API ────────────────────────────────────────────────────

    @app .route ('/api/guild/<guild_id>/rejoin-roles',methods =['GET','POST'])
    @login_required 
    @role_required ('admin')
    def api_rejoin_roles (guild_id ):
        f =f'data/rejoin_{guild_id}.json'
        if request .method =='GET':
            if not os .path .exists (f ):
                return jsonify ({'enabled':False ,'tracked_role_ids':[],'leave_log':[]})
            try :
                with open (f ,'r',encoding ='utf-8')as fp :
                    d =json .load (fp )
            except Exception :
                d ={'enabled':False ,'tracked_role_ids':[],'leave_log':[]}
            d .setdefault ('enabled',False )
            d .setdefault ('tracked_role_ids',[])
            d .setdefault ('leave_log',[])
            return jsonify (d )

        data =request .get_json (silent =True )or {}
        enabled =bool (data .get ('enabled',False ))
        # tracked_role_ids: принимать только числовые строки, макс 50
        raw_ids =data .get ('tracked_role_ids',[])
        if not isinstance (raw_ids ,list ):
            raw_ids =[]
        seen =set ()
        clean_ids =[]
        for x in raw_ids :
            s =str (x )
            if s .isdigit ()and 17 <=len (s )<=22 and s not in seen :
                seen .add (s )
                clean_ids .append (s )
            if len (clean_ids )>=50 :
                break 
                # Кросс-проверка со списком ролей бота — отсутствующие роли могли быть удалены на сервереr
        import web .app as _app 
        bot =_app .bot_instance 
        guild =None 
        if bot :
            guild =bot .get_guild (int (guild_id ))
            if guild is None :
                for g in bot .guilds :
                    if str (g .id )==str (guild_id ):
                        guild =g 
                        break 

        if guild is not None :
            valid_ids =[rid for rid in clean_ids if guild .get_role (int (rid ))is not None ]
        else :
        # Bot offline veya guild bulunamadы — tюm ID'leri принять et
            valid_ids =clean_ids 

            # leave_log korunuyor (cog tarafыndan yazыlыr)
        existing ={}
        if os .path .exists (f ):
            try :
                with open (f ,'r',encoding ='utf-8')as fp :
                    existing =json .load (fp )
            except Exception :
                existing ={}
        leave_log =data .get ('leave_log')
        if not isinstance (leave_log ,list ):
            leave_log =existing .get ('leave_log',[])
            # leave_log'u 200 ile sыnыrla
        leave_log =leave_log [-200 :]
        result ={
        'enabled':enabled ,
        'tracked_role_ids':valid_ids ,
        'leave_log':leave_log ,
        }
        os .makedirs ('data',exist_ok =True )
        with open (f ,'w',encoding ='utf-8')as fp :
            json .dump (result ,fp ,indent =2 ,ensure_ascii =False )
        return jsonify ({'success':True ,'tracked_count':len (valid_ids )})

        # ── API ЗНАЧКОВ ────────────────────────────────────────────────────────────

    @app .route ('/api/guild/<guild_id>/badges')
    @login_required 
    @role_required ('mod')
    def api_guild_badges (guild_id ):
        f =f'data/badges_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ([])
        with open (f ,'r',encoding ='utf-8')as fp :
            data =json .load (fp )
        result =[]
        for uid ,u in data .items ():
            if u .get ('badges'):
                result .append ({'user_id':uid ,'name':u .get ('name',uid ),'badges':u ['badges'],'messages':u .get ('messages',0 )})
        result .sort (key =lambda x :len (x ['badges']),reverse =True )
        return jsonify (result [:50 ])

        # ── COG УПРАВЛЕНИЕ API ─────────────────────────────────────────────────────

    @app .route ('/api/cogs')
    @login_required 
    @role_required ('owner')
    def api_cogs ():
        import web .app as _app ;bot =_app .bot_instance 
        import os 
        # Скрыть служебные файлы, чтобы не путать пользователя:
        #  - имена с '_' / __init__ — вспомогательные (не cog'и)
        #  - NON_COG — модули-помощники на диске, загружаемые через import, а не как cog
        NON_COG ={'embed_utils','leveling_engagement'}
        all_cogs =[]
        _cogs_dir =os .path .join (os .path .dirname (os .path .dirname (os .path .abspath (__file__ ))),'cogs')
        for f in os .listdir (_cogs_dir ):
            if not f .endswith ('.py'):continue 
            name =f [:-3 ]
            if name .startswith ('_')or name in NON_COG :
                continue 
            all_cogs .append (name )
        loaded =[ext .split ('.')[-1 ]for ext in (bot .extensions if bot else [])]
        return jsonify ([{
        'name':c ,
        'loaded':c in loaded 
        }for c in sorted (all_cogs )])

    @app .route ('/api/cogs/<cog_name>/reload',methods =['POST'])
    @login_required 
    @role_required ('owner')
    def api_reload_cog (cog_name ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio 
        if not bot :return jsonify ({'error':'Бот офлайн'})
        async def do ():
            if f'cogs.{cog_name}'in bot .extensions :
                await (bot .reload_extension (f'cogs.{cog_name}'))
            else :
                await (bot .load_extension (f'cogs.{cog_name}'))
        try :
            asyncio .run_coroutine_threadsafe (do (),bot .loop ).result (timeout =10 )
            return jsonify ({'success':True })
        except Exception as e :
            return jsonify ({'error':str (e )})

    @app .route ('/api/cogs/<cog_name>/unload',methods =['POST'])
    @login_required 
    @role_required ('owner')
    def api_unload_cog (cog_name ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio 
        if not bot :return jsonify ({'error':'Бот офлайн'})
        if cog_name =='cog_manager':
            return jsonify ({'error':'Модуль удалён!'})
        async def do ():
            await (bot .unload_extension (f'cogs.{cog_name}'))
        try :
            asyncio .run_coroutine_threadsafe (do (),bot .loop ).result (timeout =10 )
            return jsonify ({'success':True })
        except Exception as e :
            return jsonify ({'error':str (e )})

            # ── СЕРВЕР ИНФОРМАЦИЯ API ───────────────────────────────────────────────────

    @app .route ('/api/guild/<guild_id>/info2')
    @login_required 
    @role_required ('mod')
    def api_guild_info2 (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        if not bot :return jsonify ({'error':'Бот офлайн'})
        guild =bot .get_guild (int (guild_id ))
        if not guild :return jsonify ({'error':'Сервер не найден'})
        return jsonify ({
        'id':str (guild .id ),
        'name':guild .name ,
        'description':guild .description or '',
        'icon':str (guild .icon .url )if guild .icon else None ,
        'banner':str (guild .banner .url )if guild .banner else None ,
        'splash':str (guild .splash .url )if guild .splash else None ,
        'member_count':guild .member_count ,
        'online_count':sum (1 for m in guild .members if m .status !=discord .Status .offline ),
        'bot_count':sum (1 for m in guild .members if m .bot ),
        'channel_count':len (guild .channels ),
        'role_count':len (guild .roles ),
        'emoji_count':len (guild .emojis ),
        'boost_level':guild .premium_tier ,
        'boost_count':guild .premium_subscription_count ,
        'created_at':guild .created_at .isoformat (),
        'owner_id':str (guild .owner_id ),
        'verification_level':str (guild .verification_level ),
        'features':list (guild .features ),
        })

        # ── ETKИNLИKLER API ──────────────────────────────────────────────────────

    @app .route ('/api/guild/<guild_id>/events')
    @login_required 
    @role_required ('mod')
    def api_guild_events (guild_id ):
        f =f'data/events_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ([])
        with open (f ,'r',encoding ='utf-8')as fp :
            data =json .load (fp )
        events =list (data .values ())
        events .sort (key =lambda x :x .get ('time',''))
        return jsonify (events )

    @app .route ('/api/guild/<guild_id>/events/<event_id>/delete',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_delete_event (guild_id ,event_id ):
        f =f'data/events_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ({'success':True })
        with open (f ,'r',encoding ='utf-8')as fp :data =json .load (fp )
        data .pop (event_id ,None )
        with open (f ,'w',encoding ='utf-8')as fp :json .dump (data ,fp ,indent =2 ,ensure_ascii =False )
        return jsonify ({'success':True })

        # ── РОЖДЕНИЕ ДЕНЬ API ───────────────────────────────────────────────────────

    @app .route ('/api/guild/<guild_id>/birthdays')
    @login_required 
    @role_required ('mod')
    def api_birthdays (guild_id ):
        f =f'data/birthdays_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ([])
        with open (f ,'r',encoding ='utf-8')as fp :data =json .load (fp )
        return jsonify ([{'user_id':k ,**v }for k ,v in data .items ()])

        # ── WEBHOOK API ──────────────────────────────────────────────────────────

    @app .route ('/api/guild/<guild_id>/webhooks')
    @login_required 
    @role_required ('admin')
    def api_guild_webhooks (guild_id ):
        f =f'data/webhooks_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ([])
        with open (f ,'r',encoding ='utf-8')as fp :return jsonify (list (json .load (fp ).values ()))

    @app .route ('/api/guild/<guild_id>/webhooks/send',methods =['POST'])
    @login_required 
    @role_required ('admin')
    def api_send_webhook_v2 (guild_id ):
        import web .app as _app ;bot =_app .bot_instance 
        import asyncio ,discord as _discord 
        if not bot :return jsonify ({'error':'Бот офлайн'})
        data =request .get_json (silent =True )or {}
        wh_id =data .get ('webhook_id')
        message =data .get ('message','')
        username =data .get ('username','Aether')
        f =f'data/webhooks_{guild_id}.json'
        if not os .path .exists (f ):return jsonify ({'error':'Вебхук не найден'})
        with open (f ,'r',encoding ='utf-8')as fp :whs =json .load (fp )
        if wh_id not in whs :return jsonify ({'error':'Вебхук не найден'})
        wh_data =whs [wh_id ]
        async def do ():
            channel =bot .get_channel (int (wh_data ['channel_id']))
            if channel :
                webhooks =await (channel .webhooks ())
                wh =_discord .utils .get (webhooks ,id =int (wh_id ))
                if wh :
                    await (wh .send (content =message ,username =username ))
        try :
            asyncio .run_coroutine_threadsafe (do (),bot .loop ).result (timeout =10 )
            return jsonify ({'success':True })
        except Exception as e :
            return jsonify ({'error':str (e )})

            # ── TICKET PERMISSIONS API ─────────────────────────────────────────────────
    @app .route ('/api/guild/<int:guild_id>/ticket-permissions')
    @login_required 
    def api_ticket_permissions_get (guild_id ):
        """Получить настройки разрешений тикетов"""
        cfg_path =f'data/ticket_permissions_{guild_id}.json'
        default ={
        'systems':{
        'ai_enabled':True ,
        'rate_limiter':True ,
        'auto_close':True ,
        'feedback':True ,
        'progress_indicator':True ,
        'complaint_system':True ,
        },
        'roles':{
        'mod_roles':[],
        'owner_roles':[],
        }
        }
        try :
            if os .path .exists (cfg_path ):
                with open (cfg_path ,'r',encoding ='utf-8')as f :
                    data =json .load (f )
                return jsonify ({'success':True ,'config':data })
            return jsonify ({'success':True ,'config':default })
        except Exception as e :
            return jsonify ({'success':False ,'error':str (e )}),500 

    @app .route ('/api/guild/<int:guild_id>/ticket-permissions',methods =['POST'])
    @login_required 
    def api_ticket_permissions_set (guild_id ):
        """Сохранить настройки разрешений тикетов"""
        data =request .get_json ()
        if not data :
            return jsonify ({'success':False ,'error':'Нет данных'}),400 

        cfg_path =f'data/ticket_permissions_{guild_id}.json'
        try :
            os .makedirs ('data',exist_ok =True )
            tmp =cfg_path +'.tmp'
            with open (tmp ,'w',encoding ='utf-8')as f :
                json .dump (data ,f ,ensure_ascii =False ,indent =2 )
            os .replace (tmp ,cfg_path )
            return jsonify ({'success':True })
        except Exception as e :
            return jsonify ({'success':False ,'error':str (e )}),500 

    # ═══════════════════════════════════════════════════════════════════
    #  РОЛИ И ДОСТУП (Command ACL) — управление доступом к командам
    # ═══════════════════════════════════════════════════════════════════
    @app .route ('/role-permissions')
    @login_required
    @role_required ('owner')
    def role_permissions_page ():
        return render_template (
        'role_permissions.html',
        role =session .get ('role'),
        username =session .get ('username'),
        guild_id =active_guild_id ()
        )

    @app .route ('/panel-access')
    @login_required
    @role_required ('owner')
    def panel_access_page ():
        """Доступ к панелям: какие Discord-роли получают панель
        Владелец / Администратор / Модератор / Участник."""
        return render_template (
        'panel_access.html',
        role =session .get ('role'),
        username =session .get ('username'),
        guild_id =active_guild_id ()
        )

    @app .route ('/panel-menu')
    @login_required
    @role_required ('owner')
    def panel_menu_page ():
        """Доступ к меню: какие категории (группы) и страницы (комнаты)
        видны в панели Модератора и Администратора."""
        return render_template (
        'panel_menu.html',
        role =session .get ('role'),
        username =session .get ('username'),
        guild_id =active_guild_id ()
        )

    @app .route ('/api/role-permissions/<guild_id>')
    @login_required
    @role_required ('owner')
    def api_role_permissions_get (guild_id ):
        """Вернуть: все роли сервера, категории команд, текущие ACL."""
        from services .permission_acl import COMMAND_CATEGORIES ,load_acl
        import web .app as _app
        bot =_app .bot_instance
        guild =None
        if bot :
            guild =bot .get_guild (int (guild_id ))
            if guild is None :
                for g in bot .guilds :
                    if str (g .id )==str (guild_id ):
                        guild =g
                        break
        roles =[]
        if guild :
            roles =[
            {'id':str (r .id ),'name':r .name ,'color':str (r .color ),
             'position':r .position ,'hoist':r .hoist ,
             'permissions':r .permissions .value }
            for r in guild .roles
            ]
            roles .sort (key =lambda x :x ['position'],reverse =True )
        acl =load_acl (int (guild_id ))
        return jsonify ({
        'success':True ,
        'roles':roles ,
        'categories':COMMAND_CATEGORIES ,
        'acl':acl ,
        })

    @app .route ('/api/role-permissions/<guild_id>/set',methods =['POST'])
    @login_required
    @role_required ('owner')
    def api_role_permissions_set (guild_id ):
        """Установить роли для команды/категории."""
        from services .permission_acl import set_rule ,clear_rule
        data =request .get_json (silent =True )or {}
        command =data .get ('command','').strip ()
        role_ids =data .get ('role_ids',[]) or []
        if not command :
            return jsonify ({'success':False ,'error':'Нет команды'}),400
        if role_ids :
            set_rule (int (guild_id ),command ,[str (r )for r in role_ids ])
        else :
            clear_rule (int (guild_id ),command )
        return jsonify ({'success':True })

    @app .route ('/api/role-permissions/<guild_id>/clear',methods =['POST'])
    @login_required
    @role_required ('owner')
    def api_role_permissions_clear (guild_id ):
        """Сбросить все ограничения (всё доступно всем)."""
        from services .permission_acl import save_acl
        save_acl (int (guild_id ),{})
        return jsonify ({'success':True })

    @app .route ('/api/role-permissions/<guild_id>/preset',methods =['POST'])
    @login_required
    @role_required ('owner')
    def api_role_permissions_preset (guild_id ):
        """Применить пресет: moderator / admin / member / everyone."""
        from services .permission_acl import COMMAND_CATEGORIES ,save_acl
        data =request .get_json (silent =True )or {}
        preset =data .get ('preset','')
        role_ids =[str (r )for r in (data .get ('role_ids',[]) or [])]
        if not role_ids :
            return jsonify ({'success':False ,'error':'Выберите хотя бы одну роль'}),400
        acl ={}
        if preset =='mod':
            for cat ,cmds in COMMAND_CATEGORIES .items ():
                if cat =='Модерация':
                    acl [cat ]=role_ids
        elif preset =='staff':
            for cat ,cmds in COMMAND_CATEGORIES .items ():
                if cat in ('Модерация','Сервер','Приглашения/Участники'):
                    acl [cat ]=role_ids
        elif preset =='all':
            for cat ,cmds in COMMAND_CATEGORIES .items ():
                acl [cat ]=role_ids
        else :
            return jsonify ({'success':False ,'error':'Неизвестный пресет'}),400
        save_acl (int (guild_id ),acl )
        return jsonify ({'success':True ,'preset':preset })

    @app .route ('/api/role-permissions/<guild_id>/category/everyone',methods =['POST'])
    @login_required
    @role_required ('owner')
    def api_role_permissions_category_everyone (guild_id ):
        """Открыть категорию для всех: снять ограничения с категории и всех её команд."""
        from services .permission_acl import COMMAND_CATEGORIES ,load_acl ,save_acl
        data =request .get_json (silent =True )or {}
        category =data .get ('category','').strip ()
        if not category :
            return jsonify ({'success':False ,'error':'Не указана категория'}),400
        cmds =COMMAND_CATEGORIES .get (category ,[])
        acl =load_acl (int (guild_id ))
        acl .pop (category ,None )   # снять ограничение с категории
        for c in cmds :
            acl .pop (c ,None )      # снять ограничение с каждой команды
        save_acl (int (guild_id ),acl )
        return jsonify ({'success':True ,'category':category ,'commands_cleared':len (cmds )})

    @app .route ('/api/role-permissions/<guild_id>/category/assign',methods =['POST'])
    @login_required
    @role_required ('owner')
    def api_role_permissions_category_assign (guild_id ):
        """Топливо: назначить несколько ролей сразу на целую категорию (все её команды)."""
        from services .permission_acl import COMMAND_CATEGORIES ,load_acl ,save_acl
        data =request .get_json (silent =True )or {}
        category =data .get ('category','').strip ()
        role_ids =[str (r )for r in (data .get ('role_ids',[]) or [])]
        if not category :
            return jsonify ({'success':False ,'error':'Не указана категория'}),400
        cmds =COMMAND_CATEGORIES .get (category ,[])
        acl =load_acl (int (guild_id ))
        if role_ids :
            acl [category ]=role_ids
            for c in cmds :
                acl [c ]=role_ids
        else :
            acl .pop (category ,None )
            for c in cmds :
                acl .pop (c ,None )
        save_acl (int (guild_id ),acl )
        return jsonify ({'success':True ,'category':category ,'role_ids':role_ids ,'commands':len (cmds )})

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
                    except Exception :
                        pass 

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
        'top_moderators':top_mods 
        })

    @app .route ('/dashboard')
    @login_required 
    def dashboard_page ():
        """Страница дашборда с аналитикой"""
        return render_template ('dashboard.html',role =session .get ('role'),username =session .get ('username'))


        # ── TICKET SEARCH API ───────────────────────────────────────────────────────
    @app .route ('/api/tickets/search',methods =['POST'])
    @login_required 
    def api_ticket_search ():
        """Поиск тикетов по фильтрам"""
        import json 
        import os 
        from datetime import datetime ,timedelta 

        data =request .get_json ()
        search =data .get ('search','').lower ()
        status =data .get ('status','')
        category =data .get ('category','')
        days =data .get ('days','')

        # Загрузить данные тикетов
        data_dir ='data'
        tickets =[]

        if os .path .exists (data_dir ):
            for filename in os .listdir (data_dir ):
                if filename .startswith ('ai_tickets_')and filename .endswith ('.json'):
                    guild_id =filename .replace ('ai_tickets_','').replace ('.json','')
                    filepath =os .path .join (data_dir ,filename )
                    try :
                        with open (filepath ,'r',encoding ='utf-8')as f :
                            ticket_data =json .load (f )
                            for ticket_id ,ticket in ticket_data .items ():
                            # Фильтр по статусу
                                if status and ticket .get ('status','open')!=status :
                                    continue 

                                    # Фильтр по категории
                                if category and ticket .get ('category','')!=category :
                                    continue 

                                    # Фильтр по дате
                                if days :
                                    created_at =ticket .get ('created_at','')
                                    if created_at :
                                        created_date =datetime .fromisoformat (created_at .replace ('Z','+00:00'))
                                        cutoff_date =datetime .now (created_date .tzinfo )-timedelta (days =int (days ))
                                        if created_date <cutoff_date :
                                            continue 

                                            # Фильтр по поиску
                                if search :
                                    search_fields =[
                                    str (ticket_id ),
                                    ticket .get ('user_name',''),
                                    ticket .get ('description',''),
                                    ticket .get ('category','')
                                    ]
                                    if not any (search in field .lower ()for field in search_fields ):
                                        continue 

                                tickets .append ({
                                'id':ticket_id ,
                                'guild_id':guild_id ,
                                'user_name':ticket .get ('user_name','Неизвестный'),
                                'status':ticket .get ('status','open'),
                                'category':ticket .get ('category','Без категории'),
                                'description':ticket .get ('description',''),
                                'channel_name':ticket .get ('channel_name',''),
                                'created_at':ticket .get ('created_at',''),
                                'closed_by':ticket .get ('closed_by','')
                                })
                    except Exception :
                        pass 

                        # Сортировка по дате (новые первые)
        tickets .sort (key =lambda x :x .get ('created_at',''),reverse =True )

        return jsonify ({
        'success':True ,
        'tickets':tickets [:100 ]# Максимум 100 результатов
        })

    @app .route ('/ticket-search')
    @login_required 
    def ticket_search_page ():
        """Страница поиска тикетов"""
        return render_template ('ticket_search.html',role =session .get ('role'),username =session .get ('username'))


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
                    except Exception :
                        pass 

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


        # ── USER PROFILE API ────────────────────────────────────────────────────────
    @app .route ('/api/user-profile',methods =['POST'])
    @login_required 
    def api_user_profile ():
        """Получить профиль пользователя"""
        import json 
        import os 

        data =request .get_json ()
        query =data .get ('query','').strip ()

        if not query :
            return jsonify ({'success':False ,'error':'Запрос не может быть пустым'}),400 

            # Найти пользователя в тикетах
        data_dir ='data'
        user_tickets =[]
        user_info =None 

        if os .path .exists (data_dir ):
            for filename in os .listdir (data_dir ):
                if filename .startswith ('ai_tickets_')and filename .endswith ('.json'):
                    filepath =os .path .join (data_dir ,filename )
                    try :
                        with open (filepath ,'r',encoding ='utf-8')as f :
                            tickets =json .load (f )
                            for ticket_id ,ticket in tickets .items ():
                                user_name =ticket .get ('user_name','')
                                user_id =ticket .get ('user_id','')

                                # Поиск по ID, имени или тегу
                                if (query in str (user_id )or 
                                query .lower ()in user_name .lower ()or 
                                query .lower ()in ticket .get ('user_tag','').lower ()):

                                    if not user_info :
                                        user_info ={
                                        'id':user_id ,
                                        'name':user_name ,
                                        'tag':ticket .get ('user_tag',''),
                                        'avatar_url':ticket .get ('avatar_url',''),
                                        'joined_at':ticket .get ('joined_at',''),
                                        'last_activity':ticket .get ('last_activity','')
                                        }

                                    user_tickets .append ({
                                    'id':ticket_id ,
                                    'status':ticket .get ('status','open'),
                                    'category':ticket .get ('category',''),
                                    'created_at':ticket .get ('created_at',''),
                                    'description':ticket .get ('description','')
                                    })
                    except Exception :
                        pass 

        if not user_info :
            return jsonify ({'success':False ,'error':'Пользователь не найден'}),404 

            # Статистика
        total_tickets =len (user_tickets )
        open_tickets =sum (1 for t in user_tickets if t ['status']=='open')
        closed_tickets =total_tickets -open_tickets 

        # Загрузить предупреждения
        warnings =[]
        warnings_file ='data/warnings.json'
        if os .path .exists (warnings_file ):
            try :
                with open (warnings_file ,'r',encoding ='utf-8')as f :
                    all_warnings =json .load (f )
                    user_warnings =all_warnings .get (str (user_info ['id']),[])
                    warnings =user_warnings 
            except Exception :
                pass 

        return jsonify ({
        'success':True ,
        'user':{
        **user_info ,
        'total_tickets':total_tickets ,
        'open_tickets':open_tickets ,
        'closed_tickets':closed_tickets ,
        'warnings_count':len (warnings ),
        'tickets':user_tickets [:20 ],# Последние 20 тикетов
        'warnings':warnings [:10 ]# Последние 10 предупреждений
        }
        })

    @app .route ('/user-profile')
    @login_required 
    def user_profile_page ():
        """Страница профиля пользователя"""
        return render_template ('user_profile.html',role =session .get ('role'),username =session .get ('username'))


        # ── NOTIFICATIONS API ───────────────────────────────────────────────────────
    @app .route ('/api/notifications/settings',methods =['GET'])
    @login_required 
    def api_notifications_settings_get ():
        """Получить настройки уведомлений"""
        import json 
        import os 

        settings_file ='data/notification_settings.json'
        default_settings ={
        'web_enabled':True ,
        'discord_enabled':True ,
        'email_enabled':False ,
        'event_ticket_open':True ,
        'event_ticket_message':True ,
        'event_ticket_close':True ,
        'event_priority_change':False ,
        'event_assignment':False ,
        'event_warn':True ,
        'event_mod_action':True ,
        'event_staff_apply':True ,
        'discord_channel':'',
        'webhook_url':'',
        'smtp_server':'',
        'smtp_port':587 ,
        'smtp_email':'',
        'smtp_password':''
        }

        if os .path .exists (settings_file ):
            try :
                with open (settings_file ,'r',encoding ='utf-8')as f :
                    settings =json .load (f )
                    # Merge with defaults
                    for key ,value in default_settings .items ():
                        if key not in settings :
                            settings [key ]=value 
            except Exception :
                settings =default_settings 
        else :
            settings =default_settings 

        return jsonify ({'success':True ,'settings':settings })

    @app .route ('/api/notifications/settings',methods =['POST'])
    @login_required 
    def api_notifications_settings_post ():
        """Сохранить настройки уведомлений"""
        import json 
        import os 

        data =request .get_json ()

        settings_file ='data/notification_settings.json'
        os .makedirs ('data',exist_ok =True )

        try :
            with open (settings_file ,'w',encoding ='utf-8')as f :
                json .dump (data ,f ,ensure_ascii =False ,indent =2 )
            return jsonify ({'success':True })
        except Exception as e :
            return jsonify ({'success':False ,'error':str (e )}),500 

    @app .route ('/api/notifications/test',methods =['POST'])
    @login_required 
    def api_notifications_test ():
        """Отправить тестовое уведомление по всем настроенным каналам"""
        try :
            from services .notification_dispatcher import send_test
            channels =send_test (discord_sender =_notify_discord_sender )
            return jsonify ({'success':True ,'channels':channels })
        except Exception as e :
            return jsonify ({'success':False ,'error':str (e )}),500 

    @app .route ('/api/notifications/history',methods =['GET'])
    @login_required 
    def api_notifications_history ():
        """Получить историю уведомлений"""
        import json 
        import os 

        history_file ='data/notification_history.json'

        if os .path .exists (history_file ):
            try :
                with open (history_file ,'r',encoding ='utf-8')as f :
                    history =json .load (f )
            except Exception :
                history =[]
        else :
            history =[]

            # Сортировка по дате (новые первые)
        history .sort (key =lambda x :x .get ('created_at',''),reverse =True )

        # Чистим markdown из видимых полей — панель разметку не рендерит
        try :
            import web .app as _app
            for _h in history :
                _app ._clean_md_fields (_h )
        except Exception :
            pass

        return jsonify ({'success':True ,'notifications':history [:50 ]})# Максимум 50

    @app .route ('/notifications')
    @login_required 
    def notifications_page ():
        """Страница настроек уведомлений (только персонал)"""
        if ROLES .get (session .get ('role'),-1 )<ROLES .get ('mod',999 ):
            return redirect (url_for ('index'))
        return render_template ('notifications.html',role =session .get ('role'),username =session .get ('username'))


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


        # ── THEME SETTINGS API ──────────────────────────────────────────────────────
    @app .route ('/api/theme/settings',methods =['GET'])
    @login_required 
    def api_theme_settings_get ():
        """Получить настройки темы"""
        import json 
        import os 

        theme_file ='data/theme_settings.json'
        default_settings ={
        'theme':'dark',
        'accent_color':'#5865F2',
        'font_size':14 
        }

        if os .path .exists (theme_file ):
            try :
                with open (theme_file ,'r',encoding ='utf-8')as f :
                    settings =json .load (f )
            except Exception :
                settings =default_settings 
        else :
            settings =default_settings 

        return jsonify ({'success':True ,'settings':settings })

    @app .route ('/api/theme/settings',methods =['POST'])
    @login_required 
    def api_theme_settings_post ():
        """Сохранить настройки темы"""
        import json 
        import os 

        data =request .get_json ()

        theme_file ='data/theme_settings.json'
        os .makedirs ('data',exist_ok =True )

        try :
            with open (theme_file ,'w',encoding ='utf-8')as f :
                json .dump (data ,f ,ensure_ascii =False ,indent =2 )
            return jsonify ({'success':True })
        except Exception as e :
            return jsonify ({'success':False ,'error':str (e )}),500 

    @app .route ('/theme-settings')
    @login_required 
    def theme_settings_page ():
        """Страница настроек темы"""
        return render_template ('theme_settings.html',role =session .get ('role'),username =session .get ('username'))


        # ── ADVANCED ANALYTICS API ──────────────────────────────────────────────────
    @app .route ('/api/analytics/advanced',methods =['POST'])
    @login_required 
    def api_analytics_advanced ():
        """Получить расширенную аналитику"""
        import json 
        import os 
        from datetime import datetime ,timedelta 
        from collections import Counter ,defaultdict 

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
                    except Exception :
                        pass 

                        # Фильтрация по периоду
        cutoff_date =datetime .now ()-timedelta (days =period )
        filtered_tickets =[]

        for ticket in all_tickets :
            created_at =ticket .get ('created_at','')
            if created_at :
                try :
                    created_date =datetime .fromisoformat (created_at .replace ('Z','+00:00'))
                    if created_date >=cutoff_date :
                    # Фильтрация по категории
                        if category_filter and ticket .get ('category','')!=category_filter :
                            continue 
                            # Фильтрация по модератору
                        if moderator_filter and ticket .get ('closed_by','')!=moderator_filter :
                            continue 
                        filtered_tickets .append (ticket )
                except Exception :
                    pass 

                    # Расчет статистики
        total_tickets =len (filtered_tickets )
        closed_tickets =sum (1 for t in filtered_tickets if t .get ('status')=='closed')
        resolution_rate =round ((closed_tickets /total_tickets *100 ),1 )if total_tickets >0 else 0 

        # Среднее время решения
        resolution_times =[]
        for ticket in filtered_tickets :
            if ticket .get ('status')=='closed'and ticket .get ('created_at')and ticket .get ('closed_at'):
                try :
                    created =datetime .fromisoformat (ticket ['created_at'].replace ('Z','+00:00'))
                    closed =datetime .fromisoformat (ticket ['closed_at'].replace ('Z','+00:00'))
                    hours =(closed -created ).total_seconds ()/3600 
                    resolution_times .append (hours )
                except Exception :
                    pass 

        avg_resolution_time =round (sum (resolution_times )/len (resolution_times ),1 )if resolution_times else 0 

        # Оценка удовлетворенности (placeholder)
        satisfaction_score =4.5 

        # Тренды (сравнение с предыдущим периодом)
        prev_cutoff_date =cutoff_date -timedelta (days =period )
        prev_tickets =[t for t in all_tickets if prev_cutoff_date <=datetime .fromisoformat (t .get ('created_at','').replace ('Z','+00:00'))<cutoff_date ]
        prev_total =len (prev_tickets )

        total_tickets_trend =round (((total_tickets -prev_total )/prev_total *100 ),1 )if prev_total >0 else 0 

        # Тренд тикетов (по дням)
        tickets_by_day =defaultdict (int )
        for ticket in filtered_tickets :
            created_at =ticket .get ('created_at','')
            if created_at :
                try :
                    date =datetime .fromisoformat (created_at .replace ('Z','+00:00')).date ()
                    tickets_by_day [date ]+=1 
                except Exception :
                    pass 

        trend_labels =[]
        trend_data =[]
        for i in range (period ,0 ,-1 ):
            date =(datetime .now ()-timedelta (days =i )).date ()
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
                    created =datetime .fromisoformat (ticket ['created_at'].replace ('Z','+00:00'))
                    closed =datetime .fromisoformat (ticket ['closed_at'].replace ('Z','+00:00'))
                    hours =(closed -created ).total_seconds ()/3600 
                    category =ticket .get ('category','Другое')
                    resolution_by_category [category ].append (hours )
                except Exception :
                    pass 

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
        """Экспорт отчета аналитики"""
        from flask import Response 

        data =request .get_json ()
        format_type =data .get ('format','csv')

        # Placeholder для экспорта
        if format_type =='csv':
            content ="Дата,Категория,Статус,Время решения\n"
            content +="01.01.2026,Вопрос,Закрыт,2.5\n"
            content +="02.01.2026,Жалоба,Закрыт,4.0\n"

            return Response (
            content ,
            mimetype ='text/csv',
            headers ={'Content-Disposition':'attachment; filename=analytics_report.csv'}
            )

        return jsonify ({'success':False ,'error':'Формат временно недоступен'}),501 

    @app .route ('/advanced-analytics')
    @login_required 
    def advanced_analytics_page ():
        """Страница расширенной аналитики"""
        return render_template ('advanced_analytics.html',role =session .get ('role'),username =session .get ('username'))


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
        'created_at':datetime .now ().isoformat ()
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
        'created_at':datetime .now ().isoformat (),
        'updated_at':datetime .now ().isoformat ()
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




def calculate_ai_ticket_stats (guild_id :int )->dict :
    """AI ticket статистика hesapla"""
    import json ,os 
    from datetime import datetime 
    from collections import Counter 

    # Penalty dosyasыnы загрузить
    penalty_file ='data/ticket_penalties.json'
    penalties ={}
    if os .path .exists (penalty_file ):
        try :
            with open (penalty_file ,'r',encoding ='utf-8')as f :
                penalties =json .load (f )
        except Exception:
            pass 

    guild_penalties =penalties .get (str (guild_id ),{})

    # Temel статистика
    total_penalties =sum (len (p )if isinstance (p ,list )else 1 for p in guild_penalties .values ())

    # Наказание причина say
    reasons =[]
    for user_penalties in guild_penalties .values ():
        if isinstance (user_penalties ,list ):
            for p in user_penalties :
                reasons .append (p .get ('reason','неизвестно'))
        else :
            reasons .append (user_penalties .get ('reason','неизвестно'))

    reason_counter =Counter (reasons )

    # Взаимный нарушение, фейковый жалоба число
    mutual_violations =reason_counter .get ('взаимный мат/оскорбление',0 )
    fake_complaints =reason_counter .get ('фейковый жалоба + правило нарушение',0 )
    single_violations =total_penalties -mutual_violations -fake_complaints 

    # Oranlar
    total =total_penalties if total_penalties >0 else 1 
    mutual_rate =round ((mutual_violations /total )*100 ,1 )
    fake_rate =round ((fake_complaints /total )*100 ,1 )
    single_rate =round ((single_violations /total )*100 ,1 )
    no_violation_rate =max (0 ,100 -mutual_rate -fake_rate -single_rate )

    # En очень наказание alan userlar
    top_offenders =[]
    for user_id ,user_penalties in guild_penalties .items ():
        if isinstance (user_penalties ,list ):
            count =len (user_penalties )
            total_duration =sum (p .get ('duration',0 )for p in user_penalties )
            last_penalty =user_penalties [-1 ].get ('date','неизвестно')if user_penalties else 'неизвестно'
            name =user_penalties [-1 ].get ('name',user_id )if user_penalties else user_id 
        else :
            count =1 
            total_duration =user_penalties .get ('duration',0 )
            last_penalty =user_penalties .get ('date','неизвестно')
            name =user_penalties .get ('name',user_id )

        top_offenders .append ({
        'name':name ,
        'count':count ,
        'total_duration':total_duration ,
        'last_penalty':last_penalty [:10 ]if isinstance (last_penalty ,str )else 'неизвестно'
        })

    top_offenders .sort (key =lambda x :x ['count'],reverse =True )
    top_offenders =top_offenders [:10 ]

    # Наказание причина
    penalty_reasons =[]
    for reason ,count in reason_counter .most_common ():
        penalty_reasons .append ({
        'name':reason ,
        'count':count ,
        'percentage':round ((count /total )*100 ,1 )
        })

        # AI ticket verilerini загрузить
    ai_tickets =_load_ai_tickets (guild_id )
    total_tickets =len (ai_tickets )

    return {
    'total_tickets':total_tickets ,
    'total_penalties':total_penalties ,
    'mutual_violations':mutual_violations ,
    'fake_complaints':fake_complaints ,
    'single_violation_rate':single_rate ,
    'mutual_rate':mutual_rate ,
    'fake_rate':fake_rate ,
    'no_violation_rate':no_violation_rate ,
    'avg_confidence':75 ,# Placeholder - gerчek hesaplama для AI response'larы saklamak gerek
    'high_confidence_count':int (total_penalties *0.8 ),# Tahmini
    'low_confidence_count':int (total_penalties *0.2 ),# Tahmini
    'appeal_rate':5 ,# Placeholder
    'appeal_success_rate':30 ,# Placeholder
    'top_offenders':top_offenders ,
    'penalty_reasons':penalty_reasons 
    }