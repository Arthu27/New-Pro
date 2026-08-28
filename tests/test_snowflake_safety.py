# -*- coding: utf-8 -*-
"""Снежинки Discord и ID сервера — защита точности id.

Два связанных класса багов, найденных по жалобе «выбираю канал посреди
списка — слетает на другой» + «Щит пишет Другие серверы бота недоступны,
staff-limits 404»:

1. JS хранит числа как double: int > 2^53 в JSON теряет цифры (id каналов
   и ролей новых серверов — 18..19 цифр). web.routes._common.jsonify
   теперь отдаёт такие int строкой; Каналы и маршруты, настройки
   модерации, PagerDuty и анти-фейк шлют id строками, не Number/parseInt.
2. MAIN_GUILD_ID из .env нормализуется до цифр (пробелы/кавычки/комментарий)
   — как clean_number у бота: иначе гейт /api/guild/<id> отвечал 404
   «Другие серверы бота недоступны» на живые API (staff-limits и др.).

Запуск: python3 tests/test_snowflake_safety.py
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_snow_test_')
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


print('== 1. Safe jsonify: снежинки → строки ==')
from web.routes._common import _json_snow, _JS_SAFE_INT_MAX  # noqa: E402

BIG = 1384282749317152878            # реальный id уровня сервера юзера
check(BIG > _JS_SAFE_INT_MAX, 'BIG действительно больше 2^53')
s = _json_snow({'channel_id': BIG, 'zero': 0, 'n': None,
                'items': [BIG, {'uid': BIG}], 'flag': True})
check(s['channel_id'] == str(BIG), 'большой int → строка')
check(s['zero'] == 0 and s['n'] is None and s['flag'] is True,
      '0/None/True не трогаем')
check(s['items'][0] == str(BIG) and s['items'][1]['uid'] == str(BIG),
      'вложенные list/dict чистятся')
check(_json_snow(12345) == 12345, 'малое число остаётся числом')
check(_json_snow(-BIG) == str(-BIG), 'отрицательные большие — тоже строки')
check(_json_snow(_JS_SAFE_INT_MAX) == _JS_SAFE_INT_MAX, 'граница 2^53 — число')
check(_json_snow(_JS_SAFE_INT_MAX + 1) == str(_JS_SAFE_INT_MAX + 1),
      '2^53+1 — уже строка')

print('== 2. Сквозной поток «Каналы и маршруты» с реальным id ==')
import importlib  # noqa: E402
appmod = importlib.import_module('web.app')
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()

with client.session_transaction() as sess:
    sess.clear()
    sess['logged_in'] = True
    sess['username'] = 'admin'
    sess['role'] = 'admin'

CH = str(1384282749317152878)
r = client.get('/api/channel-routes').get_json()
check(r['success'] and int(r['gid']) == 777, 'список маршрутов открывается')
check(any(x['key'] == 'proof_channel' for x in r['routes']),
      'маршрут proof_channel есть в списке')

r = client.post('/api/channel-routes/proof_channel', json={'channel_id': CH})
d = r.get_json()
check(r.status_code == 200 and d['success'], 'сохранение большого id ок')
check(d['channel_id'] == CH and isinstance(d['channel_id'], str),
      'POST-ответ: id вернулся строкой без потери цифр')

r = client.get('/api/channel-routes').get_json()
row = next(x for x in r['routes'] if x['key'] == 'proof_channel')
check(row['channel_id'] == CH and isinstance(row['channel_id'], str),
      'GET: канал вернулся строкой посимвольно (не сломан double)')
raw = json.load(open('data/channel_routes.json', encoding='utf-8'))
check(int(raw['777']['proof_channel']) == int(CH),
      'в файле бота — честный int (бот читает как раньше)')

r = client.post('/api/channel-routes/proof_channel', json={'channel_id': '0'})
check(r.get_json()['success'], 'очистка маршрута («0» = авто) ок')
row = next(x for x in client.get('/api/channel-routes').get_json()['routes']
           if x['key'] == 'proof_channel')
check(not row['channel_id'], 'после очистки channel_id пуст (авто)')
if os.path.exists('data/channel_routes.json'):
    os.remove('data/channel_routes.json')

print('== 3. Клиентские контракты: id без Number/parseInt ==')
tpl = open(os.path.join(ROOT, 'web', 'templates', 'channel_settings.html'),
           encoding='utf-8').read()
check('Number(cid)' not in tpl, 'chsSave: нет Number(cid) — id строкой')
check("String(cid)" in tpl and "cid === '0' ? null" in tpl,
      'chsSave: строкой, «0» → null (авто)')
for name in ('mod_settings.html', 'pagerduty.html'):
    src = open(os.path.join(ROOT, 'web', 'templates', name),
               encoding='utf-8').read()
    bad = re.findall(r'parseInt\([^)]*(?:Role|Channel|channel)[^)]*\)', src)
    check(not bad, f'{name}: нет parseInt по id ролей/каналов {bad}')
src = open(os.path.join(ROOT, 'web', 'templates', 'antifake.html'),
           encoding='utf-8').read()
check('Number(uid)' not in src and 'user_id: String(uid)' in src,
      'antifake: user_id строкой при очистке страйков')

print('== 4. MAIN_GUILD_ID: нормализация цифр ==')
import web.app as _wa  # noqa: E402
for raw, want in (('12345 ', '12345'), ('"12345"', '12345'),
                  ('12345 # мой сервер', '12345'), ('  12345,\t', '12345'),
                  ('', ''), (None, '')):
    got = _wa._norm_guild_id(raw)
    check(got == want, f'_norm_guild_id({raw!r}) → {got!r}')
check(re.fullmatch(r'\d*', _wa.MAIN_GUILD_ID or '') is not None,
      'загруженный MAIN_GUILD_ID — только цифры')

print('== 5. Гейт с грязным .env: регрессия 404 закрыта ==')
code = r'''
import os, sys, tempfile
_TMP = tempfile.mkdtemp(prefix="hakumo_gate_")
os.chdir(_TMP)
sys.path.insert(0, %r)
os.makedirs("data", exist_ok=True)
os.environ["DB_PATH"] = os.path.join(_TMP, "data", "bot.db")
os.environ["PANEL_USER"] = "a"
os.environ["PANEL_PASSWORD"] = "x"
# Грязное значение, как бывает у хозяев в .env
os.environ["MAIN_GUILD_ID"] = " 777 # мой сервер"
import web.app as m
c = m.app.test_client()
with c.session_transaction() as s:
    s["logged_in"] = True
    s["username"] = "a"
    s["role"] = "owner"
r = c.get("/api/guild/777/staff-limits")
print("MAIN=%%r code=%%s" %% (m.MAIN_GUILD_ID, r.status_code))
assert m.MAIN_GUILD_ID == "777", m.MAIN_GUILD_ID
assert r.status_code == 200, r.get_json()
print("GATE_OK")
''' % ROOT
out = subprocess.run([sys.executable, '-c', code], capture_output=True,
                     text=True, timeout=300)
check('GATE_OK' in out.stdout,
      'MAIN_GUILD_ID с пробелом/комментарием: API жив (200, не 404)')
if out.returncode != 0:
    print(out.stdout[-400:], out.stderr[-400:])

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
