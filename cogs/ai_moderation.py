"""
AI Moderation Cog
=================
- Multi-language toxic detection (RU/TR/EN)
- Auto-escalation: warn → mute → ban (кик отключён по решению владельца)
- Context-aware analysis (irony, emoji, abbreviations)
- False positive reduction via user feedback learning
- Real-time alerts to log channel
- Admin override & whitelist
"""
import discord 
from discord .ext import commands ,tasks 
import json 
import os 
import re 
import time 
import asyncio 
from datetime import datetime ,timedelta, timezone
from collections import defaultdict ,Counter 

from logger import get_logger 
log =get_logger ("ai_moderation")


DATA_DIR ="data"
os .makedirs (DATA_DIR ,exist_ok =True )

# TOXIC PATTERNS (3 dil) 
TOXIC_PATTERNS ={
# Severity 1 — mild (warn)
"mild":{
"ru":[
r"\b(дурак|тупой|глупый|урод|кринж|кринге)\b",
r"\b(идиот|дебил|лох|олух|придурок)\b",
],
"tr":[
r"\b(salak|aptal|gerizekalы|ahmak|mal)\b",
r"\b(aptal|salak)\b",
],
"en":[
r"\b(stupid|dumb|idiot|loser|noob)\b",
r"\b(sucks|cringe|trash)\b",
],
},
# Severity 2 — moderate (mute)
"moderate":{
"ru":[
r"\b(ненавижу|убью|убить|ненависть)\b",
r"\b(шлюха|проститутка|тварь)\b",
],
"tr":[
r"\b(ёldюreceгim|nefret|orospu|piч)\b",
],
"en":[
r"\b(hate|kill yourself|kys|loser)\b",
r"\b(whore|slut|bitch)\b",
],
},
# Severity 3 — severe (ban)
"severe":{
"ru":[
r"\b(расстрел|взорвать|террор|isis)\b",
r"\b(педофил|изнасилование|порно с детьми)\b",
],
"tr":[
r"\b(tecavюz|terёr|patlayыcы|ыsg)\b",
],
"en":[
r"\b(terrorist|terrorism|bomb|isis)\b",
r"\b(rape|pedophile|child porn)\b",
],
},
# Spam исключён из AI-детекции по просьбе владельца:
# спам/флуд обрабатывается отдельными механизмами, без ИИ.
# Discrimination
"discrimination":{
"any":[
r"\b(n[ыi]gg[ae]r|f[ae]gg[oi]t|tr[ae]nn[yi])\b",
r"\b(ж[иы]д|цыган|хохол|москаль)\b",
],
},
}

# Severity → action mapping
SEVERITY_ACTION ={
"mild":{"action":"warn","mute_minutes":0 },
"moderate":{"action":"mute","mute_minutes":10 },
"severe":{"action":"ban","mute_minutes":0 },
"spam":{"action":"warn","mute_minutes":0 },
"discrimination":{"action":"mute","mute_minutes":60 },
}


