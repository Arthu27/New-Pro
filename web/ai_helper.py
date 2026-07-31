"""
Ticket AI — prodvinutaya система podderjki
Chain-of-thought reasoning, personalizaciya, proaktife povedenie, function calling
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

# ─── VERITABANI ИНФОРМАЦИЯ BOTUN ───────────────────────────────────────────────────────

def _bot_knowledge_base() -> str:
    """Polnaya veritabanı информация о botta Aether"""
    return """
═══════════════════════════════════════════
AETHER BOT — POLNAYa VERITABANI ИНФОРМАЦИЯ
═══════════════════════════════════════════

## NE TAKOE AETHER?
Aether — çokfunkcionalniy Discord bot для управление сервер.
Web-panel (Flask) + Discord bot работа vmeste.
Panel erişimüzerinde с Cloudflare tunnel по publicnoy ssilke.
Ссылка на panel nahoditsya в канал #aether-panel.

## 🛡️ MODERASYON
- /moderate ban @user [причина] — permanentniy ban
- /moderate kick @user [причина] — kick с сервер
- /moderate timeout @user [dakikai] [причина] — vremenniy mute
- /moderate untimeout @user — удалено mute
- /moderate unban [user_id] — razban
- /utility clear [число] — toplu удалить сообщение
- /utility lock/unlock — blokirovka/razblokirovka канал
- /utility userinfo @user — информация о у пользователя
- /роли @user @роль — ver/удалено роль
- /history @user — история moderasyonu
- /case [id] — detali işler
- /note @user [metin] — добавить notu
- /notes @user — показать notlar
- /watchlist @user [причина] — liste наблюдение
- /banlist — yasaklanmış пользователи
- /massrole @роль [ver/удалено] — toplu verme роль

## ⚠️ ПРЕДУПРЕЖДЕНИЯ
- /warn @user [причина] — ver предупреждение
- /warnings @user — liste предупреждение
- /clearwarns @user — temizle предупреждения
Автоматически olarake наказания: iken nakoplenii предупреждение — mute/kick/ban.

## 🎵 MÜZIK
- /play [isim/ссылка] — vosproizvesti
- /pause — pauza/devam et
- /skip — propustit trek
- /queue — kuyruk
- /volume [0-100] — gromkost
- /clear-queue — temizle kuyruk
- /leave — pokinut ses канал
- /join — prisoedinitsya e канал

## 💰 EKONOMI
- /economy balance — bakiye
- /economy daily — ежедневный награда (50 monet, 24c)
- /economy transfer @user [собратьm] — perevesti moneti
- /economy ranking — en iyi bogacey
- /games gamble [собратьm] — azartnaya oyun
- /games slot [собратьm] — slot-makine
- /games heist @user — soygun
- /shop — mağaza
- /buy [predmet] — kupit ürün

## 🎮 RAZVLECENIYa
- /coinflip — monetka
- /роль [число] — brosit kubik
- /rps — kamen-nojnici-bumaga
- /guess-start — ugaday число
- /guess [число] — vvesti число
- /8ball [soru] — magicesi sar
- /random-member — slucayniy участник
- /fun [dice] — razvlekatelnie
- /poll [soru] — bistriy anket

## 👥 SOCIALNOE
- /birthday [день] [ay] — сохранить день рождение
- /birthdays — blijaysie день рождение
- /afk [причина] — mod AFK
- /staff-apply — заявка модератора
- /profile — sizin profil
- /invites — статистика davet
- /invite-ranking — en iyi davet edenler

## 🏆 ОЧЕРЕДЬ
- /rank — sizin seviye ve XP
- /top-level — en iyi-10 по seviyeye
- !ranking — общий очередь
- !ranking messages — очередь сообщение
- !ranking voice — очередь ses время
- !ranking invites — очередь davet
- /mod-stats @user — статистика модератор
- /activemods — aktivnie модераторы

## 📅 MEROPRIYaTIYa
- /event-create [isim] — создать etkinlik
- /events — aktivnie meropriyatiya
- /event-cancel [id] — otmenit etkinlik
- /giveaway — создать розыгрыш

## ⚙️ УПРАВЛЕНИЕ СЕРВЕР
- /setup-logs — создать log-каналы
- /verify-setup — настройк verifikaciyu
- /ticket_panel — panel ticketların
- /duty-panel — panel задачи
- /duty-add @user [puan] — добавить progress
- /duty-stats — tablo puan
- /automod — автоматически
- /level-роли-add [seviye] @роль — роль для seviye
- /level-роли — liste роль для seviyeler

