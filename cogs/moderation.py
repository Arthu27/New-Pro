
from logger import get_logger

_log = get_logger("moderation")

import discord 
from discord .ext import commands ,tasks 
from discord import app_commands 
from datetime import datetime ,timedelta ,timezone 
import json 
import os 
import time 
from cogs .embed_utils import gif ,now_ts ,mod_dm_embed ,mod_log_embed ,success_embed ,error_embed 

from logger import get_logger 
log =get_logger ("moderation")


DIVIDER ="✦ ───────────────────── ✦"


async def _respond (interaction ,**kw ):
    """Ответить на interaction максимально надёжно.

    Первый ответ — response.send_message; если уже был defer/ответ —
    followup. Ошибки самой отправки глушим с записью в журнал: модератор
    НИКОГДА не должен видеть «Приложение не отвечает» при выполненном
    наказании.
    """
    try :
        if interaction .response .is_done ():
            await interaction .followup .send (**kw )
        else :
            await interaction .response .send_message (**kw )
    except Exception as _e :
        log .info (f'[MODPANEL] Ответ не доставлен: {_e}')
        try :
            await interaction .followup .send (**kw )
        except Exception as _e2 :
            log .warning (f'[MODPANEL] Ответ не доставлен и через followup: {_e2}')


# ── Длительности: понятный ввод + потолок из панели ──────────────────────
import re as _re_mod

_DUR_UNITS = [
    (('д', 'дн', 'd', 'day', 'день', 'дня', 'дней'), 1440),
    (('ч', 'h', 'hour', 'час', 'часа', 'часов'), 60),
    (('м', 'm', 'min', 'мин', 'минут', 'минута', 'минуты'), 1),
    (('н', 'w', 'нед', 'недел', 'week'), 10080),
]


def parse_duration_minutes(raw, default=5):
    """'90' → 90 мин; '1ч'/'2 часа'/'1h' → 60/120; '1д' → 1440; '30м' → 30.

    Понимает опечатки и русские/английские единицы. Не понял — default.
    """
    txt = str(raw or '').strip().lower().replace(' ', '')
    if not txt:
        return default
    m = _re_mod.match(r'^(\d+(?:[.,]\d+)?)(.*)$', txt)
    if not m:
        return default
    num = float(m.group(1).replace(',', '.'))
    unit = m.group(2)
    if not unit:
        return max(1, int(num))                      # просто число = минуты
    for variants, mult in _DUR_UNITS:
        if unit.startswith(variants):
            return max(1, int(num * mult))
    return default


def human_duration(minutes):
    minutes = int(minutes)
    if minutes % 1440 == 0 and minutes >= 1440:
        d = minutes // 1440
        return f'{d} дн'
    if minutes % 60 == 0 and minutes >= 60:
        return f'{minutes // 60} ч'
    return f'{minutes} мин'

