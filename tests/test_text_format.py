# -*- coding: utf-8 -*-
"""Тесты services/text_format.py — русские склонения, длительности, сроки.

Запуск: python3 tests/test_text_format.py
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

_TMP = tempfile.mkdtemp(prefix='aether_textfmt_test_')
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
from services import text_format as tf  # noqa: E402

print('== 1. plural_ru: склонения ==')
cases = [
    (1, 'минута'), (2, 'минуты'), (4, 'минуты'), (5, 'минут'), (11, 'минут'),
    (21, 'минута'), (22, 'минуты'), (25, 'минут'), (101, 'минута'),
    (111, 'минут'), (112, 'минут'), (0, 'минут'),
]
ok = all(tf.plural_ru(n, 'минута', 'минуты', 'минут') == want for n, want in cases)
check(ok, f'таблица склонений «минута» {[c for c in cases if tf.plural_ru(c[0], "минута", "минуты", "минут") != c[1]] or "ок"}')
check(tf.plural_ru(-3, 'день', 'дня', 'дней') == 'дня', 'отрицательные по модулю')
check(tf.plural_ru('билайн', 'день', 'дня', 'дней') == 'дней', 'мусор -> форма many')
check(tf.spell(5, 'день', 'дня', 'дней') == '5 дней', 'spell: число + форма')

print('== 2. fmt_seconds / fmt_seconds_short ==')
check(tf.fmt_seconds(0) == '0 сек', '0 -> 0 сек')
check(tf.fmt_seconds(45) == '45 секунд', '45 -> 45 секунд')
check(tf.fmt_seconds(90) == '1 минута 30 секунд', '90 -> 1 минута 30 секунд')
check(tf.fmt_seconds(3600) == '1 час', '3600 -> 1 час')
check(tf.fmt_seconds(3661) == '1 час 1 минута 1 секунда', 'собирает часы+минуты+секунды')
check(tf.fmt_seconds(90061) == '1 день 1 час 1 минута', 'дни: секунды не шумят, максимум 3 единицы')
check(tf.fmt_seconds(604800) == '7 дней', 'неделя — это 7 дней (без турецких единиц)')
check(tf.fmt_seconds(None) == '0 сек' and tf.fmt_seconds('x') == '0 сек', 'устойчивость к мусору')
check(tf.fmt_seconds(-50) == '0 сек', 'отрицательные зажаты в ноль')
check(tf.fmt_seconds_short(90061) == '1д 1ч 1м', 'short: 1д 1ч 1м')
check(tf.fmt_seconds_short(30) == '30с', 'short: 30с')

print('== 3. parse_duration ==')
dur_cases = [
    ('5м', 300), ('5 минут', 300), ('1ч30м', 5400), ('2 часа', 7200),
    ('1 день 2 часа', 93600), ('30s', 30), ('2h', 7200), ('1w', 604800),
    ('45', 45), ('1нед', 604800), ('1 мес', 2592000),
]
bad = [(t, tf.parse_duration(t), w) for t, w in dur_cases if tf.parse_duration(t) != w]
check(not bad, f'таблица длительностей RU+EN {bad or "ок"}')
check(tf.parse_duration('примерно') is None, 'без цифр -> None')
check(tf.parse_duration('5 световых лет') is None, 'неизвестная единица -> None')
check(tf.parse_duration('') is None and tf.parse_duration(None) is None, 'пустое -> None')

print('== 4. parse_deadline ==')
now = datetime(2026, 8, 13, 10, 0, 0, tzinfo=UTC)
check(tf.parse_deadline('через 5м', now) == now + timedelta(minutes=5), '«через 5м» — относительный срок')
check(tf.parse_deadline('2ч', now) == now + timedelta(hours=2), 'голая длительность — тоже срок')
check(tf.parse_deadline('18:30', now) == now.replace(hour=18, minute=30), '«18:30» — сегодня, если впереди')
check(tf.parse_deadline('09:15', now) == (now + timedelta(days=1)).replace(hour=9, minute=15),
      '«09:15» при 10:00 — завтра')
check(tf.parse_deadline('2026-08-20 12:00', now)
      == datetime(2026, 8, 20, 12, 0, tzinfo=UTC), 'ISO дата-время')
check(tf.parse_deadline('2020-01-01 00:00', now) is None, 'прошедшая ISO дата -> None')
check(tf.parse_deadline('скоро', now) is None, 'мусор -> None')
check(tf.parse_deadline('18:30', now.replace(tzinfo=None)).tzinfo is not None,
      'naive now не роняет парсер (пояс восстанавливается)')

print('== 5. rel_time / clamp_text / extract_words ==')
check(tf.rel_time(now + timedelta(minutes=5), now) == 'через 5 минут', 'будущее -> «через …»')
check(tf.rel_time(now - timedelta(hours=2), now) == '2 часа назад', 'прошлое -> «… назад»')
check(tf.rel_time((now + timedelta(seconds=90)).isoformat(), now) == 'через 1 минута 30 секунд',
      'ISO-строка на входе')
check(tf.rel_time('билайн', now) == '?', 'мусор -> ?')
check(tf.clamp_text('x' * 2000, 1024) == 'x' * 1023 + '…', 'clamp до 1024 с многоточием')
check(tf.clamp_text('короткий', 1024) == 'короткий', 'короткий текст не трогаем')
check(tf.clamp_text(None, 10) == '', 'None -> пустая строка')
check(tf.extract_words('ПРИВЕТ, как дела? 42') == ['привет', 'как', 'дела', '42'],
      'extract_words: только слова/числа, в lower')

print('== 6. Строгость линтов слоя ==')
import ast
src = open(os.path.join(ROOT, 'services', 'text_format.py'), encoding='utf-8').read()
tree = ast.parse(src)
silent = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler)
          and len(n.body) == 1 and isinstance(n.body[0], (ast.Pass, ast.Continue))]
check(not silent, f'нет молчаливых except {silent or "ок"}')
check('utcnow' not in src, 'utcnow() не используется (только aware UTC)')

import shutil
shutil.rmtree(_TMP, ignore_errors=True)
print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
