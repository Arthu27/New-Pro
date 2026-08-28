# -*- coding: utf-8 -*-
"""Имена вместо ID — везде: варны, риски, субъекты, амнистия, журнал.

Запуск: python3 tests/test_names_everywhere.py
"""
import json
import os
import sys
import tempfile
from datetime import datetime, timezone

_TMP = tempfile.mkdtemp(prefix='hakumo_names_')
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
NOW = datetime.now(timezone.utc).isoformat()

# данные: карта имён + варны + аудит + шаги варнов
with open('data/member_names_%s.json' % GID, 'w', encoding='utf-8') as f:
    json.dump({
        '111222333444555666': 'НочнойФлудер',
        '222333444555666777': 'Спамер228',
    }, f, ensure_ascii=False)
with open('data/warnings.json', 'w', encoding='utf-8') as f:
    json.dump({GID: {
        '111222333444555666': [{'reason': 'флуд', 'moderator': 'lina.mod', 'timestamp': NOW}],
        '222333444555666777': [{'reason': 'спам', 'moderator': 'sonya.staff', 'timestamp': NOW},
                               {'reason': 'спам 2', 'moderator': 'sonya.staff', 'timestamp': NOW}],
    }}, f, ensure_ascii=False)
with open('data/audit_log.json', 'w', encoding='utf-8') as f:
    json.dump({GID: [{'action': 'warn', 'user_name': 'из-аудита',
                      'mod_name': 'artem.mods', 'timestamp': NOW}]}, f, ensure_ascii=False)
with open('data/warn_config_%s.json' % GID, 'w', encoding='utf-8') as f:
    json.dump({'steps': [{'count': 3, 'action': 'mute', 'action_name': 'Мут'}]}, f, ensure_ascii=False)

from web.app import app as flask_app  # noqa: E402

client = flask_app.test_client()
with client.session_transaction() as s:
    s['logged_in'] = True
    s['username'] = 'owner'
    s['role'] = 'owner'

print('== /api/warnings ==')
r = client.get('/api/warnings')
d = r.get_json()
check(r.status_code == 200 and isinstance(d, list) and len(d) == 3,
      f'варны отдаются (получено {len(d) if isinstance(d, list) else "?"})')
by_uid = {w['user_id']: w for w in d}
check(by_uid['111222333444555666']['user_name'] == 'НочнойФлудер',
      f"варны: имя из карты ({by_uid['111222333444555666'].get('user_name')})")
check(by_uid['222333444555666777']['user_name'] == 'Спамер228',
      'варны: имя у каждого участника')

print('== /api/guild/<gid>/mod-control/overview ==')
r = client.get(f'/api/guild/{GID}/mod-control/overview')
d = r.get_json()
risk = d.get('risk', {})
items = risk.get('items', [])
check(r.status_code == 200 and isinstance(items, list),
      f'обзор мод-контроля отдаётся (risk.items={len(items)})')
if items:
    by_uid = {it['user_id']: it for it in items}
    check(by_uid.get('111222333444555666', {}).get('name') == 'НочнойФлудер',
          f"риски: имя из карты ({by_uid.get('111222333444555666', {}).get('name')})")

print('== /api/guild/<gid>/mod-insights/overview ==')
r = client.get(f'/api/guild/{GID}/mod-insights/overview')
d = r.get_json()
subjects = (d.get('subjects') or {}).get('items', [])
check(r.status_code == 200 and isinstance(subjects, list),
      f'субъекты отдаются (items={len(subjects)})')
if subjects:
    by_uid = {it['user_id']: it for it in subjects}
    check(by_uid.get('111222333444555666', {}).get('name') == 'НочнойФлудер',
          f"субъекты: имя из карты ({by_uid.get('111222333444555666', {}).get('name')})")

print('== /api/logs ==')
r = client.get('/api/logs')
d = r.get_json()
# действия отдаются по-русски (audit_labels): warn → «Предупреждение»
warn = next((e for e in d if e.get('action', '').lower() == 'предупреждение'), None)
check(warn is not None and warn.get('user_name') == 'из-аудита',
      'журнал: имя из аудита сохраняется (не перетирается картой)')

print('== BOT_SLIM: AI-чат включён ==')
from cogs_policy import select_cog_files, SLIM_COGS  # noqa: E402
check('ai_chat.py' in SLIM_COGS, 'AI-чат входит в профиль SLIM')
enabled, gone = select_cog_files(['ai_chat.py', 'economy_cog.py'], slim=True)
check('ai_chat.py' in enabled and 'economy_cog.py' in gone,
      'BOT_SLIM: ai_chat грузится, экономика — нет')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(0 if FAIL == 0 else 1)
