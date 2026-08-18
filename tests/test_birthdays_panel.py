# -*- coding: utf-8 -*-
"""Панель «Дни рождения» (идеи #56-60).

Календарь 1:1 с алгоритмом /birthdays кога (num=MM*100+DD, перенос +1200),
валидация даты 1:1 с /birthday, форма записи формата кога, дефолты
настроек 1:1 с get_settings, превью эмбеда, CSV с BOM, права mod+/admin+,
шаблон без эмодзи, меню и PAGE_COGS.

Запуск: python3 tests/test_birthdays_panel.py
"""
import importlib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timedelta

_TMP = tempfile.mkdtemp(prefix='aether_birthdays_test_')
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


from web.routes import birthdays_panel as BP  # noqa: E402

EMOJI_RE = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')
NOW = datetime(2026, 8, 16, 12, 0)  # today_num = 816


def seed_birthdays():
    return {
        '1': {'date': '08-16', 'name': 'Аня', 'year': 2000, 'celebrated': '2026'},
        '2': {'date': '08-20', 'name': 'Боря'},
        '6': {'date': '08-20', 'name': 'Анна', 'year': 1998},
        '3': {'date': '12-31', 'name': 'Вик;а', 'celebrated': '2025'},
        '4': {'date': '01-10', 'name': 'Гриша', 'year': 1995},
        '5': {'date': '08-15', 'name': 'Дима', 'year': 2001},
        '7': {'date': 'плохая', 'name': 'Слом'},
        '8': 'не словарь',
    }


print('== 1. Календарь 1:1 с /birthdays кога ==')
entries = BP.schedule(seed_birthdays(), now=NOW)
check([e['user_id'] for e in entries] == ['1', '6', '2', '3', '4', '5'],
      'порядок: сегодня, ничья 08-20 (Анна раньше Бори), потом по удалённости')
check(len(entries) == 6, 'битая дата и не-словарь пропущены (6 из 8)')
one = entries[0]
check(one['today'] is True and one['days_until'] == 0, 'сегодняшняя запись помечена')
check(one['age'] == 26 and one['celebrated_this_year'] is True,
      'возраст 2026-2000=26, поздравлена в этом году')
check(entries[1]['user_id'] == '6' and entries[1]['age'] == 28,
      'у Анны возраст 28, общий с Борей день')
check(entries[2]['year'] is None and entries[2]['age'] is None,
      'у Бори года нет — возраст не считаем')
check(entries[3]['days_until'] == 415, '12-31: 1231-816=415')
check(entries[4]['days_until'] == 494, '01-10: 110-816+1200=494 (перенос года кога)')
check(entries[5]['days_until'] == 1199 and entries[5]['today'] is False,
      'вчерашняя 08-15 ушла в хвост: 815-816+1200=1199')
check(entries[2]['celebrated'] == '' and entries[2]['celebrated_this_year'] is False,
      'не поздравлен — пустая строка года')
weird = BP.schedule({'9': {'date': '13-40', 'name': 'Странный'},
                     '10': {'date': '8-5', 'name': 'Без нулей'},
                     '11': {'date': None}}, now=NOW)
check([e['user_id'] for e in weird] == ['9', '10'],
      'парсящиеся кривые даты ког показывает — панель тоже; None пропущен')
check(weird[0]['days_until'] == 524, '13-40: 1340-816=524 — как у кога')
check(weird[1]['days_until'] == 1189, '8-5: 805-816+1200=1189 — как у кога')
check(BP.schedule(None, now=NOW) == [] and BP.schedule({}, now=NOW) == [],
      'пустые хранилища — пустой календарь')

print('== 2. Сводка календаря ==')
stats = BP.calendar_stats(entries)
check(stats['total'] == 6, 'всего записей')
check(stats['today'] == 1, 'сегодня празднует одна')
check(stats['week'] == 2, 'на неделе (1-7 дней) двое: Анна и Боря')
check(stats['celebrated_year'] == 1, 'в этом году поздравлен один')
check(stats['next']['user_id'] == '1', 'ближайший — сегодняшний')
check(BP.calendar_stats([])['next'] is None, 'пусто — без ближайшего')

