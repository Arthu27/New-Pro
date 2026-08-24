"""
Aether Security Cog
- AI поддержка spam tespiti (pattern + скорость + benzerlik analizi)
- Обнаружение фейковых аккаунтов (новый аккаунт, нет аватара, подозрительное имя)
- Сканер безопасности ссылок (список вредоносных доменов + URL-сокращатели)
- Система автоматических бэкапов (резервная копия настроек сервера)
"""

from logger import get_logger

_log = get_logger("security")

from json_store import load_json as _js_load, save_json as _js_save

import discord 
from discord .ext import commands ,tasks 
from discord import app_commands 
import json ,os ,re ,time ,math 
from collections import defaultdict 
from datetime import datetime ,timezone ,timedelta 
from config import Config 

#  Zararlы domain список 
MALICIOUS_DOMAINS ={
# Phishing / scam
'grabify.link','iplogger.org','blasze.tk','ps3cfw.com',
'bit.ly','tinyurl.com','shorturl.at','cutt.ly','rb.gy',
'discord-nitro.gift','discordapp.gift','steamcommunity.ru',
'free-nitro.ru','nitro-discord.ru','discord-gift.ru',
'freestuff.gg','discord.gift','dlscord.com','discorcl.com',
# Malware
'mediafire.com','anonfiles.com','gofile.io',
}

# Подозрительное имя pattern'leri
SUSPICIOUS_NAME_PATTERNS =[
r'discord.*nitro',r'free.*nitro',r'steam.*gift',
r'admin.*\d{4}',r'mod.*\d{4}',r'support.*\d{4}',
r'giveaway',r'free.*gift',r'claim.*reward',
]

DATA_FILE ='data/security_{guild_id}.json'
BACKUP_DIR ='data/backups'

_CFG_DEFAULT ={
'ai_spam':False ,# opt-in
'fake_account':False ,# opt-in
'link_scanner':False ,# opt-in
'new_account_days':7 ,
'new_account_action':'warn',# warn | kick | ban
'log_channel':None ,
}

def _load_cfg (guild_id ):
    return _js_load (DATA_FILE .format (guild_id =guild_id ),_CFG_DEFAULT ,log =_log )

def _save_cfg (guild_id ,data ):
    _js_save (DATA_FILE .format (guild_id =guild_id ),data ,log =_log )

def _similarity (a :str ,b :str )->float :
    """Схожесть двух строк (0-1). По расстоянию Левенштейна."""
    if not a or not b :
        return 0.0 
    a ,b =a .lower (),b .lower ()
    if a ==b :
        return 1.0 
    la ,lb =len (a ),len (b )
    if abs (la -lb )/max (la ,lb )>0.5 :
        return 0.0 
        # Basit karakter ёrtюшme oranы
    common =sum (1 for c in a if c in b )
    return common /max (la ,lb )

def _extract_domains (text :str )->list :
    """Metinden domain'leri удалить."""
    pattern =re .compile (
    r'(?:https?://|www\.)([a-zA-Z0-9\-\.]+\.[a-zA-Z]{2,})',
    re .IGNORECASE 
    )
    return [m .group (1 ).lower ()for m in pattern .finditer (text )]

def _is_suspicious_name (name :str )->bool :
    name_lower =name .lower ()
    for pattern in SUSPICIOUS_NAME_PATTERNS :
        if re .search (pattern ,name_lower ):
            return True 
    return False 


