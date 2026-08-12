"""
Самообучение — AI учится на своих ошибках и успехах
Анализ обратной связи, корректировка поведения
"""

from logger import get_logger

_log = get_logger("self_learning")

import json 
import os 
from datetime import datetime ,timedelta, timezone
from typing import Dict ,List ,Optional 
from collections import defaultdict 


class SelfLearning :
    """Система самообучения AI"""

    def __init__ (self ):
        self .feedback_log =[]# журнал обратной связи
        self .learned_patterns ={}# Viucennie kalыplar
        self .mistakes =[]# Ошибки AI
        self .successes =[]# Uspesnie cevaplar

        # Загрузить данные
        self ._load_data ()

    def record_feedback (
    self ,
    user_message :str ,
    ai_response :str ,
    feedback_type :str ,
    feedback_details :Dict =None 
    ):
        """Сохран obratnuyu ссылка"""
        entry ={
        'timestamp':datetime.now(timezone.utc).replace(tzinfo=None).isoformat (),
        'user_message':user_message ,
        'ai_response':ai_response ,
        'feedback_type':feedback_type ,# 'positive', 'negative', 'correction'
        'details':feedback_details or {}
        }

        self .feedback_log .append (entry )

        # Ограничиваем лог
        if len (self .feedback_log )>1000 :
            self .feedback_log =self .feedback_log [-1000 :]

            # Analiz ediyoruz ve obucaemsya
        self ._analyze_and_learn (entry )

        # Сохран
        self ._save_data ()

    def record_mistake (
    self ,
    user_message :str ,
    ai_response :str ,
    correct_response :str ,
    mistake_type :str 
    ):
        """Сохран ошибка AI"""
        mistake ={
        'timestamp':datetime.now(timezone.utc).replace(tzinfo=None).isoformat (),
        'user_message':user_message ,
        'wrong_response':ai_response ,
        'correct_response':correct_response ,
        'mistake_type':mistake_type # 'wrong_info', 'inappropriate', 'misunderstanding'
        }

        self .mistakes .append (mistake )

        # Ограничиваем
        if len (self .mistakes )>500 :
            self .mistakes =self .mistakes [-500 :]

            # Ucimsya на osibke
        self ._learn_from_mistake (mistake )

        # Сохран
        self ._save_data ()

    def record_success (
    self ,
    user_message :str ,
    ai_response :str ,
    success_type :str 
    ):
        """Сохран uspesniy ответ"""
        success ={
        'timestamp':datetime.now(timezone.utc).replace(tzinfo=None).isoformat (),
        'user_message':user_message ,
        'ai_response':ai_response ,
        'success_type':success_type # 'helpful', 'accurate', 'empathetic'
        }

        self .successes .append (success )

        # Ограничиваем
        if len (self .successes )>500 :
            self .successes =self .successes [-500 :]

            # Ucimsya на uspehe
        self ._learn_from_success (success )

        # Сохран
        self ._save_data ()

    def _analyze_and_learn (self ,feedback :Dict ):
        """Analiz ediyor obratnuyu ссылка ve obucaetsya"""
        feedback_type =feedback ['feedback_type']

        if feedback_type =='negative':
        # Negativnaya obratnaya ссылка — ucimsya izbegat
            self ._learn_from_mistake ({
            'user_message':feedback ['user_message'],
            'wrong_response':feedback ['ai_response'],
            'correct_response':feedback .get ('details',{}).get ('suggested_response',''),
            'mistake_type':'negative_feedback'
            })

        elif feedback_type =='positive':
        # Pozitivnaya obratnaya ссылка — zapominaem ne работает
            self ._learn_from_success ({
            'user_message':feedback ['user_message'],
            'ai_response':feedback ['ai_response'],
            'success_type':'positive_feedback'
            })

        elif feedback_type =='correction':
        # Korrektirovka — zapominaem правил ответ
            correct_response =feedback .get ('details',{}).get ('correction','')
            if correct_response :
                self ._learn_from_mistake ({
                'user_message':feedback ['user_message'],
                'wrong_response':feedback ['ai_response'],
                'correct_response':correct_response ,
                'mistake_type':'correction'
                })

    def _learn_from_mistake (self ,mistake :Dict ):
        """Ucitsya на osibke"""
        user_msg =mistake ['user_message'].lower ()
        wrong_resp =mistake ['wrong_response']
        correct_resp =mistake .get ('correct_response','')
        mistake_type =mistake ['mistake_type']

        # Удалить anahtar словоler
        keywords =self ._extract_keywords (user_msg )

        # Zapominaem pattern
        pattern_key =f"avoid_{mistake_type}"
        if pattern_key not in self .learned_patterns :
            self .learned_patterns [pattern_key ]=[]

        self .learned_patterns [pattern_key ].append ({
        'keywords':keywords ,
        'wrong_response':wrong_resp [:200 ],# Ограничиваем длинныйluгu
        'correct_response':correct_resp [:200 ]if correct_resp else '',
        'timestamp':mistake ['timestamp']
        })

        # Ограничиваем kalыplar
        if len (self .learned_patterns [pattern_key ])>100 :
            self .learned_patterns [pattern_key ]=self .learned_patterns [pattern_key ][-100 :]

    def _learn_from_success (self ,success :Dict ):
        """Ucitsya на uspehe"""
        user_msg =success ['user_message'].lower ()
        ai_resp =success ['ai_response']
        success_type =success ['success_type']

        # Удалить anahtar словоler
        keywords =self ._extract_keywords (user_msg )

        # Zapominaem pattern
        pattern_key =f"repeat_{success_type}"
        if pattern_key not in self .learned_patterns :
            self .learned_patterns [pattern_key ]=[]

        self .learned_patterns [pattern_key ].append ({
        'keywords':keywords ,
        'response':ai_resp [:200 ],# Ограничиваем длинныйluгu
        'timestamp':success ['timestamp']
        })

        # Ограничиваем kalыplar
        if len (self .learned_patterns [pattern_key ])>100 :
            self .learned_patterns [pattern_key ]=self .learned_patterns [pattern_key ][-100 :]

    def _extract_keywords (self ,text :str )->List [str ]:
        """Извлекает ключевые слова из текста"""
        import re 

        # Удален stop-словоler
        stop_words ={
        've','в','на','с','по','для','из','do','из','e','u',
        'the','a','an','and','or','but','in','on','at','to','for'
        }

        # Удалить словоler
        words =re .findall (r'\b\w+\b',text .lower ())

        # Filtreliyoruz
        keywords =[w for w in words if len (w )>2 and w not in stop_words ]

        # Удален dublikati
        return list (set (keywords ))

    def get_learning_context (self ,user_message :str )->str :
        """Получает контекст обучения для промпта"""
        user_msg_lower =user_message .lower ()
        keywords =self ._extract_keywords (user_msg_lower )

        if not keywords :
            return ""

        context_parts =[]

        # Ищем pohojie kalыplar
        for pattern_type ,patterns in self .learned_patterns .items ():
            matching_patterns =[]

            for pattern in patterns [-20 :]:# В конец 20
            # Контроль ediyoruz peresecenie anahtarevih slov
                pattern_keywords =set (pattern ['keywords'])
                message_keywords =set (keywords )
                intersection =pattern_keywords &message_keywords 

                if len (intersection )>=2 :# Minimum 2 obsih словоler
                    matching_patterns .append (pattern )

            if matching_patterns :
                if pattern_type .startswith ('avoid_'):
                # Kalыplar kotorih необходимо izbegat
                    context_parts .append (
                    "\n⚠️ ИЗБЕГАЙ похожих ответов (прежние ошибки):\n"
                    )
                    for p in matching_patterns [:3 ]:# Maksimum 3
                        if p .get ('wrong_response'):
                            context_parts .append (f"- {p['wrong_response']}\n")
                        if p .get ('correct_response'):
                            context_parts .append (f"+ Vmesto: {p['correct_response']}\n")

                elif pattern_type .startswith ('repeat_'):
                # Kalыplar kotorie необходимо povtoryat
                    context_parts .append (
                    "\n✅ ISPOLZUY podobnie cevaplar (idi uspesni):\n"
                    )
                    for p in matching_patterns [:3 ]:# Maksimum 3
                        if p .get ('response'):
                            context_parts .append (f"- {p['response']}\n")

        return ''.join (context_parts )

    def get_learning_stats (self )->Dict :
        """Получает статистику обучения"""
        return {
        'total_feedback':len (self .feedback_log ),
        'total_mistakes':len (self .mistakes ),
        'total_successes':len (self .successes ),
        'learned_patterns':sum (len (p )for p in self .learned_patterns .values ()),
        'pattern_types':list (self .learned_patterns .keys ()),
        'recent_mistakes':self .mistakes [-5 :]if self .mistakes else [],
        'recent_successes':self .successes [-5 :]if self .successes else [],
        }

    def _load_data (self ):
        """Загрузить данные из файла"""
        data_file ='data/ai_learning.json'
        if os .path .exists (data_file ):
            try :
                with open (data_file ,'r',encoding ='utf-8')as f :
                    data =json .load (f )
                    self .feedback_log =data .get ('feedback_log',[])
                    self .learned_patterns =data .get ('learned_patterns',{})
                    self .mistakes =data .get ('mistakes',[])
                    self .successes =data .get ('successes',[])
            except Exception as _ex:
                _log.debug("_load_data(): подавлено: %s", _ex)

    def _save_data (self ):
        """Сохранить данные в файл"""
        try :
            os .makedirs ('data',exist_ok =True )
            data_file ='data/ai_learning.json'
            with open (data_file ,'w',encoding ='utf-8')as f :
                json .dump ({
                'feedback_log':self .feedback_log [-200 :],# Сохран только son 200
                'learned_patterns':self .learned_patterns ,
                'mistakes':self .mistakes [-100 :],# В конец 100
                'successes':self .successes [-100 :],# В конец 100
                },f ,indent =2 ,ensure_ascii =False )
        except Exception as e :
            print (f"[SELF LEARNING] Ошибка sohraneniya: {e}")


            # Kюresel пример
_self_learning =None 

def get_self_learning ()->SelfLearning :
    """Получает глобальный экземпляр SelfLearning"""
    global _self_learning 
    if _self_learning is None :
        _self_learning =SelfLearning ()
    return _self_learning 