class Moderation (commands .Cog ):
    def __init__ (self ,bot ):
        self .bot =bot 
        try :
            if not self .punish_roles_loop .is_running ():
                self .punish_roles_loop .start ()
        except Exception as _ex :
            log .debug (f'punish_roles_loop старт: {_ex}')

    def save_case (self ,guild_id ,action ,user_id ,mod_id ,reason ):
        os .makedirs ('data',exist_ok =True )
        filepath ='data/mod_data.json'
        try :
            data ={'cases':{}}
            if os .path .exists (filepath ):
                with open (filepath ,'r',encoding ='utf-8')as f :
                    loaded =json .load (f )
                # Устойчивость: файл могли записать другие коги с другой схемой
                # (например, {'case': ..., 'notes': ...}). Не теряем их записи,
                # а лишь гарантируем ключ 'cases'.
                if isinstance (loaded ,dict ):
                    data =loaded
                data .setdefault ('cases',{})
            gid =str (guild_id )
            if gid not in data ['cases']:
                data ['cases'][gid ]=[]
            case_id =len (data ['cases'][gid ])+1 
            data ['cases'][gid ].append ({
            'id':case_id ,'action':action ,
            'user_id':str (user_id ),'mod_id':str (mod_id ),
            'reason':reason or 'Не указана',
            'timestamp':datetime .now (timezone .utc ).isoformat ()
            })
            with open (filepath ,'w',encoding ='utf-8')as f :
                json .dump (data ,f ,indent =2 ,ensure_ascii =False )
            return case_id 
        except Exception as e :
            log .info (f"[MOD] Ошибка сохранения дел: {e}")
            return 0 

    async def send_log (self ,guild ,embed ):
        # Общий резолвер: -модерация → legacy (mod-log, moderasyon) → server-log …
        ch =None
        try :
            from cogs .logs import find_log_channel
            ch =find_log_channel (guild ,'модерация')
        except Exception :
            ch =None
        if not ch :
            ch =discord .utils .get (guild .text_channels ,name ="mod-log")
        if not ch :
            ch =discord .utils .get (guild .text_channels ,name ="moderasyon")
        if ch :
            try :
                await ch .send (embed =embed )
            except Exception as _ex:
                _log.debug("send_log(): подавлено: %s", _ex)

    async def _notify_owner (self ,action ,user ,mod ,reason =None ):
        from config import clean_number
        owner_id = clean_number(os.getenv('OWNER_ID')) or 0
        if not owner_id or not mod or mod .id ==owner_id :
            return 
        flag_file ='data/mod_notify.json'
        try :
            enabled =json .load (open (flag_file ,encoding ='utf-8')).get ('enabled',False )if os .path .exists (flag_file )else False 
        except Exception :
            enabled =False 
        if not enabled :
            return 
        try :
            owner =await self .bot .fetch_user (owner_id )
            name =user .display_name if hasattr (user ,'display_name')else str (user )
            msg =f"**{action.upper()}** — {name} | Mod: {mod.display_name}"
            if reason :
                msg +=f" | Причина: {reason}"
            await owner .send (msg )
        except Exception as _ex:
            _log.debug("_notify_owner(): подавлено: %s", _ex)

    async def send_dm (self ,user ,embed ):
        # DM — шаг best-effort: закрытые ЛС/сетевые сбои НЕ должны
        # отменять наказание или превращать его в «ошибку» для модератора
        try :
            await user .send (embed =embed )
        except Exception as _ex:
            _log.debug("send_dm(): подавлено: %s", _ex)

    def _confirm_embed (self ,action ,user ,guild ,reason ,case_id ,extra ="" ,moderator =None ):
        """Embed подтверждения для модератора — чистый стиль без эмодзи:
        заголовок-результат, карточка участника, поля, однострочный футер."""
        moderator =moderator or (guild .me if guild else None )
        configs ={
        "ban":("Бан выполнен",0xE74C3C ,"забанен"),
        "kick":("Кик выполнен",0xE67E22 ,"кикнут с сервера"),
        "timeout":("Мут выполнен",0xF39C12 ,"временно замьючен"),
        "untimeout":("Мут снят",0x2ECC71 ,"мут снят"),
        "unban":("Бан снят",0x2ECC71 ,"разбанен"),
        }
        title ,color ,action_text =configs .get (action ,("Действие выполнено",0x2ECC71 ,"применено"))

        e =discord .Embed (title =title ,
        description =f"**{user.display_name}** — {action_text}\nID: `{user.id}`",
        color =color ,timestamp =datetime .now (timezone .utc ))

        e .add_field (name ="Причина",value =(reason or "Не указана")[:1000],inline =True )
        e .add_field (name ="Модератор",value =(moderator .mention if moderator else "—"),inline =True )
        if extra :
            e .add_field (name ="Детали",value =str (extra )[:1000],inline =False )

        e .set_thumbnail (url =user .display_avatar .url )

        if guild .icon :
            e .set_footer (text =f"{guild.name} · дело #{case_id} · ЛС отправлено",
            icon_url =guild .icon .url )
        else :
            e .set_footer (text =f"{guild.name} · дело #{case_id} · ЛС отправлено")

        return e 


            # /роли 


        # /leaveguild 

    # ═══════════════════════════════════════════════════════════════════


    #  /modpanel — панель модерации через select-меню════════════════════════════════════════════════════════════════
    @app_commands.command(name="modpanel", description="Панель модерации (выпадающее меню)")
    # Доступ к /modpanel решает ВЛАДЕЛЕЦ через веб-панель (Доступ → Права
    # команд): раньше тут висели default_permissions(moderate_members=True) и
    # checks.has_permissions(moderate_members=True) — это запрещало команду на
    # стороне самого Discord, и выданная в панели роль всё равно «не включала»
    # доступ (Discord блокировал команду до панельной проверки ACL). Теперь
    # команда видна всем, а выполнять её разрешает ролевой ACL (has_access в
    # main.py) + actions_for_member ниже фильтрует действия по ролям.
    async def modpanel (self ,interaction ):
        # Роли решают, что видно: если у ролей модератора заданы свои лимиты,
        # в меню попадают ТОЛЬКО настроенные действия (владелец видит всё).
        allowed =actions_for_member (interaction .guild ,interaction .user )
        if not allowed :
            await _respond (interaction ,
            embed =error_embed (
            'Тебе пока не доступно ни одного действия. Владелец настраивает '
            'их в панели: Щит сервера → Лимиты команды → роль.'),
            ephemeral =True )
            return 
        _u =interaction .user 
        # Компактная карточка: владелец просил «слишком много инфы» —
        # только строка-подсказка и само выпадающее меню, без простыней.
        embed =discord .Embed (
        title ="🛡 Панель модерации",
        description ="Выберите действие в меню ниже — укажете цель, срок и причину.",
        color =0x5865F2 )
        if interaction .guild .icon :
            embed .set_footer (text =interaction .guild .name )
        await _respond (interaction ,embed =embed ,view =ModPanelView (self ,interaction .user ,allowed ),ephemeral =True )

    def _parse_target_id (self ,target :str ):
        """Из '@упоминание' или '123456789' вернуть int ID (или None)."""
        if not target :
            return None
        import re as _re
        m =_re .search (r'(\d{15,22})',target )
        if m :
            return int (m .group (1 ))
        return None

    def _resolve_member (self ,guild ,target ):
        """Найти участника по строке из модалки: @упоминание, ID или ТОЧНЫЙ ник.

        Возвращает (user, uid). uid может быть найден без user (оффлайн/ушёл —
        добираем через fetch_user выше по стеку), user без uid не бывает.
        Точный ник: совпадение с username / отображаемым / ником на сервере
        (без учёта регистра); неоднозначность → (None, None), мод уточнит.
        """
        uid =self ._parse_target_id (target )
        if uid :
            return discord .utils .get (guild .members ,id =uid ),uid
        name =(target or '').strip ().lstrip ('@').strip ().casefold ()
        if len (name )<2 :
            return None ,None
        cands =[u for u in guild .members
        if name in (str (getattr (u ,'name','')).casefold (),
        str (getattr (u ,'global_name','')or '').casefold (),
        str (getattr (u ,'display_name','')).casefold ())]
        if len (cands )==1 :
            return cands [0 ],cands [0 ].id
        return None ,None

    # ── Апелляция («бан») ─────────────────────────────────────────────
    # «Бан» больше НЕ выгоняет с сервера: у участника закрываются все каналы,
    # открытым остаётся только один — канал апелляции, где он обжалует бан.
    async def _isolation_channel (self ,guild ):
        """Канал апелляции из панели (Каналы и маршруты → «Канал апелляции (бан)»).

        Канал выбирает владелец сам — бот ничего не создаёт. Не настроен —
        «бан» из панели не работает (об этом прямо говорит модератору).
        """
        try :
            from services .channel_routes import get_route as _gr 
            cid =int (_gr (guild .id ,'ban_appeal_channel')or 0)
        except Exception as _ex :
            log .debug (f'[MODPANEL] канал апелляции: {_ex}')
            return None 
        if not cid :
            return None 
        return guild .get_channel (cid )

    async def _isolate_member (self ,guild ,user ,iso ):
        """Закрыть все каналы для участника, оставить открытым канал апелляции."""
        if iso is None :
            return None ,0
        deny =discord .PermissionOverwrite (view_channel =False ,send_messages =False ,
        connect =False ,speak =False )
        allow =discord .PermissionOverwrite (view_channel =True ,send_messages =True )
        closed =0
        for ch in guild .channels :
            if ch ==iso :
                continue
            try :
                await ch .set_permissions (user ,overwrite =deny )
                closed +=1
            except Exception as _ex :
                log .debug (f'_isolate_member(): {ch}: {_ex}')
        if iso is not None :
            try :
                await iso .set_permissions (user ,overwrite =allow )
            except Exception as _ex :
                log .debug (f'_isolate_member(): iso: {_ex}')
        return iso ,closed

    async def _unisolate_member (self ,guild ,user ):
        """Снять апелляцию: вернуть участнику обычный доступ ко всем каналам."""
        for ch in guild .channels :
            try :
                await ch .set_permissions (user ,overwrite =None )
            except Exception as _ex :
                log .debug (f'_unisolate_member(): {ch}: {_ex}')

    # ── Почему Forbidden: иерархия ролей / владелец сервера / право бота ──
    _NEED_PERMS = {
        'ban': ('ban_members', 'Бан участников'),
        'kick': ('kick_members', 'Выгонять участников'),
        'timeout': ('moderate_members', 'Модерация участников (таймаут)'),
        'mute_chat': ('manage_roles', 'Управление ролями (мут-роль)'),
        'vmute': ('manage_roles', 'Управление ролями (мут-роль)'),
    }

    async def preflight_reason(self, guild, user, action):
        """Проверить ЗАРАНЕЕ, хватит ли боту прав (до попытки и до записи
        дела в базу). None — всё ок, иначе — причина для модератора."""
        try:
            me = guild.me
            if not me:
                return None
            # снять наказание можно и без иерархии; выдать — нет
            if (action not in ('unban', 'untimeout', 'vunmute', 'clear')
                    and user and getattr(user, 'id', None) == guild.owner_id):
                return 'Это владелец сервера — применить к нему наказание нельзя в принципе.'
            if (action in self._NEED_PERMS and user
                    and getattr(user, 'top_role', None) is not None
                    and user.top_role >= me.top_role):
                return (f'Роль бота ({me.top_role.name}) стоит не выше роли '
                        f'«{user.top_role.name}» нарушителя — Discord не позволит '
                        'действие. Поднимите роль бота: Настройки сервера → Роли.')
            perm, label = self._NEED_PERMS.get(action, (None, None))
            if perm and not getattr(me.guild_permissions, perm, False):
                return (f'Боту не выдано право «{label}». '
                        'Настройки сервера → Роли → роль бота.')
        except Exception:
            return None
        return None

    async def _forbidden_reason(self, guild, user, action):
        """Человеческое объяснение discord.Forbidden — что именно проверить."""
        try:
            me = guild.me
            if user and getattr(user, 'id', None) == guild.owner_id:
                return 'Это владелец сервера — применить наказание к нему нельзя.'
            if user and me and user.top_role >= me.top_role:
                return (f'Роль бота ({me.top_role.name}) стоит не выше роли '
                        f'«{user.top_role.name}». Поднимите роль бота: '
                        'Настройки сервера → Роли → перетащите роль бота выше.')
            perm, label = self._NEED_PERMS.get(action, (None, None))
            if perm and me and not getattr(me.guild_permissions, perm, False):
                return f'Боту не выдано право «{label}». Настройки сервера → Роли → роль бота.'
        except Exception as _fre:
            log.debug('forbidden_reason: подавлено: %s', _fre)
        return ('Проверьте: роль бота выше роли нарушителя и у бота есть нужное '
                'право (Настройки сервера → Роли).')

    async def _execute_mod_action (self ,interaction ,action ,target ,reason ,amount ,proof_link =None ):
        """Выполнить выбранное действие модерации."""
        guild =interaction .guild

        # Лимиты стаффа — защита от «плохих» модераторов (владельца не трогаем).
        # С 2026-08 лимитируется ВСЁ: варны, муты, баны, чистка — и действует
        # САМЫЙ СТРОГИЙ лимит среди ролей модератора (пер-рольные лимиты).
        try :
            _sl_key ={'warn':'warn','timeout':'mute','mute_chat':'mute','vmute':'mute',
            'untimeout':'unmute','vunmute':'unmute','unban':'unban',
            'ban':'ban','clear':'clear','kick':'kick'}.get (action )
            _sl_uid =getattr (interaction .user ,'id',0 )
            try :
                from config import Config as _Cfg
                _sl_bot_owner =_sl_uid in _Cfg .all_owner_ids ()
            except Exception :
                _sl_bot_owner =False
            _sl_panel =getattr (interaction .user ,'is_panel',False )
            if _sl_key and guild and not _sl_bot_owner and not _sl_panel \
            and _sl_uid !=getattr (guild ,'owner_id',0 ):
                from services .staff_limits import check_limit as _sl_check ,ACTION_TITLES 
                if action =='clear':
                    try :
                        _sl_amt =max (1 ,min (int (amount )or 10 ,200 ))
                    except Exception :
                        _sl_amt =10
                else :
                    _sl_amt =1
                _sl_roles =[]
                try :
                    _sl_roles =[r .id for r in (getattr (interaction .user ,'roles',None )or [])
                    if getattr (r ,'id',None )!=getattr (guild ,'id',None )]
                except Exception :
                    _sl_roles =[]
                _sl_ok ,_sl_used ,_sl_lim =_sl_check (guild .id ,interaction .user .id ,_sl_key ,_sl_amt ,role_ids =_sl_roles )
                if not _sl_ok :
                    _what =ACTION_TITLES .get (_sl_key ,'действий' )
                    _left =max (0 ,_sl_lim -_sl_used )
                    _txt =f'Лимит исчерпан: {_sl_lim} {_what} (использовано {_sl_used}, осталось {_left}).'
                    try :
                        from services .staff_limits import refresh_in_text as _sl_refresh
                        _when =_sl_refresh (guild .id ,interaction .user .id ,_sl_key )
                        if _when :_txt +=f' Обновится через {_when}.'
                    except Exception as _sx :_log .debug ('[MODPANEL] staff_limits refresh: %s',_sx )
                    _txt +=' Настраивается: панель → Щит сервера → Лимиты.'
                    await _respond (interaction ,
                    embed =error_embed (_txt),
                    ephemeral =True )
                    return
                # Потолок длительности мута (панель → Щит → Лимиты):
                # просит дольше разрешённого — вежливый отказ, а не молчание
                if action in ('timeout','mute_chat'):
                    try :
                        from services .staff_limits import effective_max_duration as _sl_cap
                        _cap =_sl_cap (guild .id ,'mute',_sl_roles )
                        if _cap :
                            _minutes_req =parse_duration_minutes (amount ,5 )
                            if _minutes_req *60 >_cap :
                                await _respond (interaction ,
                                embed =error_embed (
                                f'Мут дольше разрешённого: тебе можно давать мут '
                                f'только до {human_duration (max (1,_cap //60 ))}, а ты просишь '
                                f'{human_duration (_minutes_req )}. '
                                f'Потолок настраивается: панель → Щит сервера → Лимиты.'),
                                ephemeral =True )
                                return
                    except Exception as _cex :
                        log .debug (f'[STAFF_LIMIT][dur] {_cex}')
        except Exception as _le :
            log .debug (f'[STAFF_LIMIT] {_le}')

        # Наказания — только с доказательством (ссылкой на скрин/видео):
        # модальные окна Discord не принимают вложения, поэтому через панель
        # доказательство передаётся ссылкой.
        _punish_actions =("ban","timeout","mute_chat","vmute")
        if action in _punish_actions :
            from cogs .proof_cog import require_proof
            _action_ru ={'ban':'апелляция','kick':'кик','timeout':'мут','mute_chat':'мут чата','vmute':'войс-мут'}[action ]
            if not await require_proof (interaction ,action_ru =_action_ru ,link =proof_link ):
                return

        if action =="warn":
            user ,uid =self ._resolve_member (guild ,target )
            if not user and uid :
                try :
                    user =await self .bot .fetch_user (uid )
                except Exception :
                    user =None
            if not uid :
                await _respond (interaction ,embed =error_embed (
                'Не нашёл участника по цели. Нужен @ник, ТОЧНОЕ имя или ID.'),
                ephemeral =True )
                return
            ok ,text =await self .apply_panel_action (
            guild ,(user if user is not None else uid ),'warn',
            reason =reason ,actor =getattr (interaction .user ,'display_name','Модератор'))
            if ok :
                who =getattr (user ,'display_name',None )or str (uid )
                await _respond (interaction ,embed =success_embed (
                'Варн выдан',f'**{who }** · `{uid }`\n{text }',guild =guild ),
                ephemeral =True )
            else :
                await _respond (interaction ,embed =error_embed (text ),ephemeral =True )
            return

        if action in ("ban","kick","timeout","mute_chat","untimeout","vmute","vunmute"):
            user ,uid =self ._resolve_member (guild ,target )
            if not user and uid :
                try :
                    user =await self .bot .fetch_user (uid )
                except Exception :
                    user =None
            if not user :
                await _respond (interaction ,
                embed =error_embed ("Пользователь не найден. Укажите @упоминание, точный ник или ID — ровно как на сервере."),
                ephemeral =True )
                return

            # Предпроверка прав бота: знаем ЗАРАНЕЕ, получится ли действие,
            # и дело в базу не пишется зря
            _pre =await self .preflight_reason (guild ,user ,action )
            if _pre :
                await _respond (interaction ,
                embed =error_embed (_pre ,"У бота не хватит прав"),ephemeral =True )
                return

            try :
                if action =="ban":
                    # «Бан» не выкидывает с сервера: все каналы закрываются,
                    # открыт только канал апелляции из панели. Без настроенного
                    # канала действие не выполняется — говорим, чего не хватает.
                    _iso =await self ._isolation_channel (guild )
                    if _iso is None :
                        await _respond (interaction ,
                        embed =error_embed (
                        'Настройки не завершены: не выбран канал апелляции. '
                        'Панель → Каналы и маршруты → «Канал апелляции (бан)». '
                        'Пока канал не выбран, «бан» из панели не работает.'),
                        ephemeral =True )
                        return 
                    _closed =await self ._isolate_member (guild ,user ,_iso )
                    _brole =self ._punish_role (guild ,'ban')
                    if _brole is not None :
                        # роль бана: каналы закрывает сама роль (настрой её права),
                        # бот лишь открывает участнику канал апелляции
                        try :
                            await _iso .set_permissions (user ,overwrite =discord .PermissionOverwrite (view_channel =True ,send_messages =True ))
                        except Exception as _pe :
                            log .debug (f'[MODPANEL] allow апелляции: {_pe}')
                        await user .add_roles (_brole ,reason =reason or 'бан')
                        msg =f"🚫 роль бана «{_brole .name }» + канал апелляции {_iso .mention }"
                    else :
                        _closed =await self ._isolate_member (guild ,user ,_iso )
                        msg =f"🚫 апелляция: закрыто каналов {_closed }, открыт {_iso .mention }"
                    try :
                        from services .staff_limits import record_hit as _sl_rec
                        _sl_rec (guild .id ,interaction .user .id ,'ban',1 )
                    except Exception as _re :
                        log .debug (f'[STAFF_LIMIT] ban rec: {_re}')
                elif action =="kick":
                    # Система kick полностью отключена решением владельца (2026-08):
                    # опция убрана из меню, ручные вызовы — вежливый отказ.
                    if interaction .response .is_done ():
                        await interaction .followup .send ("🛡 Кик отключён на этом сервере — используй мут или апелляцию.",ephemeral =True )
                    else :
                        await interaction .response .send_message ("🛡 Кик отключён на этом сервере — используй мут или апелляцию.",ephemeral =True )
                    return 
                elif action == "timeout":
                    # «Мут (чат + войс)» — это ОДНО нативное состояние Discord:
                    # member.timeout() глушит И текст, И голос одновременно.
                    # Роль так не умеет (роль закрывает только чат), поэтому
                    # таймаут ВСЕГДА нативный — это и есть «за раз и чат, и войс».
                    # Сначала снимаем любые отдельные мут-роли/серверное
                    # заглушение, чтобы на участнике не осталось второго мута.
                    minutes = parse_duration_minutes(amount, 5)
                    minutes = max(1, min(minutes, 40320))  # потолок Discord — 28 дней
                    try:
                        from services import mute_state
                        await mute_state.clear_all_mutes(guild, user)
                    except Exception as _mse:
                        log.debug(f'[MODPANEL] timeout clear all: {_mse}')
                    until = datetime.now(timezone.utc) + timedelta(minutes=minutes)
                    await user.timeout(until, reason=reason)
                    msg = (f"🔇 таймаут на {human_duration(minutes)} "
                           f"(~{minutes} мин) — закрыты и чат, и голос")
                    await self._maybe_watchlist_after_mute(interaction, user, reason)
                elif action == "mute_chat":
                    # «Мут (только чат)» — закрываем ТОЛЬКО текст через мут-роль.
                    # Нативный таймаут тут не подходит: он заглушил бы и голос.
                    # Поэтому чат-мут работает мут-ролью; без роли честно просим
                    # её настроить (а не выдаём таймаут с подписью «только чат»).
                    _mrole = self._punish_role(guild, 'mute')
                    if _mrole is None:
                        await _respond(interaction, embed=error_embed(
                            "Мут только чата работает через мут-роль, а она не выбрана. "
                            "Настройте её: панель → «Настройки модерации» → роли наказаний. "
                            "Если нужно заглушить и чат, и голос сразу — выберите «Мут (чат + войс)»."),
                            ephemeral=True)
                        return
                    minutes = parse_duration_minutes(amount, 5)
                    try:
                        from services import mute_state
                        await mute_state.clear_all_mutes(guild, user)
                    except Exception as _mse:
                        log.debug(f'[MODPANEL] mute_chat clear all: {_mse}')
                    await user.add_roles(_mrole, reason=reason or 'мут чата')
                    self._remember_temp(guild, user, _mrole, minutes * 60)
                    msg = (f"🤐 чат закрыт на {human_duration(minutes)} "
                           f"(роль «{_mrole.name}»); голос не тронут")
                    await self._maybe_watchlist_after_mute(interaction, user, reason)
                elif action =="vmute":
                    # Войс-мут — ТОЛЬКО микрофон, чат не трогаем. Снимаем
                    # нативный таймаут/чат-мут, если он стоял, чтобы не было
                    # «двойного мута»: роль войс-мута глушит голос сама.
                    _vrole =self ._punish_role (guild ,'vmute')
                    minutes =parse_duration_minutes (amount ,5 )
                    if _vrole is not None :
                        # роль войс-мута: работает и вне голоса, снимется по сроку
                        await self ._clear_chat_mute (guild ,user )
                        await user .add_roles (_vrole ,reason =reason or 'войс-мут')
                        self ._remember_temp (guild ,user ,_vrole ,minutes *60 )
                        msg =f"🎙️ войс-мут «{_vrole .name }» на {minutes } мин"
                    else :
                        if not user .voice or not user .voice .channel :
                            await _respond (interaction ,
                            embed =error_embed ("Участник не в голосовом канале. Голосовой мьют невозможен."),
                            ephemeral =True )
                            return
                        # нативное серверное заглушение микрофона (без таймаута чата)
                        await self ._clear_chat_mute (guild ,user )
                        try :
                            await user .edit (mute =True )
                        except Exception as _ve :
                            await _respond (interaction ,
                            embed =error_embed (f"Не удалось заглушить микрофон: {_ve }"),
                            ephemeral =True )
                            return
                        msg ="🎙️ микрофон заглушён (войс-мут)"
                elif action =="vunmute":
                    _vrole =self ._punish_role (guild ,'vmute')
                    if _vrole is not None :
                        await self ._drop_roles (guild ,user ,[_vrole ])
                        msg =f"🎙️ войс-мут снят ({_vrole .name })"
                    else :
                        try :
                            await user .edit (mute =False )
                        except Exception as _ve :
                            log .debug (f'[MODPANEL] vunmute edit: {_ve}')
                        msg ="🎙️ микрофон включён"
                else :  # untimeout — снимаем ЛЮБОЙ мут (чат+войс) разом
                    try :
                        from services import mute_state
                        await mute_state .clear_all_mutes (guild ,user )
                    except Exception as _mse :
                        log .debug (f'[MODPANEL] untimeout clear all: {_mse}')
                    msg ="🔊 мут снят (чат и голос)"

                # Вспомогательные шаги: дело, DM, лог, уведомление панели.
                # Каждый — в своём try: сбой побочного шага НЕ должен превращать
                # выполненное наказание в «ошибку» для модератора.
                aux_errors =[]
                # Лимиты: фиксируем успешные муты в дневном счётчике
                # (бан и чистка пишутся в своих ветках)
                try :
                    _sl_rec_key ={'timeout':'mute','mute_chat':'mute','vmute':'mute',
                    'untimeout':'unmute','vunmute':'unmute','kick':'kick'}.get (action )
                    if _sl_rec_key and guild :
                        from services .staff_limits import record_hit as _sl_rec 
                        _sl_rec (guild .id ,interaction .user .id ,_sl_rec_key ,1 )
                except Exception as _slr :
                    log .debug (f'[STAFF_LIMIT] rec: {_slr}')
                try :
                    case_id =self .save_case (guild .id ,action ,user .id ,interaction .user .id ,reason )
                except Exception as _case_e :
                    case_id =0
                    aux_errors .append ("дело не записано")
                    log .warning (f'[MODPANEL] save_case: {_case_e}')
                try :
                    dm =mod_dm_embed (action ,guild ,interaction .user ,reason )
                    await self .send_dm (user ,dm )
                except Exception as _dm_e :
                    aux_errors .append ("DM не доставлен")
                    log .info (f'[MODPANEL] DM: {_dm_e}')
                try :
                    log_ch_embed =mod_log_embed (action ,{"ban":"🚫 Апелляция","kick":"👢 Кик","timeout":"🔇 Мут","mute_chat":"🔇 Мут чата","vmute":"🎙️ Войс-мут","vunmute":"🎙️ Войс-мут снят","untimeout":"🔊 Мут снят"}.get (action ,action ),0x3498DB ,user ,interaction .user ,guild ,reason ,case_id )
                    await self .send_log (guild ,log_ch_embed )
                except Exception as _log_e :
                    aux_errors .append ("лог-канал недоступен")
                    log .warning (f'[MODPANEL] send_log: {_log_e}')

                # Уведомление панели о действии модерации (веб/Discord/email — в фоне)
                try :
                    from cogs .ticket import _notify_panel_ticket_event as _np
                    _label ={"ban":"Апелляция","kick":"Кик","timeout":"Таймаут","mute_chat":"Мут чата","vmute":"Войс-мут","vunmute":"Войс-мут снят","untimeout":"Мут снят"}.get (action ,action )
                    _np (interaction ,'mod_action',
                    f"{_label }: {user .display_name }",
                    f"Модератор: {interaction .user .display_name } · Причина: {reason } · Дело #{case_id}")
                except Exception as _ex:
                    _log.debug("_execute_mod_action(): подавлено: %s", _ex)

                # Доказательство (ссылка) — в канал доказательств.
                proof_note =None
                try :
                    if action in _punish_actions and (proof_link or '').strip ():
                        from cogs .proof_cog import try_deliver_proof
                        _p_ru ={'ban':'апелляция','kick':'кик','timeout':'мут','mute_chat':'мут чата','vmute':'войс-мут'}.get (action ,action )
                        proof_note =await try_deliver_proof (self .bot ,guild ,interaction .user ,user ,_p_ru ,reason ,link =proof_link )
                except Exception as _pe :
                    log .warning (f'[MODPANEL] демка: {_pe}')

                confirm =success_embed (
                "Действие выполнено",
                f"**{user.display_name}** · `{user.id}`\n{msg}\n**Причина:** {reason}\n**Дело:** #{case_id}",
                guild =guild )
                if aux_errors :
                    confirm .description +=f"\n\n⚠️ {' · '.join (aux_errors )}"
                if proof_note :
                    confirm .description +=f"\n{proof_note }"
                await _respond (interaction ,embed =confirm ,ephemeral =True )
            except discord .Forbidden :
                await _respond (interaction ,
                embed =error_embed (await _forbidden_reason (guild ,user ,action ),"Не хватило прав у бота"),ephemeral =True )
            except Exception as ex :
                import traceback as _tb
                log .warning (f"[MODPANEL] Сбой действия: {_tb.format_exc()}")
                await _respond (interaction ,embed =error_embed (str (ex )),ephemeral =True )

        elif action =="unban":
            uid =self ._parse_target_id (target )
            if not uid :
                await _respond (interaction ,
                embed =error_embed ("Укажите ID пользователя для разбана (15-22 цифры, можно с @упоминанием)."),ephemeral =True )
                return
            try :
                member =guild .get_member (uid )
                # Снятие апелляции (участник остаётся на сервере)
                if member is not None :
                    await self ._unisolate_member (guild ,member )
                    await self ._unban_role (guild ,member )
                # Настоящий разбан (для легаси-банов, если пользователь вне сервера)
                unban_done =False
                try :
                    fetched =await self .bot .fetch_user (uid )
                    await guild .unban (fetched )
                    unban_done =True
                except Exception as _ub_ex :
                    log .debug (f'unban: {_ub_ex}')
                case_id =self .save_case (guild .id ,"unban",uid ,interaction .user .id ,reason )
                try :
                    from services .staff_limits import record_hit as _sl_rec
                    _sl_rec (guild .id ,interaction .user .id ,'unban',1 )
                except Exception as _re :
                    log .debug (f'[STAFF_LIMIT] unban rec: {_re}')
                _who =member .display_name if member else (getattr (fetched ,'name','') if unban_done else str (uid ))
                _desc =f"**{_who}** · `{uid}`\n"
                _desc +="Снята апелляция и разбан." if (member is not None and unban_done) else \
                        ("Апелляция снята." if member is not None else \
                         ("Разбан выполнен." if unban_done else "Ничего не изменилось (не изолирован и не забанен)."))
                _desc +=f"\n**Дело:** #{case_id}"
                confirm =success_embed ("Снятие апелляции / разбан",_desc ,guild =guild )
                await self .send_log (guild ,confirm )
                # Уведомление панели (веб/Discord/email — в фоне)
                try :
                    from cogs .ticket import _notify_panel_ticket_event as _np
                    _np (interaction ,'mod_action',
                    f"Разбан/снятие апелляции: {_who }",
                    f"Модератор: {interaction .user .display_name } · Дело #{case_id}")
                except Exception as _ex:
                    _log.debug("_execute_mod_action(): подавлено: %s", _ex)
                await _respond (interaction ,embed =confirm ,ephemeral =True )
            except Exception as ex :
                await _respond (interaction ,embed =error_embed (str (ex )),ephemeral =True )

        elif action =="clear":
            try :
                count =max (1 ,min (int (amount )or 10 ,200 ))
            except Exception :
                count =10
            deleted =await interaction .channel .purge (limit =count )
            try :
                from services .staff_limits import record_hit as _sl_rec
                _sl_rec (guild .id ,interaction .user .id ,'clear',len (deleted ))
            except Exception as _re :
                log .debug (f'[STAFF_LIMIT] clear rec: {_re}')
            confirm =success_embed (
            "Сообщения удалены",
            f"Удалено **{len(deleted)}** сообщений в {interaction.channel.mention}",
            guild =guild )
            await _respond (interaction ,embed =confirm ,ephemeral =True )

    async def _ensure_action_acl(self, interaction, action):
        """Пункт /modpanel: у модератора должно быть «классическое» разрешение.

        Меню живёт 5 минут — владелец мог успеть снять «Бан»/«Мут»/… у роли.
        Отказ здесь (до модалки и до исполнения): без права действие не
        выполнится, даже если пункт ещё виден на экране. Веб-панель сюда не
        ходит — у неё свои проверки авторизации (apply_panel_action).
        """
        try:
            from services.permission_acl import check_action as _acl_check
            key = MODPANEL_ACL_KEYS.get(action)
            guild = getattr(interaction, 'guild', None)
            if key and guild and not _acl_check(guild.id, interaction.user, key):
                label = next((lbl for val, lbl, _d, _k in MODPANEL_ACTIONS
                              if val == action), action)
                await _respond(interaction, embed=error_embed(
                    f'Действие «{label}» тебе не дал владелец. '
                    'Разрешения ролей: панель → Доступ → Права команд → '
                    'Классические разрешения.'), ephemeral=True)
                return False
        except Exception as _ex:
            log.debug(f'[MODPANEL] ACL-проверка действия {action}: {_ex}')
        return True

    async def apply_panel_action (self ,guild ,target ,action ,reason ='' ,
    amount =None ,proof_link =None ,actor ='Панель'):
        """Наказание из веб-панели («Пользователи») — единый путь с /modpanel.

        target — discord.Member (на сервере) или строка-ID (ушёл с сервера).
        Возвращает (ok, текст ответа для панели).
        """
        from cogs .embed_utils import error_embed as _err ,success_embed as _ok 
        if action not in PANEL_ACTIONS :
            return False ,'Неизвестное действие'
        if guild is None :
            return False ,'Сервер не найден'
        _actor =PanelActor (actor )
        target_str =str (getattr (target ,'id',target ))
        # варн — своя ветка (в /modpanel варнов нет, они живут в warnings)
        if action =='warn':
            try :
                from services .staff_limits import check_action 
                _okw ,_deny =check_action (guild ,_actor ,'warn')
                if not _okw :
                    return False ,_deny or 'Лимит варнов исчерпан'
            except Exception as _sx :
                _log .debug ('[MODPANEL] staff_limits warn: %s',_sx ) 
            try :
                w =self .bot .get_cog ('warnings')
                if w is None :
                    return False ,'Модуль варнов не загружен'
                # add_warning сам пишет варн, ДМ участнику и лог в канал
                res =await w .add_warning (target ,moderator =_actor ,
                reason =reason or None )
                _total =res [1 ]if isinstance (res ,tuple )else None 
                return True ,f'Варн выдан (всего: {_total if _total is not None else "?"})'
            except Exception as _ex :
                return False ,f'Не получилось: {_ex }'
        _it =PanelInteraction (guild ,_actor )
        try :
            await self ._execute_mod_action (_it ,action ,target_str ,
            reason or 'не указана',amount ,proof_link =(proof_link or '').strip ()or None )
        except Exception as _ex :
            return False ,f'Не получилось: {_ex }'
        if not _it .msgs :
            return True ,'Готово'
        text =_embed_text (_it .msgs [-1 ])
        ok ='## ❌' not in text 
        return ok ,text 

    # ── Роли наказаний (панель → «Настройки модерации») ─────────────────
    async def _clear_voice_mute (self ,guild ,user ):
        """Снять любое голосовое заглушение (роль войс-мута или нативный
        server-mute), чтобы при чат-муте/таймауте не оставалось второго мута."""
        try :
            from services import mute_state
            await mute_state .clear_voice_mute (guild ,user )
        except Exception as _e :
            log .debug (f'[MODPANEL] clear voice-mute: {_e}')

    async def _clear_chat_mute (self ,guild ,user ):
        """Снять нативный таймаут и чат-мут-роль, чтобы при войс-муте не
        оставалось второго мута (войс-мут глушит только микрофон)."""
        try :
            from services import mute_state
            await mute_state .clear_chat_mute (guild ,user )
        except Exception as _e :
            log .debug (f'[MODPANEL] clear chat-mute: {_e}')

    def _punish_role (self ,guild ,kind ):
        """discord.Role для наказания или None (не выбрана — работаем как раньше)."""
        try :
            from services import punish_roles as PR 
            rid =PR .role_for (guild .id ,kind )
            if not rid :
                return None 
            role =guild .get_role (rid )
            if role is None :
                log .debug (f'[MODPANEL] роль {kind } ({rid }) не найдена на сервере')
            return role 
        except Exception as _ex :
            log .debug (f'[MODPANEL] punish_role {kind }: {_ex}')
            return None 

    def _remember_temp (self ,guild ,user ,role ,seconds ):
        """Запомнить срок выдачи роли — loop снимет её вовремя."""
        try :
            import time as _time 
            from services import punish_roles as PR 
            until =_time .time ()+max (60 ,min (int (seconds or 0 ),28 *86400 ))
            PR .add_temp (guild .id ,user .id ,role .id ,until )
        except Exception as _ex :
            log .debug (f'[MODPANEL] remember_temp: {_ex}')

    async def _drop_roles (self ,guild ,user ,roles ):
        """Снять роли наказания и почистить журнал сроков."""
        for role in roles :
            if role is None :
                continue 
            try :
                await user .remove_roles (role ,reason ='снятие наказания')
            except Exception as _ex :
                log .debug (f'[MODPANEL] remove_roles {role .name }: {_ex}')
        try :
            from services import punish_roles as PR 
            PR .clear (guild .id ,user .id )
        except Exception as _ex :
            log .debug (f'[MODPANEL] clear temps: {_ex}')

    async def _unban_role (self ,guild ,member ):
        """Снять роль «бана» (если выбрана) — при разбане/снятии апелляции."""
        _brole =self ._punish_role (guild ,'ban')
        if _brole is not None :
            await self ._drop_roles (guild ,member ,[_brole ])

    @tasks .loop (seconds =60 )
    async def punish_roles_loop (self ):
        """Раз в минуту снимает просроченные роли наказаний."""
        try :
            import time as _time 
            from services import punish_roles as PR 
            due =PR .due (_time .time ())
            for gid ,uid ,rid in due :
                guild =self .bot .get_guild (int (gid ))
                if guild is None :
                    PR .clear (gid ,uid ,rid )
                    continue 
                member =guild .get_member (int (uid ))
                role =guild .get_role (rid )
                if member is not None and role is not None :
                    try :
                        await member .remove_roles (role ,reason ='срок наказания истёк')
                    except Exception as _ex :
                        log .debug (f'[MODPANEL] авто-снятие {role .name }: {_ex}')
                PR .clear (gid ,uid ,rid )
                if member is not None :
                    try :
                        await self .send_log (guild ,discord .Embed (
                        description =f"⏳ Срок наказания истёк: роль {getattr (role ,'mention ',rid )} "
                        f"снята с {member .mention }",color =0x2ECC71 ))
                    except Exception as _lex :
                        log .debug (f'[MODPANEL] лог авто-снятия: {_lex}') 
        except Exception as _ex :
            log .debug (f'[MODPANEL] punish_roles_loop: {_ex}')

    @punish_roles_loop .before_loop 
    async def _before_punish_loop (self ):
        import asyncio as _aio 
        await _aio .sleep (30 )      # дать боту подняться

    async def _maybe_watchlist_after_mute (self ,interaction ,user ,reason ):
        """Если пользователь получил 2+ мьюта — добавить в watchlist на 1 неделю.

        Считаем мьюты (timeout) из mod_data.json. При достижении 2-го мьюта
        добавляем в mod_advanced_data.json (watchlist) с меткой until (+7 дней).
        """
        try :
            import datetime as _dt
            # 1) Считаем мьюты пользователя
            os .makedirs ('data',exist_ok =True )
            mod_file ='data/mod_data.json'
            mute_count =0
            if os .path .exists (mod_file ):
                with open (mod_file ,'r',encoding ='utf-8')as f :
                    data =json .load (f )
                cases =data .get ('cases',{}).get (str (interaction .guild .id ),[])
                for c in cases :
                    if str (c .get ('user_id',''))==str (user .id )and c .get ('action')in ('timeout','mute_chat','vmute'):
                        mute_count +=1
            # 2) Добавляем в watchlist (advanced_mod) на 1 неделю
            adv_file ='data/mod_advanced_data.json'
            adv ={}
            if os .path .exists (adv_file ):
                with open (adv_file ,'r',encoding ='utf-8')as f :
                    adv =json .load (f )
            adv .setdefault ('watchlist',{})
            gid =str (interaction .guild .id )
            adv ['watchlist'].setdefault (gid ,{})
            until =int (time .time ())+7 *86400  # +7 дней
            adv ['watchlist'][gid ][str (user .id )]={
                "reason":f"Автоматически: {mute_count}-й мьют. {reason or ''}",
                "added_by":str (interaction .user ),
                "timestamp":datetime .now (timezone .utc ).isoformat (),
                "until":until ,
                "auto":True ,
            }
            with open (adv_file ,'w',encoding ='utf-8')as f :
                json .dump (adv ,f ,indent =2 ,ensure_ascii =False )
        except Exception as ex :
            log .warning (f"[watchlist auto] {ex}")


