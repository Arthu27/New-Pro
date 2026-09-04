# -*- coding: utf-8 -*-
"""Обновление из ПРИВАТНОГО репозитория — работает через токен.

Владелец сделал репозиторий приватным, и /update ответил:
«GitHub ответил 404 — репозиторий или ветка недоступны». Анонимный
codeload/api у приватного репозитория нарочно отдаёт 404. Теперь при
наличии токена (GITHUB_TOKEN / UPDATE_TOKEN / GH_TOKEN в .env):

  * services/self_update.remote_sha()  — API с Authorization;
  * services/self_update.download_zip() — api.github.com/.../zipball
    вместо анонимного codeload (GitHub сам отдаёт 302 на подписанный
    codeload-адрес);
  * auto_update.py (демон) — тот же выбор URL по токену;
  * update.bat — curl/PowerShell с заголовком Authorization.

Без токена поведение не меняется: публичный репозиторий качается
анонимно, а на 404 владелец получает подсказку про GITHUB_TOKEN.

Запуск: python3 tests/test_private_update.py
"""
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_priv_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.pop('DEMO_MODE', None)
os.environ.pop('GITHUB_TOKEN', None)
os.environ.pop('UPDATE_TOKEN', None)
os.environ.pop('GH_TOKEN', None)

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


from services import self_update as SU  # noqa: E402


# ─── токен читается из окружения/.env ───────────────────────────────────
print('== Токен для приватного репозитория ==')
check(SU._update_token() == '', 'без токена — пусто (публичный режим)')
os.environ['GITHUB_TOKEN'] = 'ghp_secret123'
check(SU._update_token() == 'ghp_secret123', 'GITHUB_TOKEN подхватывается')
os.environ.pop('GITHUB_TOKEN')
os.environ['UPDATE_TOKEN'] = 'github_pat_secret'
check(SU._update_token() == 'github_pat_secret',
      'UPDATE_TOKEN подхватывается (отдельный токен обновлений)')
os.environ.pop('UPDATE_TOKEN')
os.environ['GH_TOKEN'] = 'gho_secret'
check(SU._update_token() == 'gho_secret', 'GH_TOKEN подхватывается')
os.environ.pop('GH_TOKEN')

# ─── выбор URL: публичный = codeload, приватный = api zipball ──────────
print('== URL источника ==')
from services import update_source as US  # noqa: E402
US.set_source('Arthu27/New-Pro', 'arena/01a067d8-new-pro')
check(SU.zip_url().endswith('/Arthu27/New-Pro/zip/refs/heads/arena/01a067d8-new-pro'),
      'zip_url() остаётся публичной codeload-ссылкой')
check('api.github.com/repos/Arthu27/New-Pro/zipball/arena/01a067d8-new-pro'
      in SU.zipball_url(), 'zipball_url() — авторизованный api-адрес')
os.environ['GITHUB_TOKEN'] = 'tok'

_seen = {}


class _FakeResp:
    status_code = 200

    def __init__(self, status=200):
        self.status_code = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def iter_content(self, chunk_size=0):
        return iter([b'PK-data'])

    @staticmethod
    def json():
        return {'sha': 'abc1234'}


import requests as _real  # noqa: E402

print('== download_zip с токеном ходит в api.zipball с Authorization ==')
_seen.clear()
import types  # noqa: E402
fake = types.SimpleNamespace()
sys.modules['requests'] = types.SimpleNamespace(
    get=lambda *a, **k: _seen.update(url=a[0], headers=k.get('headers')) or _FakeResp())
try:
    ok, err, path = SU.download_zip(_TMP)
finally:
    sys.modules['requests'] = _real
check(ok, 'скачивание с токеном успешно')
check('api.github.com/repos/Arthu27/New-Pro/zipball/' in _seen.get('url', ''),
      'URL — api.zipball, а не анонимный codeload',
      f'→ {_seen.get("url")}')
check(('Authorization', 'token tok') in (_seen.get('headers') or {}).items()
      or (_seen.get('headers') or {}).get('Authorization') == 'token tok',
      'заголовок Authorization: token … присутствует',
      f'→ {_seen.get("headers")}')

print('== remote_sha с токеном тоже авторизован ==')
_seen.clear()
sys.modules['requests'] = types.SimpleNamespace(
    get=lambda url, timeout=10, headers=None: _seen.update(url=url, headers=headers) or _FakeResp())
try:
    sha = SU.remote_sha()
finally:
    sys.modules['requests'] = _real
check(sha == 'abc1234', 'remote_sha читает ответ')
check('api.github.com/repos/Arthu27/New-Pro/commits/' in _seen.get('url', ''),
      'и спрашивает API выбранного источника')
check((_seen.get('headers') or {}).get('Authorization') == 'token tok',
      'и с Authorization-заголовком (приватный репозиторий)')
os.environ.pop('GITHUB_TOKEN')

print('== 404 без токена — понятная подсказка про GITHUB_TOKEN ==')
_seen.clear()
sys.modules['requests'] = types.SimpleNamespace(
    get=lambda *a, **k: _FakeResp(status=404))
try:
    ok, err, _ = SU.download_zip(_TMP)
finally:
    sys.modules['requests'] = _real
check(not ok and '404' in err and 'GITHUB_TOKEN' in err,
      'ошибка объясняет: репозиторий приватный → добавьте GITHUB_TOKEN',
      f'→ {err}')

print('== 401/403 с токеном — понятная подсказка про доступы ==')
os.environ['GITHUB_TOKEN'] = 'bad-token'
sys.modules['requests'] = types.SimpleNamespace(
    get=lambda *a, **k: _FakeResp(status=403))
try:
    ok, err, _ = SU.download_zip(_TMP)
finally:
    sys.modules['requests'] = _real
check(not ok and '403' in err and 'не подходит' in err,
      'битый токен объясняется без намёков', f'→ {err}')
os.environ.pop('GITHUB_TOKEN')

# ─── демон auto_update.py — тот же выбор URL ────────────────────────────
print('== Демон auto_update (тот же принцип) ==')
import auto_update as AU  # noqa: E402
check('_zipball_url' in dir(AU) and '_update_token' in dir(AU),
      'в демоне есть токен-режим и авторизованный URL')
os.environ['GITHUB_TOKEN'] = 'tok'
check(AU._update_token() == 'tok', 'демон читает токен из окружения')
os.environ.pop('GITHUB_TOKEN')

print('== update.bat умеет заголовок авторизации ==')
bat = open(os.path.join(ROOT, 'update.bat'), encoding='utf-8', newline='').read()
check('api.github.com/repos/%REPO%/zipball/%BRANCH%' in bat,
      'при токене URL переключается на api.zipball')
check('-H "Authorization: token %GH_TOKEN%"' in bat,
      'curl получает заголовок Authorization с токеном')
check('GITHUB_TOKEN=" .env' in bat and 'UPDATE_TOKEN=" .env' in bat,
      'токен читается из .env (GITHUB_TOKEN / UPDATE_TOKEN)')
check('$env:GH_TOKEN' in bat, 'PowerShell-путь тоже использует токен')
check(bat.count('\r\n') > 100, 'файл в CRLF (как требует страж)')
# без токена codeload-ссылка остаётся рабочей
check('codeload.github.com/%REPO%/zip/refs/heads/%BRANCH%' in bat,
      'публичная codeload-ссылка сохранена (режим без токена)')

print()
print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
