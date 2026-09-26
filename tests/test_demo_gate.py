# -*- coding: utf-8 -*-
"""Демо-ворота: витрина НЕ впускает никого без пароля (владелец 2026-09-08:
«обычные участники заходят в панель владельца — именно меню владельца»).

Раньше DEMO_MODE=1 автоматически создавал сессию ВЛАДЕЛЬЦА любому, кто
открыл URL панели. Теперь:
  1. аноним и в бою, и в демо видит только welcome/login — ни меню, ни API;
  2. вход в демо — обычная форма /login с паролем панели (PANEL_PASSWORD);
  3. неверный пароль в демо не пускает (и троттлится);
  4. верный пароль даёт ровно одну сессию владельца — витрина жива;
  5. публичные API упираются в rate-limit (429), а не крутятся вечно.

Запуск: python3 tests/test_demo_gate.py
"""

import importlib
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_demo_gate_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['PANEL_USER'] = 'owner'
os.environ['PANEL_PASSWORD'] = 'demo-owner-2026'
os.environ['MAIN_GUILD_ID'] = '777'
os.environ['DEMO_MODE'] = '1'
os.environ['DEMO_FORCE'] = '1'
os.environ['PANEL_LOGIN_CONFIRM'] = '0'

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


print('== Демо-ворота: без пароля никого, с паролем — только владелец ==')
appmod = importlib.import_module('web.app')
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()

# 1. Аноним в демо: никаких страниц, никакого меню, никакого API
r = client.get('/', follow_redirects=False)
check(r.status_code == 200, 'аноним в демо видит welcome, не панель')
with client.session_transaction() as s:
    check(not s.get('logged_in') and not s.get('role'),
          'в сессии анонима нет ни входа, ни роли')

r = client.get('/api/panel/sidebar?path=/')
check(r.status_code in (302, 403), f'сайдбар анониму закрыт ({r.status_code})')
if r.status_code == 200:
    check('bot-settings' not in r.get_data(as_text=True), 'owner-меню не течёт анониму')

r = client.get('/settings', follow_redirects=False)
check(r.status_code in (302, 403), f'страница владельца /settings анониму закрыта ({r.status_code})')

r = client.get('/api/panel-menu', follow_redirects=False)
check(r.status_code in (302, 403), f'API владельца анониму закрыт ({r.status_code})')

# 2. Неверный пароль в демо не пускает
r = client.post('/login', data={'username': 'owner', 'password': 'wrong-pass'},
                follow_redirects=False)
check(r.status_code == 200, 'неверный пароль в демо остаётся на /login')
with client.session_transaction() as s:
    check(not s.get('logged_in'), 'неверный пароль сессию не создаёт')
with client.session_transaction() as s:
    check(not s.get('role'), 'роль не выдаётся за неверный пароль')

# 3. Верный пароль = сессия владельца, витрина жива
client.post('/login', data={'username': 'owner', 'password': 'demo-owner-2026'},
            follow_redirects=False)
with client.session_transaction() as s:
    check(s.get('logged_in') is True and s.get('role') == 'owner',
          'верный пароль в демо даёт сессию владельца')
r = client.get('/api/panel/sidebar?path=/')
check(r.status_code == 200 and '/settings' in r.get_data(as_text=True),
      'вошедший владелец видит своё меню (витрина жива)')
r = client.get('/')
check(r.status_code == 200, 'дашборд владельца в демо открывается')

# 4. Выход закрывает снова
client.get('/logout', follow_redirects=False)
r = client.get('/settings', follow_redirects=False)
check(r.status_code in (302, 403), 'после выхода страницы владельца закрыты')

# 5. Rate-limit публичных API: перебор упирается в 429
# (для скорости теста сжимаем окно лимита — в бою порог из AUTH_RATE_LIMITS)
appmod.AUTH_RATE_LIMITS['public'] = (5, 300)
hammer = appmod.app.test_client()
limited = False
for i in range(8):
    rr = hammer.get('/api/public/guilds')
    if rr.status_code == 429:
        limited = True
        break
check(limited, 'публичный API упирается в 429 при переборе')

# 6. Логин-перебор: после исчерпания лимита — 429
# (троттл-пауза нарастает с каждой ошибкой — занижаем порог, чтобы не спать)
appmod.AUTH_RATE_LIMITS['login'] = (4, 300)
brute = appmod.app.test_client()
blocked = False
for i in range(7):
    rr = brute.post('/login', data={'username': 'owner', 'password': f'bad-{i}'},
                    follow_redirects=False)
    if rr.status_code == 429:
        blocked = True
        break
check(blocked, 'перебор паролей упирается в 429')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
