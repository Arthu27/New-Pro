"""AI Chat Cog — DM + channel sohbet"""
import discord 
from discord .ext import commands 
import re 
import json 
import os 
import datetime 

from logger import get_logger 
log =get_logger ("ai_chat")
from json_store import load_json ,save_json 


AI_CHANNELS =set ()# Пусто — dinamik как addnir
# Динамические каналы — DM'den addnip удалить
_dynamic_channels :set =set ()# DM'den /ai-channel команда addnir

# АКТИВНЫЕ ЗАДАЧИ (цепочка «условие → действие»)
_active_tasks :list =[]# [{'id': int, 'desc': str, 'condition': str, 'action': str, 'target_id': int}]
_task_counter :int =0 

def _load_tasks ()->list :
    return load_json ('data/jarvis_tasks.json',[],log =log )

def _save_tasks (tasks :list ):
    save_json ('data/jarvis_tasks.json',tasks ,log =log )

_active_tasks =_load_tasks ()

# Owner ID — пересылает неизвестные вопросы сюда
from config import clean_number
OWNER_ID = clean_number(os.getenv('OWNER_ID')) or 0

# Ожидающие вопросы — передаются пользователю, когда owner отвечает
# {owner_dm_message_id: {'user_id': int, 'channel_id': int, 'question': str, 'is_dm': bool}}
_pending_questions :dict ={}

# Фильтр мата (русский + турецкий) — совпадение только целого слова
PROFANITY_WORDS =[
# русский мат
'сука','сучка','бля','блять','блядь','хуй','хуя','хуё','пизда','пиздец',
'ебал','ебан','ёбан','пидор','пидр','шлюха','мразь','гандон','залупа',
'мудак','долбоёб','нахуй','охуеть','заебал','уёбок','уебок','хер','мразота',
# турецкий мат (многоязычная защита)
'amk','amq','orospu','sik','göt','got','piç','pic',
'yarrak','yarak','siktir','bok','kahpe','ibne','amcık','amcik']

def _has_profanity (text :str )->bool :
    t =text .lower ()
    # только целое слово: по краям — пробел или пунктуация
    import re 
    for k in PROFANITY_WORDS :
        if re .search (r'\b'+re .escape (k )+r'\b',t ):
            return True 
    return False 

    # Пользователь основанный на разговор история — постоянный depolama
HISTORY_FILE ='data/ai_chat_histories.json'
KNOWLEDGE_FILE ='data/ai_knowledge_base.json'
INSTRUCTIONS_FILE ='data/ai_instructions.json'
PROFILES_FILE ='data/ai_user_profiles.json'# Пользователь профили личности
OWNER_PREFS_FILE ='data/owner_preferences.json'# Arthur'un постоянный tercihleri
_save_counter =0 


def _load_owner_prefs ()->dict :
    return load_json (OWNER_PREFS_FILE ,{'rules':[],'memory':{},'disabled_notifications':[]},log =log )


def _save_owner_prefs (prefs :dict ):
    save_json (OWNER_PREFS_FILE ,prefs ,log =log )


_owner_prefs =_load_owner_prefs ()


def _load_profiles ()->dict :
    return load_json (PROFILES_FILE ,{},log =log )


def _save_profiles (profiles :dict ):
    if not save_json (PROFILES_FILE ,profiles ,log =log ):
        log .info ('[AI] Profil сохран Ошибки — см. json_store warning')


def _update_profile (user_id :int ,question :str ,answer :str ,profiles :dict ):
    """Разговор user profilini обновить"""
    uid =str (user_id )
    if uid not in profiles :
        profiles [uid ]={
        'interests':[],
        'style':'normal',
        'message_count':0 ,
        'topics':{}
        }
    p =profiles [uid ]
    p ['message_count']=p .get ('message_count',0 )+1 

    # Определение интересов
    interest_keywords ={
    'музыка':['музыка','песня','альбом','исполнитель','rap','pop','rock'],
    'oyun':['oyun','game','lol','valorant','minecraft','cs2'],
    'anime':['anime','manga','naruto','attack on titan','one piece'],
    'spor':['футбол','баскетбол','матч','гол','команда'],
    'teknoloji':['kod','python','программирование','написано','ai'],
    }
    q_lower =question .lower ()
    for interest ,keywords in interest_keywords .items ():
        if any (kw in q_lower for kw in keywords ):
            if interest not in p ['interests']:
                p ['interests'].append (interest )
            p ['topics'][interest ]=p ['topics'].get (interest ,0 )+1 

            # Разговор определение стиля
    if len (question )<10 :
        p ['style']='краткий'
    elif '?'in question and len (question )>50 :
        p ['style']='любопытный'


_profiles =_load_profiles ()

def _load_histories ()->dict :
    """Загрузить историю диалогов с диска (через общий кэш json_store)."""
    try :
        # строковые ключи приводим к int
        return {int (k ):v for k ,v in load_json (HISTORY_FILE ,{},log =log ).items ()}
    except Exception as e :
        log .info (f'[AI] Ошибка загрузки истории: {e}')
        return {}

def _load_knowledge_base ()->dict :
    """Загрузить базу знаний серверов"""
    return load_json (KNOWLEDGE_FILE ,{},log =log )

def _load_instructions ()->dict :
    """Сервер основанный на постоянный инструкции загрузить"""
    return load_json (INSTRUCTIONS_FILE ,{},log =log )

def _save_instructions (instructions :dict ):
    """Постоянный инструкции сохранить"""
    if not save_json (INSTRUCTIONS_FILE ,instructions ,log =log ):
        log .info ('[AI] Ошибка сохранения инструкций — см. json_store warning')

def _detect_instruction (message :str ,answer :str )->dict :
    """
    Распознать постоянную инструкцию, которую пользователь даёт боту.
    Напр.: «если кто-то спросит X — отвечай Y»
    """
    m =message .lower ().strip ()

    # Шаблоны инструкций
    patterns =[
    # «кто бы ни спросил X — отвечай Y»
    r'кто бы ни (написал|спросил) .{3,50}',
    # «всем говори/скажи X»
    r'всем .{3,50} (говори|скажи|ответь)',
    # «впредь если спросят X — говори Y»
    r'впредь если .{3,50} (спросит|спросят)',
    # «на вопрос X отвечай Y»
    r'.{3,30} на вопрос .{3,50} (ответь|отвечай|пиши)',
    # русские формулировки
    r'если (?:кто-нибудь |кто-то )?спросит .{3,60}',
    r'всем (?:говори|отвечай|пиши) .{3,50}',
    r'на вопрос .{3,50} (?:отвечай|ответь|пиши)',
    ]

    for pattern in patterns :
        if re .search (pattern ,m ):
            return {
            'trigger':message ,# сообщение-триггер
            'response':answer ,# ответ бота (предыдущий ответ)
            'instruction':message 
            }
    return None 

