# -*- coding: utf-8 -*-
"""Таблицы и сохранения — упрощённая схема апелляций (2026-09-08).

1) «Таблица опять не отправляется»: точки отправки логов и staff-stats.
2) «Канал не включается после заявки»: теперь канал НЕ открывается — простая схема:
   заявка просто в канал апелляций, без overwrites/тредов. Проверяем skipped.
3) Права команд и комнаты — сохранение.

Запуск: python3 tests/test_tables_and_saves.py
"""
import asyncio
import json
import os
import sys
import tempfile
import threading
import time
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(tempfile.mkdtemp(prefix='tbl_saves_'))
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.abspath(os.path.join('data', 'bot.db'))
sys.path.insert(0, ROOT)

PASS = FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


import discord  # noqa: E402

# ═══════════════════════════════════════════════════════════════════
print('== 1. Графическая таблица логов: постоянные кнопки и отправка ==')
from cogs.log_menu import LogBrowserView, LogMenu, post_log_table  # noqa: E402


class _FakeChannel:
    def __init__(self, cid=555):
        self.id = cid
        self.name = 'логи'
        self.sent = []

    async def send(self, **kw):
        self.sent.append(kw)

        class _Msg:
            id = 4242
            jump_url = 'https://discord.com/channels/777/555/4242'

        return _Msg()


class _FakeGuild:
    id = 777
    name = 'Тестовый сервер'
    channels = []
    members = []


class _FakeBot:
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.guilds = []
        self.added_views = []

    def add_view(self, view, *, message_id=None):
        self.added_views.append(view)


_guild = _FakeGuild()
_view = LogBrowserView(_guild, user_id=0)
check(_view.timeout is None,
      'LogBrowserView без таймаута (кнопки живут после рестарта)',
      f'→ timeout={_view.timeout}')
custom_ids = {getattr(it, 'custom_id', None) for it in _view.children}
check({'log_menu:select', 'log_menu:prev', 'log_menu:next', 'log_menu:search',
       'log_menu:reset', 'log_menu:refresh'} <= custom_ids,
      'у всех элементов стабильные persistent custom_id', f'→ {custom_ids}')

_bot = _FakeBot()
_ch = _FakeChannel()
msg, err = _bot.loop.run_until_complete(post_log_table(_bot, _guild, _ch))
check(err is None and msg is not None, 'post_log_table отправляет сообщение', f'→ {err}')
check(bool(_ch.sent) and 'view' in _ch.sent[0] and 'file' in _ch.sent[0],
      'в сообщении и картинка-таблица, и интерактивные кнопки')

_bot.added_views = []
_bot.guilds = [_guild]
_bot.loop.run_until_complete(LogMenu(_bot).on_ready())
check(len(_bot.added_views) == 1 and isinstance(_bot.added_views[0], LogBrowserView),
      'on_ready оживляет таблицу после рестарта (bot.add_view)')

# ═══════════════════════════════════════════════════════════════════
print('== 2. Таблица активности персонала: сборка и отправка ==')
from cogs.staff_stats import build_staff_stats_embed, post_staff_stats  # noqa: E402

_mod = types.SimpleNamespace(
    id=1001, name='Модератор One', display_name='Модератор One',
    mention='<@1001>', display_avatar=None)


class _G:
    id = 777
    name = 'Тестовый сервер'

    def get_member(self, uid):
        return None


e = build_staff_stats_embed(_G(), 30, модератор=None, actions=[])
check('Staff Stats' in (e.description or ''),
      'пустые данные → честная таблица «действий не найдено»')
e2 = build_staff_stats_embed(_G(), 30, модератор=None,
                             actions=[('1001', 'ban', time.time())])
check('1001' in (e2.description or '') or 'Топ' in (e2.description or ''),
      'есть действия → таблица топа модераторов строится')
