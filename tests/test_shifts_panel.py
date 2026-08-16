# -*- coding: utf-8 -*-
"""Панель «Смены персонала» (идеи #126-130).

Неделя, «кто сейчас/следующая» (active/next кога, пояс +3), назначение
1:1 с try_add_shift (тексты), снятие с чисткой меток, настройки (пояс
-12..14, канал-None), нагрузка, CSV, права, шаблон, меню.

Запуск: python3 tests/test_shifts_panel.py
"""
import importlib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone

_TMP = tempfile.mkdtemp(prefix='aether_shifts_test_')
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


# 2026-08-16 12:00 UTC = воскресенье, локаль UTC+3 → 15:00 того же дня
NOW = datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc)
assert NOW.weekday() == 6, 'якорь: воскресенье'

SHIFTS = {
    # локаль 12:00–18:00 = UTC 09:00–15:00 — активна в NOW (осталось 3 ч)
    'aa01': {'user_id': 111, 'weekday': 6, 'start': '12:00', 'end': '18:00',
             'added_by': 'setup', 'added_at': '2026-08-01T10:00:00+00:00'},
    # локаль 19:00–21:00 = UTC 16:00–18:00 — следующая (через 4 ч)
    'bb02': {'user_id': 222, 'weekday': 6, 'start': '19:00', 'end': '21:00',
             'added_by': 'setup', 'added_at': '2026-08-01T10:00:00+00:00'},
    # понедельник через полночь: 4 часа
    'cc03': {'user_id': 111, 'weekday': 0, 'start': '22:00', 'end': '02:00',
             'added_by': 'setup', 'added_at': '2026-08-01T10:00:00+00:00'},
}
NAMES = {'111': 'Анна', '222': 'Борис'}
json.dump({'777': [{'user_id': k, 'user_name': v} for k, v in NAMES.items()]},
          open('data/audit_log.json', 'w', encoding='utf-8'))

from db import GuildData  # noqa: E402
from web.routes import shifts_panel as SP  # noqa: E402

EMOJI_RE = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')

db = GuildData('staff_shifts')
db.set('777', 'shifts', {k: dict(v) for k, v in SHIFTS.items()})
db.set('777', 'settings', {'channel_id': None, 'tz_offset': 3})
db.set('777', '_marks', {'cc03': {'start': '2026-08-10T19:00:00+00:00'}})

print('== 1. Неделя и сводка ==')
week = SP.week_rows(SHIFTS, NAMES)
sun = week[6]
check([s['id'] for s in sun['slots']] == ['aa01', 'bb02'], 'вск: сорт по времени')
check(week[0]['slots'][0]['minutes'] == 240, 'смена через полночь — 4 часа')
check(sun['slots'][0]['name'] == 'Анна' and sun['slots'][0]['wd_label'] == 'вс',
      'имена и подписи дней')
mon = SP.week_rows({}, {})[0]
check(mon['slots'] == [], 'пустое расписание — пустые дни')
stats = SP.overview_stats(SHIFTS, 3, now=NOW)
check(stats['shifts_total'] == 3 and stats['minutes_week'] == 720
      and stats['people'] == 2, '6+2+4 = 12 часов на двоих в неделю')

print('== 2. Кто дежурит ==')
duty = SP.duty_now(SHIFTS, 3, NAMES, now=NOW)
check(duty['active']['user_id'] == '111' and duty['active']['left_s'] == 10800,
      'Анна на смене, осталось 3 часа')
check(duty['next']['user_id'] == '222' and duty['next']['wait_s'] == 14400,
      'следующий Борис через 4 часа')
night = NOW.replace(hour=20)  # локаль 23:00 — тишина
duty2 = SP.duty_now(SHIFTS, 3, NAMES, now=night)
check(duty2['active'] is None and duty2['next']['user_id'] == '111',
      'в 23:00 пусто, следующая — Анна в пн 22:00')
tz_m3 = SP.duty_now(SHIFTS, -3, NAMES, now=NOW)  # Локаль 09:00 — до смен
check(tz_m3['active'] is None and tz_m3['next']['user_id'] == '111',
      'другой пояс — другая картина, та же математика')

