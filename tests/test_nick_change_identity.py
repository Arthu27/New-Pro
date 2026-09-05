# -*- coding: utf-8 -*-
"""Смена ника не дробит человека (владелец, 2026-09-05).

Жалоба: «почему система не видит изменения ников — это если что один и
тот же человек, просто имя поменял» (в аналитике «Сабина» 357 сообщений
на #2, а после смены ника счёт начинался заново).

1) Статистика сообщений пишется с user_id: топы клеятся ПО ЛИЧНОСТИ,
   подпись — свежий ник.
2) Старые записи (без uid) мигрируют по текущим никам участников.
3) Аналитика (топ участников, CSV, детализация канала, «уникальные»,
   неделя) считает людей по uid.
4) Остальные системы (войс, AFK, стафф-статистика) и так по ID — фикс.

Запуск: python3 tests/test_nick_change_identity.py
"""
import json
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_nick_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)

PASS = 0
FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


GID = 1484574976580391004
SABINA_ID = 300000000000000731

print('== 1. record() пишет uid личности ==')
from services import message_stats as MS  # noqa: E402

MS.record(GID, 'Сабина', 'общий', user_id=SABINA_ID)
MS.flush_all()
events = MS.load_full(GID)
check(events and events[0].get('uid') == str(SABINA_ID),
      'запись несёт uid автора', str(events[:1]))
check(events[0]['author'] == 'Сабина', 'ник сохранён как подпись')

print('== 2. Сценарий владельца: «Сабина» сменила ник ==')
msgs = []
# 357 сообщений под старым ником
for i in range(357):
    msgs.append({'author': 'Сабина', 'uid': str(SABINA_ID),
                 'channel': 'общий',
                 'timestamp': f'2026-09-0{1 + i % 4}T10:00:00+00:00'})
# …потом сменила ник и написала ещё
msgs.append({'author': 'SabinaStar', 'uid': str(SABINA_ID),
             'channel': 'общий', 'timestamp': '2026-09-05T12:00:00+00:00'})
msgs.append({'author': 'SabinaStar', 'uid': str(SABINA_ID),
             'channel': 'общий', 'timestamp': '2026-09-05T12:05:00+00:00'})
# другой человек (для честности топа)
for i in range(100):
    msgs.append({'author': 'Кипарис', 'uid': '300000000000000732',
                 'channel': 'общий', 'timestamp': '2026-09-03T09:00:00+00:00'})

top = MS.merge_members_top(msgs, limit=10)
check(len(top) == 2, f'два человека в топе, а не три ({len(top)})')
first = top[0]
check(first['uid'] == str(SABINA_ID) and first['messages'] == 359,
      f'Сабина — одна запись, все {first["messages"]} сообщений слиты',
      str(first))
check(first['name'] == 'SabinaStar',
      'подпись в топе — СВЕЖИЙ ник (после смены)', first['name'])
check(top[1]['name'] == 'Кипарис' and top[1]['messages'] == 100,
      'другой человек не пострадал')

# старые записи без uid — прежнее поведение (группировка по имени)
legacy = [{'author': 'Сабина', 'channel': 'о', 'timestamp': 't'},
          {'author': 'SabinaStar', 'channel': 'о', 'timestamp': 't'}]
top_leg = MS.merge_members_top(legacy, limit=5)
check(len(top_leg) == 2, 'без uid записи не склеиваются (как раньше)')

print('== 3. Миграция: старые записи получают uid по никам ==')


def _resolver(name):
    return {'сабина': 424242, 'кипарис': 424243}.get(name.strip().lower())


legacy2 = [{'author': 'сабина', 'channel': 'о', 'timestamp': 't'},
           {'author': '  Сабина ', 'channel': 'о', 'timestamp': 't'},
           {'author': 'Кипарис', 'channel': 'о', 'timestamp': 't'},
           {'author': 'НеЗнаюКтоТакой', 'channel': 'о', 'timestamp': 't'},
           {'author': 'Сабина', 'uid': '999', 'channel': 'о', 'timestamp': 't'}]
