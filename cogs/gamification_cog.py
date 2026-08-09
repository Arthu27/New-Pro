"""
Gamification Cog
Ког системы геймификации
"""
import discord 
from discord .ext import commands 
from discord import app_commands 
from datetime import datetime 
from services .gamification import points_system ,badge_system ,level_system ,leaderboard_system 

from logger import get_logger 
log =get_logger ("gamification_cog")



class GamificationCog (commands .Cog ):
    """Ког системы геймификации"""

    def __init__ (self ,bot ):
        self .bot =bot 

    @app_commands .command (name ='badges',description ='Показать ваши значки')
    @app_commands .describe (user ='Пользователь (необязательно)')
    async def badges (self ,interaction :discord .Interaction ,
    user :discord .Member =None ):
        """Показать ваши значки"""
        target_user =user or interaction .user 

        # Получить значки
        badges =badge_system .get_user_badges (str (target_user .id ))

        if not badges :
            await interaction .response .send_message (
            f"😶 У {target_user.display_name} пока нет значков!",
            ephemeral =True 
            )
            return 

            # Создать embed
        embed =discord .Embed (
        title =f"Значки — {target_user.display_name}",
        description =f"Всего значков: {len(badges)}",
        color =discord .Color .gold (),
        timestamp =datetime .now ()
        )

        # Список значков
        for badge in badges [:10 ]:
            embed .add_field (
            name =f"{badge['name']}",
            value =f"{badge.get('description', 'Нет описания')}\nПолучен: {badge['earned_at'][:10]}",
            inline =False 
            )

        await interaction .response .send_message (embed =embed )

    @app_commands .command (name ='streak',description ='Ваша серия дней')
    async def streak (self ,interaction :discord .Interaction ):
        """Ваша серия дней"""
        from services .gamification import streak_system 

        # Информация о серии
        streak_info =streak_system .get_streak (str (interaction .user .id ))

        # Создать embed
        embed =discord .Embed (
        title ="Информация о серии",
        color =discord .Color .orange (),
        timestamp =datetime .now ()
        )

        embed .add_field (name ="Текущая серия",value =f"{streak_info['current_streak']} дн.",inline =True )
        embed .add_field (name ="Самая длинная серия",value =f"{streak_info['longest_streak']} дн.",inline =True )

        await interaction .response .send_message (embed =embed )

    @commands .Cog .listener ()
    async def on_message (self ,message :discord .Message ):
        """Начислить XP за сообщение"""
        if message .author .bot :
            return 

            # Начислить очки за сообщение
        uid =str (message .author .id )
        old_level =level_system .get_level (uid )['level']
        points_system .add_points (uid ,1 ,'message')
        level =level_system .get_level (uid )

        # Проверка повышения уровня
        if level ['level']>old_level :

            # Уведомление о повышении уровня
            embed =discord .Embed (
            title ="🎉 Новый уровень!",
            description =f"**{message.author.mention}** поднялся до **{level['level']}** уровня!\n\nНовый ранг: **{level['name']}**",
            color =discord .Color .gold (),
            timestamp =datetime .now ()
            )

            from cogs .icons import send_with_icon 
            await send_with_icon (message .channel ,embed ,'levelup')

    @commands .Cog .listener ()
    async def on_ready (self ):
        """Бот готов"""
        log .info ("Ког геймификации загружен")


async def setup (bot ):
    await bot .add_cog (GamificationCog (bot ))
