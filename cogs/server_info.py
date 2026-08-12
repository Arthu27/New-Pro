"""Server Info — обученные ответы о сервере (FAQ-система)"""

from logger import get_logger

_log = get_logger("server_info")

import discord 
from discord .ext import commands 
from discord import app_commands 
import json 
import os 

DATA_DIR ='data'


def _info_file (guild_id :int )->str :
    return f'{DATA_DIR}/server_info_{guild_id}.json'


def _load_info (guild_id :int )->dict :
    path =_info_file (guild_id )
    if os .path .exists (path ):
        try :
            with open (path ,'r',encoding ='utf-8')as f :
                return json .load (f )
        except Exception as _ex:
            _log.debug("_load_info(): подавлено: %s", _ex)
    return {}


def _save_info (guild_id :int ,data :dict ):
    os .makedirs (DATA_DIR ,exist_ok =True )
    with open (_info_file (guild_id ),'w',encoding ='utf-8')as f :
        json .dump (data ,f ,ensure_ascii =False ,indent =2 )


def get_sunucu_context (guild_id :int )->str :
    """Создать текст информации о сервере для AI"""
    info =_load_info (guild_id )
    if not info :
        return ''

    lines =['=== СЕРВЕР ИНФОРМАЦИЯ ===']

    if info .get ('о'):
        lines .append (f'О сервере: {info["о"]}')
    if info .get ('правила'):
        lines .append (f'Правила: {info["правила"]}')
    if info .get ('yetkili_olmak'):
        lines .append (f'Как стать модератором: {info["yetkili_olmak"]}')
    if info .get ('приватные_данные'):
        for k ,v in info ['приватные_данные'].items ():
            lines .append (f'{k}: {v}')

    return '\n'.join (lines )


class ServerModal (discord .ui .Modal ):
    def __init__ (self ,field :str ,title :str ,guild_id :int ):
        super ().__init__ (title =title )
        self .field =field 
        self .guild_id =guild_id 
        self .input_text =discord .ui .TextInput (
        label ='Информация',
        style =discord .TextStyle .paragraph ,
        placeholder ='Пишите здесь...',
        max_length =1000 ,
        required =True 
        )
        self .add_item (self .input_text )

    async def on_submit (self ,interaction :discord .Interaction ):
        info =_load_info (self .guild_id )
        info [self .field ]=self .input_text .value .strip ()
        _save_info (self .guild_id ,info )
        await interaction .response .send_message (
        f'✅ **{self.title}** сохранено!',ephemeral =True 
        )


