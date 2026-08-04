"""
Welcome Cog
Hoш geldin системаi cog'u
"""

import discord 
from discord .ext import commands 
from datetime import datetime 

from logger import get_logger 
log =get_logger ("welcome_cog")



class WelcomeCog (commands .Cog ):
    """Hoш geldin системаi cog'u"""

    def __init__ (self ,bot ):
        self .bot =bot 
        self .welcome_message ="Hoш geldin {user}! Серверmuza katыldыгыn iчin teшekkюrler!"
        self .welcome_channel_id =None 

    @commands .command (name ='setwelcome',aliases =['hoшgeldinнастройкаla'])
    @commands .has_permissions (administrator =True )
    async def setwelcome (self ,ctx ,*,message :str ):
        """Hoш geldin сообщениеыnы настройкаla"""
        self .welcome_message =message 

        embed =discord .Embed (
        title ="✅ Приветственное сообщение обновлено",
        description =f"**Новый текст:** {message}",
        color =discord .Color .dark_grey (),
        timestamp =datetime .now ()
        )

        await ctx .send (embed =embed )

    @commands .command (name ='setwelcomechannel',aliases =['hoшgeldinканалы'])
    @commands .has_permissions (administrator =True )
    async def setwelcomechannel (self ,ctx ,channel :discord .TextChannel ):
        """Hoш geldin каналыnы настройкаla"""
        self .welcome_channel_id =channel .id 

        embed =discord .Embed (
        title ="✅ Канал приветствий обновлён",
        description =f"**Новый канал:** {channel.mention}",
        color =discord .Color .dark_grey (),
        timestamp =datetime .now ()
        )

        await ctx .send (embed =embed )

    @commands .command (name ='testwelcome',aliases =['hoшgeldintest'])
    async def testwelcome (self ,ctx ):
        """Hoш geldin сообщениеыnы test et"""
        message =self .welcome_message .replace ("{user}",ctx .author .mention )

        embed =discord .Embed (
        title ="👋 Добро пожаловать!",
        description =message ,
        color =discord .Color .dark_grey (),
        timestamp =datetime .now ()
        )

        from cogs .icons import send_with_icon 
        await send_with_icon (ctx ,embed ,'welcome')

    @commands .Cog .listener ()
    async def on_member_join (self ,member ):
        """Новый юye katыldыгыnda"""
        if not self .welcome_channel_id :
            return 

        channel =member .guild .get_channel (self .welcome_channel_id )
        if not channel :
            return 

        message =self .welcome_message .replace ("{user}",member .mention )

        embed =discord .Embed (
        title ="👋 Добро пожаловать!",
        description =message ,
        color =discord .Color .dark_grey (),
        timestamp =datetime .now ()
        )

        from cogs .icons import send_with_icon 
        await send_with_icon (channel ,embed ,'welcome')

    @commands .Cog .listener ()
    async def on_ready (self ):
        """Bot hazыr olduгunda"""
        log .info (f" WelcomeCog loaded")


async def setup (bot ):
    await bot .add_cog (WelcomeCog (bot ))
