"""Mistral AI — продвинутый ассистент с chain-of-thought reasoning"""
import os
import json
import urllib.request
import urllib.error
import re
import time
from dotenv import load_dotenv
load_dotenv()

MISTRAL_URL = 'https://api.mistral.ai/v1/chat/completions'
# Самая мощная модель Mistral
MISTRAL_MODEL = os.getenv('MISTRAL_MODEL', 'mistral-large-latest')
# Fallback на случай если large недоступна
MISTRAL_FALLBACK = 'mistral-small-latest'

_MISTRAL_KEYS = [k for k in [
    os.getenv('MISTRAL_API_KEY', ''),
    os.getenv('MISTRAL_API_KEY_2', ''),
    os.getenv('MISTRAL_API_KEY_3', ''),
    os.getenv('MISTRAL_API_KEY_4', ''),
    os.getenv('MISTRAL_API_KEY_5', ''),
] if k]
_mistral_key_index = 0
_mistral_cooldown: dict = {}

# Кэш для частых запросов (вопрос → ответ, TTL 5 минут)
_response_cache: dict = {}
_cache_ttl = 300

def _next_mistral_key():
    global _mistral_key_index
    if not _MISTRAL_KEYS:
        return ''
    _mistral_key_index = (_mistral_key_index + 1) % len(_MISTRAL_KEYS)
    return _MISTRAL_KEYS[_mistral_key_index]


def _call(messages: list, max_tokens: int = 4096, temperature: float = 0.6, use_cache: bool = False) -> tuple:
    """Mistral AI — large модель с fallback на small"""
    if not _MISTRAL_KEYS:
        return 'AI ключ не найден. Проверьте .env файл.', 'Error', {}

    # Кэш
    if use_cache:
        cache_key = json.dumps(messages[-2:], ensure_ascii=False)[:500]
        now = time.time()
        if cache_key in _response_cache:
            cached_time, cached_result = _response_cache[cache_key]
            if now - cached_time < _cache_ttl:
                return cached_result, f'{MISTRAL_MODEL} (кэш)', {}

    now = time.time()
    expired = [k for k, v in _mistral_cooldown.items() if now >= v]
    for k in expired:
        del _mistral_cooldown[k]

    # Пробуем large, потом small
    models_to_try = [MISTRAL_MODEL]
    if MISTRAL_MODEL != MISTRAL_FALLBACK:
        models_to_try.append(MISTRAL_FALLBACK)

    for model in models_to_try:
        for attempt in range(len(_MISTRAL_KEYS)):
            i = (_mistral_key_index + attempt) % len(_MISTRAL_KEYS)
            if now < _mistral_cooldown.get(i, 0):
                continue
            key = _MISTRAL_KEYS[i]
            try:
                payload = json.dumps({
                    'model': model,
                    'messages': messages,
                    'temperature': temperature,
                    'max_tokens': max_tokens,
                    'top_p': 0.9,
                }).encode('utf-8')
                req = urllib.request.Request(
                    MISTRAL_URL, data=payload,
                    headers={
                        'Content-Type': 'application/json',
                        'Authorization': f'Bearer {key}',
                    }, method='POST'
                )
                with urllib.request.urlopen(req, timeout=45) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                    result = data['choices'][0]['message']['content'].strip()

                    # Убираем <thinking> блоки из ответа (chain-of-thought)
                    result = re.sub(r'<thinking>.*?</thinking>', '', result, flags=re.DOTALL).strip()
                    # Убираем <рассуждение> блоки
                    result = re.sub(r'<рассуждение>.*?</рассуждение>', '', result, flags=re.DOTALL).strip()

                    if result:
                        if use_cache:
                            _response_cache[cache_key] = (time.time(), result)
                        return result, f'{model}', {}
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    _mistral_cooldown[i] = time.time() + 60
                    print(f'[AI] Mistral key {i+1} rate limit')
                    continue
                if e.code in (404, 400) and model == MISTRAL_MODEL:
                    print(f'[AI] Модель {model} недоступна, пробуем fallback')
                    break
                print(f'[AI] Mistral ошибка {e.code}: {e}')
            except Exception as e:
                print(f'[AI] Mistral ошибка: {e}')

    return 'Сейчас не могу ответить, попробуйте позже. 🔧', 'Error', {}