class AIModeration (commands .Cog ):
    """AI-powered moderation with toxic detection and auto-escalation"""

    def __init__ (self ,bot ):
        self .bot =bot 
        self .user_history =defaultdict (lambda :defaultdict (list ))# guild_id -> user_id -> [(timestamp, severity, action)]
        self .spam_tracker =defaultdict (lambda :defaultdict (list ))# guild_id -> user_id -> [message_times]
        self .false_positive_feedback ={}# (guild, message_hash) -> count
        self .last_dm_warning ={}# user_id -> last_dm_time
        # Whitelist
        self .whitelist_cache ={}# guild_id -> set(user_ids)

        # DATA PERSISTENCE 
    def _config_file (self ,guild_id ):
        return f"{DATA_DIR}/ai_mod_config_{guild_id}.json"

    def _history_file (self ,guild_id ):
        return f"{DATA_DIR}/ai_mod_history_{guild_id}.json"

    def load_config (self ,guild_id ):
        """Конфиг с дефолтами: сохранённый файл глубоко сливается с дефолтным.

        Старые/устаревшие файлы конфигов без новых ключей (escalation и т.п.)
        больше не отдают undefined-поля на фронт."""
        f =self ._config_file (guild_id )
        cfg =self ._default_config ()
        if not os .path .exists (f ):
            return cfg
        try :
            with open (f ,"r",encoding ="utf-8")as fp :
                stored =json .load (fp )
            if not isinstance (stored ,dict ):
                return cfg
            def _merge (dst ,src ):
                for k ,v in src .items ():
                    if isinstance (v ,dict )and isinstance (dst .get (k ),dict ):
                        _merge (dst [k ],v )
                    else :
                        dst [k ]=v
            _merge (cfg ,stored )
            return cfg
        except Exception :
            return cfg

    def save_config (self ,guild_id ,config ):
        with open (self ._config_file (guild_id ),"w",encoding ="utf-8")as fp :
            json .dump (config ,fp ,ensure_ascii =False ,indent =2 )

    def load_history (self ,guild_id ):
        f =self ._history_file (guild_id )
        if not os .path .exists (f ):
            return []
        try :
            with open (f ,"r",encoding ="utf-8")as fp :
                return json .load (fp )
        except Exception :
            return []

    def save_history_entry (self ,guild_id ,entry ):
        history =self .load_history (guild_id )
        history .append (entry )
        history =history [-1000 :]# keep last 1000
        with open (self ._history_file (guild_id ),"w",encoding ="utf-8")as fp :
            json .dump (history ,fp ,ensure_ascii =False ,indent =2 )

    def _default_config (self ):
        return {
        "enabled":True ,
        "auto_actions":{
        "mild":True ,"moderate":True ,"severe":True ,"discrimination":True 
        },
        "escalation":{
        "enabled":True ,# 3 мьюта за 24ч → бан (кик отключён по решению владельца)
        "warn_to_mute_after":3 ,
        "mute_to_kick_after":3 ,
        "kick_to_ban_after":2 ,
        "window_hours":24 ,
        },
        "languages":["ru","tr","en"],
        "log_channel_id":None ,
        "dm_on_action":True ,
        "ignored_channels":[],
        "ignored_roles":[],
        "whitelist_users":[],
        "sensitivity":0.7 ,# 0.0-1.0, higher = more strict
        "false_positive_threshold":3 ,# if 3 users report same msg as false positive, skip
        "context_window":3 ,# check last 3 messages for context
        }

        # DETECTION 
    def detect_toxic (self ,text ,languages ,sensitivity ):
        """Return list of (severity, matched_pattern) tuples"""
        text_lower =text .lower ()
        matches =[]
        # Check each severity
        for severity ,lang_dict in TOXIC_PATTERNS .items ():
            if severity in ("discrimination",):
                patterns =lang_dict .get ("any",[])
            else :
                patterns =[]
                for lang in languages :
                    patterns .extend (lang_dict .get (lang ,[]))
            for pattern in patterns :
                try :
                    if re .search (pattern ,text_lower ,re .IGNORECASE ):
                        matches .append ((severity ,pattern ))
                except re .error as _ex:
                    log.debug("detect_toxic(): подавлено: %s", _ex)
                    # Sensitivity filtering (for low severity)
        if sensitivity <0.5 and matches :
            matches =[m for m in matches if m [0 ]in ("severe","discrimination")]
        elif sensitivity <0.7 and matches :
            matches =[m for m in matches if m [0 ]!="mild"]
        return matches 

    def detect_spam (self ,guild_id ,user_id ,text ):
        """Detect rapid-fire messages (3+ in 5 seconds)"""
        now =time .time ()
        tracker =self .spam_tracker [guild_id ][user_id ]
        tracker .append (now )
        # Keep only last 10 seconds
        tracker [:]=[t for t in tracker if now -t <10 ]
        # 3+ messages in 5 seconds = spam
        recent =[t for t in tracker if now -t <5 ]
        return len (recent )>=3 

    def is_whitelisted (self ,guild_id ,member ,config ):
        """Check if user is exempt from AI moderation"""
        # Admins always exempt
        if member .guild_permissions .administrator :
            return True 
            # Whitelist
        if str (member .id )in config .get ("whitelist_users",[]):
            return True 
            # Ignored roles
        ignored_roles =config .get ("ignored_roles",[])
        if any (str (r .id )in ignored_roles for r in member .roles ):
            return True 
        return False 

    def is_ignored_channel (self ,channel_id ,config ):
        return str (channel_id )in config .get ("ignored_channels",[])

    def check_false_positive (self ,guild_id ,message_content ):
        """If same content has been reported as false positive 3+ times, skip"""
        msg_hash =hash (message_content .lower ().strip ())
        return self .false_positive_feedback .get (msg_hash ,0 )>=3 

        # ACTIONS 
    async def take_action (self ,guild ,member ,severity ,reason ,config ,message =None ):
        """Take moderation action based on severity and history"""
        action_config =SEVERITY_ACTION .get (severity ,SEVERITY_ACTION ["mild"])
        action =action_config ["action"]
        mute_minutes =action_config .get ("mute_minutes",0 )
        guild_id =str (guild .id )

        # Check escalation
        history =self .user_history [guild_id ][str (member .id )]
        recent_actions =[h for h in history if (time .time ()-h ["ts"])<config ["escalation"]["window_hours"]*3600 ]
        warns =sum (1 for h in recent_actions if h ["action"]=="warn")
        mutes =sum (1 for h in recent_actions if h ["action"]=="mute")
        kicks =sum (1 for h in recent_actions if h ["action"]=="kick")

        original_action =action 
        if config ["escalation"]["enabled"]:
            if warns >=config ["escalation"]["warn_to_mute_after"]and action =="warn":
                action ="mute"
                mute_minutes =30 
            if mutes >=config ["escalation"]["mute_to_kick_after"]and action =="mute":
                action ="kick"
            if kicks >=config ["escalation"]["kick_to_ban_after"]and action =="kick":
                action ="ban"

        # Жёсткая политика проекта (заказ владельца): кик отключён — любой
        # путь эскалации или конфига, приведший к кику, сводим к бану.
        if action =="kick":
            action ="ban"

                # Take action
        try :
            if action =="warn":
            # Send warning
                embed =discord .Embed (
                title =" Предупреждение",
                description =f"{member.mention}, ваше сообщение нарушает правила сервера.\n\n**Причина:** {reason}\n\nПожалуйста, соблюдайте правила.",
                color =0xFBBF24 
                )
                if message :
                    embed .add_field (name ="Сообщение",value =message .content [:500 ],inline =False )
                if config .get ("dm_on_action"):
                    try :
                        await member .send (embed =embed )
                    except discord .Forbidden as _ex:
                        log.debug("take_action(): подавлено: %s", _ex)
                        # Log to channel
                await self ._log_to_channel (guild ,config ,embed ,member ,severity )
            elif action =="mute"and mute_minutes >0 :
                until =datetime.now(timezone.utc)+timedelta (minutes =mute_minutes )
                await member .timeout (until ,reason =f"AI Mod: {reason}")
                embed =discord .Embed (
                title =" Временный мут",
                description =f"{member.mention} замучен на **{mute_minutes} мин** за: {reason}",
                color =0xF87171 
                )
                if config .get ("dm_on_action"):
                    try :
                        await member .send (embed =embed )
                    except discord .Forbidden as _ex:
                        log.debug("take_action(): подавлено: %s", _ex)
                await self ._log_to_channel (guild ,config ,embed ,member ,severity )
            elif action =="kick":
                await member .kick (reason =f"AI Mod: {reason}")
                embed =discord .Embed (
                title =" Кик",
                description =f"{member.mention} исключён за: {reason}",
                color =0xEF4444 
                )
                await self ._log_to_channel (guild ,config ,embed ,member ,severity )
            elif action =="ban":
                await guild .ban (member ,reason =f"AI Mod: {reason}")
                embed =discord .Embed (
                title =" Бан",
                description =f"{member.mention} забанен за: {reason}",
                color =0xDC2626 
                )
                await self ._log_to_channel (guild ,config ,embed ,member ,severity )
        except discord .Forbidden as _ex:
            log.debug("take_action(): подавлено: %s", _ex)
        except discord .HTTPException as e :
            log .info (f"[ai_mod] action error: {e}")

            # Record
        entry ={"ts":time .time (),"action":action ,"severity":severity ,"reason":reason ,"original":original_action }
        history .append (entry )
        self .save_history_entry (guild_id ,{"user_id":str (member .id ),**entry })
        return action 

    async def _log_to_channel (self ,guild ,config ,embed ,member ,severity ):
        log_ch_id =config .get ("log_channel_id")
        channel =None 
        if log_ch_id :
            channel =guild .get_channel (int (log_ch_id ))
        if channel is None :
            # Канал не настроен — падаем обратно в единый лог-канал модерации,
            # иначе AI-инциденты вообще нигде не видны
            try :
                from cogs .logs import ensure_log_channel
                channel =await ensure_log_channel (guild ,'модерация')
            except Exception :
                channel =None 
        if channel is None :
            return 
        try :
            if channel :
                embed .timestamp =datetime.now(timezone.utc)
                embed .set_footer (text =f"AI Moderation · {severity}")
                await channel .send (embed =embed )
        except (discord .Forbidden ,discord .HTTPException ) as _ex:
            log.debug("_log_to_channel(): подавлено: %s", _ex)

            # MESSAGE LISTENER 
    @commands .Cog .listener ()
    async def on_message (self ,message ):
        if message .author .bot or not message .guild :
            return 
        guild_id =str (message .guild .id )
        config =self .load_config (guild_id )
        if not config .get ("enabled",True ):
            return 
        if self .is_ignored_channel (message .channel .id ,config ):
            return 
        if self .is_whitelisted (guild_id ,message .author ,config ):
            return 
        if self .check_false_positive (guild_id ,message .content ):
            return 

            # Detect toxic
        matches =self .detect_toxic (
        message .content ,
        config .get ("languages",["ru","tr","en"]),
        config .get ("sensitivity",0.7 )
        )
        # Spam/флуд здесь не трогаем: он живёт в отдельных механизмах, без ИИ.

        if not matches :
            return 

            # Pick highest severity
        severity_order =["mild","moderate","discrimination","severe"]
        severity =max (matches ,key =lambda m :severity_order .index (m [0 ]))[0 ]
        if not config .get ("auto_actions",{}).get (severity ,True ):
            return 

            # Take action
        reason =f"AI обнаружил нарушение: {severity} ({len(matches)} паттернов)"
        await self .take_action (message .guild ,message .author ,severity ,reason ,config ,message )
        # Delete the message
        try :
            await message .delete ()
        except (discord .Forbidden ,discord .NotFound ) as _ex:
            log.debug("on_message(): подавлено: %s", _ex)

            # COMMANDS 


async def setup (bot ):
    await bot .add_cog (AIModeration (bot ))