print('== 3. Назначить и снять ==')
ok, err, _ = SP.add_shift('777', 'qq', 'пн', '10:00-12:00', 'тест')
check(not ok and err == 'Некорректный ID пользователя', 'битый ID — текст мод-контроля')
ok, err, _ = SP.add_shift('777', '333', 'февраль', '10:00-12:00', 'тест')
check(not ok and err.startswith('Не понял день «февраль»'), 'день — текст кога')
ok, err, _ = SP.add_shift('777', '333', 'пн', '25:00-26:00', 'тест')
check(not ok and err.startswith('Формат времени:'), 'время — текст кога')
ok, err, _ = SP.add_shift('777', '222', 'вс', '19:00-21:00', 'тест')
check(not ok and err == 'Такая смена уже назначена (смотри `/дежурства`).', 'дубль — текст кога')
ok, err, payload = SP.add_shift('777', '<@333>', 'вт', '08:00-10:00', 'тест')
check(ok and payload['message'].startswith('Смена добавлена: вт 08:00–10:00 (id '),
      'назначено по упоминанию')
new_id = payload['id']
check(len(new_id) == 4 and db.get('777', 'shifts', {})[new_id]['user_id'] == 333,
      'запись легла в общее хранилище')
ok, err, _ = SP.remove_shift('777', 'zz99')
check(not ok and err == ('Смена `zz99` не найдена. Список id — в `/дежурства` '
                         '(таблица недели).'), 'нет такой — текст кога')
ok, err, payload = SP.remove_shift('777', 'cc03')
check(ok and payload['message'] == 'Смена снята: пн 22:00–02:00 (id cc03).',
      'сняли — сообщение команды')
check(db.get('777', '_marks', {}) == {}, 'и её метки напоминаний вычистили')
ok, err, payload = SP.remove_shift('777', new_id)
check(ok and len(db.get('777', 'shifts', {})) == 2, 'и свежую — остались две исходные')
db.set('777', 'shifts', {k: dict(v) for k, v in SHIFTS.items()})  # фикстура целиком

print('== 4. Настройки ==')
ok, err, _ = SP.update_settings('777', tz_offset='15')
check(not ok and err == 'Пояс: от -12 до +14 (МСК = 3).', 'пояс 15 — текст кога')
ok, err, _ = SP.update_settings('777', tz_offset='мск')
check(not ok and err == 'Пояс: от -12 до +14 (МСК = 3).', 'пояс буквами — туда же')
ok, err, stt = SP.update_settings('777', tz_offset='5')
check(ok and stt['tz_offset'] == 5, '+5 встал')
ok, err, stt = SP.update_settings('777', channel_id='')
check(ok and stt['channel_id'] is None, 'пустой канал — молчаливый режим')
ok, err, stt = SP.update_settings('777', channel_id='555')
check(ok and stt['channel_id'] == 555, 'канал числом')
ok, err, _ = SP.update_settings('777', channel_id='ку')
check(not ok and err == 'Некорректный ID канала', 'канал буквами — нет')
SP.update_settings('777', tz_offset='3')  # вернули исходное

print('== 5. Нагрузка и CSV ==')
wl = SP.workload(SHIFTS, NAMES)
check([w['user_id'] for w in wl] == ['111', '222'], 'по убыванию часов')
check(wl[0]['hours'] == 10.0 and wl[0]['shifts'] == 2, 'Анна — 10 часов на двух сменах')
rows = SP.shifts_csv_rows(SHIFTS, NAMES)
check(len(rows) == 3 and rows[0][:4] == ('пн', '22:00', '02:00', '111'), 'строки по дням')
check(rows[1][5] == '6,0' and rows[2][5] == '2,0', 'часы с запятой')

print('== 6. API и права ==')
appmod = importlib.import_module('web.app')
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()


def login(role='owner'):
    with client.session_transaction() as sess:
        sess.clear()
        sess['logged_in'] = True
        sess['username'] = 'admin'
        sess['role'] = role


OV = '/api/guild/777/shiftboard/overview'
check(client.get('/staff-shifts').status_code in (302, 401, 403), 'гостю страница закрыта')
check(client.get(OV).status_code in (302, 401, 403), 'гостю API закрыто')
login('uye')
check(client.get(OV).status_code == 403, 'uye нельзя')
login('mod')
page = client.get('/staff-shifts')
check(page.status_code == 200 and 'Смены персонала' in page.get_data(as_text=True),
      'mod открывает страницу')