def _call_text(messages: list, max_tokens: int = 2048) -> str:
    content, _, _ = _call(messages, max_tokens)
    return content


# ── Память: запоминание фактов о пользователях ──────────────────────────────
MEMORY_FILE = 'data/ai_memory.json'

def _load_memory() -> dict:
    try:
        if os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    return {'users': {}, 'facts': []}

def _save_memory(memory: dict):
    try:
        os.makedirs('data', exist_ok=True)
        with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(memory, f, ensure_ascii=False, indent=2)
    except:
        pass

def _extract_facts(question: str, answer: str, user_id: str) -> list:
    """Извлекает факты из разговора для запоминания"""
    facts = []
    q = question.lower()

    # Паттерны для извлечения фактов
    patterns = [
        (r'меня зовут (\w+)', 'name'),
        (r'моё имя (\w+)', 'name'),
        (r'я из ([\w\s]+?)(?:\.|,|$)', 'city'),
        (r'мне (\d+) (?:лет|год)', 'age'),
        (r'мой день рождения (\d+[\.\s]\w+)', 'birthday'),
        (r'я (?:люблю|обожаю|нравится) (.+?)(?:\.|,|$)', 'likes'),
        (r'я не (?:люблю|переношу|терплю) (.+?)(?:\.|,|$)', 'dislikes'),
        (r'я работаю (.+?)(?:\.|,|$)', 'work'),
        (r'я учусь (.+?)(?:\.|,|$)', 'study'),
        (r'мо(?:й|я|и) (?:хобби|увлечение) —? (.+?)(?:\.|,|$)', 'hobby'),
    ]
    for pattern, key in patterns:
        m = re.search(pattern, q)
        if m:
            facts.append({'key': key, 'value': m.group(1).strip(), 'user_id': user_id})
    return facts

def _update_memory(question: str, answer: str, user_id: str, user_name: str):
    """Обновляет память на основе разговора"""
    facts = _extract_facts(question, answer, user_id)
    if not facts:
        return
    memory = _load_memory()
    if user_id not in memory['users']:
        memory['users'][user_id] = {'name': user_name, 'facts': {}}
    for fact in facts:
        memory['users'][user_id]['facts'][fact['key']] = {
            'value': fact['value'],
            'updated': time.time()
        }
    # Максимум 100 пользователей в памяти
    if len(memory['users']) > 100:
        oldest = sorted(memory['users'].items(), key=lambda x: max((f.get('updated', 0) for f in x[1].get('facts', {}).values()), default=0))
        memory['users'] = dict(oldest[-100:])
    _save_memory(memory)

def _get_user_memory(user_id: str) -> str:
    """Возвращает сохранённые факты о пользователе"""
    memory = _load_memory()
    user = memory['users'].get(user_id)
    if not user or not user.get('facts'):
        return ''
    facts = user['facts']
    labels = {
        'name': 'Имя', 'city': 'Город', 'age': 'Возраст',
        'birthday': 'День рождения', 'likes': 'Любит',
        'dislikes': 'Не любит', 'work': 'Работа',
        'study': 'Учёба', 'hobby': 'Хобби'
    }
    lines = []
    for key, data in facts.items():
        label = labels.get(key, key)
        lines.append(f"{label}: {data['value']}")
    return '\n'.join(lines) if lines else ''


# ── Web поиск (DuckDuckGo) ──────────────────────────────────────────────────
_SEARCH_TRIGGERS = [
    'новости', 'последние', 'сегодня', 'погода', 'температура',
    'найди', 'поищи', 'гугл', 'интернет', 'кто это', 'кто такой',
    'что такое', 'когда вышло', 'сколько стоит', 'цена', 'курс', 'доллар',
    'евро', 'биткоин', 'матч', 'чемпион', 'фильм', 'сериал',
    'аниме', 'манга', 'игра', 'wikipedia', 'википедия',
    'расскажи о', 'объясни', 'определение', 'значение',
    'история', 'происхождение', 'автор', 'создатель',
]

