# -*- coding: utf-8 -*-
"""Рейтинг стаффа (Staff Rating Cog)
===================================
Участники оценивают работу модераторов от 1 до 5 со словом-комментарием.
Один человек — один голос за каждого из стаффа (новый голос заменяет
старый). Админ видит, кто из команды тянет сервер, а кто нет.

- /оценить @мод <1-5> [комментарий] — поставить оценку
- /рейтингмодов                     — таблица: средний балл, число голосов
- /зачетка @мод                     — последние комментарии и динамика

Хранилище — SQLite (GuildData 'staff_rating'). Метки — aware UTC.
"""
from datetime import datetime, timezone

import discord
from discord.ext import commands

from db import GuildData
from logger import get_logger
from services import text_format as tf

log = get_logger("staff_rating")

UTC = timezone.utc
COLOR = 0x9B59B6
MAX_COMMENT = 200
COMMENTS_KEEP = 30  # сколько свежих комментариев хранить на человека


# ─── чистые функции (покрыты тестом) ────────────────────────────────────────

def empty_state():
    return {'staff': {}}  # {staff_uid: {'votes': {voter_uid: score}, 'comments': []}}


def add_vote(state, voter_id, staff_id, score, comment='', now=None):
    """Голос за стаффа. Возвращает (статус, средний_балл_или_текст_ошибки).

    Статусы: 'ok' (новый), 'updated' (переголосовал), 'self', 'bad_score'.
    """
    if voter_id == staff_id:
        return 'self', 'себя не оцениваем'
    try:
        score = int(score)
    except (TypeError, ValueError):
        return 'bad_score', 'оценка — число от 1 до 5'
    if not 1 <= score <= 5:
        return 'bad_score', 'оценка — число от 1 до 5'

    staff = state['staff'].setdefault(str(staff_id), {'votes': {}, 'comments': []})
    votes = staff['votes']
    status = 'updated' if str(voter_id) in votes else 'ok'
    votes[str(voter_id)] = score

    comment = str(comment or '').strip()[:MAX_COMMENT]
    if comment and now is not None:
        staff['comments'].append({
            'voter': voter_id, 'score': score, 'text': comment,
            'at': now.isoformat(),
        })
        del staff['comments'][:-COMMENTS_KEEP]
    return status, round(_avg(votes), 2)


def _avg(votes):
    vals = [v for v in votes.values() if isinstance(v, int)]
    return sum(vals) / len(vals) if vals else 0.0


def staff_summary(state, staff_id):
    """{avg, votes, last_score} или None, если голосов нет."""
    staff = (state or {}).get('staff', {}).get(str(staff_id))
    if not staff or not staff.get('votes'):
        return None
    votes = staff['votes']
    return {'avg': round(_avg(votes), 2), 'votes': len(votes),
            'comments': staff.get('comments', [])}


def rating_rows(state, limit=15):
    """[(staff_id_int, avg, n_votes)] — по баллу, потом по числу голосов."""
    rows = []
    for uid, staff in (state or {}).get('staff', {}).items():
        votes = staff.get('votes', {})
        if votes and str(uid).isdigit():
            rows.append((int(uid), round(_avg(votes), 2), len(votes)))
    rows.sort(key=lambda r: (-r[1], -r[2], r[0]))
    return rows[:limit]


def score_stars(score):
    """4.2 -> '★★★★☆' (округление вверх с половины: 4.5 -> 5 звёзд)."""
    try:
        n = int(float(score) + 0.5)
    except (TypeError, ValueError):
        n = 0
    n = max(0, min(5, n))
    return '★' * n + '☆' * (5 - n)


# ─── ког ────────────────────────────────────────────────────────────────────

class StaffRating(commands.Cog):
    """Народный рейтинг модераторской команды."""

    def __init__(self, bot):
        self.bot = bot
        self.db = GuildData('staff_rating')

    def _state(self, guild_id):
        return self.db.get(guild_id, 'state', empty_state()) or empty_state()

    def _save(self, guild_id, state):
        self.db.set(guild_id, 'state', state)

    @staticmethod
    def _is_staff(member):
        perms = getattr(member, 'guild_permissions', None)
        return bool(perms and (perms.manage_messages or perms.kick_members
                               or perms.ban_members or perms.administrator))

    @commands.hybrid_command(name='оценить', aliases=['rate'],
                             description='Оценить модератора: /оценить @мод 1-5 [комментарий]')
    async def cmd_rate(self, ctx, модератор: discord.Member, оценка: int,
                       *, комментарий: str = ''):
        if модератор.bot:
            await ctx.reply('Бота оценивать не надо — он и так старается.',
                            mention_author=False)
            return
        if not self._is_staff(модератор):
            await ctx.reply(f'{модератор.mention} — не из модераторской команды.',
                            mention_author=False)
            return
        state = self._state(ctx.guild.id)
        status, value = add_vote(state, ctx.author.id, модератор.id, оценка,
                                 комментарий, datetime.now(UTC))
        if status in ('self', 'bad_score'):
            await ctx.reply(f'Не засчитано: {value}.', mention_author=False)
            return
        self._save(ctx.guild.id, state)
        word = 'обновлена' if status == 'updated' else 'принята'
        embed = discord.Embed(
            title=f'Оценка {word}',
            description=(f'{ctx.author.mention} → {модератор.mention}: '
                         f'**{score_stars(оценка)} ({int(оценка)}/5)**\n'
                         f'Средний балл модератора: **{value}**'
                         + (f'\nКомментарий: {комментарий[:150]}' if комментарий else '')),
            color=COLOR, timestamp=datetime.now(UTC),
        )
        await ctx.reply(embed=embed, mention_author=False)

    @commands.hybrid_command(name='рейтингмодов', aliases=['staffrating'],
                             description='Таблица рейтинга модераторов')
    async def cmd_table(self, ctx):
        rows = rating_rows(self._state(ctx.guild.id))
        if not rows:
            await ctx.reply('Оценок ещё нет — `/оценить @мод 5 спасибо за работу`.',
                            mention_author=False)
            return
        lines = []
        for i, (uid, avg, n) in enumerate(rows[:10], 1):
            lines.append(f'**{i}.** <@{uid}> — {score_stars(avg)} **{avg}** '
                         f'({tf.spell(n, "голос", "голоса", "голосов")})')
        embed = discord.Embed(title='Рейтинг модераторов', description='\n'.join(lines),
                              color=COLOR)
        await ctx.reply(embed=embed, mention_author=False)

    @commands.hybrid_command(name='зачетка', aliases=['staffcard'],
                             description='Зачётка модератора с комментариями')
    async def cmd_card(self, ctx, модератор: discord.Member):
        s = staff_summary(self._state(ctx.guild.id), модератор.id)
        if not s:
            await ctx.reply(f'У {модератор.mention} пока нет оценок.',
                            mention_author=False)
            return
        embed = discord.Embed(
            title=f'Зачётка · {модератор.display_name}',
            description=(f'{score_stars(s["avg"])} **{s["avg"]}** из 5 · '
                         f'{tf.spell(s["votes"], "голос", "голоса", "голосов")}'),
            color=COLOR,
        )
        for c in s['comments'][-5:]:
            embed.add_field(
                name=f'{c["score"]}/5 · {c["at"][:10]}',
                value=tf.clamp_text(c['text'], 200) or '—', inline=False)
        await ctx.reply(embed=embed, mention_author=False)


async def setup(bot):
    await bot.add_cog(StaffRating(bot))
