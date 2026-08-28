# -*- coding: utf-8 -*-
"""Музыкальное меню (заказ, пункт 4).

- Единственная команда модуля — /play; старые /pause, /resume, /skip,
  /queue, /nowplaying, /leave и /musicpanel удалены.
- /play без аргумента — вежливая эфемерная подсказка (не ошибка).
- Ответ /play несёт пульт MusicControlsView (пауза/играть, скип, стоп,
  громкость ±10%, повтор, перемешать, очередь).
- Каждая кнопка пульта делает именно своё действие (проверяем на фейках),
  чужак не из войса бота получает вежливый отказ, а не тишину.
- Пульт persistent: все custom_id фиксированы, view регистрируется в setup.

Запуск: python3 tests/test_music_controls.py
"""
import asyncio
import os
import sys
import tempfile
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

_TMP = tempfile.mkdtemp(prefix='hakumo_music_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['PANEL_USER'] = 'admin'
os.environ['PANEL_PASSWORD'] = 'test123'
os.environ['MAIN_GUILD_ID'] = '777'

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


import discord  # noqa: E402

import cogs.music_cog as MC  # noqa: E402
from cogs.music_cog import MusicCog, MusicControlsView  # noqa: E402
from cogs import embed_utils as EU  # noqa: E402
import cogs.icons as _icons  # noqa: E402
# в тестах нет assets-иконок — отключаем фирменную миниатюру,
# чтобы ответ /play шёл через чистый send_message
_icons.ICONS_DIR = os.path.join(_TMP, 'no_such_icons_dir')


class _FakeVC:
    def __init__(self):
        self.calls = []
        self._playing = True
        self._paused = False
        self.channel = NS(id=900, name='Войс')
        self.source = NS(volume=1.0)

    def is_playing(self):
        return self._playing and not self._paused

    def is_paused(self):
        return self._paused

    def pause(self):
        self.calls.append('pause')
        self._paused = True

    def resume(self):
        self.calls.append('resume')
        self._paused = False

    def stop(self):
        self.calls.append('stop')

    async def disconnect(self):
        self.calls.append('disconnect')


def _cog():
    return MusicCog.__new__(MusicCog)


def _mk_state(with_track=True, paused=False):
    """(cog, guild, vc, user) — человек сидит в одном войсе с ботом."""
    cog = _cog()
    vc = _FakeVC()
    vc._paused = paused
    user = NS(id=42, voice=NS(channel=NS(id=900)), display_name='Катя',
              mention='@Катя')
    cog.queues = {}
    cog._repeats = set()
    cog._volumes = {}
    if with_track:
        cog.queues[777] = [{'query': 'lofi radio', 'requester': user},
                           {'query': 'phonk', 'requester': user},
                           {'query': 'jazz', 'requester': user}]
    else:
        cog.queues[777] = []
    guild = NS(id=777, voice_client=vc, name='Тест', icon=None)
    return cog, guild, vc, user


class _Resp:
    def __init__(self):
        self.sent = []
    def is_done(self):
        return False

    async def send_message(self, content=None, embed=None, ephemeral=False, view=None):
        self.sent.append((str(content or ''), embed, ephemeral, view))


def _inter(cog, guild, user):
    return NS(guild=guild, user=user, response=_Resp(), client=NS(get_cog=lambda n: cog))


async def _press(which, cog, guild, user):
    v = MusicControlsView()
    # discord.py 2.x:красс-колбэки кнопок — async def(inter, button), вызываем напрямую
    cb = {'toggle': v.btn_toggle, 'skip': v.btn_skip,
          'stop': v.btn_stop, 'voldown': v.btn_voldown,
          'volup': v.btn_volup, 'repeat': v.btn_repeat,
          'shuffle': v.btn_shuffle, 'queue': v.btn_queue}[which]
    inter = _inter(cog, guild, user)
    await cb.callback(inter)  # discord.py 2.x: item.callback(interaction)
    return inter.response.sent


async def _run():
    # ── пауза / продолжить ───────────────────────────────────────────────
    cog, guild, vc, user = _mk_state()
    sent = await _press('toggle', cog, guild, user)
    check('pause' in vc.calls, 'кнопка «Пауза/Играть» ставит паузу (vc.pause)')
    check(sent and sent[0][1] is not None and sent[0][2] is True, 'отлик паузы — эфемерный фирменный эмбед')
    sent = await _press('toggle', cog, guild, user)
    check(vc.calls[-1] == 'resume', 'повторное нажатие — продолжить (vc.resume)')

    cog, guild, vc, user = _mk_state()
    vc._playing = False  # ничего не играет
    sent = await _press('toggle', cog, guild, user)
    check(sent and 'Тишина' in str(EU.hakumo_embed.__name__ or '') or
          (sent and sent[0][1] is not None and 'Тишина' in str(sent[0][1].title)),
          'нет активного трека — вежливое «Тишина в эфире», не тишина')

    # ── скип ─────────────────────────────────────────────────────────────
    cog, guild, vc, user = _mk_state()
    before = [t['query'] for t in cog.queues[777]]
    sent = await _press('skip', cog, guild, user)
    after = [t['query'] for t in cog.queues[777]]
    check(after == before[1:], 'скип убирает играющий трек из очереди')
    check('stop' in vc.calls, 'скип дергает vc.stop() — движок возьмёт следующий')
    check(sent and 'Дальше' in str(sent[0][1].description), 'скип называет следующий трек')
    sent = await _press('skip', cog, guild, user)
    sent = await _press('skip', cog, guild, user)  # очередь кончилась
    check(sent and 'последний' in str(sent[0][1].description).lower() or
          'пуста' in str(sent[0][1].description) or 'пуста' in str(sent[0][1].title).lower(),
          'скип последнего трека — честное «очередь пуста»')

    # повтор: скип возвращает трек в конец
    cog, guild, vc, user = _mk_state()
    cog.set_repeat(777, True)
    before = [t['query'] for t in cog.queues[777]]
    await _press('skip', cog, guild, user)
    after = [t['query'] for t in cog.queues[777]]
    check(after == [before[1], before[2], before[0]],
          'повтор вкл: скипнутый трек встаёт в конец очереди')

    # ── стоп ─────────────────────────────────────────────────────────────
    cog, guild, vc, user = _mk_state()
    cog.set_repeat(777, True)
    sent = await _press('stop', cog, guild, user)
    check(cog.queues[777] == [], 'стоп очищает очередь')
    check('disconnect' in vc.calls, 'стоп отключает бота от войса')
    check(not cog.is_repeat(777), 'стоп сбрасывает и повтор')
    check(sent and 'Остановлено' in str(sent[0][1].title), 'стоп отвечает «Остановлено»')

    # ── громкость ────────────────────────────────────────────────────────
    cog, guild, vc, user = _mk_state()
    await _press('volup', cog, guild, user)
    check(cog.volume_of(777) == 110 and vc.source.volume == 1.1,
          'громкость +10%: состояние и живой источник')
    for _ in range(30):
        await _press('volup', cog, guild, user)
    check(cog.volume_of(777) == 200, 'громкость не уходит выше 200%')
    for _ in range(30):
        await _press('voldown', cog, guild, user)
    check(cog.volume_of(777) == 0 and vc.source.volume == 0.0,
          'громкость не уходит ниже 0%')

    # ── повтор и перемешивание ───────────────────────────────────────────
    cog, guild, vc, user = _mk_state()
    sent = await _press('repeat', cog, guild, user)
    check(cog.is_repeat(777) and 'Включён' in str(sent[0][1].description), 'повтор включается')
    sent = await _press('repeat', cog, guild, user)
    check(not cog.is_repeat(777) and 'Выключен' in str(sent[0][1].description), 'повтор выключается')

    cog, guild, vc, user = _mk_state()
    before = [t['query'] for t in cog.queues[777]]
    sent = await _press('shuffle', cog, guild, user)
    after = [t['query'] for t in cog.queues[777]]
    check(sorted(after) == sorted(before) and after[0] == before[0],
          'перемешивание: состав тот же, играющий трек не тронут')
    cog, guild, vc, user = _mk_state()
    cog.queues[777] = [{'query': 'only one', 'requester': user}]
    sent = await _press('shuffle', cog, guild, user)
    check(sent and 'минимум 2' in str(sent[0][1].description), 'один трек — вежливый отказ перемешивания')

    # ── очередь ──────────────────────────────────────────────────────────
    cog, guild, vc, user = _mk_state()
    sent = await _press('queue', cog, guild, user)
    check(sent and sent[0][1] is not None and 'Очередь' in str(sent[0][1].title)
          and sent[0][2] is True, 'очередь — эфемерный список')
    check('▶' in str(sent[0][1].description), 'в очереди помечен играющий трек')
    cog, guild, vc, user = _mk_state(with_track=False)
    sent = await _press('queue', cog, guild, user)
    check(sent and 'пуста' in str(sent[0][1].title).lower(), 'пустая очередь — честный ответ')

    # ── чужак не в войсе бота ────────────────────────────────────────────
    cog, guild, vc, user = _mk_state()
    stranger = NS(id=99, voice=None, display_name='Чужой')
    sent = await _press('skip', cog, guild, stranger)
    check(sent and 'голосового канала' in str(sent[0][0]),
          'транспорт недоступен тем, кто не в войсе бота (вежливый отказ)')
    check('stop' not in vc.calls, 'чужак ничего не скипнул')

    # ── /play без аргумента ──────────────────────────────────────────────
    cog = _cog()
    inter = NS(guild=NS(id=777, name='Тест', icon=None), user=user, response=_Resp(),
               voice_client=None, channel=NS())
    await MusicCog.play.callback(cog, inter, трек='')
    s = inter.response.sent
    check(s and s[0][2] is True and 'Что включить' in str(s[0][1].title),
          '/play без аргумента — вежливая эфемерная подсказка, не ошибка')
    check('/play' in str(s[0][1].description) and 'youtu' in str(s[0][1].description),
          'подсказка показывает формат названия и ссылки')

    # ── /play вне войса ──────────────────────────────────────────────────
    inter = NS(guild=NS(id=777, name='Тест', icon=None), user=NS(id=42, voice=None),
               response=_Resp(), voice_client=None, channel=NS())
    await MusicCog.play.callback(cog, inter, трек='lofi radio')
    s = inter.response.sent
    check(s and 'не в войсе' in str(s[0][1].title).lower(),
          '/play вне войса — подсказка зайти в канал')

    # ── /play с треком: ответ несёт пульт ────────────────────────────────
    cog = _cog()
    cog.queues = {}
    vcchan = NS(id=900, name='Войс')

    async def _connect():
        return None
    vcchan.connect = _connect
    authored = NS(id=42, voice=NS(channel=vcchan), display_name='Катя', mention='@Катя')
    inter = NS(guild=NS(id=777, name='Тест', icon=None), user=authored, response=_Resp(),
               voice_client=None, channel=NS())
    await MusicCog.play.callback(cog, inter, трек='lofi radio')
    s = inter.response.sent
    check(s and isinstance(s[0][3], MusicControlsView),
          'ответ /play несёт автоматический пульт кнопок')
    check(cog.queues[777] and cog.queues[777][0]['query'] == 'lofi radio',
          'трек встал в очередь')


print('== 1. Реестр команд: осталась одна /play ==')
cmds = [v for v in vars(MusicCog).values()
        if isinstance(v, discord.app_commands.Command)]
names = sorted(c.name for c in cmds)
check(names == ['play'], f'у MusicCog единственная слеш-команда: {names}')
p = list(cmds[0].parameters)
check(len(p) == 1 and not p[0].required and p[0].default == '',
      '/play имеет единственный необязательный аргумент')
src = open(os.path.join(ROOT, 'cogs/music_cog.py'), encoding='utf-8').read()
for gone in ("name='pause'", "name='resume'", "name='skip'", "name='queue'",
             "name='nowplaying'", "name='leave'", 'musicpanel'):
    check(gone not in src, f'упоминаний {gone} нет — команда удалена целиком')

print('== 2. Кнопки пульта (поведение) ==')
asyncio.run(_run())

print('== 3. Состав и стойкость пульта ==')
view = MusicControlsView()
ids = sorted(ch.custom_id for ch in view.children)
expect = sorted(['music:toggle', 'music:skip', 'music:stop', 'music:voldown',
                 'music:volup', 'music:repeat', 'music:shuffle', 'music:queue'])
check(ids == expect, f'все 8 кнопок на месте: {ids}')
check(view.timeout is None, 'пульт persistent (без таймаута)')
check(all(ch.custom_id for ch in view.children),
      'у каждой кнопки фиксированный custom_id — переживают рестарт')
check('bot.add_view(MusicControlsView())' in src,
      'пульт регистрируется в setup — работает после рестарта')
core = open(os.path.join(ROOT, 'web/routes/music_panel.py'), encoding='utf-8').read()
check('def perform_music_action' in core and 'def music_payload' in core, 'веб-пульт музыки на месте (санити)')
print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
