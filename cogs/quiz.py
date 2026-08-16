# -*- coding: utf-8 -*-
"""Квиз-машина (Quiz)
====================
Викторины в чате: раунды вопросов от бота, первый верный ответ забирает очко,
сезонный топ знатоков. Активная сессия живёт в памяти (перезапуск бота её
сбрасывает), очки и библиотека вопросов — в SQLite.

Хранилище: GuildData('quiz')
  'questions' — [{q, answers[], added_by, added_at}] библиотека гильдии
  'scores'    — {user_id_str: {points, correct, wins}} сезонный зачёт

Команды (группа /квиз, префикс !квиз):
  старт [раунды] [секунды]   — начать викторину в текущем канале (мод)
  стоп                       — досрочно завершить (мод)
  топ                        — сезонный топ знатоков
  вопросы                    — сколько своих вопросов в библиотеке + примеры
  добавить <вопрос> | <ответы через ;>  — пополнить библиотеку (мод)
  удалить <номер>            — убрать вопрос из библиотеки (мод)
  обнулить                   — сбросить сезонный зачёт (мод)
"""
import asyncio
import json
import random
import re
import unicodedata
from datetime import datetime, timezone

import discord
from discord.ext import commands

from db import GuildData
from logger import get_logger
from services.text_format import plural_ru

log = get_logger('quiz')
UTC = timezone.utc

MIN_ROUNDS, MAX_ROUNDS = 1, 30
MIN_SECONDS, MAX_SECONDS = 5, 120
DEFAULT_ROUNDS, DEFAULT_SECONDS = 5, 20

# Встроенный стартовый пул — играется даже на пустой библиотеке.
DEFAULT_QUESTIONS = [
    {'q': 'Столица Японии?', 'answers': ['токио']},
    {'q': 'Сколько бит в одном байте?', 'answers': ['8', 'восемь']},
    {'q': 'Какой газ составляет большую часть атмосферы Земли?', 'answers': ['азот']},
    {'q': 'Сколько игроков футбольной команды одновременно на поле?', 'answers': ['11', 'одиннадцать']},
    {'q': 'Как называется самая большая планета Солнечной системы?', 'answers': ['юпитер']},
    {'q': 'В каком году человек впервые ступил на Луну?', 'answers': ['1969']},
    {'q': 'Какой химический элемент обозначается символом O?', 'answers': ['кислород']},
    {'q': 'Сколько сторон у шестиугольника?', 'answers': ['6', 'шесть']},
    {'q': 'Какой океан самый большой по площади?', 'answers': ['тихий', 'тихий океан']},
    {'q': 'Художник картины «Мона Лиза»?', 'answers': ['да винчи', 'леонардо да винчи', 'леонардо']},
    {'q': 'Сколько минут в трёх часах?', 'answers': ['180']},
    {'q': 'Корень квадратный из 144?', 'answers': ['12', 'двенадцать']},
]

_WORD_RE = re.compile(r'[\w]+', re.UNICODE)


def normalize_answer(text):
    """Ответ к сравнимому виду: нижний регистр, ё→е, только слова через пробел."""
    t = unicodedata.normalize('NFKC', str(text or '')).lower().replace('ё', 'е')
    return ' '.join(_WORD_RE.findall(t))


def split_spec(spec):
    """'Вопрос? | ответ1 ; ответ2' -> ('Вопрос?', ['ответ1', 'ответ2']) или (None, None)."""
    if '|' not in str(spec or ''):
        return None, None
    q, _, tail = spec.partition('|')
    q = q.strip()
    answers = [a.strip() for a in tail.split(';')]
    answers = [a for a in answers if normalize_answer(a)]
    if not q or not answers:
        return None, None
    return q, answers


def is_correct(content, answers):
    """Быстрый ответ — нормализованное равенство хотя бы одному варианту."""
    got = normalize_answer(content)
    if not got:
        return False
    return any(got == normalize_answer(a) for a in answers)


def sorted_scores(scores):
    """Зачёт к виду [(user_id, points, correct, wins), ...] по очкам убыв."""
    rows = [(uid, int(s.get('points', 0)), int(s.get('correct', 0)), int(s.get('wins', 0)))
            for uid, s in (scores or {}).items()]
    rows.sort(key=lambda r: (-r[1], -r[2], -r[3], r[0]))
    return rows


def session_standings(state):
    """Текущие очки сессии [(user_id, pts)] по убыванию."""
    rows = sorted(state['session_points'].items(), key=lambda kv: (-kv[1], kv[0]))
    return rows


def format_leader_lines(rows, limit=10):
    """Строки топа: '1. <@id> — 12 очков (правильных: 9, побед: 2)'."""
    lines = []
    for i, (uid, pts, correct, wins) in enumerate(rows[:limit], 1):
        lines.append(
            f'**{i}.** <@{uid}> — **{pts}** {plural_ru(pts, "очко", "очка", "очков")} '
            f'(правильных: {correct}, побед: {wins})'
        )
    return lines


