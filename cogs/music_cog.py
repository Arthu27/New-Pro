# -*- coding: utf-8 -*-
"""
Music Cog — музыка Hakumo.

Команда одна — /play <название или ссылка> (/play без аргументов вежливо
подскажет формат — это не ошибка). Всё управление — кнопками на пульте,
который появляется автоматически под ответом /play:

    Пауза/Играть · Скип · Стоп · −10% / +10% · Повтор · Перемешать · Очередь

Отдельных /pause, /skip, /queue и прочих музыкальных команд больше нет —
их место занял пульт. Пульт persistent: кнопки работают и после рестарта
бота. Ответы — в фирменном тёмно-золотом стиле (cogs/embed_utils).

Воспроизведение: /play принимает и ссылку (youtube/vk…), и название —
принимает всё, что понимает yt-dlp; название ищется первым результатом
ytsearch1. Прямой поток отдаётся в discord.FFmpegPCMAudio (нужен ffmpeg
на сервере, путь можно задать FFMPEG_BINARY в .env). Очередь играет
автоматически: после трека включается следующий; «Скип» и «Стоп» работают
как раньше. Недоступная ссылка/нет ffmpeg — вежливое сообщение в канал,
а не тишина.
"""

import asyncio
import os
import random
import re
import shutil

import discord
from discord import app_commands
from discord.ext import commands

from logger import get_logger
log = get_logger("music_cog")

from cogs.embed_utils import hakumo_embed, reply, plural, InterCtx

_VOLUME_STEP = 10
_VOLUME_MIN = 0
_VOLUME_MAX = 200

# Прямые ссылки и поисковые запросы: yt-dlp сам понимает YouTube/VK и т.д.,
# для названий ищем первый результат ytsearch1:<запрос>.
_URL_RE = re.compile(r'^https?://', re.IGNORECASE)


def shuffle_queue(queue: list) -> list:
    """Перемешать очередь, сохранив играющий трек первым (панельный API плеера)."""
    if len(queue) < 2:
        return list(queue)
    current = queue[0]
    rest = queue[1:]
    random.shuffle(rest)
    return [current] + rest


def remove_track(queue: list, index):
    """Убрать трек по номеру (1-based, как в списке очереди). Возвращает (ok, ошибка, удалённый трек)."""
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


