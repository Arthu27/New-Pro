"""
Aether — /ladder: визуальная лестница авто-наказаний.

Читает/пишет тот же конфиг, что и авто-наказание в cogs/warnings.py
(data/warn_config_<guild_id>.json, ключ 'steps') — ступени из панели
и из команд живут вместе.
"""
import io
import json
import os

import discord
from datetime import datetime, timezone
from discord import app_commands
from discord.ext import commands

from cogs.warnings import load_warn_config


def _save_warn_config(guild_id, cfg):
    os.makedirs('data', exist_ok=True)
    f = f'data/warn_config_{guild_id}.json'
    with open(f, 'w', encoding='utf-8') as fp:
        json.dump(cfg, fp, ensure_ascii=False, indent=2)


def _steps(cfg):
    return cfg.get('steps') or cfg.get('thresholds') or []


def _fmt_step(step):
    act = step.get('action', 'mute')
    d = int(step.get('duration', 0) or 0)
    unit = step.get('unit', 'minute')
    names = {'mute': 'мут', 'timeout': 'мут', 'kick': 'кик', 'ban': 'бан'}
    a = names.get(act, act)
    if act == 'ban' and not d:
        return 'бан навсегда'
    if act == 'kick' and not d:
        return a
    if unit == 'hour':
        return f'{a} на {d} ч'
    if unit == 'day':
        return f'{a} на {d} дн'
    return f'{a} на {d} мин'


class Ladder(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _render(self, guild):
        cfg = load_warn_config(str(guild.id))
        try:
            from services.ladder_card import render_ladder_card
            return render_ladder_card(_steps(cfg), guild_name=guild.name)
        except Exception:
            return None

    @app_commands.command(name='ladder', description='Лестница авто-наказаний (красивая карточка)')
    @app_commands.checks.has_permissions(moderate_members=True)
    async def ladder(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cfg = load_warn_config(str(interaction.guild.id))
        steps = _steps(cfg)
        e = discord.Embed(color=0xC8922A, timestamp=datetime.now(timezone.utc))
        if steps:
            lines = []
            for st in sorted(steps, key=lambda s: int(s.get('count', 0))):
                lines.append(f"**{st.get('count', '?')}** варнов → {_fmt_step(st)}")
            e.description = '## 🪜 Лестница наказаний\n' + '\n'.join(lines)
        else:
            e.description = ('## 🪜 Лестница наказаний\nПока не настроена. '
                             'Добавь ступени командой /ladder-add или в веб-панели (Предупреждения).')
        e.set_footer(text=f'{interaction.guild.name} · Авто-наказание по варнам',
                     icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
        png = self._render(interaction.guild)
        if png:
            e.set_image(url='attachment://aether_ladder.png')
            await interaction.followup.send(
                embed=e, file=discord.File(io.BytesIO(png), filename='aether_ladder.png'))
        else:
            await interaction.followup.send(embed=e)

    @app_commands.command(name='ladder-add', description='Добавить ступень лестницы: через N варнов — действие')
    @app_commands.describe(count='Сколько варнов нужно для срабатывания',
                           action='Действие: мут / кик / бан',
                           duration='Длительность (для мута); 0 — бан навсегда',
                           unit='Единица времени')
    @app_commands.choices(action=[
        app_commands.Choice(name='Мут', value='mute'),
        app_commands.Choice(name='Кик', value='kick'),
        app_commands.Choice(name='Бан', value='ban'),
    ], unit=[
        app_commands.Choice(name='минут', value='minute'),
        app_commands.Choice(name='часов', value='hour'),
        app_commands.Choice(name='дней', value='day'),
    ])
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ladder_add(self, interaction: discord.Interaction,
                         count: int, action: app_commands.Choice[str],
                         duration: int = 10, unit: app_commands.Choice[str] = None):
        count = max(1, min(count, 100))
        duration = max(0, min(duration, 10000))
        unit_v = unit.value if unit else 'minute'
        act_v = action.value
        if act_v == 'kick':
            duration = 0
        cfg = load_warn_config(str(interaction.guild.id))
        steps = _steps(cfg)
        steps = [s for s in steps if int(s.get('count', 0)) != count]
        steps.append({'count': count, 'action': act_v, 'duration': duration, 'unit': unit_v})
        cfg['steps'] = steps
        _save_warn_config(interaction.guild.id, cfg)
        await interaction.response.send_message(
            f'🪜 Ступень сохранена: **{count}** варнов → **{_fmt_step({"count": count, "action": act_v, "duration": duration, "unit": unit_v})}**.\n'
            f'Всего ступеней: {len(steps)}. Проверь: /ladder',
            ephemeral=True)

    @app_commands.command(name='ladder-remove', description='Убрать ступень лестницы по количеству варнов')
    @app_commands.describe(count='Ступень с каким количеством варнов убрать')
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ladder_remove(self, interaction: discord.Interaction, count: int):
        cfg = load_warn_config(str(interaction.guild.id))
        steps = _steps(cfg)
        new = [s for s in steps if int(s.get('count', 0)) != count]
        if len(new) == len(steps):
            await interaction.response.send_message(
                f'Ступени на **{count}** варнов нет.', ephemeral=True)
            return
        cfg['steps'] = new
        _save_warn_config(interaction.guild.id, cfg)
        await interaction.response.send_message(
            f'🪜 Ступень на **{count}** варнов убрана. Осталось: {len(new)}.', ephemeral=True)

    @app_commands.command(name='ladder-test', description='Что грозит участнику прямо сейчас (симуляция)')
    @app_commands.describe(member='Кого проверить')
    @app_commands.checks.has_permissions(moderate_members=True)
    async def ladder_test(self, interaction: discord.Interaction, member: discord.Member):
        cog = self.bot.get_cog('warnings') or self.bot.get_cog('Warnings')
        try:
            total = len(cog._get_warns(interaction.guild.id, member.id)) if cog else 0
        except Exception:
            total = 0
        cfg = load_warn_config(str(interaction.guild.id))
        steps = sorted(_steps(cfg), key=lambda s: int(s.get('count', 0)))
        matched = None
        for st in steps:
            if total >= int(st.get('count', 0)):
                matched = st
        nxt = next((s for s in steps if total < int(s.get('count', 0))), None)
        e = discord.Embed(color=0xC8922A, timestamp=datetime.now(timezone.utc))
        desc = (f'## 🪜 Проверка: {member.display_name}\n'
                f'Сейчас предупреждений: **{total}**\n')
        desc += f'Активная мера: **{_fmt_step(matched)}**\n' if matched else 'Активной меры нет — участник ниже первой ступени.\n'
        if nxt:
            desc += f'Следующая ступень: **{nxt["count"]}** варнов → {_fmt_step(nxt)} (осталось {int(nxt["count"]) - total})'
        e.description = desc
        e.set_footer(text=f'{interaction.guild.name} · симуляция, наказание не применяется')
        await interaction.response.send_message(embed=e, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Ladder(bot))
