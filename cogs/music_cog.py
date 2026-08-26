"""
Music Cog — музыка Hakumo.
Включить трек, очередь, пауза/продолжить, пропуск, громкость, повтор.
Все ответы — в фирменном тёмно-золотом стиле (cogs/embed_utils).
"""

import discord
from discord.ext import commands
import random

from logger import get_logger
log = get_logger("music_cog")

from cogs.embed_utils import hakumo_embed, reply, plural


def shuffle_queue(queue: list) -> list:
    """Перемешать очередь, сохранив играющий трек первым (панельный API плеера)."""
    if len(queue) < 2:
        return list(queue)
    current = queue[0]
    rest = queue[1:]
    random.shuffle(rest)
    return [current] + rest


def remove_track(queue: list, index):
    """Убрать трек по номеру (1-based, как в !queue). Возвращает (ok, ошибка, удалённый трек)."""
    try:
        i = int(index)
    except (TypeError, ValueError):
        return False, 'Номер трека должен быть целым числом.', None
    if i < 1 or i > len(queue):
        return False, 'Нет трека с таким номером.', None
    return True, '', queue.pop(i - 1)


def _track_name(item: dict) -> str:
    """Красивое имя трека для списков."""
    q = str(item.get('title') or item.get('query') or 'Трек').strip()
    return q if len(q) <= 60 else q[:57] + '…'


class MusicCog(commands.Cog):
    """Музыкальные команды Hakumo"""

    def __init__(self, bot):
        self.bot = bot
        self.queues = {}

    def get_queue(self, guild_id: int) -> list:
        """Получить очередь сервера"""
        if guild_id not in self.queues:
            self.queues[guild_id] = []
        return self.queues[guild_id]

    async def _silent(self, ctx, title='Тишина в эфире', text='Сейчас ничего не играет. Включи трек: `!play <название>`'):
        await reply(ctx, 'music', title, text)

    @commands.command(name='play', aliases=['играй'])
    async def play(self, ctx, *, query: str):
        """Включить трек: !play <название или ссылка>"""
        if not ctx.author.voice:
            await reply(ctx, 'music', 'Ты не в войсе',
                        'Зайди в голосовой канал — и я подключусь к тебе.')
            return

        voice_channel = ctx.author.voice.channel
        if not ctx.voice_client:
            await voice_channel.connect()

        queue = self.get_queue(ctx.guild.id)
        queue.append({'query': query, 'requester': ctx.author})

        if len(queue) == 1:
            title, pos = 'Сейчас играет', 'сразу'
        else:
            title, pos = 'Добавлено в очередь', f'{len(queue)}-я'

        embed = hakumo_embed(
            'music', title, None,
            fields=[('Трек', f'**{_track_name(queue[-1])}**', False),
                    ('Позиция', pos, True),
                    ('Заказал', ctx.author.mention, True)],
            guild=ctx.guild, footer_extra='Музыка',
        )
        from cogs.icons import send_with_icon
        await send_with_icon(ctx, embed, 'music')

    @commands.command(name='pause', aliases=['пауза'])
    async def pause(self, ctx):
        """Поставить трек на паузу"""
        if not ctx.voice_client or not ctx.voice_client.is_playing():
            await self._silent(ctx)
            return
        ctx.voice_client.pause()
        await reply(ctx, 'music', 'Пауза',
                    'Трек на паузе. Продолжить: `!resume`',
                    footer_extra='Музыка')

    @commands.command(name='resume', aliases=['продолжить'])
    async def resume(self, ctx):
        """Продолжить воспроизведение трека"""
        if not ctx.voice_client:
            await self._silent(ctx)
            return
        if not ctx.voice_client.is_paused():
            await reply(ctx, 'music', 'Нечего разбудить',
                        'Сейчас на паузе ничего нет.', footer_extra='Музыка')
            return
        ctx.voice_client.resume()
        await reply(ctx, 'music', 'Снова играю',
                    'Трек продолжает звучать.', footer_extra='Музыка')

    @commands.command(name='skip', aliases=['дальше'])
    async def skip(self, ctx):
        """Пропустить трек"""
        if not ctx.voice_client or not ctx.voice_client.is_playing():
            await self._silent(ctx)
            return
        ctx.voice_client.stop()
        queue = self.get_queue(ctx.guild.id)
        left = max(0, len(queue) - 1)
        await reply(ctx, 'music', 'Трек пропущен',
                    f'В очереди осталось {left} {plural(left, "трек", "трека", "треков")}.',
                    footer_extra='Музыка')

    @commands.command(name='queue', aliases=['очередь'])
    async def queue(self, ctx):
        """Показать очередь"""
        queue = self.get_queue(ctx.guild.id)
        if not queue:
            await reply(ctx, 'music', 'Очередь пуста',
                        'Включи что-нибудь: `!play <название>`',
                        footer_extra='Музыка')
            return

        rows = []
        for i, song in enumerate(queue[:10], 1):
            mark = '▶' if i == 1 else f'`{i}.`'
            who = getattr(song.get('requester'), 'display_name', 'кто-то')
            rows.append(f'{mark} **{_track_name(song)}**\n└ {who}')
        more = len(queue) - 10
        if more > 0:
            rows.append(f'…и ещё **{more}** {plural(more, "трек", "трека", "треков")}')
        embed = hakumo_embed(
            'music', 'Очередь Hakumo', '\n'.join(rows),
            fields=[('Всего', f'{len(queue)} {plural(len(queue), "трек", "трека", "треков")}', True)],
            guild=ctx.guild, footer_extra='Музыка',
        )
        await ctx.send(embed=embed)

    @commands.command(name='nowplaying', aliases=['сейчас', 'np'])
    async def nowplaying(self, ctx):
        """Показать играющий трек"""
        queue = self.get_queue(ctx.guild.id)
        if not queue:
            await self._silent(ctx)
            return
        current = queue[0]
        embed = hakumo_embed(
            'music', 'Сейчас играет', f'## {_track_name(current)}',
            fields=[('Заказал', getattr(current.get('requester'), 'mention', '—'), True),
                    ('В очереди', f'{len(queue)}', True)],
            guild=ctx.guild, footer_extra='Музыка',
        )
        from cogs.icons import send_with_icon
        await send_with_icon(ctx, embed, 'music')

    @commands.command(name='leave', aliases=['выйти'])
    async def leave(self, ctx):
        """Выйти из голосового канала"""
        if not ctx.voice_client:
            await reply(ctx, 'music', 'Меня там нет',
                        'Я сейчас не в голосовом канале.', footer_extra='Музыка')
            return
        await ctx.voice_client.disconnect()
        if ctx.guild.id in self.queues:
            self.queues[ctx.guild.id] = []
        await reply(ctx, 'music', 'Отключился',
                    'Вышел из голосового канала, очередь очищена.',
                    footer_extra='Музыка')

    @commands.Cog.listener()
    async def on_ready(self):
        log.info("MusicCog загружен")


async def setup(bot):
    await bot.add_cog(MusicCog(bot))
