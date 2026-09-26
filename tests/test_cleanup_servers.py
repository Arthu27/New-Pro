# -*- coding: utf-8 -*-
"""Чистка «лишних» серверов: остаются только данные MAIN_GUILD_ID.

Если бот побывал на чужом/тестовом сервере (или демо-посев записал свой
сервер-заглушку), в data/ остаются их записи — и Журнал модерации их
показывал. scripts/cleanup_servers.py должен вычищать ВСЕ хранилища:
журналы, кэш аудита, курсор синка, варны, mod_data, staff_apps, файлы
вида *_<GID>.json и строки sqlite — а данные главного сервера не трогать.

Запуск: python3 tests/test_cleanup_servers.py
"""
import json
import os
import sqlite3
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix='hakumo_cleanup_servers_')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import cleanup_servers as cs  # noqa: E402

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


KEEP = '111222333444555666'
FOREIGN = '999888777666555444'
DEMO = '987654321098765432'

cs.DATA = TMP
data = TMP


def w(name, payload):
    with open(os.path.join(data, name), 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False)


# ── фикстуры: на каждый вид хранилища — и главный, и два «лишних» ─────────
w('audit_log.json', {
    KEEP: [{'action': 'Бан', 'reason': 'свой'}],
    FOREIGN: [{'action': 'bot_add', 'reason': 'чужой'}]})
w('discord_audit_cache.json', {
    KEEP: [{'action': 'Мут'}], FOREIGN: [{'action': 'kick'}], DEMO: [{'action': 'ban'}]})
w('audit_seen.json', {KEEP: '123', FOREIGN: '456'})
w('warnings.json', {KEEP: {'42': [{'reason': 'свой варн'}]},
                    FOREIGN: {'43': [{'reason': 'чужой варн'}]}})
w('mod_data.json', {'cases': {KEEP: [{'action': 'mute'}], FOREIGN: [{'action': 'ban'}]},
                    'case': {KEEP: [{'action': 'mute'}], FOREIGN: [{'action': 'ban'}]},
                    'watchlist': {KEEP: ['7']}})
w('staff_apps.json', {
    'app-1': {'app_id': 'app-1', 'guild_id': KEEP, 'display_name': 'свой'},
    'app-2': {'app_id': 'app-2', 'guild_id': FOREIGN, 'display_name': 'чужой'}})
w('night_summary.json', {KEEP: {'enabled': True}, FOREIGN: {'enabled': False}})
w(f'xp_{KEEP}.json', {'1': {'xp': 10}})
w(f'xp_{FOREIGN}.json', {'2': {'xp': 20}})
w(f'guardian_{DEMO}.json', {'incidents': []})
w('onboarding_state.json', {'plain': True})  # без серверных ключей — не трогаем

db_path = os.path.join(data, 'bot.db')
con = sqlite3.connect(db_path)
con.execute('CREATE TABLE guild_data (namespace TEXT, guild_id INTEGER, '
            'key TEXT, value TEXT, updated_at TEXT)')
con.executemany('INSERT INTO guild_data (namespace, guild_id, key, value) '
                'VALUES (?, ?, ?, ?)',
                [('welcome_pro', int(KEEP), 'settings', '{}'),
                 ('welcome_pro', int(FOREIGN), 'settings', '{}'),
                 ('mod_digest', int(DEMO), 'settings', '{}')])
con.commit()
con.close()

print('== plan: видит все виды «лишнего» и не предлагает главное ==')
actions = cs.plan(KEEP)
desc = '\n'.join(d for _k, _t, d in actions)
check(any('xp_' + FOREIGN in d for d in desc.splitlines()),
      'файл *_<чужойGID>.json предложен к удалению')
check('xp_' + KEEP not in desc,
      'файл главного сервера не предлагается')
for frag in ('audit_log.json', 'discord_audit_cache.json', 'audit_seen.json',
             'warnings.json', 'mod_data.json', 'staff_apps.json',
             'night_summary.json', 'guild_data'):
    check(frag in desc, f'план покрывает {frag}')
check('свой варн' not in desc and "'action': 'Бан'" not in desc,
      'данные главного сервера в плане не упоминаются')

print('== apply: лишнее вычищено, главное цело ==')
report = cs.apply_plan(actions)
check(not report['errors'], 'без ошибок применения', f"{report['errors']}")


def r(name):
    with open(os.path.join(data, name), encoding='utf-8') as f:
        return json.load(f)


al = r('audit_log.json')
check(KEEP in al and FOREIGN not in al, 'audit_log: только главный сервер')
cache = r('discord_audit_cache.json')
check(KEEP in cache and FOREIGN not in cache and DEMO not in cache,
      'discord_audit_cache: чужой и демо-GID удалены, главный цел')
seen = r('audit_seen.json')
check(KEEP in seen and FOREIGN not in seen,
      'audit_seen: курсор чужого сервера снят')
warn = r('warnings.json')
check(KEEP in warn and FOREIGN not in warn and warn[KEEP]['42'],
      'warnings: чужие варны убраны, свои на месте')
md = r('mod_data.json')
check(KEEP in md['case'] and FOREIGN not in md['case']
      and KEEP in md['cases'] and FOREIGN not in md['cases'] and md.get('watchlist'),
      'mod_data: оба журнала (case и cases) почищены, соседние секции целы')
apps = r('staff_apps.json')
check('app-1' in apps and 'app-2' not in apps,
      'staff_apps: чужая заявка удалена по полю guild_id, своя осталась')
ns = r('night_summary.json')
check(KEEP in ns and FOREIGN not in ns, 'night_summary: только главный')
check(not os.path.exists(os.path.join(data, f'xp_{FOREIGN}.json'))
      and os.path.exists(os.path.join(data, f'xp_{KEEP}.json'))
      and not os.path.exists(os.path.join(data, f'guardian_{DEMO}.json')),
      'файлы чужих/демо-серверов удалены, файл главного цел')
check(r('onboarding_state.json') == {'plain': True},
      'файл без серверных ключей не тронут')

con = sqlite3.connect(db_path)
gids = {str(row[0]) for row in con.execute('SELECT DISTINCT guild_id FROM guild_data')}
con.close()
check(gids == {KEEP}, 'sqlite: строки только главного сервера', f'{gids}')

print('== keep_gid: MAIN_GUILD_ID без .env не выдумывается ==')
check(cs.keep_gid() in ('', os.getenv('MAIN_GUILD_ID', '')) or cs.keep_gid().isdigit(),
      'keep_gid отдаёт строку окружения/конфига или пусто (без фейка)')

print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
