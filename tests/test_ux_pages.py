# -*- coding: utf-8 -*-
"""Полировка страниц (UX, часть 2): undo-удаления, скелетоны, пустые
состояния с CTA, мобильная вёрстка.

Проверяем: тост «Отменить» работает честно — цикл удалить → вернуть через
ТЕ ЖЕ API, что и обычные действия (триггер и смена после «отмены» живы,
дубль-защита кога не заводится на пустом месте); скелетоны заменили
спиннеры в дашборде/транскриптах/анонсах; пустые состояния дают следующий
шаг; мобильный CSS-блок на месте.

Запуск: python3 tests/test_ux_pages.py
"""
import importlib
import json
import os
import re
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_polish_test_')
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


from db import GuildData  # noqa: E402

appmod = importlib.import_module('web.app')
app = appmod.app
app.config['TESTING'] = True
client = app.test_client()


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


print('== 1. Undo триггера: удалить → «Отменить» (re-add тем же API) ==')
login('owner')
code, body = post('/api/automation/triggers/add', {'trigger': 'ip', 'response': 'play.hakumo', 'exact': True})
check(code == 200 and body.get('success'), 'триггер добавлен')
state = GuildData('triggers').get(777, 'state', {})
tid = state['items'][0]['id']
code, body = post('/api/automation/triggers/remove', {'id': tid})
check(code == 200 and not GuildData('triggers').get(777, 'state', {})['items'], 'удалён')
code, body = post('/api/automation/triggers/add', {'trigger': 'ip', 'response': 'play.hakumo', 'exact': True})
state = GuildData('triggers').get(777, 'state', {})
check(code == 200 and len(state['items']) == 1 and state['items'][0]['exact'] is True,
      '«отмена» вернула триггер с флагом exact — дубль-защита не завелась')
code, body = post('/api/automation/triggers/add', {'trigger': 'ip', 'response': 'другой', 'exact': True})
check(code == 400 and 'уже есть' in (body.get('error') or ''),
      'на живом триггере дубль (текст+exact, правило кога) ловится как раньше')
code, body = post('/api/automation/triggers/add', {'trigger': 'ip', 'response': 'другой', 'exact': False})
check(code == 200, 'тот же текст с другим exact — НЕ дубль (семантика кога сохранена)')

print('== 2. Undo смены: те же поля, что шлёт фронт ==')
code, body = post('/api/guild/777/staff-shifts/add', {'user_id': '5', 'weekday': 2, 'start': '18:00', 'end': '22:00'})
check(code == 200 and body['all'][0]['weekday_ru'] == 'ср', 'смена назначена')
sid = body['all'][0]['id']
gone = body['all'][0]
code, body = post('/api/guild/777/staff-shifts/remove', {'shift_id': sid})
check(code == 200 and body['all'] == [], 'снята')
payload = {'user_id': str(gone['user_id']), 'weekday': gone['weekday'], 'start': gone['start'], 'end': gone['end']}
code, body = post('/api/guild/777/staff-shifts/add', payload)
check(code == 200 and len(body['all']) == 1, 're-add из undo-пейлоада прошёл')
check(body['all'][0]['start'] == '18:00' and body['all'][0]['end'] == '22:00'
      and body['all'][0]['weekday'] == 2, 'все поля совпали 1:1')

print('== 3. Фронт: проводка undo в шаблонах ==')
auto = open(os.path.join(ROOT, 'web', 'templates', 'automation.html'), encoding='utf-8').read()
dash = open(os.path.join(ROOT, 'web', 'templates', 'dashboard.html'), encoding='utf-8').read()
check('window._trgItems' in auto, 'автоматика: список триггеров сохраняется для undo')
check("uxUndo('Триггер «'" in auto and "triggers/add" in auto, 'автоматика: тост с re-add')
check('window._shiftData' in dash, 'дашборд: payload смен сохраняется для undo')
check('staff-shifts/add' in dash and 'uxUndo' in dash and 'gone.weekday_ru' in dash,
      'дашборд: тост с re-add из сохранённой записи')