e3 = build_staff_stats_embed(_G(), 30, модератор=_mod, actions=[])
check('Активность' in (e3.author.name or ''),
      'карточка конкретного модератора собирается тем же кодом')

_ch2 = _FakeChannel()
msg2, err2 = _bot.loop.run_until_complete(post_staff_stats(_bot, _G(), _ch2, 30))
check(err2 is None and msg2 is not None, 'post_staff_stats отправляет embed', f'→ {err2}')
check(bool(_ch2.sent) and 'embed' in _ch2.sent[0], 'в канал уходит embed-таблица')

# ═══════════════════════════════════════════════════════════════════
print('== 3. Канал апелляции: упрощённая схема — просто заявка в канал ==')
from cogs.appeals import Appeals  # noqa: E402
from services import channel_routes as CR  # noqa: E402

CR.ROUTES_FILE = os.path.abspath('data/channel_routes.json')
APPEAL_CH_ID = 1544483947705008188


class _PermChannel:
    def __init__(self, cid=APPEAL_CH_ID):
        self.id = cid
        self.name = 'апелляции'
        self.overwrites = {}
        self.targets = {}

    async def set_permissions(self, target, overwrite=None):
        self.overwrites[target.id] = overwrite
        self.targets[target.id] = target


class _G2:
    id = 1484574976580391004
    name = 'Сервер'

    def __init__(self, channels):
        self.channels = channels
        self._by_id = {c.id: c for c in channels}

    def get_channel(self, cid):
        return self._by_id.get(cid)


class _User:
    id = 2002


class _G3(_G2):
    def get_channel(self, cid):
        return None

    async def fetch_channel(self, cid):
        return self._by_id.get(cid)


_cog = Appeals.__new__(Appeals)
# для _appeal_channel нужен db — в тесте без __init__ подменяем
try:
    from db import GuildData as _GD
    _cog.db = _GD('appeals')
except Exception:
    _cog.db = None
    _cog._load = lambda gid: {'log_channel_id': 0, 'items': [], 'next_id': 1}
_pc = _PermChannel()

# 3а. маршрут настроен → skipped, без overwrites
CR.set_route(_G2.id, 'ban_appeal_channel', APPEAL_CH_ID)
_g2 = _G2([_pc])
opened, ch_ref = asyncio.new_event_loop().run_until_complete(
    _cog._open_appeal_channel(_g2, _User()))
check(opened == 'skipped' and ch_ref is _pc, 'маршрут настроен → канал НЕ открываем (skipped)')
check(_pc.overwrites == {}, 'простая схема: никаких overwrites')

# 3б. кэш пуст → в простой схеме канал не открывается, но и не падает (skipped)
_pc2 = _PermChannel()
_g3 = _G3([_pc2])
opened3, ch3 = asyncio.new_event_loop().run_until_complete(
    _cog._open_appeal_channel(_g3, _User()))
check(opened3 == 'skipped' and _pc2.overwrites == {}, 'канала нет в кэше → skipped, без overwrites (простая схема)')

# 3в. пустой маршрут → skipped
CR.set_route(_G2.id, 'ban_appeal_channel', 0)
_pc3 = _PermChannel(cid=999)
_g4 = _G2([_pc3])
opened4, ch4 = asyncio.new_event_loop().run_until_complete(
    _cog._open_appeal_channel(_g4, _User(), fallback_channel=_pc3))
check(opened4 == 'skipped' and _pc3.overwrites == {}, 'пустой маршрут → skipped, без overwrites')

# 3г. ни маршрута, ни fallback → skipped
opened5, ch5 = asyncio.new_event_loop().run_until_complete(
    _cog._open_appeal_channel(_g4, _User()))
check(opened5 == 'skipped', 'открывать нечего → skipped')

# 3д. dm_channel_line
line = _cog._dm_channel_line('opened', _pc)
check('апелляции' in line.lower(), 'в ЛС видно имя канала', f'→ {line[:60]}')
line_skipped = _cog._dm_channel_line('skipped', _pc)
check('апелляции' in line_skipped.lower() or 'канал' in line_skipped.lower(),
      'skipped-линия показывает канал')
