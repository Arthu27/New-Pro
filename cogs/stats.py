import discord 
from discord .ext import commands 
from discord import app_commands 
import json 
import os 
from datetime import datetime 
from collections import defaultdict 

class Stats (commands .Cog ):
    def __init__ (self ,bot ):
        self .bot =bot 
        self .stats_file ="data/mod_stats.json"
        self .load_stats ()

    def load_stats (self ):
        os .makedirs ("data",exist_ok =True )
        if os .path .exists (self .stats_file ):
            with open (self .stats_file ,"r")as f :
                self .stats =json .load (f )
        else :
            self .stats ={}

    def save_stats (self ):
        with open (self .stats_file ,"w")as f :
            json .dump (self .stats ,f ,indent =2 )

    def add_action (self ,guild_id ,mod_id ,action ):
        guild_id =str (guild_id )
        mod_id =str (mod_id )

        if guild_id not in self .stats :
            self .stats [guild_id ]={}
        if mod_id not in self .stats [guild_id ]:
            self .stats [guild_id ][mod_id ]=defaultdict (int )

        self .stats [guild_id ][mod_id ][action ]=self .stats [guild_id ][mod_id ].get (action ,0 )+1 
        self .save_stats ()

    @commands .Cog .listener ()
    async def on_member_ban (self ,guild ,user ):
        async for entry in guild .audit_logs (limit =1 ,action =discord .AuditLogAction .ban ):
            if entry .target .id ==user .id :
                self .add_action (guild .id ,entry .user .id ,"ban")
                break 

    @commands .Cog .listener ()
    async def on_member_remove (self ,member ):
        async for entry in member .guild .audit_logs (limit =1 ,action =discord .AuditLogAction .kick ):
            if entry .target .id ==member .id :
                self .add_action (member .guild .id ,entry .user .id ,"kick")
                break 

    @app_commands .command (name ="modstats",description ="Показать статистику модераторов")
    @app_commands .checks .has_permissions (moderate_members =True )
    async def modstats (self ,interaction :discord .Interaction ,moderator :discord .Member =None ):
        guild_id =str (interaction .guild .id )

        if moderator :
            mod_id =str (moderator .id )
            stats =self .stats .get (guild_id ,{}).get (mod_id ,{})

            if not stats :
                await interaction .response .send_message (f"{moderator.mention} еще не выполнял действий модерации.",ephemeral =True )
                return 

            e =discord .Embed (title =f" {moderator.name} - Статистика",color =discord .Color .blue ())
            e .set_thumbnail (url =moderator .display_avatar .url )

            total =sum (stats .values ())
            for action ,count in stats .items ():
                e .add_field (name =action .capitalize (),value =str (count ),inline =True )
            e .set_footer (text =f"Всего: {total} действие")

            await interaction .response .send_message (embed =e ,ephemeral =True )
        else :
        # Все модераторы
            guild_stats =self .stats .get (guild_id ,{})

            if not guild_stats :
                await interaction .response .send_message ("Пока статистика нет.",ephemeral =True )
                return 

            e =discord .Embed (title =" Модератор Статистика",color =discord .Color .blue ())

            sorted_mods =sorted (
            guild_stats .items (),
            key =lambda x :sum (x [1 ].values ()),
            reverse =True 
            )[:10 ]

            for mod_id ,stats in sorted_mods :
                try :
                    mod =await self .bot .fetch_user (int (mod_id ))
                    total =sum (stats .values ())
                    e .add_field (
                    name =str (mod ),
                    value =f"Всего: {total} действие",
                    inline =False 
                    )
                except Exception :
                    pass 

            await interaction .response .send_message (embed =e ,ephemeral =True )

    @app_commands .command (name ="activemods",description ="Показать самых активных модераторов")
    @app_commands .checks .has_permissions (moderate_members =True )
    async def activemods (self ,interaction :discord .Interaction ):
        guild_id =str (interaction .guild .id )
        guild_stats =self .stats .get (guild_id ,{})

        if not guild_stats :
            await interaction .response .send_message ("Пока статистика нет.",ephemeral =True )
            return 

        e =discord .Embed (
        title =" EN АКТИВЕН МОДЕРАТОРЫ",
        description ="\n Liderlik Tablosu \n",
        color =0xF1C40F 
        )

        sorted_mods =sorted (
        guild_stats .items (),
        key =lambda x :sum (x [1 ].values ()),
        reverse =True 
        )[:10 ]

        medals =["","",""]
        for i ,(mod_id ,stats )in enumerate (sorted_mods ,1 ):
            try :
                mod =await self .bot .fetch_user (int (mod_id ))
                total =sum (stats .values ())
                medal =medals [i -1 ]if i <=3 else f"#{i}"

                actions =", ".join ([f"{k}: {v}"for k ,v in stats .items ()])
                e .add_field (
                name =f"{medal} {mod.name}",
                value =f"```yaml\nВсего: {total} действие\n{actions}\n```",
                inline =False 
                )
            except Exception :
                pass 

        e .set_footer (text ="Moderasyon Статистика",icon_url =interaction .guild .icon .url if interaction .guild .icon else None )
        await interaction .response .send_message (embed =e ,ephemeral =True )

async def setup (bot ):
    await bot .add_cog (Stats (bot ),guilds =[discord .Object (id =1421244140359909513 ),discord .Object (id =1107038411895881788 ),discord .Object (id =1498837105915330562 )])
