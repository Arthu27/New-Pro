"""
Ticket AI — продвинутая система поддержки
Chain-of-thought reasoning, персонализация, проактивное поведение, function calling
"""

from logger import get_logger

_log = get_logger("ai_helper")

import os 
import json 
import re 
import datetime 
from typing import Dict ,List ,Optional ,Tuple 

# Import function calling system
try :
    from web .ai_functions import AIFunctions 
except ImportError :
    AIFunctions =None 

    # ─── БАЗА ЗНАНИЙ О БОТЕ ───────────────────────────────────────────────────────

def _bot_knowledge_base ()->str :
    """Полная база знаний о боте Hakumo (Discord)"""
    base ="""ПОЛНАЯ БАЗА ЗНАНИЙ О БОТЕ HAKUMO (Discord)
═══════════════════════════════════════════════════

## КОМАНДЫ БОТА (реальный боевой список — других команд НЕТ, не выдумывай!)

**Модерация** (модераторы):
- /modpanel — главная панель модератора: варн/снять варн/мут/бан/кик/чистка — всё через удобное окно с прикреплением демки
- /warnings @user — предупреждения участника
- /unwarn @user № — снять предупреждение
- /proofs [@user] — доказательства (демки) по серверу или участнику
- /proofdel № — удалить демку (админ)
- /proof @участник наказание причина + файл (или ссылка) — загрузить демку прямо из Discord: файл уходит в канал доказательств
- Загрузка демок — командой /proof в боте или на веб-панели, вкладка «Доказательства»

**Тикеты и команда**:
- /ticket-panel — разместить панель обращений (админ)
- участников тикета модератор добавляет/убирает кнопками ➕/➖ в меню тикета
- /staff-panel — панель набора в команду (админ)
- /my-application — статус моей заявки

**Репорты и разбор жалоб**:
- /report @участник причина [скрин/видео-файл или ссылка] — жалоба: создаётся
  приватная ветка с разбором; обвиняемый видит дело и свои прошлые нарушения
- /witness @user — позвать свидетеля в ветку репорта (модератор)
- /my_violations — мои нарушения, с кнопкой обжалования
- /апелляция — апелляция на наказание (подаётся в ЛС боту)
- /report-setup @роль [#канал] — настройка системы репортов (админ): без канала сама создаёт закрытый #репорты, видимый только модерации
- /report-settings — лестница рецидивов (1-е предупреждение, 2-е мут на день,
  3-е мут на неделю, 4-е бан) и срок давности (админ)
- Разбором управляет модератор: режимы обсуждения (по очереди / свободный /
  слово вручную), «дать слово», вынесение решения (дефолтное по рецидивам или
  индивидуальное: варн/мут/кик/бан/без наказания + срок). Закрытый тикет
  архивируется (переписка сжимается), ветка удаляется.

**Утилиты**:
- /afk [причина] — уйти в AFK (бот ответит на упоминания)
- /afk-remove — вернуться из AFK
- /апелляция — апелляция на наказание (в ЛС боту)
- /logs-setup — создать каналы логов (админ)

**Музыка** (префикс !):
- !play запрос — включить трек; !pause !resume !skip !queue !nowplaying
  !leave

**Автоматика бота** (работает сама, команд не нужно):
- Автомодерация: фильтр слов/ссылок/флуда/капса (настраивается в панели)
- Антирейд и верификация новичков
- Приветствия с красивыми карточками (настраиваются в панели)
- Логирование событий сервера в каналы логов
- AI-помощник: упомяни бота или напиши ? вопрос — отвечу

**Веб-панель Hakumo Panel**:
- Полное управление ботом через браузер (адрес даёт владелец)
- Роли доступа: owner / admin / curator / mod / uye
- Куратор — старший модератор (всё модерское + тикеты и сообщество)

Если пользователь спрашивает команду, которой нет в этом списке — честно скажи,
что такой функции сейчас нет, и предложи ближайшее из списка или веб-панель.
═══════════════════════════════════════════════════
ОТВЕЧАЙ КРАТКО И ТОЧНО. ЕСЛИ НЕ ЗНАЕШЬ КОМАНДУ — НЕ ВЫДУМЫВАЙ.
"""

    # Полная карта панели (разделы/страницы/роли) — генерируется из живого MENU
    try :
        from web .ai_knowledge import build_panel_knowledge
        base +="\n\n"+build_panel_knowledge (compact =True )
    except Exception as _ex:
        _log.debug("_bot_knowledge_base(): подавлено: %s", _ex )
    return base


    # ─── ОПРЕДЕЛЕНИЕ КАТЕГОРИИ (AI) ─────────────────────────────────────────────

def _detect_category_ai (message :str ,history :List [Dict ])->str :
    """Определение категории через AI (не по ключевым словам)"""
    prompt ="""Определи категорию обращения пользователя в Discord-тикете.

КАТЕГОРИИ:
- complaint: жалоба на другого пользователя (оскорбления, спам, токсичность)
- question: вопрос о боте, панели, командах, ролях, экономике
- technical: техническая проблема (что-то не работает, ошибка)
- other: всё остальное (болтовня, приветствие, неясное)

ПРАВИЛА:
- Если «мне пишут гадости в ЛС» — это complaint
- Если «как сделать X?» — это question
- Если «что-то не работает или выдаёт ошибку» — это technical
- Если просто болтает или непонятно — это other

Ответь ТОЛЬКО одним словом: complaint, question, technical или other.
Без пояснений, без точек, без кавычек.

Сообщение пользователя: """

    messages =[
    {'role':'user','content':prompt +message }
    ]

    try :
        from web .model_selector import smart_call 
        result ,_ ,_ =smart_call (messages ,task_type ='category_detection',max_tokens =10 ,temperature =0.1 )
        result =result .strip ().lower ()
        if result in ('complaint','question','technical','other'):
            return result 
    except Exception as _ex:
        _log.debug("_detect_category_ai(): подавлено: %s", _ex)

        # Fallback на keyword-based
    return _detect_category_fallback (message )


def _detect_category_fallback (message :str )->str :
    """Fallback: определение категории по ключевым словам"""
    msg =message .lower ()
    complaint_words =['жалоба','oskorblyaet','spamit','toksicniy','materitsya','ugrojaet','travit']
    technical_words =['не работает','ошибка','bag','sloazs','vidaet ошибка','не mogu']
    question_words =['как','где','ne время','ne','почему','zacem','mюmkюn ли']

    if any (w in msg for w in complaint_words ):
        return 'complaint'
    if any (w in msg for w in technical_words ):
        return 'technical'
    if any (w in msg for w in question_words ):
        return 'question'
    return 'other'


    # ─── PROMPTI С CHAIN-OF-THOUGHT ─────────────────────────────────────────────

def _prompt_complaint ()->str :
    """Prompt для жалоб: собрать факты и передать модератору.

    Заказ владельца 2026-08-26: ИИ НИКОГДА не наказывает сам — ни мут,
    ни варн, ни что-либо ещё. Единственное «действие» — позвать
    модератора (ACTION:ESCALATE). Решение всегда за человеком.
    """
    return """Ты — AI-помощник Discord-сервера. Отвечай на русском.

ПОЛУЧЕНА ЖАЛОБА. Твоя задача:
1. ПРОАНАЛИЗИРУЙ ситуацию (кто, что, когда)
2. СОБЕРИ информацию:
   - Спроси, кто нарушитель (Discord ID или @упоминание)
   - Спроси, в каком канале произошло
   - Попроси доказательства (скриншоты, ссылки на сообщения)
3. УСПОКОЙ пользователя и скажи, что модераторы разберутся

ЖЁСТКИЕ ПРАВИЛА:
- Ты НЕ применяешь наказания и даже НЕ предлагаешь их (никаких мутов,
  варнов, банов, киков, тюрем). Наказания выдаёт только модератор-человек.
- Не выдумывай факты, имена и цифры. Чего не знаешь — того не знаешь.
- НЕ проси скриншоты, если их уже прислали
- НЕ предлагай «открыть тикет» — мы уже в тикете
- Будь эмпатичным, но профессиональным
- Нарушение серьёзное или не хватает данных → на новой строке
  ACTION:ESCALATE — позвать модератора. Это твоё единственное действие.

ФОРМАТ ОТВЕТА:
Только текст ответа пользователю; при необходимости последней строкой
ACTION:ESCALATE
"""


