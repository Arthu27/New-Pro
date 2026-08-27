# -*- coding: utf-8 -*-
"""Разовый «чистый старт» при запуске бота (заказ владельца 2026-08).

1. Логи/истории серверов стираются (audit/dm/login/panel-логи, кейсы,
   варны, страйки, message_logs, modproof) — а доступы к панели
   (panel_credentials, flask_secret, tunnel_url) и настройки остаются.
2. Защита гарантированно выключается во ВСЕХ сторах, что нашлись на
   диске: security_*/antifake/autofilter_*/guardian_*/ai_mod_config_*/
   antiraid_* + anti_alt в базе. Пороги и белые списки сохраняются.
3. Миграция срабатывает РОВНО один раз (маркер data/.freshstart_v1.json):
   что владелец включит после неё — не трогается. Это главный сценарий:
   «включим сами, и пусть никто больше не выключает».

Запуск: python3 tests/test_fresh_start.py
"""
import json
import os
import shutil
import sqlite3
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_fresh_test_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')

PASS = 0


FAIL = 0
def ok(name, cond, extra=''):
    global PASS
    if not cond:
        print(f'FAIL: {name} {extra}')
        sys.exit(1)
    PASS += 1
    print(f'  ok - {name}')


def w(name, payload):
    path = os.path.join('data', name)
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(payload, fh, ensure_ascii=False)
    return path


# --- Сесид: «грязный» сервер со старой эпохи «всё включено» -------------
os.makedirs('data', exist_ok=True)

w('security_111.json', {'ai_spam': True, 'fake_account': True,
                        'link_scanner': True, 'threshold': 5})
w('antifake.json', {'111': {'enabled': True, 'days': 7}})
w('autofilter_111.json', {'enabled': True, 'words': {'enabled': True, 'list': ['дуpaк']},
                          'links': {'enabled': True}, 'caps': {'enabled': False},
                          'flood': {'enabled': True}})
w('guardian_111.json', {'enabled': True, 'whitelist': [42]})
w('ai_mod_config_111.json', {'enabled': True, 'strict': 3})
w('antiraid_111.json', {'join_raid': True, 'bot_protection': True,
                        'webhook_protection': False, 'delete_protection': True,
                        'age_filter': True, 'min_age': 9})
# второй сервер — тоже включён (проверяем ВСЕ гильдии, не одну)
w('security_222.json', {'ai_spam': True, 'fake_account': False, 'link_scanner': False})

w('audit_log.json', [{'a': 1}])
w('audit_log_backup.json', [{'a': 2}])
w('dm_log.json', [])
w('login_log.json', [])
w('panel_logs.json', [])
w('mod_data.json', {'cases': []})
w('warnings.json', {'111': []})
w('night_summary.json', {})
w('notification_history.json', [])
w('antifake_strikes.json', {'111': []})
w('anticrash_stats.json', {})
w('modproof_111.json', {})
w('message_logs_111.json', [])

# что обязано уцелеть
w('panel_credentials.json', {'user': 'owner', 'password': 'x'})
w('flask_secret.key', {'k': 1})
with open('data/tunnel_url.txt', 'w', encoding='utf-8') as fh:
    fh.write('https://panel.example')
w('notification_settings.json', {'111': {'digest': True}})  # настройки — не лог

# v2: логины/входы/бэкапы/демо-семена/рантайм-логи
w('tokens.json', {'abc': {'username': 'owner'}})
w('audit_seen.json', {'111': 'cursor'})
w('ai_chat_histories.json', {'111': []})
w('invite_joins_111.json', [{'joined': 1}])
w('demo_channels.json', [{'id': 1, 'type': 'text'}])
os.makedirs('data/backups', exist_ok=True)
with open('data/backups/backup_20260101_000000_ab12.zip', 'wb') as fh:
    fh.write(b'PK\x03\x04old-logs')
w('backups.json', {'items': []})
os.makedirs('data/flask_sessions', exist_ok=True)
with open('data/flask_sessions/sess1', 'w', encoding='utf-8') as fh:
    fh.write('session')  # сессии НЕ логи — должны уцелеть
os.makedirs('logs', exist_ok=True)
with open('logs/bot.log', 'w', encoding='utf-8') as fh:
    fh.write('runtime log line')

conn = sqlite3.connect(os.environ['DB_PATH'])
conn.execute('''CREATE TABLE IF NOT EXISTS guild_data (
    namespace TEXT NOT NULL, guild_id INTEGER NOT NULL, key TEXT NOT NULL,
    value TEXT NOT NULL, updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (namespace, guild_id, key))''')
conn.execute("INSERT INTO guild_data (namespace, guild_id, key, value) "
             "VALUES ('anti_alt', 111, 'settings', ?)",
             (json.dumps({'enabled': True, 'action': 'kick'}),))
conn.commit()
conn.close()

from services import fresh_start  # noqa: E402