# ═══════════════════════════════════════════════════════════════════
#  SELECT-МЕНЮ МОДЕРАЦИИ (без кнопок/эмодзи — только выпадающие меню)
# ═══════════════════════════════════════════════════════════════════
# ── Наказания из веб-панели («Пользователи») ─────────────────────────────
# Тот же путь исполнения, что у /modpanel, но «модератором» выступает
# панель: действия пишутся в дела и логи от имени «Панель: <логин>».
PANEL_ACTIONS = ('warn', 'timeout', 'mute_chat', 'vmute', 'ban',
                 'unban', 'untimeout', 'vunmute')


class PanelActor:
    """«Модератор» из веб-панели — пишется в дела и логи."""

    is_panel = True
    bot = False
    id = 0
    roles = ()

    def __init__(self, name='Панель'):
        self._name = str(name or 'Панель')

    @property
    def display_name(self):
        return f'Панель: {self._name}'

    @property
    def mention(self):
        return self.display_name

    def __str__(self):
        return self.display_name


class PanelInteraction:
    """Interaction-заглушка: собирает ответы бота, чтобы панель показала их."""

    def __init__(self, guild, actor):
        self.guild = guild
        self.user = actor
        self.channel = None
        self.client = None
        self.msgs = []

        class _Resp:
            def is_done(s):
                return False

            async def send_message(s, embed=None, ephemeral=False, **kw):
                if embed is not None:
                    self.msgs.append(embed)

        class _Follow:
            async def send(s, embed=None, ephemeral=False, **kw):
                if embed is not None:
                    self.msgs.append(embed)

        self.response = _Resp()
        self.followup = _Follow()


