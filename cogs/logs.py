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
'mod':{'label':'Модерация','emoji':'','color':0xE74C3C ,'channel':'moderasyon'},
'member':{'label':'Участники','emoji':'','color':0x2ECC71 ,'channel':'участники'},
'message':{'label':'Сообщения','emoji':'','color':0x3498DB ,'channel':'сообщения'},
'role':{'label':'Роли','emoji':'','color':0x9B59B6 ,'channel':'сервер'},
'channel':{'label':'Каналы','emoji':'','color':0xF39C12 ,'channel':'сервер'},
'voice':{'label':'Голос','emoji':'','color':0x1ABC9C ,'channel':'ses'},
'сервер':{'label':'Сервер','emoji':'','color':0xE67E22 ,'channel':'сервер'},
'automod':{'label':'Автоматически','emoji':'','color':0xE74C3C ,'channel':'moderasyon'},
'invite':{'label':'Priglaseniya','emoji':'','color':0x95A5A6 ,'channel':'сервер'},
}

DIV =""

# Ёnbellek сообщение — для znat soderjanie удален
_msg_cache :dict ={}

# Queue-based zapis — bir potok, нет race condition
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


    # Imena log-каналы
LOG_CHANNELS ={
'moderasyon':'-модерация',
'участники':'-участники',
'сообщения':'-сообщения',
'ses':'-ses',
'сервер':'-сервер',
}
LOG_CATEGORY_NAME =' Loglar'


