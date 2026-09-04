"""
RAG (Retrieval Augmented Generation) — поиск по базе информации сервера
AI может искать в правилах, FAQ, логах тикетов, документации
"""

from logger import get_logger

_log = get_logger("ai_rag")

import os 
import json 
import re 
from typing import List ,Dict ,Optional 
from datetime import datetime 


class KnowledgeBase :
    """База данных информации о сервере с поиском"""

    def __init__ (self ,guild_id :int ):
        self .guild_id =guild_id 
        self .documents =[]
        self ._load_documents ()

    def _load_documents (self ):
        """Загруз все dokumenti в pamyat"""
        # 1. Правила сервер (Особый правило yoksa Стандартные правила Hakumo загруз)
        rules_loaded =False 
        for rf in [f"data/rules_{self.guild_id}.json","data/rules.json"]:
            if os .path .exists (rf ):
                try :
                    with open (rf ,'r',encoding ='utf-8')as f :
                        rules_data =json .load (f )
                        for rule in rules_data .get ('rules',[]):
                            self .documents .append ({
                            'type':'rule',
                            'content':rule .get ('text',''),
                            'metadata':{'id':rule .get ('id',0 )}
                            })
                            rules_loaded =True 
                    if rules_loaded :
                        break 
                except Exception as _ex:
                    _log.debug("_load_documents(): подавлено: %s", _ex)
        if not rules_loaded :
            default_rules =[
            "Правило #1: Уважение и вежливость — Запрещены оскорбления, мат, унижения и язык вражды.",
            "Правило #2: Спам и Флуд — Запрещена массовая отправка сообщений, реклама и ссылки без разрешения.",
            "Правило #3: Голосовые каналы — Запрещено шуметь, включать посторонние звуки и мешать воспроизведению музыки.",
            "Правило #4: Решения администрации — Уважайте действия модераторов; обжалование наказаний проводится через тикеты.",
            "Правило #5: Конфиденциальность и безопасность — Запрещено распространение личных данных и вредоносных ссылок."
            ]
            for idx ,rtext in enumerate (default_rules ,1 ):
                self .documents .append ({
                'type':'rule',
                'content':rtext ,
                'metadata':{'id':idx }
                })

                # 2. FAQ (Изученные ответы из тикетов и команды /faq-learn)
        for faq_file in ['data/learned_faq.json','data/faq_learned.json']:
            if os .path .exists (faq_file ):
                try :
                    with open (faq_file ,'r',encoding ='utf-8')as f :
                        faq_data =json .load (f )
                    items =faq_data if isinstance (faq_data ,list )else faq_data .get (str (self .guild_id ),[])
                    for faq in items :
                        if isinstance (faq ,dict )and faq .get ('question')and faq .get ('answer'):
                            self .documents .append ({
                            'type':'faq',
                            'content':f"ВОПРОС: {faq.get('question', '')}\nОТВЕТ АДМИНИСТРАЦИИ: {faq.get('answer', '')}",
                            'metadata':{'id':faq .get ('id',''),'score':1.0 }
                            })
                except Exception as _ex:
                    _log.debug("_load_documents(): подавлено: %s", _ex)

                    # 3. Логи тикетов (последние 50)
        tickets_file =f"data/tickets_{self.guild_id}.json"
        if os .path .exists (tickets_file ):
            try :
                with open (tickets_file ,'r',encoding ='utf-8')as f :
                    tickets_data =json .load (f )
                    for ticket in tickets_data .get ('tickets',[])[-50 :]:
                    # Удалить anahtar momenti из ticketin
                        summary =f"Ticket: {ticket.get('category', '?')} — {ticket.get('status', '?')}"
                        if ticket .get ('summary'):
                            summary +=f"\n{ticket.get('summary', '')}"

                        self .documents .append ({
                        'type':'ticket',
                        'content':summary ,
                        'metadata':{
                        'user_id':ticket .get ('user_id',0 ),
                        'created_at':ticket .get ('created_at','')
                        }
                        })
            except Exception as _ex:
                _log.debug("_load_documents(): подавлено: %s", _ex)

                # 4. Пользователь notlar (из data/notes.json если есть)
        notes_file ='data/notes.json'
        if os .path .exists (notes_file ):
            try :
                with open (notes_file ,'r',encoding ='utf-8')as f :
                    notes_data =json .load (f )
                    guild_notes =notes_data .get (str (self .guild_id ),{})
                    for user_id ,notes in guild_notes .items ():
                        for note in notes :
                            self .documents .append ({
                            'type':'note',
                            'content':note .get ('text',''),
                            'metadata':{
                            'user_id':int (user_id ),
                            'author':note .get ('author','?'),
                            'timestamp':note .get ('timestamp','')
                            }
                            })
            except Exception as _ex:
                _log.debug("_load_documents(): подавлено: %s", _ex)

    def search (self ,query :str ,max_results :int =5 )->List [Dict ]:
        """Arama по tabanda информация (prostoy keyword-based)"""
        query_lower =query .lower ()
        query_words =set (re .findall (r'\w+',query_lower ))

        scored_docs =[]
        for doc in self .documents :
            content_lower =doc ['content'].lower ()

            # Podscet sovpadeniy
            matches =sum (1 for word in query_words if word in content_lower )

            if matches >0 :
            # Normalizovanniy skor
                score =matches /len (query_words )if query_words else 0 
                scored_docs .append ((score ,doc ))

                # Sortiruem по skoru
        scored_docs .sort (reverse =True ,key =lambda x :x [0 ])

        # Vozvrasaem en хорошо результат
        return [doc for score ,doc in scored_docs [:max_results ]]

    def get_context_for_query (self ,query :str )->str :
        """Получает контекст из релевантной информации для ответа на вопрос"""
        results =self .search (query ,max_results =3 )

        if not results :
            return ""

        context_parts =["БАЗА ЗНАНИЙ И ПРАВИЛА СЕРВЕРА:"]

        for i ,doc in enumerate (results ,1 ):
            doc_type =doc ['type']
            content =doc ['content'][:500 ]  # Ограничиваем длину

            if doc_type =='rule':
                context_parts .append (f"\n{i}. ПРАВИЛО СЕРВЕРА:\n{content}")
            elif doc_type =='faq':
                context_parts .append (f"\n{i}. ПОХОЖИЙ ОТВЕТ ИЗ FAQ:\n{content}")
            elif doc_type =='ticket':
                context_parts .append (f"\n{i}. РЕШЕНИЕ ИЗ ПРОШЛЫХ ТИКЕТОВ:\n{content}")
            elif doc_type =='note':
                context_parts .append (f"\n{i}. ЗАМЕТКА О ПОЛЬЗОВАТЕЛЕ:\n{content}")

        return "\n".join (context_parts )


