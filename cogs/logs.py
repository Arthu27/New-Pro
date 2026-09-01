import discord
from discord.ext import commands
from discord import app_commands
import datetime
import json
import os
import re
import time
import threading
import queue
from typing import Dict, Any 

from logger import get_logger 
from config import Config 
from services .audit_labels import audit_label 
log =get_logger ("logs")


AUDIT_FILE ="data/audit_log.json"

CATEGORIES ={
'mod':{'label':'Модерация','emoji':'🛡','color':0xE74C3C ,'channel':'модерация'},
'member':{'label':'Участники','emoji':'👋','color':0x2ECC71 ,'channel':'участники'},
'message':{'label':'Сообщения','emoji':'💬','color':0x3498DB ,'channel':'сообщения'},
'role':{'label':'Роли','emoji':'🎭','color':0x9B59B6 ,'channel':'сервер'},
'channel':{'label':'Каналы','emoji':'🗂','color':0xF39C12 ,'channel':'сервер'},
'voice':{'label':'Голос','emoji':'🔊','color':0x1ABC9C ,'channel':'голос'},
'сервер':{'label':'Сервер','emoji':'🏠','color':0xE67E22 ,'channel':'сервер'},
'automod':{'label':'Автоматически','emoji':'⚔','color':0xE74C3C ,'channel':'модерация'},
'invite':{'label':'Приглашения','emoji':'🔗','color':0x95A5A6 ,'channel':'сервер'},
'proof':{'label':'Доказательства','emoji':'📸','color':0x9B59B6 ,'channel':'доказательства'},
}

DIV =" \u2022 "

# Кэш сообщений — чтобы знать содержимое удалённых
_msg_cache :dict ={}

# Запись через очередь — один поток, нет race condition
_audit_queue :queue .Queue =queue .Queue ()
_audit_worker_thread :threading .Thread =None 

def _audit_worker ():
    while True :
        try :
            event_data =_audit_queue .get (timeout =2.0 )
        except queue .Empty as _ex:
            log.debug("_audit_worker(): подавлено: %s", _ex)
            continue 
        if event_data is None :
            break 
        try :
            _write_audit_event (event_data )
        except Exception as e :
            log .info (f"[AUDIT-WORKER] Ошибка запись: {e}")
        finally :
            _audit_queue .task_done ()

def _write_audit_event (event_data :Dict [str ,Any ]):
    guild_id =event_data ['guild_id']
    category =event_data ['category']
    action =event_data ['action']
    details =event_data ['details']

    os .makedirs ("data",exist_ok =True )
    data ={}
    if os .path .exists (AUDIT_FILE ):
        for _ in range (5 ):
            try :
                with open (AUDIT_FILE ,'r',encoding ='utf-8')as f :
                    data =json .load (f )
                break 
            except (json .JSONDecodeError ,OSError ):
                time .sleep (0.1 )

    gid =str (guild_id )
    data .setdefault (gid ,[])
    data [gid ].append ({
    'category':category ,
    'action':action ,
    'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat (),
    **details 
    })
    if len (data [gid ])>2000 :
        data [gid ]=data [gid ][-2000 :]

    tmp =AUDIT_FILE +f'.tmp{os.getpid()}'
    try :
        with open (tmp ,'w',encoding ='utf-8')as f :
            json .dump (data ,f ,indent =2 ,ensure_ascii =False )
        for _ in range (5 ):
            try :
                if os .path .exists (AUDIT_FILE ):
                    os .replace (tmp ,AUDIT_FILE )
                else :
                    os .rename (tmp ,AUDIT_FILE )
                break 
            except PermissionError :
                time .sleep (0.2 )
    except Exception as e :
        log .info (f"[AUDIT] Ошибка запись: {e}")
    finally :
        try :
            if os .path .exists (tmp ):
                os .remove (tmp )
        except Exception as _ex:
            log.debug("_write_audit_event(): подавлено: %s", _ex)

def _ensure_worker ():
    global _audit_worker_thread 
    if _audit_worker_thread is None or not _audit_worker_thread .is_alive ():
        _audit_worker_thread =threading .Thread (target =_audit_worker ,daemon =True ,name ="audit-worker")
        _audit_worker_thread .start ()

# Категория аудита → топики живых обновлений панели (services.live_bus).
# Одно событие может затрагивать несколько страниц — поэтому список.
# Какие топики панели дёрнуть при событии категории. 'logs' шлём всегда —
# консоль (/konsol) показывает любые события и должна обновляться пушем.
_CAT_TOPICS = {
    'mod': ('moderation', 'security', 'modcenter', 'logs'),
    'member': ('members', 'analytics', 'logs'),
    'voice': ('voice', 'analytics', 'logs'),
    'invite': ('invites', 'analytics', 'logs'),
    'message': ('logs',),
    'role': ('roles', 'members', 'logs'),
    'channel': ('channels', 'logs'),
}


def save_event (guild_id ,category ,action ,details :dict ):
    if action =='Сообщение отправлено':
        return
    # Живой пуш в панель: страницы обновятся сразу при событии, а не по таймеру.
    try :
        from services .live_bus import publish as _lp
        for _t in _CAT_TOPICS .get (str (category ),('logs',)):
            _lp (guild_id ,_t )
    except Exception as _live_ex :
        log .debug ('save_event live_publish: %s',_live_ex )
    _ensure_worker ()
    _audit_queue .put ({
    'guild_id':guild_id ,
    'category':category ,
    'action':action ,
    'details':details ,
    })


    # Имена лог-каналов — красиво и по-русски (эмодзи + ・ + слово).
    # Ключ 'голос' должен совпадать с CATEGORIES[voice]['channel'] — раньше
    # его не было ('ses'), и войс-логи улетали в канал «сервер» (древняя бага).
LOG_CHANNELS ={
'модерация':'🛡・модерация',
'moderasyon':'🛡・модерация',  # legacy alias (старые серверы)
'участники':'👋・участники',
'сообщения':'💬・сообщения',
'голос':'🔊・голос',
'ses':'🔊・голос',  # legacy alias
'сервер':'📋・сервер',
'доказательства':'📸・доказательства',
}
LOG_CATEGORY_NAME ='📚 Логи'
# Старые имена категории (до переименования) — находим и мягко обновляем
LOG_CATEGORY_LEGACY =[' Логи','Логи',' Logs','Logs','logs']

# Старые (legacy) имена каналов по каждому каноническому — раньше коги
# писали логи в разные каналы (mod-log, moderasyon, '-модерация', '-ses' …)
LEGACY_CHANNEL_NAMES ={
'🛡・модерация':['-модерация','mod-log','moderasyon','-moderasyon','modlog'],
'💬・сообщения':['-сообщения','message-log','сообщения-лог'],
'👋・участники':['-участники','member-log','участники-лог'],
'🔊・голос':['-ses','voice-log','ses-log','-голос'],
'📋・сервер':['-сервер','server-log','hakumo-logs','сервер-лог'],
'📸・доказательства':['-доказательства','proof-log','proofs','demki','демки'],
}


def log_category_display (category :str ='сервер'):
    """Красивое имя лог-канала категории (то, что видят участники)."""
    category ={'модерация':'mod','moderasyon':'mod','участники':'member',
    'сообщения':'message','голос':'voice','ses':'voice','роли':'role',
    'каналы':'channel'}.get (category ,category )
    ch_name =CATEGORIES .get (category ,{}).get ('channel','сервер')
    return LOG_CHANNELS .get (ch_name ,LOG_CHANNELS ['сервер'])


def _configured_log_channel (guild ,category ):
    """Канал, выбранный для категории в панели («Логи сервера»).

    Приоритет выше поиска по имени: владелец выбрал — туда и пишем.
    Канал исчез/удалён — тихо возвращаемся к прежнему поиску.
    """
    try :
        from services .log_settings import target_channel_id
        _cat ={'модерация':'mod','moderasyon':'mod','участники':'member',
        'сообщения':'message','голос':'voice','ses':'voice','роли':'role',
        'каналы':'channel'}.get (category ,category )
        _cid =target_channel_id (guild .id ,_cat )
        if _cid :
            _ch =(guild .get_channel_or_thread (int (_cid ))
                   if hasattr (guild ,"get_channel_or_thread")
                   else guild .get_channel (int (_cid )))
            if _ch is not None :
                return _ch
    except Exception as _ex :
        log .debug (f'[LOGS] настроенный канал пропущен: {_ex}')
    return None


def find_log_channel (guild ,category :str ='сервер'):
    """Единый поиск лог-канала для категории.

    Порядок: канал из панели («Логи сервера») → каноническое имя
    (-модерация …) → legacy-имена (mod-log, moderasyon …) → общие старые
    каналы (server-log, hakumo-logs). None, если ничего нет.
    Используется ВСЕМИ когами — иначе логи уходят в несуществующие каналы.
    """
    _panel_ch =_configured_log_channel (guild ,category )
    if _panel_ch is not None :
        return _panel_ch
    target =log_category_display (category )

    candidates =[target ]+LEGACY_CHANNEL_NAMES .get (target ,[])+['server-log','hakumo-logs']
    # Нормализованная карта каналов: эмодзи/прочерки/регистр не мешают
    # (-mod-log, -moderasyon, -Модерация  — всё находится)
    _pool =list (guild .text_channels )+list (getattr (guild ,'forums',[])or [])
    norm_map ={}
    for _c in _pool :
        norm_map .setdefault (_norm_ch_name (_c .name ),_c )
    seen =set ()
    for name in candidates :
        nname =_norm_ch_name (name )
        if nname in seen :
            continue
        seen .add (nname )
        ch =norm_map .get (nname )or discord .utils .get (_pool ,name =name )
        if ch :
            return ch
    return None


def _norm_ch_name (name ):
    # -mod-log = modlog, -Moderasyon = moderasyon: сравнение без эмодзи и регистра
    import re as _re ,unicodedata as _ud
    try :
        _s =_ud .normalize ('NFKD',str (name or ''))
        return _re .sub (r'[^a-zа-яё0-9]+','',_s .lower ())
    except Exception :
        return str (name or '').lower ()


# Автосоздание: не давим на API — одна попытка на канал за 10 минут
_auto_create_state :dict ={}

async def ensure_log_channel (guild ,category :str ='сервер'):
    # Найти лог-канал, а если его нет — СОЗДАТЬ (самолечение системы).
    # Раньше отсутствующий канал означал тихую потерю логов навсегда.
    # Канал и скрытая категория (с правами бота) создаются на лету; троттлинг
    # 10 минут на случай отсутствия прав Manage Channels. None = не удалось.
    ch =find_log_channel (guild ,category )
    if ch :
        # Мягкая миграция внешнего вида: канал со старым уродливым именем
        # (-модерация, -ses …) переименовываем в красивое (🛡・модерация …)
        _pretty =log_category_display (category )
        if _pretty and ch .name !=_pretty :
            try :
                import asyncio as _asyncio
                _cor =ch .edit (name =_pretty ,reason ='Hakumo: красивое русское название лог-канала')
                if _asyncio .iscoroutine (_cor ):
                    await _cor 
                log .info (f'[LOGS] Канал переименован: #{ch.name} → #{_pretty}')
            except Exception as _rn:
                log .debug (f'[LOGS] переименование пропущено: {_rn}')
        return ch
    category ={'модерация':'mod','moderasyon':'mod','участники':'member',
    'сообщения':'message','голос':'voice','ses':'voice','роли':'role',
    'каналы':'channel'}.get (category ,category )
    ch_name =CATEGORIES .get (category ,{}).get ('channel','сервер')
    target =LOG_CHANNELS .get (ch_name ,None )
    # Сервисные каналы других модулей задаются напрямую по имени
    if target is None and category in ('ticket-log','ai-alerts'):
        target =category
    if target is None :
        return None
    # Автосоздание каналов — ТОЛЬКО с явного разрешения из панели
    # (заказ владельца 2026-08: «логи не создаются сами по себе»).
    try :
        from services .log_settings import autocreate_allowed ,autocreate_is_dead 
        if not autocreate_allowed (guild .id ,ch_name ):
            return None
        # «Удалил канал — значит, не нужен»: категория, чей автосозданный
        # канал владелец снёс, больше никогда не воссоздаётся (2026-08-25).
        if autocreate_is_dead (guild .id ,target ,
                lambda cid :guild .get_channel (int (cid ))is not None ):
            return None
    except Exception as _ex :
        log .debug("ensure_log_channel(): log_settings подавлено: %s", _ex)
    key =(str (guild .id ),target )
    now =time .time ()
    if now -_auto_create_state .get (key ,0 )<600 :
        return None
    _auto_create_state [key ]=now
    try :
        cat =_find_log_category (guild )
        if cat is not None and getattr (cat ,'name','')!=LOG_CATEGORY_NAME :
            try :
                await cat .edit (name =LOG_CATEGORY_NAME ,reason ='Hakumo: красивое название категории логов')
            except Exception as _rn:
                log .debug (f'[LOGS] переименование категории пропущено: {_rn}')
        if cat is None :
            overwrites ={
            guild .default_role :discord .PermissionOverwrite (read_messages =False ),
            guild .me :discord .PermissionOverwrite (
            read_messages =True ,send_messages =True ,embed_links =True ,
            attach_files =True ,read_message_history =True ),
            }
            cat =await guild .create_category (LOG_CATEGORY_NAME ,overwrites =overwrites ,
            reason ="Hakumo: автосоздание категории логов")
        else :
            _c ,_ow =ensure_log_permissions (guild ,cat )
            if _ow :
                await cat .edit (overwrites =_ow ,reason ="Hakumo: автопочинка прав на логи")
        ch =await guild .create_text_channel (target ,category =cat ,
        reason ="Hakumo: автосоздание лог-канала",
        topic =f"Логи «{target}» — события каждый день")
        try :
            from services .log_settings import autocreate_note 
            autocreate_note (guild .id ,target ,ch .id )
        except Exception as _ex :
            log .debug (f'[LOGS] запоминание автосоздания подавлено: {_ex}')
        log .info (f'[LOGS] Автосоздан канал #{target} ({getattr (guild ,"name","?")})')
        return ch
    except Exception as _e :
        log .info (f'[LOGS] Автосоздание #{target} не удалось: {_e}')
        return None


