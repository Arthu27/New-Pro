# -*- coding: utf-8 -*-
"""Тесты cogs/anti_alt.py — возраст аккаунтов, решения, настройки, хранилище.

Запуск: python3 tests/test_anti_alt.py
"""
import ast
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

_TMP = tempfile.mkdtemp(prefix='aether_antialt_test_')
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
from cogs import anti_alt as aa  # noqa: E402
from db import GuildData  # noqa: E402

NOW = datetime(2026, 8, 13, 12, 0, 0, tzinfo=UTC)

print('== 1. merge_settings: дефолты и сломанные данные ==')
s = aa.merge_settings(None)
check(s == aa.DEFAULT_SETTINGS and s is not aa.DEFAULT_SETTINGS,
      'None -> копия дефолта')
s = aa.merge_settings({'enabled': True, 'action': 'kick', 'мусор': 1})
check(s['enabled'] is True and s['action'] == 'kick' and 'мусор' not in s,
      'неизвестные ключи выбрасываются')
s = aa.merge_settings({'action': 'взорвать', 'min_age_days': 'старая', 'whitelist': 'да'})
check(s['action'] == 'alert' and s['min_age_days'] == 7 and s['whitelist'] == [],
      'битые типы откатываются к безопасному дефолту')
s = aa.merge_settings({'min_age_days': -5})
check(s['min_age_days'] == 0, 'отрицательный порог зажат в ноль')

print('== 2. account_age_days ==')
check(abs(aa.account_age_days(NOW - timedelta(days=3), NOW) - 3.0) < 1e-6,
      'ровно 3 дня')
check(abs(aa.account_age_days((NOW - timedelta(hours=6)).isoformat(), NOW) - 0.25) < 1e-6,
      'ISO-строка на входе')
check(aa.account_age_days((NOW - timedelta(days=1)).replace(tzinfo=None), NOW) > 0.9,
      'naive метка трактуется как UTC, не падает')

print('== 3. decide: решения по зашедшим ==')
off = aa.merge_settings({'enabled': False})
trig, action, age, why = aa.decide(off, 1, NOW - timedelta(hours=1), NOW)
check(not trig and why == 'выключено', 'выключено — никого не трогаем')

on = aa.merge_settings({'enabled': True, 'min_age_days': 7, 'action': 'kick'})
trig, action, age, why = aa.decide(on, 1, NOW - timedelta(days=30), NOW)
check(not trig and why == 'возраст в норме', '30 дней при пороге 7 — ок')
trig, action, age, why = aa.decide(on, 1, NOW - timedelta(days=2), NOW)
check(trig and action == 'kick', '2 дня при пороге 7 — кик')
check('дн' in why or 'дня' in why or 'дней' in why, f'причина с порогом: {why!r}')

wl = aa.merge_settings({'enabled': True, 'min_age_days': 7, 'action': 'ban',
                        'whitelist': [42]})
trig, action, age, why = aa.decide(wl, 42, NOW - timedelta(hours=1), NOW)
check(not trig and why == 'в белом списке', 'белый список неприкосновенен')
trig, action, age, why = aa.decide(wl, 43, NOW - timedelta(hours=1), NOW)
check(trig and action == 'ban', 'другой свежий — бан по настройке')

edge = aa.merge_settings({'enabled': True, 'min_age_days': 0})
trig, action, age, why = aa.decide(edge, 1, NOW - timedelta(seconds=30), NOW)
check(not trig, 'порог 0 дней — выключен по смыслу (все аккаунты старше)')

print('== 4. settings_lines ==')
lines = aa.settings_lines({'enabled': True, 'min_age_days': 3, 'action': 'ban',
                           'log_channel_id': 0, 'whitelist': [1, 2]})
check(len(lines) == 5 and 'включена' in lines[0] and 'бан' in lines[2],
      '5 строк статуса, действие по-русски')
check('3 дня' in lines[1], f'склонение порога: {lines[1]!r}')
check('2 аккаунта' in lines[4], f'склонение белого списка: {lines[4]!r}')

print('== 5. хранилище GuildData ==')
db = GuildData('anti_alt')
db.set(4242, 'settings', {'enabled': True, 'action': 'ban', 'min_age_days': 14})
back = aa.merge_settings(db.get(4242, 'settings', {}))
check(back['enabled'] is True and back['action'] == 'ban' and back['min_age_days'] == 14,
      'настройки переживают roundtrip через SQLite')
check(aa.merge_settings(db.get(8888, 'settings', {}))['enabled'] is True
      and aa.merge_settings(db.get(8888, 'settings', {}))['action'] == 'alert',
      'чужой сервер -> дефолт (щит включён, безопасное действие alert)')

print('== 6. линт модуля ==')
src = open(os.path.join(ROOT, 'cogs', 'anti_alt.py'), encoding='utf-8').read()
tree = ast.parse(src)
silent = []
for node in ast.walk(tree):
    if isinstance(node, ast.ExceptHandler):
        body = [b for b in node.body
                if not (isinstance(b, ast.Expr) and isinstance(b.value, ast.Constant)
                        and isinstance(b.value.value, str))]
        if len(body) == 1 and isinstance(body[0], (ast.Pass, ast.Continue)):
            silent.append(node.lineno)
check(not silent, f'ни одного молчаливого except {silent or "ок"}')
check('utcnow' not in src, 'utcnow() не используется')
check('MODERATION-only' not in src, 'модуль самостоятельный — без магических глобалов')

import shutil
shutil.rmtree(_TMP, ignore_errors=True)
print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
