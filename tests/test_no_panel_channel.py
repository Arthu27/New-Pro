# -*- coding: utf-8 -*-
"""Бот не создаёт #hakumo-panel и не кидает туда ссылку."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = open(os.path.join(ROOT, 'main.py'), encoding='utf-8').read()

PASS = FAIL = 0


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


print('== send_panel_link no-op ==')
check('async def send_panel_link' in src, 'функция на месте (вызовы старта живы)')
check('create_text_channel("hakumo-panel"' not in src
      and "create_text_channel('hakumo-panel'" not in src,
      'create_text_channel(hakumo-panel) убран')
check('Ссылка на панель отправлена' not in src, 'публикация embed в канал убрана')
check('авто-канал hakumo-panel отключён' in src, 'явный no-op с логом')

print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
