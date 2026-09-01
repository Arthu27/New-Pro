"""
AI Function Calling — AI olabilir vizivat fonksiyonlar для poluceniya verilerin ve заверш действие
"""

from logger import get_logger

_log = get_logger("ai_functions")

import json 
import os 
import discord 
from datetime import datetime ,timedelta, timezone
from typing import Dict ,List ,Optional ,Any 


class AIFunctions :
    """Набор функций, доступных AI"""

    def __init__ (self ,bot :discord .Client ):
        self .bot =bot 
        self .functions ={
        'get_user_warnings':self .get_user_warnings ,
        'get_user_info':self .get_user_info ,
        'get_user_roles':self .get_user_roles ,
        'check_message_history':self .check_message_history ,
        'search_rules':self .search_rules ,
        'get_server_stats':self .get_server_stats ,
        'get_ticket_history':self .get_ticket_history ,
        'remember_fact':self .remember_fact ,
        'recall_facts':self .recall_facts ,
        'check_user_reputation':self .check_user_reputation ,
        'search_knowledge_base':self .search_knowledge_base ,
        'search_user_messages':self .search_user_messages ,
        'get_weekly_activity':self .get_weekly_activity ,
        'get_moderator_weekly':self .get_moderator_weekly ,
        }

    def get_available_functions (self )->str :
        """Возвращает описание доступных функций для AI"""
        return """
ДОСТУПНЫЕ ФУНКЦИИ (вызывай при необходимости):

1. get_user_warnings(user_id: int)
   Получить историю предупреждений пользователя
   Пример: get_user_warnings(123456789)

2. get_user_info(user_id: int)
   Получить информацию о пользователе (имя, дата регистрации, время на сервере)
   Пример: get_user_info(123456789)

3. get_user_roles(user_id: int)
   Получить список ролей пользователя
   Пример: get_user_roles(123456789)

4. check_message_history(user_id: int, limit: int = 10)
   Проверить последние сообщения пользователя
   Пример: check_message_history(123456789, 20)

5. search_rules(query: str)
   Поиск по правилам сервера
   Пример: search_rules("spam")

6. get_server_stats()
   Получить статистику сервера (участники, онлайн, каналы)
   Пример: get_server_stats()

7. get_ticket_history(user_id: int)
   Получить историю тикетов пользователя
   Пример: get_ticket_history(123456789)

8. remember_fact(user_id: int, fact: str)
   Запомнить важный факт о пользователе
   Пример: remember_fact(123456789, "Предпочитает краткие ответы")

9. recall_facts(user_id: int)
   Вспомнить все факты о пользователе
   Пример: recall_facts(123456789)

10. check_user_reputation(user_id: int)
    Проверить репутацию пользователя (предупреждения, муты, баны)
    Пример: check_user_reputation(123456789)

11. search_knowledge_base(query: str)
    Поиск по базе информации сервера (правила, FAQ, тикеты, заметки)
    Пример: search_knowledge_base("как войти в панель")

12. search_user_messages(user_id: str, query: str, limit: int = 5)
   Поиск по сообщениям пользователя (архив, до 48 часов)
   Пример: search_user_messages(user_id="123456789", query="mute")

13. get_weekly_activity(days: int = 7, limit: int = 15)
   Активность участников за период: и сообщения в чате, и время в войсе.
   Возвращает топ: у кого сколько сообщений и сколько времени в голосовых.
   Пример: get_weekly_activity(days=7)

14. get_moderator_weekly(days: int = 7)
   Недельная статистика модераторов: мод-действия (баны/кики/муты/варны),
   сообщения в чате и время в войсе — по каждому модератору.
   Пример: get_moderator_weekly(days=7)

ВАЖНО: для статистики активности/модераторов вызывай get_weekly_activity
или get_moderator_weekly (НЕ выдумывай другие имена — search_channel_activity
и подобные не существуют, используй get_weekly_activity).

ФОРМАТ ВЫЗОВА ФУНКЦИИ:
[FUNC:название_функции(параметр1=значение, параметр2=значение)]

ПРИМЕР:
[FUNC:get_user_warnings(user_id=123456789)]
"""


    async def execute_function (self ,func_call :str ,guild :discord .Guild )->Optional [str ]:
        """Vipolnyaet funkciyu из vizova AI"""
        try :
        # Отдельношtыrыyoruz vizov: [FUNC:name(param1=value1, param2=value2)]
            if not func_call .startswith ('[FUNC:')or not func_call .endswith (']'):
                return None 

            func_call =func_call [6 :-1 ]# Удален [FUNC: ve ]

            # Отдельношtыrыyoruz имя fonksiyonlar ve parametri
            if '('not in func_call or ')'not in func_call :
                return None 

            func_name =func_call .split ('(')[0 ].strip ()
            params_str =func_call .split ('(')[1 ].rsplit (')',1 )[0 ].strip ()

            # Алиасы: ИИ иногда зовёт функции «по смыслу» именами, которых
            # нет в реестре (search_channel_activity, get_activity...).
            # Мапим их на реальные функции вместо «функция не найдена».
            _aliases = {
                'search_channel_activity': 'get_weekly_activity',
                'get_channel_activity': 'get_weekly_activity',
                'channel_activity': 'get_weekly_activity',
                'get_activity': 'get_weekly_activity',
                'weekly_stats': 'get_weekly_activity',
                'get_staff_stats': 'get_moderator_weekly',
                'get_mod_stats': 'get_moderator_weekly',
                'moderator_activity': 'get_moderator_weekly',
            }
            func_name = _aliases.get(func_name, func_name)

            # Отдельношtыrыyoruz parametri
            params ={}
            if params_str :
                for param in params_str .split (','):
                    if '='in param :
                        key ,value =param .split ('=',1 )
                        key =key .strip ()
                        value =value .strip ()

                        # Konvertiruem tipi
                        if value .isdigit ():
                            value =int (value )
                        elif value .replace ('.','').isdigit ():
                            value =float (value )
                        elif value .lower ()in ('true','false'):
                            value =value .lower ()=='true'

                        params [key ]=value 

                        # Чтяжелыйыyoruz funkciyu
            if func_name not in self .functions :
                # Подсказка ИИ: такой функции нет — даём список реальных,
                # чтобы он не залипал на выдуманном имени.
                _avail = ", ".join(sorted(self.functions.keys()))
                _log.info("AI вызвал несуществующую функцию %s (доступны: %s)",
                          func_name, _avail)
                return (f"Ошибка: функция {func_name} не существует. "
                        f"Доступные функции: {_avail}. "
                        "Для статистики активности используй get_weekly_activity, "
                        "для модераторов — get_moderator_weekly. "
                        "Ответь пользователю на основе этого списка, не повторяй вызов.")

            result =await self .functions [func_name ](guild =guild ,**params )
            return str (result )

        except Exception as e :
            return f"Ошибка заверш fonksiyonlar: {str(e)}"

    async def get_user_warnings (self ,guild :discord .Guild ,user_id :int )->str :
        """Получить история предупреждение"""
        try :
            from cogs .warnings import load_warnings 
            warnings_data =load_warnings ()
            gid =str (guild .id )
            uid =str (user_id )

            user_warnings =warnings_data .get (gid ,{}).get (uid ,[])

            if not user_warnings :
                return f"U пользователь <@{user_id}> нет предупреждение."

            result =f"Предупреждения <@{user_id}> ({len(user_warnings)}):\n"
            for i ,варн in enumerate (user_warnings [-5 :],1 ):# последние 5
                result +=f"{i}. {варн.get('reason', 'Без причины')} — {варн.get('mod', '?')} ({варн.get('timestamp', '?')[:10]})\n"

            return result 
        except Exception as e :
            return f"Ошибка: {str(e)}"

    async def get_user_info (self ,guild :discord .Guild ,user_id :int )->str :
        """Получить информация о у пользователя"""
        try :
            member =guild .get_member (user_id )
            if not member :
                return f"Пользователь <@{user_id}> не найдено на на сервере."

            created =member .created_at .strftime ("%d.%m.%Y")
            joined =member .joined_at .strftime ("%d.%m.%Y")if member .joined_at else "?"
            days_on_server =(datetime.now(timezone.utc)-member .joined_at ).days if member .joined_at else 0 

            return (
            f"Информация о <@{user_id}>:\n"
            f"Имя: {member.display_name}\n"
            f"ID: {user_id}\n"
            f"Зарегистрирован: {created}\n"
            f"На сервере с: {joined} ({days_on_server} дн.)\n"
            f"Ролей: {len(member.roles)}"
            )
        except Exception as e :
            return f"Ошибка: {str(e)}"

    async def get_user_roles (self ,guild :discord .Guild ,user_id :int )->str :
        """Получить роли пользователь"""
        try :
            member =guild .get_member (user_id )
            if not member :
                return f"Пользователь <@{user_id}> не найдено."

            roles =[r .name for r in member .roles if r .name !="@everyone"]
            if not roles :
                return f"У <@{user_id}> нет ролей."

            return f"Роли <@{user_id}>: {', '.join(roles)}"
        except Exception as e :
            return f"Ошибка: {str(e)}"

    async def check_message_history (self ,guild :discord .Guild ,user_id :int ,limit :int =10 )->str :
        """Контроль et son сообщения пользователь"""
        try :
            from cogs .logs import _msg_cache 

            user_messages =[
            msg for msg in _msg_cache .values ()
            if msg .get ('author_id')==user_id 
            ][:limit ]

            if not user_messages :
                return f"Нет nedavnih сообщение из <@{user_id}> в kese."

            result =f"В конец {len(user_messages)} сообщение <@{user_id}>:\n"
            for msg in reversed (user_messages ):
                content =msg .get ('content','')[:100 ]
                channel =msg .get ('channel_name','?')
                result +=f"#{channel}: {content}\n"

            return result 
        except Exception as e :
            return f"Ошибка: {str(e)}"

    async def search_user_messages (self ,guild :discord .Guild ,user_id :int ,channel_id :int =0 ,limit :int =20 )->str :
        """Поиск сообщений пользователя: сначала Discord API, потом лог бота (fallback).

        Гибридный подход:
        1) Discord API (channel.history + search) — самый полный, но требует
           прав message_history и работает только когда бот онлайн.
        2) data/message_log_<guild_id>.json — fallback на случай офлайна/недоступности.

        Параметры:
            user_id — Discord user ID
            channel_id — 0 (все каналы) или конкретный канал
            limit — сколько сообщений вернуть (default 20, max 100)
        """
        try :
            import json as _json 
            uid =int (user_id )
            limit =max (1 ,min (int (limit )if str (limit ).isdigit ()else 20 ,100 ))

            # ── 1) DISCORD API DENEMESИ ──────────────────────────────────
            api_msgs =[]
            api_error =None 
            try :
                if channel_id and int (channel_id ):
                    ch =guild .get_channel (int (channel_id ))
                    if ch is None :
                        try :
                            ch =await guild .fetch_channel (int (channel_id ))
                        except Exception :
                            ch =None 
                    if ch is not None :
                    # Проверяем права бота
                        perms =ch .permissions_for (guild .me )
                        if perms .read_message_history and perms .read_messages :
                            async for msg in ch .history (limit =500 ):
                                if msg .author .id ==uid :
                                    api_msgs .append ({
                                    'channel_name':ch .name ,
                                    'channel_id':str (ch .id ),
                                    'content':msg .content or '[вложение/эмбед]',
                                    'timestamp':msg .created_at .isoformat (),
                                    'jump_url':msg .jump_url ,
                                    })
                                    if len (api_msgs )>=limit :
                                        break 
                else :
                # Все каналыda ara (bot online + yetkisi varsa)
                    text_channels =list (guild .text_channels )
                    for ch in text_channels :
                        try :
                            perms =ch .permissions_for (guild .me )
                            if not (perms .read_message_history and perms .read_messages ):
                                continue 
                                # Her каналda en son 500 сообщениеы tara (каналda
                                # mrxway'in написатьdыгы her шeyi bulmak для)
                            async for msg in ch .history (limit =500 ):
                                if msg .author .id ==uid :
                                    api_msgs .append ({
                                    'channel_name':ch .name ,
                                    'channel_id':str (ch .id ),
                                    'content':msg .content or '[вложение/эмбед]',
                                    'timestamp':msg .created_at .isoformat (),
                                    'jump_url':msg .jump_url ,
                                    })
                                    # 3x limit yeterli (en новый очередьda)
                                    if len (api_msgs )>=limit *3 :
                                        break 
                            if len (api_msgs )>=limit *3 :
                                break 
                        except (discord .Forbidden ,discord .HTTPException ) as _ex:
                            _log.debug("search_user_messages(): подавлено: %s", _ex)
                            continue 
            except Exception as e :
                api_error =str (e )
                api_msgs =[]

                # ── 2) FALLBACK: BOT LOG'U ──────────────────────────────────
            log_msgs =[]
            log_error =None 
            f =f'data/message_log_{guild.id}.json'
            if os .path .exists (f ):
                try :
                    with open (f ,'r',encoding ='utf-8')as fp :
                        logs =_json .load (fp )or []
                except (OSError ,_json .JSONDecodeError ,ValueError ):
                    logs =[]
                cid_filter =str (channel_id )if channel_id and int (channel_id )else None 
                log_msgs =[m for m in logs 
                if str (m .get ('author_id',''))==str (uid )
                and (cid_filter is None or str (m .get ('channel_id',''))==cid_filter )]

                # ── 3) BИRLEШTИR + SIRALA ─────────────────────────────────
                # Сначала результаты Discord API (самые новые), потом только из логов
            api_keys ={(m .get ('channel_id',''),m .get ('timestamp',''),m .get ('content','')[:100 ])
            for m in api_msgs }
            merged =list (api_msgs )
            for m in log_msgs :
                key =(m .get ('channel_id',''),m .get ('timestamp',''),(m .get ('content')or '')[:100 ])
                if key not in api_keys :
                    merged .append (m )

            if not merged :
                return (f"Сообщения от <@{user_id}> не найдены ни в Discord API, ни в логе бота.\n"
                "Возможные причины: пользователь ничего не писал, бот ещё не записал "
                "его сообщения, или у бота нет прав на чтение истории каналов.")

                # Новый → старый
            merged .sort (key =lambda x :x .get ('timestamp',''),reverse =True )
            merged =merged [:limit ]

            # ── 4) FORMATLA ────────────────────────────────────────────
            result_lines =[f"Найдено {len(merged)} сообщений от <@{uid}>"]
            if api_msgs :
                result_lines .append (f"Источник: Discord API ({len(api_msgs)} записей)")
            if log_msgs :
                not_in_api =sum (1 for m in log_msgs if (m .get ('channel_id',''),m .get ('timestamp',''),(m .get ('content')or '')[:100 ])not in api_keys )
                if not_in_api :
                    result_lines .append (f"Из лога бота (только бот был офлайн): ещё {not_in_api} сообщений")
            result_lines .append ("")

            for m in merged :
                ts =m .get ('timestamp','')[:19 ].replace ('T',' ')
                ch =m .get ('channel_name','?')
                txt =(m .get ('content')or '[вложение/эмбед]')[:300 ]
                line =f"• [{ts}] #{ch}: {txt}"
                if m .get ('jump_url'):
                    line +=f"\n  [Открыть]({m['jump_url']})"
                result_lines .append (line )

            if api_error :
                result_lines .append (f"\n⚠️ Discord API недоступен: {api_error}")
            if log_error :
                result_lines .append (f"\n⚠️ Ошибка чтения лога: {log_error}")

            return "\n".join (result_lines )
        except Exception as e :
        # Детальная диагностика — что именно упало внутри search_user_messages
            import traceback 
            err_type =type (e ).__name__ 
            err_msg =str (e )or "(пусто)"
            tb =traceback .format_exc ()
            # Сократим traceback до последних 5 строк
            tb_lines =[l for l in tb .splitlines ()if l .strip ()][-5 :]
            tb_short ='\n'.join (tb_lines )if tb_lines else '(нет traceback)'
            print (f'[AI-FUNC] search_user_messages CRASH: {err_type}: {err_msg}')
            print (f'[AI-FUNC] Traceback (last 5):\n{tb_short}')
            return (
            "⚠️ Ошибка в функции поиска сообщений\n\n"
            f"**Тип:** `{err_type}`\n"
            f"**Текст:** {err_msg[:200]}\n\n"
            "Возможные причины:\n"
            "• Бот не имеет прав на чтение истории каналов\n"
            "• Указанный пользователь не найден на сервере\n"
            "• Внутренняя ошибка бота (проверьте логи на [AI-FUNC])\n\n"
            "Подробности в логах бота: ищите строки `[AI-FUNC]`."
            )

    async def get_weekly_activity(self, guild: discord.Guild, days: int = 7,
                                  limit: int = 15) -> str:
        """Активность участников за период: сообщения в чате + время в войсе.

        Сообщения — из services.mod_activity.message_counts (пишутся
        on_message), войс — из cogs.voice_tracker (поле daily по дням).
        """
        try:
            days = max(1, min(30, int(days or 7)))
            limit = max(1, min(50, int(limit or 15)))
            # ── сообщения за период ──
            try:
                from services.mod_activity import message_counts
                msg = message_counts(guild.id, days=days)
            except Exception as _ex:
                _log.debug("get_weekly_activity: message_counts: %s", _ex)
                msg = {}
            # ── войс за период (сумма по последним `days` дням) ──
            voice_sec = {}
            voice_name = {}
            try:
                from cogs import voice_tracker as _vt
                from datetime import date as _date, timedelta as _td
                days_set = {str(_date.today() - _td(days=i)) for i in range(days)}
                for uid, rec in _vt.voice_all(guild.id).items():
                    daily = rec.get('daily') or {}
                    secs = 0
                    for d, v in daily.items():
                        if d in days_set:
                            try:
                                secs += int(v or 0)
                            except (TypeError, ValueError) as _ve:
                                _log.debug("weekly voice: битое %r за %s: %s", v, d, _ve)
                                secs += 0  # битое значение дня пропускаем
                    if secs > 0:
                        voice_sec[str(uid)] = secs
                        voice_name[str(uid)] = rec.get('name') or uid
            except Exception as _ex:
                _log.debug("get_weekly_activity: voice: %s", _ex)

            uids = set(msg) | set(voice_sec)
            if not uids:
                return (f"За последние {days} дн. активности не записано "
                        "(бот только начал собирать статистику или сообщений/войса не было).")

            rows = []
            for uid in uids:
                m = int(msg.get(uid, {}).get('messages', 0) or 0)
                s = int(voice_sec.get(uid, 0) or 0)
                name = (msg.get(uid, {}).get('name') or voice_name.get(uid)
                        or uid)
                rows.append((uid, str(name)[:24], m, s))
            # сортируем по суммарной активности (сообщения + эквивалент в сек)
            rows.sort(key=lambda r: (r[2] * 60 + r[3]), reverse=True)
            top = rows[:limit]

            def _fmt_voice(secs):
                m_, s_ = divmod(secs, 60)
                h_, m_ = divmod(m_, 60)
                if h_:
                    return f"{h_}ч {m_}м"
                if m_:
                    return f"{m_}м"
                return f"{s_}с"

            lines = [f"📊 Активность за {days} дн. (топ {len(top)}):"]
            medals = ['🥇', '🥈', '🥉']
            for i, (uid, name, m, s) in enumerate(top):
                pref = medals[i] if i < 3 else f"`{i+1}.`"
                parts = [f"**{name}**"]
                parts.append(f"💬 {m} сообщ.")
                if s:
                    parts.append(f"🎙 {_fmt_voice(s)} в войсе")
                lines.append(f"{pref} {' · '.join(parts)}")
            lines.append("\nДанные собираются с момента работы бота; "
                         "период раньше старта статистики не виден.")
            return "\n".join(lines)
        except Exception as e:
            return f"Ошибка при сборе активности: {e}"

    async def get_moderator_weekly(self, guild: discord.Guild,
                                   days: int = 7) -> str:
        """Недельная статистика модераторов: действия + сообщения + войс."""
        try:
            days = max(1, min(30, int(days or 7)))
            # мод-действия (бан/кик/мут/варн и т.п.) из cogs.staff_stats
            try:
                from cogs.staff_stats import collect_actions, summarize, _breakdown
                actions = collect_actions(guild.id)
                per = summarize(actions, days=days)
            except Exception as _ex:
                _log.debug("get_moderator_weekly: staff_stats: %s", _ex)
                per = {}
            # сообщения
            try:
                from services.mod_activity import message_counts
                msg = message_counts(guild.id, days=days)
            except Exception as _ex:
                _log.debug("get_moderator_weekly: message_counts: %s", _ex)
                msg = {}
            # войс по дням
            voice_sec = {}
            try:
                from cogs import voice_tracker as _vt
                from datetime import date as _date, timedelta as _td
                days_set = {str(_date.today() - _td(days=i)) for i in range(days)}
                for uid, rec in _vt.voice_all(guild.id).items():
                    daily = rec.get('daily') or {}
                    secs = sum(int(daily.get(d, 0) or 0) for d in days_set)
                    if secs > 0:
                        voice_sec[str(uid)] = secs
            except Exception as _ex:
                _log.debug("get_moderator_weekly: voice: %s", _ex)

            mod_ids = set(per)
            # добавим тех, у кого есть мод-действия; имя берём из сервера
            if not mod_ids:
                return (f"За последние {days} дн. модераторских действий не "
                        "записано (варны/муты/баны не выносились или бот недавно).")

            def _name(uid):
                mem = None
                try:
                    mem = guild.get_member(int(uid))
                except (TypeError, ValueError) as _ne:
                    _log.debug("moderator name: uid %r не парсится: %s", uid, _ne)
                if mem is not None:
                    return mem.display_name
                return (msg.get(uid, {}).get('name') or uid)

            rows = []
            for uid in mod_ids:
                ent = per.get(uid, {})
                total = int(ent.get('total', 0) or 0)
                breakdown = _breakdown(ent.get('by', {})) if ent.get('by') else '—'
                m = int(msg.get(uid, {}).get('messages', 0) or 0)
                s = int(voice_sec.get(uid, 0) or 0)
                rows.append((uid, _name(uid), total, breakdown, m, s))
            rows.sort(key=lambda r: r[2], reverse=True)

            def _fmt_voice(secs):
                m_, _ = divmod(secs, 60)
                h_, m_ = divmod(m_, 60)
                return f"{h_}ч {m_}м" if h_ else (f"{m_}м" if m_ else "0м")

            medals = ['🥇', '🥈', '🥉']
            lines = [f"🛡 Активность модераторов за {days} дн. ({len(rows)} чел.):"]
            for i, (uid, name, total, breakdown, m, s) in enumerate(rows):
                pref = medals[i] if i < 3 else f"`{i+1}.`"
                lines.append(
                    f"{pref} **{str(name)[:24]}** — действий: **{total}**\n"
                    f"    {breakdown} · 💬 {m} сообщ."
                    + (f" · 🎙 {_fmt_voice(s)} в войсе" if s else ""))
            return "\n".join(lines)
        except Exception as e:
            return f"Ошибка при сборе статистики модераторов: {e}"

    async def search_rules (self ,guild :discord .Guild ,query :str )->str :
        """Arama по правил сервер"""
        try :
            rules_file =f"data/rules_{guild.id}.json"
            if not os .path .exists (rules_file ):
                return "Правила сервер не найден."

            with open (rules_file ,'r',encoding ='utf-8')as f :
                rules_data =json .load (f )

            rules =rules_data .get ('rules',[])
            query_lower =query .lower ()

            matches =[
            rule for rule in rules 
            if query_lower in rule .get ('text','').lower ()
            ]

            if not matches :
                return f"Не найдено правила по sorguyu '{query}'."

            result =f"Найдено {len(matches)} правила:\n"
            for i ,rule in enumerate (matches [:5 ],1 ):
                result +=f"{i}. {rule.get('text', '')}\n"

            return result 
        except Exception as e :
            return f"Ошибка: {str(e)}"

    async def get_server_stats (self ,guild :discord .Guild )->str :
        """Получить статистику сервера"""
        try :
            total_members =guild .member_count 
            online_members =len ([m for m in guild .members if m .status ==discord .Status .online ])
            text_channels =len (guild .text_channels )
            voice_channels =len (guild .voice_channels )
            return (
            f"Статистика сервера {guild.name}:\n"
            f"Участников: {total_members} (в сети: {online_members})\n"
            f"Текстовых каналов: {text_channels}\n"
            f"Голосовых каналов: {voice_channels}\n"
            f"Ролей: {len (guild .roles )}\n"
            f"Ролей: {len(guild.roles)}"
            )
        except Exception as e :
            return f"Ошибка: {str(e)}"

    async def get_ticket_history (self ,guild :discord .Guild ,user_id :int )->str :
        """Получить историю тикетов"""
        try :
            ticket_file =f"data/tickets_{guild.id}.json"
            if not os .path .exists (ticket_file ):
                return f"У <@{user_id}> нет истории тикетов."

            with open (ticket_file ,'r',encoding ='utf-8')as f :
                tickets_data =json .load (f )

            user_tickets =[
            t for t in tickets_data .get ('tickets',[])
            if t .get ('user_id')==user_id 
            ]

            if not user_tickets :
                return f"У <@{user_id}> нет тикетов."

            result =f"Ticketlar <@{user_id}> ({len(user_tickets)}):\n"
            for ticket in user_tickets [-5 :]:# В конец 5
                status =ticket .get ('status','?')
                category =ticket .get ('category','?')
                created =ticket .get ('created_at','?')[:10 ]
                result +=f"- {category} ({status}) — {created}\n"

            return result 
        except Exception as e :
            return f"Ошибка: {str(e)}"

    async def remember_fact (self ,guild :discord .Guild ,user_id :int ,fact :str )->str :
        """Zapomnit fakt о у пользователя"""
        try :
            memory_file ='data/ai_memory.json'
            memory ={}

            if os .path .exists (memory_file ):
                with open (memory_file ,'r',encoding ='utf-8')as f :
                    memory =json .load (f )

            user_key =str (user_id )
            if user_key not in memory :
                memory [user_key ]=[]

            memory [user_key ].append ({
            'fact':fact ,
            'timestamp':datetime.now(timezone.utc).isoformat ()
            })

            # Ограничиваем 50 faktami
            if len (memory [user_key ])>50 :
                memory [user_key ]=memory [user_key ][-50 :]

            with open (memory_file ,'w',encoding ='utf-8')as f :
                json .dump (memory ,f ,ensure_ascii =False ,indent =2 )

            return f"Zapomnil: {fact}"
        except Exception as e :
            return f"Ошибка: {str(e)}"

    async def recall_facts (self ,guild :discord .Guild ,user_id :int )->str :
        """Vspomnit fakti о у пользователя"""
        try :
            memory_file ='data/ai_memory.json'
            if not os .path .exists (memory_file ):
                return f"Нет сохранённых фактов о <@{user_id}>."

            with open (memory_file ,'r',encoding ='utf-8')as f :
                memory =json .load (f )

            user_key =str (user_id )
            facts =memory .get (user_key ,[])

            if not facts :
                return f"Нет сохранённых фактов о <@{user_id}>."

            result =f"Fakti о <@{user_id}> ({len(facts)}):\n"
            for fact_data in facts [-10 :]:# В конец 10
                fact =fact_data .get ('fact','')
                result +=f"- {fact}\n"

            return result 
        except Exception as e :
            return f"Ошибка: {str(e)}"

    async def check_user_reputation (self ,guild :discord .Guild ,user_id :int )->str :
        """Проверить репутацию пользователя"""
        try :
            warnings_text =await self .get_user_warnings (guild ,user_id )
            info_text =await self .get_user_info (guild ,user_id )
            tickets_text =await self .get_ticket_history (guild ,user_id )

            return (
            f"=== REPUTACIYa <@{user_id}> ===\n\n"
            f"{info_text}\n\n"
            f"{warnings_text}\n\n"
            f"{tickets_text}"
            )
        except Exception as e :
            return f"Ошибка: {str(e)}"

    async def search_knowledge_base (self ,guild :discord .Guild ,query :str )->str :
        """Arama по tabanda информация сервер (правила, FAQ, ticketlar, notlar)"""
        try :
            from web .ai_rag import get_knowledge_base 

            kb =get_knowledge_base (guild .id )
            context =kb .get_context_for_query (query )

            if not context :
                return f"Не найдено informacii в tabanda информация по sorguyu: {query}"

            return context 
        except Exception as e :
            return f"Ошибка aramaa в tabanda информация: {str(e)}"
