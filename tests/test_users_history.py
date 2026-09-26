# -*- coding: utf-8 -*-
"""Карточка участника /users показывает живую историю модерации.

Багрепорт владельца (2026-09-04): «мне дали мут — нигде не показало, что да
как; даже у того, кто мне дал мут — его нет в списке». Причина: save_case
пишет дела в data/mod_data.json под ключом 'cases', а профиль панели читал
только легаси-ключ 'case' → «История модерации» всегда пустая; плюс имя
модератора не сохранялось — в карточке был голый Discord-ID.

Проверяем API /api/member-profile/<gid>/<uid>:
  • дела читаются из АКТУАЛЬНОГО ключа 'cases' (и из легаси 'case' тоже);
  • у пострадавшего видно наказание с именем выдавшего (не ID);
  • у модератора видны дела, которые он ВЫДАЛ (dir='out');
  • дедуп: дело, попавшее в оба ключа, не задваивается.
"""
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TMP = tempfile.mkdtemp(prefix='users_history_test_')
os.chdir(_TMP)
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)

_src = os.path.join(ROOT, 'data')
if os.path.isdir(_src):
    for fn in os.listdir(_src):
        _s, _d = os.path.join(_src, fn), os.path.join('data', fn)
        if os.path.isdir(_s):
            shutil.copytree(_s, _d, dirs_exist_ok=True)
        else:
            shutil.copy(_s, _d)

os.environ['DEMO_MODE'] = '1'
os.environ.setdefault('PANEL_USER', 'admin')
os.environ.setdefault('PANEL_PASSWORD', 'test123')
os.environ['MAIN_GUILD_ID'] = '777'
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')

PASS = FAIL = 0
GID, VICTIM, MOD = '777', '3001', '3002'


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


def seed_cases(md):
    with open('data/mod_data.json', 'w', encoding='utf-8') as f:
        json.dump(md, f)


def seed_names():
    with open(f'data/member_names_{GID}.json', 'w', encoding='utf-8') as f:
        json.dump({MOD: 'Анна'}, f)


def profile(client, uid):
    with client.session_transaction() as s:
        s['logged_in'] = True
        s['username'] = 'admin'
        s['role'] = 'owner'
        s['selected_guild'] = GID
    return client.get(f'/api/member-profile/{GID}/{uid}').get_json()


import web.app as appmod  # noqa: E402

appmod.app.config['TESTING'] = True
client = appmod.app.test_client()
seed_names()

print('== История модерации в карточке /users ==')

# 1. Дело из АКТУАЛЬНОГО ключа 'cases' (так пишет save_case) видно.
seed_cases({'cases': {GID: [
    {'id': 'c1', 'user_id': VICTIM, 'action': 'mute', 'reason': 'спам',
     'mod_id': MOD, 'timestamp': '2026-09-04T10:00:00'}]}})
d = profile(client, VICTIM)
hist = d.get('case') or []
check(len(hist) == 1 and hist[0]['action'] == 'mute' and hist[0]['reason'] == 'спам',
      'дело из ключа "cases" приходит в карточку (раньше: пусто)')

# 2. Имя модератора разрешилось, направление «получил».
check(hist and hist[0].get('mod') == 'Анна' and hist[0].get('dir') == 'in',
      f'в деле имя модератора «Анна», dir=in (получил): {hist[0] if hist else None}')

# 3. У модератора видны дела, которые он ВЫДАЛ.
d2 = profile(client, MOD)
h2 = d2.get('case') or []
check(len(h2) == 1 and h2[0].get('dir') == 'out'
      and h2[0].get('mod') == '3001',
      'у выдавшего мут карточка показывает его дело (dir=out, участник по имени/ID)')

# 4. Легаси-ключ 'case' тоже читается.
seed_cases({'case': {GID: [
    {'id': 'c4', 'user_id': VICTIM, 'action': 'warn', 'reason': 'старое',
     'mod_id': MOD, 'timestamp': '2026-01-01T00:00:00'}]}})
d3 = profile(client, VICTIM)
check(len(d3.get('case') or []) == 1 and d3['case'][0]['action'] == 'warn',
      'легаси-ключ "case" читается, старые записи не пропали')

# 5. Дело в обоих ключах не задваивается.
dupe = [{'id': 'c5', 'user_id': VICTIM, 'action': 'kick', 'reason': 'дубль',
         'mod_id': MOD, 'timestamp': '2026-09-04T13:00:00'}]
seed_cases({'cases': {GID: dupe}, 'case': {GID: dupe}})
d4 = profile(client, VICTIM)
check(len(d4.get('case') or []) == 1, 'дело из обоих ключей не задвоилось')

# 6. /api/logs (журнал панели) тоже видит актуальный ключ.
seed_cases({'cases': {GID: dupe}})
with client.session_transaction() as s:
    s['logged_in'] = True
    s['username'] = 'admin'
    s['role'] = 'owner'
    s['selected_guild'] = GID
r = client.get('/api/logs?page=1&per_page=50')
items = r.get_json()
if isinstance(items, dict):
    items = items.get('items') or items.get('logs') or []
check(any(str(it.get('user_id')) == VICTIM for it in items if isinstance(it, dict)),
      '/api/logs видит дела из ключа "cases"')

print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
