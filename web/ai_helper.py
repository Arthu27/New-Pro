"""
Ядро AI-ассистента панели.
Chain-of-thought reasoning, персонализация, проактивное поведение, function calling.
Используется всеми модулями, где есть ИИ-ответ (аналитика, автодиагностика,
журнал действий, журнал ошибок, чат). Тикетной системы больше нет.
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

**Команда**:
- /staff-panel — панель набора в команду (админ)
- /my-application — статус моей заявки

**Репорты и разбор жалоб**:
- /report @участник причина [скрин/видео-файл или ссылка] — жалоба: создаётся
  приватная ветка с разбором; обвиняемый видит дело и свои прошлые нарушения
- /witness @user — позвать свидетеля в ветку репорта (модератор)
- /my-violations — мои нарушения, с кнопкой обжалования
- апелляция — только кнопкой (в карточке бана в ЛС, меню в канале
  или кнопка в /my-violations); отдельной команды нет (2026-09-08)
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
- /logs-setup — создать каналы логов (админ)

**Чего НЕТ в боте** (не выдумывай):
- Музыкального плеера нет (!play / !skip и т.п. — таких команд нет)
- Экономики / магазина монет / XP-уровней нет

**Автоматика бота** (работает сама, команд не нужно):
- Автомодерация: фильтр слов/ссылок/флуда/капса (настраивается в панели)
- Антирейд и верификация новичков
- Приветствия с красивыми карточками (настраиваются в панели)
- Логирование событий сервера в каналы логов
- AI-помощник: упомяни бота или напиши ? вопрос — отвечу

**Веб-панель Hakumo Panel**:
- Полное управление ботом через браузер (адрес даёт владелец)
- Роли доступа: owner / admin / curator / mod / участник (uye)
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
- question: вопрос о боте, панели, командах, ролях, правилах
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
    complaint_words =['жалоба','оскорбляет','спамит','токсичный','матерится','угрожает','травит']
    technical_words =['не работает','ошибка','баг','сломался','выдаёт ошибку','не могу']
    question_words =['как','где','какое время','что такое','почему','зачем','можно ли']

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
    """Промпт для вопросов — chain-of-thought"""
    return """Ты — AI-помощник Discord-сервера Hakumo. Отвечай ТОЛЬКО на русском.

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
- Не выдумывай музыку, экономику и XP — в боте их нет

ПРИМЕР ХОРОШИХ ОТВЕТОВ:
В: Как забанить спамера?
О: Открой `/modpanel`, выбери участника и действие «Бан», укажи причину. Бот применит наказание и запишет его в логи.

В: Как посмотреть свои наказания?
О: Команда `/my-violations` — там список и кнопка обжалования.
"""


def _prompt_technical ()->str :
    """Промпт для технических проблем — chain-of-thought"""
    return """Ты — AI техподдержки Discord-сервера Hakumo. Отвечай ТОЛЬКО на русском.

ТЕХНИЧЕСКАЯ ПРОБЛЕМА. Твоя задача:
1. ДИАГНОСТИРУЙ проблему (что именно не работает)
2. ПРЕДЛОЖИ решения (минимум 2 варианта):
   - Самое вероятное решение
   - Альтернативное решение
3. ПОШАГОВО объясни, как выполнить решение
4. Если не помогло → ACTION:ESCALATE

ПРАВИЛА:
- Начинай с самого простого решения
- Давай пошаговые инструкции (1, 2, 3...)
- Если нужна команда — укажи точно с примером
- НЕ предлагай «открыть тикет» — мы уже в тикете
- Если проблема сложная и ты не уверен → сразу ACTION:ESCALATE
- Музыки в боте нет: если спрашивают про плеер — честно скажи об этом

ПРИМЕР:
В: Бот не отвечает в чате
О: Давай проверим:
1. Упомяни бота (@Hakumo) или напиши вопрос с префиксом ?
2. Убедись, что AI-чат включён в настройках панели
3. Проверь, что канал разрешён для AI

