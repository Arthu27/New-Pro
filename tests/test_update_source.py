# -*- coding: utf-8 -*-
"""Источник обновлений: владелец сам ставит, ОТКУДА бот качает версии.

Заказ 30.08 «дай, я поставлю, откуда он будет скачивать, название типо»:
репозиторий и ветка задаются в панели (data/update_source.json) и важнее
UPDATE_REPO/UPDATE_BRANCH из .env. Источник один для всех путей
обновления — команды /update (services/self_update) и демона
auto_update.py: раньше демон был прибит гвоздями к .env на старте и мог
качать не оттуда, что владелец думал.

Запуск: python3 tests/test_update_source.py
"""
import json
import os
import sys
import tempfile
import types

_TMP = tempfile.mkdtemp(prefix='hakumo_upsrc_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ.pop('DEMO_MODE', None)
os.environ['SECRET_KEY'] = 'test-secret'
os.environ['MAIN_GUILD_ID'] = '777'
os.environ.pop('UPDATE_REPO', None)
os.environ.pop('UPDATE_BRANCH', None)

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


from services import update_source as US  # noqa: E402
from services import self_update as SU  # noqa: E402


# ═══ A. Приоритет: панель → .env → по умолчанию ══════════════════════════
print('== A. Приоритет источника ==')
check(US.get_repo() == 'Arthu27/New-Pro', 'по умолчанию — Arthu27/New-Pro')
check(US.get_branch() == 'main', 'по умолчанию ветка — main')
os.environ['UPDATE_REPO'] = 'Someone/Else'
os.environ['UPDATE_BRANCH'] = 'env-branch'
check(US.get_repo() == 'Someone/Else' and US.get_branch() == 'env-branch',
      '.env (окружение) работает, файла-тумблера ещё нет')
check(US.source_kind() == '.env / по умолчанию', 'источник честно помечен: .env')

ok, err, (repo, branch) = US.set_source('Arthu27/New-Pro', 'arena/01a04e42-new-pro')
check(ok and repo == 'Arthu27/New-Pro' and branch == 'arena/01a04e42-new-pro',
      'тумблер панели сохраняет репозиторий и ветку')
check(US.get_repo() == 'Arthu27/New-Pro' and US.get_branch() == 'arena/01a04e42-new-pro',
      'ТУМБЛЕР ВАЖНЕЕ .env (в окружении до сих пор Someone/Else)')
check(US.source_kind() == 'панель', 'источник помечен: панель')
with open('data/update_source.json', encoding='utf-8') as fh:
    check(json.load(fh) == {'repo': 'Arthu27/New-Pro',
                            'branch': 'arena/01a04e42-new-pro'},
          'файл-тумблер — валидный JSON')

# валидация: мусорные значения не пролезают
for bad_repo in ('без-слэша', 'a/b c', '../evil', ''):
    ok, err, _ = US.set_source(bad_repo, 'main')
    check(not ok, f'репозиторий «{bad_repo}» отвергнут')
for bad_branch in ('..', '-x', 'a b', ''):
    ok, err, _ = US.set_source('Arthu27/New-Pro', bad_branch)
    check(not ok, f'ветка «{bad_branch}» отвергнута')
check(US.get_branch() == 'arena/01a04e42-new-pro',
      'после отказов сохранённое значение не тронуто')

# битый файл — честный откат к .env
with open('data/update_source.json', 'w', encoding='utf-8') as fh:
    fh.write('{битый')
check(US.get_repo() == 'Someone/Else',
      'битый файл игнорируется → действует .env')


# ═══ B. /update (self_update) качает из выбранного источника ═════════════
print('== B. /update качает из выбранного источника ==')
US.set_source('Foo/Bar', 'my-branch')
check(SU.zip_url() == 'https://codeload.github.com/Foo/Bar/zip/refs/heads/my-branch',
      f'zip_url строится из источника панели ({SU.zip_url()})')

_seen = {}


class _FakeResp:
    status_code = 200

    @staticmethod
    def json():
        return {'sha': 'cafe1234'}


import requests as _real_requests  # noqa: E402
sys.modules['requests'] = types.SimpleNamespace(
    get=lambda url, timeout=10, headers=None: _seen.update(url=url) or _FakeResp())
try:
    sha = SU.remote_sha()
finally:
    sys.modules['requests'] = _real_requests
check(sha == 'cafe1234', 'remote_sha читает ответ GitHub')
check('api.github.com/repos/Foo/Bar/commits/my-branch' in _seen.get('url', ''),
      f'и спрашивает ИМЕННО выбранный источник ({_seen.get("url")})')


# ═══ C. Демон auto_update качает из того же источника ════════════════════
print('== C. Демон auto_update — тот же источник ==')
import auto_update  # noqa: E402
repo_d, branch_d = auto_update._source()
check((repo_d, branch_d) == ('Foo/Bar', 'my-branch'),
      f'_source() демона = источник панели ({repo_d}@{branch_d})')
check('repos/Foo/Bar/commits/my-branch' in auto_update._repo_api(),
      'GitHub API демона — выбранный источник')
check('Foo/Bar/archive/refs/heads/my-branch' in auto_update._zip_url(),
      'ZIP демона — выбранный источник')


# ═══ D. Панель: эндпоинт и карточка ══════════════════════════════════════
print('== D. Панель: /api/bot-settings/update-source ==')
from web.app import app as _flask_app  # noqa: E402

# без сети: remote_sha предсказуем
from services import self_update as _SU2
_SU2.remote_sha = lambda: 'deadbeef00'

client = _flask_app.test_client()


def login_as(role):
    with client.session_transaction() as s:
        s.clear()
        s['logged_in'] = True
        s['username'] = 'UpdSrcTest'
        s['role'] = role


check('/api/bot-settings/update-source' in
      {str(r) for r in _flask_app.url_map.iter_rules()},
      'роут зарегистрирован')

with client.session_transaction() as s:
    s.clear()
check(client.get('/api/bot-settings/update-source').status_code in (302, 401, 403),
      'без логина закрыт')
login_as('mod')
check(client.get('/api/bot-settings/update-source').status_code in (302, 403),
      'модератора не пускают (только владелец)')
login_as('admin')
check(client.get('/api/bot-settings/update-source').status_code in (302, 403),
      'админа не пускают (только владелец — это про обновления бота)')

login_as('owner')
d = client.get('/api/bot-settings/update-source').get_json()
check(d.get('ok') and d.get('repo') == 'Foo/Bar' and d.get('branch') == 'my-branch',
      f'владелец видит источник ({d.get("repo")}@{d.get("branch")})')
check(d.get('local_sha') and d.get('remote_sha') == 'deadbeef00',
      'локальная и свежая версии видны рядом (сразу ясно, отстаёт ли бот)')

r = client.post('/api/bot-settings/update-source',
                json={'repo': 'мусор', 'branch': 'main'})
check(r.status_code == 400 and r.get_json().get('error'),
      'невалидный репозиторий → 400 с объяснением')

r = client.post('/api/bot-settings/update-source',
                json={'repo': 'Arthu27/New-Pro', 'branch': 'arena/01a04e42-new-pro'})
d = r.get_json()
check(r.status_code == 200 and d.get('ok') and d.get('kind') == 'панель',
      'владелец меняет источник из панели (без .env и перезапуска)')
d2 = client.get('/api/bot-settings/update-source').get_json()
check(d2.get('repo') == 'Arthu27/New-Pro'
      and d2.get('branch') == 'arena/01a04e42-new-pro',
      'новый источник сохранён и читается обратно')

page = client.get('/bot-settings').get_data(as_text=True)
for marker in ('bs-upd-repo', 'bs-upd-branch', 'bs-upd-save', 'Источник обновлений',
               'Свежая на GitHub'):
    check(marker in page, f'страница настроек: «{marker}» на месте')

login_as('uye')
r_u = client.get('/bot-settings')
check(r_u.status_code in (302, 403),
      f'участнику страница настроек закрыта целиком ({r_u.status_code})')

print()
print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
