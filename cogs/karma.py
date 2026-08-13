# -*- coding: utf-8 -*-
"""Карма (Karma Cog)
===================
Награды «спасибо» соседям по серверу: помог бро — отметь его, очки копятся
в таблицу лидеров. Реакция-➕ на чужом сообщении тоже засчитывает очко
(свои — не считаются, накрутка блокируется кулдауном на пару).

- /спасибо @user [причина]  — +1 кармы
- /карма [@user]            — карточка очков
- /карматоп                 — топ-10 сервера

Хранилище — SQLite (GuildData 'karma'). Метки — aware UTC.
"""
from datetime import datetime, timezone

import discord
from discord.ext import commands

from db import GuildData
from logger import get_logger
from services import text_format as tf

log = get_logger("karma")

UTC = timezone.utc
COLOR = 0xF1C40F
THANK_COOLDOWN = 60  # секунд между «спасибо» одной и той же паре


# ─── чистые функции (покрыты тестом) ────────────────────────────────────────

def empty_state():
    return {'scores': {}, 'thanks': []}


def apply_rep(state, target_id, amount=1):
    """Накинуть очков. Возвращает новый счёт цели."""
    scores = state.setdefault('scores', {})
    key = str(target_id)
    scores[key] = int(scores.get(key, 0)) + int(amount)
    return scores[key]


def top_rows(state, limit=10):
    """[(user_id_int, score), ...] по убыванию."""
    scores = (state or {}).get('scores', {})
    rows = [(int(uid), int(score)) for uid, score in scores.items()
            if str(uid).isdigit() and int(score) != 0]
    rows.sort(key=lambda r: (-r[1], r[0]))
    return rows[:limit]


def get_score(state, user_id):
    return int((state or {}).get('scores', {}).get(str(user_id), 0))


def can_thank(state, giver_id, target_id, now, cooldown=THANK_COOLDOWN):
    """Можно ли поблагодарить: не себя и не чаще cooldown на пару.
    Возвращает (ok, осталось_сек)."""
    if giver_id == target_id:
        return False, 0
    for th in reversed((state or {}).get('thanks', [])):
        if th.get('giver') == giver_id and th.get('target') == target_id:
            try:
                when = datetime.fromisoformat(th.get('at', ''))
            except ValueError as _ex:
                log.debug('karma: битая метка в журнале благодарностей: %s', _ex)
                continue
            if when.tzinfo is None:
                when = when.replace(tzinfo=UTC)
            left = cooldown - (now - when).total_seconds()
            if left > 0:
                return False, int(left)
            break  # последняя запись просрочена — старше уже не смотрим
    return True, 0


def thank(state, giver_id, target_id, now, reason='', cooldown=THANK_COOLDOWN):
    """Благодарность: (state, ok, новый_счёт_или_остаток)."""
    ok, left = can_thank(state, giver_id, target_id, now, cooldown)
    if not ok:
        return state, False, left
    total = apply_rep(state, target_id, 1)
    thanks = state.setdefault('thanks', [])
    thanks.append({'giver': giver_id, 'target': target_id,
                   'at': now.isoformat(), 'reason': str(reason)[:150]})
    del thanks[:-200]  # журнал не раздуваем — хватает хвоста для кулдауна
    return state, True, total


# ─── ког ────────────────────────────────────────────────────────────────────

class Karma(commands.Cog):
    """Очки благодарности между участниками."""

    def __init__(self, bot):
        self.bot = bot
        self.db = GuildData('karma')

    def _state(self, guild_id):
        return self.db.get(guild_id, 'state', empty_state()) or empty_state()

    def _save(self, guild_id, state):
        self.db.set(guild_id, 'state', state)

    # ---- реакция ➕ = спасибо ----
    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        msg = reaction.message
        if not msg.guild or user.bot or msg.author.bot:
            return
        if str(reaction.emoji) not in ('➕', '👍'):
            return
        if msg.author.id == user.id:
            return
        state = self._state(msg.guild.id)
        state, ok, total = thank(state, user.id, msg.author.id, datetime.now(UTC),
                                 reason='реакция')
        if ok:
            self._save(msg.guild.id, state)
            log.debug('karma: +1 %s от %s (всего %s)', msg.author.id, user.id, total)

    # ---- команды ----
    @commands.hybrid_command(name='спасибо', aliases=['thanks', 'thank'],
                             description='Дать +1 кармы участнику')
    async def cmd_thanks(self, ctx, участник: discord.Member, *, причина: str = ''):
        if участник.bot:
            await ctx.reply('Ботам карму не выдаём — они и так стараются.',
                            mention_author=False)
            return
        if участник.id == ctx.author.id:
            await ctx.reply('Себе спасибо не говорят — скромность!', mention_author=False)
            return
        state = self._state(ctx.guild.id)
        state, ok, value = thank(state, ctx.author.id, участник.id,
                                 datetime.now(UTC), причина)
        if not ok:
            await ctx.reply(f'Этого человека вы уже благодарили недавно — '
                            f'подождите ещё {tf.fmt_seconds(value)}.',
                            mention_author=False)
            return
        self._save(ctx.guild.id, state)
        embed = discord.Embed(
            title='Карма выдана',
            description=(f'{ctx.author.mention} → {участник.mention}: **+1**'
                         f' (всего **{value}**)'
                         + (f'\nЗа: {причина[:150]}' if причина else '')),
            color=COLOR, timestamp=datetime.now(UTC),
        )
        await ctx.reply(embed=embed, mention_author=False)

    @commands.hybrid_command(name='карма', aliases=['karma'],
                             description='Карточка кармы')
    async def cmd_card(self, ctx, участник: discord.Member = None):
        member = участник or ctx.author
        state = self._state(ctx.guild.id)
        score = get_score(state, member.id)
        place = next((i for i, (uid, _s) in enumerate(top_rows(state, 10_000), 1)
                      if uid == member.id), None)
        embed = discord.Embed(
            title=f'Карма · {member.display_name}',
            description=(f'Очков: **{score}**\n'
                         f'Место: **{f"#{place}" if place else "вне топа"}**'),
            color=COLOR,
        )
        embed.set_thumbnail(url=member.display_avatar.url if member.display_avatar else None)
        await ctx.reply(embed=embed, mention_author=False)

    @commands.hybrid_command(name='карматоп', aliases=['karmatop'],
                             description='Топ-10 по карме')
    async def cmd_top(self, ctx):
        rows = top_rows(self._state(ctx.guild.id), 10)
        if not rows:
            await ctx.reply('Кармы пока ни у кого нет — начните говорить спасибо!',
                            mention_author=False)
            return
        lines = []
        for i, (uid, score) in enumerate(rows, 1):
            lines.append(f'**{i}.** <@{uid}> — {tf.spell(score, "очко", "очка", "очков")}')
        embed = discord.Embed(title='Топ кармы', description='\n'.join(lines),
                              color=COLOR)
        await ctx.reply(embed=embed, mention_author=False)


async def setup(bot):
    await bot.add_cog(Karma(bot))
