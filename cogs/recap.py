# -*- coding: utf-8 -*-
"""Рекап канала (Recap Cog)
==========================
«Что я пропустил за ночь?» — статистический разбор истории канала без AI:
кто писал, какие слова гремели, когда был пик, самая реактивная реплика.

- /recap [#канал] [часов] — сводка за период (по умолчанию 24 ч)
- /recap week [#канал]    — за неделю

Чистая статистика, никаких внешних API. Метки — aware UTC.
"""
import re
from collections import Counter
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands

from logger import get_logger
from services import text_format as tf

log = get_logger("recap")

UTC = timezone.utc
COLOR = 0x9B59B6

# русские стоп-слова — не считаются «темами разговора»
STOPWORDS = frozenset({
    'и', 'в', 'не', 'на', 'с', 'что', 'я', 'он', 'она', 'мы', 'вы', 'ты',
    'по', 'за', 'к', 'у', 'о', 'из', 'а', 'но', 'да', 'как', 'то', 'это',
    'все', 'так', 'его', 'её', 'их', 'уже', 'для', 'или', 'если', 'бы',
    'же', 'есть', 'был', 'была', 'были', 'было', 'от', 'до', 'при', 'со',
    'нет', 'тут', 'там', 'ну', 'вот', 'когда', 'кто', 'где', 'мне', 'тебя',
    'меня', 'сейчас', 'почему', 'можно', 'надо', 'куда', 'всем', 'всему',
    'этого', 'этой', 'этот', 'эта', 'ещё', 'под', 'над', 'про', 'без', 'через',
    'the', 'a', 'an', 'is', 'are', 'to', 'of', 'in', 'it', 'and', 'or',
})

_LINK_RE = re.compile(r'https?://\S+')


# ─── чистые функции (покрыты тестом) ────────────────────────────────────────

def normalize_message(msg):
    """Привести discord.Message-подобный объект к простому dict.

    Принимает и dict, и объект с атрибутами author/content/created_at.
    """
    if isinstance(msg, dict):
        out = dict(msg)
        created = out.get('created_at')
        if isinstance(created, str):
            created = datetime.fromisoformat(created)
        if created is not None and created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        out['created_at'] = created
        return out
    author = getattr(msg, 'author', None)
    created = getattr(msg, 'created_at', None)
    if created is not None and created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return {
        'author': str(author),
        'author_id': getattr(author, 'id', 0),
        'content': str(getattr(msg, 'content', '') or ''),
        'created_at': created,
        'bot': bool(getattr(author, 'bot', False)),
        'reactions': list(getattr(msg, 'reactions', []) or []),
    }


def content_words(content):
    """Слова контента без ссылок, короче 3 букв не считаем."""
    text = _LINK_RE.sub(' ', str(content or '').lower())
    return [w for w in tf.extract_words(text)
            if len(w) >= 3 and w not in STOPWORDS and not w.isdigit()]


def reaction_score(msg):
    """Суммарное число реакций на сообщении (dict или объект)."""
    if isinstance(msg, dict):
        reactions = msg.get('reactions', []) or []
    else:
        reactions = getattr(msg, 'reactions', None) or []
    total = 0
    for r in reactions:
        if isinstance(r, dict):
            total += int(r.get('count', 0) or 0)
        else:
            total += int(getattr(r, 'count', 0) or 0)
    return total


def build_recap(messages, hours=24, now=None):
    """Сердце рекапа — чистая статистика по списку сообщений.

    Возвращает {'total', 'unique_authors', 'top_authors', 'top_words',
                'busy_hour', 'avg_per_hour', 'hottest', 'links'}.
    """
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    hours = max(1, int(hours or 24))
    since = now - timedelta(hours=hours)

    authors = Counter()
    words = Counter()
    by_hour = Counter()
    total = 0
    links = 0
    hottest = None
    hottest_score = -1

    for raw in messages or []:
        msg = normalize_message(raw)
        ts = msg.get('created_at')
        if msg.get('bot'):
            continue
        if ts is not None and ts < since:
            continue
        total += 1
        name = msg.get('author') or '?'
        authors[name] += 1
        words.update(content_words(msg.get('content')))
        if ts is not None:
            by_hour[ts.hour] += 1
        if _LINK_RE.search(str(msg.get('content') or '')):
            links += 1
        score = reaction_score(msg)
        content = str(msg.get('content') or '').strip()
        if content and score > hottest_score:
            hottest_score = score
            hottest = {'author': name, 'content': content[:200], 'reactions': score}

    busy = by_hour.most_common(1)[0][0] if by_hour else None
    return {
        'total': total,
        'unique_authors': len(authors),
        'top_authors': authors.most_common(5),
        'top_words': words.most_common(8),
        'busy_hour': busy,
        'avg_per_hour': round(total / hours, 1),
        'hottest': hottest,
        'links': links,
    }


