"""
Multi-modelnaya система — автоматически выбор lucsey modelleri для каждый задачи
"""
import os 
import json 
import time 
from typing import Dict ,List ,Optional ,Tuple 
from datetime import datetime ,timedelta 


class ModelSelector :
    """Umniy выбор modelleri для каждый задачи"""

    # Modelleri по prioritetu (из lucsey e hudsey)
    MODELS ={
    'powerful':{
    'name':'mistral-large-latest',
    'provider':'mistral',
    'speed':'slow',
    'quality':'excellent',
    'cost':'high',
    },
    'balanced':{
    'name':'mistral-medium-latest',
    'provider':'mistral',
    'speed':'medium',
    'quality':'good',
    'cost':'medium',
    },
    'fast':{
    'name':'mistral-small-latest',
    'provider':'mistral',
    'speed':'fast',
    'quality':'decent',
    'cost':'low',
    },
    }

    # Какой тип modelleri ispolzovat для raznih zadac
    TASK_MODEL_MAP ={
    # Prostie задачи — быстрый model
    'greeting':'fast',
    'simple_question':'fast',
    'category_detection':'fast',
    'sentiment_analysis':'fast',

    # Srednie задачи — ilebakiyeirovannaya model
    'technical_support':'balanced',
    'general_chat':'balanced',
    'faq_answer':'balanced',
    'function_calling':'balanced',

    # Slojnie задачи — mosnaya model
    'complaint_analysis':'powerful',
    'moderation_decision':'powerful',
    'complex_reasoning':'powerful',
    'conflict_resolution':'powerful',
    }

    def __init__ (self ):
        self .model_stats ={}# Статистика по каждый modelleri
        self .task_history =[]# История zadac

        # Загруз istatistiгi если есть
        self ._load_stats ()

    def select_model (self ,task_type :str ,context :Dict =None )->str :
        """Vibiraet lucsuyu model для задачи"""

        # Alыyoruz rekomenduemiy тип modelleri
        recommended_type =self .TASK_MODEL_MAP .get (task_type ,'balanced')
        recommended_model =self .MODELS [recommended_type ]

        # Контроль ediyoruz istatistiгi — если model sыk sыk padaet, ispolzuem yedek
        model_name =recommended_model ['name']
        stats =self .model_stats .get (model_name ,{})

        failure_rate =stats .get ('failures',0 )/max (stats .get ('total',1 ),1 )

        # Если failure rate > 20%, pereanahсканироватьemsya на yedek model
        if failure_rate >0.2 :
            if recommended_type =='powerful':
                model_name =self .MODELS ['balanced']['name']
            elif recommended_type =='balanced':
                model_name =self .MODELS ['fast']['name']

                # Loglarruem выбор
        self .task_history .append ({
        'task_type':task_type ,
        'recommended_type':recommended_type ,
        'selected_model':model_name ,
        'timestamp':datetime .utcnow ().isoformat ()
        })

        # Ограничиваем история
        if len (self .task_history )>1000 :
            self .task_history =self .task_history [-1000 :]

        return model_name 

    def record_success (self ,model_name :str ,response_time :float =None ):
        """Сохран успешно использование modelleri"""
        if model_name not in self .model_stats :
            self .model_stats [model_name ]={'total':0 ,'successes':0 ,'failures':0 ,'avg_time':0 }

        self .model_stats [model_name ]['total']+=1 
        self .model_stats [model_name ]['successes']+=1 

        # Обновл ortalama время
        if response_time :
            current_avg =self .model_stats [model_name ]['avg_time']
            total =self .model_stats [model_name ]['total']
            self .model_stats [model_name ]['avg_time']=(
            (current_avg *(total -1 )+response_time )/total 
            )

        self ._save_stats ()

    def record_failure (self ,model_name :str ):
        """Сохран неудачно использование modelleri"""
        if model_name not in self .model_stats :
            self .model_stats [model_name ]={'total':0 ,'successes':0 ,'failures':0 ,'avg_time':0 }

        self .model_stats [model_name ]['total']+=1 
        self .model_stats [model_name ]['failures']+=1 

        self ._save_stats ()

    def get_model_info (self ,model_name :str )->Dict :
        """Alыyor информация о modelleri"""
        for model_type ,model_data in self .MODELS .items ():
            if model_data ['name']==model_name :
                stats =self .model_stats .get (model_name ,{})
                return {
                'type':model_type ,
                'name':model_name ,
                'provider':model_data ['provider'],
                'speed':model_data ['speed'],
                'quality':model_data ['quality'],
                'cost':model_data ['cost'],
                'stats':stats 
                }
        return {}

    def _load_stats (self ):
        """Загруз istatistiгi из dosyaya"""
        stats_file ='data/model_stats.json'
        if os .path .exists (stats_file ):
            try :
                with open (stats_file ,'r',encoding ='utf-8')as f :
                    data =json .load (f )
                    self .model_stats =data .get ('model_stats',{})
                    self .task_history =data .get ('task_history',[])
            except :
                pass 

    def _save_stats (self ):
        """Сохран istatistiгi в dosya"""
        try :
            os .makedirs ('data',exist_ok =True )
            stats_file ='data/model_stats.json'
            with open (stats_file ,'w',encoding ='utf-8')as f :
                json .dump ({
                'model_stats':self .model_stats ,
                'task_history':self .task_history [-100 :]# Сохран только son 100
                },f ,indent =2 )
        except :
            pass 


            # Kюresel пример
