"""
Report Cog
Ког отчётности
"""

import discord 
from discord .ext import commands 
from discord import app_commands 
from datetime import datetime ,timedelta 
from services .advanced_reporting import report_builder ,analytics_engine 

from logger import get_logger 
log =get_logger ("report_cog")



class ReportCog (commands .Cog ):
    """Ког отчётности"""

    def __init__ (self ,bot ):
        self .bot =bot 

    @app_commands .command (name ='report-daily',description ='Создать ежедневный отчёт')
    @app_commands .checks .has_permissions (manage_guild =True )
    async def report_daily (self ,interaction :discord .Interaction ):
        """Создать ежедневный отчёт"""
        # Создать отчёт
        report =report_builder .generate_daily_report ()

        # Embed создать
        embed =discord .Embed (
        title ="📅 Ежедневный отчёт",
        description =f"Дата: {report['date']}",
        color =discord .Color .blue (),
        timestamp =datetime .now ()
        )

        # Статистика
        embed .add_field (name ="Всего тикетов",value =str (report ['total_tickets']),inline =True )
        embed .add_field (name ="Открыто тикетов",value =str (report ['open_tickets']),inline =True )
        embed .add_field (name ="Закрыто тикетов",value =str (report ['closed_tickets']),inline =True )

        embed .add_field (name ="⏱ Среднее время решения",value =f"{report['avg_resolution_time']:.2f} ч",inline =True )
        embed .add_field (name ="Соблюдение SLA",value =f"{report['sla_compliance']:.2f}%",inline =True )
        embed .add_field (name ="⭐ Удовлетворённость",value =f"{report['customer_satisfaction']:.2f}/5",inline =True )

        await interaction .response .send_message (embed =embed )

    @app_commands .command (name ='report-weekly',description ='Создать еженедельный отчёт')
    @app_commands .checks .has_permissions (manage_guild =True )
    async def report_weekly (self ,interaction :discord .Interaction ):
        """Создать еженедельный отчёт"""
        # Создать отчёт
        report =report_builder .generate_weekly_report ()

        # Embed создать
        embed =discord .Embed (
        title ="📅 Еженедельный отчёт",
        description =f"Неделя: {report['week_start']} - {report['week_end']}",
        color =discord .Color .blue (),
        timestamp =datetime .now ()
        )

        # Статистика
        embed .add_field (name ="Всего тикетов",value =str (report ['total_tickets']),inline =True )
        embed .add_field (name ="Открыто тикетов",value =str (report ['open_tickets']),inline =True )
        embed .add_field (name ="Закрыто тикетов",value =str (report ['closed_tickets']),inline =True )

        embed .add_field (name ="⏱ Среднее время решения",value =f"{report['avg_resolution_time']:.2f} ч",inline =True )
        embed .add_field (name ="Соблюдение SLA",value =f"{report['sla_compliance']:.2f}%",inline =True )
        embed .add_field (name ="⭐ Удовлетворённость",value =f"{report['customer_satisfaction']:.2f}/5",inline =True )

        # Разбивка по дням
        if report .get ('daily_breakdown'):
            daily_text ="\n".join ([
            f"• {day}: {tickets} тикетов"
            for day ,tickets in report ['daily_breakdown'].items ()
            ])
            embed .add_field (name ="По дням",value =daily_text ,inline =False )

        await interaction .response .send_message (embed =embed )

    @app_commands .command (name ='report-custom',description ='Создать специальный отчёт')
    @app_commands .describe (days ='Количество дней (по умолчанию: 30)',
    report_type ='Тип отчёта (tickets/sla/performance)')
    @app_commands .checks .has_permissions (manage_guild =True )
    async def report_custom (self ,interaction :discord .Interaction ,
    days :int =30 ,report_type :str ='tickets'):
        """Создать специальный отчёт"""
        # Создать отчёт
        if report_type =='tickets':
            report =report_builder .generate_custom_report (days =days ,report_type ='tickets')
        elif report_type =='sla':
            report =report_builder .generate_custom_report (days =days ,report_type ='sla')
        elif report_type =='performance':
            report =report_builder .generate_custom_report (days =days ,report_type ='performance')
        else :
            await interaction .response .send_message (
            " Неверный тип отчёта! (tickets/sla/performance)",
            ephemeral =True 
            )
            return 

            # Embed создать
        embed =discord .Embed (
        title =f"📋 Специальный отчёт ({report_type})",
        description =f"Период: {report['period_start']} — {report['period_end']}",
        color =discord .Color .blue (),
        timestamp =datetime .now ()
        )

        # Статистика
        for key ,value in report .get ('stats',{}).items ():
            if isinstance (value ,(int ,float )):
                embed .add_field (name =key ,value =str (value ),inline =True )

        await interaction .response .send_message (embed =embed )

    @app_commands .command (name ='report-analytics',description ='Просмотр аналитического отчёта')
    async def report_analytics (self ,interaction :discord .Interaction ):
        """Просмотр аналитического отчёта"""
        # Получить аналитику
        analytics =analytics_engine .get_dashboard_analytics ()

        # Embed создать
        embed =discord .Embed (
        title ="📊 Панель аналитики",
        color =discord .Color .blue (),
        timestamp =datetime .now ()
        )

        # Статистика
        embed .add_field (name ="Всего тикетов",value =str (analytics ['total_tickets']),inline =True )
        embed .add_field (name ="Открыто тикетов",value =str (analytics ['open_tickets']),inline =True )
        embed .add_field (name ="Закрыто тикетов",value =str (analytics ['closed_tickets']),inline =True )

        embed .add_field (name ="⏱ Среднее время решения",value =f"{analytics['avg_resolution_time']:.2f} ч",inline =True )
        embed .add_field (name ="Соблюдение SLA",value =f"{analytics['sla_compliance']:.2f}%",inline =True )
        embed .add_field (name ="⭐ Удовлетворённость",value =f"{analytics['customer_satisfaction']:.2f}/5",inline =True )

        # Топ категорий
        if analytics .get ('top_categories'):
            categories_text ="\n".join ([
            f"• {cat['category']}: {cat['count']} тикетов"
            for cat in analytics ['top_categories'][:5 ]
            ])
            embed .add_field (name ="Топ категорий",value =categories_text ,inline =False )

            # Лучшие сотрудники
        if analytics .get ('top_performers'):
            performers_text ="\n".join ([
            f"• {performer['user_name']}: {performer['closed_tickets']} закрыто"
            for performer in analytics ['top_performers'][:5 ]
            ])
            embed .add_field (name ="Лучшие сотрудники",value =performers_text ,inline =False )

        await interaction .response .send_message (embed =embed )

    @commands .Cog .listener ()
    async def on_ready (self ):
        """Бот готов"""
        log .info (" ReportCog loaded")


async def setup (bot ):
    await bot .add_cog (ReportCog (bot ))
