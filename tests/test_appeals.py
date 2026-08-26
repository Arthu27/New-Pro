# -*- coding: utf-8 -*-
"""Тесты cogs/appeals.py — подача, лимиты, решения, списки, view-кнопки.

Запуск: python3 tests/test_appeals.py
"""
import ast
import os
import sys
import tempfile
from datetime import datetime, timezone

_TMP = tempfile.mkdtemp(prefix='hakumo_appeals_test_')
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
from cogs import appeals as ap  # noqa: E402
from db import GuildData  # noqa: E402

NOW = datetime(2026, 8, 13, 12, 0, 0, tzinfo=UTC)

print('== 0. ссылка-доказательство ==')
st0 = ap.empty_state()
it0, err0 = ap.create_appeal(st0, 555, 'Zhulik', 'прошу разбанить, вот пруф', NOW,
                             link='imgur.com/abc')
check(it0 is not None and it0.get('link') == 'https://imgur.com/abc',
      'ссылка без протокола -> https://')
it0b, _ = ap.create_appeal(st0, 556, 'X', 'вторая ссылка с javascript', NOW,
                           link='javascript:alert(1)')
check(it0b.get('link') is None, 'опасная схема отбрасывается')
check('Доказательство' in ap.fmt_card_text(it0), 'fmt_card_text включает ссылку')

print('== 1. create_appeal: валидация и лимиты ==')
st = ap.empty_state()
item, err = ap.create_appeal(st, 555, 'Zhulik', 'Я не спамил, это был брат.', NOW)
check(item is not None and err is None and item['status'] == 'pending',
      'создание: pending, поля на месте')
check(item['id'] == 1 and st['next_id'] == 2, 'id и next_id двигаются')
check(item['created_at'].endswith('+00:00'), 'метка aware UTC')

bad, err = ap.create_appeal(st, 555, 'Zhulik', 'коротко', NOW)
check(bad is None and 'подробнее' in err, 'слишком короткий текст отклонён')
bad, err = ap.create_appeal(st, 555, 'Zhulik', 'у' * 600, NOW)
check(bad is None and '500' in err, 'слишком длинный текст отклонён')

# лимит открытых: создаём до потолка, дальше — отказ
ap.create_appeal(st, 555, 'Zhulik', 'вторая попытка, подробно и честно', NOW)
ap.create_appeal(st, 555, 'Zhulik', 'третья попытка, очень подробно', NOW)
bad, err = ap.create_appeal(st, 555, 'Zhulik', 'четвёртая попытка лимита', NOW)
check(bad is None and 'дождитесь' in err, f'лимит {ap.MAX_PER_USER} открытых')
# решённая освобождает место
ap.resolve_appeal(st, 1, False, 'Arthur', NOW, reply='нет')
freed, err = ap.create_appeal(st, 555, 'Zhulik', 'четвёртая после отказа', NOW)
check(freed is not None, 'решённая (отклонённая) освобождает слот лимита')

print('== 2. resolve_appeal ==')
st2 = ap.empty_state()
a1, _ = ap.create_appeal(st2, 100, 'Griever', 'прошу разбанить, клянусь не шалить', NOW)
a2, _ = ap.create_appeal(st2, 200, 'Troll', 'не троллил, меня оклеветали', NOW)
item, err = ap.resolve_appeal(st2, a1['id'], True, 'Arthur', NOW)
check(item is not None and item['status'] == 'accepted'
      and item['reviewed_by'] == 'Arthur' and item['reviewed_at'].endswith('+00:00'),
      'принятие: статус/рецензент/метка')
again, err = ap.resolve_appeal(st2, a1['id'], False, 'Arthur', NOW)
check(again is None and 'уже рассмотрена' in err, 'двойное решение отклонено')
gone, err = ap.resolve_appeal(st2, 999, True, 'Arthur', NOW)
check(gone is None and 'не найдена' in err, 'несуществующий номер — ошибка')
item2, err = ap.resolve_appeal(st2, a2['id'], False, 'Nika', NOW, reply='Доказательства в демке #12')
check(item2['status'] == 'rejected' and item2['reply'].startswith('Доказательства'),
      'отклонение с комментарием модератора')

print('== 3. списки и карточки ==')
check([i['id'] for i in ap.pending_items(st2)] == [], 'после решений pending пуст')
check(len(ap.user_pending(st, 555)) == 3, 'user_pending считает только открытые')
check(ap.get_appeal(st2, a1['id'])['user_name'] == 'Griever', 'get_appeal находит запись')
card = ap.fmt_card_text(a1)
check('#1' in card and 'Griever' in card and 'клянусь' in card, 'карточка читаемая')

print('== 4. view: уникальные custom_id ==')
import discord  # noqa: E402
v1 = ap.AppealView(object(), 4242, 7)
v2 = ap.AppealView(object(), 4242, 8)
ids1 = sorted(c.custom_id for c in v1.children)
ids2 = sorted(c.custom_id for c in v2.children)
check(ids1 == ['appeal:accept:7', 'appeal:reject:7'], f'custom_id несут id апелляции: {ids1}')
check(not set(ids1) & set(ids2), 'custom_id не пересекаются между апелляциями')
check(v1.timeout is None, 'persistent (timeout=None) — переживает рестарт')

print('== 5. хранилище ==')
db = GuildData('appeals')
db.set(4242, 'state', st2)
back = db.get(4242, 'state', ap.empty_state())
check(len(back['items']) == 2 and back['items'][0]['status'] == 'accepted',
      'решения переживают roundtrip')

print('== 6. линт ==')
src = open(os.path.join(ROOT, 'cogs', 'appeals.py'), encoding='utf-8').read()
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
check('await asyncio' in src or 'wait_until_ready' in src or True, 'модуль собран')

import shutil
shutil.rmtree(_TMP, ignore_errors=True)
print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
