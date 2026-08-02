"""
AutoModeration Cog
Otomatik moderasyon cog'u
"""

import discord 
from discord .ext import commands 
from datetime import datetime 
import re 

from logger import get_logger 
log =get_logger ("automod_cog")



class AutoModCog (commands .Cog ):
    """Otomatik moderasyon cog'u"""

    def __init__ (self ,bot ):
        self .bot =bot 
        self .banned_words =['kюfюr1','kюfюr2','kюfюr3']

    @commands .command (name ='automod',aliases =['otomod'])
    @commands .has_permissions (administrator =True )
    async def automod (self ,ctx ):
        """Otomatik moderasyon настройкаlarыnы gёster"""
        embed =discord .Embed (
        title =" Otomatik Moderasyon",
        color =discord .Color .dark_grey (),
        timestamp =datetime .now ()
        )

        embed .add_field (name ="Anti-Spam",value =" Активный",inline =True )
        embed .add_field (name ="Anti-Link",value =" Активный",inline =True )
        embed .add_field (name ="Anti-Mention",value =" Активный",inline =True )
        embed .add_field (name ="Word Filter",value =" Активный",inline =True )
        embed .add_field (name ="Auto-Delete",value =" Активный",inline =True )
        embed .add_field (name ="Auto-Warn",value =" Активный",inline =True )

        await ctx .send (embed =embed )

    @commands .command (name ='addword',aliases =['kelimeekle'])
    @commands .has_permissions (administrator =True )
    async def addword (self ,ctx ,word :str ):
        """Запретlы kelime добавить"""
        self .banned_words .append (word .lower ())

        embed =discord .Embed (
        title =" Kelime Добавлен",
        description =f"**Запретlы kelime:** {word}",
        color =discord .Color .dark_grey (),
        timestamp =datetime .now ()
        )

        await ctx .send (embed =embed )

    @commands .command (name ='removeword',aliases =['kelimesil'])
    @commands .has_permissions (administrator =True )
    async def removeword (self ,ctx ,word :str ):
        """Запретlы kelimeyi kaldыr"""
        if word .lower ()in self .banned_words :
            self .banned_words .remove (word .lower ())

            embed =discord .Embed (
            title =" Kelime Kaldыrыldы",
            description =f"**Kaldыrыlan kelime:** {word}",
            color =discord .Color .dark_grey (),
            timestamp =datetime .now ()
            )

            await ctx .send (embed =embed )
        else :
            await ctx .send (" Kelime не найдено!")

    @commands .command (name ='wordlist',aliases =['kelimelistesi'])
    async def wordlist (self ,ctx ):
        """Запретlы kelime listesini gёster"""
        embed =discord .Embed (
        title =" Запретlы Kelimeler",
        description =", ".join (self .banned_words [:20 ])if self .banned_words else "Запретlы kelime нет",
        color =discord .Color .dark_grey (),
        timestamp =datetime .now ()
        )

        await ctx .send (embed =embed )

    @commands .Cog .listener ()
    async def on_message (self ,message ):
        """Сообщение geldiгinde проверить et"""
        if message .author .bot :
            return 

            # Запретlы kelime проверкаю
        for word in self .banned_words :
            if word in message .content .lower ():
                await message .delete ()
                await message .channel .send (f" {message.author.mention} Запретlы kelime kullandыnыz!",delete_after =5 )
                return 

    @commands .Cog .listener ()
    async def on_ready (self ):
        """Bot hazыr olduгunda"""
        log .info (f" AutoModCog loaded")


async def setup (bot ):
    await bot .add_cog (AutoModCog (bot ))
