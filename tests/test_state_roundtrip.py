# -*- coding: utf-8 -*-
"""Round-trip переходов состояния через демо-API панели.

Новый тип проверки: не «отвечает 200», а «создал → увидел в списке →
изменил → удалил → вернулось как было» (и негативные переходы дают
корректные 400/404). Ловит баги класса «кнопка есть, но состояние
не сохраняется».

Проверки (демо-режим, временная data/-директория):
1. Роли: создать → появилась в списке → удалить → исчезла;
   без имени → 400; удаление несуществующей → 404.
2. Расписание: save → появился анонс → toggle дважды (enabled меняется)
   → delete → исчез; пустой анонс → 400; delete чужого id → 404.
3. Leveling: PATCH конфига сохраняется и читается обратно, затем
   возврат исходного значения.
4. Хранилище после всех операций — валидный JSON (не развалилось).

Запуск: python3 tests/test_state_roundtrip.py
"""
import json
import os
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_roundtrip_')
os.chdir(_TMP)
os.makedirs('data', exist_ok=True)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault('PANEL_USER', 'admin')
os.environ.setdefault('PANEL_PASSWORD', 'test123')
os.environ['MAIN_GUILD_ID'] = '777'
os.environ['DEMO_MODE'] = '1'

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


import web.app as appmod  # noqa: E402

appmod.app.config['TESTING'] = True
client = appmod.app.test_client()

with client.session_transaction() as s:
    s['logged_in'] = True
    s['username'] = 'admin'
    s['role'] = 'owner'
    s['selected_guild'] = '777'

GID = '777'


def roles_list():
    r = client.get(f'/api/guild/{GID}/roles')
    assert r.status_code == 200, f'GET roles → {r.status_code}'
    return r.get_json()


def sched_state():
    r = client.get('/api/schedule/state')
    assert r.status_code == 200, f'GET schedule/state → {r.status_code}'
    return r.get_json()


# ─── 1. роли ─────────────────────────────────────────────────────────────────
print('== 1. Роли: создать → увидеть → удалить ==')
before = roles_list()
n_before = len(before)
r = client.post(f'/api/guild/{GID}/roles/create', json={'name': 'Тестовая роль', 'color': '#123456'})
check(r.status_code == 200 and r.get_json().get('success'), f'создание роли → {r.status_code}')

after_create = roles_list()
new_role = [x for x in after_create if x.get('name') == 'Тестовая роль']
check(len(after_create) == n_before + 1 and len(new_role) == 1,
      f'роль появилась в списке ({len(after_create)} = {n_before} + 1)')

if new_role:
    rid = new_role[0]['id']
    r = client.post(f'/api/guild/{GID}/roles/{rid}/delete')
    check(r.status_code == 200 and r.get_json().get('success'), f'удаление роли → {r.status_code}')
    after_delete = roles_list()
    check(len(after_delete) == n_before and not any(x.get('id') == rid for x in after_delete),
          f'роль исчезла из списка (снова {len(after_delete)})')

r = client.post(f'/api/guild/{GID}/roles/create', json={})
check(r.status_code == 400, f'создание без имени → 400 (получено {r.status_code})')
r = client.post(f'/api/guild/{GID}/roles/999999/delete')
check(r.status_code == 404, f'удаление несуществующей → 404 (получено {r.status_code})')

# ─── 2. расписание ───────────────────────────────────────────────────────────
print('== 2. Расписание: save → toggle → delete ==')
state0 = sched_state()
n0 = len(state0.get('items', []))
r = client.post('/api/schedule/save', json={
    'content': 'Тестовый анонс round-trip', 'channel_id': 1002,
    'repeat': 'once', 'time': '20:00', 'tz_offset': 3})
data = r.get_json()
check(r.status_code == 200 and data.get('ok') and data.get('id'), f'save анонса → id={data.get("id")}')

new_id = data.get('id')
state1 = sched_state()
item = [i for i in state1.get('items', []) if i.get('id') == new_id]
check(len(state1.get('items', [])) == n0 + 1 and len(item) == 1,
      f'анонс появился в state ({len(state1.get("items", []))} = {n0} + 1)')

enabled0 = item[0].get('enabled') if item else None
r = client.post('/api/schedule/toggle', json={'id': new_id})
t1 = r.get_json()
r = client.post('/api/schedule/toggle', json={'id': new_id})
t2 = r.get_json()
check(r.status_code == 200 and t1.get('ok') and t2.get('ok')
      and bool(t1.get('enabled')) != bool(t2.get('enabled')),
      f'toggle дважды: enabled {t1.get("enabled")} → {t2.get("enabled")} (исходно {enabled0})')

r = client.post('/api/schedule/delete', json={'id': new_id})
check(r.status_code == 200 and r.get_json().get('ok'), f'delete анонса → {r.status_code}')
state2 = sched_state()
check(len(state2.get('items', [])) == n0 and not any(i.get('id') == new_id for i in state2.get('items', [])),
      f'анонс исчез (снова {len(state2.get("items", []))})')

r = client.post('/api/schedule/save', json={})
check(r.status_code == 400, f'save пустого анонса → 400 (получено {r.status_code})')
r = client.post('/api/schedule/delete', json={'id': 999999})
check(r.status_code == 404, f'delete чужого id → 404 (получено {r.status_code})')

# ─── 3. leveling config ──────────────────────────────────────────────────────
print('== 3. Leveling: PATCH конфига сохраняется ==')
cfg0 = client.get('/api/leveling/config').get_json()
en0 = cfg0.get('enabled')
r = client.post('/api/leveling/config', json={'enabled': False})
check(r.status_code == 200 and r.get_json().get('ok'), f'PATCH конфига → {r.status_code}')
cfg1 = client.get('/api/leveling/config').get_json()
check(cfg1.get('enabled') is False, f'enabled=False сохранился (получено {cfg1.get("enabled")})')
client.post('/api/leveling/config', json={'enabled': en0})
cfg2 = client.get('/api/leveling/config').get_json()
check(cfg2.get('enabled') == en0, f'возврат исходного enabled={en0} (получено {cfg2.get("enabled")})')

# ─── 4. хранилище цело ───────────────────────────────────────────────────────
print('== 4. Хранилище — валидный JSON после операций ==')
ok = True
for fname in (f'data/demo_roles_{GID}.json', f'data/schedule_demo_{GID}.json'):
    if not os.path.exists(fname):
        check(False, f'{fname} не создан')
        ok = False
        continue
    try:
        json.load(open(fname, encoding='utf-8'))
    except Exception as e:  # noqa: BLE001
        check(False, f'{fname} битый: {e}')
        ok = False
check(ok, 'файлы демо-хранилища валидны')

shutil.rmtree(_TMP, ignore_errors=True)
print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
