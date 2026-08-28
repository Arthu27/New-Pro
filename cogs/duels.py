# -*- coding: utf-8 -*-
"""Дуэли (Duels Cog)
===================
Честный способ решить спор: /дуэль @соперник — кнопки «Принять/Отказаться»,
монетка 50/50, статистика побед ведётся по серверу. Никаких ставок из
экономики — это чистый фан без балансов, зато с лидербордом.

- /дуэль @user      — вызвать на дуэль
- /дуэли [@user]    — статистика побед/поражений/серии
- /дуэлтоп          — топ дуэлянтов сервера

Хранилище — SQLite (GuildData 'duels'). Метки — aware UTC.
"""
import random
from datetime import datetime, timezone

import discord
from discord.ext import commands

from db import GuildData
from logger import get_logger
from services import text_format as tf

log = get_logger("duels")

UTC = timezone.utc
COLOR = 0xE67E22
DUEL_TIMEOUT = 60  # секунд на принятие вызова


# ─── чистые функции (покрыты тестом) ────────────────────────────────────────

def empty_state():
    return {'players': {}, 'total': 0}  # players: {uid: {'wins', 'losses', 'streak', 'best_streak'}}


def _player(state, uid):
    p = state['players'].setdefault(str(uid), {'wins': 0, 'losses': 0,
                                               'streak': 0, 'best_streak': 0})
    for k in ('wins', 'losses', 'streak', 'best_streak'):
        p.setdefault(k, 0)
    return p


def record_result(state, winner_id, loser_id, now):
    """Записать исход: серии и лучшая серия обновляются. Возвращает (w_rec, l_rec)."""
    w = _player(state, winner_id)
    l = _player(state, loser_id)
    w['wins'] += 1
    w['streak'] += 1
    w['best_streak'] = max(w['best_streak'], w['streak'])
    l['losses'] += 1
    l['streak'] = 0
    w['last_at'] = now.isoformat()
    l['last_at'] = now.isoformat()
    state['total'] = int(state.get('total', 0)) + 1
    return w, l


def player_stats(state, uid):
    """Строка статистики: победы/поражения/винрейт/серия."""
    p = (state or {}).get('players', {}).get(str(uid))
    if not p:
        return None
    total = p['wins'] + p['losses']
    winrate = round(100 * p['wins'] / total) if total else 0
    return {
        'wins': p['wins'], 'losses': p['losses'], 'total': total,
        'winrate': winrate, 'streak': p['streak'], 'best_streak': p['best_streak'],
    }


def top_duels(state, limit=10):
    """[(uid, wins, losses)] — по победам, потом по винрейту."""
    rows = []
    for uid, p in (state or {}).get('players', {}).items():
        total = p.get('wins', 0) + p.get('losses', 0)
        if total and str(uid).isdigit():
            rows.append((int(uid), p.get('wins', 0), p.get('losses', 0)))
    rows.sort(key=lambda r: (-r[1], (r[2] - r[1]), r[0]))
    return rows[:limit]


def duel_summary(state, uid):
    """'5 побед · 3 поражения · винрейт 62%' одной строкой."""
    s = player_stats(state, uid)
    if not s:
        return 'дуэлей пока не было'
    return (f"{tf.spell(s['wins'], 'победа', 'победы', 'побед')} · "
            f"{tf.spell(s['losses'], 'поражение', 'поражения', 'поражений')} · "
            f"винрейт {s['winrate']}%"
            + (f" · серия {s['streak']}" if s['streak'] >= 2 else ''))


# ─── view вызова ────────────────────────────────────────────────────────────

