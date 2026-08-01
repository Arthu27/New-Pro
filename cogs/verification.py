"""
Aether — Doгrulama (Данныеfication) — Gёzlemci / opt-in modu
---------------------------------------------------------
Varsayыlan: KAPALI. Новый gelen kullanыcыlara otomatik hiчbir шey YAPILMAZ:
  * Captcha kodu gёsterilmez
  * "Проверка" / "Подтвердитьndы" роль VERILMEZ
  * Zaman aшыmыnda KICK YAPILMAZ
  * сервер sahibi panelden aчmadыkчa система sessiz kalыr

Aчmak iчin: `/verify-toggle enabled:true` ya da panelden.
"""

import discord 
from discord .ext import commands 
from discord import app_commands 
import json 
import os 


VERIFY_CONFIG_FILE ="data/verification_config.json"


def _load_global_state ()->dict :
    """Global olarak verification системаi aчыk mы kapalы mы?"""
    if not os .path .exists (VERIFY_CONFIG_FILE ):
        return {"enabled":False ,"kick_timeout_minutes":0 }# 0 = kick нет
    try :
        with open (VERIFY_CONFIG_FILE ,"r",encoding ="utf-8")as f :
            data =json .load (f )
        if not isinstance (data ,dict ):
            return {"enabled":False ,"kick_timeout_minutes":0 }
        return data 
    except Exception :
        return {"enabled":False ,"kick_timeout_minutes":0 }


def _save_global_state (state :dict ):
    os .makedirs ("data",exist_ok =True )
    with open (VERIFY_CONFIG_FILE ,"w",encoding ="utf-8")as f :
        json .dump (state ,f ,indent =2 ,ensure_ascii =False )


class Verification (commands .Cog ):
    """Иsteгe baгlы captcha/Роль системаi. Varsayыlan KAPALI."""

    def __init__ (self ,bot ):
        self .bot =bot 

    @commands .Cog .listener ()
    async def on_member_join (self ,member :discord .Member ):
        state =_load_global_state ()
        # KAPALI ise hiчbir шey yapma
        if not state .get ("enabled",False ):
            return 
        if member .bot :
            return 

        guild =member .guild 
        unverified_role =discord .utils .get (guild .roles ,name ="Проверка")
        verified_role =discord .utils .get (guild .roles ,name ="Подтвердитьndы")

        # Sadece bilgilendirme — otomatik Роль/kick YOK
        try :
            await member .send (
            f" {guild.name} серверsuna hoш geldin!\n"
            f"Если требуется проверка, следуйте инструкциям на сервере."
            )
        except Exception :
            pass 
            # Not: kick/Роль-atama/Канал-oluшturma gibi hiчbir otomatik aksiyon YOK.

    @app_commands .command (name ="verify-toggle",description ="Включить/отключить систему верификации (режим наблюдателя)")
    @app_commands .checks .has_permissions (administrator =True )
    async def verify_toggle (self ,interaction :discord .Interaction ,enabled :bool ):
        state =_load_global_state ()
        state ["enabled"]=enabled 
        state ["updated_by"]=str (interaction .user )
        _save_global_state (state )
        await interaction .response .send_message (
        f" Данныеfication системаi **{'AЧIK' if enabled else 'KAPALI'}**.\n"
        +(" Bot otomatik captcha/Роль/kick YAPMAYACAK — sadece bilgilendirme."if enabled else " Artыk новый gelenler iчin hiчbir otomatik операция yapыlmayacak."),
        ephemeral =True ,
        )

    @app_commands .command (name ="verify-status",description ="Данныеfication системаinin anlыk статусunu gёsterir")
    async def verify_status (self ,interaction :discord .Interaction ):
        state =_load_global_state ()
        e =discord .Embed (
        title =" Данныеfication — Статус",
        color =0x2ECC71 if state .get ("enabled")else 0x95A5A6 ,
        )
        e .add_field (name ="Система",value =" Aчыk"if state .get ("enabled")else " Kapalы",inline =True )
        e .add_field (name ="Otomatik aksiyon",value =" YOK (gёzlemci modu)",inline =True )
        e .add_field (name ="Son gюncelleme",value =state .get ("updated_by","—"),inline =True )
        e .description =(
        "Bu cog gёzlemci modunda: bot kimseye otomatik captcha/Роль/kick UYGULAMAZ. "
        "Sadece sen `/verify-toggle enabled:true` dersen bilgilendirme DM'i atar."
        )
        await interaction .response .send_message (embed =e ,ephemeral =True )


async def setup (bot ):
    await bot .add_cog (
    Verification (bot ),
    guilds =[
    discord .Object (id =1421244140359909513 ),
    discord .Object (id =1498837105915330562 ),
    discord .Object (id =1107038411895881788 ),
    ],
    )
