"""
Ticket AI — продвинутая система поддержки
Chain-of-thought reasoning, персонализация, проактивное поведение, function calling
"""
import os
import json
import re
import datetime
from typing import Dict, List, Optional, Tuple

# Import function calling system
try:
    from web.ai_functions import AIFunctions
except ImportError:
    AIFunctions = None

# ─── БАЗА ЗНАНИЙ БОТА ───────────────────────────────────────────────────────

def _bot_knowledge_base() -> str:
    """Полная база знаний о боте Aether"""
    return """
═══════════════════════════════════════════
AETHER BOT — ПОЛНАЯ БАЗА ЗНАНИЙ
═══════════════════════════════════════════

## ЧТО ТАКОЕ AETHER?
Aether — многофункциональный Discord бот для управления сервером.
Веб-панель (Flask) + Discord бот работают вместе.
Панель доступна через Cloudflare tunnel по публичной ссылке.
Ссылка на панель находится в канале #aether-panel.

## 🛡️ МОДЕРАЦИЯ
- /moderate ban @user [причина] — перманентный бан
- /moderate kick @user [причина] — кик с сервера
- /moderate timeout @user [минуты] [причина] — временный мут
- /moderate untimeout @user — снять мут
- /moderate unban [user_id] — разбан
- /utility clear [количество] — массовое удаление сообщений
- /utility lock/unlock — блокировка/разблокировка канала
- /utility userinfo @user — информация о пользователе
- /role @user @роль — выдать/снять роль
- /history @user — история модерации
- /case [id] — детали дела
- /note @user [текст] — добавить заметку
- /notes @user — показать заметки
- /watchlist @user [причина] — список наблюдения
- /banlist — забаненные пользователи
- /massrole @роль [выдать/снять] — массовая выдача ролей

## ⚠️ ПРЕДУПРЕЖДЕНИЯ
- /warn @user [причина] — выдать предупреждение
- /warnings @user — список предупреждений
- /clearwarns @user — очистить предупреждения
Автоматические наказания: при накоплении предупреждений — мут/кик/бан.

## 🎵 МУЗЫКА
- /play [название/ссылка] — воспроизвести
- /pause — пауза/продолжить
- /skip — пропустить трек
- /queue — очередь
- /volume [0-100] — громкость
- /clear-queue — очистить очередь
- /leave — покинуть голосовой канал
- /join — присоединиться к каналу

## 💰 ЭКОНОМИКА
- /economy balance — баланс
- /economy daily — ежедневная награда (50 монет, 24ч)
- /economy transfer @user [сумма] — перевести монеты
- /economy ranking — топ богачей
- /games gamble [сумма] — азартная игра
- /games slot [сумма] — слот-машина
- /games heist @user — ограбление
- /shop — магазин
- /buy [предмет] — купить товар

## 🎮 РАЗВЛЕЧЕНИЯ
- /coinflip — монетка
- /roll [количество] — бросить кубик
- /rps — камень-ножницы-бумага
- /guess-start — угадай число
- /guess [число] — ввести число
- /8ball [вопрос] — магический шар
- /random-member — случайный участник
- /fun [dice] — развлекательные
- /poll [вопрос] — быстрый опрос

## 👥 СОЦИАЛЬНОЕ
- /birthday [день] [месяц] — сохранить день рождения
- /birthdays — ближайшие дни рождения
- /afk [причина] — режим AFK
- /staff-apply — заявка модератора
- /profile — ваш профиль
- /invites — статистика приглашений
- /invite-ranking — топ приглашающих

## 🏆 РЕЙТИНГИ
- /rank — ваш уровень и XP
- /top-level — топ-10 по уровню
- !ranking — общий рейтинг
- !ranking messages — рейтинг сообщений
- !ranking voice — рейтинг голосового времени
- !ranking invites — рейтинг приглашений
- /mod-stats @user — статистика модераторов
- /activemods — активные модераторы

## 📅 МЕРОПРИЯТИЯ
- /event-create [название] — создать мероприятие
- /events — активные мероприятия
- /event-cancel [id] — отменить мероприятие
- /giveaway — создать розыгрыш

## ⚙️ УПРАВЛЕНИЕ СЕРВЕРОМ
- /setup-logs — создать лог-каналы
- /verify-setup — настроить верификацию
- /ticket_panel — панель тикетов
- /duty-panel — панель заданий
- /duty-add @user [очки] — добавить прогресс
- /duty-stats — таблица очков
- /automod — автомодерация
- /level-role-add [уровень] @роль — роль за уровень
- /level-roles — список ролей за уровни

## 🔧 ИНСТРУМЕНТЫ
- /botinfo — информация о боте
- /serverinfo — информация о сервере
- /uptime — время работы бота
- /health — здоровье сервера
- /avatar @user — аватар пользователя
- /channel-stats — статистика канала
- /archive [количество] — архив сообщений
- /ai-reset — сбросить историю AI
- /ai-learn [тема] [текст] — обучить AI
- /color [#HEX] — информация о цвете
- /announce #канал [текст] — создать объявление

## 🤖 AI АССИСТЕНТ
- Пишите в канал с AI — он ответит
- /ai-reset — сбросить историю разговора
- /ai-learn [тема] [текст] — научить AI новому факту
- AI помогает в тикетах автоматически

## 🎫 ТИКЕТЫ
- Нажмите кнопку в канале тикетов
- Откроется канал #ticket-вашеимя
- AI поможет решить проблему
- Если не сможет — направит к модераторам
- При закрытии — транскрипт сохраняется

## ✅ ВЕРИФИКАЦИЯ
- Зайдите в канал верификации
- Нажмите кнопку или используйте /verify
- После верификации — получите роль участника

## 😴 AFK
- /afk [причина] — войти в режим AFK
- Ник меняется на 💤 [ваш ник]
- При упоминании — бот сообщает что вы AFK
- При отправке сообщения — AFK снимается автоматически

## 🎂 ДНИ РОЖДЕНИЯ
- /birthday [день] [месяц] — сохранить
- /birthdays — ближайшие дни рождения
- В день рождения — бот поздравляет автоматически

## 📨 ПРИГЛАШЕНИЯ
- /invites — ваша статистика
- /invite-ranking — топ приглашающих
- Уровни: Посол / Приглашающий / Новый приглашающий

## 🌐 ВЕБ-ПАНЕЛЬ
Панель — веб-интерфейс управления сервером.
Как войти: ссылка в канале #aether-panel → Discord ID + пароль.
Уровни доступа:
- Участник: профиль, заявки, день рождения
- Модератор: логи, предупреждения, тикеты
- Админ: команды, каналы, роли, автомод
- Владелец: всё

## ❓ ЧАСТЫЕ ВОПРОСЫ
В: Как войти в панель?
О: Ссылка в канале #aether-panel → Discord ID + пароль.

В: Музыка не играет?
О: Зайдите в голосовой канал, потом /play. Если ошибка — /leave и снова /play.

В: Как повысить уровень?
О: Пишите сообщения + сидите в голосовых каналах. /rank — ваш уровень.

В: Как открыть тикет?
О: Кнопка в канале тикетов → "Создать тикет".

В: Как получить роль?
О: Канал выбора ролей или /color-role.

В: Как подать заявку модератора?
О: /staff-apply или через панель.

В: Как сохранить день рождения?
О: /birthday [день] [месяц] или через панель.

В: Забыл пароль от панели?
О: Нажмите "Забыли пароль?" на странице входа → Discord ID → код в DM.
"""