def _embed_text(e):
    return str(getattr(e, 'description', None) or getattr(e, 'title', '') or '').strip()


# Действия панели: (value, label, описание, ключ лимита стаффа).
# Ключ — как в services/staff_limits: мут чата/войса/таймаут — один ключ mute.
MODPANEL_ACTIONS = [
    ("warn", "Варн (предупреждение)", "Официальный варн: в дело, участнику в ЛС", "warn"),
    ("ban", "Бан (апелляция)", "Не выгоняет: закроет каналы, оставит только канал апелляции", "ban"),
    ("timeout", "Таймаут (чат + войс)", "Нативный таймаут Discord: одним действием закрыты и текст, и голос (до 28 дней)", "mute"),
    ("mute_chat", "Мут (только чат)", "Закрывает только чат через мут-роль; голос работает", "mute"),
    ("vmute", "Мут (только войс)", "Глушит микрофон; чат не трогается", "mute"),
    ("unban", "Снять апелляцию / разбан", "Вернуть доступ к каналам (по ID)", "unban"),
    ("clear", "Очистка сообщений", "Снести N последних сообщений в канале", "clear"),
    ("untimeout", "Размут (чат + войс)", "Снять таймаут — снова можно всё", "unmute"),
    ("vunmute", "Размут (войс)", "Вернуть участнику голос", "unmute"),
]