class Quiz(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = GuildData('quiz')
        self.sessions = {}  # channel_id -> state

    # ── библиотека и зачёт ─────────────────────────────────────────────

    def _questions(self, guild_id):
        return self.db.get(guild_id, 'questions', []) or []

    def _save_questions(self, guild_id, questions):
        self.db.set(guild_id, 'questions', questions)

    def _scores(self, guild_id):
        return self.db.get(guild_id, 'scores', {}) or {}

    def _save_scores(self, guild_id, scores):
        self.db.set(guild_id, 'scores', scores)

    def _question_pool(self, guild_id, rounds):
        """Пул раундов: своя библиотека, если есть, иначе встроенная."""
        custom = [{'q': q['q'], 'answers': list(q['answers'])} for q in self._questions(guild_id)]
        pool = custom if custom else [dict(item) for item in DEFAULT_QUESTIONS]
        random.shuffle(pool)
        return pool[:max(1, min(rounds, len(pool)))], bool(custom), len(pool)

    # ── движок сессии ──────────────────────────────────────────────────

    async def _run_session(self, state):
        try:
            channel = state['channel']
            total = len(state['queue'])
            for idx, item in enumerate(state['queue'], 1):
                if state['cancelled']:
                    return
                state['current'] = item
                state['answered_by'] = None
                state['answered_event'].clear()
                await channel.send(
                    f'**Вопрос {idx}/{total}**\n{item["q"]}\n\n'
                    f'Пишите ответ в чат — время: {state["seconds"]} сек.'
                )
                try:
                    await asyncio.wait_for(state['answered_event'].wait(), timeout=state['seconds'])
                except asyncio.TimeoutError:
                    if not state['cancelled']:
                        await channel.send(
                            f'Время вышло. Правильный ответ: **{item["answers"][0]}**'
                        )
                if state['cancelled']:
                    return
                await asyncio.sleep(2)  # пауза между раундами
            await self._finish_session(state, reason='финиш')
        except asyncio.CancelledError:
            log.debug('Сессия квиза отменена штатно (стоп/завершение)')
        except Exception as e:
            log.error(f'Сессия квиза упала: {e}')
        finally:
            self.sessions.pop(state['channel'].id, None)

    async def _finish_session(self, state, reason='стоп'):
        state['cancelled'] = True
        rows = session_standings(state)
        channel = state['channel']
        if not rows:
            await channel.send(f'Викторина окончена ({reason}). Очков никто не набрал — в следующий раз повезёт!')
            return
        medals = ['1)', '2)', '3)']
        lines = []
        for i, (uid, pts) in enumerate(rows[:3], 1):
            lines.append(f'**{medals[i - 1]}** <@{uid}> — **{pts}** {plural_ru(pts, "очко", "очка", "очков")}')
        winner_id = rows[0][0]
        # сезонный зачёт: очки, правильные и победа
        scores = self._scores(state['guild_id'])
        for uid, pts in state['session_points'].items():
            entry = scores.setdefault(str(uid), {'points': 0, 'correct': 0, 'wins': 0})
            entry['points'] = int(entry.get('points', 0)) + pts
            entry['correct'] = int(entry.get('correct', 0)) + state['session_correct'].get(uid, 0)
        scores[str(winner_id)]['wins'] = int(scores[str(winner_id)].get('wins', 0)) + 1
        self._save_scores(state['guild_id'], scores)
        await channel.send(
            '**Викторина окончена!**\n' + '\n'.join(lines) +
            f'\n\nОчки ушли в сезонный зачёт — смотри `/квиз топ`.'
        )

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return
        state = self.sessions.get(message.channel.id)
        if not state or state['cancelled'] or state.get('current') is None:
            return
        if state['answered_by'] is not None:
            return
        if not is_correct(message.content, state['current']['answers']):
            return
        uid = message.author.id
        state['answered_by'] = uid
        state['session_points'][uid] = state['session_points'].get(uid, 0) + 1
        state['session_correct'][uid] = state['session_correct'].get(uid, 0) + 1
        state['answered_event'].set()
        await message.channel.send(
            f'Верно, {message.author.mention} забирает очко! Ответ: **{state["current"]["answers"][0]}**'
        )

    # ── команды ────────────────────────────────────────────────────────

    @commands.hybrid_group(name='квиз', aliases=['quiz'], description='Викторина: старт, топ, библиотека вопросов', fallback='помощь')
    async def grp(self, ctx):
        await ctx.send(
            '**Квиз-машина.** Команды: `/квиз старт [раунды] [секунды]`, `/квиз стоп`, '
            '`/квиз топ`, `/квиз вопросы`, `/квиз добавить вопрос | ответ`, `/квиз удалить №`, `/квиз обнулить`'
        )

    @grp.command(name='старт', aliases=['start'], description='Начать викторину: [раунды=5] [секунды=20]')
    @commands.has_permissions(manage_guild=True)
    async def start(self, ctx, rounds: int = DEFAULT_ROUNDS, seconds: int = DEFAULT_SECONDS):
        if ctx.channel.id in self.sessions:
            return await ctx.send('В этом канале уже идёт викторина — `/квиз стоп`, чтобы завершить.')
        if not (MIN_ROUNDS <= rounds <= MAX_ROUNDS):
            return await ctx.send(f'Раундов: от {MIN_ROUNDS} до {MAX_ROUNDS}.')
        if not (MIN_SECONDS <= seconds <= MAX_SECONDS):
            return await ctx.send(f'Секунд на вопрос: от {MIN_SECONDS} до {MAX_SECONDS}.')
        queue, custom, pool_size = self._question_pool(ctx.guild.id, rounds)
        state = {
            'guild_id': ctx.guild.id,
            'channel': ctx.channel,
            'queue': queue,
            'seconds': seconds,
            'current': None,
            'answered_by': None,
            'answered_event': asyncio.Event(),
            'cancelled': False,
            'session_points': {},
            'session_correct': {},
        }
        self.sessions[ctx.channel.id] = state
        source = 'своя библиотека' if custom else 'встроенный набор вопросов'
        await ctx.send(
            f'**Викторина начинается!** Раундов: **{len(queue)}**, на ответ — **{seconds}** сек '
            f'({source}, в пуле {pool_size}). Первый верный ответ забирает очко. Поехали!'
        )
        state['task'] = asyncio.create_task(self._run_session(state))

    @grp.command(name='стоп', aliases=['stop'], description='Досрочно завершить викторину')
    @commands.has_permissions(manage_guild=True)
    async def stop(self, ctx):
        state = self.sessions.get(ctx.channel.id)
        if not state:
            return await ctx.send('В этом канале викторина не идёт.')
        await self._finish_session(state, reason='стоп-модератором')
        self.sessions.pop(ctx.channel.id, None)
        task = state.get('task')
        if task:
            task.cancel()

    @grp.command(name='топ', aliases=['top'], description='Сезонный топ знатоков')
    async def top(self, ctx):
        rows = sorted_scores(self._scores(ctx.guild.id))
        if not rows:
            return await ctx.send('Зачёт пуст — сыграйте первую викторину: `/квиз старт`.')
        emb = discord.Embed(title='Квиз — сезонный топ', description='\n'.join(format_leader_lines(rows)),
                            color=0xF2B33D)
        emb.set_footer(text='Очки за первые верные ответы · сброс: /квиз обнулить')
        await ctx.send(embed=emb)

    @grp.command(name='вопросы', aliases=['bank'], description='Библиотека вопросов сервера')
    async def questions_cmd(self, ctx):
        questions = self._questions(ctx.guild.id)
        if not questions:
            return await ctx.send(
                f'Своя библиотека пуста — играется встроенный набор ({len(DEFAULT_QUESTIONS)} вопросов). '
                'Пополнить: `/квиз добавить вопрос | ответ`.'
            )
        preview = '\n'.join(f'**{i}.** {q["q"]}' for i, q in enumerate(questions[:5], 1))
        tail = f'\n…и ещё {len(questions) - 5}' if len(questions) > 5 else ''
        await ctx.send(f'**Своя библиотека:** {len(questions)} {plural_ru(len(questions), "вопрос", "вопроса", "вопросов")}\n{preview}{tail}')

    @grp.command(name='добавить', aliases=['add'], description='Добавить вопрос: <вопрос> | <ответы через ;>')
    @commands.has_permissions(manage_guild=True)
    async def add(self, ctx, *, spec: str):
        q, answers = split_spec(spec)
        if not q:
            return await ctx.send('Формат: `/квиз добавить Вопрос? | ответ` (варианты через «;»).')
        questions = self._questions(ctx.guild.id)
        if any(normalize_answer(item.get('q')) == normalize_answer(q) for item in questions):
            return await ctx.send('Такой вопрос уже есть в библиотеке.')
        questions.append({
            'q': q,
            'answers': answers,
            'added_by': str(ctx.author.id),
            'added_at': datetime.now(UTC).isoformat(),
        })
        self._save_questions(ctx.guild.id, questions)
        await ctx.send(f'Вопрос добавлен (**{len(questions)}** в библиотеке): {q} → {", ".join(answers)}')

    @grp.command(name='удалить', aliases=['del'], description='Удалить вопрос по номеру из «/квиз вопросы»')
    @commands.has_permissions(manage_guild=True)
    async def remove(self, ctx, index: int):
        questions = self._questions(ctx.guild.id)
        if not (1 <= index <= len(questions)):
            return await ctx.send(f'Нет вопроса с номером {index}. Смотри `/квиз вопросы`.')
        removed = questions.pop(index - 1)
        self._save_questions(ctx.guild.id, questions)
        await ctx.send(f'Удалён вопрос: {removed["q"]}')

    @grp.command(name='обнулить', aliases=['reset'], description='Сбросить сезонный зачёт')
    @commands.has_permissions(manage_guild=True)
    async def reset(self, ctx):
        self._save_scores(ctx.guild.id, {})
        await ctx.send('Сезонный зачёт обнулён. Чистый лист — `/квиз старт`!')


async def setup(bot):
    await bot.add_cog(Quiz(bot))