n = MS.attach_uids(legacy2, _resolver)
check(n == 3, f'проставлено 3 uid (без учёта регистра/пробелов, чужой uid не тронут) ({n})')
check(legacy2[0]['uid'] == '424242' and legacy2[1]['uid'] == '424242'
      and legacy2[2]['uid'] == '424243', 'uid верные')
check('uid' not in legacy2[3], 'нераспознанный остался без uid')
check(legacy2[4]['uid'] == '999', 'уже штампованное не перезаписывается')

print('== 4. Аналитика (analytics_plus) считает по личности ==')
import web.routes.analytics_plus as AX  # noqa: E402

import datetime as _dt

evs = []
for m in msgs:
    # как в проде: _parse_ts отдаёт наивные локальные даты
    d = _dt.datetime.fromisoformat(m['timestamp']).astimezone() \
        .replace(tzinfo=None)
    evs.append((m['author'], m['channel'], d, m.get('uid')))
top_a = AX.top_members_counter(evs)
check(top_a[0][0] == 'SabinaStar' and top_a[0][1] == 359,
      f'топ авторов по личности: {top_a[0]}')
check(AX.unique_members(evs) == 2,
      'уникальных авторов 2 (не 3 — ник не второй человек)')
drill = AX.channel_drill(evs, 'общий')
check(drill['top_authors'][0][0] == 'SabinaStar'
      and drill['unique_authors'] == 2,
      'детализация канала тоже по личности')
wk = AX.week_summary(evs, now=_dt.datetime(2026, 9, 6, 13))
check(wk['week_users'] == 2, 'недельная сводка: 2 человека', str(wk))

print('== 5. Живой API аналитики: владелец видит одного человека ==')
import web.app as appmod  # noqa: E402

with open(f'data/message_logs_{GID}.json', 'w', encoding='utf-8') as f:
    json.dump(msgs, f, ensure_ascii=False)
os.environ['MAIN_GUILD_ID'] = str(GID)
os.environ['DB_PATH'] = os.path.abspath('data/bot.db')
appmod.bot_instance = None
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()
with client.session_transaction() as s:
    s.clear()
    s['logged_in'] = True
    s['username'] = 'Owner'
    s['role'] = 'owner'
    s['selected_guild'] = str(GID)
r = client.get(f'/api/guild/{GID}/analytics')
d = r.get_json() or {}
tm = d.get('top_members') or []
check(r.status_code == 200 and len(tm) == 2,
      f'/analytics: {len(tm)} человека в топе', str(tm)[:120])
check(tm and tm[0]['name'] == 'SabinaStar' and tm[0]['messages'] == 359,
      f'топ-1: {tm[0].get("name")} · {tm[0].get("messages")} сообщений — '
      'ник сменился, человек один', str(tm[0]))

print('== 6. Остальные системы и так по ID (фикс не нужен) ==')
vt = open(os.path.join(ROOT, 'cogs', 'voice_tracker.py'), encoding='utf-8').read()
check("voice_all(guild_id).get(str(user_id))" in vt,
      'войс-статистика ключуется user_id')
afk = open(os.path.join(ROOT, 'cogs', 'afk.py'), encoding='utf-8').read()
check('str(user_id)' in afk.replace(' ', ''),
      'AFK ключуется user_id')
ss = open(os.path.join(ROOT, 'cogs', 'staff_stats.py'), encoding='utf-8').read()
check("GuildData('warnings').get(int(guild_id), str(user_id), [])" in ss,
      'стафф-статистика ключуется user_id')
act = open(os.path.join(ROOT, 'cogs', 'activity_stats.py'), encoding='utf-8').read()
check('user_id=getattr(message.author, \'id\', None)' in act,
      'счётчик сообщений передаёт user_id автора')
check('_migrate_legacy_names' in act,
      'старые записи мигрируют при старте бота')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
