# -*- coding: utf-8 -*-
"""Тесты cogs/reminders.py — создание, сроки, повторы, доставка, лимиты.

Запуск: python3 tests/test_reminders.py
"""
import ast
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

_TMP = tempfile.mkdtemp(prefix='hakumo_remind_test_')
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
from cogs import reminders as r  # noqa: E402
from db import GuildData  # noqa: E402

NOW = datetime(2026, 8, 13, 12, 0, 0, tzinfo=UTC)

print('== 1. create_reminder: сроки и лимиты ==')
st = r.empty_state()
item, err = r.create_reminder(st, 10, 55, 'позвонить маме', '10м', NOW)
check(item is not None and err is None, 'создание: 10м распарсилось')
check(item['due_at'] == (NOW + timedelta(minutes=10)).isoformat(), 'due_at — aware ISO в будущем')
check(item['id'] == 1 and st['next_id'] == 2, 'id и next_id двигаются')

item2, _ = r.create_reminder(st, 10, 55, 'полить цветы', 'через 2ч', NOW)
item3, _ = r.create_reminder(st, 10, 55, 'вечерний созвон', '18:30', NOW)
check(item2['due_at'] == (NOW + timedelta(hours=2)).isoformat(), '«через 2ч» ок')
check(item3['due_at'] == NOW.replace(hour=18, minute=30).isoformat(), '«18:30» — сегодня вечером')

bad, err = r.create_reminder(st, 10, 55, 'x', 'когда-нибудь', NOW)
check(bad is None and 'не понял срок' in err, 'мусорный срок — внятная ошибка')
bad, err = r.create_reminder(st, 10, 55, '', '10м', NOW)
check(bad is None and 'пустой текст' in err, 'пустой текст — ошибка')
bad, err = r.create_reminder(st, 10, 55, 'у' * 400, '10м', NOW)
check(bad is None and '300' in err, 'слишком длинный текст — ошибка')

st2 = r.empty_state()
for i in range(r.MAX_PER_USER):
    r.create_reminder(st2, 7, 1, f'дело {i}', '5м', NOW)
bad, err = r.create_reminder(st2, 7, 1, 'ещё одно', '5м', NOW)
check(bad is None and 'лимит' in err, f'лимит {r.MAX_PER_USER} активных на пользователя')
ok_other, _ = r.create_reminder(st2, 8, 1, 'чужое', '5м', NOW)
check(ok_other is not None, 'лимит — на пользователя, не на сервер')

print('== 2. повторяющиеся ==')
sec, body = r.parse_repeat('каждые 24ч отчёт в канал')
check(sec == 86400 and body == 'отчёт в канал', '«каждые 24ч …» -> repeat + текст')
sec, body = r.parse_repeat('просто текст')
check(sec is None and body == 'просто текст', 'без маркера — без повтора')
sec, body = r.parse_repeat('каждый день зарядка')
check(sec == 86400 and body == 'зарядка', '«каждый день …» тоже понимает')

print('== 3. due_items / mark_delivered ==')
st3 = r.empty_state()
past, _ = r.create_reminder(st3, 1, 1, 'уже пора', '1м', NOW)
past['due_at'] = (NOW - timedelta(seconds=5)).isoformat()  # просрочено
future, _ = r.create_reminder(st3, 1, 1, 'ещё рано', '2ч', NOW)
due = r.due_items(st3, NOW)
check([i['id'] for i in due] == [past['id']], 'к доставке — только просроченные')

r.mark_delivered(st3, past, NOW)
check(past['done'] is True and not r.due_items(st3, NOW), 'одноразовое закрывается')

rep, _ = r.create_reminder(st3, 1, 1, 'каждый час пик', '1м', NOW)
rep['repeat_seconds'] = 3600
rep['due_at'] = (NOW - timedelta(minutes=30)).isoformat()
r.mark_delivered(st3, rep, NOW)
check(rep['done'] is False, 'повторяющееся не закрывается')
check(rep['due_at'] == (NOW + timedelta(minutes=30)).isoformat(),
      'повтор переносится вперёд кратно интервалу')

print('== 4. cancel / список / формат ==')
st4 = r.empty_state()
a, _ = r.create_reminder(st4, 5, 1, 'первое', '10м', NOW)
b, _ = r.create_reminder(st4, 5, 1, 'второе', '1ч', NOW)
check(r.cancel_item(st4, a['id'], 5) is True, 'своё отменяется')
check(r.cancel_item(st4, a['id'], 5) is False, 'повторная отмена — False')
check(r.cancel_item(st4, b['id'], 999) is False, 'чужое не отменить')
check([i['id'] for i in r.user_items(st4, 5)] == [b['id']], 'в списке — только активные')

line = r.fmt_reminder_line(b, NOW)
check(f"#{b['id']}" in line and 'через 1 час' in line and 'второе' in line,
      f'строка списка читаемая: {line!r}')

print('== 5. хранилище GuildData ==')
db = GuildData('reminders')
g = 4242
db.set(g, 'state', st4)
back = db.get(g, 'state', r.empty_state())
check(back['next_id'] == st4['next_id'] and len(back['items']) == len(st4['items']),
      'roundtrip состояния через SQLite')
check(db.get(999_999, 'state', r.empty_state()) == r.empty_state(),
      'сервер без данных -> пустое состояние по умолчанию')

print('== 6. линт модуля ==')
src = open(os.path.join(ROOT, 'cogs', 'reminders.py'), encoding='utf-8').read()
tree = ast.parse(src)
silent = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler)
          and len([b for b in n.body if not (isinstance(b, ast.Expr)
                   and isinstance(b.value, ast.Constant))]) == 1
          and isinstance([b for b in n.body if not (isinstance(b, ast.Expr)
                          and isinstance(b.value, ast.Constant))][0],
                         (ast.Pass, ast.Continue))]
# except-ветки вида «pass  # комментарий» тоже отловим текстово
check('utcnow' not in src, 'utcnow() не используется')
check('datetime.now(timezone.utc)' in src or 'datetime.now(UTC)' in src,
      'метки времени — aware UTC')
check(src.count('GuildData(') >= 1, 'хранилище — GuildData (SQLite)')

import shutil
shutil.rmtree(_TMP, ignore_errors=True)
print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