def _is_forum_ch (ch ):
    """Канал-форум? В форум пишут ПОСТАМИ (create_thread), не сообщениями."""
    try :
        if isinstance (ch ,discord .ForumChannel ):
            return True
        return getattr (getattr (ch ,'type',None ),'name','')=='forum'
    except Exception :
        return False


async def _safe_send (ch ,**kw ):
    """Отправка в лог-канал, не роняющая слушатель. Возвращает True/False.

    Частый боевой сценарий: категория « Логи» создана старым кодом без
    доступа для бота → Forbidden на каждом send → «логи не работают».
    Ошибка пишется в журнал, слушатель живёт дальше.
    """
    try :
        _e =kw .get ('embed')
        _th_name =''
        if _e is not None :
            _th_name =str (getattr (_e ,'title','')or '')
            if not _th_name :
                _m0 =getattr (_e ,'_hakumo_log_meta',None )
                _th_name =str (_m0 .get ('title',''))if _m0 else ''
        _m =getattr (_e ,'_hakumo_log_meta',None )if _e is not None else None 
        if _m and 'file'not in kw and 'files'not in kw :
            try :
                from services .log_card import render_log_card ,get_log_cards_cfg 
                import io as _io 
                import asyncio as _aio 
                # Оформление карточки настраивается в панели (Логи → оформление):
                # тема/акцент/выключение хранятся в data/log_cards_<gid>.json.
                _gid =getattr (getattr (ch ,'guild',None ),'id',0 )or 0 
                _cfg =await _aio .to_thread (get_log_cards_cfg ,_gid )
                if not _cfg .get ('enabled',True ):
                    _png =None # владелец выключил картинки — остаётся текстовый эмбед
                else :
                    # JPEG + отдельный поток: PNG-кодирование жрало ~1.2с на каждый лог
                    # и фризило весь бот. Теперь ~30-100 мс, бот не замирает.
                    _png =await _aio .to_thread (render_log_card ,_m ['cat'],_m ['title'],_m ['rows'],
                    color =_m ['color'],cat_name =_cat_meta (_m ['cat'])[2 ],
                    guild_name =_m ['guild'],theme =_cfg .get ('theme'),
                    accent =_cfg .get ('accent'),
                    time_str =datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).strftime ('%H:%M UTC'))
                if _png :
                    kw ['file']=discord .File (_io .BytesIO (_png ),filename ='hakumo_log_card.jpg')
                    _e .set_image (url ='attachment://hakumo_log_card.jpg')
                    # В лог-канале — ТОЛЬКО картинка: весь текст уже отрисован
                    # внутри карточки, дублирующий markdown-текст убираем.
                    # Если рендер карточки не удался, текстовый эмбед остаётся
                    # как запасной вариант (ничего не теряется).
                    # Оригинальный текст/футер сохраняем на самом объекте —
                    # для отладки и тестов (в Discord они не видны).
                    _e ._hakumo_log_desc =(_e .description or '')
                    _ft =_e .footer .text if _e .footer else ''
                    _e ._hakumo_log_footer =(_ft or '')
                    _e .description =None
                    _e .title =None
                    try :
                        _e .remove_footer ()
                    except Exception as _ex:
                        log.debug("_safe_send(): подавлено: %s", _ex)
            except Exception as _ex:
                log.debug("_safe_send(): подавлено: %s", _ex)
        if _is_forum_ch (ch ):
            # Форум-канал как лог: каждый лог = НОВЫЙ ПОСТ форума
            # (в сам форум сообщениями писать нельзя — только постами).
            _tk ={}
            for _k in ('content','embed','embeds','file','files','view','allowed_mentions'):
                if _k in kw :
                    _tk [_k ]=kw [_k ]
            await ch .create_thread (name =(_th_name or 'Лог')[:100],**_tk )
            return True
        await ch .send (**kw )
        return True
    except Exception as _e :
        log .info (f'[LOGS] Отправка не удалась (#{getattr (ch ,"name","?")}): {_e}')
        return False


def ensure_log_permissions (guild ,category =None ):
    """Гарантировать боту доступ к категории логов (самолечение прав).

    Возвращает (category, fixed: bool). Ничего не создаёт — только чинит
    права существующей категории. Вызывается из /setup-logs и on_ready.
    """
    try :
        if category is None :
            category =_find_log_category (guild )
        if category is None :
            return None ,False
        overwrites =dict (category .overwrites )
        me_ow =overwrites .get (guild .me )
        need =me_ow is None or not (me_ow .read_messages and me_ow .send_messages )
        if not need :
            return category ,False
        overwrites [guild .me ]=discord .PermissionOverwrite (
        read_messages =True ,send_messages =True ,embed_links =True ,
        attach_files =True ,read_message_history =True )
        return category ,overwrites
    except Exception as _e :
        log .info (f'[LOGS] ensure_log_permissions: {_e}')
        return category ,False


async def ensure_forum_log_permissions (guild ):
    """Форум-канал в роли лога: боту нужны права СОЗДАВАТЬ ПОСТЫ.

    Владелец выбрал форум в «Логах сервера» — проверяем/чиним оверрайты
    (send_messages + create_public_threads), иначе посты не создаются.
    Вызывается из /logs-setup и on_ready (самолечение).
    """
    try :
        from services .log_settings import get_log_settings
        for cid in ((get_log_settings (guild .id ).get ('channels')or {}).values ()):
            if not str (cid or '').strip ().isdigit ():
                continue
            ch =guild .get_channel (int (cid ))
            if ch is None or not _is_forum_ch (ch ):
                continue
            ow =dict (ch .overwrites )
            me_ow =ow .get (guild .me )
            if me_ow is not None and me_ow .create_public_threads and me_ow .send_messages :
                continue
            ow [guild .me ]=discord .PermissionOverwrite (
            view_channel =True ,send_messages =True ,embed_links =True ,
            attach_files =True ,create_public_threads =True ,
            read_message_history =True )
            await ch .edit (overwrites =ow ,reason ="Hakumo: права на посты в форум-логе")
            log .info (f'[LOGS] Права на форум-лог #{ch.name} выданы')
    except Exception as _e :
        log .info (f'[LOGS] ensure_forum_log_permissions: {_e}')


def _find_log_category (guild ):
    """Категория логов: новое имя «📚 Логи» или старые (' Логи' и т.п.)."""
    cat =None
    for _c in getattr (guild ,'categories',[])or []:
        if getattr (_c ,'name','')==LOG_CATEGORY_NAME :
            return _c
    for legacy in LOG_CATEGORY_LEGACY :
        cat =discord .utils .get (getattr (guild ,'categories',[])or [],name =legacy )
        if cat is not None :
            return cat
    try :
        for _c in getattr (guild ,'categories',[])or []:
            if _norm_ch_name (getattr (_c ,'name',''))in ('логи','logs'):
                return _c
    except Exception as _ex:
        log .debug (f'[LOGS] поиск категории: {_ex}')
    return None


# ═══════════════════════════════════════════════════════════════════════
#  СТИЛЬ ЛОГ-ЭМБЕДОВ — единый премиальный вид для всех категорий
# ═══════════════════════════════════════════════════════════════════════
_LOG_META = {
    'mod':     ('🛡️', 0xE74C3C, 'Модерация'),
    'member':  ('👋', 0xC8922A, 'Участники'),
    'message': ('💬', 0x3498DB, 'Сообщения'),
    'voice':   ('🔊', 0x1ABC9C, 'Войс'),
    'channel': ('🗂️', 0xE67E22, 'Каналы'),
    'role':    ('🎭', 0x9B59B6, 'Роли'),
    'invite':  ('🔗', 0x16A085, 'Приглашения'),
    'guild':   ('🏠', 0xC8922A, 'Сервер'),
    'ticket':  ('🎫', 0xF39C12, 'Тикеты'),
    'ai':      ('🤖', 0xE91E63, 'AI-алерты'),
    'welcome': ('🎉', 0x2ECC71, 'Приветствие'),
    'proof':   ('📸', 0x9B59B6, 'Доказательства'),
}


def _cat_meta(category):
    """(эмодзи, цвет, русское имя) категории логов."""
    m = _LOG_META.get(category)
    if m:
        return m
    return ('🏠', 0xC8922A, 'Сервер')


class _LogEmbed(discord.Embed):
    # Embed с метаданными карточки лога (читает _safe_send).
    pass


# Заказ владельца 2026-08-25: в логах — ИМЕНА, а не сырые ID.
_RE_MENTION = re.compile(r'<@!?(\d{15,25})>')
_RE_ROLE_MENTION = re.compile(r'<@&(\d{15,25})>')
_RE_CHANNEL_MENTION = re.compile(r'<#(\d{15,25})>')
_RE_ID_PARENS = re.compile(r'\s*\((\d{15,25})\)')
_RE_ID_TAIL = re.compile(r'\s*[·\-]?\s*`?(\d{15,25})`?\s*$')


def _card_friendly(text, guild):
    """Строка для карточки лога: имена вместо ID, без markdown-мусора.

    Упоминания резолвятся в имена через состав сервера; голые длинные
    ID (и «Имя (ID)», и «Имя · ID») убираются — остаётся человекочитаемое.
    """
    try:
        s = str(text if text is not None else '')

        def _mem(m):
            mid = int(m.group(1))
            name = None
            if guild is not None:
                mem = guild.get_member(mid)
                if mem is not None:
                    name = getattr(mem, 'display_name', None) or str(mem)
            return '@' + (name or 'участник')

        def _role(m):
            rid = int(m.group(1))
            name = None
            if guild is not None:
                role = guild.get_role(rid)
                if role is not None:
                    name = getattr(role, 'name', None)
            return '@' + (name or 'роль')

        def _chan(m):
            cid = int(m.group(1))
            name = None
            if guild is not None:
                ch = guild.get_channel(cid)
                if ch is not None:
                    name = getattr(ch, 'name', None)
            return '#' + (name or 'канал')

        s = _RE_MENTION.sub(_mem, s)
        s = _RE_ROLE_MENTION.sub(_role, s)
        s = _RE_CHANNEL_MENTION.sub(_chan, s)
        s = s.replace('**', '').replace('`', '')
        s = _RE_ID_PARENS.sub('', s)       # «Имя (123…)» -> «Имя»
        s = _RE_ID_TAIL.sub('', s)         # «Имя · 123…» -> «Имя»
        s = re.sub(r'\s·\s·\s', ' · ', s)
        s = s.strip(' ·-')
        return s or '—'
    except Exception:
        return str(text)


def _strip_raw_id(text):
    """Убрать голый ID из строки эмбеда (markdown и упоминания остаются).

    «**Имя** · @упоминание · `123456789012345678`» -> «**Имя** · @упоминание»:
    в Discord упоминание само рендерится именем, цифровой хвост не нужен.
    """
    try:
        s = str(text)
        s = _RE_ID_TAIL.sub('', s)
        s = re.sub(r'\s*[·\-]?\s*`(\d{15,25})`', '', s)
        return s.strip(' ·-') or str(text)
    except Exception:
        return text


