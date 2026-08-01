"""
Aether — Embed & GIF modul
Все cog've importiruyut den bunun modulya.
"""
import discord 
import random 
from datetime import datetime ,timezone 

DIVIDER =""

GIFS ={
"ban":["https://media.tenor.com/x8v1oNUOmg4AAAAC/ban-hammer.gif","https://media.tenor.com/deECPGRKlmYAAAAC/ban-banned.gif"],
"kick":["https://media.tenor.com/OtNpHMFHMhsAAAAC/kick-out.gif"],
"mute":["https://media.tenor.com/zjaHBJMFMIsAAAAC/shh-quiet.gif"],
"warn":["https://media.tenor.com/xTMoHBqFkFkAAAAC/warning-caution.gif"],
"timeout":["https://media.tenor.com/zjaHBJMFMIsAAAAC/shh-quiet.gif"],
"unban":["https://media.tenor.com/3Ky6UNqMFpkAAAAC/talking-speak.gif"],
"untimeout":["https://media.tenor.com/3Ky6UNqMFpkAAAAC/talking-speak.gif"],
"success":["https://media.tenor.com/ZBDpMFBMFpkAAAAC/celebration-party.gif"],
"error":["https://media.tenor.com/x8v1oNUOmg4AAAAC/ban-hammer.gif"],
}


def gif (category :str )->str :
    pool =GIFS .get (category ,GIFS ["success"])
    return random .choice (pool )


def now_ts ()->int :
    return int (datetime .now (timezone .utc ).timestamp ())


def Aether_footer (guild =None ,extra =""):
    text =f"Aether{' · ' + extra if extra else ''}"
    icon =guild .icon .url if guild and guild .icon else None 
    return {"text":text ,"icon_url":icon }


def _divider ()->str :
    return DIVIDER 


    #  DM Embed (отправл пользователю) 

def mod_dm_embed (action ,guild ,moderator ,reason =None ,extra_fields =None ,gif_key =None ):
    """DM сообщение пользователю — minimalizm stil"""
    configs ={
    "ban":{
    "title":"Siz забаненi",
    "color":0xE74C3C ,
    "text":f"Siz idi **на время** udaleni с сервер **{guild.name}**.",
    "note":"Если siz scitaete bu решение osibocnim — iletiшime geчin с управление.",
    "gif":"https://media.tenor.com/x8v1oNUOmg4AAAAC/ban-hammer.gif",
    },
    "kick":{
    "title":"Siz isanahtareni",
    "color":0xE67E22 ,
    "text":f"Siz idi isanahtareni с сервер **{guild.name}**.",
    "note":"Siz edebilirsiniz vernutsya по ssilke-priglaseniyu. Soblyudayte правила.",
    "gif":"https://media.tenor.com/OtNpHMFHMhsAAAAC/kick-out.gif",
    },
    "timeout":{
    "title":"Siz susturuldui",
    "color":0xF39C12 ,
    "text":f"На на сервере **{guild.name}** vam vremenno ogranicena отправл сообщение.",
    "note":"Mute olacak удалено автоматически как по желание sroka.",
    "gif":"https://media.tenor.com/zjaHBJMFMIsAAAAC/shh-quiet.gif",
    },
    "untimeout":{
    "title":"Mute удалено",
    "color":0x2ECC71 ,
    "text":f"Sizin mute на на сервере **{guild.name}** удалено.",
    "note":"Siz tekrar edebilirsiniz denhaklarыnlyat сообщения. Soblyudayte правила.",
    "gif":None ,
    },
    "warn":{
    "title":"Предупреждение",
    "color":0xFF6B6B ,
    "text":f"На на сервере **{guild.name}** siz aldыnыz предупреждение для нарушение правила.",
    "note":"Iken nakoplenii предупреждение mogut olmak primeneni bolee strogie наказания.",
    "gif":"https://media.tenor.com/xTMoHBqFkFkAAAAC/warning-caution.gif",
    },
    "unban":{
    "title":"Ban удалено",
    "color":0x2ECC71 ,
    "text":f"Sizin ban на на сервере **{guild.name}** удалено.",
    "note":"Siz edebilirsiniz vernutsya на сервер. Cenite etot sans.",
    "gif":None ,
    },
    }
    cfg =configs .get (action ,configs ["warn"])

    e =discord .Embed (color =cfg ["color"],timestamp =datetime .now (timezone .utc ))

    desc =f"## {cfg['title']}\n"
    desc +=f"### {cfg['text']}\n"
    desc +=f"\n\n"
    desc +=f"**Сервер:** {guild.name}\n"
    desc +=f"**Модератор:** {moderator.display_name}\n"
    desc +=f"**Причина:** {reason or 'Не belirtildi'}\n"

    if extra_fields :
        desc +="\n"
        for name ,value ,inline in extra_fields :
            desc +=f"**{name}:** {value}\n"

    desc +=f"\n\n"
    desc +=f"> {cfg['note']}"

    e .description =desc 
    e .set_thumbnail (url =guild .icon .url if guild .icon else None )

    # GIF для действие
    if cfg .get ("gif"):
        e .set_image (url =cfg ["gif"])

        # Footer с simge с сервер
    if guild .icon :
        e .set_footer (text =f"{guild.name} · Moderasyon",icon_url =guild .icon .url )
    else :
        e .set_footer (text =f"{guild.name} · Moderasyon")

    return e 


    #  Mod Log Embed (отправл в mod-log канал) 

