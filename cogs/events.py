"""Система событий — назначить дату, отправить напоминание"""
import discord 
from discord .ext import commands ,tasks 
from discord import app_commands 
import json ,os 
from datetime import datetime ,timedelta 
from config import Config 

class Events (commands .Cog ):
    def __init__ (self ,bot ):
        self .bot =bot 
        self .check_events .start ()

    def cog_unload (self ):
        self .check_events .cancel ()

    def _file (self ,guild_id ):
        return f'data/events_{guild_id}.json'

    def _load (self ,guild_id ):
        f =self ._file (guild_id )
        if not os .path .exists (f ):return {}
        with open (f ,'r',encoding ='utf-8')as fp :return json .load (fp )

    def _save (self ,guild_id ,data ):
        os .makedirs ('data',exist_ok =True )
        with open (self ._file (guild_id ),'w',encoding ='utf-8')as fp :
            json .dump (data ,fp ,indent =2 ,ensure_ascii =False )

    @tasks .loop (minutes =5 )
    async def check_events (self ):
        now =datetime .utcnow ()
        for guild in self .bot .guilds :
            events =self ._load (guild .id )
            changed =False 
            for eid ,ev in list (events .items ()):
                if ev .get ('notified'):continue 
                try :
                    event_time =datetime .fromisoformat (ev ['time'])
                except Exception :continue 

                diff_min =(event_time -now ).total_seconds ()/60 

                # 60 minutes ёncesi hatыrlatma
                if 55 <=diff_min <=65 and not ev .get ('reminded_1h'):
                    await self ._send_reminder (guild ,ev ,'1 час')
                    events [eid ]['reminded_1h']=True 
                    changed =True 

                    # 10 minutes ёncesi hatыrlatma
                if 5 <=diff_min <=15 and not ev .get ('reminded_10m'):
                    await self ._send_reminder (guild ,ev ,'10 минут')
                    events [eid ]['reminded_10m']=True 
                    changed =True 

                    # Событие baшladы
                if diff_min <=0 and not ev .get ('notified'):
                    await self ._send_start (guild ,ev )
                    events [eid ]['notified']=True 
                    changed =True 

            if changed :
                self ._save (guild .id ,events )

    @check_events .before_loop 
    async def before_check (self ):
        await self .bot .wait_until_ready ()

    async def _send_reminder (self ,guild ,ev ,time_str ):
        ch =guild .get_channel (int (ev .get ('channel_id',0 )))
        if not ch :return 
        embed =discord .Embed (
        title =f'Напоминание о событии — осталось {time_str}',
        description =f'**{ev["title"]}**\n\n{ev.get("description", "")}',
        color =discord .Color .dark_grey ()
        )
        embed .add_field (name ='Дата и время',value =f'<t:{int(datetime.fromisoformat(ev["time"]).timestamp())}:F>')
        mention =f'<@&{ev["role_id"]}>'if ev .get ('role_id')else '@everyone'
        await ch .send (content =mention ,embed =embed )

    async def _send_start (self ,guild ,ev ):
        ch =guild .get_channel (int (ev .get ('channel_id',0 )))
        if not ch :return 
        embed =discord .Embed (
        title =f'СОБЫТИЕ НАЧАЛОСЬ — {ev["title"]}',
        description =ev .get ('description',''),
        color =discord .Color .dark_grey ()
        )
        mention =f'<@&{ev["role_id"]}>'if ev .get ('role_id')else '@everyone'
        await ch .send (content =mention ,embed =embed )

    @app_commands .command (name ='event-create',description ='Создать новое событие')
    @app_commands .describe (
    baslik ='Событие baшlыгы',
    aciklama ='Событие описание',
    date ='Дата (GG/AA/YYYY)',
    часов ='Время (SS:DD)',
    channel ='Duyuru канал'
    )
    @app_commands .checks .has_permissions (manage_events =True )
    async def create_event (self ,interaction :discord .Interaction ,
    baslik :str ,aciklama :str ,
    date :str ,часов :str ,
    channel :discord .TextChannel ):
        try :
            dt =datetime .strptime (f'{date} {часов}','%d/%m/%Y %H:%M')
        except ValueError :
            await interaction .response .send_message ('Неверный формат даты/времени. Пример: 25/12/2025 20:00',ephemeral =True )
            return 

        if dt <datetime .utcnow ():
            await interaction .response .send_message ('Нельзя создать событие в прошлом',ephemeral =True )
            return 

        events =self ._load (interaction .guild_id )
        eid =str (int (dt .timestamp ()))
        events [eid ]={
        'id':eid ,'title':baslik ,'description':aciklama ,
        'time':dt .isoformat (),'channel_id':str (channel .id ),
        'created_by':str (interaction .user .id ),
        'notified':False ,'reminded_1h':False ,'reminded_10m':False 
        }
        self ._save (interaction .guild_id ,events )

        embed =discord .Embed (title =f'{baslik}',description =aciklama ,color =discord .Color .dark_grey ())
        embed .add_field (name ='Дата и время',value =f'<t:{int(dt.timestamp())}:F>')
        embed .add_field (name ='Канал анонсов',value =channel .mention )
        embed .set_footer (text =f'Событие ID: {eid}')
        await interaction .response .send_message (embed =embed )

    @app_commands .command (name ='events',description ='Показать предстоящие события')
    async def list_events (self ,interaction :discord .Interaction ):
        events =self ._load (interaction .guild_id )
        upcoming =[(eid ,ev )for eid ,ev in events .items ()
        if not ev .get ('notified')and 
        datetime .fromisoformat (ev ['time'])>datetime .utcnow ()]
        upcoming .sort (key =lambda x :x [1 ]['time'])

        if not upcoming :
            await interaction .response .send_message ('Нет предстоящих событий',ephemeral =True )
            return 

        embed =discord .Embed (title ='Предстоящие события',color =discord .Color .dark_grey ())
        for eid ,ev in upcoming [:10 ]:
            ts =int (datetime .fromisoformat (ev ['time']).timestamp ())
            embed .add_field (
            name =ev ['title'],
            value =f'<t:{ts}:F> (<t:{ts}:R>)',
            inline =False 
            )
        await interaction .response .send_message (embed =embed )

    @app_commands .command (name ='event-cancel',description ='Отменить событие')
    @app_commands .checks .has_permissions (manage_events =True )
    async def cancel_event (self ,interaction :discord .Interaction ,etkinlik_id :str ):
        events =self ._load (interaction .guild_id )
        if etkinlik_id not in events :
            await interaction .response .send_message ('Событие не найдено',ephemeral =True )
            return 
        title =events [etkinlik_id ]['title']
        del events [etkinlik_id ]
        self ._save (interaction .guild_id ,events )
        await interaction .response .send_message (f'Событие {title} отменено')

async def setup (bot ):
    await bot .add_cog (Events (bot ),guilds =Config .guild_objects ())
