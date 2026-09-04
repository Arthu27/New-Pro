# -*- coding: utf-8 -*-
"""Общая база роутов панели: импорты, хелперы, ctx.

Вырезано из web/routes_extra.py при нарезке (аудит, поведение 1:1).
Route-модули импортируют отсюда всё необходимое; Ctx несёт то, что раньше
было замыканием register_extra_routes: app, ROLES, декораторы, MAIN_GUILD_ID.
"""

from logger import get_logger

_log = get_logger("routes_extra")

from flask import render_template ,session ,redirect ,url_for ,request ,Response 
from flask import jsonify as _flask_jsonify

# ── Снежинки Discord в JSON ─────────────────────────────────────────────
# JavaScript хранит числа как double: int > 2^53 (а id каналов/ролей —
# 18..19 цифр, т.е. в ~300 раз больше) при разборе JSON необратимо теряет
# цифры. Симптом: «выбрал канал посреди списка — а показался другой /
# выбор слетел». По контракту Discord такие id и идут строками, поэтому
# ВСЕ int > 2^53 из API панели уходят клиенту строкой.
_JS_SAFE_INT_MAX = (1 << 53) - 1


def _json_snow(obj):
    if isinstance(obj, dict):
        return {k: _json_snow(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_snow(v) for v in obj]
    if isinstance(obj, int) and not isinstance(obj, bool):
        if obj > _JS_SAFE_INT_MAX or obj < -_JS_SAFE_INT_MAX:
            return str(obj)
    return obj


def jsonify(*args, **kwargs):
    """jsonify с сохранением снежинок (>2^53 int → str)."""
    return _flask_jsonify(
        *[_json_snow(a) for a in args],
        **{k: _json_snow(v) for k, v in kwargs.items()})
import os ,json 
import time 
import math 
import discord 
from datetime import datetime, timezone, timedelta


async def _fetch_channel_msgs_async (bot ,channel_mentions ):
    """Async helper to fetch recent messages from a channel, given a bot instance and optional mentions filter."""
    lines =[]
    for g in bot .guilds :
        for ch in g .text_channels :
        # Упомянут ли канал в вопросе?
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
        _res =notify_event (event ,title ,body ,discord_sender =_notify_discord_sender )
        # Живой пуш: колокольчик на всех открытых вкладках обновится сразу,
        # без 30-секундного опроса.
        try :
            from services .live_bus import publish_global
            publish_global ('notifications')
        except Exception as _live_ex :
            _log .debug ('notifications live-push: %s' ,_live_ex )
        return _res
    except Exception :
        return {}


def _live_publish (gid ,topic ):
    """Толкнуть SSE-сигнал об изменении данных (живые обновления панели).

    Никогда не прерывает основной обработчик — ошибка шины игнорируется.
    """
    try :
        from services .live_bus import publish as _pub
        _pub (gid ,topic )
    except Exception as _ex :
        _log .debug ('live_publish %s/%s: %s' ,gid ,topic ,_ex )


def _live_publish_global (topic ):
    """Глобальный SSE-сигнал (список серверов, тема и т.п.)."""
    try :
        from services .live_bus import publish_global as _pubg
        _pubg (topic )
    except Exception as _ex :
        _log .debug ('live_publish_global %s: %s' ,topic ,_ex )


# ── Классические разрешения: одна точка для всех веб-роутов ──────────────
def viewer_member(bot, gid):
    """Discord-мембер, под которым вошли в панель (session['discord_id']).

    None → проверять нечего: статический логин из .env, role=owner панели
    или мембер не найден — доверенный вход (владелец настраивал доступы).
    """
    if session.get('role') == 'owner':
        return None
    did = str(session.get('discord_id') or '').strip()
    if not did.isdigit() or bot is None:
        return None
    try:
        guild = bot.get_guild(int(gid))
        return guild.get_member(int(did)) if guild is not None else None
    except Exception:
        return None


def acl_action_allowed(gid, member, action_key):
    """«Классическое» разрешение действия (панель → Доступ → Права команд).

    Строгая модель: member None (доверенный вход — владелец панели) — можно;
    иначе решает check_action — по умолчанию ЗАПРЕТ, пока владелец не разрешит
    ролью. Discord-права не учитываются. Сбой чтения БД — не открываем действие
    (fail-close): лучше не показать кнопку, чем дать невыданное право.
    """
    if member is None:
        return True
    try:
        from services.permission_acl import check_action
        return bool(check_action(int(gid), member, action_key))
    except Exception as _ex:
        _log.debug('acl_action_allowed: %s', _ex)
        return False


def _panel_limit_deny(bot, gid, member, key, amount=1):
    """Лимиты стаффа («Щит сервера» → Лимиты) для панельного действия.

    member — viewer_member(bot, gid): реальный Discord-участник, вошедший
    в панель; None (доверенный вход владельца) — лимиты не пишем.
    Возвращает None — можно, либо готовый текст отказа («Лимит исчерпан…»).
    Сбой не мешает действию (тот же fail-open, что в когах).
    """
    try:
        if member is None or bot is None:
            return None
        guild = bot.get_guild(int(gid))
        if guild is None:
            return None
        from services import staff_limits as _SL
        ok, deny = _SL.check_action(guild, member, key, amount=amount)
        return deny if not ok else None
    except Exception as _ex:
        _log.debug('_panel_limit_deny(%s): %s', key, _ex)
        return None


def _panel_limit_record(gid, member, key, amount=1):
    """Успешное панельное действие — в счётчик лимитов модератора."""
    try:
        if member is None:
            return
        from services import staff_limits as _SL
        _SL.record_hit(int(gid), member.id, key, amount)
    except Exception as _ex:
        _log.debug('_panel_limit_record(%s): %s', key, _ex)


def _panel_mute_cap(bot, gid, member):
    """Потолок длительности мута (сек) для участника; 0 — без потолка."""
    try:
        if member is None or bot is None:
            return 0
        from services import staff_limits as _SL
        role_ids = [r.id for r in (getattr(member, 'roles', None) or [])
                    if getattr(r, 'id', None) != int(gid)]
        return int(_SL.effective_max_duration(int(gid), 'mute', role_ids) or 0)
    except Exception as _ex:
        _log.debug('_panel_mute_cap: %s', _ex)
        return 0


def _safe_json_obj():
    """request JSON строго как dict.

    Список/строка/мусор в теле → {} (robust-режим): без этого
    `data.get(...)` на не-dict ронял маршрут в 500 вместо вежливого 400.
    """
    d = request.get_json(silent=True)
    return d if isinstance(d, dict) else {}


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
            return f'⚠️ AI предлагает warn: выдать {uid} предупреждение за «{reason}». Подтвердите через /modpanel.'

        elif action_type =='ban':
            reason =action_data .get ('reason','AI ban')
            if not (guild and uid ):
                return '❌ Отсутствует параметр'
            member =guild .get_member (int (uid ))
            if not member :
                return '❌ Участник на сервере не найден'
                # AI ban предложение — автоматически примен
            return f'⚠️ AI предлагает бан: {member.display_name} ({uid}) — Причина: "{reason}". Подтвердите через /modpanel.'
            return f'✅ Ban применено (user_id: {uid})'

        elif action_type =='kick':
            reason =action_data .get ('reason','AI kick')
            if not (guild and uid ):
                return '❌ Отсутствует параметр'
            member =guild .get_member (int (uid ))
            if not member :
                return '❌ Участник на сервере не найден'
                # AI kick предложение — автоматически примен
            return f'⚠️ AI предлагает кик: {member.display_name} ({uid}) — Причина: "{action_data.get("reason", "AI kick")}". Подтвердите через /modpanel.'

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
            return f'⚠️ AI предлагает таймаут: {member.display_name} ({uid}) — {minutes} мин, причина: "{reason}". Подтвердите через /modpanel.'

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
    # Владелец демо-сервера (owner_id=7): панель входит под ним, поэтому
    # он обязан быть виден среди участников (списки, поиск, @-пикеры).
    {'id': '7', 'name': 'owner.hakumo', 'display_name': 'Владелец',
     'avatar': 'https://cdn.discordapp.com/embed/avatars/0.png', 'status': 'online',
     'roles': [{'name': 'Владелец', 'color': '#f59e0b'}],
     'joined_at': '2025-10-01T09:00:00+00:00'},
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
    {'id': '1009', 'name': 'hakumo.bot', 'display_name': 'Hakumo',
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
        """Активный сервер панели.

        MAIN_GUILD_ID из .env — главный закон: если задан, панель работает
        ТОЛЬКО с ним, даже если бот случайно состоит в других серверах
        (раньше молча переключались на первый попавшийся — чужие данные).
        Пустой MAIN_GUILD_ID — прежнее поведение (первый сервер бота)."""
        import web.app as _app
        bot = _app.bot_instance
        guilds = getattr(bot, 'guilds', None) if bot else None
        configured = str(self.MAIN_GUILD_ID or '')
        if configured:
            return configured
        if guilds:
            return str(guilds[0].id)
        # Демо-витрина без MAIN_GUILD_ID: отдаём демо-сервер 777, иначе
        # шаблоны строили битый /api/guild//channels и селекты пустовали.
        if not configured and _app._demo_mode():
            return '777'
        return configured

    def active_guild_id_int(self):
        """Активный сервер как int, или None — если сервера нет.

        active_guild_id() отдаёт СТРОКУ и вполне законно возвращает пустую:
        MAIN_GUILD_ID не задан в .env и бот ещё не подключился (или офлайн).
        Роуты писали `int(ctx.active_guild_id())` в лоб — и на пустой строке
        получали ValueError → HTTP 500 «Internal Server Error» вместо
        внятного «сервер не выбран». Инцидент 30.08: страницы Магазин,
        Музыка, Дуэли, Ачивки, Отчёт модерации, SLA/экспорт тикетов падали
        с 500 при пустом MAIN_GUILD_ID — снаружи это «панель сломана».

        Возвращает None вместо взрыва — вызывающий отдаёт 503 и подсказку.
        """
        raw = str(self.active_guild_id() or '').strip()
        if not raw:
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    def _resolve_member_async(self, guild, user_id):
        """Async helper: get cached member or fetch from API."""
        member = guild.get_member(int(user_id))
        if member:
            return member
        try:
            return _run_async(guild.fetch_member(int(user_id)))
        except Exception:
            return None







def role_member_counts(guild):
    """Число участников в каждой роли за ОДИН проход по составу сервера.

    Role.members в discord.py каждый раз копирует список всех участников и
    фильтрует его (discord/role.py:415-420):

        all_members = list(self.guild._members.values())
        return [member for member in all_members if member._roles.has(role_id)]

    Поэтому len(r.members) в цикле по ролям — это O(роли × участники): на
    20 000 участников и 250 ролей получается 5 млн итераций плюс 250 копий
    списка на 20 000 элементов. Замер в бою: [SLOW] GET /api/roles — 2.95 с.
    Один проход по участникам с подсчётом по их ролям даёт те же числа за
    O(участники + назначения).
    """
    counts = {}
    try:
        members = guild.members
    except Exception:
        return counts
    for m in members:
        try:
            member_roles = m.roles
        except Exception:
            # участник без читаемых ролей (частичный кэш, гонка при выходе) —
            # считаем его без ролей, а не роняем весь подсчёт
            member_roles = ()
        for r in member_roles:
            counts[r.id] = counts.get(r.id, 0) + 1
    return counts
