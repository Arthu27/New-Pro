import discord 
from discord .ext import commands 
from discord import app_commands 
import datetime 
import json 
import os 
import time 
import threading 
import queue 
from typing import Dict ,Any 

from logger import get_logger 
log =get_logger ("logs")


AUDIT_FILE ="data/audit_log.json"

CATEGORIES ={
'mod':{'label':'Модерация','emoji':'','color':0xE74C3C ,'channel':'модерация'},
'member':{'label':'Участники','emoji':'','color':0x2ECC71 ,'channel':'участники'},
'message':{'label':'Сообщения','emoji':'','color':0x3498DB ,'channel':'сообщения'},
'role':{'label':'Роли','emoji':'','color':0x9B59B6 ,'channel':'сервер'},
'channel':{'label':'Каналы','emoji':'','color':0xF39C12 ,'channel':'сервер'},
'voice':{'label':'Голос','emoji':'','color':0x1ABC9C ,'channel':'ses'},
'сервер':{'label':'Сервер','emoji':'','color':0xE67E22 ,'channel':'сервер'},
'automod':{'label':'Автоматически','emoji':'','color':0xE74C3C ,'channel':'модерация'},
'invite':{'label':'Приглашения','emoji':'','color':0x95A5A6 ,'channel':'сервер'},
}

DIV =""

# Кэш сообщений — чтобы знать содержимое удалённых
_msg_cache :dict ={}

# Запись через очередь — один поток, нет race condition
_audit_queue :queue .Queue =queue .Queue ()
_audit_worker_thread :threading .Thread =None 

def _audit_worker ():
    while True :
        try :
            event_data =_audit_queue .get (timeout =2.0 )
        except queue .Empty :
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
    'timestamp':datetime .datetime .utcnow ().isoformat (),
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
        except Exception :
            pass 

def _ensure_worker ():
    global _audit_worker_thread 
    if _audit_worker_thread is None or not _audit_worker_thread .is_alive ():
        _audit_worker_thread =threading .Thread (target =_audit_worker ,daemon =True ,name ="audit-worker")
        _audit_worker_thread .start ()

def save_event (guild_id ,category ,action ,details :dict ):
    if action =='Сообщение отправлено':
        return 
    _ensure_worker ()
    _audit_queue .put ({
    'guild_id':guild_id ,
    'category':category ,
    'action':action ,
    'details':details ,
    })


    # Имена лог-каналов
LOG_CHANNELS ={
'модерация':'-модерация',
'moderasyon':'-модерация',  # legacy alias (старые серверы)
'участники':'-участники',
'сообщения':'-сообщения',
'ses':'-ses',
'сервер':'-сервер',
}
LOG_CATEGORY_NAME =' Логи'

# Старые (legacy) имена каналов по каждому каноническому — раньше коги
# писали логи в разные каналы (mod-log, moderasyon, server-log …)
LEGACY_CHANNEL_NAMES ={
'-модерация':['mod-log','moderasyon','-moderasyon','modlog'],
'-сообщения':['message-log','mesaj-log'],
'-участники':['member-log','uye-log'],
'-ses':['voice-log','ses-log'],
'-сервер':['server-log','aether-logs','sunucu-log'],
}


def find_log_channel (guild ,category :str ='сервер'):
    """Единый поиск лог-канала для категории.

    Порядок: каноническое имя (-модерация …) → legacy-имена (mod-log, moderasyon …)
    → общие старые каналы (server-log, aether-logs). None, если ничего нет.
    Используется ВСЕМИ когами — иначе логи уходят в несуществующие каналы.
    """
    category ={'модерация':'mod','moderasyon':'mod','участники':'member',
    'сообщения':'message','голос':'voice','ses':'voice','роли':'role',
    'каналы':'channel'}.get (category ,category )
    ch_name =CATEGORIES .get (category ,{}).get ('channel','сервер')
    target =LOG_CHANNELS .get (ch_name ,LOG_CHANNELS ['сервер'])

    candidates =[target ]+LEGACY_CHANNEL_NAMES .get (target ,[])+['server-log','aether-logs']
    seen =set ()
    for name in candidates :
        if name in seen :
            continue
        seen .add (name )
        ch =discord .utils .get (guild .text_channels ,name =name )
        if ch :
            return ch
    return None