def _save_histories (histories :dict ,force :bool =False ):
    """Сохранить историю диалогов на диск (пакетно)"""
    global _save_counter 
    _save_counter +=1 
    # сохраняем каждое 5-е сообщение или при force=True
    if not force and _save_counter %5 !=0 :
        return 
    if not save_json (HISTORY_FILE ,histories ,log =log ):
        log .info ('[AI] Ошибка сохранения истории — см. json_store warning')

def _save_knowledge_base (knowledge :dict ):
    """Сохранить базу знаний"""
    if not save_json (KNOWLEDGE_FILE ,knowledge ,log =log ):
        log .info ('[AI] Ошибка сохранения базы знаний — см. json_store warning')

def _extract_learned_info (question :str ,answer :str )->dict :
    """Удалить обученную информацию из вопроса-ответа"""
    q =question .lower ().strip ()

    # если ответ из веб-поиска — доверие пониженное
    is_web_search =' Web поиск выполнен'in answer 
    confidence ='low'if is_web_search else 'high'

    # вопросы «кто такой X»
    if 'кто такой' in q or 'кто такая' in q or 'кто это' in q :
    # вытаскиваем имя из вопроса
        name_patterns =[
        r'(\w+(?:\s+\w+)*)\s+кто',
        r'кто\s+такой\s+(\w+(?:\s+\w+)*)',
        r'кто\s+такая\s+(\w+(?:\s+\w+)*)'
        ]
        for pattern in name_patterns :
            match =re .search (pattern ,q )
            if match :
                name =match .group (1 ).strip ()
                return {
                'type':'person_info',
                'name':name ,
                'info':answer [:500 ],# первые 500 символов
                'question':question ,
                'confidence':confidence ,
                'source':'web_search'if is_web_search else 'chat'
                }

                # вопросы «что такое X»
    if 'что такое' in q or 'что это' in q :
    # вытаскиваем тему из вопроса
        topic_patterns =[
        r'что\s+такое\s+(\w+(?:\s+\w+)*)',
        r'что\s+это\s+(\w+(?:\s+\w+)*)'
        ]
        for pattern in topic_patterns :
            match =re .search (pattern ,q )
            if match :
                topic =match .group (1 ).strip ()
                return {
                'type':'topic_info',
                'topic':topic ,
                'info':answer [:500 ],
                'question':question ,
                'confidence':confidence ,
                'source':'web_search'if is_web_search else 'chat'
                }

    return None 

_histories =_load_histories ()
_knowledge_base =_load_knowledge_base ()
_instructions =_load_instructions ()

# кэш сообщений — обновляем для каждого пользователя раз в 5 минут
_message_cache ={}
_cache_timeout =300 # 5 минут


async def _get_recent_user_messages (user_id :int ,guild ,limit :int =15 )->list :
    """Собрать последние сообщения пользователя на сервере (за 12 часов, макс. 15)"""
    if not guild :
        return []

    import datetime 
    import time 

    # Cache контроль
    cache_key =f"{guild.id}_{user_id}"
    now =time .time ()
    if cache_key in _message_cache :
        cached_data ,cached_time =_message_cache [cache_key ]
        if now -cached_time <_cache_timeout :
            return cached_data 

    recent =[]
    cutoff_time =datetime .datetime .now (datetime .timezone .utc )-datetime .timedelta (hours =12 )

    try :
    # Сканировать только активные каналы (с недавними сообщениями)
        active_channels =[]
        for channel in guild .text_channels :
            if not channel .permissions_for (guild .me ).read_message_history :
                continue 
            try :
            # В конец сообщение контроль et
                last_msg =await channel .history (limit =1 ).flatten ()
                if last_msg and (datetime .datetime .now (datetime .timezone .utc )-last_msg [0 ].created_at ).seconds <7200 :
                    active_channels .append (channel )
            except Exception as _ex:
                log.debug("_get_recent_user_messages(): подавлено: %s", _ex)
                continue 

                # Сканируем активные каналы — собираем до 15 сообщений
        for channel in active_channels [:15 ]:# не больше 15 каналов
            try :
                async for msg in channel .history (limit =30 ,after =cutoff_time ):
                    if msg .author .id ==user_id and not msg .content .startswith ('moe'):
                    # Bot не включать команды
                        recent .append ({
                        'channel':channel .name ,
                        'content':msg .content [:200 ],# 150 → 200 karakter
                        'timestamp':msg .created_at .strftime ('%H:%M')
                        })
                        if len (recent )>=limit :# 15 message найден ca dur
                            break 
            except Exception as _ex:
                log.debug("_get_recent_user_messages(): подавлено: %s", _ex)
                continue 

            if len (recent )>=limit :
                break 

                # Время по очередь (en новый en sonda)
        recent .sort (key =lambda x :x ['timestamp'])
        result =recent [-limit :]# В конец 15 message

        # Cache'e сохранить
        _message_cache [cache_key ]=(result ,now )
        return result 
    except Exception as e :
        log .info (f'[AI] Ошибка сбора сообщений: {e}')
        return []


async def _get_channel_context (channel ,limit :int =12 )->list :
    """Собрать последние сообщения текущего канала (для контекста беседы)"""
    try :
        context_messages =[]
        async for msg in channel .history (limit =limit ):
            if msg .author .bot :
                continue # сообщения бота не включаем
            context_messages .append ({
            'author':msg .author .display_name ,
            'content':msg .content [:200 ],# 150 → 200 karakter
            'timestamp':msg .created_at .strftime ('%H:%M')
            })
            # Ters преобразовать (en старый en baшta)
        context_messages .reverse ()
        return context_messages 
    except Exception as e :
        log .info (f'[AI] Канал context Ошибки: {e}')
        return []


