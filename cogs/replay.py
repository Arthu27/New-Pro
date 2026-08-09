"""
Aether — /replay: визуальная лента событий сервера (реплеер инцидентов).

Источник — data/audit_log.json (пишет cogs/logs.py). Рисует карточку-
таймлайн (services/replay_card.py) и присылает её вложением.
"""
import datetime
import io
import json
import os

import discord
from discord import app_commands
from discord.ext import commands

AUDIT_FILE = 'data/audit_log.json'


def _load_events(guild_id):
    if not os.path.exists(AUDIT_FILE):
        return []
    try:
        with open(AUDIT_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        ev = data.get(str(guild_id), [])
        return ev if isinstance(ev, list) else []
    except Exception:
        return []


def _parse_ts(ev):
    ts = str(ev.get('timestamp', ''))
    try:
        return datetime.datetime.fromisoformat(ts.replace('Z', '+00:00'))
    except Exception:
        return None


def _detail_text(ev):
    """Человекочитаемая строка деталей из полей события."""
    parts = []
    un = ev.get('user_name') or ev.get('name')
    if un:
        parts.append(str(un))
    ar = ev.get('added_roles')
    rr = ev.get('removed_roles')
    if ar:
        parts.append('+ ' + ', '.join(str(r) for r in ar))
    if rr:
        parts.append('− ' + ', '.join(str(r) for r in rr))
    chn = ev.get('channel_name') or ev.get('channel')
    if chn:
        parts.append('#' + str(chn).lstrip('#'))
    if ev.get('content'):
        parts.append('«' + str(ev['content'])[:70] + '»')
    mn = ev.get('mod_name')
    if mn and mn != '—':
        parts.append(f'Мод: {mn}')
    if ev.get('reason') and ev['reason'] != '—':
        parts.append('Причина: ' + str(ev['reason'])[:80])
    if ev.get('until'):
        parts.append('до ' + str(ev['until'])[:16].replace('T', ' '))
    return ' · '.join(parts)[:220]


class Replay(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name='replay', description='Визуальная лента событий сервера (карточка-таймлайн)')
    @app_commands.describe(member='Показать только события этого участника (необязательно)',
                           minutes='Окно в минутах в прошлое (по умолчанию 30, макс. 1440)')
    @app_commands.checks.has_permissions(moderate_members=True)
    async def replay(self, interaction: discord.Interaction,
                     member: discord.Member = None, minutes: int = 30):
        await interaction.response.defer()
        minutes = max(5, min(int(minutes or 30), 1440))
        now = datetime.datetime.now(datetime.timezone.utc)
        threshold = now - datetime.timedelta(minutes=minutes)
        uid = str(member.id) if member else None

        rows = []
        for ev in _load_events(interaction.guild.id):
            ts = _parse_ts(ev)
            if ts is None:
                continue
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=datetime.timezone.utc)
            if ts < threshold:
                continue
            if uid:
                blob = json.dumps(ev, ensure_ascii=False)
                if f'"{uid}"' not in blob and uid not in blob:
                    continue
            rows.append((ts, ev))
        rows.sort(key=lambda x: x[0])

        if not rows:
            await interaction.followup.send(
                f'За последние **{minutes}** мин событий нет. '
                'Бот ведёт летопись, пока он в сети — старые окна могут быть пустыми.',
                ephemeral=True)
            return

        events = []
        for ts, ev in rows[-14:]:
            events.append({
                'time': ts.strftime('%H:%M'),
                'cat': str(ev.get('category', 'guild')),
                'label': str(ev.get('action', 'Событие')),
                'detail': _detail_text(ev),
            })

        title = f'События: {member.display_name}' if member else 'Все события сервера'
        subtitle = f'окно {minutes} мин · UTC'
        try:
            from services.replay_card import render_replay_card
            png = render_replay_card(title, subtitle, events, now_str=now.strftime('%H:%M UTC'))
        except Exception:
            png = None

        e = discord.Embed(color=0xC8922A, timestamp=datetime.datetime.now(datetime.timezone.utc))
        e.description = f'## 🎞 Реплеер событий\n**{title}** · {subtitle}\n\n' + '\n'.join(
            f"**{ev['time']}** · {ev['label']}" + (f" — {ev['detail']}" if ev['detail'] else '')
            for ev in events[-10:])
        e.set_footer(text=f'{interaction.guild.name} · Aether Replay',
                     icon_url=interaction.guild.icon.url if interaction.guild.icon else None)

        if png:
            e.set_image(url='attachment://aether_replay.png')
            await interaction.followup.send(
                embed=e, file=discord.File(io.BytesIO(png), filename='aether_replay.png'))
        else:
            await interaction.followup.send(embed=e)


async def setup(bot):
    await bot.add_cog(Replay(bot))
