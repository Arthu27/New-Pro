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

    @app_commands .command (name ='gprofile',description ='Профиль геймификации')
    @app_commands .describe (user ='Пользователь (необязательно)')
    async def profile (self ,interaction :discord .Interaction ,
    user :discord .Member =None ):
        """Показать ваш профиль"""
        target_user =user or interaction .user 

        # Получить очки
        points =points_system .get_points (str (target_user .id ))

        # Получить уровень
        level =level_system .get_level (str (target_user .id ))

        # Получить значки
        badges =badge_system .get_user_badges (str (target_user .id ))

        # Создать embed
        embed =discord .Embed (
        title =f"Профиль — {target_user.display_name}",
        color =discord .Color .gold (),
        timestamp =datetime .now ()
        )

        embed .set_thumbnail (url =target_user .display_avatar .url )

        embed .add_field (name =" Очки",value =f"{points:,}",inline =True )
        embed .add_field (name =" Уровень",value =f"{level['level']} - {level['name']}",inline =True )
        embed .add_field (name =" Значки",value =str (len (badges )),inline =True )

        # Список значков
        if badges :
            badge_list ="\n".join ([f"• {badge['name']}"for badge in badges [:5 ]])
            embed .add_field (name ="Значки",value =badge_list ,inline =False )

        embed .set_footer (text =f"User ID: {target_user.id}")

        await interaction .response .send_message (embed =embed )

    @app_commands .command (name ='game-leaderboard',description ='Показать таблицу лидеров геймификации')
    @app_commands .describe (type ='Тип таблицы (points/badges/level)')
    async def leaderboard (self ,interaction :discord .Interaction ,type :str ='points'):
        """Показать таблицу лидеров"""
        if type =='points':
            leaders =leaderboard_system .get_top_users ('points',limit =10 )
            title ="🏆 Таблица лидеров по очкам"
        elif type =='badges':
            leaders =leaderboard_system .get_top_users ('badges',limit =10 )
            title ="🏅 Таблица лидеров по значкам"
        elif type =='level':
            leaders =leaderboard_system .get_top_users ('level',limit =10 )
            title ="📈 Таблица лидеров по уровням"
        else :
            await interaction .response .send_message (
            "❌ Неверный тип таблицы! (points/badges/level)",
            ephemeral =True 
            )
            return 

            # Создать embed
        embed =discord .Embed (
        title =title ,
        color =discord .Color .gold (),
        timestamp =datetime .now ()
        )

        # Список лидеров
        for i ,leader in enumerate (leaders ,1 ):
            medal =""if i ==1 else ""if i ==2 else ""if i ==3 else f"{i}."

            user =interaction .guild .get_member (leader ['user_id'])
            user_name =user .display_name if user else f"User {leader['user_id']}"

            if type =='points':
                value =f"{leader['points']:,} очков"
            elif type =='badges':
                value =f"Значков: {leader['badges']}"
            else :
                value =f"Уровень {leader['level']}"

            embed .add_field (
            name =f"{medal} {user_name}",
            value =value ,
            inline =False 
            )

        await interaction .response .send_message (embed =embed )

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

    @app_commands .command (name ='daily',description ='Получить ежедневную награду')
    async def daily (self ,interaction :discord .Interaction ):
        """Получить ежедневную награду"""
        # Проверка ежедневной награды
        can_claim ,time_left =points_system .can_claim_daily (str (interaction .user .id ))

        if not can_claim :
            hours =int (time_left .total_seconds ()/3600 )
            minutes =int ((time_left .total_seconds ()%3600 )/60 )

            await interaction .response .send_message (
            f"⏰ Вы уже забрали ежедневную награду! Попробуйте снова через {hours} ч {minutes} мин.",
            ephemeral =True 
            )
            return 

            # Выдать ежедневную награду
        points =points_system .claim_daily (str (interaction .user .id ))

        # Создать embed
        embed =discord .Embed (
        title =" 🎁 Ежедневная награда",
        description =f"**Получено очков:** {points}\n\nВозвращайтесь завтра!",
        color =discord .Color .green (),
        timestamp =datetime .now ()
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