def recap_embed_fields(recap, hours):
    """Поля эмбеда собраны строками — покрыто тестом."""
    r = recap
    authors = ' · '.join(f'**{n}** ({c})' for n, c in r['top_authors'][:5]) or '—'
    words = ', '.join(f'{w} ({c})' for w, c in r['top_words'][:8]) or '—'
    busy = f"{r['busy_hour']:02d}:00–{r['busy_hour']:02d}:59 UTC" if r['busy_hour'] is not None else '—'
    hottest = r['hottest']
    hottest_txt = (f"**{hottest['author']}**: {hottest['content'][:150]}"
                   f" ({tf.spell(hottest['reactions'], 'реакция', 'реакции', 'реакций')})"
                   if hottest else '—')
    return [
        ('Сообщений', f"**{r['total']}** за {tf.spell(hours, 'час', 'часа', 'часов')} "
                      f"(среднее {r['avg_per_hour']}/час)"),
        ('Участников', f"**{r['unique_authors']}**"),
        ('Активные авторы', authors),
        ('Слова периода', words),
        ('Пик активности', busy),
        ('Самая заметная реплика', hottest_txt),
        ('Ссылок скинуто', str(r['links'])),
    ]


# ─── ког ────────────────────────────────────────────────────────────────────

class Recap(commands.Cog):
    """«Что я пропустил?» — статистика канала за период."""

    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name='recap', aliases=['рекап'],
                             description='Сводка активности канала за N часов')
    @commands.has_permissions(read_message_history=True)
    async def cmd_recap(self, ctx, канал: discord.TextChannel = None, часов: int = 24):
        await self._do_recap(ctx, канал or ctx.channel, часов)

    @commands.hybrid_command(name='recapweek', aliases=['рекапнеделя'],
                             description='Рекап канала за 7 дней')
    @commands.has_permissions(read_message_history=True)
    async def cmd_recap_week(self, ctx, канал: discord.TextChannel = None):
        await self._do_recap(ctx, канал or ctx.channel, 24 * 7)

    async def _do_recap(self, ctx, channel, часов):
        if not 1 <= часов <= 24 * 30:
            await ctx.reply('Период — от 1 до 720 часов (30 дней).',
                            mention_author=False)
            return
        async with ctx.typing():
            now = datetime.now(UTC)
            messages = []
            try:
                async for msg in channel.history(
                        limit=1000, after=now - timedelta(hours=часов)):
                    messages.append(msg)
            except discord.Forbidden:
                await ctx.reply(f'Нет доступа к истории {channel.mention}.',
                                mention_author=False)
                return
            except discord.HTTPException as _ex:
                await ctx.reply('Discord не отдал историю канала — попробуйте позже.',
                                mention_author=False)
                log.warning('recap: history %s: %s', channel.id, _ex)
                return
            recap = build_recap(messages, hours=часов, now=now)

        embed = discord.Embed(
            title=f'Рекап #{getattr(channel, "name", channel)} · {tf.spell(часов, "час", "часа", "часов")}',
            color=COLOR,
            timestamp=now,
        )
        if recap['total'] == 0:
            embed.description = 'За период тихо — сообщений не было.'
        else:
            for name, value in recap_embed_fields(recap, часов):
                embed.add_field(name=name, value=tf.clamp_text(value, 1024),
                                inline=name in ('Сообщений', 'Участников', 'Пик активности'))
        await ctx.reply(embed=embed, mention_author=False)


async def setup(bot):
    await bot.add_cog(Recap(bot))
