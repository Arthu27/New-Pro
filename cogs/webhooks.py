"""Webhook controli"""
import discord 
from discord .ext import commands 
from discord import app_commands 
import json ,os 
from config import Config 

class Webhooks (commands .Cog ):
    def __init__ (self ,bot ):
        self .bot =bot 

    def _file (self ,guild_id ):
        return f'data/webhooks_{guild_id}.json'

    def _load (self ,guild_id ):
        f =self ._file (guild_id )
        if not os .path .exists (f ):return {}
        with open (f ,'r',encoding ='utf-8')as fp :return json .load (fp )

    def _save (self ,guild_id ,data ):
        os .makedirs ('data',exist_ok =True )
        with open (self ._file (guild_id ),'w',encoding ='utf-8')as fp :
            json .dump (data ,fp ,indent =2 ,ensure_ascii =False )

    @app_commands .command (name ='webhook',description ='Действия с вебхуками: создать, отправить, список, удалить')
    @app_commands .choices (action =[
    app_commands .Choice (name ="создать",value ="create"),
    app_commands .Choice (name ="отправить",value ="send"),
    app_commands .Choice (name ="список",value ="list"),
    app_commands .Choice (name ="удалить",value ="delete")
    ])
    @app_commands .checks .has_permissions (manage_webhooks =True )
    async def webhook_action (self ,interaction :discord .Interaction ,action :str ,
    channel :discord .TextChannel =None ,isim :str =None ,
    webhook_id :str =None ,message :str =None ,kullanici_adi :str =None ):
        if action =="create":
            if not channel or not isim :
                await interaction .response .send_message ('❌ Укажите канал и имя!',ephemeral =True )
                return 
            try :
                wh =await channel .create_webhook (name =isim )
            except discord .Forbidden :
                await interaction .response .send_message ('❌ Нет прав на создание вебхука!',ephemeral =True )
                return 

            data =self ._load (interaction .guild_id )
            data [str (wh .id )]={
            'id':str (wh .id ),'name':isim ,
            'url':wh .url ,'channel_id':str (channel .id ),
            'channel_name':channel .name 
            }
            self ._save (interaction .guild_id ,data )

            embed =discord .Embed (title ='✅ Вебхук создан',color =0x2ECC71 )
            embed .add_field (name ='Имя',value =isim )
            embed .add_field (name ='Канал',value =channel .mention )
            embed .add_field (name ='ID',value =str (wh .id ))
            await interaction .response .send_message (embed =embed ,ephemeral =True )

        elif action =="send":
            if not webhook_id or not message :
                await interaction .response .send_message ('❌ Укажите ID вебхука и сообщение!',ephemeral =True )
                return 

            data =self ._load (interaction .guild_id )
            if webhook_id not in data :
                await interaction .response .send_message ('❌ Вебхук не найден!',ephemeral =True )
                return 

            wh_data =data [webhook_id ]
            try :
                import aiohttp 
                async with aiohttp .ClientSession ()as session :
                    wh =discord .Webhook .from_url (wh_data ['url'],session =session )
                    await wh .send (
                    content =message ,
                    username =kullanici_adi or wh_data ['name']
                    )
            except Exception as e :
            # Если aiohttp нет — попробовать штатным методом discord.py
                try :
                    channel =interaction .guild .get_channel (int (wh_data ['channel_id']))
                    webhooks =await channel .webhooks ()
                    wh =discord .utils .get (webhooks ,id =int (webhook_id ))
                    if wh :
                        await wh .send (content =message ,username =kullanici_adi or wh_data ['name'])
                except Exception as e2 :
                    await interaction .response .send_message (f' Ошибка: {e2}',ephemeral =True )
                    return 

            await interaction .response .send_message ('📨 Сообщение отправлено!',ephemeral =True )

        elif action =="list":
            data =self ._load (interaction .guild_id )
            if not data :
                await interaction .response .send_message ('ℹ️ Нет сохранённых вебхуков!',ephemeral =True )
                return 

            embed =discord .Embed (title ='🔗 Вебхуки',color =0x3498DB )
            for wid ,wh in data .items ():
                embed .add_field (
                name =wh ['name'],
                value =f'Канал: #{wh["channel_name"]}\nID: `{wid}`',
                inline =False 
                )
            await interaction .response .send_message (embed =embed ,ephemeral =True )

        elif action =="delete":
            if not webhook_id :
                await interaction .response .send_message ('❌ Укажите ID вебхука!',ephemeral =True )
                return 

            data =self ._load (interaction .guild_id )
            if webhook_id not in data :
                await interaction .response .send_message ('❌ Вебхук не найден!',ephemeral =True )
                return 

                # Discord'dan da удалить
            try :
                channel =interaction .guild .get_channel (int (data [webhook_id ]['channel_id']))
                if channel :
                    webhooks =await channel .webhooks ()
                    wh =discord .utils .get (webhooks ,id =int (webhook_id ))
                    if wh :
                        await wh .delete ()
            except Exception :
                pass 

            name =data [webhook_id ]['name']
            del data [webhook_id ]
            self ._save (interaction .guild_id ,data )
            await interaction .response .send_message (f'🗑 Вебхук **{name}** удалён!')

async def setup (bot ):
    await bot .add_cog (Webhooks (bot ),guilds =Config .guild_objects ())