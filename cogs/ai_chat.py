"""AI Chat Cog — DM + channel sohbet"""
import discord
from discord.ext import commands
import re
import json
import os
import datetime

AI_CHANNELS = set()  # Boş — dinamik olarak addnir
# Dinamik channellar — DM'den addnip çıkarılabilir
_dynamic_channels: set = set()  # DM'den /ai-channel командаuyla addnir

# ── AKTİF GÖREVLER (koşullu görev zinciri) ──────────────────────────────────
_active_tasks: list = []  # [{'id': int, 'desc': str, 'condition': str, 'action': str, 'target_id': int}]
_task_counter: int = 0

def _load_tasks() -> list:
    f = 'data/jarvis_tasks.json'
    if os.path.exists(f):
        try:
            with open(f, 'r', encoding='utf-8') as fp:
                return json.load(fp)
        except:
            pass
    return []

def _save_tasks(tasks: list):
    os.makedirs('data', exist_ok=True)
    with open('data/jarvis_tasks.json', 'w', encoding='utf-8') as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)

_active_tasks = _load_tasks()

# Owner ID — bilmediği soruları buraya iletir
OWNER_ID = int(os.getenv('OWNER_ID') or '0')

# Baddyen sorular — owner cevap verince userya iletilir
# {owner_dm_message_id: {'user_id': int, 'channel_id': int, 'question': str, 'is_dm': bool}}
_pending_questions: dict = {}

# Küfür filtresi — tam kelime eşleşmesi
KUFUR_LISTESI = ['amk', 'amq', 'orospu', 'sik', 'göt', 'got', 'piç', 'pic',
                 'yarrak', 'yarak', 'siktir', 'bok', 'kahpe', 'ibne', 'amcık', 'amcik']

def _kufur_var_mi(text: str) -> bool:
    t = text.lower()
    # Tam kelime eşleşmesi için boşluk/noktalama ile çevrili olmalı
    import re
    for k in KUFUR_LISTESI:
        if re.search(r'\b' + re.escape(k) + r'\b', t):
            return True
    return False

# Пользователь bazlı konuşma geçmişi — kalıcı depolama
HISTORY_FILE = 'data/ai_chat_histories.json'
KNOWLEDGE_FILE = 'data/ai_knowledge_base.json'
INSTRUCTIONS_FILE = 'data/ai_instructions.json'
PROFILES_FILE = 'data/ai_user_profiles.json'  # Пользователь kişilik profilleri
OWNER_PREFS_FILE = 'data/owner_preferences.json'  # Arthur'un kalıcı tercihleri
_save_counter = 0


