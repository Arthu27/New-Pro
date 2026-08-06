"""Управление модулями (cog) — загрузка/выгрузка/перезагрузка из панели или командой"""
import discord
from discord .ext import commands
from discord import app_commands
import os

class CogManager (commands .Cog ):
    def __init__ (self ,bot ):
        self .bot =bot

    @commands .group (name ='module',aliases =['modul'],invoke_without_command =True )
    @commands .is_owner ()
    async def module_group (self ,ctx ):
        """Показать список загруженных/незагруженных модулей"""
        loaded =[ext .split ('.')[-1 ]for ext in self .bot .extensions ]
        all_cogs =[f [:-3 ]for f in os .listdir ('./cogs')if f .endswith ('.py')]
        unloaded =[c for c in all_cogs if c not in loaded ]

        embed =discord .Embed (title =' Управление модулями',color =0x3498DB )
        embed .add_field (
        name =f' Загружено ({len(loaded)})',
        value ='\n'.join (f'`{c}`'for c in sorted (loaded ))or 'Нет',
        inline =True
        )
        embed .add_field (
        name =f' Не загружено ({len(unloaded)})',
        value ='\n'.join (f'`{c}`'for c in sorted (unloaded ))or 'Нет',
        inline =True
        )
        await ctx .send (embed =embed )

    @module_group .command (name ='load',aliases =['yukle'])
    @commands .is_owner ()
    async def load_cog (self ,ctx ,cog_name :str ):
        """Загрузить модуль"""
        try :
            await self .bot .load_extension (f'cogs.{cog_name}')
            await ctx .send (f' Модуль `{cog_name}` загружен!')
        except Exception as e :
            await ctx .send (f' Ошибка: `{e}`')

    @module_group .command (name ='unload',aliases =['kaldir'])
    @commands .is_owner ()
    async def unload_cog (self ,ctx ,cog_name :str ):
        """Выгрузить модуль"""
        if cog_name =='cog_manager':
            await ctx .send (' Этот модуль не может быть выгружен!')
            return
        try :
            await self .bot .unload_extension (f'cogs.{cog_name}')
            await ctx .send (f' `{cog_name}` выгружен!')
        except Exception as e :
            await ctx .send (f' Ошибка: `{e}`')

    @module_group .command (name ='reload',aliases =['yenile'])
    @commands .is_owner ()
    async def reload_cog (self ,ctx ,cog_name :str ):
        """Перезагрузить модуль"""
        try :
            await self .bot .reload_extension (f'cogs.{cog_name}')
            await ctx .send (f' Модуль `{cog_name}` перезагружен!')
        except Exception as e :
            await ctx .send (f' Ошибка: `{e}`')

    @module_group .command (name ='reload-all',aliases =['hepsini-yenile'])
    @commands .is_owner ()
    async def reload_all (self ,ctx ):
        """Перезагрузить все модули"""
        results =[]
        for ext in list (self .bot .extensions ):
            try :
                await self .bot .reload_extension (ext )
                results .append (f' {ext.split(".")[-1]}')
            except Exception as e :
                results .append (f' {ext.split(".")[-1]}: {e}')
        await ctx .send ('\n'.join (results ))

async def setup (bot ):
    await bot .add_cog (CogManager (bot ))