class Logs (commands .Cog ):
    def __init__ (self ,bot ):
        self .bot =bot 

    async def get_log_channel (self ,guild ,category :str ='сервер'):
        """Найти канал для конкретной категории логов (общий резолвер)."""
        return find_log_channel (guild ,category )

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
            reason ="Aether: создание категории логов"
            )

        created =[]
        migrated =[]
        already =[]

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
                    await legacy_ch .edit (name =ch_name ,category =existing_cat ,reason ="Aether: миграция лог-канала")
                    migrated .append (f"#{legacy_name} → #{ch_name}")
                    continue
                await guild .create_text_channel (
                ch_name ,
                category =existing_cat ,
                reason ="Aether: создание канала логов",
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
                await guild .create_text_channel (extra ,category =existing_cat ,reason ="Aether: сервисный канал логов",topic =topic )
                created .append (extra )

        # 4) Публичный канал приветствий — НЕ в скрытой категории (его видят все)
        welcome_ch =discord .utils .get (guild .text_channels ,name ="-приветствие")
        if not welcome_ch :
            welcome_ch =await guild .create_text_channel (
            "-приветствие",
            reason ="Aether: канал приветствий",
            topic ="Приветствие и прощание участников"
            )
            created .append ("-приветствие (публичный)")
        else :
            # Старый баг: канал приветствий был спрятан в закрытой категории логов
            if welcome_ch .category ==existing_cat :
                await welcome_ch .edit (category =None ,reason ="Aether: канал приветствий должен быть публичным")
                await welcome_ch .set_permissions (guild .default_role ,read_messages =True ,send_messages =False ,reason ="Aether: публичный канал приветствий")
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
        timestamp =datetime .datetime .utcnow ()
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
        e .set_footer (text =f"Aether • {guild.name}",icon_url =guild .icon .url if guild .icon else None )
        await interaction .followup .send (embed =e ,ephemeral =True )

    @app_commands .command (name ="setup-logs",description ="Создать/починить категорию и каналы для логов")
    @app_commands .checks .has_permissions (administrator =True )
    async def setup_logs (self ,interaction :discord .Interaction ):
        await self ._setup_logs_core (interaction )

    @app_commands .command (name ="logs-setup",description ="Создать/починить категорию и каналы для логов")
    @app_commands .checks .has_permissions (administrator =True )
    async def logs_setup (self ,interaction :discord .Interaction ):
        await self ._setup_logs_core (interaction )

        # УЧАСТНИКИ 

    @commands .Cog .listener ()
    async def on_member_join (self ,member ):
        age_days =(discord .utils .utcnow ()-member .created_at ).days 
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

        member_count =member .guild .member_count 
        join_ts =int (datetime .datetime .utcnow ().timestamp ())

        e =discord .Embed (color =0xC8922A ,timestamp =datetime .datetime .utcnow ())
        e .description =(
        "## Добро пожаловать!\n"
        f"### {member.mention} присоединился к серверу\n"
        "\n\n"
        f"**Пользователь** — {member.display_name}\n"
        f"**ID** — `{member.id}`\n"
        f"**Аккаунт** — {age_text}\n"
        f"**Участник** — {member_count}-й на сервере\n"
        f"**Присоединился** — <t:{join_ts}:R>\n\n"
        ""
        )
        e .set_thumbnail (url =member .display_avatar .url )

        # Banner или welcome GIF
        if member .guild .banner :
            e .set_image (url =member .guild .banner .url )
        else :
        # Welcome GIF
            e .set_image (url ="https://media.tenor.com/ZBDpMFBMFpkAAAAC/celebration-party.gif")

            # Footer с иконкой сервера
        footer_text =f"{member.guild.name} · {member_count} участников"
        if member .guild .icon :
            e .set_footer (text =footer_text ,icon_url =member .guild .icon .url )
        else :
            e .set_footer (text =footer_text )

        await ch .send (embed =e )

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
            days_on_server =(datetime .datetime .utcnow ()-member .joined_at .replace (tzinfo =None )).days 
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

        e =discord .Embed (color =0xE74C3C ,timestamp =datetime .datetime .utcnow ())
        e .description =(
        "🚪 Участник вышел\n"
        f"### {member.display_name} покинул сервер\n"
        "\n\n"
        f"**Пользователь** — {member.display_name}\n"
        f"**ID** — `{member.id}`\n"
        f"**Был на сервере** — {joined_ago}\n"
        f"**Роли** — {roles_str[:200]}\n"
        f"**Участников** — {member_count}\n\n"
        ""
        )
        e .set_thumbnail (url =member .display_avatar .url )

        # Footer с иконкой сервера
        footer_text =f"{member.guild.name} · {member_count} участников"
        if member .guild .icon :
            e .set_footer (text =footer_text ,icon_url =member .guild .icon .url )
        else :
            e .set_footer (text =footer_text )

        await ch .send (embed =e )

    @commands .Cog .listener ()
    async def on_member_ban (self ,guild ,user ):
        save_event (guild .id ,'mod','Бан',{
        'user_id':str (user .id ),
        'user_name':str (user ),
        'avatar':str (user .display_avatar .url ),
        })

    @commands .Cog .listener ()
    async def on_member_unban (self ,guild ,user ):
        save_event (guild .id ,'mod','Бан снят',{
        'user_id':str (user .id ),
        'user_name':str (user ),
        })

    @commands .Cog .listener ()
    async def on_member_update (self ,before ,after ):
    # Смена ролей
        if before .roles !=after .roles :
            added =[r for r in after .roles if r not in before .roles ]
            removed =[r for r in before .roles if r not in after .roles ]
            if added or removed :
                save_event (before .guild .id ,'role','Изменение ролей',{
                'user_id':str (before .id ),
                'user_name':str (before ),
                'added_roles':[r .name for r in added ],
                'removed_roles':[r .name for r in removed ],
                })
                ch =await self .get_log_channel (before .guild ,'role')
                if ch :
                    e =discord .Embed (color =0x9B59B6 ,timestamp =datetime .datetime .utcnow ())
                    desc =f"## Изменение ролей\n**{before.display_name}** · `{before.id}`\n\n"
                    if added :
                        desc +=f"Добавлены: {', '.join(r.mention for r in added)}\n"
                    if removed :
                        desc +=f"Удалены: {', '.join(r.mention for r in removed)}"
                    e .description =desc 
                    e .set_footer (text =f"{before.guild.name}")
                    await ch .send (embed =e )

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
            else :
                save_event (before .guild .id ,'mod','Мут снят',{
                'user_id':str (after .id ),
                'user_name':after .display_name ,
                'action':'untimeout',
                })

                # Смена ника
        if before .nick !=after .nick :
            save_event (before .guild .id ,'member','Псевдоним изменён',{
            'user_id':str (before .id ),
            'user_name':str (before ),
            'old_nick':before .nick or before .name ,
            'new_nick':after .nick or after .name ,
            })
            ch =await self .get_log_channel (before .guild ,'member')
            if ch :
                e =discord .Embed (color =0x3498DB ,timestamp =datetime .datetime .utcnow ())
                e .description =(
                "## Псевдоним изменён\n"
                f"**{before.display_name}** · `{before.id}`\n\n"
                f"Было: `{before.nick or before.name}`\n"
                f"Стало: `{after.nick or after.name}`"
                )
                e .set_footer (text =f"{before.guild.name}")
                await ch .send (embed =e )

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
        e =discord .Embed (color =0xE74C3C ,timestamp =datetime .datetime .utcnow ())
        e .description =(
        "## Сообщение удалено\n"
        f"**{author_name}** · `{author_id}`\n"
        f"Канал: {message.channel.mention}\n\n"
        f"> {content[:500] or '[Вложение]'}"
        )
        e .set_footer (text =f"{message.guild.name}")
        try :
            await ch .send (embed =e )
        except Exception as _se :
            log .info (f'[LOGS] Не удалось отправить лог удаления: {_se}')

        # 👻 GHOST PING: тегнули и сразу удалили — отдельный алерт модераторам
        _mentioned =[m for m in message .mentions if not m .bot ]+list (message .role_mentions or [])
        if _mentioned :
            _targets =", ".join (m .mention for m in _mentioned [:8 ])
            ge =discord .Embed (color =0x9B59B6 ,timestamp =datetime .datetime .utcnow ())
            ge .description =(
            "## 👻 Ghost Ping\n"
            f"**{author_name}** · `{author_id}`\n"
            "тегнул и сразу удалил сообщение\n\n"
            f"Упомянуты: {_targets}\n"
            f"Канал: {message.channel.mention}\n\n"
            f"> {content[:300] or '[Вложение]'}"
            )
            ge .set_footer (text =f"{message.guild.name} · ghost-ping detector")
            try:
                await ch .send (embed =ge )
            except Exception :
                pass
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
        e =discord .Embed (color =0x3498DB ,timestamp =datetime .datetime .utcnow ())
        e .description =(
        "## Сообщение изменено\n"
        f"**{_ename}** · `{_eid}`\n"
        f"Канал: {before.channel.mention} · [Перейти]({after.jump_url})\n\n"
        f"**Было:**\n> {before.content[:400] or '[Пусто]'}\n\n"
        f"**Стало:**\n> {after.content[:400] or '[Пусто]'}"
        )
        e .set_footer (text =f"{before.guild.name}")
        await ch .send (embed =e )

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
        e =discord .Embed (color =color ,timestamp =datetime .datetime .utcnow ())
        e .description =(
        f"## {action}\n"
        f"**{member.display_name}** · `{member.id}`\n\n"
        f"{line}"
        )
        e .set_footer (text =f"{member.guild.name}")
        await ch .send (embed =e )

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
        e =discord .Embed (color =0x2ECC71 ,timestamp =datetime .datetime .utcnow ())
        e .description =(
        "## Канал создан\n"
        f"**{channel.name}** · `{channel.id}`\n\n"
        f"Тип: {str(channel.type)}"
        )
        e .set_footer (text =f"{channel.guild.name}")
        await ch .send (embed =e )

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
            except Exception :
                pass
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
                    e =discord .Embed (color =0xE74C3C ,timestamp =datetime .datetime .utcnow ())
                    e .description =(
                    "## Канал удален\n"
                    f"**{getattr(channel, 'name', '?')}** · `{channel.id}`\n\n"
                    "⚠️ **Боту не выдано право `Просмотр журнала аудита` (View Audit Log).**\n"
                    "Невозможно определить, кто удалил канал.\n\n"
                    "Дайте боту это право в настройках сервера."
                    )
                    e .set_footer (text =f"{guild.name}")
                    await ch .send (embed =e )
                return
            # Retry-цикл: audit log может прийти с задержкой
            for attempt in range (6 ):
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
                except Exception :
                    pass
                if mod_id is not None :
                    break 
                await _ai .sleep (1.0 )  # ждём появления записи в audit log
        except Exception :
            pass

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
        e =discord .Embed (color =0xE74C3C ,timestamp =datetime .datetime .utcnow ())
        e .description =(
        "## Канал удален\n"
        f"**{getattr(channel, 'name', '?')}** · `{channel.id}`\n\n"
        f"Тип: {str(getattr(channel, 'type', '?'))}\n"
        f"Удалил: **{mod_name or '—'}** `{mod_id or ''}`\n"
        f"Это бот: {'Да' if mod_is_bot else 'Нет'}"
        )
        if extra_warning :
            e .description +=f"\n\n{extra_warning}"
        e .set_footer (text =f"{channel.guild.name}")
        await ch .send (embed =e )

    @commands .Cog .listener ()
    async def on_guild_channel_update (self ,before ,after ):
        if before .name !=after .name :
            save_event (before .guild .id ,'channel','Канал переименован',{
            'channel_id':str (before .id ),
            'old_name':before .name ,
            'new_name':after .name ,
            })

            # ROLES 

    @commands .Cog .listener ()
    async def on_guild_role_create (self ,role ):
        save_event (role .guild .id ,'role','Роль создана',{
        'role_id':str (role .id ),
        'role_name':role .name ,
        })

    @commands .Cog .listener ()
    async def on_guild_role_delete (self ,role ):
        save_event (role .guild .id ,'role','Роль удалена',{
        'role_id':str (role .id ),
        'role_name':role .name ,
        })

    @commands .Cog .listener ()
    async def on_guild_role_update (self ,before ,after ):
        if before .name !=after .name :
            save_event (before .guild .id ,'role','Роль переименована',{
            'role_id':str (before .id ),
            'old_name':before .name ,
            'new_name':after .name ,
            })

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

    @commands .Cog .listener ()
    async def on_invite_delete (self ,invite ):
        save_event (invite .guild .id ,'invite','Приглашение удалено',{
        'code':invite .code ,
        'channel':invite .channel .name if invite .channel else '?',
        })

        # СЕРВЕР 

    @commands .Cog .listener ()
    async def on_guild_update (self ,before ,after ):
        if before .name !=after .name :
            save_event (before .id ,'сервер','Сервер переименован',{
            'old_name':before .name ,
            'new_name':after .name ,
            })

            # DISCORD AUDIT LOG SYNC 

    async def _sync_discord_audit_log (self ):
        seen_file ='data/audit_seen.json'
        seen ={}
        if os .path .exists (seen_file ):
            try :
                with open (seen_file ,'r',encoding ='utf-8')as f :
                    seen =json .load (f )
            except Exception :
                pass 

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
            except Exception :
                pass 

        for guild in self .bot .guilds :
            gid =str (guild .id )
            last_id =seen .get (gid )
            new_entries =[]
            try :
                if not last_id :
                    cutoff =datetime .datetime .utcnow ()-datetime .timedelta (days =7 )
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
                continue 
            except Exception as e :
                log .info (f'[LOGS] Ошибка audit log ({guild.name}): {e}')
                continue 

            if not new_entries :
                continue 

            seen [gid ]=str (new_entries [0 ].id )
            if gid not in cache :
                cache [gid ]=[]

            for entry in reversed (new_entries ):
                cat ,action_name =action_map .get (entry .action ,('сервер',str (entry .action ).split ('.')[-1 ]))
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
        except Exception :
            pass 

    @commands .Cog .listener ()
    async def on_ready (self ):
        import asyncio 
        await asyncio .sleep (5 )
        asyncio .get_event_loop ().create_task (self ._audit_sync_loop ())

    async def _audit_sync_loop (self ):
        import asyncio 
        fail_count =0 
        while True :
            try :
                await self ._sync_discord_audit_log ()
                fail_count =0 
                await asyncio .sleep (30 )
            except Exception as e :
                fail_count +=1 
                wait =min (60 *fail_count ,300 )
                log .info (f'[LOGS] Ошибка sync ({fail_count}): {e} — ждём {wait}с')
                await asyncio .sleep (wait )


async def setup (bot ):
    await bot .add_cog (Logs (bot ))
