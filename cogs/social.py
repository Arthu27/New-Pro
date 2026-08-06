"""
Aether Social Cog
- Расширенная система опросов (множественный выбор, по времени, анонимно, с графиком)
- Event planlayыcыsы (etkinlik takvimi, katыlыmcы список, hatыrlatmalar)
- Matchmaking система (oyun arkadaшы bulma, команда создан)
"""
import discord 
from discord .ext import commands ,tasks 
from discord import app_commands 
import json ,os 
from datetime import datetime ,timezone ,timedelta 
from typing import Optional 
from config import Config 

POLL_FILE ='data/polls_{guild_id}.json'
EVENT_FILE ='data/events_{guild_id}.json'
MATCH_FILE ='data/matchmaking_{guild_id}.json'

# Emoji bar для
BAR_FULL =''
BAR_EMPTY =''

def _bar (ratio :float ,length :int =12 )->str :
    filled =round (ratio *length )
    return BAR_FULL *filled +BAR_EMPTY *(length -filled )

def _load (path ):
    return json .load (open (path ,'r',encoding ='utf-8'))if os .path .exists (path )else {}

def _save (path ,data ):
    os .makedirs ('data',exist_ok =True )
    with open (path ,'w',encoding ='utf-8')as f :
        json .dump (data ,f ,indent =2 ,ensure_ascii =False )


        # 
        # POLL VIEW
        # 
class PollView (discord .ui .View ):
    def __init__ (self ,poll_id :str ,options :list ,anonymous :bool ,guild_id :str ):
        super ().__init__ (timeout =None )
        self .poll_id =poll_id 
        self .guild_id =guild_id 
        self .anonymous =anonymous 
        emojis =['1','2','3','4','5','6','7','8','9','']
        for i ,opt in enumerate (options [:10 ]):
            btn =discord .ui .Button (
            label =opt [:80 ],
            emoji =emojis [i ],
            style =discord .ButtonStyle .secondary ,
            custom_id =f"poll_{poll_id}_{i}"
            )
            btn .callback =self ._make_callback (i )
            self .add_item (btn )

    def _make_callback (self ,idx :int ):
        async def callback (interaction :discord .Interaction ):
            path =POLL_FILE .format (guild_id =self .guild_id )
            data =_load (path )
            poll =data .get (self .poll_id )
            if not poll :
                await interaction .response .send_message (" Anket не найдено.",ephemeral =True )
                return 
            if poll .get ('ended'):
                await interaction .response .send_message (" Bu anket sona erdi.",ephemeral =True )
                return 

            uid =str (interaction .user .id )
            votes =poll .setdefault ('votes',{})

            # Повторный клик по тому же варианту отзывает голос
            if votes .get (uid )==idx :
                del votes [uid ]
                await interaction .response .send_message (" Игра отменена.",ephemeral =True )
            else :
                votes [uid ]=idx 
                opt_name =poll ['options'][idx ]
                await interaction .response .send_message (
                f"🗳 **{opt_name}** — голос принят!"+(" (анонимно)"if self .anonymous else ""),
                ephemeral =True 
                )

            _save (path ,data )
            # Embed'i обновить
            await _update_poll_embed (interaction .message ,poll )
        return callback 


async def _update_poll_embed (message :discord .Message ,poll :dict ):
    votes =poll .get ('votes',{})
    total =len (votes )
    options =poll ['options']
    counts =[sum (1 for v in votes .values ()if v ==i )for i in range (len (options ))]

    e =message .embeds [0 ]if message .embeds else discord .Embed ()
    e .clear_fields ()
    emojis =['1','2','3','4','5','6','7','8','9','']
    for i ,(opt ,cnt )in enumerate (zip (options ,counts )):
        ratio =cnt /total if total >0 else 0 
        bar =_bar (ratio )
        pct =f"{ratio:.0%}"
        e .add_field (
        name =f"{emojis[i]} {opt}",
        value =f"`{bar}` **{pct}** ({cnt} oy)",
        inline =False 
        )
    e .set_footer (text =f"🗳 Всего голосов: {total} • Повторный клик по той же кнопке отзывает голос")
    try :
        await message .edit (embed =e )
    except Exception :
        pass 


        # 
        # EVENT VIEW
        # 
