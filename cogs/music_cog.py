"""
Music Cog
Mюzik командыы cog'u
"""

import discord 
from discord .ext import commands 
from datetime import datetime 
import asyncio 

from logger import get_logger 
log =get_logger ("music_cog")



class MusicCog (commands .Cog ):
    """Mюzik командыы cog'u"""

    def __init__ (self ,bot ):
        self .bot =bot 
        self .queues ={}# guild_id -> queue

    def get_queue (self ,guild_id :int )->list :
        """Сервер kuyruгunu al"""
        if guild_id not in self .queues :
            self .queues [guild_id ]=[]
        return self .queues [guild_id ]

    @commands .command (name ='play',aliases =['чal'])
    async def play (self ,ctx ,*,query :str ):
        """Шarkы чal"""
        # Voice channel проверкаю
        if not ctx .author .voice :
            await ctx .send (" Сначала подключитесь к голосовому каналу!")
            return 

            # Bot voice channel'a katыl
        voice_channel =ctx .author .voice .channel 

        if not ctx .voice_client :
            await voice_channel .connect ()

            # Queue'ya добавить
        queue =self .get_queue (ctx .guild .id )
        queue .append ({
        'query':query ,
        'requester':ctx .author 
        })

        embed =discord .Embed (
        title =" Kuyruгa Добавлен",
        description =f"**Шarkы:** {query}\n**Sыra:** {len(queue)}",
        color =discord .Color .dark_grey (),
        timestamp =datetime .now ()
        )

        await ctx .send (embed =embed )

    @commands .command (name ='pause',aliases =['duraklat'])
    async def pause (self ,ctx ):
        """Шarkыyы duraklat"""
        if not ctx .voice_client :
            await ctx .send (" Сейчас ничего не играет!")
            return 

        if ctx .voice_client .is_playing ():
            ctx .voice_client .pause ()

            embed =discord .Embed (
            title ="⏸ Duraklatыldы",
            color =discord .Color .dark_grey (),
            timestamp =datetime .now ()
            )

            await ctx .send (embed =embed )
        else :
            await ctx .send (" Сейчас ничего не играет!")

    @commands .command (name ='resume',aliases =['продолжить'])
    async def resume (self ,ctx ):
        """Шarkыyы продолжить ettir"""
        if not ctx .voice_client :
            await ctx .send (" Сейчас ничего не играет!")
            return 

        if ctx .voice_client .is_paused ():
            ctx .voice_client .resume ()

            embed =discord .Embed (
            title =" Продолжить Ediliyor",
            color =discord .Color .dark_grey (),
            timestamp =datetime .now ()
            )

            await ctx .send (embed =embed )
        else :
            await ctx .send (" Шu anda duraklatыlmыш bir шarkы нет!")

    @commands .command (name ='skip',aliases =['geч'])
    async def skip (self ,ctx ):
        """Шarkыyы geч"""
        if not ctx .voice_client :
            await ctx .send (" Сейчас ничего не играет!")
            return 

        if ctx .voice_client .is_playing ():
            ctx .voice_client .stop ()

            embed =discord .Embed (
            title ="⏭ Шarkы Geчildi",
            color =discord .Color .dark_grey (),
            timestamp =datetime .now ()
            )

            await ctx .send (embed =embed )
        else :
            await ctx .send (" Сейчас ничего не играет!")

    @commands .command (name ='queue',aliases =['kuyruk'])
    async def queue (self ,ctx ):
        """Kuyruгu gёster"""
        queue =self .get_queue (ctx .guild .id )

        if not queue :
            await ctx .send (" Kuyruk boш!")
            return 

        embed =discord .Embed (
        title =" Kuyruk",
        description =f"Всего {len(queue)} шarkы",
        color =discord .Color .dark_grey (),
        timestamp =datetime .now ()
        )

        # Иlk 10 шarkы
        for i ,song in enumerate (queue [:10 ],1 ):
            embed .add_field (
            name =f"{i}. {song['query']}",
            value =f"Ekleyen: {song['requester'].mention}",
            inline =False 
            )

        await ctx .send (embed =embed )

    @commands .command (name ='nowplaying',aliases =['шimdi','np'])
    async def nowplaying (self ,ctx ):
        """Шu an чalan шarkыyы gёster"""
        queue =self .get_queue (ctx .guild .id )

        if not queue :
            await ctx .send (" Сейчас ничего не играет!")
            return 

        current =queue [0 ]

        embed =discord .Embed (
        title =" Шu Anda Чalыyor",
        description =f"**Шarkы:** {current['query']}\n**Ekleyen:** {current['requester'].mention}",
        color =discord .Color .dark_grey (),
        timestamp =datetime .now ()
        )

        await ctx .send (embed =embed )

    @commands .command (name ='volume',aliases =['ses'])
    async def volume (self ,ctx ,volume :int =None ):
        """Голос уровеньsini настроить"""
        if not ctx .voice_client :
            await ctx .send (" Сейчас ничего не играет!")
            return 

        if volume is None :
            current_volume =ctx .voice_client .source .volume *100 if ctx .voice_client .source else 100 

            embed =discord .Embed (
            title =" Голос Уровеньsi",
            description =f"**Mevcut:** {int(current_volume)}%",
            color =discord .Color .dark_grey (),
            timestamp =datetime .now ()
            )

            await ctx .send (embed =embed )
            return 

        if volume <0 or volume >200 :
            await ctx .send (" Голос уровеньsi 0-200 между olmalы!")
            return 

        if ctx .voice_client .source :
            ctx .voice_client .source .volume =volume /100 

            embed =discord .Embed (
            title =" Голос Уровеньsi Настройкаlandы",
            description =f"**Новый Уровень:** {volume}%",
            color =discord .Color .dark_grey (),
            timestamp =datetime .now ()
            )

            await ctx .send (embed =embed )

    @commands .command (name ='leave',aliases =['ayrыl'])
    async def leave (self ,ctx ):
        """Голос каналыndan ayrыl"""
        if not ctx .voice_client :
            await ctx .send (" Шu anda bir ses каналыnda deгilim!")
            return 

        await ctx .voice_client .disconnect ()

        # Kuyruгu очистить
        if ctx .guild .id in self .queues :
            self .queues [ctx .guild .id ]=[]

        embed =discord .Embed (
        title =" Голос Каналыndan Ayrыldыm",
        color =discord .Color .dark_grey (),
        timestamp =datetime .now ()
        )

        await ctx .send (embed =embed )

    @commands .command (name ='clearqueue',aliases =['kuyruktemizle'])
    @commands .has_permissions (manage_guild =True )
    async def clearqueue (self ,ctx ):
        """Kuyruгu очистить"""
        if ctx .guild .id in self .queues :
            self .queues [ctx .guild .id ]=[]

        embed =discord .Embed (
        title =" Kuyruk Temizlendi",
        color =discord .Color .dark_grey (),
        timestamp =datetime .now ()
        )

        await ctx .send (embed =embed )

    @commands .command (name ='shuffle',aliases =['karышtыr'])
    async def shuffle (self ,ctx ):
        """Kuyruгu karышtыr"""
        queue =self .get_queue (ctx .guild .id )

        if len (queue )<2 :
            await ctx .send (" Kuyrukta en az 2 шarkы olmalы!")
            return 

            # Иlk шarkыyы koru
        current =queue [0 ]
        rest =queue [1 :]

        random .shuffle (rest )

        self .queues [ctx .guild .id ]=[current ]+rest 

        embed =discord .Embed (
        title =" Kuyruk Karышtыrыldы",
        description =f"**Всего:** {len(queue)} шarkы",
        color =discord .Color .dark_grey (),
        timestamp =datetime .now ()
        )

        await ctx .send (embed =embed )

    @commands .command (name ='loop',aliases =['tekrar'])
    async def loop (self ,ctx ):
        """Tekrar modunu открыть/закрыть"""
        queue =self .get_queue (ctx .guild .id )

        if not queue :
            await ctx .send (" Kuyruk boш!")
            return 

            # Basit loop - ilk шarkыyы sona добавить
        current =queue [0 ]
        queue .append (current )

        embed =discord .Embed (
        title =" Tekrar Modu",
        description =f"**Шarkы:** {current['query']}\nKuyruгun sonuna добавлено",
        color =discord .Color .dark_grey (),
        timestamp =datetime .now ()
        )

        await ctx .send (embed =embed )

    @commands .Cog .listener ()
    async def on_ready (self ):
        """Bot hazыr olduгunda"""
        log .info (f" MusicCog loaded")


async def setup (bot ):
    await bot .add_cog (MusicCog (bot ))
