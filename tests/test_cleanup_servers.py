# -*- coding: utf-8 -*-
"""Чистка данных о лишних серверах (scripts/cleanup_servers.py).

Сценарий: бот побывал на тестовых серверах — в data\ остались их файлы,
записи в журналах-словарях и строки в базе. Чистка должна оставить
только главный (MAIN_GUILD_ID) и не тронуть его данные.

Запуск: python3 tests/test_cleanup_servers.py
"""
import importlib.util
import json
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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


TMP = tempfile.mkdtemp(prefix='hakumo_cleanup_')

# подменяем DATA скрипта на временную папку
spec = importlib.util.spec_from_file_location(
    'cleanup_servers', os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), 'scripts', 'cleanup_servers.py'))
CS = importlib.util.module_from_spec(spec)
spec.loader.exec_module(CS)
CS.DATA = os.path.join(TMP, 'data')
os.makedirs(CS.DATA, exist_ok=True)

KEEP = '777'
OTHERS = ('888', '424242', '111')

print('== готовим мусор от тестовых серверов ==')
# 1) файлы с суффиксом сервера
files = {
    'message_logs_777.json': [{'author': 'свой', 'channel': 'общий'}],
    'message_logs_888.json': [{'author': 'чужой'}],
    'message_logs_424242.json': [{'author': 'чужой'}],
    'xp_777.json': {'user': 10},
    'xp_888.json': {'user': 3},
    'welcome_777.json': {'text': 'привет'},
    'welcome_424242.json': {'text': 'чужое'},
    'proof_config_777.json': {'required': False},
    'proof_config_111.json': {'required': True},
    'modproof_888.db': b'x',
}
for name, body in files.items():
    mode = 'wb' if isinstance(body, bytes) else 'w'
    with open(os.path.join(CS.DATA, name), mode) as f:
        f.write(body if isinstance(body, (bytes, str)) else json.dumps(body))

# не-серверные файлы — не трогать
with open(os.path.join(CS.DATA, 'staff_apps.json'), 'w', encoding='utf-8') as f:
    json.dump({'42': {'user_id': '42', 'role': 'Хелпер', 'guild_id': KEEP}}, f)
with open(os.path.join(CS.DATA, 'panel_credentials.txt'), 'w') as f:
    f.write('owner / pass')

# 2) журналы-словари с чужими ключами
with open(os.path.join(CS.DATA, 'audit_log.json'), 'w', encoding='utf-8') as f:
    json.dump({KEEP: [{'a': 1}], '888': [{'a': 2}, {'a': 3}],
               '424242': [{'a': 4}]}, f)

# 3) база: строки главного и чужих серверов
con = sqlite3.connect(os.path.join(CS.DATA, 'bot.db'))
con.execute('CREATE TABLE guild_data (key TEXT, guild_id INTEGER, '
            'bucket TEXT, value TEXT, ts TEXT)')
con.execute('CREATE TABLE user_data (key TEXT, user_id INTEGER, '
            'value TEXT, ts TEXT)')
for gid in (777, 888, 424242):
    con.execute('INSERT INTO guild_data VALUES (?,?,?,?,?)',
                (f'cfg{gid}', gid, 'b', '{}', 't'))
con.execute('INSERT INTO user_data VALUES (?,?,?,?)', ('economy', 42, '{}', 't'))
con.commit()
con.close()

print('== план (ничего не меняет) ==')
actions = CS.plan(KEEP)
kinds = [k for k, _t, _d in actions]
files_planned = [a for a in actions if a[0] == 'file']
json_planned = [a for a in actions if a[0] == 'json_key']
db_planned = [a for a in actions if a[0] == 'db_row']
check(len(files_planned) == 6, f'чужих файлов в плане: {len(files_planned)} (ожидалось 6)')
check(len(json_planned) == 2, f'чужих ключей журналов: {len(json_planned)} (ожидалось 2)')
check(len(db_planned) == 2, f'чужих строк базы: {len(db_planned)} (ожидалось 2)')
check(not any('777' in d for _k, _t, d in actions),
      'в плане нет НИЧЕГО про главный сервер')

print('== применяем ==')
report = CS.apply_plan(actions)
check(report['removed'] == 10, f"удалено: {report['removed']} (ожидалось 10)")
check(not report['errors'], 'без ошибок', str(report['errors'])[:120])

left = sorted(os.listdir(CS.DATA))
print('  осталось:', left)
for gone in ('message_logs_888.json', 'message_logs_424242.json', 'xp_888.json',
             'welcome_424242.json', 'proof_config_111.json', 'modproof_888.db'):
    check(gone not in left, f'{gone} удалён')
for stay in ('message_logs_777.json', 'xp_777.json', 'welcome_777.json',
             'proof_config_777.json', 'staff_apps.json', 'panel_credentials.txt',
             'audit_log.json', 'bot.db'):
    check(stay in left, f'{stay} на месте')

audit = json.load(open(os.path.join(CS.DATA, 'audit_log.json'), encoding='utf-8'))
check(list(audit.keys()) == [KEEP], 'журнал: ключи только главного сервера',
      str(list(audit.keys())))
check(audit[KEEP] == [{'a': 1}], 'записи главного сервера целы')

con = sqlite3.connect(os.path.join(CS.DATA, 'bot.db'))
gids = [str(r[0]) for r in con.execute('SELECT DISTINCT guild_id FROM guild_data')]
users = con.execute('SELECT COUNT(*) FROM user_data').fetchone()[0]
con.close()
check(gids == [KEEP], 'база: строки только главного сервера', str(gids))
check(users == 1, 'пользовательские данные не тронуты')

print('== повторная чистка: нечего находить ==')
check(CS.plan(KEEP) == [], 'повторный план пуст — мусора не осталось')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
