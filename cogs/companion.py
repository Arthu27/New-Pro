"""
Companion Cog — Bot, belirli bir userya ara очередь kendi желание DM atar.
Сообщения samimi, motive edici, личный. Hitap: "Королева".
"""
import discord 
from discord .ext import commands 
from config import Config 
from discord .ext import tasks 
import datetime 
import os 
import json 
import random 
import asyncio 

from logger import get_logger 
log =get_logger ("companion")


# Цель user ID
COMPANION_USER_ID =Config .COMPANION_USER_ID 

DATA_FILE ='data/companion_state.json'

# Tюrkiye час UTC+3
TZ_OFFSET =datetime .timezone (datetime .timedelta (hours =3 ))

# День сколько message отправл (min, max)
DAILY_MIN =1 
DAILY_MAX =3 

# Сообщение отправл часов aralыгы (Tюrkiye час)
HOUR_START =9 
HOUR_END =23 

#  Сообщение Кандидатыu 

MESSAGES_MOTIVATION =[
"Королева, сегодня как? Aklыma geldin, umarыm день gюzel geчiyordur ",
"Королева, bir что-то сказатьyeyim mi — sen dюшюndюгюnden очень более мощный. Bunu unutma ",
"Королева, bazen только продолжить etmek bile baшlы baшыna bir успешно. Gurur duyuyorum senden ",
"Королева, сегодня kendine iyi baktыn mы? Su iчmeyi, biraz nefes almayы unutma ",
"Королева, hayat bazen тяжелый gelir ama sen каждый seferinde kalkmasыnы biliyorsun. Bu очередь bir что-то не ",
"Королева, seni dюшюndюm. Umarыm сегодня sana gюzel bir что-то olmuшtur ",
"Королева, маленький adыmlar da ilerlemektir. Сегодня ne kadar маленький olursa olsun bir что-то yaptыysan, bu число ",
"Королева, yorulduгunda durmak zayыflыk не, akыllыlыktыr. Kendine Разрешение ver ",
]

MESSAGES_STUDY =[
"Королева, ders чalышыrken Pomodoro tekniгini denedin mi? 25 minutes чalыш, 5 minutes mola — beyin очень более iyi absorbe ediyor ",
"Королева, подсказка: записывать прочитанное своими словами в 3 раза эффективнее, чем просто читать. Попробуй ",
"Королева, sыnav ёncesi gece geч времяe kadar работать вместо erken yat, sabah taze kafayla bak — beyin uyku очередь infoyi pekiшtiriyor ",
"Королева, сложный bir konuyu ёгrenmenin en iyi yolu onu birine anlatmaya работать. Кто yoksa bana anlat, dinlerim ",
"Королева, сегодня работа planыn есть mы? До en сложный konudan baшlarsan, geri осталосьы очень более легкий gelir ",
"Королева, telefonu baшka комната bыrakarak работа dene. Только bu bile konsantrasyonu %40 artыrыyor, inanыlmaz не mi? ",
"Королева, каждый день только 30 minutes dюzenli работать, неделяda bir kez 5 часов работать очень более etkili. Tutarlыlыk каждый что-тоdir ",
"Королева, bir konuyu anlamadan ezberlemek seni yorar. До 'почему bёyle?' diye sor, anlayыnca zaten aklыnda kполучает ",
]

MESSAGES_SWEET =[
"Королева, сегодня день seni dюшюnerek doгdu sanki ",
"Королева, sen olmasan bu вчера biraz более очередь olurdu. Gerчekten ",
"Королева, твоя улыбка заслуживает записи, она согревает людей ",
"Королева, сегодня kendine bir iyilik yap — hak ediyorsun ",
"Королева, bazы insanlar комната girince hava deгiшir. Sen ёyle birisin ",
"Королева, seni dюшюndюm ve gюlюmsedim. Причина yere iyi hissettiriyorsun ",
"Королева, сегодня ne kadar harika biri olduгunu hatыrlatmak желание. Все bu ",
"Королева, hayatыnda seni seven insanlar есть — ve ben de число bu listeye ",
]

MESSAGES_RANDOM =[
"Королева, центрda hiчbir что-то yokken aklыma geldin. Как gerчekten? ",
"Королева, сегодня bir что-то seni mutlu etti mi? Merak ettim ",
"Королева, шu an ne yapыyorsun acaba? Umarыm gюzel bir что-тоler ",
"Королева, bazen только 'iyi misin?' demek gerekiyor. Иyi misin? ",
"Королева, сегодня kendine gюldюn mю? Gюlmek lazыm, очень lazыm ",
"Королева, seni dюшюndюm. Baшka bir причина нет, только dюшюndюm ",
"Королева, bu gece iyi uyu. Завтра новый bir день, новый bir шans ",
"Королева, сегодня маленький bir что-тоe шюkrettin mi? Маленький что-тоler aslыnda большой ",
]

