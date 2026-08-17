"""
Fun Cog
Развлекательные команды
"""

import discord
from discord.ext import commands
from datetime import datetime, timezone
import random
import aiohttp

from logger import get_logger
log = get_logger("fun_cog")

MEME_URL = "https://meme-api.com/gimme"
CAT_URL = "https://aws.random.cat/meow"
DOG_URL = "https://dog.ceo/api/breeds/image/random"

MEME_ERR = "Не удалось загрузить мем, попробуй ещё!"
CAT_ERR = "Не удалось загрузить кота, попробуй ещё!"
DOG_ERR = "Не удалось загрузить собаку, попробуй ещё!"

JOKES = [
    "Почему программист носит очки? Потому что не видит C#!",
    "SQL-запрос заходит в бар, подходит к двум таблицам и спрашивает: 'Можно JOIN?'",
    "Было 99 багов, исправил один — стало 127.",
    "Почему программист работает в темноте? Потому что светлые баги!",
    "Программист бросил жену, потому что не мог с ней сделать интерфейс.",
    "Почему программисты любят отладку? Потому что жизнь полна решений.",
    "Почему программист работает из дома? Потому что дома больше кэша!",
    "Почему пользователи Python счастливее? Потому что всё решается через import!",
    "Программист женился на компьютере — потому что хорошо ладили!",
    "Почему программисты плохо спят? Потому что видят null и пустые строки."
]

QUOTES = [
    "Жизнь коротка, искусство вечно.",
    "Знание — сила.",
    "Успех — это встреча подготовки с возможностью.",
    "Будущее зависит от сегодняшней подготовки.",
    "Неудача — приправа к успеху.",
    "Если можешь мечтать, можешь сделать.",
    "Успех — это повторение маленьких усилий каждый день.",
    "Трудности делают нас сильнее.",
    "Успех — это не сдаваться.",
    "Жизнь — это путешествие, а не пункт назначения.",
    "Лучшая месть — огромный успех.",
    "Сомнение — начало мудрости."
]


def random_joke(chooser=None):
    """Случайная шутка из того же списка, что у !joke."""
    return (chooser or random.choice)(JOKES)


def random_quote(chooser=None):
    """Случайная цитата из того же списка, что у !quote."""
    return (chooser or random.choice)(QUOTES)


def parse_meme(data):
    """Разбор ответа meme-api 1:1 команде !meme; непригодный ответ → None."""
    if not data or not data.get('url'):
        return None
    return {
        'title': data.get('title', 'Случайный мем'),
        'subreddit': data.get('subreddit', '?'),
        'ups': data.get('ups', 0),
        'image': data['url'],
    }


def parse_cat(data):
    """Разбор ответа random.cat 1:1 команде !cat; непригодный ответ → None."""
    if not data or not data.get('file'):
        return None
    return {'image': data['file'], 'text': 'Вот тебе милый котик!'}


def parse_dog(data):
    """Разбор ответа dog.ceo 1:1 команде !dog; непригодный ответ → None."""
    if not data or not data.get('message'):
        return None
    return {'image': data['message'], 'text': 'Вот тебе милый пёсик!'}


def _embed(title, desc, color=discord.Color.dark_grey(), footer=None, author=None):
    """Создаёт красивый развлекательный embed"""
    e = discord.Embed(
        title=title,
        description=desc,
        color=color,
        timestamp=datetime.now(timezone.utc)
    )
    if author:
        e.set_author(name=author.display_name, icon_url=author.display_avatar.url)
    if footer:
        e.set_footer(text=footer)
    return e


class FunCog(commands.Cog):
    """Развлекательные команды"""

    def __init__(self, bot):
        self.bot = bot

    # ПРИМЕЧАНИЕ: 8ball / coinflip / dice убраны из этого файла —
    # slash-команды с теми же именами конфликтовали с cogs/minigames.py и
    # они мешали полной загрузке minigames-кога.

    async def _fetch_json(self, url):
        """Безопасно получает данные из API"""
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return None
                return await resp.json(content_type=None)

    @commands.command(name='meme')
    async def meme(self, ctx):
        """Случайный мем"""
        try:
            item = parse_meme(await self._fetch_json(MEME_URL))
            if item is None:
                raise ValueError("Мем не получен")
            e = _embed(
                f"😂 {item['title']}",
                f"**Сабреддит:** r/{item['subreddit']}  ·  **👍** {item['ups']}",
                discord.Color.dark_grey(),
                footer=f"Просил: {ctx.author}",
                author=ctx.author
            )
            e.set_image(url=item['image'])
        except Exception:
            e = _embed(
                "😂 Случайный мем",
                MEME_ERR,
                discord.Color.red(),
                author=ctx.author
            )
        await ctx.send(embed=e)

    @commands.command(name='joke', aliases=['шутка'])
    async def joke(self, ctx):
        """Случайная шутка"""
        e = _embed(
            "😄 Случайная шутка",
            f"```{random_joke()}```",
            discord.Color.dark_grey(),
            footer="Смех бесплатный!",
            author=ctx.author
        )
        await ctx.send(embed=e)

    @commands.command(name='cat', aliases=['кот'])
    async def cat(self, ctx):
        """Случайная фотография кота"""
        try:
            item = parse_cat(await self._fetch_json(CAT_URL))
            if item is None:
                raise ValueError("Кот не получен")
            e = _embed(
                "🐱 Случайный кот",
                item['text'],
                discord.Color.dark_grey(),
                footer=f"Просил: {ctx.author}",
                author=ctx.author
            )
            e.set_image(url=item['image'])
        except Exception:
            e = _embed(
                "🐱 Случайный кот",
                CAT_ERR,
                discord.Color.red(),
                author=ctx.author
            )
        await ctx.send(embed=e)

    @commands.command(name='dog', aliases=['собака'])
    async def dog(self, ctx):
        """Случайная фотография собаки"""
        try:
            item = parse_dog(await self._fetch_json(DOG_URL))
            if item is None:
                raise ValueError("Собака не получена")
            e = _embed(
                "🐶 Случайная собака",
                item['text'],
                discord.Color.dark_grey(),
                footer=f"Просил: {ctx.author}",
                author=ctx.author
            )
            e.set_image(url=item['image'])
        except Exception:
            e = _embed(
                "🐶 Случайная собака",
                DOG_ERR,
                discord.Color.red(),
                author=ctx.author
            )
        await ctx.send(embed=e)

    @commands.command(name='quote', aliases=['цитата'])
    async def quote(self, ctx):
        """Случайная цитата"""
        e = _embed(
            "💭 Случайная цитата",
            f"*\"{random_quote()}\"*",
            discord.Color.dark_grey(),
            footer=f"Просил: {ctx.author}",
            author=ctx.author
        )
        await ctx.send(embed=e)

    @commands.Cog.listener()
    async def on_ready(self):
        """Когда бот готов"""
        log.info("FunCog loaded")


async def setup(bot):
    await bot.add_cog(FunCog(bot))