# ─── ОПРЕДЕЛЕНИЕ КАТЕГОРИИ (AI) ─────────────────────────────────────────────

def _detect_category_ai(message: str, history: List[Dict]) -> str:
    """Определение категории с помощью AI (не keyword-based)"""
    prompt = """Определи категорию обращения пользователя в Discord тикете.

КАТЕГОРИИ:
- complaint: жалоба на другого пользователя (оскорбления, спам, токсичность)
- question: вопрос о боте, панели, командах, ролях, экономике
- technical: техническая проблема (не работает, ошибка, баг)
- other: всё остальное

ПРАВИЛА:
- Если пользователь жалуется на ДРУГОГО пользователя → complaint
- Если спрашивает как что-то сделать → question
- Если что-то не работает или выдаёт ошибку → technical
- Если просто болтает или непонятно → other

Ответь ТОЛЬКО одним словом: complaint, question, technical или other.
Без пояснений, без точек, без кавычек.

Сообщение пользователя: """

    messages = [
        {'role': 'user', 'content': prompt + message}
    ]

    try:
        result, _, _ = _call(messages, max_tokens=10, temperature=0.1)
        result = result.strip().lower()
        if result in ('complaint', 'question', 'technical', 'other'):
            return result
    except:
        pass

    # Fallback на keyword-based
    return _detect_category_fallback(message)


