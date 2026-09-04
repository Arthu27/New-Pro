# -*- coding: utf-8 -*-
"""Профи-раунд: страйки антифейка, Про-аналитика, Аналитика сервера, русский текст.

Запуск: python3 tests/test_antifake_analytics_pro.py
"""
import json
import os
import re
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_afana_')
os.environ['DB_PATH'] = os.path.join(_TMP, 'bot.db')
os.environ['DEMO_MODE'] = '1'
os.environ['SECRET_KEY'] = 'test-secret'
os.environ['PANEL_USER'] = 'owner'
os.environ['PANEL_PASSWORD'] = 'preview123'
os.environ['MAIN_GUILD_ID'] = '987654321098765432'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(_TMP)
os.makedirs('data', exist_ok=True)

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


GID = '987654321098765432'

# ═══ 1. Страйки: файл-первый, гильдии не смешиваются ═════════════════════
print('== страйки антифейка ==')
import time  # noqa: E402
now = time.time()
strikes = {
    GID: {'1001': [now - 3600, now - 7200], '1002': [now - 86400 * 10]},
    '111': {'1001': [now - 60]},   # другой сервер — не должен попадать в выдачу
}
with open('data/antifake_strikes.json', 'w', encoding='utf-8') as f:
    json.dump(strikes, f)
with open('data/antifake.json', 'w', encoding='utf-8') as f:
    json.dump({GID: {'threshold': 0.85, 'protected_names': ['Hakumo'],
                     'log_channel_id': 1002}}, f)

from web.app import app as flask_app  # noqa: E402

client = flask_app.test_client()
with client.session_transaction() as s:
    s['logged_in'] = True
    s['username'] = 'owner'
    s['role'] = 'owner'

r = client.get(f'/api/guild/{GID}/antifake/strikes')
d = r.get_json()
check(r.status_code == 200 and d.get('success'), 'страйки отдаются без живого бота (файл)')
entries = {e['user_id']: e for e in d.get('entries', [])}
check(set(entries) == {'1001', '1002'},
      f'в выдаче только участники ЭТОЙ гильдии (получено {sorted(entries)})')
check(entries['1001']['active'] == 2 and entries['1001']['total'] == 2,
      'активные страйки считаются по окну (2 свежих)')
check(entries['1002']['active'] == 0 and entries['1002']['total'] == 1,
      'протухший страйк не считается активным, но остаётся в «всего»')
check(isinstance(entries['1001'].get('history'), list) and len(entries['1001']['history']) == 2,
      'история меток приходит отсортированной')

# сброс
r = client.post(f'/api/guild/{GID}/antifake/strikes/clear', json={'user_id': 1001})
d = r.get_json()
check(r.status_code == 200 and d.get('success') and d.get('removed') == 2,
      'сброс страйков участника: 2 снято')
r = client.get(f'/api/guild/{GID}/antifake/strikes')
check('1001' not in {e['user_id'] for e in r.get_json()['entries']},
      'после сброса участника нет в списке')
r = client.post(f'/api/guild/{GID}/antifake/strikes/clear', json={'user_id': 999})
check(r.status_code == 404, 'сброс без страйков — честные 404')

# CSV
r = client.get(f'/api/guild/{GID}/antifake/strikes.csv')
body = r.get_data(as_text=True)
check(r.status_code == 200 and body.startswith('\ufeffuser_id;name;active;total;last_at'),
      'CSV с BOM и заголовком')
check('1002;' in body, 'CSV содержит строку участника')

# ═══ 2. Статус/тумблер/защита без бота ═════════════════════════════════
print('== антифейк: статус и мутации без бота ==')
r = client.get(f'/api/guild/{GID}/antifake/status')
d = r.get_json()
check(r.status_code == 200 and d.get('success') and d.get('threshold_pct') == 85,
      'статус читается из файла (порог 85)')
check(d.get('protected_count') == 1 and 'Hakumo' in d.get('protected_names', []),
      'защищаемые строки из файла')
check(len(d.get('toggles', [])) == 7, '7 тумблеров')
r = client.post(f'/api/guild/{GID}/antifake/toggle', json={'key': 'check_ads'})
check(r.status_code == 200 and r.get_json().get('success') and r.get_json().get('on') is False,
      'тумблер пишется в файл')
r = client.post(f'/api/guild/{GID}/antifake/threshold', json={'percent': 70})
check(r.get_json().get('success') and r.get_json().get('threshold_pct') == 70,
      'порог пишется в файл')
