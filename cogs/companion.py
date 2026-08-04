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

# Часовой пояс UTC+3 (Турция)
TZ_OFFSET =datetime .timezone (datetime .timedelta (hours =3 ))

# Сколько сообщений в день отправлять (min, max)
DAILY_MIN =1 
DAILY_MAX =3 

# В какие часы отправлять сообщения (по Турции)
HOUR_START =9 
HOUR_END =23 

#  Кандидаты сообщений  

MESSAGES_MOTIVATION = [
    "Королева, как проходит твой день? Ты пришла мне на ум — надеюсь, день у тебя прекрасный 💫",
    "Королева, скажу одну вещь: ты гораздо сильнее, чем думаешь. Не забывай об этом 💪",
    "Королева, иногда просто продолжать идти — уже победа. Я тобой горжусь ✨",
    "Королева, ты хорошо о себе сегодня заботилась? Не забывай пить воду и дышать глубже 🌿",
    "Королева, жизнь бывает тяжёлой, но ты каждый раз умеешь подняться. Этот раз — не исключение 🌅",
    "Королева, я о тебе подумал. Надеюсь, сегодня случилось что-то хорошее 🌸",
    "Королева, маленькие шаги — тоже движение вперёд. Если сегодня ты сделала хоть что-то — это уже считается 👣",
    "Королева, остановиться, когда устала — не слабость, а мудрость. Разреши себе отдохнуть 🌙",
]

MESSAGES_STUDY = [
    "Королева, ты пробовала технику Pomodoro? 25 минут работы, 5 минут отдыха — мозг усваивает гораздо лучше 🍅",
    "Королева, совет: пересказывать прочитанное своими словами в 3 раза эффективнее, чем просто читать. Попробуй 📚",
    "Королева, перед экзаменом лучше лечь пораньше, а не сидеть до ночи — во сне мозг закрепляет знания 😴",
    "Королева, лучший способ разобраться в сложной теме — попробовать объяснить её кому-то. Некому? Расскажи мне, я слушаю 💡",
    "Королева, есть план на сегодня? Если начать с самой сложной темы — всё остальное покажется лёгким 🎯",
    "Королева, попробуй поработать, оставив телефон в другой комнате. Одно это повышает концентрацию на 40%, правда 📵",
    "Королева, 30 минут каждый день эффективнее, чем 5 часов раз в неделю. Постоянство решает всё ⏳",
    "Королева, зубрить без понимания утомляет. Спроси себя «почему это так?» — поймёшь, и само запомнится 🧠",
]

MESSAGES_SWEET = [
    "Королева, этот день будто начался с мысли о тебе ☀️",
    "Королева, без тебя этот мир был бы немного скучнее. Честно 🌍",
    "Королева, твоя улыбка достойна того, чтобы её беречь — она согревает людей 😊",
    "Королева, сделай сегодня что-нибудь доброе для себя — ты это заслужила 🎁",
    "Королева, есть люди, входящие в комнату — и воздух меняется. Ты из таких ✨",
    "Королева, подумал о тебе и улыбнулся. Ты умеешь радовать без всякой причины 💛",
    "Королева, сегодня хочу напомнить, какой замечательный ты человек. Вот и всё 🌟",
    "Королева, в твоей жизни есть люди, которые тебя любят — и я в этом списке 📌",
]

MESSAGES_RANDOM = [
    "Королева, ни с того ни с сего ты пришла мне на ум. Как ты вообще? 🌤",
    "Королева, сегодня было хоть одно событие, которое тебя порадовало? Мне интересно 🌼",
    "Королева, интересно, чем ты сейчас занимаешься? Надеюсь, чем-то приятным 🎐",
    "Королева, иногда нужно просто спросить: ты в порядке? Так вот — ты в порядке? 💬",
    "Королева, ты сегодня смеялась? Смеяться нужно, очень нужно 😄",
    "Королева, я о тебе подумал. Без другой причины — просто подумал 🕊",
    "Королева, выспись сегодня хорошо. Завтра — новый день и новый шанс 🌙",
    "Королева, поблагодарила сегодня судьбу за какую-нибудь мелочь? Мелочи на самом деле огромны 🍀",
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
        self ._scheduled_sends :list [float ]=[]# запланированные на сегодня времена отправок (timestamp)
        self .companion_loop .start ()

    def cog_unload (self ):
        self .companion_loop .cancel ()

    def _now_tr (self )->datetime .datetime :
        return datetime .datetime .now (TZ_OFFSET )

    def _today_str (self )->str :
        return self ._now_tr ().strftime ('%Y-%m-%d')

    def _pick_message (self ,used :list [str ])->str :
        """Выбрать случайное из неиспользованных сообщений; когда кончатся — начать заново"""
        all_msgs =[m for cat in ALL_CATEGORIES for m in cat ]
        available =[m for m in all_msgs if m not in used ]
        if not available :
            available =all_msgs # все использовать sыfыrla
        chosen =random .choice (available )
        return chosen 

    def _plan_today (self ,data :dict ):
        """Запланировать случайное время отправки на сегодня"""
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