# Эмодзи действий: меню панели живое, а не текстовое
MODPANEL_EMOJI = {
    "warn": "⚠️",
    "ban": "🚫",
    "timeout": "🔇",
    "mute_chat": "🤐",
    "vmute": "🎙️",
    "unban": "✅",
    "clear": "🧹",
    "untimeout": "🔊",
    "vunmute": "🎤",
}

# Пункт /modpanel → «классическое» разрешение (панель → Доступ → Права
# команд → Классические разрешения). Ключи — как в permission_acl.ACTIONS:
# не дал модератору «Бан» → у него в /modpanel нет ни «Бан», ни «Разбан»;
# не дал «Мут» → нет мута чата/войса и снятий; «Таймаут» → нет таймаута
# и снятия; «Очистка» → нет чистки. Правило не задано — действие доступно.
MODPANEL_ACL_KEYS = {
    "warn": "warn",
    "ban": "ban",
    "unban": "ban",
    "timeout": "timeout",
    "untimeout": "timeout",
    "mute_chat": "mute",
    "vmute": "mute",
    "vunmute": "mute",
    "clear": "purge",
}


def _action_acl_allows(guild_id, member, action_name):
    """Разрешено ли модератору действие action_name «классическим» ACL.

    Панель → Доступ → Права команд → «Классические разрешения»: если для
    действия заданы роли, у модератора должна быть одна из них. Правила
    нет — можно (как и везде в permission_acl). Сбой чтения БД не ломает
    панель модератора: пункт скрывается только при явном отказе.
    """
    key = MODPANEL_ACL_KEYS.get(action_name)
    if not key:
        return True
    try:
        from services.permission_acl import check_action as _acl_check
        return _acl_check(guild_id, member, key)
    except Exception:
        log.debug('actions_for_member: ACL-проверка %s пропущена (сбой БД)', action_name)
        return True