class MusicControlsView(discord.ui.View):
    """Пульт музыки — появляется автоматически под ответом /play.

    State-less и persistent (custom_id фиксированы): любые кнопки пульта
    любой давности продолжают работать, в том числе после рестарта бота.
    Вся логика — у MusicCog, пульт только делегирует.
    """

    def __init__(self):
        super().__init__(timeout=None)

    # ── инфраструктура ────────────────────────────────────────────────────
    @staticmethod
    def _cog(interaction: discord.Interaction):
        return interaction.client.get_cog('MusicCog') if interaction.client else None

    @staticmethod
    async def _say(interaction: discord.Interaction, title, text):
        """Короткий фирменный отлик на нажатие — всегда ephemeral."""
        await interaction.response.send_message(
            embed=hakumo_embed('music', title, text,
                               guild=interaction.guild, footer_extra='Музыка'),
            ephemeral=True)

    async def _guard(self, interaction: discord.Interaction):
        """(cog, vc, queue) либо None — с вежливым отликом вместо тишины."""
        cog = self._cog(interaction)
        if cog is None:
            await interaction.response.send_message(
                'Музыкальный модуль сейчас недоступен — попробуйте через минуту.',
                ephemeral=True)
            return None
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                'Пульт работает только на сервере.', ephemeral=True)
            return None
        vc = guild.voice_client
        queue = cog.get_queue(guild.id)
        return cog, vc, queue

    @staticmethod
    def _in_my_channel(interaction: discord.Interaction, vc) -> bool:
        """Управлять транспортом может только сидящий с ботом в одном войсе."""
        if vc is None:
            return False
        voice = getattr(interaction.user, 'voice', None)
        return bool(voice and voice.channel and vc.channel
                    and voice.channel.id == vc.channel.id)

    async def _transport_guard(self, interaction: discord.Interaction):
        """_guard + проверка «ты с ботом в одном войсе»."""
        found = await self._guard(interaction)
        if found is None:
            return None
        cog, vc, queue = found
        if not self._in_my_channel(interaction, vc):
            await interaction.response.send_message(
                'Этим пультом управляют из голосового канала, где я играю.',
                ephemeral=True)
            return None
        return cog, vc, queue

    # ── транспорт ─────────────────────────────────────────────────────────
    @discord.ui.button(label='Пауза / Играть', emoji='⏯', custom_id='music:toggle',
                       style=discord.ButtonStyle.primary, row=0)
    async def btn_toggle(self, interaction: discord.Interaction, button):
        found = await self._transport_guard(interaction)
        if found is None:
            return
        cog, vc, queue = found
        if vc.is_paused():
            vc.resume()
            await self._say(interaction, 'Снова играю', f'Продолжаю: **{_track_name(queue[0])}**'
                            if queue else 'Продолжаю воспроизведение.')
        elif vc.is_playing():
            vc.pause()
            await self._say(interaction, 'Пауза', 'Нажми сюда же, когда захочешь продолжить.')
        else:
            await self._say(interaction, 'Тишина в эфире',
                            'Сейчас ничего не играет. Включи трек: `/play <название>`')

    @discord.ui.button(label='Скип', emoji='⏭', custom_id='music:skip',
                       style=discord.ButtonStyle.secondary, row=0)
    async def btn_skip(self, interaction: discord.Interaction, button):
        found = await self._transport_guard(interaction)
        if found is None:
            return
        cog, vc, queue = found
        if not queue:
            await self._say(interaction, 'Тишина в эфире',
                            'Очередь пуста — скипать нечего. Включи трек: `/play <название>`')
            return
        gone = queue.pop(0)
        if cog.is_repeat(interaction.guild.id):
            queue.append(gone)  # повтор: ушедший трек встаёт в конец
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()  # движок дернёт следующий трек очереди
        if queue:
            await self._say(interaction, 'Трек пропущен',
                            f'Дальше: **{_track_name(queue[0])}** '
                            f'(в очереди {len(queue)} {plural(len(queue), "трек", "трека", "треков")}).')
        else:
            await self._say(interaction, 'Трек пропущен',
                            'Это был последний трек — очередь пуста.')

    @discord.ui.button(label='Стоп', emoji='⏹', custom_id='music:stop',
                       style=discord.ButtonStyle.danger, row=0)
    async def btn_stop(self, interaction: discord.Interaction, button):
        found = await self._guard(interaction)
        if found is None:
            return
        cog, vc, queue = found
        cog.queues[interaction.guild.id] = []
        cog.set_repeat(interaction.guild.id, False)
        if vc is not None:
            try:
                await vc.disconnect()
            except Exception as _ex:
                log.debug('music: stop-disconnect: %s', _ex)
        await self._say(interaction, 'Остановлено',
                        'Вышел из голосового канала, очередь очищена — '
                        'до связи! Включить снова: `/play <название>`')

    # ── громкость ─────────────────────────────────────────────────────────
    async def _volume(self, interaction: discord.Interaction, delta: int):
        found = await self._transport_guard(interaction)
        if found is None:
            return
        cog, vc, queue = found
        vol = cog.shift_volume(interaction.guild.id, delta)
        if vc is not None and getattr(vc, 'source', None) is not None:
            try:
                vc.source.volume = vol / 100
            except Exception as _ex:
                log.debug('music: volume set: %s', _ex)
        await self._say(interaction, 'Громкость', f'Теперь **{vol}%** (шаг {_VOLUME_STEP}%).')

    @discord.ui.button(label='−10%', emoji='🔉', custom_id='music:voldown',
                       style=discord.ButtonStyle.secondary, row=0)
    async def btn_voldown(self, interaction: discord.Interaction, button):
        await self._volume(interaction, -_VOLUME_STEP)

    @discord.ui.button(label='+10%', emoji='🔊', custom_id='music:volup',
                       style=discord.ButtonStyle.secondary, row=0)
    async def btn_volup(self, interaction: discord.Interaction, button):
        await self._volume(interaction, _VOLUME_STEP)

    # ── очередь и режимы ──────────────────────────────────────────────────
    @discord.ui.button(label='Повтор', emoji='🔁', custom_id='music:repeat',
                       style=discord.ButtonStyle.secondary, row=1)
    async def btn_repeat(self, interaction: discord.Interaction, button):
        found = await self._guard(interaction)
        if found is None:
            return
        cog, vc, queue = found
        on = cog.toggle_repeat(interaction.guild.id)
        await self._say(interaction, 'Повтор',
                        ('Включён: скипнутый трек возвращается в конец очереди.'
                         if on else 'Выключен: играем дальше по списку.'))

    @discord.ui.button(label='Перемешать', emoji='🔀', custom_id='music:shuffle',
                       style=discord.ButtonStyle.secondary, row=1)
    async def btn_shuffle(self, interaction: discord.Interaction, button):
        found = await self._guard(interaction)
        if found is None:
            return
        cog, vc, queue = found
        if len(queue) < 2:
            await self._say(interaction, 'Нечего мешать',
                            'В очереди должно быть минимум 2 трека.')
            return
        cog.queues[interaction.guild.id] = shuffle_queue(queue)
        await self._say(interaction, 'Перемешано',
                        'Играющий трек остался, хвост переупорядочен случайно.')

    @discord.ui.button(label='Очередь', emoji='📜', custom_id='music:queue',
                       style=discord.ButtonStyle.secondary, row=1)
    async def btn_queue(self, interaction: discord.Interaction, button):
        found = await self._guard(interaction)
        if found is None:
            return
        cog, vc, queue = found
        if not queue:
            await self._say(interaction, 'Очередь пуста',
                            'Включи что-нибудь: `/play <название>`')
            return
        rows = []
        for i, song in enumerate(queue[:10], 1):
            mark = '▶' if i == 1 else f'`{i}.`'
            who = getattr(song.get('requester'), 'display_name', 'кто-то')
            rows.append(f'{mark} **{_track_name(song)}**\n└ {who}')
        more = len(queue) - 10
        if more > 0:
            rows.append(f'…и ещё **{more}** {plural(more, "трек", "трека", "треков")}')
        extra = 'Повтор: вкл' if cog.is_repeat(interaction.guild.id) else 'Повтор: выкл'
        await interaction.response.send_message(
            embed=hakumo_embed(
                'music', 'Очередь Hakumo', '\n'.join(rows),
                fields=[('Всего', f'{len(queue)} {plural(len(queue), "трек", "трека", "треков")}', True)],
                guild=interaction.guild, footer_extra=f'Музыка · {extra}'),
            ephemeral=True)


