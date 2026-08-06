"""Ежедневное аниме-предложение — Jikan API + кнопка русского перевода"""
import discord 
from discord .ext import commands ,tasks 
from discord import app_commands 
import random 
import datetime 
import json 
import os 
import aiohttp 
from config import Config 

from logger import get_logger 
log =get_logger ("anime_daily")


DATA_FILE ='data/anime_daily_config.json'

KATEGORILER ={
"Действие":1 ,"Комедия":4 ,"Драма":8 ,
"Фэнтези":10 ,"Ужасы":14 ,"Романтика":22 ,
"Фантастика":24 ,"Детектив":7 ,"Триллер":41 
}


def _load ()->dict :
    if os .path .exists (DATA_FILE ):
        try :
            with open (DATA_FILE ,'r',encoding ='utf-8')as f :
                return json .load (f )
        except Exception :
            pass 
    return {}


def _save (data :dict ):
    os .makedirs ('data',exist_ok =True )
    with open (DATA_FILE ,'w',encoding ='utf-8')as f :
        json .dump (data ,f ,ensure_ascii =False ,indent =2 )


class TranslateButton (discord .ui .View ):
    def __init__ (self ,summary :str ):
        super ().__init__ (timeout =None )
        self .summary =summary 

    @discord .ui .button (label ='  Перевести на русский',style =discord .ButtonStyle .primary )
    async def translate_it (self ,interaction :discord .Interaction ,button :discord .ui .Button ):
        await interaction .response .defer (ephemeral =True )
        try :
            from deep_translator import GoogleTranslator 
            if not self .summary or self .summary =='Сводка не найдена.':
                await interaction .followup .send (' Нет текста для перевода.',ephemeral =True )
                return 
            translated =GoogleTranslator (source ='en',target ='ru').translate (self .summary )
            if len (translated )>1900 :
                translated =translated [:1900 ]+'...'
            await interaction .followup .send (f' **Краткое содержание:**\n\n{translated}',ephemeral =True )
        except Exception :
            await interaction .followup .send (' Не удалось выполнить перевод.',ephemeral =True )


async def _anime_getir (tur_id :int =None )->dict :
    """Случайное аниме из Jikan API"""
    sayfa =random .randint (1 ,4 )
    if tur_id :
        url =f'https://api.jikan.moe/v4/anime?genres={tur_id}&sfw=true&type=tv&min_score=6.5&order_by=popularity&page={sayfa}'
    else :
        url =f'https://api.jikan.moe/v4/anime?sfw=true&type=tv&min_score=7.0&order_by=popularity&page={sayfa}'
    try :
        async with aiohttp .ClientSession ()as session :
            async with session .get (url ,timeout =aiohttp .ClientMute (total =10 ))as resp :
                if resp .status ==200 :
                    Данные =await resp .json ()
                    animeler =Данные .get ('data',[])
                    if animeler :
                        return random .choice (animeler )
    except Exception :
        pass 
    return None 


def _embed_build (guild :discord .Guild ,anime :dict ,kategori :str ='Случайно')->tuple :
    """Создать embed аниме, вернуть (embed, summary)"""
    title =anime .get ('title_english')or anime .get ('title','Неизвестно')
    puan =anime .get ('score')or 'Не оценено'
    resim =anime .get ('images',{}).get ('jpg',{}).get ('large_image_url','')
    link =anime .get ('url','')
    bolum =anime .get ('episodes')or 'Неизвестно'
    summary =anime .get ('synopsis','Сводка не найдена.')
    short_summary =(summary [:300 ]+'...')if len (summary )>300 else summary 

    embed =discord .Embed (
    title =f' Аниме-предложение дня: {title}',
    url =link ,
    description =short_summary ,
    color =0xED4245 
    )
    if resim :
        embed .set_image (url =resim )
    if guild .icon :
        embed .set_thumbnail (url =guild .icon .url )
    embed .add_field (name =' Категория',value =kategori ,inline =True )
    embed .add_field (name =' Оценка',value =str (puan ),inline =True )
    embed .add_field (name =' Эпизодов',value =str (bolum ),inline =True )
    embed .set_footer (
    text =f'{guild.name}  ·  Ежедневное аниме',
    icon_url =guild .icon .url if guild .icon else None 
    )
    return embed ,summary 