line_bad = _cog._dm_channel_line('failed', None)
check(isinstance(line_bad, str) and len(line_bad) > 0, 'dm_channel_line возвращает строку при failed')

# 3е. известная комната → skipped
CR.set_route(_G2.id, 'ban_appeal_channel', 0)
_pc_known = _PermChannel(cid=APPEAL_CH_ID)
_g_known = _G2([_pc_known])
opened_k, ch_k = asyncio.new_event_loop().run_until_complete(
    _cog._open_appeal_channel(_g_known, _User(), fallback_channel=_pc3))
check(opened_k == 'skipped' and _pc_known.overwrites == {}, 'известная комната, но не открываем')
check(_pc3.overwrites == {}, 'канал карточек не трогаем')

# 3ж. fetch известного ID → skipped (в простой схеме без открытия, fetch не обязателен)
_pc_fk = _PermChannel(cid=APPEAL_CH_ID)
_g_fk = _G3([_pc_fk])
opened_fk, ch_fk = asyncio.new_event_loop().run_until_complete(
    _cog._open_appeal_channel(_g_fk, _User()))
check(opened_fk == 'skipped' and _pc_fk.overwrites == {}, 'fetch ID → skipped, без overwrites')

# 3з. Member не трогаем
class _Mem:
    id = 2002

class _GMem(_G2):
    def get_member(self, uid):
        return _Mem() if int(uid) == 2002 else None

_pc_m = _PermChannel()
_g_m = _GMem([_pc_m])
CR.set_route(_G2.id, 'ban_appeal_channel', APPEAL_CH_ID)
opened_m, ch_m = asyncio.new_event_loop().run_until_complete(
    _cog._open_appeal_channel(_g_m, _User()))
check(opened_m == 'skipped' and _pc_m.overwrites == {}, 'Member не трогаем')

# 3и. ветка: add_user не вызывается
class _ThreadCh(_PermChannel):
    def __init__(self, cid=APPEAL_CH_ID):
        super().__init__(cid)
        self.added = []

    async def add_user(self, user):
        self.added.append(user)

_th = _ThreadCh()
_g_th = _GMem([_th])
opened_th, ch_th = asyncio.new_event_loop().run_until_complete(
    _cog._open_appeal_channel(_g_th, _User()))
check(opened_th == 'skipped' and not _th.added, 'ветка: без add_user')
_th2 = _ThreadCh()
_g_th2 = _G2([_th2])
opened_th2, ch_th2 = asyncio.new_event_loop().run_until_complete(
    _cog._open_appeal_channel(_g_th2, _User()))
check(opened_th2 == 'skipped' and not _th2.added and _th2.overwrites == {}, 'жёсткий бан: без add_user и overwrite')

# 3к. оценка
RATING_ID = 1518751543329951904
check(CR.APPEAL_RATING_CHANNEL_ID == RATING_ID, 'ID канала оценки совпадает')

class _RateCh:
    def __init__(self):
        self.id = RATING_ID
        self.name = 'оценки'

_rc = _RateCh()
_g_rate = _G2([_rc])
ch_rate = asyncio.new_event_loop().run_until_complete(_cog._rating_channel(_g_rate))
check(ch_rate is _rc, 'оценка: канал из кэша')
_rc_f = _RateCh()
_g_rate_f = _G3([_rc_f])
ch_rate_f = asyncio.new_event_loop().run_until_complete(_cog._rating_channel(_g_rate_f))
check(ch_rate_f is _rc_f, 'оценка: fetch')
asrc = open(os.path.join(ROOT, 'cogs', 'appeals.py'), encoding='utf-8').read()
check('_rating_channel' in asrc and 'APPEAL_RATING_CHANNEL_ID' in asrc, 'модалка оценки пишет в _rating_channel')
check('ban_appeal_channel' in asrc and 'appeals_channel' in asrc, 'карточка — маршрут ban_appeal_channel / appeals_channel')