class EventJoinView (discord .ui .View ):
    def __init__ (self ,event_id :str ,guild_id :str ):
        super ().__init__ (timeout =None )
        self .event_id =event_id 
        self .guild_id =guild_id 

    @discord .ui .button (label ="Участвовать",emoji ="",style =discord .ButtonStyle .success ,custom_id ="event_join")
    async def join (self ,interaction :discord .Interaction ,button :discord .ui .Button ):
        path =EVENT_FILE .format (guild_id =self .guild_id )
        data =_load (path )
        event =data .get (self .event_id )
        if not event :
            await interaction .response .send_message (" Событие не найдено.",ephemeral =True )
            return 
        uid =str (interaction .user .id )
        participants =event .setdefault ('participants',[])
        if uid in participants :
            participants .remove (uid )
            msg ="🚪 Вы покинули событие."
        else :
            participants .append (uid )
            msg =f" **{event['title']}** — ты присоединился к событию!"
        _save (path ,data )
        await interaction .response .send_message (msg ,ephemeral =True )
        # Embed обновить
        await _update_event_embed (interaction .message ,event )

    @discord .ui .button (label ="Участники",emoji ="",style =discord .ButtonStyle .secondary ,custom_id ="event_list")
    async def list_participants (self ,interaction :discord .Interaction ,button :discord .ui .Button ):
        path =EVENT_FILE .format (guild_id =self .guild_id )
        data =_load (path )
        event =data .get (self .event_id ,{})
        participants =event .get ('participants',[])
        if not participants :
            await interaction .response .send_message ("Пока нет участников.",ephemeral =True )
            return 
        mentions =[f"<@{uid}>"for uid in participants [:20 ]]
        await interaction .response .send_message (
        f"** Участники ({len(participants)}):**\n"+", ".join (mentions ),
        ephemeral =True 
        )


async def _update_event_embed (message :discord .Message ,event :dict ):
    participants =event .get ('participants',[])
    e =message .embeds [0 ]if message .embeds else discord .Embed ()
    # Katыlыmcы число обновить
    for i ,field in enumerate (e .fields ):
        if ''in field .name :
            e .set_field_at (i ,name =field .name ,value =f"`{len(participants)} человек`",inline =field .inline )
            break 
    try :
        await message .edit (embed =e )
    except Exception :
        pass 


        # 
        # MATCHMAKING VIEW
        # 
class MatchView (discord .ui .View ):
    def __init__ (self ,match_id :str ,guild_id :str ,max_players :int ):
        super ().__init__ (timeout =None )
        self .match_id =match_id 
        self .guild_id =guild_id 
        self .max_players =max_players 

    @discord .ui .button (label ="Участвовать",emoji ="",style =discord .ButtonStyle .success ,custom_id ="match_join")
    async def join (self ,interaction :discord .Interaction ,button :discord .ui .Button ):
        path =MATCH_FILE .format (guild_id =self .guild_id )
        data =_load (path )
        match =data .get (self .match_id )
        if not match :
            await interaction .response .send_message (" Матч не найден.",ephemeral =True )
            return 
        uid =str (interaction .user .id )
        players =match .setdefault ('players',[])
        if uid in players :
            players .remove (uid )
            await interaction .response .send_message (" Вы покинули матч.",ephemeral =True )
        elif len (players )>=self .max_players :
            await interaction .response .send_message (" Матч заполнен!",ephemeral =True )
            return 
        else :
            players .append (uid )
            await interaction .response .send_message (f" **{match['game']}** — вы присоединились к матчу!",ephemeral =True )
        _save (path ,data )
        await _update_match_embed (interaction .message ,match ,self .max_players )

        # Takыm doldu mu?
        if len (players )>=self .max_players :
            await interaction .channel .send (
            f" **{match['game']}** — команда набрана! "
            +" ".join (f"<@{p}>"for p in players )
            +"\nВперёд, играем! "
            )


async def _update_match_embed (message :discord .Message ,match :dict ,max_players :int ):
    players =match .get ('players',[])
    e =message .embeds [0 ]if message .embeds else discord .Embed ()
    for i ,field in enumerate (e .fields ):
        if ''in field .name :
            e .set_field_at (i ,name =field .name ,value =f"`{len(players)}/{max_players}`",inline =field .inline )
            break 
    try :
        await message .edit (embed =e )
    except Exception :
        pass 


        # 
        # MAIN COG
        # 