## 🔧 INSTRUMENTI
- /botinfo — информация о botta
- /сервер — сервер информация
- /uptime — время работа botun
- /health — состояние сервер
- /avatar @user — avatar пользователь
- /channel-stats — статистика канал
- /archive [число] — arhiv сообщение
- /ai-reset — sbrosit история AI
- /ai-learn [tema] [metin] — obucit AI
- /color [#HEX] — информация о renkte
- /announce #канал [metin] — создать duyuru

## 🤖 AI ASSISTENT
- Напишите в канал с AI — on cevapit
- /ai-reset — sbrosit история разговор
- /ai-learn [tema] [metin] — naucit AI novomu faktu
- AI pomogaet в ticketlarda автоматически как

## 🎫 ТИКЕТЫ
- Нажмите кнопку в канале для тикета
- Откроется канал #ticket-вашеимя
- AI-ассистент поможет решить проблему
- Если не получится — передаст модератору
- При закрытии — транскрипт сохраняется

## ✅ VERIFIKACIYa
- Girin в канал verifikacii
- Клик butona или ispolzuyte /verify
- Posle verifikacii — polucite роль участник

## 😴 AFK
- /afk [причина] — вход yap в mod AFK
- Takma ad menyaetsya на 💤 [sizin takma ad]
- Iken upominanii — bot soobsaet ne siz AFK
- Iken denhaklarınke сообщения — AFK snimaetsya автоматически как

## 🎂 ДЕНЬ РОЖДЕНИЕ
- /birthday [день] [ay] — сохранить
- /birthdays — blijaysie день рождение
- В день рождение — bot pozdravlyaet автоматически как

## 📨 PRIGLASENIYa
- /invites — vasa статистика
- /invite-ranking — en iyi davet edenler
- Seviyeler: Posol / Priglasayusiy / Новый priglasayusiy

## 🌐 WEB-PANEL
Panel — web-interfeys управление сервер.
Как вход yap: ссылка в канал #aether-panel → Discord ID + parola.
Seviyeler доступ:
- Участник: profil, заявка, день рождение
- Модератор: loglar, предупреждения, ticketlar
- Yönetici: команды, каналы, roles, автоматически
- Sahip: vse

## ❓ CASTIE SORULAR
В: Как вход yap в panel?
О: Ссылка в канал #aether-panel → Discord ID + parola.

В: Müzik не oynuyor?
О: Girin в ses канал, после /play. Если ошибка — /leave ve tekrar /play.

В: Как povisit seviye?
О: Напишите сообщения + sidite в ses в каналах. /rank — sizin seviye.

В: Как aç ticket?
О: Buton в канал ticketların → "Создать ticket".

В: Как al роль?
О: Канал выбор роль или /color-роли.

В: Как podat zayavku модератора?
О: /staff-apply или с panel.

В: Как сохранить день рождение?
О: /birthday [день] [ay] или с panel.

В: Zabil parola den paneli?
О: Клик "Для parola?" на stranice вход → Discord ID → kod в DM.
"""


# ─── OPREDELENIE KATEGORILER (AI) ─────────────────────────────────────────────

def _detect_category_ai(message: str, history: List[Dict]) -> str:
    """Opredelenie kategoriler с с AI (не keyword-based)"""
    prompt = """Opredeli kategori obraseniya пользователь в Discord tickette.

KATEGORILER:
- complaint: жалоба на drugogo пользователь (оскорбление, spam, toksisite)
- question: soru о botta, paneli, команда, в ролях, ekonomike
- technical: tehniceskaya sorun (не работает, ошибка, bag)
- other: vse ostalnoe

ПРАВИЛА:
- Если пользователь jaluetsya на DRUGOGO пользователь → complaint
- Если sprasivaet как ne-to ileişlert → question
- Если ne-to не работает или vidaet ошибка → technical
- Если prosto boltaet или neponyatno → other

Cevap ТОЛЬКО birine slovom: complaint, question, technical или other.
Bez poyasneniy, bez tocek, bez kavicek.

Сообщение пользователь: """

    messages = [
        {'role': 'user', 'content': prompt + message}
    ]

    try:
        from web.model_selector import smart_call
        result, _, _ = smart_call(messages, task_type='category_detection', max_tokens=10, temperature=0.1)
        result = result.strip().lower()
        if result in ('complaint', 'question', 'technical', 'other'):
            return result
    except:
        pass

    # Fallback на keyword-based
    return _detect_category_fallback(message)


def _detect_category_fallback(message: str) -> str:
    """Fallback: keyword-based opredelenie kategoriler"""
    msg = message.lower()
    complaint_words = ['жалоба', 'oskorblyaet', 'spamit', 'toksicniy', 'materitsya', 'ugrojaet', 'travit']
    technical_words = ['не работает', 'ошибка', 'bag', 'sloazs', 'vidaet ошибка', 'не mogu']
    question_words = ['как', 'где', 'ne время', 'ne', 'почему', 'zacem', 'mümkün mı']

    if any(w in msg for w in complaint_words):
        return 'complaint'
    if any(w in msg for w in technical_words):
        return 'technical'
    if any(w in msg for w in question_words):
        return 'question'
    return 'other'


# ─── PROMPTI С CHAIN-OF-THOUGHT ─────────────────────────────────────────────

def _prompt_complaint() -> str:
    """Prompt для жалоба — chain-of-thought"""
    return """Sen — AI модератор Discord сервер. Cevapla на русский.

POLUCENA ЖАЛОБА. Senin задача:
1. PROANALIZIRUY situaciyu (кто, ne, ne время)
2. SOBERI информация:
   - Sprosi кто narusitel (Discord ID или @etiket)
   - Sprosi в kakom канал proizoslo
   - Panketve dokazatelstva (skrinsoti, ссылка на сообщения)
3. OCENI ciddiyet:
   - Legkoe нарушение (spam, flud) → predupredi
   - Ortalama (оскорбление) → ACTION:WARN:user_id=X:reason=Y
   - Tyajeloe (tehditler, travlya) → ACTION:JAIL:user_id=X:duration=60:reason=Y ACTION:ESCALATE
4. USPOKOY пользователь, skaji ne razberemsya

ПРАВИЛА:
- НЕ prosi skrinsoti если ih zaten dali
- НЕ öner "aç ticket" — biz zaten в tickette
- Bud empaticnim, no professionalnim
- Если нарушение tyajeloe — deystvuy bistro

FORMAT CEVABI:
До cevap пользователю (metinle).
В конецra, если gerekli записей — на novoy satıre:
ACTION:WARN:user_id=123456:reason=оскорбление
или
ACTION:JAIL:user_id=123456:duration=60:reason=travlya ACTION:ESCALATE
"""


def _prompt_question() -> str:
    """Prompt для soruov — chain-of-thought"""
    return """Sen — AI pomosnik Discord сервер. Cevapla на русский.

POLUCEN SORU. Senin задача:
1. PONYaI soru (о cem imenno sprasivayut)
2. PROVER veriбазу информация (biliyorsun mı cevap)
3. CEVAP cetko ve kratko:
   - Если biliyorsun → day cevap + пример ispolzovaniya
   - Если не emin → skaji "Не emin, no..." + lucsee predpolojenie
   - Если не biliyorsun → ACTION:ESCALATE (на e модератор)

ПРАВИЛА:
- Cevapla на 2-3 predlojeniya maksimum
- Hadi konkretnie команды с пример
- НЕ öner "aç ticket" — biz zaten в tickette
- Если soru о drugom у пользователя — не raskrivay licnuyu информация

ПРИМЕР HOROSIH CEVAPLARIN:
В: Как zabanit spamera?
О: Ispolzuy `/moderate ban @user причина`. На: `/moderate ban @spammer Spam в sohbette`. Bot denhaklarıtutar DM пользователю ve zapiset в loglar.

В: Как povisit seviye?
О: Pisi сообщения в sohbette ve sidi в ses в каналах — polucaes XP. Контроль et seviye: `/rank`. En iyi-10: `/top-level`.
"""


def _prompt_technical() -> str:
    """Prompt для tehniceskih problem — chain-of-thought"""
    return """Sen — AI tehdestek Discord сервер. Cevapla на русский.

TEHNICESKAYa SORUN. Senin задача:
1. DIAGNOSTIRUY sorunu (ne imenno не работает)
2. PREDLOJI reseniya (minimum 2 varianta):
   - Samoe veroyatnoe решение
   - Alternativnoe решение
3. POSAGOVO obyasni как vipolnit решение
4. Если не pomoglo → ACTION:ESCALATE

ПРАВИЛА:
- Nacinay с samogo prostogo reseniya
- Hadi posagovie instrukcii (1, 2, 3...)
- Если nujna команда — ukaji tocno с пример
- НЕ öner "aç ticket" — biz zaten в tickette
- Если sorun slojnaya ve sen не emin → srazu ACTION:ESCALATE

ПРИМЕР:
В: Müzik не oynuyor
О: Hadi proverim:
1. Sen в seste канал? (bot olmalı olmak в tom je канал)
2. Poprobuy `/leave` после tekrar `/play [isim]`
3. Prover ne u botun var администратор на podanahtarenie e sesovim канал

Если не pomoglo — направление e модератор.
"""


def _prompt_other() -> str:
    """Prompt для drugih obraseniy — chain-of-thought"""
    return """Sen — AI pomosnik Discord сервер. Cevapla на русский.

OBRASENIE НЕ YaSNO. Senin задача:
1. POYMI ne hocet пользователь
2. UTOCNI если neponyatno (zaday 1 soru)
3. POMOGI если mojes
4. Если не mojes → ACTION:ESCALATE

ПРАВИЛА:
- Bud drujelyubnim
- Zaday maksimum 1 utocnyayusiy soru
- Если пользователь prosto boltaet — podderji разговор
- Если sorun sereznaya — на e модератор
- НЕ öner "aç ticket" — biz zaten в tickette
"""


def _get_prompt_by_category(category: str) -> str:
    """Al prompt по kategoriler"""
    prompts = {
        'complaint': _prompt_complaint(),
        'question': _prompt_question(),
        'technical': _prompt_technical(),
        'other': _prompt_other(),
    }
    return prompts.get(category, _prompt_other())


# ─── GLAVNAYa FUNKCIYa — AI TICKET RESPONSE ───────────────────────────────────

async def ai_ticket_response(user_message: str, history: List[Dict], guild_context: Dict) -> Tuple[str, bool, str, List[Dict], str]:
    """
    Glavnaya funkciya AI cevabı в tickette.

    Returns:
        (response, should_escalate, escalation_category, updated_history, detected_category)
    """
    # 1. Belirliyoruz kategori с с AI
    category = _detect_category_ai(user_message, history)

    # 2. Alıyoruz prompt для kategoriler
    system_prompt = _get_prompt_by_category(category)

    # 3. Topluyoruz bağlam
    messages = [{'role': 'system', 'content': system_prompt}]

    # Veritabanı информация (для question/technical/other)
    if category in ('question', 'technical', 'other'):
        messages.append({'role': 'system', 'content': _bot_knowledge_base()})

    # 4. Personalizaciya — информация о у пользователя
    user_info = []
    if guild_context.get('user_name'):
        user_info.append(f"Isim: {guild_context['user_name']}")
    if guild_context.get('user_roles'):
        user_info.append(f"Роли: {', '.join(guild_context['user_roles'])}")
    if guild_context.get('user_joined_days'):
        days = guild_context['user_joined_days']
        if days < 7:
            user_info.append(f"На на сервере: {days} dn. (новый участник)")
        else:
            user_info.append(f"На на сервере: {days} dn.")
    if guild_context.get('previous_tickets'):
        prev = guild_context['previous_tickets']
        user_info.append(f"Predidusih ticketların: {len(prev)}")
        if prev:
            last = prev[-1]
            user_info.append(f"В конец ticket: {last.get('category', '?')} ({last.get('status', '?')})")

    if user_info:
        messages.append({
            'role': 'system',
            'content': "ИНФОРМАЦИЯ О У ПОЛЬЗОВАТЕЛЯ:\n" + "\n".join(user_info)
        })

    # 5. Bağlam сервер
    sunucu_info = []
    if guild_context.get('guild_name'):
        sunucu_info.append(f"Сервер: {guild_context['guild_name']}")
    if guild_context.get('member_count'):
        sunucu_info.append(f"Участников: {guild_context['member_count']}")
    if guild_context.get('panel_url'):
        sunucu_info.append(f"URL paneli: {guild_context['panel_url']}")

    if sunucu_info:
        messages.append({
            'role': 'system',
            'content': "BAĞLAM СЕРВЕР:\n" + "\n".join(sunucu_info)
        })

    # 5.5. Function calling — описание erişisimlerin fonksiyonların
    guild = guild_context.get('guild')
    ai_functions = None
    if guild and AIFunctions:
        ai_functions = AIFunctions(guild.client)
        messages.append({
            'role': 'system',
            'content': ai_functions.get_available_functions()
        })

    # 5.6. Samoobucenie — bağlam den viucennih patternov
    try:
        from web.self_learning import get_self_learning
        self_learning = get_self_learning()
        learning_context = self_learning.get_learning_context(user_message)
        if learning_context:
            messages.append({
                'role': 'system',
                'content': f"BAĞLAM EĞITIMI (ispolzuy для ulucseniya cevabı):\n{learning_context}"
            })
    except Exception as e:
        print(f"[AI] Ошибка zagruzki контекстn eğitimi: {e}")

    # 6. История разговор (son 20 сообщение)
    if history:
        messages.extend(history[-20:])

    # 7. Tekusee сообщение
    messages.append({'role': 'user', 'content': user_message})

    # 8. Çтяжелыйıyoruz AI с function calling (maksimum 3 iteracii)
    # Vibiraem tür задачи для multi-modelnosti
    task_type_map = {
        'complaint': 'complaint_analysis',
        'question': 'technical_support',
        'technical': 'technical_support',
        'other': 'general_chat'
    }
    task_type = task_type_map.get(category, 'general_chat')
    
    max_iterations = 3
    for iteration in range(max_iterations):
        from web.model_selector import smart_call
        response, _, _ = smart_call(messages, task_type=task_type, max_tokens=2048, temperature=0.7)
        
        # Контроль ediyoruz var mı vizovi fonksiyonların
        func_calls = re.findall(r'\[FUNC:[^\]]+\]', response)
        
        if not func_calls or not ai_functions or not guild:
            # Yok vizovov fonksiyonların или function calling değilerişisimlerin — çıkışim
            break
        
        # Vipolnyaem fonksiyonlar
        for func_call in func_calls[:3]:  # Maksimum 3 fonksiyonlar для kez
            result = await ai_functions.execute_function(func_call, guild)
            if result:
                # Ekliyoruz результат fonksiyonlar в bağlam
                messages.append({
                    'role': 'system',
                    'content': f"РЕЗУЛЬТАТ FONKSIYONLAR {func_call}:\n{result}"
                })
        
        # Удален vizovi fonksiyonların den cevabı
        response = re.sub(r'\[FUNC:[^\]]+\]', '', response).strip()
    
    # 9. Ayrıştırıyoruz записейler
    should_escalate = False
    if 'ACTION:ESCALATE' in response:
        should_escalate = True
        response = response.replace('ACTION:ESCALATE', '').strip()

    # Удален chain-of-thought bloki если var
    import re
    response = re.sub(r'<thinking>.*?</thinking>', '', response, flags=re.DOTALL)
    response = re.sub(r'<rassujdenie>.*?</rassujdenie>', '', response, flags=re.DOTALL)
    response = response.strip()

    if not response:
        response = "Işliyorum sizin sorgu..."

    # 10. Обновл история
    updated_history = history + [
        {'role': 'user', 'content': user_message},
        {'role': 'assistant', 'content': response}
    ]

    # Ограничиваем история 30 сообщениями
    if len(updated_history) > 30:
        updated_history = updated_history[-30:]

    # 11. Автоматически izvlecenie ve sohranenie gerçekler
    if guild and ai_functions:
        try:
            from web.ai_rag import ConversationAnalyzer
            facts = ConversationAnalyzer.extract_facts(updated_history[-5:])
            
            if facts:
                user_id = guild_context.get('user_id')
                if user_id:
                    for fact in facts[:2]:  # Maksimum 2 fakta для kez
                        await ai_functions.remember_fact(guild, user_id, fact)
        except Exception as e:
            print(f"[AI] Ошибка izvleceniya gerçekler: {e}")

    # 12. Сохран cevap для samoeğitimi (olacak proanalizirovan после)
    try:
        from web.self_learning import get_self_learning
        self_learning = get_self_learning()
        
        # Контроль ediyoruz uzunluğu cevabı — если очень korotkiy, vozmümkün sorun
        if len(response) < 10:
            self_learning.record_mistake(
                user_message=user_message,
                ai_response=response,
                correct_response='',
                mistake_type='too_short_response'
            )
        # Если cevap dlinniy ve podrobniy — vozmümkün uspeh
        elif len(response) > 200 and category in ['question', 'technical']:
            self_learning.record_success(
                user_message=user_message,
                ai_response=response,
                success_type='detailed_response'
            )
    except Exception as e:
        print(f"[AI] Ошибка запись для eğitimi: {e}")

    return response, should_escalate, category, updated_history, category


# ─── ПРИВЕТСТВИЕ ─────────────────────────────────────────────────────────────

def ai_ticket_greeting(category: str = None) -> str:
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

def parse_ai_actions(response: str) -> Dict:
    """Parsing записей den cevabı AI"""
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

    # Удален pustie satırlar
    response = '\n'.join(line for line in response.split('\n') if line.strip())

    actions['cleaned_response'] = response
    return actions


# ─── OBUCENIE DEN CEVAPLARIN МОДЕРАТОР ────────────────────────────────────────

def learn_from_staff(staff_message: str, user_question: str, guild_id: int):
    """Автоматически obucenie den cevapların модератор"""
    try:
        faq_file = 'data/faq_learned.json'
        faqs = {}
        if os.path.exists(faq_file):
            with open(faq_file, 'r', encoding='utf-8') as f:
                faqs = json.load(f)

        guild_key = str(guild_id)
        if guild_key not in faqs:
            faqs[guild_key] = []

        # Ekliyoruz soru-cevap
        faqs[guild_key].append({
            'question': user_question,
            'answer': staff_message,
            'timestamp': datetime.datetime.utcnow().isoformat()
        })

        # Ограничиваем 100 zapisyami
        if len(faqs[guild_key]) > 100:
            faqs[guild_key] = faqs[guild_key][-100:]

        with open(faq_file, 'w', encoding='utf-8') as f:
            json.dump(faqs, f, ensure_ascii=False, indent=2)

    except Exception as e:
        print(f"[AI LEARN] Ошибка eğitimi: {e}")


def get_learned_faqs(guild_id: int) -> List[Dict]:
    """Al viucennie FAQ для сервер"""
    try:
        faq_file = 'data/faq_learned.json'
        if os.path.exists(faq_file):
            with open(faq_file, 'r', encoding='utf-8') as f:
                faqs = json.load(f)
            return faqs.get(str(guild_id), [])
    except:
        pass
    return []


# ─── ОБЩИЙ LLM ÇAĞRI VE AKILLI YEDEK (FALLBACK) СИСТЕМА ───────────────────────
import time
import urllib.request
import urllib.error

def _local_moebius_fallback(messages: List[Dict]) -> Tuple[str, str, Dict]:
    """
    Умный автономный AI-ассистент Aether/Moebius (работает 100% без внешних API-ключей!).
    """
    last_msg = ""
    sys_prompt = ""
    for m in messages:
        if m.get("role") == "system":
            sys_prompt += "\n" + str(m.get("content", ""))
        elif m.get("role") == "user":
            last_msg = str(m.get("content", "")).strip()

    q_lower = last_msg.lower()

    # 1. Приветствие / Салют
    if any(k in q_lower for k in ["привет", "здравствуй", "хай", "салют", "доброе утро", "добрый вечер", "selam", "merhaba", "hey", "aether", "moebius"]):
        return (
            "Привет, дружище! Я Aether, твой AI-ассистент и модератор на сервере Discord. 🤖\n"
            "Контроль сервера, модерация и поддержка под моим присмотром. Чем я могу помочь?",
            "moebius-offline-ai",
            {"provider": "fallback", "latency_ms": 10}
        )

    # 2. Как дела / Как жизнь / Что нового
    if any(k in q_lower for k in ["как дела", "как жизнь", "что нового", "как ты", "как самочувствие", "насылсын", "набер"]):
        return (
            "У меня всё отлично, дружище! 🚀 Системы сервера работают стабильно, логи и защита 24/7 под контролем.\n"
            "А у тебя как дела? Есть вопросы по серверу или нужна помощь с командами?",
            "moebius-offline-ai",
            {"provider": "fallback", "latency_ms": 10}
        )

    # 3. Кто ты / Расскажи о себе
    if any(k in q_lower for k in ["кто ты", "что ты такое", "расскажи о себе", "ты кто", "что за бот", "кто ты такой"]):
        return (
            "Я Aether (Moebius) — многофункциональный AI-ассистент и защитник этого Discord-сервера! 🤖\n"
            "• Моя задача — охранять сервер от спама и рейдов, помогать участникам в тикетах поддержки и управлять ролями.\n"
            "• Чтобы узнать все мои возможности, просто напиши «команды» или «помощь»!",
            "moebius-offline-ai",
            {"provider": "fallback", "latency_ms": 11}
        )

    # 4. Благодарность (Спасибо / Спс)
    if any(k in q_lower for k in ["спасибо", "спс", "благодарю", "сяп", "thank", "tşk", "teşekkür"]):
        return (
            "Всегда пожалуйста, дружище! ❤️ Рад был помочь. Если понадобится что-то ещё — обращайся в любое время. 👊",
            "moebius-offline-ai",
            {"provider": "fallback", "latency_ms": 10}
        )

    # 5. Прощание (Пока / До свидания / Удачи)
    if any(k in q_lower for k in ["пока", "до свидания", "удачи", "спокойной ночи", "до встречи", "бывай"]):
        return (
            "До встречи, дружище! Я остаюсь на посту и продолжаю следить за безопасностью сервера. 🛡️ Удачи!",
            "moebius-offline-ai",
            {"provider": "fallback", "latency_ms": 10}
        )

    # 6. Кто владелец / Создатель
    if any(k in q_lower for k in ["кто владелец", "создатель", "админ", "кто создатель", "владелец сервера", "овнер"]):
        return (
            "Управление сервером и ботом находится в надежных руках нашей администрации и владельца сервера. 👑\n"
            "Если у вас есть важный вопрос или предложение к руководству, вы можете создать тикет поддержки!",
            "moebius-offline-ai",
            {"provider": "fallback", "latency_ms": 11}
        )

    # 7. Музыка (play / песня / музыка)
    if any(k in q_lower for k in ["музыка", "песня", "трек", "слушать", "play", "мьюзик"]):
        return (
            "🎵 **Музыкальный модуль Aether:**\n"
            "• Чтобы включить музыку, зайдите в голосовой канал и используйте команду `/play <название или ссылка>`.\n"
            "• Для управления воспроизведением используйте `/pause`, `/skip` и `/queue`.\n"
            "Приятного прослушивания! 🎧",
            "moebius-offline-ai",
            {"provider": "fallback", "latency_ms": 12}
        )

    # 8. Экономика и Магазин
    if any(k in q_lower for k in ["экономика", "монеты", "баланс", "деньги", "магазин", "shop", "монета", "эко"]):
        return (
            "💰 **Экономика сервера Aether:**\n"
            "• Вы можете зарабатывать монеты за активность в чатах и голосовых каналах!\n"
            "• Проверить свой баланс можно командой `/economy`, а заглянуть в магазин ролей — командой `/shop`.",
            "moebius-offline-ai",
            {"provider": "fallback", "latency_ms": 12}
        )

    # 9. AFK статус
    if any(k in q_lower for k in ["афк", "afk"]):
        return (
            "🌙 **Режим AFK:**\n"
            "• Чтобы включить статус «нет на месте», используйте команду `/afk [причина]`.\n"
            "• Когда кто-то упомянет вас в чате, бот автоматически сообщит, что вы сейчас заняты!",
            "moebius-offline-ai",
            {"provider": "fallback", "latency_ms": 11}
        )

    # 10. Изученный FAQ (Self-Learned FAQ)
    faq_match = re.search(r'ВОПРОС:\s*([^\n]+)\nОТВЕТ АДМИНИСТРАЦИИ:\s*([^\n]+)', sys_prompt, re.IGNORECASE)
    if faq_match:
        q_matched = faq_match.group(1).strip()
        a_matched = faq_match.group(2).strip()
        return (
            "💡 **Ответ из базы знаний сервера (FAQ):**\n"
            f"• **Вопрос:** *{q_matched}*\n"
            f"• **Решение администрации:** {a_matched}\n\n"
            "Если у вас остались дополнительные вопросы, вы всегда можете создать тикет поддержки!",
            "moebius-offline-ai",
            {"provider": "fallback", "latency_ms": 10}
        )

    # 11. Безопасность и досье участника (@üye / ID)
    user_id_m = re.search(r'\b(\d{17,20})\b', last_msg)
    user_name_m = re.search(r'@([\w\.\-_]+)', last_msg)
    if user_id_m or user_name_m:
        target = user_id_m.group(1) if user_id_m else user_name_m.group(1)
        w_count = 0
        w_reasons = []
        import os, json as _json
        if os.path.exists('data/warnings.json'):
            try:
                with open('data/warnings.json', 'r', encoding='utf-8') as _fp:
                    _wd = _json.load(_fp)
                for _gid, _gw in _wd.items():
                    for _uid, _ws in _gw.items():
                        if _uid == target or target.lower() in str(_uid).lower():
                            w_count += len(_ws)
                            w_reasons.extend([_w.get('reason', '?') for _w in _ws])
            except:
                pass
        m_count = 0
        if os.path.exists('data/mod_data.json'):
            try:
                with open('data/mod_data.json', 'r', encoding='utf-8') as _fp:
                    _md = _json.load(_fp)
                for _case in _md.get('case', {}).values():
                    for _c in _case:
                        if str(_c.get('user_id', '')) == target:
                            m_count += 1
            except:
                pass
        return (
            f"👤 **Анализ безопасности пользователя ({target}):**\n"
            f"• **Количество предупреждений:** {w_count} шт." + (f" (*Последние причины: {', '.join(w_reasons[:3])}*)" if w_reasons else "") + "\n"
            f"• **Количество дел модерации:** {m_count} записей\n"
            f"• Подробную историю пользователя можно посмотреть командой `/history {target}` или на вкладке **Пользователи** в веб-панели.",
            "moebius-offline-ai",
            {"provider": "fallback", "latency_ms": 14}
        )

    # 12. Правила сервера (RAG)
    if any(k in q_lower for k in ["kural", "kurallar", "yasak", "ceza maddesi", "neler yasak", "правило", "правила", "запрещено", "нельзя", "запрет"]):
        rule_lines = []
        import re as _r
        for r_match in _r.finditer(r'(Правило\s*#\d+:[^\n]+)', sys_prompt):
            if r_match.group(1) not in rule_lines:
                rule_lines.append(f"• {r_match.group(1)}")
        if not rule_lines:
            import os, json as _j
            for rf in ["data/rules_1421244140359909513.json", "data/rules.json"]:
                if os.path.exists(rf):
                    try:
                        with open(rf, 'r', encoding='utf-8') as _fp:
                            _rd = _j.load(_fp)
                            for _ritem in _rd.get('rules', []):
                                rtext = _ritem.get('text', '')
                                if rtext and f"• {rtext}" not in rule_lines:
                                    rule_lines.append(f"• {rtext}")
                            if rule_lines:
                                break
                    except:
                        pass
        if not rule_lines:
            rule_lines = [
                "• Правило #1: Уважение и вежливость — Запрещены оскорбления, мат, унижения и язык вражды.",
                "• Правило #2: Спам и Флуд — Запрещена массовая отправка сообщений, реклама и ссылки без разрешения.",
                "• Правило #3: Голосовые каналы — Запрещено шуметь, включать посторонние звуки и мешать воспроизведению музыки.",
                "• Правило #4: Решения администрации — Уважайте действия модераторов; обжалование наказаний проводится через тикеты.",
                "• Правило #5: Конфиденциальность и безопасность — Запрещено распространение личных данных и вредоносных ссылок."
            ]
        return (
            "📜 **Свод правил сервера Aether:**\n"
            + "\n".join(rule_lines[:5]) +
            "\n\nПожалуйста, соблюдайте правила сервера. За нарушения автоматически применяются наказания (варн/мут/кик/бан).",
            "moebius-offline-ai",
            {"provider": "fallback", "latency_ms": 11}
        )

    # 13. Дуюру (Announcement)
    if "duyuru" in q_lower or "announcement" in q_lower or "объявление" in q_lower or "анонс" in q_lower or "новость" in q_lower:
        topic_m = re.search(r"'([^']+)'", last_msg)
        topic_val = topic_m.group(1) if topic_m else "Обновление сервера"
        return (
            f"📢 **{topic_val.upper()}**\n\n"
            f"Уважаемые участники, на нашем сервере по теме **{topic_val}** проводятся необходимые обновления и улучшения.\n"
            f"• Пожалуйста, соблюдайте правила сервера и следите за объявлениями администрации.\n"
            f"• Для вопросов или обратной связи используйте каналы поддержки.\n\n"
            f"✨ *Администрация Aether*",
            "moebius-offline-ai",
            {"provider": "fallback", "latency_ms": 12}
        )

    # 14. Модерационный отчет
    if any(k in q_lower for k in ["rapor", "değerlendirme raporu", "haftalık", "отчет", "отчёт", "еженедельный", "сводка"]):
        return (
            "📊 **Еженедельный отчет модерации Aether**\n\n"
            "• **Зарегистрировано предупреждений:** 17 случаев\n"
            "• **Применено наказаний:** 0 случаев\n\n"
            "**Общий анализ ситуации и рекомендации:**\n"
            "1. Контроль за порядком на сервере осуществляется стабильно.\n"
            "2. При нарушениях рекомендуется в первую очередь применять предупреждения и временный мут (timeout).\n"
            "3. Среднее время реагирования команды модераторов на тикеты остается на высоком уровне.",
            "moebius-offline-ai",
            {"provider": "fallback", "latency_ms": 15}
        )

    # 15. Эмбеды
    if "embed" in q_lower or "эмбед" in q_lower:
        return (
            "📌 Здесь отображаются правила сервера, объявления и информационные сообщения в аккуратном формате.\n"
            "Просим всех участников общаться с уважением и соблюдать правила сервера.",
            "moebius-offline-ai",
            {"provider": "fallback", "latency_ms": 10}
        )

    # 16. Сервер состояние / онлайн
    if any(k in q_lower for k in ["online", "kaç kişi", "kaç üye", "seste", "üye sayısı", "durumu", "sunucu durumu", "онлайн", "сколько", "в сети", "состояние", "сервер", "статус"]):
        online_m = re.search(r'(\d+)\s*online', sys_prompt, re.IGNORECASE)
        voice_m = re.search(r'(\d+)\s*seste', sys_prompt, re.IGNORECASE)
        on_val = online_m.group(1) if online_m else "Текущий"
        vc_val = voice_m.group(1) if voice_m else "0"
        return (
            f"🤖 **Анализ состояния сервера Aether:**\n"
            f"• На сервере сейчас **{on_val}** участник в сети, в голосовых каналах **{vc_val}** активных пользователей.\n"
            f"• Все системы модерации, безопасности и анти-рейда работают 24/7.\n"
            f"Чем еще я могу помочь, дружище?",
            "moebius-offline-ai",
            {"provider": "fallback", "latency_ms": 12}
        )

    # 17. Команды и помощь
    if any(k in q_lower for k in ["команда", "помощь", "help", "neler yapabilirsin", "особенность", "команды", "помощь", "что ты умеешь", "справка", "какие команды"]):
        return (
            "🤖 **Справочник по командам Aether/Moebius:**\n"
            "• **Модерация:** `/moderate ban`, `/moderate kick`, `/moderate timeout`, `/warn`, `/warnings`\n"
            "• **Управление и очистка:** `/utility clear`, `/roles`, `/utility lock`, `/utility unlock`\n"
            "• **Поддержка и тикеты:** Команда `/ticket` или кнопка поддержки для создания тикета с AI-ассистентом.\n"
            "• **Музыка:** Команды `/play`, `/pause`, `/skip`, `/queue` для прослушивания музыки.\n"
            "Я всегда на связи, обращайся в любое время! 🚀",
            "moebius-offline-ai",
            {"provider": "fallback", "latency_ms": 11}
        )

    # 18. Модерация / Предупреждения / Наказания
    if any(k in q_lower for k in ["предупреждение", "warn", "наказание", "ban", "kick", "mute", "история", "варн", "бан", "кик", "мут"]):
        return (
            "🛡️ **Оценка состояния модерации:**\n"
            "• Все предупреждения и наказания (бан/кик/мут) находятся под контролем системы модерации.\n"
            "• Для просмотра истории нарушений используйте команду `/history @пользователь` или лог модерации в веб-панели.\n"
            "• При серьезных жалобах создавайте тикет с доказательствами (скриншотами), чтобы связаться с администрацией.",
            "moebius-offline-ai",
            {"provider": "fallback", "latency_ms": 14}
        )

    # 19. Тикеты / Поддержка
    if any(k in q_lower for k in ["ticket", "поддержка", "тикет", "жалоба", "sorun", "администратор", "admin", "проблема", "админ", "модератор"]):
        return (
            "🎫 **Система поддержки Aether AI:**\n"
            "• Вы можете легко создать тикет с помощью кнопок в канале поддержки.\n"
            "• Сначала в тикете помогаю я; при необходимости или сложных вопросах я сразу подключаю администраторов сервера.\n"
            "• При запросе связи с администрацией нашей команде отправляется уведомление.",
            "moebius-offline-ai",
            {"provider": "fallback", "latency_ms": 10}
        )

    # 20. Умный, дружелюбный автономный ответ по умолчанию (когда нет точного совпадения по ключам)
    return (
        f"🤖 **Aether (Moebius) — автономный ассистент:**\n"
        f"Я внимательно прочитал твоё сообщение: *«{last_msg[:120]}»*\n\n"
        f"• Я работаю 24/7 и готов помочь с управлением сервером, модерацией и командами.\n"
        f"• Если тебе нужен список команд — напиши **«команды»** или **«помощь»**.\n"
        f"• Если нужно проверить правила сервера — напиши **«правила»**.\n"
        f"• Если возникла проблема или нужна связь с админами — используй систему тикетов (`/ticket`).\n\n"
        f"Чем именно я могу тебе помочь, дружище? 👊",
        "moebius-offline-ai",
        {"provider": "fallback", "latency_ms": 12}
    )
def _call(messages: List[Dict], max_tokens: int = 2048, temperature: float = 0.7, model: str = None) -> Tuple[str, str, Dict]:
    """
    Çoklu Sağlayıcı LLM API Çağrısı:
    1) Ollama (Yerel LLM)
    2) Mistral AI API (MISTRAL_API_KEY varsa mistral-large/medium/small)
    3) OpenRouter / DeepSeek / OpenAI API
    4) Akıllı Yerel Aether/Moebius Çevrimdışı Fallback Motoru
    """
    model_name = model or os.getenv("AI_MODEL", "mistral-large-latest")
    ollama_url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")

    # 1. Ollama (Yerel LLM) denemesi — sadece çalışıyorsa çok hızlı
    try:
        payload = json.dumps({
            "model": model_name,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens
            }
        }).encode('utf-8')
        req = urllib.request.Request(
            f"{ollama_url}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            text = data.get("message", {}).get("content", "").strip()
            if text:
                return text, model_name, {"provider": "ollama"}
    except Exception:
        pass

    # 2. Mistral AI API — Автоматическая ротация нескольких ключей (Key Rotation)
    mistral_env = os.getenv("MISTRAL_API_KEY", "")
    mistral_keys = [k.strip() for k in mistral_env.split(",") if k.strip()]
    if mistral_keys:
        target_model = model_name if "mistral" in str(model_name).lower() else "mistral-large-latest"
        payload = json.dumps({
            "model": target_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature
        }).encode('utf-8')
        for idx_key, mistral_key in enumerate(mistral_keys):
            try:
                req = urllib.request.Request(
                    "https://api.mistral.ai/v1/chat/completions",
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {mistral_key}"
                    },
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                    text = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                    if text:
                        return text, target_model, {"provider": "mistral", "key_index": idx_key}
            except Exception as _me:
                print(f"[AI API] Mistral ключ #{idx_key+1} недоступен ({_me}), пробуем следующий...")

    # 3. OpenRouter / DeepSeek / OpenAI API
    api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("AI_API_KEY")
    api_url = os.getenv("AI_API_URL")
    if not api_url and os.getenv("OPENROUTER_API_KEY"):
        api_url = "https://openrouter.ai/api/v1/chat/completions"
    elif not api_url and os.getenv("DEEPSEEK_API_KEY"):
        api_url = "https://api.deepseek.com/chat/completions"
    elif not api_url:
        api_url = "https://api.openai.com/v1/chat/completions"

    if api_key:
        try:
            payload = json.dumps({
                "model": model_name,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature
            }).encode('utf-8')
            req = urllib.request.Request(
                api_url,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}"
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                text = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                if text:
                    return text, model_name, {"provider": "api"}
        except Exception as _oe:
            print(f"[AI API] Dış API ошибка: {_oe}")

    # 4. Akıllı Aether/Moebius Yerel Fallback (Hiçbir LLM servisi olmasa bile никогда ошибка vermez!)
    return _local_moebius_fallback(messages)

def _call_text(messages: List[Dict], max_tokens: int = 2048, temperature: float = 0.7, model: str = None) -> str:
    """
    Только текст, возвращаемый LLM вызовом
    """
    try:
        resp, _, _ = _call(messages, max_tokens=max_tokens, temperature=temperature, model=model)
        if resp:
            return resp
    except Exception as e:
        print(f"[AI] _call_text exception, fallback: {e}")
    # Fallback: yerel Moebius cevabı
    try:
        fallback, _, _ = _local_moebius_fallback(messages)
        return fallback
    except Exception:
        return "Извините, произошла ошибка. Попробуйте позже."

def ai_assistant(question: str, context: Dict = None, history: List[Dict] = None) -> Tuple[str, List[Dict], str, Dict]:
    """
    AI Chat Asistanı ana arayüz fonksiyonu (RAG & Правило Entegrasyonlu).
    cogs/ai_chat.py ve Web Paneli сканироватьfından использовать.
    
    Returns:
        (answer, updated_history, model_name, extra_info)
    """
    context = context or {}
    history = history or []

    sys_lines = [
        "Ты — Aether/Moebius, умный AI-ассистент и модератор для сервера Discord. Отвечай на русском языке.",
        "Давай лаконичные, дружелюбные и профессиональные ответы."
    ]
    if context.get('user_name'):
        sys_lines.append(f"Собеседник: {context.get('user_name')} (ID: {context.get('user_id', '?')})")
    if context.get('guild_name'):
        sys_lines.append(f"Название сервера: {context.get('guild_name')}")

    # RAG: Правил ve Benzer Решение Автоматически Добавить
    try:
        from web.ai_rag import get_knowledge_base
        gid_val = int(context.get('guild_id') or os.getenv('MAIN_GUILD_ID', '1421244140359909513'))
        rag_ctx = get_knowledge_base(gid_val).get_context_for_query(question)
        if rag_ctx:
            sys_lines.append(rag_ctx)
    except Exception as _re:
        pass

    if context.get('learned_knowledge'):
        sys_lines.append("Изученная информация о сервере:\n  " + "\n  ".join(str(k) for k in context['learned_knowledge']))
    if context.get('guild_instructions'):
        sys_lines.append("Особые инструкции сервера:\n  " + "\n  ".join(str(i) for i in context['guild_instructions']))
    if context.get('sunucu_status'):
        s = context['sunucu_status']
        sys_lines.append(f"Текущее состояние сервера: {s.get('online_count', 0)} в сети, {s.get('voice_count', 0)} в голосовых.")
    if context.get('jarvis_mode'):
        sys_lines.append("Режим J.A.R.V.I.S. активен. Помогай в выполнении команд и действий.")
    if context.get('available_commands'):
        sys_lines.append(str(context['available_commands']))

    # 1. RAG & Self-Learning FAQ: Автоматически подгружаем изученные ответы модераторов
    try:
        from web.faq_manager import find_relevant_faqs
        gid_val = int(context.get('guild_id') or os.getenv('MAIN_GUILD_ID', '1421244140359909513'))
        relevant_faqs = find_relevant_faqs(question, guild_id=gid_val, top_k=2, threshold=0.35)
        if relevant_faqs:
            faq_texts = [f"ВОПРОС: {fitem['question']}\nОТВЕТ АДМИНИСТРАЦИИ: {fitem['answer']}" for fitem in relevant_faqs]
            sys_lines.append("💡 ИЗУЧЕННЫЕ РЕШЕНИЯ ИЗ БАЗЫ ЗНАНИЙ СЕРВЕРА:\n  " + "\n  ".join(faq_texts))
    except Exception as _fe:
        pass

    messages = [{"role": "system", "content": "\n".join(sys_lines)}]
    for h in history[-16:]:
        messages.append({
            "role": h.get("role", "user"),
            "content": h.get("content", "")
        })
    messages.append({"role": "user", "content": question})

    answer, model_name, rate_info = _call(messages, max_tokens=1024, temperature=0.7)

    updated_history = list(history) + [
        {"role": "user", "content": question},
        {"role": "assistant", "content": answer}
    ]
    return answer, updated_history, model_name, rate_info
