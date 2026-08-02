"""
Search Cog
Arama командыы cog'u
"""

import discord 
from discord .ext import commands 
from datetime import datetime 

from logger import get_logger 
log =get_logger ("search_cog")



class SearchCog (commands .Cog ):
    """Arama командыы cog'u"""

    def __init__ (self ,bot ):
        self .bot =bot 

    @commands .command (name ='search',aliases =['ara'])
    async def search (self ,ctx ,*,query :str ):
        """Общий arama yap"""
        embed =discord .Embed (
        title =f" Arama: {query}",
        description ="Arama sonuчlarы загружается...",
        color =discord .Color .dark_grey (),
        timestamp =datetime .now ()
        )

        await ctx .send (embed =embed )

    @commands .command (name ='searchuser',aliases =['kullanыcыara'])
    async def searchuser (self ,ctx ,*,query :str ):
        """Пользователь ara"""
        members =[m for m in ctx .guild .members if query .lower ()in m .display_name .lower ()]

        if not members :
            await ctx .send (" Пользователь не найден!")
            return 

        embed =discord .Embed (
        title =f" Пользователь Arama: {query}",
        description =f"**Bulunan:** {len(members)} пользователь",
        color =discord .Color .dark_grey (),
        timestamp =datetime .now ()
        )

        for member in members [:10 ]:
            embed .add_field (
            name =member .display_name ,
            value =f"ID: {member.id}",
            inline =True 
            )

        await ctx .send (embed =embed )

    @commands .command (name ='searchticket',aliases =['ticketara'])
    async def searchticket (self ,ctx ,ticket_id :str ):
        """Ticket ara"""
        embed =discord .Embed (
        title =f" Ticket Arama: {ticket_id}",
        description ="Ticket информация загружается...",
        color =discord .Color .dark_grey (),
        timestamp =datetime .now ()
        )

        await ctx .send (embed =embed )

    @commands .command (name ='searchrole',aliases =['rolara'])
    async def searchrole (self ,ctx ,*,query :str ):
        """Роль ara"""
        roles =[r for r in ctx .guild .roles if query .lower ()in r .name .lower ()]

        if not roles :
            await ctx .send (" Роль не найдена!")
            return 

        embed =discord .Embed (
        title =f" Роль Arama: {query}",
        description =f"**Bulunan:** {len(roles)} роль",
        color =discord .Color .dark_grey (),
        timestamp =datetime .now ()
        )

        for role in roles [:10 ]:
            embed .add_field (
            name =role .name ,
            value =f"ID: {role.id} | Юyeler: {len(role.members)}",
            inline =True 
            )

        await ctx .send (embed =embed )

    @commands .command (name ='searchchannel',aliases =['каналara'])
    async def searchchannel (self ,ctx ,*,query :str ):
        """Канал ara"""
        channels =[c for c in ctx .guild .channels if query .lower ()in c .name .lower ()]

        if not channels :
            await ctx .send (" Канал не найден!")
            return 

        embed =discord .Embed (
        title =f" Канал Arama: {query}",
        description =f"**Bulunan:** {len(channels)} канал",
        color =discord .Color .dark_grey (),
        timestamp =datetime .now ()
        )

        for channel in channels [:10 ]:
            embed .add_field (
            name =channel .name ,
            value =f"ID: {channel.id}",
            inline =True 
            )

        await ctx .send (embed =embed )

    @commands .Cog .listener ()
    async def on_ready (self ):
        """Bot hazыr olduгunda"""
        log .info (f" SearchCog loaded")


async def setup (bot ):
    await bot .add_cog (SearchCog (bot ))