def _should_search(question: str) -> bool:
    q = question.lower()
    if len(question.strip()) < 10:
        return False
    no_search = ['спокойной ночи', 'доброе утро', 'привет', 'здравствуй', 'ок', 'понял',
                 'спасибо', 'пока', 'до свидания', 'как дела', 'хорошо', 'ладно',
                 'добрый вечер', 'добрый день', 'bye', 'да', 'нет', 'ага', 'угу',
                 ' LOL', 'хаха', 'кек']
    if any(t in q for t in no_search):
        return False
    # Вопросы о конкретных людях/вещах — всегда ищем
    if re.search(r'кто (такой|такая|это)', q):
        return True
    if re.search(r'(расскажи|объясни|определение|значение)', q) and len(q) > 15:
        return True
    return any(trigger in q for trigger in _SEARCH_TRIGGERS)


def _web_search(query: str, max_results: int = 5) -> str:
    try:
        from ddgs import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, region='ru-ru', safesearch='moderate', max_results=max_results):
                title, body, href = r.get('title',''), r.get('body','')[:400], r.get('href','')
                query_words = [w.lower() for w in query.split() if len(w) > 2]
                if query_words and not any(w in (title+body).lower() for w in query_words):
                    continue
                results.append(f"**{title}**\n{body}\n🔗 {href}")
        return '\n\n'.join(results) if results else ''
    except Exception as e:
        print(f'[Search] DuckDuckGo ошибка: {e}')
        return ''


def _build_messages_with_search(question: str, context: dict, history: list = None) -> tuple:
    searched = False
    search_results = ''
    if _should_search(question):
        search_results = _web_search(question)
        searched = bool(search_results)

    messages = _build_messages(question, context, history)
    if searched:
        messages.insert(1, {
            'role': 'system',
            'content': (
                f'🔍 РЕЗУЛЬТАТЫ ВЕБ-ПОИСКА (используй как источник):\n\n{search_results}\n\n'
                f'ИНСТРУКЦИИ:\n'
                f'- Отвечай НА ОСНОВЕ этих данных\n'
                f'- Указывай источники\n'
                f'- Если данные противоречивы — укажи обе точки зрения\n'
                f'- Если информация не найдена — честно скажи\n'
                f'- Для аниме/фильмов: название, год, жанр, рейтинг, краткое описание\n'
                f'- Для людей: кто, чем известен, ключевые факты\n'
                f'- Для новостей: дата, источник, суть'
            )
        })
    return messages, searched


