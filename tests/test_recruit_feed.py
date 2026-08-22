# -*- coding: utf-8 -*-
"""Набор команды (/staff-apps) и «Последние действия» центра модерации.

Запуск: python3 tests/test_recruit_feed.py
"""
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='aether_recruit_')
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


# ═══ 1. Набор команды: шаблон ═══════════════════════════════════════════
print('== набор команды (/staff-apps) ==')
sa = open(os.path.join(ROOT, 'web', 'templates', 'staff_apps.html'), encoding='utf-8').read()
check('Посмотреть' in sa and 'sa-open' in sa,
      'кнопка «Посмотреть» с классом sa-open')
check("closest('.sa-open')" in sa and "closest('.sa-card')" in sa,
      'делегирование на document: кнопка и карточка открывают анкету')
check('data-app-key' in sa and 'tabindex="0"' in sa and 'role="button"' in sa,
      'карточка — кликабельная (data-app-key, tabindex, role)')
check('saSearch' in sa and 'searchQuery' in sa,
      'поиск по имени/должности')
check('modal-review' in sa and 'modal-extra' in sa and 'modal-av' in sa,
      'модалка: инфо о решении, доп. поле и аватар')
check('style="' not in sa and 'prompt(' not in sa and '&times;' not in sa,
      'без инлайн-стилей, prompt() и сырого ×')
check('_appsFp' in sa and 'setLiveRefresh' in sa,
      'тихое живое обновление списка')

# ═══ 2. Центр модерации: лента последних действий ══════════════════════
print('== последние действия (мод-центр) ==')
mc = open(os.path.join(ROOT, 'web', 'templates', 'mod_center.html'), encoding='utf-8').read()
check('mc-feed-panel' in mc and 'grid-column: 1 / -1' in mc,
      'лента полноширинная — нет пустой колонки рядом')
check('mc-feed-item' in mc and 'mc-feed-ico' in mc and 'mc-feed-reason' in mc,
      'строки ленты: иконка действия + причина')
check('mcFeedCount' in mc,
      'счётчик событий в шапке ленты')
check('logs.slice(0, 10)' in mc,
      'топ-10 журнала, без перегруза')

# ═══ 3. Живые API ═══════════════════════════════════════════════════════
print('== живые API ==')
from web.app import app as flask_app  # noqa: E402

client = flask_app.test_client()
with client.session_transaction() as s:
    s['logged_in'] = True
    s['username'] = 'owner'
    s['role'] = 'owner'

r = client.get('/api/staff-apps')
d = r.get_json()
check(r.status_code == 200 and isinstance(d, list),
      f'/api/staff-apps отдаёт список (получено {len(d) if isinstance(d, list) else "?"})')
check(all(a.get('app_id') or a.get('user_id') for a in d),
      'у каждой заявки есть ключ (app_id/user_id)')

r = client.get('/api/logs')
d = r.get_json()
check(r.status_code == 200 and isinstance(d, list),
      f'/api/logs отдаёт журнал (получено {len(d) if isinstance(d, list) else "?"})')

r = client.get('/staff-apps')
body = r.get_data(as_text=True)
check(r.status_code == 200 and 'Посмотреть' in body and 'sa-card' in body,
      '/staff-apps рендерится с кнопкой «Посмотреть»')
r = client.get('/mod-center')
body = r.get_data(as_text=True)
check(r.status_code == 200 and 'Последние действия' in body and 'mc-feed-panel' in body,
      '/mod-center рендерится с полноширинной лентой')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(0 if FAIL == 0 else 1)
