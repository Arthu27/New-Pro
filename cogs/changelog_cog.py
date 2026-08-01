"""
Changelog Cog
Changelog cog'u
"""

import discord 
from discord .ext import commands 
from discord import app_commands 
from datetime import datetime 
from services .changelog import changelog_manager ,changelog_generator ,ChangeType 

from logger import get_logger 
log =get_logger ("changelog_cog")



class ChangelogCog (commands .Cog ):
    """Changelog cog'u"""

    def __init__ (self ,bot ):
        self .bot =bot 

    @app_commands .command (name ='changelog',description ='Changelog\'u gёrюntюle')
    @app_commands .describe (version ='Versiyon (opsiyonel)')
    async def changelog (self ,interaction :discord .Interaction ,version :str =None ):
        """Changelog'u gёrюntюle"""
        if version :
        # Belirli versiyon
            entries =changelog_manager .get_entries_by_version (version )

            if not entries :
                await interaction .response .send_message (
                f" Versiyon {version} для giriш не найдено!",
                ephemeral =True 
                )
                return 

                # Embed создать
            embed =discord .Embed (
            title =f" Changelog v{version}",
            description =f"Всего {len(entries)} giriш",
            color =discord .Color .blue (),
            timestamp =datetime .now ()
            )

            # Tip'e по grupla
            for entry in entries [:15 ]:
                type_emoji ={
                'added':'',
                'changed':'',
                'fixed':'',
                'removed':'',
                'security':''
                }.get (entry .change_type .value ,'')

                embed .add_field (
                name =f"{type_emoji} {entry.title}",
                value =f"{entry.description}\n[{entry.change_type.value}]",
                inline =False 
                )

            await interaction .response .send_message (embed =embed )
        else :
        # Tюm versiyonlar
            versions =changelog_manager .get_all_versions ()

            if not versions :
                await interaction .response .send_message (
                " Журнал изменений не найден!",
                ephemeral =True 
                )
                return 

                # Embed создать
            embed =discord .Embed (
            title =" Changelog Versions",
            description =f"Всего {len(versions)} versiyon",
            color =discord .Color .blue (),
            timestamp =datetime .now ()
            )

            # Versiyon listesi
            for version in versions [:10 ]:
                entries =changelog_manager .get_entries_by_version (version )
                embed .add_field (
                name =f"v{version}",
                value =f"{len(entries)} giriш\n{entries[0].timestamp[:10] if entries else 'N/A'}",
                inline =True 
                )

            await interaction .response .send_message (embed =embed )

    @app_commands .command (name ='changelog-add',description ='Добавить запись в журнал')
    @app_commands .describe (version ='Versiyon',change_type ='Deгiшiklik tipi (added/changed/fixed/removed/security)',
    title ='Baшlыk',description ='Aчыklama')
    @app_commands .checks .has_permissions (administrator =True )
    async def changelog_add (self ,interaction :discord .Interaction ,
    version :str ,change_type :str ,title :str ,
    description :str ):
        """Добавить запись в журнал"""
        # Change type проверкаю
        try :
            change_type_enum =ChangeType (change_type )
        except ValueError :
            await interaction .response .send_message (
            " Geчersiz deгiшiklik tipi! (added/changed/fixed/removed/security)",
            ephemeral =True 
            )
            return 

            # Giriш добавить
        entry =changelog_manager .add_entry (
        version =version ,
        change_type =change_type_enum ,
        title =title ,
        description =description ,
        author =interaction .user .display_name 
        )

        # Embed создать
        embed =discord .Embed (
        title =" Changelog Giriшi Добавлен",
        description =f"**Versiyon:** {version}\n**Tip:** {change_type}\n**Baшlыk:** {title}",
        color =discord .Color .green (),
        timestamp =datetime .now ()
        )

        await interaction .response .send_message (embed =embed )

    @app_commands .command (name ='changelog-latest',description ='En son changelog giriшlerini gёrюntюle')
    @app_commands .describe (limit ='Giriш sayыsы (varsayыlan: 10)')
    async def changelog_latest (self ,interaction :discord .Interaction ,limit :int =10 ):
        """En son changelog giriшlerini gёrюntюle"""
        # Giriшler al
        entries =changelog_manager .get_latest_entries (limit =limit )

        if not entries :
            await interaction .response .send_message (
            " Changelog запись не найдена!",
            ephemeral =True 
            )
            return 

            # Embed создать
        embed =discord .Embed (
        title =" Latest Changelog Entries",
        description =f"Son {len(entries)} giriш",
        color =discord .Color .blue (),
        timestamp =datetime .now ()
        )

        # Giriш listesi
        for entry in entries [:limit ]:
            type_emoji ={
            'added':'',
            'changed':'',
            'fixed':'',
            'removed':'',
            'security':''
            }.get (entry .change_type .value ,'')

            embed .add_field (
            name =f"{type_emoji} {entry.title} (v{entry.version})",
            value =f"{entry.description}\n[{entry.change_type.value}] - {entry.timestamp[:10]}",
            inline =False 
            )

        await interaction .response .send_message (embed =embed )

    @commands .Cog .listener ()
    async def on_ready (self ):
        """Bot hazыr olduгunda"""
        log .info (f" ChangelogCog loaded")


async def setup (bot ):
    await bot .add_cog (ChangelogCog (bot ))
