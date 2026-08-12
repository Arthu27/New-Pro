# -*- coding: utf-8 -*-
"""Ядро ticket.py (3514 строк): классификатор нарушений + генерация карточек.

Запуск: python3 tests/test_ticket_core.py
"""
import io
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='aether_ticket_test_')
os.chdir(_TMP)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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


import discord  # noqa: E402,F401 — нужен для импорта кога
from PIL import Image  # noqa: E402

import cogs.ticket as T  # noqa: E402

# ═══ 1. _get_punishment_for_quote — классификатор ═══════════════════════
print('== классификатор нарушений ==')
r = T._get_punishment_for_quote('я тебя убью, слышишь')
check(r['action'] == 'BAN' and r['duration'] is None, 'угроза жизни → BAN без срока')

r = T._get_punishment_for_quote('orospu işleri bunlar')
check(r['action'] == 'BAN', 'турецкая тяжёлая брань → BAN')

r = T._get_punishment_for_quote('да что ты сука несёшь')
check(r['action'] == 'MUTE' and r['duration'] == 60, 'средняя брань → MUTE 60 мин')

r = T._get_punishment_for_quote('ты дурак что ли')
check(r['action'] == 'WARN' and r['duration'] == 0, 'лёгкое неуважение → WARN')

r = T._get_punishment_for_quote('нечестно сыграл, признайся')
check(r['action'] == 'WARN' and 'Нарушение правил' in r['reason'],
      'нейтральная фраза → дефолтный WARN')

r = T._get_punishment_for_quote('убью тебя, сука поганая')
check(r['action'] == 'BAN', 'приоритет: critical сильнее medium (BAN, не MUTE)')

r = T._get_punishment_for_quote('УБЬЮ!!')
check(r['action'] == 'BAN', 'регистр не спасает (lower)')

long_q = 'убью ' + 'очень ' * 40
r = T._get_punishment_for_quote(long_q)
inside = r['reason'].split('«', 1)[1].rstrip('»')
check(len(inside) <= 60, 'цитата в reason обрезается до 60 символов')
check(set(r.keys()) == {'action', 'duration', 'reason'}, 'контракт ключей результата')
check(r['reason'].startswith('Тяжелое оскорбление'), 'reason описывает тяжесть')

# ═══ 2. Генерация карточек (PIL, headless) ══════════════════════════════
print('== генерация карточек ==')
img = T.generate_ticket_panel_card()
check(isinstance(img, Image.Image) and img.width > 400 and img.height > 200,
      f'ticket panel card: Image {img.size}')

blob = T.generate_ticket_panel_bytes()
raw = blob.getvalue()
check(isinstance(blob, io.BytesIO) and raw[:4] == b'\x89PNG',
      'ticket panel bytes: валидный PNG')

b = T._icon_badge(64, T._icon_ticket)
check(isinstance(b, Image.Image) and b.size == (64, 64), '_icon_badge: 64×64')

br = T._corner_bracket(48, 6)
check(br.size == (48, 48), '_corner_bracket: 48×48')

p = T._rounded_panel(220, 120, 16)
check(p.size == (220, 120) and p.mode == 'RGBA', '_rounded_panel: 220×120 RGBA')

bg = T._load_bg(320, 200)
check(isinstance(bg, Image.Image) and bg.size == (320, 200), '_load_bg: фон заданного размера')

f = T._f(True, 24)
check(hasattr(f, 'getbbox') or hasattr(f, 'getsize'), '_f: шрифт загружен (bold 24)')

# ═══ 3. Структура кога ══════════════════════════════════════════════════
print('== структура кога ==')
import inspect  # noqa: E402

check(inspect.iscoroutinefunction(T.setup), 'async setup(bot) на месте')
for cls in ('Ticket', 'TicketView', 'CloseTicketView', 'AdminApprovalView',
            'TicketCategoryView', 'FeedbackView'):
    check(hasattr(T, cls), f'класс {cls} существует')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(0 if FAIL == 0 else 1)
