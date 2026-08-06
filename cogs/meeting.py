"""Система собраний — собирает реальные данные, сканируя историю сообщений Discord"""
import discord 
from discord .ext import commands 
from discord import app_commands 
import json 
import os 
import datetime 
import asyncio 

from logger import get_logger 
log =get_logger ("meeting")


DATA_DIR ='data'


def _cfg_file (guild_id :int )->str :
    return f'{DATA_DIR}/meeting_{guild_id}.json'


def _load_cfg (guild_id :int )->dict :
    path =_cfg_file (guild_id )
    # До meeting config'i загрузить
    cfg ={
    'last_meeting':None ,
    'active':False ,
    'panel_channel':None ,
    'panel_message':None ,
    'staff_roles':[],
    }
    if os .path .exists (path ):
        try :
            with open (path ,'r',encoding ='utf-8')as f :
                cfg .update (json .load (f ))
        except Exception :
            pass 

            # mod_report_config'den staff_roles'u da al (birleшtir)
    mod_cfg_path =f'{DATA_DIR}/mod_report_config_{guild_id}.json'
    if os .path .exists (mod_cfg_path )and not cfg .get ('staff_roles'):
        try :
            with open (mod_cfg_path ,'r',encoding ='utf-8')as f :
                mod_cfg =json .load (f )
            if mod_cfg .get ('staff_roles'):
                cfg ['staff_roles']=mod_cfg ['staff_roles']
        except Exception :
            pass 

    return cfg 


def _save_cfg (guild_id :int ,cfg :dict ):
    os .makedirs (DATA_DIR ,exist_ok =True )
    with open (_cfg_file (guild_id ),'w',encoding ='utf-8')as f :
        json .dump (cfg ,f ,ensure_ascii =False ,indent =2 )


def _guild_embed_base (guild :discord .Guild ,title :str ,color :int )->discord .Embed :
    """Красивый embed с баннером и аватаром сервера"""
    embed =discord .Embed (title =title ,color =color )
    if guild .icon :
        embed .set_thumbnail (url =guild .icon .url )
    if guild .banner :
        embed .set_image (url =guild .banner .url )
    embed .set_footer (
    text =f'{guild.name}  ·  Собрание Система',
    icon_url =guild .icon .url if guild .icon else None 
    )
    return embed 


async def _scan_messages (guild :discord .Guild ,since :datetime .datetime )->dict :
    """
Сканировать сообщения во всех каналах с момента завершения собрания.
    Returns: {user_id: message_count}
    """
    msg_counts ={}
    scanned =0 

    for channel in guild .text_channels :
        if not channel .permissions_for (guild .me ).read_message_history :
            continue 
        try :
            async for msg in channel .history (after =since ,limit =None ):
                if msg .author .bot :
                    continue 
                uid =str (msg .author .id )
                msg_counts [uid ]=msg_counts .get (uid ,0 )+1 
                scanned +=1 
        except Exception :
            continue 

    log .info (f'[Meeting] {guild.name}: отсканировано {scanned} сообщений, {len(msg_counts)} участников')
    return msg_counts 


async def _scan_voice (guild :discord .Guild ,since :datetime .datetime )->dict :
    """
    Получить голосовые данные из файла voice_stats после собрания.
    Примечание: voice_tracker показывает мгновенное число, собрание основано на снимке.
    Returns: {user_id: seconds}
    """
    vs_path =f'{DATA_DIR}/voice_stats_{guild.id}.json'
    snapshot_path =f'{DATA_DIR}/meeting_snapshot_{guild.id}.json'

    current ={}
    if os .path .exists (vs_path ):
        try :
            with open (vs_path ,'r',encoding ='utf-8')as f :
                vs =json .load (f )
            for uid ,d in vs .get ('users',{}).items ():
                secs =d .get ('total_seconds',0 )if isinstance (d ,dict )else int (d )
                current [uid ]=secs 
        except Exception :
            pass 

            # Снимок — значение на начало собрания
    snapshot ={}
    if os .path .exists (snapshot_path ):
        try :
            with open (snapshot_path ,'r',encoding ='utf-8')as f :
                snapshot =json .load (f )
        except Exception :
            pass 

            # Разница = длительность, набранная за это собрание
    result ={}
    for uid ,secs in current .items ():
        prev =snapshot .get (uid ,0 )
        diff =secs -prev 
        if diff >0 :
            result [uid ]=diff 

    return result 


