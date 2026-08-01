"""AI Chat Cog — DM + channel sohbet"""
import discord
from discord.ext import commands
import re
import json
import os
import datetime

from logger import get_logger
log = get_logger("ai_chat")


AI_CHANNELS = set()  # Пусто — dinamik как addnir
# Динамические каналы — DM'den addnip удалить
_dynamic_channels: set = set()  # DM'den /ai-channel команда addnir

#  АКТИВЕН ЗАДАЧИ (условный задача цепь) 
_active_tasks: list = []  # [{'id': int, 'desc': str, 'condition': str, 'action': str, 'target_id': int}]
_task_counter: int = 0

def _load_tasks() -> list:
    f = 'data/jarvis_tasks.json'
    if os.path.exists(f):
        try:
            with open(f, 'r', encoding='utf-8') as fp:
                return json.load(fp)
        except Exception:
            pass
    return []

def _save_tasks(tasks: list):
    os.makedirs('data', exist_ok=True)
    with open('data/jarvis_tasks.json', 'w', encoding='utf-8') as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)

_active_tasks = _load_tasks()

# Owner ID — пересылает неизвестные вопросы сюда
OWNER_ID = int(os.getenv('OWNER_ID') or '0')

# Baddyen sorular — owner ответитьince userya iletilir
# {owner_dm_message_id: {'user_id': int, 'channel_id': int, 'question': str, 'is_dm': bool}}
_pending_questions: dict = {}

# Мат filtresi — совпадение полного слова
KUFUR_LISTESI = ['amk', 'amq', 'orospu', 'sik', 'göt', 'got', 'piç', 'pic',
                 'yarrak', 'yarak', 'siktir', 'bok', 'kahpe', 'ibne', 'amcık', 'amcik']

def _kufur_var_mi(text: str) -> bool:
    t = text.lower()
    # Tam kelime eşleşmesi для пусто/пунктуация с должно быть окружено
    import re
    for k in KUFUR_LISTESI:
        if re.search(r'\b' + re.escape(k) + r'\b', t):
            return True
    return False

# Пользователь основанный на разговор история — постоянный depolama
HISTORY_FILE = 'data/ai_chat_histories.json'
KNOWLEDGE_FILE = 'data/ai_knowledge_base.json'
INSTRUCTIONS_FILE = 'data/ai_instructions.json'
PROFILES_FILE = 'data/ai_user_profiles.json'  # Пользователь профили личности
OWNER_PREFS_FILE = 'data/owner_preferences.json'  # Arthur'un постоянный tercihleri
_save_counter = 0


