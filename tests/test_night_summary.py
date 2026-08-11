# -*- coding: utf-8 -*-
"""Тесты ночной сводки: cogs/night_summary.py.

Ловят класс бага из прод-логов: «name 'asyncio' is not defined» каждую
минуту — и следом идущий спам ретраев.

Запуск: python3 tests/test_night_summary.py
"""
import asyncio
import io
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone

# временная рабочая директория — data/* не мусорит в репо
_TMP = tempfile.mkdtemp(prefix='aether_sv_test_')
os.chdir(_TMP)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import discord

from cogs.night_summary import NightSummary

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


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ─── фейки ─────────────────────────────────────────────────────────────
class FakeChannel:
    def __init__(self, cid, name, fail=False):
        self.id = cid
        self.name = name
        self.mention = f'<#{cid}>'
        self.fail = fail
        self.sent = []

    async def send(self, embed=None, file=None, **kw):
        if self.fail:
            raise RuntimeError('канал недоступен')
        self.sent.append((embed, file))
        return object()


class FakeGuild:
    def __init__(self, gid=999, name='NightWatch', sys_ch=None):
        self.id = gid
        self.name = name
        self.system_channel = sys_ch

    def get_channel(self, cid):
        return None

    def get_member(self, uid):
        return None


class FakeBot:
    def __init__(self, guild):
        self.guilds = [guild]

    def get_cog(self, name):
        return None


GUILD = FakeGuild()
cog = NightSummary(FakeBot(GUILD))

# ─── заглушки «тяжёлых» частей ─────────────────────────────────────────
FAKE_STATS = {'warns': 3, 'bans': 1, 'kicks': 0, 'mutes': 5,
              'tagjail': 2, 'ghost': 4, 'errors': 0,
              'top_mod_id': 0, 'top_mod_count': 0}
cog.collect_day = lambda gid, day, off: dict(FAKE_STATS)
cog.render_card = lambda guild, day, stats: io.BytesIO(b'\x89PNG fake-card')

# ═══ 1. send_summary ════════════════════════════════════════════════════
print('== send_summary ==')
ch = FakeChannel(50, 'сводка')
day = datetime(2026, 8, 11)
ok = run(cog.send_summary(GUILD, day, channel=ch))
check(ok is True, 'send_summary: успешная отправка (asyncio-импорт жив!)')
check(ch.sent and ch.sent[0][1] is not None, 'карта сводки приложена файлом')
emb = ch.sent[0][0]
check(emb is not None and 'Ночная сводка' in (emb.description or '')
      and '**3**' in emb.description, 'эмбед с цифрами статистики')
check(emb.image.url == 'attachment://svodka_2026-08-11.png', 'картинка инлайнится в эмбед')

# без канала вообще — False, без исключения
ok = run(cog.send_summary(GUILD, day))
check(ok is False, 'нет канала сводки → False без падения')

# канал кидает ошибку — тоже False, не падаем
bad_ch = FakeChannel(51, 'сломанный', fail=True)
ok = run(cog.send_summary(GUILD, day, channel=bad_ch))
check(ok is False, 'канал кинул ошибку → False без падения')

# настоящий рендер карты (Pillow + шрифты ассетов)
buf = NightSummary.render_card(cog, GUILD, day, dict(FAKE_STATS))
check(buf.read(4) == b'\x89PNG', 'render_card: реальный PNG валиден')

# collect_day на пустых данных — нули, без падения
fresh = NightSummary(FakeBot(GUILD))
stats = fresh.collect_day(424242, day, 3)
check(stats['warns'] == 0 and stats['errors'] == 0, 'collect_day: пустые данные → нули')

# ═══ 2. _loop_once — расписание и антиспам ═══════════════════════════════
print('== _loop_once: расписание и антиспам ==')
attempts = []


async def fake_send(guild, day):
    attempts.append(day)
    return _send_result.get()


from collections import namedtuple   # noqa: E402
_send_result = namedtuple('Box', 'get')(lambda: True)
cog.send_summary = fake_send

night0 = datetime(2026, 8, 12, 0, 5)   # 00:05 локального — час сводки
daytime = datetime(2026, 8, 12, 14, 0)

# не рабочий час → тишина
run(cog._loop_once(GUILD, daytime))
check(len(attempts) == 0, 'не 00:xx — попыток нет')

# выключено → тишина
cog.set_cfg(GUILD.id, 'enabled', False)
run(cog._loop_once(GUILD, night0))
check(len(attempts) == 0, 'enabled=False — попыток нет')
cog.set_cfg(GUILD.id, 'enabled', True)

# первый запуск в час сводки — отправили, last_date проставлен
run(cog._loop_once(GUILD, night0))
check(len(attempts) == 1, 'в 00:xx сводка отправлена')
check(cog.cfg(GUILD.id)['last_date'] == '2026-08-12', 'last_date обновлён')

# повтор в тот же день — не дублируем
run(cog._loop_once(GUILD, night0.replace(minute=30)))
check(len(attempts) == 1, 'в этот день уже отправляли — дубля нет')

# ── неуспех: редкие ретраи и сдача ──
_send_result = namedtuple('Box2', 'get')(lambda: False)
G2 = FakeGuild(gid=777, name='FailHall')
cog2 = NightSummary(FakeBot(G2))
cog2.collect_day = lambda gid, day, off: dict(FAKE_STATS)
cog2.render_card = lambda guild, day, stats: io.BytesIO(b'x')
attempts.clear()
cog2.send_summary = fake_send

run(cog2._loop_once(G2, night0))
check(len(attempts) == 1, 'неудача №1: попытка была')
f1, _ = cog2._fails[G2.id]
check(f1 == 1, 'счётчик неудач = 1')

# тут же (через минуту) — повтор ЗАПРЕЩЁН троттлингом
run(cog2._loop_once(G2, night0.replace(minute=1)))
check(len(attempts) == 1, 'через минуту повтор заблокирован (антиспам)')

# "прошло" 5 минут — можно снова
c = list(cog2._fails[G2.id]); c[1] -= 301
cog2._fails[G2.id] = tuple(c)
run(cog2._loop_once(G2, night0.replace(minute=6)))
check(len(attempts) == 2, 'через 5 минут ретрай разрешён')

# догоняем до лимита и убеждаемся, что дальше — тишина
for i in range(10):
    c = list(cog2._fails.get(G2.id, (0, 0))); c[1] -= 301
    if c[0]:
        cog2._fails[G2.id] = tuple(c)
    run(cog2._loop_once(G2, night0))
check(len(attempts) <= 5, f'всего неудачных попыток ≤ 5 (было {len(attempts)}) — потом сдаться')
check(cog2._fails.get(G2.id, (0,))[0] >= 5, 'после 5 неудач сдались до завтра')
check(cog2.cfg(G2.id)['last_date'] == '', 'last_date НЕ записан — завтра всё будет снова')

# ─── финал ───────────────────────────────────────────────────────────────
import shutil  # noqa: E402
shutil.rmtree(_TMP, ignore_errors=True)
print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
