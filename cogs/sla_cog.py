"""
SLA Cog
Менеджер SLA-политик
"""

import discord 
from discord .ext import commands 
from discord import app_commands 
from datetime import datetime 
from services .sla_management import sla_manager ,sla_calculator ,sla_breach_detector 

from logger import get_logger 
log =get_logger ("sla_cog")



class SLACog (commands .Cog ):
    """Менеджер SLA-политик"""

    def __init__ (self ,bot ):
        self .bot =bot 

    @app_commands .command (name ='sla-info',description ='Показать информацию об SLA')
    @app_commands .describe (policy_id ='SLA policy ID (opsiyonel)')
    async def sla_info (self ,interaction :discord .Interaction ,policy_id :str =None ):
        """Показать информацию об SLA"""
        if policy_id :
        # Belirli policy
            policy =sla_manager .get_policy (policy_id )

            if not policy :
                await interaction .response .send_message (
                " SLA политика не найдена!",
                ephemeral =True 
                )
                return 

                # Embed создать
            embed =discord .Embed (
            title =f" SLA Policy: {policy.name}",
            description =policy .description ,
            color =discord .Color .blue (),
            timestamp =datetime .now ()
            )

            # Response time'lar
            if policy .response_times :
                response_text ="\n".join ([
                f"• {priority}: {time} мин"
                for priority ,time in policy .response_times .items ()
                ])
                embed .add_field (name ="Response Time",value =response_text ,inline =False )

                # Resolution time'lar
            if policy .resolution_times :
                resolution_text ="\n".join ([
                f"• {priority}: {time} мин"
                for priority ,time in policy .resolution_times .items ()
                ])
                embed .add_field (name ="⏱ Время решения",value =resolution_text ,inline =False )

            await interaction .response .send_message (embed =embed )
        else :
        # Все политики
            policies =sla_manager .get_all_policies ()

            if not policies :
                await interaction .response .send_message (
                " SLA политика не найдена!",
                ephemeral =True 
                )
                return 

                # Embed создать
            embed =discord .Embed (
            title =" SLA Policies",
            description =f"Всего {len(policies)} SLA policy",
            color =discord .Color .blue (),
            timestamp =datetime .now ()
            )

            # Policy listesi
            for policy in policies [:10 ]:
                embed .add_field (
                name =f"{policy.name}",
                value =f"{policy.description}\nID: {policy.policy_id}",
                inline =False 
                )

            await interaction .response .send_message (embed =embed )

    @app_commands .command (name ='sla-status',description ='Просмотр статуса SLA тикетов')
    @app_commands .describe (ticket_id ='Ticket ID')
    async def sla_status (self ,interaction :discord .Interaction ,ticket_id :str ):
        """Просмотр статуса SLA тикетов"""
        from services .ticket_system import ticket_manager 

        # Ticket al
        ticket =ticket_manager .get_ticket (ticket_id )

        if not ticket :
            await interaction .response .send_message (
            " Тикет не найден!",
            ephemeral =True 
            )
            return 

            # SLA hesapla
        sla_info =sla_calculator .calculate_sla (ticket )

        # Embed создать
        embed =discord .Embed (
        title =f" SLA Status: {ticket_id}",
        color =discord .Color .blue (),
        timestamp =datetime .now ()
        )

        embed .add_field (name ="Policy",value =sla_info ['policy_name'],inline =True )
        embed .add_field (name ="Priority",value =sla_info ['priority'],inline =True )
        embed .add_field (name ="Status",value =sla_info ['status'],inline =True )

        if sla_info .get ('response_deadline'):
            embed .add_field (name ="Response Deadline",value =sla_info ['response_deadline'][:16 ],inline =True )

        if sla_info .get ('resolution_deadline'):
            embed .add_field (name ="⏰ Срок решения",value =sla_info ['resolution_deadline'][:16 ],inline =True )

        if sla_info .get ('time_remaining'):
            embed .add_field (name ="Time Remaining",value =sla_info ['time_remaining'],inline =True )

        await interaction .response .send_message (embed =embed )

    @app_commands .command (name ='sla-breaches',description ='Просмотр нарушений SLA')
    async def sla_breaches (self ,interaction :discord .Interaction ):
        """Просмотр нарушений SLA"""
        # Иhlaller al
        breaches =sla_breach_detector .get_all_breaches ()

        if not breaches :
            await interaction .response .send_message (
            " Нарушение SLA не найдено!",
            ephemeral =True 
            )
            return 

            # Embed создать
        embed =discord .Embed (
        title =" SLA Breaches",
        description =f"Всего {len(breaches)} ihlal",
        color =discord .Color .red (),
        timestamp =datetime .now ()
        )

        # Иhlal listesi
        for breach in breaches [:10 ]:
            embed .add_field (
            name =f"{breach['ticket_id']} - {breach['type']}",
            value =f"Deadline: {breach['deadline'][:16]}\nBreach: {breach['breached_at'][:16]}",
            inline =False 
            )

        await interaction .response .send_message (embed =embed )

    @app_commands .command (name ='sla-create',description ='Создать SLA политику')
    @app_commands .describe (name ='Название политики',description ='Описание политики')
    @app_commands .checks .has_permissions (administrator =True )
    async def sla_create (self ,interaction :discord .Interaction ,
    name :str ,description :str ):
        """Создать SLA политику"""
        # Policy создать
        policy =sla_manager .create_policy (name ,description )

        # Embed создать
        embed =discord .Embed (
        title =" SLA Policy Создано",
        description =f"**Название:** {name}\n**Описание:** {description}\n**ID:** {policy.policy_id}",
        color =discord .Color .green (),
        timestamp =datetime .now ()
        )

        await interaction .response .send_message (embed =embed )

    @commands .Cog .listener ()
    async def on_ready (self ):
        """Бот готов"""
        log .info (" SLACog loaded")


async def setup (bot ):
    await bot .add_cog (SLACog (bot ))