class Social (commands .Cog ):
    def __init__ (self ,bot ):
        self .bot =bot 
        self .poll_checker .start ()
        self .event_reminder .start ()

    def cog_unload (self ):
        self .poll_checker .cancel ()
        self .event_reminder .cancel ()

        #  ANKET 
    @app_commands .command (name ="poll",description ="Создать новый опрос")
    @app_commands .describe (
    вопрос ="Вопрос опроса",
    варианты ="Варианты через запятую (макс. 10)",
    длительность ="Длительность в минутах (0 = бессрочно)",
    анонимно ="Анонимное голосование?"
    )
    @app_commands .checks .has_permissions (moderate_members =True )
    async def poll_create (self ,interaction :discord .Interaction ,
    вопрос :str ,варианты :str ,
    длительность :int =0 ,анонимно :bool =False ):
        options =[o .strip ()for o in варианты .split (',')if o .strip ()][:10 ]
        if len (options )<2 :
            await interaction .response .send_message (" En az 2 выбрать gir!",ephemeral =True )
            return 

        guild_id =str (interaction .guild .id )
        path =POLL_FILE .format (guild_id =guild_id )
        data =_load (path )

        poll_id =str (int (datetime .now ().timestamp ()))
        ends_at =(datetime .now (timezone .utc )+timedelta (minutes =длительность )).isoformat ()if длительность >0 else None 

        poll ={
        'id':poll_id ,
        'question':вопрос ,
        'options':options ,
        'votes':{},
        'anonymous':анонимно ,
        'created_by':str (interaction .user .id ),
        'ends_at':ends_at ,
        'ended':False ,
        'channel_id':str (interaction .channel .id ),
        'message_id':None ,
        }
        data [poll_id ]=poll 
        _save (path ,data )

        emojis =['1','2','3','4','5','6','7','8','9','']
        e =discord .Embed (
        title =f"📊 {вопрос}",
        color =0x3498db ,
        timestamp =datetime .now (timezone .utc )
        )
        e .description =f"{'🔒 Анонимное голосование' if анонимно else '🔓 Открытое голосование'}"
        for i ,opt in enumerate (options ):
            e .add_field (name =f"{emojis[i]} {opt}",value =f"`{''*12}` **0%** (0 oy)",inline =False )
        if ends_at :
            e .add_field (name ="⏰ Окончание",value =f"<t:{int(datetime.fromisoformat(ends_at).timestamp())}:R>",inline =True )
        e .set_footer (text ="🗳 Всего 0 голосов • Повторный клик по той же кнопке отзывает голос")
        e .set_author (name =interaction .user .display_name ,icon_url =interaction .user .display_avatar .url )

        view =PollView (poll_id ,options ,анонимно ,guild_id )
        await interaction .response .send_message (embed =e ,view =view )
        msg =await interaction .original_response ()

        # Сообщение ID'sini сохранить
        data [poll_id ]['message_id']=str (msg .id )
        _save (path ,data )

    @app_commands .command (name ="poll-end",description ="Завершить опрос")
    @app_commands .describe (anket_id ="Anket ID")
    @app_commands .checks .has_permissions (moderate_members =True )
    async def poll_end (self ,interaction :discord .Interaction ,anket_id :str ):
        guild_id =str (interaction .guild .id )
        path =POLL_FILE .format (guild_id =guild_id )
        data =_load (path )
        poll =data .get (anket_id )
        if not poll :
            await interaction .response .send_message (" Anket не найдено.",ephemeral =True )
            return 
        poll ['ended']=True 
        _save (path ,data )
        await interaction .response .send_message (f" Anket `{anket_id}` заверш.",ephemeral =True )

    @tasks .loop (minutes =1 )
    async def poll_checker (self ):
        """Длительность dolan anketleri автоматически закрыть."""
        now =datetime .now (timezone .utc )
        for guild in self .bot .guilds :
            path =POLL_FILE .format (guild_id =str (guild .id ))
            data =_load (path )
            changed =False 
            for poll in data .values ():
                if poll .get ('ended')or not poll .get ('ends_at'):
                    continue 
                ends_at =datetime .fromisoformat (poll ['ends_at'])
                if now >=ends_at :
                    poll ['ended']=True 
                    changed =True 
                    # результат сообщение отправить
                    try :
                        ch =guild .get_channel (int (poll ['channel_id']))
                        if ch :
                            votes =poll .get ('votes',{})
                            total =len (votes )
                            options =poll ['options']
                            counts =[sum (1 for v in votes .values ()if v ==i )for i in range (len (options ))]
                            winner_idx =counts .index (max (counts ))if counts else 0 
                            e =discord .Embed (
                            title =f" Anket результат: {poll['question']}",
                            color =0x2ecc71 
                            )
                            emojis =['1','2','3','4','5','6','7','8','9','']
                            for i ,(opt ,cnt )in enumerate (zip (options ,counts )):
                                ratio =cnt /total if total >0 else 0 
                                winner_mark =" "if i ==winner_idx else ""
                                e .add_field (
                                name =f"{emojis[i]} {opt}{winner_mark}",
                                value =f"`{_bar(ratio)}` **{ratio:.0%}** ({cnt} oy)",
                                inline =False 
                                )
                            e .set_footer (text =f"Всего {total} oy")
                            await ch .send (embed =e )
                    except Exception :
                        pass 
            if changed :
                _save (path ,data )

    @poll_checker .before_loop 
    async def before_poll_checker (self ):
        await self .bot .wait_until_ready ()

        #  ETKИNLИK 
    @app_commands .command (name ="activity",description ="Создать новое событие")
    @app_commands .describe (
    название ="Название события",
    описание ="Описание события",
    дата ="Дата (ДД.ММ.ГГГГ ЧЧ:ММ)",
    макс_участников ="Макс. участников (0 = без лимита)"
    )
    @app_commands .checks .has_permissions (moderate_members =True )
    async def event_create (self ,interaction :discord .Interaction ,
    название :str ,описание :str ,
    дата :str ,макс_участников :int =0 ):
        try :
            event_dt =datetime .strptime (дата ,'%d.%m.%Y %H:%M').replace (tzinfo =timezone .utc )
        except ValueError :
            await interaction .response .send_message (
            " Неверный формат даты! Пример: `25.12.2025 20:00`",ephemeral =True 
            )
            return 

        guild_id =str (interaction .guild .id )
        path =EVENT_FILE .format (guild_id =guild_id )
        data =_load (path )

        event_id =str (int (datetime .now ().timestamp ()))
        event ={
        'id':event_id ,
        'title':название ,
        'description':описание ,
        'date':event_dt .isoformat (),
        'max_participants':макс_участников ,
        'participants':[],
        'created_by':str (interaction .user .id ),
        'channel_id':str (interaction .channel .id ),
        'message_id':None ,
        'reminded':False ,
        }
        data [event_id ]=event 
        _save (path ,data )

        e =discord .Embed (
        title =f"🎉 {название}",
        description =описание ,
        color =0x9b59b6 ,
        timestamp =datetime .now (timezone .utc )
        )
        e .add_field (name =" Дата",value =f"<t:{int(event_dt.timestamp())}:F>",inline =True )
        e .add_field (name ="⏰ Когда",value =f"<t:{int(event_dt.timestamp())}:R>",inline =True )
        e .add_field (name =" Участники",value ="`0 человек`"+(f" / {макс_участников}"if макс_участников else ""),inline =True )
        e .set_author (name =interaction .user .display_name ,icon_url =interaction .user .display_avatar .url )
        e .set_footer (text =f" Aether Event Система • ID: {event_id}")

        view =EventJoinView (event_id ,guild_id )
        await interaction .response .send_message (embed =e ,view =view )
        msg =await interaction .original_response ()
        data [event_id ]['message_id']=str (msg .id )
        _save (path ,data )

    @app_commands .command (name ="activity-list",description ="Показать предстоящие события")
    async def event_list (self ,interaction :discord .Interaction ):
        guild_id =str (interaction .guild .id )
        path =EVENT_FILE .format (guild_id =guild_id )
        data =_load (path )
        now =datetime .now (timezone .utc )

        upcoming =sorted (
        [e for e in data .values ()if datetime .fromisoformat (e ['date'])>now ],
        key =lambda x :x ['date']
        )

        e =discord .Embed (title ="📅 Ближайшие события",color =0x9b59b6 ,timestamp =now )
        if not upcoming :
            e .description ="Ближайших событий нет."
        else :
            for ev in upcoming [:8 ]:
                dt =datetime .fromisoformat (ev ['date'])
                e .add_field (
                name =f" {ev['title']}",
                value =f"<t:{int(dt.timestamp())}:F> • {len(ev.get('participants', []))} участников",
                inline =False 
                )
        await interaction .response .send_message (embed =e ,ephemeral =True )

    @tasks .loop (minutes =10 )
    async def event_reminder (self ):
        """Отправить напоминание за 30 минут до события."""
        now =datetime .now (timezone .utc )
        for guild in self .bot .guilds :
            path =EVENT_FILE .format (guild_id =str (guild .id ))
            data =_load (path )
            changed =False 
            for event in data .values ():
                if event .get ('reminded'):
                    continue 
                dt =datetime .fromisoformat (event ['date'])
                diff =(dt -now ).total_seconds ()
                if 0 <diff <=1800 :# 30 minutes
                    event ['reminded']=True 
                    changed =True 
                    try :
                        ch =guild .get_channel (int (event ['channel_id']))
                        if ch :
                            participants =event .get ('participants',[])
                            mentions =" ".join (f"<@{uid}>"for uid in participants )if participants else "@каждый"
                            await ch .send (
                            f"⏰ **{event['title']}** начинается через **30 минут**!\n{mentions}"
                            )
                    except Exception :
                        pass 
            if changed :
                _save (path ,data )

    @event_reminder .before_loop 
    async def before_event_reminder (self ):
        await self .bot .wait_until_ready ()

        #  MATCHMAKING 
    @app_commands .command (name ="game-find",description ="Поиск напарников для игры")
    @app_commands .describe (
    oyun ="Игра имя",
    max_oyuncu ="Размер команды?",
    not_ ="Ek заметок (rank, mod, vb.)"
    )
    async def matchmaking_create (self ,interaction :discord .Interaction ,
    oyun :str ,max_oyuncu :int =5 ,
    not_ :Optional [str ]=None ):
        if max_oyuncu <2 or max_oyuncu >20 :
            await interaction .response .send_message (" Количество игроков должно быть от 2 до 20!",ephemeral =True )
            return 

        guild_id =str (interaction .guild .id )
        path =MATCH_FILE .format (guild_id =guild_id )
        data =_load (path )

        match_id =str (int (datetime .now ().timestamp ()))
        match ={
        'id':match_id ,
        'game':oyun ,
        'max_players':max_oyuncu ,
        'players':[str (interaction .user .id )],
        'note':not_ ,
        'created_by':str (interaction .user .id ),
        'created_at':datetime .now (timezone .utc ).isoformat (),
        }
        data [match_id ]=match 
        _save (path ,data )

        e =discord .Embed (
        title =f" {oyun} — Ищем игрока",
        color =0x1abc9c ,
        timestamp =datetime .now (timezone .utc )
        )
        e .add_field (name =" Игроки",value =f"`1/{max_oyuncu}`",inline =True )
        e .add_field (name =" Игра",value =f"`{oyun}`",inline =True )
        if not_ :
            e .add_field (name =" Not",value =f"`{not_}`",inline =True )
        e .add_field (name =" Создал",value =interaction .user .mention ,inline =True )
        e .set_footer (text ="Aether Matchmaking • Когда состав соберётся — придёт уведомление")
        e .set_thumbnail (url =interaction .user .display_avatar .url )

        view =MatchView (match_id ,guild_id ,max_oyuncu )
        await interaction .response .send_message (embed =e ,view =view )

    @app_commands .command (name ="game-list",description ="Показать активные поиски игроков")
    async def matchmaking_list (self ,interaction :discord .Interaction ):
        guild_id =str (interaction .guild .id )
        path =MATCH_FILE .format (guild_id =guild_id )
        data =_load (path )

        # В конец 2 времяteki активен aramalar
        now =datetime .now (timezone .utc )
        active =[
        m for m in data .values ()
        if (now -datetime .fromisoformat (m ['created_at'])).total_seconds ()<7200 
        and len (m .get ('players',[]))<m ['max_players']
        ]

        e =discord .Embed (title ="🎮 Активные поиски игроков",color =0x1abc9c ,timestamp =now )
        if not active :
            e .description ="Сейчас нет активных поисков.\n`/oyun-ara` — запустить новый!"
        else :
            for m in active [:8 ]:
                players =m .get ('players',[])
                e .add_field (
                name =f" {m['game']}",
                value =f" `{len(players)}/{m['max_players']}` • {m.get('note', '')} • <@{m['created_by']}>",
                inline =False 
                )
        await interaction .response .send_message (embed =e ,ephemeral =True )


async def setup (bot ):
    await bot .add_cog (Social (bot ),guilds =Config .guild_objects ())
