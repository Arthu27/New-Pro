"""AFK-система — /afk с причиной, уведомляет при упоминании"""
import discord 
from discord .ext import commands 
from discord import app_commands 
from datetime import datetime ,timezone 
import os 
from config import Config 

OWNER_ID =int (os .getenv ('OWNER_ID')or '0')

AFK_ICON ='assets/afk_icon.png'

def _afk_file ():
    """AFK simgesi — embed thumbnail'ı için dosya."""
    if os .path .exists (AFK_ICON ):
        return discord .File (AFK_ICON ,filename ='afk_icon.png')
    return None

# Хранение упоминаний, пришедших во время AFK — {user_id: [{from, msg, channel, guild, time}]}
_pending_mentions :dict ={}


class AFK (commands .Cog ):
    def __init__ (self ,bot ):
        self .bot =bot 
        # {guild_id: {user_id: {"reason": str, "since": datetime, "owner_mode": bool}}}
        self ._afk :dict ={}

    def _set (self ,guild_id ,user_id ,reason ,owner_mode =False ):
        self ._afk .setdefault (str (guild_id ),{})[str (user_id )]={
        "reason":reason ,
        "since":datetime .now (timezone .utc ).isoformat (),
        "owner_mode":owner_mode 
        }

    def _get (self ,guild_id ,user_id ):
        return self ._afk .get (str (guild_id ),{}).get (str (user_id ))

    def _remove (self ,guild_id ,user_id ):
        self ._afk .get (str (guild_id ),{}).pop (str (user_id ),None )

    def _is_afk_anywhere (self ,user_id ):
        """Есть ли пользователь в AFK на каком-либо сервере?"""
        for guild_data in self ._afk .values ():
            if str (user_id )in guild_data :
                return guild_data [str (user_id )]
        return None 

    @app_commands .command (name ="afk",description ="Войти в режим AFK")
    async def afk (self ,interaction :discord .Interaction ,причина :str ="AFK"):
        self ._set (interaction .guild_id ,interaction .user .id ,причина )

        ts =int (datetime .now (timezone .utc ).timestamp ())
        e =discord .Embed (color =0x5865F2 ,timestamp =datetime .now (timezone .utc ))
        # Сначала 💤 в ник — если прав нет, предупредить в карточке
        nick_note =''
        try :
            nick =interaction .user .display_name 
            if not nick .startswith ("💤"):
                await interaction .user .edit (nick =f"💤 {nick[:28]}")
        except discord .Forbidden :
            nick_note ='\n-# ⚠️ Не смог добавить 💤 к нику — нет прав (владельцу сервера ник менять нельзя)'
        except Exception :
            nick_note ='\n-# ⚠️ Не смог добавить 💤 к нику'

        e .set_author (
        name =f"💤 {interaction.user.display_name} перешёл в AFK",
        icon_url =interaction .user .display_avatar .url 
        )
        e .description =(
        f"```\n  РЕЖИМ AFK АКТИВЕН\n```\n"
        f"> **Причина:** {причина}\n"
        f"> **Начало:** <t:{ts}:R>\n\n"
        f"*Когда кто-то упомянет тебя — придёт уведомление.*"
        f"{nick_note}"
        )
        icon =_afk_file ()
        if icon :
            e .set_thumbnail (url ='attachment://afk_icon.png')
        else :
            e .set_thumbnail (url =interaction .user .display_avatar .url )
        e .set_footer (text ="💤 Выход из AFK: /afk-remove")
        if icon :
            await interaction .response .send_message (embed =e ,file =icon )
        else :
            await interaction .response .send_message (embed =e )

    @app_commands .command (name ="afk-remove",description ="Выйти из режима AFK")
    async def afk_remove (self ,interaction :discord .Interaction ):
        data =self ._get (interaction .guild_id ,interaction .user .id )
        if not data :
            await interaction .response .send_message ("Вы не в режиме AFK.",ephemeral =True )
            return 
        self ._remove (interaction .guild_id ,interaction .user .id )
        # Убрать 💤 из ника
        try :
            nick =interaction .user .display_name 
            if nick .startswith ("💤"):
                await interaction .user .edit (nick =nick [2 :].strip ()or None )
        except Exception :
            pass 
        # Показать накопившиеся упоминания
        uid =interaction .user .id 
        pending =_pending_mentions .pop (uid ,[])
        if pending :
            lines =[]
            for p in pending [-10 :]:
                lines .append (f"• **{p['from']}** — {p['guild']} #{p['channel']}\n  > {p['msg'][:100]}")
            embed =discord .Embed (
            title =f'👋 С возвращением! Тебя ждут {len(pending)} упоминаний',
            description ='\n\n'.join (lines ),
            color =0x57F287 
            )
            await interaction .response .send_message (embed =embed )
        else :
            await interaction .response .send_message ('✅ Режим AFK отключён! Никто тебя не упоминал.')

    @commands .Cog .listener ()
    async def on_message (self ,message :discord .Message ):
        if message .author .bot or not message .guild :
            return 

        gid =message .guild .id 
        uid =message .author .id 

        # Автор сообщения в AFK — ТОЛЬКО если owner_mode=False, автоматически выйти
        afk_data =self ._get (gid ,uid )
        if afk_data and not afk_data .get ('owner_mode'):
            self ._remove (gid ,uid )
            since =datetime .fromisoformat (afk_data ["since"])
            elapsed =datetime .now (timezone .utc )-since 
            mins =int (elapsed .total_seconds ()//60 )
            dur =f"{mins} мин."if mins >0 else "только что"
            e =discord .Embed (color =0x2ED573 ,timestamp =datetime .now (timezone .utc ))
            e .set_author (
            name =f"👋 {message.author.display_name} вернулся из AFK",
            icon_url =message .author .display_avatar .url 
            )
            e .description =f"> **Длительность:** **{dur}**\n> Причина: *{afk_data['reason']}*"
            await message .channel .send (embed =e ,delete_after =8 )
            # Убрать 💤 из ника
            try :
                nick =message .author .display_name 
                if nick .startswith ("💤"):
                    await message .author .edit (nick =nick [2 :].strip ()or None )
            except Exception :
                pass 
            return 

        # Упомянутый пользователь в AFK?
        for mentioned in message .mentions :
            if mentioned .bot or mentioned .id ==message .author .id :
                continue 
            data =self ._get (gid ,mentioned .id )
            if not data :
                continue 

            since =datetime .fromisoformat (data ["since"])
            elapsed =datetime .now (timezone .utc )-since 
            mins =int (elapsed .total_seconds ()//60 )
            dur =f"{mins} мин."if mins >0 else "только что"

            # Owner mode — бот спросит, что передать
            if data .get ('owner_mode')and OWNER_ID and mentioned .id ==OWNER_ID :
                e =discord .Embed (color =0x5865F2 ,timestamp =datetime .now (timezone .utc ))
                e .set_author (
                name =f"😴 {mentioned.display_name} сейчас спит",
                icon_url =mentioned .display_avatar .url 
                )
                e .description =(
                f"> **Причина:** {data['reason']}\n"
                f"> **Длительность:** {dur}\n\n"
                f"Могу передать это Arthur'у. **Что хотите спросить?**\n"
                f"-# Напишите ответ — передам, когда проснётся."
                )
                e .set_footer (text ="Сообщение будет передано Arthur'у")
                icon =_afk_file ()
                if icon :
                    e .set_thumbnail (url ='attachment://afk_icon.png')
                    sent =await message .channel .send (embed =e ,file =icon )
                else :
                    sent =await message .channel .send (embed =e )

                # Сохранить упоминание
                if OWNER_ID not in _pending_mentions :
                    _pending_mentions [OWNER_ID ]=[]
                _pending_mentions [OWNER_ID ].append ({
                'from':message .author .display_name ,
                'from_id':message .author .id ,
                'msg':message .content ,
                'channel':message .channel .name ,
                'guild':message .guild .name ,
                'time':datetime .now (timezone .utc ).isoformat (),
                'channel_id':message .channel .id ,
                })

                # Поймать следующее сообщение — что хотят спросить
                def check (m ):
                    return m .channel ==message .channel and not m .author .bot and m .author .id !=OWNER_ID 

                try :
                    follow =await self .bot .wait_for ('message',check =check ,timeout =120 )
                    # Отправить сообщение owner'у в ЛС
                    owner =await self .bot .fetch_user (OWNER_ID )
                    dm_embed =discord .Embed (
                    color =0xf59e0b ,
                    description =(
                    f'**{message.author.display_name}** упомянул тебя и спросил:\n\n'
                    f'> {follow.content[:500]}\n\n'
                    f'📍 {message.guild.name} — #{message.channel.name}'
                    )
                    )
                    dm_embed .set_author (
                    name ='Тебя упомянули, пока ты спал 💤',
                    icon_url =message .author .display_avatar .url 
                    )
                    await owner .send (embed =dm_embed )
                    # Сообщить в канал
                    await message .channel .send (
                    f'📨 Сообщение передано Arthur\'у! Ответит, когда проснётся.',
                    delete_after =10 
                    )
                    # Добавить в ожидающие
                    _pending_mentions [OWNER_ID ][-1 ]['follow_msg']=follow .content 
                except Exception :
                    pass 

            else :
                # Обычное AFK-уведомление
                e =discord .Embed (color =0x5865F2 ,timestamp =datetime .now (timezone .utc ))
                e .set_author (
                name =f"💤 {mentioned.display_name} сейчас в AFK",
                icon_url =mentioned .display_avatar .url 
                )
                e .description =(
                f"> **Причина:** {data['reason']}\n"
                f"> **Длительность:** {dur}"
                )
                e .set_footer (text ="В режиме AFK — сообщение не увидит")
                icon =_afk_file ()
                if icon :
                    e .set_thumbnail (url ='attachment://afk_icon.png')
                    await message .channel .send (embed =e ,file =icon ,delete_after =10 )
                else :
                    await message .channel .send (embed =e ,delete_after =10 )

                # Отправить owner'у в ЛС
                if OWNER_ID and mentioned .id ==OWNER_ID :
                    try :
                        owner =await self .bot .fetch_user (OWNER_ID )
                        dm_embed =discord .Embed (
                        color =0xf59e0b ,
                        description =(
                        f'**{message.author.display_name}** упомянул тебя:\n\n'
                        f'> {message.content[:500]}\n\n'
                        f'📍 {message.guild.name} — #{message.channel.name}'
                        )
                        )
                        dm_embed .set_author (
                        name ='Тебя упомянули (ты в режиме AFK) 💬',
                        icon_url =message .author .display_avatar .url 
                        )
                        await owner .send (embed =dm_embed )
                    except Exception :
                        pass 


async def setup (bot ):
    await bot .add_cog (AFK (bot ),guilds =Config .guild_objects ())