def _call_ai (question :str ,user_id :int ,guild =None ,recent_messages :list =None ,channel_context :list =None )->str :
    try :
        from web .ai_helper import ai_assistant 
        history =_histories .get (user_id ,[])

        # Пользователь infosi
        user_name ='друг'
        guild_id =0 
        if guild :
            member =guild .get_member (user_id )
            guild_id =guild .id 
            if member :
                user_name =member .display_name 

        is_dm =guild is None 
        context ={
        'user_name':user_name ,
        'user_id':str (user_id ),
        'guild_name':guild .name if guild else 'DM',
        'member_count':guild .member_count if guild else 0 ,
        'guild_id':guild_id ,
        'is_dm':is_dm ,
        }

        # владелец сервера и роли администраторов (инфо)
        if guild :
            try :
                owner =guild .owner 
                if owner :
                    context ['guild_owner']=owner .display_name 

                    # Администратор роли — manage_messages или kick разрешение которые являются
                staff_roles =[]
                for role in guild .roles :
                    if role .is_default ():
                        continue 
                    if role .permissions .manage_messages or role .permissions .kick_members or role .permissions .administrator :
                        members =[m .display_name for m in role .members if not m .bot ][:5 ]
                        if members :
                            staff_roles .append ({'name':role .name ,'members':members })
                if staff_roles :
                    context ['staff_roles']=staff_roles [:8 ]# Max 8 роли
            except Exception as e :
                log .info (f'[AI] Guild info Ошибки: {e}')

                #  СЕРВЕР СОСТОЯНИЕ (J.A.R.V.I.S. разница) 
        if guild and str (user_id )=='987430047889637426':
            try :
                online =[m for m in guild .members if not m .bot and m .status !=discord .Status .offline ]
                in_voice =[]
                for vc in guild .voice_channels :
                    for m in vc .members :
                        if not m .bot :
                            in_voice .append (m .display_name )
                            # Недавно присоединившиеся (за 24 часа)
                import datetime as _dt 
                cutoff =_dt .datetime .now (_dt .timezone .utc )-_dt .timedelta (hours =24 )
                recent_joins =[m .display_name for m in guild .members 
                if not m .bot and m .joined_at and m .joined_at >cutoff ]
                # Открытые ticket-каналы
                ticket_channels =[c for c in guild .text_channels if c .name .startswith ('ticket-')]
                context ['server_status']={
                'online_count':len (online ),
                'voice_count':len (in_voice ),
                'voice_members':in_voice [:5 ],
                'recent_joins':recent_joins [:5 ],
                'active_tickets':len (ticket_channels ),
                'total_members':guild .member_count ,
                }
            except Exception as e :
                log .info (f'[AI] Сервер status Ошибки: {e}')

                #  АКТИВЕН ЗАДАЧИ 
        if str (user_id )=='987430047889637426':
            try :
                from cogs .ai_chat import _active_tasks 
                if _active_tasks :
                    context ['active_tasks']=[t ['desc']for t in _active_tasks [:5 ]]
            except Exception as _ex:
                log.debug("_call_ai(): подавлено: %s", _ex)

                # Добавить последние Discord-сообщения пользователя в контекст (только на сервере)
        if recent_messages :
            context ['recent_user_messages']=recent_messages 

            # Канал контекстnы add (только на сервере)
        if channel_context :
            context ['channel_context']=channel_context 

            # Добавить релевантную информацию из базы сервера
        if guild_id and str (guild_id )in _knowledge_base :
            guild_knowledge =_knowledge_base [str (guild_id )]
            relevant_knowledge =[]
            q_lower =question .lower ()

            for item in guild_knowledge :
            # пропускаем ненадёжные записи (веб-поиск)
                if item .get ('confidence')=='low':
                    continue 

                    # совпадение по словам вопроса
                if any (word in item .get ('question','').lower ()for word in q_lower .split ()if len (word )>2 ):
                    relevant_knowledge .append (f"заранее выученное: {item.get('question', '')} → {item.get('info', '')}")
                    # совпадение по имени/теме
                elif 'name'in item and any (word in item ['name'].lower ()for word in q_lower .split ()if len (word )>2 ):
                    relevant_knowledge .append (f"Известная личность: {item['name']} → {item.get('info', '')}")
                elif 'topic'in item and any (word in item ['topic'].lower ()for word in q_lower .split ()if len (word )>2 ):
                    relevant_knowledge .append (f"Известная тема: {item['topic']} → {item.get('info', '')}")

            if relevant_knowledge :
                context ['learned_knowledge']=relevant_knowledge [:3 ]# не больше 3 записей

                # инструкции сервера — в контекст
        if guild_id :
            guild_instructions =_instructions .get (str (guild_id ),[])
            if guild_instructions :
                context ['guild_instructions']=guild_instructions 

                # профиль пользователя — в контекст
        uid_str =str (user_id )
        if uid_str in _profiles :
            p =_profiles [uid_str ]
            if p .get ('interests'):
                context ['user_interests']=p ['interests'][:5 ]
            if p .get ('style'):
                context ['user_style']=p ['style']

        answer ,new_history ,model_name ,_ =ai_assistant (question ,context ,history )

        # Profili обновить
        _update_profile (user_id ,question ,answer ,_profiles )
        if _profiles .get (str (user_id ),{}).get ('message_count',0 )%10 ==0 :
            _save_profiles (_profiles )

            # Talimat tespiti — "всем X ответить" gibi messagelar
        if guild_id :
            instr =_detect_instruction (question ,answer )
            if instr :
                guild_key =str (guild_id )
                if guild_key not in _instructions :
                    _instructions [guild_key ]=[]
                    # Одинаковый talimat есть mы?
                exists =any (i .get ('trigger')==instr ['trigger']for i in _instructions [guild_key ])
                if not exists :
                    _instructions [guild_key ].append (instr )
                    if len (_instructions [guild_key ])>30 :
                        _instructions [guild_key ]=_instructions [guild_key ][-30 :]
                    _save_instructions (_instructions )
                    log .info (f'[AI] Новый talimat сохранено: {instr["trigger"][:50]}')

                    # выделяем из ответа обучаемую информацию и сохраняем её
        if guild_id :
            learned =_extract_learned_info (question ,answer )
            if learned :
                guild_key =str (guild_id )
                if guild_key not in _knowledge_base :
                    _knowledge_base [guild_key ]=[]

                    # Одинаковый info есть mы контроль et
                existing =False 
                for item in _knowledge_base [guild_key ]:
                    if (item .get ('name')==learned .get ('name')or 
                    item .get ('topic')==learned .get ('topic')):
                    # Обновить
                        item .update (learned )
                        existing =True 
                        break 

                if not existing :
                    _knowledge_base [guild_key ].append (learned )
                    # держим максимум 50 записей
                    if len (_knowledge_base [guild_key ])>50 :
                        _knowledge_base [guild_key ]=_knowledge_base [guild_key ][-50 :]

                _save_knowledge_base (_knowledge_base )

                # В конце держим 40 сообщений (20 пар вопрос-ответ) — более длинная память
        _histories [user_id ]=new_history [-40 :]
        # сохраняем на диск
        _save_histories (_histories )
        return answer or 'Хм, что-то пошло не так. Попробуете ещё раз? '
    except Exception as e :
        log .info (f'[AI] Ошибка: {e}')
        return 'Сейчас не могу ответить, попробуйте позже. '