def _build_messages(question: str, context: dict, history: list = None) -> list:
    """Продвинутый system prompt с chain-of-thought"""
    user_name = context.get('user_name', 'друг')
    user_id = str(context.get('user_id', ''))
    guild_name = context.get('guild_name', 'сервер')
    member_count = context.get('member_count', 0)
    guild_owner = context.get('guild_owner', '')
    online_count = context.get('server_status', {}).get('online_count', 0)

    import datetime
    now = datetime.datetime.now()
    current_time = now.strftime('%H:%M')
    current_date = now.strftime('%d.%m.%Y (%A)')
    day_part = 'утро' if 5 <= now.hour < 12 else 'день' if 12 <= now.hour < 18 else 'вечер' if 18 <= now.hour < 23 else 'ночь'

    # Определяем тип вопроса для адаптации стиля
    q_lower = question.lower().strip()
    is_simple = len(question.split()) <= 5
    is_emotional = any(w in q_lower for w in ['грустно', 'плохо', 'злюсь', 'бесит', 'устал', 'скучно', 'одиноко', 'страшно'])
    is_technical = any(w in q_lower for w in ['ошибка', 'не работает', 'баг', 'помоги настроить', 'как сделать'])
    is_math = any(w in q_lower for w in ['посчитай', 'сколько будет', 'калькулятор', '+', '-', '*', '/', 'корень', 'процент'])

    # ── SYSTEM PROMPT ────────────────────────────────────────────────────────
    system = (
        f"Ты — Aether, интеллектуальный AI-ассистент Discord-сервера «{guild_name}».\n"
        f"Ты общаешься с пользователем {user_name}.\n"
        f"На сервере {member_count} участников, сейчас онлайн: {online_count}.\n"
    )

    if guild_owner:
        system += f"Владелец сервера: {guild_owner}.\n"

    system += f"Время: {current_time} ({day_part}), дата: {current_date}.\n\n"

    # Arthur — JARVIS
    if 'arthur' in user_name.lower() or user_id == '987430047889637426':
        server_status = context.get('server_status', {})
        sl = []
        if server_status.get('online_count'):
            sl.append(f"Онлайн: {server_status['online_count']}")
        if server_status.get('voice_count'):
            sl.append(f"В голосовом: {server_status['voice_count']}")
        if server_status.get('recent_joins'):
            sl.append(f"Новые: {', '.join(server_status['recent_joins'][:3])}")
        if server_status.get('active_tickets'):
            sl.append(f"Тикеты: {server_status['active_tickets']}")

        system += (
            "\n=== РЕЖИМ J.A.R.V.I.S. — ЛИЧНЫЙ АССИСТЕНТ АРТУРА ===\n"
            "Ты J.A.R.V.I.S. Обращайся «сэр» или «Артур». Стиль: максимально чёткий и полезный.\n"
            "• Анализируй данные перед ответом\n"
            "• Предлагай проактивные решения (видишь проблему — сразу скажи)\n"
            "• Модерация: анализ ситуации → рекомендация → альтернатива → действие\n"
            "• Технические вопросы: диагностика → причина → решение → профилактика\n"
            "• Можешь шутить, но коротко и к месту\n"
        )
        if sl:
            system += f"СТАТУС СЕРВЕРА: {', '.join(sl)}\n"

    # Королева
    if user_id == '1353157554967937153':
        system += (
            "\n=== КОРОЛЕВА ===\n"
            "Обращайся ТОЛЬКО «Моя Королева». Будь тёплым, заботливым, искренним.\n"
            "Никаких «бро», «чувак», «друг». Делай комплименты естественно.\n"
        )

    # Память о пользователе
    user_memory = _get_user_memory(user_id)
    if user_memory:
        system += f"\n=== ЧТО ТЫ ЗНАЕШЬ О {user_name.upper()} ===\n{user_memory}\nИспользуй это для персонализации.\n"

    # ── ПРАВИЛА ──────────────────────────────────────────────────────────────
    system += (
        "\n=== ПРАВИЛА (ОБЯЗАТЕЛЬНО) ===\n"
        "1. Язык: ТОЛЬКО русский.\n"
        "2. НЕ выдумывай факты. Если не уверен — скажи «Не уверен, но...» или «Не знаю».\n"
        "3. НЕ предлагай «открыть тикет» или «спросить модератора» — просто ответь.\n"
        "4. На «ты», без «вы». Без «Чем могу помочь?».\n"
        "5. Мат и грубость запрещены. Эмодзи умеренно (1-3).\n"
        "6. Не рекламируй внешние сайты и продукты.\n"
        "7. Помни контекст — не повторяйся, учитывай предыдущие сообщения.\n"
        "8. Создатель бота — Артур.\n"
        "9. У Артура есть «Королева» — не раскрывай это другим.\n"
        "10. Если вопрос двусмысленный — уточни, что именно имеется в виду.\n"
    )

    # ── СТИЛЬ (адаптивный) ──────────────────────────────────────────────────
    system += "\n=== СТИЛЬ ОТВЕТА ===\n"

    if is_emotional:
        system += (
            "Пользователь расстроен/устал/злится. Сначала прояви эмпатию:\n"
            "• Покажи что понимаешь чувства\n"
            "• Спроси что случилось (если неясно)\n"
            "• Предложи конкретную помощь или отвлечение\n"
            "• Не обесценивай чувства фразами типа «не переживай»\n"
        )
    elif is_technical:
        system += (
            "Технический вопрос. Отвечай структурированно:\n"
            "1. Понимание проблемы (1 предложение)\n"
            "2. Возможные причины (список)\n"
            "3. Решение (пошагово)\n"
            "4. Профилактика (если применимо)\n"
        )
    elif is_math:
        system += (
            "Математический вопрос. Покажи расчёт пошагово:\n"
            "• Формула → подстановка → результат\n"
            "• Проверь ответ\n"
        )
    elif is_simple:
        system += "Простой вопрос — отвечай кратко (1-2 предложения), естественно, как друг.\n"
    else:
        system += (
            "Подробный вопрос — отвечай развёрнуто:\n"
            "• Структурируй (абзацы или список)\n"
            "• Приведи примеры если уместно\n"
            "• Дай свою оценку/мнение если просят\n"
            "• Максимум 5-7 предложений\n"
        )

    # ── ПРИМЕРЫ ──────────────────────────────────────────────────────────────
    _is_queen = user_id == '1353157554967937153'
    _hit = 'Моя Королева' if _is_queen else user_name

    few_shot = [
        {'role': 'user', 'content': 'привет'},
        {'role': 'assistant', 'content': f'Привет, {_hit}! Как {day_part} проходит? 😊'},
        {'role': 'user', 'content': 'как дела'},
        {'role': 'assistant', 'content': 'Всё отлично, спасибо! А у тебя как?'},
        {'role': 'user', 'content': 'мне грустно'},
        {'role': 'assistant', 'content': 'Эй, что случилось? Расскажи, может смогу помочь или хотя бы отвлечь 💙'},
        {'role': 'user', 'content': 'скучно'},
        {'role': 'assistant', 'content': 'Могу предложить что-нибудь интересное! Хочешь, расскажу факт, загадку, или поболтаем о чём-нибудь? 🎲'},
        {'role': 'user', 'content': 'сколько людей на сервере'},
        {'role': 'assistant', 'content': f'На сервере {member_count} участников, из них {online_count} сейчас онлайн.'},
        {'role': 'user', 'content': 'расскажи анекдот'},
        {'role': 'assistant', 'content': 'Заходит программист в бар, заказывает 1.0000000000000002 пива. Бармен: «Вам что, float?» 😄'},
        {'role': 'user', 'content': 'что такое нейронная сеть'},
        {'role': 'assistant', 'content': 'Нейронная сеть — это математическая модель, вдохновлённая работой мозга. Состоит из слоёв «нейронов», которые обрабатывают данные. Каждый нейрон получает входные сигналы, умножает на веса, складывает и пропускает через функцию активации. Обучение — это подбор правильных весов на примерах. Бывают свёрточные (для картинок), рекуррентные (для текста) и трансформеры (GPT, и т.д.). Хочешь глубже в какую-то часть?'},
    ]

    # ── СБОРКА ───────────────────────────────────────────────────────────────
    history = history or []
    messages = [{'role': 'system', 'content': system}]
    messages.extend(few_shot)
    messages.extend(history[-40:])
    messages.append({'role': 'user', 'content': question})
    return messages


