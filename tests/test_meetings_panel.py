# -*- coding: utf-8 -*-
"""Собрания (идеи #141-145).

Статус (склейка ролей из мод-отчётов 1:1), старт/финиш через шаги кнопок
(голосовой снимок, окно since по цепочке, сброс полей, тексты кога),
роли отчёта (дедуп/удаление), предпросмотр очков по формуле бота на
живом _scan_voice и _load_invites, CSV, права, шаблон, меню.

Запуск: python3 tests/test_meetings_panel.py
"""
import importlib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

_TMP = tempfile.mkdtemp(prefix='aether_meetings_test_')
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


from web.routes import meetings_panel as PL  # noqa: E402

EMOJI_RE = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')
UTC = timezone.utc

# Фикстуры пишем ОДИН РАЗ до любых обращений — load_json кэширует.
json.dump({'active': False, 'last_meeting': '2026-08-15T20:00:00+00:00',
           'staff_roles': [555, 666], 'panel_channel': 9001},
          open('data/meeting_777.json', 'w', encoding='utf-8'))
json.dump({}, open('data/meeting_333.json', 'w', encoding='utf-8'))
json.dump({'staff_roles': [42]},
          open('data/mod_report_config_333.json', 'w', encoding='utf-8'))
json.dump({'active': True, 'meeting_start': None,
           'last_meeting': '2026-08-10T10:00:00+00:00'},
          open('data/meeting_666.json', 'w', encoding='utf-8'))
json.dump({'active': True}, open('data/meeting_321.json', 'w', encoding='utf-8'))
# превью-гильдия 555: голос (legacy -> SQLite), снимок, инвайты
json.dump({'users': {
           '111': {'total_seconds': 3600, 'name': 'Катя'},
           '222': {'total_seconds': 300, 'name': 'Иван'},
           '333': {'total_seconds': 900, 'name': 'Оля'}}},
          open('data/voice_stats_555.json', 'w', encoding='utf-8'))
json.dump({'111': 600, '222': 300},
          open('data/meeting_snapshot_555.json', 'w', encoding='utf-8'))
json.dump({'111': 2, '444': 1},
          open('data/invite_counts_555.json', 'w', encoding='utf-8'))

print('== 1. Тексты — слова кога ==')
cog_src = open(os.path.join(ROOT, 'cogs/meeting.py'), encoding='utf-8').read()
check('Собрание уже активно!' in cog_src, '«уже активно» — из кнопки кога')
check('Нет активного собрания.' in cog_src, '«нет активного» — из кнопки')
check('Format неверно!' in cog_src and '12.04.2026 22:00' in cog_src,
      'формат даты и пример — из модалки')
check('Собрание еще не проводилось.' in cog_src, '«не проводилось» — из кнопки отчёта')
check('Добавленные роли отсутствуют.' in cog_src, '«роли отсутствуют» — из кнопки')
check('добавлена в отчёт собрания.' in cog_src, 'успех добавления роли — из команды')
check(PL.FORMULA_TEXT in cog_src, 'формула очков — футер отчёта кога')
check(PL.ERR_ALREADY == 'Собрание уже активно!' and
      PL.ERR_NOT_ACTIVE == 'Нет активного собрания.' and
      PL.ERR_FORMAT == 'Format неверно! Напр.: 12.04.2026 22:00',
      'константы панели равны словам (без эмодзи)')

print('== 2. Статус ==')
st = PL.status_view(PL.load_cfg('777'))
check(st['active'] is False and st['ever_held'] is True and st['note'] is None,
      '777: собрание было, сейчас не идёт')
check(st['since'] == '2026-08-15T20:00:00+00:00' and st['staff_roles'] == ['555', '666'],
      '777: окно от последнего, роли свои')
check(st['elapsed_min'] is None, 'неактивному собранию длительности нет')
st = PL.status_view(PL.load_cfg('333'))
check(st['staff_roles'] == ['42'], '333: роли подмешались из конфига мод-отчётов')
st = PL.status_view(PL.load_cfg('999'))
check(st['ever_held'] is False and st['note'] == 'Собрание еще не проводилось.'
      and st['staff_roles'] == [], '999: ни разу — подпись кнопки кога')
st = PL.status_view({'active': True, 'meeting_start': '2026-08-16T10:00:00'})
check(st['elapsed_min'] is not None and st['since'] == '2026-08-16T10:00:00+00:00',
      'метка без TZ — UTC, длительность считается')
check(PL._parse_ts('мусор') is None, 'битая метка -> None')

print('== 3. Предпросмотр по формуле бота ==')
rows, totals = PL.preview('555')
check(len(rows) == 3, f'3 участника окна (пришло {len(rows)})')
check(rows[0]['uid'] == '111' and rows[0]['score'] == 110
      and rows[0]['voice_txt'] == '50 мин' and rows[0]['inv'] == 2
      and rows[0]['name'] == 'Катя',
      'Катя: 50 мин×2 + 2×5 = 110, имя из голосовой статистики')