def _load_owner_prefs() -> dict:
    if os.path.exists(OWNER_PREFS_FILE):
        try:
            with open(OWNER_PREFS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
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
        except:
            pass
    return {}


def _save_profiles(profiles: dict):
    try:
        os.makedirs('data', exist_ok=True)
        with open(PROFILES_FILE, 'w', encoding='utf-8') as f:
            json.dump(profiles, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f'[AI] Profil сохранитьme Ошибкаsı: {e}')


def _update_profile(user_id: int, question: str, answer: str, profiles: dict):
    """Konuşmadan user profilini güncelle"""
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

    # İlgi alanı tespiti
    interest_keywords = {
        'müzik': ['müzik', 'şarkı', 'albüm', 'sanatçı', 'rap', 'pop', 'rock'],
        'oyun': ['oyun', 'game', 'lol', 'valorant', 'minecraft', 'cs2'],
        'anime': ['anime', 'manga', 'naruto', 'attack on titan', 'one piece'],
        'spor': ['futbol', 'basketbol', 'maç', 'gol', 'takım'],
        'teknoloji': ['kod', 'python', 'infosayar', 'yazılım', 'ai'],
    }
    q_lower = question.lower()
    for interest, keywords in interest_keywords.items():
        if any(kw in q_lower for kw in keywords):
            if interest not in p['interests']:
                p['interests'].append(interest)
            p['topics'][interest] = p['topics'].get(interest, 0) + 1

    # Konuşma tarzı tespiti
    if len(question) < 10:
        p['style'] = 'kısa'
    elif '?' in question and len(question) > 50:
        p['style'] = 'meraklı'


_profiles = _load_profiles()

def _load_histories() -> dict:
    """Konuşma geçmişlerini dosyadan загрузить"""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # String key'leri int'e çevir
                return {int(k): v for k, v in data.items()}
        except Exception as e:
            print(f'[AI] History загрузитьme Ошибкаsı: {e}')
    return {}

def _load_knowledge_base() -> dict:
    """Сервер bazlı info tabanını загрузить"""
    if os.path.exists(KNOWLEDGE_FILE):
        try:
            with open(KNOWLEDGE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f'[AI] Knowledge base загрузитьme Ошибкаsı: {e}')
    return {}

def _load_instructions() -> dict:
    """Сервер bazlı kalıcı talimatları загрузить"""
    if os.path.exists(INSTRUCTIONS_FILE):
        try:
            with open(INSTRUCTIONS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f'[AI] Instructions загрузитьme Ошибкаsı: {e}')
    return {}

def _save_instructions(instructions: dict):
    """Kalıcı talimatları сохранить"""
    try:
        os.makedirs('data', exist_ok=True)
        with open(INSTRUCTIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(instructions, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f'[AI] Instructions сохранитьme Ошибкаsı: {e}')

def _detect_instruction(message: str, answer: str) -> dict:
    """
    Пользователя бот'a verdiği kalıcı talimatları tespit et.
    Örn: "bu soruyu kim sorarsa X cevabını ver"
    """
    m = message.lower().strip()
    
    # Talimat kalıpları
    patterns = [
        # "bu soruyu kim yazarsa yazsın X cevabını ver"
        r'bu soruyu kim (yazarsa yazsın|sorarsa sorsun|sorsa)',
        # "herkese X de / söyle"
        r'herkese .{3,50} (de|söyle|cevap ver)',
        # "bundan sonra X dersen Y de"
        r'bundan sonra .{3,50} (dersen|sorarsa)',
        # "X sorusuna Y cevabını ver"
        r'.{3,30} sorusuna .{3,50} (cevabını ver|de|söyle)',
    ]
    
    import re
    for pattern in patterns:
        if re.search(pattern, m):
            return {
                'trigger': message,   # Tetikleyici message
                'response': answer,   # Бота vereceği cevap (önceki cevap)
                'instruction': message
            }
    return None

def _save_histories(histories: dict, force: bool = False):
    """Konuşma geçmişlerini dosyaya сохранить (batch mode)"""
    global _save_counter
    _save_counter += 1
    # Her 5 messageda bir veya force=True ise сохранить
    if not force and _save_counter % 5 != 0:
        return
    try:
        os.makedirs('data', exist_ok=True)
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(histories, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f'[AI] History сохранитьme Ошибкаsı: {e}')

def _save_knowledge_base(knowledge: dict):
    """Информация tabanını сохранить"""
    try:
        os.makedirs('data', exist_ok=True)
        with open(KNOWLEDGE_FILE, 'w', encoding='utf-8') as f:
            json.dump(knowledge, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f'[AI] Knowledge base сохранитьme Ошибкаsı: {e}')

def _extract_learned_info(question: str, answer: str) -> dict:
    """Soru-cevaptan öğrenilebilir infoyi çıkar"""
    q = question.lower().strip()
    
    # Web araması yapıldıysa güvenilirlik düşük
    is_web_search = '🔍 Web araması yapıldı' in answer
    confidence = 'low' if is_web_search else 'high'
    
    # "X kimdir" soruları
    if 'кто такой' in q or 'кто это' in q or 'кто он' in q:
        # Sorudan ismi çıkar
        name_patterns = [
            r'(\w+(?:\s+\w+)*)\s+kimdir',
            r'kim\s+bu\s+(\w+(?:\s+\w+)*)',
            r'kim\s+o\s+(\w+(?:\s+\w+)*)'
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
    
    # "X nedir" soruları
    if 'что такое' in q or 'ne bu' in q:
        # Sorudan konuyu çıkar
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

# Сообщение cache — her user için 5 minutesda bir güncelle
_message_cache = {}
_cache_timeout = 300  # 5 minutes


async def _get_recent_user_messages(user_id: int, guild, limit: int = 15) -> list:
    """Пользователя son Discord messagelarını topla (son 12 час, max 15 message)"""
    if not guild:
        return []
    
    import datetime
    import time
    
    # Cache kontroleü
    cache_key = f"{guild.id}_{user_id}"
    now = time.time()
    if cache_key in _message_cache:
        cached_data, cached_time = _message_cache[cache_key]
        if now - cached_time < _cache_timeout:
            return cached_data
    
    recent = []
    cutoff_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=12)
    
    try:
        # Sadece активна channelları tara (son 2 часte message olan)
        active_channels = []
        for channel in guild.text_channels:
            if not channel.permissions_for(guild.me).read_message_history:
                continue
            try:
                # Последний messageı kontrole et
                last_msg = await channel.history(limit=1).flatten()
                if last_msg and (datetime.datetime.now(datetime.timezone.utc) - last_msg[0].created_at).seconds < 7200:
                    active_channels.append(channel)
            except:
                continue
        
        # Активен channelları tara — 15 message bulun ca dur
        for channel in active_channels[:15]:  # Max 15 channel
            try:
                async for msg in channel.history(limit=30, after=cutoff_time):
                    if msg.author.id == user_id and not msg.content.startswith('moe'):
                        # Бот командаlarını dahil etme
                        recent.append({
                            'channel': channel.name,
                            'content': msg.content[:200],  # 150 → 200 karakter
                            'timestamp': msg.created_at.strftime('%H:%M')
                        })
                        if len(recent) >= limit:  # 15 message bulun ca dur
                            break
            except:
                continue
            
            if len(recent) >= limit:
                break
        
        # Времяa göre sırala (en yeni en sonda)
        recent.sort(key=lambda x: x['timestamp'])
        result = recent[-limit:]  # Последний 15 message
        
        # Cache'e сохранить
        _message_cache[cache_key] = (result, now)
        return result
    except Exception as e:
        print(f'[AI] Сообщение всегоa Ошибкаsı: {e}')
        return []


async def _get_channel_context(channel, limit: int = 12) -> list:
    """Mevcut channelın son messagelarını topla (sohbet bağlamı için)"""
    try:
        context_messages = []
        async for msg in channel.history(limit=limit):
            if msg.author.bot:
                continue  # Бот messagelarını dahil etme
            context_messages.append({
                'author': msg.author.display_name,
                'content': msg.content[:200],  # 150 → 200 karakter
                'timestamp': msg.created_at.strftime('%H:%M')
            })
        # Ters çevir (en eski en başta)
        context_messages.reverse()
        return context_messages
    except Exception as e:
        print(f'[AI] Канал context Ошибкаsı: {e}')
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
        
        # Сервер sahibi ve right_btn roleleri infosi
        if guild:
            try:
                owner = guild.owner
                if owner:
                    context['guild_owner'] = owner.display_name

                # Правоli roleleri — manage_messages veya kick izni olanlar
                staff_roles = []
                for role in guild.roles:
                    if role.is_default():
                        continue
                    if role.permissions.manage_messages or role.permissions.kick_members or role.permissions.administrator:
                        members = [m.display_name for m in role.members if not m.bot][:5]
                        if members:
                            staff_roles.append({'name': role.name, 'members': members})
                if staff_roles:
                    context['staff_roles'] = staff_roles[:8]  # Max 8 role
            except Exception as e:
                print(f'[AI] Guild info Ошибкаsı: {e}')

        # ── SUNUCU DURUMU (J.A.R.V.I.S. farkındalığı) ──────────────────────
        if guild and str(user_id) == '987430047889637426':
            try:
                online = [m for m in guild.members if not m.bot and m.status != discord.Status.offline]
                in_voice = []
                for vc in guild.voice_channels:
                    for m in vc.members:
                        if not m.bot:
                            in_voice.append(m.display_name)
                # Последний katılanlar (son 24 час)
                import datetime as _dt
                cutoff = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=24)
                recent_joins = [m.display_name for m in guild.members
                                if not m.bot and m.joined_at and m.joined_at > cutoff]
                # Открыт ticket channelları
                ticket_channels = [c for c in guild.text_channels if c.name.startswith('ticket-')]
                context['server_status'] = {
                    'online_count': len(online),
                    'voice_count': len(in_voice),
                    'voice_members': in_voice[:5],
                    'recent_joins': recent_joins[:5],
                    'active_tickets': len(ticket_channels),
                    'total_members': guild.member_count,
                }
            except Exception as e:
                print(f'[AI] Server status Ошибкаsı: {e}')

        # ── AKTİF GÖREVLER ──────────────────────────────────────────────────
        if str(user_id) == '987430047889637426':
            try:
                from cogs.ai_chat import _active_tasks
                if _active_tasks:
                    context['active_tasks'] = [t['desc'] for t in _active_tasks[:5]]
            except:
                pass
        
        # Пользователя son Discord messagelarını context'e add (sadece serverda)
        if recent_messages:
            context['recent_user_messages'] = recent_messages
        
        # Канал bağlamını add (sadece serverda)
        if channel_context:
            context['channel_context'] = channel_context
        
        # Сервер info tabanından ilgili bilgileri add
        if guild_id and str(guild_id) in _knowledge_base:
            guild_knowledge = _knowledge_base[str(guild_id)]
            relevant_knowledge = []
            q_lower = question.lower()
            
            for item in guild_knowledge:
                # Düşük güvenilirlik bilgileri atla (web araması)
                if item.get('confidence') == 'low':
                    continue
                    
                # Soru benzerliği kontrole et
                if any(word in item.get('question', '').lower() for word in q_lower.split() if len(word) > 2):
                    relevant_knowledge.append(f"Önceden öğrenilen: {item.get('question', '')} → {item.get('info', '')}")
                # Имя/konu benzerliği kontrole et
                elif 'name' in item and any(word in item['name'].lower() for word in q_lower.split() if len(word) > 2):
                    relevant_knowledge.append(f"Bilinen kişi: {item['name']} → {item.get('info', '')}")
                elif 'topic' in item and any(word in item['topic'].lower() for word in q_lower.split() if len(word) > 2):
                    relevant_knowledge.append(f"Bilinen konu: {item['topic']} → {item.get('info', '')}")
            
            if relevant_knowledge:
                context['learned_knowledge'] = relevant_knowledge[:3]  # En fazla 3 info
        
        # Сервер talimatlarını context'e add
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

        # Profili güncelle
        _update_profile(user_id, question, answer, _profiles)
        if _profiles.get(str(user_id), {}).get('message_count', 0) % 10 == 0:
            _save_profiles(_profiles)
        
        # Talimat tespiti — "herkese X cevabını ver" gibi messagelar
        if guild_id:
            instr = _detect_instruction(question, answer)
            if instr:
                guild_key = str(guild_id)
                if guild_key not in _instructions:
                    _instructions[guild_key] = []
                # Aynı talimat var mı?
                exists = any(i.get('trigger') == instr['trigger'] for i in _instructions[guild_key])
                if not exists:
                    _instructions[guild_key].append(instr)
                    if len(_instructions[guild_key]) > 30:
                        _instructions[guild_key] = _instructions[guild_key][-30:]
                    _save_instructions(_instructions)
                    print(f'[AI] Новый talimat сохранено: {instr["trigger"][:50]}')
        
        # Öğrenilebilir infoyi çıkar ve сохранить
        if guild_id:
            learned = _extract_learned_info(question, answer)
            if learned:
                guild_key = str(guild_id)
                if guild_key not in _knowledge_base:
                    _knowledge_base[guild_key] = []
                
                # Aynı info var mı kontrole et
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
        
        # Последний 40 messageı tut (20 soru-cevap çifti) — daha uzun hafıza
        _histories[user_id] = new_history[-40:]
        # Dosyaya сохранить
        _save_histories(_histories)
        return answer or 'Hmm, bir sorun oldu. Tekrar dener misin? 🤔'
    except Exception as e:
        print(f'[AI] Ошибка: {e}')
        return 'Сейчас не могу ответить, попробуйте позже. 😅'


class AIChat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name='ai-info-clear', description="Очистить базу знаний AI serverа (Админ)")
    @commands.has_permissions(administrator=True)
    async def ai_clear_knowledge(self, ctx):
        """Сервер AI info tabanını clear (sadece adminler)"""
        guild_id = str(ctx.guild.id)
        if guild_id in _knowledge_base:
            del _knowledge_base[guild_id]
            _save_knowledge_base(_knowledge_base)
            await ctx.send('✅ Сервер AI info tabanı clearndi!', ephemeral=True)
        else:
            await ctx.send('Zaten зарегистрированные info yok. 🤷', ephemeral=True)
    async def ai_reset(self, ctx):
        """Kendi AI sohbet geçmişini sıfırla"""
        user_id = ctx.author.id
        if user_id in _histories:
            del _histories[user_id]
            _save_histories(_histories, force=True)
            await ctx.send('✅ Sohbet geçmişin sıfırlandı! Новый bir başlangıç yapabiliriz. 🔄', ephemeral=True)
        else:
            await ctx.send('Zaten зарегистрированные bir geçmişin yok. 🤷', ephemeral=True)

    @commands.hybrid_command(name='ai-sifirla', description="Сбросить историю AI чата")
    @commands.has_permissions(administrator=True)
    async def ai_add_knowledge(self, ctx, konu: str, *, info: str):
        """
        Бот'a kalıcı info öğret.
        Использование: /ai-info-add armoon Armoon, Valorant ve CS2 oynayan Türk bir esporcu.
        """
        guild_key = str(ctx.guild.id)
        if guild_key not in _knowledge_base:
            _knowledge_base[guild_key] = []
        
        # Aynı konu var mı?
        for item in _knowledge_base[guild_key]:
            if item.get('name', '').lower() == konu.lower() or \
               item.get('topic', '').lower() == konu.lower():
                item['info'] = info
                item['confidence'] = 'high'
                item['source'] = 'manual'
                _save_knowledge_base(_knowledge_base)
                await ctx.send(f'✅ **{konu}** hakkındaki info güncellendi!', ephemeral=True)
                return
        
        # Новый info add
        _knowledge_base[guild_key].append({
            'type': 'manual',
            'name': konu.lower(),
            'topic': konu.lower(),
            'info': info,
            'question': f'{konu} kimdir',
            'confidence': 'high',
            'source': 'manual'
        })
        _save_knowledge_base(_knowledge_base)
        await ctx.send(f'✅ **{konu}** hakkında info сохранено! Artık herkes sorduğunda doğru cevap vereceğim.', ephemeral=True)

    @commands.hybrid_command(name='ai-info-listele', description="Список зарегистрированных AI знаний (Админ)")
    @commands.has_permissions(administrator=True)
    async def ai_list_knowledge(self, ctx):
        """Серверya зарегистрированные AI bilgilerini listele"""
        guild_key = str(ctx.guild.id)
        items = _knowledge_base.get(guild_key, [])
        
        if not items:
            await ctx.send('Henüz зарегистрированные info yok.', ephemeral=True)
            return
        
        lines = []
        for i, item in enumerate(items, 1):
            name = item.get('name') or item.get('topic', '?')
            src = '✋ Manuel' if item.get('source') == 'manual' else '🔍 Web'
            conf = '✅' if item.get('confidence') == 'high' else '⚠️'
            lines.append(f'{conf} **{name}** ({src})')
        
        embed = discord.Embed(
            title='🧠 AI Информация Tabanı',
            description='\n'.join(lines[:20]),
            color=0x00D9FF
        )
        await ctx.send(embed=embed, ephemeral=True)

    async def _handle_dm_send(self, text: str, message: discord.Message) -> str:
        """Belirli bir userya DM отправить — 'özelden yaz', 'dm at' командаları"""
        import re

        # Hedef участникyi найти
        target_id = None
        mention_match = re.search(r'<@!?(\d+)>', text)
        if mention_match:
            target_id = int(mention_match.group(1))
        if not target_id:
            id_match = re.search(r'\b(\d{17,20})\b', text)
            if id_match:
                target_id = int(id_match.group(1))

        # "benimle aynı голосte olan" → owner'ın голос channelındaki другое участник
        cl = text.lower()
        if not target_id and any(t in cl for t in ['aynı голосte', 'ayni голосte', 'голос channelındaki', 'голос channelindaki',
                                                    'benimle olan', 'yanımdaki', 'yanimdaki']):
            for guild in self.bot.guilds:
                owner = guild.get_member(OWNER_ID)
                if not owner or not owner.voice:
                    continue
                # Aynı голос channelındaki bot olmayan другое участникler
                others = [m for m in owner.voice.channel.members
                          if m.id != OWNER_ID and not m.bot]
                if others:
                    target_id = others[0].id  # Первый kişiyi al
                    break

        if not target_id:
            return '❌ Kime DM atacağımı anlayamadım. ID, mention veya "benimle aynı голосte" de.'

        # Отправитьilecek messageı çıkar
        # "X'e özelden şunu yaz: ..." veya "X'e dm at nasıl"
        dm_content = None
        # "yaz:" veya "yaz " sonrasını al
        yaz_match = re.search(r'(?:yaz[:\s]+|at[:\s]+|отправить[:\s]+)(.+)', text, re.IGNORECASE)
        if yaz_match:
            dm_content = yaz_match.group(1).strip()
            # ID/mention'ı içeriyorsa clear
            dm_content = re.sub(r'<@!?\d+>', '', dm_content).strip()
            dm_content = re.sub(r'\b\d{17,20}\b', '', dm_content).strip()

        # Hâlâ boşsa — tüm trigger kelimeleri çıkar, kalanı message say
        if not dm_content:
            clean = text
            for t in ['özelden yaz', 'ozelden yaz', 'dm at', 'dm отправить', 'dm yaz',
                      'özel message at', 'ozel message at', 'özelden message', 'ozelden message',
                      'benimle aynı голосte', 'benimle ayni голосte', 'aynı голосte olan arkadaşa',
                      'ayni голосte olan arkadasa']:
                clean = clean.replace(t, '').strip()
            clean = re.sub(r'<@!?\d+>', '', clean).strip()
            clean = re.sub(r'\b\d{17,20}\b', '', clean).strip()
            dm_content = clean or None

        if not dm_content:
            return '❌ Ne yazacağımı anlayamadım. "özelden yaz: <message>" formatını kullan.'

        # Участникyi bul ve DM at
        for guild in self.bot.guilds:
            member = guild.get_member(target_id)
            if not member:
                continue
            try:
                await member.send(dm_content)
                return f'✅ **{member.display_name}**\'e DM отправитьildi: *{dm_content[:100]}*'
            except discord.Forbidden:
                return f'❌ **{member.display_name}** DM\'lere kapalı.'
            except Exception as e:
                return f'❌ DM отправитьilemedi: {e}'

        # Участник guild'de bulunamadıysa direkt fetch dene
        try:
            user = await self.bot.fetch_user(target_id)
            await user.send(dm_content)
            return f'✅ **{user.name}**\'e DM отправитьildi: *{dm_content[:100]}*'
        except Exception as e:
            return f'❌ Пользователь bulunamadı veya DM отправитьilemedi: {e}'

    async def _handle_voice_move(self, text: str, message: discord.Message) -> str:
        """Голос channelı movema — tek/çift adım, geri getir, channel adı desteği"""
        import re
        import asyncio

        # Normalize: ASCII türkçe karakter eşleştirmesi için hem orijinal hem normalize
        def norm(s):
            return (s.lower()
                    .replace('ü', 'u').replace('ş', 's').replace('ğ', 'g')
                    .replace('ı', 'i').replace('ö', 'o').replace('ç', 'c')
                    .replace('İ', 'i').replace('Ü', 'u').replace('Ş', 's'))

        cl = text.lower()
        cl_norm = norm(text)

        # ── Hedef участникyi найти ──────────────────────────────────────────────────
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
            return '❌ Kimi moveyacağımı anlayamadım. ID veya mention ver.'

        # ── "geri getir" / "geri al" talebi var mı? ─────────────────────────
        geri_var = any(t in cl_norm for t in ['geri getir', 'geri al', 'geri don', 'geri götür', 'geri gotur'])

        # ── Yön ve adım sayısı ───────────────────────────────────────────────
        yon = 0
        # Hem "üst/ust" hem "yukarı/yukari" destadd
        yukari_words = ['üst', 'ust', 'yukarı', 'yukari', 'yukar']
        asagi_words  = ['alt', 'aşağı', 'asagi', 'asag']

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

        # ── "bu voice / bu channela geri getir" — hedef channel adı ──────────────
        # "geri getir bu voice" → "bu голос" = özel bir channel adı değil, orijinal channel demek
        # Ama "X channelına geri getir" gibi bir channel adı geçiyorsa onu yakala
        hedef_channel_adi = None
        channel_adi_match = re.search(r'(?:geri getir|geri al|move|al)\s+(.+?)(?:\s+channelına?|voice?|$)', cl)
        if channel_adi_match:
            aday = channel_adi_match.group(1).strip()
            if aday not in ('bu', 'o', 'şu', 'su', 'bu голос', 'o голос'):
                hedef_channel_adi = aday

        results = []
        for guild in self.bot.guilds:
            member = guild.get_member(target_id)
            if not member:
                continue
            if not member.voice or not member.voice.channel:
                results.append(f'❌ {member.display_name} şu an bir голос channelında değil.')
                continue

            current_vc = member.voice.channel
            voice_channels = sorted(guild.voice_channels, key=lambda c: c.position)
            current_idx = next((i for i, c in enumerate(voice_channels) if c.id == current_vc.id), None)
            if current_idx is None:
                results.append('❌ Mevcut channel listede bulunamadı.')
                continue

            # ── Имяım 1: Taşı ────────────────────────────────────────────────
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
                # Канал adı direkt geçiyor mu metinde?
                for vc in voice_channels:
                    if norm(vc.name) in cl_norm:
                        hedef_vc = vc
                        break

            if not hedef_vc or hedef_vc.id == current_vc.id:
                if hedef_vc and hedef_vc.id == current_vc.id:
                    results.append(f'ℹ️ Zaten o channelda: **{current_vc.name}**')
                else:
                    results.append(
                        f'❌ Hedef channel bulunamadı. Mevcut: **{current_vc.name}**\n'
                        f'Голос channelları: {", ".join(vc.name for vc in voice_channels)}'
                    )
                continue

            try:
                await member.move_to(hedef_vc)
                msg = f'✅ **{member.display_name}** → **{hedef_vc.name}** movendı.'

                # ── Имяım 2: Назад getir ──────────────────────────────────────
                if geri_var:
                    # "bu voice geri getir" = orijinal channela (current_vc) geri al
                    geri_hedef = current_vc

                    # Eğer belirli bir channel adı varsa onu kullan
                    if hedef_channel_adi:
                        for vc in voice_channels:
                            if norm(vc.name) in norm(hedef_channel_adi) or norm(hedef_channel_adi) in norm(vc.name):
                                geri_hedef = vc
                                break

                    await asyncio.sleep(3)  # 3 saniye badd
                    # Участник hâlâ голос channelında mı kontrole et
                    await member.guild.chunk()  # cache обновить
                    fresh = guild.get_member(target_id)
                    if fresh and fresh.voice:
                        await fresh.move_to(geri_hedef)
                        msg += f'\n✅ 3 saniye sonra **{geri_hedef.name}** channelına geri getirildi.'
                    else:
                        msg += f'\n⚠️ Назад getirilemedi — участник голос channelından ayrılmış.'

                results.append(msg)
            except discord.Forbidden:
                results.append('❌ Правоm yok (Move Members izni gerekli).')
            except Exception as e:
                results.append(f'❌ Ошибка: {e}')

        return '\n'.join(results) if results else '❌ Участник bu serverlarda bulunamadı.'

    def _norm(self, s: str) -> str:
        return (s.lower()
                .replace('ü','u').replace('ş','s').replace('ğ','g')
                .replace('ı','i').replace('ö','o').replace('ç','c')
                .replace('İ','i').replace('Ü','u').replace('Ş','s'))

    def _extract_target(self, text: str):
        """Metinden hedef участник ID'sini çıkar. (mention, raw ID, 'beni', имя)"""
        import re
        m = re.search(r'<@!?(\d+)>', text)
        if m: return int(m.group(1))
        m = re.search(r'\b(\d{17,20})\b', text)
        if m: return int(m.group(1))
        cl = text.lower()
        if any(t in cl for t in ['beni', 'bana', 'benim', 'ben ']):
            return OWNER_ID
        # Имя ile ara — tüm serverlardaki участникlerde ara
        # Команда kelimelerini clear, kalan kısım имя olabilir
        stop_words = ['голосten at', 'voice al', 'voice çek', 'ban at', 'kick at',
                      'timeout ver', 'uyar', 'role ver', 'role al', 'bu arkadasi',
                      'bu arkadasin', 'bu kisiyi', 'bu участникyi', 'bu uyeyi',
                      'arkadasi', 'arkadasini', 'kisiyi', 'участникyi', 'uyeyi',
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
        """Metinden süreyi minutes cinsinden çıkar."""
        import re
        cl = text.lower()
        m = re.search(r'(\d+)\s*(час|hour)', cl)
        if m: return int(m.group(1)) * 60
        m = re.search(r'(\d+)\s*(день|gun|day)', cl)
        if m: return int(m.group(1)) * 1440
        m = re.search(r'(\d+)\s*(hafta|week)', cl)
        if m: return int(m.group(1)) * 10080
        m = re.search(r'(\d+)\s*(minutes|dk|min)', cl)
        if m: return int(m.group(1))
        return 10  # varsayılan

    async def _detect_owner_intent(self, text: str, message: discord.Message) -> bool:
        """Owner DM командаları — anahtar kelime bazlı, yanlış yazsan da çalışır"""
        import re
        cl = text.lower()
        cn = self._norm(text)

        # ── MÜZİK ────────────────────────────────────────────────────────────
        # Голос channelına gir (müziksiz)
        голос_gir_triggers = ['voice gir', 'voice katıl', 'voice gel', 'channela gir', 'benim voice gir',
                            'voice gir', 'голос channelına gir', 'голос channelina gir', 'yanima gel']
        if any(t in cn for t in [self._norm(x) for x in голос_gir_triggers]):
            result_msg = '❌ Голос channelında değilsin.'
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
                    result_msg = f'✅ **{member.voice.channel.name}** channelına girdim.'
                    break
                except Exception as e:
                    result_msg = f'❌ Ошибка: {e}'
            await message.channel.send(result_msg)
            return True

        # Голос channelından çık
        голос_cik_triggers = ['голосten çık', 'голосten cik', 'channeldan çık', 'channeldan cik',
                            'çık голосten', 'cik голосten', 'ботu çıkar', 'ботu cikar']
        if any(t in cn for t in [self._norm(x) for x in голос_cik_triggers]):
            result_msg = '❌ Zaten голос channelında değilim.'
            for guild in self.bot.guilds:
                vc = guild.voice_client
                if vc:
                    await vc.disconnect()
                    result_msg = '✅ Голос channelından çıktım.'
                    break
            await message.channel.send(result_msg)
            return True

        muzik_triggers = ['çal', 'cal', 'müzik', 'muzik', 'şarkı', 'sarki', 'oynat']
        if any(t in cl for t in muzik_triggers):
            query = text
            for t in ['çal', 'cal', 'müzik çal', 'muzik cal', 'şarkı çal', 'sarki cal', 'oynat', 'bana']:
                query = query.replace(t, '').strip()
            query = query.strip() or 'lofi'
            result_msg = '❌ Голос channelında değilsin.'
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
                        vc = None  # Kapanmakta olan bağlantıyı clear
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
                        result_msg = f'✅ Kuyruğa addndi: **{title}**'
                    else:
                        q.insert(0, item)
                        await play_next(guild, text_channel)
                        result_msg = f'🎵 Çalınıyor: **{title}**'
                    break
                except Exception as e:
                    result_msg = f'❌ Müzik Ошибкаsı: {e}'
            await message.channel.send(result_msg)
            return True

        # AFK убрать — önce kontrole et (закрыть/убрать varsa AFK açma)
        afk_закрыть_triggers = ['döndüm', 'geldim', 'uyandım', 'afk убрать', 'afk закрыть',
                              'afk убрать', 'afk закрыть', 'afk modunu закрыть', 'afk modu закрыть',
                              'afk bitir', 'afk удалить', 'afk отмена']
        if any(t in cl for t in afk_закрыть_triggers):
            afk_cog = self.bot.get_cog('AFK')
            for guild in self.bot.guilds:
                member = guild.get_member(OWNER_ID)
                if not member:
                    continue
                if afk_cog:
                    afk_cog._remove(guild.id, OWNER_ID)
                try:
                    nick = member.display_name
                    if nick.startswith('😴 '):
                        await member.edit(nick=nick[2:].strip() or None)
                except:
                    pass
            from cogs.afk import _pending_mentions
            pending = _pending_mentions.pop(OWNER_ID, [])
            if pending:
                lines = [f"• **{p['from']}**: {p['msg'][:60]}" for p in pending[-5:]]
                await message.channel.send(f'✅ Hoş geldin! {len(pending)} kişi etiketledi:\n' + '\n'.join(lines))
            else:
                await message.channel.send('✅ AFK modu закрытьıldı.')
            return True

        # AFK aç — "закрыть" veya "убрать" geçiyorsa tetikleme
        afk_ac_triggers = ['afk', 'uykum var', 'uyuyacağım', 'gidiyorum', 'yokum']
        afk_engel = ['закрыть', 'убрать', 'kaldir', 'bitir', 'удалить', 'отмена', 'modunu', 'modu']
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
                    if not nick.startswith('😴'):
                        await member.edit(nick=f'😴 {nick[:28]}')
                except:
                    pass
            await message.channel.send(f'😴 AFK modu активна! Причина: **{reason}**')
            return True

        # Голос channelı movema
        голос_tasi_triggers = [
            'голос channelına', 'voice move', 'voice çek', 'voice al',
            'üst channela', 'ust channela', 'alt channela',
            'channela move', 'channela çek', 'channela al', 'voice',
            'üst channel', 'ust channel', 'yukarı channel', 'yukari channel',
            'channelına al', 'channelina al', 'move voice', 'çek voice', 'al voice',
        ]
        # Голосten at — ayrı handler
        голосten_at_triggers = ['голосten at', 'голосten çıkar', 'голосten cikar', 'голос channelından at',
                              'голос channelından çıkar', 'голос channelindan at', 'голосten kick']
        if any(t in cn for t in [self._norm(x) for x in голосten_at_triggers]):
            target_id = self._extract_target(text)
            if not target_id:
                await message.channel.send('❌ Kimi ateceğimi anlayamadım.')
                return True
            results = []
            for guild in self.bot.guilds:
                member = guild.get_member(target_id)
                if not member:
                    continue
                if not member.voice:
                    results.append(f'❌ **{member.display_name}** zaten голосte değil.')
                    continue
                try:
                    await member.move_to(None)
                    results.append(f'✅ **{member.display_name}** голосten atıldı.')
                except discord.Forbidden:
                    results.append('❌ Правоm yok.')
                except Exception as e:
                    results.append(f'❌ Ошибка: {e}')
            await message.channel.send('\n'.join(results) if results else '❌ Участник bulunamadı.')
            return True

        if any(t in cl for t in голос_tasi_triggers):
            result_msg = await self._handle_voice_move(text, message)
            await message.channel.send(result_msg)
            return True

        # DM / özelden message
        dm_triggers = ['özelden yaz', 'ozelden yaz', 'dm at', 'dm отправить', 'dm yaz',
                       'özel message at', 'ozel message at', 'özelden message', 'ozelden message']
        if any(t in cl for t in dm_triggers):
            result_msg = await self._handle_dm_send(text, message)
            await message.channel.send(result_msg)
            return True

        # ── GÖREV ZİNCİRİ ────────────────────────────────────────────────────
        # "X kişiyi izle, küfür ederse ban at" gibi koşullu görevler
        gorev_add = ['görevi add', 'gorevi add', 'izle ve', 'takip et', 'görev kur', 'gorev kur',
                      'ederse ban', 'ederse kick', 'ederse timeout', 'yaparsa ban', 'yaparsa kick']
        if any(t in cn for t in [self._norm(x) for x in gorev_add]):
            target_id = self._extract_target(text)
            desc = text.strip()
            task = {'id': len(_active_tasks) + 1, 'desc': desc,
                    'target_id': target_id, 'created': str(datetime.datetime.now())}
            _active_tasks.append(task)
            _save_tasks(_active_tasks)
            await message.channel.send(
                f'✅ Görev сохранено (#{task["id"]}): *{desc[:100]}*\n'
                f'`görevleri göster` ile listeleyebilirsin.'
            )
            return True

        gorev_listele = ['görevleri göster', 'gorevi goster', 'активна görevler', 'активна gorevler',
                         'görev listesi', 'gorev listesi']
        if any(t in cn for t in [self._norm(x) for x in gorev_listele]):
            if not _active_tasks:
                await message.channel.send('📋 Активен görev yok.')
            else:
                lines = [f'**#{t["id"]}** — {t["desc"][:80]}' for t in _active_tasks]
                await message.channel.send('📋 **Активен Görevler:**\n' + '\n'.join(lines))
            return True

        gorev_удалить = ['görevi удалить', 'gorevi удалить', 'görevi убрать', 'gorevi kaldir', 'görev отмена']
        if any(t in cn for t in [self._norm(x) for x in gorev_удалить]):
            import re as _re
            num = _re.search(r'\d+', text)
            if num:
                tid = int(num.group())
                before = len(_active_tasks)
                _active_tasks[:] = [t for t in _active_tasks if t['id'] != tid]
                _save_tasks(_active_tasks)
                if len(_active_tasks) < before:
                    await message.channel.send(f'✅ Görev #{tid} удалено.')
                else:
                    await message.channel.send(f'❌ #{tid} numaralı görev bulunamadı.')
            else:
                await message.channel.send('❌ Hangi görevi удалитьmek istediğini belirt: `görevi удалить 1`')
            return True

        # ── SUNUCU DURUMU SORGULAMA ───────────────────────────────────────────
        status_triggers = ['serverda kim var', 'kim online', 'kim голосte', 'kaç kişi online',
                          'server statusu', 'neler oluyor', 'ne var ne yok serverda',
                          'kim активна', 'голосte kim var', 'online kim var']
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
                lines.append(f'• Online: {len(online)} kişi')
                if in_voice:
                    lines.append('• Голос channelları:\n  ' + '\n  '.join(in_voice))
                else:
                    lines.append('• Голос channellarında kimse yok')
                ticket_chs = [c for c in guild.text_channels if c.name.startswith('ticket-')]
                if ticket_chs:
                    lines.append(f'• Открыт ticket: {len(ticket_chs)}')
            await message.channel.send('\n'.join(lines) or '❌ Сервер infosi alınamadı.')
            return True

        # Mod уведомлениеi aç/закрыть
        mod_notify_ac = ['mod уведомление aç', 'mod уведомление ac', 'ceza уведомлениеi aç', 'ceza уведомлениеi ac',
                         'mod notify aç', 'mod notify ac', 'уведомлениеleri aç', 'уведомлениеleri ac']
        mod_notify_закрыть = ['mod уведомление закрыть', 'ceza уведомлениеi закрыть', 'mod notify закрыть', 'уведомлениеleri закрыть']
        if any(t in cn for t in [self._norm(x) for x in mod_notify_ac]):
            import json as _j
            os.makedirs('data', exist_ok=True)
            with open('data/mod_notify.json', 'w', encoding='utf-8') as f:
                _j.dump({'enabled': True}, f)
            await message.channel.send('✅ Mod уведомлениеleri açıldı. Başka modlar действие yapınca DM alacaksın.')
            return True
        if any(t in cn for t in [self._norm(x) for x in mod_notify_закрыть]):
            import json as _j
            os.makedirs('data', exist_ok=True)
            with open('data/mod_notify.json', 'w', encoding='utf-8') as f:
                _j.dump({'enabled': False}, f)
            await message.channel.send('✅ Mod уведомлениеleri закрытьıldı.')
            return True

        # Hiçbir handler eşleşmedi — normal sohbete düş
        return False

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        is_dm = isinstance(message.channel, discord.DMChannel)

        # ── Owner'ın DM cevabını yakala ──────────────────────────────────────
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
                    await message.add_reaction('✅')
                except Exception as e:
                    await message.channel.send(f'❌ İletilemedi: {e}')
                return

            # ── Owner'ın akıllı eylem sistemi (AI intent detection) ──────────
            content_lower = message.content.lower().strip()
            content_raw = message.content.strip()

            # Tercih/kural сохранитьme — "bunu bana yazma", "bunu her vakit yap" vb.
            pref_triggers = ['bunu bana yazma', 'bunu söyleme', 'bunu yapma',
                             'her vakit yap', 'her vakit söyle', 'hatırla',
                             'unutma', 'bunu bil', 'artık biliyorsun']
            if any(t in content_lower for t in pref_triggers):
                _owner_prefs['rules'].append(content_raw)
                if len(_owner_prefs['rules']) > 50:
                    _owner_prefs['rules'] = _owner_prefs['rules'][-50:]
                _save_owner_prefs(_owner_prefs)
                await message.channel.send(f'✅ Сохранитьtim: **{content_raw[:100]}**')
                return

            # AI ile intent tespit et
            intent = await self._detect_owner_intent(content_raw, message)
            if intent:
                return  # Intent işlendi, normal AI akışına geçme

        is_ai_channel = message.channel.id in AI_CHANNELS or message.channel.id in _dynamic_channels

        if not (is_dm or is_ai_channel):
            return

        # Каналda sadece "moe" ile başlayan veya bot mention içeren messagelara cevap ver
        # Dinamik channellarda her messagea cevap ver
        if is_ai_channel and not is_dm:
            is_dynamic = message.channel.id in _dynamic_channels
            if not is_dynamic:  # Sadece dinamik channellarda cevap ver, başka hiçbir yerde
                return
            # "moe" prefix'ini clear
            content = re.sub(r'^moe\s*', '', message.content, flags=re.IGNORECASE).strip()
            # mention'ları clear
            for m in message.mentions:
                content = content.replace(f'<@{m.id}>', '').replace(f'<@!{m.id}>', '')
            content = content.strip() or 'Merhaba!'
        else:
            content = message.content.strip() or 'Merhaba!'

        # Arthur'un команда talebi — J.A.R.V.I.S. modu
        if OWNER_ID and message.author.id == OWNER_ID:
            cmd_triggers = ['channel aç', 'channel создать', 'message at', 'announce yap',
                           'ban at', 'kick at', 'timeout ver', 'role ver', 'role al']
            if any(t in content.lower() for t in cmd_triggers):
                context['jarvis_mode'] = True
                context['available_commands'] = (
                    'Kullanılabilir командаlar:\n'
                    '/moderate ban @user причина\n'
                    '/moderate kick @user причина\n'
                    '/moderate timeout @user minutes причина\n'
                    '/role @user @role\n'
                    '/utility clear adet\n'
                    '/utility lock\n'
                    '/utility unlock\n'
                    'Канал создатьmak için: Discord\'da Сервер Настройкиı → Каналlar'
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
            answer = "Bunu söyleyemem. 😅"

        # Cevap "bilmiyorum" içeriyorsa owner'a sor
        bilmiyorum_triggers = ['bilmiyorum', 'emin değilim', 'info bulamadım', 'hakkında infom yok']
        if OWNER_ID and any(t in answer.lower() for t in bilmiyorum_triggers):
            try:
                owner = await self.bot.fetch_user(OWNER_ID)
                guild_id = message.guild.id if message.guild else 0
                user_name = message.author.display_name
                embed = discord.Embed(
                    title='❓ Cevaplayamadığım Soru',
                    color=0xf59e0b,
                    description=f'**Soran:** {user_name} (`{message.author.id}`)\n'
                                f'**Soru:** {content}\n\n'
                                f'**Cevaplamak için bu messagea reply at.**'
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
                print(f'[AI] Owner DM Ошибкаsı: {e}')

        if is_dm:
            # DM log'a сохранить
            try:
                import json as _j, os as _os, datetime as _dt3
                _os.makedirs('data', exist_ok=True)
                _f = 'data/dm_log.json'
                _d = _j.load(open(_f, encoding='utf-8')) if _os.path.exists(_f) else {}
                uid = str(message.author.id)
                if uid not in _d: _d[uid] = []
                # Gelen messageı сохранить
                _d[uid].append({
                    'author': message.author.display_name,
                    'content': message.content,
                    'timestamp': _dt3.datetime.utcnow().isoformat(),
                    'from_бот': False,
                })
                # Бот cevabını сохранить
                _d[uid].append({
                    'author': 'Aether',
                    'content': answer,
                    'timestamp': _dt3.datetime.utcnow().isoformat(),
                    'from_бот': True,
                })
                # Max 200 message tut
                _d[uid] = _d[uid][-200:]
                with open(_f, 'w', encoding='utf-8') as fp:
                    _j.dump(_d, fp, ensure_ascii=False, indent=2)
            except Exception as _le:
                print(f'[DM LOG] Ошибка: {_le}')
            await message.channel.send(answer)
        else:
            await message.reply(answer, mention_author=False)


async def setup(bot):
    cog = AIChat(bot)
    await bot.add_cog(cog)
    
    # Бот kapanırken history'yi сохранить
    @бот.event
    async def on_shutdown():
        _save_histories(_histories, force=True)
        print('[AI] Konuşma geçmişleri сохранено.')
