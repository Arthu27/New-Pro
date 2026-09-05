# -*- coding: utf-8 -*-
"""Таблицы и сохранения (владелец, 2026-09-05).

1) «Таблица опять не отправляется»: у графической таблицы логов
   (LogBrowserView) и у таблицы активности персонала (/staff-stats)
   теперь ЕСТЬ рабочие точки отправки — панель → Discord
   (Журнал модерации → «Таблица в Discord»; Контроль команды →
   «Таблица активности в Discord»).
2) «Канал не включается после заявки»: канал апелляции открывается
   надёжно (fetch_channel-запас + имя канала в ЛС-ответе), заявка в
   персонал больше не теряется тихо при ненастроенном канале.
3) «Права команд данные не сохраняются» + «проверь как комнаты»:
   сквозная проверка сохранения Права команд (/api/role-permissions) и
   комнат (/api/panel-menu) — POST → перечитывание (в т.ч. «как после
   рестарта»).

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

# регистрация persistent-view на рестарте (on_ready)
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
print('== 3. Канал апелляции: открывается после заявки (надёжно) ==')
from cogs.appeals import Appeals  # noqa: E402
from services import channel_routes as CR  # noqa: E402

CR.ROUTES_FILE = os.path.abspath('data/channel_routes.json')
APPEAL_CH_ID = 1544483947705008188


class _PermChannel:
    def __init__(self, cid=APPEAL_CH_ID):
        self.id = cid
        self.name = 'апелляции'
        self.overwrites = {}

    async def set_permissions(self, target, overwrite=None):
        self.overwrites[target.id] = overwrite


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
    """Гильдия, где get_channel в кэш не находит канал (как после рестарта)."""

    def get_channel(self, cid):
        return None

    async def fetch_channel(self, cid):
        return self._by_id.get(cid)


_cog = Appeals.__new__(Appeals)   # без __init__ (не тянем бота)
_pc = _PermChannel()

# 3а. Канал в кэше: маршрут настроен → открываем view+send
CR.set_route(_G2.id, 'ban_appeal_channel', APPEAL_CH_ID)
_g2 = _G2([_pc])
opened, ch_ref = asyncio.new_event_loop().run_until_complete(
    _cog._open_appeal_channel(_g2, _User()))
check(opened and ch_ref is _pc, 'маршрут настроен → канал открыт')
ow = _pc.overwrites.get(_User().id)
check(ow is not None and ow.view_channel is True and ow.send_messages is True,
      'перезапись даёт view_channel + send_messages')

# 3б. Канала НЕТ в кэше → fetch_channel находит (после рестарта тоже открывается)
_pc2 = _PermChannel()
_g3 = _G3([_pc2])
opened3, ch3 = asyncio.new_event_loop().run_until_complete(
    _cog._open_appeal_channel(_g3, _User()))
check(opened3 and ch3 is _pc2,
      'канала нет в кэше → fetch_channel: канал всё равно открывается')

# 3в. Маршрут пуст, но карточка ушла в fallback → открываем его
CR.set_route(_G2.id, 'ban_appeal_channel', 0)
_pc3 = _PermChannel(cid=999)
_g4 = _G2([_pc3])
opened4, ch4 = asyncio.new_event_loop().run_until_complete(
    _cog._open_appeal_channel(_g4, _User(), fallback_channel=_pc3))
check(opened4 and ch4 is _pc3,
      'пустой маршрут → открываем канал, куда легла карточка')

# 3г. Ни маршрута, ни fallback — честный отказ (False), без фейка «открыто»
opened5, ch5 = asyncio.new_event_loop().run_until_complete(
    _cog._open_appeal_channel(_g4, _User()))
check(opened5 is False and ch5 is None, 'открывать нечего → честный отказ')

# 3д. ЛС-подтверждение называет ИМЯ канала
line = _cog._dm_channel_line(True, _pc)
check('#апелляции' in line, 'в ЛС видно имя открытого канала',
      f'→ {line[:60]}')
line_bad = _cog._dm_channel_line(False, None)
check('не получилось' in line_bad, 'не открылся → честная строка без обещаний')

# ═══════════════════════════════════════════════════════════════════
print('== 4. Заявка в персонал не теряется тихо ==')
src = open(os.path.join(ROOT, 'cogs', 'staff_apply.py'), encoding='utf-8').read()
check('delivery' in src and 'no_channel' in src,
      'ненастроенный канал заявки фиксируется в данных (delivery=no_channel)')
check('не доставлено' in src.lower() or 'не доставлен' in src.lower(),
      'заявитель получает честное сообщение, если персонал не уведомлён')
check('log.warning' in src,
      'случай «канал заявок не настроен» попадает в лог (не тихо)')

# ═══════════════════════════════════════════════════════════════════
print('== 5. Права команд: данные сохраняются (POST → перечитывание → рестарт) ==')
os.environ['DEMO_MODE'] = '1'
os.environ['PANEL_USER'] = 'owner'
os.environ['PANEL_PASSWORD'] = 'x'
os.environ['MAIN_GUILD_ID'] = '777'
os.environ['PANEL_PORT'] = '5099'

import web.app as webapp  # noqa: E402

_client = webapp.app.test_client()
_demo_guild_id = '777'

# 5а. Доступ к странице
r_page = _client.get('/role-permissions')
check(r_page.status_code == 200, 'страница «Права команд» открывается',
      f'→ {r_page.status_code}')

# 5б. POST правило на команду → GET возвращает сохранённое
r_set = _client.post(f'/api/role-permissions/{_demo_guild_id}/set',
                     json={'command': 'report', 'role_ids': ['9001', '9003']})
check(r_set.status_code == 200 and r_set.get_json().get('success'),
      'POST /set принимает правило', f'→ {r_set.status_code}')
r_get = _client.get(f'/api/role-permissions/{_demo_guild_id}')
acl = r_get.get_json().get('acl') or {}
check(acl.get('report') == ['9001', '9003'],
      'GET после POST показывает сохранённое правило', f'→ {acl.get("report")}')

# 5в. «Как после рестарта»: читаем напрямую из БД (новое соединение)
from services.permission_acl import load_acl, load_action_acl, set_action_rule  # noqa: E402
disk_acl = load_acl(777)
check(disk_acl.get('report') == ['9001', '9003'],
      'правило лежит в БД — переживает рестарт панели', f'→ {disk_acl}')

# 5г. Действие модерации (классические разрешения) — тот же цикл
r_act = _client.post(f'/api/role-permissions/{_demo_guild_id}/action/set',
                     json={'action': 'ban', 'role_ids': ['9002']})
check(r_act.status_code == 200 and r_act.get_json().get('success'),
      'POST action/set принимает правило действия')
disk_actions = load_action_acl(777)
check(disk_actions.get('ban') == ['9002'],
      'правило действия в БД («бан» только выбранной роли)', f'→ {disk_actions}')

# 5д. Категория целиком: назначение ролей материализуется в команды
r_cat = _client.post(f'/api/role-permissions/{_demo_guild_id}/category/assign',
                     json={'category': 'Модерация', 'role_ids': ['9003']})
check(r_cat.status_code == 200 and r_cat.get_json().get('success'),
      'POST category/assign назначает категорию')
disk_acl = load_acl(777)
check(any(str(v) == "['9003']" for v in disk_acl.values()),
      'правила категории материализованы на команды', f'→ {list(disk_acl.items())[:3]}')

# ═══════════════════════════════════════════════════════════════════
print('== 6. «Комнаты» (Меню панели): сохранение страниц и групп ==')
r_pm = _client.post('/api/panel-menu',
                    json={'role': 'mod', 'groups': ['Модерация', 'Логи'],
                          'items': ['/logs', '/staff-apps']})
check(r_pm.status_code == 200 and r_pm.get_json().get('success'),
      'POST /api/panel-menu сохраняет комнаты модератора')
from services.panel_menu import get_config  # noqa: E402
cfg = get_config()
check(cfg.get('mod', {}).get('items') == ['/logs', '/staff-apps']
      and set(cfg.get('mod', {}).get('groups') or []) == {'Модерация', 'Логи'},
      'комнаты прочитаны из файла — переживают рестарт панели', f'→ {cfg}')
r_pm_bad = _client.post('/api/panel-menu', json={'role': 'vladelec', 'groups': [], 'items': []})
check(r_pm_bad.status_code == 400,
      'чужая роль не проходит (валидация входа)')

# ═══════════════════════════════════════════════════════════════════
print('== 7. Точки отправки таблиц из панели существуют ==')
r1 = _client.post('/api/logs/table/send', json={'channel_id': '555'})
check(r1.status_code in (400, 502, 503),
      'лог-таблица: без бота — честный отказ (не «отправлено»)',
      f'→ {r1.status_code}')
r2 = _client.post('/api/staff-stats/send', json={'channel_id': '555', 'days': 30})
check(r2.status_code in (400, 502, 503),
      'staff-таблица: без бота — честный отказ (не «отправлено»)',
      f'→ {r2.status_code}')

# ═══════════════════════════════════════════════════════════════════
print('== 8. Счастливый путь: панель + живой бот → таблица в канале ==')
# «Живой бот»: цикл КРУТИТСЯ в фоновом потоке (как боевой бот) — иначе
# run_coroutine_threadsafe честно виснет по таймауту.
_loop8 = asyncio.new_event_loop()
_thread8 = threading.Thread(target=_loop8.run_forever, daemon=True)
_thread8.start()
_bot.loop = _loop8
webapp.bot_instance = _bot                      # «бот поднялся»
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
check(r3.status_code == 200 and _d3.get('success') is True,
      'лог-таблица через панель ушла при живом боте', f'→ {r3.status_code} {_d3}')
check(bool(_gsend_ch.sent) and 'view' in _gsend_ch.sent[0] and 'file' in _gsend_ch.sent[0],
      'в канал легли картинка-таблица и живые кнопки')
check(_d3.get('channel') == _gsend_ch.name,
      'в ответе панели имя канала (не пустышка)')

_gstaff_ch = _FakeChannel()
_bot.get_guild = lambda gid: _FakeGuildSend([_gstaff_ch]) if gid == 777 else None
r4 = _client.post('/api/staff-stats/send', json={'channel_id': str(_gstaff_ch.id), 'days': 30})
_d4 = r4.get_json() or {}
check(r4.status_code == 200 and _d4.get('success') is True,
      'staff-таблица через панель ушла при живом боте', f'→ {r4.status_code} {_d4}')
check(bool(_gstaff_ch.sent) and 'embed' in _gstaff_ch.sent[0],
      'в канал лёг embed-таблицы активности')

# аудит: записи о отправках попали в panel_logs.json
webapp._panel_log_flusher.shutdown()
_audit = json.load(open('data/panel_logs.json', encoding='utf-8'))
_acts = [e.get('action') for e in _audit if isinstance(e, dict)]
check('LOGS_TABLE_SEND' in _acts and 'STAFF_STATS_SEND' in _acts,
      'аудит панели помнит обе отправки (LOGS_TABLE_SEND / STAFF_STATS_SEND)',
      f'→ {[_a for _a in _acts if "SEND" in str(_a)]}')

# без канала и без system_channel — честный 400
r5 = _client.post('/api/logs/table/send', json={'channel_id': ''})
check(r5.status_code == 400 and 'Канал не найден' in (r5.get_json() or {}).get('error', ''),
      'нет канала и системного → честный отказ, не «успех»')

# бот «умер»: цикл остановлен → мгновенный честный отказ (не 20-секундное висение)
_loop8.call_soon_threadsafe(_loop8.stop)
_thread8.join(timeout=2)
_dead_ch = _FakeChannel()
_bot.get_guild = lambda gid: _FakeGuildSend([_dead_ch]) if gid == 777 else None
_t0 = time.time()
r6 = _client.post('/api/logs/table/send', json={'channel_id': str(_dead_ch.id)})
_waited = time.time() - _t0
check(r6.status_code in (400, 502, 503) and _waited < 5,
      f'мертвый цикл бота → быстрый честный отказ ({_waited:.1f} с, не 20)')
check(not _dead_ch.sent, 'в мертвый цикл ничего не улетело')
webapp.bot_instance = None                      # вернуть как было

print()
print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
