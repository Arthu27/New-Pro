# -*- coding: utf-8 -*-
"""Домен «не защищён» → чиним протокол на уровне панели.

За туннелем (WEB_BEHIND_PROXY=1):
1. http → жёсткий 301 на https (Cloudflare проксирует и тот, и другой —
   редирект делает сама панель, без кликов в дашборде).
2. Локалка (localhost/127.x) не перекидывается — локальная панель как жила.
3. На https-ответах — HSTS заголовок (браузер запоминает «только https»).
4. Без WEB_BEHIND_PROXY поведение прежнее (никаких редиректов).

Запуск: python3 tests/test_https_hardener.py
"""
import os
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_https_test_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['PANEL_USER'] = 'admin'
os.environ['PANEL_PASSWORD'] = 'test123'
os.environ['MAIN_GUILD_ID'] = '777'
os.environ['DEMO_MODE'] = '1'
os.environ['WEB_BEHIND_PROXY'] = '1'

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


from web.app import app as flask_app
flask_app.config['TESTING'] = True
client = flask_app.test_client()

print('\n[1] http → https за туннелем:')
r = client.get('/', headers={'X-Forwarded-Proto': 'http', 'Host': 'hakumods.xyz'})
check(r.status_code == 301, f'http на домене → 301 (было {r.status_code})')
check((r.headers.get('Location') or '') == 'https://hakumods.xyz/',
      f'Location ведёт на https: {r.headers.get("Location")!r}')

r = client.get('/login', headers={'X-Forwarded-Proto': 'http', 'Host': 'panel.hakumods.xyz'})
check(r.status_code == 301 and (r.headers.get('Location') or '').startswith('https://panel.hakumods.xyz/'),
      'поддомен panel тоже перекидывается')

r = client.get('/', headers={'X-Forwarded-Proto': 'http', 'Host': 'localhost:5001'})
check(r.status_code != 301 or 'https://localhost' not in (r.headers.get('Location') or ''),
      'localhost не трогаем — локальная панель живёт по http')

print('\n[2] https → HSTS:')
r = client.get('/', headers={'X-Forwarded-Proto': 'https', 'Host': 'hakumods.xyz'})
sts = r.headers.get('Strict-Transport-Security') or ''
check('max-age=' in sts, f'HSTS на https-ответе: {sts!r}')
check(r.status_code != 301, 'https не редиректится сам в себя')

print('\n[3] Без туннеля — как раньше:')
os.environ['WEB_BEHIND_PROXY'] = '0'
r = client.get('/', headers={'X-Forwarded-Proto': 'http', 'Host': 'hakumods.xyz'})
check(r.status_code != 301, 'WEB_BEHIND_PROXY выключен → редиректа нет')
check(r.headers.get('Strict-Transport-Security') is None, 'и HSTS не шлём')
os.environ['WEB_BEHIND_PROXY'] = '1'

print('\n[4] Статика-код:')
src = open(os.path.join(ROOT, 'web', 'app.py'), encoding='utf-8').read()
check('def _force_https_public' in src, 'обработчик http→https на месте')
check("'Strict-Transport-Security'" in src, 'HSTS заголовок в коде')

shutil.rmtree(_TMP, ignore_errors=True)
print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