def actions_for_member(guild, member):
    """Какие действия панели показывать модератору.

    По умолчанию — все. Фильтры (оба работают вместе):
    1) «Лимиты команды» (Щит сервера → Лимиты → роль): если у ролей
       модератора есть свои лимиты/потолки — только настроенные действия;
    2) «Классические разрешения» (Доступ → Права команд → действия):
       не дал роли «Бан»/«Мут»/«Таймаут»/«Варн»/«Очистку» — пункт не
       показывается, даже если пункт позволяет команда.
    Владелец бота и владелец сервера видят всё.
    """
    try:
        uid = getattr(member, "id", 0)
        if getattr(guild, "owner_id", None) == uid:
            return list(MODPANEL_ACTIONS)
        from config import Config as _Cfg
        if uid in _Cfg.all_owner_ids():
            return list(MODPANEL_ACTIONS)
    except Exception:
        log.debug('actions_for_member: без лимитов — показываем всё')
    role_ids = []
    try:
        role_ids = [r.id for r in (getattr(member, "roles", None) or [])
                    if getattr(r, "id", None) != getattr(guild, "id", None)]
    except Exception:
        role_ids = []
    try:
        from services.staff_limits import role_scoped_actions as _rsa
        scoped = _rsa(guild.id, role_ids)
    except Exception:
        scoped = None
    if scoped is None:
        base = list(MODPANEL_ACTIONS)
    else:
        base = [a for a in MODPANEL_ACTIONS if a[3] in scoped]
    return [a for a in base if _action_acl_allows(guild.id, member, a[0])]