ALL_CATEGORIES =[
MESSAGES_MOTIVATION ,
MESSAGES_STUDY ,
MESSAGES_SWEET ,
MESSAGES_RANDOM ,
]

#  State 

def _load ()->dict :
    if os .path .exists (DATA_FILE ):
        try :
            with open (DATA_FILE ,'r',encoding ='utf-8')as f :
                return json .load (f )
        except Exception :
            pass 
    return {'last_date':None ,'sent_today':0 ,'used_messages':[]}


def _save (data :dict ):
    os .makedirs ('data',exist_ok =True )
    with open (DATA_FILE ,'w',encoding ='utf-8')as f :
        json .dump (data ,f ,ensure_ascii =False ,indent =2 )


        #  Cog 

class Companion (commands .Cog ):
    def __init__ (self ,bot :commands .Bot ):
        self .bot =bot 
        self ._scheduled_sends :list [float ]=[]# сегодняkю planlы отправл vakitlarы (timestamp)
        self .companion_loop .start ()

    def cog_unload (self ):
        self .companion_loop .cancel ()

    def _now_tr (self )->datetime .datetime :
        return datetime .datetime .now (TZ_OFFSET )

    def _today_str (self )->str :
        return self ._now_tr ().strftime ('%Y-%m-%d')

    def _pick_message (self ,used :list [str ])->str :
        """Использовать messagelardan rastgele выбрать, tюkenirse sыfыrla"""
        all_msgs =[m for cat in ALL_CATEGORIES for m in cat ]
        available =[m for m in all_msgs if m not in used ]
        if not available :
            available =all_msgs # все использовать sыfыrla
        chosen =random .choice (available )
        return chosen 

    def _plan_today (self ,data :dict ):
        """Сегодня для rastgele отправл vakitlarы planla"""
        now =self ._now_tr ()
        count =random .randint (DAILY_MIN ,DAILY_MAX )
        times =[]
        for _ in range (count ):
            hour =random .randint (HOUR_START ,HOUR_END -1 )
            minute =random .randint (0 ,59 )
            send_time =now .replace (hour =hour ,minute =minute ,second =0 ,microsecond =0 )
            # История времяleri сегодня для atla
            if send_time >now :
                times .append (send_time .timestamp ())
        self ._scheduled_sends =sorted (times )
        data ['plan']=self ._scheduled_sends 
        data ['sent_today']=0 

    async def _send_dm (self ,message :str ):
        try :
            user =await self .bot .fetch_user (COMPANION_USER_ID )
            await user .send (message )
            log .info (f'[Companion] DM отправлено → {user.name}')
        except discord .Forbidden :
            log .info ('[Companion] DM отправл — user DM\'leri закрыт.')
        except Exception as e :
            log .info (f'[Companion] Ошибка: {e}')

    @tasks .loop (minutes =5 )
    async def companion_loop (self ):
        data =_load ()
        today =self ._today_str ()
        now_ts =self ._now_tr ().timestamp ()

        # Новый день → planla
        if data .get ('last_date')!=today :
            data ['last_date']=today 
            data ['used_messages']=data .get ('used_messages',[])[-20 :]# son 20'yi tut
            self ._plan_today (data )
            _save (data )
            return 

            # Planlы vakitlarы загрузить (restart sonrasы)
        if not self ._scheduled_sends and data .get ('plan'):
            self ._scheduled_sends =data ['plan']

            # Отправл vakit geldi mi?
        due =[t for t in self ._scheduled_sends if t <=now_ts ]
        if not due :
            return 

            # Отправить
        for ts in due :
            self ._scheduled_sends .remove (ts )
            msg =self ._pick_message (data .get ('used_messages',[]))
            data .setdefault ('used_messages',[]).append (msg )
            data ['sent_today']=data .get ('sent_today',0 )+1 
            data ['plan']=self ._scheduled_sends 
            _save (data )
            await self ._send_dm (msg )
            await asyncio .sleep (2 )# rate limit доверие

    @companion_loop .before_loop 
    async def before_loop (self ):
        await self .bot .wait_until_ready ()
        # Первый запуск сегодня planlanmamышsa planla
        data =_load ()
        today =self ._today_str ()
        if data .get ('last_date')!=today :
            data ['last_date']=today 
            self ._plan_today (data )
            _save (data )
        elif data .get ('plan'):
            self ._scheduled_sends =data ['plan']


async def setup (bot :commands .Bot ):
    await bot .add_cog (Companion (bot ))
