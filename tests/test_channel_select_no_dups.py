# -*- coding: utf-8 -*-
"""Каналы в селектах панели: без дублей и без обрезанных имён.

Заказ владельца (2026-09): «в Обзоре сервера в Опубликовать объявление
2 одинаковых выбора — сделай один; чтобы таких вещей не было — проверь
везде». Плюс длинные имена каналов обрезались («Аналитика сервера» →
«Аналитика…», «статистика бота» не видно до наведения).

Где чиним:
1. /api/guild/<gid>/channels — единый источник всех пикеров: один канал
   с одним id попадает в список ровно один раз (_dedupe_channels).
2. dashboard.html и announcements.html — селекты каналов чистятся перед
   заполнением, дубли id отбрасываются, похожие имена разводятся по
   категориям (optgroup) + полное имя в title.
3. channels.html — имена каналов/категорий больше не режутся многоточием
   (white-space:normal), у строк и категорий есть title с полным именем.

Запуск: python3 tests/test_channel_select_no_dups.py
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

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


def _tpl(name):
    return open(os.path.join(ROOT, 'web', 'templates', name), encoding='utf-8').read()


# ─── 1. _dedupe_channels: источник пикеров отдаёт один канал один раз ───────
print('== _dedupe_channels (источник /api/guild/<id>/channels) ==')
sys.path.insert(0, os.path.join(ROOT, 'web', 'routes'))
import guild_admin as GA  # noqa: E402

raw = [
    {'id': '101', 'name': 'общий', 'type': 'text'},
    {'id': '101', 'name': 'общий', 'type': 'text'},   # дубль
    {'id': '102', 'name': 'новости', 'type': 'text'},
    {'id': '103', 'name': 'аналитика-сервера', 'type': 'text'},
]
out = GA._dedupe_channels(raw)
check([c['id'] for c in out] == ['101', '102', '103'],
      'дубль id 101 убран, порядок сохранён', f'→ {[c.get("id") for c in out]}')
check(GA._dedupe_channels(None) == [] and GA._dedupe_channels([]) == [],
      'пустые/битые входы не падают')
check(GA._dedupe_channels([{'id': '1', 'name': 'a'}]) == [{'id': '1', 'name': 'a'}],
      'без дублей список не меняется')

print('== _dedupe_by_id: обобщённый дедуп (каналы, роли) ==')
check(GA._dedupe_by_id([{'id': 'a'}, {'id': 'a'}, {'id': 'b'}]) == [{'id': 'a'}, {'id': 'b'}],
      '_dedupe_by_id убирает повтор id, порядок сохранён')
check(GA._dedupe_by_id(None) == [] and GA._dedupe_by_id([{'x': 1}]) == [],
      '_dedupe_by_id: пустые/без-id входы безопасны')
check(GA._dedupe_channels([{'id': '1'}, {'id': '1'}]) == GA._dedupe_by_id([{'id': '1'}, {'id': '1'}]),
      'канальная специализация повторяет обобщённый дедуп')

print('== guild_channels_roles: общий резолвер пикеров (репорты, логи…) ==')
ch, roles = GA.guild_channels_roles('nope-no-such-guild')
ids = [c['id'] for c in ch]
check(len(ids) == len(set(ids)), 'каналы без дублей id', f'→ дубли: {[i for i in set(ids) if ids.count(i) > 1]}')
rids = [r['id'] for r in roles]
check(len(rids) == len(set(rids)), 'роли без дублей id', f'→ дубли: {[i for i in set(rids) if rids.count(i) > 1]}')

print('== демо-структура каналов без повторов id ==')
seed = GA._demo_channels_seed()
ids = [c['id'] for c in seed]
check(len(ids) == len(set(ids)), 'в демо-посеве нет каналов с одинаковым id',
      f'→ дубли: {[i for i in set(ids) if ids.count(i) > 1]}')

# ─── 2. Селекты «куда публиковать» чистятся и группируются по категориям ───
print('== dashboard.html: быстрый селект объявления ==')
dash = _tpl('dashboard.html')
check("sel.innerHTML = '<option value=\"\">' + esc(phText)" in dash,
      'перед заполнением старые пункты гасятся (нет двойного списка)')
check('var seen = {}, byCat = {};' in dash and '!seen[c.id]' in dash,
      'дубли id отбрасываются при построении пунктов')
check("<optgroup" in dash and "esc(cat)" in dash,
      "каналы сгруппированы по категориям (похожие имена различимы)")
check('title="#' in dash, 'у пунктов есть полное имя во всплывающей подсказке')

print('== announcements.html: форма «Опубликовать объявление» ==')
ann = _tpl('announcements.html')
check('if (seen[channel.id]) return;' in ann,
      'дубли id отбрасываются при построении пунктов')
check('<optgroup label="' in ann and 'title="#' in ann,
      'группировка по категориям + полное имя в title у пунктов')

# ─── 3. channels.html: длинные имена видны целиком ──────────────────────────
print('== channels.html: имена каналов не обрезаются ==')
ch = _tpl('channels.html')
i = ch.find('.ch-name{font-weight:600')
seg = ch[i:i + 260] if i >= 0 else ''
check(i >= 0 and 'white-space:normal' in seg and 'text-overflow' not in seg,
      '.ch-name: перенос строки вместо обрезки многоточием', f'→ {seg[:90]}')
m2 = re.search(r'\.cat-name\{[^}]*\}', ch)
check(m2 is not None and 'white-space:normal' in m2.group(0),
      '.cat-name: перенос строки вместо обрезки', f'→ {m2.group(0)[:90] if m2 else ""}')
check('title="' + "' + esc(c.name)" in ch,
      'у строки канала title с полным именем (наведение = полное имя)')
check("title=\"' + esc(name)" in ch,
      'у категории title с полным именем')

print()
print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
