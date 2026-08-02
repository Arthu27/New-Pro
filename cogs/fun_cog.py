"""
Fun Cog
Eгlence командыы cog'u
"""

import discord 
from discord .ext import commands 
from datetime import datetime 
import random 
import aiohttp 

from logger import get_logger 
log =get_logger ("fun_cog")



class FunCog (commands .Cog ):
    """Eгlence командыы cog'u"""

    def __init__ (self ,bot ):
        self .bot =bot 

    @commands .command (name ='8ball',aliases =['8top'])
    async def eightball (self ,ctx ,*,question :str ):
        """8 ball"""
        responses =[
        "Kesinlikle evet.",
        "Kesinlikle.",
        "Шюphesiz.",
        "Evet, kesinlikle.",
        "Buna gюvenebilirsiniz.",
        "Gёrdюгюm kadarыyla evet.",
        "Muhtemelen.",
        "Evet.",
        "Ишaretler evet'i gёsteriyor.",
        "Yanыt bulanыk, tekrar dene.",
        "Daha sonra sor.",
        "Шimdi sёylemesem daha iyi.",
        "Шu anda tahmin edemiyorum.",
        "Konsantre ol ve tekrar sor.",
        "Buna gюvenme.",
        "Cevabыm hayыr.",
        "Kaynaklarыm hayыr diyor.",
        "Gёrюnюшe gёre hayыr.",
        "Чok шюpheli.",
        "Hayыr."
        ]

        response =random .choice (responses )

        embed =discord .Embed (
        title =" 8 Ball",
        color =discord .Color .dark_grey (),
        timestamp =datetime .now ()
        )

        embed .add_field (name ="Soru",value =question ,inline =False )
        embed .add_field (name ="Cevap",value =response ,inline =False )

        await ctx .send (embed =embed )

    @commands .command (name ='coinflip',aliases =['yazыtura','coin'])
    async def coinflip (self ,ctx ):
        """Yazы tura"""
        result =random .choice (["Yazы","Tura"])

        embed =discord .Embed (
        title =" Yazы Tura",
        description =f"**Sonuч:** {result}",
        color =discord .Color .dark_grey (),
        timestamp =datetime .now ()
        )

        await ctx .send (embed =embed )

    @commands .command (name ='dice',aliases =['zar'])
    async def dice (self ,ctx ,sides :int =6 ):
        """Zar at"""
        if sides <2 :
            await ctx .send (" Zar en az 2 yюzlю olmalы!")
            return 

        result =random .randint (1 ,sides )

        embed =discord .Embed (
        title =" Zar Atышы",
        description =f"**{sides} yюzlю zar:** {result}",
        color =discord .Color .dark_grey (),
        timestamp =datetime .now ()
        )

        await ctx .send (embed =embed )

    @commands .command (name ='meme')
    async def meme (self ,ctx ):
        """Rastgele meme"""
        # Placeholder - gerчek API entegrasyonu yapыlabilir
        embed =discord .Embed (
        title =" Rastgele Meme",
        description ="Meme yюkleniyor...",
        color =discord .Color .dark_grey (),
        timestamp =datetime .now ()
        )

        await ctx .send (embed =embed )

    @commands .command (name ='joke',aliases =['шaka'])
    async def joke (self ,ctx ):
        """Rastgele шaka"""
        jokes =[
        "Programcы neden gёzlюk takar? Чюnkю C# gёremez!",
        "Bir SQL sorgusu bara girer, iki tabloya yaklaшыr ve sorar: 'JOIN olabilir miyim?'",
        "99 bug vardы, dюzelttim birini. 127 bug oldu.",
        "Bir programcы neden karanlыkta чalышыr? Чюnkю light bugs!",
        "Bir programcы karыsыnы terk etti чюnkю onunla interface yapamыyordu.",
        "Bir programcы neden gёzlюk takar? Чюnkю C# gёremez!",
        "Bir programcы neden evden чalышыr? Чюnkю evde daha fazla cache есть!",
        "Bir programcы neden bilgisнастройкаыnы sevdi? Чюnkю onunla byte'larы paylaшabiliyordu!",
        "Bir programcы neden bilgisнастройкаыyla evlendi? Чюnkю onunla чok iyi anlaшыyordu!",
        "Bir programcы neden bilgisнастройкаыyla kavga etti? Чюnkю onunla чok fazla conflict vardы!"
        ]

        joke =random .choice (jokes )

        embed =discord .Embed (
        title =" Rastgele Шaka",
        description =joke ,
        color =discord .Color .dark_grey (),
        timestamp =datetime .now ()
        )

        await ctx .send (embed =embed )

    @commands .command (name ='cat',aliases =['kedi'])
    async def cat (self ,ctx ):
        """Rastgele kedi resmi"""
        # Placeholder - gerчek API entegrasyonu yapыlabilir
        embed =discord .Embed (
        title =" Rastgele Kedi",
        description ="Kedi resmi yюkleniyor...",
        color =discord .Color .dark_grey (),
        timestamp =datetime .now ()
        )

        await ctx .send (embed =embed )

    @commands .command (name ='dog',aliases =['kёpek'])
    async def dog (self ,ctx ):
        """Rastgele kёpek resmi"""
        # Placeholder - gerчek API entegrasyonu yapыlabilir
        embed =discord .Embed (
        title =" Rastgele Kёpek",
        description ="Kёpek resmi yюkleniyor...",
        color =discord .Color .dark_grey (),
        timestamp =datetime .now ()
        )

        await ctx .send (embed =embed )

    @commands .command (name ='quote',aliases =['alыntы'])
    async def quote (self ,ctx ):
        """Rastgele alыntы"""
        quotes =[
        "Hayat kыsa, sanat длинный.",
        "Bilgi gючtюr.",
        "Baшarы, hazыrlыkla fыrsatыn buluшtuгu yerdir.",
        "Gelecek, bugюnюn hazыrlыгыna baгlыdыr.",
        "Baшarыsыzlыk, baшarыnыn baharatыdыr.",
        "Hayal edebiliyorsan, yapabilirsin.",
        "Baшarы, kючюk чabalarыn her gюn tekrarlanmasыdыr.",
        "Zorluklar, bizi gючlendirir.",
        "Baшarы, pes etmemektir.",
        "Hayat, bir yolculuktur, varыш noktasы deгil."
        ]

        quote =random .choice (quotes )

        embed =discord .Embed (
        title =" Rastgele Alыntы",
        description =f"*{quote}*",
        color =discord .Color .dark_grey (),
        timestamp =datetime .now ()
        )

        await ctx .send (embed =embed )

    @commands .Cog .listener ()
    async def on_ready (self ):
        """Bot hazыr olduгunda"""
        log .info (f" FunCog loaded")


async def setup (bot ):
    await bot .add_cog (FunCog (bot ))