def _prompt_question ()->str :
    """Prompt для soruov — chain-of-thought"""
    return """Ты — AI-помощник Discord-сервера. Отвечай на русском.

ПОЛУЧЕН ВОПРОС. Твоя задача:
1. ПОЙМИ вопрос (о чём именно спрашивают)
2. ПРОВЕРЬ базу знаний (знаешь ли ответ)
3. ОТВЕТЬ чётко и кратко:
   - Знаешь → дай ответ + пример использования
   - Не уверен → скажи «Не уверен, но…» + лучшее предположение
   - Не знаешь → ACTION:ESCALATE (передать модератору)

ПРАВИЛА:
- Отвечай максимум в 2-3 предложения
- Давай конкретные команды с примером
- НЕ предлагай «открыть тикет» — мы уже в тикете
- Если вопрос о другом пользователе — не раскрывай личную информацию

ПРИМЕР ХОРОШИХ ОТВЕТОВ:
В: Как забанить спамера?
О: Используй `/moderate ban @user причина`. Например: `/moderate ban @spammer Спам в чате`. Бот отправит DM пользователю и запишет в логи.

В: Как повысить уровень?
О: Пиши сообщения в чате и сиди в голосовых каналах — получаешь XP. Проверь уровень: `!xp-rank`. Топ-10: `!xp-leaderboard`.
"""


def _prompt_technical ()->str :
    """Промпт для технических проблем — chain-of-thought"""
    return """Ты — AI техподдержки Discord-сервера. Отвечай на русском.

ТЕХНИЧЕСКАЯ ПРОБЛЕМА. Твоя задача:
1. ДИАГНОСТИРУЙ проблему (что именно не работает)
2. ПРЕДЛОЖИ решения (минимум 2 варианта):
   - Самое вероятное решение
   - Альтернативное решение
3. ПОШАГОВО объясни, как выполнить решение
4. Если не помогло → ACTION:ESCALATE

ПРАВИЛА:
- Начиная с самого простого решения
- Давай пошаговые инструкции (1, 2, 3...)
- Если нужна команда — укажи точно с примером
- НЕ предлагай «открыть тикет» — мы уже в тикете
- Если проблема сложная и ты не уверен → сразу ACTION:ESCALATE

ПРИМЕР:
В: Музыка не играет
О: Давай проверим:
1. Ты в голосовом канале? (бот должен быть в том же канале)
2. Попробуй `!leave`, затем снова `!play [название]`
3. Проверь, что у бота есть права на управление голосовыми каналами

Если не помогло — передаю модератору.
"""


def _prompt_other ()->str :
    """Prompt для drugih obraseniy — chain-of-thought"""
    return """Ты — AI-помощник Discord-сервера. Отвечай на русском.

ОБРАЩЕНИЕ НЕЯСНО. Твоя задача:
1. ПОЙМИ, чего хочет пользователь
2. УТОЧНИ, если непонятно (задай 1 вопрос)
3. ПОМОГИ, если можешь
4. Если не можешь → ACTION:ESCALATE

ПРАВИЛА:
- Будь дружелюбным
- Задавай максимум 1 уточняющий вопрос
- Если пользователь просто болтает — поддержи разговор
- Если проблема серьёзная — передай модератору
"""


def _get_prompt_by_category (category :str )->str :
    """Получить prompt по kategoriler"""
    prompts ={
    'complaint':_prompt_complaint (),
    'question':_prompt_question (),
    'technical':_prompt_technical (),
    'other':_prompt_other (),
    }
    return prompts .get (category ,_prompt_other ())


    # ─── ГЛАВНАЯ ФУНКЦИЯ — AI TICKET RESPONSE ───────────────────────────────────

async def ai_ticket_response (user_message :str ,history :List [Dict ],guild_context :Dict )->Tuple [str ,bool ,str ,List [Dict ],str ]:
    """
    Главная функция AI-ответа в тикете.

    Returns:
        (response, should_escalate, escalation_category, updated_history, detected_category)
    """
    # 1. Belirliyoruz kategori с с AI
    category =_detect_category_ai (user_message ,history )

    # 2. Alыyoruz prompt для kategoriler
    system_prompt =_get_prompt_by_category (category )

    # 3. Topluyoruz baгlam
    messages =[{'role':'system','content':system_prompt }]

    # Данныеtabanы информация (для question/technical/other)
    if category in ('question','technical','other'):
        messages .append ({'role':'system','content':_bot_knowledge_base ()})

        # 4. Personalizaciya — информация о у пользователя
    user_info =[]
    if guild_context .get ('user_name'):
        user_info .append (f"Isim: {guild_context['user_name']}")
    if guild_context .get ('user_roles'):
        user_info .append (f"Роли: {', '.join(guild_context['user_roles'])}")
    if guild_context .get ('user_joined_days'):
        days =guild_context ['user_joined_days']
        if days <7 :
            user_info .append (f"На на сервере: {days} dn. (новый участник)")
        else :
            user_info .append (f"На на сервере: {days} dn.")
    if guild_context .get ('previous_tickets'):
        prev =guild_context ['previous_tickets']
        user_info .append (f"Предыдущих тикетов: {len(prev)}")
        if prev :
            last =prev [-1 ]
            user_info .append (f"В конец ticket: {last.get('category', '?')} ({last.get('status', '?')})")

    if user_info :
        messages .append ({
        'role':'system',
        'content':"ИНФОРМАЦИЯ О У ПОЛЬЗОВАТЕЛЯ:\n"+"\n".join (user_info )
        })

        # 5. Baгlam сервер
    server_info =[]
    if guild_context .get ('guild_name'):
        server_info .append (f"Сервер: {guild_context['guild_name']}")
    if guild_context .get ('member_count'):
        server_info .append (f"Участников: {guild_context['member_count']}")
    if guild_context .get ('panel_url'):
        server_info .append (f"URL paneli: {guild_context['panel_url']}")

    if server_info :
        messages .append ({
        'role':'system',
        'content':"КОНТЕКСТ СЕРВЕРА:\n"+"\n".join (server_info )
        })

        # 5.5. Function calling — описание eriшadlerin fonksiyonlarыn
    guild =guild_context .get ('guild')
    ai_functions =None 
    if guild and AIFunctions :
        ai_functions =AIFunctions (guild .client )
        messages .append ({
        'role':'system',
        'content':ai_functions .get_available_functions ()
        })

        # 5.6. Samoobucenie — baгlam из viucennih patternov
    try :
        from web .self_learning import get_self_learning 
        self_learning =get_self_learning ()
        learning_context =self_learning .get_learning_context (user_message )
        if learning_context :
            messages .append ({
            'role':'system',
            'content':f"КОНТЕКСТ ОБУЧЕНИЯ (используй для улучшения ответа):\n{learning_context}"
            })
    except Exception as e :
        print (f"[AI] Ошибка загрузки контекста обучения: {e}")

        # 6. История разговор (son 20 сообщение)
    if history :
        messages .extend (history [-20 :])

        # 7. Tekusee сообщение
    messages .append ({'role':'user','content':user_message })

    # 8. Чтяжелыйыyoruz AI с function calling (maksimum 3 iteracii)
    # Vibiraem тип задачи для multi-modelnosti
    task_type_map ={
    'complaint':'complaint_analysis',
    'question':'technical_support',
    'technical':'technical_support',
    'other':'general_chat'
    }
    task_type =task_type_map .get (category ,'general_chat')

    max_iterations =3 
    for iteration in range (max_iterations ):
        from web .model_selector import smart_call 
        response ,_ ,_ =smart_call (messages ,task_type =task_type ,max_tokens =2048 ,temperature =0.7 )

        # Контроль ediyoruz есть ли vizovi fonksiyonlarыn
        func_calls =re .findall (r'\[FUNC:[^\]]+\]',response )

        if not func_calls or not ai_functions or not guild :
        # Нет vizovov fonksiyonlarыn или function calling deгileriшadlerin — выходim
            break 

            # Vipolnyaem fonksiyonlar
        for func_call in func_calls [:3 ]:# Maksimum 3 fonksiyonlar для kez
            result =await ai_functions .execute_function (func_call ,guild )
            if result :
            # Ekliyoruz результат fonksiyonlar в baгlam
                messages .append ({
                'role':'system',
                'content':f"РЕЗУЛЬТАТ FONKSIYONLAR {func_call}:\n{result}"
                })

                # Убрать вызовы функций из ответа
    response =re .sub (r'\[FUNC:[^\]]+\]','',response ).strip ()

    # 9. Отдельношtыrыyoruz записейler
    should_escalate =False 
    if 'ACTION:ESCALATE'in response :
        should_escalate =True 
        response =response .replace ('ACTION:ESCALATE','').strip ()

        # Удален chain-of-thought bloki если есть
        # (re уже импортирован глобально, повторный импорт не нужен)

    if not response :
        response ="Обрабатываю ваш запрос..."

        # 10. Обновл история
    updated_history =history +[
    {'role':'user','content':user_message },
    {'role':'assistant','content':response }
    ]

    # Ограничиваем история 30 сообщениями
    if len (updated_history )>30 :
        updated_history =updated_history [-30 :]

        # 11. Автоматически izvlecenie ve sohranenie gerчдобавитьr
    if guild and ai_functions :
        try :
            from web .ai_rag import ConversationAnalyzer 
            facts =ConversationAnalyzer .extract_facts (updated_history [-5 :])

            if facts :
                user_id =guild_context .get ('user_id')
                if user_id :
                    for fact in facts [:2 ]:# Maksimum 2 fakta для kez
                        await ai_functions .remember_fact (guild ,user_id ,fact )
        except Exception as e :
            print (f"[AI] Ошибка извлечения фактов: {e}")

            # 12. Сохраняем ответ для самообучения (проанализируется позже)
    try :
        from web .self_learning import get_self_learning 
        self_learning =get_self_learning ()

        # Проверяем длину ответа — если очень короткий, возможна проблема
        if len (response )<10 :
            self_learning .record_mistake (
            user_message =user_message ,
            ai_response =response ,
            correct_response ='',
            mistake_type ='too_short_response'
            )
            # Если ответ длинный и подробный — возможен успех
        elif len (response )>200 and category in ['question','technical']:
            self_learning .record_success (
            user_message =user_message ,
            ai_response =response ,
            success_type ='detailed_response'
            )
    except Exception as e :
        print (f"[AI] Ошибка записи для обучения: {e}")

    return response ,should_escalate ,category ,updated_history ,category 


    # ─── ПРИВЕТСТВИЕ ─────────────────────────────────────────────────────────────