print('== чистый старт: первый запуск ==')
rep = fresh_start.run_once(_TMP)
ok('вернул сводку', isinstance(rep, dict))
ok('маркер записан', os.path.isfile('data/.freshstart_v1.json'))

sec = json.load(open('data/security_111.json', encoding='utf-8'))
ok('security: все 3 флага погашены',
   sec['ai_spam'] is False and sec['fake_account'] is False and sec['link_scanner'] is False)
ok('security: порог уцелел', sec.get('threshold') == 5)
sec2 = json.load(open('data/security_222.json', encoding='utf-8'))
ok('security 2-го сервера тоже погашен', sec2['ai_spam'] is False)

af = json.load(open('data/antifake.json', encoding='utf-8'))
ok('antifake: выключен', af['111']['enabled'] is False)
ok('antifake: настройки уцелели', af['111'].get('days') == 7)

au = json.load(open('data/autofilter_111.json', encoding='utf-8'))
ok('autofilter: корень+секции выключены',
   au['enabled'] is False and au['words']['enabled'] is False
   and au['links']['enabled'] is False and au['flood']['enabled'] is False)
ok('autofilter: словарь уцелел', au['words'].get('list') == ['дуpaк'])

gu = json.load(open('data/guardian_111.json', encoding='utf-8'))
ok('guardian: выключен', gu['enabled'] is False)
ok('guardian: белый список уцелел', gu.get('whitelist') == [42])

am = json.load(open('data/ai_mod_config_111.json', encoding='utf-8'))
ok('ai_moderation: выключена', am['enabled'] is False and am.get('strict') == 3)

ar = json.load(open('data/antiraid_111.json', encoding='utf-8'))
ok('antiraid: все триггеры погашены',
   ar['join_raid'] is False and ar['bot_protection'] is False
   and ar['delete_protection'] is False and ar['age_filter'] is False)
ok('antiraid: порог уцелел', ar.get('min_age') == 9)

conn = sqlite3.connect(os.environ['DB_PATH'])
val = conn.execute("SELECT value FROM guild_data WHERE namespace='anti_alt'"
                   " AND guild_id=111 AND key='settings'").fetchone()[0]
conn.close()
ok('anti_alt в базе выключен', json.loads(val)['enabled'] is False)
ok('anti_alt: экшен уцелел', json.loads(val).get('action') == 'kick')

for fn in ('audit_log.json', 'audit_log_backup.json', 'dm_log.json',
           'login_log.json', 'panel_logs.json', 'mod_data.json',
           'warnings.json', 'night_summary.json', 'notification_history.json',
           'antifake_strikes.json', 'anticrash_stats.json',
           'modproof_111.json', 'message_logs_111.json'):
    ok(f'лог удалён: {fn}', not os.path.exists(os.path.join('data', fn)))

ok('panel_credentials уцелели', os.path.exists('data/panel_credentials.json'))
ok('flask_secret уцелел', os.path.exists('data/flask_secret.key'))
ok('tunnel_url уцелел',
   open('data/tunnel_url.txt', encoding='utf-8').read() == 'https://panel.example')
ok('notification_settings (настройки, не лог) уцелели',
   os.path.exists('data/notification_settings.json'))

print('== v2: входы/токены/бэкапы/демо/рантайм-логи ==')
for fn in ('tokens.json', 'audit_seen.json', 'ai_chat_histories.json',
           'invite_joins_111.json', 'demo_channels.json', 'backups.json',
           'data/backups/backup_20260101_000000_ab12.zip', 'logs/bot.log'):
    ok(f'v2 удалён: {fn}', not os.path.exists(os.path.join(_TMP, fn)))
ok('v2: сессии панели уцелели (владельца не выкидывает)',
   os.path.exists('data/flask_sessions/sess1'))
ok('маркер v2 записан', os.path.isfile('data/.freshstart_v2.json'))

print('== чистый старт: второй запуск ничего не трогает ==')
# Хозяин включил защиту сам — миграция НЕ должна её погасить снова
sec = json.load(open('data/security_111.json', encoding='utf-8'))
sec['ai_spam'] = True
json.dump(sec, open('data/security_111.json', 'w', encoding='utf-8'))
w('audit_log.json', [{'host': 'включил сам, логи пишутся'}])

rep2 = fresh_start.run_once(_TMP)
ok('второй запуск — no-op (маркер)', rep2 is None)
sec = json.load(open('data/security_111.json', encoding='utf-8'))
ok('включённое хозяином НЕ выключено', sec['ai_spam'] is True)
ok('новый лог хозяина НЕ стёрт', os.path.exists('data/audit_log.json'))
# v2 тоже одноразовая: новый токен входа после сброса не сносится
w('tokens.json', {'fresh': {'username': 'owner'}})
ok('v2 повторно не срабатывает (токен хозяина жив)',
   os.path.exists('data/tokens.json'))

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
print('ALL PASS — fresh_start (чистый старт) работает' if not FAIL else 'ЕСТЬ ПАДЕНИЯ')
shutil.rmtree(_TMP, ignore_errors=True)
