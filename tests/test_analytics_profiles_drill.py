# -*- coding: utf-8 -*-
"""Аналитика: профили активных участников + детализация канала (2026-09-05).

Владелец: «Самые активные участники — тут надо, чтобы ещё профили
показывало» и «Детализация по каналу не работает».

1) Клик по строке топа открывает профиль: активность по каналам,
   последняя активность, варны/дела — личность по uid (смена ника не мешает).
2) Селект «Детализации» больше не умирает при офлайн-боте: каналы с
   данными берутся из статистики сообщений (drill-channels), живой
   список Discord лишь дополняет порядок; счётчик сообщений в подписи.
Запуск: python3 tests/test_analytics_profiles_drill.py
"""
import json
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_an_prof_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['MAIN_GUILD_ID'] = '1484574976580391004'
os.environ['DB_PATH'] = os.path.abspath('data/bot.db')

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
SABINA = 300000000000000731

print('== 1. Чистые функции: каналы и профиль по личности ==')
import web.routes.analytics_plus as AX  # noqa: E402
import datetime as _dt  # noqa: E402


def _ev(author, ch, day, uid):
    return (author, ch, _dt.datetime(2026, 9, day, 12), uid)


evs = [
    _ev('Сабина', 'общий', 1, str(SABINA)),
    _ev('Сабина', 'общий', 2, str(SABINA)),
    _ev('SabinaStar', 'флуд', 5, str(SABINA)),      # сменила ник
    _ev('Кипарис', 'общий', 3, '300000000000000732'),
    _ev('Кипарис', 'мод-лог', 3, '300000000000000732'),
]
chans = AX.channels_with_counts(evs)
check(chans[0]['name'] == 'общий' and chans[0]['messages'] == 3,
      f'каналы с данными по убыванию ({chans[0]})')
check(len(chans) == 3, 'все три канала учтены')

ma = AX.member_activity(evs, SABINA)
check(ma['found'] and ma['name'] == 'SabinaStar',
      'профиль: подпись — свежий ник после смены', str(ma)[:90])
check(ma['messages'] == 3, 'все сообщения слиты по uid')
check(dict(ma['top_channels']).get('общий') == 2,
      'любимые каналы посчитаны')
check(ma['last_active'] and ma['last_active'].startswith('2026-09-05'),
      'последняя активность — свежайшая запись')
check(not AX.member_activity(evs, '999')['found'],
      'неизвестный uid — честно found=False')

print('== 2. Живые эндпоинты (бот офлайн) ==')
import web.app as appmod  # noqa: E402

msgs = [{'author': 'Сабина', 'uid': str(SABINA), 'channel': 'общий-chat',
         'timestamp': '2026-09-01T10:00:00+00:00'},
        {'author': 'SabinaStar', 'uid': str(SABINA), 'channel': 'флудилка',
         'timestamp': '2026-09-05T12:00:00+00:00'}]
with open(f'data/message_logs_{GID}.json', 'w', encoding='utf-8') as f:
    json.dump(msgs, f, ensure_ascii=False)

appmod.bot_instance = None
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()
with client.session_transaction() as s:
    s.clear()
    s['logged_in'] = True
    s['username'] = 'Owner'
    s['role'] = 'owner'
    s['selected_guild'] = str(GID)

r = client.get(f'/api/guild/{GID}/analytics/drill-channels')
d = r.get_json() or {}
check(r.status_code == 200 and d.get('success'),
      f'drill-channels отвечает без бота [{r.status_code}]')
names = [c['name'] for c in d.get('channels', [])]
check('общий-chat' in names and 'флудилка' in names,
      'каналы из статистики на месте', str(names))

r = client.get(f'/api/guild/{GID}/analytics/member/{SABINA}')
d = r.get_json() or {}
check(r.status_code == 200 and d.get('found'),
      f'профиль участника отвечает без бота [{r.status_code}]')
check(d.get('name') == 'SabinaStar' and d.get('messages') == 2,
      'профиль склеен по uid, ник свежий', str(d)[:100])

r = client.get(f'/api/guild/{GID}/analytics/member/abc')
check(r.status_code == 400, 'мусорный uid — 400')

r = client.get(f'/api/guild/{GID}/analytics/channel-drill?name=%D1%84%D0%BB%D1%83%D0%B4%D0%B8%D0%BB%D0%BA%D0%B0')
d = r.get_json() or {}
check(r.status_code == 200 and d.get('total') == 1,
      'детализация по каналу работает без бота', str(d)[:90])

print('== 3. Шаблон: клик-профили и живой селект ==')
tpl = open(os.path.join(ROOT, 'web', 'templates', 'analytics.html'),
           encoding='utf-8').read()
check('openMemberProfile' in tpl and 'leader-row[data-uid]' in tpl,
      'строки топа открывают профиль (клик и Enter)')
check('/analytics/member/' in tpl and 'member-profile/' in tpl,
      'профиль тянет активность и варны/дела')
check('drill-channels' in tpl,
      'селект детализации берёт каналы из статистики')
check('· \' + fmtNum(counts[c.name])' in tpl.replace("'", "'"),
      'в подписи канала — счётчик сообщений')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
