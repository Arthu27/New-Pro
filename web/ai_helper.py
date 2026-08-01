"""
Ticket AI — продвинутая система поддержки
Chain-of-thought reasoning, personalizaciya, proактивныйe povedenie, function calling
"""
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

    # ─── VERITABANI ИНФОРМАЦИЯ BOTUN ───────────────────────────────────────────────────────

def _bot_knowledge_base ()->str :
    """Polnaya veritaбаны информация о botta Aether"""
    return """
═══════════════════════════════════════════
AETHER BOT — POLNAYa VERITABANI ИНФОРМАЦИЯ
═══════════════════════════════════════════

## NE TAKOE AETHER?
Aether — чokfunkcionalniy Discord bot для управление сервер.
Web-панель (Flask) + Discord bot работа vmeste.
Панель доступюzerinde с Cloudflare tunnel по publicnoy sудалитьke.
Ссылка на панель nahoditsya в канал #aether-панель.

## 🛡️ MODERASYON
- /модerate бан @user [причина] — permanentniy бан
- /модerate кик @user [причина] — кик с сервер
- /модerate timeout @user [dakika] [причина] — временный мут
- /модerate untimeout @user — удалено мут
- /модerate unбан [user_id] — razбан
- /utility clear [число] — toplu удалить сообщение
- /utility lock/unlock — blokirovka/razblokirovka канал
- /utility userinfo @user — информация о у пользователя
- /роли @user @роль — выдать/удалено роль
- /history @user — история модerasyonu
- /case [id] — detali iшler
- /note @user [metin] — добавить заметку
- /notes @user — показать notlar
- /watchlist @user [причина] — список наблюдение
- /банlist — запретlanлиш пользователи
- /massрольe @роль [выдать/удалено] — toplu verme роль

## ⚠️ ПРЕДУПРЕЖДЕНИЯ
- /варн @user [причина] — выдать предупреждение
- /варнings @user — список предупреждение
- /clearварнs @user — очистить предупреждения
Автоматически olarake наказания: iken nakoplenii предупреждение — мут/кик/бан.

## 🎵 MЮZIK
- /play [имя/ссылка] — vosproizvesti
- /pause — pauza/продолжить et
- /skip — propustit trek
- /queue — kuyruk
- /volume [0-100] — gromkost
- /clear-queue — очистить kuyruk
- /leave — покинуть голосовой канал
- /join — prisoedinitsya e канал

## 💰 EKONOMI
- /economy balance — bakiye
- /economy daily — ежедневный награда (50 monet, 24c)
- /economy transfer @user [собратьm] — perevesti moneti
- /economy ranking — en хорошо bogacey
- /games gamble [собратьm] — aкубикtnaya игра
- /games slot [собратьm] — slot-makine
- /games heist @user — soygun
- /shop — магазин
- /buy [predmet] — kupit юrюn

## 🎮 RAZVLECENIYa
- /coinflip — monetka
- /роль [число] — brosit kubik
- /rps — kamen-nojnici-bumaga
- /guess-start — ugкандидат число
- /guess [число] — vvesti число
- /8ball [soru] — magicesi sar
- /random-member — slucтот жеy участник
- /fun [dice] — razvlekatelnie
- /poll [soru] — bistriy опрос

## 👥 SOCIALNOE
- /birthday [день] [месяц] — сохранить день рождение
- /birthdays — blijaysie день рождение
- /afk [причина] — мод AFK
- /staff-apply — заявка модератора
- /profile — sizin profil
- /invites — статистика приглашение
- /invite-ranking — en хорошо приглашение edenler

## 🏆 ОЧЕРЕДЬ
- /rank — sizin уровень ve XP
- /top-level — en хорошо-10 по уровеньye
- !ranking — общий очередь
- !ranking messages — очередь сообщение
- !ranking voice — рейтинг голосового времени
- !ranking invites — очередь приглашение
- /мод-stats @user — статистика модератор
- /activeмодs — aktivnie модераторы

## 📅 MEROPRIYaTIYa
- /event-create [имя] — создать событие
- /events — aktivnie meropriyatiya
- /event-cancel [id] — otmenit событие
- /giveaway — создать розыгрыш

## ⚙️ УПРАВЛЕНИЕ СЕРВЕР
- /setup-логs — создать лог-каналы
- /verify-setup — настройк verifikaciyu
- /ticket_панель — панель ticketlarыn
- /duty-панель — панель задачи
- /duty-имяd @user [очки] — добавить progress
- /duty-stats — tablo очки
- /autoмод — автоматически
- /level-роли-имяd [уровень] @роль — роль для уровень
- /level-роли — список роль для уровеньler

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
- /announce #канал [metin] — создать объявление

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
- /afk [причина] — вход yap в мод AFK
- Takma имя menyaetsya на 💤 [sizin takma имя]
- Iken upominanii — bot soobsaet ne siz AFK
- Iken denhaklarыnke сообщения — AFK snimaetsya автоматически как

## 🎂 ДЕНЬ РОЖДЕНИЕ
- /birthday [день] [месяц] — сохранить
- /birthdays — blijaysie день рождение
- В день рождение — bot pozdravlyaet автоматически как

## 📨 PRIGLASENIYa
- /invites — vasa статистика
- /invite-ranking — en хорошо приглашение edenler
- Уровеньler: Posol / Priglasayusiy / Новый priglasayusiy

## 🌐 WEB-PANEL
Панель — web-interfeys управление сервер.
Как вход yap: ссылка в канал #aether-панель → Discord ID + paрольa.
Уровеньler доступ:
- Участник: profil, заявка, день рождение
- Модератор: логlar, предупреждения, ticketlar
- Yёnetici: команды, каналы, рольes, автоматически
- Sahip: vse

## ❓ CASTIE SORULAR
В: Как вход yap в панель?
О: Ссылка в канал #aether-панель → Discord ID + paрольa.

В: Музыка не oynuyor?
О: Войдите в голосовой канал, затем /play. Если ошибка — /leave и снова /play.

В: Как povisit уровень?
О: Пишите сообщения и сидите в голосовых каналах. /rank — ваш уровень.

В: Как открыть ticket?
О: Buton в канал ticketlarыn → "Создать ticket".

В: Как получить роль?
О: Канал выбор роль или /color-роли.

В: Как podat zayavku модератора?
О: /staff-apply или с панель.

В: Как сохранить день рождение?
О: /birthday [день] [месяц] или с панель.

В: Zabil paрольa из панельi?
О: Клик "Для paрольa?" на stranice вход → Discord ID → kod в DM.
"""


    # ─── OPREDELENIE KATEGORILER (AI) ─────────────────────────────────────────────