class AIChat (commands .Cog ):
    def __init__ (self ,bot ):
        self .bot =bot 

    @commands .hybrid_command (name ='ai-info-clear',description ="Очистить базу AI-инфо на сервере (Менеджер)")
    @commands .has_permissions (administrator =True )
    async def ai_clear_knowledge (self ,ctx ):
        """Очистить базу знаний AI сервера (только админы)"""
        guild_id =str (ctx .guild .id )
        if guild_id in _knowledge_base :
            del _knowledge_base [guild_id ]
            _save_knowledge_base (_knowledge_base )
            from cogs .embed_utils import reply as _reply 
            await _reply (ctx ,'ai','База знаний очищена','AI забыл всё, чему его учили на этом сервере.')
        else :
            from cogs .embed_utils import reply as _reply 
            await _reply (ctx ,'ai','Уже пусто','База знаний сервера и так пуста.')

    @commands .hybrid_command (name ='ai-reset',description ="Сбросить историю AI-чата")
    async def ai_reset (self ,ctx ):
        """Сбросить свою историю AI-чата"""
        user_id =ctx .author .id 
        if user_id in _histories :
            del _histories [user_id ]
            _save_histories (_histories ,force =True )
            from cogs .embed_utils import reply as _reply 
            await _reply (ctx ,'ai','История сброшена','Наша история чата стёрта — начинаем с чистого листа.')
        else :
            from cogs .embed_utils import reply as _reply 
            await _reply (ctx ,'ai','Уже пусто','Истории чата и так нет.')

    @commands .hybrid_command (name ='ai-info-add',description ="Добавить постоянную информацию в базу знаний AI (админ)")
    @commands .has_permissions (administrator =True )
    async def ai_add_knowledge (self ,ctx ,tema :str ,*,info :str ):
        """
        Научить AI постоянной информации о сервере.
        Пример: /ai-info-add правила Полные правила сервера лежат в канале #rules.
        """
        guild_key =str (ctx .guild .id )
        if guild_key not in _knowledge_base :
            _knowledge_base [guild_key ]=[]

            # такая тема уже есть?
        for item in _knowledge_base [guild_key ]:
            if item .get ('name','').lower ()==tema .lower ()or item .get ('topic','').lower ()==tema .lower ():
                item ['info']=info 
                item ['confidence']='high'
                item ['source']='manual'
                _save_knowledge_base (_knowledge_base )
                from cogs .embed_utils import reply as _reply 
                await _reply (ctx ,'ai','Информация обновлена',f'Запись о **{tema}** перезаписана.',ephemeral =True )
                return 

                # Новый info add
        _knowledge_base [guild_key ].append ({
        'type':'manual',
        'name':tema .lower (),
        'topic':tema .lower (),
        'info':info ,
        'question':f'кто такой {tema}',
        'confidence':'high',
        'source':'manual'
        })
        _save_knowledge_base (_knowledge_base )
        from cogs .embed_utils import reply as _reply 
        await _reply (ctx ,'ai','Информация сохранена',f'Теперь я знаю всё о **{tema}** — спрашивай!',ephemeral =True )

    @commands .hybrid_command (name ='ai-info-list',description ="Список информации в базе знаний AI (админ)")
    @commands .has_permissions (administrator =True )
    async def ai_list_knowledge (self ,ctx ):
        """Показать записи базы знаний AI сервера"""
        guild_key =str (ctx .guild .id )
        items =_knowledge_base .get (guild_key ,[])

        if not items :
            from cogs .embed_utils import reply as _reply 
            await _reply (ctx ,'ai','Пока пусто','В базе знаний пока нет записей. Научи меня: `/ai-info-add <тема> <инфо>`.')
            return 

        lines =[]
        for i ,item in enumerate (items ,1 ):
            name =item .get ('name')or item .get ('topic','?')
            src ='Ручная'if item .get ('source')=='manual'else 'Веб'
            conf =''if item .get ('confidence')=='high'else ''
            lines .append (f'{conf} **{name}** ({src})')

        embed =discord .Embed (
        title =' AI База знаний',
        description ='\n'.join (lines [:20 ]),
        color =0x00D9FF 
        )
        await ctx .send (embed =embed ,ephemeral =True )

    async def _handle_dm_send (self ,text :str ,message :discord .Message )->str :
        """Отправить ЛС участнику: триггеры «напиши в личку», «отправь лс»."""
        import re 

        # Цель участника bul
        target_id =None 
        mention_match =re .search (r'<@!?(\d+)>',text )
        if mention_match :
            target_id =int (mention_match .group (1 ))
        if not target_id :
            id_match =re .search (r'\b(\d{17,20})\b',text )
            if id_match :
                target_id =int (id_match .group (1 ))

                # «в том же голосовом канале, что и я» → другой участник в канале owner'а
        cl =text .lower ()
        if not target_id and any (t in cl for t in ['в том же войсе','в одном войсе со мной',
        'кто со мной в войсе','со мной в голосовом']):
            for guild in self .bot .guilds :
                owner =guild .get_member (OWNER_ID )
                if not owner or not owner .voice :
                    continue 
                    # Другие участники в том же голосовом канале (без ботов)
                others =[m for m in owner .voice .channel .members 
                if m .id !=OWNER_ID and not m .bot ]
                if others :
                    target_id =others [0 ].id # берём первого
                    break 

        if not target_id :
            return ' Не понял, кому отправить ЛС. Укажи ID, упоминание или «кто со мной в войсе».'

            # отделяем текст сообщения
            # форматы: «напиши @user в личку: …», «отправь лс @user: …»
        dm_content =None 
        # берём всё после «личка:», «лс:», «напиши:», «отправь:»
        msg_match =re .search (r'(?:личка[:\s]+|лс[:\s]+|напиши[:\s]+|отправь[:\s]+|отправить[:\s]+)(.+)',text ,re .IGNORECASE )
        if msg_match :
            dm_content =msg_match .group (1 ).strip ()
            # вырезаем ID/упоминания из содержимого
            dm_content =re .sub (r'<@!?\d+>','',dm_content ).strip ()
            dm_content =re .sub (r'\b\d{17,20}\b','',dm_content ).strip ()

            # всё ещё пусто — вырезаем слова-команды и берём остаток как текст
        if not dm_content :
            clean =text 
            for t in ['отправь в личку','напиши в личку','отправь лс','напиши лс',
            'отправь в лс','напиши в лс','личка','личное сообщение',
            'в том же войсе','в одном войсе со мной','кто со мной в войсе',
            'со мной в голосовом']:
                clean =clean .replace (t ,'').strip ()
            clean =re .sub (r'<@!?\d+>','',clean ).strip ()
            clean =re .sub (r'\b\d{17,20}\b','',clean ).strip ()
            dm_content =clean or None 

        if not dm_content :
            return ' Не понял, что написать. Формат: «напиши @user в личку: текст».'

            # ищем участника и отправляем ЛС
        for guild in self .bot .guilds :
            member =guild .get_member (target_id )
            if not member :
                continue 
            try :
                await member .send (dm_content )
                return f' ЛС отправлено → **{member.display_name}**: *{dm_content[:100]}*'
            except discord .Forbidden :
                return f' **{member.display_name}** — личные сообщения закрыты.'
            except Exception as e :
                return f' ЛС не отправлено: {e}'

                # на сервере не нашли — пробуем прямой fetch
        try :
            user =await self .bot .fetch_user (target_id )
            await user .send (dm_content )
            return f' ЛС отправлено → **{user.name}**: *{dm_content[:100]}*'
        except Exception as e :
            return f' Пользователь не найден или ЛС не отправлено: {e}'

    async def _handle_voice_move (self ,text :str ,message :discord .Message )->str :
        """Перемещение по голосовым каналам — один/два шага, вернуть назад, поддержка имени канала"""
        import re 
        import asyncio 

        # нормализация: грубое совпадение транслита и кириллицы
        def norm (s ):
            return (s .lower ()
            .replace ('ю','u').replace ('ш','s').replace ('г','g')
            .replace ('ы','i').replace ('ё','o').replace ('ч','c')
            .replace ('И','i').replace ('Ю','u').replace ('Ш','s'))

        cl =text .lower ()
        cl_norm =norm (text )

        #  Цель участника bul 
        target_id =None 
        mention_match =re .search (r'<@!?(\d+)>',text )
        if mention_match :
            target_id =int (mention_match .group (1 ))
        if not target_id :
            id_match =re .search (r'\b(\d{17,20})\b',text )
            if id_match :
                target_id =int (id_match .group (1 ))
        if not target_id and any (t in cl for t in ['меня','мне','мой','меня перемести']):
            target_id =OWNER_ID 
        if not target_id :
            return ' Не понял, кого переместить. Укажи ID или упоминание.'

            # просьба «вернуть назад»
        back_requested =any (t in cl_norm for t in ['верни назад','верни','назад'])

        # направление и число шагов
        direction =0 
        # понимаем и «вверх», и «вниз»
        up_words =['вверх','наверх']
        down_words =['вниз','ниже']

        count_match =re .search (r'(\d+)\s*('+
        '|'.join (up_words +down_words )+r')',cl_norm )
        if count_match :
            direction =int (count_match .group (1 ))
            if any (w in count_match .group (2 )for w in norm ('|'.join (down_words )).split ('|')):
                direction =-direction 
        else :
            if any (w in cl_norm for w in up_words ):
                direction =1 
            elif any (w in cl_norm for w in down_words ):
                direction =-1 

                # «верни в канал X» — вытаскиваем имя целевого канала,
                # а служебные «этот канал / сюда» именем не считаем
        target_channel_name =None 
        channel_name_match =re .search (r'(?:верни|перемести|перекинь|притяни)\s+(.+?)(?:\s+канал?|$)',cl )
        if channel_name_match :
            candidate =channel_name_match .group (1 ).strip ()
            if candidate not in ('это','этот','канал','текущий','сюда','в этот канал'):
                target_channel_name =candidate 

        results =[]
        for guild in self .bot .guilds :
            member =guild .get_member (target_id )
            if not member :
                continue 
            if not member .voice or not member .voice .channel :
                results .append (f' {member.display_name} сейчас не в голосовом канале.')
                continue 

            current_vc =member .voice .channel 
            voice_channels =sorted (guild .voice_channels ,key =lambda c :c .position )
            current_idx =next ((i for i ,c in enumerate (voice_channels )if c .id ==current_vc .id ),None )
            if current_idx is None :
                results .append (' Текущий канал не найден в списке.')
                continue 

                # ШАГ 1: переместить участника
            target_vc =None 
            if direction !=0 :
                new_idx =max (0 ,min (len (voice_channels )-1 ,current_idx -direction ))
                target_vc =voice_channels [new_idx ]
            elif target_channel_name :
                for vc in voice_channels :
                    if norm (vc .name )in norm (target_channel_name )or norm (target_channel_name )in norm (vc .name ):
                        target_vc =vc 
                        break 
            else :
            # имя канала встречается прямо в тексте?
                for vc in voice_channels :
                    if norm (vc .name )in cl_norm :
                        target_vc =vc 
                        break 

            if not target_vc or target_vc .id ==current_vc .id :
                if target_vc and target_vc .id ==current_vc .id :
                    results .append (f'ℹ Уже в этом канале: **{current_vc.name}**')
                else :
                    results .append (
                    f' Целевой канал не найден. Текущий: **{current_vc.name}**\n'
                    f'Голосовые каналы: {", ".join(vc.name for vc in voice_channels)}'
                    )
                continue 

            try :
                await member .move_to (target_vc )
                msg =f' **{member.display_name}** → **{target_vc.name}** — переместил.'

                # ШАГ 2: вернуть назад, если просили
                if back_requested :
                # «верни» без имени — возврат в исходный канал
                    back_vc =current_vc 

                    # если указано имя канала — возвращаем в него
                    if target_channel_name :
                        for vc in voice_channels :
                            if norm (vc .name )in norm (target_channel_name )or norm (target_channel_name )in norm (vc .name ):
                                back_vc =vc 
                                break 

                    await asyncio .sleep (3 )# ждём 3 секунды
                    # Участник всё ещё в голосовом канале?
                    await member .guild .chunk ()# cache обновить
                    fresh =guild .get_member (target_id )
                    if fresh and fresh .voice :
                        await fresh .move_to (back_vc )
                        msg +=f'\n Через 3 секунды возвращён в канал **{back_vc.name}**.'
                    else :
                        msg +='\n Не удалось вернуть — участник вышел из голосового канала.'

                results .append (msg )
            except discord .Forbidden :
                results .append (' Нет прав (требуется разрешение «Перемещение участников»).')
            except Exception as e :
                results .append (f' Ошибка: {e}')

        return '\n'.join (results )if results else ' Пользователь не найден на этом сервере.'

    def _norm (self ,s :str )->str :
        return (s .lower ()
        .replace ('ю','u').replace ('ш','s').replace ('г','g')
        .replace ('ы','i').replace ('ё','o').replace ('ч','c')
        .replace ('И','i').replace ('Ю','u').replace ('Ш','s'))

    def _extract_target (self ,text :str ):
        """Извлечь ID целевого участника из текста (mention, raw ID, 'я', имя)"""
        import re 
        m =re .search (r'<@!?(\d+)>',text )
        if m :return int (m .group (1 ))
        m =re .search (r'\b(\d{17,20})\b',text )
        if m :return int (m .group (1 ))
        cl =text .lower ()
        if any (t in cl for t in ['мне','меня','мой','меня ']):
            return OWNER_ID 
            # поиск по имени среди участников сервера
            # Убрать слова команды — оставшаяся часть может быть именем
        stop_words =['выгнать из войса','выкинь из войса','кикни','забань',
        'таймаут','варн','выдай роль','сними роль','роли дай','роли забери',
        'этого участника','этому человеку','этому участнику',
        'участника','пользователя','человека',
        'его','её','этого','ему']
        clean =cl 
        for sw in stop_words :
            clean =clean .replace (sw ,' ')
        clean =re .sub (r'\s+',' ',clean ).strip ()
        if len (clean )>=2 :
            for guild in self .bot .guilds :
                for member in guild .members :
                    if member .bot :
                        continue 
                    name =member .display_name .lower ()
                    username =member .name .lower ()
                    if clean in name or clean in username or name in clean or username in clean :
                        return member .id 
        return None 

    def _extract_duration_minutes (self ,text :str )->int :
        """Metinden длительность minutes cinsinden удалить."""
        import re 
        cl =text .lower ()
        m =re .search (r'(\d+)\s*(часов|hour)',cl )
        if m :return int (m .group (1 ))*60 
        m =re .search (r'(\d+)\s*(день|день|day)',cl )
        if m :return int (m .group (1 ))*1440 
        m =re .search (r'(\d+)\s*(неделя|week)',cl )
        if m :return int (m .group (1 ))*10080 
        m =re .search (r'(\d+)\s*(minutes|dk|min)',cl )
        if m :return int (m .group (1 ))
        return 10 # varчислоlan

    async def _detect_owner_intent (self ,text :str ,message :discord .Message )->bool :
        """Owner DM команды — на ключевых словах, работает даже при опечатках"""
        import re 
        cl =text .lower ()
        cn =self ._norm (text )

        #  МУЗЫКА 
        # Зайти в голосовой канал (без музыки)
        ses_gir_triggers =['voice gir','voice katыl','voice gel','channela gir','benim voice gir',
        'voice gir','ses в канал gir','ses в канал gir','yanima gel']
        if any (t in cn for t in [self ._norm (x )for x in ses_gir_triggers ]):
            result_msg =' Ты не в голосовом канале.'
            for guild in self .bot .guilds :
                member =guild .get_member (OWNER_ID )
                if not member or not member .voice :
                    continue 
                try :
                    vc =guild .voice_client 
                    if not vc :
                        vc =await member .voice .channel .connect ()
                    else :
                        await vc .move_to (member .voice .channel )
                    result_msg =f' Зашёл в канал **{member.voice.channel.name}**.'
                    break 
                except Exception as e :
                    result_msg =f' Ошибка: {e}'
            await message .channel .send (result_msg )
            return True 

            # выйти из голосового канала
        ses_cik_triggers =['выйди из войса','выйди из голосового','покинь войс',
        'отключись от войса','выйди из канала']
        if any (t in cn for t in [self ._norm (x )for x in ses_cik_triggers ]):
            result_msg =' Я уже не в голосовом канале.'
            for guild in self .bot .guilds :
                vc =guild .voice_client 
                if vc :
                    await vc .disconnect ()
                    result_msg =' Вышел из голосового канала.'
                    break 
            await message .channel .send (result_msg )
            return True 

        music_triggers =['включи музыку','поставь трек','поставь песню','музыку включи']
        if any (t in cl for t in music_triggers ):
            await message .channel .send (
            ' Музыка переехала в полноценный плеер Aether.\n'
            'Зайди в голосовой канал и запусти активность «Aether Music» — '
            'очередь, перемотка и обложки уже там.')
            return True 

            # (AFK-интенты убраны: модуль afk.py спит в лёгком профиле)

            # перемещение по голосовым каналам
        ses_tasi_triggers =[
        'перемести в канал','перекинь в канал','притяни в канал',
        'канал выше','канал ниже','на канал выше','на канал ниже',
        'верни в канал','перемести в войс','верни в войс',
        ]
        # выгнать из голосового канала
        voice_kick_triggers =['выгнать из войса','выкинь из войса','кикни из войса',
        'выгнать из голосового','выкинуть из голосового','выгони из войса']
        if any (t in cn for t in [self ._norm (x )for x in voice_kick_triggers ]):
            target_id =self ._extract_target (text )
            if not target_id :
                await message .channel .send (' Не удалось определить пользователя — упомяни его или ответь на его сообщение.')
                return True 
            results =[]
            for guild in self .bot .guilds :
                member =guild .get_member (target_id )
                if not member :
                    continue 
                if not member .voice :
                    results .append (f' **{member.display_name}** уже не в голосовом канале.')
                    continue 
                try :
                    await member .move_to (None )
                    results .append (f' **{member.display_name}** выкинут из голосового канала.')
                except discord .Forbidden :
                    results .append (' Нет прав администратора.')
                except Exception as e :
                    results .append (f' Ошибка: {e}')
            await message .channel .send ('\n'.join (results )if results else ' Участник не найден.')
            return True 

        if any (t in cl for t in ses_tasi_triggers ):
            result_msg =await self ._handle_voice_move (text ,message )
            await message .channel .send (result_msg )
            return True 

            # ЛС: «напиши в личку …», «отправь лс …»
        dm_triggers =['напиши в личку','отправь в личку','отправь лс','напиши лс',
        'отправь в лс','напиши в лс','личка','личное сообщение']
        if any (t in cl for t in dm_triggers ):
            result_msg =await self ._handle_dm_send (text ,message )
            await message .channel .send (result_msg )
            return True 

            # ЦЕПОЧКИ ЗАДАЧ
            # условные задачи: «следи за X, если нарушит — забань»
        task_add_words =['задача добавить','создай задачу','новая задача','следи за',
        'если нарушит забань','если нарушит кикни','если нарушит таймаут',
        'если матернётся забань','если матернётся таймаут']
        if any (t in cn for t in [self ._norm (x )for x in task_add_words ]):
            target_id =self ._extract_target (text )
            desc =text .strip ()
            task ={'id':len (_active_tasks )+1 ,'desc':desc ,
            'target_id':target_id ,'created':str (datetime .datetime .now ())}
            _active_tasks .append (task )
            _save_tasks (_active_tasks )
            await message .channel .send (
            f'✅ **Задача сохранена** (#{task["id"]}): *{desc[:100]}*\n'
            'Все задачи — команда `задача показать`.'
            )
            return True 

        task_list_words =['задача показать','покажи задачи','активные задачи',
        'список задач','задачи список']
        if any (t in cn for t in [self ._norm (x )for x in task_list_words ]):
            if not _active_tasks :
                await message .channel .send ('📭 Активных задач нет.')
            else :
                lines =[f'**#{t["id"]}** — {t["desc"][:80]}'for t in _active_tasks ]
                await message .channel .send (' **Активные задачи:**\n'+'\n'.join (lines ))
            return True 

        task_delete_words =['задача удалить','удали задачу','задача отмена']
        if any (t in cn for t in [self ._norm (x )for x in task_delete_words ]):
            import re as _re 
            num =_re .search (r'\d+',text )
            if num :
                tid =int (num .group ())
                before =len (_active_tasks )
                _active_tasks [:]=[t for t in _active_tasks if t ['id']!=tid ]
                _save_tasks (_active_tasks )
                if len (_active_tasks )<before :
                    await message .channel .send (f' Задача #{tid} удалена.')
                else :
                    await message .channel .send (f' Задача #{tid} не найдена.')
            else :
                await message .channel .send (' Какую задачу удалить? Укажи номер: `задача удалить 1`')
            return True 

            # СОСТОЯНИЕ СЕРВЕРА
        status_triggers =['кто на сервере','кто онлайн','кто в войсе','сколько человек онлайн',
        'что на сервере','что происходит на сервере','как дела на сервере',
        'кто активен','кто в голосовом','кто тут есть']
        if any (t in cn for t in [self ._norm (x )for x in status_triggers ]):
            lines =[]
            for guild in self .bot .guilds :
                import discord as _discord 
                online =[m for m in guild .members 
                if not m .bot and m .status !=_discord .Status .offline ]
                in_voice =[]
                for vc in guild .voice_channels :
                    members =[m .display_name for m in vc .members if not m .bot ]
                    if members :
                        in_voice .append (f'**{vc.name}**: {", ".join(members)}')
                lines .append (f'**{guild.name}**')
                lines .append (f'• Онлайн: {len(online)} человек')
                if in_voice :
                    lines .append ('• Голосовые каналы:\n  '+'\n  '.join (in_voice ))
                else :
                    lines .append ('• В голосовых каналах никого нет')
                ticket_chs =[c for c in guild .text_channels if c .name .startswith ('ticket-')]
                if ticket_chs :
                    lines .append (f'• Открытых тикетов: {len(ticket_chs)}')
            await message .channel .send ('\n'.join (lines )or ' Не удалось получить информацию о сервере.')
            return True 

            # Вкл/выкл уведомлений модерации
        mod_notify_ac =['включи уведомления модерации','уведомления модерации вкл',
        'присылай наказания в лс','включи оповещения о наказаниях']
        mod_notify_off =['выключи уведомления модерации','уведомления модерации выкл',
        'не присылай наказания','выключи оповещения о наказаниях']
        if any (t in cn for t in [self ._norm (x )for x in mod_notify_ac ]):
            import json as _j 
            os .makedirs ('data',exist_ok =True )
            with open ('data/mod_notify.json','w',encoding ='utf-8')as f :
                _j .dump ({'enabled':True },f )
            await message .channel .send (' Уведомления включены — действия модерации будут приходить в ЛС.')
            return True 
        if any (t in cn for t in [self ._norm (x )for x in mod_notify_off ]):
            import json as _j 
            os .makedirs ('data',exist_ok =True )
            with open ('data/mod_notify.json','w',encoding ='utf-8')as f :
                _j .dump ({'enabled':False },f )
            await message .channel .send (' Уведомления модерации отключены.')
            return True 

            # ни один обработчик не сработал — обычный разговор с AI
        return False 

    @commands .Cog .listener ()
    async def on_message (self ,message :discord .Message ):
        if message .author .bot :
            return 

        is_dm =isinstance (message .channel ,discord .DMChannel )

            # перехват ответа владельца в ЛС
        if is_dm and OWNER_ID and message .author .id ==OWNER_ID :
        # Если owner ответил реплаем на сообщение — это ответ на ожидающий вопрос?
            if message .reference and message .reference .message_id in _pending_questions :
                ref_id =message .reference .message_id 
                pending =_pending_questions .pop (ref_id )
                user_id =pending ['user_id']
                channel_id =pending ['channel_id']
                question =pending ['question']
                answer =message .content .strip ()

                # Cevabы knowledge base'e сохранить
                if pending .get ('guild_id'):
                    guild_key =str (pending ['guild_id'])
                    if guild_key not in _knowledge_base :
                        _knowledge_base [guild_key ]=[]
                    _knowledge_base [guild_key ].append ({
                    'type':'owner_answer',
                    'question':question ,
                    'info':answer ,
                    'confidence':'high',
                    'source':'owner'
                    })
                    _save_knowledge_base (_knowledge_base )

                    # Пользователю cevabы ilet
                try :
                    if pending .get ('is_dm'):
                        user =await self .bot .fetch_user (user_id )
                        await user .send (answer )
                    else :
                        channel =self .bot .get_channel (channel_id )
                        if channel :
                            user =channel .guild .get_member (user_id )
                            mention =user .mention if user else f'<@{user_id}>'
                            await channel .send (f'{mention} {answer}')
                    await message .add_reaction ('')
                except Exception as e :
                    await message .channel .send (f' Не удалось доставить: {e}')
                return 

                # умные действия владельца (распознавание намерений AI)
            content_lower =message .content .lower ().strip ()
            content_raw =message .content .strip ()

            # сохранение правил/предпочтений: «запомни», «всегда говори»…
            pref_triggers =['это мне не пиши','так не говори','так не делай',
            'делай всегда','говори всегда','запомни',
            'не забывай','имей в виду','теперь ты знаешь']
            if any (t in content_lower for t in pref_triggers ):
                _owner_prefs ['rules'].append (content_raw )
                if len (_owner_prefs ['rules'])>50 :
                    _owner_prefs ['rules']=_owner_prefs ['rules'][-50 :]
                _save_owner_prefs (_owner_prefs )
                await message .channel .send (f' Сохранил: **{content_raw[:100]}**')
                return 

                # AI с intent определить
            intent =await self ._detect_owner_intent (content_raw ,message )
            if intent :
                return # намерение обработано — обычный AI-ответ не нужен

        is_ticket_channel =False 
        is_ai_channel =(
        message .channel .id in AI_CHANNELS or 
        message .channel .id in _dynamic_channels or 
        is_ticket_channel 
        )

        if not (is_dm or is_ai_channel ):
            return 

        if is_ai_channel and not is_dm :
            is_allowed_ai =(
            message .channel .id in _dynamic_channels or 
            is_ticket_channel 
            )
            if not is_allowed_ai :
                return 
            if is_ticket_channel :
                lower_msg =message .content .lower ()
                insult_kws =['оскорб','мат','написал','ебал','рот','сук','хуй','дурак','идиот','обозва','жалоб','матер','шлюх','урод','мраз','гнид','пидор','соси']
                if any (w in lower_msg for w in insult_kws )or message .mentions :
                    return # cogs/ticket.py выполняет реальную судебную проверку логов и наказывает!
            content =re .sub (r'^moe\s*','',message .content ,flags =re .IGNORECASE ).strip ()
            for m in message .mentions :
                content =content .replace (f'<@{m.id}>','').replace (f'<@!{m.id}>','')
            content =content .strip ()or 'Здравствуйте!'
        else :
            content =message .content .strip ()or 'Здравствуйте!'

            # командный запрос владельца — режим J.A.R.V.I.S.
        if OWNER_ID and message .author .id ==OWNER_ID :
            cmd_triggers =['создай канал','новый канал','сделай объявление','объяви',
            'забань','кикни','выдай таймаут','дай роль','сними роль']
            if any (t in content .lower ()for t in cmd_triggers ):
                context ={}
                context ['jarvis_mode']=True 
                context ['available_commands']=(
                'Использовать команды:\n'
                '/moderate ban @user причина\n'
                '/moderate kick @user причина\n'
                '/moderate timeout @user minutes причина\n'
                '/роли @user @роли\n'
                '/utility clear количество\n'
                '/utility lock\n'
                '/utility unlock\n'
                'Каналы создаются в Discord: Настройки сервера → Каналы'
                )

        async with message .channel .typing ():
            recent_msgs =[]
            channel_ctx =[]

            if not is_dm and message .guild :
                recent_msgs =await _get_recent_user_messages (
                message .author .id ,message .guild ,limit =15 
                )
                channel_ctx =await _get_channel_context (message .channel ,limit =12 )

            answer =await self .bot .loop .run_in_executor (
            None ,_call_ai ,content ,message .author .id ,
            message .guild if not is_dm else None ,
            recent_msgs ,channel_ctx 
            )

        if _kufur_var_mi (answer ):
            answer ="Я не могу это сказать. "

            # Ответы "не знаю" — спросить у владельца
        bilmiyorum_triggers =['bilmiyorum','emin deгilim','info bulamadыm','о infom нет']
        if OWNER_ID and any (t in answer .lower ()for t in bilmiyorum_triggers ):
            try :
                owner =await self .bot .fetch_user (OWNER_ID )
                guild_id =message .guild .id if message .guild else 0 
                user_name =message .author .display_name 
                embed =discord .Embed (
                title =' Вопрос, на который я не нашел ответ',
                color =0xf59e0b ,
                description =f'**Спросил:** {user_name} (`{message.author.id}`)\n'
                f'**Вопрос:** {content}\n\n'
                '**Чтобы ответить, сделай reply на это сообщение.**'
                )
                embed .set_footer (text =f'Сервер: {message.guild.name if message.guild else "DM"}')
                dm_msg =await owner .send (embed =embed )
                _pending_questions [dm_msg .id ]={
                'user_id':message .author .id ,
                'channel_id':message .channel .id ,
                'question':content ,
                'guild_id':guild_id ,
                'is_dm':is_dm 
                }
            except Exception as e :
                log .info (f'[AI] Owner DM Ошибки: {e}')

        if is_dm :
        # DM log'a сохранить (входящее сообщение логгер DMLogger'a записывает,
        # здесь только bot cevabы сохранить, чтобы не дублировать)
            try :
                import json as _j ,os as _os ,datetime as _dt3 
                _os .makedirs ('data',exist_ok =True )
                _f ='data/dm_log.json'
                _d =_j .load (open (_f ,encoding ='utf-8'))if _os .path .exists (_f )else {}
                uid =str (message .author .id )
                if uid not in _d or not isinstance (_d [uid ],list ):
                    _d [uid ]=[]
                # Bot cevabыnы сохранить
                _d [uid ].append ({
                'author':'Aether',
                'content':answer ,
                'timestamp':_dt3 .datetime.now(_dt3 .timezone.utc).isoformat (),
                'from_bot':True ,
                })
                # держим максимум 200 сообщений
                _d [uid ]=_d [uid ][-200 :]
                with open (_f ,'w',encoding ='utf-8')as fp :
                    _j .dump (_d ,fp ,ensure_ascii =False ,indent =2 )
            except Exception as _le :
                log .info (f'[DM LOG] Ошибка: {_le}')
            await message .channel .send (answer )
        else :
            await message .reply (answer ,mention_author =False )


async def setup (bot ):
    cog =AIChat (bot )
    await bot .add_cog (cog )

    # Bot kapanыrken history'yi сохранить
    @bot .event 
    async def on_shutdown ():
        _save_histories (_histories ,force =True )
        log .info ('[AI] Разговор история сохранено.')