def ai_ticket_greeting (category :str =None )->str :
    """Приветственное сообщение при открытии тикета"""
    return (
    "## Здравствуйте! Я — AI-ассистент\n\n"
    "Я помогу решить вашу проблему.\n\n"
    "**Опишите, что произошло:**\n"
    "- Что не работает?\n"
    "- Какую ошибку видите?\n"
    "- Что уже пробовали?\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "-# Если я не смогу помочь — передам модератору."
    )


    # ─── PARSING ДЕЙСТВИЕ ───────────────────────────────────────────────────────

def parse_ai_actions (response :str )->Dict :
    """Разбор записей из ответа AI.

    Заказ владельца 2026-08-26: ИИ не наказывает. Любые ACTION:WARN /
    ACTION:JAIL / ROLE_ASSIGN / CHANNEL_REDIRECT / DELETE_MESSAGES,
    даже если модель их выдала, НЕИЗМЕННО игнорируются и вычищаются из
    текста. Работает только ACTION:ESCALATE — позвать модератора.
    """
    import re

    actions ={
    'escalate':'ACTION:ESCALATE'in response ,
    'варн':None ,
    'тюрьма':None ,
    'role_assign':None ,
    'channel_redirect':None ,
    'delete_messages':None ,
    }

    # Модель пыталась наказать? Чистим и пишем в лог — но не исполняем.
    _forbidden =re .search (
    r'ACTION:(WARN|JAIL|ROLE_ASSIGN|CHANNEL_REDIRECT|DELETE_MESSAGES)[^\n]*',response )
    if _forbidden :
        _log .warning ("parse_ai_actions(): ИИ предложил '%s' — ОТКЛОНЕНО. "
                       "Наказания применяет только модератор.",_forbidden .group (0 )[:80 ])

    # Вычищаем ВСЕ служебные маркеры из текста ответа
    response =re .sub (r'ACTION:(WARN|JAIL|ROLE_ASSIGN|CHANNEL_REDIRECT|DELETE_MESSAGES|ESCALATE)[^\n]*','',response )

    # Удален pustie satыrlar
    response ='\n'.join (line for line in response .split ('\n')if line .strip ())

    actions ['cleaned_response']=response
    return actions


    # ─── OBUCENIE DEN CEVAPLARIN МОДЕРАТОР ────────────────────────────────────────

def learn_from_staff (staff_message :str ,user_question :str ,guild_id :int ):
    """Автоматическое обучение из ответов модератора"""
    try :
        faq_file ='data/faq_learned.json'
        faqs ={}
        if os .path .exists (faq_file ):
            with open (faq_file ,'r',encoding ='utf-8')as f :
                faqs =json .load (f )

        guild_key =str (guild_id )
        if guild_key not in faqs :
            faqs [guild_key ]=[]

            # Добавляем вопрос-ответ
        faqs [guild_key ].append ({
        'question':user_question ,
        'answer':staff_message ,
        'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat ()
        })

        # Ограничиваем 100 записьyami
        if len (faqs [guild_key ])>100 :
            faqs [guild_key ]=faqs [guild_key ][-100 :]

        with open (faq_file ,'w',encoding ='utf-8')as f :
            json .dump (faqs ,f ,ensure_ascii =False ,indent =2 )

    except Exception as e :
        print (f"[AI LEARN] Ошибка обучения: {e}")


def get_learned_faqs (guild_id :int )->List [Dict ]:
    """Получить viucennie FAQ для сервер"""
    try :
        faq_file ='data/faq_learned.json'
        if os .path .exists (faq_file ):
            with open (faq_file ,'r',encoding ='utf-8')as f :
                faqs =json .load (f )
            return faqs .get (str (guild_id ),[])
    except Exception as _ex:
        _log.debug("get_learned_faqs(): подавлено: %s", _ex)
    return []


    # ─── ОБЩИЙ LLM ЧAГRI VE AKILLI YEDEK (FALLBACK) СИСТЕМА ───────────────────────
import time 
import urllib .request 
import urllib .error 

