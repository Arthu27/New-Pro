
from logger import get_logger

_log = get_logger("autorole_level")

import discord 
from discord .ext import commands 
import json 
import os 
import random 
import time 

class AutoRoleLevel (commands .Cog ):
    """Система XP + автоматическая выдача ролей за уровни"""

    def __init__ (self ,bot ):
        self .bot =bot 
        self ._cooldowns ={}# user_id → last_xp_time

    def _xp_file (self ,guild_id ):
        return f'data/xp_{guild_id}.json'

    def _level_roles_file (self ,guild_id ):
        return f'data/level_roles_{guild_id}.json'

    def _load_xp (self ,guild_id ):
        f =self ._xp_file (guild_id )
        if not os .path .exists (f ):
            return {}
        try :
            with open (f ,'r',encoding ='utf-8')as fp :
                return json .load (fp )
        except Exception :
            return {}

    def _save_xp (self ,guild_id ,data ):
        os .makedirs ('data',exist_ok =True )
        with open (self ._xp_file (guild_id ),'w',encoding ='utf-8')as fp :
            json .dump (data ,fp ,indent =2 )

    def _get_level_roles (self ,guild_id ):
        f =self ._level_roles_file (guild_id )
        if not os .path .exists (f ):
            return {}
        try :
            with open (f ,'r',encoding ='utf-8')as fp :
                return json .load (fp )
        except Exception :
            return {}

    @staticmethod 
    def _level_from_xp (xp ):
        """Расчёт уровня из XP: с каждым уровнем требуется больше XP"""
        level =0 
        required =100 
        while xp >=required :
            xp -=required 
            level +=1 
            required =int (required *1.15 )
        return level 

    @commands .Cog .listener ()
    async def on_message (self ,message ):
        if message .author .bot or not message .guild :
            return 

        # Настройки из панели (/leveling): выключено? диапазон XP?
        _xp_min ,_xp_max =15 ,25
        try :
            import json as _j ,os as _o
            _lf =f'data/leveling_{message.guild.id}.json'
            _cfg =_j .load (open (_lf ,'r',encoding ='utf-8'))if _o .path .exists (_lf )else {}
            if _cfg and not _cfg .get ('enabled',True ):
                return 
            _xp_min =int (_cfg .get ('xp_min',15 )or 15 )
            _xp_max =max (_xp_min ,int (_cfg .get ('xp_max',25 )or 25 ))
        except Exception as _ex:
            _log.debug("on_message(): подавлено: %s", _ex)

        uid =str (message .author .id )
        now =time .time ()

        # Cooldown: 60 saniyede bir XP kazan (spam korumasы)
        last =self ._cooldowns .get (uid ,0 )
        if now -last <60 :
            return 
        self ._cooldowns [uid ]=now 

        # XP ver (15-25 arasы rastgele)
        xp_gain =random .randint (_xp_min ,_xp_max )

        xp_data =self ._load_xp (message .guild .id )
        user_data =xp_data .get (uid ,{'xp':0 ,'level':0 })

        old_xp =user_data .get ('xp',0 )
        old_level =user_data .get ('level',0 )
        new_xp =old_xp +xp_gain 
        new_level =self ._level_from_xp (new_xp )

        user_data ['xp']=new_xp 
        user_data ['level']=new_level 
        xp_data [uid ]=user_data 
        self ._save_xp (message .guild .id ,xp_data )

        # Level atladыysa уведомление отправить
        if new_level >old_level :
            try :
                await message .channel .send (
                f'🎉 {message.author.mention}, достигнут **уровень {new_level}**!',
                delete_after =10 
                )
            except Exception as _ex:
                _log.debug("on_message(): подавлено: %s", _ex)

                # Автоматически роли контроль
        level_roles =self ._get_level_roles (message .guild .id )
        if not level_roles :
            return 

        member =message .author 
        for required_level ,role_id in level_roles .items ():
            if new_level >=int (required_level ):
                role =message .guild .get_role (int (role_id ))
                if role and role not in member .roles :
                    try :
                        await member .add_roles (role ,reason =f'Уровень {required_level} — автороль')
                    except Exception as _ex:
                        _log.debug("on_message(): подавлено: %s", _ex)

                        # На сервер вход роли контроль 
    @commands .Cog .listener ()
    async def on_member_join (self ,member ):
        if member .bot :
            return 
        uid =str (member .id )
        xp_data =self ._load_xp (member .guild .id )
        user_data =xp_data .get (uid )
        if not user_data :
            return 

        level =user_data .get ('level',0 )
        level_roles =self ._get_level_roles (member .guild .id )
        if not level_roles :
            return 

        for required_level ,role_id in level_roles .items ():
            if level >=int (required_level ):
                role =member .guild .get_role (int (role_id ))
                if role :
                    try :
                        await member .add_roles (role ,reason =f'Уровень {required_level} — автороль при входе')
                    except Exception as _ex:
                        _log.debug("on_member_join(): подавлено: %s", _ex)

                        # Команды 
    @commands .command (name ='level-role-add',aliases =['level-rol-add'])
    @commands .has_permissions (administrator =True )
    async def add_level_role (self ,ctx ,level :int ,role :discord .Role ):
        """Назначить роль за уровень. Использование: !level-rol-add 5 @Роль"""
        f =self ._level_roles_file (ctx .guild .id )
        os .makedirs ('data',exist_ok =True )
        data ={}
        if os .path .exists (f ):
            with open (f ,'r',encoding ='utf-8')as fp :
                data =json .load (fp )

        data [str (level )]=str (role .id )

        with open (f ,'w',encoding ='utf-8')as fp :
            json .dump (data ,fp ,indent =2 )

        await ctx .send (f'✅ Роль {role.mention} назначена для уровня **{level}**!')

    @commands .command (name ='level-role-remove',aliases =['level-rol-remove'])
    @commands .has_permissions (administrator =True )
    async def remove_level_role (self ,ctx ,level :int ):
        """Удалить роль за уровень"""
        f =self ._level_roles_file (ctx .guild .id )
        if not os .path .exists (f ):
            await ctx .send ('❌ Роли за уровни ещё не настроены!')
            return 

        with open (f ,'r',encoding ='utf-8')as fp :
            data =json .load (fp )

        removed =data .pop (str (level ),None )

        with open (f ,'w',encoding ='utf-8')as fp :
            json .dump (data ,fp ,indent =2 )

        if removed :
            await ctx .send (f'✅ Роль для уровня **{level}** удалена!')
        else :
            await ctx .send (f'❌ Уровень **{level}** не найден!')

    @commands .command (name ='level-role',aliases =['level-rol'])
    async def list_level_roles (self ,ctx ):
        """Список ролей за уровни"""
        data =self ._get_level_roles (ctx .guild .id )
        if not data :
            await ctx .send ('❌ Роли за уровни пока не настроены! Используйте `!level-rol-add <уровень> @роль`')
            return 

        embed =discord .Embed (title ='🏅 Роли за уровни',color =0xFFD700 )
        for level ,role_id in sorted (data .items (),key =lambda x :int (x [0 ])):
            role =ctx .guild .get_role (int (role_id ))
            embed .add_field (
            name =f'Уровень {level}',
            value =role .mention if role else f'Удалённая роль ({role_id})',
            inline =False 
            )
        await ctx .send (embed =embed )

        # NOTE: `rank` and `top-level` commands are intentionally removed from this cog.
        # The new cogs/leveling_engagement.py provides richer /rank, /leaderboard, /achievements
        # commands with aliases (`level`, `xp`, `lb`, `top`). Registering them here again
        # would crash with `CommandRegistrationError: The command rank is already an existing command or alias.`
        # See commit 15504bc follow-up.

async def setup (bot ):
    await bot .add_cog (AutoRoleLevel (bot ))
