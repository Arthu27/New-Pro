import discord 
from discord .ext import commands 
from discord import app_commands 
from datetime import datetime ,timedelta ,timezone 
import json 
import os 
from cogs .embed_utils import gif ,now_ts ,mod_dm_embed ,mod_log_embed ,success_embed ,error_embed 

from logger import get_logger 
log =get_logger ("moderation")


DIVIDER =""


class Moderation (commands .Cog ):
    def __init__ (self ,bot ):
        self .bot =bot 

    def save_case (self ,guild_id ,action ,user_id ,mod_id ,reason ):
        os .makedirs ('data',exist_ok =True )
        filepath ='data/mod_data.json'
        try :
            data ={'cases':{}}
            if os .path .exists (filepath ):
                with open (filepath ,'r',encoding ='utf-8')as f :
                    loaded =json .load (f )
                # Устойчивость: файл могли записать другие коги с другой схемой
                # (например, {'case': ..., 'notes': ...}). Не теряем их записи,
                # а лишь гарантируем ключ 'cases'.
                if isinstance (loaded ,dict ):
                    data =loaded
                data .setdefault ('cases',{})
            gid =str (guild_id )
            if gid not in data ['cases']:
                data ['cases'][gid ]=[]
            case_id =len (data ['cases'][gid ])+1 
            data ['cases'][gid ].append ({
            'id':case_id ,'action':action ,
            'user_id':str (user_id ),'mod_id':str (mod_id ),
            'reason':reason or 'Не belirtildi',
            'timestamp':datetime .now (timezone .utc ).isoformat ()
            })
            with open (filepath ,'w',encoding ='utf-8')as f :
                json .dump (data ,f ,indent =2 ,ensure_ascii =False )
            return case_id 
        except Exception as e :
            log .info (f"[MOD] Ошибка sohraneniya iшler: {e}")
            return 0 

    async def send_log (self ,guild ,embed ):
        ch =discord .utils .get (guild .text_channels ,name ="mod-log")
        if not ch :
            ch =discord .utils .get (guild .text_channels ,name ="moderasyon")
        if ch :
            await ch .send (embed =embed )

    async def _notify_owner (self ,action ,user ,mod ,reason =None ):
        owner_id =int (os .getenv ('OWNER_ID','0'))
        if not owner_id or not mod or mod .id ==owner_id :
            return 
        flag_file ='data/mod_notify.json'
        try :
            enabled =json .load (open (flag_file ,encoding ='utf-8')).get ('enabled',False )if os .path .exists (flag_file )else False 
        except Exception :
            enabled =False 
        if not enabled :
            return 
        try :
            owner =await self .bot .fetch_user (owner_id )
            name =user .display_name if hasattr (user ,'display_name')else str (user )
            msg =f"**{action.upper()}** — {name} | Mod: {mod.display_name}"
            if reason :
                msg +=f" | Причина: {reason}"
            await owner .send (msg )
        except Exception :
            pass 

    async def send_dm (self ,user ,embed ):
        try :
            await user .send (embed =embed )
        except discord .Forbidden :
            pass 

    def _confirm_embed (self ,action ,user ,guild ,reason ,case_id ,extra ="" ,moderator =None ):
        """Embed onay для модератора — professionalniy stil"""
        moderator =moderator or (guild .me if guild else None )
        configs ={
        "ban":("Ban завершено",0xE74C3C ,"забанен на время"),
        "kick":("Kick завершено",0xE67E22 ,"isanahtaren с сервер"),
        "timeout":("Mute завершено",0xF39C12 ,"vremenno замьючен"),
        "untimeout":("Mute удалено",0x2ECC71 ,"mute удалено"),
        "unban":("Ban удалено",0x2ECC71 ,"razbanen"),
        }
        title ,color ,action_text =configs .get (action ,("Действие заверш",0x2ECC71 ,"primeneno"))

        e =discord .Embed (color =color ,timestamp =datetime .now (timezone .utc ))

        desc =f"## {title}\n"
        desc +=f"### **{user.display_name}** — {action_text}\n"
        desc +=f"`{user.id}`\n"
        desc +=f"\n\n"
        desc +=f"**Delo:** #{case_id}\n"
        desc +=f"**Причина:** {reason or 'Не belirtildi'}\n"
        desc +=f"**Модератор:** {moderator.mention if moderator else chr(8212)}\n"

        if extra :
            desc +=f"\n{extra}\n"

        desc +=f"\n\n"
        desc +=f"> DM пользователю denhaklarыnlen"

        e .description =desc 
        e .set_thumbnail (url =user .display_avatar .url )

        # Footer с simge с сервер
        if guild .icon :
            e .set_footer (text =f"{guild.name} · Модерация",icon_url =guild .icon .url )
        else :
            e .set_footer (text =f"{guild.name} · Модерация")

        return e 

        # /moderate 

    @app_commands .command (name ="moderate",description ="Модерация: бан, кик, мут, размут, разбан")
    @app_commands .choices (action =[
    app_commands .Choice (name ="ban",value ="ban"),
    app_commands .Choice (name ="kick",value ="kick"),
    app_commands .Choice (name ="timeout",value ="timeout"),
    app_commands .Choice (name ="untimeout",value ="untimeout"),
    app_commands .Choice (name ="unban",value ="unban")
    ])
    @app_commands .checks .has_permissions (ban_members =True )
    async def moderate_user (self ,interaction ,action :str ,
    user :discord .Member =None ,user_id :str =None ,
    minutes :int =None ,reason :str =None ):
        guild =interaction .guild 

        if action =="ban":
            if not user :
                await interaction .response .send_message (embed =error_embed ("Belirtin пользователь для ban."),ephemeral =True )
                return 
            try :
                dm =mod_dm_embed ("ban",guild ,interaction .user ,reason )
                await self .send_dm (user ,dm )
                await user .ban (reason =reason )
                case_id =self .save_case (guild .id ,'ban',user .id ,interaction .user .id ,reason )
                log =mod_log_embed ("ban","Ban",0xE74C3C ,user ,interaction .user ,guild ,reason ,case_id )
                await self .send_log (guild ,log )
                confirm =self ._confirm_embed ("ban",user ,guild ,reason ,case_id ,moderator =interaction .user )
                await interaction .response .send_message (embed =confirm ,ephemeral =True )
                await self ._notify_owner ('ban',user ,interaction .user ,reason )
            except discord .Forbidden :
                await interaction .response .send_message (embed =error_embed ("Роль пользователя выше или равна роли бота."),ephemeral =True )
            except Exception as ex :
                await interaction .response .send_message (embed =error_embed (str (ex )),ephemeral =True )

        elif action =="kick":
            if not user :
                await interaction .response .send_message (embed =error_embed ("Belirtin пользователь для kika."),ephemeral =True )
                return 
            try :
                dm =mod_dm_embed ("kick",guild ,interaction .user ,reason )
                await self .send_dm (user ,dm )
                await user .kick (reason =reason )
                case_id =self .save_case (guild .id ,'kick',user .id ,interaction .user .id ,reason )
                log =mod_log_embed ("kick","Kick",0xE67E22 ,user ,interaction .user ,guild ,reason ,case_id )
                await self .send_log (guild ,log )
                confirm =self ._confirm_embed ("kick",user ,guild ,reason ,case_id ,moderator =interaction .user )
                await interaction .response .send_message (embed =confirm ,ephemeral =True )
                await self ._notify_owner ('kick',user ,interaction .user ,reason )
            except discord .Forbidden :
                await interaction .response .send_message (embed =error_embed ("Роль пользователя выше или равна роли бота."),ephemeral =True )
            except Exception as ex :
                await interaction .response .send_message (embed =error_embed (str (ex )),ephemeral =True )

        elif action =="timeout":
            if not user :
                await interaction .response .send_message (embed =error_embed ("Belirtin пользователь для mute."),ephemeral =True )
                return 
            sure =minutes if minutes is not None else 5 
            try :
                until =discord .utils .utcnow ()+timedelta (minutes =sure )
                dm =mod_dm_embed ("timeout",guild ,interaction .user ,reason ,
                extra_fields =[("Длительность",f"**{sure} dk.**",True )])
                await self .send_dm (user ,dm )
                await user .timeout (until ,reason =reason )
                case_id =self .save_case (guild .id ,'timeout',user .id ,interaction .user .id ,reason )
                log =mod_log_embed ("timeout","Mute",0xF39C12 ,user ,interaction .user ,guild ,reason ,case_id ,
                extra_fields =[("Длительность",f"{sure} dk.",True )])
                await self .send_log (guild ,log )
                confirm =self ._confirm_embed ("timeout",user ,guild ,reason ,case_id ,
                extra =f"Длительность: **{sure} dk.** · Snimetsya: <t:{int(until.timestamp())}:R>",
                moderator =interaction .user )
                await interaction .response .send_message (embed =confirm ,ephemeral =True )
                await self ._notify_owner ('timeout',user ,interaction .user ,reason )
            except discord .Forbidden :
                await interaction .response .send_message (embed =error_embed ("У вас нет прав для выполнения этого действия."),ephemeral =True )
            except Exception as ex :
                await interaction .response .send_message (embed =error_embed (str (ex )),ephemeral =True )

        elif action =="untimeout":
            if not user :
                await interaction .response .send_message (embed =error_embed ("Belirtin пользователь."),ephemeral =True )
                return 
            try :
                await user .timeout (None )
                dm =mod_dm_embed ("untimeout",guild ,interaction .user )
                await self .send_dm (user ,dm )
                log =mod_log_embed ("untimeout","Mute удалено",0x2ECC71 ,user ,interaction .user ,guild )
                await self .send_log (guild ,log )
                confirm =self ._confirm_embed ("untimeout",user ,guild ,reason ,0 ,moderator =interaction .user )
                await interaction .response .send_message (embed =confirm ,ephemeral =True )
            except Exception as ex :
                await interaction .response .send_message (embed =error_embed (str (ex )),ephemeral =True )

        elif action =="unban":
            if not user_id :
                await interaction .response .send_message (embed =error_embed ("Belirtin ID пользователь в pole `user_id`."),ephemeral =True )
                return 
            try :
                fetched =await self .bot .fetch_user (int (user_id ))
                await guild .unban (fetched )
                case_id =self .save_case (guild .id ,'unban',fetched .id ,interaction .user .id ,reason )
                e =discord .Embed (color =0x2ECC71 ,timestamp =datetime .now (timezone .utc ))
                e .description =(
                f"## Ban удалено\n"
                f"**{fetched.name}** · `{fetched.id}`\n\n"
                f"Пользователь razbanen.\n"
                f"Модератор: {interaction.user.mention}\n\n"
                f"{DIVIDER}"
                )
                e .set_footer (text =f"{guild.name}")
                await self .send_log (guild ,e )
                await interaction .response .send_message (embed =e ,ephemeral =True )
            except Exception as ex :
                await interaction .response .send_message (embed =error_embed (str (ex )),ephemeral =True )

    @moderate_user .error 
    async def moderate_user_error (self ,interaction ,error ):
        if isinstance (error ,app_commands .MissingPermissions ):
            await interaction .response .send_message (
            embed =error_embed ("Yetersiz haklarыn. Trebuetsya: **Ban участников**."),
            ephemeral =True 
            )
        else :
            await interaction .response .send_message (embed =error_embed (str (error )),ephemeral =True )

            # /utility 

    @app_commands .command (name ="utility",description ="Utiliti: ocistka, sloumod, blokirovka, info")
    @app_commands .choices (action =[
    app_commands .Choice (name ="clear",value ="clear"),
    app_commands .Choice (name ="slowmode",value ="slowmode"),
    app_commands .Choice (name ="lock",value ="lock"),
    app_commands .Choice (name ="unlock",value ="unlock"),
    app_commands .Choice (name ="userinfo",value ="userinfo"),
    app_commands .Choice (name ="сервер",value ="сервер")
    ])
    @app_commands .checks .has_permissions (manage_messages =True )
    async def utility_commands (self ,interaction ,action :str ,
    adet :int =10 ,секунд :int =0 ,user :discord .Member =None ):
        guild =interaction .guild 

        if action =="clear":
            await interaction .response .defer (ephemeral =True )
            deleted =await interaction .channel .purge (limit =adet )
            e =discord .Embed (color =0xDC143C ,timestamp =datetime .now (timezone .utc ))
            e .description =(
            f"## Сообщения udaleni\n"
            f"Удалено **{len(deleted)}** сообщение\n\n"
            f"Канал: {interaction.channel.mention}\n"
            f"Модератор: {interaction.user.mention}\n\n"
            f"{DIVIDER}"
            )
            e .set_footer (text =f"{guild.name}")
            await interaction .followup .send (embed =e ,ephemeral =True )

        elif action =="slowmode":
            if секунд <0 or секунд >21600 :
                await interaction .response .send_message (embed =error_embed ("Znacenie den 0 do 21600 секунд."),ephemeral =True )
                return 
            await interaction .channel .edit (slowmode_delay =секунд )
            e =discord .Embed (color =0xF39C12 ,timestamp =datetime .now (timezone .utc ))
            e .description =(
            f"## Medlenniy mod\n"
            f"Канал: {interaction.channel.mention}\n"
            f"Zaderjka: **{секунд} sek.**\n"
            f"Модератор: {interaction.user.mention}\n\n"
            f"{DIVIDER}"
            )
            e .set_footer (text =f"{guild.name}")
            await interaction .response .send_message (embed =e ,ephemeral =True )

        elif action =="lock":
            await interaction .channel .set_permissions (guild .default_role ,send_messages =False )
            e =discord .Embed (color =0xE74C3C ,timestamp =datetime .now (timezone .utc ))
            e .description =(
            f"## Канал zablokirovan\n"
            f"{interaction.channel.mention}\n\n"
            f"Отправл сообщение baгlandы.\n"
            f"Zablokiroval: {interaction.user.mention}\n\n"
            f"{DIVIDER}"
            )
            e .set_footer (text =f"{guild.name}")
            await interaction .channel .send (embed =e )
            await interaction .response .send_message ("Канал zablokirovan.",ephemeral =True )

        elif action =="unlock":
            await interaction .channel .set_permissions (guild .default_role ,send_messages =True )
            e =discord .Embed (color =0x2ECC71 ,timestamp =datetime .now (timezone .utc ))
            e .description =(
            f"## Канал razblokirovan\n"
            f"{interaction.channel.mention}\n\n"
            f"Отправл сообщение в.\n"
            f"Razblokiroval: {interaction.user.mention}\n\n"
            f"{DIVIDER}"
            )
            e .set_footer (text =f"{guild.name}")
            await interaction .channel .send (embed =e )
            await interaction .response .send_message ("Канал razblokirovan.",ephemeral =True )

        elif action =="userinfo":
            u =user or interaction .user 
            roles =[r .mention for r in u .roles [1 :]]
            roles_text =" ".join (roles [:20 ])if roles else "Нет"
            if len (roles )>20 :
                roles_text +=f" · +{len(roles) - 20}"

            e =discord .Embed (
            color =u .color if u .color !=discord .Color .default ()else 0x3498DB ,
            timestamp =datetime .now (timezone .utc )
            )
            e .description =(
            f"## {u.display_name}\n"
            f"`{u.id}`\n\n"
            f"Isim: **{u.name}**\n"
            f"Псевдоним: **{u.display_name}**\n"
            f"Hesap: <t:{int(u.created_at.timestamp())}:R>\n"
            f"На на сервере: <t:{int(u.joined_at.timestamp())}:R>\n"
            f"Роли ({len(roles)}): {roles_text}\n\n"
            f"{DIVIDER}"
            )
            e .set_thumbnail (url =u .display_avatar .url )
            e .set_footer (text =f"{guild.name}")
            await interaction .response .send_message (embed =e )

        elif action =="сервер":
            g =guild 
            bots =sum (1 for m in g .members if m .bot )
            humans =g .member_count -bots 

            e =discord .Embed (color =0x3498DB ,timestamp =datetime .now (timezone .utc ))
            e .description =(
            f"## {g.name}\n"
            f"`{g.id}`\n\n"
            f"Sahip: {g.owner.mention}\n"
            f"Создало: <t:{int(g.created_at.timestamp())}:R>\n\n"
            f"Участников: **{g.member_count}**\n"
            f"Lyudey: **{humans}** · Botlarыn: **{bots}**\n\n"
            f"Metin каналы: **{len(g.text_channels)}**\n"
            f"Голос каналы: **{len(g.voice_channels)}**\n"
            f"Роль: **{len(g.roles)}**\n"
            f"Bust: Уровень {g.premium_tier} · {g.premium_subscription_count} bustov\n\n"
            f"{DIVIDER}"
            )
            if g .icon :
                e .set_thumbnail (url =g .icon .url )
            if g .banner :
                e .set_image (url =g .banner .url )
            e .set_footer (text =f"{g.name}")
            await interaction .response .send_message (embed =e )

            # /роли 

    @app_commands .command (name ="role",description ="Выдать или забрать роль у пользователя")
    @app_commands .checks .has_permissions (manage_roles =True )
    async def role (self ,interaction ,user :discord .Member ,role :discord .Role ):
        guild =interaction .guild 
        if role in user .roles :
            await user .remove_roles (role )
            action_text ="удален"
            color =0xE74C3C 
        else :
            await user .add_roles (role )
            action_text ="vidana"
            color =0x2ECC71 

        e =discord .Embed (color =color ,timestamp =datetime .now (timezone .utc ))
        e .description =(
        f"## Роль {action_text}\n"
        f"**{user.display_name}** · `{user.id}`\n\n"
        f"Роль: {role.mention}\n"
        f"Модератор: {interaction.user.mention}\n\n"
        f"{DIVIDER}"
        )
        e .set_footer (text =f"{guild.name}")
        await interaction .response .send_message (embed =e ,ephemeral =True )

        # /leaveguild 

    @app_commands .command (name ="leaveguild",description ="Покинуть сервер (только владелец бота)")
    async def leave_guild (self ,interaction ,guild_id :str ):
        app_info =await self .bot .application_info ()
        if interaction .user .id !=app_info .owner .id :
            await interaction .response .send_message (
            embed =error_embed ("Eta команда eriшimюzerinde только vladelcu botun."),
            ephemeral =True 
            )
            return 
        try :
            target =self .bot .get_guild (int (guild_id ))
            if not target :
                await interaction .response .send_message (embed =error_embed ("Сервер не найдено."),ephemeral =True )
                return 
            name =target .name 
            await target .leave ()
            e =discord .Embed (color =0x2ECC71 ,timestamp =datetime .now (timezone .utc ))
            e .description =f"## Сервер pokinut\n**{name}** · `{guild_id}`"
            await interaction .response .send_message (embed =e ,ephemeral =True )
        except ValueError :
            await interaction .response .send_message (embed =error_embed ("Неверный ID сервер."),ephemeral =True )
        except Exception as ex :
            await interaction .response .send_message (embed =error_embed (str (ex )),ephemeral =True )


async def setup (bot ):
    await bot .add_cog (Moderation (bot ))