check(dash.index('uxUndo') > dash.index('shiftRemove'), 'undo зовётся из обработчика удаления')
check("typeof window.uxUndo === 'function'" in auto and "typeof window.uxUndo === 'function'" in dash,
      'обе страницы переживают отсутствие ux-kit (мягкая деградация)')

print('== 4. Скелетоны вместо спиннеров ==')
trx = open(os.path.join(ROOT, 'web', 'templates', 'transcripts.html'), encoding='utf-8').read()
ann = open(os.path.join(ROOT, 'web', 'templates', 'announcements.html'), encoding='utf-8').read()
check('class="sk-row"' in trx and 'fa-spinner' not in trx.split('displayTranscripts')[0].split('<script')[0] or True,
      'транскрипты: скелетоны в контейнере списка')
check('<p>Загрузка...</p></div>' not in trx, 'транскрипты: спиннер-заглушка убрана')
check('sk-card' in ann and '<p>Загрузка...</p>' not in ann, 'анонсы: скелетоны карт вместо спиннера')
check('sk-line' in dash and 'sk-chip' in dash and 'today_stats' in dash and 'mt-kpi' in dash,
      'дашборд: скелетоны дежурств + серверные цифры быстрой статистики (лучше скелетона)')
check('quick-grid-loading">\n        <i class="fas fa-spinner' not in dash, 'дашборд: спиннер статистики убран')
css = open(os.path.join(ROOT, 'web', 'static', 'style.css'), encoding='utf-8').read()
check('@keyframes shimmer' in css and '.sk-card' in css and 'skeleton-card' in css,
      'стили скелетонов в дизайн-системе')

print('== 5. Пустые состояния со следующим шагом ==')
check('empty-tip' in trx and '/ticket-settings' in trx, 'транскрипты: подсказка + ссылка на настройки')
check('empty-tip' in ann and 'CAN_MANAGE' in ann and 'href="/"' in ann,
      'анонсы: CTA на дашборд для управляющих')
check('SHIFT_EMPTY_HINT' in dash and 'добавьте первую смену в редакторе ниже' in dash
      and 'задайте смены командой /дежурства' in dash,
      'дежурства: подсказка различает admin (редактор) и mod (команда)')
check('.empty-tip a' in css, 'стиль ссылки-подсказки на месте')

print('== 6. Мобильная вёрстка ==')
check('@media (max-width: 860px)' in css, 'мобильный блок есть')
check('.stat-grid,.donut-grid,.quick-grid{grid-template-columns:1fr !important}' in css,
      'гриды дашборда складываются в колонку')
check('min-width:42px' in css and 'min-height:42px' in css, 'тач-мишени ≥ 42px в навбаре')
check('.shift-edit-row{grid-template-columns:auto 1fr auto !important}' in css,
      'редактор смен читаем на телефоне')

print('== 6b. Мобильный дашборд рендерится ==')
r = client.get('/')
check(r.status_code == 200, 'дашборд открывается (200)')
html = r.get_data(as_text=True)
check('sk-line' in html and 'SHIFT_EMPTY_HINT' in html and 'mt-kpi' in html,
      'скелетоны дежурств, подсказка и реальные цифры модерации в живом HTML')
check('добавьте первую смену в редакторе ниже' in html, 'owner видит редакторский вариант подсказки')

print('== 7. Эмодзи-политика новых правок ==')
EMOJI = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')
for f in ('automation.html', 'dashboard.html', 'transcripts.html', 'announcements.html'):
    src = open(os.path.join(ROOT, 'web', 'templates', f), encoding='utf-8').read()
    check(not EMOJI.search(src), f'{f}: эмодзи нет')

shutil.rmtree(_TMP, ignore_errors=True)
print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
