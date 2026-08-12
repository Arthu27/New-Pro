# -*- coding: utf-8 -*-
"""Форс-смена пароля при первом входе панели (аудит, пункт 7).

Сценарий: PANEL_PASSWORD не задан → бот генерирует пароль, пишет его в
data/panel_credentials.txt и требует сменить при первом входе: все разделы
панели закрыты, пока owner не задаст свой пароль.

Запуск: python3 tests/test_first_login.py
"""
import json
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='aether_firstlogin_test_')
os.chdir(_TMP)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# чистый стенд: пароль НЕ задан ни в env, ни в json — ветка автогенерации
os.environ.pop('PANEL_PASSWORD', None)
os.environ.pop('PANEL_USER', None)

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


# ═══ 1. Автогенерация при старте ═══════════════════════════════════════
print('== старт: пароль сгенерирован, флаг выставлен ==')
import web.app as wa  # noqa: E402

JSON_PATH = 'data/panel_credentials.json'
TXT_PATH = 'data/panel_credentials.txt'

check(os.path.exists(JSON_PATH), 'panel_credentials.json создан при старте')
rec = json.load(open(JSON_PATH, encoding='utf-8'))
check(rec.get('user') == 'owner', 'json: user=owner')
check(rec.get('must_change_password') is True, 'json: must_change_password=True')
check(str(rec.get('password_hash', '')).startswith('scrypt:'),
      'json: пароль хранится scrypt-хэшем, не plaintext')
check(os.path.exists(TXT_PATH), 'txt-подсказка сгенерирована')

gen_pw = None
for line in open(TXT_PATH, encoding='utf-8'):
    if line.startswith('Пароль: '):
        gen_pw = line.split('Пароль: ', 1)[1].strip()
check(bool(gen_pw) and len(gen_pw) >= 12, 'txt: сгенерированный пароль прочитан')
check(gen_pw not in json.dumps(rec), 'json: plaintext-пароля в записи НЕТ')
check(wa.owner_must_change_password() is True, 'owner_must_change_password() → True')
check(wa._owner_using_default_pw is True, '_owner_using_default_pw=True (для совместимости)')

# ═══ 2. Логин → форс-редирект на смену пароля ══════════════════════════
print('== логин и guard ==')
client = wa.app.test_client()

r = client.post('/login', data={'username': 'owner', 'password': 'не-верный'})
loc = r.headers.get('Location', '')
check('change-password' not in loc, 'неверный пароль: входа нет, редиректа на смену тоже')

r = client.post('/login', data={'username': 'owner', 'password': gen_pw})
check(r.status_code == 302 and 'change-password' in r.headers.get('Location', ''),
      'верный пароль → редирект на /change-password')

r = client.get('/')
check(r.status_code == 302 and 'change-password' in r.headers.get('Location', ''),
      'guard: / закрыт до смены пароля')
r = client.get('/dashboard')
check(r.status_code == 302 and 'change-password' in r.headers.get('Location', ''),
      'guard: /dashboard закрыт')
r = client.get('/api/todo')
check(r.status_code == 403 and (r.get_json(silent=True) or {}).get('must_change_password') is True,
      'guard: API → 403 + must_change_password в JSON')

r = client.get('/change-password')
check(r.status_code == 200, 'белый список: /change-password открыт')
check('первый вход' in r.get_data(as_text=True).lower()
      and 'MUST_CHANGE = true' in r.get_data(as_text=True),
      'страница смены показывает баннер первого входа')
r = client.get('/logout')
check(r.status_code in (301, 302), 'белый список: /logout работает')

# ═══ 3. Смена пароля — и панель открывается ════════════════════════════
print('== смена пароля ==')
client = wa.app.test_client()
client.post('/login', data={'username': 'owner', 'password': gen_pw})

r = client.post('/api/user/change-password',
                json={'old_password': 'не-тот', 'new_password': 'newsecret123'})
check((r.get_json(silent=True) or {}).get('error'), 'неверный текущий пароль → error')

r = client.post('/api/user/change-password',
                json={'old_password': gen_pw, 'new_password': '123'})
check((r.get_json(silent=True) or {}).get('error'), 'короткий новый пароль → отказ')

r = client.post('/api/user/change-password',
                json={'old_password': gen_pw, 'new_password': 'newsecret123'})
check((r.get_json(silent=True) or {}).get('success') is True, 'верные данные → success')

rec2 = json.load(open(JSON_PATH, encoding='utf-8'))
check(rec2.get('must_change_password') is False, 'json: флаг снят после смены')
check(wa._pw_matches(rec2.get('password_hash'), 'newsecret123'),
      'json: новый хэш матчит новый пароль')
check('gen_pw' not in rec2.get('password_hash', '')
      and 'newsecret123' not in rec2.get('password_hash', ''),
      'json: ни старый, ни новый пароль не лежат открыто')
check(not os.path.exists(TXT_PATH), 'txt-подсказка удалена (протухший пароль не болтается)')
check(wa.owner_must_change_password() is False, 'owner_must_change_password() → False')
check(wa._pw_matches(wa.USERS['owner']['password_hash'], 'newsecret123'),
      'USERS[owner] обновлён в рантайме (без рестарта)')

r = client.get('/dashboard')
check(r.status_code == 200, 'guard снят: /dashboard открывается')
r = client.get('/api/todo', headers={'Accept': 'application/json'})
check(r.status_code != 403, 'guard снят: API больше не 403')

client2 = wa.app.test_client()
r = client2.post('/login', data={'username': 'owner', 'password': 'newsecret123'})
check(r.status_code == 302 and 'change-password' not in r.headers.get('Location', ''),
      'повторный вход новым паролем → сразу в панель')

# ═══ 4. Member-ветка: старый plaintext → scrypt при смене ══════════════
print('== member: смена пароля теперь хэшируется ==')
os.makedirs('data', exist_ok=True)
json.dump({'777': {'password': 'member_plain_pw', 'role': 'uye',
                   'display_name': 'Tester'}},
          open('data/members.json', 'w', encoding='utf-8'), ensure_ascii=False)
m = wa.app.test_client()
with m.session_transaction() as s:
    s['logged_in'] = True
    s['username'] = '777'
    s['role'] = 'uye'
r = m.post('/api/user/change-password',
           json={'old_password': 'member_plain_pw', 'new_password': 'member_new_pw_7'})
check((r.get_json(silent=True) or {}).get('success') is True,
      'member: верный текущий (plaintext-legacy) → success')
mem = json.load(open('data/members.json', encoding='utf-8'))
check(str(mem['777']['password']).startswith(('scrypt:', 'pbkdf2:')),
      'member: новый пароль записан солёным хэшем')
check(wa._pw_matches(mem['777']['password'], 'member_new_pw_7'),
      'member: новый хэш матчит новый пароль')
r = m.post('/api/user/change-password',
           json={'old_password': 'member_plain_pw', 'new_password': 'whatever123'})
check((r.get_json(silent=True) or {}).get('error'),
      'member: старый пароль больше не проходит')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(0 if FAIL == 0 else 1)
