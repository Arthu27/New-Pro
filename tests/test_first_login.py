# -*- coding: utf-8 -*-
"""Первый вход в панель БЕЗ принуждения (аудит: пожелание владельца).

Сценарий: PANEL_PASSWORD не задан → бот генерирует надёжный пароль, пишет
его в data/panel_credentials.txt, owner входит и СРАЗУ попадает в панель —
никакой форс-смены пароля и никакой 2FA. Смена пароля — по желанию через
/change-password, работает и сохраняется постоянно.

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
print('== старт: пароль сгенерирован, никаких флагов принуждения ==')
import web.app as wa  # noqa: E402

JSON_PATH = 'data/panel_credentials.json'
TXT_PATH = 'data/panel_credentials.txt'

check(os.path.exists(JSON_PATH), 'panel_credentials.json создан при старте')
rec = json.load(open(JSON_PATH, encoding='utf-8'))
check(rec.get('user') == 'owner', 'json: user=owner')
check('must_change_password' not in rec, 'json: флага must_change_password НЕТ')
check('totp_secret' not in rec, 'json: реликта totp_secret НЕТ')
check(str(rec.get('password_hash', '')).startswith('scrypt:'),
      'json: пароль хранится scrypt-хэшем, не plaintext')
check(os.path.exists(TXT_PATH), 'txt-подсказка сгенерирована')

gen_pw = None
for line in open(TXT_PATH, encoding='utf-8'):
    if line.startswith('Пароль: '):
        gen_pw = line.split('Пароль: ', 1)[1].strip()
check(bool(gen_pw) and len(gen_pw) >= 12, 'txt: сгенерированный пароль прочитан')
check(gen_pw not in json.dumps(rec), 'json: plaintext-пароля в записи НЕТ')
check(not hasattr(wa, 'owner_must_change_password'),
      'хелпер owner_must_change_password удалён из кода')
check(not hasattr(wa, 'set_must_change_password'),
      'хелпер set_must_change_password удалён из кода')
check(not hasattr(wa, '_owner_using_default_pw'),
      'реликт _owner_using_default_pw удалён')
check(not hasattr(wa, 'PENDING_2FA') and not hasattr(wa, '_require_2fa'),
      'машинерия 2FA (PENDING_2FA/_require_2fa) удалена')

# ═══ 2. Логин → сразу в панель, без прослоек ══════════════════════════
print('== логин: сразу в панель ==')
client = wa.app.test_client()

r = client.post('/login', data={'username': 'owner', 'password': 'не-верный'})
loc = r.headers.get('Location', '')
check(r.status_code == 200 and 'Неверное' in r.get_data(as_text=True),
      'неверный пароль: ошибка на странице логина')

r = client.post('/login', data={'username': 'owner', 'password': gen_pw})
loc = r.headers.get('Location', '')
check(r.status_code == 302 and 'change-password' not in loc and '2fa' not in loc.lower(),
      'верный пароль → сразу в панель (НЕ на смену пароля, НЕ на 2FA)')

r = client.get('/')
check(r.status_code == 200, '/ открывается сразу после входа')
r = client.get('/dashboard')
check(r.status_code == 200, '/dashboard открыт — guard отсутствует')
r = client.get('/api/todo', headers={'Accept': 'application/json'})
check(r.status_code != 403, 'API не отвечает 403-заглушкой')

r = client.get('/change-password')
page = r.get_data(as_text=True)
check(r.status_code == 200 and 'первый вход' not in page.lower()
      and 'MUST_CHANGE' not in page,
      '/change-password доступен по желанию, без баннера принуждения')
check('totp' not in page.lower() and '2FA' not in page,
      'на странице нет UI двухфакторной защиты')

# ═══ 3. Смена пароля по желанию — работает и сохраняется ═══════════════
print('== смена пароля по желанию ==')
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
check('must_change_password' not in rec2, 'json: после смены флага по-прежнему нет')
check(wa._pw_matches(rec2.get('password_hash'), 'newsecret123'),
      'json: новый хэш матчит новый пароль')
check('newsecret123' not in rec2.get('password_hash', ''),
      'json: новый пароль не лежит открыто')
check(not os.path.exists(TXT_PATH), 'txt-подсказка удалена (протухший пароль не болтается)')
check(wa._pw_matches(wa.USERS['owner']['password_hash'], 'newsecret123'),
      'USERS[owner] обновлён в рантайме (без рестарта)')

client2 = wa.app.test_client()
r = client2.post('/login', data={'username': 'owner', 'password': 'newsecret123'})
check(r.status_code == 302 and 'change-password' not in r.headers.get('Location', ''),
      'повторный вход новым паролем → сразу в панель')

# ═══ 4. Member-ветка: старый plaintext → scrypt при смене ══════════════
print('== member: смена пароля хэшируется ==')
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