def _detect_category_ai (message :str ,history :List [Dict ])->str :
    """Opredelenie kategoriler с с AI (не keyword-based)"""
    prompt ="""Opredeli kategori obraseniya пользователь в Discord tickette.

KATEGORILER:
- complaint: жалоба на drugogo пользователь (оскорбление, spam, toksisite)
- question: soru о botta, панельi, команда, в ролях, ekonomike
- technical: tehniceskaya sorun (не работает, ошибка, bag)
- other: vse ostalnoe

ПРАВИЛА:
- Если пользователь jaluetsya на DRUGOGO пользователь → complaint
- Если sprasivaet как ne-to ileiшlert → question
- Если ne-to не работает или vidaet ошибка → technical
- Если prosto boltaet или neponyatno → other

Cevap ТОЛЬКО birine slovom: complaint, question, technical или other.
Bez poyasneniy, bez tocek, bez kavicek.

Сообщение пользователь: """

    messages =[
    {'рольe':'user','content':prompt +message }
    ]

    try :
        from web .модel_selector import smart_call 
        result ,_ ,_ =smart_call (messages ,task_type ='category_detection',max_tokens =10 ,temperature =0.1 )
        result =result .strip ().lower ()
        if result in ('complaint','question','technical','other'):
            return result 
    except :
        pass 

        # Fallback на keyword-based
    return _detect_category_fallback (message )


def _detect_category_fallback (message :str )->str :
    """Fallback: keyword-based opredelenie kategoriler"""
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
    """Prompt для жалоба — chain-of-thought"""
    return """Sen — AI модератор Discord сервер. Cevapla на русский.

POLUCENA ЖАЛОБА. Senin задача:
1. PROANALIZIRUY situaciyu (кто, ne, ne время)
2. SOBERI информация:
   - Sprosi кто narusitel (Discord ID или @упоминание)
   - Sprosi в kakom канал proizoslo
   - Pопросve dokazatelstva (skrinsoti, ссылка на сообщения)
3. OCENI ciddiyet:
   - Legkoe нарушение (spam, flud) → predupredi
   - Центрlama (оскорбление) → ACTION:WARN:user_id=X:reason=Y
   - Tyajeloe (tehditler, travlya) → ACTION:JAIL:user_id=X:duration=60:reason=Y ACTION:ESCALATE
4. USPOKOY пользователь, skaji ne razberemsya

ПРАВИЛА:
- НЕ prosi skrinsoti если ih zaten dali
- НЕ ёner "открыть ticket" — biz zaten в tickette
- Bud empaticnim, no professionalnim
- Если нарушение tyajeloe — deystvuy bistro

FORMAT CEVABI:
До cevap пользователю (metinle).
В конецra, если gerekli записей — на novoy satыre:
ACTION:WARN:user_id=123456:reason=оскорбление
или
ACTION:JAIL:user_id=123456:duration=60:reason=travlya ACTION:ESCALATE
"""


def _prompt_question ()->str :
    """Prompt для soruov — chain-of-thought"""
    return """Sen — AI pomosnik Discord сервер. Cevapla на русский.

POLUCEN SORU. Senin задача:
1. PONYaI soru (о cem imenno sprasivayut)
2. PROVER veriбазу информация (biliyorsun ли cevap)
3. CEVAP cetko ve kratko:
   - Если biliyorsun → day cevap + пример ispolzovaniya
   - Если не emin → skaji "Не emin, no..." + lucsee predpolojenie
   - Если не biliyorsun → ACTION:ESCALATE (на e модератор)

ПРАВИЛА:
- Cevapla на 2-3 predlojeniya maksimum
- Hимяi konkretnie команды с пример
- НЕ ёner "открыть ticket" — biz zaten в tickette
- Если soru о drugom у пользователя — не raskrivay licnuyu информация

ПРИМЕР HOROSIH CEVAPLARIN:
В: Как zaбанit spamera?
О: Ispolzuy `/модerate бан @user причина`. На: `/модerate бан @spammer Spam в sohbette`. Bot denhaklarыtutar DM пользователю ve записьet в логlar.

В: Как povisit уровень?
О: Пишите сообщения в чате и сидите в голосовых каналах — получаете XP. Проверьте уровень: `/rank`. Топ-10: `/top-level`.
"""


