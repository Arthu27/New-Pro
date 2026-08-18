# -*- coding: utf-8 -*-
"""Инфо-база сервера (идеи #176-180).

Витрина 1:1 кнопке «Текущая информация» (срезы 500/200, первые пять пар),
поля 1:1 модалкам (strip, потолок 1000, «… сохранено!»), пары 1:1
OzelBilgiModal (50/500, «{заголовок} сохранено!»), очистка словами danger-
кнопки, контекст 1:1 get_sunucu_context — чтение/запись только через
_load_info/_save_info кога (общий json_store-кэш и файл).

Запуск: python3 tests/test_server_info_panel.py
"""
import importlib
import json
import os
import re
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='aether_si_test_')
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


# Фикстура ДО первого чтения (json_store кэширует).
json.dump({'о': 'Сервер о космосе', 'правила': 'Без спама',
           'yetkili_olmak': 'Напиши админу',
           'приватные_данные': {'Ссылка Discord': 'https://d.gg/x',
                                'День событий': 'пятница'}},
          open('data/server_info_777.json', 'w', encoding='utf-8'),
          ensure_ascii=False)

from web.routes import server_info_panel as SP  # noqa: E402
import cogs.server_info as SI  # noqa: E402

EMOJI_RE = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')

print('== 1. Проводка и пустая база ==')
check(SP._load_info is SI._load_info and SP._save_info is SI._save_info,
      'чтение/запись — те самые функции кога')
v = SP.view('321')
check(v['empty'] is True and v['context'] == ''
      and v['note'] == 'Информация еще не введена.',
      'пусто — словами бота, с «еще»')
check(all(f['value'] == '' and f['card'] == '' for f in v['fields'])
      and v['pairs'] == [] and v['card_pairs'] == [], 'пустые поля и пары')
check([f['title'] for f in v['fields']] == ['Информация о сервере',
                                            'Правила сервера',
                                            'Как стать модератором'],
      'заголовки — из модалок кнопок')

print('== 2. Витрина наполненной базы ==')
v = SP.view('777')
check(v['empty'] is False, 'база жива')
check(v['fields'][0]['value'] == 'Сервер о космосе'
      and v['fields'][0]['card'] == 'Сервер о космосе', 'поле «о» полное и в карточке')
check(len(v['pairs']) == 2 and len(v['card_pairs']) == 2, 'две пары, обе в карточке')
check(v['context'] == ('=== СЕРВЕР ИНФОРМАЦИЯ ===\n'
                       'О сервере: Сервер о космосе\n'
                       'Правила: Без спама\n'
                       'Как стать модератором: Напиши админу\n'
                       'Ссылка Discord: https://d.gg/x\n'
                       'День событий: пятница'),
      'контекст для AI посимвольно как в коге')

print('== 3. Поля — правила ServerModal ==')
ok, err, _ = SP.save_field_flow('777', 'мусор', 'x')
check(not ok and err == SP.ERR_FIELD, 'левое поле — отказ')
ok, err, p = SP.save_field_flow('777', 'rules', '  Новые правила  ')
check(ok and p['message'] == 'Правила сервера сохранено!'
      and SI._load_info(777)['правила'] == 'Новые правила',
      'strip и слова модалки (без эмодзи и маркдауна)')
ok, err, p = SP.save_field_flow('777', 'rules', 'й' * 1500)
check(ok and len(SI._load_info(777)['правила']) == 1000,
      'потолок 1000 — как max_length TextInput')
ok, err, p = SP.save_field_flow('777', 'rules', '   ')
check(ok and p['message'] == 'Правила сервера очищено.'
      and 'правила' not in SI._load_info(777), 'пустая строка стирает поле')

print('== 4. Пары — правила OzelBilgiModal (+ панельное удаление) ==')
ok, err, _ = SP.set_pair_flow('777', '   ', 'x')
check(not ok and err == SP.ERR_KEY, 'пустой заголовок — отказ')
ok, err, _ = SP.set_pair_flow('777', 'Ключ', '   ')
check(not ok and err == SP.ERR_VALUE, 'пустое содержимое — отказ')
ok, err, p = SP.set_pair_flow('777', 'Куратор', 'Катя')
check(ok and p['message'] == 'Куратор сохранено!'
      and SI._load_info(777)['приватные_данные']['Куратор'] == 'Катя',
      'пара добавлена словами модалки')
ok, err, p = SP.set_pair_flow('777', 'к' * 60, 'v')
check(ok and max(SI._load_info(777)['приватные_данные'], key=len),
      'потолок заголовка 50')
longkey_stored = 'к' * 50 in SI._load_info(777)['приватные_данные']
check(longkey_stored, 'длинный заголовок хранится обрезанным')
ok, err, p = SP.del_pair_flow('777', 'к' * 50)
check(ok and 'удалена. Осталось:' in p['message'], 'длинная пара убрана')
ok, err, p = SP.set_pair_flow('777', 'Ссылка Discord', 'https://new')
check(ok and len(SI._load_info(777)['приватные_данные']) == 3,
      'обновление не плодит ключи')