# ═══════════════════════════════════════════════════════════════════
print('== 4. Заявка в персонал не теряется тихо ==')
src = open(os.path.join(ROOT, 'cogs', 'staff_apply.py'), encoding='utf-8').read()
check('delivery' in src and 'no_channel' in src, 'ненастроенный канал фиксируется (delivery=no_channel)')
check('не доставлено' in src.lower() or 'не доставлен' in src.lower(), 'заявитель получает честное сообщение')
check('log.warning' in src, 'случай «канал заявок не настроен» в лог')

# ═══════════════════════════════════════════════════════════════════
print('== 5. Права команд: данные сохраняются ==')
os.environ['DEMO_MODE'] = '1'
os.environ['PANEL_USER'] = 'owner'
os.environ['PANEL_PASSWORD'] = 'x'
os.environ['MAIN_GUILD_ID'] = '777'
os.environ['PANEL_PORT'] = '5099'

import web.app as webapp  # noqa: E402
_client = webapp.app.test_client()
_client.post('/login', data={'username': os.environ.get('PANEL_USER', 'owner'), 'password': os.environ['PANEL_PASSWORD']})
_demo_guild_id = '777'

r_page = _client.get('/role-permissions')
check(r_page.status_code == 200, 'страница «Права команд» открывается', f'→ {r_page.status_code}')

r_set = _client.post(f'/api/role-permissions/{_demo_guild_id}/set', json={'command': 'report', 'role_ids': ['9001', '9003']})
check(r_set.status_code == 200 and r_set.get_json().get('success'), 'POST /set принимает правило', f'→ {r_set.status_code}')
r_get = _client.get(f'/api/role-permissions/{_demo_guild_id}')
acl = r_get.get_json().get('acl') or {}
check(acl.get('report') == ['9001', '9003'], 'GET после POST показывает правило', f'→ {acl.get("report")}')

from services.permission_acl import load_acl, load_action_acl  # noqa: E402
disk_acl = load_acl(777)
check(disk_acl.get('report') == ['9001', '9003'], 'правило в БД — переживает рестарт', f'→ {disk_acl}')

r_act = _client.post(f'/api/role-permissions/{_demo_guild_id}/action/set', json={'action': 'ban', 'role_ids': ['9002']})
check(r_act.status_code == 200 and r_act.get_json().get('success'), 'POST action/set принимает правило')
disk_actions = load_action_acl(777)
check(disk_actions.get('ban') == ['9002'], 'правило действия в БД', f'→ {disk_actions}')

r_cat = _client.post(f'/api/role-permissions/{_demo_guild_id}/category/assign', json={'category': 'Модерация', 'role_ids': ['9003']})
check(r_cat.status_code == 200 and r_cat.get_json().get('success'), 'POST category/assign назначает категорию')
disk_acl = load_acl(777)
check(any(str(v) == "['9003']" for v in disk_acl.values()), 'правила категории материализованы', f'→ {list(disk_acl.items())[:3]}')

print('== 6. «Комнаты» (Меню панели): сохранение страниц и групп ==')
r_pm = _client.post('/api/panel-menu', json={'role': 'mod', 'groups': ['Модерация', 'Логи'], 'items': ['/logs', '/staff-apps']})
check(r_pm.status_code == 200 and r_pm.get_json().get('success'), 'POST /api/panel-menu сохраняет комнаты')
from services.panel_menu import get_config  # noqa: E402
cfg = get_config()
check(cfg.get('mod', {}).get('items') == ['/logs', '/staff-apps'] and set(cfg.get('mod', {}).get('groups') or []) == {'Модерация', 'Логи'}, 'комнаты прочитаны из файла', f'→ {cfg}')
r_pm_bad = _client.post('/api/panel-menu', json={'role': 'vladelec', 'groups': [], 'items': []})
check(r_pm_bad.status_code == 400, 'чужая роль не проходит')