def _styled_log_embed(guild, category, title, fields=(), color=None,
                      thumbnail=None, image=None, note=None, card_rows=None):
    """Единый стиль лог-эмбеда: заголовок с иконкой категории, строки
    «Имя — значение», футер «Hakumo Log · Категория · Сервер» с иконкой сервера.

    fields: список кортежей (имя, значение); пустые значения пропускаются.
    note: свободный текст после полей (предупреждения и т.п.).
    """
    icon, base_color, cat_name = _cat_meta(category)
    e = _LogEmbed(color=color if color is not None else base_color,
                  timestamp=datetime.datetime.now(datetime.timezone.utc))
    desc = f"## {(icon + ' ') if icon else ''}{title}\n\n"
    for name, value in fields:
        if value in (None, ''):
            continue
        # В тексте эмбеда голые ID тоже не показываем — заказ владельца:
        # имена вместо цифр (упоминание Discord само рендерится именем).
        value = _strip_raw_id(value)
        desc += f"**{name}** — {value}\n"
    if note:
        desc += f"\n{note}"
    e.description = desc
    footer_text = f"Hakumo Log · {cat_name} · {getattr(guild, 'name', '')}"
    gicon = getattr(guild, 'icon', None)
    try:
        gicon = gicon.url if gicon else None
    except Exception:
        gicon = None
    if gicon:
        e.set_footer(text=footer_text, icon_url=gicon)
    else:
        e.set_footer(text=footer_text)
    if thumbnail:
        e.set_thumbnail(url=thumbnail)
    if image:
        e.set_image(url=image)
    # Метаданные для карточки лога (рисует services/log_card.py при отправке)
    # note тоже передаём строкой на карточку — в Discord уходит только картинка,
    # текст эмбеда скрывается (_safe_send), поэтому информацию не теряем.
    _rows = [(n, v) for n, v in (card_rows if card_rows is not None else fields)
             if v not in (None, '')]
    # Карточка — картинка: markdown и сырые ID на ней не рисуем,
    # упоминания превращаем в имена (заказ: «вместо id — имя»).
    _rows = [(_card_friendly(n, guild), _card_friendly(v, guild))
             for n, v in _rows]
    if note and len(_rows) < 8:
        _rows.append(('Инфо', note))
    e._hakumo_log_meta = {
        'cat': category,
        'title': title,
        'rows': _rows[:8],
        'color': color if color is not None else base_color,
        'guild': getattr(guild, 'name', ''),
    }
    return e


_CH_TYPE_RU = {
    'text': ('💬', 'текстовый'),
    'voice': ('🔊', 'голосовой'),
    'category': ('📁', 'категория'),
    'news': ('📢', 'объявления'),
    'stage_voice': ('🎙️', 'сцена'),
    'forum': ('💭', 'форум'),
    'media': ('🖼️', 'медиа'),
    'private_thread': ('🧵', 'приватная ветка'),
    'public_thread': ('🧵', 'ветка'),
}


def _ch_type_label(ch_type):
    """Понятное имя типа канала: «💬 текстовый» (вместо ChannelType.text)."""
    name = getattr(ch_type, 'name', None) or str(ch_type or '?')
    icon, ru = _CH_TYPE_RU.get(name, ('📄', name))
    return f"{icon} {ru}"


# ═══════════════════════════════════════════════════════════════════════
#  AUDIT-ПОДПИСЬ: кто выполнил действие (модератор + причина)
# ═══════════════════════════════════════════════════════════════════════
_audit_used = {}


async def _audit_actor(guild, action, target_id=None, window=20, retries=1):
    """Найти в audit log, КТО выполнил действие над целью.

    Возвращает (имя, id, причина, is_bot) или None (нет права view_audit_log
    или запись не появилась). Каждая запись audit log используется один раз,
    чтобы вчерашний бан не «подписывался» под сегодняшний разбан.
    """
    try:
        me = getattr(guild, 'me', None)
        if me is not None:
            try:
                if not me.guild_permissions.view_audit_log:
                    return None
            except Exception as _ex:
                log.debug("_audit_actor(): подавлено: %s", _ex)
        import asyncio as _ai
        key = (str(guild.id), action, str(target_id) if target_id is not None else '0')
        used = _audit_used.setdefault(key, set())
        now = datetime.datetime.now(datetime.timezone.utc)
        for _attempt in range(max(1, retries)):
            try:
                async for entry in guild.audit_logs(limit=8, action=action):
                    if entry.id in used:
                        continue
                    if target_id is not None:
                        if getattr(entry.target, 'id', None) != target_id:
                            continue
                    try:
                        age = (now - entry.created_at).total_seconds()
                    except Exception:
                        age = 0
                    if age > window:
                        continue
                    used.add(entry.id)
                    u = entry.user
                    if u is None:
                        return ('—', 0, getattr(entry, 'reason', None), False)
                    return (getattr(u, 'display_name', None) or str(u),
                            u.id, getattr(entry, 'reason', None),
                            bool(getattr(u, 'bot', False)))
            except discord.Forbidden:
                return None
            except Exception as _ex:
                log.debug("_audit_actor(): подавлено: %s", _ex)
            await _ai.sleep(0.2)  # между попытками (почти не используется: retries=1)
    except Exception as _ex:
        log.debug("_audit_actor(): подавлено: %s", _ex)
    return None


def _actor_line(who):
    """Строка «Имя `id`» по результату _audit_actor (или тире)."""
    if not who:
        return '—'
    name, uid, _reason, _bot = who
    return f"{name} `{uid or ''}`"


# ═══════════════════════════════════════════════════════════════════════
#  ЦЕНТР ЛОГОВ (Select-меню для администратора)
# ═══════════════════════════════════════════════════════════════════════
LOG_CENTER_ITEMS = [
    ('mod',        '🛡️', 'Модерация',   'баны, кики, мьюты, таймауты, варны'),
    ('member',     '👋', 'Участники',  'вход и выход, смена псевдонима'),
    ('message',    '💬', 'Сообщения',  'удаления, правки, ghost-ping'),
    ('voice',      '🔊', 'Войс',       'входы, выходы и переходы в голосовых'),
    ('channel',    '🗂️', 'Каналы',     'создание, удаление и изменения каналов'),
    ('role',       '🎭', 'Роли',       'создание/удаление ролей, выдача ролей'),
    ('invite',     '🔗', 'Приглашения', 'создание и удаление инвайтов'),
    ('guild',      '🏠', 'Сервер',     'переименование и настройки сервера'),
    ('ticket-log', '🎫', 'Тикеты',     'открытие и закрытие обращений'),
    ('ai-alerts',  '🤖', 'AI-алерты',  'сигналы проактивной модерации'),
    ('welcome',    '🎉', 'Приветствие', 'приветствия и прощания (публичный)'),
]

# Канал, где живут логи каждой категории центра
LOG_CENTER_CHANNELS = {
    'mod': '-модерация',
    'member': '-участники',
    'message': '-сообщения',
    'voice': '-ses',
    'channel': '-сервер',
    'role': '-сервер',
    'invite': '-сервер',
    'guild': '-сервер',
    'ticket-log': 'ticket-log',
    'ai-alerts': 'ai-alerts',
    'welcome': '-приветствие',
}


def _lc_find_channel(guild, key):
    """Найти канал категории центра логов (без создания)."""
    name = LOG_CENTER_CHANNELS.get(key)
    if not name:
        return None
    want = _norm_ch_name(name)
    for c in guild.text_channels:
        if _norm_ch_name(c.name) == want:
            return c
    return discord.utils.get(guild.text_channels, name=name)


async def _lc_ensure_channel(guild, key):
    """Найти или СОЗДАТЬ канал категории (использует общее самолечение логов)."""
    if key == 'welcome':
        ch = _lc_find_channel(guild, 'welcome')
        if ch:
            return ch
        try:
            return await guild.create_text_channel(
                '-приветствие', reason='Hakumo: канал приветствий',
                topic='Приветствие и прощание участников')
        except Exception:
            return None
    cat_map = {'mod': 'mod', 'member': 'member', 'message': 'message',
               'voice': 'voice', 'channel': 'сервер', 'role': 'сервер',
               'invite': 'сервер', 'guild': 'сервер',
               'ticket-log': 'ticket-log', 'ai-alerts': 'ai-alerts'}
    return await ensure_log_channel(guild, cat_map.get(key, 'сервер'))


class LogsCenterSelect(discord.ui.Select):
    """Выпадающее меню категорий логов."""

    def __init__(self):
        options = [
            discord.SelectOption(label=title, value=key, emoji=icon,
                                 description=desc[:95])
            for key, icon, title, desc in LOG_CENTER_ITEMS
        ]
        super().__init__(placeholder='Выберите категорию логов…',
                         min_values=1, max_values=1, options=options,
                         custom_id='lc:select')

    async def callback(self, interaction):
        view = self.view
        view.selected = self.values[0]
        view.notice = ''
        await interaction.response.edit_message(embed=view.status_embed(), view=view)