def _load_owner_prefs() -> dict:
    if os.path.exists(OWNER_PREFS_FILE):
        try:
            with open(OWNER_PREFS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {'rules': [], 'memory': {}, 'disabled_notifications': []}


def _save_owner_prefs(prefs: dict):
    os.makedirs('data', exist_ok=True)
    with open(OWNER_PREFS_FILE, 'w', encoding='utf-8') as f:
        json.dump(prefs, f, ensure_ascii=False, indent=2)


_owner_prefs = _load_owner_prefs()


def _load_profiles() -> dict:
    if os.path.exists(PROFILES_FILE):
        try:
            with open(PROFILES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_profiles(profiles: dict):
    try:
        os.makedirs('data', exist_ok=True)
        with open(PROFILES_FILE, 'w', encoding='utf-8') as f:
            json.dump(profiles, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.info(f'[AI] Profil сохран Ошибки: {e}')


def _update_profile(user_id: int, question: str, answer: str, profiles: dict):
    """Разговор user profilini обновить"""
    uid = str(user_id)
    if uid not in profiles:
        profiles[uid] = {
            'interests': [],
            'style': 'normal',
            'message_count': 0,
            'topics': {}
        }
    p = profiles[uid]
    p['message_count'] = p.get('message_count', 0) + 1

    # Определение интересов
    interest_keywords = {
        'музыка': ['музыка', 'песня', 'альбом', 'исполнитель', 'rap', 'pop', 'rock'],
        'oyun': ['oyun', 'game', 'lol', 'valorant', 'minecraft', 'cs2'],
        'anime': ['anime', 'manga', 'naruto', 'attack on titan', 'one piece'],
        'spor': ['футбол', 'баскетбол', 'матч', 'гол', 'команда'],
        'teknoloji': ['kod', 'python', 'infosayar', 'написано', 'ai'],
    }
    q_lower = question.lower()
    for interest, keywords in interest_keywords.items():
        if any(kw in q_lower for kw in keywords):
            if interest not in p['interests']:
                p['interests'].append(interest)
            p['topics'][interest] = p['topics'].get(interest, 0) + 1

    # Разговор определение стиля
    if len(question) < 10:
        p['style'] = 'краткий'
    elif '?' in question and len(question) > 50:
        p['style'] = 'любопытный'


_profiles = _load_profiles()

def _load_histories() -> dict:
    """Разговор история dosyadan загрузить"""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # String key'leri int'e преобразовать
                return {int(k): v for k, v in data.items()}
        except Exception as e:
            log.info(f'[AI] History загруз Ошибки: {e}')
    return {}

def _load_knowledge_base() -> dict:
    """Сервер основанный на info базу загрузить"""
    if os.path.exists(KNOWLEDGE_FILE):
        try:
            with open(KNOWLEDGE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            log.info(f'[AI] Knowledge base загруз Ошибки: {e}')
    return {}

def _load_instructions() -> dict:
    """Сервер основанный на постоянный инструкции загрузить"""
    if os.path.exists(INSTRUCTIONS_FILE):
        try:
            with open(INSTRUCTIONS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            log.info(f'[AI] Instructions загруз Ошибки: {e}')
    return {}

def _save_instructions(instructions: dict):
    """Постоянный инструкции сохранить"""
    try:
        os.makedirs('data', exist_ok=True)
        with open(INSTRUCTIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(instructions, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.info(f'[AI] Instructions сохран Ошибки: {e}')

def _detect_instruction(message: str, answer: str) -> dict:
    """
    Пользователь bot'a данные постоянный инструкции определить.
    Напр.: "bu soruyu кто sorarsa X ответить"
    """
    m = message.lower().strip()
    
    # Talimat kalıpları
    patterns = [
        # "bu soruyu кто кто бы ни написал X ответить"
        r'bu soruyu кто (кто бы ни написал|кто бы ни спросил|sorsa)',
        # "всем X de / сказать"
        r'всем .{3,50} (de|сказать|ответить)',
        # "bundan после X dersen Y de"
        r'bundan после .{3,50} (dersen|sorarsa)',
        # "X на вопрос Y ответить"
        r'.{3,30} на вопрос .{3,50} (ответить|de|сказать)',
    ]
    
    import re
    for pattern in patterns:
        if re.search(pattern, m):
            return {
                'trigger': message,   # Tetikleyici message
                'response': answer,   # Botun ответ для выдачи (предыдущий ответ)
                'instruction': message
            }
    return None

def _save_histories(histories: dict, force: bool = False):
    """Разговор история dosyaya сохранить (batch mode)"""
    global _save_counter
    _save_counter += 1
    # Каждый 5 messageda bir или force=True ise сохранить
    if not force and _save_counter % 5 != 0:
        return
    try:
        os.makedirs('data', exist_ok=True)
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(histories, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.info(f'[AI] History сохран Ошибки: {e}')

def _save_knowledge_base(knowledge: dict):
    """Информация базу сохранить"""
    try:
        os.makedirs('data', exist_ok=True)
        with open(KNOWLEDGE_FILE, 'w', encoding='utf-8') as f:
            json.dump(knowledge, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.info(f'[AI] Knowledge base сохран Ошибки: {e}')

def _extract_learned_info(question: str, answer: str) -> dict:
    """Вопрос-cevaptan обучаемый infoyi удалить"""
    q = question.lower().strip()
    
    # Web если выполнен поиск доверие низкий
    is_web_search = ' Web поиск выполнен' in answer
    confidence = 'low' if is_web_search else 'high'
    
    # "X кто" вопросы
    if 'кто takoy' in q or 'кто bu' in q or 'кто on' in q:
        # Вопросdan ismi удалить
        name_patterns = [
            r'(\w+(?:\s+\w+)*)\s+кто',
            r'кто\s+bu\s+(\w+(?:\s+\w+)*)',
            r'кто\s+o\s+(\w+(?:\s+\w+)*)'
        ]
        for pattern in name_patterns:
            import re
            match = re.search(pattern, q)
            if match:
                name = match.group(1).strip()
                return {
                    'type': 'person_info',
                    'name': name,
                    'info': answer[:500],  # Первый 500 karakter
                    'question': question,
                    'confidence': confidence,
                    'source': 'web_search' if is_web_search else 'chat'
                }
    
    # "X nedir" вопросы
    if 'ne takoe' in q or 'ne bu' in q:
        # Вопросdan konuyu удалить
        topic_patterns = [
            r'(\w+(?:\s+\w+)*)\s+nedir',
            r'ne\s+bu\s+(\w+(?:\s+\w+)*)'
        ]
        for pattern in topic_patterns:
            import re
            match = re.search(pattern, q)
            if match:
                topic = match.group(1).strip()
                return {
                    'type': 'topic_info',
                    'topic': topic,
                    'info': answer[:500],
                    'question': question,
                    'confidence': confidence,
                    'source': 'web_search' if is_web_search else 'chat'
                }
    
    return None

_histories = _load_histories()
_knowledge_base = _load_knowledge_base()
_instructions = _load_instructions()

# Сообщение cache — каждый user для 5 minutesda bir обновить
_message_cache = {}
_cache_timeout = 300  # 5 minutes


async def _get_recent_user_messages(user_id: int, guild, limit: int = 15) -> list:
    """Пользователь son Discord messagelarını собрать (son 12 часов, max 15 message)"""
    if not guild:
        return []
    
    import datetime
    import time
    
    # Cache контроль
    cache_key = f"{guild.id}_{user_id}"
    now = time.time()
    if cache_key in _message_cache:
        cached_data, cached_time = _message_cache[cache_key]
        if now - cached_time < _cache_timeout:
            return cached_data
    
    recent = []
    cutoff_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=12)
    
    try:
        # Только активен channelları сканировать (son 2 saatte message который является)
        active_channels = []
        for channel in guild.text_channels:
            if not channel.permissions_for(guild.me).read_message_history:
                continue
            try:
                # В конец сообщение контроль et
                last_msg = await channel.history(limit=1).flatten()
                if last_msg and (datetime.datetime.now(datetime.timezone.utc) - last_msg[0].created_at).seconds < 7200:
                    active_channels.append(channel)
            except Exception:
                continue
        
        # Активен channelları сканировать — 15 message найден ca dur
        for channel in active_channels[:15]:  # Max 15 channel
            try:
                async for msg in channel.history(limit=30, after=cutoff_time):
                    if msg.author.id == user_id and not msg.content.startswith('moe'):
                        # Bot не включать команды
                        recent.append({
                            'channel': channel.name,
                            'content': msg.content[:200],  # 150 → 200 karakter
                            'timestamp': msg.created_at.strftime('%H:%M')
                        })
                        if len(recent) >= limit:  # 15 message найден ca dur
                            break
            except Exception:
                continue
            
            if len(recent) >= limit:
                break
        
        # Время по очередь (en новый en sonda)
        recent.sort(key=lambda x: x['timestamp'])
        result = recent[-limit:]  # В конец 15 message
        
        # Cache'e сохранить
        _message_cache[cache_key] = (result, now)
        return result
    except Exception as e:
        log.info(f'[AI] Сообщение собратьma Ошибки: {e}')
        return []


async def _get_channel_context(channel, limit: int = 12) -> list:
    """Текущий channelın son messagelarını собрать (sohbet контекст для)"""
    try:
        context_messages = []
        async for msg in channel.history(limit=limit):
            if msg.author.bot:
                continue  # Bot messagelarını dahil etme
            context_messages.append({
                'author': msg.author.display_name,
                'content': msg.content[:200],  # 150 → 200 karakter
                'timestamp': msg.created_at.strftime('%H:%M')
            })
        # Ters преобразовать (en старый en başta)
        context_messages.reverse()
        return context_messages
    except Exception as e:
        log.info(f'[AI] Канал context Ошибки: {e}')
        return []


def _call_ai(question: str, user_id: int, guild=None, recent_messages: list = None, channel_context: list = None) -> str:
    try:
        from web.ai_helper import ai_assistant
        history = _histories.get(user_id, [])
        
        # Пользователь infosi
        user_name = 'arkadaş'
        guild_id = 0
        if guild:
            member = guild.get_member(user_id)
            guild_id = guild.id
            if member:
                user_name = member.display_name
        
        is_dm = guild is None
        context = {
            'user_name': user_name,
            'user_id': str(user_id),
            'guild_name': guild.name if guild else 'DM',
            'member_count': guild.member_count if guild else 0,
            'guild_id': guild_id,
            'is_dm': is_dm,
        }
        
        # Сервер sahibi ve администратор роли infosi
        if guild:
            try:
                owner = guild.owner
                if owner:
                    context['guild_owner'] = owner.display_name

                # Администратор роли — manage_messages или kick разрешение которые являются
                staff_roles = []
                for role in guild.roles:
                    if role.is_default():
                        continue
                    if role.permissions.manage_messages or role.permissions.kick_members or role.permissions.administrator:
                        members = [m.display_name for m in role.members if not m.bot][:5]
                        if members:
                            staff_roles.append({'name': role.name, 'members': members})
                if staff_roles:
                    context['staff_roles'] = staff_roles[:8]  # Max 8 роли
            except Exception as e:
                log.info(f'[AI] Guild info Ошибки: {e}')

        #  СЕРВЕР СОСТОЯНИЕ (J.A.R.V.I.S. разница) 
        if guild and str(user_id) == '987430047889637426':
            try:
                online = [m for m in guild.members if not m.bot and m.status != discord.Status.offline]
                in_voice = []
                for vc in guild.voice_channels:
                    for m in vc.members:
                        if not m.bot:
                            in_voice.append(m.display_name)
                # В конец katılanlar (son 24 часов)
                import datetime as _dt
                cutoff = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=24)
                recent_joins = [m.display_name for m in guild.members
                                if not m.bot and m.joined_at and m.joined_at > cutoff]
                # Открыт ticket channelları
                ticket_channels = [c for c in guild.text_channels if c.name.startswith('ticket-')]
                context['sunucu_status'] = {
                    'online_count': len(online),
                    'voice_count': len(in_voice),
                    'voice_members': in_voice[:5],
                    'recent_joins': recent_joins[:5],
                    'active_tickets': len(ticket_channels),
                    'total_members': guild.member_count,
                }
            except Exception as e:
                log.info(f'[AI] Сервер status Ошибки: {e}')

        #  АКТИВЕН ЗАДАЧИ 
        if str(user_id) == '987430047889637426':
            try:
                from cogs.ai_chat import _active_tasks
                if _active_tasks:
                    context['active_tasks'] = [t['desc'] for t in _active_tasks[:5]]
            except Exception:
                pass
        
        # Пользователь son Discord messagelarını context'e add (только на сервере)
        if recent_messages:
            context['recent_user_messages'] = recent_messages
        
        # Канал контекстnı add (только на сервере)
        if channel_context:
            context['channel_context'] = channel_context
        
        # Сервер info tabanından ilgili информация add
        if guild_id and str(guild_id) in _knowledge_base:
            guild_knowledge = _knowledge_base[str(guild_id)]
            relevant_knowledge = []
            q_lower = question.lower()
            
            for item in guild_knowledge:
                # Низкий доверие информация atla (web поиск)
                if item.get('confidence') == 'low':
                    continue
                    
                # Вопрос benzerliği контроль et
                if any(word in item.get('question', '').lower() for word in q_lower.split() if len(word) > 2):
                    relevant_knowledge.append(f"заранее öğrenilen: {item.get('question', '')} → {item.get('info', '')}")
                # Isim/konu benzerliği контроль et
                elif 'name' in item and any(word in item['name'].lower() for word in q_lower.split() if len(word) > 2):
                    relevant_knowledge.append(f"Bilinen человек: {item['name']} → {item.get('info', '')}")
                elif 'topic' in item and any(word in item['topic'].lower() for word in q_lower.split() if len(word) > 2):
                    relevant_knowledge.append(f"Bilinen konu: {item['topic']} → {item.get('info', '')}")
            
            if relevant_knowledge:
                context['learned_knowledge'] = relevant_knowledge[:3]  # En fazla 3 info
        
        # Сервер инструкцииnı context'e add
        if guild_id:
            guild_instructions = _instructions.get(str(guild_id), [])
            if guild_instructions:
                context['guild_instructions'] = guild_instructions

        # Пользователь kişilik profilini context'e add
        uid_str = str(user_id)
        if uid_str in _profiles:
            p = _profiles[uid_str]
            if p.get('interests'):
                context['user_interests'] = p['interests'][:5]
            if p.get('style'):
                context['user_style'] = p['style']

        answer, new_history, model_name, _ = ai_assistant(question, context, history)

        # Profili обновить
        _update_profile(user_id, question, answer, _profiles)
        if _profiles.get(str(user_id), {}).get('message_count', 0) % 10 == 0:
            _save_profiles(_profiles)
        
        # Talimat tespiti — "всем X ответить" gibi messagelar
        if guild_id:
            instr = _detect_instruction(question, answer)
            if instr:
                guild_key = str(guild_id)
                if guild_key not in _instructions:
                    _instructions[guild_key] = []
                # Одинаковый talimat var mı?
                exists = any(i.get('trigger') == instr['trigger'] for i in _instructions[guild_key])
                if not exists:
                    _instructions[guild_key].append(instr)
                    if len(_instructions[guild_key]) > 30:
                        _instructions[guild_key] = _instructions[guild_key][-30:]
                    _save_instructions(_instructions)
                    log.info(f'[AI] Новый talimat сохранено: {instr["trigger"][:50]}')
        
        # Öğrenilebilir infoyi удалить ve сохранить
        if guild_id:
            learned = _extract_learned_info(question, answer)
            if learned:
                guild_key = str(guild_id)
                if guild_key not in _knowledge_base:
                    _knowledge_base[guild_key] = []
                
                # Одинаковый info var mı контроль et
                existing = False
                for item in _knowledge_base[guild_key]:
                    if (item.get('name') == learned.get('name') or 
                        item.get('topic') == learned.get('topic')):
                        # Обновить
                        item.update(learned)
                        existing = True
                        break
                
                if not existing:
                    _knowledge_base[guild_key].append(learned)
                    # Max 50 info tut
                    if len(_knowledge_base[guild_key]) > 50:
                        _knowledge_base[guild_key] = _knowledge_base[guild_key][-50:]
                
                _save_knowledge_base(_knowledge_base)
        
        # В конец 40 сообщение tut (20 soru-cevap çifti) — более uzun hafıza
        _histories[user_id] = new_history[-40:]
        # Dosyaya сохранить
        _save_histories(_histories)
        return answer or 'Hmm, bir sorun oldu. Tekrar dener misin? '
    except Exception as e:
        log.info(f'[AI] Ошибка: {e}')
        return 'Сейчас не mogu cevapla, poprobuyte после. '


def _get_gojo_photo(answer: str, question: str) -> str:
    """Выбирает соответствующий VTuber-аватар Годжо без фона по теме сообщения в тикете"""
    text = (answer + " " + question).lower()
    if any(k in text for k in ["проверяю", "лог", "баз", "данные", "настройки", "сервер", "система", "контрол", "kontrol", "incele", "жалоб", "наруш", "оскорб"]):
        return "assets/ai_gojo/vtuber_investigating.png"
    elif any(k in text for k in ["решение", "готово", "исправлено", "сделано", "помочь", "помощ", "решен", "çözüm", "halled", "tamam", "успех"]):
        return "assets/ai_gojo/vtuber_solution.png"
    elif any(k in text for k in ["вердикт", "наказан", "апелляц", "забанен", "мьют", "мут", "штраф", "суд", "verdict"]):
        return "assets/ai_gojo/vtuber_verdict.png"
    else:
        return "assets/ai_gojo/vtuber_welcome.png"


class AIChat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name='ai-info-clear', description="Temizle veriбазу информация AI на сервер (Менеджер)")
    @commands.has_permissions(administrator=True)
    async def ai_clear_knowledge(self, ctx):
        """Сервер AI info базу clear (только adminler)"""
        guild_id = str(ctx.guild.id)
        if guild_id in _knowledge_base:
            del _knowledge_base[guild_id]
            _save_knowledge_base(_knowledge_base)
            await ctx.send(' База знаний сервера AI очищена!', ephemeral=True)
        else:
            await ctx.send('База знаний уже пуста. ', ephemeral=True)
    async def ai_reset(self, ctx):
        """Kendi AI sohbet историю sıfırla"""
        user_id = ctx.author.id
        if user_id in _histories:
            del _histories[user_id]
            _save_histories(_histories, force=True)
            await ctx.send(' История чата сброшена! Начинаем с чистого листа. ', ephemeral=True)
        else:
            await ctx.send('История чата уже пуста. ', ephemeral=True)

    @commands.hybrid_command(name='ai-sifirla', description="Sbrosit история AI cata")
    @commands.has_permissions(administrator=True)
    async def ai_add_knowledge(self, ctx, konu: str, *, info: str):
        """
        Bot'a постоянный info öğret.
        Использование: /ai-info-add armoon Armoon, Valorant ve CS2 oynayan Türk bir esporcu.
        """
        guild_key = str(ctx.guild.id)
        if guild_key not in _knowledge_base:
            _knowledge_base[guild_key] = []
        
        # Одинаковый konu var mı?
        for item in _knowledge_base[guild_key]:
            if item.get('name', '').lower() == konu.lower() or \
               item.get('topic', '').lower() == konu.lower():
                item['info'] = info
                item['confidence'] = 'high'
                item['source'] = 'manual'
                _save_knowledge_base(_knowledge_base)
                await ctx.send(f' Информация о **{konu}** обновлена!', ephemeral=True)
                return
        
        # Новый info add
        _knowledge_base[guild_key].append({
            'type': 'manual',
            'name': konu.lower(),
            'topic': konu.lower(),
            'info': info,
            'question': f'{konu} кто',
            'confidence': 'high',
            'source': 'manual'
        })
        _save_knowledge_base(_knowledge_base)
        await ctx.send(f' Информация о **{konu}** сохранена! Теперь я буду знать правильный ответ.', ephemeral=True)

    @commands.hybrid_command(name='ai-info-listele', description="Liste zaregistrirovannih AI информация (Менеджер)")
    @commands.has_permissions(administrator=True)
    async def ai_list_knowledge(self, ctx):
        """На сервер запись AI информация listele"""
        guild_key = str(ctx.guild.id)
        items = _knowledge_base.get(guild_key, [])
        
        if not items:
            await ctx.send('В базе знаний пока нет записей.', ephemeral=True)
            return
        
        lines = []
        for i, item in enumerate(items, 1):
            name = item.get('name') or item.get('topic', '?')
            src = ' Manuel' if item.get('source') == 'manual' else ' Web'
            conf = '' if item.get('confidence') == 'high' else ''
            lines.append(f'{conf} **{name}** ({src})')
        
        embed = discord.Embed(
            title=' AI Информация Tabanı',
            description='\n'.join(lines[:20]),
            color=0x00D9FF
        )
        await ctx.send(embed=embed, ephemeral=True)

    async def _handle_dm_send(self, text: str, message: discord.Message) -> str:
        """Belirli bir userya DM отправить — 'особый yaz', 'dm at' команды"""
        import re

        # Цель участника bul
        target_id = None
        mention_match = re.search(r'<@!?(\d+)>', text)
        if mention_match:
            target_id = int(mention_match.group(1))
        if not target_id:
            id_match = re.search(r'\b(\d{17,20})\b', text)
            if id_match:
                target_id = int(id_match.group(1))

        # "benimle одинаковый seste который является" → owner'ın ses channelındaki diğer участник
        cl = text.lower()
        if not target_id and any(t in cl for t in ['одинаковый seste', 'одинаковый seste', 'ses channelındaki', 'ses channelindaki',
                                                    'benimle который является', 'yanımdaki', 'yanimdaki']):
            for guild in self.bot.guilds:
                owner = guild.get_member(OWNER_ID)
                if not owner or not owner.voice:
                    continue
                # Одинаковый ses channelındaki bot olmayan diğer участники
                others = [m for m in owner.voice.channel.members
                          if m.id != OWNER_ID and not m.bot]
                if others:
                    target_id = others[0].id  # Первый kişiyi al
                    break

        if not target_id:
            return ' Кто DM atacağımı anlayamadım. ID, mention или "benimle одинаковый seste" de.'

        # Отправл сообщение удалить
        # "X'e особый şunu yaz: ..." или "X'e dm at как"
        dm_content = None
        # "yaz:" или "yaz " sonrasını al
        yaz_match = re.search(r'(?:yaz[:\s]+|at[:\s]+|отправить[:\s]+)(.+)', text, re.IGNORECASE)
        if yaz_match:
            dm_content = yaz_match.group(1).strip()
            # ID/mention'ı содержимое clear
            dm_content = re.sub(r'<@!?\d+>', '', dm_content).strip()
            dm_content = re.sub(r'\b\d{17,20}\b', '', dm_content).strip()

        # Hâlâ пусто — все trigger kelimeleri удалить, kalanı message say
        if not dm_content:
            clean = text
            for t in ['особый yaz', 'ozelden yaz', 'dm at', 'dm отправить', 'dm yaz',
                      'особый message at', 'ozel message at', 'особый message', 'ozelden message',
                      'benimle одинаковый seste', 'benimle одинаковый seste', 'одинаковый seste который является arkadaşa',
                      'одинаковый seste который является arkadasa']:
                clean = clean.replace(t, '').strip()
            clean = re.sub(r'<@!?\d+>', '', clean).strip()
            clean = re.sub(r'\b\d{17,20}\b', '', clean).strip()
            dm_content = clean or None

        if not dm_content:
            return ' Ne yazacağımı anlayamadım. "особый yaz: <message>" formatını использовать.'

        # Участника bul ve DM at
        for guild in self.bot.guilds:
            member = guild.get_member(target_id)
            if not member:
                continue
            try:
                await member.send(dm_content)
                return f' **{member.display_name}**\'e DM отправлено: *{dm_content[:100]}*'
            except discord.Forbidden:
                return f' **{member.display_name}** DM\'lere закрыт.'
            except Exception as e:
                return f' DM отправл: {e}'

        # Участник guild'de найден direkt fetch dene
        try:
            user = await self.bot.fetch_user(target_id)
            await user.send(dm_content)
            return f' **{user.name}**\'e DM отправлено: *{dm_content[:100]}*'
        except Exception as e:
            return f' Пользователь не найден или DM отправл: {e}'

    async def _handle_voice_move(self, text: str, message: discord.Message) -> str:
        """Ses канал movema — tek/çift adım, geri getir, channel имя desteği"""
        import re
        import asyncio

        # Normalize: ASCII русский karakter eşleştirmesi для hem orijinal hem normalize
        def norm(s):
            return (s.lower()
                    .replace('ü', 'u').replace('ş', 's').replace('ğ', 'g')
                    .replace('ı', 'i').replace('ö', 'o').replace('ç', 'c')
                    .replace('İ', 'i').replace('Ü', 'u').replace('Ş', 's'))

        cl = text.lower()
        cl_norm = norm(text)

        #  Цель участника bul 
        target_id = None
        mention_match = re.search(r'<@!?(\d+)>', text)
        if mention_match:
            target_id = int(mention_match.group(1))
        if not target_id:
            id_match = re.search(r'\b(\d{17,20})\b', text)
            if id_match:
                target_id = int(id_match.group(1))
        if not target_id and any(t in cl for t in ['beni', 'bana', 'benim']):
            target_id = OWNER_ID
        if not target_id:
            return ' Кто moveyacağımı anlayamadım. ID или mention ver.'

        #  "geri getir" / "geri al" talebi var mı? 
        geri_var = any(t in cl_norm for t in ['geri getir', 'geri al', 'geri don', 'geri götür', 'geri gotur'])

        #  Yön ve adım количество 
        yon = 0
        # Hem "верх/ust" hem "Вверх/Вверх" destadd
        yukari_words = ['верх', 'ust', 'Вверх', 'Вверх', 'yukar']
        asagi_words  = ['Низ', 'вниз', 'asagi', 'asag']

        sayi_match = re.search(r'(\d+)\s*(' +
            '|'.join(yukari_words + asagi_words) + r')', cl_norm)
        if sayi_match:
            yon = int(sayi_match.group(1))
            if any(w in sayi_match.group(2) for w in norm('|'.join(asagi_words)).split('|')):
                yon = -yon
        else:
            if any(w in cl_norm for w in yukari_words):
                yon = 1
            elif any(w in cl_norm for w in asagi_words):
                yon = -1

        #  "bu voice / bu channela geri getir" — hedef channel имя 
        # "geri getir bu voice" → "bu ses" = особый bir channel имя не, orijinal channel demek
        # Ama "X в канал geri getir" gibi bir channel имя geçiyorsa onu yakala
        hedef_channel_adi = None
        channel_adi_match = re.search(r'(?:geri getir|geri al|move|al)\s+(.+?)(?:\s+в канал?|voice?|$)', cl)
        if channel_adi_match:
            aday = channel_adi_match.group(1).strip()
            if aday not in ('bu', 'o', 'şu', 'su', 'bu ses', 'o ses'):
                hedef_channel_adi = aday

        results = []
        for guild in self.bot.guilds:
            member = guild.get_member(target_id)
            if not member:
                continue
            if not member.voice or not member.voice.channel:
                results.append(f' {member.display_name} şu an bir ses в канале не.')
                continue

            current_vc = member.voice.channel
            voice_channels = sorted(guild.voice_channels, key=lambda c: c.position)
            current_idx = next((i for i, c in enumerate(voice_channels) if c.id == current_vc.id), None)
            if current_idx is None:
                results.append(' Текущий channel listede не найдено.')
                continue

            #  Isimım 1: Taşı 
            hedef_vc = None
            if yon != 0:
                new_idx = max(0, min(len(voice_channels) - 1, current_idx - yon))
                hedef_vc = voice_channels[new_idx]
            elif hedef_channel_adi:
                for vc in voice_channels:
                    if norm(vc.name) in norm(hedef_channel_adi) or norm(hedef_channel_adi) in norm(vc.name):
                        hedef_vc = vc
                        break
            else:
                # Канал имя direkt geçiyor mu metinde?
                for vc in voice_channels:
                    if norm(vc.name) in cl_norm:
                        hedef_vc = vc
                        break

            if not hedef_vc or hedef_vc.id == current_vc.id:
                if hedef_vc and hedef_vc.id == current_vc.id:
                    results.append(f'ℹ Zaten o channelda: **{current_vc.name}**')
                else:
                    results.append(
                        f' Цель channel не найдено. Текущий: **{current_vc.name}**\n'
                        f'Ses channelları: {", ".join(vc.name for vc in voice_channels)}'
                    )
                continue

            try:
                await member.move_to(hedef_vc)
                msg = f' **{member.display_name}** → **{hedef_vc.name}** movendı.'

                #  Isimım 2: До getir 
                if geri_var:
                    # "bu voice geri getir" = orijinal channela (current_vc) geri al
                    geri_hedef = current_vc

                    # Если belirli bir channel имя varsa onu использовать
                    if hedef_channel_adi:
                        for vc in voice_channels:
                            if norm(vc.name) in norm(hedef_channel_adi) or norm(hedef_channel_adi) in norm(vc.name):
                                geri_hedef = vc
                                break

                    await asyncio.sleep(3)  # 3 секунд badd
                    # Участник hâlâ ses в канале mı контроль et
                    await member.guild.chunk()  # cache обновить
                    fresh = guild.get_member(target_id)
                    if fresh and fresh.voice:
                        await fresh.move_to(geri_hedef)
                        msg += f'\n 3 секунд после **{geri_hedef.name}** в канал geri getirildi.'
                    else:
                        msg += f'\n До getirilemedi — участник ses из канала ayrılmış.'

                results.append(msg)
            except discord.Forbidden:
                results.append(' Администратор yok (Move Members разрешение gerekli).')
            except Exception as e:
                results.append(f' Ошибка: {e}')

        return '\n'.join(results) if results else ' Участник bu сервер не найдено.'

    def _norm(self, s: str) -> str:
        return (s.lower()
                .replace('ü','u').replace('ş','s').replace('ğ','g')
                .replace('ı','i').replace('ö','o').replace('ç','c')
                .replace('İ','i').replace('Ü','u').replace('Ş','s'))

    def _extract_target(self, text: str):
        """Metinden hedef участник ID'sini удалить. (mention, raw ID, 'beni', isim)"""
        import re
        m = re.search(r'<@!?(\d+)>', text)
        if m: return int(m.group(1))
        m = re.search(r'\b(\d{17,20})\b', text)
        if m: return int(m.group(1))
        cl = text.lower()
        if any(t in cl for t in ['beni', 'bana', 'benim', 'ben ']):
            return OWNER_ID
        # Isim с ara — все сервер участник ara
        # Команда kelimelerini clear, kalan kısım isim может быть
        stop_words = ['sesten at', 'voice al', 'voice тянуть', 'ban at', 'kick at',
                      'timeout ver', 'uyar', 'роли ver', 'роли al', 'bu arkadasi',
                      'bu arkadasin', 'bu kisiyi', 'bu участника', 'bu uyeyi',
                      'arkadasi', 'arkadasini', 'kisiyi', 'участника', 'uyeyi',
                      'bunu', 'bunu', 'onu', 'şunu', 'sunu']
        clean = cl
        for sw in stop_words:
            clean = clean.replace(sw, ' ')
        clean = re.sub(r'\s+', ' ', clean).strip()
        if len(clean) >= 2:
            for guild in self.bot.guilds:
                for member in guild.members:
                    if member.bot:
                        continue
                    name = member.display_name.lower()
                    username = member.name.lower()
                    if clean in name or clean in username or name in clean or username in clean:
                        return member.id
        return None

    def _extract_duration_minutes(self, text: str) -> int:
        """Metinden длительность minutes cinsinden удалить."""
        import re
        cl = text.lower()
        m = re.search(r'(\d+)\s*(часов|hour)', cl)
        if m: return int(m.group(1)) * 60
        m = re.search(r'(\d+)\s*(день|gun|day)', cl)
        if m: return int(m.group(1)) * 1440
        m = re.search(r'(\d+)\s*(hafta|week)', cl)
        if m: return int(m.group(1)) * 10080
        m = re.search(r'(\d+)\s*(minutes|dk|min)', cl)
        if m: return int(m.group(1))
        return 10  # varчислоlan

    async def _detect_owner_intent(self, text: str, message: discord.Message) -> bool:
        """Owner DM команды — anahtar kelime основанный на, неверно yazsan da çalışır"""
        import re
        cl = text.lower()
        cn = self._norm(text)

        #  MÜZİK 
        # Ses в канал gir (музыкаsiz)
        ses_gir_triggers = ['voice gir', 'voice katıl', 'voice gel', 'channela gir', 'benim voice gir',
                            'voice gir', 'ses в канал gir', 'ses в канал gir', 'yanima gel']
        if any(t in cn for t in [self._norm(x) for x in ses_gir_triggers]):
            result_msg = ' Ses в канале değilsin.'
            for guild in self.bot.guilds:
                member = guild.get_member(OWNER_ID)
                if not member or not member.voice:
                    continue
                try:
                    vc = guild.voice_client
                    if not vc:
                        vc = await member.voice.channel.connect()
                    else:
                        await vc.move_to(member.voice.channel)
                    result_msg = f' **{member.voice.channel.name}** в канал girdim.'
                    break
                except Exception as e:
                    result_msg = f' Ошибка: {e}'
            await message.channel.send(result_msg)
            return True

        # Ses из канала çık
        ses_cik_triggers = ['sesten çık', 'sesten cik', 'channeldan çık', 'channeldan cik',
                            'çık sesten', 'cik sesten', 'botu удалить', 'botu cikar']
        if any(t in cn for t in [self._norm(x) for x in ses_cik_triggers]):
            result_msg = ' Zaten ses в канале değilim.'
            for guild in self.bot.guilds:
                vc = guild.voice_client
                if vc:
                    await vc.disconnect()
                    result_msg = ' Ses из канала вышел.'
                    break
            await message.channel.send(result_msg)
            return True

        muzik_triggers = ['çal', 'cal', 'музыка', 'muzik', 'песня', 'sarki', 'oynat']
        if any(t in cl for t in muzik_triggers):
            query = text
            for t in ['çal', 'cal', 'музыка çal', 'muzik cal', 'песня çal', 'sarki cal', 'oynat', 'bana']:
                query = query.replace(t, '').strip()
            query = query.strip() or 'lofi'
            result_msg = ' Ses в канале değilsin.'
            for guild in self.bot.guilds:
                member = guild.get_member(OWNER_ID)
                if not member or not member.voice:
                    continue
                voice_channel = member.voice.channel
                text_channel = guild.text_channels[0] if guild.text_channels else None
                try:
                    from cogs.music import fetch_source, get_queue, play_next
                    vc = guild.voice_client
                    if vc and not vc.is_connected():
                        vc = None  # Kapanmakta который является ссылка clear
                    if not vc:
                        vc = await voice_channel.connect()
                    elif vc.channel != voice_channel:
                        await vc.move_to(voice_channel)
                    stream_url, title, webpage_url = await fetch_source(query)
                    item = {'stream_url': stream_url, 'title': title,
                            'webpage_url': webpage_url, 'requester': 'Arthur (DM)'}
                    q = get_queue(guild.id)
                    if vc.is_playing() or vc.is_paused():
                        q.append(item)
                        result_msg = f' Kuyruğa addndi: **{title}**'
                    else:
                        q.insert(0, item)
                        await play_next(guild, text_channel)
                        result_msg = f' Çalınıyor: **{title}**'
                    break
                except Exception as e:
                    result_msg = f' Müzik Ошибки: {e}'
            await message.channel.send(result_msg)
            return True

        # AFK удалить — до контроль et (закрыть/удалить varsa AFK açma)
        afk_kapat_triggers = ['döndüm', 'geldim', 'uyandım', 'afk удалить', 'afk закрыть',
                              'afk удалить', 'afk закрыть', 'afk modunu закрыть', 'afk modu закрыть',
                              'afk bitir', 'afk удалить', 'afk отмена']
        if any(t in cl for t in afk_kapat_triggers):
            afk_cog = self.bot.get_cog('AFK')
            for guild in self.bot.guilds:
                member = guild.get_member(OWNER_ID)
                if not member:
                    continue
                if afk_cog:
                    afk_cog._remove(guild.id, OWNER_ID)
                try:
                    nick = member.display_name
                    if nick.startswith(' '):
                        await member.edit(nick=nick[2:].strip() or None)
                except Exception:
                    pass
            from cogs.afk import _pending_mentions
            pending = _pending_mentions.pop(OWNER_ID, [])
            if pending:
                lines = [f"• **{p['from']}**: {p['msg'][:60]}" for p in pending[-5:]]
                await message.channel.send(f' Добро пожаловать geldin! {len(pending)} человек etiketledi:\n' + '\n'.join(lines))
            else:
                await message.channel.send(' AFK modu закрыто.')
            return True

        # AFK aç — "закрыть" или "удалить" geçiyorsa tetikleme
        afk_ac_triggers = ['afk', 'uykum var', 'uyuyacağım', 'gidiyorum', 'yokum']
        afk_engel = ['закрыть', 'удалить', 'удалить', 'bitir', 'удалить', 'отмена', 'modunu', 'modu']
        if any(t in cl for t in afk_ac_triggers) and not any(e in cl for e in afk_engel):
            reason = text
            for t in ['afk at', 'afk ol', 'afk yap', 'afk', 'beni']:
                reason = reason.replace(t, '').strip()
            reason = reason or 'AFK'
            afk_cog = self.bot.get_cog('AFK')
            for guild in self.bot.guilds:
                member = guild.get_member(OWNER_ID)
                if not member:
                    continue
                if afk_cog:
                    afk_cog._set(guild.id, OWNER_ID, reason, owner_mode=True)
                try:
                    nick = member.display_name
                    if not nick.startswith(''):
                        await member.edit(nick=f' {nick[:28]}')
                except Exception:
                    pass
            await message.channel.send(f' AFK modu активен! Причина: **{reason}**')
            return True

        # Ses канал movema
        ses_tasi_triggers = [
            'ses в канал', 'voice move', 'voice тянуть', 'voice al',
            'верх channela', 'ust channela', 'Низ channela',
            'channela move', 'channela тянуть', 'channela al', 'voice',
            'верх channel', 'ust channel', 'Вверх channel', 'Вверх channel',
            'в канал al', 'в канал al', 'move voice', 'тянуть voice', 'al voice',
        ]
        # Sesten at — ayrı handler
        sesten_at_triggers = ['sesten at', 'sesten удалить', 'sesten cikar', 'ses из канала at',
                              'ses из канала удалить', 'ses из канала at', 'sesten kick']
        if any(t in cn for t in [self._norm(x) for x in sesten_at_triggers]):
            target_id = self._extract_target(text)
            if not target_id:
                await message.channel.send(' Не удалось определить пользователя для исключения.')
                return True
            results = []
            for guild in self.bot.guilds:
                member = guild.get_member(target_id)
                if not member:
                    continue
                if not member.voice:
                    results.append(f' **{member.display_name}** zaten seste не.')
                    continue
                try:
                    await member.move_to(None)
                    results.append(f' **{member.display_name}** sesten atıldı.')
                except discord.Forbidden:
                    results.append(' Администратор yok.')
                except Exception as e:
                    results.append(f' Ошибка: {e}')
            await message.channel.send('\n'.join(results) if results else ' Участник не найдено.')
            return True

        if any(t in cl for t in ses_tasi_triggers):
            result_msg = await self._handle_voice_move(text, message)
            await message.channel.send(result_msg)
            return True

        # DM / особый message
        dm_triggers = ['особый yaz', 'ozelden yaz', 'dm at', 'dm отправить', 'dm yaz',
                       'особый message at', 'ozel message at', 'особый message', 'ozelden message']
        if any(t in cl for t in dm_triggers):
            result_msg = await self._handle_dm_send(text, message)
            await message.channel.send(result_msg)
            return True

        #  ЗАДАЧА ZİNCİRİ 
        # "X kişiyi izle, мат ederse ban at" gibi условный задачи
        gorev_add = ['задача add', 'gorevi add', 'izle ve', 'takip et', 'задача kur', 'gorev kur',
                      'ederse ban', 'ederse kick', 'ederse timeout', 'yaparsa ban', 'yaparsa kick']
        if any(t in cn for t in [self._norm(x) for x in gorev_add]):
            target_id = self._extract_target(text)
            desc = text.strip()
            task = {'id': len(_active_tasks) + 1, 'desc': desc,
                    'target_id': target_id, 'created': str(datetime.datetime.now())}
            _active_tasks.append(task)
            _save_tasks(_active_tasks)
            await message.channel.send(
                f' Задача сохранено (#{task["id"]}): *{desc[:100]}*\n'
                f'`задача показать` с listeleyebilirsin.'
            )
            return True

        gorev_listele = ['задача показать', 'gorevi goster', 'активен задачи', 'активен gorevler',
                         'задача список', 'gorev список']
        if any(t in cn for t in [self._norm(x) for x in gorev_listele]):
            if not _active_tasks:
                await message.channel.send(' Активен задача yok.')
            else:
                lines = [f'**#{t["id"]}** — {t["desc"][:80]}' for t in _active_tasks]
                await message.channel.send(' **Активен Задачи:**\n' + '\n'.join(lines))
            return True

        gorev_sil = ['задача удалить', 'gorevi удалить', 'задача удалить', 'gorevi удалить', 'задача отмена']
        if any(t in cn for t in [self._norm(x) for x in gorev_sil]):
            import re as _re
            num = _re.search(r'\d+', text)
            if num:
                tid = int(num.group())
                before = len(_active_tasks)
                _active_tasks[:] = [t for t in _active_tasks if t['id'] != tid]
                _save_tasks(_active_tasks)
                if len(_active_tasks) < before:
                    await message.channel.send(f' Задача #{tid} удалено.')
                else:
                    await message.channel.send(f' Задача #{tid} не найдена.')
            else:
                await message.channel.send(' Какой задача удалить желание belirt: `задача удалить 1`')
            return True

        #  СЕРВЕР СОСТОЯНИЕ SORGULAMA 
        status_triggers = ['на сервере кто var', 'кто online', 'кто seste', 'сколько человек online',
                          'сервер statusu', 'neler oluyor', 'ne var ne yok на сервере',
                          'кто активен', 'seste кто var', 'online кто var']
        if any(t in cn for t in [self._norm(x) for x in status_triggers]):
            lines = []
            for guild in self.bot.guilds:
                import discord as _discord
                online = [m for m in guild.members
                          if not m.bot and m.status != _discord.Status.offline]
                in_voice = []
                for vc in guild.voice_channels:
                    members = [m.display_name for m in vc.members if not m.bot]
                    if members:
                        in_voice.append(f'**{vc.name}**: {", ".join(members)}')
                lines.append(f'**{guild.name}**')
                lines.append(f'• Online: {len(online)} человек')
                if in_voice:
                    lines.append('• Ses channelları:\n  ' + '\n  '.join(in_voice))
                else:
                    lines.append('• Ses channellarında кто yok')
                ticket_chs = [c for c in guild.text_channels if c.name.startswith('ticket-')]
                if ticket_chs:
                    lines.append(f'• Открыт ticket: {len(ticket_chs)}')
            await message.channel.send('\n'.join(lines) or ' Не удалось получить информацию о сервере.')
            return True

        # Mod уведомление aç/закрыть
        mod_notify_ac = ['mod уведомление aç', 'mod уведомление ac', 'наказание уведомление aç', 'наказание уведомление ac',
                         'mod notify aç', 'mod notify ac', 'уведомление aç', 'уведомление ac']
        mod_notify_kapat = ['mod уведомление закрыть', 'наказание уведомление закрыть', 'mod notify закрыть', 'уведомление закрыть']
        if any(t in cn for t in [self._norm(x) for x in mod_notify_ac]):
            import json as _j
            os.makedirs('data', exist_ok=True)
            with open('data/mod_notify.json', 'w', encoding='utf-8') as f:
                _j.dump({'enabled': True}, f)
            await message.channel.send(' Уведомления модератора включены. Вы будете получать ЛС о действиях.n.')
            return True
        if any(t in cn for t in [self._norm(x) for x in mod_notify_kapat]):
            import json as _j
            os.makedirs('data', exist_ok=True)
            with open('data/mod_notify.json', 'w', encoding='utf-8') as f:
                _j.dump({'enabled': False}, f)
            await message.channel.send(' Mod уведомление закрыто.')
            return True

        # Hiçbir handler eşleşmedi — normal sohbete düş
        return False

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        is_dm = isinstance(message.channel, discord.DMChannel)

        #  Owner'ın DM cevabını yakala 
        if is_dm and OWNER_ID and message.author.id == OWNER_ID:
            # Owner bir messagea reply attıysa, o message baddyen soru mu?
            if message.reference and message.reference.message_id in _pending_questions:
                ref_id = message.reference.message_id
                pending = _pending_questions.pop(ref_id)
                user_id = pending['user_id']
                channel_id = pending['channel_id']
                question = pending['question']
                answer = message.content.strip()

                # Cevabı knowledge base'e сохранить
                if pending.get('guild_id'):
                    guild_key = str(pending['guild_id'])
                    if guild_key not in _knowledge_base:
                        _knowledge_base[guild_key] = []
                    _knowledge_base[guild_key].append({
                        'type': 'owner_answer',
                        'question': question,
                        'info': answer,
                        'confidence': 'high',
                        'source': 'owner'
                    })
                    _save_knowledge_base(_knowledge_base)

                # Пользователю cevabı ilet
                try:
                    if pending.get('is_dm'):
                        user = await self.bot.fetch_user(user_id)
                        await user.send(answer)
                    else:
                        channel = self.bot.get_channel(channel_id)
                        if channel:
                            user = channel.guild.get_member(user_id)
                            mention = user.mention if user else f'<@{user_id}>'
                            await channel.send(f'{mention} {answer}')
                    await message.add_reaction('')
                except Exception as e:
                    await message.channel.send(f' Не удалось доставить: {e}')
                return

            #  Owner'ın akıllı eylem система (AI intent detection) 
            content_lower = message.content.lower().strip()
            content_raw = message.content.strip()

            # Tercih/правило сохран — "bunu bana yazma", "bunu каждый vakit yap" vb.
            pref_triggers = ['bunu bana yazma', 'bunu сказатьme', 'bunu yapma',
                             'каждый vakit yap', 'каждый vakit сказать', 'hatırla',
                             'unutma', 'bunu bil', 'теперь biliyorsun']
            if any(t in content_lower for t in pref_triggers):
                _owner_prefs['rules'].append(content_raw)
                if len(_owner_prefs['rules']) > 50:
                    _owner_prefs['rules'] = _owner_prefs['rules'][-50:]
                _save_owner_prefs(_owner_prefs)
                await message.channel.send(f' Сохранитьtim: **{content_raw[:100]}**')
                return

            # AI с intent определить
            intent = await self._detect_owner_intent(content_raw, message)
            if intent:
                return  # Intent işlendi, normal AI akışına geçme

        is_ticket_channel = getattr(message.channel, 'name', '').lower().startswith(('ticket-', 'тикет-', 'destek-', 'tk-', 'closed-'))
        is_ai_channel = (
            message.channel.id in AI_CHANNELS or
            message.channel.id in _dynamic_channels or
            is_ticket_channel
        )

        if not (is_dm or is_ai_channel):
            return

        if is_ai_channel and not is_dm:
            is_allowed_ai = (
                message.channel.id in _dynamic_channels or
                is_ticket_channel
            )
            if not is_allowed_ai:
                return
            content = re.sub(r'^moe\s*', '', message.content, flags=re.IGNORECASE).strip()
            for m in message.mentions:
                content = content.replace(f'<@{m.id}>', '').replace(f'<@!{m.id}>', '')
            content = content.strip() or 'Здравствуйте!'
        else:
            content = message.content.strip() or 'Здравствуйте!'

        # Arthur'un команда talebi — J.A.R.V.I.S. modu
        if OWNER_ID and message.author.id == OWNER_ID:
            cmd_triggers = ['channel aç', 'channel создать', 'message at', 'announce yap',
                           'ban at', 'kick at', 'timeout ver', 'роли ver', 'роли al']
            if any(t in content.lower() for t in cmd_triggers):
                context['jarvis_mode'] = True
                context['available_commands'] = (
                    'Использовать команды:\n'
                    '/moderate ban @user причина\n'
                    '/moderate kick @user причина\n'
                    '/moderate timeout @user minutes причина\n'
                    '/роли @user @роли\n'
                    '/utility clear adet\n'
                    '/utility lock\n'
                    '/utility unlock\n'
                    'Канал создан для: Discord\'da Сервер Настройкиı → Каналы'
                )

        async with message.channel.typing():
            recent_msgs = []
            channel_ctx = []
            
            if not is_dm and message.guild:
                recent_msgs = await _get_recent_user_messages(
                    message.author.id, message.guild, limit=15
                )
                channel_ctx = await _get_channel_context(message.channel, limit=12)
            
            answer = await self.bot.loop.run_in_executor(
                None, _call_ai, content, message.author.id,
                message.guild if not is_dm else None,
                recent_msgs, channel_ctx
            )

        if _kufur_var_mi(answer):
            answer = "Bunu сказатьyemem. "

        # Ответ "bilmiyorum" содержимое owner'a sor
        bilmiyorum_triggers = ['bilmiyorum', 'emin değilim', 'info bulamadım', 'о infom yok']
        if OWNER_ID and any(t in answer.lower() for t in bilmiyorum_triggers):
            try:
                owner = await self.bot.fetch_user(OWNER_ID)
                guild_id = message.guild.id if message.guild else 0
                user_name = message.author.display_name
                embed = discord.Embed(
                    title=' Вопрос, на который я не нашел ответ',
                    color=0xf59e0b,
                    description=f'**Спросил:** {user_name} (`{message.author.id}`)\n'
                                f'**Вопрос:** {content}\n\n'
                                f'**Ответlamak для bu messagea reply at.**'
                )
                embed.set_footer(text=f'Сервер: {message.guild.name if message.guild else "DM"}')
                dm_msg = await owner.send(embed=embed)
                _pending_questions[dm_msg.id] = {
                    'user_id': message.author.id,
                    'channel_id': message.channel.id,
                    'question': content,
                    'guild_id': guild_id,
                    'is_dm': is_dm
                }
            except Exception as e:
                log.info(f'[AI] Owner DM Ошибки: {e}')

        if is_dm:
            # DM log'a сохранить
            try:
                import json as _j, os as _os, datetime as _dt3
                _os.makedirs('data', exist_ok=True)
                _f = 'data/dm_log.json'
                _d = _j.load(open(_f, encoding='utf-8')) if _os.path.exists(_f) else {}
                uid = str(message.author.id)
                if uid not in _d: _d[uid] = []
                # Gelen сообщение сохранить
                _d[uid].append({
                    'author': message.author.display_name,
                    'content': message.content,
                    'timestamp': _dt3.datetime.utcnow().isoformat(),
                    'from_bot': False,
                })
                # Bot cevabını сохранить
                _d[uid].append({
                    'author': 'Aether',
                    'content': answer,
                    'timestamp': _dt3.datetime.utcnow().isoformat(),
                    'from_bot': True,
                })
                # Max 200 message tut
                _d[uid] = _d[uid][-200:]
                with open(_f, 'w', encoding='utf-8') as fp:
                    _j.dump(_d, fp, ensure_ascii=False, indent=2)
            except Exception as _le:
                log.info(f'[DM LOG] Ошибка: {_le}')
            await message.channel.send(answer)
        else:
            is_ticket_ch = getattr(message.channel, 'name', '').lower().startswith(('ticket-', 'тикет-', 'destek-', 'tk-', 'closed-'))
            if is_ticket_ch:
                try:
                    from cogs._ai_card import generate_ai_dialogue_bytes
                    state_mode = "welcome"
                    text_lower = (answer + " " + content).lower()
                    if any(k in text_lower for k in ["проверяю", "лог", "баз", "данные", "настройки", "сервер", "система", "контрол", "ncele", "жалоб", "наруш", "оскорб"]):
                        state_mode = "investigate"
                    elif any(k in text_lower for k in ["вердикт", "наказан", "апелляц", "забанен", "мьют", "мут", "штраф", "суд", "verdict"]):
                        state_mode = "verdict"
                    elif any(k in text_lower for k in ["решение", "готово", "исправлено", "сделано", "помочь", "помощ", "решен", "çözüm", "halled", "tamam", "успех"]):
                        state_mode = "solution"

                    img_buf = await self.bot.loop.run_in_executor(
                        None, generate_ai_dialogue_bytes, answer[:650], content, state_mode
                    )
                    file = discord.File(img_buf, filename="gojo_dialogue.png")
                    await message.reply(file=file, mention_author=False)
                except Exception as e:
                    log.error(f"[AI Ticket Dialogue Card Error]: {e}")
                    await message.reply(answer, mention_author=False)
            else:
                await message.reply(answer, mention_author=False)


async def setup(bot):
    cog = AIChat(bot)
    await bot.add_cog(cog)
    
    # Bot kapanırken history'yi сохранить
    @bot.event
    async def on_shutdown():
        _save_histories(_histories, force=True)
        log.info('[AI] Разговор история сохранено.')
