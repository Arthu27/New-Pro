import discord 
from discord .ext import commands 
from discord import app_commands 
import json 
import os 
from datetime import datetime 
from cogs .embed_utils import _divider ,now_ts ,error_embed 
from logger import get_logger 
from config import Config 

log =get_logger ("advanced_mod")

class AdvancedMod (commands .Cog ):
    def __init__ (self ,bot ):
        self .bot =bot 
        self .data_file ="data/mod_advanced_data.json"
        self .load_data ()

    def load_data (self ):
        os .makedirs ("data",exist_ok =True )
        loaded ={}
        if os .path .exists (self .data_file ):
            try :
                with open (self .data_file ,"r",encoding ="utf-8")as f :
                    loaded =json .load (f )
            except Exception :
                loaded ={}
        if not isinstance (loaded ,dict ):
            loaded ={}
        # Гарантируем ключи, чтобы не ловить KeyError
        loaded .setdefault ("case",{})
        loaded .setdefault ("notes",{})
        loaded .setdefault ("watchlist",{})
        self .data =loaded

    async def _mod_log_channel (self ,guild ):
        """Найти канал модерации (mod-log или moderasyon)."""
        ch =discord .utils .get (guild .text_channels ,name ="mod-log")
        if not ch :
            ch =discord .utils .get (guild .text_channels ,name ="moderasyon")
        return ch

    def _cleanup_expired_watchlist (self ,guild_id ,watch ):
        """Удалить из watchlist записи с истёкшим сроком (until). Возвращает обновлённый список."""
        import time as _t
        now =_t .time ()
        changed =False
        for uid ,info in list (watch .items ()):
            until =info .get ( "until" )if isinstance (info ,dict )else None
            if until and float (until )<=now :
                del watch [uid ]
                changed =True
        if changed :
            self .data [ "watchlist" ][guild_id ]=watch
            self .save_data ()
        return watch

    @commands .Cog .listener ()
    async def on_message (self ,message :discord .Message ):
        """Отслеживание пользователей из списка наблюдения (watchlist)."""
        if message .author .bot or not message .guild :
            return
        guild_id =str (message .guild .id )
        user_id =str (message .author .id )
        watch =self .data [ "watchlist" ].get (guild_id ,{})
        # Убираем истёкшие (1-недельные) автоматические записи
        watch =self ._cleanup_expired_watchlist (guild_id ,watch )
        if user_id not in watch :
            return

        # Anti-спам: не спамим алерты чаще, чем раз в 60 сек на пользователя
        import time as _time
        now =_time .time ()
        last =self .data .setdefault ( "watch_alerts",{ }).setdefault (user_id ,0)
        if now -last < 60 :
            return
        self .data [ "watch_alerts" ][user_id ]=now

        target =await self ._mod_log_channel (message .guild )
        if not target :
            return
        info =watch [user_id ]
        content =message .content or ( "(вложение/файл)" )
        e =discord .Embed (
        title ="👁 Извещение из списка наблюдения",
        color =0xF39C12 ,
        timestamp =datetime .utcnow ()
        )
        e .set_author (name =message .author .display_name ,icon_url =message .author .display_avatar .url )
        e .add_field (name ="Пользователь",value =f"{message.author.mention}\n`{message.author.id}`",inline =True )
        e .add_field (name ="Канал",value =message .channel .mention ,inline =True )
        e .add_field (name ="Причина",value =f"```{info.get('reason','Не указана')}```",inline =False )
        e .add_field (name ="Сообщение",value =f"{content[:900] or '(пусто)'}",inline =False )
        e .add_field (name ="Ссылка",value =f"[Перейти]({message.jump_url})",inline =False )
        e .set_footer (text ="Aether Модерация • watchlist",icon_url =message .guild .icon .url if message .guild .icon else None )
        try :
            await target .send (embed =e )
        except Exception as ex :
            log .error (f"watchlist alert error: {ex}")

    def save_data (self ):
        with open (self .data_file ,"w",encoding ="utf-8")as f :
            json .dump (self .data ,f ,indent =2 ,ensure_ascii =False )

    def add_case (self ,guild_id ,user_id ,mod_id ,action ,reason ):
        guild_id =str (guild_id )
        if guild_id not in self .data ["case"]:
            self .data ["case"][guild_id ]=[]
        case_id =len (self .data ["case"][guild_id ])+1 
        self .data ["case"][guild_id ].append ({
        "id":case_id ,"user_id":user_id ,"mod_id":mod_id ,
        "action":action ,"reason":reason ,
        "timestamp":datetime .utcnow ().isoformat ()
        })
        self .save_data ()
        return case_id 

    @app_commands .command (name ="history",description ="Показать историю модерации пользователя")
    @app_commands .checks .has_permissions (moderate_members =True )
    async def history (self ,interaction :discord .Interaction ,user :discord .Member ):
        guild_id =str (interaction .guild .id )
        case =self .data ["case"].get (guild_id ,[])
        user_case =[c for c in case if str (c ["user_id"])==str (user .id )]

        if not user_case :
            e =discord .Embed (title ="📗 Чистая история",color =0x2ECC71 ,timestamp =datetime .utcnow ())
            e .description =(
            f"```ansi\n\u001b[1;32m ЧИСТАЯ ЗАПИСЬ\u001b[0m\n```\n{_divider()}\n\n"
            f"{user.mention} записей о модерации не найдено.\n\n{_divider()}"
            )
            e .set_thumbnail (url =user .display_avatar .url )
            e .add_field (name =" Пользователь",value =f"`{user.name}` • `{user.id}`",inline =True )
            e .add_field (name =" Состояние",value ="```diff\n+ Нарушений нет\n```",inline =True )
            e .set_footer (text =f"Aether Модерация • {interaction.guild.name}",icon_url =interaction .guild .icon .url if interaction .guild .icon else None )
            await interaction .response .send_message (embed =e ,ephemeral =True )
            return 

        action_emojis ={"ban":"","kick":"","timeout":"","warn":"","unban":""}
        action_colors ={"ban":"31","kick":"33","timeout":"33","warn":"33","unban":"32"}

        e =discord .Embed (title ="📕 История модерации",color =0xE74C3C ,timestamp =datetime .utcnow ())
        e .description =(
        f"```ansi\n\u001b[1;31m ЗАПИСЬ МОДЕРАЦИИ\u001b[0m\n```\n{_divider()}"
        )
        e .set_thumbnail (url =user .display_avatar .url )
        e .set_author (name =f"{user.display_name} — история нарушений",icon_url =user .display_avatar .url )

        for case in user_case [-8 :]:
            act =case ['action'].lower ()
            emoji =action_emojis .get (act ,"")
            color_code =action_colors .get (act ,"37")
            e .add_field (
            name =f"{emoji} Дело #{case['id']} — {case['action'].upper()}",
            value =(
            f"```ansi\n\u001b[1;{color_code}m{case['action'].upper()}\u001b[0m\n```"
            f" {case['reason']}\n"
            f" `{case['timestamp'][:10]}`"
            ),
            inline =False 
            )

        e .add_field (
        name =" Сводка",
        value =f"```Всего {len(user_case)} действий модерации```",
        inline =False 
        )
        e .set_footer (
        text =f"Aether Модерация • {interaction.guild.name}",
        icon_url =interaction .guild .icon .url if interaction .guild .icon else None 
        )
        await interaction .response .send_message (embed =e ,ephemeral =True )

    @app_commands .command (name ="case",description ="Показать конкретное дело")
    @app_commands .checks .has_permissions (moderate_members =True )
    async def case (self ,interaction :discord .Interaction ,case_id :int ):
        guild_id =str (interaction .guild .id )
        case =self .data ["case"].get (guild_id ,[])
        case =next ((c for c in case if c ["id"]==case_id ),None )

        if not case :
            await interaction .response .send_message (embed =error_embed (f"Дело #{case_id} не найдено."),ephemeral =True )
            return 

        try :
            user =await self .bot .fetch_user (case ["user_id"])
            mod =await self .bot .fetch_user (case ["mod_id"])
        except Exception :
            user =mod =None 

        action_emojis ={"ban":"","kick":"","timeout":"","warn":""}
        emoji =action_emojis .get (case ["action"].lower (),"")

        e =discord .Embed (title =f"{emoji} Дело #{case_id} Детали",color =0x3498DB ,timestamp =datetime .utcnow ())
        e .description =(
        f"```ansi\n\u001b[1;34m ДЕТАЛИ ДЕЛА\u001b[0m\n```\n{_divider()}"
        )
        if user :
            e .set_thumbnail (url =user .display_avatar .url )
        e .add_field (name =" Цель",value =f"`{user}` • `{case['user_id']}`"if user else f"`{case['user_id']}`",inline =True )
        e .add_field (name =" Модератор",value =f"`{mod}`"if mod else f"`{case['mod_id']}`",inline =True )
        e .add_field (name =" Действие",value =f"```{case['action'].upper()}```",inline =True )
        e .add_field (name =" Причина",value =f"```{case['reason']}```",inline =False )
        e .add_field (name =" Дата",value =f"`{case['timestamp'][:19].replace('T', ' ')}`",inline =False )
        e .set_footer (
        text =f"Aether Модерация • {interaction.guild.name}",
        icon_url =interaction .guild .icon .url if interaction .guild .icon else None 
        )
        await interaction .response .send_message (embed =e ,ephemeral =True )

    @app_commands .command (name ="note",description ="Добавить заметку пользователю")
    @app_commands .checks .has_permissions (moderate_members =True )
    async def note (self ,interaction :discord .Interaction ,user :discord .Member ,note :str ):
        guild_id =str (interaction .guild .id )
        user_id =str (user .id )
        if guild_id not in self .data ["notes"]:
            self .data ["notes"][guild_id ]={}
        if user_id not in self .data ["notes"][guild_id ]:
            self .data ["notes"][guild_id ][user_id ]=[]
        self .data ["notes"][guild_id ][user_id ].append ({
        "note":note ,"mod":str (interaction .user ),
        "timestamp":datetime .utcnow ().isoformat ()
        })
        self .save_data ()

        e =discord .Embed (title ="📝 Заметка добавлена",color =0xF1C40F ,timestamp =datetime .utcnow ())
        e .description =(
        f"```ansi\n\u001b[1;33m ЗАМЕТКА СОХРАНЕНА\u001b[0m\n```\n{_divider()}"
        )
        e .set_thumbnail (url =user .display_avatar .url )
        e .add_field (name =" Пользователь",value =f"{user.mention}\n`{user.id}`",inline =True )
        e .add_field (name ="✍️ Добавил",value =interaction .user .mention ,inline =True )
        e .add_field (name ="📝 Заметка",value =f"```{note}```",inline =False )
        e .add_field (name =" Дата",value =f"<t:{now_ts()}:F>",inline =False )
        e .set_footer (text =f"Aether Модерация • {interaction.guild.name}",icon_url =interaction .guild .icon .url if interaction .guild .icon else None )
        await interaction .response .send_message (embed =e ,ephemeral =True )

    @app_commands .command (name ="notes",description ="Показать заметки пользователя")
    @app_commands .checks .has_permissions (moderate_members =True )
    async def notes (self ,interaction :discord .Interaction ,user :discord .Member ):
        guild_id =str (interaction .guild .id )
        user_id =str (user .id )
        notes =self .data ["notes"].get (guild_id ,{}).get (user_id ,[])

        if not notes :
            await interaction .response .send_message (
            embed =discord .Embed (description =f"ℹ️ У {user.mention} заметок нет.",color =0x3498DB ),
            ephemeral =True 
            )
            return 

        e =discord .Embed (title =f" {user.display_name} — заметки",color =0xF1C40F ,timestamp =datetime .utcnow ())
        e .description =f"```ansi\n\u001b[1;33m ЗАМЕТКИ\u001b[0m\n```\n{_divider()}"
        e .set_thumbnail (url =user .display_avatar .url )
        for i ,n in enumerate (notes ,1 ):
            e .add_field (
            name =f"📝 Заметка #{i} — `{n['timestamp'][:10]}`",
            value =f"```{n['note']}```*— {n['mod']}*",
            inline =False 
            )
        e .set_footer (text =f"Всего {len(notes)} заметок • Aether Модерация",icon_url =interaction .guild .icon .url if interaction .guild .icon else None )
        await interaction .response .send_message (embed =e ,ephemeral =True )

    @app_commands .command (name ="watchlist",description ="Добавить/удалить из списка наблюдения")
    @app_commands .checks .has_permissions (moderate_members =True )
    async def watchlist (self ,interaction :discord .Interaction ,user :discord .Member ,reason :str =None ):
        guild_id =str (interaction .guild .id )
        user_id =str (user .id )
        if guild_id not in self .data ["watchlist"]:
            self .data ["watchlist"][guild_id ]={}

        if user_id in self .data ["watchlist"][guild_id ]:
            del self .data ["watchlist"][guild_id ][user_id ]
            self .save_data ()
            e =discord .Embed (title ="👁 Удалён из списка наблюдения",color =0x2ECC71 ,timestamp =datetime .utcnow ())
            e .description =f"```ansi\n\u001b[1;32m УДАЛЁН ИЗ СПИСКА\u001b[0m\n```\n{_divider()}"
            e .set_thumbnail (url =user .display_avatar .url )
            e .add_field (name =" Пользователь",value =f"{user.mention}\n`{user.id}`",inline =True )
            e .add_field (name =" Дата",value =f"<t:{now_ts()}:R>",inline =True )
            e .set_footer (text =f"Aether Модерация • {interaction.guild.name}",icon_url =interaction .guild .icon .url if interaction .guild .icon else None )
        else :
            self .data ["watchlist"][guild_id ][user_id ]={
            "reason":reason or "Не указана",
            "added_by":str (interaction .user ),
            "timestamp":datetime .utcnow ().isoformat ()
            }
            self .save_data ()
            e =discord .Embed (title =" Добавлено в список наблюдения",color =0xF39C12 ,timestamp =datetime .utcnow ())
            e .description =(
            f"```ansi\n\u001b[1;33m ВНЕСЕНО В СПИСОК НАБЛЮДЕНИЯ\u001b[0m\n```\n{_divider()}\n\n"
            f"{user.mention} теперь в списке наблюдения. Действия будут отслеживаться.\n\n{_divider()}"
            )
            e .set_thumbnail (url =user .display_avatar .url )
            e .add_field (name =" Пользователь",value =f"{user.mention}\n`{user.id}`",inline =True )
            e .add_field (name ="✍️ Добавил",value =interaction .user .mention ,inline =True )
            e .add_field (name =" Причина",value =f"```{reason or 'Не указана'}```",inline =False )
            e .add_field (name =" Дата",value =f"<t:{now_ts()}:F>",inline =False )
            e .set_footer (text =f"Aether Модерация • {interaction.guild.name}",icon_url =interaction .guild .icon .url if interaction .guild .icon else None )
        await interaction .response .send_message (embed =e ,ephemeral =True )

    @app_commands .command (name ="watchlist-show",description ="Показать список наблюдения")
    @app_commands .checks .has_permissions (moderate_members =True )
    async def watchlist_show (self ,interaction :discord .Interaction ):
        guild_id =str (interaction .guild .id )
        watchlist =self .data ["watchlist"].get (guild_id ,{})
        watchlist =self ._cleanup_expired_watchlist (guild_id ,watchlist )

        if not watchlist :
            await interaction .response .send_message (
            embed =discord .Embed (description =" Список наблюдения сейчас пуст.",color =0x3498DB ),
            ephemeral =True 
            )
            return

        import time as _t
        now =_t .time ()
        e =discord .Embed (title ="👁 Список наблюдения",color =0xF39C12 ,timestamp =datetime .utcnow ())
        e .description =(
        f"```ansi\n\u001b[1;33m ПОЛЬЗОВАТЕЛИ ПОД НАБЛЮДЕНИЕМ\u001b[0m\n```\n{_divider()}"
        )
        for user_id ,data in watchlist .items ():
            try :
                user =await self .bot .fetch_user (int (user_id ))
                name =str (user )
            except Exception :
                name =user_id 
            until =data .get ("until")if isinstance (data ,dict )else None
            extra =""
            if until :
                rem =int (float (until ))-int (now )
                if rem >0 :
                    extra =f"\n*Авто-снятие: через {rem // 86400}д {(rem % 86400) // 3600}ч*"
                else :
                    extra ="\n*Истекает сейчас*"
            e .add_field (
            name =f" {name}",
            value =f" `{data['reason']}`\n *{data['added_by']}*\n `{data['timestamp'][:10]}`{extra}",
            inline =False 
            )
        e .set_footer (
        text =f"Всего: {len(watchlist)} пользователей • Aether Модерация",
        icon_url =interaction .guild .icon .url if interaction .guild .icon else None 
        )
        await interaction .response .send_message (embed =e ,ephemeral =True )

    @app_commands .command (name ="banlist",description ="Показать список забаненных пользователей")
    @app_commands .checks .has_permissions (ban_members =True )
    async def banlist (self ,interaction :discord .Interaction ):
        await interaction .response .defer (ephemeral =True )
        bans =[entry async for entry in interaction .guild .bans (limit =50 )]

        if not bans :
            await interaction .followup .send (
            embed =discord .Embed (description =" Забаненных пользователей нет.",color =0x2ECC71 ),
            ephemeral =True 
            )
            return 

        e =discord .Embed (title ="🔨 Список банов",color =0xE74C3C ,timestamp =datetime .utcnow ())
        e .description =(
        f"```ansi\n\u001b[1;31m ЗАБАНЕННЫЕ ПОЛЬЗОВАТЕЛИ\u001b[0m\n```\n{_divider()}"
        )
        for entry in bans [:20 ]:
            e .add_field (
            name =f" {entry.user}",
            value =f"`{entry.user.id}`\n *{entry.reason or 'Причина не указана'}*",
            inline =False 
            )
        e .set_footer (
        text =f"Всего: {len(bans)} банов • Aether Модерация",
        icon_url =interaction .guild .icon .url if interaction .guild .icon else None 
        )
        await interaction .followup .send (embed =e ,ephemeral =True )

    @app_commands .command (name ="massrole",description ="Массовая выдача/снятие роли")
    @app_commands .describe (role ="Роль, которую нужно выдать или снять",action ="Действие: выдать или снять роль у всех участников")
    @app_commands .choices (action =[
    app_commands .Choice (name ="выдать",value ="give"),
    app_commands .Choice (name ="снять",value ="remove")
    ])
    @app_commands .checks .has_permissions (administrator =True )
    async def massrole (self ,interaction :discord .Interaction ,role :discord .Role ,action :str ):
        await interaction .response .defer (ephemeral =True )
        count =0 
        if action .lower ()=="give":
            for member in interaction .guild .members :
                if role not in member .roles and not member .bot :
                    try :
                        await member .add_roles (role )
                        count +=1 
                    except Exception :
                        pass 
            e =discord .Embed (title ="✅ Роли выданы массово",color =0x2ECC71 ,timestamp =datetime .utcnow ())
            e .description =f"```ansi\n\u001b[1;32m МАССОВАЯ ВЫДАЧА РОЛИ\u001b[0m\n```\n{_divider()}"
            e .add_field (name ="🎭 Роль",value =role .mention ,inline =True )
            e .add_field (name ="👥 Затронуто",value =f"```{count} человек```",inline =True )
        elif action .lower ()=="al":
            for member in interaction .guild .members :
                if role in member .roles :
                    try :
                        await member .remove_roles (role )
                        count +=1 
                    except Exception :
                        pass 
            e =discord .Embed (title ="✅ Роли массово сняты",color =0xE74C3C ,timestamp =datetime .utcnow ())
            e .description =f"```ansi\n\u001b[1;31m МАССОВОЕ СНЯТИЕ РОЛИ\u001b[0m\n```\n{_divider()}"
            e .add_field (name ="🎭 Роль",value =role .mention ,inline =True )
            e .add_field (name ="👥 Затронуто",value =f"```{count} человек```",inline =True )
        else :
            await interaction .followup .send ("❌ Неверное действие! Выберите «выдать» или «снять».",ephemeral =True )
            return 
        e .set_footer (text =f"Aether Модерация • {interaction.guild.name}",icon_url =interaction .guild .icon .url if interaction .guild .icon else None )
        await interaction .followup .send (embed =e ,ephemeral =True )


async def setup (bot ):
    await bot .add_cog (AdvancedMod (bot ),guilds =Config .guild_objects ())