def _local_moebius_fallback (messages :List [Dict ])->Tuple [str ,str ,Dict ]:
    """
    Умный автономный AI-ассистент Hakumo/Moebius (работает 100% без внешних API-ключей!).
    """
    last_msg =""
    sys_prompt =""
    for m in messages :
        if m .get ("role")=="system":
            sys_prompt +="\n"+str (m .get ("content",""))
        elif m .get ("role")=="user":
            last_msg =str (m .get ("content","")).strip ()

    q_lower =last_msg .lower ()

    # 1. Приветствие / Салют
    if any (k in q_lower for k in ["привет","здравствуй","хай","салют","доброе утро","добрый вечер","selam","merhaba","hey","hakumo","moebius"]):
        return (
        "Привет, дружище! Я Hakumo, AI-ассистент сервера Discord. 🤖\n"
        "Отвечаю на вопросы, помогаю с панелью и настройками. Наказания выдаёт только модератор-человек — я лишь помогаю разобраться. Чем могу помочь?",
        "moebius-offline-ai",
        {"provider":"fallback","latency_ms":10 }
        )

        # 1.5. Поиск сообщений пользователя ("покажи сообщения X" / "найди сообщения")
        # В офлайн-режиме (нет LLM) — честно говорим что не можем выполнить поиск
        # и предлагаем решение, вместо выдумывания результата.
        # ВАЖНО: этот блок стоит ПЕРЕД блоком "Прощание", иначе слово "покажи"
        # ошибочно триггерит "пока" → "До встречи, дружище!".
        # Игнорируем если речь о правилах/командах/помощи — это другой кейс.
    if (any (k in q_lower for k in [
    "покажи сообщ","найди сообщ","выведи сообщ","историю сообщ",
    "последние сообщ","что писал","где писал","искать сообщ"
    ])or (
    # "найди сообщения mrxway" / "покажи mrxway" — ловим по контексту
    any (w in q_lower for w in ['mrxway','покажи','найди','выведи','историю'])
    and re .search (r'сообщ',q_lower )
    ))and not any (ex in q_lower for ex in ['правил','команд','помощь','помощи','help','kurallar','kural']):
        target_id_m2 =re .search (r'\b(\d{17,20})\b',last_msg )
        target_name_m2 =re .search (r'@([\w\.\-_]+)',last_msg )
        if target_id_m2 :
            target_str =f"<@{target_id_m2.group(1)}>"
        elif target_name_m2 :
            target_str =f"@{target_name_m2.group(1)}"
        else :
            target_str ="указанного пользователя"

            # Проверим, есть ли лог-файл бота (даже в офлайн-режиме)
        log_status ="не найден (бот ещё не записал ни одного сообщения)"
        try :
            import json as _jj 
            _target_gid =os .getenv ('MAIN_GUILD_ID','')or 'unknown'
            _log_f =f'data/message_log_{_target_gid}.json'
            if os .path .exists (_log_f ):
                try :
                    with open (_log_f ,'r',encoding ='utf-8')as _lfp :
                        _ldata =_jj .load (_lfp )
                    log_status =f"существует, содержит {len(_ldata)} сообщений (но я не могу их отфильтровать в офлайн-режиме)"
                except Exception :
                    log_status ="повреждён или недоступен"
        except Exception as _ex:
            _log.debug("_local_moebius_fallback(): подавлено: %s", _ex)

        return (
        f"🔍 **Поиск сообщений {target_str}:**\n\n"
        "К сожалению, в текущем автономном (офлайн) режиме я не могу выполнить "
        "полноценный поиск сообщений через Discord API.\n\n"
        "**Что нужно сделать:**\n"
        "• Проверьте подключение к AI-сервису (Mistral/Ollama) — тогда я смогу "
        "вызвать функцию `search_user_messages` и дать точный ответ.\n"
        "• Или используйте веб-панель → раздел «Пользователи» для просмотра истории.\n"
        "• Или команду `/history @пользователь` в Discord.\n\n"
        f"**Статус лога бота:** {log_status}\n\n"
        "Я не буду выдумывать содержимое сообщений — лучше честно сказать, что поиск "
        "сейчас недоступен, чем дать вам недостоверную информацию. 🙏",
        "moebius-offline-ai",
        {"provider":"fallback","latency_ms":11 }
        )

        # 1.6. «Как настроить X?» — пошаговые гайды из базы знаний.
        # Стоит раньше остальных блоков, чтобы «как настроить варны/тикеты/...»
        # не перехватывалось общими ключами (экономика, тикеты и т.д.).
    # «настро» ловит и infinitive «настроить», и «настройку» — но не «настроение»
    if (any (k in q_lower for k in ["настро","как включить","как выключить","где включается","где выключается","куда нажать","как поставить","как подключить","как завести","как поменять","как сменить"])and "настроени" not in q_lower ):
        try :
            from web .ai_knowledge import build_setup_faq
            return (
            build_setup_faq (last_msg ),
            "moebius-offline-ai",
            {"provider":"fallback","latency_ms":11 }
            )
        except Exception as _ex:
            _log.debug("_local_moebius_fallback(): подавлено: %s", _ex )

        # 2. Как дела / Как жизнь / Что нового
    if any (k in q_lower for k in ["как дела","как жизнь","что нового","как ты","как самочувствие","насылсын","набер"]):
        return (
        "У меня всё отлично, дружище! 🚀 Системы сервера работают стабильно, логи и защита 24/7 под контролем.\n"
        "А у тебя как дела? Есть вопросы по серверу или нужна помощь с командами?",
        "moebius-offline-ai",
        {"provider":"fallback","latency_ms":10 }
        )

        # 3. Кто ты / Расскажи о себе
    if any (k in q_lower for k in ["кто ты","что ты такое","расскажи о себе","ты кто","что за бот","кто ты такой"]):
        return (
        "Я Hakumo (Moebius) — многофункциональный AI-ассистент и защитник этого Discord-сервера! 🤖\n"
        "• Моя задача — охранять сервер от спама и рейдов, помогать участникам в тикетах поддержки и управлять ролями.\n"
        "• Чтобы узнать все мои возможности, просто напиши «команды» или «помощь»!",
        "moebius-offline-ai",
        {"provider":"fallback","latency_ms":11 }
        )

        # 4. Благодарность (Спасибо / Спс)
    if any (k in q_lower for k in ["спасибо","спс","благодарю","сяп","thank","tшk","teшekkюr"]):
        return (
        "Всегда пожалуйста, дружище! ❤️ Рад был помочь. Если понадобится что-то ещё — обращайся в любое время. 👊",
        "moebius-offline-ai",
        {"provider":"fallback","latency_ms":10 }
        )

        # 5. Прощание (Пока / До свидания / Удачи)
    # \b-границы: иначе «покажи правила» ошибочно ловилось подстрокой «пока»
    if re .search (r'\bпока\b|до свидания|\bудачи\b|спокойной ночи|до встречи|\bбывай\b',q_lower ):
        return (
        "До встречи, дружище! Я остаюсь на посту и продолжаю следить за безопасностью сервера. 🛡️ Удачи!",
        "moebius-offline-ai",
        {"provider":"fallback","latency_ms":10 }
        )

        # 6. Кто владелец / Создатель
    if any (k in q_lower for k in ["кто владелец","создатель","админ","кто создатель","владелец сервера","овнер"]):
        return (
        "Управление сервером и ботом находится в надежных руках нашей администрации и владельца сервера. 👑\n"
        "Если у вас есть важный вопрос или предложение к руководству, вы можете создать тикет поддержки!",
        "moebius-offline-ai",
        {"provider":"fallback","latency_ms":11 }
        )

        # 7. Музыка (play / песня / музыка)
    if any (k in q_lower for k in ["музыка","песня","трек","слушать","play","мьюзик"]):
        return (
        "🎵 **Музыкальный модуль Hakumo:**\n"
        "• Чтобы включить музыку, зайдите в голосовой канал и используйте команду `/play <название или ссылка>`.\n"
        "• Для управления воспроизведением используйте `/pause`, `/skip` и `/queue`.\n"
        "Приятного прослушивания! 🎧",
        "moebius-offline-ai",
        {"provider":"fallback","latency_ms":12 }
        )

        # 8. Экономика и Магазин
    if any (k in q_lower for k in ["экономика","монеты","баланс","деньги","магазин","shop","монета","эко"]):
        return (
        "💰 **Экономика сервера Hakumo:**\n"
        "• Вы можете зарабатывать монеты за активность в чатах и голосовых каналах!\n"
        "• Проверить свой баланс можно командой `/economy`, а заглянуть в магазин ролей — командой `/shop`.",
        "moebius-offline-ai",
        {"provider":"fallback","latency_ms":12 }
        )

        # 9. AFK статус
    if any (k in q_lower for k in ["афк","afk"]):
        return (
        "🌙 **Режим AFK:**\n"
        "• Чтобы включить статус «нет на месте», используйте команду `/afk [причина]`.\n"
        "• Когда кто-то упомянет вас в чате, бот автоматически сообщит, что вы сейчас заняты!",
        "moebius-offline-ai",
        {"provider":"fallback","latency_ms":11 }
        )

        # 10. Изученный FAQ (Self-Learned FAQ)
    faq_match =re .search (r'ВОПРОС:\s*([^\n]+)\nОТВЕТ АДМИНИСТРАЦИИ:\s*([^\n]+)',sys_prompt ,re .IGNORECASE )
    if faq_match :
        q_matched =faq_match .group (1 ).strip ()
        a_matched =faq_match .group (2 ).strip ()
        return (
        "💡 **Ответ из базы знаний сервера (FAQ):**\n"
        f"• **Вопрос:** *{q_matched}*\n"
        f"• **Решение администрации:** {a_matched}\n\n"
        "Если у вас остались дополнительные вопросы, вы всегда можете создать тикет поддержки!",
        "moebius-offline-ai",
        {"provider":"fallback","latency_ms":10 }
        )

        # 11. Безопасность и досье участника (@участник / ID)
    user_id_m =re .search (r'\b(\d{17,20})\b',last_msg )
    user_name_m =re .search (r'@([\w\.\-_]+)',last_msg )
    if user_id_m or user_name_m :
        target =user_id_m .group (1 )if user_id_m else user_name_m .group (1 )
        w_count =0 
        w_reasons =[]
        import os ,json as _json 
        if os .path .exists ('data/warnings.json'):
            try :
                with open ('data/warnings.json','r',encoding ='utf-8')as _fp :
                    _wd =_json .load (_fp )
                for _gid ,_gw in _wd .items ():
                    for _uid ,_ws in _gw .items ():
                        if _uid ==target or target .lower ()in str (_uid ).lower ():
                            w_count +=len (_ws )
                            w_reasons .extend ([_w .get ('reason','?')for _w in _ws ])
            except Exception as _ex:
                _log.debug("_local_moebius_fallback(): подавлено: %s", _ex)
        m_count =0 
        if os .path .exists ('data/mod_data.json'):
            try :
                with open ('data/mod_data.json','r',encoding ='utf-8')as _fp :
                    _md =_json .load (_fp )
                for _case in _md .get ('case',{}).values ():
                    for _c in _case :
                        if str (_c .get ('user_id',''))==target :
                            m_count +=1 
            except Exception as _ex:
                _log.debug("_local_moebius_fallback(): подавлено: %s", _ex)
        return (
        f"👤 **Анализ безопасности пользователя ({target}):**\n"
        f"• **Количество предупреждений:** {w_count} шт."+(f" (*Последние причины: {', '.join(w_reasons[:3])}*)"if w_reasons else "")+"\n"
        f"• **Количество дел модерации:** {m_count} записей\n"
        f"• Подробную историю пользователя можно посмотреть командой `/history {target}` или на вкладке **Пользователи** в веб-панели.",
        "moebius-offline-ai",
        {"provider":"fallback","latency_ms":14 }
        )

        # 12. Правила сервера (RAG)
    if any (k in q_lower for k in ["kural","kurallar","запрет","наказание maddesi","neler запрет","правило","правила","запрещено","нельзя","запрет"]):
        rule_lines =[]
        import re as _r 
        for r_match in _r .finditer (r'(Правило\s*#\d+:[^\n]+)',sys_prompt ):
            if r_match .group (1 )not in rule_lines :
                rule_lines .append (f"• {r_match.group(1)}")
        if not rule_lines :
            import os ,json as _j 
            for rf in [f"data/rules_{os .getenv ('MAIN_GUILD_ID','0')}.json","data/rules.json"]:
                if os .path .exists (rf ):
                    try :
                        with open (rf ,'r',encoding ='utf-8')as _fp :
                            _rd =_j .load (_fp )
                            for _ritem in _rd .get ('rules',[]):
                                rtext =_ritem .get ('text','')
                                if rtext and f"• {rtext}"not in rule_lines :
                                    rule_lines .append (f"• {rtext}")
                            if rule_lines :
                                break 
                    except Exception as _ex:
                        _log.debug("_local_moebius_fallback(): подавлено: %s", _ex)
        if not rule_lines :
            rule_lines =[
            "• Правило #1: Уважение и вежливость — Запрещены оскорбления, мат, унижения и язык вражды.",
            "• Правило #2: Спам и Флуд — Запрещена массовая отправка сообщений, реклама и ссылки без разрешения.",
            "• Правило #3: Голосовые каналы — Запрещено шуметь, включать посторонние звуки и мешать воспроизведению музыки.",
            "• Правило #4: Решения администрации — Уважайте действия модераторов; обжалование наказаний проводится через тикеты.",
            "• Правило #5: Конфиденциальность и безопасность — Запрещено распространение личных данных и вредоносных ссылок."
            ]
        return (
        "📜 **Свод правил сервера Hakumo:**\n"
        +"\n".join (rule_lines [:5 ])+
        "\n\nПожалуйста, соблюдайте правила сервера. За нарушения модераторы применяют наказания (варн/мут/кик/бан) — решения принимает человек.",
        "moebius-offline-ai",
        {"provider":"fallback","latency_ms":11 }
        )

        # 13. Дуюру (Announcement)
    if "объявление"in q_lower or "announcement"in q_lower or "объявление"in q_lower or "анонс"in q_lower or "новость"in q_lower :
        topic_m =re .search (r"'([^']+)'",last_msg )
        topic_val =topic_m .group (1 )if topic_m else "Обновление сервера"
        return (
        f"📢 **{topic_val.upper()}**\n\n"
        f"Уважаемые участники, на нашем сервере по теме **{topic_val}** проводятся необходимые обновления и улучшения.\n"
        "• Пожалуйста, соблюдайте правила сервера и следите за объявлениями администрации.\n"
        "• Для вопросов или обратной связи используйте каналы поддержки.\n\n"
        "✨ *Администрация Hakumo*",
        "moebius-offline-ai",
        {"provider":"fallback","latency_ms":12 }
        )

        # 14. Модерационный отчет — ТОЛЬКО реальные цифры из audit_log
        # (тот же источник, что /mod-report). Нет данных — честно говорим
        # «нет данных», ничего не выдумываем и не советуем наказания.
    if any (k in q_lower for k in ["rapor","deгerlendirme raporu","еженедельный","отчет","отчёт","еженедельный","сводка","активност"]):
        facts =[]
        total =0 
        try :
            from web .routes .analytics_plus import _read_audit ,_parse_ts 
            from datetime import datetime as _dt ,timedelta as _td 
            _gid =int (os .getenv ('MAIN_GUILD_ID','0')or 0 )
            cutoff =_dt .now ()-_td (days =7 )
            per_mod ={}
            for ev in _read_audit (_gid ):
                if ev .get ('category')!='mod':
                    continue 
                _ts =_parse_ts (ev .get ('timestamp'))
                if _ts is None or _ts <cutoff :
                    continue 
                total +=1 
                _mn =str (ev .get ('mod_name')or '').strip ()
                if _mn :
                    per_mod [_mn ]=per_mod .get (_mn ,0 )+1 
            if per_mod :
                top =sorted (per_mod .items (),key =lambda kv :kv [1 ],reverse =True )
                facts .append ("• **Активность модераторов за 7 дней:**")
                facts +=[f"  — {name}: {cnt} д." for name ,cnt in top [:8 ]]
            if total ==0 and not per_mod :
                return (
                "📊 **Отчёт модерации за 7 дней:**\n\n"
                "За последнюю неделю в журнале модерации нет ни одного записанного "
                "действия. Это честные данные из журнала бота (audit_log), ничего "
                "выдуманного.\n\n"
                "Как только модераторы начнут выдавать наказания через команды бота — "
                "цифры появятся здесь и на странице «Отчёты» панели.",
                "moebius-offline-ai",
                {"provider":"fallback","latency_ms":12 }
                )
        except Exception as _ex:
            _log.debug("_local_moebius_fallback(): подавлено: %s", _ex)
            return (
            "📊 **Отчёт модерации:** данные журнала сейчас недоступны, поэтому я "
            "не буду называть никакие цифры — выдумывать не стану. Точные данные "
            "всегда на странице «Отчёты» в панели.",
            "moebius-offline-ai",
            {"provider":"fallback","latency_ms":12 }
            )
        return (
        f"📊 **Отчёт модерации за 7 дней** (реальные данные журнала):\n\n"
        f"• **Всего мод-действий:** {total}\n"
        +"\n".join (facts )+
        "\n\nПодробные графики — панель → «Отчёты». Нужны детали по конкретному "
        "модератору или действию — спросите, я разберу по журналу.",
        "moebius-offline-ai",
        {"provider":"fallback","latency_ms":15 }
        )

        # 15. Эмбеды
    if "embed"in q_lower or "эмбед"in q_lower :
        return (
        "📌 Здесь отображаются правила сервера, объявления и информационные сообщения в аккуратном формате.\n"
        "Просим всех участников общаться с уважением и соблюдать правила сервера.",
        "moebius-offline-ai",
        {"provider":"fallback","latency_ms":10 }
        )

        # 16. Сервер состояние / онлайн
    if any (k in q_lower for k in ["online","сколько человек","сколько участник","seste","участник количество","статусu","сервер статусu","онлайн","сколько","в сети","состояние","сервер","статус"]):
        online_m =re .search (r'(\d+)\s*online',sys_prompt ,re .IGNORECASE )
        voice_m =re .search (r'(\d+)\s*seste',sys_prompt ,re .IGNORECASE )
        on_val =online_m .group (1 )if online_m else "Текущий"
        vc_val =voice_m .group (1 )if voice_m else "0"
        return (
        "🤖 **Анализ состояния сервера Hakumo:**\n"
        f"• На сервере сейчас **{on_val}** участник в сети, в голосовых каналах **{vc_val}** активных пользователей.\n"
        "• Все системы модерации, безопасности и анти-рейда работают 24/7.\n"
        "Чем еще я могу помочь, дружище?",
        "moebius-offline-ai",
        {"provider":"fallback","latency_ms":12 }
        )

        # 16.5. Панель и роли доступа (включая Куратора) — из живой карты MENU
    if any (k in q_lower for k in ["панел","panel","куратор","веб-панель","где настроить доступ","роли доступа"]):
        try :
            from web .ai_knowledge import build_panel_faq
            return (
            build_panel_faq (),
            "moebius-offline-ai",
            {"provider":"fallback","latency_ms":11 }
            )
        except Exception as _ex:
            _log.debug("_local_moebius_fallback(): подавлено: %s", _ex )

        # 17. Команды и помощь
    if any (k in q_lower for k in ["команда","помощь","help","neler yapabilirsin","особенность","команды","помощь","что ты умеешь","справка","какие команды"]):
        return (
        "🤖 **Справочник по командам Hakumo/Moebius:**\n"
        "• **Модерация:** `/moderate бан`, `/moderate кик`, `/moderate timeout`, `/варн`, `/warnings`\n"
        "• **Управление и очистка:** `/utility clear`, `/roles`, `/utility lock`, `/utility unlock`\n"
        "• **Поддержка и тикеты:** Команда `/ticket` или кнопка поддержки для создания тикета с AI-ассистентом.\n"
        "• **Музыка:** Команды `/play`, `/pause`, `/skip`, `/queue` для прослушивания музыки.\n"
        "Я всегда на связи, обращайся в любое время! 🚀",
        "moebius-offline-ai",
        {"provider":"fallback","latency_ms":11 }
        )

        # 18. Модерация / Предупреждения / Наказания
    if any (k in q_lower for k in ["предупреждение","варн","наказание","бан","кик","мут","история","варн","бан","кик","мут"]):
        return (
        "🛡️ **Оценка состояния модерации:**\n"
        "• Все предупреждения и наказания (бан/кик/мут) находятся под контролем системы модерации.\n"
        "• Для просмотра истории нарушений используйте команду `/history @пользователь` или лог модерации в веб-панели.\n"
        "• При серьезных жалобах создавайте тикет с доказательствами (скриншотами), чтобы связаться с администрацией.",
        "moebius-offline-ai",
        {"provider":"fallback","latency_ms":14 }
        )

        # 19. Тикеты / Поддержка
    if any (k in q_lower for k in ["ticket","поддержка","тикет","жалоба","sorun","администратор","админ","проблема","админ","модератор","sikayet","жалоба","kufur","kюfюr"]):
        return (
        "🎫 **Система поддержки Hakumo AI:**\n"
        "• Вы можете легко создать тикет с помощью кнопок в канале поддержки.\n"
        "• Сначала в тикете помогаю я; при необходимости или сложных вопросах я сразу подключаю администраторов сервера.\n"
        "• При запросе связи с администрацией нашей команде отправляется уведомление.",
        "moebius-offline-ai",
        {"provider":"fallback","latency_ms":10 }
        )

        # 20. Умный, дружелюбный автономный ответ по умолчанию (когда нет точного совпадения по ключам)
    return (
    "🤖 **Hakumo (Moebius) — автономный ассистент:**\n"
    f"Я внимательно прочитал твоё сообщение: *«{last_msg[:120]}»*\n\n"
    "• Я работаю 24/7 и готов помочь с управлением сервером, модерацией и командами.\n"
    "• Если тебе нужен список команд — напиши **«команды»** или **«помощь»**.\n"
    "• Если нужно проверить правила сервера — напиши **«правила»**.\n"
    "• Если возникла проблема или нужна связь с админами — используй систему тикетов (`/ticket`).\n\n"
    "Чем именно я могу тебе помочь, дружище? 👊",
    "moebius-offline-ai",
    {"provider":"fallback","latency_ms":12 }
    )