print('== 7. Точки отправки таблиц из панели существуют ==')
r1 = _client.post('/api/logs/table/send', json={'channel_id': '555'})
check(r1.status_code in (400, 502, 503), 'лог-таблица: без бота — честный отказ', f'→ {r1.status_code}')
r2 = _client.post('/api/staff-stats/send', json={'channel_id': '555', 'days': 30})
check(r2.status_code in (400, 502, 503), 'staff-таблица: без бота — честный отказ', f'→ {r2.status_code}')

print('== 8. Счастливый путь: панель + живой бот → таблица в канале ==')
_loop8 = asyncio.new_event_loop()
_thread8 = threading.Thread(target=_loop8.run_forever, daemon=True)
_thread8.start()
_bot.loop = _loop8
webapp.bot_instance = _bot
_gsend_ch = _FakeChannel()

class _FakeGuildSend:
    id = 777
    name = 'Тестовый сервер'
    system_channel = None
    def __init__(self, channels):
        self.channels = channels
        self._by_id = {c.id: c for c in channels}
    def get_channel(self, cid):
        return self._by_id.get(cid)

_bot.get_guild = lambda gid: _FakeGuildSend([_gsend_ch]) if gid == 777 else None

r3 = _client.post('/api/logs/table/send', json={'channel_id': str(_gsend_ch.id)})
_d3 = r3.get_json() or {}
check(r3.status_code == 200 and _d3.get('success') is True, 'лог-таблица через панель ушла при живом боте', f'→ {r3.status_code} {_d3}')
check(bool(_gsend_ch.sent) and 'view' in _gsend_ch.sent[0] and 'file' in _gsend_ch.sent[0], 'в канал легли картинка-таблица и живые кнопки')
check(_d3.get('channel') == _gsend_ch.name, 'в ответе панели имя канала')

_gstaff_ch = _FakeChannel()
_bot.get_guild = lambda gid: _FakeGuildSend([_gstaff_ch]) if gid == 777 else None
r4 = _client.post('/api/staff-stats/send', json={'channel_id': str(_gstaff_ch.id), 'days': 30})
_d4 = r4.get_json() or {}
check(r4.status_code == 200 and _d4.get('success') is True, 'staff-таблица через панель ушла', f'→ {r4.status_code} {_d4}')
check(bool(_gstaff_ch.sent) and 'embed' in _gstaff_ch.sent[0], 'в канал лёг embed-таблицы')

webapp._panel_log_flusher.shutdown()
_audit = json.load(open('data/panel_logs.json', encoding='utf-8'))
_acts = [e.get('action') for e in _audit if isinstance(e, dict)]
check('LOGS_TABLE_SEND' in _acts and 'STAFF_STATS_SEND' in _acts, 'аудит помнит отправки', f'→ {[_a for _a in _acts if "SEND" in str(_a)]}')

r5 = _client.post('/api/logs/table/send', json={'channel_id': ''})
check(r5.status_code == 400 and 'Канал не найден' in (r5.get_json() or {}).get('error', ''), 'нет канала → честный отказ')

_loop8.call_soon_threadsafe(_loop8.stop)
_thread8.join(timeout=2)
_dead_ch = _FakeChannel()
_bot.get_guild = lambda gid: _FakeGuildSend([_dead_ch]) if gid == 777 else None
_t0 = time.time()
r6 = _client.post('/api/logs/table/send', json={'channel_id': str(_dead_ch.id)})
_waited = time.time() - _t0
check(r6.status_code in (400, 502, 503) and _waited < 5, f'мертвый цикл → быстрый отказ ({_waited:.1f} с)')
check(not _dead_ch.sent, 'в мертвый цикл ничего не улетело')
webapp.bot_instance = None

print()
print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
