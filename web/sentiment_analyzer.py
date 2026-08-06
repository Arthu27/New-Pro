"""
Анализ настроения сервера в реальном времени
Отслеживание эмоций, тона, конфликтов
"""
import discord 
import json 
import os 
from datetime import datetime ,timedelta 
from typing import Dict ,List ,Optional ,Tuple 
from collections import defaultdict 
import re 


class SentimentAnalyzer :
    """Analizёr duygu сервер"""

    # Kalыplar для opredeleniya duygular
    EMOTION_PATTERNS ={
    'positive':[
    r'\b(teшekkюrler|blagodaryu|отлично|kruto|супер|klass|zdorovo|prekrasno|zamesohbettelno)\b',
    r'\b(хорошо|normal|ok|oky|ladno|ponyal|prinyal)\b',
    r'\b(lyublyu|nravitsya|obojayu|kayf|vostorg)\b',
    r'\b(rad|rada|scastliv|scastliva|dovolen|dovolna)\b',
    r'[:\)]+|[:D]+|[❤️💖😊😄🎉👍]+',
    ],
    'negative':[
    r'\b(besit|zlyus|nenaviju|razdrajaet|dostalo|zadolbalo)\b',
    r'\b(kёtю|ujasno|otvratitelno|kosmar|jvar)\b',
    r'\b(grustno|pecalno|tosklivo|biroko|depressiya)\b',
    r'\b(ustal|ustala|vimotalsya|vimotalas|bez удалить)\b',
    r'\b(aptal|aptal|aptal|aptal|durak)\b',
    r'[:\(]+|[:\[]+|[😢😭😡🤬💔👎]+',
    ],
    'neutral':[
    r'\b(вопрос|podskajite|obyasnite|rasskajite)\b',
    r'\b(interesno|lyubopitno|hm|hmm)\b',
    ],
    }

    # Vesovie koefficienti для duygular
    EMOTION_WEIGHTS ={
    'positive':1.0 ,
    'negative':-1.0 ,
    'neutral':0.0 ,
    }

    def __init__ (self ):
        self .message_buffer =defaultdict (list )# channel_id -> messages
        self .sentiment_cache ={}# channel_id -> sentiment_data
        self .alerts_sent =set ()# Predotvrasenie spama предупреждение

        # Загруз история
        self ._load_history ()

    def analyze_message (self ,message :discord .Message )->Dict :
        """Analiz ediyor bir сообщение"""
        content =message .content .lower ()

        # Belirliyoruz duygular
        emotions =self ._detect_emotions (content )

        # Belirliyoruz dominiruyusuyu emociyu
        dominant =max (emotions ,key =emotions .get )if emotions else 'neutral'

        # Hesaplыyoruz skor
        score =sum (
        emotions [emotion ]*self .EMOTION_WEIGHTS [emotion ]
        for emotion in emotions 
        )

        result ={
        'message_id':message .id ,
        'author_id':message .author .id ,
        'author_name':str (message .author ),
        'channel_id':message .channel .id ,
        'channel_name':message .channel .name ,
        'content':message .content [:200 ],# Ограничиваем длинныйluгu
        'emotions':emotions ,
        'dominant_emotion':dominant ,
        'sentiment_score':score ,
        'timestamp':datetime .utcnow ().isoformat (),
        }

        # Ekliyoruz в pano
        self .message_buffer [message .channel .id ].append (result )

        # Ограничиваем pano
        if len (self .message_buffer [message .channel .id ])>100 :
            self .message_buffer [message .channel .id ]=self .message_buffer [message .channel .id ][-100 :]

        return result 

    def _detect_emotions (self ,content :str )->Dict [str ,float ]:
        """Opredelyaet duygular в metine"""
        emotions ={'positive':0.0 ,'negative':0.0 ,'neutral':0.0 }

        for emotion ,patterns in self .EMOTION_PATTERNS .items ():
            for pattern in patterns :
                matches =len (re .findall (pattern ,content ,re .IGNORECASE ))
                emotions [emotion ]+=matches 

                # Normalizuem
        total =sum (emotions .values ())
        if total >0 :
            emotions ={k :v /total for k ,v in emotions .items ()}

        return emotions 

    def get_channel_sentiment (self ,channel_id :int ,window_minutes :int =60 )->Dict :
        """Alыyor duygu канал для son N dakika"""
        messages =self .message_buffer .get (channel_id ,[])

        # Filtreliyoruz по время
        cutoff =datetime .utcnow ()-timedelta (minutes =window_minutes )
        recent =[
        msg for msg in messages 
        if datetime .fromisoformat (msg ['timestamp'])>cutoff 
        ]

        if not recent :
            return {
            'channel_id':channel_id ,
            'message_count':0 ,
            'avg_sentiment':0.0 ,
            'dominant_emotion':'neutral',
            'emotion_breakdown':{'positive':0 ,'negative':0 ,'neutral':0 },
            'trend':'stable'
            }

            # Hesaplыyoruz ortalama duygu
        avg_sentiment =sum (msg ['sentiment_score']for msg in recent )/len (recent )

        # Podscitivaem duygular
        emotion_counts ={'positive':0 ,'negative':0 ,'neutral':0 }
        for msg in recent :
            emotion_counts [msg ['dominant_emotion']]+=1 

            # Belirliyoruz trend (sravnivaem pervuyu ve vtoruyu polovinu)
        mid =len (recent )//2 
        if mid >0 :
            first_half_avg =sum (msg ['sentiment_score']for msg in recent [:mid ])/mid 
            second_half_avg =sum (msg ['sentiment_score']for msg in recent [mid :])/(len (recent )-mid )

            if second_half_avg >first_half_avg +0.1 :
                trend ='improving'
            elif second_half_avg <first_half_avg -0.1 :
                trend ='declining'
            else :
                trend ='stable'
        else :
            trend ='stable'

        result ={
        'channel_id':channel_id ,
        'message_count':len (recent ),
        'avg_sentiment':round (avg_sentiment ,2 ),
        'dominant_emotion':max (emotion_counts ,key =emotion_counts .get ),
        'emotion_breakdown':emotion_counts ,
        'trend':trend 
        }

        # Kesiruem
        self .sentiment_cache [channel_id ]=result 

        return result 

    def get_server_sentiment (self ,guild :discord .Guild ,window_minutes :int =60 )->Dict :
        """Alыyor общий duygu сервер"""
        channel_sentiments =[]

        for channel in guild .text_channels :
            sentiment =self .get_channel_sentiment (channel .id ,window_minutes )
            if sentiment ['message_count']>0 :
                channel_sentiments .append (sentiment )

        if not channel_sentiments :
            return {
            'guild_id':guild .id ,
            'guild_name':guild .name ,
            'total_messages':0 ,
            'avg_sentiment':0.0 ,
            'dominant_emotion':'neutral',
            'mood':'neutral',
            'channels':{}
            }

            # Hesaplыyoruz ortalama по на сервер
        total_messages =sum (s ['message_count']for s in channel_sentiments )
        avg_sentiment =sum (
        s ['avg_sentiment']*s ['message_count']for s in channel_sentiments 
        )/total_messages 

        # Belirliyoruz общий duygu
        if avg_sentiment >0.3 :
            mood ='very_positive'
        elif avg_sentiment >0.1 :
            mood ='positive'
        elif avg_sentiment <-0.3 :
            mood ='very_negative'
        elif avg_sentiment <-0.1 :
            mood ='negative'
        else :
            mood ='neutral'

            # Topluyoruz duygular
        total_emotions ={'positive':0 ,'negative':0 ,'neutral':0 }
        for s in channel_sentiments :
            for emotion ,count in s ['emotion_breakdown'].items ():
                total_emotions [emotion ]+=count 

        return {
        'guild_id':guild .id ,
        'guild_name':guild .name ,
        'total_messages':total_messages ,
        'avg_sentiment':round (avg_sentiment ,2 ),
        'dominant_emotion':max (total_emotions ,key =total_emotions .get ),
        'mood':mood ,
        'channels':{s ['channel_id']:s for s in channel_sentiments }
        }

    async def check_for_alerts (self ,guild :discord .Guild )->List [Dict ]:
        """Контроль ediyor nujni ли предупреждение о nastroenii"""
        alerts =[]

        for channel in guild .text_channels :
            sentiment =self .get_channel_sentiment (channel .id ,window_minutes =30 )

            # Предупреждение если очень negativnoe duygu
            if sentiment ['avg_sentiment']<-0.5 and sentiment ['message_count']>=5 :
                alert_key =f"{channel.id}_negative"
                if alert_key not in self .alerts_sent :
                    alerts .append ({
                    'type':'negative_sentiment',
                    'channel_id':channel .id ,
                    'channel_name':channel .name ,
                    'sentiment':sentiment ['avg_sentiment'],
                    'message_count':sentiment ['message_count'],
                    'message':f"⚠️ Negativnoe duygu в #{channel.name} ({sentiment['avg_sentiment']})"
                    })
                    self .alerts_sent .add (alert_key )

                    # Sbrasivaem предупреждение с 10 dakika
                    import asyncio 
                    asyncio .create_task (self ._reset_alert (alert_key ,delay =600 ))

                    # Предупреждение если чakышma (очень negativa для korotkoe время)
            recent_10min =self .get_channel_sentiment (channel .id ,window_minutes =10 )
            if recent_10min ['emotion_breakdown']['negative']>=5 :
                alert_key =f"{channel.id}_conflict"
                if alert_key not in self .alerts_sent :
                    alerts .append ({
                    'type':'potential_conflict',
                    'channel_id':channel .id ,
                    'channel_name':channel .name ,
                    'negative_messages':recent_10min ['emotion_breakdown']['negative'],
                    'message':f"🔥 Vozmojniy чakышma в #{channel.name} ({recent_10min['emotion_breakdown']['negative']} negativnih сообщение)"
                    })
                    self .alerts_sent .add (alert_key )
                    asyncio .create_task (self ._reset_alert (alert_key ,delay =300 ))

        return alerts 

    async def _reset_alert (self ,alert_key :str ,delay :int ):
        """Sbrasivaet предупреждение с N saniye"""
        import asyncio 
        await asyncio .sleep (delay )
        self .alerts_sent .discard (alert_key )

    def _load_history (self ):
        """Загруз история из dosyaya"""
        history_file ='data/sentiment_history.json'
        if os .path .exists (history_file ):
            try :
                with open (history_file ,'r',encoding ='utf-8')as f :
                    data =json .load (f )
                    for channel_id ,messages in data .items ():
                        self .message_buffer [int (channel_id )]=messages 
            except :
                pass 

    def _save_history (self ):
        """Сохран история в dosya"""
        try :
            os .makedirs ('data',exist_ok =True )
            history_file ='data/sentiment_history.json'

            # Сохран только son 50 сообщение на канал
            data ={
            str (channel_id ):messages [-50 :]
            for channel_id ,messages in self .message_buffer .items ()
            }

            with open (history_file ,'w',encoding ='utf-8')as f :
                json .dump (data ,f ,indent =2 ,ensure_ascii =False )
        except :
            pass 


            # Kюresel пример
_sentiment_analyzer =None 

def get_sentiment_analyzer ()->SentimentAnalyzer :
    """Alыyor kюresel пример SentimentAnalyzer"""
    global _sentiment_analyzer 
    if _sentiment_analyzer is None :
        _sentiment_analyzer =SentimentAnalyzer ()
    return _sentiment_analyzer 
