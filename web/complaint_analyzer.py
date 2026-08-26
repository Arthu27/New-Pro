"""
Супер-умный анализ жалоб на оскорбления
Глубокий анализ истории, репутации, контекста, доказательств
"""

from logger import get_logger

_log = get_logger("complaint_analyzer")

import discord 
import json 
import os 
import re 
from datetime import datetime ,timedelta ,timezone 
from typing import Dict ,List ,Optional ,Tuple 


class ComplaintAnalyzer :
    """Продвинутый анализатор жалоб"""

    def __init__ (self ,bot :discord .Client ):
        self .bot =bot 
        self .toxicity_patterns =[
        # === РУССКИЙ ===
        r'\b(тварь|ублюдок|мраз|сволочь|мразь|мерзавец|подонок|скотина)\b',
        r'\b(дурак|дура|идиот|тупой|тупица|дебил|кретин|олух|болван|придурок)\b',
        r'\b(пошёл|пошла|пошли|иди|идите)\s*(на\s*хер|на\s*хуй|в\s*жопу|в\s*задницу)\b',
        r'\b(сука|блядь|блять|нахер|нахуй|пиздец|ебать|ебаный|ебанутый|хуй|хуя|хую)\w*',
        r'\b(мудак|мудak|гондон|пидор|пидорас|шлюха|блядина)\w*',
        r'\b(урод|мразотный|дрянь|сволота|скотина|гадина|тварь)\b',
        r'\b(ты\s+чмо|ты\s+лох|ты\s+конченый|ты\s+тупой|ты\s+идиот)\b',
        # === ТУРЕЦКИЙ ===
        r'\b(amk|amq|orospu|piч|yarrak|siktir|gёt|amcыk|salak|aptal|gerizekalы)\b',
        r'\b(ananы|bacыnы|karыnы|kыzыnы|karыnы)\s*(sikeyim|becereyim|sikim)\b',
        r'\b(aqыlsыz|ahmak|шerefsiz|namussuz|orospu|pezevenk)\b',
        r'\b(siktir\s*git|defol|ibne|top\s*senin|gёt\s*veren)\b',
        r'\b(lan|aq|aлиna|koyim|amcыгыnы|yarram)\w*',
        # === АНГЛИЙСКИЙ ===
        r'\b(stupid|idiot|moron|fool|dumb|loser|asshole|jerk|dickhead)\b',
        r'\b(shut\s*up|fuck\s*you|go\s*to\s*hell|piece\s*of\s*shit)\b',
        r'\b(bastard|bitch|whore|slut|cunt|wanker)\b',
        r'\b(nigger|faggot|retard)\w*',
        # === УГРОЗЫ (RU/TR/EN) ===
        r'\b(убью|убить|зарежу|прирежу|прибью|пристрелю|закопаю|утоплю)\b',
        r'\b(повешу|отрежу|разорву|сломаю|разобью)\w*',
        r'\b(ёldюreceгim|ёldюr|gebert|vuracaгыm|keseceгim)\b',
        r'\b(kill\s*you|will\s*kill|i\s*will\s*kill|murder\s*you)\b',
        ]

    async def analyze_complaint (
    self ,
    guild :discord .Guild ,
    complainant_id :int ,
    accused_id :int ,
    complaint_text :str ,
    provided_messages :List [str ]=None 
    )->Dict :
        """
        Polniy analiz жалобы
        
        Returns:
            {
                'verdict': 'GUILTY' | 'INNOCENT' | 'MUTUAL' | 'FALSE_COMPLAINT' | 'UNCLEAR',
                'confidence': 0-100,
                'evidence': {...},
                'recommendation': {...},
                'analysis': str
            }
        """
        # 1. Topluyoruz информация о каждый ikisi пользователь
        complainant_info =await self ._get_user_profile (guild ,complainant_id )
        accused_info =await self ._get_user_profile (guild ,accused_id )

        # 2. Analiz ediyoruz история сообщение
        message_history =await self ._get_message_history (guild ,complainant_id ,accused_id )

        # 3. Контроль ediyoruz itibarы каждый ikisi
        complainant_rep =await self ._get_reputation (guild ,complainant_id )
        accused_rep =await self ._get_reputation (guild ,accused_id )

        # 4. Analiz ediyoruz predostavlennie сообщения
        provided_analysis =self ._analyze_provided_messages (provided_messages or [])

        # 5. Контроль ediyoruz baгlam (bila ли provokasyon)
        context_analysis =await self ._analyze_context (guild ,message_history ,complainant_id ,accused_id )

        # 6. Ocenivaem ciddiyet
        severity =self ._assess_severity (provided_analysis ,context_analysis )

        # 7. Создан karar
        verdict_data =self ._form_verdict (
        complainant_info ,accused_info ,
        complainant_rep ,accused_rep ,
        provided_analysis ,context_analysis ,
        severity 
        )

        return verdict_data 

    async def _get_user_profile (self ,guild :discord .Guild ,user_id :int )->Dict :
        """Получить profil пользователь"""
        member =guild .get_member (user_id )
        if not member :
            return {'found':False ,'id':user_id }

        return {
        'found':True ,
        'id':user_id ,
        'name':member .display_name ,
        'joined_at':member .joined_at .isoformat ()if member .joined_at else None ,
        'days_on_server':(datetime .now (timezone .utc )-member .joined_at ).days if member .joined_at else 0 ,
        'role':[role .name for role in member .roles if role .name !="@everyone"],
        'is_moderator':member .guild_permissions .kick_members or member .guild_permissions .ban_members ,
        'account_age':(datetime .now (timezone .utc )-member .created_at ).days ,
        }

    async def _get_message_history (
    self ,
    guild :discord .Guild ,
    user1_id :int ,
    user2_id :int ,
    limit :int =100 
    )->List [Dict ]:
        """Получить история сообщение mejdu dvumya пользователь"""
        from cogs .logs import _msg_cache 

        # Ищем сообщения из каждый ikisi в kese
        messages =[]
        for msg in _msg_cache .values ():
            if msg .get ('author_id')in [user1_id ,user2_id ]:
                messages .append (msg )

                # Sortiruem по время
        messages .sort (key =lambda x :x .get ('timestamp',''))

        # Ограничиваем
        return messages [-limit :]

    async def _get_reputation (self ,guild :discord .Guild ,user_id :int )->Dict :
        """Получить репутацию пользователя"""
        from cogs .warnings import load_warnings 

        warnings_data =load_warnings ()
        guild_warnings =warnings_data .get (str (guild .id ),{}).get (str (user_id ),[])

        # Scitaem предупреждения для raznie periodi
        now =datetime .now (timezone .utc )
        warnings_7d =0 
        warnings_30d =0 
        warnings_total =len (guild_warnings )

        for варн in guild_warnings :
            warn_date_raw =варн .get ('timestamp',now .isoformat ())
            try :
                warn_date =datetime .fromisoformat (warn_date_raw )
            except (ValueError ,TypeError ) as _ex:
                _log.debug("_get_reputation(): подавлено: %s", _ex)
                continue 
                # Если naive — делаем aware (UTC)
            if warn_date .tzinfo is None :
                warn_date =warn_date .replace (tzinfo =timezone .utc )
            days_ago =(now -warn_date ).days 

            if days_ago <=7 :
                warnings_7d +=1 
            if days_ago <=30 :
                warnings_30d +=1 

                # Контроль ediyoruz история banov/mutov
        mod_data_file ='data/mod_data.json'
        mod_history =[]
        if os .path .exists (mod_data_file ):
            try :
                with open (mod_data_file ,'r',encoding ='utf-8')as f :
                    mod_data =json .load (f )
                    guild_mods =mod_data .get ('cases',{}).get (str (guild .id ),[])
                    mod_history =[
                    case for case in guild_mods 
                    if case .get ('user_id')==str (user_id )
                    ]
            except Exception as _ex:
                _log.debug("_get_reputation(): подавлено: %s", _ex)

        bans =sum (1 for case in mod_history if case .get ('action')=='бан')
        mutes =sum (1 for case in mod_history if case .get ('action')in ['timeout','мут'])

        return {
        'warnings_total':warnings_total ,
        'warnings_7d':warnings_7d ,
        'warnings_30d':warnings_30d ,
        'bans':bans ,
        'mutes':mutes ,
        'recent_warnings':guild_warnings [-5 :]if guild_warnings else [],
        }

    def _analyze_provided_messages (self ,messages :List [str ])->Dict :
        """Анализирует предоставленные сообщения (турецкие/русские/английские)."""
        import re 

        toxicity_count =0 
        threats_count =0 
        complainer_toxic =0 
        accused_toxic =0 

        # Расширенный список оскорбительных слов (для fallback-проверки,
        # когда regex не сработал но маркер [ЖАЛОБА EDEN] присутствует)
        offensive_words ={
        'тварь','ублюдок','мразь','сволочь','мерзавец','подонок','скотина',
        'дурак','дура','идиот','тупой','тупица','дебил','кретин','олух',
        'придурок','чмо','лох','урод','гадина','дрянь','мразотный',
        'сука','блядь','блять','нахер','нахуй','пиздец','ебать','ебаный',
        'ебанутый','хуй','хуя','хую','мудак','гондон','пидор','пидорас',
        'шлюха','блядина','конченый','гнида','мразь',
        # Турецкий
        'amk','amq','orospu','piч','yarrak','siktir','salak','aptal',
        'gerizekalы','aqыlsыz','ahmak','шerefsiz','namussuz','pezevenk',
        'ibne','lan','aq','amcыk',
        # Английский
        'stupid','idiot','moron','fool','dumb','loser','asshole','jerk',
        'dickhead','bastard','bitch','whore','slut','cunt','wanker',
        'nigger','faggot','retard','scum',
        }
        offensive_set =set (offensive_words )

        for msg in messages :
            msg_lower =msg .lower ()
            # Удаляем метки времени и теги для чистой проверки
            clean_text =re .sub (r'^\[[^\]]+\]\s*\[(?:ЖАЛОБА EDEN|ЖАЛОБА EDИLEN)[^\]]*\]\s*(?:🎯 ВЕРНО|📍 BAГLAMLI|🗑️ УДАЛЕН СООБЩЕНИЕ):\s*','',msg )

            # Проверяем на токсичность через regex
            is_toxic_regex =any (
            re .search (pattern ,msg_lower ,re .IGNORECASE )
            for pattern in self .toxicity_patterns 
            )

            # Проверяем на токсичность через словарь (fallback)
            words_in_text =re .findall (r'\b[a-zA-Zа-яА-ЯёЁ]+\b',clean_text .lower ())
            is_toxic_dict =bool (words_in_text )and any (
            w in offensive_set for w in words_in_text 
            )

            is_toxic =is_toxic_regex or is_toxic_dict 

            if is_toxic :
                toxicity_count +=1 

                # Определяем кто токсичен
                if '[ЖАЛОБА EDEN'in msg or '[ЖАЛОБА EDEN]'in msg :
                    complainer_toxic +=1 
                elif '[ЖАЛОБА EDИLEN'in msg or '[ЖАЛОБА EDИLEN]'in msg :
                    accused_toxic +=1 

                    # Проверяем на угрозы (русские + турецкие + английские ключевые слова)
            threat_patterns =[
            r'\b(убью|убить|зарежу|прирежу|прибью|пристрелю|закопаю|утоплю|повешу|отрежу|разорву|грохну)\b',
            r'\b(ёldюreceгim|ёldюr|gebert|vuracaгыm|keseceгim|seni\s*ёldюr)\b',
            r'\b(kill\s*you|will\s*kill|i\s*will\s*kill|murder\s*you|i\s*will\s*end\s*you)\b',
            ]
            if any (re .search (p ,msg_lower ,re .IGNORECASE )for p in threat_patterns ):
                threats_count +=1 

        return {
        'total_messages':len (messages ),
        'toxic_messages':toxicity_count ,
        'threats':threats_count ,
        'complainer_toxic':complainer_toxic ,
        'accused_toxic':accused_toxic ,
        'mutual_toxicity':complainer_toxic >0 and accused_toxic >0 ,
        }

    async def _analyze_context (
    self ,
    guild :discord .Guild ,
    message_history :List [Dict ],
    complainant_id :int ,
    accused_id :int 
    )->Dict :
        """Анализирует контекст разговора между двумя пользователями."""

        # Ищем сообщения прямо перед инцидентом
        context_messages =[]
        for msg in message_history [-20 :]:# последние 20
            if msg .get ('author_id')in [complainant_id ,accused_id ]:
                context_messages .append (msg )

                # Проверяем была ли провокация (русские/турецкие ключевые слова)
        provocation_indicators =[
        # Русский
        'сам такой','отвечай','а ты кто','заткнись','закрой рот','ты кто',
        'ответь мне','что молчишь','сам дурак','ты тупой','ты идиот',
        # Турецкий
        'kendi takoy','otvecu','a sen кто','zatknis','kapa чeneni','sen кто',
        'sen aptalsin','salak','gerizekalы',
        # Английский
        'shut up','stupid','idiot','fool',
        ]

        provocation_count =0 
        for msg in context_messages :
            content =msg .get ('content','').lower ()
            if any (indicator in content for indicator in provocation_indicators ):
                provocation_count +=1 

                # Проверяем кто начал первый — ищем первое токсичное сообщение
        first_aggressor =None 
        for msg in context_messages :
            content =msg .get ('content','').lower ()
            is_toxic =any (
            re .search (pattern ,content ,re .IGNORECASE )
            for pattern in self .toxicity_patterns 
            )
            if is_toxic :
                first_aggressor =msg .get ('author_id')
                break 

        return {
        'context_messages_count':len (context_messages ),
        'provocation_indicators':provocation_count ,
        'first_aggressor':first_aggressor ,
        'had_provocation':provocation_count >0 ,
        }

    def _assess_severity (self ,provided_analysis :Dict ,context_analysis :Dict )->str :
        """Оценивает серьёзность нарушения."""

        # Угрозы — всегда критично
        if provided_analysis ['threats']>0 :
            return 'CRITICAL'

            # Очень много токсичных сообщений
        if provided_analysis ['toxic_messages']>=5 :
            return 'HIGH'

            # Несколько токсичных сообщений
        if provided_analysis ['toxic_messages']>=2 :
            return 'MEDIUM'

            # Одно токсичное сообщение
        if provided_analysis ['toxic_messages']==1 :
            return 'LOW'

        return 'NONE'

    def _form_verdict (
    self ,
    complainant_info :Dict ,
    accused_info :Dict ,
    complainant_rep :Dict ,
    accused_rep :Dict ,
    provided_analysis :Dict ,
    context_analysis :Dict ,
    severity :str 
    )->Dict :
        """Создаёт финальное решение AI по жалобе."""

        # Определяем вердикт
        if provided_analysis ['mutual_toxicity']:
            verdict ='MUTUAL'
            confidence =85 
        elif provided_analysis ['complainer_toxic']>provided_analysis ['accused_toxic']:
            verdict ='FALSE_COMPLAINT'
            confidence =80 
        elif provided_analysis ['accused_toxic']>0 :
            verdict ='GUILTY'
            confidence =75 
        elif provided_analysis ['toxic_messages']==0 :
            verdict ='INNOCENT'
            confidence =70 
        else :
            verdict ='UNCLEAR'
            confidence =40 

            # Корректируем доверие на основе репутации
        if accused_rep ['warnings_7d']>=3 :
            if verdict =='GUILTY':
                confidence +=10 
        elif complainant_rep ['warnings_7d']>=3 :
            if verdict =='FALSE_COMPLAINT':
                confidence +=10 

                # Создаём предложение
        recommendation =self ._form_recommendation (
        verdict ,severity ,accused_rep ,complainant_rep 
        )

        # Создаём текстовый анализ
        analysis_text =self ._form_analysis_text (
        complainant_info ,accused_info ,
        provided_analysis ,context_analysis ,
        verdict ,confidence ,severity 
        )

        return {
        'verdict':verdict ,
        'confidence':min (confidence ,100 ),
        'severity':severity ,
        'evidence':{
        'toxic_messages':provided_analysis ['toxic_messages'],
        'threats':provided_analysis ['threats'],
        'mutual_toxicity':provided_analysis ['mutual_toxicity'],
        'complainer_toxic':provided_analysis ['complainer_toxic'],
        'accused_toxic':provided_analysis ['accused_toxic'],
        'accused_warnings':accused_rep ['warnings_total'],
        'complainer_warnings':complainant_rep ['warnings_total'],
        'had_provocation':context_analysis ['had_provocation'],
        },
        'recommendation':recommendation ,
        'analysis':analysis_text ,
        }

    def _form_recommendation (
    self ,
    verdict :str ,
    severity :str ,
    accused_rep :Dict ,
    complainant_rep :Dict 
    )->Dict :
        """Создаёт предложение по наказанию для модератора."""

        if verdict =='GUILTY':
            if severity =='CRITICAL':
                return {
                'action':'BAN',
                'duration':None ,# Перманентный
                'reason':'Угрозы и оскорбления — критическое нарушение'
                }
            elif severity =='HIGH':
                if accused_rep ['warnings_total']>=3 :
                    return {
                    'action':'BAN',
                    'duration':7 *24 *60 ,# 7 дней
                    'reason':'Систематические оскорбления (множество предупреждений)'
                    }
                else :
                    return {
                    'action':'MUTE',
                    'duration':24 *60 ,# 24 часа
                    'reason':'Множественные оскорбления'
                    }
            elif severity =='MEDIUM':
                return {
                'action':'MUTE',
                'duration':4 *60 ,# 4 часа
                'reason':'Оскорбление в чате'
                }
            else :# LOW
                return {
                'action':'WARN',
                'duration':None ,
                'reason':'Единичное оскорбление'
                }

        elif verdict =='MUTUAL':
            return {
            'action':'MUTE_BOTH',
            'duration':2 *60 ,# 2 часа обоим
            'reason':'Взаимные оскорбления (оба нарушили правила)'
            }

        elif verdict =='FALSE_COMPLAINT':
            return {
            'action':'WARN_COMPLAINANT',
            'duration':None ,
            'reason':'Ложная жалоба — доказательств нарушения не найдено'
            }

        else :# INNOCENT or UNCLEAR
            return {
            'action':'NO_ACTION',
            'duration':None ,
            'reason':'Недостаточно доказательств для наказания'
            }

    def _form_analysis_text (
    self ,
    complainant_info :Dict ,
    accused_info :Dict ,
    provided_analysis :Dict ,
    context_analysis :Dict ,
    verdict :str ,
    confidence :int ,
    severity :str 
    )->str :
        """Создаёт текстовый анализ жалобы (plain-text вариант)."""

        # Локализация
        verdict_ru ={
        'GUILTY':'🚨 ВИНОВЕН',
        'INNOCENT':'✅ НЕ ВИНОВЕН',
        'MUTUAL':'⚖️ ВЗАИМНАЯ ВИНА',
        'FALSE_COMPLAINT':'🟡 ЛОЖНАЯ ЖАЛОБА',
        'UNCLEAR':'❓ НЕЯСНО',
        }.get (verdict ,verdict )

        severity_ru ={
        'CRITICAL':'🔴 Критическая',
        'HIGH':'🟠 Высокая',
        'MEDIUM':'🟡 Средняя',
        'LOW':'🔵 Низкая',
        'NONE':'⚪ Нет нарушений',
        }.get (severity ,severity )

        analysis_parts =[
        "## 📋 Анализ жалобы\n",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n",
        f"**Вердикт:** {verdict_ru}\n",
        f"**Уверенность:** {confidence}%\n",
        f"**Серьёзность:** {severity_ru}\n\n",

        "### 📊 Доказательства:\n",
        f"• Токсичных сообщений: **{provided_analysis['toxic_messages']}**\n",
        f"• Угроз: **{provided_analysis['threats']}**\n",
        f"• Взаимная токсичность: **{'⚠️ Да' if provided_analysis['mutual_toxicity'] else '✅ Нет'}**\n\n",

        "### 🔍 Контекст:\n",
        f"• Была провокация: **{'⚠️ Да' if context_analysis['had_provocation'] else '✅ Нет'}**\n",
        f"• Первый агрессор: **{context_analysis.get('first_aggressor') or 'Не определён'}**\n",
        f"• Сообщений в контексте: **{context_analysis['context_messages_count']}**\n\n",
        ]

        return ''.join (analysis_parts )

    def _form_embed (
    self ,
    verdict :str ,
    confidence :int ,
    severity :str ,
    evidence :Dict ,
    recommendation :Dict ,
    complainant_info :Dict ,
    accused_info :Dict 
    )->discord .Embed :
        """Создаёт красивый discord.Embed с результатами анализа (как /help)."""

        # Локализация вердикта
        verdict_ru_map ={
        'GUILTY':('🚨 ВИНОВЕН',0xE74C3C ,'Подтверждено нарушение правил сервера'),
        'INNOCENT':('✅ НЕ ВИНОВЕН',0x2ECC71 ,'Доказательств нарушения не найдено'),
        'MUTUAL':('⚖️ ВЗАИМНАЯ ВИНА',0xF39C12 ,'Оба участника нарушили правила'),
        'FALSE_COMPLAINT':('🟡 ЛОЖНАЯ ЖАЛОБА',0x95A5A6 ,'Жалоба не подтвердилась, жалобщик сам нарушал правила'),
        'UNCLEAR':('❓ НЕЯСНО',0x95A5A6 ,'Недостаточно данных для принятия решения'),
        }
        verdict_text ,embed_color ,verdict_desc =verdict_ru_map .get (verdict ,(verdict ,0x3498DB ,''))

        # Серьёзность → текст
        severity_ru_map ={
        'CRITICAL':('🔴 Критическая',0xE74C3C ),
        'HIGH':('🟠 Высокая',0xE67E22 ),
        'MEDIUM':('🟡 Средняя',0xF1C40F ),
        'LOW':('🔵 Низкая',0x3498DB ),
        'NONE':('⚪ Нет нарушений',0x95A5A6 ),
        }
        severity_text ,severity_color =severity_ru_map .get (severity ,(severity ,0x95A5A6 ))

        # Рекомендация → текст
        action_ru_map ={
        'BAN':'🔨 Бан',
        'MUTE':'🔇 Мут',
        'WARN':'⚠️ Предупреждение',
        'MUTE_BOTH':'🔇 Мут обоим',
        'WARN_COMPLAINANT':'⚠️ Предупреждение жалобщику',
        'NO_ACTION':'✅ Действие не требуется',
        }
        action_text =action_ru_map .get (recommendation ['action'],recommendation ['action'])

        duration_text ='Перманентно'if recommendation .get ('duration')is None else self ._format_duration (recommendation .get ('duration',0 ))

        # Жертва (accused)
        accused_name =accused_info .get ('name',f"ID {accused_info.get('id', '?')}")
        accused_id =accused_info .get ('id','?')
        accused_account_age =accused_info .get ('account_age',0 )
        accused_days =accused_info .get ('days_on_server',0 )

        # Жалобщик (complainant)
        complainer_name =complainant_info .get ('name',f"ID {complainant_info.get('id', '?')}")
        complainer_id =complainant_info .get ('id','?')

        # Проверяем оскорбил ли жалобщик обвиняемого
        complainer_toxic =evidence .get ('complainer_toxic',0 )
        accused_toxic =evidence .get ('accused_toxic',0 )
        complainer_abused =complainer_toxic >0 

        embed =discord .Embed (
        title =f"⚖️ Анализ жалобы — {verdict_text}",
        description =f"_{verdict_desc}_",
        color =embed_color ,
        timestamp =datetime .now (timezone .utc ),
        )

        # 📊 Главный блок
        embed .add_field (
        name ="━━━━━━━━━━━━━━━━━━━━",
        value =(
        f"**🎯 Вердикт:** {verdict_text}\n"
        f"**📈 Уверенность AI:** {confidence}%\n"
        f"**⚠️ Серьёзность:** {severity_text}\n"
        "━━━━━━━━━━━━━━━━━━━━"
        ),
        inline =False ,
        )

        # 👤 Участники
        embed .add_field (
        name ="👤 Обвиняемый",
        value =(
        f"**{accused_name}** (`{accused_id}`)\n"
        f"├ Возраст аккаунта: `{accused_account_age} дн.`\n"
        f"├ На сервере: `{accused_days} дн.`\n"
        f"└ Предупреждений: `{evidence.get('accused_warnings', 0)}`"
        ),
        inline =True ,
        )

        embed .add_field (
        name ="📝 Жалобщик",
        value =(
        f"**{complainer_name}** (`{complainer_id}`)\n"
        f"└ Предупреждений: `{evidence.get('complainer_warnings', 0)}`"
        ),
        inline =True ,
        )

        embed .add_field (
        name ="\u200b",# невидимый разделитель
        value ="\u200b",
        inline =False ,
        )

        # 🔍 Доказательства
        evidence_text =(
        f"├ 💬 Токсичных сообщений: **`{evidence.get('toxic_messages', 0)}`**\n"
        f"├ ⚠️ Угроз: **`{evidence.get('threats', 0)}`**\n"
        f"├ 🔄 Взаимная токсичность: **`{'⚠️ Да' if evidence.get('mutual_toxicity') else '✅ Нет'}`**\n"
        f"└ 🎭 Провокация: **`{'⚠️ Была' if evidence.get('had_provocation') else '✅ Нет'}`**"
        )
        embed .add_field (
        name ="🔍 Доказательства",
        value =f"```\n{evidence_text}\n```",
        inline =False ,
        )

        # ⚠️ ВАЖНО: Если жалобщик сам оскорбил — выделить это!
        if complainer_abused :
            complainer_insult_block =(
            f"⚠️ **Жалобщик сам оскорбил обвиняемого** ({complainer_toxic} токсичных сообщений)\n"
            )
            if accused_toxic >0 :
                complainer_insult_block +=f"↳ Обвиняемый тоже отвечал ({accused_toxic} токсичных) — это **взаимная вина**\n"
            else :
                complainer_insult_block +="↳ Обвиняемый не отвечал — это **ложная жалоба**\n"
            embed .add_field (
            name ="⚠️ ВАЖНАЯ ИНФОРМАЦИЯ",
            value =complainer_insult_block ,
            inline =False ,
            )

            # 💡 Рекомендация AI
        embed .add_field (
        name ="💡 Рекомендация AI для модератора",
        value =(
        f"**Действие:** {action_text}\n"
        f"**Длительность:** {duration_text}\n"
        f"**Причина:** {recommendation.get('reason', 'Не указана')}"
        ),
        inline =False ,
        )

        # 📝 Заключение
        if verdict =='GUILTY':
            conclusion ="✅ AI рекомендует применить наказание к обвиняемому."
        elif verdict =='INNOCENT':
            if complainer_abused :
                conclusion =(
                "✅ Доказательств нарушения обвиняемого не найдено. "
                "Жалоба отклонена.\n"
                "⚠️ Но жалобщик сам оскорблял — рекомендуется вынести предупреждение."
                )
            else :
                conclusion ="✅ Доказательств нарушения не найдено. Жалоба отклонена."
        elif verdict =='MUTUAL':
            conclusion ="⚖️ Оба участника нарушили правила. Рекомендуется наказать обоих."
        elif verdict =='FALSE_COMPLAINT':
            conclusion ="🟡 Жалобщик сам нарушал правила. Рекомендуется предупреждение жалобщику."
        else :
            conclusion ="❓ Недостаточно данных для принятия решения. Передаётся модератору."

        embed .add_field (
        name ="📝 Заключение",
        value =conclusion ,
        inline =False ,
        )

        embed .set_footer (text ="🤖 Hakumo AI · Система анализа жалоб")

        return embed 

    @staticmethod 
    def _format_duration (minutes :int )->str :
        """Форматирует длительность из минут в читаемый текст."""
        if minutes is None or minutes ==0 :
            return 'Перманентно'
        if minutes <60 :
            return f'{minutes} мин.'
        if minutes <1440 :
            hours =minutes /60 
            return f'{hours:g} ч.'
        days =minutes /1440 
        return f'{days:g} дн.'
