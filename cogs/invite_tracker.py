import discord 
from discord .ext import commands 
from discord import app_commands 
import json 
import os 
from datetime import datetime 
from cogs .embed_utils import _divider ,now_ts 
from config import Config 

class InviteTracker (commands .Cog ):
    def __init__ (self ,bot ):
        self .bot =bot 
        self .invite_cache ={}

    async def cache_invites (self ,guild ):
        try :
            invites =await guild .invites ()
            self .invite_cache [guild .id ]={inv .code :inv .uses for inv in invites }
        except Exception :
            pass 

    @commands .Cog .listener ()
    async def on_ready (self ):
        for guild in self .bot .guilds :
            await self .cache_invites (guild )

    @commands .Cog .listener ()
    async def on_invite_create (self ,invite ):
        if invite .guild .id not in self .invite_cache :
            self .invite_cache [invite .guild .id ]={}
        self .invite_cache [invite .guild .id ][invite .code ]=invite .uses 

    @commands .Cog .listener ()
    async def on_invite_delete (self ,invite ):
        if invite .guild .id in self .invite_cache :
            self .invite_cache [invite .guild .id ].pop (invite .code ,None )

    @commands .Cog .listener ()
    async def on_member_join (self ,member ):
        guild =member .guild 
        try :
            new_invites =await guild .invites ()
        except Exception :
            return 
        old_cache =self .invite_cache .get (guild .id ,{})
        inviter =None 
        used_code =None 
        for inv in new_invites :
            old_uses =old_cache .get (inv .code ,0 )
            if inv .uses >old_uses :
                inviter =inv .inviter 
                used_code =inv .code 
                break 
        self .invite_cache [guild .id ]={inv .code :inv .uses for inv in new_invites }
        self ._save_join (guild .id ,member ,inviter ,used_code )

    @commands .Cog .listener ()
    async def on_member_remove (self ,member ):
        self ._save_leave (member .guild .id ,member )

    def _save_join (self ,guild_id ,member ,inviter ,code ):
        os .makedirs ('data',exist_ok =True )
        f =f'data/invite_joins_{guild_id}.json'
        joins =[]
        if os .path .exists (f ):
            with open (f ,'r',encoding ='utf-8')as fp :
                joins =json .load (fp )
        joins .append ({
        'user_id':str (member .id ),'user_name':member .display_name ,
        'inviter_id':str (inviter .id )if inviter else None ,
        'inviter':inviter .display_name if inviter else 'Неизвестно',
        'code':code ,'joined_at':datetime .utcnow ().isoformat ()
        })
        with open (f ,'w',encoding ='utf-8')as fp :
            json .dump (joins [-500 :],fp ,indent =2 ,ensure_ascii =False )
        if inviter :
            self ._update_inviter_count (guild_id ,inviter ,+1 )

    def _save_leave (self ,guild_id ,member ):
        os .makedirs ('data',exist_ok =True )
        f =f'data/invite_leaves_{guild_id}.json'
        leaves =[]
        if os .path .exists (f ):
            with open (f ,'r',encoding ='utf-8')as fp :
                leaves =json .load (fp )
        leaves .append ({
        'user_id':str (member .id ),'user_name':member .display_name ,
        'left_at':datetime .utcnow ().isoformat ()
        })
        with open (f ,'w',encoding ='utf-8')as fp :
            json .dump (leaves [-500 :],fp ,indent =2 ,ensure_ascii =False )

    def _update_inviter_count (self ,guild_id ,inviter ,delta ):
        f =f'data/invite_counts_{guild_id}.json'
        counts ={}
        if os .path .exists (f ):
            with open (f ,'r',encoding ='utf-8')as fp :
                counts =json .load (fp )
        uid =str (inviter .id )
        if uid not in counts :
            counts [uid ]={'name':inviter .display_name ,'total':0 }
        counts [uid ]['name']=inviter .display_name 
        counts [uid ]['total']=max (0 ,counts [uid ].get ('total',0 )+delta )
        with open (f ,'w',encoding ='utf-8')as fp :
            json .dump (counts ,fp ,indent =2 ,ensure_ascii =False )

    @app_commands .command (name ='invites',description ='Показать, сколько человек ты пригласил')
    async def my_invites (self ,interaction :discord .Interaction ):
        f =f'data/invite_counts_{interaction.guild_id}.json'
        if not os .path .exists (f ):
            await interaction .response .send_message (' Пока нет данных о приглашениях!',ephemeral =True )
            return 
        with open (f ,'r',encoding ='utf-8')as fp :
            counts =json .load (fp )
        uid =str (interaction .user .id )
        info =counts .get (uid ,{'total':0 })
        total =info .get ('total',0 )

        e =discord .Embed (title =" Статистика приглашений",color =0x3498DB ,timestamp =datetime .utcnow ())
        e .description =(
        f"```ansi\n\u001b[1;34m DAVET RAPORU\u001b[0m\n```\n{_divider()}"
        )
        e .set_thumbnail (url =interaction .user .display_avatar .url )
        e .add_field (name =" Пользователь",value =interaction .user .mention ,inline =True )
        e .add_field (name =" Всего приглашений",value =f"```{total} человек```",inline =True )
        if total >=10 :
            rank =" Большой"
        elif total >=5 :
            rank ="🎖 Мастер приглашений"
        elif total >=1 :
            rank ="🌱 Новичок приглашений"
        else :
            rank =" Пока нет приглашений"
        e .add_field (name =" Unvan",value =f"```{rank}```",inline =True )
        e .add_field (name ="💡 Подсказка",value ="*Приглашай больше людей и поднимайся в рейтинге!*",inline =False )
        e .set_footer (text =f"Aether • {interaction.guild.name}",icon_url =interaction .guild .icon .url if interaction .guild .icon else None )
        await interaction .response .send_message (embed =e )

    @app_commands .command (name ='invite-ranking',description ='Рейтинг приглашений')
    async def invite_leaderboard (self ,interaction :discord .Interaction ):
        f =f'data/invite_counts_{interaction.guild_id}.json'
        if not os .path .exists (f ):
            await interaction .response .send_message (' Пока нет данных о приглашениях!',ephemeral =True )
            return 
        with open (f ,'r',encoding ='utf-8')as fp :
            counts =json .load (fp )
        sorted_counts =sorted (counts .items (),key =lambda x :x [1 ].get ('total',0 ),reverse =True )[:10 ]

        e =discord .Embed (title =" Рейтинг приглашений",color =0x3498DB ,timestamp =datetime .utcnow ())
        e .description =(
        f"```ansi\n\u001b[1;34m ЛУЧШИЕ ПРИГЛАШАЮЩИЕ\u001b[0m\n```\n{_divider()}"
        )
        medals =['','','']
        for i ,(uid ,info )in enumerate (sorted_counts ,1 ):
            medal =medals [i -1 ]if i <=3 else f'`{i}.`'
            total =info .get ('total',0 )
            bar =""*min (total ,10 )+""*max (0 ,10 -total )
            e .add_field (
            name =f"{medal} {info.get('name', uid)}",
            value =f"`{bar}` **{total}** приглашений",
            inline =False 
            )
        e .set_footer (text =f"Aether • {interaction.guild.name}",icon_url =interaction .guild .icon .url if interaction .guild .icon else None )
        await interaction .response .send_message (embed =e )


async def setup (bot ):
    await bot .add_cog (InviteTracker (bot ),guilds =Config .guild_objects ())