class LogsCenterView(discord.ui.View):
    """Центр логов: выберите категорию в меню — статус, тест, починка."""

    def __init__(self, guild, requester_id, timeout_v=600):
        super().__init__(timeout=timeout_v)
        self.guild = guild
        self.requester_id = requester_id
        self.selected = 'mod'
        self.notice = ''
        self.add_item(LogsCenterSelect())

    async def interaction_check(self, interaction):
        try:
            if not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message(
                    '🚫 Центр логов доступен только администраторам.', ephemeral=True)
                return False
        except Exception as _ex:
            log.debug("interaction_check(): подавлено: %s", _ex)
        return True

    # ── эмбеды ─────────────────────────────────────────────────────────
    def overview_embed(self):
        e = discord.Embed(
            color=0xC8922A,
            timestamp=datetime.datetime.now(datetime.timezone.utc))
        e.description = (
            "## 📋 Центр логов\n"
            "Выберите категорию в меню ниже — покажу её канал, "
            "что туда пишется, и проверю доставку.\n")
        lines = []
        for key, icon, title, desc in LOG_CENTER_ITEMS:
            ch = _lc_find_channel(self.guild, key)
            mark = ch.mention if ch else '❌ не создан'
            lines.append(f"{icon} **{title}** — {mark}")
        e.add_field(name=f"Каналы ({len(LOG_CENTER_ITEMS)} категорий)",
                    value='\n'.join(lines)[:1024], inline=False)
        e.add_field(name="Управление",
                    value=("📨 **Тест** — отправить пробное сообщение\n"
                           "🔧 **Создать/починить** — создать канал или восстановить права бота\n"
                           "🔄 **Обновить** — перечитать статус"),
                    inline=False)
        gicon = getattr(self.guild, 'icon', None)
        gicon = gicon.url if gicon else None
        if gicon:
            e.set_footer(text=f"Hakumo Log · {self.guild.name}", icon_url=gicon)
        else:
            e.set_footer(text=f"Hakumo Log · {self.guild.name}")
        return e

    def status_embed(self):
        meta = {k: (i, t, d) for k, i, t, d in LOG_CENTER_ITEMS}
        icon, title, desc = meta.get(self.selected, ('📋', self.selected, ''))
        ch = _lc_find_channel(self.guild, self.selected)
        color = 0x2ECC71 if ch else 0xE74C3C
        e = discord.Embed(color=color, timestamp=datetime.datetime.now(datetime.timezone.utc))
        e.description = (
            f"## {icon} {title}\n\n"
            f"**Что логируется** — {desc}\n"
            f"**Канал** — {ch.mention if ch else '❌ не создан'}\n")
        if ch:
            topic = getattr(ch, 'topic', None) or '—'
            e.description += f"**Тема канала** — {topic[:80]}\n"
        if self.selected == 'welcome':
            e.description += "\n🎉 Этот канал **публичный** — его видят все участники."
        if self.notice:
            e.description += f"\n\n{self.notice}"
        e.set_footer(text=f"Hakumo Log · Центр логов · {self.guild.name}")
        return e

    def events_embed(self):
        meta = {k: (i, t, d) for k, i, t, d in LOG_CENTER_ITEMS}
        icon, title, desc = meta.get(self.selected, ('📋', self.selected, ''))
        ch = _lc_find_channel(self.guild, self.selected)
        e = discord.Embed(color=0xD4AF37, timestamp=datetime.datetime.now(datetime.timezone.utc))
        e.description = (
            f"## {icon} {title} — Недавние события\n"
            f"Канал: {ch.mention if ch else '❌ не создан'}\n\n"
        )
        try:
            with open(AUDIT_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            events = data.get(str(self.guild.id), [])
            cat_map = {'mod': ('mod', 'automod'), 'member': ('member',), 'message': ('message',),
                       'voice': ('voice',), 'channel': ('channel', 'сервер'), 'role': ('role', 'сервер'),
                       'invite': ('invite', 'сервер'), 'guild': ('guild', 'сервер'),
                       'ticket-log': ('ticket-log',), 'ai-alerts': ('ai-alerts',), 'welcome': ('member',)}
            target_cats = cat_map.get(self.selected, (self.selected,))
            matches = [ev for ev in reversed(events) if str(ev.get('category', '')).lower() in target_cats][:5]
            if matches:
                lines = []
                for ev in matches:
                    ts = str(ev.get('timestamp', ''))[:16].replace('T', ' ')
                    act = ev.get('action', 'Событие')
                    det = ev.get('user_name') or ev.get('channel') or ev.get('content') or ev.get('reason') or ''
                    lines.append(f"• `{ts}` **{act}**" + (f" — {str(det)[:60]}" if det else ''))
                e.add_field(name="Последние записи аудита", value="\n".join(lines)[:1020], inline=False)
            else:
                e.add_field(name="Последние записи аудита", value="*Записей пока нет (летопись пишется при активности).*", inline=False)
        except Exception:
            e.add_field(name="Последние записи аудита", value="*Нет сохранённых записей.*", inline=False)
        if self.notice:
            e.description += f"\n\n{self.notice}"
        e.set_footer(text=f"Hakumo Log · {self.guild.name}")
        return e

    # ── кнопки ─────────────────────────────────────────────────────────
    @discord.ui.button(label='Тест', style=discord.ButtonStyle.success,
                       emoji='📨', custom_id='lc:test')
    async def lc_test(self, interaction, button):
        ch = _lc_find_channel(self.guild, self.selected)
        if not ch:
            self.notice = '⚠️ Канал не создан — нажмите «🔧 Создать/починить».'
        else:
            cat_map = {'mod': 'mod', 'member': 'member', 'message': 'message',
                       'voice': 'voice', 'channel': 'channel', 'role': 'role',
                       'invite': 'invite', 'guild': 'guild',
                       'ticket-log': 'ticket', 'ai-alerts': 'ai', 'welcome': 'welcome'}
            te = _styled_log_embed(
                self.guild, cat_map.get(self.selected, 'guild'),
                'Тест доставки логов',
                fields=[('Проверяющий', f"{interaction.user.mention} · `{interaction.user.id}`"),
                        ('Категория', self.selected)],
                note='✅ Если вы видите это сообщение — логи в этот канал доставляются.')
            ok = await _safe_send(ch, embed=te)
            self.notice = ('✅ Тест отправлен — посмотрите в канал.'
                           if ok else
                           '⚠️ Не удалось отправить — проверьте права бота на категорию «📚 Логи».')
        try:
            await interaction.response.edit_message(embed=self.status_embed(), view=self)
        except Exception as _ex:
            log.debug("lc_test(): подавлено: %s", _ex)

    @discord.ui.button(label='События', style=discord.ButtonStyle.primary,
                       emoji='📜', custom_id='lc:events')
    async def lc_events(self, interaction, button):
        self.notice = ''
        try:
            await interaction.response.edit_message(embed=self.events_embed(), view=self)
        except Exception as _ex:
            log.debug("lc_events(): подавлено: %s", _ex)

    @discord.ui.button(label='Создать/починить', style=discord.ButtonStyle.primary,
                       emoji='🔧', custom_id='lc:fix')
    async def lc_fix(self, interaction, button):
        ch = await _lc_ensure_channel(self.guild, self.selected)
        if ch:
            self.notice = f'🔧 Готово: канал {ch.mention} существует, права проверены.'
        else:
            self.notice = ('⚠️ Не удалось создать канал. '
                           'Дайте боту права «Управление каналами» и повторите.')
        try:
            await interaction.response.edit_message(embed=self.status_embed(), view=self)
        except Exception as _ex:
            log.debug("lc_fix(): подавлено: %s", _ex)

    @discord.ui.button(label='Обзор', style=discord.ButtonStyle.secondary,
                       emoji='🏠', custom_id='lc:overview')
    async def lc_overview(self, interaction, button):
        self.notice = ''
        try:
            await interaction.response.edit_message(embed=self.overview_embed(), view=self)
        except Exception as _ex:
            log.debug("lc_overview(): подавлено: %s", _ex)

    @discord.ui.button(label='Обновить', style=discord.ButtonStyle.secondary,
                       emoji='🔄', custom_id='lc:refresh')
    async def lc_refresh(self, interaction, button):
        self.notice = ''
        try:
            await interaction.response.edit_message(embed=self.status_embed(), view=self)
        except Exception as _ex:
            log.debug("lc_refresh(): подавлено: %s", _ex)


class Logs (commands .Cog ):
    def __init__ (self ,bot ):
        self .bot =bot 
        self ._audit_sync_started =False   # защита от дубля цикла при reconnect
        self ._audit_forbidden_notified =set ()  # о чём уже предупредили однажды

    async def get_log_channel (self ,guild ,category :str ='сервер'):
        # Настройки из панели («Логи сервера»): категорию можно выключить —
        # тогда события в канал не уходят вовсе (файл читается каждый раз,
        # применение мгновенное, без рестарта).
        try :
            from services .log_settings import category_enabled 
            if not category_enabled (guild .id ,category ):
                return None 
        except Exception as _ex :
            log .debug("get_log_channel(): log_settings подавлено: %s", _ex)
        # Найти канал категории логов; отсутствующий — создать автоматически
        return await ensure_log_channel (guild ,category )

        # КОМАНДА: СОЗДАТЬ LOG-КАНАЛЫ 

    async def _setup_logs_core (self ,interaction :discord .Interaction ):
        """Общее ядро /setup-logs и /logs-setup: создать/починить всю систему логов.

        Идемпотентно: legacy-каналы (mod-log, moderasyon, server-log …)
        переименовываются в канонические, дубликаты не создаются.
        """
        guild =interaction .guild
        await interaction .response .defer (ephemeral =True )

        # 1) Категория « Логи» — видна только персоналу
        existing_cat =discord .utils .get (guild .categories ,name =LOG_CATEGORY_NAME )

        if not existing_cat :
            overwrites ={
            guild .default_role :discord .PermissionOverwrite (
            read_messages =False ,
            ),
            guild .me :discord .PermissionOverwrite (
            read_messages =True ,
            send_messages =True ,
            embed_links =True ,
            attach_files =True ,
            read_message_history =True ,
            ),
            }
            # Даём доступ модераторам (роли с правами kick/ban/admin)
            for role in guild .roles :
                if role .permissions .kick_members or role .permissions .ban_members or role .permissions .administrator :
                    overwrites [role ]=discord .PermissionOverwrite (
                    read_messages =True ,
                    send_messages =False ,
                    read_message_history =True ,
                    )

            existing_cat =await guild .create_category (
            LOG_CATEGORY_NAME ,
            overwrites =overwrites ,
            reason ="Hakumo: создание категории логов"
            )

        created =[]
        migrated =[]
        already =[]

        # 1б) Категория могла остаться от старого кода без доступа для бота —
        # тогда каждый send падает с Forbidden и «логи не работают». Чиним.
        try :
            _cat ,_ow =ensure_log_permissions (guild ,existing_cat )
            if _ow :
                await existing_cat .edit (overwrites =_ow ,reason ="Hakumo: починка прав бота на категорию логов")
                migrated .append ("права категории «📚 Логи» восстановлены")
        except Exception as _pe :
            log .info (f'[SETUP-LOGS] починка прав: {_pe}')
        try :
            await ensure_forum_log_permissions (guild )
        except Exception as _fe :
            log .info (f'[SETUP-LOGS] форум-лог: {_fe}')

        # 2) Канонические каналы + миграция legacy-имён (mod-log → -модерация и т.д.)
        canonical =list (dict .fromkeys (LOG_CHANNELS .values ()))
        for ch_name in canonical :
            ch =discord .utils .get (guild .text_channels ,name =ch_name )
            if ch is None :
                legacy_ch =None
                legacy_name =None
                for legacy in LEGACY_CHANNEL_NAMES .get (ch_name ,[]):
                    legacy_ch =discord .utils .get (guild .text_channels ,name =legacy )
                    if legacy_ch :
                        legacy_name =legacy
                        break
                if legacy_ch :
                    await legacy_ch .edit (name =ch_name ,category =existing_cat ,reason ="Hakumo: миграция лог-канала")
                    migrated .append (f"#{legacy_name} → #{ch_name}")
                    continue
                await guild .create_text_channel (
                ch_name ,
                category =existing_cat ,
                reason ="Hakumo: создание канала логов",
                topic =f"Логи «{ch_name}» — события каждый день"
                )
                created .append (ch_name )
            else :
                if ch .category !=existing_cat :
                    await ch .edit (category =existing_cat )
                already .append (ch_name )

        # 3) Сервисные каналы других модулей (тикеты и AI-алерты тоже пишут логи)
        extra_channels ={
        'ticket-log':'Логи тикетов — открытие и закрытие обращений',
        'ai-alerts':'AI-алерты проактивной модерации',
        }
        for extra ,topic in extra_channels .items ():
            ch =discord .utils .get (guild .text_channels ,name =extra )
            if ch :
                if ch .category !=existing_cat :
                    await ch .edit (category =existing_cat )
                already .append (extra )
            else :
                await guild .create_text_channel (extra ,category =existing_cat ,reason ="Hakumo: сервисный канал логов",topic =topic )
                created .append (extra )

        # 4) Публичный канал приветствий — НЕ в скрытой категории (его видят все)
        welcome_ch =discord .utils .get (guild .text_channels ,name ="-приветствие")
        if not welcome_ch :
            welcome_ch =await guild .create_text_channel (
            "-приветствие",
            reason ="Hakumo: канал приветствий",
            topic ="Приветствие и прощание участников"
            )
            created .append ("-приветствие (публичный)")
        else :
            # Старый баг: канал приветствий был спрятан в закрытой категории логов
            if welcome_ch .category ==existing_cat :
                await welcome_ch .edit (category =None ,reason ="Hakumo: канал приветствий должен быть публичным")
                await welcome_ch .set_permissions (guild .default_role ,read_messages =True ,send_messages =False ,reason ="Hakumo: публичный канал приветствий")
                migrated .append ("-приветствие → вынесен из скрытой категории")
            already .append ("-приветствие")

        # 4б) Авто-настройка welcome-конфига, если каналы ещё не заданы
        try :
            wcfg_path =f'data/welcome_{guild.id}.json'
            wcfg ={}
            if os .path .exists (wcfg_path ):
                with open (wcfg_path ,'r',encoding ='utf-8')as f :
                    wcfg =json .load (f )
            changed =False
            w_cfg =wcfg .setdefault ('welcome',{})
            if not w_cfg .get ('channel_id'):
                w_cfg ['channel_id']=str (welcome_ch .id )
                changed =True
            l_cfg =wcfg .setdefault ('leave',{})
            if not l_cfg .get ('channel_id'):
                l_cfg ['channel_id']=str (welcome_ch .id )
                changed =True
            if changed :
                os .makedirs ('data',exist_ok =True )
                with open (wcfg_path ,'w',encoding ='utf-8')as f :
                    json .dump (wcfg ,f ,ensure_ascii =False ,indent =2 )
        except Exception as _wc_err :
            log .info (f'[SETUP-LOGS] welcome-config: {_wc_err}')

        # 4в) Проверка доставки — шлём тестовый embed в каждый лог-канал
        delivery_ok =[]
        delivery_fail =[]
        for ch_name in canonical +list (extra_channels .keys ()):
            ch =discord .utils .get (guild .text_channels ,name =ch_name )
            if not ch :
                continue
            te =discord .Embed (
            description =f"✅ Тест: логи в этот канал работают · #{ch_name}",
            color =0xC8922A )
            if await _safe_send (ch ,embed =te ):
                delivery_ok .append (ch_name )
            else :
                delivery_fail .append (ch_name )

        # 5) Отчёт
        result_lines =[]
        if created :
            result_lines .append (f" **Создано ({len(created)}):**\n"+"\n".join (f"• `{c}`"for c in created ))
        if migrated :
            result_lines .append (f" **Перенесено и переименовано ({len(migrated)}):**\n"+"\n".join (f"• `{m}`"for m in migrated ))
        if already :
            result_lines .append (f" **Уже было ({len(already)}):**\n"+"\n".join (f"• `{a}`"for a in dict .fromkeys (already )))

        e =discord .Embed (
        title ="✅ Система логов настроена",
        description ="\n\n".join (result_lines ),
        color =0x2ECC71 ,
        timestamp =datetime.datetime.now(datetime.timezone.utc)
        )
        e .add_field (
        name =" Каналы",
        value =(
        "🛡 **-модерация** — баны, кики, мьюты, предупреждения\n"
        " **-участники** — вход, выход, смена ника\n"
        " **-сообщения** — удаление, редактирование\n"
        " **-ses** — вход/выход из войса\n"
        " **-сервер** — каналы, роли, инвайты, сервер\n"
        " **ticket-log** — тикеты ·  **ai-alerts** — AI алерты\n"
        " **-приветствие** — приветствия и прощания (публичный)"
        ),
        inline =False
        )
        e .add_field (
        name =" Куда пишут все модули",
        value ="Мод-панель, варны, тикеты и AI-модерация автоматически находят эти каналы — ничего больше настраивать не нужно.",
        inline =False
        )
        if delivery_ok :
            _dv ="Тестовые сообщения отправлены в: "+" ".join (f"`{c}`"for c in delivery_ok )
            if delivery_fail :
                _dv +="\n\n⚠️ **Не удалось отправить в:** "+" ".join (f"`{c}`"for c in delivery_fail )
                _dv +="\nПроверьте права бота (Administrator или доступ к категории «📚 Логи»)."
            e .add_field (
            name =f" Проверка доставки: {len(delivery_ok)}/{len(delivery_ok)+len(delivery_fail)}",
            value =_dv ,
            inline =False
            )
        e .set_footer (text =f"Hakumo • {guild.name}",icon_url =guild .icon .url if guild .icon else None )
        await interaction .followup .send (embed =e ,ephemeral =True )


    @app_commands .command (name ="logs-setup",description ="Создать/починить категорию и каналы для логов")
    @app_commands .checks .has_permissions (administrator =True )
    async def logs_setup (self ,interaction :discord .Interaction ):
        await self ._setup_logs_core (interaction )

        # УЧАСТНИКИ 

    @commands .Cog .listener ()
    async def on_member_join (self ,member ):
        age_days =(datetime.datetime.now(datetime.timezone.utc)-member .created_at ).days 
        save_event (member .guild .id ,'member','Участник вошёл',{
        'user_id':str (member .id ),
        'user_name':str (member ),
        'avatar':str (member .display_avatar .url ),
        'account_age_days':age_days ,
        })

        # Приветствие сообщение
        try :
            wcfg_path =f'data/welcome_{member.guild.id}.json'
            if os .path .exists (wcfg_path ):
                with open (wcfg_path ,'r',encoding ='utf-8')as f :
                    wcfg =json .load (f )
                w =wcfg .get ('welcome',{})
                if w .get ('channel_id'):
                    wch =member .guild .get_channel (int (w ['channel_id']))
                    if wch :
                        title =(w .get ('title')or 'Добро пожаловать, {user}!').replace ('{user}',member .display_name ).replace ('{сервер}',member .guild .name ).replace ('{count}',str (member .guild .member_count )).replace ('{mention}',member .mention )
                        msg =(w .get ('message')or '{mention} добро пожаловать на сервер!').replace ('{user}',member .display_name ).replace ('{сервер}',member .guild .name ).replace ('{count}',str (member .guild .member_count )).replace ('{mention}',member .mention )
                        color =int (w .get ('color','#c8922a').lstrip ('#'),16 )
                        e =discord .Embed (title =title ,description =msg ,color =color )
                        e .set_thumbnail (url =member .display_avatar .url )
                        await wch .send (embed =e )
        except Exception as _e :
            log .info (f'[WELCOME] Ошибка: {_e}')

        ch =await self .get_log_channel (member .guild ,'member')
        if not ch :
            return 

            # Формат возраста аккаунта
        if age_days <7 :
            age_text =f"🆕 новый аккаунт ({age_days} дн.)"
        elif age_days <30 :
            age_text =f"{age_days} дн."
        elif age_days <365 :
            months =age_days //30 
            age_text =f"{months} мес."
        else :
            years =age_days //365 
            months =(age_days %365 )//30 
            age_text =f"{years} г. {months} мес."

        member_count = member.guild.member_count 
        join_ts = int(datetime.datetime.now(datetime.timezone.utc).timestamp())

        fields = [
            ('Пользователь', f"**{member.display_name}** · {member.mention} · `{member.id}`"),
            ('Аккаунт создан', age_text),
            ('Участник на сервере', f"#{member_count}"),
            ('Присоединился', f"<t:{join_ts}:R>"),
        ]
        card_rows = [
            ('Участник', f"{member.display_name} ({member.id})"),
            ('Аккаунт', age_text),
            ('Всего участников', str(member_count)),
        ]
        e = _styled_log_embed(member.guild, 'member', 'Новый участник на сервере',
                              fields=fields, card_rows=card_rows,
                              color=0x2ECC71, thumbnail=str(member.display_avatar.url))

        await _safe_send(ch, embed=e)

    @commands .Cog .listener ()
    async def on_member_remove (self ,member ):
        save_event (member .guild .id ,'member','Участник вышел',{
        'user_id':str (member .id ),
        'user_name':str (member ),
        'avatar':str (member .display_avatar .url ),
        'role':[r .name for r in member .roles [1 :]],
        })

        # Прощальное сообщение
        try :
            wcfg_path =f'data/welcome_{member.guild.id}.json'
            if os .path .exists (wcfg_path ):
                with open (wcfg_path ,'r',encoding ='utf-8')as f :
                    wcfg =json .load (f )
                lv =wcfg .get ('leave',{})
                if lv .get ('channel_id'):
                    lch =member .guild .get_channel (int (lv ['channel_id']))
                    if lch :
                        title =(lv .get ('title')or 'До свидания, {user}!').replace ('{user}',member .display_name ).replace ('{сервер}',member .guild .name ).replace ('{count}',str (member .guild .member_count )).replace ('{mention}',member .mention )
                        msg =(lv .get ('message')or '{user} покинул сервер.').replace ('{user}',member .display_name ).replace ('{сервер}',member .guild .name ).replace ('{count}',str (member .guild .member_count )).replace ('{mention}',member .mention )
                        color =int (lv .get ('color','#e05555').lstrip ('#'),16 )
                        e =discord .Embed (title =title ,description =msg ,color =color )
                        e .set_thumbnail (url =member .display_avatar .url )
                        await lch .send (embed =e )
        except Exception as _e :
            log .info (f'[LEAVE] Ошибка: {_e}')

        ch =await self .get_log_channel (member .guild ,'member')
        if not ch :
            return 

        roles_str =", ".join (r .name for r in member .roles [1 :])if member .roles [1 :]else "нет"
        member_count =member .guild .member_count 
        # Считаем, сколько участник был на сервере
        joined_ago =""
        if member .joined_at :
            days_on_server =(datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)-member .joined_at .replace (tzinfo =None )).days 
            if days_on_server ==0 :
                joined_ago ="менее дня"
            elif days_on_server ==1 :
                joined_ago ="1 день"
            elif days_on_server <30 :
                joined_ago =f"{days_on_server} дн."
            elif days_on_server <365 :
                joined_ago =f"{days_on_server // 30} мес."
            else :
                joined_ago =f"{days_on_server // 365} г. {days_on_server % 365 // 30} мес."

        fields = [
            ('Пользователь', f"**{member.display_name}** · `{member.id}`"),
            ('Был на сервере', joined_ago or "менее дня"),
            ('Роли', roles_str[:200]),
            ('Осталось участников', str(member_count)),
        ]
        card_rows = [
            ('Участник', f"{member.display_name} ({member.id})"),
            ('Был на сервере', joined_ago or "менее дня"),
            ('Роли', roles_str[:90]),
        ]
        e = _styled_log_embed(member.guild, 'member', 'Участник покинул сервер',
                              fields=fields, card_rows=card_rows,
                              color=0xE74C3C, thumbnail=str(member.display_avatar.url))

        await _safe_send(ch, embed=e)

        # КИК: выход мог быть киком — проверяем audit log и логируем в -модерация
        try :
            kwho =await _audit_actor (member .guild ,discord .AuditLogAction .kick ,target_id =member .id ,window =12 ,retries =1 )
            if kwho :
                kreason =(kwho [2 ]or '—')
                save_event (member .guild .id ,'mod','Кик',{
                'user_id':str (member .id ),
                'user_name':str (member ),
                'mod_name':_actor_line (kwho ),
                'reason':kreason ,
                })
                kch =await self .get_log_channel (member .guild ,'модерация')
                if kch :
                    ke =_styled_log_embed (member .guild ,'mod','Участник кикнут',
                    fields =[
                    ('Пользователь',f"**{member.display_name}** · {member.mention} · `{member.id}`"),
                    ('Модератор',_actor_line (kwho )),
                    ('Причина',kreason ),
                    ],
                    color =0xE67E22 ,thumbnail =str (member .display_avatar .url ))
                    await _safe_send (kch ,embed =ke )
        except Exception as _kick_err :
            log .info (f'[LOGS] kick-detect: {_kick_err}')

    @commands .Cog .listener ()
    async def on_member_ban (self ,guild ,user ):
        # Кто забанил и почему — из журнала аудита
        who =await _audit_actor (guild ,discord .AuditLogAction .ban ,target_id =user .id ,window =25 ,retries =1 )
        reason =(who [2 ]if who else None )or '—'
        save_event (guild .id ,'mod','Бан',{
        'user_id':str (user .id ),
        'user_name':str (user ),
        'avatar':str (user .display_avatar .url ),
        'mod_name':_actor_line (who ),
        'reason':reason ,
        })
        ch =await self .get_log_channel (guild ,'модерация')
        if not ch :
            return
        try :
            av =str (user .display_avatar .url )
        except Exception :
            av =None
        e =_styled_log_embed (guild ,'mod','Пользователь заблокирован',
        fields =[
        ('Пользователь',f"**{getattr(user,'display_name',str(user))}** · {user.mention} · `{user.id}`"),
        ('Модератор',_actor_line (who )),
        ('Причина',reason ),
        ],
        color =0xC0392B ,thumbnail =av )
        await _safe_send (ch ,embed =e )

    @commands .Cog .listener ()
    async def on_member_unban (self ,guild ,user ):
        who =await _audit_actor (guild ,discord .AuditLogAction .unban ,target_id =user .id ,window =25 ,retries =1 )
        save_event (guild .id ,'mod','Бан снят',{
        'user_id':str (user .id ),
        'user_name':str (user ),
        'mod_name':_actor_line (who ),
        })
        ch =await self .get_log_channel (guild ,'модерация')
        if not ch :
            return
        try :
            av =str (user .display_avatar .url )
        except Exception :
            av =None
        e =_styled_log_embed (guild ,'mod','Блокировка снята',
        fields =[
        ('Пользователь',f"**{getattr(user,'display_name',str(user))}** · {user.mention} · `{user.id}`"),
        ('Модератор',_actor_line (who )),
        ],
        color =0x2ECC71 ,thumbnail =av )
        await _safe_send (ch ,embed =e )

    @commands .Cog .listener ()
    async def on_member_update (self ,before ,after ):
    # Смена ролей
        if before .roles !=after .roles :
            added =[r for r in after .roles if r not in before .roles ]
            removed =[r for r in before .roles if r not in after .roles ]
            if added or removed :
                who =await _audit_actor (before .guild ,discord .AuditLogAction .member_role_update ,target_id =before .id ,window =20 ,retries =1 )
                save_event (before .guild .id ,'role','Изменение ролей',{
                'user_id':str (before .id ),
                'user_name':str (before ),
                'added_roles':[r .name for r in added ],
                'removed_roles':[r .name for r in removed ],
                'mod_name':_actor_line (who ),
                })
                # Пачкуем вывод: массовая раздача ролей уходит ОДНОЙ сводной
                # карточкой, а не десятком одинаковых (канал не «портится»).
                _item ={
                'user_name':str (before .display_name ),
                'added':[r .name for r in added ],
                'removed':[r .name for r in removed ],
                'mod':_actor_line (who ),
                }
                async def _flush_roles (items ,_g =before .guild ):
                    _ch =await self .get_log_channel (_g ,'role')
                    if not _ch :
                        return
                    _rows =[]
                    _cap =7
                    for _it in items [:_cap ]:
                        _bits =[]
                        if _it .get ('added'):
                            _bits .append ("Добавлена роль: "+", ".join (_it ['added']))
                        if _it .get ('removed'):
                            _bits .append ("Убрана роль: "+", ".join (_it ['removed']))
                        _txt =" · ".join (_bits )or '—'
                        if _it .get ('mod'):
                            _txt +=f"  ({_it ['mod']})"
                        _rows .append ((_it ['user_name'],_txt ))
                    if len (items )>_cap :
                        _rows .append (('Итого',f'{len (items )} участников · выше {_cap} последних'))
                    _title ='Изменение ролей участника'if len (items )==1 else f'Изменение ролей · {len (items )} участников'
                    _e =_styled_log_embed (_g ,'role',_title ,
                    fields =_rows ,card_rows =_rows )
                    await _safe_send (_ch ,embed =_e )
                try :
                    from services .log_throttle import member_updates as _mu
                    _mu .feed ((before .guild .id ,'roles'),_item ,_flush_roles )
                except Exception as _te :
                    log .debug (f'[LOGS] throttle roles: {_te}')

                    # Mute
        before_to =getattr (before ,'timed_out_until',None )
        after_to =getattr (after ,'timed_out_until',None )
        if before_to !=after_to :
            if after_to :
                save_event (before .guild .id ,'mod','Мут',{
                'user_id':str (after .id ),
                'user_name':after .display_name ,
                'action':'timeout',
                'reason':'С Discord',
                'until':after_to .isoformat ()if after_to else '',
                })
                # Сохран в mod_data.json
                try :
                    os .makedirs ('data',exist_ok =True )
                    _f ='data/mod_data.json'
                    _d ={'cases':{}}
                    if os .path .exists (_f ):
                        with open (_f ,'r',encoding ='utf-8')as fp :
                            _loaded =json .load (fp )
                        if isinstance (_loaded ,dict ):
                            _d =_loaded
                    _d .setdefault ('cases',{})
                    _gid =str (before .guild .id )
                    _d ['cases'].setdefault (_gid ,[])
                    _d ['cases'][_gid ].append ({
                    'id':len (_d ['cases'][_gid ])+1 ,
                    'action':'timeout',
                    'user_id':str (after .id ),
                    'mod_id':'system',
                    'reason':'С Discord',
                    'timestamp':datetime .datetime .now (datetime .timezone .utc ).isoformat ()
                    })
                    with open (_f ,'w',encoding ='utf-8')as fp :
                        json .dump (_d ,fp ,indent =2 ,ensure_ascii =False )
                except Exception as _e :
                    log .info (f'[LOGS] Ошибка запись mute: {_e}')
                # Эмбед мута в -модерация: кто, причина, до какого времени
                try :
                    _to_mod =await _audit_actor (before .guild ,discord .AuditLogAction .member_update ,target_id =after .id ,window =15 ,retries =1 )
                    _to_reason =(_to_mod [2 ]if _to_mod else None )or '—'
                    _tch =await self .get_log_channel (before .guild ,'модерация')
                    if _tch :
                        _until_ts =int (after_to .timestamp ())if after_to else None
                        _te =_styled_log_embed (before .guild ,'mod','Участник замьючен (таймаут)',
                        fields =[
                        ('Пользователь',f"**{after.display_name}** · {after.mention} · `{after.id}`"),
                        ('Модератор',_actor_line (_to_mod )),
                        ('Причина',_to_reason ),
                        ('Действует до',f"<t:{_until_ts}:f> · <t:{_until_ts}:R>"if _until_ts else '—'),
                        ],
                        color =0xE67E22 ,thumbnail =str (after .display_avatar .url ))
                        await _safe_send (_tch ,embed =_te )
                except Exception as _to_err :
                    log .info (f'[LOGS] timeout-embed: {_to_err}')
            else :
                save_event (before .guild .id ,'mod','Мут снят',{
                'user_id':str (after .id ),
                'user_name':after .display_name ,
                'action':'untimeout',
                })
                try :
                    _uto_mod =await _audit_actor (before .guild ,discord .AuditLogAction .member_update ,target_id =after .id ,window =15 ,retries =1 )
                    _utch =await self .get_log_channel (before .guild ,'модерация')
                    if _utch :
                        _ue =_styled_log_embed (before .guild ,'mod','Таймаут снят',
                        fields =[
                        ('Пользователь',f"**{after.display_name}** · {after.mention} · `{after.id}`"),
                        ('Модератор',_actor_line (_uto_mod )),
                        ],
                        color =0x2ECC71 ,thumbnail =str (after .display_avatar .url ))
                        await _safe_send (_utch ,embed =_ue )
                except Exception as _uto_err :
                    log .info (f'[LOGS] untimeout-embed: {_uto_err}')

                # Смена ника
        if before .nick !=after .nick :
            save_event (before .guild .id ,'member','Псевдоним изменён',{
            'user_id':str (before .id ),
            'user_name':str (before ),
            'old_nick':before .nick or before .name ,
            'new_nick':after .nick or after .name ,
            })
            # Ники тоже пачкуем за 12с — «переименовал всех» не завалит канал
            _item ={
            'user_name':str (before .display_name ),
            'old_nick':before .nick or before .name ,
            'new_nick':after .nick or after .name ,
            }
            async def _flush_nicks (items ,_g =before .guild ):
                _ch =await self .get_log_channel (_g ,'member')
                if not _ch :
                    return
                _rows =[]
                _cap =7
                for _it in items [:_cap ]:
                    _rows .append ((_it ['user_name'],f"`{_it ['old_nick']}` → `{_it ['new_nick']}`"))
                if len (items )>_cap :
                    _rows .append (('Итого',f'{len (items )} смен ника · выше {_cap} последних'))
                _title ='Псевдоним изменён'if len (items )==1 else f'Псевдонимы · {len (items )} смен'
                _e =_styled_log_embed (_g ,'member',_title ,
                fields =_rows ,card_rows =_rows ,color =0x3498DB )
                await _safe_send (_ch ,embed =_e )
            try :
                from services .log_throttle import member_updates as _mu
                _mu .feed ((before .guild .id ,'nick'),_item ,_flush_nicks )
            except Exception as _te :
                log .debug (f'[LOGS] throttle nick: {_te}')

                # СООБЩЕНИЯ 

    @commands .Cog .listener ()
    async def on_message (self ,message ):
        if message .author .bot or not message .guild :
            return 
        msg_data ={
        'content':message .content or '',
        'author_id':message .author .id ,
        'author_name':message .author .display_name ,
        'channel_id':message .channel .id ,
        'channel_name':message .channel .name ,
        'guild_id':message .guild .id ,
        'timestamp':message .created_at .isoformat (),
        }
        _msg_cache [message .id ]=msg_data 
        if len (_msg_cache )>5000 :
            oldest =list (_msg_cache .keys ())[:2500 ]
            for k in oldest :
                del _msg_cache [k ]
                # Также сохранить в data/message_log_<guild_id>.json (для AI поиска)
        self ._save_message_log (message .guild .id ,msg_data )

    def _save_message_log (self ,guild_id :int ,msg_data :dict ):
        """Сохранить сообщение в per-guild JSON-log (для AI-поиска)."""
        import json as _json 
        try :
            f =f'data/message_log_{guild_id}.json'
            logs =[]
            if os .path .exists (f ):
                try :
                    with open (f ,'r',encoding ='utf-8')as fp :
                        logs =_json .load (fp )or []
                except (OSError ,_json .JSONDecodeError ,ValueError ):
                    logs =[]
            logs .append ({
            'message_id':msg_data .get ('message_id',''),
            'author_id':str (msg_data ['author_id']),
            'author_name':msg_data ['author_name'],
            'channel_id':str (msg_data ['channel_id']),
            'channel_name':msg_data ['channel_name'],
            'content':msg_data ['content'][:500 ],
            'timestamp':msg_data ['timestamp'],
            })
            # Макс 5000 сообщений (FIFO) — защита от переполнения
            if len (logs )>5000 :
                logs =logs [-5000 :]
            os .makedirs ('data',exist_ok =True )
            with open (f ,'w',encoding ='utf-8')as fp :
                _json .dump (logs ,fp ,ensure_ascii =False )
        except Exception as e :
            log .info (f'[LOG] save_message_log error: {e}')

    @commands .Cog .listener ()
    async def on_message_delete (self ,message ):
        if not message .guild :
            return 
        author =message .author
        if author is not None and author .bot :
            return 
        cached =_msg_cache .pop (message .id ,None )
        # Сообщение не из кэша (отправлено до перезапуска бота) — автора может
        # не быть, но лог всё равно пишем с тем, что есть
        author_name =getattr (author ,'display_name',None )or (cached .get ('author_name')if cached else None )or 'Неизвестный'
        author_id =author .id if author else (cached .get ('author_id')if cached else 0 )
        content =message .content or (cached ['content']if cached else '')or '[Содержимое не найдено]'
        save_event (message .guild .id ,'message','Сообщение удалено',{
        'user_id':str (author_id ),
        'user_name':author_name ,
        'channel':message .channel .name ,
        'channel_id':str (message .channel .id ),
        'content':content [:500 ],
        })
        ch =await self .get_log_channel (message .guild ,'message')
        if not ch :
            return 
        _atts =getattr (message ,'attachments',None )or []
        _fields =[
        ('Автор',f"**{author_name}** · `{author_id}`"),
        ('Канал',message .channel .mention ),
        ('Текст',f"> {content[:450] or '[Вложение]'}"),
        ]
        try :
            _fields .append (('Отправлено',f"<t:{int(message.created_at.timestamp())}:R>"))
        except Exception as _ex:
            log.debug("on_message_delete(): подавлено: %s", _ex)
        if _atts :
            _fields .append (('Вложений удалено',f"**{len(_atts)}**"))
        _th =None
        try :
            _th =str (message .author .display_avatar .url )if message .author else None
        except Exception as _ex:
            log.debug("on_message_delete(): подавлено: %s", _ex)
        e =_styled_log_embed (message .guild ,'message','Сообщение удалено',
        fields =_fields ,color =0xE74C3C ,thumbnail =_th )
        try :
            await _safe_send (ch ,embed =e )
        except Exception as _se :
            log .info (f'[LOGS] Не удалось отправить лог удаления: {_se}')

        # 👻 GHOST PING: тегнули и сразу удалили — отдельный алерт модераторам
        _mentioned =[m for m in message .mentions if not m .bot ]+list (message .role_mentions or [])
        if _mentioned :
            _targets =", ".join (m .mention for m in _mentioned [:8 ])
            ge =_styled_log_embed (message .guild ,'message','👻 Ghost Ping',
            fields =[
            ('Виновник',f"**{author_name}** · `{author_id}`"),
            ('Что сделал','тегнул и сразу удалил сообщение'),
            ('Упомянуты',_targets ),
            ('Канал',message .channel .mention ),
            ('Текст',f"> {content[:300] or '[Вложение]'}"),
            ],
            color =0x9B59B6 ,thumbnail =_th )
            await _safe_send (ch ,embed =ge )
            save_event (message .guild .id ,'message','Ghost Ping',{
            'author_id':str (author_id ),
            'author':author_name ,
            'channel_id':message .channel .id ,
            'channel':getattr (message .channel ,'name','?'),
            'targets':[getattr (m ,'id',0)for m in _mentioned [:8 ]],
            })

    @commands .Cog .listener ()
    async def on_message_edit (self ,before ,after ):
        if not before .guild or before .content ==after .content :
            return 
        _eauthor =before .author
        if _eauthor is not None and _eauthor .bot :
            return 
        _ename =getattr (_eauthor ,'display_name',None )or 'Неизвестный'
        _eid =_eauthor .id if _eauthor else 0
        save_event (before .guild .id ,'message','Сообщение изменено',{
        'user_id':str (_eid ),
        'user_name':_ename ,
        'channel':before .channel .name ,
        'channel_id':str (before .channel .id ),
        'before':before .content [:300 ],
        'after':after .content [:300 ],
        })
        ch =await self .get_log_channel (before .guild ,'message')
        if not ch :
            return 
        _eth =None
        try :
            _eth =str (_eauthor .display_avatar .url )if _eauthor else None
        except Exception as _ex:
            log.debug("on_message_edit(): подавлено: %s", _ex)
        e =_styled_log_embed (before .guild ,'message','Сообщение изменено',
        fields =[
        ('Автор',f"**{_ename}** · `{_eid}`"),
        ('Канал',f"{before.channel.mention} · [Перейти к сообщению]({after.jump_url})"),
        ('Было',f"> {before.content[:400] or '[Пусто]'}"),
        ('Стало',f"> {after.content[:400] or '[Пусто]'}"),
        ],
        color =0x3498DB ,thumbnail =_eth )
        await _safe_send (ch ,embed =e )

        # SES КАНАЛЫ 

    @commands .Cog .listener ()
    async def on_voice_state_update (self ,member ,before ,after ):
        if before .channel ==after .channel :
            return 
        b ,a =before .channel ,after .channel
        if b is None and a is not None :
            # Зашёл в голосовой канал
            action ='Зашёл в голосовой'
            color =0x1ABC9C
            detail ={'channel':a .name }
            line =f"Канал: **{a.name}**"
        elif b is not None and a is None :
            # Вышел из голосового
            action ='Вышел из голосового'
            color =0x95A5A6
            detail ={'channel':b .name }
            line =f"Канал: **{b.name}**"
        else :
            # Переключился на другой канал
            action ='Переключился в другой канал'
            color =0x3498DB
            detail ={'channel':f'{b.name} → {a.name}','from':b .name ,'to':a .name }
            line =f"**{b.name}** ➜ **{a.name}**"

        save_event (member .guild .id ,'voice',action ,{
        'user_id':str (member .id ),
        'user_name':str (member ),
        **detail
        })
        ch =await self .get_log_channel (member .guild ,'voice')
        if not ch :
            return
        _vfields =[
        ('Участник',f"**{member.display_name}** · `{member.id}`"),
        ('Канал',line .replace ('**','')if False else line ),
        ]
        try :
            _in =a if a is not None else b
            if _in is not None :
                _vfields .append (('В канале сейчас',f"**{len(_in.members)}** чел."))
        except Exception as _ex:
            log.debug("on_voice_state_update(): подавлено: %s", _ex)
        _vth =None
        try :
            _vth =str (member .display_avatar .url )
        except Exception as _ex:
            log.debug("on_voice_state_update(): подавлено: %s", _ex)
        e =_styled_log_embed (member .guild ,'voice',action ,
        fields =_vfields ,color =color ,thumbnail =_vth )
        await _safe_send (ch ,embed =e )

        # КАНАЛЫ 

    @commands .Cog .listener ()
    async def on_guild_channel_create (self ,channel ):
        save_event (channel .guild .id ,'channel','Канал создан',{
        'channel_id':str (channel .id ),
        'channel_name':channel .name ,
        'channel_type':str (channel .type ),
        })
        ch =await self .get_log_channel (channel .guild ,'channel')
        if not ch :
            return 
        e =_styled_log_embed (channel .guild ,'channel','Канал создан',
        fields =[
        ('Канал',f"{getattr(channel,'mention','#'+channel.name)} · `{channel.id}`"),
        ('Тип',_ch_type_label (getattr (channel ,'type','?'))),
        ('Категория',getattr (getattr (channel ,'category',None ),'name',None )or '—'),
        ],
        color =0x2ECC71 )
        await _safe_send (ch ,embed =e )

    @commands .Cog .listener ()
    async def on_guild_channel_delete (self ,channel ):
        # Кто удалил канал (из audit log) — с retry, т.к. audit log появляется с задержкой.
        mod_name =None 
        mod_id =None 
        mod_is_bot =False 
        try :
            import asyncio as _ai 
            guild =channel .guild 
            # Проверяем право на чтение audit log — без него мы не сможем узнать, кто удалил.
            can_view =False 
            try :
                me =guild .me 
                can_view =bool (me .guild_permissions .view_audit_log )
            except Exception as _ex:
                log.debug("on_guild_channel_delete(): подавлено: %s", _ex)
            if not can_view :
                save_event (guild .id ,'channel','Канал удалён',{
                'channel_id':str (channel .id ),
                'channel_name':getattr (channel ,'name','?'),
                'channel_type':str (getattr (channel ,'type','?')),
                'mod_name':'?',
                'mod_id':None ,
                'warning':'Нет права View Audit Log — не удалось определить, кто удалил канал',
                })
                ch =await self .get_log_channel (guild ,'channel')
                if ch :
                    e =discord .Embed (color =0xE74C3C ,timestamp =datetime.datetime.now(datetime.timezone.utc))
                    e .description =(
                    "## Канал удален\n"
                    f"**{getattr(channel, 'name', '?')}** · `{channel.id}`\n\n"
                    "⚠️ **Боту не выдано право `Просмотр журнала аудита` (View Audit Log).**\n"
                    "Невозможно определить, кто удалил канал.\n\n"
                    "Дайте боту это право в настройках сервера."
                    )
                    e .set_footer (text =f"{guild.name}")
                    await _safe_send (ch ,embed =e )
                return
            # Retry-цикл: audit log может прийти с задержкой
            for attempt in range (1 ):
                try :
                    async for entry in guild .audit_logs (limit =10 ,action =discord .AuditLogAction .channel_delete ):
                        tid =getattr (entry .target ,'id',None )
                        if tid is not None and tid ==channel .id :
                            u =entry .user 
                            if u is not None :
                                mod_name =getattr (u ,'display_name',None )or str (u )
                                mod_id =u .id 
                                mod_is_bot =bool (getattr (u ,'bot',False ))
                            break 
                except discord .Forbidden :
                    break 
                except Exception as _ex:
                    log.debug("on_guild_channel_delete(): подавлено: %s", _ex)
                if mod_id is not None :
                    break 
                pass  # без ожидания: лог уходит сразу
        except Exception as _ex:
            log.debug("on_guild_channel_delete(): подавлено: %s", _ex)

        extra_warning =''
        if mod_id is not None and mod_is_bot :
            extra_warning =(' ⚠️ **ВНИМАНИЕ:** канал удалён через аккаунт бота! '
                           'Это означает утечку/компрометацию токена бота или использование '
                           'его вебхука/интеграции. Проверьте безопасность токена!')

        save_event (channel .guild .id ,'channel','Канал удалён',{
        'channel_id':str (channel .id ),
        'channel_name':getattr (channel ,'name','?'),
        'channel_type':str (getattr (channel ,'type','?')),
        'mod_name':mod_name or '—',
        'mod_id':str (mod_id )if mod_id else None ,
        'mod_is_bot':mod_is_bot ,
        'source':'event',
        })
        ch =await self .get_log_channel (channel .guild ,'channel')
        if not ch :
            return 
        e =_styled_log_embed (channel .guild ,'channel','Канал удалён',
        fields =[
        ('Канал',f"**#{getattr(channel, 'name', '?')}** · `{channel.id}`"),
        ('Тип',_ch_type_label (getattr (channel ,'type','?'))),
        ('Категория',getattr (getattr (channel ,'category',None ),'name',None )or '—'),
        ('Удалил',f"**{mod_name or '—'}** `{mod_id or ''}`"),
        ('Через бота','⚠️ Да'if mod_is_bot else 'Нет'),
        ],
        color =0xE74C3C )
        if extra_warning :
            e .description +=f"\n\n{extra_warning}"
        e .set_footer (text =f"{channel.guild.name}")
        await _safe_send (ch ,embed =e )

    @commands .Cog .listener ()
    async def on_guild_channel_update (self ,before ,after ):
        # Собираем diff изменений: имя, тема, слоумод, NSFW
        diffs =[]
        if before .name !=after .name :
            diffs .append (('Название',f"`{before.name}` → `{after.name}`"))
        if getattr (before ,'topic',None )!=getattr (after ,'topic',None ):
            bt =(getattr (before ,'topic',None )or '—')[:80 ]
            at =(getattr (after ,'topic',None )or '—')[:80 ]
            diffs .append (('Тема',f"`{bt}` → `{at}`"))
        if getattr (before ,'slowmode_delay',0 )!=getattr (after ,'slowmode_delay',0 ):
            diffs .append (('Слоумод',f"{getattr(before,'slowmode_delay',0)}с → {getattr(after,'slowmode_delay',0)}с"))
        if getattr (before ,'nsfw',False )!=getattr (after ,'nsfw',False ):
            diffs .append (('NSFW',f"{getattr(before,'nsfw',False)} → {getattr(after,'nsfw',False)}"))
        if not diffs :
            return
        save_event (before .guild .id ,'channel','Канал изменён',{
        'channel_id':str (before .id ),
        'changes':[{'what':n ,'diff':v }for n ,v in diffs ],
        })
        ch =await self .get_log_channel (before .guild ,'channel')
        if not ch :
            return
        who =await _audit_actor (before .guild ,discord .AuditLogAction .channel_update ,target_id =before .id ,window =15 ,retries =1 )
        fields =[('Канал',f"{getattr(after,'mention','#'+after.name)} · `{before.id}`")]+diffs
        if who :
            fields .append (('Изменил',_actor_line (who )))
        e =_styled_log_embed (before .guild ,'channel','Канал изменён',
        fields =fields )
        await _safe_send (ch ,embed =e )

            # ROLES 

    @commands .Cog .listener ()
    async def on_guild_role_create (self ,role ):
        save_event (role .guild .id ,'role','Роль создана',{
        'role_id':str (role .id ),
        'role_name':role .name ,
        })
        ch =await self .get_log_channel (role .guild ,'role')
        if not ch :
            return
        try :
            color_hex =f"#{role.color.value:06x}"
        except Exception :
            color_hex ='—'
        _perms =role .permissions 
        _key_perms =[]
        if _perms .administrator :_key_perms .append ('Администратор')
        if _perms .manage_guild :_key_perms .append ('Управление сервером')
        if _perms .manage_channels :_key_perms .append ('Управление каналами')
        if _perms .manage_roles :_key_perms .append ('Управление ролями')
        if _perms .kick_members :_key_perms .append ('Кик')
        if _perms .ban_members :_key_perms .append ('Бан')
        if _perms .moderate_members :_key_perms .append ('Таймаут')
        e =_styled_log_embed (role .guild ,'role','Роль создана',
        fields =[
        ('Роль',f"{role.mention} **{role.name}** · `{role.id}`"),
        ('Цвет',f"`{color_hex}`"),
        ('Отдельный список','Да'if role .hoist else 'Нет'),
        ('Упоминаемая','Да'if role .mentionable else 'Нет'),
        ('Ключевые права',", ".join (_key_perms )if _key_perms else 'обычные'),
        ],
        color =getattr (role .color ,'value',0 )or 0x9B59B6 )
        await _safe_send (ch ,embed =e )

    @commands .Cog .listener ()
    async def on_guild_role_delete (self ,role ):
        save_event (role .guild .id ,'role','Роль удалена',{
        'role_id':str (role .id ),
        'role_name':role .name ,
        })
        ch =await self .get_log_channel (role .guild ,'role')
        if not ch :
            return
        try :
            _mcount =len (role .members )
        except Exception :
            _mcount ='?'
        who =await _audit_actor (role .guild ,discord .AuditLogAction .role_delete ,target_id =role .id ,window =20 ,retries =1 )
        e =_styled_log_embed (role .guild ,'role','Роль удалена',
        fields =[
        ('Роль',f"**{role.name}** · `{role.id}`"),
        ('Участников с ролью было',f"**{_mcount}**"),
        ('Удалил',_actor_line (who )),
        ],
        color =0xE74C3C )
        await _safe_send (ch ,embed =e )

    @commands .Cog .listener ()
    async def on_guild_role_update (self ,before ,after ):
        diffs =[]
        if before .name !=after .name :
            diffs .append (('Название',f"`{before.name}` → `{after.name}`"))
        try :
            if before .color !=after .color :
                diffs .append (('Цвет',f"`#{before.color.value:06x}` → `#{after.color.value:06x}`"))
        except Exception as _ex:
            log.debug("on_guild_role_update(): подавлено: %s", _ex)
        if getattr (before ,'hoist',None )!=getattr (after ,'hoist',None ):
            diffs .append (('Отдельный список',f"{getattr(before,'hoist',False)} → {getattr(after,'hoist',False)}"))
        if getattr (before ,'mentionable',None )!=getattr (after ,'mentionable',None ):
            diffs .append (('Упоминаемая',f"{getattr(before,'mentionable',False)} → {getattr(after,'mentionable',False)}"))
        try :
            if before .permissions .value !=after .permissions .value :
                diffs .append (('Права','набор прав изменён'))
        except Exception as _ex:
            log.debug("on_guild_role_update(): подавлено: %s", _ex)
        if not diffs :
            return
        save_event (before .guild .id ,'role','Роль изменена',{
        'role_id':str (before .id ),
        'old_name':before .name ,
        'new_name':after .name ,
        'changes':[{'what':n ,'diff':v }for n ,v in diffs ],
        })
        ch =await self .get_log_channel (before .guild ,'role')
        if not ch :
            return
        e =_styled_log_embed (before .guild ,'role','Роль изменена',
        fields =[('Роль',f"{after.mention} **{after.name}** · `{after.id}`")]+diffs )
        await _safe_send (ch ,embed =e )

            # PRIGLASENIYa 

    @commands .Cog .listener ()
    async def on_invite_create (self ,invite ):
        save_event (invite .guild .id ,'invite','Приглашение создано',{
        'user_id':str (invite .inviter .id )if invite .inviter else '?',
        'user_name':str (invite .inviter )if invite .inviter else '?',
        'code':invite .code ,
        'channel':invite .channel .name if invite .channel else '?',
        'max_uses':invite .max_uses or '∞',
        })
        ch =await self .get_log_channel (invite .guild ,'invite')
        if not ch :
            return
        _inv =invite .inviter 
        try :
            _max_age =getattr (invite ,'max_age',0 )or 0
            _age_txt ='∞'if _max_age ==0 else (f"{_max_age//3600} ч."if _max_age %86400 else f"{_max_age//86400} дн.")
        except Exception :
            _age_txt ='—'
        e =_styled_log_embed (invite .guild ,'invite','Приглашение создано',
        fields =[
        ('Код',f"`discord.gg/{invite.code}`"),
        ('Создал',f"**{getattr(_inv,'display_name',_inv)}** · `{getattr(_inv,'id','?')}`"if _inv else '—'),
        ('Канал',invite .channel .mention if invite .channel else '—'),
        ('Лимит использований',invite .max_uses or '∞'),
        ('Действует',_age_txt ),
        ('Временное','Да'if getattr (invite ,'temporary',False )else 'Нет'),
        ],
        color =0x16A085 ,thumbnail =(str (_inv .display_avatar .url )if _inv else None ))
        await _safe_send (ch ,embed =e )

    @commands .Cog .listener ()
    async def on_invite_delete (self ,invite ):
        save_event (invite .guild .id ,'invite','Приглашение удалено',{
        'code':invite .code ,
        'channel':invite .channel .name if invite .channel else '?',
        })
        ch =await self .get_log_channel (invite .guild ,'invite')
        if not ch :
            return
        e =_styled_log_embed (invite .guild ,'invite','Приглашение удалено',
        fields =[
        ('Код',f"`discord.gg/{invite.code}`"),
        ('Канал',invite .channel .mention if invite .channel else '—'),
        ('Использований было',getattr (invite ,'uses',0 )or 0 ),
        ],
        color =0x95A5A6 )
        await _safe_send (ch ,embed =e )

        # СЕРВЕР 

    @commands .Cog .listener ()
    async def on_guild_update (self ,before ,after ):
        diffs =[]
        if before .name !=after .name :
            diffs .append (('Название',f"`{before.name}` → `{after.name}`"))
        if getattr (before ,'afk_channel',None )!=getattr (after ,'afk_channel',None ):
            bc =getattr (getattr (before ,'afk_channel',None ),'name',None )or '—'
            ac =getattr (getattr (after ,'afk_channel',None ),'name',None )or '—'
            diffs .append (('AFK-канал',f"`{bc}` → `{ac}`"))
        if getattr (before ,'afk_timeout',None )!=getattr (after ,'afk_timeout',None ):
            diffs .append (('AFK-таймаут',f"{getattr(before,'afk_timeout','?')}с → {getattr(after,'afk_timeout','?')}с"))
        if getattr (before ,'verification_level',None )!=getattr (after ,'verification_level',None ):
            diffs .append (('Проверка участников',f"`{getattr(before,'verification_level','?')}` → `{getattr(after,'verification_level','?')}`"))
        if getattr (getattr (before ,'icon',None ),'key',None )!=getattr (getattr (after ,'icon',None ),'key',None ):
            diffs .append (('Аватар сервера','изменён'))
        if not diffs :
            return
        save_event (before .id ,'сервер','Сервер изменён',{
        'changes':[{'what':n ,'diff':v }for n ,v in diffs ],
        })
        ch =await self .get_log_channel (after ,'сервер')
        if not ch :
            return
        who =await _audit_actor (after ,discord .AuditLogAction .guild_update ,window =15 ,retries =1 )
        fields =diffs [:]
        if who :
            fields .append (('Изменил',_actor_line (who )))
        e =_styled_log_embed (after ,'guild','Сервер изменён',fields =fields )
        await _safe_send (ch ,embed =e )

            # ЦЕНТР ЛОГОВ: select-меню — статус категорий, тест, починка


            # DISCORD AUDIT LOG SYNC 

    async def _sync_discord_audit_log (self ):
        seen_file ='data/audit_seen.json'
        seen ={}
        if os .path .exists (seen_file ):
            try :
                with open (seen_file ,'r',encoding ='utf-8')as f :
                    seen =json .load (f )
            except Exception as _ex:
                log.debug("_sync_discord_audit_log(): подавлено: %s", _ex)

        action_map ={
        discord .AuditLogAction .ban :('mod','Бан'),
        discord .AuditLogAction .unban :('mod','Бан снят'),
        discord .AuditLogAction .kick :('mod','Кик'),
        discord .AuditLogAction .member_update :('mod','Участник обновлён'),
        discord .AuditLogAction .channel_create :('channel','Канал создан'),
        discord .AuditLogAction .channel_delete :('channel','Канал удалён'),
        discord .AuditLogAction .channel_update :('channel','Канал обновлён'),
        discord .AuditLogAction .role_create :('role','Роль создана'),
        discord .AuditLogAction .role_delete :('role','Роль удалена'),
        discord .AuditLogAction .role_update :('role','Роль обновлена'),
        discord .AuditLogAction .member_role_update :('role','Изменение ролей'),
        discord .AuditLogAction .invite_create :('invite','Приглашение создано'),
        discord .AuditLogAction .invite_delete :('invite','Приглашение удалено'),
        discord .AuditLogAction .message_delete :('message','Сообщение удалено'),
        discord .AuditLogAction .message_bulk_delete :('message','Массовое удаление'),
        discord .AuditLogAction .guild_update :('сервер','Сервер обновлён'),
        discord .AuditLogAction .webhook_create :('сервер','Вебхук создан'),
        discord .AuditLogAction .webhook_delete :('сервер','Вебхук удалён'),
        }

        cache_file ='data/discord_audit_cache.json'
        cache ={}
        if os .path .exists (cache_file ):
            try :
                with open (cache_file ,'r',encoding ='utf-8')as f :
                    cache =json .load (f )
            except Exception as _ex:
                log.debug("_sync_discord_audit_log(): подавлено: %s", _ex)

        audit_errors =[]
        # Панель живёт одним сервером (MAIN_GUILD_ID): аудит чужих гильдий
        # не тянем — иначе в «Журнале модерации» всплывают записи серверов,
        # которых владелец не настраивал.
        _main_gid =str (Config .MAIN_GUILD_ID or '')
        for guild in self .bot .guilds :
            gid =str (guild .id )
            if _main_gid and gid !=_main_gid :
                continue 
            last_id =seen .get (gid )
            new_entries =[]
            try :
                if not last_id :
                    cutoff =datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)-datetime .timedelta (days =7 )
                    async for entry in guild .audit_logs (limit =None ,oldest_first =False ):
                        if entry .created_at .replace (tzinfo =None )<cutoff :
                            break 
                        new_entries .append (entry )
                else :
                    async for entry in guild .audit_logs (limit =100 ,oldest_first =False ):
                        if entry .id <=int (last_id ):
                            break 
                        new_entries .append (entry )
            except discord .Forbidden :
                if gid not in self ._audit_forbidden_notified :
                    self ._audit_forbidden_notified .add (gid )
                    log .info (f'[LOGS] Нет права "Просмотр журнала аудита" — аудит-синк пропускается ({guild.name})')
                continue 
            except Exception as e :
                # Сбоит сам Discord (503/нагрузка) — НЕ логируем здесь каждые 30 сек:
                # цикл сам решит, когда и что писать (экспоненциальная пауза)
                audit_errors .append ((guild .name ,e ))
                continue 

            if not new_entries :
                continue 

            seen [gid ]=str (new_entries [0 ].id )
            if gid not in cache :
                cache [gid ]=[]

            for entry in reversed (new_entries ):
                # Полный русский словарь всех действий Discord (services/audit_labels):
                # никаких сырых bot_add / overwrite_create в журнале.
                cat ,action_name =(audit_label (entry .action .name )or 
                action_map .get (entry .action ,('сервер',str (entry .action ).split ('.')[-1 ])))
                target =entry .target 
                user =entry .user 

                # Opredelenie mute
                if entry .action ==discord .AuditLogAction .member_update :
                    after_attr =entry .changes .after 
                    if hasattr (after_attr ,'timed_out_until'):
                        action_name ='Мут'if getattr (after_attr ,'timed_out_until',None )else 'Мут снят'
                    else :
                        continue 

                tname =(getattr (target ,'display_name',None )or 
                getattr (target ,'name',None )or 
                str (getattr (target ,'id','?')))
                mname =(getattr (user ,'display_name',None )or 
                str (getattr (user ,'id','?')))if user else '?'

                ev ={
                'category':cat ,
                'action':action_name ,
                'target_name':tname ,
                'target_id':str (getattr (target ,'id','?')),
                'mod_name':mname ,
                'mod_id':str (getattr (user ,'id','?'))if user else '?',
                'reason':entry .reason or '',
                'timestamp':entry .created_at .isoformat (),
                'audit_id':str (entry .id ),
                'source':'discord_audit',
                }

                save_event (guild .id ,cat ,action_name ,{
                'target_name':tname ,
                'target_id':str (getattr (target ,'id','?')),
                'mod_name':mname ,
                'mod_id':str (getattr (user ,'id','?'))if user else '?',
                'reason':entry .reason or '',
                'audit_id':str (entry .id ),
                'source':'discord_audit',
                })

                cache [gid ].append (ev )

            if len (cache [gid ])>1000 :
                cache [gid ]=cache [gid ][-1000 :]

        try :
            os .makedirs ('data',exist_ok =True )
            with open (cache_file ,'w',encoding ='utf-8')as f :
                json .dump (cache ,f ,ensure_ascii =False ,indent =2 )
        except Exception as e :
            log .info (f'[LOGS] Ошибка запись kesa: {e}')

        try :
            with open (seen_file ,'w',encoding ='utf-8')as f :
                json .dump (seen ,f )
        except Exception as _ex:
            log.debug("_sync_discord_audit_log(): подавлено: %s", _ex)

        return audit_errors 

    @commands .Cog .listener ()
    async def on_ready (self ):
        import asyncio 
        await asyncio .sleep (5 )
        # on_ready может сработать повторно после переподключения шлюза —
        # цикл аудита запускаем только ОДИН раз, иначе будут дубли опросов
        if not self ._audit_sync_started :
            self ._audit_sync_started =True 
            asyncio .get_event_loop ().create_task (self ._audit_sync_loop ())
        # Тихий саморемонт: если категория логов осталась от старого кода без
        # доступа для бота — восстанавливаем права (частая причина «логи не идут»)
        for _g in self .bot .guilds :
            try :
                _cat ,_ow =ensure_log_permissions (_g )
                if _ow :
                    await _cat .edit (overwrites =_ow ,reason ="Hakumo: автопочинка прав на логи")
                    log .info (f'[LOGS] Права категории логов восстановлены: {_g.name}')
            except Exception as _he :
                log .info (f'[LOGS] self-heal ({getattr (_g ,"name","?")}): {_he}')
            try :
                await ensure_forum_log_permissions (_g )
            except Exception as _fe :
                log .info (f'[LOGS] форум-лог ({getattr (_g ,"name","?")}): {_fe}')

    async def _audit_sync_loop (self ):
        import asyncio 
        fail_streak =0 
        while True :
            try :
                errs =await self ._sync_discord_audit_log ()
            except Exception as e :
                errs =[('sync',e )]
            if errs :
                # Discord отвечает 5xx/недоступен: растущая пауза 1→2→4→8→15 мин (кап 15),
                # в журнал — одна строка при начале сбоя, каждая 10-я и при восстановлении
                fail_streak +=1 
                wait =min (30 *(2 ** min (fail_streak ,5 )),900 )
                gname ,err =errs [0 ]
                if fail_streak ==1 or fail_streak %10 ==0 :
                    log .info (f'[LOGS] Аудит API Discord недоступен ({fail_streak} подряд; {gname}): {err} — пауза {wait}с')
                await asyncio .sleep (wait )
            else :
                if fail_streak :
                    log .info (f'[LOGS] Аудит API Discord восстановился после {fail_streak} сбоев')
                fail_streak =0 
                await asyncio .sleep (30 )


async def setup (bot ):
    await bot .add_cog (Logs (bot ))