def _call (messages :List [Dict ],max_tokens :int =2048 ,temperature :float =0.7 ,model :str =None )->Tuple [str ,str ,Dict ]:
    """
    Мультпровайдерный вызов LLM API:
    1) Ollama (локальная LLM)
    2) Mistral AI API (MISTRAL_API_KEY: mistral-large/medium/small)
    3) OpenRouter / DeepSeek / OpenAI API
    4) Умный локальный офлайн-движок Hakumo/Moebius (fallback)
    """
    model_name =model or os .getenv ("AI_MODEL","mistral-large-latest")
    ollama_url =os .getenv ("OLLAMA_URL","http://127.0.0.1:11434")

    # 1. Попытка Ollama (локальная LLM) — очень быстро, если работает
    try :
        payload =json .dumps ({
        "model":model_name ,
        "messages":messages ,
        "stream":False ,
        "options":{
        "temperature":temperature ,
        "num_predict":max_tokens 
        }
        }).encode ('utf-8')
        req =urllib .request .Request (
        f"{ollama_url}/api/chat",
        data =payload ,
        headers ={"Content-Type":"application/json"},
        method ="POST"
        )
        with urllib .request .urlopen (req ,timeout =1.5 )as resp :
            data =json .loads (resp .read ().decode ('utf-8'))
            text =data .get ("message",{}).get ("content","").strip ()
            if text :
                return text ,model_name ,{"provider":"ollama"}
    except Exception as _ex:
        _log.debug("_call(): подавлено: %s", _ex)

        # 2. Mistral AI API — Автоматическая ротация нескольких ключей (Key Rotation)
    mistral_env =os .getenv ("MISTRAL_API_KEY","")
    mistral_keys =[k .strip ()for k in mistral_env .split (",")if k .strip ()]
    if mistral_keys :
        target_model =model_name if "mistral"in str (model_name ).lower ()else "mistral-large-latest"
        payload =json .dumps ({
        "model":target_model ,
        "messages":messages ,
        "max_tokens":max_tokens ,
        "temperature":temperature 
        }).encode ('utf-8')
        for idx_key ,mistral_key in enumerate (mistral_keys ):
            try :
                req =urllib .request .Request (
                "https://api.mistral.ai/v1/chat/completions",
                data =payload ,
                headers ={
                "Content-Type":"application/json",
                "Authorization":f"Bearer {mistral_key}"
                },
                method ="POST"
                )
                with urllib .request .urlopen (req ,timeout =10 )as resp :
                    data =json .loads (resp .read ().decode ('utf-8'))
                    text =data .get ("choices",[{}])[0 ].get ("message",{}).get ("content","").strip ()
                    if text :
                        return text ,target_model ,{"provider":"mistral","key_index":idx_key }
            except Exception as _me :
                print (f"[AI API] Mistral ключ #{idx_key+1} недоступен ({_me}), пробуем следующий...")

                # 3. OpenRouter / DeepSeek / OpenAI API
    api_key =os .getenv ("OPENROUTER_API_KEY")or os .getenv ("DEEPSEEK_API_KEY")or os .getenv ("OPENAI_API_KEY")or os .getenv ("AI_API_KEY")
    api_url =os .getenv ("AI_API_URL")
    if not api_url and os .getenv ("OPENROUTER_API_KEY"):
        api_url ="https://openrouter.ai/api/v1/chat/completions"
    elif not api_url and os .getenv ("DEEPSEEK_API_KEY"):
        api_url ="https://api.deepseek.com/chat/completions"
    elif not api_url :
        api_url ="https://api.openai.com/v1/chat/completions"

    if api_key :
        try :
            payload =json .dumps ({
            "model":model_name ,
            "messages":messages ,
            "max_tokens":max_tokens ,
            "temperature":temperature 
            }).encode ('utf-8')
            req =urllib .request .Request (
            api_url ,
            data =payload ,
            headers ={
            "Content-Type":"application/json",
            "Authorization":f"Bearer {api_key}"
            },
            method ="POST"
            )
            with urllib .request .urlopen (req ,timeout =10 )as resp :
                data =json .loads (resp .read ().decode ('utf-8'))
                text =data .get ("choices",[{}])[0 ].get ("message",{}).get ("content","").strip ()
                if text :
                    return text ,model_name ,{"provider":"api"}
        except Exception as _oe :
            print (f"[AI API] Внешняя API ошибка: {_oe}")

            # 4. Akыllы Hakumo/Moebius Yerel Fallback (Hiчbir LLM servisi olmasa bile никогда ошибка vermez!)
    return _local_moebius_fallback (messages )