class ModActionSelect(discord.ui.Select):
    """Выбор действия модерации — только то, что доступно этому модератору."""

    def __init__(self, cog, member=None, allowed=None):
        acts = allowed if allowed is not None else MODPANEL_ACTIONS
        options = [discord.SelectOption(
                       label=label, value=value, description=desc,
                       emoji=MODPANEL_EMOJI.get(value, '⚡'))
                   for value, label, desc, _key in acts]
        super().__init__(
            placeholder="⚡ Что сделать? Выберите действие…",
            options=options,
            min_values=1,
            max_values=1,
        )
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        action = self.values[0]
        # Защита на границе: доступ могли снять, пока меню было на экране
        if not await self.cog._ensure_action_acl(interaction, action):
            return
        modal = ModActionModal(self.cog, action, guild=interaction.guild)
        await interaction.response.send_modal(modal)


# Действия-наказания в мод-панели: к ним обязательна демка (пока включено
# требование в панели: «Доказательства» → тумблер).
_PUNISH_MODPANEL = ("ban", "timeout", "mute_chat", "vmute")


class ModActionModal(discord.ui.Modal):
    """Модальное окно ввода — поля строго под выбранное действие.

    «Очистка» спрашивает только количество и причину (никакой демки),
    разбан/размут — цель и причину, наказания — демку, НО только если
    требование включено в панели.
    """

    def __init__(self, cog, action, guild=None):
        self.cog = cog
        self.action = action
        titles = {
            "warn": "Варн (предупреждение)",
            "ban": "Бан (апелляция)",
            "timeout": "Мут (чат + войс)",
            "mute_chat": "Мут чата",
            "vmute": "Войс-мут",
            "unban": "Снять апелляцию / разбан",
            "clear": "Очистка сообщений",
            "untimeout": "Снять мут",
            "vunmute": "Снять войс-мут",
        }
        super().__init__(title=titles.get(action, "Модерация"))

        if action != "clear":
            self.target = discord.ui.TextInput(
                label="Цель (@ник, точное имя или ID)", required=True,
                placeholder="@упоминание, ник или 15-22 цифры ID",
            )
            self.add_item(self.target)
        if action in ("timeout", "mute_chat", "vmute", "clear"):
            if action == "clear":
                _lbl, _ph, _d = "Сколько сообщений удалить?", "например: 25", "10"
            else:
                _lbl, _ph, _d = "На сколько? (мин/час/дни)", "60, 1ч, 3ч, 1д…", "60"
            self.amount = discord.ui.TextInput(
                label=_lbl, required=False, placeholder=_ph, default=_d,
            )
            self.add_item(self.amount)
        self.reason = discord.ui.TextInput(
            label="Причина", required=False, placeholder="За что? (необязательно)",
            style=discord.TextStyle.short,
        )
        self.add_item(self.reason)
        _need_proof = False
        if action in _PUNISH_MODPANEL:
            try:
                from cogs.proof_cog import proof_is_required
                _need_proof = proof_is_required(getattr(guild, 'id', 0) or 0)
            except Exception:
                _need_proof = True
        if _need_proof:
            self.proof = discord.ui.TextInput(
                label="Доказательство (ссылка на скрин/видео)", required=True,
                placeholder="https://… — без этого наказание не выдаётся",
                max_length=500,
            )
            self.add_item(self.proof)

    async def on_submit(self, interaction: discord.Interaction):
        # Финальная защита действия: модалку могли открыть до смены прав,
        # роль могли снять — без «классического» разрешения не исполняем.
        if not await self.cog._ensure_action_acl(interaction, self.action):
            return
        # Быстрый ack — дальше цепочка (таймаут → дело → DM → лог) может
        # занять больше 3 секунд, без defer токен умирал и Discord рисовал
        # «Приложение не отвечает», хотя наказание уже применено.
        try:
            await interaction.response.defer(ephemeral=True)
        except Exception as _ex:
            _log.debug("on_submit(): подавлено: %s", _ex)
        _t = getattr(self, 'target', None)
        _a = getattr(self, 'amount', None)
        _p = getattr(self, 'proof', None)
        _reason = (self.reason.value or "").strip() or "Не указана"
        await self.cog._execute_mod_action(
            interaction,
            self.action,
            (_t.value or "").strip() if _t else "",
            _reason,
            (_a.value or "").strip() if _a else "5",
            proof_link=(_p.value or "").strip() if _p else "",
        )