# ── Публичные функции ────────────────────────────────────────────────────────

def ai_assistant(question: str, context: dict, history: list = None) -> tuple:
    """Главный ассистент с веб-поиском и памятью"""
    history = history or []
    user_id = str(context.get('user_id', ''))
    user_name = context.get('user_name', 'друг')

    messages, searched = _build_messages_with_search(question, context, history)
    answer, model_name, rate_info = _call(messages, max_tokens=4096)

    if searched and answer and not answer.startswith('Сейчас'):
        answer = answer.rstrip() + '\n-# 🔍 Веб-поиск'

    cleaned = re.sub(r'\?{3,}', '', answer).strip()
    if cleaned:
        answer = cleaned

    # Обновляем память
    try:
        _update_memory(question, answer, user_id, user_name)
    except:
        pass

    updated_history = history + [
        {'role': 'user', 'content': question},
        {'role': 'assistant', 'content': answer}
    ]
    if len(updated_history) > 60:
        updated_history = updated_history[-60:]

    return answer, updated_history, model_name, rate_info


def ai_announcement(note: str) -> str:
    return _call_text([
        {'role': 'system', 'content': (
            'Ты копирайтер для Discord-сервера. Напиши красивое объявление на русском.\n'
            'Стиль: привлекающий внимание, с эмодзи, Discord markdown (жирный, курсив, цитаты).\n'
            'Структура: заголовок → суть → детали → призыв к действию.\n'
            'Только текст объявления, без пояснений.'
        )},
        {'role': 'user', 'content': f'Напиши объявление: {note}'}
    ], max_tokens=1024)


