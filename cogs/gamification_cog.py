"""
Gamification Cog
Gamification система cog'u
"""
import discord 
from discord .ext import commands 
from discord import app_commands 
from datetime import datetime 
from services .gamification import points_system ,badge_system ,level_system ,leaderboard_system 

from logger import get_logger 
log =get_logger ("gamification_cog")



class GamificationCog (commands .Cog ):
    """Gamification система cog'u"""

    def __init__ (self ,bot ):
        self .bot =bot 

    @app_commands .command (name ='gprofile',description ='Профиль геймификации')
    @app_commands .describe (user ='Пользователь (необязательно)')
    async def profile (self ,interaction :discord .Interaction ,
    user :discord .Member =None ):
        """Profilinizi gёrюntюleyin"""
        target_user =user or interaction .user 

        # Очки al
        points =points_system .get_points (target_user .id )

        # Уровень al
        level =level_system .get_level (target_user .id )

        # Rozetler al
        badges =badge_system .get_user_badges (target_user .id )

        # Embed создать
        embed =discord .Embed (
        title =f" {target_user.display_name}'s Profile",
        color =discord .Color .gold (),
        timestamp =datetime .now ()
        )

        embed .set_thumbnail (url =target_user .display_avatar .url )

        embed .add_field (name =" Очки",value =f"{points:,}",inline =True )
        embed .add_field (name =" Уровень",value =f"{level['level']} - {level['name']}",inline =True )
        embed .add_field (name =" Rozetler",value =str (len (badges )),inline =True )

        # Значок listesi
        if badges :
            badge_list ="\n".join ([f"• {badge['name']}"for badge in badges [:5 ]])
            embed .add_field (name ="Rozetler",value =badge_list ,inline =False )

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

            # Embed создать
        embed =discord .Embed (
        title =title ,
        color =discord .Color .gold (),
        timestamp =datetime .now ()
        )

        # Lider listesi
        for i ,leader in enumerate (leaders ,1 ):
            medal =""if i ==1 else ""if i ==2 else ""if i ==3 else f"{i}."

            user =interaction .guild .get_member (leader ['user_id'])
            user_name =user .display_name if user else f"User {leader['user_id']}"

            if type =='points':
                value =f"{leader['points']:,} очки"
            elif type =='badges':
                value =f"{leader['badges']} rozet"
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

        # Rozetler al
        badges =badge_system .get_user_badges (target_user .id )

        if not badges :
            await interaction .response .send_message (
            f"😶 У {target_user.display_name} пока нет значков!",
            ephemeral =True 
            )
            return 

            # Embed создать
        embed =discord .Embed (
        title =f" {target_user.display_name}'s Badges",
        description =f"Всего {len(badges)} rozet",
        color =discord .Color .gold (),
        timestamp =datetime .now ()
        )

        # Значок listesi
        for badge in badges [:10 ]:
            embed .add_field (
            name =f"{badge['name']}",
            value =f"{badge.get('description', 'Нет описания')}\nПолучен: {badge['earned_at'][:10]}",
            inline =False 
            )

        await interaction .response .send_message (embed =embed )

    @app_commands .command (name ='daily',description ='Gюnlюk ёdюlюnюzю alыn')
    async def daily (self ,interaction :discord .Interaction ):
        """Gюnlюk ёdюlюnюzю alыn"""
        # Gюnlюk ёdюl проверкаю
        can_claim ,time_left =points_system .can_claim_daily (interaction .user .id )

        if not can_claim :
            hours =int (time_left .total_seconds ()/3600 )
            minutes =int ((time_left .total_seconds ()%3600 )/60 )

            await interaction .response .send_message (
            f"⏰ Вы уже забрали ежедневную награду! Попробуйте снова через {hours} ч {minutes} мин.",
            ephemeral =True 
            )
            return 

            # Gюnlюk ёdюl ver
        points =points_system .claim_daily (interaction .user .id )

        # Embed создать
        embed =discord .Embed (
        title =" Gюnlюk Ёdюl",
        description =f"**Получено очков:** {points}\n\nВозвращайтесь завтра!",
        color =discord .Color .green (),
        timestamp =datetime .now ()
        )

        await interaction .response .send_message (embed =embed )

    @app_commands .command (name ='streak',description ='Seri bilgilerinizi gёrюntюleyin')
    async def streak (self ,interaction :discord .Interaction ):
        """Seri bilgilerinizi gёrюntюleyin"""
        from services .gamification import streak_system 

        # Seri информация al
        streak_info =streak_system .get_streak (interaction .user .id )

        # Embed создать
        embed =discord .Embed (
        title =" Seri Bilgileri",
        color =discord .Color .orange (),
        timestamp =datetime .now ()
        )

        embed .add_field (name =" Mevcut Seri",value =f"{streak_info['current_streak']} gюn",inline =True )
        embed .add_field (name =" En Длинный Seri",value =f"{streak_info['longest_streak']} gюn",inline =True )

        await interaction .response .send_message (embed =embed )

    @commands .Cog .listener ()
    async def on_message (self ,message :discord .Message ):
        """Начислить XP за сообщение"""
        if message .author .bot :
            return 

            # XP ver
        xp_gained =points_system .add_xp (message .author .id ,1 )

        # Проверка повышения уровня
        if xp_gained :
            level =level_system .get_level (message .author .id )

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
        log .info (f" GamificationCog loaded")


async def setup (bot ):
    await bot .add_cog (GamificationCog (bot ))