def _detect_category_fallback(message: str) -> str:
    """Fallback: keyword-based определение категории"""
    msg = message.lower()
    complaint_words = ['жалоба', 'оскорбляет', 'спамит', 'токсичный', 'матерится', 'угрожает', 'травит']
    technical_words = ['не работает', 'ошибка', 'баг', 'сломалось', 'выдаёт ошибку', 'не могу']
    question_words = ['как', 'где', 'когда', 'что', 'почему', 'зачем', 'можно ли']

    if any(w in msg for w in complaint_words):
        return 'complaint'
    if any(w in msg for w in technical_words):
        return 'technical'
    if any(w in msg for w in question_words):
        return 'question'
    return 'other'


# ─── ПРОМПТЫ С CHAIN-OF-THOUGHT ─────────────────────────────────────────────

def _prompt_complaint() -> str:
    """Промпт для жалоб — chain-of-thought"""
    return """Ты — AI модератор Discord сервера. Отвечай на русском.

ПОЛУЧЕНА ЖАЛОБА. Твоя задача:
1. ПРОАНАЛИЗИРУЙ ситуацию (кто, что, когда)
2. СОБЕРИ информацию:
   - Спроси кто нарушитель (Discord ID или @упоминание)
   - Спроси в каком канале произошло
   - Попроси доказательства (скриншоты, ссылки на сообщения)
3. ОЦЕНИ серьёзность:
   - Лёгкое нарушение (спам, флуд) → предупреди
   - Среднее (оскорбления) → ACTION:WARN:user_id=X:reason=Y
   - Тяжёлое (угрозы, травля) → ACTION:JAIL:user_id=X:duration=60:reason=Y ACTION:ESCALATE
4. УСПОКОЙ пользователя, скажи что разберёмся

ПРАВИЛА:
- НЕ проси скриншоты если их уже дали
- НЕ предлагай "открыть тикет" — мы уже в тикете
- Будь эмпатичным, но профессиональным
- Если нарушение тяжёлое — действуй быстро

ФОРМАТ ОТВЕТА:
Сначала ответ пользователю (текстом).
Потом, если нужно действие — на новой строке:
ACTION:WARN:user_id=123456:reason=оскорбления
или
ACTION:JAIL:user_id=123456:duration=60:reason=травля ACTION:ESCALATE
"""


def _prompt_question() -> str:
    """Промпт для вопросов — chain-of-thought"""
    return """Ты — AI помощник Discord сервера. Отвечай на русском.

ПОЛУЧЕН ВОПРОС. Твоя задача:
1. ПОНЯИ вопрос (о чём именно спрашивают)
2. ПРОВЕРЬ базу знаний (знаешь ли ответ)
3. ОТВЕТЬ чётко и кратко:
   - Если знаешь → дай ответ + пример использования
   - Если не уверен → скажи "Не уверен, но..." + лучшее предположение
   - Если не знаешь → ACTION:ESCALATE (направь к модераторам)

ПРАВИЛА:
- Отвечай на 2-3 предложения максимум
- Давай конкретные команды с примерами
- НЕ предлагай "открыть тикет" — мы уже в тикете
- Если вопрос о другом пользователе — не раскрывай личную информацию

ПРИМЕРЫ ХОРОШИХ ОТВЕТОВ:
В: Как забанить спамера?
О: Используй `/moderate ban @user причина`. Например: `/moderate ban @spammer Спам в чате`. Бот отправит DM пользователю и запишет в логи.

В: Как повысить уровень?
О: Пиши сообщения в чате и сиди в голосовых каналах — получаешь XP. Проверить уровень: `/rank`. Топ-10: `/top-level`.
"""