class DuelView(discord.ui.View):
    """Кнопки вызова. Живут DUEL_TIMEOUT секунд — вызов штука мгновенная."""

    def __init__(self, cog, guild_id, challenger, opponent):
        super().__init__(timeout=DUEL_TIMEOUT)
        self.cog = cog
        self.guild_id = guild_id
        self.challenger = challenger
        self.opponent = opponent
        self.message = None

    async def interaction_check(self, interaction):
        if interaction.user.id not in (self.challenger.id, self.opponent.id):
            await interaction.response.send_message('Не ваша дуэль!', ephemeral=True)
            return False
        return True

    @discord.ui.button(label='Принять дуэль', style=discord.ButtonStyle.success)
    async def btn_accept(self, interaction, button):
        if interaction.user.id != self.opponent.id:
            await interaction.response.send_message(
                'Принять вызов может только вызванный!', ephemeral=True)
            return
        winner, loser = ((self.challenger, self.opponent) if random.random() < 0.5
                         else (self.opponent, self.challenger))
        state = self.cog._state(self.guild_id)
        w_rec, _l = record_result(state, winner.id, loser.id, datetime.now(UTC))
        self.cog._save(self.guild_id, state)

        for child in self.children:
            child.disabled = True
        embed = discord.Embed(
            title='Дуэль решена!',
            description=(f'{self.challenger.mention}  VS  {self.opponent.mention}\n\n'
                         f'Победа за {winner.mention} — серия побед: **{w_rec["streak"]}**.\n'
                         f'Итоги: `{duel_summary(state, winner.id)}`'),
            color=COLOR, timestamp=datetime.now(UTC),
        )
        await interaction.response.edit_message(embed=embed, view=self)
        log.info('duels: %s > %s на %s', winner.id, loser.id, self.guild_id)

    @discord.ui.button(label='Отказаться', style=discord.ButtonStyle.danger)
    async def btn_decline(self, interaction, button):
        if interaction.user.id != self.opponent.id:
            await interaction.response.send_message(
                'Отказаться может только вызванный!', ephemeral=True)
            return
        for child in self.children:
            child.disabled = True
        embed = discord.Embed(
            title='Дуэль отменена',
            description=f'{self.opponent.mention} отказался от поединка.',
            color=0x95A5A6, timestamp=datetime.now(UTC),
        )
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

    async def on_timeout(self):
        if self.message is not None:
            for child in self.children:
                child.disabled = True
            try:
                embed = self.message.embeds[0]
                embed.set_footer(text='Время вышло — вызов истёк')
                await self.message.edit(embed=embed, view=self)
            except (discord.NotFound, discord.HTTPException) as _ex:
                log.debug('duels: таймаут-апдейт не ушёл: %s', _ex)


# ─── ког ────────────────────────────────────────────────────────────────────

class Duels(commands.Cog):
    """Честные монеточные дуэли со статистикой."""

    def __init__(self, bot):
        self.bot = bot
        self.db = GuildData('duels')

    def _state(self, guild_id):
        return self.db.get(guild_id, 'state', empty_state()) or empty_state()

    def _save(self, guild_id, state):
        self.db.set(guild_id, 'state', state)

    @commands.hybrid_command(name='дуэль', aliases=['duel'],
                             description='Вызвать участника на дуэль (монетка 50/50)')
    async def cmd_duel(self, ctx, соперник: discord.Member):
        if соперник.bot:
            await ctx.reply('С ботами не дуэлимся — у них вместо крови электричество.',
                            mention_author=False)
            return
        if соперник.id == ctx.author.id:
            await ctx.reply('Дуэль с собой — это шахматы. Тут нельзя.', mention_author=False)
            return
        embed = discord.Embed(
            title='Вызов на дуэль!',
            description=(f'{ctx.author.mention} вызывает {соперник.mention}!\n'
                         f'Монетка честная: 50/50. У соперника {DUEL_TIMEOUT} секунд.'),
            color=COLOR, timestamp=datetime.now(UTC),
        )
        view = DuelView(self, ctx.guild.id, ctx.author, соперник)
        msg = await ctx.reply(embed=embed, view=view, mention_author=False)
        view.message = msg

    @commands.hybrid_command(name='дуэли', aliases=['duels'],
                             description='Статистика дуэлянта')
    async def cmd_stats(self, ctx, участник: discord.Member = None):
        member = участник or ctx.author
        s = player_stats(self._state(ctx.guild.id), member.id)
        if not s:
            await ctx.reply(f'У {member.mention if участник else "вас"} ещё не было дуэлей.',
                            mention_author=False)
            return
        embed = discord.Embed(
            title=f'Дуэли · {member.display_name}',
            description=(f'Победы: **{s["wins"]}** · Поражения: **{s["losses"]}**\n'
                         f'Винрейт: **{s["winrate"]}%**\n'
                         f'Текущая серия: **{s["streak"]}** · '
                         f'Лучшая серия: **{s["best_streak"]}**'),
            color=COLOR,
        )
        embed.set_thumbnail(url=member.display_avatar.url if member.display_avatar else None)
        await ctx.reply(embed=embed, mention_author=False)

    @commands.hybrid_command(name='дуэлтоп', aliases=['dueltop'],
                             description='Топ дуэлянтов сервера')
    async def cmd_top(self, ctx):
        rows = top_duels(self._state(ctx.guild.id), 10)
        if not rows:
            await ctx.reply('Дуэлей ещё не было — `/дуэль @кто-нибудь`!',
                            mention_author=False)
            return
        lines = [f'**{i}.** <@{uid}> — {tf.spell(w, "победа", "победы", "побед")}/{l} пораж.'
                 for i, (uid, w, l) in enumerate(rows, 1)]
        embed = discord.Embed(title='Топ дуэлянтов', description='\n'.join(lines),
                              color=COLOR)
        await ctx.reply(embed=embed, mention_author=False)


async def setup(bot):
    await bot.add_cog(Duels(bot))
