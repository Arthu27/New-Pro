# -*- coding: utf-8 -*-
"""Страж панели: ни одна страница не должна отдавать HTTP 500.

Инцидент 30.08 «до сих пор проблемы с ботом»: обход ВСЕХ GET-страниц
панели показал 8 эндпоинтов, падающих с 500 Internal Server Error:

    /api/achievements/state   /api/duels/state
    /api/music/state          /api/shop/state
    /api/mod-report           /api/mod-report.csv
    /api/tickets-ops/sla      /api/tickets-ops/export.csv

Причина у всех одна: `int(ctx.active_guild_id())`. Метод отдаёт СТРОКУ и
совершенно законно возвращает ПУСТУЮ — когда MAIN_GUILD_ID не задан в
.env и бот ещё не подключился (или офлайн). `int('')` бросает ValueError
→ Flask отвечает 500. Для владельца это выглядит как «панель сломана»:
страницы Магазин, Музыка, Дуэли, Ачивки, Отчёт модерации и SLA/экспорт
тикетов просто не открывались.

Правильное поведение: 503 + внятное «Сервер не выбран», а не 500.
Для этого в Ctx появился active_guild_id_int() → int или None.

Тест проверяет ДВА режима:
  * MAIN_GUILD_ID пуст  — 500 быть не должно нигде (допустим 503);
  * MAIN_GUILD_ID задан — те же эндпоинты обязаны отдавать данные (200),
    иначе «починка» превратила бы страницы в вечную заглушку.

Запуск: python3 tests/test_panel_no_500.py
"""
import os
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_p500_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['SECRET_KEY'] = 'test-secret'
os.environ.pop('MAIN_GUILD_ID', None)

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


# ─────────────────────────────────────────────────────────────────────────
print('== 1. Ни один GET-роут панели не отдаёт 500 (MAIN_GUILD_ID пуст) ==')

from web.app import app  # noqa: E402

client = app.test_client()
with client.session_transaction() as s:
    s['logged_in'] = True
    s['role'] = 'owner'
    s['username'] = 'owner'

routes = sorted({str(r.rule) for r in app.url_map.iter_rules()
                 if 'GET' in r.methods and '<' not in str(r.rule)})

# 503 «сервер не выбран» — ЗАКОННЫЙ ответ при пустом MAIN_GUILD_ID.
# Ловим именно 500 (Internal Server Error) — необработанное исключение.
broken = []
for url in routes:
    try:
        resp = client.get(url)
        if resp.status_code >= 500 and resp.status_code != 503:
            broken.append((url, resp.status_code))
    except Exception as e:                       # исключение = тоже поломка
        broken.append((url, f'{type(e).__name__}: {e}'))

print(f'  обойдено страниц: {len(routes)}')
check(not broken, f'нет ответов 500 (сломано: {broken[:6]})')

# именно те восемь, что падали в инциденте
INCIDENT = [
    '/api/achievements/state', '/api/duels/state',
    '/api/shop/state',
    '/api/mod-report', '/api/mod-report.csv',
    '/api/tickets-ops/sla', '/api/tickets-ops/export.csv',
]
for url in INCIDENT:
    code = client.get(url).status_code
    check(code != 500,
          f'{url} → {code} (не 500; при пустом MAIN_GUILD_ID ждём 503)')

# ─────────────────────────────────────────────────────────────────────────
print('== 2. Хелпер Ctx.active_guild_id_int() ==')
from web.routes._common import Ctx  # noqa: E402

check(hasattr(Ctx, 'active_guild_id_int'),
      'Ctx.active_guild_id_int() существует')


class _FakeCtx(Ctx):
    def __init__(self, value):
        self._v = value

    def active_guild_id(self):
        return self._v


check(_FakeCtx('').active_guild_id_int() is None,
      'пустая строка → None (а не ValueError)')
check(_FakeCtx('   ').active_guild_id_int() is None,
      'пробелы → None')
check(_FakeCtx(None).active_guild_id_int() is None,
      'None → None')
check(_FakeCtx('не число').active_guild_id_int() is None,
      'мусор → None (а не падение)')
check(_FakeCtx('777').active_guild_id_int() == 777,
      'нормальный id → int 777')
check(_FakeCtx(' 777 ').active_guild_id_int() == 777,
      'id с пробелами → int 777')

# ─────────────────────────────────────────────────────────────────────────
print('== 3. Небезопасный int(ctx.active_guild_id()) не вернулся в код ==')
import re  # noqa: E402

PAT = re.compile(r'int\s*\(\s*ctx\s*\.\s*active_guild_id\s*\(\s*\)\s*\)')
offenders = []
routes_dir = os.path.join(ROOT, 'web', 'routes')
for fname in sorted(os.listdir(routes_dir)):
    if not fname.endswith('.py'):
        continue
    text = open(os.path.join(routes_dir, fname), encoding='utf-8').read()
    for i, line in enumerate(text.splitlines(), 1):
        stripped = line.lstrip()
        # пропускаем комментарии и строки внутри docstring'ов (там паттерн
        # упоминается как ОПИСАНИЕ бага — это не код)
        if stripped.startswith('#') or '`' in line:
            continue
        if PAT.search(line):
            offenders.append(f'{fname}:{i}')
check(not offenders,
      f'нигде нет int(ctx.active_guild_id()) в коде ({offenders})')

# ─────────────────────────────────────────────────────────────────────────
print('== 4. С заданным MAIN_GUILD_ID страницы отдают данные, а не заглушку ==')
# перезапускаем приложение с сервером в окружении
for mod in [m for m in list(sys.modules) if m.startswith('web')]:
    del sys.modules[mod]
os.environ['MAIN_GUILD_ID'] = '777'

from web.app import app as app2  # noqa: E402

client2 = app2.test_client()
with client2.session_transaction() as s:
    s['logged_in'] = True
    s['role'] = 'owner'
    s['username'] = 'owner'

# Эндпоинты удалённых фич (achievements/duels/shop/mod-report/tickets-ops/
# музыка) больше не существуют — честный 404, а не 500 и не «вечный сервер
# не выбран». Музыка снесена 2026-09-01 вместе с /api/music/*.
DELETED_FEATURES = [
    '/api/achievements/state', '/api/duels/state', '/api/shop/state',
    '/api/mod-report', '/api/mod-report.csv',
    '/api/tickets-ops/sla', '/api/tickets-ops/export.csv',
    '/api/music/state',
]
for url in DELETED_FEATURES:
    code = client2.get(url).status_code
    check(code == 404,
          f'{url} → {code} (фича удалена — ждём ровный 404, не 500)')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
