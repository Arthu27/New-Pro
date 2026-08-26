# -*- coding: utf-8 -*-
"""Тесты cogs/staff_shifts.py — стафф-смены с автонапоминаниями.

Покрытие: разбор дня недели и диапазона времени, окна смен (включая смену
через полночь), «кто сейчас/следующий», и главное — цикл напоминаний
check_cycle с подменённым временем: старт пингует один раз, конец смены
благодарит один раз, идемпотентно. CRUD через командные колбэки.

Запуск: python3 tests/test_staff_shifts.py
"""
import asyncio
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone

_TMP = tempfile.mkdtemp(prefix='hakumo_shifts_test_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
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
from cogs import staff_shifts as S  # noqa: E402
from db import GuildData  # noqa: E402

GID = 4242
# пятница 14.08.2026; расписание: пт 18:00–22:00 МСК = 15:00–19:00 UTC
SHIFT = {'user_id': 501, 'weekday': 4, 'start': '18:00', 'end': '22:00'}
START_UTC = datetime(2026, 8, 14, 15, 0, 30, tzinfo=UTC)   # 18:00:30 МСК — смена идёт
END_UTC = datetime(2026, 8, 14, 19, 0, 10, tzinfo=UTC)     # 22:00:10 МСК — только кончилась


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


print('== 1. Разбор дня недели и времени ==')
check(S.parse_weekday('пт') == 4 and S.parse_weekday('суббота') == 5 and S.parse_weekday('mon') == 0, 'алиасы дней')
check(S.parse_weekday('апрель') is None, 'мусор -> None')
check(S.parse_time_range('18:00-22:00') == (1080, 1320), 'обычный диапазон')
check(S.parse_time_range('22:00-02:00') == (1320, 120), 'через полночь — валиден')
check(S.parse_time_range('24:00-02:00') is None and S.parse_time_range('18:00-18:00') is None
      and S.parse_time_range('утро-вечер') is None, 'мусор/вырождение -> None')
check(S.fmt_time(1320) == '22:00' and S.fmt_time(5) == '00:05', 'обратное форматирование')

print('== 2. Кто сейчас / следующий ==')
check(S.active_shift([SHIFT], START_UTC, 3)[0]['user_id'] == 501, 'активная смена находится')
check(S.active_shift([SHIFT], END_UTC, 3) is None, 'после конца — никого')
mid = datetime(2026, 8, 15, 0, 30, tzinfo=UTC)  # сб 03:30 МСК — вне смены
check(S.active_shift([SHIFT], mid, 3) is None, 'ночью вне смены — пусто')
night_shift = {'user_id': 7, 'weekday': 4, 'start': '22:00', 'end': '02:00'}  # пт→сб
wrap_now = datetime(2026, 8, 14, 21, 30, tzinfo=UTC)  # сб 00:30 МСК
check(S.active_shift([night_shift], wrap_now, 3)[0]['user_id'] == 7, 'смена через полночь активна ночью')
nxt = S.next_shift([SHIFT], END_UTC, 3)
wait_days = (nxt[1] - END_UTC).total_seconds() / 86400
check(nxt[0]['user_id'] == 501 and nxt[0]['weekday'] == 4 and 6.7 < wait_days < 7.2,
      'следующая — через неделю (та же пятница)')
table = S.week_table([SHIFT])
check('**пт** <@501> `18:00–22:00`' in table and '**чт** —' in table, 'таблица недели честная')

print('== 3. Цикл напоминаний (подменённое время) ==')


class FakeChannel:
    def __init__(self, cid):
        self.id = cid
        self.sent = []

    async def send(self, text=None, embed=None):
        self.sent.append(text if text is not None else embed)


class FakeBot:
    def __init__(self, channel):
        self._channel = channel

    def get_channel(self, cid):
        return self._channel if cid == self._channel.id else None


chan = FakeChannel(10)
cog = S.StaffShifts.__new__(S.StaffShifts)
cog.bot = FakeBot(chan)
cog.db = GuildData('staff_shifts')
cog.db.set(GID, 'shifts', {'ab12': dict(SHIFT)})
cog.db.set(GID, 'settings', {'channel_id': 10, 'tz_offset': 3})

events = run(cog.check_cycle(GID, START_UTC))
check(events and events[0][0] == 'start', 'старт смены замечен')
check(any('Смена началась' in (m or '') and '<@501>' in (m or '') for m in chan.sent), 'пинг дежурному ушёл')
sent_after_start = len(chan.sent)
run(cog.check_cycle(GID, START_UTC))
check(len(chan.sent) == sent_after_start, 'повторный тик не дублирует пинг (идемпотентно)')

mid = datetime(2026, 8, 14, 16, 0, 0, tzinfo=UTC)  # 19:00 МСК — середина смены
events = run(cog.check_cycle(GID, mid))
check(events == [], 'в середине смены тишина')

events = run(cog.check_cycle(GID, END_UTC))
check(events and events[0][0] == 'end', 'конец смены замечен')
check(any('завершена' in (m or '') for m in chan.sent), 'благодарность ушла')
check(any('Следующая смена' in (m or '') for m in chan.sent), 'назван следующий дежурный')
sent_after_end = len(chan.sent)
run(cog.check_cycle(GID, END_UTC))
check(len(chan.sent) == sent_after_end, 'конец тоже идемпотентен')

print('== 4. CRUD через команды ==')


class FakeUser:
    id = 778899

    def __str__(self):
        return 'Mod#1'


class FakeCtx:
    def __init__(self):
        self.guild = type('G', (), {'id': 7777})()
        self.author = type('A', (), {'id': 1})()
        self.answers = []

    async def send(self, text=None, embed=None):
        self.answers.append(text if text is not None else embed)


ctx = FakeCtx()
run(S.StaffShifts.assign.callback(cog, ctx, user=FakeUser(), weekday='сб', time_range='10:00-14:00'))
check(any('Смена добавлена' in (a or '') for a in ctx.answers), 'назначить: ок')
sid = list(cog._shifts(7777).keys())
check(len(sid) == 1, 'смена в базе')
ctx2 = FakeCtx()
run(S.StaffShifts.assign.callback(cog, ctx2, user=FakeUser(), weekday='сб', time_range='10:00-14:00'))
check(any('уже назначена' in (a or '') for a in ctx2.answers), 'дублей не плодим')
ctx3 = FakeCtx()
run(S.StaffShifts.assign.callback(cog, ctx3, user=FakeUser(), weekday='abracadabra', time_range='10:00-14:00'))
check(any('Не понял день' in (a or '') for a in ctx3.answers), 'кривой день — внятный отказ')
ctx4 = FakeCtx()
run(S.StaffShifts.revoke.callback(cog, ctx4, shift_id=sid[0]))
check(cog._shifts(7777) == {}, 'снять: смена удалена')
ctx5 = FakeCtx()
run(S.StaffShifts.set_tz.callback(cog, ctx5, offset=99))
check(any('Пояс: от -12 до +14' in (a or '') for a in ctx5.answers), 'пояс за пределами — отказ')

print('== 5. Политика сообщений — без декоративных эмодзи ==')
src = open(os.path.join(ROOT, 'cogs', 'staff_shifts.py'), encoding='utf-8').read()
import re as _re
check(not _re.search(r'[\U0001F000-\U0001FAFF\u2600-\u27BF]', src), 'эмодзи в модуле нет')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
