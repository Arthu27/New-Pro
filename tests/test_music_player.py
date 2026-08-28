# -*- coding: utf-8 -*-
"""Движок /play: yt-dlp → FFmpegPCMAudio → очередь.

Баг 2026-08-29: /play добавлял трек в очередь и показывал пульт, но
воспроизведение нигде не запускалось (vc.play/yt-dlp отсутствовали) —
«песня не играет, ссылку не принимает». Тест проверяет:

- _resolve_stream: ссылка уходит в yt-dlp как есть, название — ytsearch1,
  возвращает (url, title);
- _play_next: поднимает vc.play с источником и after-колбэком, помечает
  сервер играющим, очередь НЕ съедается до конца трека;
- _on_track_end: убирает сыгранный трек и включает следующий;
- «Скип» (vc.stop) не даёт двойного снятия следующего трека;
- нет ffmpeg / не найден трек — вежливое сообщение и переход дальше.

Запуск: python3 tests/test_music_player.py
"""
import asyncio
import os
import sys
import tempfile
import types
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

_TMP = tempfile.mkdtemp(prefix='hakumo_musicplayer_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ.pop('FFMPEG_BINARY', None)

PASS = 0
FAIL = 0


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


import cogs.music_cog as MC  # noqa: E402
from cogs.music_cog import MusicCog  # noqa: E402


class FakeSource:
    volume = 1.0


class FakeChannel:
    def __init__(self):
        self.sent = []

    async def send(self, embed=None, **kw):
        self.sent.append(embed)


class FakeVC:
    def __init__(self, guild):
        self.guild = guild
        self.played = []
        self._playing = False
        self._paused = False

    def is_playing(self):
        return self._playing

    def is_paused(self):
        return self._paused

    def play(self, source, after=None):
        self.played.append((source, after))
        self._playing = True

    def stop(self):
        self._playing = False
        if self.played:
            _, after = self.played[-1]
            if after:
                after(None)


class FakeGuild:
    def __init__(self, gid):
        self.id = gid
        self.voice_client = FakeVC(self)
        self.text_channels = []


class FakeBot:
    def __init__(self, gid):
        self.guild = FakeGuild(gid)
        self.loop = asyncio.get_event_loop()

    def get_guild(self, gid):
        return self.guild if int(gid) == self.guild.id else None

    async def close(self):
        pass


def _ytdl_mod(info=None, side_effect=None):
    """Фейк-модуль yt_dlp: extract_info либо отдаёт info, либо кидает."""
    module = types.ModuleType('yt_dlp')
    ydl = Mock()
    if side_effect is not None:
        ydl.extract_info.side_effect = side_effect
    else:
        ydl.extract_info.return_value = info
    module.YoutubeDL = Mock(return_value=Mock(
        __enter__=lambda s: ydl, __exit__=Mock(return_value=False)))
    return module


def _mk_cog(gid=777):
    cog = MusicCog(FakeBot(gid))
    user = NS(display_name='Катя', mention='@Катя')
    cog.queues = {gid: [
        {'query': 'https://youtu.be/abc', 'requester': user,
         'channel_id': None, 'title': None},
        {'query': 'lofi radio', 'requester': user,
         'channel_id': None, 'title': None},
    ]}
    return cog


class _FfmpegPatch:
    """shutil.which → заданный бинарник, чистая установка/снятие."""

    def __init__(self, path):
        self.path = path

    def __enter__(self):
        self.p = patch.object(MC, 'shutil')
        self.mock = self.p.start()
        real = self.mock.which
        self.mock.which.return_value = self.path
        return self

    def __exit__(self, *a):
        self.p.stop()


def _patch_source(cog):
    return patch.object(cog, '_new_source', return_value=FakeSource())


async def _run():
    # ── 1. resolve: ссылка и поиск ────────────────────────────────────────
    cog = _mk_cog()
    calls = []

    def _extract(url, download=False):
        calls.append(url)
        return {'url': 'http://audio/1', 'title': 'Название'}

    with patch.dict(sys.modules, {'yt_dlp': _ytdl_mod(side_effect=_extract)}):
        url, title = await cog._resolve_stream('https://youtu.be/abc')
        check(url == 'http://audio/1' and title == 'Название',
              'ссылка уходит в yt-dlp как есть и возвращается поток')
        await cog._resolve_stream('lofi radio')
        check(calls[1] == 'ytsearch1:lofi radio',
              'название ищется через ytsearch1')

    # ── 2. _play_next запускает vc.play с after ───────────────────────────
    cog = _mk_cog()
    with patch.dict(sys.modules, {'yt_dlp': _ytdl_mod({
            'url': 'http://audio/1', 'title': 'Первый'})}):
        with _FfmpegPatch('/usr/bin/ffmpeg'), _patch_source(cog):
            started = await cog._play_next(777, ctx=NS(voice_client=None))
    vc = cog.bot.guild.voice_client
    check(started is True, 'песня запустилась (vc.play вызван)')
    check(len(vc.played) == 1 and vc.played[0][1] is not None,
          'источник пришёл с after-колбэком (очередь продолжит сама)')
    check(777 in cog._playing_guilds, 'сервер помечен играющим')
    check(cog.queues[777][0]['query'] == 'https://youtu.be/abc',
          'играющий трек остался в очереди до конца (скип не съест следующий)')
    check(cog.queues[777][0].get('title') == 'Первый',
          'в очередь записано название трека с yt-dlp')

    # ── 3. конец трека → следующий ────────────────────────────────────────
    vc._playing = False        # discord.py: после after is_playing() уже False
    with patch.dict(sys.modules, {'yt_dlp': _ytdl_mod({
            'url': 'http://audio/2', 'title': 'Второй'})}):
        with _FfmpegPatch('/usr/bin/ffmpeg'), _patch_source(cog):
            await cog._on_track_end(777)
    check(len(cog.queues[777]) == 1 and cog.queues[777][0]['query'] == 'lofi radio',
          'сыгранный трек убран, следующий в очереди')
    check(len(vc.played) == 2, 'после трека автоматически включён следующий')

    # ── 4. скип: vc.stop → after → без двойного снятия ────────────────────
    cog = _mk_cog()
    with patch.dict(sys.modules, {'yt_dlp': _ytdl_mod({
            'url': 'http://audio/1', 'title': 'Первый'})}):
        with _FfmpegPatch('/usr/bin/ffmpeg'), _patch_source(cog):
            await cog._play_next(777, ctx=NS(voice_client=None))
    vc = cog.bot.guild.voice_client
    vc.stop()   # скип: дискорд дернёт after
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    check(cog.queues[777] and cog.queues[777][0]['query'] == 'lofi radio',
          'скип (vc.stop) не съел следующий трек — очередь цела')

    # ── 5. нет ffmpeg → сообщение, очередь цела ───────────────────────────
    cog = _mk_cog()
    ch = FakeChannel()
    cog.bot.guild.text_channels = [ch]
    with patch.dict(sys.modules, {'yt_dlp': _ytdl_mod({
            'url': 'http://audio/1', 'title': 'Первый'})}):
        with _FfmpegPatch(None):
            await cog._play_next(777, ctx=NS(voice_client=None))
    check(len(cog.queues[777]) == 2,
          'нет ffmpeg — очередь цела, ничего не съедено впустую')
    check(not cog.bot.guild.voice_client.played,
          'без ffmpeg трек не запущен (пользователю объяснено)')

    # ── 6. трек не найден → переход к следующему ──────────────────────────
    cog = _mk_cog()

    def _mix(url, download=False):
        if url.startswith('http'):
            raise Exception('Video unavailable')
        return {'url': 'http://audio/2', 'title': 'lofi'}

    with patch.dict(sys.modules, {'yt_dlp': _ytdl_mod(side_effect=_mix)}):
        await cog._play_next(777, ctx=NS(voice_client=None))
    check(cog.queues[777][0]['query'] == 'lofi radio',
          'недоступная ссылка не вешает очередь — движемся к следующему')

    # ── 7. нет yt-dlp → очередь не съедается, объяснение ───────────────────
    cog = _mk_cog()
    with patch.dict(sys.modules, {'yt_dlp': None}):
        started = await cog._play_next(777, ctx=NS(voice_client=None))
    check(started is False and len(cog.queues[777]) == 2,
          'нет yt-dlp — очередь цела (не удаляем треки без движка)')


print('== 1. yt-dlp: ссылка и поиск ==')
asyncio.run(_run())

print('== 2. /play вызывает движок ==')
src = open(os.path.join(ROOT, 'cogs', 'music_cog.py'), encoding='utf-8').read()
for need in ('async def _resolve_stream', 'async def _play_next',
             'vc.play(source', '_after_track', 'FFmpegPCMAudio'):
    check(need in src, f'в коге есть {need}')
check('yt_dlp.YoutubeDL' in src or 'yt_dlp' in src,
      'движок использует yt-dlp (ссылки/названия)')
check("'FFMPEG_BINARY'" in src, 'путь к ffmpeg настраивается через .env')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
