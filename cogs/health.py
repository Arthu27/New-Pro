"""Оценка состояния сервера (0–100) и статистика по каналам.

/server-health — сводка здоровья сервера: баны, кики, спам, активность.
/channel-stats — топ самых активных каналов.
"""

from logger import get_logger

_log = get_logger("health")

from json_store import load_json as _js_load, save_json as _js_save

import discord 
from discord .ext import commands 
from discord import app_commands 
import json 
import os 
from datetime import datetime ,timezone ,date 
from collections import defaultdict 
from config import Config 

def _health_file (guild_id ):
    return f'data/health_{guild_id}.json'

_HEALTH_DEFAULT ={'channel_messages':{},'hourly':{},'daily':{},'spam_count':0 ,'ban_count':0 ,'kick_count':0 }

def _load_health (guild_id ):
    # горячий путь (каждое сообщение) — читаем через кеш, диск не трогаем
    return _js_load (_health_file (guild_id ),_HEALTH_DEFAULT ,log =_log )

def _save_health (guild_id ,data ):
    _js_save (_health_file (guild_id ),data ,log =_log )

def _calc_score (data ,guild :discord .Guild ):
    """Расчёт оценки состояния сервера (0-100)"""
    score =100 
    total_members =max (guild .member_count ,1 )

    # доля банов (за последние 7 дней)
    ban_rate =data .get ('ban_count',0 )/total_members *100 
    score -=min (ban_rate *5 ,30 )

    # доля киков
    kick_rate =data .get ('kick_count',0 )/total_members *100 
    score -=min (kick_rate *3 ,20 )

    # Spam количество
    spam =data .get ('spam_count',0 )
    score -=min (spam *0.5 ,20 )

    # бонус за активность: +10, если почти каждый день были сообщения
    daily =data .get ('daily',{})
    active_days =len ([v for v in daily .values ()if v >0 ])
    if active_days >=5 :
        score +=10 
    elif active_days >=3 :
        score +=5 

    return max (0 ,min (100 ,round (score )))

def _score_label (score ):
    if score >=80 :return "🟢 Отлично",0x2ecc71 
    if score >=60 :return "🟡 Хорошо",0xf1c40f 
    if score >=40 :return "🟠 Центр",0xe67e22 
    return " Плохо",0xe74c3c 


class Health (commands .Cog ):
    def __init__ (self ,bot ):
        self .bot =bot 
        # Определение спама: время последних сообщений {guild_id: {user_id: [timestamps]}}
        self ._msg_times =defaultdict (lambda :defaultdict (list ))

    @commands .Cog .listener ()
    async def on_message (self ,message :discord .Message ):
        if message .author .bot or not message .guild :
            return 
        gid =str (message .guild .id )
        uid =str (message .author .id )
        cid =str (message .channel .id )
        cname =message .channel .name 

        data =_load_health (gid )

        # счётчики сообщений по каналам
        if 'channel_messages'not in data :
            data ['channel_messages']={}
        ch_data =data ['channel_messages'].setdefault (cid ,{'name':cname ,'total':0 })
        ch_data ['total']=ch_data .get ('total',0 )+1 
        ch_data ['name']=cname 

        # почасовая статистика
        hour_key =datetime .now (timezone .utc ).strftime ('%Y-%m-%d %H:00')
        data .setdefault ('hourly',{})[hour_key ]=data ['hourly'].get (hour_key ,0 )+1 
        # держим последние 48 часов
        hourly =data ['hourly']
        if len (hourly )>48 :
            oldest =sorted (hourly .keys ())[0 ]
            del hourly [oldest ]

            # ежедневная статистика
        day_key =str (date .today ())
        data .setdefault ('daily',{})[day_key ]=data ['daily'].get (day_key ,0 )+1 
        # держим последние 30 дней
        daily =data ['daily']
        if len (daily )>30 :
            oldest =sorted (daily .keys ())[0 ]
            del daily [oldest ]

            # детект спама (5+ сообщений за 5 секунд)
        import time 
        now =time .time ()
        times =self ._msg_times [gid ][uid ]
        times .append (now )
        times [:]=[t for t in times if now -t <5 ]
        if len (times )>=5 :
            data ['spam_count']=data .get ('spam_count',0 )+1 

        _save_health (gid ,data )

    @commands .Cog .listener ()
    async def on_member_ban (self ,guild ,user ):
        data =_load_health (str (guild .id ))
        data ['ban_count']=data .get ('ban_count',0 )+1 
        _save_health (str (guild .id ),data )

    @commands .Cog .listener ()
    async def on_member_remove (self ,member ):
    # проверяем, не кик ли это
        try :
            async for entry in member .guild .audit_logs (limit =1 ,action =discord .AuditLogAction .kick ):
                if entry .target .id ==member .id :
                    data =_load_health (str (member .guild .id ))
                    data ['kick_count']=data .get ('kick_count',0 )+1 
                    _save_health (str (member .guild .id ),data )
        except Exception as _ex:
            _log.debug("on_member_remove(): подавлено: %s", _ex)

    @app_commands .command (name ="server-health",description ="Показать оценку состояния сервера (активность, баны, спам)")
    async def server_health (self ,interaction :discord .Interaction ):
        gid =str (interaction .guild .id )
        data =_load_health (gid )
        score =_calc_score (data ,interaction .guild )
        label ,color =_score_label (score )

        e =discord .Embed (title =f"💚 {interaction.guild.name} — состояние сервера",color =color )
        e .set_thumbnail (url =interaction .guild .icon .url if interaction .guild .icon else None )

        bar_filled =round (score /10 )
        bar =""*bar_filled +""*(10 -bar_filled )
        e .add_field (name ="🩺 Оценка",value =f"`{bar}` **{score}/100** {label}",inline =False )

        e .add_field (name =" Ban",value =str (data .get ('ban_count',0 )),inline =True )
        e .add_field (name =" Kick",value =str (data .get ('kick_count',0 )),inline =True )
        e .add_field (name =" Spam",value =str (data .get ('spam_count',0 )),inline =True )

        # Самые активные каналы
        ch_msgs =data .get ('channel_messages',{})
        top =sorted (ch_msgs .values (),key =lambda x :x .get ('total',0 ),reverse =True )[:3 ]
        if top :
            ch_text ="\n".join (f"#{c['name']}: {c['total']} сообщ."for c in top )
            e .add_field (name =" Самые активные каналы",value =ch_text ,inline =False )

        e .set_footer (text ="Оценка: по количеству банов/киков/спама и по активности")
        await interaction .response .send_message (embed =e )

    @app_commands .command (name ="channel-stats",description ="Показать статистику сообщений по каналам")
    async def channel_stats (self ,interaction :discord .Interaction ):
        gid =str (interaction .guild .id )
        data =_load_health (gid )
        ch_msgs =data .get ('channel_messages',{})

        if not ch_msgs :
            await interaction .response .send_message ("Пока данных нет.",ephemeral =True )
            return 

        top =sorted (ch_msgs .values (),key =lambda x :x .get ('total',0 ),reverse =True )[:10 ]
        max_val =top [0 ]['total']if top else 1 

        e =discord .Embed (title ="📊 Статистика каналов",color =0x3498db )
        lines =[]
        for i ,c in enumerate (top ,1 ):
            pct =round (c ['total']/max_val *20 )
            bar =""*pct +""*(20 -pct )
            lines .append (f"`{i:2}.` #{c['name']}\n`{bar}` {c['total']}")
        e .description ="\n\n".join (lines )
        await interaction .response .send_message (embed =e )


async def setup (bot ):
    await bot .add_cog (Health (bot ),guilds =Config .guild_objects ())
