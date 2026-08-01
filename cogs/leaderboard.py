"""Liderlik Tablosu — message, ses, davet очередь"""
import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import datetime
from collections import defaultdict

DATA_DIR = 'data'


def _lb_file(guild_id: int) -> str:
    return f'{DATA_DIR}/leaderboard_{guild_id}.json'


def _load(guild_id: int) -> dict:
    path = _lb_file(guild_id)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {'messages': {}, 'voice_minutes': {}, 'invites': {}}


def _save(guild_id: int, data: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(_lb_file(guild_id), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _medal(rank: int) -> str:
    return ['', '', ''].get(rank - 1, f'`#{rank}`')


class Leaderboard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._voice_join: dict = {}  # user_id → join_time

    # Сообщение sayacı 
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        data = _load(message.guild.id)
        uid = str(message.author.id)
        data['messages'][uid] = data['messages'].get(uid, 0) + 1
        _save(message.guild.id, data)

    # Голос длительность takibi 
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before, after):
        if member.bot:
            return
        uid = member.id
        now = datetime.datetime.utcnow()

        # Канал girdi
        if not before.channel and after.channel:
            self._voice_join[uid] = now

        # Канал вышел
        elif before.channel and not after.channel:
            if uid in self._voice_join:
                minutes = int((now - self._voice_join.pop(uid)).total_seconds() / 60)
                if minutes > 0:
                    data = _load(member.guild.id)
                    suid = str(uid)
                    data['voice_minutes'][suid] = data['voice_minutes'].get(suid, 0) + minutes
                    _save(member.guild.id, data)

    # /очередь команда 
    @commands.command(name='ses-очередь', aliases=['sssıralama', 'sesliler', 'sesstat'])
    async def voice_leaderboard(self, ctx):
        """Всего ses длительность очередь: !ses-очередь"""
        vs_path = f'data/voice_stats_{ctx.guild.id}.json'
        if not os.path.exists(vs_path):
            await ctx.send(' Пока ses данные yok.')
            return

        import json as _json
        with open(vs_path, 'r', encoding='utf-8') as f:
            vs = _json.load(f)

        users = vs.get('users', {})
        sorted_users = sorted(
            users.items(),
            key=lambda x: x[1].get('total_seconds', 0) if isinstance(x[1], dict) else int(x[1]),
            reverse=True
        )[:15]

        medals = ['', '', '']
        lines = []
        for i, (uid, d) in enumerate(sorted_users):
            secs = d.get('total_seconds', 0) if isinstance(d, dict) else int(d)
            name = d.get('name', f'<@{uid}>') if isinstance(d, dict) else f'<@{uid}>'
            h, m = divmod(secs // 60, 60)
            medal = medals[i] if i < 3 else f'`#{i+1}`'
            bar_len = min(int((secs / sorted_users[0][1].get('total_seconds', 1) if isinstance(sorted_users[0][1], dict) else 1) * 10), 10)
            bar = '' * bar_len + '' * (10 - bar_len)
            lines.append(f'{medal} **{name}**\n {bar} `{h}s {m}dk`')

        embed = discord.Embed(
            title=' Голос Длительность Очередь',
            description='\n\n'.join(lines) or 'Данные yok.',
            color=0x57F287
        )
        embed.set_footer(text=f'{ctx.guild.name} • Всего ses длительность')
        await ctx.send(embed=embed)
    async def leaderboard(self, ctx, kategori: str = 'overall'):
        """Сервер liderlik tablosunu показать: !очередь [message/ses/davet/overall]"""
        data = _load(ctx.guild.id)
        class FakeInteraction:
            guild = ctx.guild
            channel = ctx.channel
            async def followup_send(self, **kwargs):
                await ctx.send(**kwargs)
        fi = FakeInteraction()

        if kategori in ('message', 'messages', 'msg'):
            await self._show_messages_ctx(ctx, data)
        elif kategori in ('ses', 'voice'):
            await self._show_voice_ctx(ctx, data)
        elif kategori in ('davet', 'invites', 'invite'):
            await self._show_invites_ctx(ctx, data)
        else:
            await self._show_overall_ctx(ctx, data)

    async def _show_messages_ctx(self, ctx, data):
        sorted_users = sorted(data['messages'].items(), key=lambda x: x[1], reverse=True)[:10]
        embed = discord.Embed(title=' Сообщение Очередь', color=0x5865F2)
        lines = []
        for i, (uid, count) in enumerate(sorted_users, 1):
            member = ctx.guild.get_member(int(uid))
            name = member.display_name if member else f'<@{uid}>'
            lines.append(f'{_medal(i)} **{name}** — {count:,} message')
        embed.description = '\n'.join(lines) or 'Пока Данные yok.'
        embed.set_footer(text=f'{ctx.guild.name} • Liderlik Tablosu')
        await ctx.send(embed=embed)

    async def _show_voice_ctx(self, ctx, data):
        sorted_users = sorted(data['voice_minutes'].items(), key=lambda x: x[1], reverse=True)[:10]
        embed = discord.Embed(title=' Голос Длительность Очередь', color=0x57F287)
        lines = []
        for i, (uid, mins) in enumerate(sorted_users, 1):
            member = ctx.guild.get_member(int(uid))
            name = member.display_name if member else f'<@{uid}>'
            h, m = divmod(mins, 60)
            lines.append(f'{_medal(i)} **{name}** — {h}s {m}dk')
        embed.description = '\n'.join(lines) or 'Пока Данные yok.'
        embed.set_footer(text=f'{ctx.guild.name} • Liderlik Tablosu')
        await ctx.send(embed=embed)

    async def _show_invites_ctx(self, ctx, data):
        invite_file = f'{DATA_DIR}/invite_counts_{ctx.guild.id}.json'
        invite_data = {}
        if os.path.exists(invite_file):
            try:
                with open(invite_file, 'r', encoding='utf-8') as f:
                    raw = json.load(f)
                # Значение dict может быть — int'e преобразовать
                for uid, val in raw.items():
                    if isinstance(val, dict):
                        invite_data[uid] = val.get('total', val.get('count', val.get('uses', 0)))
                    else:
                        invite_data[uid] = int(val)
            except Exception:
                pass
        sorted_users = sorted(invite_data.items(), key=lambda x: x[1], reverse=True)[:10]
        embed = discord.Embed(title=' Davet Очередь', color=0xFEE75C)
        lines = []
        for i, (uid, count) in enumerate(sorted_users, 1):
            member = ctx.guild.get_member(int(uid))
            name = member.display_name if member else f'<@{uid}>'
            lines.append(f'{_medal(i)} **{name}** — {count} davet')
        embed.description = '\n'.join(lines) or 'Пока Данные yok.'
        embed.set_footer(text=f'{ctx.guild.name} • Liderlik Tablosu')
        await ctx.send(embed=embed)

    async def _show_overall_ctx(self, ctx, data):
        scores = defaultdict(int)
        for uid, count in data['messages'].items():
            scores[uid] += count
        for uid, mins in data['voice_minutes'].items():
            scores[uid] += mins * 2
        sorted_users = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:10]
        embed = discord.Embed(
            title=' Общий Liderlik Tablosu',
            description='Сообщение (×1) + Голос minutessı (×2)',
            color=0xF1C40F
        )
        lines = []
        for i, (uid, score) in enumerate(sorted_users, 1):
            member = ctx.guild.get_member(int(uid))
            name = member.display_name if member else f'<@{uid}>'
            msgs = data['messages'].get(uid, 0)
            mins = data['voice_minutes'].get(uid, 0)
            h, m = divmod(mins, 60)
            lines.append(
                f'{_medal(i)} **{name}** — {score:,} очков\n'
                f' {msgs:,} message • {h}s {m}dk'
            )
        embed.description = (embed.description or '') + '\n\n' + ('\n'.join(lines) or 'Пока Данные yok.')
        embed.set_footer(text=f'{ctx.guild.name} • Liderlik Tablosu')
        await ctx.send(embed=embed)

    @app_commands.command(name='mystats', description='Моя статистика')
    async def my_stats(self, interaction: discord.Interaction):
        data = _load(interaction.guild.id)
        uid = str(interaction.user.id)

        msgs = data['messages'].get(uid, 0)
        mins = data['voice_minutes'].get(uid, 0)
        h, m = divmod(mins, 60)
        score = msgs * 1 + mins * 2

        # Очередь найти
        all_scores = {u: data['messages'].get(u, 0) + data['voice_minutes'].get(u, 0) * 2
                      for u in set(list(data['messages'].keys()) + list(data['voice_minutes'].keys()))}
        sorted_all = sorted(all_scores.items(), key=lambda x: x[1], reverse=True)
        rank = next((i + 1 for i, (u, _) in enumerate(sorted_all) if u == uid), '?')

        embed = discord.Embed(
            title=f' {interaction.user.display_name} — Статистика',
            color=interaction.user.accent_color or 0x5865F2
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.add_field(name=' Сообщение', value=f'{msgs:,}', inline=True)
        embed.add_field(name=' Голос', value=f'{h}s {m}dk', inline=True)
        embed.add_field(name=' Очки', value=f'{score:,}', inline=True)
        embed.add_field(name=' Очередь', value=f'#{rank}', inline=True)
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(Leaderboard(bot), guilds=[discord.Object(id=1421244140359909513), discord.Object(id=1107038411895881788), discord.Object(id=1498837105915330562)])