print('== 3. Валидация даты 1:1 с /birthday ==')
ok, err = BP.validate_entry(16, 8, None, now=NOW)
check(ok == {'day': 16, 'month': 8, 'year': None} and err == '', 'дата без года')
ok, err = BP.validate_entry('05', ' 3 ', '2000', now=NOW)
check(ok == {'day': 5, 'month': 3, 'year': 2000}, 'строки парсятся, пробелы чистятся')
check(BP.validate_entry(0, 8, None, now=NOW)[1] == 'Неверная дата!', 'день 0')
check(BP.validate_entry(32, 1, None, now=NOW)[1] == 'Неверная дата!', 'день 32')
check(BP.validate_entry(10, 13, None, now=NOW)[1] == 'Неверная дата!', 'месяц 13')
check(BP.validate_entry('abc', 5, None, now=NOW)[1] == 'Неверная дата!', 'день буквами')
check(BP.validate_entry(True, 5, None, now=NOW)[1] == 'Неверная дата!', 'bool не день')
check(BP.validate_entry(5.5, 5, None, now=NOW)[1] == 'Неверная дата!',
      'дробный день отброшен')
check(BP.validate_entry(31, 12, None, now=NOW)[0]['day'] == 31, 'граница 31/12 ок')
check(BP.validate_entry(29, 2, None, now=NOW)[0] is not None,
      '29 февраля — как у бота: ког не строит date, валиден')
check(BP.validate_entry(10, 5, '1800', now=NOW)[1] == 'Год — от 1900 до 2026',
      'слишком ранний год')
check(BP.validate_entry(10, 5, 2027, now=NOW)[1] == 'Год — от 1900 до 2026',
      'год из будущего')
check(BP.validate_entry(10, 5, 2026, now=NOW)[0]['year'] == 2026, 'текущий год ок')
check(BP.validate_entry(10, 5, 'abc', now=NOW)[1] == 'Год — от 1900 до 2026',
      'год буквами')
check(BP.validate_entry(10, 5, True, now=NOW)[1] == 'Год — от 1900 до 2026',
      'bool не год')
check(BP.validate_entry(10, 5, 0, now=NOW)[1] == 'Год — от 1900 до 2026',
      'нулевой год отброшен')
check(BP.validate_entry(10, 5, '', now=NOW)[0]['year'] is None,
      'пустая строка года — «без года»')

print('== 4. Формат записи кога ==')
entry = BP.build_entry({'day': 5, 'month': 3, 'year': 2000}, 'Тест')
check(entry == {'date': '03-05', 'name': 'Тест', 'year': 2000},
      'date MM-DD, год числом — как у set_birthday')
entry = BP.build_entry({'day': 16, 'month': 8, 'year': None}, 'Аня')
check(entry == {'date': '08-16', 'name': 'Аня'} and 'year' not in entry,
      'без года ключа year нет (бот: entry["year"] только если задан)')

print('== 5. Настройки: дефолты 1:1 с когом ==')
cog_src = open(os.path.join(ROOT, 'cogs', 'birthday.py'), encoding='utf-8').read()
check("'message':'" + BP.DEFAULT_MESSAGE + "'" in cog_src,
      'дефолтное сообщение побайтово как в get_settings кога')
pub = BP.public_settings({})
check(pub['channel_id'] is None and pub['role_id'] is None
      and pub['message'] == BP.DEFAULT_MESSAGE,
      'пустое хранилище — дефолты кога')
check(pub['gift_coins'] == 0 and pub['channel_set'] is False
      and pub['role_set'] is False, 'подарок 0, канал и роль не заданы')
pub = BP.public_settings({'channel_id': '42', 'gift_coins': 300, 'zapas': 'храни'})
check(pub['gift_coins'] == 300 and pub['channel_set'] is True
      and pub['zapas'] == 'храни', 'файл перекрывает дефолты, чужие ключи целы')
check(BP.public_settings({'gift_coins': '150'})['gift_coins'] == 150,
      'строковый подарок парсится')
check(BP.public_settings({'gift_coins': 'много'})['gift_coins'] == 0,
      'кривой подарок — 0')
