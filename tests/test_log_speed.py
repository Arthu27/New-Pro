# -*- coding: utf-8 -*-
"""Мгновенные логи в каналах (заказ владельца: «инфу долго собирает, пипец
медленно — сделай почти моментально»).

Причина была найдена профайлером: каждый лог-карточка кодировалась в PNG
с optimize=True — ~1.2 СЕКУНДЫ чистого кодирования на каждый лог, и всё
это синхронно в event loop (бот замирал). Рисование само по себе ~90 мс.

Проверяем:
1. render_log_card отдаёт JPEG (\xff\xd8), быстро (<150 мс на повторных,
   <400 мс на холодном старте) и файлом <300 КБ.
2. _safe_send рендерит в ОТДЕЛЬНОМ ПОТОКЕ (to_thread) и шлёт .jpg.
3. Дубль «Команды» убран из меню «Контент» (сам маршрут /execute-command
   жив — им пользуется профиль участника).

Запуск: python3 tests/test_log_speed.py
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault('DB_PATH', '/tmp/aether_logspeed.db')

PASS = 0


def ok(name, cond, extra=''):
    global PASS
    if not cond:
        print(f'FAIL: {name} {extra}')
        sys.exit(1)
    PASS += 1
    print(f'  ok - {name}')


print('== 1. Карточка лога: JPEG и быстро ==')
from services.log_card import render_log_card, LOG_CARD_OK  # noqa: E402
ok('PIL доступен (карточки рисуются)', LOG_CARD_OK)

rows = [('Участник', 'Тестовый юзер (123456789012345678)'),
        ('Причина', 'спам'), ('Канал', '#общий')]
t0 = time.perf_counter()
card = render_log_card('mod', 'Проверка скорости', rows, color=0xE74C3C,
                       cat_name='Модерация', guild_name='Сервер', time_str='12:00 UTC')
cold = (time.perf_counter() - t0) * 1000
ok('карточка рендерится', bool(card))
ok(f'холодный рендер < 400 мс ({cold:.0f} мс; было ~1285)', cold < 400)
ok('это JPEG (магия \\xff\\xd8)', card[:2] == b'\xff\xd8')
ok(f'файл < 300 КБ ({len(card)//1024} КБ; было 537)', len(card) < 300 * 1024)

t0 = time.perf_counter()
for _ in range(10):
    render_log_card('mod', 'Проверка скорости', rows, color=0xE74C3C,
                    cat_name='Модерация', guild_name='Сервер', time_str='12:00 UTC')
warm = (time.perf_counter() - t0) * 100
ok(f'тёплый рендер < 150 мс ({warm:.0f} мс; было ~1271)', warm < 150)

print('== 2. Отправка: не блокирует бота ==')
logs_src = open(os.path.join(ROOT, 'cogs/logs.py'), encoding='utf-8').read()
ok('рендер карточки в отдельном потоке (to_thread)',
   'to_thread (render_log_card' in logs_src)
ok('лог-карточка шлётся .jpg', "filename ='aether_log_card.jpg')" in logs_src
   and 'attachment://aether_log_card.jpg' in logs_src)
ok('старый тяжёлый .png отправкой не остался', 'aether_log_card.png' not in logs_src)

print('== 3. Дубль «Команды» убран из меню ==')
from services import panel_menu as PM  # noqa: E402
content = next((g for g in PM.MENU if g.get('key') == 'content'), None)
ok('группа «Контент» на месте', content is not None)
ok('«Команда» (/execute-command) больше НЕ в меню «Контент»',
   all(p.get('path') != '/execute-command' for p in (content or {}).get('pages', [])))
ok('маршрут /execute-command жив (нужен профилю участника)',
   '/execute-command' in open(os.path.join(ROOT, 'web/app.py'), encoding='utf-8').read())

print(f'\nALL {PASS} PASS — логи летают, дубль убран')
