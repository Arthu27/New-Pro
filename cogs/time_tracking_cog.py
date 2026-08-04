"""
Time Tracking Cog
Отслеживание времени cog'u
"""
import discord 
from discord .ext import commands 
from discord import app_commands 
from datetime import datetime ,timedelta 
from services .time_tracking import time_tracker ,pomodoro_timer 

from logger import get_logger 
log =get_logger ("time_tracking_cog")



class TimeTrackingCog (commands .Cog ):
    """Отслеживание времени cog'u"""

    def __init__ (self ,bot ):
        self .bot =bot 

    @app_commands .command (name ='time-start',description ='Запустить таймер')
    @app_commands .describe (description ='Описание таймера')
    async def time_start (self ,interaction :discord .Interaction ,
    description :str ='Чalышma'):
        """Запустить таймер"""
        # Проверить, есть ли уже активный таймер
        active_entry =time_tracker .get_active_entry (interaction .user .id )

        if active_entry :
            await interaction .response .send_message (
            f"⏱ Zaten активный bir zamanlayыcыnыz есть! Начат: {active_entry['start_time'][:16]}",
            ephemeral =True 
            )
            return 

            # Запустить таймер
        entry =time_tracker .start_timer (
        user_id =interaction .user .id ,
        description =description 
        )

        # Embed создать
        embed =discord .Embed (
        title ="⏱ Таймер запущен",
        description =f"**Описание:** {description}\n**Начало:** {entry['start_time'][:16]}",
        color =discord .Color .green (),
        timestamp =datetime .now ()
        )

        await interaction .response .send_message (embed =embed )

    @app_commands .command (name ='time-stop',description ='Остановить таймер')
    async def time_stop (self ,interaction :discord .Interaction ):
        """Zamanlayыcы остановить"""
        # Zamanlayыcы остановить
        entry =time_tracker .stop_timer (interaction .user .id )

        if not entry :
            await interaction .response .send_message (
            "❌ У вас нет активного таймера!",
            ephemeral =True 
            )
            return 

            # Sюre hesapla
        duration =datetime .fromisoformat (entry ['end_time'])-datetime .fromisoformat (entry ['start_time'])
        hours =int (duration .total_seconds ()/3600 )
        minutes =int ((duration .total_seconds ()%3600 )/60 )

        # Embed создать
        embed =discord .Embed (
        title ="⏱ Таймер остановлен",
        description =f"**Описание:** {entry['description']}\n**Длительность:** {hours} ч {minutes} мин",
        color =discord .Color .red (),
        timestamp =datetime .now ()
        )

        await interaction .response .send_message (embed =embed )

    @app_commands .command (name ='time-report',description ='Показать ваш отчёт по времени')
    @app_commands .describe (days ='Gюn sayыsы (varsayыlan: 7)')
    async def time_report (self ,interaction :discord .Interaction ,days :int =7 ):
        """Zaman raporunuzu gёrюntюleyin"""
        # Rapor al
        report =time_tracker .get_user_report (interaction .user .id ,days =days )

        # Embed создать
        embed =discord .Embed (
        title =f"📊 Отчёт по времени ({days} дн.)",
        color =discord .Color .blue (),
        timestamp =datetime .now ()
        )

        embed .add_field (name ="⏱ Общее время",value =f"{report['total_hours']:.2f} время",inline =True )
        embed .add_field (name =" Всего Giriш",value =str (report ['total_entries']),inline =True )
        embed .add_field (name ="📈 Среднее в день",value =f"{report['avg_hours_per_day']:.2f}  ч/день",inline =True )

        # Gюnlюk breakdown
        if report ['daily_breakdown']:
            daily_text ="\n".join ([
            f"• {day}: {hours:.2f} время"
            for day ,hours in list (report ['daily_breakdown'].items ())[:7 ]
            ])
            embed .add_field (name ="Gюnlюk Breakdown",value =daily_text ,inline =False )

        await interaction .response .send_message (embed =embed )

    @app_commands .command (name ='pomodoro',description ='Pomodoro timer запустить')
    @app_commands .describe (work_minutes ='Чalышma sюresi (varsayыlan: 25)',
    break_minutes ='Mola sюresi (varsayыlan: 5)')
    async def pomodoro (self ,interaction :discord .Interaction ,
    work_minutes :int =25 ,break_minutes :int =5 ):
        """Pomodoro timer запустить"""
        # Pomodoro запустить
        session =pomodoro_timer .start_session (
        user_id =interaction .user .id ,
        work_minutes =work_minutes ,
        break_minutes =break_minutes 
        )

        # Embed создать
        embed =discord .Embed (
        title =" Pomodoro Baшlatыldы",
        description =f"**Чalышma Sюresi:** {work_minutes} dakika\n**Mola Sюresi:** {break_minutes} dakika\n\nЧalышmaya baшlayыn!",
        color =discord .Color .red (),
        timestamp =datetime .now ()
        )

        await interaction .response .send_message (embed =embed )

    @app_commands .command (name ='pomodoro-complete',description ='Pomodoro\'yu готовоla')
    async def pomodoro_complete (self ,interaction :discord .Interaction ):
        """Pomodoro'yu готовоla"""
        # Pomodoro готовоla
        session =pomodoro_timer .complete_pomodoro (interaction .user .id )

        if not session :
            await interaction .response .send_message (
            " Активный pomodoro нет!",
            ephemeral =True 
            )
            return 

            # Иstatistikler al
        stats =pomodoro_timer .get_user_stats (interaction .user .id )

        # Embed создать
        embed =discord .Embed (
        title =" Pomodoro Готовоlandы!",
        description =f"**Tebrikler!** Bir pomodoro более готовоladыnыz!",
        color =discord .Color .green (),
        timestamp =datetime .now ()
        )

        embed .add_field (name =" Всего Pomodoro",value =str (stats ['total_pomodoros']),inline =True )
        embed .add_field (name ="⏱ Всего Sюre",value =f"{stats['total_hours']:.2f} время",inline =True )

        await interaction .response .send_message (embed =embed )

    @app_commands .command (name ='pomodoro-stats',description ='Pomodoro статистикаlerinizi gёrюntюleyin')
    async def pomodoro_stats (self ,interaction :discord .Interaction ):
        """Pomodoro статистикаlerinizi gёrюntюleyin"""
        # Иstatistikler al
        stats =pomodoro_timer .get_user_stats (interaction .user .id )

        # Embed создать
        embed =discord .Embed (
        title =" Pomodoro Иstatistikleri",
        color =discord .Color .red (),
        timestamp =datetime .now ()
        )

        embed .add_field (name =" Всего Pomodoro",value =str (stats ['total_pomodoros']),inline =True )
        embed .add_field (name ="⏱ Всего Sюre",value =f"{stats['total_hours']:.2f} время",inline =True )
        embed .add_field (name =" Gюnlюk Центрlama",value =f"{stats['avg_per_day']:.2f}",inline =True )

        await interaction .response .send_message (embed =embed )

    @commands .Cog .listener ()
    async def on_ready (self ):
        """Bot hazыr olduгunda"""
        log .info (f" TimeTrackingCog loaded")


async def setup (bot ):
    await bot .add_cog (TimeTrackingCog (bot ))
