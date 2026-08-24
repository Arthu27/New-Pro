# -*- coding: utf-8 -*-
"""Общая база роутов панели: импорты, хелперы, ctx.

Вырезано из web/routes_extra.py при нарезке (аудит, поведение 1:1).
Route-модули импортируют отсюда всё необходимое; Ctx несёт то, что раньше
было замыканием register_extra_routes: app, ROLES, декораторы, MAIN_GUILD_ID.
"""

from logger import get_logger

_log = get_logger("routes_extra")

from flask import render_template ,session ,redirect ,url_for ,request ,jsonify ,Response 
import os ,json 
import time 
import math 
import discord 
from datetime import datetime, timezone, timedelta


def _load_ai_tickets (guild_id :int )->dict :
    """Загрузить данные AI-тикетов"""
    path =f"data/ai_tickets_{guild_id}.json"
    if os .path .exists (path ):
        try :
            with open (path ,'r',encoding ='utf-8')as f :
                return json .load (f )
        except Exception as _ex:
            _log.debug("_load_ai_tickets(): подавлено: %s", _ex)
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
            except Exception as _ex:
                _log.debug("_fetch_channel_msgs_async(): подавлено: %s", _ex)
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


def name_map_for (gid ,bot =None ):
    """uid → имя: data/member_names_{gid}.json → демо-участники → кэш бота.

    Единый источник имён для всех списков панели (логи, варны, риски,
    субъекты, заявки): вместо голых ID везде показывается имя, если оно
    известно; неизвестные id остаются как есть.
    """
    out ={}
    try :
        f ='data/member_names_%s.json' % str (gid )
        if os .path .exists (f ):
            with open (f ,encoding ='utf-8')as fp :
                d =json .load (fp )
            if isinstance (d ,dict ):
                for k ,v in d .items ():
                    if v :
                        out [str (k )]=str (v )
    except Exception as _ex :
        _log.debug("name_map_for(%s): файл имён: %s", gid ,_ex )
    try :
        import web .app as _appm
        if _appm ._demo_mode ():
            for m in DEMO_MEMBERS :
                out .setdefault (str (m .get ('id')),str (m .get ('display_name')or m .get ('name')or m .get ('id')))
    except Exception as _ex :
        _log.debug("name_map_for(%s): демо-имена: %s", gid ,_ex )
    if bot is None :
        try :
            import web .app as _appm2
            bot =_appm2 .bot_instance
        except Exception :
            bot =None 
    try :
        if bot and str (gid ).isdigit ():
            g =bot .get_guild (int (gid ))
            if g is not None :
                for m in getattr (g ,'members',[]):
                    out .setdefault (str (m .id ),str (m .display_name ))
    except Exception as _ex :
        _log.debug("name_map_for(%s): кэш бота: %s", gid ,_ex )
    return out 

def fill_names (items ,gid ,field_map =None ,bot =None ):
    """Дописать имена в записи: {id-поле: имя-поле}; пустые/числовые имена заменяются."""
    field_map =field_map or {'user_id':'user_name','mod_id':'mod_name'}
    nm =name_map_for (gid ,bot )
    for it in items :
        if not isinstance (it ,dict ):
            continue 
        for idf ,nf in field_map .items ():
            uid =str (it .get (idf )or '').strip ()
            if not uid :
                continue 
            cur =str (it .get (nf )or '').strip ()
            if not cur or cur ==uid or cur .isdigit ():
                it [nf ]=nm .get (uid )or uid 
    return items 

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
                        except Exception as _ex:
                            _log.debug("_bulk(): подавлено: %s", _ex)
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
                except Exception as _ex:
                    _log.debug("_process_action(): подавлено: %s", _ex)
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

