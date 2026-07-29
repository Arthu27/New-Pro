"""Cog controli - panelden/команда cog aç/закрыть"""
import discord
from discord.ext import commands
from discord import app_commands
import os

class CogManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name='modul', invoke_without_command=True)
    @commands.is_owner()
    async def modul_group(self, ctx):
        """Cog control команды"""
        loaded = [ext.split('.')[-1] for ext in self.bot.extensions]
        all_cogs = [f[:-3] for f in os.listdir('./cogs') if f.endswith('.py')]
        unloaded = [c for c in all_cogs if c not in loaded]

        embed = discord.Embed(title='⚙️ Modül Управление', color=0x3498DB)
        embed.add_field(
            name=f'✅ Загруз ({len(loaded)})',
            value='\n'.join(f'`{c}`' for c in sorted(loaded)) or 'Нет',
            inline=True
        )
        embed.add_field(
            name=f'❌ Загруз Не ({len(unloaded)})',
            value='\n'.join(f'`{c}`' for c in sorted(unloaded)) or 'Нет',
            inline=True
        )
        await ctx.send(embed=embed)

    @modul_group.command(name='загрузить')
    @commands.is_owner()
    async def load_cog(self, ctx, cog_name: str):
        """Cog загрузить"""
        try:
            await self.bot.load_extension(f'cogs.{cog_name}')
            await ctx.send(f'✅ Модуль `{cog_name}` загружен!')
        except Exception as e:
            await ctx.send(f'❌ Ошибка: `{e}`')

    @modul_group.command(name='удалить')
    @commands.is_owner()
    async def unload_cog(self, ctx, cog_name: str):
        """Cog удалить"""
        if cog_name == 'cog_manager':
            await ctx.send('❌ Этот модуль не может быть выгружен!')
            return
        try:
            await self.bot.unload_extension(f'cogs.{cog_name}')
            await ctx.send(f'✅ `{cog_name}` удалена!')
        except Exception as e:
            await ctx.send(f'❌ Ошибка: `{e}`')

    @modul_group.command(name='обновить')
    @commands.is_owner()
    async def reload_cog(self, ctx, cog_name: str):
        """Cog обновить"""
        try:
            await self.bot.reload_extension(f'cogs.{cog_name}')
            await ctx.send(f'✅ Модуль `{cog_name}` перезагружен!')
        except Exception as e:
            await ctx.send(f'❌ Ошибка: `{e}`')

    @modul_group.command(name='hepsini-обновить')
    @commands.is_owner()
    async def reload_all(self, ctx):
        """Все cog'ları обновить"""
        results = []
        for ext in list(self.bot.extensions):
            try:
                await self.bot.reload_extension(ext)
                results.append(f'✅ {ext.split(".")[-1]}')
            except Exception as e:
                results.append(f'❌ {ext.split(".")[-1]}: {e}')
        await ctx.send('\n'.join(results))

async def setup(bot):
    await bot.add_cog(CogManager(bot))