class MusicCog(commands.Cog):
    """Музыка Hakumo: одна команда /play + кнопочный пульт."""

    def __init__(self, bot):
        self.bot = bot
        self.queues = {}
        self._repeats = set()   # gid → повтор очереди включён
        self._volumes = {}      # gid → 0..200 %
        self._playing_guilds = set()   # gid, где сейчас что-то звучит
        self._current_track = {}       # gid → track, который сейчас играет

    # ── движок воспроизведения ───────────────────────────────────────────
    @staticmethod
    def _ffmpeg_binary():
        """ffmpeg для декодирования: единый детектор services/ffmpeg_probe.

        Ищет в FFMPEG_BINARY (.env), системном PATH и типичных местах
        установки (Windows: winget/choco/scoop/Program Files/рядом с ботом;
        Linux: /usr/bin, /usr/local/bin, /opt). Раньше на Windows VDS ffmpeg
        часто лежал на диске, но не в PATH — музыка молча не играла.
        """
        try:
            from services.ffmpeg_probe import find_ffmpeg
            found = find_ffmpeg()   # .env (FFMPEG_BINARY) + PATH + типичные места
            if found:
                return found
        except Exception as _ex:
            log.debug('music: ffmpeg_probe недоступен (%s) — пробую PATH', _ex)
        # запасной вариант — PATH (минимальные окружения/тесты)
        return shutil.which('ffmpeg') or shutil.which('ffmpeg.exe')

    async def _resolve_stream(self, query: str):
        """yt-dlp: ссылка или поиск → (прямой аудио-url, название трека).

        Ссылки из /play принимаются как есть; обычное название ищется
        первым результатом ytsearch1. Бросает исключение, если трек
        не найден или библиотека недоступна.
        """
        try:
            import yt_dlp
        except ImportError as _e:
            raise ImportError(
                'на сервере не установлена библиотека yt-dlp '
                '(выполни `pip install -r requirements.txt` и перезапусти бота)')
        target = query if _URL_RE.match(query) else f'ytsearch1:{query}'
        opts = {
            'format': 'bestaudio/best',
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'nocheckcertificate': True,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = await asyncio.to_thread(ydl.extract_info, target, download=False)
        if info is None:
            raise ValueError('трек не найден')
        if isinstance(info, dict) and info.get('_type') == 'playlist' and info.get('entries'):
            info = info['entries'][0]
        if not isinstance(info, dict):
            raise ValueError('трек не найден')
        url = info.get('url') or info.get('webpage_url') or ''
        title = (info.get('title') or query).strip()
        if not url:
            raise ValueError('не удалось получить поток аудио')
        return url, title

    def _new_source(self, url: str):
        return discord.FFmpegPCMAudio(
            url,
            before_options='-reconnect 1 -reconnect_streamed 1 '
                           '-reconnect_delay_max 5 -nostdin',
            options='-vn',
            executable=self._ffmpeg_binary() or 'ffmpeg',
        )

    async def _announce(self, guild, track, kind, title, text):
        """Играющий/ошибочный трек — короткое сообщение в канал команды."""
        channel = None
        cid = track.get('channel_id')
        if cid and guild is not None:
            channel = discord.utils.get(guild.text_channels, id=int(cid))
        if channel is None:
            return
        try:
            await channel.send(embed=hakumo_embed(
                kind, title, text, guild=guild, footer_extra='Музыка'))
        except Exception as _ex:
            log.debug('music: announce: %s', _ex)

    async def _play_next(self, guild_id, ctx=None):
        """Запустить первый трек очереди, если ничего не играет.

        Возвращает True, если воспроизведение запущено (или уже идёт).
        Ошибки (не найден трек, no ffmpeg) — вежливое сообщение в канал
        и переход к следующему треку очереди.
        """
        try:
            if getattr(self, '_playing_guilds', None) is None:
                self._playing_guilds = set()
            if getattr(self, '_current_track', None) is None:
                self._current_track = {}
            if int(guild_id) in self._playing_guilds:
                return False
            vc = getattr(ctx, 'voice_client', None)
            if vc is None and getattr(self, 'bot', None) is not None:
                try:
                    g = self.bot.get_guild(int(guild_id))
                    vc = getattr(g, 'voice_client', None)
                except Exception:
                    vc = None
            queue = self.get_queue(guild_id)
            if vc is None or not queue:
                return False
            if vc.is_playing() or vc.is_paused():
                return False
            track = queue[0]
            guild = getattr(vc, 'guild', None)
            if guild is None and getattr(self, 'bot', None) is not None:
                guild = self.bot.get_guild(int(guild_id))
            try:
                url, title = await self._resolve_stream(track.get('query', ''))
            except ImportError as _ie:
                # библиотеки нет вообще — очередь не трогаем, объясняем
                await self._announce(guild, track, 'error', 'Нет yt-dlp',
                                     'На сервере не установлена библиотека '
                                     '**yt-dlp**. Обнови зависимость и '
                                     'перезапусти бота.')
                return False
            except Exception as _ex:
                log.warning('music: %s: %s', track.get('query'), _ex)
                queue.pop(0)
                await self._announce(
                    guild, track, 'error', 'Не удалось найти трек',
                    f'**{_track_name(track)}** — {str(_ex)[:160]}. '
                    'Проверь ссылку или напиши название трека.')
                await self._play_next(guild_id)
                return True
            if self._ffmpeg_binary() is None:
                # ffmpeg нет — пробуем поставить автоматически (бот качает
                # статический билд в ./bin). Ждём в фоне до ~90 сек.
                _ff_path = None
                try:
                    from services.ffmpeg_probe import ensure_ffmpeg, install_status
                    st = install_status()
                    # Сообщаем о загрузке только если реально качаем (а не
                    # повторяем /play после уже неудавшейся установки).
                    if not st.get('done') and not st.get('running'):
                        await self._announce(
                            guild, track, 'info', 'Ставлю ffmpeg',
                            'Для музыки нужен **ffmpeg** — не нашёлся, качаю '
                            'автоматически (один раз, ~20–60 сек). Следующий трек '
                            'уже заиграет без ожидания.')
                    _ff_path = await asyncio.to_thread(ensure_ffmpeg, True)
                except Exception as _ffex:
                    log.debug('music: автоустановка ffmpeg: %s', _ffex)
                    _ff_path = self._ffmpeg_binary()

            if self._ffmpeg_binary() is None and not _ff_path:
                # Не нашли и не смогли поставить — объясняем и останавливаемся.
                _is_win = os.name == 'nt'
                if _is_win:
                    hint = ('Поставь вручную:\n'
                            '• winget: `winget install Gyan.FFmpeg` (потом перезапуск бота);\n'
                            '• или скачай с gyan.dev/ffmpeg и распакуй `ffmpeg.exe` '
                            'рядом с ботом в папку `bin/` или `ffmpeg/bin/`;\n'
                            '• либо укажи путь в `.env`: `FFMPEG_BINARY=путь/к/ffmpeg.exe`.')
                else:
                    hint = ('Установи пакет ffmpeg (`sudo apt install ffmpeg` и т.п.) '
                            'или укажи путь в `.env`: '
                            '`FFMPEG_BINARY=путь/к/ffmpeg`.')
                await self._announce(
                    guild, track, 'error', 'Нет ffmpeg',
                    'Для музыки нужен **ffmpeg** (декодирует аудио). Автоустановка '
                    'не удалась (нет доступа к сети или права на запись).\n' + hint)
                return False

            track['url'] = url
            track['title'] = title
            source = self._new_source(url)
            # громкость из состояния сервера
            try:
                source.volume = self.volume_of(guild_id) / 100
            except Exception as _ex:
                log.debug('music: громкость источника: %s', _ex)
            self._playing_guilds.add(int(guild_id))
            self._current_track[int(guild_id)] = track
            vc.play(source, after=lambda _e: self._after_track(guild_id, _e))
            return True
        except Exception as _ex:
            log.warning('music: play_next: %s', _ex)
            return False

    def _after_track(self, guild_id, error=None):
        """Колбэк после трека (вызывается discord.py в цикле бота)."""
        if error is not None:
            log.warning('music: трек завершился с ошибкой: %s', error)
        try:
            bot = getattr(self, 'bot', None)
            loop = getattr(bot, 'loop', None) or asyncio.get_event_loop()
            loop.create_task(self._on_track_end(guild_id))
        except Exception as _ex:
            log.debug('music: after: %s', _ex)

    async def _on_track_end(self, guild_id: int):
        """Трек закончился: убрать его из очереди и включить следующий."""
        gid = int(guild_id)
        if getattr(self, '_playing_guilds', None) is not None:
            self._playing_guilds.discard(gid)
        queue = self.get_queue(gid)
        current = (getattr(self, '_current_track', None) or {}).get(gid)
        if getattr(self, '_current_track', None) is not None:
            self._current_track.pop(gid, None)
        if queue and current is not None and queue[0] is current:
            queue.pop(0)
        await self._play_next(gid)

    # ── состояние ─────────────────────────────────────────────────────────
    def get_queue(self, guild_id: int) -> list:
        """Получить очередь сервера"""
        if guild_id not in self.queues:
            self.queues[guild_id] = []
        return self.queues[guild_id]

    def is_repeat(self, guild_id: int) -> bool:
        return int(guild_id) in self._repeats

    def toggle_repeat(self, guild_id: int) -> bool:
        gid = int(guild_id)
        if gid in self._repeats:
            self._repeats.discard(gid)
            return False
        self._repeats.add(gid)
        return True

    def set_repeat(self, guild_id: int, on: bool):
        gid = int(guild_id)
        if on:
            self._repeats.add(gid)
        else:
            self._repeats.discard(gid)

    def volume_of(self, guild_id: int) -> int:
        return int(self._volumes.get(int(guild_id), 100))

    def shift_volume(self, guild_id: int, delta: int) -> int:
        gid = int(guild_id)
        vol = max(_VOLUME_MIN, min(_VOLUME_MAX, self.volume_of(gid) + int(delta)))
        self._volumes[gid] = vol
        return vol

    async def _silent(self, ctx, title='Тишина в эфире',
                      text='Сейчас ничего не играет. Включи трек: `/play <название>`'):
        await reply(ctx, 'music', title, text)

    # ── единственная команда ──────────────────────────────────────────────
    @app_commands.command(name='play',
                          description='Включить трек (название или ссылка)')
    @app_commands.describe(трек='Название трека или ссылка на YouTube')
    async def play(self, interaction: discord.Interaction, трек: str = ''):
        """Включить трек: /play <название или ссылка> — пульт появится сам."""
        ctx = InterCtx(interaction)
        трек = (трек or '').strip()
        if not трек:
            # вежливая подсказка вместо ошибки — человек просто не поставил аргумент
            await reply(
                ctx, 'music', 'Что включить?',
                'Напиши: `/play` и название трека или ссылку.\n'
                'Примеры: `/play lofi radio` · `/play https://youtu.be/...`\n'
                'Пульт управления (пауза, скип, громкость, очередь) '
                'появится под сообщением сам.',
                ephemeral=True)
            return
        if not ctx.author.voice:
            await reply(ctx, 'music', 'Ты не в войсе',
                        'Зайди в голосовой канал — и я подключусь к тебе. '
                        'Пульт появится тут же.')
            return

        voice_channel = ctx.author.voice.channel
        if not ctx.voice_client:
            try:
                await voice_channel.connect()
            except Exception as _ex:
                log.warning('music: connect %s: %s', ctx.guild and ctx.guild.id, _ex)
                await reply(ctx, 'music', 'Не смог зайти в войс',
                            'Проверь мои права на голосовой канал '
                            '(подключение и разговор).')
                return

        queue = self.get_queue(ctx.guild.id)
        queue.append({'query': трек, 'requester': ctx.author,
                      'channel_id': getattr(getattr(ctx, 'channel', None), 'id', None),
                      'title': None})

        # Если это первый трек — сразу поднимаем движок (yt-dlp + ffmpeg).
        # Фоном, чтобы ответ с пультом не ждал поиска по сети.
        try:
            if len(queue) == 1:
                asyncio.create_task(self._play_next(ctx.guild.id, ctx=ctx))
            elif not self._playing_guilds:
                asyncio.create_task(self._play_next(ctx.guild.id, ctx=ctx))
        except Exception as _ex:
            log.debug('music: запуск движка: %s', _ex)

        if len(queue) == 1:
            title, pos = 'Сейчас играет', 'сразу'
        else:
            title, pos = 'Добавлено в очередь', f'{len(queue)}-я'

        embed = hakumo_embed(
            'music', title, None,
            fields=[('Трек', f'**{_track_name(queue[-1])}**', False),
                    ('Позиция', pos, True),
                    ('Заказал', ctx.author.mention, True)],
            guild=ctx.guild, footer_extra='Музыка · пульт ниже',
        )
        from cogs.icons import send_with_icon
        await send_with_icon(ctx, embed, 'music', view=MusicControlsView())

    @commands.Cog.listener()
    async def on_ready(self):
        log.info("MusicCog загружен")


async def setup(bot):
    cog = MusicCog(bot)
    await bot.add_cog(cog)
    bot.add_view(MusicControlsView())  # пульт переживает рестарт
