import discord 
from discord .ext import commands 
from discord import app_commands 
from datetime import datetime ,timedelta ,timezone 
import json 
import os 
import time 
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

    # ═══════════════════════════════════════════════════════════════════
    #  /modpanel — панель модерации через select-меню
    # ═══════════════════════════════════════════════════════════════════
    @app_commands .command (name ="modpanel",description ="Панель модерации (выпадающее меню)")
    @app_commands .checks .has_permissions (moderate_members =True )
    async def modpanel (self ,interaction ):
        embed =discord .Embed (
        title ="🛡 Модерация",
        description =(
        "Выберите действие в выпадающем меню ниже.\n"
        "После выбора откроется окно для ввода цели и причины."
        ),
        color =0x3498DB ,
        timestamp =datetime .now (timezone .utc )
        )
        if interaction .guild .icon :
            embed .set_footer (text =f"{interaction.guild.name} · Модерация",icon_url =interaction .guild .icon .url )
        else :
            embed .set_footer (text =f"{interaction.guild.name} · Модерация")
        await interaction .response .send_message (embed =embed ,view =ModPanelView (self ))

    def _parse_target_id (self ,target :str ):
        """Из '@упоминание' или '123456789' вернуть int ID (или None)."""
        if not target :
            return None
        import re as _re
        m =_re .search (r'(\d{15,20})',target )
        if m :
            return int (m .group (1 ))
        return None

    async def _execute_mod_action (self ,interaction ,action ,target ,reason ,amount ):
        """Выполнить выбранное действие модерации."""
        guild =interaction .guild

        if action in ("ban","kick","timeout","mute_chat","untimeout","vmute","vunmute"):
            uid =self ._parse_target_id (target )
            user =discord .utils .get (guild .members ,id =uid ) if uid else None
            if not user :
                try :
                    user =await self .bot .fetch_user (uid ) if uid else None
                except Exception :
                    user =None
            if not user :
                await interaction .response .send_message (
                embed =error_embed ("Пользователь не найден. Укажите корректный ID или упоминание."),
                ephemeral =True )
                return

            try :
                if action =="ban":
                    await user .ban (reason =reason )
                    msg ="пользователь забанен"
                elif action =="kick":
                    await user .kick (reason =reason )
                    msg ="пользователь исключён"
                elif action in ("timeout","mute_chat"):
                    minutes =max (1 ,int (amount )or 5 )
                    until =discord .utils .utcnow ()+timedelta (minutes =minutes )
                    await user .timeout (until ,reason =reason )
                    if action =="mute_chat":
                        msg =f"чат закрыт на {minutes} мин (timeout)"
                    else :
                        msg =f"чат и voice закрыты на {minutes} мин (timeout)"
                    # 2 mute → 1 неделя в watchlist
                    await self._maybe_watchlist_after_mute (interaction ,user ,reason )
                elif action =="vmute":
                    if not user .voice or not user .voice .channel :
                        await interaction .response .send_message (
                        embed =error_embed ("Участник не в голосовом канале. Голосовой мьют невозможен."),
                        ephemeral =True )
                        return
                    await user .edit (mute =True )
                    msg ="микрофон заглушён (голосовой мьют)"
                elif action =="vunmute":
                    await user .edit (mute =False )
                    msg ="микрофон включён"
                else :  # untimeout
                    await user .timeout (None )
                    msg ="timeout снят (чат + voice открыты)"

                case_id =self .save_case (guild .id ,action ,user .id ,interaction .user .id ,reason )
                dm =mod_dm_embed (action ,guild ,interaction .user ,reason )
                await self .send_dm (user ,dm )
                log =mod_log_embed (action ,action .capitalize (),0x3498DB ,user ,interaction .user ,guild ,reason ,case_id )
                await self .send_log (guild ,log )

                confirm =success_embed (
                f"Действие выполнено",
                f"**{user.display_name}** · `{user.id}`\n{msg}\n**Причина:** {reason}\n**Дело:** #{case_id}",
                guild =guild )
                await interaction .response .send_message (embed =confirm ,ephemeral =True )
            except discord .Forbidden :
                await interaction .response .send_message (
                embed =error_embed ("Недостаточно прав для этого действия."),ephemeral =True )
            except Exception as ex :
                await interaction .response .send_message (embed =error_embed (str (ex )),ephemeral =True )

        elif action =="unban":
            uid =self ._parse_target_id (target )
            if not uid :
                await interaction .response .send_message (
                embed =error_embed ("Укажите ID пользователя для разбана."),ephemeral =True )
                return
            try :
                fetched =await self .bot .fetch_user (uid )
                await guild .unban (fetched )
                case_id =self .save_case (guild .id ,"unban",fetched .id ,interaction .user .id ,reason )
                confirm =success_embed (
                "Разбан",
                f"**{fetched.name}** · `{fetched.id}`\nПользователь разбанен.\n**Дело:** #{case_id}",
                guild =guild )
                await self .send_log (guild ,confirm )
                await interaction .response .send_message (embed =confirm ,ephemeral =True )
            except Exception as ex :
                await interaction .response .send_message (embed =error_embed (str (ex )),ephemeral =True )

        elif action =="clear":
            try :
                count =max (1 ,min (int (amount )or 10 ,200 ))
            except Exception :
                count =10
            deleted =await interaction .channel .purge (limit =count )
            confirm =success_embed (
            "Сообщения удалены",
            f"Удалено **{len(deleted)}** сообщений в {interaction.channel.mention}",
            guild =guild )
            await interaction .response .send_message (embed =confirm ,ephemeral =True )

    async def _maybe_watchlist_after_mute (self ,interaction ,user ,reason ):
        """Если пользователь получил 2+ мьюта — добавить в watchlist на 1 неделю.

        Считаем мьюты (timeout) из mod_data.json. При достижении 2-го мьюта
        добавляем в mod_advanced_data.json (watchlist) с меткой until (+7 дней).
        """
        try :
            import datetime as _dt
            # 1) Считаем мьюты пользователя
            os .makedirs ('data',exist_ok =True )
            mod_file ='data/mod_data.json'
            mute_count =0
            if os .path .exists (mod_file ):
                with open (mod_file ,'r',encoding ='utf-8')as f :
                    data =json .load (f )
                cases =data .get ('cases',{}).get (str (interaction .guild .id ),[])
                for c in cases :
                    if str (c .get ('user_id',''))==str (user .id )and c .get ('action')in ('timeout','mute_chat','vmute'):
                        mute_count +=1
            # 2) Добавляем в watchlist (advanced_mod) на 1 неделю
            adv_file ='data/mod_advanced_data.json'
            adv ={}
            if os .path .exists (adv_file ):
                with open (adv_file ,'r',encoding ='utf-8')as f :
                    adv =json .load (f )
            adv .setdefault ('watchlist',{})
            gid =str (interaction .guild .id )
            adv ['watchlist'].setdefault (gid ,{})
            until =int (time .time ())+7 *86400  # +7 дней
            adv ['watchlist'][gid ][str (user .id )]={
                "reason":f"Автоматически: {mute_count}-й мьют. {reason or ''}",
                "added_by":str (interaction .user ),
                "timestamp":datetime .now (timezone .utc ).isoformat (),
                "until":until ,
                "auto":True ,
            }
            with open (adv_file ,'w',encoding ='utf-8')as f :
                json .dump (adv ,f ,indent =2 ,ensure_ascii =False )
        except Exception as ex :
            log .warning (f"[watchlist auto] {ex}")

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