def _save_voice_snapshot (guild_id :int ):
    """Текущий ses данные snapshot как сохранить"""
    vs_path =f'{DATA_DIR}/voice_stats_{guild_id}.json'
    snapshot_path =f'{DATA_DIR}/meeting_snapshot_{guild_id}.json'

    if os .path .exists (vs_path ):
        try :
            with open (vs_path ,'r',encoding ='utf-8')as f :
                vs =json .load (f )
            snapshot ={}
            for uid ,d in vs .get ('users',{}).items ():
                secs =d .get ('total_seconds',0 )if isinstance (d ,dict )else int (d )
                snapshot [uid ]=secs 
            with open (snapshot_path ,'w',encoding ='utf-8')as f :
                json .dump (snapshot ,f )
        except Exception :
            pass 


def _load_invites (guild_id :int )->dict :
    path =f'{DATA_DIR}/invite_counts_{guild_id}.json'
    if os .path .exists (path ):
        try :
            with open (path ,'r',encoding ='utf-8')as f :
                data =json .load (f )
            result ={}
            for uid ,val in data .items ():
                if isinstance (val ,dict ):
                    result [uid ]=val .get ('total',val .get ('count',val .get ('uses',0 )))
                else :
                    result [uid ]=int (val )
            return result 
        except Exception :
            pass 
    return {}


def _bar (value :int ,max_val :int ,length :int =10 )->str :
    if max_val ==0 :
        return ''*length 
    filled =int ((value /max_val )*length )
    return ''*filled +''*(length -filled )


