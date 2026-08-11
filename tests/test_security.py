# -*- coding: utf-8 -*-
"""Регрессионные тесты безопасности (security fixes, ветка arena/019fee4a):

1) Калькулятор !account — безопасный AST-вычислитель (DoS через 9**9**9... закрыт)
2) SECRET_KEY панели не хардкодится (ключ из .env или случайный файл в data/)
3) CSRF-рубеж: write-запросы с чужим Origin отклоняются 403
4) Cookie сессии: HttpOnly + SameSite=Lax
5) Zip Slip: фильтр путей архива автообновления

Запуск: python3 tests/test_security.py
"""
import datetime
import os
import shutil
import sys
import tempfile
import time

# Работаем в временной директории, чтобы генерация data/* не мусорила в репо.
_TMP = tempfile.mkdtemp(prefix='aether_sec_test_')
os.chdir(_TMP)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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


# ─── 1. Калькулятор ──────────────────────────────────────────────────────────
print('== калькулятор: DoS закрыт, обычная математика работает ==')
import ast as _ast

# Подхватываем чистую логику без discord-зависимостей кога.
_src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         'cogs', 'info_tools.py'), encoding='utf-8').read()
_head = _src.split('class InfoTools')[0]
_head = _head.replace('import discord', '').replace('from discord.ext import commands', '')
exec(_head, globals())

_OKS = {'2+2*3': 8, '(2+3)*4': 20, '7%3': 1, '2**50': 1125899906842624}
for expr, want in _OKS.items():
    try:
        got = _calc_eval(_ast.parse(expr, mode='eval'))
        check(got == want, f'считает {expr} = {want}')
    except Exception as ex:
        check(False, f'считает {expr} (упало: {ex})')

_BAD = ['9**9**9', '9**9**9**9**9**9', '2**1000', '999999999*999999999*999999999']
for expr in _BAD:
    t0 = time.time()
    try:
        r = _calc_eval(_ast.parse(expr, mode='eval'))
        check(False, f'блокирует DoS {expr} (вернулось {r})')
    except (ValueError, OverflowError, ZeroDivisionError):
        dt = time.time() - t0
        check(dt < 0.5, f'блокирует DoS {expr} за {dt * 1000:.0f}мс')

# ─── 2. SECRET_KEY не хардкодится ───────────────────────────────────────────
print('== SECRET_KEY: нет известных ключей в коде ==')
KNOWN_LEAKED = {'ultra-secret-key-change-this-in-production',
                'aether-super-secret-key-2026',
                'your-secret-key-here'}

from config import Config  # noqa: E402
check(Config.SECRET_KEY not in KNOWN_LEAKED, 'config.py: нет захардкоженного SECRET_KEY')

os.environ.pop('SECRET_KEY', None)  # имитируем .env без ключа
from web.app import app as _flask_app  # noqa: E402
check(isinstance(_flask_app.secret_key, str) and len(_flask_app.secret_key) >= 32
      and _flask_app.secret_key not in KNOWN_LEAKED,
      'web/app.py: ключ сессий случайный (>=32 символа), не из кода')

# ─── 3. Cookie сессии ────────────────────────────────────────────────────────
print('== cookie сессии панели ==')
check(_flask_app.config.get('SESSION_COOKIE_HTTPONLY') is True, 'SESSION_COOKIE_HTTPONLY=True')
check(_flask_app.config.get('SESSION_COOKIE_SAMESITE') == 'Lax', 'SESSION_COOKIE_SAMESITE=Lax')
check(_flask_app.config.get('SESSION_COOKIE_SECURE') is not True,
      'SESSION_COOKIE_SECURE выключен по умолчанию (иначе сломается http://localhost)')

# ─── 4. CSRF-рубеж (Origin/Referer) ──────────────────────────────────────────
print('== CSRF: чужой Origin отклоняется ==')
client = _flask_app.test_client()
r = client.post('/login', data={'username': 'owner', 'password': 'x'},
                headers={'Origin': 'http://evil.example.com'})
check(r.status_code == 403, f'POST /login с чужим Origin -> 403 (получено {r.status_code})')

r2 = client.post('/login', data={'username': 'owner', 'password': 'x'},
                 headers={'Origin': 'http://localhost'})
check(r2.status_code != 403, f'POST /login со своим Origin -> не 403 (получено {r2.status_code})')

r3 = client.post('/login', data={'username': 'nope', 'password': 'x'})
check(r3.status_code != 403, f'POST /login без Origin (curl) -> не 403 (получено {r3.status_code})')

r4 = client.get('/login')
check(r4.status_code == 200, 'GET /login работает как раньше')

# ─── 5. Zip Slip фильтр автообновления ───────────────────────────────────────
print('== Zip Slip: пути архива фильтруются ==')
from auto_update import _zip_target_ok  # noqa: E402
root = os.path.join(_TMP, 'botdir')
check(_zip_target_ok(root, os.path.join(root, 'main.py')), 'обычный файл разрешён')
check(_zip_target_ok(root, os.path.join(root, 'cogs', 'x.py')), 'вложенный файл разрешён')
check(not _zip_target_ok(root, os.path.join(root, '..', 'evil.py')), '../../ запрещён')
check(not _zip_target_ok(root, os.path.join(root, '..', '..', 'etc', 'passwd')), 'выход за два уровня запрещён')
check(not _zip_target_ok(root, '/etc/passwd'), 'абсолютный путь запрещён')
check(not _zip_target_ok(root, root + '_sneaky' + os.sep + 'x.py'), 'похожая директория-обманка запрещена')

shutil.rmtree(_TMP, ignore_errors=True)
print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