ok, err, p = SP.del_pair_flow('777', 'Куратор')
check(ok and p['message'] == 'Пара «Куратор» удалена. Осталось: 2.',
      'удаление со счётчиком')
ok, err, p = SP.del_pair_flow('777', 'Нет такой')
check(not ok and p is None and err == 'Пара «Нет такой» не найдена.',
      'чужая пара — её текст')

print('== 5. Файл после всех правок ==')
stored = SI._load_info(777)
check(stored == {'о': 'Сервер о космосе', 'yetkili_olmak': 'Напиши админу',
                 'приватные_данные': {'Ссылка Discord': 'https://new',
                                      'День событий': 'пятница'}},
      'итоговое состояние пересчитано руками')
on_disk = json.load(open('data/server_info_777.json', encoding='utf-8'))
check(on_disk == stored, 'файл на диске совпадает')
v = SP.view('777')
check('Правила:' not in v['context']
      and 'Ссылка Discord: https://new' in v['context'],
      'контекст пересобран без стёртых правил')

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


VW = '/api/guild/777/server-info/view'
check(client.get('/server-info').status_code in (302, 401, 403),
      'гостю страница закрыта')
check(client.get(VW).status_code in (302, 401, 403), 'гостю API закрыто')
login('uye')
check(client.get(VW).status_code == 403, 'uye не смотрит')
login('mod')
page = client.get('/server-info')
check(page.status_code == 200
      and 'Инфо-база сервера' in page.get_data(as_text=True),
      'mod открывает страницу')
d = client.get(VW).get_json()
check(d['success'] and d['view']['empty'] is False
      and d['can_edit'] is False
      and len(d['view']['pairs']) == 2, 'вид для mod')
check(client.post('/api/guild/777/server-info/field',
                  json={'field': 'about', 'text': 'x'}).status_code == 403,
      'mod не правит поля')
check(client.post('/api/guild/777/server-info/clear', json={})
      .status_code == 403, 'mod не очищает')
login('admin')
r = client.post('/api/guild/777/server-info/field',
                json={'field': 'about', 'text': '  Обновлено  '})
d = r.get_json()
check(r.status_code == 200 and d['message'] == 'Информация о сервере сохранено!'
      and d['view']['fields'][0]['value'] == 'Обновлено',
      'admin обновил поле через API')
r = client.post('/api/guild/777/server-info/pair',
                json={'key': 'День тестов', 'value': 'сегодня'})
check(r.status_code == 200 and len(r.get_json()['view']['pairs']) == 3,
      'admin добавил пару через API')
r = client.post('/api/guild/777/server-info/pair-delete',
                json={'key': 'День тестов'})
check(r.status_code == 200 and 'Осталось: 2.' in r.get_json()['message'],
      'admin убрал пару через API')
r = client.post('/api/guild/777/server-info/pair-delete',
                json={'key': 'День тестов'})
check(r.status_code == 400
      and r.get_json()['error'] == 'Пара «День тестов» не найдена.',
      'повторное — 400 её текстом')
r = client.post('/api/guild/777/server-info/clear', json={})
check(r.status_code == 200
      and r.get_json()['message'] == 'Вся информация о сервере очищена.',
      'clear — словами danger-кнопки')
d = client.get(VW).get_json()
check(d['view']['empty'] is True and d['view']['context'] == ''
      and d['view']['note'] == 'Информация еще не введена.',
      'после очистки — пусто и заметка бота')
login('mod')

print('== 7. Шаблон, меню, регистрация ==')
tpl = open(os.path.join(ROOT, 'web/templates/server_info.html'),
           encoding='utf-8').read()
check(not EMOJI_RE.search(tpl), 'в шаблоне нет эмодзи')
src = open(os.path.join(ROOT, 'web/routes/server_info_panel.py'),
           encoding='utf-8').read()
check(not EMOJI_RE.search(src), 'в модуле нет эмодзи')
base_tpl = open(os.path.join(ROOT, 'web', 'templates', 'base.html'), encoding='utf-8').read()
check('data-theme="light"' in base_tpl, 'светлая тема учтена (общий shell)')
for fid in ('siFields', 'siPairs', 'siPairForm', 'siPairKey', 'siPairVal',
            'siPairAdd', 'siClearRow', 'siClear', 'siContext', 'siEmpty',
            'siMsg', 'siPairMsg'):
    check(('id="' + fid + '"') in tpl, f'блок {fid} на месте')
for path in ("'/view'", "'/field'", "'/pair'", "'/pair-delete'", "'/clear'"):
    check(path in tpl, f'путь {path} в шаблоне')
check('localhost' not in tpl and '127.0.0.1' not in tpl, 'без локальных адресов')
import services.panel_menu as PM
ai_pages = [pg['path'] for g in PM.MENU if g['key'] == 'ai'
            for pg in g['pages']]
check('/server-info' in ai_pages, 'пункт меню «Инфо-база» в «AI»')
check(PM.PAGE_COGS.get('/server-info') == ('server_info',), 'ког привязан')
ext = open(os.path.join(ROOT, 'web/routes_extra.py'), encoding='utf-8').read()
check(ext.count('server_info_panel') >= 1,
      'модуль зарегистрирован в routes_extra')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
