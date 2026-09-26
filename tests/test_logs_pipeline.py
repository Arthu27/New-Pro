# -*- coding: utf-8 -*-
"""Поток логов: Discord-событие → диск → панель, панель → каналы.

Ключи панели (mod) и русские имена каналов («модерация») должны
сворачиваться в одно; /message-logs не должен строить /api/guild//...;
в журнале канал виден и из поля channel.

Запуск: python3 tests/test_logs_pipeline.py
"""
import asyncio
import importlib
import json
import os
import shutil
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import MagicMock

_TMP = tempfile.mkdtemp(prefix='hakumo_logs_pipe_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)

os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['PANEL_USER'] = 'owner'
os.environ['PANEL_PASSWORD'] = 'test123'
os.environ['MAIN_GUILD_ID'] = ''
os.environ['DEMO_MODE'] = '1'
os.environ['DEMO_FORCE'] = '1'
os.environ['TOKEN'] = ''
os.environ['PANEL_LOGIN_CONFIRM'] = '0'

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


print('== 1. Канон категорий: RU == panel key ==')
from services.log_settings import (  # noqa: E402
    canonical_category, category_enabled, autocreate_allowed,
    set_log_settings, get_log_settings, _save, dest_category,
    LOG_CATEGORIES, LOG_GROUPS,
)

check(canonical_category('модерация') == 'mod', 'модерация → mod')
check(canonical_category('mod') == 'mod', 'mod остаётся mod')
check(canonical_category('ses') == 'voice', 'ses → voice')
check(canonical_category('guild') == 'сервер', 'guild → сервер')
check(canonical_category('ticket-log') == 'ticket-log',
      'ticket-log не сворачивается')
check(canonical_category('ai-alerts') == 'ai-alerts',
      'ai-alerts не сворачивается')
check(dest_category('модерация') == 'mod', 'dest: модерация остаётся mod')
check(dest_category('наказания') == 'warn', 'dest: наказания → warn')
check(dest_category('channel') == 'rest', 'dest: каналы → rest')
check(dest_category('сервер') == 'rest', 'dest: сервер → rest')
check(dest_category('ban') == 'ban', 'dest: ban остаётся ban')
_panel_keys = [k for k, _, _ in LOG_CATEGORIES]
check(_panel_keys == ['message', 'voice', 'nick', 'member', 'rest',
                      'ban', 'mute', 'staff', 'warn'],
      'панель: логи + отчёты, наказания разделены')
check([g[0] for g in LOG_GROUPS] == ['logs', 'reports'],
      'две группы: логи и отчёты')

set_log_settings(42, enabled={'mod': False}, autocreate={'mod': True})
check(category_enabled(42, 'модерация') is False,
      'enabled.mod=off гасит и «модерация»')
check(category_enabled(42, 'mod') is False, 'enabled.mod=off гасит mod')
check(autocreate_allowed(42, 'модерация') is True,
      'autocreate.mod=on разрешает и «модерация»')
check(autocreate_allowed(42, 'mod') is True, 'autocreate.mod=on разрешает mod')

_save(42, {'enabled': {'модерация': False, 'mod': True},
           'autocreate': {}, 'channels': {}})
check(category_enabled(42, 'модерация') is True,
      'точный канон побеждает alias при свёртке')

print('== 2. get_log_channel: выключенный mod, канал есть ==')
from cogs.logs import Logs, save_event, flush_audit  # noqa: E402

set_log_settings(42, enabled={'mod': False})


class _Ch:
    def __init__(self, name):
        self.name = name
        self.id = 111


class _Guild:
    id = 42
    text_channels = [_Ch('🛡・модерация')]
    forums = []
    categories = []

    def get_channel(self, cid):
        return None

    def get_channel_or_thread(self, cid):
        return None


_cog = Logs(MagicMock())
_got = asyncio.run(_cog.get_log_channel(_Guild(), 'модерация'))
check(_got is None, 'get_log_channel(модерация) = None, хотя канал существует')

print('== 2b. Поиск ветки по имени, без ID ==')
from cogs.logs import find_log_channel  # noqa: E402


class _Th:
    def __init__(self, name, parent_name, id_):
        self.name = name
        self.id = id_
        self.parent_id = 90
        self.parent = SimpleNamespace(name=parent_name, id=90)
        self.type = SimpleNamespace(name='public_thread')


class _GuildThreads:
    id = 42
    text_channels = []
    forums = []
    threads = [
        _Th('сообщения', '・логи', 11),
        _Th('войсы', '・логи', 12),
        _Th('никнеймы', '・логи', 13),
        _Th('зашел/вышел', '・логи', 14),
        _Th('остальное', '・логи', 15),
        _Th('баны', '・отчеты', 21),
        _Th('муты войс/чат', '・отчеты', 22),
        _Th('снятие/чс стаффа', '・отчеты', 23),
        _Th('варны', '・отчеты', 24),
    ]

    def get_channel(self, cid):
        return None

    def get_channel_or_thread(self, cid):
        return None


_gt = _GuildThreads()
_want = {
    'message': 11, 'voice': 12, 'nick': 13, 'member': 14, 'rest': 15,
    'ban': 21, 'mute': 22, 'staff': 23, 'warn': 24,
}
for _k, _id in _want.items():
    _ch = find_log_channel(_gt, _k)
    check(_ch is not None and _ch.id == _id,
          f'ветка {_k} → id {_id}', )

print('== 3. save_event: канон, channel_name, skip обычных сообщений ==')
save_event(777, 'message', 'Сообщение отправлено',
           {'channel': 'флудилка', 'content': 'привет'})
flush_audit()
_audit_path = 'data/audit_log.json'
_audit = {}
if os.path.exists(_audit_path):
    _audit = json.load(open(_audit_path, encoding='utf-8'))
_evs = _audit.get('777') or []
check(not any(e.get('action') == 'Сообщение отправлено' for e in _evs),
      'обычная отправка в аудит не пишется')

save_event(777, 'модерация', 'Бан', {
    'user_name': 'Мира', 'channel': 'мод-чат',
})
save_event(777, 'message', 'Сообщение удалено', {
    'user_name': 'Мира', 'channel': 'флудилка', 'content': 'упс',
})
flush_audit()
_audit = json.load(open(_audit_path, encoding='utf-8'))
_evs = _audit.get('777') or []
_ban = next((e for e in _evs if e.get('action') == 'Бан'), None)
_del = next((e for e in _evs if e.get('action') == 'Сообщение удалено'), None)
check(_ban is not None and _ban.get('category') == 'mod',
      'save_event сворачивает «модерация» в mod')
check(_del is not None and _del.get('channel_name') == 'флудилка',
      'save_event копирует channel → channel_name')
check(_del.get('channel') == 'флудилка',
      'исходное поле channel сохраняется')

print('== 4. Панель: пустой MAIN_GUILD_ID → option 777, журнал видит канал ==')
appmod = importlib.import_module('web.app')
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()
with client.session_transaction() as s:
    s.clear()
    s['logged_in'] = True
    s['username'] = 'owner'
    s['role'] = 'owner'
    s['selected_guild'] = '777'
    s['main_guild_id'] = ''

r = client.get('/message-logs')
html = r.get_data(as_text=True)
check(r.status_code == 200, '/message-logs отдаёт 200')
check('value="777"' in html, 'селект сервера — 777, не пустой gid')
check('/api/guild//' not in html, 'нет битого /api/guild//')

r = client.get('/api/guild/777/message-logs')
rows = r.get_json() or []
check(r.status_code == 200 and any(
    (x.get('channel_name') or x.get('channel')) == 'флудилка' for x in rows),
      'API /message-logs отдаёт имя канала из audit')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
