# -*- coding: utf-8 -*-
"""Стабильность бота на VDS (заказ владельца 2026-08: «почему отключается»).

1. Короткие разрывы с Discord — норма, но они должны быть ВИДНЫ в логе
   (on_disconnect / on_resumed в main.py).
2. Смерть процесса — не норма: start.sh поднимает бот сам (цикл),
   systemd-служба deploy/hakumo.service — правильный способ на VDS.
3. Неверный токен — код выхода 7: скрипты не крутят бесконечный
   перезапуск против битого TOKEN.
Запуск: python3 tests/test_vds_stability.py
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PASS = 0


def ok(name, cond, extra=''):
    global PASS
    if not cond:
        print(f'FAIL: {name} {extra}')
        sys.exit(1)
    PASS += 1
    print(f'  ok - {name}')


main_src = open(os.path.join(ROOT, 'main.py'), encoding='utf-8').read()
ok('разрыв связи с Discord виден в логе (on_disconnect)',
   'async def on_disconnect' in main_src and 'потеряно' in main_src)
ok('восстановление связи видно (on_resumed, события не теряются)',
   'async def on_resumed' in main_src and 'resume' in main_src.lower())
ok('внутренний цикл переподключения с паузой 5→60 сек на месте',
   'while True' in main_src and '_delay = min(60' in main_src)
ok('неверный/пропавший токен — код 7 (без вечного перезапуска)',
   main_src.count('sys.exit(7)') == 2)

sh = open(os.path.join(ROOT, 'start.sh'), encoding='utf-8').read()
ok('start.sh: авто-поднятие процесса (цикл while true)',
   'while true' in sh and 'sleep 5' in sh)
ok('start.sh: битый токен не гоняет цикл (выход по коду 7)',
   '"$CODE" -eq 7' in sh)
ok('start.sh: советует systemd-службу для VDS',
   'VDS-SETUP.md' in sh)
ok('start.sh синтаксически валиден (bash -n)',
   os.system('bash -n start.sh') == 0)

svc = open(os.path.join(ROOT, 'deploy', 'hakumo.service'), encoding='utf-8').read()
ok('systemd-служба: Restart=always + 5 сек',
   'Restart=always' in svc and 'RestartSec=5' in svc)
ok('systemd-служба: стартует после сети',
   'network-online.target' in svc)

guide = open(os.path.join(ROOT, 'deploy', 'VDS-SETUP.md'), encoding='utf-8').read()
for marker in ('journalctl -u hakumo -f', 'OOM', 'enable --now hakumo',
               'Короткие переподключения'):
    ok(f'инструкция VDS содержит «{marker}»', marker in guide)

print(f'\nALL {PASS} PASS — бот на VDS поднимается сам')
