"""
Fun Cog
Развлекательные команды
"""

import discord
from discord.ext import commands
from datetime import datetime
import random
import aiohttp

from logger import get_logger
log = get_logger("fun_cog")


def _embed(title, desc, color=discord.Color.dark_grey(), footer=None, author=None):
    """Создаёт красивый развлекательный embed"""
    e = discord.Embed(
        title=title,
        description=desc,
        color=color,
        timestamp=datetime.now()
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

    @commands.command(name='8ball', aliases=['шар'])
    async def eightball(self, ctx, *, question: str):
        """Магический шар — ответит на твой вопрос"""
        responses = [
            "Определённо да.",
            "Точно да.",
            "Несомненно.",
            "Да, однозначно.",
            "Можешь быть уверен.",
            "Судя по всему, да.",
            "Скорее всего.",
            "Да.",
            "Знаки говорят — да.",
            "Ответ неясен, попробуй ещё.",
            "Спроси позже.",
            "Лучше сейчас не говорить.",
            "Пока не могу предсказать.",
            "Сосредоточься и спроси снова.",
            "Не рассчитывай на это.",
            "Мой ответ — нет.",
            "Источники говорят — нет.",
            "Судя по всему, нет.",
            "Очень сомнительно.",
            "Нет."
        ]
        e = _embed(
            "🎱 Магический шар",
            f"**Вопрос:** {question}\n\n**Ответ:** {random.choice(responses)}",
            discord.Color.dark_grey(),
            author=ctx.author
        )
        await ctx.send(embed=e)

    @commands.command(name='coinflip', aliases=['монета'])
    async def coinflip(self, ctx):
        """Подбросить монету"""
        result = random.choice(["Орёл", "Решка"])
        e = _embed(
            "🪙 Монетка",
            f"**Результат:** {result}",
            discord.Color.dark_grey(),
            footer="Попробуй удачу!",
            author=ctx.author
        )
        await ctx.send(embed=e)

    @commands.command(name='dice', aliases=['кость'])
    async def dice(self, ctx, sides: int = 6):
        """Бросить кость"""
        if sides < 2:
            await ctx.send("🎲 Кость должна быть минимум 2-х гранная!")
            return
        if sides > 10000:
            await ctx.send("🎲 Кость максимум 10000 гранная!")
            return

        result = random.randint(1, sides)
        e = _embed(
            "🎲 Бросок кости",
            f"**Кость с {sides} гранями:** `{result}`",
            discord.Color.dark_grey(),
            footer="Удачи!",
            author=ctx.author
        )
        await ctx.send(embed=e)

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
            data = await self._fetch_json("https://meme-api.com/gimme")
            if not data or not data.get('url'):
                raise ValueError("Мем не получен")
            e = _embed(
                f"😂 {data.get('title', 'Случайный мем')}",
                f"**Сабреддит:** r/{data.get('subreddit', '?')}  ·  **👍** {data.get('ups', 0)}",
                discord.Color.dark_grey(),
                footer=f"Просил: {ctx.author}",
                author=ctx.author
            )
            e.set_image(url=data['url'])
        except Exception:
            e = _embed(
                "😂 Случайный мем",
                "Не удалось загрузить мем, попробуй ещё!",
                discord.Color.red(),
                author=ctx.author
            )
        await ctx.send(embed=e)

    @commands.command(name='joke', aliases=['шутка'])
    async def joke(self, ctx):
        """Случайная шутка"""
        jokes = [
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
        e = _embed(
            "😄 Случайная шутка",
            f"```{random.choice(jokes)}```",
            discord.Color.dark_grey(),
            footer="Смех бесплатный!",
            author=ctx.author
        )
        await ctx.send(embed=e)

    @commands.command(name='cat', aliases=['кот'])
    async def cat(self, ctx):
        """Случайная фотография кота"""
        try:
            data = await self._fetch_json("https://aws.random.cat/meow")
            if not data or not data.get('file'):
                raise ValueError("Кот не получен")
            e = _embed(
                "🐱 Случайный кот",
                "Вот тебе милый котик!",
                discord.Color.dark_grey(),
                footer=f"Просил: {ctx.author}",
                author=ctx.author
            )
            e.set_image(url=data['file'])
        except Exception:
            e = _embed(
                "🐱 Случайный кот",
                "Не удалось загрузить кота, попробуй ещё!",
                discord.Color.red(),
                author=ctx.author
            )
        await ctx.send(embed=e)

    @commands.command(name='dog', aliases=['собака'])
    async def dog(self, ctx):
        """Случайная фотография собаки"""
        try:
            data = await self._fetch_json("https://dog.ceo/api/breeds/image/random")
            if not data or not data.get('message'):
                raise ValueError("Собака не получена")
            e = _embed(
                "🐶 Случайная собака",
                "Вот тебе милый пёсик!",
                discord.Color.dark_grey(),
                footer=f"Просил: {ctx.author}",
                author=ctx.author
            )
            e.set_image(url=data['message'])
        except Exception:
            e = _embed(
                "🐶 Случайная собака",
                "Не удалось загрузить собаку, попробуй ещё!",
                discord.Color.red(),
                author=ctx.author
            )
        await ctx.send(embed=e)

    @commands.command(name='quote', aliases=['цитата'])
    async def quote(self, ctx):
        """Случайная цитата"""
        quotes = [
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
        e = _embed(
            "💭 Случайная цитата",
            f"*\"{random.choice(quotes)}\"*",
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