# ── Демо-участники (когда бот офлайн: поиск, @-пикер, подсказки) ─────────
DEMO_MEMBERS = [
    {'id': '1001', 'name': 'sonya.staff', 'display_name': 'Sonya',
     'avatar': 'https://cdn.discordapp.com/embed/avatars/1.png', 'status': 'online',
     'roles': [{'name': 'Куратор', 'color': '#22d3ee'}], 'joined_at': '2025-11-02T10:00:00+00:00'},
    {'id': '1002', 'name': 'artem.mods', 'display_name': 'Artem',
     'avatar': 'https://cdn.discordapp.com/embed/avatars/2.png', 'status': 'idle',
     'roles': [{'name': 'Модератор', 'color': '#4f46e5'}], 'joined_at': '2025-11-03T12:00:00+00:00'},
    {'id': '1003', 'name': 'lina.mod', 'display_name': 'Lina',
     'avatar': 'https://cdn.discordapp.com/embed/avatars/3.png', 'status': 'dnd',
     'roles': [{'name': 'Хелпер', 'color': '#22d3ee'}], 'joined_at': '2025-11-05T18:00:00+00:00'},
    {'id': '1004', 'name': 'max.gg', 'display_name': 'Max',
     'avatar': 'https://cdn.discordapp.com/embed/avatars/4.png', 'status': 'online',
     'roles': [{'name': 'Актив', 'color': '#0ea5e9'}], 'joined_at': '2025-11-10T09:00:00+00:00'},
    {'id': '1005', 'name': 'dasha.live', 'display_name': 'Dasha',
     'avatar': 'https://cdn.discordapp.com/embed/avatars/5.png', 'status': 'offline',
     'roles': [{'name': 'Ветеран', 'color': '#16a34a'}], 'joined_at': '2025-12-01T14:00:00+00:00'},
    {'id': '1006', 'name': 'kolyan.tv', 'display_name': 'Kolyan',
     'avatar': 'https://cdn.discordapp.com/embed/avatars/0.png', 'status': 'online',
     'roles': [{'name': 'Бустер', 'color': '#ec4899'}], 'joined_at': '2025-12-05T20:00:00+00:00'},
    {'id': '1007', 'name': 'nastya.chat', 'display_name': 'Nastya',
     'avatar': 'https://cdn.discordapp.com/embed/avatars/2.png', 'status': 'idle',
     'roles': [{'name': 'Музыкант', 'color': '#fb7185'}], 'joined_at': '2026-01-10T11:00:00+00:00'},
    {'id': '1008', 'name': 'vanya.voice', 'display_name': 'Vanya',
     'avatar': 'https://cdn.discordapp.com/embed/avatars/3.png', 'status': 'online',
     'roles': [{'name': 'Новичок', 'color': '#64748b'}], 'joined_at': '2026-02-14T16:00:00+00:00'},
    {'id': '1009', 'name': 'aether.bot', 'display_name': 'Aether',
     'avatar': '', 'status': 'online', 'bot': True,
     'roles': [], 'joined_at': '2025-10-01T00:00:00+00:00'},
]


def demo_members_search (query ,limit =25 ):
    """Демо-поиск участников: по имени/нику/ID — как ms_search_members, но без бота."""
    q =str (query or '').strip ().lower ()
    if not q :
        return list (DEMO_MEMBERS )[:limit ]
    out =[]
    for m in DEMO_MEMBERS :
        hay =f"{m.get('name','')} {m.get('display_name','')} {m.get('id','')}".lower ()
        if q in hay :
            out .append (m )
        if len (out )>=limit :
            break
    return out


def demo_member_payload (m ):
    """Формат участника для панели (совпадает с ms_member_payload)."""
    return {
        'id':str (m .get ('id','')),
        'name':m .get ('display_name')or m .get ('name',''),
        'display_name':m .get ('display_name')or m .get ('name',''),
        'username':m .get ('name',''),
        'avatar':m .get ('avatar',''),
        'status':m .get ('status','offline'),
        'bot':bool (m .get ('bot',False )),
        'mention':f"<@{m.get('id','')}>",
        'joined_at':m .get ('joined_at',''),
        'roles':m .get ('roles',[]),
    }


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
        'proof': str(w.get('proof') or ''),
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
        'proof': str(c.get('proof') or ''),
    }

# Корень репозитория (web/routes/_common.py -> ../../..)
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class Ctx:
    """Контекст регистрации роутов (бывшее замыкание register_extra_routes)."""

    def __init__(self, app, ROLES, login_required, role_required, MAIN_GUILD_ID):
        self.app = app
        self.ROLES = ROLES
        self.login_required = login_required
        self.role_required = role_required
        self.MAIN_GUILD_ID = MAIN_GUILD_ID

    def active_guild_id(self):
        """Return a live guild ID, never a stale value left in .env."""
        import web.app as _app
        bot = _app.bot_instance
        guilds = getattr(bot, 'guilds', None) if bot else None
        configured = str(self.MAIN_GUILD_ID or '')
        if guilds:
            if any(str(g.id) == configured for g in guilds):
                return configured
            return str(guilds[0].id)
        return configured

    def _resolve_member_async(self, guild, user_id):
        """Async helper: get cached member or fetch from API."""
        member = guild.get_member(int(user_id))
        if member:
            return member
        try:
            return _run_async(guild.fetch_member(int(user_id)))
        except Exception:
            return None






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
        except Exception as _ex:
            _log.debug("calculate_ai_ticket_stats(): подавлено: %s", _ex)

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
