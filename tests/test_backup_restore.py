# -*- coding: utf-8 -*-
"""Восстановление из бэкапа гильдии: /api/guild/777/restore + /api/restore-upload.

Сценарий аудита «все связки»: restore по backup_id и по загруженному
файлу (роли/каналы реально создаются в фейк-гильдии), идемпотентность
повторного запуска, отказные пути (нет файла / неизвестный id / битый
JSON / мусорная структура), traversal на скачивании и удалении архивов.

История: do_restore() раньше запускали как корутину через
run_coroutine_threadsafe → ЛЮБОЙ валидный restore падал в 500; битый
backups.json (валидный JSON не-список) ронял маршрут AttributeError'ом.
Оба дефекта исправлены, этот тест — регресс.

Запуск: python3 tests/test_backup_restore.py
"""
import io
import json
import os
import sys
import tempfile
import asyncio
import threading

os.environ['PANEL_USER'] = 'owner'
os.environ['PANEL_PASSWORD'] = 'owner-pass-123'
os.environ['OWNER_ID'] = '42'
os.environ.pop('DEMO_MODE', None)
os.environ['MAIN_GUILD_ID'] = '777'
os.environ['PANEL_LOGIN_CONFIRM'] = '0'
_TMP = tempfile.mkdtemp(prefix='hakumo_restore_')
os.chdir(_TMP)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from types import SimpleNamespace as NS

# role_map до импорта web.app (читается один раз на import)
os.makedirs('data', exist_ok=True)
json.dump({'400': 'curator'}, open('data/role_map.json', 'w'))

import web.app as A


class FakeRole:
    def __init__(self, name):
        self.name = name


class FakeChannel:
    def __init__(self, name):
        self.name = name


GUILD_STATE = {'roles': [FakeRole('everyone-exists')], 'channels': [FakeChannel('general')]}


class FakeGuild:
    id = 777
    owner_id = 42
    name = 'RestoreGuild'
    roles = property(lambda self: GUILD_STATE['roles'])
    channels = property(lambda self: GUILD_STATE['channels'])

    def get_member(self, uid):
        return None

    async def create_role(self, **kw):
        r = FakeRole(kw['name'])
        GUILD_STATE['roles'].append(r)
        return r

    async def create_text_channel(self, **kw):
        c = FakeChannel(kw['name'])
        GUILD_STATE['channels'].append(c)
        return c

    async def create_voice_channel(self, **kw):
        c = FakeChannel(kw['name'])
        GUILD_STATE['channels'].append(c)
        return c

    async def create_category(self, **kw):
        c = FakeChannel(kw['name'])
        GUILD_STATE['channels'].append(c)
        return c


guild = FakeGuild()
loop = asyncio.new_event_loop()
threading.Thread(target=loop.run_forever, daemon=True).start()
A.bot_instance = NS(guilds=[guild], get_guild=lambda gid: guild if gid == 777 else None,
                    loop=loop, latency=0.05, get_cog=lambda n: None,
                    get_channel=lambda cid: None, get_role=lambda rid: None,
                    change_presence=lambda **k: None, description='stub', application_id=1,
                    user=NS(id=1, name='bot'))

c = A.app.test_client()
c.post('/login', data={'username': 'owner', 'password': 'owner-pass-123'})

PASS = 0
FAIL = 0


