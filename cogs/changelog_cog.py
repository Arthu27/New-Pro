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
    @app_commands .describe (version ='Версия (необязательно)')
    async def changelog (self ,interaction :discord .Interaction ,version :str =None ):
        """Показать журнал изменений"""
        if version :
        # Конкретная версия
            entries =changelog_manager .get_entries_by_version (version )

            if not entries :
                await interaction .response .send_message (
                f"❌ Для версии {version} записей не найдено!",
                ephemeral =True 
                )
                return 

                # Embed создать
            embed =discord .Embed (
            title =f"📜 Журнал v{version}",
            description =f"Всего записей: {len(entries)}",
            color =discord .Color .blue (),
            timestamp =datetime .now ()
            )

            # Группировка по типу
            for entry in entries [:15 ]:
                type_emoji ={
                'added':'✨',
                'changed':'🔄',
                'fixed':'🔧',
                'removed':'🗑️',
                'security':'🔒'
                }.get (entry .change_type .value ,'')

                embed .add_field (
                name =f"{type_emoji} {entry.title}",
                value =f"{entry.description}\n[{entry.change_type.value}]",
                inline =False 
                )

            await interaction .response .send_message (embed =embed )
        else :
        # Все версии
            versions =changelog_manager .get_all_versions ()

            if not versions :
                await interaction .response .send_message (
                " Журнал изменений не найден!",
                ephemeral =True 
                )
                return 

                # Embed создать
            embed =discord .Embed (
            title ="📜 Версии журнала",
            description =f"Всего версий: {len(versions)}",
            color =discord .Color .blue (),
            timestamp =datetime .now ()
            )

            # Список версий
            for version in versions [:10 ]:
                entries =changelog_manager .get_entries_by_version (version )
                embed .add_field (
                name =f"v{version}",
                value =f"{len(entries)} записей\n{entries[0].timestamp[:10] if entries else 'N/A'}",
                inline =True 
                )

            await interaction .response .send_message (embed =embed )

    @app_commands .command (name ='changelog-add',description ='Добавить запись в журнал')
    @app_commands .describe (version ='Версия',change_type ='Тип изменения (added/changed/fixed/removed/security)',
    title ='Заголовок',description ='Описание')
    @app_commands .checks .has_permissions (administrator =True )
    async def changelog_add (self ,interaction :discord .Interaction ,
    version :str ,change_type :str ,title :str ,
    description :str ):
        """Добавить запись в журнал"""
        # Проверка типа изменения
        try :
            change_type_enum =ChangeType (change_type )
        except ValueError :
            await interaction .response .send_message (
            "❌ Неверный тип изменения! (added/changed/fixed/removed/security)",
            ephemeral =True 
            )
            return 

            # Добавить запись
        entry =changelog_manager .add_entry (
        version =version ,
        change_type =change_type_enum ,
        title =title ,
        description =description ,
        author =interaction .user .display_name 
        )

        # Embed создать
        embed =discord .Embed (
        title ="✅ Запись добавлена в журнал",
        description =f"**Версия:** {version}\n**Тип:** {change_type}\n**Заголовок:** {title}",
        color =discord .Color .green (),
        timestamp =datetime .now ()
        )

        await interaction .response .send_message (embed =embed )

    @app_commands .command (name ='changelog-latest',description ='Показать последние записи журнала')
    @app_commands .describe (limit ='Количество записей (по умолчанию: 10)')
    async def changelog_latest (self ,interaction :discord .Interaction ,limit :int =10 ):
        """Показать последние записи журнала"""
        # Получить записи
        entries =changelog_manager .get_latest_entries (limit =limit )

        if not entries :
            await interaction .response .send_message (
            "📜 Записей в журнале не найдено!",
            ephemeral =True 
            )
            return 

            # Embed создать
        embed =discord .Embed (
        title ="📜 Последние записи журнала",
        description =f"Последние {len(entries)} записей",
        color =discord .Color .blue (),
        timestamp =datetime .now ()
        )

        # Список записей
        for entry in entries [:limit ]:
            type_emoji ={
            'added':'✨',
            'changed':'🔄',
            'fixed':'🔧',
            'removed':'🗑️',
            'security':'🔒'
            }.get (entry .change_type .value ,'')

            embed .add_field (
            name =f"{type_emoji} {entry.title} (v{entry.version})",
            value =f"{entry.description}\n[{entry.change_type.value}] - {entry.timestamp[:10]}",
            inline =False 
            )

        await interaction .response .send_message (embed =embed )

    @commands .Cog .listener ()
    async def on_ready (self ):
        """Бот готов"""
        log .info (f" ChangelogCog loaded")


async def setup (bot ):
    await bot .add_cog (ChangelogCog (bot ))
