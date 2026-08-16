# -*- coding: utf-8 -*-
"""HTML-экспорт журнала модерации: services/log_export.py + роут + команда.

Покрытие: парсинг меток, загрузка, фильтры (период/категория/мод/поиск),
рендер автономного HTML (экранирование XSS, сводка, пустота), безопасное
имя файла, панельный /logs/export (права, attachment) и бот-команда
/логи-экспорт (файл реально уходит).

Запуск: python3 tests/test_log_export.py
"""
import asyncio
import importlib
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

_TMP = tempfile.mkdtemp(prefix='aether_logexp_test_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['PANEL_USER'] = 'admin'
os.environ['PANEL_PASSWORD'] = 'test123'

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
from services import log_export as lx  # noqa: E402

NOW = datetime(2026, 8, 16, 12, 0, 0, tzinfo=UTC)


def ev(cat, act, days_ago, mod='Страж', target='Нарушитель', **extra):
    return {
        'category': cat, 'action': act,
        'timestamp': (NOW - timedelta(days=days_ago)).isoformat(),
        'mod_name': mod, 'target_name': target, **extra,
    }


EVENTS = [
    ev('модерация', 'ban', 1, reason='спам'),
    ev('модерация', 'warn', 3, mod='Ночной', reason='токсик'),
    ev('сообщения', 'purge', 9, target='—', count=15),
    ev('вход', 'join', 40),
]
json.dump({'777': EVENTS, '888': [ev('прочее', 'x', 1)]},
          open('data/audit_log.json', 'w', encoding='utf-8'), ensure_ascii=False)

print('== 1. parse_ts / load_events ==')
check(lx.parse_ts(None) is None and lx.parse_ts('мусор') is None, 'мусор -> None')
check(lx.parse_ts('2026-08-16 10:00').tzinfo is not None, 'naive ISO считается UTC')
check(len(lx.load_events(777)) == 4 and lx.load_events(999) == [], 'загрузка по гильдии')
json.dump('{{битый', open('data/broken.json', 'w', encoding='utf-8'))
check(lx.load_events(777, 'data/broken.json') == [], 'битый файл -> []')

print('== 2. Фильтры ==')
check(len(lx.filter_events(EVENTS, days=7, now=NOW)) == 2, 'за 7 дней — 2 события')
check(len(lx.filter_events(EVENTS, days=10, now=NOW)) == 3, 'за 10 дней — 3')
check(len(lx.filter_events(EVENTS, category='сообщения', now=NOW)) == 1, 'по категории точно')
check(len(lx.filter_events(EVENTS, mod='ночн', now=NOW)) == 1, 'по модератору подстрокой')
check(len(lx.filter_events(EVENTS, query='спам', now=NOW)) == 1, 'поиск по деталям')
check(lx.filter_events(EVENTS, query='НЕТ_ТАКОГО', now=NOW) == [], 'поиск без совпадений')

print('== 3. Рендер HTML ==')
doc = lx.render_html(EVENTS[:2], guild_name='Тест Сервер', filters_desc='период: 7 дн.', generated_at=NOW)
check(doc.startswith('<!DOCTYPE html>') and 'lang="ru"' in doc, 'автономный документ')
check('http://' not in doc and 'https://' not in doc, 'без внешних ресурсов (реально автономный)')
check('Тест Сервер' in doc and 'Всего событий</small>2' in doc, 'шапка и счётчик')
xss = lx.render_html([ev('модерация', '<script>alert(1)</script>', 0, reason='<img src=x>')], generated_at=NOW)
check('<script>alert(1)</script>' not in xss and '&lt;script&gt;' in xss, 'XSS экранируется')
empty = lx.render_html([], generated_at=NOW)
check('событий нет' in empty, 'пустой отчёт честный')
when_row = lx.row_fields(EVENTS[0])
check(when_row[3] == 'Страж' and 'reason=спам' in when_row[5], 'колонки мод/детали собираются')

print('== 4. Имя файла ==')
fn = lx.export_filename('Мой Сервер #/:D', now=NOW)
check(fn == f'modlog_Мой_Сервер_D_{NOW.strftime("%Y-%m-%d")}.html', f'безопасное имя: {fn}')

print('== 5. Панель: /logs/export ==')
appmod = importlib.import_module('web.app')


class FakeGuild:
    def __init__(self):
        self.id = 777
        self.name = 'TestGuild'


class FakeBot:
    def __init__(self):
        self.guilds = [FakeGuild()]

    def get_guild(self, gid):
        return self.guilds[0] if gid == 777 else None


appmod.set_bot_instance(FakeBot())
client = appmod.app.test_client()


def login(role):
    with client.session_transaction() as s:
        s.clear()
        s['logged_in'] = True
        s['username'] = 'admin'
        s['role'] = role


login('uye')
r = client.get('/logs/export')
check(r.status_code in (302, 403), f'uye не пускают ({r.status_code})')
login('owner')
r = client.get('/logs/export?days=30')
body = r.get_data(as_text=True)
check(r.status_code == 200, 'выгрузка отдаётся 200')
check('attachment' in (r.headers.get('Content-Disposition') or '')
      and 'modlog_TestGuild_' in (r.headers.get('Content-Disposition') or ''),
      f'attachment заголовок: {r.headers.get("Content-Disposition")}')
check('Журнал модерации' in body, 'заголовок отчёта на месте')
check('ban' in body and 'purge' in body and 'join' not in body, '30 дней: ban и purge внутри, древний join отсечён')
r2 = client.get('/logs/export?days=7&mod=Ночной')
check('warn' in r2.get_data(as_text=True), 'параметр mod фильтрует')

print('== 6. Команда /логи-экспорт ==')
from cogs.logs import Logs  # noqa: E402


class FakeCtx:
    def __init__(self):
        self.guild = type('G', (), {'id': 777, 'name': 'TestGuild'})()
        self.sent = []

    async def send(self, text=None, file=None, **kw):
        self.sent.append((text, file))


cog = Logs.__new__(Logs)
ctx = FakeCtx()
asyncio.get_event_loop().run_until_complete(cog.logs_export.callback(cog, ctx, days=10))
text, file_obj = ctx.sent[0]
check(file_obj is not None and file_obj.filename.endswith('.html'), f'файл приложен: {file_obj.filename}')
payload = file_obj.fp.getvalue().decode('utf-8')
check(payload.startswith('<!DOCTYPE html>') and 'warn' in payload, 'содержимое — отчёт за 10 дней')
check('3' in (text or '') and 'событ' in (text or ''), f'подпись с количеством: {text}')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