def _prompt_technical() -> str:
    """Промпт для технических проблем — chain-of-thought"""
    return """Ты — AI техподдержка Discord сервера. Отвечай на русском.

ТЕХНИЧЕСКАЯ ПРОБЛЕМА. Твоя задача:
1. ДИАГНОСТИРУЙ проблему (что именно не работает)
2. ПРЕДЛОЖИ решения (минимум 2 варианта):
   - Самое вероятное решение
   - Альтернативное решение
3. ПОШАГОВО объясни как выполнить решение
4. Если не помогло → ACTION:ESCALATE

ПРАВИЛА:
- Начинай с самого простого решения
- Давай пошаговые инструкции (1, 2, 3...)
- Если нужна команда — укажи точно с примером
- НЕ предлагай "открыть тикет" — мы уже в тикете
- Если проблема сложная и ты не уверен → сразу ACTION:ESCALATE

ПРИМЕРЫ:
В: Музыка не играет
О: Давай проверим:
1. Ты в голосовом канале? (бот должен быть в том же канале)
2. Попробуй `/leave` потом снова `/play [название]`
3. Проверь что у бота есть права на подключение к голосовым каналам

Если не помогло — направлю к модераторам.
"""


def _prompt_other() -> str:
    """Промпт для других обращений — chain-of-thought"""
    return """Ты — AI помощник Discord сервера. Отвечай на русском.

ОБРАЩЕНИЕ НЕ ЯСНО. Твоя задача:
1. ПОЙМИ что хочет пользователь
2. УТОЧНИ если непонятно (задай 1 вопрос)
3. ПОМОГИ если можешь
4. Если не можешь → ACTION:ESCALATE

ПРАВИЛА:
- Будь дружелюбным
- Задай максимум 1 уточняющий вопрос
- Если пользователь просто болтает — поддержи разговор
- Если проблема серьёзная — направь к модераторам
- НЕ предлагай "открыть тикет" — мы уже в тикете
"""


def _get_prompt_by_category(category: str) -> str:
    """Получить промпт по категории"""
    prompts = {
        'complaint': _prompt_complaint(),
        'question': _prompt_question(),
        'technical': _prompt_technical(),
        'other': _prompt_other(),
    }
    return prompts.get(category, _prompt_other())


# ─── ГЛАВНАЯ ФУНКЦИЯ — AI TICKET RESPONSE ───────────────────────────────────