class Security (commands .Cog ):
    def __init__ (self ,bot ):
        self .bot =bot 
        # AI spam tracking: uid -> [(timestamp, content), ...]
        self .msg_history :dict [int ,list ]=defaultdict (list )
        # Burst tracking: uid -> [timestamps]
        self .burst_tracker :dict [int ,list ]=defaultdict (list )
        self .backup_loop .start ()

    def cog_unload (self ):
        self .backup_loop .cancel ()

        #  Log helper 
    async def _log (self ,guild :discord .Guild ,embed :discord .Embed ,cfg :dict ):
        ch_id =cfg .get ('log_channel')
        ch =guild .get_channel (int (ch_id ))if ch_id else None 
        if not ch :
            # Единый резолвер: -модерация → mod-log → moderasyon → …
            try :
                from cogs .logs import ensure_log_channel
                ch =await ensure_log_channel (guild ,'модерация')
            except Exception :
                ch =None 
        if not ch :
            ch =discord .utils .get (guild .text_channels ,name ='mod-log')
        if ch :
            try :
                await ch .send (embed =embed )
            except Exception as _ex:
                _log.debug("_log(): подавлено: %s", _ex)

                #  AI Антиспам Analizi 
    def _ai_spam_score (self ,uid :int ,content :str )->tuple [float ,str ]:
        """
        Проанализировать сообщение и вернуть оценку спама (0.0–1.0) и причину.
        Мультисигнал: скорость + схожесть + повторы + аномалия длины
        """
        now =time .time ()
        window =8 # секунд
        history =self .msg_history [uid ]

        # Старый запись clear
        history =[(t ,c )for t ,c in history if now -t <30 ]
        self .msg_history [uid ]=history 

        signals =[]

        # 1. Скорость sinyali: 8 saniyede сколько message?
        recent =[t for t ,_ in history if now -t <window ]
        speed_score =min (len (recent )/6 ,1.0 )# 6+ message = 1.0
        if speed_score >0.5 :
            signals .append (f"скорость ({len(recent)} message/{window}s)")

            # 2. Benzerlik sinyali: son messagelara ne kadar benziyor?
        if history :
            sims =[_similarity (content ,c )for _ ,c in history [-5 :]]
            avg_sim =sum (sims )/len (sims )
            sim_score =avg_sim 
            if sim_score >0.7 :
                signals .append (f"benzerlik ({avg_sim:.0%})")
        else :
            sim_score =0.0 

            # 3. Сигнал повтора: одинаковое содержимое сколько раз?
        repeat_count =sum (1 for _ ,c in history if c .lower ()==content .lower ())
        repeat_score =min (repeat_count /3 ,1.0 )
        if repeat_score >0.5 :
            signals .append (f"повтор ({repeat_count}x)")

            # 4. Длинныйluk anomalisi: очень краткий + очень быстрый
        length_score =0.3 if len (content )<5 and speed_score >0.4 else 0.0 

        # весомая оценка
        final_score =(
        speed_score *0.35 +
        sim_score *0.35 +
        repeat_score *0.20 +
        length_score *0.10 
        )

        # История add
        self .msg_history [uid ].append ((now ,content ))

        reason =" + ".join (signals )if signals else "normal"
        return final_score ,reason 

        #  Фейковые аккаунты Tespiti 
    def _fake_account_score (self ,member :discord .Member ,cfg :dict )->tuple [float ,list ]:
        """Оценка риска фейкового аккаунта (0–1) и список предупреждений."""
        warnings =[]
        score =0.0 

        # Hesap yaшы
        age_days =(datetime.now(timezone.utc)-member .created_at ).days 
        threshold =cfg .get ('new_account_days',7 )
        if age_days <1 :
            score +=0.5 
            warnings .append (f" Hesap **{age_days} ежедневный** (очень новый!)")
        elif age_days <threshold :
            score +=0.3 
            warnings .append (f" Hesap **{age_days} ежедневный** ({threshold} день az)")

            # Default avatar
        if member .display_avatar .is_animated ()is False and 'embed'in str (member .display_avatar .url ):
            score +=0.2 
            warnings .append ("ℹ️ Используется стандартный аватар")

            # Подозрительное имя
        if _is_suspicious_name (member .name )or _is_suspicious_name (member .display_name ):
            score +=0.4 
            warnings .append (f"⚠️ Подозрительное имя пользователя: `{member.name}`")

            # Discriminator 0000 (старый система bot pattern'i)
        if hasattr (member ,'discriminator')and member .discriminator =='0000':
            score +=0.1 
            warnings .append ("ℹ Новый user имя система")

        return min (score ,1.0 ),warnings 

        #  Сканер ссылок 
    def _scan_links (self ,content :str )->tuple [bool ,list ]:
        """Есть ли вредоносная ссылка? (bool, найденные домены)"""
        domains =_extract_domains (content )
        found =[]
        for domain in domains :
        # Tam eшleшme
            if domain in MALICIOUS_DOMAINS :
                found .append (domain )
                continue 
                # Низ domain контроль (напр.: evil.grabify.link)
            for bad in MALICIOUS_DOMAINS :
                if domain .endswith ('.'+bad )or domain ==bad :
                    found .append (domain )
                    break 
        return bool (found ),found 

        #  Event Listeners 
    @commands .Cog .listener ()
    async def on_message (self ,message :discord .Message ):
        if message .author .bot or not message .guild :
            return 
        if (message .author .guild_permissions .moderate_members or 
        message .author .guild_permissions .administrator ):
            return 

        cfg =_load_cfg (str (message .guild .id ))
        guild =message .guild 
        member =message .author 

        #  Сканер ссылок 
        if cfg .get ('link_scanner',False ):
            has_bad ,bad_domains =self ._scan_links (message .content )
            if has_bad :
                try :
                    await message .delete ()
                except Exception as _ex:
                    _log.debug("on_message(): подавлено: %s", _ex)
                e =discord .Embed (
                title ="🛡️ Вредоносная ссылка заблокирована",
                color =0xe74c3c ,
                timestamp =datetime .now (timezone .utc )
                )
                e .description =(
                f"{member.mention} поделился вредоносной/подозрительной ссылкой!\n\n"
                "**🌐 Обнаруженные домены:**\n"
                +"\n".join (f"• `{d}`"for d in bad_domains )
                )
                e .set_thumbnail (url =member .display_avatar .url )
                e .set_footer (text =" Aether Сканер ссылок")
                await self ._log (guild ,e ,cfg )
                try :
                    await message .channel .send (
                    f" {member.mention} вредоносный link engellendi!",
                    delete_after =5 
                    )
                except Exception as _ex:
                    _log.debug("on_message(): подавлено: %s", _ex)
                return 

                #  AI Антиспам Tespiti 
        if cfg .get ('ai_spam',False ):
            score ,reason =self ._ai_spam_score (member .id ,message .content )

            if score >=0.85 :
            # Высокий доверие → удалить + timeout
                try :
                    await message .delete ()
                except Exception as _ex:
                    _log.debug("on_message(): подавлено: %s", _ex)
                try :
                    await member .timeout (
                    datetime.now(timezone.utc)+timedelta (minutes =5 ),
                    reason =f"AI Антиспам Tespiti: {reason}"
                    )
                except Exception as _ex:
                    _log.debug("on_message(): подавлено: %s", _ex)
                e =discord .Embed (
                title =" AI Антиспам Tespiti — Высокий Risk",
                color =0xe74c3c ,
                timestamp =datetime .now (timezone .utc )
                )
                e .description =f"**Сканирование:** `{score:.0%}` | **Причина:** {reason}\n**⏳ Наказание:** мут на 5 минут"
                e .set_thumbnail (url =member .display_avatar .url )
                e .add_field (name =" Пользователь",value =f"{member.mention} `{member.id}`",inline =True )
                e .add_field (name =" Канал",value =message .channel .mention ,inline =True )
                e .set_footer (text =" Aether AI Security")
                await self ._log (guild ,e ,cfg )

            elif score >=0.65 :
            # Центр доверие → только удалить + uyar
                try :
                    await message .delete ()
                except Exception as _ex:
                    _log.debug("on_message(): подавлено: %s", _ex)
                try :
                    await message .channel .send (
                    f" {member.mention} spam yapma!",
                    delete_after =5 
                    )
                except Exception as _ex:
                    _log.debug("on_message(): подавлено: %s", _ex)
                e =discord .Embed (
                title =" AI Антиспам Tespiti — Центр Risk",
                color =0xf39c12 ,
                timestamp =datetime .now (timezone .utc )
                )
                e .description =f"**Сканирование:** `{score:.0%}` | **Причина:** {reason}"
                e .set_thumbnail (url =member .display_avatar .url )
                e .add_field (name =" Пользователь",value =f"{member.mention} `{member.id}`",inline =True )
                e .set_footer (text =" Aether AI Security")
                await self ._log (guild ,e ,cfg )

    @commands .Cog .listener ()
    async def on_member_join (self ,member :discord .Member ):
        cfg =_load_cfg (str (member .guild .id ))
        if not cfg .get ('fake_account',True ):
            return 

        score ,warnings =self ._fake_account_score (member ,cfg )
        if score <0.3 :
            return 

        guild =member .guild 
        action =cfg .get ('new_account_action','warn')

        e =discord .Embed (
        title ="⚠️ Обнаружен подозрительный аккаунт",
        color =0xe74c3c if score >=0.6 else 0xf39c12 ,
        timestamp =datetime .now (timezone .utc )
        )
        e .set_thumbnail (url =member .display_avatar .url )
        e .description ="\n".join (warnings )
        e .add_field (name =" Пользователь",value =f"{member.mention}\n`{member.id}`",inline =True )
        e .add_field (name =" Возраст аккаунта",value =f"`{(datetime.now(timezone.utc) - member.created_at).days} день`",inline =True )
        e .add_field (name =" Уровень риска",value =f"`{score:.0%}`",inline =True )

        if score >=0.6 and action =='kick':
            try :
                await member .kick (reason ="Fake hesap tespiti")
                e .add_field (name =" Действие",value ="```Kick применено```",inline =False )
            except Exception as _ex:
                _log.debug("on_member_join(): подавлено: %s", _ex)
        elif score >=0.8 and action =='ban':
            try :
                await member .ban (reason ="Fake hesap tespiti")
                e .add_field (name =" Действие",value ="```Ban применено```",inline =False )
            except Exception as _ex:
                _log.debug("on_member_join(): подавлено: %s", _ex)
        else :
            e .add_field (name =" Действие",value ="```Модератор уведомление отправлено```",inline =False )

        e .set_footer (text =" Aether Безопасность Система")
        await self ._log (guild ,e ,cfg )

        #  Slash Команды 
    @app_commands .command (name ="security",description ="Показать настройки безопасности")
    @app_commands .checks .has_permissions (administrator =True )
    async def security_status (self ,interaction :discord .Interaction ):
        cfg =_load_cfg (str (interaction .guild .id ))
        e =discord .Embed (
        title =" Безопасность Система Состояние",
        color =0x2ecc71 ,
        timestamp =datetime .now (timezone .utc )
        )
        e .add_field (name =" AI Антиспам",value =" Активен"if cfg .get ('ai_spam')else " Закрыт",inline =True )
        e .add_field (name =" Фейковые аккаунты",value =" Активен"if cfg .get ('fake_account')else " Закрыт",inline =True )
        e .add_field (name =" Сканер ссылок",value =" Активен"if cfg .get ('link_scanner')else " Закрыт",inline =True )
        e .add_field (name =" Порог нового аккаунта",value =f"`{cfg.get('new_account_days', 7)} день`",inline =True )
        e .add_field (name ="🆕 Действие для новых аккаунтов",value =f"`{cfg.get('new_account_action', 'warn')}`",inline =True )
        e .set_footer (text =" Aether Security")
        await interaction .response .send_message (embed =e ,ephemeral =True )

    @app_commands .command (name ="security-toggle",description ="Включить/отключить функцию безопасности")
    @app_commands .describe (feature ="Функция",enabled ="Вкл/Выкл")
    @app_commands .choices (feature =[
    app_commands .Choice (name ="AI-детект спама",value ="ai_spam"),
    app_commands .Choice (name ="Детект фейковых аккаунтов",value ="fake_account"),
    app_commands .Choice (name ="Сканер ссылок",value ="link_scanner"),
    ])
    @app_commands .checks .has_permissions (administrator =True )
    async def security_toggle (self ,interaction :discord .Interaction ,feature :str ,enabled :bool ):
        cfg =_load_cfg (str (interaction .guild .id ))
        cfg [feature ]=enabled 
        _save_cfg (str (interaction .guild .id ),cfg )
        status =" Активен"if enabled else " Закрыт"
        await interaction .response .send_message (
        f" **{feature}** → {status}",ephemeral =True 
        )

    @app_commands .command (name ="security-newaccount",description ="Настроить действие для новых аккаунтов")
    @app_commands .describe (days ="Возраст аккаунта в днях, младше которого он подозрителен",action ="Действие")
    @app_commands .choices (action =[
    app_commands .Choice (name ="Только Bildir",value ="warn"),
    app_commands .Choice (name ="Kick",value ="kick"),
    app_commands .Choice (name ="Ban",value ="ban"),
    ])
    @app_commands .checks .has_permissions (administrator =True )
    async def security_newaccount (self ,interaction :discord .Interaction ,days :int ,action :str ):
        cfg =_load_cfg (str (interaction .guild .id ))
        cfg ['new_account_days']=days 
        cfg ['new_account_action']=action 
        _save_cfg (str (interaction .guild .id ),cfg )
        await interaction .response .send_message (
        f" Порог возраста нового аккаунта: **{days} дн.** | Действие: **{action}**",ephemeral =True 
        )

    @app_commands .command (name ="scan-link",description ="Проверить ссылку сканером безопасности")
    @app_commands .describe (url ="Taranacak URL")
    @app_commands .checks .has_permissions (moderate_members =True )
    async def scan_link (self ,interaction :discord .Interaction ,url :str ):
        has_bad ,bad_domains =self ._scan_links (url )
        if has_bad :
            e =discord .Embed (title ="⛔ Вредоносная ссылка!",color =0xe74c3c )
            e .description ="Эта ссылка содержит вредоносный/подозрительный домен:\n"+"\n".join (f"• `{d}`"for d in bad_domains )
        else :
            e =discord .Embed (title =" Ссылка чиста",color =0x2ecc71 )
            e .description ="Эта ссылка не найдена в списках известных вредоносных доменов."
        e .add_field (name =" URL",value =f"`{url[:100]}`",inline =False )
        e .set_footer (text =" Aether Сканер ссылок")
        await interaction .response .send_message (embed =e ,ephemeral =True )

        #  Автоматически Backup 
    @tasks .loop (hours =24 )
    async def backup_loop (self ):
        """Резервное копирование настроек всех серверов каждые 24 часа."""
        for guild in self .bot .guilds :
            await self ._backup_guild (guild )

    @backup_loop .before_loop 
    async def before_backup (self ):
        await self .bot .wait_until_ready ()

    async def _backup_guild (self ,guild :discord .Guild ):
        os .makedirs (BACKUP_DIR ,exist_ok =True )
        timestamp =datetime .now ().strftime ('%Y%m%d_%H%M')
        backup ={
        'guild_id':str (guild .id ),
        'guild_name':guild .name ,
        'timestamp':timestamp ,
        'member_count':guild .member_count ,
        'role':[
        {
        'id':str (r .id ),'name':r .name ,
        'color':str (r .color ),'hoist':r .hoist ,
        'mentionable':r .mentionable ,'position':r .position ,
        'permissions':r .permissions .value 
        }
        for r in guild .roles if not r .managed 
        ],
        'channels':[
        {
        'id':str (c .id ),'name':c .name ,
        'type':str (c .type ),'position':c .position ,
        'category':c .category .name if hasattr (c ,'category')and c .category else None 
        }
        for c in guild .channels 
        ],
        'categories':[
        {'id':str (c .id ),'name':c .name ,'position':c .position }
        for c in guild .categories 
        ],
        }
        path =os .path .join (BACKUP_DIR ,f'backup_{guild.id}_{timestamp}.json')
        with open (path ,'w',encoding ='utf-8')as f :
            json .dump (backup ,f ,indent =2 ,ensure_ascii =False )

            # Старый yedaddri clear (son 7 tane tut)
        all_backups =sorted ([
        x for x in os .listdir (BACKUP_DIR )
        if x .startswith (f'backup_{guild.id}_')
        ])
        for old in all_backups [:-7 ]:
            try :
                os .remove (os .path .join (BACKUP_DIR ,old ))
            except Exception as _ex:
                _log.debug("_backup_guild(): подавлено: %s", _ex)

    @app_commands .command (name ="backup",description ="Создать резервную копию настроек сервера")
    @app_commands .checks .has_permissions (administrator =True )
    async def backup_now (self ,interaction :discord .Interaction ):
        await interaction .response .defer (ephemeral =True )
        await self ._backup_guild (interaction .guild )
        # Показать список резервных копий
        backups =sorted ([
        x for x in os .listdir (BACKUP_DIR )
        if x .startswith (f'backup_{interaction.guild.id}_')
        ],reverse =True )
        e =discord .Embed (title ="✅ Резервная копия создана",color =0x2ecc71 ,timestamp =datetime .now (timezone .utc ))
        e .description =f"Настройки сервера **{interaction.guild.name}** скопированы."
        e .add_field (
        name =f"💾 Текущие копии ({len(backups)})",
        value ="\n".join (f"• `{b}`"for b in backups [:5 ])or "Нет",
        inline =False 
        )
        e .set_footer (text ="💾 Aether Backup • ежедневное авто-копирование активно")
        await interaction .followup .send (embed =e ,ephemeral =True )

    @app_commands .command (name ="backup-list",description ="Показать список резервных копий")
    @app_commands .checks .has_permissions (administrator =True )
    async def backup_list (self ,interaction :discord .Interaction ):
        if not os .path .exists (BACKUP_DIR ):
            await interaction .response .send_message ("📦 Копий пока нет.",ephemeral =True )
            return 
        backups =sorted ([
        x for x in os .listdir (BACKUP_DIR )
        if x .startswith (f'backup_{interaction.guild.id}_')
        ],reverse =True )
        e =discord .Embed (title ="💾 Резервные копии сервера",color =0x3498db ,timestamp =datetime .now (timezone .utc ))
        if not backups :
            e .description ="Копий пока не найдено. Создайте копию командой `/backup`."
        else :
            e .description ="\n".join (f"• `{b}`"for b in backups )
        e .set_footer (text ="💾 Хранятся последние 7 копий")
        await interaction .response .send_message (embed =e ,ephemeral =True )


async def setup (bot ):
    await bot .add_cog (Security (bot ),guilds =Config .guild_objects ())
