# -*- coding: utf-8 -*-
"""Категория «Модерация» панели: сквозной аудит без Discord-бота.

Проверяем (15 страниц + их API + потоки записи + права + «до буквы»):
  1. Все 15 страниц раздела отдают 200 владельцу, содержат свой заголовок
     и не несут мусора в видимом тексте (undefined/NaN/[object Object]/
     кракозябры/утечка Jinja).
  2. Метаданные меню: группа «Модерация» = ровно те пути, что зарегистрированы
     во Flask, у каждого есть description и access.
  3. Читающие API раздела отдают 200 и честную структуру (демо-режим).
  4. Потоки записи без бота честны: офлайн-действия не притворяются успехом
     (temp-mod → 503, bulk → success=False), валидация → 400, чужой/неизвестный
     id → 404 (staff-apps review).
  5. Roundtrip «создать → увидеть → удалить» работает на чистых данных:
     лестница наказаний, расписание, причины мод-контроля, варны.
  6. Права: роль mod не ходит в админ-эндпоинты (403 / редирект).
  7. «До буквы»: в файлах раздела нет турецких/кракозябрных хвостов.

Запуск: python3 tests/test_mod_category_audit.py
"""
import json
import os
import re
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_modcat_')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# cwd не меняем — web.app регистрирует роуты относительно корня репо;
# в tmp уходим только для БД. Свои фикстуры пишем в data/ (гитигнор, демо-скретч).
os.chdir(ROOT)
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['DEMO_MODE'] = '1'
os.environ.pop('TOKEN', None)
os.environ['SECRET_KEY'] = 'test-secret'
os.environ['PANEL_USER'] = 'owner'
os.environ['PANEL_PASSWORD'] = 'preview123'
os.environ['MAIN_GUILD_ID'] = '987654321098765432'

PASS = 0
FAIL = 0


def check(cond, label, extra=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f'  PASS: {label}')
    else:
        FAIL += 1
        print(f'  FAIL: {label} {extra}')


GID = os.environ['MAIN_GUILD_ID']
import web.app as A  # noqa: E402
from services import panel_menu as PM  # noqa: E402

c = A.app.test_client()
with c.session_transaction() as sess:
    sess['logged_in'] = True
    sess['role'] = 'owner'
    sess['username'] = 'tester'

# ── 1. Страницы раздела ────────────────────────────────────────────────
MOD_PAGES = [p['path'] for grp in PM.MENU if grp['key'] == 'mod'
             for p in grp['pages']]
LABEL = {p['path']: p['label'] for grp in PM.MENU if grp['key'] == 'mod'
         for p in grp['pages']}
check(len(MOD_PAGES) == 15, f'в меню «Модерация» ровно 15 страниц (не {len(MOD_PAGES)})')

JUNK = [re.compile(r'>\s*undefined\b'), re.compile(r'\bNaN\b'),
        re.compile(r'\[object Object\]'), re.compile(r'[\ufffd]'),
        re.compile(r'Ã[\x80-\xbf]|â€|Ð[\x80-\x9f]'), re.compile(r'\{\{|\{%')]
for path in MOD_PAGES:
    r = c.get(path)
    ok = r.status_code == 200
    html = r.get_data(as_text=True)
    body = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', html, flags=re.S | re.I)
    bad = [p.pattern for p in JUNK if p.search(body)]
    has_title = LABEL[path] in body
    check(ok and not bad and has_title,
          f'{path} → 200, заголовок «{LABEL[path]}», без мусора',
          f'status={r.status_code} bad={bad} title={has_title}')

# ── 2. Меню ↔ роуты ───────────────────────────────────────────────────
ROUTES = {str(r) for r in A.app.url_map.iter_rules()}
for path in MOD_PAGES:
    meta = next(p for grp in PM.MENU if grp['key'] == 'mod'
                for p in grp['pages'] if p['path'] == path)
    check(path in ROUTES, f'{path} зарегистрирован во Flask')
    check(bool(meta.get('description')), f'{path} имеет description')
    check(bool(meta.get('access')), f'{path} имеет access')

# ── 3. Читающие API ───────────────────────────────────────────────────
GET_APIS = [
    '/api/warnings', '/api/temp-mod/active', '/api/mod-history', '/api/mod-stats',
    '/api/logs', '/api/proofs', '/api/proof-required', '/api/proof-whitelist',
    '/api/staff-apps',
    f'/api/guild/{GID}/appeals/overview', f'/api/guild/{GID}/mod-schedule',
    f'/api/guild/{GID}/reports-queue', f'/api/guild/{GID}/report-settings',
    f'/api/guild/{GID}/mod-control/overview', f'/api/guild/{GID}/mod-insights/overview',
    f'/api/guild/{GID}/ladder/view',
]
for api in GET_APIS:
    r = c.get(api)
    check(r.status_code == 200, f'GET {api} → 200', f'→ {r.status_code}')

# ── 4. Потоки записи без бота честны ──────────────────────────────────
def post(path, payload):
    return c.post(path, json=payload)

r = post('/api/temp-mod/mute', {'guild_id': GID, 'user_id': '111111111111111111',
                                'duration': 5, 'unit': 'minutes'})