ov = client.get(OV).get_json()
check(ov['success'] and ov['can_edit'] is False, 'mod без права назначений')
check(ov['stats']['shifts_total'] == 3 and len(ov['week']) == 7, 'обзор собрался')
check('<@111>' in ov['week_table_text'] and '12:00–18:00' in ov['week_table_text'],
      'сырой текст команды приложен')
check(set(ov['duty'].keys()) == {'active', 'next', 'tz_offset'}
      and (ov['duty']['active'] is None
           or ov['duty']['active']['user_id'] in ('111', '222')),
      '«кто» считается от живых часов тем же кодом')
r = client.post('/api/guild/777/shiftboard/add',
                json={'user_id': '333', 'weekday': 'ср', 'time': '09:00-11:00'})
check(r.status_code == 403, 'mod не назначает')
login('admin')
r = client.post('/api/guild/777/shiftboard/add',
                json={'user_id': '333', 'weekday': 'ку', 'time': '09:00-11:00'})
check(r.status_code == 400 and r.get_json()['error'].startswith('Не понял день'), 'день — 400')
r = client.post('/api/guild/777/shiftboard/add',
                json={'user_id': '333', 'weekday': 'ср', 'time': '09:00-11:00'})
d = r.get_json()
check(r.status_code == 200 and d['success'] and d['row']['name'] == '', 'назначил admin')
r = client.post('/api/guild/777/shiftboard/remove', json={'shift_id': d['id']})
check(r.get_json()['success'], 'и снял назад')
r = client.post('/api/guild/777/shiftboard/settings',
                json={'tz_offset': '77'})
check(r.status_code == 400, 'пояс через API — 400')
r = client.post('/api/guild/777/shiftboard/settings',
                json={'channel_id': '777111', 'tz_offset': '3'})
check(r.get_json()['settings']['channel_id'] == 777111, 'настройки сохранились')

csv_r = client.get('/api/guild/777/shiftboard/export.csv')
body = csv_r.get_data(as_text=True)
check(csv_r.status_code == 200
      and 'staff_shifts_777.csv' in csv_r.headers.get('Content-Disposition', ''), 'имя файла')
check(body.startswith('\ufeffday;start;end'), 'BOM + шапка')
check(len(body.strip().split('\n')) == 4, 'шапка + 3 смены')
check('Анна' in body, 'имена из аудита в выгрузке')
login('uye')
check(client.get('/api/guild/777/shiftboard/export.csv').status_code == 403,
      'uye не выгружает')

print('== 7. Шаблон, меню, регистрация ==')
tpl = open(os.path.join(ROOT, 'web/templates/staff_shifts.html'), encoding='utf-8').read()
check(not EMOJI_RE.search(tpl), 'в шаблоне нет эмодзи')
check('[data-theme="light"]' in tpl, 'светлая тема учтена')
for fid in ('ssWeek', 'ssDuty', 'ssAdd', 'ssCsv', 'ssRaw', 'ssChan', 'ssTz', 'ssWork'):
    check(('id="' + fid + '"') in tpl, f'блок {fid} на месте')
check("'/overview'" in tpl and "'/add'" in tpl and "'/remove'" in tpl
      and "'/settings'" in tpl and '/export.csv' in tpl, 'API-пути в шаблоне')
check('localhost' not in tpl and '127.0.0.1' not in tpl, 'без локальных адресов')
import services.panel_menu as PM
com_pages = [pg['path'] for g in PM.MENU if g['key'] == 'community' for pg in g['pages']]
check('/staff-shifts' in com_pages, 'пункт меню «Смены персонала» в «Сообществе»')
check(PM.PAGE_COGS.get('/staff-shifts') == ('staff_shifts',), 'staff_shifts-ког привязан')
ext = open(os.path.join(ROOT, 'web/routes_extra.py'), encoding='utf-8').read()
check(ext.count('shifts_panel') >= 2, 'модуль зарегистрирован в routes_extra')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
