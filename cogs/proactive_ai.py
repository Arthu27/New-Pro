"""Проактивный AI — бот сам размышляет и пишет Артуру в ЛС"""
import discord 
from discord .ext import commands ,tasks 
import datetime 
import os 
import json 

from logger import get_logger 
log =get_logger ("proactive_ai")


OWNER_ID =int (os .getenv ('OWNER_ID')or '0')
DATA_FILE ='data/proactive_ai.json'

# Предупреждение eшikleri
LEAVE_ALERT_THRESHOLD =3 # 1 времяte bu kadar человек ayrыlыrsa uyar
JOIN_ALERT_THRESHOLD =10 # 1 времяte bu kadar человек katыlыrsa uyar (raid?)
WARN_ALERT_THRESHOLD =3 # 1 времяte bu kadar предупреждение verilirse uyar


def _load ()->dict :
    if os .path .exists (DATA_FILE ):
        try :
            with open (DATA_FILE ,'r',encoding ='utf-8')as f :
                return json .load (f )
        except Exception :
            pass 
    return {'last_morning':None ,'last_check':None ,'asked_today':[],
    'leave_log':[],'join_log':[],'warn_log':[]}


def _save (data :dict ):
    os .makedirs ('data',exist_ok =True )
    with open (DATA_FILE ,'w',encoding ='utf-8')as f :
        json .dump (data ,f ,ensure_ascii =False ,indent =2 )


class ProactiveAI (commands .Cog ):
    def __init__ (self ,bot ):
        self .bot =bot 
        self .proactive_loop .start ()

    def cog_unload (self ):
        self .proactive_loop .cancel ()

    async def _send_to_owner (self ,message :str ):
        """Arthur'a DM at"""
        if not OWNER_ID :
            return 
        try :
            owner =await self .bot .fetch_user (OWNER_ID )
            await owner .send (message )
        except Exception as e :
            log .info (f'[ProactiveAI] DM Ошибки: {e}')

    async def _think_and_ask (self ):
        """Бот размышляет и при нужде спрашивает Артура"""
        if not OWNER_ID :
            return 

        data =_load ()
        now =datetime .datetime .now ()
        today =now .strftime ('%Y-%m-%d')
        asked_today =data .get ('asked_today',[])

        # Ежедневный sыfыrla
        if data .get ('last_date')!=today :
            data ['asked_today']=[]
            data ['last_date']=today 
            asked_today =[]

            # Sabah сообщение (09:00-09:30) - отключено
            # if now.hour == 9 and now.minute < 30 and 'morning' заметок in asked_today:
            #     from web.ai_helper import _call_text
            #     # Сервер statusunu al
            #     guild_info = []
            #     for guild in self.bot.guilds:
            #         guild_info.append(f"{guild.name}: {guild.member_count} участник")

            #     morning_msg = _call_text([
            #         {'role': 'system', 'content': (
            #             'Sen Aether, Артуров Discord-бот. '
            #             'Sabah Arthur\'a краткий, samimi bir день сообщение yaz. '
            #             'Сервер statusunu belirt, сегодня для bir что-то sormak istiyorsan sor. '
            #             'Maksimum 3 cюmle. Emoji использовать.'
            #         )},
            #         {'role': 'user', 'content': f'Сервера: {", ".join(guild_info)}. Сегодня {now.strftime("%A, %d %B")}. Sabah сообщение yaz.'}
            #     ], max_tokens=150)

            #     await self._send_to_owner(morning_msg)
            #     asked_today.append('morning')
            #     data['asked_today'] = asked_today
            #     _save(data)
            #     return

            # Akшam сводка (21:00-21:30)
        if now .hour ==21 and now .minute <30 and 'evening'not in asked_today :
            from web .ai_helper import _call_text 

            # Сервер aktivitesini собрать
            stats =[]
            for guild in self .bot .guilds :
                stats .append (f"{guild.name}: {guild.member_count} участник")

            evening_msg =_call_text ([
            {'role':'system','content':(
            'Sen Aether, Артуров Discord-бот. '
            'Вечером напиши Артуру короткую сводку. '
            'Спроси, как прошёл день, и поинтересуйся планами на завтра. '
            'Максимум 3 предложения. Тепло и естественно.'
            )},
            {'role':'user','content':f'Сервер: {", ".join(stats)}. Напиши вечернюю сводку.'}
            ],max_tokens =150 )

            await self ._send_to_owner (evening_msg )
            asked_today .append ('evening')
            data ['asked_today']=asked_today 
            _save (data )
            return 

            # Rastgele merak sorusu — отключено (gereksiz API чaгrыsы)
            # if 12 <= now.hour <= 20 and 'random' заметок in asked_today:
            #     pass

    @tasks .loop (minutes =15 )
    async def proactive_loop (self ):
        """Каждый 15 minutesda сервер analiz et, gerekirse uyar"""
        await self ._think_and_ask ()
        await self ._check_anomalies ()

    @proactive_loop .before_loop 
    async def before_loop (self ):
        await self .bot .wait_until_ready ()

    async def _check_anomalies (self ):
        """Сервер anomalilerini определить ve Arthur'a bildir"""
        if not OWNER_ID :
            return 
        data =_load ()
        now =datetime .datetime .now ()
        now_ts =now .timestamp ()
        one_hour_ago =now_ts -3600 
        alerts =[]

        # В конец 1 времяteki ayrыlmalarы контроль et
        leave_log =[t for t in data .get ('leave_log',[])if t >one_hour_ago ]
        if len (leave_log )>=LEAVE_ALERT_THRESHOLD :
            alerts .append (f'🚪 За последний час сервер покинули **{len(leave_log)} человек**!')
            data ['leave_log']=[]# Sыfыrla, tekrar uyarma

            # В конец 1 времяteki katыlыmlarы контроль et
        join_log =[t for t in data .get ('join_log',[])if t >one_hour_ago ]
        if len (join_log )>=JOIN_ALERT_THRESHOLD :
            alerts .append (f'🚨 За последний час присоединились **{len(join_log)} участников** — похоже на рейд!')
            data ['join_log']=[]

        if alerts :
            msg ='**🤖 J.A.R.V.I.S. — тревога**\n'+'\n'.join (alerts )
            await self ._send_to_owner (msg )

        data ['leave_log']=[t for t in data .get ('leave_log',[])if t >one_hour_ago ]
        data ['join_log']=[t for t in data .get ('join_log',[])if t >one_hour_ago ]
        _save (data )

    @commands .Cog .listener ()
    async def on_member_join (self ,member :discord .Member ):
        """Логировать входы"""
        data =_load ()
        data .setdefault ('join_log',[]).append (datetime .datetime .now ().timestamp ())
        data ['join_log']=data ['join_log'][-50 :]
        _save (data )

    @commands .Cog .listener ()
    async def on_member_remove (self ,member :discord .Member ):
        """Логировать выходы и сообщить Артуру"""
        data =_load ()
        data .setdefault ('leave_log',[]).append (datetime .datetime .now ().timestamp ())
        data ['leave_log']=data ['leave_log'][-50 :]
        _save (data )
        # Anlыk уведомление
        if OWNER_ID :
            try :
                owner =await self .bot .fetch_user (OWNER_ID )
                await owner .send (
                f' **{member.display_name}** `{member.guild.name}` сервер покинул.'
                )
            except Exception :
                pass 


async def setup (bot ):
    await bot .add_cog (ProactiveAI (bot ))