check(BP.public_settings({'gift_coins': True})['gift_coins'] == 0,
      'bool-подарок — 0')

print('== 6. Превью поздравления ==')
view = BP.greeting_view({}, now=NOW)
check(view['ready'] is False and view['role_set'] is False
      and view['gift_coins'] == 0, 'без настроек поздравление не готово')
check(view['line'] == 'У @Мария сегодня день рождения (20 лет)!',
      'строка эмбеда с возрастом образца')
check(view['fields'][0] == {'name': 'Дата', 'value': '08/16'}
      and view['fields'][1] == {'name': 'Возраст', 'value': '20'},
      'поля Дата и Возраст — как в check_birthdays')
check('@Мария' in view['template'] and '{user}' not in view['template'],
      'шаблон подставил {user}')
check(view['sample'] is True, 'флаг образца')
view = BP.greeting_view({'channel_id': '5', 'role_id': '6', 'gift_coins': 150,
                         'message': 'Именинник: {user}! {неизвестно}'}, now=NOW)
check(view['ready'] is True and view['role_set'] is True
      and view['gift_coins'] == 150, 'настроенное поздравление готово')
check(view['template'] == 'Именинник: @Мария! {неизвестно}',
      'неизвестный плейсхолдер остаётся литералом (SafeDict)')

print('== 7. API: права и потоки ==')
# API-раздел идёт против настоящего now панели — даты делаем относительными
# (чистая математика календаря выше в секции 1 закреплена фиксированным NOW).
real_now = datetime.now()


def rel(days):
    return (real_now + timedelta(days=days)).strftime('%m-%d')


api_birthdays = {
    '1': {'date': rel(0), 'name': 'Аня', 'year': 2000,
          'celebrated': str(real_now.year)},
    '2': {'date': rel(4), 'name': 'Боря'},
    '6': {'date': rel(4), 'name': 'Анна', 'year': 1998},
    '3': {'date': rel(130), 'name': 'Вик;а',
          'celebrated': str(real_now.year - 1)},
    '4': {'date': rel(200), 'name': 'Гриша', 'year': 1995},
    '5': {'date': rel(-1), 'name': 'Дима', 'year': 2001},
    '7': {'date': 'плохая', 'name': 'Слом'},
    '8': 'не словарь',
}
with open('data/birthdays_777.json', 'w', encoding='utf-8') as fh:
    json.dump(api_birthdays, fh)
with open('data/birthday_settings_777.json', 'w', encoding='utf-8') as fh:
    json.dump({'channel_id': '555', 'gift_coins': 300,
               'message': 'Именинник: {user}!', 'zapas': 'храни меня'}, fh)
with open('data/audit_log.json', 'w', encoding='utf-8') as fh:
    json.dump({'777': [
        {'category': 'mod', 'action': 'Мут', 'user_id': '2', 'user_name': 'Борислав',
         'timestamp': NOW.isoformat()},
    ]}, fh)

appmod = importlib.import_module('web.app')
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()


def login(role='owner'):
    with client.session_transaction() as s:
        s.clear()
        s['logged_in'] = True
        s['username'] = 'admin'
        s['role'] = role


OV = '/api/guild/777/birthdays/overview'
check(client.get('/birthdays').status_code in (302, 401, 403),
      'гостю страница закрыта')
check(client.get(OV).status_code in (302, 401, 403), 'гостю снимок закрыт')
login('uye')
check(client.get(OV).status_code == 403, 'uye нельзя')
login('mod')
page = client.get('/birthdays')
check(page.status_code == 200 and 'Дни рождения' in page.get_data(as_text=True),
      'mod открывает страницу')
check("var GID = '777'" in page.get_data(as_text=True), 'активный сервер в странице')
ov = client.get(OV).get_json()
check(ov['success'] and ov['can_edit'] is False, 'mod читает без права правки')
check(ov['stats']['total'] == 6 and ov['entries'][0]['user_id'] == '1',
      'календарь отдан, сегодняшний первый')
check(ov['entries'][0]['today'] is True, 'сегодняшний помечен и в API')
check(ov['entries'][2]['name'] == 'Борислав', 'имя из аудит-журнала перекрыло файл')
check(ov['settings']['gift_coins'] == 300 and ov['settings']['channel_set'] is True,
      'настройки из файла кога')