_model_selector =None 

def get_model_selector ()->ModelSelector :
    """Alыyor kюresel пример ModelSelector"""
    global _model_selector 
    if _model_selector is None :
        _model_selector =ModelSelector ()
    return _model_selector 


def smart_call (messages :List [Dict ],task_type :str ,max_tokens :int =2048 ,temperature :float =0.7 )->Tuple [str ,str ,Dict ]:
    """
    Умный вызов AI с автоматическим выбором модели

    Args:
        messages: Список сообщений
        task_type: Тип задачи (greeting, complaint_analysis, etc.)
        max_tokens: Максимум токенов
        temperature: Температура

    Returns:
        (response, model_name, info)
    """
    from web .ai_helper import _call 

    selector =get_model_selector ()
    model_name =selector .select_model (task_type )

    start_time =time .time ()

    try :
    # Чтяжелыйыyoruz AI с vibrannoy modelyu
        response ,used_model ,rate_info =_call (
        messages ,
        max_tokens =max_tokens ,
        temperature =temperature ,
        model =model_name 
        )

        response_time =time .time ()-start_time 

        # Сохран uspeh
        selector .record_success (model_name ,response_time )

        info ={
        'model':model_name ,
        'task_type':task_type ,
        'response_time':response_time ,
        'model_info':selector .get_model_info (model_name )
        }

        return response ,model_name ,info 

    except Exception :
    # Сохраняем неудачу
        selector .record_failure (model_name )

        # Probuem yedek model
        if task_type in ['complaint_analysis','moderation_decision','complex_reasoning']:
            fallback_model =ModelSelector .MODELS ['balanced']['name']
        else :
            fallback_model =ModelSelector .MODELS ['fast']['name']

        try :
            response ,used_model ,rate_info =_call (
            messages ,
            max_tokens =max_tokens ,
            temperature =temperature ,
            model =fallback_model 
            )

            response_time =time .time ()-start_time 
            selector .record_success (fallback_model ,response_time )

            info ={
            'model':fallback_model ,
            'task_type':task_type ,
            'response_time':response_time ,
            'fallback':True ,
            'model_info':selector .get_model_info (fallback_model )
            }

            return response ,fallback_model ,info 

        except Exception as e2 :
            raise Exception (f"Оба модели упали: {model_name}, {fallback_model}") from e2 