Если не помогло — передаю модератору.
"""


def _prompt_other ()->str :
    """Промпт для прочих обращений — chain-of-thought"""
    return """Ты — AI-помощник Discord-сервера Hakumo. Отвечай ТОЛЬКО на русском.

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
    """Получить промпт по категории"""
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

    # 2. Собираем промпт для категоризации
    system_prompt =_get_prompt_by_category (category )

    # 3. Собираем контекст
    messages =[{'role':'system','content':system_prompt }]

    # Данные базы знаний (для question/technical/other)
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

        # 5. Контекст сервера
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

        # 5.5. Function calling — описание доступных функций
    guild =guild_context .get ('guild')
    ai_functions =None 
    if guild and AIFunctions :
        ai_functions =AIFunctions (guild .client )
        messages .append ({
        'role':'system',
        'content':ai_functions .get_available_functions ()
        })

        # 5.6. Самообучение — контекст из выученных шаблонов
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

    # 8. Опрашиваем AI с function calling (максимум 3 итерации)
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

        # Проверяем, есть ли вызовы функций
        func_calls =re .findall (r'\[FUNC:[^\]]+\]',response )

        if not func_calls or not ai_functions or not guild :
        # Нет вызовов функций или function calling недоступен — выходим
            break 

            # Vipolnyaem fonksiyonlar
        for func_call in func_calls [:3 ]:# Maksimum 3 fonksiyonlar для kez
            result =await ai_functions .execute_function (func_call ,guild )
            if result :
            # Добавляем результаты функций в контекст
                messages .append ({
                'role':'system',
                'content':f"РЕЗУЛЬТАТ FONKSIYONLAR {func_call}:\n{result}"
                })

                # Убрать вызовы функций из ответа
    response =re .sub (r'\[FUNC:[^\]]+\]','',response ).strip ()

    # 9. Разделяем записи
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

        # 11. Автоматически извлекаем и сохраняем факты
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

    # Убираем пустые строки
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

        # Ограничиваем 100 записями
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


    # ─── ОБЩИЙ ВЫЗОВ LLM И УМНЫЙ РЕЗЕРВ (FALLBACK) ───────────────────────
import time 
import urllib .request 
import urllib .error 

def _sanitize_ai_reply (text :str )->str :
    """Вырезать устаревший бренд/воду. Старый шаблон Moebius — целиком заменить."""
    if not text :
        return text 
    out =str (text )
    # Полный старый шаблон (ещё мог приехать с кэша/старого процесса)
    if re .search (r'Hakumo\s*\(\s*Moebius\s*\)|автономн\w*\s+ассистент|внимательно прочитал|дружище',out ,re .I ):
        m =re .search (r'«([^»]{1,80})»|"([^"]{1,80})"',out )
        quoted =(m .group (1 )or m .group (2 )or '').strip ().lower ()if m else ''
        if re .fullmatch (r'(привет|даров|дарова|здарова|хай|салют|hey|hi)[!?.]*',quoted or ''):
            return 'Привет. Чем помочь?'
        if any (k in (quoted or out .lower ())for k in ('поможешь','помоги','если спросят')):
            return 'Да. Напиши вопрос — отвечу по делу.'
        return 'Я Hakumo. Спроси коротко: правила, команды или статус сервера.'
    out =re .sub (r'(?i)Hakumo\s*\(\s*Moebius\s*\)','Hakumo',out )
    out =re .sub (r'(?i)\bMoebius\b','',out )
    out =re .sub (r'(?i)/ticket\b','/report',out )
    out =re .sub (r'(?i)систем\w*\s+тикетов','/report',out )
    out =re .sub (r'(?i),?\s*дружище!?','',out )
    out =re .sub (r'[ \t]{2,}',' ',out )
    out =re .sub (r'\n{3,}','\n\n',out )
    return out .strip ()


def _local_hakumo_fallback (messages :List [Dict ])->Tuple [str ,str ,Dict ]:
    text ,tag ,meta =_local_hakumo_fallback_impl (messages )
    return _sanitize_ai_reply (text ),tag ,meta 


# Совместимость со старыми импортами
_local_moebius_fallback =_local_hakumo_fallback 