class AnimeDaily (commands .Cog ):
    def __init__ (self ,bot ):
        self .bot =bot 
        self .gunluk_anime .start ()

    def cog_unload (self ):
        self .gunluk_anime .cancel ()

    @tasks .loop (hours =24 )
    async def gunluk_anime (self ):
        """Каждый день в 10:00 отправляет предложение аниме"""
        cfg =_load ()
        for guild in self .bot .guilds :
            gid =str (guild .id )
            gcfg =cfg .get (gid ,{})
            if not gcfg .get ('enabled')or not gcfg .get ('channel_id'):
                continue 
            channel =guild .get_channel (gcfg ['channel_id'])
            if not channel :
                continue 
            try :
                tur_id =gcfg .get ('tur_id')
                category =gcfg .get ('tur_adi','Случайно')
                anime =await _anime_getir (tur_id )
                if not anime :
                    continue 
                embed ,summary =_embed_build (guild ,anime ,category )
                role_id =gcfg .get ('role_id')
                content =f'<@&{role_id}>'if role_id else None 
                await channel .send (content =content ,embed =embed ,view =TranslateButton (summary ))
            except Exception as e :
                log .info (f'[AnimeDaily] {guild.name} Ошибка: {e}')

    @gunluk_anime .before_loop 
    async def before_loop (self ):
        await self .bot .wait_until_ready ()
        # ждём до 10:00
        now =datetime .datetime .now ()
        target =now .replace (hour =10 ,minute =0 ,second =0 ,microsecond =0 )
        if now >=target :
            target +=datetime .timedelta (days =1 )
        wait =(target -now ).total_seconds ()
        import asyncio 
        await asyncio .sleep (wait )

        #  Slash команды 

    @app_commands .command (name ='anime-setup',description ="Настройка ежедневных предложений аниме")
    @app_commands .describe (
    channel ='Канал для ежедневных предложений аниме',
    kategori ='Категория аниме (пусто = случайная)',
    role ='Роль для упоминания (необязательно)',
    )
    @app_commands .choices (kategori =[
    app_commands .Choice (name =k ,value =str (v ))for k ,v in KATEGORILER .items ()
    ]+[app_commands .Choice (name ='Случайно',value ='0')])
    @app_commands .checks .has_permissions (manage_channels =True )
    async def anime_setup (self ,interaction :discord .Interaction ,
    channel :discord .TextChannel ,
    kategori :str ='0',
    role :discord .Role =None ):
        cfg =_load ()
        gid =str (interaction .guild .id )
        tur_id =int (kategori )if kategori !='0'else None 
        category =next ((k for k ,v in KATEGORILER .items ()if v ==tur_id ),'Случайно')

        cfg [gid ]={
        'enabled':True ,
        'channel_id':channel .id ,
        'tur_id':tur_id ,
        'tur_adi':category ,
        'role_id':role .id if role else None ,
        }
        _save (cfg )

        embed =discord .Embed (title =' Настройки ежедневного аниме',color =0x57F287 )
        if interaction .guild .icon :
            embed .set_thumbnail (url =interaction .guild .icon .url )
        embed .add_field (name =' Канал',value =channel .mention ,inline =True )
        embed .add_field (name =' Категория',value =category ,inline =True )
        embed .add_field (name =' Роль',value =role .mention if role else 'Нет',inline =True )
        embed .set_footer (text ='Ежедневная отправка в 10:00')
        await interaction .response .send_message (embed =embed )

    @app_commands .command (name ='anime-off',description ="Отключить ежедневные предложения аниме")
    @app_commands .checks .has_permissions (manage_channels =True )
    async def anime_disable (self ,interaction :discord .Interaction ):
        cfg =_load ()
        gid =str (interaction .guild .id )
        if gid in cfg :
            cfg [gid ]['enabled']=False 
            _save (cfg )
        await interaction .response .send_message (' Ежедневные предложения аниме отключены.',ephemeral =True )

    @app_commands .command (name ='anime',description ='Случайное предложение аниме')
    @app_commands .describe (kategori ='Категория аниме')
    @app_commands .choices (kategori =[
    app_commands .Choice (name =k ,value =str (v ))for k ,v in KATEGORILER .items ()
    ]+[app_commands .Choice (name ='Случайно',value ='0')])
    async def anime_oner (self ,interaction :discord .Interaction ,kategori :str ='0'):
        await interaction .response .defer ()
        tur_id =int (kategori )if kategori !='0'else None 
        category =next ((k for k ,v in KATEGORILER .items ()if v ==tur_id ),'Случайно')
        anime =await _anime_getir (tur_id )
        if not anime :
            await interaction .followup .send (' Аниме не найдено, попробуйте ещё раз.')
            return 
        embed ,summary =_embed_build (interaction .guild ,anime ,category )
        await interaction .followup .send (embed =embed ,view =TranslateButton (summary ))

    @app_commands .command (name ='anime-suggest',description ="Случайное или категорийное предложение аниме")
    @app_commands .describe (kategori ='Категория аниме (пусто = случайная)')
    @app_commands .choices (kategori =[
    app_commands .Choice (name =k ,value =str (v ))for k ,v in KATEGORILER .items ()
    ]+[app_commands .Choice (name ='Случайно',value ='0')])
    async def anime_oner2 (self ,interaction :discord .Interaction ,kategori :str ='0'):
        await interaction .response .defer ()
        tur_id =int (kategori )if kategori !='0'else None 
        category =next ((k for k ,v in KATEGORILER .items ()if v ==tur_id ),'Случайно')
        anime =await _anime_getir (tur_id )
        if not anime :
            await interaction .followup .send (' Аниме не найдено, попробуйте ещё раз.')
            return 
        embed ,summary =_embed_build (interaction .guild ,anime ,category )
        await interaction .followup .send (embed =embed ,view =TranslateButton (summary ))


async def setup (bot ):
    await bot .add_cog (AnimeDaily (bot ),guilds =Config .guild_objects ())