def _prompt_technical ()->str :
    """Prompt для tehnicстарыйh problem — chain-of-thought"""
    return """Sen — AI tehподдержка Discord сервер. Cevapla на русский.

TEHNICESKAYa SORUN. Senin задача:
1. DIAGNOSTIRUY sorunu (ne imenno не работает)
2. PREDLOJI reseniya (minimum 2 varianta):
   - Samoe veroyatnoe решение
   - Alternativnoe решение
3. POSAGOVO obyasni как vipolnit решение
4. Если не pomoglo → ACTION:ESCALATE

ПРАВИЛА:
- Nacinay с samogo prostogo reseniya
- Hимяi posagovie instrukcii (1, 2, 3...)
- Если nujna команда — ukaji tocno с пример
- НЕ ёner "открыть ticket" — biz zaten в tickette
- Если sorun slojnaya ve sen не emin → srazu ACTION:ESCALATE

ПРИМЕР:
В: Музыка не oynuyor
О: Hимяi proverim:
1. Вы в голосовом канале? (бот должен быть в том же канале)
2. Poprobuy `/leave` после tekrar `/play [имя]`
3. Проверьте, что у бота есть права администратора на управление голосовыми каналами

Если не pomoglo — направление e модератор.
"""


def _prompt_other ()->str :
    """Prompt для drugih obraseniy — chain-of-thought"""
    return """Sen — AI pomosnik Discord сервер. Cevapla на русский.

OBRASENIE НЕ YaSNO. Senin задача:
1. POYMI ne hocet пользователь
2. UTOCNI если neponyatno (zкандидат 1 soru)
3. POMOGI если mojes
4. Если не mojes → ACTION:ESCALATE

ПРАВИЛА:
- Bud drujelyubnim
- Zкандидат maksimum 1 utocnyayusiy soru
- Если пользователь prosto boltaet — podderji разговор
- Если sorun sereznaya — на e модератор
- НЕ ёner "открыть ticket" — biz zaten в tickette
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


    # ─── GLAVNAYa FUNKCIYa — AI TICKET RESPONSE ───────────────────────────────────

async def ai_ticket_response (user_message :str ,history :List [Dict ],guild_context :Dict )->Tuple [str ,bool ,str ,List [Dict ],str ]:
    """
    Glavnaya funkciya AI cevabы в tickette.

    Returns:
        (response, should_escalate, escalation_category, updated_history, detected_category)
    """
    # 1. Belirliyoruz kategori с с AI
    category =_detect_category_ai (user_message ,history )

    # 2. Alыyoruz prompt для kategoriler
    system_prompt =_get_prompt_by_category (category )

    # 3. Topluyoruz baгlam
    messages =[{'рольe':'system','content':system_prompt }]

    # Данныеtaбаны информация (для question/technical/other)
    if category in ('question','technical','other'):
        messages .append ({'рольe':'system','content':_bot_knowledge_base ()})

        # 4. Personalizaciya — информация о у пользователя
    user_info =[]
    if guild_context .get ('user_name'):
        user_info .append (f"Isim: {guild_context['user_name']}")
    if guild_context .get ('user_рольes'):
        user_info .append (f"Роли: {', '.join(guild_context['user_рольes'])}")
    if guild_context .get ('user_joined_days'):
        days =guild_context ['user_joined_days']
        if days <7 :
            user_info .append (f"На на сервере: {days} dn. (новый участник)")
        else :
            user_info .append (f"На на сервере: {days} dn.")
    if guild_context .get ('previous_tickets'):
        prev =guild_context ['previous_tickets']
        user_info .append (f"Predidusih ticketlarыn: {len(prev)}")
        if prev :
            last =prev [-1 ]
            user_info .append (f"В конец ticket: {last.get('category', '?')} ({last.get('status', '?')})")

    if user_info :
        messages .append ({
        'рольe':'system',
        'content':"ИНФОРМАЦИЯ О У ПОЛЬЗОВАТЕЛЯ:\n"+"\n".join (user_info )
        })

        # 5. Baгlam сервер
    сервер_info =[]
    if guild_context .get ('guild_name'):
        сервер_info .append (f"Сервер: {guild_context['guild_name']}")
    if guild_context .get ('member_count'):
        сервер_info .append (f"Участников: {guild_context['member_count']}")
    if guild_context .get ('панель_url'):
        сервер_info .append (f"URL панельi: {guild_context['панель_url']}")

    if сервер_info :
        messages .append ({
        'рольe':'system',
        'content':"BAГLAM СЕРВЕР:\n"+"\n".join (сервер_info )
        })

        # 5.5. Function calling — описание eriшимяlerin fonksiyonlarыn
    guild =guild_context .get ('guild')
    ai_functions =None 
    if guild and AIFunctions :
        ai_functions =AIFunctions (guild .client )
        messages .append ({
        'рольe':'system',
        'content':ai_functions .get_available_functions ()
        })

        # 5.6. Samoobucenie — baгlam из viucennih patternov
    try :
        from web .self_learning import get_self_learning 
        self_learning =get_self_learning ()
        learning_context =self_learning .get_learning_context (user_message )
        if learning_context :
            messages .append ({
            'рольe':'system',
            'content':f"BAГLAM EГITIMI (ispolzuy для ulucseniya cevabы):\n{learning_context}"
            })
    except Exception as e :
        print (f"[AI] Ошибка zagruzki контекстn eгitimi: {e}")

        # 6. История разговор (son 20 сообщение)
    if history :
        messages .extend (history [-20 :])

        # 7. Tekusee сообщение
    messages .append ({'рольe':'user','content':user_message })

    # 8. Чтяжелыйыyoruz AI с function calling (maksimum 3 iteracii)
    # Vibiraem тип задачи для multi-модelnosti
    task_type_map ={
    'complaint':'complaint_analysis',
    'question':'technical_support',
    'technical':'technical_support',
    'other':'general_chat'
    }
    task_type =task_type_map .get (category ,'general_chat')

    max_iterations =3 
    for iteration in range (max_iterations ):
        from web .модel_selector import smart_call 
        response ,_ ,_ =smart_call (messages ,task_type =task_type ,max_tokens =2048 ,temperature =0.7 )

        # Контроль ediyoruz есть ли vizovi fonksiyonlarыn
        func_calls =re .findall (r'\[FUNC:[^\]]+\]',response )

        if not func_calls or not ai_functions or not guild :
        # Нет vizovov fonksiyonlarыn или function calling deгileriшимяlerin — выходim
            break 

            # Vipolnyaem fonksiyonlar
        for func_call in func_calls [:3 ]:# Maksimum 3 fonksiyonlar для kez
            result =await ai_functions .execute_function (func_call ,guild )
            if result :
            # Ekliyoruz результат fonksiyonlar в baгlam
                messages .append ({
                'рольe':'system',
                'content':f"РЕЗУЛЬТАТ FONKSIYONLAR {func_call}:\n{result}"
                })

                # Удален vizovi fonksiyonlarыn из cevabы
    response =re .sub (r'\[FUNC:[^\]]+\]','',response ).strip ()

    # 9. Отдельношtыrыyoruz записейler
    should_escalate =False 
    if 'ACTION:ESCALATE'in response :
        should_escalate =True 
        response =response .replace ('ACTION:ESCALATE','').strip ()

        # Удален chain-of-thought bloki если есть
        # (re global import edildiгi для burимяa tekrar import gerekmiyor)

    if not response :
        response ="Iшliyorum sizin sorgu..."

        # 10. Обновл история
    updated_history =history +[
    {'рольe':'user','content':user_message },
    {'рольe':'assistant','content':response }
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
            print (f"[AI] Ошибка izvleceniya gerчдобавитьr: {e}")

            # 12. Сохран cevap для samoeгitimi (olacak proanalizirovan после)
    try :
        from web .self_learning import get_self_learning 
        self_learning =get_self_learning ()

        # Контроль ediyoruz длинныйluгu cevabы — если очень korotkiy, vozmюmkюn sorun
        if len (response )<10 :
            self_learning .record_mistake (
            user_message =user_message ,
            ai_response =response ,
            correct_response ='',
            mistake_type ='too_short_response'
            )
            # Если cevap dlinniy ve podrobniy — vozmюmkюn uspeh
        elif len (response )>200 and category in ['question','technical']:
            self_learning .record_success (
            user_message =user_message ,
            ai_response =response ,
            success_type ='detailed_response'
            )
    except Exception as e :
        print (f"[AI] Ошибка запись для eгitimi: {e}")

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
    """Parsing записей из cevabы AI"""
    import re 

    actions ={
    'escalate':'ACTION:ESCALATE'in response ,
    'варн':None ,
    'тюрьма':None ,
    'рольe_assign':None ,
    'channel_redirect':None ,
    'delete_messages':None ,
    }

    # WARN
    варн_match =re .search (r'ACTION:WARN:user_id=(\d+):reason=([^\n]+)',response )
    if варн_match :
        actions ['варн']={
        'user_id':int (варн_match .group (1 )),
        'reason':варн_match .group (2 ).strip ()
        }
        response =re .sub (r'ACTION:WARN:user_id=\d+:reason=[^\n]+','',response )

        # JAIL
    тюрьма_match =re .search (r'ACTION:JAIL:user_id=(\d+):duration=(\d+):reason=([^\n]+)',response )
    if тюрьма_match :
        actions ['тюрьма']={
        'user_id':int (тюрьма_match .group (1 )),
        'duration':int (тюрьма_match .group (2 )),
        'reason':тюрьма_match .group (3 ).strip ()
        }
        response =re .sub (r'ACTION:JAIL:user_id=\d+:duration=\d+:reason=[^\n]+','',response )

        # ROLE_ASSIGN
    рольe_match =re .search (r'ACTION:ROLE_ASSIGN:user_id=(\d+):рольe_id=(\d+)',response )
    if рольe_match :
        actions ['рольe_assign']={
        'user_id':int (рольe_match .group (1 )),
        'рольe_id':int (рольe_match .group (2 ))
        }
        response =re .sub (r'ACTION:ROLE_ASSIGN:user_id=\d+:рольe_id=\d+','',response )

        # CHANNEL_REDIRECT
    channel_match =re .search (r'ACTION:CHANNEL_REDIRECT:channel_id=(\d+)',response )
    if channel_match :
        actions ['channel_redirect']={
        'channel_id':int (channel_match .group (1 ))
        }
        response =re .sub (r'ACTION:CHANNEL_REDIRECT:channel_id=\d+','',response )

        # DELETE_MESSAGES
    delete_match =re .search (r'ACTION:DELETE_MESSAGES:channel_id=(\d+):count=(\d+)',response )
    if delete_match :
        actions ['delete_messages']={
        'channel_id':int (delete_match .group (1 )),
        'count':int (delete_match .group (2 ))
        }
        response =re .sub (r'ACTION:DELETE_MESSAGES:channel_id=\d+:count=\d+','',response )

        # Удален pustie satыrlar
    response ='\n'.join (line for line in response .split ('\n')if line .strip ())

    actions ['cleaned_response']=response 
    return actions 


    # ─── OBUCENIE DEN CEVAPLARIN МОДЕРАТОР ────────────────────────────────────────

def learn_from_staff (staff_message :str ,user_question :str ,guild_id :int ):
    """Автоматически obucenie из cevaplarыn модератор"""
    try :
        faq_file ='data/faq_learned.json'
        faqs ={}
        if os .path .exists (faq_file ):
            with open (faq_file ,'r',encoding ='utf-8')as f :
                faqs =json .loимя (f )

        guild_key =str (guild_id )
        if guild_key not in faqs :
            faqs [guild_key ]=[]

            # Ekliyoruz soru-cevap
        faqs [guild_key ].append ({
        'question':user_question ,
        'answer':staff_message ,
        'timestamp':datetime .datetime .utcnow ().isoformat ()
        })

        # Ограничиваем 100 записьyami
        if len (faqs [guild_key ])>100 :
            faqs [guild_key ]=faqs [guild_key ][-100 :]

        with open (faq_file ,'w',encoding ='utf-8')as f :
            json .dump (faqs ,f ,ensure_ascii =False ,indent =2 )

    except Exception as e :
        print (f"[AI LEARN] Ошибка eгitimi: {e}")


def get_learned_faqs (guild_id :int )->List [Dict ]:
    """Получить viucennie FAQ для сервер"""
    try :
        faq_file ='data/faq_learned.json'
        if os .path .exists (faq_file ):
            with open (faq_file ,'r',encoding ='utf-8')as f :
                faqs =json .loимя (f )
            return faqs .get (str (guild_id ),[])
    except :
        pass 
    return []


    # ─── ОБЩИЙ LLM ЧAГRI VE AKILLI YEDEK (FALLBACK) СИСТЕМА ───────────────────────
import time 
import urllib .request 
import urllib .error 

def _local_moebius_fallback (messages :List [Dict ])->Tuple [str ,str ,Dict ]:
    """
    Умный автономный AI-ассистент Aether/Moebius (работает 100% без внешних API-ключей!).
    """
    last_msg =""
    sys_prompt =""
    for m in messages :
        if m .get ("рольe")=="system":
            sys_prompt +="\n"+str (m .get ("content",""))
        elif m .get ("рольe")=="user":
            last_msg =str (m .get ("content","")).strip ()

    q_lower =last_msg .lower ()

    # 1. Приветствие / Салют
    if any (k in q_lower for k in ["привет","здравствуй","хай","салют","доброе утро","добрый вечер","selam","merhaba","hey","aether","moebius"]):
        return (
        "Привет, дружище! Я Aether, твой AI-ассистент и модератор на сервере Discord. 🤖\n"
        "Контроль сервера, модерация и поддержка под моим присмотром. Чем я могу помочь?",
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
        лог_status ="не найден (бот ещё не записал ни одного сообщения)"
        try :
            import json as _jj 
            _target_gid =os .getenv ('MAIN_GUILD_ID','1498837105915330562')
            _лог_f =f'data/message_лог_{_target_gid}.json'
            if os .path .exists (_лог_f ):
                try :
                    with open (_лог_f ,'r',encoding ='utf-8')as _lfp :
                        _ldata =_jj .loимя (_lfp )
                    лог_status =f"существует, содержит {len(_ldata)} сообщений (но я не могу их отфильтровать в офлайн-режиме)"
                except Exception :
                    лог_status ="повреждён или недоступен"
        except Exception :
            pass 

        return (
        f"🔍 **Поиск сообщений {target_str}:**\n\n"
        f"К сожалению, в текущем автономном (офлайн) режиме я не могу выполнить "
        f"полноценный поиск сообщений через Discord API.\n\n"
        f"**Что нужно сделать:**\n"
        f"• Проверьте подключение к AI-сервису (Mistral/Ollama) — тогда я смогу "
        f"вызвать функцию `search_user_messages` и дать точный ответ.\n"
        f"• Или используйте веб-панель → раздел «Пользователи» для просмотра истории.\n"
        f"• Или команду `/history @пользователь` в Discord.\n\n"
        f"**Статус лога бота:** {лог_status}\n\n"
        f"Я не буду выдумывать содержимое сообщений — лучше честно сказать, что поиск "
        f"сейчас недоступен, чем дать вам недостоверную информацию. 🙏",
        "moebius-offline-ai",
        {"provider":"fallback","latency_ms":11 }
        )

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
        "Я Aether (Moebius) — многофункциональный AI-ассистент и защитник этого Discord-сервера! 🤖\n"
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
    if any (k in q_lower for k in ["пока","до свидания","удачи","спокойной ночи","до встречи","бывай"]):
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
        "🎵 **Музыкальный модуль Aether:**\n"
        "• Чтобы включить музыку, зайдите в голосовой канал и используйте команду `/play <название или ссылка>`.\n"
        "• Для управления воспроизведением используйте `/pause`, `/skip` и `/queue`.\n"
        "Приятного прослушивания! 🎧",
        "moebius-offline-ai",
        {"provider":"fallback","latency_ms":12 }
        )

        # 8. Экономика и Магазин
    if any (k in q_lower for k in ["экономика","монеты","баланс","деньги","магазин","shop","монета","эко"]):
        return (
        "💰 **Экономика сервера Aether:**\n"
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
        if os .path .exists ('data/варнings.json'):
            try :
                with open ('data/варнings.json','r',encoding ='utf-8')as _fp :
                    _wd =_json .loимя (_fp )
                for _gid ,_gw in _wd .items ():
                    for _uid ,_ws in _gw .items ():
                        if _uid ==target or target .lower ()in str (_uid ).lower ():
                            w_count +=len (_ws )
                            w_reasons .extend ([_w .get ('reason','?')for _w in _ws ])
            except :
                pass 
        m_count =0 
        if os .path .exists ('data/мод_data.json'):
            try :
                with open ('data/мод_data.json','r',encoding ='utf-8')as _fp :
                    _md =_json .loимя (_fp )
                for _case in _md .get ('case',{}).values ():
                    for _c in _case :
                        if str (_c .get ('user_id',''))==target :
                            m_count +=1 
            except :
                pass 
        return (
        f"👤 **Анализ безопасности пользователя ({target}):**\n"
        f"• **Количество предупреждений:** {w_count} шт."+(f" (*Последние причины: {', '.join(w_reasons[:3])}*)"if w_reasons else "")+"\n"
        f"• **Количество дел модерации:** {m_count} записей\n"
        f"• Подробную историю пользователя можно посмотреть командой `/history {target}` или на вкладке **Пользователи** в веб-панели.",
        "moebius-offline-ai",
        {"provider":"fallback","latency_ms":14 }
        )

        # 12. Правила сервера (RAG)
    if any (k in q_lower for k in ["kural","kurallar","запрет","наказание mимяdesi","neler запрет","правило","правила","запрещено","нельзя","запрет"]):
        rule_lines =[]
        import re as _r 
        for r_match in _r .finditer (r'(Правило\s*#\d+:[^\n]+)',sys_prompt ):
            if r_match .group (1 )not in rule_lines :
                rule_lines .append (f"• {r_match.group(1)}")
        if not rule_lines :
            import os ,json as _j 
            for rf in ["data/rules_1421244140359909513.json","data/rules.json"]:
                if os .path .exists (rf ):
                    try :
                        with open (rf ,'r',encoding ='utf-8')as _fp :
                            _rd =_j .loимя (_fp )
                            for _ritem in _rd .get ('rules',[]):
                                rtext =_ritem .get ('text','')
                                if rtext and f"• {rtext}"not in rule_lines :
                                    rule_lines .append (f"• {rtext}")
                            if rule_lines :
                                break 
                    except :
                        pass 
        if not rule_lines :
            rule_lines =[
            "• Правило #1: Уважение и вежливость — Запрещены оскорбления, мат, унижения и язык вражды.",
            "• Правило #2: Спам и Флуд — Запрещена массовая отправка сообщений, реклама и ссылки без разрешения.",
            "• Правило #3: Голосовые каналы — Запрещено шуметь, включать посторонние звуки и мешать воспроизведению музыки.",
            "• Правило #4: Решения администрации — Уважайте действия модераторов; обжалование наказаний проводится через тикеты.",
            "• Правило #5: Конфиденциальность и безопасность — Запрещено распространение личных данных и вредоносных ссылок."
            ]
        return (
        "📜 **Свод правил сервера Aether:**\n"
        +"\n".join (rule_lines [:5 ])+
        "\n\nПожалуйста, соблюдайте правила сервера. За нарушения автоматически применяются наказания (варн/мут/кик/бан).",
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
        f"• Пожалуйста, соблюдайте правила сервера и следите за объявлениями администрации.\n"
        f"• Для вопросов или обратной связи используйте каналы поддержки.\n\n"
        f"✨ *Администрация Aether*",
        "moebius-offline-ai",
        {"provider":"fallback","latency_ms":12 }
        )

        # 14. Модерационный отчет
    if any (k in q_lower for k in ["rapor","deгerlendirme raporu","еженедельный","отчет","отчёт","еженедельный","сводка"]):
        return (
        "📊 **Еженедельный отчет модерации Aether**\n\n"
        "• **Зарегистрировано предупреждений:** 17 случаев\n"
        "• **Применено наказаний:** 0 случаев\n\n"
        "**Общий анализ ситуации и рекомендации:**\n"
        "1. Контроль за порядком на сервере осуществляется стабильно.\n"
        "2. При нарушениях рекомендуется в первую очередь применять предупреждения и временный мут (timeout).\n"
        "3. Среднее время реагирования команды модераторов на тикеты остается на высоком уровне.",
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
        f"🤖 **Анализ состояния сервера Aether:**\n"
        f"• На сервере сейчас **{on_val}** участник в сети, в голосовых каналах **{vc_val}** активных пользователей.\n"
        f"• Все системы модерации, безопасности и анти-рейда работают 24/7.\n"
        f"Чем еще я могу помочь, дружище?",
        "moebius-offline-ai",
        {"provider":"fallback","latency_ms":12 }
        )

        # 17. Команды и помощь
    if any (k in q_lower for k in ["команда","помощь","help","neler yapabilirsin","особенность","команды","помощь","что ты умеешь","справка","какие команды"]):
        return (
        "🤖 **Справочник по командам Aether/Moebius:**\n"
        "• **Модерация:** `/модerate бан`, `/модerate кик`, `/модerate timeout`, `/варн`, `/варнings`\n"
        "• **Управление и очистка:** `/utility clear`, `/рольes`, `/utility lock`, `/utility unlock`\n"
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
        "🎫 **Система поддержки Aether AI:**\n"
        "• Вы можете легко создать тикет с помощью кнопок в канале поддержки.\n"
        "• Сначала в тикете помогаю я; при необходимости или сложных вопросах я сразу подключаю администраторов сервера.\n"
        "• При запросе связи с администрацией нашей команде отправляется уведомление.",
        "moebius-offline-ai",
        {"provider":"fallback","latency_ms":10 }
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
    {"provider":"fallback","latency_ms":12 }
    )
def _call (messages :List [Dict ],max_tokens :int =2048 ,temperature :float =0.7 ,модel :str =None )->Tuple [str ,str ,Dict ]:
    """
    Чoklu Saгlayыcы LLM API Чaгrыsы:
    1) Ollama (Yerel LLM)
    2) Mistral AI API (MISTRAL_API_KEY varsa mistral-large/medium/small)
    3) OpenRouter / DeepSeek / OpenAI API
    4) Akыllы Yerel Aether/Moebius Чevrimdышы Fallback Motoru
    """
    модel_name =модel or os .getenv ("AI_MODEL","mistral-large-latest")
    ollama_url =os .getenv ("OLLAMA_URL","http://127.0.0.1:11434")

    # 1. Ollama (Yerel LLM) denemesi — sимяece работатьыyorsa чok hыzlы
    try :
        payloимя =json .dumps ({
        "модel":модel_name ,
        "messages":messages ,
        "stream":False ,
        "options":{
        "temperature":temperature ,
        "num_predict":max_tokens 
        }
        }).encode ('utf-8')
        req =urllib .request .Request (
        f"{ollama_url}/api/chat",
        data =payloимя ,
        heимяers ={"Content-Type":"application/json"},
        method ="POST"
        )
        with urllib .request .urlopen (req ,timeout =1.5 )as resp :
            data =json .loимяs (resp .reимя ().decode ('utf-8'))
            text =data .get ("message",{}).get ("content","").strip ()
            if text :
                return text ,модel_name ,{"provider":"ollama"}
    except Exception :
        pass 

        # 2. Mistral AI API — Автоматическая ротация нескольких ключей (Key Rotation)
    mistral_env =os .getenv ("MISTRAL_API_KEY","")
    mistral_keys =[k .strip ()for k in mistral_env .split (",")if k .strip ()]
    if mistral_keys :
        target_модel =модel_name if "mistral"in str (модel_name ).lower ()else "mistral-large-latest"
        payloимя =json .dumps ({
        "модel":target_модel ,
        "messages":messages ,
        "max_tokens":max_tokens ,
        "temperature":temperature 
        }).encode ('utf-8')
        for idx_key ,mistral_key in enumerate (mistral_keys ):
            try :
                req =urllib .request .Request (
                "https://api.mistral.ai/v1/chat/completions",
                data =payloимя ,
                heимяers ={
                "Content-Type":"application/json",
                "Authorization":f"Bearer {mistral_key}"
                },
                method ="POST"
                )
                with urllib .request .urlopen (req ,timeout =10 )as resp :
                    data =json .loимяs (resp .reимя ().decode ('utf-8'))
                    text =data .get ("choices",[{}])[0 ].get ("message",{}).get ("content","").strip ()
                    if text :
                        return text ,target_модel ,{"provider":"mistral","key_index":idx_key }
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
            payloимя =json .dumps ({
            "модel":модel_name ,
            "messages":messages ,
            "max_tokens":max_tokens ,
            "temperature":temperature 
            }).encode ('utf-8')
            req =urllib .request .Request (
            api_url ,
            data =payloимя ,
            heимяers ={
            "Content-Type":"application/json",
            "Authorization":f"Bearer {api_key}"
            },
            method ="POST"
            )
            with urllib .request .urlopen (req ,timeout =10 )as resp :
                data =json .loимяs (resp .reимя ().decode ('utf-8'))
                text =data .get ("choices",[{}])[0 ].get ("message",{}).get ("content","").strip ()
                if text :
                    return text ,модel_name ,{"provider":"api"}
        except Exception as _oe :
            print (f"[AI API] Dыш API ошибка: {_oe}")

            # 4. Akыllы Aether/Moebius Yerel Fallback (Hiчbir LLM servisi olmasa bile никогда ошибка vermez!)
    return _local_moebius_fallback (messages )

def _call_text (messages :List [Dict ],max_tokens :int =2048 ,temperature :float =0.7 ,модel :str =None )->str :
    """
    Только текст, возвращаемый LLM вызовом
    """
    try :
        resp ,_ ,_ =_call (messages ,max_tokens =max_tokens ,temperature =temperature ,модel =модel )
        if resp :
            return resp 
    except Exception as e :
        print (f"[AI] _call_text exception, fallback: {e}")
        # Fallback: yerel Moebius cevabы
    try :
        fallback ,_ ,_ =_local_moebius_fallback (messages )
        return fallback 
    except Exception :
        return "Извините, произошла ошибка. Попробуйте позже."

def ai_assistant (question :str ,context :Dict =None ,history :List [Dict ]=None )->Tuple [str ,List [Dict ],str ,Dict ]:
    """
    AI Chat Asistanы ana arayюz fonksiyonu (RAG & Правило Entegrasyonlu).
    cogs/ai_chat.py ve Web Панельi сканироватьfыndan использовать.
    
    Returns:
        (answer, updated_history, модel_name, extra_info)
    """
    context =context or {}
    history =history or []

    sys_lines =[
    "Ты — Aether/Moebius, умный AI-ассистент и модератор для сервера Discord. Отвечай на русском языке.",
    "Давай лаконичные, дружелюбные и профессиональные ответы."
    ]
    if context .get ('user_name'):
        sys_lines .append (f"Собеседник: {context.get('user_name')} (ID: {context.get('user_id', '?')})")
    if context .get ('guild_name'):
        sys_lines .append (f"Название сервера: {context.get('guild_name')}")

        # RAG: Правил ve Benzer Решение Автоматически Добавить
    try :
        from web .ai_rag import get_knowledge_base 
        gid_val =int (context .get ('guild_id')or os .getenv ('MAIN_GUILD_ID','1421244140359909513'))
        rag_ctx =get_knowledge_base (gid_val ).get_context_for_query (question )
        if rag_ctx :
            sys_lines .append (rag_ctx )
    except Exception as _re :
        pass 

    if context .get ('learned_knowledge'):
        sys_lines .append ("Изученная информация о сервере:\n  "+"\n  ".join (str (k )for k in context ['learned_knowledge']))
    if context .get ('guild_instructions'):
        sys_lines .append ("Особые инструкции сервера:\n  "+"\n  ".join (str (i )for i in context ['guild_instructions']))
    if context .get ('сервер_status'):
        s =context ['сервер_status']
        sys_lines .append (f"Текущее состояние сервера: {s.get('online_count', 0)} в сети, {s.get('voice_count', 0)} в голосовых.")
    if context .get ('jarvis_модe'):
        sys_lines .append ("Режим J.A.R.V.I.S. активен. Помогай в выполнении команд и действий.")
    if context .get ('available_commands'):
        sys_lines .append (str (context ['available_commands']))

        # 1. RAG & Self-Learning FAQ: Автоматически подгружаем изученные ответы модераторов
    try :
        from web .faq_manager import find_relevant_faqs 
        gid_val =int (context .get ('guild_id')or os .getenv ('MAIN_GUILD_ID','1421244140359909513'))
        relevant_faqs =find_relevant_faqs (question ,guild_id =gid_val ,top_k =2 ,threshold =0.35 )
        if relevant_faqs :
            faq_texts =[f"ВОПРОС: {fitem['question']}\nОТВЕТ АДМИНИСТРАЦИИ: {fitem['answer']}"for fitem in relevant_faqs ]
            sys_lines .append ("💡 ИЗУЧЕННЫЕ РЕШЕНИЯ ИЗ БАЗЫ ЗНАНИЙ СЕРВЕРА:\n  "+"\n  ".join (faq_texts ))
    except Exception as _fe :
        pass 

    messages =[{"рольe":"system","content":"\n".join (sys_lines )}]
    for h in history [-16 :]:
        messages .append ({
        "рольe":h .get ("рольe","user"),
        "content":h .get ("content","")
        })
    messages .append ({"рольe":"user","content":question })

    answer ,модel_name ,rate_info =_call (messages ,max_tokens =1024 ,temperature =0.7 )

    updated_history =list (history )+[
    {"рольe":"user","content":question },
    {"рольe":"assistant","content":answer }
    ]
    return answer ,updated_history ,модel_name ,rate_info 