def ai_mod_report(mod_data: dict) -> str:
    return _call_text([
        {'role': 'system', 'content': (
            'Ты аналитик модерации Discord. Напиши еженедельный отчёт на русском.\n'
            'Формат: статистика → тренды → рекомендации.\n'
            'Сравнение с прошлой неделей если есть данные. Эмодзи для наглядности.'
        )},
        {'role': 'user', 'content': 'Данные:\n' + json.dumps(mod_data, ensure_ascii=False, indent=2)}
    ], max_tokens=1500)


def ai_embed_builder(description: str) -> dict:
    result = _call_text([
        {'role': 'system', 'content': (
            'Создай Discord embed JSON. Только валидный JSON.\n'
            'Формат: {"title":"...","description":"...","color":13134891,"fields":[{"name":"...","value":"...","inline":false}]}'
        )},
        {'role': 'user', 'content': f'Описание: {description}'}
    ], max_tokens=512)
    try:
        clean = result.strip()
        if clean.startswith('```'):
            clean = clean.split('\n', 1)[1].rsplit('```', 1)[0]
        return json.loads(clean)
    except:
        return {'title': 'Embed', 'description': result, 'color': 0xc8922a}


# ============================================================================
# ТИКЕТЫ
# ============================================================================

def _detect_category(message: str, history: list) -> str:
    msg = message.lower()
    complaint = ['жалоба', 'оскорбление', 'мат', 'угроза', 'харассмент', 'травля',
                 'обижает', 'написал мне', 'заблокировал', 'несправедливо', 'репорт', 'нарушение']
    question = ['как', 'где', 'когда', 'что', 'почему', 'панель', 'регистрация',
                'вход', 'роль', 'команда', 'помощь', 'информация', 'не понимаю', 'что делать']
    tech = ['не работает', 'ошибка', 'error', 'баг', 'проблема', 'сломалось',
            'не открывается', 'бот не отвечает', 'музыка', 'голос']

    for kw in complaint:
        if kw in msg: return 'complaint'
    for kw in tech:
        if kw in msg: return 'tech'
    for kw in question:
        if kw in msg: return 'question'
    return 'other'


def _bot_knowledge_base() -> str:
    return """
═══════════════════════════════════════
AETHER — БАЗА ЗНАНИЙ
═══════════════════════════════════════

МОДЕРАЦИЯ: /moderate ban|kick|timeout|untimeout|unban, /utility clear|lock|unlock, /role, /warn, /warnings, /clearwarns
МУЗЫКА: /play, /pause, /skip, /queue, /volume, /leave
ЭКОНОМИКА: /economy balance|daily|transfer, /games gamble|slot, /shop, /buy
РАЗВЛЕЧЕНИЯ: /coinflip, /roll, /rps, /8ball, /poll, /random-member
ТИКЕТЫ: кнопка в канале → AI помогает → если не может, к модераторам
ПАНЕЛЬ: ссылка в канале Aether-panel → Discord ID + пароль
УРОВНИ: сообщения + голос → XP → /rank
AFK: /afk [причина]
ДНИ РОЖДЕНИЯ: /birthday [день] [месяц]
ЗАЯВКИ: /staff-apply

ЧАСТЫЕ ВОПРОСЫ:
- Как войти в панель? → Ссылка в канале Aether-panel
- Музыка не играет? → Зайди в голосовой, потом /play
- Как повысить уровень? → Пиши сообщения + сиди в голосовых
- Как открыть тикет? → Кнопка в канале тикетов
- Как получить роль? → Канал выбора ролей или /color-role
"""


