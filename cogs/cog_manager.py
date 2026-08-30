"""Управление модулями (cog) — из панели или слеш-командой /module (владелец).

Раньше было !module load/unload/reload — теперь одна слеш-команда
/module <действие> [модуль]: меню Discord остаётся компактным, префиксных
команд у бота больше нет.
"""
import discord
from discord import app_commands
from discord.ext import commands
import os

from logger import get_logger

log = get_logger("cog_manager")

from cogs.embed_utils import hakumo_embed, reply, InterCtx


def _is_bot_owner(interaction) -> bool:
    """Владелец(ы) бота из .env (OWNER_ID + OWNER_IDS)."""
    try:
        from config import Config
        return interaction.user.id in Config.all_owner_ids()
    except Exception:
        return False


async def _owner_only(interaction) -> bool:
    """Вежливый отказ не-владельцу (без «сырых» ошибок прав)."""
    if _is_bot_owner(interaction):
        return True
    await interaction.response.send_message(
        'Эта команда — только для владельца бота.', ephemeral=True)
    return False


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

    async def _list(self, ctx):
        loaded = [ext.split('.')[-1] for ext in self.bot.extensions]
        all_cogs = [f[:-3] for f in os.listdir('./cogs') if f.endswith('.py')]
        sleeping = self._sleeping()
        just_off = [c for c in all_cogs if c not in loaded and c not in sleeping]
        rows = [f'`{c}`' for c in sorted(loaded)]
        embed = hakumo_embed(
            'system', 'Управление модулями', None,
            fields=[
                (f'Всегда в строю ({len(loaded)})',
                 '\n'.join(rows)[:1000] or '—', True),
                (f'Спят по профилю ({len(sleeping)})',
                 '\n'.join(f'`{c}`' for c in sorted(sleeping))[:1000] or '—', True),
            ],
            guild=ctx.guild, footer_extra='Модули',
        )
        if just_off:
            embed.add_field(
                name=f'Выгружены вручную ({len(just_off)})',
                value='\n'.join(f'`{c}`' for c in sorted(just_off))[:1000] or '—',
                inline=False)
        embed.add_field(
            name='Команды',
            value=('`/module` → «Список» — что загружено\n'
                   '`/module` → «Загрузить / Выгрузить / Перезагрузить» + имя модуля\n'
                   '`/module` → «Перезагрузить все»\n'
                   f'Разбудить {len(sleeping)} спящих: `BOT_FULL=1` или `EXTRA_COGS` в .env'),
            inline=False)
        await ctx.send(embed=embed)

    @app_commands.command(name='module',
                          description='Модули бота: список, загрузка, выгрузка (владелец бота)')
    @app_commands.describe(действие='Что сделать', модуль='Имя модуля без .py')
    @app_commands.choices(действие=[
        app_commands.Choice(name='Список', value='list'),
        app_commands.Choice(name='Загрузить', value='load'),
        app_commands.Choice(name='Выгрузить', value='unload'),
        app_commands.Choice(name='Перезагрузить', value='reload'),
        app_commands.Choice(name='Перезагрузить все', value='reload-all'),
    ])
    @app_commands.default_permissions(administrator=True)
    async def module(self, interaction: discord.Interaction,
                     действие: app_commands.Choice[str],
                     модуль: str = None):
        """Управление модулями: /module <действие> [модуль]"""
        if not await _owner_only(interaction):
            return
        ctx = InterCtx(interaction)
        act = действие.value
        cog_name = (модуль or '').strip()

        if act == 'list':
            await self._list(ctx)
            return

        if act in ('load', 'unload', 'reload'):
            if not cog_name:
                await reply(ctx, 'warn', 'Не хватает данных',
                            f'Для «{действие.name}» укажи имя модуля — например `moderation`.',
                            footer_extra='Модули')
                return
            if act == 'unload' and cog_name == 'cog_manager':
                await reply(ctx, 'warn', 'Нельзя',
                            'Менеджер модулей выгружать нельзя — потеряешь управление.')
                return
            try:
                if act == 'load':
                    await self.bot.load_extension(f'cogs.{cog_name}')
                    await reply(ctx, 'system', 'Модуль загружен', f'`{cog_name}` — в строю.')
                elif act == 'unload':
                    await self.bot.unload_extension(f'cogs.{cog_name}')
                    await reply(ctx, 'system', 'Модуль выгружен',
                                f'`{cog_name}` — уснул до команды.')
                else:
                    await self.bot.reload_extension(f'cogs.{cog_name}')
                    await reply(ctx, 'system', 'Модуль перезагружен',
                                f'`{cog_name}` — свежий код.')
                # Свежезагруженные команды — сразу под бюджет меню
                # (глобальные И guild-scoped): /module load не должен
                # вернуть в слеш-меню лишние команды до рестарта.
                try:
                    from slash_budget import apply_slash_budget
                    apply_slash_budget(self.bot.tree)
                except Exception as _ex:
                    log.debug('cog_manager: apply_slash_budget: %s', _ex)
            except Exception as e:
                await reply(ctx, 'error', 'Не получилось', f'`{cog_name}`: {e}')
            return

        if act == 'reload-all':
            ok, bad = [], []
            for ext in list(self.bot.extensions):
                try:
                    await self.bot.reload_extension(ext)
                    ok.append(ext.split('.')[-1])
                except Exception as e:
                    bad.append(f'`{ext.split(".")[-1]}` — {e}')
            try:
                from slash_budget import apply_slash_budget
                apply_slash_budget(self.bot.tree)
            except Exception as _ex:
                log.debug('cog_manager: apply_slash_budget (reload-all): %s', _ex)
            embed = hakumo_embed(
                'system', 'Перезагрузка всех модулей', None,
                fields=[
                    (f'Перезагружено ({len(ok)})',
                     ', '.join(f'`{c}`' for c in ok)[:1000] or '—', False),
                    (f'Ошибки ({len(bad)})', '\n'.join(bad)[:1000] or 'нет', False),
                ],
                guild=ctx.guild, footer_extra='Модули',
            )
            await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(CogManager(bot))