def _local_hakumo_fallback_impl (messages :List [Dict ])->Tuple [str ,str ,Dict ]:
    """Простой офлайн-ответчик Hakumo: коротко, по-русски, без тикетов и Moebius."""
    last_msg =""
    sys_prompt =""
    for m in messages :
        if m .get ("role")=="system":
            sys_prompt +="\n"+str (m .get ("content",""))
        elif m .get ("role")=="user":
            last_msg =str (m .get ("content","")).strip ()

    q =last_msg .lower ().strip ()
    q_compact =re .sub (r'[^\wа-яё]+',' ',q ,flags =re .I ).strip ()
    tag ="hakumo-offline"
    meta ={"provider":"fallback","latency_ms":10 }

    def pack (text ,ms =10 ):
        return text ,tag ,{**meta ,"latency_ms":ms }

    def from_sys (*patterns ,default =None ):
        for p in patterns :
            m =re .search (p ,sys_prompt ,re .I )
            if m :
                return m .group (1 ).strip ()
        return default 

    # Привет
    if q_compact in {
    "привет","здравствуй","здравствуйте","здрасте","хай","салют","даров","дарова",
    "здарова","доброе утро","добрый день","добрый вечер","hey","hi","hello","приветик","йо"
    }or re .fullmatch (r'(привет|даров|дарова|здарова|хай|салют|hey|hi)( всем)?',q_compact ):
        return pack ("Привет. Чем помочь?")

    # Кто ты / старый бренд
    if (any (k in q for k in ("кто ты","что ты такое","расскажи о себе","ты кто","что за бот","кто ты такой","что умеешь","что ты умеешь"))
    or (("что это"in q or "что такое"in q )and any (k in q for k in ("hakumo","moebius","бот","ассистент","помощник")))
    or ("автономн"in q and "ассистент"in q )
    or "moebius"in q
    or q_compact in ("что это","это что","hakumo","moebius")
    or q .startswith ("hakumo (moebius)")):
        return pack (
        "Я Hakumo — AI-помощник сервера: правила, команды, панель, статус. "
        "Наказания выдают модераторы. Тикетов нет — жалоба через /report.",
        11 )

    # Поможешь?
    if any (k in q for k in ("поможешь","помоги","можешь помочь","подскажешь","ответишь","если спросят"))\
    and not any (k in q for k in ("правил","команд","настро","варн","бан","панел","кто ты")):
        return pack ("Да. Напиши вопрос — отвечу по делу.")

    # Как дела
    if any (k in q for k in ("как дела","как жизнь","что нового","как ты","как самочувствие")):
        return pack ("У меня всё отлично. Чем помочь?")

    # Спасибо / пока
    if any (k in q for k in ("спасибо","спс","благодарю","сяп","thank")):
        return pack ("Пожалуйста.")
    if re .search (r'\bпока\b|до свидания|\bудачи\b|спокойной ночи|до встречи|\bбывай\b',q ):
        return pack ("До встречи.")

    # Настройка
    if (any (k in q for k in ("настро","как включить","как выключить","куда нажать","как поставить","как подключить","как поменять","как сменить"))
    and "настроени"not in q ):
        try :
            from web .ai_knowledge import build_setup_faq 
            return pack (build_setup_faq (last_msg ),11 )
        except Exception :
            pass 

    # Музыка / экономика — нет
    if any (k in q for k in ("музыка","песня","трек","play","мьюзик")):
        return pack ("Музыкального модуля нет. Я помогаю с правилами, командами и панелью.",12 )
    if any (k in q for k in ("экономика","монеты","баланс","деньги","магазин","shop","монета")):
        return pack ("Экономики и магазина нет. Спроси про роли или раздел панели.",12 )

    # AFK
    if any (k in q for k in ("афк","afk","отошел","отошёл")):
        return pack ("AFK: `/afk [причина]`. Если тебя упомянут — бот ответит, что ты отошёл.",11 )

    # FAQ из system
    faq =re .search (r'ВОПРОС:\s*([^\n]+)\nОТВЕТ АДМИНИСТРАЦИИ:\s*([^\n]+)',sys_prompt ,re .I )
    if faq :
        return pack (f"{faq.group(2).strip()}")

    # Правила
    if any (k in q for k in ("запрет","правило","правила","запрещено","нельзя","свод правил")):
        lines =[]
        for rm in re .finditer (r'(Правило\s*#\d+:[^\n]+)',sys_prompt ):
            lines .append ("• "+rm .group (1 ))
        if not lines and 'ПРАВИЛА СЕРВЕРА'in sys_prompt :
            chunk =sys_prompt .split ('ПРАВИЛА СЕРВЕРА',1 )[-1 ]
            for line in chunk .splitlines ():
                t =line .strip ().lstrip ('•-– ').strip ()
                if t .startswith ('Правило')or (t and t [0 ].isdigit ()and '.'in t [:4 ]):
                    lines .append ('• '+t )
                if len (lines )>=8 :
                    break 
        if not lines :
            lines =[
            "• Уважение — без оскорблений и языка вражды.",
            "• Без спама, флуда и рекламы без разрешения.",
            "• В голосовых — не мешать другим.",
            "• Решения модерации обжалуются через апелляции / /my-violations.",
            "• Не распространять личные данные и вредоносные ссылки.",
            ]
        return pack (
        "**Свод правил:**\n"+"\n".join (lines [:8 ])+
        "\nНаказания выдают модераторы-люди.",
        11 )

    # Статус
    if any (k in q for k in ("online","сколько человек","сколько участников","в голосе","онлайн","в сети","состояние сервера","статус сервера","кто в войсе","кто онлайн")):
        on_val =from_sys (r'(\d+)\s*в сети',r'Сейчас:\s*(\d+)\s*в сети',default =None )
        vc_val =from_sys (r'(\d+)\s*в голосовых',default ='0')
        members =from_sys (r'Участников(?: на сервере)?:\s*(\d+)',default =None )
        parts =[]
        if members :
            parts .append (f"всего {members}")
        if on_val is not None :
            parts .append (f"в сети {on_val}")
        parts .append (f"в голосовых {vc_val}")
        return pack ("Сейчас на сервере: "+", ".join (parts )+".",12 )

    # Панель
    if any (k in q for k in ("панел","panel","куратор","веб-панель","роли доступа")):
        try :
            from web .ai_knowledge import build_panel_faq 
            return pack (build_panel_faq (),11 )
        except Exception :
            return pack ("Панель Hakumo — веб-управление сервером. Адрес даёт владелец.",11 )

    # Команды / модерация / жалоба
    if any (k in q for k in ("команда","помощь","help","команды","справка","какие команды")):
        return pack (
        "Команды: `/modpanel`, `/report`, `/my-violations`, `/afk`. "
        "Музыки, экономики и тикетов нет.",
        11 )
    if any (k in q for k in ("предупреждение","варн","наказание","бан","кик","мут","история наказа")):
        return pack (
        "Модерация: `/modpanel`. История: `/history`. Жалоба: `/report`.",
        14 )
    if any (k in q for k in ("ticket","поддержка","тикет","жалоба","админ","проблема","модератор","помогите")):
        return pack (
        "Тикетов нет. Жалоба — `/report`. Вопросы по правилам/командам — сюда.",
        10 )

    # Дефолт
    return pack ("Уточни вопрос одной фразой: «правила», «команды» или «кто онлайн».",12 )


