# -*- coding: utf-8 -*-
"""Видимость уведомлений/активности, имена в логах, цветные роли,
роли по реакциям, профиль BOT_SLIM.

Запуск: python3 tests/test_visibility_roles_pro.py
"""
import json
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_vis_')
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

# ═══ 1. Видимость: конфиг, API, рендер ═════════════════════════════════
print('== видимость уведомлений и ленты ==')
from web.app import app as flask_app  # noqa: E402

client = flask_app.test_client()
with client.session_transaction() as s:
    s['logged_in'] = True
    s['username'] = 'owner'
    s['role'] = 'owner'

r = client.get('/api/panel/visibility')
d = r.get_json()
check(r.status_code == 200 and d['success']
      and d['visibility']['notifications_min_role'] == 'mod'
      and d['visibility']['activity_min_role'] == 'mod',
      'дефолт: уведомления и лента — модераторы и выше')
r = client.post('/api/panel/visibility', json={
    'notifications_min_role': 'admin', 'activity_min_role': 'uye'})
d = r.get_json()
check(d['visibility']['notifications_min_role'] == 'admin'
      and d['visibility']['activity_min_role'] == 'uye',
      'сохранение минимальных ролей')
r = client.post('/api/panel/visibility', json={'notifications_min_role': 'бред'})
check(r.get_json()['visibility']['notifications_min_role'] == 'admin',
      'битая роль не перетирает сохранённую')

# участник: уведомления min admin — скрыты; лента min uye — видна
with client.session_transaction() as s:
    s['role'] = 'uye'
r = client.get('/api/notifications/poll')
d = r.get_json()
check(r.status_code == 200 and d['notifications'] == [] and d['unread'] == 0,
      'участник: уведомления пусты (min admin)')
r = client.get('/')
body = r.get_data(as_text=True)
check('id="notifBtn"' not in body, 'участник: колокольчик скрыт (min admin)')
check('id="activityBtn"' in body, 'участник: кнопка ленты видна (min uye)')
r = client.get('/api/activity-feed')
check(r.status_code == 200 and isinstance(r.get_json(), dict) and 'items' in r.get_json(),
      'участник: лента отвечает (min uye)')

# поднимем порог ленты до owner — участник теряет ленту
with client.session_transaction() as s:
    s['role'] = 'owner'
r = client.post('/api/panel/visibility', json={'activity_min_role': 'owner'})
check(r.status_code == 200 and r.get_json()['visibility']['activity_min_role'] == 'owner',
      'владелец: порог ленты поднят до owner')
with client.session_transaction() as s:
    s['role'] = 'uye'
r = client.get('/api/activity-feed')
check(r.get_json() == [], 'участник: лента пуста (min owner)')
r = client.get('/')
check('id="activityBtn"' not in r.get_data(as_text=True),
      'участник: кнопка ленты скрыта (min owner)')

# модер при min owner тоже без ленты, владелец — с лентой
with client.session_transaction() as s:
    s['role'] = 'mod'
check('id="activityBtn"' not in client.get('/').get_data(as_text=True),
      'модератор: лента скрыта (min owner)')
with client.session_transaction() as s:
    s['role'] = 'owner'
check('id="activityBtn"' in client.get('/').get_data(as_text=True),
      'владелец: лента видна (min owner)')

# вернуть дефолт
client.post('/api/panel/visibility', json={
    'notifications_min_role': 'mod', 'activity_min_role': 'mod'})

# ═══ 2. Имена в логах вместо ID ═══════════════════════════════════════
print('== имена в логах ==')
import json as _json  # noqa: E402
with open('data/member_names_%s.json' % GID, 'w', encoding='utf-8') as f:
    _json.dump({'111222333444555666': 'НочнойФлудер'}, f)
with open('data/audit_log.json', 'w', encoding='utf-8') as f:
    _json.dump({GID: [
        {'action': 'warn', 'user_name': 'аудит-имя', 'mod_name': 'lina.mod',
         'timestamp': '2026-08-20T12:00:00+00:00'},
        {'action': 'ban', 'user_id': '111222333444555666', 'mod_id': 'artem.mods',
         'timestamp': '2026-08-21T12:00:00+00:00'},
    ]}, f)
with client.session_transaction() as s:
    s['role'] = 'mod'
