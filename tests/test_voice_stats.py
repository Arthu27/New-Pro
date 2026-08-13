# -*- coding: utf-8 -*-
"""Тесты голосовой статистики: единый SQLite-источник (cogs/voice_tracker),
русские единицы времени (конец эпохе «dk/sa/sn»), миграция legacy JSON,
и рендер API панели с реальными данными.

Запуск: python3 tests/test_voice_stats.py
"""
import json
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='aether_voice_test_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
# изолированная SQLite-база для теста
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')

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


GID = 4242

print('== 1. fmt_duration: русские единицы ==')
from cogs.voice_tracker import fmt_duration

table = [
    (0, '0 мин'), (45, '45 сек'), (90, '1 мин 30 сек'), (600, '10 мин'),
    (3600, '1 ч 0 мин'), (3661, '1 ч 1 мин'), (90000, '1 д 1 ч'),
]
for sec, want in table:
    got = fmt_duration(sec)
    assert got == want, (sec, got, want)
check(True, 'таблица: сек/мин/ч/дни — по-русски, dk/sn нет')
check(fmt_duration(None) == '0 мин' and fmt_duration('билайн') == '0 мин',
      'устойчивость к мусору на входе')

print('== 2. Хелперы поверх SQLite ==')
from db import GuildData
from cogs import voice_tracker as vt

db = GuildData('voice_stats')
today = __import__('datetime').date.today().isoformat()
db.set(GID, '1001', {'name': 'Zhulik', 'avatar': '', 'total_seconds': 7325,
                     'daily': {today: 1800, '2020-01-01': 500}})
db.set(GID, '1002', {'name': 'Troll', 'avatar': '', 'total_seconds': 90,
                     'daily': {today: 90}})
db.set(GID, '1003', {'name': 'MuteBob', 'avatar': '', 'total_seconds': 0, 'daily': {}})

check(vt.voice_seconds(GID, '1001') == 7325 and vt.voice_seconds(GID, '404') == 0,
      'voice_seconds: точные значения, отсутствующий = 0')
check(vt.voice_today_users(GID) == 2, 'voice_today_users: двое сегодня (нулевой не считается)')
check(vt.voice_today_seconds(GID) == 1890, 'voice_today_seconds: сумма за сегодня')
check(vt.voice_today_seconds(GID, '1001') == 1800, 'voice_today_seconds: конкретный пользователь')
lb = vt.voice_leaderboard(GID)
check([r['user_id'] for r in lb] == ['1001', '1002'], 'leaderboard: сортировка, нулевой фильтруется')
check(lb[0]['seconds'] == 7325 and lb[0]['name'] == 'Zhulik', 'leaderboard: поля на месте')
view = vt.voice_view(GID)
check(set(view.keys()) == {'users'} and view['users']['1001']['minutes'] == 122
      and view['users']['1001']['seconds'] == 7325,
      'voice_view: легаси-совместимая форма (minutes + seconds + daily)')

print('== 3. Миграция legacy JSON ==')
GID2 = 7777
os.makedirs('data', exist_ok=True)
legacy = {'users': {
    '2001': {'name': 'OldUser', 'avatar': 'a.png', 'total_seconds': 3600,
             'daily': {today: 600}},
    '2002': {'name': 'MinUser', 'minutes': 12},   # древняя схема: минуты
    '2003': 300,                                   # совсем древняя: голое число секунд
}}
with open(f'data/voice_stats_{GID2}.json', 'w', encoding='utf-8') as fp:
    json.dump(legacy, fp)
all2 = vt.voice_all(GID2)
check(all2['2001']['total_seconds'] == 3600 and all2['2001']['daily'][today] == 600,
      'миграция: total_seconds и daily перенесены')
check(all2['2002']['total_seconds'] == 720, 'миграция: legacy-minutes x60')
check(all2['2003']['total_seconds'] == 300, 'миграция: голое число = секунды')
check(not os.path.exists(f'data/voice_stats_{GID2}.json')
      and os.path.exists(f'data/voice_stats_{GID2}.json.legacy'),
      'миграция: файл убран в .legacy (не перечитывается)')