def check(ok, label, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {label}')
    else:
        FAIL += 1
        print(f'  FAIL: {label} {extra}')


# 1. backups.json отсутствует
r = c.post('/api/guild/777/restore', json={'backup_id': 'bk1'})
check(r.status_code == 200 and 'не найдена' in r.get_json().get('error', ''),
      'restore без backups.json → «Резервная копия не найдена»', r.get_data(as_text=True)[:120])

# 2. валидный backups.json
BK = [{'id': 'bk1', 'guild_name': 'OldServer', 'created_at': '2026-01-01',
       'role': [{'name': 'TestRole', 'color': '#ff0000', 'hoist': True, 'mentionable': False, 'permissions': 8}],
       'channels': [{'name': 'тест-канал', 'type': 'text', 'topic': 'тема'},
                    {'name': 'Голосовая', 'type': 'voice'},
                    {'name': 'Категория', 'type': 'category'}]}]
json.dump(BK, open('data/backups.json', 'w'))

# 3. несуществующий id
r = c.post('/api/guild/777/restore', json={'backup_id': 'nope'})
check('не найдена' in r.get_json().get('error', ''),
      'restore с неизвестным id → «Резервная копия не найдена»', r.get_data(as_text=True)[:120])

# 4. валидный restore
r = c.post('/api/guild/777/restore', json={'backup_id': 'bk1'})
j = r.get_json()
check(bool(j.get('success')) and j['result']['roles_created'] == 1
      and j['result']['channels_created'] == 3 and not j['result']['errors'],
      'restore bk1 → success, roles=1, channels=3', r.get_data(as_text=True)[:200])
check(any(x.name == 'TestRole' for x in GUILD_STATE['roles'])
      and any(x.name == 'тест-канал' for x in GUILD_STATE['channels']),
      'фейк-гильдия получила роль и каналы')

# 5. идемпотентность
r = c.post('/api/guild/777/restore', json={'backup_id': 'bk1'})
j = r.get_json()
check(bool(j.get('success')) and j['result']['roles_created'] == 0 and j['result']['channels_created'] == 0,
      'повторный restore → roles=0, channels=0 (дедуп по именам)', r.get_data(as_text=True)[:200])

# 6. мусорная структура (валидный JSON, не список) — раньше AttributeError → 500
json.dump({'битый': 1}, open('data/backups.json', 'w'))
r = c.post('/api/guild/777/restore', json={'backup_id': 'bk1'})
check(r.status_code == 200 and 'error' in r.get_json(),
      'restore с мусорным backups.json → вежливая ошибка, не 500', r.get_data(as_text=True)[:150])
json.dump(BK, open('data/backups.json', 'w'))

# 7. multipart с битым JSON
r = c.post('/api/guild/777/restore',
           data={'file': (io.BytesIO('{битый json'.encode()), 'b.json')})
check('Неверный JSON' in r.get_json().get('error', ''),
      'restore с битым JSON-файлом → «Неверный JSON-файл»', r.get_data(as_text=True)[:120])

# 8. multipart с валидным JSON → восстановление по upload
UP = {'guild_name': 'UploadedGuild', 'created_at': '2026-02-02',
      'role': [{'name': 'UpRole', 'color': '#00ff00', 'hoist': False, 'mentionable': True, 'permissions': 0}],
      'channels': [{'name': 'up-channel', 'type': 'text', 'topic': ''}]}
r = c.post('/api/guild/777/restore',
           data={'file': (io.BytesIO(json.dumps(UP).encode()), 'u.json')})
j = r.get_json()
check(bool(j.get('success')) and j['result']['roles_created'] == 1 and j['result']['channels_created'] == 1,
      'restore upload → success, roles=1, channels=1', r.get_data(as_text=True)[:200])

# 9. restore-upload: предпросмотр валидного файла
r = c.post('/api/restore-upload',
           data={'file': (io.BytesIO(json.dumps(UP).encode()), 'u.json')})
j = r.get_json()
check(j.get('guild_name') == 'UploadedGuild' and j.get('roles_count') == 1
      and j.get('channels_count') == 1 and j.get('has_settings') is False,
      'restore-upload → метаданные (guild, counts)', r.get_data(as_text=True)[:200])

# 10. restore-upload: крайние случаи
r = c.post('/api/restore-upload', data={})
check('Файл отсутствует' in r.get_json().get('error', ''),
      'restore-upload без файла → «Файл отсутствует»', r.get_data(as_text=True)[:120])
r = c.post('/api/restore-upload',
           data={'file': (io.BytesIO('не json'.encode()), 'x.json')})
check('Неверный файл' in r.get_json().get('error', ''),
      'restore-upload с битым → error «Неверный файл»', r.get_data(as_text=True)[:120])

# 11. traversal на скачивании/удалении архивов панели
open('data/canary.json', 'w').write('secret')
r = c.get('/api/backups/download/..%2F..%2Fcanary.json')
check(r.status_code == 404, 'download ..%2F → 404 (route не матчит слэши)', str(r.status_code))
r = c.get('/api/backups/download/..')
check(r.status_code == 404, 'download «..» → 404 «Архив не найден»', str(r.status_code))
r = c.delete('/api/backups/..')
check(r.status_code == 400 and 'Некорректное имя' in r.get_json().get('error', ''),
      'DELETE «..» → 400 «Некорректное имя»', f'{r.status_code} {r.get_data(as_text=True)[:100]}')
r = c.delete('/api/backups/..%2Fcanary.json')
check(r.status_code == 404, 'DELETE ..%2F → 404 (не матчится)', str(r.status_code))
check(open('data/canary.json').read() == 'secret', 'канарейка не тронута')

print(f'\n════ RESTORE: PASS {PASS} / FAIL {FAIL} ════')
sys.exit(1 if FAIL else 0)
