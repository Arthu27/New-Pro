"""
Aether — Верификация — режим наблюдателя / opt-in
---------------------------------------------------------
По умолчанию: ВЫКЛЮЧЕНО. Для новых пользователей автоматически ничего не делается:
  * Captcha-код не показывается
  * Роль "Проверка" / "Подтверждён" не выдаётся
  * Кик по тайм-ауту не производится
  * Пока владелец сервера не включит в панели — система молчит

Включить: `/verify-toggle enabled:true` или через панель.
"""

import discord 
from discord .ext import commands 
from discord import app_commands 
import json 
import os 


VERIFY_CONFIG_FILE ="data/verification_config.json"


def _load_global_state ()->dict :
    """Включена ли система верификации глобально?"""
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
    """Опциональная система captcha/ролей. По умолчанию ВЫКЛ."""

    def __init__ (self ,bot ):
        self .bot =bot 

    @commands .Cog .listener ()
    async def on_member_join (self ,member :discord .Member ):
        state =_load_global_state ()
        # если ВЫКЛЮЧЕНО — ничего не делаем
        if not state .get ("enabled",False ):
            return 
        if member .bot :
            return 

        guild =member .guild 

        # Только информирование — автоматических ролей/киков нет
        try :
            await member .send (
            f"👋 Добро пожаловать на сервер {guild.name}!\n"
            "Если требуется проверка, следуйте инструкциям на сервере."
            )
        except Exception :
            pass 
            # Примечание: никаких автоматических действий (кик, выдача ролей, создание каналов) не выполняется.

    @app_commands .command (name ="verify-toggle",description ="Включить/отключить систему верификации (режим наблюдателя)")
    @app_commands .checks .has_permissions (administrator =True )
    async def verify_toggle (self ,interaction :discord .Interaction ,enabled :bool ):
        state =_load_global_state ()
        state ["enabled"]=enabled 
        state ["updated_by"]=str (interaction .user )
        _save_global_state (state )
        await interaction .response .send_message (
        f"🛡 Система верификации: **{'включена' if enabled else 'выключена'}**.\n"
        +("ℹ️ Бот НЕ будет автоматически выдавать капчу/роль/кик — только информирование."if enabled else "Для новых участников больше не будет никаких автоматических действий."),
        ephemeral =True ,
        )

    @app_commands .command (name ="verify-status",description ="Показать текущий статус системы верификации")
    async def verify_status (self ,interaction :discord .Interaction ):
        state =_load_global_state ()
        e =discord .Embed (
        title ="🛡 Верификация — статус",
        color =0x2ECC71 if state .get ("enabled")else 0x95A5A6 ,
        )
        e .add_field (name ="Система",value ="✅ Вкл"if state .get ("enabled")else "⛔ Выкл",inline =True )
        e .add_field (name ="Автоматические действия",value ="🚫 Нет (режим наблюдателя)",inline =True )
        e .add_field (name ="Последнее обновление",value =state .get ("updated_by","—"),inline =True )
        e .description =(
        "Этот модуль работает в режиме наблюдателя: бот НЕ применяет автоматическую капчу/роль/кик. "
        "Он лишь отправляет информационное DM, если включёно через `/verify-toggle enabled:true`."
        )
        await interaction .response .send_message (embed =e ,ephemeral =True )


async def setup (bot ):
    # Серверы для slash-команд — из .env (MAIN_GUILD_ID + EXTRA_GUILD_IDS)
    from config import Config
    await bot .add_cog (
    Verification (bot ),
    guilds =Config .guild_objects (),
    )
