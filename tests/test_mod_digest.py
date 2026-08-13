# -*- coding: utf-8 -*-
"""Тесты cogs/mod_digest.py — агрегация событий, расписание, эмбед-слой.

Запуск: python3 tests/test_mod_digest.py
"""
import ast
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

_TMP = tempfile.mkdtemp(prefix='aether_digest_test_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
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


UTC = timezone.utc
from cogs import mod_digest as md  # noqa: E402
from db import GuildData  # noqa: E402

NOW = datetime(2026, 8, 13, 18, 30, 0, tzinfo=UTC)


def ev(cat='mod', action='Мут', mod='Arthur', sec_ago=3600, day=None):
    ts = day or (NOW - timedelta(seconds=sec_ago))
    return {'category': cat, 'action': action, 'user_name': 'Zhulik',
            'mod_name': mod, 'detail': 'spam', 'timestamp': ts.isoformat()}


print('== 1. aggregate_digest: агрегация ==')
events = [
    ev('mod', 'Мут', 'Arthur', 3600),
    ev('mod', 'Бан', 'Arthur', 7200),
    ev('warn', 'Предупреждение', 'Nika', 10_000),
    ev('warn', 'Предупреждение', 'Nika', 20_000),
    ev('ticket', 'Тикет закрыт', 'Nika', 50_000),
    ev('mod', 'Мут', 'Arthur', 9 * 86400),          # 9 дней назад — за окном 7
    {'category': 'mod', 'action': 'Мут', 'timestamp': 'билайн'},  # мусор
    ev('proof', 'Демка', None, 300),                # без модератора
]
s = md.aggregate_digest(events, days=7, now=NOW)
check(s['total'] == 6, f'за 7 дней 6 событий (9-дневное и мусор вне окна), got {s["total"]}')
check(dict(s['per_category']) == {'mod': 2, 'warn': 2, 'ticket': 1, 'proof': 1},
      'категории посчитаны')
check(s['top_actions'][0] == ('Предупреждение', 2), 'топ-действие первое')
check(s['top_mods'][0] == ('Nika', 3) and ('Arthur', 2) in s['top_mods'],
      'моды ранжированы по числу действий; пустой mod_name не попадает')
s14 = md.aggregate_digest(events, days=14, now=NOW)
check(s14['total'] == 7, 'за 14 дней 9-дневное входит в окно')
check(s['busiest_day'][1] >= 1 and s['busiest_day'][0] in s['per_day'],
      'самый горячий день определён')
check(md.aggregate_digest([], days=7)['total'] == 0, 'пустой вход -> ноль, не падение')
check(md.aggregate_digest(None, days='x')['total'] == 0, 'None/мусор дней -> ноль')

print('== 2. should_send: расписание ==')
s_on = md.merge_settings({'enabled': True, 'channel_id': 100, 'hour_utc': 18})
check(md.should_send(s_on, NOW) is True, 'первый запуск в нужный час — шлём')
s_on['last_sent'] = NOW.isoformat()
check(md.should_send(s_on, NOW) is False, 'повторно в тот же час — не шлём')
s_on['last_sent'] = (NOW - timedelta(days=7)).isoformat()
check(md.should_send(s_on, NOW) is True, 'неделя прошла — снова шлём')
check(md.should_send(s_on, NOW.replace(hour=10)) is False, 'не тот час — не шлём')
check(md.should_send(md.merge_settings({'enabled': False}), NOW) is False,
      'выключено — не шлём')
check(md.should_send({'enabled': True, 'channel_id': 0}, NOW) is False,
      'без канала — не шлём')

print('== 3. эмбед-слой ==')
payload = md.digest_embed_dict(s, 7, 'Hakumo')
check('7 дней' in payload['title'] and 'Hakumo' in payload['title'], 'заголовок')
fields = dict(payload['fields'])
check(fields['Всего событий'] == '6', 'поле «всего»')
check('Предупреждения: **2**' in fields['По категориям'], 'категория по-русски')
check('Arthur' in fields['Активные модераторы'], 'модераторы в поле')

print('== 4. load_events: файл audit_log ==')
os.makedirs('data', exist_ok=True)
with open('data/audit_log.json', 'w', encoding='utf-8') as fp:
    json.dump({'4242': [ev() for _ in range(3)], '7777': {'сломано': True}}, fp)
check(len(md.load_events('4242')) == 3, 'события гильдии читаются')
check(md.load_events('7777') == [], 'битый формат значения -> []')
check(md.load_events('9999') == [], 'нет гильдии -> []')
os.remove('data/audit_log.json')
check(md.load_events('4242') == [], 'нет файла -> []')
with open('data/audit_log.json', 'w', encoding='utf-8') as fp:
    fp.write('{не json')
check(md.load_events('4242') == [], 'битый JSON -> [] без падения')

print('== 5. merge_settings + хранилище ==')
ms = md.merge_settings({'enabled': True, 'hour_utc': 25})
check(ms['hour_utc'] == 1, 'час 25 -> мод 24')
db = GuildData('mod_digest')
db.set(4242, 'settings', {'enabled': True, 'channel_id': 5, 'hour_utc': 9,
                          'last_sent': NOW.isoformat()})
back = md.merge_settings(db.get(4242, 'settings', {}))
check(back['channel_id'] == 5 and back['hour_utc'] == 9 and back['last_sent'],
      'настройки переживают roundtrip')

print('== 6. линт ==')
src = open(os.path.join(ROOT, 'cogs', 'mod_digest.py'), encoding='utf-8').read()
tree = ast.parse(src)
silent = [n.lineno for n in ast.walk(tree)
          if isinstance(n, ast.ExceptHandler)
          and len([b for b in n.body if not (isinstance(b, ast.Expr)
                   and isinstance(b.value, ast.Constant))]) == 1
          and isinstance([b for b in n.body if not (isinstance(b, ast.Expr)
                          and isinstance(b.value, ast.Constant))][0],
                         (ast.Pass, ast.Continue))]
check(not silent, f'ни одного молчаливого except {silent or "ок"}')
check('utcnow' not in src, 'utcnow() не используется')
check(not any(tok in src for tok in ('}dk', '}sa{', "}sn'", 's{mn}dk')),
      'турецких единиц времени (dk/sa/sn) нет')

import shutil
shutil.rmtree(_TMP, ignore_errors=True)
print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
