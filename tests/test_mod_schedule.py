# -*- coding: utf-8 -*-
"""Панель «Расписание наказаний» (календарь истечений + отложенные действия).

Чистые функции принимают общие файлы бота (temp_*.json), API работает
только с активным сервером, создание/отмена пишут в тот самый файл,
который перечитывает планировщик cogs/temp_moderation.

Запуск: python3 tests/test_mod_schedule.py
"""
import importlib
import json
import os
import shutil
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix='hakumo_msched_test_')
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


from web.routes import mod_schedule as MS  # noqa: E402

print('== 1. чистые функции ==')
NOW = time.time()
check(MS._validate_new({'action': 'mute', 'user_id': '42',
                        'run_at': NOW + 3600, 'duration': 30})[0]['duration'] == 1800,
      'длительность приходит секундами')
_, err = MS._validate_new({'action': 'explode', 'user_id': '42',
                           'run_at': NOW + 3600, 'duration': 30})
check(err and 'mute' in err, 'незнакомое действие отклонено')
_, err = MS._validate_new({'action': 'mute', 'user_id': 'abc',
                           'run_at': NOW + 3600, 'duration': 30})
check(err and 'цифр' in err, 'ID не из цифр — понятная ошибка')
_, err = MS._validate_new({'action': 'mute', 'user_id': '42',
                           'run_at': NOW - 5, 'duration': 30})
check(err and 'будущем' in err, 'время в прошлом не пройдёт')
_, err = MS._validate_new({'action': 'mute', 'user_id': '42',
                           'run_at': NOW + 70 * 86400, 'duration': 30})
check(err and '60 дней' in err, 'за два месяца не отложить')
_, err = MS._validate_new({'action': 'mute', 'user_id': '42',
                           'run_at': NOW + 3600, 'duration': 0})
check(err and 'Длительность' in err, 'нулевая длительность не пройдёт')

# файлы бота → истечения
MS._write_json('data/temp_mutes.json', {'777': {
    '42': {'until': NOW + 7200, 'reason': 'флуд', 'mod_id': '7'},
    '43': {'until': NOW - 10, 'reason': 'старое', 'mod_id': '7'},
}, '555': {'50': {'until': NOW + 7200, 'reason': '', 'mod_id': '1'}}})
MS._write_json('data/temp_bans.json', {'777': {
    '44': {'until': NOW + 86400, 'reason': 'токсик', 'mod_id': '7'}}})
exp = MS._guild_expirations('777', {'42': 'Флудер'})
check(len(exp) == 2 and exp[0]['user_name'] == 'Флудер',
      'истечения сервера: живые + имена из аудита')
check(all(e['user_id'] != '50' for e in exp), 'чужой сервер не подмешан')
check(exp[0]['until'] <= exp[1]['until'], 'истечения по возрастанию времени')

# расписание: отбор сервера и чистка старых хвостов
MS._write_json('data/temp_scheduled.json', [
    {'id': 'a1', 'guild_id': '777', 'user_id': '42', 'action': 'mute',
     'run_at': NOW + 3600, 'duration': 1800, 'reason': 'ночной', 'status': 'pending'},
    {'id': 'a2', 'guild_id': '555', 'user_id': '50', 'action': 'ban',
     'run_at': NOW + 3600, 'duration': 1800, 'reason': '', 'status': 'pending'},
    {'id': 'old', 'guild_id': '777', 'user_id': '1', 'action': 'kick',
     'run_at': NOW - 10 * 86400, 'duration': 60, 'reason': '', 'status': 'executed'},
])
sch = MS._guild_scheduled('777', {})
check([s['id'] for s in sch] == ['a1'], 'отложенные только своего сервера')
raw = MS._read_json('data/temp_scheduled.json', [])
check(all(e['id'] != 'old' for e in raw), 'старые исполненные вычищаются из файла')
py = MS.schedule_payload('777', {'42': 'Флудер'})
check(py['stats']['pending'] == 1 and py['stats']['active'] == 2
      and py['stats']['nearest'] is not None,
      'сводка: активные/отложенные/ближайшее')