class ModHelpButton(discord.ui.Button):
    """«Как это работает» — короткая шпаргалка, не мешает меню."""

    def __init__(self):
        super().__init__(emoji='❓', style=discord.ButtonStyle.secondary,
                         label='Как это работает')

    async def callback(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title='❓ Шпаргалка по панели',
            description=(
                'Панель личная — только вызвавший модератор нажимает её меню.\n'
                'Меню живёт 5 минут, потом просто вызовите /modpanel снова.'),
            color=0x5865F2)
        embed.add_field(
            name='🎯 Цель',
            value='@упоминание, точное имя или ID — бот поймёт любой вариант.\n'
                  'Не нашли участника? Скорее всего, он ушёл с сервера: ID работает и так.',
            inline=False)
        embed.add_field(
            name='⏱ Срок',
            value='«60» — минуты, «1ч», «3ч», «1д» — час/день. Просто число = минуты.',
            inline=False)
        embed.add_field(
            name='🚫 Бан — это апелляция',
            value='Участник остаётся на сервере: все каналы закрыты, открыт только '
                  'канал апелляции. Настраивается: Панель → Каналы и маршруты.',
            inline=False)
        embed.add_field(
            name='🧹 Чистка',
            value='Удаляет N последних сообщений в канале, где вы находитесь.',
            inline=False)
        embed.set_footer(text='Шпаргалка · панель Hakumo')
        await interaction.response.send_message(embed=embed, ephemeral=True)


class ModPanelView(discord.ui.View):
    """View панели: меню действий + кнопка-шпаргалка."""

    def __init__(self, cog, member=None, allowed=None):
        super().__init__(timeout=300)
        self.add_item(ModActionSelect(cog, member, allowed))
        self.add_item(ModHelpButton())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Меню действий /modpanel — доступ решает владелец через панель ролей.

        Раньше тут жёстко требовалось Discord-право «Модерация участников» —
        роль, которой владелец выдал /modpanel в панели (Доступ → Права
        команд), всё равно упиралась в этот запрет. Теперь проверяем тот же
        ролевой ACL, что и саму команду (has_access), а конкретные действия
        дополнительно фильтруются (actions_for_member / _ensure_action_acl).
        """
        user = interaction.user
        if getattr(user, 'guild_permissions', None) and user.guild_permissions.administrator:
            return True
        try:
            from services.permission_acl import has_access
            guild = interaction.guild
            if guild and not has_access(guild.id, 'modpanel', user):
                await interaction.response.send_message(
                    embed=error_embed("Недостаточно прав: доступ к /modpanel "
                                      "настраивает владелец (панель → Доступ → "
                                      "Права команд)."),
                    ephemeral=True)
                return False
        except Exception as _ex:
            log.debug('ModPanelView.interaction_check: ACL не прочитан (%s) — пускаю', _ex)
        return True


async def setup (bot ):
    await bot .add_cog (Moderation (bot ))