check(rows[1] == {'uid': '333', 'name': 'Оля', 'voice_secs': 900,
                  'voice_txt': '15 мин', 'inv': 0, 'score': 30},
      'Оля: только голос против снимка')
check(rows[2]['uid'] == '444' and rows[2]['name'] == '444' and rows[2]['score'] == 5,
      'инвайт без голоса: 1×5 = 5, имя-фолбэк — uid')
check(totals == {'participants': 3, 'voice_min': 65, 'invites': 3, 'score': 145},
      f'итоги окна (пришло {totals})')
rows0, totals0 = PL.preview('999')
check(rows0 == [] and totals0['score'] == 0,
      'пустая гильдия — пустое окно, без падений')

print('== 4. Старт и финиш — шаги кнопок ==')
ok, err, _ = PL.start_flow('444', '32.13.2026 99:99')
check(not ok and err == PL.ERR_FORMAT, 'битая дата — текст модалки')
ok, err, start_iso = PL.start_flow('444', '12.04.2026 22:00')
check(ok and start_iso == '2026-04-12T22:00:00+00:00', 'своя дата — как в модалке')
ok, err, _ = PL.start_flow('444')
check(not ok and err == PL.ERR_ALREADY, 'повторный старт — «уже активно»')
ok, err, since, cfg = PL.end_flow('333')
check(not ok and err == PL.ERR_NOT_ACTIVE, 'финиш без старта — «нет активного»')
ok, err, since, cfg = PL.end_flow('666')
check(ok and since == datetime(2026, 8, 10, 10, 0, tzinfo=UTC),
      'окно since: meeting_start пуст -> last_meeting')
check(cfg['active'] is False and cfg['meeting_start'] is None
      and cfg['last_meeting'] is not None, 'финиш сбрасывает поля как кнопка')
ok, err, since, cfg = PL.end_flow('321')
want_from = datetime.now(UTC) - timedelta(days=7, minutes=1)
check(ok and since >= want_from and since <= datetime.now(UTC),
      'совсем без меток — окно «7 дней назад»')
ok, err, start_iso = PL.start_flow('5555')
check(ok and os.path.exists('data/meeting_snapshot_5555.json'),
      'старт фиксирует голосовой снимок')
snap = json.load(open('data/meeting_snapshot_5555.json', encoding='utf-8'))
check(snap == {}, 'пустой сервер — пустой снимок, но файл есть')

print('== 5. Роли отчёта ==')
ok, err, msg = PL.add_role_flow('777', '555')
check(ok and msg == 'Роль 555 добавлена в отчёт собрания.',
      'дубликат — ответ как у команды, список не пухнет')
check(PL.load_cfg('777')['staff_roles'] == [555, 666], 'дубликат не продублировался')
ok, err, msg = PL.add_role_flow('777', '<@&777889>')
check(ok and PL.load_cfg('777')['staff_roles'] == [555, 666, 777889],
      'меншен-синтаксис роли принят')
ok, err, _ = PL.add_role_flow('777', 'мусор')
check(not ok and err == PL.ERR_ROLE_ID, 'битый ID роли')
ok, err, msg = PL.add_role_flow('777', '4242', name='Модеры')
check(ok and msg == 'Роль Модеры добавлена в отчёт собрания.',
      'имя в тексте, когда бот его разрешил')
ok, err, msg = PL.remove_role_flow('777', '666')
check(ok and msg == 'Роль 666 убрана из отчёта собрания.'
      and PL.load_cfg('777')['staff_roles'] == [555, 777889, 4242],
      'удаление из списка')
ok, err, _ = PL.remove_role_flow('777', '666')
check(not ok and err == PL.ERR_ROLE_MISSING, 'повторное удаление — честный отказ')
ok, err, _ = PL.remove_role_flow('999', '1')
check(not ok and err == PL.ERR_NO_ROLES, 'пустой список — слова кнопки кога')

print('== 6. CSV-помощники ==')
crow = PL.csv_rows(rows)[0]
check(crow == ('111', 'Катя', 50, 2, 110), 'строка выгрузки: минуты и очки')
check(PL._csv_cell('а;б\nв') == 'а,б в', 'ячейки чистятся')

print('== 7. API и права ==')
appmod = importlib.import_module('web.app')
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()


def login(role='owner'):
    with client.session_transaction() as sess:
        sess.clear()
        sess['logged_in'] = True
        sess['username'] = 'admin'
        sess['role'] = role