async def ai_ticket_response(user_message: str, history: List[Dict], guild_context: Dict) -> Tuple[str, bool, str, List[Dict], str]:
    """
    Главная функция AI ответа в тикете.

    Returns:
        (response, should_escalate, escalation_category, updated_history, detected_category)
    """
    # 1. Определяем категорию с помощью AI
    category = _detect_category_ai(user_message, history)

    # 2. Получаем промпт для категории
    system_prompt = _get_prompt_by_category(category)

    # 3. Собираем контекст
    messages = [{'role': 'system', 'content': system_prompt}]

    # База знаний (для question/technical/other)
    if category in ('question', 'technical', 'other'):
        messages.append({'role': 'system', 'content': _bot_knowledge_base()})

    # 4. Персонализация — информация о пользователе
    user_info = []
    if guild_context.get('user_name'):
        user_info.append(f"Имя: {guild_context['user_name']}")
    if guild_context.get('user_roles'):
        user_info.append(f"Роли: {', '.join(guild_context['user_roles'])}")
    if guild_context.get('user_joined_days'):
        days = guild_context['user_joined_days']
        if days < 7:
            user_info.append(f"На сервере: {days} дн. (новый участник)")
        else:
            user_info.append(f"На сервере: {days} дн.")
    if guild_context.get('previous_tickets'):
        prev = guild_context['previous_tickets']
        user_info.append(f"Предыдущих тикетов: {len(prev)}")
        if prev:
            last = prev[-1]
            user_info.append(f"Последний тикет: {last.get('category', '?')} ({last.get('status', '?')})")

    if user_info:
        messages.append({
            'role': 'system',
            'content': "ИНФОРМАЦИЯ О ПОЛЬЗОВАТЕЛЕ:\n" + "\n".join(user_info)
        })

    # 5. Контекст сервера
    server_info = []
    if guild_context.get('guild_name'):
        server_info.append(f"Сервер: {guild_context['guild_name']}")
    if guild_context.get('member_count'):
        server_info.append(f"Участников: {guild_context['member_count']}")
    if guild_context.get('panel_url'):
        server_info.append(f"URL панели: {guild_context['panel_url']}")

    if server_info:
        messages.append({
            'role': 'system',
            'content': "КОНТЕКСТ СЕРВЕРА:\n" + "\n".join(server_info)
        })

    # 5.5. Function calling — описание доступных функций
    guild = guild_context.get('guild')
    ai_functions = None
    if guild and AIFunctions:
        ai_functions = AIFunctions(guild.client)
        messages.append({
            'role': 'system',
            'content': ai_functions.get_available_functions()
        })

    # 6. История разговора (последние 20 сообщений)
    if history:
        messages.extend(history[-20:])

    # 7. Текущее сообщение
    messages.append({'role': 'user', 'content': user_message})

    # 8. Вызываем AI с function calling (максимум 3 итерации)
    max_iterations = 3
    for iteration in range(max_iterations):
        response, _, _ = _call(messages, max_tokens=2048, temperature=0.7)
        
        # Проверяем есть ли вызовы функций
        func_calls = re.findall(r'\[FUNC:[^\]]+\]', response)
        
        if not func_calls or not ai_functions or not guild:
            # Нет вызовов функций или function calling недоступен — выходим
            break
        
        # Выполняем функции
        for func_call in func_calls[:3]:  # Максимум 3 функции за раз
            result = await ai_functions.execute_function(func_call, guild)
            if result:
                # Добавляем результат функции в контекст
                messages.append({
                    'role': 'system',
                    'content': f"РЕЗУЛЬТАТ ФУНКЦИИ {func_call}:\n{result}"
                })
        
        # Убираем вызовы функций из ответа
        response = re.sub(r'\[FUNC:[^\]]+\]', '', response).strip()
    
    # 9. Парсим действия
    should_escalate = False
    if 'ACTION:ESCALATE' in response:
        should_escalate = True
        response = response.replace('ACTION:ESCALATE', '').strip()

    # Убираем chain-of-thought блоки если есть
    import re
    response = re.sub(r'<thinking>.*?</thinking>', '', response, flags=re.DOTALL)
    response = re.sub(r'<рассуждение>.*?</рассуждение>', '', response, flags=re.DOTALL)
    response = response.strip()

    if not response:
        response = "Обрабатываю ваш запрос..."

    # 10. Обновляем историю
    updated_history = history + [
        {'role': 'user', 'content': user_message},
        {'role': 'assistant', 'content': response}
    ]

    # Ограничиваем историю 30 сообщениями
    if len(updated_history) > 30:
        updated_history = updated_history[-30:]

    # 11. Автоматическое извлечение и сохранение фактов
    if guild and ai_functions:
        try:
            from web.ai_rag import ConversationAnalyzer
            facts = ConversationAnalyzer.extract_facts(updated_history[-5:])
            
            if facts:
                user_id = guild_context.get('user_id')
                if user_id:
                    for fact in facts[:2]:  # Максимум 2 факта за раз
                        await ai_functions.remember_fact(guild, user_id, fact)
        except Exception as e:
            print(f"[AI] Ошибка извлечения фактов: {e}")

    return response, should_escalate, category, updated_history, category


# ─── ПРИВЕТСТВИЕ ─────────────────────────────────────────────────────────────

def ai_ticket_greeting(category: str = None) -> str:
    """Приветственное сообщение при открытии тикета"""
    return (
        "## Привет! Я — AI ассистент\n\n"
        "Я помогу решить вашу проблему.\n\n"
        "**Опишите что случилось:**\n"
        "- Что не работает?\n"
        "- Какие ошибки видите?\n"
        "- Что уже пробовали?\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "-# Если я не смогу помочь — направлю к модераторам."
    )