# ═══════════════════════════════════════════════════════════════════
#  SELECT-МЕНЮ МОДЕРАЦИИ (без кнопок/эмодзи — только выпадающие меню)
# ═══════════════════════════════════════════════════════════════════
class ModActionSelect(discord.ui.Select):
    """Выбор действия модерации."""

    def __init__(self, cog):
        options = [
            discord.SelectOption(label="Ban", value="ban", description="Забанить участника"),
            discord.SelectOption(label="Kick", value="kick", description="Выгнать участника"),
            discord.SelectOption(label="Mute (Chat + Voice)", value="timeout", description="Timeout — закрыть и чат, и голосовой"),
            discord.SelectOption(label="Mute (Только чат)", value="mute_chat", description="Закрыть только чат (timeout)"),
            discord.SelectOption(label="Mute (Только voice)", value="vmute", description="Заглушить микрофон (чат не трогает)"),
            discord.SelectOption(label="Unban", value="unban", description="Разбанить участника (по ID)"),
            discord.SelectOption(label="Очистить сообщения", value="clear", description="Удалить N сообщений"),
            discord.SelectOption(label="Unmute (Chat + Voice)", value="untimeout", description="Снять timeout с участника"),
            discord.SelectOption(label="Unmute (Voice)", value="vunmute", description="Включить микрофон участника"),
        ]
        super().__init__(
            placeholder="Выберите действие модерации...",
            options=options,
            min_values=1,
            max_values=1,
        )
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        action = self.values[0]
        modal = ModActionModal(self.cog, action)
        await interaction.response.send_modal(modal)


class ModActionModal(discord.ui.Modal):
    """Модальное окно ввода данных для выбранного действия."""

    def __init__(self, cog, action):
        self.cog = cog
        self.action = action
        title = "Модерация"
        super().__init__(title=title)

        self.target = discord.ui.TextInput(
            label="Цель (ID или @упоминание)", required=False,
            placeholder="123456789012345678 или @пользователь",
        )
        self.reason = discord.ui.TextInput(
            label="Причина", required=False, default="Не указана",
            style=discord.TextStyle.short,
        )
        self.amount = discord.ui.TextInput(
            label="Минут (timeout) / количество (clear)", required=False,
            default="5",
        )
        self.add_item(self.target)
        self.add_item(self.reason)
        self.add_item(self.amount)

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog._execute_mod_action(
            interaction,
            self.action,
            self.target.value or "",
            self.reason.value or "",
            self.amount.value or "5",
        )


class ModPanelView(discord.ui.View):
    """View панели: только выпадающее меню, без кнопок."""

    def __init__(self, cog):
        super().__init__(timeout=300)
        self.add_item(ModActionSelect(cog))


async def setup (bot ):
    await bot .add_cog (Moderation (bot ))
