"""Управление модулями (cog) — загрузка/выгрузка/перезагрузка из панели или командой"""
import discord
from discord.ext import commands
import os


class CogManager(commands.Cog):
    """Менеджер модулей бота (только для владельца)"""

    def __init__(self, bot):
        self.bot = bot

    def _sleeping(self):
        """Модули, спящие по профилю cogs_policy (LEAN по умолчанию)."""
        try:
            import cogs_policy
            files = [f for f in os.listdir('./cogs') if f.endswith('.py')]
            _on, off = cogs_policy.select_from_environment(files)
            return {f[:-3] for f in off}
        except Exception:
            return set()

    @commands.group(name='module', aliases=['модуль'], invoke_without_command=True)
    @commands.is_owner()
    async def module_group(self, ctx):
        """Показать список загруженных/незагруженных модулей"""
        from cogs.embed_utils import aether_embed, plural
        loaded = [ext.split('.')[-1] for ext in self.bot.extensions]
        all_cogs = [f[:-3] for f in os.listdir('./cogs') if f.endswith('.py')]
        sleeping = self._sleeping()
        just_off = [c for c in all_cogs if c not in loaded and c not in sleeping]
        rows = [f'`{c}`' for c in sorted(loaded)]
        embed = aether_embed(
            'system', 'Управление модулями', None,
            fields=[
                (f' Всегда в строю ({len(loaded)})',
                 '\n'.join(rows)[:1000] or '—', True),
                (f' Спят по профилю ({len(sleeping)})',
                 '\n'.join(f'`{c}`' for c in sorted(sleeping))[:1000] or '—', True),
            ],
            guild=ctx.guild, footer_extra='Модули',
        )
        if just_off:
            embed.add_field(
                name=f'⏸ Выгружены вручную ({len(just_off)})',
                value='\n'.join(f'`{c}`' for c in sorted(just_off))[:1000] or '—',
                inline=False)
        embed.add_field(
            name='Команды',
            value=('`!module load <имя>` — загрузить\n'
                   '`!module unload <имя>` — выгрузить\n'
                   '`!module reload <имя>` — перезагрузить\n'
                   f'Разбудить {len(sleeping)} спящих: `BOT_FULL=1` или `EXTRA_COGS` в .env'),
            inline=False)
        await ctx.send(embed=embed)

    @module_group.command(name='load', aliases=['загрузить'])
    @commands.is_owner()
    async def load_cog(self, ctx, cog_name: str):
        """Загрузить модуль"""
        from cogs.embed_utils import reply
        try:
            await self.bot.load_extension(f'cogs.{cog_name}')
            await reply(ctx, 'system', 'Модуль загружен', f'`{cog_name}` — в строю.')
        except Exception as e:
            await reply(ctx, 'error', 'Не загрузился', f'`{cog_name}`: {e}')

    @module_group.command(name='unload', aliases=['выгрузить'])
    @commands.is_owner()
    async def unload_cog(self, ctx, cog_name: str):
        """Выгрузить модуль"""
        from cogs.embed_utils import reply
        if cog_name == 'cog_manager':
            await reply(ctx, 'warn', 'Нельзя',
                        'Менеджер модулей выгружать нельзя — потеряешь управление.')
            return
        try:
            await self.bot.unload_extension(f'cogs.{cog_name}')
            await reply(ctx, 'system', 'Модуль выгружен', f'`{cog_name}` — уснул до команды.')
        except Exception as e:
            await reply(ctx, 'error', 'Не выгрузился', f'`{cog_name}`: {e}')

    @module_group.command(name='reload', aliases=['перезагрузить'])
    @commands.is_owner()
    async def reload_cog(self, ctx, cog_name: str):
        """Перезагрузить модуль"""
        from cogs.embed_utils import reply
        try:
            await self.bot.reload_extension(f'cogs.{cog_name}')
            await reply(ctx, 'system', 'Модуль перезагружен', f'`{cog_name}` — свежий код.')
        except Exception as e:
            await reply(ctx, 'error', 'Не перезагрузился', f'`{cog_name}`: {e}')

    @module_group.command(name='reload-all', aliases=['обновить-всё'])
    @commands.is_owner()
    async def reload_all(self, ctx):
        """Перезагрузить все модули"""
        from cogs.embed_utils import aether_embed
        ok, bad = [], []
        for ext in list(self.bot.extensions):
            try:
                await self.bot.reload_extension(ext)
                ok.append(ext.split('.')[-1])
            except Exception as e:
                bad.append(f'`{ext.split(".")[-1]}` — {e}')
        embed = aether_embed(
            'system', 'Перезагрузка всех модулей', None,
            fields=[
                (f' Перезагружено ({len(ok)})', ', '.join(f'`{c}`' for c in ok)[:1000] or '—', False),
                (f' Ошибки ({len(bad)})', '\n'.join(bad)[:1000] or 'нет', False),
            ],
            guild=ctx.guild, footer_extra='Модули',
        )
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(CogManager(bot))
