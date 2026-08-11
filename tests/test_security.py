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
# пароль владельца задаём известным из env — иначе он сгенерируется случайный
os.environ['PANEL_PASSWORD'] = 'SecTest!2026'
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

# ─── 6. Пароли: scrypt вместо sha256, совместимость ─────────────────────────
print('== пароли: солёный scrypt, апгрейд старых форматов ==')
from web.app import _hash_pw, _pw_matches, _pw_is_strong, _sha256_legacy  # noqa: E402

h = _hash_pw('MyPass123')
check(_pw_is_strong(h), f'новый хэш солёный ({h.split(":")[0]}), не голый sha256')
check(_pw_matches(h, 'MyPass123'), 'scrypt: верный пароль принят')
check(not _pw_matches(h, 'MyPass124'), 'scrypt: неверный пароль отклонён')
check(h != _hash_pw('MyPass123'), 'соль случайная: хэши одного пароля различаются')
_legacy = _sha256_legacy('oldpass')
check(_pw_matches(_legacy, 'oldpass'), 'старый sha256 принят (обратная совместимость)')
check(_pw_matches('plainpass', 'plainpass'), 'древний plaintext принят (мигрирует при логине)')
check(not _pw_matches('', ''), 'пустой пароль никогда не пускает')
check(not _pw_matches('garbage', None), 'None пароль отклонён')

# ─── 7. TOTP 2FA полный цикл ─────────────────────────────────────────────────
print('== TOTP 2FA: подключение, вход, отключение ==')
import json as _json
from urllib.parse import urlparse, parse_qs

import pyotp

c = _flask_app.test_client()
with c.session_transaction() as s:
    s['logged_in'] = True
    s['username'] = 'owner'
    s['role'] = 'owner'

check(c.get('/api/2fa/totp/status').get_json().get('enabled') is False,
      'TOTP изначально выключен')

begin = c.post('/api/2fa/totp/begin').get_json()
check(begin.get('success') is True and begin.get('qr', '').startswith('data:image/png'),
      'begin: выдан секрет + QR-картинка')
secret = begin['secret']


def wrong_code(real):
    """Код, гарантированно отличающийся от текущего TOTP."""
    return f'{(int(real) + 1) % 1000000:06d}'


r = c.post('/api/2fa/totp/enable', json={'code': wrong_code(pyotp.TOTP(secret).now())})
check(r.get_json().get('success') is not True, 'enable: неверный код отклонён')

r = c.post('/api/2fa/totp/enable', json={'code': pyotp.TOTP(secret).now()})
check(r.get_json().get('success') is True, 'enable: верный код — 2FA включена')
check(c.get('/api/2fa/totp/status').get_json().get('enabled') is True, 'status: включена отражается')

rec = _json.load(open('data/panel_credentials.json', encoding='utf-8'))
check(rec.get('totp_secret') == secret and rec.get('password_hash'),
      'panel_credentials.json: секрет И хэш пароля сохранены вместе')

# Вход теперь требует код
c2 = _flask_app.test_client()
r = c2.post('/login', data={'username': 'owner', 'password': 'SecTest!2026'})
loc = r.headers.get('Location', '')
check(r.status_code == 302 and '/2fa' in loc,
      'логин с включённой 2FA -> редирект на /2fa (пароля мало)')
tok = parse_qs(urlparse(loc).query).get('token', [''])[0]
check(bool(tok), 'токен 2FA выдан')

r = c2.post('/2fa', data={'token': tok, 'code': wrong_code(pyotp.TOTP(secret).now())})
with c2.session_transaction() as s:
    check(not s.get('logged_in'), '2FA: неверный код — сессия НЕ создана')

r = c2.post('/2fa', data={'token': tok, 'code': pyotp.TOTP(secret).now()})
with c2.session_transaction() as s:
    _logged = s.get('logged_in')
check(_logged is True and r.status_code == 302 and '2fa' not in r.headers.get('Location', ''),
      '2FA: верный код — вход выполнен, редирект в панель')

# Смена пароля владельца НЕ должна стирать 2FA (регресс ontoфикса)
r = c.post('/api/change-password', json={'target': 'owner', 'new_password': 'NewPass789'})
check(r.get_json().get('success') is True, 'смена пароля owner — успех')
rec2 = _json.load(open('data/panel_credentials.json', encoding='utf-8'))
check(rec2.get('totp_secret') == secret and _pw_matches(rec2.get('password_hash'), 'NewPass789'),
      'после смены пароля TOTP-секрет сохранился')

# Отключение 2FA валидным кодом
r = c2.post('/api/2fa/totp/disable', json={'code': pyotp.TOTP(secret).now()})
check(r.get_json().get('success') is True, 'disable: с валидным кодом 2FA отключается')

c3 = _flask_app.test_client()
r = c3.post('/login', data={'username': 'owner', 'password': 'NewPass789'})
check(r.status_code == 302 and '/2fa' not in r.headers.get('Location', ''),
      'после отключения 2FA логин идёт сразу в панель')

shutil.rmtree(_TMP, ignore_errors=True)
print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