ST = '/api/guild/888/meetings/status'
check(client.get('/meetings').status_code in (302, 401, 403), 'гостю страница закрыта')
check(client.get(ST).status_code in (302, 401, 403), 'гостю API закрыто')
login('uye')
check(client.get(ST).status_code == 403, 'uye не смотрит')
login('mod')
page = client.get('/meetings')
check(page.status_code == 200 and 'Собрания' in page.get_data(as_text=True),
      'mod открывает страницу')
check(client.post('/api/guild/888/meetings/start', json={}).status_code == 403,
      'mod не запускает собрание')
d = client.get('/api/guild/999/meetings/status').get_json()
check(d['status']['note'] == 'Собрание еще не проводилось.'
      and d['bot_online'] is False and d['can_edit'] is False,
      'статус пустого сервера через API')
pv = client.get('/api/guild/555/meetings/preview').get_json()
check(pv['success'] and len(pv['rows']) == 3 and pv['note'] == PL.PREVIEW_NOTE,
      'предпросмотр через API с честной подписью')
login('admin')
r = client.post('/api/guild/888/meetings/start', json={'time': '1 января'})
check(r.status_code == 400 and r.get_json()['error'] == PL.ERR_FORMAT,
      'API: битая дата — 400 с текстом кога')
r = client.post('/api/guild/888/meetings/start', json={'time': ''})
check(r.status_code == 200 and 'Собрание запущено:' in r.get_json()['message'],
      'API: старт с «сейчас»')
r = client.post('/api/guild/888/meetings/start', json={'time': ''})
check(r.status_code == 400 and r.get_json()['error'] == PL.ERR_ALREADY,
      'API: повторный старт — 400')
r = client.post('/api/guild/888/meetings/end', json={})
d = r.get_json()
check(r.status_code == 200 and 'Собрание завершено.' in d['message']
      and d['report_sent'] is False and 'Бот офлайн' in d['message'],
      'API: финиш офлайн — честно о несланном отчёте')
r = client.post('/api/guild/888/meetings/end', json={})
check(r.status_code == 400 and r.get_json()['error'] == PL.ERR_NOT_ACTIVE,
      'API: второй финиш — «нет активного»')
r = client.post('/api/guild/888/meetings/roles', json={'role': '31337'})
check(r.status_code == 200 and r.get_json()['status']['staff_roles'] == ['31337'],
      'API: роль добавлена')
r = client.post('/api/guild/888/meetings/roles/remove', json={'role': '31337'})
check(r.status_code == 200 and r.get_json()['status']['staff_roles'] == [],
      'API: роль убрана')
ex = client.get('/api/guild/555/meetings/export.csv')
body = ex.get_data(as_text=True)
check(ex.status_code == 200 and ex.headers['Content-Disposition'].endswith(
      'meetings_preview_555.csv'), 'имя файла выгрузки')
check(body.startswith('\ufeffuid;name;voice_minutes;invites;score'), 'BOM и шапка')
lines = body.strip().split('\n')
check(len(lines) == 4 and lines[1].startswith('111;Катя;50;2;110'),
      f'шапка + 3 строки, первая — Катя (пришло {len(lines)})')
login('uye')
check(client.get('/api/guild/555/meetings/export.csv').status_code == 403,
      'uye не выгружает')
login('mod')

print('== 8. Шаблон, меню, регистрация ==')
tpl = open(os.path.join(ROOT, 'web/templates/meetings.html'), encoding='utf-8').read()
check(not EMOJI_RE.search(tpl), 'в шаблоне нет эмодзи')
src = open(os.path.join(ROOT, 'web/routes/meetings_panel.py'), encoding='utf-8').read()
check(not EMOJI_RE.search(src), 'в модуле нет эмодзи')
check('[data-theme="light"]' in tpl, 'светлая тема учтена')
for fid in ('mtKpis', 'mtStartTime', 'mtStart', 'mtEnd', 'mtRoleInp', 'mtRoleAdd',
            'mtRoles', 'mtPrev', 'mtCsv'):
    check(('id="' + fid + '"') in tpl, f'блок {fid} на месте')
check("'/start'" in tpl and "'/end'" in tpl and "'/roles/remove'" in tpl
      and "'/export.csv'" in tpl, 'API-пути в шаблоне')
check('localhost' not in tpl and '127.0.0.1' not in tpl, 'без локальных адресов')
import services.panel_menu as PM
com_pages = [pg['path'] for g in PM.MENU if g['key'] == 'community' for pg in g['pages']]
check('/meetings' in com_pages, 'пункт меню «Собрания» в «Сообществе»')
check(PM.PAGE_COGS.get('/meetings') == ('meeting',), 'meeting-ког привязан')
ext = open(os.path.join(ROOT, 'web/routes_extra.py'), encoding='utf-8').read()
check(ext.count('meetings_panel') >= 1, 'модуль зарегистрирован в routes_extra')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