all2b = vt.voice_view(GID2)
check(all2b['users']['2001']['total_seconds'] == 3600, 'после миграции чтение идёт из SQLite')
# битый файл: не падает, архивируется
GID3 = 8888
with open(f'data/voice_stats_{GID3}.json', 'w', encoding='utf-8') as fp:
    fp.write('{бито')
vt._migrated_guilds.discard(GID3) if GID3 in vt._migrated_guilds else None
check(vt.voice_all(GID3) == {}, 'битый legacy-JSON: пустой ответ без падения')
check(os.path.exists(f'data/voice_stats_{GID3}.json.legacy')
      or not os.path.exists(f'data/voice_stats_{GID3}.json'), 'битый файл не остаётся на пути')

print('== 4. API панели: /api/guild/<gid>/voice-stats ==')
import web.app as panel_app

app = panel_app.app
app.config['TESTING'] = True
client = app.test_client()
with client.session_transaction() as s:
    s['logged_in'] = True
    s['username'] = 'Arthur'
    s['role'] = 'owner'

r = client.get(f'/api/guild/{GID}/voice-stats')
check(r.status_code == 200, 'эндпоинт отвечает 200')
data = r.get_json()
check(data['leaderboard'][0]['name'] == 'Zhulik'
      and data['leaderboard'][0]['time'] == '2 ч 2 мин',
      'строка участника по-русски (2 ч 2 мин, не 2s 2dk)')
check(data['leaderboard'][1]['time'] == '1 мин 30 сек', 'секундный формат по-русски')
check(data['total_time'] == '2 ч 3 мин', 'итог сервера по-русски')
check(data['today_users'] == 2, 'today_users: реальные люди сегодня (не мусор из JSON)')
check(data['avg_time'] == '41 мин 11 сек', 'среднее по-русски')
raw = r.get_data(as_text=True)
check('dk' not in raw and 'sn"' not in raw and 'sa' not in (data['total_time'] or ''),
      'турецких dk/sn/sa в ответе не осталось')

r404 = client.get('/api/guild/9999/voice-stats')
d404 = r404.get_json()
check(r404.status_code == 200 and d404['leaderboard'] == [] and d404['total_time'] == '0 мин',
      'пустой сервер: JSON 200 без 500-ки')

print('== 5. Единые единицы в когах ==')
from cogs.duty import fmt_dur
check(fmt_dur(3661) == '1 ч 1 мин' and fmt_dur(61) == '1 мин 1 сек', 'duty.fmt_dur: по-русски')
from cogs.mod_report import _fmt_time
check(_fmt_time(125) == '2 ч 5 мин' and _fmt_time(45) == '45 мин', 'mod_report._fmt_time: по-русски')

print('== 6. Сторожевые линты ==')
left = []
for base in ('cogs', 'web', 'services'):
    for dp, _dn, fns in os.walk(os.path.join(ROOT, base)):
        if '__pycache__' in dp:
            continue
        for fn in fns:
            if not fn.endswith('.py'):
                continue
            sp = os.path.join(dp, fn)
            s = open(sp, encoding='utf-8', errors='ignore').read()
            if 'voice_stats_{' in s and not sp.endswith('voice_tracker.py'):
                left.append(sp)
check(not left, f'мёртвые читатели voice_stats_*.json истреблены {left}')
bad = []
for base in ('cogs', 'web'):
    for dp, _dn, fns in os.walk(os.path.join(ROOT, base)):
        if '__pycache__' in dp:
            continue
        for fn in fns:
            if not fn.endswith('.py'):
                continue
            s = open(os.path.join(dp, fn), encoding='utf-8', errors='ignore').read()
            for tok in ('}dk', '}sa', "}sn'", "'{m}d'", 's{mn}dk', 'h}s{'):
                if tok in s:
                    bad.append((fn, tok))
check(not bad, f'турецкие единицы времени истреблены {bad[:5]}')

import shutil
shutil.rmtree(_TMP, ignore_errors=True)
print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
