# -*- coding: utf-8 -*-
"""Пикеры каналов логов не пустеют никогда: живой бот → кэш → настройки.

Запуск: python3 tests/test_log_channel_pickers.py
"""
import os
import sys
import tempfile
import types

# демо-режим НЕ включаем: проверяем честный каскад бот→кэш→настройки
_TMP = tempfile.mkdtemp(prefix='hakumo_pick_')
os.chdir(_TMP)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS = 0
FAIL = 0


def check(cond, label, extra=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f'  PASS: {label}')
    else:
        FAIL += 1
        print(f'  FAIL: {label} {extra}')


from web.routes import staff_limits_panel as SLP
import discord as _dc


class FakeCh:
    def __init__(self, id, name, position=0):
        self.id = id
        self.name = name
        self.position = position
        # форум-тип проходит фильтр пикера (текстовые требуют isinstance)
        self.type = _dc.ChannelType.forum


class FakeTh:
    def __init__(self, id, name, parent_id=None, parent_name=''):
        self.id = id
        self.name = name
        self.parent_id = parent_id
        self.parent = types.SimpleNamespace(name=parent_name, id=parent_id) if parent_id else None


class FakeGuild:
    def __init__(self, channels, threads=None):
        self.channels = channels
        self.threads = threads or []
        self.id = 555


class FakeBot:
    def __init__(self, guild):
        self.guilds = [guild]
        self._g = guild

    def get_guild(self, gid):
        return self._g if int(gid) == self._g.id else None


GID = 555
bot = FakeBot(FakeGuild([FakeCh(1, 'общий'), FakeCh(2, 'журнал-модерации')]))

print('== живой бот: список + кэш ==')
chans, src = SLP._guild_channels(bot, GID)
check(src == 'bot' and len(chans) == 2 and chans[0]['name'] == 'общий · форум',
      'от живого бота: каналы с # и источник bot', f'→ {src} {chans}')
cache_file = f'data/panel_channels_cache_{GID}.json'
check(os.path.exists(cache_file), 'кэш записан на диск')

print('== бот офлайн: список из кэша ==')
chans2, src2 = SLP._guild_channels(None, GID)
check(src2 == 'cache' and len(chans2) == 2 and chans2[1]['name'] == 'журнал-модерации · форум',
      'без бота пикеры не пустые — каналы из кэша', f'→ {src2} {chans2}')

print('== нет бота и нет кэша: ранее настроенные каналы ==')
os.remove(cache_file)
from services import log_settings as LS
LS.set_log_settings(GID, enabled={'mod': True}, channels={'mod': '777', 'member': '888'})
chans3, src3 = SLP._guild_channels(None, GID)
ids = [c['id'] for c in chans3]
check(src3 == 'settings' and '777' in ids and '888' in ids and len(ids) == 2,
      'фолбэк: выбранные раньше каналы остаются в селектах', f'→ {src3} {chans3}')

print('== гильдия не найдена, но бот жив: кэш спасает ==')
if os.path.exists(f'data/panel_channels_cache_{GID}.json'):
    os.remove(f'data/panel_channels_cache_{GID}.json')
SLP._channels_cache_save(GID, [{'id': '5', 'name': '#спасённый'}])
chans4, src4 = SLP._guild_channels(FakeBot(FakeGuild([])), GID)
check(src4 == 'cache' and chans4 and chans4[0]['name'] == '#спасённый',
      'чужой guild_id не очищает пикеры', f'→ {src4} {chans4}')

print('== живой бот: ветки тоже в пикере ==')
g_th = FakeGuild(
    [FakeCh(1, 'общий'), FakeCh(2, 'журнал-модерации')],
    threads=[FakeTh(9, 'ивент', parent_id=1, parent_name='общий')])
g_th.id = 556
bot_th = FakeBot(g_th)
chans_t, src_t = SLP._guild_channels(bot_th, 556)
names_t = [c['name'] for c in chans_t]
check(src_t == 'bot' and any('ветка ивент' in n for n in names_t)
      and any(c.get('type') == 'thread' for c in chans_t),
      'ветки гильдии попадают в пикер логов', f'→ {names_t}')

print('== страница: офлайн-пометка + селекты на месте ==')
tpl = open(os.path.join(sys.path[0], 'web', 'templates', 'log_settings.html'),
           encoding='utf-8').read()
check('lsOfflineNote' in tpl and 'channels_source' in tpl,
      'страница честно говорит, когда бот офлайн')
check('lsApplyCh' in tpl and 'lsCh' in tpl,
      'селекты: на каждую категорию + один канал во все сразу')
check('lsBg' in tpl and 'preview.png?cat=' in tpl,
      'на каждую категорию — URL фона и живой preview.png с текстами лога')

src = open(os.path.join(sys.path[0], 'web', 'routes', 'staff_limits_panel.py'),
           encoding='utf-8').read()
check("'channels_source': src" in src, 'API отдаёт источник каналов')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
