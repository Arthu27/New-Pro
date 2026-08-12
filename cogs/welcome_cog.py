"""
Welcome Cog
Ког системы приветствий
"""

import discord 
from discord .ext import commands 
from datetime import datetime 

from logger import get_logger 
log =get_logger ("welcome_cog")



class WelcomeCog (commands .Cog ):
    """Система приветствий (legacy + панель)"""

    def __init__ (self ,bot ):
        self .bot =bot 
        self .welcome_message ="👋 Добро пожаловать, {user}! Рады видеть тебя на сервере!"
        self .welcome_channel_id =None 

    @commands .command (name ='setwelcome',aliases =['настройкаприветствия'])
    @commands .has_permissions (administrator =True )
    async def setwelcome (self ,ctx ,*,message :str ):
        """Настроить текст приветствия"""
        self .welcome_message =message 

        embed =discord .Embed (
        title ="✅ Приветственное сообщение обновлено",
        description =f"**Новый текст:** {message}",
        color =discord .Color .dark_grey (),
        timestamp =datetime .now ()
        )

        await ctx .send (embed =embed )

    @commands .command (name ='setwelcomechannel',aliases =['каналприветствий'])
    @commands .has_permissions (administrator =True )
    async def setwelcomechannel (self ,ctx ,channel :discord .TextChannel ):
        """Настроить канал приветствий"""
        self .welcome_channel_id =channel .id 

        embed =discord .Embed (
        title ="✅ Канал приветствий обновлён",
        description =f"**Новый канал:** {channel.mention}",
        color =discord .Color .dark_grey (),
        timestamp =datetime .now ()
        )

        await ctx .send (embed =embed )

    @commands .command (name ='testwelcome',aliases =['тестприветствия'])
    async def testwelcome (self ,ctx ):
        """Проверить текст приветствия"""
        message =self .welcome_message .replace ("{user}",ctx .author .mention )

        embed =discord .Embed (
        title ="👋 Добро пожаловать!",
        description =message ,
        color =discord .Color .dark_grey (),
        timestamp =datetime .now ()
        )

        from cogs .icons import send_with_icon 
        await send_with_icon (ctx ,embed ,'welcome')


    # ── Панель (/welcome-editor): data/welcome_{gid}.json ──
    def _panel_section (self ,guild_id ,kind ):
        """kind: 'welcome' | 'leave' → dict из панели или None."""
        try :
            import json ,os
            f =f'data/welcome_{guild_id}.json'
            if not os .path .exists (f ):
                return None
            with open (f ,'r',encoding ='utf-8')as fp :
                sec =(json .load (fp )or {}).get (kind )
            if isinstance (sec ,dict )and (sec .get ('channel_id')or sec .get ('message')):
                return sec 
        except Exception as _ex:
            log.debug("_panel_section(): подавлено: %s", _ex)
        return None

    def _fmt_panel_text (self ,text ,member ):
        txt =str (text or '')
        txt =txt .replace ('{user}',member .mention ).replace ('{username}',member .display_name )
        txt =txt .replace ('{count}',str (member .guild .member_count or ''))
        txt =txt .replace ('{server}',member .guild .name ).replace ('{guild}',member .guild .name )
        return txt 

    async def _send_panel_msg (self ,member ,kind ):
        sec =self ._panel_section (member .guild .id ,kind )
        if not sec :
            return 
        try :
            ch_id =int (sec .get ('channel_id')or 0 )
        except Exception :
            ch_id =0
        channel =member .guild .get_channel (ch_id )if ch_id else None
        if channel is None :
            channel =member .guild .system_channel 
        if channel is None :
            return 
        text =self ._fmt_panel_text (sec .get ('message'),member )
        if not text .strip ():
            return 
        title ="👋 Добро пожаловать!" if kind =='welcome' else "👋 До свидания"
        embed =discord .Embed (
        title =title ,
        description =text [:1900 ],
        color =0xD4AF37 ,
        timestamp =datetime .now ()
        )
        try :
            await channel .send (embed =embed )
            log .info (f"[WELCOME] панель-сообщение ({kind}) → {member}")
        except Exception as e :
            log .warning (f"[WELCOME] отправка панель-сообщения: {e}")

    @commands .Cog .listener ()
    async def on_member_join (self ,member ):
        """Вход: legacy-префикс конфиг + сообщение из панели."""
        # 1) Legacy: !setwelcome (в памяти, до рестарта)
        try :
            if self .welcome_channel_id :
                channel =member .guild .get_channel (self .welcome_channel_id )
                if channel :
                    message =self .welcome_message .replace ("{user}",member .mention )
                    embed =discord .Embed (
                    title ="👋 Добро пожаловать!",
                    description =message ,
                    color =discord .Color .dark_grey (),
                    timestamp =datetime .now ()
                    )
                    from cogs .icons import send_with_icon
                    await send_with_icon (channel ,embed ,'welcome')
        except Exception as e :
            log .warning (f"[WELCOME] legacy: {e}")
        # 2) Панель (/welcome-editor)
        await self ._send_panel_msg (member ,'welcome')

    @commands .Cog .listener ()
    async def on_member_remove (self ,member ):
        """Участник вышел — прощание из панели."""
        await self ._send_panel_msg (member ,'leave')

    @commands .Cog .listener ()
    async def on_ready (self ):
        """Бот готов"""
        log .info ("WelcomeCog loaded")


async def setup (bot ):
    await bot .add_cog (WelcomeCog (bot ))
