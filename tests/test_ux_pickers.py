# -*- coding: utf-8 -*-
"""UX-пикеры ID и мелкий UX (идеи #91-95).

web/static/pickers.js: хелперы datalist-подсказок, статус-чипов, поиска
по спискам, копирования ID, Ctrl+S. Контракты живых списков
/api/guild/<gid>/channels и /roles (список vs dict с error — по этому
пикер отличает «бот офлайн»). Подключение в шаблонах новых страниц.

Запуск: python3 tests/test_ux_pickers.py
"""
import importlib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime
from types import SimpleNamespace

_TMP = tempfile.mkdtemp(prefix='hakumo_ux_test_')
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


EMOJI_RE = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')

print('== 1. pickers.js: хелперы и чистота ==')
js = open(os.path.join(ROOT, 'web/static/pickers.js'), encoding='utf-8').read()
for fn in ('window.pickerLoad', 'window.pickerExtractId', 'window.attachIdPicker',
           'window.attachListFilter', 'window.bindCopyId', 'window.bindCtrlS'):
    check(fn in js, f'хелпер {fn} на месте')
check("'/api/guild/' + gid + '/channels'" in js
      and "'/api/guild/' + gid + '/roles'" in js, 'живые эндпоинты в хелпере')
check('Array.isArray(d)' in js and 'd.channels' in js,
      'различение списка и dict-ошибки (онлайн-флаг)')
check(('(' + chr(92) + 'd{5,24})') in js and (chr(92) * 2 + 'd{5,24}') not in js,
      'вытаскивание цифр из <#123> (одиночный слэш — живая регулярка)')
check(not EMOJI_RE.search(js), 'в хелпере нет эмодзи')
css = open(os.path.join(ROOT, 'web/static/style.css'), encoding='utf-8').read()
check('.picker-chip.ok' in css and '.picker-chip.bad' in css
      and '[data-copy-id]' in css, 'стили чипов и копирования в style.css')

print('== 2. Контракты живых списков (FakeBot) ==')
import discord  # noqa: E402

appmod = importlib.import_module('web.app')
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()


def _channel(cid, name, ctype, position):
    return SimpleNamespace(id=cid, name=name, type=ctype, position=position,
                           category=None, topic='', nsfw=False,
                           slowmode_delay=0, bitrate=64000, user_limit=0,
                           members=[], created_at=datetime(2026, 1, 1),
                           mention=f'<#{cid}>')


_GUILD = SimpleNamespace(
    id=777, name='Тестхейм',
    channels=[
        _channel(30, 'общий', discord.ChannelType.text, 1),
        _channel(10, 'хаб', discord.ChannelType.category, 0),
        _channel(20, 'голосовой', discord.ChannelType.voice, 0),
    ],
    roles=[
        SimpleNamespace(id=1, name='@everyone', color=0, members=list(range(99))),
        SimpleNamespace(id=2, name='Модеры', color=0, members=list(range(9))),
        SimpleNamespace(id=3, name='Админы', color=0, members=list(range(3))),
    ])


class _FakeBot:
    guilds = [_GUILD]

    def get_guild(self, gid):
        return _GUILD if gid == 777 else None


def login(role='owner'):
    with client.session_transaction() as s:
        s.clear()
        s['logged_in'] = True
        s['username'] = 'admin'
        s['role'] = role


appmod.set_bot_instance(None)
login('mod')
offline = client.get('/api/guild/777/channels').get_json()
check(isinstance(offline, dict) and offline.get('error')
      and offline.get('channels') == [],
      'офлайн-каналы — dict с error и пустым channels (пикер ловит)')
check(client.get('/api/guild/777/roles').get_json() == [],
      'офлайн-роли — пустой список')

appmod.set_bot_instance(_FakeBot())
ch = client.get('/api/guild/777/channels').get_json()
check(isinstance(ch, list) and len(ch) == 3, 'онлайн-каналы — голый список')
check([c['id'] for c in ch] == ['10', '20', '30'],
      'сортировка (category_pos, position): хаб и голос (-1,0) по исходному порядку, общий (-1,1) позже')
check({c['type'] for c in ch} == {'category', 'text', 'voice'},
      'типы в словарных словах пикера')
ro = client.get('/api/guild/777/roles').get_json()
check(isinstance(ro, list) and [r['name'] for r in ro] == ['Модеры', 'Админы'],
      '@everyone пропущен, сортировка по числу участников')

print('== 3. Подключение в шаблонах ==')
j2c = open(os.path.join(ROOT, 'web/templates/j2c.html'), encoding='utf-8').read()
an = open(os.path.join(ROOT, 'web/templates/anime_daily.html'), encoding='utf-8').read()
bd = open(os.path.join(ROOT, 'web/templates/birthdays.html'), encoding='utf-8').read()
so = open(os.path.join(ROOT, 'web/templates/social.html'), encoding='utf-8').read()
for name, tpl in (('j2c', j2c), ('anime', an), ('birthdays', bd), ('social', so)):
    check('/static/pickers.js' in tpl, f'{name}: хелпер подключён')
    check(not EMOJI_RE.search(tpl), f'{name}: эмодзи не появились')
check("kind: 'voice'" in j2c and "kind: 'category'" in j2c,
      'j2c: лобби — голосовой, категория — категория')
check('id="j2LobbyStatus"' in j2c and 'id="j2CategoryStatus"' in j2c,
      'j2c: статус-слоты у полей')
check("kind: 'text'" in an and "kind: 'role'" in an
      and 'id="anChannelStatus"' in an and 'id="anRoleStatus"' in an,
      'anime: канал текстовый, роль — роль, статусы у полей')
check("kind: 'text'" in bd and "kind: 'role'" in bd
      and 'id="bdSetChannelStatus"' in bd and 'id="bdSetRoleStatus"' in bd,
      'birthdays: пикеры канала и роли со статусами')

print('== 4. Поиск по спискам ==')
check('id="j2RoomSearch"' in j2c and "attachListFilter(document.getElementById('j2RoomSearch'), 'j2Rooms', '.j2-row')" in j2c,
      'j2c: поиск по комнатам')
check('id="bdSearch"' in bd and "'bdList', '.bd-row'" in bd,
      'birthdays: поиск по календарю')
check('id="soEventSearch"' in so and 'id="soMatchSearch"' in so
      and "'soEvents', '.so-row'" in so and "'soMatches', '.so-row'" in so,
      'social: поиск по событиям и поискам')

print('== 5. Копирование ID и Ctrl+S ==')
check(j2c.count('data-copy-id') >= 2 and 'bindCopyId(document)' in j2c,
      'j2c: копирование канала и владельца')
check('bindCopyId(document)' in so, 'social: копирование подключено')
check('bindCtrlS(j2Save)' in j2c, 'j2c: Ctrl+S сохраняет')
check('bindCtrlS(function () { anSave(false); })' in an, 'anime: Ctrl+S сохраняет')
check('bindCtrlS(bdSaveSettings)' in bd, 'birthdays: Ctrl+S сохраняет')
check('ctrlKey' in js and 'preventDefault()' in js,
      'Ctrl+S не отправляет страницу')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