check(client.post('/api/guild/777/birthdays/set',
                  json={'user_id': '9', 'day': 1, 'month': 1}).status_code == 403,
      'mod не записывает даты')
check(client.post('/api/guild/777/birthdays/delete',
                  json={'user_id': '9'}).status_code == 403, 'mod не удаляет')
check(client.post('/api/guild/777/birthdays/settings',
                  json={'gift_coins': 5}).status_code == 403,
      'mod не трогает настройки')
pv = client.post('/api/guild/777/birthdays/preview', json={})
check(pv.status_code == 200 and pv.get_json()['preview']['gift_coins'] == 300,
      'mod превьюит — это чтение')
check(pv.get_json()['preview']['template'] == 'Именинник: @Мария!',
      'превью рисует сохранённый шаблон')

login('admin')
r = client.post('/api/guild/777/birthdays/set',
                json={'user_id': '<@42>', 'day': '5', 'month': '3', 'year': '2000'})
d = r.get_json()
check(r.status_code == 200
      and d['entry'] == {'date': '03-05', 'name': '42', 'year': 2000},
      'admin записал по упоминанию; имя — ID раз в аудите его нет')
disk = json.load(open('data/birthdays_777.json', encoding='utf-8'))
check(disk['42'] == d['entry'], 'файл кога дополнен той же записью')
r = client.post('/api/guild/777/birthdays/set',
                json={'user_id': '42', 'day': 6, 'month': 4})
check(r.get_json()['entry'] == {'date': '04-06', 'name': '42'},
      'перезапись заменяет дату и сбрасывает год — как /birthday')
r = client.post('/api/guild/777/birthdays/set',
                json={'user_id': '9', 'day': 32, 'month': 1})
check(r.status_code == 400 and r.get_json()['error'] == 'Неверная дата!',
      'день 32 — 400 словами бота')
r = client.post('/api/guild/777/birthdays/set',
                json={'user_id': '9', 'day': 1, 'month': 0})
check(r.status_code == 400 and r.get_json()['error'] == 'Неверная дата!',
      'месяц 0 — 400')
r = client.post('/api/guild/777/birthdays/set',
                json={'user_id': '9', 'day': 1, 'month': 1, 'year': 1700})
check(r.status_code == 400
      and r.get_json()['error'].startswith('Год — от 1900 до '), 'год 1700 — 400')
r = client.post('/api/guild/777/birthdays/set',
                json={'user_id': 'куку', 'day': 1, 'month': 1})
check(r.status_code == 400
      and r.get_json()['error'] == 'Некорректный ID пользователя',
      'битый ID — слова мод-контроля')

r = client.post('/api/guild/777/birthdays/delete', json={'user_id': '<@42>'})
d = r.get_json()
check(r.status_code == 200 and d['removed']['date'] == '04-06',
      'admin удалил по упоминанию, удалённое возвращено')
disk = json.load(open('data/birthdays_777.json', encoding='utf-8'))
check('42' not in disk, 'запись убрана из файла')
r = client.post('/api/guild/777/birthdays/delete', json={'user_id': '42'})
check(r.status_code == 404
      and r.get_json()['error'] == 'Запись о дне рождения не найдена.',
      'повторное удаление — 404 словами бота')

r = client.post('/api/guild/777/birthdays/settings',
                json={'channel_id': '', 'role_id': '777', 'gift_coins': '50',
                      'message': 'Поздравляем {user}!'})
d = r.get_json()
check(r.status_code == 200 and d['settings']['channel_id'] is None
      and d['settings']['channel_set'] is False, 'пустой канал — None')
check(d['settings']['role_id'] == '777' and d['settings']['role_set'] is True
      and d['settings']['gift_coins'] == 50, 'роль и подарок сохранены')
stored = json.load(open('data/birthday_settings_777.json', encoding='utf-8'))
check(stored['zapas'] == 'храни меня' and stored['gift_coins'] == 50
      and isinstance(stored['gift_coins'], int),
      'чужой ключ файла цел, подарок — число (формат кога)')
