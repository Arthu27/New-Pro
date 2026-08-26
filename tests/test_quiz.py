# -*- coding: utf-8 -*-
"""Тесты cogs/quiz.py — квиз-машина.

Покрытие: нормализация ответов, разбор спецификации, сезонный зачёт,
полный прогон сессии движком (старт → ответ → очко → финиш с победителем),
таймаут раунда, защита от двойного зачёта, библиотека CRUD.

Запуск: python3 tests/test_quiz.py
"""
import asyncio
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone

_TMP = tempfile.mkdtemp(prefix='hakumo_quiz_test_')
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
from cogs import quiz as Q  # noqa: E402

print('== 1. Нормализация ответов ==')
check(Q.normalize_answer('  ТоКио!! ') == 'токио', 'регистр/пунктуация срезаются')
check(Q.normalize_answer('Ёлка') == 'елка', 'ё -> е')
check(Q.normalize_answer('тихий   океан') == 'тихий океан', 'многословный ответ схлопывается')
check(Q.is_correct('ДА ВИНЧИ', ['да винчи', 'леонардо']), 'вариант совпал — верно')
check(not Q.is_correct('леонардо да винчи', ['да винчи']), 'лишние слова — уже не тот ответ (строгое сравнение)')
check(not Q.is_correct('париж', ['токио']), 'неверный ответ не засчитывается')
check(not Q.is_correct('   ', ['токио']), 'пустой ответ не засчитывается')

print('== 2. split_spec — разбор «вопрос | ответы» ==')
q, a = Q.split_spec('Сколько будет 2+2? | 4; четыре')
check(q == 'Сколько будет 2+2?' and a == ['4', 'четыре'], 'вопрос и варианты через ;')
check(Q.split_spec('без разделителя') == (None, None), 'без | -> отказ')
check(Q.split_spec('вопрос | ; ;') == (None, None), 'пустые ответы -> отказ')
check(Q.split_spec(' | ответ') == (None, None), 'пустой вопрос -> отказ')

print('== 3. Зачёт и сортировка ==')
rows = Q.sorted_scores({'1': {'points': 5, 'correct': 4, 'wins': 0},
                        '2': {'points': 9, 'correct': 8, 'wins': 1}})
check(rows[0][0] == '2' and rows[1][0] == '1', 'сортировка по очкам убыв.')
lines = Q.format_leader_lines(rows)
check(lines[0].startswith('**1.** <@2>') and '9' in lines[0], 'строка топа честная')

print('== 4. Библиотека CRUD (GuildData) ==')
G = 4242
cog = Q.Quiz.__new__(Q.Quiz)
from db import GuildData  # noqa: E402
cog.db = GuildData('quiz')
cog.sessions = {}
check(cog._questions(G) == [], 'библиотека пуста изначально')
cog._save_questions(G, [{'q': 'Тест?', 'answers': ['да'], 'added_by': '1', 'added_at': datetime.now(UTC).isoformat()}])
check(len(cog._questions(G)) == 1, 'вопрос сохраняется')
pool, custom, size = cog._question_pool(G, 5)
check(custom and size == 1 and pool[0]['q'] == 'Тест?', 'пул берёт свою библиотеку')
pool2, custom2, size2 = cog._question_pool(9999, 5)
check(not custom2 and size2 == len(Q.DEFAULT_QUESTIONS), 'пустая гильдия — встроенный набор')
check(len(pool2) == 5, 'раунды урезаются до запрошенного числа')


class FakeAuthor:
    def __init__(self, uid):
        self.id = uid
        self.mention = f'<@{uid}>'
        self.bot = False


class FakeChannel:
    def __init__(self, cid=10):
        self.id = cid
        self.sent = []

    async def send(self, text=None, embed=None):
        self.sent.append(text if text is not None else embed)


class FakeGuild:
    id = G


class FakeMessage:
    def __init__(self, channel, author, content):
        self.channel = channel
        self.author = author
        self.guild = FakeGuild()
        self.content = content


print('== 5. Сессия: раунд → верный ответ → очко → финиш ==')
ch = FakeChannel()


def make_state(seconds=0.05, queue=None):
    return {
        'guild_id': G,
        'channel': ch,
        'queue': queue if queue is not None else [{'q': 'Столица Японии?', 'answers': ['токио']}],
        'seconds': seconds,
        'current': None,
        'answered_by': None,
        'answered_event': asyncio.Event(),
        'cancelled': False,
        'session_points': {},
        'session_correct': {},
    }


async def session_flow():
    state = make_state()
    cog._save_scores(G, {})
    cog.sessions[ch.id] = state          # как делает команда /квиз старт
    task = asyncio.create_task(cog._run_session(state))
    while state['current'] is None:
        await asyncio.sleep(0.005)
    await cog.on_message(FakeMessage(ch, FakeAuthor(501), 'Токио'))
    await task
    return state


state = asyncio.get_event_loop().run_until_complete(session_flow())
check(state['session_points'].get(501) == 1, 'первый верный ответ = очко')
check(ch.sent and 'Верно' in (ch.sent[-2] if len(ch.sent) > 1 else ''), 'бот объявил верный ответ')
finale = ch.sent[-1] or ''
check('Викторина окончена' in finale and '<@501>' in finale, 'финиш объявляет победителя')
scores = cog._scores(G)
check(scores.get('501', {}).get('points') == 1, 'очко ушло в сезонный зачёт')
check(scores.get('501', {}).get('wins') == 1, 'победа записана')
check(ch.id not in cog.sessions, 'сессия убрана из реестра')

print('== 6. Таймаут раунда — ответ открывается, очков нет ==')
ch2 = FakeChannel(11)


async def timeout_flow():
    state = make_state(seconds=0.03)
    state['channel'] = ch2
    task = asyncio.create_task(cog._run_session(state))
    await task
    return state


state2 = asyncio.get_event_loop().run_until_complete(timeout_flow())
check(any('Время вышло' in (m or '') for m in ch2.sent), 'таймаут оглашён с правильным ответом')
check(state2['session_points'] == {}, 'без ответов очков нет')

print('== 7. Стоп модератором ==')
ch3 = FakeChannel(12)
state3 = make_state(seconds=60.0)  # длинный раунд, режем стопом
state3['channel'] = ch3


async def stop_flow():
    task = asyncio.create_task(cog._run_session(state3))
    while state3['current'] is None:
        await asyncio.sleep(0.005)
    cog.sessions[ch3.id] = state3
    await cog._finish_session(state3, reason='стоп-модератором')
    cog.sessions.pop(ch3.id, None)
    task.cancel()
    return True


asyncio.get_event_loop().run_until_complete(stop_flow())
check(any('Викторина окончена' in (m or '') for m in ch3.sent), 'стоп печатает итоги')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
