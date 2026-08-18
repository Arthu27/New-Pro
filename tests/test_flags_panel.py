# -*- coding: utf-8 -*-
"""Фичефлаги в панели (идея #8).

Проверяем: валидацию ключа, CRUD через тот же синглтон менеджера, что и
slash-команды (create/toggle/rollout/delete), персист в
data/feature_flags.json, снимок для undo, права mod/admin, шаблон
(гейтинг, без эмодзи), меню.

Запуск: python3 tests/test_flags_panel.py
"""
import importlib
import json
import os
import re
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='aether_flagspanel_test_')
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


from services.feature_flags import feature_flag_manager as FFM  # noqa: E402
from web.routes import flags_panel as FP  # noqa: E402

print('== 1. Валидация и payload ==')
check(FP._validate_key('')[1] == 'Введите ключ флага.', 'пустой ключ — честная ошибка')
check(FP._validate_key('ok_key-1')[0] == 'ok_key-1', 'валидный ключ проходит')
check(FP._validate_key('x')[0] is None, '1 символ — мимо (2-64)')
check(FP._validate_key('Bad KEY!')[0] is None, 'регистр/символы — мимо')
check(FP._validate_key('k' * 65)[0] is None, '65 символов — мимо')
p0 = FP.flags_payload()
check(p0['success'] and p0['total'] == 0 and p0['flags'] == [] and p0['avg_rollout'] == 0,
      'пустой реестр: честные нули')

print('== 2. API: права и CRUD ==')
appmod = importlib.import_module('web.app')
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()


def login(role='owner'):
    with client.session_transaction() as s:
        s.clear()
        s['logged_in'] = True
        s['username'] = 'admin'
        s['role'] = role


def post(path, payload):
    r = client.post(path, data=json.dumps(payload), content_type='application/json')
    try:
        return r.status_code, r.get_json()
    except Exception:
        return r.status_code, {'raw': r.data[:200]}


check(client.get('/feature-flags').status_code in (302, 401, 403), 'гостю страница закрыта')
check(client.get('/api/feature-flags/state').status_code in (302, 401, 403), 'гостю state закрыт')
login('uye')
check(client.get('/feature-flags').status_code == 403, 'uye нельзя')
login('mod')
check(client.get('/feature-flags').status_code == 200, 'mod читает страницу')
check(client.get('/api/feature-flags/state').status_code == 200, 'mod читает state')
check(post('/api/feature-flags/create', {'key': 'aa', 'name': 'A'})[0] == 403, 'mod не создаёт')
check(post('/api/feature-flags/toggle', {'key': 'aa'})[0] == 403, 'mod не переключает')

login('admin')
code, d = post('/api/feature-flags/create',
               {'key': 'ticket_ai_triage', 'name': 'AI-триаж тикетов', 'description': 'Сортировка тикетов'})
check(code == 200 and d['created']['key'] == 'ticket_ai_triage' and d['total'] == 1,
      'admin создаёт флаг')
check(d['created']['created_by'] == 'panel:admin', 'авторство panel:admin')
check(d['created']['enabled'] is False and d['created']['rollout'] == 0, 'новый флаг выключен с 0%')
code, d = post('/api/feature-flags/create', {'key': 'ticket_ai_triage', 'name': 'X'})
check(code == 409 and d['error'] == 'Флаг с таким ключом уже есть.', 'дубликат — 409')
code, d = post('/api/feature-flags/create', {'key': '!ПЛОХОЙ', 'name': 'X'})
check(code == 400 and d['error'] == 'Ключ: строчные буквы, цифры, дефис или подчёркивание (2-64 символа).',
      'плохой ключ — 400 с текстом')
code, d = post('/api/feature-flags/create', {'key': 'noname', 'name': ' '})
check(code == 400 and d['error'] == 'Введите название флага.', 'без названия — 400')

code, d = post('/api/feature-flags/toggle', {'key': 'ticket_ai_triage'})
check(code == 200 and d['flags'][0]['enabled'] is True and d['enabled_count'] == 1,
      'toggle включает')
code, d = post('/api/feature-flags/toggle', {'key': 'ticket_ai_triage'})
check(code == 200 and d['flags'][0]['enabled'] is False, 'toggle выключает')
code, d = post('/api/feature-flags/toggle', {'key': 'ghost_flag'})
check(code == 404 and d['error'] == 'Флаг не найден.', 'toggle призрака — 404')

code, d = post('/api/feature-flags/rollout', {'key': 'ticket_ai_triage', 'percent': 35})
check(code == 200 and d['flags'][0]['rollout'] == 35, 'rollout выставлен (35%)')
check(FFM.get_flag('ticket_ai_triage').rollout_percentage == 35, 'rollout доехал до менеджера')
code, d = post('/api/feature-flags/rollout', {'key': 'ticket_ai_triage', 'percent': 'много'})
check(code == 400 and d['error'] == 'Процент должен быть целым числом.', 'rollout мусор — 400')
code, d = post('/api/feature-flags/rollout', {'key': 'ticket_ai_triage', 'percent': 150})
check(code == 400 and d['error'] == 'Процент выкатки — от 0 до 100.', 'rollout сверх 100 — 400')

with open('data/feature_flags.json', encoding='utf-8') as fh:
    on_disk = json.load(fh)
check('ticket_ai_triage' in on_disk, 'флаг персистится в файл бота')

code, d = post('/api/feature-flags/delete', {'key': 'ghost_flag'})
check(code == 404 and d['error'] == 'Флаг не найден.', 'delete призрака — 404')
code, d = post('/api/feature-flags/delete', {'key': 'ticket_ai_triage'})
check(code == 200 and d['total'] == 0 and d['removed']['rollout'] == 35,
      'delete 200 + снимок для undo')
code, d = post('/api/feature-flags/create',
               {'key': 'ticket_ai_triage', 'name': 'AI-триаж тикетов', 'description': 'Сортировка тикетов'})
code2, d2 = post('/api/feature-flags/rollout', {'key': 'ticket_ai_triage', 'percent': 35})
check(code == 200 and code2 == 200 and d2['flags'][0]['rollout'] == 35,
      'undo: флаг и процент восстановлены')

print('== 3. Шаблон и меню ==')
html = client.get('/feature-flags').get_data(as_text=True)
check('id="ffKey"' in html and 'var CAN_EDIT = true' in html, 'admin: форма + CAN_EDIT=true')
login('mod')
html_mod = client.get('/feature-flags').get_data(as_text=True)
check('id="ffKey"' not in html_mod and 'var CAN_EDIT = false' in html_mod, 'mod: без формы')
tpl = open(os.path.join(ROOT, 'web/templates/feature_flags.html'), encoding='utf-8').read()
emoji = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')
check(not emoji.search(tpl), 'в шаблоне нет эмодзи')
base_tpl = open(os.path.join(ROOT, 'web', 'templates', 'base.html'), encoding='utf-8').read()
check('data-theme="light"' in base_tpl, 'светлая тема учтена (общий shell)')
check('uxUndo' in tpl and 'askConfirm' in tpl, 'undo и confirm на месте')
import services.panel_menu as PM
paths = [pg['path'] for g in PM.MENU for pg in g['pages']]
check('/feature-flags' in paths, 'пункт меню «Флаги» есть')
check('/feature-flags' not in PM.PAGE_COGS, 'флаги — сервисный модуль, в PAGE_COGS не входит')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
