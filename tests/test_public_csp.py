# -*- coding: utf-8 -*-
"""Строгий CSP публичных страниц (владелец 2026-09-08 «давай» после отчёта
PageSpeed «политика CSP не эффективна против XSS»).

Публичные страницы (витрина, вход, регистрация, анкета) — XSS-поверхность,
которую видит весь интернет. Их script-src работает по nonce:
  1. заголовок CSP содержит свежий nonce и НЕ содержит unsafe-inline;
  2. nonce из заголовка совпадает с nonce в <script> самой страницы;
  3. в шаблонах нет инлайн-обработчиков (onclick= и пр.) — строгий CSP
     их не исполняет, значит они не нужны и вводить в заблуждение не могут;
  4. панель за логином остаётся на прежней политике с unsafe-inline.

Запуск: python3 tests/test_public_csp.py
"""

import importlib
import os
import re
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_public_csp_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['PANEL_USER'] = 'owner'
os.environ['PANEL_PASSWORD'] = 'test-pass-123'
os.environ['MAIN_GUILD_ID'] = '777'
os.environ['DEMO_MODE'] = '1'
os.environ['DEMO_FORCE'] = '1'

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


print('== 1. Шаблоны: инлайн-обработчики и nonce ==')
for name in ('welcome', 'login', 'register', 'public_apply'):
    tpl = open(os.path.join(ROOT, 'web', 'templates', f'{name}.html'),
               encoding='utf-8').read()
    handlers = [h for h in re.findall(r'\son[a-z]+\s*=\s*["\']', tpl)
                if not re.match(r'\son(tent|rols)\b', h)]
    check(not handlers, f'{name}.html: 0 инлайн-обработчиков ({len(handlers)} найдено)')
    scripts = len(re.findall(r'<script(?:\s[^>]*)?>', tpl))
    nonced = tpl.count('nonce="{{ csp_nonce }}"')
    check(scripts > 0 and scripts == nonced,
          f'{name}.html: все <script> с nonce ({nonced}/{scripts})')

print('== 2. Живые страницы: заголовок CSP ==')
appmod = importlib.import_module('web.app')
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()

PUBLIC = ('/', '/login', '/register', '/apply')
for path in PUBLIC:
    r = client.get(path)
    csp = r.headers.get('Content-Security-Policy', '')
    html = r.get_data(as_text=True)
    m = re.search(r"'nonce-([A-Za-z0-9_-]+)'", csp)
    check(r.status_code == 200, f'{path} → 200 ({r.status_code})')
    check(m is not None, f'{path}: CSP содержит nonce')
    check('unsafe-inline' not in csp.split('script-src')[1].split(';')[0],
          f'{path}: script-src без unsafe-inline')
    if m:
        # nonce из заголовка обязан стоять на каждом <script> страницы
        nonces = set(re.findall(r'<script nonce="([^"]+)"', html))
        check(nonces == {m.group(1)},
              f'{path}: nonce заголовка совпадает с nonce скриптов ({len(nonces)} шт.)')

print('== 3. Панель за логином: прежняя политика ==')
client.post('/login', data={'username': 'owner', 'password': 'test-pass-123'})
r = client.get('/settings')
csp = r.headers.get('Content-Security-Policy', '')
check(r.status_code == 200, 'вход владельцем работает')
check("'unsafe-inline'" in csp and 'nonce-' not in csp,
      'панель остаётся на unsafe-inline (миграция поэтапная)')

print('== 4. Nonce свежий на каждый запрос ==')
n1 = re.search(r"'nonce-([A-Za-z0-9_-]+)'",
               client.get('/').headers.get('Content-Security-Policy', ''))
n2 = re.search(r"'nonce-([A-Za-z0-9_-]+)'",
               client.get('/').headers.get('Content-Security-Policy', ''))
check(n1 and n2 and n1.group(1) != n2.group(1),
      'два запроса — два разных nonce')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
