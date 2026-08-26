# -*- coding: utf-8 -*-
"""Тесты cogs/proactive_mod.py + страж семьи багов naive/aware datetime.

Прод-инцидент: on_message падал на КАЖДОМ сообщении —
`can't subtract offset-naive and offset-aware datetimes`:
буфер писал aware-метки, а _check_spam строил naive `now`
(`now(timezone.utc).replace(tzinfo=None)`).

Та же семья мин: `member.timeout(naive_dt)` — discord.py требует aware
(TypeError). Страж ниже сканирует все коги и не даёт вернуться этому
паттерну рядом с вызовами .timeout().

Запуск: python3 tests/test_proactive_mod.py
"""
import asyncio
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone

_TMP = tempfile.mkdtemp(prefix='hakumo_proact_test_')
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
from cogs.proactive_mod import ProactiveModeration, _as_utc  # noqa: E402


class _Msg:
    def __init__(self, channel_id=10, author_id=42):
        self.channel = type('C', (), {'id': channel_id})()
        self.author = type('A', (), {'id': author_id, 'mention': '<@42>'})()
        self.guild = object()
        self.content = 'текст'
        self.id = 1


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


print('== 1. _as_utc — нормализация меток ==')
naive = datetime.now(UTC).replace(tzinfo=None)
aware = datetime.now(UTC)
check(_as_utc(naive).tzinfo is not None, 'naive -> aware (считаем UTC)')
check(_as_utc(aware) is aware, 'aware возвращается как есть')
check((_as_utc(naive) - _as_utc(aware)).total_seconds() < 1, 'смешанные метки вычитаются без TypeError')

print('== 2. _check_spam — окно и смешанный буфер (прод-крэш) ==')
cog = ProactiveModeration.__new__(ProactiveModeration)
cog.bot = object()
cog.spam_threshold = 5
cog.spam_window = 10
cog.message_buffer = {
    10: [
        {'author_id': 42, 'author_name': 'x', 'content': 'a',
         'timestamp': datetime.now(UTC) - timedelta(seconds=3)},              # aware, в окне
        {'author_id': 42, 'author_name': 'x', 'content': 'b',
         'timestamp': (datetime.now(UTC) - timedelta(seconds=2)).replace(tzinfo=None)},  # легаси naive, в окне
        {'author_id': 42, 'author_name': 'x', 'content': 'c',
         'timestamp': datetime.now(UTC) - timedelta(seconds=60)},             # aware, вне окна
        {'author_id': 99, 'author_name': 'y', 'content': 'd',
         'timestamp': datetime.now(UTC)},                                      # чужой автор
    ]
}
alerts = []


async def fake_alert(guild, kind, text, message):
    alerts.append((kind, text))


cog._alert_moderators = fake_alert
run(cog._check_spam(_Msg()))   # до порога — 2 свежих + само сообщение уже в буфере нет
check(alerts == [], f'мало свежих сообщений — без алерта ({alerts})')

now = datetime.now(UTC)
cog.message_buffer[10] = [
    {'author_id': 42, 'author_name': 'x', 'content': str(i),
     'timestamp': now - timedelta(seconds=i % 3)} for i in range(6)
]
run(cog._check_spam(_Msg()))
check(any(k == 'spam' for k, _ in alerts), 'порог достигнут — алерт о спаме')
check(any('6 сообщений' in t for _, t in alerts), 'в алерте честный счёт сообщений')

print('== 3. Страж: .timeout() никогда не получает naive-datetime ==')
scan_fail = []
assign_re = re.compile(r'^\s*([A-Za-z_]\w*)\s*=[^\n]*replace\s*\(\s*tzinfo\s*=\s*None\s*\)')
call_re = re.compile(r'\.timeout\s*\(\s*([A-Za-z_]\w*)')
for fn in sorted(os.listdir(os.path.join(ROOT, 'cogs'))):
    if not fn.endswith('.py'):
        continue
    src = open(os.path.join(ROOT, 'cogs', fn), encoding='utf-8').read()
    stripped_vars = {m.group(1) for m in map(assign_re.match, src.splitlines()) if m}
    for m in call_re.finditer(src):
        var = m.group(1)
        if var in stripped_vars:
            scan_fail.append(f'{fn}: timeout({var}) — {var} построен с tzinfo=None')
for fn in sorted(os.listdir(os.path.join(ROOT, 'cogs'))):
    if not fn.endswith('.py'):
        continue
    src = open(os.path.join(ROOT, 'cogs', fn), encoding='utf-8').read()
    inline = re.search(r'\.timeout\s*\([^)]*replace\s*\(\s*tzinfo\s*=\s*None', src, re.S)
    if inline:
        scan_fail.append(f'{fn}: timeout(...) — инлайн-стрип tzinfo')
check(not scan_fail, 'ни один .timeout() не получает naive' + (f' — {scan_fail}' if scan_fail else ''))

print('== 4. Буфер пишет только aware-метки ==')
src = open(os.path.join(ROOT, 'cogs', 'proactive_mod.py'), encoding='utf-8').read()
append_zone = src.split("message_buffer [channel_id ].append", 1)[1].split('})', 1)[0]
check("datetime.now(timezone.utc)" in append_zone.replace(' ', '') or
      'datetime .now (timezone .utc )' in append_zone,
      "метка буфера — aware UTC")
check('replace(tzinfo=None)' not in append_zone.replace(' ', ''),
      'запись в буфер не стрипает таймзону')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
import shutil
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