class ConversationAnalyzer :
    """Анализатор разговора — извлекает важные факты"""

    @staticmethod 
    def extract_facts (messages :List [Dict ])->List [str ]:
        """Izvlekaet vajnie fakti из разговор"""
        facts =[]

        # Шаблоны для извлечения фактов
        patterns =[
        (r'menya zovut (\w+)','Имя пользователя: {}'),
        (r'mne (\d+) (?:let|god)','Возраст: {} лет'),
        (r'ya из ([\w\s]+?)(?:\.|,|$)','Город: {}'),
        (r'moy (?:discord|ds|takma имя):? ([\w#]+)','Discord: {}'),
        (r'(?:lyublyu|nravitsya|interesuyus) ([\w\s]+?)(?:\.|,|$)','Интересы: {}'),
        (r'работа ([\w\s]+?)(?:\.|,|$)','Работа: {}'),
        (r'ucus ([\w\s]+?)(?:\.|,|$)','Учёба: {}'),
        ]

        for msg in messages :
            content =msg .get ('content','')
            if msg .get ('role')!='user':
                continue 

            for pattern ,template in patterns :
                match =re .search (pattern ,content ,re .IGNORECASE )
                if match :
                    fact =template .format (match .group (1 ).strip ())
                    if fact not in facts :
                        facts .append (fact )

        return facts 

    @staticmethod 
    def detect_sentiment (messages :List [Dict ])->str :
        """Определяет настроение разговора"""
        positive_words =['спасибо','teşekkürler','отлично','супер','класс','помог','решил']
        negative_words =['бесит','злюсь','ненавижу','тупой','идиот','не работает','ошибка']

        all_text =' '.join ([msg .get ('content','')for msg in messages [-10 :]]).lower ()

        positive_count =sum (1 for word in positive_words if word in all_text )
        negative_count =sum (1 for word in negative_words if word in all_text )

        if positive_count >negative_count :
            return 'positive'
        elif negative_count >positive_count :
            return 'negative'
        else :
            return 'neutral'


            # Глобальный кэш базы знаний (чтобы не пересоздавать каждый раз)
_kb_cache :Dict [int ,KnowledgeBase ]={}


def get_knowledge_base (guild_id :int )->KnowledgeBase :
    """Получает базу данных информации о сервере (с кэшированием)"""
    if guild_id not in _kb_cache :
        _kb_cache [guild_id ]=KnowledgeBase (guild_id )
    return _kb_cache [guild_id ]


def refresh_knowledge_base (guild_id :int ):
    """Обновляет кэш определённой информации"""
    if guild_id in _kb_cache :
        del _kb_cache [guild_id ]