r = client.post(f'/api/guild/{GID}/antifake/threshold', json={'percent': 10})
check(r.status_code == 400, 'порог вне 60..100 отклоняется')
r = client.post(f'/api/guild/{GID}/antifake/protect', json={'text': 'Куратор'})
check(r.get_json().get('success') and 'Куратор' in r.get_json().get('protected_names', []),
      'защита строки без бота')

# лаборатория — чистые функции
r = client.post(f'/api/guild/{GID}/antifake/lab', json={'text': 'Hakumo'})
d = r.get_json()
check(d.get('success') and d.get('catch') and d['matches'][0]['score_pct'] == 100,
      'лаборатория ловит точное совпадение')
r = client.post(f'/api/guild/{GID}/antifake/lab', json={'text': ''})
check(r.status_code == 400, 'лаборатория с пустым текстом — 400')

# ═══ 3. Про-аналитика удалена ═══════════════════════════════════════════
print('== Про-аналитика ==')
import glob as _g  # noqa: E402  (нужен секции «русский текст» ниже)
# /advanced-analytics целиком читала data/ai_tickets_*.json — данные
# тикет-системы, снятой владельцем. Страница, маршрут и шаблон удалены.
check(not os.path.exists(os.path.join(ROOT, 'web', 'templates', 'advanced_analytics.html')),
      'шаблон Про-аналитики удалён вместе с тикетами')


# ═══ 4. Аналитика сервера: нет var()/color-mix в Chart.js-конфигах ══════
print('== Аналитика сервера ==')
t_an = open(os.path.join(ROOT, 'web', 'templates', 'analytics.html'), encoding='utf-8').read()
js_body = re.sub(r'<style>.*?</style>', '', t_an, flags=re.S)
js_body = re.sub(r'<script src="[^"]*"></script>', '', js_body)
bad_colors = re.findall(r"(?:ticks|grid|legend)\s*:\s*\{[^}]*?(?:color-mix|var\()", js_body)
check(not bad_colors, f'в Chart.js-конфигах аналитики нет var()/color-mix ({bad_colors[:3]})')
check('anTick()' in t_an and 'anGrid()' in t_an, 'аналитика: темо-зависимые цвета осей/сетки')

# ═══ 5. Русский текст: турецкого не осталось ═══════════════════════════
print('== русский текст ==')
tr_needles = ['Роль yok', 'Tetikleyici', 'команда yok', '!anticrash kanal', 'olmadan']
for f in _g.glob(os.path.join(ROOT, 'web', 'templates', '*.html')):
    text = open(f, encoding='utf-8').read()
    for n in tr_needles:
        check(n not in text, f'{os.path.basename(f)}: нет «{n}»')

# ═══ 6. Числовые ряды CPU/RAM (п.2: только числа, графики удалены) ══════
print('== числовые показатели (без линий) ==')
appjs = open(os.path.join(ROOT, 'web', 'static', 'app.js'), encoding='utf-8').read()
hc_cut = appjs[appjs.index('window.HakumoChart'):]
check('сейчас' in hc_cut and 'сред' in hc_cut and 'макс' in hc_cut and 'мин' in hc_cut,
      'бывший спарклайн показывает числовую сводку сейчас/сред/мин/макс')
check('_statsRow' in hc_cut and "'<svg'" not in hc_cut,
      'числовая сводка без SVG-линий')
t_bs = open(os.path.join(ROOT, 'web', 'templates', 'bot_stats.html'), encoding='utf-8').read()
check("$('cpuNow').textContent" in t_bs and "$('ramNow').textContent" in t_bs,
      'bot-stats: текущие CPU/RAM — просто числом')
check('HakumoChart' in t_bs, 'bot-stats: сводки истории сессии живые')

# ═══ 7. Страница антифейка: карточки страйков ═════════════════════════
print('== шаблон страйков ==')
t_af = open(os.path.join(ROOT, 'web', 'templates', 'antifake.html'), encoding='utf-8').read()
check('af-strike-card' in t_af and 'af-strike-card .bar' in t_af,
      'страйки — карточки с прогресс-баром')
check('История:' in t_af and 'активных из' in t_af,
      'карточка: история меток и счётчик активных')
check('fa-eraser' in t_af, 'кнопка сброса с иконкой')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(0 if FAIL == 0 else 1)
