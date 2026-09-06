
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


async def _ack(interaction, ephemeral=True):
    """Сразу закрыть 3-секундное окно Discord, чтобы не было
    «Приложение не отвечает», пока бан/мут ещё идут.

    thinking=False — без спиннера «думает…» на панели.
    """
    try:
        resp = getattr(interaction, 'response', None)
        if resp is None or resp.is_done():
            return
        try:
            await resp.defer(ephemeral=ephemeral, thinking=False)
        except TypeError:
            await resp.defer(ephemeral=ephemeral)
    except Exception as _e:
        log.debug('[MODPANEL] defer: %s', _e)


def _is_untouchable(guild, user):
    """Владелец бота, владелец сервера и боты — наказания не выдаём."""
    if user is None:
        return False
    uid = getattr(user, 'id', None)
    if not uid:
        return False
    try:
        from config import Config
        if int(uid) in Config.all_owner_ids():
            return True
    except Exception:
        pass
    if uid == getattr(guild, 'owner_id', None):
        return True
    if getattr(user, 'bot', False):
        return True
    return False


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

    def _recent_mute_count(self, guild_id, user_id, hours: float = 48.0) -> int:
        """Сколько мутов (таймаут/чат/войс) получил пользователь за окно.
        Источник — data/mod_data.json (те же дела, что пишет save_case)."""
        try:
            filepath = 'data/mod_data.json'
            if not os.path.exists(filepath):
                return 0
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            cases = (data.get('cases') or {}).get(str(guild_id)) or []
            horizon = datetime.now(timezone.utc).timestamp() - hours * 3600
            n = 0
            for c in cases:
                if str(c.get('user_id')) != str(user_id):
                    continue
                if c.get('action') not in ('timeout', 'mute_chat', 'vmute'):
                    continue
                ts = c.get('timestamp')
                if not ts:
                    continue
                try:
                    when = datetime.fromisoformat(ts).timestamp()
                except Exception as _te:
                    log.debug(f"[MOD] _recent_mute_count bad ts {ts}: {_te}")
                    continue
                if when >= horizon:
                    n += 1
            return n
        except Exception as e:
            log.info(f"[MOD] _recent_mute_count: {e}")
            return 0

    async def _maybe_auto_warn(self, guild, user):
        """Авто-варн от бота: 3 мута за 48 ч → 1 предупреждение.
        Порог настраивается через mod-настройки (по умолчанию 3/48ч).
        Не дублируем: если у пользователя уже есть авто-варн, поставленный
        ПОСЛЕ его последнего мута — повторно не выдаём."""
        try:
            threshold = 3
            window_h = 48.0
            try:
                from services.async_io import load_json_async
                _cfg_path = f'data/mod_autowarn_{guild.id}.json'
                _ac = await load_json_async(_cfg_path, None, log=log)
                if _ac:
                    threshold = int(_ac.get('mute_threshold', threshold))
                    window_h = float(_ac.get('window_hours', window_h))
            except Exception as _ce:
                log.debug(f"[MOD] auto-warn cfg: {_ce}")

            if self._recent_mute_count(guild.id, user.id, window_h) < threshold:
                return

            # Не дублировать уже выданный авто-варн после последнего мута.
            warns_cog = self.bot.get_cog('warnings')
            if warns_cog is None:
                return
            warns = warns_cog._get_warns(guild.id, user.id)
            last_mute_ts = ''
            try:
                from services.async_io import load_json_async
                _md = await load_json_async('data/mod_data.json', {}, log=log) or {}
                _cs = (_md.get('cases') or {}).get(str(guild.id)) or []
                _mine = [c.get('timestamp', '') for c in _cs
                         if str(c.get('user_id')) == str(user.id)
                         and c.get('action') in ('timeout', 'mute_chat', 'vmute')]
                last_mute_ts = max(_mine) if _mine else ''
            except Exception as _me:
                log.debug(f"[MOD] auto-warn last-mute scan: {_me}")
            for w in warns:
                if (w.get('mod_id') == str(self.bot.user.id)
                        and 'автоматически' in (w.get('reason') or '').lower()
                        and w.get('timestamp', '') >= last_mute_ts):
                    return  # авто-варн за эту серию уже выдан

            bot_member = guild.me
            reason = (f'Автоматически: {threshold} мута за {window_h:.0f} ч '
                      f'(правило рецидива). Выдано ботом.')
            await warns_cog.add_warning(user, bot_member, reason)
        except Exception as _aw_e:
            log.info(f'[MOD] auto-warn: {_aw_e}')

    def save_case (self ,guild_id ,action ,user_id ,mod_id ,reason ,mod_name=None ):
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
            # Имя модератора в момент наказания: панель показывает его,
            # даже если имя так и не попало в карту имён сервера.
            'mod_name':str (mod_name or ''),
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
            from services.async_io import load_json_async
            _flag =await load_json_async (flag_file ,{},log =log )or {}
            enabled =bool (_flag .get ('enabled',False ))
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
    # Два уровня доступа:
    #  1) Discord (ВИДИМОСТЬ): default_permissions(moderate_members=True) —
    #     по умолчанию команда видна только ролям с правом «Модерация
    #     участников», обычные участники её не видят в меню «/». Это
    #     настраиваемый дефолт: владелец открывает команду конкретным ролям
    #     без выдачи полного права — Настройки сервера → Интеграции → Hakumo
    #     → /modpanel (инструкция продублирована в панели → Доступ).
    #  2) Бот (ЧТО МОЖНО): ролевой ACL из панели (has_access в main.py) —
    #     отмеченные тут роли могут вызывать команду, а actions_for_member
    #     ниже режет конкретные действия (бан/мут/варн/очистка) по ролям.
    # Рантайм checks.has_permissions(moderate_members) НЕ ставим намеренно:
    # это жёсткий блок, который не переопределить ни панелью, ни Интеграциями
    # — из-за него выданные роли «не включались».
    @app_commands.default_permissions(moderate_members=True)
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
        view =ModPanelView (self ,interaction .user ,allowed )
        view ._root_edit =interaction .edit_original_response
        await _respond (interaction ,embed =view .panel_embed (interaction .guild ),view =view ,ephemeral =True )

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
            from services .channel_routes import resolve_route as _gr 
            cid =int (_gr (guild .id ,'ban_appeal_channel',guild )or 0)
        except Exception as _ex :
            log .debug (f'[MODPANEL] канал апелляции: {_ex}')
            return None 
        if not cid :
            return None 
        ch = guild .get_channel (cid )
        if ch is None :
            fn = getattr (guild ,'get_channel_or_thread',None )
            if callable (fn ):
                ch = fn (cid )
        if ch is None :
            getter = getattr (guild ,'get_thread',None )
            if callable (getter ):
                ch = getter (cid )
        return ch

    async def _isolate_member (self ,guild ,user ,iso ):
        """Закрыть участнику ВСЕ каналы — включая канал апелляции.

        Канал апелляции открывается НЕ в момент бана, а после подачи
        апелляции в ЛС боту (/апелляция → cogs/appeals.py _submit_appeal):
        заказ владельца 2026-09-05 — «канал апелляции должно быть видно
        только после того, как человек подаст апелляцию в личке бота».
        (Анти-альт при изоляции молодого аккаунта открывает канал сам —
        там это осознанный механизм проверки «ты живой?».)
        """
        if iso is None :
            return None ,0
        if _is_untouchable (guild ,user ):
            return iso ,0
        # Роль бана сама закрывает каналы. Обход комнат по одной —
        # минуты лагов и «приложение не отвечает».
        if self ._punish_role (guild ,'ban') is not None :
            return iso ,0
        deny =discord .PermissionOverwrite (view_channel =False ,send_messages =False ,
        connect =False ,speak =False )
        pool = list (guild .channels )
        for th in getattr (guild ,'threads',None ) or []:
            if th not in pool :
                pool .append (th )
        import asyncio as _aio
        sem =_aio .Semaphore (8 )
        async def _one (ch ):
            async with sem :
                try :
                    await ch .set_permissions (user ,overwrite =deny )
                    return 1
                except Exception as _ex :
                    log .debug (f'_isolate_member(): {ch}: {_ex}')
                    return 0
        bits =await _aio .gather (*[_one (ch )for ch in pool ],return_exceptions =True )
        closed =sum (x for x in bits if x ==1 )
        return iso ,closed

    async def _unisolate_member (self ,guild ,user ):
        """Снять апелляцию: вернуть участнику обычный доступ ко всем каналам."""
        pool = list (guild .channels )
        for th in getattr (guild ,'threads',None ) or []:
            if th not in pool :
                pool .append (th )
        for ch in pool :
            try :
                await ch .set_permissions (user ,overwrite =None )
            except Exception as _ex :
                log .debug (f'_unisolate_member(): {ch}: {_ex}')

    # ── Почему Forbidden: иерархия ролей / владелец сервера / право бота ──
    # «ban» здесь НЕ Discord-бан: участник остаётся на сервере, бот выдаёт
    # роль бана и закрывает каналы — право «Бан участников» боту НЕ нужно
    # (жалоба владельца 2026-09-04). Нужны роль и канал, отсюда manage_roles.
    _NEED_PERMS = {
        'ban': ('manage_roles', 'Управление ролями (роль бана и доступ к каналу апелляции)'),
        'kick': ('kick_members', 'Выгонять участников'),
        # Мут (чат + войс) работает МУТ-РОЛЯМИ (владелец 2026-09-05:
        # «он просто должен выдать роли — зачем ему права»). Право
        # «Модерация участников» нужно только НАТИВНОМУ таймауту Discord,
        # а тот — бонус: без права молча пропускается (см. ветку timeout).
        'timeout': ('manage_roles', 'Управление ролями (мут-роль)'),
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
            'untimeout':'unmute','vunmute':'unmute','unmute_chat':'unmute','unban':'unban',
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
                from services .staff_limits import (
                    check_limit as _sl_check ,limit_deny_text as _sl_deny )
                # Одна операция = 1 хит. Чистка раньше писала ЧИСЛО сообщений
                # в квоту «10 чисток/день» — первая попытка на 25 сразу
                # врала «Лимит исчерпан … использовано 0, осталось 10».
                _sl_amt =1
                _sl_roles =[]
                try :
                    _sl_roles =[r .id for r in (getattr (interaction .user ,'roles',None )or [])
                    if getattr (r ,'id',None )!=getattr (guild ,'id',None )]
                except Exception :
                    _sl_roles =[]
                _sl_ok ,_sl_used ,_sl_lim =_sl_check (guild .id ,interaction .user .id ,_sl_key ,_sl_amt ,role_ids =_sl_roles )
                if not _sl_ok :
                    _when =None
                    try :
                        from services .staff_limits import refresh_in_text as _sl_refresh
                        _when =_sl_refresh (guild .id ,interaction .user .id ,_sl_key )
                    except Exception as _sx :_log .debug ('[MODPANEL] staff_limits refresh: %s',_sx )
                    _txt =_sl_deny (_sl_key ,_sl_used ,_sl_lim ,amount =_sl_amt ,refresh =_when )
                    _txt +=' Настраивается: панель → Щит сервера → Лимиты.'
                    await _respond (interaction ,
                    embed =error_embed (_txt),
                    ephemeral =True )
                    return
                # Срок мута: 30 мин … 2 ч у всех (Sabotash 2026-09-02)
                if action in ('timeout','mute_chat','vmute'):
                    try :
                        from services .staff_limits import (
                            effective_max_duration as _sl_cap,
                            mute_duration_error as _sl_derr)
                        _cap =_sl_cap (guild .id ,'mute',_sl_roles )
                        _minutes_req =parse_duration_minutes (amount ,30 )
                        _derr =_sl_derr (_minutes_req *60 ,cap_sec =_cap )
                        if _derr :
                            await _respond (interaction ,
                            embed =error_embed (_derr ),
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

        if action =='unwarn':
            # «Снять варн» из /modpanel — тот же единый путь, что в панели
            user ,uid =self ._resolve_member (guild ,target )
            if not user :
                await _respond (interaction ,embed =error_embed (
                'Не нашёл участника по цели. Нужен @ник, ТОЧНОЕ имя или ID.'),
                ephemeral =True )
                return
            ok ,text =await self .apply_panel_action (
            guild ,user ,'unwarn',
            reason =reason ,actor =getattr (interaction .user ,'display_name','Модератор'))
            if ok :
                await _respond (interaction ,embed =success_embed (
                'Варн снят',f'**{user .display_name }** · `{uid }`\n{text }',guild =guild ),
                ephemeral =True )
            else :
                await _respond (interaction ,embed =error_embed (text ),ephemeral =True )
            return

        if action in ("ban","kick","timeout","mute_chat","untimeout","vmute","vunmute","unmute_chat"):
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

            _lift = action in ('untimeout', 'vunmute', 'unmute_chat')
            if not _lift and _is_untouchable(guild, user):
                await _respond(interaction, embed=error_embed(
                    'Это владелец бота или сервера — наказывать нельзя.'),
                    ephemeral=True)
                return

            # ИЕРАРХИЯ ПЕРСОНАЛА: не наказываем персонал своего уровня и выше
            # (владелец 2026-09-05: «модер наказывает модера/куратора — беспредел»)
            try :
                from services .staff_hierarchy import check as _hchk
                _hok ,_hdeny ,_ar ,_tr =_hchk (guild ,interaction .user ,user ,action )
                if not _hok :
                    await _respond (interaction ,
                    embed =error_embed (_hdeny ),ephemeral =True )
                    return
            except Exception as _hex :
                log .debug (f'[MODPANEL] hierarchy: {_hex}')

            # Предпроверка прав бота: знаем ЗАРАНЕЕ, получится ли действие,
            # и дело в базу не пишется зря
            _pre =await self .preflight_reason (guild ,user ,action )
            if _pre :
                await _respond (interaction ,
                embed =error_embed (_pre ,"У бота не хватит прав"),ephemeral =True )
                return

            await _ack (interaction )

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
                    _iso_ch ,_closed =await self ._isolate_member (guild ,user ,_iso )
                    _brole =self ._punish_role (guild ,'ban')
                    if _brole is not None :
                        # роль бана закрывает каналы; канал апелляции человек
                        # получит САМ, когда подаст апелляцию в ЛС боту
                        # (/апелляция) — не в момент бана (заказ владельца)
                        await user .add_roles (_brole ,reason =reason or 'бан')
                        msg =(f"роль бана «{_brole .name }» — каналы закрыты. "
                              f"Апелляция откроется после подачи в личке бота")
                    else :
                        msg =(f"закрыто каналов {_closed }. "
                              f"Апелляция откроется после подачи в личке бота")
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
                    # «Мут (чат + войс)» — ГЛАВНОЕ: СРАЗУ ОБЕ РОЛИ (мут чата +
                    # мут войса) + серверное заглушение микрофона. Нативный
                    # таймаут Discord требует права «Модерация участников»,
                    # которого у бота может не быть (владелец 2026-09-05:
                    # «требует прав — а должен просто дать обе роли и всё»),
                    # поэтому роли — основной механизм, нативный — бонус
                    # поверх, если право вдруг есть (молча пропускаем сбой).
                    minutes = parse_duration_minutes(amount, 30)
                    minutes = max(1, min(minutes, 40320))  # Discord — до 28 дней
                    try:
                        from services import mute_state
                        await mute_state.clear_all_mutes(guild, user)
                    except Exception as _mse:
                        log.debug(f'[MODPANEL] timeout clear all: {_mse}')
                    _extra_roles = []
                    for _kind in ('mute', 'vmute'):
                        try:
                            _r = self._punish_role(guild, _kind)
                            if _r is not None and _r not in user.roles:
                                await user.add_roles(_r, reason=reason or 'мут')
                                self._remember_temp(guild, user, _r, minutes * 60)
                                _extra_roles.append(_r.name)
                        except Exception as _tre:
                            log.debug(f'[MODPANEL] timeout роль {_kind}: {_tre}')
                    # микрофон: закрыть сразу, если человек в голосовом канале
                    try:
                        if getattr(getattr(user, 'voice', None), 'channel', None) \
                                and not getattr(user.voice, 'mute', False):
                            await user.edit(mute=True, reason=reason or 'мут')
                    except Exception as _ve:
                        log.debug(f'[MODPANEL] timeout server-mute: {_ve}')
                    # нативный таймаут — ТОЛЬКО если право есть; сбой не ломает
                    try:
                        until = datetime.now(timezone.utc) + timedelta(minutes=minutes)
                        await user.timeout(until, reason=reason or 'мут')
                    except (discord.Forbidden, discord.HTTPException, AttributeError) as _te:
                        log.debug(f'[MODPANEL] нативный таймаут пропущен: {_te}')
                    msg = (f"🔇 мут на {human_duration(minutes)} "
                           f"(~{minutes} мин) — обе роли выданы: чат закрыт, "
                           "микрофон заглушён")
                    if _extra_roles:
                        msg += " · роли: " + ", ".join(f"«{n}»" for n in _extra_roles)
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
                    minutes = parse_duration_minutes(amount, 30)
                    minutes = max(1, min(minutes, 40320))
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
                    minutes =parse_duration_minutes (amount ,30 )
                    minutes =max (1 ,min (minutes ,40320 ))
                    if _vrole is not None :
                        # роль + сервер-мут микрофона: в голосовые зайти МОЖНО,
                        # микрофон закрыт (владелец 2026-09-05: «микрофон
                        # должен закрываться, а в войсы он заходить может»)
                        await self ._clear_chat_mute (guild ,user )
                        await user .add_roles (_vrole ,reason =reason or 'войс-мут')
                        self ._remember_temp (guild ,user ,_vrole ,minutes *60 )
                        try :
                            if getattr (getattr (user ,'voice',None ),'channel',None ) \
                            and not getattr (user .voice ,'mute',False ) :
                                await user .edit (mute =True ,reason =reason or 'войс-мут')
                        except Exception as _ve :
                            log .debug (f'[MODPANEL] vmute server-mute: {_ve}')
                        # если роль случайно запрещает вход в голосовые — чиним:
                        # войс-мут глушит МИКРОФОН, а не выгоняет из каналов
                        await self ._fix_vmute_role_connect (guild ,_vrole )
                        msg =f"🎙️ войс-мут «{_vrole .name }» на {minutes } мин — микрофон заглушён, зайти в голосовой можно"
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
                    # микрофон вернуть В ЛЮБОМ случае (раньше после снятия
                    # роли микрофон оставался замьюченным)
                    try :
                        if getattr (getattr (user ,'voice',None ),'mute',False ) :
                            await user .edit (mute =False ,reason ='войс-мут снят')
                    except Exception as _ve :
                        log .debug (f'[MODPANEL] vunmute edit: {_ve}')
                    msg ="🎙️ войс-мут снят — микрофон открыт"
                elif action =="unmute_chat":
                    try :
                        from services import mute_state
                        await mute_state .clear_chat_mute (guild ,user )
                    except Exception as _mse :
                        log .debug (f'[MODPANEL] unmute_chat: {_mse}')
                    msg ="чат-мут снят, голос не тронут"
                else :  # untimeout — снимаем ЛЮБОЙ мут (чат+войс) разом
                    try :
                        from services import mute_state
                        await mute_state .clear_all_mutes (guild ,user )
                    except Exception as _mse :
                        log .debug (f'[MODPANEL] untimeout clear all: {_mse}')
                    msg ="мут снят (чат и голос)"

                # Вспомогательные шаги: дело, DM, лог, уведомление панели.
                # Каждый — в своём try: сбой побочного шага НЕ должен превращать
                # выполненное наказание в «ошибку» для модератора.
                aux_errors =[]
                # Лимиты: фиксируем успешные муты в дневном счётчике
                # (бан и чистка пишутся в своих ветках)
                try :
                    _sl_rec_key ={'timeout':'mute','mute_chat':'mute','vmute':'mute',
                    'untimeout':'unmute','vunmute':'unmute','unmute_chat':'unmute',
                    'kick':'kick'}.get (action )
                    if _sl_rec_key and guild :
                        from services .staff_limits import record_hit as _sl_rec 
                        _sl_rec (guild .id ,interaction .user .id ,_sl_rec_key ,1 )
                except Exception as _slr :
                    log .debug (f'[STAFF_LIMIT] rec: {_slr}')
                try :
                    import asyncio as _aio_sc
                    # запись дела (файл) — в рабочем потоке, без блокировки loop
                    case_id =await _aio_sc .to_thread (
                        self .save_case ,guild .id ,action ,user .id ,interaction .user .id ,reason ,
                        getattr (interaction .user ,'display_name' ,None )or str (interaction .user ))
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
                    from cogs.logs import send_action_log
                    await send_action_log(
                        guild, action, user, interaction.user,
                        reason=reason, case_id=case_id,
                        duration=amount, proof=proof_link)
                except Exception as _log_e :
                    aux_errors .append ("лог-канал недоступен")
                    log .warning (f'[MODPANEL] send_log: {_log_e}')

                # Авто-варн за серию мутов (3 за 48 ч) — выдаёт сам бот.
                if action in ('timeout', 'mute_chat', 'vmute'):
                    try :
                        await self ._maybe_auto_warn (guild ,user )
                    except Exception as _aw_e :
                        log .info (f'[MODPANEL] auto-warn: {_aw_e}')

                # Уведомление панели о действии модерации (веб/Discord/email — в фоне)
                try :
                    from services .panel_notify import notify_panel_event as _np
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
                import asyncio as _aio_sc2
                case_id =await _aio_sc2 .to_thread (
                    self .save_case ,guild .id ,"unban",uid ,interaction .user .id ,reason ,
                    getattr (interaction .user ,'display_name' ,None )or str (interaction .user ))
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
                try :
                    from cogs .logs import send_action_log
                    _uobj =member
                    if _uobj is None and unban_done :
                        _uobj =fetched
                    if _uobj is not None :
                        await send_action_log (
                        guild ,'unban',_uobj ,interaction .user ,
                        reason =reason ,case_id =case_id )
                except Exception as _ulog :
                    log .debug (f'[MODPANEL] unban log: {_ulog}')
                confirm =success_embed ("Снятие апелляции / разбан",_desc ,guild =guild )
                # Уведомление панели (веб/Discord/email — в фоне)
                try :
                    from services .panel_notify import notify_panel_event as _np
                    _np (interaction ,'mod_action',
                    f"Разбан/снятие апелляции: {_who }",
                    f"Модератор: {interaction .user .display_name } · Дело #{case_id}")
                except Exception as _ex:
                    _log.debug("_execute_mod_action(): подавлено: %s", _ex)
                await _respond (interaction ,embed =confirm ,ephemeral =True )
            except Exception as ex :
                await _respond (interaction ,embed =error_embed (str (ex )),ephemeral =True )

        elif action =="clear":
            ch =getattr (interaction ,'channel',None )
            if ch is None or not hasattr (ch ,'purge'):
                await _respond (interaction ,embed =error_embed (
                'Очистка работает только в текстовом канале, где вызвана /modpanel.'),
                ephemeral =True )
                return
            try :
                count =max (1 ,min (int (amount )or 10 ,200 ))
            except Exception :
                count =10
            try :
                deleted =await ch .purge (limit =count )
            except discord .Forbidden :
                await _respond (interaction ,embed =error_embed (
                'У бота нет права «Управление сообщениями» в этом канале. '
                'Настройки сервера → Роли → роль бота.'),
                ephemeral =True )
                return
            except discord .HTTPException as ex :
                await _respond (interaction ,embed =error_embed (
                f'Не удалось удалить сообщения: {ex}'),
                ephemeral =True )
                return
            try :
                from services .staff_limits import record_hit as _sl_rec
                _sl_rec (guild .id ,interaction .user .id ,'clear',1 )
            except Exception as _re :
                log .debug (f'[STAFF_LIMIT] clear rec: {_re}')
            _where =getattr (ch ,'mention',None )or 'канале'
            confirm =success_embed (
            "Сообщения удалены",
            f"Удалено **{len(deleted)}** сообщений в {_where}",
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
            if action in ('mute', 'unmute'):
                gid = getattr(interaction, 'guild_id', None) or getattr(
                    getattr(interaction, 'guild', None), 'id', None)
                kinds = (mute_kinds_for if action == 'mute' else unmute_kinds_for)(
                    gid, interaction.user)
                if not kinds:
                    await _respond(interaction, embed=error_embed(
                        'Это действие тебе не выдано.'), ephemeral=True)
                    return False
                return True
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
    amount =None ,proof_link =None ,actor ='Панель' ,duration_cap =None ):
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
        # ИЕРАРХИЯ ПЕРСОНАЛА (владелец 2026-09-05: «модер наказывает модера
        # и куратора — беспредел»): персонал не наказывает персонал своего
        # уровня и выше; владелец бота/сервера/боты — вне юрисдикции.
        # Веб-панель шлёт PanelInteraction-путь (target=Member/ID) и сюда.
        try :
            from services .staff_hierarchy import check as _hcheck
            _hm =target if isinstance (target ,discord .Member ) \
            else guild .get_member (int (target_str )or 0 )
            _hok ,_hdeny ,_ ,_ =_hcheck (guild ,_actor ,_hm ,action )
            if not _hok :
                return False ,_hdeny
        except Exception as _hex :
            _log .debug ('[MODPANEL] hierarchy: %s',_hex )
        # Срок мута: 30 мин … 2 ч у всех (Sabotash 2026-09-02).
        if action in ('timeout','mute_chat','vmute') and amount :
            try :
                from services .staff_limits import mute_duration_error as _pderr
                _pc =duration_cap
                if _pc is None :
                    from services .staff_limits import effective_max_duration as _pcap
                    _pc =_pcap (guild .id ,'mute')
                # 0 = без ограничения (владелец / явный skip) — срок не режем
                if _pc :
                    _pm =parse_duration_minutes (amount ,30 )
                    _derr =_pderr (_pm *60 ,cap_sec =_pc )
                    if _derr :
                        return False ,_derr
            except Exception as _pex :
                _log .debug ('[MODPANEL] panel dur cap: %s',_pex )
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
        if action =='unwarn':
            # Снятие ПОСЛЕДНЕГО варна из панели (владелец 2026-09-05:
            # «не вижу в панели снять warn»). Право — ОТДЕЛЬНОЕ:
            # ACL «Снять варн» (ключ unwarn), как в /modpanel и /unwarn.
            try :
                from services .staff_limits import check_action as _slc
                _okw ,_deny =_slc (guild ,_actor ,'unwarn')
                if not _okw :
                    return False ,_deny or 'Лимит исчерпан'
            except Exception as _sx :
                _log .debug ('[MODPANEL] staff_limits unwarn: %s',_sx )
            w =self .bot .get_cog ('warnings')
            if w is None :
                return False ,'Модуль варнов не загружен'
            _tm =target if isinstance (target ,discord .Member ) \
            else guild .get_member (int (target_str )or 0 )
            if _tm is None :
                return False ,'Участника нет на сервере — снять варн нельзя'
            target =_tm
            removed ,total =await w .remove_last_warning (target ,_actor )
            if removed is None :
                return False ,'У участника нет предупреждений'
            try :
                from services .staff_limits import record_hit as _rec2
                _rec2 (guild .id ,getattr (_actor ,'id',0 )or 0 ,'unwarn',1 )
            except Exception as _rex :
                _log .debug ('[MODPANEL] unwarn rec: %s',_rex)
            return True ,(f"Снято: #{removed .get ('id')} — "
                          f"{removed .get ('reason','Не указана')}. "
                          f"Осталось варнов: {total}")
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
    async def _fix_vmute_role_connect (self ,guild ,vrole ):
        """У роли войс-мута НЕ должно быть запретов «Подключаться»/«Видеть»
        в голосовых каналах: она глушит микрофон (плюс сервер-мут), а не
        запрещает вход. Чиним ТОЛЬКО каналы с явным запретом (локально по
        кэшу оверрайдов), без вызовов API для остальных."""
        if vrole is None :
            return
        try :
            for ch in getattr (guild ,'voice_channels',[] )or []:
                ow =ch .overwrites_for (vrole )
                if ow is None :
                    continue
                deny =getattr (ow ,'deny',0 )
                # соединить запреты connect(1<<20)/view_channel(1<<10)
                if (int (deny )&(1 <<20 ))or (int (deny )&(1 <<10 )) :
                    await ch .set_permissions (
                        vrole ,connect =None ,view_channel =None ,
                        speak =None ,reason ='войс-мут: микрофон, а не запрет входа')
        except Exception as _ex :
            log .debug (f'[MODPANEL] fix vmute role connect: {_ex}')

    @commands .Cog .listener ()
    async def on_voice_state_update (self ,member ,before ,after ):
        """Зашёл в голосовой с ролью войс-мута → сервер-мут микрофона.
        Микрофон открывается только снятием мута (роль/срок/кнопка)."""
        try :
            if member is None or member .bot :
                return
            joined =after .channel is not None and before .channel is None
            if not joined :
                return
            _vrole =self ._punish_role (member .guild ,'vmute')
            if _vrole is None or _vrole not in member .roles :
                return
            if getattr (member .voice ,'mute',False ) :
                return
            await member .edit (mute =True ,reason ='активен войс-мут')
        except Exception as _ex :
            log .debug (f'[MODPANEL] on_voice_state_update: {_ex}')

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
                # истёк ВОЙС-мут → вернуть микрофон; истёк чат-мут при нативном
                # таймауте → его не трогаем (native снимется сам по сроку)
                if member is not None :
                    try :
                        from services import punish_roles as _PR2
                        if rid ==_PR2 .role_for (gid ,'vmute') :
                            from services import mute_state as _ms
                            await _ms .clear_voice_mute (guild ,member )
                    except Exception as _ex :
                        log .debug (f'[MODPANEL] авто-анмьют микрофона: {_ex}')
                PR .clear (gid ,uid ,rid )
                if member is not None :
                    try :
                        from cogs .logs import send_action_log
                        from services import punish_roles as _PR3
                        if rid ==_PR3 .role_for (gid ,'ban'):
                            _act ='unban'
                        elif rid ==_PR3 .role_for (gid ,'mute'):
                            _act ='unmute_chat'
                        elif rid ==_PR3 .role_for (gid ,'vmute'):
                            _act ='vunmute'
                        else :
                            _act ='untimeout'
                        await send_action_log (
                        guild ,_act ,member ,None ,
                        reason ='срок наказания истёк')
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
            from services.async_io import load_json_async ,save_json_async
            # 1) Считаем мьюты пользователя (чтение файла — в потоке)
            mod_file ='data/mod_data.json'
            mute_count =0
            data =await load_json_async (mod_file ,{},log =log )or {}
            cases =data .get ('cases',{}).get (str (interaction .guild .id ),[])
            for c in cases :
                if str (c .get ('user_id',''))==str (user .id )and c .get ('action')in ('timeout','mute_chat','vmute'):
                    mute_count +=1
            # 2) Добавляем в watchlist (advanced_mod) на 1 неделю
            adv_file ='data/mod_advanced_data.json'
            adv =await load_json_async (adv_file ,{},log =log )or {}
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
            await save_json_async (adv_file ,adv ,log =log )
            # Панель «Наблюдение» обновляется по событию, а не опросом по
            # таймеру: без этой публикации страница не узнает о новом
            # фигуранте, пока её не откроют заново.
            try :
                from services import live_bus
                live_bus .publish (interaction .guild .id ,'watchlist')
            except Exception as _ex :
                log .debug ("[watchlist auto] live_bus: %s",_ex )
        except Exception as ex :
            log .debug ("[watchlist auto] %s",ex )


# ═══════════════════════════════════════════════════════════════════
#  SELECT-МЕНЮ МОДЕРАЦИИ (без кнопок/эмодзи — только выпадающие меню)
# ═══════════════════════════════════════════════════════════════════
# ── Наказания из веб-панели («Пользователи») ─────────────────────────────
# Тот же путь исполнения, что у /modpanel, но «модератором» выступает
# панель: действия пишутся в дела и логи от имени «Панель: <логин>».
PANEL_ACTIONS = ('warn', 'unwarn', 'timeout', 'mute_chat', 'vmute', 'ban',
                 'unban', 'untimeout', 'vunmute', 'unmute_chat')


# ═══════════════════════════════════════════════════════════════════════════
#  ПКМ-МЕНЮ: правый клик по участнику → Приложения → мут/войс-мут/снять
#  (владелец 2026-09-05: «чтобы через ПКМ»). Те же ACL, лимиты и дела,
#  что у /modpanel и панели — единый путь apply_panel_action.
# ═══════════════════════════════════════════════════════════════════════════
class _CtxMuteModal(discord.ui.Modal):
    """Окно мута из ПКМ: срок + причина."""

    duration = discord.ui.TextInput(
        label='Срок (30 мин … 2 ч)', placeholder='30, 60, 2ч',
        required=True, max_length=16)
    reason = discord.ui.TextInput(
        label='Причина', style=discord.TextStyle.paragraph,
        max_length=300, required=False)

    def __init__(self, cog, member, action, acl_key, limit_key, label):
        super().__init__(timeout=180)
        self._cog = cog
        self._member = member
        self._action = action
        self._acl_key = acl_key
        self._limit_key = limit_key
        self._label = label

    async def on_submit(self, interaction):
        from services.permission_acl import check_action as _acl
        if not _acl(interaction.guild_id, interaction.user, self._acl_key):
            await interaction.response.send_message(
                '🚫 Действие тебе не выдано (панель → Доступ → Права команд → '
                'Классические разрешения).', ephemeral=True)
            return
        # дневные лимиты персонала — как у команды из /modpanel
        try:
            from services.staff_limits import check_action as _slc
            _ok, _deny = _slc(interaction.guild, interaction.user,
                              self._limit_key)
            if not _ok:
                await interaction.response.send_message(_deny or 'Лимит исчерпан',
                                                        ephemeral=True)
                return
        except Exception as _sx:
            log.debug(f'[ПКМ] staff_limits: {_sx}')
        _dur_cap = None
        try:
            from services.staff_limits import effective_max_duration as _pcap
            _roles = [r.id for r in (getattr(interaction.user, 'roles', None) or [])
                      if getattr(r, 'id', None) != getattr(interaction.guild, 'id', None)]
            _dur_cap = _pcap(interaction.guild.id, 'mute', _roles)
        except Exception as _cx:
            log.debug(f'[ПКМ] duration cap: {_cx}')
        ok, text = await self._cog.apply_panel_action(
            interaction.guild, self._member, self._action,
            reason=(str(self.reason.value or '').strip()
                    or 'Причина не указана'),
            amount=str(self.duration.value or '').strip(),
            actor=getattr(interaction.user, 'display_name', None)
            or str(interaction.user),
            duration_cap=_dur_cap)
        # успех — в дневной счётчик модератора
        if ok:
            try:
                from services.staff_limits import record_hit as _rec
                _rec(interaction.guild_id, interaction.user.id,
                     self._limit_key, 1)
            except Exception as _rx:
                log.debug(f'[ПКМ] record: {_rx}')
        await interaction.response.send_message(
            ('✅ ' if ok else '⚠️ ') + str(text or ('Готово' if ok else 'Не получилось')),
            ephemeral=True)


def _mod_cog_of(interaction):
    try:
        return interaction.client.get_cog('Moderation')
    except Exception:
        return None


@app_commands.context_menu(name='🔇 Мут (чат + войс)')
async def ctx_full_mute(interaction, member: discord.Member):
    """Мут через ПКМ: обе роли сразу (чат + микрофон)."""
    if member.bot or member.id == interaction.user.id:
        return await interaction.response.send_message(
            'Себе и ботам мут не выдать.', ephemeral=True)
    mod = _mod_cog_of(interaction)
    if mod is None:
        return await interaction.response.send_message(
            'Модуль модерации не загружен.', ephemeral=True)
    await interaction.response.send_modal(_CtxMuteModal(
        mod, member, 'timeout', 'timeout', 'mute', 'Мут (чат + войс)'))


@app_commands.context_menu(name='🎙️ Войс-мут (микрофон)')
async def ctx_voice_mute(interaction, member: discord.Member):
    """Войс-мут через ПКМ: микрофон закрыт, зайти в войс можно."""
    if member.bot or member.id == interaction.user.id:
        return await interaction.response.send_message(
            'Себе и ботам мут не выдать.', ephemeral=True)
    mod = _mod_cog_of(interaction)
    if mod is None:
        return await interaction.response.send_message(
            'Модуль модерации не загружен.', ephemeral=True)
    await interaction.response.send_modal(_CtxMuteModal(
        mod, member, 'vmute', 'vmute', 'mute', 'Войс-мут'))


@app_commands.context_menu(name='🔊 Снять муты')
async def ctx_unmute(interaction, member: discord.Member):
    """Снять мут через ПКМ: сначала выбор чат / войс."""
    kinds = unmute_kinds_for(interaction.guild_id, interaction.user)
    if not kinds:
        return await interaction.response.send_message(
            'Снять мут тебе не выдано (панель → Доступ → Права команд).',
            ephemeral=True)
    mod = _mod_cog_of(interaction)
    if mod is None:
        return await interaction.response.send_message(
            'Модуль модерации не загружен.', ephemeral=True)
    embed = discord.Embed(
        title="Снять мут",
        description=f"{member.mention}\nКак снять — чат или войс.",
        color=0x2ECC71)
    await interaction.response.send_message(
        embed=embed,
        view=UnmuteKindView(mod, member.id, kinds, member=interaction.user),
        ephemeral=True)


_CTX_COMMANDS = (ctx_full_mute, ctx_voice_mute, ctx_unmute)


async def _ctx_setup(bot):
    """Зарегистрировать ПКМ-команды (идемпотентно при перезагрузке)."""
    for _cmd in _CTX_COMMANDS:
        try:
            bot.tree.add_command(_cmd)
        except discord.app_commands.CommandAlreadyRegistered:
            # перезагрузка кога — команда уже в дереве, это норма
            log.debug('ПКМ-команда уже зарегистрирована: %s',
                      getattr(_cmd, 'name', '?'))


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
# 4-е поле — ГРУППА ДЛЯ ЛИМИТОВ («Лимиты команды» в Щите сервера): таймаут,
# чат-мут и войс-мут — это один потолок «муты» (см. staff_limits DURATION_KEYS).
# РАЗРЕШЕНИЯ при этом раздельные — их задаёт MODPANEL_ACL_KEYS ниже.
# kick НАМЕРЕННО отсутствует: система кика отключена владельцем (см. обработку
# action == "kick" — вежливый отказ). Не добавлять.
# Порядок — для удобства (заказ владельца): варн → мут-семейство (таймаут,
# чат-мут, войс-мут и их снятия) → ОЧИСТКА → бан/апелляция внизу (снятие бана
# — следующим после бана).
MODPANEL_ACTIONS = [
    # Описания — КОРОТКИЕ и по-человечески (владелец 2026-09-05: «не надо
    # такое подробное и тупое»): селект — выбор действия, не инструкция.
    # Мут/размут — ОДИН пункт, вид (чат/войс/оба) прячется во второй селект.
    ("warn", "Варн", "Предупреждение за нарушение", "warn"),
    ("unwarn", "Снять варн", "Убрать последний варн", "warn"),
    ("mute", "Мут", "Чат, войс или оба — следующим шагом", "mute"),
    ("unmute", "Снять мут", "Чат или войс — следующим шагом", "unmute"),
    ("clear", "Очистка сообщений", "Удалить сообщения в канале", "clear"),
    ("ban", "Бан", "Закрыть каналы", "ban"),
    ("unban", "Снять бан", "Вернуть доступ (по ID)", "unban"),
]

# Эмодзи действий: меню панели живое, а не текстовое
MODPANEL_EMOJI = {
    "warn": "⚠️",
    "unwarn": "📵",
    "ban": "🚫",
    "mute": "🔇",
    "timeout": "🔇",
    "mute_chat": "🤐",
    "vmute": "🎙️",
    "unban": "✅",
    "clear": "🧹",
    "untimeout": "🔊",
    "vunmute": "🎤",
    "unmute": "🔊",
    "unmute_chat": "💬",
}

# Пункт /modpanel → «классическое» разрешение (панель → Доступ → Права
# команд → Классические разрешения). Ключи — как в permission_acl.ACTIONS:
# не дал модератору «Бан» → у него в /modpanel нет ни «Бан», ни «Разбан»;
# не дал «Мут» → нет мута чата/войса и снятий; «Таймаут» → нет таймаута
# и снятия; «Очистка» → нет чистки. Правило не задано — действие доступно.
# Каждый пункт панели — ОТДЕЛЬНОЕ «классическое» разрешение, которое владелец
# включает роли в панели (Доступ → Права команд → Классические разрешения).
# Чат-мут и войс-мут разделены: «Мут чата» не даёт войс и наоборот. Снятие
# мута следует за выдачей (нет права мутить — нечего и снимать), разблокировка
# следует за баном. По умолчанию действие ЗАПРЕЩЕНО (check_action default-deny),
# Discord-права не учитываются — система прав полностью своя.
MODPANEL_ACL_KEYS = {
    "warn": "warn",
    "unwarn": "unwarn",
    "ban": "ban",
    "unban": "ban",
    "mute": "mute",
    "timeout": "timeout",
    "untimeout": "timeout",
    "unmute": "timeout",
    "unmute_chat": "mute",
    "mute_chat": "mute",
    "vmute": "vmute",
    "vunmute": "vmute",
    "clear": "purge",
}


def mute_kinds_for(guild_id, member):
    """Какие виды мута доступны: чат / войс / оба."""
    chat = _action_acl_allows(guild_id, member, 'mute_chat')
    voice = _action_acl_allows(guild_id, member, 'vmute')
    both = _action_acl_allows(guild_id, member, 'timeout')
    out = []
    if chat:
        out.append(('mute_chat', 'Чат', 'Закрыть переписку'))
    if voice:
        out.append(('vmute', 'Войс', 'Выключить микрофон'))
    if both:
        out.append(('timeout', 'Чат и войс', 'Заглушить оба'))
    return out


def unmute_kinds_for(guild_id, member):
    """Какие виды размута доступны: чат / войс / оба."""
    chat = _action_acl_allows(guild_id, member, 'mute_chat') \
        or _action_acl_allows(guild_id, member, 'timeout')
    voice = _action_acl_allows(guild_id, member, 'vmute') \
        or _action_acl_allows(guild_id, member, 'timeout')
    out = []
    if chat:
        out.append(('unmute_chat', 'Чат', 'Вернуть переписку'))
    if voice:
        out.append(('vunmute', 'Войс', 'Вернуть микрофон'))
    if chat and voice:
        out.append(('untimeout', 'Чат и войс', 'Снять оба мута'))
    return out


def _action_acl_allows(guild_id, member, action_name):
    """Разрешено ли модератору действие action_name «классическим» ACL.

    Строгая модель: check_action возвращает True только если у модератора есть
    роль, которой это действие явно разрешено в панели. Нет правила → скрываем
    (default-deny). Сбой чтения БД — тоже скрываем (fail-close): лучше не
    показать пункт, чем дать невыданное право.
    """
    if action_name == 'unmute':
        return bool(unmute_kinds_for(guild_id, member))
    if action_name == 'mute':
        return bool(mute_kinds_for(guild_id, member))
    key = MODPANEL_ACL_KEYS.get(action_name)
    if not key:
        return False
    try:
        from services.permission_acl import check_action as _acl_check
        return bool(_acl_check(guild_id, member, key))
    except Exception:
        log.debug('actions_for_member: ACL-проверка %s — сбой, пункт скрыт', action_name)
        return False


def actions_for_member(guild, member):
    """Какие действия панели показывать модератору.

    СТРОГАЯ МОДЕЛЬ (своя система, Discord-права не учитываются):
      • владелец БОТА (OWNER_ID/OWNER_IDS) — видит всё;
      • владелец СЕРВЕРА в Discord и админ — НЕ дают прав;
      • по умолчанию модератор не видит НИЧЕГО — пункт показывается, только
        если его роль явно разрешена в панели (Доступ → Права команд →
        Классические разрешения).
    Дополнительно работают «Лимиты команды» (Щит сервера → Лимиты → роль):
    если у ролей модератора заданы лимиты только на часть действий, видит
    только их (пересечение с разрешениями).
    """
    try:
        uid = getattr(member, "id", 0)
        from config import Config as _Cfg
        if uid in _Cfg.all_owner_ids():
            return list(MODPANEL_ACTIONS)
    except Exception:
        log.debug('actions_for_member: owner-проверка не удалась')
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


class MuteKindSelect(discord.ui.Select):
    """Второй шаг мута: чат / войс / оба. Дальше — модалка срока."""

    def __init__(self, cog, target_id, kinds):
        options = [discord.SelectOption(
            label=label, value=value, description=desc,
            emoji=MODPANEL_EMOJI.get(value, '🔇'))
            for value, label, desc in kinds]
        super().__init__(placeholder="Какой мут?",
                         options=options, min_values=1, max_values=1)
        self.cog = cog
        self.target_id = str(target_id)

    async def callback(self, interaction: discord.Interaction):
        action = self.values[0]
        if not await self.cog._ensure_action_acl(interaction, action):
            return
        modal = ModActionModal(self.cog, action, guild=interaction.guild,
                               prefill_target=self.target_id,
                               user=interaction.user)
        await interaction.response.send_modal(modal)


class MuteKindView(discord.ui.View):
    """Короткое меню «чат / войс / оба» после пункта «Мут»."""

    def __init__(self, cog, target_id, kinds, member=None):
        super().__init__(timeout=180)
        self.cog = cog
        self.member = member
        self.add_item(MuteKindSelect(cog, target_id, kinds))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.member and getattr(interaction.user, 'id', None) != getattr(self.member, 'id', None):
            await interaction.response.send_message(
                'Это меню другого модератора.', ephemeral=True)
            return False
        return True


class UnmuteKindSelect(discord.ui.Select):
    """Второй шаг размута: чат / войс / оба. Без ввода и без кнопок."""

    def __init__(self, cog, target_id, kinds):
        options = [discord.SelectOption(
            label=label, value=value, description=desc,
            emoji=MODPANEL_EMOJI.get(value, '🔊'))
            for value, label, desc in kinds]
        super().__init__(placeholder="Как снять мут?",
                         options=options, min_values=1, max_values=1)
        self.cog = cog
        self.target_id = str(target_id)

    async def callback(self, interaction: discord.Interaction):
        action = self.values[0]
        if not await self.cog._ensure_action_acl(interaction, action):
            return
        await _ack(interaction)
        await self.cog._execute_mod_action(
            interaction, action, self.target_id,
            'Снято через панель', '', proof_link=None)


class UnmuteKindView(discord.ui.View):
    """Короткое меню «чат или войс» после пункта «Снять мут»."""

    def __init__(self, cog, target_id, kinds, member=None):
        super().__init__(timeout=180)
        self.cog = cog
        self.member = member
        self.add_item(UnmuteKindSelect(cog, target_id, kinds))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.member and getattr(interaction.user, 'id', None) != getattr(self.member, 'id', None):
            await interaction.response.send_message(
                'Это меню другого модератора.', ephemeral=True)
            return False
        return True


async def _silent_reset_panel(interaction, panel):
    """Сбросить селект наказаний, чтобы то же действие можно было выбрать снова.

    Discord не шлёт callback, если кликнуть уже выбранный пункт — поэтому
    после шага собираем меню заново и пушим в сообщение.

    После send_modal ответ взаимодействия уже занят, поэтому правим
    эфемерную панель токеном исходного /modpanel (_root_edit), а не
    interaction.message.edit (у эфемерки он часто падает).
    Если пуш не вышел — возвращаем старые селекты, иначе custom_id разъедутся.
    """
    try:
        guild = getattr(interaction, 'guild', None)
        old_t, old_a = panel.target_select, panel.action_select
        panel._rebuild(guild)
        embed = panel.panel_embed(guild)
        pushed = False
        root = getattr(panel, '_root_edit', None)
        if root is not None:
            try:
                await root(embed=embed, view=panel)
                pushed = True
            except Exception as _e:
                log.debug('modpanel reset root: %s', _e)
        if not pushed:
            try:
                msg = getattr(interaction, 'message', None)
                if msg is not None:
                    await msg.edit(embed=embed, view=panel)
                    pushed = True
            except Exception as _e:
                log.debug('modpanel reset msg.edit: %s', _e)
        if not pushed:
            try:
                await interaction.edit_original_response(embed=embed, view=panel)
                pushed = True
            except Exception as _e:
                log.debug('modpanel reset original: %s', _e)
        if not pushed:
            panel.clear_items()
            panel.target_select, panel.action_select = old_t, old_a
            panel.add_item(old_t)
            panel.add_item(old_a)
    except Exception as _e:
        log.debug('modpanel reset: %s', _e)


async def _launch_action(cog, interaction, action, prefill, panel=None):
    """Открыть модалку / размут. panel — чтобы потом сбросить селект."""
    if action == "mute":
        gid = getattr(interaction, 'guild_id', None) or getattr(
            getattr(interaction, 'guild', None), 'id', None)
        kinds = mute_kinds_for(gid, interaction.user)
        if not kinds:
            await _respond(interaction, embed=error_embed(
                'Мут тебе не выдан.'), ephemeral=True)
            return
        if not prefill:
            await _respond(interaction, embed=error_embed(
                'Сначала выберите участника — или выберите его сейчас в меню.'),
                ephemeral=True)
            return
        if panel is not None:
            panel.pending_action = None
        if len(kinds) == 1:
            modal = ModActionModal(cog, kinds[0][0], guild=interaction.guild,
                                   prefill_target=prefill, user=interaction.user)
            await interaction.response.send_modal(modal)
            if panel is not None:
                await _silent_reset_panel(interaction, panel)
            return
        who = prefill
        try:
            mem = interaction.guild.get_member(int(prefill))
            if mem is not None:
                who = mem.mention
        except Exception:
            pass
        embed = discord.Embed(
            title="Мут",
            description=f"{who}\nКакой — чат, войс или оба.",
            color=0xE67E22)
        await interaction.response.send_message(
            embed=embed,
            view=MuteKindView(cog, prefill, kinds, member=interaction.user),
            ephemeral=True)
        if panel is not None:
            await _silent_reset_panel(interaction, panel)
        return
    if action == "unmute":
        gid = getattr(interaction, 'guild_id', None) or getattr(
            getattr(interaction, 'guild', None), 'id', None)
        kinds = unmute_kinds_for(gid, interaction.user)
        if not kinds:
            await _respond(interaction, embed=error_embed(
                'Снять мут тебе не выдано.'), ephemeral=True)
            return
        if not prefill:
            await _respond(interaction, embed=error_embed(
                'Сначала выберите участника — или выберите его сейчас в меню.'),
                ephemeral=True)
            return
        if panel is not None:
            panel.pending_action = None
        if len(kinds) == 1:
            await _ack(interaction)
            await cog._execute_mod_action(
                interaction, kinds[0][0], prefill,
                'Снято через панель', '', proof_link=None)
            if panel is not None:
                await _silent_reset_panel(interaction, panel)
            return
        who = prefill
        try:
            mem = interaction.guild.get_member(int(prefill))
            if mem is not None:
                who = mem.mention
        except Exception:
            pass
        embed = discord.Embed(
            title="Снять мут",
            description=f"{who}\nКак снять — чат или войс.",
            color=0x2ECC71)
        await interaction.response.send_message(
            embed=embed,
            view=UnmuteKindView(cog, prefill, kinds, member=interaction.user),
            ephemeral=True)
        if panel is not None:
            await _silent_reset_panel(interaction, panel)
        return
    modal = ModActionModal(cog, action, guild=interaction.guild,
                           prefill_target=prefill, user=interaction.user)
    await interaction.response.send_modal(modal)
    if panel is not None:
        panel.pending_action = None
        await _silent_reset_panel(interaction, panel)


class ModActionSelect(discord.ui.Select):
    """Выбор действия модерации — только то, что доступно этому модератору."""

    def __init__(self, cog, member=None, allowed=None, target_select=None):
        acts = allowed if allowed is not None else MODPANEL_ACTIONS
        options = [discord.SelectOption(
                       label=label, value=value, description=desc,
                       emoji=MODPANEL_EMOJI.get(value, '⚡'))
                   for value, label, desc, _key in acts]
        super().__init__(
            placeholder="Что сделать?",
            options=options,
            min_values=1,
            max_values=1,
        )
        self.cog = cog
        self.target_select = target_select

    async def callback(self, interaction: discord.Interaction):
        action = self.values[0]
        if not await self.cog._ensure_action_acl(interaction, action):
            return
        view = self.view
        prefill = ""
        if view is not None:
            prefill = str(getattr(view, 'selected_uid', None) or '')
            view.pending_action = action
        if not prefill:
            try:
                _sel = getattr(self, "target_select", None)
                _vals = list(getattr(_sel, "values", []) or [])
                if _vals:
                    prefill = str(_vals[0].id)
                    if view is not None:
                        view.selected_uid = prefill
            except Exception as _pe:
                log.debug("modpanel prefill цели: %s", _pe)
        # Действие без участника: запоминаем и ждём выбор человека
        # (можно и наоборот — сначала человек, потом действие).
        if action != "clear" and not prefill:
            if view is not None:
                await view.refresh(interaction)
                return
        await _launch_action(self.cog, interaction, action, prefill, panel=view)

_PUNISH_MODPANEL = ("ban", "timeout", "mute_chat", "vmute")


class ModActionModal(discord.ui.Modal):
    """Модальное окно ввода — поля строго под выбранное действие.

    «Очистка» спрашивает только количество и причину (никакой демки),
    разбан/размут — цель и причину, наказания — демку, НО только если
    требование включено в панели.
    """

    def __init__(self, cog, action, guild=None, prefill_target="", user=None):
        self.cog = cog
        self.action = action
        titles = {
            "warn": "Варн",
            "ban": "Бан",
            "timeout": "Мут (чат + войс)",
            "mute_chat": "Мут (только чат)",
            "vmute": "Мут (только войс)",
            "unban": "Снять бан",
            "clear": "Очистка сообщений",
            "untimeout": "Размут (чат + войс)",
            "vunmute": "Размут (войс)",
        }
        super().__init__(title=titles.get(action, "Модерация"))

        # Цель, выбранная мышкой в панели, приходит как fixed_target_id —
        # поле ввода НИКА в модалку не ставим вовсе (жалоба владельца:
        # «выбрал участника — просит ник ещё раз, убери»). Поле остаётся
        # только для ручного пути (ник/ID вписываются руками).
        self.fixed_target_id = str(prefill_target or "").strip() or None
        if action != "clear" and not self.fixed_target_id:
            self.target = discord.ui.TextInput(
                label="Цель (@ник, точное имя или ID)", required=True,
                placeholder="@упоминание, ник или 15-22 цифры ID",
            )
            self.add_item(self.target)
        if action in ("timeout", "mute_chat", "vmute", "clear"):
            if action == "clear":
                _lbl, _ph = "Сколько сообщений удалить?", "1-100"
                self.amount = discord.ui.TextInput(
                    label=_lbl, required=False, placeholder=_ph, default="10",
                )
            else:
                self.amount = discord.ui.TextInput(
                    label="На сколько? (30 мин … 2 ч)", required=True,
                    placeholder="30, 60, 2ч",
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
            # Белый список «без демки» (панель → Доказательства): доверенному
            # модератору поле «Доказательство» не ставим ВООБЩЕ. Раньше
            # список был, а модалка его игнорировала — обязательное поле
            # оставалось у всех (владелец 2026-09-05).
            if _need_proof and user is not None:
                try:
                    from cogs.proof_cog import proof_is_whitelisted
                    _need_proof = not proof_is_whitelisted(
                        getattr(guild, 'id', 0) or 0,
                        user_id=getattr(user, 'id', 0),
                        role_ids=[getattr(r, 'id', 0)
                                  for r in getattr(user, 'roles', []) or []])
                except Exception as _wlx:
                    log.debug(f'_need_proof whitelist: {_wlx}')
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
        _target_value = self.fixed_target_id or ((_t.value or "").strip() if _t else "")
        await self.cog._execute_mod_action(
            interaction,
            self.action,
            _target_value,
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
            value='Выберите участника МЫШКОЙ в меню «Кого наказать?» — при выборе '
                  'действия бот НЕ попросит ник второй раз. Участник ушёл с сервера? '
                  'Он останется в списке выбора: подойдёт и его ID.',
            inline=False)
        embed.add_field(
            name='⏱ Срок',
            value='Муты: от 30 минут до 2 часов. «30», «60», «2ч». Просто число = минуты.',
            inline=False)
        embed.add_field(
            name='🚫 Бан — это апелляция',
            value='Участник остаётся на сервере, все каналы закрыты. Канал '
                  'апелляции откроется ему сам — после подачи апелляции в ЛС '
                  'боту (/апелляция). Канал задаёт владелец: Панель → Каналы '
                  'и маршруты.',
            inline=False)
        embed.add_field(
            name='🧹 Чистка',
            value='Удаляет N последних сообщений в канале, где вы находитесь.',
            inline=False)
        embed.set_footer(text='Шпаргалка · панель Hakumo')
        await interaction.response.send_message(embed=embed, ephemeral=True)


class ModTargetSelect(discord.ui.UserSelect):
    """Участник мышкой. Можно выбрать ДО действия или ПОСЛЕ — порядок любой."""

    def __init__(self, cog, default_values=None):
        kw = dict(placeholder="Кого наказать?", min_values=1, max_values=1)
        if default_values:
            kw['default_values'] = list(default_values)
        super().__init__(**kw)
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        try:
            vals = list(self.values or [])
            if view is not None and vals:
                view.selected_uid = str(vals[0].id)
        except Exception as _pe:
            log.debug("ModTargetSelect uid: %s", _pe)
        pending = getattr(view, 'pending_action', None) if view is not None else None
        prefill = getattr(view, 'selected_uid', None) if view is not None else None
        if pending and prefill:
            await _launch_action(self.cog, interaction, pending, prefill, panel=view)
            return
        # Только запомнили человека — без «думает…», мгновенный апдейт меню.
        if view is not None:
            await view.refresh(interaction, rebuild_action=False)
            return
        try:
            if not interaction.response.is_done():
                await interaction.response.defer()
        except Exception as _te:
            log.debug("ModTargetSelect: %s", _te)


class ModPanelView(discord.ui.View):
    """Селект участника + селект действия. Порядок любой, пункт можно выбрать снова."""

    def __init__(self, cog, member=None, allowed=None):
        super().__init__(timeout=300)
        self.cog = cog
        self.allowed = allowed
        self.owner_id = getattr(member, 'id', None)
        self.selected_uid = None
        self.pending_action = None
        self._root_edit = None  # interaction.edit_original_response от /modpanel
        self._rebuild(None)

    def _action_label(self, action):
        for value, label, _d, _k in (self.allowed or MODPANEL_ACTIONS):
            if value == action:
                return label
        return action

    def panel_embed(self, guild):
        bits = []
        if self.selected_uid:
            bits.append(f"участник <@{self.selected_uid}>")
        if self.pending_action:
            bits.append(f"«{self._action_label(self.pending_action)}»")
        if bits:
            desc = " · ".join(bits) + "\nМожно выбрать заново и в любом порядке."
        else:
            desc = "Участник и действие — в любом порядке."
        e = discord.Embed(title="🛡 Панель модерации", description=desc, color=0x5865F2)
        icon = getattr(getattr(guild, 'icon', None), 'url', None)
        name = getattr(guild, 'name', None) if guild is not None else None
        if name and icon:
            e.set_footer(text=name, icon_url=icon)
        elif name:
            e.set_footer(text=name)
        return e

    def _rebuild(self, guild):
        self.clear_items()
        defaults = []
        if self.selected_uid and guild is not None:
            try:
                mem = guild.get_member(int(self.selected_uid))
                if mem is not None:
                    defaults = [mem]
            except Exception:
                defaults = []
        self.target_select = ModTargetSelect(self.cog, default_values=defaults or None)
        self.action_select = ModActionSelect(self.cog, None, self.allowed,
                                             target_select=self.target_select)
        self.add_item(self.target_select)
        self.add_item(self.action_select)

    async def refresh(self, interaction, *, rebuild_action=True):
        guild = getattr(interaction, 'guild', None)
        if rebuild_action:
            self._rebuild(guild)
        embed = self.panel_embed(guild)
        try:
            if not interaction.response.is_done():
                await interaction.response.edit_message(embed=embed, view=self)
                return
        except Exception as _e:
            log.debug('modpanel refresh edit_message: %s', _e)
        msg = getattr(interaction, 'message', None)
        if msg is not None:
            try:
                await msg.edit(embed=embed, view=self)
                return
            except Exception as _e:
                log.debug('modpanel refresh msg.edit: %s', _e)
        try:
            await interaction.edit_original_response(embed=embed, view=self)
        except Exception as _e:
            log.debug('modpanel refresh original: %s', _e)
            try:
                if not interaction.response.is_done():
                    await interaction.response.defer()
            except Exception:
                pass

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        user = interaction.user
        if self.owner_id and getattr(user, 'id', None) == self.owner_id:
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
            log.debug('ModPanelView.interaction_check: ACL не прочитан (%s)', _ex)
        return True


async def setup (bot ):
    await bot .add_cog (Moderation (bot ))
    await _ctx_setup (bot )   # ПКМ-меню: мут/войс-мут/снять муты
