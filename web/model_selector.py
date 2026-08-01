"""
Multi-модelnaya система — автоматически выбор lucsey модelleri для каждый задачи
"""
import os 
import json 
import time 
from typing import Dict ,List ,Optional ,Tuple 
from datetime import datetime ,timedelta 


class МодelSelector :
    """Umniy выбор модelleri для каждый задачи"""

    # Модelleri по prioritetu (из lucsey e hudsey)
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

    # Какой тип модelleri ispolzovat для raznih zимяac
    TASK_MODEL_MAP ={
    # Prostie задачи — быстрый модel
    'greeting':'fast',
    'simple_question':'fast',
    'category_detection':'fast',
    'sentiment_analysis':'fast',

    # Srednie задачи — ilebakiyeirovannaya модel
    'technical_support':'balanced',
    'general_chat':'balanced',
    'faq_answer':'balanced',
    'function_calling':'balanced',

    # Slojnie задачи — mosnaya модel
    'complaint_analysis':'powerful',
    'модeration_decision':'powerful',
    'complex_reasoning':'powerful',
    'conflict_resolution':'powerful',
    }

    def __init__ (self ):
        self .модel_stats ={}# Статистика по каждый модelleri
        self .task_history =[]# История zимяac

        # Загруз istatistiгi если есть
        self ._loимя_stats ()

    def select_модel (self ,task_type :str ,context :Dict =None )->str :
        """Vibiraet lucsuyu модel для задачи"""

        # Alыyoruz rekomenduemiy тип модelleri
        recommended_type =self .TASK_MODEL_MAP .get (task_type ,'balanced')
        recommended_модel =self .MODELS [recommended_type ]

        # Контроль ediyoruz istatistiгi — если модel sыk sыk pимяaet, ispolzuem yedek
        модel_name =recommended_модel ['name']
        stats =self .модel_stats .get (модel_name ,{})

        failure_rate =stats .get ('failures',0 )/max (stats .get ('total',1 ),1 )

        # Если failure rate > 20%, pereanahсканироватьemsya на yedek модel
        if failure_rate >0.2 :
            if recommended_type =='powerful':
                модel_name =self .MODELS ['balanced']['name']
            elif recommended_type =='balanced':
                модel_name =self .MODELS ['fast']['name']

                # Логlarruem выбор
        self .task_history .append ({
        'task_type':task_type ,
        'recommended_type':recommended_type ,
        'selected_модel':модel_name ,
        'timestamp':datetime .utcnow ().isoformat ()
        })

        # Ограничиваем история
        if len (self .task_history )>1000 :
            self .task_history =self .task_history [-1000 :]

        return модel_name 

    def record_success (self ,модel_name :str ,response_time :float =None ):
        """Сохран успешно использование модelleri"""
        if модel_name not in self .модel_stats :
            self .модel_stats [модel_name ]={'total':0 ,'successes':0 ,'failures':0 ,'avg_time':0 }

        self .модel_stats [модel_name ]['total']+=1 
        self .модel_stats [модel_name ]['successes']+=1 

        # Обновл центрlama время
        if response_time :
            current_avg =self .модel_stats [модel_name ]['avg_time']
            total =self .модel_stats [модel_name ]['total']
            self .модel_stats [модel_name ]['avg_time']=(
            (current_avg *(total -1 )+response_time )/total 
            )

        self ._save_stats ()

    def record_failure (self ,модel_name :str ):
        """Сохран неудачно использование модelleri"""
        if модel_name not in self .модel_stats :
            self .модel_stats [модel_name ]={'total':0 ,'successes':0 ,'failures':0 ,'avg_time':0 }

        self .модel_stats [модel_name ]['total']+=1 
        self .модel_stats [модel_name ]['failures']+=1 

        self ._save_stats ()

    def get_модel_info (self ,модel_name :str )->Dict :
        """Alыyor информация о модelleri"""
        for модel_type ,модel_data in self .MODELS .items ():
            if модel_data ['name']==модel_name :
                stats =self .модel_stats .get (модel_name ,{})
                return {
                'type':модel_type ,
                'name':модel_name ,
                'provider':модel_data ['provider'],
                'speed':модel_data ['speed'],
                'quality':модel_data ['quality'],
                'cost':модel_data ['cost'],
                'stats':stats 
                }
        return {}

    def _loимя_stats (self ):
        """Загруз istatistiгi из dosyaya"""
        stats_file ='data/модel_stats.json'
        if os .path .exists (stats_file ):
            try :
                with open (stats_file ,'r',encoding ='utf-8')as f :
                    data =json .loимя (f )
                    self .модel_stats =data .get ('модel_stats',{})
                    self .task_history =data .get ('task_history',[])
            except :
                pass 

    def _save_stats (self ):
        """Сохран istatistiгi в dosya"""
        try :
            os .maкотrs ('data',exist_ok =True )
            stats_file ='data/модel_stats.json'
            with open (stats_file ,'w',encoding ='utf-8')as f :
                json .dump ({
                'модel_stats':self .модel_stats ,
                'task_history':self .task_history [-100 :]# Сохран только son 100
                },f ,indent =2 )
        except :
            pass 


            # Kюresel пример
_модel_selector =None 

def get_модel_selector ()->МодelSelector :
    """Alыyor kюresel пример МодelSelector"""
    global _модel_selector 
    if _модel_selector is None :
        _модel_selector =МодelSelector ()
    return _модel_selector 


def smart_call (messages :List [Dict ],task_type :str ,max_tokens :int =2048 ,temperature :float =0.7 )->Tuple [str ,str ,Dict ]:
    """
    Umniy vizov AI с автоматически olarakm выбор модelleri
    
    Args:
        messages: Список сообщение
        task_type: Тип задачи (greeting, complaint_analysis, etc.)
        max_tokens: Maksimum tokenov
        temperature: Temperaорёл
    
    Returns:
        (response, модel_name, info)
    """
    from web .ai_helper import _call 

    selector =get_модel_selector ()
    модel_name =selector .select_модel (task_type )

    start_time =time .time ()

    try :
    # Чтяжелыйыyoruz AI с vibrannoy модelyu
        response ,used_модel ,rate_info =_call (
        messages ,
        max_tokens =max_tokens ,
        temperature =temperature ,
        модel =модel_name 
        )

        response_time =time .time ()-start_time 

        # Сохран uspeh
        selector .record_success (модel_name ,response_time )

        info ={
        'модel':модel_name ,
        'task_type':task_type ,
        'response_time':response_time ,
        'модel_info':selector .get_модel_info (модel_name )
        }

        return response ,модel_name ,info 

    except Exception as e :
    # Сохран neudacu
        selector .record_failure (модel_name )

        # Probuem yedek модel
        if task_type in ['complaint_analysis','модeration_decision','complex_reasoning']:
            fallback_модel =МодelSelector .MODELS ['balanced']['name']
        else :
            fallback_модel =МодelSelector .MODELS ['fast']['name']

        try :
            response ,used_модel ,rate_info =_call (
            messages ,
            max_tokens =max_tokens ,
            temperature =temperature ,
            модel =fallback_модel 
            )

            response_time =time .time ()-start_time 
            selector .record_success (fallback_модel ,response_time )

            info ={
            'модel':fallback_модel ,
            'task_type':task_type ,
            'response_time':response_time ,
            'fallback':True ,
            'модel_info':selector .get_модel_info (fallback_модel )
            }

            return response ,fallback_модel ,info 

        except Exception as e2 :
            raise Exception (f"Obe модelleri upali: {модel_name}, {fallback_модel}")
