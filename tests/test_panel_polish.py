# -*- coding: utf-8 -*-
"""Полировка панели (пакет заказов владельца, статика):

1. Шапка больше не застревает на «загрузка…» — есть фолбэк «Сервер» + живое имя.
2. WebSocket-клиент молчит за доменом (никаких ws://localhost в шаблонах-статике —
   эта строка ломала «не защищён» и спамила реконнектами).
3. Тактильные анимации кнопок (hover/active) в style.css.
4. Доказательство к наказаниям: поле в UI профиля, payload, ссылка в истории,
   attach в API warn/ban.
5. Кнопка «Выключить всё» (сброс защиты) на месте.
6. Setup-батник: портативные копии конфига/ключа для VDS, чистый ASCII.

Запуск: python3 tests/test_panel_polish.py
"""
import os
import re
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='aether_polish_test_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

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


def read(rel, binary=False):
    mode = 'rb' if binary else 'r'
    kw = {} if binary else {'encoding': 'utf-8'}
    with open(os.path.join(ROOT, rel), mode, **kw) as fh:
        return fh.read()


print('\n[1] Шапка без вечной «загрузка…»:')
base = read('web/templates/base.html')
check('загрузка…' not in base, 'застревающего плейсхолдера нет')
check('sidebarGuildName' in base and "'/api/guilds'" in base,
      'живое имя сервера подтягивается из /api/guilds')

print('\n[2] WebSocket-клиент:')
ws = read('web/static/websocket-client.js')
check('ws://localhost' not in ws, 'нет захардкоженного ws://localhost')
check('isLocal' in ws, 'за доменом клиент молчит (isLocal-гейт)')
check(ws.count('!this.url') >= 2, 'стражи пустого url в connect/reconnect')
check("window.location.protocol === 'https:' ? 'wss:' : 'ws:'" in ws, 'https → wss протокол')

print('\n[3] Анимации кнопок:')
css = read('web/static/style.css')
check('Тактильный отклик кнопок' in css, 'блок анимаций в style.css')
check(':active' in css and 'scale(.96)' in css, 'нажатие сжимает кнопку')
check(':hover' in css and 'translateY(-1px)' in css, 'наведение приподнимает')
check('prefers-reduced-motion' in css, 'уважение reduced-motion')

print('\n[4] Доказательства к наказаниям:')
mp = read('web/templates/member_profile.html')
check('Доказательство — ссылка' in mp, 'промпт доказательства в UI')
check('{ reason: reason, proof: proof }' in mp, 'proof уходит в payload')
check('>доказательство</a>' in mp, 'ссылка-доказательство в истории')
mem = read('web/routes/members.py')
check("d .get ('proof')" in mem, 'API читает proof')
check("proof .startswith (('http://','https://'))" in mem, 'валидируем, что это ссылка')
check("Доказательство: {proof }" in mem, 'proof попадает в DM о бане')
com = read('web/routes/_common.py')
check("'proof': str(w.get('proof') or '')," in com, 'proof проходит в варны панели')
check("'proof': str(c.get('proof') or '')," in com, 'proof проходит в историю дел')

print('\n[5] Кнопка «Выключить всё»:')
sec = read('web/templates/security.html')
check('id="scResetAll"' in sec, 'кнопка в «Контуре защиты»')
check('type="button" class="btn btn-sm btn-danger" id="scResetAll"' in sec
      or 'class="btn btn-sm btn-danger" id="scResetAll"' in sec.replace('\n', ' '),
      'у кнопки type="button"')
check("post('/protection-reset'" in sec, 'UI зовёт живой эндпоинт')
sp = read('web/routes/security_panel.py')
check('def protection_reset_all' in sp, 'protection_reset_all в коде')
check('/api/guild/<gid>/security-center/protection-reset' in sp, 'эндпоинт зарегистрирован')

print('\n[6] Setup-батник (VDS-автономность):')
bat_raw = read('scripts/setup_panel_tunnel.bat', binary=True)
check(all(b < 128 for b in bat_raw), 'ASCII-only — кодировке ломать нечего')
check(b'\r\n' in bat_raw and b'\n' not in bat_raw.replace(b'\r\n', b''),
      'CRLF переносы без lone-LF')
bat = bat_raw.decode('ascii')
check('tunnel-creds.json' in bat, 'портативная копия ключа рядом с ботом')
check('%~dp0config.yml' in bat, 'портативная копия конфига рядом с ботом')

print('\n[7] VDS-режим в боте:')
main = read('main.py')
check('_nt.ensure_binary(scripts_dir)' in main, 'cloudflared докачается сам')
check('_nt.runtime_config(root, cfg)' in main, 'credentials-путь чинится при переезде')
nt = read('services/named_tunnel.py')
check('def ensure_binary' in nt and 'def runtime_config' in nt, 'хелперы на месте')
gi = read('.gitignore')
check('scripts/tunnel-creds.json' in gi, 'ключ туннеля в .gitignore (не утекёт в репо)')

shutil.rmtree(_TMP, ignore_errors=True)
print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