# ─── ПАРСИНГ ДЕЙСТВИЙ ───────────────────────────────────────────────────────

def parse_ai_actions(response: str) -> Dict:
    """Парсинг действий из ответа AI"""
    import re

    actions = {
        'escalate': 'ACTION:ESCALATE' in response,
        'warn': None,
        'jail': None,
        'role_assign': None,
        'channel_redirect': None,
        'delete_messages': None,
    }

    # WARN
    warn_match = re.search(r'ACTION:WARN:user_id=(\d+):reason=([^\n]+)', response)
    if warn_match:
        actions['warn'] = {
            'user_id': int(warn_match.group(1)),
            'reason': warn_match.group(2).strip()
        }
        response = re.sub(r'ACTION:WARN:user_id=\d+:reason=[^\n]+', '', response)

    # JAIL
    jail_match = re.search(r'ACTION:JAIL:user_id=(\d+):duration=(\d+):reason=([^\n]+)', response)
    if jail_match:
        actions['jail'] = {
            'user_id': int(jail_match.group(1)),
            'duration': int(jail_match.group(2)),
            'reason': jail_match.group(3).strip()
        }
        response = re.sub(r'ACTION:JAIL:user_id=\d+:duration=\d+:reason=[^\n]+', '', response)

    # ROLE_ASSIGN
    role_match = re.search(r'ACTION:ROLE_ASSIGN:user_id=(\d+):role_id=(\d+)', response)
    if role_match:
        actions['role_assign'] = {
            'user_id': int(role_match.group(1)),
            'role_id': int(role_match.group(2))
        }
        response = re.sub(r'ACTION:ROLE_ASSIGN:user_id=\d+:role_id=\d+', '', response)

    # CHANNEL_REDIRECT
    channel_match = re.search(r'ACTION:CHANNEL_REDIRECT:channel_id=(\d+)', response)
    if channel_match:
        actions['channel_redirect'] = {
            'channel_id': int(channel_match.group(1))
        }
        response = re.sub(r'ACTION:CHANNEL_REDIRECT:channel_id=\d+', '', response)

    # DELETE_MESSAGES
    delete_match = re.search(r'ACTION:DELETE_MESSAGES:channel_id=(\d+):count=(\d+)', response)
    if delete_match:
        actions['delete_messages'] = {
            'channel_id': int(delete_match.group(1)),
            'count': int(delete_match.group(2))
        }
        response = re.sub(r'ACTION:DELETE_MESSAGES:channel_id=\d+:count=\d+', '', response)

    # Убираем пустые строки
    response = '\n'.join(line for line in response.split('\n') if line.strip())

    actions['cleaned_response'] = response
    return actions


# ─── ОБУЧЕНИЕ ИЗ ОТВЕТОВ МОДЕРАТОРОВ ────────────────────────────────────────

def learn_from_staff(staff_message: str, user_question: str, guild_id: int):
    """Автоматическое обучение из ответов модераторов"""
    try:
        faq_file = 'data/faq_learned.json'
        faqs = {}
        if os.path.exists(faq_file):
            with open(faq_file, 'r', encoding='utf-8') as f:
                faqs = json.load(f)

        guild_key = str(guild_id)
        if guild_key not in faqs:
            faqs[guild_key] = []

        # Добавляем вопрос-ответ
        faqs[guild_key].append({
            'question': user_question,
            'answer': staff_message,
            'timestamp': datetime.datetime.utcnow().isoformat()
        })

        # Ограничиваем 100 записями
        if len(faqs[guild_key]) > 100:
            faqs[guild_key] = faqs[guild_key][-100:]

        with open(faq_file, 'w', encoding='utf-8') as f:
            json.dump(faqs, f, ensure_ascii=False, indent=2)

    except Exception as e:
        print(f"[AI LEARN] Ошибка обучения: {e}")


def get_learned_faqs(guild_id: int) -> List[Dict]:
    """Получить выученные FAQ для сервера"""
    try:
        faq_file = 'data/faq_learned.json'
        if os.path.exists(faq_file):
            with open(faq_file, 'r', encoding='utf-8') as f:
                faqs = json.load(f)
            return faqs.get(str(guild_id), [])
    except:
        pass
    return []