r = client.get('/api/logs')
d = r.get_json()
# действия отдаются по-русски (audit_labels): ban→«Бан», warn→«Предупреждение»
by_action = {e['action']: e for e in d}
check(by_action['Бан'].get('user_name') == 'НочнойФлудер',
      f"логи: ID резолвится в имя из карты ({by_action['Бан'].get('user_name')})")
check(by_action['Предупреждение'].get('user_name') == 'аудит-имя',
      'логи: явное имя не перетирается')
check(by_action['Бан'].get('mod_name') == 'artem.mods',
      'логи: модератор с именем не трогается')

# ═══ 3. Цветные роли: сохранение + валидация + демо-публикация ═════════
print('== цветные роли ==')
with client.session_transaction() as s:
    s['role'] = 'admin'
r = client.post('/api/guild/%s/color-roles' % GID, json={'colors': [
    {'name': 'Красный', 'hex': '#ff0000', 'emoji': ''},
    {'name': 'Кривой', 'hex': 'нецвет', 'emoji': ''},
    {'name': '', 'hex': '#00ff00', 'emoji': ''},
]})
d = r.get_json()
check(r.status_code == 200 and d['success'] and len(d['colors']) == 1
      and d['colors'][0]['hex'] == '#ff0000',
      f'сохранение: валидный цвет принят, мусор отброшен ({d.get("colors")})')
r = client.get('/api/guild/%s/color-roles' % GID)
check(r.get_json()[0]['name'] == 'Красный', 'палитра читается обратно')
r = client.post('/api/guild/%s/color-roles/publish' % GID, json={
    'channel_id': '1002', 'colors': [{'name': 'Красный', 'hex': '#ff0000', 'emoji': ''}]})
d = r.get_json()
check(r.status_code == 200 and d.get('success') and d.get('demo'),
      'демо-публикация цветных ролей работает без бота')
r = client.post('/api/guild/%s/color-roles/publish' % GID, json={
    'channel_id': '', 'colors': [{'name': 'x', 'hex': '#ff0000'}]})
check(r.status_code == 400, 'публикация без канала — 400')

# ═══ 4. Роли по реакциям — фича удалена (модуль reaction_roles снесён) ═══

# ═══ 5. Профиль BOT_SLIM ══════════════════════════════════════════════
print('== BOT_SLIM ==')
from cogs_policy import select_cog_files, SLIM_COGS  # noqa: E402
files = ['moderation.py', 'reports.py', 'staff_apply.py',
         'voice_tracker.py',
         'ai_chat.py', 'help.py',
         'logs.py', 'impersonation.py']
enabled, gone = select_cog_files(files, slim=True)
sel = set(enabled)
check({'moderation.py', 'reports.py', 'staff_apply.py',
       'voice_tracker.py',
       'help.py', 'logs.py', 'impersonation.py', 'ai_chat.py'} <= sel,
      'BOT_SLIM: модерация, репорты, заявки, войс-статистика, ядро и AI-чат загружены')
import os as _os
check(not _os.path.exists(os.path.join(ROOT, 'cogs', 'music_cog.py'))
      and not _os.path.exists(os.path.join(ROOT, 'cogs', 'voice_commands.py')),
      'BOT_SLIM: файлы музыки (music_cog/voice_commands) физически удалены')

# ═══ 6. Шаблоны ═══════════════════════════════════════════════════════
print('== шаблоны ==')
cr = open(os.path.join(ROOT, 'web', 'templates', 'color_roles.html'), encoding='utf-8').read()
check('cr-card' in cr and 'cr-publish' in cr and 'alert(' not in cr,
      'цветные роли: карточки, публикация, без alert()')
check('confirmAction' in cr and 'savePalette' in cr,
      'цветные роли: подтверждение удаления и автосохранение')
pa = open(os.path.join(ROOT, 'web', 'templates', 'panel_access.html'), encoding='utf-8').read()
check('pv-notif' in pa and 'pv-activity' in pa and '/api/panel/visibility' in pa,
      'доступ: настройка видимости уведомлений и ленты')
base = open(os.path.join(ROOT, 'web', 'templates', 'base.html'), encoding='utf-8').read()
check('vis_notifications' in base and 'vis_activity' in base,
      'base: колокольчик и лента под условной видимостью')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(0 if FAIL == 0 else 1)
