"""
Report Cog
Reporting cog'u
"""

import discord 
from discord .ext import commands 
from discord import app_commands 
from datetime import datetime ,timedelta 
from services .advanced_reporting import report_builder ,analytics_engine 

from logger import get_logger 
log =get_logger ("report_cog")



class ReportCog (commands .Cog ):
    """Reporting cog'u"""

    def __init__ (self ,bot ):
        self .bot =bot 

    @app_commands .command (name ='report-daily',description ='Создать ежедневный отчёт')
    @app_commands .checks .has_permissions (manage_guild =True )
    async def report_daily (self ,interaction :discord .Interaction ):
        """Создать ежедневный отчёт"""
        # Rapor создать
        report =report_builder .generate_daily_report ()

        # Embed создать
        embed =discord .Embed (
        title =" Daily Report",
        description =f"Дата: {report['date']}",
        color =discord .Color .blue (),
        timestamp =datetime .now ()
        )

        # Иstatistikler
        embed .add_field (name ="Total Tickets",value =str (report ['total_tickets']),inline =True )
        embed .add_field (name ="Open Tickets",value =str (report ['open_tickets']),inline =True )
        embed .add_field (name ="Closed Tickets",value =str (report ['closed_tickets']),inline =True )

        embed .add_field (name ="Avg Resolution Time",value =f"{report['avg_resolution_time']:.2f}h",inline =True )
        embed .add_field (name ="SLA Compliance",value =f"{report['sla_compliance']:.2f}%",inline =True )
        embed .add_field (name ="Customer Satisfaction",value =f"{report['customer_satisfaction']:.2f}/5",inline =True )

        await interaction .response .send_message (embed =embed )

    @app_commands .command (name ='report-weekly',description ='Создать еженедельный отчёт')
    @app_commands .checks .has_permissions (manage_guild =True )
    async def report_weekly (self ,interaction :discord .Interaction ):
        """Создать еженедельный отчёт"""
        # Rapor создать
        report =report_builder .generate_weekly_report ()

        # Embed создать
        embed =discord .Embed (
        title =" Weekly Report",
        description =f"Неделя: {report['week_start']} - {report['week_end']}",
        color =discord .Color .blue (),
        timestamp =datetime .now ()
        )

        # Иstatistikler
        embed .add_field (name ="Total Tickets",value =str (report ['total_tickets']),inline =True )
        embed .add_field (name ="Open Tickets",value =str (report ['open_tickets']),inline =True )
        embed .add_field (name ="Closed Tickets",value =str (report ['closed_tickets']),inline =True )

        embed .add_field (name ="Avg Resolution Time",value =f"{report['avg_resolution_time']:.2f}h",inline =True )
        embed .add_field (name ="SLA Compliance",value =f"{report['sla_compliance']:.2f}%",inline =True )
        embed .add_field (name ="Customer Satisfaction",value =f"{report['customer_satisfaction']:.2f}/5",inline =True )

        # Gюnlюk breakdown
        if report .get ('daily_breakdown'):
            daily_text ="\n".join ([
            f"• {day}: {tickets} tickets"
            for day ,tickets in report ['daily_breakdown'].items ()
            ])
            embed .add_field (name ="Daily Breakdown",value =daily_text ,inline =False )

        await interaction .response .send_message (embed =embed )

    @app_commands .command (name ='report-custom',description ='Создать специальный отчёт')
    @app_commands .describe (days ='Gюn sayыsы (varsayыlan: 30)',
    report_type ='Rapor tipi (tickets/sla/performance)')
    @app_commands .checks .has_permissions (manage_guild =True )
    async def report_custom (self ,interaction :discord .Interaction ,
    days :int =30 ,report_type :str ='tickets'):
        """Создать специальный отчёт"""
        # Rapor создать
        if report_type =='tickets':
            report =report_builder .generate_custom_report (days =days ,report_type ='tickets')
        elif report_type =='sla':
            report =report_builder .generate_custom_report (days =days ,report_type ='sla')
        elif report_type =='performance':
            report =report_builder .generate_custom_report (days =days ,report_type ='performance')
        else :
            await interaction .response .send_message (
            " Geчersiz rapor tipi! (tickets/sla/performance)",
            ephemeral =True 
            )
            return 

            # Embed создать
        embed =discord .Embed (
        title =f" Custom Report ({report_type})",
        description =f"Period: {report['period_start']} - {report['period_end']}",
        color =discord .Color .blue (),
        timestamp =datetime .now ()
        )

        # Иstatistikler
        for key ,value in report .get ('stats',{}).items ():
            if isinstance (value ,(int ,float )):
                embed .add_field (name =key ,value =str (value ),inline =True )

        await interaction .response .send_message (embed =embed )

    @app_commands .command (name ='report-analytics',description ='Analytics raporunu gёrюntюle')
    async def report_analytics (self ,interaction :discord .Interaction ):
        """Analytics raporunu gёrюntюle"""
        # Analytics al
        analytics =analytics_engine .get_dashboard_analytics ()

        # Embed создать
        embed =discord .Embed (
        title =" Analytics Dashboard",
        color =discord .Color .blue (),
        timestamp =datetime .now ()
        )

        # Иstatistikler
        embed .add_field (name ="Total Tickets",value =str (analytics ['total_tickets']),inline =True )
        embed .add_field (name ="Open Tickets",value =str (analytics ['open_tickets']),inline =True )
        embed .add_field (name ="Closed Tickets",value =str (analytics ['closed_tickets']),inline =True )

        embed .add_field (name ="Avg Resolution Time",value =f"{analytics['avg_resolution_time']:.2f}h",inline =True )
        embed .add_field (name ="SLA Compliance",value =f"{analytics['sla_compliance']:.2f}%",inline =True )
        embed .add_field (name ="Customer Satisfaction",value =f"{analytics['customer_satisfaction']:.2f}/5",inline =True )

        # Top categories
        if analytics .get ('top_categories'):
            categories_text ="\n".join ([
            f"• {cat['category']}: {cat['count']} tickets"
            for cat in analytics ['top_categories'][:5 ]
            ])
            embed .add_field (name ="Top Categories",value =categories_text ,inline =False )

            # Top performers
        if analytics .get ('top_performers'):
            performers_text ="\n".join ([
            f"• {performer['user_name']}: {performer['closed_tickets']} tickets"
            for performer in analytics ['top_performers'][:5 ]
            ])
            embed .add_field (name ="Top Performers",value =performers_text ,inline =False )

        await interaction .response .send_message (embed =embed )

    @commands .Cog .listener ()
    async def on_ready (self ):
        """Bot hazыr olduгunda"""
        log .info (f" ReportCog loaded")


async def setup (bot ):
    await bot .add_cog (ReportCog (bot ))
