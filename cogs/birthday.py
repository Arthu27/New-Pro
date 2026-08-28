
from logger import get_logger

_log = get_logger("birthday")

import discord 
from discord .ext import commands ,tasks 
from discord import app_commands 
import json 
import os 
from datetime import datetime ,timezone 
from cogs .embed_utils import _divider ,now_ts 
from config import Config 

GIF_BIRTHDAY ="https://media.tenor.com/ZBDpMFBMFpkAAAAC/celebration-party.gif"

class Birthday (commands .Cog ):
    def __init__ (self ,bot ):
        self .bot =bot 
        self .check_birthdays .start ()
        self .remove_birthday_roles .start ()

    def cog_unload (self ):
        self .check_birthdays .cancel ()
        self .remove_birthday_roles .cancel ()

    def get_data (self ,guild_id ):
        f =f'data/birthdays_{guild_id}.json'
        if not os .path .exists (f ):
            return {}
        with open (f ,'r',encoding ='utf-8')as fp :
            return json .load (fp )

    def save_data (self ,guild_id ,data ):
        os .makedirs ('data',exist_ok =True )
        with open (f'data/birthdays_{guild_id}.json','w',encoding ='utf-8')as fp :
            json .dump (data ,fp ,indent =2 ,ensure_ascii =False )

    def get_settings (self ,guild_id ):
        f =f'data/birthday_settings_{guild_id}.json'
        if not os .path .exists (f ):
            return {'channel_id':None ,'role_id':None ,'message':'🎂 Сегодня день рождения у {user}! Поздравляем! 🎉'}
        with open (f ,'r',encoding ='utf-8')as fp :
            return json .load (fp )

    @tasks .loop (hours =1 )
    async def check_birthdays (self ):
        now =datetime .now (timezone .utc )
        if now .hour !=9 :
            return 
        today =f"{now.month:02d}-{now.day:02d}"
        for guild in self .bot .guilds :
            data =self .get_data (guild .id )
            settings =self .get_settings (guild .id )
            if not settings .get ('channel_id'):
                continue 
            channel =guild .get_channel (int (settings ['channel_id']))
            if not channel :
                continue 
            for user_id ,info in data .items ():
                if info .get ('date')!=today :
                    continue 
                    # Сегодня уже поздравляли?
                if info .get ('celebrated')==str (now .year ):
                    continue 
                member =guild .get_member (int (user_id ))
                if not member :
                    try :
                        member =await guild .fetch_member (int (user_id ))
                    except Exception as _ex:
                        _log.debug('check_birthdays(): подавлено: %s', _ex)
                if not member :
                    continue 
                age_str =""
                age =None 
                if info .get ('year'):
                    age =now .year -info ['year']
                    age_str =f" ({age} лет)"

                embed =discord .Embed (
                title ="🎂 День рождения!",
                color =0xFF69B4 ,
                timestamp =now 
                )
                embed .description =(
                f"```ansi\n\u001b[1;35m С ДНЁМ РОЖДЕНИЯ!\u001b[0m\n```\n{_divider()}\n\n"
                f"🎂 У {member.mention} сегодня день рождения{age_str}!\n\n"
                "> Все ждём твоих поздравлений! 💌\n\n"
                f"{_divider()}"
                )
                embed .set_thumbnail (url =member .display_avatar .url )
                embed .set_image (url =GIF_BIRTHDAY )
                embed .add_field (name ="📅 Дата",value =f"```{info['date'].replace('-', '/')}```",inline =True )
                if age :
                    embed .add_field (name ="🎈 Возраст",value =f"```{age}```",inline =True )
                embed .add_field (name ="🎉 Поздравь!",value ="*Оставь поздравление ниже!* ",inline =False )
                embed .set_footer (text =f"Hakumo • {guild.name}",icon_url =guild .icon .url if guild .icon else None )
                from cogs .icons import send_with_icon 
                await send_with_icon (channel ,embed ,'birthday',content =f'🎉 {member.mention}')

                # Выдать роль на день рождения
                if settings .get ('role_id'):
                    role =guild .get_role (int (settings ['role_id']))
                    if role :
                        try :
                            await member .add_roles (role ,reason ="Роль именинника")
                        except Exception as _ex:
                            _log.debug("check_birthdays(): подавлено: %s", _ex)

                            # Economy hediyesi ver
                if settings .get ('gift_coins',0 )>0 :
                    await self ._give_birthday_coins (guild .id ,user_id ,settings ['gift_coins'])

                    # Kutlandы как iшaretle
                info ['celebrated']=str (now .year )
                self .save_data (guild .id ,data )

    @tasks .loop (hours =1 )
    async def remove_birthday_roles (self ):
        """Забрать роль после того, как день рождения прошёл."""
        now =datetime .now (timezone .utc )
        today =f"{now.month:02d}-{now.day:02d}"
        for guild in self .bot .guilds :
            settings =self .get_settings (guild .id )
            if not settings .get ('role_id'):
                continue 
            role =guild .get_role (int (settings ['role_id']))
            if not role :
                continue 
            data =self .get_data (guild .id )
            for user_id ,info in data .items ():
                if info .get ('date')==today :
                        continue # Сегодня день рождения — роль оставить
                member =guild .get_member (int (user_id ))
                if member and role in member .roles :
                    try :
                        await member .remove_roles (role ,reason ="День рождения закончился")
                    except Exception as _ex:
                        _log.debug("remove_birthday_roles(): подавлено: %s", _ex)

    async def _give_birthday_coins (self ,guild_id ,user_id ,amount ):
        """Добавить подарок ко дню рождения в экономику."""
        f =f'data/economy_{guild_id}.json'
        try :
            econ ={}
            if os .path .exists (f ):
                with open (f ,'r',encoding ='utf-8')as fp :
                    econ =json .load (fp )
            econ .setdefault (str (user_id ),{})['balance']=econ .get (str (user_id ),{}).get ('balance',0 )+amount 
            with open (f ,'w',encoding ='utf-8')as fp :
                json .dump (econ ,fp ,indent =2 ,ensure_ascii =False )
        except Exception as _ex:
            _log.debug("_give_birthday_coins(): подавлено: %s", _ex)

    @check_birthdays .before_loop 
    async def before_check (self ):
        await self .bot .wait_until_ready ()

    @remove_birthday_roles .before_loop 
    async def before_remove_roles (self ):
        await self .bot .wait_until_ready ()

    @app_commands .command (name ='birthday',description ='Сохранить день рождение')
    @app_commands .describe (день ='День (1-31)',месяц ='Месяц (1-12)',год ='Год (необязательно)')
    async def set_birthday (self ,interaction :discord .Interaction ,день :int ,месяц :int ,год :int =None ):
        if not (1 <=день <=31 and 1 <=месяц <=12 ):
            await interaction .response .send_message ('❌ Неверная дата!',ephemeral =True )
            return 
        data =self .get_data (interaction .guild_id )
        entry ={'date':f'{месяц:02d}-{день:02d}','name':interaction .user .display_name }
        if год :
            entry ['year']=год 
        data [str (interaction .user .id )]=entry 
        self .save_data (interaction .guild_id ,data )

        e =discord .Embed (title ="🎂 Дата рождения сохранена!",color =0xFF69B4 ,timestamp =datetime .now (timezone .utc ))
        e .description =(
        f"```ansi\n\u001b[1;35m ЗАПИСЬ ЗАВЕРШЕНО\u001b[0m\n```\n{_divider()}\n\n"
        f"🎂 Дата рождения сохранена! В этот день мы тебя поздравим.\n\n{_divider()}"
        )
        e .set_thumbnail (url =interaction .user .display_avatar .url )
        e .add_field (name ="📅 Дата",value =f"```{день}/{месяц}{f'/{год}' if год else ''}```",inline =True )
        e .add_field (name ="👤 Пользователь",value =interaction .user .mention ,inline =True )
        e .add_field (name ="ℹ️ Информация",value ="*Когда наступит день рождения — объявим на сервере!*",inline =False )
        e .set_footer (text =f"Hakumo • {interaction.guild.name}",icon_url =interaction .guild .icon .url if interaction .guild .icon else None )
        await interaction .response .send_message (embed =e ,ephemeral =True )

    @app_commands .command (name ='birthdays',description ='Показать ближайшие дни рождения')
    async def list_birthdays (self ,interaction :discord .Interaction ):
        data =self .get_data (interaction .guild_id )
        if not data :
            await interaction .response .send_message ('🎂 Пока нет записей о днях рождения!',ephemeral =True )
            return 
        now =datetime .now (timezone .utc )
        today_num =now .month *100 +now .day 
        entries =[]
        for uid ,info in data .items ():
            try :
                m ,d =map (int ,info ['date'].split ('-'))
                num =m *100 +d 
                diff =num -today_num 
                if diff <0 :
                    diff +=1200 
                member =interaction .guild .get_member (int (uid ))
                name =member .display_name if member else info .get ('name',uid )
                entries .append ((diff ,d ,m ,name ,uid ))
            except Exception as _ex:
                _log.debug("list_birthdays(): подавлено: %s", _ex)
                continue 
        entries .sort ()

        e =discord .Embed (title ="🎂 Ближайшие дни рождения",color =0xFF69B4 ,timestamp =now )
        e .description =f"```ansi\n\u001b[1;35m КАЛЕНДАРЬ ДНЕЙ РОЖДЕНИЯ\u001b[0m\n```\n{_divider()}"
        for diff ,d ,m ,name ,uid in entries [:15 ]:
            if diff ==0 :
                label ="🎉 **СЕГОДНЯ!**"
            elif diff <=7 :
                label =f"⏰ через {diff} дн."
            else :
                label =f"📅 через {diff} дн."
            e .add_field (name =f"🎂 {name}",value =f"`{d:02d}/{m:02d}` — {label}",inline =False )
        e .set_footer (text =f"Hakumo • {interaction.guild.name}",icon_url =interaction .guild .icon .url if interaction .guild .icon else None )
        await interaction .response .send_message (embed =e )

    @app_commands .command (name ='birthday-delete',description ='Удалить запись о дне рождения')
    async def delete_birthday (self ,interaction :discord .Interaction ):
        data =self .get_data (interaction .guild_id )
        uid =str (interaction .user .id )
        if uid not in data :
            await interaction .response .send_message ('ℹ️ Запись о дне рождения не найдена.',ephemeral =True )
            return 
        del data [uid ]
        self .save_data (interaction .guild_id ,data )
        await interaction .response .send_message ('🗑️ Ваша дата рождения удалена из базы.',ephemeral =True )

    @app_commands .command (name ='birthday-setup',description ="Настройка системы дней рождения (менеджер)")
    @app_commands .describe (
    channel ='Канал для поздравлений',
    role ='Роль на день рождения (необязательно)',
    gift_coins ='Сколько монет дарить на день рождения'
    )
    @app_commands .checks .has_permissions (administrator =True )
    async def setup_birthday_slash (self ,interaction :discord .Interaction ,
    channel :discord .TextChannel ,
    role :discord .Role =None ,
    gift_coins :int =0 ):
        settings =self .get_settings (interaction .guild_id )
        settings ['channel_id']=str (channel .id )
        if role :
            settings ['role_id']=str (role .id )
        settings ['gift_coins']=gift_coins 
        os .makedirs ('data',exist_ok =True )
        with open (f'data/birthday_settings_{interaction.guild_id}.json','w',encoding ='utf-8')as fp :
            json .dump (settings ,fp ,indent =2 ,ensure_ascii =False )

        e =discord .Embed (title ="🎂 Система дней рождения настроена!",color =0x2ECC71 ,timestamp =datetime .now (timezone .utc ))
        e .add_field (name ="📢 Канал",value =channel .mention ,inline =True )
        e .add_field (name =" Роль",value =role .mention if role else "`Нет`",inline =True )
        e .add_field (name =" Бонусные монеты",value =f"`{gift_coins}`"if gift_coins else "`Нет`",inline =True )
        e .set_footer (text =f"Hakumo • {interaction.guild.name}")
        await interaction .response .send_message (embed =e ,ephemeral =True )


async def setup (bot ):
    await bot .add_cog (Birthday (bot ),guilds =Config .guild_objects ())