class Logs (commands .Cog ):
    def __init__ (self ,bot ):
        self .bot =bot 

    async def get_log_channel (self ,guild ,category :str ='сервер'):
        """Найти канал для конкретной категории логов"""
        ch_name =CATEGORIES .get (category ,{}).get ('channel','сервер')
        target =LOG_CHANNELS .get (ch_name ,LOG_CHANNELS ['сервер'])

        # Arыyoruz по tocnomu isme
        ch =discord .utils .get (guild .text_channels ,name =target )
        if ch :
            return ch 

            # Fallback: arыyoruz старый server-log
        ch =discord .utils .get (guild .text_channels ,name ="server-log")
        if ch :
            return ch 

            # Fallback: arыyoruz aether-logs
        ch =discord .utils .get (guild .text_channels ,name ="aether-logs")
        return ch 

        # КОМАНДА: СОЗДАТЬ LOG-КАНАЛЫ 

    @app_commands .command (name ="setup-logs",description ="Создать категорию и каналы для логов")
    @app_commands .checks .has_permissions (administrator =True )
    async def setup_logs (self ,interaction :discord .Interaction ):
        guild =interaction .guild 
        await interaction .response .defer (ephemeral =True )

        # Проверяем, есть ли уже категория
        existing_cat =discord .utils .get (guild .categories ,name =LOG_CATEGORY_NAME )

        if not existing_cat :
        # Создать категорию от имени администратора
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
            # Daem eriшim модератор (роли с администрации kick/ban)
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
        already =[]

        for ch_name in LOG_CHANNELS .values ():
            existing =discord .utils .get (guild .text_channels ,name =ch_name )
            if existing :
            # Перемещаем в категорию, если ещё не там
                if existing .category !=existing_cat :
                    await existing .edit (category =existing_cat )
                already .append (ch_name )
            else :
                ch =await guild .create_text_channel (
                ch_name ,
                category =existing_cat ,
                reason ="Aether: создание канала логов",
                topic =f"Ежедневный sobitiy: {ch_name}"
                )
                created .append (ch_name )

                # Создал канал для приветствие если нет
        welcome_ch =discord .utils .get (guild .text_channels ,name ="-приветствие")
        if not welcome_ch :
            welcome_ch =await guild .create_text_channel (
            "-приветствие",
            category =existing_cat ,
            reason ="Aether: канал приветствие",
            topic ="Приветствие ve prosaniya с участник"
            )
            created .append ("-приветствие")
        else :
            already .append ("-приветствие")

        result_lines =[]
        if created :
            result_lines .append (f" **Создало ({len(created)}):**\n"+"\n".join (f"• {c}"for c in created ))
        if already :
            result_lines .append (f" **Zaten susestvuyut ({len(already)}):**\n"+"\n".join (f"• {a}"for a in already ))

        e =discord .Embed (
        title ="✅ Система логов настроена",
        description ="\n\n".join (result_lines ),
        color =0x2ECC71 ,
        timestamp =datetime .datetime .utcnow ()
        )
        e .add_field (
        name =" Каналы",
        value =(
        " **-moderasyon** — bani, kiki, muti, предупреждения\n"
        " **-участники** — вход, выход, смена ника\n"
        " **-сообщения** — удалить, redaktirovanie\n"
        " **-ses** — вход/выход из войса\n"
        " **-сервер** — каналы, roles, invayti, сервер\n"
        " **-приветствие** — приветствие ve prosaniya"
        ),
        inline =False 
        )
        e .set_footer (text =f"Aether • {guild.name}",icon_url =guild .icon .url if guild .icon else None )
        await interaction .followup .send (embed =e ,ephemeral =True )

        # УЧАСТНИКИ 

    @commands .Cog .listener ()
    async def on_member_join (self ,member ):
        age_days =(discord .utils .utcnow ()-member .created_at ).days 
        save_event (member .guild .id ,'member','Участник vosel',{
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
                        title =(w .get ('title')or 'Добро пожаловать добро пожаловать geldiniz, {user}!').replace ('{user}',member .display_name ).replace ('{сервер}',member .guild .name ).replace ('{count}',str (member .guild .member_count )).replace ('{mention}',member .mention )
                        msg =(w .get ('message')or '{mention} добро пожаловать добро пожаловать geldiniz на сервер!').replace ('{user}',member .display_name ).replace ('{сервер}',member .guild .name ).replace ('{count}',str (member .guild .member_count )).replace ('{mention}',member .mention )
                        color =int (w .get ('color','#c8922a').lstrip ('#'),16 )
                        e =discord .Embed (title =title ,description =msg ,color =color )
                        e .set_thumbnail (url =member .display_avatar .url )
                        await wch .send (embed =e )
        except Exception as _e :
            log .info (f'[WELCOME] Ошибка: {_e}')

        ch =await self .get_log_channel (member .guild ,'member')
        if not ch :
            return 

            # Hesap yaшы formatы
        if age_days <7 :
            age_text =f" новый hesap ({age_days} dn.)"
        elif age_days <30 :
            age_text =f"{age_days} день"
        elif age_days <365 :
            months =age_days //30 
            age_text =f"{months} mes."
        else :
            years =age_days //365 
            months =(age_days %365 )//30 
            age_text =f"{years} g. {months} mes."

        member_count =member .guild .member_count 
        join_ts =int (datetime .datetime .utcnow ().timestamp ())

        e =discord .Embed (color =0xC8922A ,timestamp =datetime .datetime .utcnow ())
        e .description =(
        f"## Добро пожаловать добро пожаловать geldiniz!\n"
        f"### {member.mention} prisoedinilsya e на сервер\n"
        f"\n\n"
        f"**Пользователь** — {member.display_name}\n"
        f"**ID** — `{member.id}`\n"
        f"**Hesap** — {age_text}\n"
        f"**Участник** — {member_count}-y на на сервере\n"
        f"**Prisoedinilsya** — <t:{join_ts}:R>\n\n"
        f""
        )
        e .set_thumbnail (url =member .display_avatar .url )

        # Banner или welcome GIF
        if member .guild .banner :
            e .set_image (url =member .guild .banner .url )
        else :
        # Welcome GIF
            e .set_image (url ="https://media.tenor.com/ZBDpMFBMFpkAAAAC/celebration-party.gif")

            # Footer с simge с сервер
        footer_text =f"{member.guild.name} · {member_count} участников"
        if member .guild .icon :
            e .set_footer (text =footer_text ,icon_url =member .guild .icon .url )
        else :
            e .set_footer (text =footer_text )

        await ch .send (embed =e )

    @commands .Cog .listener ()
    async def on_member_remove (self ,member ):
        save_event (member .guild .id ,'member','Участник visel',{
        'user_id':str (member .id ),
        'user_name':str (member ),
        'avatar':str (member .display_avatar .url ),
        'role':[r .name for r in member .roles [1 :]],
        })

        # Prosalnoe сообщение
        try :
            wcfg_path =f'data/welcome_{member.guild.id}.json'
            if os .path .exists (wcfg_path ):
                with open (wcfg_path ,'r',encoding ='utf-8')as f :
                    wcfg =json .load (f )
                lv =wcfg .get ('leave',{})
                if lv .get ('channel_id'):
                    lch =member .guild .get_channel (int (lv ['channel_id']))
                    if lch :
                        title =(lv .get ('title')or 'Do svidaniya, {user}!').replace ('{user}',member .display_name ).replace ('{сервер}',member .guild .name ).replace ('{count}',str (member .guild .member_count )).replace ('{mention}',member .mention )
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
        f"🚪 Участник вышел\n"
        f"### {member.display_name} покинул сервер\n"
        f"\n\n"
        f"**Пользователь** — {member.display_name}\n"
        f"**ID** — `{member.id}`\n"
        f"**Bil на на сервере** — {joined_ago}\n"
        f"**Роли** — {roles_str[:200]}\n"
        f"**Участников** — {member_count}\n\n"
        f""
        )
        e .set_thumbnail (url =member .display_avatar .url )

        # Footer с simge с сервер
        footer_text =f"{member.guild.name} · {member_count} участников"
        if member .guild .icon :
            e .set_footer (text =footer_text ,icon_url =member .guild .icon .url )
        else :
            e .set_footer (text =footer_text )

        await ch .send (embed =e )

    @commands .Cog .listener ()
    async def on_member_ban (self ,guild ,user ):
        save_event (guild .id ,'mod','Ban',{
        'user_id':str (user .id ),
        'user_name':str (user ),
        'avatar':str (user .display_avatar .url ),
        })

    @commands .Cog .listener ()
    async def on_member_unban (self ,guild ,user ):
        save_event (guild .id ,'mod','Ban удалено',{
        'user_id':str (user .id ),
        'user_name':str (user ),
        })

    @commands .Cog .listener ()
    async def on_member_update (self ,before ,after ):
    # Smena роль
        if before .roles !=after .roles :
            added =[r for r in after .roles if r not in before .roles ]
            removed =[r for r in before .roles if r not in after .roles ]
            if added or removed :
                save_event (before .guild .id ,'role','Роли изменено',{
                'user_id':str (before .id ),
                'user_name':str (before ),
                'added_roles':[r .name for r in added ],
                'removed_roles':[r .name for r in removed ],
                })
                ch =await self .get_log_channel (before .guild ,'role')
                if ch :
                    e =discord .Embed (color =0x9B59B6 ,timestamp =datetime .datetime .utcnow ())
                    desc =f"## Роли изменено\n**{before.display_name}** · `{before.id}`\n\n"
                    if added :
                        desc +=f"Dobavleni: {', '.join(r.mention for r in added)}\n"
                    if removed :
                        desc +=f"Удален: {', '.join(r.mention for r in removed)}"
                    e .description =desc 
                    e .set_footer (text =f"{before.guild.name}")
                    await ch .send (embed =e )

                    # Mute
        before_to =getattr (before ,'timed_out_until',None )
        after_to =getattr (after ,'timed_out_until',None )
        if before_to !=after_to :
            if after_to :
                save_event (before .guild .id ,'mod','Mute',{
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
                save_event (before .guild .id ,'mod','Mute удалено',{
                'user_id':str (after .id ),
                'user_name':after .display_name ,
                'action':'untimeout',
                })

                # Smena nika
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
                f"## Псевдоним изменён\n"
                f"**{before.display_name}** · `{before.id}`\n\n"
                f"Bilo: `{before.nick or before.name}`\n"
                f"Stalo: `{after.nick or after.name}`"
                )
                e .set_footer (text =f"{before.guild.name}")
                await ch .send (embed =e )

                # СООБЩЕНИЯ 

    @commands .Cog .listener ()
    async def on_message (self ,message ):
        if message .author .bot or not message .guild :
            return 
        content =message .content [:500 ]if message .content else '[Vlojenie/Embed]'
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
        if message .author .bot or not message .guild :
            return 
        cached =_msg_cache .pop (message .id ,None )
        content =message .content or (cached ['content']if cached else '')or '[Содержимое не найдено]'
        save_event (message .guild .id ,'message','Сообщение удалено',{
        'user_id':str (message .author .id ),
        'user_name':str (message .author ),
        'channel':message .channel .name ,
        'channel_id':str (message .channel .id ),
        'content':content [:500 ],
        })
        ch =await self .get_log_channel (message .guild ,'message')
        if not ch :
            return 
        e =discord .Embed (color =0xE74C3C ,timestamp =datetime .datetime .utcnow ())
        e .description =(
        f"## Сообщение удалено\n"
        f"**{message.author.display_name}** · `{message.author.id}`\n"
        f"Канал: {message.channel.mention}\n\n"
        f"> {content[:500] or '[Вложение]'}"
        )
        e .set_footer (text =f"{message.guild.name}")
        await ch .send (embed =e )

        # 👻 GHOST PING: тегнули и сразу удалили — отдельный алерт модераторам
        _mentioned =[m for m in message .mentions if not m .bot ]+list (message .role_mentions or [])
        if _mentioned :
            _targets =", ".join (m .mention for m in _mentioned [:8 ])
            ge =discord .Embed (color =0x9B59B6 ,timestamp =datetime .datetime .utcnow ())
            ge .description =(
            f"## 👻 Ghost Ping\n"
            f"**{message.author.display_name}** · `{message.author.id}`\n"
            f"тегнул и сразу удалил сообщение\n\n"
            f"Упомянуты: {_targets}\n"
            f"Канал: {message.channel.mention}\n\n"
            f"> {content[:300] or '[Вложение]'}"
            )
            ge .set_footer (text =f"{message.guild.name} · ghost-ping detector")
            try:
                await ch .send (embed =ge )
            except Exception :
                pass

    @commands .Cog .listener ()
    async def on_message_edit (self ,before ,after ):
        if before .author .bot or before .content ==after .content or not before .guild :
            return 
        save_event (before .guild .id ,'message','Сообщение изменено',{
        'user_id':str (before .author .id ),
        'user_name':str (before .author ),
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
        f"## Сообщение изменено\n"
        f"**{before.author.display_name}** · `{before.author.id}`\n"
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
        save_event (channel .guild .id ,'channel','Канал создано',{
        'channel_id':str (channel .id ),
        'channel_name':channel .name ,
        'channel_type':str (channel .type ),
        })
        ch =await self .get_log_channel (channel .guild ,'channel')
        if not ch :
            return 
        e =discord .Embed (color =0x2ECC71 ,timestamp =datetime .datetime .utcnow ())
        e .description =(
        f"## Канал создано\n"
        f"**{channel.name}** · `{channel.id}`\n\n"
        f"Tюr: {str(channel.type)}"
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
                save_event (guild .id ,'channel','Канал удален',{
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
                    f"## Канал удален\n"
                    f"**{getattr(channel, 'name', '?')}** · `{channel.id}`\n\n"
                    f"⚠️ **Боту не выдано право `Просмотр журнала аудита` (View Audit Log).**\n"
                    f"Невозможно определить, кто удалил канал.\n\n"
                    f"Дайте боту это право в настройках сервера."
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

        save_event (channel .guild .id ,'channel','Канал удален',{
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
        f"## Канал удален\n"
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
            save_event (before .guild .id ,'channel','Канал pereimenovan',{
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
            save_event (before .guild .id ,'role','Роль pereimenovana',{
            'role_id':str (before .id ),
            'old_name':before .name ,
            'new_name':after .name ,
            })

            # PRIGLASENIYa 

    @commands .Cog .listener ()
    async def on_invite_create (self ,invite ):
        save_event (invite .guild .id ,'invite','Davet создано',{
        'user_id':str (invite .inviter .id )if invite .inviter else '?',
        'user_name':str (invite .inviter )if invite .inviter else '?',
        'code':invite .code ,
        'channel':invite .channel .name if invite .channel else '?',
        'max_uses':invite .max_uses or '∞',
        })

    @commands .Cog .listener ()
    async def on_invite_delete (self ,invite ):
        save_event (invite .guild .id ,'invite','Davet удалено',{
        'code':invite .code ,
        'channel':invite .channel .name if invite .channel else '?',
        })

        # СЕРВЕР 

    @commands .Cog .listener ()
    async def on_guild_update (self ,before ,after ):
        if before .name !=after .name :
            save_event (before .id ,'сервер','Сервер pereimenovan',{
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
        discord .AuditLogAction .ban :('mod','Ban'),
        discord .AuditLogAction .unban :('mod','Ban удалено'),
        discord .AuditLogAction .kick :('mod','Kick'),
        discord .AuditLogAction .member_update :('mod','Участник обновлено'),
        discord .AuditLogAction .channel_create :('channel','Канал создано'),
        discord .AuditLogAction .channel_delete :('channel','Канал удалено'),
        discord .AuditLogAction .channel_update :('channel','Канал обновлено'),
        discord .AuditLogAction .role_create :('role','Роль создан'),
        discord .AuditLogAction .role_delete :('role','Роль удалено'),
        discord .AuditLogAction .role_update :('role','Роль obnovlena'),
        discord .AuditLogAction .member_role_update :('role','Роли изменено'),
        discord .AuditLogAction .invite_create :('invite','Davet создано'),
        discord .AuditLogAction .invite_delete :('invite','Davet удалено'),
        discord .AuditLogAction .message_delete :('message','Сообщение удалено'),
        discord .AuditLogAction .message_bulk_delete :('message','Массовая удалить'),
        discord .AuditLogAction .guild_update :('сервер','Сервер обновлено'),
        discord .AuditLogAction .webhook_create :('сервер','Vebhuk создано'),
        discord .AuditLogAction .webhook_delete :('сервер','Vebhuk удалено'),
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
                        action_name ='Mute'if getattr (after_attr ,'timed_out_until',None )else 'Mute удалено'
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
                log .info (f'[LOGS] Ошибка sync ({fail_count}): {e} — jdem {wait}с')
                await asyncio .sleep (wait )


async def setup (bot ):
    await bot .add_cog (Logs (bot ))