print('== 2. веб ==')
appmod = importlib.import_module('web.app')
client = appmod.app.test_client()


def login(role='owner'):
    with client.session_transaction() as sess:
        sess.clear()
        sess['logged_in'] = True
        sess['username'] = 'admin'
        sess['role'] = role


check(client.get('/mod-schedule').status_code in (302, 401, 403),
      'гостю страница закрыта')
login('mod')   # создание и отмена — уровень модератора, как /schedule в боте
r = client.get('/mod-schedule')
check(r.status_code == 200 and 'Календарь' not in '' and b'msCal' in r.data,
      'страница открывается модератору')
html = r.get_data(as_text=True)
check('id="msCal"' in html and 'id="msSchedList"' in html
      and 'data-day' in html or 'ms-day' in html,
      'календарная сетка и списки в шаблоне')
check('id="msAction"' in html and 'id="msRunAt"' in html,
      'форма отложенного действия в шаблоне')
check("'/create'" in html and 'data-cancel' in html,
      'создание и отмена заведены в js')

API = '/api/guild/777/mod-schedule'
r = client.get(API).get_json()
check(r.get('success') and r['stats']['active'] == 2
      and r['stats']['pending'] == 1, 'API: общая сводка')
check(any(e['user_id'] == '42' for e in r['expirations']),
      'API: список истечений')

# создать из панели — файл смотрится ботом: проверяем формат записи
r = client.post(API + '/create', json={
    'action': 'Ban', 'user_id': '555000', 'run_at': int(NOW + 7200),
    'duration': 45, 'reason': 'плановый', 'user_name': 'Цель'})
d = r.get_json()
check(d.get('success'), 'создание отложенного действия из панели')
raw = MS._read_json('data/temp_scheduled.json', [])
mine = [e for e in raw if e.get('user_id') == '555000']
check(len(mine) == 1 and mine[0]['status'] == 'pending'
      and mine[0]['duration'] == 2700
      and all(k in mine[0] for k in ('id', 'action', 'guild_id', 'user_id',
                                     'mod_id', 'run_at', 'duration', 'reason')),
      'запись ровно в формате планировщика бота')
check(mine[0]['action'] == 'ban', 'действие нормализовано к нижнему регистру')
ent_id = mine[0]['id']
r = client.get(API).get_json()
check(any(s['id'] == ent_id and s['user_name'] == 'Цель'
          for s in r['scheduled']), 'созданное видно в сводке')

# ошибки формы
r = client.post(API + '/create', json={'action': 'mute', 'user_id': 'xx',
                                       'run_at': NOW + 100, 'duration': 5})
check(r.status_code == 400, 'битая форма — 400 из валидатора')
r = client.post(API + '/cancel', json={'id': ent_id})
check(r.get_json().get('success'), 'отмена запланированного')
raw = MS._read_json('data/temp_scheduled.json', [])
check([e for e in raw if e['id'] == ent_id][0]['status'] == 'cancelled',
      'отмена записана статусом (бот её пропустит)')
r = client.post(API + '/cancel', json={'id': ent_id})
check(r.status_code == 404, 'повторная отмена — честный 404')

# изоляция по активному серверу: чужой gid в пути всё равно ведёт на главный
r = client.get('/api/guild/555/mod-schedule').get_json()
check(r.get('success') and all(s['id'] != 'a2' for s in r['scheduled']),
      'изоляция: /555 отвечает данными главного сервера')

print('== 3. меню ==')
from services import panel_menu as PM  # noqa: E402
paths = [i['path'] for g in PM.MENU for i in g.get('pages', [])]
check('/mod-schedule' in paths, 'пункт меню «Расписание» зарегистрирован')
check(PM.PAGE_COGS.get('/mod-schedule') == ('temp_moderation',),
      'страница привязана к когу временных наказаний')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
