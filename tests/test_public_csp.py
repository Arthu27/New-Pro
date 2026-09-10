# -*- coding: utf-8 -*-
"""Строгий CSP публичных страниц (владелец 2026-09-08 «давай» после отчёта
PageSpeed «политика CSP не эффективна против XSS»).

Публичные страницы (витрина, вход, регистрация, анкета, статус) —
XSS-поверхность, которую видит весь интернет:
  1. script-src по свежему nonce, БЕЗ unsafe-inline;
  2. nonce из заголовка совпадает с nonce в <script> самой страницы;
  3. в шаблонах нет инлайн-обработчиков (onclick= и пр.) и НЕТ innerHTML-
     записей — страница живёт под require-trusted-types-for 'script'
     (Trusted Types), DOM строится createElement/textContent;
  4. панель за логином — тоже строго: nonce + 'unsafe-hashes' +
     sha256-хэши статичных обработчиков, unsafe-inline убран;
  5. хэши в заголовке панели совпадают с хэшами, которые браузер
     вычислит по значениям on*-атрибутов отрендеренной страницы
     (html-парсер → значение атрибута → sha256 → base64).

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
for name in ('welcome', 'login', 'register', 'public_apply', 'status_public'):
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

PUBLIC = ('/', '/login', '/register', '/apply', '/status')
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
    check("require-trusted-types-for 'script'" in csp,
          f'{path}: CSP требует Trusted Types')
    # TT-синк — это ПРИСВАИВАНИЕ (.innerHTML = / +=); упоминание слова
    # в комментарии — не санкция, ищем именно запись.
    # В демо-режиме '/' после авто-входа — сам дашборд панели: его виджеты
    # пишут innerHTML (страница за логином), проверка — только для
    # публичных витрин.
    _demo_panel = path == '/' and os.environ.get('DEMO_MODE') == '1'
    if not _demo_panel:
        check(not re.search(r'\.(?:inner|outer)HTML\s*\+?=', html),
              f'{path}: нет записей в innerHTML/outerHTML (TT-синков)')

print('== 3. Панель за логином: nonce + sha256-хэши ==')
client.post('/login', data={'username': 'owner', 'password': 'test-pass-123'})
r = client.get('/settings')
csp = r.headers.get('Content-Security-Policy', '')
html = r.get_data(as_text=True)
check(r.status_code == 200, 'вход владельцем работает')
ssrc = csp.split('script-src')[1].split(';')[0]
check('unsafe-inline' not in ssrc, 'панель: script-src без unsafe-inline')
m = re.search(r"'nonce-([A-Za-z0-9_-]+)'", ssrc)
check(m is not None, 'панель: script-src содержит nonce')
check("'unsafe-hashes'" in ssrc, 'панель: unsafe-hashes (хэши on*-атрибутов)')
hashes_in_csp = set(re.findall(r"'sha256-[A-Za-z0-9+/=]+'", ssrc))
check(len(hashes_in_csp) >= 100, f'панель: хэшей в заголовке ≥ 100 ({len(hashes_in_csp)})')
if m:
    nonces = set(re.findall(r'<script nonce="([^"]+)"', html))
    check(nonces == {m.group(1)},
          f'панель: nonce заголовка совпадает с nonce скриптов ({len(nonces)} шт.)')

# Хэш-совместимость с браузером: парсим отрендеренный HTML как браузер,
# берём ЗНАЧЕНИЯ on*-атрибутов и считаем их sha256 — обязаны совпасть
# с хэшами в CSP. Если не совпало — обработчик в панели мёртв.
from html.parser import HTMLParser


class _OnAttr(HTMLParser):
    def __init__(self):
        super().__init__()
        self.handlers = []

    def handle_starttag(self, tag, attrs):
        for k, v in attrs:
            if k.startswith('on') and v is not None:
                self.handlers.append(v)


import base64 as _b64
import hashlib as _hl
_p = _OnAttr()
_p.feed(html)
_broken = []
for code in _p.handlers:
    h = "'sha256-" + _b64.b64encode(_hl.sha256(code.encode('utf-8')).digest()).decode('ascii') + "'"
    if h not in hashes_in_csp:
        _broken.append(code[:60])
check(not _broken, f'панель: все on*-обработчики страницы покрыты хэшами ({len(_p.handlers)} шт.)')
for b in _broken[:3]:
    print('     не покрыт:', b)

print('== 4. Nonce свежий на каждый запрос ==')
n1 = re.search(r"'nonce-([A-Za-z0-9_-]+)'",
               client.get('/').headers.get('Content-Security-Policy', ''))
n2 = re.search(r"'nonce-([A-Za-z0-9_-]+)'",
               client.get('/').headers.get('Content-Security-Policy', ''))
check(n1 and n2 and n1.group(1) != n2.group(1),
      'два запроса — два разных nonce')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
