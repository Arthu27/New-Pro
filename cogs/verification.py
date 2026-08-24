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

from logger import get_logger

_log = get_logger("verification")

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
        except Exception as _ex:
            _log.debug("on_member_join(): подавлено: %s", _ex)
            # Примечание: никаких автоматических действий (кик, выдача ролей, создание каналов) не выполняется.


async def setup (bot ):
    # Серверы для slash-команд — из .env (MAIN_GUILD_ID + EXTRA_GUILD_IDS)
    from config import Config
    await bot .add_cog (
    Verification (bot ),
    guilds =Config .guild_objects (),
    )