def mod_log_embed (action ,title ,color ,user ,moderator ,guild ,reason =None ,case_id =None ,extra_fields =None ):
    """Embed для mod-log канал — minimalizm stil"""
    e =discord .Embed (color =color ,timestamp =datetime .now (timezone .utc ))
    desc =(
    f"## {title}\n"
    f"**{user.display_name}** · `{user.id}`\n\n"
    f"Модератор: {moderator.mention}\n"
    f"Причина: {reason or 'Не belirtildi'}\n"
    )
    if case_id :
        desc +=f"Delo: **#{case_id}**\n"
    if extra_fields :
        for name ,value ,inline in extra_fields :
            desc +=f"{name}: {value}\n"
    desc +=f"\n{DIVIDER}"
    e .description =desc 
    e .set_thumbnail (url =user .display_avatar .url )
    e .set_footer (text =f"{guild.name}")
    return e 


    #  Общий Embed'i 

def success_embed (title ,description ,guild =None ,gif_key =None ,fields =None ):
    """Успешно действие"""
    e =discord .Embed (color =0x2ECC71 ,timestamp =datetime .now (timezone .utc ))
    desc =f"## {title}\n{description}"
    if fields :
        desc +="\n"
        for name ,value ,inline in fields :
            desc +=f"\n**{name}**: {value}"
    desc +=f"\n\n{DIVIDER}"
    e .description =desc 
    if gif_key :
        e .set_image (url =gif (gif_key ))
    if guild :
        e .set_footer (text =f"{guild.name}")
    return e 


def error_embed (description ,title ="Ошибка"):
    """Ошибка"""
    e =discord .Embed (color =0xE74C3C ,timestamp =datetime .now (timezone .utc ))
    e .description =f"## {title}\n{description}"
    return e 


def info_embed (title ,description ,guild =None ):
    """Информация"""
    e =discord .Embed (color =0x3498DB ,timestamp =datetime .now (timezone .utc ))
    e .description =f"## {title}\n{description}"
    if guild :
        e .set_footer (text =f"{guild.name}")
    return e 


def warning_embed (title ,description ):
    """Предупреждение"""
    e =discord .Embed (color =0xF39C12 ,timestamp =datetime .now (timezone .utc ))
    e .description =f"## {title}\n{description}"
    return e 


async def setup (bot ):
    pass 

