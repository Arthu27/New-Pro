"""
Music Cog
Музыкальные команды
"""

import discord 
from discord .ext import commands 
from datetime import datetime 
import asyncio 
import random 

from logger import get_logger 
log =get_logger ("music_cog")



class MusicCog (commands .Cog ):
    """Музыкальные команды"""

    def __init__ (self ,bot ):
        self .bot =bot 
        self .queues ={}# guild_id -> очередь

    def get_queue (self ,guild_id :int )->list :
        """Получить очередь сервера"""
        if guild_id not in self .queues :
            self .queues [guild_id ]=[]
        return self .queues [guild_id ]

    @commands .command (name ='play',aliases =['играй'])
    async def play (self ,ctx ,*,query :str ):
        """Включить трек"""
        # Проверка голосового канала
        if not ctx .author .voice :
            await ctx .send ("🎧 Сначала подключитесь к голосовому каналу!")
            return 

            # Бот подключается к голосовому каналу
        voice_channel =ctx .author .voice .channel 

        if not ctx .voice_client :
            await voice_channel .connect ()

            # Добавить в очередь
        queue =self .get_queue (ctx .guild .id )
        queue .append ({
        'query':query ,
        'requester':ctx .author 
        })

        embed =discord .Embed (
        title ="🎵 Добавлено в очередь",
        description =f"**Трек:** {query}\n**Позиция:** {len(queue)}",
        color =discord .Color .dark_grey (),
        timestamp =datetime .now ()
        )

        from cogs .icons import send_with_icon 
        await send_with_icon (ctx ,embed ,'music')

    @commands .command (name ='pause',aliases =['пауза'])
    async def pause (self ,ctx ):
        """Поставить трек на паузу"""
        if not ctx .voice_client :
            await ctx .send ("🔇 Сейчас ничего не играет!")
            return 

        if ctx .voice_client .is_playing ():
            ctx .voice_client .pause ()

            embed =discord .Embed (
            title ="⏸ Пауза",
            color =discord .Color .dark_grey (),
            timestamp =datetime .now ()
            )

            await ctx .send (embed =embed )
        else :
            await ctx .send ("🔇 Сейчас ничего не играет!")

    @commands .command (name ='resume',aliases =['продолжить'])
    async def resume (self ,ctx ):
        """Продолжить воспроизведение трека"""
        if not ctx .voice_client :
            await ctx .send ("🔇 Сейчас ничего не играет!")
            return 

        if ctx .voice_client .is_paused ():
            ctx .voice_client .resume ()

            embed =discord .Embed (
            title ="▶️ Воспроизведение продолжено",
            color =discord .Color .dark_grey (),
            timestamp =datetime .now ()
            )

            await ctx .send (embed =embed )
        else :
            await ctx .send ("ℹ️ Сейчас нет трека на паузе!")

    @commands .command (name ='skip',aliases =['дальше'])
    async def skip (self ,ctx ):
        """Пропустить трек"""
        if not ctx .voice_client :
            await ctx .send ("🔇 Сейчас ничего не играет!")
            return 

        if ctx .voice_client .is_playing ():
            ctx .voice_client .stop ()

            embed =discord .Embed (
            title ="⏭ Трек пропущен",
            color =discord .Color .dark_grey (),
            timestamp =datetime .now ()
            )

            await ctx .send (embed =embed )
        else :
            await ctx .send ("🔇 Сейчас ничего не играет!")

    @commands .command (name ='queue',aliases =['очередь'])
    async def queue (self ,ctx ):
        """Показать очередь"""
        queue =self .get_queue (ctx .guild .id )

        if not queue :
            await ctx .send ("🎵 Очередь пуста!")
            return 

        embed =discord .Embed (
        title ="🎶 Очередь",
        description =f"Всего треков: {len(queue)}",
        color =discord .Color .dark_grey (),
        timestamp =datetime .now ()
        )

        # Первые 10 треков
        for i ,song in enumerate (queue [:10 ],1 ):
            embed .add_field (
            name =f"{i}. {song['query']}",
            value =f"Добавил: {song['requester'].mention}",
            inline =False 
            )

        await ctx .send (embed =embed )

    @commands .command (name ='nowplaying',aliases =['сейчас','np'])
    async def nowplaying (self ,ctx ):
        """Показать играющий трек"""
        queue =self .get_queue (ctx .guild .id )

        if not queue :
            await ctx .send ("🔇 Сейчас ничего не играет!")
            return 

        current =queue [0 ]

        embed =discord .Embed (
        title ="🎧 Сейчас играет",
        description =f"**Трек:** {current['query']}\n**Добавил:** {current['requester'].mention}",
        color =discord .Color .dark_grey (),
        timestamp =datetime .now ()
        )

        from cogs .icons import send_with_icon 
        await send_with_icon (ctx ,embed ,'music')

    @commands .command (name ='volume',aliases =['громкость'])
    async def volume (self ,ctx ,volume :int =None ):
        """Настроить уровень громкости"""
        if not ctx .voice_client :
            await ctx .send ("🔇 Сейчас ничего не играет!")
            return 

        if volume is None :
            current_volume =ctx .voice_client .source .volume *100 if ctx .voice_client .source else 100 

            embed =discord .Embed (
            title ="🔊 Громкость",
            description =f"**Текущая:** {int(current_volume)}%",
            color =discord .Color .dark_grey (),
            timestamp =datetime .now ()
            )

            await ctx .send (embed =embed )
            return 

        if volume <0 or volume >200 :
            await ctx .send ("⚠️ Уровень громкости должен быть от 0 до 200!")
            return 

        if ctx .voice_client .source :
            ctx .voice_client .source .volume =volume /100 

            embed =discord .Embed (
            title ="🔊 Громкость настроена",
            description =f"**Новый уровень:** {volume}%",
            color =discord .Color .dark_grey (),
            timestamp =datetime .now ()
            )

            await ctx .send (embed =embed )

    @commands .command (name ='leave',aliases =['выйти'])
    async def leave (self ,ctx ):
        """Выйти из голосового канала"""
        if not ctx .voice_client :
            await ctx .send ("ℹ️ Я сейчас не в голосовом канале!")
            return 

        await ctx .voice_client .disconnect ()

        # Очистить очередь
        if ctx .guild .id in self .queues :
            self .queues [ctx .guild .id ]=[]

        embed =discord .Embed (
        title ="👋 Вышел из голосового канала",
        color =discord .Color .dark_grey (),
        timestamp =datetime .now ()
        )

        await ctx .send (embed =embed )

    @commands .command (name ='clearqueue',aliases =['очиститьочередь'])
    @commands .has_permissions (manage_guild =True )
    async def clearqueue (self ,ctx ):
        """Очистить очередь"""
        if ctx .guild .id in self .queues :
            self .queues [ctx .guild .id ]=[]

        embed =discord .Embed (
        title ="🧹 Очередь очищена",
        color =discord .Color .dark_grey (),
        timestamp =datetime .now ()
        )

        await ctx .send (embed =embed )

    @commands .command (name ='shuffle',aliases =['перемешать'])
    async def shuffle (self ,ctx ):
        """Перемешать очередь"""
        queue =self .get_queue (ctx .guild .id )

        if len (queue )<2 :
            await ctx .send ("⚠️ В очереди должно быть минимум 2 трека!")
            return 

            # Сохранить первый трек
        current =queue [0 ]
        rest =queue [1 :]

        random .shuffle (rest )

        self .queues [ctx .guild .id ]=[current ]+rest 

        embed =discord .Embed (
        title ="🔀 Очередь перемешана",
        description =f"**Всего:** {len(queue)} треков",
        color =discord .Color .dark_grey (),
        timestamp =datetime .now ()
        )

        await ctx .send (embed =embed )

    @commands .command (name ='loop',aliases =['tekrar','povtor','повтор'])
    async def loop (self ,ctx ):
        """Включить/выключить повтор трека"""
        queue =self .get_queue (ctx .guild .id )

        if not queue :
            await ctx .send ("🎵 Очередь пуста!")
            return 

            # Простой повтор — первый трек в конец
        current =queue [0 ]
        queue .append (current )

        embed =discord .Embed (
        title ="🔁 Режим повтора",
        description =f"**Трек:** {current['query']}\nДобавлен в конец очереди",
        color =discord .Color .dark_grey (),
        timestamp =datetime .now ()
        )

        await ctx .send (embed =embed )

    @commands .Cog .listener ()
    async def on_ready (self ):
        """Когда бот готов"""
        log .info (" MusicCog loaded")


async def setup (bot ):
    await bot .add_cog (MusicCog (bot ))
