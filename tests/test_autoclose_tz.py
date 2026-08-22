# -*- coding: utf-8 -*-
"""Авто-закрытие тикетов: сравнение меток не должно падать на naive/aware.

Регрессия из живого лога бота:
  [AutoClose] Ошибка проверки ticket-...:
  can't compare offset-naive and offset-aware datetimes
Причина была: cutoff обрезался до naive (replace(tzinfo=None)),
а message.created_at у Discord — aware.

Запуск: python3 tests/test_autoclose_tz.py
"""
import asyncio
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

_TMP = tempfile.mkdtemp(prefix='aether_autoclose_')
os.environ['DB_PATH'] = os.path.join(_TMP, 'bot.db')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(_TMP)

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


import discord  # noqa: E402
from services.auto_close_service import AutoCloseService  # noqa: E402


class FakeMessage:
    def __init__(self, created_at):
        self.created_at = created_at
        self.author = None
        self.content = ''


class FakeChannel(discord.TextChannel):
    """Канал с подменённым history() — isinstance(TextChannel) проходит.
    __init__ не зовёт super() — дискордовый конструктор не нужен для фейка."""
    def __init__(self, name, messages):
        self.name = name
        self._messages = messages

    async def history(self, limit=1, oldest_first=False):
        for m in self._messages[:limit]:
            yield m


class FakeCategory:
    def __init__(self, channels):
        self.name = 'Тикеты'
        self.channels = channels


class FakeGuild:
    def __init__(self, categories):
        self.categories = categories


class FakeBot:
    def __init__(self, guilds):
        self.guilds = guilds


def run_case(service, guilds):
    """Прогнать _check_inactive_tickets и вернуть закрытые имена каналов."""
    closed = []

    async def fake_close(channel, last_message):
        closed.append(channel.name)

    service._close_inactive_ticket = fake_close
    asyncio.run(service._check_inactive_tickets())
    return closed


print('== сценарий из лога бота ==')
now = datetime.now(timezone.utc)

# 1) aware-сообщение старше порога → тикет закрывается, БЕЗ TypeError
svc = AutoCloseService(FakeBot([FakeGuild([FakeCategory([
    FakeChannel('ticket-old-aw', [FakeMessage(now - timedelta(hours=30))]),
])])]))
closed = run_case(svc, svc.bot.guilds)
check(closed == ['ticket-old-aw'],
      f'aware-метка старше порога закрывает тикет без падения (закрыто: {closed})')

# 2) aware-сообщение свежее порога → не трогаем
svc = AutoCloseService(FakeBot([FakeGuild([FakeCategory([
    FakeChannel('ticket-fresh', [FakeMessage(now - timedelta(hours=1))]),
])])]))
closed = run_case(svc, svc.bot.guilds)
check(closed == [], f'свежий тикет остаётся открытым (закрыто: {closed})')

# 3) легаси-naive метка старше порога → считаем UTC, закрываем (без падения)
svc = AutoCloseService(FakeBot([FakeGuild([FakeCategory([
    FakeChannel('ticket-legacynoper', [FakeMessage((now - timedelta(hours=40)).replace(tzinfo=None))]),
])])]))
closed = run_case(svc, svc.bot.guilds)
check(closed == ['ticket-legacynoper'],
      f'легаси-naive метка трактуется как UTC и закрывается (закрыто: {closed})')

# 4) канал не из «Тикетов» или не ticket-* — пропускается
svc = AutoCloseService(FakeBot([FakeGuild([FakeCategory([
    FakeChannel('general', [FakeMessage(now - timedelta(hours=40))]),
])])]))
closed = run_case(svc, svc.bot.guilds)
check(closed == [], f'не-ticket канал не трогается (закрыто: {closed})')

# 5) в исходнике нет наивного cutoff (сторож от регрессии)
src = open(os.path.join(ROOT, 'services', 'auto_close_service.py'), encoding='utf-8').read()
check('datetime.now(timezone.utc).replace(tzinfo=None)' not in src,
      'баговый naive-cutoff (now().replace(tzinfo=None)) удалён из сервиса')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(0 if FAIL == 0 else 1)