class ServerInfoView (discord .ui .View ):
    def __init__ (self ,guild_id :int ):
        super ().__init__ (timeout =None )
        self .guild_id =guild_id 

    @discord .ui .button (label ='О сервере',style =discord .ButtonStyle .primary ,row =0 )
    async def о (self ,interaction :discord .Interaction ,button :discord .ui .Button ):
        if not interaction .user .guild_permissions .administrator :
            await interaction .response .send_message ('❌ Нужны права администратора.',ephemeral =True )
            return 
        await interaction .response .send_modal (
        ServerModal ('о','Информация о сервере',self .guild_id )
        )

    @discord .ui .button (label =' Правила',style =discord .ButtonStyle .primary ,row =0 )
    async def правила (self ,interaction :discord .Interaction ,button :discord .ui .Button ):
        if not interaction .user .guild_permissions .administrator :
            await interaction .response .send_message ('❌ Нужны права администратора.',ephemeral =True )
            return 
        await interaction .response .send_modal (
        ServerModal ('правила','Правила сервера',self .guild_id )
        )

    @discord .ui .button (label ='Как стать модератором',style =discord .ButtonStyle .primary ,row =0 )
    async def администратор (self ,interaction :discord .Interaction ,button :discord .ui .Button ):
        if not interaction .user .guild_permissions .administrator :
            await interaction .response .send_message ('❌ Нужны права администратора.',ephemeral =True )
            return 
        await interaction .response .send_modal (
        ServerModal ('yetkili_olmak','Как стать модератором',self .guild_id )
        )

    @discord .ui .button (label ='Добавить информацию',style =discord .ButtonStyle .secondary ,row =1 )
    async def ozel_add (self ,interaction :discord .Interaction ,button :discord .ui .Button ):
        if not interaction .user .guild_permissions .administrator :
            await interaction .response .send_message ('❌ Нужны права администратора.',ephemeral =True )
            return 
        await interaction .response .send_modal (OzelBilgiModal (self .guild_id ))

    @discord .ui .button (label =' Текущая информация',style =discord .ButtonStyle .secondary ,row =1 )
    async def goster (self ,interaction :discord .Interaction ,button :discord .ui .Button ):
        info =_load_info (interaction .guild .id )
        if not info :
            await interaction .response .send_message ('Информация еще не введена.',ephemeral =True )
            return 

        embed =discord .Embed (title =' Информация о сервере',color =0x5865F2 )
        if interaction .guild .icon :
            embed .set_thumbnail (url =interaction .guild .icon .url )

        if info .get ('о'):
            embed .add_field (name =' О',value =info ['о'][:500 ],inline =False )
        if info .get ('правила'):
            embed .add_field (name =' Правила',value =info ['правила'][:500 ],inline =False )
        if info .get ('yetkili_olmak'):
            embed .add_field (name ='🛡 Как стать модератором',value =info ['yetkili_olmak'][:500 ],inline =False )
        if info .get ('приватные_данные'):
            for k ,v in list (info ['приватные_данные'].items ())[:5 ]:
                embed .add_field (name =k ,value =str (v )[:200 ],inline =True )

        await interaction .response .send_message (embed =embed ,ephemeral =True )

    @discord .ui .button (label ='Очистить',style =discord .ButtonStyle .danger ,row =1 )
    async def clear (self ,interaction :discord .Interaction ,button :discord .ui .Button ):
        if not interaction .user .guild_permissions .administrator :
            await interaction .response .send_message ('❌ Нужны права администратора.',ephemeral =True )
            return 
        _save_info (interaction .guild .id ,{})
        await interaction .response .send_message ('🗑 Вся информация о сервере очищена.',ephemeral =True )


class OzelBilgiModal (discord .ui .Modal ,title ='Добавлено информацию'):
    def __init__ (self ,guild_id :int ):
        super ().__init__ ()
        self .guild_id =guild_id 
        self .heading =discord .ui .TextInput (
        label ='Заголовок',
        placeholder ='напр.: Ссылка Discord, День событий...',
        max_length =50 
        )
        self .body =discord .ui .TextInput (
        label ='Содержимое',
        style =discord .TextStyle .paragraph ,
        placeholder ='Содержимое информации...',
        max_length =500 
        )
        self .add_item (self .heading )
        self .add_item (self .body )

    async def on_submit (self ,interaction :discord .Interaction ):
        info =_load_info (self .guild_id )
        if 'приватные_данные'not in info :
            info ['приватные_данные']={}
        info ['приватные_данные'][self .heading .value .strip ()]=self .body .value .strip ()
        _save_info (self .guild_id ,info )
        await interaction .response .send_message (
        f' **{self.heading.value}** сохранено!',ephemeral =True 
        )


class ServerInfo (commands .Cog ):
    def __init__ (self ,bot ):
        self .bot =bot 

    @commands .command (name ='server-info')
    @commands .has_permissions (administrator =True )
    async def sunucu_info_panel (self ,ctx ):
        """Server info control paneli: !server-info"""
        embed =discord .Embed (
        title =' Управление информацией о сервере',
        color =0x5865F2 ,
        description =(
        '> Научи бота информации о сервере.\n'
        '> Эта информация используется в AI-чате.\n\n'
        '** О сервере** — цель и тематика сервера\n'
        '** Правила** — Правила сервера\n'
        '** Как стать модератором** — как получить роль модератора\n'
        '** Дополнительная информация** — любая другая информация\n'
        '** Текущая информация** — просмотр сохранённой информации'
        )
        )
        if ctx .guild .icon :
            embed .set_thumbnail (url =ctx .guild .icon .url )
        if ctx .guild .banner :
            embed .set_image (url =ctx .guild .banner .url )
        embed .set_footer (
        text =f'{ctx.guild.name} · Система информации о сервере',
        icon_url =ctx .guild .icon .url if ctx .guild .icon else None 
        )
        await ctx .send (embed =embed ,view =ServerInfoView (ctx .guild .id ))


async def setup (bot ):
    await bot .add_cog (ServerInfo (bot ))