r = client.post('/api/guild/777/birthdays/settings', json={'channel_id': 'abc'})
check(r.status_code == 400
      and r.get_json()['error'] == 'ID канала — только цифры', 'канал буквами — 400')
r = client.post('/api/guild/777/birthdays/settings', json={'role_id': '12a'})
check(r.status_code == 400
      and r.get_json()['error'] == 'ID роли — только цифры', 'роль буквами — 400')
r = client.post('/api/guild/777/birthdays/settings', json={'gift_coins': -1})
check(r.status_code == 400
      and r.get_json()['error'] == 'Подарок — целое число от 0 до 100000',
      'отрицательный подарок — 400')
r = client.post('/api/guild/777/birthdays/settings', json={'gift_coins': 100001})
check(r.status_code == 400
      and r.get_json()['error'] == 'Подарок — целое число от 0 до 100000',
      'подарок сверх потолка — 400')
r = client.post('/api/guild/777/birthdays/settings', json={'message': ''})
check(r.status_code == 400
      and r.get_json()['error'] == 'Сообщение — от 1 до 200 символов',
      'пустое сообщение — 400')
r = client.post('/api/guild/777/birthdays/settings', json={'message': 'я' * 201})
check(r.status_code == 400
      and r.get_json()['error'] == 'Сообщение — от 1 до 200 символов',
      'длинное сообщение — 400')
r = client.post('/api/guild/777/birthdays/settings', json={'message': 'я' * 200})
check(r.status_code == 200, 'ровно 200 символов — можно')
pv = client.post('/api/guild/777/birthdays/preview', json={}).get_json()
check(pv['preview']['gift_coins'] == 50
      and pv['preview']['template'] == 'я' * 200,
      'превью читает свежие настройки')

login('mod')
csv_r = client.get('/api/guild/777/birthdays/export.csv')
body = csv_r.get_data(as_text=True)
check(csv_r.status_code == 200
      and 'birthdays_777.csv' in csv_r.headers.get('Content-Disposition', ''),
      'mod скачивает CSV с именем сервера')
check(body.startswith('\ufeffuser_id;name;date;year;age;days_until;celebrated'),
      'BOM + шапка календаря')
check(f';Аня;{rel(0)};2000;{real_now.year - 2000};0;{real_now.year}' in body,
      'сегодняшняя: возраст и год поздравления')
check('Вик,а' in body, 'точка с запятой в имени обезврежена')
check('Борислав' in body, 'в выгрузке имена из аудита')

print('== 8. Шаблон, меню, регистрация ==')
tpl = open(os.path.join(ROOT, 'web/templates/birthdays.html'), encoding='utf-8').read()
check(not EMOJI_RE.search(tpl), 'в шаблоне нет эмодзи')
base_tpl = open(os.path.join(ROOT, 'web', 'templates', 'base.html'), encoding='utf-8').read()
check('data-theme="light"' in base_tpl, 'светлая тема учтена (общий shell)')
for fid in ('bdKpis', 'bdList', 'bdCsv', 'bdAddPanel', 'bdAddId', 'bdAddDay',
            'bdAddMonth', 'bdAddYear', 'bdAddMsg', 'bdSetPanel', 'bdSetChannel',
            'bdSetRole', 'bdSetGift', 'bdSetMsg', 'bdSetMsgNote',
            'bdPreviewBox', 'bdPreviewBtn'):
    check(('id="' + fid + '"') in tpl, f'блок {fid} на месте')
check("'/overview'" in tpl and '/export.csv' in tpl
      and "'/preview'" in tpl, 'API-пути в шаблоне')
import services.panel_menu as PM
com_pages = [pg['path'] for g in PM.MENU if g['key'] == 'community' for pg in g['pages']]
check('/birthdays' in com_pages, 'пункт «Дни рождения» в группе «Сообщество»')
check(PM.PAGE_COGS.get('/birthdays') == ('birthday',),
      'birthday-ког привязан к странице')
ext = open(os.path.join(ROOT, 'web/routes_extra.py'), encoding='utf-8').read()
check(ext.count('birthdays_panel') >= 1, 'модуль зарегистрирован в routes_extra')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
