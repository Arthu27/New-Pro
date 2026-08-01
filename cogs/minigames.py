"""Mini oyunlar"""
import discord 
from discord .ext import commands 
from discord import app_commands 
import random 
from cogs .embed_utils import _divider ,now_ts 

class MiniGames (commands .Cog ):
    def __init__ (self ,bot ):
        self .bot =bot 
        self .active_guesses ={}

    @app_commands .command (name ='coinflip',description ='Metin tura at')
    async def coin_flip (self ,interaction :discord .Interaction ,tahmin :str =None ):
        result =random .choice (['Metin','Tura'])
        e =discord .Embed (title ="  Metin Tura",color =0xF1C40F ,timestamp =discord .utils .utcnow ())
        e .description =f"```ansi\n\u001b[1;33m PARA ATILDI\u001b[0m\n```\n{_divider()}"
        e .add_field (name =" результат",value =f"```{result}```",inline =True )
        if tahmin :
            tahmin_norm =tahmin .lower ().strip ()
            correct =(tahmin_norm in ['текст','текст']and result =='Metin')or (tahmin_norm =='tura'and result =='Tura')
            e .add_field (name =" Tahminin",value =f"```{tahmin.capitalize()}```",inline =True )
            e .add_field (name =" Состояние",value =f"```{' Верно!' if correct else ' Неверно!'}```",inline =True )
            e .color =0x2ECC71 if correct else 0xE74C3C 
        e .set_footer (text =f"Желание: {interaction.user.name}",icon_url =interaction .user .display_avatar .url )
        await interaction .response .send_message (embed =e )

    @app_commands .command (name ='роль',description ='Zar at')
    @app_commands .describe (adet ='Сколько zar atыlsыn (1-5)')
    async def rolel_dice (self ,interaction :discord .Interaction ,adet :int =1 ):
        adet =max (1 ,min (5 ,adet ))
        results =[random .randint (1 ,6 )for _ in range (adet )]
        dice_emojis ={1 :'',2 :'',3 :'',4 :'',5 :'',6 :''}
        e =discord .Embed (title ="  Zar Atыldы!",color =0x9B59B6 ,timestamp =discord .utils .utcnow ())
        e .description =(
        f"```ansi\n\u001b[1;35m ZAR SONUCU\u001b[0m\n```\n{_divider()}\n\n"
        f"# {' '.join(dice_emojis[r] for r in results)}\n\n{_divider()}"
        )
        e .add_field (name =" результат",value =f"```{' | '.join(str(r) for r in results)}```",inline =True )
        if adet >1 :
            e .add_field (name =" Всего",value =f"```{sum(results)}```",inline =True )
        e .set_footer (text =f"Желание: {interaction.user.name}",icon_url =interaction .user .display_avatar .url )
        await interaction .response .send_message (embed =e )

    @app_commands .command (name ='rps',description ='Taш kaгыt makas oyna')
    @app_commands .choices (secim =[
    app_commands .Choice (name ='Taш',value ='taш'),
    app_commands .Choice (name ='Kaгыt',value ='kaгыt'),
    app_commands .Choice (name ='Makas',value ='makas'),
    ])
    async def rps (self ,interaction :discord .Interaction ,secim :str ):
        choices =['taш','kaгыt','makas']
        emojis ={'taш':'','kaгыt':'','makas':''}
        bot_choice =random .choice (choices )
        wins ={'taш':'makas','kaгыt':'taш','makas':'kaгыt'}
        if secim ==bot_choice :
            result ,color ,badge =' Berabere!',0xF39C12 ," BERABERE"
        elif wins [secim ]==bot_choice :
            result ,color ,badge =' Kazandыn!',0x2ECC71 ," KAZANDIN"
        else :
            result ,color ,badge =' Kaybettin!',0xE74C3C ," KAYBETTИN"
        e =discord .Embed (title ="  Taш Kaгыt Makas",color =color ,timestamp =discord .utils .utcnow ())
        e .description =(
        f"```ansi\n\u001b[1;{'32' if '' in badge else '31' if '' in badge else '33'}m{badge}\u001b[0m\n```\n{_divider()}"
        )
        e .add_field (name =" Senin Выбор",value =f"# {emojis[secim]} {secim.capitalize()}",inline =True )
        e .add_field (name =" Botun Выбор",value =f"# {emojis[bot_choice]} {bot_choice.capitalize()}",inline =True )
        e .add_field (name =" результат",value =f"```{result}```",inline =False )
        e .set_footer (text =f"Желание: {interaction.user.name}",icon_url =interaction .user .display_avatar .url )
        await interaction .response .send_message (embed =e )

    @app_commands .command (name ='guess-start',description ='Число tahmin oyunu запустить (1-100)')
    async def start_guess (self ,interaction :discord .Interaction ):
        gid =interaction .guild_id 
        if gid in self .active_guesses :
            await interaction .response .send_message (' Zaten активен bir oyun есть! `/oyun-tahmin` с продолжить et.',ephemeral =True )
            return 
        number =random .randint (1 ,100 )
        self .active_guesses [gid ]={'number':number ,'attempts':0 ,'started_by':interaction .user .id }
        e =discord .Embed (title ="  Число Tahmin Играu Baшladы!",color =0x3498DB ,timestamp =discord .utils .utcnow ())
        e .description =(
        f"```ansi\n\u001b[1;34m OYUN BAШLADI\u001b[0m\n```\n{_divider()}\n\n"
        f"1 с 100 arasыnda bir число tuttum!\n"
        f"`/oyun-tahmin [число]` команда tahmin et.\n\n{_divider()}"
        )
        e .set_thumbnail (url =interaction .user .display_avatar .url )
        e .add_field (name =" Aramalыk",value ="```1 — 100```",inline =True )
        e .add_field (name =" Запуск",value =interaction .user .mention ,inline =True )
        e .add_field (name =" Подсказка",value ="*Используйте подсказки больше/меньше для отслеживания!*",inline =False )
        e .set_footer (text =f"Aether • {interaction.guild.name}",icon_url =interaction .guild .icon .url if interaction .guild .icon else None )
        await interaction .response .send_message (embed =e )

    @app_commands .command (name ='guess',description ='Число tahmin et')
    @app_commands .describe (число ='Tahminin (1-100)')
    async def guess (self ,interaction :discord .Interaction ,число :int ):
        gid =interaction .guild_id 
        if gid not in self .active_guesses :
            await interaction .response .send_message (' Активен oyun нет! `/oyun-запустить` с запустить.',ephemeral =True )
            return 
        game =self .active_guesses [gid ]
        game ['attempts']+=1 
        number =game ['number']
        if number ==number :
            del self .active_guesses [gid ]
            e =discord .Embed (title ="  ВЕРНО TAHMИN!",color =0x2ECC71 ,timestamp =discord .utils .utcnow ())
            e .description =(
            f"```ansi\n\u001b[1;32m KAZANDIN!\u001b[0m\n```\n{_divider()}\n\n"
            f"{interaction.user.mention} число buldu! \n\n{_divider()}"
            )
            e .add_field (name =" Число",value =f"```{number}```",inline =True )
            e .add_field (name =" Попытка",value =f"```{game['attempts']} deneme```",inline =True )
        elif number <number :
            e =discord .Embed (title ="  Более Большой!",color =0xF39C12 ,timestamp =discord .utils .utcnow ())
            e .description =f"```ansi\n\u001b[1;33m БОЛЕЕ БОЛЬШОЙ\u001b[0m\n```\n{_divider()}"
            e .add_field (name =" Tahminin",value =f"```{number}```",inline =True )
            e .add_field (name =" Попытка",value =f"```{game['attempts']}. deneme```",inline =True )
            e .add_field (name =" Подсказка",value ="*Число больше, двигайтесь вверх!*",inline =False )
        else :
            e =discord .Embed (title ="  Более Маленький!",color =0xF39C12 ,timestamp =discord .utils .utcnow ())
            e .description =f"```ansi\n\u001b[1;33m БОЛЕЕ МАЛЕНЬКИЙ\u001b[0m\n```\n{_divider()}"
            e .add_field (name =" Tahminin",value =f"```{number}```",inline =True )
            e .add_field (name =" Попытка",value =f"```{game['attempts']}. deneme```",inline =True )
            e .add_field (name =" Подсказка",value ="*Число меньше, двигайтесь вниз!*",inline =False )
        e .set_footer (text =f"Aether • {interaction.guild.name}",icon_url =interaction .guild .icon .url if interaction .guild .icon else None )
        await interaction .response .send_message (embed =e )

    @app_commands .command (name ='8ball',description ='Sihirli 8 top - soruyu sor!')
    @app_commands .describe (soru ='Вопросnuz')
    async def magic_8ball (self ,interaction :discord .Interaction ,soru :str ):
        responses =[
        (' Kesinlikle evet!',0x2ECC71 ),(' Да, ёyle видеть.',0x2ECC71 ),
        (' Большой ihtimalle evet.',0x2ECC71 ),(' Buna доверие.',0x2ECC71 ),
        (' Шu an сказатьmek сложный.',0xF39C12 ),(' Tekrar sor.',0xF39C12 ),
        (' Сейчас ответитьemem.',0xF39C12 ),(' Konsantre ol ve tekrar sor.',0xF39C12 ),
        (' Sanmыyorum.',0xE74C3C ),(' Нет.',0xE74C3C ),
        (' Kesinlikle hayыr.',0xE74C3C ),(' Видеть по hayыr.',0xE74C3C ),
        ]
        cevap ,color =random .choice (responses )
        e =discord .Embed (title ="  Sihirli 8 Top",color =color ,timestamp =discord .utils .utcnow ())
        e .description =(
        f"```ansi\n\u001b[1;35m CEVAP GELИYOR...\u001b[0m\n```\n{_divider()}"
        )
        e .add_field (name =" Вопрос",value =f"*{soru}*",inline =False )
        e .add_field (name =" Ответ",value =f"```{cevap}```",inline =False )
        e .set_footer (text =f"Желание: {interaction.user.name}",icon_url =interaction .user .display_avatar .url )
        await interaction .response .send_message (embed =e )

    @app_commands .command (name ='oyun-rastgele-uye',description ='С сервера rastgele bir участник выбрать')
    async def random_member (self ,interaction :discord .Interaction ,role :discord .Role =None ):
        members =[m for m in interaction .guild .members if not m .bot ]
        if role :
            members =[m for m in members if role in m .roles ]
        if not members :
            await interaction .response .send_message (' Uygun участник не найден!',ephemeral =True )
            return 
        secilen =random .choice (members )
        e =discord .Embed (title ="  Rastgele Участник Выбрано!",color =0xDC143C ,timestamp =discord .utils .utcnow ())
        e .description =(
        f"```ansi\n\u001b[1;31m ВЫБОР сделано\u001b[0m\n```\n{_divider()}\n\n"
        f"Kura тянуть ve kazanan belli oldu! \n\n{_divider()}"
        )
        e .set_thumbnail (url =secilen .display_avatar .url )
        e .add_field (name =" Выбрать",value =secilen .mention ,inline =True )
        if role :
            e .add_field (name =" Роли Filtresi",value =role .mention ,inline =True )
        e .add_field (name =" Кандидаты",value =f"```{len(members)} человек```",inline =True )
        e .set_footer (text =f"Aether • {interaction.guild.name}",icon_url =interaction .guild .icon .url if interaction .guild .icon else None )
        await interaction .response .send_message (embed =e )


async def setup (bot ):
    await bot .add_cog (MiniGames (bot ),guilds =[discord .Object (id =1421244140359909513 ),discord .Object (id =1107038411895881788 ),discord .Object (id =1498837105915330562 )])
