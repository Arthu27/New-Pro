# -*- coding: utf-8 -*-
"""Страницы участников/тикетов/ролей: демо-данные и авто-выбор сервера.

Проблемы, которые чинит этот сторож:
- /users показывал «Выберите сервер» (не было авто-выбора);
- /invite-tracker висел на «Загрузка...» (селект без опций);
- /member-notes, /watchlist-panel, /color-roles, чат (DM) были пустыми —
  демо-данные не засеивались;
- /api/guild/<gid>/members возвращал [] без бота.

Запуск: python3 tests/test_pages_data_pro.py
"""
import json
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_pages_data_')
os.environ['DB_PATH'] = os.path.join(_TMP, 'bot.db')
os.environ['DEMO_MODE'] = '1'
os.environ['SECRET_KEY'] = 'test-secret'
os.environ['PANEL_USER'] = 'owner'
os.environ['PANEL_PASSWORD'] = 'preview123'
os.environ['MAIN_GUILD_ID'] = '987654321098765432'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(_TMP)
os.makedirs('data', exist_ok=True)

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


GID = '987654321098765432'

# демо-файлы, как их пишет seed_demo_panel.py
with open('data/member_notes.json', 'w', encoding='utf-8') as f:
    json.dump({'1001': {'name': 'Sonya', 'avatar': '',
                        'notes': [{'id': 'n1', 'note': 'Надёжная', 'author': 'x',
                                   'timestamp': '2026-08-20T12:00:00+00:00'}]}}, f)
with open('data/mod_data.json', 'w', encoding='utf-8') as f:
    json.dump({'watchlist': {GID: {'111222333444555666': {'reason': 'тест',
                                                          'added_by': 'x',
                                                          'timestamp': '2026-08-20T12:00:00+00:00'}}}}, f)
with open('data/color_roles_%s.json' % GID, 'w', encoding='utf-8') as f:
    json.dump([{'name': 'Красный', 'hex': '#ef4444', 'emoji': ''},
               {'name': 'Синий', 'hex': '#3b82f6', 'emoji': ''},
               {'name': 'Зелёный', 'hex': '#22c55e', 'emoji': ''}], f)
with open('data/dm_log.json', 'w', encoding='utf-8') as f:
    json.dump({'111222333444555666': [{'content': 'привет', 'author': 'x',
                                       'bot': False, 'timestamp': '2026-08-20T12:00:00+00:00'}]}, f)
with open('data/invites_%s.json' % GID, 'w', encoding='utf-8') as f:
    json.dump({'leaderboard': [{'name': 'sonya.staff', 'joins': 5, 'leaves': 0}],
               'total_joins': 5, 'total_leaves': 0}, f)
with open('data/member_names_%s.json' % GID, 'w', encoding='utf-8') as f:
    json.dump({'111222333444555666': 'Тестовый'}, f)

# ═══ 1. Демо-ветки API (данные — без живого бота) ══════════════════════
print('== API без бота ==')
from web.app import app as flask_app  # noqa: E402

client = flask_app.test_client()
with client.session_transaction() as s:
    s['logged_in'] = True
    s['username'] = 'owner'
    s['role'] = 'owner'

r = client.get(f'/api/guild/{GID}/members')
d = r.get_json()
check(r.status_code == 200 and isinstance(d, list) and len(d) >= 5,
      f'/api/guild/.../members в демо отдаёт участников (получено {len(d) if isinstance(d, list) else "?"})')
check(any(m.get('name') == 'sonya.staff' for m in d) if isinstance(d, list) else False,
      'в списке есть демо-участники (sonya.staff)')

r = client.get('/api/member-notes')
d = r.get_json()
check(isinstance(d, list) and len(d) >= 1 and all(x.get('notes') for x in d),
      'заметки участников не пустые')

r = client.get(f'/api/watchlist/{GID}')
d = r.get_json()
check(isinstance(d, list) and len(d) >= 1, 'наблюдение не пустое')

r = client.get(f'/api/guild/{GID}/color-roles')
d = r.get_json()
check(isinstance(d, list) and len(d) >= 3, 'палитра цветных ролей не пустая')

r = client.get(f'/api/guild/{GID}/invite-tracker-full')
d = r.get_json()
check(isinstance(d, dict) and d.get('leaderboard'), 'приглашения: лидерборд не пустой')

r = client.get(f'/api/dm/{GID}/recent')
d = r.get_json()
check(isinstance(d, list) and len(d) >= 1, 'DM-разговоры в чате не пустые')

# ═══ 2. Шаблоны: авто-выбор главного сервера ══════════════════════════
print('== авто-выбор сервера ==')
users = open(os.path.join(ROOT, 'web', 'templates', 'users.html'), encoding='utf-8').read()
check("MAIN_GID" in users and "if (!sel.value && MAIN_GID) sel.value = MAIN_GID" in users,
      'users: авто-выбор главного сервера')
check("loadMembers(false)" in users, 'users: список грузится сразу после серверов')
inv = open(os.path.join(ROOT, 'web', 'templates', 'invite_tracker.html'), encoding='utf-8').read()
check("MAIN_GID" in inv and "loadGuilds().then" in inv,
      'invite-tracker: серверы грузятся и выбираются автоматически')
check("appendChild(opt)" in inv, 'invite-tracker: селект наполняется опциями')

# ═══ 3. Демо-сид содержит все новые данные ════════════════════════════
print('== демо-сид ==')
seed = open(os.path.join(ROOT, 'scripts', 'seed_demo_panel.py'), encoding='utf-8').read()
for marker in ('member_notes.json', 'watchlist', 'color_roles_', 'dm_log.json',
               'invite_joins_', 'invites_'):
    check(marker in seed, f'сид пишет {marker}')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(0 if FAIL == 0 else 1)