check(r.status_code == 503 and (r.get_json() or {}).get('success') is not True,
      'temp-mod без бота → 503 и не success', f'→ {r.status_code}')
r = post(f'/api/guild/{GID}/bulk-mute', {'role_id': '1', 'minutes': 5})
check((r.get_json() or {}).get('success') is not True,
      'bulk-mute без бота не притворяется успехом')
r = post('/api/proofs/upload', {'guild_id': GID})
check(r.status_code == 400, 'proofs/upload без наказания → 400', f'→ {r.status_code}')
r = post('/api/staff-apps/doesnotexist/review', {'action': 'approve'})
check(r.status_code == 404, 'staff-apps review неизвестной заявки → 404', f'→ {r.status_code}')

# ── 5. Roundtrip на чистых данных ─────────────────────────────────────
# лестница наказаний
r = post(f'/api/guild/{GID}/ladder/add', {'count': 9, 'action': 'mute',
                                          'duration': 15, 'unit': 'minutes'})
check(r.status_code == 200 and (r.get_json() or {}).get('success') is True,
      'ladder: ступень 9 добавлена', f'→ {r.status_code} {r.get_data(as_text=True)[:100]}')
view = (c.get(f'/api/guild/{GID}/ladder/view').get_json() or {}).get('steps', [])
check(any(int(s.get('count') or 0) == 9 for s in view), 'ladder: ступень 9 видна')
r = post(f'/api/guild/{GID}/ladder/remove', {'count': 9})
check(r.status_code == 200, 'ladder: ступень 9 удалена', f'→ {r.status_code}')
view = (c.get(f'/api/guild/{GID}/ladder/view').get_json() or {}).get('steps', [])
check(not any(int(s.get('count') or 0) == 9 for s in view), 'ladder: ступени 9 больше нет')

# расписание
import time as _t
r = post(f'/api/guild/{GID}/mod-schedule/create',
         {'user_id': '111111111111111111', 'action': 'mute',
          'run_at': _t.time() + 3600, 'duration': 5, 'reason': 'аудит'})
d = r.get_json() or {}
check(r.status_code == 200 and d.get('success') is True and d.get('id'),
      'mod-schedule: отложенное действие создано', f'→ {r.status_code} {str(d)[:100]}')
sched = (c.get(f'/api/guild/{GID}/mod-schedule').get_json() or {})
check(any(e.get('id') == d.get('id') for e in sched.get('scheduled', [])),
      'mod-schedule: запись в списке')
r = post(f'/api/guild/{GID}/mod-schedule/cancel', {'id': d.get('id')})
check(r.status_code == 200, 'mod-schedule: отмена принята', f'→ {r.status_code}')

# причины мод-контроля
r = post(f'/api/guild/{GID}/mod-control/reasons', {'kind': 'warn', 'text': 'причина аудита'})
d = r.get_json() or {}
rid = (d.get('item') or {}).get('id')
check(r.status_code == 200 and rid, 'mod-control: причина добавлена', f'→ {r.status_code}')
r = c.post(f'/api/guild/{GID}/mod-control/reasons/warn/{rid}/delete')
check(r.status_code == 200, 'mod-control: причина удалена', f'→ {r.status_code}')

# варны: запись → чтение → очистка
r = post('/api/command/warn', {'guild_id': GID, 'user_id': '111111111111111111',
                               'reason': 'аудит-варн'})
check(r.status_code == 200 and (r.get_json() or {}).get('success') is True,
      'варн: добавлен через API', f'→ {r.status_code}')
warns = c.get('/api/warnings').get_json() or []
check(any(w.get('user_id') == '111111111111111111' and 'аудит-варн' in w.get('reason', '')
          for w in warns), 'варн: виден в /api/warnings')

# ── 6. Права: mod не ходит в админ-эндпоинты ──────────────────────────
cm = A.app.test_client()
with cm.session_transaction() as s:
    s['logged_in'] = True
    s['role'] = 'mod'
    s['username'] = 'moder'
r = cm.post(f'/api/guild/{GID}/ladder/add', json={'count': 8, 'action': 'mute',
                                                  'duration': 1, 'unit': 'minutes'})
check(r.status_code == 403, 'ladder/add для mod → 403', f'→ {r.status_code}')
r = cm.get('/bulk-actions')
check(r.status_code in (302, 403), 'bulk-actions для mod недоступна', f'→ {r.status_code}')

# ── 7. «До буквы»: нет турецких/кракозябрных хвостов ──────────────────
BAD_WORDS = ['Belirli', 'dosya', 'girdilerini', 'etmeden', 'sekilde', 'yazma',
             'toplu', 'Cevab', 'gercek', 'saklamak', 'Tahmini', 'kadar badd',
             'dюшю', 'gerчek', 'response\'lar']
for fn in ('web/_store.py', 'web/app.py', 'web/routes/_common.py',
           'web/routes/backup_restore.py', 'web/sentiment_analyzer.py',
           'web/deepseek_scraper.py'):
    text = open(os.path.join(ROOT, fn), encoding='utf-8').read()
    hit = [w for w in BAD_WORDS if w in text]
    check(not hit, f'{fn} без турецких хвостов', f'найдено: {hit}')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