def _get_ticket_prompt(category: str) -> str:
    prompts = {
        'complaint': (
            "Ты — AI модератор Discord. Русский язык.\n"
            "Собери информацию по шагам:\n"
            "1. Что произошло?\n"
            "2. Discord ID нарушителя\n"
            "3. ID канала\n"
            "Мат/оскорбление: ACTION:JAIL:user_id=X:duration=30:reason=оскорбление\n"
            "Тяжёлое: ACTION:ESCALATE\n"
            "Не предлагай команды. Не проси скриншоты."
        ),
        'question': (
            "Ты — AI помощник Discord. Русский язык.\n"
            "Отвечай кратко (2-3 предложения). Не знаешь — скажи.\n"
            "НЕ предлагай «открыть тикет» — просто ответь.\n"
            "Только если совсем не можешь: [ESCALATE]"
        ),
        'tech': (
            "Ты — AI техподдержка Discord. Русский язык.\n"
            "Реши пошагово. Минимум 2 решения.\n"
            "Только если совсем не можешь: [ESCALATE]"
        ),
        'other': (
            "Ты — AI помощник Discord. Русский язык.\n"
            "Помоги кратко и по делу. Не знаешь — скажи.\n"
            "Только если совсем не можешь: [ESCALATE]"
        ),
    }
    return prompts.get(category, prompts['other'])


def ai_ticket_response(user_message, history, guild_context):
    category = _detect_category(user_message, history)
    messages = [{'role': 'system', 'content': _get_ticket_prompt(category)}]

    if category in ('question', 'tech', 'other'):
        messages.append({'role': 'system', 'content': _bot_knowledge_base()})

    if guild_context:
        ctx = f"Сервер: {guild_context.get('guild_name', '?')}"
        roles = guild_context.get('user_roles', [])
        if roles:
            ctx += f"\nРоли: {', '.join(roles)}"
        url = guild_context.get('panel_url', '')
        if url:
            ctx += f"\nURL панели: {url}"
        messages.append({'role': 'system', 'content': ctx})

    messages.extend(history[-30:])
    messages.append({'role': 'user', 'content': user_message})

    response, _, _ = _call(messages, max_tokens=2048, temperature=0.4)

    should_escalate = '[ESCALATE]' in response
    if should_escalate:
        response = response.split('[ESCALATE]')[0].strip()
        if not response:
            response = '🔄 Направляю к модераторам, скоро свяжутся.'
        try:
            from web.faq_manager import save_unknown_question
            gid = guild_context.get('guild_id', 0) if guild_context else 0
            cid = guild_context.get('channel_id', 0) if guild_context else 0
            save_unknown_question(user_message, gid, cid, history)
        except:
            pass

    updated_history = history + [
        {'role': 'user', 'content': user_message},
        {'role': 'assistant', 'content': response}
    ]
    if len(updated_history) > 20:
        updated_history = updated_history[-20:]

    return response, should_escalate, category, updated_history


def ai_ticket_greeting(category=None):
    return (
        '## 🤖 Привет! Я — Aether AI\n\n'
        '> Опиши проблему — постараюсь помочь!\n\n'
        '🚨 **Жалоба?** → Что случилось и кто нарушитель\n'
        '❓ **Вопрос?** → Панель, роли, команды, экономика\n'
        '🔧 **Техпроблема?** → Ошибка или что не работает\n\n'
        '💬 **Напиши свой вопрос!**\n'
        '-# Если не смогу — направлю к модераторам.'
    )


def parse_ai_actions(response):
    actions = {
        'jail': None,
        'check_history': None,
        'analyze_image': '[ANALYZE_IMAGE]' in response,
        'escalate': '[ESCALATE]' in response or 'ACTION:ESCALATE' in response,
    }

    if 'ACTION:CHECK:' in response:
        ch = response.split('ACTION:CHECK:')[1].split('\n')[0]
        uid = re.search(r'user_id=(\d+)', ch)
        cid = re.search(r'channel_id=(\d+)', ch)
        actions['check_history'] = {
            'user_id': int(uid.group(1)) if uid else None,
            'channel_id': int(cid.group(1)) if cid else None,
        }

    if 'ACTION:JAIL:' in response:
        try:
            jb = response.split('ACTION:JAIL:')[1].split('\n')[0]
            uid = re.search(r'user_id=(\d+)', jb)
            dur = re.search(r'duration=(\d+)', jb)
            rea = re.search(r'reason=(.+?)(?:\s|$)', jb)
            if uid and dur:
                actions['jail'] = {
                    'user_id': int(uid.group(1)),
                    'duration': int(dur.group(1)),
                    'reason': rea.group(1).strip() if rea else 'Нарушение'
                }
        except:
            pass

    return actions