async def _build_meeting_report (guild :discord .Guild ,since :datetime .datetime )->list [discord .Embed ]:
    """Собрание raporu embed список"""
    now =datetime .datetime .now (datetime .timezone .utc )
    ts_since =int (since .timestamp ())
    ts_now =int (now .timestamp ())

    # Данные собрать
    msg_counts =await _scan_messages (guild ,since )
    voice_data =await _scan_voice (guild ,since )
    invite_data =_load_invites (guild .id )

    cfg =_load_cfg (guild .id )
    staff_role_ids =cfg .get ('staff_roles',[])

    embeds =[]

    #  KAPAK 
    cover =discord .Embed (color =0x2B2D31 )
    cover .set_author (
    name =f'{guild.name}  ·  Собрание Raporu',
    icon_url =guild .icon .url if guild .icon else None 
    )
    cover .description =(
    '```ansi\n'
    '\u001b[1;34m\u001b[0m\n'
    '\u001b[1;34m      СОБРАНИЕ PERFORMANS RAPORU  \u001b[0m\n'
    '\u001b[1;34m\u001b[0m\n'
    '```\n'
    f'>  <t:{ts_since}:F> → <t:{ts_now}:F>\n'
    f'>  Всего участников: **{guild.member_count}**\n'
    f'>  Активен Пользователь: **{len(msg_counts)}**'
    )
    if guild .banner :
        cover .set_image (url =guild .banner .url )
    if guild .icon :
        cover .set_thumbnail (url =guild .icon .url )
    cover .set_footer (text =f'{guild.name}  ·  Собрание Система',icon_url =guild .icon .url if guild .icon else None )
    embeds .append (cover )

    #  ОБЩИЙ ОЧЕРЕДЬ (Сообщение + Ses) 
    from collections import defaultdict 
    scores =defaultdict (lambda :{'msg':0 ,'voice':0 ,'inv':0 ,'score':0 })
    for uid ,cnt in msg_counts .items ():
        scores [uid ]['msg']=cnt 
        scores [uid ]['score']+=cnt 
    for uid ,secs in voice_data .items ():
        mins =secs //60 
        scores [uid ]['voice']=secs 
        scores [uid ]['score']+=mins *2 
    for uid ,cnt in invite_data .items ():
        scores [uid ]['inv']=cnt 
        scores [uid ]['score']+=cnt *5 

    top5 =sorted (scores .items (),key =lambda x :x [1 ]['score'],reverse =True )[:5 ]
    max_score =top5 [0 ][1 ]['score']if top5 else 1 

    overall =discord .Embed (title ='  Общий Очередь — Top 5',color =0xF1C40F )
    if guild .icon :
        overall .set_thumbnail (url =guild .icon .url )
    medals =['','','','4','5']
    lines =[]
    for i ,(uid ,s )in enumerate (top5 ):
        m =guild .get_member (int (uid ))
        name =m .display_name if m else f'<@{uid}>'
        bar =_bar (s ['score'],max_score )
        h ,mn =divmod (s ['voice']//60 ,60 )
        lines .append (
        f'{medals[i]} **{name}**\n'
        f' {bar} `{s["score"]:,} очков`\n'
        f'  {s["msg"]:,}   {h}s{mn}dk   {s["inv"]}'
        )
    overall .description ='\n\n'.join (lines )or 'Данные нет.'
    overall .set_footer (text ='Очки: Сообщение×1 + Звук мин×2 + Приглашение×5',icon_url =guild .icon .url if guild .icon else None )
    embeds .append (overall )

    #  РОЛЬ BAZLI TOP 4 
    for role_id in staff_role_ids [:8 ]:
        role =guild .get_role (role_id )
        if not role or role .is_default ():
            continue 

        role_members =[m for m in role .members if not m .bot ]
        if not role_members :
            continue 

        role_scores =[]
        for member in role_members :
            uid =str (member .id )
            msg =msg_counts .get (uid ,0 )
            voice_secs =voice_data .get (uid ,0 )
            inv =invite_data .get (uid ,0 )
            score =msg +(voice_secs //60 )*2 +inv *5 
            role_scores .append ((member ,msg ,voice_secs ,inv ,score ))

        role_scores .sort (key =lambda x :x [4 ],reverse =True )
        top4 =role_scores [:4 ]
        if not top4 :
            continue 

        max_s =top4 [0 ][4 ]if top4 [0 ][4 ]>0 else 1 
        role_embed =discord .Embed (
        title =f'{role.name}  —  Top {min(4, len(top4))}',
        color =role .color .value if role .color .value else 0x5865F2 
        )
        if guild .icon :
            role_embed .set_thumbnail (url =guild .icon .url )

        rank_emojis =['','','','4']
        lines =[]
        for i ,(member ,msg ,voice_secs ,inv ,score )in enumerate (top4 ):
            bar =_bar (score ,max_s )
            h ,mn =divmod (voice_secs //60 ,60 )
            lines .append (
            f'{rank_emojis[i]} **{member.display_name}**\n'
            f' {bar} `{score:,} очки`\n'
            f'  {msg:,}   {h}s{mn}dk   {inv}'
            )
        role_embed .description ='\n\n'.join (lines )
        role_embed .set_footer (text =f'{role.name} • {len(role_members)} участник',icon_url =guild .icon .url if guild .icon else None )
        embeds .append (role_embed )

        # ЗАВЕРШЕНИЕ СОБРАНИЯ
    close =discord .Embed (color =0x57F287 )
    if guild .icon :
        close .set_thumbnail (url =guild .icon .url )
    close .description =(
    f'> Период отчёта: <t:{ts_since}:D> → <t:{ts_now}:D>\n'
    '> До следующего собрания данные продолжат накапливаться.\n\n'
    '-# Aether  ·  Система собраний'
    )
    close .set_footer (text =f'{guild.name}',icon_url =guild .icon .url if guild .icon else None )
    embeds .append (close )

    return embeds 


class MeetingStartModal (discord .ui .Modal ,title ='Собрание Запустить'):
    """Ввод времени начала собрания"""
    date_input =discord .ui .TextInput (
    label ='Время начала собрания',
    placeholder ='GG.AA.YYYY SS:DD  (напр.: 12.04.2026 22:00)',
    required =False ,
    max_length =20 
    )

    async def on_submit (self ,interaction :discord .Interaction ):
        cfg =_load_cfg (interaction .guild .id )

        # Время parse et
        date_str =self .date_input .value .strip ()
        if date_str :
            try :
                dt =datetime .datetime .strptime (date_str ,'%d.%m.%Y %H:%M')
                meeting_time =dt .replace (tzinfo =datetime .timezone .utc )
            except ValueError :
                await interaction .response .send_message (
                ' Format неверно! Напр.: `12.04.2026 22:00`',ephemeral =True 
                )
                return 
        else :
            meeting_time =datetime .datetime .now (datetime .timezone .utc )

        _save_voice_snapshot (interaction .guild .id )
        cfg ['active']=True 
        cfg ['meeting_start']=meeting_time .isoformat ()
        _save_cfg (interaction .guild .id ,cfg )

        # Paneli обновить
        try :
            view =MeetingView (interaction .guild .id )
            for item in view .children :
                if hasattr (item ,'custom_id')and item .custom_id =='meeting_start':
                    item .disabled =True 
            await interaction .message .edit (view =view )
        except Exception :
            pass 

        ts =int (meeting_time .timestamp ())
        embed =_guild_embed_base (interaction .guild ,'📢 Собрание началось',0x57F287 )
        embed .description =(
        f'> Начало собрания: <t:{ts}:F>\n'
        '> Сообщения и голосовая активность считаются с этого момента.\n\n'
        'Когда собрание закончится, нажмите кнопку **✅ Завершить собрание**.'
        )
        await interaction .response .send_message (embed =embed )


class MeetingView (discord .ui .View ):
    """Кнопки панели собрания"""

    def __init__ (self ,guild_id :int ):
        super ().__init__ (timeout =None )
        self .guild_id =guild_id 

    @discord .ui .button (
    label ='▶️ Запустить собрание',
    style =discord .ButtonStyle .success ,
    custom_id ='meeting_start',
    row =0 
    )
    async def start_meeting (self ,interaction :discord .Interaction ,button :discord .ui .Button ):
        if not interaction .user .guild_permissions .administrator :
            await interaction .response .send_message ('❌ Недостаточно прав.',ephemeral =True )
            return 

        cfg =_load_cfg (interaction .guild .id )
        if cfg .get ('active'):
            await interaction .response .send_message ('⚠️ Собрание уже активно!',ephemeral =True )
            return 

            # Открыть модалку — ввод времени
        await interaction .response .send_modal (MeetingStartModal ())

    @discord .ui .button (
    label ='✅ Завершить собрание',
    style =discord .ButtonStyle .danger ,
    custom_id ='meeting_end',
    row =0 
    )
    async def end_meeting (self ,interaction :discord .Interaction ,button :discord .ui .Button ):
        if not interaction .user .guild_permissions .administrator :
            await interaction .response .send_message ('❌ Недостаточно прав.',ephemeral =True )
            return 

        cfg =_load_cfg (interaction .guild .id )
        if not cfg .get ('active'):
            await interaction .response .send_message ('ℹ️ Нет активного собрания.',ephemeral =True )
            return 

        await interaction .response .defer ()

        since_str =cfg .get ('meeting_start')or cfg .get ('last_meeting')
        if since_str :
            since =datetime .datetime .fromisoformat (since_str )
            if since .tzinfo is None :
                since =since .replace (tzinfo =datetime .timezone .utc )
        else :
            since =datetime .datetime .now (datetime .timezone .utc )-datetime .timedelta (days =7 )

        embeds =await _build_meeting_report (interaction .guild ,since )
        for i in range (0 ,len (embeds ),10 ):
            await interaction .followup .send (embeds =embeds [i :i +10 ])

        cfg ['active']=False 
        cfg ['last_meeting']=datetime .datetime .now (datetime .timezone .utc ).isoformat ()
        cfg ['meeting_start']=None 
        _save_cfg (interaction .guild .id ,cfg )

        for item in self .children :
            if hasattr (item ,'custom_id'):
                if item .custom_id =='meeting_start':
                    item .disabled =False 
                elif item .custom_id =='meeting_end':
                    item .disabled =True 
        await interaction .message .edit (view =self )

    @discord .ui .button (
    label ='📊 Последний отчёт',
    style =discord .ButtonStyle .secondary ,
    custom_id ='meeting_last_report',
    row =0 
    )
    async def last_report (self ,interaction :discord .Interaction ,button :discord .ui .Button ):
        if not interaction .user .guild_permissions .manage_messages :
            await interaction .response .send_message ('❌ Недостаточно прав.',ephemeral =True )
            return 

        await interaction .response .defer ()
        cfg =_load_cfg (interaction .guild .id )

        since_str =cfg .get ('last_meeting')or cfg .get ('meeting_start')
        if not since_str :
            await interaction .followup .send (' Собрание еще не проводилось.')
            return 

        since =datetime .datetime .fromisoformat (since_str )
        if since .tzinfo is None :
            since =since .replace (tzinfo =datetime .timezone .utc )

        embeds =await _build_meeting_report (interaction .guild ,since )
        for i in range (0 ,len (embeds ),10 ):
            await interaction .followup .send (embeds =embeds [i :i +10 ])

    @discord .ui .button (
    label ='➕ Добавить роль',
    style =discord .ButtonStyle .blurple ,
    custom_id ='meeting_role_add',
    row =1 
    )
    async def role_add (self ,interaction :discord .Interaction ,button :discord .ui .Button ):
        if not interaction .user .guild_permissions .administrator :
            await interaction .response .send_message ('❌ Недостаточно прав.',ephemeral =True )
            return 
        await interaction .response .send_message (
        '➕ Добавить роль для упоминания в отчёте:\n`!sobranie-rol-add @Роль`',
        ephemeral =True 
        )

    @discord .ui .button (
    label ='🗑️ Удалить роль',
    style =discord .ButtonStyle .grey ,
    custom_id ='meeting_role_remove',
    row =1 
    )
    async def role_remove (self ,interaction :discord .Interaction ,button :discord .ui .Button ):
        if not interaction .user .guild_permissions .administrator :
            await interaction .response .send_message ('❌ Недостаточно прав.',ephemeral =True )
            return 
        cfg =_load_cfg (interaction .guild .id )
        role =cfg .get ('staff_roles',[])
        if not role :
            await interaction .response .send_message ('Добавленные роли отсутствуют.',ephemeral =True )
            return 
        role_list =[]
        for rid in role :
            r =interaction .guild .get_role (rid )
            if r :
                role_list .append (f'• {r.name}')
        await interaction .response .send_message (
        '**Текущий роли:**\n'+'\n'.join (role_list )+
        '\n\nУбрать: `!sobranie-rol-remove @Роль`',
        ephemeral =True 
        )

    @discord .ui .button (
    label ='📋 Список ролей',
    style =discord .ButtonStyle .grey ,
    custom_id ='meeting_role_list',
    row =1 
    )
    async def role_list (self ,interaction :discord .Interaction ,button :discord .ui .Button ):
        cfg =_load_cfg (interaction .guild .id )
        role =cfg .get ('staff_roles',[])
        if not role :
            await interaction .response .send_message ('Добавленные роли отсутствуют.',ephemeral =True )
            return 
        role_list =[]
        for rid in role :
            r =interaction .guild .get_role (rid )
            if r :
                role_list .append (f'• **{r.name}** ({len(r.members)} участник)')
        embed =_guild_embed_base (interaction .guild ,'📋 Роли в отчёте',0x5865F2 )
        embed .description ='\n'.join (role_list )
        await interaction .response .send_message (embed =embed ,ephemeral =True )


class Meeting (commands .Cog ):
    def __init__ (self ,bot ):
        self .bot =bot 

    @commands .command (name ='meeting',aliases =['sobranie','toplanti'])
    @commands .has_permissions (administrator =True )
    async def meeting_panel (self ,ctx ):
        """Отправить панель собрания: !sobranie"""
        cfg =_load_cfg (ctx .guild .id )

        embed =_guild_embed_base (ctx .guild ,'🎛️ Панель управления собранием',0x5865F2 )
        embed .description =(
        '> С этой панели можно управлять собранием.\n\n'
        '**▶️ Запустить собрание** — начать новое собрание, счётчики запускаются\n'
        '**✅ Завершить собрание** — закрыть собрание и отправить отчёт\n'
        '**📊 Последний отчёт** — показать данные с последнего собрания'
        )

        is_active =cfg .get ('active',False )
        view =MeetingView (ctx .guild .id )

        # Собрание Запустить: активен deгilse открыт, активен закрыт
        for item in view .children :
            if hasattr (item ,'custom_id'):
                if item .custom_id =='meeting_start':
                    item .disabled =is_active 

        msg =await ctx .send (embed =embed ,view =view )

        # Panel message ID'sini сохранить
        cfg ['panel_channel']=ctx .channel .id 
        cfg ['panel_message']=msg .id 
        _save_cfg (ctx .guild .id ,cfg )

    @commands .command (name ='meeting-role-add',aliases =['sobranie-rol-add','toplanti-rol-add'])
    @commands .has_permissions (administrator =True )
    async def add_role (self ,ctx ,role :discord .Role ):
        """Добавить роль администратора в отчёт: !sobranie-rol-add @Роль"""
        cfg =_load_cfg (ctx .guild .id )
        if role .id not in cfg .get ('staff_roles',[]):
            cfg .setdefault ('staff_roles',[]).append (role .id )
            _save_cfg (ctx .guild .id ,cfg )
        await ctx .send (f'✅ Роль **{role.name}** добавлена в отчёт собрания.')

    @commands .command (name ='meeting-role-remove',aliases =['sobranie-rol-remove','toplanti-rol-cikar'])
    @commands .has_permissions (administrator =True )
    async def remove_role (self ,ctx ,role :discord .Role ):
        """Удалить роль из отчёта: !meeting-role-remove @Роль"""
        cfg =_load_cfg (ctx .guild .id )
        if role .id in cfg .get ('staff_roles',[]):
            cfg ['staff_roles'].remove (role .id )
            _save_cfg (ctx .guild .id ,cfg )
        await ctx .send (f' **{role.name}** роль rapordan удалить.')

    @commands .Cog .listener ()
    async def on_ready (self ):
        """Загрузить постоянные view"""
        for guild in self .bot .guilds :
            cfg =_load_cfg (guild .id )
            if cfg .get ('panel_message'):
                self .bot .add_view (MeetingView (guild .id ))


async def setup (bot ):
    await bot .add_cog (Meeting (bot ))
    # Persistent views
    for guild in bot .guilds :
        cfg =_load_cfg (guild .id )
        if cfg .get ('panel_message'):
            bot .add_view (MeetingView (guild .id ))