def _call (messages :List [Dict ],max_tokens :int =2048 ,temperature :float =0.7 ,model :str =None )->Tuple [str ,str ,Dict ]:
    """
    Движок ответов (Hakumo Brain снаружи):
    1) Mistral / облако — основной путь на малом VDS
    2) Ollama — только если явно включена (OLLAMA_MODEL / AI_USE_OLLAMA=1)
    3) Короткий офлайн-фолбэк
    """
    from services .hakumo_brain import own_model_name ,backup_model_name ,ollama_enabled 

    backup =backup_model_name (model )
    try :
        temperature =float (temperature )
    except (TypeError ,ValueError ):
        temperature =0.15 
    temperature =max (0.0 ,min (1.0 ,temperature ))

    # 1. ОБЛАКО (мало места на VDS — так и надо)
    mistral_env =os .getenv ("MISTRAL_API_KEY","")
    mistral_keys =[k .strip ()for k in mistral_env .split (",")if k .strip ()]
    if mistral_keys :
        target_model =backup if "mistral"in str (backup ).lower ()else "mistral-large-latest"
        payload =json .dumps ({
        "model":target_model ,
        "messages":messages ,
        "max_tokens":max_tokens ,
        "temperature":min (temperature ,0.3 ),
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
                with urllib .request .urlopen (req ,timeout =20 )as resp :
                    data =json .loads (resp .read ().decode ('utf-8'))
                    text =data .get ("choices",[{}])[0 ].get ("message",{}).get ("content","").strip ()
                    if text :
                        return text ,target_model ,{"provider":"mistral","engine":"cloud"}
            except Exception as _me :
                _log .debug ("mistral key #%s: %s",idx_key +1 ,_me )

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
            "model":backup ,
            "messages":messages ,
            "max_tokens":max_tokens ,
            "temperature":min (temperature ,0.3 ),
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
            with urllib .request .urlopen (req ,timeout =20 )as resp :
                data =json .loads (resp .read ().decode ('utf-8'))
                text =data .get ("choices",[{}])[0 ].get ("message",{}).get ("content","").strip ()
                if text :
                    return text ,backup ,{"provider":"api","engine":"cloud"}
        except Exception as _oe :
            _log .debug ("backup api: %s",_oe )

    # 2. Ollama — только если явно включили (много RAM)
    if ollama_enabled ():
        ollama_url =(os .getenv ("OLLAMA_URL")or "http://127.0.0.1:11434").rstrip ('/')
        own =own_model_name ()or "llama3.1"
        try :
            payload =json .dumps ({
            "model":own ,
            "messages":messages ,
            "stream":False ,
            "options":{
            "temperature":temperature ,
            "num_predict":max_tokens ,
            "top_p":0.9 ,
            }
            }).encode ('utf-8')
            req =urllib .request .Request (
            f"{ollama_url}/api/chat",
            data =payload ,
            headers ={"Content-Type":"application/json"},
            method ="POST"
            )
            with urllib .request .urlopen (req ,timeout =45 )as resp :
                data =json .loads (resp .read ().decode ('utf-8'))
                text =data .get ("message",{}).get ("content","").strip ()
                if text :
                    return text ,own ,{"provider":"ollama","engine":"local"}
        except Exception as _ex :
            _log .debug ("ollama %s: %s",own ,_ex )

    # 3. Аварийный короткий офлайн
    return _local_hakumo_fallback (messages )

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
        # Fallback: локальный ответ Hakumo
    try :
        fallback ,_ ,_ =_local_hakumo_fallback (messages )
        return fallback 
    except Exception :
        return "Извините, произошла ошибка. Попробуйте позже."

def ai_assistant (question :str ,context :Dict =None ,history :List [Dict ]=None ,
temperature :float =None ,max_tokens :int =None ,model :str =None )->Tuple [str ,List [Dict ],str ,Dict ]:
    """
    Главная функция AI-ассистента чата (RAG + интеграция правил).
    Используется из cogs/ai_chat.py и веб-панели.
    
    Returns:
        (answer, updated_history, model_name, extra_info)
    """
    context =context or {}
    history =history or []

    sys_lines =[]
    # Hakumo Brain — думающий ассистент (не триггеры)
    try :
        from services .hakumo_brain import build_brain_preamble ,settings_custom_instructions 
        _custom =str ((context or {}).get ('custom_instructions')or '')
        if not _custom :
            try :
                from services .ai_chat_settings import load_settings 
                _custom =settings_custom_instructions (load_settings ())
            except Exception :
                pass 
        sys_lines .extend (build_brain_preamble (_custom ))
    except Exception as _brain_ex :
        _log .debug ('brain preamble: %s',_brain_ex )
        sys_lines .extend ([
        "Ты Hakumo — AI-помощник Discord-сервера. Отвечай только по-русски.",
        "Думай над вопросом, опирайся на данные сервера, не выдумывай.",
        ])
    sys_lines .extend ([
    "ЖЁСТКИЕ ПРАВИЛА:",
    "1. Не применяй наказания сам — только модератор-человек.",
    "2. Цифры/имена о сервере — только из досье и результатов инструментов.",
    "3. Не отнекивайся «нет доступа», если досье ниже есть.",
    "4. Тикетов нет — жалоба через /report.",
    "5. Не повторяй дословно прошлый ответ; продолжай тему при reply.",
    ])
    if context .get ('user_name'):
        sys_lines .append (f"Собеседник: {context.get('user_name')} (ID: {context.get('user_id', '?')})")
    if context .get ('guild_name'):
        sys_lines .append (f"Название сервера: {context.get('guild_name')}")
        # Живой слепок сервера — ИИ знает людей, каналы и роли, не «фантазирует»
    # ИИ всегда знает «сегодня» — вопросы про даты/сроки отвечает точно
    try :
        sys_lines .append ("Сегодняшняя дата: "+
        datetime .datetime .now ().strftime ('%d.%m.%Y %H:%M'))
    except Exception as _ex:
        _log.debug("ai_assistant(): подавлено: %s", _ex)

    # Полное досье (предпочтительно) — иначе старые поля
    if context .get ('server_dossier'):
        try :
            from services .ai_server_snapshot import dossier_to_prompt_lines 
            sys_lines .extend (dossier_to_prompt_lines (context ['server_dossier']))
        except Exception as _ex:
            _log.debug("ai_assistant dossier: %s", _ex)
    else :
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
        if context .get ('channels'):
            _chs =[str (c )for c in context ['channels']if c ][:40 ]
            if _chs :
                sys_lines .append ("Каналы сервера: "+", ".join (_chs ))
        if context .get ('roles'):
            _rls =[str (r0 )for r0 in context ['roles']if r0 ][:30 ]
            if _rls :
                sys_lines .append ("Роли сервера: "+", ".join (_rls ))
        if context .get ('server_status'):
            s =context ['server_status']
            _st =[f"Сейчас: {s.get('online_count', 0)} в сети, {s.get('voice_count', 0)} в голосовых."]
            if s .get ('voice_detail'):
                _st .append ('Голосовые: '+' | '.join (s ['voice_detail'][:8 ]))
            elif s .get ('voice_members'):
                _st .append ('В войсе: '+', '.join (s ['voice_members'][:8 ]))
            if s .get ('recent_joins'):
                _st .append ('Зашли за 24ч: '+', '.join (s ['recent_joins'][:8 ]))
            if s .get ('active_tickets')is not None :
                _st .append (f"Открытых тикетов: {s.get('active_tickets')}")
            sys_lines .append (' '.join (_st ))

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
        for m in (context ['channel_context']or [])[-16 :]:
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

    # Если полного досье нет — короткий статус; иначе уже в досье
    if (not context .get ('server_dossier')) and context .get ('server_status'):
        s =context ['server_status']
        sys_lines .append (f"Текущее состояние сервера: {s.get('online_count', 0)} в сети, {s.get('voice_count', 0)} в голосовых.")

        # Вопрос про активность модераторов → подкладываем РЕАЛЬНЫЕ цифры
        # из того же журнала, что и страница «Отчёты». Модель отвечает
        # фактами, а не выдумками.
    _q_lower =(question or '').lower ()
    _want_mod =any (k in _q_lower for k in [
    'активност','активность','модер','модеров ',' модеров','отчёт','отчет',
    'сводк','еженедельн','наказан','варн','предупрежден','who did the moderation',
    ])
    # Если досье уже дало mod_week — не дублируем; иначе подгружаем по запросу
    if _want_mod and not (context .get ('server_dossier')or {}).get ('mod_week'):
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

    # Детерминизм + точность: низкая температура, полный хвост.
    # Параметры можно усилить из настроек Discord-чата / панели.
    _temp =0.18 if temperature is None else float (temperature )
    _toks =1600 if max_tokens is None else int (max_tokens )
    answer ,model_name ,rate_info =_call (
    messages ,max_tokens =_toks ,temperature =_temp ,model =model )
    answer =_sanitize_ai_reply (answer or '')
    try :
        from services .hakumo_brain import ground_answer 
        _allowed =None 
        try :
            from slash_budget import KEEP_SLASH as _KEEP 
            _allowed ={str (c ).lower ()for c in _KEEP }|{('/'+str (c )).lower ()for c in _KEEP }
        except Exception :
            pass 
        answer =ground_answer (answer ,_allowed )
    except Exception as _gex :
        _log .debug ('ground_answer: %s',_gex )

    updated_history =list (history )+[
    {"role":"user","content":question },
    {"role":"assistant","content":answer }
    ]
    return answer ,updated_history ,model_name ,rate_info 