def _call_text (messages :List [Dict ],max_tokens :int =2048 ,temperature :float =0.7 ,model :str =None )->str :
    """
    Только текст, возвращаемый LLM вызовом
    """
    try :
        resp ,_ ,_ =_call (messages ,max_tokens =max_tokens ,temperature =temperature ,model =model )
        if resp :
            return resp 
    except Exception as e :
        print (f"[AI] _call_text exception, fallback: {e}")
        # Fallback: локальный ответ Moebius
    try :
        fallback ,_ ,_ =_local_moebius_fallback (messages )
        return fallback 
    except Exception :
        return "Извините, произошла ошибка. Попробуйте позже."

def ai_assistant (question :str ,context :Dict =None ,history :List [Dict ]=None )->Tuple [str ,List [Dict ],str ,Dict ]:
    """
    Главная функция AI-ассистента чата (RAG + интеграция правил).
    Используется из cogs/ai_chat.py и веб-панели.
    
    Returns:
        (answer, updated_history, model_name, extra_info)
    """
    context =context or {}
    history =history or []

    sys_lines =[
    "Ты — Hakumo/Moebius, информационный AI-ассистент сервера Discord. Отвечай на русском языке.",
    "Ты — эксперт высшего класса: умный, точный, рассудительный. Отвечай на ЛЮБОЙ "
    "вопрос полно и уверенно: что спросили — то и получи.",
    "МЕТОД РАБОТЫ (всегда, внутренне): сначала мысленно разбери вопрос — что именно "
    "нужно человеку; сверься с данными сервера и разговора выше; потом выдай один "
    "готовый ответ. Само рассуждение НЕ показывай — показывай его итог.",
    "ФОРМА ОТВЕТА: первое предложение — прямой точный ответ (без воды и «конечно!»); "
    "дальше — суть и детали, полезные догадки и варианты; если вопрос расплывчат — "
    "ответь на самую вероятную трактовку и одной строкой уточни альтернативу.",
    "ФОРМАТ Discord: короткие абзацы, **жирный** для ключевого, списки маркером; "
    "код — только в коде. Без шаблонных извинений и без «как AI я не могу».",
    "ТОН: подстраивайся под спрашивающего — спросили коротко, отвечай коротко; "
    "шутят — ответь с лёгким юмором; раздражены — спокойно, по делу, без пафоса.",
    "ЧЕСТНОСТЬ ТОЧНОСТИ: уверен — говори уверенно; предполагаешь — честно помечай "
    "«вероятнее всего» и давай наиболее правдоподобный вариант, а не молчи.",
    "НЕ попугайничай: не повторяй дословно свои ответы из истории диалога — спросили "
    "снова, раскрой глубже или с другой стороны.",
    # Заказ владельца 2026-08-26: ИИ — только консультирует.
    "ЖЁСТКИЕ ПРАВИЛА (нарушать нельзя):",
    "1. Ты НЕ модератор и НЕ применяешь наказания: никаких мутов, варнов, банов, "
    "киков, тюрем — даже в виде совета «дай мут такому-то». Наказания выдаёт "
    "только модератор-человек через команды бота.",
    "2. НЕ выдумывай факты О СЕРВЕРЕ: цифры статистики, имена людей, даты и записи "
    "журналов бери строго из контекста и баз знаний выше — не издумай их.",
    "3. Никогда НЕ отказывай отговорками вроде «у меня нет доступа к данным», "
    "«данных нет», «я не могу это узнать»: общие знания, логику и здравый смысл "
    "используй свободно и отвечай как взрослый эксперт.",
    "4. Никаких служебных команд ACTION:* — максимум ACTION:ESCALATE (позвать модератора).",
    ]
    if context .get ('user_name'):
        sys_lines .append (f"Собеседник: {context.get('user_name')} (ID: {context.get('user_id', '?')})")
    if context .get ('guild_name'):
        sys_lines .append (f"Название сервера: {context.get('guild_name')}")
        # Живой слепок сервера — ИИ знает людей, каналы и роли, не «фантазирует»
    # ИИ всегда знает «сегодня» — вопросы про даты/сроки отвечает точно
    try :
        sys_lines .append ("Сегодняшняя дата: "+
        datetime .datetime .now ().strftime ('%d.%m.%Y'))
    except Exception as _ex:
        _log.debug("ai_assistant(): подавлено: %s", _ex)

    if context .get ('member_count'):
        sys_lines .append (f"Участников на сервере: {context['member_count']}")
    if context .get ('guild_owner'):
        sys_lines .append (f"Владелец сервера: {context['guild_owner']}")
    if context .get ('staff_roles'):
        try :
            _sr ='; '.join (
            f"{r0.get('name')}: {', '.join(r0.get('members') or [])}"
            for r0 in (context ['staff_roles']or [])[:8 ])
            if _sr :
                sys_lines .append ("Команда сервера (роль — люди): "+_sr )
        except Exception as _ex:
            _log.debug("ai_assistant(): подавлено: %s", _ex)
        # Реальные слеш-команды бота (из whitelist меню) — ИИ советует
        # только существующее, не выдумывает /search и т.п.
    try :
        from slash_budget import KEEP_SLASH as _KEEP 
        _cmds =sorted (str (c )for c in _KEEP )
        if _cmds :
            sys_lines .append (
            "РЕАЛЬНЫЕ слеш-команды бота (советуй только их, ЛЮБАЯ другая команда — выдумка): "+
            ", ".join ("/"+c for c in _cmds )+"\n"+
            "Если нужной команды здесь НЕТ — скажи, как это делается через эти команды "
            "или через панель, а не придумывай новую.")
    except Exception as _ex:
        _log.debug("ai_assistant(): подавлено: %s", _ex)

    if context .get ('channels'):
        _chs =[str (c )for c in context ['channels']if c ][:40 ]
        if _chs :
            sys_lines .append ("Каналы сервера: "+", ".join (_chs ))
    if context .get ('roles'):
        _rls =[str (r0 )for r0 in context ['roles']if r0 ][:30 ]
        if _rls :
            sys_lines .append ("Роли сервера: "+", ".join (_rls ))

        # Всё о панели и боте: роли (включая Куратора), разделы и страницы —
        # чтобы ИИ отвечал про панель точно и не выдумывал ссылок.
    try :
        from web .ai_knowledge import build_panel_knowledge
        sys_lines .append (build_panel_knowledge (compact =True ))
    except Exception as _ex:
        _log.debug("ai_assistant(): подавлено: %s", _ex )

        # RAG: Правил ve Benzer Решение Автоматически Добавить
    try :
        from web .ai_rag import get_knowledge_base 
        gid_val =int (context .get ('guild_id')or os .getenv ('MAIN_GUILD_ID','0'))
        rag_ctx =get_knowledge_base (gid_val ).get_context_for_query (question )
        if rag_ctx :
            sys_lines .append (rag_ctx )
    except Exception as _ex:
        _log.debug("ai_assistant(): подавлено: %s", _ex)

    if context .get ('learned_knowledge'):
        sys_lines .append ("Изученная информация о сервере:\n  "+"\n  ".join (str (k )for k in context ['learned_knowledge']))
    if context .get ('guild_instructions'):
        sys_lines .append ("Особые инструкции сервера:\n  "+"\n  ".join (str (i )for i in context ['guild_instructions']))
        # Хроника разговора — ИИ понимает, «о чём вообще речь», и не тупит
    if context .get ('channel_context'):
        _cc =[]
        for m in (context ['channel_context']or [])[-12 :]:
            if isinstance (m ,dict ):
                _cc .append (f"[{m.get('timestamp','')}] {m.get('author','?')}: {m.get('content','')}")
            else :
                _cc .append (str (m ))
        if _cc :
            sys_lines .append ("ПОСЛЕДНИЕ СООБЩЕНИЯ В КАНАЛЕ (хроника вокруг вопроса, "
            "[время] автор: текст):\n  "+"\n  ".join (_cc ))
    if context .get ('recent_user_messages'):
        _ru =[]
        for m in (context ['recent_user_messages']or [])[-10 :]:
            if isinstance (m ,dict ):
                _ru .append (f"[{m.get('timestamp','')}] в #{m.get('channel','?')}: {m.get('content','')}")
            else :
                _ru .append (str (m ))
        if _ru :
            sys_lines .append ("Недавние сообщения спрашивающего в других каналах:\n  "+
            "\n  ".join (_ru ))
    if context .get ('asker_roles'):
        sys_lines .append ("Роли спрашивающего: "+", ".join (
        str (r0 )for r0 in context ['asker_roles'][:10 ]))
    if context .get ('user_interests'):
        sys_lines .append ("Замеченные интересы спрашивающего: "+", ".join (
        str (i0 )for i0 in context ['user_interests'][:6 ]))
    if context .get ('user_style'):
        sys_lines .append ("Любимый стиль общения спрашивающего: "+str (context ['user_style']))

    if context .get ('server_status'):
        s =context ['server_status']
        sys_lines .append (f"Текущее состояние сервера: {s.get('online_count', 0)} в сети, {s.get('voice_count', 0)} в голосовых.")

        # Вопрос про активность модераторов → подкладываем РЕАЛЬНЫЕ цифры
        # из того же журнала, что и страница «Отчёты». Модель отвечает
        # фактами, а не выдумками.
    _q_lower =(question or '').lower ()
    if any (k in _q_lower for k in [
    'активност','активность','модер','модеров ',' модеров','отчёт','отчет',
    'сводк','еженедельн','наказан','варн','предупрежден','who did the moderation',
    ]):
        try :
            from web .routes .analytics_plus import _read_audit ,_parse_ts 
            from datetime import datetime as _dt ,timedelta as _td 
            _gid =int (context .get ('guild_id')or os .getenv ('MAIN_GUILD_ID','0')or 0 )
            cutoff =_dt .now ()-_td (days =7 )
            per_mod ={}
            _total =0 
            for ev in _read_audit (_gid ):
                if ev .get ('category')!='mod':
                    continue 
                _ts =_parse_ts (ev .get ('timestamp'))
                if _ts is None or _ts <cutoff :
                    continue 
                _total +=1 
                _mn =str (ev .get ('mod_name')or '').strip ()
                if _mn :
                    per_mod [_mn ]=per_mod .get (_mn ,0 )+1 
            _mod_block =[
            f"РЕАЛЬНАЯ СТАТИСТИКА МОДЕРАЦИИ ЗА 7 ДНЕЙ (из журнала бота, используй ТОЛЬКО эти цифры):",
            f"- Всего мод-действий: {_total}",
            ]
            for _mn ,_cnt in sorted (per_mod .items (),key =lambda kv :kv [1 ],reverse =True )[:10 ]:
                _mod_block .append (f"- {_mn}: {_cnt} действий" )
            if _total ==0 :
                _mod_block .append ("- Журнал пуст: за неделю не записано ни одного мод-действия. Честно скажи это." )
            _mod_block .append ("Эти цифры — единственный источник. Не добавляй своих оценок чисел и не предлагай наказания." )
            sys_lines .append ("\n".join (_mod_block ))
        except Exception as _ex:
            _log.debug("ai_assistant(): подавлено: %s", _ex)
    if context .get ('jarvis_mode'):
        sys_lines .append ("Режим J.A.R.V.I.S. активен. Помогай в выполнении команд и действий.")
    if context .get ('available_commands'):
        sys_lines .append (str (context ['available_commands']))

        # 1. RAG & Self-Learning FAQ: Автоматически подгружаем изученные ответы модераторов
    try :
        from web .faq_manager import find_relevant_faqs 
        gid_val =int (context .get ('guild_id')or os .getenv ('MAIN_GUILD_ID','0'))
        relevant_faqs =find_relevant_faqs (question ,guild_id =gid_val ,top_k =2 ,threshold =0.35 )
        if relevant_faqs :
            faq_texts =[f"ВОПРОС: {fitem['question']}\nОТВЕТ АДМИНИСТРАЦИИ: {fitem['answer']}"for fitem in relevant_faqs ]
            sys_lines .append ("💡 ИЗУЧЕННЫЕ РЕШЕНИЯ ИЗ БАЗЫ ЗНАНИЙ СЕРВЕРА:\n  "+"\n  ".join (faq_texts ))
    except Exception as _ex:
        _log.debug("ai_assistant(): подавлено: %s", _ex)

    messages =[{"role":"system","content":"\n".join (sys_lines )}]
    for h in history [-16 :]:
        messages .append ({
        "role":h .get ("role","user"),
        "content":h .get ("content","")
        })
    messages .append ({"role":"user","content":question })

    # Детерминизм заказан владельцем: тот же вопрос → тот же ответ,
    # без «плавания» формулировок. Хвост длиннее — ответы полные.
    answer ,model_name ,rate_info =_call (messages ,max_tokens =1408 ,temperature =0.25 )

    updated_history =list (history )+[
    {"role":"user","content":question },
    {"role":"assistant","content":answer }
    ]
    return answer ,updated_history ,model_name ,rate_info 
