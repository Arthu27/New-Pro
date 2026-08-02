"""
Level Cog
Расширенная уровень система cog'u
"""
import discord 
from discord .ext import commands 
from datetime import datetime 
import random 

from logger import get_logger 
log =get_logger ("level_cog")



class LevelCog (commands .Cog ):
    """Расширенная уровень система cog'u"""

    def __init__ (self ,bot ):
        self .bot =bot 

    @commands .command (name ='level-rank',aliases =['уровень'])
    async def rank (self ,ctx ,member :discord .Member =None ):
        """Уровень kartыnы gёster"""
        member =member or ctx .author 

        embed =discord .Embed (
        title =f" {member.display_name}'s Уровень",
        color =discord .Color .dark_grey (),
        timestamp =datetime .now ()
        )

        embed .set_thumbnail (url =member .display_avatar .url )
        embed .add_field (name ="Уровень",value ="10",inline =True )
        embed .add_field (name ="XP",value ="5,000/10,000",inline =True )
        embed .add_field (name ="Sыralama",value ="#5",inline =True )

        await ctx .send (embed =embed )

    @commands .command (name ='level-lb',aliases =['level-top'])
    async def leaderboard (self ,ctx ):
        """Уровень lider tablosunu gёster"""
        embed =discord .Embed (
        title =" Уровень Lider Tablosu",
        color =discord .Color .dark_grey (),
        timestamp =datetime .now ()
        )

        # Ёrnek lider tablosu
        for i in range (1 ,11 ):
            embed .add_field (
            name =f"#{i} Пользователь{i}",
            value =f"Уровень {20-i} | XP: {10000-i*500:,}",
            inline =False 
            )

        await ctx .send (embed =embed )

    @commands .command (name ='rewards',aliases =['ёdюller'])
    async def rewards (self ,ctx ):
        """Уровень ёdюllerini gёster"""
        embed =discord .Embed (
        title =" Уровень Ёdюlleri",
        color =discord .Color .dark_grey (),
        timestamp =datetime .now ()
        )

        rewards =[
        ("Уровень 5","@Юye rolю"),
        ("Уровень 10","@Активный Юye rolю"),
        ("Уровень 20","@VIP rolю"),
        ("Уровень 50","@Efsane rolю")
        ]

        for level ,reward in rewards :
            embed .add_field (
            name =level ,
            value =reward ,
            inline =True 
            )

        await ctx .send (embed =embed )

    @commands .command (name ='setlevel',aliases =['уровеньнастройкаla'])
    @commands .has_permissions (administrator =True )
    async def setlevel (self ,ctx ,member :discord .Member ,level :int ):
        """Kullanыcыnыn уровеньsini настроить"""
        embed =discord .Embed (
        title =" Уровень Настройкаlandы",
        description =f"**{member.mention}'ыn уровеньsi:** {level}",
        color =discord .Color .dark_grey (),
        timestamp =datetime .now ()
        )

        await ctx .send (embed =embed )

    @commands .Cog .listener ()
    async def on_ready (self ):
        """Bot hazыr olduгunda"""
        log .info (f" LevelCog loaded")


async def setup (bot ):
    await bot .add_cog (LevelCog (bot ))
